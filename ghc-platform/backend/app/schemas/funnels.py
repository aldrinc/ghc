from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class FunnelCreateRequest(BaseModel):
    clientId: str
    campaignId: Optional[str] = None
    name: str
    description: Optional[str] = None


class FunnelUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    campaignId: Optional[str] = None
    entryPageId: Optional[str] = None


class FunnelDuplicateRequest(BaseModel):
    targetCampaignId: Optional[str] = None
    name: Optional[str] = None
    copyMode: Literal["approvedOnly", "activePublication"] = "approvedOnly"
    autoPublish: bool = False


class FunnelPageCreateRequest(BaseModel):
    name: str
    slug: Optional[str] = None


class FunnelPageUpdateRequest(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    ordering: Optional[int] = None


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


class FunnelPageAIGenerateRequest(BaseModel):
    prompt: str
    messages: list[FunnelAIChatMessage] = Field(default_factory=list)
    currentPuckData: Optional[dict[str, Any]] = None
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
