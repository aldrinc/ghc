# Campaign Delivery Variant Clone Plan

## Summary

Delivery mode switching should not mutate an existing campaign in place.

Instead, switching delivery mode should create a new campaign variant that:

- reuses the existing creative media
- preserves the same approved launch context lineage
- creates a fresh campaign-scoped delivery configuration
- rebuilds the Meta preparation layer for the new delivery mode
- leaves the source campaign untouched as the historical record

This plan replaces in-place delivery switching with a clone-and-rebuild workflow.

## Core Product Decision

Treat `switch delivery mode` as:

1. clone the current campaign into a new campaign variant
2. reuse the existing creative media without rerunning creative generation
3. rebuild all campaign-scoped Meta preparation artifacts on the new campaign
4. never copy live Meta entity state or publish history into the new campaign

This is the key boundary:

- creative media is reusable
- Meta prep metadata is not reusable

## Why This Approach Fits The Current System

The current codebase stores most downstream ad-launch state at the campaign level:

- `Campaign`
- `CampaignDeliveryConfig`
- `Asset`
- `MetaCreativeSpec`
- `MetaAdSetSpec`
- `MetaPublishSelection`
- `MetaPublishRun`
- `MetaPublishRunItem`

Relevant code anchors:

- campaign and delivery config: `mos/backend/app/db/models.py`
- delivery endpoints: `mos/backend/app/routers/campaigns.py`
- Meta review setup: `mos/backend/app/routers/campaigns.py`
- Meta publish validation and execution: `mos/backend/app/routers/meta_ads.py`
- launch context readiness: `mos/backend/app/services/campaign_launch_context.py`

Because those rows are campaign-scoped, cloning to a new campaign is safer than trying to swap delivery mode and downstream launch state in place.

## Goals

- allow an operator to switch from internal funnel delivery to external URL delivery without rerunning creative generation
- allow an operator to switch from external URL delivery to internal funnel delivery without reusing stale Meta metadata
- preserve the source campaign as the historical campaign of record
- keep creative media reusable across delivery variants
- force the target campaign to rebuild Meta-ready destination metadata before publish

## Non-Goals

- do not reuse old Meta creative specs directly
- do not reuse old Meta publish plans directly
- do not migrate live Meta campaign objects from one MOS campaign to another
- do not silently keep running an already-launched campaign under a different delivery mode
- do not introduce delivery-mode-specific fallbacks that bypass validation

## Operator UX

### Entry Point

Add a primary action on the campaign delivery surface and Meta surface:

- `Create delivery variant`

This replaces the idea of directly toggling a campaign between `internal_funnel` and `external_urls`.

### Modal

When the operator clicks `Create delivery variant`, show a modal with:

- target delivery mode
- new campaign name
- if target is `external_urls`:
  - `preSalesUrl`
  - `salesUrl`
  - optional `checkoutUrl`
  - optional `thankYouUrl`
- if target is `internal_funnel`:
  - operator guidance that the new campaign will require one funnel before Meta review or launch

Modal copy should say:

- the current campaign will remain unchanged
- approved creative media will be reused
- Meta review setup, QA, and launch state will be rebuilt for the new variant
- existing publish history will not carry forward

### Post-Clone Landing

After clone succeeds, route the operator to the new campaign detail page.

The new campaign should show:

- source campaign link
- delivery mode badge
- cloned asset/media availability
- launch context readiness
- delivery readiness state
- a clear next action:
  - `Validate URLs` for external
  - `Attach or create funnel` for internal

## Variant Semantics

The source campaign remains frozen in meaning.

The target campaign is a sibling campaign variant with:

- a new `Campaign.id`
- the same client and product linkage
- the same launch-context source lineage
- copied asset media
- no copied live Meta entity state

Recommended naming behavior:

- source: `Campaign Name`
- target external variant: `Campaign Name · External`
- target internal variant: `Campaign Name · Internal`

## Data Copy and Rebuild Rules

### Copy

Copy these into the new campaign:

- campaign core fields:
  - `client_id`
  - `product_id`
  - `channels`
  - `asset_brief_types`
  - goal and budget fields
- launch-context lineage:
  - create a new `StrategyV2Launch` row for the target campaign pointing to the same source Strategy V2 run and artifacts
- asset brief artifacts:
  - copy brief artifact payloads into new campaign-scoped artifact rows
- ready asset rows:
  - create new `Asset` rows under the target campaign
  - reuse the same stored media by keeping `storage_key`, `content_type`, size, dimensions, and file status

### Rewrite During Copy

Rewrite these fields when cloning:

- `campaign_id`
- `asset_brief_artifact_id`
- delivery-related brief fields:
  - `deliveryMode`
  - `funnelId`
  - `destinationType`
  - `destinationLabel`
- delivery-related asset metadata:
  - strip stale `campaignDeliveryConfigId`
  - strip stale `resolvedDestinationUrl`
  - strip stale `destinationSource`
  - strip stale `destinationValidationSnapshot`
  - strip stale delivery-mode-specific values that were derived from the source campaign
- asset lineage metadata:
  - add `sourceCampaignId`
  - add `sourceAssetId`
  - add `clonedForDeliveryVariant = true`

### Rebuild

Regenerate these on the target campaign:

- `CampaignDeliveryConfig`
- `MetaCreativeSpec`
- `MetaAdSetSpec`
- launch-plan artifact
- campaign-level Meta QA run output

### Never Copy

Do not copy these into the new campaign:

- `MetaAssetUpload`
- `MetaAdCreative`
- `MetaCampaign`
- `MetaAdSet`
- `MetaAd`
- `MetaPublishRun`
- `MetaPublishRunItem`

These are execution records for the source campaign and should remain there.

## Publish Selection Decision

There are two valid options for publish selections:

### Option A: Do Not Copy Selections

Pros:

- cleanest interpretation of "swap out all Meta elements"
- no risk of copying stale package decisions

Cons:

- operator must re-curate the final package

### Option B: Copy Selections Using Source Asset -> Target Asset Mapping

Pros:

- the operator keeps the same included and excluded media set
- reduces repetitive setup

Cons:

- requires deterministic old-to-new asset mapping during clone

Recommendation for v1:

- copy publish selections
- treat them as operator curation rather than Meta launch metadata
- only copy them if every selected source asset has a matching cloned target asset

If that mapping is incomplete, fail the clone with a clear error rather than partially copying.

## Direction-Specific Behavior

### Internal Funnel -> External URLs

This is the cleanest direction.

Behavior:

- clone the campaign
- create target delivery config with `external_urls`
- clear `funnelId` from cloned briefs
- clear `funnel_id` from cloned assets
- require URL validation before Meta review setup or publish
- rebuild Meta creative specs so destination URLs point at the external pre-sales or sales URL

Creative media is reused as-is.

### External URLs -> Internal Funnel

This direction is valid, but the target campaign will need a funnel before Meta review.

Behavior:

- clone the campaign
- create target delivery config with `internal_funnel`
- clear any external URLs from the target delivery config
- keep creative media
- block Meta review setup until the operator provides one target funnel for the new campaign

The operator can satisfy the funnel requirement by either:

- generating a new funnel for the target campaign
- duplicating an existing funnel into the target campaign

The target campaign should not attempt to infer a funnel automatically.

### Internal Funnel -> Internal Funnel

Not a delivery mode switch.

Out of scope for this action.

### External URLs -> External URLs

This is effectively `clone campaign as external variant`.

Allowed if useful operationally, but not required for the first implementation.

## Funnel Handling For Internal Targets

For a target campaign with `internal_funnel` delivery:

- one explicit funnel must eventually be attached or selected for Meta review setup
- cloned assets can exist before that funnel exists
- the campaign should expose a blocked state until a valid funnel is available

Recommended operator action:

- `Attach or create funnel`

Implementation options:

1. Add an explicit target-campaign funnel attach flow.
2. Reuse the existing funnel duplication flow if the source campaign already has a suitable funnel.

Recommendation:

- support both
- do not auto-attach a funnel without operator intent

## Backend Workflow

### New Endpoint

Add a backend endpoint:

- `POST /campaigns/{campaign_id}/clone-for-delivery-switch`

Suggested request shape:

```json
{
  "targetDeliveryMode": "external_urls",
  "name": "Campaign Name · External",
  "preSalesUrl": "https://lp.example.com/pre-sale",
  "salesUrl": "https://lp.example.com/offer",
  "checkoutUrl": null,
  "thankYouUrl": null,
  "copyPublishSelections": true
}
```

For internal target mode:

```json
{
  "targetDeliveryMode": "internal_funnel",
  "name": "Campaign Name · Internal",
  "copyPublishSelections": true
}
```

### Endpoint Responsibilities

The endpoint should:

1. load the source campaign
2. verify the source campaign exists and belongs to the org
3. verify launch-context lineage can be cloned
4. create the target campaign
5. create the target delivery config
6. clone asset brief artifacts
7. clone ready assets
8. optionally copy publish selections
9. create a new target `StrategyV2Launch` row
10. return:
   - target campaign id
   - target delivery config
   - cloned asset count
   - copied brief count
   - copied selection count
   - next required operator action

### Launch Context Handling

The target campaign must pass the same readiness contract as the source campaign.

Do this by inserting a new `StrategyV2Launch` row for the target campaign that points to:

- the same `source_strategy_v2_workflow_run_id`
- the same source artifacts
- the same selected angle / offer / copy lineage

That allows `ensure_campaign_launch_context_artifact` to operate normally on the target campaign.

### Asset Brief Cloning

Asset briefs are stored in artifact payloads rather than a first-class table.

Clone plan:

- create new artifact rows under the target campaign
- preserve brief ids if they are only campaign-scoped
- preserve requirement indexes
- preserve creative concept, constraints, tone, and visual guidance
- rewrite delivery fields for the target mode

Internal -> external rewrite:

- `deliveryMode = external_urls`
- `funnelId = null`
- keep `destinationType`

External -> internal rewrite:

- `deliveryMode = internal_funnel`
- external URLs are not embedded in the brief
- `funnelId` remains null until a funnel is attached

### Asset Cloning

Clone only reusable creative media:

- assets with `file_status = ready`
- assets belonging to the source campaign

For each target asset:

- create a new `Asset` row
- reuse:
  - `storage_key`
  - `content_type`
  - `size_bytes`
  - `width`
  - `height`
  - `asset_kind`
  - `channel_id`
  - `format`
  - approved or draft status as appropriate
- rewrite:
  - `campaign_id`
  - `asset_brief_artifact_id`
  - `funnel_id` based on target mode
- scrub stale delivery-derived metadata

Do not rerun image generation, video generation, or remote creative-service jobs.

## Meta Layer Rebuild Rules

The clone action should not create Meta specs automatically.

Instead, the target campaign should use the existing downstream preparation flow:

- operator validates external URLs or attaches a funnel
- operator clicks `Prepare Meta review`
- system creates fresh `MetaCreativeSpec` and `MetaAdSetSpec` rows for the target campaign

This keeps the system aligned with current preparation boundaries and avoids inventing a second Meta-spec compiler path.

### Fresh Meta Creative Spec Requirements

Target `MetaCreativeSpec` rows must be rebuilt with:

- target campaign id
- target delivery mode
- target `campaignDeliveryConfigId`
- target `destinationSource`
- fresh `resolvedDestinationUrl`
- fresh `reviewPaths` for internal funnel targets
- fresh destination metadata in `metadata_json`

### Fresh Meta Ad Set Spec Requirements

Target `MetaAdSetSpec` rows must be rebuilt with:

- target campaign id
- fresh conversion-domain expectations
- any destination-dependent metadata refreshed

If the current ad set editor is not strongly destination-aware, still rebuild the row so it is target-campaign-scoped and not carrying source-campaign lineage implicitly.

## Staleness Rules

Once a delivery variant is created:

- the source campaign's Meta specs remain valid only for the source campaign
- the target campaign starts with no valid Meta prep state
- the target campaign must regenerate Meta prep state before publish

For the target campaign:

- external delivery must validate before Meta review setup, QA, or publish
- internal delivery must have one explicit funnel before Meta review setup, QA, or publish

## Frontend Work

### New Actions

Add:

- `Create delivery variant`
- `Switch to external via variant`
- `Switch to internal via variant`

These should open the same modal with different defaults.

### New Clone Modal

Fields:

- target delivery mode
- target campaign name
- external URLs when applicable
- copy publish selections toggle

### Target Campaign State

After clone, the target campaign should show:

- a banner indicating it was cloned from the source campaign
- source campaign link
- delivery readiness state
- media reuse summary
- next action CTA

### Meta Surface Updates

On the target campaign, the Meta panel should:

- show that creative media was cloned
- show that Meta review setup has not yet been regenerated
- hide publish actions until Meta prep is rebuilt

## Error Handling

Fail the clone cleanly if:

- source campaign does not exist
- source launch lineage cannot be loaded
- target delivery config is invalid
- publish selections are requested to be copied but asset mapping is incomplete
- required target inputs are missing

Do not silently downgrade behavior.

## Analytics and Audit

Persist clone metadata so the target campaign can explain its origin:

- `sourceCampaignId`
- `cloneReason = delivery_switch`
- `sourceDeliveryMode`
- `targetDeliveryMode`
- `createdByUserId`
- timestamp

Recommended storage:

- campaign metadata artifact or a dedicated lightweight audit artifact

## Testing Plan

### Backend Tests

Add tests for:

- clone internal -> external campaign creates new campaign and leaves source unchanged
- clone external -> internal campaign creates new campaign and blocks Meta review until funnel exists
- cloned campaign reuses stored media without rerunning creative generation
- target campaign gets a fresh delivery config
- target campaign gets a cloned launch lineage row
- cloned assets scrub stale delivery-derived metadata
- copied publish selections map source asset ids to target asset ids correctly
- no live Meta entity rows are copied
- target Meta review setup produces fresh Meta creative specs with the new destination source

### Integration Tests

Add end-to-end tests for:

1. internal source campaign with published funnel -> create external variant -> validate URLs -> prepare Meta review -> publish plan uses external URLs
2. external source campaign -> create internal variant -> attach funnel -> prepare Meta review -> publish plan uses internal review paths

### Regression Tests

Add tests ensuring:

- source campaign publish history remains visible only on the source campaign
- target campaign cannot publish using source campaign specs
- changing target delivery config after clone invalidates target-only readiness, not source readiness

## Build Order

### Phase 1: Backend Clone Foundation

1. add clone endpoint
2. clone campaign core fields
3. clone launch lineage
4. create target delivery config

### Phase 2: Creative Reuse

1. clone asset brief artifacts
2. clone ready assets
3. scrub stale delivery metadata
4. add source-to-target asset mapping support

### Phase 3: Meta Layer Reset

1. ensure no live Meta rows are copied
2. copy publish selections if enabled
3. gate target campaign Meta actions on fresh prep

### Phase 4: Frontend UX

1. add clone modal
2. add target campaign banners and next actions
3. route users into the new campaign variant

### Phase 5: Direction-Specific Completion

1. internal -> external happy path
2. external -> internal attach-funnel flow
3. regression coverage

## Acceptance Criteria

This work is complete when:

1. an operator can create a new external delivery campaign variant from an internal funnel campaign
2. the new campaign reuses creative media without rerunning creative generation
3. the new campaign has fresh delivery config and fresh Meta specs
4. the source campaign keeps its original delivery setup and publish history
5. a target campaign cannot publish until its own Meta prep state is rebuilt
6. an operator can create a new internal delivery campaign variant from an external campaign
7. the internal target remains blocked until one funnel is attached or created
8. no stale destination metadata survives from source campaign to target campaign publish flow

## Recommendation

Implement this as a campaign-variant creation flow, not as an in-place delivery toggle.

That gives the operator the behavior they want:

- keep the creative work
- swap the destination model
- rebuild the Meta payload layer cleanly
- preserve the original campaign as a historical artifact
