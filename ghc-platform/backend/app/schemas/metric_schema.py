from typing import List, Optional
from pydantic import BaseModel


class MetricDefinition(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    unit: Optional[str] = None


class EventDefinition(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    properties: List[str] = []
    metrics: List[MetricDefinition] = []


class MetricSchema(BaseModel):
    clientId: str
    events: List[EventDefinition] = []
    primaryKpis: List[str] = []
    secondaryKpis: List[str] = []
