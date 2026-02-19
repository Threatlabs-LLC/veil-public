"""Tests for rate limiting middleware."""

import pytest
from starlette.testclient import TestClient
from fastapi import FastAPI
from backend.middleware.rate_limit import RateLimitMiddleware


@pytest.fixture
def rate_limited_app():
    """Create a minimal app with aggressive rate limits for testing."""
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

    # Very low limits for testing
    app.add_middleware(RateLimitMiddleware, default_rpm=3, auth_rpm=2, gateway_rpm=5)
    return app


class TestRateLimiting:
    def test_allows_within_limit(self, rate_limited_app):
        client = TestClient(rate_limited_app)
        for _ in range(3):
            res = client.get("/api/test")
            assert res.status_code == 200

    def test_blocks_over_limit(self, rate_limited_app):
        client = TestClient(rate_limited_app)
        for _ in range(3):
            client.get("/api/test")
        # 4th request should be blocked
        res = client.get("/api/test")
        assert res.status_code == 429
        assert "rate_limit" in res.json()["error"]["type"]

    def test_rate_limit_headers_present(self, rate_limited_app):
        client = TestClient(rate_limited_app)
        res = client.get("/api/test")
        assert "X-RateLimit-Limit" in res.headers
        assert "X-RateLimit-Remaining" in res.headers

    def test_auth_has_lower_limit(self, rate_limited_app):
        client = TestClient(rate_limited_app)
        for _ in range(2):
            res = client.get("/api/auth/login")
            assert res.status_code == 200
        # 3rd auth request should be blocked
        res = client.get("/api/auth/login")
        assert res.status_code == 429

    def test_health_endpoint_not_rate_limited(self, rate_limited_app):
        client = TestClient(rate_limited_app)
        for _ in range(10):
            res = client.get("/api/health")
            assert res.status_code == 200

    def test_disabled_rate_limiter(self):
        app = FastAPI()

        @app.get("/api/test")
        async def test_endpoint():
            return {"status": "ok"}

        app.add_middleware(RateLimitMiddleware, default_rpm=1, enabled=False)
        client = TestClient(app)
        for _ in range(10):
            res = client.get("/api/test")
            assert res.status_code == 200

    def test_retry_after_header(self, rate_limited_app):
        client = TestClient(rate_limited_app)
        for _ in range(3):
            client.get("/api/test")
        res = client.get("/api/test")
        assert res.status_code == 429
        assert res.headers.get("Retry-After") == "60"
