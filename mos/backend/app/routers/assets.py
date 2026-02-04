from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.repositories.assets import AssetsRepository
from app.db.enums import AssetStatusEnum
from app.db.models import Client, Funnel, Product
from app.schemas.assets import AssetUpdateRequest
from app.schemas.funnels import GenerateFunnelImageRequest
from app.services.funnels import create_funnel_image_asset
from app.services.media_storage import MediaStorage

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("")
def list_assets(
    clientId: str | None = None,
    campaignId: str | None = None,
    experimentId: str | None = None,
    productId: str | None = None,
    funnelId: str | None = None,
    assetKind: str | None = None,
    tags: list[str] | None = None,
    statuses: list[str] | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    repo = AssetsRepository(session)
    resolved_statuses: list[AssetStatusEnum] | None = None
    if statuses:
        resolved_statuses = []
        for entry in statuses:
            if entry not in AssetStatusEnum.__members__:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status: {entry}")
            resolved_statuses.append(AssetStatusEnum[entry])
    return jsonable_encoder(
        repo.list(
            org_id=auth.org_id,
            client_id=clientId,
            campaign_id=campaignId,
            experiment_id=experimentId,
            product_id=productId,
            funnel_id=funnelId,
            asset_kind=assetKind,
            tags=tags,
            statuses=resolved_statuses,
        )
    )


@router.get("/{asset_id}/download")
def download_asset(
    asset_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = AssetsRepository(session)
    asset = repo.get(org_id=auth.org_id, asset_id=asset_id)
    if not asset or not asset.storage_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    if asset.file_status and asset.file_status != "ready":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset file is not ready")
    storage = MediaStorage()
    url = storage.presign_get(bucket=storage.bucket, key=asset.storage_key)
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.post("/generate-image", status_code=status.HTTP_201_CREATED)
def generate_funnel_image(
    payload: GenerateFunnelImageRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    client = session.scalars(select(Client).where(Client.org_id == auth.org_id, Client.id == payload.clientId)).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    asset = create_funnel_image_asset(
        session=session,
        org_id=auth.org_id,
        client_id=payload.clientId,
        prompt=payload.prompt,
        aspect_ratio=payload.aspectRatio,
        usage_context=payload.usageContext,
    )
    return {
        "assetId": str(asset.id),
        "publicId": str(asset.public_id),
        "width": asset.width,
        "height": asset.height,
        "url": f"/public/assets/{asset.public_id}",
    }


@router.patch("/{asset_id}")
def update_asset(
    asset_id: str,
    payload: AssetUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = AssetsRepository(session)
    asset = repo.get(org_id=auth.org_id, asset_id=asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    fields: dict[str, object] = {}
    fields_set = payload.model_fields_set

    if "assetKind" in fields_set:
        if payload.assetKind is None or not str(payload.assetKind).strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="assetKind cannot be empty")
        fields["asset_kind"] = payload.assetKind

    if "tags" in fields_set:
        if payload.tags is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tags cannot be null")
        cleaned: list[str] = []
        for tag in payload.tags:
            if not isinstance(tag, str) or not tag.strip():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tags must be non-empty strings")
            cleaned.append(tag.strip())
        fields["tags"] = cleaned

    if "alt" in fields_set:
        if payload.alt is not None and not str(payload.alt).strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="alt cannot be empty")
        fields["alt"] = payload.alt

    if "productId" in fields_set:
        if payload.productId is None:
            fields["product_id"] = None
        else:
            if not str(payload.productId).strip():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="productId cannot be empty")
            product = session.scalars(
                select(Product).where(
                    Product.org_id == auth.org_id,
                    Product.client_id == asset.client_id,
                    Product.id == payload.productId,
                )
            ).first()
            if not product:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
            fields["product_id"] = payload.productId

    if "funnelId" in fields_set:
        if payload.funnelId is None:
            fields["funnel_id"] = None
        else:
            if not str(payload.funnelId).strip():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="funnelId cannot be empty")
            funnel = session.scalars(
                select(Funnel).where(
                    Funnel.org_id == auth.org_id,
                    Funnel.client_id == asset.client_id,
                    Funnel.id == payload.funnelId,
                )
            ).first()
            if not funnel:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")
            fields["funnel_id"] = payload.funnelId

    if not fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No updates provided")

    updated = repo.update(org_id=auth.org_id, asset_id=asset_id, **fields)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return jsonable_encoder(updated)
