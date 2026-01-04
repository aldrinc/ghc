from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from app.ads.apify_client import ApifyClient
from app.ads.ingestors.base import ChannelIngestor
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
        Prefer a direct Ads Library URL when a page ID is available; otherwise fall back to the page URL.
        We stash both the page_id and original URL in request metadata for later retries.
        """
        page_id = None
        if identity.external_id:
            page_id = str(identity.external_id).strip()
        elif identity.metadata_json:
            ids = identity.metadata_json.get("facebook_page_ids") or []
            if ids:
                page_id = str(ids[0]).strip()

        ads_library_url = self._ads_library_url(page_id) if page_id else None

        fallback_page_url = identity.external_url
        if not fallback_page_url and identity.external_id:
            fallback_page_url = f"https://www.facebook.com/{identity.external_id}"

        url = ads_library_url or fallback_page_url
        if not url:
            raise RuntimeError("Missing Facebook page URL or ID for Meta Ads ingestion")
        metadata = {
            "identity_id": identity.id,
            "page_id": page_id,
            "page_url": fallback_page_url,
            "ads_library_url_used": bool(ads_library_url),
        }
        return [IngestRequest(url=url, limit=results_limit or None, metadata=metadata)]

    def run(self, request: IngestRequest) -> list[RawAdItem]:
        # First attempt: whatever URL we were given (Ads Library URL when we have a page_id, otherwise the page URL).
        items, meta = self._run_actor(request.url, request.limit)

        has_ads = self._has_ad_payload(items)
        page_id_from_request = request.metadata.get("page_id") if isinstance(request.metadata, dict) else None
        page_id_from_error = self._page_id_from_items(items)
        page_id = page_id_from_request or page_id_from_error

        # Retry once with an Ads Library URL if the first attempt produced no ads or PAGE_PRIVATE/ADS_NOT_FOUND.
        # This helps when the raw page is private but the Ads Library page_id still works.
        if (not has_ads) and page_id and not (request.metadata or {}).get("ads_library_url_used"):
            retry_url = self._ads_library_url(page_id)
            if retry_url and retry_url != request.url:
                retry_items, retry_meta = self._run_actor(retry_url, request.limit)
                # Prefer the retry results; even error payloads should carry provider IDs for debugging.
                items, meta = retry_items, retry_meta

        # Always return at least one RawAdItem so provider_run_id/dataset_id are preserved even when no ads.
        wrapped: List[RawAdItem] = []
        combined_meta = {**meta, **(request.metadata or {}), "requested_url": request.url}
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

    def _run_actor(self, url: str, limit: int | None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "startUrls": [{"url": url}],
            "urls": [{"url": url}],
            "count": limit or 100,
            "maxItems": limit or 100,
            "period": "",
            "scrapeAdDetails": True,
            "scrapePageAds.activeStatus": os.getenv("APIFY_META_ACTIVE_STATUS", "active"),
            "scrapePageAds.countryCode": os.getenv("APIFY_META_COUNTRY_CODE", "ALL"),
        }
        run = self.apify_client.start_actor_run(self.actor_id, input_payload=payload)
        run_id = run.get("id") or run.get("runId")
        if not run_id:
            raise RuntimeError("Apify actor run did not return an id")
        final_run = self.apify_client.poll_run_until_terminal(run_id)
        dataset_id = final_run.get("defaultDatasetId")
        items: List[Dict[str, Any]] = []
        if dataset_id:
            items = self.apify_client.fetch_dataset_items(dataset_id, limit=limit)

        meta = {"provider_run_id": run_id, "dataset_id": dataset_id, "actor_id": self.actor_id}
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
    def _ads_library_url(page_id: str | None) -> str | None:
        if not page_id:
            return None
        pid = str(page_id).strip()
        if not pid:
            return None
        return (
            "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL"
            "&is_targeted_country=false&media_type=all&search_type=page&view_all_page_id="
            f"{pid}"
        )

    @staticmethod
    def _page_id_from_items(items: List[Dict[str, Any]]) -> str | None:
        for item in items or []:
            if not isinstance(item, dict):
                continue
            page_info = item.get("pageInfo") or {}
            pid = page_info.get("page_id") or item.get("page_id")
            if pid:
                return str(pid)
        return None

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
