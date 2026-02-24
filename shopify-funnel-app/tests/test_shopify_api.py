from __future__ import annotations

import asyncio

import pytest

from app.shopify_api import ShopifyApiClient, ShopifyApiError

_THEME_SYNC_REQUIRED_CSS_VARS = {
    "--color-page-bg": "#f5f5f5",
    "--color-bg": "#ffffff",
    "--color-text": "#222222",
    "--color-brand": "#123456",
    "--color-cta": "#0a8f3c",
    "--color-cta-text": "#ffffff",
    "--color-border": "rgba(0, 0, 0, 0.2)",
    "--color-soft": "rgba(0, 0, 0, 0.08)",
    "--focus-outline-color": "rgba(6, 26, 112, 0.35)",
    "--font-sans": "Inter, sans-serif",
    "--radius-md": "14px",
    "--container-max": "1380px",
    "--container-pad": "24px",
    "--section-pad-y": "120px",
    "--footer-bg": "#f4ede6",
}


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
        '{"current":{"settings":{"color_background":"#ffffff","color_foreground":"#111111","color_button":"#000000",'
        '"color_button_text":"#ffffff","color_link":"#000000","color_accent":"#000000","footer_background":"#ffffff",'
        '"footer_text":"#111111","color_schemes":[{"settings":{"background":"#ffffff","text":"#111111","button":"#000000",'
        '"button_label":"#ffffff","secondary_button":"#eeeeee","secondary_button_label":"#111111"}}]}}}\n'
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
            assert "--font-body-family: var(--font-sans) !important;" in css_content
            assert "--border-radius-medium: var(--radius-md) !important;" in css_content
            assert "--page-width: var(--container-max) !important;" in css_content
            assert "--page-padding: var(--container-pad) !important;" in css_content
            assert "--footer-pad-y: var(--section-pad-y) !important;" in css_content
            assert "--mos-brand-logo-url: \"https://assets.example.com/public/assets/logo-1\";" in css_content
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
                "current.settings.color_accent",
                "current.settings.color_background",
                "current.settings.color_button",
                "current.settings.color_button_text",
                "current.settings.color_foreground",
                "current.settings.color_link",
                "current.settings.color_schemes[*].settings.background",
                "current.settings.color_schemes[*].settings.button",
                "current.settings.color_schemes[*].settings.button_label",
                "current.settings.color_schemes[*].settings.secondary_button",
                "current.settings.color_schemes[*].settings.secondary_button_label",
                "current.settings.color_schemes[*].settings.text",
                "current.settings.footer_background",
                "current.settings.footer_text",
            ],
            "updatedPaths": [
                "current.settings.color_accent",
                "current.settings.color_background",
                "current.settings.color_button",
                "current.settings.color_button_text",
                "current.settings.color_foreground",
                "current.settings.color_link",
                "current.settings.color_schemes[*].settings.background",
                "current.settings.color_schemes[*].settings.button",
                "current.settings.color_schemes[*].settings.button_label",
                "current.settings.color_schemes[*].settings.secondary_button",
                "current.settings.color_schemes[*].settings.secondary_button_label",
                "current.settings.color_schemes[*].settings.text",
                "current.settings.footer_background",
                "current.settings.footer_text",
            ],
            "missingPaths": [],
            "requiredMissingPaths": [],
        },
    }
    assert len(observed_payloads) == 5


def test_sync_theme_brand_allows_upsert_without_job():
    client = ShopifyApiClient()
    observed_payloads: list[dict] = []
    settings_json = '\ufeff{"current":{"settings":{"color_background":"#ffffff"}}}\n'

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
                "current.settings.color_accent",
                "current.settings.color_background",
                "current.settings.color_button",
                "current.settings.color_button_text",
                "current.settings.color_foreground",
                "current.settings.color_link",
                "current.settings.color_schemes[*].settings.background",
                "current.settings.color_schemes[*].settings.button",
                "current.settings.color_schemes[*].settings.button_label",
                "current.settings.color_schemes[*].settings.secondary_button",
                "current.settings.color_schemes[*].settings.secondary_button_label",
                "current.settings.color_schemes[*].settings.text",
                "current.settings.footer_background",
                "current.settings.footer_text",
            ],
            "updatedPaths": ["current.settings.color_background"],
            "missingPaths": [
                "current.settings.color_accent",
                "current.settings.color_button",
                "current.settings.color_button_text",
                "current.settings.color_foreground",
                "current.settings.color_link",
                "current.settings.color_schemes[*].settings.background",
                "current.settings.color_schemes[*].settings.button",
                "current.settings.color_schemes[*].settings.button_label",
                "current.settings.color_schemes[*].settings.secondary_button",
                "current.settings.color_schemes[*].settings.secondary_button_label",
                "current.settings.color_schemes[*].settings.text",
                "current.settings.footer_background",
                "current.settings.footer_text",
            ],
            "requiredMissingPaths": [],
        },
    }
    assert len(observed_payloads) == 4


def test_sync_theme_brand_requires_managed_layout_markers():
    client = ShopifyApiClient()
    settings_json = '{"current":{"settings":{"color_background":"#ffffff"}}}\n'

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
    settings_json = '{"current":{"settings":{"color_background":"#ffffff"}}}\n'

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


def test_sync_theme_brand_skips_compat_aliases_for_other_theme():
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
        if "mutation themeFilesUpsert" in query:
            files = (payload.get("variables") or {}).get("files") or []
            css_file = next(item for item in files if item["filename"] == "assets/acme-workspace-workspace-brand.css")
            css_content = css_file["body"]["value"]
            assert "--color-brand: #123456 !important;" in css_content
            assert "--color-highlight: var(--color-brand) !important;" not in css_content
            return {
                "themeFilesUpsert": {
                    "upsertedThemeFiles": [
                        {"filename": "layout/theme.liquid"},
                        {"filename": "assets/acme-workspace-workspace-brand.css"},
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
            css_vars={"--color-brand": "#123456"},
            font_urls=[],
            data_theme="light",
            theme_name="custom-theme",
        )
    )

    assert result["themeName"] == "custom-theme"
    assert result["jobId"] is None


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

    assert ':root, html, body, .color-scheme, .gradient, .footer, [data-color-scheme], [class*="color-scheme"], [class*="scheme-"], [class*="color-"], [class*="footer"] {' in css
    assert 'html[data-theme="light"] .footer {' not in css
    assert 'html[data-theme="light"], html[data-theme="light"] html, html[data-theme="light"] body, html[data-theme="light"] .color-scheme' in css
    assert 'html[data-theme="light"] [class*="footer"] {' in css
    assert '--footer-bg: #f4ede6 !important;' in css


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
    "settings": {
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
            "secondary_button": "#ffffff",
            "secondary_button_label": "#222222"
          }
        }
      ]
    }
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


def test_audit_theme_brand_reports_gaps_for_missing_marker_and_css_asset():
    client = ShopifyApiClient()
    settings_json = '{"current":{"settings":{"color_background":"#f5f5f5"}}}\n'

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
