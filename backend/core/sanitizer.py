"""Sanitization pipeline: detect → map → replace.

Takes user input text, detects sensitive entities, maps them to placeholders,
and returns the sanitized text along with the entity list.
"""

from dataclasses import dataclass, field

from backend.core.mapper import EntityMapper, MappedEntity
from backend.detectors.base import DetectedEntity
from backend.detectors.registry import DetectorRegistry


@dataclass
class SanitizationResult:
    """Result of sanitizing a text."""

    original_text: str
    sanitized_text: str
    entities: list[MappedEntity] = field(default_factory=list)

    @property
    def entity_count(self) -> int:
        return len(self.entities)

    def to_dict(self, include_originals: bool = True) -> dict:
        result = {
            "sanitized_text": self.sanitized_text,
            "entity_count": self.entity_count,
            "entities": [
                {
                    "entity_type": e.entity_type,
                    "placeholder": e.placeholder,
                    "confidence": e.confidence,
                    "start": e.start,
                    "end": e.end,
                    "detection_method": e.detection_method,
                    **({"original": e.original_value} if include_originals else {}),
                }
                for e in self.entities
            ],
        }
        if include_originals:
            result["original_text"] = self.original_text
        return result


class Sanitizer:
    """Orchestrates the detect → map → replace pipeline."""

    def __init__(self, registry: DetectorRegistry, mapper: EntityMapper):
        self._registry = registry
        self._mapper = mapper

    def sanitize(self, text: str) -> SanitizationResult:
        """Detect entities, map to placeholders, and replace in text."""
        # Step 1: Detect all entities
        detected: list[DetectedEntity] = self._registry.detect_all(text)

        if not detected:
            return SanitizationResult(
                original_text=text,
                sanitized_text=text,
                entities=[],
            )

        # Step 2: Map each detection to a placeholder
        mapped_entities: list[MappedEntity] = []
        for det in detected:
            mapped = self._mapper.get_or_create_placeholder(
                entity_type=det.entity_type,
                original_value=det.value,
                confidence=det.confidence,
                detection_method=det.detection_method,
                entity_subtype=det.entity_subtype,
                start=det.start,
                end=det.end,
            )
            mapped_entities.append(mapped)

        # Step 3: Replace in text (process from end to preserve positions)
        sanitized = text
        for entity in sorted(mapped_entities, key=lambda e: e.start, reverse=True):
            sanitized = (
                sanitized[: entity.start] + entity.placeholder + sanitized[entity.end :]
            )

        return SanitizationResult(
            original_text=text,
            sanitized_text=sanitized,
            entities=mapped_entities,
        )

    @property
    def mapper(self) -> EntityMapper:
        return self._mapper
