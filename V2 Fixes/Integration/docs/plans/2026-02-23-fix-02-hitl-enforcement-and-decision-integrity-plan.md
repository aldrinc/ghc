# Fix 02 Plan — HITL Enforcement and Decision Integrity

**Date:** 2026-02-23
**Status:** Draft for implementation
**Owner:** Strategy V2 workflow + API layer
**Primary objective:** Enforce mandatory, auditable human decisions across Strategy V2 so no stage can be advanced by implicit or pseudo-human automation.

---

## 1) Problem Statement

The workflow has signal-based decision pauses, but decision integrity is not strong enough to guarantee true human-in-the-loop behavior.

Observed issues:
- Decision payload `operator_user_id` can be supplied directly by API caller payload and is not bound to authenticated identity.
- Current human check blocks a small set of system IDs/prefixes, but allows arbitrary human-looking IDs.
- Reviewed run artifacts include explicit "Auto-selected" notes at angle and offer winner gates.
- Original runbook defines 6 mandatory human decision points; current workflow enforces 4 gates in runtime path.

This creates audit and trust risk for customer-facing outputs.

---

## 2) Original V2 HITL Contract (Source of Truth)

Reference:
- `V2 Fixes/Integration/RUNBOOK.md`
- `V2 Fixes/Integration/docs/plans/2026-02-21-pipeline-integration-design.md`
- `V2 Fixes/Integration/templates/angle_selection.yaml`
- `V2 Fixes/Integration/templates/angle_selection_guide.md`

Runbook-required human decisions:
1. H1: Proceed past foundational research quality gate.
2. H2: Confirm competitor asset collection before Stage 2A/2B analysis.
3. H3: Select angle.
4. H4: Select UMP/UMS pair.
5. H5: Select offer variant.
6. H6: Final copy approval.

Expected properties of each decision:
- Explicit operator identity.
- Explicit rationale.
- Evidence-aware selection from presented candidates.
- Immutable audit trail.

---

## 3) Current-State Deep Audit

### 3.1 Runtime enforcement that already exists

- Workflow pauses for signals at H3/H4/H5/H6 (`strategy_v2.py`).
- Activities validate decision payload schemas.
- `_require_human_operator_user_id` blocks obvious automation IDs and prefixes.

### 3.2 Integrity gaps

1. **Identity spoofability at API boundary**
   - Decision endpoints accept payload `operator_user_id` and pass it through.
   - No strict requirement that `operator_user_id == auth.user_id`.

2. **Auto-selection not policy-blocked**
   - Decision note text indicating auto-selection is not rejected.
   - No `decision_mode` or explicit manual attestation field.

3. **H1/H2 not explicit runtime gates**
   - Workflow currently enforces only four post-stage gates.
   - Research proceed and competitor asset confirmation gates are not modeled as explicit signals.

4. **Audit completeness gaps**
   - Decision artifacts include notes and user IDs, but not enough structured evidence that the decision was manual and informed.

### 3.3 Evidence from reviewed run

Artifacts:
- `artifact-downloads/strategy_v2_7153a278-2d82-42b7-aa4a-9a64c9bfa166/15_strategy_v2_step_payload__...__v2-07.json`
- `artifact-downloads/strategy_v2_7153a278-2d82-42b7-aa4a-9a64c9bfa166/18_strategy_v2_step_payload__...__v2-09.json`

Observed fields:
- `operator_user_id = human-qa-operator`
- `operator_note = Auto-selected top ranked angle during rerun validation`
- `operator_note = Auto-selected top ranked variant during rerun validation`

This is acceptable for internal rerun validation only if explicitly flagged as such. It should not pass as standard production HITL behavior.

---

## 4) Target Policy and Behavior

## 4.1 HITL decision policy levels

Define two explicit modes:
- `production_strict` (default): manual-only decisions, bound to authenticated user identity.
- `internal_validation` (explicitly opted-in): allows controlled automation for rerun QA with full labeling.

Default behavior in production_strict:
- Decision endpoints must ignore or reject body-provided `operator_user_id` and stamp authenticated `auth.user_id`.
- Decision payload must include `decision_mode = "manual"`.
- Decision payload must include non-trivial rationale and acknowledgement fields.
- Any auto-selection markers are rejected.

## 4.2 Required decision payload enrichments

For H3/H4/H5/H6 (and added H1/H2), extend contracts with:
- `decision_mode`: `manual | internal_automation`
- `reviewed_candidate_ids`: array (where applicable)
- `selected_candidate_id`: explicit selected id (already present for some gates)
- `operator_note`: min length requirement in strict mode
- `attestation` block:
  - `reviewed_evidence: true`
  - `understands_impact: true`

For H1/H2 add dedicated contracts:
- `ResearchProceedDecision`
- `CompetitorAssetConfirmationDecision`

---

## 5) Detailed Implementation Plan

## WP1 — Contract Hardening

Files:
- `mos/backend/app/strategy_v2/contracts.py`

Changes:
- Add `DecisionMode` literal type.
- Extend existing decision models with:
  - `decision_mode`
  - `reviewed_candidate_ids` (except final approval where optional)
  - stronger `operator_note` constraints (or conditional checks in activity layer).
- Add new models for H1/H2 decisions.

Acceptance:
- Invalid or incomplete decision payloads are rejected at validation time.

## WP2 — API Identity Binding and Input Sanitization

Files:
- `mos/backend/app/routers/workflows.py`

Changes:
- For strategy-v2 decision endpoints, do not trust request body `operator_user_id`.
- Stamp `operator_user_id = auth.user_id` server-side before signaling.
- Reject payloads attempting `decision_mode=internal_automation` unless internal-validation flag is enabled.

Acceptance:
- Caller cannot spoof operator identity in decision signals.

## WP3 — Activity-Level Manual Decision Enforcement

Files:
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`

Changes:
- Replace simple blocked-prefix check with policy validation function:
  - validate mode
  - validate attestation
  - validate rationale quality
  - reject auto-selection language in strict mode
- Add explicit rejection messages with remediation.

Acceptance:
- Any non-manual decision in strict mode raises `StrategyV2DecisionError`.

## WP4 — Add Missing H1/H2 Gates to Workflow

Files:
- `mos/backend/app/temporal/workflows/strategy_v2.py`
- `mos/backend/app/strategy_v2/step_keys.py`
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`
- `mos/backend/app/routers/workflows.py`

Changes:
- Introduce new workflow stages/signals:
  - `v2-02a` research proceed approval (H1)
  - `v2-02b` competitor asset confirmation (H2)
- Persist step payload artifacts for both decisions.
- Expose new signal endpoints for these gates.

Acceptance:
- Workflow cannot progress past foundational or competitor asset handoff without explicit decision artifacts.

## WP5 — Audit Trail and Decision Provenance

Files:
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`
- (Optional) analytics/audit consumer modules

Changes:
- Persist enriched decision metadata:
  - authenticated user id
  - decision mode
  - reviewed candidates
  - rationale
  - timestamp and stage context
- Add decision summary snapshots in workflow state query payloads.

Acceptance:
- Every gate decision is fully auditable from artifacts alone.

---

## 6) File-Level Edit Map

| File | Edit type | Why |
|---|---|---|
| `mos/backend/app/strategy_v2/contracts.py` | Extend | Add stricter HITL payload contracts |
| `mos/backend/app/routers/workflows.py` | Refactor | Bind decisions to authenticated user; prevent spoofing |
| `mos/backend/app/temporal/workflows/strategy_v2.py` | Extend | Add H1/H2 stages and signals |
| `mos/backend/app/strategy_v2/step_keys.py` | Extend | Add step keys for new decision stages |
| `mos/backend/app/temporal/activities/strategy_v2_activities.py` | Refactor | Decision policy validation + richer artifact persistence |
| `mos/backend/tests/test_strategy_v2_workflow_api.py` | Expand | Validate identity binding and decision rejection cases |
| `mos/backend/tests/test_strategy_v2_workflow_ordering.py` | Expand | Verify added gate order and blocking behavior |

---

## 7) Test Strategy

## 7.1 API tests

- Body-supplied `operator_user_id` different from auth user is ignored/rejected.
- Missing attestation fields rejected.
- `decision_mode=internal_automation` rejected in strict mode.

## 7.2 Activity tests

- Auto-selection note language rejected in strict mode.
- Service account style IDs rejected.
- Manual decision with complete attestation passes.

## 7.3 Workflow tests

- Workflow pauses at H1/H2/H3/H4/H5/H6 in order.
- Without each signal, workflow stays blocked.
- Artifacts for each gate are created with complete decision metadata.

---

## 8) Rollout Plan

1. Introduce `STRATEGY_V2_HITL_POLICY_MODE` with default `production_strict`.
2. Backfill tests for all decision endpoints before enabling new gates.
3. Roll out H1/H2 gates in staging first to verify operator UX compatibility.
4. Enable in production after UI updates for new signals are deployed.

No fallback policy:
- Do not silently auto-advance decisions when fields are missing.
- Fail fast with explicit remediation.

---

## 9) Acceptance Criteria (Definition of Done)

1. Decision identity is cryptographically bound to authenticated user context at API layer.
2. Strategy V2 enforces all 6 documented human decision points in runtime.
3. Production mode rejects automated decision signals and auto-selection notes.
4. Each decision artifact includes complete auditable context and rationale.
5. Workflow ordering and API tests cover all new rejection and gating cases.

---

## 10) Dependencies and Sequencing

- Can be implemented partially in parallel with Fix #1.
- Preferred sequence:
  1. API identity binding + decision contract hardening
  2. Add H1/H2 workflow gates
  3. Enable strict policy default
- Fix #3 depends on reliable H6 approval semantics but otherwise decoupled.

---

## 11) Non-Goals

- No changes to LLM model configuration.
- No UI redesign details in this document (API/workflow contract only).
- No support for hidden automation in production mode.
