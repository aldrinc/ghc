from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    ClientSwipeAsset,
    CompanySwipeAsset,
    CompanySwipeBrand,
    CompanySwipeMedia,
    SwipeCollection,
    SwipeCollectionItem,
)

DEFAULT_SWIPE_COLLECTION_KIND = "default"
DEFAULT_SWIPE_COLLECTION_NAME = "Default"
GETHOOKD_INBOX_KIND = "gethookd_inbox"
GETHOOKD_INBOX_NAME = "GetHookd"
GETHOOKD_ORIGIN_SYSTEM = "gethookd_public_api"
WRITABLE_SWIPE_COLLECTION_KINDS = {"uploaded", "curated"}

# Review status constants
REVIEW_STATUS_PENDING = "pending_review"
REVIEW_STATUS_APPROVED = "approved"
REVIEW_STATUS_REJECTED = "rejected"
REVIEW_STATUS_STALE = "stale_after_sync"


class CompanySwipesRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_assets(
        self,
        *,
        org_id: str,
        limit: int = 50,
        offset: int = 0,
        collection_id: str | None = None,
        origin_system: str | None = None,
        review_status: str | None = None,
        changed_since: datetime | None = None,
    ) -> list[CompanySwipeAsset]:
        stmt = select(CompanySwipeAsset).where(CompanySwipeAsset.org_id == org_id)

        if collection_id:
            stmt = stmt.join(
                SwipeCollectionItem,
                SwipeCollectionItem.swipe_asset_id == CompanySwipeAsset.id,
            ).where(
                SwipeCollectionItem.org_id == org_id,
                SwipeCollectionItem.collection_id == collection_id,
            )

        if origin_system:
            stmt = stmt.where(CompanySwipeAsset.origin_system == origin_system)

        if review_status:
            stmt = stmt.where(CompanySwipeAsset.review_status == review_status)

        if changed_since:
            stmt = stmt.where(CompanySwipeAsset.source_last_synced_at >= changed_since)

        stmt = stmt.order_by(CompanySwipeAsset.created_at.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt).all())

    def get_asset(self, org_id: str, swipe_id: str) -> CompanySwipeAsset | None:
        stmt = select(CompanySwipeAsset).where(
            CompanySwipeAsset.org_id == org_id,
            CompanySwipeAsset.id == swipe_id,
        )
        return self.session.scalars(stmt).first()

    def get_asset_by_external_id(
        self,
        *,
        org_id: str,
        origin_system: str,
        external_ad_id: str,
    ) -> CompanySwipeAsset | None:
        stmt = select(CompanySwipeAsset).where(
            CompanySwipeAsset.org_id == org_id,
            CompanySwipeAsset.origin_system == origin_system,
            CompanySwipeAsset.external_ad_id == external_ad_id,
        )
        return self.session.scalars(stmt).first()

    def create_asset(self, **fields) -> CompanySwipeAsset:
        swipe = CompanySwipeAsset(**fields)
        self.session.add(swipe)
        self.session.flush()
        return swipe

    def update_asset(self, *, org_id: str, swipe_id: str, **fields) -> CompanySwipeAsset | None:
        swipe = self.get_asset(org_id=org_id, swipe_id=swipe_id)
        if swipe is None:
            return None
        for key, value in fields.items():
            setattr(swipe, key, value)
        self.session.flush()
        return swipe

    def set_review_status(
        self,
        *,
        org_id: str,
        swipe_id: str,
        review_status: str,
        reviewed_by_user_id: Optional[str] = None,
    ) -> Optional[CompanySwipeAsset]:
        """Set review status on a swipe asset."""
        now = datetime.now(timezone.utc)
        return self.update_asset(
            org_id=org_id,
            swipe_id=swipe_id,
            review_status=review_status,
            reviewed_at=now,
            reviewed_by_user_id=reviewed_by_user_id,
        )

    def approve_asset(
        self,
        *,
        org_id: str,
        swipe_id: str,
        reviewed_by_user_id: Optional[str] = None,
    ) -> Optional[CompanySwipeAsset]:
        """Approve an asset and clear stale status if present."""
        return self.set_review_status(
            org_id=org_id,
            swipe_id=swipe_id,
            review_status=REVIEW_STATUS_APPROVED,
            reviewed_by_user_id=reviewed_by_user_id,
        )

    def reject_asset(
        self,
        *,
        org_id: str,
        swipe_id: str,
        reviewed_by_user_id: Optional[str] = None,
    ) -> Optional[CompanySwipeAsset]:
        """Reject an asset - preserves canonical row."""
        return self.set_review_status(
            org_id=org_id,
            swipe_id=swipe_id,
            review_status=REVIEW_STATUS_REJECTED,
            reviewed_by_user_id=reviewed_by_user_id,
        )

    def mark_pending(
        self,
        *,
        org_id: str,
        swipe_id: str,
    ) -> Optional[CompanySwipeAsset]:
        """Mark asset back to pending review."""
        return self.set_review_status(
            org_id=org_id,
            swipe_id=swipe_id,
            review_status=REVIEW_STATUS_PENDING,
        )

    def create_media(self, **fields) -> CompanySwipeMedia:
        media = CompanySwipeMedia(**fields)
        self.session.add(media)
        self.session.flush()
        return media

    def list_brands(self, org_id: str) -> list[CompanySwipeBrand]:
        stmt = select(CompanySwipeBrand).where(CompanySwipeBrand.org_id == org_id)
        return list(self.session.scalars(stmt).all())

    def upsert_brand(
        self,
        *,
        org_id: str,
        external_brand_id: str,
        name: str,
        logo_url: Optional[str] = None,
        ad_library_link: Optional[str] = None,
    ) -> CompanySwipeBrand:
        existing = self.session.scalar(
            select(CompanySwipeBrand).where(
                CompanySwipeBrand.org_id == org_id,
                CompanySwipeBrand.external_brand_id == external_brand_id,
            )
        )
        if existing:
            existing.name = name
            if logo_url and not existing.logo_url:
                existing.logo_url = logo_url
            if ad_library_link and not existing.ad_library_link:
                existing.ad_library_link = ad_library_link
            self.session.flush()
            return existing

        brand = CompanySwipeBrand(
            org_id=org_id,
            external_brand_id=external_brand_id,
            name=name,
            logo_url=logo_url,
            ad_library_link=ad_library_link,
        )
        self.session.add(brand)
        self.session.flush()
        return brand

    def list_media(self, org_id: str, swipe_asset_id: str) -> list[CompanySwipeMedia]:
        stmt = (
            select(CompanySwipeMedia)
            .where(
                CompanySwipeMedia.org_id == org_id,
                CompanySwipeMedia.swipe_asset_id == swipe_asset_id,
            )
            .order_by(CompanySwipeMedia.created_at.asc())
        )
        return list(self.session.scalars(stmt).all())

    def list_media_for_assets(
        self, *, org_id: str, swipe_asset_ids: Iterable[str]
    ) -> dict[str, list[CompanySwipeMedia]]:
        ids = [swipe_asset_id for swipe_asset_id in swipe_asset_ids if swipe_asset_id]
        if not ids:
            return {}
        stmt = (
            select(CompanySwipeMedia)
            .where(
                CompanySwipeMedia.org_id == org_id,
                CompanySwipeMedia.swipe_asset_id.in_(ids),
            )
            .order_by(CompanySwipeMedia.created_at.asc())
        )
        grouped: dict[str, list[CompanySwipeMedia]] = defaultdict(list)
        for media in self.session.scalars(stmt).all():
            grouped[str(media.swipe_asset_id)].append(media)
        return dict(grouped)


class SwipeCollectionsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def ensure_default_collection(self, *, org_id: str) -> SwipeCollection:
        collection = self.get_by_kind(org_id=org_id, kind=DEFAULT_SWIPE_COLLECTION_KIND)
        if collection is None:
            collection = SwipeCollection(
                org_id=org_id,
                name=DEFAULT_SWIPE_COLLECTION_NAME,
                kind=DEFAULT_SWIPE_COLLECTION_KIND,
            )
            self.session.add(collection)
            self.session.flush()

        # Exclude GetHookd origin assets from default collection
        catalog_asset_ids = {
            str(asset_id)
            for asset_id in self.session.scalars(
                select(CompanySwipeAsset.id).where(
                    CompanySwipeAsset.org_id == org_id,
                    CompanySwipeAsset.source_kind != "upload",
                    CompanySwipeAsset.origin_system != GETHOOKD_ORIGIN_SYSTEM,
                )
            ).all()
        }
        existing_ids = {
            str(asset_id)
            for asset_id in self.session.scalars(
                select(SwipeCollectionItem.swipe_asset_id).where(
                    SwipeCollectionItem.org_id == org_id,
                    SwipeCollectionItem.collection_id == collection.id,
                )
            ).all()
        }
        missing_ids = sorted(catalog_asset_ids - existing_ids)
        for swipe_asset_id in missing_ids:
            self.session.add(
                SwipeCollectionItem(
                    org_id=org_id,
                    collection_id=collection.id,
                    swipe_asset_id=swipe_asset_id,
                )
            )
        if missing_ids:
            self.session.flush()
        self.session.commit()
        self.session.refresh(collection)
        return collection

    def ensure_gethookd_collection(self, *, org_id: str) -> SwipeCollection:
        """Ensure the system-managed GetHookd inbox collection exists."""
        collection = self.get_by_kind(org_id=org_id, kind=GETHOOKD_INBOX_KIND)
        if collection is None:
            collection = SwipeCollection(
                org_id=org_id,
                name=GETHOOKD_INBOX_NAME,
                kind=GETHOOKD_INBOX_KIND,
            )
            self.session.add(collection)
            self.session.flush()
            self.session.commit()
            self.session.refresh(collection)
        return collection

    def add_item_if_missing(
        self,
        *,
        org_id: str,
        collection_id: str,
        swipe_asset_id: str,
    ) -> bool:
        """Add a single asset to a collection if not already present."""
        existing = self.session.scalar(
            select(SwipeCollectionItem).where(
                SwipeCollectionItem.org_id == org_id,
                SwipeCollectionItem.collection_id == collection_id,
                SwipeCollectionItem.swipe_asset_id == swipe_asset_id,
            )
        )
        if existing:
            return False
        self.session.add(
            SwipeCollectionItem(
                org_id=org_id,
                collection_id=collection_id,
                swipe_asset_id=swipe_asset_id,
            )
        )
        self.session.commit()
        return True

    def list(self, *, org_id: str) -> list[SwipeCollection]:
        self.ensure_default_collection(org_id=org_id)
        stmt = (
            select(SwipeCollection)
            .where(SwipeCollection.org_id == org_id)
            .order_by(
                SwipeCollection.kind.asc(),
                SwipeCollection.created_at.asc(),
            )
        )
        return list(self.session.scalars(stmt).all())

    def get(self, *, org_id: str, collection_id: str) -> SwipeCollection | None:
        if not collection_id:
            return None
        self.ensure_default_collection(org_id=org_id)
        stmt = select(SwipeCollection).where(
            SwipeCollection.org_id == org_id,
            SwipeCollection.id == collection_id,
        )
        return self.session.scalars(stmt).first()

    def get_by_kind(self, *, org_id: str, kind: str) -> SwipeCollection | None:
        stmt = select(SwipeCollection).where(
            SwipeCollection.org_id == org_id,
            SwipeCollection.kind == kind,
        )
        return self.session.scalars(stmt).first()

    def create(
        self,
        *,
        org_id: str,
        name: str,
        kind: str,
        created_by_user_id: str | None,
        cloned_from_collection_id: str | None = None,
    ) -> SwipeCollection:
        collection = SwipeCollection(
            org_id=org_id,
            name=name,
            kind=kind,
            created_by_user_id=created_by_user_id,
            cloned_from_collection_id=cloned_from_collection_id,
        )
        self.session.add(collection)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ValueError(f"Swipe collection '{name}' already exists.") from exc
        self.session.refresh(collection)
        return collection

    def clone(
        self,
        *,
        org_id: str,
        source_collection_id: str,
        name: str,
        created_by_user_id: str | None,
    ) -> SwipeCollection:
        source = self.get(org_id=org_id, collection_id=source_collection_id)
        if source is None:
            raise ValueError("Swipe collection not found.")
        cloned = SwipeCollection(
            org_id=org_id,
            name=name,
            kind="curated",
            created_by_user_id=created_by_user_id,
            cloned_from_collection_id=source.id,
        )
        self.session.add(cloned)
        self.session.flush()
        source_asset_ids = self.list_asset_ids(org_id=org_id, collection_id=source_collection_id)
        for swipe_asset_id in source_asset_ids:
            self.session.add(
                SwipeCollectionItem(
                    org_id=org_id,
                    collection_id=cloned.id,
                    swipe_asset_id=swipe_asset_id,
                )
            )
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ValueError(f"Swipe collection '{name}' already exists.") from exc
        self.session.refresh(cloned)
        return cloned

    def add_items(self, *, org_id: str, collection_id: str, swipe_asset_ids: list[str]) -> None:
        existing = {
            str(asset_id)
            for asset_id in self.session.scalars(
                select(SwipeCollectionItem.swipe_asset_id).where(
                    SwipeCollectionItem.org_id == org_id,
                    SwipeCollectionItem.collection_id == collection_id,
                    SwipeCollectionItem.swipe_asset_id.in_(swipe_asset_ids),
                )
            ).all()
        }
        for swipe_asset_id in swipe_asset_ids:
            if swipe_asset_id in existing:
                continue
            self.session.add(
                SwipeCollectionItem(
                    org_id=org_id,
                    collection_id=collection_id,
                    swipe_asset_id=swipe_asset_id,
                )
            )
        self.session.commit()

    def remove_item(self, *, org_id: str, collection_id: str, swipe_asset_id: str) -> bool:
        stmt = select(SwipeCollectionItem).where(
            SwipeCollectionItem.org_id == org_id,
            SwipeCollectionItem.collection_id == collection_id,
            SwipeCollectionItem.swipe_asset_id == swipe_asset_id,
        )
        row = self.session.scalars(stmt).first()
        if row is None:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    def list_asset_ids(self, *, org_id: str, collection_id: str) -> list[str]:
        stmt = select(SwipeCollectionItem.swipe_asset_id).where(
            SwipeCollectionItem.org_id == org_id,
            SwipeCollectionItem.collection_id == collection_id,
        )
        return [str(asset_id) for asset_id in self.session.scalars(stmt).all()]

    def analysis_counts(self, *, org_id: str, collection_id: str) -> dict[str, int]:
        stmt = (
            select(CompanySwipeAsset.analysis_status, func.count(CompanySwipeAsset.id))
            .join(
                SwipeCollectionItem,
                SwipeCollectionItem.swipe_asset_id == CompanySwipeAsset.id,
            )
            .where(
                SwipeCollectionItem.org_id == org_id,
                SwipeCollectionItem.collection_id == collection_id,
                CompanySwipeAsset.org_id == org_id,
            )
            .group_by(CompanySwipeAsset.analysis_status)
        )
        return {
            str(status or "unknown"): int(count)
            for status, count in self.session.execute(stmt).all()
        }

    def item_count(self, *, org_id: str, collection_id: str) -> int:
        stmt = select(func.count(SwipeCollectionItem.id)).where(
            SwipeCollectionItem.org_id == org_id,
            SwipeCollectionItem.collection_id == collection_id,
        )
        return int(self.session.scalar(stmt) or 0)

    def item_counts(self, *, org_id: str) -> dict[str, int]:
        stmt = (
            select(SwipeCollectionItem.collection_id, func.count(SwipeCollectionItem.id))
            .where(SwipeCollectionItem.org_id == org_id)
            .group_by(SwipeCollectionItem.collection_id)
        )
        return {
            str(collection_id): int(count)
            for collection_id, count in self.session.execute(stmt).all()
        }

    def ready_asset_ids(self, *, org_id: str, collection_id: str) -> list[str]:
        stmt = (
            select(CompanySwipeAsset.id)
            .join(
                SwipeCollectionItem,
                SwipeCollectionItem.swipe_asset_id == CompanySwipeAsset.id,
            )
            .where(
                CompanySwipeAsset.org_id == org_id,
                SwipeCollectionItem.org_id == org_id,
                SwipeCollectionItem.collection_id == collection_id,
                CompanySwipeAsset.analysis_status == "ready",
            )
            .order_by(CompanySwipeAsset.created_at.desc())
        )
        return [str(asset_id) for asset_id in self.session.scalars(stmt).all()]


class ClientSwipesRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, org_id: str, client_id: str) -> list[ClientSwipeAsset]:
        stmt = (
            select(ClientSwipeAsset)
            .where(ClientSwipeAsset.org_id == org_id, ClientSwipeAsset.client_id == client_id)
            .order_by(ClientSwipeAsset.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def get(self, org_id: str, swipe_id: str) -> ClientSwipeAsset | None:
        stmt = select(ClientSwipeAsset).where(
            ClientSwipeAsset.org_id == org_id, ClientSwipeAsset.id == swipe_id
        )
        return self.session.scalars(stmt).first()

    def create(self, org_id: str, client_id: str, **fields) -> ClientSwipeAsset:
        swipe = ClientSwipeAsset(org_id=org_id, client_id=client_id, **fields)
        self.session.add(swipe)
        self.session.commit()
        self.session.refresh(swipe)
        return swipe

    def update(self, org_id: str, swipe_id: str, **fields) -> ClientSwipeAsset | None:
        swipe = self.get(org_id, swipe_id)
        if not swipe:
            return None
        for key, value in fields.items():
            setattr(swipe, key, value)
        self.session.commit()
        self.session.refresh(swipe)
        return swipe

    def delete(self, org_id: str, swipe_id: str) -> bool:
        swipe = self.get(org_id, swipe_id)
        if not swipe:
            return False
        self.session.delete(swipe)
        self.session.commit()
        return True
