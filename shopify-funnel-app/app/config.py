from __future__ import annotations

from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SHOPIFY_APP_API_KEY: str
    SHOPIFY_APP_API_SECRET: str
    SHOPIFY_APP_SCOPES: str
    SHOPIFY_APP_BASE_URL: AnyHttpUrl
    SHOPIFY_INTERNAL_API_TOKEN: str
    SHOPIFY_APP_DB_URL: str = "sqlite:///./shopify_funnel_app.db"
    SHOPIFY_ADMIN_API_VERSION: str = "2026-01"
    SHOPIFY_STOREFRONT_API_VERSION: str = "2026-01"
    SHOPIFY_REQUEST_TIMEOUT_SECONDS: float = 20.0

    SHOPIFY_ENABLE_ORDER_FORWARDING: bool = True
    SHOPIFY_ENABLE_COMPLIANCE_FORWARDING: bool = True
    MOS_BACKEND_BASE_URL: AnyHttpUrl | None = None
    MOS_WEBHOOK_SHARED_SECRET: str | None = None
    SHOPIFY_WORKSPACE_LINK_SIGNING_SECRET: str | None = None
    SHOPIFY_INSTALL_SUCCESS_REDIRECT_URL: AnyHttpUrl | None = None

    @field_validator("SHOPIFY_APP_SCOPES")
    @classmethod
    def validate_scopes(cls, value: str) -> str:
        scopes = [scope.strip() for scope in value.split(",") if scope.strip()]
        if not scopes:
            raise ValueError("SHOPIFY_APP_SCOPES must include at least one scope")
        return ",".join(scopes)

    @model_validator(mode="after")
    def validate_forwarding_config(self) -> "Settings":
        requires_mos_forwarding = (
            self.SHOPIFY_ENABLE_ORDER_FORWARDING
            or self.SHOPIFY_ENABLE_COMPLIANCE_FORWARDING
        )
        if requires_mos_forwarding:
            if not self.MOS_BACKEND_BASE_URL:
                raise ValueError(
                    "MOS_BACKEND_BASE_URL is required when Shopify->mOS forwarding is enabled"
                )
            if not self.MOS_WEBHOOK_SHARED_SECRET:
                raise ValueError(
                    "MOS_WEBHOOK_SHARED_SECRET is required when Shopify->mOS forwarding is enabled"
                )
        return self

    @property
    def app_base_url(self) -> str:
        return str(self.SHOPIFY_APP_BASE_URL).rstrip("/")

    @property
    def mos_compliance_webhook_url(self) -> str:
        base = str(self.MOS_BACKEND_BASE_URL).rstrip("/")
        return f"{base}/shopify/compliance/webhook"

    @property
    def admin_scopes_csv(self) -> str:
        return self.SHOPIFY_APP_SCOPES

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
