from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "ghc-platform" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.db.base import SessionLocal  # noqa: E402
from app.db.repositories.ads import AdsRepository  # noqa: E402


def main(batch_size: int, org_id: str | None) -> None:
    session = SessionLocal()
    repo = AdsRepository(session)
    stats = repo.backfill_ad_scores(org_id=org_id, batch_size=batch_size)
    print(f"Backfill complete: {stats}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill ad_scores for existing ads.")
    parser.add_argument("--batch-size", type=int, default=500, help="Batch size for processing ads without scores.")
    parser.add_argument("--org-id", type=str, default=None, help="Limit backfill to a single org_id.")
    args = parser.parse_args()
    main(batch_size=args.batch_size, org_id=args.org_id)
