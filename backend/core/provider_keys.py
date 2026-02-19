"""Provider key resolution — checks org settings first, falls back to env vars."""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.organization import Organization


async def get_provider_key(
    provider: str, org_id: str, db: AsyncSession
) -> tuple[str, str]:
    """Get API key and base URL for a provider.

    Checks org settings first, falls back to global env vars.
    Returns (api_key, base_url).
    """
    # Try org-level keys first
    org = await db.get(Organization, org_id)
    if org and org.settings:
        try:
            org_settings = json.loads(org.settings) if isinstance(org.settings, str) else {}
        except (json.JSONDecodeError, TypeError):
            org_settings = {}

        if provider == "openai":
            key = org_settings.get("openai_api_key", "")
            if key:
                return key, settings.openai_base_url
        elif provider == "anthropic":
            key = org_settings.get("anthropic_api_key", "")
            if key:
                return key, settings.anthropic_base_url
        elif provider == "ollama":
            base = org_settings.get("ollama_base_url", "") or settings.ollama_base_url
            return "ollama", base  # Ollama doesn't need a real API key

    # Fall back to global env vars
    if provider == "openai":
        return settings.openai_api_key, settings.openai_base_url
    elif provider == "anthropic":
        return settings.anthropic_api_key, settings.anthropic_base_url
    elif provider == "ollama":
        return "ollama", settings.ollama_base_url

    return "", ""
