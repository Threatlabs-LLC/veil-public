"""Entity normalization — ensures variant spellings map to the same placeholder.

Examples:
  - "John Smith" and "JOHN SMITH" → "john smith"
  - "john.smith@Acme.com" and "JOHN.SMITH@acme.com" → "john.smith@acme.com"
  - "(555) 123-4567" and "555-123-4567" → "5551234567"
  - "192.168.1.1" → "192.168.1.1" (IPs are already normalized)
"""

import re

# Name particles to strip during normalization
NAME_PARTICLES = {"van", "von", "de", "del", "di", "da", "el", "al", "le", "la", "du", "des"}


def normalize_entity(entity_type: str, value: str) -> str:
    """Normalize an entity value for deduplication lookup."""
    normalizer = NORMALIZERS.get(entity_type, _normalize_default)
    return normalizer(value)


def _normalize_default(value: str) -> str:
    return value.strip().lower()


def _normalize_person(value: str) -> str:
    """Normalize person names: lowercase, strip particles, sort remaining parts."""
    name = value.strip().lower()
    # Remove common titles
    name = re.sub(r"\b(mr|mrs|ms|dr|prof|sir|jr|sr|ii|iii|iv)\.?\b", "", name, flags=re.IGNORECASE)
    parts = name.split()
    # Remove name particles for normalization
    parts = [p for p in parts if p not in NAME_PARTICLES]
    # Sort remaining parts (handles "Smith John" vs "John Smith")
    parts.sort()
    return " ".join(parts).strip()


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _normalize_phone(value: str) -> str:
    """Strip all formatting, keep only digits and leading +."""
    stripped = re.sub(r"[^\d+]", "", value)
    # Remove leading +1 for US numbers to normalize
    if stripped.startswith("+1") and len(stripped) == 12:
        stripped = stripped[2:]
    elif stripped.startswith("1") and len(stripped) == 11:
        stripped = stripped[1:]
    return stripped


def _normalize_ip(value: str) -> str:
    return value.strip()


def _normalize_credit_card(value: str) -> str:
    return re.sub(r"[\s\-]", "", value)


def _normalize_ssn(value: str) -> str:
    return re.sub(r"[\s\-]", "", value)


def _normalize_url(value: str) -> str:
    url = value.strip().lower()
    # Remove trailing slash for consistency
    return url.rstrip("/")


def _normalize_mac(value: str) -> str:
    return re.sub(r"[\-:]", ":", value.strip().lower())


NORMALIZERS = {
    "PERSON": _normalize_person,
    "EMAIL": _normalize_email,
    "PHONE": _normalize_phone,
    "IP_ADDRESS": _normalize_ip,
    "CREDIT_CARD": _normalize_credit_card,
    "SSN": _normalize_ssn,
    "URL": _normalize_url,
    "HOSTNAME": _normalize_default,
    "MAC_ADDRESS": _normalize_mac,
    "API_KEY": _normalize_default,
    "SECRET": _normalize_default,
    "CONNECTION_STRING": _normalize_default,
    "ORGANIZATION": _normalize_default,
    "ADDRESS": _normalize_default,
}
