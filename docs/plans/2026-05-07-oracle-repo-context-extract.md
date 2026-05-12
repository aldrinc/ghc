# Oracle repo context extract: animated swipe GIF template engine

Date: 2026-05-07

Purpose: supplement the raw files attached to Oracle with focused context from very large files and the prior visual investigation. This file is not a replacement for source code. It is a compressed index of the parts that matter for adding deterministic animated GIF/template support to the existing swipe image flow.

## Product decision from the investigation

The prompt-only approach is not sufficient for this requirement. The Sora 2 trial against the MARS energy-level chart produced visible template drift:

- extra graph points that were not in the source template
- extra text such as an added `WITH TENOR` phrase where the source did not have it
- incorrect color treatment for the line, including white/yellow artifacts instead of the brand red
- axis labels changed size and placement
- the vertical `ENERGY LEVEL` label was flipped/scaled incorrectly
- a Tenor product image was inserted even though the source chart template had no competitor product slot

The resulting architecture should treat animated swipe recreation as a deterministic template-editing/rendering system with optional AI only for masked generative regions. The model should not be responsible for locked text, chart geometry, axis labels, product-slot eligibility, colors, timing, or layout.

## Source page and media context

Target page: https://mengotomars.com/pages/10-reasons-glp-shop

Extracted media from the page included ten listicle visual assets. Seven were animated GIFs and three were static WebP assets.

Observed animated assets:

- item 01: GIF, 1368x1368, 2.4 seconds, 2 frames
- item 03: GIF, 672x672, 4.8 seconds, 4 frames
- item 04: GIF, 798x798, 2.9 seconds, 29 frames
- item 05: GIF, 996x996, 2.86 seconds, 16 frames
- item 07: GIF, 672x672, 7.2 seconds, 7 frames
- item 09: GIF, 1008x1008, 4.8 seconds, 4 frames
- item 10: GIF, 672x672, 2.8 seconds, 14 frames

Static assets:

- item 02: static WebP
- item 06: static WebP
- item 08: static WebP

The tested source item 05 is an animated chart. It contains text such as `ENERGY LEVEL`, `NORMAL CRASH`, `TIME OF DAY`, `6AM`, `12PM`, `6PM`, and later `WITH MARS MEN`. It does not contain a competitor product packshot. Therefore a Tenor product bottle should not be inserted into this template. Only brand-copy replacement is eligible.

Local investigation artifacts from the prior run:

- extracted page media directory: `/tmp/mars-glp-media`
- Sora test directory: `/tmp/tenor-sora2-test`
- source item 05 frames: `/tmp/tenor-sora2-test/source05/frame-001.png` and siblings
- Sora 2 output video: `/tmp/tenor-sora2-test/sora2_item05_tenor.mp4`
- center-square converted GIF: `/tmp/tenor-sora2-test/sora2_item05_tenor_center_square.gif`
- Sora prompt: `/tmp/tenor-sora2-test/prompt_item05_sora2.txt`

## Tenor product context

Brand/product page: https://shoptenorco.com/8b89a76d/daily-drive-essentials/sales-page/

Observed product facts from the page JSON-LD during investigation:

- brand: Tenor
- product: Daily Drive Essentials
- description: physician-formulated men's vitality protocol with 21 disclosed active ingredients in 2 vegan capsules daily to support drive, stamina, energy, focus, and hormonal balance
- product imagery exists on the page, including `tenor-bottle-thumb-46f673f782.webp` and carousel/main product assets

Product imagery should only be used when the template manifest proves the original swipe has an equivalent competitor product slot. The existence of a brand product reference is not enough to insert the product into every template.

## Existing swipe image flow

The current static swipe image adaptation flow is documented in `docs/swipe-image-add-flow.md`.

Important backend path:

- `POST /swipes/generate-image-ad` in `mos/backend/app/routers/swipes.py`
- request/response schemas in `mos/backend/app/schemas/swipe_image_ads.py`
- Temporal workflow in `mos/backend/app/temporal/workflows/swipe_image_ad.py`
- core activity in `mos/backend/app/temporal/activities/swipe_image_ad_activities.py`
- stage-one prompt builder context in `mos/backend/app/services/swipe_prompt.py`
- stage-one prompt template in `mos/backend/app/prompts/swipe/swipe_to_image_ad.md`
- static renderer client in `mos/backend/app/services/image_render_client.py`
- storage/persistence in `mos/backend/app/services/media_storage.py`, `mos/backend/app/services/assets.py`, `mos/backend/app/db/repositories/swipes.py`, and relevant DB models

The current static flow has a two-stage model split:

- `model` is the stage-one Gemini prompt-generation model with File Search/RAG support.
- `renderModelId` is the final image-rendering model.
- `SwipeImageAdGenerateRequest` rejects image-rendering model names in `model` and tells callers to use `renderModelId`.

This split should be preserved. Animated generation should introduce explicit animated template fields rather than repurposing static image fields ambiguously.

## Existing generic video flow

There is an existing creative service video path in:

- `mos/backend/app/services/creative_service_client.py`
- `mos/backend/app/services/video_ads_orchestrator.py`
- `mos/backend/app/temporal/activities/asset_activities.py`

This path supports `final_video` outputs and persistence but does not understand GIF templates, template manifests, deterministic layer locking, frame extraction, or GIF/WebP animation export. It can be reused for remote model execution if the implementation adds a deterministic template layer around it, but it should not be treated as sufficient by itself.

## Current explicit limitation for non-static swipe assets

`mos/backend/app/temporal/activities/asset_activities.py` currently rejects selected swipe collection assets that are not static for image creative generation:

- relevant area: around lines 650-685
- observed error text: `Selected swipe collection contains non-static assets that are not supported for image creative generation yet.`

The animated implementation must remove or narrow this limitation only for the new animated path. It should not silently route GIF/video assets through the static image generator.

## Relevant large database model map

`mos/backend/app/db/models.py` is very large. The classes below are the relevant persistence surface for this plan:

- `Artifact` begins around line 828
- `Asset` begins around line 1377
- `CreativeServiceRun` begins around line 1441
- `CreativeServiceOutput` begins around line 1564
- `CompanySwipeBrand` begins around line 1959
- `CompanySwipeAsset` begins around line 1979
- `CompanySwipeMedia` begins around line 2101
- `SwipeCollection` begins around line 2140
- `SwipeCollectionItem` begins around line 2161
- `ClientSwipeAsset` begins around line 2185

Implementation should decide whether to extend existing JSON metadata fields and asset kinds first, or add new typed tables only when necessary. The near-term implementation likely needs:

- an asset/output representation for animated generated assets
- a template-manifest artifact or DB-backed record
- provenance linking source swipe media, extracted frames, manifest, edits, rendered animation, and quality report
- review UI data that can expose both source and generated animated assets

## Relevant large activity map

`mos/backend/app/temporal/activities/asset_activities.py` contains these relevant regions:

- `_extract_requirement_swipe_source` around line 167
- selected swipe collection non-static rejection around lines 650-685
- `_record_output` around line 1392
- `_get_existing_run_by_idempotency` around line 1425
- `_create_generated_asset_from_url` around line 1756
- requirement/source extraction around line 2063
- video path begins around line 2335
- idempotent video run handling around lines 2385-2401
- final video handling around lines 2539-2591
- pin asset creation around lines 2624-2651

`mos/backend/app/temporal/activities/swipe_image_ad_activities.py` contains these relevant regions:

- image render client imports around lines 55-57
- model guard `_is_image_render_model_name` around line 636
- product-image requirement resolution around lines 589-601
- source product reference instructions around lines 821-832
- claim avoidance block around lines 901-910
- current activity docstring around lines 3538-3541
- model-name guard around lines 3589-3592
- render provider/client creation around lines 3640-3667
- source image resolution around lines 3720-3737
- product reference resolution and clean errors around lines 3750-3770
- product prompt image source handling around lines 3884-3890
- Gemini stage-one prompt generation around lines 3897-3976
- render request/output area around lines 4000-4075
- copy generation from rendered output around lines 4107-4133
- metadata persistence around lines 4138-4265

## Deterministic implementation requirement

The implementation should explicitly separate these responsibilities:

- template capture: download source GIF/static image, decode frames, read timing, normalize dimensions, detect candidate layers
- manifest creation: produce a strict JSON manifest describing locked layers, editable layers, masks, text elements, charts, product slots, color tokens, timing, export settings, and source evidence
- human review/editing: allow users to inspect and approve/correct the manifest before generation where needed
- product-slot gating: only allow product insertion if a competitor product region is detected and recorded with evidence in the manifest
- deterministic rendering: use a local renderer to draw text, charts, overlays, product placements, masks, frame timing, and GIF/WebP/video export exactly from the manifest
- AI generation: only generate or edit masked regions explicitly marked as `ai_editable`
- QA: compare output to source/template using structural checks, OCR/text checks, color checks, frame count/timing checks, geometry checks, and product-slot policy checks

## Generic template types

This must not be table/chart-specific. The plan should handle at least:

- static and animated charts
- before/after or transition frames
- text overlays on lifestyle footage
- product demonstrations
- countdowns or sequential list animations
- UI screenshots or app-like animations
- meme/reaction style GIFs
- packshot swaps where the source actually contains a competitor packshot
- mixed media with locked background and editable text/product regions

## Output contract for the desired Oracle plan

The desired Oracle answer should be an implementation plan, not executable code. It should go module by module and include:

- backend APIs and schemas
- database/persistence changes
- Temporal workflows/activities
- manifest schema
- renderer architecture
- model provider boundaries
- frontend UX
- QA/evaluation
- migration and rollout
- testing
- observability
- cost tracking
- risks and implementation phases

The answer should strongly avoid a prompt-only solution. It should also avoid unauthorized model fallbacks. If a selected model cannot produce a required region, the system should return a clean error.
