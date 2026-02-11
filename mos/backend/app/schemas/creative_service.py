from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


IMAGE_JOB_STATUS = Literal["queued", "processing", "succeeded", "failed"]
VIDEO_TURN_STATUS = Literal["queued", "processing", "completed", "failed"]


class CreativeServiceImageAdsCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    reference_text: str | None = None
    reference_asset_ids: list[str] = Field(default_factory=list)
    count: int = Field(..., ge=1)
    aspect_ratio: str | None = None
    client_request_id: str | None = None


class CreativeServiceAssetCreateFromUriIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["image", "video", "audio"]
    source: Literal["upload", "generated", "derived"]
    primary_uri: str
    title: str | None = None
    description: str | None = None
    metadata_json: dict[str, Any] | None = None
    generate_proxy: bool = True


class CreativeServiceAssetOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    primary_uri: str | None = None
    primary_url: str | None = None


class CreativeServiceAssetRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    asset_id: str | None = None
    position: int | None = None
    output_index: int | None = None
    primary_uri: str | None = None
    primary_url: str | None = None
    prompt_used: str | None = None


class CreativeServiceImageAdsJob(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    status: IMAGE_JOB_STATUS
    prompt: str | None = None
    count: int | None = None
    aspect_ratio: str | None = None
    model_id: str | None = None
    error_detail: str | None = None
    references: list[CreativeServiceAssetRef] = Field(default_factory=list)
    outputs: list[CreativeServiceAssetRef] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreativeServiceVideoSessionCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    kind: Literal["freestyle"] = "freestyle"


class CreativeServiceVideoSessionOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    session_id: str | None = None

    @model_validator(mode="after")
    def _normalize_session_id(self) -> "CreativeServiceVideoSessionOut":
        if self.session_id is None and self.id is not None:
            self.session_id = self.id
        if self.session_id is None:
            raise ValueError("Video session response is missing session_id")
        return self


class CreativeServiceVideoAttachmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    title: str | None = None
    role: str | None = None


class CreativeServiceVideoMessageCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    attachments: list[CreativeServiceVideoAttachmentIn] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    client_request_id: str | None = None


class CreativeServiceVideoMessageOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    turn_id: str
    message: dict[str, Any] | None = None


class CreativeServiceVideoTurnOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    turn_id: str
    status: VIDEO_TURN_STATUS
    error_detail: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class CreativeServiceVideoProjectOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    recipe_ref: str | None = None
    pins: dict[str, Any] = Field(default_factory=dict)
    approvals: dict[str, Any] = Field(default_factory=dict)


class CreativeServiceVideoResultOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str
    project: CreativeServiceVideoProjectOut | None = None
    final_video: CreativeServiceAssetRef | None = None


class CreativeServiceErrorBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str | None = None
    message: str | None = None
    details: dict[str, Any] | None = None
    request_id: str | None = None


class CreativeServiceErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    error: CreativeServiceErrorBody | None = None
