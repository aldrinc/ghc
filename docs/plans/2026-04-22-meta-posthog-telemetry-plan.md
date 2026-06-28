# Meta + PostHog Telemetry Plan

Decision: build a first-class campaign telemetry layer in MOS that mirrors Meta performance data and first-party/PostHog event data into our database, keyed to campaign, publication, session, and page stage. Do not rely on Meta alone for path analysis. Meta should remain the paid-media source; first-party/PostHog should become the source of truth for on-site drop-off analysis.

## Why This Is Necessary

Today, MOS can answer some media questions, but it cannot fully answer the strategy question you asked:

- "Where is the user dropping off?"
- "Is the issue pre-sales to sales, sales to checkout, or checkout to purchase?"
- "Is the Meta signal consistent with first-party event behavior?"

For an `external_urls` campaign like Ember, the current system does not have enough first-party event detail inside MOS to support those decisions with confidence.

## Current State

| Source | What we have today | What is missing |
| --- | --- | --- |
| Meta Ads API | On-demand campaign/adset/ad status plus insights/action metrics in the management snapshot | No durable raw timeseries mirror of all action metrics by day/ad/adset/campaign |
| MOS funnel runtime | `funnel_events` and `funnel_orders` persist page views, clicks, checkout started, order completed for `internal_funnel` traffic | External campaigns do not feed this event store |
| Meta pixel / CAPI | Browser pixel events are emitted from public funnels and purchase CAPI events are sent server-side | We do not store a durable local log of what was emitted and acknowledged |
| PostHog | No first-class credential model or sync job in MOS today | No reliable way to pull event streams into MOS for analysis |

## Where The Information For This Campaign Lives Today

For Ember specifically, the campaign data is split:

- Meta campaign/ad/adset state and paid-media action counts live in Meta and are fetched through `/meta/management/plan`.
- MOS stores publish runs and management snapshot artifacts.
- If the campaign is `internal_funnel`, MOS also stores event data in `funnel_events` and `funnel_orders`.
- If the campaign is `external_urls`, the actual user journey after click is mostly outside MOS unless that destination is independently instrumented and mirrored back.

That means the current Ember path can tell us:

- whether ads are delivering
- how many landing page views / add to carts / purchases Meta reports
- broad paid-media health

It cannot reliably tell us:

- the exact pre-sales to sales drop-off path
- whether the user saw the sales page but failed before checkout
- whether checkout-started users abandoned at payment
- whether Meta event counts and first-party counts disagree

## Non-Negotiable Design Rule

Do not treat Meta as the exact event ledger.

Meta should provide:

- paid-media delivery state
- ad/adset/campaign insights
- aggregated action counts
- outbound conversion send status

MOS should provide:

- canonical session and visitor identity
- exact page-stage pathing
- checkout progression
- order completion truth
- cross-source reconciliation

## Architecture

We need four connected layers.

### 1. Credential Layer

Add a workspace-scoped PostHog integration model using encrypted secret storage, following the same pattern already used for Postiz and Meta credentials.

Store:

- `base_url`
- `project_id`
- `project_api_key` if needed for capture-side validation
- `personal_api_key` or equivalent query credential for read-side exports
- `capture_host`
- `project_key_label` or metadata for review
- validation status and last validation error

Important: do not store a generic ambiguous "apiKey". PostHog has different keys for capture and query access. Model them explicitly so the system does not guess.

### 2. Identity + Attribution Layer

Every event we mirror must be joinable to campaign context.

Canonical join keys:

- `org_id`
- `client_id`
- `campaign_id`
- `meta_campaign_id`
- `publication_id` or `site_publication_id`
- `session_id`
- `visitor_id`
- `occurred_at`
- `page_stage`
- `page_id` or canonical page key
- `source` (`mos_runtime`, `posthog`, `meta_insights`, `meta_capi`)

Attribution fields that must survive from click through purchase:

- `utm_source`
- `utm_medium`
- `utm_campaign`
- `utm_content`
- `utm_term`
- `fbclid`
- `meta_campaign_id`
- `meta_adset_id`
- `meta_ad_id`
- `landing_url`
- `referrer`

For `external_urls`, this is the critical gap. If those identifiers are not propagated into PostHog events and downstream checkout/order events, we will never have a trustworthy campaign-level event mirror.

### 3. Mirror Layer

Mirror raw events and raw metrics into MOS on a schedule.

#### 3A. Meta Mirror

Create durable tables for raw Meta performance data:

- `meta_insight_snapshots`
- `meta_insight_rows`
- `meta_action_breakdowns`

Persist:

- campaign/adset/ad ids
- date bucket
- impressions
- spend
- cpm
- frequency
- link clicks
- ctr
- cpc
- all `actions`
- all `action_values`
- video metrics
- the exact raw payload returned by Meta

This makes the management report reproducible and removes repeated expensive reads from Meta.

#### 3B. PostHog Mirror

Create durable tables for first-party mirrored telemetry:

- `campaign_event_sources`
- `posthog_sync_runs`
- `posthog_event_mirror`
- `posthog_person_mirror` if needed later

Persist at minimum:

- event name
- distinct id
- timestamp
- session id
- page URL / path
- referrer
- UTM and click ids
- campaign/publication metadata
- page stage
- event properties blob

We do not need every PostHog table shape exposed in MOS. We need a normalized event mirror optimized for campaign analysis.

#### 3C. Outbound Meta Conversion Log

Persist a local log whenever MOS emits Meta CAPI events:

- `meta_outbound_conversion_events`

Store:

- event name
- event id
- pixel id
- send timestamp
- request payload hash
- response summary
- error if any
- linked order / funnel / session ids

This lets us answer "did we send the conversion?" without depending on ad hoc logs.

### 4. Analytics Layer

Build materialized campaign analytics on top of the raw mirrors.

Core fact tables:

- `campaign_session_facts`
- `campaign_stage_transition_facts`
- `campaign_conversion_facts`
- `campaign_reconciliation_facts`

Derived metrics:

- pre-sales page sessions
- pre-sales to sales click sessions
- sales page sessions
- checkout-started sessions
- purchase sessions
- pre-sales CTR
- sales-to-checkout rate
- sales-page purchase CVR
- checkout CVR
- Meta LPV vs first-party landing sessions delta
- Meta ATC vs first-party checkout-started delta
- Meta purchases vs order-completed delta

This is the layer the strategy report should read from.

## What We Should Reuse Instead Of Rebuilding

Existing pieces already worth keeping:

- `funnel_events` and `funnel_orders` for `internal_funnel`
- current public runtime event taxonomy
- current Meta management snapshot contract
- encrypted secret helpers in `integration_secrets.py`
- management artifacts for caching and audit history

We should extend these, not replace them.

## Implementation Phases

### Phase 1. Credential + Config Foundation

Goal: make PostHog a first-class workspace integration.

Build:

- `ClientPosthogCredentials` model
- repository + API routes
- encrypted secret storage using `encrypt_secret_json`
- validation endpoint that fails cleanly on bad credentials
- workspace response payload showing configured host/project and masked secret state

Acceptance:

- strategy team can configure PostHog once per client/workspace
- MOS can validate read access to the target PostHog project

### Phase 2. Unified Event Taxonomy

Goal: make MOS and PostHog speak the same language.

Standardize canonical events:

- `funnel_entered`
- `pre_sales_page_view`
- `pre_sales_to_sales_click`
- `sales_page_view`
- `checkout_started`
- `order_completed`
- `purchase_failed` if available
- `upsell_accepted` / `upsell_declined` later if relevant

Standardize canonical properties:

- `campaign_id`
- `meta_campaign_id`
- `publication_id`
- `page_stage`
- `page_id`
- `session_id`
- `visitor_id`
- `utm_*`
- `fbclid`
- `meta_ad_id`
- `meta_adset_id`

Acceptance:

- a single event dictionary can be interpreted the same way whether it came from MOS runtime or PostHog mirror

### Phase 3. External Campaign Instrumentation Contract

Goal: make `external_urls` campaigns analyzable.

Require every external destination to emit the canonical event schema into PostHog.

That means:

- landing page records canonical page-view event
- pre-sales CTA records transition event
- sales page records page-view event
- checkout start records checkout event
- purchase completion records order event
- session and attribution ids are preserved through the flow

If the external destination cannot satisfy this contract, MOS should mark the campaign as `benchmark_unavailable.missing_first_party_event_contract` instead of pretending analysis is complete.

Acceptance:

- external traffic becomes explainable at stage level

### Phase 4. PostHog Sync Pipeline

Goal: mirror first-party event data into MOS efficiently.

Build:

- incremental sync job by time window
- idempotent upsert on event identity
- sync watermark per source
- retry and failure logging
- raw payload retention policy

Recommended pull cadence:

- every 15 minutes for active campaigns
- nightly backfill / repair job

Acceptance:

- MOS DB contains first-party event history without requiring live PostHog queries for every report

### Phase 5. Meta Raw Mirror

Goal: persist the full Meta action ledger we use for reporting.

Build:

- daily or intra-day pull of insights rows for active campaigns
- raw action breakdown persistence
- ad/adset/campaign rollup persistence
- sync watermark per ad account / campaign

Acceptance:

- management and Slack reports can read mostly from MOS DB
- Meta API pressure drops

### Phase 6. Reconciliation Layer

Goal: compare Meta and first-party truth directly.

Build daily reconciliations:

- Meta landing page views vs first-party landing sessions
- Meta add-to-cart vs first-party checkout-started
- Meta purchases vs first-party order-completed
- event gap percentages and diagnostics

Acceptance:

- report can explain whether a problem is media-side, landing-page-side, or tracking-side

### Phase 7. Strategy Report Layer

Goal: turn telemetry into a decision-ready report.

Report sections:

- delivery summary
- stage-by-stage funnel counts
- Meta vs first-party reconciliation
- largest drop-off stage
- metric deltas vs KPI
- top warnings
- top actions

Critical strategy outputs:

- "Main issue is pre-sales to sales drop-off"
- "Main issue is sales page to checkout-started drop-off"
- "Main issue is tracking disagreement, not funnel performance"

Acceptance:

- a strategy team member can open the report and immediately see the failing stage and evidence

## Data Model Additions

| Table | Purpose |
| --- | --- |
| `client_posthog_credentials` | encrypted workspace-scoped PostHog credentials |
| `posthog_sync_runs` | job audit trail and watermarks |
| `posthog_event_mirror` | raw mirrored PostHog events |
| `meta_insight_snapshots` | sync run header for Meta pulls |
| `meta_insight_rows` | durable ad/adset/campaign metrics rows |
| `meta_action_breakdowns` | raw `actions` and `action_values` persistence |
| `meta_outbound_conversion_events` | CAPI emission log |
| `campaign_session_facts` | sessionized campaign telemetry |
| `campaign_stage_transition_facts` | stage-level funnel movement facts |
| `campaign_reconciliation_facts` | Meta vs first-party comparison outputs |

## What Changes In The Meta Agent

Today the Meta agent mostly reads:

- on-demand Meta snapshot
- optional internal MOS funnel benchmark data

After this plan, the Meta agent should read:

- durable Meta insights mirror
- durable PostHog event mirror
- durable MOS funnel events
- reconciliation facts

This gives the agent enough evidence to say:

- the ads are fine but the landing page is weak
- the landing page is fine but checkout is collapsing
- Meta says LPV is high but first-party sessions are missing, so tracking is broken

## Main Risks

### Risk 1. Ambiguous PostHog credentials

Mitigation:

- separate capture-side and query-side credentials explicitly

### Risk 2. External sites do not carry campaign identifiers

Mitigation:

- make event contract validation a launch requirement

### Risk 3. Double-counting across MOS and PostHog

Mitigation:

- define a canonical event identity and source precedence

### Risk 4. Meta and first-party numbers never match exactly

Mitigation:

- design reconciliation thresholds and report deltas instead of demanding exact equality

## Suggested Delivery Order

1. PostHog credential model and validation
2. canonical event schema
3. external campaign event contract
4. PostHog mirror pipeline
5. Meta raw mirror tables
6. reconciliation layer
7. strategy report and Slack delivery

## Bottom Line

If we want MOS to tell us exactly where Ember is failing, we need MOS to own a campaign telemetry model, not just a reporting UI.

The system has to mirror:

- Meta paid-media metrics
- first-party/PostHog step events
- MOS checkout and order truth

Until those are unified in the database, the agent can describe campaign symptoms, but it cannot reliably explain the stage-level cause.
