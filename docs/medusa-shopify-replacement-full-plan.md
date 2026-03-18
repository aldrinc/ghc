# Medusa as Shopify Replacement: Full Integration, Storefront, Templating, and Migration Plan

## Purpose

This document is the single implementation brief for replacing Shopify with Medusa in Marketi.

It covers:

- the target system architecture
- how MOS and Medusa should split responsibilities
- what capabilities we gain after the swap
- how storefront templating, styling, and site import should work
- how to migrate from the current Shopify-dependent stack
- how to do this without blowing up compute costs

This plan is based on:

- the current codebase in this repository
- Medusa official documentation checked on March 12, 2026

## Executive Summary

The correct architecture is:

- **MOS remains the storefront authoring, rendering, experiment, design-system, import, preview, and deployment layer**
- **Medusa becomes the commerce backend**

That means:

- We do **not** replace MOS’s page/template runtime with a stock Medusa storefront.
- We do **not** rebuild the Shopify theme model inside Medusa.
- We do **not** clone websites as raw HTML and call them templates.

Instead, we:

1. Replace Shopify-specific commerce dependencies with a Medusa adapter layer.
2. Keep MOS as the place where pages, templates, design systems, testimonial blocks, and experiments are created.
3. Generalize the existing funnel/template system into a full storefront template system.
4. Add a robust import pipeline that turns strong reference sites into reusable Marketi template families.
5. Run Medusa economically using pooled infrastructure and a reusable Marketi plugin/customization package.

## What The Current System Actually Is

Today Shopify is not only checkout. It is woven into several different responsibilities.

### Shopify-dependent areas in the repo

- `shopify-funnel-app/`
  - OAuth install and installation records
  - Storefront token provisioning
  - catalog APIs
  - policy page sync
  - checkout creation
  - order and compliance webhooks

- `mos/backend/app/services/shopify_checkout.py`
  - converts a MOS checkout request into a Shopify cart/checkout bridge call

- `mos/backend/app/routers/public_funnels.py`
  - runtime checkout switching between Stripe and Shopify

- `mos/backend/app/routers/shopify_webhooks.py`
  - order ingestion and attribution into MOS

- `mos/backend/app/services/shopify_connection.py`
  - workspace connection status
  - product validation/listing/creation
  - variant updates
  - policy page sync
  - theme-brand workflows

- `mos/frontend/src/pages/workspaces/ProductDetailPage.tsx`
  - Shopify product mapping, create-in-Shopify flow, variant sync, and readiness checks

- `mos/frontend/src/pages/workspaces/BrandDesignSystemPage.tsx`
  - Shopify connection UX
  - theme template draft flows
  - audit/export flows

### What MOS already has that we should keep

- Puck-based structured page rendering and editing
- reusable templates stored as `puckData`
- design-system token generation and validation
- AI page editing that preserves template structure
- static/public funnel runtime
- publication/deployment primitives
- testimonial/review media rendering

This is the key insight:

> We are not replacing a simple Shopify checkout integration. We are replacing Shopify as the commerce operating system while preserving MOS as the marketing/storefront operating system.

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

Medusa’s docs currently describe a modular commerce backend with out-of-the-box Commerce Modules including Cart, Customer, Fulfillment, Inventory, Order, Payment, Pricing, Product, Promotion, Region, Sales Channel, Stock Location, Store, and Tax. Source: [Commerce Modules](https://docs.medusajs.com/resources/commerce-modules).

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
- operational boundaries match today’s “one client, one store” model
- workspace-specific admin customizations stay isolated
- one broken customization cannot poison every tenant

## Recommended Marketi Medusa Customization Package

Build a reusable package, for example:

- `packages/marketi-medusa-plugin`

This package should encapsulate reusable Medusa customizations across all stores.

Medusa’s docs state that plugins can package modules, workflows, API routes, admin extensions, and more, specifically as the reusable path across multiple Medusa applications. Sources: [Plugins](https://docs.medusajs.com/learn/fundamentals/plugins), [Re-use customizations with plugins](https://docs.medusajs.com/learn/customization/reuse-customizations).

### The plugin should contain

- custom module(s) for Marketi-specific storefront metadata
- workflow hooks for order attribution and post-purchase sync
- admin widgets/routes for Marketi-specific commerce operations
- API routes for MOS-triggered operations that are not covered cleanly by stock Admin APIs
- event subscribers for completed orders, inventory changes, and promotion updates

## What Capabilities We Gain After The Swap

## Commerce capabilities

Based on current Medusa docs, the practical gains include:

- richer catalog structure
  - products, options, variants, categories, collections, tags
- price rules and tiered pricing
  - useful for bundle pricing, offer ladders, and conditional merchandising
- inventory-aware cart validation
  - Medusa’s inventory docs show add-to-cart flows validating stocked quantity when inventory is managed
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

- Shopify-hosted checkout
- Shopify app ecosystem
- Shopify theme ecosystem
- built-in merchant familiarity with the Shopify admin

These are real losses, so the MOS authoring + Medusa operations experience must be materially better to justify the move.

## Non-negotiable Architecture Decisions

1. MOS remains the storefront authoring and rendering layer.
2. Medusa is the commerce backend, not the template editor.
3. The current funnel/template system becomes the general storefront template system.
4. Reference sites are imported into structured components and tokens, not persisted as raw HTML themes.
5. We build a reusable Marketi Medusa customization package once, then install it into each Medusa store.
6. We use pooled infrastructure with promotion to dedicated resources for heavy tenants.

## Workstream 1: Commerce Service Integration

## Objective

Replace the current Shopify-specific bridge and runtime calls with a provider-neutral commerce layer in MOS.

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

Implement providers:

- `shopify`
- `medusa`

This allows dual-running during migration instead of rewriting everything at once.

### 2. Replace direct Shopify runtime assumptions

Today `public_funnels.py` branches by `variant.provider` and directly handles `stripe` and `shopify`.

Change the runtime model so checkout resolution becomes:

- `provider = commerce`
- `commerceProvider = medusa | stripe`

For Medusa-backed products, MOS should call a Medusa checkout adapter instead of `shopify_checkout.py`.

### 3. Introduce a Medusa adapter in MOS

New backend service, for example:

- `mos/backend/app/services/medusa_connection.py`

Responsibilities:

- Admin API calls for product/variant/catalog operations
- Store API calls for carts/checkout
- auth/session handling for internal service-to-service use
- strict error propagation

## Workstream 2: Data Model Migration In MOS

## Objective

Remove Shopify-shaped assumptions from MOS’s product and variant records while keeping the migration incremental.

## Current problem

The current product model still encodes Shopify-specific fields such as:

- `shopify_product_gid`
- `external_price_id` carrying Shopify variant GIDs
- `shopify_last_synced_at`
- `shopify_last_sync_error`

## Required schema direction

Add generic commerce fields:

- `commerce_provider`
- `external_product_id`
- `external_variant_id`
- `external_catalog_source`
- `external_sync_status`
- `external_sync_error`
- `external_last_synced_at`

Keep the old Shopify fields temporarily during migration.

### Mapping policy

- existing Shopify data is migrated into generic external fields
- Shopify-specific columns remain only for transition and rollback
- new Medusa integrations write only the generic external fields

## Workstream 3: Medusa Application Standardization

## Objective

Define one standard Medusa app layout that every workspace/store instance uses.

## Standard Medusa app composition

- Medusa server instance
- Medusa worker instance
- PostgreSQL database
- Redis
- Marketi Medusa plugin

Medusa’s production docs recommend PostgreSQL + Redis and separate server/worker deployments, with `shared` mode as the default and `server` / `worker` modes for production separation. Sources:

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
- attach the Medusa external product id
- attach Medusa external variant ids to MOS variants

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

## Workstream 5: Checkout, Cart, And Order Attribution

## Objective

Rebuild the purchase flow so it still fits the MOS public runtime and attribution model.

## Target flow

1. MOS public page resolves product/variant/offer state.
2. MOS calls Medusa-backed cart/checkout creation.
3. Customer completes payment through Medusa’s payment flow.
4. Medusa emits order completion hooks/subscribers.
5. Medusa plugin posts a normalized completion event to MOS.
6. MOS records:
   - order
   - funnel attribution
   - page attribution
   - variant attribution
   - visitor/session metadata

## Metadata strategy

Carry MOS attribution metadata through cart/order metadata:

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

This mirrors what today is stored in Shopify note attributes and Stripe metadata, but moves it into a Medusa-native flow.

## Recommended Medusa customization

- wrap or extend checkout/order-completion flows with a Marketi workflow
- attach attribution metadata at add-to-cart / cart-completion time
- emit normalized internal webhooks back to MOS

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

### Custom Medusa admin additions

Use Admin Extensions for:

- MOS workspace linkage widget
- attribution visibility widget
- “open in MOS” links
- custom promotion helpers for Marketi offer logic

Source: [Medusa Admin customizations](https://docs.medusajs.com/learn/customization/customize-admin), [Medusa UI / Admin Extensions](https://docs.medusajs.com/ui/installation/medusa-admin-extension)

## Workstream 7: Templating, Styling, And Storefront Runtime

## Goal

Turn the current funnel-template system into a full storefront-template system.

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

## Important rule

There should be **one page/template engine**, not:

- one for funnels
- one for “real storefront pages”
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

### Safety gates

Before publish:

- token schema validation
- contrast audit
- accent-density checks
- template slot completeness
- Medusa binding validation

The existing design-system audit model should be expanded, not replaced.

## Storefront runtime choice

MOS should continue to render storefront pages.

Medusa’s official docs explicitly state the storefront is installed and hosted separately from the Medusa application, and teams can use the frontend stack and UX of their choice. Source: [Next.js Starter Storefront](https://docs.medusajs.com/resources/nextjs-starter).

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

## Workstream 10: Deployment, Compute, And Cost Control

## Objective

Run 10-20 workspaces economically without giving every workspace a full dedicated VM stack unless it actually needs it.

## Recommended infrastructure model

Use **pooled single-tenant apps**:

- one Medusa app per workspace/store
- shared app nodes
- shared Redis
- shared Postgres host or cluster
- database-per-workspace
- promote only heavy workspaces to dedicated resources

## Why this is the right cost model

If you do:

- one full VM pair per workspace

cost multiplies linearly and unnecessarily.

If you do:

- many Medusa workloads packed onto a few app nodes

you keep isolation at the application/database level while sharing base infrastructure.

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

## Current Medusa production guidance vs Marketi cost policy

Medusa docs recommend separate server and worker instances in production, while `shared` mode is the default and suitable for development. Sources:

- [General deployment guide](https://docs.medusajs.com/learn/deployment/general)
- [Worker mode](https://docs.medusajs.com/learn/production/worker-mode)

For Marketi, the practical policy should be:

- start many low-volume workspaces on shared infrastructure
- split server/worker where needed
- dedicate resources only when justified by real load

That is a deliberate operating choice based on tenant economics, not a contradiction of Medusa’s docs.

## Hetzner example sizing

As checked on March 12, 2026, Hetzner’s cloud page currently shows example EU shared plans such as:

- `CX23`: 2 vCPU / 4 GB / 40 GB at about `€3.49/mo`
- `CX33`: 4 vCPU / 8 GB / 80 GB at about `€5.49/mo`
- `CX43`: 8 vCPU / 16 GB / 160 GB at about `€9.49/mo`

Source: [Hetzner Cloud pricing](https://www.hetzner.com/cloud)

For the first 10-20 workspaces, a sensible starting point is:

- 2 shared app nodes
- 1 shared worker node
- 1 shared Postgres server or managed Postgres
- 1 shared Redis

The exact final instance sizes should be based on profiling, not assumption.

## Workstream 11: Migration Phasing

## Phase 0: Foundation

- finalize target architecture
- define generic commerce provider interfaces in MOS
- define Marketi Medusa plugin shape
- define generic external commerce fields in MOS

## Phase 1: Medusa platform bootstrap

- create base Medusa app
- create Marketi plugin
- wire PostgreSQL + Redis
- set up server/worker deployment template
- add basic admin customizations

## Phase 2: MOS provider abstraction

- implement Medusa adapter in MOS
- preserve Shopify adapter
- route catalog operations through the provider layer

## Phase 3: Catalog migration

- import products/variants/pricing/inventory from Shopify
- map MOS products to Medusa ids
- recreate promotions and bundle rules

## Phase 4: Checkout migration

- implement Medusa cart/checkout integration in MOS runtime
- add order-completion callbacks/subscribers into MOS
- preserve attribution metadata end to end

## Phase 5: Storefront template generalization

- upgrade funnel-template system into full storefront page system
- add page types beyond pre-sell/PDP
- add commerce bindings

## Phase 6: Reference import MVP

- capture bundle worker
- section normalization
- token extraction
- block matching
- reviewer workflow

## Phase 7: Controlled cutover

- dual-run Shopify and Medusa
- move selected workspaces/funnels to Medusa
- freeze Shopify catalog changes before final cutover
- keep Shopify read-only for historical lookup

## Phase 8: Retirement

- remove `shopify-funnel-app`
- remove Shopify-specific operator flows
- remove Shopify-named schema once data is fully migrated and rollback window closes

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

### Risk: Checkout attribution becomes weaker than today

Mitigation:

- define attribution metadata contract before building the Medusa checkout path
- enforce it in workflows/subscribers

### Risk: Commerce operators have to bounce between too many systems

Mitigation:

- keep MOS focused on storefront and experimentation
- extend Medusa admin only where operator handoff would otherwise be painful

## Recommended First Implementation Slice

If we want the fastest path to a real result, build this first:

1. Generic commerce provider interface in MOS
2. Base Medusa app + Marketi plugin
3. Product + variant sync into Medusa
4. Medusa-backed checkout flow for one page type
5. Normalized order completion back into MOS
6. Storefront template generalization for:
   - home
   - PDP
   - collection
7. Reference import MVP for:
   - theme extraction
   - pattern extraction
   - manual review

That gives us a working replacement path without waiting for the full site-import and template-synthesis system to be perfect.

## Final Recommendation

The system we should build is:

- **commerce-backed by Medusa**
- **storefront-authored by MOS**
- **template-driven**
- **token-governed**
- **import-assisted**
- **experiment-friendly**
- **cost-controlled through pooled infrastructure**

The right mental model is:

> Medusa runs the store’s commerce engine. MOS runs the store’s presentation, templating, experimentation, and iteration engine.

That is the path that replaces Shopify without throwing away the strongest parts of the current Marketi stack.

## External References

- [Medusa documentation hub](https://docs.medusajs.com/)
- [Commerce Modules](https://docs.medusajs.com/resources/commerce-modules)
- [Product Module](https://docs.medusajs.com/resources/commerce-modules/product)
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
