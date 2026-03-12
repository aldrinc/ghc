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
3. Choose a delivery mode for the campaign:
   - `internal_funnel`
   - `external_urls`
4. If `internal_funnel`:
   - Generate pre-sales and sales pages in MOS.
   - Optionally publish/deploy them.
5. If `external_urls`:
   - Save canonical pre-sales URL.
   - Save canonical sales URL.
   - Optionally save checkout URL and thank-you URL.
   - Validate the URLs before downstream work begins.
6. Generate asset briefs and run creative production.
7. Prepare Meta review payloads and validate landing pages.
8. Launch Meta assets, creatives, ad sets, campaigns, and ads.
9. Run deterministic management and decision workflows for cut, scale, and review.

## Guiding Principles

- Keep foundational docs unchanged as the source of truth for strategy, offer, copy, and campaign context.
- Treat delivery configuration as a campaign concern, not as a side effect of funnel generation.
- Do not add silent fallbacks. Missing or invalid destination configuration should fail with clear errors.
- Keep internal funnels and external URLs as supported parallel modes rather than trying to fake one as the other.
- Reuse the current creative, QA, and Meta prep pipeline wherever possible.

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

### 1. Foundational docs and Strategy V2

No structural changes required.

The current system already rebuilds campaign-scoped source-of-truth context from:

- client canon
- strategy stages
- offer
- copy
- copy context
- strategy sheet
- experiment specs
- asset briefs

The only required addition is to include delivery configuration in campaign-scoped context bundles so downstream steps can consume it consistently.

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
- `destinationUrl`
- `destinationLabel`
- keep `funnelId` optional for internal mode

Recommended semantics:

- internal campaigns:
  - `deliveryMode = internal_funnel`
  - `funnelId` may be set
  - `destinationType` can be `pre-sales` or `sales`
  - `destinationUrl` may be omitted until review path resolution
- external campaigns:
  - `deliveryMode = external_urls`
  - `funnelId = null`
  - `destinationType` required
  - `destinationUrl` required

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

- auto-create an internal default delivery config on read or via migration backfill
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

## Open Product Decisions

These decisions should be made before implementation starts:

1. Are pre-sales and sales both always required for external campaigns, or can a campaign run with only one canonical destination?
2. Should checkout URL be operator-managed now, or deferred until management/reporting needs it?
3. Should external delivery support multiple destination variants per campaign, or only one canonical pre-sales and one canonical sales URL in v1?
4. Should Meta launch be allowed only after destination validation passes, or can operators bypass with a manual override?
5. Should external destination validation store fetched snapshots for audit, or only pass/fail status and error messages?

## Recommended Build Order

The fastest high-value sequence is:

1. Delivery config foundation
2. Creative pipeline decoupling
3. Meta review and QA hardening
4. Meta launch compiler
5. Meta management apply mode

This order gets the system to:

- foundational docs
- external pre-sales and sales URLs
- creative production
- Meta-ready review and QA

before taking on the more complex launch-and-management automation.

## Definition of Done

This initiative should be considered complete when:

1. A campaign can explicitly choose `external_urls` delivery mode.
2. Pre-sales and sales external URLs can be saved, validated, and surfaced in the UI.
3. Asset briefs and creative production can run without any internal funnel rows.
4. Prepared Meta creative specs carry canonical external destination URLs.
5. Paid ads QA validates those external destinations successfully.
6. Meta launch can create campaign objects from prepared specs.
7. Meta management can compute and apply approved actions with audit history.

## Recommendation

Implement this as a delivery-mode expansion of the campaign system, not as an attempt to force external URLs into the existing funnel model.

Internal funnels should remain the MOS-native path.
External URLs should become a first-class alternative path.
Both should share the same foundational docs, asset brief, creative production, QA, and Meta orchestration layers wherever that reuse is structurally sound.
