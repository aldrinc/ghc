# Design System Unification PRD

## Decision

Use one canonical reusable style object across Marketi: the product-facing **Design Preset**, backed in phase 1 by the existing `design_systems` table.

Do not keep separate runtime style object families for:

- workspace brand systems
- imported native site styles
- template style presets
- Medusa shell styling

Phase 1 implementation decision:

1. expand `design_systems` into the canonical preset record
2. keep imported style in `site_imports` as a non-runnable **design candidate** until promoted
3. retire `template_style_presets` and move template variants onto `design_systems`
4. keep the existing binding surfaces instead of adding a generic `design_bindings` table
5. store immutable publish-time style snapshots on publication records instead of creating a second live style system

This is the smallest model that still supports all required product behaviors:

- an imported site can preserve its native style as a reusable preset
- an imported preset can be applied to another site
- an existing brand preset can be applied onto an imported site
- a reference page can feed a Medusa one-product shell without creating a second theming mechanism

## Why This Decision

The repo already has the right backbone, but style state is split across incompatible carriers:

| Current carrier | Where it lives | Current meaning | Problem |
| --- | --- | --- | --- |
| Screenshot-to-code preflight | `screenshot-to-code/backend/loop/design_system_preflight.py` | rich extracted evidence | evidence only, not runnable |
| `SiteImport.theme_candidate` | `mos/backend/app/db/models.py` | lightweight import summary | too lossy for reuse or shell styling |
| `DesignSystem.tokens` | `mos/backend/app/db/models.py` | reusable runtime tokens | table is too thin; missing provenance, status, compatibility |
| Client/site/page binding columns | `clients.design_system_id`, `sites.theme_binding_mode`, `sites.design_system_id`, `site_pages.design_system_id` | runtime precedence | works today and should be reused, not replaced |
| `TemplateStylePreset.tokens` | `template_style_presets` | template-only style object | duplicates `design_systems` |
| `TemplateVariant.style_preset_id` | `template_variants` | template variant style reference | keeps storefront styling off the main binding path |

The result is one core contradiction:

Imported style can be reviewed and converted, but it is not born as the same kind of object that sites, pages, and workspace defaults already know how to bind.

That contradiction shows up concretely in code:

- `normalize_capture()` creates `theme_candidate` as `{ palette, fonts, spacing, cta }`, which is weaker than the canonical token schema in `design_system_generation.py`.
- `save_import_as_site()` creates the `Site` and `SitePage` records, but does not promote or bind the imported style.
- import conversion creates `TemplateStylePreset` directly from `theme_candidate`, so style gets trapped in the template pipeline.
- `_resolve_site_design_system_tokens()` already enforces explicit precedence and explicit error states. That should remain the center of truth instead of adding a second resolver.
- Medusa planning docs already assume a single token stack: base schema, template defaults, workspace overrides, and page overrides.

## Product Model

Phase 1 should reduce the system to four meanings:

| Product concept | Phase 1 storage | Runnable | Notes |
| --- | --- | --- | --- |
| Design Preset | `design_systems` | yes | reusable style library item |
| Import Design Candidate | `site_imports` candidate fields | no | evidence plus proposed canonical tokens |
| Binding | existing client/site/page/variant columns | yes | tells the resolver which preset applies |
| Publish Snapshot | publication metadata | immutable | preserves exact tokens at publish or approval time |

### 1. Design Preset

Design Preset is the reusable style system a user can apply to sites, pages, template variants, and store shells.

Phase 1 storage:

- keep `design_systems`
- expand it instead of inventing a second canonical table

Required fields on `design_systems`:

| Field | Purpose |
| --- | --- |
| `id` | stable preset id |
| `org_id` | ownership |
| `client_id` | workspace scope |
| `name` | human label |
| `tokens` | canonical validated token payload |
| `kind` | `workspace_brand`, `imported_reference`, `starter_default`, `manual`, `derived` |
| `status` | `draft`, `validated`, `approved`, `archived` |
| `token_schema_version` | validation and migration gate |
| `source_type` | `onboarding_generation`, `site_import`, `template_derivation`, `manual_edit` |
| `source_ref` | JSON payload with import ids, urls, snapshot refs, and upstream artifact ids |
| `derived_from_design_system_id` | lineage for copied or mutated presets |
| `compatibility` | shell and template capability flags |
| `preview_artifacts` | render refs such as screenshot-to-code html/png or review thumbnails |
| `created_at` / `updated_at` | existing lifecycle fields |

Rules:

- `tokens` must always validate through `validate_design_system_tokens()`
- presets are the only reusable style object that runtime surfaces can bind to
- a preset may come from workspace onboarding or from an imported site, but it is still the same object

### 2. Import Design Candidate

Import Design Candidate is not a separate live preset. It is the import-stage record of extracted style evidence plus a proposed canonical token mapping.

Phase 1 storage:

- keep it on `site_imports`
- do not introduce a generic `design_candidates` table yet

Required additions to `site_imports`:

| Field | Purpose |
| --- | --- |
| `design_candidate` | canonical candidate payload and mapping result |
| `design_candidate_status` | `pending`, `mapped`, `partial`, `blocked`, `approved` |
| `promoted_design_system_id` | optional FK to the promoted preset |
| `design_candidate_artifacts` | refs to preflight html/png/json, capture metadata, and audit output |

Recommended candidate payload shape:

| Key | Purpose |
| --- | --- |
| `rawEvidence` | screenshot-to-code preflight output, capture metadata, theme summary |
| `mappedTokens` | proposed canonical token payload |
| `coverage` | which token groups mapped cleanly vs partially |
| `provenance` | source url, import id, timestamps, actors, upstream model info |
| `compatibility` | shell/template readiness assessment |

Rules:

- candidates are review artifacts, not runtime bindings
- `theme_candidate` becomes transitional compatibility data and should be deprecated after migration
- the system must error, not silently apply a candidate as if it were a preset

### 3. Binding

Phase 1 should reuse the binding surfaces already present in the repo.

Do not add a generic `design_bindings` table yet. It would duplicate working mechanisms and create a second migration problem.

Binding surfaces:

| Surface | Existing fields | Phase 1 meaning |
| --- | --- | --- |
| workspace default | `clients.design_system_id` | default preset for the workspace |
| site | `sites.theme_binding_mode`, `sites.design_system_id` | site-level binding choice |
| page override | `site_pages.design_system_id` | explicit page override |
| template variant | new `template_variants.design_system_id` | template style binding after `style_preset_id` retirement |
| publish snapshot | `site_publications.meta` | immutable copy of resolved tokens at publish time |

Site binding modes should remain:

- `standalone`
- `workspace_default`
- `design_system`

Their meaning becomes stricter:

- `standalone` means no preset binding; templates rely only on built-in defaults
- `workspace_default` means resolve `clients.design_system_id`
- `design_system` means `sites.design_system_id` must exist and must resolve

### 4. Publish Snapshot

Published or approved outputs should not depend on a mutable preset row.

Phase 1 recommendation:

- persist resolved design snapshot data inside immutable records instead of introducing a standalone snapshot table

Required publish-time payload:

| Field | Purpose |
| --- | --- |
| `designSystemId` | source preset id at publish time |
| `designSystemVersion` | schema or updated-at marker |
| `resolvedTokens` | full resolved canonical token payload |
| `sourceBinding` | workspace/site/page/variant source that produced the snapshot |

Storage targets:

- `site_publications.meta.designSnapshot`
- equivalent immutable variant publication or approval metadata when template variants become publishable

## Binding And Inheritance Rules

### Resolution stack

The only supported style stack is:

1. base token schema from `base_tokens.json`
2. template-family defaults
3. shell-specific defaults when the consumer is a storefront shell
4. resolved Design Preset
5. explicit page-level override when the page is bound directly to another preset
6. immutable publication snapshot once published

### Hard rules

1. Imported candidates cannot be applied directly.
2. Reusable runtime surfaces only bind to `design_systems`.
3. `template_style_presets` cannot remain a separate long-term source of truth.
4. Missing explicit bindings are hard errors, consistent with `_resolve_site_design_system_tokens()`.
5. `standalone` never secretly falls back to a workspace preset.
6. Template defaults and shell defaults are not reusable presets.
7. Publish-time snapshots freeze resolved tokens; editing a preset later does not rewrite a publication.

### Precedence by surface

| Surface | Resolution rule |
| --- | --- |
| funnel/page runtime | keep current `resolve_design_system_tokens()` semantics |
| site runtime | keep `_resolve_site_design_system_tokens()` semantics |
| site page | page override first, then site mode |
| template preview | template variant preset first, otherwise explicit preview choice |
| one-product shell pages | resolve through the site and page binding path, not a shell-specific theme object |

## Required User Flows

### A. Import site and preserve native design system

Flow:

1. import creates `site_imports` record plus `design_candidate`
2. candidate maps source evidence onto canonical tokens
3. reviewer chooses `Promote as preset`
4. system creates a `design_systems` row with `kind=imported_reference`
5. saved site binds to that preset through `theme_binding_mode=design_system`

Required behavior:

- promotion must preserve provenance back to the import
- the preset must appear in the workspace preset library
- the same preset must be available for other sites and templates

### B. Import site but apply an existing preset instead

Flow:

1. import still creates a design candidate for audit and comparison
2. user chooses an existing preset from the workspace library
3. saved site binds to that preset
4. import candidate remains available as evidence, but is not the active site style

Required behavior:

- the system must not destroy the imported candidate just because another preset was bound
- the UI should show imported-native vs applied-preset difference clearly

### C. Save import as site

`save_import_as_site()` must stop dropping style intent implicitly.

Add a required `designHandling` input:

| Value | Meaning |
| --- | --- |
| `promote_imported` | create preset from candidate and bind site to it |
| `bind_existing` | bind to an existing `design_system_id` |
| `workspace_default` | bind to workspace default |
| `standalone` | create site with no preset binding |

Rules:

- omission of `designHandling` is an error
- `bind_existing` requires `designSystemId`
- `promote_imported` requires a mapped candidate that passes validation

### D. Convert import to template variant

Current convert flow creates `TemplateStylePreset` from `theme_candidate`.

Target flow:

1. import candidate maps to canonical tokens
2. conversion chooses an existing preset or promotes the import candidate
3. `template_variants.design_system_id` stores the chosen preset
4. governance audits the preset tokens from `design_systems`

That keeps site runtime and template runtime on the same style object.

### E. Apply imported preset onto another site

Flow:

1. import A promotes a preset
2. site B sets `theme_binding_mode=design_system` and `design_system_id=<preset>`
3. resolver and preview path work unchanged because they already consume `DesignSystem`

### F. Medusa one-product shell

The Medusa shell must consume the same preset model as the imported reference page.

Required result:

- the imported reference page provides structure inspiration and a style candidate
- the reusable one-product shell provides structure and data bindings
- the chosen Design Preset provides visual language across home or PDP, cart drawer, offer surfaces, policy pages, and checkout-adjacent flows

No separate shell theme object should exist.

## Medusa One-Product Shell Implications

The Medusa planning docs already assume token-driven styling. This PRD should align to that instead of inventing a parallel shell preset system.

Implications:

1. the shell is a consumer of tokens, not a second design-system family
2. imported reference sites should produce token proposals, not copied CSS
3. the canonical token schema must expand for storefront needs, not just funnel needs

Required storefront token groups to add to the canonical schema:

- navigation and announcement surfaces
- product card and product grid tokens
- price and compare-at price typography
- cart drawer and mini-cart surfaces
- checkout-adjacent buttons, forms, and trust modules
- policy/contact/support page surfaces
- motion intensity and interaction emphasis for storefront affordances

Recommended preset compatibility payload:

| Key | Meaning |
| --- | --- |
| `supportsFunnels` | safe for funnel runtime |
| `supportsSalesPdp` | safe for sales-page or PDP templates |
| `supportsOneProductShell` | safe for one-product store shell |
| `missingTokenGroups` | storefront groups not yet mapped |

## API And Data Model Changes

### Database changes

#### `design_systems`

Add:

- `kind`
- `status`
- `token_schema_version`
- `source_type`
- `source_ref`
- `derived_from_design_system_id`
- `compatibility`
- `preview_artifacts`

Keep:

- `id`
- `org_id`
- `client_id`
- `name`
- `tokens`

#### `site_imports`

Add:

- `design_candidate`
- `design_candidate_status`
- `design_candidate_artifacts`
- `promoted_design_system_id`

Deprecate:

- `theme_candidate` as the authoritative style artifact

#### `template_variants`

Add:

- `design_system_id`

Deprecate and then remove:

- `style_preset_id`

#### `template_style_presets`

Retire after backfill into `design_systems`.

### Service changes

| Area | Required change |
| --- | --- |
| `site_import_normalize.py` | create canonical design candidate payload, not only `theme_candidate` |
| `design_system_generation.py` | materialize and validate imported candidate tokens against the canonical schema |
| `site_imports.py` | require explicit `designHandling` on save and convert paths |
| `storefront_imports.py` | stop creating `TemplateStylePreset`; create or reference `DesignSystem` instead |
| `template_variant_governance.py` | audit `design_systems.tokens` |
| site and preview resolvers | keep existing resolution semantics and extend them to variants/publications |

### API changes

Add or change:

| Endpoint | Change |
| --- | --- |
| `POST /site-imports/:id/promote-design-preset` | promote import candidate into `design_systems` |
| `POST /site-imports/:id/save-as-site` | require `designHandling` and optional `designSystemId` |
| import convert endpoint | return `designSystemId`, not `stylePresetId` |
| preset library endpoints | include `kind`, `status`, `source_type`, `compatibility`, preview metadata |
| template variant endpoints | accept and return `designSystemId` |

## Migration Plan

### Phase 0: Expand canonical preset model

- add metadata columns to `design_systems`
- keep current readers working on `tokens`
- backfill existing workspace design systems with `kind=workspace_brand` and `status=approved`

### Phase 1: Introduce import candidate payload

- write `design_candidate` and related status fields on every import
- keep `theme_candidate` only as transitional compatibility output
- validate candidate mappings against the canonical schema and record coverage

### Phase 2: Fix import save and convert flows

- require explicit `designHandling` on `save_import_as_site()`
- add import candidate promotion to `design_systems`
- stop dropping imported style at site save time
- switch convert flow from `TemplateStylePreset` creation to `DesignSystem` promotion or selection

### Phase 3: Move template variants onto canonical presets

- add `template_variants.design_system_id`
- backfill from `style_preset_id`
- move governance and preview readers to `design_systems.tokens`
- remove writer paths for `template_style_presets`

### Phase 4: Publish snapshots

- persist resolved style snapshot data into `site_publications.meta`
- do the same for any immutable template publication record
- ensure publish output no longer depends on mutable preset rows

### Phase 5: Cleanup

- remove `template_style_presets`
- remove `template_variants.style_preset_id`
- deprecate `theme_candidate` from import review APIs once all clients read `design_candidate`

## Risks And Open Questions

1. The canonical token schema is still funnel-heavy. Storefront token expansion is required before one-product shells can claim full compatibility.
2. Some imports will only partially map into canonical tokens. The system needs an explicit `partial` or `blocked` candidate state, not a fake successful promotion.
3. Font handling must stay curated. Imported font observations should become suggestions, not auto-approved external font dependencies.
4. `standalone` mode is valid, but it should be used deliberately. On imported sites it may produce a visual mismatch if the template family defaults are much weaker than the source reference.
5. Publication snapshot storage can live in `meta` in phase 1, but if multiple product surfaces start reusing snapshots directly, a dedicated table may become worth it later.

## Final Recommendation

Implement the unification around the schema and resolver you already have:

- one canonical preset table
- one explicit import candidate representation
- one set of binding columns
- one immutable publish snapshot

Do not create a second reusable style system for storefronts, imports, or Medusa shells.

The key migration move is not inventing more objects. It is making imported style graduate into the same object that the rest of the product already knows how to bind and resolve.
