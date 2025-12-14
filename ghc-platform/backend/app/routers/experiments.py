from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.repositories.experiments import ExperimentsRepository

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("")
def list_experiments(
    campaignId: str | None = None,
    clientId: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    repo = ExperimentsRepository(session)
    return jsonable_encoder(repo.list(org_id=auth.org_id, campaign_id=campaignId, client_id=clientId))
