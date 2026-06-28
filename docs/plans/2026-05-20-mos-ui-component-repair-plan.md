# MOS UI Component Repair Plan

## Goal

Bring the MOS component layer to a coherent, browser-reviewed state after the first token migration pass. Success means the shared primitives render cleanly in Chrome, representative product routes use them correctly, and regressions are caught by executable checks.

## Observable Problem

The first migration updated tokens and some primitives, but visual QA was incomplete. Several primitives and consuming surfaces were not reviewed in a real browser, so layout, sizing, density, hierarchy, and interaction states may be inconsistent or broken.

## Working Diagnosis

The system lacks a first-party component review surface. Without a page that renders the primitives together, changes get validated through scattered product routes and tests instead of direct visual inspection. That lets partial primitive migrations pass build/test while still looking wrong.

## Designed Machine

1. Capture the current UI in Chrome using the user's active MOS browser session.
2. Add a local component review route that renders all core primitives and layout helpers in one place.
3. Review the route in Chrome at desktop and narrow widths.
4. Patch primitives and helper classes until the review route and representative product routes are visually coherent.
5. Keep borrowed-name and semantic checks green.
6. Save screenshots, audit notes, and command logs in a repair proof pack.

## Repair Addendum: Source-Matched Components

The first browser pass made the app cleaner but drifted from `Moz Design System.html`. The revised repair target is now source-matched component primitives, excluding brand identity elements.

Additional requirements:

1. Extract the embedded source HTML/CSS from `/Users/aldrinclement/Downloads/Moz Design System.html`.
2. Treat the extracted component CSS as the pass/fail baseline for shared primitives.
3. Align buttons, badges/status, form fields, cards, floating panels, choices, and component review anatomy to the reference values.
4. Expand the review route to include reference-specific examples that were skipped: button states, input states, chips, input groups, combobox-style panels, OTP, choice cards, value pills, status dots, and card variants.
5. Validate the repaired route and representative product routes in the browser again.

## Repair Addendum: Actual Route Components

The source review found that the dev harness had improved faster than the usable first-run route. The repair target now includes consuming routes, not only primitive demos.

Additional requirements:

1. Replace basic onboarding choices with a reusable source-shaped `ChoiceList` system: single-select stack, multi-select cards, compact choices, and grid/card choices.
2. Fix the actual focused input ring on `/workspaces/new`; it must use a soft ring token, not the dark focus border token.
3. Capture the real workspace creation input and selected choice step in the browser.
4. Fix any runtime load issue that blocks browser proof.

## Scope

In scope:

- `mos/frontend/src/components/ui`
- `mos/frontend/src/components/layout`
- `mos/frontend/src/components/StatusBadge.tsx`
- `mos/frontend/src/styles/theme.css`
- `mos/frontend/src/styles/globals.css`
- `mos/frontend/src/styles/design-system.css`
- local component review route/page
- representative product route cleanup where primitives expose obvious defects

Out of scope:

- brand identity, logos, wordmarks, customer brand output
- marketing/funnel redesign
- production deploy
- model or API behavior changes

## Acceptance

- Chrome screenshots exist for the component review page and at least two representative product routes.
- Component review page includes buttons, badges, inputs, textarea, select, callouts, tabs, table, dialog, popover, menu, toast, progress, skeleton, page header, filter bar, empty state, error state, and status badges.
- Component review page also includes the reference-only component anatomy needed to catch prior skips: state cards, input groups, chips, combobox-style panels, OTP cells, choice cards, status dots, and card variants.
- Actual onboarding/first-run route uses the repaired input and choice components, not a separate stale variant.
- Primitive sizing, density, radius, focus, hover, disabled, and text overflow states are reviewed and repaired.
- Shared primitive values match the extracted reference for core shape and sizing: pill buttons at 46/36/54/64px, 54px form controls, 12px input radius, 20px cards, 14px floating panels, 22px badges, and source radii tokens.
- Product routes do not show obvious overlap, clipped text, blown-out spacing, or incoherent hierarchy from primitive changes.
- `npm run check:design-system` passes.
- `npm run check:semantic-ui` passes.
- `npm run build` passes.
- `npm run test:unit` passes or any unrelated blocker is documented with exact cause.

## Verification Commands

- `cd mos/frontend && npm run --silent check:design-system`
- `cd mos/frontend && npm run --silent check:semantic-ui`
- `cd mos/frontend && npm run --silent build`
- `cd mos/frontend && npm run --silent test:unit`

## Artifacts

- `proof_pack/mos-ui-component-repair/browser-audit.md`
- `proof_pack/mos-ui-component-repair/screenshots/`
- `proof_pack/mos-ui-component-repair/logs/`
- `proof_pack/mos-ui-component-repair/plan.contract.json`
- `proof_pack/mos-ui-component-repair/index.html`

## Failure Modes

- Shallow diagnosis: fixed by direct component harness review.
- Symptom-only patching: fixed by repairing primitives before route-specific cleanup.
- Perfect-day browser pass: fixed by checking desktop and narrow widths.
- Scope creep: defer marketing/funnel/customer brand redesign.
- Missing metrics: pass/fail comes from screenshots, route checks, build/test, and contract verification.

## Parallelism

- `parallelizable`: no for implementation, yes for local command reads.
- `single-agent reason`: edits touch shared primitives and styles; overlapping workers would create conflicts.
- `validation owner`: main agent.
