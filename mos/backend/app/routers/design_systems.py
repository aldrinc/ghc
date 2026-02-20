from __future__ import annotations

import mimetypes
from copy import deepcopy

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.repositories.clients import ClientsRepository
from app.db.repositories.design_systems import DesignSystemsRepository
from app.schemas.design_systems import DesignSystemCreateRequest, DesignSystemUpdateRequest
from app.services.assets import create_client_logo_upload_asset
from app.services.design_system_generation import (
    DesignSystemGenerationError,
    validate_design_system_tokens,
)

router = APIRouter(prefix="/design-systems", tags=["design-systems"])
_DESIGN_SYSTEM_LOGO_MAX_BYTES = 20 * 1024 * 1024
_DESIGN_SYSTEM_LOGO_ALLOWED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
}


def _ensure_client_belongs(session: Session, *, org_id: str, client_id: str):
    clients_repo = ClientsRepository(session)
    client = clients_repo.get(org_id=org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


def _validated_tokens_or_422(tokens: dict[str, object]) -> dict[str, object]:
    try:
        return validate_design_system_tokens(tokens)
    except DesignSystemGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


def _resolve_logo_content_type_or_400(file: UploadFile) -> str:
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if not content_type and file.filename:
        guessed = mimetypes.guess_type(file.filename)[0]
        if guessed:
            content_type = guessed.lower()
    if not content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to determine file type for {file.filename or 'upload'}.",
        )
    if content_type not in _DESIGN_SYSTEM_LOGO_ALLOWED_MIME_TYPES:
        allowed = ", ".join(sorted(_DESIGN_SYSTEM_LOGO_ALLOWED_MIME_TYPES))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported logo file type ({content_type}). Allowed image types: {allowed}.",
        )
    return content_type


def _apply_logo_to_tokens_or_422(
    *,
    tokens: object,
    logo_public_id: str,
    default_logo_alt: str,
) -> dict[str, object]:
    if not isinstance(tokens, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Design system tokens must be a JSON object.",
        )
    next_tokens = deepcopy(tokens)
    brand = next_tokens.get("brand")
    if brand is None:
        brand_obj: dict[str, object] = {}
    elif isinstance(brand, dict):
        brand_obj = deepcopy(brand)
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Design system tokens.brand must be a JSON object.",
        )
    brand_obj["logoAssetPublicId"] = logo_public_id
    logo_alt = brand_obj.get("logoAlt")
    if not isinstance(logo_alt, str) or not logo_alt.strip():
        brand_obj["logoAlt"] = default_logo_alt
    next_tokens["brand"] = brand_obj
    return _validated_tokens_or_422(next_tokens)


@router.get("")
def list_design_systems(
    clientId: str | None = None,
    includeShared: bool = True,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    repo = DesignSystemsRepository(session)
    return jsonable_encoder(
        repo.list(
            org_id=auth.org_id,
            client_id=clientId,
            include_shared=includeShared if clientId else False,
        )
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
    validated_tokens = _validated_tokens_or_422(payload.tokens)
    design_system = repo.create(
        org_id=auth.org_id,
        name=payload.name,
        tokens=validated_tokens,
        client_id=client_id,
    )
    if client_id and client and client.design_system_id is None and not has_existing:
        clients_repo = ClientsRepository(session)
        clients_repo.update(
            org_id=auth.org_id, client_id=client_id, design_system_id=str(design_system.id)
        )
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
        fields["tokens"] = _validated_tokens_or_422(payload.tokens)
    if "clientId" in payload.model_fields_set:
        client_id = payload.clientId or None
        if client_id:
            _ensure_client_belongs(session, org_id=auth.org_id, client_id=client_id)
        fields["client_id"] = client_id

    updated = repo.update(org_id=auth.org_id, design_system_id=design_system_id, **fields)
    return jsonable_encoder(updated)


@router.post("/{design_system_id}/logo", status_code=status.HTTP_201_CREATED)
async def upload_design_system_logo(
    design_system_id: str,
    file: UploadFile = File(...),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = DesignSystemsRepository(session)
    design_system = repo.get(org_id=auth.org_id, design_system_id=design_system_id)
    if not design_system:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found")
    if not design_system.client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Design system must be workspace-scoped to upload a brand logo.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File {file.filename or 'upload'} is empty.",
        )
    if len(content) > _DESIGN_SYSTEM_LOGO_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File {file.filename or 'upload'} exceeds {_DESIGN_SYSTEM_LOGO_MAX_BYTES} bytes.",
        )
    content_type = _resolve_logo_content_type_or_400(file)

    try:
        asset = create_client_logo_upload_asset(
            session=session,
            org_id=auth.org_id,
            client_id=str(design_system.client_id),
            content_bytes=content,
            filename=file.filename,
            content_type=content_type,
            tags=["brand_logo", "design_system"],
            alt=f"{design_system.name} logo",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    tokens = _apply_logo_to_tokens_or_422(
        tokens=design_system.tokens,
        logo_public_id=str(asset.public_id),
        default_logo_alt=str(design_system.name),
    )
    updated = repo.update(
        org_id=auth.org_id,
        design_system_id=design_system_id,
        tokens=tokens,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design system not found")
    return {
        "assetId": str(asset.id),
        "publicId": str(asset.public_id),
        "url": f"/public/assets/{asset.public_id}",
        "designSystem": jsonable_encoder(updated),
    }


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
