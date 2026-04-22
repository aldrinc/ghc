from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.services.meta_ads import MetaAdsClient, MetaAdsError, MetaAdsRateLimitError, _normalize_ad_account_id
from app.services.meta_management_benchmarks import (
    MetaBenchmarkContext,
    MetaBenchmarkEvaluation,
    MetaFunnelMetricsSnapshot,
)


class MetaMediaBuyingPlanError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_payload: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_payload = error_payload


def _to_int(value: Any, *, field: str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if raw.isdigit():
            return int(raw)
    raise MetaMediaBuyingPlanError(f"Invalid {field}: expected int-like value, got {value!r}")


def _to_float(value: Any, *, field: str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip()
        try:
            return float(raw)
        except ValueError as exc:
            raise MetaMediaBuyingPlanError(
                f"Invalid {field}: expected float-like value, got {value!r}"
            ) from exc
    raise MetaMediaBuyingPlanError(f"Invalid {field}: expected float-like value, got {value!r}")


def _parse_action_list(value: Any, *, field: str) -> dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, list):
        raise MetaMediaBuyingPlanError(
            f"Invalid {field}: expected a list, got {type(value).__name__}"
        )
    out: dict[str, float] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        action_type = item.get("action_type")
        if not isinstance(action_type, str) or not action_type.strip():
            continue
        raw_val = item.get("value")
        if raw_val is None:
            continue
        out[action_type] = _to_float(raw_val, field=f"{field}.{action_type}")
    return out


def _sum_action(value: Any, *, field: str) -> int:
    action_map = _parse_action_list(value, field=field)
    total = 0
    for k, v in action_map.items():
        _ = k
        total += int(v)
    return total


@dataclass(frozen=True)
class MetaEventMappings:
    landing_page_view_action_type: Optional[str] = "landing_page_view"
    content_view_action_type: Optional[str] = "offsite_conversion.fb_pixel_view_content"
    add_to_cart_action_type: Optional[str] = "offsite_conversion.fb_pixel_add_to_cart"
    initiate_checkout_action_type: Optional[str] = "offsite_conversion.fb_pixel_initiate_checkout"
    purchase_action_type: Optional[str] = "offsite_conversion.fb_pixel_purchase"
    purchase_value_action_type: Optional[str] = "offsite_conversion.fb_pixel_purchase"


class MetaInsightsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datePreset: str = "last_3d"


class MetaCutRuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minSpend: float = 30.0
    maxCpm: float = 50.0
    minLinkCtr: float = 1.0
    maxLinkCpc: float = 3.0


class MetaCustomMetricDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metricId: str
    label: str
    description: str
    formula: str
    sourcePlane: str
    sourceClass: str
    unit: str
    numeratorLabel: str
    denominatorLabel: str
    minimum: float | None = None
    target: float | None = None
    good: float | None = None


class MetaCustomMetricEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metricId: str
    scope: str
    status: str
    value: float | None = None
    unit: str
    numerator: int | None = None
    denominator: int | None = None
    minimum: float | None = None
    target: float | None = None
    good: float | None = None
    resolvedSources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    reason: str | None = None
    recommendation: str | None = None


class MetaCustomMetricRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adId: str
    adName: str = ""
    metrics: list[MetaCustomMetricEvaluation] = Field(default_factory=list)


class MetaAdMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adId: str
    adName: str = ""
    adsetId: Optional[str] = None
    campaignId: Optional[str] = None

    impressions: int
    spend: float
    cpm: float
    frequency: Optional[float] = None

    inlineLinkClicks: Optional[int] = None
    linkCtrPct: Optional[float] = None
    linkCpc: Optional[float] = None

    hookRatePct: Optional[float] = None
    holdRatePct: Optional[float] = None

    atcRatioPct: Optional[float] = None
    purchaseRatioPct: Optional[float] = None
    aov: Optional[float] = None

    raw: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class MetaPlannedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    metaAdId: str
    reason: str
    triggeredRules: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class MetaAppliedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    metaEntityId: str
    status: str
    requestPayload: dict[str, Any] = Field(default_factory=dict)
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


MetaManagementBenchmarkMode = Literal["disabled", "best_effort", "required"]
MetaManagementScope = Literal["meta_only", "meta_plus_funnel"]


class MetaManagementBenchmarkStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requestedMode: MetaManagementBenchmarkMode
    available: bool
    reasonCode: str | None = None
    reason: str | None = None


class MetaObjectStatusCount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    count: int


class MetaIssueSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adId: str
    adName: str = ""
    adsetId: str | None = None
    status: str | None = None
    effectiveStatus: str | None = None
    errorCode: int | None = None
    errorSummary: str | None = None
    errorMessage: str | None = None


class MetaObjectStateSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaignStatus: str | None = None
    campaignEffectiveStatus: str | None = None
    adsetCount: int = 0
    adCount: int = 0
    insightsRowCount: int = 0
    deliveryState: str
    deliverySummary: str
    adsetStatusCounts: list[MetaObjectStatusCount] = Field(default_factory=list)
    adsetEffectiveStatusCounts: list[MetaObjectStatusCount] = Field(default_factory=list)
    adStatusCounts: list[MetaObjectStatusCount] = Field(default_factory=list)
    adEffectiveStatusCounts: list[MetaObjectStatusCount] = Field(default_factory=list)
    issueCount: int = 0
    reviewPendingCount: int = 0
    issueSamples: list[MetaIssueSample] = Field(default_factory=list)


class MetaManagementPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    generatedAt: str
    window: dict[str, Any]
    campaign: dict[str, Any]
    adsets: list[dict[str, Any]]
    objectState: MetaObjectStateSummary
    observedActionTypes: dict[str, list[str]] = Field(default_factory=dict)
    rows: list[MetaAdMetrics]
    actions: list[MetaPlannedAction]
    appliedActions: list[MetaAppliedAction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    managementScope: MetaManagementScope = "meta_only"
    benchmarkStatus: MetaManagementBenchmarkStatus = Field(
        default_factory=lambda: MetaManagementBenchmarkStatus(
            requestedMode="disabled",
            available=False,
            reasonCode="disabled_by_request",
            reason="Benchmark evaluation was not requested.",
        )
    )
    benchmarkContext: MetaBenchmarkContext | None = None
    funnelSnapshot: MetaFunnelMetricsSnapshot | None = None
    benchmarkEvaluations: list[MetaBenchmarkEvaluation] = Field(default_factory=list)
    customMetricDefinitions: list[MetaCustomMetricDefinition] = Field(default_factory=list)
    customMetricSummary: list[MetaCustomMetricEvaluation] = Field(default_factory=list)
    customMetricRows: list[MetaCustomMetricRow] = Field(default_factory=list)


@dataclass(frozen=True)
class _MetaCustomMetricSpec:
    metric_id: str
    label: str
    description: str
    formula: str
    numerator_primitive: str
    denominator_primitive: str
    numerator_label: str
    denominator_label: str
    minimum: float | None = None
    target: float | None = None
    good: float | None = None


@dataclass(frozen=True)
class _ResolvedPrimitive:
    value: int
    source_key: str
    observed: bool
    warnings: tuple[str, ...] = ()


_META_CUSTOM_METRIC_SPECS: tuple[_MetaCustomMetricSpec, ...] = (
    _MetaCustomMetricSpec(
        metric_id="meta_atc_ratio_pct",
        label="ATC Ratio",
        description=(
            "Adds to cart divided by website landing page views. This shows whether the "
            "landing page is converting paid visitors into shopping intent."
        ),
        formula="Adds to cart / Landing page views",
        numerator_primitive="adds_to_cart",
        denominator_primitive="landing_page_views",
        numerator_label="Adds to cart",
        denominator_label="Landing page views",
        minimum=10.0,
    ),
    _MetaCustomMetricSpec(
        metric_id="meta_conversion_rate_pct",
        label="Conversion Rate",
        description=(
            "Purchases divided by website landing page views. This is the Meta-estimated "
            "end-to-end conversion rate from ad visit to order."
        ),
        formula="Purchases / Landing page views",
        numerator_primitive="purchases",
        denominator_primitive="landing_page_views",
        numerator_label="Purchases",
        denominator_label="Landing page views",
        minimum=1.0,
        good=3.0,
    ),
    _MetaCustomMetricSpec(
        metric_id="meta_ic_ratio_pct",
        label="IC Ratio",
        description=(
            "Initiated checkouts divided by website landing page views. This shows how many "
            "landing page visitors reach checkout start."
        ),
        formula="Initiated checkouts / Landing page views",
        numerator_primitive="initiated_checkouts",
        denominator_primitive="landing_page_views",
        numerator_label="Initiated checkouts",
        denominator_label="Landing page views",
    ),
    _MetaCustomMetricSpec(
        metric_id="meta_purchase_ratio_pct",
        label="Purchase Ratio",
        description=(
            "Purchases divided by adds to cart. This is a checkout-efficiency read on how "
            "many carts finish as orders."
        ),
        formula="Purchases / Adds to cart",
        numerator_primitive="purchases",
        denominator_primitive="adds_to_cart",
        numerator_label="Purchases",
        denominator_label="Adds to cart",
        minimum=30.0,
    ),
    _MetaCustomMetricSpec(
        metric_id="meta_video_hold_rate_pct",
        label="Video Hold Rate",
        description=(
            "50% video plays divided by impressions. This shows whether the body of the ad "
            "holds attention after the hook."
        ),
        formula="Video plays at 50% / Impressions",
        numerator_primitive="video_p50_plays",
        denominator_primitive="impressions",
        numerator_label="Video plays at 50%",
        denominator_label="Impressions",
        minimum=25.0,
    ),
)


_CUSTOM_METRIC_RECOMMENDATIONS: dict[str, str] = {
    "meta_atc_ratio_pct": (
        "Landing page efficiency is below KPI. Audit message match, offer clarity, proof, "
        "and CTA density before adding spend."
    ),
    "meta_conversion_rate_pct": (
        "Overall conversion from landing page view to purchase is weak. Review the full path "
        "from creative promise through checkout completion."
    ),
    "meta_purchase_ratio_pct": (
        "Purchases are not keeping up with cart volume. Check for checkout friction, price "
        "shock, payment failures, or missing trust elements."
    ),
    "meta_video_hold_rate_pct": (
        "The creative is losing attention after the hook. Tighten the body, pacing, and "
        "proof sequence before scaling."
    ),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe_strings(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def _build_custom_metric_definitions() -> list[MetaCustomMetricDefinition]:
    return [
        MetaCustomMetricDefinition(
            metricId=spec.metric_id,
            label=spec.label,
            description=spec.description,
            formula=spec.formula,
            sourcePlane="meta_ads",
            sourceClass="meta_estimated",
            unit="pct",
            numeratorLabel=spec.numerator_label,
            denominatorLabel=spec.denominator_label,
            minimum=spec.minimum,
            target=spec.target,
            good=spec.good,
        )
        for spec in _META_CUSTOM_METRIC_SPECS
    ]


def _resolve_action_primitive(
    *,
    actions: dict[str, float],
    observed_action_types: set[str],
    action_type: str | None,
    warning_code: str,
) -> _ResolvedPrimitive:
    if not action_type:
        return _ResolvedPrimitive(value=0, source_key="", observed=False, warnings=(warning_code,))
    return _ResolvedPrimitive(
        value=int(actions.get(action_type, 0.0)),
        source_key=action_type,
        observed=action_type in observed_action_types,
        warnings=tuple([warning_code]) if action_type not in observed_action_types else (),
    )


def _resolve_video_p50_primitive(*, row: dict[str, Any]) -> _ResolvedPrimitive:
    if "video_p50_watched_actions" not in row:
        return _ResolvedPrimitive(
            value=0,
            source_key="video_p50_watched_actions",
            observed=False,
            warnings=("missing_source.video_p50",),
        )
    try:
        return _ResolvedPrimitive(
            value=_sum_action(row.get("video_p50_watched_actions"), field="video_p50_watched_actions"),
            source_key="video_p50_watched_actions",
            observed=True,
            warnings=(),
        )
    except MetaMediaBuyingPlanError:
        return _ResolvedPrimitive(
            value=0,
            source_key="video_p50_watched_actions",
            observed=False,
            warnings=("invalid_source.video_p50",),
        )


def _resolve_custom_metric_primitives(
    *,
    row: dict[str, Any],
    observed_action_types: set[str],
    event_mappings: MetaEventMappings,
) -> dict[str, _ResolvedPrimitive]:
    actions = _parse_action_list(row.get("actions"), field="actions")
    return {
        "impressions": _ResolvedPrimitive(
            value=_to_int(row.get("impressions"), field="impressions"),
            source_key="impressions",
            observed=True,
        ),
        "landing_page_views": _resolve_action_primitive(
            actions=actions,
            observed_action_types=observed_action_types,
            action_type=event_mappings.landing_page_view_action_type,
            warning_code="missing_source.landing_page_views",
        ),
        "adds_to_cart": _resolve_action_primitive(
            actions=actions,
            observed_action_types=observed_action_types,
            action_type=event_mappings.add_to_cart_action_type,
            warning_code="missing_source.adds_to_cart",
        ),
        "initiated_checkouts": _resolve_action_primitive(
            actions=actions,
            observed_action_types=observed_action_types,
            action_type=event_mappings.initiate_checkout_action_type,
            warning_code="missing_source.initiated_checkouts",
        ),
        "purchases": _resolve_action_primitive(
            actions=actions,
            observed_action_types=observed_action_types,
            action_type=event_mappings.purchase_action_type,
            warning_code="missing_source.purchases",
        ),
        "video_p50_plays": _resolve_video_p50_primitive(row=row),
    }


def _aggregate_custom_metric_primitives(
    primitive_sets: list[dict[str, _ResolvedPrimitive]],
) -> dict[str, _ResolvedPrimitive]:
    aggregated: dict[str, _ResolvedPrimitive] = {}
    for primitive_name in {
        "impressions",
        "landing_page_views",
        "adds_to_cart",
        "initiated_checkouts",
        "purchases",
        "video_p50_plays",
    }:
        values = [primitive_set[primitive_name] for primitive_set in primitive_sets]
        aggregated[primitive_name] = _ResolvedPrimitive(
            value=sum(item.value for item in values),
            source_key=values[0].source_key if values else "",
            observed=any(item.observed for item in values),
            warnings=tuple(
                _dedupe_strings([warning for item in values for warning in item.warnings])
            ),
        )
    return aggregated


def _evaluate_custom_metric_status(
    *,
    value: float,
    definition: MetaCustomMetricDefinition,
) -> tuple[str, str | None]:
    if definition.good is not None and value >= definition.good:
        return "good", f"{definition.label} cleared the strong-performance threshold."
    if definition.target is not None:
        if value >= definition.target:
            return "on_target", f"{definition.label} met the KPI target."
        return "below_target", f"{definition.label} is below the KPI target."
    if definition.minimum is not None:
        if value >= definition.minimum:
            return "on_target", f"{definition.label} met the KPI floor."
        return "below_target", f"{definition.label} is below the KPI floor."
    return "target_not_configured", "Target not configured for this metric yet."


def _evaluate_custom_metric(
    *,
    definition: MetaCustomMetricDefinition,
    numerator: _ResolvedPrimitive,
    denominator: _ResolvedPrimitive,
    scope: str,
) -> MetaCustomMetricEvaluation:
    warnings = _dedupe_strings(["estimated_metric_source", *numerator.warnings, *denominator.warnings])
    resolved_sources = _dedupe_strings([numerator.source_key, denominator.source_key])
    if not denominator.observed:
        return MetaCustomMetricEvaluation(
            metricId=definition.metricId,
            scope=scope,
            status="unavailable",
            unit=definition.unit,
            numerator=numerator.value,
            denominator=denominator.value,
            minimum=definition.minimum,
            target=definition.target,
            good=definition.good,
            resolvedSources=resolved_sources,
            warnings=warnings,
            reason=(
                f"Meta did not return the configured source for "
                f"{definition.denominatorLabel.lower()} in this window."
            ),
            recommendation=None,
        )
    if denominator.value <= 0:
        return MetaCustomMetricEvaluation(
            metricId=definition.metricId,
            scope=scope,
            status="insufficient_data",
            unit=definition.unit,
            numerator=numerator.value,
            denominator=denominator.value,
            minimum=definition.minimum,
            target=definition.target,
            good=definition.good,
            resolvedSources=resolved_sources,
            warnings=warnings,
            reason=f"{definition.denominatorLabel} was 0 in the selected window.",
            recommendation=None,
        )

    value = (numerator.value / denominator.value) * 100.0
    status, reason = _evaluate_custom_metric_status(value=value, definition=definition)
    recommendation = _CUSTOM_METRIC_RECOMMENDATIONS.get(definition.metricId) if status == "below_target" else None
    return MetaCustomMetricEvaluation(
        metricId=definition.metricId,
        scope=scope,
        status=status,
        value=value,
        unit=definition.unit,
        numerator=numerator.value,
        denominator=denominator.value,
        minimum=definition.minimum,
        target=definition.target,
        good=definition.good,
        resolvedSources=resolved_sources,
        warnings=warnings,
        reason=reason,
        recommendation=recommendation,
    )


def _build_custom_metric_payload(
    *,
    rows: list[dict[str, Any]],
    computed_rows: list[MetaAdMetrics],
    observed_action_types: set[str],
    event_mappings: MetaEventMappings,
) -> tuple[list[MetaCustomMetricDefinition], list[MetaCustomMetricEvaluation], list[MetaCustomMetricRow]]:
    definitions = _build_custom_metric_definitions()
    definition_map = {definition.metricId: definition for definition in definitions}
    row_primitive_sets = [
        _resolve_custom_metric_primitives(
            row=row,
            observed_action_types=observed_action_types,
            event_mappings=event_mappings,
        )
        for row in rows
    ]
    custom_metric_rows: list[MetaCustomMetricRow] = []
    for computed_row, primitives in zip(computed_rows, row_primitive_sets):
        metrics = [
            _evaluate_custom_metric(
                definition=definition_map[spec.metric_id],
                numerator=primitives[spec.numerator_primitive],
                denominator=primitives[spec.denominator_primitive],
                scope="ad",
            )
            for spec in _META_CUSTOM_METRIC_SPECS
        ]
        custom_metric_rows.append(
            MetaCustomMetricRow(
                adId=computed_row.adId,
                adName=computed_row.adName,
                metrics=metrics,
            )
        )

    summary_primitives = _aggregate_custom_metric_primitives(row_primitive_sets)
    custom_metric_summary = [
        _evaluate_custom_metric(
            definition=definition_map[spec.metric_id],
            numerator=summary_primitives[spec.numerator_primitive],
            denominator=summary_primitives[spec.denominator_primitive],
            scope="campaign",
        )
        for spec in _META_CUSTOM_METRIC_SPECS
    ]
    return definitions, custom_metric_summary, custom_metric_rows


def fetch_meta_campaign_snapshot(
    *,
    client: MetaAdsClient,
    campaign_id: str,
    ad_account_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    campaign_fields = ",".join(
        [
            "id",
            "name",
            "objective",
            "status",
            "effective_status",
            "daily_budget",
            "lifetime_budget",
            "buying_type",
            "special_ad_categories",
            "is_adset_budget_sharing_enabled",
        ]
    )
    campaign = client._request(
        "GET",
        campaign_id,
        params={"fields": campaign_fields},
        throttle_scope=ad_account_id,
    )

    adsets_fields = ",".join(
        [
            "id",
            "name",
            "daily_budget",
            "lifetime_budget",
            "optimization_goal",
            "billing_event",
            "status",
            "effective_status",
            "promoted_object",
            "start_time",
            "end_time",
        ]
    )
    adsets = client._request(
        "GET",
        f"{campaign_id}/adsets",
        params={"fields": adsets_fields, "limit": 200},
        throttle_scope=ad_account_id,
    ).get("data")
    if adsets is None:
        adsets_list: list[dict[str, Any]] = []
    elif isinstance(adsets, list):
        adsets_list = [row for row in adsets if isinstance(row, dict)]
    else:
        raise MetaMediaBuyingPlanError("Meta returned non-list adsets data.")

    ads_fields = ",".join(
        [
            "id",
            "name",
            "status",
            "effective_status",
            "adset_id",
            "campaign_id",
            "issues_info",
        ]
    )
    ads_out: list[dict[str, Any]] = []
    after: Optional[str] = None
    seen: set[str] = set()
    while True:
        params: dict[str, Any] = {"fields": ads_fields, "limit": 200}
        if after:
            params["after"] = after
        resp = client._request(
            "GET",
            f"{campaign_id}/ads",
            params=params,
            throttle_scope=ad_account_id,
        )
        data = resp.get("data") if isinstance(resp, dict) else None
        if data:
            ads_out.extend([row for row in data if isinstance(row, dict)])
        paging = resp.get("paging") if isinstance(resp, dict) else None
        cursors = paging.get("cursors") if isinstance(paging, dict) else None
        after = cursors.get("after") if isinstance(cursors, dict) else None
        if not after:
            break
        if after in seen:
            raise MetaMediaBuyingPlanError("Meta ads pagination cursor repeated; aborting to avoid infinite loop.")
        seen.add(after)

    return campaign, adsets_list, ads_out


def _to_status_label(value: Any) -> str | None:
    cleaned = str(value).strip() if value is not None else ""
    return cleaned or None


def _status_counts(rows: list[dict[str, Any]], *, field: str) -> list[MetaObjectStatusCount]:
    counts: dict[str, int] = {}
    for row in rows:
        value = _to_status_label(row.get(field))
        if value is None:
            continue
        counts[value] = counts.get(value, 0) + 1
    return [
        MetaObjectStatusCount(value=value, count=count)
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _issue_entries(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [entry for entry in value if isinstance(entry, dict)]
    return []


def _extract_issue_sample(ad: dict[str, Any]) -> MetaIssueSample | None:
    issues = _issue_entries(ad.get("issues_info"))
    first_issue = issues[0] if issues else {}
    error_code = first_issue.get("error_code")
    if not isinstance(error_code, int):
        try:
            error_code = int(str(error_code)) if error_code is not None else None
        except (TypeError, ValueError):
            error_code = None

    error_summary = first_issue.get("error_summary")
    error_message = first_issue.get("error_message")
    if not isinstance(error_summary, str):
        error_summary = None
    if not isinstance(error_message, str):
        error_message = None
    if not issues and _to_status_label(ad.get("effective_status")) != "WITH_ISSUES":
        return None
    ad_id = ad.get("id")
    if not isinstance(ad_id, str) or not ad_id.strip():
        return None
    return MetaIssueSample(
        adId=ad_id,
        adName=ad.get("name") if isinstance(ad.get("name"), str) else "",
        adsetId=ad.get("adset_id") if isinstance(ad.get("adset_id"), str) else None,
        status=_to_status_label(ad.get("status")),
        effectiveStatus=_to_status_label(ad.get("effective_status")),
        errorCode=error_code,
        errorSummary=error_summary,
        errorMessage=error_message,
    )


def _review_pending(sample: MetaIssueSample) -> bool:
    candidates = [sample.effectiveStatus, sample.errorSummary, sample.errorMessage]
    joined = " ".join(value.lower() for value in candidates if isinstance(value, str))
    return "review" in joined or sample.effectiveStatus == "PENDING_REVIEW"


def _build_object_state_summary(
    *,
    campaign: dict[str, Any],
    adsets: list[dict[str, Any]],
    ads: list[dict[str, Any]],
    insights_row_count: int,
) -> MetaObjectStateSummary:
    issue_samples = [sample for sample in (_extract_issue_sample(ad) for ad in ads) if sample is not None]
    review_pending_count = sum(1 for sample in issue_samples if _review_pending(sample))

    campaign_status = _to_status_label(campaign.get("status"))
    campaign_effective_status = _to_status_label(campaign.get("effective_status"))
    ad_effective_statuses = {
        count.value for count in _status_counts(ads, field="effective_status") if count.count > 0
    }

    if insights_row_count > 0:
        delivery_state = "delivering"
        delivery_summary = (
            f"Meta returned {insights_row_count} ad-level insight row"
            f"{'' if insights_row_count == 1 else 's'} for the selected window."
        )
    elif review_pending_count > 0:
        delivery_state = "review_blocked"
        delivery_summary = (
            f"{review_pending_count} ad{'' if review_pending_count == 1 else 's'} "
            "appear to be blocked in Meta review, so no delivery rows were returned yet."
        )
    elif "WITH_ISSUES" in ad_effective_statuses:
        delivery_state = "ads_with_issues"
        delivery_summary = (
            f"{len(issue_samples)} ad{'' if len(issue_samples) == 1 else 's'} are marked "
            "`WITH_ISSUES`, so delivery data may be unavailable until Meta clears them."
        )
    elif campaign_effective_status == "ARCHIVED" or campaign_status == "ARCHIVED":
        delivery_state = "archived"
        delivery_summary = "This campaign is archived, so fresh delivery metrics are not expected."
    elif campaign_effective_status == "PAUSED" or campaign_status == "PAUSED":
        delivery_state = "paused"
        delivery_summary = "This campaign is paused in Meta, so the selected window returned no ad-level delivery rows."
    elif not ads:
        delivery_state = "no_ads"
        delivery_summary = "Meta campaign snapshot returned no ads yet."
    else:
        delivery_state = "no_recent_delivery"
        delivery_summary = (
            "Meta returned no ad-level insights for this window. Check the selected date range, "
            "review state, and whether the campaign is actively serving."
        )

    return MetaObjectStateSummary(
        campaignStatus=campaign_status,
        campaignEffectiveStatus=campaign_effective_status,
        adsetCount=len(adsets),
        adCount=len(ads),
        insightsRowCount=insights_row_count,
        deliveryState=delivery_state,
        deliverySummary=delivery_summary,
        adsetStatusCounts=_status_counts(adsets, field="status"),
        adsetEffectiveStatusCounts=_status_counts(adsets, field="effective_status"),
        adStatusCounts=_status_counts(ads, field="status"),
        adEffectiveStatusCounts=_status_counts(ads, field="effective_status"),
        issueCount=len(issue_samples),
        reviewPendingCount=review_pending_count,
        issueSamples=issue_samples[:10],
    )


def fetch_ad_level_insights(
    *,
    client: MetaAdsClient,
    ad_account_id: str,
    campaign_id: str,
    date_preset: str,
) -> list[dict[str, Any]]:
    fields = ",".join(
        [
            "ad_id",
            "ad_name",
            "adset_id",
            "campaign_id",
            "date_start",
            "date_stop",
            "impressions",
            "spend",
            "cpm",
            "frequency",
            "inline_link_clicks",
            "inline_link_click_ctr",
            "cost_per_inline_link_click",
            "actions",
            "action_values",
            "video_play_actions",
            "video_thruplay_watched_actions",
            "video_p50_watched_actions",
        ]
    )
    filtering = json.dumps([{"field": "campaign.id", "operator": "EQUAL", "value": campaign_id}])
    params: dict[str, Any] = {
        "fields": fields,
        "level": "ad",
        "date_preset": date_preset,
        "filtering": filtering,
        "limit": 200,
    }

    out: list[dict[str, Any]] = []
    after: Optional[str] = None
    seen: set[str] = set()
    normalized_ad_account_id = _normalize_ad_account_id(ad_account_id)
    while True:
        if after:
            params["after"] = after
        resp = client._request(
            "GET",
            f"{normalized_ad_account_id}/insights",
            params=params,
            throttle_scope=ad_account_id,
        )
        data = resp.get("data") if isinstance(resp, dict) else None
        if data:
            out.extend([row for row in data if isinstance(row, dict)])
        paging = resp.get("paging") if isinstance(resp, dict) else None
        cursors = paging.get("cursors") if isinstance(paging, dict) else None
        after = cursors.get("after") if isinstance(cursors, dict) else None
        if not after:
            break
        if after in seen:
            raise MetaMediaBuyingPlanError("Meta pagination cursor repeated; aborting to avoid infinite loop.")
        seen.add(after)
    return out


def _compute_ad_metrics(
    *,
    row: dict[str, Any],
    event_mappings: MetaEventMappings,
    include_raw: bool,
) -> MetaAdMetrics:
    warnings: list[str] = []

    ad_id = row.get("ad_id")
    if not isinstance(ad_id, str) or not ad_id.strip():
        raise MetaMediaBuyingPlanError("Insights row missing ad_id.")
    impressions = _to_int(row.get("impressions"), field="impressions")
    spend = _to_float(row.get("spend"), field="spend")
    cpm = _to_float(row.get("cpm"), field="cpm")
    frequency_raw = row.get("frequency")
    frequency = _to_float(frequency_raw, field="frequency") if frequency_raw is not None else None

    inline_link_clicks_raw = row.get("inline_link_clicks")
    inline_link_clicks = _to_int(inline_link_clicks_raw, field="inline_link_clicks") if inline_link_clicks_raw is not None else None

    link_ctr_raw = row.get("inline_link_click_ctr")
    link_ctr_pct = _to_float(link_ctr_raw, field="inline_link_click_ctr") if link_ctr_raw is not None else None
    if link_ctr_pct is None and inline_link_clicks is not None and impressions > 0:
        link_ctr_pct = (inline_link_clicks / impressions) * 100.0
        warnings.append("computed_link_ctr_pct_from_counts")

    link_cpc_raw = row.get("cost_per_inline_link_click")
    link_cpc = _to_float(link_cpc_raw, field="cost_per_inline_link_click") if link_cpc_raw is not None else None
    if link_cpc is None and inline_link_clicks is not None and inline_link_clicks > 0:
        link_cpc = spend / inline_link_clicks
        warnings.append("computed_link_cpc_from_spend_and_clicks")

    video_plays = None
    if "video_play_actions" in row:
        try:
            video_plays = _sum_action(row.get("video_play_actions"), field="video_play_actions")
        except MetaMediaBuyingPlanError:
            warnings.append("invalid_video_play_actions")
    thruplays = None
    if "video_thruplay_watched_actions" in row:
        try:
            thruplays = _sum_action(row.get("video_thruplay_watched_actions"), field="video_thruplay_watched_actions")
        except MetaMediaBuyingPlanError:
            warnings.append("invalid_video_thruplay_watched_actions")

    hook_rate_pct = None
    hold_rate_pct = None
    if impressions > 0 and video_plays is not None:
        hook_rate_pct = (video_plays / impressions) * 100.0
    if impressions > 0 and thruplays is not None:
        hold_rate_pct = (thruplays / impressions) * 100.0

    actions = _parse_action_list(row.get("actions"), field="actions")
    action_values = _parse_action_list(row.get("action_values"), field="action_values")

    atc_ratio_pct = None
    purchase_ratio_pct = None
    aov = None

    if event_mappings.content_view_action_type and event_mappings.add_to_cart_action_type:
        content_views = actions.get(event_mappings.content_view_action_type, 0.0)
        atcs = actions.get(event_mappings.add_to_cart_action_type, 0.0)
        if content_views > 0:
            atc_ratio_pct = (atcs / content_views) * 100.0
    elif event_mappings.content_view_action_type or event_mappings.add_to_cart_action_type:
        warnings.append("incomplete_event_mapping_atc_ratio")

    if event_mappings.purchase_action_type and event_mappings.add_to_cart_action_type:
        purchases = actions.get(event_mappings.purchase_action_type, 0.0)
        atcs = actions.get(event_mappings.add_to_cart_action_type, 0.0)
        if atcs > 0:
            purchase_ratio_pct = (purchases / atcs) * 100.0
    elif event_mappings.purchase_action_type or event_mappings.add_to_cart_action_type:
        warnings.append("incomplete_event_mapping_purchase_ratio")

    if event_mappings.purchase_action_type and event_mappings.purchase_value_action_type:
        purchases = actions.get(event_mappings.purchase_action_type, 0.0)
        purchase_value = action_values.get(event_mappings.purchase_value_action_type, 0.0)
        if purchases > 0:
            aov = purchase_value / purchases
    elif event_mappings.purchase_action_type or event_mappings.purchase_value_action_type:
        warnings.append("incomplete_event_mapping_aov")

    return MetaAdMetrics(
        adId=ad_id,
        adName=row.get("ad_name") if isinstance(row.get("ad_name"), str) else "",
        adsetId=row.get("adset_id") if isinstance(row.get("adset_id"), str) else None,
        campaignId=row.get("campaign_id") if isinstance(row.get("campaign_id"), str) else None,
        impressions=impressions,
        spend=spend,
        cpm=cpm,
        frequency=frequency,
        inlineLinkClicks=inline_link_clicks,
        linkCtrPct=link_ctr_pct,
        linkCpc=link_cpc,
        hookRatePct=hook_rate_pct,
        holdRatePct=hold_rate_pct,
        atcRatioPct=atc_ratio_pct,
        purchaseRatioPct=purchase_ratio_pct,
        aov=aov,
        raw=row if include_raw else {},
        warnings=warnings,
    )


def build_management_plan(
    *,
    client: MetaAdsClient,
    ad_account_id: str,
    campaign_id: str,
    mode: str,
    insights: MetaInsightsConfig,
    cut_rules: MetaCutRuleConfig,
    event_mappings: MetaEventMappings,
    include_raw: bool = False,
) -> MetaManagementPlan:
    if mode not in {"plan_only", "apply"}:
        raise MetaMediaBuyingPlanError("mode must be plan_only or apply")

    try:
        campaign, adsets, ads = fetch_meta_campaign_snapshot(
            client=client,
            campaign_id=campaign_id,
            ad_account_id=ad_account_id,
        )
        preflight_object_state = _build_object_state_summary(
            campaign=campaign,
            adsets=adsets,
            ads=ads,
            insights_row_count=0,
        )
        if preflight_object_state.deliveryState in {
            "review_blocked",
            "ads_with_issues",
            "archived",
            "paused",
            "no_ads",
        }:
            rows = []
        else:
            rows = fetch_ad_level_insights(
                client=client,
                ad_account_id=ad_account_id,
                campaign_id=campaign_id,
                date_preset=insights.datePreset,
            )
    except MetaAdsRateLimitError as exc:
        raise MetaMediaBuyingPlanError(
            "Meta management snapshot deferred due to ad account pressure.",
            status_code=exc.status_code,
            error_payload=exc.error_payload,
        ) from exc
    except MetaAdsError as exc:
        raise MetaMediaBuyingPlanError(
            str(exc),
            status_code=exc.status_code,
            error_payload=exc.error_payload,
        ) from exc

    object_state = _build_object_state_summary(
        campaign=campaign,
        adsets=adsets,
        ads=ads,
        insights_row_count=len(rows),
    )

    computed_rows: list[MetaAdMetrics] = []
    observed_actions: set[str] = set()
    observed_action_values: set[str] = set()
    for row in rows:
        observed_actions.update(_parse_action_list(row.get("actions"), field="actions").keys())
        observed_action_values.update(_parse_action_list(row.get("action_values"), field="action_values").keys())
        computed_rows.append(_compute_ad_metrics(row=row, event_mappings=event_mappings, include_raw=include_raw))

    custom_metric_definitions, custom_metric_summary, custom_metric_rows = _build_custom_metric_payload(
        rows=rows,
        computed_rows=computed_rows,
        observed_action_types=observed_actions,
        event_mappings=event_mappings,
    )

    actions: list[MetaPlannedAction] = []
    for r in computed_rows:
        if r.spend <= cut_rules.minSpend:
            continue
        triggered: list[str] = []
        reason_parts: list[str] = []

        if r.linkCpc is not None and r.linkCpc > cut_rules.maxLinkCpc:
            triggered.append("kill_ad.link_cpc")
            reason_parts.append(f"Link CPC {r.linkCpc:.2f} > {cut_rules.maxLinkCpc:.2f}")
        if r.linkCtrPct is not None and r.linkCtrPct < cut_rules.minLinkCtr:
            triggered.append("kill_ad.link_ctr")
            reason_parts.append(f"Link CTR {r.linkCtrPct:.2f}% < {cut_rules.minLinkCtr:.2f}%")
        if r.cpm > cut_rules.maxCpm:
            triggered.append("kill_ad.cpm")
            reason_parts.append(f"CPM {r.cpm:.2f} > {cut_rules.maxCpm:.2f}")

        if not triggered:
            continue

        actions.append(
            MetaPlannedAction(
                kind="pause_ad",
                metaAdId=r.adId,
                reason="; ".join(reason_parts),
                triggeredRules=triggered,
                metrics={
                    "spend": r.spend,
                    "cpm": r.cpm,
                    "linkCtrPct": r.linkCtrPct,
                    "linkCpc": r.linkCpc,
                },
            )
        )

    warnings: list[str] = []
    if not rows:
        warnings.append(f"no_delivery_rows.{object_state.deliveryState}")
    if not event_mappings.landing_page_view_action_type:
        warnings.append("missing_event_mapping.landing_page_view_action_type")
    if not event_mappings.content_view_action_type:
        warnings.append("missing_event_mapping.content_view_action_type")
    if not event_mappings.add_to_cart_action_type:
        warnings.append("missing_event_mapping.add_to_cart_action_type")
    if not event_mappings.initiate_checkout_action_type:
        warnings.append("missing_event_mapping.initiate_checkout_action_type")
    if not event_mappings.purchase_action_type:
        warnings.append("missing_event_mapping.purchase_action_type")
    if not event_mappings.purchase_value_action_type:
        warnings.append("missing_event_mapping.purchase_value_action_type")

    applied_actions: list[MetaAppliedAction] = []
    if mode == "apply":
        for action in actions:
            request_payload: dict[str, Any]
            before: dict[str, Any]
            after: dict[str, Any] = {}
            target_entity_id = action.metaAdId
            try:
                if action.kind == "pause_ad":
                    before = client.get_object(
                        object_id=action.metaAdId,
                        fields="id,status,effective_status",
                        throttle_scope=ad_account_id,
                    )
                    request_payload = {"status": "PAUSED"}
                    after = client.update_ad(
                        ad_id=action.metaAdId,
                        payload=request_payload,
                        throttle_scope=ad_account_id,
                    )
                elif action.kind == "adjust_campaign_budget":
                    before = client.get_object(
                        object_id=campaign_id,
                        fields="id,daily_budget,lifetime_budget,status",
                        throttle_scope=ad_account_id,
                    )
                    request_payload = action.metrics.get("requestedChange") if isinstance(action.metrics, dict) else {}
                    if not isinstance(request_payload, dict) or not request_payload:
                        raise MetaMediaBuyingPlanError(
                            "adjust_campaign_budget action is missing metrics.requestedChange payload."
                        )
                    target_entity_id = campaign_id
                    after = client.update_campaign(
                        campaign_id=campaign_id,
                        payload=request_payload,
                        throttle_scope=ad_account_id,
                    )
                else:
                    raise MetaMediaBuyingPlanError(f"Unsupported apply action kind: {action.kind}")
            except MetaAdsError as exc:
                applied_actions.append(
                    MetaAppliedAction(
                        kind=action.kind,
                        metaEntityId=target_entity_id,
                        status="failed",
                        requestPayload=request_payload if "request_payload" in locals() else {},
                        before=before if "before" in locals() and isinstance(before, dict) else {},
                        after={},
                        error=str(exc),
                    )
                )
                continue

            applied_actions.append(
                MetaAppliedAction(
                    kind=action.kind,
                    metaEntityId=target_entity_id,
                    status="applied",
                    requestPayload=request_payload,
                    before=before if isinstance(before, dict) else {},
                    after=after if isinstance(after, dict) else {},
                    error=None,
                )
            )

    return MetaManagementPlan(
        mode=mode,
        generatedAt=_now_iso(),
        window={"datePreset": insights.datePreset},
        campaign=campaign,
        adsets=adsets,
        objectState=object_state,
        observedActionTypes={
            "actions": sorted(observed_actions),
            "action_values": sorted(observed_action_values),
        },
        rows=computed_rows,
        actions=actions,
        appliedActions=applied_actions,
        warnings=warnings,
        customMetricDefinitions=custom_metric_definitions,
        customMetricSummary=custom_metric_summary,
        customMetricRows=custom_metric_rows,
    )
