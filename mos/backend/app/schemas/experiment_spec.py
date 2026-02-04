from typing import List, Optional
from pydantic import BaseModel


class ExperimentVariant(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    channels: List[str] = []
    guardrails: List[str] = []


class ExperimentSpec(BaseModel):
    id: str
    name: str
    hypothesis: Optional[str] = None
    metricIds: List[str] = []
    variants: List[ExperimentVariant] = []
    sampleSizeEstimate: Optional[int] = None
    durationDays: Optional[int] = None
    budgetEstimate: Optional[float] = None


class ExperimentSpecSet(BaseModel):
    clientId: str
    campaignId: Optional[str] = None
    experimentSpecs: List[ExperimentSpec] = []


class ExperimentSpecsUpdateRequest(BaseModel):
    experimentSpecs: List[ExperimentSpec] = []
