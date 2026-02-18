from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.services.meta_ads import MetaAdsClient, MetaAdsError


class MetaMediaBuyingPlanError(RuntimeError):
    pass


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
            raise MetaMediaBuyingPlanError(f"Invalid {field}: expected float-like value, got {value!r}") from exc
    raise MetaMediaBuyingPlanError(f"Invalid {field}: expected float-like value, got {value!r}")


def _parse_action_list(value: Any, *, field: str) -> dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, list):
        raise MetaMediaBuyingPlanError(f"Invalid {field}: expected a list, got {type(value).__name__}")
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
    # These are counts (should be ints), but Meta returns them as strings. Sum safely as ints.
    total = 0
    for k, v in action_map.items():
        _ = k
        total += int(v)
    return total


@dataclass(frozen=True)
class MetaEventMappings:
    content_view_action_type: Optional[str] = "offsite_conversion.fb_pixel_view_content"
    add_to_cart_action_type: Optional[str] = "offsite_conversion.fb_pixel_add_to_cart"
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


class MetaManagementPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    generatedAt: str
    window: dict[str, Any]
    campaign: dict[str, Any]
    adsets: list[dict[str, Any]]
    observedActionTypes: dict[str, list[str]] = Field(default_factory=dict)
    rows: list[MetaAdMetrics]
    actions: list[MetaPlannedAction]
    warnings: list[str] = Field(default_factory=list)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_meta_campaign_snapshot(
    *,
    client: MetaAdsClient,
    campaign_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
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
    campaign = client._request("GET", campaign_id, params={"fields": campaign_fields})

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
    adsets = client._request("GET", f"{campaign_id}/adsets", params={"fields": adsets_fields, "limit": 200}).get(
        "data"
    )
    if adsets is None:
        adsets_list: list[dict[str, Any]] = []
    elif isinstance(adsets, list):
        adsets_list = [row for row in adsets if isinstance(row, dict)]
    else:
        raise MetaMediaBuyingPlanError("Meta returned non-list adsets data.")

    return campaign, adsets_list


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
    while True:
        if after:
            params["after"] = after
        resp = client._request("GET", f"act_{ad_account_id}/insights", params=params)
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
    inline_link_clicks = (
        _to_int(inline_link_clicks_raw, field="inline_link_clicks") if inline_link_clicks_raw is not None else None
    )

    link_ctr_raw = row.get("inline_link_click_ctr")
    link_ctr_pct = _to_float(link_ctr_raw, field="inline_link_click_ctr") if link_ctr_raw is not None else None
    if link_ctr_pct is None and inline_link_clicks is not None and impressions > 0:
        # Meta sometimes omits derived rate fields when the numerator is 0; compute explicitly.
        link_ctr_pct = (inline_link_clicks / impressions) * 100.0
        warnings.append("computed_link_ctr_pct_from_counts")

    link_cpc_raw = row.get("cost_per_inline_link_click")
    link_cpc = _to_float(link_cpc_raw, field="cost_per_inline_link_click") if link_cpc_raw is not None else None
    if link_cpc is None and inline_link_clicks is not None and inline_link_clicks > 0:
        # Meta sometimes omits derived cost fields; compute explicitly.
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
    if mode == "apply":
        raise MetaMediaBuyingPlanError("mode=apply is not implemented yet. Use mode=plan_only.")

    client = MetaAdsClient.from_settings()
    try:
        campaign, adsets = fetch_meta_campaign_snapshot(client=client, campaign_id=campaign_id)
        rows = fetch_ad_level_insights(
            client=client,
            ad_account_id=ad_account_id,
            campaign_id=campaign_id,
            date_preset=insights.datePreset,
        )
    except MetaAdsError as exc:
        raise MetaMediaBuyingPlanError(str(exc)) from exc

    computed_rows: list[MetaAdMetrics] = []
    observed_actions: set[str] = set()
    observed_action_values: set[str] = set()
    for row in rows:
        observed_actions.update(_parse_action_list(row.get("actions"), field="actions").keys())
        observed_action_values.update(_parse_action_list(row.get("action_values"), field="action_values").keys())
        computed_rows.append(_compute_ad_metrics(row=row, event_mappings=event_mappings, include_raw=include_raw))

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
    if not event_mappings.content_view_action_type:
        warnings.append("missing_event_mapping.content_view_action_type")
    if not event_mappings.add_to_cart_action_type:
        warnings.append("missing_event_mapping.add_to_cart_action_type")
    if not event_mappings.purchase_action_type:
        warnings.append("missing_event_mapping.purchase_action_type")
    if not event_mappings.purchase_value_action_type:
        warnings.append("missing_event_mapping.purchase_value_action_type")

    return MetaManagementPlan(
        mode=mode,
        generatedAt=_now_iso(),
        window={"datePreset": insights.datePreset},
        campaign=campaign,
        adsets=adsets,
        observedActionTypes={
            "actions": sorted(observed_actions),
            "action_values": sorted(observed_action_values),
        },
        rows=computed_rows,
        actions=actions,
        warnings=warnings,
    )
