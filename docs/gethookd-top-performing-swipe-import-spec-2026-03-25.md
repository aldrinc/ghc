# GetHookd Nightly Swipe Sync Spec

## Decision

- Use a nightly batch sync from GetHookd. Do not make this a user-triggered import flow.
- Treat GetHookd as a reference corpus, not as a publishing system.
- Store synced assets in the existing canonical swipe library:
  - `company_swipe_assets` for the swipe record
  - `media_assets` plus `MediaMirrorService` for canonical mirrored binaries
  - `company_swipe_media` as the swipe-facing compatibility layer
- Create a dedicated system-managed `GetHookd` collection and default nightly imports into that collection.
- Exclude GetHookd assets from the org default collection so the default library remains usable.
- Keep asset-level review state on the synced swipe so humans can decide what becomes launchable.
- Curators add approved assets into writable swipe collections. Collection membership remains the only source used for creative generation.
- Add a persisted `campaigns.default_swipe_collection_id`. Launching creative should use an explicit collection override or the campaign default. Do not silently substitute another collection.
- Reuse the existing creative-production and Meta review/publish pipeline. The new work is upstream of that pipeline, not a replacement for it.
- Reuse existing creative/library UI primitives and consolidate them into a shared review-grid component set instead of building another bespoke browser for GetHookd.

This keeps one asset system, one media system, one collection system, and one publishing path.

## Why This Shape

- The current code already has the right primitives:
  - `company_swipe_assets` as the canonical reference-ad record
  - `swipe_collections` and `swipe_collection_items` as the curation layer
  - `CreativeProductionRequest.swipeCollectionId` and `CreativeProductionWorkflow` as the launch contract
  - `media_assets` plus `MediaMirrorService` as the proven remote-media mirroring path
- The current default collection already auto-includes every non-upload swipe. That is exactly why GetHookd needs its own dedicated system collection; otherwise nightly sync will flood the default collection and make it operationally useless.
- A manual import modal solves the wrong problem. The user wants a continuously refreshed corpus, then a human curation step, then normal launch/publish.
- A direct GetHookd-to-ads flow would bypass the existing creative-production, QA, review, and publishing system and create a second operational path.

## Operating Model

1. A workspace stores a GetHookd API token and one or more sync feed definitions.
2. A nightly workflow pulls GetHookd Explore results for each active feed.
3. The workflow upserts brands, swipe assets, and mirrored media into MOS, then adds those assets to the system-managed `GetHookd` collection.
4. New or materially changed assets are marked `pending_review`.
5. Reviewers browse the `GetHookd` collection, filter to pending items, and bulk-add approved assets into curated swipe collections.
6. Campaigns store a default swipe collection.
7. Creative production uses that collection as the remix source, then the existing downstream pipeline handles QA, Meta review, and publishing.
8. Future nightly runs refresh the reference assets and flag any approved asset whose upstream creative changed.

This separates the system into four layers:

- ingestion from GetHookd
- review and curation
- campaign launch defaults
- existing generation/publishing

## Scope

### In scope

- workspace-scoped GetHookd credential storage
- workspace-scoped GetHookd sync feed configuration
- nightly GetHookd sync workflow and run logging
- GetHookd asset upsert into `company_swipe_assets`
- mirrored media storage through `media_assets` plus `MediaMirrorService`
- asset-level review state for GetHookd-origin swipes
- review UI and bulk collection-add actions
- persisted campaign default swipe collection
- continuous metadata refresh for previously synced GetHookd assets

### Out of scope

- a user-triggered per-ad import modal
- direct GetHookd-to-live-ad publishing
- auto-adding nightly imports into launch collections
- silently falling back to the org default collection at launch time
- using the system-managed `GetHookd` collection directly as a campaign launch default
- a literal unbounded crawl of all GetHookd Explore inventory every night
- rebuilding all of GetHookd Explore inside MOS

The last point matters: GetHookd billing and rate limits make a feed-driven sync defensible; a full-platform crawl is not.

## System Shape

### 1. Feed-driven nightly sync

Nightly sync should run against saved feed definitions, not an unconstrained global search.

Recommended feed examples:

- `Meta top performers - broad`
- `Meta UGC winners - wellness`
- `Meta video winners - US`

Each feed stores:

- `name`
- `enabled`
- `query`
- `platforms`
- `niche`
- `ad_format`
- `location`
- `language`
- `performance_scores`
- `status`
- `sort_column`
- `sort_direction`
- `ads_per_brand_limit`
- `max_pages_per_run`
- `per_page`

Recommended v1 defaults:

- `performance_scores = winning,optimized`
- `status = active`
- `platform = facebook,instagram`
- `sort = days_active desc`
- `per_page = 100`
- `ads_per_brand_limit = 3`
- `max_pages_per_run` set explicitly per feed so credits are bounded

### 2. Dedicated GetHookd collection

Add a system-managed collection kind for synced GetHookd inventory.

Recommended shape:

- collection kind: `gethookd_inbox`
- collection name: `GetHookd`
- auto-created per org
- membership managed only by sync code
- visible in the Swipes page
- not writable from normal collection-management UI
- not eligible as a campaign default launch collection

Default collection rules should become:

- org default collection auto-includes internal catalog assets
- org default collection excludes `origin_system = "gethookd_public_api"`
- `GetHookd` collection auto-includes assets with `origin_system = "gethookd_public_api"`

This keeps synced reference inventory browseable without destroying the signal value of the existing default collection.

### 3. Review lives on the asset, not in a second import queue

Imported GetHookd assets should remain first-class `company_swipe_assets`.

Do not create a duplicate pending table just for review. Instead add review metadata to the asset:

- `review_status`
  - `pending_review`
  - `approved`
  - `rejected`
  - `stale_after_sync`
- `reviewed_at`
- `reviewed_by_user_id`
- `source_first_seen_at`
- `source_last_seen_at`
- `source_last_synced_at`
- `source_payload_hash`
- `source_content_changed_at`

This keeps the current collection and swipe APIs intact while letting the UI filter to:

- GetHookd pending review
- GetHookd approved
- GetHookd stale after sync

### 4. Collections remain the launch contract

Reviewers should approve by adding assets into one or more writable collections.

Rules:

- the default collection remains read-only and auto-populated for non-GetHookd catalog assets
- the `GetHookd` collection is the read-only inbox for synced GetHookd assets
- launchable curation happens only in writable collections
- adding an asset to a writable collection marks it `approved`
- rejecting an asset marks it `rejected` but does not delete the canonical record

### 5. Campaigns own the launch default

Add `campaigns.default_swipe_collection_id`.

Launch behavior:

- if the request includes `swipeCollectionId`, use it after validation
- otherwise use `campaign.default_swipe_collection_id`
- if neither exists, return a clean `409` instructing the user to set a default
- if the resolved collection has no ready assets, return a clean `409`
- if the resolved collection is `default` or `gethookd_inbox`, return a clean `409`; launch defaults must point at curated or uploaded collections

Do not silently pick the org default collection. The user asked for an intentional launch default, not an implicit fallback.

## Nightly Workflow Spec

### Scheduler

Implement a dedicated nightly workflow for GetHookd sync.

Recommended shape:

- `GetHookdNightlySyncWorkflow`
- one scheduled run per active workspace with GetHookd enabled
- each run iterates that workspace’s enabled feeds sequentially

Use Temporal for execution and scheduling so the sync path matches the rest of the ingestion stack. This is net-new scheduling infrastructure in this repo; there is no existing GetHookd schedule implementation to reuse.

### Run steps

For each workspace run:

1. Load the workspace GetHookd credential.
2. Load enabled sync feeds.
3. For each feed, call GetHookd Explore page-by-page up to `max_pages_per_run`.
4. Normalize each result into the MOS swipe shape.
5. Upsert brand, swipe asset, and media.
6. Ensure the asset is a member of the system-managed `GetHookd` collection.
7. Queue taxonomy for any new asset or any asset whose creative content changed materially.
8. Record sync-run metrics and per-feed counts.

### Upsert rules

For each normalized GetHookd result:

1. Upsert `company_swipe_brands` by `org_id + external_brand_id`.
2. Upsert `company_swipe_assets` by `org_id + origin_system + external_ad_id`.
3. If the asset is new:
   - set `source_kind = "catalog"`
   - set `origin_system = "gethookd_public_api"`
   - set `review_status = "pending_review"`
   - mirror media through the shared `media_assets` path
   - create `company_swipe_media` compatibility rows after the final mirrored `media_asset_id` is known
   - add the asset to the `GetHookd` collection
   - set `analysis_status = "queued"`
4. If the asset already exists:
   - update mutable reference fields such as performance score, days active, used count, and source payload timestamps
   - ensure the asset remains in the `GetHookd` collection
   - if the normalized creative payload hash changed, set `review_status = "stale_after_sync"`
   - if only performance metadata changed, preserve current review status and collection membership

### Change classification

Treat these as metadata-only changes:

- `days_active`
- `used_count`
- `performance_score`
- `active_in_library`
- `end_date`
- other ranking / runtime / activity fields

Treat these as creative changes that require re-review:

- title
- body
- CTA
- landing page
- display format
- media URLs / media count / media ordering

When a creative change is detected:

- update the canonical asset row
- mirror any new remote media
- mark the asset `stale_after_sync`
- keep existing curated collection membership intact, but flag it in UI as stale

Do not silently remove the asset from launch collections. Reviewers need to make that call explicitly.

### Missing-from-feed behavior

If an asset stops appearing in nightly sync results:

- update `source_last_seen_at`
- do not delete the asset
- do not remove it from collections
- continue surfacing it until a reviewer removes it or rejects it

GetHookd Explore has no documented webhook or delta stream, so absence from the nightly feed is not strong enough evidence to delete data.

## Media Storage Decision

Downloaded GetHookd media should use the same storage system as Meta ad ingestion.

Specifically:

- do reuse `media_assets` plus `MediaMirrorService`
- do not reuse the swipe upload helper `_store_swipe_upload_media(...)` for GetHookd sync
- do not call `AdsRepository.upsert_ad_with_assets(...)` directly, because that would create unrelated `ads`, `ad_facts`, `ad_scores`, and creative memberships
- instead, extract the reusable media-only logic from the Meta ads path into a shared helper

Recommended extraction:

- `MediaAssetsRepository.upsert_remote_asset(...)`
- or `RemoteMediaAssetService.upsert_and_mirror(...)`

That shared helper should:

1. accept a normalized remote media description
2. upsert a `media_assets` row
3. mirror the remote file through `MediaMirrorService`
4. return the final canonical `MediaAsset`

This matters because `MediaMirrorService` can dedupe by SHA and replace a draft `MediaAsset` with an existing one. Swipe compatibility rows should therefore be created only after mirroring returns the final canonical `media_asset_id`.

## Review and Curation UX

### Shared component set

Do not build a GetHookd-specific browser from scratch.

The frontend should converge on a shared asset review component set built from the existing library and creative review primitives:

- reuse `LibraryItem` as the normalized preview/details view model
- reuse `MediaViewer` and `LibraryItemDetailsPanel` for preview and deep inspection
- generalize `CreativeReviewGrid` and `AdReviewCard` into asset-agnostic review components that support:
  - filters
  - multi-select
  - select-all-on-filtered-results
  - bulk actions
  - detail-panel opening

Recommended shared components:

- `AssetReviewGrid`
- `AssetReviewCard`
- `AssetReviewToolbar`
- `AssetDetailsPanel`

GetHookd review, swipe review, and Meta creative review should all use the same grid shell and selection model, with only the badges and action bar varying by context.

### Swipes page

The Swipes page should gain a review mode for the system-managed `GetHookd` collection.

Recommended filters:

- source: `GetHookd`
- review status: `Pending`, `Approved`, `Rejected`, `Stale`
- collection membership: `Not in launch collection`
- changed since: `Last sync`, `Last 7 days`

Recommended bulk actions:

- `Add to collection`
- `Reject`
- `Mark back to pending`

Recommended row metadata:

- brand
- platform
- performance score tier
- days active
- used count
- landing page / source hostname
- last synced at
- review status
- stale badge when upstream creative changed

### Collection add flow

Bulk-add should allow selecting one or more writable collections.

Behavior:

- add missing membership only
- on successful add, set `review_status = approved`
- if the asset was `stale_after_sync`, approval clears the stale flag

Do not auto-create collections during review. The user should explicitly choose the curation target.
Do not allow bulk-add into `default` or `gethookd_inbox`.

## Campaign Default Swipe Collection

### Data model

Add:

- `campaigns.default_swipe_collection_id -> swipe_collections.id`

Put this on `Campaign`, not `CampaignDeliveryConfig`. The setting controls creative source material, not delivery destination.

### API

Recommended additions:

- `GET /campaigns/{campaign_id}/swipe-default`
- `PUT /campaigns/{campaign_id}/swipe-default`

Recommended response shape:

```json
{
  "swipeCollectionId": "uuid-or-null",
  "swipeCollectionName": "Collection name or null",
  "readySwipeCount": 12
}
```

### Launch flow

Update creative production so the collection is a persisted campaign setting, not a browser-only remembered value.

Recommended behavior:

- `SwipeCollectionSelector` reads and writes the campaign default from the backend
- localStorage can remain a temporary UI convenience only if it does not override the persisted campaign default
- `POST /campaigns/{campaign_id}/creative/produce` should accept an optional explicit override
- if no override is sent, resolve the campaign default
- if no campaign default exists, error clearly
- only curated or uploaded collections should be eligible in the selector; system collections should be excluded or disabled

This aligns the launch path with the user’s stated model: a campaign has a default swipe file, and reviewed GetHookd assets are promoted into the collections that power that file.

## Continuous Update Plan

The continuous-update plan should be:

### Layer 1. Reference sync

- nightly GetHookd feed sync keeps the reference corpus fresh
- the synced row remains the canonical reference asset in MOS
- upstream performance metadata updates in place

### Layer 2. Human curation

- reviewers decide which reference assets belong in which collections
- collection membership is the durable curation decision
- stale approved assets are surfaced for explicit re-review

### Layer 3. Campaign launch default

- each campaign points at a curated collection
- campaigns do not infer a collection from workspace state or browser storage

### Layer 4. Existing publish pipeline

- creative production already accepts a swipe collection and records source collection metadata in workflow inputs and artifacts
- downstream brand QA, compliance QA, Meta review setup, and publishing stay on the existing path

This means GetHookd updates the reference corpus continuously, while MOS remains the system that decides what gets launched and published.

## Continuous Refresh Signals

To make the nightly sync operationally useful, add campaign-level refresh indicators.

Recommended derived signals:

- `newApprovedSinceLastCreativeRun`
- `staleApprovedAssetsCount`
- `pendingReviewCount`
- `approvedAssetDeltaSinceLastCreativeRun`

These do not auto-launch or auto-publish. They tell the operator that a campaign’s default source collection has changed enough to justify another creative-production run.

## Required Model and Repository Changes

### Credentials

Add a workspace-scoped credential record:

- `client_gethookd_credentials`
  - `id`
  - `org_id`
  - `client_id`
  - `credentials_encrypted`
  - `last_validated_at`
  - `last_validation_error`
  - `created_at`
  - `updated_at`
  - unique key on `org_id + client_id`

Credential payload:

```json
{
  "apiToken": "..."
}
```

Use `app.services.integration_secrets` for encryption. Never expose the raw token back to the client.

### Sync feeds

Add workspace-scoped feed configuration:

- `client_gethookd_sync_feeds`
  - `id`
  - `org_id`
  - `client_id`
  - `name`
  - `enabled`
  - `filters_json`
  - `max_pages_per_run`
  - `per_page`
  - `created_at`
  - `updated_at`

### Sync runs

Add run logging:

- `gethookd_sync_runs`
  - `id`
  - `org_id`
  - `client_id`
  - `status`
  - `started_at`
  - `finished_at`
  - `feeds_attempted`
  - `feeds_succeeded`
  - `assets_new`
  - `assets_updated`
  - `assets_marked_stale`
  - `assets_failed`
  - `credits_used`
  - `error_summary`

### System collections

Extend collection kinds with a system-managed GetHookd inbox:

- `swipe_collections.kind = "gethookd_inbox"`

Repository changes:

- update `ensure_default_collection(...)` so it excludes `origin_system = "gethookd_public_api"`
- add `ensure_gethookd_collection(...)`
- add `add_item_if_missing(...)` for single-asset system membership writes

User collection create APIs should not allow `gethookd_inbox`. That kind is system-owned only.

### Company swipe asset fields

Add fields on `company_swipe_assets`:

- `review_status`
- `reviewed_at`
- `reviewed_by_user_id`
- `source_first_seen_at`
- `source_last_seen_at`
- `source_last_synced_at`
- `source_payload_hash`
- `source_content_changed_at`
- `source_metadata_json`

Keep:

- `source_kind = "catalog"`
- `origin_system = "gethookd_public_api"`

This preserves typed queryability while still allowing the repo to route GetHookd assets into their own system collection.

### Source payload and metadata persistence

We need to store both the ad record and the metadata around the record robustly inside MOS.

Recommended persistence model:

- keep commonly queried fields in typed columns on `company_swipe_assets`
- store the full normalized GetHookd result payload in `company_swipe_assets.ad_library_object`
- store sync-specific and provider-specific metadata in `company_swipe_assets.source_metadata_json`
- store provider media metadata in `media_assets.metadata_json`

`source_metadata_json` should capture data such as:

- feed ids that surfaced the asset
- last sync run id
- raw performance tier labels
- niche / language / location returned by GetHookd
- share / embed URLs
- raw provider media descriptors
- import provenance and change-detection hashes

API models should expose enough of this for review UI without forcing the browser to reconstruct it from raw JSON only.

### Company swipe dedupe

Add a unique constraint or partial unique index for imported external ads:

- `uq_company_swipe_assets_org_origin_external_ad`
- columns: `org_id`, `origin_system`, `external_ad_id`
- apply only when `external_ad_id IS NOT NULL`

This closes the race where multiple sync workers or reruns ingest the same GetHookd ad concurrently.

### Swipe media bridge

Add a nullable foreign key on `company_swipe_media`:

- `media_asset_id -> media_assets.id`

Purpose:

- keep swipe APIs and taxonomy flows compatible with the current swipe model
- let swipes reuse mirrored binaries, preview keys, MIME metadata, and SHA-based dedupe from the Meta media system

Recommended uniqueness:

- unique key on `swipe_asset_id + media_asset_id` when `media_asset_id IS NOT NULL`

### Campaign default

Add:

- `campaigns.default_swipe_collection_id -> swipe_collections.id`

If the cross-workspace swipe collection spec lands later, this field must validate visibility against `campaign.client_id`. For now, current code is org-scoped.

## Data Mapping

| GetHookd field | Local field | Notes |
| --- | --- | --- |
| `id` | `company_swipe_assets.external_ad_id` | Store the GetHookd ad id here |
| `external_id` | `company_swipe_assets.external_platform_ad_id` | Upstream platform ad id |
| `platform` | `company_swipe_assets.platforms` | Preserve raw platform string |
| inferred from `platform` | `company_swipe_assets.channel` | `meta` in v1 because Explore docs only list `facebook` and `instagram` |
| `display_format` | `company_swipe_assets.display_format` | Preserve exact GetHookd value |
| inferred from media / format | `company_swipe_assets.ad_unit_format` | Normalize to `image`, `video`, or `carousel` |
| `title` | `company_swipe_assets.title` | direct |
| `body` | `company_swipe_assets.body` | direct |
| `landing_page` | `company_swipe_assets.landing_page` | direct |
| `cta_type` | `company_swipe_assets.cta_type` | direct |
| `cta_text` | `company_swipe_assets.cta_text` | direct |
| `start_date` | `company_swipe_assets.start_date` | direct |
| `end_date` | `company_swipe_assets.end_date` | direct |
| `days_active` | `company_swipe_assets.days_active` | direct |
| `active_in_library` | `company_swipe_assets.active_in_library` | direct |
| `used_count` | `company_swipe_assets.used_count` | direct |
| `performance_score` | `company_swipe_assets.performance_score` | numeric score |
| `performance_score_title` | `company_swipe_assets.performance_score_data` | store title plus raw score metadata |
| `share_url` | `company_swipe_assets.share_url` and `ad_source_link` | keep the source/share URL |
| `brand.external_id` | `company_swipe_brands.external_brand_id` | upsert |
| `brand.name` | `company_swipe_brands.name` | upsert |
| `brand.logo_url` | `company_swipe_brands.logo_url` | upsert |
| raw item | `company_swipe_assets.ad_library_object` | preserve the normalized GetHookd payload |
| feed / sync / provider metadata | `company_swipe_assets.source_metadata_json` | preserve non-core metadata needed for review and audit |
| normalized creative payload | `company_swipe_assets.source_payload_hash` | use for change detection |
| `media[]` | `media_assets` | canonical mirrored-media storage |
| mirrored media | `company_swipe_media` | swipe compatibility rows linked to canonical `media_assets` |

## API Surface

Recommended backend endpoints:

- `GET /clients/{client_id}/gethookd/credentials`
- `PUT /clients/{client_id}/gethookd/credentials`
- `GET /clients/{client_id}/gethookd/sync-feeds`
- `POST /clients/{client_id}/gethookd/sync-feeds`
- `PUT /clients/{client_id}/gethookd/sync-feeds/{feed_id}`
- `DELETE /clients/{client_id}/gethookd/sync-feeds/{feed_id}`
- `GET /swipes/company` extended with source/review filters
- `POST /swipes/review/approve`
- `POST /swipes/review/reject`
- `GET /campaigns/{campaign_id}/swipe-default`
- `PUT /campaigns/{campaign_id}/swipe-default`

No user-triggered `POST /swipes/gethookd/import` endpoint is needed in the primary design.

## GetHookd API Limitations That Drive This Design

| Limitation | Impact on this spec |
| --- | --- |
| GetHookd exposes Explore search, not a dedicated “top performers” endpoint | We define “top performers” as saved sync feeds built on Explore |
| Explore supports `performance_scores`, but documented sort columns are only `created_at`, `start_date`, `days_active`, and `used_count` | Nightly sync uses tier filters plus sort heuristics, not true score sorting |
| Public Explore docs only list `facebook` and `instagram` platform filters | v1 is a Meta reference-asset sync, even if our internal swipe model is broader |
| Paging is page-based and `per_page` is capped at 100 | Sync feeds need explicit page budgets |
| API access requires a Grow or Scale plan and bearer-token auth | The workspace credential must validate clearly and fail loudly when unavailable |
| Billing is per item returned and write operations also cost credits | Feeds must be bounded; a literal “sync everything nightly” crawl is not operationally sound |
| Rate limits are 5 requests/second, 300/minute, 5,000/hour per token | The workflow must throttle and process feeds predictably |
| The public docs do not show a documented single-ad detail endpoint, webhook, or delta-sync API for Explore results | Nightly sync must rescan feeds and upsert by `external_ad_id`; there is no true incremental source API |
| Inference from docs: media URLs are shown, but lifetime and downstream-hosting guarantees are not documented | Mirror media into MOS storage instead of hotlinking |
| GetHookd Performance Score is a proprietary heuristic, not first-party ROAS truth | UI copy must say “Top-performing in GetHookd,” not imply real revenue performance |

## Error Handling

Return explicit errors for:

- missing GetHookd credentials
- invalid token
- missing `explore:read` scope
- insufficient GetHookd credits
- GetHookd rate limit hit
- unsupported or unreachable media URL during mirror
- missing `SWIPE_TAXONOMY_MODEL`
- invalid or empty campaign default collection

Do not add degraded fallback behavior that skips storage, skips taxonomy, or silently launches against another collection.

## Likely Files To Touch

- `mos/backend/app/db/models.py`
- `mos/backend/app/db/repositories/swipes.py`
- `mos/backend/app/db/repositories/ads.py` or a new extracted shared media-assets repository
- `mos/backend/app/routers/swipes.py`
- `mos/backend/app/routers/clients.py`
- `mos/backend/app/routers/campaigns.py`
- `mos/backend/app/schemas/swipe_assets.py`
- `mos/backend/app/schemas/creative_production.py`
- `mos/backend/app/services/integration_secrets.py`
- `mos/backend/app/services/media_mirror.py`
- `mos/backend/app/temporal/worker.py`
- new: `mos/backend/app/services/gethookd_client.py`
- new: `mos/backend/app/temporal/workflows/gethookd_nightly_sync.py`
- new: `mos/backend/app/temporal/activities/gethookd_sync_activities.py`
- new migration for credentials, sync feeds, sync runs, system collection kind, swipe review fields, metadata JSON, media bridge, asset dedupe, and campaign default collection
- `mos/frontend/src/api/swipes.ts`
- `mos/frontend/src/api/clients.ts`
- `mos/frontend/src/api/campaigns.ts`
- `mos/frontend/src/lib/library.ts`
- `mos/frontend/src/pages/swipes/SwipesPage.tsx`
- `mos/frontend/src/components/campaigns/SwipeCollectionSelector.tsx`
- `mos/frontend/src/components/creative/CreativeReviewGrid.tsx`
- `mos/frontend/src/components/creative/AdReviewCard.tsx`
- `mos/frontend/src/components/library/LibraryCard.tsx`
- `mos/frontend/src/components/library/LibraryItemDetailsPanel.tsx`
- `mos/frontend/src/types/library.ts`
- `mos/frontend/src/types/swipes.ts`
- new: shared asset review components if we extract them from creative/library

## Rollout Plan

### Phase 1. Reference sync foundation

- add credentials, sync feeds, sync runs
- add nightly workflow
- reuse Meta media mirroring
- add swipe review fields and filters

### Phase 2. Review-to-collection flow

- add bulk approve/reject actions
- add stale-after-sync behavior
- make GetHookd review a first-class workflow on the Swipes page

### Phase 3. Campaign default and refresh signals

- persist `campaign.default_swipe_collection_id`
- remove browser-only collection memory as the primary source of truth
- surface campaign refresh indicators derived from collection deltas

This sequencing gets the reference corpus and review loop working before changing launch behavior.

## Sources

- GetHookd Public API: [https://gethookdai.crisp.help/en/article/public-api-6ihtg/](https://gethookdai.crisp.help/en/article/public-api-6ihtg/)
- GetHookd Ad Performance Score: [https://gethookdai.crisp.help/en/article/understand-the-ad-performance-score-tjajzj/](https://gethookdai.crisp.help/en/article/understand-the-ad-performance-score-tjajzj/)
