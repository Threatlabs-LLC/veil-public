"""FastAPI dependencies for license/tier checks.

Usage in endpoints:

    @router.post("/rules", dependencies=[Depends(require_feature(FEATURE_CUSTOM_RULES))])
    async def create_rule(...):
        ...

    @router.get("/advanced", dependencies=[Depends(require_tier("team"))])
    async def advanced_endpoint(...):
        ...
"""

from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user
from backend.db.session import get_db
from backend.licensing.tiers import get_tier, tier_at_least, tier_has_feature
from backend.models.organization import Organization
from backend.models.user import User


async def get_org_tier(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Get the current organization's tier. Dependency for other checks."""
    org = await db.get(Organization, user.organization_id)
    return org.tier if org else "free"


def require_tier(required: str):
    """Dependency factory: require a minimum tier level.

    Usage: dependencies=[Depends(require_tier("team"))]
    """
    async def _check(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        org = await db.get(Organization, user.organization_id)
        current = org.tier if org else "free"
        if not tier_at_least(current, required):
            tier_def = get_tier(required)
            raise HTTPException(
                403,
                {
                    "error": "tier_required",
                    "message": f"This feature requires the {tier_def.name} plan or higher.",
                    "current_tier": current,
                    "required_tier": required,
                },
            )
        return org
    return _check


def require_feature(feature: str):
    """Dependency factory: require a specific feature flag.

    Usage: dependencies=[Depends(require_feature(FEATURE_WEBHOOKS))]
    """
    async def _check(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        org = await db.get(Organization, user.organization_id)
        current = org.tier if org else "free"
        if not tier_has_feature(current, feature):
            raise HTTPException(
                403,
                {
                    "error": "feature_not_available",
                    "message": f"The '{feature}' feature is not available on your current plan.",
                    "current_tier": current,
                    "feature": feature,
                },
            )
        return org
    return _check
