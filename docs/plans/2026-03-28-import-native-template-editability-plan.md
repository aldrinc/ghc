# Import-Native Template Editability Plan

## Decision

New imports should not be coerced into legacy template families like Sales PDP or Pre-sales Listicle.

Each new import should create its own first-party imported template with:

- an LLM-generated page name
- clear, template-specific section names
- stable section ids derived from the imported output
- section-level semantic tags like `hero`, `faq`, `comparison`, `offer`, `footer`
- editable first-party Puck content inside each section

The import path should preserve what the imported page actually is, not map it onto an old family that happens to look similar.

## Why The Current Model Fails

The current system breaks editability at the architectural level:

- archive imports currently terminate as a runtime block instead of first-party editable content
- legacy family synthesis pushes new imports into old component contracts
- the editor only works well when blocks have stable first-party fields, slots, and validation rules
- the current Funnel AI flow assumes either generic primitives or a known legacy template family

That is why the imported page can render, but editing the real section content remains brittle or impossible.

## Goals

- Imported pages should show up in `My Sites` as normal editable sites.
- The section outline should reflect the imported page's actual sections with clear names.
- Buttons, FAQs, comparisons, offer cards, images, galleries, and testimonial rows should be directly editable.
- The AI assistant should edit imported templates through the same funnel-AI workflow pattern already used in MOS.
- No opaque runtime iframe should be the saved editable artifact.
- No silent fallback to a legacy template family.

## Non-Goals

- Do not generate arbitrary React component code per import.
- Do not preserve raw screenshot-to-code JSX as the editor source of truth.
- Do not rely on `SalesPdp*` or `PreSales*` blocks for new imports.

## Target Editing Model

### 1. Imported Page Shell

Every imported page should materialize into a first-party Puck root:

- `ImportedPage`

`ImportedPage` owns:

- `pageName`
- `pageSlug`
- `pageRole`
- `themeTokens`
- `sections`

It should be the only top-level block in `puckData.content`, exactly the way legacy families use `SalesPdpPage` or `PreSalesPage` today.

### 2. Imported Section Wrapper

Every imported source section should become an `ImportedSection`.

Each `ImportedSection` should store:

- `id`: stable Puck id
- `sourceSectionId`: stable id from imported source, such as `product-purchase-section`
- `sectionKey`: stable slug used by AI and validation, such as `flavor_bundle_selector`
- `displayName`: clear human label, such as `Flavor And Bundle Selector`
- `semanticTags`: list like `["offer", "bundle-selector", "purchase"]`
- `layout`: section-level layout config
- `content`: slot containing editable child nodes

The section identity should be specific to the template. Semantic tags should help classification, but should not replace the template-specific display name.

### 3. Editable Child Primitives Inside Sections

Actual editing happens inside the section, not on an opaque blob.

Each section should be translated into first-party child primitives. Reuse existing generic blocks where they fit, and add a small import-native primitive set where current primitives are too weak.

Recommended primitive set:

- `Heading`
- `Text`
- `Image`
- `Button`
- `Columns`
- `List`
- `StatRow`
- `Accordion`
- `ComparisonTable`
- `ReviewGrid`
- `VideoGrid`
- `Gallery`
- `OfferSelector`
- `LinkGroup`
- `IconList`

The section wrapper gives identity. The child primitives give editability.

## How Actual Content Editing Works

### Buttons

Buttons should never be trapped inside raw HTML or JSX strings.

Each button becomes a first-party node with explicit props:

- `label`
- `variant`
- `size`
- `width`
- `align`
- `linkType`
- `href`
- `targetPageId`
- `trackingKey`
- optional `boundOfferId`

This makes the editor and AI assistant able to:

- rename the CTA
- change its visual style
- swap from external link to internal page link
- bind the CTA to a workspace offer
- move or duplicate the CTA

Commerce-sensitive behavior should stay bound. For example, a purchase CTA can change label and layout, but should not invent a fake `productOfferId`.

### Offer Cards And Bundle Selectors

The imported purchase section should become an `OfferSelector` with explicit option objects rather than a single legacy config blob.

Each offer option should expose fields like:

- `id`
- `title`
- `subtitle`
- `price`
- `compareAt`
- `saveLabel`
- `image`
- `isDefault`
- `boundOfferId`
- `ctaLabel`

This lets a human or the AI assistant edit:

- tier names
- helper copy
- badge text
- CTA labels
- image assignment
- display order

without losing the actual offer binding to workspace commerce data.

### FAQ Sections

An imported FAQ section should become:

- `ImportedSection(displayName="Pre-Purchase FAQ", semanticTags=["faq"])`
- child `Accordion`

Each FAQ item should be a real array entry with:

- `question`
- `answer`

That gives direct editing for:

- changing questions
- rewriting answers
- reordering items
- adding or removing entries

### Comparison Sections

A comparison section should become a `ComparisonTable` or `ComparisonGrid` primitive with explicit rows and columns:

- `title`
- `columns`
- `rows`

Each row should remain fully editable.

### Review And Testimonial Sections

Review sections should become structured `ReviewGrid` or `VideoGrid` nodes with repeatable items:

- `quote`
- `author`
- `subLabel`
- `image`
- `video`
- `rating`

These should not be hidden inside a single template config blob unless the block is still structurally editable at the item level.

### Footer Sections

Footer sections should become:

- copyright text
- link groups
- payment icon row
- optional logo/media

All as explicit child nodes or explicit structured props.

## Naming Model

The naming system should be dynamic and LLM-assisted.

The LLM should generate:

- `templateName`
- `pageName`
- `displayName` per section
- `sectionKey` per section
- `semanticTags` per section

Suggested rule set:

- `pageName` should be short and human-readable
- `displayName` should describe the actual function of the section, not use a generic placeholder
- `sectionKey` should be deterministic and slug-safe
- `semanticTags` should be a short controlled list

Example:

- source id: `product-purchase-section`
- display name: `Flavor And Bundle Selector`
- section key: `flavor_bundle_selector`
- semantic tags: `["offer", "bundle-selector", "purchase"]`

The editor should show `Flavor And Bundle Selector`, not `generic_content`, and not `SalesPdpHero`.

## Translation Pipeline

### Stage 1. Source Extraction

Keep the current archive extraction path for:

- ordered source sections
- source section ids
- `keyText`
- `keyMedia`
- `parsedData`
- theme candidate tokens

This is already the right raw material.

### Stage 2. Import Blueprint

Add a new import-blueprint pass that takes the extracted sections and produces:

- template metadata
- page metadata
- section identities
- semantic tags
- layout intent
- field-level translation targets

The blueprint is the contract between import analysis and Puck generation.

### Stage 3. Puck Translation

Translate each section into:

- `ImportedSection`
- nested first-party primitives

This translation should detect common imported structures such as:

- hero copy stacks
- CTA rows
- image galleries
- bundle selectors
- FAQ arrays
- comparison rows
- testimonial cards
- footer link groups

If a section contains something unsupported, the import should fail cleanly with a section-scoped error. It should not quietly fall back to a runtime blob.

## Data Shape For Imported Templates

Recommended section payload:

```json
{
  "type": "ImportedSection",
  "props": {
    "id": "sec_01",
    "sourceSectionId": "product-purchase-section",
    "sectionKey": "flavor_bundle_selector",
    "displayName": "Flavor And Bundle Selector",
    "semanticTags": ["offer", "bundle-selector", "purchase"],
    "layout": {
      "bandWidth": "bleed",
      "contentWidth": "xl",
      "surface": "none",
      "padY": "lg",
      "padX": "md"
    },
    "content": [
      {
        "type": "Heading",
        "props": {
          "id": "heading_purchase_title",
          "text": "OMNI Creatine Gummy",
          "level": 1,
          "align": "left"
        }
      },
      {
        "type": "OfferSelector",
        "props": {
          "id": "offer_selector_main",
          "title": "Choose flavor and bundle size",
          "options": []
        }
      },
      {
        "type": "Button",
        "props": {
          "id": "cta_primary",
          "label": "Add to Cart",
          "variant": "primary",
          "width": "full",
          "boundOfferId": "offer_123"
        }
      }
    ]
  }
}
```

This is the level where editing actually becomes possible.

## How Funnel AI Should Work With Imported Templates

### Current Funnel AI Pattern

Today, the editor AI sends the current page `puckData` to the backend and the backend returns updated `puckData`, which the editor loads directly. That loop is already implemented in:

- `mos/frontend/src/funnels/puckAiPlugin.tsx`
- `mos/backend/app/services/funnel_ai.py`
- `mos/backend/app/agent/funnel_tools.py`

That pattern should stay. The page structure it edits should change.

### New Template Kind

Add a new template mode:

- `templateKind = "imported-template"`

The AI system prompt should get imported-template-specific structure guidance:

- `ImportedPage` is the only top-level block
- `ImportedSection` blocks live inside `ImportedPage.props.content`
- preserve section order and section ids unless the user explicitly asks to reorder
- preserve `sectionKey`, `sourceSectionId`, and semantic tags unless the user explicitly asks to rename them
- only use allowed import-native primitives
- do not invent new component types

### AI Context Payload

The assistant should receive more than raw `puckData`. It should also receive a template manifest:

- `templateName`
- `pageName`
- ordered section manifest
- allowed child primitives per section
- stable node ids and semantic roles
- commerce bindings
- media bindings

That gives the model enough context to make targeted edits without guessing.

### AI Editing Granularity

The AI assistant should be able to edit at three levels.

#### Page-level

- rename page
- update root title/description
- reorder sections when explicitly requested

#### Section-level

- rename section display name
- rewrite section copy
- add or remove FAQ items
- update benefit bullets
- change section layout tokens
- reorder section-internal content

#### Node-level

- rename a button
- change button destination
- change image alt text or prompt
- replace an offer badge
- edit a comparison row
- edit a review card
- update a footer link label

### Recommended AI Contract

The current full-page `puckData` response can still work, but imported templates will be safer if the AI operates through structured mutations instead of blind full-page rewrites.

Recommended mutation contract:

- `rename_page`
- `update_section_meta`
- `replace_section_content`
- `insert_node`
- `update_node_props`
- `remove_node`
- `reorder_nodes`

The backend can then apply those operations deterministically to the stored `puckData`.

This is better than raw whole-page regeneration because:

- section ids remain stable
- node ids remain stable
- smaller AI changes are easier to validate
- button bindings and offer bindings are harder to break

### Short-Term Compatibility Path

To avoid blocking rollout, the current Funnel AI whole-page response contract can be kept initially, but the prompt and validation rules must understand `imported-template`.

That means:

- the plugin can still send `currentPuckData`
- the backend can still return updated `puckData`
- validation must check imported-template rules instead of Sales PDP rules

## Validation Rules

Imported templates need their own validator.

Required checks:

- top-level block must be `ImportedPage`
- section children must all be `ImportedSection`
- every section must keep `sourceSectionId`
- every section must keep `sectionKey`
- every section must have `displayName`
- only allowed child primitive types may appear
- no unknown component types
- button targets must be valid
- bound commerce ids must reference real workspace entities
- no placeholder runtime section blocks

Optional warnings:

- section renamed but semantic tags unchanged
- orphan node ids
- section has no editable child nodes

## Editor UX Requirements

The page editor should present the imported template clearly:

- left outline shows actual section names
- breadcrumb uses the LLM-generated page name
- selecting a section shows section metadata and layout controls
- selecting a child primitive shows actual fields for that node
- AI assistant can target either the whole page, a named section, or a named node

Example editor outline:

- Brand Intro Hero
- Evidence Marquee
- Flavor And Bundle Selector
- Customer Results Grid
- Why OMNI Comparison
- Pre-Purchase FAQ
- Footer Links

That is the reviewable, editable object model.

## Storage And Provenance

The source zip should remain provenance, not runtime.

Store separately:

- original archive metadata
- source section extraction output
- import blueprint
- translated Puck data
- translation warnings/errors

Do not make the saved editable site depend on replaying the imported runtime.

## Suggested Implementation Plan

### Phase 1. Import-Native Blueprint

- add `imported-template` as a first-class template mode
- build blueprint generation from imported sections
- store page name, section names, tags, and section keys

### Phase 2. Puck Translation

- add `ImportedPage`
- add `ImportedSection`
- add import-native primitives
- translate archive sections into editable Puck trees

### Phase 3. Site Creation

- create `My Sites` entries directly from translated imported-template Puck data
- remove archive save paths that depend on runtime blobs or legacy families

### Phase 4. Funnel AI Integration

- add imported-template prompt guidance in Funnel AI
- pass template manifest into AI generation
- add imported-template validation
- optionally move from full-page rewrites to structured mutation ops

### Phase 5. Review UI

- replace legacy family synthesis coverage with section translation coverage
- show clear section names
- show per-section translation status and validation status

## Concrete Code Areas To Change

Backend:

- `mos/backend/app/services/site_import_archive.py`
- `mos/backend/app/services/site_imports.py`
- `mos/backend/app/services/template_synthesis.py` for legacy-only scoping
- `mos/backend/app/services/funnel_ai.py`
- `mos/backend/app/agent/funnel_tools.py`

Frontend:

- `mos/frontend/src/funnels/puckConfig.tsx`
- `mos/frontend/src/funnels/puckData.ts`
- `mos/frontend/src/funnels/puckAiPlugin.tsx`
- `mos/frontend/src/pages/workspaces/StoreTemplatesPage.tsx`
- `mos/frontend/src/pages/workspaces/SitePageEditorPage.tsx`

Tests:

- `mos/backend/tests/test_site_imports_api.py`
- new import-native template translation tests
- new imported-template AI validation tests

## Final Recommendation

The correct model is:

- imported page becomes an imported template
- imported template gets a dynamic page name
- each imported section gets a clear template-specific name
- each section is translated into real editable child primitives
- Funnel AI edits those primitives through the same page-draft workflow MOS already uses

That gives us:

- accurate section identity
- real editability
- AI-assisted mutation
- clean validation
- no dependency on old Sales PDP assumptions
