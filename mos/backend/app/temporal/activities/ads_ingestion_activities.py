from __future__ import annotations

import os
from collections import Counter
from contextlib import contextmanager
from typing import Any, Dict, List, Optional
from uuid import UUID

from temporalio import activity

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.ads.ingestors.registry import IngestorRegistry
from app.ads.normalization import derive_primary_domain, normalize_facebook_page_url, normalize_url
from app.ads.types import NormalizeContext
from app.db.enums import (
    AdChannelEnum,
    AdStatusEnum,
    ProductBrandRelationshipSourceEnum,
    ProductBrandRelationshipTypeEnum,
)
from app.db.repositories.ads import AdsRepository
from app.db.repositories.jobs import JOB_STATUS_FAILED, JOB_STATUS_RUNNING, JOB_STATUS_QUEUED, JOB_STATUS_SUCCEEDED, JOB_TYPE_ADD_CREATIVE_BREAKDOWN, SUBJECT_TYPE_AD
from app.schemas.ads_ingestion import BrandDiscovery
from app.db.base import SessionLocal
from app.ads.apify_client import ApifyClient
from app.db.models import Ad, AdFacts, AdScore, Brand, Job, ResearchRun, ResearchRunBrand
from app.services.ad_breakdown import extract_teardown_header_fields
from app.services.media_mirror import MediaMirrorService


@contextmanager
def _repo() -> AdsRepository:
    """Provide a short-lived repo with a SessionLocal that is always closed."""
    session = SessionLocal()
    try:
        yield AdsRepository(session)
    finally:
        session.close()


@activity.defn
def upsert_brands_and_identities_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    product_id = params.get("product_id")
    campaign_id = params.get("campaign_id")
    discovery_payload = params.get("brand_discovery") or params.get("brand_discovery_payload") or {}
    if not product_id:
        raise ValueError("product_id is required for ads ingestion.")

    discovery = BrandDiscovery.model_validate(discovery_payload)
    with _repo() as repo:
        run = repo.create_research_run(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            brand_discovery_payload=discovery.model_dump(mode="json"),
        )
        activity.logger.info(
            "ads_ingestion.upsert_brands_and_identities.start",
            extra={"org_id": org_id, "client_id": client_id, "research_run_id": run.id},
        )

        brand_ids: List[str] = []
        identity_ids: List[str] = []

        for brand in discovery.brands:
            brand_row = repo.upsert_brand(
                org_id=org_id,
                canonical_name=brand.name,
                normalized_name=brand.normalized_name,
                primary_website_url=brand.website,
                primary_domain=brand.primary_domain,
            )
            brand_ids.append(brand_row.id)
            repo.add_research_run_brand(research_run_id=run.id, brand_id=brand_row.id, role=brand.role)
            repo.ensure_product_brand_relationship(
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                brand_id=brand_row.id,
                relationship_type=ProductBrandRelationshipTypeEnum.competitor,
                source_type=ProductBrandRelationshipSourceEnum.competitor_discovery,
                source_id=str(run.id),
            )

            for channel, channel_identity in brand.channels.as_dict().items():
                external_url = None
                if channel == AdChannelEnum.META_ADS_LIBRARY:
                    if channel_identity.facebook_page_urls:
                        external_url = channel_identity.facebook_page_urls[0]
                identity_row = repo.upsert_brand_channel_identity(
                    brand_id=brand_row.id,
                    channel=channel,
                    external_id=None,
                    external_url=external_url,
                    metadata=channel_identity.model_dump(mode="json"),
                )
                identity_ids.append(identity_row.id)

        activity.logger.info(
            "ads_ingestion.upsert_brands_and_identities.done",
            extra={
                "research_run_id": run.id,
                "brand_count": len(brand_ids),
                "identity_count": len(identity_ids),
            },
        )
        return {
            "research_run_id": run.id,
            "brand_ids": brand_ids,
            "brand_channel_identity_ids": identity_ids,
        }


@activity.defn
def ingest_ads_for_identities_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    research_run_id = params["research_run_id"]
    identity_ids = params.get("brand_channel_identity_ids")
    results_limit = params.get("results_limit")

    apify_client = ApifyClient()
    registry = IngestorRegistry(apify_client)

    with _repo() as repo:
        run = repo.session.get(ResearchRun, research_run_id)
        if not run:
            raise RuntimeError(f"Research run {research_run_id} not found.")
        if not run.product_id or not run.client_id:
            raise RuntimeError(
                f"Research run {research_run_id} is missing product_id or client_id; "
                "cannot link brands to a product."
            )

        mirror_service = MediaMirrorService(repo.session)
        identities = repo.identities_for_run(research_run_id) if not identity_ids else []
        if identity_ids:
            identity_strs = {str(i) for i in identity_ids}
            identities = [i for i in repo.identities_for_run(research_run_id) if str(i.id) in identity_strs]

        if not identities:
            activity.logger.error(
                "ads_ingestion.ingest.no_identities",
                extra={"research_run_id": research_run_id, "identity_ids": identity_ids},
            )
            raise RuntimeError(f"No brand channel identities found for research run {research_run_id}")

        ingest_runs: List[Dict[str, Any]] = []
        ingested_ad_ids: set[str] = set()
        seen_page_urls: set[str] = set()
        skipped_duplicates: List[Dict[str, Any]] = []
        for identity in identities:
            repo.ensure_product_brand_relationship(
                org_id=str(run.org_id),
                client_id=str(run.client_id),
                product_id=str(run.product_id),
                brand_id=str(identity.brand_id),
                relationship_type=ProductBrandRelationshipTypeEnum.competitor,
                source_type=ProductBrandRelationshipSourceEnum.ads_ingestion,
                source_id=str(run.id),
            )
            ingestor = registry.get(identity.channel)
            requests: List[Any] = []
            try:
                requests = ingestor.build_requests(identity, results_limit=results_limit)
            except Exception as exc:  # noqa: BLE001
                ingest_run = repo.start_ingest_run(
                    research_run_id=research_run_id,
                    brand_channel_identity_id=identity.id,
                    channel=identity.channel,
                    requested_url=None,
                    provider="APIFY",
                    results_limit=results_limit,
                )
                repo.mark_ingest_failure(
                    ingest_run.id,
                    error=f"build_requests_failed: {exc}",
                )
                activity.logger.warning(
                    "ads_ingestion.ingest.requests_missing",
                    extra={
                        "research_run_id": research_run_id,
                        "brand_channel_identity_id": identity.id,
                        "channel": identity.channel.value,
                        "error": str(exc),
                    },
                )
                continue
            deduped_requests: List[Any] = []
            for request in requests:
                page_url = None
                if isinstance(getattr(request, "metadata", None), dict):
                    page_url = request.metadata.get("page_url")
                if not page_url:
                    page_url = getattr(request, "url", None)
                if page_url and page_url in seen_page_urls:
                    skipped_duplicates.append(
                        {
                            "brand_channel_identity_id": identity.id,
                            "page_url": page_url,
                        }
                    )
                    continue
                if page_url:
                    seen_page_urls.add(page_url)
                deduped_requests.append(request)

            requests = deduped_requests
            if not requests:
                ingest_run = repo.start_ingest_run(
                    research_run_id=research_run_id,
                    brand_channel_identity_id=identity.id,
                    channel=identity.channel,
                    requested_url=None,
                    provider="APIFY",
                    results_limit=results_limit,
                )
                repo.mark_ingest_failure(
                    ingest_run.id,
                    error="build_requests_empty",
                )
                activity.logger.warning(
                    "ads_ingestion.ingest.requests_empty",
                    extra={
                        "research_run_id": research_run_id,
                        "brand_channel_identity_id": identity.id,
                        "channel": identity.channel.value,
                    },
                )
                continue
            ingest_run = repo.start_ingest_run(
                research_run_id=research_run_id,
                brand_channel_identity_id=identity.id,
                channel=identity.channel,
                requested_url=requests[0].url if requests else None,
                provider="APIFY",
                results_limit=results_limit,
            )
            items_count = 0
            provider_run_id: Optional[str] = None
            provider_dataset_id: Optional[str] = None
            actor_input: Optional[Dict[str, Any]] = None
            activity.logger.info(
                "ads_ingestion.ingest.start",
                extra={
                    "research_run_id": research_run_id,
                    "brand_channel_identity_id": identity.id,
                    "channel": identity.channel.value,
                },
            )
            try:
                for request in requests:
                    raw_items = ingestor.run(request)
                    for raw in raw_items:
                        meta = raw.metadata or {}
                        provider_run_id = provider_run_id or meta.get("provider_run_id")
                        provider_dataset_id = provider_dataset_id or meta.get("dataset_id")
                        actor_input = actor_input or meta.get("actor_input")
                        ctx = NormalizeContext(
                            brand_id=identity.brand_id,
                            brand_channel_identity_id=identity.id,
                            research_run_id=research_run_id,
                            ingest_run_id=ingest_run.id,
                        )
                        normalized = ingestor.normalize(raw, ctx)
                        if not normalized:
                            continue
                        ad_row, media_assets = repo.upsert_ad_with_assets(
                            brand_id=identity.brand_id,
                            brand_channel_identity_id=identity.id,
                            channel=identity.channel,
                            normalized=normalized,
                        )
                        if media_assets:
                            try:
                                mirror_service.mirror_assets(media_assets)
                            except Exception:
                                repo.session.rollback()
                                raise
                        ingested_ad_ids.add(str(ad_row.id))
                        items_count += 1
                repo.mark_ingest_success(
                    ingest_run.id,
                    items_count=items_count,
                    provider_run_id=provider_run_id,
                    provider_dataset_id=provider_dataset_id,
                    is_partial=bool(results_limit and items_count >= results_limit),
                )
                ingest_runs.append(
                    {
                        "ad_ingest_run_id": ingest_run.id,
                        "brand_channel_identity_id": identity.id,
                        "items_count": items_count,
                        "provider_run_id": provider_run_id,
                        "provider_dataset_id": provider_dataset_id,
                        "requested_url": requests[0].url if requests else None,
                        "actor_input": actor_input,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                repo.session.rollback()
                repo.mark_ingest_failure(ingest_run.id, error=str(exc), provider_run_id=provider_run_id)
                activity.logger.error(
                    "ads_ingestion.ingest.error",
                    extra={
                        "research_run_id": research_run_id,
                        "brand_channel_identity_id": identity.id,
                        "error": str(exc),
                    },
                )
                raise

        total_items = sum(run.get("items_count", 0) for run in ingest_runs)
        status = "ok"
        reason = None
        if total_items == 0:
            status = "empty"
            reason = "no_ads_returned"
            activity.logger.warning(
                "ads_ingestion.ingest.no_ads",
                extra={
                    "research_run_id": research_run_id,
                    "identity_count": len(identities),
                    "skipped_duplicates": len(skipped_duplicates),
                },
            )

        return {
            "ad_ingest_runs": ingest_runs,
            "ad_ids": sorted(ingested_ad_ids),
            "status": status,
            "reason": reason,
            "skipped_duplicates": skipped_duplicates,
        }


@activity.defn
def fetch_ad_library_page_totals_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetch total ads counts per Facebook Page using Apify's maintained actor.

    This is intended for competitor "strength" ranking (active volume) without having
    to scrape full creative payloads.
    """
    research_run_id = params["research_run_id"]
    query_key = str(params.get("query_key") or os.getenv("ADS_META_TOTALS_QUERY_KEY", "meta_active_total"))
    active_status = str(params.get("active_status") or os.getenv("ADS_META_TOTALS_ACTIVE_STATUS", "active"))

    results_limit_raw = params.get("results_limit") or os.getenv("ADS_META_TOTALS_RESULTS_LIMIT", "1")
    try:
        results_limit = int(results_limit_raw)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"results_limit must be an int, got {results_limit_raw!r}") from exc

    include_about_page_raw = params.get("include_about_page")
    if include_about_page_raw is None:
        include_about_page_raw = os.getenv("ADS_META_TOTALS_INCLUDE_ABOUT_PAGE", "true")
    include_about_page = str(include_about_page_raw).strip().lower() in {"1", "true", "yes", "y"}

    actor_id = os.getenv("APIFY_META_TOTALS_ACTOR_ID", "apify~facebook-ads-scraper")
    max_wait_raw = os.getenv("ADS_META_TOTALS_MAX_WAIT_SECONDS", "900")
    try:
        max_wait_seconds = int(max_wait_raw)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"ADS_META_TOTALS_MAX_WAIT_SECONDS must be an int, got {max_wait_raw!r}") from exc

    identity_ids = params.get("brand_channel_identity_ids")

    apify = ApifyClient()
    with _repo() as repo:
        run = repo.session.get(ResearchRun, research_run_id)
        if not run:
            raise RuntimeError(f"Research run {research_run_id} not found.")

        identities = repo.identities_for_run(research_run_id)
        if identity_ids:
            identity_strs = {str(i) for i in identity_ids}
            identities = [i for i in identities if str(i.id) in identity_strs]
            if not identities:
                raise RuntimeError(
                    f"No brand channel identities matched for research run {research_run_id}; "
                    f"identity_ids={sorted(identity_strs)}"
                )

        url_to_identities: dict[str, list[Any]] = {}
        for identity in identities:
            candidate_urls: list[str] = []
            if identity.external_url:
                candidate_urls.append(identity.external_url)
            metadata = getattr(identity, "metadata_json", None) or {}
            if isinstance(metadata, dict):
                for u in metadata.get("facebook_page_urls") or []:
                    if isinstance(u, str) and u.strip():
                        candidate_urls.append(u)
            canonical = None
            for u in candidate_urls:
                canonical = normalize_facebook_page_url(u)
                if canonical:
                    break
            if not canonical:
                raise RuntimeError(
                    "Cannot fetch totals: identity is missing a valid Facebook Page URL "
                    f"(brand_channel_identity_id={identity.id})"
                )
            url_to_identities.setdefault(canonical, []).append(identity)

        start_urls = [{"url": u, "method": "GET"} for u in sorted(url_to_identities.keys())]
        if not start_urls:
            raise RuntimeError(f"No Facebook Page URLs found for research run {research_run_id}.")

        actor_input: Dict[str, Any] = {
            "startUrls": start_urls,
            "onlyTotal": True,
            "includeAboutPage": include_about_page,
            "isDetailsPerAd": True,
            "resultsLimit": results_limit,
            "activeStatus": active_status,
        }

        activity.logger.info(
            "ads_ingestion.totals.start",
            extra={
                "research_run_id": research_run_id,
                "query_key": query_key,
                "active_status": active_status,
                "page_count": len(start_urls),
                "actor_id": actor_id,
            },
        )

        run_data = apify.start_actor_run(actor_id, input_payload=actor_input)
        provider_run_id = run_data.get("id") or run_data.get("runId")
        if not provider_run_id:
            raise RuntimeError(f"Apify actor run did not return an id (actor_id={actor_id}).")

        final = apify.poll_run_until_terminal(provider_run_id, max_wait_seconds=max_wait_seconds)
        dataset_id = final.get("defaultDatasetId")
        if not dataset_id:
            raise RuntimeError(
                f"Apify actor run missing defaultDatasetId (actor_id={actor_id}, run_id={provider_run_id})."
            )

        items = apify.fetch_dataset_items(dataset_id, limit=len(start_urls))
        if not items:
            raise RuntimeError(
                f"Apify dataset returned no items (actor_id={actor_id}, run_id={provider_run_id}, dataset_id={dataset_id})."
            )

        totals_by_url: dict[str, dict[str, Any]] = {}
        for item in items:
            raw_url = item.get("inputUrl") or item.get("facebookUrl") or item.get("url")
            canonical_url = normalize_facebook_page_url(raw_url) if isinstance(raw_url, str) else None
            if not canonical_url:
                raise RuntimeError(
                    "Apify totals item missing inputUrl/facebookUrl; cannot map totals to identities. "
                    f"keys={sorted(list(item.keys()))}"
                )

            results = item.get("results")
            if not isinstance(results, list) or not results:
                raise RuntimeError(
                    f"Apify totals item missing results[] for url={canonical_url}. "
                    f"keys={sorted(list(item.keys()))}"
                )
            first = results[0] if isinstance(results[0], dict) else None
            if not isinstance(first, dict) or "totalCount" not in first:
                raise RuntimeError(
                    f"Apify totals item missing results[0].totalCount for url={canonical_url}. "
                    f"first_keys={sorted(list(first.keys())) if isinstance(first, dict) else None}"
                )
            total_raw = first.get("totalCount")
            try:
                total_count = int(total_raw)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"Apify totals item has non-int totalCount for url={canonical_url}: {total_raw!r}"
                ) from exc

            page_id = first.get("pageID")
            page_id_str = str(page_id) if page_id is not None else None

            page_name = None
            page_info = item.get("pageInfo")
            if isinstance(page_info, dict):
                adlib = page_info.get("adLibraryPageInfo")
                if isinstance(adlib, dict):
                    pinfo = adlib.get("pageInfo")
                    if isinstance(pinfo, dict):
                        name = pinfo.get("name")
                        if isinstance(name, str) and name.strip():
                            page_name = name.strip()

            totals_by_url[canonical_url] = {
                "input_url": canonical_url,
                "total_count": total_count,
                "page_id": page_id_str,
                "page_name": page_name,
                "raw_result": item,
            }

        missing_urls = [u for u in url_to_identities.keys() if u not in totals_by_url]
        if missing_urls:
            raise RuntimeError(
                "Apify totals did not return results for all requested pages. "
                f"missing={missing_urls}"
            )

        stored: list[dict[str, Any]] = []
        for url, identities_for_url in url_to_identities.items():
            result = totals_by_url[url]
            for identity in identities_for_url:
                row = repo.upsert_ad_library_page_total(
                    org_id=str(run.org_id),
                    research_run_id=research_run_id,
                    brand_id=str(identity.brand_id),
                    brand_channel_identity_id=str(identity.id),
                    channel=identity.channel,
                    query_key=query_key,
                    active_status=active_status,
                    input_url=result["input_url"],
                    total_count=result["total_count"],
                    page_id=result["page_id"],
                    page_name=result["page_name"],
                    provider="APIFY",
                    provider_actor_id=actor_id,
                    provider_run_id=provider_run_id,
                    provider_dataset_id=dataset_id,
                    actor_input=actor_input,
                    raw_result=result.get("raw_result"),
                )
                stored.append(
                    {
                        "ad_library_page_total_id": str(row.id),
                        "brand_channel_identity_id": str(identity.id),
                        "brand_id": str(identity.brand_id),
                        "input_url": result["input_url"],
                        "total_count": result["total_count"],
                        "page_id": result["page_id"],
                        "page_name": result["page_name"],
                    }
                )

        activity.logger.info(
            "ads_ingestion.totals.done",
            extra={
                "research_run_id": research_run_id,
                "query_key": query_key,
                "active_status": active_status,
                "stored_count": len(stored),
                "actor_id": actor_id,
                "provider_run_id": provider_run_id,
                "provider_dataset_id": dataset_id,
            },
        )
        return {
            "research_run_id": research_run_id,
            "query_key": query_key,
            "active_status": active_status,
            "provider_run_id": provider_run_id,
            "provider_dataset_id": dataset_id,
            "stored": stored,
        }


@activity.defn
def select_ads_for_context_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Select a small, high-signal subset of ads for downstream ads_context and creative breakdowns.

    The intent is to bias toward "winning" ads:
    - active
    - running >= N days
    - image/video formats
    - (optionally) preferred language codes
    """

    def _parse_bool(value: Any, *, name: str) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        if text in {"1", "true", "yes", "y"}:
            return True
        if text in {"0", "false", "no", "n", ""}:
            return False
        raise ValueError(f"{name} must be a bool-like value, got {value!r}")

    def _parse_int(value: Any, *, name: str) -> int:
        try:
            return int(value)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"{name} must be an int, got {value!r}") from exc

    def _parse_csv(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            return [str(v).strip() for v in value if str(v).strip()]
        text = str(value or "").strip()
        if not text:
            return []
        return [part.strip() for part in text.split(",") if part.strip()]

    research_run_id = params["research_run_id"]
    totals_query_key = str(
        params.get("totals_query_key") or os.getenv("ADS_META_TOTALS_QUERY_KEY", "meta_active_total")
    )

    max_total_ads = _parse_int(
        params.get("max_total_ads") or os.getenv("ADS_CONTEXT_SELECT_MAX_TOTAL_ADS", "40"),
        name="max_total_ads",
    )
    if max_total_ads <= 0:
        raise ValueError(f"max_total_ads must be > 0, got {max_total_ads}")

    max_ads_per_brand = _parse_int(
        params.get("max_ads_per_brand")
        or os.getenv("ADS_CONTEXT_SELECT_MAX_ADS_PER_BRAND")
        or os.getenv("ADS_CONTEXT_MAX_ADS_PER_BRAND", "3"),
        name="max_ads_per_brand",
    )
    if max_ads_per_brand <= 0:
        raise ValueError(f"max_ads_per_brand must be > 0, got {max_ads_per_brand}")

    max_brands = _parse_int(
        params.get("max_brands") or os.getenv("ADS_CONTEXT_SELECT_MAX_BRANDS", "25"),
        name="max_brands",
    )
    if max_brands <= 0:
        raise ValueError(f"max_brands must be > 0, got {max_brands}")

    active_only = _parse_bool(
        params.get("active_only") or os.getenv("ADS_CONTEXT_SELECT_ACTIVE_ONLY", "true"),
        name="active_only",
    )
    min_days_active = _parse_int(
        params.get("min_days_active") or os.getenv("ADS_CONTEXT_SELECT_MIN_DAYS_ACTIVE", "7"),
        name="min_days_active",
    )
    if min_days_active < 0:
        raise ValueError(f"min_days_active must be >= 0, got {min_days_active}")

    allowed_formats = [f.lower() for f in _parse_csv(os.getenv("ADS_CONTEXT_SELECT_DISPLAY_FORMATS", "image,video"))]
    allowed_formats = [f for f in allowed_formats if f]
    if not allowed_formats:
        raise ValueError("ADS_CONTEXT_SELECT_DISPLAY_FORMATS must include at least one format")

    preferred_language_codes = [c.upper() for c in _parse_csv(os.getenv("ADS_CONTEXT_SELECT_LANGUAGE_CODES", "EN"))]
    language_strict = _parse_bool(
        os.getenv("ADS_CONTEXT_SELECT_LANGUAGE_STRICT", "false"),
        name="ADS_CONTEXT_SELECT_LANGUAGE_STRICT",
    )

    with _repo() as repo:
        totals_rows = repo.ad_library_page_totals_for_run(
            research_run_id=research_run_id,
            query_key=totals_query_key,
        )
        if not totals_rows:
            raise RuntimeError(
                "No ad library totals found for research run; cannot rank competitors. "
                f"research_run_id={research_run_id} totals_query_key={totals_query_key}"
            )

        totals_by_brand = Counter()
        for row in totals_rows:
            totals_by_brand[row.brand_id] += int(getattr(row, "total_count", 0) or 0)

        brand_order = [brand_id for brand_id, _ in totals_by_brand.most_common()]
        if not brand_order:
            raise RuntimeError(
                "Ad library totals returned no brands; cannot select ads. "
                f"research_run_id={research_run_id} totals_query_key={totals_query_key}"
            )
        brand_order = brand_order[:max_brands]

        stmt = (
            select(
                Ad.id,
                Ad.brand_id,
                Ad.last_seen_at,
                AdFacts.days_active,
                AdFacts.display_format,
                AdFacts.language_codes,
                AdScore.performance_score,
            )
            .join(ResearchRunBrand, ResearchRunBrand.brand_id == Ad.brand_id)
            .join(AdFacts, AdFacts.ad_id == Ad.id)
            .outerjoin(AdScore, AdScore.ad_id == Ad.id)
            .where(ResearchRunBrand.research_run_id == research_run_id)
            .where(Ad.brand_id.in_(brand_order))
        )
        if active_only:
            stmt = stmt.where(AdFacts.status == AdStatusEnum.active)
        if min_days_active:
            stmt = stmt.where(AdFacts.days_active.isnot(None), AdFacts.days_active >= min_days_active)
        if allowed_formats:
            stmt = stmt.where(AdFacts.display_format.isnot(None), AdFacts.display_format.in_(allowed_formats))
        if language_strict and preferred_language_codes:
            stmt = stmt.where(AdFacts.language_codes.overlap(preferred_language_codes))

        rows = list(repo.session.execute(stmt).all())
        if not rows:
            raise RuntimeError(
                "No ads matched selection filters for research run. "
                f"research_run_id={research_run_id} active_only={active_only} "
                f"min_days_active={min_days_active} allowed_formats={allowed_formats} "
                f"language_strict={language_strict} preferred_language_codes={preferred_language_codes}"
            )

        candidates_by_brand: dict[Any, list[dict[str, Any]]] = {}
        for ad_id, brand_id, last_seen_at, days_active, display_format, language_codes, performance_score in rows:
            languages = language_codes or []
            language_match = (
                bool(preferred_language_codes)
                and any(code in languages for code in preferred_language_codes)
            )
            candidates_by_brand.setdefault(brand_id, []).append(
                {
                    "ad_id": str(ad_id),
                    "brand_id": str(brand_id),
                    "language_match": language_match,
                    "days_active": int(days_active or 0),
                    "performance_score": int(performance_score or 0),
                    "last_seen_at": last_seen_at,
                    "display_format": display_format,
                }
            )

        def _sort_key(c: dict[str, Any]) -> tuple:
            # Prefer language match first, then longer-running, then generic performance score.
            # last_seen_at acts as a stable tie-breaker for similarly "good" ads.
            last_seen = c.get("last_seen_at")
            last_seen_ord = last_seen.timestamp() if last_seen else 0
            return (
                1 if c.get("language_match") else 0,
                int(c.get("days_active") or 0),
                int(c.get("performance_score") or 0),
                last_seen_ord,
            )

        selected_ad_ids: list[str] = []
        selected_by_brand: dict[str, int] = {}
        for brand_id in brand_order:
            candidates = candidates_by_brand.get(brand_id) or []
            if not candidates:
                continue
            candidates = sorted(candidates, key=_sort_key, reverse=True)
            remaining = max_total_ads - len(selected_ad_ids)
            if remaining <= 0:
                break
            take = min(max_ads_per_brand, remaining)
            chosen = candidates[:take]
            if not chosen:
                continue
            selected_ad_ids.extend([c["ad_id"] for c in chosen])
            selected_by_brand[str(brand_id)] = len(chosen)

        if not selected_ad_ids:
            raise RuntimeError(
                "Selection produced zero ads after ranking. "
                f"research_run_id={research_run_id} brand_count={len(brand_order)}"
            )

        return {
            "research_run_id": research_run_id,
            "ad_ids": selected_ad_ids,
            "selection": {
                "active_only": active_only,
                "min_days_active": min_days_active,
                "allowed_formats": allowed_formats,
                "preferred_language_codes": preferred_language_codes,
                "language_strict": language_strict,
                "max_total_ads": max_total_ads,
                "max_ads_per_brand": max_ads_per_brand,
                "max_brands": max_brands,
                "totals_query_key": totals_query_key,
                "selected_count": len(selected_ad_ids),
                "selected_by_brand": selected_by_brand,
            },
        }


@activity.defn
def build_ads_context_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    research_run_id = params["research_run_id"]
    max_media_assets = int(os.getenv("ADS_CONTEXT_MAX_MEDIA_ASSETS", "2"))
    max_breakdown_ads = int(os.getenv("ADS_CONTEXT_MAX_BREAKDOWN_ADS", "8"))
    max_highlight_ads = int(os.getenv("ADS_CONTEXT_MAX_HIGHLIGHT_ADS", "5"))
    max_ads_per_brand = int(os.getenv("ADS_CONTEXT_MAX_ADS_PER_BRAND", "3"))
    max_primary_text = int(os.getenv("ADS_CONTEXT_PRIMARY_TEXT_LIMIT", "320"))
    max_headline = int(os.getenv("ADS_CONTEXT_HEADLINE_LIMIT", "160"))
    fallback_context: Dict[str, Any] = {
        "ads_context": {
            "brands": [],
            "cross_brand": {"top_destination_domains": [], "cta_distribution": []},
            "warning": "ads_context generation failed; continuing without ads context",
        }
    }

    def _truncate_text(text: Optional[str], max_chars: int) -> Optional[str]:
        if not text:
            return None
        if max_chars <= 0:
            return None
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip()

    with _repo() as repo:
        def _serialize_media(ad_id: str) -> list[Dict[str, Any]]:
            _, media_rows = repo.ad_with_media(ad_id)
            assets: list[Dict[str, Any]] = []
            for media, role in media_rows:
                metadata = getattr(media, "metadata_json", {}) or {}
                asset_type = getattr(media, "asset_type", None)
                asset_type_value = getattr(asset_type, "value", None) if asset_type is not None else None
                assets.append(
                    {
                        "role": role,
                        "asset_type": asset_type_value or str(asset_type) if asset_type else None,
                        "source_url": getattr(media, "source_url", None) or getattr(media, "stored_url", None),
                        "thumbnail_url": metadata.get("thumbnail_url") or metadata.get("preview_url"),
                    }
                )
                if len(assets) >= max_media_assets:
                    break
            return assets

        session = repo.session
        try:
            ad_ids = params.get("ad_ids")
            if ad_ids:
                ad_ids_set: set[UUID] = set()
                ad_id_order: list[str] = []
                invalid_ids: list[Any] = []
                for aid in ad_ids:
                    try:
                        parsed = UUID(str(aid))
                        ad_ids_set.add(parsed)
                        ad_id_order.append(str(parsed))
                    except Exception:  # noqa: BLE001
                        invalid_ids.append(aid)
                if invalid_ids:
                    raise ValueError(f"Invalid ad_ids passed to build_ads_context_activity: {invalid_ids}")
                ads = list(
                    session.scalars(
                        select(Ad)
                        .where(Ad.id.in_(ad_ids_set))
                    ).all()
                )
                if ad_id_order:
                    order_map = {ad_id: idx for idx, ad_id in enumerate(ad_id_order)}
                    ads.sort(key=lambda ad: order_map.get(str(ad.id), len(order_map)))
            else:
                ads = repo.ads_for_run(research_run_id)

            if not ads:
                activity.logger.error(
                    "ads_ingestion.build_ads_context.no_ads",
                    extra={"research_run_id": research_run_id},
                )
                return fallback_context

            activity.logger.info(
                "ads_ingestion.build_ads_context.start",
                extra={"research_run_id": research_run_id, "ad_count": len(ads)},
            )
            run_brand_rows = list(
                session.query(ResearchRunBrand).filter(ResearchRunBrand.research_run_id == research_run_id).all()
            )
            run_brand_ids = [row.brand_id for row in run_brand_rows]
            ad_brand_ids = [ad.brand_id for ad in ads]
            brand_ids = set(run_brand_ids + ad_brand_ids)
            brand_lookup: Dict[str, Brand] = {}
            if brand_ids:
                brand_lookup = {brand.id: brand for brand in session.query(Brand).filter(Brand.id.in_(brand_ids)).all()}

            totals_query_key = os.getenv("ADS_META_TOTALS_QUERY_KEY", "meta_active_total")
            totals_rows = repo.ad_library_page_totals_for_run(
                research_run_id=research_run_id,
                query_key=totals_query_key,
            )
            totals_by_brand = Counter()
            if totals_rows:
                for row in totals_rows:
                    totals_by_brand[str(row.brand_id)] += int(getattr(row, "total_count", 0) or 0)

            per_brand: Dict[str, Dict[str, Any]] = {}
            cross_domains = Counter()
            cross_cta = Counter()

            def _summarize_ad(ad: Ad) -> Dict[str, Any]:
                brand_name = brand_lookup.get(ad.brand_id).canonical_name if ad.brand_id in brand_lookup else None
                return {
                    "brand": brand_name,
                    "brand_name": brand_name,
                    "channel": getattr(ad.channel, "value", str(ad.channel)),
                    "ad_status": getattr(ad.ad_status, "value", str(ad.ad_status)),
                    "cta_type": ad.cta_type,
                    "cta_text": ad.cta_text,
                    "headline": _truncate_text(ad.headline, max_headline),
                    "primary_text": _truncate_text(ad.body_text, max_primary_text),
                    "destination_domain": ad.destination_domain or derive_primary_domain(normalize_url(ad.landing_url)),
                    "landing_url": ad.landing_url,
                }

            for ad in ads:
                brand_stats = per_brand.setdefault(
                    ad.brand_id,
                    {
                        "brand_id": str(ad.brand_id),
                        "brand_name": brand_lookup.get(ad.brand_id).canonical_name if ad.brand_id in brand_lookup else None,
                        "ad_count": 0,
                        "active_count": 0,
                        "destination_domains": Counter(),
                        "cta_types": Counter(),
                        "ad_briefs": [],
                    },
                )
                brand_stats["ad_count"] += 1
                if getattr(ad, "ad_status", None) and getattr(ad.ad_status, "value", "") == "active":
                    brand_stats["active_count"] += 1
                domain = ad.destination_domain or derive_primary_domain(normalize_url(ad.landing_url))
                if domain:
                    brand_stats["destination_domains"][domain] += 1
                    cross_domains[domain] += 1
                if ad.cta_type:
                    brand_stats["cta_types"][ad.cta_type] += 1
                    cross_cta[ad.cta_type] += 1
                brand_stats["ad_briefs"].append(_summarize_ad(ad))

            context = {
                "brands": [],
                "cross_brand": {
                    "top_destination_domains": cross_domains.most_common(5),
                    "cta_distribution": cross_cta.most_common(5),
                },
            }
            selection_meta = params.get("selection")
            if ad_ids:
                # Document the intent behind passing explicit ad_ids; selection is performed upstream.
                context["selection"] = {
                    "ad_ids_provided": True,
                    "selected_ads": len(ads),
                }
                if isinstance(selection_meta, dict):
                    context["selection"].update(selection_meta)
            for stats in per_brand.values():
                brand_entry: Dict[str, Any] = {
                    "brand_id": stats["brand_id"],
                    "brand_name": stats.get("brand_name"),
                    "ad_count": stats["ad_count"],
                    "active_share": (stats["active_count"] / stats["ad_count"]) if stats["ad_count"] else 0,
                    "top_destination_domains": stats["destination_domains"].most_common(5),
                    "top_cta_types": stats["cta_types"].most_common(5),
                }
                if totals_rows:
                    brand_entry["ad_library_active_ads_total"] = totals_by_brand.get(stats["brand_id"], 0)
                ad_briefs = stats.get("ad_briefs") or []
                if ad_briefs:
                    brand_entry["top_ads"] = ad_briefs[:max_ads_per_brand]
                context["brands"].append(brand_entry)

            # Include brands that were discovered for this research run even if no ads were ingested.
            if run_brand_ids:
                seen_brand_ids = {str(brand_id) for brand_id in per_brand.keys()}
                for brand_id in run_brand_ids:
                    brand_id_str = str(brand_id)
                    if brand_id_str in seen_brand_ids:
                        continue
                    brand_row = brand_lookup.get(brand_id)
                    context["brands"].append(
                        {
                            "brand_id": brand_id_str,
                            "brand_name": brand_row.canonical_name if brand_row else None,
                            "ad_count": 0,
                            "active_share": 0,
                            "top_destination_domains": [],
                            "top_cta_types": [],
                            "representative_ad_ids": [],
                        }
                    )
            if totals_rows:
                for brand_entry in context["brands"]:
                    if "ad_library_active_ads_total" not in brand_entry:
                        brand_entry["ad_library_active_ads_total"] = totals_by_brand.get(
                            str(brand_entry.get("brand_id") or ""), 0
                        )
                context["brands"] = sorted(
                    context["brands"],
                    key=lambda b: (
                        int(b.get("ad_library_active_ads_total") or 0),
                        int(b.get("ad_count") or 0),
                    ),
                    reverse=True,
                )

            def _section_by_prefix(sections: Dict[str, str], prefix: str) -> Optional[str]:
                for key, value in sections.items():
                    if key.startswith(prefix):
                        return value or None
                return None

            # Attach creative breakdown summaries (if available).
            breakdown_items: List[Dict[str, Any]] = []
            breakdown_status_counts = Counter()

            run = session.get(ResearchRun, research_run_id)
            org_id = getattr(run, "org_id", None) if run else None

            ad_id_values = [ad.id for ad in ads]
            jobs_stmt = (
                select(Job)
                .where(
                    Job.job_type == JOB_TYPE_ADD_CREATIVE_BREAKDOWN,
                    Job.subject_type == SUBJECT_TYPE_AD,
                    Job.subject_id.in_(ad_id_values),
                )
                .order_by(Job.updated_at.desc())
            )
            if org_id:
                jobs_stmt = jobs_stmt.where(Job.org_id == org_id)

            jobs = list(session.scalars(jobs_stmt).all())
            job_by_ad_id: Dict[str, Job] = {}
            for job in jobs:
                subject_id = str(getattr(job, "subject_id", ""))
                if subject_id and subject_id not in job_by_ad_id:
                    job_by_ad_id[subject_id] = job

            for ad in ads:
                ad_id = str(ad.id)
                job = job_by_ad_id.get(ad_id)
                media_assets = _serialize_media(ad_id)
                if not job:
                    breakdown_status_counts["missing"] += 1
                    breakdown_items.append(
                        {
                            "brand": brand_lookup.get(ad.brand_id).canonical_name if ad.brand_id in brand_lookup else None,
                            "brand_name": brand_lookup.get(ad.brand_id).canonical_name if ad.brand_id in brand_lookup else None,
                            "channel": getattr(ad.channel, "value", str(ad.channel)),
                            "ad_status": getattr(ad.ad_status, "value", str(ad.ad_status)),
                            "destination_domain": ad.destination_domain
                            or derive_primary_domain(normalize_url(ad.landing_url)),
                            "breakdown": {"status": "missing"},
                            "media_assets": media_assets,
                        }
                    )
                    continue

                status = str(getattr(job, "status", "") or "unknown")
                breakdown_status_counts[status] += 1
                output = getattr(job, "output", None) or {}
                input_payload = getattr(job, "input", None) or {}
                model = output.get("model") or input_payload.get("model")
                prompt_sha = output.get("prompt_sha256") or input_payload.get("prompt_sha256")

                breakdown: Dict[str, Any] = {
                    "status": status,
                    "model": model,
                    "prompt_sha256": prompt_sha,
                }
                if status == JOB_STATUS_FAILED:
                    breakdown["error"] = getattr(job, "error", None)

                parsed = output.get("parsed") if isinstance(output, dict) else None
                sections = None
                if isinstance(parsed, dict):
                    maybe_sections = parsed.get("sections")
                    if isinstance(maybe_sections, dict):
                        sections = {str(k): str(v) for k, v in maybe_sections.items()}

                if status == JOB_STATUS_SUCCEEDED and sections:
                    header_fields = extract_teardown_header_fields(sections)
                    breakdown.update(
                        {
                            "one_liner": header_fields.get("one_liner"),
                            "algorithmic_thesis": header_fields.get("algorithmic_thesis"),
                            "hook_score": header_fields.get("hook_score"),
                        }
                    )

                breakdown_items.append(
                    {
                        "brand": brand_lookup.get(ad.brand_id).canonical_name if ad.brand_id in brand_lookup else None,
                        "brand_name": brand_lookup.get(ad.brand_id).canonical_name if ad.brand_id in brand_lookup else None,
                        "channel": getattr(ad.channel, "value", str(ad.channel)),
                        "ad_status": getattr(ad.ad_status, "value", str(ad.ad_status)),
                        "primary_text": _truncate_text(ad.body_text, max_primary_text),
                        "headline": _truncate_text(ad.headline, max_headline),
                        "cta_type": ad.cta_type,
                        "cta_text": ad.cta_text,
                        "landing_url": ad.landing_url,
                        "destination_domain": ad.destination_domain or derive_primary_domain(normalize_url(ad.landing_url)),
                        "breakdown": breakdown,
                        "media_assets": media_assets,
                    }
                )

            # Prefer explicit keys for known statuses even if missing from Counter.
            context["creative_breakdowns"] = {
                "summary": {
                    "total_ads": len(ads),
                    "missing": int(breakdown_status_counts.get("missing", 0)),
                    JOB_STATUS_QUEUED: int(breakdown_status_counts.get(JOB_STATUS_QUEUED, 0)),
                    JOB_STATUS_RUNNING: int(breakdown_status_counts.get(JOB_STATUS_RUNNING, 0)),
                    JOB_STATUS_SUCCEEDED: int(breakdown_status_counts.get(JOB_STATUS_SUCCEEDED, 0)),
                    JOB_STATUS_FAILED: int(breakdown_status_counts.get(JOB_STATUS_FAILED, 0)),
                },
                "ads": breakdown_items,
            }
            if max_breakdown_ads and len(breakdown_items) > max_breakdown_ads:
                context["creative_breakdowns"]["ads"] = breakdown_items[:max_breakdown_ads]
                context["creative_breakdowns"]["truncated"] = True
                context["creative_breakdowns"]["returned_ads"] = len(context["creative_breakdowns"]["ads"])
            else:
                context["creative_breakdowns"]["returned_ads"] = len(breakdown_items)

            # Compact, LLM-friendly highlight ads (global top-N by recency)
            highlight_ads: List[Dict[str, Any]] = []
            for ad in ads:
                highlight_ads.append(_summarize_ad(ad))
                if len(highlight_ads) >= max_highlight_ads:
                    break
            context["highlight_ads"] = highlight_ads

            # Persist the exact context we return (and pass upstream) for traceability.
            repo.update_ads_context(research_run_id, context)
            activity.logger.info(
                "ads_ingestion.build_ads_context.done",
                extra={"research_run_id": research_run_id, "brand_count": len(per_brand)},
            )
            return {"ads_context": context, "ad_count": len(ads)}
        except SQLAlchemyError as exc:
            activity.logger.error(
                "ads_ingestion.build_ads_context.error",
                extra={"research_run_id": research_run_id, "error": str(exc)},
            )
            return fallback_context


@activity.defn
def list_ads_for_run_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    research_run_id = params["research_run_id"]
    with _repo() as repo:
        ads = repo.ads_for_run(research_run_id)
        ad_ids = [str(ad.id) for ad in ads]
        activity.logger.info(
            "ads_ingestion.list_ads_for_run",
            extra={"research_run_id": research_run_id, "ad_count": len(ad_ids)},
        )
        return {"ad_ids": ad_ids}
