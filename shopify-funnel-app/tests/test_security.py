from __future__ import annotations

import hashlib
import hmac

from app.security import normalize_shop_domain, verify_oauth_hmac


def _oauth_hmac(query_items: list[tuple[str, str]], secret: str) -> str:
    pairs = [item for item in query_items if item[0] not in {"hmac", "signature"}]
    pairs.sort(key=lambda item: item[0])
    message = "&".join(f"{key}={value}" for key, value in pairs)
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def test_normalize_shop_domain_accepts_valid_domain():
    assert normalize_shop_domain(" Example-Shop.myshopify.com ") == "example-shop.myshopify.com"


def test_verify_oauth_hmac_accepts_valid_signature():
    query_items = [
        ("code", "abc"),
        ("shop", "example-shop.myshopify.com"),
        ("state", "state-123"),
        ("timestamp", "1710000000"),
    ]
    digest = _oauth_hmac(query_items, "test_secret")
    query_items.append(("hmac", digest))

    assert verify_oauth_hmac(query_items)


def test_verify_oauth_hmac_rejects_invalid_signature():
    query_items = [
        ("code", "abc"),
        ("shop", "example-shop.myshopify.com"),
        ("state", "state-123"),
        ("timestamp", "1710000000"),
        ("hmac", "invalid"),
    ]

    assert not verify_oauth_hmac(query_items)
