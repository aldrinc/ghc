from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.repositories.deep_research_jobs import DeepResearchJobsRepository
from app.services.deep_research import DeepResearchJobService

router = APIRouter(prefix="/deep-research", tags=["deep-research"])


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = DeepResearchJobsRepository(session)
    job = repo.get(job_id=job_id, org_id=auth.org_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return jsonable_encoder(job)


@router.post("/jobs/{job_id}/refresh")
def refresh_job(
    job_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = DeepResearchJobsRepository(session)
    job = repo.get(job_id=job_id, org_id=auth.org_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    service = DeepResearchJobService(session)
    updated = service.refresh_from_openai(job_id=job_id) if job.response_id else job
    return jsonable_encoder(updated or job)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = DeepResearchJobsRepository(session)
    job = repo.get(job_id=job_id, org_id=auth.org_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.response_id:
        raise HTTPException(status_code=400, detail="Job has no response_id to cancel")

    service = DeepResearchJobService(session)
    updated = service.cancel_job(job_id=job_id)
    return jsonable_encoder(updated or job)
