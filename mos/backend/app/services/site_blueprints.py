"""Site family and page blueprint definitions for Site-based experiences.

This module defines site families (e.g., medusa-b2b-starter) and their page blueprints,
which are used to create Site instances backed by the existing funnel/page runtime.

The commerce-core page set includes:
- home: Homepage with featured products, categories, and value propositions
- category: Product category/collection page with filtering
- product_detail: Product detail page with pricing and add-to-cart
- cart: Shopping cart with quantity adjustments
- checkout: Checkout flow with shipping and payment

Quote flows, approval flows, and account flows are NOT included in the current scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SitePageBlueprint:
    """Blueprint for a single page within a site family."""

    page_type: str
    template_id: str
    name: str
    slug: str
    description: str | None
    ordering: int
    is_entry: bool = False


@dataclass(frozen=True)
class SiteFamilyDescriptor:
    """Descriptor for a site family (e.g., medusa-b2b-starter)."""

    family: str
    name: str
    description: str
    site_type: str
    commerce_provider: str
    page_blueprints: tuple[SitePageBlueprint, ...]
    provenance_notes: tuple[str, ...]


# Medusa B2B Starter page blueprints
# These are truthful shells grounded in the Medusa B2B starter feature set:
# - Product catalog and categories
# - Product detail pages with pricing
# - Shopping cart
# - Checkout flow with shipping and payment
#
# Note: Quote, approval, and account flows are NOT included in the current scope.

MEDUSA_B2B_STARTER_BLUEPRINT = SiteFamilyDescriptor(
    family="medusa-b2b-starter",
    name="Medusa B2B Starter",
    description="A B2B ecommerce starter template with product catalog, cart, and checkout.",
    site_type="ecommerce",
    commerce_provider="medusa",
    page_blueprints=(
        SitePageBlueprint(
            page_type="home",
            template_id="medusa-b2b-home",
            name="Home",
            slug="home",
            description="Homepage with featured products, categories, and B2B value propositions.",
            ordering=0,
            is_entry=True,
        ),
        SitePageBlueprint(
            page_type="category",
            template_id="medusa-b2b-category",
            name="Category",
            slug="category",
            description="Product category/collection page with filtering and selection.",
            ordering=1,
        ),
        SitePageBlueprint(
            page_type="product_detail",
            template_id="medusa-b2b-pdp",
            name="Product Detail",
            slug="product",
            description="Product detail page with pricing, variants, and add-to-cart.",
            ordering=2,
        ),
        SitePageBlueprint(
            page_type="cart",
            template_id="medusa-b2b-cart",
            name="Cart",
            slug="cart",
            description="Shopping cart with quantity adjustments and checkout initiation.",
            ordering=3,
        ),
        SitePageBlueprint(
            page_type="checkout",
            template_id="medusa-b2b-checkout",
            name="Checkout",
            slug="checkout",
            description="Checkout flow with shipping, payment, and order confirmation.",
            ordering=4,
        ),
    ),
    provenance_notes=(
        "Derived from Medusa B2B starter feature set.",
        "Supports product catalog, cart, and checkout flows.",
        "Uses existing Puck block system for page composition.",
        "No fake reviews or unsupported business claims.",
        "Quote, approval, and account flows are not included in current scope.",
    ),
)


# Registry of all site families
SITE_FAMILIES: dict[str, SiteFamilyDescriptor] = {
    "medusa-b2b-starter": MEDUSA_B2B_STARTER_BLUEPRINT,
}


def list_site_families() -> list[SiteFamilyDescriptor]:
    """List all available site families."""
    return list(SITE_FAMILIES.values())


def get_site_family(family: str) -> SiteFamilyDescriptor | None:
    """Get a specific site family descriptor by family ID."""
    return SITE_FAMILIES.get(family)


def get_page_blueprint(family: str, page_type: str) -> SitePageBlueprint | None:
    """Get a specific page blueprint from a site family."""
    descriptor = SITE_FAMILIES.get(family)
    if not descriptor:
        return None
    for blueprint in descriptor.page_blueprints:
        if blueprint.page_type == page_type:
            return blueprint
    return None


def get_entry_page_blueprint(family: str) -> SitePageBlueprint | None:
    """Get the entry page blueprint for a site family."""
    descriptor = SITE_FAMILIES.get(family)
    if not descriptor:
        return None
    for blueprint in descriptor.page_blueprints:
        if blueprint.is_entry:
            return blueprint
    return None
