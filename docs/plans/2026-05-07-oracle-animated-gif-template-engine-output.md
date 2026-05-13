# Animated GIF / Template Engine End-to-End Implementation Plan

This plan is grounded in the attached MOS repo/context bundle and the May 7, 2026 local proposal docs for animated swipe GIF generation.

## 1. Executive decision and architecture thesis

Build an **animated template engine**, not an animated prompt generator.

The core product requirement is not “make a new animated ad inspired by a swipe.” The requirement is “recreate the source template with high fidelity while applying only approved brand, product, copy, and compliance-safe substitutions.” The first Sora 2 test already exposed the failure mode that makes prompt-only generation unsuitable for production: it added chart points, duplicated text, changed chart colors, changed label sizing/orientation, and inserted a Tenor bottle despite the source template having no product slot. The attached local proposal correctly identifies this as a renderer-ownership problem, not a prompt-tuning problem: the model treated the source as inspiration, while MOS needs the source to become a locked template.

The implementation should therefore introduce a separate animated-swipe path with these ownership rules:

1. **Template capture is deterministic.** MOS downloads the source GIF/video/static image, hashes it, extracts exact media metadata, extracts frames, records frame delays, and persists source-derived artifacts.

2. **Template structure is represented in a manifest.** Every source is converted into a versioned `animated_template_manifest` that stores source metadata, canvas, timing, layer graph, masks, text boxes, chart paths, product-slot evidence, brand/copy slots, color roles, export settings, and QA expectations.

3. **Locked layers are never delegated to AI.** Text, chart paths, axis labels, counters, UI chrome, badges, logos, product placement geometry, colors, crops, masks, z-order, and timing are rendered by code. The model may only generate pixels inside explicitly approved `generative_region` masks.

4. **Product insertion is evidence-gated.** Product imagery must not be attached to a model or inserted into output unless the approved manifest contains an explicit `product_slot` or `productReplacement.hasCompetitorProductSlot = true` with recorded source evidence. The existence of Tenor product imagery is never enough. The item `05` chart case should render with brand/copy/color changes only and no product packshot.

5. **Review precedes paid generation.** The system must produce a manifest preview and risk summary before any expensive video/image model call. Human review should be required when OCR, product-slot detection, layer tracking, chart extraction, UI chrome detection, or generative mask boundaries are uncertain.

6. **AI is optional, not default.** Many animated swipes, especially charts, counters, text-heavy graphics, badge cards, product cards, and UI screenshots, should be generated without any Sora/Veo/image-model call. A deterministic renderer can render those entirely from source-derived geometry and approved brand/copy tokens.

7. **The output is a deterministic composite.** The final GIF/WebP/MP4 is assembled frame by frame from source-matched backgrounds, deterministic overlays, optional generated region clips, masks, motion curves, and export settings. The final output is not accepted until QA artifacts prove source-template fidelity.

This gives MOS a reusable architecture for charts, tables, UI screenshots, customer collages, product badge graphics, before/after panels, UGC/lifestyle clips, meme-style GIFs, listicle motion cards, and hybrid photographic templates. The same manifest/layer/renderer model supports all template families because the renderer owns generic primitives, not chart-specific concepts.

The near-term engineering decision is:

* Keep the existing static swipe-image path intact.
* Add a new animated-template path beside it.
* Reuse existing MOS primitives where they fit: `WorkflowRun`, `Asset`, `CreativeServiceRun`, `CreativeServiceOutput`, `MediaStorage`, `ArtifactsRepository`, product reference asset selection, campaign creative context, asset brief extraction, and review grid patterns.
* Do not reuse the static path by forcing GIFs through `generate_swipe_image_ad_activity`.
* Do not treat the existing generic video flow as sufficient. It can be reused only for masked generative regions because it does not extract timing/layers/masks, does not deterministically render locked overlays, and does not export animated GIF/WebP composites.

The target architecture is a three-lane system:

**Lane A: static image swipe adaptation.** Existing `POST /swipes/generate-image-ad`, `SwipeImageAdWorkflow`, `generate_swipe_image_ad_activity`, `image_render_client.py`, and persistence stay as-is except for shared helper extraction where useful.

**Lane B: animated template analysis and review.** New endpoints/workflows create, validate, preview, approve, and version `AnimatedTemplateManifest` records. This lane can run before any generation and should often be the only work needed to determine whether a template is renderable.

**Lane C: animated template render/generation.** New endpoints/workflows apply approved brand/product/copy substitutions to an approved manifest, optionally generate masked regions, composite deterministic frames, export GIF/WebP/MP4, persist generated assets, and produce QA contact sheets.

This separation prevents a regression where animated assets accidentally route into the prompt-only image renderer. It also aligns with the repo’s existing preference for explicit model boundaries, strict parsing, and provenance-heavy assets.

## 2. Existing system analysis, by attached path and module

### 2.1 Static swipe-image flow

The current static flow lives primarily in `mos/backend/app/routers/swipes.py`, `mos/backend/app/schemas/swipe_image_ads.py`, `mos/backend/app/temporal/workflows/swipe_image_ad.py`, `mos/backend/app/temporal/activities/swipe_image_ad_activities.py`, `mos/backend/app/services/swipe_prompt.py`, `mos/backend/app/prompts/swipe/swipe_to_image_ad.md`, and `mos/backend/app/services/image_render_client.py`.

The direct backend entrypoint is `POST /swipes/generate-image-ad` in `mos/backend/app/routers/swipes.py`. The route calls `_start_swipe_image_ad_run`, creates a `WorkflowRun` with `kind="swipe_image_ad"`, starts `SwipeImageAdWorkflow`, and passes org/client/product/campaign/brief IDs, swipe source, product-image policy, stage-one model, stage-two render model, aspect ratio, and count. The route’s docstring says the workflow generates a prompt from a competitor swipe image using Gemini vision and File Search, renders final images via the embedded Freestyle renderer, and persists generated assets.

The request schema is `SwipeImageAdGenerateRequest` in `mos/backend/app/schemas/swipe_image_ads.py`. It enforces exactly one of `companySwipeId` or `swipeImageUrl`. It also enforces a critical stage boundary: `model` is only for stage-one prompt generation and must not be an image generation model; image-rendering models belong in `renderModelId`. This model guard is central to the animated plan because animated generation must add explicit animated-template fields rather than overloading static fields.

`mos/backend/app/temporal/workflows/swipe_image_ad.py` defines `SwipeImageAdInput` and `SwipeImageAdWorkflow`. The workflow is intentionally thin: it validates required inputs and forwards everything into `generate_swipe_image_ad_activity` with a single activity retry policy of `maximum_attempts=1`. This pattern is useful for the first animated implementation because a single high-level workflow can still be composed of several activities, but for animated templates the activity boundaries should be more granular than the current static path because analysis, review, AI region generation, rendering, and QA each have different retry/idempotency behavior.

`mos/backend/app/temporal/activities/swipe_image_ad_activities.py` is the static flow’s real implementation. It resolves the swipe source with `_resolve_swipe_image`, resolves product reference policy with `_resolve_swipe_requires_product_image_policy`, loads context from artifacts and design system records, bundles Gemini File Search documents, generates copy packs, calls Gemini for the stage-one prompt, parses a single markdown code block with `extract_new_image_prompt_from_markdown`, sends the extracted prompt to an image renderer, downloads generated outputs, and persists `Asset` rows with rich `ai_metadata`. Its activity docstring explicitly describes the current static flow: Gemini creates a generation-ready prompt, the extracted prompt alone is sent to the renderer, and generated assets are persisted.

`mos/backend/app/services/swipe_prompt.py` provides important reusable behavior. `load_swipe_to_image_ad_prompt` loads the prompt from Agenta or the local markdown file. `extract_new_image_prompt_from_markdown` requires exactly one valid `text` or `markdown` fenced code block. `inline_swipe_render_placeholders` inlines placeholder mappings and rejects unresolved bracket placeholders. The animated implementation should mirror this strict contract for any LLM-produced JSON, but the LLM should produce analysis suggestions or copy options, not the locked final template.

`mos/backend/app/prompts/swipe/swipe_to_image_ad.md` is static-image-specific and instructs the model to produce a dense image prompt. It contains strong preservation rules for design DNA, UI chrome, spatial fidelity, portrait framing, product form factor, and claims. Those rules remain useful as conceptual lineage, but they are insufficient for animated production because the final output still depends on a model to render text, layout, and product placement. The animated path should use a new prompt only for analysis assistance and masked generative regions; it should not ask the model to recreate the full template.

`mos/backend/app/services/image_render_client.py` currently abstracts static image renderers. It maps Gemini render models to `creative_service`, Higgsfield `nano-banana*` models to `higgsfield`, and GPT Image models to `openai`. It exposes `ImageRenderClient.create_image_ads` and `get_image_ads_job`. This should remain a static image client. Animated rendering should not be shoehorned into `ImageRenderClient` because the deterministic renderer must own frame sequences, timing, masks, and multiple export formats.

### 2.2 Product reference selection and the current weakness

The static flow’s current product-image gating is based on explicit request parameter, filename catalog, or optional default behavior. In `generate_swipe_image_ad_activity`, if `resolved_swipe_requires_product_image` is true, `_select_product_reference_assets` is required; if false, product references are omitted; if unknown, product references may be selected if available. That policy is acceptable for static image swipes with curated profiles, but it is not safe enough for arbitrary animated templates.

The animated path must replace “requires product image?” with a stronger manifest-level `product_slot` evidence model:

* A product reference asset may be selected only after the manifest proves a competitor product slot exists.
* Unknown product slot status must not default to “optional product references.” Unknown must become `review_required` or `hasCompetitorProductSlot=false` with no product insertion.
* Product insertion must be blocked when the source template is a chart, table, counter, social UI screenshot, or text-heavy graphic with no product/object evidence.
* Product insertion must be blocked even when the target brand has a primary product asset.

The Mars item `05` source chart is the canonical regression test. The attached context says it contains chart labels and later `WITH MARS MEN`, but no competitor packshot; therefore Tenor Daily Drive Essentials should not appear.

### 2.3 Production creative generation path

The normal UI production flow starts in campaign creative production, not the manual swipe endpoint. `CampaignCreativeTab.tsx` calls `POST /campaigns/{campaign_id}/creative/produce` with selected asset brief IDs and a selected swipe collection ID. The backend eventually runs `generate_assets_for_brief_activity` in `mos/backend/app/temporal/activities/asset_activities.py`. That activity builds an ad copy pack, creates a creative generation plan, then invokes `generate_swipe_image_ad_activity` once per image plan item. The frontend currently requires selecting at least one creative brief and a swipe collection before starting creative production.

`asset_activities.py` currently supports normalized formats `"image"` and `"video"` through `_normalize_requirement_format`, `_SUPPORTED_FORMATS = {"image", "video"}`, and format-specific branches. For image requirements, it creates a `CreativeGenerationPlanArtifact` with `CreativeGenerationPlanItem` rows containing `companySwipeId`, `sourceLabel`, `sourceMediaUrl`, `copyPackId`, `productImagePolicy`, and `sourceSetKey`. For video requirements, it uses `CreativeServiceClient`, uploads product/logo references, and calls `VideoAdsOrchestrator`.

The current `_resolve_collection_swipe_sources` rejects non-static selected swipe assets for image generation with the error: “Selected swipe collection contains non-static assets that are not supported for image creative generation yet.” The animated implementation must narrow this limitation only for the new animated format. Static image requirements should continue to reject non-static sources. Animated requirements should accept GIF/video sources and route to the animated template workflow rather than static image generation.

### 2.4 Generic video flow

`mos/backend/app/schemas/creative_service.py` defines the creative-service video session contracts: `CreativeServiceVideoSessionCreateIn`, `CreativeServiceVideoMessageCreateIn`, `CreativeServiceVideoTurnOut`, `CreativeServiceVideoResultOut`, and `CreativeServiceAssetRef`. `CreativeServiceVideoResultOut` can include `final_video`.

`mos/backend/app/services/creative_service_client.py` already provides `create_video_session`, `create_video_message`, `get_video_turn`, and `get_video_result`, with explicit idempotency keys and structured error handling.

`mos/backend/app/services/video_ads_orchestrator.py` wraps that API in `VideoAdsOrchestrator.run_variant`. It creates a freestyle video session, sends messages for up to `CREATIVE_SERVICE_MAX_VIDEO_TURNS`, polls turns, and returns `VideoVariantResult` when a `final_video.primary_url` appears. This is useful infrastructure for a masked generative region only. It is not a template engine. The local repo context explicitly says the generic video path can produce `final_video` but does not understand GIF templates, manifests, deterministic layer locking, frame extraction, or GIF/WebP animation export.

The animated implementation should therefore either add a new `AnimatedRegionGenerationClient` abstraction around Sora/Veo/creative-service video sessions or add a constrained method to `VideoAdsOrchestrator` that can generate a masked region clip. It should not call `VideoAdsOrchestrator.run_variant` with a full-template prompt and expect fidelity.

### 2.5 Media storage and asset persistence

`mos/backend/app/services/media_storage.py` defines `MediaStorage`, using S3-compatible storage with `build_key`, `object_exists`, `upload_bytes`, `presign_get`, and `download_bytes`. Generated assets currently use content-addressed storage keys with immutable cache control.

`asset_activities.py` defines `_create_generated_asset_from_url`. It downloads the remote output, infers content type and asset kind, hashes bytes, stores them in `MediaStorage`, inspects image dimensions with PIL when relevant, creates an `Asset` row with `source_type=ai`, `status=draft`, `asset_kind`, `channel_id`, `format`, `content`, `storage_key`, `content_type`, `size_bytes`, `ai_metadata`, tags, and `expires_at`.

Animated outputs should reuse this persistence style but need a new local helper that can persist generated GIF/WebP/MP4 bytes directly, not only from remote URLs. The deterministic renderer will often create local artifacts from source frames and code-rendered overlays. It should not need to upload to a remote creative service only to download back. Implement `_create_generated_asset_from_bytes` in `asset_activities.py` or a shared `asset_persistence.py`, then use the same `AssetsRepository.create` contract.

### 2.6 Frontend swipe and review surfaces

`mos/frontend/src/api/swipes.ts` exposes hooks for company swipes, client swipes, GetHookd inbox, swipe collections, collection detail, collection CRUD, and swipe review bulk actions. It does not yet expose animated-template preview/approval/run endpoints.

`mos/frontend/src/components/campaigns/SwipeCollectionSelector.tsx` already supports asset type filtering for “All asset types,” “Static images,” “Videos,” “Carousels,” and “Unknown.” It uses `resolveSwipeAssetType`, `matchesSwipeAssetTypeFilter`, and preview normalization. This is a good foundation for animated template source selection, but the UI should distinguish “static image source usable for static image requirements” from “animated source usable for animated image requirements.” Currently, GIFs may still resolve as type `"image"` depending on backend media type; the plan should add explicit `animation` or `animated_image` media affordances rather than relying on the broad `"image"` type.

`mos/frontend/src/types/swipes.ts` defines `SwipeAssetType = "image" | "video" | "carousel" | "unknown"`. Add `"animated_image"` or `"animation"` carefully. Because existing filters and review grids expect `SwipeAssetTypeFilter = SwipeAssetType | "all"`, update all switch statements and labels.

`mos/frontend/src/components/library/SwipeMedia.tsx` already handles static media, video hover previews, and carousels. The animated template UI can reuse this component for source previews but should add a contact-sheet/diff component rather than overloading `SwipeMedia`.

`mos/frontend/src/components/review/AssetReviewGrid.tsx` is a shared review grid supporting filtering, multi-select, drag-select, and card detail panels. Generated animated assets should surface in existing creative review grids, but manifest preview/review is a separate stateful workflow and needs a dedicated component.

`mos/frontend/src/lib/assetBriefTypes.ts` currently defines `AssetBriefType = "image" | "video"` and defaults to image. Add `"animated_image"` only after backend normalization and campaign production routing exist.

### 2.7 Attached DB model limitation

The attached repo context extract maps the relevant `mos/backend/app/db/models.py` surfaces—`Artifact`, `Asset`, `CreativeServiceRun`, `CreativeServiceOutput`, `CompanySwipeAsset`, `CompanySwipeMedia`, `SwipeCollection`, `SwipeCollectionItem`, and `ClientSwipeAsset`—but the raw `db/models.py` file was not present in the uploaded bundle list. The data model sketches below are therefore implementation recommendations designed to fit the mapped model surface, not claims about exact existing column declarations.

## 3. End-to-end target workflow

### 3.1 User-facing workflow: manual animated template run

A manual operator flow should support a single source GIF/video/static animated candidate without touching the campaign production planner.

1. User selects a source from the swipe library or enters a source URL.
2. User selects campaign/client/product/asset brief/requirement index.
3. User chooses `renderMode = "auto" | "deterministic" | "hybrid"`.
4. User optionally chooses a specific generation model for masked regions. If no generative region is needed, no model selection is required.
5. User clicks **Analyze template**.
6. Backend starts `SwipeAnimatedTemplateAnalysisWorkflow`.
7. UI shows status: downloading source, extracting frames, OCR, detection, motion tracking, manifest built, QA preview built.
8. UI opens manifest preview:

   * source playback,
   * keyframe contact sheet,
   * overlay boxes/masks,
   * detected text list,
   * chart/path list,
   * UI chrome list,
   * product-slot evidence panel,
   * brand/copy slot panel,
   * locked vs editable vs generative layer counts,
   * risk summary.
9. User approves, edits, or rejects the manifest.
10. On approve, user clicks **Render**.
11. Backend starts `SwipeAnimatedTemplateRenderWorkflow`.
12. If no `generative_region` layers exist, renderer runs locally with no model call.
13. If generative regions exist, backend generates only those masked regions using the explicitly selected provider/model.
14. Deterministic renderer composites final frames.
15. Renderer exports animated WebP, GIF, and optionally MP4 preview.
16. QA runs and produces:

* source vs output contact sheet,
* keyframe side-by-side,
* diff heatmaps,
* OCR verification,
* timing verification,
* product policy report,
* color role report,
* final score.

17. Backend persists assets and QA artifacts.
18. UI shows generated asset review with quick approve/reject and blocking issues.

### 3.2 User-facing workflow: production campaign creative generation

Campaign creative production should support static image, animated image, and video requirements without breaking existing static generation.

1. Asset brief generation can produce requirements with `format = "image"`, `"animated_image"`, or `"video"`.
2. Campaign creative tab shows all brief types and lets the user select briefs for generation.
3. Swipe collection selector shows counts by source type:

   * static images,
   * animated GIFs,
   * videos,
   * carousels,
   * unknown.
4. Before production starts, frontend performs a readiness check:

   * static image requirements need at least one static image source,
   * animated image requirements need at least one GIF/video/animated-capable source,
   * video requirements need the existing video inputs.
5. Backend `generate_assets_for_brief_activity` routes by requirement format:

   * `"image"` -> existing static swipe image plan,
   * `"animated_image"` -> new animated template plan,
   * `"video"` -> existing generic video path.
6. For animated requirements, backend builds `AnimatedCreativeGenerationPlanArtifact` or extends `CreativeGenerationPlanArtifact` items with template run fields.
7. For each animated source:

   * if an approved reusable manifest exists for `(org_id, source_sha256, analyzer_version, manifest_version)` and compatible template constraints, reuse it;
   * if no approved manifest exists, create manifest and mark the plan item `review_required`;
   * do not proceed to paid generation until review is complete.
8. UI groups production items into:

   * ready to render,
   * awaiting manifest approval,
   * blocked by analysis error,
   * blocked by product-slot uncertainty,
   * completed.
9. After all required manifest approvals, user clicks **Continue production** or selects specific items to render.
10. Render workflow generates and persists final animated assets, then existing creative review surfaces show them in the latest production batch.

This makes animated production more interactive than static production. That is acceptable because template fidelity and product-slot gating are non-negotiable. The review checkpoint is not optional for uncertain templates.

### 3.3 Backend workflow lanes

Introduce two Temporal workflows:

```python
@dataclass
class SwipeAnimatedTemplateAnalysisInput:
    org_id: str
    client_id: str
    product_id: str | None
    campaign_id: str | None
    asset_brief_id: str | None
    requirement_index: int | None
    company_swipe_id: str | None
    swipe_media_id: str | None
    source_url: str | None
    source_label: str | None
    requested_analyzer_version: str | None
    workflow_run_id: str | None
    force_reanalysis: bool = False

@dataclass
class SwipeAnimatedTemplateRenderInput:
    org_id: str
    client_id: str
    product_id: str
    campaign_id: str | None
    asset_brief_id: str
    requirement_index: int
    template_manifest_id: str
    approved_manifest_version: int
    render_request: dict
    model_selection: dict | None
    workflow_run_id: str | None
    creative_generation_batch_id: str | None
    creative_generation_plan_artifact_id: str | None
    creative_generation_plan_item_id: str | None
```

The analysis workflow should be composed of activities:

1. `resolve_animated_source_activity`
2. `extract_animated_source_metadata_activity`
3. `sample_animated_source_frames_activity`
4. `analyze_animated_template_layers_activity`
5. `build_animated_template_manifest_activity`
6. `validate_animated_template_manifest_activity`
7. `persist_animated_template_preview_artifacts_activity`
8. `persist_animated_template_manifest_activity`

The render workflow should be composed of activities:

1. `load_approved_manifest_activity`
2. `resolve_brand_product_copy_context_activity`
3. `prepare_deterministic_render_plan_activity`
4. `estimate_or_record_ai_region_cost_activity`
5. `generate_masked_regions_activity` only if needed
6. `render_animated_template_frames_activity`
7. `export_animated_outputs_activity`
8. `run_animated_template_qa_activity`
9. `persist_animated_generated_assets_activity`
10. `record_animated_template_outputs_activity`

Each activity should be idempotent by content hash and run key. Analysis should not retry destructive changes. Render should not silently alter model choice or fallback providers.

### 3.4 When AI is not needed

The render plan should set `modelCallsRequired = false` when:

* all layers are `locked_source_region`, `deterministic_rebuild`, `brand_swap`, `copy_swap`, `product_swap`, or `omit`;
* no layer is `generative_region`;
* product replacement, if any, can be done through deterministic mask/composite using existing product imagery;
* background is source-preserved or can be deterministically inpainted from adjacent frames/static fill;
* final copy fits within approved text boxes under deterministic layout rules.

Examples requiring no AI:

* Mars item `05` chart,
* listicle chart/counter GIF,
* static badge card with moving shine,
* social UI screenshot with source post image preserved and only text swapped,
* before/after where panels are preserved and labels swap,
* customer collage where only count text changes and image tiles are preserved.

Examples requiring AI:

* source has a lifestyle/video/photo region that must become the target brand’s product-in-use scene;
* source has competitor packshot integrated into a photographic hand/scene and deterministic product replacement cannot preserve occlusion/lighting;
* source has a UGC subject where the source person/background should change while captions/UI stay locked;
* source has a product demo where the movement inside a masked region must be generated.

If AI is not needed, the UI should show “No model call required” and cost estimate should be deterministic render only.

## 4. Data model plan

### 4.1 Existing surfaces to reuse

Reuse:

* `WorkflowRun` for status and workflow navigation.
* `Artifact` for campaign-scoped manifest or plan artifacts where the artifact type system supports it.
* `Asset` for final generated assets and reviewable media.
* `CreativeServiceRun`, `CreativeServiceTurn`, `CreativeServiceOutput`, and `CreativeServiceEvent` for remote video/model calls when generative regions are used.
* `CompanySwipeAsset`, `CompanySwipeMedia`, `SwipeCollection`, and `SwipeCollectionItem` for source swipe library linkage.
* `MediaStorage` for source copies, extracted frames, masks, previews, contact sheets, exported GIF/WebP/MP4, and QA artifacts.

Add typed tables for manifest review because manifest status, approval, reviewer edits, and reuse lookups need queryable records. Storing all of this only inside `Asset.ai_metadata` or `Artifact.data` would make the review UI and idempotency weaker.

### 4.2 New table: `animated_template_manifests`

Purpose: one row per analyzed source/template manifest version. A source may have multiple versions because analyzers improve, humans edit manifests, or brand-specific slots are added.

Recommended columns:

```python
class AnimatedTemplateManifest(Base):
    __tablename__ = "animated_template_manifests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    client_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    product_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    campaign_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    company_swipe_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    company_swipe_media_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    source_url = Column(Text, nullable=True)
    source_label = Column(Text, nullable=True)
    source_mime_type = Column(String(128), nullable=False)
    source_sha256 = Column(String(64), nullable=False, index=True)
    source_size_bytes = Column(BigInteger, nullable=False)

    source_width = Column(Integer, nullable=False)
    source_height = Column(Integer, nullable=False)
    source_duration_ms = Column(Integer, nullable=True)
    source_frame_count = Column(Integer, nullable=True)
    source_frame_rate = Column(Float, nullable=True)

    analyzer_version = Column(String(64), nullable=False)
    manifest_schema_version = Column(Integer, nullable=False, default=1)
    manifest_version = Column(Integer, nullable=False, default=1)
    manifest_sha256 = Column(String(64), nullable=False, index=True)
    manifest_json = Column(JSONB, nullable=False)

    status = Column(
        String(32),
        nullable=False,
        default="draft",
        index=True,
    )
    analysis_status = Column(String(32), nullable=False, default="queued", index=True)
    analysis_error = Column(Text, nullable=True)

    review_required = Column(Boolean, nullable=False, default=True)
    review_reasons = Column(JSONB, nullable=False, default=list)
    risk_summary = Column(JSONB, nullable=False, default=dict)

    product_slot_status = Column(String(32), nullable=False, default="unknown", index=True)
    product_slot_confidence = Column(Float, nullable=True)
    has_competitor_product_slot = Column(Boolean, nullable=False, default=False)

    render_mode_recommended = Column(String(32), nullable=False, default="deterministic")
    ai_required = Column(Boolean, nullable=False, default=False)

    source_storage_key = Column(Text, nullable=True)
    source_bucket = Column(Text, nullable=True)
    preview_contact_sheet_key = Column(Text, nullable=True)
    preview_contact_sheet_bucket = Column(Text, nullable=True)
    overlay_preview_key = Column(Text, nullable=True)
    overlay_preview_bucket = Column(Text, nullable=True)
    frame_manifest_key = Column(Text, nullable=True)
    mask_manifest_key = Column(Text, nullable=True)

    created_by_user_id = Column(Text, nullable=True)
    approved_by_user_id = Column(Text, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by_user_id = Column(Text, nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)

    supersedes_manifest_id = Column(UUID(as_uuid=True), ForeignKey("animated_template_manifests.id"), nullable=True)
    artifact_id = Column(UUID(as_uuid=True), nullable=True)
    workflow_run_id = Column(UUID(as_uuid=True), nullable=True)

    idempotency_key = Column(String(96), nullable=False)
    retention_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
```

Indexes:

```sql
CREATE UNIQUE INDEX uq_animated_template_manifest_idempotency
ON animated_template_manifests (org_id, idempotency_key);

CREATE INDEX ix_animated_template_manifest_source_reuse
ON animated_template_manifests (org_id, source_sha256, analyzer_version, manifest_schema_version, status);

CREATE INDEX ix_animated_template_manifest_campaign_status
ON animated_template_manifests (org_id, campaign_id, status, created_at DESC);

CREATE INDEX ix_animated_template_manifest_product_slot
ON animated_template_manifests (org_id, has_competitor_product_slot, product_slot_status);
```

Status values:

* `draft`: manifest created but not approved.
* `needs_review`: manifest has review blockers or uncertainty.
* `approved`: human approved and renderable.
* `rejected`: user rejected the manifest.
* `superseded`: newer version replaces it.
* `failed`: analysis failed and cannot produce a valid manifest.

Analysis status values:

* `queued`
* `processing`
* `succeeded`
* `failed`

Product slot status values:

* `not_detected`
* `detected`
* `uncertain`
* `review_required`
* `disabled_by_policy`

### 4.3 New table: `animated_template_manifest_events`

Purpose: immutable review and edit event log for auditability.

```python
class AnimatedTemplateManifestEvent(Base):
    __tablename__ = "animated_template_manifest_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    manifest_id = Column(UUID(as_uuid=True), ForeignKey("animated_template_manifests.id"), nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    actor_user_id = Column(Text, nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
```

Event types:

* `analysis.started`
* `analysis.metadata_extracted`
* `analysis.layers_detected`
* `analysis.manifest_built`
* `analysis.failed`
* `review.field_updated`
* `review.layer_policy_changed`
* `review.product_slot_confirmed`
* `review.product_slot_rejected`
* `review.approved`
* `review.rejected`
* `manifest.superseded`
* `render.started`
* `render.completed`
* `render.failed`

This event table lets the UI show “why product replacement was allowed,” “who approved product slot evidence,” and “what changed from analyzer output.”

### 4.4 New table: `animated_template_runs`

Purpose: one row per render/generation run using an approved manifest and a brand/product/campaign context.

```python
class AnimatedTemplateRun(Base):
    __tablename__ = "animated_template_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    client_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    campaign_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    manifest_id = Column(UUID(as_uuid=True), ForeignKey("animated_template_manifests.id"), nullable=False, index=True)
    manifest_sha256 = Column(String(64), nullable=False)
    manifest_version = Column(Integer, nullable=False)

    workflow_run_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    asset_brief_id = Column(Text, nullable=False, index=True)
    brief_artifact_id = Column(UUID(as_uuid=True), nullable=True)
    requirement_index = Column(Integer, nullable=False)
    creative_generation_batch_id = Column(String(96), nullable=True, index=True)
    creative_generation_plan_artifact_id = Column(UUID(as_uuid=True), nullable=True)
    creative_generation_plan_item_id = Column(String(96), nullable=True, index=True)

    status = Column(String(32), nullable=False, default="queued", index=True)
    render_mode = Column(String(32), nullable=False)
    ai_required = Column(Boolean, nullable=False, default=False)

    requested_model_provider = Column(String(64), nullable=True)
    requested_model_id = Column(String(128), nullable=True)
    authorized_model_provider = Column(String(64), nullable=True)
    authorized_model_id = Column(String(128), nullable=True)

    render_request_json = Column(JSONB, nullable=False)
    render_plan_json = Column(JSONB, nullable=True)
    cost_estimate_json = Column(JSONB, nullable=True)
    cost_actual_json = Column(JSONB, nullable=True)

    output_asset_ids = Column(JSONB, nullable=False, default=list)
    output_storage_keys = Column(JSONB, nullable=False, default=dict)
    qa_report_json = Column(JSONB, nullable=True)
    qa_score = Column(Float, nullable=True)
    qa_status = Column(String(32), nullable=True)

    idempotency_key = Column(String(96), nullable=False)
    error_detail = Column(Text, nullable=True)
    retention_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)
```

Indexes:

```sql
CREATE UNIQUE INDEX uq_animated_template_run_idempotency
ON animated_template_runs (org_id, idempotency_key);

CREATE INDEX ix_animated_template_run_plan_item
ON animated_template_runs (org_id, creative_generation_batch_id, creative_generation_plan_item_id);

CREATE INDEX ix_animated_template_run_brief
ON animated_template_runs (org_id, campaign_id, asset_brief_id, requirement_index, created_at DESC);
```

### 4.5 New table: `animated_template_artifacts`

This table is optional but useful if storage keys become numerous. It records derived artifacts independently of manifest/run rows.

```python
class AnimatedTemplateArtifact(Base):
    __tablename__ = "animated_template_artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    manifest_id = Column(UUID(as_uuid=True), ForeignKey("animated_template_manifests.id"), nullable=True, index=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("animated_template_runs.id"), nullable=True, index=True)

    artifact_kind = Column(String(64), nullable=False, index=True)
    storage_bucket = Column(Text, nullable=False)
    storage_key = Column(Text, nullable=False)
    content_type = Column(String(128), nullable=False)
    size_bytes = Column(BigInteger, nullable=True)
    sha256 = Column(String(64), nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    frame_index = Column(Integer, nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)

    retention_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
```

Artifact kinds:

* `source_original`
* `source_normalized_mp4`
* `source_frame`
* `source_keyframe`
* `source_contact_sheet`
* `overlay_preview`
* `layer_mask`
* `mask_contact_sheet`
* `analysis_debug`
* `manifest_json`
* `render_frame`
* `render_output_gif`
* `render_output_webp`
* `render_output_mp4`
* `qa_contact_sheet`
* `qa_diff_heatmap`
* `qa_report_json`
* `generated_region_video`
* `generated_region_frame`

### 4.6 Artifact enum additions

If `ArtifactTypeEnum` is centrally defined, add:

* `animated_template_manifest`
* `animated_template_generation_plan`
* `animated_template_qa_report`

Near-term, the DB tables should be the primary source for manifest review. Artifact rows are useful for campaign provenance and for attaching manifest payloads into existing artifact browsing/context flows. Store only approved manifests as artifact rows unless the UI needs draft artifacts.

### 4.7 Asset kind and format changes

Existing `Asset.asset_kind` likely supports `"image"` and `"video"` from `_asset_kind_for_content_type`. Animated GIF and animated WebP are both MIME type `image/*`; they should persist with `asset_kind="image"` unless the existing enum is extended. To preserve review/UI clarity without wide DB changes, set:

* `asset_kind = "image"` for GIF/WebP.
* `format = "animated_image"` from requirement.
* `content.sourceKind = "animated_swipe_template"`.
* `ai_metadata.animatedTemplate = {...}`.

If `Asset.asset_kind` can safely be extended, add `"animated_image"`. This would require updating any validators, frontend normalizers, and Meta/publish code. The safer first phase is to keep `asset_kind="image"` and use `format` plus metadata for animation semantics.

Add content fields:

```json
{
  "assetBriefId": "...",
  "requirementIndex": 0,
  "requirement": { "format": "animated_image", "...": "..." },
  "sourceKind": "animated_swipe_template",
  "sourceUrl": "...",
  "variantIndex": null,
  "prompt": null,
  "animatedTemplateManifestId": "...",
  "animatedTemplateRunId": "...",
  "outputFormat": "gif|webp|mp4"
}
```

Add `ai_metadata` fields:

```json
{
  "sourceKind": "animated_swipe_template",
  "animatedTemplateManifestId": "...",
  "animatedTemplateManifestSha256": "...",
  "animatedTemplateRunId": "...",
  "sourceSwipeCompanyId": "...",
  "sourceSwipeMediaId": "...",
  "sourceSha256": "...",
  "sourceFrameCount": 16,
  "sourceDurationMs": 2860,
  "renderMode": "deterministic",
  "aiRequired": false,
  "aiRegionModelCalls": [],
  "productSlot": {
    "hasCompetitorProductSlot": false,
    "replacementApplied": false,
    "evidenceCount": 0
  },
  "qa": {
    "qaStatus": "pass",
    "qaScore": 93.2,
    "qaReportArtifactId": "...",
    "contactSheetUrl": "..."
  },
  "cost": {
    "deterministicRenderMs": 5200,
    "modelUsd": 0,
    "modelBillableSeconds": 0
  }
}
```

### 4.8 Migration plan

Create Alembic migration, for example:

`mos/backend/alembic/versions/00xx_animated_template_manifests.py`

Steps:

1. Create `animated_template_manifests`.
2. Create `animated_template_manifest_events`.
3. Create `animated_template_runs`.
4. Create `animated_template_artifacts`.
5. Add indexes listed above.
6. Add optional artifact enum values if the enum is DB-backed.
7. Add check constraints if useful:

   * exactly one of `company_swipe_id` or `source_url` should be present if source is not an uploaded local artifact;
   * `source_frame_count >= 1`;
   * `source_width > 0`;
   * `source_height > 0`;
   * `manifest_schema_version >= 1`.
8. Add non-blocking metadata columns to existing tables only if necessary:

   * `CompanySwipeAsset.source_metadata_json.animated_template_last_manifest_id` can remain metadata rather than schema.
   * `Asset.format` already exists from `_create_generated_asset_from_url`; no DB change unless enum constrained.
9. Backfill nothing. Do not create fake manifests. Existing assets remain static/video as-is.

### 4.9 Retention and cleanup

Use two retention classes:

**Reusable source manifests.** Approved manifests should not expire by default if the source is in the swipe library and the org retains the source media. They are useful reusable production assets. Draft/failed/unapproved manifests can expire after `ANIMATED_TEMPLATE_DRAFT_RETENTION_DAYS`, defaulting to `CREATIVE_SERVICE_RETENTION_DAYS`.

**Derived render artifacts.** Generated frames, masks, debug images, temporary generated region clips, and intermediate MP4s should expire after `CREATIVE_SERVICE_RETENTION_DAYS` unless linked to a final asset or QA report. Final GIF/WebP/MP4 assets use existing `Asset.expires_at` behavior.

Add cleanup activity or scheduled job:

```python
@activity.defn
def cleanup_expired_animated_template_artifacts_activity(params):
    # list AnimatedTemplateArtifact where retention_expires_at < now
    # delete storage object if no final Asset references storage_key
    # mark deleted metadata or delete row
```

Never delete:

* approved manifest JSON,
* final generated asset bytes,
* QA report for approved/generated assets,
* source media owned by swipe library.

### 4.10 Idempotency

Analysis idempotency key:

```text
animated_template_analysis_v1 |
org_id |
company_swipe_id or source_url |
source_sha256 |
source_mime_type |
analyzer_version |
manifest_schema_version |
force_reanalysis=false
```

If an approved manifest exists for the same `source_sha256`, `analyzer_version`, and `manifest_schema_version`, return it unless `force_reanalysis=true`.

Render idempotency key:

```text
animated_template_render_v1 |
org_id |
client_id |
product_id |
campaign_id |
asset_brief_id |
requirement_index |
manifest_id |
manifest_sha256 |
approved_manifest_version |
brand_context_sha |
copy_context_sha |
product_reference_sha_list |
render_request_sha |
requested_model_provider |
requested_model_id |
output_formats |
renderer_version
```

For deterministic-only runs, this key should allow full reuse of a completed run and output asset IDs. For model-region runs, include every generated-region request and selected model. Do not silently reuse a run generated by another model if the requested model differs.

## 5. Manifest schema

### 5.1 Design goals

The manifest must be generic, not chart-specific. It should represent an animated template as a timeline of layers and slots. Specialized detectors can populate chart paths, counters, UI chrome, product masks, or social screenshot regions, but the renderer should only need generic primitives:

* source region,
* text,
* image,
* video/generative region,
* vector path,
* shape,
* mask,
* product slot,
* logo slot,
* group,
* counter,
* chart series,
* UI chrome,
* badge,
* particle/texture overlay.

Charts, tables, social posts, customer collages, before/after panels, and UGC clips are different combinations of the same primitives. That is how the schema avoids overfitting.

### 5.2 Top-level manifest schema sketch

```json
{
  "$schema": "https://mos.local/schemas/animated-template-manifest-v1.json",
  "schemaVersion": 1,
  "templateId": "atmplt_...",
  "manifestId": "uuid",
  "manifestVersion": 1,
  "analyzerVersion": "animated-template-analyzer-2026-05-07",
  "createdAt": "2026-05-07T00:00:00Z",

  "source": {
    "sourceKind": "company_swipe|direct_url|uploaded_asset",
    "companySwipeId": null,
    "companySwipeMediaId": null,
    "url": null,
    "sourceLabel": "item-05.gif",
    "mimeType": "image/gif",
    "sha256": "hex",
    "sizeBytes": 0,
    "width": 996,
    "height": 996,
    "durationMs": 2860,
    "frameCount": 16,
    "loopCount": 0,
    "frameDelaysMs": [180, 180],
    "hasTransparency": false,
    "colorSpace": "srgb",
    "backgroundColor": "#000000",
    "normalizedVideoStorageKey": null,
    "sourceStorageKey": "..."
  },

  "canvas": {
    "width": 996,
    "height": 996,
    "aspectRatio": "1:1",
    "pixelRatio": 1,
    "safeCrop": null,
    "cornerRadius": 0,
    "background": {
      "type": "solid|source|transparent",
      "colorRole": "background",
      "sourceLayerId": null
    }
  },

  "timeline": {
    "durationMs": 2860,
    "fps": null,
    "frameTimesMs": [0, 180, 360],
    "frameDelaysMs": [180, 180],
    "loop": true,
    "loopCount": 0,
    "timebase": "source_frames",
    "exportFramePolicy": "preserve_source_delays|resample_constant_fps",
    "recommendedPreviewFps": 12
  },

  "templateClassification": {
    "families": ["chart", "text_heavy_graphic"],
    "primaryFamily": "chart",
    "confidence": 0.91,
    "signals": [
      { "type": "chart_axes_detected", "confidence": 0.94 },
      { "type": "ocr_text_labels", "confidence": 0.88 }
    ]
  },

  "colorRoles": {},
  "textRoles": {},
  "brandReplacement": {},
  "productReplacement": {},
  "copyReplacement": {},
  "layers": [],
  "groups": [],
  "slots": [],
  "masks": [],
  "sourceFrames": [],
  "qualityExpectations": {},
  "review": {},
  "renderDefaults": {},
  "provenance": {}
}
```

### 5.3 Layer policies

Layer policies should be a closed enum:

```json
[
  "locked_source_region",
  "deterministic_rebuild",
  "brand_swap",
  "logo_swap",
  "product_swap",
  "copy_swap",
  "generative_region",
  "omit",
  "review_only"
]
```

Definitions:

* `locked_source_region`: preserve the exact source region as pixels. It may be copied frame by frame or source-matched through background plate extraction. No semantic edits.
* `deterministic_rebuild`: rebuild using geometry/path/text/style extracted from source. Use code renderer. Good for chart lines, axes, simple shapes, badges, counters, UI boxes.
* `brand_swap`: replace competitor brand text with target brand text using deterministic text layout and color role.
* `logo_swap`: replace competitor logo mark with approved target logo asset, using deterministic placement/mask.
* `product_swap`: replace competitor product slot with approved target product asset. Requires product-slot evidence.
* `copy_swap`: replace source copy with approved final copy. Requires final copy in render request or linked copy pack.
* `generative_region`: model may generate new pixels only within this mask. No text/charts/products/UI chrome inside the generated output unless explicitly allowed.
* `omit`: remove a source element; replacement is background fill/inpaint/deterministic redraw.
* `review_only`: detected element is not rendered but appears in review diagnostics.

Default policy should be `locked_source_region` for complex unknown pixels and `deterministic_rebuild` for detected vector/text primitives. Never default to `generative_region`.

### 5.4 Generic layer schema

```json
{
  "id": "layer_axis_y_label",
  "type": "text|image|video_region|source_region|shape|path|chart_series|counter|badge|ui_chrome|logo|product|group|mask|particle|unknown",
  "policy": "deterministic_rebuild",
  "zIndex": 20,
  "parentGroupId": null,

  "sourceEvidence": {
    "detectors": [
      {
        "detector": "ocr_v1",
        "confidence": 0.93,
        "frameIndexes": [0, 4, 8],
        "evidenceStorageKeys": []
      }
    ],
    "sourceBoxes": [
      { "frameIndex": 0, "box": [50, 240, 40, 360], "confidence": 0.93 }
    ],
    "sourceMasks": [
      { "frameIndex": 0, "maskId": "mask_y_axis_label" }
    ],
    "notes": []
  },

  "geometry": {
    "box": [50, 240, 40, 360],
    "anchor": "center",
    "rotationDegrees": -90,
    "transform": [1, 0, 0, 1, 0, 0],
    "clipMaskId": null,
    "cornerRadius": 0
  },

  "content": {},
  "style": {},
  "motion": {},
  "rendering": {
    "owner": "deterministic_renderer|ai_region_model|source_copy",
    "blendMode": "normal",
    "opacity": 1,
    "antiAlias": true,
    "compositeMode": "source_over"
  },

  "validation": {
    "confidence": 0.93,
    "reviewRequired": false,
    "reviewReasons": [],
    "locked": true,
    "allowedEdits": ["brand_text", "color_role"]
  }
}
```

### 5.5 Product-slot evidence model

Top-level product replacement object:

```json
{
  "productReplacement": {
    "hasCompetitorProductSlot": false,
    "status": "not_detected|detected|uncertain|review_required|disabled_by_policy",
    "replacementAllowed": false,
    "replacementRequired": false,
    "replacementMode": "none|deterministic_packshot_swap|masked_ai_region_then_overlay|manual_only",
    "sourceProductSlots": [],
    "negativeEvidence": [],
    "decision": {
      "decidedBy": "analyzer|human",
      "userId": null,
      "decidedAt": null,
      "reason": "No packaged product or product-like slot detected in any sampled frame."
    }
  }
}
```

Source product slot schema:

```json
{
  "id": "product_slot_1",
  "slotKind": "packshot|bottle|pouch|box|jar|tube|device|in_use_product|ambiguous_object",
  "confidence": 0.0,
  "replacementEligible": false,
  "reviewRequired": true,

  "evidence": [
    {
      "type": "object_detection",
      "label": "bottle",
      "confidence": 0.91,
      "frameIndex": 4,
      "box": [620, 420, 160, 340],
      "maskId": "mask_product_slot_1_frame_4"
    },
    {
      "type": "ocr_on_object",
      "text": "MARS MEN",
      "confidence": 0.78,
      "frameIndex": 4,
      "box": [650, 520, 80, 30]
    },
    {
      "type": "logo_detection",
      "sourceBrand": "Mars Men",
      "confidence": 0.83,
      "frameIndex": 4
    },
    {
      "type": "motion_stability",
      "confidence": 0.88,
      "frameIndexes": [0, 4, 8, 12],
      "trackId": "track_product_slot_1"
    }
  ],

  "negativeEvidence": [
    {
      "type": "template_family",
      "label": "chart_without_packshot",
      "confidence": 0.92
    }
  ],

  "geometry": {
    "canonicalBox": [620, 420, 160, 340],
    "canonicalMaskId": "mask_product_slot_1",
    "perFrameBoxes": [],
    "perFrameMasks": [],
    "occlusionMasks": [],
    "shadowLayerId": null,
    "highlightLayerId": null,
    "perspectiveQuad": null,
    "anchor": "center"
  },

  "sourceProductIdentity": {
    "brandText": [],
    "logoText": [],
    "packagingFormFactor": null,
    "dominantColors": [],
    "readableClaims": [],
    "unreadableTextPresent": false
  },

  "targetConstraints": {
    "preserveFormFactor": true,
    "allowedTargetAssetKinds": ["product_packshot_png"],
    "allowFormFactorMismatch": false,
    "allowModelToRenderProduct": false,
    "deterministicOverlayRequired": true
  }
}
```

Product slot creation rules:

* `hasCompetitorProductSlot=true` only when there is at least one eligible slot with positive source evidence.
* Evidence must include at least one visual object/product signal and at least one of:

  * OCR/logo/brand-on-object,
  * product-like packaging shape,
  * human holding/in-use product signal,
  * source metadata taxonomy `product_presence` strongly indicating product presence.
* Chart/table/UI/text-only templates with no object evidence must set `hasCompetitorProductSlot=false`.
* If evidence is mixed or below threshold, set `status="review_required"` and `replacementAllowed=false`.
* Human approval can flip `replacementAllowed` only by selecting/confirming a slot and mask.

### 5.6 Color role model

```json
{
  "colorRoles": {
    "background": {
      "sourceValue": "#050505",
      "targetValue": "#050505",
      "policy": "preserve_source|brand_token|manual_override",
      "sourceSamples": [
        { "frameIndex": 0, "point": [20, 20], "value": "#050505" }
      ],
      "confidence": 0.99
    },
    "brandAccent": {
      "sourceValue": "#D33A32",
      "targetValue": "#C83232",
      "policy": "brand_token",
      "brandTokenPath": "cssVars.--color-brand",
      "fallbackAllowed": false,
      "confidence": 0.95
    },
    "axisText": {
      "sourceValue": "#D33A32",
      "targetValue": "#C83232",
      "policy": "linked_role",
      "linkedRole": "brandAccent",
      "confidence": 0.9
    },
    "comparisonLine": {
      "sourceValue": "#FFFFFF",
      "targetValue": "#FFFFFF",
      "policy": "preserve_source",
      "confidence": 0.97
    }
  }
}
```

Rules:

* Target hex values come from design system tokens, approved render request, or human manifest edit.
* No model prompt should say “make it red” when a role exists. The renderer receives exact values.
* If a required brand color token is missing, error or require review. Do not guess.

### 5.7 Text role model

```json
{
  "textRoles": {
    "source_brand_name": {
      "roleKind": "brand_name",
      "sourceText": "MARS MEN",
      "targetText": "TENOR",
      "policy": "brand_swap",
      "caseTransform": "uppercase",
      "reviewRequired": false
    },
    "axis_label_y": {
      "roleKind": "chart_axis_label",
      "sourceText": "ENERGY LEVEL",
      "targetText": "ENERGY LEVEL",
      "policy": "preserve_text",
      "reviewRequired": false
    },
    "claim_badge": {
      "roleKind": "claim",
      "sourceText": "THIRD PARTY TESTED",
      "targetText": null,
      "policy": "requires_approved_copy",
      "reviewRequired": true
    }
  }
}
```

Text layer content:

```json
{
  "content": {
    "textRoleId": "axis_label_y",
    "sourceText": "ENERGY LEVEL",
    "targetText": "ENERGY LEVEL",
    "textSource": "ocr|manual|approved_copy_pack|brand_token",
    "allowLineWrap": false,
    "maxLines": 1,
    "overflowPolicy": "shrink_to_fit|review_required|clip_like_source",
    "readingOrder": 1
  },
  "style": {
    "fontFamily": "source_match_or_brand_font",
    "fontAssetId": null,
    "fontWeight": 800,
    "fontStyle": "normal",
    "fontSizePx": 40,
    "lineHeightPx": 44,
    "letterSpacingPx": 18,
    "textAlign": "center",
    "verticalAlign": "middle",
    "fillColorRole": "axisText",
    "strokeColorRole": null,
    "strokeWidthPx": 0,
    "textTransform": "uppercase"
  }
}
```

Rules:

* OCR output is evidence, not automatically approved final copy.
* Source text that is unreadable should be recorded as `[UNREADABLE]` and marked review-required.
* Model-rendered text is disallowed unless `generation.modelMayRenderText=true` and the layer is not locked. Production default is false.
* Text fit failures must stop render or require review. Do not silently shrink below threshold unless the manifest permits `shrink_to_fit`.

### 5.8 Motion and timing model

Top-level timeline preserves source delays. Each layer can have independent motion.

```json
{
  "motion": {
    "type": "static|keyframes|source_tracked|path_draw|counter_increment|fade|slide|scale|wipe|loop_texture",
    "sourceMotionId": "track_123",
    "startMs": 400,
    "endMs": 2400,
    "easing": "linear|ease_in|ease_out|ease_in_out|steps|source_sampled",
    "keyframes": [
      {
        "timeMs": 0,
        "frameIndex": 0,
        "opacity": 0,
        "transform": [1, 0, 0, 1, 0, 0],
        "box": [0, 0, 100, 100],
        "pathProgress": 0
      },
      {
        "timeMs": 1200,
        "frameIndex": 8,
        "opacity": 1,
        "pathProgress": 0.6
      }
    ],
    "perFrame": [
      {
        "frameIndex": 0,
        "timeMs": 0,
        "box": [0, 0, 100, 100],
        "maskId": "mask_layer_frame_0"
      }
    ],
    "loopBehavior": "source|hold_last|ping_pong|seamless",
    "reviewRequired": false
  }
}
```

For chart line draw-on:

```json
{
  "type": "path_draw",
  "pathId": "path_primary_line",
  "startMs": 300,
  "endMs": 2300,
  "easing": "source_sampled",
  "keyframes": [
    { "timeMs": 300, "pathProgress": 0 },
    { "timeMs": 1200, "pathProgress": 0.45 },
    { "timeMs": 2300, "pathProgress": 1 }
  ]
}
```

Rules:

* If source timing cannot be extracted confidently, stop for review.
* Source GIF frame delays must be preserved unless render request explicitly asks for resampling.
* Motion on locked layers is rendered deterministically.
* Generated regions may have their own video frames but must be time-aligned to the manifest.

### 5.9 Mask and source-frame model

```json
{
  "sourceFrames": [
    {
      "frameIndex": 0,
      "timeMs": 0,
      "delayMs": 180,
      "storageKey": "frames/source_0000.png",
      "sha256": "hex",
      "width": 996,
      "height": 996,
      "isKeyframe": true,
      "samplingReason": "first_frame"
    }
  ],
  "masks": [
    {
      "id": "mask_product_slot_1",
      "kind": "binary|alpha|polygon|rle",
      "coordinateSpace": "canvas",
      "source": "detector|manual|derived_from_layer",
      "storageKey": "masks/product_slot_1.png",
      "bbox": [620, 420, 160, 340],
      "polygon": [[620, 420], [780, 420], [780, 760], [620, 760]],
      "featherPx": 0,
      "dilatePx": 0,
      "confidence": 0.91
    }
  ]
}
```

Masks must be coordinate-system explicit. Every mask must include enough metadata to render and preview it, not just a storage key.

### 5.10 Validation rules

Manifest validation should run in Pydantic plus semantic validators.

Hard validation:

* `source.sha256` is required.
* `source.width`, `source.height`, `canvas.width`, and `canvas.height` must be positive.
* `timeline.durationMs` must match sum of `frameDelaysMs` within tolerance.
* Every layer ID must be unique.
* Every referenced `maskId`, `colorRole`, `textRoleId`, `pathId`, and `groupId` must exist.
* Locked layers must have deterministic render owners.
* `generative_region` layers must have masks.
* Product swap layers require `productReplacement.hasCompetitorProductSlot=true` and an eligible `sourceProductSlot`.
* If `hasCompetitorProductSlot=false`, no layer may have `policy="product_swap"`.
* If `modelMayRenderText=false`, no `generative_region` may include text roles.
* If `modelMayInsertProduct=false`, generative prompts must not attach product references.
* Color roles with `policy="brand_token"` must have a target value or review blocker.
* Text roles with `policy="requires_approved_copy"` must have target text or review blocker.
* Layers with confidence below threshold must set `reviewRequired=true`.
* Render cannot proceed if `reviewRequired=true` and status is not approved.
* A human edit that changes product slot eligibility must create an event.

## 6. Ingestion and analysis pipeline

### 6.1 Source resolution and download

Implement new module:

`mos/backend/app/services/animated_templates/source_resolver.py`

Responsibilities:

* Resolve exactly one source:

  * `companySwipeId` plus optional `mediaId`,
  * direct `sourceUrl`,
  * uploaded local asset ID if later supported.
* For `companySwipeId`, load `CompanySwipeAsset` and `CompanySwipeMedia` through `CompanySwipesRepository`.
* Prefer animated media when multiple items exist:

  * `image/gif`,
  * `image/webp` with animation if detectable,
  * `video/mp4`,
  * `video/webm`,
  * fallback to static image only when the requested mode allows static-to-animated deterministic template.
* Download bytes using streaming with a larger config than static images:

  * `ANIMATED_TEMPLATE_SOURCE_MAX_BYTES`, default 100 MB,
  * `ANIMATED_TEMPLATE_DOWNLOAD_TIMEOUT_SECONDS`, default 60 seconds.
* Validate MIME type:

  * accepted: `image/gif`, `image/webp`, `image/png`, `image/jpeg`, `video/mp4`, `video/webm`, `video/quicktime`;
  * reject unsupported with clear error.
* Compute SHA-256.
* Store original bytes in `MediaStorage` as `source_original`.
* Return source descriptor.

Do not reuse `_download_bytes` blindly because it currently enforces `SWIPE_IMAGE_MAX_BYTES` and expects image behavior. Create a streaming download helper that writes to temp file, enforces max bytes, and supports video content types.

### 6.2 ffprobe/ffmpeg metadata extraction

Implement:

`mos/backend/app/services/animated_templates/media_probe.py`

Functions:

```python
def probe_media(path: Path) -> AnimatedMediaProbe:
    ...
def extract_gif_frame_delays(path: Path) -> list[int]:
    ...
def normalize_source_to_mp4_if_needed(path: Path, mime_type: str) -> NormalizedVideo:
    ...
```

Use `ffprobe` for:

* width,
* height,
* duration,
* frame count,
* stream codec,
* frame rate,
* pixel format,
* rotation,
* color metadata.

Use Pillow or imageio for GIF/WebP exact frame delays when ffprobe is ambiguous. GIF frame delays are often not constant; preserving them matters. Store both exact delays and normalized timebase.

Validation:

* Reject zero duration for animated source unless static mode is allowed.
* Reject width/height beyond configurable max unless downsampling is explicitly supported.
* Reject too many frames unless analysis downsampling is configured:

  * e.g. `ANIMATED_TEMPLATE_MAX_SOURCE_FRAMES=600`,
  * `ANIMATED_TEMPLATE_MAX_RENDER_FRAMES=180` for initial rollout.
* For long videos, require trim/crop selection before analysis or default to a clean error.

### 6.3 Frame extraction and sampling

Implement:

`mos/backend/app/services/animated_templates/frame_sampler.py`

Extract:

* all frames for small GIFs under max frame count;
* keyframes for longer videos:

  * first,
  * last,
  * middle,
  * high-difference frames,
  * scene-change frames,
  * frames where OCR/detection changes,
  * frames around motion extrema.

Persist:

* source frames as PNG,
* downscaled preview frames,
* contact sheet,
* frame manifest JSON.

Sampling strategy:

```python
sampled_frames = union(
    first_last_mid(source),
    uniform_sample(max_n=12),
    perceptual_diff_peaks(max_n=12),
    scene_change_frames(max_n=8),
    gif_disposal_change_frames(),
)
```

For deterministic rendering, the renderer may need all frames. Analysis can sample fewer frames, but source timings and renderer output should preserve the full timeline. For GIFs under the max, extracting all frames is preferred.

### 6.4 OCR

OCR is evidence, not rendering. The plan should use OCR to populate text layers and review UI.

Implement:

`mos/backend/app/services/animated_templates/ocr.py`

Inputs:

* sampled frames,
* optional high-res source frames,
* region proposals from connected components and UI detection.

Outputs:

* text strings,
* bounding boxes,
* confidence,
* orientation,
* rotation,
* reading order,
* per-frame persistence/tracking,
* detected text role suggestions.

OCR pipeline:

1. Run text detection on each sampled frame.
2. Merge text boxes across frames using IoU and text similarity.
3. Detect orientation:

   * horizontal,
   * vertical rotated -90/90,
   * multiline,
   * curved text not initially supported.
4. Normalize text:

   * keep raw OCR text,
   * store normalized comparison text,
   * mark `[UNREADABLE]` when confidence low.
5. Classify roles:

   * brand name,
   * product name,
   * chart label,
   * axis label,
   * tick label,
   * badge,
   * CTA,
   * disclaimer,
   * UI label,
   * username/handle,
   * claim.
6. Mark review-required if:

   * role is brand/product/copy/claim and confidence below threshold,
   * text is visible but unreadable,
   * target copy is required and missing.

For the Mars item `05`, OCR should produce `ENERGY LEVEL`, `NORMAL CRASH`, `TIME OF DAY`, `6AM`, `12PM`, `6PM`, and later `WITH MARS MEN`. The vertical `ENERGY LEVEL` label should be represented as a rotated text layer, not left to a video model.

### 6.5 Object/product/logo detection

Implement:

`mos/backend/app/services/animated_templates/object_detection.py`

This stage has two responsibilities:

* detect visible objects/product-like regions,
* detect whether those objects qualify as competitor product slots.

Signals:

1. Object detector:

   * bottle,
   * pouch,
   * box,
   * jar,
   * tube,
   * supplement container,
   * food package,
   * cosmetic product,
   * device,
   * phone/screen,
   * hand-held object.
2. OCR-on-object:

   * text inside object mask,
   * brand names,
   * product labels,
   * supplement/product words.
3. Logo detection:

   * competitor logo,
   * brand mark,
   * label graphics.
4. Region stability:

   * product packshots often remain spatially stable across frames,
   * in-use product may move with hands but track as coherent object.
5. Template context:

   * product/badge composition increases prior,
   * chart/table/text-heavy UI without objects decreases prior.
6. Swipe taxonomy:

   * `product_presence` from `CompanySwipeAsset` can be supporting evidence,
   * never sole evidence.
7. Human correction:

   * review UI can draw/confirm product mask.

Product-slot decision:

```python
if positive_visual_object_score >= 0.75 and supporting_identity_score >= 0.40:
    status = "detected"
elif positive_visual_object_score >= 0.55 or conflicting_signals:
    status = "review_required"
else:
    status = "not_detected"
```

But do not rely only on numeric score. Store evidence. A detected slot must have a mask/box and form-factor guess.

Negative evidence examples:

* only chart lines and labels,
* no object-like regions above threshold,
* source template family is chart/text-only,
* any product-like output would occlude locked chart/UI layers,
* object detector finds “bottle” only in generated target references, not source frames.

### 6.6 Chart/path extraction

Implement:

`mos/backend/app/services/animated_templates/chart_detection.py`

This should populate generic `path`, `chart_series`, `shape`, `text`, and `motion` layers.

Pipeline:

1. Detect chart-like template family:

   * axes,
   * tick labels,
   * gridlines,
   * line/path segments,
   * plot area bounds,
   * labels near axes,
   * high-contrast colored lines.
2. Use OCR boxes to mask out text before path extraction.
3. Use color segmentation for dominant line colors.
4. Use Canny/Sobel edges and contour tracing.
5. Fit paths:

   * polylines,
   * cubic Beziers,
   * dashed lines,
   * area fills.
6. Detect animation:

   * path draw-on progress across frames,
   * point markers appearing,
   * label reveal timing.
7. Store:

   * plot area,
   * axis paths,
   * gridline paths,
   * series paths,
   * label layers,
   * color roles,
   * motion keyframes.

Important: chart paths should preserve geometry. Brand recoloring is allowed by changing color roles, not by asking a model to redraw a line. The attached prompt docs explicitly call out that chart lines must preserve source path geometry and avoid extra points, glows, duplicate labels, or simplification.

### 6.7 UI chrome detection

Implement:

`mos/backend/app/services/animated_templates/ui_chrome_detection.py`

Detect:

* mobile app headers,
* Instagram/TikTok/Twitter-like screenshot chrome,
* browser bars,
* phone screen captures,
* comment rows,
* reaction/share/save icons,
* username/handle/timestamp zones,
* UI borders/dividers,
* CTA buttons,
* caption blocks,
* listicle page embedded UI.

Represent UI chrome as deterministic layers:

* text layers for usernames/captions/comments,
* icon vector or source-region layers for icons,
* shape layers for rows/dividers/buttons,
* source-region layers for small icons if vectorization fails,
* generative region only for post media area if allowed.

UI chrome must not be treated as optional decoration. The static prompt already emphasizes preserving native UI/screenshot chrome; the animated path should enforce it through layer locking rather than prompt wording.

### 6.8 Motion tracking

Implement:

`mos/backend/app/services/animated_templates/motion_tracking.py`

Inputs:

* sampled frames,
* layer proposals,
* masks,
* source frame times.

Outputs:

* per-layer tracks,
* keyframes,
* motion confidence,
* unresolved movement review blockers.

Methods:

* sparse optical flow for points,
* template matching for static overlays,
* mask IoU across frames,
* contour tracking for chart line draw,
* text box tracking,
* object tracking for product slots,
* scene-change detection.

Confidence rules:

* Text/UI/charts require high motion confidence because renderer must reproduce them.
* If a locked layer disappears/reappears, record visibility keyframes.
* If layer tracking fails, set `reviewRequired=true`.
* If movement belongs to a generative region, the model may own internal motion, but mask boundaries/timing still must be deterministic.

### 6.9 Layer classification

Implement:

`mos/backend/app/services/animated_templates/layer_classifier.py`

Inputs:

* OCR outputs,
* object detections,
* chart paths,
* UI chrome detections,
* motion tracks,
* template family classification.

Outputs:

* layer list,
* policies,
* review reasons,
* render mode recommendation.

Policy defaults by family:

* Chart/text-heavy:

  * axes/text/chart paths -> deterministic,
  * background -> locked source or deterministic,
  * model regions -> none.
* Product/badge:

  * badges/text/claims -> deterministic,
  * product slot -> product swap if evidence approved,
  * background texture -> locked or generative only if safe.
* Social UI:

  * chrome/text/icons -> deterministic/source locked,
  * post media area -> locked or generative depending request.
* Customer collage:

  * grid/tile masks/count/rating text -> deterministic,
  * tile images -> locked or generative.
* Before/after:

  * panel geometry/divider/labels -> deterministic,
  * panel photos -> locked or generative.
* UGC/lifestyle:

  * captions/product slot/UI overlays -> deterministic,
  * body/background motion -> generative if requested.

### 6.10 Confidence and review gating

Every manifest should produce:

```json
"review": {
  "required": true,
  "blockingReasons": [],
  "warnings": [],
  "confidenceSummary": {
    "ocr": 0.91,
    "productSlot": 0.0,
    "motion": 0.87,
    "chartExtraction": 0.94,
    "uiChrome": null
  },
  "recommendedAction": "approve|edit|reject|manual_manifest_required",
  "humanReviewChecklist": []
}
```

Review should be required when:

* product slot status is `uncertain` or `review_required`;
* product swap requested but no approved product slot;
* OCR has low confidence on locked text;
* text replacement is needed but target copy missing;
* chart/path extraction confidence below threshold;
* UI chrome detected but incomplete;
* motion tracking confidence below threshold for locked layer;
* source duration/frame count exceeds rollout limits;
* model is needed but no explicit model selected;
* output would require unsupported feature.

If all signals are high confidence and no product slot is involved, the system can allow “quick approve,” but still show preview before paid generation.

## 7. Deterministic renderer

### 7.1 Rendering technology recommendation

Use a **Python-orchestrated deterministic renderer** with three specialized components:

1. **Python/OpenCV/Pillow** for frame IO, masks, compositing, image analysis, contact sheets, and simple pixel operations.
2. **SVG/CSS text/vector renderer** through either headless Chromium/Playwright or a Cairo/Pango/Skia stack for deterministic text, shapes, charts, and UI overlays.
3. **ffmpeg** for final export to GIF/WebP/MP4, palette optimization, timing preservation, and video muxing.

Recommended module:

`mos/backend/app/services/animated_templates/renderer/`

Submodules:

* `render_plan.py`
* `frame_renderer.py`
* `text_renderer.py`
* `vector_renderer.py`
* `mask_compositor.py`
* `product_compositor.py`
* `exporter.py`
* `qa_artifacts.py`

The renderer should create a render plan from the manifest and approved request, then render frames to a temp directory. It should never call an AI model itself. AI region generation is a separate upstream step that provides region clips/frames to composite.

### 7.2 Tradeoffs

**Python/OpenCV/Pillow only**

Pros:

* Easy backend integration.
* Good for masks, pixel compositing, frame extraction, diffing, contact sheets.
* Deterministic.
* No Node dependency.

Cons:

* Text rendering fidelity is weaker, especially letter spacing, vertical text, emoji, font fallback, OpenType features, antialiasing, and multiline layout.
* Complex vector/SVG/UI layers become cumbersome.
* Chart path antialiasing may differ from browser/SVG output.

Use for masks, image compositing, QA, and simple overlays. Do not rely on Pillow alone for production typography.

**Node/canvas**

Pros:

* Browser-like canvas model.
* Good ecosystem for PNG/SVG.
* Could share frontend-ish rendering logic.

Cons:

* Adds Node service/runtime to backend.
* Font metrics can differ by platform.
* Canvas text still less expressive than HTML/SVG/CSS for complex typography.
* Harder to integrate with existing Python Temporal activities.

Do not choose as primary for first backend implementation unless the team already has Node render infrastructure.

**ffmpeg filtergraph**

Pros:

* Excellent for video timing, overlays, masks, palette generation, WebP/GIF/MP4 export.
* Efficient for compositing prepared clips.

Cons:

* Terrible for maintainable text/layout logic.
* Complex filtergraphs become brittle.
* Hard to inspect and review layer-by-layer.
* Text rendering with drawtext depends on font setup and is awkward for precise UI/charts.

Use ffmpeg for export and possibly simple overlay composition, not for manifest rendering.

**Browser/canvas / headless Chromium**

Pros:

* Best practical fidelity for text layout, CSS transforms, SVG paths, shapes, and UI chrome.
* Can render each frame from HTML/SVG templates.
* Supports web fonts when available.
* Strong for review previews because frontend can understand similar primitives.

Cons:

* Headless browser dependency.
* Need strict sandboxing/timeouts.
* Font availability must be controlled.
* More overhead per frame if not optimized.

Recommendation: use headless Chromium or a Skia/Pango/Cairo stack for deterministic vector/text layer rendering, orchestrated from Python. For first implementation, a pure SVG document per frame rendered by `resvg`/CairoSVG/Chromium screenshot is practical. If exact text metrics become critical, prefer Pango/Cairo or Chromium with explicit CSS and font files.

### 7.3 Text rendering fidelity

Text must preserve:

* box,
* rotation,
* anchor,
* alignment,
* font family or fallback,
* font size,
* weight,
* letter spacing,
* line height,
* text transform,
* fill/stroke,
* opacity,
* shadow/glow if source has it,
* visibility timing.

Implement `TextRenderer`:

```python
class TextRenderer:
    def render_text_layer(self, layer, frame_time_ms, context) -> RenderedLayer:
        ...
    def fit_text(self, text, box, style, overflow_policy) -> FittedText:
        ...
    def validate_text_fit(self, layer, target_text) -> list[RenderIssue]:
        ...
```

Text fit rules:

* `review_required`: fail if text does not fit within max shrink threshold.
* `shrink_to_fit`: shrink only down to `minFontSizePx` and record applied shrink.
* `clip_like_source`: clip with layer mask if source appears clipped.
* `wrap_like_source`: wrap using source line count and line breaks.
* `preserve_box`: never expand the text box unless human approved.

For vertical labels, use rotation transforms rather than rendering vertical glyph stacking unless the source used vertical glyph stacking.

### 7.4 Font handling

Fonts come from:

* design system tokens,
* uploaded brand fonts if available,
* known system fallback mapping,
* source-matched inferred font family category.

The system must not invent exact font names when unknown. Use:

```json
"fontFamily": "source_match_sans_condensed_bold",
"fontFallbackStack": ["Inter", "Arial", "Helvetica", "sans-serif"],
"fontResolution": {
  "status": "fallback_used|brand_font_used|source_font_unknown",
  "reviewRequired": false
}
```

If a font is required for fidelity and not available, mark review-required or use approved fallback with QA warning. Store font assets privately in media storage or local deployment, never expose font files through generated artifacts.

### 7.5 SVG/vector layer handling

Use SVG for:

* chart paths,
* axes,
* gridlines,
* badges,
* icons when vectorized,
* UI boxes,
* dividers,
* simple shapes,
* masks.

Path layer schema:

```json
{
  "type": "path",
  "content": {
    "pathData": "M 100 800 C ...",
    "pathCoordinateSpace": "canvas",
    "drawMode": "stroke|fill|stroke_fill"
  },
  "style": {
    "strokeColorRole": "primaryLine",
    "strokeWidthPx": 8,
    "strokeLinecap": "round",
    "strokeLinejoin": "round",
    "fillColorRole": null
  },
  "motion": {
    "type": "path_draw",
    "keyframes": [...]
  }
}
```

For path draw animation, calculate path length and render with stroke-dasharray/stroke-dashoffset per frame. For chart point markers, render markers as shape layers keyed to path progress.

### 7.6 Chart/path animation

Renderer should support:

* path draw-on,
* animated markers,
* animated labels,
* counter increments,
* bar chart growth,
* line color swaps,
* axis/grid locks.

Do not allow model-generated chart layers. QA should compare:

* extracted source path vs rendered path,
* number of points/markers,
* label positions,
* color roles,
* timing of reveal.

For item `05`, the renderer should draw:

* background,
* axes/grid if present,
* vertical `ENERGY LEVEL`,
* horizontal `TIME OF DAY`,
* tick labels,
* `NORMAL CRASH`,
* `WITH TENOR` if approved as brand swap from `WITH MARS MEN`,
* white comparison line,
* brand red line,
* exact path progress timing,
* no product.

### 7.7 Masks

Masks support:

* binary PNG alpha,
* polygon,
* RLE,
* per-frame masks,
* feather/dilate/erode settings,
* inverse masks.

Mask compositing rules:

* Generated region frames are clipped to mask.
* Deterministic overlays can sit above generated region.
* Product replacement can include occlusion masks and shadow/highlight layers.
* QA verifies generated region has no nontransparent pixels outside mask.

### 7.8 Product replacement rendering

Product replacement is deterministic.

Inputs:

* approved product slot,
* target product asset,
* product alpha mask or extracted product silhouette,
* slot box/mask,
* perspective quad,
* occlusion mask,
* shadow/highlight source layers.

Steps:

1. Validate product slot evidence and approval.
2. Validate target product asset exists and is ready.
3. Validate form-factor compatibility:

   * pouch-to-pouch,
   * bottle-to-bottle,
   * box-to-box,
   * or human-approved mismatch.
4. Extract target product foreground if not already transparent.
5. Fit target product to slot:

   * preserve source slot aspect unless form factor needs padding,
   * apply perspective transform if quad exists,
   * scale/rotate to match source,
   * apply mask and occlusion.
6. Apply deterministic shadow/highlight:

   * source-derived shadow layer if available,
   * simple alpha blur shadow if manifest allows.
7. Render product above/below proper z-index.
8. QA:

   * no product if slot not approved,
   * product within mask,
   * no model-rendered product if deterministic overlay required.

Do not attach product assets to generative models unless `productReplacement.replacementMode` explicitly requires a masked generative background with product slot present. Even then, the model should not render readable product label text; deterministic overlay should own final packshot.

### 7.9 GIF/WebP/MP4 export

Implement `exporter.py`:

```python
def export_gif(frame_paths, frame_delays_ms, output_path, palette_mode="adaptive"):
    ...
def export_webp(frame_paths, frame_delays_ms, output_path, quality=80):
    ...
def export_mp4(frame_paths, fps, output_path, crf=18):
    ...
```

GIF export:

* Use ffmpeg `palettegen` / `paletteuse` for quality.
* Preserve variable frame delays where possible.
* Use source loop count, default loop forever.
* Optimize file size with config:

  * max colors,
  * dither mode,
  * lossy gifsicle if installed and configured.
* Ensure final GIF does not collapse to static.

WebP export:

* Use animated WebP for review and web performance.
* Preserve frame timing.
* Store as `image/webp`.
* Prefer WebP for landing-page delivery if frontend supports it.

MP4 export:

* Create square/portrait preview MP4 for review and social compatibility.
* H.264 yuv420p.
* Use fps derived from timeline or render request.
* MP4 cannot preserve variable frame delays exactly; use resampling with recorded method.

### 7.10 Color management

Assume sRGB unless source says otherwise. Normalize frames to sRGB for rendering. Store source color metadata. Avoid AI-generated color approximation for roles. QA samples color roles and compares target rendered colors to exact hex values within tolerance.

### 7.11 Renderer failure behavior

Renderer must fail cleanly when:

* manifest invalid,
* approved target copy missing,
* required brand color missing,
* font unavailable and no approved fallback,
* product slot requested but not approved,
* product asset missing/unready,
* source frames missing,
* generated region frames missing or wrong duration,
* mask dimensions mismatch,
* output export fails,
* QA finds policy violation.

No silent fallback to static image rendering, no automatic model switch, no auto-insertion.

## 8. AI model integration

### 8.1 When to call Sora/Veo/image models

Call an AI model only for layers with `policy="generative_region"` and `rendering.owner="ai_region_model"`.

Do not call a model when:

* manifest has zero generative regions;
* template is chart/counter/text-heavy and all changes are deterministic;
* product slot is not approved;
* requested model is missing and generation would require one;
* selected model does not support the required masked input, duration, resolution, or reference mode.

For initial rollout, support three AI region modes:

1. **Still background generation** for a static masked background region.
2. **Keyframe generation** for a region that remains still or can be tweened.
3. **Video region generation** for a masked UGC/lifestyle region.

The model may generate:

* background texture,
* photographic subject motion,
* lifestyle scene behind deterministic overlays,
* post media area in social screenshot,
* customer/photo tile content,
* before/after panel imagery if claims are approved.

The model may not generate:

* locked text,
* charts,
* axes,
* counters,
* badges,
* UI chrome,
* logos,
* product labels,
* product packshots unless explicitly allowed by manifest, and even then deterministic overlay is preferred.

### 8.2 Passing masked references

For each generative region, create a region generation packet:

```json
{
  "regionId": "ugc_background_region",
  "modelProvider": "creative_service|openai|google|other",
  "modelId": "sora-2",
  "durationMs": 2860,
  "aspectRatio": "1:1",
  "canvasSize": [996, 996],
  "regionBox": [0, 0, 996, 996],
  "maskStorageKey": "...",
  "sourceKeyframes": [
    { "frameIndex": 0, "storageKey": "...", "timeMs": 0 },
    { "frameIndex": 8, "storageKey": "...", "timeMs": 1400 }
  ],
  "negativeMasks": [
    "locked_text_mask",
    "product_slot_mask",
    "ui_chrome_mask"
  ],
  "lockedLayerSummary": {
    "modelMustNotRender": ["text", "chart", "product", "ui_chrome", "badges"]
  },
  "prompt": "...",
  "attachments": []
}
```

If product slot is absent, product references are not included. The attached model comparison prompt already states product references should be attached only when `productReplacement.hasCompetitorProductSlot` is true.

### 8.3 Avoiding model-rendered text/charts/products

Implement prompt construction with hard constraints plus mechanical safeguards:

* Provide cropped/masked source references where locked text/charts/products are masked out.
* Attach negative masks for locked layers.
* Use prompts that say “generate only pixels inside region X; deterministic renderer will draw text/charts/products.”
* Do not include final on-screen text in model prompt except as “do not render.”
* Do not attach product images unless manifest product slot allows it.
* Postprocess model output:

  * OCR generated region; fail if unexpected readable text appears.
  * Detect product-like objects; fail if no product slot allowed.
  * Detect chart-like geometry inside generated region when chart locked; fail.
  * Check mask leakage.

### 8.4 Cost accounting

Add cost estimate endpoint and recording.

Cost dimensions:

* analysis:

  * local CPU time,
  * optional vision model calls for classification if configured,
  * OCR compute.
* deterministic render:

  * frame count,
  * canvas size,
  * output formats.
* AI region generation:

  * provider,
  * model,
  * duration seconds,
  * resolution,
  * number of regions,
  * number of attempts,
  * reference assets.
* QA:

  * local compute,
  * optional judge model if configured.

Cost schema:

```json
{
  "estimateVersion": 1,
  "analysis": {
    "requiresPaidModel": false,
    "estimatedUsd": 0
  },
  "deterministicRender": {
    "frameCount": 16,
    "outputFormats": ["gif", "webp", "mp4"],
    "estimatedUsd": 0
  },
  "aiRegions": [
    {
      "regionId": "ugc_region",
      "provider": "creative_service",
      "modelId": "sora-2",
      "durationSeconds": 3,
      "estimatedUsd": 1.2
    }
  ],
  "totalEstimatedUsd": 1.2,
  "modelCallsRequired": true
}
```

Record actual cost in `AnimatedTemplateRun.cost_actual_json` and `ai_metadata.cost`.

### 8.5 Provider abstraction

Create:

`mos/backend/app/services/animated_templates/ai_region_client.py`

Protocol:

```python
class AnimatedRegionGenerationClient(Protocol):
    def generate_region(
        self,
        *,
        request: AnimatedRegionGenerationRequest,
        idempotency_key: str,
    ) -> AnimatedRegionGenerationResult:
        ...
```

Result:

```python
@dataclass
class AnimatedRegionGenerationResult:
    provider: str
    model_id: str
    remote_run_id: str | None
    output_kind: Literal["video", "image_sequence", "image"]
    output_url: str | None
    output_storage_key: str | None
    local_frame_storage_keys: list[str]
    duration_ms: int
    cost_metadata: dict
    prompt_sha256: str
```

Adapters:

* `CreativeServiceAnimatedRegionClient` using existing `CreativeServiceClient` video sessions.
* `OpenAIAnimatedRegionClient` only if supported for still/keyframe regions.
* Future `GoogleVeoAnimatedRegionClient`.

No adapter may switch models. If requested model unsupported, return a structured `UnsupportedAnimatedRegionModelError`.

### 8.6 No fallback model switching

Hard rule:

```python
if requested_model_id != actual_model_id:
    raise RuntimeError("Animated region provider returned a different model than requested.")
```

If provider fails:

* record failure,
* return clean error,
* allow user to manually retry with the same or different authorized model,
* never automatically pick a fallback.

This is consistent with the non-negotiable constraints and the static path’s explicit model guard.

## 9. Backend module-by-module implementation plan

### 9.1 `mos/backend/app/routers/swipes.py`

Add animated endpoints under `/swipes` to keep source-template workflow near existing swipe functionality.

New imports:

```python
from app.schemas.animated_templates import (
    AnimatedTemplateAnalyzeRequest,
    AnimatedTemplateAnalyzeResponse,
    AnimatedTemplateApprovalRequest,
    AnimatedTemplateManifestResponse,
    AnimatedTemplateRenderRequest,
    AnimatedTemplateRenderResponse,
    AnimatedTemplateCostEstimateRequest,
    AnimatedTemplateCostEstimateResponse,
)
from app.temporal.workflows.swipe_animated_template import (
    SwipeAnimatedTemplateAnalysisWorkflow,
    SwipeAnimatedTemplateAnalysisInput,
    SwipeAnimatedTemplateRenderWorkflow,
    SwipeAnimatedTemplateRenderInput,
)
from app.db.repositories.animated_templates import AnimatedTemplatesRepository
```

Add helper:

```python
async def _start_swipe_animated_template_analysis_run(...)
async def _start_swipe_animated_template_render_run(...)
```

Endpoints:

```python
@router.post("/animated-templates/analyze")
async def analyze_animated_template(...)

@router.get("/animated-templates/{manifest_id}")
def get_animated_template_manifest(...)

@router.patch("/animated-templates/{manifest_id}")
def update_animated_template_manifest(...)

@router.post("/animated-templates/{manifest_id}/approve")
def approve_animated_template_manifest(...)

@router.post("/animated-templates/{manifest_id}/reject")
def reject_animated_template_manifest(...)

@router.post("/animated-templates/{manifest_id}/cost-estimate")
def estimate_animated_template_cost(...)

@router.post("/animated-templates/{manifest_id}/render")
async def render_animated_template(...)

@router.get("/animated-templates/runs/{run_id}")
def get_animated_template_run(...)

@router.get("/animated-templates")
def list_animated_template_manifests(...)
```

Behavior:

* `analyze` creates a `WorkflowRun(kind="swipe_animated_template_analysis")`.
* `render` requires manifest status approved and approved version match.
* `render` creates `WorkflowRun(kind="swipe_animated_template_render")`.
* `approve` validates manifest before setting approved.
* `patch` supports user corrections but must create a new manifest version or event. For simple edits, mutate draft manifest and update `manifest_sha256`; for approved manifests, create a superseding draft.

Do not modify `generate_image_ad_from_swipe` except for shared imports. The static endpoint remains unchanged.

### 9.2 `mos/backend/app/schemas/swipe_image_ads.py`

Keep `SwipeImageAdGenerateRequest` unchanged. Do not add animated fields here. The current model guard is correct and should remain.

Potential minimal addition:

* none for static.
* If frontend wants shared model guard utilities, move `_is_image_render_model_name` logic to a shared schema validator module, but do not change existing request behavior.

### 9.3 New `mos/backend/app/schemas/animated_templates.py`

Define Pydantic schemas for API and manifest validation.

Core API schemas:

```python
class AnimatedTemplateSource(BaseModel):
    company_swipe_id: str | None = Field(None, alias="companySwipeId")
    company_swipe_media_id: str | None = Field(None, alias="companySwipeMediaId")
    source_url: str | None = Field(None, alias="sourceUrl")

    @model_validator(mode="after")
    def validate_exactly_one_source(self): ...

class AnimatedTemplateAnalyzeRequest(BaseModel):
    client_id: str = Field(..., alias="clientId")
    product_id: str | None = Field(None, alias="productId")
    campaign_id: str | None = Field(None, alias="campaignId")
    asset_brief_id: str | None = Field(None, alias="assetBriefId")
    requirement_index: int | None = Field(None, alias="requirementIndex")
    source: AnimatedTemplateSource
    analyzer_version: str | None = Field(None, alias="analyzerVersion")
    force_reanalysis: bool = Field(False, alias="forceReanalysis")
    review_mode: Literal["required", "auto"] = Field("required", alias="reviewMode")
```

Render request:

```python
class AnimatedTemplateRenderRequest(BaseModel):
    client_id: str = Field(..., alias="clientId")
    product_id: str = Field(..., alias="productId")
    campaign_id: str | None = Field(None, alias="campaignId")
    asset_brief_id: str = Field(..., alias="assetBriefId")
    requirement_index: int = Field(0, alias="requirementIndex")
    approved_manifest_version: int = Field(..., alias="approvedManifestVersion")

    output_formats: list[Literal["gif", "webp", "mp4"]] = Field(default_factory=lambda: ["gif", "webp"])
    render_mode: Literal["deterministic", "hybrid"] = Field("deterministic", alias="renderMode")
    aspect_ratio: str | None = Field(None, alias="aspectRatio")
    final_copy: dict[str, Any] | None = Field(None, alias="finalCopy")
    model_selection: AnimatedTemplateModelSelection | None = Field(None, alias="modelSelection")
    count: int = Field(1, ge=1, le=6)
```

Model selection validator:

* If `renderMode="hybrid"` and manifest has generative regions, model selection required.
* If model selection exists but manifest has no generative region, either ignore with warning? Better: error unless `allowUnusedModelSelection=true`. This prevents users thinking a model was used.

Manifest response:

```python
class AnimatedTemplateManifestResponse(BaseModel):
    id: str
    status: str
    analysisStatus: str
    source: dict
    manifest: dict
    previewUrls: dict
    reviewRequired: bool
    reviewReasons: list[str]
    productSlotSummary: dict
    renderModeRecommended: str
    aiRequired: bool
    createdAt: datetime
    updatedAt: datetime
```

Error schema:

```python
class AnimatedTemplateError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}
```

Manifest Pydantic models:

* `AnimatedTemplateManifestModel`
* `ManifestSource`
* `ManifestCanvas`
* `ManifestTimeline`
* `ManifestLayer`
* `ManifestMask`
* `ManifestColorRole`
* `ManifestTextRole`
* `ManifestProductReplacement`
* `ManifestReview`

Implement semantic validation in a service too; Pydantic should handle structural validation only.

### 9.4 `mos/backend/app/schemas/asset_brief_types.py`

Add support for animated image:

```python
SUPPORTED_ASSET_BRIEF_TYPES = ("image", "animated_image", "video")
```

But consider naming. Recommended canonical value: `"animated_image"`.

Normalize aliases:

* `"gif"` -> `"animated_image"`
* `"animated"` -> `"animated_image"`
* `"animated_image"` -> `"animated_image"`
* `"animated-image"` -> `"animated_image"`

This file currently only normalizes exact supported values. Add helper:

```python
def normalize_asset_brief_type(value: str) -> str:
    ...
```

Then use it in required/optional normalization.

### 9.5 `mos/backend/app/schemas/asset_brief.py`

`AssetRequirement.format` is already a string, so no change required structurally. Add docs/comments or validation elsewhere to recognize `"animated_image"`.

### 9.6 `mos/backend/app/schemas/creative_generation.py`

Add new plan schemas or extend existing.

Option A: extend `CreativeGenerationPlanItem` with optional animated fields. This is lower migration cost but mixes static and animated.

Option B: add `AnimatedCreativeGenerationPlanItem`. Recommended for clarity.

```python
class AnimatedCreativeGenerationPlanItem(BaseModel):
    id: str
    batch_id: str = Field(alias="batchId")
    asset_brief_id: str = Field(alias="assetBriefId")
    requirement_index: int = Field(alias="requirementIndex")
    channel: str
    format: Literal["animated_image"]
    ...
    company_swipe_id: str = Field(alias="companySwipeId")
    source_media_id: str | None = Field(default=None, alias="sourceMediaId")
    source_label: str = Field(alias="sourceLabel")
    source_media_url: str = Field(alias="sourceMediaUrl")
    source_mime_type: str | None = Field(default=None, alias="sourceMimeType")
    copy_pack_id: str = Field(alias="copyPackId")
    template_manifest_id: str | None = Field(default=None, alias="templateManifestId")
    template_manifest_status: str | None = Field(default=None, alias="templateManifestStatus")
    source_set_key: str = Field(alias="sourceSetKey")
```

Add `AnimatedCreativeGenerationPlanArtifact` or add `animatedItems` to existing `CreativeGenerationPlanArtifact`.

Recommended phased approach:

* Phase 1 manual animated endpoints do not touch campaign plan.
* Phase 2 add `animatedItems` to plan artifact.

### 9.7 `mos/backend/app/temporal/activities/swipe_image_ad_activities.py`

Do not add animated generation into this file. It is already large and static-specific. Make limited changes:

1. Extract reusable helpers into shared modules if needed:

   * `_download_bytes` -> `app.services.media_download.download_bytes`.
   * `_optional_clean_string` -> shared utility.
   * product reference asset selection remains in `asset_activities.py` for now.
2. Keep `_is_image_render_model_name` and stage-one prompt guard.
3. Do not allow GIF/video assets to sneak into static path. Add a stricter check after `_resolve_swipe_image`:

   * if `swipe_mime_type == "image/gif"` and source has multiple frames, raise a clean error for static path unless explicitly treating first frame is supported;
   * message: “Animated swipe media is not supported by `/swipes/generate-image-ad`; use `/swipes/animated-templates/analyze`.”
4. Preserve existing metadata and static behavior.

### 9.8 New `mos/backend/app/temporal/activities/swipe_animated_template_activities.py`

Define activities:

```python
@activity.defn(name="swipes.resolve_animated_template_source")
def resolve_animated_template_source_activity(params): ...

@activity.defn(name="swipes.extract_animated_template_metadata")
def extract_animated_template_metadata_activity(params): ...

@activity.defn(name="swipes.sample_animated_template_frames")
def sample_animated_template_frames_activity(params): ...

@activity.defn(name="swipes.analyze_animated_template_layers")
def analyze_animated_template_layers_activity(params): ...

@activity.defn(name="swipes.build_animated_template_manifest")
def build_animated_template_manifest_activity(params): ...

@activity.defn(name="swipes.validate_animated_template_manifest")
def validate_animated_template_manifest_activity(params): ...

@activity.defn(name="swipes.persist_animated_template_manifest")
def persist_animated_template_manifest_activity(params): ...

@activity.defn(name="swipes.prepare_animated_template_render_plan")
def prepare_animated_template_render_plan_activity(params): ...

@activity.defn(name="swipes.generate_animated_template_regions")
def generate_animated_template_regions_activity(params): ...

@activity.defn(name="swipes.render_animated_template")
def render_animated_template_activity(params): ...

@activity.defn(name="swipes.qa_animated_template_output")
def qa_animated_template_output_activity(params): ...

@activity.defn(name="swipes.persist_animated_template_outputs")
def persist_animated_template_outputs_activity(params): ...
```

Keep each activity idempotent. Persist intermediate artifacts after each expensive stage.

### 9.9 `mos/backend/app/temporal/activities/asset_activities.py`

Changes:

1. Update `_SUPPORTED_FORMATS` to include `"animated_image"`.
2. Update `_normalize_requirement_format`.
3. Update `resolve_default_swipe_collection_activity` only if campaign default collection needs animated counts. It currently asks for ready image assets. Keep static default behavior for image. Add separate resolver for animated:

   * `resolve_default_animated_swipe_collection_activity`, or
   * pass required formats.
4. In `_resolve_collection_swipe_sources`, do not change static behavior. Add new function:

```python
def _resolve_collection_animated_swipe_sources(...):
    # accept image/gif, animated webp, video
    # reject static images unless static-to-animated allowed
```

5. Add dataclass:

```python
@dataclass(frozen=True)
class _AnimatedPlanItemExecution:
    requirement_index: int
    plan_item: AnimatedCreativeGenerationPlanItem
    copy_pack_id: str
```

6. Add `_generate_animated_plan_item_asset` that starts or directly calls the animated render activity/workflow.
7. In `generate_assets_for_brief_activity`, branch:

```python
if normalized_format == "image":
    existing static
elif normalized_format == "animated_image":
    animated template path
elif normalized_format == "video":
    existing video
```

8. For animated path, if manifest not approved, return/record a review-required state rather than failing the entire production batch if product policy allows staged review. There are two choices:

   * conservative first phase: fail with clear message listing manifest review URLs;
   * better product flow: create analysis workflow items and return workflow status `review_required`.

For initial integration, implement:

* `generate_assets_for_brief_activity` creates/starts analysis for animated items and returns a clean `ApplicationError(type="AnimatedTemplateReviewRequired", non_retryable=True)` containing manifest IDs and review URLs.
* Later add resumable production after approvals.

9. Add `_create_generated_asset_from_bytes` shared helper.

### 9.10 `mos/backend/app/services/creative_service_client.py`

Existing video and asset upload methods are useful. Add no silent fallback.

Add optional methods only if creative service exposes masked region endpoints. If not, use existing video session API through a new adapter.

Potential addition:

```python
def create_masked_video_region(...)
```

Only add if API exists. Otherwise do not fake it.

### 9.11 `mos/backend/app/services/video_ads_orchestrator.py`

Do not change `run_variant` semantics for generic video. Add a new constrained method or a new class.

Recommended new class in a new file:

`mos/backend/app/services/animated_templates/creative_service_region_client.py`

It can use `CreativeServiceClient.create_video_session` and `create_video_message` but with region-specific prompts, attachments, and postprocessing.

If modifying `video_ads_orchestrator.py`, add:

```python
def run_masked_region(
    self,
    *,
    title: str,
    region_prompt: str,
    region_context: dict[str, Any],
    attachments: list[CreativeServiceVideoAttachmentIn],
    session_idempotency_key: str,
    turn_idempotency_prefix: str,
) -> VideoVariantResult:
    ...
```

It should not reuse `build_initial_video_message`, which is generic full-video ad copy. Create a new `build_masked_region_message`.

### 9.12 `mos/backend/app/services/image_render_client.py`

Leave static image render client intact. Add a guard or documentation that it is not for animated templates.

Create separate:

`mos/backend/app/services/animated_templates/renderer_client.py`

The deterministic renderer is local and should not implement `ImageRenderClient` because its input/output contract is a manifest/render plan, not a text prompt.

### 9.13 Media storage

Extend storage helpers:

* `store_animated_source_bytes`
* `store_extracted_frame`
* `store_mask_png`
* `store_contact_sheet`
* `store_render_output_bytes`
* `build_animated_template_storage_prefix`

Storage key pattern:

```text
{MEDIA_STORAGE_PREFIX}/animated_templates/{org_id}/{source_sha256}/source/orig.{ext}
{MEDIA_STORAGE_PREFIX}/animated_templates/{org_id}/{source_sha256}/analysis/{manifest_id}/frames/frame_0000.png
{MEDIA_STORAGE_PREFIX}/animated_templates/{org_id}/{source_sha256}/analysis/{manifest_id}/masks/{mask_id}.png
{MEDIA_STORAGE_PREFIX}/animated_templates/{org_id}/{source_sha256}/runs/{run_id}/outputs/final.gif
```

Use hash-based keys for immutable content when possible. For run outputs, include content hash in filename or metadata.

### 9.14 Repositories

New:

`mos/backend/app/db/repositories/animated_templates.py`

Methods:

```python
class AnimatedTemplatesRepository:
    def get_manifest(...)
    def get_manifest_by_idempotency(...)
    def find_approved_manifest_for_source(...)
    def create_manifest(...)
    def update_manifest(...)
    def approve_manifest(...)
    def reject_manifest(...)
    def create_manifest_event(...)
    def list_manifests(...)
    def create_run(...)
    def get_run(...)
    def get_run_by_idempotency(...)
    def update_run(...)
    def list_runs(...)
    def create_artifact(...)
    def list_artifacts(...)
```

Repository must enforce org scoping. Approval must check manifest status and version.

### 9.15 Workflows

New:

`mos/backend/app/temporal/workflows/swipe_animated_template.py`

Define two workflows:

* `SwipeAnimatedTemplateAnalysisWorkflow`
* `SwipeAnimatedTemplateRenderWorkflow`

Use granular retry policies:

```python
_NO_RETRY = RetryPolicy(maximum_attempts=1)
_IO_RETRY = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=2), maximum_interval=timedelta(seconds=30))
_RENDER_RETRY = RetryPolicy(maximum_attempts=1)
_MODEL_RETRY = RetryPolicy(maximum_attempts=1)
```

Analysis can retry downloads/probe on transient IO. Model calls and deterministic render should not retry in ways that hide failures unless idempotency is exact.

### 9.16 Config/env

Add settings to `mos/backend/app/config.py`:

```python
ANIMATED_TEMPLATE_ENABLED: bool = False
ANIMATED_TEMPLATE_CAMPAIGN_PRODUCTION_ENABLED: bool = False
ANIMATED_TEMPLATE_ANALYZER_VERSION: str = "animated-template-analyzer-v1"
ANIMATED_TEMPLATE_RENDERER_VERSION: str = "animated-template-renderer-v1"

ANIMATED_TEMPLATE_SOURCE_MAX_BYTES: int = 100 * 1024 * 1024
ANIMATED_TEMPLATE_DOWNLOAD_TIMEOUT_SECONDS: float = 60.0
ANIMATED_TEMPLATE_FFPROBE_TIMEOUT_SECONDS: float = 30.0
ANIMATED_TEMPLATE_FFMPEG_TIMEOUT_SECONDS: float = 300.0
ANIMATED_TEMPLATE_MAX_SOURCE_FRAMES: int = 600
ANIMATED_TEMPLATE_MAX_RENDER_FRAMES: int = 180
ANIMATED_TEMPLATE_MAX_DURATION_SECONDS: float = 10.0

ANIMATED_TEMPLATE_FRAME_SAMPLE_MAX: int = 32
ANIMATED_TEMPLATE_REVIEW_REQUIRED_DEFAULT: bool = True
ANIMATED_TEMPLATE_PRODUCT_SLOT_CONFIDENCE_THRESHOLD: float = 0.75
ANIMATED_TEMPLATE_OCR_CONFIDENCE_THRESHOLD: float = 0.70
ANIMATED_TEMPLATE_MOTION_CONFIDENCE_THRESHOLD: float = 0.70

ANIMATED_TEMPLATE_EXPORT_GIF_ENABLED: bool = True
ANIMATED_TEMPLATE_EXPORT_WEBP_ENABLED: bool = True
ANIMATED_TEMPLATE_EXPORT_MP4_ENABLED: bool = True

ANIMATED_TEMPLATE_AI_REGION_ENABLED: bool = False
ANIMATED_TEMPLATE_DEFAULT_AI_PROVIDER: str | None = None
ANIMATED_TEMPLATE_DEFAULT_AI_MODEL: str | None = None
ANIMATED_TEMPLATE_ALLOW_MODEL_RENDERED_TEXT: bool = False
ANIMATED_TEMPLATE_ALLOW_UNAPPROVED_PRODUCT_SLOT: bool = False
```

The last flag should default false and should never be enabled in production. It can be omitted entirely to avoid unsafe behavior.

### 9.17 Observability/logging

Use `WorkflowsRepository.log_activity` as current static path does. Add logs:

* `animated_template_analysis.started`
* `animated_template_analysis.source_resolved`
* `animated_template_analysis.frames_extracted`
* `animated_template_analysis.layers_detected`
* `animated_template_analysis.manifest_persisted`
* `animated_template_review.approved`
* `animated_template_render.started`
* `animated_template_render.ai_regions_generated`
* `animated_template_render.deterministic_render_completed`
* `animated_template_render.qa_completed`
* `animated_template_render.assets_persisted`

Langfuse:

* trace analysis LLM/vision assistance if any,
* trace AI region generation prompts,
* do not trace full sensitive source images unless current policies allow.

Metrics:

* analysis duration,
* render duration,
* frame count,
* source bytes,
* output bytes,
* review-required rate,
* product-slot false positive rate,
* QA fail rate,
* AI cost.

### 9.18 Tests

Backend test files:

* `tests/test_animated_template_schema.py`
* `tests/test_animated_template_manifest_validation.py`
* `tests/test_animated_template_product_slot_policy.py`
* `tests/test_animated_template_analysis_workflow.py`
* `tests/test_animated_template_renderer.py`
* `tests/test_animated_template_api.py`
* `tests/test_asset_activities_animated_requirements.py`
* `tests/test_swipes_static_rejects_animated_media.py`

Golden fixtures:

* chart GIF with no product slot,
* product badge GIF with product slot,
* social UI GIF/video,
* before/after panel,
* customer collage,
* UGC/lifestyle masked region.

Test the Mars item `05` expected manifest:

* `hasCompetitorProductSlot=false`,
* no product layers,
* chart paths deterministic,
* text layers detected,
* no AI regions required,
* render output contains no product-like object insertion.

## 10. Frontend module-by-module implementation plan

### 10.1 Typed API client: `mos/frontend/src/api/swipes.ts`

Add types imported from `@/types/animatedTemplates`.

Add query keys:

```ts
export const ANIMATED_TEMPLATE_MANIFESTS_QUERY_KEY = ["swipes", "animated-templates"] as const;
export const animatedTemplateManifestQueryKey = (manifestId?: string | null) =>
  ["swipes", "animated-template", manifestId] as const;
export const animatedTemplateRunQueryKey = (runId?: string | null) =>
  ["swipes", "animated-template-run", runId] as const;
```

Add hooks:

```ts
export function useAnimatedTemplateManifest(manifestId?: string | null, enabled = true) { ... }
export function useAnimatedTemplateRun(runId?: string | null, enabled = true) { ... }
export function useAnimatedTemplateApi() {
  return {
    analyzeAnimatedTemplate,
    updateAnimatedTemplateManifest,
    approveAnimatedTemplateManifest,
    rejectAnimatedTemplateManifest,
    estimateAnimatedTemplateCost,
    renderAnimatedTemplate,
  };
}
```

Invalidate relevant query keys after approval/render.

### 10.2 `mos/frontend/src/types/animatedTemplates.ts`

New file.

Types:

* `AnimatedTemplateManifest`
* `AnimatedTemplateLayer`
* `AnimatedTemplateMask`
* `AnimatedTemplateProductSlot`
* `AnimatedTemplateReview`
* `AnimatedTemplateAnalyzeRequest`
* `AnimatedTemplateAnalyzeResponse`
* `AnimatedTemplateApprovalRequest`
* `AnimatedTemplateRenderRequest`
* `AnimatedTemplateRenderResponse`
* `AnimatedTemplateRun`
* `AnimatedTemplateCostEstimate`

Keep fields camelCase to match API schemas.

### 10.3 `mos/frontend/src/types/swipes.ts`

Extend:

```ts
export type SwipeAssetType = "image" | "animated_image" | "video" | "carousel" | "unknown";
```

Update `GetHookdInboxSummary.defaultAssetType`.

Ensure existing switch statements handle the new value.

### 10.4 `mos/frontend/src/lib/assetBriefTypes.ts`

Add:

```ts
export type AssetBriefType = "image" | "animated_image" | "video";

export const ASSET_BRIEF_TYPE_OPTIONS = [
  { value: "image", label: "Image" },
  { value: "animated_image", label: "Animated image / GIF" },
  { value: "video", label: "Video" },
];
```

Default can remain `["image"]` until rollout.

### 10.5 Campaign creative generation UI

In `CampaignCreativeTab.tsx`:

* Display animated image briefs distinctly.
* Show source collection readiness by required media types.
* Before calling `POST /campaigns/{id}/creative/produce`, warn if animated briefs are selected but animated feature flag disabled.
* After production starts, if backend returns `AnimatedTemplateReviewRequired`, navigate to a review queue rather than only workflow page.
* Add a panel:

  * “Animated template review required”
  * list manifest previews,
  * product-slot status,
  * approve/reject buttons.

Do not disrupt the existing static path: the current `handleStartCreativeProduction` should still post `assetBriefIds` and `swipeCollectionId`. Backend can return richer payload later; frontend should handle both old `{ workflow_run_id }` and new `{ workflow_run_id, reviewRequiredManifests }`.

### 10.6 Swipe library UI

In `SwipeCollectionSelector.tsx`:

* Add filter option:

  * `{ label: "Animated images / GIFs", value: "animated_image" }`.
* Show badges:

  * `Static image`,
  * `Animated GIF`,
  * `Video`,
  * `Carousel`,
  * `Unknown`.
* Add per-source affordance:

  * “Analyze as animated template” action for GIF/video sources.
* Disable static-only sources for animated-only production if appropriate.
* Surface media duration/frame count when available in `source_metadata_json` or media metadata.

### 10.7 Manifest preview/review UI

Create component directory:

`mos/frontend/src/components/animatedTemplates/`

Components:

* `AnimatedTemplateReviewPage.tsx`
* `AnimatedTemplateManifestPreview.tsx`
* `AnimatedTemplateTimeline.tsx`
* `AnimatedTemplateLayerOverlay.tsx`
* `AnimatedTemplateLayerList.tsx`
* `AnimatedTemplateProductSlotPanel.tsx`
* `AnimatedTemplateTextRolesPanel.tsx`
* `AnimatedTemplateColorRolesPanel.tsx`
* `AnimatedTemplateWarningsPanel.tsx`
* `AnimatedTemplateApprovalBar.tsx`
* `AnimatedTemplateContactSheet.tsx`

Review UI design:

Top row:

* source playback or animated preview,
* overlay toggle,
* frame scrubber,
* contact sheet thumbnails.

Right panel:

* `Review required` status,
* blocking reasons,
* recommended render mode,
* product slot summary,
* AI required summary,
* estimated cost.

Layer list:

* grouped by policy,
* locked layers collapsed by default,
* warnings highlighted,
* click layer to highlight overlay.

Product slot panel:

* `No product slot detected` with negative evidence,
* or slot candidates with boxes/masks,
* approve/reject candidate,
* form-factor display,
* warning: “Product replacement will be disabled until approved.”

Human review speed matters. The UI should not force users to inspect raw JSON first. It should show the highest-risk decisions at top:

1. Product slot decision.
2. Text/copy uncertainties.
3. Generative region masks.
4. Chart/UI layer fidelity.
5. Cost/model calls.

### 10.8 Generated asset review UI

Existing creative review grid should support animated assets.

Add:

* animated thumbnail generation or use WebP/MP4 preview,
* play/pause on hover for GIF/WebP/MP4,
* badges:

  * `Animated template`,
  * `Deterministic`,
  * `Hybrid`,
  * `QA pass/fail`.
* Detail panel should show:

  * source vs output contact sheet,
  * manifest ID,
  * run ID,
  * product-slot status,
  * model calls,
  * QA blockers.

If existing `CreativeReviewGrid` cannot show QA artifacts, add animated template detail tab rather than changing all creative review behavior.

### 10.9 Diff/contact-sheet UI

Create:

`AnimatedTemplateDiffViewer.tsx`

Features:

* side-by-side source/output keyframes,
* onion-skin overlay,
* diff heatmap toggle,
* OCR text verification list,
* timing comparison,
* product policy status.

Human review speed:

* show 6 to 12 keyframes in a contact sheet,
* highlight only changed regions,
* display “No product inserted” or “Product replaced in approved slot” prominently,
* show red blockers before metrics.

### 10.10 Routing

Add routes:

* `/campaigns/:campaignId/animated-templates/:manifestId/review`
* `/campaigns/:campaignId/animated-template-runs/:runId`
* optional `/swipes/animated-templates/:manifestId/review`

### 10.11 Frontend tests

Add tests:

* API hooks call expected endpoints.
* `SwipeAssetType` displays animated image label.
* manifest review product slot approval toggles state.
* render button disabled when manifest not approved.
* cost estimate shows no model cost for deterministic chart template.
* generated asset detail shows contact sheet and QA status.

## 11. API contract plan

### 11.1 Analyze endpoint

`POST /swipes/animated-templates/analyze`

Request:

```json
{
  "clientId": "uuid",
  "productId": "uuid",
  "campaignId": "uuid",
  "assetBriefId": "brief-id",
  "requirementIndex": 0,
  "source": {
    "companySwipeId": "uuid",
    "companySwipeMediaId": "uuid",
    "sourceUrl": null
  },
  "analyzerVersion": null,
  "forceReanalysis": false,
  "reviewMode": "required"
}
```

Response:

```json
{
  "workflowRunId": "uuid",
  "temporalWorkflowId": "swipe-animated-template-analysis-...",
  "manifestId": null,
  "status": "started"
}
```

If existing approved manifest reused:

```json
{
  "workflowRunId": null,
  "temporalWorkflowId": null,
  "manifestId": "uuid",
  "status": "reused_approved_manifest"
}
```

### 11.2 Manifest get endpoint

`GET /swipes/animated-templates/{manifestId}`

Response:

```json
{
  "id": "uuid",
  "status": "needs_review",
  "analysisStatus": "succeeded",
  "source": {
    "sourceLabel": "item-05.gif",
    "mimeType": "image/gif",
    "width": 996,
    "height": 996,
    "durationMs": 2860,
    "frameCount": 16
  },
  "manifestVersion": 1,
  "manifestSha256": "hex",
  "manifest": {},
  "previewUrls": {
    "source": "signed-url",
    "contactSheet": "signed-url",
    "overlayPreview": "signed-url"
  },
  "reviewRequired": true,
  "reviewReasons": ["product_slot_not_detected_no_action_required", "approval_required_before_render"],
  "productSlotSummary": {
    "hasCompetitorProductSlot": false,
    "status": "not_detected",
    "replacementAllowed": false,
    "confidence": 0.0
  },
  "renderModeRecommended": "deterministic",
  "aiRequired": false,
  "createdAt": "...",
  "updatedAt": "..."
}
```

### 11.3 Manifest patch endpoint

`PATCH /swipes/animated-templates/{manifestId}`

Use JSON Patch or a constrained edit payload. Prefer constrained edit payload first:

```json
{
  "expectedManifestVersion": 1,
  "edits": [
    {
      "type": "set_layer_policy",
      "layerId": "layer_1",
      "policy": "copy_swap"
    },
    {
      "type": "update_text_role",
      "textRoleId": "brand_phrase",
      "targetText": "WITH TENOR"
    },
    {
      "type": "reject_product_slot",
      "slotId": "product_slot_candidate_1",
      "reason": "This is a chart label, not a product."
    }
  ]
}
```

Response returns updated draft manifest.

### 11.4 Approval endpoint

`POST /swipes/animated-templates/{manifestId}/approve`

Request:

```json
{
  "expectedManifestVersion": 1,
  "approvalNotes": "Chart template: no product slot. Deterministic render only.",
  "productSlotDecision": {
    "hasCompetitorProductSlot": false,
    "confirmed": true
  }
}
```

Response:

```json
{
  "manifestId": "uuid",
  "status": "approved",
  "approvedAt": "...",
  "approvedByUserId": "..."
}
```

Approval validation must fail if:

* blocking review reasons remain,
* product slot decision not confirmed when product evidence uncertain,
* required target text/colors missing,
* model regions present without masks.

### 11.5 Render endpoint

`POST /swipes/animated-templates/{manifestId}/render`

Request:

```json
{
  "clientId": "uuid",
  "productId": "uuid",
  "campaignId": "uuid",
  "assetBriefId": "brief-id",
  "requirementIndex": 0,
  "approvedManifestVersion": 1,
  "outputFormats": ["gif", "webp", "mp4"],
  "renderMode": "deterministic",
  "aspectRatio": "1:1",
  "finalCopy": {
    "textRoles": {
      "brand_phrase": "WITH TENOR"
    }
  },
  "modelSelection": null,
  "count": 1
}
```

Response:

```json
{
  "workflowRunId": "uuid",
  "temporalWorkflowId": "swipe-animated-template-render-...",
  "runId": "uuid",
  "status": "started"
}
```

### 11.6 Run status endpoint

`GET /swipes/animated-templates/runs/{runId}`

Response:

```json
{
  "id": "uuid",
  "status": "succeeded",
  "manifestId": "uuid",
  "assetIds": ["uuid"],
  "outputUrls": {
    "gif": "signed-url",
    "webp": "signed-url",
    "mp4": "signed-url"
  },
  "qa": {
    "status": "pass",
    "score": 94.5,
    "contactSheetUrl": "signed-url",
    "blockingIssues": [],
    "warnings": []
  },
  "cost": {
    "modelUsd": 0,
    "modelBillableSeconds": 0,
    "deterministicRenderMs": 5200
  }
}
```

### 11.7 Cost estimate endpoint

`POST /swipes/animated-templates/{manifestId}/cost-estimate`

Request:

```json
{
  "approvedManifestVersion": 1,
  "renderMode": "hybrid",
  "outputFormats": ["gif", "webp"],
  "modelSelection": {
    "provider": "creative_service",
    "modelId": "sora-2"
  }
}
```

Response:

```json
{
  "modelCallsRequired": false,
  "renderMode": "deterministic",
  "aiRegions": [],
  "estimatedUsd": 0,
  "warnings": ["No generative regions exist; selected model will not be used."]
}
```

If selected model is unsupported, return error rather than fallback.

### 11.8 Error shape

Use consistent error details:

```json
{
  "error": {
    "code": "PRODUCT_SLOT_REQUIRED",
    "message": "Product replacement was requested, but the approved manifest does not contain a competitor product slot.",
    "details": {
      "manifestId": "uuid",
      "hasCompetitorProductSlot": false,
      "requestedLayerIds": ["product_layer_1"]
    }
  }
}
```

Common codes:

* `ANIMATED_TEMPLATE_DISABLED`
* `SOURCE_NOT_FOUND`
* `UNSUPPORTED_SOURCE_MEDIA_TYPE`
* `SOURCE_TOO_LARGE`
* `FFPROBE_FAILED`
* `FRAME_EXTRACTION_FAILED`
* `MANIFEST_VALIDATION_FAILED`
* `MANIFEST_REVIEW_REQUIRED`
* `MANIFEST_NOT_APPROVED`
* `MANIFEST_VERSION_MISMATCH`
* `PRODUCT_SLOT_REQUIRED`
* `PRODUCT_SLOT_UNCERTAIN`
* `TARGET_COPY_MISSING`
* `TARGET_COLOR_MISSING`
* `UNSUPPORTED_MODEL_FOR_REGION`
* `MODEL_SELECTION_REQUIRED`
* `MODEL_RENDERED_LOCKED_CONTENT`
* `RENDER_FAILED`
* `QA_FAILED`

## 12. Temporal workflow and activity plan

### 12.1 Analysis workflow

`SwipeAnimatedTemplateAnalysisWorkflow.run(input)`

Pseudo-flow:

```python
source = await execute_activity(resolve_animated_template_source_activity, ...)
probe = await execute_activity(extract_animated_template_metadata_activity, ...)
frames = await execute_activity(sample_animated_template_frames_activity, ...)
analysis = await execute_activity(analyze_animated_template_layers_activity, ...)
manifest = await execute_activity(build_animated_template_manifest_activity, ...)
validated = await execute_activity(validate_animated_template_manifest_activity, ...)
preview = await execute_activity(persist_animated_template_preview_artifacts_activity, ...)
record = await execute_activity(persist_animated_template_manifest_activity, ...)
return {"manifest_id": record["manifest_id"], "status": record["status"]}
```

Activity retry policy:

* source resolution: no retry for validation errors, IO retry for download.
* ffprobe/frame extraction: retry once for transient process failure, not for unsupported media.
* analysis/build/validation: no retry unless pure IO issue.
* persistence: retry on DB transient.

### 12.2 Render workflow

`SwipeAnimatedTemplateRenderWorkflow.run(input)`

Pseudo-flow:

```python
manifest = load_approved_manifest
context = resolve_brand_product_copy_context
render_plan = prepare_render_plan
cost = estimate_cost
if render_plan.ai_regions:
    generated_regions = generate_regions
else:
    generated_regions = []
render_outputs = deterministic_render
qa = run_qa
asset_ids = persist_outputs
return result
```

Retry:

* AI generation: maximum attempts 1 by default. User can manually retry.
* deterministic renderer: no automatic retry unless known temp file IO issue.
* export: retry once if ffmpeg transient, but same settings.
* persistence: retry DB/storage.

### 12.3 Idempotency keys

Each activity receives an idempotency key and should check existing records/artifacts.

Analysis:

* `resolve_source` stores original source by source hash.
* `extract_frames` stores frame manifest keyed by source hash + extractor version.
* `manifest` keyed by source hash + analyzer version + schema version.

Render:

* `run` keyed by approved manifest hash + render request hash + model selection.
* `generate_regions` keyed by region hash + selected model + prompt hash.
* `render_frames` keyed by render plan hash + renderer version.
* `export` keyed by rendered frames hash + export settings.
* `asset persistence` keyed by output SHA.

### 12.4 Artifact persistence

Persist early and often:

* source original after download,
* probe JSON,
* frame manifest and contact sheet,
* analysis JSON,
* draft manifest JSON,
* overlay preview,
* render plan,
* generated region outputs,
* final frames optional for QA,
* final outputs,
* QA report/contact sheets.

This prevents reruns from repeating expensive analysis and gives UI partial progress.

### 12.5 Failure modes

Analysis failure examples:

* unsupported MIME type,
* source too large,
* frame extraction fails,
* OCR unavailable,
* product slot uncertain,
* manifest invalid.

Render failure examples:

* manifest not approved,
* version mismatch,
* copy missing,
* brand color missing,
* product slot not approved,
* selected model unsupported,
* model output violates mask,
* renderer fails,
* QA fail.

Failures should update:

* `WorkflowRun` activity log,
* `AnimatedTemplateManifest.analysis_error` or `AnimatedTemplateRun.error_detail`,
* manifest/run events,
* frontend-readable status.

### 12.6 Human review checkpoint

Temporal cannot wait indefinitely inside a workflow for human approval unless using signals. Simpler first implementation:

* Analysis workflow ends after manifest persistence.
* Approval happens through REST endpoint.
* Render workflow starts after approval.

Later enhancement:

* A production workflow can start analysis, return review-required state, and be resumed by a separate render workflow after approval.

## 13. QA and scoring plan

### 13.1 QA artifacts for every generated output

Every generated GIF/WebP/MP4 should have:

1. Source contact sheet.
2. Output contact sheet.
3. Source vs output side-by-side contact sheet.
4. Diff heatmap contact sheet.
5. Layer overlay preview.
6. Product-slot policy report.
7. OCR comparison report.
8. Timing report.
9. Color role report.
10. Final JSON QA report.

The local proposal explicitly calls for side-by-side source vs output contact sheets and separate scoring for generative region quality vs final composite fidelity.

### 13.2 Automated metrics

Metrics:

**Template structural fidelity**

* canvas size match,
* aspect ratio match,
* safe crop match,
* frame count/duration match,
* layer count and z-order consistency.

**Timing fidelity**

* source frame delays vs output delays,
* total duration delta,
* key motion event timing delta,
* loop seam score.

**Visual diff**

* SSIM on locked source regions,
* perceptual hash difference on keyframes,
* edge map difference for UI/charts,
* color histogram delta excluding approved changed regions.

**Text fidelity**

* OCR output text matches expected target text,
* no duplicate unexpected text,
* text boxes match geometry tolerance,
* rotation/orientation match,
* font size within tolerance or approved shrink.

**Chart fidelity**

* path geometry difference,
* marker count,
* axis label positions,
* gridline count,
* series colors.

**Product policy**

* if no product slot, detect no target product/object insertion;
* if product slot approved, product appears only in slot mask;
* product form factor matches approved constraints;
* no product references sent to model when slot false.

**Color roles**

* sampled pixels for brand roles match target hex within tolerance,
* preserved source roles remain within tolerance.

**Generated region constraints**

* generated pixels outside mask below threshold,
* no model-rendered text if disallowed,
* no product-like object if disallowed,
* duration matches.

### 13.3 Scoring model

QA report shape:

```json
{
  "schemaVersion": 1,
  "overallStatus": "pass|warning|fail",
  "weightedScore100": 94.5,
  "scores": {
    "templateFidelity": 96,
    "spatialFidelity": 95,
    "motionFidelity": 92,
    "textFidelity": 98,
    "colorFidelity": 97,
    "productPolicy": 100,
    "copyCompliance": 95,
    "outputUsability": 92
  },
  "blockingIssues": [],
  "warnings": [],
  "metrics": {},
  "artifacts": {}
}
```

Blocking issues:

* product inserted without approved slot,
* locked text rendered incorrectly/unreadable,
* chart geometry changed beyond tolerance,
* extra chart points,
* output duration off by more than threshold,
* required copy missing,
* unsupported claims detected,
* generated region leaks outside mask,
* model used when no model authorized.

Warnings:

* slight font mismatch,
* minor color delta,
* compressed GIF banding,
* small motion drift,
* OCR low confidence but human approved.

### 13.4 Compliance checks

Compliance should check:

* no unsupported claims added,
* no invented numbers/certifications/guarantees,
* no hidden mechanism revealed in feed copy if existing blind-angle rules apply,
* final on-screen copy comes from source-visible text, approved copy pack, or explicit final copy,
* disclaimer present if required by asset brief/product.

Reuse existing `SwipeAdCopyPack` and blackout audit approach where possible, but animated on-screen text should be deterministic and manifest-driven.

### 13.5 Human review optimization

The final review UI should answer five questions quickly:

1. Did it keep the source template?
2. Did it only change approved brand/copy/product elements?
3. Was product inserted only if a source product slot existed?
4. Are text/charts/UI readable and correctly placed?
5. Is the animation timing close enough to source?

Show those answers before detailed metrics.

## 14. Rollout plan

### 14.1 Feature flags

Add flags:

* `ANIMATED_TEMPLATE_ENABLED`
* `ANIMATED_TEMPLATE_CAMPAIGN_PRODUCTION_ENABLED`
* `ANIMATED_TEMPLATE_AI_REGION_ENABLED`
* frontend `VITE_ANIMATED_TEMPLATE_ENABLED`

Phase gates:

* manual analysis only,
* manual deterministic render,
* manual hybrid render,
* campaign production analysis,
* campaign production render.

### 14.2 Pilot 1: deterministic chart template

Template: Mars item `05` or equivalent chart GIF.

Requirements:

* no product slot,
* no AI call,
* deterministic chart/text/color/timing,
* output GIF/WebP,
* QA contact sheets.

Acceptance:

* no Tenor product inserted,
* chart point count unchanged,
* `WITH MARS MEN` -> `WITH TENOR` only if approved,
* labels preserve size/orientation,
* red line exact target brand color,
* duration/frame delays match.

### 14.3 Pilot 2: product/badge template

Template with visible competitor packshot.

Requirements:

* product slot detected with evidence,
* product replacement blocked until human approval,
* deterministic product overlay,
* badge/text deterministic,
* optional background locked.

Acceptance:

* no product insertion before approval,
* product appears only in slot after approval,
* form factor preserved,
* no invented claims.

### 14.4 Pilot 3: customer collage

Template with grid/tile motion and count/rating text.

Requirements:

* tile masks detected,
* grid geometry locked,
* count/rating copy deterministic,
* optional tile image generation or preservation.

Acceptance:

* tile positions/timing preserved,
* no unsupported social proof number invented,
* contact sheet proves grid fidelity.

### 14.5 Pilot 4: UGC/lifestyle motion

Template with captions/UI overlay and moving subject/background.

Requirements:

* captions/UI locked,
* lifestyle region mask generated,
* no text/product rendered by model unless approved,
* deterministic overlays.

Acceptance:

* model output stays inside mask,
* captions readable,
* no product added if no slot,
* motion loops acceptably.

### 14.6 Production migration

After pilots:

1. Add `animated_image` asset brief type in UI.
2. Allow selected swipe collections to include animated sources.
3. Add production review queue for manifests.
4. Add render resume after approval.
5. Add generated animated assets to campaign review.
6. Add Meta/publish compatibility checks if animated GIF/WebP/MP4 requirements are platform-specific.

## 15. Risks and mitigations

### 15.1 Product-slot false positives

Risk: detector marks chart labels, icons, or badges as product slots.

Mitigation:

* multi-signal evidence model,
* negative evidence,
* review-required uncertainty,
* no default product insertion,
* QA object detection after render,
* canonical chart no-product tests.

### 15.2 OCR/text geometry mismatch

Risk: OCR misses text or renderer uses wrong font metrics.

Mitigation:

* show OCR in review,
* require human correction on low confidence,
* use deterministic text fit validation,
* preserve source text boxes,
* use Pango/Chromium/SVG renderer,
* QA OCR final output.

### 15.3 Overfitting to charts

Risk: schema becomes chart-specific.

Mitigation:

* use generic layer primitives,
* chart detection only populates path/text layers,
* template families are classification metadata, not renderer branches,
* pilots cover product/badge, collage, UGC, UI.

### 15.4 Renderer complexity

Risk: deterministic renderer becomes large.

Mitigation:

* start with simple primitives:

  * source region,
  * text,
  * path,
  * shape,
  * image overlay,
  * mask,
  * export.
* Add UI chrome and product perspective later.
* Keep manifest schema stable while adding renderer capabilities.

### 15.5 Model-region drift

Risk: AI region output introduces locked content.

Mitigation:

* masks,
* negative prompts,
* no product references unless slot approved,
* OCR/object detection post-check,
* deterministic overlays on top,
* fail QA rather than ship.

### 15.6 File size and performance

Risk: GIFs become huge or rendering too slow.

Mitigation:

* animated WebP preferred for landing pages,
* GIF palette optimization,
* frame resampling limits,
* max duration/frame count rollout limits,
* background frame reuse,
* caching by render plan hash.

### 15.7 Existing static path regression

Risk: adding animated support breaks static image generation.

Mitigation:

* separate schemas/endpoints/workflows,
* static tests unchanged,
* static path rejects animated media cleanly,
* no modifications to `SwipeImageAdGenerateRequest` beyond none.

### 15.8 Campaign production UX complexity

Risk: production now has review-required steps.

Mitigation:

* manifest review queue,
* batch approve deterministic low-risk manifests,
* show blockers compactly,
* allow deterministic render immediately after approval,
* keep static briefs unaffected.

## 16. Implementation milestones with acceptance criteria

### Milestone 1: schema, DB, repository foundation

Deliver:

* Alembic migration.
* SQLAlchemy models.
* `AnimatedTemplatesRepository`.
* Pydantic schemas.
* Feature flags.

Acceptance:

* migration applies and rolls back locally,
* create/get/list/update manifest works,
* approve/reject events recorded,
* idempotency unique constraints pass tests.

### Milestone 2: source ingestion and frame extraction

Deliver:

* source resolver,
* media probe,
* frame sampler,
* source/contact sheet storage,
* analysis workflow skeleton.

Acceptance:

* GIF source downloads, hashes, probes, extracts frames/delays,
* video source probes and samples frames,
* source artifacts stored,
* unsupported media errors cleanly.

### Milestone 3: manifest v1 for chart/text templates

Deliver:

* OCR integration,
* basic chart/path extraction,
* color role extraction,
* motion timing for path draw/static layers,
* manifest builder/validator,
* overlay preview.

Acceptance:

* Mars item `05` produces manifest with no product slot,
* text layers for chart labels,
* chart line path layers,
* deterministic render recommended,
* review UI can display manifest.

### Milestone 4: deterministic renderer v1

Deliver:

* text/path/shape/source-region renderer,
* GIF/WebP/MP4 export,
* color roles,
* frame timing,
* QA contact sheets.

Acceptance:

* chart pilot renders without AI,
* output duration matches source,
* no product inserted,
* QA pass report created,
* generated Asset persisted.

### Milestone 5: manifest review UI

Deliver:

* API hooks,
* review page,
* layer overlay,
* product slot panel,
* approve/reject,
* cost estimate display.

Acceptance:

* user can inspect source keyframes,
* approve chart manifest,
* render from approved manifest,
* cannot render unapproved manifest,
* product slot false displays clearly.

### Milestone 6: product slot detection and deterministic product swap

Deliver:

* object/product detector,
* product evidence model,
* product mask review,
* deterministic product compositor,
* product QA.

Acceptance:

* product template requires slot approval,
* no product slot means product references blocked,
* approved product slot swaps product within mask,
* form-factor mismatch blocked unless approved.

### Milestone 7: campaign production integration

Deliver:

* `animated_image` format support,
* animated source resolver for selected collections,
* plan items,
* analysis kickoff,
* review-required response,
* render resume.

Acceptance:

* static image requirements unchanged,
* animated requirements do not route to static generator,
* non-static selected swipes allowed only for animated requirements,
* production creates reviewable manifests.

### Milestone 8: hybrid AI regions

Deliver:

* `AnimatedRegionGenerationClient`,
* creative-service video adapter,
* masked region prompt builder,
* generated region compositing,
* cost tracking,
* QA leakage checks.

Acceptance:

* UGC masked region generated with selected model,
* locked captions/UI rendered deterministically,
* product not attached without slot,
* unsupported model returns clean error,
* no automatic fallback.

### Milestone 9: QA hardening and rollout

Deliver:

* metrics dashboards,
* regression fixtures,
* QA thresholds,
* pilot reports,
* documentation.

Acceptance:

* pilots pass,
* operator can review output quickly,
* static path tests pass,
* feature flag ready for limited production.

## 17. Open questions

1. Which exact model providers are authorized for masked animated regions in production: creative service only, Sora, Veo, or both?
2. Does the creative service expose a true masked video/region endpoint, or must the first adapter use freestyle sessions with source/mask attachments?
3. Should final landing-page delivery prefer animated WebP over GIF for file size, while keeping GIF as optional export?
4. Should `Asset.asset_kind` be extended to `"animated_image"`, or should animation semantics remain in `format` and metadata?
5. What is the maximum acceptable source duration/frame count for first production rollout?
6. Are brand fonts reliably available in design system tokens, and are font binaries stored in MOS?
7. Should manifest approval be campaign-scoped or source-scoped? Source-scoped approval is reusable, but campaign-specific copy/product edits may need separate render approvals.
8. Should low-risk deterministic manifests auto-approve in internal mode, or always require human approval before paid/customer-facing render?
9. What product form-factor mismatches are allowed? For example, can a bottle replace a jar if the target product only has a bottle?
10. Should generated region QA use a judge model, or only deterministic checks for first rollout?
11. How should final animated assets integrate with Meta publishing if the platform prefers MP4 over GIF/WebP?
12. Should selected swipe collections support separate source pools per requirement type?
13. Should manual uploaded GIFs go through the same swipe library ingestion path or a separate one-off source path?
14. What retention policy should apply to approved reusable manifests for competitor swipe sources?
15. How much human editing of masks/layers should v1 support: bounding boxes only, polygon masks, or brush masks?
16. Should chart extraction ever allow manual path editing in UI, or should v1 fail/review with source-region preservation?
17. Should template manifests be exported/imported as JSON for debugging?
18. Which QA score threshold blocks production vs warns only?

## 18. Concrete file-by-file change list

### Backend: new files

`mos/backend/app/schemas/animated_templates.py`

* API request/response schemas.
* Manifest Pydantic models.
* Error models.
* Validation helpers for model selection and render requests.

`mos/backend/app/db/repositories/animated_templates.py`

* Repository for manifest/run/artifact/event CRUD.
* Approved manifest lookup by source hash.
* Idempotency lookup.

`mos/backend/app/temporal/workflows/swipe_animated_template.py`

* `SwipeAnimatedTemplateAnalysisInput`.
* `SwipeAnimatedTemplateRenderInput`.
* Analysis workflow.
* Render workflow.
* Retry policies.

`mos/backend/app/temporal/activities/swipe_animated_template_activities.py`

* Source resolution.
* Metadata extraction.
* Frame sampling.
* Layer analysis.
* Manifest build/validation.
* Render plan.
* AI region generation.
* Deterministic render.
* QA.
* Asset persistence.

`mos/backend/app/services/animated_templates/__init__.py`

* Package init.

`mos/backend/app/services/animated_templates/source_resolver.py`

* Resolve company swipe/direct URL source.
* Download/store source bytes.

`mos/backend/app/services/animated_templates/media_probe.py`

* ffprobe/Pillow probe helpers.
* GIF/WebP delay extraction.

`mos/backend/app/services/animated_templates/frame_sampler.py`

* Extract frames.
* Keyframe/contact sheet generation.

`mos/backend/app/services/animated_templates/ocr.py`

* OCR wrapper and text merging.

`mos/backend/app/services/animated_templates/object_detection.py`

* Product/object/logo detection wrappers.
* Product-slot evidence builder.

`mos/backend/app/services/animated_templates/chart_detection.py`

* Chart/path extraction.

`mos/backend/app/services/animated_templates/ui_chrome_detection.py`

* UI screenshot chrome detection.

`mos/backend/app/services/animated_templates/motion_tracking.py`

* Layer tracking and keyframes.

`mos/backend/app/services/animated_templates/layer_classifier.py`

* Convert detections to layer policies.

`mos/backend/app/services/animated_templates/manifest_builder.py`

* Assemble manifest JSON.

`mos/backend/app/services/animated_templates/manifest_validator.py`

* Semantic validation.

`mos/backend/app/services/animated_templates/render_plan.py`

* Convert approved manifest + brand/product/copy context into renderer inputs.

`mos/backend/app/services/animated_templates/renderer/frame_renderer.py`

* Main frame rendering loop.

`mos/backend/app/services/animated_templates/renderer/text_renderer.py`

* Text layout/fitting.

`mos/backend/app/services/animated_templates/renderer/vector_renderer.py`

* SVG/path/shape rendering.

`mos/backend/app/services/animated_templates/renderer/mask_compositor.py`

* Alpha mask and generated region compositing.

`mos/backend/app/services/animated_templates/renderer/product_compositor.py`

* Product slot replacement.

`mos/backend/app/services/animated_templates/renderer/exporter.py`

* GIF/WebP/MP4 export.

`mos/backend/app/services/animated_templates/qa.py`

* QA metrics and reports.

`mos/backend/app/services/animated_templates/ai_region_client.py`

* Protocol and request/result dataclasses.

`mos/backend/app/services/animated_templates/creative_service_region_client.py`

* Adapter using `CreativeServiceClient` video sessions for masked regions.

`mos/backend/app/services/animated_templates/costs.py`

* Estimate and actual cost records.

`mos/backend/alembic/versions/00xx_animated_template_manifests.py`

* Tables/indexes/enums.

### Backend: modified files

`mos/backend/app/routers/swipes.py`

* Add animated template endpoints.
* Add workflow starters.
* Keep `/generate-image-ad` unchanged.

`mos/backend/app/schemas/swipe_image_ads.py`

* No animated overload.
* Optional shared validation import only if needed.

`mos/backend/app/schemas/asset_brief_types.py`

* Add `"animated_image"` support.
* Add alias normalization.

`mos/backend/app/schemas/asset_brief.py`

* No structural change required; document accepted format.

`mos/backend/app/schemas/creative_generation.py`

* Add animated plan schemas or `animatedItems`.

`mos/backend/app/schemas/creative_service.py`

* Add masked region schemas only if creative service API supports them.
* Otherwise no required change.

`mos/backend/app/temporal/activities/swipe_image_ad_activities.py`

* Add static-path guard for animated media.
* Extract shared download/string helpers if needed.
* Do not add animated rendering logic.

`mos/backend/app/temporal/activities/asset_activities.py`

* Add `"animated_image"` format normalization.
* Add animated source resolution.
* Add animated plan execution.
* Add `_create_generated_asset_from_bytes`.
* Preserve static non-static rejection.

`mos/backend/app/services/creative_service_client.py`

* Reuse existing video methods.
* Add masked endpoint only if real API exists.
* Keep explicit errors.

`mos/backend/app/services/video_ads_orchestrator.py`

* Prefer no change; otherwise add constrained masked-region method.
* Do not alter generic video behavior.

`mos/backend/app/services/image_render_client.py`

* No animated support in static client.
* Optional docstring/guard.

`mos/backend/app/services/media_storage.py`

* Optional helper methods for animated artifact keys; core methods already sufficient.

`mos/backend/app/services/assets.py`

* Optional helpers for product/logo assets if renderer needs direct brand logo resolution.

`mos/backend/app/db/repositories/swipes.py`

* Add helper to return media metadata and distinguish animated GIF/WebP.
* Do not alter existing list behavior unless adding serialized metadata.

`mos/backend/app/config.py`

* Add animated template flags and limits.

### Frontend: new files

`mos/frontend/src/types/animatedTemplates.ts`

* Typed manifest/run/API payloads.

`mos/frontend/src/components/animatedTemplates/AnimatedTemplateReviewPage.tsx`

* Main review route.

`mos/frontend/src/components/animatedTemplates/AnimatedTemplateManifestPreview.tsx`

* Preview layout.

`mos/frontend/src/components/animatedTemplates/AnimatedTemplateLayerOverlay.tsx`

* Canvas overlay boxes/masks.

`mos/frontend/src/components/animatedTemplates/AnimatedTemplateLayerList.tsx`

* Layer list and policy display.

`mos/frontend/src/components/animatedTemplates/AnimatedTemplateProductSlotPanel.tsx`

* Product-slot evidence/approval.

`mos/frontend/src/components/animatedTemplates/AnimatedTemplateTextRolesPanel.tsx`

* Text role review.

`mos/frontend/src/components/animatedTemplates/AnimatedTemplateColorRolesPanel.tsx`

* Color role review.

`mos/frontend/src/components/animatedTemplates/AnimatedTemplateWarningsPanel.tsx`

* Risk summary.

`mos/frontend/src/components/animatedTemplates/AnimatedTemplateContactSheet.tsx`

* Source/output sheet display.

`mos/frontend/src/components/animatedTemplates/AnimatedTemplateDiffViewer.tsx`

* QA diff/contact sheet.

`mos/frontend/src/pages/animatedTemplates/AnimatedTemplateReviewRoute.tsx`

* Route wrapper if routing pattern prefers pages.

### Frontend: modified files

`mos/frontend/src/api/swipes.ts`

* Add animated template hooks and API methods.

`mos/frontend/src/api/campaigns.ts`

* Support production response with animated review-required payload if backend returns it.
* Possibly add campaign animated review query.

`mos/frontend/src/pages/campaigns/tabs/CampaignCreativeTab.tsx`

* Show animated brief type.
* Handle review-required production state.
* Link to manifest review queue.
* Keep existing static workflow behavior.

`mos/frontend/src/pages/campaigns/CampaignDetailPage.tsx`

* Add routes/tabs/links for animated review if needed.

`mos/frontend/src/components/campaigns/SwipeCollectionSelector.tsx`

* Add animated image filter.
* Show GIF/animated badges.
* Add “Analyze as animated template” action.

`mos/frontend/src/lib/campaignProductionBatch.ts`

* Read `animatedTemplateRunId`, `animatedTemplateManifestId`, and QA status from asset metadata.
* Group animated outputs correctly.

`mos/frontend/src/lib/assetBriefTypes.ts`

* Add `animated_image`.

`mos/frontend/src/types/swipes.ts`

* Add `animated_image` asset type and media metadata fields if available.

`mos/frontend/src/types/assetReview.ts`

* Add `AssetSource` or metadata fields if needed for animated template QA.
* Add `assetType` support for animated image.

`mos/frontend/src/lib/assetReviewNormalizers.ts`

* Normalize generated animated assets and source GIF/video swipes.
* Include QA metadata if present.

`mos/frontend/src/components/review/AssetReviewGrid.tsx`

* Add animated badge/play affordance if generic enough.
* Otherwise keep grid and enhance detail panel only.

`mos/frontend/src/components/library/SwipeMedia.tsx`

* Display animated GIF/WebP previews.
* Preserve video hover preview.
* Add play/pause controls for animated images if needed.

### Test files

Backend:

* `mos/backend/tests/test_animated_templates_api.py`
* `mos/backend/tests/test_animated_template_manifest_schema.py`
* `mos/backend/tests/test_animated_template_product_slot_policy.py`
* `mos/backend/tests/test_animated_template_renderer_chart.py`
* `mos/backend/tests/test_animated_template_qa.py`
* `mos/backend/tests/test_asset_activities_animated_image.py`
* `mos/backend/tests/test_static_swipe_rejects_animated_media.py`

Frontend:

* `mos/frontend/src/components/animatedTemplates/__tests__/AnimatedTemplateManifestPreview.test.tsx`
* `mos/frontend/src/components/animatedTemplates/__tests__/AnimatedTemplateProductSlotPanel.test.tsx`
* `mos/frontend/src/api/__tests__/swipesAnimatedTemplates.test.ts`
* `mos/frontend/src/lib/__tests__/assetBriefTypes.test.ts`

### First engineering slice

The first slice should be narrow and deterministic:

1. Add DB tables/repository/schemas.
2. Add analyze endpoint/workflow for GIF sources.
3. Extract frames and build contact sheet.
4. Build a hand-authored or simple auto manifest for chart/text templates.
5. Add manifest review UI.
6. Render chart/text template deterministically without AI.
7. Persist GIF/WebP output and QA contact sheet.
8. Verify Mars item `05` produces no product insertion.

This slice proves the architecture’s central claim: MOS can recreate an animated source template with locked layers and no model drift. Only after that should product swaps and hybrid AI regions be added.
