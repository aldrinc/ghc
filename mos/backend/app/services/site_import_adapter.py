"""MOS adapter service for site import.

This service adapts GeneratorRunResult from the screenshot-to-code generator
into concrete Puck data for the Site runtime using site blueprints.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.services.site_blueprints import (
    SITE_FAMILIES,
    SitePageBlueprint,
    get_page_blueprint,
)
from app.services.site_import_generator_client import GeneratorRunResult

logger = logging.getLogger(__name__)


# Default model slots for generation.
# Default single-candidate imports use explicit slot 1 (Gemini).
DEFAULT_MODEL_SLOTS = [1]

# Supported site families for validation (from blueprints)
SUPPORTED_FAMILIES = set(SITE_FAMILIES.keys())

PAGE_TYPE_HINT_ALIASES = {
    "home": "home",
    "homepage": "home",
    "landing": "home",
    "store": "store",
    "collection": "collection",
    "category": "category",
    "product": "product_detail",
    "pdp": "product_detail",
    "product_detail": "product_detail",
    "cart": "cart",
    "checkout": "checkout",
    "account": "account_dashboard",
    "account_dashboard": "account_dashboard",
    "account_profile": "account_profile",
    "account_addresses": "account_addresses",
    "account_orders": "account_orders",
    "account_order_detail": "account_order_detail",
    "order_confirmed": "order_confirmed",
    "order_transfer": "order_transfer",
    "order_transfer_accept": "order_transfer_accept",
    "order_transfer_decline": "order_transfer_decline",
}


@dataclass(frozen=True)
class AdaptedPage:
    """An adapted page from the generator output."""

    page_type: str
    template_id: str
    name: str
    slug: str
    puck_data: dict[str, Any]
    generated_code: str | None


@dataclass(frozen=True)
class AdapterResult:
    """Result of adapting generator output to site data."""

    adapted_site: dict[str, Any]
    adapted_pages: list[dict[str, Any]]
    adapted_puck_data: dict[str, Any]
    resolved_site_family: str
    resolved_page_type: str
    resolved_template_id: str


class SiteImportAdapterError(Exception):
    """Error during site adaptation."""

    pass


def _normalize_page_type_hint(page_type_hint: str | None) -> str | None:
    if not page_type_hint:
        return None

    normalized = PAGE_TYPE_HINT_ALIASES.get(page_type_hint.strip().lower())
    if normalized is None:
        raise SiteImportAdapterError(
            "Unsupported pageTypeHint. Supported values: "
            f"{', '.join(sorted(PAGE_TYPE_HINT_ALIASES))}"
        )
    return normalized


def _extract_html_from_code(code: str | None) -> str | None:
    """Extract HTML from generated code (React component or HTML file)."""
    if not code:
        return None

    # Try to find HTML content in the generated code
    # Handle React component with template literal
    html_match = re.search(
        r"return\s*\(`(.*?)`\);",
        code,
        re.DOTALL,
    )
    if html_match:
        return html_match.group(1)

    # Handle plain HTML file
    html_match = re.search(r"<html[^>]*>(.*?)</html>", code, re.DOTALL | re.IGNORECASE)
    if html_match:
        return html_match.group(0)

    # Handle component returning JSX
    html_match = re.search(
        r"return\s*\(?(.*?)\);?\s*$",
        code,
        re.DOTALL | re.MULTILINE,
    )
    if html_match:
        return html_match.group(1)

    return None


def _detect_page_type_from_content(code: str | None, html: str | None) -> str:
    """Detect the page type from generated content."""
    if not code and not html:
        raise SiteImportAdapterError(
            "Adapter could not classify the imported page because generator output was empty. Provide a page type hint."
        )

    content = (code or "") + (html or "")
    content_lower = content.lower()

    # Product detail page detection
    if any(
        marker in content_lower
        for marker in [
            "product",
            "pdp",
            "detail",
            "add to cart",
            "add-to-cart",
            "price",
            "$",
            "variant",
            "buy now",
        ]
    ):
        return "product_detail"

    # Category/collection page detection
    if any(
        marker in content_lower
        for marker in [
            "collection",
            "category",
            "filter",
            "grid",
            "products",
            "browse",
        ]
    ):
        return "category"

    # Cart page detection
    if any(
        marker in content_lower
        for marker in [
            "cart",
            "shopping cart",
            "checkout",
            "items",
            "quantity",
            "remove",
        ]
    ):
        # Distinguish cart from checkout
        if "checkout" in content_lower and "cart" not in content_lower.split("checkout")[0]:
            return "checkout"
        return "cart"

    # Checkout detection
    if any(
        marker in content_lower
        for marker in [
            "checkout",
            "shipping",
            "payment",
            "billing",
            "order",
            "address",
        ]
    ):
        return "checkout"

    raise SiteImportAdapterError(
        "Adapter could not classify the imported page into a supported page role from the generated React/Tailwind output. Provide a page type hint or improve the adapter mapping."
    )


def _infer_site_family_from_content(code: str | None) -> str:
    """
    Infer the site family from generated content.

    Returns the inferred family if evidence is found, otherwise raises
    SiteImportAdapterError to avoid silent default behavior.

    Args:
        code: The generated React/Tailwind code to analyze.

    Returns:
        The inferred site family string.

    Raises:
        SiteImportAdapterError: If no family evidence is found in the content.
    """
    if not code:
        raise SiteImportAdapterError(
            "Cannot determine site family: no generated code available. "
            "Provide a siteFamilyHint to specify the target family."
        )

    code_lower = code.lower()

    # Check for B2B indicators (checked first as more specific)
    if any(
        marker in code_lower
        for marker in [
            "b2b",
            "wholesale",
            "business",
            "company",
            "bulk",
            "quote",
            "purchase order",
            "net 30",
        ]
    ):
        return "medusa-b2b-starter"

    # Check for B2C indicators (generic storefront/retail markers)
    if any(
        marker in code_lower
        for marker in [
            "b2c",
            "retail",
            "storefront",
            "customer account",
            "order history",
            "shipping address",
            "gift card",
            "loyalty",
            "medusab2c",
        ]
    ):
        return "medusa-b2c-starter"

    # No evidence found - raise error instead of silent default
    raise SiteImportAdapterError(
        "Cannot determine site family: no recognizable family-specific evidence found in generated content. "
        "Provide a siteFamilyHint to specify the target family. "
        f"Supported families: {', '.join(sorted(SUPPORTED_FAMILIES))}"
    )


def _build_puck_data_from_code(
    code: str | None,
    html: str | None,
    page_type: str,
    template_id: str,
) -> dict[str, Any]:
    """
    Build Puck data structure from generated code.

    This creates a minimal Puck data structure that can be used with the
    medusa-b2b-* templates. The actual block mapping would be done through
    synthesis, but we provide a basic structure here.
    """
    # Extract key content from generated code for potential future use
    content_preview = ""
    if html:
        # Get text content from HTML
        text_matches = re.findall(r"<[^>]*>([^<]*)</[^>]*>", html)
        content_preview = " ".join(t.strip() for t in text_matches[:10])

    # Build a basic Puck data structure
    # The root field is required by Puck
    puck_data: dict[str, Any] = {
        "root": {
            "props": {
                "title": content_preview[:100] if content_preview else "Imported Page",
            },
        },
        "content": [],
    }

    # Add basic blocks based on page type
    # This is a minimal structure - synthesis would populate with actual blocks
    if page_type == "home":
        puck_data["content"] = [
            {
                "props": {
                    "heading": "Welcome",
                    "subheading": content_preview[:200]
                    if content_preview
                    else "Imported from website",
                },
                "type": "Heading",
            },
        ]
    elif page_type == "product_detail":
        puck_data["content"] = [
            {
                "props": {
                    "title": "Product",
                    "description": content_preview[:200]
                    if content_preview
                    else "Product description",
                },
                "type": "ProductCard",
            },
        ]
    elif page_type == "category":
        puck_data["content"] = [
            {
                "props": {
                    "title": "Collection",
                },
                "type": "ProductCollection",
            },
        ]
    elif page_type == "cart":
        puck_data["content"] = [
            {
                "props": {
                    "title": "Shopping Cart",
                },
                "type": "Cart",
            },
        ]
    elif page_type == "checkout":
        puck_data["content"] = [
            {
                "props": {
                    "title": "Checkout",
                },
                "type": "Checkout",
            },
        ]

    return puck_data


def _map_to_template(
    page_type: str,
    family: str = "medusa-b2b-starter",
) -> tuple[SitePageBlueprint | None, str]:
    """
    Map a detected page type to a template blueprint.

    Returns the blueprint and resolved site family.
    """
    # Get the page blueprint
    blueprint = get_page_blueprint(family, page_type)

    if blueprint is None:
        raise SiteImportAdapterError(
            f"No template found for page type: {page_type} in family: {family}"
        )

    return blueprint, family


def _validate_site_family(family: str | None) -> str:
    """
    Validate a site family hint.

    Args:
        family: The family string to validate.

    Returns:
        The validated family string.

    Raises:
        SiteImportAdapterError: If the family is not supported.
    """
    if family is None:
        raise SiteImportAdapterError(
            "Site family is required. Provide a siteFamilyHint to specify the target family. "
            f"Supported families: {', '.join(sorted(SUPPORTED_FAMILIES))}"
        )

    if family not in SUPPORTED_FAMILIES:
        raise SiteImportAdapterError(
            f"Unsupported site family: {family}. "
            f"Supported families: {', '.join(sorted(SUPPORTED_FAMILIES))}"
        )

    return family


def adapt_generator_result(
    generator_result: GeneratorRunResult,
    page_type_hint: str | None = None,
    site_family_hint: str | None = None,
) -> AdapterResult:
    """
    Adapt generator output to Site runtime format.

    Takes the GeneratorRunResult from the screenshot-to-code generator and:
    1. Extracts generated code from variants
    2. Detects page type from content
    3. Resolves site family (from hint or inference)
    4. Maps to appropriate templates
    5. Builds adapted_site, adapted_pages, and adapted_puck_data

    Args:
        generator_result: The result from the screenshot-to-code generator
        page_type_hint: Optional hint for the page type (e.g., 'home', 'pdp')
        site_family_hint: Optional hint for the site family (e.g., 'medusa-b2b-starter')

    Returns:
        AdapterResult with adapted data and resolved fields
    """
    # Get the first variant (primary)
    variants = generator_result.variants
    if not variants:
        raise SiteImportAdapterError("Generator returned no variants")

    primary_variant = variants[0]
    generated_code = primary_variant.get("code")

    # Extract HTML from code
    html_content = _extract_html_from_code(generated_code)

    # Detect page type
    if page_type_hint:
        detected_page_type = _normalize_page_type_hint(page_type_hint)
    else:
        detected_page_type = _detect_page_type_from_content(generated_code, html_content)

    # Determine site family: use hint if provided, otherwise infer
    if site_family_hint:
        resolved_family = _validate_site_family(site_family_hint)
    else:
        # Try to infer from content - will raise if no evidence found
        resolved_family = _infer_site_family_from_content(generated_code)

    # Map to template
    blueprint, resolved_family = _map_to_template(detected_page_type, resolved_family)

    if blueprint is None:
        raise SiteImportAdapterError(f"Could not map page type {detected_page_type} to template")

    # Build Puck data
    puck_data = _build_puck_data_from_code(
        code=generated_code,
        html=html_content,
        page_type=detected_page_type,
        template_id=blueprint.template_id,
    )

    # Build adapted page
    adapted_page: dict[str, Any] = {
        "page_type": blueprint.page_type,
        "template_id": blueprint.template_id,
        "name": blueprint.name,
        "slug": blueprint.slug,
        "ordering": blueprint.ordering,
        "puck_data": puck_data,
        "generated_code": generated_code,
    }

    # Build adapted site
    adapted_site: dict[str, Any] = {
        "name": f"Imported Site ({resolved_family})",
        "site_family": resolved_family,
        "site_type": "ecommerce",
        "commerce_provider": "medusa",
        "entry_page_type": blueprint.page_type,
    }

    # Build adapted pages list
    adapted_pages: list[dict[str, Any]] = [adapted_page]

    return AdapterResult(
        adapted_site=adapted_site,
        adapted_pages=adapted_pages,
        adapted_puck_data=puck_data,
        resolved_site_family=resolved_family,
        resolved_page_type=blueprint.page_type,
        resolved_template_id=blueprint.template_id,
    )
