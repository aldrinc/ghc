from __future__ import annotations

from typing import Optional

from sqlalchemy import asc, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import StrategyV2Launch
from app.db.repositories.base import Repository


class StrategyV2LaunchesRepository(Repository):
    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def create(self, **fields) -> StrategyV2Launch:
        row = StrategyV2Launch(**fields)
        self.session.add(row)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise
        self.session.refresh(row)
        return row

    def list_for_source_run(
        self,
        *,
        org_id: str,
        source_strategy_v2_workflow_run_id: str,
    ) -> list[StrategyV2Launch]:
        stmt = (
            select(StrategyV2Launch)
            .where(
                StrategyV2Launch.org_id == org_id,
                StrategyV2Launch.source_strategy_v2_workflow_run_id == source_strategy_v2_workflow_run_id,
            )
            .order_by(desc(StrategyV2Launch.created_at))
        )
        return list(self.session.scalars(stmt).all())

    def list_for_campaign(
        self,
        *,
        org_id: str,
        campaign_id: str,
    ) -> list[StrategyV2Launch]:
        stmt = (
            select(StrategyV2Launch)
            .where(
                StrategyV2Launch.org_id == org_id,
                StrategyV2Launch.campaign_id == campaign_id,
            )
            .order_by(desc(StrategyV2Launch.created_at))
        )
        return list(self.session.scalars(stmt).all())

    def get_by_launch_key(self, *, org_id: str, launch_key: str) -> Optional[StrategyV2Launch]:
        stmt = select(StrategyV2Launch).where(
            StrategyV2Launch.org_id == org_id,
            StrategyV2Launch.launch_key == launch_key,
        )
        return self.session.scalars(stmt).first()

    def get_by_angle_run_and_ums(
        self,
        *,
        org_id: str,
        angle_run_id: str,
        selected_ums_id: str,
    ) -> Optional[StrategyV2Launch]:
        stmt = select(StrategyV2Launch).where(
            StrategyV2Launch.org_id == org_id,
            StrategyV2Launch.angle_run_id == angle_run_id,
            StrategyV2Launch.selected_ums_id == selected_ums_id,
        )
        return self.session.scalars(stmt).first()

    def next_launch_index(
        self,
        *,
        org_id: str,
        client_id: str,
        product_id: str,
        angle_id: str,
    ) -> int:
        stmt = (
            select(func.max(StrategyV2Launch.launch_index))
            .where(
                StrategyV2Launch.org_id == org_id,
                StrategyV2Launch.client_id == client_id,
                StrategyV2Launch.product_id == product_id,
                StrategyV2Launch.angle_id == angle_id,
                StrategyV2Launch.launch_index.is_not(None),
            )
        )
        max_value = self.session.execute(stmt).scalar_one_or_none()
        if not isinstance(max_value, int):
            return 1
        return max_value + 1

    def list_for_launch_workflow_run(
        self,
        *,
        org_id: str,
        launch_workflow_run_id: str,
    ) -> list[StrategyV2Launch]:
        stmt = (
            select(StrategyV2Launch)
            .where(
                StrategyV2Launch.org_id == org_id,
                StrategyV2Launch.launch_workflow_run_id == launch_workflow_run_id,
            )
            .order_by(asc(StrategyV2Launch.created_at))
        )
        return list(self.session.scalars(stmt).all())
