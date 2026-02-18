from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "mos" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.services.meta_media_buying import (  # noqa: E402
    MetaCutRuleConfig,
    MetaEventMappings,
    MetaInsightsConfig,
    build_management_plan,
)


def _money(value: Any) -> str:
    if value is None:
        return "NA"
    try:
        return f"${float(value):.2f}"
    except Exception:
        return "NA"


def _pct(value: Any) -> str:
    if value is None:
        return "NA"
    try:
        return f"{float(value):.2f}%"
    except Exception:
        return "NA"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a plan-only Meta media buying action plan.")
    parser.add_argument("--meta-campaign-id", required=True, help="Meta campaign id (e.g. 120...).")
    parser.add_argument("--ad-account-id", default=None, help="Meta ad account id (default: META_AD_ACCOUNT_ID).")
    parser.add_argument("--date-preset", default="last_3d", help="Meta Insights date_preset (default: last_3d).")

    parser.add_argument(
        "--content-view-action-type",
        default="offsite_conversion.fb_pixel_view_content",
        help="Action type key for Content Views.",
    )
    parser.add_argument(
        "--add-to-cart-action-type",
        default="offsite_conversion.fb_pixel_add_to_cart",
        help="Action type key for Add To Cart.",
    )
    parser.add_argument(
        "--purchase-action-type",
        default="offsite_conversion.fb_pixel_purchase",
        help="Action type key for Purchases (count).",
    )
    parser.add_argument(
        "--purchase-value-action-type",
        default="offsite_conversion.fb_pixel_purchase",
        help="Action type key for Purchases (value).",
    )

    args = parser.parse_args()

    ad_account_id = args.ad_account_id or settings.META_AD_ACCOUNT_ID
    if not ad_account_id:
        raise SystemExit("META_AD_ACCOUNT_ID is required (or pass --ad-account-id).")

    plan = build_management_plan(
        ad_account_id=ad_account_id,
        campaign_id=args.meta_campaign_id,
        mode="plan_only",
        insights=MetaInsightsConfig(datePreset=args.date_preset),
        cut_rules=MetaCutRuleConfig(),
        event_mappings=MetaEventMappings(
            content_view_action_type=args.content_view_action_type,
            add_to_cart_action_type=args.add_to_cart_action_type,
            purchase_action_type=args.purchase_action_type,
            purchase_value_action_type=args.purchase_value_action_type,
        ),
    )

    camp = plan.campaign or {}
    print("# Meta Media Buying Plan (Dry Run)\n")
    print(f"- Window: `{json.dumps(plan.window, sort_keys=True)}`")
    print(f"- Campaign: `{camp.get('id')}` {camp.get('name')!r}")
    print(f"- Objective: `{camp.get('objective')}`")
    print(f"- Status: `{camp.get('status')}` (effective: `{camp.get('effective_status')}`)")
    print(
        "- Event mappings: "
        f"`{json.dumps({'content_view': args.content_view_action_type, 'add_to_cart': args.add_to_cart_action_type, 'purchase': args.purchase_action_type, 'purchase_value': args.purchase_value_action_type}, sort_keys=True)}`"
    )
    if camp.get("daily_budget") is not None:
        print(f"- Daily Budget (raw minor units): `{camp.get('daily_budget')}`")
    observed = plan.observedActionTypes or {}
    if observed:
        print(f"- Observed action_type keys: `{json.dumps(observed, sort_keys=True)}`")
    if plan.warnings:
        print(f"- Warnings: `{json.dumps(plan.warnings)}`")

    print("\n## Planned Actions\n")
    if not plan.actions:
        print("No actions triggered by cut rules in this window.")
    else:
        for action in plan.actions:
            print(f"- {action.kind}: ad `{action.metaAdId}` ({action.reason})")

    print("\n## Ad Metrics (First 20)\n")
    headers = ["adId", "spend", "cpm", "linkCtr", "linkCpc", "hookRate", "holdRate"]
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join(["---"] * len(headers)) + "|")
    for row in plan.rows[:20]:
        print(
            "| "
            + " | ".join(
                [
                    row.adId,
                    _money(row.spend),
                    _money(row.cpm),
                    _pct(row.linkCtrPct),
                    _money(row.linkCpc),
                    _pct(row.hookRatePct),
                    _pct(row.holdRatePct),
                ]
            )
            + " |"
        )


if __name__ == "__main__":
    main()
