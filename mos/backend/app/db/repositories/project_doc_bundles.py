from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import ProjectDocBundle, ProjectDocBundleItem


class ProjectDocBundlesRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, *, bundle_id: str, org_id: str | None = None) -> ProjectDocBundle | None:
        stmt = select(ProjectDocBundle).where(ProjectDocBundle.id == bundle_id)
        if org_id:
            stmt = stmt.where(ProjectDocBundle.org_id == org_id)
        return self.session.scalars(stmt).first()

    def list_for_scope(
        self,
        *,
        org_id: str,
        client_id: str,
        product_id: str,
        bundle_type: str | None = None,
    ) -> list[ProjectDocBundle]:
        stmt = (
            select(ProjectDocBundle)
            .where(
                ProjectDocBundle.org_id == org_id,
                ProjectDocBundle.client_id == client_id,
                ProjectDocBundle.product_id == product_id,
            )
            .order_by(desc(ProjectDocBundle.created_at))
        )
        if bundle_type:
            stmt = stmt.where(ProjectDocBundle.bundle_type == bundle_type)
        return list(self.session.scalars(stmt).all())

    def get_active(
        self,
        *,
        org_id: str,
        client_id: str,
        product_id: str,
        bundle_type: str,
    ) -> ProjectDocBundle | None:
        stmt = (
            select(ProjectDocBundle)
            .where(
                ProjectDocBundle.org_id == org_id,
                ProjectDocBundle.client_id == client_id,
                ProjectDocBundle.product_id == product_id,
                ProjectDocBundle.bundle_type == bundle_type,
                ProjectDocBundle.is_active.is_(True),
            )
            .order_by(desc(ProjectDocBundle.updated_at))
        )
        return self.session.scalars(stmt).first()

    def create(
        self,
        *,
        org_id: str,
        client_id: str,
        product_id: str,
        bundle_type: str,
        title: str,
        status: str,
        is_active: bool,
        metadata_json: dict | None,
        created_by_user: str | None,
        approved_by_user: str | None = None,
    ) -> ProjectDocBundle:
        now = datetime.now(timezone.utc)
        bundle = ProjectDocBundle(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            bundle_type=bundle_type,
            title=title,
            status=status,
            is_active=is_active,
            metadata_json=metadata_json or {},
            created_by_user=created_by_user,
            approved_by_user=approved_by_user,
            approved_at=now if approved_by_user else None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(bundle)
        self.session.flush()
        self.session.refresh(bundle)
        return bundle

    def update(self, *, bundle: ProjectDocBundle) -> ProjectDocBundle:
        bundle.updated_at = datetime.now(timezone.utc)
        self.session.add(bundle)
        self.session.flush()
        self.session.refresh(bundle)
        return bundle

    def deactivate_scope(
        self,
        *,
        org_id: str,
        client_id: str,
        product_id: str,
        bundle_type: str,
    ) -> None:
        self.session.query(ProjectDocBundle).filter(
            ProjectDocBundle.org_id == org_id,
            ProjectDocBundle.client_id == client_id,
            ProjectDocBundle.product_id == product_id,
            ProjectDocBundle.bundle_type == bundle_type,
            ProjectDocBundle.is_active.is_(True),
        ).update(
            {
                ProjectDocBundle.is_active: False,
                ProjectDocBundle.updated_at: datetime.now(timezone.utc),
            },
            synchronize_session=False,
        )
        self.session.flush()

    def replace_items(
        self,
        *,
        bundle_id: str,
        items: list[dict],
    ) -> list[ProjectDocBundleItem]:
        self.session.query(ProjectDocBundleItem).filter(
            ProjectDocBundleItem.project_doc_bundle_id == bundle_id
        ).delete(synchronize_session=False)
        created: list[ProjectDocBundleItem] = []
        for item in items:
            bundle_item = ProjectDocBundleItem(
                project_doc_bundle_id=bundle_id,
                artifact_id=item["artifact_id"],
                role=item["role"],
                item_order=item.get("item_order", 0),
                metadata_json=item.get("metadata_json") or {},
            )
            self.session.add(bundle_item)
            created.append(bundle_item)
        self.session.flush()
        return created

    def list_items(self, *, bundle_id: str) -> list[ProjectDocBundleItem]:
        stmt = (
            select(ProjectDocBundleItem)
            .where(ProjectDocBundleItem.project_doc_bundle_id == bundle_id)
            .order_by(ProjectDocBundleItem.item_order.asc(), ProjectDocBundleItem.created_at.asc())
        )
        return list(self.session.scalars(stmt).all())
