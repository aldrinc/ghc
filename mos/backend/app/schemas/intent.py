from __future__ import annotations

from typing import Optional, List

from pydantic import BaseModel


class IntentFunnelPageTemplate(BaseModel):
    templateId: str
    name: Optional[str] = None
    slug: Optional[str] = None


class CampaignIntentRequest(BaseModel):
    campaignName: str
    productId: str
    channels: List[str]
    assetBriefTypes: List[str]
    goalDescription: Optional[str] = None
    objectiveType: Optional[str] = None
    numericTarget: Optional[float] = None
    baseline: Optional[float] = None
    timeframeDays: Optional[int] = None
    budgetMin: Optional[float] = None
    budgetMax: Optional[float] = None
    funnelName: Optional[str] = None
    funnelPages: Optional[List[IntentFunnelPageTemplate]] = None
    useDefaultFunnelTemplates: bool = False
