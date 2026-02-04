from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict
from pydantic import field_validator

from app.ads.normalization import normalize_facebook_page_url


class CompetitorRow(BaseModel):
    name: str
    website: Optional[str] = None
    facebook_page_url: Optional[str] = None
    facebook_page_url_source: Optional[str] = None
    facebook_page_url_confidence: Optional[float] = None
    facebook_page_url_evidence: Optional[List[str]] = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("facebook_page_url", mode="after")
    @classmethod
    def _normalize_facebook_url(cls, value: Optional[str]) -> Optional[str]:
        return normalize_facebook_page_url(value)

    @field_validator("facebook_page_url_evidence", mode="after")
    @classmethod
    def _dedupe_evidence(cls, evidence: Optional[List[str]]) -> Optional[List[str]]:
        if not evidence:
            return None
        seen: List[str] = []
        for url in evidence:
            cleaned = (url or "").strip()
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        return seen or None


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
