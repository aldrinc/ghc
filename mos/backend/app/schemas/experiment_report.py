from typing import List, Optional
from pydantic import BaseModel


class ExperimentResult(BaseModel):
    experimentId: str
    primaryMetrics: dict
    secondaryMetrics: dict = {}
    insights: List[str] = []
    recommendations: List[str] = []


class ExperimentReport(BaseModel):
    clientId: str
    campaignId: Optional[str] = None
    results: List[ExperimentResult] = []
    summary: Optional[str] = None
