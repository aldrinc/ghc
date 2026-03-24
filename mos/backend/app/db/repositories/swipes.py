from __future__ import annotations

from collections import defaultdict
from typing import Iterable

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
WRITABLE_SWIPE_COLLECTION_KINDS = {"uploaded", "curated"}


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
        stmt = stmt.order_by(CompanySwipeAsset.created_at.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt).all())

    def get_asset(self, org_id: str, swipe_id: str) -> CompanySwipeAsset | None:
        stmt = select(CompanySwipeAsset).where(
            CompanySwipeAsset.org_id == org_id,
            CompanySwipeAsset.id == swipe_id,
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

    def create_media(self, **fields) -> CompanySwipeMedia:
        media = CompanySwipeMedia(**fields)
        self.session.add(media)
        self.session.flush()
        return media

    def list_brands(self, org_id: str) -> list[CompanySwipeBrand]:
        stmt = select(CompanySwipeBrand).where(CompanySwipeBrand.org_id == org_id)
        return list(self.session.scalars(stmt).all())

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

    def list_media_for_assets(self, *, org_id: str, swipe_asset_ids: Iterable[str]) -> dict[str, list[CompanySwipeMedia]]:
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

        catalog_asset_ids = {
            str(asset_id)
            for asset_id in self.session.scalars(
                select(CompanySwipeAsset.id).where(
                    CompanySwipeAsset.org_id == org_id,
                    CompanySwipeAsset.source_kind != "upload",
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

    def list(self, *, org_id: str) -> list[SwipeCollection]:
        self.ensure_default_collection(org_id=org_id)
        stmt = select(SwipeCollection).where(SwipeCollection.org_id == org_id).order_by(
            SwipeCollection.kind.asc(),
            SwipeCollection.created_at.asc(),
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
        return {str(status or "unknown"): int(count) for status, count in self.session.execute(stmt).all()}

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
        return {str(collection_id): int(count) for collection_id, count in self.session.execute(stmt).all()}

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
