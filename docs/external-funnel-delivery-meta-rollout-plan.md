# External Funnel Delivery and Meta Rollout Plan

## Objective

Add a first-class campaign mode that lets operators:

1. Run the existing foundational docs and Strategy V2 process.
2. Attach pre-sales and sales destinations to a campaign as external URLs.
3. Continue through creative production without requiring MOS-hosted funnel pages.
4. Prepare, launch, and later manage Meta campaigns against those external destinations.

The design should preserve the current internal funnel path while adding an external delivery path that is explicit, validated, and auditable.

## Desired Operator Workflow

Target operator flow:

1. Create or open a campaign.
2. Run foundational docs / Strategy V2 to completion.
3. Complete the required Strategy V2 decision gates and artifact approvals:
   - foundational research proceed gate
   - competitor asset confirmation
   - angle selection
   - UMP/UMS pair selection
   - offer winner selection
   - final copy approval
4. Persist the campaign launch context and pinned downstream packet:
   - selected angle
   - angle docs and ranked candidates
   - approved UMP/UMS pair
   - approved offer
   - approved copy
   - copy context
   - awareness-angle matrix
   - template payloads
5. Choose a delivery mode for the campaign:
   - `internal_funnel`
   - `external_urls`
6. If `internal_funnel`:
   - Generate pre-sales and sales pages in MOS.
   - Optionally publish/deploy them.
7. If `external_urls`:
   - Save canonical pre-sales URL.
   - Save canonical sales URL.
   - Optionally save checkout URL and thank-you URL.
   - Validate the URLs before downstream work begins.
8. Generate asset briefs and run creative production.
9. Prepare Meta review payloads and validate landing pages.
10. Launch Meta assets, creatives, ad sets, campaigns, and ads.
11. Run deterministic management and decision workflows for cut, scale, and review.

## Guiding Principles

- Keep foundational docs unchanged as the source of truth for strategy, offer, copy, and campaign context.
- Treat delivery configuration as a campaign concern, not as a side effect of funnel generation.
- Do not add silent fallbacks. Missing or invalid destination configuration should fail with clear errors.
- Keep internal funnels and external URLs as supported parallel modes rather than trying to fake one as the other.
- Reuse the current creative, QA, and Meta prep pipeline wherever possible.

## Required Upstream Strategy V2 Contract

The external-delivery plan depends on more than a generic "Strategy V2 completed" status.
Downstream creative generation and Meta preparation require specific artifacts, decisions, and lineage from the Strategy V2 flow.

### A. Foundational context bundles that ads generation still needs

The campaign creative path should continue to bundle and expose the higher-level strategy docs that already feed stage-one copy and asset generation:

- `strategy_v2_stage0`
- `strategy_v2_stage1`
- `strategy_v2_stage2`
- `strategy_v2_stage3`
- `strategy_v2_awareness_angle_matrix`
- `strategy_v2_offer`
- `strategy_v2_copy_context`
- `strategy_v2_copy`
- campaign `strategy_sheet`
- campaign `experiment_specs`
- campaign `asset_briefs`

These are already part of the creative-generation context design and should remain part of the plan.

### B. Required operator decisions and workflow checkpoints

The launch path in the repo is gated by explicit Strategy V2 decisions. The plan must require completion of these gates before downstream launch, creative, or Meta-specific automation can assume the campaign context is valid:

- proceed foundational research
- confirm competitor assets
- select the winning angle
- select the winning UMP/UMS pair
- select the winning offer variant
- approve final copy

The current launch context loader also requires specific checkpoint lineage, especially:

- `v2-06` angle synthesis and ranked angle candidates
- `v2-08` offer pipeline and ranked UMP/UMS pairs
- `v2-09` winner selection and artifact references
- `v2-11` final copy approval

Those checkpoint requirements should be explicit in the rollout plan rather than implied.

### C. Minimum pinned launch packet that downstream systems need

Before external URL delivery or Meta launch can proceed, the campaign should have a pinned downstream packet that includes at least:

- selected angle id
- selected angle name
- selected angle evidence
- ranked angle candidates / angle docs
- angle run id
- approved UMP
- approved UMS
- core promise
- value stack summary
- guarantee type
- pricing rationale
- approved offer winner
- selected product offer id
- approved copy artifact
- approved copy headline
- approved pre-sell markdown
- approved sales page markdown
- approved template payloads for:
  - `pre-sales-listicle`
  - `sales-pdp`
- copy quality gate report
- semantic gates
- congruency output
- copy context files
- awareness-angle matrix
- operator inputs required by downstream offer/ad generation:
  - business model
  - funnel position
  - target platforms
  - target regions
  - existing proof assets
  - brand voice notes

### D. Supporting research and proof context that should remain accessible

The delivery plan should also explicitly preserve access to supporting context that may be referenced by funnel generation, testimonial generation, proof selection, or ads QA:

- competitor analysis
- VOC observations
- VOC scored outputs
- proof asset candidates
- stage1 payload and competitor URLs

### E. Hard rule for downstream execution

Creative generation, external delivery setup, Meta review setup, and Meta launch should all fail fast if the required pinned Strategy V2 context is missing, stale, or unapproved.

This means the plan must treat the following as prerequisites, not optional enrichments:

- angle docs
- UMP/UMS decision
- offer winner decision
- final copy approval
- copy context
- awareness-angle matrix
- template payloads
- supporting proof and research references

## Current Repository Reality

The current codebase already has substantial infrastructure that this rollout should reuse.

### Foundational docs and campaign context

The system already reconstructs campaign context from internal artifacts rather than from a hand-managed docs directory. This is documented in:

- `docs/swipe-image-add-flow.md`

Relevant backend areas:

- `mos/backend/app/strategy_v2/`
- `mos/backend/app/temporal/activities/strategy_v2_launch_activities.py`
- `mos/backend/app/temporal/activities/asset_activities.py`

This is a strong foundation and should remain unchanged.

### Internal funnel generation

Campaign funnel generation is currently internal-funnel-only:

- `mos/backend/app/temporal/workflows/campaign_funnel_generation.py`
- `mos/backend/app/routers/campaigns.py`

The workflow hardcodes default pages:

- pre-sales listicle
- sales PDP

### Creative production coupling to funnels

Creative production is currently coupled to asset briefs that may carry `funnelId`:

- `mos/backend/app/schemas/asset_brief.py`
- `mos/backend/app/temporal/activities/experiment_activities.py`
- `mos/backend/app/temporal/activities/asset_activities.py`

Important current constraints:

- asset briefs may be populated with `funnelId`
- brief scope validation checks that the funnel belongs to the campaign
- some asset generation and persistence paths still expect funnel-backed context

This is the main coupling that must be loosened.

### Meta review setup already supports literal URLs

The Meta review preparation path already contains the right seam:

- `mos/backend/app/routers/campaigns.py`
- `mos/backend/app/services/paid_ads_qa.py`

Today it can resolve a destination from:

- an internal review path such as `pre-sales` or `sales`
- a literal URL if the destination field is already absolute

That means external URL support does not require replacing the entire Meta prep path.

### Meta launch and management are incomplete

The repo includes:

- Meta asset upload/create routes
- strict Meta spec persistence
- a management planner that computes metrics and recommends actions in `plan_only` mode

Key files:

- `mos/backend/app/routers/meta_ads.py`
- `mos/backend/app/services/meta_ads.py`
- `mos/backend/app/services/meta_media_buying.py`
- `docs/meta-media-buying-agent.md`

Important limitation:

- `mode=apply` for management is intentionally not implemented yet

This rollout should acknowledge that the prep path is much more complete than the full launch-and-manage loop.

## Target Architecture

### Core concept: campaign delivery mode

Introduce an explicit campaign delivery mode with two supported values:

- `internal_funnel`
- `external_urls`

This field becomes the switch that determines whether the campaign uses MOS-hosted funnel pages or externally hosted destinations.

### Core concept: campaign destination config

Store canonical campaign destinations independently from funnel records.

Recommended model:

- `pre_sales_url`
- `sales_url`
- `checkout_url` (optional)
- `thank_you_url` (optional)
- `validation_status`
- `validation_error`
- `validated_at`
- `delivery_notes` (optional operator annotation)

This should be modeled either:

1. As columns on `campaigns` if the scope is guaranteed to remain small and fixed.
2. As a dedicated `campaign_delivery_configs` table if more delivery metadata is expected over time.

Recommendation: use a dedicated table. The concept is durable, and it avoids overloading the `campaigns` table with delivery-specific operational state.

## Proposed Data Model

### New enum

Add a delivery mode enum:

- `internal_funnel`
- `external_urls`

### New table

Add `campaign_delivery_configs` with fields:

- `id`
- `org_id`
- `client_id`
- `campaign_id`
- `delivery_mode`
- `pre_sales_url`
- `sales_url`
- `checkout_url`
- `thank_you_url`
- `validation_status`
- `validation_error`
- `validated_at`
- `created_at`
- `updated_at`

Suggested constraints:

- unique on `campaign_id`
- non-null `delivery_mode`
- if `delivery_mode = external_urls`, require `pre_sales_url` and `sales_url`
- if `delivery_mode = internal_funnel`, external URL fields may be null

### Validation rules

For `external_urls`:

- `pre_sales_url` must be absolute `http` or `https`
- `sales_url` must be absolute `http` or `https`
- values must be trimmed and normalized
- duplicate pre-sales and sales URLs are allowed only if explicitly intended; otherwise reject
- no relative paths
- no blank values

For `internal_funnel`:

- no external destination is required
- downstream routes should continue using MOS funnel/publication paths

## API Plan

### Campaign delivery endpoints

Add:

- `GET /campaigns/{campaign_id}/delivery`
- `PUT /campaigns/{campaign_id}/delivery`
- `POST /campaigns/{campaign_id}/delivery/validate`

The write payload should include:

- `deliveryMode`
- `preSalesUrl`
- `salesUrl`
- `checkoutUrl`
- `thankYouUrl`

Validation should perform:

- strict URL format checks
- fetch checks for public accessibility
- landing page readiness checks for policy/privacy markers where appropriate

If validation fails, return a clear error payload. Do not silently accept and defer failure downstream.

### Validation staleness and invalidation rule

Delivery validation is scoped to the exact normalized delivery configuration.

For `external_urls` campaigns:

- validation pass/fail applies only to the normalized tuple of:
  - `pre_sales_url`
  - `sales_url`
  - `checkout_url`
  - `thank_you_url`
- any change to delivery mode or any normalized URL value must:
  - clear the previous validation result
  - set `validation_status = not_validated`
  - clear `validation_error`
  - clear `validated_at`
- the system must not reuse a prior successful validation after any destination change

For `internal_funnel` campaigns:

- validation status should be `not_applicable`
- switching from `external_urls` back to `internal_funnel` should clear stored external URLs and any prior validation result

Public URL rule:

- only public absolute `http` or `https` URLs are valid for external delivery
- reject localhost, loopback, private-network, and obvious intranet-style destinations

### Campaign create/update behavior

Extend campaign DTOs so the delivery mode can be surfaced in the UI and API.

Current relevant DTO:

- `mos/backend/app/schemas/common.py`

Frontend types to extend:

- `mos/frontend/src/types/common.ts`

### Funnel generation endpoint behavior

Current endpoint:

- `POST /campaigns/{campaign_id}/funnels/generate`

Proposed behavior:

- if `delivery_mode = internal_funnel`, keep current behavior
- if `delivery_mode = external_urls`, either:
  - reject with a clear message that internal funnel generation is not applicable, or
  - hide/disable the action in the UI and still keep backend protection

Recommendation: do both. UI should hide/disable, backend should enforce.

### Creative production endpoint behavior

Current endpoint:

- `POST /campaigns/{campaign_id}/creative/produce`

This endpoint can remain, but downstream generation must resolve destination configuration from campaign delivery state rather than assuming funnel-backed routing.

### Meta review setup endpoint behavior

Current endpoint:

- `POST /campaigns/{campaign_id}/meta/review-setup`

Extend it so destination resolution order becomes:

1. explicit creative spec destination URL
2. external campaign delivery config URL for the requested destination type
3. internal review path for funnel-backed campaigns

This keeps the current seam while making the external path first-class.

## Workflow Changes

### 0. Upstream Strategy V2 prerequisites and pinned launch context

This needs to be a named part of the delivery plan.

Before campaign delivery mode, creative production, or Meta launch runs, the system should validate that the campaign has:

- the foundational artifact set used by stage-one creative generation
- required Strategy V2 checkpoints and decision lineage
- a pinned downstream packet suitable for deterministic downstream execution

Required launch-side checkpoint lineage:

- `v2-06`
- `v2-08`
- `v2-09`
- `v2-11`

Required approved downstream artifacts:

- `strategy_v2_stage3`
- `strategy_v2_offer`
- `strategy_v2_copy`
- `strategy_v2_copy_context`
- optionally `strategy_v2_awareness_angle_matrix` when present for the selected run

Required approved decision state:

- selected angle
- selected UMP/UMS pair
- selected offer winner
- approved final copy

Required packet fields that should be queryable and auditable from the campaign:

- selected angle payload and ranked angle candidates
- angle run id
- stage3 UMP and UMS
- offer winner payload
- copy payload
- copy template payloads
- copy context payload
- awareness-angle matrix payload
- proof asset candidates and research support where available

Recommendation:

- add an explicit campaign-level "launch context readiness" check before allowing external delivery setup, creative generation, Meta review prep, or Meta launch
- implement that readiness check by reusing `load_strategy_v2_source_context`, not by creating a second contract

### Launch-context staleness rule

The campaign launch context should be treated as a pinned artifact derived from the Strategy V2 source run lineage returned by `load_strategy_v2_source_context`.

Staleness rule:

- the pinned campaign launch-context artifact is valid only for the exact source lineage used to build it
- if any required source provenance changes, the previous launch-context artifact becomes stale and a new artifact must be pinned before downstream execution continues

Required provenance inputs for staleness:

- source Strategy V2 workflow run id
- approved copy artifact id
- stage3 artifact id
- offer artifact id
- copy context artifact id
- awareness-angle-matrix artifact id when present
- required launch step payload lineage (`v2-06`, `v2-08`, `v2-09`, `v2-11`)

Effectively:

- any change in approved angle/copy/offer lineage invalidates the previously pinned launch packet
- the system should persist a new campaign launch-context artifact rather than silently continuing on a stale packet

### 1. Foundational docs and Strategy V2

No structural changes required.

The current system already rebuilds campaign-scoped source-of-truth context from:

- stage0
- stage1
- stage2
- stage3
- client canon
- strategy stages
- offer
- copy
- copy context
- strategy sheet
- experiment specs
- asset briefs

The only required addition is to include delivery configuration in campaign-scoped context bundles so downstream steps can consume it consistently.

In addition, the plan should explicitly state that the campaign workspace must expose the pinned Strategy V2 launch packet alongside those foundational docs so ads generation is grounded in the approved angle, UMP/UMS, offer, and copy decisions.

### 2. Internal funnel generation workflow

Keep current internal funnel workflow unchanged for `internal_funnel` campaigns.

Relevant file:

- `mos/backend/app/temporal/workflows/campaign_funnel_generation.py`

No need to change this workflow to support external URLs. External delivery should be a separate branch in campaign orchestration.

### 3. Asset brief generation

This is the main structural change.

Current issues:

- `AssetBrief` only models `funnelId`, not a canonical destination object
- `experiment_activities.py` may inject `funnelId` via `funnel_map`
- downstream consumers infer routing from funnel linkage

Proposed `AssetBrief` additions:

- `deliveryMode`
- `destinationType`
- `destinationLabel`
- keep `funnelId` optional for internal mode

Recommended semantics:

- internal campaigns:
  - `deliveryMode = internal_funnel`
  - `funnelId` may be set
  - `destinationType` can be `pre-sales` or `sales`
  - downstream resolution can map `destinationType` to internal review routing
- external campaigns:
  - `deliveryMode = external_urls`
  - `funnelId = null`
  - `destinationType` required
  - actual destination URL should be resolved from the campaign delivery config downstream
  - do not allow asset briefs to become a second canonical source of destination URLs in v1

### 4. Creative generation context and execution

Relevant file:

- `mos/backend/app/temporal/activities/asset_activities.py`

Required changes:

- stop treating `funnelId` as mandatory for downstream execution
- validate brief scope against campaign delivery config when no funnel exists
- persist destination metadata into:
  - ad copy pack artifacts
  - creative generation plan artifacts
  - asset `ai_metadata`

Current helper behavior that should be adjusted:

- `_validate_brief_scope`

New behavior:

- if `funnelId` exists, validate funnel ownership as today
- if `funnelId` does not exist, require a valid campaign delivery config and destination fields

### 5. Swipe copy and destination propagation

Current metadata fields already include:

- `destinationPage`
- `reviewPaths`
- `destination_url`

Extend metadata to include:

- `deliveryMode`
- `resolvedDestinationUrl`
- `campaignDeliveryConfigId`
- `destinationValidationSnapshot`

This ensures every generated asset carries enough lineage for review, QA, launch, and debugging.

### 6. Paid ads QA

Relevant file:

- `mos/backend/app/services/paid_ads_qa.py`

The current QA path already validates:

- destination URL presence
- public absolute URL resolution
- fetchability
- incomplete/under construction markers
- privacy markers

Required changes:

- support external campaign destinations as first-class sources
- report whether the destination source was:
  - `stored_destination_url`
  - `campaign_delivery_config`
  - `review_path`
  - `destination_page`

This is useful for auditability and failure diagnosis.

### 7. Meta launch compiler

The repo has the primitives to create Meta entities, but not yet a complete campaign launch compiler.

Required addition:

- a `LaunchPlan` artifact that captures the selected generation batch, asset set, destination wiring, copy, targeting assumptions, and budget structure

Compiler responsibilities:

- upload assets to Meta
- create ad creatives
- create campaign
- create ad sets
- create ads
- persist all remote IDs and request IDs
- remain idempotent when retried

This should sit above the current `/meta/*` primitives rather than replacing them.

### 8. Meta management loop

The current management planner computes insights and proposed actions in `plan_only` mode.

Required next step:

- implement `apply` mode with approval gates

Required persisted artifacts:

- metrics snapshot artifact
- recommended actions artifact
- approval decision record
- applied action record with before/after values

Actions to support first:

- pause ad
- adjust campaign budget

Actions to defer until later:

- duplicate into scaling campaign
- cross-campaign horizontal scaling

## Frontend Plan

### Campaign detail page

Current relevant screen:

- `mos/frontend/src/pages/campaigns/CampaignDetailPage.tsx`

Add a Delivery section with:

- delivery mode selector
- pre-sales URL field
- sales URL field
- optional checkout URL field
- optional thank-you URL field
- validate button
- validation status badge
- last validated timestamp

### UI behavior by mode

If `internal_funnel`:

- show current funnels tab and funnel actions
- show internal review links in Meta panel

If `external_urls`:

- hide or disable internal funnel creation action
- show external destination status
- show external links in Meta panel where pre-sales/sales links are currently shown

### Meta ads panel

Current relevant component:

- `mos/frontend/src/components/campaigns/CampaignMetaAdsPanel.tsx`

Update it so:

- pre-sales and sales buttons use external campaign URLs when applicable
- the panel clearly labels whether the destination source is internal review routing or external landing pages
- upload preview cards show canonical destination URL, not just symbolic destination page type

## Detailed Backend Work Breakdown

### Phase 0: Upstream artifact contract and launch-context readiness

1. Define the minimum pinned Strategy V2 contract required for downstream campaign execution.
2. Add a readiness check that validates required checkpoints, artifact refs, and approvals.
3. Expose that readiness state at the campaign level in the API and UI.
4. Ensure the pinned launch packet is persisted and queryable for all downstream flows.

Acceptance criteria:

- the system can explain exactly why a campaign is not ready for downstream execution
- readiness explicitly checks angle selection, UMP/UMS selection, offer winner selection, and final copy approval
- downstream flows do not start if the pinned Strategy V2 packet is incomplete

### Phase 1: Delivery config foundation

1. Add DB enum and migration.
2. Add `campaign_delivery_configs` table and repository.
3. Add schemas and router endpoints.
4. Extend campaign payloads and frontend types.
5. Add validation service for external URLs.

Acceptance criteria:

- a campaign can persist delivery mode and external URLs
- invalid URLs hard-fail
- validation status is stored and queryable

### Phase 2: Creative pipeline decoupling

1. Extend `AssetBrief` schema.
2. Update asset brief generation to populate destination fields.
3. Refactor `asset_activities.py` to stop requiring `funnelId` for external campaigns.
4. Propagate destination metadata into ad copy packs, generation plans, and asset metadata.
5. Add tests for both internal and external campaign paths.

Acceptance criteria:

- creative production runs successfully for a campaign with external URLs and no funnel rows
- generated asset metadata includes canonical destination information

### Phase 3: Meta review and QA hardening

1. Update Meta review setup to read campaign delivery config.
2. Update QA destination resolution order.
3. Surface destination source in review payloads and QA findings.
4. Add integration tests for external landing page review.

Acceptance criteria:

- Meta review setup produces creative specs with external `destination_url`
- paid ads QA can fetch and assess those external pages

### Phase 4: Meta launch compiler

1. Define `LaunchPlan` schema and artifact type.
2. Add compiler service from prepared specs to Meta mutations.
3. Add idempotent request key strategy.
4. Persist launch results in existing Meta persistence tables.
5. Add launch endpoint and status polling.

Acceptance criteria:

- operators can launch a prepared generation batch into Meta without manual object creation
- reruns do not duplicate remote objects unexpectedly

### Phase 5: Meta management apply mode

1. Implement approved action executor for `pause_ad`.
2. Implement approved action executor for budget changes.
3. Persist actions and approvals.
4. Add scheduled workflow for recurring plan generation.
5. Add management UI for review and approval.

Acceptance criteria:

- `plan_only` and `apply` share the same decision logic
- applied changes are persisted with reason, entity, before, and after

## Testing Plan

### Backend tests

Add or extend tests around:

- campaign delivery config validation
- external URL persistence
- asset brief generation without `funnelId`
- creative production with external destinations
- Meta review setup with literal external URLs
- paid ads QA against external URLs
- launch plan compilation
- management `apply` behavior

Likely locations:

- `mos/backend/tests/`
- current Meta tests such as:
  - `test_campaign_meta_review_destination.py`
  - `test_campaign_meta_review_setup.py`

### Frontend tests

Add tests for:

- delivery mode toggle behavior
- URL validation form state
- hiding internal funnel actions when in external mode
- Meta panel destination link rendering in both modes

### Manual verification checklist

For an external-url campaign:

1. Complete foundational docs / Strategy V2.
2. Save external pre-sales and sales URLs.
3. Validate URLs.
4. Generate creatives.
5. Prepare Meta review.
6. Run paid ads QA.
7. Confirm created Meta creative specs reference the external destination URLs.

## Rollout Strategy

### Feature flag

Gate the new external delivery path behind a feature flag at org or client level.

Recommendation:

- reuse the existing tenant-aware rollout pattern already used for Strategy V2

### Backward compatibility

Existing campaigns should default to:

- `internal_funnel`

No existing funnel generation behavior should change for those campaigns.

### Migration strategy

For pre-existing campaigns:

- backfill an internal default delivery config via migration
- do not infer external URLs from historical data

## Risks and Mitigations

### Risk: creative pipeline still contains hidden funnel assumptions

Mitigation:

- audit every place that reads `funnelId`
- add failing tests for external campaigns with no funnel linkage

### Risk: operators confuse draft-review URLs with canonical live destinations

Mitigation:

- always label destination source in UI and metadata
- distinguish:
  - internal review path
  - external canonical URL
  - live published MOS funnel URL

### Risk: external pages fail policy readiness checks more often than internal pages

Mitigation:

- add a dedicated validation and QA step before Meta prep
- make privacy/policy/readiness failures visible early

### Risk: Meta launch implementation duplicates remote entities on retry

Mitigation:

- require deterministic request IDs and stored remote mappings
- persist launch plan and launch execution state

## Resolved Decisions

The following decisions are fixed for v1 and should be treated as implementation requirements:

1. Reuse `load_strategy_v2_source_context` as the canonical Strategy V2 launch-context contract.
2. Treat pre-sales and sales as both required for `external_urls` campaigns.
3. Keep checkout and thank-you URLs operator-managed but optional in v1.
4. Support only one canonical pre-sales URL and one canonical sales URL per campaign in v1.
5. Do not allow asset briefs to override campaign canonical destinations with literal URLs in v1.
6. Require destination validation to pass before Meta launch; no manual bypass in v1.
7. Accept only public absolute `http` or `https` destinations for external delivery validation.
8. Store validation status, error message, and timestamp in v1; do not persist fetched HTML snapshots.
9. Backfill default `internal_funnel` delivery configs in migration rather than creating them lazily on read.

## Recommended Build Order

The fastest high-value sequence is:

1. Upstream artifact contract and launch-context readiness
2. Delivery config foundation
3. Creative pipeline decoupling
4. Meta review and QA hardening
5. Meta launch compiler
6. Meta management apply mode

This order gets the system to:

- foundational docs
- pinned angle / UMP / UMS / offer / copy context
- external pre-sales and sales URLs
- creative production
- Meta-ready review and QA

before taking on the more complex launch-and-management automation.

## Definition of Done

This initiative should be considered complete when:

1. A campaign can explicitly choose `external_urls` delivery mode.
2. A campaign exposes explicit readiness for downstream execution based on pinned Strategy V2 context.
3. Angle docs, UMP/UMS decisions, offer winner, final copy approval, copy context, and template payloads are all queryable from the campaign launch context.
4. Pre-sales and sales external URLs can be saved, validated, and surfaced in the UI.
5. Asset briefs and creative production can run without any internal funnel rows.
6. Prepared Meta creative specs carry canonical external destination URLs.
7. Paid ads QA validates those external destinations successfully.
8. Meta launch can create campaign objects from prepared specs.
9. Meta management can compute and apply approved actions with audit history.

## Recommendation

Implement this as a delivery-mode expansion of the campaign system, not as an attempt to force external URLs into the existing funnel model.

Internal funnels should remain the MOS-native path.
External URLs should become a first-class alternative path.
Both should share the same foundational docs, asset brief, creative production, QA, and Meta orchestration layers wherever that reuse is structurally sound.
