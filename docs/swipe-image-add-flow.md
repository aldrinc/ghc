# Swipe Image Add Flow

## Purpose

This document explains where the swipe image add flow lives in the codebase, how stage one and stage two work, what assets and documents the flow uses, and where Gemini-related context is stored.

It is intended as a rebuild guide for implementing a similar workflow elsewhere.

## Short Version

There are two practical entrypoints:

- Manual backend entrypoint: `POST /swipes/generate-image-ad`
- Production app path: campaign creative production, which eventually calls the same swipe image activity

The flow is split into two major stages:

- Stage one: Gemini-based analysis and prompt generation
- Stage two: final image rendering plus asset persistence

The important architectural detail is that the system does not maintain a separate static "foundational docs" directory for Gemini. Instead, it rebuilds stage-one context from internal artifacts and DB snapshots, bundles that context into JSON documents, uploads those bundles into Gemini File Search, and stores only the upload registry metadata locally.

## Where The Flow Lives

### Library / swipe browsing UI

The saved swipes page is only a browser for company swipes. It does not start the image add workflow itself.

- `mos/frontend/src/pages/swipes/SwipesPage.tsx`
- `mos/frontend/src/api/swipes.ts`
- `mos/frontend/src/types/swipes.ts`

This page loads:

- `GET /swipes/company`
- `GET /swipes/client/{client_id}`

### Manual backend workflow entrypoint

The direct route for starting a swipe image generation run is:

- `mos/backend/app/routers/swipes.py`

Relevant route:

- `POST /swipes/generate-image-ad`

That route creates a `WorkflowRun`, starts a Temporal workflow, and passes through:

- org/client/product/campaign IDs
- asset brief ID
- requirement index
- either `companySwipeId` or `swipeImageUrl`
- optional `swipeRequiresProductImage`
- stage-one `model`
- stage-two `renderModelId`
- output count and aspect ratio

### Temporal wrapper

The Temporal workflow is intentionally thin:

- `mos/backend/app/temporal/workflows/swipe_image_ad.py`

It validates the required inputs and forwards everything into a single activity:

- `generate_swipe_image_ad_activity`

### Actual implementation

The real logic lives here:

- `mos/backend/app/temporal/activities/swipe_image_ad_activities.py`

This file contains:

- swipe source resolution
- stage-one Gemini context assembly
- Gemini File Search document bundling and upload
- stage-one copy pack generation
- stage-one render prompt generation
- stage-two image rendering
- persistence of generated assets and provenance metadata

## Production Path vs Manual Path

There are two operational modes.

### Manual path

This is the explicit swipe API:

- `POST /swipes/generate-image-ad`

It is useful if you want to run a single swipe adaptation directly.

### Production path

The normal UI path is not the manual swipe endpoint. The main product flow goes through campaign creative production:

- Frontend:
  - `mos/frontend/src/pages/campaigns/CampaignDetailPage.tsx`
  - `mos/frontend/src/components/campaigns/CampaignMetaAdsPanel.tsx`
- Backend:
  - `mos/backend/app/routers/campaigns.py`
  - `POST /campaigns/{campaign_id}/creative/produce`

That workflow eventually calls:

- `generate_assets_for_brief_activity`

inside:

- `mos/backend/app/temporal/activities/asset_activities.py`

For image requirements, that activity creates a creative generation plan, selects a curated set of swipe sources, and then calls `generate_swipe_image_ad_activity` once per planned execution item.

## Real Stage Boundaries

At the API/schema level, the stage split is explicit:

- `model` is stage one only
- `renderModelId` is stage two only

This is enforced in:

- `mos/backend/app/schemas/swipe_image_ads.py`

If a user passes an image-generation model into `model`, the request fails. The system expects a Gemini File Search-capable text model for stage one and a rendering model for stage two.

## Stage One

Stage one is the Gemini side of the flow. In practice it has several substeps.

### Stage 1A: Resolve the swipe source

The run must use exactly one swipe source:

- `companySwipeId`
- or `swipeImageUrl`

The source image is resolved to:

- raw bytes
- MIME type
- source URL

If the source is a saved company swipe, the system loads its media and prefers an image asset.

### Stage 1B: Resolve whether the swipe needs product references

The system decides whether product images should be attached as references during generation.

Policy sources:

- explicit request parameter
- filename lookup in a local profile catalog
- optional default behavior if no rule matches

The local profile catalog is:

- `mos/backend/app/data/swipe_profiles/initial_swipe_product_image_profiles_v1.json`

That file maps swipe filenames to:

- `requires_product_image: true`
- `requires_product_image: false`
- a human explanation of why

This catalog is used in both:

- swipe execution
- default swipe set planning

### Stage 1C: Load the prompt template

The stage-one swipe prompt template is:

- `mos/backend/app/prompts/swipe/swipe_to_image_ad.md`

Prompt loading is handled by:

- `mos/backend/app/services/swipe_prompt.py`

Two prompt sources are supported:

- local markdown file when `AGENTA_ENABLED=false`
- Agenta prompt registry when `AGENTA_ENABLED=true`

So prompt storage is separate from Gemini File Search storage:

- prompt template source: local file or Agenta
- contextual "foundational docs" source: internal artifacts and snapshots uploaded into Gemini File Search

### Stage 1D: Rebuild the foundational context

This is the core part people often miss.

The workflow does not keep a hand-maintained folder of Gemini docs. Instead, it reconstructs stage-one context from source-of-truth data inside MOS.

The required source docs are assembled in:

- `mos/backend/app/temporal/activities/swipe_image_ad_activities.py`

The flow loads or constructs the following context pieces:

- latest `client_canon`
- design system snapshot
- latest `strategy_v2_stage0`
- latest `strategy_v2_stage1`
- latest `strategy_v2_stage2`
- latest `strategy_v2_stage3`
- latest `strategy_v2_awareness_angle_matrix`
- latest `strategy_v2_offer`
- latest `strategy_v2_copy_context`
- latest `strategy_v2_copy`
- product profile snapshot
- offer pricing snapshot
- latest campaign `strategy_sheet`
- latest campaign `experiment_spec`
- the current `asset_brief` artifact

The artifact types come from:

- `mos/backend/app/db/enums.py`

The latest artifact lookup is done by:

- `mos/backend/app/db/repositories/artifacts.py`

### Stage 1E: Bundle the context for Gemini File Search

Those source docs are then rebundled into five Gemini-facing bundle docs:

- `swipe_stage1_bundle_brand_foundation`
- `swipe_stage1_bundle_offer_and_pricing`
- `swipe_stage1_bundle_strategy_stages`
- `swipe_stage1_bundle_strategy_copy`
- `swipe_stage1_bundle_campaign_context`

Each bundle is a JSON document containing:

- bundle metadata
- source doc keys
- source doc titles
- source kinds
- source content hashes
- the actual source content text

This matters because the system uploads a small number of bundled docs to Gemini rather than uploading every underlying source file independently for each request.

### Stage 1F: Upload bundle docs into Gemini File Search

Gemini File Search upload logic lives in:

- `mos/backend/app/services/gemini_file_search.py`

The upload function:

- checks whether an equivalent doc already exists by `org_id`, `idea_workspace_id`, `doc_key`, `sha256`, and `product_id`
- reuses the existing Gemini document when possible
- otherwise creates a Gemini File Search store if needed
- uploads the document
- waits for indexing to complete
- records the upload metadata locally

Important inputs used for scoping:

- `org_id`
- `idea_workspace_id`
- `client_id`
- `product_id`
- `campaign_id`
- `doc_key`
- `step_key`

For this flow, `step_key` is:

- `swipe_image_ad_stage1`

### Stage 1G: Generate the swipe copy pack

Before generating the final render prompt, the flow also generates platform-specific feed copy.

This happens in:

- `mos/backend/app/temporal/activities/swipe_image_ad_activities.py`

Specifically:

- `_generate_swipe_stage1_copy_pack`

That step:

- reads the selected requirement from the asset brief
- determines platform from channel
- determines destination page type from the funnel pages
- builds blind-angle guardrails
- asks Gemini to produce three copy variations in strict JSON
- validates the result against `SwipeAdCopyPack`
- runs additional blackout auditing to ensure the copy does not reveal the underlying mechanism too directly
- retries if the copy leaks forbidden terms or explains too much

The structured schema lives in:

- `mos/backend/app/schemas/creative_generation.py`

This copy pack becomes part of the generated asset provenance later.

### Stage 1H: Generate the final render prompt

After the copy pack is ready, Gemini gets the actual swipe-to-image prompt request.

Inputs sent to Gemini:

- rendered prompt template
- competitor swipe image bytes
- optional product reference image bytes
- Gemini File Search tool attachment with the uploaded store names

Gemini then returns markdown that must contain exactly one fenced prompt block. The system extracts only that prompt block and rejects malformed or ambiguous outputs.

Prompt parsing happens in:

- `mos/backend/app/services/swipe_prompt.py`

The final result of stage one is:

- a dense generation-ready image prompt

## Stage Two

Stage two is the renderer plus persistence.

### Stage 2A: Choose the renderer

Renderer selection lives in:

- `mos/backend/app/services/image_render_client.py`

Provider resolution rules:

- `gemini-*` render models map to `creative_service`
- `nano-banana*` render models map to `higgsfield`
- otherwise the system falls back to `IMAGE_RENDER_PROVIDER`

The selected render model comes from:

- request `renderModelId`
- or `SWIPE_IMAGE_RENDER_MODEL`

### Stage 2B: Send the final prompt to the renderer

The renderer receives:

- extracted final prompt
- product reference asset IDs
- or product reference image URLs
- output count
- aspect ratio
- render model ID
- idempotency key

The stage-one Gemini prompt markdown itself is not sent as-is. Only the extracted image prompt is sent to the renderer.

### Stage 2C: Poll until completion

The system creates a render job, polls it until:

- `succeeded`
- or `failed`

Retryable failures are retried a limited number of times.

### Stage 2D: Persist local assets

When render outputs succeed, the system:

- downloads the generated asset bytes
- computes the file hash
- stores the bytes in media storage
- creates a local `Asset` row
- attaches provenance metadata

The persistence helper is:

- `mos/backend/app/temporal/activities/asset_activities.py`
- `_create_generated_asset_from_url`

The persisted asset has:

- `source_type = ai`
- `status = draft`
- `sourceKind = swipe_adaptation`
- `prompt`
- source URLs
- requirement metadata
- large `ai_metadata` payload for provenance

## What Assets The Flow Uses

### 1. Competitor swipe image

This is the core source image.

Origin options:

- saved company swipe media
- direct remote image URL

### 2. Product reference images

These are optional or required depending on the swipe policy.

They come from:

- product source assets selected by `_select_product_reference_assets`

These are used in two different ways:

- stage one: one product reference image may be attached to Gemini as additional image context
- stage two: product reference assets or image URLs may be attached to the renderer

### 3. Prompt template

The main prompt template is:

- `mos/backend/app/prompts/swipe/swipe_to_image_ad.md`

Optional remote prompt management source:

- Agenta registry

### 4. Design system tokens

The system reads design system tokens from the client's linked design system record and includes them in stage-one context.

This is where brand colors, fonts, and some brand asset metadata come from.

### 5. Product profile

The system constructs a snapshot including fields such as:

- title
- description
- product type
- vendor
- tags
- benefits
- feature bullets
- disclaimers

### 6. Offer and pricing

The system resolves a deterministic product offer and pricing snapshot. This is included so Gemini does not invent pricing context.

### 7. Strategy artifacts

These are the higher-level foundational strategy docs:

- client canon
- strategy v2 stages
- awareness angle matrix
- offer
- copy context
- copy
- strategy sheet
- experiment spec
- asset brief

### 8. Ad copy pack and creative generation plan

In the production campaign path, image generation is also shaped by two system-owned artifacts:

- ad copy pack artifact
- creative generation plan artifact

These are created in:

- `mos/backend/app/temporal/activities/asset_activities.py`

The creative generation plan binds each image requirement to a curated set of swipe sources.

## The Curated Default Swipe Set

In production creative generation, the system uses a default curated swipe set rather than allowing image requirements to bind arbitrary swipes in the brief.

That set is defined by filename labels in:

- `mos/backend/app/temporal/activities/asset_activities.py`

Examples include:

- `10.png`
- `11.png`
- `12.png`
- `Static #1.png`
- `big_text.jpg`
- `women_health.jpg`

The planner resolves actual `company_swipe_assets` media that match those filenames and fails if:

- any required filename is missing
- the same filename resolves to multiple different source swipes

This means the source set is system-owned, deterministic, and curated.

## Where Gemini Stores The Foundational Docs

This has three layers.

### Layer 1: Source of truth inside MOS

The actual business context does not originate in Gemini. It originates in MOS itself:

- artifact records
- client design system
- product records
- offer and variant records
- campaign records

These are the real source-of-truth objects.

### Layer 2: Gemini File Search documents

The flow converts those source-of-truth objects into bundled JSON documents and uploads them to Gemini File Search.

So the actual context consumed by Gemini during the run lives remotely in Gemini File Search stores.

The local app does not store a permanent full-text copy of those bundle docs in a dedicated docs folder. It regenerates and reuploads them from internal sources.

### Layer 3: Local registry/cache table

The app stores upload metadata in:

- `gemini_context_files`

Migration:

- `mos/backend/alembic/versions/0051_gemini_context_files.py`

Repository:

- `mos/backend/app/db/repositories/gemini_context_files.py`

Tracked fields include:

- `idea_workspace_id`
- `client_id`
- `product_id`
- `campaign_id`
- `doc_key`
- `doc_title`
- `source_kind`
- `step_key`
- `sha256`
- `gemini_store_name`
- `gemini_file_name`
- `gemini_document_name`
- `filename`
- `mime_type`
- `size_bytes`
- `status`

This is a registry and dedupe layer, not the primary content store.

## What `idea_workspace_id` Means Here

Gemini File Search uploads are scoped by `idea_workspace_id`.

For the swipe image flow, the resolver uses:

- explicit `idea_workspace_id` if provided
- otherwise `workflow_id`
- otherwise `campaign_id`
- otherwise `client_id`

In practice, campaign-level runs usually use `campaign_id` as the workspace scope.

That means the same client/product can have Gemini context uploads grouped differently depending on which campaign or workspace the run belongs to.

## How To Inspect What Gemini Currently Has

The backend exposes:

- `GET /gemini/context`
- `POST /gemini/chat/stream`

Implementation:

- `mos/backend/app/routers/gemini.py`

`GET /gemini/context` lets you list registered Gemini context files for a given:

- `ideaWorkspaceId`
- optional `clientId`
- optional `productId`
- optional `campaignId`

This is the easiest way to inspect what the app thinks is available for Gemini File Search.

## What Gets Persisted On The Final Asset

The final generated asset contains unusually rich provenance in `ai_metadata`.

Examples include:

- swipe source URL
- swipe source filename
- stage-one prompt model
- stage-two render model
- render provider
- Gemini store names
- Gemini RAG doc keys
- Gemini RAG bundle doc keys
- Gemini document names
- full stage-one prompt markdown
- extracted prompt
- placeholder map
- copy pack payload
- copy model
- product reference asset IDs
- product reference image URLs

This is useful if you want a strong audit trail in a rebuild.

## Important Constraints And Behavior

### No hidden fallbacks

This code generally fails loudly when required context is missing:

- no client canon
- no design system
- missing offer/pricing context
- missing campaign artifacts
- no product assets when the swipe explicitly requires them

That matches the repo's preference for explicit failures instead of silent fallback behavior.

### The production image path is system-owned

In campaign creative production:

- image requirements cannot specify their own explicit swipe bindings
- the system binds them to the curated default swipe set

If you rebuild this elsewhere and want operator-selected swipes instead, this is one of the first places you would change.

### Local prompt image files are not the runtime source set

There are image files under:

- `mos/backend/app/prompts/swipe/`

Those are not the primary runtime source-of-truth for the production swipe set. The production flow resolves source media from `company_swipe_assets` by matching curated filenames. The local files are prompt assets and references, not the canonical campaign swipe library.

## Rebuild Blueprint

If you want to reproduce this workflow in another system, the minimum architecture is:

### 1. A swipe source library

You need:

- saved competitor swipe records
- media records per swipe
- stable source URLs
- optional filename-based policies

### 2. A product asset library

You need:

- source product images
- product-level asset selection logic
- optional logo/design-system linkage

### 3. Internal source-of-truth strategy docs

You need a structured way to store:

- brand canon / messaging source of truth
- product profile
- offer and pricing
- campaign brief
- asset brief
- copy context / strategy docs

### 4. A Gemini context projection layer

You need code that:

- loads the source-of-truth docs
- converts them into deterministic JSON payloads
- groups them into a few larger bundles
- uploads those bundles to Gemini File Search
- dedupes them by hash
- tracks their remote document IDs locally

### 5. A stage-one Gemini workflow

You need at least two Gemini substeps:

- copy-pack generation
- render-prompt generation

And you should validate both outputs, especially if the feed copy must obey constraints like blind-angle rules.

### 6. A stage-two render provider abstraction

You need a render client abstraction that can take:

- final prompt
- optional product image references
- aspect ratio
- count
- model ID

And return:

- job status
- final output URLs
- model metadata

### 7. Provenance-heavy asset persistence

You should persist:

- final prompt used
- stage-one raw markdown
- source swipe metadata
- context store IDs
- copy-pack payload
- render job metadata
- source and output hashes

Without this, debugging drift and comparing generations becomes much harder.

## Practical If You Want A Similar Workflow Elsewhere

The cleanest conceptual split is:

1. Source library layer
2. Context assembly layer
3. Gemini stage-one layer
4. Render stage-two layer
5. Asset persistence and provenance layer

The most portable pieces from MOS are:

- the stage boundary between `model` and `renderModelId`
- deterministic JSON context bundling
- Gemini File Search upload registry
- strict prompt-output parsing
- provenance-heavy final asset metadata

The most MOS-specific pieces are:

- artifact type naming
- strategy v2 document set
- campaign creative production orchestration
- curated default swipe set logic

## Suggested Starting Point For A Rebuild

If you do not want all of MOS, the smallest practical clone is:

- one table for saved swipes
- one table for product assets
- one table for product/campaign briefs
- one table for Gemini context upload registry
- one route to run stage one
- one route to run stage two
- one asset table with full metadata

Then add:

- prompt registry support
- curated swipe sets
- copy-pack generation
- workflow orchestration

in that order.

## File Index

Main implementation files:

- `mos/backend/app/routers/swipes.py`
- `mos/backend/app/temporal/workflows/swipe_image_ad.py`
- `mos/backend/app/temporal/activities/swipe_image_ad_activities.py`
- `mos/backend/app/services/swipe_prompt.py`
- `mos/backend/app/services/gemini_file_search.py`
- `mos/backend/app/db/repositories/gemini_context_files.py`
- `mos/backend/app/services/image_render_client.py`
- `mos/backend/app/temporal/activities/asset_activities.py`
- `mos/backend/app/schemas/swipe_image_ads.py`
- `mos/backend/app/schemas/creative_generation.py`
- `mos/backend/app/prompts/swipe/swipe_to_image_ad.md`
- `mos/backend/app/data/swipe_profiles/initial_swipe_product_image_profiles_v1.json`

Related UI / workflow files:

- `mos/frontend/src/pages/swipes/SwipesPage.tsx`
- `mos/frontend/src/pages/campaigns/CampaignDetailPage.tsx`
- `mos/frontend/src/components/campaigns/CampaignMetaAdsPanel.tsx`
- `mos/backend/app/routers/campaigns.py`
- `mos/backend/app/routers/gemini.py`

