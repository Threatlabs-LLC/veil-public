"""Policies API — configure what happens when PII is detected."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user
from backend.db.session import get_db
from backend.models.policy import Policy
from backend.models.user import User

router = APIRouter(prefix="/policies", tags=["policies"])


# --- Schemas ---

class PolicyCreate(BaseModel):
    name: str
    description: str | None = None
    entity_type: str  # * = all types
    action: str = "redact"  # redact | block | warn | allow
    notify: bool = False
    severity: str = "medium"
    min_confidence: float = 0.7
    priority: int = 100


class PolicyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    action: str | None = None
    notify: bool | None = None
    severity: str | None = None
    min_confidence: float | None = None
    is_active: bool | None = None
    priority: int | None = None


class PolicyOut(BaseModel):
    id: str
    name: str
    description: str | None
    entity_type: str
    action: str
    notify: bool
    severity: str
    min_confidence: float
    is_active: bool
    is_built_in: bool
    priority: int
    created_at: str
    updated_at: str


VALID_ACTIONS = {"redact", "block", "warn", "allow"}
VALID_SEVERITIES = {"low", "medium", "high", "critical"}


def _policy_to_out(p: Policy) -> PolicyOut:
    return PolicyOut(
        id=p.id,
        name=p.name,
        description=p.description,
        entity_type=p.entity_type,
        action=p.action,
        notify=p.notify,
        severity=p.severity,
        min_confidence=p.min_confidence,
        is_active=p.is_active,
        is_built_in=p.is_built_in,
        priority=p.priority,
        created_at=str(p.created_at),
        updated_at=str(p.updated_at),
    )


def _validate_action(action: str) -> None:
    if action not in VALID_ACTIONS:
        raise HTTPException(400, f"Invalid action '{action}'. Must be one of: {VALID_ACTIONS}")


def _validate_severity(severity: str) -> None:
    if severity not in VALID_SEVERITIES:
        raise HTTPException(400, f"Invalid severity '{severity}'. Must be one of: {VALID_SEVERITIES}")


# --- Endpoints ---

@router.get("", response_model=list[PolicyOut])
async def list_policies(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all policies for the organization."""
    result = await db.execute(
        select(Policy)
        .where(Policy.organization_id == user.organization_id)
        .order_by(Policy.priority, Policy.entity_type)
    )
    return [_policy_to_out(p) for p in result.scalars().all()]


@router.post("", response_model=PolicyOut, status_code=201)
async def create_policy(
    body: PolicyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new policy. Owner/admin only."""
    if user.role not in ("owner", "admin"):
        raise HTTPException(403, "Admin access required to manage policies")
    _validate_action(body.action)
    _validate_severity(body.severity)

    policy = Policy(
        organization_id=user.organization_id,
        name=body.name,
        description=body.description,
        entity_type=body.entity_type,
        action=body.action,
        notify=body.notify,
        severity=body.severity,
        min_confidence=body.min_confidence,
        priority=body.priority,
    )
    db.add(policy)
    await db.flush()
    return _policy_to_out(policy)


@router.get("/{policy_id}", response_model=PolicyOut)
async def get_policy(
    policy_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single policy."""
    result = await db.execute(
        select(Policy).where(
            Policy.id == policy_id,
            Policy.organization_id == user.organization_id,
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(404, "Policy not found")
    return _policy_to_out(policy)


@router.patch("/{policy_id}", response_model=PolicyOut)
async def update_policy(
    policy_id: str,
    body: PolicyUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a policy. Owner/admin only."""
    if user.role not in ("owner", "admin"):
        raise HTTPException(403, "Admin access required to manage policies")
    result = await db.execute(
        select(Policy).where(
            Policy.id == policy_id,
            Policy.organization_id == user.organization_id,
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(404, "Policy not found")
    if policy.is_built_in:
        raise HTTPException(403, "Cannot modify built-in policies")

    if body.action is not None:
        _validate_action(body.action)
        policy.action = body.action
    if body.name is not None:
        policy.name = body.name
    if body.description is not None:
        policy.description = body.description
    if body.notify is not None:
        policy.notify = body.notify
    if body.severity is not None:
        _validate_severity(body.severity)
        policy.severity = body.severity
    if body.min_confidence is not None:
        policy.min_confidence = body.min_confidence
    if body.is_active is not None:
        policy.is_active = body.is_active
    if body.priority is not None:
        policy.priority = body.priority

    return _policy_to_out(policy)


@router.delete("/{policy_id}")
async def delete_policy(
    policy_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a policy. Owner/admin only."""
    if user.role not in ("owner", "admin"):
        raise HTTPException(403, "Admin access required to manage policies")
    result = await db.execute(
        select(Policy).where(
            Policy.id == policy_id,
            Policy.organization_id == user.organization_id,
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(404, "Policy not found")
    if policy.is_built_in:
        raise HTTPException(403, "Cannot delete built-in policies")

    await db.delete(policy)
    return {"status": "deleted"}
