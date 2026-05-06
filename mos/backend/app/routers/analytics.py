from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.repositories.client_posthog_settings import ClientPosthogSettingsRepository
from app.db.repositories.clients import ClientsRepository
from app.schemas.analytics import (
    ClientPosthogSettingsRequest,
    ClientPosthogSettingsResponse,
    ClientPosthogSnippetParseRequest,
)
from app.services.posthog_workspace_settings import (
    build_posthog_tracking_payload,
    normalize_posthog_settings_payload,
    parse_posthog_snippet,
    serialize_posthog_settings_record,
)

router = APIRouter(prefix="/clients/{client_id}/analytics", tags=["analytics"])


def _require_client(session: Session, *, org_id: str, client_id: str) -> None:
    client = ClientsRepository(session).get(org_id=org_id, client_id=client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")


def _serialize_response(record) -> dict:
    return jsonable_encoder(
        ClientPosthogSettingsResponse.model_validate(serialize_posthog_settings_record(record))
    )


@router.get("/posthog")
def get_posthog_settings(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    record = ClientPosthogSettingsRepository(session).get(org_id=auth.org_id, client_id=client_id)
    return _serialize_response(record)


@router.post("/posthog/parse-snippet")
def parse_posthog_settings_snippet(
    client_id: str,
    payload: ClientPosthogSnippetParseRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    try:
        parsed = parse_posthog_snippet(payload.snippet)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return jsonable_encoder(
        ClientPosthogSettingsResponse.model_validate(
            {
                "has_settings": False,
                **parsed,
                "resolved_tracking": build_posthog_tracking_payload(parsed),
                "created_at": None,
                "updated_at": None,
            }
        )
    )


@router.put("/posthog")
def put_posthog_settings(
    client_id: str,
    payload: ClientPosthogSettingsRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repository = ClientPosthogSettingsRepository(session)
    try:
        normalized_payload = payload.model_dump(by_alias=False)
        normalized = normalize_posthog_settings_payload(
            normalized_payload,
            enforce_source_contract=True,
        )
        record = repository.upsert(
            org_id=auth.org_id,
            client_id=client_id,
            created_by_user_id=auth.user_id,
            **normalized,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except Exception:
        session.rollback()
        raise
    return _serialize_response(record)
