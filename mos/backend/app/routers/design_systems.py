from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.repositories.clients import ClientsRepository
from app.db.repositories.design_systems import DesignSystemsRepository
from app.schemas.design_systems import DesignSystemCreateRequest, DesignSystemUpdateRequest

router = APIRouter(prefix="/design-systems", tags=["design-systems"])


def _ensure_client_belongs(session: Session, *, org_id: str, client_id: str):
    clients_repo = ClientsRepository(session)
    client = clients_repo.get(org_id=org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


@router.get("")
def list_design_systems(
    clientId: str | None = None,
    includeShared: bool = True,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    repo = DesignSystemsRepository(session)
    return jsonable_encoder(
        repo.list(org_id=auth.org_id, client_id=clientId, include_shared=includeShared if clientId else False)
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_design_system(
    payload: DesignSystemCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    client_id = payload.clientId or None
    client = None
    has_existing = False
    if client_id:
        client = _ensure_client_belongs(session, org_id=auth.org_id, client_id=client_id)

    repo = DesignSystemsRepository(session)
    if client_id:
        has_existing = repo.has_client_design_systems(org_id=auth.org_id, client_id=client_id)
    design_system = repo.create(
        org_id=auth.org_id,
        name=payload.name,
        tokens=payload.tokens,
        client_id=client_id,
    )
    if client_id and client and client.design_system_id is None and not has_existing:
        clients_repo = ClientsRepository(session)
        clients_repo.update(org_id=auth.org_id, client_id=client_id, design_system_id=str(design_system.id))
        session.refresh(design_system)
    return jsonable_encoder(design_system)


@router.get("/{design_system_id}")
def get_design_system(
    design_system_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = DesignSystemsRepository(session)
    design_system = repo.get(org_id=auth.org_id, design_system_id=design_system_id)
    if not design_system:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found")
    return jsonable_encoder(design_system)


@router.patch("/{design_system_id}")
def update_design_system(
    design_system_id: str,
    payload: DesignSystemUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = DesignSystemsRepository(session)
    existing = repo.get(org_id=auth.org_id, design_system_id=design_system_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found")

    fields: dict[str, object] = {}
    if payload.name is not None:
        fields["name"] = payload.name
    if payload.tokens is not None:
        fields["tokens"] = payload.tokens
    if "clientId" in payload.model_fields_set:
        client_id = payload.clientId or None
        if client_id:
            _ensure_client_belongs(session, org_id=auth.org_id, client_id=client_id)
        fields["client_id"] = client_id

    updated = repo.update(org_id=auth.org_id, design_system_id=design_system_id, **fields)
    return jsonable_encoder(updated)


@router.delete("/{design_system_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_design_system(
    design_system_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = DesignSystemsRepository(session)
    deleted = repo.delete(org_id=auth.org_id, design_system_id=design_system_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found")
    return None
