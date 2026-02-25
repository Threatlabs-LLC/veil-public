"""OpenAI-compatible LLM provider adapter.

Supports any API that follows the OpenAI chat completions format:
  - OpenAI
  - Ollama (with OpenAI compatibility mode)
  - Azure OpenAI
  - LiteLLM
  - Any OpenAI-compatible proxy
"""

import json
from collections.abc import AsyncIterator

import httpx

from backend.providers.base import BaseLLMProvider, ChatMessage, StreamChunk


# OpenAI reasoning models that reject temperature, top_p, and max_tokens
REASONING_MODELS = {"o1", "o1-mini", "o1-preview", "o3", "o3-mini", "o3-pro", "o4-mini"}


class OpenAICompatProvider(BaseLLMProvider):
    """OpenAI-compatible chat completions provider with streaming support."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 120.0,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "openai_compatible"

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamChunk]:
        """Stream chat completion via SSE."""
        url = f"{self._base_url}/chat/completions"

        is_reasoning = model in REASONING_MODELS

        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
        }

        if is_reasoning:
            # Reasoning models use max_completion_tokens, not max_tokens,
            # and do not accept temperature or top_p.
            payload["max_completion_tokens"] = max_tokens
        else:
            payload["temperature"] = temperature
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    data = line[6:]  # Strip "data: " prefix
                    if data == "[DONE]":
                        return

                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue

                    choice = choices[0]
                    delta = choice.get("delta", {})
                    finish_reason = choice.get("finish_reason")
                    model_name = chunk.get("model", model)

                    # Standard text content from Chat Completions API.
                    # Note: Image generation uses the Responses API provider
                    # (openai_responses.py), not this provider.
                    content = delta.get("content") or ""
                    if content or finish_reason:
                        yield StreamChunk(
                            content=content,
                            content_type="text",
                            finish_reason=finish_reason,
                            model=model_name,
                        )
