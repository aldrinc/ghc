from __future__ import annotations

from typing import List

from pydantic import BaseModel


class CampaignFunnelGenerationRequest(BaseModel):
    experimentIds: List[str]
