"""Unit tests for core sanitization — normalizer, mapper, sanitizer, rehydrator."""

import json


from backend.core.normalizer import normalize_entity
from backend.core.mapper import EntityMapper
from backend.core.rehydrator import Rehydrator
from backend.core.sanitizer import Sanitizer
from backend.detectors.regex_detector import RegexDetector
from backend.detectors.registry import DetectorRegistry


# ── Normalizer ─────────────────────────────────────────────────────────


class TestNormalizerPerson:
    def test_case_insensitive(self):
        assert normalize_entity("PERSON", "John Smith") == normalize_entity("PERSON", "JOHN SMITH")

    def test_order_insensitive(self):
        assert normalize_entity("PERSON", "Smith John") == normalize_entity("PERSON", "John Smith")

    def test_strips_titles(self):
        norm = normalize_entity("PERSON", "Dr. John Smith")
        assert "dr" not in norm
        assert "john" in norm
        assert "smith" in norm

    def test_strips_particles(self):
        # "van" is a particle and gets stripped
        norm = normalize_entity("PERSON", "Ludwig van Beethoven")
        assert "van" not in norm.split()

    def test_empty_name(self):
        assert normalize_entity("PERSON", "  ") == ""


class TestNormalizerEmail:
    def test_lowercased(self):
        assert normalize_entity("EMAIL", "John@Example.COM") == "john@example.com"

    def test_stripped(self):
        assert normalize_entity("EMAIL", " alice@corp.com ") == "alice@corp.com"


class TestNormalizerPhone:
    def test_strips_formatting(self):
        assert normalize_entity("PHONE", "(555) 123-4567") == "5551234567"

    def test_strips_us_country_code(self):
        assert normalize_entity("PHONE", "+1-555-123-4567") == "5551234567"

    def test_strips_leading_1(self):
        assert normalize_entity("PHONE", "15551234567") == "5551234567"


class TestNormalizerIP:
    def test_strips_whitespace(self):
        assert normalize_entity("IP_ADDRESS", " 192.168.1.1 ") == "192.168.1.1"


class TestNormalizerCreditCard:
    def test_strips_spaces(self):
        assert normalize_entity("CREDIT_CARD", "4532 0151 1283 0366") == "4532015112830366"

    def test_strips_dashes(self):
        assert normalize_entity("CREDIT_CARD", "4532-0151-1283-0366") == "4532015112830366"


class TestNormalizerSSN:
    def test_strips_dashes(self):
        assert normalize_entity("SSN", "123-45-6789") == "123456789"


class TestNormalizerURL:
    def test_lowercase_and_strip_slash(self):
        assert normalize_entity("URL", "HTTPS://Example.COM/Path/") == "https://example.com/path"


class TestNormalizerMAC:
    def test_colon_format(self):
        assert normalize_entity("MAC_ADDRESS", "00:1A:2B:3C:4D:5E") == "00:1a:2b:3c:4d:5e"

    def test_dash_to_colon(self):
        assert normalize_entity("MAC_ADDRESS", "00-1A-2B-3C-4D-5E") == "00:1a:2b:3c:4d:5e"


class TestNormalizerDefault:
    def test_unknown_type_lowercased(self):
        assert normalize_entity("UNKNOWN_TYPE", " Hello World ") == "hello world"


# ── Entity Mapper ──────────────────────────────────────────────────────


class TestEntityMapper:
    def test_creates_placeholder(self):
        mapper = EntityMapper(session_id="test-session")
        mapped = mapper.get_or_create_placeholder(
            entity_type="EMAIL",
            original_value="john@example.com",
        )
        assert mapped.placeholder == "EMAIL_001"
        assert mapped.entity_type == "EMAIL"
        assert mapped.original_value == "john@example.com"

    def test_same_entity_same_placeholder(self):
        mapper = EntityMapper(session_id="test-session")
        m1 = mapper.get_or_create_placeholder("EMAIL", "john@example.com")
        m2 = mapper.get_or_create_placeholder("EMAIL", "john@example.com")
        assert m1.placeholder == m2.placeholder == "EMAIL_001"

    def test_normalized_dedup(self):
        """Different casings of the same email should map to the same placeholder."""
        mapper = EntityMapper(session_id="test-session")
        m1 = mapper.get_or_create_placeholder("EMAIL", "John@Example.COM")
        m2 = mapper.get_or_create_placeholder("EMAIL", "john@example.com")
        assert m1.placeholder == m2.placeholder

    def test_different_entities_different_placeholders(self):
        mapper = EntityMapper(session_id="test-session")
        m1 = mapper.get_or_create_placeholder("EMAIL", "alice@corp.com")
        m2 = mapper.get_or_create_placeholder("EMAIL", "bob@corp.com")
        assert m1.placeholder == "EMAIL_001"
        assert m2.placeholder == "EMAIL_002"

    def test_different_types_separate_counters(self):
        mapper = EntityMapper(session_id="test-session")
        e = mapper.get_or_create_placeholder("EMAIL", "a@b.com")
        p = mapper.get_or_create_placeholder("PHONE", "555-1234")
        assert e.placeholder == "EMAIL_001"
        assert p.placeholder == "PHONE_001"

    def test_reverse_lookup(self):
        mapper = EntityMapper(session_id="test-session")
        mapper.get_or_create_placeholder("EMAIL", "john@example.com")
        assert mapper.lookup_placeholder("EMAIL_001") == "john@example.com"

    def test_reverse_lookup_missing(self):
        mapper = EntityMapper(session_id="test-session")
        assert mapper.lookup_placeholder("NOPE_001") is None

    def test_get_all_placeholders(self):
        mapper = EntityMapper(session_id="test-session")
        mapper.get_or_create_placeholder("EMAIL", "a@b.com")
        mapper.get_or_create_placeholder("PHONE", "555-1234")
        all_ph = mapper.get_all_placeholders()
        assert len(all_ph) == 2
        assert "EMAIL_001" in all_ph
        assert "PHONE_001" in all_ph

    def test_counter_state_json(self):
        mapper = EntityMapper(session_id="test-session")
        mapper.get_or_create_placeholder("EMAIL", "a@b.com")
        mapper.get_or_create_placeholder("EMAIL", "b@c.com")
        mapper.get_or_create_placeholder("PHONE", "555-1234")
        state = json.loads(mapper.get_counter_state_json())
        assert state == {"EMAIL": 2, "PHONE": 1}

    def test_from_db_state(self):
        """Reconstructed mapper should continue from saved state."""
        mapper = EntityMapper(session_id="s1")
        mapper.get_or_create_placeholder("EMAIL", "a@b.com")
        mapper.get_or_create_placeholder("EMAIL", "c@d.com")

        counter_json = mapper.get_counter_state_json()
        existing = [
            {"entity_type": "EMAIL", "original_value": "a@b.com", "placeholder": "EMAIL_001"},
            {"entity_type": "EMAIL", "original_value": "c@d.com", "placeholder": "EMAIL_002"},
        ]

        restored = EntityMapper.from_db_state("s1", counter_json, existing)
        # Existing entity should get same placeholder
        m = restored.get_or_create_placeholder("EMAIL", "a@b.com")
        assert m.placeholder == "EMAIL_001"
        # New entity should get next counter
        m2 = restored.get_or_create_placeholder("EMAIL", "new@e.com")
        assert m2.placeholder == "EMAIL_003"

    def test_entities_list(self):
        mapper = EntityMapper(session_id="test")
        mapper.get_or_create_placeholder("EMAIL", "a@b.com")
        mapper.get_or_create_placeholder("PHONE", "555-1234")
        assert len(mapper.entities) == 2

    def test_position_tracking(self):
        mapper = EntityMapper(session_id="test")
        m = mapper.get_or_create_placeholder(
            "EMAIL", "a@b.com", start=10, end=17
        )
        assert m.start == 10
        assert m.end == 17


# ── Rehydrator ─────────────────────────────────────────────────────────


class TestRehydrator:
    def _make_rehydrator(self, mappings: dict[str, str]) -> Rehydrator:
        mapper = EntityMapper(session_id="test")
        for placeholder, original in mappings.items():
            # Manually populate reverse map
            mapper._reverse[placeholder] = original
        return Rehydrator(mapper=mapper)

    def test_rehydrate_single(self):
        rh = self._make_rehydrator({"EMAIL_001": "john@example.com"})
        result = rh.rehydrate("Hello EMAIL_001, welcome!")
        assert result == "Hello john@example.com, welcome!"

    def test_rehydrate_multiple(self):
        rh = self._make_rehydrator({
            "EMAIL_001": "john@example.com",
            "PHONE_001": "(555) 123-4567",
        })
        result = rh.rehydrate("Contact EMAIL_001 at PHONE_001")
        assert result == "Contact john@example.com at (555) 123-4567"

    def test_rehydrate_unknown_placeholder_redacted(self):
        rh = self._make_rehydrator({"EMAIL_001": "john@example.com"})
        result = rh.rehydrate("Hello UNKNOWN_001")
        assert result == "Hello [REDACTED]"

    def test_rehydrate_no_placeholders(self):
        rh = self._make_rehydrator({})
        result = rh.rehydrate("Just normal text here.")
        assert result == "Just normal text here."

    def test_rehydrate_empty_string(self):
        rh = self._make_rehydrator({})
        assert rh.rehydrate("") == ""

    def test_rehydrate_preserves_surrounding_text(self):
        rh = self._make_rehydrator({"IP_ADDRESS_001": "10.0.0.1"})
        result = rh.rehydrate("Server IP_ADDRESS_001 is down (check logs)")
        assert result == "Server 10.0.0.1 is down (check logs)"


class TestRehydratorStreaming:
    def _make_rehydrator(self, mappings: dict[str, str]) -> Rehydrator:
        mapper = EntityMapper(session_id="test")
        for placeholder, original in mappings.items():
            mapper._reverse[placeholder] = original
        return Rehydrator(mapper=mapper)

    def test_streaming_complete_placeholder(self):
        rh = self._make_rehydrator({"EMAIL_001": "john@example.com"})
        safe, remaining = rh.rehydrate_streaming("Hello EMAIL_001 how are you")
        # The full placeholder is in the middle, not at the end, so it should be rehydrated
        assert "john@example.com" in safe
        assert remaining == ""

    def test_streaming_partial_placeholder_held(self):
        rh = self._make_rehydrator({"EMAIL_001": "john@example.com"})
        safe, remaining = rh.rehydrate_streaming("Hello EMAIL")
        # "EMAIL" at the end looks like it could be the start of a placeholder
        assert "EMAIL" not in safe
        assert "EMAIL" in remaining

    def test_streaming_partial_with_underscore(self):
        rh = self._make_rehydrator({"EMAIL_001": "john@example.com"})
        safe, remaining = rh.rehydrate_streaming("Hello EMAIL_00")
        assert "EMAIL_00" in remaining

    def test_streaming_accumulate_and_complete(self):
        """Simulate two chunks that together form a complete placeholder."""
        rh = self._make_rehydrator({"PHONE_001": "(555) 123-4567"})
        # First chunk: partial
        safe1, buf = rh.rehydrate_streaming("Call PHONE")
        assert buf  # should hold back PHONE

        # Second chunk completes it
        safe2, buf2 = rh.rehydrate_streaming(buf + "_001 soon")
        assert "(555) 123-4567" in safe2
        assert buf2 == ""

    def test_streaming_no_placeholder(self):
        rh = self._make_rehydrator({})
        safe, remaining = rh.rehydrate_streaming("Just normal text here")
        assert safe == "Just normal text here"
        assert remaining == ""


# ── Sanitizer Pipeline ─────────────────────────────────────────────────


class TestSanitizer:
    def _make_sanitizer(self) -> Sanitizer:
        registry = DetectorRegistry()
        registry.register(RegexDetector())
        mapper = EntityMapper(session_id="test")
        return Sanitizer(registry=registry, mapper=mapper)

    def test_sanitize_email(self):
        s = self._make_sanitizer()
        result = s.sanitize("Contact john@example.com please")
        assert "john@example.com" not in result.sanitized_text
        assert "EMAIL_001" in result.sanitized_text
        assert result.entity_count == 1
        assert result.entities[0].entity_type == "EMAIL"
        assert result.entities[0].original_value == "john@example.com"

    def test_sanitize_preserves_non_pii(self):
        s = self._make_sanitizer()
        result = s.sanitize("Hello world, how are you?")
        assert result.sanitized_text == "Hello world, how are you?"
        assert result.entity_count == 0

    def test_sanitize_multiple_entities(self):
        s = self._make_sanitizer()
        text = "Email alice@corp.com from 192.168.1.50"
        result = s.sanitize(text)
        assert "alice@corp.com" not in result.sanitized_text
        assert "192.168.1.50" not in result.sanitized_text
        assert result.entity_count >= 2

    def test_sanitize_same_entity_twice(self):
        s = self._make_sanitizer()
        text = "Send to john@acme.com and CC john@acme.com"
        result = s.sanitize(text)
        # Both occurrences should get the same placeholder
        assert result.sanitized_text.count("EMAIL_001") == 2
        assert "john@acme.com" not in result.sanitized_text

    def test_sanitize_empty_string(self):
        s = self._make_sanitizer()
        result = s.sanitize("")
        assert result.sanitized_text == ""
        assert result.entity_count == 0

    def test_sanitize_to_dict(self):
        s = self._make_sanitizer()
        result = s.sanitize("Email: test@example.com")
        d = result.to_dict()
        assert "original_text" in d
        assert "sanitized_text" in d
        assert "entities" in d
        assert len(d["entities"]) == 1
        assert d["entities"][0]["entity_type"] == "EMAIL"

    def test_sanitize_position_correct(self):
        s = self._make_sanitizer()
        text = "Hello test@example.com goodbye"
        result = s.sanitize(text)
        assert result.sanitized_text.startswith("Hello ")
        assert result.sanitized_text.endswith(" goodbye")

    def test_roundtrip_sanitize_rehydrate(self):
        """Full roundtrip: sanitize → rehydrate should recover original values."""
        registry = DetectorRegistry()
        registry.register(RegexDetector())
        mapper = EntityMapper(session_id="test")
        sanitizer = Sanitizer(registry=registry, mapper=mapper)
        rehydrator = Rehydrator(mapper=mapper)

        original = "Contact john@example.com at 192.168.1.50"
        sanitized = sanitizer.sanitize(original)
        rehydrated = rehydrator.rehydrate(sanitized.sanitized_text)

        assert "john@example.com" in rehydrated
        assert "192.168.1.50" in rehydrated

    def test_roundtrip_preserves_structure(self):
        """Rehydrated text should have the same structure as original."""
        registry = DetectorRegistry()
        registry.register(RegexDetector())
        mapper = EntityMapper(session_id="test")
        sanitizer = Sanitizer(registry=registry, mapper=mapper)
        rehydrator = Rehydrator(mapper=mapper)

        original = "Dear john@example.com, your IP is 10.0.0.1. Thanks!"
        sanitized = sanitizer.sanitize(original)
        rehydrated = rehydrator.rehydrate(sanitized.sanitized_text)

        assert rehydrated == original
