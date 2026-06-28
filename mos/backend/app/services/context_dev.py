from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings


class ContextDevConfigError(RuntimeError):
    pass


class ContextDevError(RuntimeError):
    pass


CONTEXT_DEV_BUSINESS_PROFILE_DATAPOINTS: list[dict[str, Any]] = [
    {
        "datapoint_name": "business_name",
        "datapoint_type": "text",
        "datapoint_description": "The business or brand name shown on the website.",
        "datapoint_example": "Acme Studio",
    },
    {
        "datapoint_name": "business_model",
        "datapoint_type": "text",
        "datapoint_description": (
            "How the business appears to make money, such as ecommerce, SaaS subscription, "
            "service business, lead generation, marketplace, course, membership, or other."
        ),
        "datapoint_example": "SaaS subscription",
    },
    {
        "datapoint_name": "primary_offering_kind",
        "datapoint_type": "text",
        "datapoint_description": (
            "Classify the primary thing sold as exactly one of: product, service, software, "
            "course, lead_generation, marketplace, other."
        ),
        "datapoint_example": "service",
    },
    {
        "datapoint_name": "primary_offering_name",
        "datapoint_type": "text",
        "datapoint_description": (
            "The main product, service, software, course, or offer name the business sells."
        ),
        "datapoint_example": "Revenue Sprint",
    },
    {
        "datapoint_name": "primary_offering_description",
        "datapoint_type": "text",
        "datapoint_description": (
            "A factual description of the main offering based only on website evidence."
        ),
        "datapoint_example": (
            "A four-week implementation service for improving lifecycle email revenue."
        ),
    },
    {
        "datapoint_name": "offering_type",
        "datapoint_type": "text",
        "datapoint_description": "The specific product or service type/category in plain language.",
        "datapoint_example": "Email marketing agency",
    },
    {
        "datapoint_name": "category",
        "datapoint_type": "text",
        "datapoint_description": "The broader category or niche the business operates in.",
        "datapoint_example": "B2B marketing services",
    },
    {
        "datapoint_name": "pricing_model",
        "datapoint_type": "text",
        "datapoint_description": (
            "How pricing appears to work, such as one-time, monthly, yearly, per-seat, "
            "hourly, retainer, project-based, quote-based, custom, or unknown."
        ),
        "datapoint_example": "monthly retainer",
    },
    {
        "datapoint_name": "price_or_rate",
        "datapoint_type": "text",
        "datapoint_description": (
            "The visible price, starting price, rate, or pricing note. "
            "Return unknown if not visible."
        ),
        "datapoint_example": "Starting at $2,500/month",
    },
    {
        "datapoint_name": "target_customer",
        "datapoint_type": "text",
        "datapoint_description": (
            "The audience or customer segment explicitly implied by the website."
        ),
        "datapoint_example": "Founder-led B2B SaaS teams",
    },
    {
        "datapoint_name": "key_outcome",
        "datapoint_type": "text",
        "datapoint_description": (
            "The main outcome customers appear to buy, based only on website evidence."
        ),
        "datapoint_example": "Increase qualified demo bookings",
    },
]


@dataclass(frozen=True)
class ContextDevClient:
    api_key: str
    base_url: str = settings.CONTEXT_DEV_BASE_URL
    timeout_seconds: float = settings.CONTEXT_DEV_REQUEST_TIMEOUT_SECONDS

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        response: httpx.Response | None = None
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.request(
                        method,
                        url,
                        params=dict(params or {}),
                        json=dict(json_payload or {}) if json_payload is not None else None,
                        headers=self._headers(),
                    )
            except httpx.HTTPError as exc:
                raise ContextDevError(
                    f"Context.dev request failed for {path}: {exc.__class__.__name__}"
                ) from exc
            if response.status_code != 429 or attempt == max_attempts - 1:
                break
            retry_after = response.headers.get("Retry-After")
            try:
                delay_seconds = float(retry_after) if retry_after else float(2**attempt)
            except ValueError:
                delay_seconds = float(2**attempt)
            time.sleep(min(max(delay_seconds, 0.5), 10.0))
        if response is None:
            raise ContextDevError(f"Context.dev request failed for {path}: no response.")
        if response.status_code >= 400:
            message = ""
            error_code = ""
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    message = str(payload.get("message") or "")
                    error_code = str(payload.get("error_code") or "")
            except ValueError:
                message = response.text[:200]
            detail = f"Context.dev {path} returned status {response.status_code}"
            if error_code:
                detail = f"{detail} ({error_code})"
            if message:
                detail = f"{detail}: {message}"
            raise ContextDevError(detail)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ContextDevError(f"Context.dev {path} returned non-JSON response.") from exc
        if not isinstance(payload, dict):
            raise ContextDevError(f"Context.dev {path} returned an invalid response shape.")
        return payload

    def prefetch_brand(self, *, domain: str) -> dict[str, Any]:
        return self._request("POST", "/brand/prefetch", json_payload={"domain": domain})

    def retrieve_brand(self, *, domain: str) -> dict[str, Any]:
        return self._request("GET", "/brand/retrieve", params={"domain": domain})

    def query_business_profile(self, *, domain: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/brand/ai/query",
            json_payload={
                "domain": domain,
                "specific_pages": {
                    "home_page": True,
                    "about_us": True,
                    "faq": True,
                    "pricing": True,
                    "contact_us": True,
                },
                "data_to_extract": CONTEXT_DEV_BUSINESS_PROFILE_DATAPOINTS,
            },
        )

    def extract_products(self, *, domain: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/brand/ai/products",
            json_payload={"domain": domain, "maxProducts": 6},
        )


def get_context_dev_client() -> ContextDevClient:
    api_key = (settings.CONTEXT_DEV_API_KEY or "").strip()
    if not api_key:
        raise ContextDevConfigError(
            "CONTEXT_DEV_API_KEY is required for existing business extraction."
        )
    return ContextDevClient(api_key=api_key)


def domain_from_url(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    if not parsed.netloc:
        raise ContextDevError("business_url must include a valid domain.")
    return parsed.netloc.lower().removeprefix("www.")


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip() and value.strip().lower() != "unknown":
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
    return None


def _brand_value(payload: Mapping[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _query_values(payload: Mapping[str, Any]) -> dict[str, Any]:
    extracted = payload.get("data_extracted")
    values: dict[str, Any] = {}
    if not isinstance(extracted, list):
        return values
    for item in extracted:
        if not isinstance(item, Mapping):
            continue
        name = item.get("datapoint_name")
        if isinstance(name, str) and name.strip():
            values[name.strip()] = item.get("datapoint_value")
    return values


def _first_product(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    products = payload.get("products")
    if isinstance(products, list):
        for product in products:
            if isinstance(product, Mapping):
                return product
    return {}


def _product_price_value(product: Mapping[str, Any]) -> str | None:
    price = product.get("price")
    if isinstance(price, Mapping):
        amount = price.get("amount")
        currency = price.get("currency")
        billing_frequency = price.get("billing_frequency")
        parts = [
            _first_text(amount),
            _first_text(currency),
            _first_text(billing_frequency),
        ]
        value = " ".join(part for part in parts if part)
        return value or None
    return _first_text(price)


def _product_pricing_model(product: Mapping[str, Any]) -> str | None:
    price = product.get("price")
    if isinstance(price, Mapping):
        return _first_text(price.get("pricing_model"), product.get("pricing_model"))
    return _first_text(product.get("pricing_model"))


def _field(value: Any, *, source: str, endpoint: str, raw_path: str) -> dict[str, Any]:
    normalized_value = value if value not in ("", [], {}) else None
    return {
        "value": normalized_value,
        "provenance": "concrete" if normalized_value is not None else "unknown",
        "provider": "context_dev",
        "endpoint": endpoint,
        "raw_path": raw_path,
        "confidence": "provider_returned" if normalized_value is not None else "unknown",
        "evidence": source if normalized_value is not None else None,
    }


def build_existing_business_review(
    *, business_url: str, competitor_urls: list[str] | None = None
) -> dict[str, Any]:
    client = get_context_dev_client()
    domain = domain_from_url(business_url)
    prefetch: dict[str, Any] = {
        "status": "disabled",
        "provider": "context_dev",
        "endpoint": "/brand/prefetch",
        "note": "Prefetch warms Context.dev cache only; extraction uses retrieve/query/products.",
    }
    if settings.CONTEXT_DEV_PREFETCH_ENABLED:
        try:
            prefetch = client.prefetch_brand(domain=domain)
        except ContextDevError as exc:
            prefetch = {
                "status": "non_blocking_error",
                "provider": "context_dev",
                "endpoint": "/brand/prefetch",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
                "note": "Prefetch warms Context.dev cache only; extraction uses retrieve/query/products.",
            }
    brand = client.retrieve_brand(domain=domain)
    query = client.query_business_profile(domain=domain)
    products = client.extract_products(domain=domain)
    query_values = _query_values(query)
    first_product = _first_product(products)

    brand_name = _first_text(
        query_values.get("business_name"),
        _brand_value(brand, "name"),
        _brand_value(brand, "title"),
        _brand_value(brand, "brand", "name"),
        _brand_value(brand, "brand", "title"),
    )
    product_name = _first_text(first_product.get("name"), query_values.get("primary_offering_name"))
    product_description = _first_text(
        first_product.get("description"),
        query_values.get("primary_offering_description"),
        _brand_value(brand, "description"),
        _brand_value(brand, "brand", "description"),
    )
    price_value = _first_text(query_values.get("price_or_rate"), _product_price_value(first_product))

    fields = {
        "business_name": _field(
            brand_name,
            source="Context.dev brand + AI query",
            endpoint="/brand/retrieve",
            raw_path="brand.name|title",
        ),
        "business_model": _field(
            query_values.get("business_model"),
            source="Context.dev AI query",
            endpoint="/brand/ai/query",
            raw_path="data_extracted.business_model",
        ),
        "offering_kind": _field(
            query_values.get("primary_offering_kind"),
            source="Context.dev AI query",
            endpoint="/brand/ai/query",
            raw_path="data_extracted.primary_offering_kind",
        ),
        "offering_type": _field(
            _first_text(query_values.get("offering_type"), first_product.get("category")),
            source="Context.dev AI query + products",
            endpoint="/brand/ai/query",
            raw_path="data_extracted.offering_type|products[0].category",
        ),
        "offering_name": _field(
            product_name,
            source="Context.dev products + AI query",
            endpoint="/brand/ai/products",
            raw_path="products[0].name",
        ),
        "offering_description": _field(
            product_description,
            source="Context.dev products + AI query",
            endpoint="/brand/ai/products",
            raw_path="products[0].description",
        ),
        "category": _field(
            _first_text(query_values.get("category"), first_product.get("category")),
            source="Context.dev AI query + products",
            endpoint="/brand/ai/query",
            raw_path="data_extracted.category|products[0].category",
        ),
        "pricing_model": _field(
            _first_text(
                query_values.get("pricing_model"),
                _product_pricing_model(first_product),
                first_product.get("billing_frequency"),
            ),
            source="Context.dev AI query + products",
            endpoint="/brand/ai/query",
            raw_path="data_extracted.pricing_model|products[0].price.pricing_model|products[0].pricing_model",
        ),
        "price": _field(
            price_value,
            source="Context.dev AI query + products",
            endpoint="/brand/ai/query",
            raw_path="data_extracted.price_or_rate|products[0].price",
        ),
        "target_customer": _field(
            query_values.get("target_customer"),
            source="Context.dev AI query",
            endpoint="/brand/ai/query",
            raw_path="data_extracted.target_customer",
        ),
        "key_outcome": _field(
            query_values.get("key_outcome"),
            source="Context.dev AI query",
            endpoint="/brand/ai/query",
            raw_path="data_extracted.key_outcome",
        ),
    }

    return {
        "provider": "context_dev",
        "domain": domain,
        "business_url": business_url,
        "competitor_urls": competitor_urls or [],
        "fields": fields,
        "raw": {
            "prefetch": prefetch,
            "brand": brand,
            "query": query,
            "products": products,
        },
        "requests": {
            "prefetch_brand": {
                "endpoint": "/brand/prefetch",
                "body": {"domain": domain},
                "blocking": False,
            },
            "retrieve_brand": {"endpoint": "/brand/retrieve", "params": {"domain": domain}},
            "query_business_profile": {
                "endpoint": "/brand/ai/query",
                "data_to_extract": CONTEXT_DEV_BUSINESS_PROFILE_DATAPOINTS,
            },
            "extract_products": {
                "endpoint": "/brand/ai/products",
                "body": {"domain": domain, "maxProducts": 6},
            },
        },
    }
