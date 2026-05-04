from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    GETHOOKD_ORIGIN_SYSTEM,
    ClientSwipeAsset,
    CompanySwipeAsset,
    CompanySwipeBrand,
    CompanySwipeMedia,
    MediaAsset,
    SwipeCollection,
    SwipeCollectionItem,
)

DEFAULT_SWIPE_COLLECTION_KIND = "default"
DEFAULT_SWIPE_COLLECTION_NAME = "Default"
GETHOOKD_INBOX_COLLECTION_KIND = "gethookd_inbox"
GETHOOKD_INBOX_KIND = GETHOOKD_INBOX_COLLECTION_KIND
GETHOOKD_INBOX_NAME = "GetHookd"
WRITABLE_SWIPE_COLLECTION_KINDS = {"uploaded", "curated"}

# GetHookd-specific constants
GETHOOKD_REVIEW_STATUS_PENDING = "pending_review"
GETHOOKD_REVIEW_STATUS_APPROVED = "approved"
GETHOOKD_REVIEW_STATUS_REJECTED = "rejected"
GETHOOKD_REVIEW_STATUS_STALE = "stale_after_sync"

# Backward-compatible aliases for older call sites.
REVIEW_STATUS_PENDING = GETHOOKD_REVIEW_STATUS_PENDING
REVIEW_STATUS_APPROVED = GETHOOKD_REVIEW_STATUS_APPROVED
REVIEW_STATUS_REJECTED = GETHOOKD_REVIEW_STATUS_REJECTED
REVIEW_STATUS_STALE = GETHOOKD_REVIEW_STATUS_STALE

_KNOWN_SWIPE_AD_UNIT_FORMATS = {"image", "video", "carousel"}


def _normalize_swipe_ad_unit_format(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in _KNOWN_SWIPE_AD_UNIT_FORMATS:
        return normalized
    return None


def _normalize_swipe_media_type(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"image", "video"}:
        return normalized
    return None


def _resolve_company_swipe_media_type(media: CompanySwipeMedia) -> str | None:
    for candidate in (
        getattr(media, "type", None),
        getattr(media, "_resolved_asset_type", None),
    ):
        normalized = _normalize_swipe_media_type(candidate)
        if normalized:
            return normalized

    mime_type = str(getattr(media, "mime_type", None) or "").strip().lower()
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"

    video_length = getattr(media, "video_length", None)
    if isinstance(video_length, int) and video_length > 0:
        return "video"
    return None


def infer_swipe_asset_ad_unit_format(
    *,
    ad_unit_format: object,
    media_items: Sequence[CompanySwipeMedia] | None = None,
) -> str | None:
    normalized_format = _normalize_swipe_ad_unit_format(ad_unit_format)
    if normalized_format:
        return normalized_format

    if not media_items:
        return None

    video_count = 0
    image_count = 0
    for media in media_items:
        media_type = _resolve_company_swipe_media_type(media)
        if media_type == "video":
            video_count += 1
        elif media_type == "image":
            image_count += 1

    if video_count:
        return "video"
    if image_count > 1:
        return "carousel"
    if image_count == 1:
        return "image"
    return None


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
        swipe = self.get_asset(org_id=org_id, swipe_id=swipe_id)
        if swipe is None:
            return None
        swipe.review_status = review_status
        if review_status == REVIEW_STATUS_PENDING:
            swipe.reviewed_at = None
            swipe.reviewed_by_user_id = None
        else:
            swipe.reviewed_at = datetime.now(timezone.utc)
            swipe.reviewed_by_user_id = reviewed_by_user_id
        self.session.flush()
        return swipe

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

    def delete_media_for_asset(self, *, org_id: str, swipe_asset_id: str) -> None:
        stmt = select(CompanySwipeMedia).where(
            CompanySwipeMedia.org_id == org_id,
            CompanySwipeMedia.swipe_asset_id == swipe_asset_id,
        )
        for media in self.session.scalars(stmt).all():
            self.session.delete(media)
        self.session.flush()

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
            select(CompanySwipeMedia, MediaAsset)
            .where(
                CompanySwipeMedia.org_id == org_id,
                CompanySwipeMedia.swipe_asset_id.in_(ids),
            )
            .outerjoin(MediaAsset, MediaAsset.id == CompanySwipeMedia.media_asset_id)
            .order_by(CompanySwipeMedia.created_at.asc())
        )
        grouped: dict[str, list[CompanySwipeMedia]] = defaultdict(list)
        for media, media_asset in self.session.execute(stmt).all():
            setattr(media, "_resolved_asset_type", getattr(media_asset, "asset_type", None))
            setattr(media, "_resolved_storage_key", getattr(media_asset, "storage_key", None))
            setattr(
                media,
                "_resolved_preview_storage_key",
                getattr(media_asset, "preview_storage_key", None),
            )
            setattr(media, "_resolved_bucket", getattr(media_asset, "bucket", None))
            setattr(
                media,
                "_resolved_preview_bucket",
                getattr(media_asset, "preview_bucket", None),
            )
            setattr(media, "_resolved_media_metadata", getattr(media_asset, "metadata_json", {}) or {})
            grouped[str(media.swipe_asset_id)].append(media)
        return dict(grouped)

    def list_assets_with_review_filters(
        self,
        *,
        org_id: str,
        limit: int = 50,
        offset: int = 0,
        collection_id: str | None = None,
        client_id: str | None = None,
        review_status: str | None = None,
        origin_system: str | None = None,
        search: str | None = None,
        changed_since_days: int | None = None,
        not_in_writable_collections: bool = False,
        exclude_gethookd: bool = False,
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

        if client_id:
            stmt = stmt.where(
                CompanySwipeAsset.source_metadata_json.contains({"client_ids": [client_id]})
            )

        if review_status is not None:
            stmt = stmt.where(CompanySwipeAsset.review_status == review_status)

        if origin_system is not None:
            stmt = stmt.where(CompanySwipeAsset.origin_system == origin_system)

        if search:
            search_like = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    CompanySwipeAsset.title.ilike(search_like),
                    CompanySwipeAsset.body.ilike(search_like),
                    CompanySwipeAsset.external_ad_id.ilike(search_like),
                )
            )

        if changed_since_days is not None and changed_since_days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=changed_since_days)
            stmt = stmt.where(
                or_(
                    CompanySwipeAsset.source_last_synced_at >= cutoff,
                    CompanySwipeAsset.source_content_changed_at >= cutoff,
                )
            )

        if not_in_writable_collections:
            stmt = stmt.where(
                ~CompanySwipeAsset.id.in_(
                    select(SwipeCollectionItem.swipe_asset_id)
                    .join(SwipeCollection, SwipeCollection.id == SwipeCollectionItem.collection_id)
                    .where(
                        SwipeCollectionItem.org_id == org_id,
                        SwipeCollection.kind.in_(tuple(WRITABLE_SWIPE_COLLECTION_KINDS)),
                    )
                )
            )

        if exclude_gethookd:
            stmt = stmt.where(CompanySwipeAsset.origin_system != GETHOOKD_ORIGIN_SYSTEM)

        stmt = stmt.order_by(CompanySwipeAsset.created_at.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt).all())

    def get_gethookd_inbox_assets(
        self,
        *,
        org_id: str,
        limit: int = 50,
        offset: int = 0,
        review_status: str | None = None,
    ) -> list[CompanySwipeAsset]:
        stmt = select(CompanySwipeAsset).where(
            CompanySwipeAsset.org_id == org_id,
            CompanySwipeAsset.origin_system == GETHOOKD_ORIGIN_SYSTEM,
        )
        if review_status is not None:
            stmt = stmt.where(CompanySwipeAsset.review_status == review_status)
        stmt = stmt.order_by(CompanySwipeAsset.created_at.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt).all())

    def approve_swipe(
        self,
        *,
        org_id: str,
        swipe_id: str,
        reviewed_by_user_id: str | None = None,
    ) -> CompanySwipeAsset | None:
        return self.approve_asset(
            org_id=org_id,
            swipe_id=swipe_id,
            reviewed_by_user_id=reviewed_by_user_id,
        )

    def reject_swipe(
        self,
        *,
        org_id: str,
        swipe_id: str,
        reviewed_by_user_id: str | None = None,
    ) -> CompanySwipeAsset | None:
        return self.reject_asset(
            org_id=org_id,
            swipe_id=swipe_id,
            reviewed_by_user_id=reviewed_by_user_id,
        )

    def mark_swipe_pending(
        self,
        *,
        org_id: str,
        swipe_id: str,
        reviewed_by_user_id: str | None = None,
    ) -> CompanySwipeAsset | None:
        return self.mark_pending(
            org_id=org_id,
            swipe_id=swipe_id,
        )


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
                    # Exclude GetHookd assets from default collection
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
        return collection

    def add_item_if_missing(
        self,
        *,
        org_id: str,
        collection_id: str,
        swipe_asset_id: str,
    ) -> bool:
        """Add an item to a collection if not already present."""
        existing = self.session.scalar(
            select(SwipeCollectionItem).where(
                SwipeCollectionItem.org_id == org_id,
                SwipeCollectionItem.collection_id == collection_id,
                SwipeCollectionItem.swipe_asset_id == swipe_asset_id,
            )
        )
        if existing is not None:
            return False
        item = SwipeCollectionItem(
            org_id=org_id,
            collection_id=collection_id,
            swipe_asset_id=swipe_asset_id,
        )
        self.session.add(item)
        self.session.flush()
        return True

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

    def add_items(
        self,
        *,
        org_id: str,
        collection_id: str,
        swipe_asset_ids: list[str],
        mark_approved: bool = False,
        reviewed_by_user_id: str | None = None,
    ) -> None:
        """Add items to a collection.

        Args:
            org_id: Organization ID
            collection_id: Collection ID
            swipe_asset_ids: List of swipe asset IDs to add
            mark_approved: If True, mark GetHookd assets as approved when adding to collection
        """
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

        # Get swipe assets to update (for clearing stale status)
        assets_to_update = list(
            self.session.scalars(
                select(CompanySwipeAsset).where(
                    CompanySwipeAsset.org_id == org_id,
                    CompanySwipeAsset.id.in_(swipe_asset_ids),
                    CompanySwipeAsset.origin_system == GETHOOKD_ORIGIN_SYSTEM,
                )
            ).all()
        )

        now = datetime.now(timezone.utc)
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

            # Clear stale status when adding to a writable collection
            for asset in assets_to_update:
                if str(asset.id) == swipe_asset_id:
                    asset.source_last_synced_at = now
                    if mark_approved:
                        asset.review_status = GETHOOKD_REVIEW_STATUS_APPROVED
                        asset.reviewed_at = now
                        asset.reviewed_by_user_id = reviewed_by_user_id
                        asset.source_content_changed_at = None
                    break

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

    def ready_asset_ids(
        self,
        *,
        org_id: str,
        collection_id: str,
        ad_unit_formats: Sequence[str] | None = None,
    ) -> list[str]:
        stmt = (
            select(
                CompanySwipeAsset.id,
                CompanySwipeAsset.ad_unit_format,
            )
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
        rows = list(self.session.execute(stmt).all())
        if not ad_unit_formats:
            return [str(asset_id) for asset_id, _ad_unit_format in rows]

        normalized_formats = {
            normalized
            for value in ad_unit_formats
            if (normalized := _normalize_swipe_ad_unit_format(value))
        }
        if not normalized_formats:
            return [str(asset_id) for asset_id, _ad_unit_format in rows]

        unresolved_asset_ids = [
            str(asset_id)
            for asset_id, ad_unit_format in rows
            if _normalize_swipe_ad_unit_format(ad_unit_format) is None
        ]
        media_by_asset_id = CompanySwipesRepository(self.session).list_media_for_assets(
            org_id=org_id,
            swipe_asset_ids=unresolved_asset_ids,
        )

        matched_asset_ids: list[str] = []
        for asset_id, ad_unit_format in rows:
            resolved_format = infer_swipe_asset_ad_unit_format(
                ad_unit_format=ad_unit_format,
                media_items=media_by_asset_id.get(str(asset_id), []),
            )
            if resolved_format in normalized_formats:
                matched_asset_ids.append(str(asset_id))
        return matched_asset_ids


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
