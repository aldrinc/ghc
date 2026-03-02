# Shopify Order Page Integration Onboarding

This is the one-time setup required to run Marketi funnel order pages using Shopify-hosted checkout.

## 1) Create the Shopify app (one-time in Partner Dashboard)

1. Create a new app in Shopify Partner Dashboard.
2. Set app URLs:
- App URL: `{SHOPIFY_APP_BASE_URL}`
- Allowed redirection URL: `{SHOPIFY_APP_BASE_URL}/auth/callback`
3. Configure Admin API scopes (minimum for current implementation):
- `read_orders`
- `write_orders`
- `unauthenticated_read_product_listings`
- `read_products`
- `write_products`
- `read_discounts`
- `write_discounts`

## 2) Configure and run the new Shopify bridge service

Folder: `shopify-funnel-app`

1. Copy `shopify-funnel-app/.env.example` to `shopify-funnel-app/.env`.
2. Fill required values:
- `SHOPIFY_APP_API_KEY`
- `SHOPIFY_APP_API_SECRET`
- `SHOPIFY_APP_BASE_URL`
- `SHOPIFY_INTERNAL_API_TOKEN`
- `MOS_BACKEND_BASE_URL`
- `MOS_WEBHOOK_SHARED_SECRET`
3. Start the service:

```bash
cd shopify-funnel-app
uvicorn app.main:app --reload --port 8011
```

## 3) Configure `mos/backend` to use the bridge

In `mos/backend/.env` set:

- `SHOPIFY_APP_BASE_URL=http://localhost:8011`
- `SHOPIFY_INTERNAL_API_TOKEN=<same value configured as SHOPIFY_INTERNAL_API_TOKEN in shopify-funnel-app>`
- `SHOPIFY_ORDER_WEBHOOK_SECRET=<same as MOS_WEBHOOK_SHARED_SECRET>`

Restart backend after setting these.

### Production notes

- `SHOPIFY_APP_BASE_URL` in `mos/backend` must point to the same bridge host used by `shopify-funnel-app` `SHOPIFY_APP_BASE_URL`.
- This host must be reachable by both:
  - end-user browser (for `/auth/install` redirect)
  - `mos/backend` runtime (for server-to-server bridge calls)
- `SHOPIFY_INTERNAL_API_TOKEN` in `mos/backend` and `SHOPIFY_INTERNAL_API_TOKEN` in `shopify-funnel-app` must match exactly.
- After any env change, redeploy/restart both services.

## 4) Install app into your Shopify store and link to a Marketi client

1. Open install URL:

```text
{SHOPIFY_APP_BASE_URL}/auth/install?shop={your-store}.myshopify.com&client_id={mos_client_uuid}
```

2. Approve permissions.
3. Verify install exists:

```bash
curl "http://localhost:8011/admin/installations" \
  -H "Authorization: Bearer ${SHOPIFY_INTERNAL_API_TOKEN}"
```

If OAuth callback fails with an `ORDERS_CREATE` protected customer data error, set `SHOPIFY_ENABLE_ORDER_FORWARDING=false` in `shopify-funnel-app/.env` and retry install. This keeps checkout creation working while webhook forwarding remains disabled.

## 5) Storefront token setup (automatic + recovery)

After OAuth install, the bridge automatically attempts storefront token creation.

If status still shows `installed_missing_storefront_token`, retry automatic setup:

```bash
curl -X POST "http://localhost:8011/admin/installations/{your-store}.myshopify.com/storefront-token/auto" \
  -H "Authorization: Bearer ${SHOPIFY_INTERNAL_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"clientId":"<mos_client_uuid>"}'
```

If auto setup still fails, manually set a storefront token:

```bash
curl -X PATCH "http://localhost:8011/admin/installations/{your-store}.myshopify.com" \
  -H "Authorization: Bearer ${SHOPIFY_INTERNAL_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"storefrontAccessToken":"<storefront_token>","clientId":"<mos_client_uuid>"}'
```

## 6) Configure funnel offer price points to use Shopify

For each offer price point that should checkout through Shopify:

- `provider = "shopify"`
- `externalPriceId = "gid://shopify/ProductVariant/<variant_id>"`

This is read by `POST /public/checkout` and converted into a Storefront `cartCreate` call.

## 7) End-to-end validation path

1. Open funnel page.
2. Click CTA on the order section.
3. Frontend calls `POST /public/checkout`.
4. Backend calls `shopify-funnel-app /v1/checkouts`.
5. User is redirected to Shopify `checkoutUrl`.
6. On paid order, Shopify sends `orders/create` webhook to `shopify-funnel-app`.
7. Bridge forwards event to `mos/backend /shopify/orders/webhook`.
8. Backend records order row in `funnel_orders` and emits `order_completed` event.

## Notes

- Store provisioning remains manual in Shopify.
- Checkout page customization remains limited on non-Plus plans.
- If multiple Shopify stores are linked to one Marketi client, checkout creation by `clientId` will fail with a clear conflict. In that case use explicit shop targeting in bridge requests.
- Dev stores may redirect checkout URLs to `/password` if storefront password protection is enabled.
- If checkout removes items as out of stock in a dev store, confirm storefront lock isn’t enabled (`Online Store channel is locked`) and disable storefront password protection before retesting.
