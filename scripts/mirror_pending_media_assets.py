from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "ghc-platform" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.db.base import SessionLocal  # noqa: E402
from app.db.enums import MediaMirrorStatusEnum  # noqa: E402
from app.db.models import MediaAsset  # noqa: E402
from app.services.media_mirror import MediaMirrorService  # noqa: E402


def main(batch_size: int) -> None:
    session = SessionLocal()
    mirror = MediaMirrorService(session)
    total = 0

    while True:
        batch = (
            session.query(MediaAsset)
            .filter(MediaAsset.mirror_status == MediaMirrorStatusEnum.pending)
            .limit(batch_size)
            .all()
        )
        if not batch:
            break
        mirror.mirror_assets(batch)
        total += len(batch)
        print(f"Mirrored batch of {len(batch)} (total: {total})")

    print(f"Done. Total assets mirrored: {total}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mirror pending media assets to object storage.")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size to process per loop.")
    args = parser.parse_args()
    main(batch_size=args.batch_size)
