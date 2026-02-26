"""Day 1 — Performance benchmarks.

Measures:
- Detection latency per request (small/medium/large messages)
- Sanitization pipeline throughput
- Registry with multiple detectors
- Large message handling
- Long conversation entity mapping
"""

import time

from backend.detectors.regex_detector import RegexDetector
from backend.detectors.registry import create_default_registry
from backend.core.sanitizer import Sanitizer
from backend.core.mapper import EntityMapper


# ── Test Data ────────────────────────────────────────────────────────────

SMALL_MESSAGE = "Contact john@example.com for details."

MEDIUM_MESSAGE = (
    "Hi team, please review the following:\n\n"
    "1. John Smith (SSN: 123-45-6789) reported an issue with server 192.168.1.50.\n"
    "2. Contact: john.smith@acme.com or call (555) 123-4567.\n"
    "3. Credit card on file: 4532 0151 1283 0366.\n"
    "4. Database connection: postgresql://admin:secret@db.internal:5432/production.\n"
    "5. AWS key found in config: AKIAIOSFODNN7EXAMPLE.\n"
    "6. MAC address of the device: 00:1A:2B:3C:4D:5E.\n"
    "7. Staging server at app.staging.corp is also affected.\n"
)

LARGE_MESSAGE = MEDIUM_MESSAGE * 20  # ~4KB of text with many entities

HUGE_MESSAGE = MEDIUM_MESSAGE * 100  # ~20KB of text


# ══════════════════════════════════════════════════════════════════════════
# REGEX DETECTOR PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════


class TestRegexDetectorPerformance:
    """Benchmark the regex detector alone."""

    def setup_method(self):
        self.detector = RegexDetector()

    def test_small_message_under_5ms(self):
        """Small message detection should complete in <5ms."""
        start = time.perf_counter()
        for _ in range(100):
            self.detector.detect(SMALL_MESSAGE)
        elapsed = (time.perf_counter() - start) / 100 * 1000

        assert elapsed < 5, f"Small message detection took {elapsed:.2f}ms (target: <5ms)"

    def test_medium_message_under_10ms(self):
        """Medium message detection should complete in <10ms."""
        start = time.perf_counter()
        for _ in range(100):
            self.detector.detect(MEDIUM_MESSAGE)
        elapsed = (time.perf_counter() - start) / 100 * 1000

        assert elapsed < 10, f"Medium message detection took {elapsed:.2f}ms (target: <10ms)"

    def test_large_message_under_50ms(self):
        """Large message (~4KB) detection should complete in <50ms."""
        start = time.perf_counter()
        for _ in range(20):
            self.detector.detect(LARGE_MESSAGE)
        elapsed = (time.perf_counter() - start) / 20 * 1000

        assert elapsed < 50, f"Large message detection took {elapsed:.2f}ms (target: <50ms)"

    def test_huge_message_under_200ms(self):
        """Huge message (~20KB) detection should complete in <200ms."""
        start = time.perf_counter()
        for _ in range(5):
            self.detector.detect(HUGE_MESSAGE)
        elapsed = (time.perf_counter() - start) / 5 * 1000

        assert elapsed < 200, f"Huge message detection took {elapsed:.2f}ms (target: <200ms)"

    def test_clean_text_fast(self):
        """Clean text (no PII) should be faster since fewer regex matches."""
        clean = "This is a perfectly clean message with no sensitive data. " * 50
        start = time.perf_counter()
        for _ in range(100):
            self.detector.detect(clean)
        elapsed = (time.perf_counter() - start) / 100 * 1000

        assert elapsed < 10, f"Clean text detection took {elapsed:.2f}ms (target: <10ms)"


# ══════════════════════════════════════════════════════════════════════════
# FULL SANITIZATION PIPELINE PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════


class TestSanitizationPipelinePerformance:
    """Benchmark the full detect → map → replace pipeline."""

    def _create_sanitizer(self):
        registry = create_default_registry()
        mapper = EntityMapper(session_id="perf-test")
        return Sanitizer(registry, mapper)

    def test_small_message_pipeline_under_10ms(self):
        """Full pipeline for small message should complete in <10ms."""
        sanitizer = self._create_sanitizer()
        start = time.perf_counter()
        for _ in range(100):
            sanitizer.sanitize(SMALL_MESSAGE)
        elapsed = (time.perf_counter() - start) / 100 * 1000

        assert elapsed < 10, f"Small pipeline took {elapsed:.2f}ms (target: <10ms)"

    def test_medium_message_pipeline_under_20ms(self):
        """Full pipeline for medium message should complete in <20ms."""
        sanitizer = self._create_sanitizer()
        start = time.perf_counter()
        for _ in range(50):
            sanitizer.sanitize(MEDIUM_MESSAGE)
        elapsed = (time.perf_counter() - start) / 50 * 1000

        assert elapsed < 20, f"Medium pipeline took {elapsed:.2f}ms (target: <20ms)"

    def test_large_message_pipeline_under_500ms(self):
        """Full pipeline for large message (~4KB) should complete in <500ms (includes NER)."""
        sanitizer = self._create_sanitizer()
        start = time.perf_counter()
        for _ in range(10):
            sanitizer.sanitize(LARGE_MESSAGE)
        elapsed = (time.perf_counter() - start) / 10 * 1000

        assert elapsed < 500, f"Large pipeline took {elapsed:.2f}ms (target: <500ms)"

    def test_huge_message_pipeline_under_3000ms(self):
        """Full pipeline for huge message (~20KB) should complete in <3s (includes NER)."""
        sanitizer = self._create_sanitizer()
        start = time.perf_counter()
        for _ in range(3):
            sanitizer.sanitize(HUGE_MESSAGE)
        elapsed = (time.perf_counter() - start) / 3 * 1000

        assert elapsed < 3000, f"Huge pipeline took {elapsed:.2f}ms (target: <3000ms)"


# ══════════════════════════════════════════════════════════════════════════
# ENTITY MAPPER PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════


class TestEntityMapperPerformance:
    """Benchmark the entity mapper (placeholder creation + lookup)."""

    def test_mapper_1000_entities(self):
        """Creating 1000 unique entity mappings should be fast."""
        mapper = EntityMapper(session_id="perf-test")
        start = time.perf_counter()

        for i in range(1000):
            mapper.get_or_create_placeholder(
                entity_type="EMAIL",
                original_value=f"user{i}@example.com",
                confidence=0.99,
                detection_method="regex",
                start=0,
                end=10,
            )

        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 100, f"1000 entity mappings took {elapsed:.2f}ms (target: <100ms)"

    def test_mapper_repeated_lookups_fast(self):
        """Looking up existing mappings should be O(1)."""
        mapper = EntityMapper(session_id="perf-test")
        # Pre-populate
        for i in range(100):
            mapper.get_or_create_placeholder(
                entity_type="EMAIL",
                original_value=f"user{i}@example.com",
                confidence=0.99,
                detection_method="regex",
                start=0,
                end=10,
            )

        start = time.perf_counter()
        for _ in range(1000):
            mapper.get_or_create_placeholder(
                entity_type="EMAIL",
                original_value="user50@example.com",
                confidence=0.99,
                detection_method="regex",
                start=0,
                end=10,
            )
        elapsed = (time.perf_counter() - start) * 1000

        assert elapsed < 50, f"1000 repeated lookups took {elapsed:.2f}ms (target: <50ms)"


# ══════════════════════════════════════════════════════════════════════════
# THROUGHPUT
# ══════════════════════════════════════════════════════════════════════════


class TestThroughput:
    """Measure requests per second for the detection pipeline."""

    def test_throughput_medium_messages(self):
        """Should handle at least 100 medium messages per second."""
        detector = RegexDetector()
        iterations = 200
        start = time.perf_counter()

        for _ in range(iterations):
            detector.detect(MEDIUM_MESSAGE)

        elapsed = time.perf_counter() - start
        throughput = iterations / elapsed

        assert throughput >= 100, (
            f"Throughput: {throughput:.0f} msgs/sec (target: >=100)"
        )

    def test_throughput_small_messages(self):
        """Should handle at least 500 small messages per second."""
        detector = RegexDetector()
        iterations = 1000
        start = time.perf_counter()

        for _ in range(iterations):
            detector.detect(SMALL_MESSAGE)

        elapsed = time.perf_counter() - start
        throughput = iterations / elapsed

        assert throughput >= 500, (
            f"Throughput: {throughput:.0f} msgs/sec (target: >=500)"
        )


# ══════════════════════════════════════════════════════════════════════════
# DETECTION CORRECTNESS UNDER LOAD
# ══════════════════════════════════════════════════════════════════════════


class TestCorrectnessUnderLoad:
    """Ensure detection results are consistent under high throughput."""

    def test_consistent_results_across_runs(self):
        """Same input should always produce same results."""
        detector = RegexDetector()
        baseline = detector.detect(MEDIUM_MESSAGE)
        baseline_types = sorted([(r.entity_type, r.value) for r in baseline])

        for _ in range(100):
            results = detector.detect(MEDIUM_MESSAGE)
            result_types = sorted([(r.entity_type, r.value) for r in results])
            assert result_types == baseline_types

    def test_sanitization_deterministic(self):
        """Sanitization should produce same output for same input."""
        registry = create_default_registry()
        mapper = EntityMapper(session_id="perf-test")
        sanitizer = Sanitizer(registry, mapper)

        first_result = sanitizer.sanitize(MEDIUM_MESSAGE)
        for _ in range(50):
            result = sanitizer.sanitize(MEDIUM_MESSAGE)
            assert result.sanitized_text == first_result.sanitized_text
            assert result.entity_count == first_result.entity_count
