from __future__ import annotations

import pytest

from app.schemas import (
    CreateCatalogProductRequest,
    CreateCheckoutRequest,
    ListProductsRequest,
    UpdateCatalogVariantRequest,
    UpsertPolicyPagesRequest,
    VerifyProductRequest,
)


def test_create_checkout_request_requires_exactly_one_target():
    with pytest.raises(ValueError):
        CreateCheckoutRequest(
            lines=[{"merchandiseId": "gid://shopify/ProductVariant/1", "quantity": 1}],
        )

    with pytest.raises(ValueError):
        CreateCheckoutRequest(
            clientId="client_1",
            shopDomain="example.myshopify.com",
            lines=[{"merchandiseId": "gid://shopify/ProductVariant/1", "quantity": 1}],
        )


def test_create_checkout_request_accepts_client_target():
    payload = CreateCheckoutRequest(
        clientId="client_1",
        lines=[{"merchandiseId": "gid://shopify/ProductVariant/1", "quantity": 2}],
    )

    assert payload.clientId == "client_1"
    assert payload.shopDomain is None


def test_verify_product_request_requires_exactly_one_target():
    with pytest.raises(ValueError):
        VerifyProductRequest(productGid="gid://shopify/Product/1")

    with pytest.raises(ValueError):
        VerifyProductRequest(
            clientId="client_1",
            shopDomain="example.myshopify.com",
            productGid="gid://shopify/Product/1",
        )


def test_verify_product_request_accepts_shop_target():
    payload = VerifyProductRequest(
        shopDomain="example.myshopify.com",
        productGid="gid://shopify/Product/123",
    )

    assert payload.shopDomain == "example.myshopify.com"
    assert payload.clientId is None


def test_list_products_request_requires_exactly_one_target():
    with pytest.raises(ValueError):
        ListProductsRequest()

    with pytest.raises(ValueError):
        ListProductsRequest(clientId="client_1", shopDomain="example.myshopify.com")


def test_list_products_request_accepts_client_target():
    payload = ListProductsRequest(clientId="client_1", query="sleep", limit=10)

    assert payload.clientId == "client_1"
    assert payload.shopDomain is None
    assert payload.query == "sleep"
    assert payload.limit == 10


def test_create_catalog_product_request_requires_exactly_one_target():
    with pytest.raises(ValueError):
        CreateCatalogProductRequest(
            title="Sleep Drops",
            variants=[{"title": "Default", "priceCents": 9900, "currency": "USD"}],
        )

    with pytest.raises(ValueError):
        CreateCatalogProductRequest(
            clientId="client_1",
            shopDomain="example.myshopify.com",
            title="Sleep Drops",
            variants=[{"title": "Default", "priceCents": 9900, "currency": "USD"}],
        )


def test_create_catalog_product_request_accepts_shop_target():
    payload = CreateCatalogProductRequest(
        shopDomain="example.myshopify.com",
        title="Sleep Drops",
        status="DRAFT",
        variants=[{"title": "Default", "priceCents": 9900, "currency": "USD"}],
    )

    assert payload.clientId is None
    assert payload.shopDomain == "example.myshopify.com"
    assert payload.status == "DRAFT"


def test_update_catalog_variant_request_requires_exactly_one_target():
    with pytest.raises(ValueError):
        UpdateCatalogVariantRequest(
            variantGid="gid://shopify/ProductVariant/1",
            priceCents=4900,
        )

    with pytest.raises(ValueError):
        UpdateCatalogVariantRequest(
            clientId="client_1",
            shopDomain="example.myshopify.com",
            variantGid="gid://shopify/ProductVariant/1",
            priceCents=4900,
        )


def test_update_catalog_variant_request_requires_update_fields():
    with pytest.raises(ValueError):
        UpdateCatalogVariantRequest(
            clientId="client_1",
            variantGid="gid://shopify/ProductVariant/1",
        )


def test_update_catalog_variant_request_accepts_compare_at_price_clear():
    payload = UpdateCatalogVariantRequest(
        shopDomain="example.myshopify.com",
        variantGid="gid://shopify/ProductVariant/1",
        compareAtPriceCents=None,
    )

    assert payload.clientId is None
    assert payload.shopDomain == "example.myshopify.com"
    assert payload.compareAtPriceCents is None


def test_update_catalog_variant_request_accepts_inventory_fields():
    payload = UpdateCatalogVariantRequest(
        clientId="client_1",
        variantGid="gid://shopify/ProductVariant/1",
        sku="SKU-001",
        barcode="BAR-001",
        inventoryPolicy="continue",
        inventoryManagement="shopify",
    )

    assert payload.clientId == "client_1"
    assert payload.sku == "SKU-001"
    assert payload.barcode == "BAR-001"
    assert payload.inventoryPolicy == "continue"
    assert payload.inventoryManagement == "shopify"


def test_upsert_policy_pages_request_requires_exactly_one_target():
    with pytest.raises(ValueError):
        UpsertPolicyPagesRequest(
            pages=[
                {
                    "pageKey": "privacy_policy",
                    "title": "Privacy Policy",
                    "handle": "privacy-policy",
                    "bodyHtml": "<p>hello</p>",
                }
            ],
        )

    with pytest.raises(ValueError):
        UpsertPolicyPagesRequest(
            clientId="client_1",
            shopDomain="example.myshopify.com",
            pages=[
                {
                    "pageKey": "privacy_policy",
                    "title": "Privacy Policy",
                    "handle": "privacy-policy",
                    "bodyHtml": "<p>hello</p>",
                }
            ],
        )


def test_upsert_policy_pages_request_accepts_client_target():
    payload = UpsertPolicyPagesRequest(
        clientId="client_1",
        pages=[
            {
                "pageKey": "privacy_policy",
                "title": "Privacy Policy",
                "handle": "privacy-policy",
                "bodyHtml": "<p>hello</p>",
            }
        ],
    )

    assert payload.clientId == "client_1"
    assert payload.shopDomain is None
