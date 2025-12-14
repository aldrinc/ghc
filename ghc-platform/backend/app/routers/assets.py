from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.repositories.assets import AssetsRepository

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("")
def list_assets(
    clientId: str | None = None,
    campaignId: str | None = None,
    experimentId: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    repo = AssetsRepository(session)
    return jsonable_encoder(
        repo.list(
            org_id=auth.org_id,
            client_id=clientId,
            campaign_id=campaignId,
            experiment_id=experimentId,
        )
    )
