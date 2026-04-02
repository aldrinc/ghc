from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class AgentThreadCreateRequest(BaseModel):
    clientId: str
    productId: str
    agentProfile: str = "copy"
    objectiveType: str = "presell_page_rewrite"
    bundleKey: str = "ember_v1"
    runtimeProfileKey: Optional[str] = None
    strategyBundleId: Optional[str] = None
    title: Optional[str] = None
    siteId: Optional[str] = None
    pageId: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_page_binding(self) -> "AgentThreadCreateRequest":
        if self.pageId and not self.siteId:
            raise ValueError("siteId is required when pageId is provided.")
        if self.siteId and not self.pageId:
            raise ValueError("pageId is required when siteId is provided.")
        return self


class AgentThreadPageSessionRequest(BaseModel):
    clientId: str
    productId: str
    siteId: str
    pageId: str
    agentProfile: str = "copy"
    objectiveType: str = "page_copy_agent"
    title: Optional[str] = None
    bundleKey: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    forceNew: bool = False


class AgentThreadMessageRequest(BaseModel):
    content: str = Field(min_length=1)


class ApprovalResolveRequest(BaseModel):
    targetKind: Literal["artifact", "site_page_version"]
    targetId: str
    decision: Literal["approved", "rejected"] = "approved"
    notes: Optional[str] = None


class AgentTurnResponse(BaseModel):
    id: str
    seq: int
    role: str
    content: str
    runId: Optional[str] = None
    artifactId: Optional[str] = None
    sitePageVersionId: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    createdAt: str


class RuntimeSessionResponse(BaseModel):
    id: str
    status: str
    runtimeHome: str
    hermesSessionId: Optional[str] = None
    projectionHash: str
    toolsets: list[str] = Field(default_factory=list)
    lastError: Optional[str] = None
    lastUsedAt: str


class ApprovalItemResponse(BaseModel):
    id: str
    targetKind: str
    artifactId: Optional[str] = None
    sitePageVersionId: Optional[str] = None
    status: str
    decision: Optional[str] = None
    resolutionNotes: Optional[str] = None
    createdAt: str
    resolvedAt: Optional[str] = None


class AgentThreadDetailResponse(BaseModel):
    thread: dict[str, Any]
    runtimeSession: RuntimeSessionResponse
    turns: list[AgentTurnResponse]
    approvals: list[ApprovalItemResponse]


class AgentThreadValidationResponse(AgentThreadDetailResponse):
    validation: dict[str, Any] = Field(default_factory=dict)
