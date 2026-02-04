from typing import List, Optional
from pydantic import BaseModel


class ChannelPlan(BaseModel):
    channel: str
    objective: Optional[str] = None
    budgetSplitPercent: Optional[float] = None
    notes: Optional[str] = None


class MessagingPillar(BaseModel):
    title: str
    proofPoints: List[str] = []


class StrategySheet(BaseModel):
    clientId: str
    campaignId: Optional[str] = None
    goal: Optional[str] = None
    hypothesis: Optional[str] = None
    channelPlan: List[ChannelPlan] = []
    messaging: List[MessagingPillar] = []
    risks: List[str] = []
    mitigations: List[str] = []
