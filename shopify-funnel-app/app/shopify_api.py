from __future__ import annotations

from typing import Any

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
