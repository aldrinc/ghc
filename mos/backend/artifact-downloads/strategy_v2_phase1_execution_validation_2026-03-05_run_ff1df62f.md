# Strategy V2 Phase 1 Execution Validation (2026-03-05)

## Source + Run Context
- Source Strategy V2 run id: `732c4f5c-7d12-42bf-8014-75c9bfd00230`
- Source temporal workflow id: `strategy-v2-0d3186be-2c4f-4d5d-a810-d87b3b35265e-dc897cce-ac0d-41d6-b857-66e7468080a5-502a0317-3e6a-484e-b114-1eaeee68b334-b206f2e3-0e28-4bec-b5f0-ab86f7a0ecf1`
- Copy artifact id: `5a17ae17-f8d5-4b97-9b3c-0f4798ff530e`

## Executed Validation Run (Fast, Media Deferred)
- Generated at UTC: `2026-03-05T18:19:34.267011+00:00`
- Campaign id: `e1ab4199-1878-49ad-aad2-59c65a88367f`
- Funnel id: `ff1df62f-cca8-477f-9268-c7e4616ad09b`
- Funnel route slug:
  - `ang-a02-herbdrug-interaction-non-answer-fix-phase1-fast-20260305181924-funnel-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow`
- Pages:
  - Pre-sales page id: `277d6672-c2db-43ce-81c3-099f8db90e0e` (draft `672d1240-b1b7-4e26-8c8b-ac1b0993ada3`)
  - Sales page id: `2864646c-809a-496d-9df2-3e6e8e908791` (draft `899c59ca-fbc6-4740-9473-fd7bba7b0a57`)
- Mode details:
  - `generate_testimonials=false`
  - `async_media_enrichment=true`
  - queued media enrichment jobs: `2`

## Preview Links
Using your frontend service on `5275`:
- Pre-sales: `http://localhost:5275/f/502a0317/ang-a02-herbdrug-interaction-non-answer-fix-phase1-fast-20260305181924-funnel-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/pre-sales`
- Sales: `http://localhost:5275/f/502a0317/ang-a02-herbdrug-interaction-non-answer-fix-phase1-fast-20260305181924-funnel-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/sales`

Backend public endpoints on `8008`:
- Meta: `http://localhost:8008/public/funnels/502a0317/ang-a02-herbdrug-interaction-non-answer-fix-phase1-fast-20260305181924-funnel-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/meta`
- Pre-sales JSON: `http://localhost:8008/public/funnels/502a0317/ang-a02-herbdrug-interaction-non-answer-fix-phase1-fast-20260305181924-funnel-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/pages/pre-sales`
- Sales JSON: `http://localhost:8008/public/funnels/502a0317/ang-a02-herbdrug-interaction-non-answer-fix-phase1-fast-20260305181924-funnel-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/pages/sales`

## Validated Changes In This Output
- Pre-sales `Shop` -> `Learn more` normalization is active:
  - `PreSalesPitch.props.config.cta.label = Learn more`
  - `PreSalesFloatingCta.props.config.label = Learn more`
- Pre-sales testimonial section between listicle and marquee is removed:
  - `PreSalesReviews` component absent from pre-sales page composition.
- Footer policy links and payment icons are injected on both pages from compliance profile:
  - links: `Privacy`, `Terms`, `Returns`, `Shipping`
  - payment icons: `american_express`, `apple_pay`, `google_pay`, `maestro`, `mastercard`, `paypal`, `visa`
  - copyright: `© 2026 Aldrin Clement`
- Sales hero selector `seeWhyLabel` is removed (`None` in output).
- Strict schema/fit-pack normalization no longer fails for this source packet in pre-sales and sales payload validation.

## Runtime Blockers Identified (Full Media + Testimonials Path)
When executing full inline media/testimonial generation (`async_media_enrichment=false`, `generate_testimonials=true`), the run is currently unstable due to two concrete long-stall points:

1. Testimonial Claude structured call can block for a long period:
- Stack path: `funnel_tools -> funnel_testimonials.generate_funnel_page_testimonials -> claude_files.call_claude_structured_message -> httpx.Client.post`
- Observed while interrupted in live run.

2. Sales PDP carousel image render can stall in threaded renderer:
- Stack path: `funnel_testimonials.generate_sales_pdp_carousel_images -> testimonial_renderer.renderer.ThreadedTestimonialRenderer.render_png -> queue.get()`
- Observed while interrupted in live run.

These blockers are why this validation artifact uses the fast/deferred media mode for deterministic completion.

## Code Changes Applied This Session
- `app/strategy_v2/template_bridge.py`
  - Added strict pre-sales legacy clipping/normalization for subtitle, badge values, reasons body, pitch bullets/title, and marquee compaction.
  - Added strict sales legacy clipping/normalization for purchase title, problem/guarantee/faq text caps, and marquee compaction.
  - Added/updated helper clipping utilities and ordering so normalized values are actually persisted before final prune.
- `app/temporal/activities/campaign_intent_activities.py`
  - Added compliance-profile footer policy link/payment icon injection for pre-sales and sales pages during pinned Strategy V2 payload application.
  - Footer now uses Shopify policy URLs + required payment icon list in fast materialization flows.
- `tests/test_strategy_v2_template_bridge.py`
  - Added regression test for pre-sales legacy clipping against strict contract caps.

## Test Validation Executed
- `pytest -q tests/test_strategy_v2_template_bridge.py` -> pass
- `pytest -q tests/test_strategy_v2_launch_api.py -k launch` -> pass
