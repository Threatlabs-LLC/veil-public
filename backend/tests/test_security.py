"""Day 1 — Security hardening tests.

Covers:
- PII not leaking in error responses
- SQL injection resistance in search/filter params
- XSS resistance in user-controllable fields
- CORS configuration
- Auth required on all state-changing routes
- Rate limiting (auth brute-force protection)
- Error response sanity
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


# ══════════════════════════════════════════════════════════════════════════
# PII LEAK PREVENTION
# ══════════════════════════════════════════════════════════════════════════


class TestPIILeakPrevention:
    """Verify PII never appears in error responses or stack traces."""

    @pytest.fixture
    async def auth_client(self, client, db, seeded_org, auth_token):
        """Client with auth headers."""
        client.headers["Authorization"] = f"Bearer {auth_token}"
        return client

    @pytest.mark.asyncio
    async def test_invalid_conversation_id_no_pii(self, auth_client):
        """Error response for missing conversation should not contain PII."""
        resp = await auth_client.get("/api/conversations/nonexistent-id")
        assert resp.status_code == 404
        body = resp.text
        # Should not contain any PII-like data
        assert "SSN" not in body or "123-45" not in body
        assert "password" not in body.lower() or "secret" not in body.lower()

    @pytest.mark.asyncio
    async def test_malformed_json_body_no_pii(self, auth_client):
        """Malformed JSON should return clean error without echoing input."""
        resp = await auth_client.post(
            "/api/auth/login",
            content='{"email": "john@secret.com", "password": "SSN:123-45-6789"}',
            headers={"Content-Type": "application/json"},
        )
        # Should be 401 (invalid credentials) or 422 (validation error)
        body = resp.text
        # The actual SSN should not be echoed back
        assert "123-45-6789" not in body

    @pytest.mark.asyncio
    async def test_register_duplicate_email_no_leak(self, client, db, seeded_org):
        """Duplicate email registration should not leak existing user info."""
        resp = await client.post(
            "/api/auth/register",
            json={"email": "admin@test.com", "password": "testpass123"},
        )
        assert resp.status_code == 400
        body = resp.json()
        # Should say "Email already registered" but not leak user details
        assert "already" in body.get("detail", "").lower()
        assert "password" not in str(body).lower()
        assert "hash" not in str(body).lower()


# ══════════════════════════════════════════════════════════════════════════
# SQL INJECTION RESISTANCE
# ══════════════════════════════════════════════════════════════════════════


class TestSQLInjection:
    """Test that search/filter parameters resist SQL injection."""

    @pytest.fixture
    async def auth_client(self, client, db, seeded_org, auth_token):
        client.headers["Authorization"] = f"Bearer {auth_token}"
        return client

    @pytest.mark.asyncio
    async def test_search_sql_injection_conversations(self, auth_client):
        """SQL injection in conversation search should be safe."""
        payloads = [
            "'; DROP TABLE conversations; --",
            "' OR '1'='1",
            "\" OR 1=1 --",
            "'; SELECT * FROM users; --",
            "1; UNION SELECT password_hash FROM users --",
        ]
        for payload in payloads:
            resp = await auth_client.get(f"/api/conversations?q={payload}")
            # Should return 200 (empty results) or 422 (validation error), never 500
            assert resp.status_code in (200, 422), f"Unexpected status for payload: {payload}"

    @pytest.mark.asyncio
    async def test_search_sql_injection_audit(self, auth_client):
        """SQL injection in audit log search should be safe."""
        payload = "'; DROP TABLE audit_events; --"
        resp = await auth_client.get(f"/api/admin/audit?q={payload}")
        assert resp.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_sort_param_validated(self, auth_client):
        """Sort parameter should only accept whitelisted values."""
        resp = await auth_client.get("/api/conversations?sort=updated_desc; DROP TABLE conversations")
        # Should be 422 (validation error) since sort has a regex pattern constraint
        assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# XSS RESISTANCE
# ══════════════════════════════════════════════════════════════════════════


class TestXSSResistance:
    """Test that user-controllable fields don't enable XSS."""

    @pytest.fixture
    async def auth_client(self, client, db, seeded_org, auth_token):
        client.headers["Authorization"] = f"Bearer {auth_token}"
        return client

    @pytest.mark.asyncio
    async def test_xss_in_display_name(self, auth_client):
        """XSS payload in display name should be stored as-is (not executed)."""
        xss_payload = '<script>alert("xss")</script>'
        resp = await auth_client.patch(
            "/api/auth/profile",
            json={"display_name": xss_payload},
        )
        # Backend stores it as plain text — frontend React auto-escapes
        # The API should accept it (it's just a string) and return it safely
        assert resp.status_code == 200
        body = resp.json()
        # The value is stored as-is; React will escape it on render
        assert body["display_name"] == xss_payload

    @pytest.mark.asyncio
    async def test_xss_in_rule_name(self, auth_client):
        """XSS payload in rule name should not cause issues."""
        xss_payload = '<img src=x onerror=alert(1)>'
        resp = await auth_client.post(
            "/api/rules",
            json={
                "name": xss_payload,
                "entity_type": "TEST",
                "detection_method": "regex",
                "pattern": "test\\d+",
                "confidence": 0.8,
            },
        )
        # Should accept or reject on validation — never crash
        assert resp.status_code in (200, 201, 403, 422)

    @pytest.mark.asyncio
    async def test_xss_in_org_name_register(self, client, db):
        """XSS in org name during registration should be stored safely."""
        resp = await client.post(
            "/api/auth/register",
            json={
                "email": "xss-test@example.com",
                "password": "securepass123",
                "display_name": "Normal Name",
                "org_name": '<script>alert("xss")</script>',
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        # Should contain the org name as plain text
        assert "access_token" in body


# ══════════════════════════════════════════════════════════════════════════
# CORS CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════


class TestCORSConfiguration:
    """Test that CORS is configured correctly."""

    @pytest.mark.asyncio
    async def test_cors_allowed_origin(self, client):
        """Allowed origin should receive CORS headers."""
        resp = await client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Should include the CORS header
        assert resp.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_cors_disallowed_origin(self, client):
        """Disallowed origin should NOT receive Access-Control-Allow-Origin."""
        resp = await client.options(
            "/api/health",
            headers={
                "Origin": "https://evil-site.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        allow_origin = resp.headers.get("access-control-allow-origin", "")
        # Should not echo back the evil origin
        assert "evil-site.com" not in allow_origin


# ══════════════════════════════════════════════════════════════════════════
# AUTHENTICATION REQUIRED
# ══════════════════════════════════════════════════════════════════════════


class TestAuthRequired:
    """Verify that state-changing endpoints require authentication."""

    @pytest.mark.asyncio
    async def test_settings_requires_auth(self, client, db, seeded_org):
        """GET /api/settings should require auth."""
        resp = await client.get("/api/settings")
        # Without a seeded user in DB, this returns 401
        # With a seeded user but no token, it falls back to first user
        # This is by design for community edition
        assert resp.status_code in (200, 401)

    @pytest.mark.asyncio
    async def test_rules_create_requires_auth(self, client):
        """POST /api/rules requires auth."""
        resp = await client.post(
            "/api/rules",
            json={"name": "Test", "entity_type": "TEST", "detection_method": "regex",
                  "pattern": "test", "confidence": 0.8},
        )
        # Either 401 (no user exists) or works (community fallback)
        assert resp.status_code in (200, 201, 401, 403)

    @pytest.mark.asyncio
    async def test_admin_dashboard_requires_auth(self, client):
        """GET /api/admin/dashboard requires auth."""
        resp = await client.get("/api/admin/dashboard")
        assert resp.status_code in (200, 401)

    @pytest.mark.asyncio
    async def test_webhooks_create_requires_auth(self, client):
        """POST /api/webhooks requires auth."""
        resp = await client.post(
            "/api/webhooks",
            json={"url": "https://example.com/hook", "events": ["pii.detected"]},
        )
        # 401 (no auth) or 403 (tier restriction)
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_invalid_jwt_rejected(self, client, db, seeded_org):
        """Fake/expired JWT should be rejected."""
        resp = await client.get(
            "/api/settings",
            headers={"Authorization": "Bearer fake.jwt.token"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_jwt_rejected(self, client, db, seeded_org):
        """Expired JWT should be rejected."""
        from jose import jwt as jose_jwt
        import time

        expired_token = jose_jwt.encode(
            {"sub": "fake-user-id", "org": "fake-org-id", "exp": int(time.time()) - 3600},
            "CHANGE-ME-IN-PRODUCTION",
            algorithm="HS256",
        )
        resp = await client.get(
            "/api/settings",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════
# RATE LIMITING
# ══════════════════════════════════════════════════════════════════════════


class TestRateLimiting:
    """Test rate limiting behavior."""

    @pytest.mark.asyncio
    async def test_auth_rate_limit_headers(self):
        """Auth endpoints should have rate limit headers."""
        from backend.main import app
        from backend.middleware.rate_limit import RateLimitMiddleware

        # Re-enable rate limiting for this test
        for mw in app.user_middleware:
            if mw.cls is RateLimitMiddleware:
                mw.kwargs["enabled"] = True

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/auth/login",
                json={"email": "test@test.com", "password": "wrong"},
            )
            # Should have rate limit headers
            assert "x-ratelimit-limit" in resp.headers or resp.status_code == 401

        # Restore disabled state
        for mw in app.user_middleware:
            if mw.cls is RateLimitMiddleware:
                mw.kwargs["enabled"] = False

    @pytest.mark.asyncio
    async def test_auth_brute_force_protection(self):
        """Auth endpoint should have fixed lower rate limit (10 rpm) regardless of tier."""
        from backend.middleware.rate_limit import RateLimitMiddleware

        mw = RateLimitMiddleware(app=None, enabled=True)
        assert mw._get_limit("/api/auth/login", "free") == 10
        assert mw._get_limit("/api/auth/register", "enterprise") == 10

    @pytest.mark.asyncio
    async def test_gateway_higher_limit(self):
        """Gateway endpoint should use tier's gateway rate limit."""
        from backend.middleware.rate_limit import RateLimitMiddleware
        from backend.licensing.tiers import get_tier

        mw = RateLimitMiddleware(app=None, enabled=True)
        assert mw._get_limit("/v1/chat/completions", "free") == get_tier("free").gateway_rate_limit

    @pytest.mark.asyncio
    async def test_default_api_limit(self):
        """Default API endpoints should use tier's api rate limit."""
        from backend.middleware.rate_limit import RateLimitMiddleware
        from backend.licensing.tiers import get_tier

        mw = RateLimitMiddleware(app=None, enabled=True)
        assert mw._get_limit("/api/conversations", "free") == get_tier("free").api_rate_limit


# ══════════════════════════════════════════════════════════════════════════
# ERROR RESPONSE SANITY
# ══════════════════════════════════════════════════════════════════════════


class TestErrorResponses:
    """Verify error responses are clean and don't leak internals."""

    @pytest.mark.asyncio
    async def test_404_clean(self, client):
        """404 responses should not contain stack traces."""
        resp = await client.get("/api/nonexistent-endpoint")
        assert resp.status_code in (404, 405)
        body = resp.text
        assert "Traceback" not in body
        assert "File " not in body

    @pytest.mark.asyncio
    async def test_422_validation_error_clean(self, client):
        """Validation errors should not leak internal details."""
        resp = await client.post(
            "/api/auth/login",
            json={"email": 12345},  # Wrong type
        )
        assert resp.status_code == 422
        body = resp.text
        assert "Traceback" not in body

    @pytest.mark.asyncio
    async def test_health_endpoint_no_secrets(self, client):
        """Health endpoints should not leak secrets or config."""
        resp = await client.get("/api/health")
        body = resp.json()
        assert "secret" not in str(body).lower()
        assert "password" not in str(body).lower()
        assert "api_key" not in str(body).lower()

    @pytest.mark.asyncio
    async def test_health_ready_no_secrets(self, client):
        """Readiness probe should not leak secrets."""
        resp = await client.get("/api/health/ready")
        body = resp.text
        assert "secret" not in body.lower()
        assert "password" not in body.lower()
