"""API key management — create, list, revoke vk_ prefixed keys."""

import hashlib
import json
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user
from backend.db.session import get_db
from backend.models.api_key import ApiKey
from backend.models.user import User

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class ApiKeyCreate(BaseModel):
    name: str
    scopes: list[str] = []


class ApiKeyOut(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    last_used_at: str | None
    created_at: str


def _generate_api_key() -> tuple[str, str, str]:
    """Generate a vk_ prefixed API key. Returns (full_key, key_hash, key_prefix)."""
    raw = secrets.token_urlsafe(32)
    full_key = f"vk_{raw}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    key_prefix = full_key[:8]
    return full_key, key_hash, key_prefix


def _key_to_out(key: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        scopes=json.loads(key.scopes) if key.scopes else [],
        is_active=key.is_active,
        last_used_at=str(key.last_used_at) if key.last_used_at else None,
        created_at=str(key.created_at),
    )


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all API keys for the organization."""
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.organization_id == user.organization_id)
        .order_by(ApiKey.created_at.desc())
    )
    return [_key_to_out(k) for k in result.scalars().all()]


@router.post("")
async def create_api_key(
    body: ApiKeyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key. The full key is only returned once."""
    full_key, key_hash, key_prefix = _generate_api_key()

    api_key = ApiKey(
        organization_id=user.organization_id,
        user_id=user.id,
        name=body.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=json.dumps(body.scopes),
    )
    db.add(api_key)
    await db.flush()

    return {
        "id": api_key.id,
        "name": api_key.name,
        "key": full_key,
        "key_prefix": key_prefix,
        "scopes": body.scopes,
    }


@router.delete("/{key_id}")
async def revoke_api_key(
    key_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke (deactivate) an API key."""
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.organization_id == user.organization_id,
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(404, "API key not found")

    key.is_active = False
    return {"status": "revoked"}
