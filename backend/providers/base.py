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
    """A single chunk from a streaming LLM response."""

    content: str = ""
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
