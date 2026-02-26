# Strategy V2 Artifact Review Outline

Workflow run: `3a60b036-c9fc-4262-ae56-6903a0a112bf`

This outline maps exported artifacts to the original V2 architecture so review can follow the pre-build plan sequence.

## Source Plan Anchors

- Master pipeline stages: `V2 Fixes/Integration/docs/plans/2026-02-21-pipeline-integration-design.md:25`
- Stage 0 seed input contract: `V2 Fixes/Integration/docs/plans/2026-02-21-pipeline-integration-design.md:74`
- Stage 1 foundational research flow: `V2 Fixes/Integration/docs/plans/2026-02-21-pipeline-integration-design.md:96`
- Stage 2B VOC + angle discovery: `V2 Fixes/Integration/docs/plans/2026-02-21-pipeline-integration-design.md:147`
- Human angle selection gate: `V2 Fixes/Integration/docs/plans/2026-02-21-pipeline-integration-design.md:197`
- Stage 3 offer architecture: `V2 Fixes/Integration/docs/plans/2026-02-21-pipeline-integration-design.md:223`
- Offer-to-copy bridge: `V2 Fixes/Integration/docs/plans/2026-02-21-pipeline-integration-design.md:264`
- Stage 4 copy execution: `V2 Fixes/Integration/docs/plans/2026-02-21-pipeline-integration-design.md:297`
- Product brief evolution schema (Stage 0→4): `V2 Fixes/Integration/docs/plans/2026-02-21-pipeline-integration-design.md:467`
- Foundational pipeline reference (01/03/04/06): `V2 Fixes/Foundational Docs/pipeline/00_pipeline_overview.md:7`
- Offer downstream outputs + awareness matrix contract: `V2 Fixes/Offer Agent — Final/downstream-integration/INTEGRATION-GUIDE.md:7`

## Review Order (Plan-Aligned)

### 1) Stage 0 — Seed Input Contract

Plan context:
- Stage 0 seed schema and derived variables (Integration design Stage 0)

Primary artifact:
- `01_strategy_v2_stage0__3e06e6cd-eda0-4ade-a20b-560e25d276a7.json`

What to validate:
- Product seed fields are complete and accurate for this workspace.
- `product_customizable` reflects intended constraints.

### 2) Stage 1 — Foundational Research Translation

Plan context:
- Foundational docs chain is 01 -> 03 -> 04 -> 06.
- In integrated pipeline, this is translated into the Stage 1 brief + downstream step payloads.

Primary artifact:
- `02_strategy_v2_stage1__7400b326-2cee-410a-966b-1aa5db588001.json`

Supporting step payloads (research-to-angle path):
- `v2-02` habitat strategy
- `v2-03` scrape/virality
- `v2-04` habitat scoring
- `v2-05` VOC extraction
- `v2-06` angle synthesis

What to validate:
- `category_niche`, market maturity, primary segment, and bottleneck align with foundational research intent.
- Angle candidates emerged from evidence (not generic copy).

### 3) Stage 2 — Human Angle Selection (HITL)

Plan context:
- Explicit human decision point selects one angle before offer construction.

Primary artifact:
- `03_strategy_v2_stage2__bfacfe31-eb19-4c31-a240-db07b46f51bc.json`

Supporting step payload:
- `v2-07` angle selection HITL

What to validate:
- Selected angle is coherent (`who`, `pain_desire`, `mechanism_why`, `belief_shift`, `trigger`).
- Compliance constraints are present and sensible.

### 4) Stage 3 — Offer Architecture

Plan context:
- Offer pipeline, UMP/UMS selection, variant scoring, winner selection.
- Awareness-angle matrix is a required downstream deliverable.

Primary artifacts:
- `04_strategy_v2_awareness_angle_matrix__70ee040b-6edc-4c73-a33f-b2e48df520ec.json`
- `05_strategy_v2_stage3__721869e6-8f67-418f-8af5-5a62588198f9.json`

Supporting step payloads:
- `v2-08` offer pipeline (ranked UMP/UMS)
- `v2-08b` offer variant scoring
- `v2-09` offer winner HITL

What to validate:
- UMP/UMS and core promise are differentiated and evidence-backed.
- Selected variant rationale tracks with scoring.
- Awareness matrix framing is usable across awareness levels.

### 5) Stage 3 -> 4 Bridge — Copy Shared Context Population

Plan context:
- Offer-to-copy bridge populates audience/product, awareness matrix, and compliance/voice context.

Primary artifacts:
- `06_strategy_v2_copy_context__2e4caa9a-b6b9-4b07-adcc-6325a4734f9c.json`
- Extracted markdown files in same folder:
  - `...__audience_product_markdown.md`
  - `...__awareness_angle_matrix_markdown.md`
  - `...__brand_voice_markdown.md`
  - `...__compliance_markdown.md`
  - `...__mental_models_markdown.md`

What to validate:
- Context files are complete and internally consistent with Stage 3 decisions.
- No contradiction between compliance notes and copy direction.

### 6) Stage 4 — Copy Execution + Final Approval

Plan context:
- Copy generation/scoring, then final human approval gate.

Primary artifacts:
- Generated copy:
  - `07_strategy_v2_copy__7d85cb3f-1f11-4225-8b00-983a64c56cef.json`
  - `07_strategy_v2_copy__7d85cb3f-1f11-4225-8b00-983a64c56cef__body_markdown.md`
- Final approved copy:
  - `08_strategy_v2_copy__bd88b8c2-b091-4efc-9f01-5042de36d6a0.json`
  - `08_strategy_v2_copy__bd88b8c2-b091-4efc-9f01-5042de36d6a0__approved_body_markdown.md`
  - `08_strategy_v2_copy__bd88b8c2-b091-4efc-9f01-5042de36d6a0__approved_headline.txt`

Supporting step payloads:
- `v2-10` copy pipeline
- `v2-11` final approval HITL

What to validate:
- Approved copy preserves selected angle + offer promise.
- Headline/body congruency and compliance are acceptable.

## Quick Read Path (If Time-Constrained)

1. Stage 2 (`stage2` artifact) — confirm strategic direction.
2. Stage 3 (`stage3` + awareness matrix) — confirm offer architecture quality.
3. Approved copy artifact — confirm final output quality.
4. Copy context markdowns — verify bridge fidelity.

## Full Step-Payload Chain (for deep audit)

The following step payload artifacts exist for this run and can be queried by step key:
- `v2-01` Stage 0 Build
- `v2-02` Habitat Strategy
- `v2-03` Scrape + Virality
- `v2-04` Habitat Scoring
- `v2-05` VOC Extraction
- `v2-06` Angle Synthesis
- `v2-07` Angle Selection HITL
- `v2-08` Offer Pipeline
- `v2-08b` Offer Variant Scoring
- `v2-09` Offer Winner HITL
- `v2-10` Copy Pipeline
- `v2-11` Final Approval HITL

