from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class TeardownEvidenceInput(BaseModel):
    client_ref: Optional[str] = None
    evidence_type: str
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None

    # transcript
    speaker_role: Optional[str] = None
    spoken_text: Optional[str] = None
    onscreen_text: Optional[str] = None
    audio_notes: Optional[str] = None

    # storyboard
    scene_no: Optional[int] = None
    visual_description: Optional[str] = None
    action_blocking: Optional[str] = None
    narrative_job: Optional[str] = None

    # numeric claims
    value_numeric: Optional[Decimal] = None
    unit: Optional[str] = None
    claim_text: Optional[str] = None
    claim_topic: Optional[str] = None
    verification_status: Optional[str] = None
    source_url: Optional[str] = None

    # targeting signals
    modality: Optional[str] = None
    category: Optional[str] = None
    value: Optional[str] = None
    is_observation: Optional[bool] = True
    confidence: Optional[Decimal] = None

    # narrative beats
    beat_key: Optional[str] = None
    description: Optional[str] = None

    # proof usages
    proof_type: Optional[str] = None
    proof_description: Optional[str] = None

    # cta
    cta_kind: Optional[str] = None
    cta_text: Optional[str] = None
    offer_stack_present: Optional[bool] = None
    risk_reversal_present: Optional[bool] = None
    notes: Optional[str] = None

    # production requirements
    req_type: Optional[str] = None
    req_value: Optional[str] = None

    # ad copy block
    copy_field: Optional[str] = Field(default=None, alias="field")
    copy_text: Optional[str] = Field(default=None, alias="text")
    copy_raw_text: Optional[str] = Field(default=None, alias="raw_text")
    copy_language: Optional[str] = Field(default=None, alias="language")


class TeardownAssertionInput(BaseModel):
    assertion_type: str
    assertion_text: str
    confidence: Optional[Decimal] = None
    evidence_refs: List[str] = Field(default_factory=list)


class TeardownUpsertRequest(BaseModel):
    creative_id: Optional[str] = None
    ad_id: Optional[str] = None
    client_id: Optional[str] = None
    campaign_id: Optional[str] = None
    research_run_id: Optional[str] = None
    schema_version: int = 1
    captured_at: Optional[datetime] = None
    funnel_stage: Optional[str] = None
    one_liner: Optional[str] = None
    algorithmic_thesis: Optional[str] = None
    hook_score: Optional[int] = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    evidence_items: List[TeardownEvidenceInput] = Field(default_factory=list)
    assertions: List[TeardownAssertionInput] = Field(default_factory=list)


class TeardownEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    evidence_type: str
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    payload: dict[str, Any]


class TeardownAssertionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assertion_type: str
    assertion_text: str
    confidence: Optional[Decimal] = None
    evidence_item_ids: List[str] = Field(default_factory=list)
    created_by_user_id: Optional[str] = None
    created_at: Optional[datetime] = None


class TeardownResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    creative_id: str
    brand_id: Optional[str] = None
    brand_name: Optional[str] = None
    channel: Optional[str] = None
    creative_fingerprint: Optional[str] = None
    primary_media_asset_url: Optional[str] = None
    client_id: Optional[str] = None
    campaign_id: Optional[str] = None
    research_run_id: Optional[str] = None
    schema_version: int
    captured_at: Optional[datetime] = None
    funnel_stage: Optional[str] = None
    one_liner: Optional[str] = None
    algorithmic_thesis: Optional[str] = None
    hook_score: Optional[int] = None
    raw_payload: dict[str, Any]
    is_canonical: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    evidence_items: List[TeardownEvidenceResponse] = Field(default_factory=list)
    assertions: List[TeardownAssertionResponse] = Field(default_factory=list)
