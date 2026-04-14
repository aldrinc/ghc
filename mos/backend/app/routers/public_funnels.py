from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response as BinaryResponse
from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

import stripe

from app.config import settings
from app.db.deps import get_session
from app.db.enums import FunnelEventTypeEnum, FunnelPageVersionStatusEnum, FunnelStatusEnum
from app.db.models import (
    Client,
    ClientComplianceProfile,
    ClientMedusaConfig,
    DesignSystem,
    Funnel,
    FunnelEvent,
    FunnelPage,
    FunnelPageVersion,
    Product,
    ProductVariant,
    Site,
    SitePage,
    SitePageVersion,
)
from app.db.repositories.funnels import (
    FunnelPageVersionsRepository,
    FunnelPagesRepository,
    FunnelPublicRepository,
    FunnelsRepository,
)
from app.db.repositories.paid_ads_qa import PaidAdsQaRepository
from app.schemas.commerce import (
    PublicCheckoutRequest,
    SiteCommerceCartCreateRequest,
    SiteCommerceCartUpdateRequest,
    SiteCommerceLineItemAddRequest,
    SiteCommerceLineItemUpdateRequest,
    SiteCommerceShippingMethodRequest,
    SiteCommercePaymentSessionRequest,
)
from app.schemas.funnels import PublicEventsIngestRequest
from app.services.compliance import (
    get_policy_template,
    list_policy_page_keys,
    render_policy_template_markdown,
)
from app.services.design_systems import resolve_design_system_tokens
from app.services.paid_ads_qa import clean_optional_text, normalize_tracking_provider
from app.services.funnel_metadata import build_public_page_metadata_for_context
from app.services.imported_html_runtime import resolve_funnel_page_stage
from app.services.commerce_provider import create_managed_checkout
from app.services.media_storage import MediaStorage
from app.services.public_routing import normalize_route_token, require_product_route_slug
from app.services.medusa_connection import (
    get_client_medusa_config,
    get_stripe_account_profile_by_id,
)
from app.services.site_publications import get_active_site_publication, list_site_publication_pages
from app.services.medusa_store_runtime import (
    MedusaStoreConfig,
    get_medusa_store_config,
    medusa_list_regions,
    medusa_list_products,
    medusa_get_product,
    medusa_get_product_by_handle,
    medusa_get_products_by_ids,
    medusa_list_collections,
    medusa_list_categories,
    medusa_create_cart,
    medusa_get_cart,
    medusa_update_cart,
    medusa_add_cart_line_item,
    medusa_update_cart_line_item,
    medusa_delete_cart_line_item,
    medusa_list_shipping_options,
    medusa_add_shipping_method,
    medusa_list_payment_providers,
    medusa_create_payment_collection,
    medusa_initialize_payment_session,
    medusa_complete_cart,
    filter_payment_providers_by_allowlist,
    validate_provider_id_against_allowlist,
    resolve_default_payment_provider_id,
)

router = APIRouter(prefix="/public", tags=["public"])
_MOS_META_TRACKING_METADATA_KEY = "mosMetaTracking"


def _resolve_public_medusa_stripe_account_id(
    *,
    session: Session,
    config: ClientMedusaConfig,
) -> str | None:
    if not config.stripe_account_profile_id:
        return None
    profile = get_stripe_account_profile_by_id(
        session=session,
        profile_id=str(config.stripe_account_profile_id),
    )
    if not profile:
        return None
    return profile.stripe_account_id


def create_shopify_checkout(
    *,
    client_id: str,
    variant_gid: str,
    quantity: int,
    metadata: dict[str, object],
) -> dict[str, str]:
    return create_managed_checkout(
        provider="shopify",
        client_id=client_id,
        external_variant_id=variant_gid,
        quantity=quantity,
        metadata=metadata,
    )


def _public_page_stage(
    *, slug: str | None = None, template_id: str | None = None, page_name: str | None = None
) -> str:
    return resolve_funnel_page_stage(
        slug=slug,
        template_id=template_id,
        page_name=page_name,
    )


# Site page types for commerce experiences
# These map to the page_type field in site blueprints
SITE_PAGE_TYPES = {
    "home",
    "store",
    "collection",
    "category",
    "product_detail",
    "cart",
    "checkout",
    "privacy_policy",
    "terms_of_service",
    "returns_refunds_policy",
    "shipping_policy",
    "contact_support",
    "account_dashboard",
    "account_profile",
    "account_addresses",
    "account_orders",
    "account_order_detail",
    "order_confirmed",
    "order_transfer",
    "order_transfer_accept",
    "order_transfer_decline",
}


def _site_page_type(
    *,
    slug: str | None = None,
    template_id: str | None = None,
    page_type: str | None = None,
) -> str | None:
    """Determine the site page type for commerce experiences.

    Returns the page_type if this is a recognized site page type,
    or None if not a recognized site page type.
    """
    normalized_page_type = clean_optional_text(page_type)
    if normalized_page_type in SITE_PAGE_TYPES:
        return normalized_page_type

    normalized_template_id = clean_optional_text(template_id)
    if not normalized_template_id:
        return None

    # Map template IDs to site page types
    # B2B templates
    template_to_page_type = {
        "medusa-b2b-home": "home",
        "medusa-b2b-category": "category",
        "medusa-b2b-pdp": "product_detail",
        "medusa-b2b-cart": "cart",
        "medusa-b2b-checkout": "checkout",
        "medusa-b2b-policy-privacy": "privacy_policy",
        "medusa-b2b-policy-terms": "terms_of_service",
        "medusa-b2b-policy-returns": "returns_refunds_policy",
        "medusa-b2b-policy-shipping": "shipping_policy",
        "medusa-b2b-policy-contact": "contact_support",
        # B2C templates
        "medusa-b2c-home": "home",
        "medusa-b2c-store": "store",
        "medusa-b2c-collection": "collection",
        "medusa-b2c-category": "category",
        "medusa-b2c-product": "product_detail",
        "medusa-b2c-cart": "cart",
        "medusa-b2c-checkout": "checkout",
        "medusa-b2c-policy-privacy": "privacy_policy",
        "medusa-b2c-policy-terms": "terms_of_service",
        "medusa-b2c-policy-returns": "returns_refunds_policy",
        "medusa-b2c-policy-shipping": "shipping_policy",
        "medusa-b2c-policy-contact": "contact_support",
        "medusa-b2c-account-dashboard": "account_dashboard",
        "medusa-b2c-account-profile": "account_profile",
        "medusa-b2c-account-addresses": "account_addresses",
        "medusa-b2c-account-orders": "account_orders",
        "medusa-b2c-account-order-detail": "account_order_detail",
        "medusa-b2c-order-confirmed": "order_confirmed",
        "medusa-b2c-order-transfer": "order_transfer",
        "medusa-b2c-order-transfer-accept": "order_transfer_accept",
        "medusa-b2c-order-transfer-decline": "order_transfer_decline",
    }

    return template_to_page_type.get(normalized_template_id)


def _require_absolute_public_website_url(website_url: str | None) -> str:
    cleaned = clean_optional_text(website_url)
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="website_url query parameter is required.",
        )

    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="website_url must be an absolute URL (http/https).",
        )
    return cleaned


def _public_policy_placeholder_values(
    *,
    profile: ClientComplianceProfile,
    workspace_name: str,
    website_url: str,
) -> dict[str, str]:
    values: dict[str, str] = {}
    scalar_fields = {
        "legal_business_name": profile.legal_business_name,
        "operating_entity_name": profile.operating_entity_name,
        "company_address_text": profile.company_address_text,
        "business_license_identifier": profile.business_license_identifier,
        "support_email": profile.support_email,
        "support_phone": profile.support_phone,
        "support_hours_text": profile.support_hours_text,
        "response_time_commitment": profile.response_time_commitment,
    }
    for key, value in scalar_fields.items():
        if isinstance(value, str) and value.strip():
            values[key] = value.strip()

    metadata = profile.metadata_json if isinstance(profile.metadata_json, dict) else {}
    for key, raw_value in metadata.items():
        if not isinstance(key, str):
            continue
        placeholder_key = key.strip()
        if not placeholder_key or raw_value is None:
            continue
        if isinstance(raw_value, str):
            cleaned = raw_value.strip()
            if cleaned:
                values[placeholder_key] = cleaned
            continue
        if isinstance(raw_value, (int, float, bool)):
            values[placeholder_key] = str(raw_value)

    values["brand_name"] = workspace_name
    values["website_url"] = website_url
    return values


def _resolve_public_medusa_runtime_config(
    *, session: Session, funnel: Funnel
) -> dict[str, Any] | None:
    if clean_optional_text(funnel.site_family) != "medusa-b2c-starter":
        return None

    config = get_client_medusa_config(
        session=session,
        org_id=str(funnel.org_id),
        client_id=str(funnel.client_id),
    )
    if not config or not clean_optional_text(config.base_url):
        return None
    if not clean_optional_text(config.publishable_key_encrypted):
        return None

    return {
        "backendUrl": clean_optional_text(config.base_url),
        "publishableKey": clean_optional_text(config.publishable_key_encrypted),
        "stripeAccountId": _resolve_public_medusa_stripe_account_id(
            session=session,
            config=config,
        ),
        "defaultCountryCode": "us",
    }


def _site_uses_b2c_medusa_runtime(site: Site) -> bool:
    if clean_optional_text(site.site_family) == "medusa-b2b-starter":
        return False
    return clean_optional_text(site.commerce_provider) == "medusa"


def _resolve_public_medusa_runtime_config_for_site(
    *, session: Session, site: Site
) -> dict[str, Any] | None:
    if not _site_uses_b2c_medusa_runtime(site):
        return None

    config = get_client_medusa_config(
        session=session,
        org_id=str(site.org_id),
        client_id=str(site.client_id),
    )
    if not config or not clean_optional_text(config.base_url):
        return None
    if not clean_optional_text(config.publishable_key_encrypted):
        return None

    return {
        "backendUrl": clean_optional_text(config.base_url),
        "publishableKey": clean_optional_text(config.publishable_key_encrypted),
        "stripeAccountId": _resolve_public_medusa_stripe_account_id(
            session=session,
            config=config,
        ),
        "defaultCountryCode": "us",
    }


def _resolve_public_site_design_system_tokens(
    *,
    session: Session,
    site: Site,
    page: SitePage | None = None,
) -> dict[str, Any] | None:
    if page and page.design_system_id:
        design_system = session.scalars(
            select(DesignSystem).where(
                DesignSystem.org_id == UUID(str(site.org_id)),
                DesignSystem.id == UUID(str(page.design_system_id)),
            )
        ).first()
        if not design_system:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Page '{page.id}' references design_system_id '{page.design_system_id}' "
                    "which no longer exists. Please reconfigure the page override."
                ),
            )
        return design_system.tokens

    site_mode = (
        site.theme_binding_mode.value
        if hasattr(site.theme_binding_mode, "value")
        else site.theme_binding_mode
    )

    if site_mode == "standalone":
        return None

    if site_mode == "design_system":
        if not site.design_system_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Site '{site.id}' has theme_binding_mode 'design_system' "
                    "but is missing a bound design_system_id."
                ),
            )
        design_system = session.scalars(
            select(DesignSystem).where(
                DesignSystem.org_id == UUID(str(site.org_id)),
                DesignSystem.id == UUID(str(site.design_system_id)),
            )
        ).first()
        if not design_system:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Site '{site.id}' references design_system_id '{site.design_system_id}' "
                    "which no longer exists. Please reconfigure the site's theme binding."
                ),
            )
        return design_system.tokens

    if site_mode == "workspace_default":
        return resolve_design_system_tokens(
            session=session,
            org_id=str(site.org_id),
            client_id=str(site.client_id),
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=(
            f"Site '{site.id}' has unrecognized theme_binding_mode '{site_mode}'. "
            "Valid modes are: standalone, workspace_default, design_system."
        ),
    )


def _resolve_site_by_route_token(*, session: Session, site_token: str) -> Site | None:
    token = str(site_token or "").strip()
    if not token:
        return None

    site = session.scalars(select(Site).where(Site.route_slug == token)).first()
    if site:
        return site

    try:
        parsed_site_id = str(UUID(token))
    except ValueError:
        short_token = token.lower()
        if len(short_token) != 8 or any(ch not in "0123456789abcdef" for ch in short_token):
            return None
        matches = list(
            session.scalars(
                select(Site)
                .where(func.left(cast(Site.id, String), 8) == short_token)
                .order_by(Site.created_at.asc(), Site.id.asc())
                .limit(2)
            ).all()
        )
        if len(matches) == 1:
            return matches[0]
        return None

    return session.scalars(select(Site).where(Site.id == parsed_site_id)).first()


def _get_site_or_404(
    *, session: Session, product_slug: str, site_slug: str
) -> tuple[Site, Product, str]:
    site = _resolve_site_by_route_token(session=session, site_token=site_slug)
    if not site:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")
    if not site.product_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Site has no product configured.",
        )
    product = session.scalars(
        select(Product).where(Product.id == site.product_id, Product.org_id == site.org_id)
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
    return site, product, resolved_product_slug


def _get_public_runtime_target_or_404(
    *, session: Session, product_slug: str, funnel_slug: str
) -> tuple[str, Funnel | Site, Product, str]:
    funnel = _resolve_funnel_by_route_token(session=session, funnel_token=funnel_slug)
    if funnel:
        resolved_funnel, product, resolved_product_slug = _get_funnel_or_404(
            session=session,
            product_slug=product_slug,
            funnel_slug=funnel_slug,
        )
        return "funnel", resolved_funnel, product, resolved_product_slug

    site = _resolve_site_by_route_token(session=session, site_token=funnel_slug)
    if site:
        resolved_site, product, resolved_product_slug = _get_site_or_404(
            session=session,
            product_slug=product_slug,
            site_slug=funnel_slug,
        )
        return "site", resolved_site, product, resolved_product_slug

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")


def _public_site_preview_pages(*, session: Session, site_id: str) -> list[SitePage]:
    preview_page_ids = {
        str(page_id)
        for page_id in session.scalars(
            select(SitePageVersion.page_id)
            .join(SitePage, SitePage.id == SitePageVersion.page_id)
            .where(
                SitePage.site_id == site_id,
                SitePageVersion.status.in_(["draft", "approved"]),
            )
            .distinct()
        ).all()
    }
    pages = session.scalars(
        select(SitePage)
        .where(SitePage.site_id == site_id)
        .order_by(SitePage.ordering.asc(), SitePage.created_at.asc())
    ).all()
    return [page for page in pages if str(page.id) in preview_page_ids]


def _public_site_preview_version(*, session: Session, page_id: str) -> SitePageVersion | None:
    draft = session.scalars(
        select(SitePageVersion)
        .where(SitePageVersion.page_id == page_id, SitePageVersion.status == "draft")
        .order_by(SitePageVersion.created_at.desc())
    ).first()
    if draft:
        return draft
    return session.scalars(
        select(SitePageVersion)
        .where(SitePageVersion.page_id == page_id, SitePageVersion.status == "approved")
        .order_by(SitePageVersion.created_at.desc())
    ).first()


def _build_public_site_metadata(*, site: Site, page: SitePage) -> dict[str, Any]:
    site_name = clean_optional_text(site.name) or "Store"
    page_name = clean_optional_text(page.name) or site_name
    description = clean_optional_text(site.description) or f"{page_name} page."
    title = page_name if page_name.lower() == site_name.lower() else f"{page_name} | {site_name}"
    return {
        "title": title,
        "description": description,
        "lang": "en",
        "brandName": site_name,
    }


def _canonical_public_page_slug(
    *, slug: str | None = None, template_id: str | None = None, page_name: str | None = None
) -> str | None:
    raw_slug = clean_optional_text(slug)
    stage = _public_page_stage(slug=raw_slug, template_id=template_id, page_name=page_name)
    if stage == "pre_sales":
        return "presales"
    return raw_slug


def _public_page_slug_candidates(slug: str | None) -> list[str]:
    raw_slug = clean_optional_text(slug)
    if not raw_slug:
        return []

    candidates: list[str] = []
    normalized_slug = normalize_route_token(raw_slug)
    for candidate in (raw_slug, normalized_slug):
        cleaned = clean_optional_text(candidate)
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

    if normalized_slug == "presales" and "pre-sales" not in candidates:
        candidates.append("pre-sales")

    return candidates


def _is_legacy_public_presales_slug(slug: str | None) -> bool:
    return normalize_route_token(clean_optional_text(slug) or "") == "pre-sales"


def _resolve_funnel_by_route_token(*, session: Session, funnel_token: str) -> Funnel | None:
    token = str(funnel_token or "").strip()
    if not token:
        return None

    funnels_repo = FunnelsRepository(session)
    funnel = funnels_repo.get_by_route_slug(route_slug=token)
    if funnel:
        return funnel

    try:
        parsed_funnel_id = str(UUID(token))
    except ValueError:
        # Support short id aliases like "638d19db" by matching UUID prefix.
        short_token = token.lower()
        if len(short_token) != 8 or any(ch not in "0123456789abcdef" for ch in short_token):
            return None
        matches = list(
            session.scalars(
                select(Funnel)
                .where(func.left(cast(Funnel.id, String), 8) == short_token)
                .order_by(Funnel.created_at.asc(), Funnel.id.asc())
                .limit(2)
            ).all()
        )
        if len(matches) == 1:
            return matches[0]
        return None
    return session.scalars(select(Funnel).where(Funnel.id == parsed_funnel_id)).first()


def _get_funnel_or_404(
    *, session: Session, product_slug: str, funnel_slug: str
) -> tuple[Funnel, Product, str]:
    funnel = _resolve_funnel_by_route_token(session=session, funnel_token=funnel_slug)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")
    if funnel.status in {FunnelStatusEnum.disabled, FunnelStatusEnum.archived}:
        detail = (
            "Funnel archived" if funnel.status == FunnelStatusEnum.archived else "Funnel disabled"
        )
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=detail)
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
    funnel = _resolve_funnel_by_route_token(session=session, funnel_token=funnel_slug)
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")
    if funnel.status in {FunnelStatusEnum.disabled, FunnelStatusEnum.archived}:
        detail = (
            "Funnel archived" if funnel.status == FunnelStatusEnum.archived else "Funnel disabled"
        )
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=detail)
    return funnel


def _publication_id_for_public_response(funnel: Funnel) -> str:
    """
    Public runtime expects a publicationId string. For unpublished funnels, we return the funnel id
    (a valid UUID) so public event ingestion won't crash on invalid UUID input.
    """

    return str(funnel.active_publication_id or funnel.id)


def _site_publication_id_for_public_response(site: Site) -> str:
    return str(site.active_site_publication_id or site.id)


def _public_site_meta_response(
    *,
    session: Session,
    site: Site,
    resolved_product_slug: str,
    response: Response,
) -> dict[str, Any]:
    publication_id = _site_publication_id_for_public_response(site)
    if site.active_site_publication_id:
        publication = get_active_site_publication(session, site_id=str(site.id))
        if not publication:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Publication not found"
            )
        pages = list_site_publication_pages(session, publication_id=str(publication.id))
        entry_slug = None
        for item in pages:
            if str(item.page_id) == str(publication.entry_page_id):
                entry_slug = item.slug_at_publish
                break
        if not entry_slug:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Entry page not found"
            )

        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return {
            "productSlug": resolved_product_slug,
            "funnelSlug": str(site.route_slug or site.id),
            "funnelId": str(site.id),
            "publicationId": publication_id,
            "entrySlug": entry_slug,
            "medusaRuntimeConfig": _resolve_public_medusa_runtime_config_for_site(
                session=session,
                site=site,
            ),
            "pages": [
                {
                    "pageId": str(item.page_id),
                    "slug": item.slug_at_publish,
                }
                for item in pages
            ],
        }

    preview_pages = _public_site_preview_pages(session=session, site_id=str(site.id))
    if not site.entry_page_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry page not found")
    entry_page = next((page for page in preview_pages if str(page.id) == str(site.entry_page_id)), None)
    if not entry_page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entry page has no saved version"
        )

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {
        "productSlug": resolved_product_slug,
        "funnelSlug": str(site.route_slug or site.id),
        "funnelId": str(site.id),
        "publicationId": publication_id,
        "entrySlug": entry_page.slug,
        "medusaRuntimeConfig": _resolve_public_medusa_runtime_config_for_site(
            session=session,
            site=site,
        ),
        "pages": [{"pageId": str(page.id), "slug": page.slug} for page in preview_pages],
    }


def _public_site_page_response(
    *,
    session: Session,
    site: Site,
    resolved_product_slug: str,
    slug: str,
    response: Response,
) -> dict[str, Any]:
    publication_id = _site_publication_id_for_public_response(site)
    slug_candidates = _public_page_slug_candidates(slug)

    if site.active_site_publication_id:
        publication = get_active_site_publication(session, site_id=str(site.id))
        if not publication:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Publication not found"
            )
        publication_pages = list_site_publication_pages(session, publication_id=str(publication.id))
        page_lookup = {item.slug_at_publish: item for item in publication_pages}
        publication_page = None
        for candidate_slug in slug_candidates:
            publication_page = page_lookup.get(candidate_slug)
            if publication_page:
                break
        if not publication_page:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

        page_rows = {
            str(page.id): page
            for page in session.scalars(
                select(SitePage).where(SitePage.id.in_([item.page_id for item in publication_pages]))
            ).all()
        }
        page = page_rows.get(str(publication_page.page_id))
        if not page:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
        version = session.scalars(
            select(SitePageVersion).where(SitePageVersion.id == publication_page.page_version_id)
        ).first()
        if not version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Page content not found"
            )

        page_map = {str(item.page_id): item.slug_at_publish for item in publication_pages}
        page_stage_map = {
            str(item.page_id): _public_page_stage(
                slug=item.slug_at_publish,
                template_id=page_rows.get(str(item.page_id)).template_id
                if page_rows.get(str(item.page_id))
                else None,
                page_name=page_rows.get(str(item.page_id)).name
                if page_rows.get(str(item.page_id))
                else None,
            )
            for item in publication_pages
        }
        page_type_map = {
            str(item.page_id): _site_page_type(
                slug=item.slug_at_publish,
                template_id=page_rows.get(str(item.page_id)).template_id
                if page_rows.get(str(item.page_id))
                else None,
                page_type=item.page_type_at_publish
                or (
                    page_rows.get(str(item.page_id)).page_type
                    if page_rows.get(str(item.page_id))
                    else None
                ),
            )
            for item in publication_pages
        }
        page_type_map = {k: v for k, v in page_type_map.items() if v is not None}
        canonical_slug = publication_page.slug_at_publish
        if normalize_route_token(slug) != normalize_route_token(canonical_slug):
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
            return {"redirectToSlug": canonical_slug}

        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return {
            "productSlug": resolved_product_slug,
            "funnelId": str(site.id),
            "publicationId": publication_id,
            "pageId": str(page.id),
            "slug": canonical_slug,
            "stage": _public_page_stage(
                slug=canonical_slug,
                template_id=page.template_id,
                page_name=page.name,
            ),
            "puckData": version.puck_data,
            "pageMap": page_map,
            "pageStageMap": page_stage_map,
            "pageTypeMap": page_type_map,
            "designSystemTokens": _resolve_public_site_design_system_tokens(
                session=session,
                site=site,
                page=page,
            ),
            "metadata": _build_public_site_metadata(site=site, page=page),
            "tracking": None,
            "nextPageId": None,
        }

    preview_pages = _public_site_preview_pages(session=session, site_id=str(site.id))
    page = None
    for candidate_slug in slug_candidates:
        page = next((item for item in preview_pages if item.slug == candidate_slug), None)
        if page:
            break
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    version = _public_site_preview_version(session=session, page_id=str(page.id))
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Page has no saved version"
        )

    page_map = {str(item.id): item.slug for item in preview_pages}
    page_stage_map = {
        str(item.id): _public_page_stage(
            slug=item.slug,
            template_id=item.template_id,
            page_name=item.name,
        )
        for item in preview_pages
    }
    page_type_map = {
        str(item.id): _site_page_type(
            slug=item.slug,
            template_id=item.template_id,
            page_type=item.page_type,
        )
        for item in preview_pages
    }
    page_type_map = {k: v for k, v in page_type_map.items() if v is not None}
    canonical_slug = page.slug
    if normalize_route_token(slug) != normalize_route_token(canonical_slug):
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return {"redirectToSlug": canonical_slug}

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {
        "productSlug": resolved_product_slug,
        "funnelId": str(site.id),
        "publicationId": publication_id,
        "pageId": str(page.id),
        "slug": canonical_slug,
        "stage": _public_page_stage(
            slug=canonical_slug,
            template_id=page.template_id,
            page_name=page.name,
        ),
        "puckData": version.puck_data,
        "pageMap": page_map,
        "pageStageMap": page_stage_map,
        "pageTypeMap": page_type_map,
        "designSystemTokens": _resolve_public_site_design_system_tokens(
            session=session,
            site=site,
            page=page,
        ),
        "metadata": _build_public_site_metadata(site=site, page=page),
        "tracking": None,
        "nextPageId": None,
    }


def _normalize_variant_provider(provider: str | None) -> str | None:
    cleaned = str(provider or "").strip().lower()
    return cleaned or None


def _is_validation_workspace_product(product: Product) -> bool:
    handle = str(product.handle or "").strip().lower()
    title = str(product.title or "").strip().lower()
    return "swipe-validation" in handle or "swipe validation" in title


def _dedupe_workspace_products_by_medusa_id(
    workspace_products: list[Product],
) -> tuple[list[Product], list[str]]:
    deduped: list[Product] = []
    duplicate_errors: list[str] = []
    seen_medusa_ids: dict[str, Product] = {}

    for product in workspace_products:
        medusa_product_id = str(product.medusa_product_id or "").strip()
        if not medusa_product_id:
            deduped.append(product)
            continue
        if medusa_product_id in seen_medusa_ids:
            duplicate_errors.append(
                f"Excluded duplicate workspace mapping for Medusa product '{medusa_product_id}' ({product.title})."
            )
            continue
        seen_medusa_ids[medusa_product_id] = product
        deduped.append(product)

    return deduped, duplicate_errors


def _is_checkout_ready_variant(variant: ProductVariant) -> bool:
    provider = _normalize_variant_provider(variant.provider)
    if not provider:
        return False
    external_price_id = str(variant.external_price_id or "").strip()
    if provider == "shopify":
        return external_price_id.startswith("gid://shopify/ProductVariant/")
    if provider in {"stripe", "medusa"}:
        return bool(external_price_id)
    return False


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


def _record_checkout_started_event(
    *,
    session: Session,
    request: Request,
    funnel: Funnel,
    page_id: str | None,
    visitor_id: str | None,
    session_id: str | None,
    utm: dict[str, object] | None,
    provider: str,
    checkout_session_id: str,
    variant: ProductVariant,
    quantity: int,
) -> None:
    publication_id = funnel.active_publication_id
    if publication_id is None or not page_id:
        return

    session.add(
        FunnelEvent(
            occurred_at=datetime.now(timezone.utc),
            org_id=funnel.org_id,
            client_id=funnel.client_id,
            campaign_id=funnel.campaign_id,
            funnel_id=funnel.id,
            publication_id=publication_id,
            page_id=page_id,
            event_type=FunnelEventTypeEnum.checkout_started,
            visitor_id=visitor_id,
            session_id=session_id,
            host=request.headers.get("host"),
            path=request.url.path,
            referrer=request.headers.get("referer"),
            utm=dict(utm or {}),
            props={
                "provider": provider,
                "checkout_session_id": checkout_session_id,
                "variant_id": str(variant.id),
                "offer_id": str(funnel.selected_offer_id) if funnel.selected_offer_id else None,
                "quantity": quantity,
            },
        )
    )
    session.commit()


def _resolve_public_meta_tracking(*, session: Session, funnel: Funnel) -> dict[str, str] | None:
    profile = PaidAdsQaRepository(session).get_platform_profile(
        org_id=str(funnel.org_id),
        client_id=str(funnel.client_id),
        platform="meta",
    )
    if profile is None:
        return None
    metadata = profile.metadata_json if isinstance(profile.metadata_json, dict) else {}
    mos_tracking = metadata.get(_MOS_META_TRACKING_METADATA_KEY)
    if not isinstance(mos_tracking, dict):
        return None
    if normalize_tracking_provider(mos_tracking.get("status")) != "active":
        return None
    if normalize_tracking_provider(mos_tracking.get("mode")) != "public_funnel_runtime":
        return None
    if normalize_tracking_provider(mos_tracking.get("channel")) != "meta":
        return None
    pixel_id = clean_optional_text(mos_tracking.get("pixelId")) or clean_optional_text(
        profile.pixel_id
    )
    if not pixel_id:
        return None
    return {
        "provider": "meta",
        "mode": "public_funnel_runtime",
        "metaPixelId": pixel_id,
    }


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
    target_kind, runtime_target, _product, resolved_product_slug = _get_public_runtime_target_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )
    if target_kind == "site":
        return _public_site_meta_response(
            session=session,
            site=runtime_target,
            resolved_product_slug=resolved_product_slug,
            response=response,
        )

    public_repo = FunnelPublicRepository(session)
    funnel = runtime_target

    publication_id = _publication_id_for_public_response(funnel)
    if funnel.active_publication_id:
        publication = public_repo.get_active_publication(
            funnel_id=str(funnel.id), publication_id=str(funnel.active_publication_id)
        )
        if not publication:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Publication not found"
            )
        pages = public_repo.list_publication_pages(publication_id=str(funnel.active_publication_id))
        page_rows = {
            str(page.id): page
            for page in session.scalars(
                select(FunnelPage).where(FunnelPage.id.in_([item.page_id for item in pages]))
            ).all()
        }
        entry_slug = None
        for pp in pages:
            if str(pp.page_id) == str(publication.entry_page_id):
                page = page_rows.get(str(pp.page_id))
                entry_slug = (
                    _canonical_public_page_slug(
                        slug=pp.slug_at_publish,
                        template_id=page.template_id if page else None,
                        page_name=page.name if page else None,
                    )
                    or pp.slug_at_publish
                )
                break
        if not entry_slug:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Entry page not found"
            )

        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return {
            "productSlug": resolved_product_slug,
            "funnelSlug": str(funnel.route_slug),
            "funnelId": str(funnel.id),
            "publicationId": publication_id,
            "entrySlug": entry_slug,
            "medusaRuntimeConfig": _resolve_public_medusa_runtime_config(
                session=session,
                funnel=funnel,
            ),
            "pages": [
                {
                    "pageId": str(pp.page_id),
                    "slug": (
                        _canonical_public_page_slug(
                            slug=pp.slug_at_publish,
                            template_id=page_rows.get(str(pp.page_id)).template_id
                            if page_rows.get(str(pp.page_id))
                            else None,
                            page_name=page_rows.get(str(pp.page_id)).name
                            if page_rows.get(str(pp.page_id))
                            else None,
                        )
                        or pp.slug_at_publish
                    ),
                }
                for pp in pages
            ],
        }

    # Preview mode: allow viewing approved pages even if the funnel hasn't been published yet.
    page_map = _preview_page_map(session=session, funnel_id=str(funnel.id))
    preview_pages = session.scalars(
        select(FunnelPage)
        .where(FunnelPage.funnel_id == funnel.id)
        .order_by(FunnelPage.ordering.asc(), FunnelPage.created_at.asc())
    ).all()
    preview_page_rows = {str(page.id): page for page in preview_pages}
    public_page_map = {
        page_id: (
            _canonical_public_page_slug(
                slug=preview_page_rows[page_id].slug,
                template_id=preview_page_rows[page_id].template_id,
                page_name=preview_page_rows[page_id].name,
            )
            or slug_value
        )
        for page_id, slug_value in page_map.items()
        if page_id in preview_page_rows
    }
    if not funnel.entry_page_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry page not found")
    entry_slug = public_page_map.get(str(funnel.entry_page_id))
    if not entry_slug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entry page has no saved version"
        )

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {
        "productSlug": resolved_product_slug,
        "funnelSlug": str(funnel.route_slug),
        "funnelId": str(funnel.id),
        "publicationId": publication_id,
        "entrySlug": entry_slug,
        "medusaRuntimeConfig": _resolve_public_medusa_runtime_config(
            session=session,
            funnel=funnel,
        ),
        "pages": [{"pageId": page_id, "slug": slug} for page_id, slug in public_page_map.items()],
    }


@router.get("/funnels/{product_slug}/{funnel_slug}/pages/{slug:path}")
def public_funnel_page(
    product_slug: str,
    funnel_slug: str,
    slug: str,
    response: Response,
    session: Session = Depends(get_session),
):
    target_kind, runtime_target, _product, resolved_product_slug = _get_public_runtime_target_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )
    if target_kind == "site":
        return _public_site_page_response(
            session=session,
            site=runtime_target,
            resolved_product_slug=resolved_product_slug,
            slug=slug,
            response=response,
        )

    public_repo = FunnelPublicRepository(session)
    funnel = runtime_target

    if _is_legacy_public_presales_slug(slug):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    publication_id = _publication_id_for_public_response(funnel)
    if funnel.active_publication_id:
        slug_candidates = _public_page_slug_candidates(slug)
        pp = None
        for candidate_slug in slug_candidates:
            pp = public_repo.get_publication_page_by_slug(
                publication_id=str(funnel.active_publication_id), slug=candidate_slug
            )
            if pp:
                break
        if not pp:
            redirect = None
            for candidate_slug in slug_candidates:
                redirect = public_repo.get_redirect(
                    funnel_id=str(funnel.id), from_slug=candidate_slug
                )
                if redirect:
                    break
            if redirect:
                response.headers["X-Robots-Tag"] = "noindex, nofollow"
                return {
                    "redirectToSlug": _canonical_public_page_slug(slug=redirect.to_slug)
                    or redirect.to_slug,
                }
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

        version = public_repo.get_page_version(version_id=str(pp.page_version_id))
        if not version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Page content not found"
            )

        publication_pages = public_repo.list_publication_pages(
            publication_id=str(funnel.active_publication_id)
        )
        page_map = {str(item.page_id): item.slug_at_publish for item in publication_pages}
        page_rows = {
            str(item.id): item
            for item in session.scalars(
                select(FunnelPage).where(
                    FunnelPage.id.in_([item.page_id for item in publication_pages])
                )
            ).all()
        }
        public_page_map = {
            page_id: (
                _canonical_public_page_slug(
                    slug=slug_value,
                    template_id=page_rows.get(page_id).template_id
                    if page_rows.get(page_id)
                    else None,
                    page_name=page_rows.get(page_id).name if page_rows.get(page_id) else None,
                )
                or slug_value
            )
            for page_id, slug_value in page_map.items()
        }
        page_stage_map = {
            str(item.page_id): _public_page_stage(
                slug=public_page_map[str(item.page_id)],
                template_id=page_rows.get(str(item.page_id)).template_id
                if page_rows.get(str(item.page_id))
                else None,
                page_name=page_rows.get(str(item.page_id)).name
                if page_rows.get(str(item.page_id))
                else None,
            )
            for item in publication_pages
        }
        # Build pageTypeMap for site experiences (maps page IDs to site page types)
        page_type_map = {
            str(item.page_id): _site_page_type(
                slug=public_page_map.get(str(item.page_id)),
                template_id=page_rows.get(str(item.page_id)).template_id
                if page_rows.get(str(item.page_id))
                else None,
                page_type=page_rows.get(str(item.page_id)).page_type
                if page_rows.get(str(item.page_id))
                else None,
            )
            for item in publication_pages
        }
        page_type_map = {k: v for k, v in page_type_map.items() if v is not None}
        page = session.scalars(select(FunnelPage).where(FunnelPage.id == pp.page_id)).first()
        canonical_slug = (
            _canonical_public_page_slug(
                slug=pp.slug_at_publish,
                template_id=page.template_id if page else None,
                page_name=page.name if page else None,
            )
            or pp.slug_at_publish
        )
        if normalize_route_token(slug) != normalize_route_token(canonical_slug):
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
            return {"redirectToSlug": canonical_slug}
        design_system_tokens = resolve_design_system_tokens(
            session=session,
            org_id=str(funnel.org_id),
            client_id=str(funnel.client_id),
            funnel=funnel,
            page=page,
        )
        metadata = build_public_page_metadata_for_context(
            session=session,
            org_id=str(funnel.org_id),
            funnel=funnel,
            page=page,
            puck_data=version.puck_data,
        )
        tracking = _resolve_public_meta_tracking(session=session, funnel=funnel)
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return {
            "productSlug": resolved_product_slug,
            "funnelId": str(funnel.id),
            "publicationId": publication_id,
            "pageId": str(pp.page_id),
            "slug": canonical_slug,
            "stage": _public_page_stage(
                slug=canonical_slug,
                template_id=page.template_id if page else None,
                page_name=page.name if page else None,
            ),
            "puckData": version.puck_data,
            "pageMap": public_page_map,
            "pageStageMap": page_stage_map,
            "pageTypeMap": page_type_map,
            "designSystemTokens": design_system_tokens,
            "metadata": metadata,
            "tracking": tracking,
            "nextPageId": str(page.next_page_id) if page and page.next_page_id else None,
        }

    # Preview mode: allow viewing pages with draft or approved versions even if the funnel hasn't been published yet.
    slug_candidates = _public_page_slug_candidates(slug)
    page = session.scalars(
        select(FunnelPage).where(
            FunnelPage.funnel_id == funnel.id, FunnelPage.slug.in_(slug_candidates)
        )
    ).first()
    if not page:
        redirect = None
        for candidate_slug in slug_candidates:
            redirect = public_repo.get_redirect(funnel_id=str(funnel.id), from_slug=candidate_slug)
            if redirect:
                break
        if redirect:
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
            return {
                "redirectToSlug": _canonical_public_page_slug(slug=redirect.to_slug)
                or redirect.to_slug
            }
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    versions_repo = FunnelPageVersionsRepository(session)
    draft = versions_repo.latest_for_page(
        page_id=str(page.id), status=FunnelPageVersionStatusEnum.draft
    )
    approved = versions_repo.latest_for_page(
        page_id=str(page.id), status=FunnelPageVersionStatusEnum.approved
    )
    version = draft or approved
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Page has no saved version"
        )

    page_map = _preview_page_map(session=session, funnel_id=str(funnel.id))
    preview_pages = session.scalars(
        select(FunnelPage)
        .where(FunnelPage.funnel_id == funnel.id)
        .order_by(FunnelPage.ordering.asc(), FunnelPage.created_at.asc())
    ).all()
    public_page_map = {
        page_id: (
            _canonical_public_page_slug(
                slug=item.slug,
                template_id=item.template_id,
                page_name=item.name,
            )
            or slug_value
        )
        for page_id, slug_value in page_map.items()
        for item in preview_pages
        if str(item.id) == page_id
    }
    page_stage_map = {
        str(item.id): _public_page_stage(
            slug=public_page_map.get(str(item.id), item.slug),
            template_id=item.template_id,
            page_name=item.name,
        )
        for item in preview_pages
    }
    # Build pageTypeMap for site experiences (maps page IDs to site page types)
    page_type_map = {
        str(item.id): _site_page_type(
            slug=public_page_map.get(str(item.id), item.slug),
            template_id=item.template_id,
            page_type=item.page_type,
        )
        for item in preview_pages
    }
    page_type_map = {k: v for k, v in page_type_map.items() if v is not None}
    canonical_slug = (
        _canonical_public_page_slug(
            slug=page.slug,
            template_id=page.template_id,
            page_name=page.name,
        )
        or page.slug
    )
    if normalize_route_token(slug) != normalize_route_token(canonical_slug):
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return {"redirectToSlug": canonical_slug}
    design_system_tokens = resolve_design_system_tokens(
        session=session,
        org_id=str(funnel.org_id),
        client_id=str(funnel.client_id),
        funnel=funnel,
        page=page,
    )
    metadata = build_public_page_metadata_for_context(
        session=session,
        org_id=str(funnel.org_id),
        funnel=funnel,
        page=page,
        puck_data=version.puck_data,
    )
    tracking = _resolve_public_meta_tracking(session=session, funnel=funnel)
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {
        "productSlug": resolved_product_slug,
        "funnelId": str(funnel.id),
        "publicationId": publication_id,
        "pageId": str(page.id),
        "slug": canonical_slug,
        "stage": _public_page_stage(
            slug=canonical_slug,
            template_id=page.template_id,
            page_name=page.name,
        ),
        "puckData": version.puck_data,
        "pageMap": public_page_map,
        "pageStageMap": page_stage_map,
        "pageTypeMap": page_type_map,
        "designSystemTokens": design_system_tokens,
        "metadata": metadata,
        "tracking": tracking,
        "nextPageId": str(page.next_page_id) if page.next_page_id else None,
    }


@router.get("/funnels/{product_slug}/{funnel_slug}/policy-pages/{page_key}")
def public_funnel_policy_page(
    product_slug: str,
    funnel_slug: str,
    page_key: str,
    website_url: str,
    response: Response,
    session: Session = Depends(get_session),
):
    target_kind, runtime_target, _product, _resolved_product_slug = _get_public_runtime_target_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )

    if page_key not in set(list_policy_page_keys()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy page not found")

    website_url_value = _require_absolute_public_website_url(website_url)

    if target_kind == "site":
        site = runtime_target
        org_id = site.org_id
        client_id = site.client_id
    else:
        funnel = runtime_target
        org_id = funnel.org_id
        client_id = funnel.client_id

    client = session.scalars(select(Client).where(Client.id == client_id)).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    workspace_name = clean_optional_text(client.name)
    if not workspace_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspace name is required to render policy pages.",
        )

    profile = session.scalars(
        select(ClientComplianceProfile).where(
            ClientComplianceProfile.org_id == org_id,
            ClientComplianceProfile.client_id == client_id,
        )
    ).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compliance profile not found for this site.",
        )

    template = get_policy_template(page_key=page_key)
    placeholder_values = _public_policy_placeholder_values(
        profile=profile,
        workspace_name=workspace_name,
        website_url=website_url_value,
    )

    try:
        markdown = render_policy_template_markdown(
            page_key=page_key,
            placeholder_values=placeholder_values,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {
        "pageKey": page_key,
        "title": template["title"],
        "markdown": markdown,
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Publication not found"
            )
        pages = public_repo.list_publication_pages(publication_id=str(funnel.active_publication_id))
        page_rows = {
            str(page.id): page
            for page in session.scalars(
                select(FunnelPage).where(FunnelPage.id.in_([item.page_id for item in pages]))
            ).all()
        }
        links = public_repo.list_publication_links(publication_id=str(funnel.active_publication_id))
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return {
            "productSlug": resolved_product_slug,
            "funnelSlug": str(funnel.route_slug),
            "funnelId": str(funnel.id),
            "publicationId": publication_id,
            "entryPageId": str(publication.entry_page_id),
            "pages": [
                {
                    "pageId": str(pp.page_id),
                    "slug": (
                        _canonical_public_page_slug(
                            slug=pp.slug_at_publish,
                            template_id=page_rows.get(str(pp.page_id)).template_id
                            if page_rows.get(str(pp.page_id))
                            else None,
                            page_name=page_rows.get(str(pp.page_id)).name
                            if page_rows.get(str(pp.page_id))
                            else None,
                        )
                        or pp.slug_at_publish
                    ),
                }
                for pp in pages
            ],
            "links": [jsonable_encoder(link) for link in links],
        }

    # Preview mode: only return pages that have at least one saved version (draft or approved) for the graph.
    page_map = _preview_page_map(session=session, funnel_id=str(funnel.id))
    preview_pages = session.scalars(
        select(FunnelPage)
        .where(FunnelPage.funnel_id == funnel.id)
        .order_by(FunnelPage.ordering.asc(), FunnelPage.created_at.asc())
    ).all()
    preview_page_rows = {str(page.id): page for page in preview_pages}
    if not funnel.entry_page_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry page not found")
    if str(funnel.entry_page_id) not in page_map:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entry page has no saved version"
        )

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {
        "productSlug": resolved_product_slug,
        "funnelSlug": str(funnel.route_slug),
        "funnelId": str(funnel.id),
        "publicationId": publication_id,
        "entryPageId": str(funnel.entry_page_id),
        "pages": [
            {
                "pageId": page_id,
                "slug": (
                    _canonical_public_page_slug(
                        slug=preview_page_rows[page_id].slug,
                        template_id=preview_page_rows[page_id].template_id,
                        page_name=preview_page_rows[page_id].name,
                    )
                    or slug_value
                ),
            }
            for page_id, slug_value in page_map.items()
            if page_id in preview_page_rows
        ],
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
    checkout_ready_variants = [
        variant for variant in variants if _is_checkout_ready_variant(variant)
    ]
    if not checkout_ready_variants:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product variants are not configured for checkout for this funnel product.",
        )
    serialized_variants: list[dict] = []
    for variant in checkout_ready_variants:
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
        candidates_query = select(ProductVariant).where(
            ProductVariant.product_id == funnel.product_id
        )
        if funnel.selected_offer_id:
            candidates_query = candidates_query.where(
                ProductVariant.offer_id == funnel.selected_offer_id
            )
        candidates = session.scalars(candidates_query).all()
        checkout_ready_candidates = [
            item for item in candidates if _is_checkout_ready_variant(item)
        ]
        if not checkout_ready_candidates:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No checkout-ready variants are configured for this funnel product.",
            )
        matches = [
            item for item in checkout_ready_candidates if item.option_values == payload.selection
        ]
        if len(matches) != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selection does not resolve to a single variant.",
            )
        variant = matches[0]

    if not variant:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Variant resolution failed."
        )

    normalized_provider = _normalize_variant_provider(variant.provider)
    if not normalized_provider:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Variant provider is required for checkout.",
        )
    external_price_id = str(variant.external_price_id or "").strip() or None
    metadata = {
        "funnel_slug": _metadata_value(payload.funnelSlug, "funnelSlug"),
        "funnel_id": _metadata_value(str(funnel.id), "funnelId"),
        "offer_id": _metadata_value(str(funnel.selected_offer_id), "offerId")
        if funnel.selected_offer_id
        else None,
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
    if normalized_provider == "stripe":
        if not external_price_id:
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
            line_items=[{"price": external_price_id, "quantity": payload.quantity}],
            metadata=metadata,
        )
        _record_checkout_started_event(
            session=session,
            request=request,
            funnel=funnel,
            page_id=payload.pageId,
            visitor_id=payload.visitorId,
            session_id=payload.sessionId,
            utm=payload.utm,
            provider=normalized_provider,
            checkout_session_id=str(checkout_session.id),
            variant=variant,
            quantity=payload.quantity,
        )
        return {"checkoutUrl": checkout_session.url, "sessionId": checkout_session.id}

    if normalized_provider == "shopify":
        if not external_price_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Shopify variant GID is missing for this variant.",
            )
        checkout = create_shopify_checkout(
            client_id=str(funnel.client_id),
            variant_gid=external_price_id,
            quantity=payload.quantity,
            metadata=metadata,
        )
        _record_checkout_started_event(
            session=session,
            request=request,
            funnel=funnel,
            page_id=payload.pageId,
            visitor_id=payload.visitorId,
            session_id=payload.sessionId,
            utm=payload.utm,
            provider=normalized_provider,
            checkout_session_id=str(checkout["cartId"]),
            variant=variant,
            quantity=payload.quantity,
        )
        return {"checkoutUrl": checkout["checkoutUrl"], "sessionId": checkout["cartId"]}

    if normalized_provider == "medusa":
        if not external_price_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Medusa external variant ID is missing for this variant.",
            )
        checkout = create_managed_checkout(
            provider=normalized_provider,
            client_id=str(funnel.client_id),
            external_variant_id=external_price_id,
            quantity=payload.quantity,
            metadata=metadata,
        )
        _record_checkout_started_event(
            session=session,
            request=request,
            funnel=funnel,
            page_id=payload.pageId,
            visitor_id=payload.visitorId,
            session_id=payload.sessionId,
            utm=payload.utm,
            provider=normalized_provider,
            checkout_session_id=str(checkout["cartId"]),
            variant=variant,
            quantity=payload.quantity,
        )
        return {"checkoutUrl": checkout["checkoutUrl"], "sessionId": checkout["cartId"]}

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Unsupported checkout provider.",
    )


# =============================================================================
# Site Commerce Endpoints
# =============================================================================


def _get_medusa_store_config_for_funnel(
    *,
    session: Session,
    funnel: Funnel,
) -> MedusaStoreConfig:
    """Get Medusa Store config for a funnel's workspace."""
    config = get_medusa_store_config(
        session=session,
        org_id=str(funnel.org_id),
        client_id=str(funnel.client_id),
    )
    if not config:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Medusa Store API is not configured for this workspace. A publishable key is required.",
        )
    return config


@router.get("/funnels/{product_slug}/{funnel_slug}/site/commerce")
def public_site_commerce(
    product_slug: str,
    funnel_slug: str,
    response: Response,
    session: Session = Depends(get_session),
    product_id: str | None = None,
    product_handle: str | None = None,
    collection_id: str | None = None,
    category_id: str | None = None,
    category_handle: str | None = None,
    category: str | None = None,  # Alias for category_handle
    cart_id: str | None = None,
    region_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """Get rich commerce data for site pages.

    This endpoint returns catalog data, regions, and optionally cart state
    for site experiences backed by Medusa Store API.

    Query params:
    - product_id: Fetch a specific product by Medusa ID
    - product_handle: Fetch a specific product by handle
    - collection_id: Filter products by collection
    - category_id: Filter products by category ID
    - category_handle: Filter products by category handle (resolved to category_id)
    - cart_id: Include cart state if provided
    - region_id: Include payment providers for this region
    - limit/offset: Pagination for product listing
    """
    funnel, product, resolved_product_slug = _get_funnel_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )

    # Check if this is a site experience with Medusa
    if not funnel.experience_kind or funnel.experience_kind != "site":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site commerce endpoint is only available for site experiences.",
        )

    if not funnel.commerce_provider or funnel.commerce_provider != "medusa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site commerce endpoint requires Medusa commerce provider.",
        )

    config = _get_medusa_store_config_for_funnel(session=session, funnel=funnel)

    # Support both category_handle and category (alias) parameters
    # Use category if category_handle is not provided
    effective_category_handle = category_handle or category

    # Resolve category_handle to category_id if provided
    resolved_category_id = category_id
    if effective_category_handle and not category_id:
        try:
            categories = medusa_list_categories(config=config)
            for cat in categories:
                if cat.get("handle") == effective_category_handle:
                    resolved_category_id = cat.get("id")
                    break
        except HTTPException:
            pass  # Continue without category filter if lookup fails

    result: dict[str, Any] = {
        "productSlug": resolved_product_slug,
        "funnelSlug": str(funnel.route_slug),
        "funnelId": str(funnel.id),
        "siteFamily": funnel.site_family,
        "commerceProvider": funnel.commerce_provider,
        "storeName": funnel.name,  # Use funnel name as store name for branding
    }

    # Track errors for critical fetches
    errors: list[str] = []

    # Fetch regions - critical for cart operations
    try:
        regions = medusa_list_regions(config=config)
        result["regions"] = regions
    except HTTPException as e:
        result["regions"] = []
        errors.append(f"Failed to fetch regions: {e.detail if hasattr(e, 'detail') else str(e)}")

    # If no region_id was explicitly provided, use the first region for price calculation
    # This ensures prices are returned in the product response from Medusa Store API
    effective_region_id = region_id
    regions_list = result.get("regions", [])
    if not effective_region_id and regions_list:
        first_region = regions_list[0]
        effective_region_id = first_region.get("id") if isinstance(first_region, dict) else None

    # Fetch collections - non-critical
    try:
        collections = medusa_list_collections(config=config)
        result["collections"] = collections
    except HTTPException:
        result["collections"] = []

    # Fetch products - critical for catalog pages
    # For site experiences, we scope products to the workspace's mapped mOS products
    # instead of returning the entire Medusa catalog
    try:
        # Get the client_id from the funnel to query workspace products
        client_id = str(funnel.client_id) if funnel.client_id else None

        if client_id:
            # Query local mOS products with medusa_product_id for this workspace
            workspace_products = (
                session.execute(
                    select(Product)
                    .where(
                        Product.client_id == UUID(client_id),
                        Product.medusa_product_id.isnot(None),
                    )
                    .order_by(Product.created_at.asc(), Product.id.asc())
                )
                .scalars()
                .all()
            )

            validation_products = [
                product
                for product in workspace_products
                if _is_validation_workspace_product(product)
            ]
            if validation_products:
                errors.append(
                    "Excluded validation-only workspace products from the public storefront: "
                    + ", ".join(product.title for product in validation_products)
                )
            workspace_products = [
                product
                for product in workspace_products
                if not _is_validation_workspace_product(product)
            ]

            workspace_products, duplicate_product_errors = _dedupe_workspace_products_by_medusa_id(
                workspace_products
            )
            errors.extend(duplicate_product_errors)

            # Extract Medusa product IDs
            medusa_product_ids = [
                p.medusa_product_id for p in workspace_products if p.medusa_product_id
            ]

            # Build a mapping from product_type to product for filtering by derived category
            # The derived category handle is product_type.lower().replace(" ", "-")
            product_type_map: dict[str, Product] = {}
            for p in workspace_products:
                if p.product_type:
                    product_type_map[p.product_type] = p

            # If effective_category_handle is provided, filter to only products with matching product_type
            # This handles the derived category filtering for workspace-scoped sites
            filtered_product_ids = medusa_product_ids
            if effective_category_handle:
                # Convert category_handle back to product_type for matching
                # handle format: "herbal-teas" -> product_type format: "Herbal Teas"
                target_product_type = effective_category_handle.replace("-", " ").title()

                # Find products with matching product_type
                matched_products = [
                    p
                    for p in workspace_products
                    if p.product_type and p.product_type.lower() == target_product_type.lower()
                ]
                filtered_product_ids = [
                    p.medusa_product_id for p in matched_products if p.medusa_product_id
                ]

                # If no products match the category, fall back to all products
                # This ensures the category page isn't blank when product_type isn't set
                if not filtered_product_ids:
                    filtered_product_ids = medusa_product_ids

            if filtered_product_ids:
                # Fetch only the workspace's mapped products from Medusa
                # Pass effective_region_id to get region-specific pricing in the response
                products = medusa_get_products_by_ids(
                    config=config,
                    product_ids=filtered_product_ids,
                    region_id=effective_region_id,
                )

                # Build a mapping from medusa_product_id to local mOS product + variants
                # This allows us to enrich with local pricing when Medusa prices are absent
                mos_product_by_medusa_id: dict[str, Product] = {}
                mos_variants_by_product_id: dict[str, list[ProductVariant]] = {}
                for p in workspace_products:
                    if p.medusa_product_id:
                        mos_product_by_medusa_id[p.medusa_product_id] = p
                        # Fetch local variants for this product
                        local_variants = (
                            session.execute(
                                select(ProductVariant).where(ProductVariant.product_id == p.id)
                            )
                            .scalars()
                            .all()
                        )
                        if local_variants:
                            mos_variants_by_product_id[p.id] = list(local_variants)

                # Enrich products with local mOS variant prices if Medusa prices are absent
                # This ensures accurate pricing when Medusa Store payload doesn't include usable prices
                for medusa_product in products:
                    medusa_product_id = medusa_product.get("id")
                    if not medusa_product_id:
                        continue

                    # Get the local mOS product for this Medusa product
                    mos_product = mos_product_by_medusa_id.get(medusa_product_id)
                    if not mos_product:
                        continue

                    # Get local variants for this product
                    local_variants = mos_variants_by_product_id.get(mos_product.id, [])
                    if not local_variants:
                        continue

                    # Get variants from Medusa response
                    medusa_variants = medusa_product.get("variants", [])
                    if not isinstance(medusa_variants, list):
                        medusa_variants = []

                    # If Medusa has no variants or no prices, add local variant prices
                    # But preserve Medusa variant IDs for cart operations (use external_price_id)
                    if not medusa_variants or not any(
                        v.get("prices")
                        and len(v.get("prices", [])) > 0
                        and v["prices"][0].get("amount")
                        for v in medusa_variants
                    ):
                        # Build mapping from external_price_id (Medusa variant ID) to local variant
                        # This ensures we use the correct Medusa variant ID for add-to-cart
                        local_var_by_external_id: dict[str, ProductVariant] = {}
                        for local_var in local_variants:
                            ext_id = str(local_var.external_price_id or "").strip()
                            if ext_id:
                                local_var_by_external_id[ext_id] = local_var

                        # Create enriched variants using Medusa variant IDs (external_price_id)
                        enriched_variants = []
                        if medusa_variants:
                            # Medusa has variants - match by Medusa variant ID
                            for medusa_var in medusa_variants:
                                medusa_var_id = medusa_var.get("id")
                                if not medusa_var_id:
                                    continue

                                # Get local variant for this Medusa variant
                                local_var = local_var_by_external_id.get(medusa_var_id)
                                if not local_var:
                                    continue

                                # Use Medusa variant ID for cart operations, add local price
                                enriched_variants.append(
                                    {
                                        "id": medusa_var_id,  # Use Medusa variant ID, not local ID
                                        "title": local_var.title,
                                        "prices": [
                                            {
                                                "amount": local_var.price,
                                                "currency_code": local_var.currency.upper()
                                                if local_var.currency
                                                else "USD",
                                            }
                                        ],
                                    }
                                )
                        else:
                            # No Medusa variants - create from local variants using external_price_id
                            for ext_id, local_var in local_var_by_external_id.items():
                                enriched_variants.append(
                                    {
                                        "id": ext_id,  # Use Medusa variant ID from external_price_id
                                        "title": local_var.title,
                                        "prices": [
                                            {
                                                "amount": local_var.price,
                                                "currency_code": local_var.currency.upper()
                                                if local_var.currency
                                                else "USD",
                                            }
                                        ],
                                    }
                                )

                        if enriched_variants:
                            medusa_product["variants"] = enriched_variants

                result["products"] = products
                result["productsCount"] = len(products)

                # Derive categories from workspace products' types
                # This gives a workspace-scoped category view instead of global Medusa categories
                product_types = set()
                for p in workspace_products:
                    if p.product_type:
                        product_types.add(p.product_type)

                # Always use derived categories for workspace-scoped sites
                # This ensures navigation shows Honest Herbalist categories, not Medusa demo categories
                if product_types:
                    derived_categories = [
                        {
                            "id": pt,
                            "name": pt.replace("_", " ").title(),
                            "handle": pt.lower().replace(" ", "-"),
                        }
                        for pt in sorted(product_types)
                    ]
                    result["categories"] = derived_categories

                    # If effective_category_handle is provided, include currentCategory for coherent rendering
                    if effective_category_handle:
                        # Find matching category from derived categories
                        target_handle = effective_category_handle.lower()
                        found_category = None
                        for cat in derived_categories:
                            if cat.get("handle") == target_handle:
                                found_category = cat
                                break
                        # Always set currentCategory when category_handle is provided
                        # If not found in derived categories, create a representation of the selected category
                        if found_category:
                            result["currentCategory"] = found_category
                        else:
                            result["currentCategory"] = {
                                "id": effective_category_handle,
                                "name": effective_category_handle.replace("-", " ").title(),
                                "handle": effective_category_handle.lower(),
                            }
                else:
                    # No product types - derive at least a default "All Products" category
                    # This ensures the category page isn't completely blank
                    result["categories"] = [
                        {
                            "id": "all",
                            "name": "All Products",
                            "handle": "all",
                        }
                    ]
                    # If a category_handle was provided but no categories matched,
                    # set currentCategory to represent the selected category for coherent rendering
                    if effective_category_handle:
                        result["currentCategory"] = {
                            "id": effective_category_handle,
                            "name": effective_category_handle.replace("-", " ").title(),
                            "handle": effective_category_handle.lower(),
                        }
            else:
                # No mapped products for this workspace - return empty catalog
                # This is the correct behavior for workspace-scoped sites.
                # We do NOT fall back to the global Medusa catalog as that would
                # reintroduce sample/dummy products which are not wanted.
                result["products"] = []
                result["productsCount"] = 0
                result["categories"] = []
        else:
            # No client_id on funnel - this is a configuration error
            # Return empty catalog rather than leaking global Medusa products
            result["products"] = []
            result["productsCount"] = 0
            result["categories"] = []
    except HTTPException as e:
        result["products"] = []
        result["productsCount"] = 0
        errors.append(f"Failed to fetch products: {e.detail if hasattr(e, 'detail') else str(e)}")

    # Fetch current product if specified, otherwise fall back to the site's bound product.
    # Priority: 1) exact product_id match, 2) handle match in products list, 3) fallback to API, 4) use first product
    if product_id:
        try:
            current_product = medusa_get_product(
                config=config,
                product_id=product_id,
                region_id=effective_region_id,
            )
            result["currentProduct"] = current_product
        except HTTPException:
            result["currentProduct"] = None
    elif product_handle:
        # First try to find in the already-fetched products list for efficiency
        found_in_list = None
        product_handle_lower = product_handle.lower()
        for p in result.get("products", []):
            p_handle = (p.get("handle") or "").lower()
            if p_handle == product_handle_lower:
                found_in_list = p
                break
            # Also check if the handle is contained within the product handle (handles may differ slightly)
            if product_handle_lower in p_handle:
                found_in_list = p
                break

        if found_in_list:
            result["currentProduct"] = found_in_list
        else:
            # Fall back to API call if not found in list
            try:
                current_product = medusa_get_product_by_handle(
                    config=config,
                    handle=product_handle,
                    region_id=effective_region_id,
                )
                result["currentProduct"] = current_product
            except HTTPException:
                result["currentProduct"] = None
    elif product.medusa_product_id:
        try:
            current_product = medusa_get_product(
                config=config,
                product_id=product.medusa_product_id,
                region_id=effective_region_id,
            )
            result["currentProduct"] = current_product
        except HTTPException:
            result["currentProduct"] = None
    elif result["products"]:
        result["currentProduct"] = result["products"][0]

    # Fetch cart if cart_id provided
    if cart_id:
        try:
            cart = medusa_get_cart(config=config, cart_id=cart_id)
            result["cart"] = cart
        except HTTPException:
            result["cart"] = None

    # Fetch payment providers if region_id provided
    if effective_region_id:
        medusa_config = get_client_medusa_config(
            session=session,
            org_id=str(funnel.org_id),
            client_id=str(funnel.client_id),
        )
        if not medusa_config:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Medusa configuration not found for this workspace.",
            )

        allowed_provider_ids = list(medusa_config.allowed_payment_provider_ids or [])
        default_payment_provider_id = medusa_config.default_payment_provider_id

        payment_providers = medusa_list_payment_providers(
            config=config,
            region_id=effective_region_id,
        )
        payment_providers = filter_payment_providers_by_allowlist(
            providers=payment_providers,
            allowed_provider_ids=allowed_provider_ids,
        )
        resolved_default_id = resolve_default_payment_provider_id(
            allowed_provider_ids=allowed_provider_ids,
            default_payment_provider_id=default_payment_provider_id,
            available_providers=payment_providers,
        )
        result["paymentProviders"] = payment_providers
        result["defaultPaymentProviderId"] = resolved_default_id

    # Include any errors encountered during critical fetches
    if errors:
        result["errors"] = errors

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return result


@router.get("/funnels/{product_slug}/{funnel_slug}/site/cart")
def public_site_cart_get(
    product_slug: str,
    funnel_slug: str,
    cart_id: str,
    response: Response,
    session: Session = Depends(get_session),
):
    """Get a cart by ID from Medusa Store API."""
    funnel, _product, _resolved_product_slug = _get_funnel_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )

    if not funnel.experience_kind or funnel.experience_kind != "site":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site cart endpoint is only available for site experiences.",
        )

    if not funnel.commerce_provider or funnel.commerce_provider != "medusa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site cart endpoint requires Medusa commerce provider.",
        )

    config = _get_medusa_store_config_for_funnel(session=session, funnel=funnel)

    cart = medusa_get_cart(config=config, cart_id=cart_id)

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {"cart": cart}


@router.post("/funnels/{product_slug}/{funnel_slug}/site/cart")
def public_site_cart_create(
    product_slug: str,
    funnel_slug: str,
    payload: SiteCommerceCartCreateRequest,
    response: Response,
    session: Session = Depends(get_session),
):
    """Create a new cart in Medusa Store API."""
    funnel, _product, _resolved_product_slug = _get_funnel_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )

    if not funnel.experience_kind or funnel.experience_kind != "site":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site cart endpoint is only available for site experiences.",
        )

    if not funnel.commerce_provider or funnel.commerce_provider != "medusa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site cart endpoint requires Medusa commerce provider.",
        )

    config = _get_medusa_store_config_for_funnel(session=session, funnel=funnel)

    cart = medusa_create_cart(
        config=config,
        region_id=payload.region_id,
        country_code=payload.country_code,
        email=payload.email,
        shipping_address=payload.shipping_address,
        items=payload.items,
    )

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {"cart": cart}


@router.post("/funnels/{product_slug}/{funnel_slug}/site/cart/{cart_id}")
def public_site_cart_update(
    product_slug: str,
    funnel_slug: str,
    cart_id: str,
    payload: SiteCommerceCartUpdateRequest,
    response: Response,
    session: Session = Depends(get_session),
):
    """Update a cart in Medusa Store API."""
    funnel, _product, _resolved_product_slug = _get_funnel_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )

    if not funnel.experience_kind or funnel.experience_kind != "site":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site cart endpoint is only available for site experiences.",
        )

    if not funnel.commerce_provider or funnel.commerce_provider != "medusa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site cart endpoint requires Medusa commerce provider.",
        )

    config = _get_medusa_store_config_for_funnel(session=session, funnel=funnel)

    cart = medusa_update_cart(
        config=config,
        cart_id=cart_id,
        email=payload.email,
        shipping_address=payload.shipping_address,
        billing_address=payload.billing_address,
    )

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {"cart": cart}


@router.post("/funnels/{product_slug}/{funnel_slug}/site/cart/{cart_id}/items")
def public_site_cart_add_item(
    product_slug: str,
    funnel_slug: str,
    cart_id: str,
    payload: SiteCommerceLineItemAddRequest,
    response: Response,
    session: Session = Depends(get_session),
):
    """Add a line item to a cart in Medusa Store API."""
    funnel, _product, _resolved_product_slug = _get_funnel_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )

    if not funnel.experience_kind or funnel.experience_kind != "site":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site cart endpoint is only available for site experiences.",
        )

    if not funnel.commerce_provider or funnel.commerce_provider != "medusa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site cart endpoint requires Medusa commerce provider.",
        )

    if payload.quantity < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quantity must be at least 1.",
        )

    config = _get_medusa_store_config_for_funnel(session=session, funnel=funnel)

    cart = medusa_add_cart_line_item(
        config=config,
        cart_id=cart_id,
        variant_id=payload.variant_id,
        quantity=payload.quantity,
    )

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {"cart": cart}


@router.post("/funnels/{product_slug}/{funnel_slug}/site/cart/{cart_id}/items/{line_id}")
def public_site_cart_update_item(
    product_slug: str,
    funnel_slug: str,
    cart_id: str,
    line_id: str,
    payload: SiteCommerceLineItemUpdateRequest,
    response: Response,
    session: Session = Depends(get_session),
):
    """Update a line item quantity in a cart."""
    funnel, _product, _resolved_product_slug = _get_funnel_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )

    if not funnel.experience_kind or funnel.experience_kind != "site":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site cart endpoint is only available for site experiences.",
        )

    if not funnel.commerce_provider or funnel.commerce_provider != "medusa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site cart endpoint requires Medusa commerce provider.",
        )

    if payload.quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quantity must be non-negative.",
        )

    config = _get_medusa_store_config_for_funnel(session=session, funnel=funnel)

    if payload.quantity == 0:
        medusa_delete_cart_line_item(
            config=config,
            cart_id=cart_id,
            line_id=line_id,
        )
        cart = medusa_get_cart(config=config, cart_id=cart_id)
    else:
        cart = medusa_update_cart_line_item(
            config=config,
            cart_id=cart_id,
            line_id=line_id,
            quantity=payload.quantity,
        )

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {"cart": cart}


@router.delete("/funnels/{product_slug}/{funnel_slug}/site/cart/{cart_id}/items/{line_id}")
def public_site_cart_delete_item(
    product_slug: str,
    funnel_slug: str,
    cart_id: str,
    line_id: str,
    response: Response,
    session: Session = Depends(get_session),
):
    """Delete a line item from a cart."""
    funnel, _product, _resolved_product_slug = _get_funnel_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )

    if not funnel.experience_kind or funnel.experience_kind != "site":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site cart endpoint is only available for site experiences.",
        )

    if not funnel.commerce_provider or funnel.commerce_provider != "medusa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site cart endpoint requires Medusa commerce provider.",
        )

    config = _get_medusa_store_config_for_funnel(session=session, funnel=funnel)

    medusa_delete_cart_line_item(
        config=config,
        cart_id=cart_id,
        line_id=line_id,
    )

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {"deleted": True}


@router.get("/funnels/{product_slug}/{funnel_slug}/site/shipping-options")
def public_site_shipping_options(
    product_slug: str,
    funnel_slug: str,
    cart_id: str,
    response: Response,
    session: Session = Depends(get_session),
):
    """Get shipping options for a cart from Medusa Store API."""
    funnel, _product, _resolved_product_slug = _get_funnel_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )

    if not funnel.experience_kind or funnel.experience_kind != "site":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site shipping endpoint is only available for site experiences.",
        )

    if not funnel.commerce_provider or funnel.commerce_provider != "medusa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site shipping endpoint requires Medusa commerce provider.",
        )

    config = _get_medusa_store_config_for_funnel(session=session, funnel=funnel)

    shipping_options = medusa_list_shipping_options(
        config=config,
        cart_id=cart_id,
    )

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {"shipping_options": shipping_options}


@router.post("/funnels/{product_slug}/{funnel_slug}/site/shipping-methods")
def public_site_add_shipping_method(
    product_slug: str,
    funnel_slug: str,
    payload: SiteCommerceShippingMethodRequest,
    response: Response,
    session: Session = Depends(get_session),
):
    """Add a shipping method to a cart."""
    funnel, _product, _resolved_product_slug = _get_funnel_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )

    if not funnel.experience_kind or funnel.experience_kind != "site":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site shipping endpoint is only available for site experiences.",
        )

    if not funnel.commerce_provider or funnel.commerce_provider != "medusa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site shipping endpoint requires Medusa commerce provider.",
        )

    config = _get_medusa_store_config_for_funnel(session=session, funnel=funnel)

    cart = medusa_add_shipping_method(
        config=config,
        cart_id=payload.cart_id,
        option_id=payload.option_id,
    )

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {"cart": cart}


@router.get("/funnels/{product_slug}/{funnel_slug}/site/payment-providers")
def public_site_payment_providers(
    product_slug: str,
    funnel_slug: str,
    region_id: str,
    response: Response,
    session: Session = Depends(get_session),
):
    """Get payment providers for a region from Medusa Store API."""
    funnel, _product, _resolved_product_slug = _get_funnel_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )

    if not funnel.experience_kind or funnel.experience_kind != "site":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site payment endpoint is only available for site experiences.",
        )

    if not funnel.commerce_provider or funnel.commerce_provider != "medusa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site payment endpoint requires Medusa commerce provider.",
        )

    medusa_config = get_client_medusa_config(
        session=session,
        org_id=str(funnel.org_id),
        client_id=str(funnel.client_id),
    )
    if not medusa_config:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Medusa configuration not found for this workspace.",
        )

    allowed_provider_ids = list(medusa_config.allowed_payment_provider_ids or [])
    default_payment_provider_id = medusa_config.default_payment_provider_id

    config = _get_medusa_store_config_for_funnel(session=session, funnel=funnel)

    payment_providers = medusa_list_payment_providers(
        config=config,
        region_id=region_id,
    )

    payment_providers = filter_payment_providers_by_allowlist(
        providers=payment_providers,
        allowed_provider_ids=allowed_provider_ids,
    )
    resolved_default = resolve_default_payment_provider_id(
        allowed_provider_ids=allowed_provider_ids,
        default_payment_provider_id=default_payment_provider_id,
        available_providers=payment_providers,
    )

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {
        "payment_providers": payment_providers,
        "default_payment_provider_id": resolved_default,
    }


@router.post("/funnels/{product_slug}/{funnel_slug}/site/checkout/session")
def public_site_checkout_session(
    product_slug: str,
    funnel_slug: str,
    cart_id: str,
    provider_id: str,
    response: Response,
    session: Session = Depends(get_session),
):
    """Initialize a payment session for checkout.

    This creates a payment collection and initializes a payment session
    with the specified provider.
    """
    funnel, _product, _resolved_product_slug = _get_funnel_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )

    if not funnel.experience_kind or funnel.experience_kind != "site":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site checkout endpoint is only available for site experiences.",
        )

    if not funnel.commerce_provider or funnel.commerce_provider != "medusa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site checkout endpoint requires Medusa commerce provider.",
        )

    medusa_config = get_client_medusa_config(
        session=session,
        org_id=str(funnel.org_id),
        client_id=str(funnel.client_id),
    )
    if not medusa_config:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Medusa configuration not found for this workspace.",
        )

    allowed_provider_ids = list(medusa_config.allowed_payment_provider_ids or [])

    validate_provider_id_against_allowlist(
        provider_id=provider_id,
        allowed_provider_ids=allowed_provider_ids,
    )

    config = _get_medusa_store_config_for_funnel(session=session, funnel=funnel)

    # Create payment collection
    payment_collection = medusa_create_payment_collection(
        config=config,
        cart_id=cart_id,
    )

    # Initialize payment session
    payment_collection = medusa_initialize_payment_session(
        config=config,
        payment_collection_id=payment_collection["id"],
        provider_id=provider_id,
    )

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {"payment_collection": payment_collection}


@router.post("/funnels/{product_slug}/{funnel_slug}/site/checkout/complete")
def public_site_checkout_complete(
    product_slug: str,
    funnel_slug: str,
    cart_id: str,
    response: Response,
    session: Session = Depends(get_session),
):
    """Complete a cart and create an order.

    This finalizes the checkout process. The cart must have:
    - Email set
    - Shipping address set
    - Shipping method selected
    - Payment session initialized

    Returns the order on success, or an error if the cart is not ready.
    """
    funnel, _product, _resolved_product_slug = _get_funnel_or_404(
        session=session,
        product_slug=product_slug,
        funnel_slug=funnel_slug,
    )

    if not funnel.experience_kind or funnel.experience_kind != "site":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site checkout endpoint is only available for site experiences.",
        )

    if not funnel.commerce_provider or funnel.commerce_provider != "medusa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site checkout endpoint requires Medusa commerce provider.",
        )

    config = _get_medusa_store_config_for_funnel(session=session, funnel=funnel)

    order = medusa_complete_cart(
        config=config,
        cart_id=cart_id,
    )

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {
        "type": "order",
        "order": order,
    }


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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Batch must share publicationId"
        )
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
        site = session.scalars(
            select(Site).where(
                (Site.active_site_publication_id == publication_uuid) | (Site.id == publication_uuid)
            )
        ).first()
        if site:
            return {"ingested": 0}
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    headers = {"Cache-Control": "public, max-age=31536000, immutable"}
    return BinaryResponse(
        content=data,
        media_type=asset.content_type or content_type or "application/octet-stream",
        headers=headers,
    )
