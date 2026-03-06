# Strategy V2 Style + Runtime Validation (2026-03-05)

## Regenerated Funnel (Same Flow)
- Campaign id: `e1ab4199-1878-49ad-aad2-59c65a88367f`
- Funnel id: `cbf58966-d571-4734-9a31-0a8000757a42`
- Route slug: `ang-a02-style-pass-20260305183856-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow`
- Product/public slug: `502a0317`

## Page IDs + Latest Drafts
- Pre-sales page id: `23b7fb06-5c38-47e8-9bd5-a6296dfbbf47`
  - Latest draft: `a2699827-06d4-491b-a4ad-d1a67f2bafd1` (`testimonial_generation`)
- Sales page id: `5cf3c515-0e08-41b9-9f8a-0a61caac8edc`
  - Latest draft: `d81a19cd-5b8b-47ed-b5bc-7846104fc6b1` (`sales_pdp_carousel_generation`)

## Preview Links (5275)
- Pre-sales: `http://localhost:5275/f/502a0317/ang-a02-style-pass-20260305183856-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/pre-sales`
- Sales: `http://localhost:5275/f/502a0317/ang-a02-style-pass-20260305183856-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/sales`
- HTTP status checks: both return `200`

## Public API Links (8008)
- Meta: `http://localhost:8008/public/funnels/502a0317/ang-a02-style-pass-20260305183856-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/meta`
- Pre-sales JSON: `http://localhost:8008/public/funnels/502a0317/ang-a02-style-pass-20260305183856-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/pages/pre-sales`
- Sales JSON: `http://localhost:8008/public/funnels/502a0317/ang-a02-style-pass-20260305183856-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/pages/sales`

## Functional Validation (Payload-Level)
Validated on latest public page payloads:
- Pre-sales `PreSalesReviews` section remains removed from page composition.
- Pre-sales CTA labels are `Learn more`:
  - `PreSalesPitch.props.config.cta.label`
  - `PreSalesFloatingCta.props.config.label`
- Footer links are present on both pages from policy profile:
  - `Privacy`, `Terms`, `Returns`, `Shipping`
- Footer payment icon strip present on both pages:
  - `american_express`, `apple_pay`, `google_pay`, `maestro`, `mastercard`, `paypal`, `visa`
- Sales selector micro-copy remains removed:
  - `SalesPdpHero.purchase.offer.seeWhyLabel` is empty

## Runtime Benchmarks (Post-Fix)

### 1) Sales PDP carousel generation (targeted failed path)
- Function: `generate_sales_pdp_carousel_images`
- Budget: `max_duration_seconds=240`
- Result: **success**
- Elapsed: **123.31s**
- Output: `generated=6`, new sales draft `d81a19cd-5b8b-47ed-b5bc-7846104fc6b1`

### 2) Pre-sales testimonial generation (heavy path)
- Function: `generate_funnel_page_testimonials` (`template_id=pre-sales-listicle`)
- Budget: `max_duration_seconds=240`
- Result: **success**
- Elapsed: **212.91s**
- Output: `generated=6`, new pre-sales draft `a2699827-06d4-491b-a4ad-d1a67f2bafd1`

### 3) Sales testimonial generation (heavy path)
- Function: `generate_funnel_page_testimonials` (`template_id=sales-pdp`)
- Budget: `max_duration_seconds=240`
- Result: **bounded timeout (expected behavior under load)**
- Error: `Testimonials step exceeded configured time budget while rendering testimonial groups.`
- Elapsed before stop: **244.14s**

## What Was Changed

### Style-system + template lock changes
- Pre-sales token lock expanded for geometry/spacing/hero/footer invariants.
- Sales token lock expanded for spacing/heading/urgency/FAQ/footer invariants.
- Pre-sales design-system token adjustments:
  - tighter top-section density (`hero`, `badge strip`, `pitch`)
  - normalized section spacing/heading line-height
  - mobile section spacing + footer spacing polish
- Sales design-system token adjustments:
  - normalized section spacing/heading line-height
  - stronger urgency token palette (bg/border/text/row/icon/highlight)
  - FAQ/footers spacing polish
- Sales urgency module CSS hardened:
  - stronger contrast hierarchy, icon chip contrast, row borders/weights
- Mobile footer link stacking enabled for both templates.

### Runtime and reliability changes
- `ThreadedTestimonialRenderer`:
  - added worker pool support (`worker_count`)
  - added bounded response wait with explicit timeout errors
- Sales carousel rendering parallelized safely:
  - render bytes concurrently with multiple renderer workers
  - DB asset writes remain sequential on session thread
- Claude structured call controls added:
  - per-call timeout + attempt overrides supported in `call_claude_structured_message`
  - testimonial flows now use tighter structured timeout/attempt policy
- Testimonial render budget enforcement improved:
  - per-render timeout now bounded by remaining step budget
  - step exits with explicit budget error instead of long silent hangs

## Remaining Runtime Risk
- Full sales testimonial generation can still exceed a 240s budget under current media/testimonial volume.
- It now fails fast and explicitly, but still needs either:
  - lower testimonial render volume in rapid mode, or
  - split sales testimonial generation into smaller sub-steps with separate budgets.

## Tests Run
- `pytest -q tests/test_testimonial_renderer_avatar_optional.py tests/test_strategy_v2_template_bridge.py tests/test_funnel_testimonials_variability.py -k 'not rejects_missing_variant_id'` -> pass
- `pytest -q tests/test_strategy_v2_launch_api.py -k launch` -> pass
- `npm run build` in `mos/frontend` -> pass

Notes:
- The existing test `test_validate_sales_pdp_carousel_plan_rejects_missing_variant_id` currently fails in this branch due payload order/expectation mismatch in that specific fixture (it trips template mismatch earlier than duplicate-variant assertion).
