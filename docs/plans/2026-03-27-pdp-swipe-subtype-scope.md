## Decision

Add `pdp` as a brief-level subtype and enforce uniqueness at plan-build time, not with a prompt-only tweak. Keep the full workspace-aware swipe context for PDP, but branch the prompt and post-render behavior so PDP does not inherit ad-only assumptions.

## Why The Current Flow Cannot Enforce PDP Uniqueness

- The brief schema has no subtype or set-level PDP context today in [asset_brief.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/schemas/asset_brief.py#L15).
- Plan items have no room for per-image slot assignment, `mustCover`, or `avoidRepeating` metadata in [creative_generation.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/schemas/creative_generation.py#L42).
- The current planner clones the same requirement and copy-pack dependency across every swipe source in [asset_activities.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/asset_activities.py#L1278).
- The stage-one prompt input only injects brand, angle, and destination context in [swipe_image_ad_activities.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/swipe_image_ad_activities.py#L1743).
- Workspace mode always resolves linked ad copy pack context and always runs rendered-asset swipe copy generation in [swipe_image_ad_activities.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/swipe_image_ad_activities.py#L3701) and [swipe_image_ad_activities.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/swipe_image_ad_activities.py#L3941).
- The active prompt template is explicitly high-CTR and direct-response ad oriented in [swipe_to_image_ad.md](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/prompts/swipe/swipe_to_image_ad.md#L1).

## Recommended PDP Design

- Add `AssetBrief.subtype`, defaulting to `ad`, with new value `pdp`.
- Add a brief-level `pdpContext` block. Minimum useful fields:
  - `seriesGoal`
  - `coverageSlots`
  - `globalRules`
  - `dedupeAxes`
  - `allowRepeatedCoreAngle`
- Keep `requirements` as the output-format requirement layer. Do not overload `format` for this. `format` is already validated as the asset type in [experiment_activities.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/experiment_activities.py#L1399).
- Assign one ordered PDP slot per swipe source during creative-plan creation. Example slot families for an 8-image set:
  - hero/value prop
  - benefit stack
  - lifestyle/performance
  - product close-up or gummy detail
  - social proof
  - trust or certifications
  - flavor or ingredients
  - supplement facts or how to use
- Persist slot-level fields onto each `CreativeGenerationPlanItem`:
  - `subtype`
  - `slotKey`
  - `slotObjective`
  - `mustCover`
  - `avoidRepeating`
  - `setPosition`
  - `setSize`
- For PDP, keep the full workspace RAG and document context. The thing to remove is ad-only behavior, not workspace context.

## Prompting And Execution Changes

- Replace the fixed prompt loader in [swipe_prompt.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/swipe_prompt.py#L11) with subtype-aware prompt selection.
- Add a dedicated PDP prompt file rather than stuffing exceptions into the ad prompt. The current template in [swipe_to_image_ad.md](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/prompts/swipe/swipe_to_image_ad.md#L1) is too ad-specific.
- Extend the stage-one runtime input in [swipe_image_ad_activities.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/swipe_image_ad_activities.py#L1743) so PDP runs receive:
  - slot objective
  - required topics
  - forbidden repeated topics
  - sibling-set position context
  - an explicit PDP rule like “do not restate already-covered proof or benefits unless the slot requires it”
- For PDP subtype, skip rendered-asset swipe copy generation in [swipe_image_ad_activities.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/swipe_image_ad_activities.py#L3941). That path is direct-response ad copy, not PDP review content.
- Remove the mandatory ad-copy-pack dependency for PDP planning in [asset_activities.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/asset_activities.py#L1296). Right now that dependency forces ad semantics into the set.

## Code Surface

- Brief schema: [asset_brief.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/schemas/asset_brief.py#L15)
- Plan schema: [creative_generation.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/schemas/creative_generation.py#L42)
- Plan builder: [asset_activities.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/asset_activities.py#L1209)
- Ad copy pack builder to branch for PDP: [asset_activities.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/asset_activities.py#L1062)
- Prompt loader: [swipe_prompt.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/swipe_prompt.py#L11)
- Swipe execution: [swipe_image_ad_activities.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/swipe_image_ad_activities.py#L3385)
- Workflow and request surfaces if direct manual PDP runs should understand subtype too: [swipe_image_ads.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/schemas/swipe_image_ads.py#L8), [swipe_image_ad.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/workflows/swipe_image_ad.py#L15), [swipes.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/routers/swipes.py#L976)
- Brief generation path if subtype should be authored upstream: [experiment_activities.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/experiment_activities.py#L1427)

## Rollout

1. Add `subtype` and `pdpContext` to brief and plan schemas.
2. Implement PDP slot assignment in the creative-generation plan.
3. Add subtype-aware prompt loading and a dedicated PDP prompt.
4. Branch swipe execution so PDP skips rendered-asset ad-copy generation.
5. Persist PDP slot metadata into generated asset provenance for review. The current annotation point is [asset_activities.py](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/activities/asset_activities.py#L420).
6. Validate on one 8-image PDP set and check that each output’s metadata shows a distinct slot and exclusion list.

## Main Risk

If we only add “do not repeat info” to the prompt and leave planning untouched, the system will still fan out nearly identical requirement context to every swipe source. That would look like a PDP subtype on paper, but it would behave like the current ad flow with a weaker instruction.
