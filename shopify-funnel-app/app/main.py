from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import ORJSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session, init_db
from app.models import OAuthState, ProcessedWebhookEvent, ShopInstallation
from app.schemas import (
    CatalogProductVariant,
    CatalogProductSummary,
    CreateCatalogProductRequest,
    CreateCatalogProductResponse,
    CreatedCatalogVariant,
    CreateCheckoutRequest,
    CreateCheckoutResponse,
    ForwardOrderPayload,
    GetProductRequest,
    GetProductResponse,
    InstallationResponse,
    ListProductsRequest,
    ListProductsResponse,
    SyncThemeBrandRequest,
    SyncThemeBrandResponse,
    UpsertedPolicyPage,
    UpsertPolicyPagesRequest,
    UpsertPolicyPagesResponse,
    UpdateCatalogVariantRequest,
    UpdateCatalogVariantResponse,
    VerifyProductRequest,
    VerifyProductResponse,
    UpdateInstallationRequest,
)
from app.security import (
    normalize_shop_domain,
    require_internal_api_token,
    verify_oauth_hmac,
    verify_webhook_hmac,
)
from app.shopify_api import ShopifyApiClient, ShopifyApiError

app = FastAPI(title="Marketi Shopify Funnel App", default_response_class=ORJSONResponse)
shopify_api = ShopifyApiClient()


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


def _serialize_installation(installation: ShopInstallation) -> InstallationResponse:
    scopes = [scope.strip() for scope in installation.scopes.split(",") if scope.strip()]
    return InstallationResponse(
        shopDomain=installation.shop_domain,
        clientId=installation.client_id,
        hasStorefrontAccessToken=bool(installation.storefront_access_token),
        scopes=scopes,
        installedAt=installation.installed_at,
        updatedAt=installation.updated_at,
        uninstalledAt=installation.uninstalled_at,
    )


def _build_shopify_oauth_url(*, shop_domain: str, state: str) -> str:
    query = urlencode(
        {
            "client_id": settings.SHOPIFY_APP_API_KEY,
            "scope": settings.admin_scopes_csv,
            "redirect_uri": f"{settings.app_base_url}/auth/callback",
            "state": state,
        }
    )
    return f"https://{shop_domain}/admin/oauth/authorize?{query}"


async def _register_required_webhooks(*, shop_domain: str, admin_access_token: str) -> None:
    webhooks: list[tuple[str, str]] = [
        ("APP_UNINSTALLED", f"{settings.app_base_url}/webhooks/app/uninstalled"),
    ]
    if settings.SHOPIFY_ENABLE_ORDER_FORWARDING:
        webhooks.append(("ORDERS_CREATE", f"{settings.app_base_url}/webhooks/orders/create"))

    for topic, callback_url in webhooks:
        await shopify_api.register_webhook(
            shop_domain=shop_domain,
            access_token=admin_access_token,
            topic=topic,
            callback_url=callback_url,
        )


@app.get("/auth/install")
def auth_install(
    shop: str,
    client_id: str | None = None,
    session: Session = Depends(get_session),
):
    shop_domain = normalize_shop_domain(shop)
    state = uuid4().hex
    oauth_state = OAuthState(state=state, shop_domain=shop_domain, client_id=client_id)
    session.add(oauth_state)
    session.commit()

    return RedirectResponse(url=_build_shopify_oauth_url(shop_domain=shop_domain, state=state), status_code=302)


@app.get("/auth/callback")
async def auth_callback(request: Request, session: Session = Depends(get_session)):
    query_items = list(request.query_params.multi_items())
    if not verify_oauth_hmac(query_items):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth HMAC")

    shop = request.query_params.get("shop")
    code = request.query_params.get("code")
    state_value = request.query_params.get("state")
    if not shop or not code or not state_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required OAuth callback params: shop, code, state",
        )

    shop_domain = normalize_shop_domain(shop)
    oauth_state = session.get(OAuthState, state_value)
    if not oauth_state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")
    if oauth_state.shop_domain != shop_domain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state does not match the shop domain",
        )

    try:
        admin_access_token, scopes_csv = await shopify_api.exchange_code_for_access_token(
            shop_domain=shop_domain,
            code=code,
        )

        installation = session.scalars(
            select(ShopInstallation).where(ShopInstallation.shop_domain == shop_domain)
        ).first()
        if installation is None:
            installation = ShopInstallation(
                shop_domain=shop_domain,
                client_id=oauth_state.client_id,
                admin_access_token=admin_access_token,
                scopes=scopes_csv,
                uninstalled_at=None,
            )
            session.add(installation)
        else:
            installation.admin_access_token = admin_access_token
            installation.scopes = scopes_csv
            installation.uninstalled_at = None
            if oauth_state.client_id:
                installation.client_id = oauth_state.client_id
            installation.updated_at = datetime.now(timezone.utc)

        await _register_required_webhooks(
            shop_domain=shop_domain,
            admin_access_token=admin_access_token,
        )
        session.delete(oauth_state)
        session.commit()

    except ShopifyApiError as exc:
        session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    if settings.SHOPIFY_INSTALL_SUCCESS_REDIRECT_URL:
        success_url = (
            f"{str(settings.SHOPIFY_INSTALL_SUCCESS_REDIRECT_URL).rstrip('/')}"
            f"?shop={shop_domain}"
        )
        return RedirectResponse(url=success_url, status_code=302)

    return {
        "ok": True,
        "shopDomain": shop_domain,
        "clientId": installation.client_id,
        "scopes": [scope.strip() for scope in scopes_csv.split(",") if scope.strip()],
        "next": (
            "Set storefrontAccessToken via PATCH /admin/installations/{shop_domain} before creating checkouts."
        ),
    }


@app.get("/admin/installations", dependencies=[Depends(require_internal_api_token)])
def list_installations(session: Session = Depends(get_session)):
    installations = session.scalars(select(ShopInstallation).order_by(ShopInstallation.updated_at.desc())).all()
    return [_serialize_installation(installation) for installation in installations]


@app.patch(
    "/admin/installations/{shop_domain}",
    dependencies=[Depends(require_internal_api_token)],
)
def update_installation(
    shop_domain: str,
    payload: UpdateInstallationRequest,
    session: Session = Depends(get_session),
):
    normalized_shop = normalize_shop_domain(shop_domain)
    installation = session.scalars(
        select(ShopInstallation).where(ShopInstallation.shop_domain == normalized_shop)
    ).first()
    if not installation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop installation not found")

    fields_set = payload.model_fields_set
    if "clientId" in fields_set:
        installation.client_id = payload.clientId

    if "storefrontAccessToken" in fields_set:
        token = payload.storefrontAccessToken
        if token is not None:
            token = token.strip()
        installation.storefront_access_token = token or None

    installation.updated_at = datetime.now(timezone.utc)
    session.add(installation)
    session.commit()
    session.refresh(installation)
    return _serialize_installation(installation)


def _resolve_active_installation(
    *,
    client_id: str | None,
    shop_domain: str | None,
    session: Session,
) -> ShopInstallation:
    if client_id:
        matches = session.scalars(
            select(ShopInstallation).where(
                ShopInstallation.client_id == client_id,
                ShopInstallation.uninstalled_at.is_(None),
            )
        ).all()
        if not matches:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active Shopify installation found for clientId={client_id}",
            )
        if len(matches) > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Multiple active Shopify installations found for this clientId. "
                    "Provide shopDomain explicitly."
                ),
            )
        return matches[0]

    normalized_shop = normalize_shop_domain(shop_domain or "")
    installation = session.scalars(
        select(ShopInstallation).where(
            ShopInstallation.shop_domain == normalized_shop,
            ShopInstallation.uninstalled_at.is_(None),
        )
    ).first()
    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active Shopify installation found for shopDomain={normalized_shop}",
        )
    return installation


def _resolve_checkout_installation(
    *,
    request: CreateCheckoutRequest,
    session: Session,
) -> ShopInstallation:
    installation = _resolve_active_installation(
        client_id=request.clientId,
        shop_domain=request.shopDomain,
        session=session,
    )

    if not installation.storefront_access_token:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Installation is missing storefront_access_token. "
                "Set it via PATCH /admin/installations/{shop_domain}."
            ),
        )
    return installation


@app.post(
    "/v1/catalog/products/verify",
    response_model=VerifyProductResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def verify_catalog_product(
    payload: VerifyProductRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_active_installation(
        client_id=payload.clientId,
        shop_domain=payload.shopDomain,
        session=session,
    )

    try:
        product = await shopify_api.verify_product_exists(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
            product_gid=payload.productGid,
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return VerifyProductResponse(
        shopDomain=installation.shop_domain,
        productGid=product["id"],
        handle=product["handle"],
        title=product["title"],
    )


@app.post(
    "/v1/catalog/products/list",
    response_model=ListProductsResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def list_catalog_products(
    payload: ListProductsRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_active_installation(
        client_id=payload.clientId,
        shop_domain=payload.shopDomain,
        session=session,
    )
    query = (payload.query or "").strip() or None
    try:
        products = await shopify_api.list_products(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
            query=query,
            limit=payload.limit,
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return ListProductsResponse(
        shopDomain=installation.shop_domain,
        products=[
            CatalogProductSummary(
                productGid=item["id"],
                title=item["title"],
                handle=item["handle"],
                status=item["status"],
            )
            for item in products
        ],
    )


@app.post(
    "/v1/catalog/products/get",
    response_model=GetProductResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def get_catalog_product(
    payload: GetProductRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_active_installation(
        client_id=payload.clientId,
        shop_domain=payload.shopDomain,
        session=session,
    )
    try:
        product = await shopify_api.get_product(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
            product_gid=payload.productGid,
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return GetProductResponse(
        shopDomain=installation.shop_domain,
        productGid=product["productGid"],
        title=product["title"],
        handle=product["handle"],
        status=product["status"],
        variants=[
            CatalogProductVariant(
                variantGid=item["variantGid"],
                title=item["title"],
                priceCents=item["priceCents"],
                currency=item["currency"],
                compareAtPriceCents=item.get("compareAtPriceCents"),
                sku=item.get("sku"),
                barcode=item.get("barcode"),
                taxable=item["taxable"],
                requiresShipping=item["requiresShipping"],
                inventoryPolicy=item.get("inventoryPolicy"),
                inventoryManagement=item.get("inventoryManagement"),
                inventoryQuantity=item.get("inventoryQuantity"),
                optionValues=item.get("optionValues") or {},
            )
            for item in product["variants"]
        ],
    )


@app.post(
    "/v1/catalog/products/create",
    response_model=CreateCatalogProductResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def create_catalog_product(
    payload: CreateCatalogProductRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_active_installation(
        client_id=payload.clientId,
        shop_domain=payload.shopDomain,
        session=session,
    )
    try:
        created = await shopify_api.create_product(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
            title=payload.title,
            description=payload.description,
            handle=payload.handle,
            vendor=payload.vendor,
            product_type=payload.productType,
            tags=payload.tags,
            status=payload.status,
            variants=[variant.model_dump() for variant in payload.variants],
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return CreateCatalogProductResponse(
        shopDomain=installation.shop_domain,
        productGid=created["productGid"],
        title=created["title"],
        handle=created["handle"],
        status=created["status"],
        variants=[
            CreatedCatalogVariant(
                variantGid=item["variantGid"],
                title=item["title"],
                priceCents=item["priceCents"],
                currency=item["currency"],
            )
            for item in created["variants"]
        ],
    )


@app.patch(
    "/v1/catalog/variants",
    response_model=UpdateCatalogVariantResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def update_catalog_variant(
    payload: UpdateCatalogVariantRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_active_installation(
        client_id=payload.clientId,
        shop_domain=payload.shopDomain,
        session=session,
    )

    fields_set = payload.model_fields_set
    update_fields: dict[str, Any] = {}
    if "title" in fields_set:
        update_fields["title"] = payload.title
    if "priceCents" in fields_set:
        update_fields["priceCents"] = payload.priceCents
    if "compareAtPriceCents" in fields_set:
        update_fields["compareAtPriceCents"] = payload.compareAtPriceCents
    if "sku" in fields_set:
        update_fields["sku"] = payload.sku
    if "barcode" in fields_set:
        update_fields["barcode"] = payload.barcode
    if "inventoryPolicy" in fields_set:
        update_fields["inventoryPolicy"] = payload.inventoryPolicy
    if "inventoryManagement" in fields_set:
        update_fields["inventoryManagement"] = payload.inventoryManagement

    try:
        updated = await shopify_api.update_variant(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
            variant_gid=payload.variantGid,
            fields=update_fields,
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return UpdateCatalogVariantResponse(
        shopDomain=installation.shop_domain,
        productGid=updated["productGid"],
        variantGid=updated["variantGid"],
    )


@app.post(
    "/v1/policies/pages/upsert",
    response_model=UpsertPolicyPagesResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def upsert_policy_pages(
    payload: UpsertPolicyPagesRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_active_installation(
        client_id=payload.clientId,
        shop_domain=payload.shopDomain,
        session=session,
    )
    try:
        synced_pages = await shopify_api.upsert_policy_pages(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
            pages=[page.model_dump() for page in payload.pages],
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return UpsertPolicyPagesResponse(
        shopDomain=installation.shop_domain,
        pages=[
            UpsertedPolicyPage(
                pageKey=item["pageKey"],
                pageId=item["pageId"],
                title=item["title"],
                handle=item["handle"],
                url=item["url"],
                operation=item["operation"],
            )
            for item in synced_pages
        ],
    )


@app.post(
    "/v1/themes/brand/sync",
    response_model=SyncThemeBrandResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def sync_theme_brand(
    payload: SyncThemeBrandRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_active_installation(
        client_id=payload.clientId,
        shop_domain=payload.shopDomain,
        session=session,
    )
    try:
        synced = await shopify_api.sync_theme_brand(
            shop_domain=installation.shop_domain,
            access_token=installation.admin_access_token,
            workspace_name=payload.workspaceName,
            brand_name=payload.brandName,
            logo_url=payload.logoUrl,
            css_vars=payload.cssVars,
            font_urls=payload.fontUrls,
            data_theme=payload.dataTheme,
            theme_id=payload.themeId,
            theme_name=payload.themeName,
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return SyncThemeBrandResponse(
        shopDomain=installation.shop_domain,
        themeId=synced["themeId"],
        themeName=synced["themeName"],
        themeRole=synced["themeRole"],
        layoutFilename=synced["layoutFilename"],
        cssFilename=synced["cssFilename"],
        jobId=synced.get("jobId"),
    )


def _coerce_attribute_map(attributes: dict[str, str]) -> list[dict[str, str]]:
    serialized: list[dict[str, str]] = []
    for key, value in sorted(attributes.items()):
        cleaned_key = key.strip()
        cleaned_value = value.strip()
        if not cleaned_key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart attribute key cannot be empty")
        serialized.append({"key": cleaned_key, "value": cleaned_value})
    return serialized


@app.post(
    "/v1/checkouts",
    response_model=CreateCheckoutResponse,
    dependencies=[Depends(require_internal_api_token)],
)
async def create_checkout(
    payload: CreateCheckoutRequest,
    session: Session = Depends(get_session),
):
    installation = _resolve_checkout_installation(request=payload, session=session)

    cart_input: dict[str, Any] = {
        "lines": [
            {
                "merchandiseId": line.merchandiseId,
                "quantity": line.quantity,
            }
            for line in payload.lines
        ]
    }
    if payload.discountCodes:
        cart_input["discountCodes"] = payload.discountCodes
    if payload.attributes:
        cart_input["attributes"] = _coerce_attribute_map(payload.attributes)
    if payload.note:
        cart_input["note"] = payload.note
    if payload.buyerIdentity:
        buyer_identity = payload.buyerIdentity.model_dump(exclude_none=True)
        if buyer_identity:
            cart_input["buyerIdentity"] = buyer_identity

    try:
        cart_id, checkout_url = await shopify_api.create_cart(
            shop_domain=installation.shop_domain,
            storefront_access_token=installation.storefront_access_token,
            cart_input=cart_input,
        )
    except ShopifyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return CreateCheckoutResponse(
        shopDomain=installation.shop_domain,
        cartId=cart_id,
        checkoutUrl=checkout_url,
    )


def _coerce_note_attributes(order_payload: dict[str, Any]) -> dict[str, str]:
    raw = order_payload.get("note_attributes")
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="order.note_attributes must be a list",
        )

    attributes: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each note_attribute entry must be an object",
            )
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="note_attribute.name must be a string",
            )
        if value is None:
            value = ""
        if not isinstance(value, str):
            value = str(value)
        attributes[name] = value
    return attributes


def _coerce_line_items(order_payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = order_payload.get("line_items")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="order.line_items must be a list",
        )

    line_items: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each line_items entry must be an object",
            )
        line_items.append(
            {
                "id": item.get("id"),
                "variantId": item.get("variant_id"),
                "quantity": item.get("quantity"),
                "sku": item.get("sku"),
                "title": item.get("title"),
            }
        )
    return line_items


async def _forward_order_to_mos(payload: ForwardOrderPayload) -> None:
    if not settings.SHOPIFY_ENABLE_ORDER_FORWARDING:
        return

    forward_url = f"{str(settings.MOS_BACKEND_BASE_URL).rstrip('/')}/shopify/orders/webhook"
    headers = {
        "Content-Type": "application/json",
        "x-marketi-webhook-secret": settings.MOS_WEBHOOK_SHARED_SECRET or "",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.SHOPIFY_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(forward_url, json=payload.model_dump(), headers=headers)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Failed to forward Shopify order to MOS backend "
                f"({response.status_code}): {response.text}"
            ),
        )


@app.post("/webhooks/orders/create")
async def orders_create_webhook(request: Request, session: Session = Depends(get_session)):
    body = await request.body()
    if not verify_webhook_hmac(body=body, supplied_hmac=request.headers.get("x-shopify-hmac-sha256")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook HMAC")

    shop_header = request.headers.get("x-shopify-shop-domain")
    event_id = request.headers.get("x-shopify-event-id")
    if not shop_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing x-shopify-shop-domain header",
        )
    if not event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing x-shopify-event-id header",
        )

    shop_domain = normalize_shop_domain(shop_header)

    existing = session.scalars(
        select(ProcessedWebhookEvent).where(
            ProcessedWebhookEvent.shop_domain == shop_domain,
            ProcessedWebhookEvent.topic == "ORDERS_CREATE",
            ProcessedWebhookEvent.event_id == event_id,
        )
    ).first()
    if existing:
        return {"received": True, "duplicate": True}

    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook payload must be a JSON object",
        )

    note_attributes = _coerce_note_attributes(payload)
    if not note_attributes.get("funnel_id"):
        session.add(
            ProcessedWebhookEvent(
                shop_domain=shop_domain,
                topic="ORDERS_CREATE",
                event_id=event_id,
                status="ignored_missing_funnel_id",
            )
        )
        session.commit()
        return {
            "received": True,
            "ignored": True,
            "reason": "Order is missing funnel_id note attribute",
        }

    order_payload = ForwardOrderPayload(
        shopDomain=shop_domain,
        orderId=str(payload.get("id") or ""),
        orderName=payload.get("name"),
        currency=payload.get("currency"),
        totalPrice=payload.get("total_price"),
        createdAt=payload.get("created_at"),
        noteAttributes=note_attributes,
        lineItems=_coerce_line_items(payload),
    )
    if not order_payload.orderId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order payload is missing id",
        )

    await _forward_order_to_mos(order_payload)

    session.add(
        ProcessedWebhookEvent(
            shop_domain=shop_domain,
            topic="ORDERS_CREATE",
            event_id=event_id,
            status="forwarded",
        )
    )
    session.commit()
    return {"received": True}


@app.post("/webhooks/app/uninstalled")
async def app_uninstalled_webhook(request: Request, session: Session = Depends(get_session)):
    body = await request.body()
    if not verify_webhook_hmac(body=body, supplied_hmac=request.headers.get("x-shopify-hmac-sha256")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook HMAC")

    shop_header = request.headers.get("x-shopify-shop-domain")
    if not shop_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing x-shopify-shop-domain header",
        )
    shop_domain = normalize_shop_domain(shop_header)

    installation = session.scalars(
        select(ShopInstallation).where(ShopInstallation.shop_domain == shop_domain)
    ).first()
    if installation:
        installation.uninstalled_at = datetime.now(timezone.utc)
        installation.admin_access_token = ""
        installation.storefront_access_token = None
        installation.updated_at = datetime.now(timezone.utc)
        session.add(installation)
        session.commit()

    return {"received": True}
