from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ShopifyThemeTemplateDraft,
    ShopifyThemeTemplateDraftVersion,
)
from app.db.repositories.base import Repository


class ShopifyThemeTemplateDraftsRepository(Repository):
    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def list_for_client(
        self,
        *,
        org_id: str,
        client_id: str,
        limit: int = 20,
    ) -> list[ShopifyThemeTemplateDraft]:
        safe_limit = max(1, min(limit, 100))
        stmt = (
            select(ShopifyThemeTemplateDraft)
            .where(
                ShopifyThemeTemplateDraft.org_id == org_id,
                ShopifyThemeTemplateDraft.client_id == client_id,
            )
            .order_by(
                ShopifyThemeTemplateDraft.updated_at.desc(),
                ShopifyThemeTemplateDraft.created_at.desc(),
            )
            .limit(safe_limit)
        )
        return list(self.session.scalars(stmt).all())

    def get(
        self,
        *,
        org_id: str,
        client_id: str,
        draft_id: str,
    ) -> Optional[ShopifyThemeTemplateDraft]:
        stmt = select(ShopifyThemeTemplateDraft).where(
            ShopifyThemeTemplateDraft.id == draft_id,
            ShopifyThemeTemplateDraft.org_id == org_id,
            ShopifyThemeTemplateDraft.client_id == client_id,
        )
        return self.session.scalars(stmt).first()

    def get_latest_version(self, *, draft_id: str) -> Optional[ShopifyThemeTemplateDraftVersion]:
        stmt = (
            select(ShopifyThemeTemplateDraftVersion)
            .where(ShopifyThemeTemplateDraftVersion.draft_id == draft_id)
            .order_by(
                ShopifyThemeTemplateDraftVersion.version_number.desc(),
                ShopifyThemeTemplateDraftVersion.created_at.desc(),
            )
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def list_versions(self, *, draft_id: str) -> list[ShopifyThemeTemplateDraftVersion]:
        stmt = (
            select(ShopifyThemeTemplateDraftVersion)
            .where(ShopifyThemeTemplateDraftVersion.draft_id == draft_id)
            .order_by(ShopifyThemeTemplateDraftVersion.version_number.desc())
        )
        return list(self.session.scalars(stmt).all())

    def create_draft(
        self,
        *,
        org_id: str,
        client_id: str,
        shop_domain: str,
        theme_id: str,
        theme_name: str,
        theme_role: str,
        design_system_id: str | None = None,
        product_id: str | None = None,
        created_by_user_external_id: str | None = None,
        status: str = "draft",
    ) -> ShopifyThemeTemplateDraft:
        now = datetime.now(timezone.utc)
        draft = ShopifyThemeTemplateDraft(
            org_id=org_id,
            client_id=client_id,
            design_system_id=design_system_id,
            product_id=product_id,
            shop_domain=shop_domain,
            theme_id=theme_id,
            theme_name=theme_name,
            theme_role=theme_role,
            status=status,
            created_by_user_external_id=created_by_user_external_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(draft)
        self.session.commit()
        self.session.refresh(draft)
        return draft

    def create_version(
        self,
        *,
        draft: ShopifyThemeTemplateDraft,
        payload: dict[str, Any],
        source: str = "build_job",
        notes: str | None = None,
        created_by_user_external_id: str | None = None,
    ) -> ShopifyThemeTemplateDraftVersion:
        max_version_stmt = select(
            func.max(ShopifyThemeTemplateDraftVersion.version_number)
        ).where(ShopifyThemeTemplateDraftVersion.draft_id == draft.id)
        current_max_version = self.session.execute(max_version_stmt).scalar_one_or_none()
        next_version = (int(current_max_version) if current_max_version is not None else 0) + 1

        now = datetime.now(timezone.utc)
        version = ShopifyThemeTemplateDraftVersion(
            draft_id=draft.id,
            org_id=draft.org_id,
            client_id=draft.client_id,
            version_number=next_version,
            source=source,
            payload=payload,
            notes=notes,
            created_by_user_external_id=created_by_user_external_id,
            created_at=now,
        )
        draft.updated_at = now
        self.session.add(version)
        self.session.commit()
        self.session.refresh(version)
        self.session.refresh(draft)
        return version

    def mark_published(
        self,
        *,
        draft: ShopifyThemeTemplateDraft,
    ) -> ShopifyThemeTemplateDraft:
        now = datetime.now(timezone.utc)
        draft.status = "published"
        draft.published_at = now
        draft.updated_at = now
        self.session.commit()
        self.session.refresh(draft)
        return draft
