# Onboarding Foundation Step Scope Verification

Date: 2026-05-21

## Result

PASS with local test runner blocked by missing Postgres on `localhost:5433`.

## Checks

- PASS: `python -m py_compile mos/backend/app/routers/clients.py mos/backend/app/temporal/workflows/strategy_v2.py mos/backend/app/temporal/activities/strategy_v2_activities.py`
- PASS: manual helper smoke verified `include_step06=False` runs only `01`, `03`, `04`.
- PASS: manual workflow smoke verified `foundation_only=True` accepts no `stage1`/Step 06 and persists the foundation bundle.
- PASS: `npm run build` in `mos/frontend`.
- PASS: `git diff --check` on touched files.
- PASS: onboarding UI copy no longer exposes internal foundational step numbers.
- PASS: `planctl verify docs/plans/2026-05-21-onboarding-foundation-step-scope-plan.contract.json --run`.
- PASS: proof dashboard rendered to `proof_pack/onboarding-foundation-step-scope-2026-05-21/index.html`.
- PASS: Step 04 default provider is now `deerflow`; GPT remains available by setting `STRATEGY_V2_FOUNDATIONAL_STEP04_PROVIDER=gpt`.
- PASS: Step 03 default model is now `deepseek-v4-pro` through `STRATEGY_V2_FOUNDATIONAL_STEP03_MODEL`.
- BLOCKED: focused `pytest` cannot load `mos/backend/tests/conftest.py` because Postgres on `localhost:5433` refuses connections.
- BLOCKED: full touched-file `ruff check` is dominated by pre-existing lint errors in large legacy files. Runtime syntax was covered by `py_compile`; frontend build passed.

## Scope

Onboarding foundation-only now uses required docs:

- `v2-02.foundation.01`
- `v2-02.foundation.03`
- `v2-02.foundation.04`

Full Strategy V2 downstream paths still keep Step 06 where avatar brief context is required.
