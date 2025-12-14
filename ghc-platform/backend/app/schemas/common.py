from typing import Optional
from pydantic import BaseModel, EmailStr


class ClientCreate(BaseModel):
    name: str
    industry: Optional[str] = None


class CampaignCreate(BaseModel):
    client_id: str
    name: str
    goal_description: Optional[str] = None
    objective_type: Optional[str] = None
    numeric_target: Optional[float] = None
    baseline: Optional[float] = None
    timeframe_days: Optional[int] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None


class UserCreate(BaseModel):
    email: EmailStr
    role: str
