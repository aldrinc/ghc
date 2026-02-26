# Strategy V2 Source-of-Truth Checklist (2026-02-23)

## Runtime Validation Run
- Fresh run in progress: `workflow_run_id=318541e9-6660-4e79-88ee-c3c824811f3d`
- Temporal workflow id: `strategy-v2-41c2ac3c-91a2-4f00-ba55-c0d2a190b2a7-c4dc509f-6d7e-4a60-b499-de351e796fb0-c1eb6b1d-1d0e-4c9b-ada8-ec1f8284fd40-6e206bbb-beb0-4fff-83b5-078835111103`
- Progress indicator working (`pending_activity_progress` heartbeat visible) while stage `v2-02` foundational prompts execute.
- Note: provider calls are long-running; execution has not reached HITL gates yet at this snapshot.

## Fix 01 — Runtime Prompt-Chain Parity

### WP1 Prompt runtime foundation
- Status: `Implemented`
- Evidence:
  - Strict prompt resolution with single-match enforcement: `mos/backend/app/strategy_v2/prompt_runtime.py:54`
  - Missing placeholder hard-fail: `mos/backend/app/strategy_v2/prompt_runtime.py:75`
  - Prompt provenance object (path/SHA/model/contracts): `mos/backend/app/strategy_v2/prompt_runtime.py:25`

### WP2 Stage 2B parity rewrite
- Status: `Implemented`
- Evidence:
  - Agent 0/0b/1/2/3 prompt-chain execution + persisted artifacts (`v2-02..v2-06`): `mos/backend/app/temporal/activities/strategy_v2_activities.py:2316`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:2831`
  - Agent 2 DUAL MODE runtime contract includes `DUAL_MODE_REQUIRED: true`: `mos/backend/app/temporal/activities/strategy_v2_activities.py:2569`
  - STEP4 corpus transformation path: `mos/backend/app/strategy_v2/translation.py:473`

### WP3 Offer orchestrator integration
- Status: `Implemented`
- Evidence:
  - Orchestrator + step prompts (01..03 in run_offer_pipeline, 04..05 in variants activity): `mos/backend/app/temporal/activities/strategy_v2_activities.py:3427`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:3594`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:3881`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:4209`
  - Awareness matrix sourced from Offer step output and persisted: `mos/backend/app/temporal/activities/strategy_v2_activities.py:3587`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:3710`

### WP4 Copywriting prompt-template integration
- Status: `Implemented`
- Evidence:
  - Template prompts for headline/promise/advertorial/sales: `mos/backend/app/temporal/activities/strategy_v2_activities.py:4648`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:4711`
  - Promise contract extracted from winning headline (not hardcoded): `mos/backend/app/temporal/activities/strategy_v2_activities.py:4768`

### WP5 Artifacts/provenance/observability
- Status: `Implemented`
- Evidence:
  - Prompt provenance captured per chain and validated: `mos/backend/app/temporal/activities/strategy_v2_activities.py:4936`, `mos/backend/app/strategy_v2/copy_semantic_gates.py:449`
  - Step payload persistence for stage 2-4 chain outputs: `mos/backend/app/temporal/activities/strategy_v2_activities.py:687`

## Fix 02 — HITL Enforcement & Decision Integrity

### WP1 Contract hardening (decision_mode/reviewed IDs/attestation)
- Status: `Missing`
- Evidence:
  - Decision contracts only include operator IDs + selection fields; no `decision_mode`/attestation fields: `mos/backend/app/strategy_v2/contracts.py:185`

### WP2 API identity binding on signal endpoints
- Status: `Missing`
- Evidence:
  - Signal endpoints validate request body directly and pass `operator_user_id` through without stamping from `auth.user_id`: `mos/backend/app/routers/workflows.py:833`, `mos/backend/app/routers/workflows.py:858`, `mos/backend/app/routers/workflows.py:883`, `mos/backend/app/routers/workflows.py:908`, `mos/backend/app/routers/workflows.py:933`, `mos/backend/app/routers/workflows.py:958`

### WP3 Activity-level manual-decision enforcement
- Status: `Implemented (baseline)`
- Evidence:
  - Blocked system/automation IDs and prefixes enforced in activity layer: `mos/backend/app/temporal/activities/strategy_v2_activities.py:203`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:212`

### WP4 Missing H1/H2 gates in workflow
- Status: `Implemented`
- Evidence:
  - H1 `v2-02a` and H2 `v2-02b` mandatory waits + decision finalization: `mos/backend/app/temporal/workflows/strategy_v2.py:255`, `mos/backend/app/temporal/workflows/strategy_v2.py:281`

### WP5 Audit trail & decision provenance depth
- Status: `Partial`
- Evidence:
  - Decision payload artifacts are persisted at each gate, but enriched attestation schema from plan is not present: `mos/backend/app/temporal/activities/strategy_v2_activities.py:2929`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:2995`, `mos/backend/app/strategy_v2/contracts.py:185`

## Fix 03 — Copy Depth, Structure, Promise Delivery Gates

### WP1 Promise contract fidelity
- Status: `Implemented`
- Evidence:
  - Promise contract extracted from prompt and carried into payload: `mos/backend/app/temporal/activities/strategy_v2_activities.py:4768`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:4998`

### WP2 Copy quality gate module
- Status: `Partial (semantic gates implemented, explicit word-floor module from plan not present)`
- Evidence:
  - Deterministic semantic gates (section coverage, CTA window, guarantee proximity, promise timing): `mos/backend/app/strategy_v2/copy_semantic_gates.py:183`
  - Planned standalone module `copy_quality.py` is absent.

### WP3 Stage 4 structural rewrite
- Status: `Implemented`
- Evidence:
  - Template-driven generation for presell/sales and contract-bound structure checks: `mos/backend/app/temporal/activities/strategy_v2_activities.py:4817`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:4878`

### WP4 Runtime gate integration
- Status: `Implemented`
- Evidence:
  - Sequence includes headline scoring + QA, promise extraction, page generation, semantic gates, congruency hard gates: `mos/backend/app/temporal/activities/strategy_v2_activities.py:4692`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:4768`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:4844`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:4892`

### WP5 Observability and diagnostics
- Status: `Partial`
- Evidence:
  - `copy_payload.semantic_gates` and provenance diagnostics are included: `mos/backend/app/temporal/activities/strategy_v2_activities.py:5004`
  - Explicit word-count diagnostics and reason-code taxonomy from plan are not fully represented.

## Test Evidence Run This Session
- `tests/test_strategy_v2_workflow_api.py` selected HITL/state tests: passed (`3 passed`)
- `tests/test_strategy_v2_translation_and_scorers.py`: passed
- `tests/test_strategy_v2_copy_pipeline_guards.py`: passed

## Current Blocking Risk
- Provider-side latency/in-progress bottleneck in foundational web-enabled calls can materially delay full-run validation and gate progression. This is operationally visible and now trackable via `pending_activity_progress` heartbeat.
