# Medusa as Shopify Replacement: Full Integration, Storefront, Templating, and Migration Plan

## Purpose

This document is the single implementation brief for replacing Shopify with Medusa in Marketi.

It covers:

- the target system architecture
- how MOS and Medusa should split responsibilities
- what capabilities we gain after the swap
- how storefront templating, styling, and site import should work
- how payment providers (Stripe, PayPal, Apple Pay, Google Pay) work through Medusa
- how ad platform integrations (Meta CAPI/pixel, TikTok, GA4) and telemetry carry over
- how to deploy and operate Medusa infrastructure
- how the agentic onboarding and workspace setup flow provisions commerce automatically
- how to migrate from the current Shopify-dependent stack
- how to do this without blowing up compute costs

This plan is based on:

- the current codebase in this repository (audited March 19, 2026)
- Medusa official documentation checked on March 12, 2026

## Executive Summary

The correct architecture is:

- **MOS remains the storefront authoring, rendering, experiment, design-system, import, preview, and deployment layer**
- **Medusa becomes the commerce backend**

That means:

- We do **not** replace MOS's page/template runtime with a stock Medusa storefront.
- We do **not** rebuild the Shopify theme model inside Medusa.
- We do **not** clone websites as raw HTML and call them templates.

Instead, we:

1. Replace Shopify-specific commerce dependencies with a Medusa adapter layer.
2. Keep MOS as the place where pages, templates, design systems, testimonial blocks, and experiments are created.
3. Generalize the existing funnel/template system into a full storefront template system.
4. Add a robust import pipeline that turns strong reference sites into reusable Marketi template families.
5. Run Medusa economically using pooled infrastructure and a reusable Marketi plugin/customization package.

## What The Current System Actually Is

Today Shopify is not only checkout. It is woven into several different responsibilities across 20+ files.

### Shopify-dependent areas in the repo

**Standalone bridge app:**

- `shopify-funnel-app/`
  - OAuth install and installation records
  - Storefront token provisioning (automatic + manual override)
  - Cart creation via Storefront API `cartCreate`
  - Order webhook forwarding to MOS
  - GDPR compliance webhooks (customers/data_request, customers/redact, shop/redact)
  - App uninstall hook
  - Baseline theme zip asset (`theme/futrgroup2-theme.zip`)

**Backend services (6 files):**

- `mos/backend/app/services/shopify_checkout.py`
  - Converts MOS checkout requests into Shopify cart/checkout bridge calls
  - Validates variant GIDs (`gid://shopify/ProductVariant/...`)
  - Calls `shopify-funnel-app` via internal bearer token

- `mos/backend/app/services/shopify_connection.py` (~3,500 lines)
  - Shop domain normalization (including custom storefront domains)
  - OAuth scope validation
  - Product listing, creation, validation
  - Variant updates (price, SKU, barcode, inventory policy)
  - Catalog collection synchronization
  - Theme template draft workflows
  - Brand sync job coordination
  - Policy page synchronization

- `mos/backend/app/services/shopify_catalog.py`
  - Verifies Shopify product GIDs exist in connected store

- `mos/backend/app/services/shopify_collection_sync.py`
  - Lists workspace product GIDs, syncs as a Shopify collection

- `mos/backend/app/services/shopify_theme_content_planner.py`
  - AI-powered theme content and template slot planning

- `mos/backend/app/services/shopify_theme_copy_agent.py`
  - AI copywriting for Shopify theme templates

**Backend routers (5 files with Shopify-specific endpoints):**

- `mos/backend/app/routers/public_funnels.py`
  - Runtime checkout switching between Stripe and Shopify via `variant.provider`

- `mos/backend/app/routers/shopify_webhooks.py`
  - Order ingestion, attribution recording (`FunnelOrder` + `FunnelEvent`)
  - Meta pixel conversion forwarding for completed orders
  - GDPR compliance webhook handling

- `mos/backend/app/routers/clients.py` (~15 Shopify-specific endpoints)
  - Connection status, app credentials, OAuth install URL
  - Installation management (update, delete, set default shop)
  - Shopify product listing
  - Theme brand sync (async job management)
  - Theme template draft operations (build, generate images, publish)

- `mos/backend/app/routers/products.py`
  - Create product in Shopify, sync variants, full product sync

- `mos/backend/app/routers/compliance.py`
  - Sync MOS-generated compliance policies to Shopify

**Backend schemas:**

- `mos/backend/app/schemas/shopify.py` - webhook payload schemas
- `mos/backend/app/schemas/shopify_connection.py` - ~55 Pydantic classes for installation, products, variants, themes, credentials

**Data layer:**

- `mos/backend/app/db/models.py`
  - `Product.shopify_product_gid` (indexed)
  - `ProductVariant.shopify_last_synced_at`
  - `ProductVariant.shopify_last_sync_error`
  - `ClientShopifyAppCredential` model
  - `ShopifyThemeTemplateDraft` model
  - `ShopifyThemeTemplateDraftVersion` model

- `mos/backend/app/db/repositories/shopify_theme_template_drafts.py`
  - CRUD for theme draft records

**Frontend (12+ files):**

- `mos/frontend/src/pages/workspaces/ProductDetailPage.tsx`
  - Shopify product mapping, create-in-Shopify, variant sync, readiness checks

- `mos/frontend/src/pages/workspaces/BrandDesignSystemPage.tsx`
  - Shopify connection UX, theme template draft flows, audit/export

- `mos/frontend/src/pages/commerce/CommercePage.tsx` + `ShopifyTab.tsx`
  - Commerce hub with dedicated Shopify tab

- `mos/frontend/src/components/commerce/`
  - `ShopifyConnectionCard.tsx` - connection status card
  - `ShopifyAppCredentialsCard.tsx` - API credentials management
  - `ThemeTemplateWorkflowCard.tsx` - theme operations
  - `CompliancePolicyCard.tsx` - policy sync

- `mos/frontend/src/api/clients.ts` - all Shopify API calls
- `mos/frontend/src/api/products.ts` - product Shopify operations
- `mos/frontend/src/api/compliance.ts` - compliance operations
- `mos/frontend/src/hooks/useShopifyAppCredentials.ts`
- `mos/frontend/src/hooks/useShopifyConnection.ts`
- `mos/frontend/src/lib/shopifyTemplateUtils.ts`

**Cross-cutting integrations not previously documented:**

- `mos/backend/app/services/meta_conversions.py`
  - Sends Meta pixel conversion events triggered by Shopify order webhooks

- `mos/backend/app/temporal/activities/campaign_intent_activities.py`
  - Shopify product references in campaign workflow activities

- `mos/backend/app/temporal/activities/strategy_v2_activities.py`
  - Shopify integration in strategy workflows

- `mos/backend/app/routers/paid_ads_qa.py`
  - Shopify in tracking provider normalization

- `mos/frontend/src/components/campaigns/CampaignMetaAdsPanel.tsx`
  - Shopify references in Meta ads campaign context

**Environment variables (8 settings):**

- `SHOPIFY_APP_BASE_URL` - bridge URL
- `SHOPIFY_INTERNAL_API_TOKEN` - bearer token for bridge
- `SHOPIFY_ORDER_WEBHOOK_SECRET` - HMAC for order webhooks
- `SHOPIFY_COMPLIANCE_WEBHOOK_SECRET` - HMAC for compliance
- `SHOPIFY_CHECKOUT_REQUEST_TIMEOUT_SECONDS` (default 20s)
- `SHOPIFY_THEME_OPERATIONS_TIMEOUT_SECONDS` (default 180s)
- `SHOPIFY_THEME_EXPORT_TIMEOUT_SECONDS` (default 600s)
- `SHOPIFY_THEME_COMPONENT_IMAGE_BATCH_SIZE` (default 4)

### What MOS already has that we should keep

- Puck-based structured page rendering and editing
- Reusable templates stored as `puckData`
- Design-system token generation and validation (~300 CSS variables in `base_tokens.json`)
- AI page editing that preserves template structure
- Static/public funnel runtime with tracking (13 event types)
- Publication/deployment primitives
- Testimonial/review media rendering

### What is already partially provider-agnostic

The variant model has two fields that are already generic:

- `ProductVariant.provider` - text field, currently supports `"stripe"` and `"shopify"`
- `ProductVariant.external_price_id` - generic external identifier (Stripe price ID or Shopify variant GID)

The checkout router (`public_funnels.py`) already branches on `variant.provider` to dispatch to the right backend. Adding `"medusa"` as a third provider value is structurally straightforward.

The public commerce schemas (`commerce.py`, `commerce.ts`) are already provider-agnostic.

This is the key insight:

> We are not replacing a simple Shopify checkout integration. We are replacing Shopify as the commerce operating system while preserving MOS as the marketing/storefront operating system. But the variant-level provider abstraction already exists — the work is extending it to cover the full surface, not building it from scratch.

## Target Architecture

## High-level split

### MOS owns

- workspace model
- products as marketing objects
- offers and experimentation context
- page authoring
- block/template system
- design systems and style governance
- testimonial and review presentation assets
- import pipeline for reference sites
- preview and publication
- deploy orchestration
- attribution and event capture

### Medusa owns

- product catalog as commerce records
- variants and options
- price sets and promotion rules
- carts
- payment orchestration
- orders
- inventory and stock locations
- sales channels
- regions/currencies/tax behavior
- fulfillment workflows
- commerce admin operations

## Why Medusa fits this split

Medusa's docs currently describe a modular commerce backend with out-of-the-box Commerce Modules including Cart, Customer, Fulfillment, Inventory, Order, Payment, Pricing, Product, Promotion, Region, Sales Channel, Stock Location, Store, and Tax. Source: [Commerce Modules](https://docs.medusajs.com/resources/commerce-modules).

The official storefront docs also explicitly state that the storefront is hosted separately from the Medusa application and that teams can choose their own frontend stack and design system. Source: [Next.js Starter Storefront](https://docs.medusajs.com/resources/nextjs-starter).

That aligns with keeping MOS as the storefront layer.

## Recommended Medusa Footprint

For Marketi, do **not** build one giant shared multi-tenant Medusa app first.

The best fit is:

- one Medusa application per workspace/store
- shared platform infrastructure beneath it
- a reusable Marketi Medusa plugin/package installed into every Medusa app

### Why

- tenant isolation is much simpler
- data migration is cleaner
- operational boundaries match today's "one client, one store" model
- workspace-specific admin customizations stay isolated
- one broken customization cannot poison every tenant

## Recommended Marketi Medusa Customization Package

Build a reusable package, for example:

- `packages/marketi-medusa-plugin`

This package should encapsulate reusable Medusa customizations across all stores.

Medusa's docs state that plugins can package modules, workflows, API routes, admin extensions, and more, specifically as the reusable path across multiple Medusa applications. Sources: [Plugins](https://docs.medusajs.com/learn/fundamentals/plugins), [Re-use customizations with plugins](https://docs.medusajs.com/learn/customization/reuse-customizations).

### The plugin should contain

- Custom module(s) for Marketi-specific storefront metadata (funnel IDs, publication IDs, attribution context)
- Workflow hooks for order attribution and post-purchase sync back to MOS
- Admin widgets/routes for Marketi-specific commerce operations
- API routes for MOS-triggered operations not covered by stock Admin APIs
- Event subscribers for completed orders, inventory changes, and promotion updates
- Meta pixel / ad platform conversion forwarding (replacing current `meta_conversions.py` Shopify path)

## What Capabilities We Gain After The Swap

## Commerce capabilities

Based on current Medusa docs, the practical gains include:

- richer catalog structure
  - products, options, variants, categories, collections, tags
- price rules and tiered pricing
  - useful for bundle pricing, offer ladders, and conditional merchandising
- inventory-aware cart validation
  - Medusa's inventory docs show add-to-cart flows validating stocked quantity when inventory is managed
- regions/currencies/tax-aware pricing
- sales channels and stock location support
- promotion module support
- fulfillment module support
- workflow-based extensibility for commerce flows

Sources:

- [Product Module](https://docs.medusajs.com/resources/commerce-modules/product)
- [Commerce Modules](https://docs.medusajs.com/resources/commerce-modules)
- [Inventory Module in Flows](https://docs.medusajs.com/resources/commerce-modules/inventory/inventory-in-flows)
- [Retrieve Variant Prices](https://docs.medusajs.com/resources/storefront-development/products/price)
- [Multi-Region Store Recipe](https://docs.medusajs.com/v2/resources/recipes/multi-region-store)

## Platform capabilities

- custom workflows around checkout and order completion
- custom data models linked to commerce entities
- admin UI extension points
- reusable customization packaging across store instances

Sources:

- [Core Workflows Reference](https://docs.medusajs.com/resources/medusa-workflows-reference)
- [Customize Medusa Admin](https://docs.medusajs.com/learn/customization/customize-admin)
- [Medusa Admin Extensions](https://docs.medusajs.com/ui/installation/medusa-admin-extension)
- [Plugins](https://docs.medusajs.com/learn/fundamentals/plugins)

## What we lose compared with Shopify

- Shopify-hosted checkout (must host our own or use Medusa's payment module)
- Shopify app ecosystem (no third-party plugins)
- Shopify theme ecosystem (irrelevant since MOS is the storefront layer)
- Built-in merchant familiarity with the Shopify admin
- Shopify's payment liability shield (PCI scope shifts to us via Medusa + payment provider)

These are real losses, so the MOS authoring + Medusa operations experience must be materially better to justify the move.

## Non-negotiable Architecture Decisions

1. MOS remains the storefront authoring and rendering layer.
2. Medusa is the commerce backend, not the template editor.
3. The current funnel/template system becomes the general storefront template system.
4. Reference sites are imported into structured components and tokens, not persisted as raw HTML themes.
5. We build a reusable Marketi Medusa customization package once, then install it into each Medusa store.
6. We use pooled infrastructure with promotion to dedicated resources for heavy tenants.
7. Ad platform conversion events (Meta, TikTok) must work end-to-end through Medusa before any workspace cuts over.

## Workstream 1: Commerce Service Integration

## Objective

Replace the current Shopify-specific bridge and runtime calls with a provider-neutral commerce layer in MOS.

## Current state

The variant model already has provider-agnostic fields (`provider`, `external_price_id`) and the checkout router already branches on `variant.provider`. The gap is that everything above variant-level checkout dispatch is Shopify-specific: product sync, catalog operations, connection management, theme workflows.

## Required changes

### 1. Add a commerce provider abstraction in MOS backend

Introduce an internal interface for:

- `get_connection_status`
- `list_products`
- `create_product`
- `get_product`
- `sync_variants`
- `update_variant`
- `create_checkout`
- `ingest_order_completion`
- `sync_policy_pages`
- `verify_product_exists`
- `sync_collection`
- `forward_conversion_event`

Implement providers:

- `shopify` (wrapping existing `shopify_connection.py`, `shopify_checkout.py`, `shopify_catalog.py`, `shopify_collection_sync.py`)
- `medusa`

This allows dual-running during migration instead of rewriting everything at once.

### 2. Extend the checkout dispatch

Today `public_funnels.py` branches by `variant.provider` and directly handles `stripe` and `shopify`.

Add a third branch for `medusa`. The checkout dispatch structure is already clean — the work is implementing the Medusa checkout adapter, not refactoring the dispatch.

For Medusa-backed products, MOS should call a Medusa checkout adapter instead of `shopify_checkout.py`.

### 3. Introduce a Medusa adapter in MOS

New backend service:

- `mos/backend/app/services/medusa_connection.py`

Responsibilities:

- Admin API calls for product/variant/catalog operations
- Store API calls for carts/checkout
- Auth/session handling for internal service-to-service use
- Strict error propagation

### 4. Migrate cross-cutting integrations

These files currently assume Shopify as the commerce source and must be updated to work with the provider abstraction:

- `meta_conversions.py` — conversion events must fire for Medusa orders, not just Shopify
- `campaign_intent_activities.py` — Temporal activities must resolve products via provider layer
- `strategy_v2_activities.py` — strategy workflows must be provider-agnostic
- `paid_ads_qa.py` — tracking provider normalization must recognize Medusa

## Workstream 2: Data Model Migration In MOS

## Objective

Remove Shopify-shaped assumptions from MOS's product and variant records while keeping the migration incremental.

## Current state

The data model is a hybrid. Variants are mostly generic, products are Shopify-specific:

**Already generic on ProductVariant:**
- `provider` — text, supports `"stripe"` and `"shopify"`
- `external_price_id` — generic external identifier
- Rich commerce fields: `sku`, `barcode`, `compare_at_price`, `weight`, `inventory_quantity`, `inventory_policy`, `requires_shipping`, `taxable`, `unit_price`, `quantity_rule`, `quantity_price_breaks`

**Still Shopify-specific:**
- `Product.shopify_product_gid` — indexed, no generic equivalent
- `ProductVariant.shopify_last_synced_at`
- `ProductVariant.shopify_last_sync_error`

**Shopify-only models (3 tables):**
- `ClientShopifyAppCredential`
- `ShopifyThemeTemplateDraft`
- `ShopifyThemeTemplateDraftVersion`

## Required schema changes

### On Product, add:

- `commerce_provider` — enum text (`"shopify"`, `"medusa"`, `"stripe"`, `null`)
- `external_product_id` — generic replacement for `shopify_product_gid`
- `external_sync_status` — replaces implicit Shopify sync state
- `external_sync_error` — generic error field
- `external_last_synced_at` — generic sync timestamp

### On ProductVariant, add:

- `external_variant_id` — explicit external variant identifier (today `external_price_id` serves double duty as both price and variant ID)
- `external_sync_status`
- `external_sync_error` — generic replacement for `shopify_last_sync_error`
- `external_last_synced_at` — generic replacement for `shopify_last_synced_at`

### Mapping policy

- Existing Shopify data is migrated into generic external fields via Alembic migration
- Shopify-specific columns remain only for transition and rollback
- New Medusa integrations write only the generic external fields
- `provider` on variants gains `"medusa"` as a valid value

### Theme draft models

`ShopifyThemeTemplateDraft` and `ShopifyThemeTemplateDraftVersion` should be renamed to generic `ThemeTemplateDraft` / `ThemeTemplateDraftVersion` when the storefront template system (Workstream 7) is built. These are MOS-owned authoring artifacts, not Shopify artifacts.

## Workstream 3: Medusa Application Standardization

## Objective

Define one standard Medusa app layout that every workspace/store instance uses.

## Standard Medusa app composition

- Medusa server instance
- Medusa worker instance
- PostgreSQL database
- Redis
- Marketi Medusa plugin

Medusa's production docs recommend PostgreSQL + Redis and separate server/worker deployments, with `shared` mode as the default and `server` / `worker` modes for production separation. Sources:

- [General deployment guide](https://docs.medusajs.com/learn/deployment/general)
- [Worker mode](https://docs.medusajs.com/learn/production/worker-mode)

## Standard Medusa configuration policy

- one Postgres database per workspace/store
- one Redis cluster shared across many store apps
- one plugin package installed everywhere
- one deployment template everywhere
- one observability/alerting package everywhere

## Workstream 4: Catalog And Commerce Data Migration

## Objective

Move product, variant, price, and inventory data off Shopify and into Medusa without interrupting storefront experiments.

## Migration source of truth

For initial migration:

- Shopify is source of truth for live commerce data
- MOS is source of truth for:
  - marketing copy context
  - offer positioning
  - page structure
  - design system
  - imported assets

## Migration tasks

### 1. Product import

Import from Shopify into Medusa:

- products
- handles
- descriptions
- tags
- categories/collections where applicable
- variants
- option values
- SKUs/barcodes
- compare-at prices
- inventory quantities
- images/media references

### 2. MOS cross-linking

For each migrated product:

- create or update MOS product cross-reference
- set `Product.commerce_provider = "medusa"`
- set `Product.external_product_id` to Medusa product ID
- set `ProductVariant.provider = "medusa"`
- set `ProductVariant.external_price_id` to Medusa variant ID
- set `ProductVariant.external_variant_id` to Medusa variant ID

### 3. Promotion recreation

Recreate current offer mechanics in Medusa using:

- price sets
- promotion rules
- bundle logic where needed
- custom workflows for Marketi-specific upsell sequencing

### 4. Historical orders

Do not make full historical-order migration a phase-1 dependency unless finance or support explicitly require it.

Recommended approach:

- keep Shopify read-only for historical support lookup
- migrate only the minimum needed order data into MOS for attribution continuity
- migrate historical commerce records later if required

## Workstream 5: Checkout, Cart, Payment Providers, And Order Attribution

## Objective

Rebuild the purchase flow so it supports multiple payment providers through Medusa, fits the MOS public runtime, and preserves the attribution model.

## Current state

- **Stripe**: fully integrated. `public_funnels.py` creates `stripe.checkout.Session` directly. Webhook at `stripe_webhooks.py` records `FunnelOrder` with `stripe_session_id` and `stripe_payment_intent_id`.
- **Shopify**: fully integrated via bridge. `shopify_checkout.py` calls `shopify-funnel-app` which calls Storefront API `cartCreate`. Shopify hosts its own checkout with its configured payment providers. Order webhook flows back through `shopify_webhooks.py`.
- **PayPal**: display-only. `PaymentIconStrip.tsx` shows the PayPal logo. No backend integration.
- **Apple Pay / Google Pay**: display-only. Icons in `PaymentIconStrip.tsx`. No backend integration.

The checkout dispatch in `public_funnels.py` branches on `variant.provider` (`"stripe"` or `"shopify"`). The `FunnelOrder` model stores Stripe session IDs and reuses the same field for Shopify with a `shopify:{domain}:{ref}` format.

## Target flow

1. MOS public page resolves product/variant/offer state.
2. MOS calls Medusa Store API to create a cart with line items + attribution metadata.
3. Medusa resolves payment providers available for the store's region/config.
4. Customer completes payment through Medusa's checkout (Stripe, PayPal, Apple Pay, Google Pay — whatever is configured).
5. Medusa processes order completion internally.
6. Marketi Medusa plugin emits a normalized order-complete webhook to MOS.
7. MOS records:
   - `FunnelOrder` with status "completed"
   - `FunnelEvent` with event type "order_completed"
   - funnel, page, variant, offer attribution
   - visitor/session metadata
8. MOS fires ad platform conversion events (Meta CAPI, TikTok, future platforms).

## Payment provider strategy

### Why Medusa owns payment providers

Today, payment provider selection is split awkwardly:

- Stripe variants bypass Shopify entirely — MOS talks to Stripe directly
- Shopify variants delegate everything to Shopify's checkout, which handles payment method selection internally
- PayPal and wallets are not supported at all

With Medusa, payment provider orchestration is centralized:

- Medusa's Payment Module supports pluggable payment providers
- Stripe, PayPal, and manual payment providers are available as Medusa payment provider plugins
- Apple Pay and Google Pay work through Stripe's Payment Element (no separate integration needed)
- Each store configures which providers are active per region
- MOS never touches card data or payment provider APIs directly

Source: [Medusa Payment Module](https://docs.medusajs.com/resources/commerce-modules/payment), [Stripe Payment Provider](https://docs.medusajs.com/resources/commerce-modules/payment/payment-provider/stripe)

### Required payment providers

**Phase 1 (launch):**
- Stripe (cards, Apple Pay, Google Pay via Stripe Payment Element)
- This matches current Stripe capability and adds wallet support for free

**Phase 2 (expand):**
- PayPal (via Medusa PayPal provider plugin or custom provider)
- Klarna / Afterpay (if relevant for workspace verticals)

**Not in scope:**
- Cryptocurrency
- Direct bank transfers
- Manual/offline payments

### Payment provider configuration model

Each Medusa store instance configures:

- Active payment providers (Stripe always, PayPal optional)
- Provider credentials (Stripe secret key, PayPal client ID/secret)
- Region-provider mapping (which providers are available in which regions)
- Currency settings per region

The Marketi Medusa plugin should enforce:

- Stripe is always configured (default provider)
- Apple Pay / Google Pay are enabled automatically when Stripe is active (via Payment Element)
- PayPal is opt-in per workspace

### Checkout UX model

With Medusa handling payment orchestration, the checkout experience changes:

**Current (Stripe variant):** MOS → redirect to Stripe Checkout hosted page → return to success URL
**Current (Shopify variant):** MOS → redirect to Shopify checkout → Shopify handles payment method selection

**Target (Medusa):** Two viable approaches:

1. **Medusa-hosted checkout page** — Medusa provides a checkout page (or we build a lightweight one) that shows available payment methods. MOS redirects to it. Simplest to implement.

2. **Embedded checkout in MOS** — MOS renders the checkout form using Stripe Payment Element (or equivalent) with Medusa as the backend for cart/order state. Better UX but more frontend work.

Recommended: Start with option 1 (redirect), migrate to option 2 for workspaces that need it.

### Impact on FunnelOrder model

The `FunnelOrder` model currently stores:

- `stripe_session_id` (reused for Shopify as `shopify:{domain}:{ref}`)
- `stripe_payment_intent_id`

These need to become:

- `external_order_id` — Medusa order ID
- `external_payment_id` — payment session/intent ID from whichever provider completed the payment
- `payment_provider` — `"stripe"`, `"paypal"`, `"apple_pay"`, etc. (which provider actually processed the payment)
- Keep `stripe_session_id` and `stripe_payment_intent_id` during migration for backward compatibility

## Metadata strategy

Carry MOS attribution metadata through Medusa cart/order metadata:

- `funnel_id`
- `publication_id`
- `page_id`
- `offer_id`
- `variant_id`
- `visitor_id`
- `session_id`
- `selection`
- `utm`
- `quantity`

This mirrors what today is stored in Shopify note attributes and Stripe metadata, but moves it into Medusa's cart/order metadata system.

## Conversion event forwarding

Today `shopify_webhooks.py` triggers Meta pixel events via `meta_conversions.py` on order completion. The Medusa path must replicate this:

- Marketi Medusa plugin emits order-complete event to MOS
- MOS webhook handler fires Meta/TikTok conversion events using the same attribution metadata
- Conversion event parity must be validated before any workspace cuts over

## Recommended Medusa customization

- Wrap or extend checkout/order-completion flows with a Marketi workflow
- Attach attribution metadata at add-to-cart / cart-completion time
- Emit normalized internal webhooks back to MOS (provider-agnostic order-complete event)
- Include GDPR compliance handlers (replacing `shopify-funnel-app` compliance webhooks)
- Configure Stripe Payment Element for Apple Pay / Google Pay support

## What we retire from MOS

Once Medusa handles checkout:

- `mos/backend/app/routers/stripe_webhooks.py` — Stripe webhook handling moves to Medusa
- Direct `stripe.checkout.Session.create()` calls in `public_funnels.py` — replaced by Medusa cart/checkout API
- `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` move from MOS config to Medusa config
- MOS no longer needs to know about individual payment providers; it only talks to Medusa

## Workstream 6: Admin And Operator Workflows

## Objective

Make sure operators can still manage store operations without dropping into multiple systems for simple tasks.

## Recommended responsibility split

### In MOS

- template selection
- page authoring
- design systems
- imported reference-site review
- experiment variant creation
- product positioning and offer framing
- testimonial and social-proof curation

### In Medusa Admin

- canonical product data
- pricing records
- stock levels
- fulfillment/shipping setup
- discount and promotion operations
- order operations
- payment provider configuration (Stripe keys, PayPal credentials, region settings)

### Custom Medusa admin additions

Use Admin Extensions for:

- MOS workspace linkage widget
- attribution visibility widget
- "open in MOS" links
- custom promotion helpers for Marketi offer logic
- payment provider setup wizard (guided Stripe + PayPal configuration)

Source: [Medusa Admin customizations](https://docs.medusajs.com/learn/customization/customize-admin), [Medusa UI / Admin Extensions](https://docs.medusajs.com/ui/installation/medusa-admin-extension)

### Frontend migration

The current Commerce page (`CommercePage.tsx` + `ShopifyTab.tsx`) and its components (`ShopifyConnectionCard`, `ShopifyAppCredentialsCard`, `ThemeTemplateWorkflowCard`, `CompliancePolicyCard`) need to become provider-aware:

- Connection card shows Medusa or Shopify status depending on workspace provider
- Product operations route through the provider abstraction
- Theme template workflows move to the generic storefront template system (Workstream 7)

## Workstream 7: Templating, Styling, And Storefront Runtime

## Goal

Turn the current funnel-template system into a full storefront-template system.

## Current state baseline

The template system today is narrow:

- **2 templates**: `pre_sales_listicle` and `sales_pdp`, both clones of a single brand (PuppyPad)
- **34 Puck blocks**: 7 generic (Section, Columns, Spacer, Heading, Text, Button, Image) + 10 PreSales-specific + 14 SalesPdp-specific + 3 content blocks (FeatureGrid, Testimonials, FAQ)
- **5 page stages**: `pre_sales`, `sales`, `checkout`, `thank_you`, `custom` — inferred from slug, not stored
- **~300 CSS variables** in `base_tokens.json` — heavily weighted toward funnel aesthetics (listicle, PDP, marquee, reviews)
- **No cross-template block reuse** — PreSalesHero and SalesPdpHero are separate components that cannot compose across families
- **No storefront page types** — no home, collection, product listing, or account pages
- **No commerce data binding** — templates are static content with optional product/offer links, not live commerce data

This is the largest workstream. The existing system is a funnel builder, not a storefront builder.

## Core model

Templates should be layered into:

1. template family
2. template variant
3. design system
4. page instance
5. commerce bindings

### Page types to support

- home
- PDP
- collection
- cart/checkout-adjacent pages
- policy pages
- advertorial/pre-sell
- launch/seasonal pages

### Required block library evolution

The current 34 blocks need to evolve into a two-tier system:

**Tier 1: Generic blocks** (usable across all template families)
- Hero, ProofBar, FeatureStack, ComparisonTable, ReviewWall, FAQ, StickyOfferRail, Footer, CollectionGrid, BundleSelector, ProductCarousel, AddToCartForm, VariantSelector, Breadcrumb, NavigationHeader
- These replace the current template-specific duplicates (PreSalesHero, SalesPdpHero → Hero)

**Tier 2: Template-family presets** (visual configuration on top of generic blocks)
- `sales-pdp/bold-proof` configures Hero + ReviewWall + ComparisonTable with specific prop defaults
- `listicle-presell/founder-led` configures Hero + FeatureStack + StickyOfferRail with different defaults

This deduplicates the current component tree and enables cross-template composition.

## Important rule

There should be **one page/template engine**, not:

- one for funnels
- one for "real storefront pages"
- one for imported themes

Everything should use the same structured block system.

## Styling model

Use the current token-driven pattern as the foundation:

- canonical base token schema
- template defaults
- workspace-level design-system overrides
- optional page-level overrides

No uncontrolled CSS editing should be part of the main operator path.

### Style layers

1. **Base token schema**
   - from `base_tokens.json`

2. **Template family defaults**
   - visual assumptions needed to keep each family coherent

3. **Workspace design system**
   - brand colors, typography, CTA treatment, surfaces, accents

4. **Page-local override layer**
   - small scoped changes for a specific test variant

### Token schema expansion needed

The current token schema is funnel-focused. For storefront support, add tokens for:

- Product grid layout (card spacing, image ratio, price typography)
- Variant selector (swatch size, selected state, disabled state)
- Collection filters (sidebar width, chip style, active state)
- Checkout form (input style, step indicator, summary panel)
- Navigation (menu depth, mobile drawer, logo placement)

### Safety gates

Before publish:

- token schema validation
- contrast audit
- accent-density checks
- template slot completeness
- Medusa binding validation (product exists, variant has price, inventory check)

The existing design-system audit model should be expanded, not replaced.

## Storefront runtime choice

MOS should continue to render storefront pages.

Medusa's official docs explicitly state the storefront is installed and hosted separately from the Medusa application, and teams can use the frontend stack and UX of their choice. Source: [Next.js Starter Storefront](https://docs.medusajs.com/resources/nextjs-starter).

Therefore:

- Medusa starter storefront should be treated as reference material and integration sample code
- MOS runtime remains the production storefront/page system

## Workstream 8: Reference Site Import System

## Goal

Import strong websites rapidly, but convert them into Marketi-native template families and blocks.

## Import philosophy

Do **not** store imported sites as raw HTML/CSS templates.

Instead, import them as:

- theme/style candidates
- structural section patterns
- reusable blocks
- synthesized template variants

## Import modes

### 1. Theme extraction

Extract:

- palette
- fonts
- spacing density
- border/radius/shadow language
- CTA treatment
- section contrast pattern

Output:

- design-system candidate
- import notes

### 2. Pattern extraction

Extract:

- section structure
- content hierarchy
- visual composition
- proof/CTA rhythms

Output:

- reusable block or block composition candidates

### 3. Template synthesis

Convert one or more imported pages into:

- Marketi template family or variant
- `puckData` structure
- style preset
- asset set
- provenance record

## Import pipeline

### Step 1: Capture bundle

Create a backend import worker that uses Playwright to capture:

- desktop screenshots
- mobile screenshots
- HTML snapshot
- DOM tree
- computed styles
- section boundaries
- image URLs
- CTA positions
- nav/footer structure

Output:

- `SiteImportBundle`

### Step 2: Normalize into canonical sections

Parse the capture into typed sections:

- hero
- proof bar
- feature stack
- comparison table
- review wall
- FAQ
- sticky offer rail
- footer
- collection grid
- bundle selector

Each section should store:

- section type guess
- DOM subset
- screenshot crop
- key text
- key media
- style signature
- confidence score

### Step 3: Match to existing block library

Map the normalized sections into the existing Marketi component language.

Possible outcomes:

- exact block match
- partial block match with slot mapping
- no acceptable block exists

If there is no acceptable match, generate a **new block request**.
Do not fall back to persisting raw external markup as a first-class template.

### Step 4: Generate token candidate

Translate imported visual language into the canonical design-system token schema.

Then run:

- token validation
- design-system audit
- template compatibility checks

### Step 5: Asset ingestion and provenance

For every imported asset:

- store origin URL
- timestamp
- content hash
- workspace/import-job ownership
- reuse approval state

For any asset not allowed to remain:

- create replacement task
- regenerate or replace before production publish

### Step 6: Synthesize template variant

Build a structured Marketi template variant containing:

- block order
- default props
- slot placeholders
- style preset
- imported approved assets
- commerce binding definitions
- provenance metadata

### Step 7: Human review

Provide review UI showing:

- source screenshots
- rendered MOS preview
- block coverage result
- token diff
- missing slot list
- commerce binding status

### Step 8: Variant generation

Once the template exists, generate fast derivatives:

- alternate hero emphasis
- alternate proof density
- alternate CTA treatments
- alternate media ordering
- alternate offer layouts
- alternate review wall depth

That is how we import once and iterate many times.

## Workstream 9: Policy Pages, Reviews, And Other Store Content

### Policy pages

Keep policy generation in MOS.

Recommended approach:

- publish policy pages as structured pages in the storefront template system
- optionally mirror metadata to Medusa if needed for admin visibility
- do not recreate Shopify page-sync as the primary model
- `compliance.py` router and service continue to generate policies; the sync target changes from Shopify to Medusa (or becomes publish-only if policies are rendered by MOS)

### Reviews and testimonial assets

Keep review media and testimonial rendering in MOS.

Treat them as reusable block inputs:

- review card
- UGC strip
- before/after wall
- social proof cluster

### Navigation and collections

- Medusa provides collection/product data
- MOS controls how collection and nav pages are presented

## Workstream 10: Ad Platform, Analytics, And Telemetry Integration

## Objective

Ensure all ad platform conversion events, analytics tracking, and observability work end-to-end through Medusa-backed commerce without any attribution loss.

## Current state

### Meta integration (most mature)

**Server-side (CAPI):**
- `meta_conversions.py` sends Purchase events to Meta Conversions API on Shopify order completion
- Includes hashed PII (email, phone, external_id), order value, currency, content IDs
- Pixel ID resolved from `PaidAdsPlatformProfile` with `mosMetaTracking` metadata
- Response stored in `FunnelOrder.checkout_metadata.meta_conversion`

**Client-side (pixel):**
- `metaPixel.ts` lazy-loads `fbevents.js` and initializes pixel via `fbq("init", pixelId)`
- `metaFunnelEvents.ts` maps runtime events to Meta pixel events:
  - `"Entered Funnel"` → custom event
  - `pre_sales_page_view` → `PageView`
  - `sales_page_view` → `PageView` + `ViewContent`
  - `sales_to_checkout_click` → `AddToCart`
  - `checkout_started` → tracked server-side
  - `order_completed` → `Purchase` (fired client-side from sessionStorage on thank-you page + server-side via CAPI)

**Meta Ads management:**
- `meta_ads.py` router (~1000 lines): campaign creation, ad set management, creative upload, publish orchestration
- Validation framework for compliance ruleset (v1, v2)
- Workspace configuration, connection status, usage tracking
- `configure_generated_funnels_meta_tracking_activity` in Temporal wires up pixel tracking during funnel generation

### Funnel event tracking (14 event types)

- `page_view`, `cta_click` (legacy)
- `"Entered Funnel"`, `funnel_exit`
- `pre_sales_page_view`, `sales_page_view`, `checkout_page_view`, `thank_you_page_view`, `custom_page_view`
- `pre_sales_to_sales_click`, `sales_to_checkout_click`, `custom_page_click`
- `checkout_started`, `order_completed`

All recorded in `funnel_events` table with: visitor_id, session_id, utm, props, publication context.

### Session and attribution tracking

- `visitor_id`: generated client-side, stored in localStorage
- `session_id`: passed through checkout metadata
- Click ID detection: `fbclid`, `gclid`, `ttclid`, `msclkid`, `twclid`, `li_fat_id`
- UTM parameters extracted from URL

### What doesn't exist yet

- TikTok Conversions API (ttclid detected but no server-side event forwarding)
- Google Analytics 4 / GTM integration
- Google Ads conversion tracking (gclid detected but not forwarded)
- OpenTelemetry platform telemetry (spec exists in `mos-telemetry-spec.md`, not deployed)

## What changes for Medusa

### Meta CAPI migration

`meta_conversions.py` currently accepts `ShopifyOrderWebhookPayload`. It needs to become provider-agnostic:

- Accept a normalized `OrderCompletionEvent` regardless of source (Shopify, Medusa, Stripe direct)
- Extract the same attribution metadata from Medusa order metadata as it does from Shopify note attributes
- Hashed PII (email, phone) must be carried through Medusa's customer/order data
- The pixel resolution logic (`resolve_active_meta_pixel_tracking`) stays unchanged — it operates on MOS workspace config, not payment provider

### Meta pixel client-side changes

No changes needed. The pixel fires on page events and checkout initiation, which happen in the MOS frontend regardless of commerce backend. The only change is that the thank-you page `Purchase` event needs to read order data from the Medusa-backed order completion, not from Shopify/Stripe session data.

### Attribution metadata contract

Define a canonical `OrderCompletionEvent` schema that all commerce providers must produce:

```
OrderCompletionEvent:
  source_provider: "medusa" | "shopify" | "stripe"
  external_order_id: string
  external_payment_id: string
  payment_provider: "stripe" | "paypal" | "apple_pay" | "google_pay"
  amount_cents: int
  currency: string
  customer_email: string (for CAPI hashing)
  customer_phone: string | null
  line_items: [{variant_id, quantity, unit_price}]
  attribution:
    funnel_id, publication_id, page_id, offer_id, variant_id
    visitor_id, session_id
    utm: {source, medium, campaign, term, content}
    click_ids: {fbclid, gclid, ttclid, ...}
  ip_address: string (for CAPI)
  user_agent: string (for CAPI)
```

### TikTok Conversions API

Add server-side TikTok event forwarding following the same pattern as Meta CAPI:

- New service: `tiktok_conversions.py`
- Fires on `OrderCompletionEvent` when workspace has active TikTok pixel
- Sends `CompletePayment` event with hashed PII, order value, content IDs
- Uses `ttclid` from attribution click_ids for matching

### Google Ads / GA4

Lower priority than Meta and TikTok. When needed:

- Google Ads offline conversion import via API (uses `gclid`)
- GA4 Measurement Protocol for server-side events
- GTM container loading in public funnel runtime (simple script injection, low effort)

### Telemetry and observability

Per `mos-telemetry-spec.md`, the target stack is:

- OpenTelemetry traces via Grafana Alloy collector
- Grafana Tempo for trace storage
- Grafana Loki for structured logs
- Prometheus for metrics (Mimir for scale-out)
- Langfuse for LLM-specific observability (already deployed)

For Medusa specifically:

- Medusa app instances should emit traces/metrics to the same OTel collector
- Marketi Medusa plugin should produce structured logs for order events, payment completions, inventory changes
- MOS webhook handler for Medusa events should create trace spans linked to the originating cart/checkout trace
- Medusa admin operations should be observable through the same Grafana dashboards

This is not a blocker for Medusa launch but should be wired in during Phase 2-3 to avoid debugging in the dark.

## Workstream 11: Deployment, Compute, And Cost Control

## Objective

Run 10-20 workspaces economically without giving every workspace a full dedicated VM stack unless it actually needs it.

## Current deployment architecture

### MOS platform

- **Backend**: Docker image (`mos-backend`) built via GitHub Actions, pushed to GHCR, deployed via `docker-compose.deploy.yml` with SSH
- **Worker**: Same image, different CMD (`python -m app.temporal.worker`)
- **Frontend**: Docker image (`mos-frontend`) with Vite build baked in, served by nginx
- **Self-deploy**: CI triggers `self-deploy.moshq.app/api/applications/plans/apply` via Cloudhand API
- **Database**: PostgreSQL 16 (separate from MOS containers)
- **Temporal**: Self-hosted server + PostgreSQL backend + Temporal UI

### Funnel/storefront publishing

- **Cloudhand**: Custom Terraform-generation and deployment orchestration system (`mos/backend/cloudhand/`)
  - `ApplicationSpec` describes apps with runtime type (docker, nodejs, python, static, go)
  - Source types include `funnel_publication` and `funnel_artifact`
  - `deploy.py` handles Terraform plan/apply, artifact embedding, CDN integration
  - `terraform_gen.py` generates Terraform from specs
- **CDN**: Bunny CDN for published funnel assets
- **DNS**: Namecheap API for domain provisioning
- **Media storage**: S3-compatible (configured via `MEDIA_STORAGE_*` env vars)

### Shopify bridge

- `shopify-funnel-app/`: standalone FastAPI service on port 8011
- SQLite database for installation records
- Deployed separately (not part of main Docker Compose)

### ops/home-site (existing Hetzner pattern)

- Terraform for Hetzner Cloud CX23 provisioning
- systemd services, nginx reverse proxy, Let's Encrypt via Certbot
- Deployed via Terraform remote provisioners (SSH)

## What needs to exist for Medusa

### Per-workspace Medusa instance

Each workspace gets:

- Medusa server process (Node.js)
- Medusa worker process (Node.js)
- Dedicated PostgreSQL database (on shared Postgres host)
- Shared Redis connection
- Marketi Medusa plugin installed
- Admin UI accessible at `{workspace}.admin.moshq.app` or similar

### Medusa deployment artifacts

Build and maintain:

- `packages/marketi-medusa-plugin/` — the reusable plugin package
- `packages/medusa-app/` — base Medusa app with plugin pre-installed, standard config
- Docker image for Medusa app (server + worker modes, like MOS backend)
- GitHub Actions workflow to build and push Medusa image to GHCR

### Infrastructure provisioning

Extend Cloudhand to support Medusa workspace provisioning:

- New `ApplicationSpec` source type: `medusa_workspace`
- Terraform template that provisions:
  - Database on shared Postgres host (`CREATE DATABASE workspace_{id}`)
  - Medusa server process (Docker container or systemd service)
  - Medusa worker process
  - nginx virtual host with SSL
  - DNS record for admin subdomain
- Provisioning triggered by MOS backend when workspace enables commerce (see Workstream 13)

### Or: extend the ops/ pattern directly

Alternative to Cloudhand integration:

- `ops/medusa/terraform/main.tf` — shared Medusa infrastructure (app nodes, Postgres, Redis)
- `ops/medusa/scripts/provision-workspace.sh` — creates DB, configures Medusa instance, deploys plugin
- `ops/medusa/scripts/deploy-update.sh` — rolling update of Medusa image across instances
- systemd service templates per workspace instance

Either approach works. Cloudhand is more automated; ops/ scripts are simpler to start with.

## Recommended infrastructure model

Use **pooled single-tenant apps**:

- one Medusa app per workspace/store
- shared app nodes
- shared Redis
- shared Postgres host or cluster
- database-per-workspace
- promote only heavy workspaces to dedicated resources

## Recommended tiers

### Tier 1: Shared pool

- low-volume workspace
- Medusa app runs on shared app nodes
- DB is isolated per workspace
- worker can run in shared mode or a pooled worker group

### Tier 2: Split mode on shared pool

- workspace has meaningful order volume or heavier background jobs
- Medusa app still on shared node pool
- dedicated worker process for that workspace

### Tier 3: Dedicated tenant

- high-volume or high-risk workspace
- dedicated server + worker resources
- same plugin package and deployment template

## Hetzner example sizing

As checked on March 12, 2026, Hetzner's cloud page currently shows example EU shared plans such as:

- `CX23`: 2 vCPU / 4 GB / 40 GB at about `€3.49/mo`
- `CX33`: 4 vCPU / 8 GB / 80 GB at about `€5.49/mo`
- `CX43`: 8 vCPU / 16 GB / 160 GB at about `€9.49/mo`

Source: [Hetzner Cloud pricing](https://www.hetzner.com/cloud)

For the first 10-20 workspaces, a sensible starting point is:

- 2 shared app nodes (CX33 or CX43)
- 1 shared Postgres server (CX33 minimum, managed preferred)
- 1 shared Redis instance
- Reuse existing Hetzner account and Terraform patterns from `ops/home-site`

## CI/CD integration

Add to the existing GitHub Actions pipeline (`.github/workflows/docker-images.yml`):

- Build Medusa Docker image (Node.js base)
- Push to GHCR alongside `mos-backend` and `mos-frontend`
- Optional deploy job (SSH to shared app nodes, pull new image, restart workspace services)
- Or: trigger via Cloudhand API (same pattern as `self-deploy.yml`)

## Workstream 12: Agentic Commerce Provisioning

## Objective

When a workspace completes onboarding, MOS should automatically provision and configure the Medusa commerce backend — including store creation, payment provider setup, product sync, and checkout readiness — without manual operator intervention.

## Current onboarding flow

Today, onboarding is a 5-step wizard → Temporal workflow chain:

1. **OnboardingWizard** collects: brand story, product details, business model, target platforms/regions, brand voice, compliance notes
2. `POST /clients/{client_id}/onboarding` creates: Product, ProductOffer, ProductVariant, OnboardingPayload
3. **ClientOnboardingWorkflow** starts → spawns **StrategyV2Workflow** as child
4. Strategy V2 runs agent pipeline (6 AI agents, 6 human gates):
   - Agent 0: habitat strategist
   - Agent 0B: social video strategist
   - Agent 1: habitat qualifier
   - Agent 3: angle synthesis
   - Copy pipeline, offer pipeline
5. **CampaignIntentWorkflow** creates campaigns
6. **CampaignFunnelGenerationWorkflow** generates funnel pages with AI, configures Meta tracking

**What is manual today:**
- Shopify connection (user provides API credentials, initiates OAuth)
- Storefront token provisioning
- Product creation in Shopify (user triggers from ProductDetailPage)
- Policy page sync to Shopify
- Payment provider configuration (happens inside Shopify admin, outside MOS)

## Target: commerce provisioning as part of the onboarding workflow

### New Temporal activity: `provision_workspace_commerce_activity`

Add to the onboarding workflow chain, after Strategy V2 produces initial research artifacts and design system:

**Input:**
- `org_id`, `client_id`
- `product_id` (created during onboarding)
- `target_regions` (from onboarding wizard)
- `business_model` (from onboarding wizard)

**Steps:**

1. **Create Medusa store instance**
   - Call provisioning API/script to create workspace database
   - Deploy Medusa app instance with Marketi plugin
   - Configure store settings (name, default region, currency)
   - Record Medusa store URL and admin URL in MOS workspace config

2. **Configure payment providers**
   - Enable Stripe as default provider (using workspace or platform Stripe keys)
   - Configure region-currency mappings based on `target_regions`
   - Optionally enable PayPal if workspace config requests it
   - Apple Pay / Google Pay enabled automatically via Stripe Payment Element

3. **Sync initial product catalog**
   - Create product in Medusa from MOS product record
   - Create variants with pricing from MOS variant records
   - Set inventory policy (track vs. don't track)
   - Upload product images from MOS asset storage

4. **Configure sales channel**
   - Create Medusa sales channel linked to MOS workspace
   - Assign products to sales channel

5. **Validate checkout readiness**
   - Test cart creation with a test variant
   - Validate payment provider configuration
   - Confirm webhook endpoint is reachable
   - Record readiness status in MOS workspace

**Output:**
- `medusa_store_url`
- `medusa_admin_url`
- `commerce_readiness_status` (ready, partial, failed)
- `payment_providers_configured` (list)
- Any errors or warnings

### Integration with existing workflow chain

```
OnboardingWizard submission
  → ClientOnboardingWorkflow
    → StrategyV2Workflow (research, angles, copy, offers)
    → provision_workspace_commerce_activity  ← NEW
    → CampaignIntentWorkflow (campaigns)
    → CampaignFunnelGenerationWorkflow (funnel pages)
      → configure_generated_funnels_meta_tracking_activity (existing)
      → configure_funnel_commerce_bindings_activity  ← NEW
```

### New Temporal activity: `configure_funnel_commerce_bindings_activity`

After funnel pages are generated, bind them to the Medusa store:

- Resolve product/variant IDs to Medusa IDs
- Set `variant.provider = "medusa"` and `variant.external_price_id` to Medusa variant ID
- Validate that all commerce bindings resolve (product exists, variant has price, payment configured)
- Record binding status per funnel page

### Human gates

Commerce provisioning should **not** require a human gate for basic setup. The wizard already collected the necessary inputs (product, pricing, regions).

Add a human gate only for:

- Payment provider credential entry (if workspace-specific Stripe keys are needed instead of platform keys)
- PayPal enablement (opt-in)
- Custom region/currency configuration beyond what the wizard captured

### Frontend: commerce readiness indicator

Add to the workspace dashboard:

- Commerce status badge (provisioning, ready, error)
- Payment providers configured (Stripe, PayPal, Apple Pay, Google Pay)
- Checkout test result
- "Configure payment" action for manual credential entry if needed
- Link to Medusa admin for advanced configuration

### Existing manual flows that become automated

| Action | Today | After |
| --- | --- | --- |
| Commerce backend provisioning | Manual Shopify OAuth + credential entry | Automatic in onboarding workflow |
| Product creation in commerce backend | Manual from ProductDetailPage | Automatic during onboarding |
| Payment provider setup | Manual in Shopify admin | Automatic (Stripe), opt-in (PayPal) |
| Storefront token provisioning | Semi-automatic via shopify-funnel-app | Not needed (MOS talks to Medusa directly) |
| Policy page sync | Manual trigger from compliance page | Automatic during funnel generation |
| Meta tracking config | Automatic via Temporal activity | Stays automatic (no change) |
| Checkout readiness validation | Manual testing | Automatic validation in provisioning |

## Workstream 13: Migration Phasing

## Phase 0: Foundation

- Finalize target architecture
- Define generic commerce provider interface in MOS (`commerce_provider.py`)
- Define Marketi Medusa plugin shape
- Define `OrderCompletionEvent` schema for provider-agnostic conversion events
- Add generic external commerce fields to MOS schema (Alembic migration)
- Backfill existing Shopify data into generic fields

## Phase 1: Medusa platform bootstrap

- Create base Medusa app in `packages/medusa-app/`
- Create Marketi plugin in `packages/marketi-medusa-plugin/`
- Wire PostgreSQL + Redis
- Configure Stripe payment provider in Medusa
- Set up server/worker deployment template (extend `ops/home-site` or Cloudhand patterns)
- Add basic admin customizations (MOS workspace link widget)
- Build Medusa Docker image and add to CI pipeline

## Phase 2: MOS provider abstraction + ad platform generalization

- Wrap existing Shopify services into `ShopifyProvider` class
- Implement `MedusaProvider` class
- Route catalog operations through the provider layer
- Update `clients.py` and `products.py` routers to use provider abstraction
- Update Temporal activities (`campaign_intent_activities.py`, `strategy_v2_activities.py`) to use provider layer
- Generalize `meta_conversions.py` to accept `OrderCompletionEvent` instead of `ShopifyOrderWebhookPayload`
- Wire OTel basics into Medusa instances

## Phase 3: Catalog migration + payment providers

- Import products/variants/pricing/inventory from Shopify into Medusa
- Map MOS products to Medusa IDs (update `external_product_id`, `external_variant_id`)
- Recreate promotions and bundle rules
- Validate catalog parity between Shopify and Medusa
- Configure PayPal provider in Medusa (for workspaces that need it)
- Validate Apple Pay / Google Pay work via Stripe Payment Element

## Phase 4: Checkout, conversion, and attribution migration

- Implement Medusa cart/checkout integration in MOS runtime (add `"medusa"` branch to checkout dispatch)
- Add order-completion webhook handler for Medusa events
- Preserve attribution metadata end to end through Medusa cart/order metadata
- Wire Meta CAPI through Medusa order path using `OrderCompletionEvent`
- Implement TikTok Conversions API forwarding
- Validate conversion event parity: dual-run Shopify and Medusa, compare event volumes
- Validate all payment providers work end-to-end (Stripe, PayPal, Apple Pay, Google Pay)

## Phase 5: Agentic provisioning

- Implement `provision_workspace_commerce_activity` Temporal activity
- Implement `configure_funnel_commerce_bindings_activity` Temporal activity
- Integrate into ClientOnboardingWorkflow chain
- Add commerce readiness indicator to workspace dashboard
- Add payment provider configuration UI for manual overrides
- Deploy workspace provisioning scripts (Cloudhand or ops/ pattern)

## Phase 6: Storefront template generalization

- Deduplicate template-specific blocks into generic block library
- Add page type enum (stored, not inferred from slug)
- Add page types beyond pre-sell/PDP: home, collection, policy
- Add commerce bindings to blocks
- Expand token schema for storefront page types
- Rename `ShopifyThemeTemplateDraft` models to generic names

## Phase 7: Reference import MVP

- Capture bundle worker
- Section normalization
- Token extraction
- Block matching
- Reviewer workflow

## Phase 8: Controlled cutover

- Dual-run Shopify and Medusa for selected workspaces
- Move workspaces to Medusa one at a time
- Validate per-workspace checklist:
  - Checkout works with all configured payment providers
  - Orders record in MOS with correct attribution
  - Meta CAPI Purchase events fire with correct values
  - TikTok conversion events fire (if configured)
  - Inventory updates reflect in Medusa
  - Agentic provisioning works for new workspaces
- Freeze Shopify catalog changes before final cutover per workspace
- Keep Shopify read-only for historical lookup

## Phase 9: Retirement

- Remove `shopify-funnel-app/` (28 files)
- Remove all Shopify-specific backend services (6 files)
- Remove Shopify-specific router endpoints from `clients.py`, `products.py`, `compliance.py`
- Remove Shopify-specific schemas (`shopify.py`, `shopify_connection.py` — ~55 classes)
- Remove frontend Shopify components (12+ files: ShopifyTab, ShopifyConnectionCard, ShopifyAppCredentialsCard, hooks, utils)
- Remove Shopify-specific DB models (`ClientShopifyAppCredential`, renamed theme draft models)
- Drop Shopify-specific columns (`shopify_product_gid`, `shopify_last_synced_at`, `shopify_last_sync_error`) after rollback window closes
- Remove 8 Shopify environment variables from config
- Remove direct Stripe integration from MOS (Stripe is now Medusa's concern)
- Remove `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` from MOS config

## Risks And Mitigations

### Risk: We accidentally rebuild a theme system outside MOS

Mitigation:

- keep MOS as the only primary template/page system
- use Medusa starter only as reference or integration sample

### Risk: Import pipeline becomes a raw HTML dumping ground

Mitigation:

- require imported pages to map into structured components or generate explicit new-block requests

### Risk: Per-tenant Medusa apps create ops sprawl

Mitigation:

- standardize one base app + one plugin + one deploy template
- keep infra pooled underneath
- extend existing `ops/home-site` Terraform patterns
- automate provisioning via Temporal activities

### Risk: Checkout attribution becomes weaker than today

Mitigation:

- define `OrderCompletionEvent` schema with required attribution fields before building the Medusa checkout path
- enforce it in Medusa workflows/subscribers
- validate conversion event parity (Meta, TikTok) before any workspace cuts over

### Risk: Commerce operators have to bounce between too many systems

Mitigation:

- keep MOS focused on storefront and experimentation
- extend Medusa admin only where operator handoff would otherwise be painful

### Risk: Ad platform conversion events break during migration

Mitigation:

- `meta_conversions.py` currently fires on Shopify order webhooks
- Medusa order-completion webhook handler must fire the same events via `OrderCompletionEvent`
- Run both paths in parallel during dual-run phase and compare event volumes
- Add alerting on conversion event volume drops

### Risk: Temporal workflows silently break on provider switch

Mitigation:

- `campaign_intent_activities.py` and `strategy_v2_activities.py` reference Shopify directly
- Phase 2 must update these before any workspace migrates
- Add provider-awareness tests to existing workflow test suites

### Risk: Template generalization scope creep delays commerce migration

Mitigation:

- Phase 6 (templates) is deliberately sequenced after Phase 5 (agentic provisioning)
- Medusa can go live for commerce operations while the template system is still funnel-shaped
- Template generalization is valuable but not a blocker for the commerce swap

### Risk: PCI compliance scope expands

Mitigation:

- Medusa + Stripe/PayPal handles card data, not MOS
- Validate that the payment flow keeps card data out of MOS and Medusa app code
- Use Medusa's payment module with provider plugins to maintain current PCI scope
- Apple Pay / Google Pay through Stripe Payment Element — no additional PCI scope

### Risk: Payment provider integration fails for specific methods

Mitigation:

- Stripe is the baseline — always works, includes Apple Pay/Google Pay via Payment Element
- PayPal is additive — test thoroughly before enabling for workspaces
- Never make PayPal a requirement for launch; it's an enhancement
- Each workspace can configure which providers are active

### Risk: Automated provisioning creates broken or half-configured stores

Mitigation:

- `provision_workspace_commerce_activity` runs validation at the end (test cart, test payment, test webhook)
- Commerce readiness status is visible on workspace dashboard
- Failed provisioning does not block the onboarding workflow — it records errors and allows manual intervention
- Provisioning is idempotent — can be retried

### Risk: Medusa workspace provisioning is too slow for onboarding UX

Mitigation:

- Provisioning runs as a Temporal activity (async, not blocking the wizard)
- User sees research and strategy results while commerce provisions in background
- Commerce readiness only matters when funnels are ready to publish
- Target provisioning time: under 5 minutes for basic setup

## Recommended First Implementation Slice

If we want the fastest path to a real result, build this first:

1. Generic commerce provider interface in MOS + `OrderCompletionEvent` schema
2. Base Medusa app + Marketi plugin + Stripe payment provider configured
3. Product + variant sync into Medusa
4. Medusa-backed checkout flow for one existing funnel page (Stripe only)
5. Normalized order completion back into MOS + Meta CAPI event
6. Basic workspace provisioning script (manual trigger, not yet in Temporal)
7. One workspace fully on Medusa, Shopify kept read-only

That gives us a working replacement path for commerce operations. Then layer on:

- PayPal + Apple Pay / Google Pay (Stripe Payment Element)
- TikTok Conversions API
- Automated provisioning in Temporal onboarding workflow
- Storefront template generalization

Storefront template work (home, collection, import pipeline) can proceed in parallel but should not gate the commerce cutover.

## Final Recommendation

The system we should build is:

- **commerce-backed by Medusa**
- **multi-payment-provider** (Stripe, PayPal, Apple Pay, Google Pay via Medusa)
- **storefront-authored by MOS**
- **template-driven**
- **token-governed**
- **import-assisted**
- **experiment-friendly**
- **conversion-event-complete** (Meta CAPI, TikTok, GA4 — all working before cutover)
- **automatically provisioned** (commerce setup integrated into onboarding workflow)
- **cost-controlled through pooled infrastructure**
- **observable** (OTel traces, Grafana dashboards, Langfuse for LLM ops)

The right mental model is:

> Medusa runs the store's commerce engine. MOS runs the store's presentation, templating, experimentation, and iteration engine. The onboarding workflow provisions both automatically.

That is the path that replaces Shopify without throwing away the strongest parts of the current Marketi stack.

## External References

- [Medusa documentation hub](https://docs.medusajs.com/)
- [Commerce Modules](https://docs.medusajs.com/resources/commerce-modules)
- [Product Module](https://docs.medusajs.com/resources/commerce-modules/product)
- [Payment Module](https://docs.medusajs.com/resources/commerce-modules/payment)
- [Stripe Payment Provider](https://docs.medusajs.com/resources/commerce-modules/payment/payment-provider/stripe)
- [Core Workflows Reference](https://docs.medusajs.com/resources/medusa-workflows-reference)
- [General deployment guide](https://docs.medusajs.com/learn/deployment/general)
- [Worker mode](https://docs.medusajs.com/learn/production/worker-mode)
- [Next.js Starter Storefront](https://docs.medusajs.com/resources/nextjs-starter)
- [Customize Medusa Admin](https://docs.medusajs.com/learn/customization/customize-admin)
- [Medusa Admin Extensions / Medusa UI](https://docs.medusajs.com/ui/installation/medusa-admin-extension)
- [Plugins](https://docs.medusajs.com/learn/fundamentals/plugins)
- [Re-use customizations with plugins](https://docs.medusajs.com/learn/customization/reuse-customizations)
- [Inventory Module in Flows](https://docs.medusajs.com/resources/commerce-modules/inventory/inventory-in-flows)
- [Get variant prices in storefront](https://docs.medusajs.com/resources/storefront-development/products/price)
- [Multi-region store recipe](https://docs.medusajs.com/v2/resources/recipes/multi-region-store)
- [Hetzner Cloud pricing](https://www.hetzner.com/cloud)
