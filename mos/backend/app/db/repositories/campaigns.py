from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Campaign


class CampaignsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(
        self,
        org_id: str,
        client_id: Optional[str] = None,
        product_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Campaign]:
        stmt = select(Campaign).where(Campaign.org_id == org_id)
        if client_id:
            stmt = stmt.where(Campaign.client_id == client_id)
        if product_id:
            stmt = stmt.where(Campaign.product_id == product_id)
        stmt = stmt.order_by(Campaign.created_at.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt).all())

    def get(self, org_id: str, campaign_id: str) -> Optional[Campaign]:
        stmt = select(Campaign).where(Campaign.org_id == org_id, Campaign.id == campaign_id)
        return self.session.scalars(stmt).first()

    def create(self, org_id: str, client_id: str, name: str, **fields) -> Campaign:
        campaign = Campaign(org_id=org_id, client_id=client_id, name=name, **fields)
        self.session.add(campaign)
        self.session.commit()
        self.session.refresh(campaign)
        return campaign

    def update(self, org_id: str, campaign_id: str, **fields) -> Optional[Campaign]:
        campaign = self.get(org_id, campaign_id)
        if not campaign:
            return None
        for key, value in fields.items():
            setattr(campaign, key, value)
        self.session.commit()
        self.session.refresh(campaign)
        return campaign

    def delete(self, org_id: str, campaign_id: str) -> bool:
        campaign = self.get(org_id, campaign_id)
        if not campaign:
            return False
        self.session.delete(campaign)
        self.session.commit()
        return True
