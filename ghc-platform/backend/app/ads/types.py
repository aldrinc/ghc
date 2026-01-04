from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.db.enums import AdStatusEnum, MediaAssetTypeEnum


@dataclass
class IngestRequest:
    url: str
    limit: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RawAdItem:
    payload: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedAsset:
    asset_type: MediaAssetTypeEnum
    source_url: Optional[str] = None
    stored_url: Optional[str] = None
    sha256: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_ms: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    role: Optional[str] = None


@dataclass
class NormalizedAdWithAssets:
    external_ad_id: str
    ad_status: AdStatusEnum = AdStatusEnum.unknown
    started_running_at: Optional[datetime] = None
    ended_running_at: Optional[datetime] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    body_text: Optional[str] = None
    headline: Optional[str] = None
    cta_type: Optional[str] = None
    cta_text: Optional[str] = None
    landing_url: Optional[str] = None
    destination_domain: Optional[str] = None
    raw_json: Dict[str, Any] = field(default_factory=dict)
    assets: List[NormalizedAsset] = field(default_factory=list)


@dataclass
class NormalizeContext:
    brand_id: str
    brand_channel_identity_id: str
    research_run_id: str
    ingest_run_id: Optional[str] = None
