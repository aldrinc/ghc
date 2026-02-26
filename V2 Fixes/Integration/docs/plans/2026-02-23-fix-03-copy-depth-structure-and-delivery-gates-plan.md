# Fix 03 Plan — Copy Depth, Structure, and Promise Delivery Gates

**Date:** 2026-02-23
**Status:** Draft for implementation
**Owner:** Strategy V2 copy stage
**Primary objective:** Raise Stage 4 output quality from minimal passable copy to documented V2 copywriting standards with strict depth, structure, and Promise Contract delivery enforcement.

---

## 1) Problem Statement

Current Stage 4 passes headline and congruency gates but still produces short, low-depth copy that does not match the Copywriting Agent's intended architecture.

Observed output profile in reviewed run:
- Presell markdown: ~393 words.
- Sales page markdown: ~554 words.
- Combined body markdown: ~948 words.

This is below documented Copywriting Agent expectations for advertorial + sales page in warm-traffic funnel execution and indicates missing structure/depth controls.

---

## 2) Original V2 Copywriting Contract (Source of Truth)

Primary references:
- `V2 Fixes/Copywriting Agent — Final/SYSTEM_README.md`
- `V2 Fixes/Copywriting Agent — Final/ARCHITECTURE_MAP.md`
- `V2 Fixes/Copywriting Agent — Final/04_prompt_templates/advertorial_writing.md`
- `V2 Fixes/Copywriting Agent — Final/04_prompt_templates/sales_page_writing.md`
- `V2 Fixes/Copywriting Agent — Final/04_prompt_templates/promise_contract_extraction.md`
- `V2 Fixes/Copywriting Agent — Final/01_governance/sections/Section 2 - Page-Type Templates.md`
- `V2 Fixes/Copywriting Agent — Final/01_governance/sections/Section 9 - Section-Level Job Definitions.md`
- `V2 Fixes/Copywriting Agent — Final/02_engines/page_templates/Presales and Sales Page General Constraints.md`

Core intended behavior:
1. Headline generation and deterministic scoring.
2. Promise Contract extraction (explicit 4-field contract) from the selected headline.
3. Presell advertorial writing with B1-B4 progression and section jobs.
4. Sales page writing with B5-B8 progression and section jobs.
5. Congruency scoring with PC2 hard gate.
6. Page structure and depth aligned to page templates and section-level constraints.

---

## 3) Current-State Deep Audit

Runtime file:
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`

Current behavior gaps:
- Copy body built by deterministic markdown assembly helpers:
  - `_build_presell_markdown`
  - `_build_sales_page_markdown`
- Promise contracts are static dictionaries, not extracted from winning headline contract.
- `_validate_markdown_integrity` only enforces coarse checks:
  - non-empty
  - >=600 chars
  - required headings
  - markdown link CTA
- No word-range gates by page type.
- No section word budgets.
- No CTA density/placement checks.
- No explicit section-level job compliance checks (S9).

Result: a short template can pass congruency and still underperform true sales intent.

---

## 4) Gap Matrix (Expected vs Actual)

| Area | Expected from V2 docs | Current flow | Gap type |
|---|---|---|---|
| Promise Contract origin | Extracted from winning headline | Static hardcoded contracts | Contract fidelity gap |
| Presell architecture | 6-section B1-B4 with section jobs and delivery timing | Minimal 5-ish section template, shallow copy | Structural gap |
| Sales architecture | 12-section B5-B8 (or documented production architecture) | 5-section summary-like template | Structural and conversion gap |
| Word-depth controls | Explicit page-type ranges and section budgets | No word-count gating | Depth gate gap |
| Section-level QA | S9 job checks and progression checks | Not implemented | Behavioral QA gap |
| CTA strategy | Placement and density constraints | Minimal CTA presence check only | Conversion mechanics gap |

---

## 5) Target Quality Standard for New Flow

## 5.1 Canonical profiles (for Strategy V2 default)

To resolve doc-range variability, define runtime profile defaults for presold traffic:

- `presell_advertorial`:
  - floor: 800 words
  - target: 1,000-1,400 words
  - hard ceiling: 1,800 words
  - required sections: 6

- `sales_page_warm`:
  - floor: 1,800 words
  - target: 2,200-3,000 words
  - hard ceiling: 3,500 words
  - required sections: 10-12 (depending chosen architecture mode)

These defaults are strict for Strategy V2 unless explicitly overridden by an approved profile.

## 5.2 Mandatory gate categories

1. **Depth gates**
   - word count floor/ceiling by page type
   - minimum words in core sections (mechanism/proof/offer/guarantee)
2. **Structure gates**
   - required section list by page type
   - belief progression ordering (B1→B4 for presell, B5→B8 for sales)
3. **Promise delivery gates**
   - Promise Contract delivery timing checks must align with `minimum_delivery`
   - PC2 remains hard gate
4. **Conversion mechanics gates**
   - CTA count and first CTA placement window
   - guarantee proximity to CTA
5. **Compliance/tone gates**
   - maintain existing congruency + compliance constraints

No fallback policy:
- If any gate fails, fail stage with explicit remediation.

---

## 6) Detailed Implementation Plan

## WP1 — Promise Contract Fidelity

Files:
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`

Changes:
- Replace static Promise Contract construction with extracted contract from winning headline (prompt-template-driven extraction in Fix #1 path).
- Persist extracted contract per page asset.

Acceptance:
- `copy_payload.promise_contracts.presell` and `.sales_page` are traceably derived from headline contract logic, not hardcoded defaults.

## WP2 — Copy Quality Gate Module

Files:
- `mos/backend/app/strategy_v2/copy_quality.py` (new)
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`

Changes:
- Add deterministic markdown analyzer:
  - section parser (`##` boundaries)
  - word counts total + per section
  - CTA extraction/counting
  - belief-marker progression checks
- Add page-type profiles and thresholds.
- Add explicit exceptions with remediation instructions.

Acceptance:
- Short templates below floor are blocked even if congruency passes.

## WP3 — Stage 4 Structural Rewrite (aligned with copy templates)

Files:
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`

Changes:
- Replace deterministic assembly helpers with template-driven generation path (Fix #1 dependency).
- Enforce required section naming and section jobs.
- Introduce architecture mode metadata (`section2_copy_first`, `merged`, etc.) for sales pages.

Acceptance:
- Generated outputs meet required section topology for selected architecture mode.

## WP4 — Runtime Gate Integration

Files:
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`

Changes:
- Apply gate sequence:
  1. headline scorer + QA
  2. Promise Contract extraction
  3. presell generation
  4. presell quality gates
  5. presell congruency gates
  6. sales generation
  7. sales quality gates
  8. sales congruency gates
- Fail immediately when a gate fails with machine-readable gate report.

Acceptance:
- `copy_payload` includes `quality_gate_report` for presell and sales.

## WP5 — Observability and Artifact Transparency

Files:
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`

Changes:
- Persist quality diagnostics in artifact payload:
  - total words
  - section words
  - CTA stats
  - gate pass/fail by rule
  - architecture mode
- Include reason codes for rejection to support UI remediation.

Acceptance:
- Operators can see exactly why copy failed and what must change.

---

## 7) File-Level Edit Map

| File | Edit type | Why |
|---|---|---|
| `mos/backend/app/strategy_v2/copy_quality.py` | New | Deterministic depth/structure/CTA analyzer |
| `mos/backend/app/temporal/activities/strategy_v2_activities.py` | Major refactor | Replace static builders, integrate quality gates |
| `mos/backend/app/strategy_v2/contracts.py` | Minor extension | Optional typing for `copy_quality_report` payloads |
| `mos/backend/tests/test_strategy_v2_translation_and_scorers.py` | Expand | Add copy quality analyzer tests |
| `mos/backend/tests/test_strategy_v2_workflow_api.py` | Expand | Verify stage fails for shallow outputs and reports actionable diagnostics |

---

## 8) Gate Specification (Draft)

## 8.1 Presell gates

- `PRESELL_WORD_FLOOR`: total words >= 800
- `PRESELL_WORD_CEILING`: total words <= 1800
- `PRESELL_SECTION_COUNT`: >= 6 required sections
- `PRESELL_MECHANISM_DEPTH`: mechanism section >= 150 words
- `PRESELL_PROMISE_TIMING`: Promise Contract minimum delivery by configured section boundary
- `PRESELL_CTA_COUNT`: 1-2 CTA placements (profile-driven)

## 8.2 Sales gates

- `SALES_WORD_FLOOR`: total words >= 1800
- `SALES_WORD_CEILING`: total words <= 3500
- `SALES_SECTION_COUNT`: >= 10 sections (or exact required set for chosen mode)
- `SALES_PROOF_DEPTH`: proof sections cumulative >= 300 words
- `SALES_GUARANTEE_DEPTH`: guarantee section >= 80 words
- `SALES_CTA_COUNT`: 3-4 primary CTA placements
- `SALES_FIRST_CTA_POSITION`: first CTA appears by <= 40% of document length
- `SALES_PROMISE_TIMING`: Promise Contract delivery requirements satisfied

## 8.3 Shared hard gates

- Congruency composite pass threshold remains >= 75%.
- PC2 hard gate must pass for both presell and sales page.

---

## 9) Test Strategy

## 9.1 Unit tests

- Section parser correctness on markdown variants.
- Word-count and per-section budget checks.
- CTA extraction and placement calculations.
- Promise timing checker against `minimum_delivery` patterns.

## 9.2 Integration tests

- Stage 4 rejects shallow outputs (< floor) with clear reason codes.
- Stage 4 accepts valid long-form outputs meeting all gates.
- Artifact payload includes gate report fields.

## 9.3 Regression tests

- Existing headline scorer and congruency scorer behavior remains unchanged.
- Existing final approval gate behavior remains intact.

---

## 10) Rollout Plan

1. Introduce feature flag: `STRATEGY_V2_COPY_DEPTH_GATES_ENABLED`.
2. Run in observe-only mode in staging for baseline fail-rate measurement.
3. Enable hard enforcement after thresholds are calibrated on real runs.
4. Keep strict no-fallback behavior when enforcement is enabled.

---

## 11) Acceptance Criteria (Definition of Done)

1. Stage 4 outputs satisfy documented long-form structural expectations for presell and sales pages.
2. Promise Contract is extracted from winning headline and enforced via timing-aware checks.
3. Short shallow copy cannot pass Stage 4 even if congruency alone passes.
4. Artifacts include machine-readable quality gate diagnostics for operator remediation.
5. Tests cover failure and success paths for all new depth and structure gates.

---

## 12) Dependencies and Sequencing

- This fix depends on Fix #1 prompt-chain parity for best results.
- Can partially ship with current generator path by adding depth gates first, but full quality parity requires template-driven generation.
- Compatible with Fix #2 and should be enforced before final approval gate in production.

---

## 13) Non-Goals

- No model-family changes.
- No frontend UX design in this plan.
- No relaxation of hard-gate policy to avoid failures.
