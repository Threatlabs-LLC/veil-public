"""Rehydrator — replaces placeholders back with original values in LLM responses.

Handles both complete responses and streaming token buffers.
"""

import re

from backend.core.mapper import EntityMapper

# Pattern that matches our placeholder format: TYPE_NNN
PLACEHOLDER_PATTERN = re.compile(
    r"\b([A-Z][A-Z_]+)_(\d{3})\b"
)


class Rehydrator:
    """Replaces placeholders with original values using the session mapper."""

    def __init__(self, mapper: EntityMapper):
        self._mapper = mapper

    def rehydrate(self, text: str) -> str:
        """Replace all placeholders in text with their original values."""
        def _replace(match: re.Match) -> str:
            placeholder = match.group(0)
            original = self._mapper.lookup_placeholder(placeholder)
            return original if original is not None else placeholder

        return PLACEHOLDER_PATTERN.sub(_replace, text)

    def rehydrate_streaming(self, buffer: str) -> tuple[str, str]:
        """Rehydrate a streaming buffer, returning (rehydrated_safe, remaining_buffer).

        The remaining_buffer contains any partial placeholder at the end that
        we can't yet determine (e.g., "IP_" or "EMAIL_00" at the end of a chunk).

        Returns:
            tuple of (safe_text_to_emit, buffer_to_keep)
        """
        # Find the last potential partial placeholder
        # Look for an incomplete pattern at the end: capital letters followed by _
        # or a complete TYPE_ followed by incomplete digits
        partial_match = re.search(r"\b[A-Z][A-Z_]*(?:_\d{0,2})?$", buffer)

        if partial_match:
            safe_part = buffer[: partial_match.start()]
            remaining = buffer[partial_match.start() :]
        else:
            safe_part = buffer
            remaining = ""

        # Rehydrate the safe part
        rehydrated = self.rehydrate(safe_part)
        return rehydrated, remaining
