"""
Template hydration service for storefront templates.

Materializes built-in template assets and applies product/variant context
to template puckData for created drafts.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from app.db.models import Product, ProductVariant
from app.services.funnel_templates import FunnelTemplate, apply_template_assets
from sqlalchemy.orm import Session


def hydrate_template_puckdata(
    puck_data: dict[str, Any],
    product: Product,
    variant: ProductVariant | None,
) -> dict[str, Any]:
    """
    Hydrate template puckData with product/variant context.

    Replaces hardcoded PuppyPad-specific content with actual product data
    while preserving template structure.

    Args:
        puck_data: The template puckData to hydrate.
        product: The selected product.
        variant: The selected variant (may be None for some templates).

    Returns:
        Hydrated puckData with product context applied.
    """
    result = deepcopy(puck_data)

    # Get product info
    product_title = product.title or "Product"
    product_description = product.description or ""

    # Get variant info
    variant_title = variant.title if variant else None
    variant_price = None
    variant_compare_at_price = None
    variant_currency = None

    if variant:
        if variant.price is not None:
            variant_price = variant.price
        if variant.compare_at_price is not None:
            variant_compare_at_price = variant.compare_at_price
        variant_currency = variant.currency or "usd"

    # Extract product benefits/features if available
    primary_benefits = []
    feature_bullets = []
    if hasattr(product, "primary_benefits") and product.primary_benefits:
        primary_benefits = (
            list(product.primary_benefits) if isinstance(product.primary_benefits, list) else []
        )
    if hasattr(product, "feature_bullets") and product.feature_bullets:
        feature_bullets = (
            list(product.feature_bullets) if isinstance(product.feature_bullets, list) else []
        )

    # Walk and replace product-specific content
    def walk(node: Any, path: Any = None) -> None:
        if path is None:
            path = []
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if isinstance(value, str):
                    # Replace PuppyPad references with product title
                    if "PuppyPad" in value:
                        node[key] = value.replace("PuppyPad", product_title)
                    elif "puppypad" in value.lower():
                        # Handle lowercase references
                        node[key] = re.sub(
                            r"puppypad", product_title.lower(), value, flags=re.IGNORECASE
                        )
                elif isinstance(value, dict):
                    # Handle specific known template structures
                    if key == "purchase" and "title" in value:
                        # Update purchase section title
                        walk(value, path + [key])
                    elif key == "offer" and "options" in value:
                        # Update offer options with variant pricing
                        walk(value, path + [key])
                    elif key == "hero" and "title" in value:
                        # Update hero title
                        walk(value, path + [key])
                    else:
                        walk(value, path + [key])
                elif isinstance(value, list):
                    for item in value:
                        walk(item, path + [key])
        elif isinstance(node, list):
            for item in node:
                walk(item, path)

    walk(result)

    # Apply specific updates for known template structures
    _apply_hero_updates(result, product_title, product_description, primary_benefits)
    _apply_purchase_updates(result, product_title, variant, product)
    _apply_offer_updates(result, product_title, variant, product)
    _apply_marquee_updates(result, product_title, primary_benefits, feature_bullets)
    _apply_story_updates(
        result, product_title, product_description, primary_benefits, feature_bullets
    )
    _apply_pitch_updates(
        result, product_title, product_description, primary_benefits, feature_bullets
    )
    _apply_footer_updates(result, product_title)

    return result


def _apply_hero_updates(
    puck_data: dict[str, Any],
    product_title: str,
    product_description: str,
    primary_benefits: list[str],
) -> None:
    """Update hero section with product context."""
    content = puck_data.get("content", [])
    for block in content:
        if block.get("type") == "SalesPdpPage":
            for child in block.get("props", {}).get("content", []):
                if child.get("type") == "SalesPdpHero":
                    config = child.get("props", {}).get("config", {})
                    purchase = config.get("purchase", {})

                    # Update title
                    if "title" in purchase:
                        purchase["title"] = product_title

                    # Update benefits if we have them
                    if primary_benefits and "benefits" in purchase:
                        benefits = purchase.get("benefits", [])
                        for i, benefit in enumerate(benefits[: len(primary_benefits)]):
                            if i < len(primary_benefits):
                                benefit["text"] = primary_benefits[i]

                elif child.get("type") == "PreSalesHero":
                    config = child.get("props", {}).get("config", {})
                    hero = config.get("hero", {})

                    # Update hero title for pre-sales
                    if "title" in hero:
                        # Replace generic product references
                        hero["title"] = product_title
                    if "subtitle" in hero and product_description:
                        hero["subtitle"] = product_description


def _apply_purchase_updates(
    puck_data: dict[str, Any],
    product_title: str,
    variant: ProductVariant | None,
    product: Product,
) -> None:
    """Update purchase section with variant context."""
    content = puck_data.get("content", [])
    for block in content:
        if block.get("type") == "SalesPdpPage":
            for child in block.get("props", {}).get("content", []):
                if child.get("type") == "SalesPdpHero":
                    config = child.get("props", {}).get("config", {})
                    purchase = config.get("purchase", {})

                    # Update size options if variant has option_values
                    if variant:
                        size_config = purchase.get("size", {})
                        color_config = purchase.get("color", {})
                        option_values = (
                            variant.option_values if isinstance(variant.option_values, dict) else {}
                        )
                        size_value = option_values.get("size") or option_values.get("Size")
                        color_value = (
                            option_values.get("color")
                            or option_values.get("Color")
                            or option_values.get("colour")
                            or option_values.get("Colour")
                        )

                        if isinstance(size_config, dict):
                            size_config["title"] = "Selected option"
                            size_config["helpLinkLabel"] = ""
                            size_config["shippingDelayLabel"] = ""
                            size_config["options"] = [
                                {
                                    "id": "selected-size",
                                    "label": str(size_value or variant.title or product.title),
                                    "sizeIn": "",
                                    "sizeCm": "",
                                }
                            ]

                        if isinstance(color_config, dict):
                            color_config["title"] = "Variant details"
                            color_config["outOfStockTitle"] = ""
                            color_config["outOfStockBody"] = ""
                            color_config["options"] = (
                                [{"id": "selected-color", "label": str(color_value)}]
                                if color_value
                                else []
                            )


def _apply_offer_updates(
    puck_data: dict[str, Any],
    product_title: str,
    variant: ProductVariant | None,
    product: Product,
) -> None:
    """Update offer section with pricing context."""
    if not variant:
        return

    content = puck_data.get("content", [])
    for block in content:
        if block.get("type") == "SalesPdpPage":
            for child in block.get("props", {}).get("content", []):
                if child.get("type") == "SalesPdpHero":
                    config = child.get("props", {}).get("config", {})
                    purchase = config.get("purchase", {})
                    offer = purchase.get("offer", {})

                    if isinstance(offer, dict):
                        original_options = (
                            offer.get("options") if isinstance(offer.get("options"), list) else []
                        )
                        first_image = None
                        if original_options and isinstance(original_options[0], dict):
                            first_image = deepcopy(original_options[0].get("image"))
                        offer["title"] = "Selected offer"
                        offer["helperText"] = ""
                        offer["seeWhyLabel"] = ""
                        offer["options"] = [
                            {
                                "id": str(variant.id),
                                "title": variant.title or product_title,
                                "image": first_image or {"src": "", "alt": product_title},
                                "price": (variant.price or 0) / 100,
                                "compareAt": (variant.compare_at_price or 0) / 100,
                                "saveLabel": "",
                            }
                        ]


def _apply_marquee_updates(
    puck_data: dict[str, Any],
    product_title: str,
    primary_benefits: list[str],
    feature_bullets: list[str],
) -> None:
    """Update marquee section with product context."""
    # Combine benefits and features for marquee items
    marquee_items = []
    if primary_benefits:
        marquee_items.extend(primary_benefits[:4])
    if feature_bullets:
        # Extract short feature descriptions
        for bullet in feature_bullets[:4]:
            if isinstance(bullet, str) and len(bullet) < 50:
                marquee_items.append(bullet.upper())

    content = puck_data.get("content", [])
    for block in content:
        if block.get("type") == "SalesPdpPage":
            for child in block.get("props", {}).get("content", []):
                if child.get("type") == "SalesPdpMarquee":
                    config = child.get("props", {}).get("config", {})
                    if "items" in config and marquee_items:
                        config["items"] = marquee_items[: max(1, min(len(marquee_items), 6))]


def _apply_story_updates(
    puck_data: dict[str, Any],
    product_title: str,
    product_description: str,
    primary_benefits: list[str],
    feature_bullets: list[str],
) -> None:
    """Update story/problem/solution sections with product context."""
    content = puck_data.get("content", [])
    for block in content:
        if block.get("type") == "SalesPdpPage":
            for child in block.get("props", {}).get("content", []):
                if child.get("type") == "SalesPdpStorySolution":
                    config = child.get("props", {}).get("config", {})
                    # Update solution title
                    if "title" in config:
                        config["title"] = product_title
                    # Update callout
                    if "callout" in config:
                        callout = config["callout"]
                        if "rightBody" in callout:
                            callout["rightBody"] = callout["rightBody"].replace(
                                "PuppyPad", product_title
                            )
                    # Update bullets
                    if "bullets" in config:
                        for bullet in config["bullets"]:
                            if "body" in bullet:
                                bullet["body"] = bullet["body"].replace("PuppyPad", product_title)

                elif child.get("type") == "SalesPdpComparison":
                    config = child.get("props", {}).get("config", {})
                    # Update comparison columns
                    if "columns" in config:
                        columns = config["columns"]
                        if "pup" in columns:
                            columns["pup"] = columns["pup"].replace(
                                "PUPPYPAD", product_title.upper()
                            )


def _apply_pitch_updates(
    puck_data: dict[str, Any],
    product_title: str,
    product_description: str,
    primary_benefits: list[str],
    feature_bullets: list[str],
) -> None:
    """Update pitch section with product context."""
    content = puck_data.get("content", [])
    for block in content:
        if block.get("type") == "PreSalesPage":
            for child in block.get("props", {}).get("content", []):
                if child.get("type") == "PreSalesPitch":
                    config = child.get("props", {}).get("config", {})
                    # Update title
                    if "title" in config:
                        config["title"] = product_title
                    if "bullets" in config:
                        replacement_bullets = feature_bullets[:3] or primary_benefits[:3]
                        if product_description and not replacement_bullets:
                            replacement_bullets = [product_description]
                        if replacement_bullets:
                            config["bullets"] = replacement_bullets


def _apply_footer_updates(
    puck_data: dict[str, Any],
    product_title: str,
) -> None:
    """Update footer section with product context."""
    content = puck_data.get("content", [])
    for block in content:
        if block.get("type") == "SalesPdpPage":
            for child in block.get("props", {}).get("content", []):
                if child.get("type") == "SalesPdpFooter":
                    config = child.get("props", {}).get("config", {})
                    if "logo" in config:
                        logo = config["logo"]
                        if "alt" in logo:
                            logo["alt"] = logo["alt"].replace("PuppyPad", product_title)
                    if "copyright" in config:
                        # Update copyright year
                        import datetime

                        config["copyright"] = f"© {datetime.datetime.now().year} {product_title}"


def materialize_template_assets(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    template: FunnelTemplate,
    puck_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Materialize template assets by uploading them and replacing paths with asset public IDs.

    Args:
        session: Database session.
        org_id: Organization ID.
        client_id: Client/workspace ID.
        template: The funnel template with asset base path.
        puck_data: The puckData to process.

    Returns:
        PuckData with asset paths replaced by asset public IDs.
    """
    hydrated_template = FunnelTemplate(
        template_id=template.template_id,
        name=template.name,
        description=template.description,
        preview_image=template.preview_image,
        category=template.category,
        puck_data=deepcopy(puck_data),
        asset_base_path=template.asset_base_path,
        asset_prefix=template.asset_prefix,
    )
    return apply_template_assets(
        session=session,
        org_id=org_id,
        client_id=client_id,
        template=hydrated_template,
        design_system_tokens=None,
    )
