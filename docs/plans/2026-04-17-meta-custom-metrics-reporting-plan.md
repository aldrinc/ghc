# Meta Custom Metrics Reporting Plan

## Decision

Implement the requested Meta-style custom metrics as a MOS-owned derived-metrics layer computed from raw Meta insights primitives and included in the post-publish management report.

Do not make the first version depend on Meta business-portfolio custom metric objects.

The system should:

- compute the metrics locally and deterministically
- label them clearly as Meta-derived estimated metrics
- show the exact formula, numerator, denominator, KPI target, and warnings
- include them in the management snapshot and markdown report
- preserve the current first-party funnel metrics as a separate plane of truth

This is the right boundary because the business-portfolio custom metrics shown in Ads Manager are operator-local artifacts, not a portable reporting contract for a fresh ad account.

## Requested Metrics

The screenshots define five custom metrics that the strategy team wants in the report.

### 1. ATC Ratio

- label: `ATC Ratio`
- formula: `Adds to cart / Website landing page views`
- KPI target: `>10%`
- source plane: Meta estimated metrics

### 2. Conversion Rate

- label: `Conversion Rate`
- formula: `Purchases / Website landing page views`
- KPI target: `1-3%`
- source plane: Meta estimated metrics

### 3. IC Ratio

- label: `IC Ratio`
- expanded label: `Initiate Checkout Ratio`
- formula: `Checkouts initiated / Website landing page views`
- KPI target: not shown in the screenshots, so this should be configurable rather than hard-coded in v1
- source plane: Meta estimated metrics

### 4. Purchase Ratio

- label: `Purchase Ratio`
- formula: `Purchases / Adds to cart`
- KPI target: `>30%`
- source plane: Meta estimated metrics

### 5. Video Hold Rate

- label: `Video Hold Rate`
- formula: `Video plays at 50% / Impressions`
- KPI target: `>25%`
- source plane: Meta estimated metrics

## Why We Should Not Depend On Meta Custom Metric Objects

Meta Ads Manager custom metrics are business-portfolio scoped and operator-managed. That creates three problems if MOS depends on them directly:

- they are not guaranteed to exist on a fresh account
- they are not guaranteed to have the same ids or availability across business portfolios
- they do not provide a stable engineering contract for automated reporting

The formulas above are simple enough that MOS should compute them itself from raw insights.

Optional later enhancement:

- if Meta exposes the relevant custom metric definitions or custom conversion definitions through a reliable API surface, MOS can import them for display or reconciliation
- that import should be additive, not the source of truth for report computation

## Core Product Decision

The report should show two clearly separated metric planes:

- `Meta Derived Metrics`
  - based on Meta insights
  - useful for reading the ad account the way a buyer reads Ads Manager
  - includes estimated metrics and modeled platform behavior
- `First-Party Funnel Metrics`
  - based on internal `FunnelEvent` data
  - useful for diagnosing actual site-side performance
  - should remain separate even when formulas look similar

Do not collapse these into one blended metric group.

Examples:

- the requested `Conversion Rate` is `Purchases / Website landing page views` from Meta-side estimated metrics
- the existing `salesPdpPurchaseCvrPct` is `Orders completed / Sales page sessions` from MOS funnel events

Those answer different questions and should both be visible.

## What Exists Today

Today MOS already computes some adjacent metrics in the post-publish management snapshot:

- `linkCtrPct`
- `linkCpc`
- `hookRatePct`
- `holdRatePct` based on `video_thruplay_watched_actions`
- `atcRatioPct` based on content view actions, not landing page views
- `purchaseRatioPct`
- `aov`

The current gaps relative to the requested custom metrics are:

- no landing-page-view based ratios
- no initiate-checkout ratio
- no explicit video-50%-watch metric surfaced as a named custom metric
- no per-metric formula / KPI / explanation metadata in the report
- no clean separation between Meta-derived custom metrics and first-party funnel metrics

## Implementation Strategy

### Phase 1: Introduce a custom metric registry

Add a dedicated registry for Meta-derived custom metrics instead of hard-coding more flat fields into `MetaAdMetrics`.

Recommended backend model:

- `MetaDerivedMetricDefinition`
  - `id`
  - `label`
  - `description`
  - `formula`
  - `unit`
  - `sourcePlane`
  - `defaultThreshold`
  - `displayOrder`
- `MetaDerivedMetricValue`
  - `metricId`
  - `value`
  - `numerator`
  - `denominator`
  - `status`
  - `warningCodes`
  - `sourceKeys`
  - `scope`

Recommended initial metric ids:

- `meta_atc_ratio_pct`
- `meta_conversion_rate_pct`
- `meta_ic_ratio_pct`
- `meta_purchase_ratio_pct`
- `meta_video_hold_rate_pct`

Why this matters:

- the current flat field model does not scale
- the report needs display metadata, not just numbers
- the strategy team needs formula-level explainability

### Phase 2: Add a primitive-count layer

Before computing the custom metrics, normalize the raw Meta insights row into reusable primitive counts.

Recommended primitives:

- `impressions`
- `landingPageViews`
- `addsToCart`
- `initiatedCheckouts`
- `purchases`
- `videoP50Plays`

These should come from:

- direct fields where Meta provides them
- otherwise `actions` / `action_values` maps
- otherwise `video_p50_watched_actions` for the 50% video play metric

Important:

- treat action resolution as a registry with alias lists, not a single hard-coded key
- record which action key actually resolved each primitive
- if a primitive cannot be resolved, surface that as a warning rather than silently substituting another metric

### Phase 3: Define action alias resolution rules

Some requested metrics depend on Meta action keys that can vary by account or optimization path.

The implementation should support candidate key lists per primitive.

Recommended approach:

- add a primitive-source registry like:
  - `landingPageViews`
  - `addsToCart`
  - `initiatedCheckouts`
  - `purchases`
- each primitive has:
  - `candidateActionTypes`
  - `fallbackFieldReaders`
  - `requiredForMetrics`

Initial candidate sources to validate against live campaigns:

- landing page views
  - expected to come from Meta landing-page-view action types in `actions`
- adds to cart
  - expected to include `offsite_conversion.fb_pixel_add_to_cart`
- initiated checkouts
  - expected to include Meta checkout-initiation action types in `actions`
- purchases
  - expected to include `offsite_conversion.fb_pixel_purchase`
- video 50% plays
  - from `video_p50_watched_actions`

Important implementation rule:

- do not hard-code uncertain alias lists as final truth without validating them against actual `observedActionTypes` and raw insights rows from published campaigns

### Phase 4: Compute the requested metrics locally

Once the primitive-count layer exists, compute the requested custom metrics in MOS.

Required formulas:

- `meta_atc_ratio_pct = addsToCart / landingPageViews * 100`
- `meta_conversion_rate_pct = purchases / landingPageViews * 100`
- `meta_ic_ratio_pct = initiatedCheckouts / landingPageViews * 100`
- `meta_purchase_ratio_pct = purchases / addsToCart * 100`
- `meta_video_hold_rate_pct = videoP50Plays / impressions * 100`

Do not replace the existing metrics.

Instead:

- keep current fields for backward compatibility
- add the custom metric set in parallel
- let the report display both

### Phase 5: Add metric definitions and thresholds to workspace config

The screenshots include KPI guidance. That should live in config, not in JSX.

Recommended storage:

- extend the Meta paid ads profile metadata with a `metaDerivedMetricBenchmarks` block
- store:
  - threshold type
  - threshold value
  - good value
  - display label
  - explanatory copy

Suggested defaults:

- `meta_atc_ratio_pct`
  - minimum / target: `10`
- `meta_conversion_rate_pct`
  - minimum: `1`
  - good: `3`
- `meta_purchase_ratio_pct`
  - minimum / target: `30`
- `meta_video_hold_rate_pct`
  - minimum / target: `25`
- `meta_ic_ratio_pct`
  - no hard-coded target until the team defines one explicitly

Important:

- `IC Ratio` should not get a fabricated KPI target in v1
- the report should say `Target not configured` rather than inventing one

### Phase 6: Extend the management snapshot contract

Add a dedicated custom-metrics block to the `MetaManagementPlan` payload.

Recommended shape:

- `customMetricDefinitions`
- `customMetricSummary`
- `customMetricRows`
- `customMetricEvaluations`

Where:

- `customMetricDefinitions`
  - one definition per metric id
- `customMetricSummary`
  - campaign-level aggregate values
- `customMetricRows`
  - per-ad values
- `customMetricEvaluations`
  - threshold status objects similar to existing `benchmarkEvaluations`

Do not overload `benchmarkEvaluations` with Meta-derived custom metrics.

Reason:

- benchmark evaluations currently represent first-party funnel benchmarks
- mixing the planes will make the report harder to read and reason about

### Phase 7: Add a dedicated report section

The markdown report should get a first-class `Meta Derived Custom Metrics` section.

Recommended layout:

- Summary table
  - Metric
  - Formula
  - Value
  - KPI
  - Status
  - Source note
- Per-metric drilldown
  - description
  - raw numerator / denominator
  - warning codes
  - interpretation
- Per-ad custom metric view
  - only for ads above a denominator threshold

Recommended report wording rules:

- always state whether the metric is `Meta estimated` or `MOS first-party`
- always show the exact numerator and denominator counts
- always show `Unavailable` if denominator or source keys are missing
- always show which action key resolved the primitive when applicable

### Phase 8: Add UI cards for strategy review

The Manage panel should show these as a separate strip of cards above or beside the first-party benchmark cards.

Recommended card content:

- display name
- current value
- KPI target
- short formula
- status badge
- tooltip / expandable details with numerator and denominator

Example:

- `ATC Ratio`
  - `12.4%`
  - `Target >10%`
  - `ATC / LPV`
  - `On target`

### Phase 9: Tie custom metrics into recommendations

Once the metrics exist, use them in report recommendations.

Recommended mapping:

- low `meta_atc_ratio_pct`
  - landing page mismatch or weak sales page
- low `meta_ic_ratio_pct`
  - weak offer resonance or CTA flow friction
- low `meta_purchase_ratio_pct`
  - checkout friction, price shock, or payment problem
- low `meta_conversion_rate_pct`
  - overall funnel efficiency problem
- low `meta_video_hold_rate_pct`
  - body of the creative is not maintaining attention after the hook

Important:

- the first version should keep these as recommendation text, not auto-actions
- do not auto-pause or auto-scale on these new metrics until the team has validated the thresholds

### Phase 10: Validate against live campaign data

Before rollout, run the metric engine against real published runs and compare MOS results to the Ads Manager custom metric values shown in the business portfolio.

Validation checklist:

- same campaign
- same date window
- same level of aggregation
- same attribution / event settings where relevant
- same numerator and denominator counts where inspectable

Acceptance rule:

- if MOS cannot match the Ads Manager custom metric closely enough, the discrepancy must be explained in the report as a source-modeling difference

## Data Model Recommendation

### Backend

Recommended files to touch:

- `mos/backend/app/services/meta_media_buying.py`
- new helper module, preferably `mos/backend/app/services/meta_derived_metrics.py`
- `mos/backend/app/routers/meta_ads.py`
- `mos/backend/app/services/paid_ads_qa.py`
- `mos/backend/app/db/enums.py`

Recommended new artifact types:

- `meta_management_custom_metrics_snapshot`
- `meta_management_report_markdown`

### Frontend

Recommended files to touch:

- `mos/frontend/src/types/meta.ts`
- `mos/frontend/src/components/campaigns/meta/MetaManagementPanel.tsx`
- possibly a new `MetaCustomMetricsPanel.tsx`

## Reporting Contract Recommendation

Each custom metric in the report should carry:

- `metricId`
- `label`
- `description`
- `formula`
- `sourcePlane`
- `sourceClass`
- `value`
- `unit`
- `numerator`
- `denominator`
- `kpiMinimum`
- `kpiGood`
- `status`
- `resolvedSources`
- `warnings`

`sourceClass` should explicitly distinguish:

- `meta_estimated`
- `meta_direct`
- `mos_first_party`

The five requested metrics should all be labeled `meta_estimated` unless validated otherwise.

## Failure And Warning Rules

The custom metric section should fail clearly when:

- landing page views cannot be resolved from Meta insights
- initiated checkout cannot be resolved
- purchases cannot be resolved
- the selected window has zero denominator volume

Recommended warning codes:

- `missing_source.landing_page_views`
- `missing_source.initiated_checkouts`
- `missing_source.purchases`
- `missing_source.adds_to_cart`
- `missing_source.video_p50`
- `zero_denominator`
- `unvalidated_alias_resolution`
- `estimated_metric_source`

## Rollout Plan

### Step 1

Build the primitive-count layer and metric registry.

### Step 2

Compute and persist the five requested custom metrics in the management snapshot.

### Step 3

Render them in the markdown report with formulas, KPI targets, and numerator / denominator counts.

### Step 4

Render them in the Manage UI as a separate card group.

### Step 5

Add strategy-facing recommendation text driven by these metrics.

### Step 6

Validate against live campaigns and tighten alias resolution rules.

## Acceptance Criteria

The feature is ready when:

- the report includes all five requested custom metrics
- each metric shows formula, raw numerator, raw denominator, value, and KPI
- the report clearly distinguishes Meta-derived custom metrics from first-party funnel metrics
- unresolved source keys produce explicit warnings instead of silent substitution
- the strategy team can read the report and understand which layer is failing:
  - creative attention
  - landing page efficiency
  - checkout initiation
  - purchase completion
- MOS does not depend on pre-created Meta business-portfolio custom metrics to produce the report

## Recommended Next File To Update

This plan should be implemented alongside the broader management-plan doc:

- `docs/plans/2026-04-17-meta-post-publish-management-plan.md`

That file describes the current post-publish management contract.
This file defines how to extend that contract with the requested Meta-style custom metrics.
