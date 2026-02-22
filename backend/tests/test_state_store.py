"""Tests for the shared state store (in-memory fallback)."""

import time
from unittest.mock import patch

from backend.core import state_store


def _clear():
    """Reset in-memory store between tests."""
    state_store._mem_store.clear()
    state_store._redis_client = None
    state_store._redis_checked = True  # Force in-memory mode


class TestStateStoreSetGetDelete:
    def setup_method(self):
        _clear()

    def test_set_and_get(self):
        state_store.set("key1", "val1", ttl_seconds=60)
        assert state_store.get("key1") == "val1"

    def test_get_missing_returns_none(self):
        assert state_store.get("nonexistent") is None

    def test_delete(self):
        state_store.set("key1", "val1", ttl_seconds=60)
        state_store.delete("key1")
        assert state_store.get("key1") is None

    def test_delete_missing_key_no_error(self):
        state_store.delete("nonexistent")  # Should not raise

    def test_ttl_expiry(self):
        state_store.set("key1", "val1", ttl_seconds=1)
        assert state_store.get("key1") == "val1"
        # Simulate time passing
        state_store._mem_store["key1"] = ("val1", time.time() - 1)
        assert state_store.get("key1") is None

    def test_overwrite_value(self):
        state_store.set("key1", "val1", ttl_seconds=60)
        state_store.set("key1", "val2", ttl_seconds=60)
        assert state_store.get("key1") == "val2"


class TestStateStoreIncrement:
    def setup_method(self):
        _clear()

    def test_increment_new_key(self):
        assert state_store.increment("counter", ttl_seconds=60) == 1

    def test_increment_existing_key(self):
        state_store.increment("counter", ttl_seconds=60)
        assert state_store.increment("counter", ttl_seconds=60) == 2

    def test_increment_multiple(self):
        for i in range(5):
            result = state_store.increment("counter", ttl_seconds=60)
        assert result == 5

    def test_increment_expired_resets(self):
        state_store.increment("counter", ttl_seconds=1)
        state_store.increment("counter", ttl_seconds=1)
        # Simulate expiry
        state_store._mem_store["counter"] = ("2", time.time() - 1)
        assert state_store.increment("counter", ttl_seconds=60) == 1


class TestStateStoreGetInt:
    def setup_method(self):
        _clear()

    def test_get_int_missing(self):
        assert state_store.get_int("missing") == 0

    def test_get_int_after_set(self):
        state_store.set("counter", "5", ttl_seconds=60)
        assert state_store.get_int("counter") == 5

    def test_get_int_after_increment(self):
        state_store.increment("counter", ttl_seconds=60)
        state_store.increment("counter", ttl_seconds=60)
        assert state_store.get_int("counter") == 2

    def test_get_int_non_numeric(self):
        state_store.set("key", "abc", ttl_seconds=60)
        assert state_store.get_int("key") == 0


class TestStateStoreDeletePattern:
    def setup_method(self):
        _clear()

    def test_delete_pattern(self):
        state_store.set("veil:reset:aaa", "user1", ttl_seconds=60)
        state_store.set("veil:reset:bbb", "user2", ttl_seconds=60)
        state_store.set("veil:lockout:ccc", "3", ttl_seconds=60)
        state_store.delete_pattern("veil:reset:")
        assert state_store.get("veil:reset:aaa") is None
        assert state_store.get("veil:reset:bbb") is None
        assert state_store.get("veil:lockout:ccc") == "3"

    def test_delete_pattern_no_match(self):
        state_store.set("veil:lockout:x", "1", ttl_seconds=60)
        state_store.delete_pattern("veil:reset:")  # No matching keys
        assert state_store.get("veil:lockout:x") == "1"


class TestStateStoreCleanup:
    def setup_method(self):
        _clear()

    def test_cleanup_expired(self):
        state_store.set("key1", "val1", ttl_seconds=60)
        state_store.set("key2", "val2", ttl_seconds=1)
        # Expire key2
        state_store._mem_store["key2"] = ("val2", time.time() - 1)
        state_store._cleanup_expired()
        assert state_store.get("key1") == "val1"
        assert "key2" not in state_store._mem_store


class TestShouldRunTask:
    def setup_method(self):
        _clear()

    def test_always_true_without_redis(self):
        """Without Redis, should_run_task always returns True (single worker)."""
        assert state_store.should_run_task("test_task", 60) is True
        # Calling again still True since no Redis to hold the lock
        assert state_store.should_run_task("test_task", 60) is True

    def test_always_true_on_different_tasks(self):
        assert state_store.should_run_task("task_a", 60) is True
        assert state_store.should_run_task("task_b", 60) is True
