"""Conversations API — CRUD for conversation management."""

import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.session import get_db
from backend.models.conversation import Conversation, Message
from backend.models.entity import Entity, MappingSession

router = APIRouter()


class ConversationSummary(BaseModel):
    id: str
    title: str | None
    provider: str
    model: str
    total_messages: int
    created_at: str
    updated_at: str


class MessageOut(BaseModel):
    id: str
    role: str
    content: str  # display content (rehydrated for assistant, original for user)
    sanitized_content: str | None = None
    entities_detected: int = 0
    model_used: str | None = None
    created_at: str


class EntityOut(BaseModel):
    entity_type: str
    original_value: str
    placeholder: str
    confidence: float
    detection_method: str


@router.get("/conversations")
async def list_conversations(
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    sort: str = Query("updated_desc", pattern="^(updated_desc|updated_asc|created_desc|created_asc|messages_desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """List all conversations with optional search and filters."""
    query = select(Conversation).where(Conversation.status != "archived")

    # Full-text search on title and message content
    if q:
        search_term = f"%{q}%"
        # Search title or messages that contain the term
        msg_conv_ids = (
            select(Message.conversation_id)
            .where(
                or_(
                    Message.original_content.ilike(search_term),
                    Message.sanitized_content.ilike(search_term),
                )
            )
            .distinct()
        )
        query = query.where(
            or_(
                Conversation.title.ilike(search_term),
                Conversation.id.in_(msg_conv_ids),
            )
        )

    if provider:
        query = query.where(Conversation.provider == provider)
    if model:
        query = query.where(Conversation.model == model)

    # Sorting
    sort_map = {
        "updated_desc": Conversation.updated_at.desc(),
        "updated_asc": Conversation.updated_at.asc(),
        "created_desc": Conversation.created_at.desc(),
        "created_asc": Conversation.created_at.asc(),
        "messages_desc": Conversation.total_messages.desc(),
    }
    query = query.order_by(sort_map[sort])
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    conversations = result.scalars().all()

    return [
        ConversationSummary(
            id=c.id,
            title=c.title,
            provider=c.provider,
            model=c.model,
            total_messages=c.total_messages,
            created_at=str(c.created_at),
            updated_at=str(c.updated_at),
        )
        for c in conversations
    ]


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a conversation with all messages."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "Conversation not found")

    # Get messages
    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.sequence_number)
    )
    messages = msg_result.scalars().all()

    # Get entities for this conversation's mapping session
    session_result = await db.execute(
        select(MappingSession).where(MappingSession.conversation_id == conversation_id)
    )
    mapping_session = session_result.scalar_one_or_none()

    entities = []
    if mapping_session:
        ent_result = await db.execute(
            select(Entity).where(Entity.session_id == mapping_session.id)
        )
        entities = [
            EntityOut(
                entity_type=e.entity_type,
                original_value=e.original_value,
                placeholder=e.placeholder,
                confidence=e.confidence,
                detection_method=e.detection_method,
            )
            for e in ent_result.scalars().all()
        ]

    return {
        "id": conv.id,
        "title": conv.title,
        "provider": conv.provider,
        "model": conv.model,
        "status": conv.status,
        "total_messages": conv.total_messages,
        "created_at": str(conv.created_at),
        "messages": [
            MessageOut(
                id=m.id,
                role=m.role,
                content=(
                    m.desanitized_content or m.sanitized_content
                    if m.role == "assistant"
                    else m.original_content or m.sanitized_content
                ),
                sanitized_content=m.sanitized_content,
                entities_detected=m.entities_detected,
                model_used=m.model_used,
                created_at=str(m.created_at),
            )
            for m in messages
        ],
        "entities": entities,
    }


class ConversationUpdate(BaseModel):
    title: str | None = None


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    body: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update conversation metadata (e.g. rename)."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "Conversation not found")

    if body.title is not None:
        conv.title = body.title

    return {
        "id": conv.id,
        "title": conv.title,
        "provider": conv.provider,
        "model": conv.model,
        "status": conv.status,
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Archive a conversation (soft delete)."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "Conversation not found")

    conv.status = "archived"
    return {"status": "archived"}


@router.get("/conversations/{conversation_id}/export")
async def export_conversation(
    conversation_id: str,
    format: str = Query("json", pattern="^(json|csv)$"),
    db: AsyncSession = Depends(get_db),
):
    """Export a conversation as JSON or CSV."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "Conversation not found")

    # Get messages
    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.sequence_number)
    )
    messages = msg_result.scalars().all()

    # Get entities
    session_result = await db.execute(
        select(MappingSession).where(MappingSession.conversation_id == conversation_id)
    )
    mapping_session = session_result.scalar_one_or_none()

    entities = []
    if mapping_session:
        ent_result = await db.execute(
            select(Entity).where(Entity.session_id == mapping_session.id)
        )
        entities = ent_result.scalars().all()

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["sequence", "role", "content", "sanitized_content", "entities_detected", "model_used", "created_at"])
        for m in messages:
            content = (
                m.desanitized_content or m.sanitized_content
                if m.role == "assistant"
                else m.original_content or m.sanitized_content
            )
            writer.writerow([
                m.sequence_number, m.role, content,
                m.sanitized_content, m.entities_detected,
                m.model_used or "", str(m.created_at),
            ])

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="conversation-{conversation_id[:8]}.csv"'},
        )

    # JSON format
    export_data = {
        "conversation": {
            "id": conv.id,
            "title": conv.title,
            "provider": conv.provider,
            "model": conv.model,
            "status": conv.status,
            "total_messages": conv.total_messages,
            "created_at": str(conv.created_at),
        },
        "messages": [
            {
                "sequence": m.sequence_number,
                "role": m.role,
                "content": (
                    m.desanitized_content or m.sanitized_content
                    if m.role == "assistant"
                    else m.original_content or m.sanitized_content
                ),
                "sanitized_content": m.sanitized_content,
                "entities_detected": m.entities_detected,
                "model_used": m.model_used,
                "latency_ms": m.provider_latency_ms,
                "created_at": str(m.created_at),
            }
            for m in messages
        ],
        "entities": [
            {
                "entity_type": e.entity_type,
                "original_value": e.original_value,
                "placeholder": e.placeholder,
                "confidence": e.confidence,
                "detection_method": e.detection_method,
            }
            for e in entities
        ],
    }

    return StreamingResponse(
        iter([json.dumps(export_data, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="conversation-{conversation_id[:8]}.json"'},
    )
