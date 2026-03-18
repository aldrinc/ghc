from typing import Optional, List
from pydantic import BaseModel, EmailStr, field_validator

from app.schemas.asset_brief_types import normalize_required_asset_brief_types


class ClientCreate(BaseModel):
    name: str
    industry: Optional[str] = None
    strategyV2Enabled: bool = False


class CampaignCreate(BaseModel):
    client_id: str
    product_id: str
    name: str
    channels: List[str]
    asset_brief_types: List[str]
    start_planning: bool = False
    goal_description: Optional[str] = None
    objective_type: Optional[str] = None
    numeric_target: Optional[float] = None
    baseline: Optional[float] = None
    timeframe_days: Optional[int] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None

    @field_validator("asset_brief_types")
    @classmethod
    def _validate_asset_brief_types(cls, value: List[str]) -> List[str]:
        return normalize_required_asset_brief_types(value, field_name="asset_brief_types")


class UserCreate(BaseModel):
    email: EmailStr
    role: str
