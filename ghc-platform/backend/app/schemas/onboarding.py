from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class OnboardingStartRequest(BaseModel):
    business_type: Literal["new", "existing"] = "new"
    brand_story: str = Field(..., min_length=10)
    offers: List[str] = Field(..., min_length=1)
    constraints: Optional[List[str]] = None
    competitor_domains: Optional[List[str]] = None
    funnel_notes: Optional[str] = None
    business_model: Optional[str] = None
    primary_markets: List[str] = Field(..., min_length=1)
    primary_languages: List[str] = Field(..., min_length=1)
    goals: Optional[List[str]] = None
    notes: Optional[str] = None
