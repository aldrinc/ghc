# Onboarding Review Screen Redesign Plan

Date: 2026-05-20
Status: approved for implementation
Root: `/Users/aldrinclement/Documents/programming/marketi`

## Decision

Replace the onboarding review step's editable form surface with a read-only review screen and a separate edit view.

The review screen should answer:

- What will be created or changed?
- What is missing or optional?
- Is the setup safe to submit?

The edit view should answer:

- Which field do I need to change?
- How do I return to review?

## Goal

Make the workspace review step scannable in under 10 seconds without removing the ability to edit extracted or manually entered data before workspace creation.

Key results:

- Review screen starts read-only.
- Missing required fields and optional pricing gaps appear before normal details.
- Workspace, offer, pricing, and competitors are grouped into label/value sections.
- Editing happens in a focused edit view, not inside the default review layout.
- Existing and new business submit behavior remains unchanged.

## Problem

The current review screen mixes review and editing. It shows `Workspace changes`, then immediately renders a full editable form with inputs, dropdowns, and textareas. This makes quick review slow because the user has to parse control chrome instead of facts.

## Diagnosis

Root cause: one UI surface is doing three jobs: extracted-data review, missing-data resolution, and full form editing. Those jobs need separate modes.

## Current Machine

1. User reaches `existing-review` or `new-review`.
2. UI title asks `Does this look right?`.
3. UI shows `Workspace changes`.
4. UI renders all editable fields inline.
5. User must scan form controls to decide whether to create the workspace.

## Designed Machine

1. User reaches `existing-review` or `new-review`.
2. UI title says `Review workspace`.
3. UI shows attention items first.
4. UI shows a compact change summary.
5. UI shows read-only grouped review sections.
6. Section edit buttons open a focused edit view.
7. `Edit all details` opens the full edit view.
8. Save returns to review.
9. Create workspace uses the same existing payload path.

## Implementation Items

- P01: Add read-only review model helpers for field labels, display values, attention items, pricing status, and competitor URL display.
- P02: Replace default review form with read-only review sections and a top attention area.
- P03: Add focused edit views for workspace, offer, pricing, competitors, and all details.
- P04: Preserve existing create-workspace payload behavior and existing/new business paths.
- P05: Update tests to assert the review screen is read-only by default and editing is explicit.

## Speed Map

- parallelizable: no
- single-agent reason: implementation is centered in `OnboardingWizard.tsx` and the existing test file; overlapping edits would create merge risk.
- expected speed gain: local parallel reads and verification are enough.
- token spend justification: native subagents not worth it for a focused two-file UI change.
- write ownership: main thread owns `OnboardingWizard.tsx`, `OnboardingWizard.test.tsx`, and proof files.
- fan-in plan: no multi-agent fan-in required.
- validation owner: main thread runs targeted tests, build, lanecheck, planctl, and proofdash.
- meta-tooling opportunity: none yet; this is a product-specific review state.

## Acceptance Checks

- Review step heading is `Review workspace`.
- Review mode does not render editable business, offer, pricing, or competitor controls by default.
- `Edit all details` exposes the existing editable field set.
- Section edit actions expose focused editable fields.
- Missing pricing is displayed as an optional gap and can be edited without blocking create.
- Targeted onboarding wizard tests pass.
- Frontend build passes.
