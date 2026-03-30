# Postiz Into MOS Scope

## Decision

Integrate Postiz as a self-hosted outbound publishing sidecar, and let Postiz handle scheduling.

- MOS should own workspace mapping, approvals, content assembly, and publishing history.
- Postiz should own channel OAuth, platform-specific validation, media ingestion, scheduled execution, and actual post delivery.
- V1 should use only Postiz's documented public API surface.
- V1 should support direct publish and one-time scheduled publish through Postiz.
- V1 should not add MOS Temporal workflows or a MOS-owned recurring scheduler.
- V1 should not depend on Postiz's internal `/autopost` or `/webhooks` APIs.

## Why This Boundary

### MOS already has the right control-plane patterns

- Workspace-scoped credentials and config already exist in MOS for external systems.
- MOS is already the system of record for campaign intent, approvals, and generated content.

Relevant local references:

- `mos/backend/app/routers/gethookd.py`
- `mos/backend/app/services/integration_secrets.py`
- `mos/frontend/src/components/clients/GetHookdSettings.tsx`
- `mos/frontend/src/pages/campaigns/tabs/CampaignPublishTab.tsx`

### Postiz already solves the expensive part

Upstream Postiz currently provides:

- self-hosted deployment
- public API with API key or OAuth auth
- channel connection via OAuth URL generation
- media upload endpoints
- create/list/delete posts
- scheduled posting through `POST /public/v1/posts`
- platform-specific integration settings and helper tools
- MCP and SDK/CLI surfaces

Relevant upstream references:

- https://github.com/gitroomhq/postiz-app
- https://docs.postiz.com/public-api/introduction
- https://docs.postiz.com/public-api/oauth
- https://docs.postiz.com/installation/docker-compose

### Simpler than duplicating scheduling inside MOS

Adding MOS Temporal would create a second scheduler even though Postiz already executes scheduled posts.

So the right split is:

- MOS decides what to post and whether it should go out now or at a specific time.
- Postiz stores and executes the scheduled post.

Postiz does have an internal `autopost` feature, but the exposed controller is UI-authenticated and RSS-oriented, not public API-first. That makes it the wrong dependency for V1 recurring cadence.

## Recommended V1 Shape

### 1. Deployment

Add Postiz as a separately deployed service alongside MOS and keep its runtime isolated.

- keep Postiz app state separate from MOS app state
- use a dedicated Postgres database for Postiz
- use a dedicated Redis for Postiz
- follow Postiz's default self-hosted runtime requirements as-is
- do not couple MOS runtime to Postiz's internal orchestration stack in V1

This keeps operational ownership clear and avoids cross-wiring MOS into Postiz internals.

### 2. MOS Data Model

V1 should stay workspace-scoped, similar to GetHookd and Medusa, not org-wide like Meta.

Recommended tables:

- `client_postiz_credentials`
  - `org_id`, `client_id`
  - `base_url`
  - `auth_type` (`api_key` first, `oauth_token` later if needed)
  - `credentials_encrypted`
  - `last_validated_at`
  - `last_validation_error`
- `client_postiz_channels`
  - `org_id`, `client_id`
  - `integration_id`
  - `identifier`
  - `name`
  - `profile`
  - `picture_url`
  - `disabled`
  - `is_default`
  - `metadata_json`
- `client_postiz_posting_profiles`
  - reusable defaults such as timezone, short-link behavior, default channel set, approval mode, UTM/link settings
- `postiz_publications`
  - local content reference
  - posting profile id
  - target channel ids snapshot
  - Postiz post id
  - publish mode (`now` or `schedule`)
  - scheduled-for timestamp
  - returned payload snapshot
  - last known status
  - release URLs
  - error payload
  - last synced at

## Public API Contract MOS Should Use

V1 should stay on documented Postiz endpoints:

- `GET /public/v1/is-connected`
- `GET /public/v1/integrations`
- `GET /public/v1/social/{integration}`
- `GET /public/v1/integration-settings/{id}`
- `POST /public/v1/integration-trigger/{id}`
- `POST /public/v1/upload`
- `POST /public/v1/upload-from-url`
- `POST /public/v1/posts`
- `GET /public/v1/posts`
- `DELETE /public/v1/posts/{id}`

Important upstream constraints:

- public API rate limit is `30 requests/hour`
- create-post supports `draft`, `schedule`, and `now`
- media should be uploaded into Postiz first rather than posting arbitrary external URLs
- `GET /social/{integration}` returns an OAuth URL, but callback completion still lives inside Postiz
- `GET /posts` returns enough state for reconciliation (`QUEUE`, `PUBLISHED`, `ERROR`, `DRAFT`) plus `releaseURL`
- documented public API does not expose a recurring/autopost contract MOS should rely on in V1

## MOS API Additions

Recommended V1 routes:

- `GET /clients/{client_id}/postiz/credentials`
- `PUT /clients/{client_id}/postiz/credentials`
- `POST /clients/{client_id}/postiz/validate`
- `POST /clients/{client_id}/postiz/channels/sync`
- `GET /clients/{client_id}/postiz/channels`
- `POST /clients/{client_id}/postiz/connect-url`
- `GET /clients/{client_id}/postiz/posting-profiles`
- `POST /clients/{client_id}/postiz/posting-profiles`
- `PUT /clients/{client_id}/postiz/posting-profiles/{profile_id}`
- `GET /clients/{client_id}/postiz/posts`
- `POST /clients/{client_id}/postiz/posts`
- `DELETE /clients/{client_id}/postiz/posts/{post_id}`
- `POST /clients/{client_id}/postiz/posts/{post_id}/sync`

## Workflow Design

### Direct publish

1. MOS loads an approved content object.
2. MOS uploads media to Postiz if media is present.
3. MOS resolves the selected Postiz channel ids.
4. MOS calls `POST /public/v1/posts` with `type = "now"`.
5. MOS stores returned Postiz `postId` values.
6. MOS refreshes status from `GET /public/v1/posts` on demand or during lightweight sync.

### Scheduled publish

1. MOS loads an approved content object.
2. MOS uploads media to Postiz if media is present.
3. MOS resolves the selected Postiz channel ids.
4. MOS calls `POST /public/v1/posts` with `type = "schedule"` and a scheduled timestamp.
5. MOS stores returned Postiz `postId` values and the scheduled timestamp.
6. MOS exposes list, cancel, and sync actions against the Postiz post record.

### What V1 does not do

- MOS does not own recurring execution for Postiz publishing.
- MOS does not run Temporal workflows for Postiz publishing.
- MOS does not depend on Postiz private autopost or webhook APIs.

## UI Recommendation

Do not force this into the existing ad-platform publish registry in V1.

Current frontend publish abstractions are ad-platform specific:

- `AdPlatformId = "meta" | "tiktok" | "bing" | "google_ads"`
- the current publish tab is explicitly framed as paid-ad platform publishing

Organic social posting is a different product surface. V1 should live in workspace/client setup and then fan into campaign usage later.

Recommended V1 UI:

- add a `Postiz` tab on the workspace/client detail page beside `GetHookd`
- include:
  - credentials card
  - validate connection action
  - channel sync action
  - channel selection/defaults
  - posting profiles
  - direct publish / schedule publish actions
  - recent publication history
- add a lightweight "Publish to social now" panel later in campaign detail once workspace setup is stable

## Recommended Phasing

### Phase 1. Connectivity

- deploy Postiz service
- add workspace credentials storage
- validate API connectivity
- sync and persist channels

Size: small

### Phase 2. Manual posting

- add media upload bridge
- add create-post MOS route for `now`
- add publication tracking
- add minimal workspace UI

Size: medium

### Phase 3. Scheduled posting

- extend create-post flow for `schedule`
- add list/cancel/sync flows for scheduled posts
- add posting profiles and defaults

Size: medium

### Phase 4. Reporting and polish

- map Postiz post state and release URL into MOS history
- surface post analytics where useful
- add approval and guardrail refinements

Size: small

## Risks

- Postiz public API rate limits are low enough that MOS must batch work and avoid chatty polling.
- Channel connection is OAuth redirect based, so MOS needs a clean "open Postiz auth flow, then resync channels" UX.
- Some Postiz integrations require provider-specific helper lookups before posting; MOS cannot hardcode one generic payload shape.
- A shared Postiz API key across unrelated client workspaces would create a messy channel namespace. V1 should avoid that by keeping credentials workspace-scoped.
- Documented public API does not expose a recurring/autopost contract, so true ongoing cadence is not a V1 promise.
- Depending on Postiz internal APIs for autopost or webhook setup would create unnecessary upgrade risk.

## Open Questions

- Do we want one Postiz org/API key per MOS workspace, or do we intentionally want some workspaces to share the same Postiz org?
- Is one-time scheduled publishing enough for first release, or do we need true recurring cadence immediately?
- If true recurring cadence is required, are we willing to depend on Postiz private `autopost` behavior?
- Does scheduled posting require per-post approval, or only profile-level approval?
- Do we want release URL and analytics sync in V1, or is "submission accepted by Postiz" enough for first release?

## Recommendation Summary

Build this as a MOS-owned configuration and history layer that calls Postiz's public API for direct and scheduled posts.

That gives us:

- fast path to direct social posting without rebuilding provider integrations
- clean separation between MOS content/control and Postiz delivery mechanics
- no duplicated scheduler in MOS
- a credible V1 that can grow later without locking MOS to Postiz private endpoints too early
