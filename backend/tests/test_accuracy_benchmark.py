"""Detection accuracy benchmark — measures precision and recall per entity type.

Run with: python -m pytest backend/tests/test_accuracy_benchmark.py -v -s

Produces a summary table showing TP/FP/FN/Precision/Recall/F1 per entity type.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from backend.detectors.base import DetectedEntity
from backend.detectors.registry import create_default_registry


# ---------------------------------------------------------------------------
# Corpus definitions
# ---------------------------------------------------------------------------


@dataclass
class AnnotatedSample:
    """A text sample with expected entity annotations."""

    text: str
    expected: list[dict]  # [{"type": "EMAIL", "value": "...", "start": int, "end": int}]
    description: str = ""


@dataclass
class NegativeSample:
    """Text that should produce zero detections (or only NER false positives)."""

    text: str
    description: str = ""


# ---- True Positive Corpus ----

TP_SAMPLES: list[AnnotatedSample] = [
    # === EMAIL (5) ===
    AnnotatedSample(
        text="Contact us at john.doe@example.com for support.",
        expected=[{"type": "EMAIL", "value": "john.doe@example.com", "start": 17, "end": 36}],
        description="EMAIL: standard address",
    ),
    AnnotatedSample(
        text="Send to alice+billing@company.org immediately.",
        expected=[{"type": "EMAIL", "value": "alice+billing@company.org", "start": 8, "end": 32}],
        description="EMAIL: plus-addressed",
    ),
    AnnotatedSample(
        text="Email admin@mail.internal.corp.co for access.",
        expected=[{"type": "EMAIL", "value": "admin@mail.internal.corp.co", "start": 6, "end": 33}],
        description="EMAIL: subdomain",
    ),
    AnnotatedSample(
        text="Reach ceo@megacorp.enterprises for partnerships.",
        expected=[{"type": "EMAIL", "value": "ceo@megacorp.enterprises", "start": 6, "end": 30}],
        description="EMAIL: corporate TLD",
    ),
    AnnotatedSample(
        text="Notify user_name-99@test-server.io about the outage.",
        expected=[{"type": "EMAIL", "value": "user_name-99@test-server.io", "start": 7, "end": 34}],
        description="EMAIL: special chars in local part",
    ),

    # === CREDIT_CARD (5) ===
    AnnotatedSample(
        text="Visa card: 4532015112830366 on file.",
        expected=[{"type": "CREDIT_CARD", "value": "4532015112830366", "start": 11, "end": 27}],
        description="CREDIT_CARD: Visa no separators",
    ),
    AnnotatedSample(
        text="Charge to 5425 2334 3010 9903 please.",
        expected=[{"type": "CREDIT_CARD", "value": "5425 2334 3010 9903", "start": 10, "end": 29}],
        description="CREDIT_CARD: MasterCard with spaces",
    ),
    AnnotatedSample(
        text="Amex: 3714-496353-98431 for the order.",
        expected=[{"type": "CREDIT_CARD", "value": "3714-496353-98431", "start": 6, "end": 23}],
        description="CREDIT_CARD: Amex with dashes",
    ),
    AnnotatedSample(
        text="Payment card 4916338506082832 was declined.",
        expected=[{"type": "CREDIT_CARD", "value": "4916338506082832", "start": 13, "end": 29}],
        description="CREDIT_CARD: Visa plain",
    ),
    AnnotatedSample(
        text="Card ending 5105-1051-0510-5100 is expired.",
        expected=[{"type": "CREDIT_CARD", "value": "5105-1051-0510-5100", "start": 12, "end": 31}],
        description="CREDIT_CARD: MasterCard dashes",
    ),

    # === SSN (5) ===
    AnnotatedSample(
        text="SSN: 123-45-6789 on the form.",
        expected=[{"type": "SSN", "value": "123-45-6789", "start": 5, "end": 16}],
        description="SSN: standard format with dashes",
    ),
    AnnotatedSample(
        text="Social security number is 234 56 7890.",
        expected=[{"type": "SSN", "value": "234 56 7890", "start": 26, "end": 37}],
        description="SSN: with spaces",
    ),
    AnnotatedSample(
        text="Employee SSN is 345-67-8901 per records.",
        expected=[{"type": "SSN", "value": "345-67-8901", "start": 16, "end": 27}],
        description="SSN: embedded in sentence",
    ),
    AnnotatedSample(
        text="Record for SSN 456-78-9012 is updated.",
        expected=[{"type": "SSN", "value": "456-78-9012", "start": 15, "end": 26}],
        description="SSN: with context label",
    ),
    AnnotatedSample(
        text="Found SSN 567-89-0123 near the date 2024-01-15.",
        expected=[{"type": "SSN", "value": "567-89-0123", "start": 10, "end": 21}],
        description="SSN: near a date (ambiguity test)",
    ),

    # === PHONE (5) ===
    AnnotatedSample(
        text="Call (555) 123-4567 for details.",
        expected=[{"type": "PHONE", "value": "(555) 123-4567", "start": 5, "end": 19}],
        description="PHONE: US with parens",
    ),
    AnnotatedSample(
        text="Reach us at 555-867-5309 anytime.",
        expected=[{"type": "PHONE", "value": "555-867-5309", "start": 12, "end": 24}],
        description="PHONE: US with dashes",
    ),
    AnnotatedSample(
        text="Mobile: 555.234.5678 is preferred.",
        expected=[{"type": "PHONE", "value": "555.234.5678", "start": 8, "end": 20}],
        description="PHONE: US with dots",
    ),
    AnnotatedSample(
        text="Contact +1 555 345 6789 for emergencies.",
        expected=[{"type": "PHONE", "value": "+1 555 345 6789", "start": 8, "end": 23}],
        description="PHONE: US with country code",
    ),
    AnnotatedSample(
        text="International: +44 20 7946 0958 is the London office.",
        expected=[{"type": "PHONE", "value": "+44 20 7946 0958", "start": 15, "end": 31}],
        description="PHONE: UK international",
    ),

    # === IP_ADDRESS (4) ===
    AnnotatedSample(
        text="Server at 192.168.1.100 is unreachable.",
        expected=[{"type": "IP_ADDRESS", "value": "192.168.1.100", "start": 10, "end": 23}],
        description="IP_ADDRESS: private IPv4",
    ),
    AnnotatedSample(
        text="External IP: 203.0.113.42 is blocked.",
        expected=[{"type": "IP_ADDRESS", "value": "203.0.113.42", "start": 13, "end": 25}],
        description="IP_ADDRESS: public IPv4",
    ),
    AnnotatedSample(
        text="Gateway is at 10.0.0.1 in the network.",
        expected=[{"type": "IP_ADDRESS", "value": "10.0.0.1", "start": 14, "end": 22}],
        description="IP_ADDRESS: edge octets",
    ),
    AnnotatedSample(
        text="IPv6 address 2001:0db8:85a3:0000:0000:8a2e:0370:7334 found in log.",
        expected=[{"type": "IP_ADDRESS", "value": "2001:0db8:85a3:0000:0000:8a2e:0370:7334", "start": 13, "end": 52}],
        description="IP_ADDRESS: full IPv6",
    ),

    # === API_KEY / SECRET (4) ===
    AnnotatedSample(
        text="AWS key: AKIAIOSFODNN7EXAMPLE is active.",
        expected=[{"type": "API_KEY", "value": "AKIAIOSFODNN7EXAMPLE", "start": 9, "end": 29}],
        description="API_KEY: AWS access key",
    ),
    AnnotatedSample(
        text="Set api_key=sk_live_abcdefghijklmnop in env.",
        expected=[{"type": "SECRET", "value": "api_key=sk_live_abcdefghijklmnop", "start": 4, "end": 36}],
        description="SECRET: api_key= pattern",
    ),
    AnnotatedSample(
        text="Use password=SuperSecretPass1234 in config.",
        expected=[{"type": "SECRET", "value": "password=SuperSecretPass1234", "start": 4, "end": 32}],
        description="SECRET: password= pattern",
    ),
    AnnotatedSample(
        text="Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U in header.",
        expected=[{"type": "AUTH_TOKEN", "value": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U", "start": 15, "end": 113}],
        description="AUTH_TOKEN: Bearer JWT",
    ),

    # === CONNECTION_STRING (4) ===
    AnnotatedSample(
        text="Database: postgresql://admin:s3cret@db.internal.corp:5432/production",
        expected=[{"type": "CONNECTION_STRING", "value": "postgresql://admin:s3cret@db.internal.corp:5432/production", "start": 10, "end": 68}],
        description="CONNECTION_STRING: PostgreSQL",
    ),
    AnnotatedSample(
        text="Connect to mongodb://user:pass@mongo.cluster.local:27017/mydb for data.",
        expected=[{"type": "CONNECTION_STRING", "value": "mongodb://user:pass@mongo.cluster.local:27017/mydb", "start": 11, "end": 61}],
        description="CONNECTION_STRING: MongoDB",
    ),
    AnnotatedSample(
        text="Cache at redis://default:token123@redis-host:6379/0 is ready.",
        expected=[{"type": "CONNECTION_STRING", "value": "redis://default:token123@redis-host:6379/0", "start": 9, "end": 51}],
        description="CONNECTION_STRING: Redis",
    ),
    AnnotatedSample(
        text="Legacy: mysql://root:password@mysql-server:3306/legacy_db is deprecated.",
        expected=[{"type": "CONNECTION_STRING", "value": "mysql://root:password@mysql-server:3306/legacy_db", "start": 8, "end": 58}],
        description="CONNECTION_STRING: MySQL",
    ),

    # === URL (3) ===
    AnnotatedSample(
        text="Visit https://app.example.com/api?token=abc123&user=admin for the dashboard.",
        expected=[{"type": "URL", "value": "https://app.example.com/api?token=abc123&user=admin", "start": 6, "end": 57}],
        description="URL: with query params",
    ),
    AnnotatedSample(
        text="Endpoint at http://admin:pass@internal-api.corp:8080/v2/data is restricted.",
        expected=[{"type": "URL", "value": "http://admin:pass@internal-api.corp:8080/v2/data", "start": 12, "end": 60}],
        description="URL: with basic auth (detected as URL due to overlap priority)",
    ),
    AnnotatedSample(
        text="Check https://staging.internal.example.com/health for status.",
        expected=[{"type": "URL", "value": "https://staging.internal.example.com/health", "start": 6, "end": 50}],
        description="URL: internal staging",
    ),

    # === HOSTNAME (3) ===
    AnnotatedSample(
        text="Deploy to app-server.internal and restart.",
        expected=[{"type": "HOSTNAME", "value": "app-server.internal", "start": 10, "end": 29}],
        description="HOSTNAME: .internal domain",
    ),
    AnnotatedSample(
        text="The host db-replica.corp handles read queries.",
        expected=[{"type": "HOSTNAME", "value": "db-replica.corp", "start": 9, "end": 24}],
        description="HOSTNAME: .corp domain",
    ),
    AnnotatedSample(
        text="Cache is on redis.staging and ready.",
        expected=[{"type": "HOSTNAME", "value": "redis.staging", "start": 12, "end": 25}],
        description="HOSTNAME: .staging domain",
    ),

    # === PERSON (4, NER only) ===
    AnnotatedSample(
        text="Meeting with Sarah Johnson at the conference tomorrow.",
        expected=[{"type": "PERSON", "value": "Sarah Johnson", "start": 13, "end": 26}],
        description="PERSON: common two-word name",
    ),
    AnnotatedSample(
        text="Dr. Michael Chen will review the results next week.",
        expected=[{"type": "PERSON", "value": "Dr. Michael Chen", "start": 0, "end": 16}],
        description="PERSON: name with title",
    ),
    AnnotatedSample(
        text="Please forward this to Maria Garcia-Lopez for approval.",
        expected=[{"type": "PERSON", "value": "Maria Garcia-Lopez", "start": 23, "end": 41}],
        description="PERSON: hyphenated surname",
    ),
    AnnotatedSample(
        text="Robert Williams submitted the report on Monday.",
        expected=[{"type": "PERSON", "value": "Robert Williams", "start": 0, "end": 15}],
        description="PERSON: name at start",
    ),

    # === ORGANIZATION (3, NER only) ===
    AnnotatedSample(
        text="We signed the contract with Acme Corporation last quarter.",
        expected=[{"type": "ORGANIZATION", "value": "Acme Corporation", "start": 27, "end": 43}],
        description="ORGANIZATION: company with Corp suffix",
    ),
    AnnotatedSample(
        text="Submit the report to Goldman Sachs by Friday.",
        expected=[{"type": "ORGANIZATION", "value": "Goldman Sachs", "start": 21, "end": 34}],
        description="ORGANIZATION: financial institution",
    ),
    AnnotatedSample(
        text="The partnership with Microsoft was announced today.",
        expected=[{"type": "ORGANIZATION", "value": "Microsoft", "start": 21, "end": 30}],
        description="ORGANIZATION: well-known company",
    ),

    # === Mixed samples (5) ===
    AnnotatedSample(
        text="Patient record for SSN 678-90-1234, contact: (555) 456-7890, email: patient@hospital.org",
        expected=[
            {"type": "SSN", "value": "678-90-1234", "start": 23, "end": 34},
            {"type": "PHONE", "value": "(555) 456-7890", "start": 45, "end": 59},
            {"type": "EMAIL", "value": "patient@hospital.org", "start": 68, "end": 88},
        ],
        description="MIXED: HIPAA record with SSN + phone + email",
    ),
    AnnotatedSample(
        text="Transfer from card 4532015112830366 to account, notify admin@bank.com",
        expected=[
            {"type": "CREDIT_CARD", "value": "4532015112830366", "start": 19, "end": 35},
            {"type": "EMAIL", "value": "admin@bank.com", "start": 55, "end": 69},
        ],
        description="MIXED: financial doc with CC + email",
    ),
    AnnotatedSample(
        text="Alert from 10.0.0.1: user=jsmith connected from 203.0.113.55",
        expected=[
            {"type": "IP_ADDRESS", "value": "10.0.0.1", "start": 11, "end": 19},
            {"type": "USERNAME", "value": "user=jsmith", "start": 21, "end": 32},
            {"type": "IP_ADDRESS", "value": "203.0.113.55", "start": 49, "end": 61},
        ],
        description="MIXED: DevOps log with IPs + username",
    ),
    AnnotatedSample(
        text="Ticket from alice@support.com: server db.prod is down, try postgresql://ops:fix@db.prod:5432/main",
        expected=[
            {"type": "EMAIL", "value": "alice@support.com", "start": 12, "end": 29},
            {"type": "HOSTNAME", "value": "db.prod", "start": 38, "end": 45},
            {"type": "CONNECTION_STRING", "value": "postgresql://ops:fix@db.prod:5432/main", "start": 60, "end": 98},
        ],
        description="MIXED: support ticket with email + hostname + conn string",
    ),
    AnnotatedSample(
        text="Contract with SSN 789-01-2345 signed by email: legal@firm.com, fax: (555) 789-0123",
        expected=[
            {"type": "SSN", "value": "789-01-2345", "start": 18, "end": 29},
            {"type": "EMAIL", "value": "legal@firm.com", "start": 47, "end": 61},
            {"type": "PHONE", "value": "(555) 789-0123", "start": 68, "end": 82},
        ],
        description="MIXED: legal doc with SSN + email + phone",
    ),
]


# ---- True Negative Corpus ----

TN_SAMPLES: list[NegativeSample] = [
    NegativeSample(
        text="The weather forecast calls for sunny skies and temperatures around 72 degrees.",
        description="TN: plain weather prose",
    ),
    NegativeSample(
        text="Our new product launches in three color options: red, blue, and green.",
        description="TN: product description",
    ),
    NegativeSample(
        text="The function calculates the factorial of a given integer and returns the result.",
        description="TN: programming description",
    ),
    NegativeSample(
        text="Version 3.14.159 was released with bug fixes and performance improvements.",
        description="TN: version number (not IP)",
    ),
    NegativeSample(
        text="Order #ORD-2024-78901 has been shipped via express delivery.",
        description="TN: order ID (not SSN)",
    ),
    NegativeSample(
        text="The meeting is scheduled for March 15, 2024 at the main conference room.",
        description="TN: date (not SSN)",
    ),
    NegativeSample(
        text="Please review section 4.2.1 of the documentation for installation steps.",
        description="TN: section numbers",
    ),
    NegativeSample(
        text="The algorithm runs in O(n log n) time complexity for the average case.",
        description="TN: algorithm notation",
    ),
    NegativeSample(
        text="Add 2 cups of flour, 1 teaspoon of salt, and mix for 5 minutes.",
        description="TN: recipe instructions",
    ),
    NegativeSample(
        text="The building has 42 floors and was completed in 1998.",
        description="TN: building description",
    ),
    NegativeSample(
        text="# Installation Guide\n\nRun `pip install mypackage` to get started.",
        description="TN: markdown documentation",
    ),
    NegativeSample(
        text="for i in range(100):\n    result = process(i)\n    print(result)",
        description="TN: Python code without secrets",
    ),
    NegativeSample(
        text="The committee approved the budget of $1,234,567 for fiscal year 2025.",
        description="TN: monetary amounts",
    ),
    NegativeSample(
        text="Select items from the catalog: SKU-A001, SKU-B002, SKU-C003.",
        description="TN: catalog SKUs",
    ),
    NegativeSample(
        text="Latitude 40.7128, Longitude -74.0060 marks the city center.",
        description="TN: geographic coordinates",
    ),
    NegativeSample(
        text="The dataset contains 50000 rows and 25 columns in CSV format.",
        description="TN: dataset stats",
    ),
    NegativeSample(
        text="Use the formula: area = length * width to calculate square footage.",
        description="TN: math formula",
    ),
    NegativeSample(
        text="Chapter 12 discusses advanced topics in distributed systems architecture.",
        description="TN: textbook reference",
    ),
    NegativeSample(
        text="The train departs at 14:30 from platform 9 and arrives at 17:45.",
        description="TN: train schedule",
    ),
    NegativeSample(
        text="Mix colors: RGB(255, 128, 0) creates a warm orange tone for the banner.",
        description="TN: color codes",
    ),
]

# NER-only entity types that require Presidio/spaCy
NER_ONLY_TYPES = {"PERSON", "ORGANIZATION"}


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkScorer:
    """Accumulates TP/FP/FN per entity type using span-overlap matching."""

    tp: dict[str, int] = field(default_factory=lambda: {})
    fp: dict[str, int] = field(default_factory=lambda: {})
    fn: dict[str, int] = field(default_factory=lambda: {})

    def _iou(self, a_start: int, a_end: int, b_start: int, b_end: int) -> float:
        """Compute Intersection over Union of two spans."""
        overlap_start = max(a_start, b_start)
        overlap_end = min(a_end, b_end)
        intersection = max(0, overlap_end - overlap_start)
        union = max(a_end - a_start, 1) + max(b_end - b_start, 1) - intersection
        return intersection / union if union > 0 else 0.0

    def score_sample(
        self,
        detected: list[DetectedEntity],
        expected: list[dict],
        skip_ner: bool = False,
    ) -> dict[str, dict[str, int]]:
        """Score a single sample. Returns per-type TP/FP/FN deltas."""
        deltas: dict[str, dict[str, int]] = {}

        # Filter expected if skipping NER types
        active_expected = [
            e for e in expected
            if not (skip_ner and e["type"] in NER_ONLY_TYPES)
        ]

        matched_detected: set[int] = set()
        matched_expected: set[int] = set()

        # Match expected → detected using IoU >= 0.5
        for ei, exp in enumerate(active_expected):
            etype = exp["type"]
            best_iou = 0.0
            best_di = -1

            for di, det in enumerate(detected):
                if di in matched_detected:
                    continue
                if det.entity_type != etype:
                    continue

                iou = self._iou(exp["start"], exp["end"], det.start, det.end)
                if iou > best_iou:
                    best_iou = iou
                    best_di = di

            if best_iou >= 0.5:
                matched_detected.add(best_di)
                matched_expected.add(ei)
                self.tp[etype] = self.tp.get(etype, 0) + 1
                deltas.setdefault(etype, {"tp": 0, "fp": 0, "fn": 0})
                deltas[etype]["tp"] += 1
            else:
                self.fn[etype] = self.fn.get(etype, 0) + 1
                deltas.setdefault(etype, {"tp": 0, "fp": 0, "fn": 0})
                deltas[etype]["fn"] += 1

        # Unmatched detections are false positives
        for di, det in enumerate(detected):
            if di not in matched_detected:
                etype = det.entity_type
                # Skip NER-only FPs when NER is unavailable
                if skip_ner and etype in NER_ONLY_TYPES:
                    continue
                self.fp[etype] = self.fp.get(etype, 0) + 1
                deltas.setdefault(etype, {"tp": 0, "fp": 0, "fn": 0})
                deltas[etype]["fp"] += 1

        return deltas

    def precision(self, entity_type: str) -> float:
        tp = self.tp.get(entity_type, 0)
        fp = self.fp.get(entity_type, 0)
        return tp / (tp + fp) if (tp + fp) > 0 else 1.0

    def recall(self, entity_type: str) -> float:
        tp = self.tp.get(entity_type, 0)
        fn = self.fn.get(entity_type, 0)
        return tp / (tp + fn) if (tp + fn) > 0 else 1.0

    def f1(self, entity_type: str) -> float:
        p = self.precision(entity_type)
        r = self.recall(entity_type)
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    def overall_precision(self) -> float:
        tp = sum(self.tp.values())
        fp = sum(self.fp.values())
        return tp / (tp + fp) if (tp + fp) > 0 else 1.0

    def overall_recall(self) -> float:
        tp = sum(self.tp.values())
        fn = sum(self.fn.values())
        return tp / (tp + fn) if (tp + fn) > 0 else 1.0

    def overall_f1(self) -> float:
        p = self.overall_precision()
        r = self.overall_recall()
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    def all_types(self) -> list[str]:
        types = set(self.tp.keys()) | set(self.fp.keys()) | set(self.fn.keys())
        return sorted(types)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def registry():
    """Create a detector registry (regex + NER if available)."""
    return create_default_registry()


@pytest.fixture(scope="module")
def ner_available(registry):
    """Check if Presidio NER is available."""
    return any(d.name == "presidio" for d in registry._detectors)


@pytest.fixture(scope="module")
def scorer():
    """Shared scorer that accumulates results across all tests."""
    return BenchmarkScorer()


# ---------------------------------------------------------------------------
# Parametrized tests — one per sample
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sample",
    TP_SAMPLES,
    ids=[s.description for s in TP_SAMPLES],
)
def test_true_positive(sample: AnnotatedSample, registry, ner_available, scorer):
    """Each TP sample should detect expected entities."""
    detected = registry.detect_all(sample.text)
    skip_ner = not ner_available

    deltas = scorer.score_sample(detected, sample.expected, skip_ner=skip_ner)

    # Filter to non-NER expectations for assertion
    relevant_expected = [
        e for e in sample.expected
        if not (skip_ner and e["type"] in NER_ONLY_TYPES)
    ]

    if not relevant_expected:
        pytest.skip("NER not available, no regex expectations in this sample")
        return

    # Check that at least one expected entity was found
    found_types = {d.entity_type for d in detected}
    expected_types = {e["type"] for e in relevant_expected}
    missing = expected_types - found_types

    # Allow the test to pass but log misses — aggregate tests enforce thresholds
    if missing:
        pytest.xfail(f"Missing types: {missing}")


@pytest.mark.parametrize(
    "sample",
    TN_SAMPLES,
    ids=[s.description for s in TN_SAMPLES],
)
def test_true_negative(sample: NegativeSample, registry, ner_available, scorer):
    """TN samples should produce zero or minimal detections."""
    detected = registry.detect_all(sample.text)

    # NER may produce false positives on clean text — only count regex FPs
    regex_detections = [d for d in detected if d.detection_method == "regex"]

    # Score as empty expected — all detections are FPs
    if regex_detections:
        for det in regex_detections:
            scorer.fp[det.entity_type] = scorer.fp.get(det.entity_type, 0) + 1

    # Strict: no regex false positives on clean text
    assert len(regex_detections) == 0, (
        f"False positives on clean text: "
        f"{[(d.entity_type, d.value) for d in regex_detections]}"
    )


# ---------------------------------------------------------------------------
# Aggregate threshold tests
# ---------------------------------------------------------------------------


# Types where we require >=90% recall and >=90% precision
REGEX_THRESHOLD_TYPES = [
    "EMAIL", "CREDIT_CARD", "IP_ADDRESS", "URL",
    "CONNECTION_STRING", "API_KEY", "SECRET", "AUTH_TOKEN",
]

# Types with lower thresholds (more ambiguous patterns)
FUZZY_THRESHOLD_TYPES = [
    "SSN", "PHONE", "HOSTNAME",
]


def test_aggregate_precision_regex_types(scorer):
    """Regex entity types should achieve >=90% precision."""
    for etype in REGEX_THRESHOLD_TYPES:
        tp = scorer.tp.get(etype, 0)
        if tp == 0:
            continue  # Skip types with no TP data
        p = scorer.precision(etype)
        assert p >= 0.90, f"{etype} precision {p:.1%} < 90%"


def test_aggregate_recall_regex_types(scorer):
    """Regex entity types should achieve >=90% recall."""
    for etype in REGEX_THRESHOLD_TYPES:
        fn = scorer.fn.get(etype, 0)
        tp = scorer.tp.get(etype, 0)
        if tp + fn == 0:
            continue
        r = scorer.recall(etype)
        assert r >= 0.90, f"{etype} recall {r:.1%} < 90%"


def test_aggregate_precision_fuzzy_types(scorer):
    """Fuzzy types should achieve >=75% precision."""
    for etype in FUZZY_THRESHOLD_TYPES:
        tp = scorer.tp.get(etype, 0)
        if tp == 0:
            continue
        p = scorer.precision(etype)
        assert p >= 0.75, f"{etype} precision {p:.1%} < 75%"


def test_aggregate_recall_fuzzy_types(scorer):
    """Fuzzy types should achieve >=75% recall."""
    for etype in FUZZY_THRESHOLD_TYPES:
        fn = scorer.fn.get(etype, 0)
        tp = scorer.tp.get(etype, 0)
        if tp + fn == 0:
            continue
        r = scorer.recall(etype)
        assert r >= 0.75, f"{etype} recall {r:.1%} < 75%"


def test_overall_f1(scorer):
    """Overall F1 should be >= 85%."""
    f1 = scorer.overall_f1()
    assert f1 >= 0.85, f"Overall F1 {f1:.1%} < 85%"


# ---------------------------------------------------------------------------
# Summary table (runs with -s)
# ---------------------------------------------------------------------------


def test_print_summary_table(scorer):
    """Print the full benchmark summary table (use -s flag to see output)."""
    types = scorer.all_types()
    if not types:
        print("\nNo data collected — run TP tests first.")
        return

    header = f"{'Entity Type':<22} | {'TP':>3} | {'FP':>3} | {'FN':>3} | {'Precision':>9} | {'Recall':>8} | {'F1':>7}"
    separator = "-" * len(header)

    print(f"\n\n{'=' * len(header)}")
    print("  DETECTION ACCURACY BENCHMARK")
    print(f"{'=' * len(header)}")
    print(header)
    print(separator)

    for etype in types:
        tp = scorer.tp.get(etype, 0)
        fp = scorer.fp.get(etype, 0)
        fn = scorer.fn.get(etype, 0)
        p = scorer.precision(etype)
        r = scorer.recall(etype)
        f1 = scorer.f1(etype)
        print(f"{etype:<22} | {tp:>3} | {fp:>3} | {fn:>3} | {p:>8.1%} | {r:>7.1%} | {f1:>6.1%}")

    print(separator)
    total_tp = sum(scorer.tp.values())
    total_fp = sum(scorer.fp.values())
    total_fn = sum(scorer.fn.values())
    print(
        f"{'OVERALL':<22} | {total_tp:>3} | {total_fp:>3} | {total_fn:>3} | "
        f"{scorer.overall_precision():>8.1%} | {scorer.overall_recall():>7.1%} | "
        f"{scorer.overall_f1():>6.1%}"
    )
    print(f"{'=' * len(header)}\n")
