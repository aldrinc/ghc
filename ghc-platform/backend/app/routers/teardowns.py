from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.repositories.teardowns import TeardownsRepository
from app.schemas.teardowns import TeardownUpsertRequest

router = APIRouter(prefix="/teardowns", tags=["teardowns"])


def _handle_error(exc: Exception, not_found_message: str = "Teardown not found") -> HTTPException:
    message = str(exc)
    if "not found" in message.lower():
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


@router.post("", status_code=status.HTTP_201_CREATED)
def upsert_teardown(
    payload: TeardownUpsertRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = TeardownsRepository(session)
    try:
        result = repo.upsert_teardown(org_id=auth.org_id, payload=payload, created_by_user_id=auth.user_id)
        return jsonable_encoder(result)
    except Exception as exc:  # noqa: BLE001
        raise _handle_error(exc)


@router.get("/{teardown_id}")
def get_teardown(
    teardown_id: str,
    include_children: bool = True,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = TeardownsRepository(session)
    try:
        result = repo.get_by_id(org_id=auth.org_id, teardown_id=teardown_id, include_children=include_children)
        return jsonable_encoder(result)
    except Exception as exc:  # noqa: BLE001
        raise _handle_error(exc)


@router.get("/by-creative/{creative_id}")
def get_teardown_by_creative(
    creative_id: str,
    include_children: bool = True,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = TeardownsRepository(session)
    try:
        result = repo.get_canonical_for_creative(
            org_id=auth.org_id, creative_id=creative_id, include_children=include_children
        )
        return jsonable_encoder(result)
    except Exception as exc:  # noqa: BLE001
        raise _handle_error(exc)


@router.get("/by-ad/{ad_id}")
def get_teardown_by_ad(
    ad_id: str,
    include_children: bool = True,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = TeardownsRepository(session)
    try:
        result = repo.get_canonical_for_ad(org_id=auth.org_id, ad_id=ad_id, include_children=include_children)
        return jsonable_encoder(result)
    except Exception as exc:  # noqa: BLE001
        raise _handle_error(exc)


@router.get("")
def search_teardowns(
    clientId: str | None = None,
    campaignId: str | None = None,
    hookType: str | None = None,
    proofType: str | None = None,
    beatKey: str | None = None,
    signalCategory: str | None = None,
    numericUnit: str | None = None,
    claimTopic: str | None = None,
    claimTextContains: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    includeChildren: bool = False,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = TeardownsRepository(session)
    try:
        results = repo.search(
            org_id=auth.org_id,
            client_id=clientId,
            campaign_id=campaignId,
            hook_type=hookType,
            proof_type=proofType,
            beat_key=beatKey,
            signal_category=signalCategory,
            numeric_unit=numericUnit,
            claim_topic=claimTopic,
            claim_text_contains=claimTextContains,
            limit=limit,
            offset=offset,
            include_children=includeChildren,
        )
        return jsonable_encoder(results)
    except Exception as exc:  # noqa: BLE001
        raise _handle_error(exc)
