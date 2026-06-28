from __future__ import annotations

from typing import Any

from app.services import context_dev


class _FakeContextDevClient:
    def prefetch_brand(self, *, domain: str) -> dict[str, Any]:
        raise context_dev.ContextDevError(
            "Context.dev /brand/prefetch returned status 403 (FORBIDDEN): Prefetch endpoints require a paid plan."
        )

    def retrieve_brand(self, *, domain: str) -> dict[str, Any]:
        return {
            "brand": {
                "title": "Example Brand",
                "description": "Provider returned brand description.",
            }
        }

    def query_business_profile(self, *, domain: str) -> dict[str, Any]:
        return {
            "data_extracted": [
                {"datapoint_name": "business_model", "datapoint_value": "SaaS subscription"},
                {"datapoint_name": "primary_offering_kind", "datapoint_value": "software"},
                {"datapoint_name": "primary_offering_name", "datapoint_value": "Example Platform"},
                {"datapoint_name": "pricing_model", "datapoint_value": "unknown"},
                {"datapoint_name": "price_or_rate", "datapoint_value": "unknown"},
            ]
        }

    def extract_products(self, *, domain: str) -> dict[str, Any]:
        return {
            "products": [
                {
                    "name": "Example Platform",
                    "description": "Provider returned product description.",
                    "category": "Marketing software",
                    "price": {
                        "amount": 99,
                        "currency": "USD",
                        "billing_frequency": "monthly",
                        "pricing_model": "subscription",
                    },
                }
            ]
        }


def test_existing_business_review_does_not_block_on_prefetch_plan_error(monkeypatch):
    monkeypatch.setattr(context_dev.settings, "CONTEXT_DEV_PREFETCH_ENABLED", True)
    monkeypatch.setattr(context_dev, "get_context_dev_client", lambda: _FakeContextDevClient())

    review = context_dev.build_existing_business_review(
        business_url="https://example.com",
        competitor_urls=["https://competitor.example"],
    )

    assert review["provider"] == "context_dev"
    assert review["domain"] == "example.com"
    assert review["competitor_urls"] == ["https://competitor.example"]
    assert review["raw"]["prefetch"]["status"] == "non_blocking_error"
    assert review["requests"]["prefetch_brand"]["blocking"] is False
    assert review["fields"]["business_name"]["value"] == "Example Brand"
    assert review["fields"]["pricing_model"]["value"] == "subscription"
    assert review["fields"]["price"]["value"] == "99 USD monthly"
