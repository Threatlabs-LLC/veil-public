"""Event bus — fires events for entity detection, policy violations, usage thresholds.

Supports webhook delivery to Slack, Teams, email, and custom HTTP endpoints.
Events are processed asynchronously to never block the request path.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    ENTITY_DETECTED = "entity.detected"
    POLICY_VIOLATION = "policy.violation"
    HIGH_RISK_REQUEST = "request.high_risk"
    USAGE_THRESHOLD = "usage.threshold"
    AUTH_FAILURE = "auth.failure"
    PROVIDER_ERROR = "provider.error"


@dataclass
class VeilChatEvent:
    event_type: EventType
    org_id: str
    user_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data: dict = field(default_factory=dict)
    severity: str = "info"  # info | warning | critical

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type.value,
            "org_id": self.org_id,
            "user_id": self.user_id,
            "timestamp": self.timestamp,
            "data": self.data,
            "severity": self.severity,
        }

    def to_slack_block(self) -> dict:
        """Format as a Slack Block Kit message."""
        severity_emoji = {"info": "shield", "warning": "warning", "critical": "rotating_light"}
        emoji = severity_emoji.get(self.severity, "bell")
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f":{emoji}: VeilChat: {self.event_type.value}",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Severity:* {self.severity}"},
                        {"type": "mrkdwn", "text": f"*Time:* {self.timestamp}"},
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"```{json.dumps(self.data, indent=2)[:1000]}```",
                    },
                },
            ],
        }


@dataclass
class WebhookConfig:
    url: str
    event_types: list[EventType] | None = None  # None = all events
    format: str = "json"  # json | slack
    headers: dict = field(default_factory=dict)
    is_active: bool = True
    secret: str | None = None  # HMAC signing secret


class EventBus:
    """Async event bus with webhook delivery."""

    def __init__(self):
        self._handlers: list[Callable] = []
        self._webhooks: list[WebhookConfig] = []
        self._queue: asyncio.Queue | None = None
        self._worker_task: asyncio.Task | None = None

    def register_handler(self, handler: Callable) -> None:
        """Register a sync/async handler for all events."""
        self._handlers.append(handler)

    def register_webhook(self, config: WebhookConfig) -> None:
        """Register a webhook endpoint."""
        self._webhooks.append(config)

    async def start(self) -> None:
        """Start the background event processing worker."""
        self._queue = asyncio.Queue()
        self._worker_task = asyncio.create_task(self._process_events())

    async def stop(self) -> None:
        """Stop the event processing worker."""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def emit(self, event: VeilChatEvent) -> None:
        """Emit an event — never blocks the caller."""
        if self._queue:
            await self._queue.put(event)
        else:
            # If worker not started, process inline (dev mode)
            await self._deliver_event(event)

    async def _process_events(self) -> None:
        """Background worker that processes events from the queue."""
        while True:
            try:
                event = await self._queue.get()
                await self._deliver_event(event)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Event processing error: {e}")

    async def _deliver_event(self, event: VeilChatEvent) -> None:
        """Deliver event to all handlers and webhooks."""
        # Call registered handlers
        for handler in self._handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Event handler error: {e}")

        # Deliver to webhooks
        for webhook in self._webhooks:
            if not webhook.is_active:
                continue
            if webhook.event_types and event.event_type not in webhook.event_types:
                continue

            try:
                await self._send_webhook(webhook, event)
            except Exception as e:
                logger.error(f"Webhook delivery error ({webhook.url}): {e}")

    async def _send_webhook(self, webhook: WebhookConfig, event: VeilChatEvent) -> None:
        """Send event to a single webhook endpoint."""
        if webhook.format == "slack":
            payload = event.to_slack_block()
        else:
            payload = event.to_dict()

        body_bytes = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json", **webhook.headers}

        # Sign the payload with HMAC-SHA256 if a secret is configured
        if webhook.secret:
            import hashlib
            import hmac
            signature = hmac.new(
                webhook.secret.encode(), body_bytes, hashlib.sha256
            ).hexdigest()
            headers["X-VeilChat-Signature"] = f"sha256={signature}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                webhook.url, content=body_bytes, headers=headers
            )
            if response.status_code >= 400:
                logger.warning(
                    f"Webhook {webhook.url} returned {response.status_code}: {response.text[:200]}"
                )


# Global event bus instance
event_bus = EventBus()


# --- Convenience functions ---

async def emit_entity_detected(
    org_id: str, user_id: str, entity_type: str, count: int, **kwargs
) -> None:
    await event_bus.emit(VeilChatEvent(
        event_type=EventType.ENTITY_DETECTED,
        org_id=org_id,
        user_id=user_id,
        data={"entity_type": entity_type, "count": count, **kwargs},
        severity="info",
    ))


async def emit_policy_violation(
    org_id: str, user_id: str, entity_type: str, action: str, **kwargs
) -> None:
    await event_bus.emit(VeilChatEvent(
        event_type=EventType.POLICY_VIOLATION,
        org_id=org_id,
        user_id=user_id,
        data={"entity_type": entity_type, "action": action, **kwargs},
        severity="warning",
    ))


async def emit_high_risk_request(
    org_id: str, user_id: str, risk_score: float, reason: str, **kwargs
) -> None:
    await event_bus.emit(VeilChatEvent(
        event_type=EventType.HIGH_RISK_REQUEST,
        org_id=org_id,
        user_id=user_id,
        data={"risk_score": risk_score, "reason": reason, **kwargs},
        severity="critical",
    ))


async def emit_auth_failure(
    org_id: str, email: str, reason: str, **kwargs
) -> None:
    await event_bus.emit(VeilChatEvent(
        event_type=EventType.AUTH_FAILURE,
        org_id=org_id,
        data={"email": email, "reason": reason, **kwargs},
        severity="warning",
    ))


async def emit_provider_error(
    org_id: str, user_id: str, provider: str, model: str, error: str, **kwargs
) -> None:
    await event_bus.emit(VeilChatEvent(
        event_type=EventType.PROVIDER_ERROR,
        org_id=org_id,
        user_id=user_id,
        data={"provider": provider, "model": model, "error": error, **kwargs},
        severity="critical",
    ))


async def emit_usage_threshold(
    org_id: str, resource: str, current: int, limit: int, **kwargs
) -> None:
    await event_bus.emit(VeilChatEvent(
        event_type=EventType.USAGE_THRESHOLD,
        org_id=org_id,
        data={"resource": resource, "current": current, "limit": limit, **kwargs},
        severity="warning",
    ))
