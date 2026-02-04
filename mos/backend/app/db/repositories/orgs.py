from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Org


class OrgsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_external_id(self, external_id: str) -> Optional[Org]:
        stmt = select(Org).where(Org.external_id == external_id)
        return self.session.scalars(stmt).first()

    def create(self, name: str, external_id: str) -> Org:
        org = Org(name=name, external_id=external_id)
        self.session.add(org)
        self.session.commit()
        self.session.refresh(org)
        return org
