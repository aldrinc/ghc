import json
from pathlib import Path

from dotenv import load_dotenv
from pydantic import AnyUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load env values for components that read os.environ directly (e.g., Google clients).
_backend_root = Path(__file__).resolve().parents[1]
_project_root = _backend_root.parent.parent
load_dotenv(_project_root / ".env", override=False)
load_dotenv(_backend_root / ".env", override=True)


def _coerce_json(value: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


class Settings(BaseSettings):
    DATABASE_URL: AnyUrl
    CLERK_JWT_ISSUER: str
    CLERK_JWKS_URL: str
    CLERK_AUDIENCE: str

    DB_POOL_SIZE: int = 20
    DB_POOL_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    TEMPORAL_NAMESPACE: str = "default"
    TEMPORAL_TASK_QUEUE: str = "growth-agency"
    TEMPORAL_ADDRESS: str = "localhost:7234"

    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    OPENAI_API_KEY: str | None = None
    OPENAI_WEBHOOK_SECRET: str | None = None

    MEDIA_STORAGE_BUCKET: str | None = None
    MEDIA_STORAGE_PREVIEW_BUCKET: str | None = None
    MEDIA_STORAGE_ENDPOINT: str | None = None
    MEDIA_STORAGE_REGION: str = "us-east-1"
    MEDIA_STORAGE_ACCESS_KEY: str | None = None
    MEDIA_STORAGE_SECRET_KEY: str | None = None
    MEDIA_STORAGE_PREFIX: str = "dev"
    MEDIA_STORAGE_PRESIGN_TTL_SECONDS: int = 900
    MEDIA_STORAGE_USE_SSL: bool = True
    MEDIA_STORAGE_FORCE_PATH_STYLE: bool = True

    MEDIA_MIRROR_MAX_BYTES: int = 50 * 1024 * 1024
    MEDIA_MIRROR_TIMEOUT_SECONDS: float = 15.0
    MEDIA_MIRROR_MAX_CONCURRENCY: int = 3
    MEDIA_MIRROR_PREVIEW_MAX_DIMENSION: int = 512

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    model_config = SettingsConfigDict(env_file=".env", env_json_loads=_coerce_json, extra="ignore")


settings = Settings()
