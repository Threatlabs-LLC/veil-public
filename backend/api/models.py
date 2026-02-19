"""Models API — list available LLM models and providers."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user
from backend.db.session import get_db
from backend.models.user import User

router = APIRouter(prefix="/models", tags=["models"])

# Model registry — metadata for known models
MODEL_REGISTRY: dict[str, list[dict]] = {
    "openai": [
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "context_window": 128000, "cost_per_1k_input": 0.00015, "cost_per_1k_output": 0.0006},
        {"id": "gpt-4o", "name": "GPT-4o", "context_window": 128000, "cost_per_1k_input": 0.0025, "cost_per_1k_output": 0.01},
        {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "context_window": 128000, "cost_per_1k_input": 0.01, "cost_per_1k_output": 0.03},
        {"id": "o3-mini", "name": "o3-mini", "context_window": 128000, "cost_per_1k_input": 0.0011, "cost_per_1k_output": 0.0044},
    ],
    "anthropic": [
        {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6", "context_window": 200000, "cost_per_1k_input": 0.003, "cost_per_1k_output": 0.015},
        {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5", "context_window": 200000, "cost_per_1k_input": 0.0008, "cost_per_1k_output": 0.004},
        {"id": "claude-opus-4-6", "name": "Claude Opus 4.6", "context_window": 200000, "cost_per_1k_input": 0.015, "cost_per_1k_output": 0.075},
    ],
    "ollama": [
        {"id": "llama3.2", "name": "Llama 3.2", "context_window": 128000, "cost_per_1k_input": 0, "cost_per_1k_output": 0},
        {"id": "mistral", "name": "Mistral 7B", "context_window": 32000, "cost_per_1k_input": 0, "cost_per_1k_output": 0},
        {"id": "codellama", "name": "Code Llama", "context_window": 16000, "cost_per_1k_input": 0, "cost_per_1k_output": 0},
        {"id": "mixtral", "name": "Mixtral 8x7B", "context_window": 32000, "cost_per_1k_input": 0, "cost_per_1k_output": 0},
    ],
}


class ModelInfo(BaseModel):
    id: str
    name: str
    provider: str
    context_window: int
    cost_per_1k_input: float
    cost_per_1k_output: float


class ProviderInfo(BaseModel):
    id: str
    name: str
    is_configured: bool
    model_count: int


@router.get("")
async def list_models(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all available models grouped by provider, with cost metadata."""
    import json
    from backend.models.organization import Organization
    from backend.config import settings

    org = await db.get(Organization, user.organization_id)
    org_settings = {}
    if org and org.settings:
        try:
            org_settings = json.loads(org.settings) if isinstance(org.settings, str) else org.settings
        except (json.JSONDecodeError, TypeError):
            pass

    # Determine which providers are configured
    configured = {}
    configured["openai"] = bool(org_settings.get("openai_api_key") or settings.openai_api_key)
    configured["anthropic"] = bool(org_settings.get("anthropic_api_key") or settings.anthropic_api_key)

    # Check if Ollama is reachable (async to avoid blocking, with SSRF protection)
    ollama_url = org_settings.get("ollama_base_url") or settings.ollama_base_url
    try:
        import asyncio
        import urllib.request
        from backend.core.url_validator import is_safe_url

        safe, _ = is_safe_url(ollama_url)
        if not safe:
            configured["ollama"] = False
        else:
            def _probe_ollama() -> bool:
                try:
                    req = urllib.request.Request(
                        ollama_url.rstrip("/").replace("/v1", "") + "/api/tags",
                        method="GET",
                    )
                    with urllib.request.urlopen(req, timeout=1):
                        return True
                except Exception:
                    return False

            configured["ollama"] = await asyncio.to_thread(_probe_ollama)
    except Exception:
        configured["ollama"] = False

    providers = []
    all_models = []

    for provider_id, models in MODEL_REGISTRY.items():
        providers.append(ProviderInfo(
            id=provider_id,
            name={"openai": "OpenAI", "anthropic": "Anthropic", "ollama": "Ollama"}.get(provider_id, provider_id),
            is_configured=configured.get(provider_id, False),
            model_count=len(models),
        ))
        for m in models:
            all_models.append(ModelInfo(
                id=m["id"],
                name=m["name"],
                provider=provider_id,
                context_window=m["context_window"],
                cost_per_1k_input=m["cost_per_1k_input"],
                cost_per_1k_output=m["cost_per_1k_output"],
            ))

    return {
        "providers": providers,
        "models": all_models,
    }
