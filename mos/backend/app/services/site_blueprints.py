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
from typing import Any, Literal


ThemeRequirement = Literal["optional", "required"]


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
    theme_requirement: ThemeRequirement = "optional"


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
    theme_requirement="optional",
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
        SitePageBlueprint(
            page_type="privacy_policy",
            template_id="medusa-b2b-policy-privacy",
            name="Privacy Policy",
            slug="privacy",
            description="Store privacy policy rendered from the workspace compliance profile.",
            ordering=5,
        ),
        SitePageBlueprint(
            page_type="terms_of_service",
            template_id="medusa-b2b-policy-terms",
            name="Terms of Service",
            slug="terms",
            description="Store terms of service rendered from the workspace compliance profile.",
            ordering=6,
        ),
        SitePageBlueprint(
            page_type="returns_refunds_policy",
            template_id="medusa-b2b-policy-returns",
            name="Returns and Refunds",
            slug="returns",
            description="Returns and refunds policy rendered from the workspace compliance profile.",
            ordering=7,
        ),
        SitePageBlueprint(
            page_type="shipping_policy",
            template_id="medusa-b2b-policy-shipping",
            name="Shipping Policy",
            slug="shipping",
            description="Shipping policy rendered from the workspace compliance profile.",
            ordering=8,
        ),
        SitePageBlueprint(
            page_type="contact_support",
            template_id="medusa-b2b-policy-contact",
            name="Contact",
            slug="contact",
            description="Customer support and business contact information for the store.",
            ordering=9,
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


# Medusa B2C Starter page blueprints
# These are truthful shells grounded in the Medusa B2C starter feature set:
# - home, store, collection, category, product_detail
# - cart, checkout
# - account_dashboard, account_profile, account_addresses, account_orders, account_order_detail
# - order_confirmed, order_transfer, order_transfer_accept, order_transfer_decline
#
# Source: medusajs/nextjs-starter-medusa commit 56c4a6fa2a0432430007ffa912a34573b665cf19

MEDUSA_B2C_STARTER_BLUEPRINT = SiteFamilyDescriptor(
    family="medusa-b2c-starter",
    name="Medusa B2C Starter",
    description="A B2C ecommerce starter template with full storefront, cart, checkout, and customer account flows.",
    site_type="ecommerce",
    commerce_provider="medusa",
    theme_requirement="optional",
    page_blueprints=(
        SitePageBlueprint(
            page_type="home",
            template_id="medusa-b2c-home",
            name="Home",
            slug="home",
            description="Homepage with featured products, categories, and store navigation.",
            ordering=0,
            is_entry=True,
        ),
        SitePageBlueprint(
            page_type="store",
            template_id="medusa-b2c-store",
            name="All Products",
            slug="store",
            description="All products store page with full product listing.",
            ordering=1,
        ),
        SitePageBlueprint(
            page_type="collection",
            template_id="medusa-b2c-collection",
            name="Collection",
            slug="collection",
            description="Product collection page with filtering.",
            ordering=2,
        ),
        SitePageBlueprint(
            page_type="category",
            template_id="medusa-b2c-category",
            name="Category",
            slug="category",
            description="Product category page with nested subcategory support.",
            ordering=3,
        ),
        SitePageBlueprint(
            page_type="product_detail",
            template_id="medusa-b2c-product",
            name="Product Detail",
            slug="product",
            description="Product detail page with gallery, pricing, variants, and add-to-cart.",
            ordering=4,
        ),
        SitePageBlueprint(
            page_type="cart",
            template_id="medusa-b2c-cart",
            name="Cart",
            slug="cart",
            description="Shopping cart with quantity adjustments and checkout initiation.",
            ordering=5,
        ),
        SitePageBlueprint(
            page_type="checkout",
            template_id="medusa-b2c-checkout",
            name="Checkout",
            slug="checkout",
            description="Checkout flow with shipping, payment, and order confirmation.",
            ordering=6,
        ),
        SitePageBlueprint(
            page_type="privacy_policy",
            template_id="medusa-b2c-policy-privacy",
            name="Privacy Policy",
            slug="privacy-policy",
            description="Store privacy policy rendered from the workspace compliance profile.",
            ordering=7,
        ),
        SitePageBlueprint(
            page_type="terms_of_service",
            template_id="medusa-b2c-policy-terms",
            name="Terms of Service",
            slug="terms-of-service",
            description="Terms of service rendered from the workspace compliance profile.",
            ordering=8,
        ),
        SitePageBlueprint(
            page_type="returns_refunds_policy",
            template_id="medusa-b2c-policy-returns",
            name="Refund Policy",
            slug="refund-policy",
            description="Returns and refunds policy rendered from the workspace compliance profile.",
            ordering=9,
        ),
        SitePageBlueprint(
            page_type="shipping_policy",
            template_id="medusa-b2c-policy-shipping",
            name="Shipping Policy",
            slug="shipping-policy",
            description="Shipping policy rendered from the workspace compliance profile.",
            ordering=10,
        ),
        SitePageBlueprint(
            page_type="contact_support",
            template_id="medusa-b2c-policy-contact",
            name="Contact Support",
            slug="contact-support",
            description="Support contact page rendered from the workspace compliance profile.",
            ordering=11,
        ),
        SitePageBlueprint(
            page_type="account_dashboard",
            template_id="medusa-b2c-account-dashboard",
            name="Account Dashboard",
            slug="account",
            description="Customer account overview with login/register.",
            ordering=12,
        ),
        SitePageBlueprint(
            page_type="account_profile",
            template_id="medusa-b2c-account-profile",
            name="Account Profile",
            slug="account/profile",
            description="Customer profile management.",
            ordering=13,
        ),
        SitePageBlueprint(
            page_type="account_addresses",
            template_id="medusa-b2c-account-addresses",
            name="Account Addresses",
            slug="account/addresses",
            description="Customer address book management.",
            ordering=14,
        ),
        SitePageBlueprint(
            page_type="account_orders",
            template_id="medusa-b2c-account-orders",
            name="Account Orders",
            slug="account/orders",
            description="Customer orders list.",
            ordering=15,
        ),
        SitePageBlueprint(
            page_type="account_order_detail",
            template_id="medusa-b2c-account-order-detail",
            name="Order Detail",
            slug="account/orders/details",
            description="Single order detail view.",
            ordering=16,
        ),
        SitePageBlueprint(
            page_type="order_confirmed",
            template_id="medusa-b2c-order-confirmed",
            name="Order Confirmed",
            slug="order/confirmed",
            description="Order confirmation page after successful checkout.",
            ordering=17,
        ),
        SitePageBlueprint(
            page_type="order_transfer",
            template_id="medusa-b2c-order-transfer",
            name="Order Transfer",
            slug="order/transfer",
            description="Order transfer landing page for gift/transfer flows.",
            ordering=18,
        ),
        SitePageBlueprint(
            page_type="order_transfer_accept",
            template_id="medusa-b2c-order-transfer-accept",
            name="Accept Transfer",
            slug="order/transfer/accept",
            description="Accept order transfer action page.",
            ordering=19,
        ),
        SitePageBlueprint(
            page_type="order_transfer_decline",
            template_id="medusa-b2c-order-transfer-decline",
            name="Decline Transfer",
            slug="order/transfer/decline",
            description="Decline order transfer action page.",
            ordering=20,
        ),
    ),
    provenance_notes=(
        "Derived from Medusa B2C starter feature set (medusajs/nextjs-starter-medusa).",
        "Supports full storefront, cart, checkout, policy pages, and customer account flows.",
        "No fake reviews or unsupported business claims.",
        "Account, address, order, and transfer flows included.",
    ),
)


# Registry of all site families
SITE_FAMILIES: dict[str, SiteFamilyDescriptor] = {
    "medusa-b2b-starter": MEDUSA_B2B_STARTER_BLUEPRINT,
    "medusa-b2c-starter": MEDUSA_B2C_STARTER_BLUEPRINT,
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


def validate_theme_requirement(
    descriptor: SiteFamilyDescriptor | None,
    *,
    theme_binding_mode: str,
    subject: str,
) -> None:
    """Validate that a descriptor's theme requirement matches the requested mode."""
    if descriptor is None or descriptor.theme_requirement != "required":
        return
    if theme_binding_mode != "standalone":
        return
    raise ValueError(
        f"{subject} requires an explicit site theme. "
        "Choose 'workspace_default' or 'design_system' instead of 'standalone'."
    )
