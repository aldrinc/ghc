#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from copy import deepcopy
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.base import session_scope
from app.db.enums import AssetStatusEnum
from app.db.models import Asset, Client, DesignSystem


_LOGO_PLACEHOLDER = "__LOGO_ASSET_PUBLIC_ID__"


def _get_logo_public_id(tokens: object) -> str | None:
    if not isinstance(tokens, dict):
        return None
    brand = tokens.get("brand")
    if not isinstance(brand, dict):
        return None
    value = brand.get("logoAssetPublicId")
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or cleaned == _LOGO_PLACEHOLDER:
        return None
    return cleaned


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill missing design_system.tokens.brand.logoAssetPublicId from the most recent approved "
            "asset tagged 'brand_logo' for the same org/client."
        )
    )
    parser.add_argument("--org-id", default=None)
    parser.add_argument("--client-id", default=None)
    parser.add_argument("--design-system-id", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--write", action="store_true", help="Apply changes (default is dry-run).")
    args = parser.parse_args()

    patched = 0
    missing_logo_asset = 0
    skipped = 0

    with session_scope() as session:
        stmt = select(DesignSystem).order_by(DesignSystem.created_at.desc())
        if args.org_id:
            stmt = stmt.where(DesignSystem.org_id == args.org_id)
        if args.client_id:
            stmt = stmt.where(DesignSystem.client_id == args.client_id)
        if args.design_system_id:
            stmt = stmt.where(DesignSystem.id == args.design_system_id)

        design_systems = list(session.scalars(stmt).all())
        for ds in design_systems:
            # Only client-bound design systems can be backfilled deterministically.
            if not ds.client_id:
                continue

            if _get_logo_public_id(ds.tokens) is not None:
                continue

            client = session.scalars(
                select(Client).where(Client.org_id == ds.org_id, Client.id == ds.client_id)
            ).first()
            if not client:
                skipped += 1
                continue

            asset = session.scalars(
                select(Asset)
                .where(
                    Asset.org_id == ds.org_id,
                    Asset.client_id == ds.client_id,
                    Asset.status == AssetStatusEnum.approved,
                    Asset.tags.contains(["brand_logo"]),
                )
                .order_by(Asset.created_at.desc())
            ).first()
            if not asset:
                missing_logo_asset += 1
                continue

            tokens = deepcopy(ds.tokens) if isinstance(ds.tokens, dict) else {}
            brand = tokens.get("brand")
            if not isinstance(brand, dict):
                # If brand isn't an object, we can't safely fix the rest of the schema here.
                skipped += 1
                continue

            brand["logoAssetPublicId"] = str(asset.public_id)
            if not isinstance(brand.get("logoAlt"), str) or not brand.get("logoAlt", "").strip():
                brand["logoAlt"] = str(client.name)
            if not isinstance(brand.get("name"), str) or not brand.get("name", "").strip():
                brand["name"] = str(client.name)

            if args.write:
                ds.tokens = tokens
                flag_modified(ds, "tokens")
                patched += 1

            if args.limit and patched >= args.limit:
                break

        if args.write and patched:
            session.commit()

    mode = "write" if args.write else "dry-run"
    print(
        f"mode={mode} patched={patched} missing_brand_logo_asset={missing_logo_asset} skipped={skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

