# Onboarding Foundation Readiness Gate Plan

## Decision
Replace onboarding completion routing from `client_onboarding.status=completed` to a product-scoped foundation readiness state derived from the Strategy V2 foundation run and required foundational artifacts. Keep users on setup until readiness is true. Route to a new post-foundation landing page first, not workspace overview.

## Goal (Dalio Step 1)
- Within one release, new onboarding users do not enter workspace overview until foundational docs are complete and validated.
- 0 premature redirects from onboarding setup screen to workspace overview when foundation is still running.
- 100% of successful onboarding runs land on the new post-foundation landing page before overview.

## Problem (Dalio Step 2)
- Observable: onboarding page redirects when `client_onboarding` completes, even though foundational research is still running.
- Evidence:
  - `mos/frontend/src/components/clients/OnboardingWizard.tsx:842-847` redirects on `setupWorkflowDetail.run.status === "completed"`.
  - `mos/backend/app/temporal/workflows/client_onboarding.py:51-71` starts Strategy V2 as child with `ParentClosePolicy.ABANDON` and returns immediately.
- Impact: users reach overview before foundation docs/research are ready, creating inconsistent state and weak first-run experience.

## Diagnosis (Dalio Step 3)
- Root cause: UI completion signal tracks parent orchestration run (`client_onboarding`) instead of the true unit-of-readiness (Strategy V2 foundation run + foundational artifacts).
- System flaw:
  - Wrong lifecycle boundary selected for navigation.
  - No explicit workspace readiness contract exposed to frontend.
  - Overview entry points are not guarded by readiness.

## Current Machine
- Wizard starts marketing-agent setup -> backend creates `client_onboarding` run.
- `client_onboarding` launches Strategy V2 child asynchronously and exits.
- Frontend polls parent run and redirects to `/workspaces/overview` once parent is complete.
- No canonical readiness state for foundation completion.

## Designed Machine
- Backend exposes canonical readiness state for `(workspace, product)`:
  - `foundation_pending`
  - `foundation_failed`
  - `foundation_ready`
- Readiness criteria (strict):
  - latest relevant `strategy_v2` run exists,
  - status is `completed`,
  - `strategy_v2_state.current_stage === "foundation_complete"`,
  - required foundational step artifacts present (`v2-02.foundation.01`, `.03`, `.04`, `.06`).
- Wizard success screen polls readiness state, not parent onboarding run.
- Routing contract:
  - pending/failed => remain on setup page.
  - ready => route to new post-foundation page (new route), then user chooses continue to overview.
- Workspace overview entry is guarded by readiness resolver for first-run contexts.

## Implementation Plan (Dalio Step 4 Design)
1. Add backend workspace readiness endpoint and schema.
2. Implement readiness service that resolves latest product-scoped Strategy V2 run and validates foundation criteria.
3. Return explicit error when readiness cannot be determined (no silent fallback).
4. Add frontend readiness API hook + polling utility.
5. Refactor onboarding success screen logic to drive state from readiness endpoint.
6. Create new post-foundation landing page route and UI scaffold.
7. Add route resolver/guard for overview entry during first-run setup.
8. Add backend + frontend tests for ready/pending/failed paths and navigation transitions.
9. Add instrumentation events for state transitions and redirect decisions.

## Doing (Dalio Step 5)
1. Backend lane
   - Files (likely):
     - `mos/backend/app/routers/clients.py` or new readiness router
     - `mos/backend/app/schemas/onboarding.py` or new readiness schema file
     - `mos/backend/app/db/repositories/workflows.py` (query helper)
     - `mos/backend/tests/...` readiness tests
   - Output: deterministic readiness API response with strict criteria.
2. Frontend lane
   - Files (likely):
     - `mos/frontend/src/api/clients.ts`
     - `mos/frontend/src/components/clients/OnboardingWizard.tsx`
     - `mos/frontend/src/pages/workspaces/WorkspaceOnboardingPage.tsx`
     - `mos/frontend/src/pages/workspaces/WorkspaceFoundationReadyPage.tsx` (new)
     - `mos/frontend/src/App.tsx`
     - route-guard helper (new)
     - `mos/frontend/src/...test.tsx`
   - Output: onboarding remains on setup until ready; then lands on new page.
3. Validation lane
   - Run targeted backend/frontend tests and manual onboarding flow verification.

## Success Criteria
- No redirect from onboarding setup while readiness is `foundation_pending`.
- Redirect occurs only when readiness is `foundation_ready`.
- First landing after readiness is new page, not overview.
- Overview route guard blocks premature access during first-run setup.
- Failed foundation run shows actionable failed state and retry path.

## Acceptance Checks
1. Given new onboarding, when client_onboarding completes but strategy_v2 is still running, setup page remains visible.
2. Given strategy_v2 foundation completion + required artifact keys, setup transitions to new post-foundation page.
3. Given missing required foundational keys, readiness remains pending/failed (never ready).
4. Given direct visit to `/workspaces/overview` during pending state, guard reroutes to setup status page.
5. Given failed strategy_v2 foundation run, onboarding page shows failure status and retry CTA.

## Verification Commands
- `cd /Users/aldrinclement/Documents/programming/marketi/mos/backend && pytest tests`
- `cd /Users/aldrinclement/Documents/programming/marketi/mos/frontend && npm run test -- --runInBand`
- Manual flow: onboarding create -> observe pending state -> complete foundation -> verify landing page redirect.

## Preemptive Failure Modes
- Using run status only without artifact validation => false-ready state.
- Choosing wrong strategy run in multi-run workspace => stale readiness.
- Race condition between readiness flip and route transition => redirect loop.
- Adding fallback inference when endpoint data is missing => hidden broken state.
- Guarding only onboarding flow but not direct overview route => bypass.

## Worst-Day Test
- Foundation processing is slow (30-60 min), intermittent polling failures, and user refreshes/navigates away repeatedly.
- Expected behavior: deterministic pending screen resumes, no premature overview access, no silent fallback.

## Metrics
- Leading:
  - `onboarding_readiness_poll_success_rate`
  - `onboarding_readiness_state_transition_count`
  - `overview_guard_redirect_count`
- Lagging:
  - `% onboarding sessions with premature overview entry` (target 0%)
  - `% onboarding sessions landing on new post-foundation page after ready` (target 100%)
  - support incidents about missing foundation docs after onboarding (target downtrend)

## Parallelization Map
- `parallelizable`: yes
- Lanes:
  - Lane A backend readiness contract
  - Lane B frontend onboarding/route behavior
  - Lane C tests + instrumentation validation
- Expected speed gain: high (backend and frontend are mostly disjoint write scopes).
- Token spend justification: moderate; avoids serial context churn and shortens cycle time.
- Write ownership:
  - A: backend router/schema/repo/tests
  - B: frontend hooks/components/routes
  - C: test files + verification logs only
- Fan-in point: onboarding flow integration in `OnboardingWizard` + route config.
- Fan-in plan: merge backend contract first, then frontend integration, then run validation suite.
- Validation owner: Lane C + final orchestrator pass.

## Single-Agent Reason (if parallel blocked)
- If native sub-agents are blocked by runtime policy, execute same lane order sequentially with local parallel command execution.

## Meta-Tooling Opportunity
- Add reusable `workspace readiness` module + shared constants for foundational step keys across backend/frontend to eliminate drift.
- Add a single test helper that fabricates workflow timelines for onboarding/strategy runs to reduce future setup-state regressions.

## Owner / Date / Review
- Owner: main
- Plan date: 2026-05-21
- Review checkpoint: after backend readiness contract tests + before frontend guard merge.

## Stop Condition
Planning complete when:
- readiness contract is explicit and testable,
- acceptance checks are unambiguous,
- `plan-gate-proof.json` passes `plangatecheck`,
- implementation handoff is ready for `Ship the plan`.

Say "Ship the plan" when you want me to implement and verify it.
