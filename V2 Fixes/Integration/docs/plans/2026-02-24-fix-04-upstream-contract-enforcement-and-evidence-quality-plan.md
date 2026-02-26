# Fix 04 Plan — Upstream Contract Enforcement and Evidence Quality Gates

## 1) Objective

Fix the upstream failure chain in Strategy V2 so we do not enter Offer/Copy with degraded evidence.

Primary goal:
- stop the workflow as soon as required upstream inputs are missing or blocked
- enforce structured output contracts for v2-03/v2-04/v2-05/v2-06
- prevent low-information artifacts from passing quality gates and poisoning downstream copy

## 2) Why this fix is needed

Recent failed run evidence shows the final copy error is downstream fallout, not root cause:

- `v2-03` Agent 0b returned `BLOCKED_MISSING_REQUIRED_INPUTS`, but pipeline continued.
- `v2-04` Agent 1 returned `MISSING_REQUIRED_INPUTS` + `CANNOT_PROCEED`, but pipeline continued.
- `v2-05` VOC items scored at `adjusted_score=0.0` with `zero_evidence_gate=true`.
- `v2-06` angle scores flattened (`final_score=20.0`, `demand_signal=0.0`, `pain_intensity=0.0`, `std_score=0`).
- Angle selection still passed because current gate checks count/depth only, not evidence quality.
- Copy then failed strict congruency/semantic gates.

## 3) Root-cause chain to address

1. Runtime input contract mismatch with original V2 prompt contracts.
2. Blocked upstream outputs are accepted as valid payloads.
3. Loose schemas permit structurally empty or placeholder objects.
4. Normalization defaults mask missing fields and convert missingness into pseudo-valid rows.
5. Stage transitions rely on count-based gates instead of evidence-quality gates.

## 4) Source-of-truth alignment

This fix aligns runtime behavior with original V2 intent:
- "Do not proceed until required inputs are present" (Agents 0b/1/2 contracts).
- Hard-gate behavior for insufficient evidence.
- Fail-fast with explicit remediation messages.

This fix explicitly does **not** introduce silent fallbacks.

## 5) Scope

In scope:
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`
- `mos/backend/app/strategy_v2/contracts.py`
- `mos/backend/app/strategy_v2/apify_ingestion.py`
- tests for stage-level gate behavior and schema enforcement

Out of scope:
- changing model/provider choices
- loosening copy-stage quality gates
- adding synthetic/fake data paths

## 6) Design principles for implementation

1. Fail fast at the first invalid upstream stage.
2. Prefer explicit, typed contracts over permissive dicts.
3. No implicit defaults for required scoring fields.
4. No "continue with reduced confidence" behavior in production path.
5. Every gate failure returns explicit remediation guidance.

## 7) Work packages

## WP1 — Runtime input parity for Agents 0b/1/2

Problem:
- Agent prompts require inputs not passed by runtime (`PRODUCT_CATEGORY_KEYWORDS`, structured `AVATAR_BRIEF`, `SCRAPED_DATA_FILES` equivalent context contract).

Plan:
- Introduce explicit runtime input builders for Agent 0b/1/2 with strict required fields.
- Require structured avatar payload in runtime block, not summary-only string.
- Require category keyword list in runtime block.
- For Agent 1, pass explicit scraped-data contract payload (dataset/run references + counts + source manifests) used in place of filesystem-path semantics.

Gate:
- If any required runtime input field is missing, raise `StrategyV2MissingContextError` before prompt call.

Deliverables:
- typed input builders + unit tests for required-field enforcement.

## WP2 — Blocked-output detection and immediate stop

Problem:
- Upstream blocked outputs are persisted and scored.

Plan:
- Add stage-local detectors for known blocked states:
  - `BLOCKED_MISSING_REQUIRED_INPUTS`
  - `MISSING_REQUIRED_INPUTS`
  - `CANNOT_PROCEED`
  - placeholder sentinel habitat names
- Evaluate both structured fields and `handoff_block`/raw output text.
- If detected, stop stage and raise deterministic remediation error.

Gate:
- `v2-03` cannot proceed when Agent 0b indicates blocked status.
- `v2-04` cannot proceed when Agent 1 indicates cannot proceed.
- `v2-05` cannot proceed when Agent 2 signals blocked mode due missing handoff/mining context.

Deliverables:
- helper validators + tests per stage.

## WP3 — Tighten upstream schemas (reject empty structure)

Problem:
- Current schemas allow empty objects (for example `strategy_habitats: [{}]`).

Plan:
- Replace permissive inline JSON schemas with stricter object contracts.
- Require non-empty required keys for:
  - Agent 0 `strategy_habitats` items
  - Agent 0b `configurations` items
  - Agent 1 habitat observation rows
  - Agent 2 observation rows used by scorer
- Enforce `extra=forbid` semantics for stage payload contracts where feasible.

Gate:
- Empty/placeholder rows fail validation before persistence/scoring.

Deliverables:
- contract updates + migration notes + tests.

## WP4 — Remove missingness-masking defaults in VOC/Angle normalization

Problem:
- Defaults (`NONE`, `UNKNOWN`, many `N`/`Y`) hide missing required observables.

Plan:
- Split normalization into:
  - required scoring fields
  - optional metadata fields
- For required scoring fields:
  - require explicit field presence from Agent outputs
  - reject rows missing required observables
- Keep defaults only for truly optional fields that do not affect hard gates.
- Ensure normalization errors include field-level diagnostics.

Gate:
- Reject VOC rows that cannot be scored faithfully.
- Reject angle observation rows missing required evidence/quality inputs.

Deliverables:
- normalization refactor + row-level validation tests.

## WP5 — Add evidence-quality transition gates (v2-05 and v2-06)

Problem:
- Count-only gates let low-signal outputs pass.

Plan:
- Add deterministic transition gates:

`v2-05` VOC extraction gate:
- minimum observation count threshold
- non-zero evidence ratio threshold
- minimum unique source bucket threshold
- reject if excessive `zero_evidence_gate` incidence

`v2-06` angle synthesis gate:
- require non-zero score variance
- require at least N candidates above evidence floor
- require non-zero demand signal for top candidates

Gate:
- fail before `v2-07` angle selection if quality thresholds are not met.

Deliverables:
- gating functions + configurable thresholds + tests.

## WP6 — Competitor/source URL hygiene for upstream ingestion

Problem:
- Stage1 `competitor_urls` is polluted with non-actionable discovery links; ingestion gets noisy context.

Plan:
- Build deterministic URL classifier:
  - scrapeable competitor/source refs
  - non-scrapeable research/discovery refs
- Feed only scrapeable refs into Apify ingestion.
- Preserve full raw list in artifacts, but separate operational ingestion set.

Gate:
- if scrapeable source set is empty, fail with remediation.

Deliverables:
- source-ref filter utility + test fixtures for known noisy URLs.

## WP7 — Angle selection quality gate hardening

Problem:
- selection gate currently checks support-count/top-quote-count but not score quality.

Plan:
- extend selected-angle gate to require:
  - minimum scored evidence quality
  - minimum demand signal
  - no `evidence_floor_gate=true` for selected candidate
- reject angle selections that pass format but fail evidence quality.

Gate:
- `apply_strategy_v2_angle_selection_activity` fails if selected angle quality is below threshold.

Deliverables:
- extended gate checks + tests.

## WP8 — Observability and audit diagnostics

Problem:
- stage failures are visible but root-cause diagnosis is slower than needed.

Plan:
- standardize structured diagnostics payload on failures:
  - `stage`
  - `gate_name`
  - `failed_checks`
  - `required_inputs_missing`
  - `artifact_id`/`agent_run_id`
  - remediation block
- include blocked-status snapshot in persisted step payloads when failing.

Deliverables:
- consistent failure payload contract + tests.

## 8) Implementation sequencing

1. WP2 (blocked-output stop) and WP3 (schema hardening) first.
2. WP1 (runtime input parity) next.
3. WP4 (normalization strictness) then WP5 (quality transition gates).
4. WP6 (URL hygiene), WP7 (selection hardening), WP8 (observability) last.

Reason:
- stops bad data earliest, then fixes contracts that produce good data, then tightens downstream gates.

## 9) Test plan

## Unit tests

- Agent 0b blocked output triggers fail-fast in `v2-03`.
- Agent 1 cannot-proceed output triggers fail-fast in `v2-04`.
- Empty `strategy_habitats` object fails schema validation.
- VOC row missing required scoring fields fails normalization.
- `v2-05` gate fails when zero-evidence ratio exceeds threshold.
- `v2-06` gate fails on flat score distribution.
- Selected angle fails if `evidence_floor_gate=true`.
- URL hygiene excludes non-scrapeable discovery links.

## Integration tests

- end-to-end upstream path (`v2-02` to `v2-07`) with valid fixtures should pass.
- same path with blocked Agent 0b fixture should fail at `v2-03`.
- same path with cannot-proceed Agent 1 fixture should fail at `v2-04`.
- same path with collapsed VOC fixture should fail at `v2-05`.

## Replay validation on historical artifacts

- replay latest failed artifact chain and verify workflow now fails at first upstream invalid stage.
- confirm no run reaches copy when upstream gates fail.

## 10) Rollout strategy

Phase 1:
- ship behind a dedicated runtime gate flag.
- run replay suite + targeted integration tests in dev.

Phase 2:
- enable for internal manual runs.
- validate failure messages and operator remediation flow.

Phase 3:
- enable by default in production strategy_v2 path.

Rollback:
- disable fix flag only if emergency, preserving strict error transparency (no silent fallback behavior).

## 11) Acceptance criteria

1. Upstream blocked outputs never pass beyond originating stage.
2. `v2-03`/`v2-04`/`v2-05` required-input mismatches fail with explicit remediation.
3. `v2-05` cannot produce all-zero effective corpus without failing gate.
4. `v2-06` cannot yield flat no-signal candidates without failing gate.
5. Angle selection rejects low-evidence candidates even if quote counts pass.
6. Copy pipeline is only reached when upstream evidence quality gates pass.

## 12) Risks and mitigations

Risk:
- stricter gates increase early run failures during transition.

Mitigation:
- clear remediation messages
- staged rollout with replay validation
- explicit threshold tuning via config with documented defaults

Risk:
- schema tightening may break existing test fixtures.

Mitigation:
- migrate fixtures in same PR and add contract changelog notes.

## 13) PR breakdown recommendation

PR1:
- WP2 + WP3 (fail-fast + schema hardening)

PR2:
- WP1 + WP4 (input parity + normalization strictness)

PR3:
- WP5 + WP7 (quality gates + selection hardening)

PR4:
- WP6 + WP8 (URL hygiene + diagnostics)

