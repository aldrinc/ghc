from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import CampaignDeliveryModeEnum, FunnelEventTypeEnum
from app.db.models import Campaign, Funnel, FunnelEvent, FunnelPage, MetaPublishRun, ProductVariant
from app.db.repositories.campaign_delivery_configs import CampaignDeliveryConfigsRepository
from app.db.repositories.paid_ads_qa import PaidAdsQaRepository
from app.services.funnel_template_categories import resolve_funnel_template_category

_LAST_N_DAYS_PRESET = re.compile(r"^last_(\d+)d$")
_BENCHMARKS_METADATA_KEY = "metaManagementBenchmarks"


class MetaManagementBenchmarkError(RuntimeError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class MetaOneSidedBenchmark(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum: float
    good: float | None = None


class MetaTargetBenchmark(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: float


class MetaAtcPriceBandBenchmark(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    minPrice: float | None = None
    maxPrice: float | None = None
    target: float


class MetaManagementBenchmarkProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    adLinkCtrPct: MetaOneSidedBenchmark
    presellCtrPct: MetaTargetBenchmark
    salesPdpPurchaseCvrPct: MetaOneSidedBenchmark
    checkoutCvrPct: MetaTargetBenchmark
    salesPdpAtcPctPriceBands: list[MetaAtcPriceBandBenchmark] = Field(default_factory=list)


class MetaBenchmarkContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clientId: str
    campaignId: str
    metaCampaignId: str
    datePreset: str
    funnelId: str
    publicationId: str
    deliveryMode: str
    profileId: str
    priceCents: int | None = None
    priceDollars: float | None = None
    atcPriceBandId: str | None = None
    atcPriceBandLabel: str | None = None
    priceResolutionError: str | None = None
    profileUpdatedAt: str | None = None


class MetaFunnelMetricsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    startedAt: str
    endedAt: str
    presellPageId: str | None = None
    salesPageId: str
    presellPageViewSessions: int = 0
    presellCtaClickSessions: int = 0
    salesPageViewSessions: int = 0
    checkoutStartedSessions: int = 0
    orderCompletedSessions: int = 0
    presellCtrPct: float | None = None
    salesPdpAtcPct: float | None = None
    salesPdpPurchaseCvrPct: float | None = None
    checkoutCvrPct: float | None = None


class MetaBenchmarkEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metricId: str
    label: str
    scope: str
    status: str
    value: float | None = None
    unit: str
    minimum: float | None = None
    target: float | None = None
    good: float | None = None
    numerator: int | None = None
    denominator: int | None = None
    reason: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class _ResolvedBenchmarkContext:
    profile_id: str
    profile_updated_at: str | None
    delivery_mode: CampaignDeliveryModeEnum
    funnel: Funnel
    sales_page: FunnelPage
    presell_page: FunnelPage | None
    publication_id: str
    price_cents: int | None
    price_resolution_error: str | None


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _coerce_session_key(event: FunnelEvent) -> str | None:
    raw = getattr(event, "session_id", None)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _count_unique_sessions(
    *,
    events: list[FunnelEvent],
    page_id: str | None,
    event_type: FunnelEventTypeEnum,
) -> int:
    seen: set[str] = set()
    for event in events:
        if event.event_type != event_type:
            continue
        if page_id is not None and str(event.page_id) != page_id:
            continue
        session_key = _coerce_session_key(event)
        if session_key:
            seen.add(session_key)
    return len(seen)


def _count_unique_sessions_for_event_types(
    *,
    events: list[FunnelEvent],
    page_id: str | None,
    event_types: tuple[FunnelEventTypeEnum, ...],
) -> int:
    seen: set[str] = set()
    for event in events:
        if event.event_type not in event_types:
            continue
        if page_id is not None and str(event.page_id) != page_id:
            continue
        session_key = _coerce_session_key(event)
        if session_key:
            seen.add(session_key)
    return len(seen)


def _ratio_pct(*, numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return (numerator / denominator) * 100.0


def _resolve_window(date_preset: str) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    cleaned = date_preset.strip().lower()
    if cleaned == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if cleaned == "yesterday":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return end - timedelta(days=1), end
    match = _LAST_N_DAYS_PRESET.match(cleaned)
    if match:
        days = int(match.group(1))
        if days <= 0:
            raise MetaManagementBenchmarkError(
                f"Unsupported date preset for benchmark evaluation: {date_preset}",
                code="unsupported_date_preset",
            )
        return now - timedelta(days=days), now
    raise MetaManagementBenchmarkError(
        "Benchmark evaluation only supports day-based Meta presets like today, yesterday, or last_3d.",
        code="unsupported_date_preset",
    )


def parse_meta_management_benchmark_profile(metadata: Mapping[str, Any] | None) -> MetaManagementBenchmarkProfile:
    metadata_map = dict(metadata or {})
    raw_profile = metadata_map.get(_BENCHMARKS_METADATA_KEY)
    if not isinstance(raw_profile, dict):
        raise MetaManagementBenchmarkError(
            "Meta benchmark profile is missing from paid ads profile metadata.metaManagementBenchmarks.",
            code="benchmark_profile_missing",
        )
    try:
        return MetaManagementBenchmarkProfile.model_validate(raw_profile)
    except Exception as exc:  # pragma: no cover - pydantic error formatting is sufficient
        raise MetaManagementBenchmarkError(
            f"Meta benchmark profile is invalid: {exc}",
            code="benchmark_profile_invalid",
        ) from exc


def _resolve_price_cents(session: Session, funnel: Funnel) -> tuple[int | None, str | None]:
    selected_offer_id = str(funnel.selected_offer_id or "").strip()
    if not selected_offer_id:
        return None, "Funnel is missing selected_offer_id, so the sales PDP ATC price band cannot be resolved."

    variants = list(
        session.scalars(
            select(ProductVariant).where(ProductVariant.offer_id == selected_offer_id)
        ).all()
    )
    price_values = sorted(
        {
            int(variant.price)
            for variant in variants
            if isinstance(getattr(variant, "price", None), int) and int(variant.price) > 0
        }
    )
    if not price_values:
        return None, "Selected offer has no concrete price points, so the sales PDP ATC benchmark cannot be resolved."
    if len(price_values) != 1:
        return None, "Selected offer has multiple distinct price points; configure benchmarking per price point first."
    return price_values[0], None


def _resolve_campaign_funnel_context(
    *,
    session: Session,
    org_id: str,
    campaign: Campaign,
    meta_campaign_id: str,
) -> _ResolvedBenchmarkContext:
    delivery = CampaignDeliveryConfigsRepository(session).get_by_campaign(
        org_id=org_id,
        campaign_id=str(campaign.id),
    )
    if delivery is None:
        raise MetaManagementBenchmarkError(
            "Campaign delivery config is required before benchmark evaluation can run.",
            code="delivery_config_missing",
        )
    if delivery.delivery_mode != CampaignDeliveryModeEnum.internal_funnel:
        raise MetaManagementBenchmarkError(
            "This campaign uses external URLs, so mOS can only show Meta-native management. First-party funnel benchmarks require internal_funnel delivery.",
            code="unsupported_delivery_mode",
        )

    publish_run = session.scalars(
        select(MetaPublishRun)
        .where(
            MetaPublishRun.org_id == org_id,
            MetaPublishRun.campaign_id == campaign.id,
            MetaPublishRun.meta_campaign_id == meta_campaign_id,
        )
        .order_by(MetaPublishRun.created_at.desc())
    ).first()
    funnel_id = None
    if publish_run is not None and isinstance(publish_run.metadata_json, dict):
        raw_funnel_id = publish_run.metadata_json.get("funnelId")
        if isinstance(raw_funnel_id, str) and raw_funnel_id.strip():
            funnel_id = raw_funnel_id.strip()

    funnels = list(
        session.scalars(
            select(Funnel).where(
                Funnel.org_id == org_id,
                Funnel.campaign_id == campaign.id,
            )
        ).all()
    )
    funnel: Funnel | None = None
    if funnel_id:
        funnel = next((candidate for candidate in funnels if str(candidate.id) == funnel_id), None)
        if funnel is None:
            raise MetaManagementBenchmarkError(
                f"Published funnel {funnel_id} could not be found for campaign {campaign.id}.",
                code="published_funnel_not_found",
            )
    elif len(funnels) == 1:
        funnel = funnels[0]
    else:
        raise MetaManagementBenchmarkError(
            "Benchmark evaluation could not determine a single funnel for this campaign. Publish metadata must include funnelId.",
            code="funnel_resolution_ambiguous",
        )

    publication_id = str(funnel.active_publication_id or "").strip()
    if not publication_id:
        raise MetaManagementBenchmarkError(
            "Selected funnel is not published, so first-party funnel benchmarks cannot be evaluated.",
            code="funnel_not_published",
        )

    pages = list(
        session.scalars(
            select(FunnelPage).where(FunnelPage.funnel_id == funnel.id)
        ).all()
    )
    sales_page = next((page for page in pages if resolve_funnel_template_category(page.template_id) == "sales"), None)
    if sales_page is None:
        raise MetaManagementBenchmarkError(
            "Benchmark evaluation requires a published sales page.",
            code="sales_page_missing",
        )
    presell_page = next(
        (page for page in pages if resolve_funnel_template_category(page.template_id) == "presales"),
        None,
    )

    price_cents, price_resolution_error = _resolve_price_cents(session, funnel)
    return _ResolvedBenchmarkContext(
        profile_id="",
        profile_updated_at=None,
        delivery_mode=delivery.delivery_mode,
        funnel=funnel,
        sales_page=sales_page,
        presell_page=presell_page,
        publication_id=publication_id,
        price_cents=price_cents,
        price_resolution_error=price_resolution_error,
    )


def build_funnel_metrics_snapshot(
    *,
    session: Session,
    funnel: Funnel,
    publication_id: str,
    sales_page: FunnelPage,
    presell_page: FunnelPage | None,
    date_preset: str,
) -> MetaFunnelMetricsSnapshot:
    start_at, end_at = _resolve_window(date_preset)
    relevant_page_ids = [str(sales_page.id)]
    if presell_page is not None:
        relevant_page_ids.append(str(presell_page.id))

    events = list(
        session.scalars(
            select(FunnelEvent).where(
                FunnelEvent.funnel_id == funnel.id,
                FunnelEvent.publication_id == publication_id,
                FunnelEvent.page_id.in_(relevant_page_ids),
                FunnelEvent.occurred_at >= start_at,
                FunnelEvent.occurred_at <= end_at,
            )
        ).all()
    )

    presell_page_view_sessions = (
        _count_unique_sessions_for_event_types(
            events=events,
            page_id=str(presell_page.id),
            event_types=(
                FunnelEventTypeEnum.pre_sales_page_view,
                FunnelEventTypeEnum.page_view,
            ),
        )
        if presell_page is not None
        else 0
    )
    presell_cta_click_sessions = (
        _count_unique_sessions_for_event_types(
            events=events,
            page_id=str(presell_page.id),
            event_types=(
                FunnelEventTypeEnum.pre_sales_to_sales_click,
                FunnelEventTypeEnum.cta_click,
            ),
        )
        if presell_page is not None
        else 0
    )
    sales_page_view_sessions = _count_unique_sessions_for_event_types(
        events=events,
        page_id=str(sales_page.id),
        event_types=(
            FunnelEventTypeEnum.sales_page_view,
            FunnelEventTypeEnum.page_view,
        ),
    )
    checkout_started_sessions = _count_unique_sessions(
        events=events,
        page_id=str(sales_page.id),
        event_type=FunnelEventTypeEnum.checkout_started,
    )
    order_completed_sessions = _count_unique_sessions(
        events=events,
        page_id=str(sales_page.id),
        event_type=FunnelEventTypeEnum.order_completed,
    )

    return MetaFunnelMetricsSnapshot(
        startedAt=_iso(start_at),
        endedAt=_iso(end_at),
        presellPageId=str(presell_page.id) if presell_page is not None else None,
        salesPageId=str(sales_page.id),
        presellPageViewSessions=presell_page_view_sessions,
        presellCtaClickSessions=presell_cta_click_sessions,
        salesPageViewSessions=sales_page_view_sessions,
        checkoutStartedSessions=checkout_started_sessions,
        orderCompletedSessions=order_completed_sessions,
        presellCtrPct=_ratio_pct(
            numerator=presell_cta_click_sessions,
            denominator=presell_page_view_sessions,
        ),
        salesPdpAtcPct=_ratio_pct(
            numerator=checkout_started_sessions,
            denominator=sales_page_view_sessions,
        ),
        salesPdpPurchaseCvrPct=_ratio_pct(
            numerator=order_completed_sessions,
            denominator=sales_page_view_sessions,
        ),
        checkoutCvrPct=_ratio_pct(
            numerator=order_completed_sessions,
            denominator=checkout_started_sessions,
        ),
    )


def _evaluate_one_sided_metric(
    *,
    metric_id: str,
    label: str,
    scope: str,
    value: float | None,
    numerator: int | None,
    denominator: int | None,
    unit: str,
    benchmark: MetaOneSidedBenchmark,
    reason: str | None = None,
    context: Mapping[str, Any] | None = None,
) -> MetaBenchmarkEvaluation:
    if reason:
        return MetaBenchmarkEvaluation(
            metricId=metric_id,
            label=label,
            scope=scope,
            status="unavailable",
            value=value,
            unit=unit,
            minimum=benchmark.minimum,
            good=benchmark.good,
            numerator=numerator,
            denominator=denominator,
            reason=reason,
            context=dict(context or {}),
        )
    if value is None or denominator is None or denominator <= 0:
        return MetaBenchmarkEvaluation(
            metricId=metric_id,
            label=label,
            scope=scope,
            status="insufficient_data",
            value=value,
            unit=unit,
            minimum=benchmark.minimum,
            good=benchmark.good,
            numerator=numerator,
            denominator=denominator,
            reason="No denominator volume is available for this metric in the selected window.",
            context=dict(context or {}),
        )
    if benchmark.good is not None and value >= benchmark.good:
        status = "good"
    elif value >= benchmark.minimum:
        status = "on_target"
    else:
        status = "below_target"
    return MetaBenchmarkEvaluation(
        metricId=metric_id,
        label=label,
        scope=scope,
        status=status,
        value=value,
        unit=unit,
        minimum=benchmark.minimum,
        good=benchmark.good,
        numerator=numerator,
        denominator=denominator,
        reason=None,
        context=dict(context or {}),
    )


def _evaluate_target_metric(
    *,
    metric_id: str,
    label: str,
    scope: str,
    value: float | None,
    numerator: int | None,
    denominator: int | None,
    unit: str,
    benchmark: MetaTargetBenchmark,
    reason: str | None = None,
    context: Mapping[str, Any] | None = None,
) -> MetaBenchmarkEvaluation:
    if reason:
        return MetaBenchmarkEvaluation(
            metricId=metric_id,
            label=label,
            scope=scope,
            status="unavailable",
            value=value,
            unit=unit,
            target=benchmark.target,
            numerator=numerator,
            denominator=denominator,
            reason=reason,
            context=dict(context or {}),
        )
    if value is None or denominator is None or denominator <= 0:
        return MetaBenchmarkEvaluation(
            metricId=metric_id,
            label=label,
            scope=scope,
            status="insufficient_data",
            value=value,
            unit=unit,
            target=benchmark.target,
            numerator=numerator,
            denominator=denominator,
            reason="No denominator volume is available for this metric in the selected window.",
            context=dict(context or {}),
        )
    status = "on_target" if value >= benchmark.target else "below_target"
    return MetaBenchmarkEvaluation(
        metricId=metric_id,
        label=label,
        scope=scope,
        status=status,
        value=value,
        unit=unit,
        target=benchmark.target,
        numerator=numerator,
        denominator=denominator,
        reason=None,
        context=dict(context or {}),
    )


def _resolve_atc_price_band(
    *,
    profile: MetaManagementBenchmarkProfile,
    price_cents: int | None,
) -> tuple[MetaAtcPriceBandBenchmark | None, str | None]:
    if price_cents is None:
        return None, "Front-end price point could not be resolved for the selected funnel."
    price_dollars = price_cents / 100.0
    for band in profile.salesPdpAtcPctPriceBands:
        if band.minPrice is not None and price_dollars < band.minPrice:
            continue
        if band.maxPrice is not None and price_dollars > band.maxPrice:
            continue
        return band, None
    return None, f"No ATC benchmark band matches front-end price ${price_dollars:,.2f}."


def build_management_benchmark_payload(
    *,
    session: Session,
    org_id: str,
    campaign: Campaign,
    meta_campaign_id: str,
    date_preset: str,
    ad_rows: list[Any],
) -> tuple[MetaBenchmarkContext, MetaFunnelMetricsSnapshot, list[MetaBenchmarkEvaluation]]:
    delivery = CampaignDeliveryConfigsRepository(session).get_by_campaign(
        org_id=org_id,
        campaign_id=str(campaign.id),
    )
    if delivery is None:
        raise MetaManagementBenchmarkError(
            "Campaign delivery config is required before benchmark evaluation can run.",
            code="delivery_config_missing",
        )
    if delivery.delivery_mode != CampaignDeliveryModeEnum.internal_funnel:
        raise MetaManagementBenchmarkError(
            "This campaign uses external URLs, so mOS can only show Meta-native management. First-party funnel benchmarks require internal_funnel delivery.",
            code="unsupported_delivery_mode",
        )

    profile_record = PaidAdsQaRepository(session).get_platform_profile(
        org_id=org_id,
        client_id=str(campaign.client_id),
        platform="meta",
    )
    if profile_record is None:
        raise MetaManagementBenchmarkError(
            "Meta paid ads profile is required before benchmark evaluation can run.",
            code="paid_ads_profile_missing",
        )
    profile = parse_meta_management_benchmark_profile(profile_record.metadata_json)
    resolved_context = _resolve_campaign_funnel_context(
        session=session,
        org_id=org_id,
        campaign=campaign,
        meta_campaign_id=meta_campaign_id,
    )
    funnel_snapshot = build_funnel_metrics_snapshot(
        session=session,
        funnel=resolved_context.funnel,
        publication_id=resolved_context.publication_id,
        sales_page=resolved_context.sales_page,
        presell_page=resolved_context.presell_page,
        date_preset=date_preset,
    )

    total_impressions = 0
    total_link_clicks = 0
    for row in ad_rows:
        impressions = getattr(row, "impressions", None)
        if isinstance(impressions, int):
            total_impressions += impressions
        inline_link_clicks = getattr(row, "inlineLinkClicks", None)
        if isinstance(inline_link_clicks, int):
            total_link_clicks += inline_link_clicks
    ad_link_ctr_pct = _ratio_pct(numerator=total_link_clicks, denominator=total_impressions)

    atc_band, atc_error = _resolve_atc_price_band(
        profile=profile,
        price_cents=resolved_context.price_cents,
    )
    benchmark_context = MetaBenchmarkContext(
        clientId=str(campaign.client_id),
        campaignId=str(campaign.id),
        metaCampaignId=meta_campaign_id,
        datePreset=date_preset,
        funnelId=str(resolved_context.funnel.id),
        publicationId=resolved_context.publication_id,
        deliveryMode=resolved_context.delivery_mode.value,
        profileId=str(profile_record.id),
        priceCents=resolved_context.price_cents,
        priceDollars=(resolved_context.price_cents / 100.0) if resolved_context.price_cents is not None else None,
        atcPriceBandId=atc_band.id if atc_band is not None else None,
        atcPriceBandLabel=atc_band.label if atc_band is not None else None,
        priceResolutionError=resolved_context.price_resolution_error or atc_error,
        profileUpdatedAt=(
            _iso(profile_record.updated_at)
            if getattr(profile_record, "updated_at", None) is not None
            else None
        ),
    )

    evaluations: list[MetaBenchmarkEvaluation] = [
        _evaluate_one_sided_metric(
            metric_id="ad_link_ctr_pct",
            label="Ad link CTR",
            scope="campaign",
            value=ad_link_ctr_pct,
            numerator=total_link_clicks,
            denominator=total_impressions,
            unit="%",
            benchmark=profile.adLinkCtrPct,
            context={"source": "meta_insights"},
        )
    ]

    if resolved_context.presell_page is None:
        evaluations.append(
            MetaBenchmarkEvaluation(
                metricId="presell_ctr_pct",
                label="Advertorial / listicle CTR",
                scope="pre_sales_page",
                status="not_applicable",
                value=None,
                unit="%",
                target=profile.presellCtrPct.target,
                numerator=None,
                denominator=None,
                reason="This funnel does not contain a pre-sales listicle page.",
                context={"source": "funnel_events"},
            )
        )
    else:
        evaluations.append(
            _evaluate_target_metric(
                metric_id="presell_ctr_pct",
                label="Advertorial / listicle CTR",
                scope="pre_sales_page",
                value=funnel_snapshot.presellCtrPct,
                numerator=funnel_snapshot.presellCtaClickSessions,
                denominator=funnel_snapshot.presellPageViewSessions,
                unit="%",
                benchmark=profile.presellCtrPct,
                context={
                    "source": "funnel_events",
                    "pageId": str(resolved_context.presell_page.id),
                },
            )
        )

    evaluations.append(
        _evaluate_one_sided_metric(
            metric_id="sales_pdp_purchase_cvr_pct",
            label="Sales PDP conversion rate",
            scope="sales_page",
            value=funnel_snapshot.salesPdpPurchaseCvrPct,
            numerator=funnel_snapshot.orderCompletedSessions,
            denominator=funnel_snapshot.salesPageViewSessions,
            unit="%",
            benchmark=profile.salesPdpPurchaseCvrPct,
            context={
                "source": "funnel_events",
                "pageId": str(resolved_context.sales_page.id),
            },
        )
    )

    evaluations.append(
        _evaluate_target_metric(
            metric_id="checkout_cvr_pct",
            label="Checkout conversion rate",
            scope="checkout",
            value=funnel_snapshot.checkoutCvrPct,
            numerator=funnel_snapshot.orderCompletedSessions,
            denominator=funnel_snapshot.checkoutStartedSessions,
            unit="%",
            benchmark=profile.checkoutCvrPct,
            context={"source": "funnel_events"},
        )
    )

    if atc_band is None:
        evaluations.append(
            MetaBenchmarkEvaluation(
                metricId="sales_pdp_atc_pct",
                label="Sales PDP add-to-cart rate",
                scope="sales_page",
                status="unavailable",
                value=funnel_snapshot.salesPdpAtcPct,
                unit="%",
                target=None,
                numerator=funnel_snapshot.checkoutStartedSessions,
                denominator=funnel_snapshot.salesPageViewSessions,
                reason=resolved_context.price_resolution_error or atc_error,
                context={
                    "source": "funnel_events",
                    "pageId": str(resolved_context.sales_page.id),
                },
            )
        )
    else:
        evaluations.append(
            _evaluate_target_metric(
                metric_id="sales_pdp_atc_pct",
                label="Sales PDP add-to-cart rate",
                scope="sales_page",
                value=funnel_snapshot.salesPdpAtcPct,
                numerator=funnel_snapshot.checkoutStartedSessions,
                denominator=funnel_snapshot.salesPageViewSessions,
                unit="%",
                benchmark=MetaTargetBenchmark(target=atc_band.target),
                context={
                    "source": "funnel_events",
                    "pageId": str(resolved_context.sales_page.id),
                    "priceBandId": atc_band.id,
                    "priceBandLabel": atc_band.label,
                },
            )
        )

    return benchmark_context, funnel_snapshot, evaluations
