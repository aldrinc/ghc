# Shopify App Setup Handoff

Last updated: 2026-03-18

This document is for the person creating or updating the Shopify app configuration for `mOS`.

Use the values in this document exactly as written. Do not substitute different scopes, URLs, API versions, or install-flow settings unless you are explicitly told to do so.

## Goal

Create or update the Shopify app so it matches the required production configuration for `mOS`.

## Required app configuration

### App identity

- App name: `mOS`

### Access

- Redirect URL:
  - `https://app.moshq.app/auth/callback`
- Scopes:
  - `read_customer_events`
  - `read_discounts`
  - `write_discounts`
  - `write_inventory`
  - `read_inventory`
  - `read_online_store_navigation`
  - `write_online_store_navigation`
  - `read_orders`
  - `write_orders`
  - `read_products`
  - `write_products`
  - `read_publications`
  - `write_publications`
  - `read_content`
  - `write_content`
  - `read_themes`
  - `write_themes`
  - `write_pixels`
  - `unauthenticated_read_product_listings`
- Use legacy install flow:
  - `false`

### App URL

- App URL:
  - `https://app.moshq.app`
- Embedded in Shopify admin:
  - `true`

### Webhooks

- Webhooks API version:
  - `2026-01`

## Shopify Dev Dashboard steps

### 1. Create the app

1. Go to the Shopify Dev Dashboard: [https://dev.shopify.com](https://dev.shopify.com)
2. Open `Apps`.
3. Click `Create app`.
4. Choose `Start from Dev Dashboard`.
5. Set the app name to `mOS`.
6. Create the app.

### 2. Create and release a version

1. Open the new app.
2. Go to `Versions`.
3. Click `Create a version`.
4. Enter the configuration from the `Required app configuration` section above.
5. Make sure `Embed app in Shopify admin` is enabled.
6. Release the version.

## Copy/paste block

Use this block if Shopify accepts scopes as a comma-separated string:

```text
App name: mOS
Redirect URL: https://app.moshq.app/auth/callback
Scopes: read_customer_events,read_discounts,write_discounts,write_inventory,read_inventory,read_online_store_navigation,write_online_store_navigation,read_orders,write_orders,read_products,write_products,read_publications,write_publications,read_content,write_content,read_themes,write_themes,write_pixels,unauthenticated_read_product_listings
Use legacy install flow: false
App URL: https://app.moshq.app
Embedded: true
Webhooks API version: 2026-01
```

## Important notes

- Do not change the callback URL.
- Do not remove scopes because they "seem optional". If Shopify blocks any scope or requires review, stop and report exactly which scope triggered the issue.
- Do not switch the webhooks API version to a newer value just because it is available. Use `2026-01`.
- If the dashboard shows a trailing slash variant for the app URL, use `https://app.moshq.app` unless Shopify forces normalization.

## After setup, send back

Please send all of the following:

1. Confirmation that the app was created or updated successfully.
2. The Shopify `Client ID` / API key.
3. The Shopify `Client secret` / API secret.
4. A screenshot of the released app version showing:
   - App URL
   - Redirect URL
   - Scopes
   - Embedded status
   - Webhooks API version
5. Any approval or access-request blockers encountered in Shopify.

## Likely approval note

Because this app requests order-related and other sensitive access, Shopify may require additional approval or protected customer data review before all scopes work on non-development stores. If that happens, do not change the scope list. Report the exact Shopify message instead.

## References

- Create apps using the Dev Dashboard: [https://shopify.dev/docs/apps/build/dev-dashboard/create-apps-using-dev-dashboard](https://shopify.dev/docs/apps/build/dev-dashboard/create-apps-using-dev-dashboard)
- Deploy app versions from the Dev Dashboard: [https://shopify.dev/docs/apps/launch/deployment/deploy-app-versions](https://shopify.dev/docs/apps/launch/deployment/deploy-app-versions)
- Turn on embedding in the Dev Dashboard: [https://shopify.dev/docs/api/app-bridge/previous-versions/app-bridge-from-npm/app-setup](https://shopify.dev/docs/api/app-bridge/previous-versions/app-bridge-from-npm/app-setup)
- Shopify API access scopes: [https://shopify.dev/docs/api/usage/access-scopes](https://shopify.dev/docs/api/usage/access-scopes)
- Protected customer data requirements: [https://shopify.dev/docs/apps/launch/protected-customer-data](https://shopify.dev/docs/apps/launch/protected-customer-data)
