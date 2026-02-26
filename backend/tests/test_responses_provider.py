"""Tests for the OpenAI Responses API provider (image generation)."""

import json
import pytest
from unittest.mock import patch

from backend.providers.openai_responses import (
    OpenAIResponsesProvider,
    is_responses_capable,
    IMAGE_CAPABLE_MODELS,
)
from backend.providers.base import ChatMessage, StreamChunk


# ────────────────────────────────────────────────────────────
# Model detection
# ────────────────────────────────────────────────────────────


class TestModelDetection:
    def test_gpt4o_is_responses_capable(self):
        assert is_responses_capable("gpt-4o") is True

    def test_gpt4o_mini_is_responses_capable(self):
        assert is_responses_capable("gpt-4o-mini") is True

    def test_gpt41_is_responses_capable(self):
        assert is_responses_capable("gpt-4.1") is True

    def test_gpt41_mini_is_responses_capable(self):
        assert is_responses_capable("gpt-4.1-mini") is True

    def test_gpt41_nano_is_responses_capable(self):
        assert is_responses_capable("gpt-4.1-nano") is True

    def test_gpt35_not_responses_capable(self):
        assert is_responses_capable("gpt-3.5-turbo") is False

    def test_claude_not_responses_capable(self):
        assert is_responses_capable("claude-3-opus") is False

    def test_llama_not_responses_capable(self):
        assert is_responses_capable("llama-3.1-70b") is False

    def test_empty_string_not_capable(self):
        assert is_responses_capable("") is False

    def test_image_capable_models_is_set(self):
        assert isinstance(IMAGE_CAPABLE_MODELS, set)
        assert len(IMAGE_CAPABLE_MODELS) >= 3


# ────────────────────────────────────────────────────────────
# Provider basics
# ────────────────────────────────────────────────────────────


class TestProviderBasics:
    def test_provider_name(self):
        provider = OpenAIResponsesProvider(api_key="test-key")
        assert provider.name == "openai_responses"

    def test_provider_default_base_url(self):
        provider = OpenAIResponsesProvider(api_key="test-key")
        assert provider._base_url == "https://api.openai.com/v1"

    def test_provider_custom_base_url(self):
        provider = OpenAIResponsesProvider(api_key="test-key", base_url="https://custom.api.com/v1/")
        assert provider._base_url == "https://custom.api.com/v1"

    def test_provider_strips_trailing_slash(self):
        provider = OpenAIResponsesProvider(api_key="test-key", base_url="https://api.example.com/v1/")
        assert provider._base_url == "https://api.example.com/v1"


# ────────────────────────────────────────────────────────────
# Event handling
# ────────────────────────────────────────────────────────────


class TestEventHandling:
    def setup_method(self):
        self.provider = OpenAIResponsesProvider(api_key="test-key")

    def test_text_delta_event(self):
        result = self.provider._handle_event(
            "response.output_text.delta",
            {"delta": "Hello world"},
            "gpt-4o",
        )
        assert isinstance(result, StreamChunk)
        assert result.content == "Hello world"
        assert result.content_type == "text"
        assert result.model == "gpt-4o"

    def test_text_delta_empty(self):
        result = self.provider._handle_event(
            "response.output_text.delta",
            {"delta": ""},
            "gpt-4o",
        )
        assert result is None

    def test_image_completed_event(self):
        result = self.provider._handle_event(
            "response.image_generation_call.completed",
            {"result": "iVBORw0KGgoAAAANSUhEUg=="},
            "gpt-4o",
        )
        assert isinstance(result, StreamChunk)
        assert result.content_type == "image_base64"
        assert result.image_data == "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="
        assert result.model == "gpt-4o"

    def test_image_completed_empty(self):
        result = self.provider._handle_event(
            "response.image_generation_call.completed",
            {"result": ""},
            "gpt-4o",
        )
        assert result is None

    def test_response_completed_event(self):
        result = self.provider._handle_event(
            "response.completed",
            {},
            "gpt-4o",
        )
        assert isinstance(result, StreamChunk)
        assert result.finish_reason == "stop"

    def test_response_failed_event(self):
        result = self.provider._handle_event(
            "response.failed",
            {"error": {"message": "Rate limit exceeded"}},
            "gpt-4o",
        )
        assert isinstance(result, RuntimeError)
        assert "Rate limit exceeded" in str(result)

    def test_response_failed_no_message(self):
        result = self.provider._handle_event(
            "response.failed",
            {"error": {}},
            "gpt-4o",
        )
        assert isinstance(result, RuntimeError)
        assert "Unknown error" in str(result)

    def test_unknown_event_ignored(self):
        result = self.provider._handle_event(
            "response.in_progress",
            {},
            "gpt-4o",
        )
        assert result is None

    def test_output_text_done_ignored(self):
        result = self.provider._handle_event(
            "response.output_text.done",
            {},
            "gpt-4o",
        )
        assert result is None

    def test_image_generating_ignored(self):
        result = self.provider._handle_event(
            "response.image_generation_call.generating",
            {"partial_image": "..."},
            "gpt-4o",
        )
        assert result is None


# ────────────────────────────────────────────────────────────
# Streaming integration (mocked HTTP)
# ────────────────────────────────────────────────────────────


def _make_sse_lines(events: list[tuple[str, dict]]) -> list[str]:
    """Build SSE text lines from event/data pairs."""
    lines = []
    for event_type, data in events:
        lines.append(f"event: {event_type}")
        lines.append(f"data: {json.dumps(data)}")
        lines.append("")
    return lines


class MockAsyncLineIterator:
    """Mock for httpx response.aiter_lines()."""

    def __init__(self, lines: list[str]):
        self._lines = lines
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._lines):
            raise StopAsyncIteration
        line = self._lines[self._index]
        self._index += 1
        return line


class MockStreamResponse:
    """Mock httpx streaming response."""

    def __init__(self, lines: list[str], status_code: int = 200):
        self._lines = lines
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def aiter_lines(self):
        return MockAsyncLineIterator(self._lines)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockAsyncClient:
    """Mock httpx.AsyncClient."""

    def __init__(self, response: MockStreamResponse):
        self._response = response

    def stream(self, method, url, **kwargs):
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_stream_text_only():
    """Test a text-only response from the Responses API."""
    events = [
        ("response.output_text.delta", {"delta": "Hello "}),
        ("response.output_text.delta", {"delta": "world!"}),
        ("response.output_text.done", {"text": "Hello world!"}),
        ("response.completed", {"status": "completed"}),
    ]
    lines = _make_sse_lines(events)
    mock_response = MockStreamResponse(lines)
    mock_client = MockAsyncClient(mock_response)

    provider = OpenAIResponsesProvider(api_key="test-key")

    chunks = []
    with patch("httpx.AsyncClient", return_value=mock_client):
        async for chunk in provider.chat_stream(
            messages=[ChatMessage(role="user", content="Say hello")],
            model="gpt-4o",
        ):
            chunks.append(chunk)

    assert len(chunks) == 3  # 2 text + 1 finish
    assert chunks[0].content == "Hello "
    assert chunks[0].content_type == "text"
    assert chunks[1].content == "world!"
    assert chunks[2].finish_reason == "stop"


@pytest.mark.asyncio
async def test_stream_image_only():
    """Test an image-only response (no text)."""
    events = [
        ("response.image_generation_call.generating", {"partial_image": "partial..."}),
        ("response.image_generation_call.completed", {"result": "iVBORbase64data"}),
        ("response.completed", {"status": "completed"}),
    ]
    lines = _make_sse_lines(events)
    mock_response = MockStreamResponse(lines)
    mock_client = MockAsyncClient(mock_response)

    provider = OpenAIResponsesProvider(api_key="test-key")

    chunks = []
    with patch("httpx.AsyncClient", return_value=mock_client):
        async for chunk in provider.chat_stream(
            messages=[ChatMessage(role="user", content="Draw a cat")],
            model="gpt-4o",
        ):
            chunks.append(chunk)

    assert len(chunks) == 2  # 1 image + 1 finish
    assert chunks[0].content_type == "image_base64"
    assert "iVBORbase64data" in chunks[0].image_data
    assert chunks[1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_stream_mixed_text_and_image():
    """Test a response with both text and image content."""
    events = [
        ("response.output_text.delta", {"delta": "Here is the image you requested:\n\n"}),
        ("response.output_text.done", {"text": "Here is the image you requested:\n\n"}),
        ("response.image_generation_call.generating", {"partial_image": "partial..."}),
        ("response.image_generation_call.completed", {"result": "base64imagedata"}),
        ("response.output_text.delta", {"delta": "\n\nThe image shows a sunset."}),
        ("response.completed", {"status": "completed"}),
    ]
    lines = _make_sse_lines(events)
    mock_response = MockStreamResponse(lines)
    mock_client = MockAsyncClient(mock_response)

    provider = OpenAIResponsesProvider(api_key="test-key")

    chunks = []
    with patch("httpx.AsyncClient", return_value=mock_client):
        async for chunk in provider.chat_stream(
            messages=[ChatMessage(role="user", content="Generate a sunset image")],
            model="gpt-4o",
        ):
            chunks.append(chunk)

    # Text + image + text + finish
    assert len(chunks) == 4
    assert chunks[0].content_type == "text"
    assert chunks[0].content == "Here is the image you requested:\n\n"
    assert chunks[1].content_type == "image_base64"
    assert chunks[2].content_type == "text"
    assert "sunset" in chunks[2].content
    assert chunks[3].finish_reason == "stop"


@pytest.mark.asyncio
async def test_stream_error_handling():
    """Test that response.failed events raise exceptions."""
    events = [
        ("response.output_text.delta", {"delta": "Starting..."}),
        ("response.failed", {"error": {"message": "Content policy violation"}}),
    ]
    lines = _make_sse_lines(events)
    mock_response = MockStreamResponse(lines)
    mock_client = MockAsyncClient(mock_response)

    provider = OpenAIResponsesProvider(api_key="test-key")

    with pytest.raises(RuntimeError, match="Content policy violation"):
        with patch("httpx.AsyncClient", return_value=mock_client):
            async for chunk in provider.chat_stream(
                messages=[ChatMessage(role="user", content="test")],
                model="gpt-4o",
            ):
                pass


@pytest.mark.asyncio
async def test_system_message_converted_to_developer():
    """Test that system messages are converted to developer role."""
    events = [
        ("response.output_text.delta", {"delta": "OK"}),
        ("response.completed", {"status": "completed"}),
    ]
    lines = _make_sse_lines(events)
    mock_response = MockStreamResponse(lines)

    captured_payload = {}

    class CapturingClient:
        def stream(self, method, url, **kwargs):
            captured_payload.update(kwargs.get("json", {}))
            return mock_response

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    provider = OpenAIResponsesProvider(api_key="test-key")

    with patch("httpx.AsyncClient", return_value=CapturingClient()):
        async for _ in provider.chat_stream(
            messages=[
                ChatMessage(role="system", content="You are helpful."),
                ChatMessage(role="user", content="Hello"),
            ],
            model="gpt-4o",
        ):
            pass

    # Verify system was converted to developer
    input_msgs = captured_payload.get("input", [])
    assert len(input_msgs) == 2
    assert input_msgs[0]["role"] == "developer"
    assert input_msgs[0]["content"] == "You are helpful."
    assert input_msgs[1]["role"] == "user"


@pytest.mark.asyncio
async def test_payload_includes_image_generation_tool():
    """Test that the payload always includes the image_generation tool."""
    events = [
        ("response.completed", {"status": "completed"}),
    ]
    lines = _make_sse_lines(events)
    mock_response = MockStreamResponse(lines)

    captured_payload = {}

    class CapturingClient:
        def stream(self, method, url, **kwargs):
            captured_payload.update(kwargs.get("json", {}))
            return mock_response

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    provider = OpenAIResponsesProvider(api_key="test-key")

    with patch("httpx.AsyncClient", return_value=CapturingClient()):
        async for _ in provider.chat_stream(
            messages=[ChatMessage(role="user", content="Hello")],
            model="gpt-4o",
        ):
            pass

    tools = captured_payload.get("tools", [])
    assert len(tools) == 1
    assert tools[0]["type"] == "image_generation"


@pytest.mark.asyncio
async def test_payload_uses_responses_endpoint():
    """Test that the request goes to /responses, not /chat/completions."""
    events = [
        ("response.completed", {"status": "completed"}),
    ]
    lines = _make_sse_lines(events)
    mock_response = MockStreamResponse(lines)

    captured_url = None

    class CapturingClient:
        def stream(self, method, url, **kwargs):
            nonlocal captured_url
            captured_url = url
            return mock_response

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    provider = OpenAIResponsesProvider(api_key="test-key")

    with patch("httpx.AsyncClient", return_value=CapturingClient()):
        async for _ in provider.chat_stream(
            messages=[ChatMessage(role="user", content="Hello")],
            model="gpt-4o",
        ):
            pass

    assert captured_url == "https://api.openai.com/v1/responses"
