"""API integration tests — auth, rules, policies, settings, admin."""

import pytest

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


# ── Helper ─────────────────────────────────────────────────────────────


async def register_user(client: AsyncClient, email="test@example.com",
                        password="TestPass123!", org_name="TestOrg") -> dict:
    res = await client.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "org_name": org_name,
    })
    assert res.status_code == 200, res.text
    return res.json()


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Auth Tests ─────────────────────────────────────────────────────────


class TestAuthRegister:
    async def test_register_success(self, client):
        data = await register_user(client)
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "test@example.com"
        assert data["user"]["role"] == "owner"

    async def test_register_duplicate_email(self, client):
        await register_user(client, email="dupe@test.com")
        res = await client.post("/api/auth/register", json={
            "email": "dupe@test.com",
            "password": "TestPass123!",
        })
        assert res.status_code == 400

    async def test_register_creates_org(self, client):
        data = await register_user(client, email="org@test.com", org_name="My Org")
        assert data["user"]["organization_id"]


class TestAuthLogin:
    async def test_login_success(self, client):
        await register_user(client, email="login@test.com", password="MyPass123!")
        res = await client.post("/api/auth/login", json={
            "email": "login@test.com",
            "password": "MyPass123!",
        })
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data

    async def test_login_wrong_password(self, client):
        await register_user(client, email="loginwrong@test.com", password="RightPass!")
        res = await client.post("/api/auth/login", json={
            "email": "loginwrong@test.com",
            "password": "WrongPass!",
        })
        assert res.status_code == 401

    async def test_login_nonexistent_email(self, client):
        res = await client.post("/api/auth/login", json={
            "email": "nobody@test.com",
            "password": "Whatever!",
        })
        assert res.status_code == 401


class TestAuthMe:
    async def test_get_me_authenticated(self, client):
        data = await register_user(client, email="me@test.com")
        token = data["access_token"]
        res = await client.get("/api/auth/me", headers=auth_headers(token))
        assert res.status_code == 200
        me = res.json()
        assert me["email"] == "me@test.com"

    async def test_get_me_invalid_token(self, client):
        res = await client.get("/api/auth/me",
                               headers=auth_headers("invalid-token"))
        assert res.status_code == 401


# ── Rules CRUD Tests ───────────────────────────────────────────────────


class TestRulesAPI:
    async def _setup(self, client) -> tuple[str, dict]:
        data = await register_user(client, email=f"rules-{id(self)}@test.com")
        return data["access_token"], data

    async def test_list_rules(self, client):
        token, _ = await self._setup(client)
        res = await client.get("/api/rules", headers=auth_headers(token))
        assert res.status_code == 200
        rules = res.json()
        assert isinstance(rules, list)
        # Seeded built-in rules should be present
        assert len(rules) >= 1

    async def test_create_rule(self, client):
        token, _ = await self._setup(client)
        res = await client.post("/api/rules", headers=auth_headers(token), json={
            "name": "Employee ID",
            "entity_type": "EMPLOYEE_ID",
            "detection_method": "regex",
            "pattern": r"EMP-\d{5}",
            "confidence": 0.85,
        })
        assert res.status_code == 201
        rule = res.json()
        assert rule["name"] == "Employee ID"
        assert rule["entity_type"] == "EMPLOYEE_ID"
        assert rule["is_built_in"] is False

    async def test_create_rule_invalid_regex(self, client):
        token, _ = await self._setup(client)
        res = await client.post("/api/rules", headers=auth_headers(token), json={
            "name": "Bad",
            "entity_type": "TEST",
            "detection_method": "regex",
            "pattern": r"[invalid",
        })
        assert res.status_code == 400

    async def test_delete_custom_rule(self, client):
        token, _ = await self._setup(client)
        # Create
        res = await client.post("/api/rules", headers=auth_headers(token), json={
            "name": "Temp Rule",
            "entity_type": "TEMP",
            "detection_method": "regex",
            "pattern": r"TEMP-\d+",
        })
        rule_id = res.json()["id"]
        # Delete
        res = await client.delete(f"/api/rules/{rule_id}",
                                  headers=auth_headers(token))
        assert res.status_code == 200

    async def test_delete_builtin_rule_blocked(self, client):
        token, _ = await self._setup(client)
        # Get built-in rules
        res = await client.get("/api/rules", headers=auth_headers(token))
        rules = res.json()
        builtin = next((r for r in rules if r["is_built_in"]), None)
        if builtin:
            res = await client.delete(f"/api/rules/{builtin['id']}",
                                      headers=auth_headers(token))
            assert res.status_code == 403

    async def test_test_rule_endpoint(self, client):
        token, _ = await self._setup(client)
        # Create a rule first
        res = await client.post("/api/rules", headers=auth_headers(token), json={
            "name": "Ticket ID",
            "entity_type": "TICKET",
            "detection_method": "regex",
            "pattern": r"TICK-\d{4}",
        })
        rule_id = res.json()["id"]
        # Test it
        res = await client.post(f"/api/rules/{rule_id}/test",
                                headers=auth_headers(token),
                                json={"text": "See TICK-0042 for details"})
        assert res.status_code == 200
        data = res.json()
        assert len(data["matches"]) >= 1


# ── Policies CRUD Tests ───────────────────────────────────────────────


class TestPoliciesAPI:
    async def _setup(self, client) -> str:
        data = await register_user(client, email=f"pol-{id(self)}@test.com")
        return data["access_token"]

    async def test_list_policies(self, client):
        token = await self._setup(client)
        res = await client.get("/api/policies", headers=auth_headers(token))
        assert res.status_code == 200
        policies = res.json()
        assert isinstance(policies, list)
        # Seeded default policies
        assert len(policies) >= 1

    async def test_create_policy(self, client):
        token = await self._setup(client)
        res = await client.post("/api/policies", headers=auth_headers(token), json={
            "name": "Warn on Phone",
            "entity_type": "PHONE",
            "action": "warn",
            "severity": "low",
            "min_confidence": 0.8,
        })
        assert res.status_code == 201
        policy = res.json()
        assert policy["name"] == "Warn on Phone"
        assert policy["action"] == "warn"

    async def test_create_policy_invalid_action(self, client):
        token = await self._setup(client)
        res = await client.post("/api/policies", headers=auth_headers(token), json={
            "name": "Bad",
            "entity_type": "EMAIL",
            "action": "destroy",  # invalid
        })
        assert res.status_code == 400

    async def test_create_policy_invalid_severity(self, client):
        token = await self._setup(client)
        res = await client.post("/api/policies", headers=auth_headers(token), json={
            "name": "Bad",
            "entity_type": "EMAIL",
            "action": "redact",
            "severity": "extreme",  # invalid
        })
        assert res.status_code == 400

    async def test_update_policy(self, client):
        token = await self._setup(client)
        # Create
        res = await client.post("/api/policies", headers=auth_headers(token), json={
            "name": "To Update",
            "entity_type": "PHONE",
            "action": "warn",
        })
        policy_id = res.json()["id"]
        # Update
        res = await client.patch(f"/api/policies/{policy_id}",
                                 headers=auth_headers(token),
                                 json={"action": "block"})
        assert res.status_code == 200
        assert res.json()["action"] == "block"

    async def test_delete_custom_policy(self, client):
        token = await self._setup(client)
        res = await client.post("/api/policies", headers=auth_headers(token), json={
            "name": "Temp",
            "entity_type": "TEST",
            "action": "allow",
        })
        policy_id = res.json()["id"]
        res = await client.delete(f"/api/policies/{policy_id}",
                                  headers=auth_headers(token))
        assert res.status_code == 200


# ── Settings Tests ─────────────────────────────────────────────────────


class TestSettingsAPI:
    async def _setup(self, client) -> str:
        data = await register_user(client, email=f"set-{id(self)}@test.com")
        return data["access_token"]

    async def test_get_settings(self, client):
        token = await self._setup(client)
        res = await client.get("/api/settings", headers=auth_headers(token))
        assert res.status_code == 200
        data = res.json()
        assert "default_provider" in data
        assert "sanitization_enabled" in data

    async def test_get_settings_masks_keys(self, client):
        token = await self._setup(client)
        # First set a key
        await client.patch("/api/settings", headers=auth_headers(token),
                           json={"openai_api_key": "sk-test1234567890abcdef"})
        # Read back
        res = await client.get("/api/settings", headers=auth_headers(token))
        data = res.json()
        # Key should be masked
        assert data["openai_api_key"] != "sk-test1234567890abcdef"
        assert "***" in data["openai_api_key"] or data["openai_api_key"].startswith("sk-")

    async def test_update_settings(self, client):
        token = await self._setup(client)
        res = await client.patch("/api/settings", headers=auth_headers(token),
                                 json={"default_model": "gpt-4o"})
        assert res.status_code == 200
        data = res.json()
        assert data["default_model"] == "gpt-4o"


# ── Admin Dashboard Tests ─────────────────────────────────────────────


class TestAdminAPI:
    async def _setup(self, client) -> str:
        data = await register_user(client, email=f"admin-{id(self)}@test.com")
        return data["access_token"]

    async def test_dashboard(self, client):
        token = await self._setup(client)
        res = await client.get("/api/admin/dashboard", headers=auth_headers(token))
        assert res.status_code == 200
        data = res.json()
        assert "total_conversations" in data
        assert "total_messages" in data
        assert "total_entities_detected" in data

    async def test_usage(self, client):
        token = await self._setup(client)
        res = await client.get("/api/admin/usage?days=7",
                               headers=auth_headers(token))
        assert res.status_code == 200
        data = res.json()
        assert "data" in data

    async def test_entity_stats(self, client):
        token = await self._setup(client)
        res = await client.get("/api/admin/entities",
                               headers=auth_headers(token))
        assert res.status_code == 200
        data = res.json()
        assert "by_type" in data
        assert "total" in data

    async def test_audit_logs(self, client):
        token = await self._setup(client)
        res = await client.get("/api/admin/audit?limit=10",
                               headers=auth_headers(token))
        assert res.status_code == 200
        data = res.json()
        assert "logs" in data
        assert "total" in data
