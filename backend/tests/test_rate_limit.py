"""Tests for rate limiting middleware."""

import pytest
from starlette.testclient import TestClient
from fastapi import FastAPI
from backend.middleware.rate_limit import RateLimitMiddleware


@pytest.fixture
def rate_limited_app():
    """Create a minimal app with rate limits for testing.

    Uses default tier-aware limits (free tier: 60 API, 120 gateway).
    Auth endpoints always use 10 RPM.
    """
    app = FastAPI()

    @app.get("/api/test")
    async def test_endpoint():
        return {"status": "ok"}

    @app.get("/api/auth/login")
    async def auth_endpoint():
        return {"status": "ok"}

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    app.add_middleware(RateLimitMiddleware)
    return app


class TestRateLimiting:
    def test_allows_within_limit(self, rate_limited_app):
        """Requests within the free tier limit should succeed."""
        client = TestClient(rate_limited_app)
        for _ in range(10):
            res = client.get("/api/test")
            assert res.status_code == 200

    def test_rate_limit_headers_present(self, rate_limited_app):
        client = TestClient(rate_limited_app)
        res = client.get("/api/test")
        assert "X-RateLimit-Limit" in res.headers
        assert "X-RateLimit-Remaining" in res.headers

    def test_auth_has_lower_limit(self, rate_limited_app):
        """Auth endpoint uses fixed 10 RPM regardless of tier."""
        client = TestClient(rate_limited_app)
        for _ in range(10):
            res = client.get("/api/auth/login")
            assert res.status_code == 200
        # 11th auth request should be blocked
        res = client.get("/api/auth/login")
        assert res.status_code == 429

    def test_health_endpoint_not_rate_limited(self, rate_limited_app):
        client = TestClient(rate_limited_app)
        for _ in range(100):
            res = client.get("/api/health")
            assert res.status_code == 200

    def test_disabled_rate_limiter(self):
        app = FastAPI()

        @app.get("/api/test")
        async def test_endpoint():
            return {"status": "ok"}

        app.add_middleware(RateLimitMiddleware, enabled=False)
        client = TestClient(app)
        for _ in range(100):
            res = client.get("/api/test")
            assert res.status_code == 200

    def test_retry_after_header(self, rate_limited_app):
        """429 responses include Retry-After header."""
        client = TestClient(rate_limited_app)
        # Exceed auth limit (10 RPM)
        for _ in range(10):
            client.get("/api/auth/login")
        res = client.get("/api/auth/login")
        assert res.status_code == 429
        assert res.headers.get("Retry-After") == "60"

    def test_tier_aware_limits(self):
        """Rate limits should come from tier definitions."""
        from backend.licensing.tiers import get_tier

        mw = RateLimitMiddleware(app=None, enabled=True)

        # Free tier
        free_def = get_tier("free")
        assert mw._get_limit("/api/test", "free") == free_def.api_rate_limit
        assert mw._get_limit("/v1/chat/completions", "free") == free_def.gateway_rate_limit

        # Team tier
        team_def = get_tier("team")
        assert mw._get_limit("/api/test", "team") == team_def.api_rate_limit
        assert mw._get_limit("/v1/chat/completions", "team") == team_def.gateway_rate_limit

        # Auth is always fixed
        assert mw._get_limit("/api/auth/login", "free") == 10
        assert mw._get_limit("/api/auth/login", "enterprise") == 10
