# PRD: UI Standardization Phase 2 (Status + Callouts + Page Primitives)

## Context / Background

We have committed to a semantic token system for the app UI:

- Tokens live in `mos/frontend/src/styles/theme.css` and switch for dark mode via `:root[data-theme="dark"]`.
- Tailwind semantic utilities are mapped in `mos/frontend/tailwind.config.ts`.
- CI enforces token rules via `mos/frontend/scripts/check-semantic-ui.mjs` (baseline is now empty).

Phase 1 delivered:

- Dark mode via `data-theme` (no `dark:*` Tailwind usage).
- Strict enforcement against neutral palettes (`slate-*`, `gray-*`, `zinc-*`, `neutral-*`, `stone-*`) and `bg-white` / `ring-offset-white`.
- Token colors now support Tailwind opacity modifiers (e.g. `bg-surface/95`) via `color-mix(...)` in `mos/frontend/tailwind.config.ts`.

Phase 2 focuses on the remaining major source of inconsistency: **status colors/callouts** and **ad-hoc page UI patterns**.

## Problem Statement

1. **Status/callout styling is not semantic**
   - We still have hard-coded status palettes in UI code (e.g. `bg-amber-50`, `border-amber-200`, `bg-red-50`, `bg-emerald-500/...`).
   - These do not consistently theme in dark mode and create an uneven “design language” across pages.

2. **Pages re-implement the same UI patterns**
   - “Filter bars”, loading/empty states, and inline error banners are frequently implemented per-page with bespoke markup and classes.
   - This is one of the reasons AI-generated pages look off: they don’t default to shared primitives and inherit inconsistent styling.

## Goals

- Replace palette-based statuses/callouts with **semantic status tokens** and shared primitives.
- Provide **reusable page primitives** so new pages (including AI-generated) “snap” into the same UI structure.
- After migration, enforce “no palette statuses” in CI to prevent regressions.

## Non-Goals

- Rebranding or large visual redesign (typography, spacing scale, radii, etc.).
- Changing the theme switching mechanism (must remain `data-theme` token switching).
- Introducing alternate styling systems (no Tailwind `dark:*` variants, no second token source).

## Current Inventory (Palette-Based Status Styling)

These are the known palette usages that Phase 2 should migrate (from a repo scan on 2026-02-09):

Warning / in-progress (amber):

- `mos/frontend/src/components/StatusBadge.tsx`
- `mos/frontend/src/components/ads/AdsIngestionRetryCallout.tsx`
- `mos/frontend/src/pages/campaigns/CampaignDetailPage.tsx`
- `mos/frontend/src/pages/explore/ExploreAdsPage.tsx`
- `mos/frontend/src/pages/explore/ExploreBrandsPage.tsx`
- `mos/frontend/src/pages/library/AdsPanel.tsx`
- `mos/frontend/src/pages/research/AdLibraryPage.tsx`
- `mos/frontend/src/pages/research/ResearchPage.tsx`
- `mos/frontend/src/pages/swipes/SwipesPage.tsx`
- `mos/frontend/src/pages/workflows/WorkflowDetailPage.tsx`
- `mos/frontend/src/pages/workflows/WorkflowsPage.tsx`
- `mos/frontend/src/pages/workspaces/WorkspaceOverviewPage.tsx`

Error (red):

- `mos/frontend/src/pages/library/CreativeTeardownsPanel.tsx`

Success highlight (emerald):

- `mos/frontend/src/components/library/LibraryCard.tsx`

## Requirements

### 1) Semantic Status Tokens (Light + Dark)

Status semantics must be representable without hard-coded palettes.

Required status tokens:

- `danger` (already exists)
- `success` (already exists)
- `warning` (added in Phase 1 follow-up; must be used everywhere warnings are needed)

Optional (only if needed by real UI):

- `info`

Deliverables:

- Define/confirm token values for `--warning` in `mos/frontend/src/styles/theme.css` for both themes.
- If `info` is needed, add `--info` and map it in `mos/frontend/tailwind.config.ts`.

Usage conventions (standardize):

- Background: `bg-{status}/10` or `bg-{status}/5`
- Border: `border-{status}/30`
- Text: `text-{status}`
- Icon/dot accents: `bg-{status}` or `text-{status}`

### 2) Shared Callout Component

Create a reusable callout/banner component that replaces per-page ad-hoc warning/error blocks.

Location:

- `mos/frontend/src/components/ui/callout.tsx`

API (proposed):

- `variant`: `"info" | "warning" | "danger" | "success" | "neutral"`
- `title`: optional string / node
- `children`: body content
- `icon`: optional (defaults per variant)
- `actions`: optional slot for buttons/links
- `size`: `"sm" | "md"` (optional)

Behavior + accessibility:

- `variant="danger" | "warning"` should support `role="alert"` when appropriate (do not force it for purely informational copy).
- Must be readable in both themes with token-driven colors.

### 3) Standardize StatusBadge

`mos/frontend/src/components/StatusBadge.tsx` should:

- Use semantic tokens for status states (`running` => `warning`).
- Avoid any palette-based `amber-*`.
- Keep sizing/typography consistent with `Badge` and `Callout`.

### 4) Migrate Existing Pages/Components

Replace palette-based status UI with the new semantic patterns:

- Convert every `bg-amber-*`, `text-amber-*`, `border-amber-*` usage in the inventory to token usage or `Callout`.
- Convert `bg-red-*` error block(s) to `danger` token usage or `Callout`.
- Convert `bg-emerald-*` highlights in `LibraryCard` to `success` token usage.

### 5) Page Primitives For Reuse (So AI Pages Don’t Go Off-Rails)

Add primitives that cover the most common repeated patterns:

- `FilterBar` (search + selects + toggles + reset)
- `EmptyState` (title, description, optional action)
- `LoadingState` / skeleton helpers (consistent spacing + surface)

Locations (proposed):

- `mos/frontend/src/components/layout/FilterBar.tsx`
- `mos/frontend/src/components/layout/EmptyState.tsx`
- (Optional) `mos/frontend/src/components/layout/LoadingState.tsx`

Then update the worst offenders (high traffic pages first) to use the primitives:

- Explore pages (already mostly standardized in Phase 1, but should consume `FilterBar` once it exists)
- Research pages
- Workflows pages

### 6) CI Enforcement For Status Palettes (After Migration)

After migrations land, extend CI enforcement to block regressions for status palettes.

Options:

1. Extend `mos/frontend/scripts/check-semantic-ui.mjs` with additional forbidden patterns:
   - `\\b(?:amber|red|emerald|green|yellow|rose)-\\d{2,3}\\b`
2. Or create a dedicated `scripts/check-semantic-status.mjs` to keep concerns separate.

Constraints:

- No silent skip rules. If we need exceptions (e.g. data viz), make them explicit, small, and documented.

## Implementation Plan (Suggested PR Breakdown)

PR 1: Tokens + primitives

- Confirm token values for `warning` (and add `info` only if required by real UI).
- Implement `Callout` component + examples.
- Update `StatusBadge` to semantic tokens.

PR 2: Migrate inventory

- Replace palette-based warning/error/success styles in the inventory with `Callout` + tokens.
- Replace `LibraryCard` emerald pills with `success` tokens.

PR 3: Page primitives

- Implement `FilterBar`, `EmptyState` (and optional `LoadingState`).
- Migrate a small set of pages to validate the primitives (Explore + Workflows first).
- Update documentation: add usage examples to `mos/frontend/docs/ui-style-guide.md`.

PR 4: Enforcement

- Add CI rule(s) to block status palette classes.
- Ensure baseline is empty and checks are strict.

## Acceptance Criteria

- No `amber-*`, `red-*`, `emerald-*` (and other status palette) utilities in `mos/frontend/src/**` (excluding any explicitly documented exception list, if absolutely required).
- All warning/danger/success callouts use semantic tokens or `Callout`.
- `StatusBadge` uses semantic tokens only.
- Dark mode remains token-driven (`data-theme`) with consistent status styling.
- CI fails on reintroducing status palette classes.

## Test Plan

- `npm run build` in `mos/frontend` succeeds.
- CI semantic checks pass.
- Visual smoke test (light + dark):
  - Workflows: running/failed/completed states
  - Research/Explore: error banners and empty states
  - Library: any success highlights remain legible

## Open Questions

- Do we need an `info` token, or can we use a neutral callout + `accent` for “informational” states?
- Are there any intentional “brand color” status states that must not map to success/warning/danger?
