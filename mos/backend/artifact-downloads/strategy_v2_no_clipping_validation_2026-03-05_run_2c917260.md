# Strategy V2 No-Clipping Validation (2026-03-05)

## What Changed
- Removed TemplateBridge clipping behavior so bridge now normalizes shape but does not truncate copy.
- Added stronger template-payload prompt constraints for pre-sales and sales payload generation.
- Increased rapid `template_payload_only` page repair attempts from 3 -> 5.
- Fixed product-name override application so `SalesPdpHero.props.config.purchase.title` patch value is forced to `stage3.product_name` at final patch-assembly time.
- Relaxed two pre-sales contract edges to reduce brittle rejects without clipping:
  - `reasons[].body` max length: `360 -> 420`
  - `marquee[]` word count: `1-3 -> 1-4`

## Regenerated Funnel (Fast Mode, No Testimonials/Images)
- Funnel id: `2c917260-9237-46ae-82a8-4b0189e087c8`
- Public id: `a6236ab1-2932-4dac-b690-a192f3b6d920`
- Route slug:
  - `ang-a02-rapid-pass-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow`
- Experiment spec id: `exp-A02-Interaction Triage Workflow`

## Page IDs
- Pre-sales: `3f7dba3e-1121-4655-aeaa-21f4a15ca855`
- Sales: `9c6fcf78-cfcb-402d-8645-f585766e9279`

## Preview Links (5275)
- Pre-sales:
  - `http://localhost:5275/f/502a0317/ang-a02-rapid-pass-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/pre-sales`
- Sales:
  - `http://localhost:5275/f/502a0317/ang-a02-rapid-pass-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/sales`
- HTTP status: both `200`

## Public API Links (8008)
- Meta:
  - `http://localhost:8008/public/funnels/502a0317/ang-a02-rapid-pass-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/meta`
- Pre-sales JSON:
  - `http://localhost:8008/public/funnels/502a0317/ang-a02-rapid-pass-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/pages/pre-sales`
- Sales JSON:
  - `http://localhost:8008/public/funnels/502a0317/ang-a02-rapid-pass-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/pages/sales`
- HTTP status: all `200`

## Payload Validation Checks
- Sales hero title is product-name-only:
  - `SalesPdpHero.props.config.purchase.title = "The Honest Herbalist Handbook"`
- Sales selector microcopy remains removed:
  - `SalesPdpHero.props.config.purchase.offer.seeWhyLabel = ""`
- Pre-sales CTA labels are normalized:
  - `PreSalesPitch.props.config.cta.label = "Learn more"`
  - `PreSalesFloatingCta.props.config.label = "Learn more"`
- Pre-sales reasons (including #3 and #4) are present and no longer hard-truncated by bridge clipping.
  - Reason 3 body length: `342`
  - Reason 4 body length: `354`

## Build/Test Validation
- `python -m py_compile app/strategy_v2/template_bridge.py app/temporal/activities/strategy_v2_activities.py` -> pass
- `pytest -q tests/test_strategy_v2_template_bridge.py` -> pass
- `npm run build` (frontend) -> pass

## Notes
- TemplateBridge now fails validation when payload constraints are violated instead of mutating copy.
- The copy engine prompt path now carries explicit field limits so retries target the exact schema constraints.
