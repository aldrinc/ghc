# Marketi Shopify Funnel App

This service is a Shopify app bridge for Marketi funnels. It does three things:

1. Handles Shopify OAuth installation and stores per-shop admin tokens.
2. Creates Storefront carts (`cartCreate`) and returns Shopify-hosted `checkoutUrl` values.
3. Receives Shopify order webhooks and forwards them to `mos/backend` so funnel order attribution can be recorded.

## What this app does not do

- It does not create Shopify stores. Store creation remains manual/merchant-driven.
- It does not customize Shopify checkout pages. It only redirects to hosted checkout.

## Endpoints

- `GET /auth/install?shop={shop}.myshopify.com&client_id={mos_client_uuid}`
- `GET /auth/callback`
- `GET /admin/installations` (Bearer internal token)
- `PATCH /admin/installations/{shop}.myshopify.com` (Bearer internal token)
- `POST /v1/checkouts` (Bearer internal token)
- `POST /webhooks/orders/create`
- `POST /webhooks/app/uninstalled`

## Local run

1. Copy `.env.example` to `.env` and fill required values.
2. Run:

```bash
cd shopify-funnel-app
uvicorn app.main:app --reload --port 8011
```

3. Expose it with a tunnel (for OAuth/webhooks), then set `SHOPIFY_APP_BASE_URL` to that public URL.

## OAuth install flow

1. Open:

```text
{SHOPIFY_APP_BASE_URL}/auth/install?shop={shop}.myshopify.com&client_id={mos_client_uuid}
```

2. Approve requested scopes in Shopify.
3. After callback, the installation is stored and webhooks are registered.

## Storefront token setup

The app requires a storefront access token per shop to run `cartCreate`.

Set/update it with:

```bash
curl -X PATCH "http://localhost:8011/admin/installations/{shop}.myshopify.com" \
  -H "Authorization: Bearer ${SHOPIFY_INTERNAL_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"storefrontAccessToken":"<storefront_token>","clientId":"<mos_client_uuid>"}'
```

## Checkout request format

`POST /v1/checkouts`

```json
{
  "clientId": "<mos_client_uuid>",
  "lines": [
    {
      "merchandiseId": "gid://shopify/ProductVariant/1234567890",
      "quantity": 1
    }
  ],
  "attributes": {
    "funnel_id": "<uuid>",
    "offer_id": "<uuid>",
    "price_point_id": "<uuid>",
    "quantity": "1"
  }
}
```

Response:

```json
{
  "shopDomain": "example.myshopify.com",
  "cartId": "gid://shopify/Cart/...",
  "checkoutUrl": "https://example.myshopify.com/cart/c/..."
}
```

## Webhook forwarding to `mos/backend`

When `SHOPIFY_ENABLE_ORDER_FORWARDING=true`, `orders/create` is forwarded to:

- `POST {MOS_BACKEND_BASE_URL}/shopify/orders/webhook`
- Header: `x-marketi-webhook-secret: {MOS_WEBHOOK_SHARED_SECRET}`

Only orders with `note_attributes.funnel_id` are forwarded.

## Protected customer data note (important)

If Shopify returns:

`Webhook registration failed for ORDERS_CREATE ... protected customer data`

set `SHOPIFY_ENABLE_ORDER_FORWARDING=false` while testing checkout creation. In this mode, app install still works and checkout generation still works, but order forwarding is disabled until protected customer data access is approved for the app.

## Dev store storefront password

Dev stores often have storefront password protection enabled. In that case, checkout URLs can redirect to `/password` for logged-out visitors. Disable the storefront password in the dev store or test while authenticated in the storefront session.

If checkout shows `Out of stock` after redirect, verify storefront lock state first. When the Storefront API returns `Online Store channel is locked`, disable storefront password protection in the dev store and retry with a fresh checkout URL.

## Tests

```bash
cd shopify-funnel-app
pytest -q
```
