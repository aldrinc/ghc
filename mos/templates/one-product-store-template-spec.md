# One-Product Store Template Spec

## Decision

Build a reusable one-product storefront template by reusing existing page systems, not by inventing new page types. The homepage or PDP should be based on the existing sales-page implementation, checkout should be based on the existing Medusa checkout page, and legal or support pages should be based on the existing policy or contact templates. `Buy now` persists the selected cart state in Medusa and routes the shopper directly into checkout, while a global header cart opens a slide-out cart drawer.

## Product Definition

This template is for a direct-response, one-SKU or one-core-product store.

- Primary use case: paid traffic lands on a single high-conversion page and goes straight to checkout.
- Homepage and PDP are the same experience.
- The starter uses Medusa as the system of record for products, variants, pricing, cart state, and checkout state.
- `Buy now` writes the selected variant or offer into the Medusa cart and routes to the storefront checkout page.
- The template must still include the operational pages a real store needs: privacy, terms, refund, shipping, support, and order tracking.

For the initial design direction, assume a premium supplement-style storefront inspired by high-performing creatine gummy offers:

- strong brand presence in the first viewport
- high trust and proof density
- clear bundle economics
- aggressive CTA visibility
- no generic marketplace feel

Do not hardcode product claims, medical claims, ingredient facts, or testimonials into the template defaults. Those stay merchant-authored and evidence-backed.

## Goals

- Reusable template for any one-product store, not only creatine gummies.
- Conversion-first PDP on `/`.
- Direct-to-checkout primary flow with no dedicated cart page.
- Required global slide-out cart drawer accessible from the header.
- Reuse existing page templates and components as the base for the starter.
- Configurable variant, bundle, and merchandising system.
- Required legal and support surfaces included from day one.
- Real order tracking path defined end-to-end.
- Fast to theme and populate through config.

## Non-Goals

- Multi-product catalog browsing.
- On-site checkout implementation.
- Rebuilding sales, checkout, policy, or support pages from scratch when repo-owned base pages already exist.
- CMS implementation beyond a config-driven content model.
- Subscription logic unless explicitly added to the offer model.
- Fake tracking pages or placeholder support flows.

## Experience Thesis

- Visual thesis: clean clinical trust meets candy-premium energy, with the product pack as the hero object and the brand name louder than the headline.
- Content plan: poster-like hero, proof and product depth, offer stack and FAQ resolution, final CTA close.
- Interaction thesis: sticky buy module, scroll-linked proof reveals, restrained media zoom for gallery and ingredient/detail sections.

## Reuse-First Architecture

Decision: this starter should compose and skin existing page implementations already in the repo. It should not introduce a parallel set of homepage, checkout, or policy pages that duplicate the same responsibilities.

### Base page matrix

| Store surface | Existing base to reuse | Repo reference |
| --- | --- | --- |
| Home/PDP | Existing sales-page system | [`mos/backend/app/templates/funnels/sales_pdp.json`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/sales_pdp.json) and [`mos/frontend/src/funnels/templates/salesPdp/SalesPdpTemplate.tsx`](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/funnels/templates/salesPdp/SalesPdpTemplate.tsx) |
| Checkout | Existing Medusa checkout page | [`mos/backend/app/templates/funnels/medusa-b2c-checkout.json`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2c-checkout.json) and [`mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx`](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx) |
| Product detail commerce wiring | Existing Medusa product page and runtime | [`mos/backend/app/templates/funnels/medusa-b2c-product.json`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2c-product.json) and [`mos/frontend/src/components/commerce/b2c/pages/MedusaB2CProductPage.tsx`](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/commerce/b2c/pages/MedusaB2CProductPage.tsx) |
| Policy pages | Existing Medusa policy templates | [`mos/backend/app/templates/funnels/medusa-b2c-policy-privacy.json`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2c-policy-privacy.json), [`mos/backend/app/templates/funnels/medusa-b2c-policy-terms.json`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2c-policy-terms.json), [`mos/backend/app/templates/funnels/medusa-b2c-policy-returns.json`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2c-policy-returns.json), and [`mos/backend/app/templates/funnels/medusa-b2c-policy-shipping.json`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2c-policy-shipping.json) |
| Support page | Existing contact policy template | [`mos/backend/app/templates/funnels/medusa-b2c-policy-contact.json`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2c-policy-contact.json) |

### What “template” means here

- The starter should be a reusable composition of existing pages, components, and content schemas.
- The “creatine gummies page” should be treated as a page instance or preset on top of the existing sales-page base, not as a one-off page architecture.
- Checkout should be a branded or configured version of the existing Medusa checkout page, not a separately invented checkout implementation.
- Policy and support pages should be routed instances of the existing policy or contact templates with brand-specific content.

### Allowed customization scope

- Update styling, content defaults, merchandising configuration, product binding, and CTA behavior.
- Add Medusa bindings and cart-drawer behavior where the base pages need them.
- Extend existing page components only when the starter requires additional hooks or slots.

### Disallowed customization scope

- Creating a second homepage system when `SalesPdpPage` already covers the sales-page use case.
- Creating a second checkout page when `MedusaB2CCheckoutPage` already exists.
- Creating duplicate privacy, refund, shipping, terms, or contact page systems.
- Forking base pages without a concrete starter requirement that cannot be handled through composition or extension.

## Information Architecture

| Route | Purpose | Notes |
| --- | --- | --- |
| `/` | Canonical homepage + PDP | Main conversion surface |
| `/product` | Optional alias route | Redirect to `/` to avoid duplicate content |
| `/checkout` | Checkout page | May resolve to a country-prefixed runtime path such as `/us/checkout` |
| `/policies/privacy-policy` | Privacy policy | Separate page, not modal |
| `/policies/terms-of-service` | Terms of service | Separate page, not modal |
| `/policies/refund-policy` | Returns and refunds policy | Separate page, not modal |
| `/policies/shipping-policy` | Shipping policy | Recommended for support clarity |
| `/support` | Contact and support page | Includes contact methods and service expectations |
| `/track-order` | Order lookup/status page | Ship only with real lookup backend |

Global UI surface: header cart button opens a slide-out cart drawer. There is no `/cart` page.

## Medusa Starter Wiring

Decision: the template starter should be Medusa-native for catalog, pricing, cart, checkout, customer session, and order data. Any Shopify or other hosted-checkout handoff should be treated as a separate adapter, not the default starter path.

### Wiring map

| Concern | Current repo implementation | Starter responsibility |
| --- | --- | --- |
| Sales-page visual base | [`mos/frontend/src/funnels/templates/salesPdp/SalesPdpTemplate.tsx`](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/funnels/templates/salesPdp/SalesPdpTemplate.tsx) | Reuse the existing sales-page system as the home or PDP shell |
| Runtime config | [`mos/frontend/src/lib/medusa/config.ts`](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/lib/medusa/config.ts) | Read backend URL, publishable key, default region, and default country |
| Session persistence | [`mos/frontend/src/lib/medusa/session.ts`](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/lib/medusa/session.ts) | Persist `cartId`, auth token, country code, and locale in browser storage |
| Catalog access | [`mos/frontend/src/lib/medusa/data.ts`](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/lib/medusa/data.ts) | Load product, variant, collection, category, and cart data from Medusa Store API |
| Storefront runtime | [`mos/frontend/src/components/commerce/b2c/B2CRuntimeProvider.tsx`](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/commerce/b2c/B2CRuntimeProvider.tsx) | Own country selection, cart creation, cart updates, checkout navigation, and customer session |
| Product binding reference | [`mos/frontend/src/components/commerce/b2c/pages/MedusaB2CProductPage.tsx`](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/commerce/b2c/pages/MedusaB2CProductPage.tsx) | Load one Medusa product by handle, resolve variant selection, and trigger buy flow |
| Checkout reference | [`mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx`](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx) | Render checkout, shipping, payment, and policy-link surfaces |

### Product binding model

- The one-product template should bind to a single Medusa product by `handle` as the canonical starter configuration.
- `product.medusa.handle` should be the minimum required binding field in the template config.
- `product.medusa.id` can be stored as an optional optimization or publish-time snapshot, but the runtime should be able to recover from handle alone.
- On page load, the storefront should call `loadProductByHandle(handle)` through the B2C runtime and hydrate the page from the returned `MedusaProduct`.

### Variant and offer mapping

- Variant selectors should be generated from Medusa product `options` and `variants`, not hardcoded page enums.
- The merchandising layer can still define named offers such as `Single Jar`, `3 Pack`, or `Subscribe & Save`, but each offer must map to one or more Medusa variant ids plus quantities.
- If the product has one physical variant and marketing bundles are multiplicative, the offer config should map that offer to repeated quantities of the same variant.
- If the product has flavor or size variants, the selector should resolve the correct concrete Medusa variant id before `Buy now` becomes enabled.
- If no valid Medusa variant can be resolved from the current selections, the page should block checkout and show a clear error state.

### Cart and checkout wiring

- The runtime should use `getOrCreateCart()` to recover or create the active Medusa cart.
- `Buy now` should add or update the selected Medusa line items in that cart, persist the resulting `cartId`, and route to the Medusa checkout page.
- The header cart drawer should read from the active Medusa cart state exposed by `B2CRuntimeProvider`.
- Quantity changes and remove actions in the drawer should call `updateCartItem` and `removeCartItem`.
- Checkout should use the existing Medusa checkout route and mutations already modeled in the B2C runtime, including email, shipping address, shipping method, payment session, and complete-cart actions.

### Region, currency, and country contract

- Region must be determined at cart creation time through Medusa.
- Default behavior should use `VITE_MEDUSA_DEFAULT_REGION_ID` when configured; otherwise resolve the region from the current country code.
- Country changes mid-checkout should not be supported. If the shopper switches country after cart creation, the template should require a fresh cart.
- Public route resolution may include a country prefix through the runtime site-path system, for example `/us/checkout`.

### Required Medusa runtime configuration

- `VITE_MEDUSA_BACKEND_URL`
- `VITE_MEDUSA_PUBLISHABLE_KEY`
- `VITE_MEDUSA_DEFAULT_REGION_ID` or a resolvable default country
- `VITE_MEDUSA_DEFAULT_COUNTRY_CODE`

## Primary User Flows

### 1. Purchase flow

1. User lands on `/`.
2. User reviews hero, benefits, ingredients or proof, reviews, guarantee, and FAQ.
3. User selects required options such as flavor, bundle, or purchase type.
4. User clicks `Buy now`.
5. Frontend resolves the selected Medusa variant or offer mapping into concrete cart lines.
6. Medusa cart state is created or updated and `cartId` is persisted.
7. Frontend routes immediately to the Medusa checkout page.

### 2. Cart drawer flow

1. User completes `Buy now` and is redirected to checkout.
2. User later returns to the storefront in the same session or reopens the site with persisted cart state.
3. User clicks the header cart button.
4. Slide-out cart drawer opens from the header edge and shows the most recent Medusa cart contents.
5. User reviews line items, updates quantity, removes items, or proceeds back to checkout.
6. Drawer state stays synchronized with the persisted active cart reference.

### 3. Support flow

1. User lands on `/support` from footer or post-purchase communications.
2. User sees support email, support hours, response SLA, and issue categories.
3. If a support form backend exists, submit through the form.
4. If no support form backend exists, expose only real support channels.

### 4. Order tracking flow

1. User lands on `/track-order`.
2. User enters order number plus email, or tracking number, depending on backend contract.
3. Frontend requests order status from backend.
4. User sees fulfillment state, shipment events, tracking links, and current delivery status.

## Page Spec: Homepage / PDP

The homepage should be a single narrative page with a persistent route and a sticky purchase path. It should be implemented as a reuse or configuration of the existing sales-page base, not as a new PDP page system.

### Section order

1. Hero
2. Trust strip
3. Product proof
4. Ingredient or feature detail
5. Social proof
6. Offer stack
7. Comparison or objection handling
8. FAQ
9. Guarantee and support reassurance
10. Footer with legal and support links

### Hero

- Full-bleed or dominant-visual composition.
- Product packshot or lifestyle asset as the main visual anchor.
- Brand name, product name, key promise, price anchor, and CTA above the fold.
- Rating summary and review count can appear if real data exists.
- Sticky buy module begins on desktop immediately and appears as a compact sticky bar on mobile after scroll threshold.
- Header must include a cart icon with an item count badge. Activating it opens the cart drawer.
- CTA copy should match the actual action. `Buy now` should persist the selected cart state and go directly to checkout. Do not expose a separate `Add to cart` CTA.
- The section structure should be achieved by configuring or extending the existing sales-page sections rather than replacing the entire page architecture.

### Trust strip

- Compact row for shipping promise, guarantee, secure checkout, and subscription disclosure if applicable.
- Only include claims the merchant can operationally support.

### Product proof

- Explain what the product is, who it is for, and why it is differentiated.
- Allow merchant-configured evidence blocks such as ingredient callouts, certification badges, or sourcing details.
- For supplements, include configurable areas for supplement facts, directions, warnings, and disclaimers.

### Ingredient or feature detail

- Modular section for active ingredients, mechanism, or product technology.
- Each item should support title, short explanation, visual asset, and optional citation or source label.
- Do not encode medical promises into the template.

### Social proof

- Video testimonials, review cards, before/after only if compliant and approved for the merchant category.
- Reviews must come from merchant-provided content.
- Review summary can be repeated in sticky purchase module.

### Offer stack

- Required selector area for bundle, flavor, size, or purchase type.
- Show compare-at price, per-unit economics, savings label, and subscription note where relevant.
- Allow one recommended offer to be visually emphasized.
- Quantity changes must update CTA label, cart payload, and checkout payload.
- The offer module should support a single primary CTA: `Buy now`.

### Comparison and objection handling

- Structured grid or list addressing common objections.
- Typical rows: convenience, taste, dosing format, price per serving, delivery, guarantee.
- Keep this factual and merchant-editable.

### FAQ

- Accordions for shipping, ingredients, dosage, returns, subscriptions, and support.
- Include anchor links from header or sticky nav.

### Guarantee and support reassurance

- Clear guarantee summary with full refund-policy link.
- Support CTA linking to `/support`.
- Shipping expectations and fulfillment window summary.

### Footer

- Brand mark, copyright, legal links, support link, track-order link, and optional social links.
- Footer content must match actual business identity and support operations.

## Auxiliary Page Spec

All auxiliary routes should prefer the existing Medusa policy or contact templates as their base implementation.

### Privacy policy

- Render as a dedicated route.
- Source from a config payload or backend policy-page endpoint.
- Must be linkable from footer and checkout-adjacent surfaces.

### Terms of service

- Dedicated route.
- Include offer, billing, fulfillment, disputes, and account expectations where applicable.

### Refund policy

- Dedicated route.
- Must match guarantee messaging on the PDP.
- If refunds depend on time window, product condition, or contact workflow, that must be explicit.

### Shipping policy

- Recommended dedicated route.
- Include processing times, shipping windows, carrier expectations, and international constraints if relevant.

### Support page

- Include support email, phone if offered, hours, response-time commitment, and issue categories.
- Optional contact form only if a real backend endpoint exists.
- Include links to refund, shipping, and tracking where relevant.

### Track-order page

- Dedicated route with a real lookup form.
- Must not ship as a dead-end placeholder page.
- Response should display order number, order state, fulfillment state, shipment list, carrier, tracking number, tracking URL, latest tracking event, and estimated delivery if available.
- If no shipment exists yet, show a truthful pre-fulfillment state and next expected milestone.

## Checkout and Commerce Behavior

Decision: use a single-CTA Medusa model. `Buy now` persists the cart in Medusa and goes straight to the Medusa checkout page, while the store also exposes a required slide-out cart drawer from the header. There is no dedicated `/cart` page.

### CTA rules

- `Buy now` resolves the active Medusa variant mapping, persists it into the cart, and routes to checkout immediately.
- CTA stays disabled until required selections are made.
- CTA enters loading state during cart persistence and checkout navigation.
- On success, navigate to the checkout route resolved by the B2C runtime.
- On failure, show a blocking inline error with retry. Do not silently fall back to another flow.

### Cart drawer rules

- Header cart button must be globally accessible and open the drawer from any scroll position.
- Drawer must show line items, product image, selected options, quantity controls, pricing summary, and a checkout CTA.
- Drawer must support remove-item and change-quantity actions.
- Drawer should expose `Continue shopping` and `Checkout` actions. Do not include a `View cart` action because no cart page exists.
- Cart badge count must stay synchronized with cart state.
- Cart state and the last returned `cartId` should persist so the drawer can be reopened after the checkout redirect or a return visit in the same browser context.

### Checkout sources

- `Buy now` should persist cart state and route to checkout from the current active selection in one action.
- Drawer `Checkout` should route to the checkout page using the current Medusa cart state.

### Existing Medusa alignment

- The current B2C runtime already exposes `loadProductByHandle`, `createCart`, `refreshCart`, `addToCart`, `updateCartItem`, `removeCartItem`, `navigateToCheckout`, and checkout mutation helpers.
- The starter should reuse these Medusa-facing primitives instead of inventing a separate commerce layer for the first version of the template.

### Template checkout payload requirements

- Map each visible offer choice to one or more Medusa variant ids and quantities.
- Support checkout routing from either the active PDP selection or the cart drawer state.
- Persist the returned `cartId` together with enough client state to render the cart drawer accurately on return.
- Include analytics and attribution attributes already used by funnel infrastructure.
- Support bundle mapping for single unit, multi-pack, and free-gift or bonus insertion if backend supports it.
- Keep Medusa ids out of presentational components where possible by isolating them in the commerce binding layer.

## Content Model

The template should stay config-driven like the existing sales template, but with a broader store-level schema.

| Config group | Purpose | Key fields |
| --- | --- | --- |
| `meta` | SEO and document metadata | `title`, `description`, `lang`, social image |
| `theme` | Design tokens and art direction | colors, fonts, radii, spacing, shadows, motion intensity |
| `brand` | Identity | name, logo, support identity, business name |
| `product` | Core merchandise data | name, subtitle, images, description, facts, disclaimers, Medusa handle |
| `offers` | Sellable choices | option groups, bundle definitions, recommended offer, compare-at price, Medusa variant mapping |
| `commerce` | Medusa wiring | backend config, country, region, cart behavior, checkout route behavior |
| `checkout` | Checkout page behavior | CTA labels, checkout copy, shipping and payment presentation |
| `proof` | Reviews and trust content | ratings, testimonials, badges, press, certifications |
| `policies` | Legal page content or references | privacy, terms, refund, shipping |
| `support` | Support operations | email, phone, hours, SLA, faq shortcuts |
| `tracking` | Order lookup config | lookup fields, endpoint, empty state copy, error copy |
| `analytics` | Event instrumentation | pixel IDs, event names, attribution metadata |

## Proposed Frontend Type Expansion

Define a starter binding config around the existing page systems instead of creating a new standalone page schema. The binding layer should feed the existing sales-page template, Medusa checkout page, and policy or contact templates with a shared one-product store configuration.

```ts
type OneProductStoreConfig = {
  meta: MetaConfig
  theme?: ThemeConfig
  brand: BrandConfig
  product: ProductConfig
  landingPage: LandingPageConfig
  offers: OfferConfig[]
  commerce: MedusaCommerceConfig
  checkout: CheckoutConfig
  policies: PolicyConfig
  support: SupportConfig
  tracking: TrackingConfig
  analytics?: AnalyticsConfig
  copy: UiCopy
}
```

This config should be consumed by the existing funnel-template layer, especially the sales-page and Medusa B2C page systems already registered through the Puck configuration, rather than a separate starter-only renderer.

## API Requirements

### Required now

- Medusa Store API configuration through `VITE_MEDUSA_BACKEND_URL` and `VITE_MEDUSA_PUBLISHABLE_KEY`.
- Product retrieval by handle for the bound one-product PDP.
- Cart create or retrieve, add line item, update line item, remove line item, and get cart totals.
- Checkout support for shipping options, payment providers or sessions, and complete-cart behavior.

### Starter runtime contract

- The template should consume the existing Medusa helper modules in `mos/frontend/src/lib/medusa`.
- The template should run under `B2CRuntimeProvider` so country, locale, cart, customer, and checkout state stay centralized.
- The product page should bind through `loadProductByHandle` and not duplicate Medusa fetch logic ad hoc.

### Required before shipping `/track-order`

- `POST /public/orders/lookup` or equivalent public lookup endpoint must accept order number plus email, or tracking number, and return order status, fulfillment data, shipment timeline, and tracking links.

### Recommended for support

- `POST /public/support/contact` should submit a support request and return a receipt id plus expected response window.

### Existing policy-page option

The repo already contains policy-page patterns in [`mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx`](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx). Reuse this idea for:

- privacy policy
- terms of service
- refund policy
- shipping policy
- contact support

## Analytics Events

Track at minimum:

- page view
- hero CTA click
- cart drawer opened
- cart item removed
- cart quantity changed
- cart persisted
- offer selected
- variant selected
- checkout started
- buy-now failed
- policy page viewed
- support link clicked
- support form submitted
- track-order submitted
- track-order success
- track-order failure

## SEO Requirements

- `/` is canonical.
- `/product` redirects to `/`.
- Unique metadata for policy and support pages.
- JSON-LD for product and FAQ only when merchant data is complete and valid.
- Avoid duplicate content between homepage and alias routes.

## Accessibility Requirements

- Keyboard-operable selectors, accordions, gallery, and sticky buy controls.
- Visible focus states on every interactive element.
- Screen-reader labels for rating summaries, media controls, and CTA states.
- Legal and support pages must be navigable without motion or hover assumptions.

## Performance Requirements

- Prioritize fast first paint on paid-traffic landings.
- Hero media optimized for mobile first.
- Sticky purchase UI must not degrade scroll performance.
- Defer non-critical review media below the fold.

## Compliance and Merchant Content Requirements

This template can support supplement-style stores, but compliance content must be merchant-provided and reviewed before launch.

- Do not ship default medical or disease claims.
- Provide configurable slots for supplement facts, dosage directions, warnings, allergen info, and disclaimers.
- Guarantee, refund, shipping, and subscription language must align across PDP, policies, and checkout-adjacent surfaces.
- Privacy and support links must always be visible in footer and checkout-related contexts.

## Implementation Notes Against Current Repo

- Reuse the existing sales-page system behind [`mos/backend/app/templates/funnels/sales_pdp.json`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/sales_pdp.json) and [`mos/frontend/src/funnels/templates/salesPdp/SalesPdpTemplate.tsx`](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/funnels/templates/salesPdp/SalesPdpTemplate.tsx) as the home or PDP base.
- Reuse the existing checkout page behind [`mos/backend/app/templates/funnels/medusa-b2c-checkout.json`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2c-checkout.json).
- Reuse the existing Medusa policy and contact templates for legal and support surfaces.
- Promote the template from a single rendered page to a small routed storefront composition, but do not replace the existing underlying page systems.
- Keep Medusa platform details behind a commerce adapter instead of spreading them through visual components.
- Reuse policy-page concepts already present in the main frontend where practical.
- Reuse the existing Medusa B2C runtime instead of building a parallel starter-specific cart or checkout stack.
- Treat order tracking as a hard dependency, not a soft placeholder.

## Phased Delivery

### Phase 1

- Canonical one-product PDP on `/`
- Medusa product, variant, cart, and checkout wiring
- offer and variant selection
- footer legal links
- privacy, terms, refund, and shipping routes

### Phase 2

- support route
- support form integration if backend exists
- improved trust and proof modules
- analytics instrumentation

### Phase 3

- real `/track-order` flow
- shipment timeline UI
- post-purchase support enhancements

## Open Decisions

- Should `/track-order` be powered by Medusa order data directly, MOS backend projections, or another fulfillment source?
- Will support be email-only at launch, or should the template assume a support form API?
- Are subscriptions in scope for v1 of this template?
- Should policy pages live in local config for template previews and switch to backend-managed content in production?
- Do we want the starter to support a non-Medusa checkout adapter later, or is Medusa the only supported commerce backend for v1?
