# Site Theme Binding Plan

## Decision

Make site theming explicit and site-scoped.
Do not implicitly force every site to inherit the workspace brand.

Each site should declare its own theme source:

- `standalone`
- `workspace_default`
- `design_system`

The site should then resolve its effective theme from that explicit choice.

This gives us both classes of sites the product needs:

- sites that intentionally bind to workspace brand/design system
- sites that intentionally stand alone without brand binding

## Why This Change

Today the behavior is mixed and hard to reason about:

- the site preview fetches design-system tokens with implicit fallback behavior
- the Site Theme tab exists, but it is only a placeholder
- the site/page editor language still frames theme inheritance as automatic
- the B2C Starter storefront has access to tokens, but most of its visual design is still hard-coded

That creates three product problems:

- users cannot clearly decide whether a site should bind to workspace brand or not
- the UI suggests theme configurability, but the site-level theme surface is effectively missing
- the runtime behavior is implicit, so the resulting storefront can look partially branded and partially generic

## Current State Reviewed

### Existing site theme UX

The site detail page already has a Theme tab, but it is still a placeholder:

- `mos/frontend/src/pages/workspaces/SiteDetailPage.tsx`

Current text:

- "Theme management coming soon. This site currently inherits from the workspace design system."

### Existing site/page inheritance model

The current site preview resolves design-system tokens using implicit fallback precedence:

- page override
- site override
- workspace default design system

Relevant code:

- `mos/backend/app/routers/sites.py`
- `mos/backend/app/services/design_systems.py`

### Existing page editor language

The page settings modal still assumes automatic inheritance:

- `mos/frontend/src/pages/workspaces/SitePageEditorPage.tsx`

Current helper text:

- "Leave as workspace default to inherit the brand tokens."

### Existing B2C Starter storefront implementation

The Medusa B2C Starter pages are thin wrappers around dedicated React components.
Those components mostly use hard-coded Tailwind classes rather than design-system tokens.

Relevant files:

- `mos/backend/app/templates/funnels/medusa-b2c-home.json`
- `mos/backend/app/templates/funnels/medusa-b2c-store.json`
- `mos/frontend/src/components/commerce/b2c/pages/B2CStarterShell.tsx`
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CHomePage.tsx`
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CStorePage.tsx`
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CProductPage.tsx`
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx`

### Existing template contrast

Our sales and pre-sales templates already consume design-system tokens explicitly.
That makes the architectural gap clear: the site runtime can carry theme tokens, but the B2C Starter storefront is not using them consistently.

Relevant files:

- `mos/frontend/src/funnels/templates/preSalesListicle/PreSalesTemplate.tsx`
- `mos/frontend/src/funnels/templates/salesPdp/SalesPdpTemplate.tsx`
- `mos/frontend/src/funnels/templates/shared/designSystemBrandLogo.ts`

## Product Goals

- let the user choose whether a site binds to workspace brand or stands alone
- make the site-level theme source visible and editable in the Site Theme tab
- stop implicit theme behavior from surprising users
- make new site creation ask for theme intent up front
- make B2C Starter storefronts actually honor the selected site theme when one is applied
- preserve support for page-level overrides later without making that phase-1 scope

## Non-Goals

- building a full generic theme-builder framework for every site family in phase 1
- redesigning all storefront templates at the same time
- introducing silent fallback behavior when a site is configured to be standalone
- expanding page-level theme overrides before site-level semantics are settled

## Proposed Model

### 1. Add explicit site theme binding mode

Add a site-level field:

- `theme_binding_mode`

Recommended values:

| Value | Meaning | Uses `design_system_id`? | Workspace fallback allowed? |
| --- | --- | --- | --- |
| `standalone` | Site intentionally has no bound design system | No | No |
| `workspace_default` | Site intentionally uses the workspace default design system | No | Yes |
| `design_system` | Site intentionally uses a specific selected design system | Yes | No |

Recommended rule:

- `standalone` means the resolved site theme is `null`
- `workspace_default` means resolve from `Client.design_system_id`
- `design_system` means resolve from the site's selected `design_system_id`

### 2. Keep `design_system_id`, but stop overloading it

We should keep `design_system_id` on `Site`.
It is still useful when the user explicitly selects a design system.

What changes is the meaning:

- today, missing `design_system_id` implicitly means "probably use workspace default"
- after this change, missing `design_system_id` is only meaningful in combination with `theme_binding_mode`

That makes site behavior reviewable and deterministic.

### 3. Page-level behavior should inherit from site, not from workspace

Phase 1 recommendation:

- page-level default becomes `inherit_site`
- page settings should stop saying "workspace default"
- page settings should describe inheritance from the site theme

We can still support page-level design-system override later, but the default mental model should be:

- workspace brand configures the workspace
- site theme configures the site
- page settings optionally override the site

## UX Proposal

## Site Creation

Expose a Theme section during site creation.

Recommended options:

1. `Standalone`
2. `Use workspace brand`
3. `Use selected design system`

If the user selects `Use selected design system`, show a design-system picker.

Recommended default for new sites:

- `Standalone`

Exception:

- if a specific site family or template requires brand assets to function truthfully, require explicit user selection and error cleanly if omitted

## Site Detail: Theme Tab

Replace the placeholder Theme tab with a real configuration surface.

Recommended sections:

### Theme Source

- radio/select control for `Standalone`, `Use workspace brand`, `Use selected design system`
- design-system picker when `Use selected design system` is active
- save action

### Effective Theme Summary

Show the user what the site will actually receive:

- effective source
- design system name
- logo availability
- font availability
- key color tokens

### Runtime Usage Summary

Explain where the current site family uses site theme today:

- brand name
- logo
- typography
- colors
- CTA styling

This is important because the B2C Starter currently does not consume all theme tokens.
The UI should not overpromise what is already wired.

## Site Page Editor

Change helper copy from workspace-centric language to site-centric language.

Recommended change:

- old: "Leave as workspace default to inherit the brand tokens."
- new: "Leave as site default to inherit this site's theme."

If page overrides remain enabled, the page editor should clearly say that page overrides sit on top of the site theme.

## Backend Plan

### Phase 1. Add explicit site theme semantics

Update the site model and API shape.

Recommended backend changes:

- add `theme_binding_mode` to `Site`
- expose it through site schemas and site detail responses
- add a site-level update endpoint for theme settings
- validate that `design_system` mode requires a non-empty `designSystemId`
- validate that `standalone` mode ignores any provided `designSystemId`

Files likely involved:

- `mos/backend/app/db/models.py`
- `mos/backend/app/schemas/sites.py`
- `mos/backend/app/routers/sites.py`
- `mos/backend/app/db/repositories/sites_runtime.py`

### Phase 2. Replace implicit fallback resolution

Today `_resolve_site_design_system_tokens()` in `mos/backend/app/routers/sites.py` still falls back implicitly.

Change this to explicit mode-based resolution:

- `standalone` -> return `None`
- `workspace_default` -> resolve workspace default tokens
- `design_system` -> resolve site design system tokens

This is the main behavioral correction.

### Phase 3. Add site update API

We need a real site-level update endpoint.
The repository already supports `update_site()`, but there is no proper site settings mutation surface for this use case.

Recommended endpoint:

- `PATCH /sites/{site_id}`

Recommended payload fields:

- `name?`
- `description?`
- `routeSlug?`
- `primaryDomain?`
- `themeBindingMode?`
- `designSystemId?`

This should be the source of truth for the Theme tab.

## Frontend Plan

### Phase 1. Build real site theme settings UI

Replace the placeholder block in:

- `mos/frontend/src/pages/workspaces/SiteDetailPage.tsx`

Add:

- theme source selector
- design-system picker
- effective summary card
- save state
- error state

### Phase 2. Update create-site flow

Expose theme choice during site creation in:

- `mos/frontend/src/pages/workspaces/SitesPage.tsx`
- `mos/frontend/src/api/sites.ts`

This ensures the user's intent is captured at creation time instead of inferred later.

### Phase 3. Update page editor language

Update page settings copy and behavior in:

- `mos/frontend/src/pages/workspaces/SitePageEditorPage.tsx`

This is a necessary cleanup so the UI model stays coherent after the site-level feature exists.

## Storefront Implementation Plan

The product change is not complete unless the selected site theme affects the storefront in a visible, intentional way.

### Phase 1. Define a minimal B2C Starter theme contract

Do not attempt full token coverage first.
Define a small curated site-theme surface for B2C Starter.

Recommended first-pass fields:

- logo asset
- brand display name
- sans font
- heading font
- page background
- text color
- muted text color
- border color
- primary brand color
- CTA background
- CTA text color
- radius

These can be derived from design-system tokens when a design system is active.

### Phase 2. Add a B2C theme adapter layer

Create a small adapter that reads the resolved site theme and maps it into a B2C Starter storefront theme object.

Responsibilities:

- normalize token names
- provide only the supported B2C fields
- avoid implicit fallback when the site is `standalone`
- fail cleanly if a required field is missing for a required template

### Phase 3. Wire B2C Starter pages to consume the theme

Update the B2C Starter pages to use the adapter output rather than raw hard-coded colors and fonts where appropriate.

Primary targets:

- `mos/frontend/src/components/commerce/b2c/pages/B2CStarterShell.tsx`
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CHomePage.tsx`
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CStorePage.tsx`
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CProductPage.tsx`
- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx`

Expected visible changes:

- header logo and brand mark
- heading typography
- CTA styling
- border/surface palette
- footer brand treatment

### Phase 4. Remove accidental global-theme leakage

Some typography is currently coming from global app CSS rather than explicit storefront theme intent.

Relevant files:

- `mos/frontend/src/styles/globals.css`
- `mos/frontend/src/styles/theme.css`

Recommendation:

- define storefront heading and body font application explicitly inside the B2C starter shell/theme layer
- do not rely on global heading defaults to create branded storefront typography

## Template and Site Family Governance

Add metadata for theme requirements on site families or templates.

Recommended field:

- `theme_requirement`

Recommended values:

- `optional`
- `required`

Use cases:

- a generic storefront starter can be `optional`
- a template that requires a real logo or brand assets can be `required`

Recommended behavior:

- if `required` and the site is created as `standalone`, return a clean validation error
- do not silently switch the site to workspace brand

## Migration Plan

We should preserve current behavior for existing sites while changing semantics for future sites.

### Backfill rule

For existing sites:

- if `site.design_system_id` is set, backfill `theme_binding_mode = design_system`
- if `site.design_system_id` is empty but the site currently behaves as inherited from workspace default, backfill `theme_binding_mode = workspace_default`

This avoids changing existing previews unexpectedly.

### New-site rule after migration

For newly created sites:

- default to `standalone`

That is the product behavior change.

## Testing Plan

We need explicit coverage for the three supported theme modes.

### Backend tests

- `standalone` returns `null` effective design-system tokens
- `workspace_default` resolves workspace default design system
- `design_system` resolves site-selected design system
- `design_system` mode errors when `designSystemId` is missing
- `standalone` ignores provided `designSystemId`

### Frontend tests

- Theme tab renders correct state for each mode
- create-site flow sends the selected theme mode
- page editor copy reflects site inheritance rather than workspace inheritance

### Runtime tests

- standalone site preview renders without design-system tokens
- workspace-bound site preview resolves workspace brand correctly
- selected-design-system site preview resolves the selected design system correctly
- B2C Starter visuals change only when a site theme is intentionally applied

## Rollout Plan

### Phase A. Product model and UI

Ship:

- `theme_binding_mode`
- site update API
- Theme tab UI
- create-site theme selection
- page editor copy cleanup

This establishes explicit user intent and makes the product model reviewable.

### Phase B. B2C Starter theme consumption

Ship:

- B2C Starter theme adapter
- header/logo/font/color wiring
- storefront visual token usage

This makes the chosen site theme visibly affect the storefront.

### Phase C. Optional page-level overrides

Only after the site-level model is stable:

- add page-level theme override mode
- keep site-level inheritance as the default

## Open Questions

1. Should new sites default to `standalone` for all site families, or only for B2C Starter?
2. Do we want page-level theme overrides in phase 1, or explicitly defer them?
3. Do imported sites default to `standalone` even if the workspace has a brand design system?
4. Should a site in `standalone` mode still be allowed to use site name and non-design-system commerce data? Recommended answer: yes.
5. Should B2C Starter support a site-specific logo asset outside of the design system later, or should all branded logo usage flow through design systems?

## Recommended Scope Cut

If we want the highest-value version with the least churn, ship this first:

1. explicit site theme binding mode
2. real Site Theme tab UI
3. create-site theme choice
4. page editor copy changed to inherit from site
5. B2C Starter consumes a small curated theme token set

Do not include page-level theme overrides in the first implementation pass.

## Final Recommendation

Treat site theme as an explicit site property, not an implicit workspace fallback.

That gives the product a clean mental model:

- workspace brand configures the workspace
- site theme configures the site
- pages inherit from the site unless explicitly overridden later

That is the right foundation for supporting both branded and standalone sites without the current ambiguity.
