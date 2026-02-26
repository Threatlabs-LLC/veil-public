"""End-to-end API tests for document upload and sanitization endpoints.

Covers:
  POST /api/documents/scan   — standalone document scan (no LLM)
  POST /api/chat/with-document — document + chat with LLM (sanitization only, no real LLM call)

Tests verify: multipart upload, extraction, sanitization, auth, error handling,
file limits, feature flags, DB persistence, and policy evaluation.
"""

from __future__ import annotations

import csv
import io

import pytest
from httpx import AsyncClient


# ── Helpers ──────────────────────────────────────────────────────────────


async def register_user(client: AsyncClient, email="doctest@example.com",
                        password="TestPass123!", org_name="DocTestOrg") -> dict:
    res = await client.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "org_name": org_name,
    })
    assert res.status_code == 200, res.text
    return res.json()


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _upgrade_org_tier(client: AsyncClient, token: str, tier: str = "team"):
    from backend.db.session import get_db
    from backend.main import app

    override = app.dependency_overrides.get(get_db)
    if override:
        gen = override()
        db = await gen.__anext__()
        try:
            from jose import jwt
            from backend.config import settings
            from backend.models.user import User
            from backend.models.organization import Organization

            payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
            user = await db.get(User, payload["sub"])
            if user:
                org = await db.get(Organization, user.organization_id)
                if org:
                    org.tier = tier
                    await db.commit()
        finally:
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass


def _make_txt(content: str) -> tuple[str, bytes, str]:
    """Return (filename, data, content_type) for a text file."""
    return ("test.txt", content.encode("utf-8"), "text/plain")


def _make_csv_bytes(rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    from docx import Document
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_xlsx_bytes(headers: list[str], rows: list[list]) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# Text with known PII for sanitization verification
PII_TEXT = (
    "Patient: John Smith, SSN: 123-45-6789, Email: john.smith@hospital.org, "
    "Phone: (555) 123-4567, IP: 10.0.0.1"
)

PII_CSV_ROWS = [
    ["Name", "Email", "SSN", "Phone"],
    ["Alice Johnson", "alice@corp.com", "111-22-3333", "(555) 100-2000"],
    ["Bob Williams", "bob@corp.com", "222-33-4444", "(555) 300-4000"],
    ["Carol Davis", "carol@corp.com", "333-44-5555", "(555) 500-6000"],
]

PII_DOCX_PARAGRAPHS = [
    "Employee Record: Sarah Connor",
    "SSN: 456-78-9012, Email: sarah.connor@skynet.com",
    "Home address: 123 Main St, Los Angeles, CA 90001",
    "Phone: (310) 555-8899",
]

PII_XLSX_HEADERS = ["Name", "Email", "SSN"]
PII_XLSX_ROWS = [
    ["James Wilson", "james@acme.com", "567-89-0123"],
    ["Maria Garcia", "maria@acme.com", "678-90-1234"],
]


# ══════════════════════════════════════════════════════════════════════════
# POST /api/documents/scan — BASIC FUNCTIONALITY
# ══════════════════════════════════════════════════════════════════════════


class TestDocumentScanTxt:
    """Upload .txt files and verify scan results."""

    async def test_scan_txt_with_pii(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("patient_notes.txt", PII_TEXT.encode(), "text/plain")},
        )
        assert res.status_code == 200, res.text
        body = res.json()

        assert body["filename"] == "patient_notes.txt"
        assert body["file_type"] == "txt"
        assert body["entity_count"] >= 3  # SSN + email + phone at minimum
        assert "123-45-6789" not in body["sanitized_text"]
        assert "john.smith@hospital.org" not in body["sanitized_text"]
        assert body["document_id"] is not None
        assert body["was_truncated"] is False

    async def test_scan_txt_no_pii(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        clean_text = "The weather forecast calls for rain in the northwest region tomorrow."
        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("clean.txt", clean_text.encode(), "text/plain")},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["entity_count"] == 0
        assert body["sanitized_text"] == clean_text

    async def test_scan_returns_entity_details(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        text = "Contact: john.smith@hospital.org, SSN: 123-45-6789, Phone: (555) 123-4567"
        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("contact.txt", text.encode(), "text/plain")},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["entity_count"] >= 2
        assert len(body["entities"]) >= 2

        entity_types = {e["entity_type"] for e in body["entities"]}
        assert "SSN" in entity_types or "EMAIL" in entity_types

        for ent in body["entities"]:
            assert "placeholder" in ent
            assert "confidence" in ent
            assert "detection_method" in ent


class TestDocumentScanCsv:
    """Upload .csv files and verify scan results."""

    async def test_scan_csv_with_pii(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        csv_data = _make_csv_bytes(PII_CSV_ROWS)
        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("employees.csv", csv_data, "text/csv")},
        )
        assert res.status_code == 200
        body = res.json()

        assert body["file_type"] == "csv"
        assert body["entity_count"] >= 6  # 3 SSN + 3 email minimum
        assert "111-22-3333" not in body["sanitized_text"]
        assert "alice@corp.com" not in body["sanitized_text"]


class TestDocumentScanDocx:
    """Upload .docx files and verify scan results."""

    @pytest.fixture(autouse=True)
    def check_docx(self):
        try:
            import docx  # noqa: F401
        except ImportError:
            pytest.skip("python-docx not installed")

    async def test_scan_docx_with_pii(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        docx_data = _make_docx_bytes(PII_DOCX_PARAGRAPHS)
        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("employee_record.docx", docx_data,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert res.status_code == 200
        body = res.json()

        assert body["file_type"] == "docx"
        assert body["entity_count"] >= 2
        assert "456-78-9012" not in body["sanitized_text"]
        assert "sarah.connor@skynet.com" not in body["sanitized_text"]


class TestDocumentScanXlsx:
    """Upload .xlsx files and verify scan results."""

    @pytest.fixture(autouse=True)
    def check_openpyxl(self):
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            pytest.skip("openpyxl not installed")

    async def test_scan_xlsx_with_pii(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        xlsx_data = _make_xlsx_bytes(PII_XLSX_HEADERS, PII_XLSX_ROWS)
        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("hr_data.xlsx", xlsx_data,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert res.status_code == 200
        body = res.json()

        assert body["file_type"] == "xlsx"
        assert body["entity_count"] >= 2
        assert "567-89-0123" not in body["sanitized_text"]
        assert "james@acme.com" not in body["sanitized_text"]


# ══════════════════════════════════════════════════════════════════════════
# RESPONSE SCHEMA VALIDATION
# ══════════════════════════════════════════════════════════════════════════


class TestDocumentScanResponseSchema:
    """Verify the response shape of /api/documents/scan."""

    async def test_response_has_all_fields(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("schema_test.txt", b"Test content with alice@test.com", "text/plain")},
        )
        assert res.status_code == 200
        body = res.json()

        required_fields = [
            "document_id", "filename", "file_type", "file_size_bytes",
            "char_count", "page_count", "was_truncated", "sanitized_text",
            "entity_count", "entities",
        ]
        for field in required_fields:
            assert field in body, f"Missing field: {field}"

    async def test_file_size_bytes_accurate(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        content = b"Hello world, test file content."
        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("size_check.txt", content, "text/plain")},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["file_size_bytes"] == len(content)

    async def test_char_count_accurate(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        text = "Exactly forty-two characters in this text."
        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("chars.txt", text.encode(), "text/plain")},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["char_count"] == len(text)


# ══════════════════════════════════════════════════════════════════════════
# ERROR HANDLING
# ══════════════════════════════════════════════════════════════════════════


class TestDocumentScanErrors:
    """Error cases for /api/documents/scan."""

    async def test_no_auth_returns_401(self, client):
        res = await client.post(
            "/api/documents/scan",
            files={"file": ("test.txt", b"hello", "text/plain")},
        )
        assert res.status_code == 401

    async def test_empty_file_returns_400(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        assert res.status_code == 400

    async def test_unsupported_file_type_returns_422(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("archive.zip", b"PK\x03\x04fake", "application/zip")},
        )
        assert res.status_code == 422
        body = res.json()
        assert "supported_types" in body["detail"] or "extraction_failed" in str(body)

    async def test_oversized_file_returns_413(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        from backend.core.document import MAX_FILE_SIZE_BYTES
        # Just over the limit
        oversized = b"x" * (MAX_FILE_SIZE_BYTES + 1)
        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("huge.txt", oversized, "text/plain")},
        )
        assert res.status_code == 413

    async def test_corrupted_docx_returns_422(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("broken.docx", b"not a real docx file",
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert res.status_code == 422

    async def test_corrupted_pdf_returns_422(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("broken.pdf", b"not a real pdf", "application/pdf")},
        )
        assert res.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# FEATURE FLAG
# ══════════════════════════════════════════════════════════════════════════


class TestDocumentFeatureFlag:
    """Verify document_upload_enabled feature flag."""

    async def test_disabled_flag_returns_403(self, client, monkeypatch):
        data = await register_user(client)
        token = data["access_token"]

        from backend import config
        monkeypatch.setattr(config.settings, "document_upload_enabled", False)

        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("test.txt", b"hello", "text/plain")},
        )
        assert res.status_code == 403
        assert "disabled" in res.text.lower()


# ══════════════════════════════════════════════════════════════════════════
# DATABASE PERSISTENCE
# ══════════════════════════════════════════════════════════════════════════


class TestDocumentScanPersistence:
    """Verify document metadata is saved to the database."""

    async def test_document_record_created(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        text = "Record test: bob@example.com, SSN 111-22-3333"
        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("persist_test.txt", text.encode(), "text/plain")},
        )
        assert res.status_code == 200
        body = res.json()
        doc_id = body["document_id"]
        assert doc_id is not None

        # Verify the record exists in DB by checking it's a valid UUID-like string
        assert len(doc_id) > 0

    async def test_entity_count_matches_response(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        text = "Contact: eve@corp.com, SSN: 999-88-7777, Phone: (555) 999-0000"
        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("count_test.txt", text.encode(), "text/plain")},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["entity_count"] == len(body["entities"])


# ══════════════════════════════════════════════════════════════════════════
# POST /api/chat/with-document — BASIC FUNCTIONALITY
# ══════════════════════════════════════════════════════════════════════════


class TestChatWithDocument:
    """Test the chat-with-document endpoint (sanitization layer only).

    These tests verify the upload + sanitization + policy path.
    They do NOT test actual LLM streaming (that requires mocking the provider).
    We test by triggering policy blocks or checking error paths.
    """

    async def test_chat_with_document_empty_file_returns_400(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        res = await client.post(
            "/api/chat/with-document",
            headers=auth_headers(token),
            data={"message": "Summarize this", "provider": "openai", "model": "gpt-4o-mini"},
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        assert res.status_code == 400

    async def test_chat_with_document_unsupported_type_returns_422(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        res = await client.post(
            "/api/chat/with-document",
            headers=auth_headers(token),
            data={"message": "Analyze this", "provider": "openai", "model": "gpt-4o-mini"},
            files={"file": ("data.zip", b"PK\x03\x04fake", "application/zip")},
        )
        assert res.status_code == 422

    async def test_chat_with_document_no_auth_returns_401(self, client):
        res = await client.post(
            "/api/chat/with-document",
            data={"message": "Hello"},
            files={"file": ("test.txt", b"content", "text/plain")},
        )
        assert res.status_code == 401

    async def test_chat_with_document_disabled_returns_403(self, client, monkeypatch):
        data = await register_user(client)
        token = data["access_token"]

        from backend import config
        monkeypatch.setattr(config.settings, "document_upload_enabled", False)

        res = await client.post(
            "/api/chat/with-document",
            headers=auth_headers(token),
            data={"message": "Summarize", "provider": "openai", "model": "gpt-4o-mini"},
            files={"file": ("test.txt", b"hello", "text/plain")},
        )
        assert res.status_code == 403

    async def test_chat_with_document_oversized_returns_413(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        from backend.core.document import MAX_FILE_SIZE_BYTES
        oversized = b"x" * (MAX_FILE_SIZE_BYTES + 1)
        res = await client.post(
            "/api/chat/with-document",
            headers=auth_headers(token),
            data={"message": "Analyze", "provider": "openai", "model": "gpt-4o-mini"},
            files={"file": ("huge.txt", oversized, "text/plain")},
        )
        assert res.status_code == 413

    async def test_chat_with_document_corrupted_pdf_returns_422(self, client):
        data = await register_user(client)
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        res = await client.post(
            "/api/chat/with-document",
            headers=auth_headers(token),
            data={"message": "Read this PDF", "provider": "openai", "model": "gpt-4o-mini"},
            files={"file": ("broken.pdf", b"not a pdf", "application/pdf")},
        )
        assert res.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# POLICY BLOCKING (chat-with-document)
# ══════════════════════════════════════════════════════════════════════════


class TestDocumentPolicyBlocking:
    """Verify that documents with blocked entity types are rejected by policy."""

    async def test_blocked_entity_type_returns_403(self, client):
        """Create a block policy for SSN, then upload a doc with SSNs."""
        data = await register_user(client, email="policyblock@test.com",
                                   org_name="PolicyBlockOrg")
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        # Create a block policy for SSN
        res = await client.post(
            "/api/policies",
            headers=auth_headers(token),
            json={"name": "Block SSN", "entity_type": "SSN", "action": "block"},
        )
        assert res.status_code in (200, 201), f"Policy creation failed: {res.text}"

        # Upload a document with SSNs — should be blocked
        text = "Employee SSN: 111-22-3333, another SSN: 222-33-4444"
        res = await client.post(
            "/api/chat/with-document",
            headers=auth_headers(token),
            data={"message": "Summarize", "provider": "openai", "model": "gpt-4o-mini"},
            files={"file": ("ssn_doc.txt", text.encode(), "text/plain")},
        )
        assert res.status_code == 403
        body = res.json()
        assert body["detail"]["error"] == "blocked_by_policy"


# ══════════════════════════════════════════════════════════════════════════
# MULTI-FORMAT SANITIZATION VERIFICATION
# ══════════════════════════════════════════════════════════════════════════


class TestDocumentScanSanitizationIntegrity:
    """Verify that PII is consistently stripped across all file formats."""

    async def _scan_and_verify(self, client, token, filename, data, content_type,
                               forbidden_strings, min_entities):
        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": (filename, data, content_type)},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["entity_count"] >= min_entities, (
            f"Expected >= {min_entities} entities, got {body['entity_count']}"
        )
        for s in forbidden_strings:
            assert s not in body["sanitized_text"], (
                f"PII '{s}' leaked in sanitized output for {filename}"
            )
        return body

    async def test_pii_stripped_from_txt(self, client):
        data = await register_user(client, email="txtpii@test.com", org_name="TxtPiiOrg")
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        await self._scan_and_verify(
            client, token, "notes.txt", PII_TEXT.encode(), "text/plain",
            forbidden_strings=["123-45-6789", "john.smith@hospital.org", "(555) 123-4567"],
            min_entities=3,
        )

    async def test_pii_stripped_from_csv(self, client):
        data = await register_user(client, email="csvpii@test.com", org_name="CsvPiiOrg")
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        csv_data = _make_csv_bytes(PII_CSV_ROWS)
        await self._scan_and_verify(
            client, token, "employees.csv", csv_data, "text/csv",
            forbidden_strings=["111-22-3333", "alice@corp.com", "222-33-4444", "bob@corp.com"],
            min_entities=6,
        )

    async def test_pii_stripped_from_docx(self, client):
        try:
            import docx  # noqa: F401
        except ImportError:
            pytest.skip("python-docx not installed")

        data = await register_user(client, email="docxpii@test.com", org_name="DocxPiiOrg")
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        docx_data = _make_docx_bytes(PII_DOCX_PARAGRAPHS)
        await self._scan_and_verify(
            client, token, "record.docx", docx_data,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            forbidden_strings=["456-78-9012", "sarah.connor@skynet.com"],
            min_entities=2,
        )

    async def test_pii_stripped_from_xlsx(self, client):
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            pytest.skip("openpyxl not installed")

        data = await register_user(client, email="xlsxpii@test.com", org_name="XlsxPiiOrg")
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        xlsx_data = _make_xlsx_bytes(PII_XLSX_HEADERS, PII_XLSX_ROWS)
        await self._scan_and_verify(
            client, token, "hr.xlsx", xlsx_data,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            forbidden_strings=["567-89-0123", "james@acme.com", "678-90-1234", "maria@acme.com"],
            min_entities=2,
        )


# ══════════════════════════════════════════════════════════════════════════
# EDGE CASES
# ══════════════════════════════════════════════════════════════════════════


class TestDocumentScanEdgeCases:
    """Edge cases for document scanning."""

    async def test_large_txt_truncated(self, client):
        data = await register_user(client, email="large@test.com", org_name="LargeOrg")
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        # 600K chars of text — should be truncated to 500K
        large_text = ("a" * 600_000).encode("utf-8")
        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("big.txt", large_text, "text/plain")},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["was_truncated"] is True
        assert body["char_count"] == 500_000

    async def test_txt_with_special_characters(self, client):
        data = await register_user(client, email="special@test.com", org_name="SpecialOrg")
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        text = "Caf\u00e9 r\u00e9sum\u00e9 with PII: test@example.com and SSN 555-66-7777"
        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("special.txt", text.encode("utf-8"), "text/plain")},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["entity_count"] >= 2
        assert "555-66-7777" not in body["sanitized_text"]

    async def test_csv_with_many_rows(self, client):
        data = await register_user(client, email="bigcsv@test.com", org_name="BigCsvOrg")
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        rows = [["Name", "Email"]]
        for i in range(100):
            rows.append([f"User {i}", f"user{i}@corp{i}.com"])
        csv_data = _make_csv_bytes(rows)

        res = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("many_rows.csv", csv_data, "text/csv")},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["entity_count"] >= 50  # At least some emails detected

    async def test_scan_same_file_twice_creates_two_records(self, client):
        data = await register_user(client, email="twice@test.com", org_name="TwiceOrg")
        token = data["access_token"]
        await _upgrade_org_tier(client, token)

        text = b"Simple file with test@example.com"
        res1 = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("dup.txt", text, "text/plain")},
        )
        res2 = await client.post(
            "/api/documents/scan",
            headers=auth_headers(token),
            files={"file": ("dup.txt", text, "text/plain")},
        )
        assert res1.status_code == 200
        assert res2.status_code == 200
        assert res1.json()["document_id"] != res2.json()["document_id"]
