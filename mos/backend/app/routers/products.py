from __future__ import annotations

import mimetypes
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.config import settings
from app.db.deps import get_session
from app.db.repositories.assets import AssetsRepository
from app.db.models import Asset, ClientUserPreference, Product, ProductOffer, ProductOfferBonus, ProductVariant
from app.schemas.shopify_connection import (
    ShopifyCreateProductRequest,
    ShopifyProductCreateResponse,
    ShopifyProductVariantSyncResponse,
    ShopifySyncProductVariantsRequest,
)
from app.db.repositories.products import (
    ProductOfferBonusesRepository,
    ProductOffersRepository,
    ProductVariantsRepository,
    ProductsRepository,
)
from app.services.assets import create_product_upload_asset
from app.services.media_storage import MediaStorage
from app.services.shopify_catalog import verify_shopify_product_exists
from app.services.shopify_connection import (
    create_client_shopify_product,
    get_client_shopify_product,
    get_client_shopify_connection_status,
    update_client_shopify_variant,
)
from app.schemas.products import (
    ProductCreateRequest,
    ProductOfferBonusCreateRequest,
    ProductOfferCreateRequest,
    ProductOfferUpdateRequest,
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
_SHOPIFY_PRODUCT_GID_PREFIX = "gid://shopify/Product/"
_SHOPIFY_VARIANT_GID_PREFIX = "gid://shopify/ProductVariant/"
_SHOPIFY_UNSYNCED_VARIANT_FIELDS = {
    "currency",
    "requiresShipping",
    "taxable",
    "weight",
    "weightUnit",
    "inventoryQuantity",
    "incoming",
    "nextIncomingDate",
    "unitPrice",
    "unitPriceMeasurement",
    "quantityRule",
    "quantityPriceBreaks",
}


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


def _normalize_shopify_product_gid(gid: str) -> str:
    cleaned = gid.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="shopifyProductGid cannot be empty.",
        )
    if not cleaned.startswith(_SHOPIFY_PRODUCT_GID_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="shopifyProductGid must be a Shopify product GID.",
        )
    return cleaned


def _validate_shopify_variant_gid(external_price_id: str) -> str:
    cleaned = external_price_id.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="externalPriceId cannot be empty.",
        )
    if not cleaned.startswith(_SHOPIFY_VARIANT_GID_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Shopify externalPriceId must be a Shopify variant GID.",
        )
    return cleaned


def _validate_variant_provider_mapping(*, provider: str | None, external_price_id: str | None) -> None:
    if provider == "shopify":
        if external_price_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Shopify provider requires externalPriceId (gid://shopify/ProductVariant/...).',
            )
        _validate_shopify_variant_gid(external_price_id)
        return

    if external_price_id and external_price_id.strip().startswith(_SHOPIFY_VARIANT_GID_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Shopify variant GIDs require provider="shopify".',
        )


def _is_shopify_managed_variant(variant: ProductVariant) -> bool:
    return (
        variant.provider == "shopify"
        and isinstance(variant.external_price_id, str)
        and variant.external_price_id.strip().startswith(_SHOPIFY_VARIANT_GID_PREFIX)
    )


def _serialize_offer_bonus(
    *,
    bonus: ProductOfferBonus,
    product: Product,
) -> dict:
    return {
        "id": str(bonus.id),
        "position": bonus.position,
        "created_at": bonus.created_at,
        "bonus_product": {
            "id": str(product.id),
            "title": product.title,
            "description": product.description,
            "product_type": product.product_type,
            "shopify_product_gid": product.shopify_product_gid,
        },
    }


def _serialize_offer_with_bonuses(
    *,
    offer: ProductOffer,
    bonuses: list[dict],
) -> dict:
    payload = jsonable_encoder(offer)
    payload["bonuses"] = bonuses
    return payload


def _get_client_user_pref(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    user_external_id: str,
) -> ClientUserPreference | None:
    return session.scalar(
        select(ClientUserPreference).where(
            ClientUserPreference.org_id == org_id,
            ClientUserPreference.client_id == client_id,
            ClientUserPreference.user_external_id == user_external_id,
        )
    )


def _require_offer_for_org(*, session: Session, offer_id: str, org_id: str) -> ProductOffer:
    offer = session.scalars(
        select(ProductOffer).where(ProductOffer.id == offer_id, ProductOffer.org_id == org_id)
    ).first()
    if not offer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    if not offer.product_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Offer is not linked to a product.",
        )
    return offer


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
    if payload.shopifyProductGid is not None:
        fields["shopify_product_gid"] = _normalize_shopify_product_gid(payload.shopifyProductGid)
    if payload.primaryBenefits is not None:
        fields["primary_benefits"] = payload.primaryBenefits
    if payload.featureBullets is not None:
        fields["feature_bullets"] = payload.featureBullets
    if payload.guaranteeText is not None:
        fields["guarantee_text"] = payload.guaranteeText
    if payload.disclaimers is not None:
        fields["disclaimers"] = payload.disclaimers

    repo = ProductsRepository(session)
    try:
        product = repo.create(org_id=auth.org_id, client_id=payload.clientId, **fields)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
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
    offers = session.scalars(
        select(ProductOffer)
        .where(ProductOffer.product_id == product.id, ProductOffer.org_id == auth.org_id)
        .order_by(ProductOffer.created_at.asc())
    ).all()

    offer_ids = [str(offer.id) for offer in offers]
    offer_bonuses = (
        session.scalars(
            select(ProductOfferBonus)
            .where(ProductOfferBonus.offer_id.in_(offer_ids))
            .order_by(ProductOfferBonus.position.asc(), ProductOfferBonus.created_at.asc())
        ).all()
        if offer_ids
        else []
    )
    bonuses_by_offer_id: dict[str, list[ProductOfferBonus]] = {}
    for bonus in offer_bonuses:
        bonuses_by_offer_id.setdefault(str(bonus.offer_id), []).append(bonus)

    bonus_product_ids = sorted({str(link.bonus_product_id) for link in offer_bonuses})
    bonus_products = (
        session.scalars(
            select(Product).where(
                Product.id.in_(bonus_product_ids),
                Product.org_id == auth.org_id,
                Product.client_id == product.client_id,
            )
        ).all()
        if bonus_product_ids
        else []
    )
    bonus_product_map = {str(item.id): item for item in bonus_products}
    serialized_offers: list[dict] = []
    for offer in offers:
        serialized_bonuses: list[dict] = []
        for bonus in bonuses_by_offer_id.get(str(offer.id), []):
            bonus_product = bonus_product_map.get(str(bonus.bonus_product_id))
            if not bonus_product:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Offer bonus references an invalid product.",
                )
            serialized_bonuses.append(_serialize_offer_bonus(bonus=bonus, product=bonus_product))
        serialized_offers.append(_serialize_offer_with_bonuses(offer=offer, bonuses=serialized_bonuses))

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
        "offers": serialized_offers,
        "variants": [jsonable_encoder(variant) for variant in variants],
    }


@router.post("/{product_id}/shopify/create", response_model=ShopifyProductCreateResponse)
def create_shopify_product_for_product(
    product_id: str,
    payload: ShopifyCreateProductRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    product = session.scalars(
        select(Product).where(Product.id == product_id, Product.org_id == auth.org_id)
    ).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if product.shopify_product_gid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product is already mapped to Shopify. Clear mapping before creating a new Shopify product.",
        )

    status_payload = get_client_shopify_connection_status(
        client_id=str(product.client_id),
        selected_shop_domain=payload.shopDomain,
    )
    if status_payload["state"] != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Shopify connection is not ready: {status_payload['message']}",
        )

    created = create_client_shopify_product(
        client_id=str(product.client_id),
        title=payload.title,
        description=payload.description,
        handle=payload.handle,
        vendor=payload.vendor,
        product_type=payload.productType,
        tags=payload.tags,
        status_text=payload.status,
        variants=[variant.model_dump() for variant in payload.variants],
        shop_domain=payload.shopDomain,
    )

    existing_external_ids = {
        value.strip()
        for value in session.scalars(
            select(ProductVariant.external_price_id).where(
                ProductVariant.product_id == product.id,
                ProductVariant.external_price_id.is_not(None),
            )
        ).all()
        if isinstance(value, str) and value.strip()
    }
    duplicate_external_id = next(
        (variant["variantGid"] for variant in created["variants"] if variant["variantGid"] in existing_external_ids),
        None,
    )
    if duplicate_external_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Variant mapping already exists for Shopify variant {duplicate_external_id}.",
        )

    existing_shopify_variant_titles = {
        value.strip().lower()
        for value in session.scalars(
            select(ProductVariant.title).where(
                ProductVariant.product_id == product.id,
                ProductVariant.provider == "shopify",
            )
        ).all()
        if isinstance(value, str) and value.strip()
    }
    duplicate_variant_title = next(
        (
            variant["title"]
            for variant in created["variants"]
            if isinstance(variant.get("title"), str)
            and variant["title"].strip()
            and variant["title"].strip().lower() in existing_shopify_variant_titles
        ),
        None,
    )
    if duplicate_variant_title is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Shopify variant title "{duplicate_variant_title}" already exists for this product.',
        )

    product.shopify_product_gid = created["productGid"]
    session.add(product)
    imported_at = datetime.now(timezone.utc)
    for variant in created["variants"]:
        session.add(
            ProductVariant(
                product_id=product.id,
                title=variant["title"],
                price=variant["priceCents"],
                currency=variant["currency"].lower(),
                provider="shopify",
                external_price_id=variant["variantGid"],
                shopify_last_synced_at=imported_at,
                shopify_last_sync_error=None,
            )
        )
    session.commit()

    return ShopifyProductCreateResponse(**created)


@router.post("/{product_id}/shopify/sync-variants", response_model=ShopifyProductVariantSyncResponse)
def sync_shopify_variants_for_product(
    product_id: str,
    payload: ShopifySyncProductVariantsRequest | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    product = session.scalars(
        select(Product).where(Product.id == product_id, Product.org_id == auth.org_id)
    ).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if not product.shopify_product_gid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product is not mapped to Shopify. Save a Shopify product GID first.",
        )

    selected_shop_domain_pref = _get_client_user_pref(
        session=session,
        org_id=auth.org_id,
        client_id=str(product.client_id),
        user_external_id=auth.user_id,
    )
    selected_shop_domain = (
        selected_shop_domain_pref.selected_shop_domain.strip().lower()
        if selected_shop_domain_pref
        and isinstance(selected_shop_domain_pref.selected_shop_domain, str)
        and selected_shop_domain_pref.selected_shop_domain.strip()
        else None
    )
    requested_shop_domain = payload.shopDomain if payload is not None else None
    effective_shop_domain = requested_shop_domain or selected_shop_domain
    status_payload = get_client_shopify_connection_status(
        client_id=str(product.client_id),
        selected_shop_domain=effective_shop_domain,
    )
    if status_payload["state"] != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Shopify connection is not ready: {status_payload['message']}",
        )
    resolved_shop_domain = status_payload.get("shopDomain")
    if not isinstance(resolved_shop_domain, str) or not resolved_shop_domain.strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Shopify connection is ready but no shopDomain was resolved.",
        )

    shopify_product = get_client_shopify_product(
        client_id=str(product.client_id),
        product_gid=product.shopify_product_gid,
        shop_domain=resolved_shop_domain,
    )
    response_product_gid = shopify_product["productGid"]
    if response_product_gid != product.shopify_product_gid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Shopify product sync returned a different product GID than the mapped product. "
                "Confirm mapping before syncing."
            ),
        )

    existing_variants = session.scalars(
        select(ProductVariant).where(ProductVariant.product_id == product.id)
    ).all()
    existing_by_external_id: dict[str, ProductVariant] = {}
    for variant in existing_variants:
        if not isinstance(variant.external_price_id, str) or not variant.external_price_id.strip():
            continue
        normalized_external_id = variant.external_price_id.strip()
        if normalized_external_id in existing_by_external_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Cannot sync Shopify variants because duplicate externalPriceId mappings exist in MOS for this product: "
                    f"{normalized_external_id}."
                ),
            )
        existing_by_external_id[normalized_external_id] = variant

    synced_at = datetime.now(timezone.utc)
    created_count = 0
    updated_count = 0
    for shopify_variant in shopify_product["variants"]:
        variant_gid = shopify_variant["variantGid"]
        option_values = shopify_variant.get("optionValues") or {}
        normalized_option_values = (
            {key: value for key, value in option_values.items()} if option_values else None
        )
        if variant_gid in existing_by_external_id:
            variant = existing_by_external_id[variant_gid]
            variant.title = shopify_variant["title"]
            variant.price = shopify_variant["priceCents"]
            variant.currency = shopify_variant["currency"].lower()
            variant.provider = "shopify"
            variant.external_price_id = variant_gid
            variant.compare_at_price = shopify_variant.get("compareAtPriceCents")
            variant.sku = shopify_variant.get("sku")
            variant.barcode = shopify_variant.get("barcode")
            variant.taxable = shopify_variant["taxable"]
            variant.requires_shipping = shopify_variant["requiresShipping"]
            variant.inventory_policy = shopify_variant.get("inventoryPolicy")
            variant.inventory_management = shopify_variant.get("inventoryManagement")
            variant.inventory_quantity = shopify_variant.get("inventoryQuantity")
            variant.option_values = normalized_option_values
            variant.shopify_last_synced_at = synced_at
            variant.shopify_last_sync_error = None
            session.add(variant)
            updated_count += 1
            continue

        session.add(
            ProductVariant(
                product_id=product.id,
                title=shopify_variant["title"],
                price=shopify_variant["priceCents"],
                currency=shopify_variant["currency"].lower(),
                provider="shopify",
                external_price_id=variant_gid,
                compare_at_price=shopify_variant.get("compareAtPriceCents"),
                sku=shopify_variant.get("sku"),
                barcode=shopify_variant.get("barcode"),
                taxable=shopify_variant["taxable"],
                requires_shipping=shopify_variant["requiresShipping"],
                inventory_policy=shopify_variant.get("inventoryPolicy"),
                inventory_management=shopify_variant.get("inventoryManagement"),
                inventory_quantity=shopify_variant.get("inventoryQuantity"),
                option_values=normalized_option_values,
                shopify_last_synced_at=synced_at,
                shopify_last_sync_error=None,
            )
        )
        created_count += 1

    session.commit()
    return ShopifyProductVariantSyncResponse(
        shopDomain=shopify_product["shopDomain"],
        productGid=shopify_product["productGid"],
        createdCount=created_count,
        updatedCount=updated_count,
        totalFetched=len(shopify_product["variants"]),
        variants=shopify_product["variants"],
    )


@router.get("/{product_id}/offers")
def list_product_offers(
    product_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    product = session.scalars(
        select(Product).where(Product.id == product_id, Product.org_id == auth.org_id)
    ).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    offers = session.scalars(
        select(ProductOffer)
        .where(ProductOffer.product_id == product.id, ProductOffer.org_id == auth.org_id)
        .order_by(ProductOffer.created_at.asc())
    ).all()
    bonuses_repo = ProductOfferBonusesRepository(session)

    serialized: list[dict] = []
    for offer in offers:
        bonus_links = bonuses_repo.list_by_offer(offer_id=str(offer.id))
        bonus_products_by_id = {
            str(item.id): item
            for item in session.scalars(
                select(Product).where(
                    Product.id.in_([link.bonus_product_id for link in bonus_links]),
                    Product.org_id == auth.org_id,
                    Product.client_id == product.client_id,
                )
            ).all()
        } if bonus_links else {}
        bonuses_payload: list[dict] = []
        for bonus in bonus_links:
            linked_product = bonus_products_by_id.get(str(bonus.bonus_product_id))
            if not linked_product:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Offer bonus references an invalid product.",
                )
            bonuses_payload.append(_serialize_offer_bonus(bonus=bonus, product=linked_product))
        serialized.append(_serialize_offer_with_bonuses(offer=offer, bonuses=bonuses_payload))
    return serialized


@router.post("/{product_id}/offers", status_code=status.HTTP_201_CREATED)
def create_product_offer(
    product_id: str,
    payload: ProductOfferCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if str(payload.productId) != str(product_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Offer productId must match URL product_id.",
        )
    product = session.scalars(
        select(Product).where(Product.id == product_id, Product.org_id == auth.org_id)
    ).first()
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
    created = offers_repo.create(
        org_id=auth.org_id,
        client_id=str(product.client_id),
        product_id=str(product.id),
        **fields,
    )
    payload_out = jsonable_encoder(created)
    payload_out["bonuses"] = []
    return payload_out


@router.patch("/offers/{offer_id}")
def update_product_offer(
    offer_id: str,
    payload: ProductOfferUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    offer = _require_offer_for_org(session=session, offer_id=offer_id, org_id=auth.org_id)

    fields_set = payload.model_fields_set
    fields: dict[str, object] = {}
    if "name" in fields_set:
        if payload.name is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name cannot be null.")
        fields["name"] = payload.name
    if "description" in fields_set:
        fields["description"] = payload.description
    if "businessModel" in fields_set:
        if payload.businessModel is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="businessModel cannot be null.")
        fields["business_model"] = payload.businessModel
    if "differentiationBullets" in fields_set:
        fields["differentiation_bullets"] = payload.differentiationBullets
    if "guaranteeText" in fields_set:
        fields["guarantee_text"] = payload.guaranteeText
    if "optionsSchema" in fields_set:
        fields["options_schema"] = payload.optionsSchema

    offers_repo = ProductOffersRepository(session)
    updated = offers_repo.update(offer_id=str(offer.id), **fields)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return jsonable_encoder(updated)


@router.get("/offers/{offer_id}/bonuses")
def list_offer_bonuses(
    offer_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    offer = _require_offer_for_org(session=session, offer_id=offer_id, org_id=auth.org_id)
    bonuses_repo = ProductOfferBonusesRepository(session)
    bonus_links = bonuses_repo.list_by_offer(offer_id=str(offer.id))

    if not bonus_links:
        return []

    bonus_products = session.scalars(
        select(Product).where(
            Product.id.in_([link.bonus_product_id for link in bonus_links]),
            Product.org_id == auth.org_id,
            Product.client_id == offer.client_id,
        )
    ).all()
    product_map = {str(item.id): item for item in bonus_products}

    serialized: list[dict] = []
    for link in bonus_links:
        linked_product = product_map.get(str(link.bonus_product_id))
        if not linked_product:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Offer bonus references an invalid product.",
            )
        serialized.append(_serialize_offer_bonus(bonus=link, product=linked_product))
    return serialized


@router.post("/offers/{offer_id}/bonuses", status_code=status.HTTP_201_CREATED)
def add_offer_bonus(
    offer_id: str,
    payload: ProductOfferBonusCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    offer = _require_offer_for_org(session=session, offer_id=offer_id, org_id=auth.org_id)

    bonus_product = session.scalars(
        select(Product).where(
            Product.id == payload.bonusProductId,
            Product.org_id == auth.org_id,
            Product.client_id == offer.client_id,
        )
    ).first()
    if not bonus_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bonus product not found")
    if str(bonus_product.id) == str(offer.product_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bonus product must differ from the offer primary product.",
        )
    if not bonus_product.shopify_product_gid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bonus product must include a Shopify product GID.",
        )

    bonuses_repo = ProductOfferBonusesRepository(session)
    existing = session.scalars(
        select(ProductOfferBonus).where(
            ProductOfferBonus.offer_id == offer.id,
            ProductOfferBonus.bonus_product_id == bonus_product.id,
        )
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bonus product is already linked to this offer.",
        )

    verify_shopify_product_exists(
        client_id=str(offer.client_id),
        product_gid=bonus_product.shopify_product_gid,
    )

    max_position = session.scalar(
        select(func.max(ProductOfferBonus.position)).where(ProductOfferBonus.offer_id == offer.id)
    )
    next_position = int(max_position) + 1 if max_position is not None else 0
    created = bonuses_repo.create(
        org_id=auth.org_id,
        client_id=str(offer.client_id),
        offer_id=str(offer.id),
        bonus_product_id=str(bonus_product.id),
        position=next_position,
    )
    return _serialize_offer_bonus(bonus=created, product=bonus_product)


@router.delete("/offers/{offer_id}/bonuses/{bonus_product_id}")
def remove_offer_bonus(
    offer_id: str,
    bonus_product_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    offer = _require_offer_for_org(session=session, offer_id=offer_id, org_id=auth.org_id)
    bonus_product = session.scalars(
        select(Product).where(
            Product.id == bonus_product_id,
            Product.org_id == auth.org_id,
            Product.client_id == offer.client_id,
        )
    ).first()
    if not bonus_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bonus product not found")

    bonuses_repo = ProductOfferBonusesRepository(session)
    deleted = bonuses_repo.delete_by_offer_and_bonus_product(
        offer_id=str(offer.id),
        bonus_product_id=str(bonus_product.id),
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer bonus not found")
    return {"ok": True}


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
    if "shopifyProductGid" in fields_set:
        if payload.shopifyProductGid is None:
            fields["shopify_product_gid"] = None
        else:
            normalized_gid = _normalize_shopify_product_gid(payload.shopifyProductGid)
            verify_shopify_product_exists(
                client_id=str(product.client_id),
                product_gid=normalized_gid,
            )
            fields["shopify_product_gid"] = normalized_gid
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

    offer_id = payload.offerId
    if offer_id is not None:
        if not str(offer_id).strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="offerId cannot be empty.")
        offer = session.scalars(
            select(ProductOffer).where(
                ProductOffer.id == offer_id,
                ProductOffer.org_id == auth.org_id,
                ProductOffer.client_id == product.client_id,
                ProductOffer.product_id == product.id,
            )
        ).first()
        if not offer:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="offerId must belong to the selected product.",
            )

    if payload.provider and payload.provider not in _SUPPORTED_PRICE_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported price provider")
    if payload.externalPriceId and not payload.provider:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="externalPriceId requires provider")
    _validate_variant_provider_mapping(
        provider=payload.provider,
        external_price_id=payload.externalPriceId,
    )

    fields: dict[str, object] = {
        "title": payload.title,
        "price": payload.price,
        "currency": payload.currency,
    }
    if offer_id is not None:
        fields["offer_id"] = offer_id
    if payload.compareAtPrice is not None:
        fields["compare_at_price"] = payload.compareAtPrice
    if payload.provider is not None:
        fields["provider"] = payload.provider
    if payload.externalPriceId is not None:
        fields["external_price_id"] = payload.externalPriceId.strip()
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
    effective_provider = payload.provider if "provider" in fields_set else variant.provider
    effective_external_price_id = payload.externalPriceId if "externalPriceId" in fields_set else variant.external_price_id
    _validate_variant_provider_mapping(
        provider=effective_provider,
        external_price_id=effective_external_price_id,
    )

    is_shopify_managed = (
        effective_provider == "shopify"
        and isinstance(effective_external_price_id, str)
        and effective_external_price_id.strip().startswith(_SHOPIFY_VARIANT_GID_PREFIX)
    )

    if is_shopify_managed and "currency" in fields_set and payload.currency is not None:
        incoming_currency = payload.currency.strip().lower()
        current_currency = (variant.currency or "").strip().lower()
        if incoming_currency != current_currency:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Shopify-managed variant currency cannot be changed from MOS. "
                    "Update currency directly in Shopify product settings."
                ),
            )

    shopify_sync_succeeded = False
    if is_shopify_managed:
        unsupported_shopify_fields = sorted(name for name in fields_set if name in _SHOPIFY_UNSYNCED_VARIANT_FIELDS)
        if unsupported_shopify_fields:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Shopify propagation does not support updating these fields from MOS: "
                    f"{', '.join(unsupported_shopify_fields)}."
                ),
            )

        shopify_fields: dict[str, object] = {}
        if "title" in fields_set:
            if payload.title is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="title cannot be null.")
            shopify_fields["title"] = payload.title
        if "price" in fields_set:
            if payload.price is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="price cannot be null.")
            shopify_fields["priceCents"] = payload.price
        if "compareAtPrice" in fields_set:
            shopify_fields["compareAtPriceCents"] = payload.compareAtPrice
        if "sku" in fields_set:
            shopify_fields["sku"] = payload.sku
        if "barcode" in fields_set:
            shopify_fields["barcode"] = payload.barcode
        if "inventoryPolicy" in fields_set:
            if payload.inventoryPolicy is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="inventoryPolicy cannot be null.")
            shopify_fields["inventoryPolicy"] = payload.inventoryPolicy
        if "inventoryManagement" in fields_set:
            shopify_fields["inventoryManagement"] = payload.inventoryManagement

        if shopify_fields:
            try:
                selected_shop_domain = _get_client_user_pref(
                    session=session,
                    org_id=auth.org_id,
                    client_id=str(product.client_id),
                    user_external_id=auth.user_id,
                )
                selected_shop = (
                    selected_shop_domain.selected_shop_domain.strip().lower()
                    if selected_shop_domain
                    and isinstance(selected_shop_domain.selected_shop_domain, str)
                    and selected_shop_domain.selected_shop_domain.strip()
                    else None
                )
                status_payload = get_client_shopify_connection_status(
                    client_id=str(product.client_id),
                    selected_shop_domain=selected_shop,
                )
                if status_payload["state"] != "ready":
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Shopify connection is not ready: {status_payload['message']}",
                    )
                resolved_shop_domain = status_payload.get("shopDomain")
                if not isinstance(resolved_shop_domain, str) or not resolved_shop_domain.strip():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Shopify connection is ready but no shopDomain was resolved.",
                    )
                update_client_shopify_variant(
                    client_id=str(product.client_id),
                    variant_gid=effective_external_price_id.strip(),
                    fields=shopify_fields,
                    shop_domain=resolved_shop_domain,
                )
                shopify_sync_succeeded = True
            except HTTPException as exc:
                sync_error_detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
                variant.shopify_last_sync_error = sync_error_detail
                session.add(variant)
                session.commit()
                raise

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
        fields["external_price_id"] = payload.externalPriceId.strip() if payload.externalPriceId is not None else None
    if "optionValues" in fields_set:
        fields["option_values"] = payload.optionValues
    if "offerId" in fields_set:
        if payload.offerId is None:
            fields["offer_id"] = None
        else:
            if not str(payload.offerId).strip():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="offerId cannot be empty.")
            offer = session.scalars(
                select(ProductOffer).where(
                    ProductOffer.id == payload.offerId,
                    ProductOffer.org_id == auth.org_id,
                    ProductOffer.client_id == product.client_id,
                    ProductOffer.product_id == product.id,
                )
            ).first()
            if not offer:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="offerId must belong to the selected product.",
                )
            fields["offer_id"] = payload.offerId
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
    if shopify_sync_succeeded:
        fields["shopify_last_synced_at"] = datetime.now(timezone.utc)
        fields["shopify_last_sync_error"] = None

    updated = variants_repo.update(variant_id=variant_id, **fields)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
    return jsonable_encoder(updated)


@router.delete("/variants/{variant_id}")
def delete_variant(
    variant_id: str,
    force: bool = False,
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

    product = session.scalars(
        select(Product).where(Product.id == variant.product_id, Product.org_id == auth.org_id)
    ).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")

    if _is_shopify_managed_variant(variant) and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Shopify-mapped variants require explicit force delete. "
                "Retry with ?force=true to delete only the MOS record."
            ),
        )

    deleted = variants_repo.delete(variant_id=variant_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
    return {"ok": True}
