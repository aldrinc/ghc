from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.repositories.swipes import CompanySwipesRepository, ClientSwipesRepository

router = APIRouter(prefix="/swipes", tags=["swipes"])


@router.get("/company")
def list_company_swipes(
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    repo = CompanySwipesRepository(session)
    return jsonable_encoder(repo.list_assets(org_id=auth.org_id))


@router.get("/client/{client_id}")
def list_client_swipes(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    repo = ClientSwipesRepository(session)
    return jsonable_encoder(repo.list(org_id=auth.org_id, client_id=client_id))
