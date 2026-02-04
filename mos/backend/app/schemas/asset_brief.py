from typing import List, Optional
from pydantic import BaseModel


class AssetRequirement(BaseModel):
    channel: str
    format: str
    angle: Optional[str] = None
    hook: Optional[str] = None
    funnelStage: Optional[str] = None


class AssetBrief(BaseModel):
    id: str
    clientId: str
    campaignId: Optional[str] = None
    experimentId: Optional[str] = None
    variantId: Optional[str] = None
    funnelId: Optional[str] = None
    variantName: Optional[str] = None
    creativeConcept: Optional[str] = None
    requirements: List[AssetRequirement] = []
    constraints: List[str] = []
    toneGuidelines: List[str] = []
    visualGuidelines: List[str] = []
