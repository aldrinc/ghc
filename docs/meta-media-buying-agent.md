# Meta Media Buying Agent (Design)

This document describes how to implement an end-to-end Meta (Facebook/Instagram) media buying agent in MOS that:

- builds campaigns using Structure B (“Creative Test”, Post-Andromeda)
- monitors performance against a fixed metrics dashboard
- applies (or recommends) cut/scale/troubleshooting actions deterministically
- produces post-launch review artifacts

It is intentionally strict: it should fail fast with clear errors when required inputs are missing, rather than guessing or falling back.

## Goals

- Deterministically configure Meta campaigns/ad sets/ads that match the requested structure.
- Persist what MOS created in Meta (so actions are auditable, deduped, and reversible).
- Continuously fetch performance data and compute the exact metrics the operator expects to see.
- Apply cut/scale rules consistently, with human approval gates where appropriate.
- Feed learnings back into the creative pipeline (concept diversity and cadence).

## Non-Goals

- “Magic” optimization via LLM. Budgeting, targeting, thresholds, and actions should be rule-based and explainable.
- Guessing missing business inputs (Tier 1 list, margin/COGS, pixel config, etc.). Missing inputs should error.

## Existing Building Blocks In This Repo

- Meta Graph client + create primitives: `mos/backend/app/services/meta_ads.py`
- Meta create/upload/spec routes: `mos/backend/app/routers/meta_ads.py`
- Persistence: `mos/backend/app/db/models.py` (`MetaAssetUpload`, `MetaAdCreative`, `MetaCampaign`, `MetaAdSet`, `MetaAd`, `MetaCreativeSpec`, `MetaAdSetSpec`)
- Temporal workflow framework + artifacts: `mos/backend/app/temporal/`, `mos/backend/app/db/models.py` (`Artifact`)

The missing pieces are the “compiler” (Structure B -> concrete Meta objects) and the “manager” (insights -> decisions -> actions).

## Inputs (Source Of Truth)

Minimum required to launch and manage:

- Meta config: `META_ACCESS_TOKEN`, `META_GRAPH_API_VERSION`, `META_AD_ACCOUNT_ID`, `META_PAGE_ID` (and `META_INSTAGRAM_ACTOR_ID` if used).
- Conversion config: pixel id + conversion domain + the canonical “Purchase” optimization event definition.
- A MOS `Campaign` (for naming + grouping) and a set of `Asset`s (images/videos) to run.
- For profit-based decisions: explicit margin/COGS/fees configuration (if absent, profit rules must be disabled or the run must error).

## High-Level Architecture

The agent is a loop:

1. **Plan**: build a `LaunchPlan` (a fully specified, validated object graph).
2. **Compile**: convert the plan into Meta API requests (campaign/ad sets/creatives/ads).
3. **Execute**: push requests to Meta in order, idempotently.
4. **Observe**: fetch insights snapshots on a schedule and compute derived metrics.
5. **Decide**: evaluate cut/scale/troubleshoot rules against defined time windows.
6. **Act**: apply actions (or emit approval-required recommendations).
7. **Review**: generate 2-week retro + experiment log outputs.

Temporal is the natural orchestrator for steps 3-7.

## LaunchPlan (What The Compiler Consumes)

Represent the launch plan as a single validated JSON document (persist it as an `Artifact`) with:

- naming fields: `date`, `productName`, `structure` (`CBO`), `audienceLabel` (`Broad`/`Int`)
- campaign: objective must be “Sales”, optimization event must be “Purchase”
- budget policy: CBO budgets and constraints
- ad sets: each with targeting, placement policy, budget, and a list of ads
- ads: each with an `assetId` + a creative spec (copy, CTA, destination URL, optional existing post id)

The key requirement: after validation, the plan must be runnable without additional inference.

## Structure Templates (Compiler Rules)

Structure A is deprecated for MOS going forward and should be treated as unsupported by the agent (error if requested).

### Structure B: “Creative Test” (Post-Andromeda, CBO)

- Budget mode: CBO
- Targeting: Broad US (18-65+, all genders)
- Structure: 3-5 ad sets, where each ad set is a concept (not minor variations)
- Ads: 3 creatives per ad set (variations of that concept)
- Budget logic:
  - minimum `$10/day` per ad in the campaign
  - never run less than `$50/day` total

Compiler output:

- One Meta campaign with campaign-level daily budget set to `max($50/day, $10/day * num_ads)` (converted to the account’s minor currency unit, e.g. cents).
- Meta Graph API requirements (v24.0): `special_ad_categories` is required (pass `[]` if none).
- Meta Graph API requirements (v24.0): for CBO, you must set `daily_budget` or `lifetime_budget` on the campaign.
- Meta Graph API requirements (v24.0): if you are not using a campaign budget (ABO), Meta requires `is_adset_budget_sharing_enabled` to be set.
- 3-5 broad ad sets with no individual budgets (ad set budget omitted).
- 3 ads per ad set.

### Naming

Campaign name template:

`[Date] - [Product] - [CBO] - [Broad|Int]`

Ad set naming must encode concept + audience segment (so reporting and automated actions remain explainable).

## Metrics (What The Manager Computes)

The manager should compute the dashboard columns directly from Meta insights fields and/or derived ratios.

Required computed metrics:

- CPM
- Hook Rate: `3s plays / impressions` (video-only; otherwise N/A)
- Hold Rate: `ThruPlay / impressions` (or `50% watch / impressions`) (video-only; otherwise N/A)
- Link CTR
- Link CPC
- ATC Ratio: `ATCs / Content Views`
- Purchase Ratio: `Purchases / ATCs`
- AOV: `Purchase value / Purchases`

Additionally recommended for scale/risk:

- Frequency
- Spend
- Purchase value (revenue proxy)
- ROAS (if available)
- Profit (only if margin inputs exist)

Time windows must match the operating rules:

- 24h, 24-48h, 24-72h (creative diagnostics)
- 48-72h (cut rules)
- 72h (ATC + purchase ratio)
- 7d (AOV)
- 3-5d and post-relaunch windows for product-level kill decisions

## Cut Rules (Deterministic Evaluations)

At the ad level, after `48-72h` AND `spend > $30`:

- kill if `CPC > 3.00`
- kill if `CTR < 1%`
- kill if `CPM > 50`

These should emit a `pause_ad` action with an explanation linking the exact metric values and the rule that triggered.

## Validated Meta Insights Mappings (Graph API v24.0)

Validated against the local Meta integration (`META_GRAPH_API_VERSION=v24.0`) by calling:

- `GET /act_{ad_account_id}/insights?level=ad&fields=...`

Key reality checks:

- Metrics are returned as strings (e.g. `"impressions": "209"`, `"cpm": "68.99"`).
- Many “count” fields (video metrics, actions) come back as arrays of `{action_type, value}` objects.
- `video_3_sec_watched_actions` is not a valid insights field in v24.0 for this integration. Use `video_play_actions` as the 3-second-play numerator.

Dashboard mappings:

- CPM:
  - field: `cpm`
- Hook Rate (3s plays / impressions):
  - numerator: sum of `value` in `video_play_actions` (typically `action_type=video_view`)
  - denominator: `impressions`
- Hold Rate (ThruPlay / impressions):
  - numerator: sum of `value` in `video_thruplay_watched_actions` (typically `action_type=video_view`)
  - denominator: `impressions`
  - optional alternative: `video_p50_watched_actions`
- Link CTR:
  - field: `inline_link_click_ctr` (percentage)
  - supporting fields: `inline_link_clicks`, `impressions`
- Link CPC:
  - field: `cost_per_inline_link_click` (currency)
  - supporting fields: `spend`, `inline_link_clicks`
- Spend:
  - field: `spend` (currency)
- Frequency:
  - field: `frequency`
- ATC Ratio / Purchase Ratio / AOV:
  - fields: `actions` and `action_values`
  - default mapping used by MOS:
    - Content Views: `offsite_conversion.fb_pixel_view_content`
    - Add To Carts: `offsite_conversion.fb_pixel_add_to_cart`
    - Purchases (count): `offsite_conversion.fb_pixel_purchase`
    - Purchases (value): `offsite_conversion.fb_pixel_purchase`
  - override: these keys can be overridden per plan request when needed.
  - do not sum multiple “purchase-like” action types by default because Meta can report multiple overlapping purchase keys in the same insights row (double-count risk).

## Scale Rules (Deterministic Evaluations)

Scale decisions should be gated on profitability (definition must be explicit in config):

- Vertical scaling (CBO): increase campaign daily budget in controlled steps (for example +20% to +50% per change) while monitoring frequency and efficiency.
- Horizontal scaling: move winning creatives into a dedicated scaling campaign (CBO or Advantage+), and test into additional audiences.

When duplicating, preserve social proof by reusing an existing post id (requires storing the post id on the creative/ad metadata).

## Troubleshooting (Diagnostic Tags)

Emit diagnostic tags to accelerate human iteration, for example:

- high_cpm: audience too small or creative quality/compliance issue
- low_ctr: hook not working
- clicks_lpv_discrepancy: site speed / tracking mismatch
- low_atc_ratio: curiosity click, landing page mismatch
- low_purchase_ratio: checkout friction / price shock / payment processor issue
- low_aov: missing order bump / quantity breaks / post-purchase OTO
- creative_fatigue: frequency rising + performance decaying

Diagnostics should never auto-change funnel/checkout; they should produce recommendations and link to the metric triggers.

## Approval + Safety Model

Default: the agent produces **recommendations** (actions) and requires explicit approval to apply:

- pausing entities
- scaling budgets
- launching new scaling campaigns

If an “auto-apply” mode is desired later, it must be explicit and scoped (for example: “auto-pause ads that meet kill rules” only).

Every action must be persisted with:

- what was changed (entity id, old value, new value)
- why (rule id, metrics snapshot id, window)
- when (timestamp)

## Dry Run Mode (Plan-Only)

The media buying agent must support a plan-only mode that makes **no Meta mutations**:

- Fetches Meta objects (campaign/ad sets/ads) + insights.
- Computes dashboard metrics.
- Evaluates cut/scale rules.
- Outputs a structured “Action Plan” describing exactly what would be changed and why.

The same decision code path must be used in both modes:

- `mode=plan_only`: return the action plan only.
- `mode=apply`: execute approved actions (pause ads, adjust budgets, duplicate, etc).

If `mode=apply` is requested before action execution is implemented, the system should error clearly rather than silently doing nothing.

## Outputs (Dashboards + Retro)

The agent should persist:

- a per-snapshot “metrics dashboard” artifact (ad/ad set/campaign rows with computed columns)
- an “actions” artifact (recommended/applied)
- a 2-week retro artifact that checks:
  - `CTR > 3%`
  - `Hook Rate > 50%` (video-only)
  - `Funnel CVR > 3%` (requires explicit CVR definition/source)
  - `AOV > 2x front-end price`
  - abandoned cart email/SMS configured (binary check)

## Implementation Plan (Concrete)

1. Add Meta insights support:
   - extend `MetaAdsClient` to call `/{act_id}/insights`
   - add a strict parser that normalizes fields into typed metrics
2. Fix Meta launch primitives to support Structure B correctly:
   - campaign create must include `special_ad_categories` and campaign-level budget (`daily_budget` or `lifetime_budget`)
   - ad set create must allow omitting ad set budgets under CBO
3. Add update endpoints:
   - `POST /{campaign_id}`, `POST /{adset_id}`, `POST /{ad_id}` for status/budget changes
4. Add a compiler:
   - `StructureBCompiler` only
5. Add a manager workflow (Temporal):
   - scheduled snapshots -> rule evaluation -> action proposals -> optional apply
6. Wire to UI:
   - expose “latest dashboard snapshot” + “pending actions” for review/approval
