"""Custom rule detector — runs org-specific regex and dictionary rules from the DB."""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Sequence

from backend.detectors.base import BaseDetector, DetectedEntity
from backend.models.rule import DetectionRule

logger = logging.getLogger(__name__)

# Maximum time (seconds) for a single regex rule to execute
_REGEX_TIMEOUT = 1.0


class CustomRuleDetector(BaseDetector):
    """Detects entities using custom rules loaded from the database."""

    def __init__(self, rules: Sequence[DetectionRule]):
        self._rules = [r for r in rules if r.is_active]

    @property
    def name(self) -> str:
        return "custom_rules"

    @property
    def is_available(self) -> bool:
        return len(self._rules) > 0

    def detect(self, text: str) -> list[DetectedEntity]:
        entities: list[DetectedEntity] = []

        for rule in self._rules:
            if rule.detection_method == "regex" and rule.pattern:
                entities.extend(self._detect_regex(text, rule))
            elif rule.detection_method == "dictionary" and rule.word_list:
                entities.extend(self._detect_dictionary(text, rule))

        return entities

    def _detect_regex(self, text: str, rule: DetectionRule) -> list[DetectedEntity]:
        results: list[DetectedEntity] = []
        try:
            pattern = re.compile(rule.pattern, re.IGNORECASE)
        except re.error:
            return results  # Skip invalid patterns

        # Run regex in a thread with timeout to prevent ReDoS
        matches: list[tuple[str, int, int]] = []

        def _run():
            try:
                for match in pattern.finditer(text):
                    matches.append((match.group(0), match.start(), match.end()))
            except Exception:
                pass

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=_REGEX_TIMEOUT)

        if thread.is_alive():
            logger.warning(
                f"Custom regex rule '{rule.name}' (id={rule.id}) timed out after "
                f"{_REGEX_TIMEOUT}s — possible ReDoS pattern, skipping"
            )
            return results

        for value, start, end in matches:
            results.append(DetectedEntity(
                entity_type=rule.entity_type,
                value=value,
                start=start,
                end=end,
                confidence=rule.confidence,
                detection_method="custom_regex",
                entity_subtype=rule.name,
            ))
        return results

    def _detect_dictionary(self, text: str, rule: DetectionRule) -> list[DetectedEntity]:
        results = []
        try:
            words = json.loads(rule.word_list)
        except (json.JSONDecodeError, TypeError):
            return results

        text_lower = text.lower()
        for word in words:
            word_lower = word.lower()
            idx = 0
            while True:
                pos = text_lower.find(word_lower, idx)
                if pos == -1:
                    break
                results.append(DetectedEntity(
                    entity_type=rule.entity_type,
                    value=text[pos:pos + len(word)],
                    start=pos,
                    end=pos + len(word),
                    confidence=rule.confidence,
                    detection_method="custom_dictionary",
                    entity_subtype=rule.name,
                ))
                idx = pos + 1

        return results
