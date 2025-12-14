from typing import List, Optional
from pydantic import BaseModel


class QAItem(BaseModel):
    assetId: str
    passed: bool
    notes: Optional[str] = None
    issues: List[str] = []


class QAReport(BaseModel):
    clientId: str
    campaignId: Optional[str] = None
    assetBriefId: Optional[str] = None
    checklist: List[QAItem] = []
    reviewer: Optional[str] = None
