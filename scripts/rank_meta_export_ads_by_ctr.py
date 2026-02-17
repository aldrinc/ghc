from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "mos" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.services.meta_ads import MetaAdsClient  # noqa: E402


def _slugify(value: str) -> str:
    out: list[str] = []
    prev_dash = False
    for ch in value.strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
            continue
        if ch in (" ", "-", "_", ".", "/", "\\", "|", ":", ";", "[", "]", "(", ")", "{", "}", ","):
            if not prev_dash:
                out.append("-")
                prev_dash = True
            continue
    slug = "".join(out).strip("-")
    return slug or "ad"


def _fetch_all_pages(fetch_page, *, limit: int = 200) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = []
    after: Optional[str] = None
    seen: set[str] = set()
    while True:
        resp = fetch_page(limit=limit, after=after)
        page = resp.get("data") if isinstance(resp, dict) else None
        if page:
            data.extend(page)
        cursors = ((resp.get("paging") or {}).get("cursors") or {}) if isinstance(resp, dict) else {}
        nxt = cursors.get("after")
        if not nxt:
            break
        if nxt in seen:
            raise RuntimeError("Meta pagination cursor repeated; aborting to avoid an infinite loop.")
        seen.add(nxt)
        after = nxt
    return data


def _to_int(value: Any, *, field: str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    raise RuntimeError(f"Invalid {field}: {value!r}")


def _to_float(value: Any, *, field: str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as exc:
            raise RuntimeError(f"Invalid {field}: {value!r}") from exc
    raise RuntimeError(f"Invalid {field}: {value!r}")


@dataclass(frozen=True)
class RankedAd:
    rank: int
    ad_id: str
    ad_name: str
    ctr: Optional[float]
    impressions: Optional[int]
    clicks: Optional[int]
    spend: Optional[float]
    folder_name: str


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a single folder with exported Meta ads ranked by CTR."
    )
    parser.add_argument(
        "--export-dir",
        required=True,
        help="Path to a folder created by scripts/export_meta_campaign_ads.py",
    )
    parser.add_argument(
        "--date-preset",
        default="maximum",
        help="Meta Insights date_preset (default: maximum).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output dir (default: <export-dir>/ranked_by_ctr_<date_preset>).",
    )
    args = parser.parse_args()

    export_dir = Path(args.export_dir).resolve()
    if not export_dir.exists() or not export_dir.is_dir():
        raise SystemExit(f"--export-dir does not exist or is not a directory: {export_dir}")

    ads_path = export_dir / "ads.json"
    campaign_path = export_dir / "campaign.json"
    if not ads_path.exists():
        raise SystemExit(f"Missing {ads_path}. Expected an export folder.")
    if not campaign_path.exists():
        raise SystemExit(f"Missing {campaign_path}. Expected an export folder.")

    ads = json.loads(ads_path.read_text(encoding="utf-8"))
    campaign = json.loads(campaign_path.read_text(encoding="utf-8"))

    if not isinstance(ads, list):
        raise SystemExit(f"Invalid {ads_path}: expected a list.")
    if not isinstance(campaign, dict):
        raise SystemExit(f"Invalid {campaign_path}: expected an object.")

    campaign_id = campaign.get("id")
    if not isinstance(campaign_id, str) or not campaign_id:
        raise SystemExit(f"Invalid {campaign_path}: missing campaign id.")

    ad_account_id = settings.META_AD_ACCOUNT_ID
    if not ad_account_id:
        raise SystemExit("META_AD_ACCOUNT_ID is required to fetch insights.")

    client = MetaAdsClient.from_settings()

    # Fetch per-ad insights via account insights, filtered to this campaign.
    fields = "ad_id,ad_name,impressions,clicks,spend,ctr"
    filtering = json.dumps([{"field": "campaign.id", "operator": "EQUAL", "value": campaign_id}])

    def fetch_page(*, limit: int, after: Optional[str]) -> dict[str, Any]:
        params: dict[str, Any] = {
            "fields": fields,
            "level": "ad",
            "date_preset": args.date_preset,
            "filtering": filtering,
            "limit": limit,
        }
        if after:
            params["after"] = after
        return client._request("GET", f"act_{ad_account_id}/insights", params=params)

    insight_rows = _fetch_all_pages(fetch_page, limit=200)
    insights_by_ad_id: dict[str, dict[str, Any]] = {}
    for row in insight_rows:
        if not isinstance(row, dict):
            continue
        aid = row.get("ad_id")
        if isinstance(aid, str) and aid:
            insights_by_ad_id[aid] = row

    # Build and sort ranking list.
    delivered: list[tuple[float, int, str]] = []  # (-ctr, -impr, ad_id)
    missing: list[str] = []

    ad_name_by_id: dict[str, str] = {}
    for ad in ads:
        if not isinstance(ad, dict):
            raise SystemExit(f"Invalid {ads_path}: expected each entry to be an object.")
        ad_id = ad.get("id")
        if not isinstance(ad_id, str) or not ad_id:
            raise SystemExit(f"Invalid {ads_path}: ad missing id.")
        ad_name = ad.get("name") if isinstance(ad.get("name"), str) else ""
        ad_name_by_id[ad_id] = ad_name

        row = insights_by_ad_id.get(ad_id)
        if not row:
            missing.append(ad_id)
            continue

        ctr = _to_float(row.get("ctr"), field="ctr")
        impr = _to_int(row.get("impressions"), field="impressions")
        delivered.append((-ctr, -impr, ad_id))

    delivered.sort()
    missing.sort()

    ranked_ids = [ad_id for _ctr, _impr, ad_id in delivered] + missing

    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else (export_dir / f"ranked_by_ctr_{_slugify(args.date_preset)}")
    )
    if output_dir.exists():
        raise SystemExit(f"Refusing to overwrite existing output dir: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)

    ranking: list[RankedAd] = []

    for idx, ad_id in enumerate(ranked_ids, start=1):
        row = insights_by_ad_id.get(ad_id)
        ctr: Optional[float]
        impressions: Optional[int]
        clicks: Optional[int]
        spend: Optional[float]
        if row:
            ctr = _to_float(row.get("ctr"), field="ctr")
            impressions = _to_int(row.get("impressions"), field="impressions")
            clicks = _to_int(row.get("clicks"), field="clicks")
            spend = _to_float(row.get("spend"), field="spend")
        else:
            ctr = None
            impressions = None
            clicks = None
            spend = None

        ad_name = ad_name_by_id.get(ad_id) or ""
        ad_name_slug = _slugify(ad_name)[:50]

        ctr_part = f"ctr-{ctr:.2f}" if ctr is not None else "ctr-NA"
        impr_part = f"impr-{impressions}" if impressions is not None else "impr-NA"
        clicks_part = f"clicks-{clicks}" if clicks is not None else "clicks-NA"
        spend_part = f"spend-{spend:.2f}" if spend is not None else "spend-NA"

        folder_name = (
            f"{idx:03d}__{ctr_part}__{impr_part}__{clicks_part}__{spend_part}"
            f"__{ad_name_slug}__ad-{ad_id}"
        )
        dest_dir = output_dir / folder_name

        src_dir = export_dir / "ads" / ad_id
        if not src_dir.exists() or not src_dir.is_dir():
            raise SystemExit(f"Missing ad export folder for ad {ad_id}: {src_dir}")

        shutil.copytree(src_dir, dest_dir)

        if row:
            (dest_dir / "insights.json").write_text(
                json.dumps(row, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            (dest_dir / "insights.json").write_text(
                json.dumps({"ad_id": ad_id, "error": "no_insights_row"}, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        ranking.append(
            RankedAd(
                rank=idx,
                ad_id=ad_id,
                ad_name=ad_name,
                ctr=ctr,
                impressions=impressions,
                clicks=clicks,
                spend=spend,
                folder_name=folder_name,
            )
        )

    (output_dir / "ranking.json").write_text(
        json.dumps([r.__dict__ for r in ranking], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(str(output_dir))


if __name__ == "__main__":
    main()

