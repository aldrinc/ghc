from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import AgentRunStatusEnum, AgentToolCallStatusEnum
from app.db.models import AgentRun, AgentToolCall


class AgentRunsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, *, run_id: str, org_id: Optional[str] = None) -> Optional[AgentRun]:
        stmt = select(AgentRun).where(AgentRun.id == run_id)
        if org_id:
            stmt = stmt.where(AgentRun.org_id == org_id)
        return self.session.scalars(stmt).first()

    def create_run(
        self,
        *,
        org_id: str,
        user_id: str,
        objective_type: str,
        client_id: Optional[str] = None,
        funnel_id: Optional[str] = None,
        page_id: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        ruleset_version: Optional[str] = None,
        inputs_json: Optional[dict[str, Any]] = None,
    ) -> AgentRun:
        run = AgentRun(
            org_id=org_id,
            user_id=user_id,
            client_id=client_id,
            funnel_id=funnel_id,
            page_id=page_id,
            objective_type=objective_type,
            status=AgentRunStatusEnum.running,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            ruleset_version=ruleset_version,
            inputs_json=inputs_json or {},
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def finish_run(
        self,
        *,
        run_id: str,
        status: AgentRunStatusEnum,
        outputs_json: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Optional[AgentRun]:
        run = self.get(run_id=run_id)
        if not run:
            return None
        run.status = status
        run.outputs_json = outputs_json
        run.error = error
        run.finished_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(run)
        return run


class AgentToolCallsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_call(
        self,
        *,
        run_id: str,
        seq: int,
        tool_name: str,
        args_json: Optional[dict[str, Any]] = None,
    ) -> AgentToolCall:
        call = AgentToolCall(
            run_id=run_id,
            seq=seq,
            tool_name=tool_name,
            status=AgentToolCallStatusEnum.running,
            args_json=args_json or {},
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(call)
        self.session.commit()
        self.session.refresh(call)
        return call

    def finish_call(
        self,
        *,
        call_id: str,
        status: AgentToolCallStatusEnum,
        result_json: Optional[dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
    ) -> Optional[AgentToolCall]:
        stmt = select(AgentToolCall).where(AgentToolCall.id == call_id)
        call = self.session.scalars(stmt).first()
        if not call:
            return None
        call.status = status
        call.result_json = result_json
        call.duration_ms = duration_ms
        call.error = error
        call.finished_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(call)
        return call

    def list_for_run(self, *, run_id: str) -> list[AgentToolCall]:
        stmt = select(AgentToolCall).where(AgentToolCall.run_id == run_id).order_by(AgentToolCall.seq.asc())
        return list(self.session.scalars(stmt).all())

