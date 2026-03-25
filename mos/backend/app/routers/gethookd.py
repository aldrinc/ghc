from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.repositories.clients import ClientsRepository
from app.db.repositories.gethookd import GetHookdCredentialsRepository, GetHookdSyncFeedsRepository
from app.schemas.gethookd import (
    GetHookdCredentialsRequest,
    GetHookdCredentialsResponse,
    GetHookdSyncFeedCreateRequest,
    GetHookdSyncFeedResponse,
    GetHookdSyncFeedUpdateRequest,
)
from app.services.gethookd_client import create_gethookd_client
from app.services.gethookd_schedule import reconcile_client_gethookd_schedule
from app.services.integration_secrets import IntegrationSecretError, encrypt_secret_json

router = APIRouter(prefix="/clients/{client_id}/gethookd", tags=["gethookd"])


def _require_client(session: Session, *, org_id: str, client_id: str) -> None:
    client = ClientsRepository(session).get(org_id=org_id, client_id=client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")


def _serialize_feed(feed) -> GetHookdSyncFeedResponse:
    return GetHookdSyncFeedResponse.model_validate(
        {
            "id": str(feed.id),
            "name": feed.name,
            "enabled": bool(feed.enabled),
            "filters": feed.filters_json or {},
            "maxPagesPerRun": int(feed.max_pages_per_run or 0),
            "perPage": int(feed.per_page or 0),
            "createdAt": feed.created_at,
            "updatedAt": feed.updated_at,
        }
    )


def _reconcile_schedule(*, session: Session, org_id: str, client_id: str) -> None:
    creds = GetHookdCredentialsRepository(session).get(org_id=org_id, client_id=client_id)
    enabled_feed_count = len(
        GetHookdSyncFeedsRepository(session).list(
            org_id=org_id,
            client_id=client_id,
            enabled_only=True,
        )
    )
    asyncio.run(
        reconcile_client_gethookd_schedule(
            org_id=org_id,
            client_id=client_id,
            has_credentials=creds is not None,
            enabled_feed_count=enabled_feed_count,
        )
    )


@router.get("/credentials")
def get_credentials(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = GetHookdCredentialsRepository(session)
    creds = repo.get(org_id=auth.org_id, client_id=client_id)
    return jsonable_encoder(
        GetHookdCredentialsResponse.model_validate(
            {
                "hasCredentials": creds is not None,
                "lastValidatedAt": getattr(creds, "last_validated_at", None),
                "lastValidationError": getattr(creds, "last_validation_error", None),
            }
        )
    )


@router.put("/credentials")
def put_credentials(
    client_id: str,
    payload: GetHookdCredentialsRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    try:
        client = create_gethookd_client(payload.api_token)
        is_valid, error_message = client.validate_credentials()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to validate GetHookd credentials: {exc}",
        ) from exc

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_message or "GetHookd credential validation failed.",
        )

    try:
        encrypted = encrypt_secret_json({"apiToken": payload.api_token})
    except IntegrationSecretError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    repo = GetHookdCredentialsRepository(session)
    creds = repo.upsert(
        org_id=auth.org_id,
        client_id=client_id,
        credentials_encrypted=encrypted,
    )
    repo.update_validation(
        org_id=auth.org_id,
        client_id=client_id,
        last_validated_at=datetime.now(timezone.utc),
        last_validation_error=None,
    )
    try:
        _reconcile_schedule(session=session, org_id=auth.org_id, client_id=client_id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return jsonable_encoder(
        GetHookdCredentialsResponse.model_validate(
            {
                "hasCredentials": True,
                "lastValidatedAt": creds.last_validated_at or datetime.now(timezone.utc),
                "lastValidationError": None,
            }
        )
    )


@router.get("/sync-feeds")
def list_sync_feeds(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    feeds = GetHookdSyncFeedsRepository(session).list(org_id=auth.org_id, client_id=client_id)
    return jsonable_encoder([_serialize_feed(feed) for feed in feeds])


@router.post("/sync-feeds", status_code=status.HTTP_201_CREATED)
def create_sync_feed(
    client_id: str,
    payload: GetHookdSyncFeedCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    feed = GetHookdSyncFeedsRepository(session).create(
        org_id=auth.org_id,
        client_id=client_id,
        name=payload.name,
        filters_json=payload.filters_json,
        max_pages_per_run=payload.max_pages_per_run,
        per_page=payload.per_page,
    )
    if not payload.enabled:
        feed = (
            GetHookdSyncFeedsRepository(session).update(
                org_id=auth.org_id,
                feed_id=str(feed.id),
                enabled=False,
            )
            or feed
        )
    try:
        _reconcile_schedule(session=session, org_id=auth.org_id, client_id=client_id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return jsonable_encoder(_serialize_feed(feed))


@router.put("/sync-feeds/{feed_id}")
def update_sync_feed(
    client_id: str,
    feed_id: str,
    payload: GetHookdSyncFeedUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    update_fields = payload.model_dump(exclude_none=True, by_alias=False)
    feed = GetHookdSyncFeedsRepository(session).update(
        org_id=auth.org_id,
        feed_id=feed_id,
        **update_fields,
    )
    if feed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="GetHookd sync feed not found"
        )
    try:
        _reconcile_schedule(session=session, org_id=auth.org_id, client_id=client_id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return jsonable_encoder(_serialize_feed(feed))


@router.delete("/sync-feeds/{feed_id}")
def delete_sync_feed(
    client_id: str,
    feed_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    deleted = GetHookdSyncFeedsRepository(session).delete(org_id=auth.org_id, feed_id=feed_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="GetHookd sync feed not found"
        )
    try:
        _reconcile_schedule(session=session, org_id=auth.org_id, client_id=client_id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"deleted": True}
