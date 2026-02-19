from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response as BinaryResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

import stripe

from app.config import settings
from app.db.deps import get_session
from app.db.enums import FunnelEventTypeEnum, FunnelPageVersionStatusEnum, FunnelStatusEnum
from app.db.models import (
    Funnel,
    FunnelEvent,
    FunnelPage,
    FunnelPageVersion,
    Product,
    ProductVariant,
)
from app.db.repositories.funnels import (
    FunnelPageVersionsRepository,
    FunnelPagesRepository,
    FunnelPublicRepository,
    FunnelsRepository,
)
from app.schemas.commerce import PublicCheckoutRequest
from app.schemas.funnels import PublicEventsIngestRequest
from app.services.design_systems import resolve_design_system_tokens
from app.services.media_storage import MediaStorage
from app.services.public_routing import normalize_route_token, require_product_route_slug
from app.services.shopify_checkout import create_shopify_checkout

router = APIRouter(prefix="/public", tags=["public"])


def _get_funnel_or_404(*, session: Session, product_slug: str, funnel_slug: str) -> tuple[Funnel, Product, str]:
    funnels_repo = FunnelsRepository(session)
    funnel = funnels_repo.get_by_route_slug(route_slug=funnel_slug)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")
    if funnel.status == FunnelStatusEnum.disabled:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Funnel disabled")
    if not funnel.product_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Funnel has no product configured.",
        )
    product = session.scalars(
        select(Product).where(Product.id == funnel.product_id, Product.org_id == funnel.org_id)
    ).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    try:
        resolved_product_slug = require_product_route_slug(product=product)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    requested_product_slug = normalize_route_token(product_slug)
    if requested_product_slug != resolved_product_slug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")
    return funnel, product, resolved_product_slug


def _get_funnel_by_slug_or_404(*, session: Session, funnel_slug: str) -> Funnel:
    funnels_repo = FunnelsRepository(session)
    funnel = funnels_repo.get_by_route_slug(route_slug=funnel_slug)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")
    if funnel.status == FunnelStatusEnum.disabled:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Funnel disabled")
    return funnel


def _publication_id_for_public_response(funnel: Funnel) -> str:
    """
    Public runtime expects a publicationId string. For unpublished funnels, we return the funnel id
    (a valid UUID) so public event ingestion won't crash on invalid UUID input.
    """

    return str(funnel.active_publication_id or funnel.id)


def _allowed_hosts(request: Request) -> set[str]:
    raw_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    if not raw_host:
        return set()
    hosts: set[str] = set()
    for part in raw_host.split(","):
        part = part.strip()
        if part:
            hosts.add(part)
    normalized: set[str] = set()
    for host in hosts:
        normalized.add(host)
        if ":" in host:
            normalized.add(host.split(":")[0])
    return {host for host in normalized if host}


def _validate_return_url(url: str, allowed_hosts: set[str], label: str) -> None:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} must be an absolute URL.",
        )
    if not allowed_hosts:
        return
    host = parsed.netloc
    hostname = parsed.hostname or ""
    if host not in allowed_hosts and hostname not in allowed_hosts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} host must match the request host.",
        )


def _metadata_value(value: object, key: str) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))
    if len(text) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{key} is too large for Stripe metadata.",
        )
    return text


def _preview_page_map(*, session: Session, funnel_id: str) -> dict[str, str]:
    """
    For unpublished funnels, we treat "preview" pages as those with at least one saved version
    (draft or approved).
    """

    preview_page_ids = set(
        str(page_id)
        for page_id in session.scalars(
            select(FunnelPageVersion.page_id)
            .join(FunnelPage, FunnelPage.id == FunnelPageVersion.page_id)
            .where(
                FunnelPage.funnel_id == funnel_id,
                FunnelPageVersion.status.in_(
                    [FunnelPageVersionStatusEnum.draft, FunnelPageVersionStatusEnum.approved]
                ),
            )
            .distinct()
        ).all()
    )
    pages_repo = FunnelPagesRepository(session)
    pages = pages_repo.list(funnel_id=funnel_id)
    return {str(page.id): page.slug for page in pages if str(page.id) in preview_page_ids}


@router.get("/funnels/{product_slug}/{funnel_slug}/meta")
def public_funnel_meta(
    product_slug: str,
    funnel_slug: str,
    response: Response,
    session: Session = Depends(get_session),
):
    public_repo = FunnelPublicRepository(session)
    funnel, _product, resolved_product_slug = _get_funnel_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )

    publication_id = _publication_id_for_public_response(funnel)
    if funnel.active_publication_id:
        publication = public_repo.get_active_publication(
            funnel_id=str(funnel.id), publication_id=str(funnel.active_publication_id)
        )
        if not publication:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publication not found")
        pages = public_repo.list_publication_pages(publication_id=str(funnel.active_publication_id))
        entry_slug = None
        for pp in pages:
            if str(pp.page_id) == str(publication.entry_page_id):
                entry_slug = pp.slug_at_publish
                break
        if not entry_slug:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry page not found")

        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return {
            "productSlug": resolved_product_slug,
            "funnelSlug": str(funnel.route_slug),
            "funnelId": str(funnel.id),
            "publicationId": publication_id,
            "entrySlug": entry_slug,
            "pages": [{"pageId": str(pp.page_id), "slug": pp.slug_at_publish} for pp in pages],
        }

    # Preview mode: allow viewing approved pages even if the funnel hasn't been published yet.
    page_map = _preview_page_map(session=session, funnel_id=str(funnel.id))
    if not funnel.entry_page_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry page not found")
    entry_slug = page_map.get(str(funnel.entry_page_id))
    if not entry_slug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry page has no saved version")

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {
        "productSlug": resolved_product_slug,
        "funnelSlug": str(funnel.route_slug),
        "funnelId": str(funnel.id),
        "publicationId": publication_id,
        "entrySlug": entry_slug,
        "pages": [{"pageId": page_id, "slug": slug} for page_id, slug in page_map.items()],
    }


@router.get("/funnels/{product_slug}/{funnel_slug}/pages/{slug}")
def public_funnel_page(
    product_slug: str,
    funnel_slug: str,
    slug: str,
    response: Response,
    session: Session = Depends(get_session),
):
    public_repo = FunnelPublicRepository(session)
    funnel, _product, resolved_product_slug = _get_funnel_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )

    publication_id = _publication_id_for_public_response(funnel)
    if funnel.active_publication_id:
        pp = public_repo.get_publication_page_by_slug(publication_id=str(funnel.active_publication_id), slug=slug)
        if not pp:
            redirect = public_repo.get_redirect(funnel_id=str(funnel.id), from_slug=slug)
            if redirect:
                response.headers["X-Robots-Tag"] = "noindex, nofollow"
                return {"redirectToSlug": redirect.to_slug}
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

        version = public_repo.get_page_version(version_id=str(pp.page_version_id))
        if not version:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page content not found")

        page_map = {
            str(item.page_id): item.slug_at_publish
            for item in public_repo.list_publication_pages(publication_id=str(funnel.active_publication_id))
        }
        page = session.scalars(select(FunnelPage).where(FunnelPage.id == pp.page_id)).first()
        design_system_tokens = resolve_design_system_tokens(
            session=session,
            org_id=str(funnel.org_id),
            client_id=str(funnel.client_id),
            funnel=funnel,
            page=page,
        )
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return {
            "productSlug": resolved_product_slug,
            "funnelId": str(funnel.id),
            "publicationId": publication_id,
            "pageId": str(pp.page_id),
            "slug": pp.slug_at_publish,
            "puckData": version.puck_data,
            "pageMap": page_map,
            "designSystemTokens": design_system_tokens,
            "nextPageId": str(page.next_page_id) if page and page.next_page_id else None,
        }

    # Preview mode: allow viewing pages with draft or approved versions even if the funnel hasn't been published yet.
    page = session.scalars(
        select(FunnelPage).where(FunnelPage.funnel_id == funnel.id, FunnelPage.slug == slug)
    ).first()
    if not page:
        redirect = public_repo.get_redirect(funnel_id=str(funnel.id), from_slug=slug)
        if redirect:
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
            return {"redirectToSlug": redirect.to_slug}
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    versions_repo = FunnelPageVersionsRepository(session)
    draft = versions_repo.latest_for_page(page_id=str(page.id), status=FunnelPageVersionStatusEnum.draft)
    approved = versions_repo.latest_for_page(page_id=str(page.id), status=FunnelPageVersionStatusEnum.approved)
    version = draft or approved
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page has no saved version")

    page_map = _preview_page_map(session=session, funnel_id=str(funnel.id))
    design_system_tokens = resolve_design_system_tokens(
        session=session,
        org_id=str(funnel.org_id),
        client_id=str(funnel.client_id),
        funnel=funnel,
        page=page,
    )
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {
        "productSlug": resolved_product_slug,
        "funnelId": str(funnel.id),
        "publicationId": publication_id,
        "pageId": str(page.id),
        "slug": page.slug,
        "puckData": version.puck_data,
        "pageMap": page_map,
        "designSystemTokens": design_system_tokens,
        "nextPageId": str(page.next_page_id) if page.next_page_id else None,
    }


@router.get("/funnels/{product_slug}/{funnel_slug}/graph")
def public_funnel_graph(
    product_slug: str,
    funnel_slug: str,
    response: Response,
    session: Session = Depends(get_session),
):
    funnel, _product, resolved_product_slug = _get_funnel_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )
    public_repo = FunnelPublicRepository(session)
    publication_id = _publication_id_for_public_response(funnel)
    if funnel.active_publication_id:
        publication = public_repo.get_active_publication(
            funnel_id=str(funnel.id), publication_id=str(funnel.active_publication_id)
        )
        if not publication:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publication not found")
        pages = public_repo.list_publication_pages(publication_id=str(funnel.active_publication_id))
        links = public_repo.list_publication_links(publication_id=str(funnel.active_publication_id))
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return {
            "productSlug": resolved_product_slug,
            "funnelSlug": str(funnel.route_slug),
            "funnelId": str(funnel.id),
            "publicationId": publication_id,
            "entryPageId": str(publication.entry_page_id),
            "pages": [{"pageId": str(pp.page_id), "slug": pp.slug_at_publish} for pp in pages],
            "links": [jsonable_encoder(link) for link in links],
        }

    # Preview mode: only return pages that have at least one saved version (draft or approved) for the graph.
    page_map = _preview_page_map(session=session, funnel_id=str(funnel.id))
    if not funnel.entry_page_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry page not found")
    if str(funnel.entry_page_id) not in page_map:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry page has no saved version")

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {
        "productSlug": resolved_product_slug,
        "funnelSlug": str(funnel.route_slug),
        "funnelId": str(funnel.id),
        "publicationId": publication_id,
        "entryPageId": str(funnel.entry_page_id),
        "pages": [{"pageId": page_id, "slug": slug_value} for page_id, slug_value in page_map.items()],
        "links": [],
    }


@router.get("/funnels/{product_slug}/{funnel_slug}/commerce")
def public_funnel_commerce(
    product_slug: str,
    funnel_slug: str,
    response: Response,
    session: Session = Depends(get_session),
):
    funnel, product, resolved_product_slug = _get_funnel_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )

    variants_query = select(ProductVariant).where(ProductVariant.product_id == product.id)
    if funnel.selected_offer_id:
        variants_query = variants_query.where(ProductVariant.offer_id == funnel.selected_offer_id)
    variants = session.scalars(variants_query).all()
    if not variants:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product variants are not configured for this funnel product.",
        )
    serialized_variants: list[dict] = []
    for variant in variants:
        data = jsonable_encoder(variant)
        data.pop("external_price_id", None)
        serialized_variants.append(data)

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {
        "productSlug": resolved_product_slug,
        "funnelSlug": str(funnel.route_slug),
        "funnelId": str(funnel.id),
        "product": {
            **jsonable_encoder(product),
            "variants": serialized_variants,
            "variants_count": len(serialized_variants),
        },
    }


@router.post("/checkout")
def public_checkout(
    payload: PublicCheckoutRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    if payload.quantity < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="quantity must be >= 1")

    funnel = _get_funnel_by_slug_or_404(session=session, funnel_slug=payload.funnelSlug)
    if not funnel.product_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Funnel has no product configured.",
        )

    variant: ProductVariant | None = None
    if payload.variantId:
        variant_query = select(ProductVariant).where(
            ProductVariant.id == payload.variantId,
            ProductVariant.product_id == funnel.product_id,
        )
        if funnel.selected_offer_id:
            variant_query = variant_query.where(ProductVariant.offer_id == funnel.selected_offer_id)
        variant = session.scalars(variant_query).first()
        if not variant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
        if variant.option_values is None and payload.selection:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selection does not match variant options.",
            )
        if variant.option_values is not None and payload.selection != variant.option_values:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selection does not match variant options.",
            )
    else:
        if not payload.selection:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="selection is required when variantId is not provided.",
            )
        candidates_query = select(ProductVariant).where(ProductVariant.product_id == funnel.product_id)
        if funnel.selected_offer_id:
            candidates_query = candidates_query.where(ProductVariant.offer_id == funnel.selected_offer_id)
        candidates = session.scalars(candidates_query).all()
        matches = [item for item in candidates if item.option_values == payload.selection]
        if len(matches) != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selection does not resolve to a single variant.",
            )
        variant = matches[0]

    if not variant:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Variant resolution failed.")

    if not variant.provider:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Variant provider is required for checkout.",
        )
    metadata = {
        "funnel_slug": _metadata_value(payload.funnelSlug, "funnelSlug"),
        "funnel_id": _metadata_value(str(funnel.id), "funnelId"),
        "offer_id": _metadata_value(str(funnel.selected_offer_id), "offerId") if funnel.selected_offer_id else None,
        "variant_id": _metadata_value(str(variant.id), "variantId"),
        # Legacy key kept for older webhooks/reporting paths.
        "price_point_id": _metadata_value(str(variant.id), "pricePointId"),
        "page_id": _metadata_value(payload.pageId, "pageId"),
        "visitor_id": _metadata_value(payload.visitorId, "visitorId"),
        "session_id": _metadata_value(payload.sessionId, "sessionId"),
        "selection": _metadata_value(payload.selection, "selection"),
        "utm": _metadata_value(payload.utm, "utm"),
        "quantity": _metadata_value(str(payload.quantity), "quantity"),
    }
    metadata = {key: value for key, value in metadata.items() if value}
    if variant.provider == "stripe":
        if not variant.external_price_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Stripe price ID is missing for this variant.",
            )
        if not settings.STRIPE_SECRET_KEY:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Stripe is not configured.",
            )
        stripe.api_key = settings.STRIPE_SECRET_KEY

        allowed_hosts = _allowed_hosts(request)
        if not allowed_hosts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Host header is required for checkout.",
            )
        _validate_return_url(str(payload.successUrl), allowed_hosts, "successUrl")
        _validate_return_url(str(payload.cancelUrl), allowed_hosts, "cancelUrl")

        checkout_session = stripe.checkout.Session.create(
            mode="payment",
            success_url=str(payload.successUrl),
            cancel_url=str(payload.cancelUrl),
            line_items=[{"price": variant.external_price_id, "quantity": payload.quantity}],
            metadata=metadata,
        )
        return {"checkoutUrl": checkout_session.url, "sessionId": checkout_session.id}

    if variant.provider == "shopify":
        if not variant.external_price_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Shopify variant GID is missing for this variant.",
            )
        checkout = create_shopify_checkout(
            client_id=str(funnel.client_id),
            variant_gid=variant.external_price_id,
            quantity=payload.quantity,
            metadata=metadata,
        )
        return {"checkoutUrl": checkout["checkoutUrl"], "sessionId": checkout["cartId"]}

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Unsupported checkout provider.",
    )


@router.post("/events")
def ingest_public_events(
    payload: PublicEventsIngestRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    if not payload.events:
        return {"ingested": 0}

    publication_ids = {event.publicationId for event in payload.events}
    if len(publication_ids) != 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Batch must share publicationId")
    publication_id = next(iter(publication_ids))

    try:
        publication_uuid = UUID(str(publication_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="publicationId must be a valid UUID.",
        ) from exc

    funnel = session.scalars(
        select(Funnel).where(Funnel.active_publication_id == publication_uuid)
    ).first()
    if not funnel:
        # Preview mode: publicationId is the funnel id (see _publication_id_for_public_response()).
        # Unpublished funnels cannot persist events because funnel_events.publication_id is a FK.
        preview_funnel = session.scalars(
            select(Funnel).where(
                Funnel.id == publication_uuid,
                Funnel.active_publication_id.is_(None),
            )
        ).first()
        if preview_funnel:
            return {"ingested": 0}
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publication not found")

    host = request.headers.get("host")
    ingested = 0
    for ev in payload.events:
        occurred_at = ev.occurredAt or datetime.now(timezone.utc)
        try:
            event_type = FunnelEventTypeEnum(ev.eventType)
        except Exception:
            continue

        session.add(
            FunnelEvent(
                occurred_at=occurred_at,
                org_id=funnel.org_id,
                client_id=funnel.client_id,
                campaign_id=funnel.campaign_id,
                funnel_id=funnel.id,
                publication_id=publication_uuid,
                page_id=ev.pageId,
                event_type=event_type,
                visitor_id=ev.visitorId,
                session_id=ev.sessionId,
                host=host,
                path=ev.path,
                referrer=ev.referrer,
                utm=ev.utm,
                props=ev.props,
            )
        )
        ingested += 1

    session.commit()
    return {"ingested": ingested}


@router.get("/assets/{public_id}")
def public_asset(
    public_id: str,
    session: Session = Depends(get_session),
):
    public_repo = FunnelPublicRepository(session)
    asset = public_repo.get_asset_by_public_id(public_id=public_id)
    if (
        not asset
        or asset.asset_kind != "image"
        or asset.file_status != "ready"
        or not asset.storage_key
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    storage = MediaStorage()
    try:
        data, content_type = storage.download_bytes(key=asset.storage_key)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    headers = {"Cache-Control": "public, max-age=31536000, immutable"}
    return BinaryResponse(
        content=data,
        media_type=asset.content_type or content_type or "application/octet-stream",
        headers=headers,
    )
