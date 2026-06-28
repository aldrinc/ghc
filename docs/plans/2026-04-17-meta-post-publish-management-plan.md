# Meta Post-Publish Management Plan

## Decision

Treat the current post-publish Meta agent as an on-demand management snapshot plus deterministic recommendations, not as a scheduled autonomous media buyer.

For the near term, the right path is:

- keep the live publish flow as-is
- document the exact snapshot contract and recommendation rules
- add a first-class post-publish report artifact for operator review
- then add scheduled monitoring and richer recommendation types on top of that stable contract

Do not describe the current system as continuously monitoring in the background. Today it evaluates on demand from the Manage phase.

## What Happens After Publish Today

### 1. Publish creates a tracked Meta launch

When a campaign is published from MOS:

- a `MetaPublishRun` is created for the campaign
- the created Meta campaign id is persisted back onto that run
- the campaign, ad sets, creatives, and ads are created in Meta as `PAUSED`
- per-asset publish run items are stored so MOS can trace which asset became which Meta object

Live code:

- `mos/backend/app/routers/meta_ads.py`
- publish run creation starts in `create_meta_publish_run`
- campaign/ad set/ad creation happens with `status="PAUSED"`

### 2. The Manage phase becomes available only for tracked published runs

The frontend Manage phase only works when a saved publish run has a `metaCampaignId`.

That means:

- the user picks a previously published run
- MOS uses that run's `metaCampaignId`
- MOS requests a management plan from the backend

This is an on-demand evaluation, not a background polling loop.

Live code:

- `mos/frontend/src/components/campaigns/meta/MetaManagementPanel.tsx`
- the panel calls `planManagement(...)` with `mode: "plan_only"` and `evaluateBenchmarks: true`

### 3. MOS builds a fresh management snapshot

The backend `POST /meta/management/plan` call does the following:

- resolves the workspace Meta config
- fetches the current remote Meta campaign object
- fetches remote Meta ad set objects for that campaign
- fetches ad-level Meta insights for the selected date window
- computes derived ad metrics
- evaluates deterministic ad-level cut rules
- optionally evaluates first-party funnel benchmarks when the published campaign is locally tracked and tied to an internal funnel
- persists artifacts for the generated snapshot and recommendations

Live code:

- `mos/backend/app/routers/meta_ads.py`
- `mos/backend/app/services/meta_media_buying.py`
- `mos/backend/app/services/meta_management_benchmarks.py`

## Exact Snapshot Contract Today

The current snapshot is the `MetaManagementPlan` payload.

### Top-level fields

The response currently contains:

- `mode`
- `generatedAt`
- `window`
- `campaign`
- `adsets`
- `observedActionTypes`
- `rows`
- `actions`
- `appliedActions`
- `warnings`
- `benchmarkContext`
- `funnelSnapshot`
- `benchmarkEvaluations`
- `artifacts`

Source:

- `mos/frontend/src/types/meta.ts`
- `mos/backend/app/services/meta_media_buying.py`

### `window`

Today the selectable windows are:

- `today`
- `yesterday`
- `last_3d`
- `last_7d`

The current UI defaults to `last_3d`.

### `campaign`

This is the live remote Meta campaign snapshot, not a MOS-only summary. Current fetched fields are:

- `id`
- `name`
- `objective`
- `status`
- `effective_status`
- `daily_budget`
- `lifetime_budget`
- `buying_type`
- `special_ad_categories`
- `is_adset_budget_sharing_enabled`

### `adsets`

This is the live remote Meta ad set snapshot list. Current fetched fields are:

- `id`
- `name`
- `daily_budget`
- `lifetime_budget`
- `optimization_goal`
- `billing_event`
- `status`
- `effective_status`
- `promoted_object`
- `start_time`
- `end_time`

### `observedActionTypes`

This is a compact data-quality map showing which Meta action types appeared in the fetched insights rows:

- `actions`
- `action_values`

This matters because ATC ratio, purchase ratio, and AOV depend on the action keys Meta returned for that window.

### `rows`

Each ad row is the computed `MetaAdMetrics` object. Current fields are:

- `adId`
- `adName`
- `adsetId`
- `campaignId`
- `impressions`
- `spend`
- `cpm`
- `frequency`
- `inlineLinkClicks`
- `linkCtrPct`
- `linkCpc`
- `hookRatePct`
- `holdRatePct`
- `atcRatioPct`
- `purchaseRatioPct`
- `aov`
- `raw`
- `warnings`

Notes:

- `raw` is only populated when `includeRaw=true`
- `warnings` records metric-reconstruction or mapping issues such as computed CTR/CPC fallbacks or incomplete event mappings

### How row metrics are computed

Current formulas:

- `linkCtrPct = inline_link_clicks / impressions * 100` when Meta does not return the derived field
- `linkCpc = spend / inline_link_clicks` when Meta does not return the derived field
- `hookRatePct = video_play_actions / impressions * 100`
- `holdRatePct = video_thruplay_watched_actions / impressions * 100`
- `atcRatioPct = add_to_cart_actions / content_view_actions * 100`
- `purchaseRatioPct = purchase_actions / add_to_cart_actions * 100`
- `aov = purchase_value / purchase_count`

Current default event mappings:

- content view: `offsite_conversion.fb_pixel_view_content`
- add to cart: `offsite_conversion.fb_pixel_add_to_cart`
- purchase count: `offsite_conversion.fb_pixel_purchase`
- purchase value: `offsite_conversion.fb_pixel_purchase`

### `actions`

This is the first-class recommendation list produced by the current rules engine.

Each item currently contains:

- `kind`
- `metaAdId`
- `reason`
- `triggeredRules`
- `metrics`

Today the only emitted action kind is:

- `pause_ad`

### `appliedActions`

This is only populated when the backend is called with `mode="apply"`.

Each item contains:

- `kind`
- `metaEntityId`
- `status`
- `requestPayload`
- `before`
- `after`
- `error`

Important:

- the current UI does not call apply mode
- the current UI calls `plan_only`
- so in normal operator usage today, `appliedActions` is empty

### `benchmarkContext`

This is the context block used for first-party funnel benchmark interpretation. Current fields are:

- `clientId`
- `campaignId`
- `metaCampaignId`
- `datePreset`
- `funnelId`
- `publicationId`
- `deliveryMode`
- `profileId`
- `priceCents`
- `priceDollars`
- `atcPriceBandId`
- `atcPriceBandLabel`
- `priceResolutionError`
- `profileUpdatedAt`

### `funnelSnapshot`

This is the first-party funnel performance snapshot built from `FunnelEvent` data for the selected window.

Current fields are:

- `startedAt`
- `endedAt`
- `presellPageId`
- `salesPageId`
- `presellPageViewSessions`
- `presellCtaClickSessions`
- `salesPageViewSessions`
- `checkoutStartedSessions`
- `orderCompletedSessions`
- `presellCtrPct`
- `salesPdpAtcPct`
- `salesPdpPurchaseCvrPct`
- `checkoutCvrPct`

Current formulas:

- `presellCtrPct = presellCtaClickSessions / presellPageViewSessions * 100`
- `salesPdpAtcPct = checkoutStartedSessions / salesPageViewSessions * 100`
- `salesPdpPurchaseCvrPct = orderCompletedSessions / salesPageViewSessions * 100`
- `checkoutCvrPct = orderCompletedSessions / checkoutStartedSessions * 100`

### `benchmarkEvaluations`

This is the benchmark-status list used by the Manage UI cards.

Each evaluation currently contains:

- `metricId`
- `label`
- `scope`
- `status`
- `value`
- `unit`
- `minimum`
- `target`
- `good`
- `numerator`
- `denominator`
- `reason`
- `context`

Current statuses:

- `below_target`
- `on_target`
- `good`
- `insufficient_data`
- `unavailable`
- `not_applicable`

Current benchmarked metrics:

- `ad_link_ctr_pct`
- `presell_ctr_pct`
- `sales_pdp_purchase_cvr_pct`
- `checkout_cvr_pct`
- `sales_pdp_atc_pct`

### `artifacts`

Every management-plan run for a locally tracked campaign persists artifacts and returns their ids:

- `metricsSnapshotArtifactId`
- `recommendedActionsArtifactId`
- `approvalDecisionArtifactId` only in apply mode

Persisted artifact types:

- `meta_management_metrics_snapshot`
- `meta_management_recommended_actions`
- `meta_management_approval_decision`
- `meta_management_applied_action`

## Exact Recommendation Behavior Today

### First-class rule engine

The current rule engine evaluates ad rows only.

Current thresholds:

- minimum spend gate: `spend > 30`
- kill on `linkCpc > 3.00`
- kill on `linkCtrPct < 1.0`
- kill on `cpm > 50.0`

If one or more of those conditions hit, MOS emits:

- `kind: pause_ad`
- `metaAdId: <ad id>`
- `reason: <human-readable explanation>`
- `triggeredRules: [...]`
- `metrics: { spend, cpm, linkCtrPct, linkCpc }`

Important limitations:

- there is no scale recommendation emitted today
- there is no budget-increase recommendation emitted today
- there is no creative-fatigue recommendation emitted today
- there is no funnel-fix recommendation emitted as a first-class action today

### Benchmark-driven operator guidance in the UI

The Manage UI adds human-readable operator guidance when a benchmark evaluation is `below_target`.

Current UI-only recommendation texts:

- `ad_link_ctr_pct`
  - "Creative clickthrough is below benchmark. Refresh the hook, first frame, and headline before scaling spend."
- `presell_ctr_pct`
  - "The pre-sell page is not moving enough visitors forward. Rework the headline, CTA placement, and bridge into the offer."
- `sales_pdp_atc_pct`
  - "The sales page is weak for its price band. Tighten offer clarity, proof, and CTA density above the fold."
- `sales_pdp_purchase_cvr_pct`
  - "Sales-page conversion is below benchmark. Audit message-match, proof quality, and objection handling."
- `checkout_cvr_pct`
  - "Checkout completion is below target. Inspect checkout friction, payment errors, and trust elements."

Important limitation:

- these benchmark recommendations are not persisted today as first-class action objects
- they are rendered by the frontend from `benchmarkEvaluations`

## What The Operator Can Actually Analyze Today

Today the operator can analyze:

- which ads are over the pause thresholds
- which benchmark cards are below target
- the current ad-level spend / CTR / CPC / CPM for the selected window
- the current first-party funnel conversion performance for internal funnels
- whether the price-band benchmark could be resolved
- whether event-mapping warnings or missing denominator warnings make the snapshot less trustworthy

Today the operator cannot yet analyze from a single dedicated post-publish report:

- period-over-period deltas
- trend lines
- ranked recommendation priority
- confidence per recommendation
- action ownership
- expected impact
- "what changed since the last snapshot"
- scaling candidates as a first-class list
- a 2-week retro artifact

## Current Constraints And Failure Modes

The current Manage phase will fail or partially degrade in these cases:

- the publish run does not have a `metaCampaignId`
- the Meta campaign is not locally tracked in MOS
- benchmark evaluation is requested but the campaign is not tied to an internal funnel delivery config
- the benchmark path cannot resolve a single funnel for the published campaign
- the funnel is not published
- the funnel has no sales page
- the funnel price point is missing or ambiguous for price-band ATC benchmarking
- the selected window has insufficient denominator volume

These failure cases are mostly correct and should stay explicit. They match the repo rule to fail clearly instead of inventing fallback behavior.

## Recommended Detailed Plan

### Phase 1: Formalize the post-publish contract

Add a dedicated contract doc and keep it synced with code.

Deliverables:

- document the exact `MetaManagementPlan` response
- document the persisted management artifact shapes
- document the exact rule thresholds and benchmark metric ids
- document which recommendations are backend-native vs UI-derived

Why:

- this gives product, engineering, and operators one source of truth
- it prevents the broader design doc from being confused with current behavior

### Phase 2: Add a first-class post-publish markdown report artifact

Add a markdown renderer for management snapshots, parallel to the existing QA markdown report.

Recommended report sections:

- Summary
  - generated time
  - selected publish run
  - selected date preset
  - campaign / funnel / price-band context
- Ad snapshot
  - one row per ad with spend, CTR, CPC, CPM, hook rate, hold rate, ATC ratio, purchase ratio, AOV
- Rule-triggered actions
  - exact ad ids
  - exact triggered rules
  - exact threshold comparisons
- Funnel benchmark review
  - each benchmark metric
  - actual value
  - benchmark target/minimum/good
  - status
- Operator recommendations
  - creative changes
  - pre-sell changes
  - sales page changes
  - checkout changes
- Data-quality warnings
  - missing event mappings
  - insufficient denominator volume
  - price-band resolution issues
- Next review actions
  - what should be checked next
  - what data is missing before stronger decisions can be made

Required artifact additions:

- `meta_management_report_markdown`
- optional saved file path similar to paid ads QA reports

### Phase 3: Promote benchmark recommendations into first-class actions

Keep the current ad pause rules, but add a second action family for operator guidance.

Recommended action kinds:

- `pause_ad`
- `hold_for_more_data`
- `refresh_creative`
- `fix_presell`
- `fix_sales_page`
- `fix_checkout`
- `candidate_for_scale`
- `cannot_evaluate`

Each action should contain:

- `kind`
- `scope`
- `priority`
- `reason`
- `source`
- `triggeredRules`
- `metrics`
- `recommendedOwner`
- `requiresHumanApproval`

Why:

- recommendations stop being trapped inside the UI
- reports and future automation can use the same action contract

### Phase 4: Add ranking and prioritization

Not all recommendations should be presented with equal weight.

Recommended priority model:

- `P1`
  - hard pause conditions
  - data integrity failures that invalidate spend decisions
- `P2`
  - below-target checkout or sales-page conversion issues with enough denominator volume
- `P3`
  - pre-sell and creative refresh recommendations
- `P4`
  - informational notes, not action drivers

Add ranking inputs:

- spend impacted
- denominator volume
- number of triggered rules
- whether the issue blocks scale

### Phase 5: Add trend-aware snapshots

The current snapshot is point-in-time for one date preset. Add comparison against the prior snapshot for the same publish run.

Recommended deltas:

- CTR delta
- CPC delta
- CPM delta
- hook-rate delta
- hold-rate delta
- pre-sell CTR delta
- sales PDP ATC delta
- sales PDP purchase CVR delta
- checkout CVR delta

Why:

- the operator needs to know whether the system is improving or decaying
- fatigue and offer deterioration are trend questions, not single-window questions

### Phase 6: Add scheduled monitoring

After the report contract is stable, add a scheduled workflow.

Recommended behavior:

- schedule snapshot generation per published Meta campaign
- store every snapshot as artifacts
- emit inbox items only when:
  - a new `pause_ad` recommendation appears
  - a benchmark drops below target after previously being on target
  - data quality regresses
  - a scale candidate appears

Important:

- do not silently auto-apply scaling actions
- if auto-pause is ever allowed, it must be an explicit opt-in per workspace

### Phase 7: Expand recommendation logic

After the report and scheduling layers exist, add new deterministic rules.

Recommended additions:

- scaling candidates when ad CTR is healthy and downstream conversion benchmarks are healthy
- fatigue warnings using repeated snapshots and frequency trend
- landing-page mismatch warnings using high CTR with low ATC
- checkout friction warnings using healthy sales-page volume and weak checkout CVR
- "insufficient data" recommendations when denominator volume is too low for a decision

### Phase 8: Add a two-week retro

This is not live today, but it belongs after the snapshot/report system is stable.

Recommended retro checks:

- best and worst ads by spend-adjusted efficiency
- benchmark pass/fail history by day
- number of pause decisions taken
- creative concepts that repeatedly underperform
- funnels with recurring presell / sales / checkout bottlenecks
- unresolved warnings that made decisions weaker

## Proposed Delivery Order

1. Document the current contract and recommendation behavior.
2. Add markdown rendering for post-publish management snapshots.
3. Persist benchmark recommendations as first-class actions.
4. Add recommendation priority and delta reporting.
5. Add scheduled snapshot generation.
6. Add richer recommendation families and the two-week retro.

## Acceptance Criteria

The post-publish system is reviewable when:

- an operator can open one markdown report and see the exact snapshot inputs, computed metrics, benchmark statuses, and recommendations
- every recommendation is traceable to explicit thresholds or benchmark rules
- the system distinguishes backend-native actions from UI-only commentary
- the report clearly states when the snapshot is incomplete or insufficient for a decision
- repeated snapshots can be compared over time

## File And Code Areas To Touch

Primary backend areas:

- `mos/backend/app/services/meta_media_buying.py`
- `mos/backend/app/services/meta_management_benchmarks.py`
- `mos/backend/app/routers/meta_ads.py`
- `mos/backend/app/db/enums.py`

Primary frontend areas:

- `mos/frontend/src/components/campaigns/meta/MetaManagementPanel.tsx`
- `mos/frontend/src/types/meta.ts`

Reference doc that should remain clearly marked as broader design, not current state:

- `docs/meta-media-buying-agent.md`
