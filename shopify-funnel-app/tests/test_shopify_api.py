from __future__ import annotations

import asyncio

import pytest

from app.shopify_api import ShopifyApiClient, ShopifyApiError


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
