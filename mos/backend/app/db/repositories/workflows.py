from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import WorkflowStatusEnum
from app.db.models import ActivityLog, WorkflowRun


class WorkflowsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(
        self,
        org_id: str,
        client_id: str | None = None,
        campaign_id: str | None = None,
        product_id: str | None = None,
    ) -> List[WorkflowRun]:
        stmt = select(WorkflowRun).where(WorkflowRun.org_id == org_id)
        if client_id:
            stmt = stmt.where(WorkflowRun.client_id == client_id)
        if product_id:
            stmt = stmt.where(WorkflowRun.product_id == product_id)
        if campaign_id:
            stmt = stmt.where(WorkflowRun.campaign_id == campaign_id)
        stmt = stmt.order_by(WorkflowRun.started_at.desc())
        return list(self.session.scalars(stmt).all())

    def create_run(
        self,
        org_id: str,
        temporal_workflow_id: str,
        temporal_run_id: str,
        kind: str,
        client_id: str | None = None,
        product_id: str | None = None,
        campaign_id: str | None = None,
    ) -> WorkflowRun:
        run = WorkflowRun(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            temporal_workflow_id=temporal_workflow_id,
            temporal_run_id=temporal_run_id,
            kind=kind,
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def get(self, org_id: str, workflow_run_id: str) -> Optional[WorkflowRun]:
        stmt = select(WorkflowRun).where(WorkflowRun.org_id == org_id, WorkflowRun.id == workflow_run_id)
        return self.session.scalars(stmt).first()

    def get_by_temporal_ids(
        self, org_id: str, temporal_workflow_id: str, temporal_run_id: str
    ) -> Optional[WorkflowRun]:
        stmt = (
            select(WorkflowRun)
            .where(
                WorkflowRun.org_id == org_id,
                WorkflowRun.temporal_workflow_id == temporal_workflow_id,
                WorkflowRun.temporal_run_id == temporal_run_id,
            )
            .order_by(WorkflowRun.started_at.desc())
        )
        return self.session.scalars(stmt).first()

    def set_status(
        self,
        org_id: str,
        workflow_run_id: str,
        status: WorkflowStatusEnum,
        finished_at=None,
    ) -> Optional[WorkflowRun]:
        run = self.get(org_id, workflow_run_id)
        if not run:
            return None
        run.status = status
        if finished_at:
            run.finished_at = finished_at
        self.session.commit()
        self.session.refresh(run)
        return run

    def log_activity(
        self,
        workflow_run_id: str,
        step: str,
        status: str,
        payload_in=None,
        payload_out=None,
        error: str | None = None,
    ) -> ActivityLog:
        log = ActivityLog(
            workflow_run_id=workflow_run_id,
            step=step,
            status=status,
            payload_in=payload_in,
            payload_out=payload_out,
            error=error,
        )
        self.session.add(log)
        self.session.commit()
        self.session.refresh(log)
        return log

    def list_logs(self, org_id: str, workflow_run_id: str) -> List[ActivityLog]:
        # org_id currently not stored on ActivityLog; rely on workflow run ownership for now.
        run = self.get(org_id=org_id, workflow_run_id=workflow_run_id)
        if not run:
            return []
        stmt = select(ActivityLog).where(ActivityLog.workflow_run_id == workflow_run_id).order_by(ActivityLog.created_at.desc())
        return list(self.session.scalars(stmt).all())

    def has_onboarding_approvals(
        self, org_id: str, client_id: str, product_id: str | None = None
    ) -> bool:
        stmt = (
            select(ActivityLog.step)
            .join(WorkflowRun, ActivityLog.workflow_run_id == WorkflowRun.id)
            .where(
                WorkflowRun.org_id == org_id,
                WorkflowRun.client_id == client_id,
                WorkflowRun.kind == "client_onboarding",
                ActivityLog.step.in_(["approve_canon", "approve_metric_schema"]),
            )
        )
        if product_id:
            stmt = stmt.where(WorkflowRun.product_id == product_id)
        steps = {row[0] for row in self.session.execute(stmt).all()}
        return "approve_canon" in steps and "approve_metric_schema" in steps
