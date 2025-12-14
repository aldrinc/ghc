from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from sqlalchemy import text

from app.config import settings
from app.db.base import engine
from app.routers import (
    artifacts,
    assets,
    campaigns,
    clients,
    experiments,
    swipes,
    workflows,
)


def create_app() -> FastAPI:
    app = FastAPI(title="GHC Platform API", default_response_class=ORJSONResponse)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
    app.include_router(campaigns.router)
    app.include_router(artifacts.router)
    app.include_router(assets.router)
    app.include_router(experiments.router)
    app.include_router(swipes.router)
    app.include_router(workflows.router)

    return app


app = create_app()
