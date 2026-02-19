"""Audit logging helper — records events to the audit_logs table."""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.audit import AuditLog

logger = logging.getLogger(__name__)


async def log_audit_event(
    db: AsyncSession,
    org_id: str,
    event_type: str,
    *,
    user_id: str | None = None,
    conversation_id: str | None = None,
    message_id: str | None = None,
    content_before: str | None = None,
    content_after: str | None = None,
    entities_snapshot: list[dict] | None = None,
    provider: str | None = None,
    model_requested: str | None = None,
    model_used: str | None = None,
    http_status: int | None = None,
    latency_ms: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Write an audit log entry. Never raises — errors are logged and swallowed."""
    try:
        entry = AuditLog(
            organization_id=org_id,
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            request_id=str(uuid.uuid4()),
            event_type=event_type,
            content_before=content_before,
            content_after=content_after,
            entities_snapshot=json.dumps(entities_snapshot) if entities_snapshot else None,
            provider=provider,
            model_requested=model_requested,
            model_used=model_used,
            http_status=http_status,
            latency_ms=latency_ms,
            error_code=error_code,
            error_message=error_message,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        db.add(entry)
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")
