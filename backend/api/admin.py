"""Admin dashboard API — usage analytics, entity stats, user management, audit logs."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user
from backend.db.session import get_db
from backend.licensing.dependencies import require_feature
from backend.licensing.tiers import FEATURE_ADVANCED_AUDIT, get_tier
from backend.models.audit import AuditLog
from backend.models.conversation import Conversation, Message
from backend.models.entity import Entity, MappingSession
from backend.models.usage import UsageStat
from backend.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


# --- Schemas ---

class DashboardStats(BaseModel):
    total_conversations: int
    total_messages: int
    total_entities_detected: int
    total_tokens_used: int
    estimated_cost_usd: float
    active_users: int
    top_entity_types: list[dict]
    requests_today: int
    entities_today: int


class UsageRow(BaseModel):
    period: str
    provider: str
    model: str
    request_count: int
    total_tokens: int
    estimated_cost_usd: float
    entities_detected: int


class EntityStatsRow(BaseModel):
    entity_type: str
    count: int
    detection_method: str
    avg_confidence: float


class UserRow(BaseModel):
    id: str
    email: str
    display_name: str | None
    role: str
    is_active: bool
    last_login_at: str | None
    created_at: str


class AuditLogRow(BaseModel):
    id: str
    event_type: str
    user_id: str | None
    conversation_id: str | None
    provider: str | None
    model_requested: str | None
    http_status: int | None
    latency_ms: int | None
    error_message: str | None
    created_at: str


# --- Endpoints ---

@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get overview dashboard stats for the organization. Owner/admin only."""
    if user.role not in ("owner", "admin"):
        raise HTTPException(403, "Admin access required")
    org_id = user.organization_id

    # Total conversations
    result = await db.execute(
        select(func.count(Conversation.id)).where(
            Conversation.organization_id == org_id,
            Conversation.status != "archived",
        )
    )
    total_conversations = result.scalar() or 0

    # Total messages
    result = await db.execute(
        select(func.count(Message.id)).where(Message.organization_id == org_id)
    )
    total_messages = result.scalar() or 0

    # Total entities detected
    result = await db.execute(
        select(func.count(Entity.id)).where(
            Entity.session_id.in_(
                select(MappingSession.id).where(MappingSession.organization_id == org_id)
            )
        )
    )
    total_entities = result.scalar() or 0

    # Usage totals
    result = await db.execute(
        select(
            func.coalesce(func.sum(UsageStat.total_tokens), 0),
            func.coalesce(func.sum(UsageStat.estimated_cost_microdollars), 0),
        ).where(UsageStat.organization_id == org_id)
    )
    row = result.one()
    total_tokens = int(row[0])
    total_cost_micro = int(row[1])

    # Active users (logged in last 30 days)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    result = await db.execute(
        select(func.count(User.id)).where(
            User.organization_id == org_id,
            User.is_active == True,
            User.last_login_at >= thirty_days_ago,
        )
    )
    active_users = result.scalar() or 0

    # Top entity types
    result = await db.execute(
        select(Entity.entity_type, func.count(Entity.id).label("cnt"))
        .where(
            Entity.session_id.in_(
                select(MappingSession.id).where(MappingSession.organization_id == org_id)
            )
        )
        .group_by(Entity.entity_type)
        .order_by(func.count(Entity.id).desc())
        .limit(10)
    )
    top_entity_types = [
        {"type": row[0], "count": row[1]} for row in result.all()
    ]

    # Today's stats
    today = date.today().isoformat()
    result = await db.execute(
        select(
            func.coalesce(func.sum(UsageStat.request_count), 0),
            func.coalesce(func.sum(UsageStat.entities_detected), 0),
        ).where(
            UsageStat.organization_id == org_id,
            UsageStat.period_start == today,
        )
    )
    today_row = result.one()

    return DashboardStats(
        total_conversations=total_conversations,
        total_messages=total_messages,
        total_entities_detected=total_entities,
        total_tokens_used=total_tokens,
        estimated_cost_usd=total_cost_micro / 1_000_000,
        active_users=active_users,
        top_entity_types=top_entity_types,
        requests_today=int(today_row[0]),
        entities_today=int(today_row[1]),
    )


@router.get("/usage")
async def get_usage(
    days: int = Query(30, ge=1, le=365),
    group_by: str = Query("day", pattern="^(day|provider|model|user)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get usage analytics with configurable date range and grouping. Owner/admin only."""
    if user.role not in ("owner", "admin"):
        raise HTTPException(403, "Admin access required")
    org_id = user.organization_id
    start_date = (date.today() - timedelta(days=days)).isoformat()

    if group_by == "day":
        result = await db.execute(
            select(
                UsageStat.period_start,
                func.sum(UsageStat.request_count).label("requests"),
                func.sum(UsageStat.total_tokens).label("tokens"),
                func.sum(UsageStat.estimated_cost_microdollars).label("cost"),
                func.sum(UsageStat.entities_detected).label("entities"),
                func.sum(UsageStat.error_count).label("errors"),
            )
            .where(
                UsageStat.organization_id == org_id,
                UsageStat.period_start >= start_date,
            )
            .group_by(UsageStat.period_start)
            .order_by(UsageStat.period_start)
        )
    elif group_by == "provider":
        result = await db.execute(
            select(
                UsageStat.provider,
                func.sum(UsageStat.request_count).label("requests"),
                func.sum(UsageStat.total_tokens).label("tokens"),
                func.sum(UsageStat.estimated_cost_microdollars).label("cost"),
                func.sum(UsageStat.entities_detected).label("entities"),
                func.sum(UsageStat.error_count).label("errors"),
            )
            .where(
                UsageStat.organization_id == org_id,
                UsageStat.period_start >= start_date,
            )
            .group_by(UsageStat.provider)
            .order_by(func.sum(UsageStat.request_count).desc())
        )
    elif group_by == "model":
        result = await db.execute(
            select(
                UsageStat.model,
                func.sum(UsageStat.request_count).label("requests"),
                func.sum(UsageStat.total_tokens).label("tokens"),
                func.sum(UsageStat.estimated_cost_microdollars).label("cost"),
                func.sum(UsageStat.entities_detected).label("entities"),
                func.sum(UsageStat.error_count).label("errors"),
            )
            .where(
                UsageStat.organization_id == org_id,
                UsageStat.period_start >= start_date,
            )
            .group_by(UsageStat.model)
            .order_by(func.sum(UsageStat.request_count).desc())
        )
    else:  # user
        result = await db.execute(
            select(
                UsageStat.user_id,
                func.sum(UsageStat.request_count).label("requests"),
                func.sum(UsageStat.total_tokens).label("tokens"),
                func.sum(UsageStat.estimated_cost_microdollars).label("cost"),
                func.sum(UsageStat.entities_detected).label("entities"),
                func.sum(UsageStat.error_count).label("errors"),
            )
            .where(
                UsageStat.organization_id == org_id,
                UsageStat.period_start >= start_date,
            )
            .group_by(UsageStat.user_id)
            .order_by(func.sum(UsageStat.request_count).desc())
        )

    rows = result.all()
    return {
        "period_days": days,
        "group_by": group_by,
        "data": [
            {
                "group": row[0],
                "request_count": int(row[1] or 0),
                "total_tokens": int(row[2] or 0),
                "estimated_cost_usd": round((row[3] or 0) / 1_000_000, 4),
                "entities_detected": int(row[4] or 0),
                "error_count": int(row[5] or 0),
            }
            for row in rows
        ],
    }


@router.get("/entities",
            dependencies=[Depends(require_feature(FEATURE_ADVANCED_AUDIT))])
async def get_entity_stats(
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get entity detection statistics grouped by type and detection method."""
    org_id = user.organization_id

    # By type
    result = await db.execute(
        select(
            Entity.entity_type,
            Entity.detection_method,
            func.count(Entity.id).label("count"),
            func.avg(Entity.confidence).label("avg_confidence"),
        )
        .where(
            Entity.session_id.in_(
                select(MappingSession.id).where(MappingSession.organization_id == org_id)
            )
        )
        .group_by(Entity.entity_type, Entity.detection_method)
        .order_by(func.count(Entity.id).desc())
    )

    rows = result.all()

    # Aggregate by type
    type_totals: dict[str, int] = {}
    for row in rows:
        type_totals[row[0]] = type_totals.get(row[0], 0) + row[2]

    return {
        "by_type_and_method": [
            {
                "entity_type": row[0],
                "detection_method": row[1],
                "count": row[2],
                "avg_confidence": round(float(row[3] or 0), 3),
            }
            for row in rows
        ],
        "by_type": [
            {"entity_type": k, "count": v}
            for k, v in sorted(type_totals.items(), key=lambda x: -x[1])
        ],
        "total": sum(type_totals.values()),
    }


@router.get("/users")
async def list_users(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users in the organization."""
    if user.role not in ("owner", "admin"):
        raise HTTPException(403, "Admin access required")

    result = await db.execute(
        select(User)
        .where(User.organization_id == user.organization_id)
        .order_by(User.created_at)
    )
    users = result.scalars().all()

    return [
        UserRow(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            role=u.role,
            is_active=u.is_active,
            last_login_at=str(u.last_login_at) if u.last_login_at else None,
            created_at=str(u.created_at),
        )
        for u in users
    ]


class UserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None


class InviteUser(BaseModel):
    email: str
    role: str = "member"
    display_name: str | None = None


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UserUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a user's role or active status. Owner/admin only."""
    if user.role not in ("owner", "admin"):
        raise HTTPException(403, "Admin access required")

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.organization_id == user.organization_id,
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "User not found")

    # Prevent demoting yourself
    if target.id == user.id and body.role and body.role != user.role:
        raise HTTPException(400, "Cannot change your own role")

    # Only owners can promote to owner/admin
    if body.role in ("owner", "admin") and user.role != "owner":
        raise HTTPException(403, "Only owners can promote to admin/owner")

    if body.role is not None:
        if body.role not in ("owner", "admin", "member"):
            raise HTTPException(400, "Role must be owner, admin, or member")
        target.role = body.role
    if body.is_active is not None:
        if target.id == user.id:
            raise HTTPException(400, "Cannot deactivate yourself")
        target.is_active = body.is_active

    return UserRow(
        id=target.id,
        email=target.email,
        display_name=target.display_name,
        role=target.role,
        is_active=target.is_active,
        last_login_at=str(target.last_login_at) if target.last_login_at else None,
        created_at=str(target.created_at),
    )


@router.post("/users/invite")
async def invite_user(
    body: InviteUser,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Invite a new user to the organization. Creates account with temporary password."""
    if user.role not in ("owner", "admin"):
        raise HTTPException(403, "Admin access required")

    from backend.models.organization import Organization
    org = await db.get(Organization, user.organization_id)
    if not org:
        raise HTTPException(404, "Organization not found")

    # Check user limit based on tier
    tier_def = get_tier(org.tier)
    max_users = tier_def.max_users
    result = await db.execute(
        select(func.count(User.id)).where(User.organization_id == user.organization_id)
    )
    current_count = result.scalar() or 0
    if current_count >= max_users:
        raise HTTPException(
            403,
            {
                "error": "user_limit_reached",
                "message": f"User limit reached ({max_users} on {tier_def.name} plan). Upgrade to add more users.",
                "current_count": current_count,
                "max_users": max_users,
                "current_tier": org.tier,
            },
        )

    # Check email uniqueness
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")

    if body.role not in ("owner", "admin", "member"):
        raise HTTPException(400, "Role must be owner, admin, or member")

    import secrets
    from backend.api.auth import _hash_password
    temp_password = secrets.token_urlsafe(12)

    new_user = User(
        organization_id=user.organization_id,
        email=body.email,
        display_name=body.display_name,
        password_hash=_hash_password(temp_password),
        role=body.role,
    )
    db.add(new_user)
    await db.flush()

    return {
        "id": new_user.id,
        "email": new_user.email,
        "role": new_user.role,
        "temp_password": temp_password,
        "message": "User created. Share the temporary password securely — they should change it on first login.",
    }


@router.get("/audit",
            dependencies=[Depends(require_feature(FEATURE_ADVANCED_AUDIT))])
async def query_audit_logs(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    event_type: str | None = None,
    user_id: str | None = None,
    conversation_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query audit logs with filters."""
    if user.role not in ("owner", "admin"):
        raise HTTPException(403, "Admin access required")

    query = select(AuditLog).where(
        AuditLog.organization_id == user.organization_id
    )

    if event_type:
        query = query.where(AuditLog.event_type == event_type)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if conversation_id:
        query = query.where(AuditLog.conversation_id == conversation_id)
    if date_from:
        query = query.where(AuditLog.created_at >= date_from)
    if date_to:
        query = query.where(AuditLog.created_at <= date_to)
    if search:
        search_term = f"%{search}%"
        query = query.where(
            AuditLog.event_type.ilike(search_term)
            | AuditLog.error_message.ilike(search_term)
            | AuditLog.provider.ilike(search_term)
        )

    # Get total count before limit/offset
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "total": total,
        "offset": offset,
        "logs": [
            AuditLogRow(
                id=log.id,
                event_type=log.event_type,
                user_id=log.user_id,
                conversation_id=log.conversation_id,
                provider=log.provider,
                model_requested=log.model_requested,
                http_status=log.http_status,
                latency_ms=log.latency_ms,
                error_message=log.error_message,
                created_at=str(log.created_at),
            )
            for log in logs
        ],
    }
