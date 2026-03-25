from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.db.models import ClientGetHookdCredentials, ClientGetHookdSyncFeed, GetHookdSyncRun


class GetHookdCredentialsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, org_id: str, client_id: str) -> Optional[ClientGetHookdCredentials]:
        stmt = select(ClientGetHookdCredentials).where(
            ClientGetHookdCredentials.org_id == org_id,
            ClientGetHookdCredentials.client_id == client_id,
        )
        return self.session.scalars(stmt).first()

    def upsert(
        self,
        *,
        org_id: str,
        client_id: str,
        credentials_encrypted: str,
    ) -> ClientGetHookdCredentials:
        stmt = (
            insert(ClientGetHookdCredentials)
            .values(
                org_id=org_id,
                client_id=client_id,
                credentials_encrypted=credentials_encrypted,
            )
            .on_conflict_do_update(
                index_elements=["org_id", "client_id"],
                set_={
                    "credentials_encrypted": credentials_encrypted,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            .returning(ClientGetHookdCredentials)
        )
        result = self.session.execute(stmt).scalar_one()
        self.session.flush()
        self.session.refresh(result)
        return result

    def update_validation(
        self,
        *,
        org_id: str,
        client_id: str,
        last_validated_at: datetime,
        last_validation_error: Optional[str] = None,
    ) -> Optional[ClientGetHookdCredentials]:
        cred = self.get(org_id=org_id, client_id=client_id)
        if cred is None:
            return None
        cred.last_validated_at = last_validated_at
        cred.last_validation_error = last_validation_error
        cred.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        self.session.refresh(cred)
        return cred

    def delete(self, org_id: str, client_id: str) -> bool:
        cred = self.get(org_id=org_id, client_id=client_id)
        if cred is None:
            return False
        self.session.delete(cred)
        self.session.flush()
        return True


class GetHookdSyncFeedsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(
        self,
        *,
        org_id: str,
        client_id: str,
        enabled_only: bool = False,
    ) -> List[ClientGetHookdSyncFeed]:
        stmt = select(ClientGetHookdSyncFeed).where(
            ClientGetHookdSyncFeed.org_id == org_id,
            ClientGetHookdSyncFeed.client_id == client_id,
        )
        if enabled_only:
            stmt = stmt.where(ClientGetHookdSyncFeed.enabled == True)
        return list(self.session.scalars(stmt).all())

    def get(self, org_id: str, feed_id: str) -> Optional[ClientGetHookdSyncFeed]:
        stmt = select(ClientGetHookdSyncFeed).where(
            ClientGetHookdSyncFeed.id == feed_id,
            ClientGetHookdSyncFeed.org_id == org_id,
        )
        return self.session.scalars(stmt).first()

    def create(
        self,
        *,
        org_id: str,
        client_id: str,
        name: str,
        filters_json: dict,
        max_pages_per_run: int = 5,
        per_page: int = 100,
    ) -> ClientGetHookdSyncFeed:
        feed = ClientGetHookdSyncFeed(
            org_id=org_id,
            client_id=client_id,
            name=name,
            filters_json=filters_json,
            max_pages_per_run=max_pages_per_run,
            per_page=per_page,
        )
        self.session.add(feed)
        self.session.flush()
        self.session.refresh(feed)
        return feed

    def update(
        self,
        *,
        org_id: str,
        feed_id: str,
        **fields,
    ) -> Optional[ClientGetHookdSyncFeed]:
        feed = self.get(org_id=org_id, feed_id=feed_id)
        if feed is None:
            return None
        for key, value in fields.items():
            setattr(feed, key, value)
        feed.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        self.session.refresh(feed)
        return feed

    def delete(self, org_id: str, feed_id: str) -> bool:
        feed = self.get(org_id=org_id, feed_id=feed_id)
        if feed is None:
            return False
        self.session.delete(feed)
        self.session.flush()
        return True


class GetHookdSyncRunsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        org_id: str,
        client_id: str,
    ) -> GetHookdSyncRun:
        run = GetHookdSyncRun(
            org_id=org_id,
            client_id=client_id,
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def get(self, org_id: str, run_id: str) -> Optional[GetHookdSyncRun]:
        stmt = select(GetHookdSyncRun).where(
            GetHookdSyncRun.id == run_id,
            GetHookdSyncRun.org_id == org_id,
        )
        return self.session.scalars(stmt).first()

    def update(
        self,
        *,
        run_id: str,
        **fields,
    ) -> Optional[GetHookdSyncRun]:
        run = self.session.get(GetHookdSyncRun, run_id)
        if run is None:
            return None
        for key, value in fields.items():
            setattr(run, key, value)
        self.session.commit()
        self.session.refresh(run)
        return run

    def complete(
        self,
        *,
        run_id: str,
        status: str,
        feeds_attempted: int,
        feeds_succeeded: int,
        assets_new: int,
        assets_updated: int,
        assets_marked_stale: int,
        assets_failed: int,
        credits_used: int,
        error_summary: Optional[str] = None,
    ) -> Optional[GetHookdSyncRun]:
        return self.update(
            run_id=run_id,
            status=status,
            finished_at=datetime.now(timezone.utc),
            feeds_attempted=feeds_attempted,
            feeds_succeeded=feeds_succeeded,
            assets_new=assets_new,
            assets_updated=assets_updated,
            assets_marked_stale=assets_marked_stale,
            assets_failed=assets_failed,
            credits_used=credits_used,
            error_summary=error_summary,
        )
