from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.enums import ArtifactTypeEnum
from app.db.repositories.artifacts import ArtifactsRepository

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("")
def list_artifacts(
    clientId: str | None = None,
    campaignId: str | None = None,
    type: ArtifactTypeEnum | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    repo = ArtifactsRepository(session)
    return jsonable_encoder(
        repo.list(
            org_id=auth.org_id,
            client_id=clientId,
            campaign_id=campaignId,
            artifact_type=type,
        )
    )


@router.get("/{artifact_id}")
def get_artifact(
    artifact_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = ArtifactsRepository(session)
    artifact = repo.get(org_id=auth.org_id, artifact_id=artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return jsonable_encoder(artifact)
