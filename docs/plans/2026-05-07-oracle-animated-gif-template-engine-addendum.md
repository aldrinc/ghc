# Addendum: Deep Implementation Details

This addendum extends the previous implementation plan with deeper module-by-module mechanics. It preserves the deterministic-template architecture, the product-slot evidence gate, and the strict separation between locked layers and model-owned masked regions described in the Oracle request and local repo context.

## A. Exact backend activity boundaries, input/output contracts, and idempotency keys

The animated-template path should not reproduce the current static path’s “one large activity owns everything” shape. `generate_swipe_image_ad_activity` works as a single static pipeline because it produces one prompt and delegates final pixels to a static renderer. Animated templates need restartable analysis, review, paid-region generation, deterministic rendering, export, and QA. Each of those stages has different retry, idempotency, and artifact durability needs.

### A.1 Activity family naming convention

Use stable explicit activity names rather than relying on function names alone. Recommended names:

```python
@activity.defn(name="animated_templates.resolve_source")
def resolve_animated_template_source_activity(...): ...

@activity.defn(name="animated_templates.probe_source")
def probe_animated_template_source_activity(...): ...

@activity.defn(name="animated_templates.extract_frames")
def extract_animated_template_frames_activity(...): ...

@activity.defn(name="animated_templates.analyze_layers")
def analyze_animated_template_layers_activity(...): ...

@activity.defn(name="animated_templates.build_manifest")
def build_animated_template_manifest_activity(...): ...

@activity.defn(name="animated_templates.validate_manifest")
def validate_animated_template_manifest_activity(...): ...

@activity.defn(name="animated_templates.persist_manifest")
def persist_animated_template_manifest_activity(...): ...

@activity.defn(name="animated_templates.prepare_render_plan")
def prepare_animated_template_render_plan_activity(...): ...

@activity.defn(name="animated_templates.generate_ai_regions")
def generate_animated_template_ai_regions_activity(...): ...

@activity.defn(name="animated_templates.render_frames")
def render_animated_template_frames_activity(...): ...

@activity.defn(name="animated_templates.export_outputs")
def export_animated_template_outputs_activity(...): ...

@activity.defn(name="animated_templates.run_qa")
def run_animated_template_qa_activity(...): ...

@activity.defn(name="animated_templates.persist_outputs")
def persist_animated_template_outputs_activity(...): ...
```

Use a separate namespace from `swipes.generate_swipe_image_ad` so Temporal histories are clear and the static route cannot accidentally invoke the animated implementation.

### A.2 `resolve_animated_template_source_activity`

Purpose: resolve the source media into immutable bytes stored in MOS media storage. It should not inspect layers yet.

Input:

```json
{
  "org_id": "uuid",
  "client_id": "uuid",
  "product_id": "uuid|null",
  "campaign_id": "uuid|null",
  "company_swipe_id": "uuid|null",
  "company_swipe_media_id": "uuid|null",
  "source_url": "https://...|null",
  "source_label": "optional",
  "workflow_run_id": "uuid|null",
  "analysis_idempotency_key": "sha"
}
```

Output:

```json
{
  "source_ref": {
    "source_kind": "company_swipe|direct_url",
    "company_swipe_id": "uuid|null",
    "company_swipe_media_id": "uuid|null",
    "source_url": "resolved download url",
    "source_label": "item-05.gif",
    "mime_type": "image/gif",
    "sha256": "hex",
    "size_bytes": 123456,
    "storage_bucket": "bucket",
    "storage_key": "animated_templates/.../source/original.gif",
    "etag": "optional",
    "downloaded_at": "iso"
  },
  "idempotency": {
    "activity_key": "sha",
    "reused_existing_source": true
  }
}
```

Idempotency key:

```text
animated_template_source_v1|
org_id|
company_swipe_id|
company_swipe_media_id|
source_url|
source_label|
source_download_url_if_resolved
```

After download, create a stronger content key:

```text
animated_template_source_content_v1|
org_id|
source_sha256|
mime_type|
size_bytes
```

Rules:

* Exactly one of `company_swipe_id` or `source_url` must be provided.
* If `company_swipe_media_id` is present, use that exact media item. Do not prefer another media silently.
* If `company_swipe_id` has multiple media items and no media ID, select the first animated-capable media by deterministic priority: animated GIF, animated WebP, video, then static image only if static analysis is explicitly allowed.
* If multiple equally eligible media items exist, return `AMBIGUOUS_SOURCE_MEDIA` and include candidate IDs. Do not guess.
* If the MIME type is `image/gif` but bytes are not a valid GIF, return `SOURCE_DECODE_FAILED`.
* If the media is a static image but the request requires animated source, return `SOURCE_NOT_ANIMATED`.
* Store the source before returning. Later activities should never re-download from the original URL unless the source storage key is missing and the retry is a same-run retry.

### A.3 `probe_animated_template_source_activity`

Purpose: derive exact media metadata and normalize basic media facts. It owns ffprobe/Pillow inspection, not layer analysis.

Input:

```json
{
  "org_id": "uuid",
  "source_ref": { "...": "..." },
  "analyzer_version": "animated-template-analyzer-v1",
  "workflow_run_id": "uuid|null"
}
```

Output:

```json
{
  "probe": {
    "source_sha256": "hex",
    "mime_type": "image/gif",
    "width": 996,
    "height": 996,
    "duration_ms": 2860,
    "frame_count": 16,
    "frame_delays_ms": [180, 180],
    "loop_count": 0,
    "has_alpha": false,
    "color_space": "srgb",
    "codec": "gif",
    "pixel_format": "pal8",
    "probe_method": "pillow_gif+ffprobe",
    "warnings": []
  },
  "artifact_refs": {
    "probe_json_key": "animated_templates/.../probe.json"
  }
}
```

Idempotency key:

```text
animated_template_probe_v1|
org_id|
source_sha256|
mime_type|
analyzer_version|
probe_tool_versions_hash
```

Implementation details:

* For GIF, use Pillow as the authority for frame count and per-frame duration because GIF frame timing can be represented poorly by ffprobe.
* For videos, use ffprobe as authority but record the raw ffprobe JSON. If frame count is absent, compute approximate frame count from duration and frame rate and mark `frame_count_estimated=true`.
* If the source has variable frame delays, keep them. Do not resample at probe stage.
* Store the full probe output as JSON artifact. The manifest should keep essential fields, but raw probe JSON is useful for debugging.

### A.4 `extract_animated_template_frames_activity`

Purpose: extract source frames and keyframes into storage and produce a `frame_manifest`.

Input:

```json
{
  "org_id": "uuid",
  "source_ref": {},
  "probe": {},
  "sampling_policy": {
    "mode": "all_under_limit",
    "max_analysis_frames": 32,
    "max_render_frames": 180
  },
  "workflow_run_id": "uuid|null"
}
```

Output:

```json
{
  "frame_manifest": {
    "source_sha256": "hex",
    "frame_count": 16,
    "analysis_frame_indexes": [0, 1, 2, 4, 8, 12, 15],
    "render_frame_indexes": [0, 1, 2, "..."],
    "frames": [
      {
        "frame_index": 0,
        "time_ms": 0,
        "delay_ms": 180,
        "storage_key": "frames/frame_0000.png",
        "sha256": "hex",
        "width": 996,
        "height": 996,
        "is_keyframe": true,
        "sampling_reason": ["first_frame", "uniform_sample"]
      }
    ],
    "contact_sheet": {
      "storage_key": "contact_sheets/source_analysis.png",
      "content_type": "image/png",
      "frame_indexes": [0, 2, 4, 8, 12, 15]
    }
  }
}
```

Idempotency key:

```text
animated_template_frames_v1|
org_id|
source_sha256|
probe_sha256|
sampling_policy_sha256|
extractor_version|
ffmpeg_version|
pillow_version
```

Critical extraction rules:

* GIF extraction must respect disposal methods. Do not simply decode each raw frame if the GIF uses partial updates. Use Pillow’s composited frames or ffmpeg with correct disposal handling. Store fully composited canvas-size PNGs.
* Store alpha if source has transparency. If transparent background exists, record `background_mode="transparent"` and do not flatten without an explicit background color.
* If all render frames are extracted, set `render_mode_source_frames="full"`. If only a subset is extracted due to limits, mark `render_mode_source_frames="sampled"` and block render unless the renderer supports resampling from video source.
* Contact sheet generation should include frame index and timestamp labels outside the source image area, not over the image pixels, so reviewers can inspect source content without label occlusion.

### A.5 `analyze_animated_template_layers_activity`

Purpose: run OCR, object/product detection, chart/path detection, UI chrome detection, motion tracking, color sampling, and layer classification. It should output analysis facts, not the final manifest.

Input:

```json
{
  "org_id": "uuid",
  "client_id": "uuid",
  "product_id": "uuid|null",
  "source_ref": {},
  "probe": {},
  "frame_manifest": {},
  "analyzer_version": "animated-template-analyzer-v1",
  "analysis_options": {
    "enable_ocr": true,
    "enable_product_detection": true,
    "enable_chart_detection": true,
    "enable_ui_chrome_detection": true,
    "enable_motion_tracking": true
  }
}
```

Output:

```json
{
  "analysis": {
    "template_classification": {},
    "ocr": {},
    "objects": {},
    "product_slot_candidates": [],
    "negative_product_slot_evidence": [],
    "charts": {},
    "ui_chrome": {},
    "motion_tracks": {},
    "color_samples": {},
    "layer_candidates": [],
    "review_reasons": [],
    "warnings": []
  },
  "artifact_refs": {
    "analysis_json_key": "analysis/layers.json",
    "debug_overlay_key": "analysis/debug_overlay.png"
  }
}
```

Idempotency key:

```text
animated_template_layer_analysis_v1|
org_id|
source_sha256|
frame_manifest_sha256|
analyzer_version|
enabled_detectors_sha256|
model_or_detector_versions_sha256
```

Important: If an OCR or detector uses a paid model, record its provider/model in `analysis.cost_components`; but the first implementation should prefer local deterministic analysis to avoid making manifest preview dependent on paid generation. If a paid model is used for analysis, it is still not allowed to render final locked pixels.

### A.6 `build_animated_template_manifest_activity`

Purpose: convert analysis facts into a strict manifest. It does not persist approval state.

Input:

```json
{
  "org_id": "uuid",
  "client_id": "uuid",
  "product_id": "uuid|null",
  "campaign_id": "uuid|null",
  "source_ref": {},
  "probe": {},
  "frame_manifest": {},
  "analysis": {},
  "manifest_schema_version": 1,
  "analyzer_version": "animated-template-analyzer-v1"
}
```

Output:

```json
{
  "manifest": {},
  "manifest_sha256": "hex",
  "manifest_summary": {
    "primary_family": "chart",
    "layer_count": 17,
    "locked_layer_count": 17,
    "generative_region_count": 0,
    "has_competitor_product_slot": false,
    "ai_required": false,
    "review_required": true,
    "review_reasons": ["approval_required_before_render"]
  }
}
```

Idempotency key:

```text
animated_template_manifest_build_v1|
org_id|
source_sha256|
probe_sha256|
frame_manifest_sha256|
analysis_sha256|
manifest_schema_version|
analyzer_version
```

Build rules:

* Stable layer IDs must be deterministic from type, role, geometry, and source evidence, not random UUIDs. Example:

```text
layer_text_axis_label_y_{short_hash(source_text|box|rotation)}
layer_chart_series_primary_{short_hash(path_signature|color)}
```

* Use sorted keys and canonical JSON when computing manifest SHA.
* Do not include presigned URLs in the manifest hash because they expire and would break idempotency.
* Do include storage keys, source SHA, detector version, geometry, evidence, and policies.

### A.7 `validate_animated_template_manifest_activity`

Purpose: run structural and semantic validation. This activity should be pure: same manifest input, same validation output.

Input:

```json
{
  "manifest": {},
  "validation_profile": "draft|approval|render",
  "render_request": null
}
```

Output:

```json
{
  "validation": {
    "status": "valid|valid_with_review|invalid",
    "blocking_errors": [],
    "review_reasons": [],
    "warnings": [],
    "derived": {
      "ai_required": false,
      "product_replacement_allowed": false,
      "renderable_without_ai": true
    }
  }
}
```

Idempotency key:

```text
animated_template_manifest_validation_v1|
manifest_sha256|
validation_profile|
render_request_sha256_or_empty|
validator_version
```

This activity should not mutate the manifest row. `persist_manifest` applies the result.

### A.8 `persist_animated_template_manifest_activity`

Purpose: upsert the manifest row and associated artifacts/events.

Input:

```json
{
  "org_id": "uuid",
  "client_id": "uuid|null",
  "product_id": "uuid|null",
  "campaign_id": "uuid|null",
  "source_ref": {},
  "probe": {},
  "manifest": {},
  "manifest_sha256": "hex",
  "validation": {},
  "preview_artifacts": {},
  "workflow_run_id": "uuid|null",
  "analysis_idempotency_key": "hex"
}
```

Output:

```json
{
  "manifest_id": "uuid",
  "status": "needs_review|draft|approved_reused",
  "manifest_version": 1,
  "manifest_sha256": "hex",
  "review_required": true,
  "reused_existing_manifest": false
}
```

Idempotency key:

```text
animated_template_manifest_persist_v1|
org_id|
source_sha256|
manifest_sha256|
analysis_idempotency_key
```

Repository behavior:

* Check `(org_id, idempotency_key)` first.
* If row exists, return it.
* If no row exists but an approved manifest exists with same `(org_id, source_sha256, analyzer_version, manifest_schema_version, manifest_sha256)`, return it as reused.
* If manifest differs from existing draft for same source, create a new row with `manifest_version = max + 1` and `supersedes_manifest_id` if appropriate.
* Log event `analysis.manifest_persisted`.

### A.9 `prepare_animated_template_render_plan_activity`

Purpose: combine approved manifest, brand/design system tokens, approved copy, optional product references, and output settings into a render plan. It is the enforcement point for product slot evidence and locked layer ownership.

Input:

```json
{
  "org_id": "uuid",
  "client_id": "uuid",
  "product_id": "uuid",
  "campaign_id": "uuid|null",
  "manifest_id": "uuid",
  "approved_manifest_version": 1,
  "render_request": {
    "output_formats": ["gif", "webp"],
    "render_mode": "deterministic",
    "final_copy": {},
    "model_selection": null
  },
  "asset_brief_id": "brief-id",
  "requirement_index": 0,
  "workflow_run_id": "uuid|null"
}
```

Output:

```json
{
  "run_id": "uuid",
  "render_plan": {
    "render_plan_version": 1,
    "renderer_version": "animated-template-renderer-v1",
    "manifest_id": "uuid",
    "manifest_sha256": "hex",
    "canvas": {},
    "timeline": {},
    "layers": [],
    "ai_regions": [],
    "product_replacements": [],
    "output_formats": ["gif", "webp"],
    "expected_frame_count": 16
  },
  "cost_estimate": {},
  "requires_ai": false
}
```

Idempotency key:

```text
animated_template_render_plan_v1|
org_id|
client_id|
product_id|
campaign_id|
manifest_id|
manifest_sha256|
approved_manifest_version|
asset_brief_id|
requirement_index|
render_request_sha256|
brand_context_sha256|
copy_context_sha256|
product_reference_context_sha256|
renderer_version
```

Hard validations:

* Manifest status must be `approved`.
* `approved_manifest_version` must match the row.
* If render request contains product replacement but manifest product slot is false, return `PRODUCT_SLOT_REQUIRED`.
* If manifest product slot is true but not human-approved and policy requires approval, return `PRODUCT_SLOT_REVIEW_REQUIRED`.
* If any layer has `policy="generative_region"` and `renderMode="deterministic"`, return `RENDER_MODE_INCOMPATIBLE`.
* If `modelSelection` is provided but `ai_regions=[]`, return `UNUSED_MODEL_SELECTION` unless the request explicitly says `allowUnusedModelSelection=true`. The safer default is an error because the user may assume model output influenced the final creative.
* If any locked layer has render owner `ai_region_model`, return `LOCKED_LAYER_AI_OWNER_FORBIDDEN`.

### A.10 `generate_animated_template_ai_regions_activity`

Purpose: generate only approved masked regions. It is skipped entirely when `render_plan.ai_regions` is empty.

Input:

```json
{
  "org_id": "uuid",
  "run_id": "uuid",
  "render_plan": {},
  "model_selection": {
    "provider": "creative_service",
    "model_id": "sora-2"
  },
  "workflow_run_id": "uuid|null"
}
```

Output:

```json
{
  "generated_regions": [
    {
      "region_id": "ugc_background",
      "provider": "creative_service",
      "model_id": "sora-2",
      "remote_run_id": "optional",
      "output_storage_key": "regions/ugc_background.mp4",
      "frame_storage_keys": [],
      "duration_ms": 2860,
      "cost_actual": {},
      "prompt_sha256": "hex"
    }
  ]
}
```

Idempotency key per region:

```text
animated_template_ai_region_v1|
org_id|
run_id|
manifest_sha256|
region_id|
region_mask_sha256|
source_keyframe_sha256s|
region_prompt_sha256|
provider|
model_id|
duration_ms|
canvas_size|
negative_mask_sha256s|
product_reference_sha256s_or_no_product_references
```

Rules:

* Never call this activity if no AI regions exist.
* Never attach product references unless the render plan contains a specific approved product slot that requires them.
* Check actual provider/model returned. If mismatch, return `MODEL_MISMATCH`.
* OCR and object-detect the generated region before returning. If generated text appears and `modelMayRenderText=false`, return `MODEL_RENDERED_TEXT_FORBIDDEN`.
* If product-like object appears and `modelMayInsertProduct=false`, return `MODEL_INSERTED_PRODUCT_FORBIDDEN`.
* Do not retry with a different model. Do not retry with a modified prompt automatically. If retrying same provider/model is allowed, only do it under a controlled same-idempotency retry for transport failure before a remote generation was accepted.

### A.11 `render_animated_template_frames_activity`

Purpose: render deterministic frames into local temp storage and persist them as artifacts if configured.

Input:

```json
{
  "org_id": "uuid",
  "run_id": "uuid",
  "render_plan": {},
  "generated_regions": [],
  "workflow_run_id": "uuid|null"
}
```

Output:

```json
{
  "rendered_frames": {
    "frame_count": 16,
    "frame_delays_ms": [180, 180],
    "frames_dir_storage_prefix": "runs/.../frames/",
    "frame_refs": [
      {
        "frame_index": 0,
        "time_ms": 0,
        "storage_key": "runs/.../frames/frame_0000.png",
        "sha256": "hex"
      }
    ],
    "rendered_frames_manifest_key": "runs/.../rendered_frames.json"
  },
  "render_stats": {
    "renderer_version": "animated-template-renderer-v1",
    "duration_ms": 4200,
    "layer_render_counts": {
      "text": 8,
      "path": 4
    }
  }
}
```

Idempotency key:

```text
animated_template_render_frames_v1|
org_id|
run_id|
render_plan_sha256|
generated_regions_sha256|
renderer_version|
font_resolution_sha256|
source_frame_manifest_sha256
```

Rules:

* Every output frame must be deterministic for the same inputs. Avoid timestamps or random seeds in rendered pixels.
* If renderer uses a browser, set device scale factor, viewport, CSS, and font set deterministically.
* If a font is missing, fail with `FONT_UNAVAILABLE` unless manifest has an approved fallback. Do not substitute silently.
* If a layer cannot be rendered, fail and include layer ID.

### A.12 `export_animated_template_outputs_activity`

Purpose: encode rendered frames into GIF/WebP/MP4.

Input:

```json
{
  "org_id": "uuid",
  "run_id": "uuid",
  "rendered_frames": {},
  "output_formats": ["gif", "webp", "mp4"],
  "export_settings": {}
}
```

Output:

```json
{
  "outputs": [
    {
      "format": "gif",
      "content_type": "image/gif",
      "storage_key": "runs/.../outputs/final.gif",
      "sha256": "hex",
      "size_bytes": 1234567,
      "width": 996,
      "height": 996,
      "duration_ms": 2860,
      "frame_count": 16
    }
  ],
  "export_stats": {
    "gif_palette_mode": "palettegen_paletteuse",
    "webp_quality": 80,
    "mp4_crf": 18,
    "duration_ms": 1800
  }
}
```

Idempotency key per format:

```text
animated_template_export_v1|
org_id|
run_id|
rendered_frames_manifest_sha256|
format|
export_settings_sha256|
ffmpeg_version|
gifsicle_version_or_none
```

Rules:

* If requested format unsupported, return `OUTPUT_FORMAT_UNSUPPORTED`.
* If GIF size exceeds configured max, return `OUTPUT_TOO_LARGE` with size details. Do not silently drop frames or reduce colors unless an explicit export policy permits it.
* For MP4, record that variable GIF delays were resampled if applicable.

### A.13 `run_animated_template_qa_activity`

Purpose: generate QA artifacts and pass/fail report.

Input:

```json
{
  "org_id": "uuid",
  "run_id": "uuid",
  "manifest": {},
  "render_plan": {},
  "source_frame_manifest": {},
  "rendered_frames": {},
  "outputs": []
}
```

Output:

```json
{
  "qa_report": {
    "overall_status": "pass|warning|fail",
    "weighted_score_100": 94.2,
    "blocking_issues": [],
    "warnings": [],
    "metrics": {}
  },
  "qa_artifacts": {
    "source_output_contact_sheet_key": "qa/contact_sheet.png",
    "diff_heatmap_key": "qa/diff.png",
    "ocr_report_key": "qa/ocr.json",
    "product_policy_report_key": "qa/product_policy.json"
  }
}
```

Idempotency key:

```text
animated_template_qa_v1|
org_id|
run_id|
manifest_sha256|
render_plan_sha256|
source_frame_manifest_sha256|
rendered_frames_manifest_sha256|
outputs_sha256|
qa_version
```

Rules:

* QA fail does not delete outputs. It marks run `qa_status=fail` and generated assets can be withheld from default review or shown with blockers.
* Product policy failure is always blocking.
* Locked-layer AI rendering detection is always blocking.
* Extra chart points are blocking for chart templates.
* Unexpected text in model-generated regions is blocking when `modelMayRenderText=false`.

### A.14 `persist_animated_template_outputs_activity`

Purpose: create final `Asset` rows, `AnimatedTemplateRun` output links, and optional `CreativeServiceOutput` links.

Input:

```json
{
  "org_id": "uuid",
  "client_id": "uuid",
  "product_id": "uuid",
  "campaign_id": "uuid|null",
  "asset_brief_id": "brief-id",
  "requirement_index": 0,
  "brief_artifact_id": "uuid",
  "funnel_id": "uuid|null",
  "run_id": "uuid",
  "manifest_id": "uuid",
  "render_plan": {},
  "outputs": [],
  "qa_report": {},
  "qa_artifacts": {},
  "creative_generation_batch_id": "optional",
  "creative_generation_plan_artifact_id": "optional",
  "creative_generation_plan_item_id": "optional"
}
```

Output:

```json
{
  "asset_ids": ["uuid"],
  "run_id": "uuid",
  "qa_status": "pass",
  "output_storage_keys": {
    "gif": "...",
    "webp": "..."
  }
}
```

Idempotency key:

```text
animated_template_persist_outputs_v1|
org_id|
run_id|
outputs_sha256|
qa_report_sha256|
asset_brief_id|
requirement_index
```

Rules:

* If an asset row already exists for the same run/output hash/format, return it.
* Do not create duplicate assets on Temporal replay.
* `source_type=ai` remains acceptable because this is generated creative, but metadata must make deterministic ownership clear.
* `format="animated_image"` for GIF/WebP. MP4 can use `format="animated_image"` or `format="video_preview"` depending downstream conventions; prefer preserving the requirement format and marking `outputFormat="mp4"` in metadata.

## B. SQLAlchemy and Alembic migration details

### B.1 Prefer text statuses over DB enums in first migration

The existing codebase uses enums for some core asset fields, but for the animated template subsystem, initial status fields should be `String` with check constraints instead of database enum types. Reasons:

* status lists will evolve during rollout;
* Alembic enum alteration is noisier in PostgreSQL;
* frontend/review states may need new draft statuses quickly;
* bad status values can still be prevented with check constraints.

Recommended check constraints:

```sql
status IN ('draft', 'needs_review', 'approved', 'rejected', 'superseded', 'failed')
analysis_status IN ('queued', 'processing', 'succeeded', 'failed')
product_slot_status IN ('not_detected', 'detected', 'uncertain', 'review_required', 'disabled_by_policy')
```

For `animated_template_runs.status`:

```sql
status IN ('queued', 'processing', 'waiting_for_ai', 'rendering', 'qa_running', 'succeeded', 'failed', 'cancelled')
qa_status IN ('not_run', 'pass', 'warning', 'fail')
```

### B.2 Alembic revision skeleton

```python
"""add animated template manifests

Revision ID: 00xx_animated_template_manifests
Revises: 00xx_previous
Create Date: 2026-05-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "00xx_animated_template_manifests"
down_revision = "00xx_previous"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "animated_template_manifests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("company_swipe_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("company_swipe_media_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_label", sa.Text(), nullable=True),
        sa.Column("source_mime_type", sa.String(length=128), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("source_width", sa.Integer(), nullable=False),
        sa.Column("source_height", sa.Integer(), nullable=False),
        sa.Column("source_duration_ms", sa.Integer(), nullable=True),
        sa.Column("source_frame_count", sa.Integer(), nullable=True),
        sa.Column("source_frame_rate", sa.Float(), nullable=True),
        sa.Column("analyzer_version", sa.String(length=96), nullable=False),
        sa.Column("manifest_schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("manifest_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("manifest_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("analysis_status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("analysis_error", sa.Text(), nullable=True),
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("review_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("risk_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("product_slot_status", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("product_slot_confidence", sa.Float(), nullable=True),
        sa.Column("has_competitor_product_slot", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("render_mode_recommended", sa.String(length=32), nullable=False, server_default="deterministic"),
        sa.Column("ai_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source_storage_key", sa.Text(), nullable=True),
        sa.Column("source_bucket", sa.Text(), nullable=True),
        sa.Column("preview_contact_sheet_key", sa.Text(), nullable=True),
        sa.Column("preview_contact_sheet_bucket", sa.Text(), nullable=True),
        sa.Column("overlay_preview_key", sa.Text(), nullable=True),
        sa.Column("overlay_preview_bucket", sa.Text(), nullable=True),
        sa.Column("frame_manifest_key", sa.Text(), nullable=True),
        sa.Column("mask_manifest_key", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Text(), nullable=True),
        sa.Column("approved_by_user_id", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by_user_id", sa.Text(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_manifest_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=96), nullable=False),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["supersedes_manifest_id"], ["animated_template_manifests.id"], ondelete="SET NULL"),
        sa.CheckConstraint("source_size_bytes > 0", name="ck_atm_source_size_positive"),
        sa.CheckConstraint("source_width > 0", name="ck_atm_source_width_positive"),
        sa.CheckConstraint("source_height > 0", name="ck_atm_source_height_positive"),
        sa.CheckConstraint("manifest_schema_version >= 1", name="ck_atm_schema_version_positive"),
        sa.CheckConstraint("manifest_version >= 1", name="ck_atm_manifest_version_positive"),
        sa.CheckConstraint("status in ('draft','needs_review','approved','rejected','superseded','failed')", name="ck_atm_status"),
        sa.CheckConstraint("analysis_status in ('queued','processing','succeeded','failed')", name="ck_atm_analysis_status"),
        sa.CheckConstraint("product_slot_status in ('unknown','not_detected','detected','uncertain','review_required','disabled_by_policy')", name="ck_atm_product_slot_status"),
    )

    op.create_index("ix_atm_org_campaign_status_created", "animated_template_manifests", ["org_id", "campaign_id", "status", sa.text("created_at DESC")])
    op.create_index("ix_atm_org_source_reuse", "animated_template_manifests", ["org_id", "source_sha256", "analyzer_version", "manifest_schema_version", "status"])
    op.create_index("ix_atm_org_product_slot", "animated_template_manifests", ["org_id", "has_competitor_product_slot", "product_slot_status"])
    op.create_unique_constraint("uq_atm_org_idempotency", "animated_template_manifests", ["org_id", "idempotency_key"])
```

Alembic does not accept `sa.text("created_at DESC")` in `op.create_index` in all versions. If the project’s Alembic version cannot handle descending index expressions directly, use raw SQL:

```python
op.execute(
    """
    CREATE INDEX ix_atm_org_campaign_status_created
    ON animated_template_manifests (org_id, campaign_id, status, created_at DESC)
    """
)
```

Create `animated_template_manifest_events`:

```python
op.create_table(
    "animated_template_manifest_events",
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("manifest_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("event_type", sa.String(length=96), nullable=False),
    sa.Column("actor_user_id", sa.Text(), nullable=True),
    sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.ForeignKeyConstraint(["manifest_id"], ["animated_template_manifests.id"], ondelete="CASCADE"),
)
op.create_index("ix_atme_org_manifest_created", "animated_template_manifest_events", ["org_id", "manifest_id", "created_at"])
op.create_index("ix_atme_org_event_type", "animated_template_manifest_events", ["org_id", "event_type"])
```

Create `animated_template_runs`:

```python
op.create_table(
    "animated_template_runs",
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("manifest_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
    sa.Column("manifest_version", sa.Integer(), nullable=False),
    sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("asset_brief_id", sa.Text(), nullable=False),
    sa.Column("brief_artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("requirement_index", sa.Integer(), nullable=False),
    sa.Column("creative_generation_batch_id", sa.String(length=96), nullable=True),
    sa.Column("creative_generation_plan_artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("creative_generation_plan_item_id", sa.String(length=96), nullable=True),
    sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
    sa.Column("render_mode", sa.String(length=32), nullable=False),
    sa.Column("ai_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    sa.Column("requested_model_provider", sa.String(length=64), nullable=True),
    sa.Column("requested_model_id", sa.String(length=128), nullable=True),
    sa.Column("authorized_model_provider", sa.String(length=64), nullable=True),
    sa.Column("authorized_model_id", sa.String(length=128), nullable=True),
    sa.Column("render_request_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column("render_plan_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("cost_estimate_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("cost_actual_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("output_asset_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
    sa.Column("output_storage_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("qa_report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("qa_score", sa.Float(), nullable=True),
    sa.Column("qa_status", sa.String(length=32), nullable=True),
    sa.Column("idempotency_key", sa.String(length=96), nullable=False),
    sa.Column("error_detail", sa.Text(), nullable=True),
    sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(["manifest_id"], ["animated_template_manifests.id"], ondelete="RESTRICT"),
    sa.CheckConstraint("requirement_index >= 0", name="ck_atr_requirement_index_nonnegative"),
    sa.CheckConstraint("manifest_version >= 1", name="ck_atr_manifest_version_positive"),
    sa.CheckConstraint("status in ('queued','processing','waiting_for_ai','rendering','qa_running','succeeded','failed','cancelled')", name="ck_atr_status"),
    sa.CheckConstraint("qa_status is null or qa_status in ('not_run','pass','warning','fail')", name="ck_atr_qa_status"),
)
op.create_unique_constraint("uq_atr_org_idempotency", "animated_template_runs", ["org_id", "idempotency_key"])
op.create_index("ix_atr_org_campaign_status", "animated_template_runs", ["org_id", "campaign_id", "status"])
op.create_index("ix_atr_org_manifest", "animated_template_runs", ["org_id", "manifest_id"])
op.create_index("ix_atr_org_plan_item", "animated_template_runs", ["org_id", "creative_generation_batch_id", "creative_generation_plan_item_id"])
```

Create `animated_template_artifacts`:

```python
op.create_table(
    "animated_template_artifacts",
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("manifest_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("artifact_kind", sa.String(length=96), nullable=False),
    sa.Column("storage_bucket", sa.Text(), nullable=False),
    sa.Column("storage_key", sa.Text(), nullable=False),
    sa.Column("content_type", sa.String(length=128), nullable=False),
    sa.Column("size_bytes", sa.BigInteger(), nullable=True),
    sa.Column("sha256", sa.String(length=64), nullable=True),
    sa.Column("width", sa.Integer(), nullable=True),
    sa.Column("height", sa.Integer(), nullable=True),
    sa.Column("frame_index", sa.Integer(), nullable=True),
    sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.ForeignKeyConstraint(["manifest_id"], ["animated_template_manifests.id"], ondelete="CASCADE"),
    sa.ForeignKeyConstraint(["run_id"], ["animated_template_runs.id"], ondelete="CASCADE"),
    sa.CheckConstraint("(manifest_id is not null) or (run_id is not null)", name="ck_ata_manifest_or_run"),
)
op.create_index("ix_ata_org_manifest_kind", "animated_template_artifacts", ["org_id", "manifest_id", "artifact_kind"])
op.create_index("ix_ata_org_run_kind", "animated_template_artifacts", ["org_id", "run_id", "artifact_kind"])
op.create_index("ix_ata_org_sha", "animated_template_artifacts", ["org_id", "sha256"])
```

### B.3 Downgrade sequence

Drop children first:

```python
def downgrade() -> None:
    op.drop_index("ix_ata_org_sha", table_name="animated_template_artifacts")
    op.drop_index("ix_ata_org_run_kind", table_name="animated_template_artifacts")
    op.drop_index("ix_ata_org_manifest_kind", table_name="animated_template_artifacts")
    op.drop_table("animated_template_artifacts")

    op.drop_index("ix_atr_org_plan_item", table_name="animated_template_runs")
    op.drop_index("ix_atr_org_manifest", table_name="animated_template_runs")
    op.drop_index("ix_atr_org_campaign_status", table_name="animated_template_runs")
    op.drop_constraint("uq_atr_org_idempotency", "animated_template_runs", type_="unique")
    op.drop_table("animated_template_runs")

    op.drop_index("ix_atme_org_event_type", table_name="animated_template_manifest_events")
    op.drop_index("ix_atme_org_manifest_created", table_name="animated_template_manifest_events")
    op.drop_table("animated_template_manifest_events")

    op.drop_constraint("uq_atm_org_idempotency", "animated_template_manifests", type_="unique")
    op.drop_index("ix_atm_org_product_slot", table_name="animated_template_manifests")
    op.drop_index("ix_atm_org_source_reuse", table_name="animated_template_manifests")
    op.execute("DROP INDEX IF EXISTS ix_atm_org_campaign_status_created")
    op.drop_table("animated_template_manifests")
```

### B.4 SQLAlchemy model details

Use `MutableDict` and `MutableList` for JSONB fields that are mutated in-place, or always assign new dict/list objects in repository updates. To avoid subtle SQLAlchemy dirty-state bugs, the repository should always assign new values:

```python
record.manifest_json = copy.deepcopy(manifest_payload)
record.review_reasons = list(review_reasons)
record.risk_summary = dict(risk_summary)
```

Use Python-side UUID defaults:

```python
id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
```

But make Alembic not depend on DB UUID generation unless existing project already uses `gen_random_uuid()`.

Add `updated_at` update behavior in model:

```python
updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
```

Because Alembic `server_default=sa.func.now()` does not update automatically on row updates.

## C. Manifest validation algorithms

### C.1 Validation should be layered

Use four validation passes:

1. **Shape validation** through Pydantic.
2. **Reference integrity validation** across IDs.
3. **Policy validation** for product/model/locked-layer rules.
4. **Renderability validation** using render request, fonts, output formats, and model capabilities.

Each pass should return structured issues:

```python
@dataclass(frozen=True)
class ManifestIssue:
    severity: Literal["blocking", "review", "warning"]
    code: str
    message: str
    path: str
    layer_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
```

Issue codes should be stable because frontend state machines and tests will assert them.

### C.2 Reference integrity algorithm

Pseudo-code:

```python
def validate_references(manifest):
    layer_ids = set()
    group_ids = set()
    mask_ids = set(manifest.masks.keys())
    color_role_ids = set(manifest.colorRoles.keys())
    text_role_ids = set(manifest.textRoles.keys())

    for layer in manifest.layers:
        if layer.id in layer_ids:
            issue("DUPLICATE_LAYER_ID", path=f"layers[{idx}].id")
        layer_ids.add(layer.id)

    for group in manifest.groups:
        if group.id in group_ids:
            issue("DUPLICATE_GROUP_ID", path=f"groups[{idx}].id")
        group_ids.add(group.id)

    for layer in manifest.layers:
        if layer.parentGroupId and layer.parentGroupId not in group_ids:
            issue("UNKNOWN_PARENT_GROUP", layer_id=layer.id)
        if layer.geometry.clipMaskId and layer.geometry.clipMaskId not in mask_ids:
            issue("UNKNOWN_CLIP_MASK", layer_id=layer.id)
        if layer.content.textRoleId and layer.content.textRoleId not in text_role_ids:
            issue("UNKNOWN_TEXT_ROLE", layer_id=layer.id)
        for role_field in color_role_fields(layer):
            if role_field.value not in color_role_ids:
                issue("UNKNOWN_COLOR_ROLE", layer_id=layer.id)
```

Also validate z-index determinism:

* z-index can be equal for layers only if `renderOrder` or original array index is preserved.
* Preferred: require unique `(zIndex, order)` where order is explicit.
* Add `renderOrder` to each layer or use layer array order as stable tie-breaker and store `zIndexTieBreakPolicy="array_order"` in manifest.

### C.3 Product policy algorithm

Pseudo-code:

```python
def validate_product_policy(manifest, render_request=None):
    product = manifest.productReplacement
    product_swap_layers = [
        layer for layer in manifest.layers
        if layer.policy == "product_swap" or layer.type == "product"
    ]

    if not product.hasCompetitorProductSlot:
        if product_swap_layers:
            blocking("PRODUCT_SWAP_WITHOUT_SOURCE_SLOT")
        if render_request and render_request.productReplacementRequested:
            blocking("PRODUCT_SLOT_REQUIRED")
        return

    eligible_slots = [
        slot for slot in product.sourceProductSlots
        if slot.replacementEligible and not slot.reviewRequired
    ]

    if product.status in {"uncertain", "review_required"}:
        if render_request and render_request.productReplacementRequested:
            blocking("PRODUCT_SLOT_REVIEW_REQUIRED")
        else:
            review("PRODUCT_SLOT_UNCERTAIN")
        return

    if product.replacementAllowed and not eligible_slots:
        blocking("PRODUCT_REPLACEMENT_ALLOWED_WITH_NO_ELIGIBLE_SLOT")

    for slot in eligible_slots:
        if not slot.evidence:
            blocking("PRODUCT_SLOT_MISSING_EVIDENCE")
        if not slot.geometry.canonicalMaskId and not slot.geometry.canonicalBox:
            blocking("PRODUCT_SLOT_MISSING_GEOMETRY")
        if slot.targetConstraints.deterministicOverlayRequired and slot.targetConstraints.allowModelToRenderProduct:
            blocking("PRODUCT_SLOT_CONFLICTING_RENDER_POLICY")
```

Human approval event should be required for `replacementAllowed=true` unless the system is in internal test mode and confidence exceeds a configured threshold. Production should require human confirmation for product replacement because product insertion is the most dangerous failure class.

### C.4 Locked-layer ownership algorithm

Pseudo-code:

```python
LOCKED_POLICIES = {
    "locked_source_region",
    "deterministic_rebuild",
    "brand_swap",
    "logo_swap",
    "product_swap",
    "copy_swap",
}

def validate_locked_layer_ownership(manifest):
    for layer in manifest.layers:
        owner = layer.rendering.owner
        if layer.policy in LOCKED_POLICIES and owner == "ai_region_model":
            blocking("LOCKED_LAYER_AI_OWNER_FORBIDDEN", layer_id=layer.id)
        if layer.policy == "generative_region" and owner != "ai_region_model":
            warning_or_block("GENERATIVE_REGION_NOT_AI_OWNED", depending on render mode)
        if layer.policy == "generative_region":
            if not layer.geometry.clipMaskId:
                blocking("GENERATIVE_REGION_MISSING_MASK", layer_id=layer.id)
            if layer.content.containsLockedText:
                blocking("GENERATIVE_REGION_CONTAINS_LOCKED_TEXT", layer_id=layer.id)
```

Additionally derive a union mask of locked text/chart/product/UI layers and ensure it is excluded from all AI masks:

```python
for ai_region in ai_regions:
    overlap = mask_iou(ai_region.mask, locked_union_mask)
    if overlap > threshold:
        blocking("AI_REGION_OVERLAPS_LOCKED_LAYER")
```

This prevents the model from touching text/chart/UI even if the manifest mistakenly labels the region generative.

### C.5 Timing validation algorithm

```python
def validate_timing(manifest):
    delays = manifest.timeline.frameDelaysMs
    frame_times = manifest.timeline.frameTimesMs
    if len(delays) != len(frame_times):
        blocking("FRAME_TIMING_LENGTH_MISMATCH")
    if any(delay <= 0 for delay in delays):
        blocking("NON_POSITIVE_FRAME_DELAY")
    duration = sum(delays)
    if abs(duration - manifest.timeline.durationMs) > 2:
        blocking("DURATION_MISMATCH")
    for layer in manifest.layers:
        motion = layer.motion
        if not motion:
            continue
        if motion.startMs is not None and motion.startMs < 0:
            blocking("MOTION_START_NEGATIVE")
        if motion.endMs is not None and motion.endMs > manifest.timeline.durationMs:
            blocking("MOTION_END_AFTER_DURATION")
        for keyframe in motion.keyframes:
            if keyframe.timeMs < 0 or keyframe.timeMs > manifest.timeline.durationMs:
                blocking("KEYFRAME_TIME_OUT_OF_RANGE")
```

Do not “fix” invalid timings by clamping. Return a clean validation error.

### C.6 Text validation algorithm

For each text layer:

* target text exists if required;
* target text does not contain unresolved placeholders;
* target text does not include `[UNKNOWN]` or `[UNREADABLE]` unless manifest explicitly allows placeholder-visible output for review;
* font policy is resolved;
* box is nonzero;
* rotation is finite;
* overflow policy is valid.

Text fit validation belongs in render plan preparation because it depends on target copy and resolved fonts:

```python
def validate_text_fit(layer, target_text, resolved_font):
    measured = text_renderer.measure(target_text, style, max_width=box.w)
    if measured.fits:
        return []
    if layer.content.overflowPolicy == "review_required":
        blocking("TEXT_OVERFLOW_REVIEW_REQUIRED")
    elif layer.content.overflowPolicy == "shrink_to_fit":
        fitted = shrink_until_fit(...)
        if fitted.font_size < layer.style.minFontSizePx:
            blocking("TEXT_MIN_FONT_SIZE_EXCEEDED")
    elif layer.content.overflowPolicy == "clip_like_source":
        warning("TEXT_WILL_CLIP_LIKE_SOURCE")
```

### C.7 Color validation algorithm

* Every role with `policy="brand_token"` must have either `targetValue` or a resolvable `brandTokenPath`.
* `targetValue` must be a valid hex or RGBA.
* Preserved source color should not be remapped unless the role’s policy permits it.
* Linked roles must not form cycles.

Cycle detection:

```python
def validate_color_links(color_roles):
    visiting = set()
    visited = set()

    def dfs(role_id):
        if role_id in visiting:
            blocking("COLOR_ROLE_LINK_CYCLE")
        if role_id in visited:
            return
        visiting.add(role_id)
        linked = color_roles[role_id].linkedRole
        if linked:
            if linked not in color_roles:
                blocking("UNKNOWN_LINKED_COLOR_ROLE")
            dfs(linked)
        visiting.remove(role_id)
        visited.add(role_id)
```

## D. Deterministic renderer internals

### D.1 Render plan compilation

The renderer should not consume the raw manifest directly. Compile a render plan with all variables resolved:

* final text strings;
* resolved color hex values;
* resolved font files/fallbacks;
* resolved source frame paths;
* resolved mask paths;
* resolved generated region frame paths;
* product asset placement transforms;
* output frame times.

Render plan schema excerpt:

```json
{
  "renderPlanVersion": 1,
  "rendererVersion": "animated-template-renderer-v1",
  "canvas": {
    "width": 996,
    "height": 996,
    "background": { "type": "solid", "color": "#050505" }
  },
  "frames": [
    {
      "frameIndex": 0,
      "timeMs": 0,
      "delayMs": 180,
      "sourceFrameKey": "..."
    }
  ],
  "layers": [
    {
      "id": "layer_axis_y",
      "resolvedType": "text",
      "policy": "deterministic_rebuild",
      "renderOwner": "deterministic_renderer",
      "zIndex": 20,
      "visibility": { "frameIndexes": [0, 1, 2] },
      "geometry": {},
      "resolvedStyle": {},
      "resolvedContent": {}
    }
  ]
}
```

The compilation step should fail if any layer has unresolved tokens. Rendering should not be the place where business policy decisions happen.

### D.2 Frame rendering sequence

For every frame:

1. Initialize canvas:

   * transparent RGBA if source transparent;
   * solid background if manifest says solid;
   * source frame copy if background is locked source.
2. Render layers in sorted order:

   * source regions,
   * generated regions,
   * deterministic shapes/paths,
   * product/logo overlays,
   * text,
   * foreground effects.
3. Apply per-layer opacity and blend mode.
4. Validate no pixels exist outside declared mask for generated regions.
5. Save PNG frame.

Pseudo-code:

```python
for frame in render_plan.frames:
    canvas = create_canvas(render_plan.canvas)
    for layer in sorted_layers:
        if not layer_visible(layer, frame):
            continue
        layer_image = render_layer(layer, frame)
        if layer.mask:
            layer_image = apply_mask(layer_image, resolve_mask(layer, frame))
        canvas = composite(canvas, layer_image, blend=layer.blendMode, opacity=layer.opacity)
    save_frame(canvas, frame.path)
```

### D.3 Source-region rendering

A `locked_source_region` can be rendered in three ways:

* whole source frame as base;
* crop source box and paste at same location;
* crop source box and paste with mask.

For fidelity, if most of the template is preserved, use the source frame as base and then redraw changed deterministic layers on top. If text is being swapped, first remove or cover source text. Source text removal is hard; for chart/text templates v1 should prefer deterministic rebuild of all text/chart layers over source base where source text would conflict.

Two approaches:

**Approach 1: full deterministic redraw.** Good for charts/cards. Create clean background and draw everything.

**Approach 2: source plate with occlusion patches.** Good for photographic/social/UGC templates. Preserve source pixels, cover only replaced text/logo/product areas with source-derived patches or approved background fill.

The render plan should explicitly declare `backgroundPlateMode`.

### D.4 Text rasterization internals

Use an SVG document per frame for vector/text layers, then rasterize. Each text layer becomes:

```xml
<g transform="translate(cx cy) rotate(-90)">
  <text
    x="0"
    y="0"
    font-family="Inter"
    font-size="40"
    font-weight="800"
    letter-spacing="18"
    text-anchor="middle"
    dominant-baseline="central"
    fill="#C83232">ENERGY LEVEL</text>
</g>
```

For multiline text, use `<tspan>` rows with explicit `x` and `dy`. Avoid relying on browser automatic line wrapping because SVG wrapping behavior differs. Compute line breaks in Python during text fitting and render explicit tspans.

Text measurement:

* Use the same renderer for measure and final render where possible.
* If using Pango/Cairo, measure through Pango.
* If using headless Chromium/SVG, use a small measurement subprocess that renders SVG text to a bounding box or uses canvas `measureText` with loaded fonts.

Store measurement output in render stats:

```json
{
  "textFit": [
    {
      "layerId": "layer_brand_phrase",
      "targetText": "WITH TENOR",
      "fontSizePx": 38,
      "appliedShrink": 0,
      "fits": true,
      "measuredBox": [100, 200, 240, 40]
    }
  ]
}
```

### D.5 Chart path renderer internals

For a path draw-on layer:

* Parse SVG path.
* Compute length using a path library or sampled polyline approximation.
* For each frame, determine progress from motion keyframes.
* Render path with `stroke-dasharray=path_length` and `stroke-dashoffset=path_length * (1-progress)`.
* Render point markers only when their source timing says visible.
* Do not infer extra points from target product/copy.

For chart QA, store path signatures:

```json
{
  "pathSignature": {
    "numCommands": 8,
    "approxLength": 720.4,
    "sampledPointsHash": "hex",
    "markerCount": 0
  }
}
```

The source and output should have the same marker count unless the manifest explicitly changed it.

### D.6 Product compositor internals

The compositor should create a product overlay stack:

1. base target product image;
2. alpha extraction if needed;
3. form-factor fit;
4. perspective transform;
5. slot mask;
6. occlusion mask;
7. shadow;
8. highlights.

Algorithm:

```python
def composite_product_slot(canvas, slot, product_asset, frame):
    product = load_product_rgba(product_asset)
    product = normalize_product_foreground(product, product_asset.alpha_policy)
    fit = compute_fit_transform(product.size, slot.box, slot.fit_policy)
    product = apply_transform(product, fit)
    if slot.perspective_quad:
        product = warp_to_quad(product, slot.perspective_quad_for_frame(frame))
    if slot.mask:
        product = apply_alpha_mask(product, slot.mask_for_frame(frame))
    if slot.shadow:
        canvas = composite(canvas, render_shadow(product, slot.shadow), below=True)
    canvas = composite(canvas, product, z=slot.z_index)
    if slot.highlight:
        canvas = composite(canvas, slot.highlight_for_frame(frame), z=slot.z_index + 1)
    return canvas
```

No product compositor code should run unless render plan has `product_replacements`. That list is only compiled when manifest product evidence is approved.

### D.7 Generated region compositing internals

Generated regions can be supplied as:

* MP4/video clip,
* image sequence,
* single image.

The renderer converts all generated region outputs into per-frame RGBA images aligned to the output timeline. For MP4:

* decode frames at output frame times using ffmpeg;
* if source timeline has variable frame delays, sample generated video by timestamp;
* store sampled region frames as artifacts;
* apply region mask;
* composite at declared z-index.

No generated region should include final overlay text. The deterministic layer stack should place text/UI/chart/product layers above it.

### D.8 Export internals

GIF export command pattern:

```bash
ffmpeg -y \
  -f concat -safe 0 -i frames.txt \
  -vf "split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=sierra2_4a" \
  -loop 0 final.gif
```

For variable frame delays, `frames.txt` uses concat demuxer:

```text
file 'frame_0000.png'
duration 0.180
file 'frame_0001.png'
duration 0.180
...
file 'frame_0015.png'
duration 0.180
file 'frame_0015.png'
```

The repeated final frame is required by ffmpeg concat behavior to preserve final duration. Record this in export stats so QA does not interpret it as an extra semantic frame.

Animated WebP command pattern:

```bash
ffmpeg -y \
  -f concat -safe 0 -i frames.txt \
  -vcodec libwebp -lossless 0 -q:v 80 -loop 0 -an final.webp
```

MP4 command pattern:

```bash
ffmpeg -y \
  -r 30 -i frame_%04d.png \
  -c:v libx264 -pix_fmt yuv420p -crf 18 -movflags +faststart final.mp4
```

When converting variable-delay frames to MP4, generate duplicated/interpolated frame sequence at target fps and record:

```json
"mp4Timing": {
  "sourceTiming": "variable_frame_delays",
  "exportTiming": "constant_fps",
  "fps": 30,
  "resampledFrameCount": 86
}
```

## E. Frontend review UX state machines

### E.1 Manifest review page state machine

The manifest review page should not be a generic JSON editor. It should be a guided state machine optimized for fast human decisions.

States:

```ts
type ManifestReviewState =
  | { name: "loading" }
  | { name: "analysisProcessing"; workflowRunId: string }
  | { name: "needsReview"; manifest: AnimatedTemplateManifest; activePanel: ReviewPanel }
  | { name: "editing"; manifest: AnimatedTemplateManifest; draftEdits: ManifestEdit[] }
  | { name: "savingEdits"; manifest: AnimatedTemplateManifest }
  | { name: "approvalBlocked"; manifest: AnimatedTemplateManifest; blockingIssues: Issue[] }
  | { name: "approving"; manifest: AnimatedTemplateManifest }
  | { name: "approved"; manifest: AnimatedTemplateManifest }
  | { name: "rejected"; manifest: AnimatedTemplateManifest }
  | { name: "error"; error: AnimatedTemplateApiError };
```

Transitions:

* `loading -> analysisProcessing` if manifest not ready but workflow ID exists.
* `loading -> needsReview` if manifest loaded and not approved.
* `needsReview -> editing` when user edits text role, color role, product decision, or layer policy.
* `editing -> savingEdits` on save.
* `savingEdits -> needsReview` on success.
* `needsReview -> approvalBlocked` if approve API returns validation blockers.
* `needsReview -> approving` on approve attempt.
* `approving -> approved` on success.
* `needsReview -> rejected` on reject.
* Any state -> error on API failure.

Panel priority:

1. Blocking issues.
2. Product slot decision.
3. Text roles.
4. Color roles.
5. Generative regions.
6. Layer list.
7. Raw manifest.

The UI should automatically open the highest-risk panel. For the Mars chart no-product case, it should open Product Slot Decision and show “No product slot detected; product insertion disabled.”

### E.2 Product slot panel states

```ts
type ProductSlotPanelState =
  | { name: "notDetected"; negativeEvidence: Evidence[]; confirmed: boolean }
  | { name: "detectedNeedsApproval"; slots: ProductSlotCandidate[]; selectedSlotId?: string }
  | { name: "uncertain"; candidates: ProductSlotCandidate[]; requiredAction: "confirm_none" | "select_slot" }
  | { name: "approvedSlot"; slot: ProductSlotCandidate }
  | { name: "rejectedAll"; reason: string };
```

Actions:

* `Confirm no product slot`.
* `Approve selected product slot`.
* `Reject candidate`.
* `Draw/adjust mask` if mask editing is available.
* `Require manual manifest` if detector is too uncertain.

A render button should remain disabled if product slot state is `uncertain` and any product replacement is requested.

### E.3 Render run page state machine

```ts
type AnimatedTemplateRunState =
  | { name: "notStarted"; manifestId: string }
  | { name: "estimatingCost" }
  | { name: "readyToRender"; costEstimate: CostEstimate }
  | { name: "startingRender" }
  | { name: "processing"; runId: string; step: RenderStep }
  | { name: "qaWarning"; run: AnimatedTemplateRun }
  | { name: "qaFailed"; run: AnimatedTemplateRun }
  | { name: "succeeded"; run: AnimatedTemplateRun }
  | { name: "failed"; run: AnimatedTemplateRun | null; error: ApiError };
```

Render steps:

* `preparing_render_plan`
* `generating_ai_regions`
* `rendering_frames`
* `exporting_outputs`
* `running_qa`
* `persisting_assets`

If `costEstimate.modelCallsRequired=false`, the UI should label the run “deterministic render only.” If a model is selected anyway, show a blocking warning rather than allowing a confusing run.

### E.4 Diff/contact-sheet viewer interactions

The viewer should have these toggles:

* source only,
* output only,
* side-by-side,
* diff heatmap,
* layer overlay,
* changed regions only,
* product slot mask,
* generative region mask,
* OCR boxes.

Default view after render:

* show side-by-side contact sheet;
* highlight blocking QA issues;
* show source and output at frames with largest diff;
* show product policy summary at top.

Human review speed details:

* Use keyboard shortcuts:

  * `A` approve asset,
  * `R` reject asset,
  * `D` toggle diff,
  * `M` toggle masks,
  * arrow keys scrub frames.
* Show a small “What changed?” summary:

  * brand text changed,
  * copy roles changed,
  * product inserted: no/yes approved slot,
  * AI regions: none/list.

## F. API error contracts

### F.1 Error envelope

Use one consistent envelope:

```json
{
  "error": {
    "code": "PRODUCT_SLOT_REQUIRED",
    "message": "Product replacement was requested, but the approved manifest does not contain a competitor product slot.",
    "severity": "blocking",
    "requestId": "optional",
    "workflowRunId": "optional",
    "manifestId": "optional",
    "runId": "optional",
    "details": {},
    "actions": [
      {
        "type": "review_manifest",
        "label": "Review product slot decision",
        "href": "/campaigns/.../animated-templates/.../review"
      }
    ]
  }
}
```

Keep `message` human-readable but not overly long. Put debug payload in `details`.

### F.2 Key errors

`MANIFEST_NOT_APPROVED`:

```json
{
  "error": {
    "code": "MANIFEST_NOT_APPROVED",
    "message": "This animated template manifest must be approved before rendering.",
    "severity": "blocking",
    "manifestId": "uuid",
    "details": {
      "status": "needs_review",
      "reviewReasons": ["approval_required_before_render"]
    }
  }
}
```

`MANIFEST_VERSION_MISMATCH`:

```json
{
  "error": {
    "code": "MANIFEST_VERSION_MISMATCH",
    "message": "The approved manifest version no longer matches the render request.",
    "severity": "blocking",
    "details": {
      "requestedVersion": 1,
      "currentVersion": 2
    }
  }
}
```

`LOCKED_LAYER_AI_OWNER_FORBIDDEN`:

```json
{
  "error": {
    "code": "LOCKED_LAYER_AI_OWNER_FORBIDDEN",
    "message": "A locked template layer was assigned to an AI renderer. Locked layers must be rendered deterministically.",
    "severity": "blocking",
    "details": {
      "layerId": "layer_axis_y",
      "policy": "deterministic_rebuild",
      "renderOwner": "ai_region_model"
    }
  }
}
```

`UNSUPPORTED_MODEL_FOR_REGION`:

```json
{
  "error": {
    "code": "UNSUPPORTED_MODEL_FOR_REGION",
    "message": "The selected model does not support the required masked animated region input.",
    "severity": "blocking",
    "details": {
      "provider": "creative_service",
      "modelId": "sora-2",
      "regionId": "ugc_region",
      "requiredCapabilities": ["mask_input", "duration_2860ms", "square_output"],
      "supportedCapabilities": ["text_to_video"]
    }
  }
}
```

`MODEL_MISMATCH`:

```json
{
  "error": {
    "code": "MODEL_MISMATCH",
    "message": "The provider returned output from a different model than the one explicitly selected.",
    "severity": "blocking",
    "details": {
      "requestedModelId": "sora-2",
      "actualModelId": "sora-2-pro"
    }
  }
}
```

`QA_FAILED_PRODUCT_POLICY`:

```json
{
  "error": {
    "code": "QA_FAILED_PRODUCT_POLICY",
    "message": "QA detected a product-like object in the output even though the source manifest does not approve a product slot.",
    "severity": "blocking",
    "details": {
      "hasCompetitorProductSlot": false,
      "detectedFrames": [4, 5, 6],
      "qaArtifactUrl": "signed-url"
    }
  }
}
```

## G. QA artifact generation details

### G.1 Contact sheet generation

Build contact sheets using selected frame indexes:

```python
def select_qa_frames(source_frame_manifest, diff_metrics=None):
    frames = {0, last, middle}
    frames.update(uniform_sample_indexes(count=8))
    if diff_metrics:
        frames.update(top_n_by_diff(diff_metrics, n=4))
    return sorted(frames)
```

Contact sheet layout:

* each row is one frame index;
* columns:

  * source,
  * output,
  * diff,
  * overlay/masks optional.
* label strip above each cell includes `frameIndex`, `timeMs`, and `delayMs`.
* labels are outside image content.

Artifact keys:

```text
qa/source_output_contact_sheet.png
qa/diff_heatmap_contact_sheet.png
qa/mask_overlay_contact_sheet.png
qa/ocr_boxes_contact_sheet.png
```

### G.2 Diff heatmap

Compute diff only after excluding approved changed masks. For locked-layer fidelity, changed masks are not ignored if the locked layer should match source.

Masks:

* `approved_change_mask`: brand text, copy text, color-swapped chart lines, product slot if approved, generative regions.
* `locked_mask`: source UI, chart geometry, unmodified labels, background source regions.

Metrics:

```python
locked_diff = diff(source, output, mask=locked_mask)
approved_diff = diff(source, output, mask=approved_change_mask)
```

The heatmap should visually emphasize `locked_diff`, because approved changes are expected.

### G.3 OCR QA

Run OCR on output keyframes and compare against expected final text roles.

Report:

```json
{
  "expectedTextRoles": [
    {
      "textRoleId": "axis_label_y",
      "expected": "ENERGY LEVEL",
      "policy": "preserve_text",
      "expectedBox": [52, 236, 30, 360],
      "expectedRotation": -90
    }
  ],
  "observedText": [
    {
      "text": "ENERGY LEVEL",
      "confidence": 0.91,
      "box": [50, 238, 32, 358],
      "matchedTextRoleId": "axis_label_y"
    }
  ],
  "unexpectedText": [],
  "missingTextRoles": [],
  "duplicateTextRoles": []
}
```

Blocking:

* missing required text role;
* unexpected readable text in generated region;
* duplicate brand phrase where only one expected;
* placeholder tokens visible.

### G.4 Product policy QA

For every output frame sampled:

* run product-like object detector;
* compare detections to approved product slot masks;
* inspect `ai_metadata` to ensure product references were not sent to model when disallowed;
* assert deterministic product compositor was the only product renderer if slot approved.

Report:

```json
{
  "hasCompetitorProductSlot": false,
  "replacementApplied": false,
  "productReferencesSentToModel": false,
  "productLikeDetections": [],
  "status": "pass"
}
```

For approved product slot:

```json
{
  "hasCompetitorProductSlot": true,
  "replacementApplied": true,
  "slotId": "product_slot_1",
  "detectionsOutsideApprovedSlot": [],
  "maskContainmentScore": 0.99,
  "status": "pass"
}
```

Blocking if product appears outside approved slot or appears when no slot exists.

### G.5 Timing QA

Compare:

* duration,
* frame count,
* frame delays,
* loop count,
* key motion event times.

Report:

```json
{
  "sourceDurationMs": 2860,
  "outputDurationMs": 2860,
  "durationDeltaMs": 0,
  "sourceFrameCount": 16,
  "outputFrameCount": 16,
  "frameDelayDeltaMaxMs": 0,
  "loopCountMatches": true,
  "status": "pass"
}
```

### G.6 Chart QA

For chart templates:

* use edge extraction and color segmentation on output;
* compare expected chart path samples to detected output path;
* count markers;
* compare axis/tick label boxes;
* compare line colors.

Blocking issues:

* extra chart point/marker;
* missing chart segment;
* path deviation above threshold;
* axis label orientation mismatch;
* duplicate labels.

This specifically prevents the Sora-style chart drift documented in the request.

## H. Cost accounting

### H.1 Cost component schema

Store both estimate and actual with same shape:

```json
{
  "schemaVersion": 1,
  "currency": "USD",
  "analysis": {
    "localCpuMs": 4200,
    "paidModelCalls": [],
    "estimatedUsd": 0,
    "actualUsd": 0
  },
  "deterministicRendering": {
    "frameCount": 16,
    "canvasPixels": 992016,
    "outputFormats": ["gif", "webp"],
    "renderCpuMs": 5100,
    "exportCpuMs": 1700,
    "estimatedUsd": 0,
    "actualUsd": 0
  },
  "aiRegions": [
    {
      "regionId": "ugc_region",
      "provider": "creative_service",
      "modelId": "sora-2",
      "durationSeconds": 3,
      "resolution": "996x996",
      "estimatedUsd": 1.25,
      "actualUsd": 1.31,
      "remoteRunId": "..."
    }
  ],
  "storage": {
    "sourceBytes": 500000,
    "intermediateBytes": 9000000,
    "outputBytes": 2400000
  },
  "totalEstimatedUsd": 0,
  "totalActualUsd": 0
}
```

### H.2 Estimate algorithm

Estimate before render:

```python
def estimate_cost(manifest, render_request):
    ai_regions = manifest.layers where policy == "generative_region"
    deterministic = estimate_local_render(manifest.timeline.frame_count, canvas_pixels, formats)
    if not ai_regions:
        return modelCallsRequired=False, total=0
    for region in ai_regions:
        require model_selection
        model_price = lookup_provider_price(model_selection)
        estimate = model_price(region.duration, region.resolution)
```

If provider pricing is unknown, return:

```json
{
  "estimateStatus": "unknown_provider_pricing",
  "modelCallsRequired": true,
  "requiresUserConfirmation": true
}
```

Do not fake a price.

### H.3 Actual cost recording

For creative service model calls, store:

* provider request ID,
* session ID,
* model ID,
* billable seconds if returned,
* token/frame/second units if returned,
* provider-reported cost if returned.

If provider does not return cost, record:

```json
{
  "actualUsd": null,
  "actualCostUnavailableReason": "provider_did_not_return_cost"
}
```

Do not invent actual cost from estimate.

## I. Test matrix

### I.1 Unit tests: schema and validation

`test_manifest_requires_unique_layer_ids`

* two layers with same ID;
* expect `DUPLICATE_LAYER_ID`.

`test_product_swap_blocked_without_slot`

* manifest has `hasCompetitorProductSlot=false`;
* layer policy `product_swap`;
* expect `PRODUCT_SWAP_WITHOUT_SOURCE_SLOT`.

`test_locked_layer_ai_owner_blocked`

* text layer policy `deterministic_rebuild`, owner `ai_region_model`;
* expect `LOCKED_LAYER_AI_OWNER_FORBIDDEN`.

`test_ai_region_requires_mask`

* generative layer no mask;
* expect `GENERATIVE_REGION_MISSING_MASK`.

`test_color_role_link_cycle_blocked`

* role A links to B, B links to A;
* expect `COLOR_ROLE_LINK_CYCLE`.

`test_manifest_version_mismatch_blocks_render`

* approved row version 2, request version 1;
* expect `MANIFEST_VERSION_MISMATCH`.

### I.2 Unit tests: idempotency

`test_analysis_source_idempotency_reuses_same_source`

* same source bytes, same org, same source URL;
* second activity call returns existing storage key.

`test_manifest_persist_idempotency_no_duplicate_rows`

* same manifest SHA and idempotency key;
* second persist returns same manifest ID.

`test_render_plan_idempotency_differs_on_copy_change`

* same manifest, different final text;
* keys differ.

`test_render_plan_idempotency_differs_on_model_selection`

* same manifest, same request, different model ID;
* keys differ.

`test_export_idempotency_differs_on_output_format`

* GIF and WebP keys differ.

### I.3 Renderer tests

`test_text_rotation_preserved`

* vertical label at -90 degrees;
* output OCR/geometry confirms rotation.

`test_chart_path_no_extra_markers`

* source manifest marker count 0;
* output chart QA marker count 0.

`test_variable_frame_delays_preserved_in_gif`

* source delays `[100, 500, 100]`;
* output GIF delays match within tolerance.

`test_product_compositor_requires_slot`

* direct call with no product replacements;
* no product overlay invoked.

`test_generated_region_mask_clipping`

* generated region has pixels outside mask;
* compositor clips output;
* QA reports no leakage after clipping.

`test_font_missing_blocks_without_approved_fallback`

* missing font, no fallback;
* expect `FONT_UNAVAILABLE`.

### I.4 API tests

`test_analyze_requires_one_source`

* both `companySwipeId` and `sourceUrl`;
* expect 422 or 400.

`test_render_unapproved_manifest_returns_409`

* manifest status `needs_review`;
* render endpoint returns `MANIFEST_NOT_APPROVED`.

`test_approve_manifest_with_blockers_returns_409`

* manifest validation has blocking issue;
* approve returns blocker list.

`test_cost_estimate_no_ai_regions_zero_model_cost`

* chart manifest;
* returns `modelCallsRequired=false`.

`test_unused_model_selection_rejected`

* chart manifest, model selection supplied;
* returns `UNUSED_MODEL_SELECTION`.

### I.5 Integration tests

`test_chart_template_end_to_end_no_ai`

* fixture GIF chart;
* analyze -> approve -> render -> QA;
* output asset created;
* `aiRequired=false`;
* product slot false;
* no product references sent.

`test_product_badge_template_requires_approval`

* product candidate detected;
* render before approval blocked;
* after approval product replacement succeeds.

`test_social_ui_template_locks_chrome`

* UI chrome layers detected;
* generated region only post media;
* final overlay preserves UI labels.

`test_campaign_static_path_unaffected`

* existing image brief with static collection;
* same static flow still succeeds.

`test_campaign_image_path_rejects_animated_source`

* image requirement with GIF source;
* static path returns non-static unsupported error or routes only if `animated_image`.

`test_campaign_animated_requirement_routes_to_manifest`

* animated requirement with GIF source;
* creates manifest review, not static image prompt.

### I.6 Regression tests for Mars item `05`

Expected assertions:

* manifest `templateClassification.primaryFamily == "chart"`;
* `productReplacement.hasCompetitorProductSlot == false`;
* no `product_swap` layers;
* no AI regions;
* text roles include `ENERGY LEVEL`, `TIME OF DAY`, `NORMAL CRASH`, `6AM`, `12PM`, `6PM`;
* brand phrase role swaps `WITH MARS MEN` to `WITH TENOR` only via deterministic text;
* chart path layer count matches source;
* output QA has `productPolicy.status == "pass"`;
* output OCR has one `WITH TENOR`, not duplicates;
* output chart has no extra markers;
* cost model total is zero or null for model spend.

## J. Additional repository integration notes

### J.1 Static path guard

Add a small detection helper:

```python
def _is_animated_image_bytes(content: bytes, mime_type: str) -> bool:
    if mime_type == "image/gif":
        with Image.open(io.BytesIO(content)) as img:
            return getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1
    if mime_type == "image/webp":
        with Image.open(io.BytesIO(content)) as img:
            return getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1
    return False
```

Use in `generate_swipe_image_ad_activity` after `_resolve_swipe_image`:

```python
if _is_animated_image_bytes(swipe_bytes, swipe_mime_type):
    raise ApplicationError(
        "Animated swipe media is not supported by the static swipe image path. Use animated template analysis.",
        type="AnimatedSwipeRequiresAnimatedTemplateFlow",
        non_retryable=True,
    )
```

This prevents accidental prompt-only GIF handling.

### J.2 `asset_brief_types.py`

Normalize:

```python
_ALIASES = {
    "image": "image",
    "image_ad": "image",
    "image-ad": "image",
    "animated": "animated_image",
    "animated_image": "animated_image",
    "animated-image": "animated_image",
    "gif": "animated_image",
    "video": "video",
    "video_ad": "video",
    "video-ad": "video",
}
```

Use aliases for both required and optional type normalizers. Do not treat `gif` as static `image`.

### J.3 Creative generation plan split

Static `CreativeGenerationPlanArtifact.items` can remain for image items. Add `animatedItems` rather than overloading `items`, because existing code currently assumes every `items` entry is a static image plan item with `companySwipeId` and `productImagePolicy`.

New Pydantic field:

```python
animated_items: list[AnimatedCreativeGenerationPlanItem] = Field(default_factory=list, alias="animatedItems")
```

Existing static code can ignore it. Animated branch reads it.

### J.4 Media type serialization

Extend `CompanySwipeMediaModel` with optional fields:

```python
is_animated: bool | None = Field(default=None, alias="isAnimated")
duration_ms: int | None = Field(default=None, alias="durationMs")
frame_count: int | None = Field(default=None, alias="frameCount")
```

Populate from `source_metadata_json` if already known. Do not probe every media item during list endpoints; that would slow the library. Probe on upload/taxonomy or animated analysis.

## K. Final enforcement checklist

Before any animated run can produce a user-reviewable generated asset:

* source bytes are stored and hashed;
* manifest exists and is approved;
* product slot decision is explicit;
* render plan proves locked layers are deterministic;
* no model call is scheduled unless generative regions exist;
* selected model/provider is exactly honored;
* product references are attached only if approved slot requires them;
* renderer uses exact frame timing;
* QA artifacts are created;
* product policy QA passes;
* output assets include manifest/run/source provenance.

This checklist should be implemented as assertions across `prepare_render_plan`, `generate_ai_regions`, `render_frames`, `run_qa`, and `persist_outputs`, not as comments. The architecture only works if each boundary refuses unsafe ambiguity instead of trying to be helpful.
