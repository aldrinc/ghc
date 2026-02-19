# Shopify Connection + Product Mapping Flow (Product Page First)

## Goal

Make Shopify setup happen from the Product page.
Do not let users proceed with Shopify-dependent actions unless the store connection is fully valid for Admin API + checkout use.

This replaces the earlier idea of collecting Shopify connection during onboarding.

## Why this direction

- The Product page is where users already manage product mappings (`shopifyProductGid`, variants, provider, external price id).
- Shopify setup is operational setup, not core brand onboarding.
- We can enforce strict readiness checks right where the user expects Shopify actions.

## Current baseline in code

- Product page already has manual Shopify product GID mapping UI: `mos/frontend/src/pages/workspaces/ProductDetailPage.tsx:302`.
- Backend can validate product existence via Shopify bridge: `mos/backend/app/services/shopify_catalog.py:25`.
- Shopify bridge owns OAuth install and installation records: `shopify-funnel-app/app/main.py:89`.
- Checkout requires bridge + storefront token and fails if missing: `shopify-funnel-app/app/main.py:272`.

## Production configuration checklist

Required because Product page Shopify actions call `mos/backend`, and `mos/backend` calls `shopify-funnel-app`.

1. Configure `shopify-funnel-app` (the bridge service):
- `SHOPIFY_APP_BASE_URL=https://<public-bridge-domain>`
- `SHOPIFY_INTERNAL_API_TOKEN=<shared-secret>`

2. Configure `mos/backend`:
- `SHOPIFY_APP_BASE_URL=https://<same-bridge-domain>`
- `SHOPIFY_INTERNAL_API_TOKEN=<same value as bridge token>`

3. Important URL constraint:
- `SHOPIFY_APP_BASE_URL` is used for both:
  - server-to-server calls from `mos/backend` to bridge (`/admin/installations`, `/v1/catalog/*`, `/v1/checkouts`)
  - browser redirect during connect flow (`/auth/install?...`)
- So this URL must be reachable by both backend runtime and end-user browser.

4. Restart/redeploy requirements:
- `mos/backend` must be restarted after env changes.
- `shopify-funnel-app` must be restarted after env changes.

5. Failure mapping:
- `Shopify checkout bridge is not configured in mos/backend...`:
  - missing `SHOPIFY_APP_BASE_URL` in `mos/backend`
- `Shopify checkout bridge auth is not configured in mos/backend...`:
  - missing `SHOPIFY_INTERNAL_API_TOKEN` in `mos/backend`
- `Shopify checkout app error: Unauthorized`:
  - token mismatch between backend `SHOPIFY_INTERNAL_API_TOKEN` and bridge token

## UX: Product Page State Machine

Show a dedicated `Shopify Connection` card on product detail.

Connection states:

1. `not_connected`
- No active installation for this workspace/client.
- CTA: `Connect Shopify`.

2. `installed_missing_storefront_token`
- App installed, but storefront token missing.
- CTA: `Set storefront token`.

3. `multiple_installations_conflict`
- More than one active shop linked to same workspace/client.
- CTA: `Choose active shop` (explicit shop selection required).

4. `ready`
- Exactly one active installation (or explicit selected shop), required scopes present, storefront token present.
- Enable product/variant mapping actions.

5. `error`
- Connection check failed or invalid config.
- Show error detail from backend and block Shopify operations.

No silent fallback between states.

## End-to-end flow

### A) Product page load -> resolve Shopify status

Frontend:
- On `ProductDetailPage` load, call backend status endpoint for product's `client_id`.

Backend:
- Query Shopify bridge installations for this client.
- Validate invariants (count, scopes, token presence).
- Return normalized status payload.

If status is not `ready`, keep Shopify-dependent actions disabled.

### B) Connect Shopify (install app)

Frontend:
- User clicks `Connect Shopify`.
- Prompt for `shopDomain` if unknown.
- Call backend `install-url` endpoint.
- Redirect browser to returned install URL.

Backend:
- Validate `shopDomain` format (`*.myshopify.com`) and client ownership.
- Generate install URL against bridge:
  - `/auth/install?shop={shop}.myshopify.com&client_id={client_id}`
- Return URL only if validation passes.

Bridge:
- Completes OAuth callback and stores installation.

Frontend return:
- User lands back on Product page.
- Product page immediately re-checks status.

### C) Post-install configuration gate

If app is installed but not fully configured:

- Require storefront token (`storefrontAccessToken`) before checkout readiness.
- Show `Set storefront token` action that hits backend patch endpoint.
- Re-check status after patch.

### D) Product mapping

Once status is `ready`, allow mapping flow:

Option 1: `Map existing Shopify product`
- User inputs/selects Shopify product GID.
- Backend verifies product exists in connected shop.
- Save `shopifyProductGid` on MOS product.

Option 2: `Create product in Shopify`
- User provides minimum create data.
- Backend creates Shopify product + at least one variant.
- Save returned product GID + variant GIDs to MOS.

### E) Variant checkout mapping gate

Before Shopify checkout is considered enabled for this product:

- At least one MOS variant must have:
  - `provider = "shopify"`
  - `externalPriceId = gid://shopify/ProductVariant/...`
- If missing, show explicit blocking validation and keep checkout readiness false.

## Required readiness invariants

`ready` means all are true:

1. Shopify app installed and active for client.
2. Required Admin API scopes are present.
3. Storefront token is present.
4. No ambiguous installation selection:
- either exactly one active shop for client
- or explicit shop selected and persisted

If any invariant fails, return non-ready state with specific reason.

## API plan (backend-owned)

Frontend must not call bridge admin endpoints directly.
Frontend must never know internal bridge token.

### 1) `GET /clients/{client_id}/shopify/status`

Returns:
- `state`: `not_connected | installed_missing_storefront_token | multiple_installations_conflict | ready | error`
- `shopDomain` (when resolvable)
- `missingScopes` (array)
- `hasStorefrontAccessToken` (bool)
- `message` (user-facing)

Errors:
- `404` client not found
- `500` bridge misconfiguration

### 2) `POST /clients/{client_id}/shopify/install-url`

Input:
- `shopDomain`
- optional `returnPath` (validated)

Returns:
- `installUrl`

Errors:
- `400` invalid shop domain
- `404` client not found
- `409` client/shop mismatch conflict
- `500` bridge base URL not configured

### 3) `PATCH /clients/{client_id}/shopify/installation`

Input:
- `shopDomain`
- `storefrontAccessToken` (required for this action)
- optional `setAsDefault` when multiple shops exist

Returns updated status payload.

Errors:
- `400` empty token
- `404` installation not found
- `409` ambiguous installation

### 4) `POST /clients/{client_id}/shopify/verify-product`

Input:
- `productGid`
- optional `shopDomain` if multi-shop

Returns:
- verified product metadata (`id`, `title`, `handle`, `shopDomain`)

Errors:
- `400` invalid GID format
- `404` no installation
- `409` not found in shop / conflict

### 5) `POST /clients/{client_id}/shopify/products`

Input:
- create payload (title + at least one variant)
- optional `shopDomain`

Returns:
- created Shopify product + variants (GIDs)

Errors:
- `400` invalid payload
- `404` installation not found
- `409` connection not ready
- `502` Shopify API upstream failure

## Product page UI changes

In `ProductDetailPage`:

1. Replace current simple `Shopify Mapping` block with two sections:
- `Shopify Connection`
- `Shopify Product Mapping`

2. `Shopify Connection` section:
- Status badge + message
- Actions based on state:
  - `Connect Shopify`
  - `Set storefront token`
  - `Refresh status`
  - `Choose default shop` (when conflict)

3. `Shopify Product Mapping` section:
- disabled until status = `ready`
- supports map existing/create new
- persists `shopifyProductGid`

4. Variant table:
- add `Shopify mapped` indicator when `provider=shopify` and valid variant GID exists
- show blocking message if no checkout-eligible variant exists

## Operational checks for "configured correctly"

For Admin API work:
- installation exists
- required scopes present
- admin token is valid (verified by successful lightweight admin call)

For checkout work:
- all of the above plus storefront token present

For webhook/order attribution work:
- if order forwarding is part of the workspace setup, validate bridge forwarding config and secret match
- if not configured, mark attribution as not ready and return explicit state

## Strict error policy

- No fallback to guessed shops.
- No automatic scope downgrades.
- No defaulting to "first installation" when multiple shops are linked.
- Every blocked action returns a specific status code + actionable error detail.

## Implementation phases

### Phase 1 (fast, high value)

- Add status + install-url + installation patch endpoints in `mos/backend`.
- Add `Shopify Connection` card in `ProductDetailPage`.
- Keep product mapping manual (current GID input), but gated by status.

### Phase 2

- Add backend product lookup/list endpoint for connected shop.
- Add existing product picker in UI.
- Add strict variant mapping readiness check in UI + backend.

### Phase 3

- Add create-product-in-Shopify endpoint and UI flow.
- Auto-create MOS variants from created Shopify variants.
- Add explicit default-shop selection UI for multi-shop clients.

### Phase 3.5

- Add strict duplicate guard when importing created Shopify variants:
  - reject if incoming Shopify variant GID already exists on MOS product
  - reject if incoming Shopify variant title matches an existing Shopify-mapped MOS variant title (case-insensitive)
- Add product-page import summary after `Create product in Shopify`:
  - show shop domain
  - show created product GID
  - show imported variant count and titles
- Keep failure mode explicit (`409`) with actionable error detail; do not silently merge duplicates.

## Acceptance criteria

1. If Shopify is not connected, product page clearly shows `Connect Shopify` and blocks Shopify mapping actions.
2. After OAuth install, status transitions to either `installed_missing_storefront_token` or `ready` (never ambiguous silent state).
3. Shopify mapping actions only enable in `ready` state.
4. Attempting Shopify checkout with missing/invalid mapping fails with explicit 4xx error.
5. Multi-store ambiguity is surfaced as `multiple_installations_conflict` until user resolves it.
6. Creating in Shopify fails with `409` when imported variants would duplicate existing Shopify variant title/GID mappings.
7. After successful Shopify creation/import, product page shows a clear import summary for operator verification.
