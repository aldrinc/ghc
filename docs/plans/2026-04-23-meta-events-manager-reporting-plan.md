# Meta Events Manager Reporting Agent Plan

Decision: build the first autonomous reporting agent on top of Meta Ads API + Meta Events Manager data only. PostHog is deferred. Use Meta object state, ad insights, and Meta event/action counts to produce a daily report with recommendations. Do not build a full telemetry mirror first.

This plan supersedes the earlier PostHog-first direction for v1.

## What This Agent Should Do

The v1 agent should let strategy review one daily report instead of opening Meta Ads Manager.

The report should answer:

- What is live, paused, under review, or blocked?
- Which ads or ad sets should be cut, watched, or considered for scaling?
- Where is the largest funnel drop-off according to Meta event data?
- Is the main problem creative, landing-page efficiency, or checkout completion?

## What We Already Have

The current system already has most of the raw ingredients.

- MOS already pulls live Meta campaign/ad set/ad state plus ad-level insights through `/meta/management/plan` in [`mos/backend/app/routers/meta_ads.py`](../../mos/backend/app/routers/meta_ads.py).
- MOS already computes Meta-derived management metrics and recommendations in [`mos/backend/app/services/meta_media_buying.py`](../../mos/backend/app/services/meta_media_buying.py).
- MOS already persists machine-readable management artifacts:
  - `meta_management_metrics_snapshot`
  - `meta_management_recommended_actions`
- The funnel runtime already emits stage-aware tracking events in [`mos/frontend/src/lib/funnelTracking.ts`](../../mos/frontend/src/lib/funnelTracking.ts).
- Those runtime events are already mapped into Meta pixel/browser events in [`mos/frontend/src/lib/metaFunnelEvents.ts`](../../mos/frontend/src/lib/metaFunnelEvents.ts):
  - `Entered Funnel`
  - `PageView`
  - `ViewContent`
  - `PreSalesToSalesClick`
  - `AddToCart`
- MOS already sends server-side Meta `Purchase` events via CAPI in [`mos/backend/app/services/meta_conversions.py`](../../mos/backend/app/services/meta_conversions.py).
- The QA/tracking metadata already documents the intended Meta tracking contract in [`mos/backend/app/services/paid_ads_qa.py`](../../mos/backend/app/services/paid_ads_qa.py).

## What Meta Can Answer For V1

Meta can answer more than simple ad performance if we treat Events Manager action counts as funnel-stage signals.

| Strategy question | Can Meta answer it for v1? | Notes |
| --- | --- | --- |
| Is the campaign delivering? | Yes | Campaign/ad set/ad state plus insights are already available. |
| Which ads are inefficient? | Yes | CTR, CPC, CPM, spend, frequency, hold rate already exist. |
| Are visitors reaching the landing page? | Yes | Use `landing_page_view`. |
| Are visitors reaching the sales page? | Yes | Use `ViewContent` where the sales page maps to `sales_page_view`. |
| Is there a pre-sales to sales drop-off? | Yes | Use `PreSalesToSalesClick` or `ViewContent` depending on funnel shape. |
| Is there a sales to checkout drop-off? | Mostly | `AddToCart` already exists as the current proxy. |
| Is there a checkout to purchase drop-off? | Partially today, cleanly after one small addition | We have `Purchase`; we should add `InitiateCheckout` so checkout friction is measured directly. |
| Which headline or section is failing? | No, not precisely | Meta can support a likely diagnosis, not a section-level causal proof. |

Important constraint: Meta event/action counts are still aggregated and estimated. They are good enough for funnel-stage diagnosis and recommendations. They are not a user-level event ledger.

## Revised V1 Source Of Truth

For the first agent, use Meta as the operational source of truth.

Specifically:

- Use Meta campaign/ad set/ad state for delivery and review blockers.
- Use Meta ad insights for media efficiency.
- Use Meta action counts and Events Manager-aligned events for funnel-stage drop-off.
- Persist compact report artifacts and source snapshots in MOS for auditability.

Do not require a raw event mirror into MOS before the first version ships.

## Core Gap

The biggest remaining functional gap is not PostHog.

It is this:

- we do not yet turn the current Meta management snapshot into a daily human report
- we do not schedule it
- we do not deliver it
- we do not yet track `InitiateCheckout` as a first-class Meta event in the runtime path

That means the system already knows a lot, but it is still an on-demand console instead of an agent.

## Revised Event Contract

The Meta-only agent should standardize on this funnel event contract.

### Required Meta-visible events

- `Entered Funnel`
- `PageView`
- `ViewContent`
- `PreSalesToSalesClick`
- `AddToCart`
- `InitiateCheckout`
- `Purchase`

### Required stage interpretation

- `Entered Funnel`
  - top-of-funnel session entry marker
- `landing_page_view`
  - first real page-load success marker from Meta
- `ViewContent`
  - sales-page reached
- `PreSalesToSalesClick`
  - pre-sales to sales transition intent
- `AddToCart`
  - sales-page to checkout intent
- `InitiateCheckout`
  - checkout started
- `Purchase`
  - completed order

### One required v1 change

Add `InitiateCheckout` to the runtime mapping when the user actually enters checkout, not only `AddToCart` when they click out of sales.

Without that, the report can still estimate checkout issues, but it cannot separate:

- weak sales-page-to-checkout intent
- from real checkout-start abandonment

cleanly enough for confident recommendations.

## Revised Recommendation Model

The first report should produce two recommendation layers.

### 1. Ad-level recommendations

- `pause_ad`
- `watch_ad`
- `scale_ad`
- `review_ad`

Trigger families:

- high spend + weak CTR
- high spend + high CPC
- high CPM + weak engagement
- low hold rate
- review blocked / `WITH_ISSUES`
- sustained strong CTR + efficient CPC + acceptable downstream funnel metrics

### 2. Funnel-level recommendations

- `creative_problem`
- `landing_page_problem`
- `sales_page_problem`
- `checkout_problem`
- `tracking_problem`

Suggested logic:

- High impressions, low CTR, low hold rate
  - likely creative problem
- Good CTR, weak `landing_page_view`
  - likely page load or landing/tracking problem
- Good `landing_page_view`, weak `ViewContent` or weak `PreSalesToSalesClick`
  - likely pre-sales message-match problem
- Good `ViewContent`, weak `AddToCart`
  - likely sales-page offer or purchase-section problem
- Good `AddToCart`, weak `InitiateCheckout`
  - likely checkout entry or cart transition problem
- Good `InitiateCheckout`, weak `Purchase`
  - likely checkout friction or payment problem

These are inference-based recommendations. The report should say that explicitly.

## What We Need To Add

### Phase 1. Tighten the Meta event contract

Goal: make Events Manager data reliable enough for automated stage analysis.

Build:

- add `InitiateCheckout` emission in the runtime path
- ensure `page_stage` stays attached where useful
- confirm event naming stays stable across generated funnels and imported HTML funnels
- add QA validation that the active Meta tracking contract includes all required events

Success criteria:

- active funnel tracking metadata lists all required browser/server events
- a validation run fails cleanly if `InitiateCheckout` is not wired
- event mappings in management are no longer partially guess-based for checkout analysis

### Phase 2. Build a Meta-only report service

Goal: turn current management JSON into a strategy-readable report.

Build:

- markdown renderer for `MetaManagementPlan`
- report sections:
  - campaign status
  - delivery blockers
  - ad winners and losers
  - custom metrics summary
  - funnel-stage drop-off diagnosis
  - recommendations
  - warnings and data-confidence notes

Add a new artifact:

- `meta_management_report_markdown`

Success criteria:

- one backend call can generate a complete report artifact from the current snapshot
- the report is readable without opening Ads Manager

### Phase 3. Add daily snapshot history

Goal: make the report comparative, not just point-in-time.

Build:

- scheduled daily management run per managed Meta campaign
- compact persisted source snapshot for each run
- previous-report comparison logic

Minimum deltas:

- spend
- CTR
- CPC
- CPM
- LPV
- ViewContent
- AddToCart
- InitiateCheckout
- Purchase
- custom metrics

Success criteria:

- daily report can say what changed since yesterday
- strategy can see whether the account is improving or degrading

### Phase 4. Add delivery

Goal: remove the need to manually open MOS or Ads Manager.

Build:

- Slack delivery of the markdown report
- start with a single daily cadence
- include links back to MOS artifacts and the campaign management panel

Success criteria:

- strategy receives one report per campaign per day
- the report is stable, short, and actionable

## Revised Data Model

We do not need a full raw-event mirror for v1.

We do need a small durable artifact set:

- `meta_management_metrics_snapshot`
- `meta_management_recommended_actions`
- `meta_management_report_markdown`

Optional but useful:

- `meta_management_source_snapshot`

That source snapshot should store the compact raw inputs used to generate the report:

- campaign object
- ad set summary
- ad summary
- insights rows
- observed action types
- custom metric summary

This is enough for reproducibility without building a full warehouse.

## What The Agent Will Be Able To Say After This Revision

Once the phases above are done, the Meta-only agent should be able to say things like:

- "Campaign is delivering, but 3 ads are burning spend with sub-1% link CTR. Pause them."
- "Creative is getting clicks, but landing-page efficiency is weak. The main drop-off is between LPV and AddToCart."
- "Users are reaching checkout, but purchase completion is weak. Investigate checkout friction before adding spend."
- "The campaign is not actually failing on performance; it is blocked in review / `WITH_ISSUES`."

What it still will not be able to say with confidence:

- which exact headline, module, or section caused the drop-off
- whether a specific checkout field or payment method failed

That deeper level is what PostHog or first-party event instrumentation can improve later.

## Recommended Build Order

1. Add `InitiateCheckout` to the Meta event contract.
2. Add `meta_management_report_markdown`.
3. Add daily scheduled report generation.
4. Add Slack delivery.
5. Expand ad-level and funnel-level recommendation rules.

## Bottom Line

You were right to push back on the earlier plan.

For the first useful agent, Meta Events Manager data is enough to answer the operational funnel questions that matter most:

- is the traffic good?
- where is the stage-level drop-off?
- should we cut ads, hold, or scale?

The real work now is not adding PostHog first. It is tightening the Meta event contract and turning the existing management snapshot into a scheduled report with recommendations.
