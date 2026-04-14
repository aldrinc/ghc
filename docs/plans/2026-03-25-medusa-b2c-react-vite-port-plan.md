# Medusa B2C Starter React + Vite Port Plan

## Decision

Port `medusajs/nextjs-starter-medusa` into Marketi as a new `medusa-b2c-starter` site family implemented in React + Vite.

This plan is the canonical import contract for Medusa family templates.

The storefront should talk to Medusa directly.

Do not proxy routine storefront commerce traffic through MOS endpoints.

Do not bring Next.js into the runtime.

Do not fold this into `medusa-b2b-starter`.

Do not treat this as a visual inspiration exercise.

The parity target is one-to-one at the level of:

- route structure
- page responsibilities
- major component boundaries
- Medusa Store API behavior
- cart and checkout flow
- customer/account/order flow
- loading, empty, and error states

The intentional rewrite is framework translation only:

- Next.js App Router, middleware, server components, server actions, and cache tags become React + Vite routing, explicit client-side Medusa SDK usage, and browser-managed session/cart persistence.

## Refined Architecture Based On Your Feedback

The core boundary is:

1. MOS owns site family definitions, page composition, template synthesis, import/adaptation, and public page/runtime config.
2. The published storefront runtime owns rendering and route handling in React + Vite.
3. The storefront runtime talks directly to Medusa for catalog, cart, checkout, customer, and order operations.

This means MOS is still in the system, but not as a commerce proxy.

MOS remains responsible for:

- `medusa-b2c-starter` family registration
- page blueprint definitions
- public page JSON and design-system payloads
- site publishing/runtime artifact generation
- import flow and template adaptation
- storing workspace-level Medusa config so the runtime can bootstrap

MOS should not sit in the request path for:

- product listing
- collection listing
- category listing
- PDP fetches
- cart mutations
- shipping methods
- payment session initialization
- customer login/register/logout
- address CRUD
- order retrieval
- transfer actions

## Why This Is A Separate Family

The current site runtime and blueprint system only truthfully covers the commerce-core page set for `medusa-b2b-starter`:

- `home`
- `category`
- `product_detail`
- `cart`
- `checkout`

That is explicit in `mos/backend/app/services/site_blueprints.py`.

The upstream B2C starter includes materially different scope:

- country-prefixed routes
- store page
- collections
- nested categories
- customer login/register
- account dashboard
- address book
- orders list and order detail
- order confirmation
- transfer flows

Trying to overload the B2B family with these behaviors would blur family meaning, complicate imports, and make the runtime harder to reason about.

## Source Of Truth

Pin one upstream commit from:

- `https://github.com/medusajs/nextjs-starter-medusa`

Use that commit as the source of truth during the port.

Before implementation starts, produce a parity checklist covering:

- every route under `src/app`
- every template under `src/modules`
- every data dependency under `src/lib/data`
- layout behavior from `src/app/layout.tsx`, `src/app/[countryCode]/(main)/layout.tsx`, and `src/app/[countryCode]/(checkout)/layout.tsx`
- middleware behavior from `src/middleware.ts`
- cookie/session handling from `src/lib/data/cookies.ts`
- SDK bootstrap from `src/lib/config.ts`

No implementation should claim parity against "latest starter behavior" without pointing back to the pinned commit.

## Non-Negotiable Constraints

- No Next.js in Marketi runtime.
- No fake data to stand in for missing Medusa support.
- No silent fallbacks for unsupported flows. Fail clearly.
- No storefront commerce proxy through MOS unless explicitly approved later.
- No "visual-only parity" signoff if account or order flows are missing.

## Canonical Import Contract

### No Legacy Section Schema

Legacy `Section` props are removed from the supported page schema:

- `layout`
- `containerWidth`
- `padding`

Use only the modern layout fields on `Section.props`:

- `bandWidth`
- `contentWidth`
- `contentAlign`
- `surface`
- `padY`
- `padX`

Operational rules:

- Do not rely on a runtime migration layer to translate old keys. That path is intentionally removed.
- Backend request validation and frontend normalization should reject legacy `Section` keys with a clear error.
- Existing stored page versions must be migrated before they are rendered or edited again.
- If an import payload contains legacy `Section` keys, treat it as invalid source data. Fix the payload or migrate it deliberately. Do not silently reinterpret it.

### Section Defaults For Medusa Imports

| Section use | Required `Section.props` | Why |
| --- | --- | --- |
| Shell section owned by a family block | `bandWidth: "bleed"`, `contentWidth: "none"`, `contentAlign: "center"`, `surface: "none"`, `padY: "none"`, `padX: "none"` | Prevents outer width clamps and double padding when the imported block already owns its inner container |
| Standard content section | `bandWidth: "bleed"`, `contentWidth: "xl"`, `contentAlign: "center"`, `surface: "none"`, `padY: "md"`, `padX: "md"` | Gives normal readable page sections a consistent modern frame |
| Intentional emphasis/card section | `bandWidth: "bleed"`, `contentWidth: "xl"`, `contentAlign: "center"`, `surface: "card"`, `padY: "md"`, `padX: "md"` | Opt-in card treatment only when the design explicitly calls for it |

For Medusa starter-family imports, treat these blocks as shell-owned and keep them on `contentWidth: "none"`:

- header and footer shells
- promo bars
- hero sections
- store/category wrappers
- product detail shells
- cart shells
- checkout shells

The practical rule is simple:

- if the imported Medusa family block already renders its own container, spacing, or full-width shell, the outer `Section` must stay full-bleed and unclamped
- do not add another container on top of it

### B2C Import Procedure

1. Pin the upstream Medusa B2C starter commit before any translation work starts.
2. Register the import explicitly as `medusa-b2c-starter`.
3. Pass explicit page-role metadata during import. Do not rely on family inference alone.
4. Translate every page to canonical Puck JSON using only the modern `Section` schema.
5. Keep imported Medusa shell blocks on `contentWidth: "none"` so the React/Vite family implementation owns the inner frame.
6. Fail the import if a page cannot be mapped cleanly to a supported B2C page type.
7. Validate the stored page JSON and live route width before signoff.

Required import metadata:

- `siteFamilyHint: "medusa-b2c-starter"`
- `pageTypeHint` per page, for example:
- `home`
- `store`
- `collection`
- `category`
- `product_detail`
- `cart`
- `checkout`
- `account_dashboard`
- `account_profile`
- `account_addresses`
- `account_orders`
- `account_order_detail`
- `order_confirmed`
- `order_transfer`
- `order_transfer_accept`
- `order_transfer_decline`

### Import Validation Checklist

Before signoff, confirm all of the following:

- canonical template JSON contains no `layout`, `containerWidth`, or `padding` keys on any `Section`
- stored published page JSON contains no legacy `Section` keys
- shell sections render full width, with the family block owning the inner container
- no imported page is depending on design-system width defaults to decide page structure
- B2C page-role mapping is explicit, not inferred from screenshot similarity alone

Useful checks:

```bash
rg -n '"(layout|containerWidth|padding)"' mos/backend/app/templates/funnels
```

```bash
curl -sS http://localhost:8008/public/funnels/<product-slug>/<funnel-slug>/pages/<page-slug> | jq '.puckData.content'
```

If either check shows legacy `Section` keys, the import is not ready.

## Current State In Marketi

### What Already Exists

The current public runtime already has useful Medusa storefront building blocks:

- public page rendering in `mos/frontend/src/pages/public/PublicFunnelPage.tsx`
- commerce UI primitives in `mos/frontend/src/components/commerce/CommerceBlocks.tsx`
- Puck block registration in `mos/frontend/src/funnels/puckConfig.tsx`
- site family descriptors in `mos/backend/app/services/site_blueprints.py`
- template-family registration in `mos/backend/app/services/template_synthesis.py`
- workspace-level Medusa config in `mos/frontend/src/api/products.ts`

### What Changes With This Plan

The existing MOS public site-commerce endpoint path is no longer the target architecture for the B2C starter.

For `medusa-b2c-starter`:

- site/page metadata still comes from MOS
- commerce data should come directly from Medusa

### What Does Not Exist Yet

The current runtime does not yet expose full upstream B2C starter parity for:

- direct Medusa SDK bootstrap in the public runtime
- country-code route normalization
- collection pages as first-class routes
- nested category route semantics
- customer authentication
- customer session persistence in a browser-managed model
- account dashboard routes
- address CRUD
- order history and order detail
- order transfer flows
- direct-to-Medusa checkout correctness equivalent to the starter

## Upstream Starter Inventory

### App Routes To Port

| Upstream route | Marketi target |
| --- | --- |
| `/[countryCode]` | home page |
| `/[countryCode]/store` | all-products store page |
| `/[countryCode]/collections/[handle]` | collection page |
| `/[countryCode]/categories/[...category]` | nested category page |
| `/[countryCode]/products/[handle]` | product detail page |
| `/[countryCode]/cart` | cart page |
| `/[countryCode]/checkout` | checkout page |
| `/[countryCode]/account` | login/account shell |
| `/[countryCode]/account/profile` | account profile |
| `/[countryCode]/account/addresses` | address book |
| `/[countryCode]/account/orders` | orders list |
| `/[countryCode]/account/orders/details/[id]` | order detail |
| `/[countryCode]/order/[id]/confirmed` | order confirmation |
| `/[countryCode]/order/[id]/transfer/[token]` | transfer landing |
| `/[countryCode]/order/[id]/transfer/[token]/accept` | transfer accept |
| `/[countryCode]/order/[id]/transfer/[token]/decline` | transfer decline |

### Module Areas To Port

From the upstream `src/modules` tree:

- `home`
- `layout`
- `store`
- `collections`
- `categories`
- `products`
- `cart`
- `checkout`
- `account`
- `order`
- shared `common`, `shipping`, and `skeletons` pieces as needed

### Data Surfaces To Port

From the upstream `src/lib/data` tree:

- products
- collections
- categories
- regions
- locales
- cart
- fulfillment
- payment
- customer
- orders
- variants

## Target Runtime Architecture

## React + Vite Rule

Everything user-facing in the storefront runtime should be implemented with the existing Marketi frontend stack:

- React
- Vite
- React Router
- existing public funnel/site runtime

Do not add a second web app.

Do not embed the Next starter as a sidecar frontend.

Do not proxy a separate Next deployment.

## Direct Medusa Rule

The storefront runtime should use Medusa directly, like the upstream starter does.

The upstream starter bootstraps `@medusajs/js-sdk` with:

- Medusa backend URL
- Medusa publishable key

The React + Vite port should do the same.

Target runtime env/config:

- `VITE_MEDUSA_BACKEND_URL`
- `VITE_MEDUSA_PUBLISHABLE_KEY`
- `VITE_MEDUSA_DEFAULT_REGION`

If these values are workspace-specific rather than globally fixed, MOS should inject or expose them as runtime config, but it should still not proxy the commerce requests themselves.

## MOS Boundary

MOS should still own:

- `medusa-b2c-starter` family registration
- site/page metadata
- design-system tokens
- route/page blueprint mapping
- runtime artifact generation
- import support
- workspace-level Medusa configuration authoring

MOS should not own:

- catalog read APIs for the storefront
- cart state APIs for the storefront
- customer auth APIs for the storefront
- order APIs for the storefront

## Session And Cart Persistence Model

This is the biggest architectural difference between the upstream Next starter and the React + Vite port.

The upstream starter uses Next server-side cookie helpers for:

- `_medusa_jwt`
- `_medusa_cart_id`
- `_medusa_cache_id`

The Vite port cannot reproduce that implementation literally without adding a server bridge, which this plan now explicitly avoids.

So the port should define a browser-managed persistence layer up front.

Default assumption for this plan:

- customer JWT is stored via a dedicated client-side session store abstraction
- cart ID is stored via the same abstraction
- country code and locale are stored there as needed

Implementation rule:

- define one storage abstraction early
- use it everywhere
- do not mix ad hoc cookie reads, localStorage reads, and in-memory state without a single source of truth

If httpOnly cookie semantics become a hard requirement later, that is a separate architecture change and should not be smuggled into this port.

## Route Model

The current public site runtime is built around a single page slug plus `pageTypeMap`.

That is not enough for the B2C starter.

We need a site-aware catch-all route model capable of:

- country-prefixed paths
- nested segments
- account sub-routes
- order and transfer sub-routes
- query param preservation for sort, page, and variant selection

Target public route shape:

- `/f/:productSlug/:funnelSlug/*sitePath`

Where `sitePath` can resolve to:

- `us`
- `us/store`
- `us/collections/summer`
- `us/categories/skincare`
- `us/categories/skincare/serums`
- `us/products/face-oil`
- `us/cart`
- `us/checkout`
- `us/account`
- `us/account/profile`
- `us/account/addresses`
- `us/account/orders`
- `us/account/orders/details/order_123`
- `us/order/order_123/confirmed`
- `us/order/order_123/transfer/token_abc`

Bundle mode should support the same nested route semantics.

## Site Family Model

Add a new site family:

- `medusa-b2c-starter`

This family should have page blueprints for at least:

- `home`
- `store`
- `collection`
- `category`
- `product_detail`
- `cart`
- `checkout`
- `account_dashboard`
- `account_profile`
- `account_addresses`
- `account_orders`
- `account_order_detail`
- `order_confirmed`
- `order_transfer`
- `order_transfer_accept`
- `order_transfer_decline`

If the existing site/page blueprint model is too page-type-oriented for nested account/order routes, extend it rather than collapsing all account behavior into one generic page.

## Porting Strategy

## Principle

Port behavior and structure first.

Do not begin by translating every upstream component file into local copies.

Instead:

1. define runtime config delivery
2. define route resolution
3. define direct Medusa client and session state
4. port layouts
5. port page templates
6. port smaller components

This avoids importing Next-specific assumptions into the wrong boundary.

## Two-Layer Frontend Model

Create two layers:

### Layer 1: Shared Medusa Runtime

Owns:

- Medusa client bootstrap
- current country/locale/region
- cart state
- customer state
- payment state
- order state
- session/cart persistence
- navigation helpers
- route parsing helpers
- loading and error state

Likely home for this work:

- `mos/frontend/src/lib/medusa/*`
- `mos/frontend/src/components/commerce/runtime/*`
- `mos/frontend/src/providers/*`

### Layer 2: B2C Starter Presentation

Owns:

- exact page layouts
- starter-style nav/footer
- starter-style store/category/collection layouts
- PDP structure
- cart structure
- checkout structure
- account and order templates

Likely home for this work:

- `mos/frontend/src/components/commerce/b2c/*`

Do not keep all of this inside one giant `CommerceBlocks.tsx` file.

## Detailed Workstreams

## Workstream 1: Runtime Config Delivery

### Goal

Make the public storefront runtime able to initialize a Medusa client directly.

### Required changes

- add `@medusajs/js-sdk` to `mos/frontend/package.json`
- define frontend env/runtime config for Medusa backend URL, publishable key, and default region
- decide whether runtime config is fully env-based or partially injected from MOS page metadata
- ensure published artifacts receive the config needed to talk directly to the correct Medusa instance

### Deliverable

The public runtime can initialize a Medusa client without hitting a MOS commerce proxy.

## Workstream 2: Route And Runtime Foundation

### Goal

Make the public site runtime capable of representing the starter’s real URL model.

### Required changes

- extend `mos/frontend/src/App.tsx` public route handling to support nested site paths
- update `mos/frontend/src/pages/public/PublicFunnelPage.tsx` to resolve nested site routes, not only a single page slug
- extend `mos/frontend/src/funnels/runtimeRouting.ts` path builders to support nested route targets
- extend runtime context in `mos/frontend/src/funnels/puckConfig.tsx` so site navigation can resolve country-aware nested routes cleanly

### Deliverable

A route layer that can render all upstream B2C starter paths in Marketi.

## Workstream 3: Site Family And Template Registration

### Goal

Make `medusa-b2c-starter` a first-class family across backend and frontend tooling.

### Files to change

- `mos/backend/app/services/site_blueprints.py`
- `mos/backend/app/services/template_synthesis.py`
- `mos/backend/app/services/site_import_adapter.py`
- `mos/frontend/src/pages/workspaces/StoreTemplatesPage.tsx`
- related schemas and enums for site family validation

### Deliverable

The new family is selectable, validated, and recognized by the runtime and import surfaces.

## Workstream 4: Medusa Client And Session Layer

### Goal

Replace the current MOS-centric storefront data path with a direct Medusa client layer.

### Required work

- create a reusable Medusa SDK bootstrap module
- create a session/cart persistence abstraction
- create direct data modules for products, collections, categories, regions, locales, cart, customer, and orders
- create mutation helpers for login, register, logout, add-to-cart, shipping, payment, and checkout

### Important implementation note

This is where the Next starter’s `src/lib/config.ts` and `src/lib/data/*` model is re-expressed for React + Vite.

Do not replicate the Next server-action shape.

Replicate the behavior and call graph, but in client-safe modules.

### Deliverable

The storefront uses Medusa directly for all commerce interactions.

## Workstream 5: Shared Commerce Runtime Refactor

### Goal

Break the current commerce runtime into reusable pieces before adding B2C complexity.

### Why

`mos/frontend/src/components/commerce/CommerceBlocks.tsx` already contains:

- cart state
- checkout state
- product grid
- PDP
- nav/footer
- category list

That file will become unmanageable if the full B2C starter is added directly into it.

### Refactor targets

Split out:

- runtime provider
- Medusa client hooks/state
- session store
- navigation helpers
- formatting helpers
- starter-specific page templates

### Deliverable

A maintainable component tree that can support both B2B and B2C families.

## Workstream 6: Anonymous Storefront Pages

### Goal

Port the non-authenticated storefront routes one-to-one.

### Pages

- home
- store
- collection
- category
- product detail
- cart
- checkout

### Local component targets

Create B2C-specific equivalents for:

- main layout
- checkout layout
- nav
- footer
- hero
- featured product rails
- refinement list
- pagination
- product gallery
- product info
- product actions
- tabs
- related products
- cart summary
- checkout form
- checkout summary

### Deliverable

Anonymous storefront behavior matches the upstream starter structurally and behaviorally.

## Workstream 7: Customer Account And Order Flows

### Goal

Port the authenticated surfaces using direct Medusa interaction from the browser runtime.

### Pages

- account shell
- login/register split
- overview
- profile
- addresses
- orders list
- order detail
- order confirmation
- transfer routes

### Required runtime support

- customer auth and session persistence
- current customer bootstrap
- address CRUD
- order lookup
- transfer route mutations

### Deliverable

The storefront can truthfully support the starter’s account and order scope.

## Workstream 8: Country And Locale Behavior

### Goal

Replace upstream Next middleware behavior with explicit React + Vite behavior.

### Upstream behavior to mirror

The starter middleware:

- loads regions
- determines country code from URL, edge geolocation, or default region
- redirects to a country-prefixed path

### Marketi target

Implement equivalent behavior using:

- direct region fetch from Medusa
- frontend bootstrap redirect logic for missing country code
- explicit route normalization
- query-string preservation

Do not attempt to mimic Next middleware internally.

Define the equivalent behavior clearly and implement it intentionally.

### Deliverable

Country-aware storefront routes behave consistently and predictably.

## Workstream 9: Import And Template Synthesis Support

### Goal

Make the new family importable only after the runtime exists.

### Required changes

- add family registration for `medusa-b2c-starter`
- map imported page roles to new page blueprint types
- extend screenshot-to-code adaptation to understand B2C page roles
- enforce the canonical modern `Section` schema during import
- fail clearly when imported content cannot be mapped cleanly

### Deliverable

The import system can target B2C starter pages without pretending unsupported sections are valid or silently reviving legacy layout props.

## File-Level Change Map

## Backend

High-probability backend files to change:

- `mos/backend/app/services/site_blueprints.py`
- `mos/backend/app/services/template_synthesis.py`
- `mos/backend/app/services/site_import_adapter.py`
- `mos/backend/app/schemas/sites.py`
- `mos/backend/app/schemas/storefront_templates.py`
- `mos/backend/app/db/enums.py`
- related tests under `mos/backend/tests/`

Backend work should stay focused on family registration, site/page metadata, and import/runtime configuration.

It should not expand into a Medusa commerce proxy.

## Frontend

High-probability frontend files to change:

- `mos/frontend/package.json`
- `mos/frontend/src/App.tsx`
- `mos/frontend/src/pages/public/PublicFunnelPage.tsx`
- `mos/frontend/src/funnels/puckConfig.tsx`
- `mos/frontend/src/funnels/runtimeRouting.ts`
- `mos/frontend/src/types/commerce.ts`
- `mos/frontend/src/components/commerce/CommerceBlocks.tsx`
- `mos/frontend/src/pages/workspaces/StoreTemplatesPage.tsx`

Likely new frontend files:

- `mos/frontend/src/lib/medusa/*`
- `mos/frontend/src/lib/commerce/*`
- `mos/frontend/src/components/commerce/runtime/*`
- `mos/frontend/src/components/commerce/b2c/*`
- route/state helpers for country-prefixed storefront paths

## Recommended Execution Sequence

1. Pin the upstream commit and create the parity checklist.
2. Add `medusa-b2c-starter` family registration and blueprint coverage.
3. Implement runtime config delivery for direct Medusa access.
4. Implement nested public site routing and path resolution.
5. Implement the Medusa client and session/cart persistence layer.
6. Refactor shared commerce runtime out of `CommerceBlocks.tsx`.
7. Port anonymous storefront layouts and pages.
8. Port account and order flows.
9. Implement country and locale normalization behavior.
10. Add import/template synthesis support for the new family.
11. Add parity tests and route-by-route visual verification.

This order minimizes wasted UI work before route and Medusa runtime surfaces are stable.

## Verification Plan

## Route Parity

For every upstream route, verify:

- correct page renders
- correct layout shell renders
- country prefix is preserved
- internal navigation generates correct local URLs

## Direct Medusa Data Parity

Verify:

- region list and country resolution
- product listing
- collection filtering
- category filtering
- variant selection
- cart creation
- cart persistence
- shipping option loading
- payment provider loading
- checkout completion
- customer login/register/logout
- address CRUD
- orders list
- order detail
- transfer action routes

## UI Parity

For each route, compare against the pinned upstream starter for:

- visual hierarchy
- section order
- empty states
- loading states
- button labels
- navigation affordances

## Regression Coverage

Add tests for:

- route resolution helpers
- Medusa client/session store behavior
- cart and checkout state transitions
- customer/account flows
- order transfer flows
- country and locale normalization

Prefer deterministic unit/integration coverage over screenshots alone.

## Definition Of Done

This port is only done when all of the following are true:

- `medusa-b2c-starter` exists as a first-class site family
- the public runtime supports nested country-aware storefront routes
- the storefront runtime talks directly to Medusa
- anonymous storefront pages match the upstream starter structurally and behaviorally
- account and order flows are implemented, not omitted
- cart, customer, and country state persist through a defined client-side session layer
- parity tests exist for route, session, cart, checkout, account, and order flows
- import/template registration for the new family is wired in or explicitly blocked with clean errors

## Explicit Non-Goals

These are not part of the initial parity definition unless explicitly approved later:

- redesigning the starter
- improving the starter UX beyond parity
- merging B2B and B2C into one generic family
- introducing Next.js as a second runtime
- expanding MOS into a storefront commerce proxy
- supporting unsupported fallback flows with placeholder behavior

## Final Recommendation

Treat this as a direct-to-Medusa storefront port, not a MOS-commerce-proxy project.

The real work is:

- adding a separate B2C site family
- upgrading the route model
- building a direct Medusa client/session layer in React + Vite
- porting the starter’s page and account/order structure faithfully

If those four pieces are done cleanly, the one-to-one React + Vite port is realistic.

If we keep the old assumption that storefront commerce must pass through MOS endpoints, the architecture will drift away from the starter and create unnecessary translation work.
