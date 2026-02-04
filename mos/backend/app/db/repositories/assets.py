from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import AssetStatusEnum
from app.db.models import Asset


class AssetsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(
        self,
        org_id: str,
        client_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        experiment_id: Optional[str] = None,
        product_id: Optional[str] = None,
        funnel_id: Optional[str] = None,
        asset_kind: Optional[str] = None,
        tags: Optional[list[str]] = None,
        statuses: Optional[list[AssetStatusEnum]] = None,
    ) -> List[Asset]:
        stmt = select(Asset).where(Asset.org_id == org_id)
        if client_id:
            stmt = stmt.where(Asset.client_id == client_id)
        if campaign_id:
            stmt = stmt.where(Asset.campaign_id == campaign_id)
        if experiment_id:
            stmt = stmt.where(Asset.experiment_id == experiment_id)
        if product_id:
            stmt = stmt.where(Asset.product_id == product_id)
        if funnel_id:
            stmt = stmt.where(Asset.funnel_id == funnel_id)
        if asset_kind:
            stmt = stmt.where(Asset.asset_kind == asset_kind)
        if tags:
            stmt = stmt.where(Asset.tags.contains(tags))
        if statuses:
            stmt = stmt.where(Asset.status.in_(statuses))
        stmt = stmt.order_by(Asset.created_at.desc())
        return list(self.session.scalars(stmt).all())

    def get(self, org_id: str, asset_id: str) -> Optional[Asset]:
        stmt = select(Asset).where(Asset.org_id == org_id, Asset.id == asset_id)
        return self.session.scalars(stmt).first()

    def get_by_public_id(
        self, org_id: str, public_id: str, client_id: Optional[str] = None
    ) -> Optional[Asset]:
        stmt = select(Asset).where(Asset.org_id == org_id, Asset.public_id == public_id)
        if client_id:
            stmt = stmt.where(Asset.client_id == client_id)
        return self.session.scalars(stmt).first()

    def create(self, org_id: str, client_id: str, channel_id: str, format: str, content: dict, **fields) -> Asset:
        asset = Asset(
            org_id=org_id,
            client_id=client_id,
            channel_id=channel_id,
            format=format,
            content=content,
            **fields,
        )
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)
        return asset

    def update_status(self, org_id: str, asset_id: str, status: AssetStatusEnum) -> Optional[Asset]:
        asset = self.get(org_id, asset_id)
        if not asset:
            return None
        asset.status = status
        self.session.commit()
        self.session.refresh(asset)
        return asset

    def update(self, org_id: str, asset_id: str, **fields) -> Optional[Asset]:
        asset = self.get(org_id, asset_id)
        if not asset:
            return None
        for key, value in fields.items():
            setattr(asset, key, value)
        self.session.commit()
        self.session.refresh(asset)
        return asset
