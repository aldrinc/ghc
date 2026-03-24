#!/usr/bin/env python3
"""Sync Honest Herbalist products from mOS to local Medusa backend.

This script:
1. Logs into the local Medusa backend to obtain an admin JWT token
2. Finds the Honest Herbalist workspace with the most products
3. Syncs products from mOS to Medusa
4. Creates/updates the Medusa config for the workspace
5. Archives old rollout sites and creates a fresh medusa-b2b-starter site
6. Publishes the site using the canonical publish flow
7. Prints the real public runtime URL

Usage:
    python scripts/sync_honest_herbalist_to_medusa.py

Environment:
    DATABASE_URL: PostgreSQL connection string (default: postgresql://app:app@localhost:5433/app)
    MEDUSA_BASE_URL: Medusa backend URL (default: http://localhost:9000)
    MEDUSA_ADMIN_EMAIL: Medusa admin email (default: admin@test.com)
    MEDUSA_ADMIN_PASSWORD: Medusa admin password (default: supersecret)
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from sqlalchemy import func, select, update

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Client,
    ClientMedusaConfig,
    Funnel,
    FunnelPage,
    FunnelPageVersion,
    FunnelStatusEnum,
    FunnelPageVersionStatusEnum,
    FunnelPageVersionSourceEnum,
    Product,
    ProductVariant,
)
from app.db.enums import FunnelPublicationLinkKindEnum
from app.services.medusa_connection import (
    medusa_admin_login,
    medusa_create_product,
    medusa_create_variant,
    medusa_update_product_sales_channels,
    medusa_update_variant,
    upsert_client_medusa_config,
)
from app.services.medusa_catalog import _normalize_currency_code
from app.services.site_blueprints import MEDUSA_B2B_STARTER_BLUEPRINT
from app.services.funnel_templates import get_funnel_template, apply_template_assets
from app.services.design_systems import resolve_design_system_tokens
from app.services.funnels import (
    default_puck_data,
    rewrite_internal_target_ids,
    extract_internal_links,
)
from app.services.public_routing import require_product_route_slug


import re

# Configuration
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://app:app@localhost:5433/app",
)
MEDUSA_BASE_URL = os.environ.get("MEDUSA_BASE_URL", "http://localhost:9000")
MEDUSA_ADMIN_EMAIL = os.environ.get("MEDUSA_ADMIN_EMAIL", "admin@test.com")
MEDUSA_ADMIN_PASSWORD = os.environ.get("MEDUSA_ADMIN_PASSWORD", "supersecret")

# Honest Herbalist workspace name patterns
HONEST_HERBALIST_NAMES = [
    "honest herbalist",
    "the honest herbalist",
    "honest-herbalist",
    "thehonestherbalist",
]

# Site family for this rollout
SITE_FAMILY = "medusa-b2b-starter"


def slugify_title(title: str) -> str:
    """Convert a title to a URL-safe slug."""
    # Convert to lowercase
    slug = title.lower()
    # Replace non-alphanumeric characters with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    # Remove leading/trailing hyphens
    slug = slug.strip("-")
    # Limit length
    if len(slug) > 100:
        slug = slug[:100].rstrip("-")
    return slug or "product"


def find_honest_herbalist_client(session) -> Client | None:
    """Find the Honest Herbalist workspace with the most products.

    This deterministically selects the workspace with the richest product set,
    matching the logic used in earlier seed scripts.
    """
    clients = session.execute(select(Client)).scalars().all()

    # Filter to Honest Herbalist clients
    hh_clients = []
    for client in clients:
        name_lower = client.name.lower()
        if any(pattern in name_lower for pattern in HONEST_HERBALIST_NAMES):
            hh_clients.append(client)

    if not hh_clients:
        return None

    if len(hh_clients) == 1:
        return hh_clients[0]

    # Multiple matches: select the one with the most products
    best_client = None
    best_product_count = -1

    for client in hh_clients:
        product_count = (
            session.execute(select(func.count()).where(Product.client_id == client.id)).scalar()
            or 0
        )

        if product_count > best_product_count:
            best_product_count = product_count
            best_client = client

    return best_client


def find_handbook_product(session, client_id: str) -> Product | None:
    """Find the handbook product for the workspace, or fall back to first product."""
    products = (
        session.execute(
            select(Product).where(Product.client_id == client_id).order_by(Product.created_at)
        )
        .scalars()
        .all()
    )

    if not products:
        return None

    # Prefer handbook product
    for product in products:
        if "handbook" in product.title.lower():
            return product

    # Fall back to first product by created_at
    return products[0]


def get_or_create_publishable_key(base_url: str, admin_token: str) -> str:
    """Get or create a publishable API key for the Medusa backend."""
    import httpx

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}",
    }

    # Try to list existing publishable keys
    try:
        response = httpx.get(
            f"{base_url}/admin/api-keys",
            headers=headers,
            params={"type": "publishable"},
            timeout=30.0,
        )
        if response.status_code == 200:
            data = response.json()
            api_keys = data.get("api_keys", [])
            for key in api_keys:
                if key.get("type") == "publishable":
                    return key.get("token") or key.get("id")
    except Exception as e:
        print(f"Warning: Could not list publishable keys: {e}")

    # Try to create a new publishable key
    try:
        response = httpx.post(
            f"{base_url}/admin/api-keys",
            headers=headers,
            json={
                "title": "mOS Publishable Key",
                "type": "publishable",
            },
            timeout=30.0,
        )
        if response.status_code in (200, 201):
            data = response.json()
            return data.get("token") or data.get("api_key", {}).get("token")
    except Exception as e:
        print(f"Warning: Could not create publishable key: {e}")

    raise RuntimeError("Could not obtain a publishable API key for Medusa")


def get_default_sales_channel_id(base_url: str, admin_token: str) -> str:
    """Get the default sales channel ID from Medusa.

    Products must be associated with a sales channel to be visible in the Store API.
    """
    import httpx

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}",
    }

    try:
        response = httpx.get(
            f"{base_url}/admin/sales-channels",
            headers=headers,
            timeout=30.0,
        )
        if response.status_code == 200:
            data = response.json()
            sales_channels = data.get("sales_channels", [])
            if sales_channels:
                return sales_channels[0].get("id")
    except Exception as e:
        print(f"Warning: Could not list sales channels: {e}")

    raise RuntimeError("Could not obtain a sales channel ID from Medusa")


def ensure_usd_region(base_url: str, admin_token: str) -> str:
    """Ensure a USD region exists in Medusa for Honest Herbalist products.

    Returns the region ID.
    """
    import httpx

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}",
    }

    # Try to list existing regions
    try:
        response = httpx.get(
            f"{base_url}/admin/regions",
            headers=headers,
            timeout=30.0,
        )
        if response.status_code == 200:
            data = response.json()
            regions = data.get("regions", [])
            # Look for a USD region
            for region in regions:
                currency_code = region.get("currency_code", "")
                if currency_code.lower() == "usd":
                    print(f"Found existing USD region: {region.get('id')}")
                    return region.get("id")
                # Also accept EUR region as fallback for testing
                if currency_code.lower() == "eur":
                    print(f"Using existing EUR region as fallback: {region.get('id')}")
                    return region.get("id")
    except Exception as e:
        print(f"Warning: Could not list regions: {e}")

    # Try to create a USD region
    try:
        # First, get countries
        countries_response = httpx.get(
            f"{base_url}/admin/countries",
            headers=headers,
            timeout=30.0,
        )
        if countries_response.status_code != 200:
            print(f"Warning: Could not list countries: {countries_response.status_code}")
            # Try to create region without countries
            response = httpx.post(
                f"{base_url}/admin/regions",
                headers=headers,
                json={
                    "name": "United States",
                    "currency_code": "usd",
                },
                timeout=30.0,
            )
            if response.status_code in (200, 201):
                data = response.json()
                region = data.get("region", data)
                print(f"Created USD region without countries: {region.get('id')}")
                return region.get("id")
        else:
            countries = countries_response.json().get("countries", [])
            us_country = None
            for c in countries:
                if c.get("iso_2", "").lower() == "us":
                    us_country = c
                    break

            # Create the region
            region_data = {
                "name": "United States",
                "currency_code": "usd",
            }
            if us_country:
                region_data["countries"] = [{"iso_2": "us"}]

            response = httpx.post(
                f"{base_url}/admin/regions",
                headers=headers,
                json=region_data,
                timeout=30.0,
            )
            if response.status_code in (200, 201):
                data = response.json()
                region = data.get("region", data)
                print(f"Created USD region: {region.get('id')}")
                return region.get("id")
            else:
                print(
                    f"Warning: Could not create USD region: {response.status_code} - {response.text}"
                )
    except Exception as e:
        print(f"Warning: Could not create USD region: {e}")

    # Fallback: try to use any existing region
    try:
        response = httpx.get(
            f"{base_url}/admin/regions",
            headers=headers,
            timeout=30.0,
        )
        if response.status_code == 200:
            data = response.json()
            regions = data.get("regions", [])
            if regions:
                print(
                    f"Using fallback region: {regions[0].get('id')} ({regions[0].get('currency_code', 'unknown')})"
                )
                return regions[0].get("id")
    except Exception:
        pass

    raise RuntimeError("Could not obtain a region ID from Medusa")


def check_medusa_product_exists(base_url: str, admin_token: str, product_id: str) -> bool:
    """Check if a Medusa product exists."""
    import httpx

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}",
    }

    try:
        response = httpx.get(
            f"{base_url}/admin/products/{product_id}",
            headers=headers,
            timeout=30.0,
        )
        return response.status_code == 200
    except Exception:
        return False


def get_medusa_product_variants(base_url: str, admin_token: str, product_id: str) -> list[dict]:
    """Fetch all variants for a Medusa product."""
    import httpx

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}",
    }

    try:
        response = httpx.get(
            f"{base_url}/admin/products/{product_id}",
            headers=headers,
            timeout=30.0,
        )
        if response.status_code == 200:
            data = response.json()
            product = data.get("product", data)
            return product.get("variants", [])
    except Exception:
        pass

    return []


def sync_products_to_medusa(
    session,
    client: Client,
    base_url: str,
    admin_token: str,
    sales_channel_id: str | None = None,
    region_id: str | None = None,
) -> int:
    """Sync all products for a client to Medusa.

    This function:
    - Creates new products in Medusa for products without medusa_product_id
    - Generates handles for products that don't have them
    - Reconciles variants for already-synced products
    - Associates products with sales channel for Store API visibility
    - Creates region-specific prices for variants when region_id provided

    Returns the number of products synced.
    """
    products = (
        session.execute(select(Product).where(Product.client_id == client.id)).scalars().all()
    )

    if not products:
        print(f"No products found for client {client.name}")
        return 0

    print(f"Found {len(products)} products for {client.name}")

    synced_count = 0
    for product in products:
        try:
            # Generate handle if missing
            if not product.handle:
                generated_handle = slugify_title(product.title)
                product.handle = generated_handle
                session.add(product)
                print(f"  Generated handle for '{product.title}': {generated_handle}")

            # Get variants for this product
            variants = (
                session.execute(
                    select(ProductVariant).where(ProductVariant.product_id == product.id)
                )
                .scalars()
                .all()
            )

            if not variants:
                print(f"  Product '{product.title}' has no variants, skipping")
                continue

            # Check if product already has a Medusa ID
            if product.medusa_product_id:
                # Check if the Medusa product actually exists
                if check_medusa_product_exists(base_url, admin_token, product.medusa_product_id):
                    print(
                        f"  Product '{product.title}' already synced (Medusa ID: {product.medusa_product_id})"
                    )

                    # Reconcile variants for already-synced products
                    reconciled = reconcile_variants(
                        session=session,
                        product=product,
                        variants=variants,
                        base_url=base_url,
                        admin_token=admin_token,
                        sales_channel_id=sales_channel_id,
                        region_id=region_id,
                    )
                    print(f"    Reconciled {reconciled} variants")
                    synced_count += 1
                    continue
                else:
                    # Stale medusa_product_id - product doesn't exist in Medusa
                    print(
                        f"  Product '{product.title}' has stale Medusa ID ({product.medusa_product_id}), resyncing..."
                    )
                    product.medusa_product_id = None
                    session.add(product)

            # Create product in Medusa
            print(f"  Creating product '{product.title}' in Medusa...")

            # Build options from variant option_values
            option_values = variants[0].option_values if variants else None
            if option_values:
                options = [
                    {
                        "title": key,
                        "values": list(
                            set(
                                v.option_values.get(key)
                                for v in variants
                                if v.option_values and v.option_values.get(key)
                            )
                        ),
                    }
                    for key in option_values.keys()
                ]
            else:
                options = [{"title": "Variant", "values": [v.title for v in variants[:1]]}]

            medusa_product = medusa_create_product(
                base_url=base_url,
                api_key=admin_token,
                title=product.title,
                description=product.description or "",
                handle=product.handle,
                options=options,
                product_status="published" if product.published_at else "draft",
                sales_channel_ids=[sales_channel_id] if sales_channel_id else None,
            )

            medusa_product_id = medusa_product.get("id")
            if not medusa_product_id:
                print(f"    ERROR: No product ID returned")
                continue

            print(f"    Created product with ID: {medusa_product_id}")

            # Update product with Medusa ID
            product.medusa_product_id = medusa_product_id
            session.add(product)

            # Ensure product is associated with sales channel
            if sales_channel_id:
                try:
                    medusa_update_product_sales_channels(
                        base_url=base_url,
                        api_key=admin_token,
                        product_id=medusa_product_id,
                        sales_channel_ids=[sales_channel_id],
                    )
                except Exception as e:
                    print(f"    Warning: Could not associate product with sales channel: {e}")

            # Create variants in Medusa
            for variant in variants:
                try:
                    # Build variant options
                    variant_options = (
                        variant.option_values
                        if variant.option_values
                        else {"Variant": variant.title}
                    )

                    # Build prices - include both USD and EUR for broader region support
                    # USD is the primary currency from mOS, EUR is added for EU region support
                    usd_price = {
                        "amount": variant.price,
                        "currency_code": "usd",
                    }
                    # Convert USD to EUR at approximate rate (1 USD ≈ 0.92 EUR)
                    # For production, use actual exchange rates
                    eur_price = {
                        "amount": variant.price,  # Same price in cents for simplicity
                        "currency_code": "eur",
                    }
                    prices = [usd_price, eur_price]

                    # Build region_ids for region-specific pricing
                    # This ensures prices work with Medusa Store API for cart operations
                    region_ids = [region_id] if region_id else None

                    # Note: We don't pass inventory_quantity to avoid enabling inventory management.
                    # Inventory management requires proper stock location/fulfillment setup.
                    # For B2B storefronts, we typically disable inventory management.
                    medusa_variant = medusa_create_variant(
                        base_url=base_url,
                        api_key=admin_token,
                        product_id=medusa_product_id,
                        title=variant.title,
                        prices=prices,
                        sku=variant.sku,
                        barcode=variant.barcode,
                        options=variant_options,
                        region_ids=region_ids,
                    )

                    variant_id = medusa_variant.get("id")
                    if variant_id:
                        variant.provider = "medusa"
                        variant.external_price_id = variant_id
                        session.add(variant)
                        print(f"    Created variant '{variant.title}' with ID: {variant_id}")

                except Exception as e:
                    print(f"    ERROR creating variant '{variant.title}': {e}")

            synced_count += 1

        except Exception as e:
            print(f"  ERROR syncing product '{product.title}': {e}")

    return synced_count


def reconcile_variants(
    session,
    product: Product,
    variants: list,
    base_url: str,
    admin_token: str,
    sales_channel_id: str | None = None,
    region_id: str | None = None,
) -> int:
    """Reconcile variants for an already-synced product.

    This ensures local variants are properly linked to Medusa variants.
    Also ensures the product is associated with the sales channel.
    Creates region-specific prices when region_id provided.
    Returns the number of variants reconciled.
    """
    reconciled = 0

    # Ensure product has a Medusa ID
    if not product.medusa_product_id:
        return 0

    medusa_product_id = product.medusa_product_id

    # Ensure product is associated with sales channel
    if sales_channel_id:
        try:
            medusa_update_product_sales_channels(
                base_url=base_url,
                api_key=admin_token,
                product_id=medusa_product_id,
                sales_channel_ids=[sales_channel_id],
            )
        except Exception as e:
            print(f"      Warning: Could not update sales channel: {e}")

    # Fetch existing variants from Medusa
    existing_variants = get_medusa_product_variants(
        base_url=base_url,
        admin_token=admin_token,
        product_id=medusa_product_id,
    )

    # Build a map of existing variants by title and SKU
    existing_by_title = {v.get("title", "").lower(): v for v in existing_variants if v.get("title")}
    existing_by_sku = {v.get("sku", "").lower(): v for v in existing_variants if v.get("sku")}

    for variant in variants:
        # Skip variants that are already Medusa-backed with a valid external_price_id
        if variant.provider == "medusa" and variant.external_price_id:
            # Verify the variant still exists in Medusa
            variant_exists = any(
                v.get("id") == variant.external_price_id for v in existing_variants
            )
            if variant_exists:
                # If region_id provided, check if existing variant prices need updating
                if region_id:
                    existing_variant = None
                    for v in existing_variants:
                        if v.get("id") == variant.external_price_id:
                            existing_variant = v
                            break
                    if existing_variant:
                        existing_prices = existing_variant.get("prices", [])
                        # Check if any price has region_id
                        has_region_price = any(
                            p.get("region_id") == region_id for p in existing_prices
                        )
                        if not has_region_price:
                            # Add region-specific prices to existing variant
                            try:
                                usd_price = {
                                    "amount": variant.price,
                                    "currency_code": "usd",
                                    "region_id": region_id,
                                }
                                eur_price = {
                                    "amount": variant.price,
                                    "currency_code": "eur",
                                    "region_id": region_id,
                                }
                                new_prices = existing_prices + [usd_price, eur_price]
                                medusa_update_variant(
                                    base_url=base_url,
                                    api_key=admin_token,
                                    product_id=medusa_product_id,
                                    variant_id=variant.external_price_id,
                                    fields={"prices": new_prices},
                                )
                                reconciled += 1
                                print(
                                    f"      Updated prices for variant '{variant.title}' with region_id"
                                )
                            except Exception as e:
                                print(
                                    f"      Warning: Could not update prices for '{variant.title}': {e}"
                                )
                continue

        try:
            # Try to find matching existing variant
            existing_variant = None
            variant_title_lower = variant.title.lower() if variant.title else ""
            variant_sku_lower = variant.sku.lower() if variant.sku else ""

            # Match by SKU first (more reliable)
            if variant_sku_lower and variant_sku_lower in existing_by_sku:
                existing_variant = existing_by_sku[variant_sku_lower]
            # Then by title
            elif variant_title_lower and variant_title_lower in existing_by_title:
                existing_variant = existing_by_title[variant_title_lower]

            if existing_variant:
                # Link local variant to existing Medusa variant
                variant_id = existing_variant.get("id")
                if variant_id:
                    variant.provider = "medusa"
                    variant.external_price_id = variant_id
                    session.add(variant)
                    reconciled += 1
                    print(
                        f"      Linked variant '{variant.title}' to existing Medusa variant {variant_id}"
                    )
                continue

            # No matching variant found, create new one
            # Build variant options
            variant_options = (
                variant.option_values if variant.option_values else {"Variant": variant.title}
            )

            # Build prices - include both USD and EUR for broader region support
            usd_price = {
                "amount": variant.price,
                "currency_code": "usd",
            }
            eur_price = {
                "amount": variant.price,  # Same price in cents for simplicity
                "currency_code": "eur",
            }
            prices = [usd_price, eur_price]

            # Build region_ids for region-specific pricing
            region_ids = [region_id] if region_id else None

            # Create variant in Medusa
            # Note: We don't pass inventory_quantity to avoid enabling inventory management.
            medusa_variant = medusa_create_variant(
                base_url=base_url,
                api_key=admin_token,
                product_id=medusa_product_id,
                title=variant.title,
                prices=prices,
                sku=variant.sku,
                barcode=variant.barcode,
                options=variant_options,
                region_ids=region_ids,
            )

            variant_id = medusa_variant.get("id")
            if variant_id:
                variant.provider = "medusa"
                variant.external_price_id = variant_id
                session.add(variant)
                reconciled += 1
                print(f"      Created variant '{variant.title}' with ID: {variant_id}")

        except Exception as e:
            # Check if it's a "variant already exists" error
            error_msg = str(e)
            if "already exists" in error_msg.lower():
                # Try to find and link the existing variant
                print(f"      Variant '{variant.title}' already exists, attempting to link...")
                # Refresh the list and try again
                existing_variants = get_medusa_product_variants(
                    base_url=base_url,
                    admin_token=admin_token,
                    product_id=medusa_product_id,
                )
                for ev in existing_variants:
                    if ev.get("title", "").lower() == variant.title.lower():
                        variant.provider = "medusa"
                        variant.external_price_id = ev.get("id")
                        session.add(variant)
                        reconciled += 1
                        print(
                            f"      Linked variant '{variant.title}' to existing Medusa variant {ev.get('id')}"
                        )
                        break
            else:
                print(f"      ERROR reconciling variant '{variant.title}': {e}")

    return reconciled


def archive_old_sites(session, org_id: str, client_id: str, site_family: str):
    """Archive existing sites for this workspace/family to ensure fresh state."""
    existing_sites = (
        session.execute(
            select(Funnel).where(
                Funnel.org_id == uuid.UUID(org_id),
                Funnel.client_id == uuid.UUID(client_id),
                Funnel.site_family == site_family,
            )
        )
        .scalars()
        .all()
    )

    for site in existing_sites:
        print(f"  Archiving existing site '{site.name}' (ID: {site.id})")
        site.status = FunnelStatusEnum.archived
        # Clear active publication to prevent archived sites from being served
        site.active_publication_id = None
        session.add(site)

    if existing_sites:
        session.flush()
        print(f"  Archived {len(existing_sites)} existing site(s)")


def create_fresh_site(
    session,
    org_id: str,
    client_id: str,
    product: Product,
    site_family: str = SITE_FAMILY,
    site_name: str = "Honest Herbalist Store",
) -> str:
    """Create a fresh site for the workspace.

    Returns the site (funnel) ID.
    """
    print(f"Creating fresh site '{site_name}'...")

    # Resolve design system tokens
    design_system_tokens = resolve_design_system_tokens(
        session=session,
        org_id=org_id,
        client_id=client_id,
    )

    # Generate unique route slug
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    route_slug = f"{site_family}-{suffix}"

    # Create the funnel row
    site_funnel = Funnel(
        org_id=uuid.UUID(org_id),
        client_id=uuid.UUID(client_id),
        name=site_name,
        description=f"{site_family} site",
        status=FunnelStatusEnum.draft,
        route_slug=route_slug,
        experience_kind="site",
        site_type=MEDUSA_B2B_STARTER_BLUEPRINT.site_type,
        site_family=site_family,
        commerce_provider=MEDUSA_B2B_STARTER_BLUEPRINT.commerce_provider,
        product_id=product.id,
    )
    session.add(site_funnel)
    session.flush()

    # Create pages from blueprints
    page_id_map = {}
    entry_page_id = None

    # Placeholder page IDs for link rewriting
    PAGE_TYPE_PLACEHOLDERS = {
        "home": "__PAGE_HOME__",
        "category": "__PAGE_CATEGORY__",
        "product_detail": "__PAGE_PRODUCT_DETAIL__",
        "cart": "__PAGE_CART__",
        "checkout": "__PAGE_CHECKOUT__",
    }

    for blueprint in MEDUSA_B2B_STARTER_BLUEPRINT.page_blueprints:
        # Get the template for this page
        template = get_funnel_template(blueprint.template_id)
        if template:
            try:
                template_puck_data = apply_template_assets(
                    session=session,
                    org_id=org_id,
                    client_id=client_id,
                    template=template,
                    design_system_tokens=design_system_tokens,
                )
            except ValueError:
                template_puck_data = default_puck_data()
        else:
            template_puck_data = default_puck_data()

        # Create the page
        page = FunnelPage(
            funnel_id=site_funnel.id,
            name=blueprint.name,
            slug=blueprint.slug,
            ordering=blueprint.ordering,
            template_id=blueprint.template_id,
            page_type=blueprint.page_type,
        )
        session.add(page)
        session.flush()

        # Track page ID for link rewriting
        page_id_map[blueprint.page_type] = str(page.id)

        # Create the initial draft version
        version = FunnelPageVersion(
            page_id=page.id,
            status=FunnelPageVersionStatusEnum.draft,
            puck_data=template_puck_data,
            source=FunnelPageVersionSourceEnum.human,
            created_at=datetime.now(timezone.utc),
        )
        session.add(version)
        session.flush()

        # Track entry page
        if blueprint.is_entry:
            entry_page_id = str(page.id)

    # Build placeholder-to-real-ID mapping for link rewriting
    placeholder_id_map = {
        PAGE_TYPE_PLACEHOLDERS[page_type]: real_id
        for page_type, real_id in page_id_map.items()
        if page_type in PAGE_TYPE_PLACEHOLDERS
    }

    # Rewrite internal links in all page puck_data
    for page_type, page_id_str in page_id_map.items():
        page_id = uuid.UUID(page_id_str)
        page = session.execute(select(FunnelPage).where(FunnelPage.id == page_id)).scalars().first()

        if not page:
            continue

        version = (
            session.execute(
                select(FunnelPageVersion)
                .where(
                    FunnelPageVersion.page_id == page_id,
                    FunnelPageVersion.status == FunnelPageVersionStatusEnum.draft,
                )
                .order_by(FunnelPageVersion.created_at.desc())
            )
            .scalars()
            .first()
        )

        if not version:
            continue

        # Rewrite placeholder IDs to real page IDs
        rewritten_puck_data = rewrite_internal_target_ids(version.puck_data, placeholder_id_map)
        version.puck_data = rewritten_puck_data
        session.add(version)

    # Set entry page
    if entry_page_id:
        site_funnel.entry_page_id = entry_page_id
        session.add(site_funnel)

    session.flush()

    print(f"Created site '{site_funnel.name}' (ID: {site_funnel.id})")
    return str(site_funnel.id)


def publish_site_canonical(session, org_id: str, site_id: str) -> str:
    """Publish a site using the canonical publish flow.

    This creates a FunnelPublication and sets active_publication_id.

    Returns the public runtime URL.
    """
    from app.db.models import FunnelPublication, FunnelPublicationPage, FunnelPublicationLink

    site_funnel = (
        session.execute(select(Funnel).where(Funnel.id == uuid.UUID(site_id))).scalars().first()
    )

    if not site_funnel:
        raise ValueError(f"Site {site_id} not found")

    # Get all pages
    pages = list(
        session.execute(
            select(FunnelPage)
            .where(FunnelPage.funnel_id == site_funnel.id)
            .order_by(FunnelPage.ordering.asc(), FunnelPage.created_at.asc())
        )
        .scalars()
        .all()
    )

    if not pages:
        raise ValueError("Site has no pages")

    if not site_funnel.entry_page_id:
        raise ValueError("Site has no entry page")

    # Get the draft/approved version for each page
    version_by_page = {}
    for page in pages:
        draft = (
            session.execute(
                select(FunnelPageVersion)
                .where(
                    FunnelPageVersion.page_id == page.id,
                    FunnelPageVersion.status == FunnelPageVersionStatusEnum.draft,
                )
                .order_by(FunnelPageVersion.created_at.desc(), FunnelPageVersion.id.desc())
            )
            .scalars()
            .first()
        )

        approved = (
            session.execute(
                select(FunnelPageVersion)
                .where(
                    FunnelPageVersion.page_id == page.id,
                    FunnelPageVersion.status == FunnelPageVersionStatusEnum.approved,
                )
                .order_by(FunnelPageVersion.created_at.desc(), FunnelPageVersion.id.desc())
            )
            .scalars()
            .first()
        )

        version = draft or approved
        if not version:
            raise ValueError(f"Page '{page.name}' has no saved version to publish")

        version_by_page[str(page.id)] = version

    # Create the publication
    publication = FunnelPublication(
        funnel_id=site_funnel.id,
        entry_page_id=site_funnel.entry_page_id,
        created_by="sync_script",
    )
    session.add(publication)
    session.flush()

    # Create publication pages
    page_id_set = {str(page.id) for page in pages}
    for page in pages:
        version = version_by_page[str(page.id)]
        session.add(
            FunnelPublicationPage(
                publication_id=publication.id,
                page_id=page.id,
                page_version_id=version.id,
                slug_at_publish=page.slug,
                title_at_publish=page.name,
                description_at_publish=None,
            )
        )

    # Extract and create publication links
    for page in pages:
        version = version_by_page[str(page.id)]
        for link in extract_internal_links(version.puck_data):
            if link.to_page_id not in page_id_set:
                continue  # Skip invalid links
            session.add(
                FunnelPublicationLink(
                    publication_id=publication.id,
                    from_page_id=str(page.id),
                    to_page_id=link.to_page_id,
                    kind=FunnelPublicationLinkKindEnum.cta,
                    label=link.label,
                    meta=link.meta or {},
                )
            )

    # Set active publication and status
    site_funnel.active_publication_id = publication.id
    site_funnel.status = FunnelStatusEnum.published
    session.add(site_funnel)

    session.commit()

    # Build public URL
    # Get product for route slug
    product = (
        session.execute(select(Product).where(Product.id == site_funnel.product_id))
        .scalars()
        .first()
    )

    # Public URL format: /f/{product_short_slug}/{funnel_slug}/{page_slug}
    product_short_slug = require_product_route_slug(product=product) if product else "product"
    funnel_slug = site_funnel.route_slug

    # Get entry page slug
    entry_page = (
        session.execute(select(FunnelPage).where(FunnelPage.id == site_funnel.entry_page_id))
        .scalars()
        .first()
    )

    entry_slug = entry_page.slug if entry_page else "home"

    public_url = f"/f/{product_short_slug}/{funnel_slug}/{entry_slug}"

    return public_url


def main():
    """Main entry point."""
    print("=" * 60)
    print("Sync Honest Herbalist Products to Medusa")
    print("=" * 60)
    print()

    # Connect to mOS database
    print(f"Connecting to mOS database...")
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Find Honest Herbalist client with most products
        print(f"Looking for Honest Herbalist workspace...")
        client = find_honest_herbalist_client(session)
        if not client:
            print("ERROR: Could not find Honest Herbalist workspace")
            print("Available clients:")
            for c in session.execute(select(Client)).scalars().all():
                product_count = (
                    session.execute(select(func.count()).where(Product.client_id == c.id)).scalar()
                    or 0
                )
                print(f"  - {c.name} (ID: {c.id}, Products: {product_count})")
            sys.exit(1)

        # Get product count for selected client
        product_count = (
            session.execute(select(func.count()).where(Product.client_id == client.id)).scalar()
            or 0
        )

        print(f"Found workspace: {client.name} (ID: {client.id})")
        print(f"Org ID: {client.org_id}")
        print(f"Products: {product_count}")
        print()

        # Find the handbook product (preferred) or first product
        product = find_handbook_product(session, str(client.id))
        if not product:
            print("ERROR: No products found in workspace")
            sys.exit(1)

        print(f"Using product: {product.title} (ID: {product.id})")
        if "handbook" in product.title.lower():
            print("  (Handbook product - preferred for storefront review)")
        print()

        # Login to Medusa
        print(f"Logging into Medusa at {MEDUSA_BASE_URL}...")
        admin_token_result = medusa_admin_login(
            base_url=MEDUSA_BASE_URL,
            email=MEDUSA_ADMIN_EMAIL,
            password=MEDUSA_ADMIN_PASSWORD,
        )
        print(f"Obtained admin token (user: {admin_token_result.user_id})")
        print()

        # Get or create publishable key
        print("Getting publishable API key...")
        publishable_key = get_or_create_publishable_key(MEDUSA_BASE_URL, admin_token_result.token)
        print(f"Publishable key: {publishable_key[:20]}...")
        print()

        # Get default sales channel ID (required for products to be visible in Store API)
        print("Getting default sales channel...")
        sales_channel_id = get_default_sales_channel_id(MEDUSA_BASE_URL, admin_token_result.token)
        print(f"Sales channel ID: {sales_channel_id}")
        print()

        # Ensure USD region exists (required for cart creation and pricing)
        print("Ensuring USD region exists...")
        region_id = ensure_usd_region(MEDUSA_BASE_URL, admin_token_result.token)
        print(f"Region ID: {region_id}")
        print()

        # Update or create Medusa config
        print("Updating Medusa config for workspace...")
        medusa_config = upsert_client_medusa_config(
            session=session,
            org_id=str(client.org_id),
            client_id=str(client.id),
            base_url=MEDUSA_BASE_URL,
            admin_api_key=admin_token_result.token,
            publishable_key=publishable_key,
        )
        medusa_config.connection_status = "connected"
        medusa_config.last_connection_check_at = datetime.now(timezone.utc)
        session.add(medusa_config)
        session.commit()
        print(f"Medusa config saved (status: {medusa_config.connection_status})")
        print()

        # Sync products
        print("Syncing products to Medusa...")
        synced = sync_products_to_medusa(
            session=session,
            client=client,
            base_url=MEDUSA_BASE_URL,
            admin_token=admin_token_result.token,
            sales_channel_id=sales_channel_id,
            region_id=region_id,
        )
        session.commit()
        print(f"Synced {synced} products")
        print()

        # Archive old sites and create fresh one
        print("Archiving old rollout sites...")
        archive_old_sites(
            session=session,
            org_id=str(client.org_id),
            client_id=str(client.id),
            site_family=SITE_FAMILY,
        )
        print()

        # Create fresh site
        print("Creating fresh medusa-b2b-starter site...")
        site_id = create_fresh_site(
            session=session,
            org_id=str(client.org_id),
            client_id=str(client.id),
            product=product,
            site_family=SITE_FAMILY,
            site_name=f"{client.name} Store",
        )
        print()

        # Publish site using canonical flow
        print("Publishing site using canonical flow...")
        public_url = publish_site_canonical(
            session=session,
            org_id=str(client.org_id),
            site_id=site_id,
        )
        print()

        # Verify publication
        print("Verifying publication...")
        site_funnel = (
            session.execute(select(Funnel).where(Funnel.id == uuid.UUID(site_id))).scalars().first()
        )

        if site_funnel and site_funnel.active_publication_id:
            print(f"  active_publication_id: {site_funnel.active_publication_id}")
            print(f"  status: {site_funnel.status}")
        else:
            print("  WARNING: active_publication_id is NULL!")
        print()

        print("=" * 60)
        print("Sync complete!")
        print("=" * 60)
        print()
        print(f"Medusa backend: {MEDUSA_BASE_URL}")
        print(f"Publishable key: {publishable_key[:20]}...")
        print(f"Workspace: {client.name} (ID: {client.id})")
        print(f"Site ID: {site_id}")
        print()
        print(f"Public URL: {public_url}")
        print()
        print("To view the site, start the mOS frontend and navigate to the URL above.")
        print("=" * 60)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
