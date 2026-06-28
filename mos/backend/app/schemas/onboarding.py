from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from app.strategy_v2.errors import StrategyV2MissingContextError
from app.strategy_v2.pricing import require_concrete_price


class OnboardingStartRequest(BaseModel):
    business_type: Literal["new", "existing"] = "new"
    brand_story: str = Field(..., min_length=10)
    product_name: str = Field(..., min_length=1)
    price: str = Field(..., min_length=1)
    product_type: str = Field(..., min_length=1)
    product_customizable: bool
    business_model: str = Field(..., min_length=1)
    funnel_position: str = Field(..., min_length=1)
    target_platforms: list[str] = Field(..., min_length=1)
    target_regions: list[str] = Field(..., min_length=1)
    existing_proof_assets: list[str] = Field(..., min_length=1)
    brand_voice_notes: str = Field(..., min_length=1)
    compliance_notes: str | None = None
    product_description: str = Field(..., min_length=1)
    product_category: str | None = None
    primary_benefits: list[str] | None = None
    feature_bullets: list[str] | None = None
    guarantee_text: str | None = None
    disclaimers: list[str] | None = None
    funnel_notes: str | None = None
    goals: list[str] | None = None
    notes: str | None = None
    competitor_urls: list[str] | None = None

    @field_validator("competitor_urls", mode="after")
    @classmethod
    def _validate_urls(cls, urls: list[str] | None) -> list[str] | None:
        if not urls:
            return None
        valid: list[str] = []
        for url in urls:
            if not url:
                continue
            url = url.strip()
            if url.startswith("http://") or url.startswith("https://"):
                valid.append(url)
        return valid or None

    @field_validator("target_platforms", "target_regions", "existing_proof_assets", mode="after")
    @classmethod
    def _validate_nonempty_list_items(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if isinstance(value, str) and value.strip()]
        if not cleaned:
            raise ValueError("Must include at least one non-empty value.")
        return cleaned

    @field_validator("price", mode="after")
    @classmethod
    def _validate_price(cls, value: str) -> str:
        try:
            return require_concrete_price(price=value, context="Onboarding")
        except StrategyV2MissingContextError as exc:
            raise ValueError(str(exc)) from exc


OfferingKind = Literal[
    "product",
    "service",
    "software",
    "course",
    "lead_generation",
    "marketplace",
    "other",
]
MarketingAgentBusinessType = Literal["new", "existing"]
MarketingAgentInputMode = Literal["manual_seed", "source_extract", "context_dev_reviewed"]


def normalize_http_url(value: str, *, field_name: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError(f"{field_name} must be a non-empty URL.")
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be a valid http/https URL.")
    return candidate.rstrip("/")


class MarketingAgentExtractRequest(BaseModel):
    business_url: str = Field(..., min_length=1)
    competitor_urls: list[str] | None = None

    @field_validator("business_url", mode="after")
    @classmethod
    def _validate_business_url(cls, value: str) -> str:
        return normalize_http_url(value, field_name="business_url")

    @field_validator("competitor_urls", mode="after")
    @classmethod
    def _validate_competitor_urls(cls, urls: list[str] | None) -> list[str] | None:
        if not urls:
            return None
        cleaned: list[str] = []
        for url in urls:
            if isinstance(url, str) and url.strip():
                cleaned.append(normalize_http_url(url, field_name="competitor_urls"))
        return cleaned or None


class MarketingAgentSetupRequest(BaseModel):
    business_type: MarketingAgentBusinessType
    input_mode: MarketingAgentInputMode = "manual_seed"
    business_url: str | None = None
    business_name: str | None = None
    business_model: str | None = None
    offering_kind: OfferingKind | None = None
    offering_type: str | None = None
    offering_name: str | None = None
    offering_description: str | None = None
    product_category: str | None = None
    category: str | None = None
    price: str | None = None
    starting_rate: str | None = None
    pricing_model: str | None = None
    charge_model: str | None = None
    competitor_urls: list[str] | None = None
    compliance_notes: str | None = None
    context_dev_summary: dict[str, Any] | None = None
    extraction_review: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("business_url", mode="after")
    @classmethod
    def _validate_optional_business_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return normalize_http_url(value, field_name="business_url")

    @field_validator("competitor_urls", mode="after")
    @classmethod
    def _validate_setup_competitor_urls(cls, urls: list[str] | None) -> list[str] | None:
        if not urls:
            return None
        cleaned: list[str] = []
        for url in urls:
            if isinstance(url, str) and url.strip():
                cleaned.append(normalize_http_url(url, field_name="competitor_urls"))
        return cleaned or None

    @field_validator(
        "business_name",
        "business_model",
        "offering_type",
        "offering_name",
        "offering_description",
        "product_category",
        "category",
        "price",
        "starting_rate",
        "pricing_model",
        "charge_model",
        "compliance_notes",
        mode="after",
    )
    @classmethod
    def _strip_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _validate_branch_requirements(self) -> "MarketingAgentSetupRequest":
        if self.business_type == "existing" and not self.business_url:
            raise ValueError("business_url is required for existing business setup.")
        if self.business_type == "new":
            missing = [
                field
                for field in (
                    "business_model",
                    "offering_kind",
                    "offering_type",
                    "offering_name",
                    "offering_description",
                )
                if getattr(self, field) in (None, "")
            ]
            if missing:
                raise ValueError(
                    "New business setup is missing required fields: " + ", ".join(missing)
                )
        return self


FoundationReadinessStatus = Literal[
    "foundation_pending",
    "foundation_failed",
    "foundation_ready",
]


class FoundationReadinessResponse(BaseModel):
    status: FoundationReadinessStatus
    should_gate_overview: bool
    reason: str
    strategy_workflow_run_id: str | None = None
    strategy_workflow_status: str | None = None
    onboarding_workflow_run_id: str | None = None
    onboarding_workflow_status: str | None = None
    required_step_keys: list[str]
    present_step_keys: list[str]
    missing_step_keys: list[str]
    checked_at: str
