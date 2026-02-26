# Fix 01 Plan — Runtime Prompt-Chain Parity with Original V2 Systems

**Date:** 2026-02-23
**Status:** Draft for implementation
**Owner:** Strategy V2 backend integration
**Primary objective:** Replace scaffolded/heuristic runtime behavior with execution of the original V2 prompt systems (VOC+Angle, Offer Agent, Copywriting Agent) while preserving deterministic scoring and strict contract validation.

---

## 1) Problem Statement

The current `strategy_v2` runtime executes successfully, but major stage behavior is not full-parity with the original V2 fix assets.

What is working:
- Foundational prompt loading is wired to `V2 Fixes/Foundational Docs/clean_prompts/`.
- Deterministic scorers are dynamically loaded from V2 assets (`VOC + Angle Engine`, `Offer Agent`, `Copywriting Agent`).
- Temporal workflow sequencing and artifact persistence are in place.

What is missing:
- Stage 2B (Agent 0/0b/1/2/3) is mostly synthesized via deterministic helpers instead of the canonical prompt chain.
- Stage 3 runs custom JSON-generation logic, not the Offer Agent 5-step orchestrator prompt chain.
- Stage 4 body generation is deterministic template assembly, not prompt-template-driven advertorial/sales workflows.

This creates behavior drift from the documented V2 systems and reduces output fidelity.

---

## 2) Original V2 Contract (Source of Truth)

### 2.1 Stage-level expectations from original docs

Reference documents:
- `V2 Fixes/Integration/RUNBOOK.md`
- `V2 Fixes/Integration/docs/plans/2026-02-21-pipeline-integration-design.md`
- `V2 Fixes/Integration/specs/translation-layer.md`
- `V2 Fixes/Integration/specs/offer-agent-input-mapping.md`
- `V2 Fixes/Integration/specs/offer-to-copy-bridge.md`
- `V2 Fixes/VOC + Angle Engine (2-21-26)/docs/plans/2026-02-20-pipeline-v2-design.md`
- `V2 Fixes/Offer Agent — Final/prompts/pipeline-orchestrator.md`
- `V2 Fixes/Copywriting Agent — Final/ARCHITECTURE_MAP.md`
- `V2 Fixes/Copywriting Agent — Final/04_prompt_templates/*.md`

Expected runtime behavior:
1. Stage 2B executes the VOC+Angle agent chain with explicit handoffs:
   - `agent-00-habitat-strategist.md`
   - `agent-00b-social-video-strategist.md`
   - `agent-01-habitat-qualifier.md`
   - `agent-02-voc-extractor.md` (DUAL MODE when Step 4 corpus exists)
   - `agent-03-shadow-angle-clusterer.md`
   - scorer scripts applied after each observation stage.
2. Stage 3 executes Offer Agent through `pipeline-orchestrator.md` + step prompts 01..05.
3. Stage 4 executes Copywriting workflows as documented:
   - headline generation workflow
   - Promise Contract extraction (Step 4.5)
   - advertorial writing template
   - sales page writing template
   - congruency hard gates.

### 2.2 Non-negotiables from AGENTS.md constraints

- No hidden fallback logic: if required context or prompt output is missing, fail with explicit remediation.
- No model swapping: keep configured models; do not change model families as part of this fix.
- No fabricated data.

---

## 3) Current-State Deep Audit (New Flow)

### 3.1 Code paths showing scaffold behavior

Key files:
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`
- `mos/backend/app/strategy_v2/translation.py`
- `mos/backend/app/temporal/workflows/strategy_v2.py`

Observed scaffolded logic:
- Stage 2B helper synthesis functions:
  - `_build_habitat_observations`
  - `_build_voc_observations`
  - `_build_angle_candidates`
- Offer synthesis shortcuts:
  - `_create_awareness_matrix`
  - `_generate_ump_ums_pairs` (custom LLM JSON schema generation)
  - `_generate_offer_variants` (custom LLM JSON schema generation)
- Copy synthesis shortcuts:
  - `_build_presell_markdown`
  - `_build_sales_page_markdown`

### 3.2 What is already parity-aligned

- Foundational prompt loading from V2 assets is implemented.
- Scorer execution imports real scripts from V2 folders.
- Stage contracts and workflow gate orchestration are strict enough to block malformed payloads.

### 3.3 Runtime evidence from reviewed run

Reference run artifacts:
- `artifact-downloads/strategy_v2_7153a278-2d82-42b7-aa4a-9a64c9bfa166/`

Key signals supporting this fix:
- Stage 2B produced only one ranked angle candidate in v2-06.
- VOC corpus volume is below target and flagged low-volume warning.
- Copy body is structurally minimal compared to canonical prompt-template expectations.

---

## 4) Gap Matrix (Expected vs Actual)

| Area | Expected from original V2 | Current new flow | Gap type |
|---|---|---|---|
| Stage 2B execution | Agent 0/0b/1/2/3 prompt chain | Deterministic helper synthesis + scorer pass | Functional parity gap |
| Agent 2 mode | DUAL MODE with transformed STEP4 corpus | Simplified extraction from parsed entries | Behavioral fidelity gap |
| Agent 3 output depth | 5+ candidates, richer observation/evidence assembly | Often sparse clusters/candidate count | Output quality gap |
| Offer pipeline | 5-step orchestrator prompt chain | Two custom JSON generators + scoring | Orchestration gap |
| Awareness-angle matrix | Step 2 Phase 7 output from Offer prompt system | Locally synthesized static structure | Provenance gap |
| Copy pipeline | Prompt-template-driven long-form workflow | Deterministic short markdown assembly | Content-depth and process gap |
| Promise contract flow | Explicit extraction from winning headline | Static promise blocks in copy stage | Semantic contract gap |

---

## 5) Target Architecture

## 5.1 Core design

Introduce a strict prompt execution substrate used by stages 2-4:
- Prompt asset resolver (exact file path resolution in `V2 Fixes`).
- Variable renderer (no silent missing placeholders).
- LLM executor with deterministic tagged output requirements.
- Structured extractor (JSON blocks and named sections).
- Contract validators for each step handoff.

No fallback path:
- Any missing required block must raise `StrategyV2MissingContextError` or `StrategyV2SchemaValidationError`.

## 5.2 Stage 2B target flow

1. Build translated inputs via `translation-layer.md` mapping.
2. Execute Agent 0 and 0b prompts.
3. Execute scrape layer (current infra abstraction can remain, but input contract must mirror Agent 0/0b outputs).
4. Execute Agent 1 prompt against scraped payload + context.
5. Execute Agent 2 prompt in DUAL MODE with transformed STEP4 corpus.
6. Execute Agent 3 prompt with competitor angle map + saturated angles.
7. Run scorers on resulting observation outputs.
8. Persist each step raw output and parsed handoff artifact.

## 5.3 Stage 3 target flow

Use `Offer Agent — Final/prompts/pipeline-orchestrator.md` as control template:
- Step 1: avatar synthesis prompt
- Step 2: market calibration prompt (awareness-angle-matrix from this output)
- Step 3: UMP/UMS generation prompt + deterministic `ump_ums_scorer`
- Step 4: offer construction prompt (base + variants)
- Step 5: self-evaluation prompt + `composite_scorer`

Keep human gate semantics unchanged for pair and variant selection (fix #2 strengthens those gates).

## 5.4 Stage 4 target flow

Execute copy pipeline aligned to `Copywriting Agent` templates:
- Headline generation prompt template (plus deterministic scorer and QA loop).
- Promise Contract extraction prompt for winning headline.
- Advertorial writing prompt template.
- Sales page writing prompt template.
- Congruency scoring with Promise Contract per page.

---

## 6) Detailed Implementation Work Packages

## WP1 — Prompt Runtime Foundation

**Goal:** Add reusable strict prompt runtime primitives.

Planned changes:
- Add new module: `mos/backend/app/strategy_v2/prompt_runtime.py`
- Add capabilities:
  - `resolve_prompt(pattern: str) -> Path`
  - `render_prompt(template: str, vars: dict[str, str]) -> str` with hard fail on missing placeholders
  - `run_prompt(...) -> str` using existing LLM client wrapper
  - `extract_required_json_block(...)`
  - `extract_required_section(...)`
- Add prompt hash/version capture for artifact provenance.

Acceptance criteria:
- Missing placeholder triggers explicit error.
- Ambiguous prompt path triggers explicit error.
- All executed prompts emit trace metadata (path + SHA256 + model).

## WP2 — Stage 2B Parity Rewrite

**Goal:** Replace helper-synthesis logic with prompt-chain execution.

Files to modify:
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`
- `mos/backend/app/strategy_v2/translation.py`

Edits:
- Add explicit stage-2 prompt constants for Agent 0/0b/1/2/3 prompt files.
- Add translation functions for:
  - STEP4 corpus transformation to Agent 2 format (DUAL MODE input).
  - competitor angle map and saturated angle extraction.
- Replace direct usage of `_build_habitat_observations`, `_build_voc_observations`, `_build_angle_candidates` in main activity path with prompt outputs.
- Keep scorer calls but run them on parsed observation payloads from agent outputs.
- Persist per-agent raw + parsed artifacts (`v2-02`..`v2-06`).

Acceptance criteria:
- Each agent prompt executes exactly once per run (except retried failures).
- Agent 2 receives explicit DUAL MODE corpus when STEP4 content exists.
- v2-06 payload stores Agent 3-derived candidates and scorer overlays.

## WP3 — Offer Agent Orchestrator Integration

**Goal:** Align stage 3 runtime with Offer Agent prompt chain.

Files to modify:
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`
- `mos/backend/app/strategy_v2/translation.py`

Edits:
- Replace `_create_awareness_matrix` as primary source with Step 2 phase output from Offer prompt chain.
- Replace custom `_generate_ump_ums_pairs` and `_generate_offer_variants` prompt text with Offer step prompt execution.
- Normalize extracted Offer step JSON outputs into existing contracts.
- Preserve deterministic score tool calls (calibration, ump_ums, hormozi, objection, novelty, composite).

Acceptance criteria:
- Stage 3 payload includes Step 1..5 outputs with traceable provenance.
- UMP/UMS candidates and offer variants originate from Offer prompts, not local synthesized instructions.

## WP4 — Copywriting Prompt-Template Integration

**Goal:** Replace deterministic markdown assembly with copywriting templates.

Files to modify:
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`

Edits:
- Add prompt execution for:
  - `headline_generation.md`
  - `promise_contract_extraction.md`
  - `advertorial_writing.md`
  - `sales_page_writing.md`
- Keep deterministic scorer gates:
  - headline scorer
  - congruency scorer (PC2 hard gate)
- Remove static promise-contract dictionaries and derive from extracted Promise Contract artifact.

Acceptance criteria:
- Promise contract in artifact is generated from winning headline.
- Presell and sales markdown are generated via prompt templates and pass congruency hard gates.

## WP5 — Artifacts, Provenance, and Observability

**Goal:** Make prompt-chain execution auditable and diffable.

Files to modify:
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`
- `mos/backend/app/strategy_v2/step_keys.py` (if additional sub-steps needed)

Edits:
- Add per-step metadata fields:
  - `prompt_path`
  - `prompt_sha256`
  - `model_name`
  - `input_contract_version`
  - `output_contract_version`
- Persist raw agent outputs as step payload attachments.

Acceptance criteria:
- Every stage 2-4 step payload can be traced back to exact prompt file and model.

---

## 7) File-Level Edit Map

| File | Edit type | Why |
|---|---|---|
| `mos/backend/app/strategy_v2/prompt_runtime.py` | New | Shared strict prompt execution primitives |
| `mos/backend/app/temporal/activities/strategy_v2_activities.py` | Major refactor | Replace synthesized stage behavior with prompt-chain execution |
| `mos/backend/app/strategy_v2/translation.py` | Extend | Add explicit translation-layer transformations for Agent 2/3 and Offer inputs |
| `mos/backend/app/strategy_v2/contracts.py` | Minor extensions | Optional typed wrappers for parsed agent outputs |
| `mos/backend/app/strategy_v2/step_keys.py` | Optional | Add finer-grain step keys if we persist sub-step artifacts |
| `mos/backend/tests/test_strategy_v2_translation_and_scorers.py` | Expand | Validate transformation and strict parse behavior |
| `mos/backend/tests/test_strategy_v2_workflow_ordering.py` | Expand | Ensure stage order and required prompt steps remain enforced |
| `mos/backend/tests/test_strategy_v2_workflow_api.py` | Expand | Verify payloads include prompt provenance |

---

## 8) Test Strategy

## 8.1 Unit tests

- Prompt resolver fails on 0 or >1 path matches.
- Missing template placeholders cause hard error.
- JSON extractor fails when required output blocks are absent.
- STEP4-to-Agent2 transformation retains required fields and IDs.

## 8.2 Integration tests

- Stage 2B executes all 5 agent prompts and persists artifacts.
- Stage 3 executes Offer step prompts and exposes expected structured outputs.
- Stage 4 executes copy prompts and returns Promise Contract-derived congruency checks.

## 8.3 Regression tests

- Existing deterministic scorer compatibility unchanged.
- Existing workflow signal order unchanged.

---

## 9) Rollout Plan

1. Implement behind a feature flag (example: `STRATEGY_V2_PROMPT_PARITY_V2=true`).
2. Run shadow comparisons on internal validation workflows.
3. Promote to default once acceptance criteria and output-quality gates are stable.

No hidden fallback policy:
- When flag is enabled, prompt-chain path is strict; failures should error explicitly with remediation.

---

## 10) Acceptance Criteria (Definition of Done)

1. Stage 2B uses the original VOC+Angle prompts for Agent 0/0b/1/2/3, with DUAL MODE when applicable.
2. Stage 3 uses Offer Agent orchestrator step prompts 01..05.
3. Stage 4 uses Copywriting prompt templates for headline/promises/advertorial/sales flows.
4. Deterministic scorers remain active and gating logic unchanged or stricter.
5. All stage payloads contain prompt provenance metadata.
6. No fallback path silently substitutes synthetic generation when required prompt outputs are missing.

---

## 11) Dependencies and Sequencing

- **Fix #1 should land before Fix #3** (copy-depth enforcement) because copy-depth checks are meaningful only once canonical copy generation path is restored.
- **Fix #2 (HITL hardening)** can proceed in parallel, but is safer after stage payload schemas stabilize under this rewrite.

---

## 12) Non-Goals

- No change to configured model families in `app/config.py` as part of this fix.
- No UI redesign work in this plan.
- No synthetic data generation for missing upstream assets.
