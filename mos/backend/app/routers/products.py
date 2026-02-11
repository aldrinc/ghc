from __future__ import annotations

import mimetypes
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.config import settings
from app.db.deps import get_session
from app.db.repositories.assets import AssetsRepository
from app.db.models import Asset
from app.db.repositories.products import (
    ProductOffersRepository,
    ProductOfferPricePointsRepository,
    ProductsRepository,
)
from app.services.assets import create_product_upload_asset
from app.services.media_storage import MediaStorage
from app.schemas.products import (
    ProductCreateRequest,
    ProductOfferCreateRequest,
    ProductOfferPricePointCreateRequest,
    ProductOfferPricePointUpdateRequest,
    ProductOfferUpdateRequest,
    ProductUpdateRequest,
)

router = APIRouter(prefix="/products", tags=["products"])

_SUPPORTED_PRICE_PROVIDERS = {"stripe"}
_PRODUCT_ASSET_KIND_BY_MIME: dict[str, str] = {
    "image/png": "image",
    "image/jpeg": "image",
    "image/jpg": "image",
    "image/webp": "image",
    "image/gif": "image",
    "video/mp4": "video",
    "video/webm": "video",
    "video/quicktime": "video",
    "application/pdf": "document",
    "application/msword": "document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
}
_PRODUCT_ASSET_ALLOWED_SUMMARY = (
    "Images (png, jpeg, webp, gif), videos (mp4, webm, mov), documents (pdf, doc, docx)."
)
_PRODUCT_ASSET_MAX_BYTES = 200 * 1024 * 1024


def _resolve_product_asset_content_type(file: UploadFile) -> str:
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
    return content_type


def _resolve_product_asset_kind(content_type: str, filename: str | None) -> str:
    asset_kind = _PRODUCT_ASSET_KIND_BY_MIME.get(content_type)
    if asset_kind:
        return asset_kind
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Unsupported file type for {filename or 'upload'} "
            f"({content_type or 'unknown'}). Allowed: {_PRODUCT_ASSET_ALLOWED_SUMMARY}"
        ),
    )


def _serialize_product_asset(asset, primary_asset_id: str | None, storage: MediaStorage) -> dict:
    data = jsonable_encoder(asset)
    if asset.storage_key:
        data["download_url"] = storage.presign_get(bucket=storage.bucket, key=asset.storage_key)
    else:
        data["download_url"] = None
    data["is_primary"] = bool(primary_asset_id and str(asset.id) == primary_asset_id)
    return data


def _is_asset_active(asset: Asset, *, now: datetime) -> bool:
    expires_at = getattr(asset, "expires_at", None)
    if expires_at is None:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > now


@router.get("")
def list_products(
    clientId: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not clientId:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="clientId is required")
    repo = ProductsRepository(session)
    products = repo.list(org_id=auth.org_id, client_id=clientId)
    primary_ids = [str(product.primary_asset_id) for product in products if product.primary_asset_id]
    asset_map: dict[str, Asset] = {}
    storage: MediaStorage | None = None
    if primary_ids:
        assets = session.scalars(
            select(Asset).where(Asset.org_id == auth.org_id, Asset.id.in_(primary_ids))
        ).all()
        asset_map = {str(asset.id): asset for asset in assets}
        if asset_map:
            storage = MediaStorage()

    results = []
    for product in products:
        primary_url = None
        if product.primary_asset_id and storage:
            asset = asset_map.get(str(product.primary_asset_id))
            if (
                asset
                and asset.asset_kind == "image"
                and asset.storage_key
                and asset.product_id
                and str(asset.product_id) == str(product.id)
            ):
                primary_url = storage.presign_get(bucket=storage.bucket, key=asset.storage_key)
        data = jsonable_encoder(product)
        data["primary_asset_url"] = primary_url
        results.append(data)
    return results


@router.post("", status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    fields: dict[str, object] = {
        "name": payload.name,
    }
    if payload.description is not None:
        fields["description"] = payload.description
    if payload.category is not None:
        fields["category"] = payload.category
    if payload.primaryBenefits is not None:
        fields["primary_benefits"] = payload.primaryBenefits
    if payload.featureBullets is not None:
        fields["feature_bullets"] = payload.featureBullets
    if payload.guaranteeText is not None:
        fields["guarantee_text"] = payload.guaranteeText
    if payload.disclaimers is not None:
        fields["disclaimers"] = payload.disclaimers

    repo = ProductsRepository(session)
    product = repo.create(org_id=auth.org_id, client_id=payload.clientId, **fields)
    return jsonable_encoder(product)


@router.get("/{product_id}")
def get_product(
    product_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    products_repo = ProductsRepository(session)
    offers_repo = ProductOffersRepository(session)
    price_points_repo = ProductOfferPricePointsRepository(session)

    product = products_repo.get(org_id=auth.org_id, product_id=product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    offers = offers_repo.list_by_product(product_id=str(product.id))
    offer_ids = [str(offer.id) for offer in offers]
    price_points_by_offer: dict[str, list[dict]] = {}
    for offer_id in offer_ids:
        price_points = price_points_repo.list_by_offer(offer_id=offer_id)
        price_points_by_offer[offer_id] = [jsonable_encoder(pp) for pp in price_points]

    primary_asset_url = None
    if product.primary_asset_id:
        assets_repo = AssetsRepository(session)
        asset = assets_repo.get(org_id=auth.org_id, asset_id=str(product.primary_asset_id))
        if (
            asset
            and asset.asset_kind == "image"
            and asset.storage_key
            and asset.product_id
            and str(asset.product_id) == str(product.id)
        ):
            storage = MediaStorage()
            primary_asset_url = storage.presign_get(bucket=storage.bucket, key=asset.storage_key)

    assets_repo = AssetsRepository(session)
    now = datetime.now(timezone.utc)
    product_assets = [
        asset
        for asset in assets_repo.list(org_id=auth.org_id, product_id=str(product.id))
        if _is_asset_active(asset, now=now)
    ]
    primary_asset_id = str(product.primary_asset_id) if product.primary_asset_id else None
    storage = MediaStorage() if product_assets else None
    serialized_assets = (
        [_serialize_product_asset(asset, primary_asset_id, storage) for asset in product_assets]
        if storage is not None
        else []
    )

    max_assets_per_brief = int(settings.CREATIVE_SERVICE_ASSETS_PER_BRIEF or 6)
    grouped_by_brief: dict[str, list[dict]] = {}
    for idx, asset in enumerate(product_assets):
        metadata = asset.ai_metadata if isinstance(asset.ai_metadata, dict) else {}
        brief_id = metadata.get("assetBriefId")
        if not isinstance(brief_id, str) or not brief_id.strip():
            continue
        group = grouped_by_brief.setdefault(brief_id, [])
        if len(group) >= max_assets_per_brief:
            continue
        group.append(serialized_assets[idx])

    return {
        **jsonable_encoder(product),
        "primary_asset_url": primary_asset_url,
        "assets": serialized_assets,
        "creative_brief_assets": [
            {"assetBriefId": brief_id, "assets": assets}
            for brief_id, assets in grouped_by_brief.items()
        ],
        "offers": [
            {
                **jsonable_encoder(offer),
                "pricePoints": price_points_by_offer.get(str(offer.id), []),
            }
            for offer in offers
        ],
    }


@router.get("/{product_id}/assets")
def list_product_assets(
    product_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    products_repo = ProductsRepository(session)
    product = products_repo.get(org_id=auth.org_id, product_id=product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    assets_repo = AssetsRepository(session)
    now = datetime.now(timezone.utc)
    assets = [asset for asset in assets_repo.list(org_id=auth.org_id, product_id=product_id) if _is_asset_active(asset, now=now)]
    primary_asset_id = str(product.primary_asset_id) if product.primary_asset_id else None
    if not assets:
        return []
    storage = MediaStorage()
    return [_serialize_product_asset(asset, primary_asset_id, storage) for asset in assets]


@router.post("/{product_id}/assets", status_code=status.HTTP_201_CREATED)
async def upload_product_assets(
    product_id: str,
    files: list[UploadFile] = File(...),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded.")

    products_repo = ProductsRepository(session)
    product = products_repo.get(org_id=auth.org_id, product_id=product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    uploads: list[tuple[UploadFile, bytes, str, str]] = []
    for file in files:
        content = await file.read()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {file.filename or 'upload'} is empty.",
            )
        if len(content) > _PRODUCT_ASSET_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File {file.filename or 'upload'} exceeds {_PRODUCT_ASSET_MAX_BYTES} bytes.",
            )
        content_type = _resolve_product_asset_content_type(file)
        asset_kind = _resolve_product_asset_kind(content_type, file.filename)
        uploads.append((file, content, content_type, asset_kind))

    created_assets = []
    for file, content, content_type, asset_kind in uploads:
        try:
            asset = create_product_upload_asset(
                session=session,
                org_id=auth.org_id,
                client_id=str(product.client_id),
                product_id=str(product.id),
                content_bytes=content,
                filename=file.filename,
                content_type=content_type,
                asset_kind=asset_kind,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        created_assets.append(asset)

    primary_asset_id = str(product.primary_asset_id) if product.primary_asset_id else None
    storage = MediaStorage()
    return {
        "assets": [_serialize_product_asset(asset, primary_asset_id, storage) for asset in created_assets]
    }


@router.patch("/{product_id}")
def update_product(
    product_id: str,
    payload: ProductUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = ProductsRepository(session)
    product = repo.get(org_id=auth.org_id, product_id=product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    fields: dict[str, object] = {}
    fields_set = payload.model_fields_set
    if payload.name is not None:
        fields["name"] = payload.name
    if payload.description is not None:
        fields["description"] = payload.description
    if payload.category is not None:
        fields["category"] = payload.category
    if payload.primaryBenefits is not None:
        fields["primary_benefits"] = payload.primaryBenefits
    if payload.featureBullets is not None:
        fields["feature_bullets"] = payload.featureBullets
    if payload.guaranteeText is not None:
        fields["guarantee_text"] = payload.guaranteeText
    if payload.disclaimers is not None:
        fields["disclaimers"] = payload.disclaimers

    if "primaryAssetId" in fields_set:
        if payload.primaryAssetId is None:
            fields["primary_asset_id"] = None
        else:
            assets_repo = AssetsRepository(session)
            asset = assets_repo.get(org_id=auth.org_id, asset_id=payload.primaryAssetId)
            if not asset:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
            if not asset.product_id or str(asset.product_id) != str(product.id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Primary asset must belong to the selected product.",
                )
            if asset.asset_kind != "image":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Primary asset must be an image.",
                )
            fields["primary_asset_id"] = payload.primaryAssetId

    updated = repo.update(org_id=auth.org_id, product_id=product_id, **fields)
    return jsonable_encoder(updated)


@router.post("/{product_id}/offers", status_code=status.HTTP_201_CREATED)
def create_offer(
    product_id: str,
    payload: ProductOfferCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if payload.productId != product_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="productId mismatch")

    products_repo = ProductsRepository(session)
    product = products_repo.get(org_id=auth.org_id, product_id=product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    fields: dict[str, object] = {
        "name": payload.name,
        "business_model": payload.businessModel,
    }
    if payload.description is not None:
        fields["description"] = payload.description
    if payload.differentiationBullets is not None:
        fields["differentiation_bullets"] = payload.differentiationBullets
    if payload.guaranteeText is not None:
        fields["guarantee_text"] = payload.guaranteeText
    if payload.optionsSchema is not None:
        fields["options_schema"] = payload.optionsSchema

    offers_repo = ProductOffersRepository(session)
    offer = offers_repo.create(
        org_id=auth.org_id,
        client_id=str(product.client_id),
        product_id=str(product.id),
        **fields,
    )
    return jsonable_encoder(offer)


@router.patch("/offers/{offer_id}")
def update_offer(
    offer_id: str,
    payload: ProductOfferUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    offers_repo = ProductOffersRepository(session)
    offer = offers_repo.get(offer_id=offer_id)
    if not offer or str(offer.org_id) != str(auth.org_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")

    fields: dict[str, object] = {}
    if payload.name is not None:
        fields["name"] = payload.name
    if payload.description is not None:
        fields["description"] = payload.description
    if payload.businessModel is not None:
        fields["business_model"] = payload.businessModel
    if payload.differentiationBullets is not None:
        fields["differentiation_bullets"] = payload.differentiationBullets
    if payload.guaranteeText is not None:
        fields["guarantee_text"] = payload.guaranteeText
    if payload.optionsSchema is not None:
        fields["options_schema"] = payload.optionsSchema

    updated = offers_repo.update(offer_id=offer_id, **fields)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return jsonable_encoder(updated)


@router.post("/offers/{offer_id}/price-points", status_code=status.HTTP_201_CREATED)
def create_price_point(
    offer_id: str,
    payload: ProductOfferPricePointCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if payload.offerId != offer_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="offerId mismatch")

    offers_repo = ProductOffersRepository(session)
    offer = offers_repo.get(offer_id=offer_id)
    if not offer or str(offer.org_id) != str(auth.org_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")

    if payload.provider and payload.provider not in _SUPPORTED_PRICE_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported price provider")
    if payload.externalPriceId and not payload.provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="externalPriceId requires provider",
        )

    fields: dict[str, object] = {
        "label": payload.label,
        "amount_cents": payload.amountCents,
        "currency": payload.currency,
    }
    if payload.provider is not None:
        fields["provider"] = payload.provider
    if payload.externalPriceId is not None:
        fields["external_price_id"] = payload.externalPriceId
    if payload.optionValues is not None:
        fields["option_values"] = payload.optionValues

    price_points_repo = ProductOfferPricePointsRepository(session)
    price_point = price_points_repo.create(offer_id=offer_id, **fields)
    return jsonable_encoder(price_point)


@router.patch("/price-points/{price_point_id}")
def update_price_point(
    price_point_id: str,
    payload: ProductOfferPricePointUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    price_points_repo = ProductOfferPricePointsRepository(session)
    price_point = price_points_repo.get(price_point_id=price_point_id)
    if not price_point:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price point not found")

    offers_repo = ProductOffersRepository(session)
    offer = offers_repo.get(offer_id=str(price_point.offer_id))
    if not offer or str(offer.org_id) != str(auth.org_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")

    if payload.provider and payload.provider not in _SUPPORTED_PRICE_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported price provider")
    if payload.externalPriceId and not payload.provider and not price_point.provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="externalPriceId requires provider",
        )

    fields: dict[str, object] = {}
    if payload.label is not None:
        fields["label"] = payload.label
    if payload.amountCents is not None:
        fields["amount_cents"] = payload.amountCents
    if payload.currency is not None:
        fields["currency"] = payload.currency
    if payload.provider is not None:
        fields["provider"] = payload.provider
    if payload.externalPriceId is not None:
        fields["external_price_id"] = payload.externalPriceId
    if payload.optionValues is not None:
        fields["option_values"] = payload.optionValues

    updated = price_points_repo.update(price_point_id=price_point_id, **fields)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price point not found")
    return jsonable_encoder(updated)
