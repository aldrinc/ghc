# Cross-Workspace Swipe Collections Spec

## Decision

Implement swipe collections as a workspace-owned resource with explicit sharing.

- In current code, "workspace" maps to `client_id` / `Client`.
- Keep `company_swipe_assets` as the one canonical org-level swipe asset table.
- Do not duplicate assets when sharing a collection across workspaces.
- Add ownership and visibility to collections so workspace-scoped flows can distinguish:
  - collections owned by the current workspace
  - collections shared into the current workspace
  - the org-wide default collection
- Shared collections are read-only outside the owner workspace.
- If a consuming workspace wants to customize a shared collection, it must clone it into its own workspace first.

This is the simplest model that gives explicit cross-workspace reuse without inventing a second swipe asset system.

## Current Problem

Today swipe collections are effectively org-scoped.

- `swipe_collections` has no workspace field.
- `GET /swipes/collections` has no workspace filter.
- `SwipeCollectionSelector` stores campaign selection by `campaignId` only, not by workspace.
- `POST /campaigns/{campaign_id}/creative/produce` validates only that the collection exists in the org.

That creates four issues:

- A workspace cannot tell which collections are "mine" versus "from somewhere else".
- Cross-workspace reuse already exists implicitly, but there is no explicit share model.
- Workspace-scoped creative generation can accidentally use a collection curated for a different workspace.
- The UI has no way to communicate ownership, provenance, or editability.

## Goals

- Make cross-workspace reuse explicit and understandable.
- Preserve one canonical swipe asset record per org.
- Let a workspace share a curated or uploaded collection with one or more other workspaces.
- Keep owner edits live for shared consumers.
- Prevent consumers from mutating a collection they do not own.
- Make campaign creative generation validate collection visibility against the campaign workspace.
- Surface enough provenance in UI and workflow logs that a reviewer can see where the collection came from quickly.

## Non-Goals

- Asset-level access control on `company_swipe_assets`.
- Per-user workspace RBAC redesign.
- Auto-merging or live two-way sync between cloned collections.
- Changing the Gemini / taxonomy flow.
- Changing creative production to silently fall back to another collection when access is invalid.

This feature governs collection ownership, discovery, and generation eligibility. It does not turn swipe assets into a security-isolated workspace resource.

## Core Concepts

### 1. Owner workspace

The workspace that owns the collection.

- Stored as `owner_client_id`.
- Required for all user-created collections.
- Nullable only for the built-in org default collection and temporary legacy rows during migration.

### 2. Visibility

How a collection can be discovered outside the owner workspace.

- `workspace`
  - visible only in the owner workspace
- `selected_workspaces`
  - visible in the owner workspace and specific explicitly shared target workspaces
- `org`
  - visible in every workspace in the org

### 3. Access mode

Computed at read time for the current workspace.

- `owner`
- `shared`
- `org_default`
- `legacy_org_shared`

`access_mode` is response metadata for the UI. It is not the canonical stored field.

### 4. Default collection

Keep the current built-in default collection.

- remains org-wide
- remains read-only
- remains auto-populated from non-upload catalog swipes
- is visible in every workspace

The UI should label it as an org-wide default, not just "Default", so reviewers know it is shared by design.

## Collection Behavior Matrix

| Collection type | Owner workspace | Visible in owner | Visible in shared target | Visible in unrelated workspace | Editable in owner | Editable in consumer | Usable for generation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `default` | `null` | Yes | Yes | Yes | No | No | Yes |
| private user collection | required | Yes | No | No | Yes | No | Yes, owner only |
| selected-workspace shared | required | Yes | Yes | No | Yes | No | Yes |
| org-shared user collection | required | Yes | Yes | Yes | Yes | No | Yes |
| legacy org-shared migrated collection | `null` until assigned | Yes | Yes | Yes | Yes, temporarily | Yes, temporarily | Yes |

The `legacy org-shared` state exists only for migration safety. New collections must not be created in that state.

## User Stories

- As a workspace owner, I can create a swipe collection inside my workspace.
- As a workspace owner, I can share that collection with one or more other workspaces.
- As a consuming workspace, I can find collections shared into my workspace and use them in creative generation.
- As a consuming workspace, I can see clearly that a shared collection belongs to another workspace and is read-only for me.
- As a consuming workspace, I can clone a shared collection into my own workspace and then edit that clone.
- As a reviewer, I can see which workspace owned the collection used to generate a creative run.

## UX Spec

### Swipes Page

The swipes page becomes workspace-aware.

- If a workspace is selected:
  - show collections visible to that workspace
  - group them into:
    - `Owned by this workspace`
    - `Shared with this workspace`
    - `Org default`
- If no workspace is selected:
  - show a read-only org overview
  - disable create, upload, and share actions
  - show the inline workspace picker for any action that needs ownership context

Each collection card should display:

- collection name
- owner workspace name
- visibility badge
- access badge
- writable/read-only badge
- swipe count
- ready count

Recommended badge language:

- `Owned`
- `Shared from {workspace}`
- `Shared to {N} workspaces`
- `Org-wide`
- `Read-only`

### Create Collection Flow

Creating a collection requires an active workspace context.

Form fields:

- `name`
- `kind`
  - `uploaded`
  - `curated`
- `visibility`
  - `workspace`
  - `selected_workspaces`
  - `org`
- `shared workspace targets`
  - shown only when `visibility=selected_workspaces`

Default form behavior:

- default `visibility` to `workspace`
- do not infer or silently change the owner workspace
- require the selected workspace explicitly

Validation:

- `name` required
- `owner_client_id` required
- `default` cannot be user-created
- `shared workspace targets` must all belong to the same org
- `shared workspace targets` must not include the owner workspace

### Share Management Flow

Owner workspaces can update share settings from the collection detail or collection card menu.

Actions:

- change `visibility`
- add target workspaces
- remove target workspaces
- convert from private to org-wide
- convert from org-wide to selected workspaces
- convert from shared to private

UX rules:

- show a live summary of who currently has access
- removing access should require confirmation
- confirmation copy must state that existing workflows are unaffected, but future generation from removed workspaces will fail until another collection is selected

### Shared Collection Consumption

When a workspace is viewing a collection it does not own:

- detail page is visible if shared to that workspace
- add/remove/upload controls are hidden or disabled
- primary action is `Clone into {current workspace}`

The read-only message should be explicit:

- `This collection is owned by {owner workspace}. Clone it into {current workspace} before modifying it.`

### Campaign Creative Selection

`SwipeCollectionSelector` must become workspace-aware.

- Query collections with the campaign workspace id.
- Group options into:
  - `This workspace`
  - `Shared with this workspace`
  - `Org default`
- Include owner workspace in the option label for any non-owned collection.
- Persist the last chosen value with a workspace-aware storage key:
  - `campaign-swipe-collection:{campaignId}:{workspaceId}`

Selection rules:

- If the stored selection is still visible in the current workspace, keep it.
- If the stored selection is no longer visible in the current workspace, clear it and show an explicit message.
- Do not silently substitute another shared collection.
- The only allowed automatic initial choice is the org default collection on first load when no prior selection exists.

Error copy when access is revoked:

- `The previously selected swipe collection is not available in this workspace anymore. Choose another collection.`

### Clone Flow

Cloning remains membership-only.

- clone copies collection membership only
- clone never duplicates `company_swipe_assets`
- clone result is always owned by the target workspace
- clone result is created as `curated`
- `cloned_from_collection_id` is preserved for lineage only
- later source edits do not sync into the clone

Clone entrypoints:

- swipes page collection detail
- campaign selector dropdown for shared collections

### Search and Sorting

Search must match:

- collection name
- owner workspace name
- collection kind
- access badge text

Sort order for workspace-scoped list:

1. owned collections
2. shared collections
3. org default
4. within each group: most recently created first

## Backend Spec

### Data Model Changes

### `swipe_collections`

Add:

- `owner_client_id uuid null`
  - FK to `clients.id`
  - nullable only for default and legacy migrated rows
- `visibility text not null`
  - enum-like validated values:
    - `workspace`
    - `selected_workspaces`
    - `org`

Keep:

- `kind`
- `cloned_from_collection_id`
- `created_by_user_id`
- `created_at`

Recommended uniqueness change:

- replace unique `(org_id, name)` with:
  - unique `(org_id, owner_client_id, lower(name))` for workspace-owned collections
  - unique `(org_id, lower(name))` for org-owned rows where `owner_client_id is null`

Reason:

- two different workspaces should be able to have a collection named `Spring Winners`
- org-owned default / legacy rows still need collision protection

### New table: `swipe_collection_workspace_shares`

Fields:

- `id`
- `org_id`
- `collection_id`
- `target_client_id`
- `granted_by_user_id`
- `created_at`

Constraints:

- unique `(collection_id, target_client_id)`
- index `(org_id, target_client_id)`
- index `(org_id, collection_id)`

### No change to canonical asset storage

Do not add workspace ownership to `company_swipe_assets` in this feature.

- assets remain org-level
- collection membership remains the organizing layer
- a shared collection exposes the same asset rows to multiple workspaces

### Repository Changes

`SwipeCollectionsRepository` should gain workspace-aware list and access helpers.

Required methods:

- `list_visible(org_id, client_id, include_org_default=True)`
- `get_visible(org_id, client_id, collection_id)`
- `can_view(org_id, client_id, collection_id)`
- `can_edit(org_id, client_id, collection_id)`
- `list_share_targets(org_id, collection_id)`
- `replace_share_targets(org_id, collection_id, target_client_ids, granted_by_user_id)`

Visibility predicate:

- collection is visible when any of these are true:
  - `kind=default`
  - `owner_client_id == client_id`
  - `visibility=org`
  - `visibility=selected_workspaces` and a share row exists for `client_id`
  - `legacy row` with `owner_client_id is null`

Edit predicate:

- collection is editable when:
  - `kind in writable kinds`
  - and `owner_client_id == client_id`
- temporary migration exception:
  - legacy rows with `owner_client_id is null` remain editable until assigned

### API Changes

### 1. List collections

`GET /swipes/collections?clientId={workspace_id}&includeShared=true`

Behavior:

- if `clientId` is provided:
  - return only collections visible to that workspace
  - include computed `access_mode`
  - include owner workspace metadata
- if `clientId` is omitted:
  - return org overview
  - include all collections
  - no computed workspace-specific access mode

Response additions:

- `owner_client_id`
- `owner_client_name`
- `visibility`
- `shared_workspace_ids` optional, detail only
- `access_mode` when `clientId` is provided

### 2. Get collection detail

`GET /swipes/collections/{collection_id}?clientId={workspace_id}`

Behavior:

- if `clientId` is present, enforce workspace visibility
- if collection is not visible to that workspace, return `404`
- include share metadata and owner metadata

### 3. Create collection

`POST /swipes/collections`

Request body additions:

- `clientId`
- `visibility`
- `sharedWorkspaceIds` optional

Strict behavior:

- `clientId` required for all user-created collections
- if `visibility=selected_workspaces`, `sharedWorkspaceIds` must be non-empty
- if `visibility=workspace`, `sharedWorkspaceIds` must be empty
- do not auto-promote a private collection to org-wide because targets were omitted

### 4. Update collection metadata / sharing

Add:

- `PATCH /swipes/collections/{collection_id}`

Editable fields:

- `name`
- `visibility`
- `sharedWorkspaceIds`

Rules:

- only owner workspace can patch
- default collection cannot be patched
- if `visibility=org`, clear share rows
- if `visibility=workspace`, clear share rows
- if `visibility=selected_workspaces`, replace share rows exactly with provided list

### 5. Clone collection

`POST /swipes/collections/{collection_id}/clone`

Request body additions:

- `clientId`

Rules:

- `clientId` is the target owner workspace
- source collection must be visible to target workspace
- result is owned by `clientId`
- result defaults to `visibility=workspace`

### 6. Collection item mutation

Existing routes remain:

- `POST /swipes/collections/{collection_id}/items`
- `DELETE /swipes/collections/{collection_id}/items/{swipe_asset_id}`
- `POST /swipes/collections/{collection_id}/uploads`

New rule:

- require `clientId`
- validate edit access against owner workspace
- if caller is not in owner workspace, return `409` with explicit clone-first error

Recommended error:

- `Swipe collection is read-only in workspace {clientId}. It is owned by workspace {ownerClientId}. Clone it before modifying it.`

### Campaign Generation Rules

`POST /campaigns/{campaign_id}/creative/produce` must validate the selected collection against `campaign.client_id`.

Required behavior:

- load campaign
- resolve `campaign.client_id`
- require that the selected collection is visible to that workspace
- if not visible, fail with `404` or `409`
- do not treat org existence as sufficient

Recommended error:

- `Selected swipe collection is not available to this campaign's workspace.`

Workflow payload should add provenance fields:

- `swipe_collection_owner_client_id`
- `swipe_collection_owner_client_name`
- `swipe_collection_access_mode`

Those should be logged into `WorkflowActivityLog.payload_in` so reviewers can see whether a run used:

- a workspace-owned collection
- a shared collection
- the org default collection

### Serialization / Schema Changes

Backend schemas:

- `SwipeCollectionModel`
- `SwipeCollectionDetailModel`
- `SwipeCollectionCreateRequest`
- `SwipeCollectionCloneRequest`

Frontend types:

- `SwipeCollection`
- `SwipeCollectionDetail`
- `SwipeCollectionCreateRequest`
- `SwipeCollectionCloneRequest`

New fields:

- `owner_client_id?: string | null`
- `owner_client_name?: string | null`
- `visibility: "workspace" | "selected_workspaces" | "org"`
- `shared_workspace_ids?: string[]`
- `access_mode?: "owner" | "shared" | "org_default" | "legacy_org_shared"`

## Migration Plan

### Database Migration

1. Add `owner_client_id` and `visibility` to `swipe_collections`.
2. Backfill:
   - built-in default collection:
     - `owner_client_id = null`
     - `visibility = org`
   - existing non-default collections:
     - `owner_client_id = null`
     - `visibility = org`
3. Create `swipe_collection_workspace_shares`.
4. Replace name uniqueness with workspace-aware uniqueness.

### Legacy Handling

Existing non-default collections cannot be assigned a workspace owner automatically without inventing data.

So migration must preserve them as explicit legacy org-shared rows.

Legacy row behavior:

- visible in all workspaces
- editable temporarily
- labelled `Legacy org-wide`
- share settings disabled until an owner workspace is assigned

Add one explicit remediation action:

- `Assign owner workspace`

That action:

- requires choosing a workspace
- sets `owner_client_id`
- removes the legacy label
- keeps `visibility=org` unless the owner changes it

This avoids fabricating ownership while keeping the system operational.

### Rollout Stages

### Stage 1

- backend schema + API changes
- frontend read-only surfacing of owner / visibility / access metadata
- campaign generation validation

### Stage 2

- share management UI
- clone-from-shared flow in selector and swipes page
- legacy owner-assignment UI

### Stage 3

- optional cleanup policy to eliminate legacy org-wide editable rows after manual assignment is complete

## Telemetry

Add events:

- `swipe_collection_created`
- `swipe_collection_updated`
- `swipe_collection_shared`
- `swipe_collection_unshared`
- `swipe_collection_selected`
- `swipe_collection_cloned`
- `swipe_collection_generation_started`
- `swipe_collection_generation_rejected`

Recommended event fields:

- `collection_id`
- `collection_kind`
- `collection_visibility`
- `owner_client_id`
- `consumer_client_id`
- `access_mode`
- `shared_target_count`
- `campaign_id` when relevant

## Test Plan

### Backend

- list visible collections for owner workspace
- list visible collections for shared target workspace
- list visible collections for unrelated workspace
- create private collection with owner workspace
- create selected-workspace shared collection
- patch share targets
- reject mutation from non-owner workspace
- allow clone from visible shared collection
- reject clone from invisible collection
- validate campaign generation rejects collection not visible to campaign workspace
- preserve default collection org-wide visibility
- preserve legacy migrated collection behavior

### Frontend

- swipes page groups owned vs shared vs org default
- selector includes owner workspace labels
- selector storage key is workspace-aware
- selector clears invalid prior selection explicitly
- shared collection detail hides mutation controls
- clone CTA appears for shared read-only collection

### Migration

- old collections backfill as legacy org-wide
- uniqueness rules allow same collection name in two different workspaces
- default collection remains readable and read-only

## Acceptance Criteria

- A workspace can create a private collection and only see it inside that workspace.
- A workspace can share a collection to another workspace and that second workspace can use it for generation.
- The consuming workspace cannot upload into or edit the shared collection directly.
- The consuming workspace can clone the shared collection into its own workspace and then edit the clone.
- Campaign creative generation fails explicitly if the selected collection is not visible to the campaign workspace.
- Reviewers can identify the owner workspace of the collection used in a workflow run without reading raw IDs only.

## Implementation Map

Likely touch points:

- `mos/backend/app/db/models.py`
- `mos/backend/app/db/repositories/swipes.py`
- `mos/backend/app/schemas/swipe_assets.py`
- `mos/backend/app/routers/swipes.py`
- `mos/backend/app/routers/campaigns.py`
- `mos/backend/tests/test_swipe_collections_api.py`
- `mos/backend/tests/test_campaign_delivery_api.py`
- `mos/frontend/src/types/swipes.ts`
- `mos/frontend/src/api/swipes.ts`
- `mos/frontend/src/components/campaigns/SwipeCollectionSelector.tsx`
- `mos/frontend/src/pages/swipes/SwipesPage.tsx`

## Open Questions

- Should org-wide user-created collections remain allowed long-term, or should sharing eventually require explicit target workspaces only?
- Do we want a dedicated org-level "best of network" collection type later, or is `visibility=org` enough for v1?
- Should the swipes page eventually require a workspace selection for all write actions, even in an org overview mode?
