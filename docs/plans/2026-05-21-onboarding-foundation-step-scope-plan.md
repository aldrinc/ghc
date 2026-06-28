# Onboarding Foundation Step Scope

## Goal

Onboarding foundation-only setup must run and gate on foundational docs 01, 03, and 04 only. It must not run or require foundational Step 06.

## Problem

The current onboarding foundation-only path still expects `v2-02.foundation.06` in readiness and the foundational research activity still runs Step 06 before persisting the foundation bundle.

## Design

- Pass `foundation_only` into the foundational research activity.
- For `foundation_only=true`, run and persist only steps `01`, `03`, and `04`.
- Skip Stage 1 translation for foundation-only bundles because the current Stage 1 translator depends on Step 06 avatar brief data.
- Keep the full Strategy V2 path unchanged: it still runs Step 06 where downstream stages need avatar context.
- Update readiness to require only `01`, `03`, and `04`.
- Update onboarding UI ETA text to match the new DSV4-heavy flow.

## Acceptance

- Onboarding foundation-only activity never calls Step 06.
- Readiness returns ready when `01`, `03`, and `04` are present.
- Full Strategy V2 still requires Step 06.
- Focused backend tests pass.
- Frontend typecheck/lint for touched files passes where available.

## Verification

- `python -m py_compile mos/backend/app/routers/clients.py mos/backend/app/temporal/workflows/strategy_v2.py mos/backend/app/temporal/activities/strategy_v2_activities.py`
- `pytest mos/backend/tests/test_api.py::test_foundation_readiness_ready_when_bundle_complete mos/backend/tests/test_strategy_v2_workflow_ordering.py::test_strategy_v2_foundation_only_finishes_after_foundational_bundle -q`
- `ruff check mos/backend/app/routers/clients.py mos/backend/app/temporal/workflows/strategy_v2.py mos/backend/app/temporal/activities/strategy_v2_activities.py mos/backend/tests/test_api.py mos/backend/tests/test_strategy_v2_workflow_ordering.py`
