"""Document scan API — upload a file, extract text, detect PII.

POST /api/documents/scan — standalone scan (no LLM, no chat).
Returns sanitized text and entity list.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user
from backend.config import settings
from backend.core.document import (
    ExtractionError,
    extract_text,
    SUPPORTED_EXTENSIONS,
)
from backend.core.mapper import EntityMapper
from backend.core.sanitizer import Sanitizer
from backend.db.session import get_db
from backend.detectors.registry import create_default_registry
from backend.models.document import Document
from backend.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/documents/scan")
async def scan_document(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document, extract text, and scan for PII.

    Returns sanitized text and a list of detected entities.
    No LLM call — pure detection only.
    """
    if not settings.document_upload_enabled:
        raise HTTPException(403, "Document upload is disabled")

    if not file.filename:
        raise HTTPException(400, "Filename is required")

    # Read file data
    data = await file.read()

    if len(data) == 0:
        raise HTTPException(400, "Empty file")

    # Extract text
    try:
        extracted = extract_text(data, file.filename)
    except ValueError as e:
        raise HTTPException(413, str(e))
    except ExtractionError as e:
        raise HTTPException(
            422,
            {"error": "extraction_failed", "message": str(e), "supported_types": sorted(SUPPORTED_EXTENSIONS)},
        )

    # Sanitize the extracted text
    org_id = user.organization_id

    # Determine org tier for feature-gated detectors
    from backend.models.organization import Organization
    org = await db.get(Organization, org_id)
    org_tier = org.tier if org else "free"

    registry = create_default_registry(org_tier=org_tier)
    mapper = EntityMapper(session_id=f"doc-scan-{file.filename}")
    sanitizer = Sanitizer(registry=registry, mapper=mapper)
    result = sanitizer.sanitize(extracted.text)

    # Save document metadata (no content stored)
    doc_record = Document(
        organization_id=org_id,
        user_id=user.id,
        filename=file.filename,
        file_type=extracted.file_type,
        file_size_bytes=extracted.file_size_bytes,
        char_count=extracted.char_count,
        page_count=extracted.page_count,
        entities_detected=result.entity_count,
        was_truncated=extracted.was_truncated,
        status="completed",
    )
    db.add(doc_record)
    await db.commit()

    return {
        "document_id": doc_record.id,
        "filename": extracted.filename,
        "file_type": extracted.file_type,
        "file_size_bytes": extracted.file_size_bytes,
        "char_count": extracted.char_count,
        "page_count": extracted.page_count,
        "was_truncated": extracted.was_truncated,
        "sanitized_text": result.sanitized_text,
        "entity_count": result.entity_count,
        "entities": [
            {
                "entity_type": e.entity_type,
                "placeholder": e.placeholder,
                "original": e.original_value,
                "confidence": e.confidence,
                "start": e.start,
                "end": e.end,
                "detection_method": e.detection_method,
            }
            for e in result.entities
        ],
    }
