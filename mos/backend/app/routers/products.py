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
from app.db.models import Asset, Product
from app.db.repositories.products import (
    ProductVariantsRepository,
    ProductsRepository,
)
from app.services.assets import create_product_upload_asset
from app.services.media_storage import MediaStorage
from app.schemas.products import (
    ProductCreateRequest,
    ProductUpdateRequest,
    ProductVariantCreateRequest,
    ProductVariantUpdateRequest,
)

router = APIRouter(prefix="/products", tags=["products"])

_SUPPORTED_PRICE_PROVIDERS = {"stripe", "shopify"}
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
        "title": payload.title,
    }
    if payload.description is not None:
        fields["description"] = payload.description
    if payload.handle is not None:
        fields["handle"] = payload.handle
    if payload.vendor is not None:
        fields["vendor"] = payload.vendor
    if payload.productType is not None:
        fields["product_type"] = payload.productType
    if payload.tags is not None:
        fields["tags"] = payload.tags
    if payload.templateSuffix is not None:
        fields["template_suffix"] = payload.templateSuffix
    if payload.publishedAt is not None:
        fields["published_at"] = payload.publishedAt
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
    variants_repo = ProductVariantsRepository(session)

    product = products_repo.get(org_id=auth.org_id, product_id=product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    variants = variants_repo.list_by_product(product_id=str(product.id))

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
        "variants": [jsonable_encoder(variant) for variant in variants],
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
    if payload.title is not None:
        fields["title"] = payload.title
    if payload.description is not None:
        fields["description"] = payload.description
    if payload.handle is not None:
        fields["handle"] = payload.handle
    if payload.vendor is not None:
        fields["vendor"] = payload.vendor
    if payload.productType is not None:
        fields["product_type"] = payload.productType
    if payload.tags is not None:
        fields["tags"] = payload.tags
    if payload.templateSuffix is not None:
        fields["template_suffix"] = payload.templateSuffix
    if payload.publishedAt is not None:
        fields["published_at"] = payload.publishedAt
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


@router.post("/{product_id}/variants", status_code=status.HTTP_201_CREATED)
def create_variant(
    product_id: str,
    payload: ProductVariantCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    products_repo = ProductsRepository(session)
    product = products_repo.get(org_id=auth.org_id, product_id=product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    if payload.provider and payload.provider not in _SUPPORTED_PRICE_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported price provider")
    if payload.externalPriceId and not payload.provider:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="externalPriceId requires provider")

    fields: dict[str, object] = {
        "title": payload.title,
        "price": payload.price,
        "currency": payload.currency,
    }
    if payload.compareAtPrice is not None:
        fields["compare_at_price"] = payload.compareAtPrice
    if payload.provider is not None:
        fields["provider"] = payload.provider
    if payload.externalPriceId is not None:
        fields["external_price_id"] = payload.externalPriceId
    if payload.optionValues is not None:
        fields["option_values"] = payload.optionValues
    if payload.sku is not None:
        fields["sku"] = payload.sku
    if payload.barcode is not None:
        fields["barcode"] = payload.barcode
    if payload.requiresShipping is not None:
        fields["requires_shipping"] = payload.requiresShipping
    if payload.taxable is not None:
        fields["taxable"] = payload.taxable
    if payload.weight is not None:
        fields["weight"] = payload.weight
    if payload.weightUnit is not None:
        fields["weight_unit"] = payload.weightUnit
    if payload.inventoryQuantity is not None:
        fields["inventory_quantity"] = payload.inventoryQuantity
    if payload.inventoryPolicy is not None:
        fields["inventory_policy"] = payload.inventoryPolicy
    if payload.inventoryManagement is not None:
        fields["inventory_management"] = payload.inventoryManagement
    if payload.incoming is not None:
        fields["incoming"] = payload.incoming
    if payload.nextIncomingDate is not None:
        fields["next_incoming_date"] = payload.nextIncomingDate
    if payload.unitPrice is not None:
        fields["unit_price"] = payload.unitPrice
    if payload.unitPriceMeasurement is not None:
        fields["unit_price_measurement"] = payload.unitPriceMeasurement
    if payload.quantityRule is not None:
        fields["quantity_rule"] = payload.quantityRule
    if payload.quantityPriceBreaks is not None:
        fields["quantity_price_breaks"] = payload.quantityPriceBreaks

    variants_repo = ProductVariantsRepository(session)
    variant = variants_repo.create(product_id=str(product.id), **fields)
    return jsonable_encoder(variant)


@router.patch("/variants/{variant_id}")
def update_variant(
    variant_id: str,
    payload: ProductVariantUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    variants_repo = ProductVariantsRepository(session)
    variant = variants_repo.get(variant_id=variant_id)
    if not variant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")

    if not variant.product_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Variant is not linked to a product.",
        )

    # Verify org ownership via the linked product.
    product = session.scalars(
        select(Product).where(Product.id == variant.product_id, Product.org_id == auth.org_id)
    ).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")

    fields_set = payload.model_fields_set
    if payload.provider and payload.provider not in _SUPPORTED_PRICE_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported price provider")
    if "externalPriceId" in fields_set and payload.externalPriceId and not payload.provider and not variant.provider:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="externalPriceId requires provider")

    fields: dict[str, object] = {}
    if payload.title is not None:
        fields["title"] = payload.title
    if payload.price is not None:
        fields["price"] = payload.price
    if payload.currency is not None:
        fields["currency"] = payload.currency
    if "compareAtPrice" in fields_set:
        fields["compare_at_price"] = payload.compareAtPrice
    if "provider" in fields_set:
        fields["provider"] = payload.provider
    if "externalPriceId" in fields_set:
        fields["external_price_id"] = payload.externalPriceId
    if "optionValues" in fields_set:
        fields["option_values"] = payload.optionValues
    if "sku" in fields_set:
        fields["sku"] = payload.sku
    if "barcode" in fields_set:
        fields["barcode"] = payload.barcode
    if "requiresShipping" in fields_set:
        fields["requires_shipping"] = payload.requiresShipping
    if "taxable" in fields_set:
        fields["taxable"] = payload.taxable
    if "weight" in fields_set:
        fields["weight"] = payload.weight
    if "weightUnit" in fields_set:
        fields["weight_unit"] = payload.weightUnit
    if "inventoryQuantity" in fields_set:
        fields["inventory_quantity"] = payload.inventoryQuantity
    if "inventoryPolicy" in fields_set:
        fields["inventory_policy"] = payload.inventoryPolicy
    if "inventoryManagement" in fields_set:
        fields["inventory_management"] = payload.inventoryManagement
    if "incoming" in fields_set:
        fields["incoming"] = payload.incoming
    if "nextIncomingDate" in fields_set:
        fields["next_incoming_date"] = payload.nextIncomingDate
    if "unitPrice" in fields_set:
        fields["unit_price"] = payload.unitPrice
    if "unitPriceMeasurement" in fields_set:
        fields["unit_price_measurement"] = payload.unitPriceMeasurement
    if "quantityRule" in fields_set:
        fields["quantity_rule"] = payload.quantityRule
    if "quantityPriceBreaks" in fields_set:
        fields["quantity_price_breaks"] = payload.quantityPriceBreaks

    updated = variants_repo.update(variant_id=variant_id, **fields)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
    return jsonable_encoder(updated)
