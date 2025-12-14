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

    TEMPORAL_NAMESPACE: str = "default"
    TEMPORAL_TASK_QUEUE: str = "growth-agency"

    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    OPENAI_API_KEY: str | None = None

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    model_config = SettingsConfigDict(env_file=".env", env_json_loads=_coerce_json, extra="ignore")


settings = Settings()
