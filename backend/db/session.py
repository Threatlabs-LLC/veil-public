from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Create all tables. Uses SQLAlchemy metadata from models."""
    from backend.models import Base  # noqa: F811

    if "sqlite" in settings.database_url:
        # Enable WAL mode and other SQLite pragmas
        from sqlalchemy import event, text

        @event.listens_for(engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _run_migrations(conn)


async def _run_migrations(conn) -> None:
    """Add columns that create_all won't add to existing tables."""
    from sqlalchemy import text, inspect

    is_sqlite = "sqlite" in settings.database_url

    def _get_table_columns(table_name):
        def _inner(connection):
            insp = inspect(connection)
            try:
                return [c["name"] for c in insp.get_columns(table_name)]
            except Exception:
                return []
        return _inner

    # --- users table migrations ---
    user_cols = await conn.run_sync(_get_table_columns("users"))
    if user_cols and "oauth_provider" not in user_cols:
        if is_sqlite:
            await conn.execute(text("ALTER TABLE users ADD COLUMN oauth_provider VARCHAR(50)"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN oauth_id VARCHAR(255)"))
        else:
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider VARCHAR(50)"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_id VARCHAR(255)"))

    # --- organizations table migrations ---
    org_cols = await conn.run_sync(_get_table_columns("organizations"))
    if org_cols and "stripe_customer_id" not in org_cols:
        if is_sqlite:
            await conn.execute(text("ALTER TABLE organizations ADD COLUMN stripe_customer_id VARCHAR(255)"))
            await conn.execute(text("ALTER TABLE organizations ADD COLUMN stripe_subscription_id VARCHAR(255)"))
            await conn.execute(text("ALTER TABLE organizations ADD COLUMN subscription_status VARCHAR(50)"))
            await conn.execute(text("ALTER TABLE organizations ADD COLUMN billing_email VARCHAR(255)"))
        else:
            await conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255)"))
            await conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(255)"))
            await conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(50)"))
            await conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS billing_email VARCHAR(255)"))


async def get_db() -> AsyncSession:
    """FastAPI dependency for database sessions."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
