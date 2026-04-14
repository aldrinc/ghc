#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import SessionLocal
from app.db.models import Campaign
from app.services.campaign_creative_context import (
    ensure_campaign_creative_context_ready,
    persist_manual_campaign_creative_context,
)
from app.services.ember_import_adapter import build_ember_manual_creative_context_request


DEFAULT_EMBER_PATH = (
    Path(__file__).resolve().parents[4]
    / "mos_strategy_v3"
    / "FutrGroup-Hookd-Project"
    / "EMBER"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and optionally persist the phase-one EMBER manual creative context adapter payload."
    )
    parser.add_argument(
        "--ember-path",
        default=str(DEFAULT_EMBER_PATH),
        help="Path to the EMBER artifact folder or the mos_strategy_v3 workspace root.",
    )
    parser.add_argument(
        "--campaign-id",
        help="Campaign id to persist into. If omitted, the script only validates and prints the payload.",
    )
    parser.add_argument(
        "--experiment-id",
        help="Optional override for the generated experiment id.",
    )
    parser.add_argument(
        "--experiment-name",
        help="Optional override for the generated experiment name.",
    )
    parser.add_argument(
        "--variant-id",
        help="Optional override for the generated variant id.",
    )
    parser.add_argument(
        "--variant-name",
        help="Optional override for the generated variant name.",
    )
    parser.add_argument(
        "--channel",
        default="facebook",
        help="Channel attached to the generated experiment variant. Default: facebook",
    )
    parser.add_argument(
        "--created-by-user",
        default="script:ember-import",
        help="created_by_user value stored on generated artifacts.",
    )
    parser.add_argument(
        "--output",
        help="Optional file path to write the validated JSON payload.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    return parser.parse_args()


def _load_campaign(session, campaign_id: str) -> Campaign:
    campaign = session.scalar(select(Campaign).where(Campaign.id == campaign_id))
    if campaign is None:
        raise SystemExit(f"Campaign not found: {campaign_id}")
    if campaign.product_id is None:
        raise SystemExit("Selected campaign is missing product_id. Attach a product before importing manual context.")
    return campaign


def main() -> None:
    args = _parse_args()
    request = build_ember_manual_creative_context_request(
        args.ember_path,
        experiment_id=args.experiment_id,
        experiment_name=args.experiment_name,
        variant_id=args.variant_id,
        variant_name=args.variant_name,
        channel=args.channel,
    )
    payload = request.model_dump(mode="json", by_alias=True)

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2 if args.pretty else None) + "\n",
            encoding="utf-8",
        )

    if not args.campaign_id:
        print(json.dumps(payload, indent=2 if args.pretty else None))
        return

    session = SessionLocal()
    try:
        campaign = _load_campaign(session, args.campaign_id)
        response = persist_manual_campaign_creative_context(
            session=session,
            org_id=str(campaign.org_id),
            campaign=campaign,
            payload=request,
            created_by_user=args.created_by_user,
        )
        readiness = ensure_campaign_creative_context_ready(
            session=session,
            org_id=str(campaign.org_id),
            campaign=campaign,
        )
        result = {
            "campaignId": str(campaign.id),
            "campaignName": campaign.name,
            "creativeContextArtifactId": response["creativeContextArtifactId"],
            "artifactIds": response["artifactIds"],
            "uploadedDocKeys": response["uploadedDocKeys"],
            "readiness": readiness,
        }
        print(json.dumps(result, indent=2 if args.pretty else None))
    finally:
        session.close()


if __name__ == "__main__":
    main()
