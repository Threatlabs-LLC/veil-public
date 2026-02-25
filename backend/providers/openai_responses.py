"""OpenAI Responses API provider — supports image generation via tool use.

The Chat Completions API does not return images in streaming responses.
Image generation requires the Responses API (POST /v1/responses) with
tools: [{"type": "image_generation"}].

Streaming events from the Responses API:
  - response.output_text.delta                → text content
  - response.image_generation_call.generating → partial image (skipped)
  - response.image_generation_call.completed  → final image (base64)
  - response.completed                        → finish
"""

import json
import logging
from collections.abc import AsyncIterator

import httpx

from backend.providers.base import BaseLLMProvider, ChatMessage, StreamChunk

logger = logging.getLogger(__name__)

# Models that support image generation via the Responses API
IMAGE_CAPABLE_MODELS = {"gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano"}


def is_responses_capable(model: str) -> bool:
    """Check if a model should use the Responses API (supports image generation)."""
    return model in IMAGE_CAPABLE_MODELS


class OpenAIResponsesProvider(BaseLLMProvider):
    """OpenAI Responses API provider with image generation support."""

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
        return "openai_responses"

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a response via the Responses API with image generation tool."""
        url = f"{self._base_url}/responses"

        # Convert ChatMessage format to Responses API input format
        # Responses API uses "developer" instead of "system"
        input_messages = []
        for m in messages:
            if m.role == "system":
                input_messages.append({
                    "role": "developer",
                    "content": m.content,
                })
            else:
                input_messages.append({
                    "role": m.role,
                    "content": m.content,
                })

        payload = {
            "model": model,
            "input": input_messages,
            "tools": [{"type": "image_generation", "quality": "auto", "size": "auto"}],
            "stream": True,
        }

        if temperature != 0.7:
            payload["temperature"] = temperature
        if max_tokens != 4096:
            payload["max_output_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code == 403:
                    raise RuntimeError(
                        "OpenAI Responses API returned 403 Forbidden. "
                        "Your API key may not have access to the Responses API "
                        "(required for image generation). Check your OpenAI account tier and permissions."
                    )
                response.raise_for_status()

                # Parse SSE: event/data pairs come as sequential lines
                current_event = None

                async for line in response.aiter_lines():
                    if line.startswith("event: "):
                        current_event = line[7:]
                        continue

                    if line.startswith("data: ") and current_event:
                        data_str = line[6:]
                        event_type = current_event
                        current_event = None  # Reset for next pair

                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        chunk = self._handle_event(event_type, data, model)
                        if chunk is not None:
                            if isinstance(chunk, Exception):
                                raise chunk
                            yield chunk
                            if chunk.finish_reason:
                                return

                    elif line == "":
                        # Empty line separates SSE events — reset state
                        current_event = None

    def _handle_event(
        self, event_type: str, data: dict, model: str
    ) -> StreamChunk | Exception | None:
        """Process a single SSE event and return a StreamChunk, exception, or None."""
        if event_type == "response.output_text.delta":
            delta = data.get("delta", "")
            if delta:
                return StreamChunk(
                    content=delta,
                    content_type="text",
                    model=model,
                )

        elif event_type == "response.image_generation_call.completed":
            # Final image — extract base64 data
            result = data.get("result", "")
            if result:
                return StreamChunk(
                    content="",
                    content_type="image_base64",
                    image_data=f"data:image/png;base64,{result}",
                    model=model,
                )

        elif event_type == "response.completed":
            return StreamChunk(
                content="",
                finish_reason="stop",
                model=model,
            )

        elif event_type == "response.failed":
            error = data.get("error", {})
            msg = error.get("message", "Unknown error")
            return RuntimeError(f"Responses API error: {msg}")

        # Skip other events: response.created, response.in_progress,
        # response.output_text.done, response.image_generation_call.generating, etc.
        return None
