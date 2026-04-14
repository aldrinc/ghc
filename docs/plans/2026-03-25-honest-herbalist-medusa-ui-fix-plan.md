# Honest Herbalist Medusa UI Fix Plan

## Decision

Rebuild the Honest Herbalist `medusa-b2b-starter` experience as a starter-parity implementation inside the existing Marketi runtime.

Do not treat this as a CSS polish pass.

The current storefront is not the upstream Medusa B2B starter. It is a separate Puck-driven template family rendered through Marketi's public funnel runtime. Because of that architectural split, visual parity requires template and runtime changes, not isolated styling tweaks.

Recommended scope:

1. Reach strong visual parity for the shared storefront shell and core commerce pages.
2. Keep current runtime scope boundaries unless you explicitly authorize expanding them.
3. Error cleanly when required data or assets are missing instead of silently degrading into fallback UI.

## Goal

Make the Honest Herbalist store look and feel materially closer to the GitHub Medusa B2B starter while still running on Marketi's site/page runtime.

Success means:

- homepage composition reads like the starter, not like a generic editorial page
- header, promo strip, hero, rails, PDP, cart, and checkout share one coherent starter-like shell
- typography and spacing stop drifting toward the current Marketi default theme
- template generation for new Honest Herbalist rollout sites produces the corrected UI by default

## Non-Goals

- swapping the site over to the upstream Next.js storefront directly
- changing the Medusa backend or commerce provider
- inventing placeholder assets, fake products, fake collections, or fake reviews
- silently adding unsupported upstream features behind weak stand-ins

## Reference Baseline

Primary upstream reference:

- GitHub repo: [medusajs/b2b-starter-medusa](https://github.com/medusajs/b2b-starter-medusa)

Relevant local upstream snapshot already present in the repo:

- `/Users/aldrinclement/Documents/programming/marketi/.tmp/medusa-b2b-starter/storefront`

Key upstream files:

- home hero: `/Users/aldrinclement/Documents/programming/marketi/.tmp/medusa-b2b-starter/storefront/src/modules/home/components/hero/index.tsx`
- main shell layout: `/Users/aldrinclement/Documents/programming/marketi/.tmp/medusa-b2b-starter/storefront/src/app/[countryCode]/(main)/layout.tsx`
- nav: `/Users/aldrinclement/Documents/programming/marketi/.tmp/medusa-b2b-starter/storefront/src/modules/layout/templates/nav/index.tsx`
- featured collection rail: `/Users/aldrinclement/Documents/programming/marketi/.tmp/medusa-b2b-starter/storefront/src/modules/home/components/featured-products/product-rail/index.tsx`

## Current State

The current Honest Herbalist storefront is generated from the Marketi site family `medusa-b2b-starter` defined in [site_blueprints.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/site_blueprints.py#L57).

The Honest Herbalist home page is currently driven by [medusa-b2b-home.json](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2b-home.json#L1), which uses:

- a `CommerceStoreHeader`
- a generic `Columns` block
- generic `Heading`, `Text`, and `Button` blocks
- a `CommerceCategoryList`
- a `CommerceProductGrid`

That is fundamentally different from the upstream starter, which uses:

- a dedicated navigation shell
- a promo bar below the header
- a full-bleed image hero
- collection-based product rails
- starter-specific layout and typography primitives

## Root Cause Summary

### 1. The site family is a shell, not a clone

The site family descriptor explicitly says this Marketi implementation is a truthful shell based on the starter feature set, not the upstream storefront implementation itself.

Relevant file:

- [site_blueprints.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/site_blueprints.py#L48)

### 2. The home page uses generic editorial blocks

The homepage is composed from generic Puck blocks rather than starter-specific home components.

Relevant file:

- [medusa-b2b-home.json](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2b-home.json#L35)

### 3. The runtime shell only approximates the upstream header/footer

The local `CommerceStoreHeader` and `CommerceStoreFooter` are custom implementations that borrow some starter motifs, but they do not reproduce the upstream shell or feature layout.

Relevant file:

- [CommerceBlocks.tsx](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/commerce/CommerceBlocks.tsx#L2332)

### 4. Typography is coming from Marketi defaults, not Medusa starter styles

The generic `Heading` block renders with Marketi typography rules, and the design system defaults inject `Merriweather` as the heading font. That explains the serif-heavy appearance in the current storefront screenshot.

Relevant files:

- [puckConfig.tsx](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/funnels/puckConfig.tsx#L615)
- [base_tokens.json](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/design_systems/base_tokens.json#L1)
- [theme.css](/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/styles/theme.css#L1)

### 5. Scope parity and visual parity are not the same thing

The current site family intentionally excludes quote, approval, and account flows from scope. The upstream starter includes those broader B2B capabilities in its shell and navigation.

Relevant file:

- [site_blueprints.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/site_blueprints.py#L13)

That means:

- full visual shell parity is feasible
- full behavior parity is not feasible without explicit scope expansion

## Parity Gap Matrix

| Surface | Upstream starter | Current Honest Herbalist runtime | Gap | Required fix |
| --- | --- | --- | --- | --- |
| Header | brand, products nav, search, quote, login, cart | brand, category nav, optional search, cart | missing shell structure and action pattern | replace with starter-specific shell component |
| Promo strip | dark announcement strip under nav | absent | first-screen composition mismatch | add starter promo bar component |
| Home hero | full-bleed image hero with centered content | two-column text layout | wrong composition entirely | build dedicated starter hero block |
| Home merchandising | collection rails | category list + generic product grid | wrong data shape and spacing rhythm | build collection-rail block backed by real collections |
| Typography | Medusa UI / starter typographic feel | Marketi heading/text primitives with custom theme tokens | visual drift | constrain tokens and/or bypass generic primitives |
| Footer | starter footer columns with Medusa links | custom footer approximation | structure drift | replace with starter-specific footer variant |
| Category page | starter-like catalog shell and left rail | partial approximation | medium drift | tighten starter-specific category shell |
| PDP | stronger parity already, but still custom | custom approximation | moderate drift | tune layout, type, controls, and details sections |
| Cart / checkout | starter shell and spacing | custom runtime blocks in generic sections | moderate drift | normalize shell and spacing across pages |
| B2B actions | quote/login/account flows | mostly absent from site family | scope gap | only add with explicit authorization |

## Implementation Phases

### Phase 0: Freeze the Parity Target

### Outcome

The team has one explicit definition of "looks like the starter" before any code changes begin.

### Tasks

1. Capture current Honest Herbalist desktop and mobile screenshots for:
   - home
   - category
   - PDP
   - cart
   - checkout
2. Capture matching upstream reference screenshots from the local upstream snapshot or a running copy.
3. Create a compact parity checklist covering:
   - header structure
   - promo bar presence
   - hero composition
   - section order
   - rail/grid structure
   - footer structure
   - major typography behavior
4. Decide whether this fix targets:
   - visual shell parity only
   - visual shell parity plus quote/login/account parity

### Recommendation

Use visual shell parity only for the first pass.

Reason:

- it achieves the user-visible fix
- it stays inside current site-family scope
- it avoids dragging backend and workflow features into a UI repair project

### Phase 1: Introduce Starter-Specific Runtime Components

### Outcome

The site family has purpose-built components for starter parity instead of depending on generic editorial blocks.

### Tasks

1. Split starter-specific storefront UI out of the generic commerce surface in:
   - `/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/commerce/CommerceBlocks.tsx`
2. Add dedicated components for:
   - `StarterStoreHeader`
   - `StarterPromoBar`
   - `StarterHomeHero`
   - `StarterCollectionRails`
   - `StarterStoreFooter`
3. Keep existing generic commerce components for non-starter use cases.
4. Register the starter-specific blocks in:
   - `/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/funnels/puckConfig.tsx`
5. Ensure each new component fails clearly when required runtime data is missing.

### Important rule

Do not hide missing collections, hero media, or required config behind fake placeholders.

Preferred behavior:

- render a clean configuration error in authoring and preview contexts
- render a minimal honest error state in public runtime if the configuration is broken

### Phase 2: Rebuild the Homepage Around Starter Composition

### Outcome

The homepage stops looking like a generic content page and starts reading like the upstream starter.

### Tasks

1. Replace the generic home body in [medusa-b2b-home.json](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2b-home.json#L35) with starter-specific blocks.
2. Update the section order to:
   - starter header
   - starter promo bar
   - starter hero
   - starter collection rails
   - optional category support section if explicitly wanted
   - starter footer
3. Back home merchandising with real Medusa collections, not categories.
4. Support a real hero image source for Honest Herbalist.
5. Decide whether Honest Herbalist uses:
   - the upstream artwork exactly
   - its own real branded hero asset in the same composition pattern

### Recommendation

Use Honest Herbalist branding and imagery in the same composition pattern, not the exact Medusa demo image.

Reason:

- the user asked for the store to look like the starter template
- they did not ask to ship Medusa demo branding or demo content
- parity should apply to structure, spacing, and shell, not Medusa demo brand content

### Phase 3: Normalize the Shared Shell Across Category, PDP, Cart, and Checkout

### Outcome

All core storefront pages feel like one system instead of separate custom layouts.

### Tasks

1. Update all page templates to use the same starter shell:
   - [medusa-b2b-category.json](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2b-category.json#L1)
   - [medusa-b2b-pdp.json](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2b-pdp.json#L1)
   - [medusa-b2b-cart.json](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2b-cart.json#L1)
   - [medusa-b2b-checkout.json](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2b-checkout.json#L1)
2. Use one consistent:
   - header
   - promo bar policy
   - page width
   - vertical spacing scale
   - footer
3. Tune category layout so the left rail, grid, and breadcrumbs feel closer to starter behavior.
4. Tighten PDP spacing, gallery weight, product info hierarchy, and control styling to reduce drift.
5. Align cart and checkout surface spacing so they no longer read like generic forms inside generic sections.

### Phase 4: Constrain Design System and Typography Drift

### Outcome

Starter pages are no longer dominated by Marketi-global type and theme defaults.

### Tasks

1. Audit how `DesignSystemProvider` tokens are applied on public storefront pages.
2. Define a site-family-level rule for `medusa-b2b-starter` token application.
3. Restrict tokens on starter pages to fields that are safe for parity:
   - store name
   - logo
   - select colors
   - possibly one accent
4. Prevent starter shell components from inheriting the generic `Heading` block visual language where that breaks parity.
5. Decide whether starter pages should:
   - use their own local typography classes
   - or use a starter-scoped token preset distinct from `base_tokens.json`

### Recommendation

Use starter-scoped component styles for the shell and merchandising surfaces.

Reason:

- the generic `Heading` and `Text` primitives are designed for broad reuse
- starter parity is highly composition-specific
- this avoids fighting the existing design-system stack every time tokens change

### Phase 5: Data and Configuration Requirements

### Outcome

The rebuilt storefront has a clear contract for the real data it needs.

### Required real inputs

- at least one real hero image or approved branded visual
- real Medusa collections for home rails
- real categories for nav and category browsing
- real product thumbnails for rails and PDP
- real store title and brand labeling

### Tasks

1. Verify that Honest Herbalist data in Medusa includes usable collections.
2. If not, decide whether to:
   - create real collections in Medusa
   - or intentionally change the home merchandising spec away from collection rails
3. Add validation so starter home publishing errors clearly if required data is missing.
4. Keep errors operator-friendly and explicit.

### Example failure messages

- `Starter home requires at least one collection to render collection rails.`
- `Starter home requires a hero image asset for the configured brand.`
- `Starter shell search was requested but no search integration is configured.`

### Phase 6: Decide on Search, Quote, Login, and Account Scope

### Outcome

The plan stays honest about what will and will not match upstream.

### Current limitation

The current site-family scope excludes quote, approval, and account flows. Upstream includes those capabilities in the shell and broader starter experience.

### Decision options

#### Option A: Visual shell parity only

Implement:

- search input visual shell
- starter-like action slots
- cart button

Do not implement:

- live search
- quote flow
- account flow

Recommendation:

- best first pass

#### Option B: Full header action parity

Implement:

- quote
- login/account
- any required supporting routes and state

Cost:

- materially larger project
- spills into backend and workflow scope

### Recommendation

Choose Option A unless you explicitly want the full B2B action surface.

### Phase 7: Add Regression Tests

### Outcome

The corrected storefront does not drift back after later template or token changes.

### Tasks

1. Add Playwright coverage for public funnel storefront routes using the existing frontend test setup in:
   - `/Users/aldrinclement/Documents/programming/marketi/mos/frontend/package.json`
2. Add tests for:
   - home renders starter hero
   - promo bar exists
   - header structure exists
   - home renders collection rails, not just a generic product grid
   - category page renders starter shell
   - PDP renders expected starter-aligned structure
3. Add screenshot assertions for:
   - home desktop
   - home mobile
   - PDP desktop
4. Keep assertions focused on layout landmarks, not brittle pixel-level trivia.

### Phase 8: Regenerate and Republish the Honest Herbalist Site

### Outcome

The live Honest Herbalist rollout site is rebuilt from corrected templates.

### Tasks

1. Update the built-in template files.
2. Recreate the rollout site through the existing sync script and site creation flow:
   - `/Users/aldrinclement/Documents/programming/marketi/mos/backend/scripts/sync_honest_herbalist_to_medusa.py`
3. Verify the newly generated site uses the corrected starter-specific templates.
4. Validate desktop and mobile before any wider rollout.

### Why this works

The sync script already:

- archives old sites
- creates a fresh `medusa-b2b-starter` site
- publishes through the canonical flow

That makes it the right regeneration path once the templates are corrected.

## File Touch Map

| Area | Likely files |
| --- | --- |
| Site family template definitions | `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2b-home.json`, `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2b-category.json`, `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2b-pdp.json`, `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2b-cart.json`, `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/funnels/medusa-b2b-checkout.json` |
| Starter-specific frontend blocks | `/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/commerce/CommerceBlocks.tsx` or a new starter-specific module beside it |
| Puck block registration | `/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/funnels/puckConfig.tsx` |
| Token / theme boundary | `/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/design-system/DesignSystemProvider.tsx`, `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/templates/design_systems/base_tokens.json`, possibly starter-scoped theme files |
| Public runtime validation | `/Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/public/PublicFunnelPage.tsx` |
| Site regeneration | `/Users/aldrinclement/Documents/programming/marketi/mos/backend/scripts/sync_honest_herbalist_to_medusa.py` |
| E2E verification | `/Users/aldrinclement/Documents/programming/marketi/mos/frontend/playwright.config.ts` plus new Playwright specs |

## Acceptance Criteria

The UI fix is done when all of the following are true:

1. The Honest Herbalist homepage uses a full starter-style hero, not the current two-column editorial section.
2. The storefront shows a starter-style top shell with a visible promo strip and corrected header rhythm.
3. Home merchandising is based on real collection rails or another explicitly approved starter-aligned structure.
4. Category, PDP, cart, and checkout share one coherent shell and spacing system.
5. Starter pages no longer inherit serif-heavy generic heading behavior by accident.
6. Required missing data causes clear errors, not fake placeholder content.
7. A newly regenerated Honest Herbalist rollout site matches the corrected design.
8. Playwright parity checks pass for the main storefront routes.

## Risks

### Risk 1: Collections are missing or weak

Impact:

- home rail parity will be blocked or compromised

Mitigation:

- verify collection data before implementation
- fail clearly if the data contract is not met

### Risk 2: Generic tokens keep leaking into starter pages

Impact:

- ongoing visual drift even after component rewrites

Mitigation:

- isolate starter shell styles from generic page primitives

### Risk 3: Header parity expands into backend scope

Impact:

- project balloons into quote/account feature work

Mitigation:

- freeze scope on visual shell parity unless explicitly expanded

### Risk 4: Template corrections do not propagate to existing rollout sites

Impact:

- code looks fixed, public site still looks wrong

Mitigation:

- regenerate the site after template changes using the existing sync flow

## Recommended Execution Order

1. Freeze parity targets and screenshots.
2. Build starter-specific shell components.
3. Rebuild the homepage template around starter hero plus collection rails.
4. Normalize category, PDP, cart, and checkout around the same shell.
5. Constrain token and typography drift.
6. Add E2E parity tests.
7. Regenerate and verify the Honest Herbalist rollout site.

## Final Recommendation

Treat this as a starter-family correction project, not a one-off Honest Herbalist restyle.

The best implementation is:

1. introduce starter-specific blocks and shell components
2. update the `medusa-b2b-*` built-in templates to use them
3. regenerate Honest Herbalist from those corrected templates

That gives you:

- the fastest path to visible parity
- a reusable fix for future `medusa-b2b-starter` rollouts
- less long-term drift than trying to force generic Puck primitives to impersonate the upstream starter
