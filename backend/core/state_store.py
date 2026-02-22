"""Shared key-value state store — Redis-backed with in-memory fallback.

Used for auth state (reset tokens, login lockout, OAuth CSRF) and any
ephemeral data that needs to survive across multiple uvicorn workers.

When VEILCHAT_REDIS_URL is configured, uses Redis for distributed state.
Otherwise falls back to in-memory dicts (fine for single-worker / self-hosted).
"""

import logging
import time

logger = logging.getLogger(__name__)

# Redis client — lazy-initialized, shared with rate_limit.py
_redis_client = None
_redis_checked = False


def _get_redis():
    """Lazy-init Redis client if configured."""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client

    _redis_checked = True
    from backend.config import settings
    if settings.redis_url:
        try:
            import redis
            _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
            _redis_client.ping()
            logger.info("State store using Redis backend")
        except Exception as e:
            logger.warning(f"Redis connection failed, falling back to in-memory: {e}")
            _redis_client = None
    return _redis_client


# In-memory fallback: key -> (value, expiry_timestamp)
_mem_store: dict[str, tuple[str, float]] = {}


def _cleanup_expired() -> None:
    """Remove expired entries from in-memory store."""
    now = time.time()
    expired = [k for k, (_, exp) in _mem_store.items() if exp <= now]
    for k in expired:
        del _mem_store[k]


def set(key: str, value: str, ttl_seconds: int) -> None:
    """Store a value with TTL."""
    r = _get_redis()
    if r:
        try:
            r.setex(key, ttl_seconds, value)
            return
        except Exception:
            pass
    _mem_store[key] = (value, time.time() + ttl_seconds)


def get(key: str) -> str | None:
    """Get a value, or None if missing/expired."""
    r = _get_redis()
    if r:
        try:
            return r.get(key)
        except Exception:
            pass
    entry = _mem_store.get(key)
    if entry is None:
        return None
    value, expiry = entry
    if time.time() > expiry:
        _mem_store.pop(key, None)
        return None
    return value


def delete(key: str) -> None:
    """Delete a key."""
    r = _get_redis()
    if r:
        try:
            r.delete(key)
            return
        except Exception:
            pass
    _mem_store.pop(key, None)


def increment(key: str, ttl_seconds: int) -> int:
    """Increment a counter. Creates with value 1 if missing. Returns new count."""
    r = _get_redis()
    if r:
        try:
            val = r.incr(key)
            if val == 1:
                r.expire(key, ttl_seconds)
            return val
        except Exception:
            pass
    # In-memory fallback
    entry = _mem_store.get(key)
    now = time.time()
    if entry is None or now > entry[1]:
        _mem_store[key] = ("1", now + ttl_seconds)
        return 1
    count = int(entry[0]) + 1
    _mem_store[key] = (str(count), entry[1])  # keep original expiry
    return count


def get_int(key: str) -> int:
    """Get an integer value, returning 0 if missing/expired."""
    val = get(key)
    if val is None:
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def should_run_task(task_name: str, interval_seconds: int) -> bool:
    """Check if a periodic task should run now.

    Uses Redis SETNX to coordinate across workers — only one worker
    acquires the lock per interval.  Without Redis (single-worker /
    self-hosted), always returns True.
    """
    r = _get_redis()
    if not r:
        return True  # No Redis = single worker, always run
    key = f"veil:task:{task_name}"
    try:
        acquired = r.set(key, "1", nx=True, ex=interval_seconds)
        return bool(acquired)
    except Exception:
        return True  # Redis error, run anyway (tasks are idempotent)


def delete_pattern(prefix: str) -> None:
    """Delete all keys matching a prefix. Use sparingly."""
    r = _get_redis()
    if r:
        try:
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor, match=f"{prefix}*", count=100)
                if keys:
                    r.delete(*keys)
                if cursor == 0:
                    break
            return
        except Exception:
            pass
    # In-memory fallback
    to_delete = [k for k in _mem_store if k.startswith(prefix)]
    for k in to_delete:
        del _mem_store[k]
