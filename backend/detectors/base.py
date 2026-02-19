"""Abstract base for all entity detectors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DetectedEntity:
    """A single detected sensitive entity in text."""

    entity_type: str  # PERSON, IP_ADDRESS, EMAIL, etc.
    value: str  # The matched text
    start: int  # Start position in original text
    end: int  # End position in original text
    confidence: float = 1.0  # 0.0 to 1.0
    detection_method: str = "regex"
    entity_subtype: str | None = None  # e.g., "VISA" for credit cards
    metadata: dict = field(default_factory=dict)

    @property
    def span(self) -> tuple[int, int]:
        return (self.start, self.end)


class BaseDetector(ABC):
    """Abstract base class for entity detectors."""

    @abstractmethod
    def detect(self, text: str) -> list[DetectedEntity]:
        """Scan text and return all detected entities."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this detector."""
        ...
