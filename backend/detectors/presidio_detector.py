"""Presidio/spaCy NER detector — detects names, orgs, addresses, and more.

Wraps Microsoft Presidio's AnalyzerEngine with spaCy NER backend.
Gracefully degrades if presidio or spaCy are not installed.

Install with: pip install veilchat[ner]
Then download the spaCy model: python -m spacy download en_core_web_md
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.detectors.base import BaseDetector, DetectedEntity

if TYPE_CHECKING:
    from presidio_analyzer import AnalyzerEngine

logger = logging.getLogger(__name__)

# Presidio entity types → VeilChat entity types
ENTITY_MAP = {
    "PERSON": "PERSON",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "IP_ADDRESS": "IP_ADDRESS",
    "CREDIT_CARD": "CREDIT_CARD",
    "US_SSN": "SSN",
    "US_PASSPORT": "PASSPORT",
    "US_DRIVER_LICENSE": "DRIVERS_LICENSE",
    "IBAN_CODE": "IBAN",
    "MEDICAL_LICENSE": "MEDICAL_RECORD",
    "URL": "URL",
    "LOCATION": "ADDRESS",
    "ORGANIZATION": "ORGANIZATION",  # NEW — not covered by regex
    "DATE_TIME": "DATE_OF_BIRTH",  # Context-dependent, we'll filter
    "NRP": "PERSON",  # Nationality/religious/political group
    "US_BANK_NUMBER": "BANK_ACCOUNT",
    "UK_NHS": "NATIONAL_ID",
    "AU_ABN": "NATIONAL_ID",
    "AU_ACN": "NATIONAL_ID",
    "AU_TFN": "NATIONAL_ID",
    "AU_MEDICARE": "NATIONAL_ID",
    "SG_NRIC_FIN": "NATIONAL_ID",
    "IN_PAN": "NATIONAL_ID",
    "IN_AADHAAR": "NATIONAL_ID",
}

# Entity types we want Presidio to detect.
# EXCLUDED: types that regex handles better and cause NER false positives in logs:
#   PHONE_NUMBER — regex has better formatting/validation
#   IP_ADDRESS — regex is more precise
#   CREDIT_CARD — regex + Luhn is more accurate
#   US_SSN — regex pattern is sufficient
#   URL — regex is more precise
#   DATE_TIME — causes massive false positives on timestamps, log dates, etc.
PRESIDIO_ENTITIES = [
    "PERSON",
    "ORGANIZATION",
    "LOCATION",
    "EMAIL_ADDRESS",
    "US_PASSPORT",
    "US_DRIVER_LICENSE",
    "IBAN_CODE",
    "MEDICAL_LICENSE",
    "US_BANK_NUMBER",
    "NRP",
    # EXCLUDED: UK_NHS — 10-digit pattern causes false positives on log IDs/process IDs
]

# Minimum confidence to accept a Presidio result
MIN_SCORE = 0.6


def _try_load_presidio() -> AnalyzerEngine | None:
    """Attempt to load Presidio. Returns None if not installed."""
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        # Try to load spaCy model
        provider = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_md"}],
        })

        nlp_engine = provider.create_engine()
        engine = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
        logger.info("Presidio NER engine loaded successfully (spaCy en_core_web_md)")
        return engine

    except ImportError:
        logger.info("Presidio not installed — NER detector disabled. Install with: pip install veilchat[ner]")
        return None
    except OSError:
        # spaCy model not downloaded
        logger.warning(
            "spaCy model 'en_core_web_md' not found. "
            "Download it with: python -m spacy download en_core_web_md"
        )
        # Fall back to small model
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider

            provider = NlpEngineProvider(nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
            })
            nlp_engine = provider.create_engine()
            engine = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
            logger.info("Presidio NER engine loaded with fallback model (spaCy en_core_web_sm)")
            return engine
        except Exception:
            logger.warning("Could not load any spaCy model. NER detector disabled.")
            return None
    except Exception as e:
        logger.warning(f"Failed to load Presidio: {e}")
        return None


class PresidioDetector(BaseDetector):
    """Detects PII using Microsoft Presidio with spaCy NER backend.

    This detector excels at finding:
    - Person names (contextual, not pattern-based)
    - Organization names
    - Physical addresses / locations
    - Medical record numbers

    These are entities that regex alone cannot reliably detect.
    """

    def __init__(self, engine: AnalyzerEngine | None = None):
        self._engine = engine or _try_load_presidio()
        self._available = self._engine is not None

    @property
    def name(self) -> str:
        return "presidio"

    @property
    def is_available(self) -> bool:
        return self._available

    def detect(self, text: str) -> list[DetectedEntity]:
        if not self._available:
            return []

        try:
            results = self._engine.analyze(
                text=text,
                language="en",
                entities=PRESIDIO_ENTITIES,
                score_threshold=MIN_SCORE,
            )
        except Exception as e:
            logger.error(f"Presidio analysis failed: {e}")
            return []

        entities: list[DetectedEntity] = []
        for result in results:
            entity_type = ENTITY_MAP.get(result.entity_type)
            if not entity_type:
                continue

            value = text[result.start:result.end]

            # Skip very short matches (likely false positives)
            if len(value.strip()) < 2:
                continue

            # Skip absurdly long NER matches (e.g., file paths detected as PERSON)
            max_lengths = {"PERSON": 60, "ORGANIZATION": 100, "LOCATION": 100}
            max_len = max_lengths.get(entity_type)
            if max_len and len(value) > max_len:
                continue

            # Skip all-digit matches for PERSON/ORGANIZATION (process IDs, etc.)
            if entity_type in ("PERSON", "ORGANIZATION") and value.strip().isdigit():
                continue

            entities.append(DetectedEntity(
                entity_type=entity_type,
                value=value,
                start=result.start,
                end=result.end,
                confidence=result.score,
                detection_method="ner_model",
                entity_subtype=result.entity_type,  # Keep Presidio's original type
                metadata={"recognizer": result.recognition_metadata.get("recognizer_name", "unknown")
                          if result.recognition_metadata else {}},
            ))

        return entities


# Singleton — loaded once at import time
_default_engine: AnalyzerEngine | None = None
_engine_loaded = False


def get_presidio_detector() -> PresidioDetector:
    """Get a singleton PresidioDetector (lazy-loads the engine once)."""
    global _default_engine, _engine_loaded
    if not _engine_loaded:
        _default_engine = _try_load_presidio()
        _engine_loaded = True
    return PresidioDetector(engine=_default_engine)
