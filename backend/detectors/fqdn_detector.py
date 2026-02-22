"""FQDN detector — catches internal/infrastructure domain names using heuristics.

Uses confidence scoring to differentiate:
  - GS-WEF01.ad.calspan.com  -> 0.95 confidence (internal AD domain) -> redacted
  - staging.corp.acme.com     -> 0.95 confidence (.corp. indicator)   -> redacted
  - api.staging.mycompany.com -> 0.85 confidence (depth 4)            -> redacted
  - docs.google.com           -> 0.0  (depth 3, no signals)           -> ignored
  - calspan.com               -> 0.0  (depth 2, no signals)           -> ignored

The policy engine's min_confidence threshold (default 0.7) determines what gets
acted on. Low-confidence matches pass through untouched.
"""

from __future__ import annotations

import re

from backend.detectors.base import BaseDetector, DetectedEntity

# Subdomains that indicate internal/AD infrastructure — always sensitive
_INTERNAL_INDICATORS = frozenset({
    ".ad.", ".corp.", ".internal.", ".local.", ".lan.",
    ".intra.", ".priv.", ".home.", ".domain.", ".infra.",
    ".mgmt.", ".ilo.", ".oob.",
})

# Server/workstation naming pattern in the leftmost label:
# GS-WEF01, DC-PROD-03, SRV-APP01, WIN-ABC1234, etc.
_SERVER_NAME_RE = re.compile(
    r"^[A-Z]{2,5}[-_][A-Z0-9]",
    re.IGNORECASE,
)

# FQDN pattern: 2+ labels ending in a TLD (2-63 chars).
# Must have at least 3 labels total (x.y.tld) to be interesting.
_FQDN_RE = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.){2,}"
    r"[a-zA-Z]{2,63}\b"
)

# Skip FQDNs that are part of a URL (already caught by URL detector)
_URL_PREFIX_RE = re.compile(r"https?://", re.IGNORECASE)


class FQDNDetector(BaseDetector):
    """Detects FQDNs that likely represent internal infrastructure.

    Scoring heuristics:
      - .ad., .corp., .internal., etc. anywhere in the FQDN -> 0.95
      - Subdomain depth >= 4                                 -> 0.85
      - Server naming pattern (XX-XXXX) as hostname          -> 0.80
      - Depth 3 with no other signals                        -> 0.0 (skip)
    """

    @property
    def name(self) -> str:
        return "fqdn"

    def detect(self, text: str) -> list[DetectedEntity]:
        entities: list[DetectedEntity] = []

        for match in _FQDN_RE.finditer(text):
            fqdn = match.group(0)
            start = match.start()

            # Skip if this FQDN is part of a URL (let URL detector handle it)
            prefix_start = max(0, start - 10)
            if _URL_PREFIX_RE.search(text[prefix_start:start]):
                continue

            confidence = self._score(fqdn)
            if confidence < 0.5:
                continue  # Not interesting enough to report

            entities.append(DetectedEntity(
                entity_type="FQDN",
                value=fqdn,
                start=start,
                end=match.end(),
                confidence=confidence,
                detection_method="regex",
            ))

        return entities

    @staticmethod
    def _score(fqdn: str) -> float:
        """Score an FQDN based on how likely it is to be internal infrastructure."""
        lower = fqdn.lower()
        parts = lower.split(".")
        depth = len(parts)

        # Depth 2 (just "company.com") — never interesting on its own
        if depth <= 2:
            return 0.0

        score = 0.0

        # Check for internal subdomain indicators anywhere in the FQDN
        dotted = f".{lower}."
        for indicator in _INTERNAL_INDICATORS:
            if indicator in dotted:
                score = max(score, 0.95)
                break

        # Deep subdomains (4+ labels) are very likely internal
        if depth >= 4:
            score = max(score, 0.85)

        # Server naming pattern in the leftmost label
        if _SERVER_NAME_RE.match(parts[0]):
            if depth >= 3:
                score = max(score, 0.90)
            else:
                score = max(score, 0.80)

        # Depth 3 with no other signals — skip (docs.google.com, cdn.cloudflare.com)
        if depth == 3 and score < 0.5:
            return 0.0

        return score
