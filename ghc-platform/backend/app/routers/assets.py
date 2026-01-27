from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.repositories.assets import AssetsRepository
from app.db.models import Client
from app.schemas.funnels import GenerateFunnelImageRequest
from app.services.funnels import create_funnel_image_asset

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
