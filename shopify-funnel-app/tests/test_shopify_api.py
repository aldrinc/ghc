from __future__ import annotations

import asyncio
import json

import pytest

from app.shopify_api import ShopifyApiClient, ShopifyApiError

_THEME_SYNC_REQUIRED_CSS_VARS = {
    "--color-page-bg": "#f5f5f5",
    "--color-bg": "#ffffff",
    "--color-text": "#222222",
    "--color-muted": "rgba(34, 34, 34, 0.72)",
    "--color-brand": "#123456",
    "--color-cta": "#0a8f3c",
    "--color-cta-text": "#ffffff",
    "--color-border": "rgba(0, 0, 0, 0.2)",
    "--color-soft": "rgba(0, 0, 0, 0.08)",
    "--focus-outline-color": "rgba(6, 26, 112, 0.35)",
    "--font-sans": "Inter, sans-serif",
    "--font-heading": "Merriweather, serif",
    "--line": "1.2",
    "--heading-line": "1.0",
    "--hero-title-letter-spacing": "-0.03em",
    "--text-sm": "16px",
    "--text-base": "15px",
    "--cta-font-size-md": "18px",
    "--radius-md": "14px",
    "--container-max": "1380px",
    "--container-pad": "24px",
    "--section-pad-y": "120px",
    "--footer-bg": "#f4ede6",
}


def _build_minimal_theme_settings_json(*, extra_current: dict[str, object] | None = None) -> str:
    current: dict[str, object] = {
        "color_background": "#ffffff",
        "color_foreground": "#111111",
        "color_button": "#000000",
        "color_button_text": "#ffffff",
        "color_link": "#000000",
        "color_accent": "#000000",
        "footer_background": "#ffffff",
        "footer_text": "#111111",
        "color_schemes": [
            {
                "settings": {
                    "background": "#ffffff",
                    "text": "#111111",
                    "button": "#000000",
                    "button_label": "#ffffff",
                    "secondary_button": "#eeeeee",
                    "secondary_button_label": "#111111",
                    "highlight": "rgba(0, 0, 0, 0.08)",
                    "keyboard_focus": "rgba(6, 26, 112, 0.35)",
                    "shadow": "rgba(34, 34, 34, 0.72)",
                    "image_background": "#ffffff",
                }
            }
        ],
    }
    if extra_current:
        current.update(extra_current)
    return json.dumps({"current": current}) + "\n"


def test_register_webhook_reuses_existing_subscription_when_address_taken():
    client = ShopifyApiClient()
    created_payloads: list[dict] = []
    callback_url = "https://example.ngrok.app/webhooks/app/uninstalled"

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        created_payloads.append(payload)
        if "mutation webhookSubscriptionCreate" in payload.get("query", ""):
            return {
                "webhookSubscriptionCreate": {
                    "webhookSubscription": None,
                    "userErrors": [{"message": "Address for this topic has already been taken"}],
                }
            }
        return {
            "webhookSubscriptions": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/WebhookSubscription/123",
                            "endpoint": {
                                "__typename": "WebhookHttpEndpoint",
                                "callbackUrl": callback_url,
                            },
                        }
                    }
                ]
            }
        }

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.register_webhook(
            shop_domain="example.myshopify.com",
            access_token="token",
            topic="APP_UNINSTALLED",
            callback_url=callback_url,
        )
    )

    assert result == "gid://shopify/WebhookSubscription/123"
    assert len(created_payloads) == 2


def test_register_webhook_duplicate_error_without_existing_subscription_raises():
    client = ShopifyApiClient()

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        if "mutation webhookSubscriptionCreate" in payload.get("query", ""):
            return {
                "webhookSubscriptionCreate": {
                    "webhookSubscription": None,
                    "userErrors": [{"message": "Address for this topic has already been taken"}],
                }
            }
        return {"webhookSubscriptions": {"edges": []}}

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    with pytest.raises(ShopifyApiError, match="Webhook registration failed for APP_UNINSTALLED"):
        asyncio.run(
            client.register_webhook(
                shop_domain="example.myshopify.com",
                access_token="token",
                topic="APP_UNINSTALLED",
                callback_url="https://example.ngrok.app/webhooks/app/uninstalled",
            )
        )


def test_verify_product_exists_returns_product_payload():
    client = ShopifyApiClient()

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        return {
            "product": {
                "id": "gid://shopify/Product/123",
                "title": "Verified Product",
                "handle": "verified-product",
            }
        }

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.verify_product_exists(
            shop_domain="example.myshopify.com",
            access_token="token",
            product_gid="gid://shopify/Product/123",
        )
    )

    assert result["id"] == "gid://shopify/Product/123"
    assert result["title"] == "Verified Product"
    assert result["handle"] == "verified-product"


def test_verify_product_exists_raises_not_found_when_missing():
    client = ShopifyApiClient()

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        return {"product": None}

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    with pytest.raises(ShopifyApiError, match="Product not found for GID"):
        asyncio.run(
            client.verify_product_exists(
                shop_domain="example.myshopify.com",
                access_token="token",
                product_gid="gid://shopify/Product/123",
            )
        )


def test_list_products_returns_summary_rows():
    client = ShopifyApiClient()

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        return {
            "products": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/Product/100",
                            "title": "Alpha",
                            "handle": "alpha",
                            "status": "ACTIVE",
                        }
                    },
                    {
                        "node": {
                            "id": "gid://shopify/Product/200",
                            "title": "Beta",
                            "handle": "beta",
                            "status": "DRAFT",
                        }
                    },
                ]
            }
        }

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.list_products(
            shop_domain="example.myshopify.com",
            access_token="token",
            query="alp",
            limit=5,
        )
    )

    assert len(result) == 2
    assert result[0]["id"] == "gid://shopify/Product/100"
    assert result[0]["status"] == "ACTIVE"


def test_get_product_returns_variants_with_inventory_fields():
    client = ShopifyApiClient()
    observed_variables: list[dict] = []

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        observed_variables.append(payload.get("variables") or {})
        variables = payload.get("variables") or {}
        if variables.get("after") is None:
            return {
                "shop": {"currencyCode": "USD"},
                "product": {
                    "id": "gid://shopify/Product/100",
                    "title": "Alpha",
                    "handle": "alpha",
                    "status": "ACTIVE",
                    "variants": {
                        "pageInfo": {"hasNextPage": True, "endCursor": "cursor-2"},
                        "edges": [
                            {
                                "node": {
                                    "id": "gid://shopify/ProductVariant/1",
                                    "title": "Default Title",
                                    "price": "49.99",
                                    "compareAtPrice": "59.99",
                                    "barcode": "BAR-001",
                                    "taxable": True,
                                    "inventoryPolicy": "CONTINUE",
                                    "inventoryQuantity": 12,
                                    "selectedOptions": [{"name": "Size", "value": "L"}],
                                    "inventoryItem": {
                                        "sku": "SKU-001",
                                        "tracked": True,
                                        "requiresShipping": True,
                                    },
                                }
                            }
                        ],
                    },
                },
            }
        return {
            "shop": {"currencyCode": "USD"},
            "product": {
                "id": "gid://shopify/Product/100",
                "title": "Alpha",
                "handle": "alpha",
                "status": "ACTIVE",
                "variants": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "edges": [
                        {
                            "node": {
                                "id": "gid://shopify/ProductVariant/2",
                                "title": "Bundle",
                                "price": "79.00",
                                "compareAtPrice": None,
                                "barcode": None,
                                "taxable": False,
                                "inventoryPolicy": "DENY",
                                "inventoryQuantity": 0,
                                "selectedOptions": [{"name": "Pack", "value": "2"}],
                                "inventoryItem": {
                                    "sku": None,
                                    "tracked": False,
                                    "requiresShipping": False,
                                },
                            }
                        }
                    ],
                },
            },
        }

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.get_product(
            shop_domain="example.myshopify.com",
            access_token="token",
            product_gid="gid://shopify/Product/100",
        )
    )

    assert result["productGid"] == "gid://shopify/Product/100"
    assert result["title"] == "Alpha"
    assert result["status"] == "ACTIVE"
    assert len(result["variants"]) == 2
    first_variant = result["variants"][0]
    assert first_variant["variantGid"] == "gid://shopify/ProductVariant/1"
    assert first_variant["priceCents"] == 4999
    assert first_variant["compareAtPriceCents"] == 5999
    assert first_variant["inventoryManagement"] == "shopify"
    assert first_variant["inventoryPolicy"] == "continue"
    assert first_variant["optionValues"] == {"Size": "L"}
    second_variant = result["variants"][1]
    assert second_variant["inventoryManagement"] is None
    assert second_variant["inventoryPolicy"] == "deny"
    assert observed_variables[0]["after"] is None
    assert observed_variables[1]["after"] == "cursor-2"


def test_create_product_returns_created_product_and_variants():
    client = ShopifyApiClient()
    observed_payloads: list[dict] = []

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        observed_payloads.append(payload)
        query = payload.get("query", "")
        if "mutation productCreate" in query:
            return {
                "productCreate": {
                    "product": {
                        "id": "gid://shopify/Product/999",
                        "title": "Sleep Drops",
                        "handle": "sleep-drops",
                        "status": "DRAFT",
                        "variants": {
                            "edges": [
                                {
                                    "node": {
                                        "id": "gid://shopify/ProductVariant/100",
                                        "title": "Starter",
                                        "price": "0.00",
                                    }
                                }
                            ]
                        },
                    },
                    "userErrors": [],
                }
            }
        if "mutation productVariantsBulkUpdate" in query:
            return {
                "productVariantsBulkUpdate": {
                    "productVariants": [
                        {
                            "id": "gid://shopify/ProductVariant/100",
                            "title": "Starter",
                            "price": "49.99",
                        }
                    ],
                    "userErrors": [],
                }
            }
        if "mutation productVariantsBulkCreate" in query:
            return {
                "productVariantsBulkCreate": {
                    "productVariants": [
                        {
                            "id": "gid://shopify/ProductVariant/200",
                            "title": "Bundle",
                            "price": "79.00",
                        }
                    ],
                    "userErrors": [],
                }
            }
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.create_product(
            shop_domain="example.myshopify.com",
            access_token="token",
            title="Sleep Drops",
            status="DRAFT",
            variants=[
                {"title": "Starter", "priceCents": 4999, "currency": "USD"},
                {"title": "Bundle", "priceCents": 7900, "currency": "USD"},
            ],
        )
    )

    assert result["productGid"] == "gid://shopify/Product/999"
    assert len(result["variants"]) == 2
    assert result["variants"][0]["variantGid"] == "gid://shopify/ProductVariant/100"
    assert result["variants"][0]["priceCents"] == 4999
    assert result["variants"][1]["variantGid"] == "gid://shopify/ProductVariant/200"
    assert len(observed_payloads) == 3


def test_create_product_requires_variants():
    client = ShopifyApiClient()

    with pytest.raises(ShopifyApiError, match="At least one variant is required"):
        asyncio.run(
            client.create_product(
                shop_domain="example.myshopify.com",
                access_token="token",
                title="Sleep Drops",
                variants=[],
            )
        )


def test_update_variant_updates_price_and_compare_at_price():
    client = ShopifyApiClient()
    observed_payloads: list[dict] = []

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        observed_payloads.append(payload)
        query = payload.get("query", "")
        if "query productVariantNode" in query:
            return {
                "node": {
                    "id": "gid://shopify/ProductVariant/100",
                    "product": {"id": "gid://shopify/Product/999"},
                }
            }
        if "mutation productVariantsBulkUpdate" in query:
            variables = payload.get("variables") or {}
            assert variables.get("productId") == "gid://shopify/Product/999"
            variants = variables.get("variants") or []
            assert len(variants) == 1
            assert variants[0]["id"] == "gid://shopify/ProductVariant/100"
            assert variants[0]["price"] == "49.99"
            assert variants[0]["compareAtPrice"] == "59.99"
            return {
                "productVariantsBulkUpdate": {
                    "productVariants": [{"id": "gid://shopify/ProductVariant/100"}],
                    "userErrors": [],
                }
            }
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.update_variant(
            shop_domain="example.myshopify.com",
            access_token="token",
            variant_gid="gid://shopify/ProductVariant/100",
            fields={"priceCents": 4999, "compareAtPriceCents": 5999},
        )
    )

    assert result["productGid"] == "gid://shopify/Product/999"
    assert result["variantGid"] == "gid://shopify/ProductVariant/100"
    assert len(observed_payloads) == 2


def test_update_variant_rejects_missing_fields():
    client = ShopifyApiClient()

    with pytest.raises(ShopifyApiError, match="At least one variant update field is required"):
        asyncio.run(
            client.update_variant(
                shop_domain="example.myshopify.com",
                access_token="token",
                variant_gid="gid://shopify/ProductVariant/100",
                fields={},
            )
        )


def test_update_variant_rejects_invalid_variant_gid():
    client = ShopifyApiClient()

    with pytest.raises(ShopifyApiError, match="variantGid must be a valid Shopify ProductVariant GID"):
        asyncio.run(
            client.update_variant(
                shop_domain="example.myshopify.com",
                access_token="token",
                variant_gid="price_123",
                fields={"priceCents": 4999},
            )
        )


def test_update_variant_clears_compare_at_price():
    client = ShopifyApiClient()

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        query = payload.get("query", "")
        if "query productVariantNode" in query:
            return {
                "node": {
                    "id": "gid://shopify/ProductVariant/100",
                    "product": {"id": "gid://shopify/Product/999"},
                }
            }
        if "mutation productVariantsBulkUpdate" in query:
            variants = ((payload.get("variables") or {}).get("variants")) or []
            assert variants[0]["compareAtPrice"] is None
            return {
                "productVariantsBulkUpdate": {
                    "productVariants": [{"id": "gid://shopify/ProductVariant/100"}],
                    "userErrors": [],
                }
            }
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.update_variant(
            shop_domain="example.myshopify.com",
            access_token="token",
            variant_gid="gid://shopify/ProductVariant/100",
            fields={"compareAtPriceCents": None},
        )
    )

    assert result["variantGid"] == "gid://shopify/ProductVariant/100"


def test_update_variant_updates_inventory_related_fields():
    client = ShopifyApiClient()

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        query = payload.get("query", "")
        if "query productVariantNode" in query:
            return {
                "node": {
                    "id": "gid://shopify/ProductVariant/100",
                    "product": {"id": "gid://shopify/Product/999"},
                }
            }
        if "mutation productVariantsBulkUpdate" in query:
            variants = ((payload.get("variables") or {}).get("variants")) or []
            assert len(variants) == 1
            variant = variants[0]
            assert variant["barcode"] == "BARCODE-001"
            assert variant["inventoryPolicy"] == "CONTINUE"
            assert variant["inventoryItem"] == {"sku": "SKU-001", "tracked": True}
            return {
                "productVariantsBulkUpdate": {
                    "productVariants": [{"id": "gid://shopify/ProductVariant/100"}],
                    "userErrors": [],
                }
            }
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.update_variant(
            shop_domain="example.myshopify.com",
            access_token="token",
            variant_gid="gid://shopify/ProductVariant/100",
            fields={
                "sku": "SKU-001",
                "barcode": "BARCODE-001",
                "inventoryPolicy": "continue",
                "inventoryManagement": "shopify",
            },
        )
    )

    assert result["variantGid"] == "gid://shopify/ProductVariant/100"


def test_update_variant_rejects_invalid_inventory_management():
    client = ShopifyApiClient()

    with pytest.raises(ShopifyApiError, match="inventoryManagement must be null or 'shopify'"):
        asyncio.run(
            client.update_variant(
                shop_domain="example.myshopify.com",
                access_token="token",
                variant_gid="gid://shopify/ProductVariant/100",
                fields={"inventoryManagement": "not-managed"},
            )
        )


def test_upsert_policy_pages_creates_missing_page():
    client = ShopifyApiClient()
    observed_payloads: list[dict] = []

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        observed_payloads.append(payload)
        query = payload.get("query", "")
        if "query pagesByHandle" in query:
            return {"pages": {"edges": []}}
        if "mutation pageCreate" in query:
            return {
                "pageCreate": {
                    "page": {
                        "id": "gid://shopify/Page/101",
                        "title": "Privacy Policy",
                        "handle": "privacy-policy",
                        "onlineStoreUrl": "https://example.myshopify.com/pages/privacy-policy",
                    },
                    "userErrors": [],
                }
            }
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.upsert_policy_pages(
            shop_domain="example.myshopify.com",
            access_token="token",
            pages=[
                {
                    "pageKey": "privacy_policy",
                    "title": "Privacy Policy",
                    "handle": "privacy-policy",
                    "bodyHtml": "<h1>Privacy Policy</h1>",
                }
            ],
        )
    )

    assert len(observed_payloads) == 2
    assert result == [
        {
            "pageKey": "privacy_policy",
            "pageId": "gid://shopify/Page/101",
            "title": "Privacy Policy",
            "handle": "privacy-policy",
            "url": "https://example.myshopify.com/pages/privacy-policy",
            "operation": "created",
        }
    ]


def test_upsert_policy_pages_updates_existing_page():
    client = ShopifyApiClient()
    observed_payloads: list[dict] = []

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        observed_payloads.append(payload)
        query = payload.get("query", "")
        if "query pagesByHandle" in query:
            return {
                "pages": {
                    "edges": [
                        {
                            "node": {
                                "id": "gid://shopify/Page/101",
                                "title": "Old Terms",
                                "handle": "terms-of-service",
                            }
                        }
                    ]
                }
            }
        if "mutation pageUpdate" in query:
            variables = payload.get("variables") or {}
            assert variables.get("id") == "gid://shopify/Page/101"
            return {
                "pageUpdate": {
                    "page": {
                        "id": "gid://shopify/Page/101",
                        "title": "Terms of Service",
                        "handle": "terms-of-service",
                        "onlineStoreUrl": "https://example.myshopify.com/pages/terms-of-service",
                    },
                    "userErrors": [],
                }
            }
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.upsert_policy_pages(
            shop_domain="example.myshopify.com",
            access_token="token",
            pages=[
                {
                    "pageKey": "terms_of_service",
                    "title": "Terms of Service",
                    "handle": "terms-of-service",
                    "bodyHtml": "<h1>Terms of Service</h1>",
                }
            ],
        )
    )

    assert len(observed_payloads) == 2
    assert result[0]["operation"] == "updated"
    assert result[0]["pageId"] == "gid://shopify/Page/101"


def test_sync_theme_brand_updates_layout_and_css():
    client = ShopifyApiClient()
    observed_payloads: list[dict] = []
    settings_json = (
        '{"current":{"color_background":"#ffffff","color_foreground":"#111111","color_button":"#000000",'
        '"color_button_text":"#ffffff","color_link":"#000000","color_accent":"#000000","footer_background":"#ffffff",'
        '"footer_text":"#111111","color_schemes":[{"settings":{"background":"#ffffff","text":"#111111","button":"#000000",'
        '"button_label":"#ffffff","secondary_button":"#eeeeee","secondary_button_label":"#111111"}}]}}\n'
    )

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        observed_payloads.append(payload)
        query = payload.get("query", "")
        if "query themesForBrandSync" in query:
            return {
                "themes": {
                    "nodes": [
                        {
                            "id": "gid://shopify/OnlineStoreTheme/1",
                            "name": "futrgroup2-0theme",
                            "role": "MAIN",
                        }
                    ]
                }
            }
        if "query themeTemplateFilesForBrandSync" in query:
            return {
                "theme": {
                    "files": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "userErrors": [],
                    }
                }
            }
        if "query themeFileByName" in query:
            requested_filenames = ((payload.get("variables") or {}).get("filenames") or [])
            requested_filename = requested_filenames[0] if requested_filenames else None
            if requested_filename == "config/settings_data.json":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "config/settings_data.json",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": settings_json,
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            return {
                "theme": {
                    "files": {
                        "nodes": [
                            {
                                "filename": "layout/theme.liquid",
                                "body": {
                                    "__typename": "OnlineStoreThemeFileBodyText",
                                    "content": (
                                        "<html><head>\n"
                                        "<!-- MOS_WORKSPACE_BRAND_START -->\n"
                                        "old content\n"
                                        "<!-- MOS_WORKSPACE_BRAND_END -->\n"
                                        "</head><body></body></html>"
                                    ),
                                },
                            }
                        ],
                        "userErrors": [],
                    }
                }
            }
        if "mutation themeFilesUpsert" in query:
            variables = payload.get("variables") or {}
            assert variables.get("themeId") == "gid://shopify/OnlineStoreTheme/1"
            files = variables.get("files") or []
            assert len(files) == 3
            filenames = {item["filename"] for item in files}
            assert filenames == {
                "layout/theme.liquid",
                "assets/acme-workspace-workspace-brand.css",
                "config/settings_data.json",
            }
            layout_file = next(item for item in files if item["filename"] == "layout/theme.liquid")
            layout_content = layout_file["body"]["value"]
            assert "acme-workspace-workspace-brand.css" in layout_content
            assert 'meta name="mos-brand-name" content="Acme"' in layout_content
            marker_start = layout_content.find("<!-- MOS_WORKSPACE_BRAND_START -->")
            head_close = layout_content.lower().find("</head>")
            assert marker_start >= 0
            assert head_close >= 0
            assert marker_start < head_close
            css_file = next(item for item in files if item["filename"] == "assets/acme-workspace-workspace-brand.css")
            css_content = css_file["body"]["value"]
            assert "--color-brand: #123456 !important;" in css_content
            assert "--color-highlight: var(--color-brand) !important;" in css_content
            assert '[class*="color-"]' in css_content
            assert '[class*="footer"]' in css_content
            assert "--color-base-button: var(--color-cta) !important;" in css_content
            assert "--color-button-text: var(--color-cta-text) !important;" in css_content
            assert "--color-price: var(--color-brand) !important;" in css_content
            assert "--color-info-background: var(--color-soft) !important;" in css_content
            assert "--color-keyboard-focus: var(--focus-outline-color) !important;" in css_content
            assert "--color-placeholder: var(--color-muted) !important;" in css_content
            assert "--font-body-family: var(--font-sans) !important;" in css_content
            assert "--border-radius-medium: var(--radius-md) !important;" in css_content
            assert "--page-width: var(--container-max) !important;" in css_content
            assert "--page-padding: var(--container-pad) !important;" in css_content
            assert "--footer-pad-y: var(--section-pad-y) !important;" in css_content
            assert "--mos-brand-logo-url: \"https://assets.example.com/public/assets/logo-1\";" in css_content
            assert "/* Managed theme component overrides. */" in css_content
            assert "body {" in css_content
            assert "background-color: var(--color-page-bg) !important;" in css_content
            assert 'a:not(.button):not(.btn):not([class*="button"]):not([class*="btn"]) {' in css_content
            assert 'button, .button, .btn, input[type="button"], input[type="submit"], input[type="reset"], [role="button"] {' in css_content
            assert 'footer, #shopify-section-footer, [role="contentinfo"], .footer, [id*="footer"], [class*="footer"] {' in css_content
            settings_file = next(item for item in files if item["filename"] == "config/settings_data.json")
            settings_content = settings_file["body"]["value"]
            assert '"color_background": "#f5f5f5"' in settings_content
            assert '"footer_background": "#f4ede6"' in settings_content
            return {
                "themeFilesUpsert": {
                    "upsertedThemeFiles": [
                        {"filename": "layout/theme.liquid"},
                        {"filename": "assets/acme-workspace-workspace-brand.css"},
                        {"filename": "config/settings_data.json"},
                    ],
                    "job": {"id": "gid://shopify/Job/1", "done": False},
                    "userErrors": [],
                }
            }
        if "query themeFileJobStatus" in query:
            return {"job": {"id": "gid://shopify/Job/1", "done": True}}
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.sync_theme_brand(
            shop_domain="example.myshopify.com",
            access_token="token",
            workspace_name="Acme Workspace",
            brand_name="Acme",
            logo_url="https://assets.example.com/public/assets/logo-1",
            css_vars=_THEME_SYNC_REQUIRED_CSS_VARS,
            font_urls=["https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap"],
            data_theme="light",
            theme_name="futrgroup2-0theme",
        )
    )

    assert result == {
        "themeId": "gid://shopify/OnlineStoreTheme/1",
        "themeName": "futrgroup2-0theme",
        "themeRole": "MAIN",
        "layoutFilename": "layout/theme.liquid",
        "cssFilename": "assets/acme-workspace-workspace-brand.css",
        "settingsFilename": "config/settings_data.json",
        "jobId": "gid://shopify/Job/1",
        "coverage": {
            "requiredSourceVars": sorted(_THEME_SYNC_REQUIRED_CSS_VARS.keys()),
            "requiredThemeVars": [
                "--border-radius-medium",
                "--color-background",
                "--color-base-background",
                "--color-base-button",
                "--color-base-button-text",
                "--color-base-text",
                "--color-button-border",
                "--color-keyboard-focus",
                "--font-body-family",
                "--font-body-line-height",
                "--font-button-size",
                "--font-heading-family",
                "--font-heading-letter-spacing",
                "--font-heading-line-height",
                "--font-navigation-size",
                "--font-product-size",
                "--footer-bg",
                "--footer-pad-y",
                "--page-padding",
                "--page-width",
            ],
            "missingSourceVars": [],
            "missingThemeVars": [],
        },
        "settingsSync": {
            "settingsFilename": "config/settings_data.json",
            "expectedPaths": [
                "current.color_accent",
                "current.color_background",
                "current.color_button",
                "current.color_button_text",
                "current.color_foreground",
                "current.color_link",
                "current.color_schemes[*].settings.background",
                "current.color_schemes[*].settings.button",
                "current.color_schemes[*].settings.button_label",
                "current.color_schemes[*].settings.highlight",
                "current.color_schemes[*].settings.image_background",
                "current.color_schemes[*].settings.keyboard_focus",
                "current.color_schemes[*].settings.secondary_button",
                "current.color_schemes[*].settings.secondary_button_label",
                "current.color_schemes[*].settings.shadow",
                "current.color_schemes[*].settings.text",
                "current.footer_background",
                "current.footer_text",
            ],
            "updatedPaths": [
                "current.color_accent",
                "current.color_background",
                "current.color_button",
                "current.color_button_text",
                "current.color_foreground",
                "current.color_link",
                "current.color_schemes[*].settings.background",
                "current.color_schemes[*].settings.button",
                "current.color_schemes[*].settings.button_label",
                "current.color_schemes[*].settings.highlight",
                "current.color_schemes[*].settings.image_background",
                "current.color_schemes[*].settings.keyboard_focus",
                "current.color_schemes[*].settings.secondary_button",
                "current.color_schemes[*].settings.secondary_button_label",
                "current.color_schemes[*].settings.shadow",
                "current.color_schemes[*].settings.text",
                "current.footer_background",
                "current.footer_text",
            ],
            "missingPaths": [],
            "requiredMissingPaths": [],
            "semanticUpdatedPaths": [],
            "unmappedColorPaths": [],
            "semanticTypographyUpdatedPaths": [],
            "unmappedTypographyPaths": [],
        },
    }
    assert len(observed_payloads) == 6


def test_sync_theme_brand_allows_upsert_without_job():
    client = ShopifyApiClient()
    observed_payloads: list[dict] = []
    settings_json = (
        "\ufeff/*\n"
        " * ------------------------------------------------------------\n"
        " * IMPORTANT: This file is auto-generated.\n"
        " * ------------------------------------------------------------\n"
        " */\n"
        '{"current":{"color_background":"#ffffff"}}\n'
    )

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        observed_payloads.append(payload)
        query = payload.get("query", "")
        if "query themesForBrandSync" in query:
            return {
                "themes": {
                    "nodes": [
                        {
                            "id": "gid://shopify/OnlineStoreTheme/1",
                            "name": "futrgroup2-0theme",
                            "role": "MAIN",
                        }
                    ]
                }
            }
        if "query themeTemplateFilesForBrandSync" in query:
            return {
                "theme": {
                    "files": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "userErrors": [],
                    }
                }
            }
        if "query themeFileByName" in query:
            requested_filenames = ((payload.get("variables") or {}).get("filenames") or [])
            requested_filename = requested_filenames[0] if requested_filenames else None
            if requested_filename == "config/settings_data.json":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "config/settings_data.json",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": settings_json,
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            return {
                "theme": {
                    "files": {
                        "nodes": [
                            {
                                "filename": "layout/theme.liquid",
                                "body": {
                                    "__typename": "OnlineStoreThemeFileBodyText",
                                    "content": (
                                        "<html><head>\n"
                                        "<!-- MOS_WORKSPACE_BRAND_START -->\n"
                                        "old content\n"
                                        "<!-- MOS_WORKSPACE_BRAND_END -->\n"
                                        "</head><body></body></html>"
                                    ),
                                },
                            }
                        ],
                        "userErrors": [],
                    }
                }
            }
        if "mutation themeFilesUpsert" in query:
            files = ((payload.get("variables") or {}).get("files") or [])
            filenames = {item["filename"] for item in files}
            assert "config/settings_data.json" in filenames
            return {
                "themeFilesUpsert": {
                    "upsertedThemeFiles": [
                        {"filename": "layout/theme.liquid"},
                        {"filename": "assets/acme-workspace-workspace-brand.css"},
                        {"filename": "config/settings_data.json"},
                    ],
                    "job": None,
                    "userErrors": [],
                }
            }
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.sync_theme_brand(
            shop_domain="example.myshopify.com",
            access_token="token",
            workspace_name="Acme Workspace",
            brand_name="Acme",
            logo_url="https://assets.example.com/public/assets/logo-1",
            css_vars=_THEME_SYNC_REQUIRED_CSS_VARS,
            font_urls=[],
            data_theme="light",
            theme_name="futrgroup2-0theme",
        )
    )

    assert result == {
        "themeId": "gid://shopify/OnlineStoreTheme/1",
        "themeName": "futrgroup2-0theme",
        "themeRole": "MAIN",
        "layoutFilename": "layout/theme.liquid",
        "cssFilename": "assets/acme-workspace-workspace-brand.css",
        "settingsFilename": "config/settings_data.json",
        "jobId": None,
        "coverage": {
            "requiredSourceVars": sorted(_THEME_SYNC_REQUIRED_CSS_VARS.keys()),
            "requiredThemeVars": [
                "--border-radius-medium",
                "--color-background",
                "--color-base-background",
                "--color-base-button",
                "--color-base-button-text",
                "--color-base-text",
                "--color-button-border",
                "--color-keyboard-focus",
                "--font-body-family",
                "--font-body-line-height",
                "--font-button-size",
                "--font-heading-family",
                "--font-heading-letter-spacing",
                "--font-heading-line-height",
                "--font-navigation-size",
                "--font-product-size",
                "--footer-bg",
                "--footer-pad-y",
                "--page-padding",
                "--page-width",
            ],
            "missingSourceVars": [],
            "missingThemeVars": [],
        },
        "settingsSync": {
            "settingsFilename": "config/settings_data.json",
            "expectedPaths": [
                "current.color_accent",
                "current.color_background",
                "current.color_button",
                "current.color_button_text",
                "current.color_foreground",
                "current.color_link",
                "current.footer_background",
                "current.footer_text",
            ],
            "updatedPaths": [
                "current.color_accent",
                "current.color_background",
                "current.color_button",
                "current.color_button_text",
                "current.color_foreground",
                "current.color_link",
                "current.footer_background",
                "current.footer_text",
            ],
            "missingPaths": [],
            "requiredMissingPaths": [],
            "semanticUpdatedPaths": [],
            "unmappedColorPaths": [],
            "semanticTypographyUpdatedPaths": [],
            "unmappedTypographyPaths": [],
        },
    }
    assert len(observed_payloads) == 5


def test_sync_theme_brand_upserts_template_component_settings():
    client = ShopifyApiClient()
    settings_json = '{"current":{"color_background":"#ffffff"}}\n'
    template_json = json.dumps(
        {
            "sections": {
                "hero": {
                    "type": "image-with-text-overlay",
                    "settings": {
                        "heading_color": "#ffffff",
                        "color_overlay": "#000000",
                    },
                }
            }
        }
    )

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        query = payload.get("query", "")
        if "query themesForBrandSync" in query:
            return {
                "themes": {
                    "nodes": [
                        {
                            "id": "gid://shopify/OnlineStoreTheme/1",
                            "name": "futrgroup2-0theme",
                            "role": "MAIN",
                        }
                    ]
                }
            }
        if "query themeTemplateFilesForBrandSync" in query:
            return {
                "theme": {
                    "files": {
                        "nodes": [
                            {
                                "filename": "templates/index.json",
                                "body": {
                                    "__typename": "OnlineStoreThemeFileBodyText",
                                },
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "userErrors": [],
                    }
                }
            }
        if "query themeFileByName" in query:
            requested_filenames = ((payload.get("variables") or {}).get("filenames") or [])
            requested_filename = requested_filenames[0] if requested_filenames else None
            if requested_filename == "config/settings_data.json":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "config/settings_data.json",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": settings_json,
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            if requested_filename == "templates/index.json":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "templates/index.json",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": template_json,
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            return {
                "theme": {
                    "files": {
                        "nodes": [
                            {
                                "filename": "layout/theme.liquid",
                                "body": {
                                    "__typename": "OnlineStoreThemeFileBodyText",
                                    "content": (
                                        "<html><head>\n"
                                        "<!-- MOS_WORKSPACE_BRAND_START -->\n"
                                        "old content\n"
                                        "<!-- MOS_WORKSPACE_BRAND_END -->\n"
                                        "</head><body></body></html>"
                                    ),
                                },
                            }
                        ],
                        "userErrors": [],
                    }
                }
            }
        if "mutation themeFilesUpsert" in query:
            files = ((payload.get("variables") or {}).get("files") or [])
            filenames = {item["filename"] for item in files}
            assert filenames == {
                "layout/theme.liquid",
                "assets/acme-workspace-workspace-brand.css",
                "config/settings_data.json",
                "templates/index.json",
            }
            template_file = next(item for item in files if item["filename"] == "templates/index.json")
            template_content = template_file["body"]["value"]
            assert '"heading_color":"#222222"' in template_content
            assert '"color_overlay":"rgba(0, 0, 0, 0.08)"' in template_content
            return {
                "themeFilesUpsert": {
                    "upsertedThemeFiles": [
                        {"filename": "layout/theme.liquid"},
                        {"filename": "assets/acme-workspace-workspace-brand.css"},
                        {"filename": "config/settings_data.json"},
                        {"filename": "templates/index.json"},
                    ],
                    "job": None,
                    "userErrors": [],
                }
            }
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.sync_theme_brand(
            shop_domain="example.myshopify.com",
            access_token="token",
            workspace_name="Acme Workspace",
            brand_name="Acme",
            logo_url="https://assets.example.com/public/assets/logo-1",
            css_vars=_THEME_SYNC_REQUIRED_CSS_VARS,
            font_urls=[],
            data_theme="light",
            theme_name="futrgroup2-0theme",
        )
    )

    assert "templates/index.json.sections.hero.settings.heading_color" in result["settingsSync"]["semanticUpdatedPaths"]
    assert "templates/index.json.sections.hero.settings.color_overlay" in result["settingsSync"]["semanticUpdatedPaths"]
    assert result["settingsSync"]["unmappedColorPaths"] == []


def test_sync_theme_brand_bootstraps_current_color_schemes_from_presets():
    client = ShopifyApiClient()
    settings_json = (
        '{"current":{"color_background":"#ffffff"},'
        '"presets":{"Default":{"color_schemes":[{"settings":{"background":"#ffffff","text":"#111111","button":"#000000",'
        '"button_label":"#ffffff","secondary_button":"#eeeeee","secondary_button_label":"#111111"}}]}}}\n'
    )

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        query = payload.get("query", "")
        if "query themesForBrandSync" in query:
            return {
                "themes": {
                    "nodes": [
                        {
                            "id": "gid://shopify/OnlineStoreTheme/1",
                            "name": "futrgroup2-0theme",
                            "role": "MAIN",
                        }
                    ]
                }
            }
        if "query themeTemplateFilesForBrandSync" in query:
            return {
                "theme": {
                    "files": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "userErrors": [],
                    }
                }
            }
        if "query themeFileByName" in query:
            requested_filenames = ((payload.get("variables") or {}).get("filenames") or [])
            requested_filename = requested_filenames[0] if requested_filenames else None
            if requested_filename == "config/settings_data.json":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "config/settings_data.json",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": settings_json,
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            return {
                "theme": {
                    "files": {
                        "nodes": [
                            {
                                "filename": "layout/theme.liquid",
                                "body": {
                                    "__typename": "OnlineStoreThemeFileBodyText",
                                    "content": (
                                        "<html><head>\n"
                                        "<!-- MOS_WORKSPACE_BRAND_START -->\n"
                                        "old content\n"
                                        "<!-- MOS_WORKSPACE_BRAND_END -->\n"
                                        "</head><body></body></html>"
                                    ),
                                },
                            }
                        ],
                        "userErrors": [],
                    }
                }
            }
        if "mutation themeFilesUpsert" in query:
            files = ((payload.get("variables") or {}).get("files") or [])
            settings_file = next(item for item in files if item["filename"] == "config/settings_data.json")
            settings_content = settings_file["body"]["value"]
            assert '"color_schemes": [' in settings_content
            assert '"background": "#f5f5f5"' in settings_content
            assert '"button": "#0a8f3c"' in settings_content
            return {
                "themeFilesUpsert": {
                    "upsertedThemeFiles": [
                        {"filename": "layout/theme.liquid"},
                        {"filename": "assets/acme-workspace-workspace-brand.css"},
                        {"filename": "config/settings_data.json"},
                    ],
                    "job": None,
                    "userErrors": [],
                }
            }
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.sync_theme_brand(
            shop_domain="example.myshopify.com",
            access_token="token",
            workspace_name="Acme Workspace",
            brand_name="Acme",
            logo_url="https://assets.example.com/public/assets/logo-1",
            css_vars=_THEME_SYNC_REQUIRED_CSS_VARS,
            font_urls=[],
            data_theme="light",
            theme_name="futrgroup2-0theme",
        )
    )

    assert result["settingsSync"]["updatedPaths"] == [
        "current.color_accent",
        "current.color_background",
        "current.color_button",
        "current.color_button_text",
        "current.color_foreground",
        "current.color_link",
        "current.color_schemes[*].settings.background",
        "current.color_schemes[*].settings.button",
        "current.color_schemes[*].settings.button_label",
        "current.color_schemes[*].settings.highlight",
        "current.color_schemes[*].settings.image_background",
        "current.color_schemes[*].settings.keyboard_focus",
        "current.color_schemes[*].settings.secondary_button",
        "current.color_schemes[*].settings.secondary_button_label",
        "current.color_schemes[*].settings.shadow",
        "current.color_schemes[*].settings.text",
        "current.footer_background",
        "current.footer_text",
    ]
    assert result["settingsSync"]["missingPaths"] == []


def test_sync_theme_brand_bootstraps_current_color_schemes_from_nested_root_node():
    client = ShopifyApiClient()
    settings_json = (
        '{"current":{"color_background":"#ffffff"},'
        '"meta":{"theme":{"color_schemes":[{"settings":{"background":"#ffffff","text":"#111111","button":"#000000",'
        '"button_label":"#ffffff","secondary_button":"#eeeeee","secondary_button_label":"#111111"}}]}}}\n'
    )

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        query = payload.get("query", "")
        if "query themesForBrandSync" in query:
            return {
                "themes": {
                    "nodes": [
                        {
                            "id": "gid://shopify/OnlineStoreTheme/1",
                            "name": "futrgroup2-0theme",
                            "role": "MAIN",
                        }
                    ]
                }
            }
        if "query themeTemplateFilesForBrandSync" in query:
            return {
                "theme": {
                    "files": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "userErrors": [],
                    }
                }
            }
        if "query themeFileByName" in query:
            requested_filenames = ((payload.get("variables") or {}).get("filenames") or [])
            requested_filename = requested_filenames[0] if requested_filenames else None
            if requested_filename == "config/settings_data.json":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "config/settings_data.json",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": settings_json,
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            return {
                "theme": {
                    "files": {
                        "nodes": [
                            {
                                "filename": "layout/theme.liquid",
                                "body": {
                                    "__typename": "OnlineStoreThemeFileBodyText",
                                    "content": (
                                        "<html><head>\n"
                                        "<!-- MOS_WORKSPACE_BRAND_START -->\n"
                                        "old content\n"
                                        "<!-- MOS_WORKSPACE_BRAND_END -->\n"
                                        "</head><body></body></html>"
                                    ),
                                },
                            }
                        ],
                        "userErrors": [],
                    }
                }
            }
        if "mutation themeFilesUpsert" in query:
            files = ((payload.get("variables") or {}).get("files") or [])
            settings_file = next(item for item in files if item["filename"] == "config/settings_data.json")
            settings_content = settings_file["body"]["value"]
            assert '"color_schemes": [' in settings_content
            assert '"background": "#f5f5f5"' in settings_content
            assert '"button": "#0a8f3c"' in settings_content
            return {
                "themeFilesUpsert": {
                    "upsertedThemeFiles": [
                        {"filename": "layout/theme.liquid"},
                        {"filename": "assets/acme-workspace-workspace-brand.css"},
                        {"filename": "config/settings_data.json"},
                    ],
                    "job": None,
                    "userErrors": [],
                }
            }
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.sync_theme_brand(
            shop_domain="example.myshopify.com",
            access_token="token",
            workspace_name="Acme Workspace",
            brand_name="Acme",
            logo_url="https://assets.example.com/public/assets/logo-1",
            css_vars=_THEME_SYNC_REQUIRED_CSS_VARS,
            font_urls=[],
            data_theme="light",
            theme_name="futrgroup2-0theme",
        )
    )

    assert len(result["settingsSync"]["updatedPaths"]) == 18
    assert result["settingsSync"]["missingPaths"] == []


def test_sync_theme_brand_requires_managed_layout_markers():
    client = ShopifyApiClient()
    settings_json = '{"current":{"color_background":"#ffffff"}}\n'

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        query = payload.get("query", "")
        if "query themesForBrandSync" in query:
            return {
                "themes": {
                    "nodes": [
                        {
                            "id": "gid://shopify/OnlineStoreTheme/1",
                            "name": "futrgroup2-0theme",
                            "role": "MAIN",
                        }
                    ]
                }
            }
        if "query themeTemplateFilesForBrandSync" in query:
            return {
                "theme": {
                    "files": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "userErrors": [],
                    }
                }
            }
        if "query themeFileByName" in query:
            requested_filenames = ((payload.get("variables") or {}).get("filenames") or [])
            requested_filename = requested_filenames[0] if requested_filenames else None
            if requested_filename == "config/settings_data.json":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "config/settings_data.json",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": settings_json,
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            return {
                "theme": {
                    "files": {
                        "nodes": [
                            {
                                "filename": "layout/theme.liquid",
                                "body": {
                                    "__typename": "OnlineStoreThemeFileBodyText",
                                    "content": "<html><head></head><body></body></html>",
                                },
                            }
                        ],
                        "userErrors": [],
                    }
                }
            }
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    with pytest.raises(ShopifyApiError, match="Theme layout must include exactly one managed brand marker block"):
        asyncio.run(
            client.sync_theme_brand(
                shop_domain="example.myshopify.com",
                access_token="token",
                workspace_name="Acme Workspace",
                brand_name="Acme",
                logo_url="https://assets.example.com/public/assets/logo-1",
                css_vars=_THEME_SYNC_REQUIRED_CSS_VARS,
                font_urls=[],
                data_theme="light",
                theme_name="futrgroup2-0theme",
            )
        )


def test_sync_theme_brand_requires_closing_head_tag():
    client = ShopifyApiClient()
    settings_json = '{"current":{"color_background":"#ffffff"}}\n'

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        query = payload.get("query", "")
        if "query themesForBrandSync" in query:
            return {
                "themes": {
                    "nodes": [
                        {
                            "id": "gid://shopify/OnlineStoreTheme/1",
                            "name": "futrgroup2-0theme",
                            "role": "MAIN",
                        }
                    ]
                }
            }
        if "query themeTemplateFilesForBrandSync" in query:
            return {
                "theme": {
                    "files": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "userErrors": [],
                    }
                }
            }
        if "query themeFileByName" in query:
            requested_filenames = ((payload.get("variables") or {}).get("filenames") or [])
            requested_filename = requested_filenames[0] if requested_filenames else None
            if requested_filename == "config/settings_data.json":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "config/settings_data.json",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": settings_json,
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            return {
                "theme": {
                    "files": {
                        "nodes": [
                            {
                                "filename": "layout/theme.liquid",
                                "body": {
                                    "__typename": "OnlineStoreThemeFileBodyText",
                                    "content": (
                                        "<html><head>\n"
                                        "<!-- MOS_WORKSPACE_BRAND_START -->\n"
                                        "old content\n"
                                        "<!-- MOS_WORKSPACE_BRAND_END -->\n"
                                        "<body></body></html>"
                                    ),
                                },
                            }
                        ],
                        "userErrors": [],
                    }
                }
            }
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    with pytest.raises(ShopifyApiError, match="Theme layout must include a closing </head> tag"):
        asyncio.run(
            client.sync_theme_brand(
                shop_domain="example.myshopify.com",
                access_token="token",
                workspace_name="Acme Workspace",
                brand_name="Acme",
                logo_url="https://assets.example.com/public/assets/logo-1",
                css_vars=_THEME_SYNC_REQUIRED_CSS_VARS,
                font_urls=[],
                data_theme="light",
                theme_name="futrgroup2-0theme",
            )
        )


def test_sync_theme_brand_errors_for_unsupported_theme_profile():
    client = ShopifyApiClient()

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        query = payload.get("query", "")
        if "query themesForBrandSync" in query:
            return {
                "themes": {
                    "nodes": [
                        {
                            "id": "gid://shopify/OnlineStoreTheme/1",
                            "name": "custom-theme",
                            "role": "MAIN",
                        }
                    ]
                }
            }
        if "query themeTemplateFilesForBrandSync" in query:
            return {
                "theme": {
                    "files": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "userErrors": [],
                    }
                }
            }
        if "query themeFileByName" in query:
            return {
                "theme": {
                    "files": {
                        "nodes": [
                            {
                                "filename": "layout/theme.liquid",
                                "body": {
                                    "__typename": "OnlineStoreThemeFileBodyText",
                                    "content": (
                                        "<html><head>\n"
                                        "<!-- MOS_WORKSPACE_BRAND_START -->\n"
                                        "old content\n"
                                        "<!-- MOS_WORKSPACE_BRAND_END -->\n"
                                        "</head><body></body></html>"
                                    ),
                                },
                            }
                        ],
                        "userErrors": [],
                    }
                }
            }
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    with pytest.raises(
        ShopifyApiError,
        match="Unsupported theme profile for themeName=custom-theme",
    ):
        asyncio.run(
            client.sync_theme_brand(
                shop_domain="example.myshopify.com",
                access_token="token",
                workspace_name="Acme Workspace",
                brand_name="Acme",
                logo_url="https://assets.example.com/public/assets/logo-1",
                css_vars=_THEME_SYNC_REQUIRED_CSS_VARS,
                font_urls=[],
                data_theme="light",
                theme_name="custom-theme",
            )
        )


def test_render_theme_brand_css_preserves_explicit_theme_var_values():
    css = ShopifyApiClient._render_theme_brand_css(
        theme_name="futrgroup2-0theme",
        workspace_name="Acme Workspace",
        brand_name="Acme",
        logo_url="https://assets.example.com/public/assets/logo-1",
        data_theme="light",
        css_vars={
            "--color-cta": "#0a8f3c",
            "--color-base-button": "#001122",
        },
        font_urls=[],
    )

    assert "--color-base-button: #001122 !important;" in css
    assert "--color-base-button: var(--color-cta) !important;" not in css


def test_render_theme_brand_css_includes_theme_scope_selectors():
    css = ShopifyApiClient._render_theme_brand_css(
        theme_name="futrgroup2-0theme",
        workspace_name="Acme Workspace",
        brand_name="Acme",
        logo_url="https://assets.example.com/public/assets/logo-1",
        data_theme="light",
        css_vars={"--footer-bg": "#f4ede6"},
        font_urls=[],
    )

    assert ':root, html, body, .color-scheme, .gradient, footer, #shopify-section-footer, [role="contentinfo"], .footer, [data-color-scheme], [id*="footer"], [class*="color-scheme"], [class*="scheme-"], [class*="color-"], [class*="footer"] {' in css
    assert 'html[data-theme="light"] .footer {' not in css
    assert 'html[data-theme="light"], html[data-theme="light"] html, html[data-theme="light"] body, html[data-theme="light"] .color-scheme' in css
    assert 'html[data-theme="light"] [class*="footer"] {' in css
    assert '--footer-bg: #f4ede6 !important;' in css


def test_resolve_theme_brand_profile_supports_canonicalized_theme_aliases():
    profile = ShopifyApiClient._resolve_theme_brand_profile(theme_name="Futr Group 2.0 Theme")

    assert profile.theme_name == "futrgroup2-0theme"
    assert profile.settings_value_paths["current.footer_background"] == "--footer-bg"
    assert "--color-muted" in profile.required_source_vars
    assert "current.color_background" in profile.required_settings_paths


def test_sync_theme_settings_data_updates_semantic_color_paths():
    profile = ShopifyApiClient._resolve_theme_brand_profile(theme_name="futrgroup2-0theme")
    effective_css_vars = ShopifyApiClient._build_theme_compat_css_vars(
        profile=profile,
        css_vars=_THEME_SYNC_REQUIRED_CSS_VARS,
    )
    settings_content = _build_minimal_theme_settings_json(
        extra_current={
            "sections": {
                "announcement": {
                    "text_color": "#ffffff",
                    "border_color": "#ffffff",
                }
            }
        }
    )

    next_settings_content, report = ShopifyApiClient._sync_theme_settings_data(
        profile=profile,
        settings_content=settings_content,
        effective_css_vars=effective_css_vars,
    )
    synced_settings = ShopifyApiClient._parse_theme_settings_json(settings_content=next_settings_content)

    assert synced_settings["current"]["sections"]["announcement"]["text_color"] == _THEME_SYNC_REQUIRED_CSS_VARS[
        "--color-text"
    ]
    assert synced_settings["current"]["sections"]["announcement"]["border_color"] == _THEME_SYNC_REQUIRED_CSS_VARS[
        "--color-border"
    ]
    assert report["semanticUpdatedPaths"] == [
        "current.sections.announcement.border_color",
        "current.sections.announcement.text_color",
    ]
    assert report["unmappedColorPaths"] == []


def test_sync_theme_settings_data_updates_checkout_and_sale_semantic_color_paths():
    profile = ShopifyApiClient._resolve_theme_brand_profile(theme_name="futrgroup2-0theme")
    effective_css_vars = ShopifyApiClient._build_theme_compat_css_vars(
        profile=profile,
        css_vars=_THEME_SYNC_REQUIRED_CSS_VARS,
    )
    settings_content = _build_minimal_theme_settings_json(
        extra_current={
            "checkout_error_color": "#ff0000",
            "color_price": "#ff0000",
            "color_sale_price": "#ff0000",
            "color_sale_tag": "#ff0000",
            "sections": {
                "main-password-header": {
                    "settings": {
                        "color_drawer_overlay": "#ff0000",
                    }
                }
            },
        }
    )

    next_settings_content, report = ShopifyApiClient._sync_theme_settings_data(
        profile=profile,
        settings_content=settings_content,
        effective_css_vars=effective_css_vars,
    )
    synced_settings = ShopifyApiClient._parse_theme_settings_json(settings_content=next_settings_content)

    assert synced_settings["current"]["checkout_error_color"] == _THEME_SYNC_REQUIRED_CSS_VARS["--color-text"]
    assert synced_settings["current"]["color_price"] == _THEME_SYNC_REQUIRED_CSS_VARS["--color-brand"]
    assert synced_settings["current"]["color_sale_price"] == _THEME_SYNC_REQUIRED_CSS_VARS["--color-cta"]
    assert synced_settings["current"]["color_sale_tag"] == _THEME_SYNC_REQUIRED_CSS_VARS["--color-cta"]
    assert synced_settings["current"]["sections"]["main-password-header"]["settings"]["color_drawer_overlay"] == (
        _THEME_SYNC_REQUIRED_CSS_VARS["--color-soft"]
    )
    assert report["unmappedColorPaths"] == []


def test_sync_theme_settings_data_updates_typography_semantic_paths():
    profile = ShopifyApiClient._resolve_theme_brand_profile(theme_name="futrgroup2-0theme")
    effective_css_vars = ShopifyApiClient._build_theme_compat_css_vars(
        profile=profile,
        css_vars={
            **_THEME_SYNC_REQUIRED_CSS_VARS,
            "--font-heading": "inter_n7",
        },
    )
    settings_content = _build_minimal_theme_settings_json(
        extra_current={
            "type_header_font": "inter_n7",
            "type_header_line_height": 0.9,
            "type_header_spacing": 0,
            "type_body_font": "inter_n4",
            "type_body_base_size": 12,
            "type_body_line_height": 1.0,
            "type_body_spacing": 0,
            "type_nav_font": "heading",
            "type_nav_base_size": 14,
            "type_buttons_font": "heading",
            "type_buttons_base_size": 14,
            "type_product_grid_font": "heading",
            "type_product_grid_base_size": 14,
        }
    )

    next_settings_content, report = ShopifyApiClient._sync_theme_settings_data(
        profile=profile,
        settings_content=settings_content,
        effective_css_vars=effective_css_vars,
    )
    synced_settings = ShopifyApiClient._parse_theme_settings_json(settings_content=next_settings_content)
    synced_current = synced_settings["current"]

    assert synced_current["type_header_font"] == "inter_n7"
    assert synced_current["type_header_line_height"] == 1.0
    assert synced_current["type_header_spacing"] == -30
    assert synced_current["type_body_font"] == "inter_n4"
    assert synced_current["type_body_base_size"] == 15
    assert synced_current["type_body_line_height"] == 1.2
    assert synced_current["type_body_spacing"] == -30
    assert synced_current["type_nav_font"] == "body"
    assert synced_current["type_nav_base_size"] == 16
    assert synced_current["type_buttons_font"] == "body"
    assert synced_current["type_buttons_base_size"] == 18
    assert synced_current["type_product_grid_font"] == "body"
    assert synced_current["type_product_grid_base_size"] == 15
    assert "current.type_header_spacing" in report["semanticTypographyUpdatedPaths"]
    assert report["unmappedTypographyPaths"] == []


def test_sync_theme_settings_data_errors_for_unmapped_typography_paths():
    profile = ShopifyApiClient._resolve_theme_brand_profile(theme_name="futrgroup2-0theme")
    effective_css_vars = ShopifyApiClient._build_theme_compat_css_vars(
        profile=profile,
        css_vars=_THEME_SYNC_REQUIRED_CSS_VARS,
    )
    settings_content = _build_minimal_theme_settings_json(
        extra_current={
            "type_header_weight": 600,
        }
    )

    with pytest.raises(
        ShopifyApiError,
        match="unmapped typography setting paths: current.type_header_weight",
    ):
        ShopifyApiClient._sync_theme_settings_data(
            profile=profile,
            settings_content=settings_content,
            effective_css_vars=effective_css_vars,
        )


def test_sync_theme_settings_data_errors_for_invalid_font_picker_handle_source():
    profile = ShopifyApiClient._resolve_theme_brand_profile(theme_name="futrgroup2-0theme")
    effective_css_vars = ShopifyApiClient._build_theme_compat_css_vars(
        profile=profile,
        css_vars={
            **_THEME_SYNC_REQUIRED_CSS_VARS,
            "--font-heading": "Cormorant Garamond, serif",
        },
    )
    settings_content = _build_minimal_theme_settings_json(
        extra_current={
            "type_header_font": "Inter",
        }
    )

    with pytest.raises(
        ShopifyApiError,
        match="requires current value 'Inter' to be a Shopify font handle",
    ):
        ShopifyApiClient._sync_theme_settings_data(
            profile=profile,
            settings_content=settings_content,
            effective_css_vars=effective_css_vars,
        )


def test_sync_theme_settings_data_aliases_cormorant_garamond_to_cormorant_handle():
    profile = ShopifyApiClient._resolve_theme_brand_profile(theme_name="futrgroup2-0theme")
    effective_css_vars = ShopifyApiClient._build_theme_compat_css_vars(
        profile=profile,
        css_vars={
            **_THEME_SYNC_REQUIRED_CSS_VARS,
            "--font-heading": "'Cormorant Garamond', serif",
        },
    )
    settings_content = _build_minimal_theme_settings_json(
        extra_current={
            "type_header_font": "inter_n7",
        }
    )

    next_settings_content, _ = ShopifyApiClient._sync_theme_settings_data(
        profile=profile,
        settings_content=settings_content,
        effective_css_vars=effective_css_vars,
    )
    synced_settings = ShopifyApiClient._parse_theme_settings_json(settings_content=next_settings_content)

    assert synced_settings["current"]["type_header_font"] == "cormorant_n7"


def test_sync_theme_settings_data_errors_for_unknown_shopify_font_family():
    profile = ShopifyApiClient._resolve_theme_brand_profile(theme_name="futrgroup2-0theme")
    effective_css_vars = ShopifyApiClient._build_theme_compat_css_vars(
        profile=profile,
        css_vars={
            **_THEME_SYNC_REQUIRED_CSS_VARS,
            "--font-heading": "Completely Unknown Family, serif",
        },
    )
    settings_content = _build_minimal_theme_settings_json(
        extra_current={
            "type_header_font": "inter_n7",
        }
    )

    with pytest.raises(
        ShopifyApiError,
        match="cannot map family 'Completely Unknown Family' to a known Shopify font handle",
    ):
        ShopifyApiClient._sync_theme_settings_data(
            profile=profile,
            settings_content=settings_content,
            effective_css_vars=effective_css_vars,
        )


def test_sync_theme_settings_data_accepts_explicit_shopify_font_handle_source():
    profile = ShopifyApiClient._resolve_theme_brand_profile(theme_name="futrgroup2-0theme")
    effective_css_vars = ShopifyApiClient._build_theme_compat_css_vars(
        profile=profile,
        css_vars={
            **_THEME_SYNC_REQUIRED_CSS_VARS,
            "--font-heading": "inter_i7",
        },
    )
    settings_content = _build_minimal_theme_settings_json(
        extra_current={
            "type_header_font": "inter_n7",
        }
    )

    next_settings_content, _ = ShopifyApiClient._sync_theme_settings_data(
        profile=profile,
        settings_content=settings_content,
        effective_css_vars=effective_css_vars,
    )
    synced_settings = ShopifyApiClient._parse_theme_settings_json(settings_content=next_settings_content)

    assert synced_settings["current"]["type_header_font"] == "inter_i7"


def test_sync_theme_template_color_settings_data_updates_component_paths():
    profile = ShopifyApiClient._resolve_theme_brand_profile(theme_name="futrgroup2-0theme")
    effective_css_vars = ShopifyApiClient._build_theme_compat_css_vars(
        profile=profile,
        css_vars=_THEME_SYNC_REQUIRED_CSS_VARS,
    )
    template_content = json.dumps(
        {
            "sections": {
                "hero": {
                    "type": "image-with-text-overlay",
                    "settings": {
                        "color_overlay": "#000000",
                        "heading_color": "#111111",
                        "button_bg_color": "#c0c0c0",
                        "button_color": "#111111",
                        "item_bg_color": "#ffffff",
                        "arrow_color": "#000000",
                        "line_color": "#000000",
                    },
                    "blocks": {
                        "heading": {
                            "type": "heading",
                            "settings": {
                                "title_color": "#222222",
                                "icon_color": "#333333",
                            },
                        }
                    },
                }
            }
        }
    )

    next_template_content, report = ShopifyApiClient._sync_theme_template_color_settings_data(
        profile=profile,
        template_filename="templates/index.json",
        template_content=template_content,
        effective_css_vars=effective_css_vars,
    )
    synced_template = ShopifyApiClient._parse_theme_template_json(
        filename="templates/index.json",
        template_content=next_template_content,
    )
    hero_settings = synced_template["sections"]["hero"]["settings"]
    heading_block_settings = synced_template["sections"]["hero"]["blocks"]["heading"]["settings"]

    assert hero_settings["color_overlay"] == _THEME_SYNC_REQUIRED_CSS_VARS["--color-soft"]
    assert hero_settings["heading_color"] == _THEME_SYNC_REQUIRED_CSS_VARS["--color-text"]
    assert hero_settings["button_bg_color"] == _THEME_SYNC_REQUIRED_CSS_VARS["--color-cta"]
    assert hero_settings["button_color"] == _THEME_SYNC_REQUIRED_CSS_VARS["--color-cta-text"]
    assert hero_settings["item_bg_color"] == _THEME_SYNC_REQUIRED_CSS_VARS["--color-page-bg"]
    assert hero_settings["arrow_color"] == _THEME_SYNC_REQUIRED_CSS_VARS["--color-brand"]
    assert hero_settings["line_color"] == _THEME_SYNC_REQUIRED_CSS_VARS["--color-border"]
    assert heading_block_settings["title_color"] == _THEME_SYNC_REQUIRED_CSS_VARS["--color-text"]
    assert heading_block_settings["icon_color"] == _THEME_SYNC_REQUIRED_CSS_VARS["--color-brand"]
    assert report["unmappedColorPaths"] == []
    assert "templates/index.json.sections.hero.settings.heading_color" in report["updatedPaths"]


def test_parse_theme_template_json_supports_leading_comment_block():
    parsed = ShopifyApiClient._parse_theme_template_json(
        filename="templates/404.json",
        template_content=(
            "\ufeff/*\n"
            " * ------------------------------------------------------------\n"
            " * IMPORTANT: This file is auto-generated.\n"
            " * ------------------------------------------------------------\n"
            " */\n"
            "{\"sections\":{\"main\":{\"type\":\"main-404\",\"settings\":{}}},\"order\":[\"main\"]}\n"
        ),
    )

    assert parsed["sections"]["main"]["type"] == "main-404"
    assert parsed["order"] == ["main"]


def test_parse_theme_template_json_errors_for_unterminated_leading_comment_block():
    with pytest.raises(
        ShopifyApiError,
        match="Theme template file templates/404.json contains an unterminated leading comment block",
    ):
        ShopifyApiClient._parse_theme_template_json(
            filename="templates/404.json",
            template_content="/*\n * IMPORTANT: auto-generated template header\n",
        )


def test_sync_theme_settings_data_errors_for_unmapped_color_paths():
    profile = ShopifyApiClient._resolve_theme_brand_profile(theme_name="futrgroup2-0theme")
    effective_css_vars = ShopifyApiClient._build_theme_compat_css_vars(
        profile=profile,
        css_vars=_THEME_SYNC_REQUIRED_CSS_VARS,
    )
    settings_content = _build_minimal_theme_settings_json(
        extra_current={
            "color_badge": "#ff00ff",
        }
    )

    with pytest.raises(
        ShopifyApiError,
        match="unmapped color setting paths: current.color_badge",
    ):
        ShopifyApiClient._sync_theme_settings_data(
            profile=profile,
            settings_content=settings_content,
            effective_css_vars=effective_css_vars,
        )


def test_audit_theme_settings_data_reports_semantic_mismatch():
    profile = ShopifyApiClient._resolve_theme_brand_profile(theme_name="futrgroup2-0theme")
    effective_css_vars = ShopifyApiClient._build_theme_compat_css_vars(
        profile=profile,
        css_vars=_THEME_SYNC_REQUIRED_CSS_VARS,
    )
    settings_content = _build_minimal_theme_settings_json(
        extra_current={
            "sections": {
                "announcement": {
                    "text_color": "#ffffff",
                }
            }
        }
    )

    report = ShopifyApiClient._audit_theme_settings_data(
        profile=profile,
        settings_content=settings_content,
        effective_css_vars=effective_css_vars,
    )

    assert "current.sections.announcement.text_color" in report["semanticMismatchedPaths"]
    assert report["unmappedColorPaths"] == []


def test_sync_theme_brand_requires_one_theme_selector():
    client = ShopifyApiClient()

    with pytest.raises(ShopifyApiError, match="Exactly one of themeId or themeName is required"):
        asyncio.run(
            client.sync_theme_brand(
                shop_domain="example.myshopify.com",
                access_token="token",
                workspace_name="Acme Workspace",
                brand_name="Acme",
                logo_url="https://assets.example.com/public/assets/logo-1",
                css_vars={"--color-brand": "#123456"},
                font_urls=[],
                data_theme="light",
            )
        )


def test_audit_theme_brand_reports_ready_when_layout_css_and_settings_are_synced():
    client = ShopifyApiClient()
    settings_json = """
{
  "current": {
    "color_background": "#f5f5f5",
    "color_foreground": "#222222",
    "color_button": "#0a8f3c",
    "color_button_text": "#ffffff",
    "color_link": "#123456",
    "color_accent": "#123456",
    "footer_background": "#f4ede6",
    "footer_text": "#222222",
    "color_schemes": [
      {
        "settings": {
          "background": "#f5f5f5",
          "text": "#222222",
          "button": "#0a8f3c",
          "button_label": "#ffffff",
          "highlight": "rgba(0, 0, 0, 0.08)",
          "keyboard_focus": "rgba(6, 26, 112, 0.35)",
          "shadow": "rgba(34, 34, 34, 0.72)",
          "image_background": "#ffffff",
          "secondary_button": "#ffffff",
          "secondary_button_label": "#222222"
        }
      }
    ]
  }
}
""".strip() + "\n"

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        query = payload.get("query", "")
        if "query themesForBrandSync" in query:
            return {
                "themes": {
                    "nodes": [
                        {
                            "id": "gid://shopify/OnlineStoreTheme/1",
                            "name": "futrgroup2-0theme",
                            "role": "MAIN",
                        }
                    ]
                }
            }
        if "query themeTemplateFilesForBrandSync" in query:
            return {
                "theme": {
                    "files": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "userErrors": [],
                    }
                }
            }
        if "query themeFileByName" in query:
            requested_filenames = ((payload.get("variables") or {}).get("filenames") or [])
            requested_filename = requested_filenames[0] if requested_filenames else None
            if requested_filename == "layout/theme.liquid":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "layout/theme.liquid",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": (
                                            "<html><head>\n"
                                            "<!-- MOS_WORKSPACE_BRAND_START -->\n"
                                            "{{ 'acme-workspace-workspace-brand.css' | asset_url | stylesheet_tag }}\n"
                                            "<!-- MOS_WORKSPACE_BRAND_END -->\n"
                                            "</head><body></body></html>"
                                        ),
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            if requested_filename == "assets/acme-workspace-workspace-brand.css":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "assets/acme-workspace-workspace-brand.css",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": ":root { --color-brand: #123456; }\n",
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            if requested_filename == "config/settings_data.json":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "config/settings_data.json",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": settings_json,
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.audit_theme_brand(
            shop_domain="example.myshopify.com",
            access_token="token",
            workspace_name="Acme Workspace",
            css_vars=_THEME_SYNC_REQUIRED_CSS_VARS,
            data_theme="light",
            theme_name="futrgroup2-0theme",
        )
    )

    assert result["themeId"] == "gid://shopify/OnlineStoreTheme/1"
    assert result["isReady"] is True
    assert result["hasManagedMarkerBlock"] is True
    assert result["layoutIncludesManagedCssAsset"] is True
    assert result["managedCssAssetExists"] is True
    assert result["coverage"]["missingSourceVars"] == []
    assert result["coverage"]["missingThemeVars"] == []
    assert result["settingsAudit"]["missingPaths"] == []
    assert result["settingsAudit"]["mismatchedPaths"] == []
    assert result["settingsAudit"]["semanticMismatchedPaths"] == []
    assert result["settingsAudit"]["unmappedColorPaths"] == []
    assert result["settingsAudit"]["semanticTypographyMismatchedPaths"] == []
    assert result["settingsAudit"]["unmappedTypographyPaths"] == []


def test_audit_theme_brand_reports_template_component_mismatch():
    client = ShopifyApiClient()
    settings_json = """
{
  "current": {
    "color_background": "#f5f5f5",
    "color_foreground": "#222222",
    "color_button": "#0a8f3c",
    "color_button_text": "#ffffff",
    "color_link": "#123456",
    "color_accent": "#123456",
    "footer_background": "#f4ede6",
    "footer_text": "#222222"
  }
}
""".strip() + "\n"
    template_json = json.dumps(
        {
            "sections": {
                "hero": {
                    "type": "image-with-text-overlay",
                    "settings": {"heading_color": "#ffffff"},
                }
            }
        }
    )

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        query = payload.get("query", "")
        if "query themesForBrandSync" in query:
            return {
                "themes": {
                    "nodes": [
                        {
                            "id": "gid://shopify/OnlineStoreTheme/1",
                            "name": "futrgroup2-0theme",
                            "role": "MAIN",
                        }
                    ]
                }
            }
        if "query themeTemplateFilesForBrandSync" in query:
            return {
                "theme": {
                    "files": {
                        "nodes": [
                            {
                                "filename": "templates/index.json",
                                "body": {"__typename": "OnlineStoreThemeFileBodyText"},
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "userErrors": [],
                    }
                }
            }
        if "query themeFileByName" in query:
            requested_filenames = ((payload.get("variables") or {}).get("filenames") or [])
            requested_filename = requested_filenames[0] if requested_filenames else None
            if requested_filename == "layout/theme.liquid":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "layout/theme.liquid",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": (
                                            "<html><head>\n"
                                            "<!-- MOS_WORKSPACE_BRAND_START -->\n"
                                            "{{ 'acme-workspace-workspace-brand.css' | asset_url | stylesheet_tag }}\n"
                                            "<!-- MOS_WORKSPACE_BRAND_END -->\n"
                                            "</head><body></body></html>"
                                        ),
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            if requested_filename == "assets/acme-workspace-workspace-brand.css":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "assets/acme-workspace-workspace-brand.css",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": ":root { --color-brand: #123456; }\n",
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            if requested_filename == "config/settings_data.json":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "config/settings_data.json",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": settings_json,
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            if requested_filename == "templates/index.json":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "templates/index.json",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": template_json,
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.audit_theme_brand(
            shop_domain="example.myshopify.com",
            access_token="token",
            workspace_name="Acme Workspace",
            css_vars=_THEME_SYNC_REQUIRED_CSS_VARS,
            data_theme="light",
            theme_name="futrgroup2-0theme",
        )
    )

    assert result["isReady"] is False
    assert "templates/index.json.sections.hero.settings.heading_color" in result["settingsAudit"]["semanticMismatchedPaths"]


def test_audit_theme_brand_reports_gaps_for_missing_marker_and_css_asset():
    client = ShopifyApiClient()
    settings_json = '{"current":{"color_background":"#f5f5f5"}}\n'

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        query = payload.get("query", "")
        if "query themesForBrandSync" in query:
            return {
                "themes": {
                    "nodes": [
                        {
                            "id": "gid://shopify/OnlineStoreTheme/1",
                            "name": "futrgroup2-0theme",
                            "role": "MAIN",
                        }
                    ]
                }
            }
        if "query themeTemplateFilesForBrandSync" in query:
            return {
                "theme": {
                    "files": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "userErrors": [],
                    }
                }
            }
        if "query themeFileByName" in query:
            requested_filenames = ((payload.get("variables") or {}).get("filenames") or [])
            requested_filename = requested_filenames[0] if requested_filenames else None
            if requested_filename == "layout/theme.liquid":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "layout/theme.liquid",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": "<html><head></head><body></body></html>",
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            if requested_filename == "assets/acme-workspace-workspace-brand.css":
                return {"theme": {"files": {"nodes": [], "userErrors": []}}}
            if requested_filename == "config/settings_data.json":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "config/settings_data.json",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": settings_json,
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    result = asyncio.run(
        client.audit_theme_brand(
            shop_domain="example.myshopify.com",
            access_token="token",
            workspace_name="Acme Workspace",
            css_vars={"--color-brand": "#123456"},
            data_theme="light",
            theme_name="futrgroup2-0theme",
        )
    )

    assert result["isReady"] is False
    assert result["hasManagedMarkerBlock"] is False
    assert result["layoutIncludesManagedCssAsset"] is False
    assert result["managedCssAssetExists"] is False
    assert "--footer-bg" in result["coverage"]["missingSourceVars"]


def test_sync_theme_brand_errors_when_settings_data_is_empty():
    client = ShopifyApiClient()

    async def fake_admin_graphql(*, shop_domain: str, access_token: str, payload: dict):
        query = payload.get("query", "")
        if "query themesForBrandSync" in query:
            return {
                "themes": {
                    "nodes": [
                        {
                            "id": "gid://shopify/OnlineStoreTheme/1",
                            "name": "futrgroup2-0theme",
                            "role": "MAIN",
                        }
                    ]
                }
            }
        if "query themeTemplateFilesForBrandSync" in query:
            return {
                "theme": {
                    "files": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "userErrors": [],
                    }
                }
            }
        if "query themeFileByName" in query:
            requested_filenames = ((payload.get("variables") or {}).get("filenames") or [])
            requested_filename = requested_filenames[0] if requested_filenames else None
            if requested_filename == "layout/theme.liquid":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "layout/theme.liquid",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": (
                                            "<html><head>\n"
                                            "<!-- MOS_WORKSPACE_BRAND_START -->\n"
                                            "old content\n"
                                            "<!-- MOS_WORKSPACE_BRAND_END -->\n"
                                            "</head><body></body></html>"
                                        ),
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
            if requested_filename == "config/settings_data.json":
                return {
                    "theme": {
                        "files": {
                            "nodes": [
                                {
                                    "filename": "config/settings_data.json",
                                    "body": {
                                        "__typename": "OnlineStoreThemeFileBodyText",
                                        "content": "",
                                    },
                                }
                            ],
                            "userErrors": [],
                        }
                    }
                }
        raise AssertionError("Unexpected query payload")

    client._admin_graphql = fake_admin_graphql  # type: ignore[method-assign]

    with pytest.raises(
        ShopifyApiError,
        match="Theme settings file config/settings_data.json is empty or whitespace-only",
    ):
        asyncio.run(
            client.sync_theme_brand(
                shop_domain="example.myshopify.com",
                access_token="token",
                workspace_name="Acme Workspace",
                brand_name="Acme",
                logo_url="https://assets.example.com/public/assets/logo-1",
                css_vars=_THEME_SYNC_REQUIRED_CSS_VARS,
                font_urls=[],
                data_theme="light",
                theme_name="futrgroup2-0theme",
            )
        )
