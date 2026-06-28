# MOS Design System Migration Plan

## Decision

Migrate the MOS product UI to the new design-system language from `/Users/aldrinclement/Downloads/Moz Design System.html`, excluding brand identity elements.

Brand exclusion means no intentional changes to logo marks, wordmarks, naming, brand-kit upload behavior, generated brand assets, or funnel/customer brand elements. This pass is for the product system: typography, spacing, colors, radii, shadows, motion, component primitives, and app surface consistency.

Refinement from 2026-05-20: clean up borrowed naming outright. The product is pre-user, so prefer breaking and fixing call sites over compatibility shims. Remove `manus`, source-demo naming, and copied vendor/temporary vocabulary from production source. Do not add aliases unless absolutely necessary; any temporary alias must be documented with why it exists, where it is used, and the follow-up deletion condition.

## Goal

Within one implementation pass, make `mos/frontend` use the new MOS design system as the default visual system for app UI.

Measurable result:

- One canonical token layer drives Tailwind colors, typography, spacing, radii, shadows, and motion.
- Production source contains no `manus` namespace, copied source-demo namespace, or borrowed design-system naming except in source/proof docs.
- Core UI primitives match the new system: buttons, inputs, selects, textarea, badges, cards, tabs, menus, popovers, dialogs, tooltips, tables, toast, progress, skeleton, and section cards.
- High-frequency product screens use those primitives instead of one-off styling.
- Brand identity files and brand asset controls are unchanged except for non-brand wrapper/layout styles if required.
- Local build, unit tests, semantic UI check, and visual smoke checks pass.

## Observable Problem

The repo already has a token/component layer, but it is still mixed with the older Manus palette, borrowed vocabulary, and partial component coverage.

Evidence from the current code:

- `mos/frontend/src/styles/theme.css` defines `--manus-*`, light/dark tokens, first-run tokens, and only a small spacing scale.
- `mos/frontend/tailwind.config.ts` exposes a `manus` color namespace.
- The supplied source design-system HTML uses source/demo naming such as `--moz-blue-*`; those values are useful, but those names should not become permanent app API while brand elements are still WIP.
- `mos/frontend/src/styles/design-system.css` mainly covers cards, section cards, overline, and first-run helpers.
- `mos/frontend/tailwind.config.ts` maps Tailwind tokens to current CSS variables but not the full new design-system scale.
- `mos/frontend/src/components/ui/*` uses the current token names but several primitives still encode old sizes, radii, hover behavior, and focus behavior directly in Tailwind classes.
- Product pages still contain direct utility styling such as `rounded-xl`, `rounded-2xl`, `bg-surface-2`, `border-border`, and hand-built empty/loading panels.

## Root-Cause Diagnosis

Working theory: the design-system source exists as a visual/spec artifact, but MOS does not yet have a complete extraction, mapping, and enforcement path.

Root cause chain:

1. New design reference is outside the repo as a bundled HTML file.
2. Current repo tokens were evolved locally around copied Manus/first-run needs.
3. Borrowed names became internal API because moving fast mattered more than naming hygiene.
4. Component primitives only encode part of the system, so pages reach for ad hoc utility classes.
5. Brand and product UI live near each other, so a broad visual migration could accidentally touch brand identity.
6. There is no automated brand-freeze or borrowed-name check for this migration.

## Current Machine

Design changes happen screen-by-screen:

- CSS variables live in `theme.css`.
- Component helpers live in `design-system.css` plus `components/ui/*`.
- Tailwind exposes semantic aliases plus borrowed namespaces.
- Screens compose raw utility classes and local variants.
- Verification mostly proves code compiles, not that the design-system boundary or brand boundary held.

This makes design drift cheap and migration audits expensive.

## Designed Machine

Create a stronger design-system pipeline:

1. Extract source tokens/components from the supplied HTML into a documented map.
2. Map raw source values to MOS/product-neutral semantic tokens, not copied source names.
3. Remove borrowed names from production source instead of aliasing them.
4. Update Tailwind to expose the full design-system scale through neutral/product-owned names.
5. Update core primitives so screens inherit the system by default.
6. Refactor product surfaces to use primitives and semantic tokens.
7. Add brand-freeze and borrowed-name checks that protect both identity and naming hygiene.
8. Verify with contract checks, local tests, build, semantic UI check, name scan, and Playwright screenshots.

## Non-Goals

- No marketing-site redesign.
- No standalone HTML funnel deploy.
- No production deploy.
- No model changes.
- No fake data.
- No change to logo marks, wordmarks, naming, brand-kit assets, customer brand output, or generated brand identity.
- No permanent compatibility alias layer for old `manus`/copied names.

## Source Truth

Captured source:

- Source file: `/Users/aldrinclement/Downloads/Moz Design System.html`
- Source manifest: `proof_pack/mos-design-system-migration/source/source_manifest.json`
- `capturectl verify`: pass

Important source details already extracted. Values are source truth; names are not automatically source truth:

- Fonts: `DM Sans` for sans/body, `Libre Baskerville` for display/serif.
- Core colors: blue scale, ink scale, slate neutrals, white/soft/tinted surfaces, semantic success/warning/danger/info colors. Map source `--moz-*` names to neutral or MOS-owned product token names.
- Type scale: `11, 12, 13, 15, 16, 18, 21, 26, 34, 44, 56, 72, 92px`.
- Spacing: 4-based scale from `4px` through `128px`.
- Radii: `4, 6, 10, 14, 20, 28px`, plus pill.
- Shadows: `xs` through `xl`, plus blue/ink shadows.
- Motion: `140ms`, `220ms`, `420ms`; easing `cubic-bezier(0.16, 1, 0.3, 1)` and `cubic-bezier(0.65, 0, 0.35, 1)`.
- Component sections: layout primitives, buttons, cards, inputs, choice cards, tooltips, badges/tags, chat/message bubbles, nav, footer, token-display utilities.

## Implementation Plan

### Phase 0 - Baseline And Guardrails

- Snapshot current dirty work with `git status --short` before edits.
- Identify brand-sensitive files and blocks.
- Identify borrowed-name offenders: `manus`, `moz` source-demo names, old palette namespaces, source-demo component names, and any other copied design-system vocabulary.
- Record the source manifest and token extraction notes.
- Create a migration checklist with expected files, acceptance checks, verification commands, and proof artifacts.

Acceptance:

- Existing user changes are not reverted.
- Brand-sensitive paths are listed before edits.
- Borrowed-name inventory exists before edits.
- Source manifest verifies.

Likely brand-sensitive paths:

- `mos/frontend/src/funnels/templates/shared/designSystemBrandLogo.ts`
- `mos/frontend/src/pages/auth/SignInPage.tsx` logo/wordmark block only
- `mos/frontend/src/pages/workspaces/BrandDesignSystemPage.tsx` brand asset controls only
- Any customer/funnel template brand asset renderers found during audit

### Phase 1 - Naming Contract And Token Extraction

- Create a raw-to-semantic token map from the bundled design-system HTML.
- Define the permanent naming contract before editing tokens:
  - product/system prefix where useful: `mos`, `ds`, or semantic names already used by the app;
  - neutral primitives for raw values: `--blue-*`, `--slate-*`, `--ink`, `--surface-*`, `--space-*`, `--radius-*`, `--shadow-*`, `--duration-*`, `--ease-*`;
  - semantic aliases only when they are the real app API: `--bg`, `--surface`, `--text`, `--primary`, `--accent`, `--danger`, `--success`, `--warning`;
  - no `--manus-*`, no Tailwind `manus.*`, no source-demo `--moz-*` token names in production source unless the user explicitly confirms that name as final product branding.
- Update `mos/frontend/src/styles/theme.css` to use the new source values under product-owned/neutral names.
- Refactor all app references to new names instead of preserving old aliases.
- Decide how dark mode maps to the new system. If the source only defines light mode, preserve current dark mode until a real dark spec exists.
- Expand spacing/type/radius/shadow/motion variables.

Acceptance:

- No app code needs raw hex colors for the new system.
- Old `--manus-*` tokens are removed from production source.
- Tailwind `manus` namespace is removed.
- Source-demo `--moz-*` tokens are not introduced as permanent app tokens.
- Any temporary alias has a proof-pack entry with reason, caller list, and deletion condition.
- Existing semantic token references still resolve.
- Brand colors/assets are not redefined as brand identity.

Expected files:

- `mos/frontend/src/styles/theme.css`
- `mos/frontend/src/styles/globals.css`
- `mos/frontend/tailwind.config.ts`
- optional generated/token map artifact under `proof_pack/mos-design-system-migration/`
- `proof_pack/mos-design-system-migration/borrowed-name-inventory.md`
- `proof_pack/mos-design-system-migration/token-naming-contract.md`

### Phase 2 - Base Typography, Layout, And Motion

- Update global heading/body rules to match the source hierarchy.
- Add display/body utility classes only when the primitive layer needs them.
- Normalize focus-visible, selection, scrollbar, disabled, and reduced-motion behavior.
- Add layout primitives for page width, section spacing, section headers, overline/eyebrow, and empty/loading surfaces.

Acceptance:

- Headings use the display font and source line-height/tracking values.
- Body uses DM Sans and source body rhythm.
- Page/section spacing comes from the token scale.
- Motion respects reduced-motion.

Expected files:

- `mos/frontend/src/styles/globals.css`
- `mos/frontend/src/styles/design-system.css`
- `mos/frontend/tailwind.config.ts`

### Phase 3 - Component Primitive Migration

Update primitives before screen work, so product screens inherit the system.

Component targets:

- `Button`: pill radius, source heights, hover halo, active scale, focus ring, primary/blue/ghost/link/destructive variants.
- `Input`, `Textarea`, `Select`: source control height, borders, focus, placeholder, error, disabled, icon slots.
- `Badge`: neutral/blue/success/warning/danger/status dots, pill shape, source type treatment.
- `Card`/section card: source padding, borders, hover, feature/testimonial/pricing-compatible variants where product UI needs them.
- `Tabs`, `Menu`, `Popover`, `Dialog`, `Tooltip`: shared surfaces, borders, elevation, focus, motion.
- `Table`: dense product-table defaults, sticky header compatibility, empty/loading states.
- `Toast`, `Progress`, `Skeleton`: system colors and motion.
- Choice cards and chat/message bubbles if currently used in onboarding/workflows.

Acceptance:

- Primitives expose variants instead of screens hand-building styles.
- Existing props remain backward-compatible unless a call site is changed in the same pass.
- Borrowed variant names/classes are renamed to product-owned or semantic names.
- No new dependency unless a primitive cannot be implemented cleanly with existing libraries.

Expected files:

- `mos/frontend/src/components/ui/button.tsx`
- `mos/frontend/src/components/ui/input.tsx`
- `mos/frontend/src/components/ui/textarea.tsx`
- `mos/frontend/src/components/ui/select.tsx`
- `mos/frontend/src/components/ui/badge.tsx`
- `mos/frontend/src/components/ui/table.tsx`
- `mos/frontend/src/components/ui/tabs.tsx`
- `mos/frontend/src/components/ui/menu.tsx`
- `mos/frontend/src/components/ui/popover.tsx`
- `mos/frontend/src/components/ui/dialog.tsx`
- `mos/frontend/src/components/ui/tooltip.tsx`
- `mos/frontend/src/components/ui/toast.tsx`
- `mos/frontend/src/components/ui/progress.tsx`
- `mos/frontend/src/components/ui/skeleton.tsx`
- `mos/frontend/src/styles/design-system.css`

### Phase 4 - Product Surface Migration

Refactor high-frequency product UI after primitives are stable.

Target sequence:

1. Shell/navigation/sidebar/header surfaces.
2. Workspace onboarding and first-run UI, excluding logo/wordmark identity.
3. Campaign detail and strategy workflow panels.
4. Experiments, swipes, and provider/meta screens.
5. Brand settings layout chrome only, excluding brand asset controls.
6. Markdown/report rendering where it visibly clashes.

Acceptance:

- Screens stop repeating one-off card, status, empty, loading, and action-bar styles.
- Screens no longer reference old borrowed namespaces/classes.
- Product UI reads as one system across routes.
- No marketing pages or funnel templates are redesigned.

Expected files:

- `mos/frontend/src/app/*`
- `mos/frontend/src/layouts/*` if present
- `mos/frontend/src/pages/**/*.{tsx,ts}`
- `mos/frontend/src/components/**/*.{tsx,ts}`
- `mos/frontend/src/styles/markdown.css`

### Phase 5 - Brand Freeze And Borrowed-Name Check

- Add a local script or contract check that fails if protected brand identity files changed unexpectedly.
- Add a local script/check that scans production source for forbidden borrowed names.
- For files that must be touched for layout, restrict the diff to wrappers, spacing, or non-brand controls.
- Add a manual diff review entry to the proof pack for brand-sensitive files.

Acceptance:

- `designSystemBrandLogo.ts` remains unchanged unless the user explicitly approves brand work.
- Logo SVG/wordmark/naming blocks in sign-in and brand settings remain unchanged.
- Customer/funnel brand output is untouched.
- Production source has no `manus` references.
- Production source has no copied `moz` source-token names unless explicitly approved as final product naming.
- Alias exceptions file is empty or contains only justified temporary entries.

Expected artifact:

- `proof_pack/mos-design-system-migration/brand-freeze-review.md`
- `proof_pack/mos-design-system-migration/borrowed-name-scan.log`
- `proof_pack/mos-design-system-migration/alias-exceptions.md`

### Phase 6 - Verification And Proof

Run local checks:

- `cd mos/frontend && yarn test:unit`
- `cd mos/frontend && yarn check:semantic-ui`
- `cd mos/frontend && yarn build`
- Borrowed-name scan against `mos/frontend/src` and `mos/frontend/tailwind.config.ts`.
- Targeted Playwright smoke against app routes after starting Vite.
- Authenticated MOS preview validation only if the implementation touches preview/editor flows: `cd mos/frontend && node scripts/validate-site-preview.mjs`

Visual proof:

- Desktop and mobile screenshots for representative product routes.
- Before/after notes for migrated primitives.
- Brand-freeze diff notes.
- Borrowed-name scan log and alias exception review.
- Contract verification with `planctl verify`.
- Proof dashboard under `proof_pack/mos-design-system-migration/index.html`.

Acceptance:

- Tests/build pass or blocked items are documented with exact reason.
- Screenshots show no overlap, broken text, blank states, or obvious old/new style clash.
- Brand-freeze check passes.
- Borrowed-name check passes.

## Acceptance Checks

- Canonical tokens exist and are used by Tailwind.
- Borrowed names are removed from production source.
- No permanent alias layer exists for old names.
- Core primitives use new system values.
- Product screens consume primitives/semantic tokens.
- Brand identity elements unchanged.
- No fake data added.
- No marketing/funnel/deploy work performed.
- `capturectl verify` passes for the source manifest.
- `plangatecheck` passes for this plan.
- Name scan passes or exceptions are documented as temporary.
- During implementation, `planctl verify` passes before final report.

## Parallelization Map

parallelizable: yes.

Independent lanes:

- Lane A, read-only audit: source extraction, current token/component inventory, brand-sensitive file list, borrowed-name inventory.
- Lane B, token implementation: `theme.css`, `globals.css`, Tailwind mapping.
- Lane C, primitive implementation: `components/ui/*`, `design-system.css`.
- Lane D, product surfaces: route/page migration after lanes B/C stabilize.
- Lane E, verification: tests, build, screenshots, brand-freeze review, proof dashboard.

Expected speed gain:

- Medium. Audit and verification can run in parallel with token/component work. Product-surface migration should wait for primitives.

Token spend justification:

- Worth using sub-agents during `Ship the plan` for audit and verification lanes because they are independent and reduce main-thread context load.

Write ownership:

- Lane B owns token/style config files.
- Lane C owns `src/components/ui/*` and shared component CSS.
- Lane D owns product route/page files only after B/C are merged.
- Lane E owns proof artifacts and validation notes.
- No lane owns brand identity files unless explicitly approved.
- Borrowed-name cleanup can be split by file ownership, but no two lanes should rename the same namespace in overlapping files.

Fan-in plan:

- Main thread integrates token and primitive work first.
- Product screens migrate after primitives compile.
- Verification lane checks diffs, screenshots, and brand-sensitive paths before final.

Validation owner:

- Main thread, with verification sidecar allowed during `Ship the plan`.

Meta-tooling opportunity:

- Add a small `scripts/check-design-system-migration.mjs` that reports raw hex colors, protected brand file changes, forbidden borrowed names, alias exceptions, unsupported radius/spacing classes, and primitive bypass patterns.

## Failure Modes

- Shallow diagnosis: treating this as a color swap. Mitigation: migrate token/component machinery first.
- Symptom plan: styling pages without primitives. Mitigation: primitive-first order.
- Willpower plan: relying on reviewers to notice brand/naming drift. Mitigation: brand-freeze and borrowed-name scripts/checks.
- Perfect-day plan: assuming all pages can migrate cleanly. Mitigation: core screens first, leave blocked pages documented.
- Missing metrics: no pass/fail proof. Mitigation: contract, tests, screenshots, brand-freeze notes.
- Overengineered plan: building a full design-token compiler. Mitigation: use CSS variables/Tailwind mapping unless repeated friction demands a script.
- Scope creep: marketing/funnel redesign sneaks in. Mitigation: non-goals and protected paths.
- Alias creep: preserving old names forever. Mitigation: no aliases unless necessary, exception ledger with deletion condition.

## Worst-Day Test

If the app has dirty user changes, partial old styling, stale auth, or a route fails to render, the migration still succeeds if:

- Core tokens and primitives compile.
- Borrowed names are removed even if it forces call-site repairs.
- High-frequency routes render with no visual breakage.
- Brand identity files remain unchanged.
- Blocked routes are documented with exact cause and not papered over with fake states.

## Metrics

Leading metrics:

- Count of primitives migrated.
- Count of hardcoded raw color/radius/spacing offenders reduced.
- Count of `manus`/borrowed-name references reduced to zero in production source.
- Count of alias exceptions, target zero.
- Count of high-frequency routes using shared primitives.
- Verification commands passed.

Lagging metrics:

- Product UI is visually coherent across representative routes.
- Future screen work can use primitives without ad hoc styling.
- The internal system vocabulary is MOS-owned or neutral, not copied.
- Brand identity diff remains zero or explicitly approved.

## Owner, Date, Review

- Owner: Codex implementation lane under user approval.
- Plan date: 2026-05-20.
- Review point: after implementation proof pack is green, before any production/deploy work.

## Blocked Inputs

No blocker for the plan.

Implementation blockers to surface if hit:

- Missing final brand identity spec, if a requested change touches brand elements.
- Auth/session failure for preview/editor validation.
- Existing dirty user edits that overlap a planned file and cannot be separated cleanly.

## Stop Condition

Planning is complete when:

- `plan-gate-proof.json` exists.
- `plangatecheck` passes.
- The user can say `Ship the plan` to execute without needing another planning pass.

Say "Ship the plan" when you want me to implement and verify it.
