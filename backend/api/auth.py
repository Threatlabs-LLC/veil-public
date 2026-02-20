"""Authentication API — JWT login/register + Google OAuth + API key management."""

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import bcrypt
import httpx
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.seed import seed_built_in_data
from backend.db.session import get_db
from backend.models.organization import Organization
from backend.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()
bearer_scheme = HTTPBearer(auto_error=False)

# --- Login attempt tracking ---
_MAX_FAILED_ATTEMPTS = 10
_LOCKOUT_SECONDS = 900  # 15 minutes
# In-memory store: email -> (failure_count, first_failure_time)
_login_attempts: dict[str, tuple[int, datetime]] = {}


def _check_lockout(email: str) -> None:
    """Raise 429 if account is locked out from too many failed attempts."""
    entry = _login_attempts.get(email)
    if not entry:
        return
    count, first_failure = entry
    if count >= _MAX_FAILED_ATTEMPTS:
        elapsed = (datetime.now(timezone.utc) - first_failure).total_seconds()
        if elapsed < _LOCKOUT_SECONDS:
            raise HTTPException(
                429,
                f"Too many failed login attempts. Try again in {int(_LOCKOUT_SECONDS - elapsed)} seconds.",
            )
        # Lockout expired — reset
        _login_attempts.pop(email, None)


def _record_failed_login(email: str) -> None:
    """Record a failed login attempt."""
    entry = _login_attempts.get(email)
    now = datetime.now(timezone.utc)
    if entry:
        count, first_failure = entry
        elapsed = (now - first_failure).total_seconds()
        if elapsed > _LOCKOUT_SECONDS:
            # Window expired, start fresh
            _login_attempts[email] = (1, now)
        else:
            _login_attempts[email] = (count + 1, first_failure)
    else:
        _login_attempts[email] = (1, now)


def _clear_failed_logins(email: str) -> None:
    """Clear failed login tracking on successful login."""
    _login_attempts.pop(email, None)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

ALGORITHM = "HS256"


# --- Schemas ---

class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str | None = None
    org_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str | None
    role: str
    organization_id: str


# --- Token helpers ---

def create_access_token(user_id: str, org_id: str) -> tuple[str, int]:
    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": user_id,
        "org": org_id,
        "exp": expire,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
    return token, int(expires_delta.total_seconds())


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency — extracts and validates the current user from JWT or API key."""
    if not credentials:
        # In cloud mode, always require authentication
        from backend.config import settings as app_settings
        if app_settings.cloud_mode:
            raise HTTPException(401, "Not authenticated")
        # Fall back to default user for community edition (no auth required)
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        if user:
            return user
        raise HTTPException(401, "Not authenticated")

    token = credentials.credentials

    # Try JWT first
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(401, "Invalid token")

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(401, "User not found or inactive")

        # Validate org claim matches user's actual org (detect stale tokens)
        token_org = payload.get("org")
        if token_org and token_org != user.organization_id:
            raise HTTPException(401, "Token organization mismatch — please re-login")

        return user

    except JWTError:
        # Try as API key (prefix: vk_)
        if token.startswith("vk_"):
            return await _validate_api_key(token, db)
        raise HTTPException(401, "Invalid authentication credentials")


async def _validate_api_key(key: str, db: AsyncSession) -> User:
    """Validate a VeilChat API key by looking up its SHA-256 hash."""
    from backend.models.api_key import ApiKey

    key_hash = hashlib.sha256(key.encode()).hexdigest()
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(401, "Invalid API key")

    # Update last_used_at
    api_key.last_used_at = datetime.now(timezone.utc)

    # Look up the user
    result = await db.execute(select(User).where(User.id == api_key.user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(401, "API key owner is inactive")
    return user


# --- Endpoints ---

@router.post("/auth/register", response_model=TokenResponse)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user and organization."""
    # Validate password strength
    if len(request.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")

    # Check if email already exists
    result = await db.execute(select(User).where(User.email == request.email))
    if result.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")

    # Create org
    org_name = request.org_name or request.email.split("@")[0]
    slug = org_name.lower().replace(" ", "-")[:100]
    # Ensure slug uniqueness
    result = await db.execute(select(Organization).where(Organization.slug == slug))
    if result.scalar_one_or_none():
        slug = f"{slug}-{str(uuid.uuid4())[:8]}"

    org = Organization(name=org_name, slug=slug, tier="free", subscription_status=None)
    db.add(org)
    await db.flush()

    # Create user
    user = User(
        organization_id=org.id,
        email=request.email,
        display_name=request.display_name or request.email.split("@")[0],
        password_hash=_hash_password(request.password),
        role="owner",
    )
    db.add(user)
    await db.flush()

    # Seed built-in rules and default policies for the new org
    await seed_built_in_data(org.id, db)

    token, expires_in = create_access_token(user.id, org.id)

    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user={
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "organization_id": org.id,
        },
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with email and password."""
    _check_lockout(request.email)

    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        _record_failed_login(request.email)
        raise HTTPException(401, "Invalid email or password")

    if not _verify_password(request.password, user.password_hash):
        _record_failed_login(request.email)
        raise HTTPException(401, "Invalid email or password")

    if not user.is_active:
        raise HTTPException(403, "Account is deactivated")

    # Successful login — clear lockout tracking
    _clear_failed_logins(request.email)

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)

    token, expires_in = create_access_token(user.id, user.organization_id)

    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user={
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "organization_id": user.organization_id,
        },
    )


@router.get("/auth/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    """Get the current authenticated user."""
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        organization_id=user.organization_id,
    )


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    email: str | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@router.patch("/auth/profile", response_model=UserOut)
async def update_profile(
    body: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's profile."""
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.email is not None:
        # Check uniqueness
        result = await db.execute(
            select(User).where(User.email == body.email, User.id != user.id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(400, "Email already in use")
        user.email = body.email

    return UserOut(
        id=user.id, email=user.email, display_name=user.display_name,
        role=user.role, organization_id=user.organization_id,
    )


@router.post("/auth/change-password")
async def change_password(
    body: PasswordChange,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password."""
    if not user.password_hash:
        raise HTTPException(400, "No password set for this account")

    if not _verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")

    if len(body.new_password) < 8:
        raise HTTPException(400, "New password must be at least 8 characters")

    user.password_hash = _hash_password(body.new_password)
    return {"status": "password_changed"}


# --- Password Reset ---

# In-memory reset token store: token_hash -> (user_id, expiry)
_reset_tokens: dict[str, tuple[str, datetime]] = {}


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


def _send_reset_email(to_email: str, reset_url: str) -> bool:
    """Send password reset email via SMTP. Returns True on success."""
    if not settings.smtp_host or not settings.smtp_from_email:
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Reset your VeilProxy password"
        msg["From"] = settings.smtp_from_email
        msg["To"] = to_email

        text = f"Reset your password by visiting: {reset_url}\n\nThis link expires in 30 minutes."
        html = f"""<div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:24px">
<h2 style="color:#5B6BC0">VeilProxy Password Reset</h2>
<p>Click the button below to reset your password. This link expires in 30 minutes.</p>
<a href="{reset_url}" style="display:inline-block;background:#5B6BC0;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600">Reset Password</a>
<p style="margin-top:24px;color:#888;font-size:12px">If you didn't request this, you can safely ignore this email.</p>
</div>"""

        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return True
    except Exception as e:
        logger.error("Failed to send reset email: %s", e)
        return False


@router.post("/auth/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Request a password reset link. Always returns success for security."""
    # Clean up expired tokens
    now = datetime.now(timezone.utc)
    expired = [k for k, v in _reset_tokens.items() if v[1] < now]
    for k in expired:
        _reset_tokens.pop(k, None)

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user and user.is_active:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        _reset_tokens[token_hash] = (user.id, now + timedelta(minutes=30))

        # Build reset URL
        if settings.cloud_mode:
            base_url = "https://app.veilproxy.ai"
        elif settings.cors_origins:
            base_url = settings.cors_origins[0].rstrip("/")
        else:
            base_url = "http://localhost:5173"
        reset_url = f"{base_url}/reset-password?token={token}"

        sent = _send_reset_email(user.email, reset_url)
        if not sent and settings.debug:
            logger.info("Password reset link (SMTP not configured): %s", reset_url)

    # Always return same response (never reveal if email exists)
    return {"status": "ok", "message": "If that email is registered, a reset link has been sent."}


@router.post("/auth/reset-password")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Reset password using a valid reset token."""
    if len(body.new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")

    token_hash = hashlib.sha256(body.token.encode()).hexdigest()

    # Clean up expired tokens
    now = datetime.now(timezone.utc)
    expired = [k for k, v in _reset_tokens.items() if v[1] < now]
    for k in expired:
        _reset_tokens.pop(k, None)

    entry = _reset_tokens.get(token_hash)
    if not entry:
        raise HTTPException(400, "Invalid or expired reset token")

    user_id, expiry = entry
    if now > expiry:
        _reset_tokens.pop(token_hash, None)
        raise HTTPException(400, "Invalid or expired reset token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(400, "Invalid or expired reset token")

    user.password_hash = _hash_password(body.new_password)
    _reset_tokens.pop(token_hash, None)

    return {"status": "ok", "message": "Password has been reset. You can now sign in."}


# --- Google OAuth ---

# In-memory CSRF state store: state_hash -> expiry
_oauth_states: dict[str, datetime] = {}


def _cleanup_expired_states() -> None:
    """Remove expired OAuth states."""
    now = datetime.now(timezone.utc)
    expired = [k for k, v in _oauth_states.items() if v < now]
    for k in expired:
        _oauth_states.pop(k, None)


@router.get("/auth/google/authorize")
async def google_authorize():
    """Return the Google OAuth consent URL."""
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(501, "Google OAuth is not configured")

    state = secrets.token_urlsafe(32)
    state_hash = hashlib.sha256(state.encode()).hexdigest()

    _cleanup_expired_states()
    _oauth_states[state_hash] = datetime.now(timezone.utc) + timedelta(minutes=10)

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": _google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return {"authorize_url": f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"}


@router.get("/auth/google/callback")
async def google_callback(code: str, state: str, db: AsyncSession = Depends(get_db)):
    """Handle Google OAuth callback — exchange code, find/create user, redirect with token."""
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(501, "Google OAuth is not configured")

    # Validate CSRF state
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    _cleanup_expired_states()
    if state_hash not in _oauth_states:
        raise HTTPException(400, "Invalid or expired OAuth state")
    _oauth_states.pop(state_hash, None)

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": _google_redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
        if token_res.status_code != 200:
            logger.error("Google token exchange failed: %s", token_res.text)
            raise HTTPException(400, "Failed to exchange Google authorization code")
        token_data = token_res.json()

        # Get user info
        userinfo_res = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        if userinfo_res.status_code != 200:
            raise HTTPException(400, "Failed to fetch Google user info")
        google_user = userinfo_res.json()

    google_id = google_user["id"]
    email = google_user.get("email", "")
    name = google_user.get("name", email.split("@")[0])

    if not email:
        raise HTTPException(400, "Google account has no email address")

    # Find existing user by OAuth ID
    result = await db.execute(
        select(User).where(User.oauth_provider == "google", User.oauth_id == google_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        # Try matching by email (link existing password account)
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user:
            # Link OAuth to existing account
            user.oauth_provider = "google"
            user.oauth_id = google_id
        else:
            # Create new user + org
            org_name = email.split("@")[0]
            slug = org_name.lower().replace(" ", "-")[:100]
            result = await db.execute(select(Organization).where(Organization.slug == slug))
            if result.scalar_one_or_none():
                import uuid
                slug = f"{slug}-{str(uuid.uuid4())[:8]}"

            org = Organization(name=org_name, slug=slug, tier="free", subscription_status=None)
            db.add(org)
            await db.flush()

            user = User(
                organization_id=org.id,
                email=email,
                display_name=name,
                password_hash=None,
                oauth_provider="google",
                oauth_id=google_id,
                role="owner",
            )
            db.add(user)
            await db.flush()

            await seed_built_in_data(org.id, db)

    if not user.is_active:
        raise HTTPException(403, "Account is deactivated")

    user.last_login_at = datetime.now(timezone.utc)

    token, expires_in = create_access_token(user.id, user.organization_id)

    # Redirect to frontend with token in URL fragment (never sent to server)
    return RedirectResponse(
        url=f"/login?oauth_token={token}",
        status_code=302,
    )


def _google_redirect_uri() -> str:
    """Build the Google OAuth redirect URI based on environment."""
    if settings.cloud_mode:
        return "https://app.veilproxy.ai/api/auth/google/callback"
    # For self-hosted, use the first CORS origin or localhost
    if settings.cors_origins:
        base = settings.cors_origins[0].rstrip("/")
        return f"{base}/api/auth/google/callback"
    return "http://localhost:8000/api/auth/google/callback"
