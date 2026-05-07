# Swipe Image Grouped Generation PRD

## Decision

We should move swipe-image generation from a per-raster runner to a grouped MOS workflow where one logical ad concept owns:

- one shared prompt/context pass
- one shared copy pack
- three sibling renders: `1:1`, `4:5`, `9:16`
- one review package
- one publish unit for Meta

This should be implemented in MOS first and kept model-agnostic at the orchestration layer. The default render model should remain Nano Banana 2 unless explicitly overridden.

## Current State

This run exposed four structural bottlenecks:

1. We pay stage-1 prompt generation three times for the same concept.
2. The local runner polls heavyweight workflow endpoints too often.
3. Retry behavior collapses the tail and forces operator babysitting.
4. Campaign generation is still organized as many raster jobs instead of logical ad groups.

Observed baseline from the GLP + quiz run:

- `249` rasters total
- `83` logical ads
- `3` aspect ratios per logical ad
- per-raster latency:
  - avg `136.5s`
  - median `109.3s`
  - p95 `293.7s`
  - max `835.7s`
- completed 3-ratio groups average `409.8s` summed runtime
- early concurrency was healthy at roughly `3.2-3.6` active workflows out of configured `4`
- the long tail degraded to roughly `1-2` effective workers after failures

## Model Compatibility

### Compatibility verdict

Yes. The grouped-generation design will work with Nano Banana 2 as the default render model.

That conclusion is based on the current MOS implementation:

- `mos/backend/app/config.py`
  - `SWIPE_IMAGE_RENDER_MODEL` defaults to `gemini-3.1-flash-image-preview`
- `mos/backend/app/temporal/activities/swipe_image_ad_activities.py`
  - stage-1 prompt generation model and final image render model are already separated
  - `render_model_id` is resolved late, after the prompt/context work
  - the render provider is chosen by `get_image_render_provider(model_id=render_model_id)`
- `mos/backend/app/services/image_render_client.py`
  - provider dispatch is model-driven, not workflow-driven
  - Gemini image models route to `EmbeddedFreestyleImageRenderClient`
  - `nano-banana-*` model ids route to `HiggsfieldImageRenderClient`
  - `gpt-image-*` model ids route to `OpenAIImageRenderClient`

That means the grouped workflow can stay independent of the renderer. It only needs to:

- build shared context once
- fan out sibling render requests with `count=1`
- pass the same `render_model_id` into each child render

The renderer-specific logic remains where it already belongs: inside the render client.

## Important nuance

There are two Nano Banana paths in the codebase today:

1. Default swipe-image path:
   - `gemini-3.1-flash-image-preview`
   - routed through `EmbeddedFreestyleImageRenderClient`
2. Higgsfield Nano Banana path:
   - `nano-banana-pro`
   - routed through `HiggsfieldImageRenderClient`

The grouped plan is compatible with both, because both are selected by model id at render time.

## What must stay true

To keep Nano Banana compatibility clean, the grouped design should preserve these invariants:

- each sibling render is still a single render request with `count=1`
- aspect ratio stays explicit on each sibling request
- orchestration does not branch on provider-specific behavior
- no automatic model fallback is introduced
- any provider-specific aliasing remains inside model normalization / provider inference

## One compatibility caveat

If "Nano Banana 2" later arrives under a new literal model id that does not match either:

- `gemini-*`
- `nano-banana-*`

then MOS will need a small provider-mapping update in `get_image_render_provider()` and possibly `_normalize_render_model_id()`. That is a naming issue, not an architecture issue.

With the current default model identifiers already in MOS, grouped execution is compatible.

## Product Requirements

### Primary goal

Cut wall-clock time for a full 3-ratio Meta creative batch by at least `2x` in normal operation while removing manual recovery work from the operator path.

### Secondary goals

- keep review speed high
- keep copy-to-destination congruence intact
- keep the render model fixed unless explicitly overridden
- make reruns resume from MOS state instead of local script state

### Non-goals

- changing the default render model
- introducing automatic fallback to another model
- weakening approval/review gates
- changing downstream Meta publish semantics beyond grouped asset support

## Refined Architecture

### 1. Introduce a logical ad group contract

Replace the per-raster request with a grouped request.

Current request shape is effectively:

```json
{
  "aspectRatio": "1:1",
  "count": 1,
  "renderModelId": "gemini-3.1-flash-image-preview"
}
```

Proposed grouped request shape:

```json
{
  "groupKey": "curated-10-glp",
  "copyPackId": "copy-pack-uuid",
  "reviewManifestId": "review-manifest-uuid",
  "aspectRatios": ["1:1", "4:5", "9:16"],
  "renderModelId": "gemini-3.1-flash-image-preview",
  "countPerAspectRatio": 1
}
```

Implementation targets:

- `mos/backend/app/schemas/swipe_image_ads.py`
- `mos/backend/app/temporal/workflows/swipe_image_ad.py`

### 2. Build shared context once per logical ad

Move these steps to the group level:

- resolve competitor swipe source
- resolve product references
- resolve destination context
- resolve congruence block
- generate stage-1 prompt
- attach shared copy pack

Then fan out three render children.

Implementation target:

- `mos/backend/app/temporal/activities/swipe_image_ad_activities.py`

### 3. Keep copy at group scope, not raster scope

One logical ad should own one copy pack.

Each aspect ratio sibling should reference the same:

- headline
- primary text
- description
- destination URL
- CTA mapping
- congruence block

Implementation target:

- reuse the copy-pack patterns already present in `mos/backend/app/temporal/activities/asset_activities.py`

### 4. Execute sibling renders in parallel

For each logical group:

- spawn `1:1`, `4:5`, and `9:16` render children immediately
- pass the same shared prompt/context payload to each child
- persist outputs under one `groupKey`
- record one child result per aspect ratio

Operational rule:

- keep `count=1` per child render
- do not use provider-specific multi-output batching for the first version

That keeps checkpointing deterministic and model behavior stable across Nano Banana and GPT Image 2.

### 5. Parallelize briefs in MOS, not in the local runner

Current bottleneck:

- GLP and quiz execute too serially at the campaign layer

Change:

- run GLP and quiz as parallel brief executions
- preserve per-brief checkpoints
- package review artifacts per brief as soon as each finishes

Implementation target:

- `mos/backend/app/temporal/workflows/creative_production.py`

### 6. Make MOS the source of truth for recovery

The current local runner owns too much recovery state.

Move these into MOS:

- grouped run state
- child render state
- retry counters
- terminal error classification
- review manifest references
- dead-letter failures

The local runner should become optional operator tooling, not the system of record.

### 7. Replace heavyweight polling with lean status APIs

Add:

- `GET /workflows/{id}/status`
  - `status`
  - `startedAt`
  - `finishedAt`
  - `progress`
  - `lastStep`
  - `terminalErrorSummary`
- `GET /assets/{id}`
  - `id`
  - `publicId`
  - `contentType`
  - `width`
  - `height`
  - `aiMetadata`

Alternative acceptable improvement:

- include resolved asset refs directly in workflow `payload_out`

### 8. Add campaign-safe failure handling

Current behavior is too brittle.

Required failure taxonomy:

- `retryable_transient`
- `provider_timeout`
- `prompt_parse`
- `config_error`
- `missing_reference`
- `policy_block`
- `unknown`

Required behavior:

- auto-retry only `retryable_transient`
- same model only
- continue the rest of the campaign
- record failed groups in a reviewable dead-letter set
- require explicit user approval for any model change

### 9. Defer local file materialization

Do not download every image during core generation.

Store in MOS:

- asset ids
- public asset refs
- metadata
- group manifests

Only materialize local files for:

- contact sheets
- OCR / text QA
- human review bundles
- final export

## Proposed Data Model Additions

### Group-level record

Add a grouped generation record with:

- `group_key`
- `campaign_id`
- `copy_pack_id`
- `review_manifest_id`
- `render_model_id`
- `status`
- `shared_prompt_artifact_id`
- `shared_context_artifact_id`
- `attempt_count`
- `result_summary`

### Child render record

One row per aspect ratio sibling:

- `group_generation_id`
- `aspect_ratio`
- `asset_id`
- `status`
- `attempt_count`
- `error_class`
- `error_detail`
- `provider`
- `render_model_id`

## API / Workflow Shape

### Phase 1: grouped request

`POST /swipes/generate-image-ad-group`

Responsibilities:

- validate grouped payload
- create grouped workflow
- return `workflowRunId` + `groupKey`

### Phase 2: grouped workflow

`SwipeImageAdGroupWorkflow`

Responsibilities:

- compute shared context once
- create sibling render children
- await all children
- persist grouped result summary
- emit grouped payload out

### Phase 3: review bundle

One review artifact per group:

- copy
- congruence block
- sibling asset refs
- render model used
- source references used

## Rollout Plan

### Phase 0: instrumentation only

- add latency metrics at group and child level
- add error taxonomy
- add lightweight status endpoint

### Phase 1: grouped generation behind a flag

- add new request schema
- add grouped workflow
- keep current single-raster route working
- use Nano Banana 2 as the default render model

### Phase 2: brief-level parallelism

- run GLP and quiz grouped workflows in parallel
- preserve deterministic bucketing and review manifests

### Phase 3: retire bespoke batch runner

- local runner becomes operator helper only
- MOS owns:
  - orchestration
  - checkpointing
  - retries
  - review packaging
  - resume behavior

## Success Metrics

We should track:

- wall-clock batch duration
- group-level p50 / p95 runtime
- child-render p50 / p95 runtime
- percent of runs requiring operator intervention
- percent of groups needing retry
- percent of terminal failures by error class
- review-package time to ready

Target outcomes:

- `>= 2x` faster wall-clock vs current real-world run
- no operator babysitting for transient failures
- no copy/destination congruence regressions
- no renderer changes from the approved default model

## Implementation Order

1. Add grouped request/response schema.
2. Add grouped workflow and child render records.
3. Reuse shared prompt/context generation once per group.
4. Fan out sibling renders with `count=1`.
5. Add lean workflow status and asset lookup endpoints.
6. Add failure taxonomy + dead-letter tracking.
7. Parallelize `CreativeProductionWorkflow` across briefs.
8. Move review packaging fully into MOS.
9. Retire the local per-raster runner for campaign-scale launches.

## Final Recommendation

Do not optimize the current local batch runner much further.

The durable path is:

- grouped generation in MOS
- Nano Banana 2 kept as the default render model
- shared prompt/context work once per logical ad
- sibling aspect ratios rendered in parallel
- MOS-owned checkpointing, retries, and review packaging

That architecture is compatible with the current Nano Banana default path, compatible with the existing Higgsfield Nano Banana path, and does not depend on GPT Image 2.
