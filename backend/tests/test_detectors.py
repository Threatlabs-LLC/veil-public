"""Unit tests for the detection pipeline — regex patterns, custom rules, registry."""

import json

import pytest

from backend.detectors.base import DetectedEntity
from backend.detectors.regex_detector import RegexDetector, _luhn_check, _is_valid_ip
from backend.detectors.registry import DetectorRegistry


# ── Regex Detector ──────────────────────────────────────────────────────


class TestRegexDetectorEmails:
    def setup_method(self):
        self.detector = RegexDetector()

    def test_simple_email(self):
        results = self.detector.detect("Contact me at john@example.com please")
        emails = [r for r in results if r.entity_type == "EMAIL"]
        assert len(emails) == 1
        assert emails[0].value == "john@example.com"
        assert emails[0].confidence == 0.99

    def test_multiple_emails(self):
        text = "Send to alice@corp.com and bob@startup.io"
        results = self.detector.detect(text)
        emails = [r for r in results if r.entity_type == "EMAIL"]
        assert len(emails) == 2

    def test_email_with_plus(self):
        results = self.detector.detect("user+tag@gmail.com")
        emails = [r for r in results if r.entity_type == "EMAIL"]
        assert len(emails) == 1
        assert emails[0].value == "user+tag@gmail.com"

    def test_email_with_dots(self):
        results = self.detector.detect("first.last@company.co.uk")
        emails = [r for r in results if r.entity_type == "EMAIL"]
        assert len(emails) == 1

    def test_no_false_positive_email(self):
        results = self.detector.detect("This is just normal text.")
        emails = [r for r in results if r.entity_type == "EMAIL"]
        assert len(emails) == 0


class TestRegexDetectorIPAddresses:
    def setup_method(self):
        self.detector = RegexDetector()

    def test_ipv4_basic(self):
        results = self.detector.detect("Server at 192.168.1.100 is down")
        ips = [r for r in results if r.entity_type == "IP_ADDRESS"]
        assert len(ips) == 1
        assert ips[0].value == "192.168.1.100"

    def test_ipv4_edge_octets(self):
        results = self.detector.detect("Address: 0.0.0.0 and 255.255.255.255")
        ips = [r for r in results if r.entity_type == "IP_ADDRESS"]
        assert len(ips) == 2

    def test_ipv4_localhost(self):
        results = self.detector.detect("localhost is 127.0.0.1")
        ips = [r for r in results if r.entity_type == "IP_ADDRESS"]
        assert len(ips) == 1
        assert ips[0].value == "127.0.0.1"

    def test_multiple_ips(self):
        text = "From 10.0.0.1 to 10.0.0.2 via 10.0.0.254"
        results = self.detector.detect(text)
        ips = [r for r in results if r.entity_type == "IP_ADDRESS"]
        assert len(ips) == 3


class TestRegexDetectorCreditCards:
    def setup_method(self):
        self.detector = RegexDetector()

    def test_visa_card(self):
        # Valid Luhn number for Visa
        results = self.detector.detect("Card: 4532015112830366")
        cards = [r for r in results if r.entity_type == "CREDIT_CARD"]
        assert len(cards) >= 1
        assert cards[0].entity_subtype == "VISA"

    def test_visa_with_spaces(self):
        results = self.detector.detect("Card: 4532 0151 1283 0366")
        cards = [r for r in results if r.entity_type == "CREDIT_CARD"]
        assert len(cards) >= 1

    def test_visa_with_dashes(self):
        results = self.detector.detect("Card: 4532-0151-1283-0366")
        cards = [r for r in results if r.entity_type == "CREDIT_CARD"]
        assert len(cards) >= 1

    def test_invalid_luhn_rejected(self):
        # Number that fails Luhn check
        results = self.detector.detect("Card: 4532015112830367")
        cards = [r for r in results if r.entity_type == "CREDIT_CARD"]
        assert len(cards) == 0

    def test_mastercard(self):
        results = self.detector.detect("MC: 5425233430109903")
        cards = [r for r in results if r.entity_type == "CREDIT_CARD"]
        assert len(cards) >= 1

    def test_amex(self):
        results = self.detector.detect("Amex: 378282246310005")
        cards = [r for r in results if r.entity_type == "CREDIT_CARD"]
        assert len(cards) >= 1


class TestRegexDetectorSSN:
    def setup_method(self):
        self.detector = RegexDetector()

    def test_ssn_with_dashes(self):
        results = self.detector.detect("SSN: 123-45-6789")
        ssns = [r for r in results if r.entity_type == "SSN"]
        assert len(ssns) >= 1

    def test_ssn_no_dashes(self):
        results = self.detector.detect("SSN: 123456789")
        ssns = [r for r in results if r.entity_type == "SSN"]
        assert len(ssns) >= 1

    def test_ssn_invalid_area_000(self):
        # SSNs starting with 000 are invalid
        results = self.detector.detect("SSN: 000-12-3456")
        ssns = [r for r in results if r.entity_type == "SSN"]
        assert len(ssns) == 0

    def test_ssn_invalid_area_666(self):
        results = self.detector.detect("SSN: 666-12-3456")
        ssns = [r for r in results if r.entity_type == "SSN"]
        assert len(ssns) == 0

    def test_ssn_with_spaces(self):
        results = self.detector.detect("SSN: 123 45 6789")
        ssns = [r for r in results if r.entity_type == "SSN"]
        assert len(ssns) >= 1

    def test_ssn_bare_digits_no_match(self):
        """Bare 9-digit sequences without context should NOT match as SSN."""
        results = self.detector.detect("Reference number 123456789 in the file")
        ssns = [r for r in results if r.entity_type == "SSN"]
        assert len(ssns) == 0

    def test_ssn_bare_digits_with_context(self):
        """Bare 9-digit SSN preceded by 'SSN:' keyword should match."""
        results = self.detector.detect("SSN: 123456789")
        ssns = [r for r in results if r.entity_type == "SSN"]
        assert len(ssns) >= 1

    def test_ssn_social_security_context(self):
        """'Social Security Number' context should trigger bare digit detection."""
        results = self.detector.detect("Social Security Number: 123456789")
        ssns = [r for r in results if r.entity_type == "SSN"]
        assert len(ssns) >= 1

    def test_ssn_not_in_address(self):
        """Digits in a street address should NOT be detected as SSN."""
        results = self.detector.detect("5678 Oak Lane, Springfield, IL 62701")
        ssns = [r for r in results if r.entity_type == "SSN"]
        assert len(ssns) == 0


class TestRegexDetectorPhones:
    def setup_method(self):
        self.detector = RegexDetector()

    def test_us_phone_parens(self):
        results = self.detector.detect("Call (555) 123-4567")
        phones = [r for r in results if r.entity_type == "PHONE"]
        assert len(phones) >= 1

    def test_us_phone_dashes(self):
        results = self.detector.detect("Call 555-123-4567")
        phones = [r for r in results if r.entity_type == "PHONE"]
        assert len(phones) >= 1

    def test_us_phone_with_country_code(self):
        results = self.detector.detect("Call +1-555-123-4567")
        phones = [r for r in results if r.entity_type == "PHONE"]
        assert len(phones) >= 1

    def test_international_phone(self):
        results = self.detector.detect("UK: +44 20 7946 0958")
        phones = [r for r in results if r.entity_type == "PHONE"]
        assert len(phones) >= 1


class TestRegexDetectorURLs:
    def setup_method(self):
        self.detector = RegexDetector()

    def test_https_url(self):
        results = self.detector.detect("Visit https://example.com/page")
        urls = [r for r in results if r.entity_type == "URL"]
        assert len(urls) == 1

    def test_http_url(self):
        results = self.detector.detect("Visit http://internal.corp.com/api")
        urls = [r for r in results if r.entity_type == "URL"]
        assert len(urls) == 1

    def test_url_with_params(self):
        results = self.detector.detect("Go to https://api.example.com/v1?key=abc&id=123")
        urls = [r for r in results if r.entity_type == "URL"]
        assert len(urls) == 1


class TestRegexDetectorSecrets:
    def setup_method(self):
        self.detector = RegexDetector()

    def test_aws_access_key(self):
        results = self.detector.detect("Key: AKIAIOSFODNN7EXAMPLE")
        keys = [r for r in results if r.entity_type == "API_KEY"]
        assert len(keys) == 1
        assert keys[0].entity_subtype == "AWS"

    def test_generic_secret(self):
        results = self.detector.detect('api_key = "sk_live_abc1234567890xyz"')
        secrets = [r for r in results if r.entity_type == "SECRET"]
        assert len(secrets) >= 1

    def test_password_assignment(self):
        results = self.detector.detect("password=SuperSecret12345678")
        secrets = [r for r in results if r.entity_type == "SECRET"]
        assert len(secrets) >= 1


class TestRegexDetectorHostnames:
    def setup_method(self):
        self.detector = RegexDetector()

    def test_internal_hostname(self):
        results = self.detector.detect("Connect to db.prod.internal")
        hosts = [r for r in results if r.entity_type == "HOSTNAME"]
        assert len(hosts) == 1

    def test_corp_hostname(self):
        results = self.detector.detect("Server: api.staging.corp")
        hosts = [r for r in results if r.entity_type == "HOSTNAME"]
        assert len(hosts) == 1


class TestRegexDetectorMAC:
    def setup_method(self):
        self.detector = RegexDetector()

    def test_mac_colon_format(self):
        results = self.detector.detect("MAC: 00:1A:2B:3C:4D:5E")
        macs = [r for r in results if r.entity_type == "MAC_ADDRESS"]
        assert len(macs) == 1

    def test_mac_dash_format(self):
        results = self.detector.detect("MAC: 00-1A-2B-3C-4D-5E")
        macs = [r for r in results if r.entity_type == "MAC_ADDRESS"]
        assert len(macs) == 1


class TestRegexDetectorConnectionStrings:
    def setup_method(self):
        self.detector = RegexDetector()

    def test_postgres_connection(self):
        results = self.detector.detect("postgresql://user:pass@localhost:5432/db")
        conns = [r for r in results if r.entity_type == "CONNECTION_STRING"]
        assert len(conns) == 1

    def test_mongodb_connection(self):
        results = self.detector.detect("mongodb://admin:secret@mongo.internal:27017/mydb")
        conns = [r for r in results if r.entity_type == "CONNECTION_STRING"]
        assert len(conns) == 1

    def test_redis_connection(self):
        results = self.detector.detect("redis://default:pass@redis.staging.corp:6379")
        conns = [r for r in results if r.entity_type == "CONNECTION_STRING"]
        assert len(conns) == 1


class TestRegexDetectorOverlaps:
    def setup_method(self):
        self.detector = RegexDetector()

    def test_overlap_resolution_longer_wins(self):
        """When two patterns match overlapping regions, the longer match wins."""
        # A URL containing an email-like pattern — the URL (longer) should win
        text = "Visit http://user@example.com/page"
        results = self.detector.detect(text)
        # Should not produce both URL and EMAIL for the overlapping region
        types = [r.entity_type for r in results]
        # URL is longer, so it should be kept
        assert "URL" in types

    def test_no_duplicate_regions(self):
        """Each character span should only be claimed by one detection."""
        text = "Email john@acme.com and IP 10.0.0.1"
        results = self.detector.detect(text)
        # Check no overlapping spans
        for i, a in enumerate(results):
            for b in results[i + 1 :]:
                overlaps = a.start < b.end and a.end > b.start
                assert not overlaps, f"{a.entity_type}[{a.start}:{a.end}] overlaps {b.entity_type}[{b.start}:{b.end}]"


class TestRegexDetectorMixedInput:
    def setup_method(self):
        self.detector = RegexDetector()

    def test_multiple_entity_types(self):
        text = (
            "Contact john@acme.com from 192.168.1.50. "
            "SSN is 123-45-6789. Call (555) 123-4567."
        )
        results = self.detector.detect(text)
        types = {r.entity_type for r in results}
        assert "EMAIL" in types
        assert "IP_ADDRESS" in types
        assert "SSN" in types
        assert "PHONE" in types

    def test_empty_text(self):
        results = self.detector.detect("")
        assert results == []

    def test_clean_text(self):
        results = self.detector.detect("This is a perfectly clean message with no PII.")
        assert results == []

    def test_positions_are_correct(self):
        text = "Email: test@example.com"
        results = self.detector.detect(text)
        emails = [r for r in results if r.entity_type == "EMAIL"]
        assert len(emails) == 1
        e = emails[0]
        assert text[e.start : e.end] == "test@example.com"


# ── Validator helpers ──────────────────────────────────────────────────


class TestLuhnCheck:
    def test_valid_visa(self):
        assert _luhn_check("4532015112830366") is True

    def test_valid_mastercard(self):
        assert _luhn_check("5425233430109903") is True

    def test_valid_amex(self):
        assert _luhn_check("378282246310005") is True

    def test_invalid_number(self):
        assert _luhn_check("1234567890123456") is False

    def test_too_short(self):
        assert _luhn_check("123") is False


class TestIPValidator:
    def test_valid_ip(self):
        assert _is_valid_ip("192.168.1.1") is True

    def test_valid_all_zeros(self):
        assert _is_valid_ip("0.0.0.0") is True

    def test_valid_all_max(self):
        assert _is_valid_ip("255.255.255.255") is True

    def test_invalid_octet_over_255(self):
        assert _is_valid_ip("256.1.1.1") is False

    def test_wrong_segment_count(self):
        assert _is_valid_ip("192.168.1") is False


# ── Address Detection ─────────────────────────────────────────────────


class TestRegexDetectorAddresses:
    def setup_method(self):
        self.detector = RegexDetector()

    def test_simple_street_address(self):
        results = self.detector.detect("I live at 123 Main Street")
        addrs = [r for r in results if r.entity_type == "ADDRESS"]
        assert len(addrs) == 1
        assert "123 Main Street" in addrs[0].value

    def test_address_with_suffix_abbreviation(self):
        results = self.detector.detect("Office at 456 Oak Ave")
        addrs = [r for r in results if r.entity_type == "ADDRESS"]
        assert len(addrs) == 1

    def test_address_with_directional(self):
        results = self.detector.detect("Located at 789 N. Broadway Blvd")
        addrs = [r for r in results if r.entity_type == "ADDRESS"]
        assert len(addrs) == 1
        assert "789" in addrs[0].value

    def test_address_with_unit(self):
        results = self.detector.detect("Ship to 100 Park Ave, Suite 200")
        addrs = [r for r in results if r.entity_type == "ADDRESS"]
        assert len(addrs) == 1
        assert "Suite 200" in addrs[0].value

    def test_full_address_with_city_state_zip(self):
        results = self.detector.detect("5678 Oak Lane, Springfield, IL 62701")
        addrs = [r for r in results if r.entity_type == "ADDRESS"]
        assert len(addrs) >= 1
        # Should capture the full address including city/state/zip
        full = max(addrs, key=lambda a: len(a.value))
        assert "5678" in full.value
        assert "62701" in full.value

    def test_ordinal_street_name(self):
        results = self.detector.detect("Located at 789 E. 42nd Street")
        addrs = [r for r in results if r.entity_type == "ADDRESS"]
        assert len(addrs) == 1
        assert "42nd" in addrs[0].value

    def test_po_box(self):
        results = self.detector.detect("Mail to P.O. Box 12345")
        addrs = [r for r in results if r.entity_type == "ADDRESS"]
        assert len(addrs) == 1
        assert "12345" in addrs[0].value

    def test_po_box_no_periods(self):
        results = self.detector.detect("PO Box 999")
        addrs = [r for r in results if r.entity_type == "ADDRESS"]
        assert len(addrs) == 1

    def test_city_state_zip(self):
        results = self.detector.detect("Springfield, IL 62701")
        addrs = [r for r in results if r.entity_type == "ADDRESS"]
        assert len(addrs) == 1
        assert "Springfield" in addrs[0].value

    def test_city_state_zip_with_plus4(self):
        results = self.detector.detect("Austin, TX 78701-1234")
        addrs = [r for r in results if r.entity_type == "ADDRESS"]
        assert len(addrs) == 1

    def test_address_prevents_ssn_misclass(self):
        """Address detection should claim the span and prevent SSN false positives."""
        text = "5678 Oak Lane, Springfield, IL 62701"
        results = self.detector.detect(text)
        ssns = [r for r in results if r.entity_type == "SSN"]
        assert len(ssns) == 0

    def test_multiple_addresses(self):
        text = "From 123 Main St to 456 Oak Ave"
        results = self.detector.detect(text)
        addrs = [r for r in results if r.entity_type == "ADDRESS"]
        assert len(addrs) == 2

    def test_no_false_positive_plain_text(self):
        """Normal text should not trigger address detection."""
        results = self.detector.detect("The company grew 500 percent last quarter")
        addrs = [r for r in results if r.entity_type == "ADDRESS"]
        assert len(addrs) == 0

    def test_common_street_suffixes(self):
        """Test various street suffix types are recognized."""
        for suffix in ["St", "Ave", "Blvd", "Dr", "Rd", "Ln", "Way", "Ct", "Pl",
                        "Cir", "Trl", "Ter", "Pkwy", "Hwy"]:
            text = f"100 Test {suffix}"
            results = self.detector.detect(text)
            addrs = [r for r in results if r.entity_type == "ADDRESS"]
            assert len(addrs) >= 1, f"Failed to detect address with suffix '{suffix}'"


# ── Person Name Detection ─────────────────────────────────────────────


class TestRegexDetectorPersonNames:
    """Context-based person name detection (regex, not NER)."""

    def setup_method(self):
        self.detector = RegexDetector()

    def test_mr_first_last(self):
        results = self.detector.detect("Contact Mr. John Smith for details")
        persons = [r for r in results if r.entity_type == "PERSON"]
        assert len(persons) == 1
        assert "Mr. John Smith" in persons[0].value

    def test_dr_full_name(self):
        results = self.detector.detect("Dr. Jane Doe is the specialist")
        persons = [r for r in results if r.entity_type == "PERSON"]
        assert len(persons) == 1
        assert "Dr. Jane Doe" in persons[0].value

    def test_middle_initial(self):
        results = self.detector.detect("Dr. Robert A. Johnson is attending")
        persons = [r for r in results if r.entity_type == "PERSON"]
        assert len(persons) == 1
        assert "Robert A. Johnson" in persons[0].value

    def test_patient_label(self):
        results = self.detector.detect("Patient: Jane Doe")
        persons = [r for r in results if r.entity_type == "PERSON"]
        assert len(persons) == 1
        assert "Jane Doe" in persons[0].value

    def test_name_label(self):
        results = self.detector.detect("Name: Alice Johnson")
        persons = [r for r in results if r.entity_type == "PERSON"]
        assert len(persons) == 1
        assert "Alice Johnson" in persons[0].value

    def test_name_label_lowercase(self):
        """Label keywords should match case-insensitively."""
        results = self.detector.detect("name: Alice Johnson")
        persons = [r for r in results if r.entity_type == "PERSON"]
        assert len(persons) == 1

    def test_client_label(self):
        results = self.detector.detect("Client: Bob Williams")
        persons = [r for r in results if r.entity_type == "PERSON"]
        assert len(persons) == 1

    def test_employee_label(self):
        results = self.detector.detect("Employee: Carol Davis")
        persons = [r for r in results if r.entity_type == "PERSON"]
        assert len(persons) == 1

    def test_dear_salutation(self):
        results = self.detector.detect("Dear John,")
        persons = [r for r in results if r.entity_type == "PERSON"]
        assert len(persons) == 1
        assert "Dear John" in persons[0].value

    def test_dear_with_honorific(self):
        results = self.detector.detect("Dear Mr. Johnson,")
        persons = [r for r in results if r.entity_type == "PERSON"]
        assert len(persons) >= 1

    def test_no_false_positive_plain_text(self):
        """Normal text without name context should not trigger."""
        results = self.detector.detect("The server processed 500 requests today")
        persons = [r for r in results if r.entity_type == "PERSON"]
        assert len(persons) == 0

    def test_no_newline_crossing(self):
        """Name patterns should not match across newlines."""
        text = "Patient: John Doe\nAddress: 123 Main St"
        results = self.detector.detect(text)
        persons = [r for r in results if r.entity_type == "PERSON"]
        assert len(persons) >= 1
        # The person match should NOT include "Address"
        for p in persons:
            assert "Address" not in p.value

    def test_mixed_pii_names_and_addresses(self):
        """Names and addresses detected separately in mixed PII text."""
        text = "Patient: John Doe\nAddress: 5678 Oak Lane\nSSN: 287-65-4321"
        results = self.detector.detect(text)
        persons = [r for r in results if r.entity_type == "PERSON"]
        addrs = [r for r in results if r.entity_type == "ADDRESS"]
        ssns = [r for r in results if r.entity_type == "SSN"]
        assert len(persons) >= 1
        assert len(addrs) >= 1
        assert len(ssns) >= 1


# ── Custom Rule Detector ───────────────────────────────────────────────


class _FakeRule:
    """Minimal stand-in for DetectionRule ORM object."""

    def __init__(self, name, entity_type, detection_method, pattern=None,
                 word_list=None, confidence=0.8, is_active=True):
        self.name = name
        self.entity_type = entity_type
        self.detection_method = detection_method
        self.pattern = pattern
        self.word_list = word_list
        self.confidence = confidence
        self.is_active = is_active


class TestCustomRuleDetector:
    def test_regex_rule_detects(self):
        from backend.detectors.custom_rule_detector import CustomRuleDetector

        rule = _FakeRule(
            name="Employee ID",
            entity_type="EMPLOYEE_ID",
            detection_method="regex",
            pattern=r"EMP-\d{5}",
        )
        detector = CustomRuleDetector([rule])
        results = detector.detect("Employee EMP-12345 joined today")
        assert len(results) == 1
        assert results[0].entity_type == "EMPLOYEE_ID"
        assert results[0].value == "EMP-12345"
        assert results[0].detection_method == "custom_regex"

    def test_dictionary_rule_detects(self):
        from backend.detectors.custom_rule_detector import CustomRuleDetector

        rule = _FakeRule(
            name="Project Names",
            entity_type="PROJECT",
            detection_method="dictionary",
            word_list=json.dumps(["Project Alpha", "Project Beta"]),
        )
        detector = CustomRuleDetector([rule])
        results = detector.detect("Working on Project Alpha this week")
        assert len(results) == 1
        assert results[0].entity_type == "PROJECT"
        assert results[0].value == "Project Alpha"
        assert results[0].detection_method == "custom_dictionary"

    def test_dictionary_case_insensitive(self):
        from backend.detectors.custom_rule_detector import CustomRuleDetector

        rule = _FakeRule(
            name="Internal Tools",
            entity_type="TOOL",
            detection_method="dictionary",
            word_list=json.dumps(["SecretTool"]),
        )
        detector = CustomRuleDetector([rule])
        results = detector.detect("Using SECRETTOOL for the build")
        assert len(results) == 1

    def test_inactive_rules_skipped(self):
        from backend.detectors.custom_rule_detector import CustomRuleDetector

        rule = _FakeRule(
            name="Inactive",
            entity_type="TEST",
            detection_method="regex",
            pattern=r"test\d+",
            is_active=False,
        )
        detector = CustomRuleDetector([rule])
        assert detector.is_available is False
        results = detector.detect("test123")
        assert len(results) == 0

    def test_invalid_regex_skipped(self):
        from backend.detectors.custom_rule_detector import CustomRuleDetector

        rule = _FakeRule(
            name="Bad Regex",
            entity_type="TEST",
            detection_method="regex",
            pattern=r"[invalid",
        )
        detector = CustomRuleDetector([rule])
        results = detector.detect("some text")
        assert len(results) == 0

    def test_multiple_dictionary_matches(self):
        from backend.detectors.custom_rule_detector import CustomRuleDetector

        rule = _FakeRule(
            name="Codenames",
            entity_type="CODENAME",
            detection_method="dictionary",
            word_list=json.dumps(["alpha", "beta"]),
        )
        detector = CustomRuleDetector([rule])
        results = detector.detect("alpha and beta are both codenames, and alpha again")
        assert len(results) == 3  # alpha x2, beta x1

    def test_regex_rule_multiple_matches(self):
        from backend.detectors.custom_rule_detector import CustomRuleDetector

        rule = _FakeRule(
            name="Ticket IDs",
            entity_type="TICKET",
            detection_method="regex",
            pattern=r"TICK-\d{4}",
        )
        detector = CustomRuleDetector([rule])
        results = detector.detect("See TICK-0001 and TICK-0042")
        assert len(results) == 2


# ── Detector Registry ──────────────────────────────────────────────────


class TestDetectorRegistry:
    def test_register_and_detect(self):
        registry = DetectorRegistry()
        registry.register(RegexDetector())
        results = registry.detect_all("Email: test@example.com")
        assert len(results) >= 1
        assert any(r.entity_type == "EMAIL" for r in results)

    def test_empty_registry(self):
        registry = DetectorRegistry()
        results = registry.detect_all("test@example.com")
        assert results == []

    def test_registry_overlap_resolution(self):
        """Registry merges results from multiple detectors and resolves overlaps."""
        registry = DetectorRegistry()
        registry.register(RegexDetector())

        text = "Email john@acme.com and IP 10.0.0.1"
        results = registry.detect_all(text)

        # Verify no overlapping spans
        for i, a in enumerate(results):
            for b in results[i + 1 :]:
                assert not (a.start < b.end and a.end > b.start)

    def test_registry_with_custom_rules(self):
        from backend.detectors.custom_rule_detector import CustomRuleDetector

        rule = _FakeRule(
            name="Emp ID",
            entity_type="EMPLOYEE_ID",
            detection_method="regex",
            pattern=r"EMP-\d{5}",
        )
        registry = DetectorRegistry()
        registry.register(RegexDetector())
        registry.register(CustomRuleDetector([rule]))

        results = registry.detect_all("EMP-12345 emailed test@example.com")
        types = {r.entity_type for r in results}
        assert "EMPLOYEE_ID" in types
        assert "EMAIL" in types

    def test_sorted_by_position(self):
        registry = DetectorRegistry()
        registry.register(RegexDetector())
        text = "IP: 10.0.0.1 Email: alice@corp.com"
        results = registry.detect_all(text)
        positions = [r.start for r in results]
        assert positions == sorted(positions)
