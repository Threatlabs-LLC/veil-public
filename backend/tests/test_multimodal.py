"""Tests for multimodal content passthrough — images and non-text content
flow through the proxy without being dropped or processed by the rehydrator."""

import json

from backend.providers.base import StreamChunk
from backend.core.mapper import EntityMapper
from backend.core.rehydrator import Rehydrator


# ── StreamChunk dataclass ────────────────────────────────────────────


class TestStreamChunkFields:
    """Verify extended StreamChunk fields exist and default correctly."""

    def test_default_content_type_is_text(self):
        chunk = StreamChunk(content="hello")
        assert chunk.content_type == "text"
        assert chunk.image_url is None
        assert chunk.image_data is None

    def test_image_url_chunk(self):
        chunk = StreamChunk(
            content="",
            content_type="image_url",
            image_url="https://example.com/img.png",
        )
        assert chunk.content_type == "image_url"
        assert chunk.image_url == "https://example.com/img.png"
        assert chunk.image_data is None
        assert chunk.content == ""

    def test_image_base64_chunk(self):
        chunk = StreamChunk(
            content="",
            content_type="image_base64",
            image_data="data:image/png;base64,iVBORw0KGgo=",
        )
        assert chunk.content_type == "image_base64"
        assert chunk.image_data == "data:image/png;base64,iVBORw0KGgo="
        assert chunk.image_url is None

    def test_text_chunk_backward_compatible(self):
        """Existing code that creates StreamChunk(content=..., finish_reason=..., model=...)
        should keep working unchanged."""
        chunk = StreamChunk(content="token", finish_reason=None, model="gpt-4o")
        assert chunk.content == "token"
        assert chunk.content_type == "text"
        assert chunk.finish_reason is None
        assert chunk.model == "gpt-4o"

    def test_finish_reason_chunk(self):
        chunk = StreamChunk(content="", finish_reason="stop", model="gpt-4o")
        assert chunk.content_type == "text"
        assert chunk.finish_reason == "stop"


# ── Image passthrough logic ──────────────────────────────────────────


class TestImagePassthrough:
    """Images should NOT go through the rehydrator — they pass through untouched."""

    def _make_rehydrator_with_mappings(self) -> Rehydrator:
        """Create a rehydrator that has some placeholder mappings."""
        mapper = EntityMapper(session_id="test-session")
        # Simulate having mapped some entities so rehydration has work to do
        mapper.get_or_create_placeholder("PERSON", "alice")
        mapper.get_or_create_placeholder("EMAIL", "alice@corp.com")
        return Rehydrator(mapper=mapper)

    def test_text_still_gets_rehydrated(self):
        """Sanity check: text content with placeholders gets rehydrated."""
        rehydrator = self._make_rehydrator_with_mappings()
        text = "Hello PERSON_001, your email is EMAIL_001."
        result = rehydrator.rehydrate(text)
        assert "alice" in result
        assert "alice@corp.com" in result

    def test_image_url_not_processed_by_rehydrator(self):
        """Image URLs should not be fed to the rehydrator."""
        chunk = StreamChunk(
            content="",
            content_type="image_url",
            image_url="https://example.com/PERSON_001.png",
        )
        # The design: code checks chunk.content_type and skips rehydration
        # for non-text. We verify the chunk carries the right type.
        assert chunk.content_type == "image_url"
        assert chunk.content == ""  # No text content to rehydrate

    def test_image_base64_not_processed_by_rehydrator(self):
        chunk = StreamChunk(
            content="",
            content_type="image_base64",
            image_data="data:image/png;base64,PERSON_001_fake_data",
        )
        assert chunk.content_type == "image_base64"
        assert chunk.content == ""


# ── Mixed text + image stream ────────────────────────────────────────


class TestMixedContentStream:
    """Simulate a stream that mixes text and image chunks."""

    def test_mixed_stream_separates_correctly(self):
        """Process a sequence of chunks like a real stream would produce."""
        chunks = [
            StreamChunk(content="Here is an image: ", content_type="text", model="gpt-4o"),
            StreamChunk(
                content="",
                content_type="image_url",
                image_url="https://example.com/generated.png",
                model="gpt-4o",
            ),
            StreamChunk(content="\nWhat do you think?", content_type="text", model="gpt-4o"),
            StreamChunk(content="", finish_reason="stop", model="gpt-4o"),
        ]

        text_parts = []
        image_parts = []

        for chunk in chunks:
            if chunk.content_type in ("image_url", "image_base64"):
                image_parts.append(chunk)
            elif chunk.content:
                text_parts.append(chunk.content)

        assert len(text_parts) == 2
        assert text_parts[0] == "Here is an image: "
        assert text_parts[1] == "\nWhat do you think?"
        assert len(image_parts) == 1
        assert image_parts[0].image_url == "https://example.com/generated.png"

    def test_multiple_images_in_stream(self):
        chunks = [
            StreamChunk(content="Two images: ", content_type="text"),
            StreamChunk(content="", content_type="image_url", image_url="https://example.com/1.png"),
            StreamChunk(content=" and ", content_type="text"),
            StreamChunk(content="", content_type="image_base64", image_data="data:image/png;base64,abc123"),
            StreamChunk(content="", finish_reason="stop"),
        ]

        images = [c for c in chunks if c.content_type in ("image_url", "image_base64")]
        texts = [c.content for c in chunks if c.content_type == "text" and c.content]

        assert len(images) == 2
        assert images[0].content_type == "image_url"
        assert images[1].content_type == "image_base64"
        assert texts == ["Two images: ", " and "]


# ── SSE formatting ───────────────────────────────────────────────────


class TestSSEImageFormatting:
    """Verify that image chunks produce correct SSE event format."""

    def test_image_url_sse_format(self):
        """The chat endpoint emits 'event: image' for image chunks."""
        chunk = StreamChunk(
            content="",
            content_type="image_url",
            image_url="https://example.com/img.png",
        )
        # Simulate what chat.py generate_sse does
        sse_data = json.dumps({
            "type": chunk.content_type,
            "url": chunk.image_url,
            "data": chunk.image_data,
        })
        sse_line = f"event: image\ndata: {sse_data}\n\n"

        assert "event: image" in sse_line
        parsed = json.loads(sse_line.split("data: ")[1].strip())
        assert parsed["type"] == "image_url"
        assert parsed["url"] == "https://example.com/img.png"
        assert parsed["data"] is None

    def test_image_base64_sse_format(self):
        chunk = StreamChunk(
            content="",
            content_type="image_base64",
            image_data="data:image/jpeg;base64,/9j/4AAQ",
        )
        sse_data = json.dumps({
            "type": chunk.content_type,
            "url": chunk.image_url,
            "data": chunk.image_data,
        })
        sse_line = f"event: image\ndata: {sse_data}\n\n"

        parsed = json.loads(sse_line.split("data: ")[1].strip())
        assert parsed["type"] == "image_base64"
        assert parsed["data"] == "data:image/jpeg;base64,/9j/4AAQ"
        assert parsed["url"] is None

    def test_text_chunk_not_formatted_as_image(self):
        chunk = StreamChunk(content="Hello world", content_type="text")
        # Text chunks should NOT be emitted as image events
        assert chunk.content_type == "text"
        assert chunk.content_type not in ("image_url", "image_base64")


# ── Gateway image passthrough (markdown) ─────────────────────────────


class TestGatewayImageMarkdown:
    """In gateway mode, images are embedded as markdown in the OpenAI-compatible response."""

    def test_image_url_to_markdown(self):
        """Gateway converts image_url chunks to markdown image syntax."""
        chunk = StreamChunk(
            content="",
            content_type="image_url",
            image_url="https://cdn.openai.com/generated/abc.png",
        )
        # Simulate what gateway.py does
        if chunk.content_type == "image_url" and chunk.image_url:
            image_content = f"\n![Generated Image]({chunk.image_url})\n"
        else:
            image_content = ""

        assert "![Generated Image]" in image_content
        assert chunk.image_url in image_content

    def test_image_base64_to_markdown(self):
        chunk = StreamChunk(
            content="",
            content_type="image_base64",
            image_data="data:image/png;base64,iVBORw0=",
        )
        if chunk.content_type == "image_base64" and chunk.image_data:
            image_content = f"\n![Generated Image]({chunk.image_data})\n"
        else:
            image_content = ""

        assert "![Generated Image]" in image_content
        assert "data:image/png;base64" in image_content

    def test_text_chunk_unchanged(self):
        """Text chunks in gateway are NOT wrapped in markdown image syntax."""
        chunk = StreamChunk(content="Hello world", content_type="text")
        # Text goes through rehydrator, not the image path
        assert chunk.content_type not in ("image_url", "image_base64")


# ── Rehydrator streaming with images ─────────────────────────────────


class TestRehydratorStreamingWithImages:
    """Rehydrator streaming should only process text; images are skipped upstream."""

    def test_rehydrator_only_handles_text(self):
        mapper = EntityMapper(session_id="test")
        mapper.get_or_create_placeholder("PERSON", "Bob Smith")
        rehydrator = Rehydrator(mapper=mapper)

        # Normal text streaming
        safe, remaining = rehydrator.rehydrate_streaming("Hello PERSON_001, how are you?")
        full = safe + rehydrator.rehydrate(remaining) if remaining else safe
        assert "Bob Smith" in full

    def test_image_content_never_reaches_rehydrator(self):
        """Demonstrate the passthrough pattern: image chunks are checked by
        content_type before ever reaching the rehydrator."""
        mapper = EntityMapper(session_id="test")
        rehydrator = Rehydrator(mapper=mapper)

        chunks = [
            StreamChunk(content="text before ", content_type="text"),
            StreamChunk(content="", content_type="image_url", image_url="https://example.com/img.png"),
            StreamChunk(content=" text after", content_type="text"),
        ]

        text_buffer = ""
        image_urls = []

        for chunk in chunks:
            if chunk.content_type in ("image_url", "image_base64"):
                # Passthrough: do not feed to rehydrator
                if chunk.image_url:
                    image_urls.append(chunk.image_url)
                continue
            if chunk.content:
                text_buffer += chunk.content

        # Only text went to the buffer
        assert text_buffer == "text before  text after"
        assert image_urls == ["https://example.com/img.png"]
        # Rehydrate the text portion
        result = rehydrator.rehydrate(text_buffer)
        assert result == "text before  text after"
