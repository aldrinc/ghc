import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.config import settings
from app.db.base import engine
from app.observability import initialize_langfuse, shutdown_langfuse
from app.services.media_storage import MediaStorageConfigurationError
from app.routers import (
    agent_runs,
    artifacts,
    assets,
    claude,
    campaigns,
    compliance,
    brands,
    clients,
    design_systems,
    products,
    funnels,
    public_funnels,
    explore,
    deep_research,
    experiments,
    openai_webhooks,
    stripe_webhooks,
    swipes,
    teardowns,
    ads,
    workflows,
    meta_ads,
    shopify_webhooks,
    deploy,
)

logger = logging.getLogger(__name__)


def _is_schema_mismatch_programming_error(exc: ProgrammingError) -> bool:
    orig = getattr(exc, "orig", None)
    if getattr(orig, "pgcode", None) == "42703":
        return True
    message = str(orig or exc).lower()
    return any(
        marker in message
        for marker in (
            "undefined column",
            "does not exist",
            "no such column",
        )
    )


@asynccontextmanager
async def _app_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    initialize_langfuse()
    try:
        yield
    finally:
        shutdown_langfuse()


def create_app() -> FastAPI:
    app = FastAPI(
        title="mOS Platform API",
        default_response_class=ORJSONResponse,
        lifespan=_app_lifespan,
    )

    allow_origins = sorted(set(settings.BACKEND_CORS_ORIGINS))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(MediaStorageConfigurationError)
    async def media_storage_configuration_error_handler(
        _request: Request, exc: MediaStorageConfigurationError
    ) -> ORJSONResponse:
        return ORJSONResponse(status_code=500, content={"detail": str(exc)})

    @app.exception_handler(ProgrammingError)
    async def programming_error_handler(_request: Request, exc: ProgrammingError) -> ORJSONResponse:
        logger.exception("Database programming error", exc_info=exc)
        if _is_schema_mismatch_programming_error(exc):
            return ORJSONResponse(
                status_code=503,
                content={
                    "detail": "Database schema is out of date. Run `alembic upgrade head` and redeploy."
                },
            )
        return ORJSONResponse(status_code=500, content={"detail": "Database query failed."})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, exc: Exception) -> ORJSONResponse:
        logger.exception("Unhandled server exception", exc_info=exc)
        return ORJSONResponse(status_code=500, content={"detail": "Internal server error."})

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/health/db")
    def health_db() -> dict[str, str]:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return {"db": "ok"}
        except Exception as exc:  # pragma: no cover - simple runtime check
            return {"db": f"error: {exc}"}

    app.include_router(clients.router)
    app.include_router(brands.router)
    app.include_router(design_systems.router)
    app.include_router(products.router)
    app.include_router(campaigns.router)
    app.include_router(artifacts.router)
    app.include_router(assets.router)
    app.include_router(compliance.router)
    app.include_router(agent_runs.router)
    app.include_router(funnels.router)
    app.include_router(public_funnels.router)
    app.include_router(experiments.router)
    app.include_router(explore.router)
    app.include_router(swipes.router)
    app.include_router(teardowns.router)
    app.include_router(ads.router)
    app.include_router(meta_ads.router)
    app.include_router(shopify_webhooks.router)
    app.include_router(workflows.router)
    app.include_router(deep_research.router)
    app.include_router(openai_webhooks.router)
    app.include_router(stripe_webhooks.router)
    app.include_router(claude.router)
    app.include_router(deploy.router)

    return app


app = create_app()
