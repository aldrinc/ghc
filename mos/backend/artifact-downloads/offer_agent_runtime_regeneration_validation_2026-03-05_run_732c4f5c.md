# Offer Agent Runtime Regeneration Validation (2026-03-05)

## Source Flow
- Source Strategy V2 run id: `732c4f5c-7d12-42bf-8014-75c9bfd00230`
- Temporal workflow id: `strategy-v2-0d3186be-2c4f-4d5d-a810-d87b3b35265e-dc897cce-ac0d-41d6-b857-66e7468080a5-502a0317-3e6a-484e-b114-1eaeee68b334-b206f2e3-0e28-4bec-b5f0-ab86f7a0ecf1`
- Org id: `0d3186be-2c4f-4d5d-a810-d87b3b35265e`
- Client id: `dc897cce-ac0d-41d6-b857-66e7468080a5`
- Product id: `502a0317-3e6a-484e-b114-1eaeee68b334` (The Honest Herbalist Handbook)
- Product offer id: `40c87861-d7c8-448e-9220-7f9450f58050`

## First Replay Attempt (Expected Block)
- Step `v2-08a` initially blocked with:
  - `Offer data readiness requires exactly 3 linked offer bonuses for V1.`
- Blocked readiness artifact id: `76ca3c61-681d-4d8e-b4ca-a92e1dea518e`

This validates the new structured missing-data gate is active and enforcing the contract.

## Data Remediation Applied
To satisfy the v1 contract (`product + discount + exactly 3 bonuses`) for this existing flow:
- Core product `product_type` normalized to: `digital`
- Exactly 3 persisted bonus products were materialized from the existing approved offer stack and linked to the default offer:
  1. `56c68de9-4c3a-4841-a309-183828de38e1` — `“Ask Anyway” Clinician/Pharmacist Question Script (copy/paste prompts + call checklist)`
  2. `3dff9d65-811b-47a2-830c-1524615f9d15` — `Customizable Med/Supplement List Builder (fillable PDF + examples)`
  3. `ba6f5b6f-60b8-4f31-b38e-15799c40af19` — `Red-Flag Herb/Food List (contraindication flags to research first)`

## Successful Offer Regeneration Replay
Replayed locally against the existing source run:
- `v2-08a` readiness
- `v2-08b` offer variants + scoring
- `v2-09` offer winner finalization

Generated artifact ids:
- Readiness step payload (`v2-08a`): `772063f5-c2bc-4b0e-b12c-960e6069f7f2`
- Offer variants step payload (`v2-08b`): `4469f7ac-211e-4696-baac-17dd04cdeb7a`
- Offer winner step payload (`v2-09`): `1497c350-16d4-477f-86a5-4dfac8109ccf`
- Strategy V2 offer artifact: `06b82963-c9b1-4645-946c-b209daf2d9d8`
- Stage 3 artifact: `25a859f3-d4bd-4911-9b17-e3e3ba8e515b`
- Copy context artifact: `42f0575e-fb5e-48b6-a690-c454711a305a`

## Validation Checks Against Marketing Requirements

### 1) Variant structure
- Variant ids are exactly:
  - `single_device`
  - `share_and_save`
  - `family_bundle`
- Each variant includes exactly `3` bonuses.

### 2) Pricing/savings/best-value metadata
- Each variant includes structured:
  - `pricing_metadata`
  - `savings_metadata`
  - `best_value_metadata`
- Best-value designation is explicit (exactly one variant marked best-value):
  - `family_bundle`: `is_best_value=true`

### 3) Product type and bundle consistency
- Readiness context product type: `digital`
- Variant product types: all `digital`
- Stage 3 product type: `digital`
- Stage 3 offer format: `DISCOUNT_PLUS_3_BONUSES_V1`
- Stage 3 bonus stack count: `3`

### 4) Scoring dimensions
Composite scorer output includes all 11 dimensions:
- `value_equation`
- `objection_coverage`
- `competitive_differentiation`
- `compliance_safety`
- `internal_consistency`
- `clarity_simplicity`
- `bottleneck_resilience`
- `momentum_continuity`
- `pricing_fidelity`
- `savings_fidelity`
- `best_value_fidelity`

## Winner Selected in Replay
- Selected variant id: `single_device`
- Offer format: `DISCOUNT_PLUS_3_BONUSES_V1`
- Product type: `digital`
- Bonus count: `3`
- Structured metadata present:
  - `pricing_metadata`: yes
  - `savings_metadata`: yes
  - `best_value_metadata`: yes

## Notes
- This replay was an offer-stage regeneration against the existing Strategy V2 source run; it did not generate a new funnel slug/page pair.
- The first blocked readiness artifact is retained intentionally as audit evidence that the missing-offer-data gate works.

## Post-Regeneration Runtime Fix (2026-03-05)
After replay, the sales page still rendered stale checkout options (`variant_a` / `Default Title`). Root cause was runtime sync behavior:
- Offer winner sync only created price points when none existed.
- Existing stale rows were left unchanged, so checkout kept old ids/titles/prices.

### Code-level fixes applied
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`
  - Offer winner sync now upserts all 3 scored variants (`single_device`, `share_and_save`, `family_bundle`) into `product_offer_price_points`.
  - Existing stale rows are repurposed or removed so offer IDs/titles/prices are authoritative.
- `mos/backend/app/services/funnel_ai.py`
  - Checkout alignment now always enforces price from product variants (pricing fidelity) and sets `compareAt` from variant compare-at price when applicable.
- `mos/backend/app/agent/funnel_tools.py`
  - Product context now passes `compare_at_cents` through to checkout alignment.

### Runtime re-application
- Replayed `v2-09` winner finalization using existing validated outputs to apply the new sync behavior.
- Refreshed the existing sales page draft in-place via media-enrichment-only pass (no AI draft generation).

### Final validation (backend public payload)
- URL: `http://localhost:8008/public/funnels/502a0317/ang-a02-herbdrug-interaction-non-answer-fix-phase1-fast-20260305181924-funnel-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/pages/sales`
- Offer ids now:
  - `single_device`
  - `share_and_save`
  - `family_bundle`
- Offer titles now:
  - `Single Device`
  - `Share & Save`
  - `Family Bundle`
- Offer prices now:
  - `49`
  - `79`
  - `99`
- Assertions:
  - `variant_a` absent
  - `Default Title` absent

### Frontend validation URL
- `http://localhost:5275/f/502a0317/ang-a02-herbdrug-interaction-non-answer-fix-phase1-fast-20260305181924-funnel-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/sales`
