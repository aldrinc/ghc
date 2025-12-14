from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Experiment


class ExperimentsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(
        self, org_id: str, campaign_id: Optional[str] = None, client_id: Optional[str] = None
    ) -> List[Experiment]:
        stmt = select(Experiment).where(Experiment.org_id == org_id)
        if campaign_id:
            stmt = stmt.where(Experiment.campaign_id == campaign_id)
        if client_id:
            stmt = stmt.where(Experiment.client_id == client_id)
        return list(self.session.scalars(stmt.order_by(Experiment.created_at.desc())).all())

    def get(self, org_id: str, experiment_id: str) -> Optional[Experiment]:
        stmt = select(Experiment).where(Experiment.org_id == org_id, Experiment.id == experiment_id)
        return self.session.scalars(stmt).first()

    def create(self, org_id: str, client_id: str, campaign_id: str, name: str, **fields) -> Experiment:
        exp = Experiment(org_id=org_id, client_id=client_id, campaign_id=campaign_id, name=name, **fields)
        self.session.add(exp)
        self.session.commit()
        self.session.refresh(exp)
        return exp

    def update(self, org_id: str, experiment_id: str, **fields) -> Optional[Experiment]:
        exp = self.get(org_id, experiment_id)
        if not exp:
            return None
        for key, value in fields.items():
            setattr(exp, key, value)
        self.session.commit()
        self.session.refresh(exp)
        return exp
