"""Service for managing site templates.

This service handles:
- Listing and retrieving site templates
- Seeding built-in site blueprints as system templates
- Instantiating templates into actual sites
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    DesignSystem,
    Site,
    SitePage,
    SitePageVersion,
    SiteLink,
    SiteImport,
    SiteTemplate,
    SiteTemplatePage,
    SiteTemplateLink,
    SiteTemplateFunnel,
    SiteTemplateFunnelStep,
    SiteFunnel,
    SiteFunnelStep,
)
from app.db.repositories.sites_runtime import SitesRuntimeRepository
from app.services.design_systems import resolve_design_system_tokens
from app.services.funnel_templates import apply_template_assets, get_funnel_template
from app.services.site_blueprints import (
    SiteFamilyDescriptor,
    SitePageBlueprint,
    list_site_families,
    get_site_family,
    validate_theme_requirement,
)


class SiteTemplateError(Exception):
    """Error during site template operations."""

    pass


_SOURCE_SITE_NOTE_PREFIX = "source_site_id:"
_SOURCE_SITE_PAGE_NOTE_PREFIX = "source_site_page_id:"
_TEMPLATE_MODE_NOTE_PREFIX = "template_mode:"
_TEMPLATE_PAGE_MODE_NOTE_PREFIX = "template_page_mode:"
_PAGE_TYPE_PLACEHOLDERS = {
    "home": "__PAGE_HOME__",
    "category": "__PAGE_CATEGORY__",
    "product_detail": "__PAGE_PRODUCT_DETAIL__",
    "cart": "__PAGE_CART__",
    "checkout": "__PAGE_CHECKOUT__",
}
_MEDUSA_ONE_PRODUCT_TEMPLATE_MODE = "medusa_one_product_store"
_MEDUSA_ONE_PRODUCT_ENTRY_PAGE_MODE = "medusa_one_product_entry_home"
_MEDUSA_ONE_PRODUCT_AUXILIARY_PAGES: tuple[SitePageBlueprint, ...] = (
    SitePageBlueprint(
        page_type="cart",
        template_id="medusa-b2c-cart",
        name="Cart",
        slug="cart",
        description="Cart page used by the storefront checkout flow.",
        ordering=0,
    ),
    SitePageBlueprint(
        page_type="checkout",
        template_id="medusa-b2c-checkout",
        name="Checkout",
        slug="checkout",
        description="Checkout flow with shipping, payment, and order confirmation.",
        ordering=1,
    ),
    SitePageBlueprint(
        page_type="privacy_policy",
        template_id="medusa-b2c-policy-privacy",
        name="Privacy Policy",
        slug="privacy-policy",
        description="Store privacy policy rendered from the workspace compliance profile.",
        ordering=2,
    ),
    SitePageBlueprint(
        page_type="terms_of_service",
        template_id="medusa-b2c-policy-terms",
        name="Terms of Service",
        slug="terms-of-service",
        description="Terms of service rendered from the workspace compliance profile.",
        ordering=3,
    ),
    SitePageBlueprint(
        page_type="returns_refunds_policy",
        template_id="medusa-b2c-policy-returns",
        name="Refund Policy",
        slug="refund-policy",
        description="Returns and refunds policy rendered from the workspace compliance profile.",
        ordering=4,
    ),
    SitePageBlueprint(
        page_type="shipping_policy",
        template_id="medusa-b2c-policy-shipping",
        name="Shipping Policy",
        slug="shipping-policy",
        description="Shipping policy rendered from the workspace compliance profile.",
        ordering=5,
    ),
    SitePageBlueprint(
        page_type="contact_support",
        template_id="medusa-b2c-policy-contact",
        name="Contact Support",
        slug="contact-support",
        description="Support contact page rendered from the workspace compliance profile.",
        ordering=6,
    ),
    SitePageBlueprint(
        page_type="account_dashboard",
        template_id="medusa-b2c-account-dashboard",
        name="Account Dashboard",
        slug="account",
        description="Customer account overview with login and register.",
        ordering=7,
    ),
    SitePageBlueprint(
        page_type="account_profile",
        template_id="medusa-b2c-account-profile",
        name="Account Profile",
        slug="account/profile",
        description="Customer profile management.",
        ordering=8,
    ),
    SitePageBlueprint(
        page_type="account_addresses",
        template_id="medusa-b2c-account-addresses",
        name="Account Addresses",
        slug="account/addresses",
        description="Customer address book management.",
        ordering=9,
    ),
    SitePageBlueprint(
        page_type="account_orders",
        template_id="medusa-b2c-account-orders",
        name="Account Orders",
        slug="account/orders",
        description="Customer orders list.",
        ordering=10,
    ),
    SitePageBlueprint(
        page_type="account_order_detail",
        template_id="medusa-b2c-account-order-detail",
        name="Order Detail",
        slug="account/orders/details",
        description="Single order detail view.",
        ordering=11,
    ),
    SitePageBlueprint(
        page_type="order_confirmed",
        template_id="medusa-b2c-order-confirmed",
        name="Order Confirmed",
        slug="order/confirmed",
        description="Order confirmation page after successful checkout.",
        ordering=12,
    ),
    SitePageBlueprint(
        page_type="order_transfer",
        template_id="medusa-b2c-order-transfer",
        name="Order Transfer",
        slug="order/transfer",
        description="Order transfer landing page for gift and transfer flows.",
        ordering=13,
    ),
    SitePageBlueprint(
        page_type="order_transfer_accept",
        template_id="medusa-b2c-order-transfer-accept",
        name="Accept Transfer",
        slug="order/transfer/accept",
        description="Accept order transfer action page.",
        ordering=14,
    ),
    SitePageBlueprint(
        page_type="order_transfer_decline",
        template_id="medusa-b2c-order-transfer-decline",
        name="Decline Transfer",
        slug="order/transfer/decline",
        description="Decline order transfer action page.",
        ordering=15,
    ),
)


def _note_with_value(prefix: str, value: str) -> str:
    return f"{prefix}{value}"


def _read_note_value(notes: list[str] | None, prefix: str) -> str | None:
    for note in notes or []:
        if isinstance(note, str) and note.startswith(prefix):
            value = note[len(prefix) :].strip()
            if value:
                return value
    return None


def _resolve_template_family_for_site(session: Session, *, site: Site) -> str:
    if site.site_import_id:
        site_import = session.scalars(
            select(SiteImport).where(SiteImport.id == site.site_import_id)
        ).first()
        if site_import and isinstance(site_import.resolved_site_family, str):
            resolved_family = site_import.resolved_site_family.strip()
            if resolved_family:
                return resolved_family

    if isinstance(site.site_family, str) and site.site_family.strip():
        return site.site_family.strip()

    return "custom-site-template"


def _iter_puck_blocks(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from _iter_puck_blocks(item)
        return

    if not isinstance(value, dict):
        return

    block_type = value.get("type")
    props = value.get("props")
    if isinstance(block_type, str) and isinstance(props, dict):
        yield value
        slot_content = props.get("content")
        if isinstance(slot_content, list):
            yield from _iter_puck_blocks(slot_content)

    content = value.get("content")
    if isinstance(content, list):
        yield from _iter_puck_blocks(content)

    zones = value.get("zones")
    if isinstance(zones, dict):
        for zone_value in zones.values():
            yield from _iter_puck_blocks(zone_value)


def _button_override_matches_buy_now(override: dict[str, Any]) -> bool:
    for key in ("originalText", "text", "label"):
        candidate = str(override.get(key) or "").strip().upper()
        if candidate.startswith("ADD TO CART"):
            return True
    return False


def _load_latest_site_page_puck_data(session: Session, *, page: SitePage) -> dict[str, Any] | None:
    version = session.scalars(
        select(SitePageVersion)
        .where(SitePageVersion.page_id == str(page.id))
        .order_by(SitePageVersion.created_at.desc())
    ).first()
    if version and isinstance(version.puck_data, dict):
        return version.puck_data
    if isinstance(page.adapted_puck_data, dict):
        return page.adapted_puck_data
    return None


def _source_site_supports_medusa_one_product_store(
    session: Session,
    *,
    site: Site,
    site_pages: list[SitePage],
) -> bool:
    if not site.site_import_id or not site_pages:
        return False

    entry_page_id = str(site.entry_page_id) if site.entry_page_id else None
    entry_page = next((page for page in site_pages if str(page.id) == entry_page_id), None)
    if entry_page is None:
        entry_page = site_pages[0]

    page_type = str(entry_page.page_type or "").strip()
    if page_type and page_type not in {"home", "product_detail"}:
        return False

    puck_data = _load_latest_site_page_puck_data(session, page=entry_page)
    if not puck_data:
        return False

    imported_page_found = False
    for block in _iter_puck_blocks(puck_data):
        if block.get("type") == "ImportedPage":
            imported_page_found = True
            continue
        if block.get("type") != "ImportedRuntimeSection":
            continue
        props = block.get("props") or {}
        if str(props.get("componentName") or "").strip() != "ProductPurchaseSection":
            continue
        button_overrides = props.get("buttonOverrides")
        if not isinstance(button_overrides, list):
            continue
        for override in button_overrides:
            if isinstance(override, dict) and _button_override_matches_buy_now(override):
                return imported_page_found
    return False


def _template_has_mode(template: SiteTemplate, *, mode: str) -> bool:
    return _read_note_value(template.provenance_notes, _TEMPLATE_MODE_NOTE_PREFIX) == mode


def _mutate_medusa_one_product_entry_puck_data(puck_data: dict[str, Any]) -> dict[str, Any]:
    for block in _iter_puck_blocks(puck_data):
        if block.get("type") != "ImportedRuntimeSection":
            continue
        props = block.get("props") or {}
        if str(props.get("componentName") or "").strip() != "ProductPurchaseSection":
            continue
        button_overrides = props.get("buttonOverrides")
        if not isinstance(button_overrides, list):
            continue
        for override in button_overrides:
            if not isinstance(override, dict) or not _button_override_matches_buy_now(override):
                continue
            override["text"] = "BUY NOW -"
            override["action"] = "medusa_buy_now"
            override["selectionStrategy"] = "omni_selected_tier"
            override["replaceCart"] = True
            return puck_data
    return puck_data


def _resolve_instantiation_design_system_tokens(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    design_system_id: str | None,
    theme_binding_mode: str | None,
) -> dict[str, Any] | None:
    if design_system_id:
        try:
            design_system_uuid = UUID(design_system_id)
        except (TypeError, ValueError) as exc:
            raise SiteTemplateError(
                f"Invalid design system reference '{design_system_id}' on template instantiation."
            ) from exc

        design_system = session.scalars(
            select(DesignSystem).where(
                DesignSystem.org_id == UUID(org_id),
                DesignSystem.id == design_system_uuid,
            )
        ).first()
        if design_system is None:
            raise SiteTemplateError(
                f"Design system '{design_system_id}' no longer exists for this workspace."
            )
        return design_system.tokens

    if theme_binding_mode == "workspace_default":
        return resolve_design_system_tokens(
            session=session,
            org_id=org_id,
            client_id=client_id,
        )

    return None


def _resolve_template_page_puck_data(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    template: SiteTemplate,
    template_page: SiteTemplatePage,
    design_system_tokens: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_site_page_id = _read_note_value(
        template_page.provenance_notes,
        _SOURCE_SITE_PAGE_NOTE_PREFIX,
    )
    if source_site_page_id:
        source_page = session.scalars(
            select(SitePage).where(SitePage.id == source_site_page_id)
        ).first()
        if source_page is None:
            raise SiteTemplateError(
                f"Template page '{template_page.name}' references missing source page '{source_site_page_id}'."
            )

        source_version = session.scalars(
            select(SitePageVersion)
            .where(
                SitePageVersion.page_id == source_site_page_id,
                SitePageVersion.status == "approved",
            )
            .order_by(SitePageVersion.created_at.desc())
        ).first()
        if source_version is None:
            source_version = session.scalars(
                select(SitePageVersion)
                .where(SitePageVersion.page_id == source_site_page_id)
                .order_by(SitePageVersion.created_at.desc())
            ).first()

        if source_version is not None:
            puck_data = deepcopy(source_version.puck_data)
            if (
                _template_has_mode(template, mode=_MEDUSA_ONE_PRODUCT_TEMPLATE_MODE)
                and _read_note_value(
                    template_page.provenance_notes,
                    _TEMPLATE_PAGE_MODE_NOTE_PREFIX,
                )
                == _MEDUSA_ONE_PRODUCT_ENTRY_PAGE_MODE
            ):
                puck_data = _mutate_medusa_one_product_entry_puck_data(puck_data)
            return (
                puck_data,
                {
                    "source_type": "site_page",
                    "source_site_page_id": source_site_page_id,
                    "source_version_id": str(source_version.id),
                },
            )

        if source_page.adapted_puck_data:
            puck_data = deepcopy(source_page.adapted_puck_data)
            if (
                _template_has_mode(template, mode=_MEDUSA_ONE_PRODUCT_TEMPLATE_MODE)
                and _read_note_value(
                    template_page.provenance_notes,
                    _TEMPLATE_PAGE_MODE_NOTE_PREFIX,
                )
                == _MEDUSA_ONE_PRODUCT_ENTRY_PAGE_MODE
            ):
                puck_data = _mutate_medusa_one_product_entry_puck_data(puck_data)
            return (
                puck_data,
                {
                    "source_type": "site_page",
                    "source_site_page_id": source_site_page_id,
                    "source_version_id": None,
                },
            )

        raise SiteTemplateError(
            f"Template page '{template_page.name}' references source page '{source_site_page_id}' but no page content is available."
        )

    if template_page.page_template_id:
        page_template = get_funnel_template(template_page.page_template_id)
        if page_template is None:
            raise SiteTemplateError(
                f"Template page '{template_page.name}' references unknown page template '{template_page.page_template_id}'."
            )
        try:
            puck_data = apply_template_assets(
                session=session,
                org_id=org_id,
                client_id=client_id,
                template=page_template,
                design_system_tokens=design_system_tokens,
            )
        except ValueError as exc:
            raise SiteTemplateError(
                f"Failed to hydrate page template '{template_page.page_template_id}' for template page '{template_page.name}': {exc}"
            ) from exc

        return (
            puck_data,
            {
                "source_type": "page_template",
                "page_template_id": template_page.page_template_id,
            },
        )

    raise SiteTemplateError(
        f"Template page '{template_page.name}' has no source site page reference and no page template id."
    )


def create_template_from_site(
    session: Session,
    *,
    site_id: str,
    org_id: str,
    client_id: str,
    name: str,
    description: str | None,
    created_by_user_external_id: str | None,
) -> SiteTemplate:
    """Create a reusable site template from an existing site runtime record."""
    sites_repo = SitesRuntimeRepository(session)
    site = sites_repo.get_site(org_id=org_id, client_id=client_id, site_id=site_id)
    if site is None:
        raise SiteTemplateError("Source site not found.")

    site_pages = sites_repo.list_pages(site_id=site_id)
    if not site_pages:
        raise SiteTemplateError("Source site has no pages to template.")

    resolved_family = _resolve_template_family_for_site(session, site=site)
    enable_medusa_one_product_store = _source_site_supports_medusa_one_product_store(
        session,
        site=site,
        site_pages=site_pages,
    )
    existing = session.scalars(
        select(SiteTemplate).where(
            SiteTemplate.family == resolved_family,
            SiteTemplate.name == name,
        )
    ).first()
    if existing is not None:
        raise SiteTemplateError(
            f"A site template named '{name}' already exists for family '{resolved_family}'."
        )

    entry_page_id = str(site.entry_page_id) if site.entry_page_id else None
    page_type_by_id: dict[str, str] = {}
    for index, page in enumerate(site_pages):
        page_type = page.page_type or f"page_{index + 1}"
        if enable_medusa_one_product_store and str(page.id) == entry_page_id:
            page_type = "home"
        page_type_by_id[str(page.id)] = page_type

    template = SiteTemplate(
        id=str(uuid4()),
        family=resolved_family,
        name=name,
        description=description,
        site_type=site.site_type or "generic",
        commerce_provider="medusa"
        if enable_medusa_one_product_store
        else (site.commerce_provider or "none"),
        is_system_template=False,
        provenance_notes=[
            f"Created from site {site_id}",
            _note_with_value(_SOURCE_SITE_NOTE_PREFIX, site_id),
            *(
                [_note_with_value(_TEMPLATE_MODE_NOTE_PREFIX, _MEDUSA_ONE_PRODUCT_TEMPLATE_MODE)]
                if enable_medusa_one_product_store
                else []
            ),
        ],
        created_at=datetime.now(timezone.utc),
    )
    session.add(template)
    session.flush()

    for index, page in enumerate(site_pages):
        page_type = page.page_type or f"page_{index + 1}"
        is_entry = str(page.id) == str(site.entry_page_id) if site.entry_page_id else index == 0
        slug = page.slug
        provenance_notes = [
            _note_with_value(_SOURCE_SITE_PAGE_NOTE_PREFIX, str(page.id)),
        ]
        if enable_medusa_one_product_store and is_entry:
            page_type = "home"
            slug = "home"
            provenance_notes.append(
                _note_with_value(_TEMPLATE_PAGE_MODE_NOTE_PREFIX, _MEDUSA_ONE_PRODUCT_ENTRY_PAGE_MODE)
            )
        template_page = SiteTemplatePage(
            id=str(uuid4()),
            site_template_id=str(template.id),
            page_type=page_type,
            name=page.name,
            slug=slug,
            description=None,
            page_template_id=page.page_template_id or page.template_id,
            ordering=page.ordering,
            is_entry=is_entry,
            provenance_notes=provenance_notes,
            created_at=datetime.now(timezone.utc),
        )
        session.add(template_page)

    if enable_medusa_one_product_store:
        existing_page_types = set(page_type_by_id.values())
        next_ordering = (
            max(((page.ordering or 0) for page in site_pages), default=0) + 1
        )
        for blueprint in _MEDUSA_ONE_PRODUCT_AUXILIARY_PAGES:
            if blueprint.page_type in existing_page_types:
                continue
            session.add(
                SiteTemplatePage(
                    id=str(uuid4()),
                    site_template_id=str(template.id),
                    page_type=blueprint.page_type,
                    name=blueprint.name,
                    slug=blueprint.slug,
                    description=blueprint.description,
                    page_template_id=blueprint.template_id,
                    ordering=next_ordering,
                    is_entry=False,
                    provenance_notes=[],
                    created_at=datetime.now(timezone.utc),
                )
            )
            existing_page_types.add(blueprint.page_type)
            next_ordering += 1

    site_links = sites_repo.list_links(site_id=site_id)
    for site_link in site_links:
        from_page_type = (
            site_link.from_page_type
            or (page_type_by_id.get(str(site_link.from_page_id)) if site_link.from_page_id else None)
        )
        to_page_type = (
            site_link.to_page_type
            or (page_type_by_id.get(str(site_link.to_page_id)) if site_link.to_page_id else None)
        )
        session.add(
            SiteTemplateLink(
                id=str(uuid4()),
                site_template_id=str(template.id),
                from_page_type=from_page_type,
                to_page_type=to_page_type,
                label=site_link.label,
                link_kind=site_link.link_kind,
                meta=site_link.meta or {},
                created_at=datetime.now(timezone.utc),
            )
        )

    session.flush()
    session.refresh(template)
    return template


def get_template_theme_requirement(family: str | None) -> str | None:
    """Resolve theme requirement metadata for a template family."""
    if not family:
        return None
    descriptor = get_site_family(family)
    return descriptor.theme_requirement if descriptor else None


def seed_system_templates(session: Session) -> list[SiteTemplate]:
    """Seed built-in site blueprints as system site templates.

    This function ensures that all built-in site families from site_blueprints
    are persisted as system templates in the database.
    """
    families = list_site_families()
    created_templates = []

    for family_descriptor in families:
        # Check if template already exists
        existing = session.scalars(
            select(SiteTemplate).where(
                SiteTemplate.family == family_descriptor.family,
                SiteTemplate.is_system_template == True,  # noqa: E712
            )
        ).first()

        if existing:
            continue

        # Create the template
        template = SiteTemplate(
            id=str(uuid4()),
            family=family_descriptor.family,
            name=family_descriptor.name,
            description=family_descriptor.description,
            site_type=family_descriptor.site_type,
            commerce_provider=family_descriptor.commerce_provider,
            is_system_template=True,
            provenance_notes=list(family_descriptor.provenance_notes),
            created_at=datetime.now(timezone.utc),
        )
        session.add(template)

        # Create page blueprints
        for blueprint in family_descriptor.page_blueprints:
            page = SiteTemplatePage(
                id=str(uuid4()),
                site_template_id=template.id,
                page_type=blueprint.page_type,
                name=blueprint.name,
                slug=blueprint.slug,
                description=blueprint.description,
                page_template_id=blueprint.template_id,
                ordering=blueprint.ordering,
                is_entry=blueprint.is_entry,
                provenance_notes=[],
                created_at=datetime.now(timezone.utc),
            )
            session.add(page)

        created_templates.append(template)

    if created_templates:
        session.commit()
        for template in created_templates:
            session.refresh(template)

    return created_templates


def list_templates(session: Session) -> list[SiteTemplate]:
    """List all site templates (both system and user-created)."""
    stmt = select(SiteTemplate).order_by(SiteTemplate.created_at.desc())
    return list(session.scalars(stmt).all())


def get_template(session: Session, template_id: str) -> SiteTemplate | None:
    """Get a site template by ID."""
    return session.scalars(select(SiteTemplate).where(SiteTemplate.id == template_id)).first()


def get_template_by_family(session: Session, family: str) -> SiteTemplate | None:
    """Get a site template by family name."""
    return session.scalars(select(SiteTemplate).where(SiteTemplate.family == family)).first()


def get_template_pages(session: Session, template_id: str) -> list[SiteTemplatePage]:
    """Get all pages for a site template."""
    stmt = (
        select(SiteTemplatePage)
        .where(SiteTemplatePage.site_template_id == template_id)
        .order_by(SiteTemplatePage.ordering)
    )
    return list(session.scalars(stmt).all())


def get_template_links(session: Session, template_id: str) -> list[SiteTemplateLink]:
    """Get all links for a site template."""
    stmt = select(SiteTemplateLink).where(SiteTemplateLink.site_template_id == template_id)
    return list(session.scalars(stmt).all())


def get_template_funnels(session: Session, template_id: str) -> list[SiteTemplateFunnel]:
    """Get all funnels for a site template."""
    stmt = select(SiteTemplateFunnel).where(SiteTemplateFunnel.site_template_id == template_id)
    return list(session.scalars(stmt).all())


def get_template_funnel_steps(
    session: Session, template_funnel_id: str
) -> list[SiteTemplateFunnelStep]:
    """Get all steps for a site template funnel."""
    stmt = (
        select(SiteTemplateFunnelStep)
        .where(SiteTemplateFunnelStep.site_template_funnel_id == template_funnel_id)
        .order_by(SiteTemplateFunnelStep.ordering)
    )
    return list(session.scalars(stmt).all())


def instantiate_template(
    session: Session,
    *,
    template_id: str,
    org_id: str,
    client_id: str,
    name: str,
    description: str | None = None,
    product_id: str | None = None,
    design_system_id: str | None = None,
    theme_binding_mode: str | None = None,
    primary_domain: str | None = None,
    created_by_user_external_id: str | None = None,
) -> dict[str, Any]:
    """Instantiate a site template into a new site.

    This creates a site from a template, including all pages.
    """
    template = get_template(session, template_id)
    if not template:
        raise SiteTemplateError(f"Template not found: {template_id}")

    if getattr(template, "status", "active") == "deprecated":
        raise SiteTemplateError(f"Template is deprecated: {template_id}")

    try:
        validate_theme_requirement(
            get_site_family(template.family),
            theme_binding_mode=theme_binding_mode or "standalone",
            subject=f"Site template '{template.name}'",
        )
    except ValueError as exc:
        raise SiteTemplateError(str(exc)) from exc

    sites_repo = SitesRuntimeRepository(session)
    design_system_tokens = _resolve_instantiation_design_system_tokens(
        session,
        org_id=org_id,
        client_id=client_id,
        design_system_id=design_system_id,
        theme_binding_mode=theme_binding_mode,
    )

    # Generate unique route slug
    route_slug = sites_repo._generate_unique_route_slug(desired_slug=name)

    # Create the site
    site = sites_repo.create_site(
        org_id=org_id,
        client_id=client_id,
        site_template_id=template_id,
        design_system_id=design_system_id,
        theme_binding_mode=theme_binding_mode,
        product_id=product_id,
        name=name,
        description=description or template.description,
        site_type=template.site_type,
        site_family=template.family,
        commerce_provider=template.commerce_provider,
        route_slug=route_slug,
        primary_domain=primary_domain,
        created_by_user_external_id=created_by_user_external_id,
    )

    # Create pages from template pages
    template_pages = get_template_pages(session, template_id)
    page_type_to_id: dict[str, str] = {}
    created_pages: list[dict[str, Any]] = []
    entry_page_id = None

    for tpage in template_pages:
        template_puck_data, page_source_provenance = _resolve_template_page_puck_data(
            session,
            org_id=org_id,
            client_id=client_id,
            template=template,
            template_page=tpage,
            design_system_tokens=design_system_tokens,
        )
        # NOTE: Pages do NOT inherit site.design_system_id. They inherit from the site
        # at token-resolution time only when they don't have an explicit override.
        page = sites_repo.create_page(
            site_id=str(site.id),
            name=tpage.name,
            slug=tpage.slug,
            page_type=tpage.page_type,
            page_role=tpage.page_type,
            template_id=tpage.page_template_id,
            page_template_id=tpage.page_template_id,
            ordering=tpage.ordering,
            adapted_puck_data=template_puck_data,
        )

        # Create initial draft version
        version = sites_repo.create_page_version(
            page_id=str(page.id),
            puck_data=deepcopy(template_puck_data),
            provenance={
                "source_type": "template",
                "template_id": template_id,
                "page_template_id": tpage.page_template_id,
                **page_source_provenance,
            },
            status="draft",
            source_type="site_template",
            source_id=template_id,
        )
        approved_version = sites_repo.create_page_version(
            page_id=str(page.id),
            puck_data=deepcopy(template_puck_data),
            provenance={
                "source_type": "template",
                "template_id": template_id,
                "page_template_id": tpage.page_template_id,
                **page_source_provenance,
            },
            status="approved",
            source_type="site_template",
            source_id=template_id,
        )

        page_type_to_id[tpage.page_type] = str(page.id)
        created_pages.append(
            {
                "pageId": str(page.id),
                "pageType": tpage.page_type,
                "templateId": tpage.page_template_id,
                "versionId": str(version.id),
                "approvedVersionId": str(approved_version.id),
            }
        )

        if tpage.is_entry:
            entry_page_id = str(page.id)

    # Create links from template links
    template_links = get_template_links(session, template_id)
    for tlink in template_links:
        sites_repo.create_link(
            site_id=str(site.id),
            from_page_id=page_type_to_id.get(tlink.from_page_type)
            if tlink.from_page_type
            else None,
            to_page_id=page_type_to_id.get(tlink.to_page_type) if tlink.to_page_type else None,
            from_page_type=tlink.from_page_type,
            to_page_type=tlink.to_page_type,
            label=tlink.label,
            link_kind=tlink.link_kind,
            meta=tlink.meta,
        )

    # Create funnels from template funnels
    template_funnels = get_template_funnels(session, template_id)
    funnel_count = 0

    for tfunnel in template_funnels:
        funnel_entry_page_id = (
            page_type_to_id.get(tfunnel.entry_page_type) if tfunnel.entry_page_type else None
        )
        funnel = SiteFunnel(
            id=str(uuid4()),
            site_id=str(site.id),
            name=tfunnel.name,
            description=tfunnel.description,
            funnel_type=tfunnel.funnel_type,
            entry_page_id=funnel_entry_page_id,
            status="draft",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(funnel)

        # Get funnel steps
        tsteps = get_template_funnel_steps(session, str(tfunnel.id))
        for tstep in tsteps:
            step = SiteFunnelStep(
                id=str(uuid4()),
                site_funnel_id=funnel.id,
                site_page_id=page_type_to_id.get(tstep.page_type, ""),
                ordering=tstep.ordering,
                step_role=tstep.step_role,
                cta_label=tstep.cta_label,
                created_at=datetime.now(timezone.utc),
            )
            session.add(step)

        funnel_count += 1

    # Set entry page on site
    if entry_page_id:
        site.entry_page_id = entry_page_id
        sites_repo.update_site(site=site)

    placeholder_id_map = {
        placeholder: page_id
        for page_type, placeholder in _PAGE_TYPE_PLACEHOLDERS.items()
        if (page_id := page_type_to_id.get(page_type))
    }
    if placeholder_id_map:
        from app.services.funnels import rewrite_internal_target_ids

        for page_data in created_pages:
            page = sites_repo.get_page(site_id=str(site.id), page_id=page_data["pageId"])
            if page is None:
                continue
            rewritten_puck_data = rewrite_internal_target_ids(
                page.adapted_puck_data,
                placeholder_id_map,
            )
            page.adapted_puck_data = rewritten_puck_data
            sites_repo.update_page(page=page)

            for page_version in sites_repo.list_versions_for_page(page_id=page_data["pageId"]):
                page_version.puck_data = deepcopy(rewritten_puck_data)
                session.add(page_version)

    session.flush()
    session.refresh(site)

    return {
        "siteId": str(site.id),
        "siteName": site.name,
        "pageCount": len(created_pages),
        "funnelCount": funnel_count,
        "entryPageId": entry_page_id,
        "createdAt": site.created_at,
    }
