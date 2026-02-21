import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import AnyUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load env values for components that read os.environ directly (e.g., Google clients).
_backend_root = Path(__file__).resolve().parents[1]
_project_root = _backend_root.parent.parent
load_dotenv(_project_root / ".env", override=False)
# Optional consolidated env (gitignored) used in local dev to store secrets outside repo-tracked env examples.
load_dotenv(_project_root / ".env.local.consolidated", override=False)
load_dotenv(_backend_root / ".env", override=True)


def _coerce_json(value: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    ALLOW_SYNTHETIC_TESTIMONIALS_IN_PRODUCTION: bool = False

    DATABASE_URL: AnyUrl
    CLERK_JWT_ISSUER: str
    CLERK_JWKS_URL: str
    CLERK_AUDIENCE: list[str] = ["http://localhost:5173", "backend"]

    DB_POOL_SIZE: int = 20
    DB_POOL_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    TEMPORAL_NAMESPACE: str = "default"
    TEMPORAL_TASK_QUEUE: str = "growth-agency"
    TEMPORAL_MEDIA_ENRICHMENT_TASK_QUEUE: str = "growth-agency-media-enrichment"
    TEMPORAL_MEDIA_ENRICHMENT_ACTIVITY_WORKERS: int = 8
    TEMPORAL_ADDRESS: str = "localhost:7234"
    CAMPAIGN_FUNNEL_VARIANT_ACTIVITY_CONCURRENCY: int = 3

    BACKEND_CORS_ORIGINS: list[str]

    OPENAI_API_KEY: str | None = None
    OPENAI_WEBHOOK_SECRET: str | None = None
    AGENTA_ENABLED: bool = False
    AGENTA_API_KEY: str | None = None
    AGENTA_HOST: str = "https://cloud.agenta.ai"
    AGENTA_PROMPT_REGISTRY: dict[str, dict[str, Any]] = Field(default_factory=dict)
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    LANGFUSE_BASE_URL: str | None = None
    LANGFUSE_ENVIRONMENT: str | None = None
    LANGFUSE_RELEASE: str | None = None
    LANGFUSE_SAMPLE_RATE: float = 1.0
    LANGFUSE_DEBUG: bool = False
    LANGFUSE_REQUIRED: bool = False
    LANGFUSE_AUTH_CHECK: bool = True
    LANGFUSE_TIMEOUT_SECONDS: int = 20

    # Deploy control plane (Terraform apply + SSH deploy) embedded in the MOS backend.
    # Root folder where plan files and Terraform state will be written.
    DEPLOY_ROOT_DIR: str = "cloudhand"
    DEPLOY_PROJECT_ID: str = "mos"
    DEPLOY_WORKSPACE_ID: str = "default"
    DEPLOY_PUBLIC_BASE_URL: str | None = None
    DEPLOY_PUBLIC_API_BASE_URL: str | None = None
    DEPLOY_ARTIFACT_RUNTIME_DIST_PATH: str = "mos/frontend/dist"

    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    SHOPIFY_APP_BASE_URL: str | None = None
    SHOPIFY_INTERNAL_API_TOKEN: str | None = None
    SHOPIFY_ORDER_WEBHOOK_SECRET: str | None = None

    META_GRAPH_API_VERSION: str | None = None
    META_GRAPH_API_BASE_URL: str = "https://graph.facebook.com"
    META_ACCESS_TOKEN: str | None = None
    META_AD_ACCOUNT_ID: str | None = None
    META_PAGE_ID: str | None = None
    META_INSTAGRAM_ACTOR_ID: str | None = None

    CREATIVE_SERVICE_BASE_URL: str | None = None
    CREATIVE_SERVICE_BEARER_TOKEN: str | None = None
    CREATIVE_SERVICE_TIMEOUT_SECONDS: float = 30.0
    CREATIVE_SERVICE_POLL_INTERVAL_SECONDS: float = 2.0
    CREATIVE_SERVICE_POLL_TIMEOUT_SECONDS: float = 300.0
    CREATIVE_SERVICE_VIDEO_POLL_TIMEOUT_SECONDS: float = 1200.0
    CREATIVE_SERVICE_MAX_VIDEO_TURNS: int = 3
    CREATIVE_SERVICE_ASSETS_PER_BRIEF: int = 6
    CREATIVE_SERVICE_RETENTION_DAYS: int = 60
    CREATIVE_SERVICE_PRODUCT_ASSET_CONTEXT_LIMIT: int = 6

    MEDIA_STORAGE_BUCKET: str | None = None
    MEDIA_STORAGE_PREVIEW_BUCKET: str | None = None
    MEDIA_STORAGE_ENDPOINT: str | None = None
    MEDIA_STORAGE_REGION: str = "us-east-1"
    MEDIA_STORAGE_ACCESS_KEY: str | None = None
    MEDIA_STORAGE_SECRET_KEY: str | None = None
    MEDIA_STORAGE_PREFIX: str = "dev"
    # Presigned media URLs are used directly in the frontend (e.g. <img src="...">),
    # so they must outlive lazy-loading / infinite-scroll sessions. Keep this <= 7 days
    # (SigV4 presign max on most S3-compatible stores).
    MEDIA_STORAGE_PRESIGN_TTL_SECONDS: int = 60 * 60 * 24 * 7
    MEDIA_STORAGE_USE_SSL: bool = True
    MEDIA_STORAGE_FORCE_PATH_STYLE: bool = True

    MEDIA_MIRROR_MAX_BYTES: int = 50 * 1024 * 1024
    MEDIA_MIRROR_TIMEOUT_SECONDS: float = 15.0
    MEDIA_MIRROR_MAX_CONCURRENCY: int = 3
    MEDIA_MIRROR_PREVIEW_MAX_DIMENSION: int = 512

    PUBLIC_ASSET_BASE_URL: str | None = None
    FUNNEL_IMAGE_GENERATION_MAX_CONCURRENCY: int = 4
    FUNNEL_IMAGES_STEP_BUDGET_SECONDS: int = 900
    FUNNEL_TESTIMONIALS_STEP_BUDGET_SECONDS: int = 900
    FUNNEL_TESTIMONIAL_TOOL_RETRY_ATTEMPTS: int = 2
    FUNNEL_MEDIA_ENRICHMENT_ACTIVITY_TIMEOUT_MINUTES: int = 30
    FUNNEL_MEDIA_ENRICHMENT_ACTIVITY_MAX_ATTEMPTS: int = 2

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("CLERK_AUDIENCE", mode="before")
    @classmethod
    def split_audience(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [aud.strip() for aud in value.split(",") if aud.strip()]
        return value

    model_config = SettingsConfigDict(env_file=".env", env_json_loads=_coerce_json, extra="ignore")


settings = Settings()
