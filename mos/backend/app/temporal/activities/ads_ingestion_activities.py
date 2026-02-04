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
from app.ads.normalization import derive_primary_domain, normalize_url
from app.ads.types import NormalizeContext
from app.db.enums import (
    AdChannelEnum,
    ProductBrandRelationshipSourceEnum,
    ProductBrandRelationshipTypeEnum,
)
from app.db.repositories.ads import AdsRepository
from app.db.repositories.jobs import JOB_STATUS_FAILED, JOB_STATUS_RUNNING, JOB_STATUS_QUEUED, JOB_STATUS_SUCCEEDED, JOB_TYPE_ADD_CREATIVE_BREAKDOWN, SUBJECT_TYPE_AD
from app.schemas.ads_ingestion import BrandDiscovery
from app.db.base import SessionLocal
from app.ads.apify_client import ApifyClient
from app.db.models import Ad, Brand, Job, ResearchRun, ResearchRunBrand
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
                for aid in ad_ids:
                    try:
                        ad_ids_set.add(UUID(str(aid)))
                    except Exception:  # noqa: BLE001
                        continue
                ads = list(
                    session.scalars(
                        select(Ad)
                        .where(Ad.id.in_(ad_ids_set))
                        .order_by(Ad.last_seen_at.desc().nullslast(), Ad.created_at.desc())
                    ).all()
                )
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
            for stats in per_brand.values():
                brand_entry: Dict[str, Any] = {
                    "brand_id": stats["brand_id"],
                    "brand_name": stats.get("brand_name"),
                    "ad_count": stats["ad_count"],
                    "active_share": (stats["active_count"] / stats["ad_count"]) if stats["ad_count"] else 0,
                    "top_destination_domains": stats["destination_domains"].most_common(5),
                    "top_cta_types": stats["cta_types"].most_common(5),
                }
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
