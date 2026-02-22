"""Chat API endpoint — the main flow.

POST /api/chat — send a message through the sanitization pipeline,
stream the LLM response via SSE, and rehydrate placeholders.
"""

import json
import logging
import time
import uuid
from typing import AsyncIterator

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user
from backend.config import settings
from backend.core.audit import log_audit_event
from backend.licensing.tiers import FEATURE_MULTI_PROVIDER, tier_has_feature
from backend.core.mapper import EntityMapper
from backend.core.policy_engine import evaluate_policies
from backend.core.rehydrator import Rehydrator
from backend.core.sanitizer import Sanitizer
from backend.core.events import emit_entity_detected, emit_policy_violation, emit_high_risk_request, emit_provider_error
from backend.core.usage import RequestMetrics, record_usage
from backend.db.session import get_db, async_session as async_session_factory
from backend.detectors.registry import create_default_registry
from backend.models.conversation import Conversation, Message
from backend.models.entity import Entity, MappingSession
from backend.models.rule import DetectionRule
from backend.models.user import User
from backend.providers.base import ChatMessage
from backend.providers.openai_compat import OpenAICompatProvider
from backend.providers.anthropic import AnthropicProvider

router = APIRouter()


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt: str | None = None



async def _get_provider(provider_name: str, org_id: str, db):
    """Get the appropriate LLM provider, resolving keys from org settings or env."""
    from backend.core.provider_keys import get_provider_key

    api_key, base_url = await get_provider_key(provider_name, org_id, db)

    if provider_name == "anthropic":
        if not api_key:
            raise HTTPException(400, "Anthropic API key not configured. Set it in Settings.")
        return AnthropicProvider(api_key=api_key, base_url=base_url)
    elif provider_name == "ollama":
        # Ollama doesn't require a real API key
        return OpenAICompatProvider(api_key=api_key or "ollama", base_url=base_url)
    else:
        if not api_key:
            raise HTTPException(400, "OpenAI API key not configured. Set it in Settings.")
        return OpenAICompatProvider(api_key=api_key, base_url=base_url)


async def _get_or_create_conversation(
    db: AsyncSession,
    org_id: str,
    user_id: str,
    conversation_id: str | None,
    provider: str,
    model: str,
    system_prompt: str | None,
) -> tuple[Conversation, EntityMapper]:
    """Get existing conversation or create a new one, along with its mapper."""
    if conversation_id:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.organization_id == org_id,
            )
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise HTTPException(404, "Conversation not found")

        # Load existing mapping session
        result = await db.execute(
            select(MappingSession).where(
                MappingSession.conversation_id == conversation_id
            )
        )
        mapping_session = result.scalar_one_or_none()

        if mapping_session:
            # Load existing entities to rebuild mapper state
            result = await db.execute(
                select(Entity).where(Entity.session_id == mapping_session.id)
            )
            from backend.core.crypto import decrypt as _crypto_decrypt
            existing_entities = [
                {
                    "entity_type": e.entity_type,
                    "original_value": _crypto_decrypt(e.original_value),
                    "placeholder": e.placeholder,
                }
                for e in result.scalars().all()
            ]
            mapper = EntityMapper.from_db_state(
                session_id=mapping_session.id,
                counter_json=mapping_session.entity_counter,
                existing_entities=existing_entities,
            )
        else:
            mapping_session = MappingSession(
                organization_id=org_id,
                user_id=user_id,
                conversation_id=conv.id,
            )
            db.add(mapping_session)
            await db.flush()
            mapper = EntityMapper(session_id=mapping_session.id)

        return conv, mapper

    # Create new conversation
    conv = Conversation(
        organization_id=org_id,
        user_id=user_id,
        provider=provider,
        model=model,
        system_prompt=system_prompt,
    )
    db.add(conv)
    await db.flush()

    mapping_session = MappingSession(
        organization_id=org_id,
        user_id=user_id,
        conversation_id=conv.id,
    )
    db.add(mapping_session)
    await db.flush()

    mapper = EntityMapper(session_id=mapping_session.id)
    return conv, mapper


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message through sanitization and stream the LLM response."""
    org_id, user_id = user.organization_id, user.id

    # Check multi-provider access
    from backend.models.organization import Organization
    org = await db.get(Organization, org_id)
    org_tier = org.tier if org else "free"
    default_provider = settings.default_provider
    if org and org.settings:
        import json as _json
        try:
            org_settings = _json.loads(org.settings) if isinstance(org.settings, str) else org.settings
            default_provider = org_settings.get("default_provider", default_provider)
        except (ValueError, TypeError):
            pass
    if request.provider != default_provider and not tier_has_feature(org_tier, FEATURE_MULTI_PROVIDER):
        raise HTTPException(
            403,
            {
                "error": "feature_not_available",
                "message": f"Multi-provider access requires the Team plan or higher. Your default provider is '{default_provider}'.",
                "current_tier": org_tier,
                "feature": "multi_provider",
            },
        )

    # Get or create conversation + mapper
    conv, mapper = await _get_or_create_conversation(
        db, org_id, user_id,
        request.conversation_id, request.provider, request.model,
        request.system_prompt,
    )

    # Load custom rules for this org
    rules_result = await db.execute(
        select(DetectionRule).where(
            DetectionRule.organization_id == org_id,
            DetectionRule.is_active == True,
        )
    )
    custom_rules = rules_result.scalars().all()

    # Create sanitizer with custom rules
    registry = create_default_registry(custom_rules=custom_rules, org_tier=org_tier)
    sanitizer = Sanitizer(registry=registry, mapper=mapper)

    # Sanitize the user message
    result = sanitizer.sanitize(request.message)

    # Evaluate policies
    if result.entities:
        from backend.detectors.base import DetectedEntity
        detected = [
            DetectedEntity(
                entity_type=e.entity_type,
                value=e.original_value,
                start=e.start,
                end=e.end,
                confidence=e.confidence,
                detection_method=e.detection_method,
            )
            for e in result.entities
        ]
        # Emit entity detection events
        entity_types = {}
        for e in detected:
            entity_types[e.entity_type] = entity_types.get(e.entity_type, 0) + 1
        for etype, ecount in entity_types.items():
            await emit_entity_detected(org_id, user_id, etype, ecount)

        # High risk: 5+ entities in one message
        if len(detected) >= 5:
            await emit_high_risk_request(
                org_id, user_id,
                risk_score=min(1.0, len(detected) / 10),
                reason=f"{len(detected)} PII entities in single message",
            )

        policy_eval = await evaluate_policies(detected, org_id, db)

        if policy_eval.blocked:
            await emit_policy_violation(
                org_id, user_id,
                entity_type=policy_eval.block_reason or "unknown",
                action="block",
            )
            await log_audit_event(
                db, org_id, "policy.blocked",
                user_id=user_id,
                error_message=policy_eval.block_reason,
            )
            await db.commit()
            raise HTTPException(
                403,
                {
                    "error": "blocked_by_policy",
                    "message": policy_eval.block_reason,
                    "entities_detected": result.entity_count,
                },
            )

    # Save user message (encrypt original content at rest)
    from backend.core.crypto import encrypt as _encrypt
    seq_num = conv.total_messages + 1
    user_msg = Message(
        conversation_id=conv.id,
        organization_id=org_id,
        sequence_number=seq_num,
        role="user",
        original_content=_encrypt(request.message),
        sanitized_content=result.sanitized_text,
        entities_detected=result.entity_count,
    )
    db.add(user_msg)

    # Audit log: message sanitized
    await log_audit_event(
        db, org_id, "message.sanitized",
        user_id=user_id,
        conversation_id=conv.id,
        entities_snapshot=[
            {"type": e.entity_type, "placeholder": e.placeholder, "confidence": e.confidence}
            for e in result.entities
        ],
        provider=request.provider,
        model_requested=request.model,
    )
    conv.total_messages = seq_num

    # Save new entities to DB (encrypt PII at rest)
    for ent in result.entities:
        entity_record = Entity(
            session_id=mapper.session_id,
            entity_type=ent.entity_type,
            entity_subtype=ent.entity_subtype,
            original_value=_encrypt(ent.original_value),
            normalized_value=ent.normalized_value,
            placeholder=ent.placeholder,
            confidence=ent.confidence,
            detection_method=ent.detection_method,
        )
        # Use merge behavior — skip if already exists
        existing = await db.execute(
            select(Entity).where(
                Entity.session_id == mapper.session_id,
                Entity.entity_type == ent.entity_type,
                Entity.normalized_value == ent.normalized_value,
            )
        )
        if not existing.scalar_one_or_none():
            db.add(entity_record)

    # Update mapping session counter
    result_ms = await db.execute(
        select(MappingSession).where(MappingSession.conversation_id == conv.id)
    )
    ms = result_ms.scalar_one()
    ms.entity_counter = mapper.get_counter_state_json()

    await db.commit()

    # Build conversation history for LLM
    messages_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.sequence_number)
    )
    history = messages_result.scalars().all()

    llm_messages: list[ChatMessage] = []

    # Build structured system prompt with active placeholder table
    active_placeholders = mapper.get_all_placeholders()
    placeholder_section = ""
    if active_placeholders:
        rows = "\n".join(
            f"  - {ph} (type: {ph.rsplit('_', 1)[0]})"
            for ph in sorted(active_placeholders.keys())
        )
        placeholder_section = (
            "\n\n## Active Placeholders\n"
            "The following placeholders appear in this conversation:\n"
            f"{rows}\n\n"
            "IMPORTANT: When referring to any of these in your response, "
            "you MUST use the exact placeholder string (e.g. PERSON_001, "
            "EMAIL_001). Never invent new placeholders, never omit the "
            "number suffix, and never paraphrase them."
        )

    sanitization_system = (
        "This conversation is routed through a data-loss-prevention proxy. "
        "Sensitive values (names, emails, IPs, etc.) have been replaced with "
        "typed placeholders like PERSON_001 or EMAIL_001. "
        "Treat every placeholder as if it were the real value — "
        "answer the user's question normally. "
        "Do NOT refuse, apologize, or comment on the placeholders."
        f"{placeholder_section}"
    )

    if request.system_prompt:
        system_content = f"{request.system_prompt}\n\n{sanitization_system}"
    else:
        system_content = sanitization_system
    llm_messages.append(ChatMessage(role="system", content=system_content))

    for msg in history:
        if msg.role == "user":
            llm_messages.append(ChatMessage(role="user", content=msg.sanitized_content))
        elif msg.role == "assistant":
            # Use sanitized content for context (what LLM originally produced)
            llm_messages.append(ChatMessage(role="assistant", content=msg.sanitized_content))

    # Get LLM provider
    provider = await _get_provider(request.provider, org_id, db)

    # Create rehydrator
    rehydrator = Rehydrator(mapper=mapper)

    # Capture values needed by the generator before releasing the session
    conv_id = conv.id
    user_message = request.message
    req_provider = request.provider
    req_model = request.model
    req_temperature = request.temperature
    req_max_tokens = request.max_tokens
    entity_count = result.entity_count
    sanitization_dict = result.to_dict(include_originals=False)

    # Release DB session before streaming to free the connection pool slot
    await db.close()

    # Stream response
    async def generate_sse() -> AsyncIterator[str]:
        # First event: sanitization results (omit originals from SSE to reduce PII exposure)
        yield f"event: sanitization\ndata: {json.dumps(sanitization_dict)}\n\n"

        full_response = ""
        model_used = req_model
        start_time = time.time()
        buffer = ""

        try:
            async for chunk in provider.chat_stream(
                messages=llm_messages,
                model=req_model,
                temperature=req_temperature,
                max_tokens=req_max_tokens,
            ):
                if chunk.model:
                    model_used = chunk.model

                if chunk.content:
                    buffer += chunk.content
                    full_response += chunk.content

                    # Try to rehydrate and emit safe portion
                    rehydrated_safe, buffer = rehydrator.rehydrate_streaming(buffer)
                    if rehydrated_safe:
                        yield f"event: token\ndata: {json.dumps({'content': rehydrated_safe})}\n\n"

                if chunk.finish_reason:
                    # Flush remaining buffer
                    if buffer:
                        rehydrated = rehydrator.rehydrate(buffer)
                        yield f"event: token\ndata: {json.dumps({'content': rehydrated})}\n\n"
                        buffer = ""

        except Exception as e:
            await emit_provider_error(
                org_id, user_id,
                req_provider, req_model, str(e),
            )
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
            return

        latency_ms = int((time.time() - start_time) * 1000)

        # Rehydrate full response for storage
        rehydrated_full = rehydrator.rehydrate(full_response)

        # Save assistant message
        async with async_session_factory() as save_db:
            assistant_msg = Message(
                conversation_id=conv_id,
                organization_id=org_id,
                sequence_number=seq_num + 1,
                role="assistant",
                sanitized_content=full_response,
                desanitized_content=rehydrated_full,
                model_used=model_used,
                provider_latency_ms=latency_ms,
            )
            save_db.add(assistant_msg)

            # Audit log: LLM response received
            await log_audit_event(
                save_db, org_id, "llm.response",
                user_id=user_id,
                conversation_id=conv_id,
                provider=req_provider,
                model_requested=req_model,
                model_used=model_used,
                latency_ms=latency_ms,
            )

            # Update conversation
            update_conv = await save_db.get(Conversation, conv_id)
            if update_conv:
                update_conv.total_messages = seq_num + 1
                if not update_conv.title and len(user_message) > 0:
                    update_conv.title = user_message[:100]

            # Record usage metrics
            input_tokens = sum(len(m.content) // 4 for m in llm_messages)
            output_tokens = len(full_response) // 4
            try:
                await record_usage(save_db, RequestMetrics(
                    org_id=org_id,
                    user_id=user_id,
                    provider=req_provider,
                    model=req_model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    entities_detected=entity_count,
                    entities_sanitized=entity_count,
                    latency_ms=latency_ms,
                ))
            except Exception as exc:
                logger.error("Usage recording failed: %s", exc)

            await save_db.commit()

        # Final event with metadata
        yield f"event: done\ndata: {json.dumps({'conversation_id': conv_id, 'message_id': str(uuid.uuid4()), 'model': model_used, 'latency_ms': latency_ms, 'entities_detected': entity_count})}\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Chat with document attachment
# ---------------------------------------------------------------------------


@router.post("/chat/with-document")
async def chat_with_document(
    message: str = Form(""),
    provider: str = Form("openai"),
    model: str = Form("gpt-4o-mini"),
    temperature: float = Form(0.7),
    max_tokens: int = Form(4096),
    system_prompt: str | None = Form(None),
    conversation_id: str | None = Form(None),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message with an attached document through sanitization and stream the LLM response.

    Multipart endpoint — accepts form fields + file upload.
    File text is extracted, prepended to the user message, then the combined text
    goes through the standard sanitize → LLM → rehydrate pipeline.
    """
    from backend.config import settings as app_settings
    from backend.core.document import extract_text, ExtractionError, SUPPORTED_EXTENSIONS
    from backend.models.document import Document

    if not app_settings.document_upload_enabled:
        raise HTTPException(403, "Document upload is disabled")

    if not file.filename:
        raise HTTPException(400, "Filename is required")

    # Read and extract document text
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(400, "Empty file")

    try:
        extracted = extract_text(data, file.filename)
    except ValueError as e:
        raise HTTPException(413, str(e))
    except ExtractionError as e:
        raise HTTPException(
            422,
            {"error": "extraction_failed", "message": str(e), "supported_types": sorted(SUPPORTED_EXTENSIONS)},
        )

    # Combine document text with user message
    combined_message = (
        f"[Attached document: {file.filename}]\n---\n{extracted.text}\n---\n\n{message}"
    )

    org_id, user_id = user.organization_id, user.id

    # Check multi-provider access
    from backend.models.organization import Organization
    org = await db.get(Organization, org_id)
    org_tier = org.tier if org else "free"
    default_provider = settings.default_provider
    if org and org.settings:
        import json as _json
        try:
            org_settings = _json.loads(org.settings) if isinstance(org.settings, str) else org.settings
            default_provider = org_settings.get("default_provider", default_provider)
        except (ValueError, TypeError):
            pass
    if provider != default_provider and not tier_has_feature(org_tier, FEATURE_MULTI_PROVIDER):
        raise HTTPException(
            403,
            {
                "error": "feature_not_available",
                "message": f"Multi-provider access requires the Team plan or higher. Your default provider is '{default_provider}'.",
                "current_tier": org_tier,
                "feature": "multi_provider",
            },
        )

    # Get or create conversation + mapper
    conv, mapper = await _get_or_create_conversation(
        db, org_id, user_id,
        conversation_id, provider, model,
        system_prompt,
    )

    # Load custom rules for this org
    rules_result = await db.execute(
        select(DetectionRule).where(
            DetectionRule.organization_id == org_id,
            DetectionRule.is_active == True,
        )
    )
    custom_rules = rules_result.scalars().all()

    # Create sanitizer with custom rules
    registry = create_default_registry(custom_rules=custom_rules, org_tier=org_tier)
    sanitizer = Sanitizer(registry=registry, mapper=mapper)

    # Sanitize the combined text
    result = sanitizer.sanitize(combined_message)

    # Evaluate policies
    if result.entities:
        from backend.detectors.base import DetectedEntity as _DetectedEntity
        detected = [
            _DetectedEntity(
                entity_type=e.entity_type,
                value=e.original_value,
                start=e.start,
                end=e.end,
                confidence=e.confidence,
                detection_method=e.detection_method,
            )
            for e in result.entities
        ]
        for e in detected:
            await emit_entity_detected(org_id, user_id, e.entity_type, 1)

        if len(detected) >= 5:
            await emit_high_risk_request(
                org_id, user_id,
                risk_score=min(1.0, len(detected) / 10),
                reason=f"{len(detected)} PII entities in document upload",
            )

        policy_eval = await evaluate_policies(detected, org_id, db)
        if policy_eval.blocked:
            await emit_policy_violation(
                org_id, user_id,
                entity_type=policy_eval.block_reason or "unknown",
                action="block",
            )
            raise HTTPException(
                403,
                {
                    "error": "blocked_by_policy",
                    "message": policy_eval.block_reason,
                    "entities_detected": result.entity_count,
                },
            )

    # Save document metadata
    doc_record = Document(
        organization_id=org_id,
        user_id=user_id,
        conversation_id=conv.id,
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

    # Save user message
    from backend.core.crypto import encrypt as _encrypt
    seq_num = conv.total_messages + 1
    user_msg = Message(
        conversation_id=conv.id,
        organization_id=org_id,
        sequence_number=seq_num,
        role="user",
        original_content=_encrypt(combined_message),
        sanitized_content=result.sanitized_text,
        entities_detected=result.entity_count,
    )
    db.add(user_msg)

    await log_audit_event(
        db, org_id, "message.sanitized",
        user_id=user_id,
        conversation_id=conv.id,
        entities_snapshot=[
            {"type": e.entity_type, "placeholder": e.placeholder, "confidence": e.confidence}
            for e in result.entities
        ],
        provider=provider,
        model_requested=model,
    )
    conv.total_messages = seq_num

    # Save new entities to DB
    for ent in result.entities:
        entity_record = Entity(
            session_id=mapper.session_id,
            entity_type=ent.entity_type,
            entity_subtype=ent.entity_subtype,
            original_value=_encrypt(ent.original_value),
            normalized_value=ent.normalized_value,
            placeholder=ent.placeholder,
            confidence=ent.confidence,
            detection_method=ent.detection_method,
        )
        existing = await db.execute(
            select(Entity).where(
                Entity.session_id == mapper.session_id,
                Entity.entity_type == ent.entity_type,
                Entity.normalized_value == ent.normalized_value,
            )
        )
        if not existing.scalar_one_or_none():
            db.add(entity_record)

    result_ms = await db.execute(
        select(MappingSession).where(MappingSession.conversation_id == conv.id)
    )
    ms = result_ms.scalar_one()
    ms.entity_counter = mapper.get_counter_state_json()

    await db.commit()

    # Build conversation history for LLM
    messages_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.sequence_number)
    )
    history = messages_result.scalars().all()

    llm_messages: list[ChatMessage] = []

    active_placeholders = mapper.get_all_placeholders()
    placeholder_section = ""
    if active_placeholders:
        rows = "\n".join(
            f"  - {ph} (type: {ph.rsplit('_', 1)[0]})"
            for ph in sorted(active_placeholders.keys())
        )
        placeholder_section = (
            "\n\n## Active Placeholders\n"
            "The following placeholders appear in this conversation:\n"
            f"{rows}\n\n"
            "IMPORTANT: When referring to any of these in your response, "
            "you MUST use the exact placeholder string (e.g. PERSON_001, "
            "EMAIL_001). Never invent new placeholders, never omit the "
            "number suffix, and never paraphrase them."
        )

    sanitization_system = (
        "This conversation is routed through a data-loss-prevention proxy. "
        "Sensitive values (names, emails, IPs, etc.) have been replaced with "
        "typed placeholders like PERSON_001 or EMAIL_001. "
        "Treat every placeholder as if it were the real value — "
        "answer the user's question normally. "
        "Do NOT refuse, apologize, or comment on the placeholders."
        f"{placeholder_section}"
    )

    if system_prompt:
        system_content = f"{system_prompt}\n\n{sanitization_system}"
    else:
        system_content = sanitization_system
    llm_messages.append(ChatMessage(role="system", content=system_content))

    for msg in history:
        if msg.role == "user":
            llm_messages.append(ChatMessage(role="user", content=msg.sanitized_content))
        elif msg.role == "assistant":
            llm_messages.append(ChatMessage(role="assistant", content=msg.sanitized_content))

    # Get LLM provider
    llm_provider = await _get_provider(provider, org_id, db)

    # Create rehydrator
    rehydrator = Rehydrator(mapper=mapper)

    # Capture values needed by the generator before releasing the session
    conv_id = conv.id
    entity_count = result.entity_count
    sanitization_dict = result.to_dict(include_originals=False)
    doc_meta = {
        'filename': extracted.filename, 'file_type': extracted.file_type,
        'char_count': extracted.char_count, 'page_count': extracted.page_count,
        'entities_detected': entity_count,
    }
    doc_filename = file.filename

    # Release DB session before streaming to free the connection pool slot
    await db.close()

    # Stream response
    async def generate_sse() -> AsyncIterator[str]:
        yield f"event: sanitization\ndata: {json.dumps(sanitization_dict)}\n\n"

        # Include document metadata in stream
        yield f"event: document\ndata: {json.dumps(doc_meta)}\n\n"

        full_response = ""
        model_used = model
        start_time = time.time()
        buffer = ""

        try:
            async for chunk in llm_provider.chat_stream(
                messages=llm_messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                if chunk.model:
                    model_used = chunk.model

                if chunk.content:
                    buffer += chunk.content
                    full_response += chunk.content

                    rehydrated_safe, buffer = rehydrator.rehydrate_streaming(buffer)
                    if rehydrated_safe:
                        yield f"event: token\ndata: {json.dumps({'content': rehydrated_safe})}\n\n"

                if chunk.finish_reason:
                    if buffer:
                        rehydrated = rehydrator.rehydrate(buffer)
                        yield f"event: token\ndata: {json.dumps({'content': rehydrated})}\n\n"
                        buffer = ""

        except Exception as e:
            await emit_provider_error(
                org_id, user_id,
                provider, model, str(e),
            )
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
            return

        latency_ms = int((time.time() - start_time) * 1000)
        rehydrated_full = rehydrator.rehydrate(full_response)

        async with async_session_factory() as save_db:
            assistant_msg = Message(
                conversation_id=conv_id,
                organization_id=org_id,
                sequence_number=seq_num + 1,
                role="assistant",
                sanitized_content=full_response,
                desanitized_content=rehydrated_full,
                model_used=model_used,
                provider_latency_ms=latency_ms,
            )
            save_db.add(assistant_msg)

            await log_audit_event(
                save_db, org_id, "llm.response",
                user_id=user_id,
                conversation_id=conv_id,
                provider=provider,
                model_requested=model,
                model_used=model_used,
                latency_ms=latency_ms,
            )

            update_conv = await save_db.get(Conversation, conv_id)
            if update_conv:
                update_conv.total_messages = seq_num + 1
                if not update_conv.title:
                    update_conv.title = f"Document: {doc_filename}"[:100]

            input_tokens = sum(len(m.content) // 4 for m in llm_messages)
            output_tokens = len(full_response) // 4
            try:
                await record_usage(save_db, RequestMetrics(
                    org_id=org_id,
                    user_id=user_id,
                    provider=provider,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    entities_detected=entity_count,
                    entities_sanitized=entity_count,
                    latency_ms=latency_ms,
                ))
            except Exception as exc:
                logger.error("Usage recording failed: %s", exc)

            await save_db.commit()

        yield f"event: done\ndata: {json.dumps({'conversation_id': conv_id, 'message_id': str(uuid.uuid4()), 'model': model_used, 'latency_ms': latency_ms, 'entities_detected': entity_count})}\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
