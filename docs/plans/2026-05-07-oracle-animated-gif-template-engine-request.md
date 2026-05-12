# Oracle Request: Animated GIF Template Engine End-To-End Plan

You are GPT-5.5 Pro Extended reviewing the MOS codebase through Oracle. Produce a minimum 20,000-word implementation plan for an end-to-end animated GIF/template engine that can recreate arbitrary source template GIFs with high fidelity while safely applying brand/product modifications.

## Project Brief

Repository: `/Users/auggieclement/Documents/GitHub/ghc`

Product area: MOS creative generation, swipe image flow, asset briefs, creative production, creative service integrations, media storage, and campaign review UI.

Current problem:

- We have an existing swipe-image flow that adapts competitor swipe images into static generated image ads.
- We need an animated image/GIF equivalent, but prompt-only AI generation drifted away from the source template.
- The first Sora 2 test for a Mars Men listicle chart GIF generated extra chart points, duplicated `WITH TENOR`, changed brand colors, changed axis label sizing/orientation, and inserted a Tenor product bottle even though the source template did not contain a product.
- The desired solution must not be brittle and must work with any source template GIF family, not just charts/tables.

Critical user requirement:

- The system must remain very similar to the source template image/GIF.
- Allowed changes: brand, product, approved copy, and approved compliance-safe substitutions.
- Product replacement must happen only if the source template contains a competitor product slot. Do not insert product just because product imagery is available.
- The generic solution must be deterministic for template-locked elements.
- We should not rely on a model to render text, charts, badges, product placements, UI chrome, exact colors, or timing when those must match the source.

## Existing Findings From Local Analysis

The current static swipe flow:

- Endpoint: `POST /swipes/generate-image-ad`.
- Request schema: `SwipeImageAdGenerateRequest`.
- Stage 1 model field is for Gemini prompt generation only.
- `renderModelId` is for the final static image renderer.
- Stage 1 uses Gemini vision + File Search context to generate a dense static image prompt.
- Stage 2 sends only the extracted prompt to a renderer and persists static image assets.
- Current image render clients support static outputs, not animated GIF generation.

Existing generic video flow:

- There is a creative service video session path.
- It can produce `final_video`.
- It is generic ad-video generation and does not treat a source GIF as a strict template.
- It does not extract source GIF timing/layers/masks, does not deterministically overlay source-matched text/charts/UI, and does not convert/composite final animated GIF/WebP outputs.

New architecture direction already drafted locally:

- Use a template manifest.
- Detect/classify layers.
- Lock deterministic layers.
- Allow AI only for masked generative regions.
- Composite final GIF/animated WebP with deterministic renderer.
- Add manifest preview/review before paid model calls.

Your job is to make this implementable in this codebase.

## Required Output

Produce a detailed implementation plan with at least 20,000 words. Do not summarize. Be concrete and module-by-module.

Required structure:

1. Executive decision and architecture thesis.
2. Existing system analysis, referencing the attached files by path and function/class/module names.
3. End-to-end target workflow, including user-facing and backend/Temporal flows.
4. Data model plan.
   - New DB tables or columns.
   - SQLAlchemy model sketches.
   - Migration plan.
   - Retention/cleanup.
   - Idempotency.
5. Manifest schema.
   - Full JSON schema sketch.
   - Layer policies.
   - Product-slot evidence model.
   - Color role model.
   - Text role model.
   - Motion/timing model.
   - Mask/source-frame model.
   - Validation rules.
6. Ingestion and analysis pipeline.
   - Source GIF/video download.
   - ffprobe/ffmpeg metadata extraction.
   - frame sampling.
   - OCR.
   - object/product/logo detection.
   - chart/path extraction.
   - UI chrome detection.
   - motion tracking.
   - confidence and review gating.
7. Deterministic renderer.
   - Rendering technology recommendation.
   - Python/OpenCV/Pillow vs Node/canvas vs ffmpeg filtergraph vs browser/canvas tradeoffs.
   - Text rendering fidelity.
   - SVG/vector layer handling.
   - Chart/path animation.
   - Masks.
   - GIF/WebP/MP4 export.
   - Color management.
   - Font handling.
8. AI model integration.
   - When to call Sora/Veo/image models.
   - How to pass masked references.
   - How to avoid model-rendered text/charts/products.
   - Cost accounting.
   - Provider abstraction.
   - No fallback model switching unless explicitly authorized.
9. Backend module-by-module implementation plan.
   - `mos/backend/app/routers/swipes.py`
   - `mos/backend/app/schemas/swipe_image_ads.py`
   - new schemas for animated templates
   - `swipe_image_ad_activities.py`
   - `asset_activities.py`
   - `creative_service_client.py`
   - `video_ads_orchestrator.py`
   - `image_render_client.py`
   - media storage
   - repositories
   - workflows
   - config/env
   - observability/logging
   - tests
10. Frontend module-by-module implementation plan.
   - campaign creative generation UI.
   - swipe library UI.
   - manifest preview/review UI.
   - generated asset review UI.
   - diff/contact-sheet UI.
   - typed API clients.
11. API contract plan.
   - Request/response shapes.
   - Preview/approval endpoints.
   - Run/status/result endpoints.
   - Error shapes.
   - Cost estimate endpoint.
12. Temporal workflow/activity plan.
   - Activity boundaries.
   - Retry policy.
   - idempotency keys.
   - artifact persistence.
   - failure modes.
13. QA and scoring plan.
   - Automated metrics.
   - visual diff.
   - source-vs-output contact sheets.
   - compliance checks.
   - human review.
14. Rollout plan.
   - behind flags.
   - deterministic chart template pilot.
   - product/badge pilot.
   - customer collage pilot.
   - UGC/lifestyle pilot.
   - migration to production creative generation.
15. Risks and mitigations.
16. Implementation milestones with detailed acceptance criteria.
17. Open questions.
18. Concrete file-by-file change list.

## Non-Negotiable Constraints

- Do not propose silent fallbacks.
- Do not switch models automatically if one was selected.
- Prefer clean, well-described errors over guessing.
- Do not create fake data.
- Product placement requires source product-slot evidence.
- Locked layers must not be rendered by AI.
- The output should be optimized for human review speed.

## Attached File Map

Read all attached files. They include the current static swipe flow, video flow, media storage, creative service schemas, frontend review/generation UI, and the local proposal docs.

Important local docs:

- `docs/plans/2026-05-07-animated-gif-template-engine-solution.md`
- `docs/plans/2026-05-07-animated-swipe-gif-model-comparison-prompt.md`
- `docs/swipe-image-add-flow.md`

Important backend files:

- `mos/backend/app/routers/swipes.py`
- `mos/backend/app/schemas/swipe_image_ads.py`
- `mos/backend/app/schemas/asset_brief.py`
- `mos/backend/app/schemas/asset_brief_types.py`
- `mos/backend/app/schemas/creative_generation.py`
- `mos/backend/app/schemas/creative_service.py`
- `mos/backend/app/schemas/swipe_assets.py`
- `mos/backend/app/services/swipe_prompt.py`
- `mos/backend/app/prompts/swipe/swipe_to_image_ad.md`
- `mos/backend/app/temporal/activities/swipe_image_ad_activities.py`
- `mos/backend/app/temporal/activities/asset_activities.py`
- `mos/backend/app/services/image_render_client.py`
- `mos/backend/app/services/creative_service_client.py`
- `mos/backend/app/services/video_ads_orchestrator.py`
- `mos/backend/app/services/media_storage.py`
- `mos/backend/app/services/assets.py`
- `mos/backend/app/db/repositories/swipes.py`
- `mos/backend/app/db/models.py`
- `mos/backend/app/config.py`

Important frontend files:

- `mos/frontend/src/api/swipes.ts`
- `mos/frontend/src/api/campaigns.ts`
- `mos/frontend/src/pages/campaigns/tabs/CampaignCreativeTab.tsx`
- `mos/frontend/src/pages/campaigns/CampaignDetailPage.tsx`
- `mos/frontend/src/components/campaigns/SwipeCollectionSelector.tsx`
- `mos/frontend/src/lib/campaignProductionBatch.ts`
- `mos/frontend/src/lib/assetBriefTypes.ts`
- `mos/frontend/src/types/swipes.ts`
- `mos/frontend/src/types/assetReview.ts`
- `mos/frontend/src/lib/assetReviewNormalizers.ts`
- `mos/frontend/src/components/review/AssetReviewGrid.tsx`
- `mos/frontend/src/components/library/SwipeMedia.tsx`

## Special Attention Areas

Please be especially detailed about:

- How to represent a generic animated template manifest without overfitting to chart GIFs.
- How to automatically determine whether a source GIF has a product slot.
- How to make product replacement deterministic and evidence-gated.
- How to handle source templates with charts, counters, social UI screenshots, customer collages, before/after panels, product badge graphics, and UGC/lifestyle motion.
- How to preserve exact text geometry and color roles.
- How to decide when AI is not needed at all.
- How to structure the review checkpoint so humans can quickly approve or correct manifest decisions.
- How to integrate with existing asset brief requirements and selected swipe collections.
- How to avoid breaking the existing static swipe image path.
- How to track cost for model-generated regions separately from deterministic rendering.
- How to produce side-by-side QA artifacts for every generated GIF.

Return the final plan only. Make it long, concrete, and implementation-ready.
