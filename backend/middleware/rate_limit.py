"""Rate limiting middleware — sliding window per-user and per-org.

Uses in-memory storage for MVP. Production should use Redis.
"""

import time
from collections import defaultdict

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting with configurable limits.

    Limits:
        - Default: 60 requests per minute per IP
        - Gateway (/v1/): 120 requests per minute per IP
        - Auth (/api/auth/): 10 requests per minute per IP (brute-force protection)
    """

    def __init__(self, app, default_rpm: int = 60, gateway_rpm: int = 120,
                 auth_rpm: int = 10, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        self.default_rpm = default_rpm
        self.gateway_rpm = gateway_rpm
        self.auth_rpm = auth_rpm
        # {bucket_key: [timestamps]}
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._window = 60.0  # 1 minute window

    def _get_limit(self, path: str) -> int:
        if path.startswith("/v1/"):
            return self.gateway_rpm
        if path.startswith("/api/auth/"):
            return self.auth_rpm
        return self.default_rpm

    def _get_key(self, request: Request, path: str) -> str:
        ip = request.client.host if request.client else "unknown"
        if path.startswith("/v1/"):
            return f"gw:{ip}"
        if path.startswith("/api/auth/"):
            return f"auth:{ip}"
        return f"api:{ip}"

    def _is_rate_limited(self, key: str, limit: int) -> tuple[bool, int]:
        """Check if the key is rate limited. Returns (limited, remaining)."""
        now = time.time()
        cutoff = now - self._window

        # Prune old entries
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

        key = self._get_key(request, path)
        limit = self._get_limit(path)
        limited, remaining = self._is_rate_limited(key, limit)

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
