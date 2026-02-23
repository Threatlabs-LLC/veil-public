"""Quota usage API — shows current resource usage vs tier limits."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user
from backend.db.session import get_db
from backend.licensing.tiers import get_tier
from backend.models.api_key import ApiKey
from backend.models.organization import Organization
from backend.models.rule import DetectionRule
from backend.models.user import User
from backend.models.webhook import Webhook

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/quota")
async def get_quota(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current resource usage vs tier limits for the organization."""
    org = await db.get(Organization, user.organization_id)
    tier_def = get_tier(org.tier if org else "free")

    user_count = (await db.execute(
        select(func.count(User.id)).where(User.organization_id == user.organization_id)
    )).scalar() or 0

    custom_rule_count = (await db.execute(
        select(func.count(DetectionRule.id)).where(
            DetectionRule.organization_id == user.organization_id,
            DetectionRule.is_built_in == False,
        )
    )).scalar() or 0

    webhook_count = (await db.execute(
        select(func.count(Webhook.id)).where(
            Webhook.organization_id == user.organization_id,
        )
    )).scalar() or 0

    api_key_count = (await db.execute(
        select(func.count(ApiKey.id)).where(
            ApiKey.organization_id == user.organization_id,
            ApiKey.is_active == True,
        )
    )).scalar() or 0

    return {
        "tier": org.tier if org else "free",
        "tier_name": tier_def.name,
        "users": {"current": user_count, "limit": tier_def.max_users},
        "custom_rules": {"current": custom_rule_count, "limit": tier_def.max_custom_rules},
        "webhooks": {"current": webhook_count, "limit": tier_def.max_webhooks},
        "api_keys": {"current": api_key_count},
        "audit_retention_days": tier_def.audit_retention_days,
        "api_rate_limit": tier_def.api_rate_limit,
        "gateway_rate_limit": tier_def.gateway_rate_limit,
    }
