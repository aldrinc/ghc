from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "ghc-platform" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.ads.types import NormalizedAsset  # noqa: E402
from app.db.base import SessionLocal  # noqa: E402
from app.db.enums import MediaAssetTypeEnum  # noqa: E402
from app.db.models import Ad, AdAssetLink  # noqa: E402
from app.db.repositories.ads import AdsRepository  # noqa: E402


def _assets_from_cards(raw_json: dict) -> list[NormalizedAsset]:
    snapshot = (raw_json or {}).get("snapshot") or {}
    cards = snapshot.get("cards") or []
    assets: list[NormalizedAsset] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        video_src = (
            card.get("video_hd_url")
            or card.get("video_sd_url")
            or card.get("watermarked_video_hd_url")
            or card.get("watermarked_video_sd_url")
        )
        image_src = (
            card.get("resized_image_url")
            or card.get("original_image_url")
            or card.get("watermarked_resized_image_url")
            or card.get("watermarked_original_image_url")
        )
        thumb = (
            card.get("video_preview_image_url")
            or card.get("thumbnail_url")
            or card.get("resized_image_url")
            or card.get("watermarked_resized_image_url")
            or card.get("original_image_url")
        )
        metadata = {"source": "meta_card", "raw": card}
        if thumb:
            metadata["preview_url"] = thumb

        if video_src:
            assets.append(
                NormalizedAsset(
                    asset_type=MediaAssetTypeEnum.VIDEO,
                    source_url=video_src,
                    metadata={**metadata, "source": "meta_card_video"},
                    role="PRIMARY",
                )
            )
        if image_src:
            assets.append(
                NormalizedAsset(
                    asset_type=MediaAssetTypeEnum.IMAGE,
                    source_url=image_src,
                    metadata={**metadata, "source": "meta_card_image"},
                    role="PRIMARY",
                )
            )
    return assets


def main(limit: int) -> None:
    session = SessionLocal()
    repo = AdsRepository(session)

    query = (
        session.query(Ad)
        .outerjoin(AdAssetLink, AdAssetLink.ad_id == Ad.id)
        .filter(AdAssetLink.id.is_(None))
        .order_by(Ad.created_at.desc())
    )
    if limit:
        query = query.limit(limit)

    ads = query.all()
    processed = 0
    linked_assets = 0

    for ad in ads:
        card_assets = _assets_from_cards(ad.raw_json)
        if not card_assets:
            continue
        for asset in card_assets:
            media_asset = repo._get_or_create_media_asset(channel=ad.channel, asset=asset)
            repo._link_ad_asset(ad_id=ad.id, media_asset_id=media_asset.id, role=asset.role)
            linked_assets += 1

        repo.session.flush()
        repo._ensure_creative_membership(ad)
        facts_payload, media_count = repo._upsert_ad_facts(ad)
        repo._upsert_ad_score(ad=ad, facts_payload=facts_payload, media_count=media_count)
        repo.session.commit()
        processed += 1
        if processed % 25 == 0:
            print(f"Processed {processed} ads so far; linked assets: {linked_assets}")

    print(f"Backfill complete. Ads updated: {processed}, assets linked: {linked_assets}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill missing ad media using snapshot.cards for ads without assets."
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit number of ads to process (0 means all).")
    args = parser.parse_args()
    main(limit=args.limit)
