# Swipe Flow Refactor Plan: Use Rendered Ad As Swipe Copy Input

Date: March 17, 2026

## Objective

Refactor the swipe image ad pipeline so that `swipeCopyPack` is generated from the final rendered ad image, not from the competitor source swipe.

The core requirement is simple:

- source swipe remains the visual reference for image generation
- rendered ad becomes the visual input for swipe-specific copy generation
- campaign creative specs are created from the post-render `swipeCopyPack`

More explicitly:

- the image currently treated as the swipe-copy image input must no longer be the original competitor swipe
- the swipe-copy image input must be the generated ad image for that specific asset
- the original swipe must remain in the pipeline only as source provenance and render inspiration

This plan intentionally does **not** introduce a separate policy layer of heuristic rules such as matching "promise, audience, and mechanism framing." The primary fix is sequencing and source-of-truth, not more copy-review rules.

## Current Problem

Today the pipeline does these steps in the wrong order:

1. Load the source swipe image.
2. Generate `swipeCopyPack` from the source swipe image.
3. Generate the render prompt from the source swipe image.
4. Render the ad image.
5. Store both branches in asset metadata.
6. Use `swipeCopyPack` to build the campaign creative spec.

That means the source swipe is used as the image input for copy, while the rendered ad is used only as the image output.

The result is predictable:

- copy can stay semantically tied to the competitor swipe
- rendered image can shift toward the brand/product context
- campaign creative spec inherits the source-swipe-driven copy
- no step forces the copy branch to be regenerated from the rendered asset

## Code Reality Today

The current behavior is visible in these places:

- swipe copy prompt builder: [swipe_image_ad_activities.py:1676](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/swipe_image_ad_activities.py#L1676)
- swipe copy generation helper: [swipe_image_ad_activities.py:2209](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/swipe_image_ad_activities.py#L2209)
- pre-render swipe copy call inside the activity: [swipe_image_ad_activities.py:2770](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/swipe_image_ad_activities.py#L2770)
- render prompt generation starts after that: [swipe_image_ad_activities.py:2820](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/swipe_image_ad_activities.py#L2820)
- rendered asset metadata persists both `promptUsed` and `swipeCopyPack`: [swipe_image_ad_activities.py:2994](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/swipe_image_ad_activities.py#L2994)
- campaign Meta review creates specs directly from `swipeCopyPack`: [campaigns.py:1216](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/routers/campaigns.py#L1216)

## Desired Future Flow

Steps 1 through 4 do not need to change. They can stay exactly as they are in the current flow:

1. Load the source swipe image.
2. Build the render prompt from the source swipe image and project context.
3. Render the final ad image.
4. Download the rendered ad image bytes.

The required changes begin only after the rendered ad is available:

5. Generate `swipeCopyPack` from the rendered ad image plus project context.
6. Persist the rendered asset and its post-render `swipeCopyPack`.
7. Create campaign creative specs from that post-render `swipeCopyPack`.

This is a targeted post-render refactor, not a redesign of the upstream swipe-to-image flow.

This changes one architectural fact:

- `swipeCopyPack` becomes a post-render artifact

It is no longer a pre-render sibling of image generation.

## Minimal Change Set

The minimum required product change is only these three steps:

1. Generate `swipeCopyPack` from the rendered ad image plus project context.
2. Persist the rendered asset together with that post-render `swipeCopyPack`.
3. Create campaign creative specs from that post-render `swipeCopyPack`.

Everything before that can remain structurally the same unless a small local implementation detail needs to move.

## Terminology Correction

Part of the confusion in the current flow is naming.

Today, the image effectively acting as the "swipe image" inside swipe-specific copy generation is the original competitor swipe.

That should change.

In the future flow:

- the image passed into swipe-specific copy generation should be the generated ad
- the original swipe should be stored separately as `sourceSwipe` provenance
- any field or variable that still means "image used for swipe-specific copy generation" must point to the generated ad, not the original swipe

If the current names are kept for backward compatibility, their semantics still need to change.

That means:

- `swipeCopyInputs.adImageOrVideo` should refer to the generated ad
- any future `swipe_image_url` used by the swipe-copy stage should refer to the generated ad
- the original swipe should never again appear as the active image input for `swipeCopyPack`

## What Stays The Same

These parts do not need to change:

- `ad_copy_pack` remains the requirement-level baseline copy artifact
- source swipes still drive visual adaptation and render prompt generation
- the existing asset brief, campaign docs, product docs, and Gemini File Search context remain relevant
- render providers and render model selection do not need to change

The refactor is about when and from what image `swipeCopyPack` is generated.

## High-Level Refactor Strategy

The refactor should be implemented in four layers:

1. move swipe copy generation to the post-render boundary
2. change the swipe-copy input contract
3. persist new provenance metadata
4. update downstream consumers to expect rendered-asset-based copy

## Layer 1: Move Swipe Copy Generation To Post-Render

The central change belongs in [swipe_image_ad_activities.py:2460](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/swipe_image_ad_activities.py#L2460).

Steps 1 through 4 should remain materially unchanged:

- resolve swipe and docs
- generate render prompt
- render image
- download/store rendered output as already required by the flow

The change should happen only after a rendered output exists.

Current post-render behavior:

- persist the asset using a `swipeCopyPack` that was already generated from the source swipe

Target post-render behavior:

- for each rendered output:
- download rendered output image
- generate swipe copy from that rendered output
- persist asset with post-render swipe copy metadata

Two implementation rules matter here:

- do not pass the source swipe image into post-render swipe copy generation
- do not create a generated asset row that lacks its final `swipeCopyPack`

The cleanest behavior is to fail the activity if post-render swipe copy generation fails. That keeps the invariant simple and avoids half-finished assets.

## Layer 2: Make Swipe Copy Per Output, Not Per Job

This is a necessary structural change.

Today the flow generates one `swipeCopyPack` before the render loop and then reuses it for every output.

That will be wrong in the new design because rendered outputs can differ from one another. Once swipe copy depends on the rendered asset, each output needs its own copy generation pass.

The per-output loop already exists in [swipe_image_ad_activities.py:2988](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/swipe_image_ad_activities.py#L2988). The new swipe-copy generation should happen inside that loop.

This gives the correct ownership model:

- one rendered output image
- one post-render `swipeCopyPack`
- one stored generated asset

## Layer 3: Replace The Swipe Copy Prompt Builder

The existing `_build_swipe_copy_stage1_prompt(...)` helper should be replaced by a post-render prompt builder.

Recommended rename:

- `_build_rendered_asset_swipe_copy_prompt(...)`

The new prompt inputs should be:

- platform
- rendered ad image attachment
- requirement metadata
- destination type
- asset brief context
- relevant project docs
- linked `ad_copy_pack` item for the same requirement
- optional product reference image, only if it is already part of the current copy context strategy

The new prompt should not include:

- source swipe URL as the ad image input
- source swipe label as the ad image input
- competitor swipe image bytes as the visual copy input

The source swipe can still be mentioned in provenance metadata, but it should not be the image the copy model sees when generating the asset-specific copy.

## Layer 4: Keep `ad_copy_pack` As The Product Baseline

This refactor should not remove the earlier `ad_copy_pack` stage.

That artifact is still valuable because it provides:

- requirement-level product truth
- requirement-level angle framing
- requirement-level Meta copy baseline
- a stable project-grounded anchor that is less likely to drift toward competitor text

The best post-render copy generation input mix is:

- rendered image for creative specificity
- `ad_copy_pack` item for product grounding
- brief/docs for campaign grounding

That is materially better than the current mix of:

- source swipe image
- brief/docs

## Layer 5: Change Metadata Shape And Provenance

The current metadata keys are ambiguous because `swipeCopyInputs.adImageOrVideo` points to the source swipe.

That should change.

I recommend introducing a versioned metadata contract such as:

```json
{
  "swipeCopyPipelineVersion": 2,
  "swipeCopyInputs": {
    "platform": "Meta",
    "adImageOrVideo": {
      "sourceKind": "rendered_output",
      "assetType": "image",
      "sourceUrl": "<rendered output url>",
      "storageKey": "<generated asset storage key>",
      "mimeType": "image/png"
    },
    "angleUsed": "...",
    "destinationPage": "...",
    "adCopyPackId": "...",
    "sourceSwipe": {
      "companySwipeId": "...",
      "sourceLabel": "...",
      "sourceUrl": "..."
    }
  }
}
```

The important change is semantic, not cosmetic:

- `adImageOrVideo` must point to the rendered output
- source swipe must move into a provenance block

This is the single most important metadata correction in the refactor.

Said another way:

- the field that the copy flow considers the swipe image must now be the generated ad
- the field must not point at the original competitor swipe under the new flow

## Layer 6: Add A Typed Model For Swipe Copy Inputs

`SwipeAdCopyPack` already has a typed schema in [creative_generation.py:87](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/schemas/creative_generation.py#L87). `swipeCopyInputs` does not.

That should be fixed.

I recommend adding:

- `SwipeCopyInputMedia`
- `SwipeCopySourceSwipeProvenance`
- `SwipeCopyInputs`

Benefits:

- explicit source kind validation
- cleaner router checks
- easier forensic exports
- less chance of silently persisting invalid metadata

## Layer 7: Update Downstream Campaign Review

The campaign router in [campaigns.py:1216](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/routers/campaigns.py#L1216) currently assumes that any `swipeCopyPack` in asset metadata is usable for Meta review.

That assumption should change.

The router should require that:

- `swipeCopyInputs` exists
- `swipeCopyInputs.adImageOrVideo.sourceKind == "rendered_output"`
- the input image URL or storage key belongs to the rendered generated asset, not the source swipe

This is not adding heuristic review rules. It is simply enforcing that the copy being used downstream was actually generated from the correct image source.

## Layer 8: Improve Forensics And Debuggability

The refactor should also improve what we persist for later review.

For each generated asset, persist:

- rendered image input metadata used for copy generation
- post-render swipe-copy prompt text
- post-render swipe-copy prompt SHA
- linked `ad_copy_pack` id
- source swipe provenance
- render prompt used
- model name used for post-render copy generation

This will make future forensic review precise:

- which image produced the copy
- which prompt produced the copy
- which product-level copy artifact grounded the copy
- which source swipe inspired the image

## Optional Readback Layer

A rendered-image text readback step can be useful, but it should be treated as a support and observability layer, not the primary fix.

Why optional:

- the main problem is wrong image provenance
- once the model sees the rendered ad instead of the source swipe, the core mismatch source is removed

Why still useful:

- it helps future forensic review
- it provides visibility into what text is actually visible in the generated ad
- it can help explain why copy drift still happens if a rendered ad is visually ambiguous

If implemented, this readback data should be stored in metadata. It does not need to be used as a separate heuristic approval rule in the first version of the refactor.

## Proposed Implementation Phases

### Phase 1: Post-Render Copy Refactor

Make only the minimum architectural change after render completes:

- remove pre-render swipe copy generation
- generate swipe copy per rendered output
- persist output-level `swipeCopyPack`

Deliverable:

- new assets always have `swipeCopyInputs.adImageOrVideo.sourceKind = rendered_output`
- steps 1 through 4 of the swipe-to-image flow remain materially unchanged

### Phase 2: Schema And Router Hardening

Add typed metadata models and update campaign review setup to require the new provenance.

Deliverable:

- Meta review cannot create a spec from a source-swipe-based `swipeCopyPack`

### Phase 3: Forensic Improvements

Persist the post-render swipe copy prompt and show the new lineage in the forensic report.

Deliverable:

- review UI clearly shows source swipe, rendered asset, and which one actually drove the copy

### Phase 4: Historical Backfill

Create a backfill script for existing assets whose swipe copy was generated from the source swipe.

Backfill criteria:

- `swipeCopyInputs.adImageOrVideo.sourceUrl == swipeSourceUrl`
- or missing `sourceKind`
- or `sourceKind != rendered_output`

Backfill behavior:

- download the stored generated asset
- regenerate `swipeCopyPack` from that generated asset
- write updated metadata
- produce a diff report against the previous campaign creative spec

This should be a deliberate migration step, not an on-the-fly fallback.

## Suggested File Changes

Primary files:

- [swipe_image_ad_activities.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/swipe_image_ad_activities.py)
- [creative_generation.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/schemas/creative_generation.py)
- [campaigns.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/routers/campaigns.py)

Secondary files:

- [swipe_image_ad.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/workflows/swipe_image_ad.py)
- [asset_activities.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/asset_activities.py)
- [export_campaign_forensic_review.py](/Users/aldrinclement/Documents/programming/marketi/scripts/export_campaign_forensic_review.py)
- [render_campaign_forensic_marketer_view.py](/Users/aldrinclement/Documents/programming/marketi/scripts/render_campaign_forensic_marketer_view.py)

## Recommended Function-Level Changes

1. Replace `_generate_swipe_stage1_copy_pack(...)` with a post-render helper.

2. Replace `_build_swipe_copy_stage1_prompt(...)` with a rendered-asset prompt builder.

3. Move `swipeCopyPack` generation into the rendered output loop.

4. Move `swipeCopyInputs.adImageOrVideo` to rendered-output provenance.

5. Add typed metadata models for swipe copy input provenance.

6. Update the campaign router to require rendered-output provenance.

7. Rename internal variables where needed so the distinction is obvious in code:

- `source_swipe_*` should always refer to the competitor reference
- `rendered_ad_*` should always refer to the generated asset used for swipe-specific copy generation
- avoid reusing `swipe_*` names for both concepts in the same function

## Testing Plan

### Unit Tests

Add tests that confirm:

- the post-render swipe copy prompt references the rendered asset, not the source swipe
- `swipeCopyInputs.adImageOrVideo.sourceKind` is `rendered_output`
- source swipe provenance is stored separately
- the correct `ad_copy_pack` item is attached to the post-render copy context

### Integration Tests

Add a regression case matching the failure already observed:

- source swipe text is about Hashimoto's
- rendered ad text is about Herb-Drug Safety Checker
- final `swipeCopyPack` follows the rendered asset, not the source swipe
- Meta review setup creates a creative spec from that rendered-asset-based copy

### Backfill Validation

For migrated assets, validate:

- old `swipeCopyPack`
- new `swipeCopyPack`
- old campaign creative spec
- proposed updated campaign creative spec

This should be reported explicitly so review is easy.

## Risks

### Longer Per-Asset Generation Time

Swipe copy generation moves after render and becomes per-output. That increases latency for multi-output jobs.

This is acceptable because the previous design was materially incorrect.

### Count Greater Than 1

If a single render job returns multiple outputs, each output now requires its own swipe copy generation call.

This is correct behavior, but it increases cost and duration linearly with output count.

### Migration Complexity

Historical assets already persisted the old provenance model. They will need a backfill path if you want the campaign review layer to be consistent across old and new assets.

## Non-Goals

This refactor does not require:

- changing the current LLM model selection
- changing render models
- removing the `ad_copy_pack` stage
- inventing extra fallback behavior
- adding a separate heuristic content-policing layer as the primary fix

## Final Recommendation

The refactor should be approved around one principle:

- the image used to generate `swipeCopyPack` must be the rendered ad, not the source swipe

Everything else in this plan supports that one principle.

If implemented this way, the system will still keep full competitor-swipe provenance, but the campaign copy branch will finally be grounded in the asset that is actually going live.
