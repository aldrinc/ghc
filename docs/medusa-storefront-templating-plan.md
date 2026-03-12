# Medusa Storefront Templating, Styling, and Import Plan

## Goal

Replace the Shopify theme-centric model with a headless template system that uses:

- MOS for template authoring, page composition, design systems, assets, AI-assisted iteration, preview, and deployment.
- Medusa for commerce data and operations: products, variants, pricing, promotions, carts, checkout, orders, inventory, regions, and fulfillment.

The main requirement is speed:

- We need to import strong reference sites rapidly.
- We need to turn them into reusable templates instead of one-off custom builds.
- We need to iterate toward winning store layouts without rebuilding a theme from scratch each time.

## What We Already Have And Should Reuse

The repo already contains the foundation for a stronger system than Shopify themes:

- Puck-based page structures and runtime rendering in `mos/frontend/src/funnels/puckConfig.tsx` and `mos/frontend/src/pages/public/PublicFunnelPage.tsx`.
- Reusable page templates stored as structured `puckData` in `mos/backend/app/templates/funnels/`.
- Existing high-fidelity reference templates:
  - `sales_pdp.json`
  - `pre_sales_listicle.json`
- Design-system token generation and materialization in `mos/backend/app/services/design_system_generation.py`.
- Deterministic design-system auditing in `docs/design-system-generation-audit.md`.
- Template asset ingestion and logo replacement in `mos/backend/app/services/funnel_templates.py`.
- AI page editing that preserves template structure in `docs/funnel-ai-agent.md`.
- Static/storefront deployment primitives already used for funnel publication.

The correct move is to generalize this into a store templating system, not to recreate Shopify theme workflows in a new stack.

## Core Decision

Do **not** treat Medusa templates as raw storefront code checked into each workspace.

Treat templates as a layered system:

1. **Template family**
   - The structural blueprint for a page type.
   - Example: `sales-pdp`, `listicle-presell`, `home-ugc`, `collection-story`, `cart-offer-stack`.

2. **Design system**
   - Workspace-level tokens for typography, color, spacing, radii, shadows, CTA treatments, and section surfaces.

3. **Page instance**
   - The concrete page content, media, merchandising choices, and block ordering for a specific workspace or test variant.

4. **Commerce bindings**
   - The runtime mapping from page blocks to Medusa data: product, variant, collection, promotion, inventory, region, shipping estimate, review feed, and checkout actions.

This is much more robust than copying HTML/CSS from a reference site and trying to maintain it forever.

## Target System Ownership

| Concern | System |
| --- | --- |
| Template authoring and page composition | MOS |
| Design tokens and style governance | MOS |
| Template import pipeline | MOS |
| Product/catalog/pricing/inventory/order data | Medusa |
| Checkout and order completion | Medusa |
| Reviews/testimonials rendering | MOS + review data source |
| Compliance/policy page generation | MOS |
| Storefront deployment and preview | MOS deploy pipeline |

## Storefront Runtime Choice

MOS should remain the primary rendering and authoring layer for storefront pages.

Medusa should be treated as:

- the commerce backend
- the source of catalog and checkout truth
- the admin/operations surface for commerce workflows

Medusa should **not** become the primary template-authoring surface.

If we use a Medusa starter at all, it should be for:

- commerce integration patterns
- account/order-history patterns
- starter shell references

It should not replace the MOS page/template system.

## How Templating Should Work In The New System

### 1. Unify funnels and store pages into one template engine

We should stop thinking in separate buckets like "funnels" versus "store theme".

We should support a single authoring model for:

- Home pages
- PDPs
- Collection pages
- Cart/upsell pages
- Policy pages
- Advertorial and pre-sell pages
- Launch pages and seasonal variants

All of them should be composed from structured page blocks in MOS, with Medusa supplying commerce data.

### 2. Introduce template families and variants

Each template family should define:

- `template_id`
- `family`
- `version`
- supported page type
- required data bindings
- exposed configuration slots
- locked layout rules
- unlocked style tokens
- import provenance

Each family can then have many variants:

- `sales-pdp / bold-proof`
- `sales-pdp / premium-editorial`
- `collection / before-after-grid`
- `home / founder-led`

This gives fast iteration without forking the entire storefront codebase.

### 3. Separate layout locks from style overrides

The current templates already hint at the right model:

- template defaults define baseline geometry and component behavior
- design-system tokens override approved CSS variables
- some CSS variables remain locked so templates do not collapse visually

We should formalize that with three style layers:

1. **Base tokens**
   - shared schema from `base_tokens.json`

2. **Template default tokens**
   - the visual assumptions that make a template family coherent

3. **Workspace/page overrides**
   - brand-specific colors, fonts, surfaces, CTA colors, section accents, and limited page-specific overrides

No free-form CSS editing should be part of the primary workflow.
If custom CSS is needed, it should be an explicit escape hatch with audit and review, not the default authoring path.

### 4. Bind store blocks to Medusa data contracts

Each store-capable block should declare its data contract.

Examples:

- `ProductHero` needs product, selected variant, gallery, badges, guarantee, offer cards, and checkout action.
- `CollectionGrid` needs collection handle, sort mode, card style, and product summary fields.
- `StickyOfferBar` needs selected variant, compare-at pricing, promotion text, and CTA behavior.
- `PolicyPage` needs generated markdown/html content and page metadata.

At runtime, MOS should resolve those bindings through a Medusa adapter layer instead of embedding store-specific logic into every template.

## How Styling Should Work

### Design-system approach

We already have the right primitives:

- a base token template
- token materialization
- token validation
- runtime audit

Extend that to the store system instead of replacing it.

### Style policy

- Every template consumes the same canonical token schema.
- Templates may define extra optional tokens, but not ad hoc names that drift by workspace.
- Typography, spacing, surface colors, and CTA styles come from tokens.
- Components read tokens first, then template defaults, then optional page overrides.
- Tokens are audited before publication.

### Font policy

- Workspace fonts are part of the design system.
- Imported reference sites should produce a suggested font stack and scale, not direct CSS copies.
- We should only persist approved font URLs plus normalized heading/body/CTA assignments.

### Visual safety rails

Before a design system or imported template can publish:

- token schema must validate
- contrast checks must pass
- accent overuse checks must pass
- template-specific slot requirements must pass
- commerce bindings must resolve

The system should error with explicit reasons instead of silently falling back.

## Robust Template Import Plan

The import pipeline should be **structure-first and tokenized**, not "save somebody else's HTML blob".

### Import modes

We should support three import modes:

1. **Theme extraction**
   - Pull palette, typography, spacing feel, section treatments, CTA style, and visual rhythm from a reference site.
   - Output: design-system candidate + style notes.

2. **Pattern extraction**
   - Pull selected sections from a reference site.
   - Output: reusable blocks or block compositions.

3. **Template synthesis**
   - Pull the layout system of one or more reference pages and map it into a reusable MOS template family or variant.
   - Output: `puckData` template variant + assets + token preset + import provenance.

### Import intake

Operator supplies:

- source URLs
- target page types
- target workspace
- whether assets may be retained as-is or must be replaced
- notes on what should be copied:
  - layout
  - typography
  - hierarchy
  - proof strategy
  - CTA structure
  - navigation
  - PDP purchase box logic

### Import pipeline steps

#### Step 1: Capture bundle

Create a new backend import worker that uses Playwright to capture:

- desktop and mobile screenshots
- HTML snapshot
- DOM tree
- computed styles for key nodes
- color palette candidates
- font families and weights
- spacing rhythm
- image URLs
- section boundaries
- CTA placements
- nav/footer structure

Output artifact: `SiteImportBundle`

This should reuse the same browser inspection style already used by the design-system audit.

#### Step 2: Normalize into canonical sections

Parse the captured page into a section model:

- hero
- proof bar
- feature stack
- comparison table
- testimonial wall
- FAQ
- sticky offer rail
- footer
- collection grid
- bundle selector

Each section gets:

- section type guess
- screenshot crop
- DOM subset
- key text
- key media
- key styles
- component confidence score

#### Step 3: Match to existing block library

Try to map each normalized section onto an existing MOS block or template composition.

Outcomes:

- exact match
- partial match with slot mapping
- no acceptable match

If no acceptable match exists, create a **new block request**, not raw HTML import.
This is the most important rule in the whole system.

We should import references into our component language, not adopt the reference site's implementation language.

#### Step 4: Extract a token candidate

Generate a design-system candidate from the reference:

- brand/heading/body/CTA font choices
- primary and secondary colors
- surface strategy
- border/radius/shadow style
- spacing density
- section contrast pattern

Then materialize it onto the canonical token schema and run the design-system audit.

#### Step 5: Ingest assets with provenance

For every image or icon we keep:

- store original URL
- record import timestamp
- hash and dedupe
- tag workspace + import job
- mark whether asset is approved for reuse or requires replacement

For every image we cannot keep:

- create a replacement task
- regenerate or replace with workspace-owned asset before publication

#### Step 6: Synthesize template variant

Generate a new template variant as structured `puckData`:

- chosen template family
- ordered blocks
- populated default props
- slot placeholders
- imported assets
- commerce binding definitions
- style preset reference

This is the deliverable that matters, not the raw captured HTML.

#### Step 7: Human review and repair

Provide an internal review UI with:

- desktop/mobile reference screenshots
- rendered MOS preview
- block-by-block diff
- token diff
- missing-slot list
- binding validation results

Reviewer actions:

- accept/reject sections
- remap sections
- replace assets
- lock/unlock style tokens
- save as workspace-local or global template variant

#### Step 8: Variant generation

Once a template variant exists, MOS should generate fast derivatives:

- new headline hierarchy
- alternate proof density
- alternate CTA emphasis
- alternate product media ordering
- alternate comparison-module placement
- alternate testimonial mix

This is where velocity comes from.
Import once, iterate many times.

## "Other Things" We Need To Handle In The New System

### Reviews and testimonial media

- Keep MOS as the place where testimonial assets are rendered and curated.
- Treat review walls, UGC cards, before/after strips, and social proof modules as portable template blocks.
- Bind them to workspace review data instead of hardcoding them into imported pages.

### Compliance and policy pages

- Keep policy generation in MOS.
- Publish policy pages as structured pages in the same template system.
- Do not rebuild a Shopify-like page-sync workflow.

### Navigation and collection merchandising

- Collections, sorting, badges, inventory messaging, and pricing come from Medusa.
- The visual shell for those experiences stays in MOS templates.

### Search and category landing pages

- Search results pages and collection pages should use the same section/block system.
- They should not live as a separate "theme-only" codepath.

### Preview and publish

- Every template variant must support:
  - workspace preview
  - draft publish
  - production publish
  - rollback

Use the existing MOS publish/deploy workflow as the delivery mechanism.

## Proposed New Backend Components

- `app/services/site_imports.py`
  - import orchestration
- `app/services/site_import_capture.py`
  - Playwright capture
- `app/services/site_import_normalize.py`
  - section extraction and normalization
- `app/services/template_synthesis.py`
  - build `puckData` template variants from normalized sections
- `app/services/medusa_storefront_bindings.py`
  - resolve Medusa data contracts for runtime
- `app/routers/site_imports.py`
  - import job APIs

## Proposed New Data Model

- `site_imports`
  - workspace, source URL, status, provenance, reviewer
- `site_import_snapshots`
  - screenshots, DOM snapshots, computed-style bundles
- `template_variants`
  - family, version, source import, visibility, status
- `template_bindings`
  - block-level Medusa data contracts
- `template_style_presets`
  - token presets linked to imports or manual variants

## Frontend Changes

- Add a `Store Templates` workspace area.
- Add an `Import Reference Site` flow.
- Add a `Template Review` screen.
- Extend the Puck editor to support:
  - store page types
  - binding validation
  - token preset switching
  - block coverage diagnostics

## Recommended Rollout Phases

### Phase 1: Foundation

- Generalize current funnel templates into shared template families.
- Add Medusa runtime binding layer.
- Ship store-capable page types: home, PDP, collection, policy.

### Phase 2: Import pipeline MVP

- Capture screenshots + DOM + computed styles.
- Build theme extraction and pattern extraction.
- Allow reviewers to convert imports into workspace-local variants.

### Phase 3: Template synthesis

- Map imports into structured `puckData`.
- Add block coverage scoring.
- Add missing-block request generation.

### Phase 4: Variant engine

- Generate multiple store variants from one imported template family.
- Add conversion-focused mutation presets for testing.

### Phase 5: Governance and scale

- Add provenance records
- Add asset approval rules
- Add stronger style audits
- Add publish gates

## Non-Goals

- Raw one-click cloning of arbitrary websites directly into production.
- Supporting uncontrolled custom CSS as the default authoring mode.
- Recreating the Shopify theme editor.
- Maintaining a separate "theme stack" and "funnel stack".

## Relevant Medusa References

- Medusa product overview: <https://medusajs.com/>
- Documentation hub: <https://docs.medusajs.com/>
- Next.js starter storefront: <https://docs.medusajs.com/resources/nextjs-starter>
- Custom modules: <https://docs.medusajs.com/learn/fundamentals/modules>
- Admin customizations: <https://docs.medusajs.com/ui/installation/medusa-admin-extension>
- Workflows reference: <https://docs.medusajs.com/resources/medusa-workflows-reference>
- Stripe payment provider: <https://docs.medusajs.com/resources/commerce-modules/payment/payment-provider/stripe>

## Final Recommendation

The new system should be:

- **component-driven**
- **token-driven**
- **binding-driven**
- **import-assisted**
- **variant-friendly**

The right mental model is:

> import reference sites into a structured template language, then iterate through reusable template families and design systems.

That gives us speed without inheriting brittle source-code debt from every reference site we admire.
