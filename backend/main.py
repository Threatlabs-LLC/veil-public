import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.core.events import event_bus
from backend.db.session import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    from backend.core.logging import setup_logging
    setup_logging(json_output=not settings.debug, level="DEBUG" if settings.debug else "INFO")

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    await init_db()
    await event_bus.start()

    # Load webhooks from DB into event bus
    from backend.api.webhooks import load_webhooks_from_db
    from backend.db.session import async_session
    try:
        async with async_session() as db:
            await load_webhooks_from_db(db)
    except Exception as e:
        logger.warning("Failed to load webhooks on startup: %s", e)

    yield
    # Shutdown
    await event_bus.stop()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Security headers middleware
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402
from starlette.requests import Request  # noqa: E402

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' https://accounts.google.com https://www.googleapis.com; "
            "frame-ancestors 'none'"
        )
        if not settings.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Rate limiting (must be added after CORS so CORS headers are always set)
from backend.middleware.rate_limit import RateLimitMiddleware  # noqa: E402
app.add_middleware(RateLimitMiddleware)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": settings.app_version}


@app.get("/api/health/ready")
async def health_ready():
    """Readiness probe — checks that DB is accessible."""
    from backend.db.session import async_session
    from sqlalchemy import text

    checks = {}
    overall = True

    # Database check
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)}
        overall = False

    # Event bus check
    from backend.core.events import event_bus
    checks["event_bus"] = {
        "status": "ok" if event_bus._worker_task and not event_bus._worker_task.done() else "degraded",
        "webhooks_registered": len(event_bus._webhooks),
    }

    status_code = 200 if overall else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content={
            "status": "ready" if overall else "not_ready",
            "version": settings.app_version,
            "checks": checks,
        },
        status_code=status_code,
    )


@app.get("/api/health/live")
async def health_live():
    """Liveness probe — always returns 200 if the process is running."""
    return {"status": "alive"}


# Import and register routers
from backend.api.chat import router as chat_router  # noqa: E402
from backend.api.conversations import router as conversations_router  # noqa: E402
from backend.api.auth import router as auth_router  # noqa: E402
from backend.api.gateway import router as gateway_router  # noqa: E402
from backend.api.admin import router as admin_router  # noqa: E402
from backend.api.rules import router as rules_router  # noqa: E402
from backend.api.policies import router as policies_router  # noqa: E402
from backend.api.settings import router as settings_router  # noqa: E402
from backend.api.api_keys import router as api_keys_router  # noqa: E402
from backend.api.webhooks import router as webhooks_router  # noqa: E402
from backend.api.models import router as models_router  # noqa: E402
from backend.api.licensing import router as licensing_router  # noqa: E402
from backend.api.sanitize import router as sanitize_router  # noqa: E402
from backend.api.documents import router as documents_router  # noqa: E402

app.include_router(chat_router, prefix="/api")
app.include_router(conversations_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(gateway_router)  # No prefix — serves at /v1/chat/completions
app.include_router(admin_router, prefix="/api")
app.include_router(rules_router, prefix="/api")
app.include_router(policies_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(api_keys_router, prefix="/api")
app.include_router(webhooks_router, prefix="/api")
app.include_router(models_router, prefix="/api")
app.include_router(licensing_router, prefix="/api")
app.include_router(sanitize_router, prefix="/api")
app.include_router(documents_router, prefix="/api")

# Serve frontend static files in production
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    from fastapi.responses import FileResponse

    # Serve static assets (JS, CSS, images) directly
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

    # SPA catch-all: serve index.html for any non-API route
    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        # Never intercept API or gateway routes
        if path.startswith("api/") or path.startswith("v1/"):
            raise HTTPException(404, "Not Found")
        # Path traversal protection: resolve and verify path stays within static_dir
        file_path = (static_dir / path).resolve()
        if not str(file_path).startswith(str(static_dir.resolve())):
            raise HTTPException(400, "Invalid path")
        # If a real static file exists, serve it
        if file_path.is_file():
            return FileResponse(file_path)
        # Otherwise serve index.html and let React Router handle it
        return FileResponse(static_dir / "index.html")
