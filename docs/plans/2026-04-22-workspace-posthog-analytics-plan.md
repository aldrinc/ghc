# Workspace-Owned PostHog Analytics Plan

## Decision

Move PostHog funnel configuration out of environment variables and into a workspace-owned settings record that is editable from a new `Analytics` workspace page in MOS.

That workspace record becomes the only source of truth for:

- published public funnel runtime tracking
- standalone imported HTML artifact tracking
- future standalone deployments

The `Analytics` UI must support two input modes:

1. structured fields
2. a pasted PostHog snippet like the Ember example

Both input modes normalize into the same stored workspace config before anything is published or deployed.

Do not keep runtime env fallbacks after cutover.

## Why This Change Is Required

Today PostHog is wired at the wrong boundary:

- global env in [`mos/backend/app/config.py`](../../mos/backend/app/config.py)
- runtime resolution in [`mos/backend/app/services/public_runtime_tracking.py`](../../mos/backend/app/services/public_runtime_tracking.py)
- deploy artifact generation in [`mos/backend/app/services/deploy.py`](../../mos/backend/app/services/deploy.py)
- standalone export bootstrap duplicated inside [`mos/backend/cloudhand/adapters/deployer.py`](../../mos/backend/cloudhand/adapters/deployer.py)

That creates three problems:

- one server-level env controls every workspace
- PostHog host overrides are currently piggybacked through Meta metadata, which is the wrong ownership boundary
- standalone deployment behavior is easy to drift because the deployer carries its own copy of the runtime bootstrap

## Target Behavior

### Workspace behavior

- Each workspace can save its own PostHog config.
- If a workspace has no saved PostHog config, PostHog is omitted for that workspace.
- Preview mode should continue to omit PostHog so internal editing does not pollute analytics.

### Input behavior

- Structured mode accepts:
  - project API key
  - API host
  - UI host
  - defaults
  - person profiles
  - enabled/disabled
- Snippet mode accepts a pasted `posthog.init(...)` snippet, extracts the same values, shows the parsed result for review, then saves the canonical config.
- The raw snippet is preserved for audit/re-edit, but runtime always uses normalized stored fields.

### Deployment behavior

- Public funnel pages read workspace PostHog config live from the database.
- Standalone imported HTML artifacts snapshot the workspace PostHog config into the artifact payload at build time.
- Standalone deploys must not depend on `POSTHOG_FUNNELS_*` env vars being present on the destination server.

## Current Code Paths To Replace

| Area | Current path | Problem |
| --- | --- | --- |
| Global config | [`mos/backend/app/config.py`](../../mos/backend/app/config.py) | PostHog is server-global |
| Runtime resolution | [`mos/backend/app/services/public_runtime_tracking.py`](../../mos/backend/app/services/public_runtime_tracking.py) | Reads env and Meta metadata override |
| Public published pages | [`mos/backend/app/routers/public_funnels.py`](../../mos/backend/app/routers/public_funnels.py) | Inherits env-based resolver |
| Artifact build | [`mos/backend/app/services/deploy.py`](../../mos/backend/app/services/deploy.py) | Snapshots env-based tracking into artifact payload |
| Standalone deploy bridge | [`mos/backend/cloudhand/adapters/deployer.py`](../../mos/backend/cloudhand/adapters/deployer.py) | Large duplicated PostHog/bootstrap logic |
| Standalone public runtime | [`mos/frontend/src/funnels/StandaloneImportedHtmlPage.tsx`](../../mos/frontend/src/funnels/StandaloneImportedHtmlPage.tsx) | Parallel logic path that can drift |
| Shared browser helper | [`mos/frontend/src/lib/posthog.ts`](../../mos/frontend/src/lib/posthog.ts) | Already has canonical browser bootstrap pieces worth reusing |

## Implementation Plan

## 1. Add a Workspace-Owned PostHog Settings Record

Create a dedicated table instead of hiding this under Meta config or client metadata.

Recommended model: `client_posthog_settings`

Suggested fields:

- `id`
- `org_id`
- `client_id`
- `enabled`
- `project_api_key`
- `api_host`
- `ui_host`
- `defaults`
- `person_profiles`
- `source_mode` with values `structured` or `snippet`
- `source_snippet` nullable text
- `created_by_user_id`
- `created_at`
- `updated_at`

Constraints:

- unique `(org_id, client_id)`
- `api_host` and `ui_host` must be normalized HTTPS origins with no path
- `person_profiles` must be `identified_only` or `always`

Why a dedicated table:

- matches the repo’s existing workspace-scoped integration pattern better than envs
- avoids coupling analytics config to Meta ad config
- keeps the persistence model explicit and reviewable

## 2. Add Backend APIs For Read, Save, And Snippet Import

Add a dedicated router, for example:

- `GET /clients/{client_id}/analytics/posthog`
- `PUT /clients/{client_id}/analytics/posthog`
- `POST /clients/{client_id}/analytics/posthog/parse-snippet`

Recommended implementation files:

- `mos/backend/app/routers/analytics.py`
- `mos/backend/app/schemas/analytics.py`
- `mos/backend/app/db/repositories/client_posthog_settings.py`
- `mos/backend/app/services/posthog_workspace_settings.py`

Save behavior:

- save only canonical normalized fields
- reject invalid config cleanly
- do not silently fall back to env

Snippet parse behavior:

- accept optional `<script>` wrapper
- extract the first `posthog.init(apiKey, config)` call
- extract only the allowlisted config keys:
  - `api_host`
  - `ui_host`
  - `defaults`
  - `person_profiles`
- ignore comments and whitespace
- reject snippets that cannot be parsed into a complete canonical config
- do not evaluate arbitrary JavaScript

Recommendation:

- implement parsing server-side so the rules are consistent, testable, and shared by all clients
- keep the parser intentionally narrow to the PostHog init shape instead of introducing a general JS evaluator

## 3. Replace Runtime Resolution With Workspace Lookup

Refactor [`mos/backend/app/services/public_runtime_tracking.py`](../../mos/backend/app/services/public_runtime_tracking.py) so PostHog comes from the workspace record only.

Specifically:

- remove reads of:
  - `POSTHOG_FUNNELS_ENABLED`
  - `POSTHOG_FUNNELS_PROJECT_API_KEY`
  - `POSTHOG_FUNNELS_API_HOST`
  - `POSTHOG_FUNNELS_UI_HOST`
  - `POSTHOG_FUNNELS_DEFAULTS`
  - `POSTHOG_FUNNELS_PERSON_PROFILES`
- remove the `mosPosthogTracking` Meta metadata override path as an active runtime source
- add a workspace resolver keyed by `funnel.client_id`

Runtime rules:

- if workspace PostHog settings do not exist or are disabled, return `None`
- if they exist but are invalid, fail cleanly with a descriptive error
- continue returning runtime payload shape compatible with the frontend:
  - `provider: "posthog"`
  - `mode: "public_funnel_runtime"`
  - `posthogProjectApiKey`
  - `posthogApiHost`
  - `posthogUiHost`
  - `posthogDefaults`
  - `posthogPersonProfiles`

Important non-change:

- keep preview pages on `include_posthog=False` as they are today in [`mos/backend/app/routers/public_funnels.py`](../../mos/backend/app/routers/public_funnels.py)

## 4. Add the Workspace Analytics UI

Add a new workspace page and nav item:

- route: `/workspaces/execution/analytics`
- label: `Analytics`

Frontend files likely touched:

- `mos/frontend/src/App.tsx`
- `mos/frontend/src/app/routes.tsx`
- `mos/frontend/src/app/AppShell.tsx`
- `mos/frontend/src/pages/workspaces/AnalyticsPage.tsx`
- `mos/frontend/src/components/clients/PosthogAnalyticsSettings.tsx`
- `mos/frontend/src/api/clients.ts`
- `mos/frontend/src/types/common.ts`

UI sections:

1. `Status`
2. `Structured Config`
3. `Import Snippet`
4. `Resolved Runtime Preview`

Behavior:

- structured fields can be edited directly
- snippet textarea can parse and populate the structured fields
- save always persists the normalized structured payload
- show the final resolved payload exactly as runtime/deploy will consume it

Suggested UX details:

- prefill `defaults` with `2026-01-30`
- prefill `person_profiles` with `identified_only`
- allow `ui_host` to be blank
- show parsed snippet errors inline instead of silently discarding values

## 5. Keep Standalone Deployments Safe By Snapshotting Workspace Config

The existing artifact build path already snapshots tracking into page payloads in [`mos/backend/app/services/deploy.py`](../../mos/backend/app/services/deploy.py).

Keep that pattern, but change the data source:

- artifact payload must use the new workspace PostHog resolver
- standalone export must consume the already-resolved page `tracking` payload
- standalone deploy must not consult server env for PostHog at all

This preserves the right contract:

- UI saves workspace config
- artifact build snapshots workspace config
- deployer only renders the snapshot

That makes future deployments deterministic and workspace-scoped.

## 6. Remove Drift Risk In The Standalone Runtime Bridge

Current risk:

- Cloudhand embeds a very large hard-coded runtime script in Python
- the public standalone React runtime has similar PostHog/bootstrap logic in TypeScript
- changes can land in one place and be missed in the other

Hardening plan:

- move the standalone bridge script out of inline Python string ownership
- keep it in a dedicated source file or generated asset that the deployer reads/injects
- extract shared PostHog event-mapping and bootstrap helpers so both runtime paths use the same canonical logic where possible

Minimum acceptable outcome:

- Python deployer no longer owns the PostHog bootstrap as hand-maintained inline code

Preferred outcome:

- standalone bridge config is injected as JSON
- bootstrap/event logic lives in a shared asset or shared helper layer

That is the main change that protects future standalone deployments from breaking due to drift.

## 7. Migration Strategy

Cut over in one controlled migration, not with indefinite dual-read fallback.

Migration steps:

1. Add `client_posthog_settings`.
2. Backfill one row per workspace that currently depends on PostHog.
3. Source backfill values from:
   - existing global `POSTHOG_FUNNELS_*` env values
   - existing `mosPosthogTracking` metadata overrides for workspace-specific `apiHost` and `uiHost`
4. Deploy code that reads only the new table.
5. Remove `POSTHOG_FUNNELS_*` from examples and deployment docs.

Backfill rules:

- if a workspace has override metadata, use that override for host values
- use the current global env values only as one-time seed data during migration
- after migration, env is no longer authoritative

This avoids a long-lived fallback while preventing analytics from disappearing on cutover day.

## 8. Deployment And Ops Changes

Update deployment-facing docs and examples:

- remove `POSTHOG_FUNNELS_*` from [`.env.production.example`](../../.env.production.example)
- update [`docs/deployment-runbook.md`](../deployment-runbook.md) to describe workspace-owned Analytics setup instead of env setup
- leave `mos/infra/docker-compose.deploy.yml` unchanged unless any now-unused env assumptions are documented there

Operational expectation after cutover:

- adding a new workspace requires configuring Analytics in MOS, not editing server env
- future server replacements or new standalone deploy targets do not need PostHog env vars to preserve analytics behavior

## 9. Validation Plan

### Backend tests

Add/replace tests for:

- workspace PostHog settings CRUD
- snippet parsing using the Ember snippet shape
- invalid snippet rejection
- invalid host rejection
- public published funnel pages exposing workspace PostHog tracking
- deploy artifact payload including workspace PostHog tracking
- preview pages still excluding PostHog
- no dependency on `POSTHOG_FUNNELS_*` settings during runtime resolution

Files already covering adjacent behavior:

- `mos/backend/tests/test_funnels.py`
- `mos/backend/tests/test_imported_html_runtime.py`
- `mos/backend/tests/test_cloudhand_deployer_funnel_proxy.py`

### Frontend tests

Add tests for:

- Analytics page route and nav presence
- structured save flow
- snippet parse/import flow
- resolved runtime preview rendering
- inline validation and error states

### Deployment verification

Verify after rollout:

1. Save Ember workspace config from the Analytics page using structured fields.
2. Save Ember workspace config again using the pasted snippet path and confirm the parsed result matches.
3. Open a published public funnel page for Ember and confirm the returned page payload exposes the workspace PostHog config.
4. Build/deploy a standalone imported HTML funnel for Ember and confirm the exported HTML contains the resolved PostHog bootstrap without any env dependency.
5. Remove `POSTHOG_FUNNELS_*` from the deployment env and confirm future deploys still work.

## Recommended Delivery Order

1. Schema + repository + service
2. Snippet parser + validation tests
3. Runtime resolver cutover
4. Artifact/deployer cutover
5. Analytics UI
6. Backfill migration
7. Docs/env cleanup
8. End-to-end validation on Ember

## Main Risks

### Risk: stale standalone deploy logic

If the deployer keeps owning its own inline PostHog/runtime bootstrap, this work will regress later.

Mitigation:

- centralize the standalone bridge source

### Risk: migration misses a workspace

If a workspace currently relies on env-only config and is not backfilled, PostHog disappears after cutover.

Mitigation:

- backfill all workspaces with published funnels or active funnel artifacts
- add a one-time audit query/report during rollout

### Risk: snippet parser is too permissive

If the parser attempts to support arbitrary JavaScript shapes, it becomes fragile and hard to trust.

Mitigation:

- support only `posthog.init(...)` extraction with allowlisted keys
- reject anything outside the supported shape with a clear error

## Final Recommendation

Implement this as a clean ownership shift:

- workspace owns PostHog config
- Analytics page manages it
- runtime resolves it from the database
- artifact build snapshots it
- standalone deploy consumes the snapshot
- env-based PostHog control is removed

That gives MOS the boundary you want and prevents future standalone deployments from breaking because of server-level env coupling.
