# Shopify Partner Dashboard Checklist (Single Public App, Listed)

Last updated: 2026-03-05

This checklist matches the current code/config in this repository and the
single-app architecture (no separate internal Shopify app).

## 1) Pre-flight (must be true before submission)

1. Stable production domain is live (no ngrok for review):
   - `https://shopify.moshq.app`
2. App config values are deployed and correct:
   - `application_url`: `https://shopify.moshq.app/`
   - OAuth callback: `https://shopify.moshq.app/auth/callback`
3. Embedded app entry is reachable in Shopify admin:
   - `GET /app` loads inside admin iframe.
4. Compliance webhook endpoint is live:
   - `POST /webhooks/compliance`
5. Direct theme write operations are intentionally disabled by policy:
   - `/v1/themes/brand/sync` returns `403`
   - `/v1/themes/brand/export` returns `403`
   - mOS `/shopify/theme/brand/sync*` and publish endpoints return `409`
6. App URL entrypoint is operational:
   - `GET /` returns `200` (informational page) or valid Shopify-context redirect.

## 2) Partner Dashboard: App Setup

In Partner Dashboard -> your app -> **App setup**:

1. `App URL`:
   - `https://shopify.moshq.app/`
2. `Allowed redirection URL(s)`:
   - `https://shopify.moshq.app/auth/callback`
3. Embedded app:
   - Enabled (`embedded = true`)
4. Admin API scopes:
   - `read_products,write_products,read_orders,read_content,write_content,read_inventory,write_inventory,read_themes,unauthenticated_read_product_listings`
5. Webhooks API version:
   - `2026-04` (keep aligned with `shopify.app.toml`)
6. Compliance webhook subscriptions:
   - `customers/data_request`
   - `customers/redact`
   - `shop/redact`
   - URI: `/webhooks/compliance`

## 3) Partner Dashboard: Distribution

In Partner Dashboard -> **Distribution**:

1. Select **Public distribution**.
2. Set visibility to **Listed** (full visibility) after review approval.
3. Confirm install link works on multiple stores.

## 4) Partner Dashboard: Listing + Review Metadata

In Partner Dashboard -> **Listing** / **Store listing**:

1. App name, short description, long description.
2. Support contact email and support URL.
3. Privacy policy URL and terms URL.
4. Pricing set to **Free** (launch state).
5. Screenshots + demo assets.
6. Clear statement of storefront behavior:
   - app does not provide manual theme-code edit/export workflows
   - storefront changes are delivered through approved extension-based rollout

## 5) Partner Dashboard: Data & Compliance

1. Confirm privacy webhooks are configured and reachable.
2. Verify production secrets are configured:
   - `SHOPIFY_APP_API_SECRET` (Shopify webhook HMAC verification)
   - `MOS_WEBHOOK_SHARED_SECRET` (bridge-to-mOS forwarding authentication)
3. If Partner Dashboard flags protected customer data requirements for your
   scopes/features, complete that request before/with submission.

## 6) Reviewer Notes (paste into submission)

Use this in the “Notes for reviewer” field (edit as needed):

1. Install app from generated install link.
2. Open embedded admin page (`/app`) after install.
3. Connect workspace and verify Shopify status is `ready`.
4. Confirm storefront token status becomes `ready` in the embedded app.
5. Confirm direct theme sync/export/publish endpoints are intentionally blocked and
   storefront changes are handled through the approved extension-based rollout.
6. Compliance webhooks are implemented for `customers/data_request`,
   `customers/redact`, and `shop/redact`.

## 7) Submission Gate (must all be green)

1. No ngrok URLs in production app URL or redirect URLs.
2. Embedded app loads inside Shopify admin.
3. OAuth install/callback succeeds from a fresh store.
4. Compliance webhook endpoint verified.
5. Support/legal/listing assets complete.
6. Review notes include exact tester path.

## 8) Policy References

1. App requirements:
   - https://shopify.dev/docs/apps/launch/app-store-review/app-requirements
2. Pass app review:
   - https://shopify.dev/docs/apps/launch/app-store-review/pass-app-review
3. Submit app for review:
   - https://shopify.dev/docs/apps/launch/app-store-review/submit-app-for-review
4. Listing and visibility:
   - https://shopify.dev/docs/apps/launch/distribution/list-apps
5. Privacy law compliance:
   - https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
6. Support expectations:
   - https://shopify.dev/docs/apps/launch/distribution/support-your-customers
