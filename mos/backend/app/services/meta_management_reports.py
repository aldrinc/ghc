from __future__ import annotations

from typing import Any

from app.services.meta_media_buying import (
    MetaAdMetrics,
    MetaCustomMetricEvaluation,
    MetaManagementPlan,
)


_METRIC_LABELS = {
    "meta_atc_ratio_pct": "ATC Ratio",
    "meta_conversion_rate_pct": "Conversion Rate",
    "meta_ic_ratio_pct": "IC Ratio",
    "meta_purchase_ratio_pct": "Purchase Ratio",
    "meta_video_hold_rate_pct": "Video Hold Rate",
}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _fmt_money(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"${float(value):,.2f}"


def _fmt_int(value: int | None) -> str:
    if value is None:
        return "-"
    return f"{value:,}"


def _fmt_pct(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def _metric_map(plan: MetaManagementPlan) -> dict[str, MetaCustomMetricEvaluation]:
    return {metric.metricId: metric for metric in plan.customMetricSummary}


def _metric_line(metric: MetaCustomMetricEvaluation) -> str:
    label = _METRIC_LABELS.get(metric.metricId, metric.metricId)
    value = _fmt_pct(metric.value) if metric.unit == "pct" else str(metric.value or "-")
    parts = [f"- {label}: `{value}`", f"status `{metric.status}`"]
    if metric.numerator is not None and metric.denominator is not None:
        parts.append(f"source `{_fmt_int(metric.numerator)} / {_fmt_int(metric.denominator)}`")
    if metric.reason:
        parts.append(metric.reason)
    return " - ".join(parts)


def _plan_totals(rows: list[MetaAdMetrics]) -> dict[str, float | int | None]:
    impressions = sum(row.impressions for row in rows)
    spend = sum(row.spend for row in rows)
    clicks = sum(row.inlineLinkClicks or 0 for row in rows)
    cpm = (spend / impressions * 1000) if impressions > 0 else None
    ctr = (clicks / impressions * 100) if impressions > 0 else None
    cpc = (spend / clicks) if clicks > 0 else None
    return {
        "impressions": impressions,
        "spend": spend,
        "clicks": clicks,
        "cpm": cpm,
        "ctr": ctr,
        "cpc": cpc,
    }


def _worst_ads(rows: list[MetaAdMetrics]) -> list[MetaAdMetrics]:
    return sorted(
        rows,
        key=lambda row: (
            row.spend,
            row.linkCpc or 0,
            -(row.linkCtrPct or 0),
        ),
        reverse=True,
    )[:5]


def _scale_candidates(rows: list[MetaAdMetrics]) -> list[MetaAdMetrics]:
    candidates = [
        row
        for row in rows
        if row.spend >= 30
        and (row.linkCtrPct or 0) >= 2.0
        and (row.linkCpc is None or row.linkCpc <= 2.5)
        and row.cpm <= 50
    ]
    return sorted(
        candidates,
        key=lambda row: (row.linkCtrPct or 0, -row.linkCpc if row.linkCpc else 0),
        reverse=True,
    )[:5]


def _ad_line(row: MetaAdMetrics) -> str:
    name = _clean_text(row.adName) or row.adId
    return (
        f"- `{name}` (`{row.adId}`): spend `{_fmt_money(row.spend)}`, "
        f"impressions `{_fmt_int(row.impressions)}`, CTR `{_fmt_pct(row.linkCtrPct)}`, "
        f"CPC `{_fmt_money(row.linkCpc)}`, CPM `{_fmt_money(row.cpm)}`"
    )


def _funnel_recommendations(plan: MetaManagementPlan) -> list[str]:
    metrics = _metric_map(plan)
    recommendations: list[str] = []

    if plan.objectState.deliveryState != "delivering":
        recommendations.append(
            f"Review delivery state before judging performance: {plan.objectState.deliverySummary}"
        )
        return recommendations

    video_hold = metrics.get("meta_video_hold_rate_pct")
    if video_hold and video_hold.status == "below_target":
        recommendations.append(
            "Creative body is not holding attention. Review the opening claim, pacing, proof density, and creative format before scaling."
        )

    atc = metrics.get("meta_atc_ratio_pct")
    if atc and atc.status == "below_target":
        recommendations.append(
            "Landing/sales efficiency is below KPI. Revisit message match, offer clarity, proof, price framing, and CTA density."
        )

    ic = metrics.get("meta_ic_ratio_pct")
    if ic and ic.status == "below_target":
        recommendations.append(
            "Checkout-start rate is weak. Review whether the purchase section is visible, the selected offer is clear, and checkout entry is working."
        )
    elif ic and ic.status in {"unavailable", "insufficient_data"}:
        recommendations.append(
            "InitiateCheckout is not producing enough usable signal yet. Confirm Events Manager is receiving the event before using checkout-start analysis."
        )

    purchase_ratio = metrics.get("meta_purchase_ratio_pct")
    if purchase_ratio and purchase_ratio.status == "below_target":
        recommendations.append(
            "Purchases are not keeping up with cart or checkout intent. Investigate checkout friction, price shock, payment failures, shipping terms, and trust gaps."
        )

    conversion = metrics.get("meta_conversion_rate_pct")
    if conversion and conversion.status == "below_target":
        recommendations.append(
            "End-to-end conversion rate is below KPI. Do not scale spend until the weakest stage above is addressed."
        )

    if not recommendations:
        recommendations.append(
            "No critical funnel-stage issue was detected from Meta event data in this window."
        )
    return recommendations


def render_meta_management_report(plan: MetaManagementPlan) -> str:
    totals = _plan_totals(plan.rows)
    campaign_name = (
        _clean_text(plan.campaign.get("name"))
        or _clean_text(plan.campaign.get("id"))
        or "Meta campaign"
    )
    campaign_id = _clean_text(plan.campaign.get("id")) or "-"
    date_preset = _clean_text(plan.window.get("datePreset")) or "-"

    lines: list[str] = [
        "# Meta Management Report",
        "",
        f"- Generated at: `{plan.generatedAt}`",
        f"- Window: `{date_preset}`",
        f"- Campaign: `{campaign_name}`",
        f"- Meta campaign id: `{campaign_id}`",
        "",
        "## Delivery State",
        "",
        f"- State: `{plan.objectState.deliveryState}`",
        f"- Summary: {plan.objectState.deliverySummary}",
        f"- Campaign effective status: `{plan.objectState.campaignEffectiveStatus or plan.objectState.campaignStatus or '-'}`",
        f"- Ad sets: `{plan.objectState.adsetCount}`",
        f"- Ads: `{plan.objectState.adCount}`",
        f"- Ads with issues: `{plan.objectState.issueCount}`",
        f"- Review pending: `{plan.objectState.reviewPendingCount}`",
        "",
        "## Media Summary",
        "",
        f"- Spend: `{_fmt_money(totals['spend'] if isinstance(totals['spend'], (float, int)) else None)}`",
        f"- Impressions: `{_fmt_int(totals['impressions'] if isinstance(totals['impressions'], int) else None)}`",
        f"- Link clicks: `{_fmt_int(totals['clicks'] if isinstance(totals['clicks'], int) else None)}`",
        f"- Link CTR: `{_fmt_pct(totals['ctr'] if isinstance(totals['ctr'], (float, int)) else None)}`",
        f"- Link CPC: `{_fmt_money(totals['cpc'] if isinstance(totals['cpc'], (float, int)) else None)}`",
        f"- CPM: `{_fmt_money(totals['cpm'] if isinstance(totals['cpm'], (float, int)) else None)}`",
        "",
        "## Meta Events Manager Drop-Off",
        "",
    ]

    if plan.customMetricSummary:
        lines.extend(_metric_line(metric) for metric in plan.customMetricSummary)
    else:
        lines.append("- No Meta custom metric summary was available for this window.")

    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {recommendation}" for recommendation in _funnel_recommendations(plan))

    if plan.actions:
        lines.extend(["", "## Ad-Level Actions", ""])
        for action in plan.actions:
            lines.append(f"- `{action.kind}` on ad `{action.metaAdId}`: {action.reason}")
    else:
        lines.extend(
            ["", "## Ad-Level Actions", "", "- No pause actions triggered under the current rules."]
        )

    candidates = _scale_candidates(plan.rows)
    if candidates:
        lines.extend(["", "## Scale Candidates", ""])
        lines.extend(_ad_line(row) for row in candidates)

    if plan.rows:
        lines.extend(["", "## Ads To Review", ""])
        lines.extend(_ad_line(row) for row in _worst_ads(plan.rows))

    if plan.objectState.issueSamples:
        lines.extend(["", "## Issue Samples", ""])
        for issue in plan.objectState.issueSamples[:5]:
            label = _clean_text(issue.adName) or issue.adId
            summary = (
                _clean_text(issue.errorSummary)
                or _clean_text(issue.errorMessage)
                or "No Meta issue summary returned."
            )
            lines.append(f"- `{label}` (`{issue.adId}`): {summary}")

    if plan.warnings:
        lines.extend(["", "## Data Warnings", ""])
        lines.extend(f"- `{warning}`" for warning in plan.warnings)

    lines.extend(
        [
            "",
            "## Data Note",
            "",
            "This report uses Meta Ads API delivery data and Meta Events Manager action counts. Stage-level diagnosis is inference-based because Meta reports aggregated/estimated event data, not a user-level event ledger.",
        ]
    )
    return "\n".join(lines).strip() + "\n"
