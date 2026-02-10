from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class FunnelCreateRequest(BaseModel):
    clientId: str
    campaignId: Optional[str] = None
    experimentId: Optional[str] = None
    productId: Optional[str] = None
    selectedOfferId: Optional[str] = None
    name: str
    description: Optional[str] = None


class FunnelUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    campaignId: Optional[str] = None
    experimentId: Optional[str] = None
    entryPageId: Optional[str] = None
    designSystemId: Optional[str] = None
    productId: Optional[str] = None
    selectedOfferId: Optional[str] = None


class FunnelDuplicateRequest(BaseModel):
    targetCampaignId: Optional[str] = None
    name: Optional[str] = None
    copyMode: Literal["approvedOnly", "activePublication"] = "approvedOnly"
    autoPublish: bool = False


class FunnelPageCreateRequest(BaseModel):
    name: str
    slug: Optional[str] = None
    templateId: Optional[str] = None
    designSystemId: Optional[str] = None
    nextPageId: Optional[str] = None


class FunnelPageUpdateRequest(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    ordering: Optional[int] = None
    designSystemId: Optional[str] = None
    nextPageId: Optional[str] = None


class FunnelPageSaveDraftRequest(BaseModel):
    puckData: dict[str, Any]


class PublicFunnelMetaResponse(BaseModel):
    publicId: str
    funnelId: str
    publicationId: str
    entrySlug: str
    pages: list[dict[str, str]]


class PublicFunnelPageResponse(BaseModel):
    funnelId: str
    publicationId: str
    pageId: str
    slug: str
    puckData: dict[str, Any]
    pageMap: dict[str, str]
    designSystemTokens: Optional[dict[str, Any]] = None
    nextPageId: Optional[str] = None


class PublicFunnelRedirectResponse(BaseModel):
    redirectToSlug: str


class PublicEventIn(BaseModel):
    eventType: str
    occurredAt: Optional[datetime] = None
    publicationId: str
    pageId: str
    visitorId: Optional[str] = None
    sessionId: Optional[str] = None
    path: Optional[str] = None
    referrer: Optional[str] = None
    utm: dict[str, Any] = Field(default_factory=dict)
    props: dict[str, Any] = Field(default_factory=dict)


class PublicEventsIngestRequest(BaseModel):
    events: list[PublicEventIn]


class GenerateFunnelImageRequest(BaseModel):
    prompt: str
    clientId: str
    aspectRatio: Optional[str] = None
    styleHints: Optional[dict[str, Any]] = None
    usageContext: Optional[dict[str, Any]] = None


class GenerateFunnelImageResponse(BaseModel):
    assetId: str
    publicId: str
    width: Optional[int] = None
    height: Optional[int] = None


class FunnelAIChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class FunnelAIAttachment(BaseModel):
    assetId: str
    publicId: str
    filename: Optional[str] = None
    contentType: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class FunnelPageAIGenerateRequest(BaseModel):
    prompt: str
    messages: list[FunnelAIChatMessage] = Field(default_factory=list)
    attachedAssets: list[FunnelAIAttachment] = Field(default_factory=list)
    copyPack: Optional[str] = None
    currentPuckData: Optional[dict[str, Any]] = None
    templateId: Optional[str] = None
    ideaWorkspaceId: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.2
    maxTokens: Optional[int] = None
    generateImages: bool = True
    maxImages: int = 3


class FunnelPageAIGenerateResponse(BaseModel):
    assistantMessage: str
    puckData: dict[str, Any]
    draftVersionId: str
    generatedImages: list[dict[str, Any]] = Field(default_factory=list)
    imagePlans: list[dict[str, Any]] = Field(default_factory=list)


class FunnelPageTestimonialGenerateRequest(BaseModel):
    draftVersionId: Optional[str] = None
    currentPuckData: Optional[dict[str, Any]] = None
    templateId: Optional[str] = None
    ideaWorkspaceId: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.3
    maxTokens: Optional[int] = None
    synthetic: bool = True


class FunnelPageTestimonialGenerateResponse(BaseModel):
    draftVersionId: str
    puckData: dict[str, Any]
    generatedTestimonials: list[dict[str, Any]] = Field(default_factory=list)


class FunnelTemplateSummary(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    previewImage: Optional[str] = None


class FunnelTemplateDetail(FunnelTemplateSummary):
    puckData: dict[str, Any]
