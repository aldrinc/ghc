# Modal Readability Repair Plan

## Decision

Fix modal readability at the shared `Dialog` and `AlertDialog` primitives first. Do not patch each modal one by one.

The immediate issue is vertical rhythm: title and description sit too close, because the primitive title/description components do not own header spacing. Some call sites add `mt-1` or `mt-2`; the delete workspace modal does not, so readability depends on caller memory.

## Goal

By the end of implementation, all MOS modal headers should have readable default spacing without requiring every caller to add `mt-*`.

Measurable target:

- `DialogTitle` / `AlertDialogTitle` and description text have consistent default separation.
- Modal body/actions keep consistent spacing from the header.
- Existing call-site spacing overrides do not double-stack into awkward gaps.
- Component review page shows the fixed default state.
- Unit/design-system checks pass.

## Problem

Observable problem from the screenshot and code:

- `AlertDialogTitle` uses `font-display text-2xl font-semibold tracking-tighter text-content`.
- `AlertDialogDescription` uses `text-sm text-content-muted`.
- There is no default margin, line-height tuning, or header group primitive between them.
- The delete workspace modal renders title immediately followed by description in `mos/frontend/src/pages/workspaces/WorkspacesPage.tsx`.
- `mos/frontend/src/pages/dev/ComponentReviewPage.tsx` manually adds `className="mt-2"` for dialog examples, proving the primitive default is incomplete.

## Diagnosis

Root cause: header rhythm is delegated to call sites instead of encoded in the modal primitive.

Current machine:

- `DialogContent`/`AlertDialogContent` provide panel shell only.
- `DialogTitle`/`AlertDialogTitle` provide type styling only.
- `DialogDescription`/`AlertDialogDescription` provide color/size only.
- Call sites manually decide title-description spacing, body spacing, and action spacing.

Designed machine:

- Modal primitives define readable header defaults.
- Call sites use semantic primitives and only override spacing for unusual layouts.
- Component review page becomes the visual fixture for default modal anatomy.
- Design-system checks protect against drift.

## Design System Review

Relevant existing system:

- Type scale lives in `mos/frontend/src/styles/theme.css`: `--text-sm: 13px`, `--text-2xl: 26px`, line-height aliases, display font `Libre Baskerville`, body font `DM Sans`.
- Spacing scale is 4-based: `--space-1` through `--space-13`.
- Floating surfaces use `mos/frontend/src/components/ui/floating.ts`: `rounded-lg`, `border-[1.5px]`, `bg-surface`, `text-sm`, `shadow-xl`, motion tokens.
- Dialog primitives live in `mos/frontend/src/components/ui/dialog.tsx`.
- Alert dialog primitives live in `mos/frontend/src/components/ui/alert-dialog.tsx`.
- Component review route already covers dialog and alert dialog examples.

Recommendation:

- Use existing spacing tokens through Tailwind classes (`mt-2`, `mt-5`, `mt-6`, `space-y-*`) rather than adding new CSS variables.
- Keep title type treatment unless visual QA proves it is overpowering.
- Improve description readability with `leading-normal` or `leading-5` and a sane max width if needed.

## Implementation Plan

### Phase 1 - Baseline Audit

- Audit all `DialogDescription` and `AlertDialogDescription` uses.
- Identify manual `mt-*` overrides that would double up after primitive defaults.
- Confirm whether any dialogs intentionally need tight title/body spacing.

Acceptance:

- List of affected call sites is known before edits.
- No production modal gets accidental double spacing.

### Phase 2 - Primitive Fix

- Update `DialogDescription` and `AlertDialogDescription` defaults to include readable top margin and line height.
- Prefer `mt-2 text-sm leading-normal text-content-muted` or equivalent based on screenshot QA.
- Consider adding `max-w-prose` only if long modal copy becomes too wide; avoid unnecessary width changes.
- Keep `className` merge order so caller overrides still work.

Expected files:

- `mos/frontend/src/components/ui/dialog.tsx`
- `mos/frontend/src/components/ui/alert-dialog.tsx`

Acceptance:

- Delete workspace modal reads clearly with no call-site-specific spacing.
- Callers can still override className.
- No new dependency.

### Phase 3 - Call-Site Cleanup

- Remove redundant `className="mt-1"` / `className="mt-2"` from standard modal descriptions where the primitive now owns spacing.
- Keep explicit spacing only for non-standard layouts, documented by local context.
- Leave destructive confirmation copy unchanged.

Likely files:

- `mos/frontend/src/pages/dev/ComponentReviewPage.tsx`
- `mos/frontend/src/components/campaigns/SwipeCollectionSelector.tsx`
- Any other modal call sites found in Phase 1.

Acceptance:

- Standard modals do not double-stack margins.
- Unusual modal layouts remain intact.

### Phase 4 - Visual Fixture

- Update component review modal examples to show default title/description spacing with no manual margin.
- If useful, add one long-description case so line-height can be judged.

Expected file:

- `mos/frontend/src/pages/dev/ComponentReviewPage.tsx`

Acceptance:

- Component review page demonstrates the fixed default.
- Alert dialog and standard dialog both covered.

### Phase 5 - Verification

Run:

```bash
cd mos/frontend
npm run --silent check:design-system
npm run --silent test:unit -- --runInBand
```

If `--runInBand` is not supported by Vitest, run:

```bash
cd mos/frontend
npm run --silent test:unit
```

Visual verification:

- Open the MOS dev UI or component review route.
- Capture modal screenshots before/after if the route is accessible.
- Confirm title, description, body, and action row spacing at desktop and narrow viewport.

## Success Criteria

- The screenshot issue is fixed by shared primitives, not a one-off workspace modal patch.
- Existing modal content remains the same.
- Standard modal descriptions have visible separation from titles.
- Long descriptions remain readable.
- No new fallback behavior.
- No model, backend, deployment, or production changes.

## Failure Modes

- Shallow diagnosis: only add `mt-2` to delete workspace modal, leaving the primitive broken.
- Symptom patch: fix one alert dialog but not normal dialogs.
- Overcorrection: add too much margin and make compact modals feel loose.
- Double spacing: primitive adds `mt-2` while call sites keep `mt-2`, creating `mt-4` visual effect.
- Scope creep: rewrite modal layout, typography, or button system when the current problem is header readability.

## Worst-Day Test

On a bad day, a new engineer adds a modal with only:

```tsx
<AlertDialogTitle>Delete item</AlertDialogTitle>
<AlertDialogDescription>This cannot be undone.</AlertDialogDescription>
```

It must still be readable without remembering a spacing class.

## Metrics

Leading:

- Count of standard modal descriptions with manual `mt-*` decreases.
- Shared primitives contain default title-description spacing.

Lagging:

- Component review screenshots show readable title-description separation.
- Design-system and unit checks pass.
- No new modal readability complaints from standard modal usage.

## Parallelization

parallelizable: no.

Single-agent reason: this is a small primitive-level UI repair. Parallel agents would add handoff cost without meaningful speed gain.

Write ownership:

- Main agent owns modal primitives, component review examples, and affected call-site cleanup.

Validation owner:

- Main agent runs checks and visual QA.

Fan-in plan:

- Not needed.

Expected speed gain:

- Single lane is fastest.

Token spend justification:

- No sub-agent spend. Scope is narrow.

## Meta-Tooling Opportunity

Add or extend a component-review visual fixture for modal anatomy so future design-system changes can be judged in one place. If modal regressions recur, add a tiny Playwright visual smoke script that opens the component review route and captures standard dialog states.

## Owner / Review

Owner: Codex implementation agent.

Review point: after `Ship the plan`, before final report, compare screenshots and verification output.

Stop condition: plan is ready for implementation when the user says `Ship the plan.`

## Plan Gate

Plan gate proof:

- `proof_pack/modal-readability-2026-05-21/plan-gate-proof.json`

Expected command:

```bash
/Users/aldrinclement/.codex/bin/plangatecheck proof_pack/modal-readability-2026-05-21/plan-gate-proof.json
```

