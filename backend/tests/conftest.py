"""Shared test fixtures — in-memory SQLite, test client, authenticated user."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models import Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_engine():
    """Create an in-memory SQLite engine for tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db(db_engine):
    """Provide a transactional database session for each test."""
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
async def seeded_org(db):
    """Create an org + admin user, return (org, user)."""
    from backend.models.organization import Organization
    from backend.models.user import User
    from backend.api.auth import _hash_password

    org = Organization(name="Test Org", slug="test-org", tier="free")
    db.add(org)
    await db.flush()

    user = User(
        organization_id=org.id,
        email="admin@test.com",
        display_name="Test Admin",
        password_hash=_hash_password("testpass123"),
        role="owner",
    )
    db.add(user)
    await db.flush()
    await db.commit()

    return org, user


@pytest.fixture
async def auth_token(seeded_org):
    """Create a JWT token for the test user."""
    from backend.api.auth import create_access_token

    org, user = seeded_org
    token, _ = create_access_token(user.id, org.id)
    return token


@pytest.fixture
async def client(db_engine):
    """Async HTTP test client with overridden DB dependency."""
    from backend.db.session import get_db
    from backend.main import app

    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    # Disable rate limiting for tests
    from backend.middleware.rate_limit import RateLimitMiddleware
    for middleware in app.user_middleware:
        if middleware.cls is RateLimitMiddleware:
            middleware.kwargs["enabled"] = False

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
