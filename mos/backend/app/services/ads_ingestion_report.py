from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.enums import AdIngestStatusEnum, MediaMirrorStatusEnum
from app.db.models import (
    Ad,
    AdAssetLink,
    AdIngestRun,
    Brand,
    BrandChannelIdentity,
    MediaAsset,
    ResearchRunBrand,
)


@dataclass(frozen=True)
class AdsIngestionReport:
    research_run_id: str
    generated_at_iso: str
    summary: dict[str, Any]
    ingest_runs: dict[str, Any]
    media_mirror: dict[str, Any]


class AdsIngestionReportService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def build_report(
        self,
        *,
        research_run_id: str,
        limit_failed_media_samples: int = 20,
        limit_failed_run_samples: int = 50,
    ) -> AdsIngestionReport:
        now_iso = datetime.now(timezone.utc).isoformat()

        run_rows = list(
            self.session.execute(
                select(AdIngestRun, BrandChannelIdentity, Brand)
                .join(BrandChannelIdentity, BrandChannelIdentity.id == AdIngestRun.brand_channel_identity_id)
                .join(Brand, Brand.id == BrandChannelIdentity.brand_id)
                .where(AdIngestRun.research_run_id == research_run_id)
                .order_by(AdIngestRun.started_at.desc())
            ).all()
        )

        runs: list[dict[str, Any]] = []
        for ingest_run, identity, brand in run_rows:
            status_raw = getattr(ingest_run, "status", None)
            status = (
                getattr(status_raw, "value", None)
                if status_raw is not None
                else None
            ) or (str(status_raw) if status_raw is not None else None)
            runs.append(
                {
                    "ad_ingest_run_id": str(getattr(ingest_run, "id", "")),
                    "research_run_id": str(getattr(ingest_run, "research_run_id", "")),
                    "brand_channel_identity_id": str(getattr(ingest_run, "brand_channel_identity_id", "")),
                    "brand_id": str(getattr(identity, "brand_id", "")),
                    "brand_name": getattr(brand, "canonical_name", None) or getattr(brand, "normalized_name", None),
                    "channel": getattr(getattr(ingest_run, "channel", None), "value", None)
                    or str(getattr(ingest_run, "channel", "")),
                    "requested_url": getattr(ingest_run, "requested_url", None),
                    "provider": getattr(ingest_run, "provider", None),
                    "provider_run_id": getattr(ingest_run, "provider_run_id", None),
                    "provider_dataset_id": getattr(ingest_run, "provider_dataset_id", None),
                    "status": status,
                    "is_partial": bool(getattr(ingest_run, "is_partial", False)),
                    "results_limit": getattr(ingest_run, "results_limit", None),
                    "items_count": int(getattr(ingest_run, "items_count", 0) or 0),
                    "error": getattr(ingest_run, "error", None),
                    "started_at": ingest_run.started_at.isoformat() if getattr(ingest_run, "started_at", None) else None,
                    "finished_at": ingest_run.finished_at.isoformat() if getattr(ingest_run, "finished_at", None) else None,
                }
            )

        # Latest status by identity (dedupe multiple attempts).
        seen_identities: set[str] = set()
        latest_by_identity: list[dict[str, Any]] = []
        for item in runs:
            identity_id = str(item.get("brand_channel_identity_id") or "")
            if not identity_id or identity_id in seen_identities:
                continue
            seen_identities.add(identity_id)
            latest_by_identity.append(item)

        status_counts = Counter((item.get("status") or "UNKNOWN") for item in latest_by_identity)

        failed_identity_ids = [
            str(item.get("brand_channel_identity_id"))
            for item in latest_by_identity
            if item.get("status") == AdIngestStatusEnum.FAILED.value
        ]

        failed_run_samples = [
            item
            for item in latest_by_identity
            if item.get("status") == AdIngestStatusEnum.FAILED.value
        ][: max(0, int(limit_failed_run_samples))]

        ad_count = self.session.execute(
            select(func.count())
            .select_from(Ad)
            .join(ResearchRunBrand, ResearchRunBrand.brand_id == Ad.brand_id)
            .where(ResearchRunBrand.research_run_id == research_run_id)
        ).scalar_one()

        media_counts = list(
            self.session.execute(
                select(
                    MediaAsset.mirror_status,
                    MediaAsset.mirror_error,
                    func.count(func.distinct(MediaAsset.id)).label("asset_count"),
                )
                .select_from(MediaAsset)
                .join(AdAssetLink, AdAssetLink.media_asset_id == MediaAsset.id)
                .join(Ad, Ad.id == AdAssetLink.ad_id)
                .join(ResearchRunBrand, ResearchRunBrand.brand_id == Ad.brand_id)
                .where(ResearchRunBrand.research_run_id == research_run_id)
                .group_by(MediaAsset.mirror_status, MediaAsset.mirror_error)
            ).all()
        )

        mirror_status_counts = Counter()
        mirror_error_counts = Counter()
        total_media_assets = 0
        for mirror_status_raw, mirror_error, asset_count in media_counts:
            count = int(asset_count or 0)
            total_media_assets += count
            status = (
                getattr(mirror_status_raw, "value", None)
                if mirror_status_raw is not None
                else None
            ) or (str(mirror_status_raw) if mirror_status_raw is not None else "unknown")
            mirror_status_counts[status] += count
            if mirror_error:
                mirror_error_counts[str(mirror_error)] += count

        missing_storage_key_count = self.session.execute(
            select(func.count(func.distinct(MediaAsset.id)))
            .select_from(MediaAsset)
            .join(AdAssetLink, AdAssetLink.media_asset_id == MediaAsset.id)
            .join(Ad, Ad.id == AdAssetLink.ad_id)
            .join(ResearchRunBrand, ResearchRunBrand.brand_id == Ad.brand_id)
            .where(ResearchRunBrand.research_run_id == research_run_id)
            .where(MediaAsset.storage_key.is_(None))
        ).scalar_one()

        failed_media_assets = list(
            self.session.scalars(
                select(MediaAsset)
                .join(AdAssetLink, AdAssetLink.media_asset_id == MediaAsset.id)
                .join(Ad, Ad.id == AdAssetLink.ad_id)
                .join(ResearchRunBrand, ResearchRunBrand.brand_id == Ad.brand_id)
                .where(ResearchRunBrand.research_run_id == research_run_id)
                .where(
                    or_(
                        MediaAsset.mirror_status == MediaMirrorStatusEnum.failed,
                        MediaAsset.storage_key.is_(None),
                    )
                )
                .distinct()
                .limit(max(0, int(limit_failed_media_samples)))
            ).all()
        )
        failed_media_samples: list[dict[str, Any]] = []
        for asset in failed_media_assets:
            mirror_status_raw = getattr(asset, "mirror_status", None)
            mirror_status = (
                getattr(mirror_status_raw, "value", None)
                if mirror_status_raw is not None
                else None
            ) or (str(mirror_status_raw) if mirror_status_raw is not None else None)
            failed_media_samples.append(
                {
                    "media_asset_id": str(getattr(asset, "id", "")),
                    "asset_type": getattr(getattr(asset, "asset_type", None), "value", None)
                    or str(getattr(asset, "asset_type", "")),
                    "mirror_status": mirror_status,
                    "mirror_error": getattr(asset, "mirror_error", None),
                    "source_url": getattr(asset, "source_url", None),
                    "storage_key": getattr(asset, "storage_key", None),
                    "preview_storage_key": getattr(asset, "preview_storage_key", None),
                }
            )

        return AdsIngestionReport(
            research_run_id=research_run_id,
            generated_at_iso=now_iso,
            summary={
                "ad_count": int(ad_count or 0),
                "identity_count": len(latest_by_identity),
            },
            ingest_runs={
                "latest_by_identity": latest_by_identity,
                "status_counts": dict(status_counts),
                "failed_identity_ids": failed_identity_ids,
                "failed_runs_sample": failed_run_samples,
            },
            media_mirror={
                "total_media_assets": total_media_assets,
                "mirror_status_counts": dict(mirror_status_counts),
                "mirror_error_counts": dict(mirror_error_counts.most_common(25)),
                "missing_storage_key_count": int(missing_storage_key_count or 0),
                "failed_media_samples": failed_media_samples,
            },
        )
