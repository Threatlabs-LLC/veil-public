"""Custom rule detector — runs org-specific regex and dictionary rules from the DB."""

from __future__ import annotations

import json
import re
from typing import Sequence

from backend.detectors.base import BaseDetector, DetectedEntity
from backend.models.rule import DetectionRule


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
        results = []
        try:
            pattern = re.compile(rule.pattern, re.IGNORECASE)
            for match in pattern.finditer(text):
                results.append(DetectedEntity(
                    entity_type=rule.entity_type,
                    value=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    confidence=rule.confidence,
                    detection_method="custom_regex",
                    entity_subtype=rule.name,
                ))
        except re.error:
            pass  # Skip invalid patterns silently
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
