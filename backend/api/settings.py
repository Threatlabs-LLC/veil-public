"""Settings API — org-level configuration for API keys, defaults, etc."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user
from backend.core.audit import log_audit_event
from backend.db.session import get_db
from backend.models.organization import Organization
from backend.models.user import User

router = APIRouter(prefix="/settings", tags=["settings"])


class OrgSettings(BaseModel):
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434/v1"
    default_provider: str = "openai"
    default_model: str = "gpt-4o-mini"
    sanitization_enabled: bool = True
    min_confidence: float = 0.7


class OrgSettingsUpdate(BaseModel):
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    ollama_base_url: str | None = None
    default_provider: str | None = None
    default_model: str | None = None
    sanitization_enabled: bool | None = None
    min_confidence: float | None = None


def _mask_key(key: str) -> str:
    """Mask API key for display (show first 8 and last 4 chars)."""
    if not key or len(key) < 16:
        return "***" if key else ""
    return f"{key[:8]}...{key[-4:]}"


def _parse_settings(org: Organization) -> dict:
    """Parse org.settings JSON into a dict."""
    if not org.settings:
        return {}
    try:
        return json.loads(org.settings) if isinstance(org.settings, str) else org.settings
    except (json.JSONDecodeError, TypeError):
        return {}


@router.get("", response_model=OrgSettings)
async def get_settings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get organization settings (API keys are masked)."""
    org = await db.get(Organization, user.organization_id)
    if not org:
        raise HTTPException(404, "Organization not found")

    data = _parse_settings(org)
    from backend.config import settings as global_settings
    from backend.core.crypto import decrypt
    return OrgSettings(
        openai_api_key=_mask_key(decrypt(data.get("openai_api_key", ""))),
        anthropic_api_key=_mask_key(decrypt(data.get("anthropic_api_key", ""))),
        ollama_base_url=data.get("ollama_base_url", global_settings.ollama_base_url),
        default_provider=data.get("default_provider", "openai"),
        default_model=data.get("default_model", "gpt-4o-mini"),
        sanitization_enabled=data.get("sanitization_enabled", True),
        min_confidence=data.get("min_confidence", 0.7),
    )


class OrgProfile(BaseModel):
    name: str
    slug: str
    tier: str
    max_users: int
    is_active: bool
    user_count: int = 0


class OrgProfileUpdate(BaseModel):
    name: str | None = None


@router.get("/org", response_model=OrgProfile)
async def get_org_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get organization profile information."""
    from sqlalchemy import func, select as sa_select
    org = await db.get(Organization, user.organization_id)
    if not org:
        raise HTTPException(404, "Organization not found")

    result = await db.execute(
        sa_select(func.count(User.id)).where(User.organization_id == org.id)
    )
    user_count = result.scalar() or 0

    return OrgProfile(
        name=org.name,
        slug=org.slug,
        tier=org.tier,
        max_users=org.max_users,
        is_active=org.is_active,
        user_count=user_count,
    )


@router.patch("/org", response_model=OrgProfile)
async def update_org_profile(
    body: OrgProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update organization profile. Owner only."""
    if user.role != "owner":
        raise HTTPException(403, "Owner access required")

    from sqlalchemy import func, select as sa_select
    org = await db.get(Organization, user.organization_id)
    if not org:
        raise HTTPException(404, "Organization not found")

    old_name = org.name
    if body.name is not None:
        org.name = body.name

    await log_audit_event(
        db, user.organization_id, "org.profile_updated",
        user_id=user.id,
        http_status=200,
        content_before=old_name,
        content_after=org.name,
    )

    result = await db.execute(
        sa_select(func.count(User.id)).where(User.organization_id == org.id)
    )
    user_count = result.scalar() or 0

    return OrgProfile(
        name=org.name,
        slug=org.slug,
        tier=org.tier,
        max_users=org.max_users,
        is_active=org.is_active,
        user_count=user_count,
    )


@router.patch("", response_model=OrgSettings)
async def update_settings(
    body: OrgSettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update organization settings. Only admins/owners can update."""
    if user.role not in ("owner", "admin"):
        raise HTTPException(403, "Admin access required")

    org = await db.get(Organization, user.organization_id)
    if not org:
        raise HTTPException(404, "Organization not found")

    data = _parse_settings(org)

    # Update only provided fields (encrypt API keys at rest)
    from backend.core.crypto import encrypt
    if body.openai_api_key is not None:
        data["openai_api_key"] = encrypt(body.openai_api_key) if body.openai_api_key else ""
    if body.anthropic_api_key is not None:
        data["anthropic_api_key"] = encrypt(body.anthropic_api_key) if body.anthropic_api_key else ""
    if body.ollama_base_url is not None:
        from backend.core.url_validator import is_safe_url
        safe, reason = is_safe_url(body.ollama_base_url)
        if not safe:
            raise HTTPException(400, f"Invalid Ollama URL: {reason}")
        data["ollama_base_url"] = body.ollama_base_url
    if body.default_provider is not None:
        data["default_provider"] = body.default_provider
    if body.default_model is not None:
        data["default_model"] = body.default_model
    if body.sanitization_enabled is not None:
        data["sanitization_enabled"] = body.sanitization_enabled
    if body.min_confidence is not None:
        data["min_confidence"] = body.min_confidence

    org.settings = json.dumps(data)

    # Log which settings fields were changed (without exposing values)
    changed_fields = [k for k, v in body.model_dump(exclude_unset=True).items() if v is not None]
    await log_audit_event(
        db, user.organization_id, "org.settings_updated",
        user_id=user.id,
        http_status=200,
        content_after=", ".join(changed_fields),
    )

    from backend.config import settings as global_settings
    from backend.core.crypto import decrypt as _decrypt
    return OrgSettings(
        openai_api_key=_mask_key(_decrypt(data.get("openai_api_key", ""))),
        anthropic_api_key=_mask_key(_decrypt(data.get("anthropic_api_key", ""))),
        ollama_base_url=data.get("ollama_base_url", global_settings.ollama_base_url),
        default_provider=data.get("default_provider", "openai"),
        default_model=data.get("default_model", "gpt-4o-mini"),
        sanitization_enabled=data.get("sanitization_enabled", True),
        min_confidence=data.get("min_confidence", 0.7),
    )
