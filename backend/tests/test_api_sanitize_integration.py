"""Full-stack API integration tests for POST /api/sanitize.

Unlike test_sanitization_comprehensive.py (which calls sanitizer.sanitize() directly
with regex-only detection), these tests exercise the real HTTP endpoint:
  auth → detector registry (regex + NER + custom rules) → overlap resolution
  → sanitization → audit logging → response serialization.

Each test class corresponds to one testdata file. Every known PII value is checked
to ensure it does NOT appear in the sanitized output.
"""

from pathlib import Path

import pytest
from httpx import AsyncClient

TESTDATA_DIR = Path(__file__).parent / "testdata"


# ── Helpers ──────────────────────────────────────────────────────────────


def _load(filename: str) -> str:
    return (TESTDATA_DIR / filename).read_text(encoding="utf-8")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register(client: AsyncClient, suffix: str) -> str:
    """Register a unique user and return the access token."""
    res = await client.post("/api/auth/register", json={
        "email": f"integ-{suffix}@test.com",
        "password": "TestPass123!",
        "org_name": f"IntegOrg-{suffix}",
    })
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


async def _sanitize(client: AsyncClient, token: str, text: str) -> dict:
    """POST /api/sanitize and return the parsed response."""
    res = await client.post(
        "/api/sanitize",
        headers=_auth(token),
        json={"text": text, "return_original": True},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _entity_types(resp: dict) -> set[str]:
    return {e["entity_type"] for e in resp["entities"]}


def _assert_none_leaked(sanitized_text: str, pii_values: list[str], label: str = ""):
    """Assert that NONE of the raw PII values appear in the sanitized output."""
    for val in pii_values:
        assert val not in sanitized_text, (
            f"PII leak{f' ({label})' if label else ''}: '{val}' found in sanitized output"
        )


# ══════════════════════════════════════════════════════════════════════════
# HEALTHCARE
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestAPIHealthcare:
    """POST /api/sanitize with healthcare_notes.txt — full-stack PII leak check."""

    PII_VALUES = [
        # SSN
        "287-65-4321",
        # Emails
        "david.thompson@outlook.com",
        "amfoster@nwmedical.org",
        # Phones
        "(206) 555-8743",
        "425-555-9012",
        # Credit card
        "4532 0151 1283 0366",
        # URL
        "https://portal.nwmedical.org/patient/margaret.thompson",
    ]

    EXPECTED_TYPES = {"SSN", "EMAIL", "PHONE", "CREDIT_CARD", "URL"}

    async def test_no_pii_leaks(self, client):
        token = await _register(client, "hc-leak")
        resp = await _sanitize(client, token, _load("healthcare_notes.txt"))
        _assert_none_leaked(resp["sanitized_text"], self.PII_VALUES, "healthcare")

    async def test_entity_types_detected(self, client):
        token = await _register(client, "hc-types")
        resp = await _sanitize(client, token, _load("healthcare_notes.txt"))
        detected = _entity_types(resp)
        for etype in self.EXPECTED_TYPES:
            assert etype in detected, f"Missing entity type: {etype}"

    async def test_entity_count(self, client):
        token = await _register(client, "hc-count")
        resp = await _sanitize(client, token, _load("healthcare_notes.txt"))
        assert resp["entity_count"] >= 7, (
            f"Expected >= 7 entities, got {resp['entity_count']}"
        )


# ══════════════════════════════════════════════════════════════════════════
# FINANCE
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestAPIFinance:
    """POST /api/sanitize with finance_report.txt — full-stack PII leak check."""

    PII_VALUES = [
        # SSNs
        "412-78-9034",
        "531-22-8876",
        # Emails
        "j.richardson@acmecorp.com",
        "lisa.park@microsoft.com",
        "knguyen@amazon.com",
        "sarah.kim@acmecorp.com",
        "michael.obrien@acmecorp.com",
        "robert.f@apexsolutions.io",
        "achen@venturegroup.com",
        # Phones
        "(206) 266-1000",
        "(425) 882-8080",
        "(212) 555-0147",
        # Credit cards
        "3782 822463 10005",
        "4916 3388 1100 7722",
        # Routing number
        "021000021",
        # IBAN
        "DE89370400440532013000",
        # IP
        "10.42.8.100",
        # API key
        "sk_live_4eC39HqLyjWDarjtT1zdp7dc",
        # Connection string password
        "Kx9$mPq2vL",
    ]

    EXPECTED_TYPES = {
        "SSN", "EMAIL", "PHONE", "CREDIT_CARD",
        "ROUTING_NUMBER", "IBAN", "IP_ADDRESS",
    }

    async def test_no_pii_leaks(self, client):
        token = await _register(client, "fin-leak")
        resp = await _sanitize(client, token, _load("finance_report.txt"))
        _assert_none_leaked(resp["sanitized_text"], self.PII_VALUES, "finance")

    async def test_entity_types_detected(self, client):
        token = await _register(client, "fin-types")
        resp = await _sanitize(client, token, _load("finance_report.txt"))
        detected = _entity_types(resp)
        for etype in self.EXPECTED_TYPES:
            assert etype in detected, f"Missing entity type: {etype}"

    async def test_entity_count(self, client):
        token = await _register(client, "fin-count")
        resp = await _sanitize(client, token, _load("finance_report.txt"))
        assert resp["entity_count"] >= 20, (
            f"Expected >= 20 entities, got {resp['entity_count']}"
        )


# ══════════════════════════════════════════════════════════════════════════
# LEGAL
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestAPILegal:
    """POST /api/sanitize with legal_contract.txt — full-stack PII leak check."""

    PII_VALUES = [
        # SSN
        "478-92-1034",
        # EINs
        "84-3298471",
        "95-4872103",
        # Emails
        "cory.brown@threatlabs.tech",
        "p.dominguez@meridianhcs.com",
        "j.whitfield@meridianhcs.com",
        "security@meridianhcs.com",
        "accounts@threatlabs.tech",
        "tadeyemi@legalteam.com",
        # Phones
        "(512) 555-3847",
        "(310) 555-2190",
        "(213) 555-7823",
        # Routing number
        "121140399",
        # Bank account
        "3300194827",
        # Driver's license
        "D4829103",
    ]

    EXPECTED_TYPES = {"SSN", "EMAIL", "PHONE", "ROUTING_NUMBER"}

    async def test_no_pii_leaks(self, client):
        token = await _register(client, "legal-leak")
        resp = await _sanitize(client, token, _load("legal_contract.txt"))
        _assert_none_leaked(resp["sanitized_text"], self.PII_VALUES, "legal")

    async def test_entity_types_detected(self, client):
        token = await _register(client, "legal-types")
        resp = await _sanitize(client, token, _load("legal_contract.txt"))
        detected = _entity_types(resp)
        for etype in self.EXPECTED_TYPES:
            assert etype in detected, f"Missing entity type: {etype}"

    async def test_entity_count(self, client):
        token = await _register(client, "legal-count")
        resp = await _sanitize(client, token, _load("legal_contract.txt"))
        assert resp["entity_count"] >= 15, (
            f"Expected >= 15 entities, got {resp['entity_count']}"
        )


# ══════════════════════════════════════════════════════════════════════════
# HR RECORDS (CSV)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestAPIHRRecords:
    """POST /api/sanitize with hr_records.csv — full-stack PII leak check."""

    PII_VALUES = [
        # SSNs (all 8 employees)
        "234-56-7890",
        "345-67-8901",
        "456-78-9012",
        "567-89-0123",
        "678-90-1234",
        "789-01-2345",
        "890-12-3456",
        "901-23-4567",
        # Emails
        "j.martinez@globaltech.com",
        "d.okonkwo@globaltech.com",
        "p.patel@globaltech.com",
        "t.andersen@globaltech.com",
        "a.rahman@globaltech.com",
        "c.lee@globaltech.com",
        "e.volkov@globaltech.com",
        "m.johnson@globaltech.com",
        # Phones
        "(415) 555-1234",
        "(415) 555-2345",
        "(650) 555-3456",
        "(408) 555-4567",
        "(925) 555-5678",
        "(415) 555-6789",
        "(510) 555-7890",
        "(650) 555-8901",
    ]

    EXPECTED_TYPES = {"SSN", "EMAIL", "PHONE"}

    async def test_no_pii_leaks(self, client):
        token = await _register(client, "hr-leak")
        resp = await _sanitize(client, token, _load("hr_records.csv"))
        _assert_none_leaked(resp["sanitized_text"], self.PII_VALUES, "hr")

    async def test_entity_types_detected(self, client):
        token = await _register(client, "hr-types")
        resp = await _sanitize(client, token, _load("hr_records.csv"))
        detected = _entity_types(resp)
        for etype in self.EXPECTED_TYPES:
            assert etype in detected, f"Missing entity type: {etype}"

    async def test_entity_count(self, client):
        token = await _register(client, "hr-count")
        resp = await _sanitize(client, token, _load("hr_records.csv"))
        assert resp["entity_count"] >= 24, (
            f"Expected >= 24 entities, got {resp['entity_count']}"
        )


# ══════════════════════════════════════════════════════════════════════════
# FIREWALL LOGS
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestAPIFirewallLogs:
    """POST /api/sanitize with firewall_logs.txt — full-stack PII leak check."""

    PII_VALUES = [
        # IPs
        "192.168.10.45",
        "192.168.10.82",
        "203.0.113.42",
        "192.168.10.120",
        "104.18.32.47",
        "10.200.50.100",
        "10.200.50.200",
        "10.0.1.50",
        "10.42.8.100",
        "142.250.80.109",
        # Emails
        "spatek@acmeinc.com",
        "sarah.kim@acmeinc.com",
    ]

    EXPECTED_TYPES = {"IP_ADDRESS", "EMAIL"}

    async def test_no_pii_leaks(self, client):
        token = await _register(client, "fw-leak")
        resp = await _sanitize(client, token, _load("firewall_logs.txt"))
        _assert_none_leaked(resp["sanitized_text"], self.PII_VALUES, "firewall")

    async def test_entity_types_detected(self, client):
        token = await _register(client, "fw-types")
        resp = await _sanitize(client, token, _load("firewall_logs.txt"))
        detected = _entity_types(resp)
        for etype in self.EXPECTED_TYPES:
            assert etype in detected, f"Missing entity type: {etype}"

    async def test_entity_count(self, client):
        token = await _register(client, "fw-count")
        resp = await _sanitize(client, token, _load("firewall_logs.txt"))
        assert resp["entity_count"] >= 10, (
            f"Expected >= 10 entities, got {resp['entity_count']}"
        )


# ══════════════════════════════════════════════════════════════════════════
# TECH SUPPORT
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestAPITechSupport:
    """POST /api/sanitize with tech_support.txt — full-stack PII leak check."""

    PII_VALUES = [
        # Emails
        "rachel.green@westfieldagency.com",
        "alex.nakamura@supportteam.io",
        "admin@westfieldagency.com",
        "spark@supportteam.io",
        "dkim@supportteam.io",
        "accounting@westfieldagency.com",
        # Phones
        "(312) 555-4829",
        "(415) 555-7723",
        # IP
        "52.14.182.93",
        # MAC address
        "00:1A:2B:3C:4D:5E",
        # Credit card
        "5425 2334 3010 9903",
        # AWS key
        "AKIAIOSFODNN7EXAMPLE",
        # AWS account ID
        "123456789012",
        # Connection string passwords
        "Tr0ub4dor&3",
        "s3cr3tP@ss",
    ]

    EXPECTED_TYPES = {
        "EMAIL", "PHONE", "IP_ADDRESS", "MAC_ADDRESS",
        "CREDIT_CARD", "API_KEY",
    }

    async def test_no_pii_leaks(self, client):
        token = await _register(client, "ts-leak")
        resp = await _sanitize(client, token, _load("tech_support.txt"))
        _assert_none_leaked(resp["sanitized_text"], self.PII_VALUES, "tech_support")

    async def test_entity_types_detected(self, client):
        token = await _register(client, "ts-types")
        resp = await _sanitize(client, token, _load("tech_support.txt"))
        detected = _entity_types(resp)
        for etype in self.EXPECTED_TYPES:
            assert etype in detected, f"Missing entity type: {etype}"

    async def test_entity_count(self, client):
        token = await _register(client, "ts-count")
        resp = await _sanitize(client, token, _load("tech_support.txt"))
        assert resp["entity_count"] >= 15, (
            f"Expected >= 15 entities, got {resp['entity_count']}"
        )


# ══════════════════════════════════════════════════════════════════════════
# CROSS-FILE: RESPONSE SCHEMA VALIDATION
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestAPISanitizeResponseSchema:
    """Verify the response structure matches SanitizeResponse for all files."""

    FILES = [
        "healthcare_notes.txt",
        "finance_report.txt",
        "legal_contract.txt",
        "hr_records.csv",
        "firewall_logs.txt",
        "tech_support.txt",
    ]

    async def test_response_schema(self, client):
        token = await _register(client, "schema")
        for filename in self.FILES:
            resp = await _sanitize(client, token, _load(filename))
            # Top-level fields
            assert "sanitized_text" in resp, f"{filename}: missing sanitized_text"
            assert "entity_count" in resp, f"{filename}: missing entity_count"
            assert "entities" in resp, f"{filename}: missing entities"
            assert "processing_ms" in resp, f"{filename}: missing processing_ms"
            assert isinstance(resp["entities"], list)
            assert resp["entity_count"] == len(resp["entities"])
            # Entity structure
            for ent in resp["entities"]:
                assert "entity_type" in ent
                assert "placeholder" in ent
                assert "start" in ent
                assert "end" in ent
                assert "confidence" in ent
                assert "detection_method" in ent

    async def test_return_original_includes_values(self, client):
        """With return_original=True and owner role, original_value is populated."""
        token = await _register(client, "origval")
        resp = await _sanitize(client, token, _load("healthcare_notes.txt"))
        has_original = any(
            e.get("original_value") is not None for e in resp["entities"]
        )
        assert has_original, "return_original=True should populate original_value for owner"
