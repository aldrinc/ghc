from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import OnboardingPayload


class OnboardingPayloadsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, org_id: str, client_id: str, data: dict) -> OnboardingPayload:
        payload = OnboardingPayload(org_id=org_id, client_id=client_id, data=data)
        self.session.add(payload)
        self.session.commit()
        self.session.refresh(payload)
        return payload

    def get(self, org_id: str, payload_id: str) -> Optional[OnboardingPayload]:
        stmt = select(OnboardingPayload).where(
            OnboardingPayload.org_id == org_id, OnboardingPayload.id == payload_id
        )
        return self.session.scalars(stmt).first()

    def latest_for_client(self, org_id: str, client_id: str) -> Optional[OnboardingPayload]:
        stmt = (
            select(OnboardingPayload)
            .where(OnboardingPayload.org_id == org_id, OnboardingPayload.client_id == client_id)
            .order_by(OnboardingPayload.created_at.desc())
        )
        return self.session.scalars(stmt).first()
