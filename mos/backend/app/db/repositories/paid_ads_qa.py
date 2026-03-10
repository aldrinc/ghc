from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db.models import PaidAdsPlatformProfile, PaidAdsQaFinding, PaidAdsQaRun


class PaidAdsQaRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_platform_profile(
        self,
        *,
        org_id: str,
        client_id: str,
        platform: str,
    ) -> Optional[PaidAdsPlatformProfile]:
        stmt = select(PaidAdsPlatformProfile).where(
            PaidAdsPlatformProfile.org_id == org_id,
            PaidAdsPlatformProfile.client_id == client_id,
            PaidAdsPlatformProfile.platform == platform,
        )
        return self.session.scalars(stmt).first()

    def upsert_platform_profile(self, **fields) -> PaidAdsPlatformProfile:
        record = self.get_platform_profile(
            org_id=fields["org_id"],
            client_id=fields["client_id"],
            platform=fields["platform"],
        )
        if record is None:
            record = PaidAdsPlatformProfile(**fields)
            self.session.add(record)
            self.session.commit()
            self.session.refresh(record)
            return record

        for key, value in fields.items():
            setattr(record, key, value)
        record.updated_at = func.now()
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def create_run(self, **fields) -> PaidAdsQaRun:
        record = PaidAdsQaRun(**fields)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def update_run(self, record: PaidAdsQaRun, **fields) -> PaidAdsQaRun:
        for key, value in fields.items():
            setattr(record, key, value)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def create_findings(self, *, findings: list[dict[str, Any]]) -> list[PaidAdsQaFinding]:
        records = [PaidAdsQaFinding(**fields) for fields in findings]
        self.session.add_all(records)
        self.session.commit()
        for record in records:
            self.session.refresh(record)
        return records

    def get_run(
        self,
        *,
        org_id: str,
        run_id: str,
    ) -> Optional[PaidAdsQaRun]:
        stmt = select(PaidAdsQaRun).where(
            PaidAdsQaRun.org_id == org_id,
            PaidAdsQaRun.id == run_id,
        )
        return self.session.scalars(stmt).first()

    def list_findings(self, *, qa_run_id: str) -> list[PaidAdsQaFinding]:
        stmt = (
            select(PaidAdsQaFinding)
            .where(PaidAdsQaFinding.qa_run_id == qa_run_id)
            .order_by(
                PaidAdsQaFinding.created_at.asc(),
                PaidAdsQaFinding.severity.asc(),
                PaidAdsQaFinding.rule_id.asc(),
            )
        )
        return list(self.session.scalars(stmt).all())
