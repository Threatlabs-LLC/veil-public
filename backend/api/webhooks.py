"""Webhook management — CRUD for webhook endpoints, test delivery."""

import json
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user
from backend.core.events import EventType, VeilChatEvent, WebhookConfig, event_bus
from backend.db.session import get_db
from backend.licensing.dependencies import require_feature
from backend.licensing.tiers import FEATURE_WEBHOOKS, get_tier
from backend.models.organization import Organization
from backend.models.user import User
from backend.models.webhook import Webhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class WebhookCreate(BaseModel):
    name: str
    url: str
    event_types: list[str] = []  # empty = all events
    format: str = "json"  # json | slack


class WebhookUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    event_types: list[str] | None = None
    format: str | None = None
    is_active: bool | None = None


class WebhookOut(BaseModel):
    id: str
    name: str
    url: str
    secret: str | None
    event_types: list[str]
    format: str
    is_active: bool
    failure_count: int
    last_triggered_at: str | None
    last_error: str | None
    created_at: str


def _webhook_to_out(w: Webhook) -> WebhookOut:
    return WebhookOut(
        id=w.id,
        name=w.name,
        url=w.url,
        secret=w.secret[:8] + "..." if w.secret else None,
        event_types=json.loads(w.event_types) if w.event_types else [],
        format=w.format,
        is_active=w.is_active,
        failure_count=w.failure_count,
        last_triggered_at=str(w.last_triggered_at) if w.last_triggered_at else None,
        last_error=w.last_error,
        created_at=str(w.created_at),
    )


@router.get("", response_model=list[WebhookOut])
async def list_webhooks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Webhook)
        .where(Webhook.organization_id == user.organization_id)
        .order_by(Webhook.created_at.desc())
    )
    return [_webhook_to_out(w) for w in result.scalars().all()]


@router.post("", response_model=WebhookOut, status_code=201,
             dependencies=[Depends(require_feature(FEATURE_WEBHOOKS))])
async def create_webhook(
    body: WebhookCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check webhook limit for tier
    org = await db.get(Organization, user.organization_id)
    tier_def = get_tier(org.tier if org else "community")
    existing = await db.execute(
        select(Webhook).where(Webhook.organization_id == user.organization_id)
    )
    webhook_count = len(existing.scalars().all())
    if webhook_count >= tier_def.max_webhooks:
        raise HTTPException(
            403,
            f"Webhook limit reached ({tier_def.max_webhooks} on {tier_def.name} plan). "
            "Upgrade to add more webhooks.",
        )

    # Validate webhook URL against SSRF
    from backend.core.url_validator import is_safe_url
    safe, reason = is_safe_url(body.url)
    if not safe:
        raise HTTPException(400, f"Invalid webhook URL: {reason}")

    if body.format not in ("json", "slack"):
        raise HTTPException(400, "Format must be 'json' or 'slack'")

    # Validate event types
    valid_types = {e.value for e in EventType}
    for et in body.event_types:
        if et not in valid_types:
            raise HTTPException(400, f"Invalid event type: {et}. Valid: {sorted(valid_types)}")

    signing_secret = secrets.token_hex(16)

    webhook = Webhook(
        organization_id=user.organization_id,
        name=body.name,
        url=body.url,
        secret=signing_secret,
        event_types=json.dumps(body.event_types) if body.event_types else "[]",
        format=body.format,
    )
    db.add(webhook)
    await db.flush()

    # Register with the event bus
    _register_webhook_with_bus(webhook)

    return _webhook_to_out(webhook)


@router.patch("/{webhook_id}", response_model=WebhookOut,
              dependencies=[Depends(require_feature(FEATURE_WEBHOOKS))])
async def update_webhook(
    webhook_id: str,
    body: WebhookUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Webhook).where(
            Webhook.id == webhook_id,
            Webhook.organization_id == user.organization_id,
        )
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(404, "Webhook not found")

    if body.name is not None:
        webhook.name = body.name
    if body.url is not None:
        from backend.core.url_validator import is_safe_url
        safe, reason = is_safe_url(body.url)
        if not safe:
            raise HTTPException(400, f"Invalid webhook URL: {reason}")
        webhook.url = body.url
    if body.event_types is not None:
        webhook.event_types = json.dumps(body.event_types)
    if body.format is not None:
        webhook.format = body.format
    if body.is_active is not None:
        webhook.is_active = body.is_active

    return _webhook_to_out(webhook)


@router.delete("/{webhook_id}",
               dependencies=[Depends(require_feature(FEATURE_WEBHOOKS))])
async def delete_webhook(
    webhook_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Webhook).where(
            Webhook.id == webhook_id,
            Webhook.organization_id == user.organization_id,
        )
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(404, "Webhook not found")

    await db.delete(webhook)
    return {"status": "deleted"}


@router.post("/{webhook_id}/test",
             dependencies=[Depends(require_feature(FEATURE_WEBHOOKS))])
async def test_webhook(
    webhook_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a test event to the webhook."""
    result = await db.execute(
        select(Webhook).where(
            Webhook.id == webhook_id,
            Webhook.organization_id == user.organization_id,
        )
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(404, "Webhook not found")

    test_event = VeilChatEvent(
        event_type=EventType.ENTITY_DETECTED,
        org_id=user.organization_id,
        user_id=user.id,
        data={"entity_type": "TEST", "count": 1, "message": "This is a test event from VeilChat"},
        severity="info",
    )

    config = WebhookConfig(
        url=webhook.url,
        event_types=None,
        format=webhook.format,
        secret=webhook.secret,
    )

    try:
        await event_bus._send_webhook(config, test_event)
        return {"status": "sent", "message": "Test event delivered successfully"}
    except Exception as e:
        raise HTTPException(502, f"Webhook delivery failed: {str(e)}")


def _register_webhook_with_bus(webhook: Webhook) -> None:
    """Register a webhook from the DB with the global event bus."""
    event_types_raw = json.loads(webhook.event_types) if webhook.event_types else []
    event_types = [EventType(et) for et in event_types_raw] if event_types_raw else None

    config = WebhookConfig(
        url=webhook.url,
        event_types=event_types,
        format=webhook.format,
        is_active=webhook.is_active,
        secret=webhook.secret,
    )
    event_bus.register_webhook(config)


async def load_webhooks_from_db(db: AsyncSession) -> None:
    """Load all active webhooks from DB and register with event bus. Called on startup."""
    result = await db.execute(
        select(Webhook).where(Webhook.is_active == True)
    )
    for webhook in result.scalars().all():
        _register_webhook_with_bus(webhook)
