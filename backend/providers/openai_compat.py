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

        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

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
                    content = delta.get("content", "")
                    finish_reason = choice.get("finish_reason")
                    model_name = chunk.get("model", model)

                    if content or finish_reason:
                        yield StreamChunk(
                            content=content or "",
                            finish_reason=finish_reason,
                            model=model_name,
                        )
