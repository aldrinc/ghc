from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class OnboardingStartRequest(BaseModel):
    business_type: Literal["new", "existing"] = "new"
    brand_story: str = Field(..., min_length=10)
    product_name: str = Field(..., min_length=1)
    product_customizable: bool
    business_model: str = Field(..., min_length=1)
    funnel_position: str = Field(..., min_length=1)
    target_platforms: List[str] = Field(..., min_length=1)
    target_regions: List[str] = Field(..., min_length=1)
    existing_proof_assets: List[str] = Field(..., min_length=1)
    brand_voice_notes: str = Field(..., min_length=1)
    compliance_notes: Optional[str] = None
    product_description: str = Field(..., min_length=1)
    product_category: Optional[str] = None
    primary_benefits: Optional[List[str]] = None
    feature_bullets: Optional[List[str]] = None
    guarantee_text: Optional[str] = None
    disclaimers: Optional[List[str]] = None
    funnel_notes: Optional[str] = None
    goals: Optional[List[str]] = None
    notes: Optional[str] = None
    competitor_urls: Optional[List[str]] = None

    @field_validator("competitor_urls", mode="after")
    @classmethod
    def _validate_urls(cls, urls: Optional[List[str]]) -> Optional[List[str]]:
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
    def _validate_nonempty_list_items(cls, values: List[str]) -> List[str]:
        cleaned = [value.strip() for value in values if isinstance(value, str) and value.strip()]
        if not cleaned:
            raise ValueError("Must include at least one non-empty value.")
        return cleaned
