from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Client


class ClientsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, org_id: str, limit: int = 50, offset: int = 0) -> List[Client]:
        stmt = (
            select(Client)
            .where(Client.org_id == org_id)
            .order_by(Client.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(stmt).all())

    def get(self, org_id: str, client_id: str) -> Optional[Client]:
        stmt = select(Client).where(Client.org_id == org_id, Client.id == client_id)
        return self.session.scalars(stmt).first()

    def create(self, org_id: str, name: str, **fields) -> Client:
        client = Client(org_id=org_id, name=name, **fields)
        self.session.add(client)
        self.session.commit()
        self.session.refresh(client)
        return client

    def update(self, org_id: str, client_id: str, **fields) -> Optional[Client]:
        client = self.get(org_id, client_id)
        if not client:
            return None
        for key, value in fields.items():
            setattr(client, key, value)
        self.session.commit()
        self.session.refresh(client)
        return client

    def delete(self, org_id: str, client_id: str) -> bool:
        client = self.get(org_id, client_id)
        if not client:
            return False
        self.session.delete(client)
        self.session.commit()
        return True
