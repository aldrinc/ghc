from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from app.ads.apify_client import ApifyClient
from app.ads.ingestors.base import ChannelIngestor
from app.ads.normalization import normalize_facebook_page_url
from app.ads.types import IngestRequest, NormalizedAdWithAssets, NormalizedAsset, RawAdItem, NormalizeContext
from app.db.enums import AdChannelEnum, AdStatusEnum, MediaAssetTypeEnum
from app.db.models import BrandChannelIdentity


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc)
    except Exception:
        return None


class MetaAdsLibraryIngestor(ChannelIngestor):
    channel = AdChannelEnum.META_ADS_LIBRARY

    def __init__(self, apify_client: ApifyClient) -> None:
        self.apify_client = apify_client
        self.actor_id = os.getenv("APIFY_META_ACTOR_ID", "curious_coder~facebook-ads-library-scraper")

    def build_requests(self, identity: BrandChannelIdentity, *, results_limit: int | None = None) -> List[IngestRequest]:
        """
        Build ingestion requests using canonical Facebook Page URLs only.
        Numeric page IDs are ignored; the scraper derives them internally.
        """
        candidate_urls: List[str] = []
        if identity.external_url:
            candidate_urls.append(identity.external_url)
        if identity.metadata_json:
            for url in identity.metadata_json.get("facebook_page_urls") or []:
                candidate_urls.append(url)

        normalized: List[str] = []
        for url in candidate_urls:
            canonical = normalize_facebook_page_url(url)
            if canonical and canonical not in normalized:
                normalized.append(canonical)

        if not normalized:
            raise RuntimeError("Missing Facebook page URL for Meta Ads ingestion")

        requests: List[IngestRequest] = []
        for url in normalized:
            metadata = {
                "identity_id": identity.id,
                "page_url": url,
            }
            requests.append(IngestRequest(url=url, limit=results_limit or None, metadata=metadata))
        return requests

    def run(self, request: IngestRequest) -> list[RawAdItem]:
        active_status = os.getenv("APIFY_META_ACTIVE_STATUS", "active")
        items, meta = self._run_actor(request.url, request.limit, active_status=active_status)

        has_ads = self._has_ad_payload(items)
        combined_meta = {**meta, **(request.metadata or {}), "requested_url": request.url, "active_status": active_status}

        # Fallback: if nothing came back and we asked for active ads only, retry once with all statuses.
        if not has_ads and active_status.lower() == "active":
            retry_status = "all"
            retry_items, retry_meta = self._run_actor(request.url, request.limit, active_status=retry_status)
            retry_has_ads = self._has_ad_payload(retry_items)
            if retry_has_ads or not items:
                items, meta = retry_items, retry_meta
                combined_meta.update(meta)
                combined_meta["active_status"] = retry_status
            else:
                combined_meta.update(retry_meta)

        # Always return at least one RawAdItem so provider_run_id/dataset_id are preserved even when no ads.
        wrapped: List[RawAdItem] = []
        if items:
            for item in items:
                wrapped.append(RawAdItem(payload=item, metadata=combined_meta))
        else:
            wrapped.append(
                RawAdItem(
                    payload={"error": "no_items_returned"},
                    metadata=combined_meta,
                )
            )
        return wrapped

    def _run_actor(self, url: str, limit: int | None, *, active_status: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        limit_per_source = limit or int(os.getenv("APIFY_META_LIMIT_PER_SOURCE", "50"))
        payload: Dict[str, Any] = {
            "urls": [{"url": url}],
            "scrapeAdDetails": True,
            "scrapePageAds.activeStatus": active_status,
            "scrapePageAds.countryCode": os.getenv("APIFY_META_COUNTRY_CODE", "ALL"),
        }
        if limit_per_source:
            payload["limitPerSource"] = limit_per_source
            payload["count"] = limit_per_source
            payload["maxItems"] = limit_per_source
        run = self.apify_client.start_actor_run(self.actor_id, input_payload=payload)
        run_id = run.get("id") or run.get("runId")
        if not run_id:
            raise RuntimeError("Apify actor run did not return an id")
        final_run = self.apify_client.poll_run_until_terminal(run_id)
        dataset_id = final_run.get("defaultDatasetId")
        items: List[Dict[str, Any]] = []
        if dataset_id:
            items = self.apify_client.fetch_dataset_items(dataset_id, limit=limit)

        meta = {"provider_run_id": run_id, "dataset_id": dataset_id, "actor_id": self.actor_id, "actor_input": payload}
        return items, meta

    def normalize(self, raw: RawAdItem, ctx: NormalizeContext) -> NormalizedAdWithAssets | None:
        data = raw.payload or {}
        if data.get("error"):
            return None
        external_id = (
            data.get("adArchiveId")
            or data.get("ad_archive_id")
            or data.get("ad_snapshot_id")
            or data.get("id")
            or ""
        )
        snapshot: Dict[str, Any] = data.get("snapshot") or {}
        body_text = (
            snapshot.get("body", {}) or {}
        )
        body_text = body_text.get("text") or data.get("body") or data.get("bodyText") or data.get("text")
        headline = snapshot.get("title") or data.get("headline") or data.get("title")
        cta_text = snapshot.get("cta_text") or data.get("ctaText") or data.get("cta_text")
        cta_type = snapshot.get("cta_type") or data.get("ctaType") or data.get("cta_type")
        landing_url = (
            snapshot.get("link_url")
            or data.get("linkUrl")
            or data.get("adLink")
            or data.get("landingPageUrl")
            or data.get("url")
        )
        assets: List[NormalizedAsset] = []
        for idx, card in enumerate(snapshot.get("cards") or []):
            if not isinstance(card, dict):
                continue
            # Prefer video when present; otherwise fall back to the card image.
            video_src = (
                card.get("video_hd_url")
                or card.get("video_sd_url")
                or card.get("watermarked_video_hd_url")
                or card.get("watermarked_video_sd_url")
            )
            image_src = (
                card.get("resized_image_url")
                or card.get("original_image_url")
                or card.get("watermarked_resized_image_url")
                or card.get("watermarked_original_image_url")
            )
            thumb = (
                card.get("video_preview_image_url")
                or card.get("thumbnail_url")
                or card.get("resized_image_url")
                or card.get("watermarked_resized_image_url")
                or card.get("original_image_url")
            )
            if video_src:
                assets.append(
                    NormalizedAsset(
                        asset_type=MediaAssetTypeEnum.VIDEO,
                        source_url=video_src,
                        metadata={"source": "meta_card_video", "raw": card, "preview_url": thumb},
                        role="PRIMARY",
                    )
                )
            if image_src:
                assets.append(
                    NormalizedAsset(
                        asset_type=MediaAssetTypeEnum.IMAGE,
                        source_url=image_src,
                        metadata={"source": "meta_card_image", "raw": card, "preview_url": thumb},
                        role="PRIMARY",
                    )
                )
        for img in snapshot.get("images") or []:
            url = None
            if isinstance(img, dict):
                url = img.get("original_image_url") or img.get("image_url") or img.get("url")
            else:
                url = img
            if not url:
                continue
            assets.append(
                NormalizedAsset(
                    asset_type=MediaAssetTypeEnum.IMAGE,
                    source_url=url,
                    metadata={"source": "meta_image", "raw": img} if isinstance(img, dict) else {"source": "meta_image"},
                    role="PRIMARY",
                )
            )
        for vid in snapshot.get("videos") or []:
            src = vid.get("video_hd_url") or vid.get("video_sd_url") or vid.get("url")
            thumb = vid.get("video_preview_image_url") or vid.get("thumbnail")
            if src:
                assets.append(
                    NormalizedAsset(
                        asset_type=MediaAssetTypeEnum.VIDEO,
                        source_url=src,
                        metadata={"source": "meta_video", "raw": vid},
                        role="PRIMARY",
                    )
                )
            if thumb:
                assets.append(
                    NormalizedAsset(
                        asset_type=MediaAssetTypeEnum.SCREENSHOT,
                        source_url=thumb,
                        metadata={"source": "meta_video_thumbnail"},
                        role="THUMBNAIL",
                    )
                )
        snapshot_url = data.get("snapshotUrl") or data.get("adSnapshotUrl") or snapshot.get("ad_library_url")
        if snapshot_url:
            assets.append(
                NormalizedAsset(
                    asset_type=MediaAssetTypeEnum.SCREENSHOT,
                    source_url=snapshot_url,
                    metadata={"source": "meta_snapshot"},
                )
            )

        return NormalizedAdWithAssets(
            external_ad_id=str(external_id),
            ad_status=self._map_status(data.get("status") or ("active" if data.get("is_active") else "inactive")),
            started_running_at=_parse_datetime(data.get("startDate") or data.get("start_date")),
            ended_running_at=_parse_datetime(data.get("endDate") or data.get("end_date")),
            first_seen_at=_parse_datetime(data.get("firstSeenDate") or data.get("start_date")),
            last_seen_at=_parse_datetime(data.get("lastSeenDate") or data.get("end_date")),
            body_text=body_text,
            headline=headline,
            cta_type=cta_type,
            cta_text=cta_text,
            landing_url=landing_url,
            raw_json=data,
            assets=assets,
        )

    @staticmethod
    def _map_status(status: Any) -> AdStatusEnum:
        text = str(status or "").lower()
        if text == "active":
            return AdStatusEnum.active
        if text == "inactive":
            return AdStatusEnum.inactive
        return AdStatusEnum.unknown

    @staticmethod
    def _has_ad_payload(items: List[Dict[str, Any]]) -> bool:
        for item in items or []:
            if not isinstance(item, dict):
                continue
            if item.get("error"):
                continue
            # Presence of snapshot/ad identifiers indicates a real ad row.
            if item.get("snapshot") or item.get("ad_archive_id") or item.get("adArchiveId") or item.get("ad_snapshot_id"):
                return True
        return False
