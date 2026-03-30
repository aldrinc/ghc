#!/usr/bin/env python3
"""Ensure local Medusa exposes US shipping options for checkout testing.

This script logs into the Medusa Admin API, finds an existing non-return
shipping configuration to use as the template, ensures a US service zone exists
on the same fulfillment set, and then creates or reconciles US shipping options
so Store API carts in the US region can rate shipping.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

import httpx


DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("MEDUSA_TIMEOUT_SECONDS", "30"))
DEFAULT_BASE_URL = os.environ.get("MEDUSA_BASE_URL", "http://localhost:9000").rstrip("/")
DEFAULT_ADMIN_EMAIL = os.environ.get("MEDUSA_ADMIN_EMAIL", "admin@test.com").strip()
DEFAULT_ADMIN_PASSWORD = os.environ.get("MEDUSA_ADMIN_PASSWORD", "supersecret")
TARGET_COUNTRY_CODE = os.environ.get("MEDUSA_TARGET_COUNTRY_CODE", "us").strip().lower()
TARGET_SERVICE_ZONE_NAME = os.environ.get(
    "MEDUSA_TARGET_SERVICE_ZONE_NAME", "United States"
).strip()


class ProvisionError(RuntimeError):
    """Raised when the Medusa store is not in a usable state for provisioning."""


@dataclass(frozen=True)
class DesiredShippingOption:
    name: str
    shipping_profile_id: str
    provider_id: str
    price_type: str
    option_type: dict[str, Any]
    rules: list[dict[str, str]]
    prices: list[dict[str, Any]]


def _clean_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise ProvisionError(
            f"Medusa returned invalid JSON for {response.request.method} {response.request.url.path}"
        ) from exc


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase or f"HTTP {response.status_code}"

    if isinstance(payload, dict):
        for key in ("message", "detail", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return str(payload)

    return str(payload)


class MedusaAdminClient:
    def __init__(self, *, base_url: str, token: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(
                timeout=timeout_seconds,
                connect=min(timeout_seconds, 10.0),
            ),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        response = self._client.request(method, path, json=json_body, params=params)
        if response.status_code >= 400:
            raise ProvisionError(
                f"Medusa Admin API {method} {path} failed with {response.status_code}: {_error_detail(response)}"
            )
        if response.status_code == 204 or not response.content:
            return None
        return _clean_json(response)


def login(*, base_url: str, email: str, password: str, timeout_seconds: float) -> str:
    response = httpx.post(
        f"{base_url.rstrip('/')}/auth/user/emailpass",
        json={"email": email, "password": password},
        timeout=httpx.Timeout(
            timeout=timeout_seconds,
            connect=min(timeout_seconds, 10.0),
        ),
    )
    if response.status_code >= 400:
        raise ProvisionError(
            f"Medusa login failed with {response.status_code}: {_error_detail(response)}"
        )

    payload = _clean_json(response)
    if not isinstance(payload, dict) or not isinstance(payload.get("token"), str):
        raise ProvisionError("Medusa login response did not include an admin token.")

    return payload["token"]


def _extract_region_for_country(regions: list[dict[str, Any]], country_code: str) -> dict[str, Any]:
    for region in regions:
        countries = region.get("countries") or []
        if not isinstance(countries, list):
            continue
        for country in countries:
            if not isinstance(country, dict):
                continue
            if str(country.get("iso_2") or "").strip().lower() == country_code:
                return region
    raise ProvisionError(
        f"No Medusa region is configured for country code '{country_code}'. Add the region before provisioning shipping."
    )


def _is_return_option(option: dict[str, Any]) -> bool:
    for rule in option.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        if rule.get("attribute") == "is_return":
            return str(rule.get("value") or "").strip().lower() == "true"
    return False


def _normalized_rules(rules: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        attribute = str(rule.get("attribute") or "").strip()
        operator = str(rule.get("operator") or "").strip()
        value = str(rule.get("value") or "").strip()
        if not attribute or not operator:
            continue
        cleaned.append(
            {
                "attribute": attribute,
                "operator": operator,
                "value": value,
            }
        )
    cleaned.sort(key=lambda item: (item["attribute"], item["operator"], item["value"]))
    return cleaned


def _desired_amount_for_region(
    option: dict[str, Any],
    *,
    region_id: str,
    currency_code: str,
) -> int:
    fallback_amount: int | None = None

    for price in option.get("prices") or []:
        if not isinstance(price, dict):
            continue
        raw_amount = price.get("amount")
        if isinstance(raw_amount, (int, float)):
            amount = int(raw_amount)
        else:
            continue

        if fallback_amount is None:
            fallback_amount = amount

        price_rules = price.get("price_rules") or []
        if any(
            isinstance(rule, dict)
            and rule.get("attribute") == "region_id"
            and str(rule.get("value") or "").strip() == region_id
            for rule in price_rules
        ):
            return amount

        if not price_rules and str(price.get("currency_code") or "").strip().lower() == currency_code:
            return amount

    if fallback_amount is None:
        raise ProvisionError(f"Shipping option '{option.get('name')}' has no usable prices.")

    return fallback_amount


def _build_desired_option(
    template_option: dict[str, Any],
    *,
    region_id: str,
    currency_code: str,
) -> DesiredShippingOption:
    option_type = template_option.get("type")
    if not isinstance(option_type, dict):
        raise ProvisionError(f"Shipping option '{template_option.get('name')}' is missing its type payload.")

    amount = _desired_amount_for_region(
        template_option,
        region_id=region_id,
        currency_code=currency_code,
    )

    return DesiredShippingOption(
        name=str(template_option.get("name") or "").strip(),
        shipping_profile_id=str(template_option.get("shipping_profile_id") or "").strip(),
        provider_id=str(template_option.get("provider_id") or "").strip(),
        price_type=str(template_option.get("price_type") or "").strip(),
        option_type={
            "label": str(option_type.get("label") or "").strip(),
            "description": str(option_type.get("description") or "").strip(),
            "code": str(option_type.get("code") or "").strip(),
        },
        rules=_normalized_rules(template_option.get("rules")),
        prices=[
            {"currency_code": currency_code, "amount": amount},
            {"region_id": region_id, "amount": amount},
        ],
    )


def _matches_desired(
    current_option: dict[str, Any],
    desired: DesiredShippingOption,
    *,
    region_id: str,
    currency_code: str,
) -> bool:
    if str(current_option.get("name") or "").strip() != desired.name:
        return False
    if str(current_option.get("provider_id") or "").strip() != desired.provider_id:
        return False
    if str(current_option.get("shipping_profile_id") or "").strip() != desired.shipping_profile_id:
        return False
    if str(current_option.get("price_type") or "").strip() != desired.price_type:
        return False

    current_type = current_option.get("type") or {}
    if not isinstance(current_type, dict):
        return False
    for key, expected in desired.option_type.items():
        if str(current_type.get(key) or "").strip() != expected:
            return False

    if _normalized_rules(current_option.get("rules")) != desired.rules:
        return False

    currency_amount: int | None = None
    region_amount: int | None = None
    for price in current_option.get("prices") or []:
        if not isinstance(price, dict):
            continue
        raw_amount = price.get("amount")
        if not isinstance(raw_amount, (int, float)):
            continue
        amount = int(raw_amount)
        price_rules = price.get("price_rules") or []
        has_region_rule = any(
            isinstance(rule, dict)
            and rule.get("attribute") == "region_id"
            and str(rule.get("value") or "").strip() == region_id
            for rule in price_rules
        )
        if has_region_rule:
            region_amount = amount
        elif not price_rules and str(price.get("currency_code") or "").strip().lower() == currency_code:
            currency_amount = amount

    desired_amount = desired.prices[0]["amount"]
    return currency_amount == desired_amount and region_amount == desired_amount


def _create_shipping_option(
    admin: MedusaAdminClient,
    desired: DesiredShippingOption,
    *,
    service_zone_id: str,
) -> dict[str, Any]:
    payload = {
        "name": desired.name,
        "service_zone_id": service_zone_id,
        "shipping_profile_id": desired.shipping_profile_id,
        "provider_id": desired.provider_id,
        "price_type": desired.price_type,
        "type": desired.option_type,
        "prices": desired.prices,
        "rules": desired.rules,
    }
    response = admin.request("POST", "/admin/shipping-options", json_body=payload)
    shipping_option = response.get("shipping_option") if isinstance(response, dict) else None
    if not isinstance(shipping_option, dict):
        raise ProvisionError(f"Medusa did not return a shipping option when creating '{desired.name}'.")
    return shipping_option


def ensure_us_shipping(
    *,
    base_url: str,
    email: str,
    password: str,
    timeout_seconds: float,
) -> None:
    token = login(
        base_url=base_url,
        email=email,
        password=password,
        timeout_seconds=timeout_seconds,
    )
    admin = MedusaAdminClient(
        base_url=base_url,
        token=token,
        timeout_seconds=timeout_seconds,
    )

    try:
        regions_response = admin.request("GET", "/admin/regions", params={"limit": 200})
        regions = regions_response.get("regions") if isinstance(regions_response, dict) else None
        if not isinstance(regions, list):
            raise ProvisionError("Medusa regions response is invalid.")
        target_region = _extract_region_for_country(regions, TARGET_COUNTRY_CODE)
        target_region_id = str(target_region.get("id") or "").strip()
        target_currency_code = str(target_region.get("currency_code") or "").strip().lower()
        if not target_region_id or not target_currency_code:
            raise ProvisionError("Medusa target region is missing id or currency code.")

        shipping_options_response = admin.request(
            "GET",
            "/admin/shipping-options",
            params={"limit": 200},
        )
        all_shipping_options = (
            shipping_options_response.get("shipping_options")
            if isinstance(shipping_options_response, dict)
            else None
        )
        if not isinstance(all_shipping_options, list):
            raise ProvisionError("Medusa shipping options response is invalid.")

        template_options = [
            option
            for option in all_shipping_options
            if isinstance(option, dict)
            and not _is_return_option(option)
            and str(option.get("service_zone", {}).get("name") or "").strip() != TARGET_SERVICE_ZONE_NAME
        ]
        if not template_options:
            raise ProvisionError(
                "No existing non-return shipping options were found to clone for US checkout."
            )

        template_zone = template_options[0].get("service_zone") or {}
        if not isinstance(template_zone, dict):
            raise ProvisionError("Template shipping option is missing its service zone.")
        template_fulfillment_set = template_zone.get("fulfillment_set") or {}
        if not isinstance(template_fulfillment_set, dict):
            raise ProvisionError("Template shipping option is missing its fulfillment set.")

        fulfillment_set_id = str(template_fulfillment_set.get("id") or "").strip()
        source_service_zone_id = str(template_zone.get("id") or "").strip()
        if not fulfillment_set_id or not source_service_zone_id:
            raise ProvisionError("Template shipping option is missing fulfillment or service zone IDs.")

        template_options = [
            option
            for option in template_options
            if str(option.get("service_zone_id") or "").strip() == source_service_zone_id
        ]

        stock_locations_response = admin.request(
            "GET",
            "/admin/stock-locations",
            params={"limit": 200},
        )
        stock_locations = (
            stock_locations_response.get("stock_locations")
            if isinstance(stock_locations_response, dict)
            else None
        )
        if not isinstance(stock_locations, list):
            raise ProvisionError("Medusa stock locations response is invalid.")

        matching_stock_location: dict[str, Any] | None = None
        matching_fulfillment_set: dict[str, Any] | None = None

        for stock_location in stock_locations:
            if not isinstance(stock_location, dict):
                continue
            location_id = str(stock_location.get("id") or "").strip()
            if not location_id:
                continue
            detail_response = admin.request(
                "GET",
                f"/admin/stock-locations/{location_id}",
                params={
                    "fields": "id,name,*fulfillment_sets,*fulfillment_sets.service_zones,*fulfillment_sets.service_zones.geo_zones"
                },
            )
            location = detail_response.get("stock_location") if isinstance(detail_response, dict) else None
            if not isinstance(location, dict):
                continue
            for fulfillment_set in location.get("fulfillment_sets") or []:
                if not isinstance(fulfillment_set, dict):
                    continue
                if str(fulfillment_set.get("id") or "").strip() == fulfillment_set_id:
                    matching_stock_location = location
                    matching_fulfillment_set = fulfillment_set
                    break
            if matching_fulfillment_set is not None:
                break

        if matching_stock_location is None or matching_fulfillment_set is None:
            raise ProvisionError(
                f"Could not find the stock location for fulfillment set '{fulfillment_set_id}'."
            )

        target_service_zone: dict[str, Any] | None = None
        for service_zone in matching_fulfillment_set.get("service_zones") or []:
            if not isinstance(service_zone, dict):
                continue
            geo_zones = service_zone.get("geo_zones") or []
            if any(
                isinstance(geo_zone, dict)
                and str(geo_zone.get("country_code") or "").strip().lower() == TARGET_COUNTRY_CODE
                for geo_zone in geo_zones
            ):
                target_service_zone = service_zone
                break

        if target_service_zone is None:
            created = admin.request(
                "POST",
                f"/admin/fulfillment-sets/{fulfillment_set_id}/service-zones",
                json_body={
                    "name": TARGET_SERVICE_ZONE_NAME,
                    "geo_zones": [{"type": "country", "country_code": TARGET_COUNTRY_CODE}],
                },
            )
            fulfillment_set = created.get("fulfillment_set") if isinstance(created, dict) else None
            if not isinstance(fulfillment_set, dict):
                raise ProvisionError("Medusa did not return the fulfillment set after creating the US service zone.")
            for service_zone in fulfillment_set.get("service_zones") or []:
                if not isinstance(service_zone, dict):
                    continue
                geo_zones = service_zone.get("geo_zones") or []
                if any(
                    isinstance(geo_zone, dict)
                    and str(geo_zone.get("country_code") or "").strip().lower() == TARGET_COUNTRY_CODE
                    for geo_zone in geo_zones
                ):
                    target_service_zone = service_zone
                    break

        if target_service_zone is None:
            raise ProvisionError("US service zone was not available after the create attempt.")

        target_service_zone_id = str(target_service_zone.get("id") or "").strip()
        if not target_service_zone_id:
            raise ProvisionError("US service zone is missing its id.")

        refresh_response = admin.request(
            "GET",
            "/admin/shipping-options",
            params={"limit": 200},
        )
        refreshed_options = (
            refresh_response.get("shipping_options") if isinstance(refresh_response, dict) else None
        )
        if not isinstance(refreshed_options, list):
            raise ProvisionError("Could not refresh Medusa shipping options.")

        existing_target_options = {
            str(option.get("name") or "").strip(): option
            for option in refreshed_options
            if isinstance(option, dict)
            and str(option.get("service_zone_id") or "").strip() == target_service_zone_id
            and not _is_return_option(option)
        }

        created_names: list[str] = []
        updated_names: list[str] = []
        retained_names: list[str] = []

        for template_option in template_options:
            desired = _build_desired_option(
                template_option,
                region_id=target_region_id,
                currency_code=target_currency_code,
            )
            if not desired.name:
                raise ProvisionError("Encountered a template shipping option without a name.")

            current = existing_target_options.get(desired.name)
            if current is not None and _matches_desired(
                current,
                desired,
                region_id=target_region_id,
                currency_code=target_currency_code,
            ):
                retained_names.append(desired.name)
                continue

            if current is not None:
                current_id = str(current.get("id") or "").strip()
                if not current_id:
                    raise ProvisionError(f"Existing US shipping option '{desired.name}' is missing its id.")
                admin.request("DELETE", f"/admin/shipping-options/{current_id}")
                updated_names.append(desired.name)
            else:
                created_names.append(desired.name)

            _create_shipping_option(
                admin,
                desired,
                service_zone_id=target_service_zone_id,
            )

        print(f"Region: {target_region.get('name')} ({target_region_id})")
        print(f"Target service zone: {target_service_zone.get('name')} ({target_service_zone_id})")
        if created_names:
            print("Created shipping options: " + ", ".join(created_names))
        if updated_names:
            print("Reconciled shipping options: " + ", ".join(updated_names))
        if retained_names:
            print("Already correct: " + ", ".join(retained_names))

    finally:
        admin.close()


def main() -> int:
    try:
        ensure_us_shipping(
            base_url=DEFAULT_BASE_URL,
            email=DEFAULT_ADMIN_EMAIL,
            password=DEFAULT_ADMIN_PASSWORD,
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        )
    except ProvisionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
