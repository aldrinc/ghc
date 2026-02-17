from __future__ import annotations

import pytest

from app.schemas import CreateCheckoutRequest, VerifyProductRequest


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
