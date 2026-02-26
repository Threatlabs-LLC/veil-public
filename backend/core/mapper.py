"""Bidirectional entity ↔ placeholder mapper.

Maintains a session-scoped mapping where:
  - Forward: (entity_type, normalized_value) → placeholder (e.g., "EMAIL_003")
  - Reverse: placeholder → original_value

Same entity always gets the same placeholder within a session.
"""

import json
from dataclasses import dataclass

from backend.core.normalizer import normalize_entity


@dataclass
class MappedEntity:
    """An entity with its assigned placeholder."""

    entity_type: str
    original_value: str
    normalized_value: str
    placeholder: str
    confidence: float = 1.0
    detection_method: str = "regex"
    entity_subtype: str | None = None
    start: int = 0
    end: int = 0


class EntityMapper:
    """Bidirectional entity ↔ placeholder mapping for a single session."""

    def __init__(self, session_id: str, initial_counter: dict[str, int] | None = None):
        self.session_id = session_id
        # Counter per entity type: {"PERSON": 3, "EMAIL": 1}
        self._counters: dict[str, int] = initial_counter or {}
        # Forward map: (entity_type, normalized_value) → placeholder
        self._forward: dict[tuple[str, str], str] = {}
        # Reverse map: placeholder → original_value (first occurrence)
        self._reverse: dict[str, str] = {}
        # All mapped entities in this session
        self._entities: list[MappedEntity] = []

    def get_or_create_placeholder(
        self,
        entity_type: str,
        original_value: str,
        confidence: float = 1.0,
        detection_method: str = "regex",
        entity_subtype: str | None = None,
        start: int = 0,
        end: int = 0,
    ) -> MappedEntity:
        """Look up or assign a placeholder for the given entity."""
        normalized = normalize_entity(entity_type, original_value)
        key = (entity_type, normalized)

        if key in self._forward:
            placeholder = self._forward[key]
        else:
            # Assign next counter for this type
            counter = self._counters.get(entity_type, 0) + 1
            self._counters[entity_type] = counter
            placeholder = f"{entity_type}_{counter:03d}"
            self._forward[key] = placeholder
            self._reverse[placeholder] = original_value

        mapped = MappedEntity(
            entity_type=entity_type,
            original_value=original_value,
            normalized_value=normalized,
            placeholder=placeholder,
            confidence=confidence,
            detection_method=detection_method,
            entity_subtype=entity_subtype,
            start=start,
            end=end,
        )
        self._entities.append(mapped)
        return mapped

    def lookup_placeholder(self, placeholder: str) -> str | None:
        """Reverse lookup: placeholder → original value."""
        return self._reverse.get(placeholder)

    def get_all_placeholders(self) -> dict[str, str]:
        """Return all placeholder → original mappings."""
        return dict(self._reverse)

    def get_counter_state(self) -> dict[str, int]:
        """Return current counter state for persistence."""
        return dict(self._counters)

    def get_counter_state_json(self) -> str:
        """Return counter state as JSON string for DB storage."""
        return json.dumps(self._counters)

    @property
    def entities(self) -> list[MappedEntity]:
        return list(self._entities)

    @classmethod
    def from_db_state(
        cls,
        session_id: str,
        counter_json: str,
        existing_entities: list[dict],
    ) -> "EntityMapper":
        """Reconstruct mapper from database state."""
        counters = json.loads(counter_json) if counter_json else {}
        mapper = cls(session_id=session_id, initial_counter=counters)

        # Rebuild forward/reverse maps from existing entities
        for ent in existing_entities:
            normalized = normalize_entity(ent["entity_type"], ent["original_value"])
            key = (ent["entity_type"], normalized)
            mapper._forward[key] = ent["placeholder"]
            mapper._reverse[ent["placeholder"]] = ent["original_value"]

        return mapper
