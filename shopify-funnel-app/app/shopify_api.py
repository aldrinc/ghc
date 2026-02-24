from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html import escape
import re
from typing import Any, Literal

import httpx

from app.config import settings

_THEME_BRAND_LAYOUT_FILENAME = "layout/theme.liquid"
_THEME_BRAND_MARKER_START = "<!-- MOS_WORKSPACE_BRAND_START -->"
_THEME_BRAND_MARKER_END = "<!-- MOS_WORKSPACE_BRAND_END -->"


class ShopifyApiError(RuntimeError):
    def __init__(self, *, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class ShopifyApiClient:
    def __init__(self) -> None:
        self._timeout = settings.SHOPIFY_REQUEST_TIMEOUT_SECONDS

    async def exchange_code_for_access_token(self, *, shop_domain: str, code: str) -> tuple[str, str]:
        url = f"https://{shop_domain}/admin/oauth/access_token"
        payload = {
            "client_id": settings.SHOPIFY_APP_API_KEY,
            "client_secret": settings.SHOPIFY_APP_API_SECRET,
            "code": code,
        }
        response = await self._post_json(url=url, payload=payload)
        access_token = response.get("access_token")
        scopes = response.get("scope")
        if not isinstance(access_token, str) or not access_token:
            raise ShopifyApiError(message="OAuth token exchange response is missing access_token")
        if not isinstance(scopes, str):
            raise ShopifyApiError(message="OAuth token exchange response is missing scope")
        return access_token, scopes

    async def register_webhook(
        self,
        *,
        shop_domain: str,
        access_token: str,
        topic: str,
        callback_url: str,
    ) -> str:
        query = """
        mutation webhookSubscriptionCreate(
            $topic: WebhookSubscriptionTopic!
            $webhookSubscription: WebhookSubscriptionInput!
        ) {
            webhookSubscriptionCreate(topic: $topic, webhookSubscription: $webhookSubscription) {
                webhookSubscription {
                    id
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        payload = {
            "query": query,
            "variables": {
                "topic": topic,
                "webhookSubscription": {
                    "callbackUrl": callback_url,
                    "format": "JSON",
                },
            },
        }
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        create_data = response.get("webhookSubscriptionCreate") or {}
        user_errors = create_data.get("userErrors") or []
        if user_errors:
            if self._has_duplicate_webhook_address_error(user_errors):
                existing_id = await self._find_existing_http_webhook_id(
                    shop_domain=shop_domain,
                    access_token=access_token,
                    topic=topic,
                    callback_url=callback_url,
                )
                if existing_id:
                    return existing_id
            messages = "; ".join(str(error.get("message")) for error in user_errors)
            raise ShopifyApiError(message=f"Webhook registration failed for {topic}: {messages}")
        webhook = create_data.get("webhookSubscription") or {}
        webhook_id = webhook.get("id")
        if not isinstance(webhook_id, str) or not webhook_id:
            raise ShopifyApiError(message=f"Webhook registration for {topic} returned no id")
        return webhook_id

    @staticmethod
    def _has_duplicate_webhook_address_error(user_errors: list[dict[str, Any]]) -> bool:
        for error in user_errors:
            message = error.get("message")
            if isinstance(message, str) and "already been taken" in message.lower():
                return True
        return False

    async def _find_existing_http_webhook_id(
        self,
        *,
        shop_domain: str,
        access_token: str,
        topic: str,
        callback_url: str,
    ) -> str | None:
        query = """
        query webhookSubscriptionsByTopic($topics: [WebhookSubscriptionTopic!]) {
            webhookSubscriptions(first: 50, topics: $topics) {
                edges {
                    node {
                        id
                        endpoint {
                            __typename
                            ... on WebhookHttpEndpoint {
                                callbackUrl
                            }
                        }
                    }
                }
            }
        }
        """
        payload = {"query": query, "variables": {"topics": [topic]}}
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        target_url = callback_url.rstrip("/")
        subscriptions = (response.get("webhookSubscriptions") or {}).get("edges") or []
        for edge in subscriptions:
            node = edge.get("node") or {}
            endpoint = node.get("endpoint") or {}
            if endpoint.get("__typename") != "WebhookHttpEndpoint":
                continue
            endpoint_callback = endpoint.get("callbackUrl")
            if isinstance(endpoint_callback, str) and endpoint_callback.rstrip("/") == target_url:
                webhook_id = node.get("id")
                if isinstance(webhook_id, str) and webhook_id:
                    return webhook_id
        return None

    async def create_cart(
        self,
        *,
        shop_domain: str,
        storefront_access_token: str,
        cart_input: dict[str, Any],
    ) -> tuple[str, str]:
        query = """
        mutation cartCreate($input: CartInput!) {
            cartCreate(input: $input) {
                cart {
                    id
                    checkoutUrl
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        payload = {"query": query, "variables": {"input": cart_input}}
        response = await self._storefront_graphql(
            shop_domain=shop_domain,
            storefront_access_token=storefront_access_token,
            payload=payload,
        )
        create_data = response.get("cartCreate") or {}
        user_errors = create_data.get("userErrors") or []
        if user_errors:
            messages = "; ".join(str(error.get("message")) for error in user_errors)
            raise ShopifyApiError(message=f"cartCreate failed: {messages}", status_code=409)

        cart = create_data.get("cart") or {}
        cart_id = cart.get("id")
        checkout_url = cart.get("checkoutUrl")
        if not isinstance(cart_id, str) or not cart_id:
            raise ShopifyApiError(message="cartCreate response is missing cart.id")
        if not isinstance(checkout_url, str) or not checkout_url:
            raise ShopifyApiError(message="cartCreate response is missing cart.checkoutUrl")
        return cart_id, checkout_url

    async def verify_product_exists(
        self,
        *,
        shop_domain: str,
        access_token: str,
        product_gid: str,
    ) -> dict[str, str]:
        query = """
        query productById($id: ID!) {
            product(id: $id) {
                id
                title
                handle
            }
        }
        """
        payload = {"query": query, "variables": {"id": product_gid}}
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        product = response.get("product")
        if not isinstance(product, dict):
            raise ShopifyApiError(message=f"Product not found for GID: {product_gid}", status_code=404)

        found_id = product.get("id")
        title = product.get("title")
        handle = product.get("handle")
        if not isinstance(found_id, str) or not found_id:
            raise ShopifyApiError(message="Product verification response is missing product.id")
        if not isinstance(title, str) or not title:
            raise ShopifyApiError(message="Product verification response is missing product.title")
        if not isinstance(handle, str) or not handle:
            raise ShopifyApiError(message="Product verification response is missing product.handle")
        return {"id": found_id, "title": title, "handle": handle}

    async def list_products(
        self,
        *,
        shop_domain: str,
        access_token: str,
        query: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, str]]:
        search_query = (query or "").strip()
        graphql_query = """
        query products($first: Int!, $query: String) {
            products(first: $first, query: $query, sortKey: UPDATED_AT, reverse: true) {
                edges {
                    node {
                        id
                        title
                        handle
                        status
                    }
                }
            }
        }
        """
        payload = {
            "query": graphql_query,
            "variables": {
                "first": limit,
                "query": search_query or None,
            },
        }
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        edges = ((response.get("products") or {}).get("edges")) or []
        if not isinstance(edges, list):
            raise ShopifyApiError(message="Product list response is invalid")

        products: list[dict[str, str]] = []
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            node = edge.get("node")
            if not isinstance(node, dict):
                continue
            product_id = node.get("id")
            title = node.get("title")
            handle = node.get("handle")
            product_status = node.get("status")

            if not isinstance(product_id, str) or not product_id:
                raise ShopifyApiError(message="Product list response is missing product.id")
            if not isinstance(title, str) or not title:
                raise ShopifyApiError(message="Product list response is missing product.title")
            if not isinstance(handle, str) or not handle:
                raise ShopifyApiError(message="Product list response is missing product.handle")
            if not isinstance(product_status, str) or not product_status:
                raise ShopifyApiError(message="Product list response is missing product.status")

            products.append(
                {
                    "id": product_id,
                    "title": title,
                    "handle": handle,
                    "status": product_status,
                }
            )

        return products

    @staticmethod
    def _price_cents_to_decimal_string(price_cents: int) -> str:
        return str((Decimal(price_cents) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    @staticmethod
    def _decimal_price_to_cents(price: Any) -> int:
        try:
            decimal_value = Decimal(str(price).strip())
        except (InvalidOperation, ValueError, AttributeError) as exc:
            raise ShopifyApiError(message=f"Invalid variant price from Shopify: {price!r}") from exc
        cents = int((decimal_value * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if cents < 0:
            raise ShopifyApiError(message=f"Shopify returned a negative variant price: {price!r}")
        return cents

    async def get_product(
        self,
        *,
        shop_domain: str,
        access_token: str,
        product_gid: str,
    ) -> dict[str, Any]:
        cleaned_product_gid = product_gid.strip()
        if not cleaned_product_gid.startswith("gid://shopify/Product/"):
            raise ShopifyApiError(
                message="productGid must be a valid Shopify Product GID.",
                status_code=400,
            )

        graphql_query = """
        query productWithVariants($id: ID!, $first: Int!, $after: String) {
            shop {
                currencyCode
            }
            product(id: $id) {
                id
                title
                handle
                status
                variants(first: $first, after: $after) {
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    edges {
                        node {
                            id
                            title
                            price
                            compareAtPrice
                            barcode
                            taxable
                            inventoryPolicy
                            inventoryQuantity
                            selectedOptions {
                                name
                                value
                            }
                            inventoryItem {
                                sku
                                tracked
                                requiresShipping
                            }
                        }
                    }
                }
            }
        }
        """

        cursor: str | None = None
        currency: str | None = None
        product_title: str | None = None
        product_handle: str | None = None
        product_status: str | None = None
        variants: list[dict[str, Any]] = []

        while True:
            payload = {
                "query": graphql_query,
                "variables": {
                    "id": cleaned_product_gid,
                    "first": 100,
                    "after": cursor,
                },
            }
            response = await self._admin_graphql(
                shop_domain=shop_domain,
                access_token=access_token,
                payload=payload,
            )

            shop = response.get("shop")
            if not isinstance(shop, dict):
                raise ShopifyApiError(message="Product response is missing shop metadata.")
            raw_currency = shop.get("currencyCode")
            if not isinstance(raw_currency, str) or len(raw_currency.strip()) != 3:
                raise ShopifyApiError(message="Product response is missing shop currencyCode.")
            normalized_currency = raw_currency.strip().upper()
            if currency is None:
                currency = normalized_currency
            elif normalized_currency != currency:
                raise ShopifyApiError(message="Shop currency changed while paginating product variants.")

            product = response.get("product")
            if not isinstance(product, dict):
                raise ShopifyApiError(message=f"Product not found for GID: {cleaned_product_gid}", status_code=404)

            product_id = product.get("id")
            if not isinstance(product_id, str) or not product_id:
                raise ShopifyApiError(message="Product response is missing product.id")
            if product_id != cleaned_product_gid:
                raise ShopifyApiError(message="Product response returned unexpected product.id")

            raw_title = product.get("title")
            if not isinstance(raw_title, str) or not raw_title:
                raise ShopifyApiError(message="Product response is missing product.title")
            raw_handle = product.get("handle")
            if not isinstance(raw_handle, str) or not raw_handle:
                raise ShopifyApiError(message="Product response is missing product.handle")
            raw_status = product.get("status")
            if not isinstance(raw_status, str) or not raw_status:
                raise ShopifyApiError(message="Product response is missing product.status")

            if product_title is None:
                product_title = raw_title
                product_handle = raw_handle
                product_status = raw_status
            else:
                if raw_title != product_title or raw_handle != product_handle or raw_status != product_status:
                    raise ShopifyApiError(message="Product metadata changed while paginating variants.")

            variants_connection = product.get("variants")
            if not isinstance(variants_connection, dict):
                raise ShopifyApiError(message="Product response is missing variants connection.")
            edges = variants_connection.get("edges")
            if not isinstance(edges, list):
                raise ShopifyApiError(message="Product variants response is invalid.")

            for edge in edges:
                if not isinstance(edge, dict):
                    raise ShopifyApiError(message="Product variants response contains invalid edge.")
                node = edge.get("node")
                if not isinstance(node, dict):
                    raise ShopifyApiError(message="Product variants response contains invalid node.")

                variant_gid = node.get("id")
                title = node.get("title")
                price = node.get("price")
                compare_at_price = node.get("compareAtPrice")
                barcode = node.get("barcode")
                taxable = node.get("taxable")
                inventory_policy = node.get("inventoryPolicy")
                inventory_quantity = node.get("inventoryQuantity")
                selected_options = node.get("selectedOptions")
                inventory_item = node.get("inventoryItem")

                if not isinstance(variant_gid, str) or not variant_gid:
                    raise ShopifyApiError(message="Product variant response is missing variant.id.")
                if not isinstance(title, str) or not title:
                    raise ShopifyApiError(message="Product variant response is missing variant.title.")
                if not isinstance(price, str) or not price:
                    raise ShopifyApiError(message="Product variant response is missing variant.price.")
                if compare_at_price is not None and not isinstance(compare_at_price, str):
                    raise ShopifyApiError(message="Product variant response has invalid compareAtPrice.")
                if barcode is not None and not isinstance(barcode, str):
                    raise ShopifyApiError(message="Product variant response has invalid barcode.")
                if not isinstance(taxable, bool):
                    raise ShopifyApiError(message="Product variant response has invalid taxable value.")
                if inventory_policy is not None and not isinstance(inventory_policy, str):
                    raise ShopifyApiError(message="Product variant response has invalid inventoryPolicy value.")
                if inventory_quantity is not None and not isinstance(inventory_quantity, int):
                    raise ShopifyApiError(message="Product variant response has invalid inventoryQuantity value.")
                if not isinstance(selected_options, list):
                    raise ShopifyApiError(message="Product variant response has invalid selectedOptions value.")
                if not isinstance(inventory_item, dict):
                    raise ShopifyApiError(message="Product variant response has invalid inventoryItem value.")

                option_values: dict[str, str] = {}
                for selected_option in selected_options:
                    if not isinstance(selected_option, dict):
                        raise ShopifyApiError(message="Product variant response has invalid selected option.")
                    option_name = selected_option.get("name")
                    option_value = selected_option.get("value")
                    if not isinstance(option_name, str) or not option_name.strip():
                        raise ShopifyApiError(message="Product variant response has selected option without name.")
                    if not isinstance(option_value, str):
                        raise ShopifyApiError(message="Product variant response has selected option without value.")
                    option_values[option_name.strip()] = option_value

                sku: str | None = None
                inventory_management: str | None = None
                raw_sku = inventory_item.get("sku")
                raw_tracked = inventory_item.get("tracked")
                raw_requires_shipping = inventory_item.get("requiresShipping")
                if raw_sku is not None and not isinstance(raw_sku, str):
                    raise ShopifyApiError(message="Product variant response has invalid inventoryItem.sku.")
                if not isinstance(raw_tracked, bool):
                    raise ShopifyApiError(message="Product variant response has invalid inventoryItem.tracked.")
                if not isinstance(raw_requires_shipping, bool):
                    raise ShopifyApiError(
                        message="Product variant response has invalid inventoryItem.requiresShipping."
                    )
                sku = raw_sku
                inventory_management = "shopify" if raw_tracked else None
                requires_shipping = raw_requires_shipping

                variants.append(
                    {
                        "variantGid": variant_gid,
                        "title": title,
                        "priceCents": self._decimal_price_to_cents(price),
                        "currency": currency,
                        "compareAtPriceCents": (
                            self._decimal_price_to_cents(compare_at_price) if compare_at_price is not None else None
                        ),
                        "sku": sku,
                        "barcode": barcode,
                        "taxable": taxable,
                        "requiresShipping": requires_shipping,
                        "inventoryPolicy": inventory_policy.strip().lower() if inventory_policy else None,
                        "inventoryManagement": inventory_management,
                        "inventoryQuantity": inventory_quantity,
                        "optionValues": option_values,
                    }
                )

            page_info = variants_connection.get("pageInfo")
            if not isinstance(page_info, dict):
                raise ShopifyApiError(message="Product variants response is missing pageInfo.")
            has_next_page = page_info.get("hasNextPage")
            end_cursor = page_info.get("endCursor")
            if not isinstance(has_next_page, bool):
                raise ShopifyApiError(message="Product variants response has invalid pageInfo.hasNextPage.")
            if has_next_page:
                if not isinstance(end_cursor, str) or not end_cursor:
                    raise ShopifyApiError(message="Product variants response has invalid pageInfo.endCursor.")
                cursor = end_cursor
                continue
            break

        if currency is None:
            raise ShopifyApiError(message="Product response is missing currency metadata.")
        if product_title is None or product_handle is None or product_status is None:
            raise ShopifyApiError(message="Product response is missing metadata.")

        return {
            "productGid": cleaned_product_gid,
            "title": product_title,
            "handle": product_handle,
            "status": product_status,
            "variants": variants,
        }

    async def create_product(
        self,
        *,
        shop_domain: str,
        access_token: str,
        title: str,
        variants: list[dict[str, Any]],
        description: str | None = None,
        handle: str | None = None,
        vendor: str | None = None,
        product_type: str | None = None,
        tags: list[str] | None = None,
        status: str = "DRAFT",
    ) -> dict[str, Any]:
        if not variants:
            raise ShopifyApiError(message="At least one variant is required for product creation.", status_code=400)

        cleaned_variants: list[dict[str, Any]] = []
        seen_titles: set[str] = set()
        normalized_currency: str | None = None
        for raw_variant in variants:
            if not isinstance(raw_variant, dict):
                raise ShopifyApiError(message="Each variant must be an object.", status_code=400)
            raw_title = raw_variant.get("title")
            if not isinstance(raw_title, str) or not raw_title.strip():
                raise ShopifyApiError(message="Each variant requires a non-empty title.", status_code=400)
            variant_title = raw_title.strip()
            lower_title = variant_title.lower()
            if lower_title in seen_titles:
                raise ShopifyApiError(message="Variant titles must be unique.", status_code=400)
            seen_titles.add(lower_title)

            raw_price_cents = raw_variant.get("priceCents")
            if not isinstance(raw_price_cents, int) or raw_price_cents < 0:
                raise ShopifyApiError(message="Each variant requires a non-negative integer priceCents.", status_code=400)

            raw_currency = raw_variant.get("currency")
            if not isinstance(raw_currency, str) or len(raw_currency.strip()) != 3:
                raise ShopifyApiError(message="Each variant requires a 3-letter currency code.", status_code=400)
            currency = raw_currency.strip().upper()
            if normalized_currency is None:
                normalized_currency = currency
            elif currency != normalized_currency:
                raise ShopifyApiError(
                    message="All variants must use the same currency for Shopify product creation.",
                    status_code=400,
                )

            cleaned_variants.append(
                {
                    "title": variant_title,
                    "priceCents": raw_price_cents,
                    "price": self._price_cents_to_decimal_string(raw_price_cents),
                    "currency": currency,
                }
            )

        product_input: dict[str, Any] = {
            "title": title.strip(),
            "status": status.strip().upper(),
            "productOptions": [
                {
                    "name": "Title",
                    "values": [{"name": variant["title"]} for variant in cleaned_variants],
                }
            ],
        }
        if description is not None and description.strip():
            product_input["descriptionHtml"] = description.strip()
        if handle is not None and handle.strip():
            product_input["handle"] = handle.strip()
        if vendor is not None and vendor.strip():
            product_input["vendor"] = vendor.strip()
        if product_type is not None and product_type.strip():
            product_input["productType"] = product_type.strip()
        if tags:
            product_input["tags"] = tags

        create_query = """
        mutation productCreate($product: ProductCreateInput!) {
            productCreate(product: $product) {
                product {
                    id
                    title
                    handle
                    status
                    variants(first: 1) {
                        edges {
                            node {
                                id
                                title
                                price
                            }
                        }
                    }
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        create_response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload={"query": create_query, "variables": {"product": product_input}},
        )
        create_data = create_response.get("productCreate") or {}
        user_errors = create_data.get("userErrors") or []
        if user_errors:
            messages = "; ".join(str(error.get("message")) for error in user_errors)
            raise ShopifyApiError(message=f"productCreate failed: {messages}", status_code=409)

        product = create_data.get("product")
        if not isinstance(product, dict):
            raise ShopifyApiError(message="productCreate response is missing product")

        product_gid = product.get("id")
        product_title = product.get("title")
        product_handle = product.get("handle")
        product_status = product.get("status")
        if not isinstance(product_gid, str) or not product_gid:
            raise ShopifyApiError(message="productCreate response is missing product.id")
        if not isinstance(product_title, str) or not product_title:
            raise ShopifyApiError(message="productCreate response is missing product.title")
        if not isinstance(product_handle, str) or not product_handle:
            raise ShopifyApiError(message="productCreate response is missing product.handle")
        if not isinstance(product_status, str) or not product_status:
            raise ShopifyApiError(message="productCreate response is missing product.status")

        initial_variant_edges = ((product.get("variants") or {}).get("edges")) or []
        if not isinstance(initial_variant_edges, list) or not initial_variant_edges:
            raise ShopifyApiError(message="productCreate response is missing initial product variant.")
        initial_variant_node = (initial_variant_edges[0] or {}).get("node") if isinstance(initial_variant_edges[0], dict) else None
        if not isinstance(initial_variant_node, dict):
            raise ShopifyApiError(message="productCreate response is missing initial variant node.")
        initial_variant_id = initial_variant_node.get("id")
        if not isinstance(initial_variant_id, str) or not initial_variant_id:
            raise ShopifyApiError(message="productCreate response is missing initial variant id.")

        update_query = """
        mutation productVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
            productVariantsBulkUpdate(productId: $productId, variants: $variants) {
                productVariants {
                    id
                    title
                    price
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        first_variant = cleaned_variants[0]
        update_response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload={
                "query": update_query,
                "variables": {
                    "productId": product_gid,
                    "variants": [{"id": initial_variant_id, "price": first_variant["price"]}],
                },
            },
        )
        update_data = update_response.get("productVariantsBulkUpdate") or {}
        update_errors = update_data.get("userErrors") or []
        if update_errors:
            messages = "; ".join(str(error.get("message")) for error in update_errors)
            raise ShopifyApiError(message=f"productVariantsBulkUpdate failed: {messages}", status_code=409)
        updated_variants = update_data.get("productVariants") or []
        if not isinstance(updated_variants, list) or not updated_variants:
            raise ShopifyApiError(message="productVariantsBulkUpdate response is missing variants.")
        updated_first_variant = updated_variants[0]
        if not isinstance(updated_first_variant, dict):
            raise ShopifyApiError(message="productVariantsBulkUpdate response is invalid.")

        created_variants: list[dict[str, Any]] = []
        if len(cleaned_variants) > 1:
            create_variants_query = """
            mutation productVariantsBulkCreate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
                productVariantsBulkCreate(productId: $productId, variants: $variants) {
                    productVariants {
                        id
                        title
                        price
                    }
                    userErrors {
                        field
                        message
                    }
                }
            }
            """
            bulk_create_response = await self._admin_graphql(
                shop_domain=shop_domain,
                access_token=access_token,
                payload={
                    "query": create_variants_query,
                    "variables": {
                        "productId": product_gid,
                        "variants": [
                            {
                                "price": variant["price"],
                                "optionValues": [{"optionName": "Title", "name": variant["title"]}],
                            }
                            for variant in cleaned_variants[1:]
                        ],
                    },
                },
            )
            bulk_create_data = bulk_create_response.get("productVariantsBulkCreate") or {}
            bulk_create_errors = bulk_create_data.get("userErrors") or []
            if bulk_create_errors:
                messages = "; ".join(str(error.get("message")) for error in bulk_create_errors)
                raise ShopifyApiError(message=f"productVariantsBulkCreate failed: {messages}", status_code=409)
            raw_created_variants = bulk_create_data.get("productVariants") or []
            if not isinstance(raw_created_variants, list):
                raise ShopifyApiError(message="productVariantsBulkCreate response is invalid.")
            for raw_variant in raw_created_variants:
                if not isinstance(raw_variant, dict):
                    continue
                created_variants.append(raw_variant)

        currency = normalized_currency or "USD"
        variant_rows: list[dict[str, Any]] = []
        for variant_node in [updated_first_variant, *created_variants]:
            variant_gid = variant_node.get("id")
            variant_title = variant_node.get("title")
            variant_price = variant_node.get("price")
            if not isinstance(variant_gid, str) or not variant_gid:
                raise ShopifyApiError(message="Variant creation response is missing variant id.")
            if not isinstance(variant_title, str) or not variant_title:
                raise ShopifyApiError(message="Variant creation response is missing variant title.")
            variant_rows.append(
                {
                    "variantGid": variant_gid,
                    "title": variant_title,
                    "priceCents": self._decimal_price_to_cents(variant_price),
                    "currency": currency,
                }
            )

        if len(variant_rows) != len(cleaned_variants):
            raise ShopifyApiError(
                message=(
                    "Shopify variant creation returned an unexpected number of variants. "
                    f"Expected {len(cleaned_variants)}, got {len(variant_rows)}."
                ),
            )

        return {
            "productGid": product_gid,
            "title": product_title,
            "handle": product_handle,
            "status": product_status,
            "variants": variant_rows,
        }

    async def _resolve_variant_product_gid(
        self,
        *,
        shop_domain: str,
        access_token: str,
        variant_gid: str,
    ) -> str:
        query = """
        query productVariantNode($id: ID!) {
            node(id: $id) {
                ... on ProductVariant {
                    id
                    product {
                        id
                    }
                }
            }
        }
        """
        payload = {"query": query, "variables": {"id": variant_gid}}
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        node = response.get("node")
        if not isinstance(node, dict):
            raise ShopifyApiError(
                message=f"Product variant not found for GID: {variant_gid}",
                status_code=404,
            )
        product = node.get("product")
        if not isinstance(product, dict):
            raise ShopifyApiError(
                message=f"Product variant is missing parent product for GID: {variant_gid}",
                status_code=404,
            )
        product_gid = product.get("id")
        if not isinstance(product_gid, str) or not product_gid:
            raise ShopifyApiError(
                message=f"Product variant is missing product id for GID: {variant_gid}",
                status_code=404,
            )
        return product_gid

    async def update_variant(
        self,
        *,
        shop_domain: str,
        access_token: str,
        variant_gid: str,
        fields: dict[str, Any],
    ) -> dict[str, str]:
        cleaned_variant_gid = variant_gid.strip()
        if not cleaned_variant_gid.startswith("gid://shopify/ProductVariant/"):
            raise ShopifyApiError(
                message="variantGid must be a valid Shopify ProductVariant GID.",
                status_code=400,
            )
        if not fields:
            raise ShopifyApiError(message="At least one variant update field is required.", status_code=400)

        supported_fields = {
            "title",
            "priceCents",
            "compareAtPriceCents",
            "sku",
            "barcode",
            "inventoryPolicy",
            "inventoryManagement",
        }
        unsupported_fields = sorted(name for name in fields.keys() if name not in supported_fields)
        if unsupported_fields:
            raise ShopifyApiError(
                message=f"Unsupported variant update fields: {', '.join(unsupported_fields)}",
                status_code=400,
            )

        variant_input: dict[str, Any] = {"id": cleaned_variant_gid}
        inventory_item_input: dict[str, Any] = {}
        if "title" in fields:
            raw_title = fields.get("title")
            if not isinstance(raw_title, str) or not raw_title.strip():
                raise ShopifyApiError(message="title must be a non-empty string.", status_code=400)
            variant_input["optionValues"] = [{"optionName": "Title", "name": raw_title.strip()}]

        if "priceCents" in fields:
            raw_price_cents = fields.get("priceCents")
            if not isinstance(raw_price_cents, int) or raw_price_cents < 0:
                raise ShopifyApiError(
                    message="priceCents must be a non-negative integer.",
                    status_code=400,
                )
            variant_input["price"] = self._price_cents_to_decimal_string(raw_price_cents)

        if "compareAtPriceCents" in fields:
            raw_compare_at_price_cents = fields.get("compareAtPriceCents")
            if raw_compare_at_price_cents is None:
                variant_input["compareAtPrice"] = None
            else:
                if not isinstance(raw_compare_at_price_cents, int) or raw_compare_at_price_cents < 0:
                    raise ShopifyApiError(
                        message="compareAtPriceCents must be null or a non-negative integer.",
                        status_code=400,
                    )
                variant_input["compareAtPrice"] = self._price_cents_to_decimal_string(raw_compare_at_price_cents)

        if "sku" in fields:
            raw_sku = fields.get("sku")
            if raw_sku is None:
                inventory_item_input["sku"] = None
            else:
                if not isinstance(raw_sku, str) or not raw_sku.strip():
                    raise ShopifyApiError(
                        message="sku must be null or a non-empty string.",
                        status_code=400,
                    )
                inventory_item_input["sku"] = raw_sku.strip()

        if "barcode" in fields:
            raw_barcode = fields.get("barcode")
            if raw_barcode is None:
                variant_input["barcode"] = None
            else:
                if not isinstance(raw_barcode, str) or not raw_barcode.strip():
                    raise ShopifyApiError(
                        message="barcode must be null or a non-empty string.",
                        status_code=400,
                    )
                variant_input["barcode"] = raw_barcode.strip()

        if "inventoryPolicy" in fields:
            raw_inventory_policy = fields.get("inventoryPolicy")
            if not isinstance(raw_inventory_policy, str) or not raw_inventory_policy.strip():
                raise ShopifyApiError(
                    message="inventoryPolicy must be one of: deny, continue.",
                    status_code=400,
                )
            normalized_inventory_policy = raw_inventory_policy.strip().upper()
            if normalized_inventory_policy not in {"DENY", "CONTINUE"}:
                raise ShopifyApiError(
                    message="inventoryPolicy must be one of: deny, continue.",
                    status_code=400,
                )
            variant_input["inventoryPolicy"] = normalized_inventory_policy

        if "inventoryManagement" in fields:
            raw_inventory_management = fields.get("inventoryManagement")
            if raw_inventory_management is None:
                inventory_item_input["tracked"] = False
            else:
                if not isinstance(raw_inventory_management, str) or not raw_inventory_management.strip():
                    raise ShopifyApiError(
                        message="inventoryManagement must be null or 'shopify'.",
                        status_code=400,
                    )
                normalized_inventory_management = raw_inventory_management.strip().lower()
                if normalized_inventory_management != "shopify":
                    raise ShopifyApiError(
                        message="inventoryManagement must be null or 'shopify'.",
                        status_code=400,
                    )
                inventory_item_input["tracked"] = True

        if inventory_item_input:
            variant_input["inventoryItem"] = inventory_item_input

        product_gid = await self._resolve_variant_product_gid(
            shop_domain=shop_domain,
            access_token=access_token,
            variant_gid=cleaned_variant_gid,
        )

        mutation = """
        mutation productVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
            productVariantsBulkUpdate(productId: $productId, variants: $variants) {
                productVariants {
                    id
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        payload = {
            "query": mutation,
            "variables": {
                "productId": product_gid,
                "variants": [variant_input],
            },
        }
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        update_data = response.get("productVariantsBulkUpdate") or {}
        user_errors = update_data.get("userErrors") or []
        if user_errors:
            messages = "; ".join(str(error.get("message")) for error in user_errors)
            raise ShopifyApiError(message=f"productVariantsBulkUpdate failed: {messages}", status_code=409)

        updated_variants = update_data.get("productVariants") or []
        if not isinstance(updated_variants, list) or not updated_variants:
            raise ShopifyApiError(message="productVariantsBulkUpdate response is missing variants.")

        updated_variant_ids = {
            item.get("id")
            for item in updated_variants
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        if cleaned_variant_gid not in updated_variant_ids:
            raise ShopifyApiError(
                message="productVariantsBulkUpdate response did not include requested variant.",
            )

        return {
            "productGid": product_gid,
            "variantGid": cleaned_variant_gid,
        }

    @staticmethod
    def _normalize_policy_page_handle(handle: str) -> str:
        cleaned = handle.strip().lower()
        if not cleaned:
            raise ShopifyApiError(message="Policy page handle cannot be empty.", status_code=400)
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", cleaned):
            raise ShopifyApiError(
                message=(
                    "Policy page handle must use lowercase letters, numbers, and hyphens "
                    "(for example: returns-refunds-policy)."
                ),
                status_code=400,
            )
        return cleaned

    @staticmethod
    def _coerce_page_node(
        *,
        node: Any,
        mutation_name: str,
        require_online_store_url: bool,
    ) -> dict[str, str]:
        if not isinstance(node, dict):
            raise ShopifyApiError(message=f"{mutation_name} response is missing page object.")

        page_id = node.get("id")
        title = node.get("title")
        handle = node.get("handle")
        online_store_url = node.get("onlineStoreUrl")

        if not isinstance(page_id, str) or not page_id:
            raise ShopifyApiError(message=f"{mutation_name} response is missing page.id.")
        if not isinstance(title, str) or not title:
            raise ShopifyApiError(message=f"{mutation_name} response is missing page.title.")
        if not isinstance(handle, str) or not handle:
            raise ShopifyApiError(message=f"{mutation_name} response is missing page.handle.")
        if require_online_store_url and (not isinstance(online_store_url, str) or not online_store_url):
            raise ShopifyApiError(
                message=(
                    f"{mutation_name} response is missing page.onlineStoreUrl. "
                    "Confirm the page is published to Online Store."
                )
            )

        return {
            "id": page_id,
            "title": title,
            "handle": handle,
            "onlineStoreUrl": online_store_url if isinstance(online_store_url, str) else "",
        }

    async def _find_page_by_handle(
        self,
        *,
        shop_domain: str,
        access_token: str,
        handle: str,
    ) -> dict[str, str] | None:
        normalized_handle = self._normalize_policy_page_handle(handle)
        query = """
        query pagesByHandle($query: String!) {
            pages(first: 10, query: $query, sortKey: UPDATED_AT, reverse: true) {
                edges {
                    node {
                        id
                        title
                        handle
                    }
                }
            }
        }
        """
        payload = {"query": query, "variables": {"query": f"handle:{normalized_handle}"}}
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        edges = ((response.get("pages") or {}).get("edges")) or []
        if not isinstance(edges, list):
            raise ShopifyApiError(message="pages query response is invalid.")

        for edge in edges:
            if not isinstance(edge, dict):
                continue
            node = edge.get("node")
            parsed = self._coerce_page_node(
                node=node,
                mutation_name="pages query",
                require_online_store_url=False,
            )
            if parsed["handle"].strip().lower() == normalized_handle:
                return parsed
        return None

    @staticmethod
    def _assert_no_user_errors(*, user_errors: list[dict[str, Any]], mutation_name: str) -> None:
        if not user_errors:
            return
        messages = "; ".join(str(error.get("message")) for error in user_errors)
        raise ShopifyApiError(message=f"{mutation_name} failed: {messages}", status_code=409)

    async def _create_policy_page(
        self,
        *,
        shop_domain: str,
        access_token: str,
        title: str,
        handle: str,
        body_html: str,
    ) -> dict[str, str]:
        mutation = """
        mutation pageCreate($page: PageCreateInput!) {
            pageCreate(page: $page) {
                page {
                    id
                    title
                    handle
                    onlineStoreUrl
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        payload = {
            "query": mutation,
            "variables": {
                "page": {
                    "title": title,
                    "handle": handle,
                    "body": body_html,
                }
            },
        }
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        create_data = response.get("pageCreate") or {}
        user_errors = create_data.get("userErrors") or []
        self._assert_no_user_errors(user_errors=user_errors, mutation_name="pageCreate")
        return self._coerce_page_node(
            node=create_data.get("page"),
            mutation_name="pageCreate",
            require_online_store_url=True,
        )

    async def _update_policy_page(
        self,
        *,
        shop_domain: str,
        access_token: str,
        page_id: str,
        title: str,
        handle: str,
        body_html: str,
    ) -> dict[str, str]:
        mutation = """
        mutation pageUpdate($id: ID!, $page: PageUpdateInput!) {
            pageUpdate(id: $id, page: $page) {
                page {
                    id
                    title
                    handle
                    onlineStoreUrl
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        payload = {
            "query": mutation,
            "variables": {
                "id": page_id,
                "page": {
                    "title": title,
                    "handle": handle,
                    "body": body_html,
                },
            },
        }
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload=payload,
        )
        update_data = response.get("pageUpdate") or {}
        user_errors = update_data.get("userErrors") or []
        self._assert_no_user_errors(user_errors=user_errors, mutation_name="pageUpdate")
        return self._coerce_page_node(
            node=update_data.get("page"),
            mutation_name="pageUpdate",
            require_online_store_url=True,
        )

    async def upsert_policy_pages(
        self,
        *,
        shop_domain: str,
        access_token: str,
        pages: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        if not pages:
            raise ShopifyApiError(message="At least one policy page is required for sync.", status_code=400)

        seen_page_keys: set[str] = set()
        seen_handles: set[str] = set()
        normalized_pages: list[dict[str, str]] = []
        for item in pages:
            if not isinstance(item, dict):
                raise ShopifyApiError(message="Each policy page payload must be an object.", status_code=400)

            raw_page_key = item.get("pageKey")
            if not isinstance(raw_page_key, str) or not raw_page_key.strip():
                raise ShopifyApiError(message="Each policy page requires pageKey.", status_code=400)
            page_key = raw_page_key.strip()
            if page_key in seen_page_keys:
                raise ShopifyApiError(message=f"Duplicate pageKey in payload: {page_key}", status_code=400)
            seen_page_keys.add(page_key)

            raw_title = item.get("title")
            if not isinstance(raw_title, str) or not raw_title.strip():
                raise ShopifyApiError(message=f"Policy page '{page_key}' requires a non-empty title.", status_code=400)
            title = raw_title.strip()

            raw_handle = item.get("handle")
            if not isinstance(raw_handle, str):
                raise ShopifyApiError(message=f"Policy page '{page_key}' requires handle.", status_code=400)
            handle = self._normalize_policy_page_handle(raw_handle)
            if handle in seen_handles:
                raise ShopifyApiError(
                    message=f"Duplicate page handle in payload: {handle}",
                    status_code=400,
                )
            seen_handles.add(handle)

            raw_body_html = item.get("bodyHtml")
            if not isinstance(raw_body_html, str) or not raw_body_html.strip():
                raise ShopifyApiError(
                    message=f"Policy page '{page_key}' requires non-empty bodyHtml.",
                    status_code=400,
                )
            body_html = raw_body_html.strip()

            normalized_pages.append(
                {
                    "pageKey": page_key,
                    "title": title,
                    "handle": handle,
                    "bodyHtml": body_html,
                }
            )

        results: list[dict[str, str]] = []
        for page in normalized_pages:
            existing_page = await self._find_page_by_handle(
                shop_domain=shop_domain,
                access_token=access_token,
                handle=page["handle"],
            )
            operation: Literal["created", "updated"]
            if existing_page:
                synced_page = await self._update_policy_page(
                    shop_domain=shop_domain,
                    access_token=access_token,
                    page_id=existing_page["id"],
                    title=page["title"],
                    handle=page["handle"],
                    body_html=page["bodyHtml"],
                )
                operation = "updated"
            else:
                synced_page = await self._create_policy_page(
                    shop_domain=shop_domain,
                    access_token=access_token,
                    title=page["title"],
                    handle=page["handle"],
                    body_html=page["bodyHtml"],
                )
                operation = "created"

            results.append(
                {
                    "pageKey": page["pageKey"],
                    "pageId": synced_page["id"],
                    "title": synced_page["title"],
                    "handle": synced_page["handle"],
                    "url": synced_page["onlineStoreUrl"],
                    "operation": operation,
                }
            )
        return results

    @staticmethod
    def _normalize_workspace_slug(workspace_name: str) -> str:
        cleaned_workspace = workspace_name.strip().lower()
        if not cleaned_workspace:
            raise ShopifyApiError(message="workspaceName must be a non-empty string.", status_code=400)
        slug = re.sub(r"[^a-z0-9]+", "-", cleaned_workspace)
        slug = re.sub(r"-{2,}", "-", slug).strip("-")
        if not slug:
            raise ShopifyApiError(
                message="workspaceName must include at least one letter or number.",
                status_code=400,
            )
        return slug[:64].rstrip("-")

    @staticmethod
    def _normalize_css_var_key(raw_key: str) -> str:
        key = raw_key.strip()
        if not re.fullmatch(r"--[A-Za-z0-9_-]+", key):
            raise ShopifyApiError(
                message=(
                    "Invalid cssVars key. Keys must look like CSS custom properties "
                    "(for example: --color-brand)."
                ),
                status_code=400,
            )
        return key

    @staticmethod
    def _normalize_css_var_value(raw_value: str) -> str:
        value = raw_value.strip()
        if not value:
            raise ShopifyApiError(message="cssVars values cannot be empty.", status_code=400)
        if any(char in value for char in ("\n", "\r", "{", "}", ";")):
            raise ShopifyApiError(
                message="cssVars values cannot contain newlines, braces, or semicolons.",
                status_code=400,
            )
        return value

    @classmethod
    def _normalize_theme_brand_css_vars(cls, css_vars: dict[str, str]) -> dict[str, str]:
        if not isinstance(css_vars, dict) or not css_vars:
            raise ShopifyApiError(message="cssVars must be a non-empty object.", status_code=400)

        normalized: dict[str, str] = {}
        for raw_key, raw_value in css_vars.items():
            if not isinstance(raw_key, str):
                raise ShopifyApiError(message="cssVars keys must be strings.", status_code=400)
            if not isinstance(raw_value, str):
                raise ShopifyApiError(message="cssVars values must be strings.", status_code=400)
            key = cls._normalize_css_var_key(raw_key)
            if key in normalized:
                raise ShopifyApiError(
                    message=f"Duplicate cssVars key after normalization: {key}",
                    status_code=400,
                )
            normalized[key] = cls._normalize_css_var_value(raw_value)
        return normalized

    @staticmethod
    def _normalize_theme_brand_font_urls(font_urls: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_url in font_urls:
            if not isinstance(raw_url, str):
                raise ShopifyApiError(message="fontUrls entries must be strings.", status_code=400)
            url = raw_url.strip()
            if not url:
                raise ShopifyApiError(message="fontUrls entries cannot be empty.", status_code=400)
            if not (url.startswith("https://") or url.startswith("http://")):
                raise ShopifyApiError(
                    message=f"fontUrls entry must be an absolute http(s) URL: {url}",
                    status_code=400,
                )
            if any(char in url for char in ('"', "'", "<", ">", "\n", "\r")):
                raise ShopifyApiError(
                    message=f"fontUrls entry contains unsupported characters: {url}",
                    status_code=400,
                )
            if url in seen:
                continue
            seen.add(url)
            normalized.append(url)
        return normalized

    @staticmethod
    def _escape_css_string(raw_value: str) -> str:
        return raw_value.replace("\\", "\\\\").replace('"', '\\"')

    @classmethod
    def _render_theme_brand_css(
        cls,
        *,
        workspace_name: str,
        brand_name: str,
        logo_url: str,
        data_theme: str | None,
        css_vars: dict[str, str],
        font_urls: list[str],
    ) -> str:
        lines: list[str] = [
            "/* Managed by mOS workspace brand sync. */",
            f"/* Workspace: {workspace_name} */",
            f"/* Brand: {brand_name} */",
        ]
        if data_theme:
            lines.append(f"/* dataTheme: {data_theme} */")
        if font_urls:
            lines.append("")
            for font_url in font_urls:
                lines.append(f'@import url("{font_url}");')
        lines.extend(["", ":root {"])
        for key in sorted(css_vars.keys()):
            lines.append(f"  {key}: {css_vars[key]};")
        lines.append(f'  --mos-workspace-name: "{cls._escape_css_string(workspace_name)}";')
        lines.append(f'  --mos-brand-name: "{cls._escape_css_string(brand_name)}";')
        lines.append(f'  --mos-brand-logo-url: "{cls._escape_css_string(logo_url)}";')
        if data_theme:
            lines.append(f'  --mos-data-theme: "{cls._escape_css_string(data_theme)}";')
        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _render_theme_brand_liquid_block(
        *,
        css_filename: str,
        workspace_name: str,
        brand_name: str,
        logo_url: str,
        data_theme: str | None,
    ) -> str:
        asset_name = css_filename
        if css_filename.startswith("assets/"):
            asset_name = css_filename.split("/", 1)[1]
        block_lines = [
            _THEME_BRAND_MARKER_START,
            "{% comment %}Managed by mOS workspace brand sync. Do not edit manually.{% endcomment %}",
            f"{{{{ '{asset_name}' | asset_url | stylesheet_tag }}}}",
            f'<meta name="mos-workspace-name" content="{escape(workspace_name, quote=True)}">',
            f'<meta name="mos-brand-name" content="{escape(brand_name, quote=True)}">',
            f'<meta name="mos-brand-logo-url" content="{escape(logo_url, quote=True)}">',
        ]
        if data_theme:
            block_lines.append(f'<meta name="mos-data-theme" content="{escape(data_theme, quote=True)}">')
        block_lines.append(_THEME_BRAND_MARKER_END)
        return "\n".join(block_lines)

    @staticmethod
    def _replace_theme_brand_liquid_block(
        *,
        layout_content: str,
        replacement_block: str,
    ) -> str:
        start_count = layout_content.count(_THEME_BRAND_MARKER_START)
        end_count = layout_content.count(_THEME_BRAND_MARKER_END)
        if start_count != 1 or end_count != 1:
            raise ShopifyApiError(
                message=(
                    "Theme layout must include exactly one managed brand marker block: "
                    f"{_THEME_BRAND_MARKER_START} ... {_THEME_BRAND_MARKER_END}"
                ),
                status_code=409,
            )

        start_idx = layout_content.find(_THEME_BRAND_MARKER_START)
        end_idx = layout_content.find(_THEME_BRAND_MARKER_END)
        if start_idx < 0 or end_idx < 0 or end_idx < start_idx:
            raise ShopifyApiError(
                message="Theme layout contains an invalid managed brand marker block.",
                status_code=409,
            )
        end_idx += len(_THEME_BRAND_MARKER_END)

        prefix = layout_content[:start_idx]
        suffix = layout_content[end_idx:]
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        if suffix and not suffix.startswith("\n"):
            suffix = "\n" + suffix
        return f"{prefix}{replacement_block}{suffix}"

    @staticmethod
    def _coerce_theme_data(*, node: Any, query_name: str) -> dict[str, str]:
        if not isinstance(node, dict):
            raise ShopifyApiError(message=f"{query_name} response is missing theme data.")
        theme_id = node.get("id")
        theme_name = node.get("name")
        theme_role = node.get("role")
        if not isinstance(theme_id, str) or not theme_id:
            raise ShopifyApiError(message=f"{query_name} response is missing theme.id.")
        if not isinstance(theme_name, str) or not theme_name:
            raise ShopifyApiError(message=f"{query_name} response is missing theme.name.")
        if not isinstance(theme_role, str) or not theme_role:
            raise ShopifyApiError(message=f"{query_name} response is missing theme.role.")
        return {"id": theme_id, "name": theme_name, "role": theme_role}

    async def _resolve_theme_for_brand_sync(
        self,
        *,
        shop_domain: str,
        access_token: str,
        theme_id: str | None,
        theme_name: str | None,
    ) -> dict[str, str]:
        if theme_id and theme_name:
            raise ShopifyApiError(
                message="Provide exactly one of themeId or themeName.",
                status_code=400,
            )
        if theme_id:
            query = """
            query themeById($id: ID!) {
                theme(id: $id) {
                    id
                    name
                    role
                }
            }
            """
            response = await self._admin_graphql(
                shop_domain=shop_domain,
                access_token=access_token,
                payload={"query": query, "variables": {"id": theme_id}},
            )
            theme = response.get("theme")
            if theme is None:
                raise ShopifyApiError(
                    message=f"Theme not found for themeId={theme_id}.",
                    status_code=404,
                )
            return self._coerce_theme_data(node=theme, query_name="theme")

        if theme_name:
            cleaned_theme_name = theme_name.strip()
            if not cleaned_theme_name:
                raise ShopifyApiError(
                    message="themeName cannot be empty when provided.",
                    status_code=400,
                )
            query = """
            query themesForBrandSync($first: Int!) {
                themes(first: $first) {
                    nodes {
                        id
                        name
                        role
                    }
                }
            }
            """
            response = await self._admin_graphql(
                shop_domain=shop_domain,
                access_token=access_token,
                payload={"query": query, "variables": {"first": 100}},
            )
            raw_nodes = (response.get("themes") or {}).get("nodes")
            if not isinstance(raw_nodes, list):
                raise ShopifyApiError(message="themes query response is invalid.")
            requested_name = cleaned_theme_name.lower()
            matches: list[dict[str, str]] = []
            for node in raw_nodes:
                parsed = self._coerce_theme_data(node=node, query_name="themes")
                if parsed["name"].strip().lower() == requested_name:
                    matches.append(parsed)
            if not matches:
                raise ShopifyApiError(
                    message=f"Theme not found for themeName={cleaned_theme_name}.",
                    status_code=404,
                )
            if len(matches) > 1:
                theme_ids = ", ".join(theme["id"] for theme in matches)
                raise ShopifyApiError(
                    message=(
                        f"Multiple themes matched themeName={cleaned_theme_name}. "
                        f"Provide themeId instead. matchedThemeIds={theme_ids}"
                    ),
                    status_code=409,
                )
            return matches[0]

        raise ShopifyApiError(
            message="Exactly one of themeId or themeName is required.",
            status_code=400,
        )

    async def _load_theme_file_text(
        self,
        *,
        shop_domain: str,
        access_token: str,
        theme_id: str,
        filename: str,
    ) -> str:
        query = """
        query themeFileByName($id: ID!, $filenames: [String!]!) {
            theme(id: $id) {
                files(first: 10, filenames: $filenames) {
                    nodes {
                        filename
                        body {
                            __typename
                            ... on OnlineStoreThemeFileBodyText {
                                content
                            }
                        }
                    }
                    userErrors {
                        field
                        message
                    }
                }
            }
        }
        """
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload={
                "query": query,
                "variables": {
                    "id": theme_id,
                    "filenames": [filename],
                },
            },
        )
        theme = response.get("theme")
        if not isinstance(theme, dict):
            raise ShopifyApiError(message=f"Theme not found for themeId={theme_id}.", status_code=404)
        files = theme.get("files")
        if not isinstance(files, dict):
            raise ShopifyApiError(message="theme files query response is invalid.")
        user_errors = files.get("userErrors") or []
        if user_errors:
            messages = "; ".join(str(error.get("message")) for error in user_errors)
            raise ShopifyApiError(message=f"theme files query failed: {messages}", status_code=409)
        nodes = files.get("nodes")
        if not isinstance(nodes, list):
            raise ShopifyApiError(message="theme files query response is missing nodes.")

        matched_node: dict[str, Any] | None = None
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_filename = node.get("filename")
            if isinstance(node_filename, str) and node_filename == filename:
                matched_node = node
                break
        if matched_node is None:
            raise ShopifyApiError(
                message=f"Theme file not found: {filename}",
                status_code=404,
            )

        body = matched_node.get("body")
        if not isinstance(body, dict):
            raise ShopifyApiError(message=f"Theme file body is missing for {filename}.")
        typename = body.get("__typename")
        if typename != "OnlineStoreThemeFileBodyText":
            raise ShopifyApiError(
                message=(
                    f"Theme file {filename} is not text-backed (typename={typename}). "
                    "Use a text theme file for managed brand sync."
                ),
                status_code=409,
            )
        content = body.get("content")
        if not isinstance(content, str):
            raise ShopifyApiError(message=f"Theme file body content is missing for {filename}.")
        return content

    async def _upsert_theme_files(
        self,
        *,
        shop_domain: str,
        access_token: str,
        theme_id: str,
        files: list[dict[str, str]],
    ) -> str:
        mutation = """
        mutation themeFilesUpsert($themeId: ID!, $files: [OnlineStoreThemeFilesUpsertFileInput!]!) {
            themeFilesUpsert(themeId: $themeId, files: $files) {
                upsertedThemeFiles {
                    filename
                }
                job {
                    id
                    done
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        response = await self._admin_graphql(
            shop_domain=shop_domain,
            access_token=access_token,
            payload={
                "query": mutation,
                "variables": {
                    "themeId": theme_id,
                    "files": [
                        {
                            "filename": item["filename"],
                            "body": {
                                "type": "TEXT",
                                "value": item["content"],
                            },
                        }
                        for item in files
                    ],
                },
            },
        )
        upsert_data = response.get("themeFilesUpsert") or {}
        user_errors = upsert_data.get("userErrors") or []
        if user_errors:
            messages = "; ".join(str(error.get("message")) for error in user_errors)
            raise ShopifyApiError(message=f"themeFilesUpsert failed: {messages}", status_code=409)

        upserted = upsert_data.get("upsertedThemeFiles")
        if not isinstance(upserted, list):
            raise ShopifyApiError(message="themeFilesUpsert response is missing upsertedThemeFiles.")
        upserted_filenames = {
            item.get("filename")
            for item in upserted
            if isinstance(item, dict) and isinstance(item.get("filename"), str)
        }
        expected_filenames = {item["filename"] for item in files}
        if expected_filenames - upserted_filenames:
            missing = ", ".join(sorted(expected_filenames - upserted_filenames))
            raise ShopifyApiError(message=f"themeFilesUpsert did not report updated files: {missing}")

        job = upsert_data.get("job")
        if not isinstance(job, dict):
            raise ShopifyApiError(message="themeFilesUpsert response is missing job metadata.")
        job_id = job.get("id")
        if not isinstance(job_id, str) or not job_id:
            raise ShopifyApiError(message="themeFilesUpsert response is missing job.id.")
        return job_id

    async def _wait_for_job_completion(
        self,
        *,
        shop_domain: str,
        access_token: str,
        job_id: str,
        poll_interval_seconds: float = 1.0,
        max_attempts: int = 30,
    ) -> None:
        query = """
        query themeFileJobStatus($id: ID!) {
            job(id: $id) {
                id
                done
            }
        }
        """
        for _ in range(max_attempts):
            response = await self._admin_graphql(
                shop_domain=shop_domain,
                access_token=access_token,
                payload={"query": query, "variables": {"id": job_id}},
            )
            job = response.get("job")
            if not isinstance(job, dict):
                raise ShopifyApiError(message=f"Job not found for id={job_id}.", status_code=404)
            done = job.get("done")
            if not isinstance(done, bool):
                raise ShopifyApiError(message=f"Job response is missing done state for id={job_id}.")
            if done:
                return
            await asyncio.sleep(poll_interval_seconds)

        raise ShopifyApiError(
            message=f"Timed out while waiting for theme file job {job_id} to complete.",
            status_code=504,
        )

    async def sync_theme_brand(
        self,
        *,
        shop_domain: str,
        access_token: str,
        workspace_name: str,
        brand_name: str,
        logo_url: str,
        css_vars: dict[str, str],
        font_urls: list[str],
        data_theme: str | None = None,
        theme_id: str | None = None,
        theme_name: str | None = None,
    ) -> dict[str, str]:
        cleaned_workspace_name = workspace_name.strip()
        if not cleaned_workspace_name:
            raise ShopifyApiError(message="workspaceName must be a non-empty string.", status_code=400)
        cleaned_brand_name = brand_name.strip()
        if not cleaned_brand_name:
            raise ShopifyApiError(message="brandName must be a non-empty string.", status_code=400)
        cleaned_logo_url = logo_url.strip()
        if not (cleaned_logo_url.startswith("https://") or cleaned_logo_url.startswith("http://")):
            raise ShopifyApiError(message="logoUrl must be an absolute http(s) URL.", status_code=400)
        if any(char in cleaned_logo_url for char in ('"', "'", "<", ">", "\n", "\r")):
            raise ShopifyApiError(
                message="logoUrl contains unsupported characters.",
                status_code=400,
            )

        normalized_css_vars = self._normalize_theme_brand_css_vars(css_vars)
        normalized_font_urls = self._normalize_theme_brand_font_urls(font_urls)
        cleaned_data_theme: str | None = None
        if data_theme is not None:
            cleaned_data_theme = data_theme.strip()
            if not cleaned_data_theme:
                raise ShopifyApiError(message="dataTheme cannot be empty when provided.", status_code=400)
            if any(char in cleaned_data_theme for char in ('"', "'", "<", ">", "\n", "\r")):
                raise ShopifyApiError(
                    message="dataTheme contains unsupported characters.",
                    status_code=400,
                )

        normalized_theme_id = theme_id.strip() if isinstance(theme_id, str) and theme_id.strip() else None
        normalized_theme_name = theme_name.strip() if isinstance(theme_name, str) and theme_name.strip() else None
        if bool(normalized_theme_id) == bool(normalized_theme_name):
            raise ShopifyApiError(
                message="Exactly one of themeId or themeName is required.",
                status_code=400,
            )
        theme = await self._resolve_theme_for_brand_sync(
            shop_domain=shop_domain,
            access_token=access_token,
            theme_id=normalized_theme_id,
            theme_name=normalized_theme_name,
        )

        layout_content = await self._load_theme_file_text(
            shop_domain=shop_domain,
            access_token=access_token,
            theme_id=theme["id"],
            filename=_THEME_BRAND_LAYOUT_FILENAME,
        )

        workspace_slug = self._normalize_workspace_slug(cleaned_workspace_name)
        css_filename = f"assets/{workspace_slug}-workspace-brand.css"
        replacement_block = self._render_theme_brand_liquid_block(
            css_filename=css_filename,
            workspace_name=cleaned_workspace_name,
            brand_name=cleaned_brand_name,
            logo_url=cleaned_logo_url,
            data_theme=cleaned_data_theme,
        )
        next_layout = self._replace_theme_brand_liquid_block(
            layout_content=layout_content,
            replacement_block=replacement_block,
        )
        css_content = self._render_theme_brand_css(
            workspace_name=cleaned_workspace_name,
            brand_name=cleaned_brand_name,
            logo_url=cleaned_logo_url,
            data_theme=cleaned_data_theme,
            css_vars=normalized_css_vars,
            font_urls=normalized_font_urls,
        )

        job_id = await self._upsert_theme_files(
            shop_domain=shop_domain,
            access_token=access_token,
            theme_id=theme["id"],
            files=[
                {"filename": _THEME_BRAND_LAYOUT_FILENAME, "content": next_layout},
                {"filename": css_filename, "content": css_content},
            ],
        )
        await self._wait_for_job_completion(
            shop_domain=shop_domain,
            access_token=access_token,
            job_id=job_id,
        )

        return {
            "themeId": theme["id"],
            "themeName": theme["name"],
            "themeRole": theme["role"],
            "layoutFilename": _THEME_BRAND_LAYOUT_FILENAME,
            "cssFilename": css_filename,
            "jobId": job_id,
        }

    async def _admin_graphql(
        self,
        *,
        shop_domain: str,
        access_token: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        url = f"https://{shop_domain}/admin/api/{settings.SHOPIFY_ADMIN_API_VERSION}/graphql.json"
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": access_token,
        }
        response = await self._post_json(url=url, payload=payload, headers=headers)
        data = response.get("data")
        errors = response.get("errors")
        if errors:
            raise ShopifyApiError(message=f"Admin GraphQL errors: {errors}")
        if not isinstance(data, dict):
            raise ShopifyApiError(message="Admin GraphQL response is missing data")
        return data

    async def _storefront_graphql(
        self,
        *,
        shop_domain: str,
        storefront_access_token: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        url = f"https://{shop_domain}/api/{settings.SHOPIFY_STOREFRONT_API_VERSION}/graphql.json"
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Storefront-Access-Token": storefront_access_token,
        }
        response = await self._post_json(url=url, payload=payload, headers=headers)
        data = response.get("data")
        errors = response.get("errors")
        if errors:
            raise ShopifyApiError(message=f"Storefront GraphQL errors: {errors}", status_code=409)
        if not isinstance(data, dict):
            raise ShopifyApiError(message="Storefront GraphQL response is missing data", status_code=409)
        return data

    async def _post_json(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise ShopifyApiError(message=f"Network error while calling Shopify: {exc}") from exc

        if response.status_code >= 400:
            raise ShopifyApiError(
                message=f"Shopify API call failed ({response.status_code}): {response.text}",
                status_code=502,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise ShopifyApiError(message="Shopify API returned invalid JSON") from exc

        if not isinstance(body, dict):
            raise ShopifyApiError(message="Shopify API response must be a JSON object")
        return body
