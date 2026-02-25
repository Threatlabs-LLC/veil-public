"""Abstract base for LLM provider adapters."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class StreamChunk:
    """A single chunk from a streaming LLM response.

    content_type values:
        "text"         — normal text token (default, goes through rehydration)
        "image_url"    — image returned as a URL (pass through untouched)
        "image_base64" — image returned as base64 data (pass through untouched)
    """

    content: str = ""
    content_type: str = "text"  # "text" | "image_url" | "image_base64"
    image_url: str | None = None
    image_data: str | None = None  # base64 encoded
    finish_reason: str | None = None
    model: str | None = None


@dataclass
class ChatResponse:
    """Complete (non-streaming) response from an LLM."""

    content: str
    model: str
    finish_reason: str = "stop"
    input_tokens: int = 0
    output_tokens: int = 0


class BaseLLMProvider(ABC):
    """Abstract base for LLM provider adapters."""

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a chat completion response."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
