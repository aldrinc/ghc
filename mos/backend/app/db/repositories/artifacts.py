from typing import List, Optional
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.enums import ArtifactTypeEnum
from app.db.models import Artifact, User


class ArtifactsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _resolve_created_by_user_id(self, *, org_id: str, created_by_user: Optional[str]) -> Optional[str]:
        candidate = (created_by_user or "").strip()
        if not candidate:
            return None

        try:
            user_id = str(UUID(candidate))
            user = self.session.scalars(
                select(User.id).where(User.org_id == org_id, User.id == user_id)
            ).first()
            return str(user) if user else None
        except ValueError:
            pass

        user = self.session.scalars(
            select(User.id).where(User.org_id == org_id, User.clerk_user_id == candidate)
        ).first()
        return str(user) if user else None

    def list(
        self,
        org_id: str,
        client_id: Optional[str] = None,
        product_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        artifact_type: Optional[ArtifactTypeEnum] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Artifact]:
        stmt = select(Artifact).where(Artifact.org_id == org_id)
        if client_id:
            stmt = stmt.where(Artifact.client_id == client_id)
        if product_id:
            stmt = stmt.where(Artifact.product_id == product_id)
        if campaign_id:
            stmt = stmt.where(Artifact.campaign_id == campaign_id)
        if artifact_type:
            stmt = stmt.where(Artifact.type == artifact_type)
        stmt = stmt.order_by(desc(Artifact.created_at)).limit(limit).offset(offset)
        return list(self.session.scalars(stmt).all())

    def get(self, org_id: str, artifact_id: str) -> Optional[Artifact]:
        stmt = select(Artifact).where(Artifact.org_id == org_id, Artifact.id == artifact_id)
        return self.session.scalars(stmt).first()

    def get_latest_by_type(
        self,
        org_id: str,
        client_id: str,
        artifact_type: ArtifactTypeEnum,
        product_id: Optional[str] = None,
    ) -> Optional[Artifact]:
        stmt = (
            select(Artifact)
            .where(
                Artifact.org_id == org_id,
                Artifact.client_id == client_id,
                Artifact.type == artifact_type,
            )
            .order_by(desc(Artifact.created_at))
        )
        if product_id:
            stmt = stmt.where(Artifact.product_id == product_id)
        return self.session.scalars(stmt).first()

    def get_latest_by_type_for_campaign(
        self, org_id: str, campaign_id: str, artifact_type: ArtifactTypeEnum
    ) -> Optional[Artifact]:
        stmt = (
            select(Artifact)
            .where(
                Artifact.org_id == org_id,
                Artifact.campaign_id == campaign_id,
                Artifact.type == artifact_type,
            )
            .order_by(desc(Artifact.created_at))
        )
        return self.session.scalars(stmt).first()

    def insert(
        self,
        org_id: str,
        client_id: str,
        artifact_type: ArtifactTypeEnum,
        data: dict,
        product_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        created_by_user: Optional[str] = None,
        version: int = 1,
    ) -> Artifact:
        resolved_created_by_user = self._resolve_created_by_user_id(
            org_id=org_id,
            created_by_user=created_by_user,
        )
        artifact = Artifact(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            type=artifact_type,
            data=data,
            created_by_user=resolved_created_by_user,
            version=version,
        )
        self.session.add(artifact)
        self.session.commit()
        self.session.refresh(artifact)
        return artifact
