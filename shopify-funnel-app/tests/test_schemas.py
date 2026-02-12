from __future__ import annotations

import pytest

from app.schemas import CreateCheckoutRequest


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
