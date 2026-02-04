from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CompanySwipeAsset, CompanySwipeBrand, CompanySwipeMedia, ClientSwipeAsset


class CompanySwipesRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_assets(self, org_id: str, limit: int = 50, offset: int = 0) -> List[CompanySwipeAsset]:
        stmt = (
            select(CompanySwipeAsset)
            .where(CompanySwipeAsset.org_id == org_id)
            .order_by(CompanySwipeAsset.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(stmt).all())

    def get_asset(self, org_id: str, swipe_id: str) -> Optional[CompanySwipeAsset]:
        stmt = select(CompanySwipeAsset).where(
            CompanySwipeAsset.org_id == org_id, CompanySwipeAsset.id == swipe_id
        )
        return self.session.scalars(stmt).first()

    def list_brands(self, org_id: str) -> List[CompanySwipeBrand]:
        stmt = select(CompanySwipeBrand).where(CompanySwipeBrand.org_id == org_id)
        return list(self.session.scalars(stmt).all())

    def list_media(self, org_id: str, swipe_asset_id: str) -> List[CompanySwipeMedia]:
        stmt = select(CompanySwipeMedia).where(
            CompanySwipeMedia.org_id == org_id, CompanySwipeMedia.swipe_asset_id == swipe_asset_id
        )
        return list(self.session.scalars(stmt).all())


class ClientSwipesRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, org_id: str, client_id: str) -> List[ClientSwipeAsset]:
        stmt = (
            select(ClientSwipeAsset)
            .where(ClientSwipeAsset.org_id == org_id, ClientSwipeAsset.client_id == client_id)
            .order_by(ClientSwipeAsset.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def get(self, org_id: str, swipe_id: str) -> Optional[ClientSwipeAsset]:
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

    def update(self, org_id: str, swipe_id: str, **fields) -> Optional[ClientSwipeAsset]:
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
