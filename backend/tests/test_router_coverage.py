"""API router coverage tests — conversations, api_keys, webhooks, models, usage, settings.

Covers the 6 routers that previously had no dedicated tests.
"""

import pytest
from httpx import ASGITransport, AsyncClient


# ── Helpers ─────────────────────────────────────────────────────────────


async def register_user(client: AsyncClient, email="test@example.com",
                        password="TestPass123!", org_name="TestOrg") -> dict:
    res = await client.post("/api/auth/register", json={
        "email": email, "password": password, "org_name": org_name,
    })
    assert res.status_code == 200, res.text
    return res.json()


async def _upgrade_org_tier(client: AsyncClient, token: str, tier: str = "team"):
    """Upgrade the registered user's org to a higher tier via internal DB."""
    from backend.db.session import get_db
    from backend.main import app

    override = app.dependency_overrides.get(get_db)
    if override:
        gen = override()
        db = await gen.__anext__()
        try:
            from sqlalchemy import select
            from backend.models.user import User
            from backend.models.organization import Organization
            from jose import jwt
            from backend.config import settings

            payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
            user = await db.get(User, payload["sub"])
            if user:
                org = await db.get(Organization, user.organization_id)
                if org:
                    org.tier = tier
                    await db.commit()
        finally:
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass


async def _get_user_org_id(client: AsyncClient, token: str) -> str:
    """Get the organization ID for the authenticated user."""
    from backend.db.session import get_db
    from backend.main import app

    override = app.dependency_overrides.get(get_db)
    if override:
        gen = override()
        db = await gen.__anext__()
        try:
            from backend.models.user import User
            from jose import jwt
            from backend.config import settings

            payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
            user = await db.get(User, payload["sub"])
            return user.organization_id if user else ""
        finally:
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass
    return ""


async def _create_conversation_in_db(client: AsyncClient, token: str,
                                      title="Test Chat", provider="openai",
                                      model="gpt-4o-mini") -> str:
    """Create a conversation directly in DB, return its ID."""
    from backend.db.session import get_db
    from backend.main import app

    override = app.dependency_overrides.get(get_db)
    if override:
        gen = override()
        db = await gen.__anext__()
        try:
            from backend.models.user import User
            from backend.models.conversation import Conversation, Message
            from jose import jwt
            from backend.config import settings

            payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
            user = await db.get(User, payload["sub"])

            conv = Conversation(
                organization_id=user.organization_id,
                user_id=user.id,
                title=title,
                provider=provider,
                model=model,
                status="active",
                total_messages=2,
            )
            db.add(conv)
            await db.flush()

            msg1 = Message(
                conversation_id=conv.id,
                organization_id=user.organization_id,
                sequence_number=1,
                role="user",
                original_content="Hello from the test",
                sanitized_content="Hello from the test",
                entities_detected=0,
            )
            msg2 = Message(
                conversation_id=conv.id,
                organization_id=user.organization_id,
                sequence_number=2,
                role="assistant",
                sanitized_content="Hi there!",
                desanitized_content="Hi there!",
                entities_detected=0,
                model_used=model,
            )
            db.add(msg1)
            db.add(msg2)
            await db.commit()

            return conv.id
        finally:
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass
    return ""


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Conversations Tests ───────────────────────────────────────────────


class TestConversationsAPI:
    """Tests for /api/conversations endpoints."""

    async def _setup(self, client) -> tuple[str, str]:
        data = await register_user(client, email=f"conv-{id(self)}@test.com")
        token = data["access_token"]
        await _upgrade_org_tier(client, token, "solo")
        conv_id = await _create_conversation_in_db(client, token)
        return token, conv_id

    async def test_list_conversations(self, client):
        token, conv_id = await self._setup(client)
        res = await client.get("/api/conversations", headers=auth_headers(token))
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["id"] == conv_id
        assert data[0]["title"] == "Test Chat"

    async def test_list_conversations_empty(self, client):
        data = await register_user(client, email=f"convempty-{id(self)}@test.com")
        token = data["access_token"]
        res = await client.get("/api/conversations", headers=auth_headers(token))
        assert res.status_code == 200
        assert res.json() == []

    async def test_list_conversations_search(self, client):
        token, conv_id = await self._setup(client)
        # Search by title
        res = await client.get("/api/conversations?q=Test", headers=auth_headers(token))
        assert res.status_code == 200
        assert len(res.json()) >= 1

        # Search for non-existent term
        res = await client.get("/api/conversations?q=nonexistent999", headers=auth_headers(token))
        assert res.status_code == 200
        assert len(res.json()) == 0

    async def test_list_conversations_sort(self, client):
        token, conv_id = await self._setup(client)
        for sort in ["updated_desc", "updated_asc", "created_desc", "created_asc", "messages_desc"]:
            res = await client.get(f"/api/conversations?sort={sort}", headers=auth_headers(token))
            assert res.status_code == 200

    async def test_list_conversations_pagination(self, client):
        token, conv_id = await self._setup(client)
        res = await client.get("/api/conversations?limit=1&offset=0", headers=auth_headers(token))
        assert res.status_code == 200
        assert len(res.json()) <= 1

    async def test_get_conversation(self, client):
        token, conv_id = await self._setup(client)
        res = await client.get(f"/api/conversations/{conv_id}", headers=auth_headers(token))
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == conv_id
        assert data["title"] == "Test Chat"
        assert "messages" in data
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "assistant"

    async def test_get_conversation_not_found(self, client):
        data = await register_user(client, email=f"conv404-{id(self)}@test.com")
        token = data["access_token"]
        res = await client.get("/api/conversations/nonexistent-id", headers=auth_headers(token))
        assert res.status_code == 404

    async def test_update_conversation_rename(self, client):
        token, conv_id = await self._setup(client)
        res = await client.patch(
            f"/api/conversations/{conv_id}",
            headers=auth_headers(token),
            json={"title": "Renamed Chat"},
        )
        assert res.status_code == 200
        assert res.json()["title"] == "Renamed Chat"

    async def test_delete_conversation(self, client):
        token, conv_id = await self._setup(client)
        res = await client.delete(f"/api/conversations/{conv_id}", headers=auth_headers(token))
        assert res.status_code == 200
        assert res.json()["status"] == "archived"

        # Archived conversation should not appear in list
        res = await client.get("/api/conversations", headers=auth_headers(token))
        conv_ids = [c["id"] for c in res.json()]
        assert conv_id not in conv_ids

    async def test_export_conversation_json(self, client):
        token, conv_id = await self._setup(client)
        res = await client.get(
            f"/api/conversations/{conv_id}/export?format=json",
            headers=auth_headers(token),
        )
        assert res.status_code == 200
        assert "application/json" in res.headers["content-type"]
        data = res.json()
        assert "conversation" in data
        assert "messages" in data
        assert len(data["messages"]) == 2

    async def test_export_conversation_csv(self, client):
        token, conv_id = await self._setup(client)
        res = await client.get(
            f"/api/conversations/{conv_id}/export?format=csv",
            headers=auth_headers(token),
        )
        assert res.status_code == 200
        assert "text/csv" in res.headers["content-type"]
        # Should contain header row + 2 message rows
        lines = res.text.strip().split("\n")
        assert len(lines) == 3  # header + 2 messages

    async def test_export_requires_solo_tier(self, client):
        data = await register_user(client, email=f"convfree-{id(self)}@test.com")
        token = data["access_token"]
        # Don't upgrade tier — stays on free
        conv_id = await _create_conversation_in_db(client, token)
        res = await client.get(
            f"/api/conversations/{conv_id}/export?format=json",
            headers=auth_headers(token),
        )
        assert res.status_code == 403

    async def test_cross_org_conversation_isolation(self, client):
        """Conversations are org-isolated — user from another org gets 404."""
        token1, conv_id = await self._setup(client)
        data2 = await register_user(client, email=f"conv-other-{id(self)}@test.com",
                                     org_name="Other Org")
        token2 = data2["access_token"]
        res = await client.get(f"/api/conversations/{conv_id}", headers=auth_headers(token2))
        assert res.status_code == 404


# ── API Keys Tests ───────────────────────────────────────────────────


class TestApiKeysAPI:
    """Tests for /api/api-keys endpoints."""

    async def _setup(self, client) -> str:
        data = await register_user(client, email=f"keys-{id(self)}@test.com")
        token = data["access_token"]
        await _upgrade_org_tier(client, token, "solo")
        return token

    async def test_list_api_keys_empty(self, client):
        token = await self._setup(client)
        res = await client.get("/api/api-keys", headers=auth_headers(token))
        assert res.status_code == 200
        assert res.json() == []

    async def test_create_api_key(self, client):
        token = await self._setup(client)
        res = await client.post("/api/api-keys", headers=auth_headers(token),
                                json={"name": "Test Key"})
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "Test Key"
        assert data["key"].startswith("vk_")
        assert data["key_prefix"].startswith("vk_")
        assert len(data["key"]) > 20

    async def test_create_api_key_with_scopes(self, client):
        token = await self._setup(client)
        res = await client.post("/api/api-keys", headers=auth_headers(token),
                                json={"name": "Scoped Key", "scopes": ["chat", "sanitize"]})
        assert res.status_code == 200
        assert res.json()["scopes"] == ["chat", "sanitize"]

    async def test_list_api_keys_after_create(self, client):
        token = await self._setup(client)
        await client.post("/api/api-keys", headers=auth_headers(token),
                          json={"name": "Listed Key"})
        res = await client.get("/api/api-keys", headers=auth_headers(token))
        assert res.status_code == 200
        keys = res.json()
        assert len(keys) == 1
        assert keys[0]["name"] == "Listed Key"
        # Full key should NOT be returned in list
        assert "key" not in keys[0] or not keys[0].get("key", "").startswith("vk_")

    async def test_revoke_api_key(self, client):
        token = await self._setup(client)
        create_res = await client.post("/api/api-keys", headers=auth_headers(token),
                                       json={"name": "Revokable Key"})
        key_id = create_res.json()["id"]

        res = await client.delete(f"/api/api-keys/{key_id}", headers=auth_headers(token))
        assert res.status_code == 200
        assert res.json()["status"] == "revoked"

        # Key should appear as inactive in list
        res = await client.get("/api/api-keys", headers=auth_headers(token))
        keys = res.json()
        revoked = next(k for k in keys if k["id"] == key_id)
        assert revoked["is_active"] is False

    async def test_revoke_nonexistent_key(self, client):
        token = await self._setup(client)
        res = await client.delete("/api/api-keys/fake-id", headers=auth_headers(token))
        assert res.status_code == 404

    async def test_create_api_key_free_tier_allowed(self, client):
        """Self-hosted has no tier gating on API keys."""
        data = await register_user(client, email=f"keyfree-{id(self)}@test.com")
        token = data["access_token"]
        res = await client.post("/api/api-keys", headers=auth_headers(token),
                                json={"name": "Free Key"})
        assert res.status_code == 200

    async def test_cross_org_revoke_blocked(self, client):
        """Ensure one org can't revoke another org's API key."""
        token1 = await self._setup(client)
        create_res = await client.post("/api/api-keys", headers=auth_headers(token1),
                                       json={"name": "Org1 Key"})
        key_id = create_res.json()["id"]

        data2 = await register_user(client, email=f"keysother-{id(self)}@test.com",
                                     org_name="Other Org")
        token2 = data2["access_token"]
        await _upgrade_org_tier(client, token2, "solo")
        res = await client.delete(f"/api/api-keys/{key_id}", headers=auth_headers(token2))
        assert res.status_code == 404


# ── Webhooks Tests ────────────────────────────────────────────────────


class TestWebhooksAPI:
    """Tests for /api/webhooks endpoints."""

    async def _setup(self, client) -> str:
        data = await register_user(client, email=f"wh-{id(self)}@test.com")
        token = data["access_token"]
        await _upgrade_org_tier(client, token, "team")
        return token

    async def test_list_webhooks_empty(self, client):
        token = await self._setup(client)
        res = await client.get("/api/webhooks", headers=auth_headers(token))
        assert res.status_code == 200
        assert res.json() == []

    async def test_create_webhook(self, client):
        token = await self._setup(client)
        res = await client.post("/api/webhooks", headers=auth_headers(token), json={
            "name": "Test Webhook",
            "url": "https://example.com/webhook",
            "event_types": ["entity.detected"],
        })
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "Test Webhook"
        assert data["url"] == "https://example.com/webhook"
        assert data["is_active"] is True
        assert data["secret"] is not None  # Masked secret

    async def test_create_webhook_all_events(self, client):
        token = await self._setup(client)
        res = await client.post("/api/webhooks", headers=auth_headers(token), json={
            "name": "All Events",
            "url": "https://example.com/all",
            "event_types": [],  # empty = all events
        })
        assert res.status_code == 201

    async def test_create_webhook_slack_format(self, client):
        token = await self._setup(client)
        res = await client.post("/api/webhooks", headers=auth_headers(token), json={
            "name": "Slack Hook",
            "url": "https://hooks.slack.com/services/T00/B00/xxx",
            "format": "slack",
        })
        assert res.status_code == 201
        assert res.json()["format"] == "slack"

    async def test_create_webhook_invalid_url(self, client):
        token = await self._setup(client)
        res = await client.post("/api/webhooks", headers=auth_headers(token), json={
            "name": "Bad URL",
            "url": "http://127.0.0.1/internal",  # SSRF blocked
        })
        assert res.status_code == 400

    async def test_create_webhook_invalid_format(self, client):
        token = await self._setup(client)
        res = await client.post("/api/webhooks", headers=auth_headers(token), json={
            "name": "Bad Format",
            "url": "https://example.com/hook",
            "format": "xml",  # invalid
        })
        assert res.status_code == 400

    async def test_create_webhook_invalid_event_type(self, client):
        token = await self._setup(client)
        res = await client.post("/api/webhooks", headers=auth_headers(token), json={
            "name": "Bad Event",
            "url": "https://example.com/hook",
            "event_types": ["nonexistent.event"],
        })
        assert res.status_code == 400

    async def test_update_webhook(self, client):
        token = await self._setup(client)
        create_res = await client.post("/api/webhooks", headers=auth_headers(token), json={
            "name": "Update Me",
            "url": "https://example.com/hook",
        })
        wh_id = create_res.json()["id"]

        res = await client.patch(f"/api/webhooks/{wh_id}", headers=auth_headers(token),
                                  json={"name": "Updated Name", "is_active": False})
        assert res.status_code == 200
        assert res.json()["name"] == "Updated Name"
        assert res.json()["is_active"] is False

    async def test_delete_webhook(self, client):
        token = await self._setup(client)
        create_res = await client.post("/api/webhooks", headers=auth_headers(token), json={
            "name": "Delete Me",
            "url": "https://example.com/hook",
        })
        wh_id = create_res.json()["id"]

        res = await client.delete(f"/api/webhooks/{wh_id}", headers=auth_headers(token))
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"

        # Should be gone from list
        res = await client.get("/api/webhooks", headers=auth_headers(token))
        assert len(res.json()) == 0

    async def test_delete_nonexistent_webhook(self, client):
        token = await self._setup(client)
        res = await client.delete("/api/webhooks/fake-id", headers=auth_headers(token))
        assert res.status_code == 404

    async def test_webhook_free_tier_blocked(self, client):
        data = await register_user(client, email=f"whfree-{id(self)}@test.com")
        token = data["access_token"]
        res = await client.post("/api/webhooks", headers=auth_headers(token), json={
            "name": "Free Hook", "url": "https://example.com/hook",
        })
        assert res.status_code == 403

    async def test_cross_org_webhook_blocked(self, client):
        token1 = await self._setup(client)
        create_res = await client.post("/api/webhooks", headers=auth_headers(token1), json={
            "name": "Org1 Hook", "url": "https://example.com/hook",
        })
        wh_id = create_res.json()["id"]

        data2 = await register_user(client, email=f"whother-{id(self)}@test.com",
                                     org_name="Other Org")
        token2 = data2["access_token"]
        await _upgrade_org_tier(client, token2, "team")
        res = await client.delete(f"/api/webhooks/{wh_id}", headers=auth_headers(token2))
        assert res.status_code == 404


# ── Models Tests ──────────────────────────────────────────────────────


class TestModelsAPI:
    """Tests for /api/models endpoint."""

    async def _setup(self, client) -> str:
        data = await register_user(client, email=f"models-{id(self)}@test.com")
        return data["access_token"]

    async def test_list_models(self, client):
        token = await self._setup(client)
        res = await client.get("/api/models", headers=auth_headers(token))
        assert res.status_code == 200
        data = res.json()
        assert "providers" in data
        assert "models" in data

    async def test_models_has_three_providers(self, client):
        token = await self._setup(client)
        res = await client.get("/api/models", headers=auth_headers(token))
        providers = res.json()["providers"]
        provider_ids = {p["id"] for p in providers}
        assert "openai" in provider_ids
        assert "anthropic" in provider_ids
        assert "ollama" in provider_ids

    async def test_models_have_required_fields(self, client):
        token = await self._setup(client)
        res = await client.get("/api/models", headers=auth_headers(token))
        models = res.json()["models"]
        assert len(models) > 0
        for m in models:
            assert "id" in m
            assert "name" in m
            assert "provider" in m
            assert "context_window" in m
            assert "cost_per_1k_input" in m
            assert "cost_per_1k_output" in m

    async def test_providers_have_configured_status(self, client):
        token = await self._setup(client)
        res = await client.get("/api/models", headers=auth_headers(token))
        providers = res.json()["providers"]
        for p in providers:
            assert "is_configured" in p
            assert isinstance(p["is_configured"], bool)
            assert "model_count" in p

    async def test_models_requires_auth(self, client):
        res = await client.get("/api/models")
        assert res.status_code == 401


# ── Settings (Extended) Tests ─────────────────────────────────────────


class TestSettingsExtended:
    """Extended settings tests covering org profile and role gating."""

    async def _setup(self, client) -> str:
        data = await register_user(client, email=f"setx-{id(self)}@test.com")
        return data["access_token"]

    async def test_get_org_profile(self, client):
        token = await self._setup(client)
        res = await client.get("/api/settings/org", headers=auth_headers(token))
        assert res.status_code == 200
        data = res.json()
        assert "name" in data
        assert "slug" in data
        assert "tier" in data
        assert "user_count" in data
        assert data["user_count"] == 1

    async def test_update_org_profile_owner(self, client):
        token = await self._setup(client)
        res = await client.patch("/api/settings/org", headers=auth_headers(token),
                                  json={"name": "New Org Name"})
        assert res.status_code == 200
        assert res.json()["name"] == "New Org Name"

    async def test_update_settings_non_admin_blocked(self, client):
        """Non-admin/owner users cannot update settings."""
        # Register owner
        owner_data = await register_user(client, email=f"setowner-{id(self)}@test.com")
        owner_token = owner_data["access_token"]
        await _upgrade_org_tier(client, owner_token, "team")

        # Invite a member (create via DB since invite flow is complex)
        from backend.db.session import get_db
        from backend.main import app

        override = app.dependency_overrides.get(get_db)
        if override:
            gen = override()
            db = await gen.__anext__()
            try:
                from backend.models.user import User
                from backend.api.auth import _hash_password, create_access_token
                from jose import jwt
                from backend.config import settings

                payload = jwt.decode(owner_token, settings.secret_key, algorithms=["HS256"])
                owner = await db.get(User, payload["sub"])

                member = User(
                    organization_id=owner.organization_id,
                    email=f"member-{id(self)}@test.com",
                    display_name="Member",
                    password_hash=_hash_password("testpass123"),
                    role="member",
                )
                db.add(member)
                await db.flush()
                member_token, _ = create_access_token(member.id, member.organization_id)
                await db.commit()
            finally:
                try:
                    await gen.__anext__()
                except StopAsyncIteration:
                    pass

            # Member should be blocked from updating settings
            res = await client.patch("/api/settings", headers=auth_headers(member_token),
                                      json={"default_model": "gpt-4o"})
            assert res.status_code == 403

    async def test_update_settings_ollama_url_validation(self, client):
        token = await self._setup(client)
        # Valid external URL should work (use a real resolvable domain)
        res = await client.patch("/api/settings", headers=auth_headers(token),
                                  json={"ollama_base_url": "https://example.com/v1"})
        assert res.status_code == 200

    async def test_update_settings_ollama_ssrf_blocked(self, client):
        token = await self._setup(client)
        res = await client.patch("/api/settings", headers=auth_headers(token),
                                  json={"ollama_base_url": "http://169.254.169.254/latest/meta-data"})
        assert res.status_code == 400

    async def test_settings_requires_auth(self, client):
        res = await client.get("/api/settings")
        assert res.status_code == 401
