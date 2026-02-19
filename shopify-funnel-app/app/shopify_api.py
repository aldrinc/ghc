from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any, Literal

import httpx

from app.config import settings


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
