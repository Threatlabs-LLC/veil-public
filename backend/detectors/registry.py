"""Detector registry — orchestrates multiple detectors into a unified pipeline."""

from backend.detectors.base import BaseDetector, DetectedEntity
from backend.detectors.regex_detector import RegexDetector


class DetectorRegistry:
    """Runs all registered detectors and merges results."""

    def __init__(self):
        self._detectors: list[BaseDetector] = []

    def register(self, detector: BaseDetector) -> None:
        self._detectors.append(detector)

    def detect_all(self, text: str) -> list[DetectedEntity]:
        """Run all detectors and merge results with overlap resolution."""
        all_entities: list[DetectedEntity] = []

        for detector in self._detectors:
            entities = detector.detect(text)
            all_entities.extend(entities)

        return self._resolve_overlaps(all_entities)

    def _resolve_overlaps(self, entities: list[DetectedEntity]) -> list[DetectedEntity]:
        """Global overlap resolution across all detectors.

        Priority order:
        1. Custom rules (user-defined) always win
        2. Regex patterns (precise, tested) beat NER
        3. NER fills gaps that regex can't cover (names, orgs, etc.)
        Within the same priority: longer spans win, then higher confidence.
        """
        if not entities:
            return entities

        def _sort_key(e: DetectedEntity) -> tuple:
            if e.detection_method.startswith("custom_"):
                priority = 0  # Custom rules always win
            elif e.detection_method == "regex":
                priority = 1  # Regex is precise, beats NER
            else:
                priority = 2  # NER fills gaps
            return (priority, -(e.end - e.start), -e.confidence)

        entities.sort(key=_sort_key)

        result: list[DetectedEntity] = []
        occupied: list[tuple[int, int]] = []

        for entity in entities:
            overlaps = any(
                entity.start < occ_end and entity.end > occ_start
                for occ_start, occ_end in occupied
            )
            if not overlaps:
                result.append(entity)
                occupied.append((entity.start, entity.end))

        result.sort(key=lambda e: e.start)
        return result


def create_default_registry(custom_rules=None, org_tier: str = "free") -> DetectorRegistry:
    """Create a registry with the default set of detectors.

    Args:
        custom_rules: Optional list of DetectionRule objects from the DB.
        org_tier: Organization tier name for feature-gated detectors.
    """
    registry = DetectorRegistry()
    registry.register(RegexDetector())

    # Add FQDN detector for Business+ tiers
    from backend.licensing.tiers import FEATURE_FQDN_DETECTION, tier_has_feature
    if tier_has_feature(org_tier, FEATURE_FQDN_DETECTION):
        from backend.detectors.fqdn_detector import FQDNDetector
        registry.register(FQDNDetector())

    # Add Presidio/spaCy NER detector if available
    from backend.detectors.presidio_detector import get_presidio_detector
    presidio = get_presidio_detector()
    if presidio.is_available:
        registry.register(presidio)

    # Add custom org rules from DB
    if custom_rules:
        from backend.detectors.custom_rule_detector import CustomRuleDetector
        custom_detector = CustomRuleDetector(custom_rules)
        if custom_detector.is_available:
            registry.register(custom_detector)

    return registry
