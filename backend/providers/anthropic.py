"""Anthropic Claude provider adapter with native streaming support."""

import json
from collections.abc import AsyncIterator

import httpx

from backend.providers.base import BaseLLMProvider, ChatMessage, StreamChunk


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude chat provider with streaming via SSE."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        timeout: float = 120.0,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "anthropic"

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamChunk]:
        """Stream chat completion via Anthropic's Messages API."""
        url = f"{self._base_url}/v1/messages"

        # Extract system message if present
        system_content = None
        chat_messages = []
        for m in messages:
            if m.role == "system":
                system_content = m.content
            else:
                chat_messages.append({"role": m.role, "content": m.content})

        payload = {
            "model": model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if system_content:
            payload["system"] = system_content

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    data = line[6:]
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")

                    if event_type == "content_block_start":
                        # Check for image content blocks
                        content_block = event.get("content_block", {})
                        block_type = content_block.get("type", "")

                        if block_type == "image":
                            source = content_block.get("source", {})
                            media_type = source.get("media_type", "image/png")
                            data = source.get("data", "")
                            if data:
                                yield StreamChunk(
                                    content="",
                                    content_type="image_base64",
                                    image_data=f"data:{media_type};base64,{data}",
                                    model=model,
                                )

                    elif event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        delta_type = delta.get("type", "")

                        if delta_type == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                yield StreamChunk(
                                    content=text,
                                    content_type="text",
                                    model=model,
                                )
                        elif delta_type == "image_delta":
                            # Anthropic may stream image data in deltas
                            data = delta.get("data", "")
                            if data:
                                media_type = delta.get("media_type", "image/png")
                                yield StreamChunk(
                                    content="",
                                    content_type="image_base64",
                                    image_data=f"data:{media_type};base64,{data}",
                                    model=model,
                                )

                    elif event_type == "message_delta":
                        stop_reason = event.get("delta", {}).get("stop_reason")
                        if stop_reason:
                            yield StreamChunk(
                                content="", finish_reason=stop_reason, model=model
                            )

                    elif event_type == "message_stop":
                        return
