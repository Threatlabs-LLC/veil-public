"""Authentication API — JWT login/register + API key management."""

import logging
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Security
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
    import hashlib
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
        import uuid
        slug = f"{slug}-{str(uuid.uuid4())[:8]}"

    org = Organization(name=org_name, slug=slug, tier="free")
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
