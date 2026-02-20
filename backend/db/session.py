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

    def _get_columns(connection):
        inspector = inspect(connection)
        try:
            return [c["name"] for c in inspector.get_columns("users")]
        except Exception:
            return []

    columns = await conn.run_sync(_get_columns)

    if "oauth_provider" not in columns:
        if "sqlite" in settings.database_url:
            await conn.execute(text("ALTER TABLE users ADD COLUMN oauth_provider VARCHAR(50)"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN oauth_id VARCHAR(255)"))
        else:
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider VARCHAR(50)"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_id VARCHAR(255)"))


async def get_db() -> AsyncSession:
    """FastAPI dependency for database sessions."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
