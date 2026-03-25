"""
GetHookd Sync Activities.

Activities for syncing GetHookd Explore ads into MOS.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from temporalio import activity

from app.config import settings
from app.db.deps import get_session
from app.db.enums import MediaAssetTypeEnum
from app.db.models import CompanySwipeAsset, CompanySwipeMedia
from app.db.repositories.gethookd import (
    GetHookdCredentialsRepository,
    GetHookdSyncFeedsRepository,
    GetHookdSyncRunsRepository,
)
from app.db.repositories.swipes import (
    GETHOOKD_INBOX_COLLECTION_KIND,
    GETHOOKD_REVIEW_STATUS_PENDING,
    CompanySwipesRepository,
    SwipeCollectionsRepository,
)
from app.db.models import GETHOOKD_ORIGIN_SYSTEM

# Define stale status for GetHookd synced assets
GETHOOKD_REVIEW_STATUS_STALE = "stale_after_sync"


from app.services.gethookd_client import (
    GetHookdClient,
    GetHookdClientError,
    GetHookdExploreFilters,
    create_gethookd_client,
)
from app.services.integration_secrets import decrypt_secret_json
from app.services.remote_media import RemoteMediaInput, RemoteMediaService

logger = logging.getLogger(__name__)


@dataclass
class GetHookdSyncActivityInput:
    """Input for the GetHookd sync activity."""

    org_id: str
    client_id: str


@dataclass
class GetHookdSyncActivityOutput:
    """Output from the GetHookd sync activity."""

    status: str
    feeds_attempted: int
    feeds_succeeded: int
    assets_new: int
    assets_updated: int
    assets_marked_stale: int
    assets_failed: int
    credits_used: int
    error_summary: Optional[str] = None


def _build_remote_media_inputs(
    *,
    swipe_asset_id: str,
    media_items: list[dict[str, Any]],
) -> list[RemoteMediaInput]:
    remote_media_inputs: list[RemoteMediaInput] = []
    for idx, media_item in enumerate(media_items or []):
        source_url = media_item.get("url") or media_item.get("image_url")
        if not source_url:
            continue
        asset_type = (
            MediaAssetTypeEnum.VIDEO if media_item.get("type") == "video" else MediaAssetTypeEnum.IMAGE
        )
        remote_media_inputs.append(
            RemoteMediaInput(
                source_url=source_url,
                asset_type=asset_type,
                metadata={
                    "swipe_asset_id": swipe_asset_id,
                    "role": "primary" if idx == 0 else "secondary",
                    "gethookd_media": media_item,
                },
            )
        )
    return remote_media_inputs


def _media_signature_from_inputs(remote_media_inputs: list[RemoteMediaInput]) -> list[tuple[str, str]]:
    return [
        (remote_media.asset_type.value, remote_media.source_url)
        for remote_media in remote_media_inputs
        if remote_media.source_url
    ]


def _media_signature_from_rows(media_rows: list[CompanySwipeMedia]) -> list[tuple[str, str]]:
    return [
        (
            str(media.type or "").strip().lower(),
            str(media.url or media.download_url or "").strip(),
        )
        for media in media_rows
        if str(media.url or media.download_url or "").strip()
    ]


def _sync_swipe_media(
    *,
    swipes_repo: CompanySwipesRepository,
    remote_media_service: RemoteMediaService,
    org_id: str,
    swipe_asset_id: str,
    remote_media_inputs: list[RemoteMediaInput],
    replace_existing: bool,
) -> None:
    if replace_existing and not remote_media_inputs:
        return
    if replace_existing:
        swipes_repo.delete_media_for_asset(org_id=org_id, swipe_asset_id=swipe_asset_id)
    for remote_media in remote_media_inputs:
        remote_result = remote_media_service.upsert_and_mirror(
            channel="meta",
            remote_media=remote_media,
        )
        swipes_repo.create_media(
            org_id=org_id,
            swipe_asset_id=swipe_asset_id,
            media_asset_id=remote_result.media_asset_id,
            url=remote_media.source_url,
            type=remote_media.asset_type.value,
        )


@activity.defn
async def gethookd_sync_workspace_activity(
    input: GetHookdSyncActivityInput,
) -> GetHookdSyncActivityOutput:
    """
    Sync GetHookd Explore ads for a specific workspace.

    This activity:
    1. Loads/GetHookd credentials
    2. Loads enabled sync feeds
    3. For each feed, fetches ads and upserts them
    4. Records sync run metrics
    """
    logger.info(
        "gethookd_sync_workspace.started",
        extra={
            "org_id": input.org_id,
            "client_id": input.client_id,
        },
    )

    # Check SWIPE_TAXONOMY_MODEL is configured - required for taxonomy analysis
    if not settings.SWIPE_TAXONOMY_MODEL:
        logger.error(
            "gethookd_sync.swipe_taxonomy_model_missing",
            extra={
                "org_id": input.org_id,
                "client_id": input.client_id,
            },
        )
        return GetHookdSyncActivityOutput(
            status="failed",
            feeds_attempted=0,
            feeds_succeeded=0,
            assets_new=0,
            assets_updated=0,
            assets_marked_stale=0,
            assets_failed=0,
            credits_used=0,
            error_summary="SWIPE_TAXONOMY_MODEL is not configured - taxonomy analysis required for new assets",
        )

    # Create a new session for this activity
    session = next(get_session())

    try:
        # Load credentials
        creds_repo = GetHookdCredentialsRepository(session)
        credentials = creds_repo.get(org_id=input.org_id, client_id=input.client_id)

        if credentials is None:
            return GetHookdSyncActivityOutput(
                status="skipped",
                feeds_attempted=0,
                feeds_succeeded=0,
                assets_new=0,
                assets_updated=0,
                assets_marked_stale=0,
                assets_failed=0,
                credits_used=0,
                error_summary="No GetHookd credentials configured",
            )

        # Decrypt the API token
        creds = decrypt_secret_json(credentials.credentials_encrypted)
        api_token = creds.get("apiToken")

        if not api_token:
            return GetHookdSyncActivityOutput(
                status="failed",
                feeds_attempted=0,
                feeds_succeeded=0,
                assets_new=0,
                assets_updated=0,
                assets_marked_stale=0,
                assets_failed=0,
                credits_used=0,
                error_summary="API token is missing",
            )

        # Create GetHookd client
        client = create_gethookd_client(api_token)

        # Load enabled feeds
        feeds_repo = GetHookdSyncFeedsRepository(session)
        feeds = feeds_repo.list(
            org_id=input.org_id,
            client_id=input.client_id,
            enabled_only=True,
        )

        if not feeds:
            return GetHookdSyncActivityOutput(
                status="skipped",
                feeds_attempted=0,
                feeds_succeeded=0,
                assets_new=0,
                assets_updated=0,
                assets_marked_stale=0,
                assets_failed=0,
                credits_used=0,
                error_summary="No enabled GetHookd sync feeds",
            )

        # Create sync run record
        runs_repo = GetHookdSyncRunsRepository(session)
        run = runs_repo.create(
            org_id=input.org_id,
            client_id=input.client_id,
        )

        # Initialize counters
        feeds_attempted = 0
        feeds_succeeded = 0
        assets_new = 0
        assets_updated = 0
        assets_marked_stale = 0
        assets_failed = 0
        credits_used = 0

        # Ensure GetHookd inbox collection exists
        collections_repo = SwipeCollectionsRepository(session)
        gethookd_collection = collections_repo.ensure_gethookd_collection(
            org_id=input.org_id,
        )

        # Process each feed
        swipes_repo = CompanySwipesRepository(session)
        remote_media_service = RemoteMediaService(session)

        for feed in feeds:
            feeds_attempted += 1

            try:
                # Parse filters from feed
                filters = GetHookdExploreFilters(
                    query=feed.filters_json.get("query", ""),
                    platforms=feed.filters_json.get("platforms", "facebook,instagram"),
                    niche=feed.filters_json.get("niche"),
                    ad_format=feed.filters_json.get("ad_format"),
                    location=feed.filters_json.get("location"),
                    language=feed.filters_json.get("language"),
                    performance_scores=feed.filters_json.get(
                        "performance_scores", "winning,optimized"
                    ),
                    status=feed.filters_json.get("status", "active"),
                    sort_column=feed.filters_json.get("sort_column", "days_active"),
                    sort_direction=feed.filters_json.get("sort_direction", "desc"),
                    ads_per_brand_limit=feed.filters_json.get("ads_per_brand_limit", 3),
                )

                max_pages = feed.max_pages_per_run or 5
                per_page = feed.per_page or 100

                feed_assets_new = 0
                feed_assets_updated = 0
                feed_assets_marked_stale = 0
                feed_assets_failed = 0

                # Fetch pages
                for page in range(1, max_pages + 1):
                    try:
                        results = client.explore(
                            filters=filters,
                            page=page,
                            per_page=per_page,
                        )
                        credits_used += len(results)

                        for ad_result in results:
                            asset_savepoint = session.begin_nested()
                            try:
                                # Compute payload hash for change detection
                                payload_hash = hashlib.sha256(
                                    json.dumps(ad_result.raw_json, sort_keys=True).encode()
                                ).hexdigest()

                                # Upsert brand
                                brand = None
                                if ad_result.brand_id:
                                    brand = swipes_repo.upsert_brand(
                                        org_id=input.org_id,
                                        external_brand_id=ad_result.brand_id,
                                        name=ad_result.brand_name or "Unknown",
                                        logo_url=ad_result.brand_logo_url,
                                        ad_library_link=ad_result.ad_library_link,
                                    )

                                # Check if asset exists
                                existing = swipes_repo.get_asset_by_external_id(
                                    org_id=input.org_id,
                                    origin_system=GETHOOKD_ORIGIN_SYSTEM,
                                    external_ad_id=ad_result.id,
                                )

                                now = datetime.now(timezone.utc)
                                remote_media_inputs = _build_remote_media_inputs(
                                    swipe_asset_id=str(existing.id) if existing is not None else "",
                                    media_items=ad_result.media or [],
                                )

                                if existing is None:
                                    # New asset - create it
                                    new_asset = swipes_repo.create_asset(
                                        org_id=input.org_id,
                                        source_kind="catalog",
                                        origin_system=GETHOOKD_ORIGIN_SYSTEM,
                                        external_ad_id=ad_result.id,
                                        external_platform_ad_id=ad_result.external_id,
                                        brand_id=brand.id if brand else None,
                                        title=ad_result.title,
                                        body=ad_result.body,
                                        platforms=ad_result.platform,
                                        cta_type=ad_result.cta_type,
                                        cta_text=ad_result.cta_text,
                                        display_format=ad_result.display_format,
                                        landing_page=ad_result.landing_page,
                                        ad_source_link=ad_result.share_url,
                                        share_url=ad_result.share_url,
                                        days_active=ad_result.days_active,
                                        active_in_library=ad_result.active_in_library,
                                        used_count=ad_result.used_count,
                                        performance_score=ad_result.performance_score,
                                        performance_score_data={
                                            "title": ad_result.performance_score_title
                                        },
                                        ad_library_object=ad_result.raw_json,
                                        review_status=GETHOOKD_REVIEW_STATUS_PENDING,
                                        source_first_seen_at=now,
                                        source_last_seen_at=now,
                                        source_last_synced_at=now,
                                        source_payload_hash=payload_hash,
                                        source_metadata_json={
                                            "feed_id": str(feed.id),
                                            "feed_name": feed.name,
                                            "run_id": str(run.id),
                                        },
                                        analysis_status="queued",
                                        analysis_model=settings.SWIPE_TAXONOMY_MODEL,
                                    )

                                    _sync_swipe_media(
                                        swipes_repo=swipes_repo,
                                        remote_media_service=remote_media_service,
                                        org_id=input.org_id,
                                        swipe_asset_id=str(new_asset.id),
                                        remote_media_inputs=_build_remote_media_inputs(
                                            swipe_asset_id=str(new_asset.id),
                                            media_items=ad_result.media or [],
                                        ),
                                        replace_existing=False,
                                    )

                                    # Add to GetHookd collection
                                    collections_repo.add_item_if_missing(
                                        org_id=input.org_id,
                                        collection_id=str(gethookd_collection.id),
                                        swipe_asset_id=str(new_asset.id),
                                    )

                                    feed_assets_new += 1

                                else:
                                    # Existing asset - check for content changes
                                    existing_media = swipes_repo.list_media(
                                        org_id=input.org_id,
                                        swipe_asset_id=str(existing.id),
                                    )
                                    media_changed = bool(remote_media_inputs) and (
                                        _media_signature_from_rows(existing_media)
                                        != _media_signature_from_inputs(remote_media_inputs)
                                    )
                                    creative_changed = (
                                        existing.title != ad_result.title
                                        or existing.body != ad_result.body
                                        or existing.cta_type != ad_result.cta_type
                                        or existing.cta_text != ad_result.cta_text
                                        or existing.landing_page != ad_result.landing_page
                                        or existing.display_format != ad_result.display_format
                                        or media_changed
                                    )

                                    new_review_status = existing.review_status
                                    if (
                                        existing.source_payload_hash
                                        and existing.source_payload_hash != payload_hash
                                    ):
                                        if creative_changed:
                                            new_review_status = GETHOOKD_REVIEW_STATUS_STALE

                                    # Update the asset
                                    swipes_repo.update_asset(
                                        org_id=input.org_id,
                                        swipe_id=str(existing.id),
                                        external_platform_ad_id=ad_result.external_id,
                                        brand_id=brand.id if brand else existing.brand_id,
                                        title=ad_result.title,
                                        body=ad_result.body,
                                        platforms=ad_result.platform,
                                        cta_type=ad_result.cta_type,
                                        cta_text=ad_result.cta_text,
                                        display_format=ad_result.display_format,
                                        landing_page=ad_result.landing_page,
                                        ad_source_link=ad_result.share_url,
                                        share_url=ad_result.share_url,
                                        days_active=ad_result.days_active,
                                        active_in_library=ad_result.active_in_library,
                                        used_count=ad_result.used_count,
                                        performance_score=ad_result.performance_score,
                                        performance_score_data={
                                            "title": ad_result.performance_score_title
                                        },
                                        ad_library_object=ad_result.raw_json,
                                        source_last_seen_at=now,
                                        source_last_synced_at=now,
                                        source_payload_hash=payload_hash,
                                        source_metadata_json={
                                            "feed_id": str(feed.id),
                                            "feed_name": feed.name,
                                            "run_id": str(run.id),
                                        },
                                        source_content_changed_at=now
                                        if creative_changed
                                        else existing.source_content_changed_at,
                                        review_status=new_review_status,
                                    )
                                    if media_changed:
                                        _sync_swipe_media(
                                            swipes_repo=swipes_repo,
                                            remote_media_service=remote_media_service,
                                            org_id=input.org_id,
                                            swipe_asset_id=str(existing.id),
                                            remote_media_inputs=remote_media_inputs,
                                            replace_existing=True,
                                        )
                                    collections_repo.add_item_if_missing(
                                        org_id=input.org_id,
                                        collection_id=str(gethookd_collection.id),
                                        swipe_asset_id=str(existing.id),
                                    )

                                    if new_review_status == GETHOOKD_REVIEW_STATUS_STALE:
                                        feed_assets_marked_stale += 1
                                    else:
                                        feed_assets_updated += 1

                                asset_savepoint.commit()

                            except Exception as exc:
                                asset_savepoint.rollback()
                                logger.warning(
                                    "gethookd_sync.asset_failed",
                                    extra={
                                        "ad_id": ad_result.id,
                                        "error": str(exc),
                                    },
                                )
                                feed_assets_failed += 1

                    except GetHookdClientError as exc:
                        logger.warning(
                            "gethookd_sync.page_failed",
                            extra={
                                "feed_id": str(feed.id),
                                "page": page,
                                "error": str(exc),
                            },
                        )
                        break  # Stop fetching this feed on error

                session.commit()
                feeds_succeeded += 1
                assets_new += feed_assets_new
                assets_updated += feed_assets_updated
                assets_marked_stale += feed_assets_marked_stale
                assets_failed += feed_assets_failed

            except Exception as exc:
                logger.warning(
                    "gethookd_sync.feed_failed",
                    extra={
                        "feed_id": str(feed.id),
                        "error": str(exc),
                    },
                )
                session.rollback()

        # Complete the run
        runs_repo.complete(
            run_id=str(run.id),
            status="completed",
            feeds_attempted=feeds_attempted,
            feeds_succeeded=feeds_succeeded,
            assets_new=assets_new,
            assets_updated=assets_updated,
            assets_marked_stale=assets_marked_stale,
            assets_failed=assets_failed,
            credits_used=credits_used,
        )

        return GetHookdSyncActivityOutput(
            status="completed",
            feeds_attempted=feeds_attempted,
            feeds_succeeded=feeds_succeeded,
            assets_new=assets_new,
            assets_updated=assets_updated,
            assets_marked_stale=assets_marked_stale,
            assets_failed=assets_failed,
            credits_used=credits_used,
        )

    except Exception as exc:
        logger.exception(
            "gethookd_sync_workspace.failed",
            extra={
                "org_id": input.org_id,
                "client_id": input.client_id,
                "error": str(exc),
            },
        )
        return GetHookdSyncActivityOutput(
            status="failed",
            feeds_attempted=0,
            feeds_succeeded=0,
            assets_new=0,
            assets_updated=0,
            assets_marked_stale=0,
            assets_failed=0,
            credits_used=0,
            error_summary=str(exc)[:1000],
        )
    finally:
        session.close()
