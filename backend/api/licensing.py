"""License management API — upload, validate, and check license status."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user
from backend.db.session import get_db
from backend.licensing.tiers import TIERS, get_tier
from backend.licensing.validator import (
    LicenseExpiredError,
    LicenseInvalidError,
    get_validator,
)
from backend.models.organization import Organization
from backend.models.user import User

router = APIRouter(prefix="/licensing", tags=["licensing"])


class LicenseUpload(BaseModel):
    license_key: str


class LicenseStatus(BaseModel):
    tier: str
    tier_name: str
    max_users: int
    features: list[str]
    is_licensed: bool
    expires_at: str | None = None
    days_remaining: int | None = None
    license_id: str | None = None


class TierInfo(BaseModel):
    id: str
    name: str
    level: int
    max_users: int
    max_custom_rules: int
    max_webhooks: int
    audit_retention_days: int
    features: list[str]


@router.get("/status", response_model=LicenseStatus)
async def get_license_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current license/tier status for this organization."""
    org = await db.get(Organization, user.organization_id)
    if not org:
        raise HTTPException(404, "Organization not found")

    tier_def = get_tier(org.tier)

    # Try to read features from org settings
    features = sorted(tier_def.features)

    result = LicenseStatus(
        tier=org.tier,
        tier_name=tier_def.name,
        max_users=org.max_users,
        features=features,
        is_licensed=org.tier != "free",
    )

    # If there's a stored license, try to get expiry info
    try:
        org_settings = json.loads(org.settings) if isinstance(org.settings, str) else {}
    except (json.JSONDecodeError, TypeError):
        org_settings = {}

    license_key = org_settings.get("license_key")
    if license_key:
        validator = get_validator()
        try:
            claims = validator.validate(license_key)
            result.expires_at = str(claims.expires_at)
            result.days_remaining = claims.days_remaining
            result.license_id = claims.license_id
        except (LicenseInvalidError, LicenseExpiredError):
            pass

    return result


@router.post("/activate", response_model=LicenseStatus)
async def activate_license(
    body: LicenseUpload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload and activate a license key. Owner only."""
    if user.role != "owner":
        raise HTTPException(403, "Only the organization owner can manage licenses")

    org = await db.get(Organization, user.organization_id)
    if not org:
        raise HTTPException(404, "Organization not found")

    validator = get_validator()
    if not validator.is_configured:
        raise HTTPException(
            400,
            "License validation is not configured on this instance. "
            "Contact your administrator to set up the public key.",
        )

    # Validate the license
    try:
        claims = validator.validate(body.license_key.strip())
    except LicenseExpiredError:
        raise HTTPException(400, "This license key has expired.")
    except LicenseInvalidError as e:
        raise HTTPException(400, f"Invalid license key: {e}")

    # Verify org ID matches (or allow any org if not specified)
    if claims.org_id and claims.org_id != org.id:
        raise HTTPException(400, "This license key was issued for a different organization.")

    # Validate tier exists
    if claims.tier not in TIERS:
        raise HTTPException(400, f"Unknown tier in license: {claims.tier}")

    tier_def = get_tier(claims.tier)

    # Store license in org settings
    try:
        org_settings = json.loads(org.settings) if isinstance(org.settings, str) else {}
    except (json.JSONDecodeError, TypeError):
        org_settings = {}

    org_settings["license_key"] = body.license_key.strip()
    org.settings = json.dumps(org_settings)

    # Update org tier and limits
    org.tier = claims.tier
    org.max_users = claims.max_users

    await db.commit()

    return LicenseStatus(
        tier=org.tier,
        tier_name=tier_def.name,
        max_users=org.max_users,
        features=sorted(tier_def.features),
        is_licensed=True,
        expires_at=str(claims.expires_at),
        days_remaining=claims.days_remaining,
        license_id=claims.license_id,
    )


@router.delete("/deactivate")
async def deactivate_license(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove current license and revert to Community tier. Owner only."""
    if user.role != "owner":
        raise HTTPException(403, "Only the organization owner can manage licenses")

    org = await db.get(Organization, user.organization_id)
    if not org:
        raise HTTPException(404, "Organization not found")

    # Remove license from settings
    try:
        org_settings = json.loads(org.settings) if isinstance(org.settings, str) else {}
    except (json.JSONDecodeError, TypeError):
        org_settings = {}

    org_settings.pop("license_key", None)
    org.settings = json.dumps(org_settings)

    # Revert to community
    org.tier = "free"
    org.max_users = get_tier("free").max_users

    await db.commit()

    return {"status": "deactivated", "tier": "free"}


@router.get("/tiers", response_model=list[TierInfo])
async def list_tiers():
    """List all available tiers and their features. Public endpoint."""
    return [
        TierInfo(
            id=tier_id,
            name=t.name,
            level=t.level,
            max_users=t.max_users,
            max_custom_rules=t.max_custom_rules,
            max_webhooks=t.max_webhooks,
            audit_retention_days=t.audit_retention_days,
            features=sorted(t.features),
        )
        for tier_id, t in TIERS.items()
    ]
