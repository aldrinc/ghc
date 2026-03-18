from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CampaignDeliveryConfig


class CampaignDeliveryConfigsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_campaign(self, *, org_id: str, campaign_id: str) -> Optional[CampaignDeliveryConfig]:
        stmt = select(CampaignDeliveryConfig).where(
            CampaignDeliveryConfig.org_id == org_id,
            CampaignDeliveryConfig.campaign_id == campaign_id,
        )
        return self.session.scalars(stmt).first()

    def create(self, **fields) -> CampaignDeliveryConfig:
        row = CampaignDeliveryConfig(**fields)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def update(self, row: CampaignDeliveryConfig, **fields) -> CampaignDeliveryConfig:
        for key, value in fields.items():
            setattr(row, key, value)
        self.session.commit()
        self.session.refresh(row)
        return row
