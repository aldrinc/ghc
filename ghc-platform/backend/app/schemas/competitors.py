from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class CompetitorRow(BaseModel):
    name: str
    website: Optional[str] = None
    facebook_page_url: Optional[str] = None
    facebook_page_id: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class ExtractCompetitorsRequest(BaseModel):
    step1_content: str

    model_config = ConfigDict(extra="forbid")


class ExtractCompetitorsResult(BaseModel):
    competitors: List[CompetitorRow]
    chosen_table_reason: str = ""
    chosen_table_markdown: str = ""

    model_config = ConfigDict(extra="forbid")


class ResolveFacebookRequest(BaseModel):
    competitors: List[CompetitorRow]
    category_niche: Optional[str] = None
    org_id: Optional[str] = None
    client_id: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class ResolveFacebookResult(BaseModel):
    competitors: List[CompetitorRow]
    evidence: Dict[str, str] = {}

    model_config = ConfigDict(extra="forbid")
