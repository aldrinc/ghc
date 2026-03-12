import json
from pathlib import Path
from typing import Annotated, Any

from pydantic import AnyUrl, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.env_loader import load_backend_env_files

# Load env values for components that read os.environ directly (e.g., Google clients).
_backend_root = Path(__file__).resolve().parents[1]
load_backend_env_files(_backend_root)


def _coerce_json(value: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _parse_string_list(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]

    parsed = _coerce_json(value)
    if isinstance(parsed, list):
        return [item.strip() for item in parsed if isinstance(item, str) and item.strip()]
    if isinstance(parsed, str):
        return [item.strip() for item in parsed.split(",") if item.strip()]
    raise ValueError("Expected a JSON string array or comma-separated string.")


_LOCAL_DEV_CORS_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5275",
    "http://127.0.0.1:5275",
}


def _default_backend_cors_origins() -> list[str]:
    return sorted(_LOCAL_DEV_CORS_ORIGINS)


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    ALLOW_SYNTHETIC_TESTIMONIALS_IN_PRODUCTION: bool = False

    DATABASE_URL: AnyUrl
    CLERK_JWT_ISSUER: str
    CLERK_JWKS_URL: str
    CLERK_AUDIENCE: Annotated[list[str], NoDecode] = ["http://localhost:5173", "backend"]

    DB_POOL_SIZE: int = 20
    DB_POOL_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    TEMPORAL_NAMESPACE: str = "default"
    TEMPORAL_TASK_QUEUE: str = "growth-agency"
    TEMPORAL_MEDIA_ENRICHMENT_TASK_QUEUE: str = "growth-agency-media-enrichment"
    TEMPORAL_MEDIA_ENRICHMENT_ACTIVITY_WORKERS: int = 8
    TEMPORAL_ADDRESS: str = "localhost:7234"
    CAMPAIGN_FUNNEL_VARIANT_ACTIVITY_CONCURRENCY: int = 3
    STRATEGY_V2_DEFAULT_ENABLED: bool = False
    STRATEGY_V2_VOC_MODEL: str = "gpt-5.2-2025-12-11"
    STRATEGY_V2_OFFER_MODEL: str = "gpt-5.2-2025-12-11"
    STRATEGY_V2_COPY_MODEL: str = "claude-opus-4-6"
    STRATEGY_V2_COPY_QA_MODEL: str = "claude-opus-4-6"
    STRATEGY_V2_APIFY_ENABLED: bool = False
    STRATEGY_V2_APIFY_MAX_WAIT_SECONDS: int = 900
    STRATEGY_V2_APIFY_MAX_ITEMS_PER_DATASET: int = 500
    STRATEGY_V2_APIFY_MAX_ACTOR_RUNS: int = 100
    STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS: str = ""
    STRATEGY_V2_APIFY_META_ACTOR_ID: str = "curious_coder~facebook-ads-library-scraper"
    STRATEGY_V2_APIFY_TIKTOK_ACTOR_ID: str = "clockworks/tiktok-scraper"
    STRATEGY_V2_APIFY_INSTAGRAM_ACTOR_ID: str = "apify/instagram-scraper"
    STRATEGY_V2_APIFY_YOUTUBE_ACTOR_ID: str = "streamers/youtube-scraper"
    STRATEGY_V2_APIFY_REDDIT_ACTOR_ID: str = "practicaltools/apify-reddit-api"
    STRATEGY_V2_APIFY_WEB_ACTOR_ID: str = "apify/web-scraper"
    STRATEGY_V2_VOC_MERGED_CORPUS_MAX_ROWS: int = 400
    STRATEGY_V2_VOC_PROMPT_CORPUS_ROWS: int = 80
    STRATEGY_V2_VOC_PROMPT_STEP4_ROWS: int = 40
    STRATEGY_V2_VOC_PROMPT_EXTERNAL_ROWS: int = 40
    STRATEGY_V2_VOC_SOURCE_DIVERSITY_MAX_RATIO: float = 0.25

    BACKEND_CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=_default_backend_cors_origins)

    OPENAI_API_KEY: str | None = None
    BASETEN_API_KEY: str | None = None
    OPENAI_WEBHOOK_SECRET: str | None = None
    BASETEN_BASE_URL: str = "https://inference.baseten.co/v1"
    GEMINI_FILE_SEARCH_ENABLED: bool = False
    GEMINI_FILE_SEARCH_MODEL: str = "gemini-2.5-flash"
    GEMINI_FILE_SEARCH_STORE_PREFIX: str = "mos"
    GEMINI_FILE_SEARCH_POLL_INTERVAL_SECONDS: float = 2.0
    GEMINI_FILE_SEARCH_POLL_TIMEOUT_SECONDS: float = 300.0
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
    BUNNY_API_KEY: str | None = None
    BUNNY_API_BASE_URL: str = "https://api.bunny.net"
    BUNNY_PULLZONE_ORIGIN_IP: str | None = None
    NAMECHEAP_API_USER: str | None = None
    NAMECHEAP_API_KEY: str | None = None
    NAMECHEAP_USERNAME: str | None = None
    NAMECHEAP_CLIENT_IP: str | None = None
    NAMECHEAP_API_BASE_URL: str = "https://api.namecheap.com/xml.response"

    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    # Single public Shopify app bridge configuration.
    SHOPIFY_APP_BASE_URL: str | None = None
    SHOPIFY_INTERNAL_API_TOKEN: str | None = None
    SHOPIFY_ORDER_WEBHOOK_SECRET: str | None = None
    SHOPIFY_COMPLIANCE_WEBHOOK_SECRET: str | None = None
    SHOPIFY_CHECKOUT_REQUEST_TIMEOUT_SECONDS: float = 20.0
    SHOPIFY_THEME_OPERATIONS_TIMEOUT_SECONDS: float = 180.0
    SHOPIFY_THEME_EXPORT_TIMEOUT_SECONDS: float = 600.0
    SHOPIFY_THEME_COMPONENT_IMAGE_BATCH_SIZE: int = 4

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
    CREATIVE_IMAGE_PLAN_ITEM_MAX_CONCURRENCY: int = 8
    CREATIVE_SERVICE_RETENTION_DAYS: int = 60
    CREATIVE_SERVICE_PRODUCT_ASSET_CONTEXT_LIMIT: int = 6
    IMAGE_RENDER_PROVIDER: str = "higgsfield"
    HIGGSFIELD_BASE_URL: str = "https://platform.higgsfield.ai"
    HF_KEY: str | None = None
    HF_API_KEY: str | None = None
    HF_API_SECRET: str | None = None
    HIGGSFIELD_DEFAULT_MODEL: str = "nano-banana-pro"
    HIGGSFIELD_DEFAULT_RESOLUTION: str = "1k"

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
    TESTIMONIAL_RENDERER_URL: str | None = None
    TESTIMONIAL_RENDERER_IMAGE_MODEL: str | None = None
    FUNNEL_IMAGE_GENERATION_MAX_CONCURRENCY: int = 4
    FUNNEL_IMAGES_STEP_BUDGET_SECONDS: int = 900
    FUNNEL_TESTIMONIALS_STEP_BUDGET_SECONDS: int = 3600
    FUNNEL_TESTIMONIAL_TOOL_RETRY_ATTEMPTS: int = 2
    FUNNEL_MEDIA_ENRICHMENT_ACTIVITY_TIMEOUT_MINUTES: int = 90
    FUNNEL_MEDIA_ENRICHMENT_ACTIVITY_HEARTBEAT_TIMEOUT_MINUTES: int = 30
    FUNNEL_MEDIA_ENRICHMENT_ACTIVITY_MAX_ATTEMPTS: int = 2

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        origins = _parse_string_list(value)
        if "http://localhost:5275" not in origins and "http://127.0.0.1:5275" not in origins:
            origins.extend(sorted(_LOCAL_DEV_CORS_ORIGINS))
        return sorted(set(origins))

    @field_validator("CLERK_AUDIENCE", mode="before")
    @classmethod
    def split_audience(cls, value: str | list[str]) -> list[str]:
        return _parse_string_list(value)

    model_config = SettingsConfigDict(env_file=".env", env_json_loads=_coerce_json, extra="ignore")


settings = Settings()
