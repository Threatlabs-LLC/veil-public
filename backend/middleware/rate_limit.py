"""Rate limiting middleware — tier-aware, per-org sliding window.

Uses in-memory storage by default. When VEILCHAT_REDIS_URL is configured,
uses Redis INCR+EXPIRE for distributed rate limiting across instances.

Rate limits are determined by the organization's tier:
  - Authenticated requests: org's tier api_rate_limit / gateway_rate_limit
  - Unauthenticated (auth endpoints): fixed 10 RPM per IP (brute-force protection)
  - Fallback for bad/missing tokens: free tier limits per IP
"""

import logging
import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Redis client — lazy-initialized
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
            logger.info("Rate limiter using Redis backend")
        except Exception as e:
            logger.warning(f"Redis connection failed, falling back to in-memory: {e}")
            _redis_client = None
    return _redis_client


# Lightweight org tier cache: {org_id: (tier, expiry_time)}
# Avoids DB hit on every request. Refreshed every 5 minutes.
_org_tier_cache: dict[str, tuple[str, float]] = {}
_TIER_CACHE_TTL = 300  # 5 minutes


def _extract_org_id(request: Request) -> str | None:
    """Extract org_id from JWT in the Authorization header."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]
    try:
        from jose import jwt
        from backend.config import settings
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return payload.get("org")
    except Exception:
        return None


async def _get_org_tier(org_id: str) -> str:
    """Get org tier with caching. Falls back to 'free' on any error."""
    now = time.time()
    cached = _org_tier_cache.get(org_id)
    if cached and cached[1] > now:
        return cached[0]

    try:
        from backend.db.session import async_session
        from backend.models.organization import Organization
        async with async_session() as db:
            org = await db.get(Organization, org_id)
            tier = org.tier if org else "free"
        _org_tier_cache[org_id] = (tier, now + _TIER_CACHE_TTL)
        return tier
    except Exception:
        return "free"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Tier-aware rate limiting.

    For authenticated requests, uses the org's tier rate limits.
    For auth endpoints, uses a fixed 10 RPM per IP (brute-force protection).
    Falls back to free tier limits for unauthenticated/invalid requests.
    """

    AUTH_RPM = 10  # Fixed — brute-force protection on login/register

    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        # In-memory fallback: {bucket_key: [timestamps]}
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._window = 60  # 1 minute window (seconds)

    def _get_limit(self, path: str, tier: str) -> int:
        """Get rate limit based on path and org tier."""
        if path.startswith("/api/auth/"):
            return self.AUTH_RPM
        from backend.licensing.tiers import get_tier
        tier_def = get_tier(tier)
        if path.startswith("/v1/"):
            return tier_def.gateway_rate_limit
        return tier_def.api_rate_limit

    def _get_key(self, request: Request, path: str, org_id: str | None) -> str:
        """Build rate limit bucket key. Uses org_id if available, else IP."""
        if org_id:
            if path.startswith("/v1/"):
                return f"rl:gw:{org_id}"
            return f"rl:api:{org_id}"
        ip = request.client.host if request.client else "unknown"
        if path.startswith("/api/auth/"):
            return f"rl:auth:{ip}"
        return f"rl:api:{ip}"

    def _check_redis(self, key: str, limit: int) -> tuple[bool, int]:
        """Check rate limit using Redis INCR + EXPIRE."""
        r = _get_redis()
        if not r:
            return self._check_memory(key, limit)

        try:
            current = r.incr(key)
            if current == 1:
                r.expire(key, self._window)
            remaining = max(0, limit - current)
            return current > limit, remaining
        except Exception:
            # Redis error — fall back to in-memory
            return self._check_memory(key, limit)

    def _check_memory(self, key: str, limit: int) -> tuple[bool, int]:
        """Check rate limit using in-memory sliding window."""
        now = time.time()
        cutoff = now - self._window

        timestamps = self._requests[key]
        self._requests[key] = [t for t in timestamps if t > cutoff]

        current_count = len(self._requests[key])
        if current_count >= limit:
            return True, 0

        self._requests[key].append(now)
        return False, limit - current_count - 1

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        path = request.url.path

        # Skip rate limiting for health checks and static files
        if path == "/api/health" or not path.startswith(("/api/", "/v1/")):
            return await call_next(request)

        # Extract org from JWT for tier-aware, per-org rate limits
        org_id = _extract_org_id(request)
        tier = "free"
        if org_id:
            tier = await _get_org_tier(org_id)
        key = self._get_key(request, path, org_id)
        limit = self._get_limit(path, tier)
        limited, remaining = self._check_redis(key, limit)

        if limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "message": "Rate limit exceeded. Please try again later.",
                        "type": "rate_limit_error",
                        "code": "rate_limited",
                    }
                },
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
