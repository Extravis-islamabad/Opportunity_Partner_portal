import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.error_handlers import register_error_handlers
from app.core.rate_limit import limiter
from app.api.v1.router import api_router


async def _license_status_refresher(logger) -> None:
    """Daily re-sync of the cached CustomerLicense.status column.

    Reads always derive status live (derive_license_status), so this is not
    load-bearing — it keeps the raw column sane for BI tools / psql / exports.
    Runs once at startup, then every 24h. Failures are logged and retried on
    the next cycle rather than crashing the app.
    """
    from app.core.database import async_session_factory
    from app.services.poc_service import refresh_license_statuses

    while True:
        try:
            async with async_session_factory() as session:
                changed = await refresh_license_statuses(session)
            if changed:
                logger.info("license_status_refresh", changed=changed)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — background loop must survive
            logger.warning("license_status_refresh_failed", error=str(exc))
        await asyncio.sleep(24 * 60 * 60)


async def _daily(name: str, job, logger) -> None:
    """Run one job at startup and every 24h thereafter.

    A generalisation of the licence refresher above, because the review SLA
    sweep needs exactly the same shape and the workflows still to come
    (exclusivity expiry, renewals, tier reviews) will too. Each job gets its
    own session and its own failure boundary: one job throwing must not stop
    the others, and must not stop itself running tomorrow.
    """
    from app.core.database import async_session_factory

    while True:
        try:
            async with async_session_factory() as session:
                result = await job(session)
                await session.commit()
            if result:
                logger.info(f"{name}_ran", **(result if isinstance(result, dict) else {"result": result}))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — a scheduled loop must survive
            logger.warning(f"{name}_failed", error=str(exc))
        await asyncio.sleep(24 * 60 * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    import structlog
    logger = structlog.get_logger()
    logger.info("application_starting", app_name=settings.APP_NAME, version=settings.APP_VERSION)

    from app.core.init_db import create_superadmin
    await create_superadmin()

    from app.services.exclusivity_service import sweep_exclusivity
    from app.services.review_sla_service import sweep_stale_reviews

    # Held in a list, not bare create_task calls: asyncio keeps only a weak
    # reference to a running task, so one whose handle nobody holds can be
    # collected mid-run.
    jobs = [
        asyncio.create_task(_license_status_refresher(logger)),
        asyncio.create_task(_daily("review_sla_sweep", sweep_stale_reviews, logger)),
        asyncio.create_task(_daily("exclusivity_sweep", sweep_exclusivity, logger)),
    ]

    yield

    for task in jobs:
        task.cancel()
    for task in jobs:
        try:
            await task
        except asyncio.CancelledError:
            pass

    from app.core.redis import redis_client
    await redis_client.aclose()
    logger.info("application_shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    # docs_enabled is APP_DEBUG AND not production — a production box never
    # exposes the interactive docs or the OpenAPI schema, even if APP_DEBUG
    # was left on.
    docs_url="/api/docs" if settings.docs_enabled else None,
    redoc_url="/api/redoc" if settings.docs_enabled else None,
    openapi_url="/api/openapi.json" if settings.docs_enabled else None,
    lifespan=lifespan,
)

def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """slowapi's default handler returns {"error": ...}, which the frontend
    (reading response.data.message) can't display — a throttled login showed
    the generic "Login failed" instead of the real reason. Flatten to the
    same {code, message, details} shape every other error uses, keeping
    slowapi's Retry-After / X-RateLimit headers."""
    response = JSONResponse(
        status_code=429,
        content={
            "code": "RATE_LIMIT_EXCEEDED",
            "message": f"Too many requests — limit is {exc.detail}. Please wait a moment and try again.",
            "details": {},
        },
    )
    view_rate_limit = getattr(request.state, "view_rate_limit", None)
    if view_rate_limit:
        response = request.app.state.limiter._inject_headers(response, view_rate_limit)
    return response


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(api_router)

# Files are NOT served as anonymous static content. Uploads used to be
# world-readable by URL; they're now streamed only through the authenticated,
# signed-token endpoint at /api/v1/files/download (see endpoints/files.py).
# We still ensure the directory exists for writes.
upload_dir = Path(settings.UPLOAD_DIR)
upload_dir.mkdir(parents=True, exist_ok=True)
