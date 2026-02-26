# Strategy V2 Downstream Plan (Simplified Angle-Selection + Detailed Template Bridge)

## 1) Simplified processing rule

We will follow one rule:
- If a marketer selects one angle, run one pipeline for that angle.
- If a marketer selects multiple angles, run one pipeline per selected angle.

Each angle pipeline stays in source-of-truth order:
1. Angle selected
2. Offer determined for that angle (including UMP/UMS and variant decisions)
3. Copy generated for that angle+offer
4. Funnel/page assets generated from that copy

No cross-angle reuse of offer or copy.

## 2) Angle-run model

## Input
- `selected_angle_ids: string[]`
- `template_ids: string[]` (or default template set)
- `decision_policy: strict_hitl | assisted_batch`
- `max_parallelism: int`

## Runtime behavior
For each `angle_id` in `selected_angle_ids`:
1. Create `angle_run_id`.
2. Run Stage 3 offer flow scoped to that `angle_run_id` and `angle_id`.
3. Run Stage 4 copy flow scoped to that angle-run offer output.
4. Build and validate template bridge payload.
5. Generate funnel assets from the validated bridge.
6. Persist angle-run bundle with full provenance.

## Output
One angle-run bundle per selected angle:
- `angle_id`
- `offer_decision_payload`
- `copy_payload`
- `template_bridge_payload`
- `funnel_result`
- `provenance`

## 3) Bridge objective

The bridge is the contract between Strategy V2 copy outputs and funnel templating.

Bridge requirements:
1. Convert approved copy into template-compatible structured data.
2. Preserve template component shape and required keys.
3. Fail fast when required mapping cannot be completed.
4. Carry explicit provenance and validation report.

V1 scope:
- Deterministic bridge for `sales-pdp` template.
- Unsupported template IDs fail with explicit error until a mapper is implemented.

## 3.1) Source-stack validation and reconciliation (required before rollout)

Problem:
- The design/source stack and the runtime stack may drift (schema docs, backend template JSON, validator behavior, and component expectations).

Validation workstream:
1. Build a runtime template capability inventory from:
- `mos/backend/app/templates/funnels/sales_pdp.json`
- Sales PDP validators in `mos/backend/app/services/funnel_ai.py` and `mos/backend/app/agent/funnel_tools.py`

2. Build a source-of-truth inventory from:
- `V2 Fixes/Copywriting Agent — Final/05_schemas/sales_pdp.schema.json`
- Relevant V2 copywriting architecture docs used for mapping intent

3. Compare inventories and classify mismatches:
- `P0`: runtime path/field missing for required bridge mapping
- `P1`: field exists but semantics/type differ
- `P2`: optional drift (non-blocking for V1)

4. Produce artifacts:
- `template_capability_inventory.runtime.json`
- `template_capability_inventory.source.json`
- `template_bridge_mismatch_report.md` (with P0/P1/P2 and remediation)

5. Gate:
- Bridge V1 rollout blocked until all P0 mismatches are resolved or explicitly removed from V1 mapping scope.

## 4) Bridge contract (V1)

`StrategyV2TemplateBridgeV1` fields:
- `bridge_version`
- `angle_run_id`
- `template_id`
- `source`
- `source.headline`
- `source.promise_contract`
- `source.sales_page_markdown`
- `source.presell_markdown`
- `normalized_sections`
- `template_patch`
- `copy_pack`
- `residual_copy`
- `validation_report`
- `provenance`

Notes:
- `template_patch` is deterministic component-path updates for template `puckData`.
- `copy_pack` is compact, structured copy guidance passed into Funnel AI generation.
- `residual_copy` captures valid copy that has no direct deterministic slot in template patch paths and must be consumed in generation guidance.

## 4.1) Copywriting output contract for template fit

Requirement:
- The copy stage must emit data that is directly consumable by the template bridge, not just freeform markdown.

V1 approach:
1. Keep markdown generation for existing quality/semantic/congruency gates.
2. Add a second structured output step (same angle-run context) that emits `template_fit_pack`.

`template_fit_pack` minimum fields:
- `hero`: `purchase_title`, `primary_cta_label`, `primary_cta_subbullets[]`
- `problem`: `title`, `paragraphs[]`, `emphasis_line`
- `mechanism`: `title`, `paragraphs[]`, `bullets[]`, `comparison_rows[]`
- `social_proof`: `badge`, `title`, `rating_label`, `summary`
- `whats_inside`: `benefits[]`, `offer_helper_text`
- `bonus`: `free_gifts_title`, `free_gifts_body`
- `guarantee`: `title`, `paragraphs[]`, `why_title`, `why_body`, `closing_line`
- `faq`: `title`, `items[]`
- `cta_close`: `text`

Validation of `template_fit_pack`:
- strict schema validation
- non-empty required fields
- coverage validation against required mapped sections
- compliance validation (no disallowed claims)

Failure behavior:
- If `template_fit_pack` fails validation, send validator errors back to copy step for repair.
- If still invalid after bounded attempts, fail angle-run with explicit bridge-fit error.

## 5) Sales-PDP mapping spec (V1)

Source sections are canonical Stage 4 sales sections:
- `hero_stack`
- `problem_recap`
- `mechanism_comparison`
- `identity_bridge`
- `social_proof`
- `cta_1`
- `whats_inside`
- `bonus_stack`
- `guarantee`
- `cta_2`
- `faq`
- `cta_3_ps`

Deterministic mapping targets:

Path source-of-truth for V1:
- Every target path below must exist in the shipped template at `mos/backend/app/templates/funnels/sales_pdp.json`.
- We do not allow synthetic/nonexistent component paths in the bridge mapper.

| Source section | Template target path(s) | Mapping rule |
|---|---|---|
| `hero_stack` | `SalesPdpHero.config.purchase.title`, `SalesPdpHeader.config.cta.label`, `SalesPdpHero.config.purchase.cta.labelTemplate` | Title/primary CTA extraction from section lead + first CTA link text |
| `problem_recap` | `SalesPdpStoryProblem.config.title`, `SalesPdpStoryProblem.config.paragraphs`, `SalesPdpStoryProblem.config.emphasisLine` | First heading sentence -> title, body paragraphs preserved |
| `mechanism_comparison` | `SalesPdpStorySolution.config.title`, `SalesPdpStorySolution.config.paragraphs`, `SalesPdpStorySolution.config.bullets`, `SalesPdpComparison.config.rows` | Mechanism statements -> bullets; explicit compare statements -> comparison rows |
| `identity_bridge` | `SalesPdpStorySolution.config.paragraphs` (append block) | Append with section marker for traceability |
| `social_proof` | `SalesPdpReviewWall.config.badge`, `SalesPdpReviewWall.config.title`, `SalesPdpReviewWall.config.ratingLabel`, `SalesPdpReviews.config.data.summary.customersSay` | Summary text into review wall headings + review summary copy |
| `cta_1` | `SalesPdpHero.config.purchase.cta.labelTemplate`, `SalesPdpHero.config.purchase.cta.subBullets` | Primary CTA line + support bullets |
| `whats_inside` | `SalesPdpHero.config.purchase.benefits`, `SalesPdpHero.config.purchase.offer.helperText` | Bullet extraction to benefits + helper text |
| `bonus_stack` | `SalesPdpHero.config.gallery.freeGifts.title`, `SalesPdpHero.config.gallery.freeGifts.body` | Bonus summary mapped into free-gifts block |
| `guarantee` | `SalesPdpGuarantee.config.title`, `SalesPdpGuarantee.config.paragraphs`, `SalesPdpGuarantee.config.whyTitle`, `SalesPdpGuarantee.config.whyBody`, `SalesPdpGuarantee.config.closingLine` | Deterministic paragraph split and assignment |
| `cta_2` | `SalesPdpGuarantee.config.closingLine` (append CTA sentence) | Merge secondary CTA into closing line block |
| `faq` | `SalesPdpFaq.config.title`, `SalesPdpFaq.config.items` | Parse Q/A pairs into FAQ items |
| `cta_3_ps` | `residual_copy.cta_3_ps` + `copy_pack.cta.close` | Preserve final CTA/P.S. for explicit generation guidance where template has no dedicated terminal CTA module |

Hard mapping requirements:
- `hero_stack`, `problem_recap`, `mechanism_comparison`, `guarantee`, and `faq` must map successfully.
- At least one CTA must be mapped into template patch (`cta_1` or `cta_2`).

## 6) Bridge build algorithm

1. Parse markdown sections.
- Use H2 section parser and canonical section normalization.

2. Normalize section keys.
- Match by canonical markers from copy contract profile.
- Reject if required section keys are missing.

3. Extract primitives.
- paragraphs
- bullets
- markdown links/anchor text
- Q/A blocks

4. Build deterministic `template_patch`.
- First validate that every configured target path exists in base template `puckData`.
- If any target path is missing, fail angle-run with a path-level bridge error.
- Create component-path updates only for supported template fields.
- Preserve existing non-copy fields from template base (IDs, media placeholders, structural configs).

5. Build `copy_pack`.
- Compact object containing headline, key claims, CTA lines, guarantee terms, FAQ summary, and unresolved residual copy.

6. Validate bridge payload.
- Schema validation for `StrategyV2TemplateBridgeV1`.
- Structural validation against template required components.
- Content validation for required mapped sections and CTA presence.
 - Cross-check `template_fit_pack` coverage against mapping requirements before patch emit.

7. Persist bridge artifact in angle-run bundle.

## 7) Bridge application to templating

Application path for each angle-run:
1. Load base template `puckData` for `template_id`.
2. Apply `template_patch` deterministically to base `puckData`.
3. Run existing template validators.
4. Pass patched `puckData` into funnel generation as `current_puck_data`.
5. Pass `copy_pack` to generation so residual copy is explicitly consumed in valid template fields.
6. Persist final generated `puckData` and reference bridge artifact IDs.

Important behavior:
- Bridge patch is primary source of truth for mapped copy fields.
- Generation step may enrich only allowed fields and must preserve required template structure.

## 8) Exact integration points

1. Add new bridge module.
- New file: `mos/backend/app/strategy_v2/template_bridge.py`
- Responsibilities: section normalization, mapper, validator, patch builder.

2. Extend Strategy V2 copy activity output.
- File: `mos/backend/app/temporal/activities/strategy_v2_activities.py`
- After copy PASS, generate and validate `template_fit_pack`, then build bridge and include both in angle-run output.

3. Extend downstream packet.
- File: `mos/backend/app/strategy_v2/downstream.py`
- Add angle-run bridge references and copy pack payload.

4. Update funnel draft activity.
- File: `mos/backend/app/temporal/activities/campaign_intent_activities.py`
- For each angle-run, load bridge, apply template patch to `puck_data`, pass `copy_pack` to draft generation.

5. Keep Funnel AI contract usage explicit.
- Files: `mos/backend/app/agent/funnel_tools.py`, `mos/backend/app/services/funnel_ai.py`
- Use provided `current_puck_data` + `copyPack`; do not rely on coarse summary-only context.

## 9) Fail-fast rules for bridge

1. Missing required section mappings -> fail angle-run.
2. Unsupported template ID for deterministic mapper -> fail angle-run.
3. Invalid patched `puckData` under template validators -> fail angle-run.
4. Missing bridge for downstream templating step -> fail angle-run.

Errors must include:
- `angle_run_id`
- `angle_id`
- failing gate/reason code
- remediation hint

## 10) Observability for bridge

Persist per angle-run:
- section normalization report
- mapping report (`mapped`, `unmapped`, `residual`)
- template patch hash
- bridge validation report
- template validation report after patch
- funnel generation request IDs

This gives exact traceability from source copy section to final template fields.

## 11) Implementation plan (enhanced)

1. Add angle-run contracts/storage.
2. Add source-stack validation scripts and mismatch report artifacts.
3. Add `template_bridge.py` and bridge schemas.
4. Add `template_fit_pack` schema and copy-stage extraction step.
5. Implement sales-pdp mapper with deterministic patch builder.
6. Hook template-fit + bridge generation into Strategy V2 copy completion.
7. Hook bridge application into funnel draft generation path.
8. Add strict validation/error gates and observability payloads.
9. Add tests.

## 12) Test plan

Unit tests:
- section normalization from real Stage 4 markdown
- mapping rules per source section
- required gate enforcement
- bridge schema validation
- `template_fit_pack` schema validation and coverage checks
- source-stack mismatch classification (P0/P1/P2)

Integration tests:
- one selected angle -> one complete angle-run with bridge + funnel output
- two selected angles -> two independent angle-runs
- missing required section mapping -> deterministic failure
- unsupported template -> deterministic failure
- invalid `template_fit_pack` -> repair loop then deterministic failure if unresolved

Regression checks:
- template required components remain present after patch
- checkout-related fields in `SalesPdpHero.config.purchase` remain valid
- no unresolved P0 mismatches in `template_bridge_mismatch_report.md`

## 13) Acceptance criteria

1. One selected angle produces exactly one complete angle-run chain.
2. N selected angles produce N independent angle-run chains.
3. Each angle-run produces angle-specific offer, copy, bridge, and funnel outputs.
4. Bridge patch is applied before funnel generation and validated.
5. Failures are explicit, deterministic, and remediation-friendly.
