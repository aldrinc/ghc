# Onboarding Foundation E2E

## Goal

Run a full local onboarding E2E for a new-business workspace and prove that the foundation-only backend process starts, the UI shows progress, and the workspace unlocks when the foundation bundle is ready.

## Problem

The backend foundation-only scope has been wired, but it needs a real UI-driven run to verify the onboarding handoff, readiness polling, waiting state, and final unlock behavior.

## Design

- Use existing MOS local dev services where available; start missing local services only.
- Sign in with repo-local MOS test auth credentials.
- Create a new-business workspace through the actual onboarding UI.
- Capture screenshots at each meaningful screen.
- Confirm backend created workflow and foundation bundle artifacts.
- Wait for readiness to become `foundation_ready` or capture failure details.
- Do not run Step 06.

## Acceptance

- UI onboarding can submit a new-business workspace.
- Waiting/progress screen appears after submit.
- Backend starts client onboarding and strategy foundation workflow.
- Readiness endpoint gates while pending and unlocks when ready.
- Screenshot artifacts exist for each screen.
- If blocked, blocker is concrete with logs and DB/API evidence.

## Verification

- Browser screenshots saved under `proof_pack/onboarding-foundation-e2e-2026-05-21/screenshots/`.
- Backend/API readiness checks saved under `proof_pack/onboarding-foundation-e2e-2026-05-21/`.
- `planctl verify docs/plans/2026-05-21-onboarding-foundation-e2e-plan.contract.json --run`
