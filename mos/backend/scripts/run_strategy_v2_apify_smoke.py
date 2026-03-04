#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _load_env() -> None:
    script_path = Path(__file__).resolve()
    backend_root = script_path.parents[1]
    project_root = script_path.parents[3]
    load_dotenv(project_root / ".env", override=False)
    load_dotenv(project_root / ".env.local.consolidated", override=False)
    load_dotenv(backend_root / ".env", override=False)


def _default_source_urls() -> dict[str, str]:
    return {
        "meta": os.getenv("STRATEGY_V2_SMOKE_META_URL", "https://www.facebook.com/duolingo"),
        "tiktok": os.getenv("STRATEGY_V2_SMOKE_TIKTOK_URL", "https://www.tiktok.com/@duolingo"),
        "instagram": os.getenv("STRATEGY_V2_SMOKE_INSTAGRAM_URL", "https://www.instagram.com/duolingo/"),
        "youtube": os.getenv("STRATEGY_V2_SMOKE_YOUTUBE_URL", "https://www.youtube.com/@duolingo"),
        "reddit": os.getenv(
            "STRATEGY_V2_SMOKE_REDDIT_URL",
            "https://www.reddit.com/r/herbalism/comments/1expmex",
        ),
        "web": os.getenv(
            "STRATEGY_V2_SMOKE_WEB_URL",
            "https://offer.ancientremediesrevived.com/c3-nb",
        ),
    }


def _default_allowed_actor_ids() -> str:
    return ",".join(
        [
            "curious_coder~facebook-ads-library-scraper",
            "clockworks/tiktok-scraper",
            "apify/instagram-scraper",
            "streamers/youtube-scraper",
            "practicaltools/apify-reddit-api",
            "apify/web-scraper",
            "apify/google-search-scraper",
            "emastra/trustpilot-scraper",
            "junglee/amazon-reviews-scraper",
        ]
    )


def _configure_smoke_env(args: argparse.Namespace) -> None:
    os.environ["STRATEGY_V2_APIFY_ENABLED"] = "true"
    os.environ["STRATEGY_V2_APIFY_MAX_ITEMS_PER_DATASET"] = str(args.max_items)
    os.environ["STRATEGY_V2_APIFY_MAX_WAIT_SECONDS"] = str(args.max_wait_seconds)
    os.environ["STRATEGY_V2_APIFY_MAX_ACTOR_RUNS"] = str(args.max_actor_runs)

    if args.allowed_actor_ids:
        os.environ["STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS"] = args.allowed_actor_ids
    elif not (os.getenv("STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS") or "").strip():
        os.environ["STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS"] = _default_allowed_actor_ids()

    # Respect explicit env overrides if already set.
    os.environ.setdefault("STRATEGY_V2_APIFY_TIKTOK_ACTOR_ID", "clockworks/tiktok-scraper")
    os.environ.setdefault("STRATEGY_V2_APIFY_INSTAGRAM_ACTOR_ID", "apify/instagram-scraper")
    os.environ.setdefault("STRATEGY_V2_APIFY_YOUTUBE_ACTOR_ID", "streamers/youtube-scraper")
    os.environ.setdefault("STRATEGY_V2_APIFY_REDDIT_ACTOR_ID", "practicaltools/apify-reddit-api")
    os.environ.setdefault("STRATEGY_V2_APIFY_WEB_ACTOR_ID", "apify/web-scraper")


def _preflight_actor_access(*, token: str, actor_ids: list[str]) -> dict[str, bool]:
    statuses: dict[str, bool] = {}
    for actor_id in actor_ids:
        encoded_actor_id = quote(actor_id, safe="~")
        response = httpx.get(
            f"https://api.apify.com/v2/acts/{encoded_actor_id}",
            params={"token": token},
            timeout=30,
        )
        statuses[actor_id] = response.status_code == 200
    return statuses


def _case_matrix(source_urls: dict[str, str]) -> dict[str, list[str]]:
    # Production-like smoke: every case includes ads + video + external VOC sources.
    return {
        "meta": [source_urls["meta"], source_urls["tiktok"], source_urls["web"]],
        "tiktok": [source_urls["meta"], source_urls["tiktok"], source_urls["web"]],
        "instagram": [source_urls["meta"], source_urls["instagram"], source_urls["web"]],
        "youtube": [source_urls["meta"], source_urls["youtube"], source_urls["web"]],
        "reddit": [source_urls["meta"], source_urls["tiktok"], source_urls["reddit"], source_urls["web"]],
        "web": [source_urls["meta"], source_urls["tiktok"], source_urls["web"]],
    }


def _parse_cases(raw_cases: str | None) -> list[str]:
    ordered = ["meta", "tiktok", "instagram", "youtube", "reddit", "web"]
    if raw_cases is None or not raw_cases.strip():
        return ordered
    selected = [item.strip().lower() for item in raw_cases.split(",") if item.strip()]
    unknown = [item for item in selected if item not in ordered]
    if unknown:
        raise RuntimeError(f"Unknown smoke case(s): {unknown}. Valid cases: {ordered}")
    return selected


def _actor_for_case(*, case_name: str, config: Any) -> str:
    if case_name == "meta":
        return str(config.meta_actor_id)
    if case_name == "tiktok":
        return str(config.tiktok_actor_id)
    if case_name == "instagram":
        return str(config.instagram_actor_id)
    if case_name == "youtube":
        return str(config.youtube_actor_id)
    if case_name == "reddit":
        return str(config.reddit_actor_id)
    if case_name == "web":
        return str(config.web_actor_id)
    raise RuntimeError(f"Unsupported case: {case_name}")


def _actors_for_source_refs(*, source_refs: list[str], config: Any) -> set[str]:
    actor_ids: set[str] = {str(config.meta_actor_id), str(config.web_actor_id)}
    lowered_refs = [ref.lower() for ref in source_refs]
    if any("tiktok.com" in ref for ref in lowered_refs):
        actor_ids.add(str(config.tiktok_actor_id))
    if any("instagram.com" in ref for ref in lowered_refs):
        actor_ids.add(str(config.instagram_actor_id))
    if any("youtube.com" in ref or "youtu.be" in ref for ref in lowered_refs):
        actor_ids.add(str(config.youtube_actor_id))
    if any("reddit.com" in ref for ref in lowered_refs):
        actor_ids.add(str(config.reddit_actor_id))
    return actor_ids


def _run_case(
    *,
    case_name: str,
    source_refs: list[str],
    expected_actor_id: str,
    run_strategy_v2_apify_ingestion: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "case": case_name,
        "source_refs": source_refs,
        "expected_actor_id": expected_actor_id,
        "status": "passed",
    }
    try:
        payload = run_strategy_v2_apify_ingestion(
            source_refs=source_refs,
            include_ads_context=True,
            include_social_video=True,
            include_external_voc=True,
        )
    except Exception as exc:  # noqa: BLE001
        result["status"] = "failed"
        result["error"] = str(exc)
        return result

    raw_runs = payload.get("raw_runs")
    candidate_assets = payload.get("candidate_assets")
    social_videos = payload.get("social_video_observations")
    external_voc = payload.get("external_voc_corpus")
    proof_candidates = payload.get("proof_asset_candidates")
    summary = payload.get("summary")

    actor_ids = [
        str(row.get("actor_id"))
        for row in (raw_runs if isinstance(raw_runs, list) else [])
        if isinstance(row, dict) and isinstance(row.get("actor_id"), str)
    ]
    run_items_by_actor: dict[str, int] = {}
    for row in raw_runs if isinstance(raw_runs, list) else []:
        if not isinstance(row, dict):
            continue
        actor_id = str(row.get("actor_id") or "").strip()
        items = row.get("items")
        run_items_by_actor[actor_id] = len(items) if isinstance(items, list) else 0

    candidate_platforms = [
        str(row.get("platform") or "").upper()
        for row in (candidate_assets if isinstance(candidate_assets, list) else [])
        if isinstance(row, dict)
    ]
    has_video_context = (
        isinstance(social_videos, list)
        and len(social_videos) > 0
    ) or any(platform in {"TIKTOK", "INSTAGRAM", "YOUTUBE"} for platform in candidate_platforms)

    checks = {
        "expected_actor_run_present": expected_actor_id in actor_ids,
        "ads_context_present": isinstance(payload.get("ads_context"), str) and bool(str(payload.get("ads_context")).strip()),
        "video_context_present": has_video_context,
        "external_voc_present": isinstance(external_voc, list) and len(external_voc) > 0,
        "proof_candidates_present": isinstance(proof_candidates, list) and len(proof_candidates) > 0,
        "workflow_context_contract": (
            isinstance(payload.get("ads_context"), str)
            and isinstance(social_videos, list)
            and isinstance(external_voc, list)
            and isinstance(proof_candidates, list)
            and isinstance(summary, dict)
        ),
    }
    result.update(
        {
            "checks": checks,
            "actor_ids": actor_ids,
            "run_items_by_actor": run_items_by_actor,
            "counts": {
                "candidate_assets": len(candidate_assets) if isinstance(candidate_assets, list) else 0,
                "social_video_observations": len(social_videos) if isinstance(social_videos, list) else 0,
                "external_voc_corpus": len(external_voc) if isinstance(external_voc, list) else 0,
                "proof_asset_candidates": len(proof_candidates) if isinstance(proof_candidates, list) else 0,
            },
            "summary": summary,
        }
    )
    if not all(checks.values()):
        result["status"] = "failed"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run low-volume Strategy V2 Apify smoke matrix.")
    parser.add_argument(
        "--cases",
        type=str,
        default=None,
        help="Comma-separated subset: meta,tiktok,instagram,youtube,reddit,web",
    )
    parser.add_argument("--max-items", type=int, default=2)
    parser.add_argument("--max-wait-seconds", type=int, default=300)
    parser.add_argument("--max-actor-runs", type=int, default=6)
    parser.add_argument(
        "--allowed-actor-ids",
        type=str,
        default=None,
        help="Optional comma-separated allowlist override.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="artifact-downloads/strategy_v2_apify_smoke_report.json",
    )
    args = parser.parse_args()

    _load_env()
    _configure_smoke_env(args)

    token = str(os.getenv("APIFY_API_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("APIFY_API_TOKEN is required for smoke tests.")

    from app.strategy_v2.apify_ingestion import (  # pylint: disable=import-outside-toplevel
        load_strategy_v2_apify_config,
        run_strategy_v2_apify_ingestion,
    )

    config = load_strategy_v2_apify_config()
    cases = _parse_cases(args.cases)
    source_urls = _default_source_urls()
    matrix = _case_matrix(source_urls)

    required_actor_ids: set[str] = set()
    for case_name in cases:
        required_actor_ids.update(_actors_for_source_refs(source_refs=matrix[case_name], config=config))
    required_actor_ids = sorted(required_actor_ids)
    actor_access = _preflight_actor_access(token=token, actor_ids=required_actor_ids)
    inaccessible = [actor_id for actor_id, accessible in actor_access.items() if not accessible]
    if inaccessible:
        raise RuntimeError(
            "Smoke preflight failed. The following actors are inaccessible with current token/config: "
            f"{inaccessible}"
        )

    case_results: list[dict[str, Any]] = []
    for case_name in cases:
        case_results.append(
            _run_case(
                case_name=case_name,
                source_refs=matrix[case_name],
                expected_actor_id=_actor_for_case(case_name=case_name, config=config),
                run_strategy_v2_apify_ingestion=run_strategy_v2_apify_ingestion,
            )
        )

    passed_count = len([row for row in case_results if row.get("status") == "passed"])
    overall_status = "passed" if passed_count == len(case_results) else "failed"
    report = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "passed_cases": passed_count,
        "total_cases": len(case_results),
        "config": {
            "max_items_per_dataset": config.max_items_per_dataset,
            "max_wait_seconds": config.max_wait_seconds,
            "max_actor_runs": config.max_actor_runs,
            "meta_actor_id": config.meta_actor_id,
            "tiktok_actor_id": config.tiktok_actor_id,
            "instagram_actor_id": config.instagram_actor_id,
            "youtube_actor_id": config.youtube_actor_id,
            "reddit_actor_id": config.reddit_actor_id,
            "web_actor_id": config.web_actor_id,
        },
        "actor_preflight": actor_access,
        "cases": case_results,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n")

    for row in case_results:
        checks = row.get("checks") if isinstance(row.get("checks"), dict) else {}
        print(
            f"[{row.get('status','failed').upper()}] {row.get('case')}: "
            f"actors={row.get('actor_ids', [])} checks_passed="
            f"{sum(1 for value in checks.values() if value)}/{len(checks)}"
        )
    print(f"report_path={output_path}")
    print(f"overall_status={overall_status}")
    return 0 if overall_status == "passed" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
