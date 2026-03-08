# Offer Agent V1 Spec — Discount + 3 Bonuses (Refined)

Date: 2026-03-05  
Status: Implementation-ready spec for engineering

## 1) Locked V1 Decisions

These are non-negotiable for V1:

- Single default offer format only: `product + discount + exactly 3 bonuses`.
- Exactly 3 offer variants:
  - `single_device`
  - `share_and_save`
  - `family_bundle`
- Exactly 3 bonuses per variant (not 4, not variable).
- No advanced discount architecture in V1:
  - no tier ladders
  - no conditional discount trees
  - no complex coupon stacks
- Offer modules must be compact and low-verbosity.
- Manual post-generation editing is allowed and should be first-class in flow.

## 2) V1 Non-Goals

Out of scope for this phase:

- Additional offer archetypes beyond `discount + 3 bonuses`.
- Dynamic variant count.
- Multi-stage pricing experiments beyond the 3 fixed variants.
- Fancy/long-form offer narrative generation as required output.

## 3) Required Functional Outcomes

- Offer output includes structured metadata for:
  - pricing
  - savings
  - best-value logic
- Offer agent explicitly receives and uses product type:
  - `physical`, `digital`, `book`, `device`, etc.
- Messaging is validated against real bundle contents and real product type.
- Missing offer data is caught in a dedicated structured checkpoint before variant generation.
- Bonus objects are reusable across product offers (not free-text only).

## 4) Canonical V1 Offer Shape

Each generated variant must conform to this shape:

```json
{
  "variant_id": "single_device | share_and_save | family_bundle",
  "offer_format": "DISCOUNT_PLUS_3_BONUSES_V1",
  "core_promise": "string",
  "product_offer": {
    "product_type": "physical | digital | book | device | other",
    "product_title": "string",
    "quantity": 1,
    "unit_label": "string"
  },
  "discount": {
    "list_price_cents": 0,
    "offer_price_cents": 0,
    "currency": "USD",
    "discount_amount_cents": 0,
    "discount_percent": 0,
    "label": "string"
  },
  "bonuses": [
    {
      "bonus_id": "string",
      "title": "string",
      "type": "checklist | guide | script | template | worksheet | other",
      "delivery_format": "pdf | video | email | app | physical | other",
      "copy_short": "string",
      "position": 1
    },
    {
      "bonus_id": "string",
      "title": "string",
      "type": "checklist | guide | script | template | worksheet | other",
      "delivery_format": "pdf | video | email | app | physical | other",
      "copy_short": "string",
      "position": 2
    },
    {
      "bonus_id": "string",
      "title": "string",
      "type": "checklist | guide | script | template | worksheet | other",
      "delivery_format": "pdf | video | email | app | physical | other",
      "copy_short": "string",
      "position": 3
    }
  ],
  "bundle_contents": {
    "includes": ["string"],
    "excludes": ["string"]
  },
  "pricing_metadata": {
    "display_price": "string",
    "billing_type": "one_time | subscription",
    "payment_options": ["string"]
  },
  "savings_metadata": {
    "savings_amount_cents": 0,
    "savings_percent": 0,
    "savings_basis": "vs_list_price"
  },
  "best_value_metadata": {
    "is_best_value": true,
    "reason_short": "string"
  }
}
```

## 5) Verbosity Constraints (Hard)

Apply runtime schema limits and reject on violation:

- `core_promise`: `<= 140` chars
- `discount.label`: `<= 60` chars
- `best_value_metadata.reason_short`: `<= 120` chars
- `bonuses[*].title`: `<= 70` chars
- `bonuses[*].copy_short`: `<= 140` chars
- `pricing_metadata.display_price`: `<= 40` chars

No silent truncation. Return explicit validation error with field path.

## 6) Product-Type Pass-Through (Fix Required)

## 6.1 Input requirement

Before Step 04 runs, product type must be resolved from persisted product data and injected into Step 04/05 prompt variables.

Required resolved field:

- `product_type`

## 6.2 Validation requirement

Generated messaging must pass:

- `product_type` congruence checks (for example, no “device setup” language for digital/book products).
- Bundle congruence checks (no claims for items not present in `bundle_contents.includes`).

If mismatch: fail with deterministic error listing offending claims.

## 7) Missing Offer Data Checkpoint (New Structured Step)

Add a dedicated readiness step before Step 04 generation (`v2-08a` recommended):

Input: stage2 + offer_pipeline_output + persisted product/offer context  
Output:

```json
{
  "status": "ready | blocked",
  "missing_fields": ["string"],
  "inconsistent_fields": ["string"],
  "required_operator_inputs": ["string"],
  "remediation_steps": ["string"]
}
```

Blocking conditions include:

- Missing `product_type`
- Missing numeric list/offer price data
- Missing/invalid discount math
- Missing bundle contents for selected variant IDs
- Bonus count not equal to 3

V1 policy: block with clear error; do not auto-fallback.

## 8) Variant Definitions (Fixed)

All runs must produce exactly these variant IDs:

- `single_device`: single-unit framing
- `share_and_save`: multi-unit share framing
- `family_bundle`: family bundle framing

All 3 must use same offer format (`discount + 3 bonuses`) and differ only in permitted axes:

- quantity framing
- discount magnitude
- best-value designation
- bundle inclusion labeling

## 9) Scoring Changes (Explicit Fidelity Dimensions)

Add three explicit Step 05 dimensions:

- `pricing_fidelity`
- `savings_fidelity`
- `best_value_fidelity`

## 9.1 Dimension intent

- `pricing_fidelity`: price fields are internally consistent and match displayed offer claims.
- `savings_fidelity`: savings math is correct and basis is explicit.
- `best_value_fidelity`: “best value” label is logically justified vs sibling variants.

## 9.2 Composite scorer update

Extend dimension set and weights in `composite_scorer` to include these three dimensions (11 total).
Recommended starting weights:

- `value_equation`: `0.11`
- `objection_coverage`: `0.11`
- `competitive_differentiation`: `0.11`
- `compliance_safety`: `0.08`
- `internal_consistency`: `0.08`
- `clarity_simplicity`: `0.08`
- `bottleneck_resilience`: `0.08`
- `momentum_continuity`: `0.10`
- `pricing_fidelity`: `0.09`
- `savings_fidelity`: `0.08`
- `best_value_fidelity`: `0.08`

Total: `1.00`

## 10) Bonus Reusability Model

Use normalized bonus objects instead of only free-text value stack extraction.

V1 reusable bonus object requirements:

- Stable `bonus_id`
- Short title + short copy
- Type + delivery format
- Position (1..3)
- Optional product linkage (`linked_product_id`) when bonus is a real existing product

Persistence target:

- Include under `strategyV2Offer` payload in `ProductOffer.options_schema`.
- Carry into Stage 3 and copy context artifacts.

## 11) Manual Edit Path (Short-Term Practical Flow)

Support quick operator correction without overbuilding automation:

1. Generate structured variant payloads.
2. Present editable JSON payload to operator.
3. Re-validate contract + run Step 05 scoring on edited payload.
4. Proceed to winner selection.

Operator edit path must run through same validators and fidelity scoring dimensions.

## 12) File-Level Implementation Plan

## 12.1 Prompt assets

- `V2 Fixes/Offer Agent — Final/prompts/step-04-offer-construction.md`
  - Replace broad output requirement with strict V1 format contract.
  - Enforce exactly 3 variant IDs and exactly 3 bonuses each.
  - Add compact module language limits.
- `V2 Fixes/Offer Agent — Final/prompts/step-05-self-evaluation-scoring.md`
  - Add explicit evaluation instructions for pricing/savings/best-value fidelity.

## 12.2 Runtime + workflow

- `mos/backend/app/temporal/activities/strategy_v2_activities.py`
  - Add `v2-08a` readiness activity.
  - Update Step 04 schema parsing to new V1 fields.
  - Enforce strict bonus count = 3.
  - Pass product type + bundle context into Step 04/05 vars.
  - Persist structured pricing/savings/best-value/bonus metadata.
- `mos/backend/app/temporal/workflows/strategy_v2.py`
  - Insert readiness checkpoint before `build_strategy_v2_offer_variants_activity`.
- `mos/backend/app/temporal/workflows/strategy_v2_launch.py`
  - Keep best-variant selection compatible with new dimensions.

## 12.3 Contracts + translation

- `mos/backend/app/strategy_v2/contracts.py`
  - Extend Stage3 contract for structured pricing/savings/best-value metadata.
- `mos/backend/app/strategy_v2/translation.py`
  - Include structured metadata in copy context serialization.

## 12.4 Scoring

- `V2 Fixes/Offer Agent — Final/scoring-tools/scoring_tools.py`
  - Add 3 fidelity dimensions to `DIMENSION_WEIGHTS` and scoring output.
- `mos/backend/app/strategy_v2/scorers.py`
  - No logic change if dynamic import is retained; ensure schema compatibility.

## 12.5 Template/UI payload handoff

- `mos/backend/app/strategy_v2/template_bridge.py`
  - Read structured pricing/savings/best-value + bonus objects instead of deriving from long text.

## 13) Test Plan (Required)

Update/add tests:

- `mos/backend/tests/test_strategy_v2_prompt_runtime.py`
  - Step 04/05 schema tests for new required fields and char limits.
  - readiness checkpoint blocked/ready behavior.
- `mos/backend/tests/test_strategy_v2_workflow_api.py`
  - End-to-end payload includes pricing/savings/best-value metadata.
  - Variant IDs must be exactly `single_device`, `share_and_save`, `family_bundle`.
- `mos/backend/tests/test_strategy_v2_workflow_ordering.py`
  - New `v2-08a` activity ordering assertion.
- `mos/backend/tests/test_strategy_v2_translation_and_scorers.py`
  - Composite scorer includes 11 dimensions and updated weights.
- `mos/backend/tests/test_strategy_v2_copy_pipeline_guards.py`
  - Product-type and bundle-content congruence guard checks.

## 14) Acceptance Criteria

All must pass:

- Offer generator always outputs exactly 3 variants and exactly 3 bonuses per variant.
- Output includes structured `pricing_metadata`, `savings_metadata`, and `best_value_metadata` for every variant.
- Product type is present and used in generation + validation.
- Bundle-contents mismatch claims are blocked with explicit error.
- New fidelity dimensions appear in Step 05 evaluation and composite output.
- Bonus copy is short-form and within hard limits.
- Manual edit path can revalidate and rescore edited payload.

## 15) Rollout Sequence

1. Contracts + readiness checkpoint (`v2-08a`).
2. Step 04 prompt/schema migration to V1 format.
3. Step 05 fidelity-dimension migration + scorer weights.
4. Stage3 persistence + template bridge consumption.
5. Manual edit path and final stabilization tests.

## 16) Guardrails

- Do not change offer model selection (`settings.STRATEGY_V2_OFFER_MODEL`) in this scope.
- Do not introduce hidden fallback logic for missing required offer data.
- Fail fast with deterministic, field-path-specific errors.
