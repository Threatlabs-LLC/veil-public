"""API Gateway mode — transparent OpenAI-compatible proxy with sanitization.

Users change one line of code:
    client = OpenAI(base_url="https://your-veilchat.com/v1")

All existing code works unchanged. Sanitization happens transparently.
Responses are rehydrated before returning to the client.

This is the highest-leverage SaaS feature — zero-friction adoption.
"""

import json
import time
import uuid

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user
from backend.config import settings
from backend.core.audit import log_audit_event
from backend.core.events import emit_entity_detected, emit_policy_violation, emit_high_risk_request
from backend.licensing.tiers import FEATURE_MULTI_PROVIDER, tier_has_feature
from backend.core.mapper import EntityMapper
from backend.core.policy_engine import evaluate_policies
from backend.core.rehydrator import Rehydrator
from backend.core.sanitizer import Sanitizer
from backend.core.usage import UsageTracker, record_usage
from backend.db.session import get_db, async_session as async_session_factory
from backend.detectors.registry import create_default_registry
from backend.models.entity import MappingSession
from backend.models.rule import DetectionRule
from backend.models.user import User

router = APIRouter()


@router.post("/v1/chat/completions")
async def gateway_chat_completions(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """OpenAI-compatible chat completions endpoint with transparent sanitization.

    Accepts the exact same request format as OpenAI's API.
    Sanitizes all message content, forwards to the real provider,
    rehydrates the response, and returns it in OpenAI format.
    """
    body = await request.json()

    model = body.get("model", "gpt-4o-mini")
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    temperature = body.get("temperature", 0.7)
    max_tokens = body.get("max_tokens", 4096)

    if not messages:
        raise HTTPException(400, {"error": {"message": "messages is required"}})

    # Determine provider from model name
    provider_name = _infer_provider(model)

    # Check multi-provider access
    from backend.models.organization import Organization
    org = await db.get(Organization, user.organization_id)
    org_tier = org.tier if org else "free"
    default_provider = settings.default_provider
    if org and org.settings:
        import json as _json
        try:
            org_settings = _json.loads(org.settings) if isinstance(org.settings, str) else org.settings
            default_provider = org_settings.get("default_provider", default_provider)
        except (ValueError, TypeError):
            pass
    if provider_name != default_provider and not tier_has_feature(org_tier, FEATURE_MULTI_PROVIDER):
        raise HTTPException(403, {
            "error": {
                "message": f"Multi-provider access requires the Team plan or higher. Your default provider is '{default_provider}'.",
                "type": "feature_not_available",
                "code": "multi_provider_required",
            }
        })

    # Load custom rules for this org
    rules_result = await db.execute(
        select(DetectionRule).where(
            DetectionRule.organization_id == user.organization_id,
            DetectionRule.is_active == True,
        )
    )
    custom_rules = rules_result.scalars().all()

    # Create a transient mapping session for this request
    session_id = str(uuid.uuid4())
    mapper = EntityMapper(session_id=session_id)
    registry = create_default_registry(custom_rules=custom_rules)
    sanitizer = Sanitizer(registry=registry, mapper=mapper)
    rehydrator = Rehydrator(mapper=mapper)

    # Usage tracking
    tracker = UsageTracker(
        org_id=user.organization_id,
        user_id=user.id,
        provider=provider_name,
        model=model,
    )
    tracker.start()

    # Sanitize all message content
    sanitized_messages = []
    total_entities = 0
    all_detected = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and content:
            result = sanitizer.sanitize(content)
            sanitized_messages.append({
                **msg,
                "content": result.sanitized_text,
            })
            total_entities += result.entity_count
            for e in result.entities:
                from backend.detectors.base import DetectedEntity
                all_detected.append(DetectedEntity(
                    entity_type=e.entity_type, value=e.original_value,
                    start=e.start, end=e.end, confidence=e.confidence,
                    detection_method=e.detection_method,
                ))
        else:
            sanitized_messages.append(msg)

    tracker.record_entities(total_entities, total_entities)

    # Emit entity detection events
    if all_detected:
        entity_types: dict[str, int] = {}
        for e in all_detected:
            entity_types[e.entity_type] = entity_types.get(e.entity_type, 0) + 1
        for etype, ecount in entity_types.items():
            await emit_entity_detected(user.organization_id, user.id, etype, ecount)

        if len(all_detected) >= 5:
            await emit_high_risk_request(
                user.organization_id, user.id,
                risk_score=min(1.0, len(all_detected) / 10),
                reason=f"{len(all_detected)} PII entities in gateway request",
            )

    # Evaluate policies
    if all_detected:
        policy_eval = await evaluate_policies(all_detected, user.organization_id, db)
        if policy_eval.blocked:
            await emit_policy_violation(
                user.organization_id, user.id,
                entity_type=policy_eval.block_reason or "unknown",
                action="block",
            )
            await log_audit_event(
                db, user.organization_id, "policy.blocked",
                user_id=user.id,
                error_message=policy_eval.block_reason,
                provider=provider_name,
                model_requested=model,
            )
            await db.commit()
            raise HTTPException(403, {
                "error": {"message": f"Blocked by policy: {policy_eval.block_reason}",
                          "type": "policy_violation", "code": "content_blocked"},
            })

    # Get the real provider (resolves keys from org settings or env)
    from backend.core.provider_keys import get_provider_key
    from backend.providers.base import ChatMessage
    from backend.providers.openai_compat import OpenAICompatProvider
    from backend.providers.anthropic import AnthropicProvider

    api_key, base_url = await get_provider_key(provider_name, user.organization_id, db)

    if provider_name == "anthropic":
        if not api_key:
            raise HTTPException(400, {"error": {"message": "Anthropic API key not configured. Set it in Settings."}})
        provider = AnthropicProvider(api_key=api_key, base_url=base_url)
    elif provider_name == "ollama":
        # Ollama doesn't require a real API key
        provider = OpenAICompatProvider(api_key=api_key or "ollama", base_url=base_url)
    else:
        if not api_key:
            raise HTTPException(400, {"error": {"message": "OpenAI API key not configured. Set it in Settings."}})
        provider = OpenAICompatProvider(api_key=api_key, base_url=base_url)

    llm_messages = [ChatMessage(role=m["role"], content=m["content"]) for m in sanitized_messages]

    # Inject structured system prompt with active placeholder table
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

    has_system = any(m["role"] == "system" for m in sanitized_messages)
    if has_system:
        # Append to existing system message
        for i, msg in enumerate(llm_messages):
            if msg.role == "system":
                llm_messages[i] = ChatMessage(
                    role="system",
                    content=f"{msg.content}\n\n{sanitization_system}",
                )
                break
    else:
        llm_messages.insert(0, ChatMessage(role="system", content=sanitization_system))

    if stream:
        return await _stream_response(
            provider, llm_messages, model, temperature, max_tokens,
            rehydrator, tracker, user, db,
        )
    else:
        return await _blocking_response(
            provider, llm_messages, model, temperature, max_tokens,
            rehydrator, tracker, user, db,
        )


async def _stream_response(provider, messages, model, temperature, max_tokens,
                           rehydrator, tracker, user, db):
    """Stream response in OpenAI SSE format with rehydration."""
    response_id = f"chatcmpl-{uuid.uuid4().hex[:29]}"

    async def generate():
        full_response = ""
        buffer = ""

        try:
            async for chunk in provider.chat_stream(
                messages=messages, model=model,
                temperature=temperature, max_tokens=max_tokens,
            ):
                if chunk.content:
                    buffer += chunk.content
                    full_response += chunk.content

                    rehydrated_safe, buffer = rehydrator.rehydrate_streaming(buffer)
                    if rehydrated_safe:
                        sse_chunk = _format_sse_chunk(
                            response_id, model, rehydrated_safe, None
                        )
                        yield f"data: {json.dumps(sse_chunk)}\n\n"

                if chunk.finish_reason:
                    if buffer:
                        rehydrated = rehydrator.rehydrate(buffer)
                        sse_chunk = _format_sse_chunk(
                            response_id, model, rehydrated, None
                        )
                        yield f"data: {json.dumps(sse_chunk)}\n\n"

                    # Final chunk with finish_reason
                    final_chunk = _format_sse_chunk(
                        response_id, model, "", chunk.finish_reason
                    )
                    yield f"data: {json.dumps(final_chunk)}\n\n"

        except Exception as e:
            tracker.record_error()
            error_chunk = {"error": {"message": str(e)}}
            yield f"data: {json.dumps(error_chunk)}\n\n"

        yield "data: [DONE]\n\n"

        # Record usage in background
        tracker.finish()
        tracker.record_tokens(0, len(full_response) // 4)  # Approximate token count
        try:
            async with async_session_factory() as save_db:
                await record_usage(save_db, tracker.metrics)
                await save_db.commit()
        except Exception:
            pass  # Don't fail the request over usage tracking

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-VeilChat-Entities-Detected": str(tracker.metrics.entities_detected),
        },
    )


async def _blocking_response(provider, messages, model, temperature, max_tokens,
                             rehydrator, tracker, user, db):
    """Non-streaming response in OpenAI format with rehydration."""
    full_response = ""
    model_used = model

    try:
        async for chunk in provider.chat_stream(
            messages=messages, model=model,
            temperature=temperature, max_tokens=max_tokens,
        ):
            if chunk.content:
                full_response += chunk.content
            if chunk.model:
                model_used = chunk.model
    except Exception as e:
        tracker.record_error()
        tracker.finish()
        raise HTTPException(502, {"error": {"message": f"Provider error: {str(e)}"}})

    # Rehydrate full response
    rehydrated = rehydrator.rehydrate(full_response)

    tracker.finish()
    output_tokens = len(full_response) // 4  # Approximate
    input_tokens = sum(len(m.content) // 4 for m in messages)
    tracker.record_tokens(input_tokens, output_tokens)

    # Record usage
    try:
        await record_usage(db, tracker.metrics)
    except Exception:
        pass

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:29]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_used,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": rehydrated,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
        "x_veilchat": {
            "entities_detected": tracker.metrics.entities_detected,
            "cost_usd": tracker.cost_display,
        },
    }


def _format_sse_chunk(response_id: str, model: str, content: str,
                      finish_reason: str | None) -> dict:
    """Format a single SSE chunk in OpenAI's format."""
    return {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": content} if content else {},
                "finish_reason": finish_reason,
            }
        ],
    }


def _infer_provider(model: str) -> str:
    """Infer the provider from model name."""
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith(("llama", "mistral", "codellama", "mixtral")):
        return "ollama"
    return "openai"
