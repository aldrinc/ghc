# Swipe Collections Plan

## Decision

Keep the system simple:

- use `company_swipe_assets` as the one canonical swipe asset table
- treat the current library as the default collection
- add collections and collection membership, not a second client-level swipe asset table
- let users upload by dragging files into a collection
- run one Gemini prompt per asset with a strict schema response
- write the Gemini output directly into the swipe asset record
- do not add a human review step

## User Experience

The user flow should be:

1. Open the Swipe tab.
2. Select, create, or clone a collection.
3. Drag images or videos into that collection.
4. See each asset appear immediately with a status.
5. Use the collection for browsing, filtering, and creative selection once assets are `Ready`.

The user should not be asked to fill out taxonomy fields during upload.

## Data Model

Reuse the current canonical tables:

- `company_swipe_assets`
- `company_swipe_media`

Do not use `client_swipe_assets` for the new architecture.

Add these tables:

- `swipe_collections`
  - `id`
  - `org_id`
  - `name`
  - `kind` with values `default`, `uploaded`, `curated`
  - `cloned_from_collection_id`
  - `created_by_user_id`
  - `created_at`
- `swipe_collection_items`
  - `id`
  - `org_id`
  - `collection_id`
  - `swipe_asset_id`
  - `created_at`
  - unique key on `collection_id + swipe_asset_id`

Add these fields to `company_swipe_assets`:

- `analysis_status`
  - `queued`, `analyzing`, `ready`, `failed`
- `analysis_error`
- `analysis_model`
- `analysis_updated_at`

Store the classification fields on `company_swipe_assets` as well. One asset can belong to many collections. Moving an asset between collections should never duplicate the asset row.

## Collection Rules

- The current built-in swipe library becomes the read-only `default` collection.
- A user can create an `uploaded` collection and drag files directly into it.
- A user can create any number of `curated` collections.
- A user can clone any collection into a new `curated` collection.
- An asset can be added from the default collection into a curated collection without copying the asset.
- Cloning a collection copies collection membership only. It does not duplicate `company_swipe_assets` rows or media files.
- Collections are the main organizing primitive for creative workflows.

## Upload Flow

The upload UX should just be drag and drop.

Flow:

1. User drops one or many files onto a collection.
2. Frontend uploads the files.
3. Backend stores each file using the existing asset/media storage path.
4. Backend creates a `company_swipe_assets` row and `company_swipe_media` row for each file.
5. Backend adds each asset to the target collection through `swipe_collection_items`.
6. Backend sets `analysis_status=queued`.
7. Background work runs one Gemini classification per asset.
8. Each asset card updates in place as the classification finishes.

For a 100-file drop:

- the user still performs one drag-and-drop action
- the frontend can stream or chunk the uploads internally
- progress is shown per asset and as a simple collection-level summary

## Progress UX

Each asset only needs one visible status:

- `Uploading`
- `Queued`
- `Analyzing`
- `Ready`
- `Failed`

The collection view should show:

- total assets in the current upload
- how many are uploading
- how many are queued
- how many are analyzing
- how many are ready
- how many failed

There should be no separate review screen. The card just moves from processing to ready.

## Gemini Classification

Use one Gemini prompt and one schema for each asset.

Input to Gemini:

- the uploaded image or video
- file metadata we already have
- OCR text if available
- provider metadata if the asset came from an existing source instead of upload

Output from Gemini:

- one schema-based JSON object
- `null` for anything it cannot determine confidently

Write path:

1. send asset and context to Gemini
2. receive schema JSON
3. validate the JSON on the backend
4. write it directly to `company_swipe_assets`
5. set `analysis_status=ready`

If Gemini fails or returns invalid schema:

- set `analysis_status=failed`
- store the error in `analysis_error`
- do not silently fall back to anything else

## Gemini Response Schema

The Gemini response should be validated against this schema. All fields are nullable except `schema_version`.

System-set fields such as `source_kind`, `origin_system`, `ad_unit_format`, `placement_shape`, and `analysis_status` should be filled by the backend, not by Gemini.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "SwipeTaxonomyV1",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version"],
  "properties": {
    "schema_version": {
      "type": "string",
      "const": "swipe_taxonomy_v1"
    },
    "channel": {
      "type": ["string", "null"],
      "enum": ["meta", "tiktok", "google", null]
    },
    "destination_type": {
      "type": ["string", "null"],
      "enum": ["product_page", "collection_page", "advertorial", "listicle", "quiz", "lead_form", "article", "app_store", "marketplace", null]
    },
    "funnel_stage": {
      "type": ["string", "null"],
      "enum": ["cold", "warm", "hot", null]
    },
    "angle_family": {
      "type": ["string", "null"],
      "enum": ["problem", "symptom", "mechanism", "outcome", "identity", "comparison", "objection", "authority", "offer", "urgency", null]
    },
    "hook_type": {
      "type": ["string", "null"],
      "enum": ["direct_benefit", "curiosity_gap", "pain_agitation", "question_hook", "stat_hook", "contrarian_hook", "authority_hook", "before_after_hook", "demo_hook", "social_proof_hook", "founder_story_hook", null]
    },
    "visual_archetype": {
      "type": ["string", "null"],
      "enum": ["ugc_selfie", "ugc_spokesperson", "founder_facecam", "product_demo", "before_after", "text_heavy_static", "testimonial_screenshot", "comparison_chart", "meme_native", "offer_card", "advertorial_mock", "lifestyle_scene", null]
    },
    "product_presence": {
      "type": ["string", "null"],
      "enum": ["hero_product", "in_use_product", "contextual_product", "packaging_only", "no_product", null]
    },
    "proof_type": {
      "type": ["string", "null"],
      "enum": ["testimonial", "review_volume", "authority", "statistic", "before_after", "demo", "ingredient", "press", "guarantee", "comparison", null]
    },
    "claim_risk": {
      "type": ["string", "null"],
      "enum": ["low", "medium", "high", "regulated", null]
    },
    "product_image_policy": {
      "type": ["string", "null"],
      "enum": ["requires_product_image", "no_product_image", "either", null]
    }
  }
}
```

Backend write rules:

- validate the response exactly against this schema
- merge it with deterministic fields from the upload and media metadata
- write the merged result to `company_swipe_assets`
- fail the asset cleanly if the schema is invalid

## Required vs Optional

Only system fields are required. Almost all classification fields should be nullable.

Required:

- file upload
- target collection
- `source_kind`
- `origin_system`
- `ad_unit_format` when determinable from media
- `analysis_status`

Optional and usually Gemini-filled:

- channel
- funnel stage
- angle family
- hook type
- visual archetype
- product presence
- proof type
- claim risk
- product image policy
- destination type
- placement shape

If Gemini cannot determine an optional field, store `null` and move on.

## Swipe Taxonomy

This is the core classification table. Keep it small and useful.

| Field | Allowed values | How it gets filled | Required | Notes |
| --- | --- | --- | --- | --- |
| `source_kind` | `catalog`, `upload` | System-set | Yes | Distinguishes seeded assets from user uploads |
| `origin_system` | `meta_ads_library`, `tiktok_creative_center`, `google_ads_transparency`, `manual_upload`, `external_url`, `internal_seed_set` | System-set | Yes | Source provenance |
| `ad_unit_format` | `image`, `video`, `carousel` | Deterministic from media | Yes when determinable | Should not depend on Gemini |
| `placement_shape` | `square_1_1`, `portrait_4_5`, `story_9_16`, `landscape_16_9` | Deterministic from dimensions | No | Null if dimensions are missing |
| `channel` | `meta`, `tiktok`, `google` | Metadata first, Gemini second | No | Null if unclear |
| `destination_type` | `product_page`, `collection_page`, `advertorial`, `listicle`, `quiz`, `lead_form`, `article`, `app_store`, `marketplace` | Gemini | No | Useful but often uncertain |
| `funnel_stage` | `cold`, `warm`, `hot` | Gemini | No | Nullable |
| `angle_family` | `problem`, `symptom`, `mechanism`, `outcome`, `identity`, `comparison`, `objection`, `authority`, `offer`, `urgency` | Gemini | No | Nullable |
| `hook_type` | `direct_benefit`, `curiosity_gap`, `pain_agitation`, `question_hook`, `stat_hook`, `contrarian_hook`, `authority_hook`, `before_after_hook`, `demo_hook`, `social_proof_hook`, `founder_story_hook` | Gemini | No | Nullable |
| `visual_archetype` | `ugc_selfie`, `ugc_spokesperson`, `founder_facecam`, `product_demo`, `before_after`, `text_heavy_static`, `testimonial_screenshot`, `comparison_chart`, `meme_native`, `offer_card`, `advertorial_mock`, `lifestyle_scene` | Gemini | No | Strong image-classification field |
| `product_presence` | `hero_product`, `in_use_product`, `contextual_product`, `packaging_only`, `no_product` | Gemini | No | Strong image-classification field |
| `proof_type` | `testimonial`, `review_volume`, `authority`, `statistic`, `before_after`, `demo`, `ingredient`, `press`, `guarantee`, `comparison` | Gemini | No | Nullable |
| `claim_risk` | `low`, `medium`, `high`, `regulated` | Gemini | No | Nullable |
| `product_image_policy` | `requires_product_image`, `no_product_image`, `either` | Gemini | No | Useful for creative adaptation |

## How Creative Uses This

Collections are the main input to creative.

That means:

- when the user starts creative generation, they select a swipe collection
- that selected collection defines the swipe pool for that generation run
- only assets with `analysis_status=ready` are usable

Classification is mainly for filtering and future prompt conditioning. Collection membership is the main control surface.

There should be no implicit collection choice at generation time. If swipe-based generation needs reference assets, the selected collection should be explicit.

At generation start, the system should persist:

- `swipe_collection_id`
- `swipe_collection_name`
- the resolved list of `swipe_asset_ids` that were `ready` at the moment the run started

This matters because collections can change later. The run record needs to preserve exactly which swipe assets were actually referenced for that generation.

The generation UI should show:

- the selected collection name
- the number of ready swipe assets available in that collection
- a simple preview or count of the assets that will be referenced

If the selected collection has no ready assets, return a clear error. Do not silently fall back to another source.

## API Direction

Collection APIs:

- `GET /swipe-collections`
- `POST /swipe-collections`
- `GET /swipe-collections/{collection_id}`
- `POST /swipe-collections/{collection_id}/clone`
  - body: `name`
  - creates a new `curated` collection with the same asset memberships
- `POST /swipe-collections/{collection_id}/items`
- `DELETE /swipe-collections/{collection_id}/items/{swipe_asset_id}`

Upload API:

- `POST /swipe-collections/{collection_id}/uploads`
  - accepts one or many files
  - creates the asset rows immediately
  - returns the created asset ids and initial statuses

Swipe APIs:

- `GET /swipes?collection_id=...`
- `GET /swipes/{swipe_asset_id}`
- `PATCH /swipes/{swipe_asset_id}`

## Files Likely To Change

Backend:

- `mos/backend/app/db/models.py`
- `mos/backend/app/db/repositories/swipes.py`
- `mos/backend/app/routers/swipes.py`
- new Gemini schema prompt and activity for swipe classification

Frontend:

- `mos/frontend/src/pages/swipes/SwipesPage.tsx`
- `mos/frontend/src/api/swipes.ts`
- `mos/frontend/src/types/swipes.ts`
- `mos/frontend/src/pages/library/LibraryPage.tsx`
- `mos/frontend/src/components/campaigns/CampaignMetaAdsPanel.tsx`
- new collection list and collection detail UI
- new drag-and-drop upload area
- new per-asset status cards

## Frontend Plan

Current state:

- `SwipesPage.tsx` just loads `/swipes/company` and renders a grid
- `LibraryPage.tsx` still labels the tab as `Saved`
- there is no collection picker, clone action, upload area, or progress UI

Frontend changes:

1. Library tab
   - rename the `Saved` tab to `Swipes`
   - update the library description so it describes collections, uploads, and reference assets

2. Swipe page shell
   - replace the current single-grid page with a two-panel layout
   - left side: collection list
   - right side: selected collection header, actions, upload area, progress summary, and swipe grid

3. Collection list
   - show all collections with name, kind, and item count
   - allow `New collection`
   - allow `Clone collection`
   - selecting a collection reloads the right-side grid
   - default collection should be visibly marked as built-in

4. Clone collection UX
   - clone action should be available from the selected collection header
   - modal only asks for the new collection name
   - on success, navigate directly into the cloned collection
   - cloning should feel instant because it is only copying membership rows

5. Upload UX
   - the selected collection header should contain a drag-and-drop target
   - empty collections should show a large dropzone
   - non-empty collections should show a compact dropzone plus an upload button
   - dropped files should create immediate placeholder cards with `Uploading` status
   - cards should update in place to `Queued`, `Analyzing`, `Ready`, or `Failed`

6. Progress and refresh
   - while any visible asset is `Uploading`, `Queued`, or `Analyzing`, poll the collection endpoint on a short interval
   - stop polling automatically once all visible assets are terminal
   - show a small summary bar with counts by status

7. Swipe cards
   - reuse the current `LibraryCard` and `SwipeMedia` where possible
   - add a status badge to each card
   - add small taxonomy chips once an asset is `Ready`
   - failed cards should show the stored `analysis_error`
   - card actions should include `Add to collection` and `Remove from collection`

8. Frontend API/types
   - add `SwipeCollection` and `SwipeAnalysisStatus` types in `mos/frontend/src/types/swipes.ts`
   - replace one-off page fetching with collection-aware hooks in `mos/frontend/src/api/swipes.ts`
   - support list collections, get collection detail, clone collection, upload files, and fetch assets by collection

9. Creative generation UI
   - add a swipe collection selector near `Generate creatives` in `mos/frontend/src/components/campaigns/CampaignMetaAdsPanel.tsx`
   - show the selected collection name and ready asset count
   - block generation with a clear UI error if no collection is selected or if the selected collection has zero ready assets
   - send `swipe_collection_id` in the generation payload
   - after the run starts, display which collection was used for that run

## Build Order

1. Add `swipe_collections` and `swipe_collection_items`, including `cloned_from_collection_id`.
2. Make the existing swipe library the `default` collection.
3. Add classification/status fields to `company_swipe_assets`.
4. Add collection, clone, membership, and upload endpoints.
5. Add one Gemini schema-classification job per asset with strict schema validation.
6. Update the Swipe tab to support collections, clone, drag-and-drop upload, and per-asset progress.
7. Add collection selection to creative generation and persist the resolved swipe asset set per run.

## Bottom Line

The refined plan is:

- one canonical swipe asset table
- collections on top of it
- drag-and-drop upload
- one Gemini schema prompt
- direct write of the schema output
- no human review pass
- collections as the source of truth for creative
