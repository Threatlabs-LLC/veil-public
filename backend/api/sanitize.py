"""Sanitize API — detection-only endpoint for testing and integration.

POST /api/sanitize      — sanitize a single text
POST /api/sanitize/batch — sanitize multiple texts in one request

No LLM call, no token cost. Returns sanitized text + detected entities.
Ideal for:
- Corpus testing and detection quality benchmarking
- CI/CD pipeline integration (scan for PII before commit/deploy)
- Third-party tool integration (Slack bots, email scanners, etc.)
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user
from backend.core.audit import log_audit_event
from backend.core.mapper import EntityMapper
from backend.core.sanitizer import Sanitizer
from backend.db.session import get_db
from backend.detectors.registry import create_default_registry
from backend.models.organization import Organization
from backend.models.rule import DetectionRule
from backend.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Schemas ---

class SanitizeRequest(BaseModel):
    text: str
    return_original: bool = False  # Include original values in response (admin only)


class SanitizeEntity(BaseModel):
    entity_type: str
    placeholder: str
    start: int
    end: int
    confidence: float
    detection_method: str
    original_value: str | None = None  # Only if return_original=True


class SanitizeResponse(BaseModel):
    sanitized_text: str
    entity_count: int
    entities: list[SanitizeEntity]
    processing_ms: int


class BatchSanitizeRequest(BaseModel):
    texts: list[str]
    return_original: bool = False


class BatchSanitizeResponse(BaseModel):
    results: list[SanitizeResponse]
    total_entities: int
    processing_ms: int


# --- Endpoints ---

@router.post("/sanitize", response_model=SanitizeResponse)
async def sanitize_text(
    request: SanitizeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sanitize text and return detected entities. No LLM call."""
    start_time = time.time()

    # Load custom rules for this org
    rules_result = await db.execute(
        select(DetectionRule).where(
            DetectionRule.organization_id == user.organization_id,
            DetectionRule.is_active == True,
        )
    )
    custom_rules = rules_result.scalars().all()

    # Determine org tier for feature-gated detectors
    org = await db.get(Organization, user.organization_id)
    org_tier = org.tier if org else "free"

    # Create sanitizer
    registry = create_default_registry(custom_rules=custom_rules, org_tier=org_tier)
    mapper = EntityMapper(session_id=str(uuid.uuid4()))
    sanitizer = Sanitizer(registry=registry, mapper=mapper)

    # Sanitize
    result = sanitizer.sanitize(request.text)

    # Build entity list
    include_original = request.return_original and user.role in ("owner", "admin")
    entities = [
        SanitizeEntity(
            entity_type=e.entity_type,
            placeholder=e.placeholder,
            start=e.start,
            end=e.end,
            confidence=e.confidence,
            detection_method=e.detection_method,
            original_value=e.original_value if include_original else None,
        )
        for e in result.entities
    ]

    processing_ms = int((time.time() - start_time) * 1000)

    # Audit log
    await log_audit_event(
        db, user.organization_id, "sanitize.api",
        user_id=user.id,
        entities_snapshot=[
            {"type": e.entity_type, "placeholder": e.placeholder, "confidence": e.confidence}
            for e in result.entities
        ],
    )
    await db.commit()

    return SanitizeResponse(
        sanitized_text=result.sanitized_text,
        entity_count=result.entity_count,
        entities=entities,
        processing_ms=processing_ms,
    )


@router.post("/sanitize/batch", response_model=BatchSanitizeResponse)
async def sanitize_batch(
    request: BatchSanitizeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sanitize multiple texts in one request. Shared entity mapping across texts."""
    start_time = time.time()

    # Load custom rules for this org
    rules_result = await db.execute(
        select(DetectionRule).where(
            DetectionRule.organization_id == user.organization_id,
            DetectionRule.is_active == True,
        )
    )
    custom_rules = rules_result.scalars().all()

    # Determine org tier for feature-gated detectors
    org = await db.get(Organization, user.organization_id)
    org_tier = org.tier if org else "free"

    # Shared mapper across all texts (consistent placeholders)
    registry = create_default_registry(custom_rules=custom_rules, org_tier=org_tier)
    mapper = EntityMapper(session_id=str(uuid.uuid4()))
    sanitizer = Sanitizer(registry=registry, mapper=mapper)

    include_original = request.return_original and user.role in ("owner", "admin")
    results: list[SanitizeResponse] = []
    total_entities = 0

    for text in request.texts:
        text_start = time.time()
        result = sanitizer.sanitize(text)
        text_ms = int((time.time() - text_start) * 1000)

        entities = [
            SanitizeEntity(
                entity_type=e.entity_type,
                placeholder=e.placeholder,
                start=e.start,
                end=e.end,
                confidence=e.confidence,
                detection_method=e.detection_method,
                original_value=e.original_value if include_original else None,
            )
            for e in result.entities
        ]
        total_entities += result.entity_count
        results.append(SanitizeResponse(
            sanitized_text=result.sanitized_text,
            entity_count=result.entity_count,
            entities=entities,
            processing_ms=text_ms,
        ))

    processing_ms = int((time.time() - start_time) * 1000)

    # Audit log
    await log_audit_event(
        db, user.organization_id, "sanitize.batch",
        user_id=user.id,
        entities_snapshot={"texts": len(request.texts), "total_entities": total_entities},
    )
    await db.commit()

    return BatchSanitizeResponse(
        results=results,
        total_entities=total_entities,
        processing_ms=processing_ms,
    )
