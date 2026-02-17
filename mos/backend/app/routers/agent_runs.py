from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.models import AgentArtifact, AgentRun, AgentToolCall


router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


@router.get("/{run_id}")
def get_run(
    run_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    run = session.scalars(select(AgentRun).where(AgentRun.id == run_id, AgentRun.org_id == auth.org_id)).first()
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    calls = list(
        session.scalars(select(AgentToolCall).where(AgentToolCall.run_id == run_id).order_by(AgentToolCall.seq.asc())).all()
    )
    return {"run": jsonable_encoder(run), "toolCalls": jsonable_encoder(calls)}


@router.get("/{run_id}/artifacts")
def list_run_artifacts(
    run_id: str,
    kind: str | None = None,
    key: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    run = session.scalars(select(AgentRun).where(AgentRun.id == run_id, AgentRun.org_id == auth.org_id)).first()
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    stmt = select(AgentArtifact).where(AgentArtifact.run_id == run_id).order_by(AgentArtifact.created_at.asc())
    if kind:
        stmt = stmt.where(AgentArtifact.kind == kind)
    if key:
        stmt = stmt.where(AgentArtifact.key == key)
    artifacts = list(session.scalars(stmt).all())
    return {"artifacts": jsonable_encoder(artifacts)}
