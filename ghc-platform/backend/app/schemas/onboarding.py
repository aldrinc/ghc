from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class OnboardingStartRequest(BaseModel):
    business_type: Literal["new", "existing"] = "new"
    brand_story: str = Field(..., min_length=10)
    offers: List[str] = Field(..., min_length=1)
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
