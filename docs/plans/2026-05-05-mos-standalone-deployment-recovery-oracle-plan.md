# Deployment Recovery and Remediation Plan for the mOS / Cloudhand Standalone Funnel Deployment System

Generated via Oracle 0.11.0 using GPT 5.5 Pro with extended browser thinking on May 5, 2026. Source context was curated and sanitized before upload.

## Part 1 — Executive decision, system map, evidence timeline, critical failure modes, and module analysis through backend deploy/public funnel routes

## 1. Executive decision and core thesis

### Executive decision

Freeze production-like standalone funnel mutation until the deployment system can produce a verifiable, reproducible artifact from a clean repository state through the normal `main -> GitHub -> CI/CD` path. Do not deploy, restart production services, mutate live nginx configs, patch live HTML, purge production CDN, or alter production database records without an explicit human authorization gate in the current operational thread.

The immediate recovery direction should be:

1. Preserve evidence first: current git states, running service env contracts, nginx configs, symlink targets, release directory metadata, artifact payload IDs, deploy job files, journal excerpts, and database row identity for the affected Tenor funnel.
2. Stop adding new direct patches to the artifact host or bridge host.
3. Reconcile code and runtime identity before touching production: product slug, funnel slug/token, publication ID, page ID, page stage, route maps, and `funnel_events` foreign keys must agree across database snapshots, generated artifact payloads, static HTML bridge config, and public event ingestion.
4. Move all durable fixes into repository code and migrations, with tests and CI validation.
5. Only after review, ship through the normal production release path.

This decision is based on repository evidence that the project already defines a CI/CD path, deploy workflow, and post-push verification process, while also documenting known deploy gaps: no deploy queue/lock, sensitive plan files under deploy state, incomplete Terraform generation, deploy RBAC not scoped to operators, and routing sensitivity to `CLOUDHAND_NGINX_MODE`.

### Core thesis

The current failure pattern is not a single “bad bundle” problem. It is a control-plane integrity problem at the boundary between MOS database publication state, generated standalone artifact payloads, Cloudhand materialization, nginx release activation, and runtime analytics ingestion.

Evidence points to at least four overlapping failure classes:

* **Release-state drift:** production-like directories and artifact-host deployments appear to have accumulated manual backups, hotfix scripts, patch files, tarballs, and multiple active `brand-funnels-*` deployments. That weakens the ability to identify the source commit and artifact payload that produced the current public behavior.
* **Runtime identity mismatch:** journal evidence shows standalone runtime events trying to insert into `funnel_events` with a `page_id` that violates `funnel_events_page_id_fkey`, meaning the runtime event payload referenced a page ID not valid for the database-side relational constraint at ingestion time.
* **Standalone bridge drift:** existing docs already identify the standalone deployer as risky because it carries its own runtime bootstrap while the public standalone React runtime has parallel logic. The documented target is to snapshot workspace config into artifact payloads and make deployer consume the snapshot rather than server env/runtime state.
* **Insufficient deployment serialization and authorization:** the README explicitly records no deploy queue/lock and notes that any authenticated org member can call deploy routes because RBAC is not yet scoped to admin/operator roles. That means concurrent applies and accidental deploy-plan mutation are credible hazards.

### Non-goals and hard boundaries

* Do not recommend changing any LLM or AI model.
* Do not ask for, reproduce, inspect, or print secret material. The excluded raw script with hard-coded auth/JWT material should be treated as evidence of secret-handling risk, not as something to recover or reuse.
* Do not mutate live services without explicit authorization.
* Do not treat local generated deploy-plan omissions as proof the real artifact lacked omitted data; the context says omitted HTML/base64 was compacted/redacted for security and signal.
* Do not silently fall back from failed validation. Prefer hard errors with actionable diagnostics.

---

## 2. Current system map

This map separates evidence from inference. Items labeled **evidence** are directly present in attached repository files or sanitized operational context. Items labeled **inference** are derived from how the referenced components interact.

### 2.1 Local repository and source of truth

**Evidence:** The repository contains a MOS monorepo with backend, frontend, Shopify bridge integration, Cloudhand deploy engine embedded under `mos/backend/cloudhand/`, deployment runbooks, GitHub workflows, Alembic migrations, frontend runtime tests, and standalone deploy plans. The README says Cloudhand deploy routes are mounted in `mos/backend/app/routers/deploy.py`, workload patching is implemented in `mos/backend/app/services/deploy.py`, and Terraform apply is triggered by `python -m cloudhand.cli ... apply ...`.

**Evidence:** The documented local runbook expects real backend, frontend, and Shopify env files and emphasizes Clerk JWT auth with org context, backend DB migrations, Temporal worker, and smoke tests.

**Operational meaning:** The repository must be the authoritative control-plane source. Local or remote patch scripts can be used only as evidence or one-time emergency actions behind an authorization gate; they should not become the release mechanism.

### 2.2 Bridge host services

**Evidence:** The deployment runbook describes backend API, Temporal worker, frontend build, Shopify bridge integration, and production compose expectations. It states the backend and worker share env/secrets, migrations live under `mos/backend/alembic`, and the Shopify bridge requires `SHOPIFY_APP_BASE_URL` plus `SHOPIFY_INTERNAL_API_TOKEN`.

**Evidence:** Sanitized operational context shows journal failures from a bridge-host-like service: `funnel_events_page_id_fkey` violations, expired JWT verification failures, SQL/Unicode save errors, and Temporal workflow duration conversion errors were explicitly listed by the user and partially visible in journal snippets. The foreign-key violation is directly visible in the attached bundle.

**Inference:** The bridge host is acting as a control plane and API surface for public runtime event ingestion, publish/deploy orchestration, and Shopify checkout bridging. It is also a path for SSH-based deployment actions toward the artifact host in at least one hotfix workflow. The `.github/workflows/tenor-tracking-hotfix.yml` excerpt shows a GitHub Action SSHing to a deploy host and then onward to an artifact host to patch live artifact files.

### 2.3 Artifact/static host

**Evidence:** The sanitized artifact summary shows enabled nginx brand funnel sites, high-port listeners, roots under `/opt/apps/brand-funnels-.../site`, upstream API proxying to the MOS API, and root redirects to sales-page URLs for current standalone deployments. One listed site listens on a high port and redirects `/` to a sales page.

**Evidence:** The artifact host context shows many Tenor-related tarballs and generated/patch artifacts in root temp deployment storage, including large Tenor standalone bundles and multiple named repair artifacts.

**Inference:** The artifact host is not merely a dumb static host. It contains active nginx configs, release symlinks, generated release directories, cached runtime assets, mirrored static assets, and deployment scratch files. That makes it part of the operational state that must be captured before remediation.

### 2.4 nginx

**Evidence:** Cloudhand’s standalone deployer generates nginx configs for funnel artifacts. The code excerpt in `mos/backend/cloudhand/adapters/deployer.py` shows generated `server` blocks with static asset `try_files`, `/api/` proxying to the upstream API base, a `location = /` root redirect for standalone imported HTML when a default route exists, and final `nginx -t` plus `systemctl reload nginx`.

**Evidence:** The artifact summary shows current nginx configs for active brand funnel sites, including high-port `listen`, `server_name _`, static roots, `proxy_pass` to `api.moshq.app`, and `return 302` root redirects to sales pages.

**Inference:** Root redirect to a sales page can be intentional in the current deployer because `_resolve_funnel_artifact_default_page_slug` prefers `sales-page` or `sales` when available. It is not automatically evidence of corruption. But for quiz/pre-sales recovery it is operationally important because the requested Tenor quiz route must not be shadowed by a root default that hides route-map errors. The deployer’s preference for sales-page default routing is visible in `_resolve_funnel_artifact_default_page_slug`.

### 2.5 Standalone artifacts

**Evidence:** `mos/backend/app/services/deploy.py` builds client funnel runtime artifact payloads from active publication snapshots. It embeds product slug, funnel ID, funnel route slug, publication ID, page ID, slug, stage, `puckData`, `pageMap`, `pageStageMap`, design tokens, metadata, tracking, `nextPageId`, and commerce variants.

**Evidence:** The deployer validates standalone output by checking that the default route exists, the imported HTML bridge marker is present, unresolved placeholders are absent, PostHog bootstrap is present when tracking declares PostHog, and Meta Pixel bootstrap is present when tracking declares Meta.

**Inference:** The artifact is a serialized database/runtime snapshot. If database IDs, page IDs, publication IDs, slug maps, or stage maps are wrong at artifact-build time, the static deployment will faithfully publish the wrong identity. Conversely, if the artifact is correct but the database rows are later deleted or republished with different IDs, public event ingestion can fail.

### 2.6 Public funnel runtime

**Evidence:** Public runtime route components fetch meta, page, and commerce data when not in bundle mode. In standalone bundle mode, `PublicFunnelPage.tsx` can use preloaded funnel data from `window.__MOS_DEPLOY_RUNTIME__`, emits page-view events, handles pre-sales attribution, sends Meta Pixel events, PostHog captures, and `POST /public/events` payloads containing `eventType`, `publicationId`, `pageId`, visitor/session IDs, path, referrer, UTM, and props.

**Evidence:** `PublicFunnelRootRedirectPage.tsx` uses a standalone default route from runtime config and navigates to product/funnel/page path.

**Inference:** Runtime correctness depends on exact agreement between static route files, preloaded runtime config, page maps, page-stage maps, and database-side publication/page rows.

### 2.7 Analytics ingestion and `funnel_events`

**Evidence:** `PublicEventIn` accepts `eventId`, `eventType`, `occurredAt`, `publicationId`, `pageId`, visitor/session IDs, path, referrer, `utm`, and `props`.

**Evidence:** Migration `0089_rmbc_funnel_event_ids_and_types.py` adds an `event_id` column to `funnel_events` and a unique partial index on non-null `event_id`, improving idempotency.

**Evidence:** Migration `0090_quiz_funnel_event_types.py` adds quiz-specific event types, and `0091_checkout_redirect_timing_event_types.py` adds checkout timing event types.

**Evidence:** Journal evidence shows `funnel_events_page_id_fkey` violations for standalone runtime analytics events, including a `web_vital_recorded` event containing a `publication_id`, `page_id`, product path, slug, and `artifactMode: standalone_html`.

**Inference:** Event enum coverage may have improved, but referential integrity still fails when artifact-side `pageId` values do not exist in the DB table referenced by the foreign key at ingestion time.

### 2.8 PostHog and Meta

**Evidence:** The workspace PostHog plan states that PostHog was previously wired at the wrong boundary: global env, runtime resolver, deploy artifact generation, and duplicated standalone deploy bootstrap. It prescribes workspace-owned `client_posthog_settings`, runtime DB lookup, artifact snapshotting, and no runtime env fallback after cutover.

**Evidence:** Frontend `metaFunnelEvents.ts` maps `presell_page_view` to Meta custom `EnteredPresales`, `sales_page_view` to `PageView` and `EnteredSales`, `pre_sales_to_sales_click` to `PreSalesToSalesClick`, and `sales_to_checkout_click` to `SalesToCheckoutClick`.

**Evidence:** `posthog.ts` initializes a named `mosFunnel` PostHog instance from runtime tracking config and maps internal events to PostHog captures, including Meta-compatible event IDs.

**Inference:** PostHog/Meta are not the primary cause of the foreign-key violation; they are downstream/proxy tracking systems. The primary data-integrity boundary is MOS `funnel_events`.

### 2.9 Shopify checkout

**Evidence:** The deployment runbook states that Shopify connection/product mapping/checkout requires `SHOPIFY_APP_BASE_URL` and `SHOPIFY_INTERNAL_API_TOKEN`, and recommends a local bridge listener for colocated production installs.

**Evidence:** `shopify_checkout.py` validates Shopify variant GIDs and optional selling-plan GIDs, serializes checkout metadata into attributes, calls the Shopify bridge `/v1/checkouts`, handles timeout/request errors, and requires `checkoutUrl` plus `cartId` in the response.

**Inference:** Bundle/variant failures should be diagnosed at the boundary between artifact commerce payload, frontend variant resolver, prepared checkout/cache path, Shopify bridge configuration, and product variant rows. This is not covered deeply in Part 1 because the requested cutoff is backend deploy/public routes; it belongs in Part 2.

### 2.10 CI/CD

**Evidence:** `.github/workflows/docker-images.yml` runs backend tests with Postgres, applies Alembic migrations, runs `pytest`, builds the frontend, builds backend/frontend images, and has a manual `workflow_dispatch` deploy job. That deploy job SSHes to a host, pulls images, runs compose, applies migrations, restarts backend/worker, installs nginx config, tests nginx, reloads nginx, and verifies SPA deep links.

**Evidence:** The deployment runbook states the automatic production path is `Self Deploy` after a green `CI/CD` run on `main`, gated by `ENABLE_PRODUCTION_CD=true`, and post-push verification uses `scripts/check_github_actions.py --sha HEAD --wait --expect-production`.

**Decision implication:** The normal repo-controlled path exists. Direct production mutation should be treated as exceptional and reversible only under an explicit gate.

---

## 3. Evidence timeline for the Tenor quiz funnel and bundle failures

This timeline lists what the evidence shows, not what it proves.

### April 22, 2026 — Workspace-owned PostHog plan identified drift risk

**Evidence:** The workspace PostHog plan says PostHog should move out of env and into a workspace-owned settings record, and explicitly calls out that standalone deployment behavior can drift because `mos/backend/cloudhand/adapters/deployer.py` carries its own copy of runtime bootstrap while the public standalone React runtime has similar logic.

**Inference:** By April 22, the team had already identified the architectural class of drift that can break standalone deployments: duplicated runtime bootstrap logic and environment-driven tracking resolution.

### April 28–30, 2026 — Large Tenor artifact activity accumulated

**Evidence:** The root temp deployment artifacts summary includes multiple Tenor tarballs across April 28–30, including Tenor daily-drive standalone and multiple feelagain builds with sizes in the tens to hundreds of megabytes.

**Inference:** A high volume of manual or semi-manual Tenor artifact packaging occurred before the May 5 quiz work. This increases the chance that live state came from a one-off package rather than a clean CI-produced artifact.

### April 29–30, 2026 — Tenor direct repair scripts and backups appear

**Evidence:** The root temp summary includes scripts and backups such as `patch_remote_deployer_prepared_checkout.py`, `patch_tenor_deployer_runtime.py`, `republish_tenor_9fb75e73_standalone.py`, backups of service files, and Tenor publish-result files.

**Inference:** The current Tenor standalone deployment likely had multiple direct intervention rounds. Each round may have solved an immediate symptom while making provenance harder.

### May 2, 2026 — RMBC event IDs and idempotency added

**Evidence:** Migration `0089_rmbc_funnel_event_ids_and_types.py` adds RMBC-related event types and a unique partial index on `funnel_events.event_id`.

**Inference:** The team was hardening analytics idempotency and event taxonomy shortly before the May 5 Tenor quiz plan. That aligns with observed analytics concerns.

### May 5, 2026 09:00 — Quiz event types added

**Evidence:** Migration `0090_quiz_funnel_event_types.py` adds `quiz_lead_viewed`, `quiz_question_viewed`, `quiz_option_presented`, `quiz_option_selected`, `quiz_option_deselected`, `quiz_question_submitted`, `quiz_completed`, `quiz_result_viewed`, `quiz_mechanism_viewed`, `quiz_proof_viewed`, `quiz_recommendation_viewed`, and `quiz_cta_viewed`.

**Inference:** The repository had already moved from “quiz events not first-class” toward a schema-supported quiz event contract.

### May 5, 2026 — Tenor quiz plan defines required production architecture

**Evidence:** The Tenor quiz deploy plan says the quiz should deploy as a MOS-managed standalone pre-sales page on `shoptenorco.com`, not as a raw Mengotomars Shopify capture. It says to remove Mars Shopify pixels/scripts, Mars canonical/base URLs, and Heyflow, replace them with a first-party quiz runtime, and always hand off to the Tenor sales page.

**Evidence:** The plan says the preferred quiz route is same-origin under `/8b89a76d/daily-drive-essentials/quiz-v6/`, because same-origin preserves session storage attribution into the sales page.

**Inference:** Any deployment that left Heyflow/Mars artifacts, wrong canonical URLs, wrong Shopify scripts, or cross-origin handoff unaccounted for would be inconsistent with the stated production architecture.

### May 5, 2026 15:30 — Checkout redirect timing event types added

**Evidence:** Migration `0091_checkout_redirect_timing_event_types.py` adds `checkout_click`, `checkout_redirect_started`, `checkout_pagehide`, and `checkout_visibility_hidden`.

**Inference:** Checkout transition timing was actively being instrumented, likely due to observed checkout/bundle transition issues. The migration itself does not prove a checkout bug; it proves repository support was added.

### May 5, 2026 22:45 — Standalone runtime analytics failed at DB foreign key

**Evidence:** Journal excerpt shows an insert/update on `funnel_events` violating `funnel_events_page_id_fkey`. The payload included `publication_id`, `page_id`, `event_type: web_vital_recorded`, a public Tenor-like path, slug, pageStage `pre_sales`, and `artifactMode: standalone_html`.

**Inference:** A standalone artifact emitted events using a page ID that the backend database did not accept for the `funnel_events.page_id` foreign key. Likely causes include stale artifact page IDs, republished pages with new IDs, synthetic/generated page IDs, wrong database, wrong org/client/funnel resolution, or ingestion code requiring base `funnel_pages` rows while artifact points at publication-only or generated identifiers.

### May 5, 2026 22:55 — JWT failures also present

**Evidence:** Journal snippet shows repeated `ExpiredSignatureError: Signature has expired` and token verification failed messages.

**Inference:** Auth noise was present around the same operational window. It is not a primary cause of public standalone event ingestion failure unless deploy/publish actions or operator calls depended on expired tokens.

### May 5, 2026 23:01 — Artifact-host state captured

**Evidence:** Artifact summary was collected at `2026-05-05T23:01:47Z` and shows enabled brand-funnel nginx sites, high-port listeners, static roots, API proxying, root redirects, and no entries in remote journal warnings.

**Inference:** The artifact host had current standalone configs active after the analytics failures. The nginx summary alone cannot prove which artifact build caused the event mismatch; the symlink targets and file contents must be tied back to artifact metadata.

---

## 4. Critical failure modes, ranked by severity and reversibility

### Severity 1 — Public runtime emits database-invalid page IDs

**Evidence:** `funnel_events_page_id_fkey` violations occurred for standalone runtime analytics events.

**Impact:** High. Analytics ingestion fails. If request errors are unhandled, public event POSTs may become noisy server errors. Depending on transaction handling, other events in a batch may be lost.

**Reversibility:** Medium. Existing bad events may not be persisted, so there may be data gaps. The code/data mismatch is fixable, but lost client-side events may not be recoverable unless mirrored elsewhere.

**Suspected causes:** Stale artifact payload, wrong page ID generation, publication/page snapshot mismatch, direct artifact patching after republish, database cleanup that removed referenced page rows, or ingestion code that lacks a publication-page identity resolver.

### Severity 2 — Dirty production-like checkouts and direct patch artifacts obscure provenance

**Evidence:** The operational context says production-like app checkouts are dirty with detached heads and backup/patch files. The root temp summary shows numerous Tenor patch scripts, backups, generated HTML files, SSH keys, and tarballs.

**Impact:** High. Operators cannot reliably answer “what code produced current behavior?” That blocks safe rollback and makes every fix riskier.

**Reversibility:** Medium. You can capture and quarantine state, then rebuild from clean `main`, but reconstructing exact prior changes may be incomplete.

**Suspected causes:** Emergency hotfixes, missing deploy lock, missing production artifact manifest, insufficient separation between deploy scratch and runtime state.

### Severity 3 — Standalone runtime bootstrap drift between Python deployer and frontend runtime

**Evidence:** The workspace PostHog plan explicitly identifies duplicated bootstrap logic in `mos/backend/cloudhand/adapters/deployer.py` and `mos/frontend/src/funnels/StandaloneImportedHtmlPage.tsx` as a risk.

**Impact:** High. Analytics, checkout, page navigation, PostHog, and Meta behavior can differ between public runtime and standalone exported HTML.

**Reversibility:** Medium. Fixing requires refactor and tests, but no production data mutation is required.

**Suspected causes:** Large inline Python runtime script ownership, repeated hotfixes in one path without mirrored changes in the other.

### Severity 4 — Deploy apply race and shared plan/state artifacts

**Evidence:** README known gaps state no deploy queue/lock exists and concurrent applies can race against shared plan/state artifacts.

**Impact:** High. Concurrent deploys can overwrite shared plan files, materialize partial artifacts, or activate a symlink from the wrong build.

**Reversibility:** Medium to low. Wrong activated static release can be rolled back if prior release directories are intact; overwritten deploy state may not be easily reconstructed.

### Severity 5 — Deploy API exposed to any authenticated org member

**Evidence:** README known gaps state deploy RBAC is not scoped to admin/operator roles and any authenticated org member can call deploy routes.

**Impact:** High. Accidental or unauthorized deploy plan mutation becomes possible through the app surface.

**Reversibility:** Medium. Access control is fixable; untracked mutation already performed may not be fully attributable.

### Severity 6 — Root redirect default can hide entry-page or stage mistakes

**Evidence:** Deployer code chooses `sales-page` or `sales` as default page slug when available, and generated nginx can redirect `/` to that default route.

**Impact:** Medium. A sales-page root redirect may be intended, but for pre-sales quiz deployments it can mask whether the intended quiz/pre-sales entry is reachable and correctly staged.

**Reversibility:** High. Adjusting default route logic or deploy config is straightforward if done in code and validated.

### Severity 7 — Plan files and scratch artifacts may contain sensitive data

**Evidence:** README warns plan files can contain sensitive env values and are stored under `DEPLOY_ROOT_DIR`; root tmp includes keys and many artifacts in deployment scratch.

**Impact:** High for security. This is separate from runtime failure but affects incident handling.

**Reversibility:** Medium. Rotate exposed credentials if any secret was present in unapproved locations; scrub artifacts; enforce permissions.

---

## 5. Module-by-module analysis through backend deploy/public funnel routes

## 5.1 Git, branch, and release discipline; dirty production checkouts

### Current evidence

* The sanitized operational context says production-like app checkouts on the bridge host are dirty, with detached heads in several service directories and numerous backup/patch files.
* The root temp summary shows many manual-looking Tenor artifacts and patch scripts, including direct deployer/runtime patches, republish scripts, backups, generated HTML captures, and SSH key files.
* A hotfix workflow exists specifically to patch Tenor artifact tracking by SSHing to a deploy host and then to the artifact host, with Python modifying files under `/opt/apps`.
* The deployment runbook and CI/CD workflow already define a repository-driven path, including image builds, migrations, compose deploy, nginx config installation, and post-deploy verification.

### Suspected causes

**Inference:** The system has been operated through at least two release modes:

1. Normal repository/CI/CD path.
2. Direct operational patching of live or production-like hosts.

The second mode likely arose from urgency around Tenor tracking, checkout, or bundle failures. It may have reduced immediate downtime, but it now prevents deterministic recovery because live behavior may not correspond to a commit, artifact ID, or CI run.

### Affected files and operational areas

* `.github/workflows/docker-images.yml`
* `.github/workflows/tenor-tracking-hotfix.yml`
* `docs/deployment-runbook.md`
* `mos/backend/app/services/deploy.py`
* `mos/backend/cloudhand/adapters/deployer.py`
* Root temp deployment scratch on bridge host.
* `/opt/apps/brand-funnels-*` and `/etc/nginx/sites-*` on artifact host.
* Any local or remote patch files copied outside the repository.

### Remediation approach

1. **Freeze mutation.** No new direct artifact edits, nginx edits, symlink changes, or service restarts until evidence is captured and a reviewed plan exists.
2. **Capture provenance.**

   * For each bridge-host service checkout: `git rev-parse HEAD`, `git status --short`, `git branch --show-current`, `git describe --always --dirty`, and `git remote -v`.
   * For each production-like service: record systemd unit name, working directory, command, environment file path names only, and image/tag if containerized.
   * For artifact host: record enabled nginx site filenames, root paths, `site` symlink targets, `site-releases` directories, release timestamps, file counts, and size summaries.
3. **Quarantine scratch.** Move ad hoc patch scripts and tarballs into a dated evidence directory with read-only permissions. Do not delete until the recovery review is complete.
4. **Define release manifest.** Every standalone deployment should emit a JSON manifest into the release directory:

   * repository commit
   * CI run ID or deploy job ID
   * artifact ID/version
   * product slug
   * funnel slug/token
   * funnel ID
   * publication ID
   * page IDs and slugs
   * build timestamp
   * deployer version/hash
5. **Block dirty deploys.** Add a preflight in Cloudhand/MOS deploy that refuses to apply from a dirty control-plane checkout unless an explicit emergency override is present and logged.

### Validation steps

* Confirm every currently active artifact-host release can be mapped to a manifest or is labeled `unknown-provenance`.
* Confirm no active service working directory is both dirty and undocumented.
* Confirm a clean clone of `main` can run backend tests, migrations, frontend build, and deploy-plan generation without using scratch files.
* Confirm the Tenor artifact path is traceable to a publication ID and artifact payload.

### Rollback considerations

Rollback should mean switching to a previously captured release directory or prior CI image tag, not applying another live patch. If a prior release lacks a manifest, rollback is allowed only with an explicit authorization gate and a pre-rollback static scan of the release’s runtime config.

---

## 5.2 GitHub Actions and CI/CD path

### Current evidence

* `.github/workflows/docker-images.yml` runs backend tests against Postgres, applies migrations, runs `pytest`, builds frontend, builds backend/frontend images, and pushes images on `main`. It has a manual `workflow_dispatch` deploy job for production.
* The deploy job runs `docker compose ... pull`, `docker compose ... up -d`, `alembic upgrade head`, then restarts backend and worker, installs nginx config, runs `nginx -t`, reloads nginx, and verifies SPA routes.
* The runbook says the automatic production path is a self-deploy guard after green CI on `main`, controlled by `ENABLE_PRODUCTION_CD=true`, and post-push verification must be treated as incomplete deployment if non-zero.
* A separate Tenor hotfix workflow bypasses the normal app deploy path and SSH-patches artifacts on the static host.

### Suspected causes

**Inference:** The CI/CD path is adequate for application images and nginx app shell, but standalone funnel artifacts have an additional deployment path through Cloudhand/MOS plan/apply. The Tenor hotfix workflow indicates that at least some artifact fixes were not routed through the same test/build/release gates.

### Affected files/functions

* `.github/workflows/docker-images.yml`
* `.github/workflows/self-deploy.yml` as referenced by runbook
* `.github/workflows/tenor-tracking-hotfix.yml`
* `scripts/check_github_actions.py`
* `scripts/check_spa_routes.py`
* `mos/infra/docker-compose.deploy.yml`
* `mos/backend/app/services/deploy.py`

### Remediation approach

1. **Promote CI/CD as the default path.**

   * All code changes must land on `main`.
   * Production app deploys use green CI and self-deploy/manual workflow as documented.
   * Standalone funnel deploys use MOS/Cloudhand only after the code that generates artifacts is in the deployed backend image.
2. **Demote hotfix workflow.**

   * Disable or archive `tenor-tracking-hotfix.yml` after recovery unless there is a clearly documented emergency procedure.
   * If retained, require `workflow_dispatch`, production environment approval, and an explicit evidence snapshot step before mutation.
3. **Add standalone artifact CI tests.**

   * Backend unit tests for artifact payload identity consistency.
   * Frontend tests for runtime page maps, event payloads, checkout attribution, and PostHog/Meta mapping.
   * Deployer tests that render a standalone imported HTML artifact and assert embedded config matches source payload.
4. **Add deploy-plan validation in CI.**

   * Validate no `upstreamApiBaseUrl` with path is accepted for standalone imported HTML.
   * Validate `serverNames` and workspace domains are normalized.
   * Validate generated deploy plan has no plaintext secrets unless explicitly allowlisted as deploy-time secret refs.

### Validation steps

* `pytest` must include deploy service tests and public funnel ingestion tests.
* `npm run build` must pass.
* Standalone runtime tests must assert event payload shape and page IDs from fixture payload.
* A dry-run artifact generation command should output a manifest without applying infrastructure.

### Rollback considerations

CI/CD rollback should use image tags or previous release artifacts. Avoid reverting by patching live hosts. If the hotfix workflow must be used during a declared emergency, it should create a backup release directory and write a mutation manifest before changing files.

---

## 5.3 Cloudhand plan/apply and standalone deployment materialization

### Current evidence

* README states MOS can patch/apply deploy plans from the backend, supports workload append/deep merge, resolves Terraform from host `PATH`, enforces workload port safety, and supports `source_type` variants.
* Known gaps include no deploy queue/lock, partial Terraform generation, sensitive plan files under `DEPLOY_ROOT_DIR`, and routing sensitivity to `CLOUDHAND_NGINX_MODE`.
* `build_funnel_publication_workload_patch` supports `artifact_render_mode` values `runtime_bundle` and `standalone_imported_html`, requires standalone `upstreamApiBaseUrl` to be an origin URL without path, and sets `source_type: funnel_artifact`.
* Publish jobs hydrate the funnel artifact workload, persist runtime artifact metadata, patch the plan, optionally apply it, reconcile Bunny, and optionally run post-deploy tracking validation.

### Suspected causes

**Inference:** The Cloudhand path is doing too many operations in one flow without serialization: publication creation, artifact hydration, plan patching, Terraform apply, CDN reconciliation, and tracking validation. Without a deploy lock, two publish/apply operations can interleave across shared plan files or shared static target directories.

**Inference:** When direct scripts bypass this path, they may patch the artifact host without updating deploy state, release manifests, or job status. That causes future MOS deploys to overwrite or conflict with manual changes.

### Affected files/functions

* `mos/backend/app/services/deploy.py`

  * `build_funnel_publication_workload_patch`
  * `_require_standalone_upstream_api_origin`
  * `hydrate_funnel_artifact_workload_patch`
  * `_run_funnel_publish_job`
  * `patch_workload_in_plan`
  * `apply_plan`
  * `_run_funnel_tracking_post_deploy_validation`
* `mos/backend/cloudhand/adapters/deployer.py`

  * `_configure_funnel_artifact_site`
  * `_write_funnel_artifact_standalone_html_routes`
  * `_activate_funnel_artifact_site_release`
  * nginx generation block

### Remediation approach

1. **Add a deploy lock.**

   * Lock by deploy root + plan path + workload name.
   * Use a filesystem lock or database-backed lock.
   * Include stale-lock detection with operator-visible diagnostics.
   * Fail closed if lock cannot be acquired.
2. **Split deploy phases.**

   * Phase A: publish DB snapshot.
   * Phase B: build artifact payload and manifest.
   * Phase C: validate artifact payload identity and static render locally/in staging.
   * Phase D: patch plan.
   * Phase E: apply after authorization.
   * Phase F: post-deploy smoke.
3. **Write immutable manifests.**

   * Artifact payload ID/version and source publication ID must be written to the release directory.
   * The plan file should reference artifact ID/version, not opaque inline payload where possible.
4. **Enforce standalone origin contract.**

   * Keep `_require_standalone_upstream_api_origin`.
   * Add tests for `https://host/api` rejection and `https://host` acceptance.
5. **Treat access URL inference as non-authoritative.**

   * If no access URL can be inferred, fail tracking validation and mark deploy incomplete rather than silently proceeding.

### Validation steps

* Simulate two concurrent deploy applies to the same workload; second must fail or queue cleanly.
* Generate a standalone Tenor artifact in dry-run and assert manifest identity.
* Verify standalone render mode removes `runtime_dist_path` and uses static HTML routes.
* Verify `nginx -t` config is generated but not applied in dry-run mode.

### Rollback considerations

Rollback should be release-directory based:

* Keep `site-releases/<timestamp>` immutable.
* `site` symlink updates should be atomic.
* Rollback changes only the symlink after authorization and `nginx -t`.
* Rollback manifest must be appended to deployment log.

---

## 5.4 `mos/backend/cloudhand/adapters/deployer.py`

### Current evidence

The deployer is central to standalone materialization:

* It defines runtime cache and standalone release directory names: `site-releases` and `site`.
* It validates standalone upstream API base root as an origin URL with no path/query/fragment.
* It canonicalizes `pre-sales` to `presales`.
* It resolves default route and prefers `sales-page` or `sales` over the publication entry slug if present.
* It builds preloaded runtime payloads with only the default landing page to keep inline runtime lean.
* It validates standalone output for route existence, bridge marker, unresolved placeholders, PostHog bootstrap, and Meta bootstrap.
* It extracts standalone imported HTML props and requires exactly one `ImportedHtmlDocument` block with valid instrumentation manifest.
* It injects standalone imported HTML bridge config containing API base path, product slug, funnel slug, page ID, page slug, stage, funnel ID, publication ID, tracking, manifest, variants, and page paths.
* It writes standalone HTML routes under product/funnel/page paths, activates release via atomic symlink, generates nginx config, tests nginx, reloads nginx, and may provision HTTPS.

### Suspected causes

**Inference:** The deployer can materialize correct artifacts only if the artifact payload is correct. It has validation for bridge presence and provider bootstrap, but the evidence does not show a validation that every `pageId` in static runtime config exists in the live MOS database before activation. The journal failure suggests this validation is missing or insufficient.

**Inference:** The deployer’s default route preference for sales page may be useful for sales-page-first funnels but dangerous for a quiz/pre-sales launch if the expected default entry should be quiz. This should become explicit deploy policy, not implicit fallback.

**Inference:** Because the deployer owns large inline JS/runtime bridge logic, it is vulnerable to drift from `StandaloneImportedHtmlPage.tsx`.

### Affected functions

* `_canonical_funnel_artifact_page_slug`
* `_canonicalize_funnel_artifact_meta`
* `_resolve_funnel_artifact_default_page_slug`
* `_resolve_funnel_artifact_runtime_target`
* `_build_preloaded_funnel_runtime_payload`
* `_extract_standalone_imported_html_props`
* `_build_standalone_imported_html_page_paths`
* `_inject_standalone_imported_html_bridge`
* `_write_funnel_artifact_standalone_html_routes`
* `_validate_funnel_artifact_site_output`
* `_activate_funnel_artifact_site_release`
* `_configure_funnel_artifact_site`

### Remediation approach

1. **Make default-route choice explicit.**

   * Add a source_ref field such as `default_page_policy`.
   * Allowed values: `entry_page`, `sales_page`, `explicit_slug`.
   * For Tenor quiz, use explicit quiz/pre-sales route when launching quiz; do not rely on sales-page preference.
2. **Validate identity before activation.**

   * For every rendered standalone page:

     * `productSlug` matches product route slug.
     * `funnelSlug` or path token resolves to the expected funnel.
     * `publicationId` exists and belongs to funnel.
     * every `pageId` in `pageMap` exists and belongs to the funnel/publication snapshot.
     * page stage in payload matches manifest stage and route expectations.
   * Fail before symlink activation if any ID is invalid.
3. **Add manifest write.**

   * Write `mos-release-manifest.json` into every release directory.
   * Include all IDs and route maps.
4. **Centralize bridge source.**

   * Move large inline standalone bridge JS into a dedicated source asset.
   * Generate or bundle it during build.
   * Deployer should inject JSON config, not own hand-maintained tracking logic.
5. **Tighten output checks.**

   * Existing checks for marker/bootstrap are good but insufficient.
   * Add checks for:

     * no `mengotomars.com`
     * no Heyflow scripts when deploying Tenor quiz
     * no unresolved MOS placeholder
     * correct `publicationId` and page IDs embedded once
     * `POST /api/public/events` endpoint present for standalone bridge
6. **Retention policy.**

   * Keep last N releases or last X days with manifests.
   * Do not allow unbounded release growth.

### Validation steps

* Unit test slug canonicalization and duplicate slug failure.
* Fixture test for a Tenor-like artifact with quiz + sales pages:

  * root redirect policy explicit
  * quiz route emits pre-sales stage
  * sales route emits sales stage
  * page IDs match fixture DB rows
* Render a standalone fixture and grep output for bridge marker, PostHog, Meta, route config, and absence of forbidden external legacy domains.
* Confirm `site` symlink points to an immutable release directory with manifest.

### Rollback considerations

The deployer already uses `site.__next__` and `mv -Tf` for atomic symlink activation. Keep that pattern. Add a rollback command that selects a prior manifest-validated release. Do not roll back to a release that lacks an identity manifest unless explicitly authorized.

---

## 5.5 `mos/backend/app/services/deploy.py`

### Current evidence

`deploy.py` owns the MOS-side deploy orchestration:

* It defines standalone render modes and tracking validation constants.
* It rejects standalone upstream API base URLs that include a path/query/fragment.
* It builds funnel artifact workload patches, setting `source_type: funnel_artifact`, `source_ref.client_id`, `source_ref.upstream_api_base_root`, `artifact_render_mode`, and optional `runtime_dist_path` for runtime bundle.
* It builds client funnel runtime artifact payloads from active publication pages, page versions, product route slugs, design tokens, metadata, tracking, page maps, stage maps, type maps, and variants.
* It auto-resolves standalone render mode if every page supports `ImportedHtmlDocument` or compliance page.
* It builds post-deploy tracking validation plans, expected events, and Playwright validations for internal events, Meta, and PostHog.
* Publish jobs publish the funnel, hydrate artifact payload, patch plan, optionally apply, reconcile Bunny, and run tracking validation.

### Suspected causes

**Inference:** `build_client_funnel_runtime_artifact_payload` likely needs stronger validation around publication/page ID referential integrity. It builds `pageMap` and `pages_payload` from publication pages and page versions, but the journal evidence indicates that an emitted `pageId` did not satisfy `funnel_events_page_id_fkey` at ingestion. That can happen if:

* the artifact was generated from one database and events ingested into another;
* the artifact included a generated/synthetic page ID;
* publication pages referenced stale/deleted `FunnelPage` rows;
* live artifact was older than current DB state;
* direct patching changed embedded IDs;
* event ingestion expects `funnel_pages.id` while artifact points at another table or stale ID.

**Inference:** Post-deploy tracking validation appears focused on emitted event names and provider bootstraps, not database acceptance of events by the real ingestion endpoint under the exact deployed `publicationId` and `pageId`.

### Affected functions

* `build_client_funnel_runtime_artifact_payload`
* `persist_client_funnel_runtime_artifact`
* `_artifact_payload_supports_standalone_imported_html`
* `_resolve_publish_job_artifact_render_mode`
* `_apply_publish_job_artifact_render_mode`
* `_extract_funnel_tracking_page_entries`
* `_build_funnel_tracking_validation_plan`
* `_validate_deployed_tracking_html`
* `_validate_observed_tracking_events`
* `_run_funnel_tracking_post_deploy_validation`
* `_run_funnel_publish_job`
* `start_funnel_publish_job`

### Remediation approach

1. **Add artifact identity audit before persistence.**

   * Query DB for every `funnelId`, `publicationId`, and `pageId` in the artifact payload.
   * Fail if any page ID is missing or not associated with the publication.
   * Fail if `pageMap` includes page IDs not in publication pages.
   * Fail if `pageStageMap` keys differ from `pageMap` keys.
2. **Add ingestion preflight.**

   * Before artifact activation, call or simulate `POST /public/events` using a validation event for each page ID against a non-persistent dry-run endpoint, or add an internal validation service that performs the same FK lookup without insert.
   * If adding dry-run support, it must not silently bypass constraints.
3. **Make publication overrides visible.**

   * The build function accepts `publication_id_overrides`; every use should be logged in the artifact manifest.
4. **Persist immutable artifact payloads.**

   * Ensure artifact payload stored for apply is immutable and versioned.
   * Do not regenerate payload during apply from mutable live DB unless explicitly intended.
5. **Strengthen post-deploy validation.**

   * Existing Playwright checks should include observed successful response from `/public/events`, not only client-side event collection.
   * Validate no 4xx/5xx for event ingestion during smoke.
6. **Guard against huge artifacts.**

   * The deploy service has max embedded asset size constants. Use them to fail early with explicit asset IDs rather than generating enormous release directories.

### Validation steps

* Add backend tests:

  * artifact payload fails if page ID missing from DB;
  * artifact payload fails if publication ID does not belong to funnel;
  * artifact payload fails if `pageMap` and `pageStageMap` differ;
  * standalone artifact validation catches missing bridge marker;
  * post-deploy validation catches event ingestion 500/FK violation.
* Run migration head and tests in CI.
* Generate a Tenor dry-run artifact and inspect `mos-release-manifest.json`.
* Submit a dry-run validation event with exact page/publication IDs and assert success before deployment.

### Rollback considerations

If `deploy.py` has already persisted a bad runtime artifact, do not delete it immediately. Mark it `invalid` or quarantine it with reason. Keep it for audit, but prevent apply jobs from selecting it. Roll back to a prior artifact version only after verifying its page IDs still exist in the current DB.

---

## 5.6 Backend deploy API and public funnel routes

### Current evidence: deploy API

`mos/backend/app/routers/deploy.py` exposes:

* `GET /deploy/plans/latest`
* `POST /deploy/plans`
* `POST /deploy/plans/workloads`
* `GET /deploy/plans/workloads/domains`
* `POST /deploy/plans/apply`
* `POST /deploy/apply` alias

It requires Clerk auth and calls `_require_internal_proxy`, which blocks direct backend-port calls unless the request client is loopback/testclient/localhost.

The README notes that this proxy-only restriction is transport-level and not full policy-level UI-only restriction, and deploy RBAC is not scoped to admin/operator roles.

### Current evidence: public funnel routes

`mos/backend/app/routers/public_funnels.py` canonicalizes pre-sales slugs, resolves funnels by route slug, UUID, or short ID prefix, checks product route slug, returns publication ID for public responses, serves funnel meta/pages, and returns preview fallback behavior for unpublished funnels. The excerpt shows `_canonical_public_page_slug`, `_public_page_slug_candidates`, `_resolve_funnel_by_route_token`, `_get_funnel_or_404`, and `_publication_id_for_public_response`.

Public runtime schemas return page payloads with `productSlug`, `funnelId`, `publicationId`, `pageId`, slug, `puckData`, `pageMap`, `pageStageMap`, metadata, tracking, and `nextPageId`.

### Suspected causes

**Inference:** The deploy API can mutate plans and trigger applies through any authenticated org member if they can reach the proxied route. That is too broad for infrastructure mutation.

**Inference:** Public route resolution supports multiple funnel tokens, including short UUID prefix. That is useful but can create ambiguity unless every artifact path token is tied to a manifest. The deployer also independently resolves funnel path tokens; any mismatch between public route token logic and deployer token logic can cause standalone paths to resolve differently.

**Inference:** Preview-mode fallback returning the funnel ID as publication ID helps avoid invalid UUIDs for unpublished funnels, but public standalone production artifacts should not depend on preview fallback. A production standalone artifact must carry a real active publication ID.

### Affected files/functions

* `mos/backend/app/routers/deploy.py`

  * `_require_internal_proxy`
  * `patch_workload`
  * `apply_plan`
  * `get_workload_domains`
* `mos/backend/app/routers/public_funnels.py`

  * `_canonical_public_page_slug`
  * `_public_page_slug_candidates`
  * `_resolve_funnel_by_route_token`
  * `_get_funnel_or_404`
  * `_publication_id_for_public_response`
  * public meta/page endpoints
  * public event ingestion endpoint, not shown in full snippet but implicated by `PublicEventIn` and journal failures
* `mos/backend/app/schemas/funnels.py`

  * `PublicFunnelPageResponse`
  * `PublicEventIn`
  * `PublicEventsIngestRequest`

### Remediation approach

1. **Deploy API authorization.**

   * Add role check for `admin` or `ops` before plan save, workload patch, and apply.
   * Keep `_require_internal_proxy`, but do not treat it as sufficient authorization.
   * Log actor user/org, workload name, plan path, render mode, and apply flag.
2. **Deploy API dry-run mode.**

   * Add a route or payload flag to validate workload patches without writing plan files.
   * Return normalized workload, inferred domains, render mode, and identity audit.
3. **Public route identity contract.**

   * Add a backend helper that resolves:

     * product slug
     * funnel token
     * funnel ID
     * active publication ID
     * page slug
     * page ID
     * page stage
   * Use the same helper for public page response and event ingestion.
4. **Event ingestion validation.**

   * For each incoming event:

     * validate `publicationId` exists;
     * validate `pageId` belongs to that publication;
     * validate publication belongs to resolved funnel/product context when path data is available;
     * if invalid, return a clean 422 with event ID and reason, not an unhandled 500.
   * Do not silently rewrite page IDs.
5. **Idempotency.**

   * Use `eventId` unique index as intended.
   * Duplicate event IDs should be treated as idempotent success where safe.
6. **Canonical slug consistency.**

   * Ensure backend public route canonicalization and deployer artifact canonicalization share the same rules for:

     * `pre-sales` -> `presales`
     * custom pre-sales slugs
     * sales-page preservation
     * short funnel token resolution
7. **Production preview separation.**

   * Public production standalone artifacts should not use preview publication fallback.
   * Add a validation that standalone deploys require a real `active_publication_id`.

### Validation steps

* API tests:

  * non-admin authenticated user cannot call deploy apply;
  * direct non-loopback deploy call still blocked;
  * admin/ops can dry-run workload patch;
  * event ingestion rejects invalid page/publication pair with 422;
  * duplicate event ID returns idempotent behavior;
  * production standalone page payload uses real active publication ID.
* Route tests:

  * `/product/funnel/pre-sales` redirects or resolves consistently to `presales`;
  * short UUID funnel token resolves only when unique;
  * ambiguous short token returns 404/409, not arbitrary match.
* Smoke:

  * Load Tenor sales route.
  * Emit one controlled validation event.
  * Verify DB insert or idempotent success.
  * Verify no FK violation in journal.

### Rollback considerations

Authorization and validation changes can initially be deployed in monitor/dry-run mode for reads, but write paths should fail closed once enabled. If stricter event ingestion rejects live events due to existing bad artifacts, do not weaken ingestion silently; pause event ingestion for invalid artifacts or republish corrected artifacts behind an explicit gate.

Continue in Part 2.


## 5.7 Funnel publication model, page IDs, publication IDs, slug canonicalization, root redirects, and stage semantics

### Current evidence

**Evidence:** Public funnel responses carry `productSlug`, `funnelId`, `publicationId`, `pageId`, `slug`, `puckData`, `pageMap`, `pageStageMap`, design tokens, metadata, optional tracking, and optional `nextPageId`. The public event input schema requires `eventType`, `publicationId`, and `pageId`, with optional `eventId`, visitor/session identifiers, path, referrer, UTM, and props.

**Evidence:** `FunnelEvent` stores `publication_id` as a foreign key to `funnel_publications.id` and `page_id` as a foreign key to `funnel_pages.id`. It also has a unique partial index on `event_id` where `event_id IS NOT NULL`.

**Evidence:** The public event ingestion route requires all events in a batch to share one `publicationId`, validates that `publicationId` is a UUID, resolves a `FunnelPublication`, resolves the associated `Funnel`, skips persistence for site/preview cases, checks existing `event_id` values, and rejects unsupported event types. The snippet does not show a pre-insert check that each `pageId` belongs to the publication before insert.

**Evidence:** Journal evidence shows a real `funnel_events_page_id_fkey` violation for an event emitted by standalone HTML mode. The failed insert included a valid-looking funnel ID and publication ID, but the `page_id` did not satisfy the database foreign key.

**Evidence:** Public route slug handling canonicalizes legacy pre-sales slugs: backend public funnel helpers map pre-sales/presales forms to canonical `presales`, and frontend runtime page map helpers do the same for legacy pre-sales pages while preserving custom pre-sales slugs.

**Evidence:** Cloudhand standalone rendering also canonicalizes `pre-sales` to `presales`, resolves funnel path tokens, writes static route directories for each page, and uses route paths of the form `/{product}/{funnel}/{page}/`.

**Evidence:** The deployer’s default route logic prefers `sales-page` or `sales` if either exists, otherwise it uses the publication entry slug. Generated nginx for standalone imported HTML can redirect `/` to the resolved default route.

### Suspected causes

**Inference:** The foreign-key failure is not primarily a slug problem. It is an identity problem. The failing runtime had a `pageId` value that the database did not consider a valid `funnel_pages.id`. Slug canonicalization can contribute to routing confusion, but the concrete failure is a broken ID relationship.

**Inference:** The most likely page identity breakpoints are:

1. A standalone artifact was generated from a publication snapshot containing a stale page ID.
2. The artifact was generated against one database/environment and posted events to another.
3. A direct patch or republish changed static runtime config without updating database publication/page rows.
4. A page was deleted/recreated after artifact generation, leaving the static artifact with an obsolete `pageId`.
5. The publication snapshot references a page version but the page row itself is absent or mismatched.
6. A generated/imported standalone HTML page used an ID derived outside the `funnel_pages` table.

**Inference:** The root redirect to sales-page is not automatically wrong because the deployer intentionally prefers sales-page when available. However, for a Tenor quiz/pre-sales launch, this default can hide the fact that the intended quiz entry route is not the default. The quiz plan explicitly expects a same-origin pre-sales quiz path that hands off to the sales page, so default-route behavior must be explicit for quiz deployments rather than inferred by sales-page preference.

### Affected files and functions

* `mos/backend/app/routers/public_funnels.py`

  * public meta route
  * public page route
  * public event ingestion route
  * `_canonical_public_page_slug`
  * `_public_page_slug_candidates`
  * `_publication_id_for_public_response`
* `mos/backend/app/services/deploy.py`

  * `build_client_funnel_runtime_artifact_payload`
  * `_extract_funnel_tracking_page_entries`
  * `_build_funnel_tracking_validation_plan`
  * `_run_funnel_tracking_post_deploy_validation`
* `mos/backend/cloudhand/adapters/deployer.py`

  * `_canonical_funnel_artifact_page_slug`
  * `_resolve_funnel_artifact_default_page_slug`
  * `_resolve_funnel_artifact_runtime_target`
  * `_build_preloaded_funnel_runtime_payload`
  * `_build_standalone_imported_html_page_paths`
  * `_write_funnel_artifact_standalone_html_routes`
* `mos/frontend/src/funnels/runtimePageMaps.ts`
* `mos/frontend/src/pages/public/PublicFunnelRootRedirectPage.tsx`
* `mos/frontend/src/pages/public/PublicFunnelEntryRedirectPage.tsx`
* `mos/frontend/src/pages/public/PublicFunnelPage.tsx`
* `mos/backend/app/db/models.py`
* `mos/backend/app/schemas/funnels.py`

### Remediation approach

#### 5.7.1 Add an explicit publication identity audit

Before artifact persistence and before standalone release activation, validate the artifact payload against the database.

Required checks:

* `artifact.meta.updatedFromFunnelId` must match a real funnel.
* `artifact.meta.updatedFromPublicationId` must match a real publication for that funnel.
* Every product bucket must map to a real product route slug.
* Every funnel payload must contain:

  * `meta.funnelId`
  * `meta.publicationId`
  * `meta.entrySlug`
  * `meta.pages[]`
  * `pages` object
* `meta.publicationId` must equal the active or explicitly selected publication ID used to build the artifact.
* Every `meta.pages[].pageId` must exist in `funnel_pages`.
* Every `pages[*].pageId` must exist in `funnel_pages`.
* Every `pageMap` key must exist in `funnel_pages`.
* Every `pageStageMap` key must have a matching `pageMap` key.
* Every page in the publication must appear exactly once in the artifact route map.
* No extra page IDs may appear in the artifact that are not in the publication.
* The page slug stored in `funnel_publication_pages.slug_at_publish` must canonicalize to the same artifact slug used in `pages`.

This validation should run in `build_client_funnel_runtime_artifact_payload` or immediately after it, before the artifact is persisted. It should also run in `_apply_publish_job_artifact_render_mode` or `hydrate_funnel_artifact_workload_patch` before the deploy plan is patched.

#### 5.7.2 Add an event-ingestion identity preflight

Public event ingestion should not rely on a database foreign-key exception as the first validation layer.

For each event:

* validate `event.publicationId` was already resolved to a real `FunnelPublication`;
* validate `event.pageId` exists in `funnel_pages`;
* validate the page belongs to the same funnel as the publication;
* validate the page was part of the publication page set, not just any page in the same funnel;
* validate `event.eventType` maps to `FunnelEventTypeEnum`;
* validate `eventId` uniqueness or duplicate idempotency before insert.

When validation fails, return a 422-style structured error with:

* `eventId`
* `publicationId`
* `pageId`
* `eventType`
* failure reason
* whether the publication exists
* whether the page exists
* whether the page belongs to the publication

Do not rewrite page IDs at ingestion time. A rewrite would hide the artifact identity defect and contaminate analytics.

#### 5.7.3 Make root redirect policy explicit

Add a deploy/source field such as:

```json
{
  "default_route_policy": "entry_page"
}
```

Allowed policies:

* `entry_page`: use publication entry page.
* `sales_page`: prefer sales page if present.
* `explicit_slug`: require `default_page_slug`.
* `none`: do not generate a root redirect; root returns a controlled diagnostic page or 404.

For Tenor quiz deployment, use `explicit_slug: "quiz-v6"` or `entry_page` after setting the quiz page as the publication entry page. Do not allow the deployer to silently choose sales-page for quiz launches.

#### 5.7.4 Unify canonical slug rules

Define one canonical slug helper shared or duplicated with tests across:

* backend public routes;
* deploy artifact generation;
* frontend runtime page maps;
* deployer static route writer.

Rules that must remain consistent:

* legacy `pre-sales` and `presales` normalize to `presales` only for legacy pre-sales pages;
* custom pre-sales slugs such as `quiz-v6` or `10-reasons-glp` must be preserved;
* `sales-page` must be preserved;
* page slugs may not contain slash or backslash;
* route tokens must be lowercased only when that is the established public contract.

### Validation steps

1. Build a fixture funnel with:

   * product slug;
   * route slug;
   * pre-sales page slug `presales`;
   * custom quiz page slug `quiz-v6`;
   * sales page slug `sales-page`;
   * publication with quiz entry.
2. Generate an artifact.
3. Assert:

   * every `pageId` exists in `funnel_pages`;
   * `publicationId` exists in `funnel_publications`;
   * `pageMap` and `pageStageMap` have identical key sets;
   * static route paths include `/quiz-v6/` and `/sales-page/`;
   * root redirect follows explicit policy.
4. POST validation events using the exact generated IDs.
5. Confirm:

   * valid events insert or idempotently no-op;
   * invalid page IDs return structured 422;
   * no raw SQLAlchemy FK traceback reaches logs as the primary error path.

### Rollback considerations

Do not roll back by relaxing FK constraints. The `funnel_events.page_id` FK is valuable evidence that the artifact is wrong. If a live artifact is emitting invalid page IDs, the safe rollback is to switch to a prior manifest-validated artifact or republish from a correct publication snapshot after explicit authorization.

---

## 5.8 Standalone imported HTML renderer and runtime bootstrap

### Current evidence

**Evidence:** The editor/preview imported HTML renderer injects a runtime script into an iframe `srcDoc`. That script measures height, binds manifest selectors, handles navigation/checkout/track/error messages, and reports errors when selectors do not match.

**Evidence:** The public standalone imported HTML renderer delegates to `StandaloneImportedHtmlPage`, passing page identity, product/funnel slug, visitor/session IDs, HTML document, instrumentation manifest, variants, page path map, and page stage map.

**Evidence:** `StandaloneImportedHtmlPage` directly writes the optimized imported HTML document into `document` with an injected standalone runtime script. It skips reinjection when `window.__mosImportedHtmlStandalonePageId` already equals the current page ID.

**Evidence:** The standalone runtime tests assert that the injected script contains commerce loading, `/public/funnels/`, `/commerce`, event tracking, prepared checkout flows, checkout status text, and warm checkout behavior. They also test Klaviyo email capture, RMBC sales diagnostic events, prepared checkout reuse, purchase-mode selection, image optimization, Meta sales-page events, and PostHog sales-page captures.

**Evidence:** The deployer independently injects a standalone imported HTML bridge for static exports, building a config with API base path, product slug, funnel slug, page ID, page slug, stage, funnel ID, publication ID, tracking, manifest, variants, and page paths.

**Evidence:** The workspace PostHog plan explicitly identifies duplicated bootstrap ownership between the Python deployer and the TypeScript standalone runtime as a drift risk.

### Suspected causes

**Inference:** The public runtime and static deployer are functionally overlapping but not necessarily generated from the same source. That creates a high probability that checkout, tracking, or event-shape fixes land in one path but not the other.

**Inference:** The `document.write` strategy in `StandaloneImportedHtmlPage` is intentional for full-document imported HTML, but it makes lifecycle and re-entry behavior fragile. The page ID guard prevents duplicate injection for the same page ID but can also make debugging stale page identity harder if the wrong page ID is embedded.

**Inference:** The Tenor quiz plan requires a first-party quiz runtime rather than raw Heyflow/Mars Shopify capture. If the imported HTML source still contains old external dependencies, the standalone bridge may work while the page itself still runs legacy scripts or emits non-MOS events.

### Affected files and functions

* `mos/frontend/src/funnels/ImportedHtmlDocument.tsx`
* `mos/frontend/src/funnels/StandaloneImportedHtmlPage.tsx`
* `mos/frontend/src/funnels/importedHtmlRuntime.ts`
* `mos/frontend/src/pages/public/PublicImportedHtmlRenderer.tsx`
* `mos/frontend/src/pages/public/PublicFunnelPage.tsx`
* `mos/backend/cloudhand/adapters/deployer.py`

  * `_inject_standalone_imported_html_bridge`
  * `_prepare_standalone_imported_html_document`
  * `_render_standalone_funnel_artifact_page`
* `mos/backend/app/services/imported_html_runtime.py`
* `mos/backend/tests/test_imported_html_runtime.py`
* `mos/frontend/src/funnels/StandaloneImportedHtmlPage.test.tsx`

### Remediation approach

#### 5.8.1 Centralize the standalone bridge source

The deployer should not own a hand-maintained copy of runtime tracking/checkout/bootstrap behavior. The target architecture:

* one canonical TypeScript source for standalone bridge behavior;
* build step emits a JS asset or string artifact;
* Python deployer reads/injects that built asset;
* Python injects only JSON config and minimal loader wrapper;
* tests compare the runtime contract across public React and static export paths.

Minimum acceptable refactor:

* Extract the large inline bridge script out of `deployer.py`.
* Add a checksum for the bridge asset into release manifest.
* Add a test that fails if deployer bridge asset is missing required event names and endpoints.

Preferred refactor:

* Build a standalone bridge bundle during frontend build.
* Store it under a backend-accessible static asset path.
* Deployer injects:

  * static bridge bundle;
  * `window.__MOS_STANDALONE_IMPORTED_HTML_CONFIG__ = {...}`.
* Runtime imports shared event mapping semantics from the same source.

#### 5.8.2 Add strict imported HTML sanitation for Tenor quiz

For Tenor quiz artifacts, add a static scan before artifact persistence and before deploy:

Forbidden strings/classes/domains for this artifact class:

* legacy source-brand domains;
* Heyflow wrapper/classes/scripts;
* old Shopify storefront scripts from the source capture;
* legacy canonical/base URLs;
* old pixels or web pixel scripts not owned by MOS runtime;
* raw secret-like tokens.

Required strings/config:

* `productSlug`;
* expected funnel token;
* expected `publicationId`;
* expected quiz `pageId`;
* `pageStage: "pre_sales"`;
* `/api/public/events`;
* final sales destination under the same public host/path;
* no answer-based routing for the current version, unless explicitly approved.

#### 5.8.3 Runtime error behavior

Do not silently ignore critical binding failures for launch-critical selectors.

Current iframe editor runtime reports binding selector misses as errors. The standalone production bridge should classify bindings:

* `required: true`: failure emits a visible diagnostic in validation mode and fails deploy smoke;
* `required: false`: failure logs diagnostic and continues;
* checkout CTA and quiz final CTA are required;
* tracking-only diagnostic sections can be optional when explicitly marked.

#### 5.8.4 Page identity guard diagnostics

Add debug metadata to standalone runtime:

* `window.__mosImportedHtmlStandalonePageId`;
* `publicationId`;
* `artifactId`;
* `releaseId`;
* `bridgeVersion`;
* `pageSlug`.

Expose this only in non-secret structured form, preferably in a comment block or `window.__MOS_RELEASE_MANIFEST__` subset. It must not include env secrets.

### Validation steps

* Unit tests:

  * `StandaloneImportedHtmlPage` emits page view with correct `publicationId` and `pageId`.
  * Pre-sales page emits both `pre_sales_page_view` and `presell_page_view` as currently coded for pre-sales pages.
  * Required selector missing fails validation.
  * Optional selector missing does not fail.
* Static artifact tests:

  * rendered HTML contains bridge marker;
  * rendered HTML contains correct page/publication IDs;
  * rendered HTML does not contain forbidden legacy strings;
  * rendered HTML posts to `/api/public/events`.
* Browser smoke:

  * load quiz route;
  * complete quiz;
  * verify final CTA emits `quiz_cta_viewed` and `pre_sales_to_sales_click`;
  * verify handoff URL includes stitchable query params;
  * verify sales page records `fromPresale`.

### Rollback considerations

A bridge refactor can break all standalone imported HTML pages if shipped carelessly. Roll out behind an artifact-renderer version field:

* old artifacts keep old bridge;
* new artifacts use new bridge;
* deploy validation must test both until old artifacts are retired;
* never rewrite existing release directories in place.

---

## 5.9 Public funnel runtime routes and page maps

### Current evidence

**Evidence:** `PublicFunnelPage.tsx` resolves route params, detects standalone bundle mode, reads preloaded funnel data if available, fetches meta/page/commerce when needed, builds `standalonePagePathById` from `page.pageMap`, and passes `pageStageById` to the imported HTML renderer.

**Evidence:** `PublicFunnelRootRedirectPage.tsx` reads the standalone default page route and navigates to the built public funnel path, preserving search/hash. If no default route exists, it reports that the deployment has no published standalone entry page configured.

**Evidence:** `PublicFunnelEntryRedirectPage.tsx` fetches funnel meta and redirects to the preferred public funnel slug.

**Evidence:** `runtimePageMaps.ts` builds runtime page maps, stage maps, and type maps from page-like objects, resolving stages from template IDs, slugs, or names and canonicalizing legacy pre-sales slugs.

### Suspected causes

**Inference:** The public runtime has two modes that can diverge:

* live API mode: fetches current DB-backed meta/page/commerce;
* standalone bundle mode: uses preloaded funnel data embedded during deploy.

If an artifact is old but the API/database is newer, the page may render from old embedded data while event ingestion validates against current DB constraints. That can produce the observed FK failure.

**Inference:** `standalonePagePathById` depends on the page payload’s `pageMap`. If `pageMap` includes stale page IDs or slugs, internal navigation and pre-sales attribution can be wrong even if the rendered HTML appears correct.

### Affected files/functions

* `mos/frontend/src/pages/public/PublicFunnelPage.tsx`
* `mos/frontend/src/pages/public/PublicFunnelRootRedirectPage.tsx`
* `mos/frontend/src/pages/public/PublicFunnelEntryRedirectPage.tsx`
* `mos/frontend/src/funnels/runtimeRouting.ts`
* `mos/frontend/src/funnels/runtimePageMaps.ts`
* `mos/frontend/src/pages/research/funnels/funnelPublicUrls.test.ts`
* `mos/backend/cloudhand/adapters/deployer.py`

  * `_inject_funnel_runtime_config`
  * `_build_preloaded_funnel_runtime_payload`

### Remediation approach

#### 5.9.1 Embed artifact freshness metadata

`window.__MOS_DEPLOY_RUNTIME__` should include:

* artifact ID;
* artifact version;
* publication ID;
* build timestamp;
* source commit;
* release ID;
* `pageIds`;
* `defaultRoutePolicy`;
* `defaultEntrySlug`.

The public runtime can include this in validation-only event props. Do not include secrets.

#### 5.9.2 Add runtime/database mismatch detection

When standalone bundle mode is active and API is reachable, the runtime can optionally fetch a lightweight identity endpoint:

```text
GET /public/funnels/{productSlug}/{funnelSlug}/identity
```

Expected response:

* active publication ID;
* page IDs by slug;
* route slug;
* product slug.

The runtime should not self-heal by changing IDs. It should:

* emit a diagnostic event if identity mismatches;
* show a validation failure during smoke tests;
* keep production behavior deterministic.

#### 5.9.3 Preloaded funnel page coverage

The deployer currently keeps the inline runtime lean by preloading only the default landing page. That is valid for performance, but for multi-page standalone HTML navigation, the static routes must still contain all page HTML and all page maps. Add validation that every route referenced by `pagePathById` exists on disk.

#### 5.9.4 Query-string preservation

Root and entry redirects preserve query and hash. Keep this behavior because attribution relies on UTMs and click IDs. Validate it with tests for:

* `fbclid`;
* `gclid`;
* `utm_source`;
* quiz handoff params;
* `src=presale`.

### Validation steps

* `npm test` route map tests:

  * product/funnel/page path generation;
  * canonical pre-sales slug behavior;
  * custom quiz slug preservation;
  * default route selection.
* Browser tests:

  * direct root load redirects to expected route;
  * direct quiz route renders without API fetch failure;
  * direct sales route preserves attribution;
  * invalid route returns controlled unavailable state, not blank page.
* Static route file check:

  * every page in `pageMap` has an `index.html`;
  * root redirect target exists;
  * no route points to a missing page slug.

### Rollback considerations

Page-map changes should be deployed with new artifacts only. Do not rewrite `pageMap` in old release directories unless an explicit emergency gate authorizes a one-off static patch and records the exact old/new manifest.

---

## 5.10 Analytics event ingestion, `funnel_events`, schema constraints, migrations, and idempotency

### Current evidence

**Evidence:** `FunnelEvent` includes foreign keys to org, client, funnel, publication, and page, indexes by occurred time and funnel/publication, and has a unique partial event ID index.

**Evidence:** Migration `0089_rmbc_funnel_event_ids_and_types.py` adds an `event_id` column and a unique partial index, indicating intentional idempotency support.

**Evidence:** Migrations `0090` and `0091` add quiz and checkout timing event types.

**Evidence:** `FunnelEventTypeEnum` includes page view, pre-sales, sales, checkout, RMBC diagnostic, purchase, tracking chain, web vital, quiz, and checkout redirect timing event types.

**Evidence:** The journal shows a `web_vital_recorded` event failed due to `funnel_events_page_id_fkey`, not due to unsupported event type.

### Suspected causes

**Inference:** Event type coverage is no longer the main blocker for quiz instrumentation because quiz event enum values and migrations exist. The immediate failure class is referential integrity.

**Inference:** The public event ingestion path appears to batch by publication ID and dedupe by `eventId`, but it needs stronger page-publication validation before insert. Without that, invalid page IDs become database exceptions and can produce unhandled server errors.

**Inference:** `web_vital_recorded` being the failing event means background diagnostics can surface identity mismatch even before high-value click/conversion events. That is useful: web vital events can act as canaries for artifact identity.

### Affected files/functions

* `mos/backend/app/db/models.py`

  * `FunnelEvent`
* `mos/backend/app/db/enums.py`

  * `FunnelEventTypeEnum`
* `mos/backend/alembic/versions/0089_rmbc_funnel_event_ids_and_types.py`
* `mos/backend/alembic/versions/0090_quiz_funnel_event_types.py`
* `mos/backend/alembic/versions/0091_checkout_redirect_timing_event_types.py`
* `mos/backend/app/routers/public_funnels.py`

  * public event ingestion route
* `mos/backend/app/schemas/funnels.py`

  * `PublicEventIn`
  * `PublicEventsIngestRequest`
* `mos/frontend/src/lib/funnelTracking.ts`
* `mos/frontend/src/funnels/StandaloneImportedHtmlPage.tsx`

### Remediation approach

#### 5.10.1 Add deterministic event validation

For each event in a batch:

* `eventId`: optional, max length enforced by schema; when present, use idempotency.
* `eventType`: must map to `FunnelEventTypeEnum`.
* `publicationId`: must match the batch publication and exist.
* `pageId`: must exist and belong to publication.
* `path`: should be accepted as diagnostic but not trusted as identity.
* `props.fromPageId`: if present, must equal `pageId` or be explicitly marked as previous-page context.

Return shape for invalid events:

```json
{
  "ingested": 0,
  "errors": [
    {
      "eventId": "...",
      "eventType": "...",
      "publicationId": "...",
      "pageId": "...",
      "code": "page_not_in_publication"
    }
  ]
}
```

Use 422 for validation errors. Use 200/202 for duplicate `eventId` no-op when the duplicate already exists.

#### 5.10.2 Preserve batch safety

A batch should be atomic for a single publication. Do not partially ingest a batch unless the response clearly reports which events were ingested and which failed. For a public funnel runtime, atomic failure is cleaner during recovery because it prevents partial event chains.

#### 5.10.3 Add idempotent duplicate behavior

When `eventId` already exists:

* skip inserting the duplicate;
* count it as `deduped`;
* do not treat it as an error;
* return `ingested`, `deduped`, and `rejected`.

This matches the migration’s purpose and prevents retry storms from `keepalive` posts.

#### 5.10.4 Add event-source classification

Record a sanitized source classification in props or a separate field:

* `runtime_mode`: `public_api`, `standalone_bundle`, `standalone_html`;
* `artifact_id`;
* `release_id`;
* `bridge_version`;
* `validation`: true/false.

This makes future incidents diagnosable without inspecting raw HTML.

### Validation steps

* Backend tests:

  * valid event inserts;
  * duplicate event ID dedupes;
  * invalid event type returns 400;
  * invalid publication returns 404;
  * page ID not in publication returns 422;
  * page ID missing from `funnel_pages` returns 422;
  * preview publication ID returns `ingested: 0` without error, matching current documented preview skip behavior.
* Browser tests:

  * standalone pre-sales page emits page-view chain;
  * quiz events insert with exact page IDs;
  * web vital event inserts for deployed page.
* Database checks:

  * no FK violations in journal after controlled smoke;
  * no spike in 4xx/5xx from `/public/events`.

### Rollback considerations

Do not remove the `page_id` FK or publication FK as a rollback. If stricter validation exposes bad live artifacts, mark the artifact invalid and republish; do not weaken analytics integrity.

---

## 5.11 PostHog tracking, Meta events, proxying, client-side bridge, and server-side conversion events

### Current evidence

**Evidence:** The workspace-owned PostHog plan says PostHog should be stored per workspace, public funnel pages should read workspace config from the database, standalone imported HTML artifacts should snapshot workspace config into artifact payloads at build time, and standalone deploys should not depend on `POSTHOG_FUNNELS_*` env vars.

**Evidence:** The same plan says the deployer currently carries duplicated PostHog/bootstrap logic and should stop owning hand-maintained inline bootstrap code.

**Evidence:** `metaFunnelEvents.ts` maps `presell_page_view` to `EnteredPresales`, `sales_page_view` to `PageView` and `EnteredSales`, `pre_sales_to_sales_click` to `PreSalesToSalesClick`, and `sales_to_checkout_click` to `SalesToCheckoutClick`.

**Evidence:** `posthog.ts` initializes a named `mosFunnel` instance, registers product/funnel/publication context, captures mapped Meta-compatible events, waits briefly for Meta cookies when needed, and adds Meta attribution props such as browser cookies/click IDs when available.

**Evidence:** `meta_conversions.py` resolves active Meta tracking from workspace Meta config, validates pixel consistency, hashes email/phone/external ID, builds Meta purchase payloads, and sends server-side purchase conversion events through Meta Ads client.

### Suspected causes

**Inference:** PostHog and Meta tracking are downstream of the MOS runtime event identity. If `pageId`/`publicationId` are wrong, PostHog and Meta may still receive client-side captures, creating a discrepancy where provider dashboards show events but MOS `funnel_events` is missing them.

**Inference:** Server-side Meta purchase events depend on Shopify order webhook metadata and active Meta workspace config. If checkout attribution is broken at the funnel-to-Shopify transition, server-side conversion quality will degrade even if browser events fire.

**Inference:** The earlier environment-based PostHog boundary can cause cross-workspace leakage or wrong host/key snapshots if the artifact was built with global env instead of workspace settings. The repository plan already identifies this as wrong boundary ownership.

### Affected files/functions

* `mos/backend/app/services/public_runtime_tracking.py`
* `mos/backend/app/routers/analytics.py`
* `mos/backend/app/schemas/analytics.py`
* `mos/backend/app/services/posthog_workspace_settings.py`
* `mos/backend/app/db/repositories/client_posthog_settings.py`
* `mos/backend/app/services/deploy.py`
* `mos/backend/cloudhand/adapters/deployer.py`
* `mos/frontend/src/lib/posthog.ts`
* `mos/frontend/src/lib/metaFunnelEvents.ts`
* `mos/frontend/src/lib/metaPixel.ts`
* `mos/backend/app/services/meta_conversions.py`
* `mos/backend/app/services/meta_account_configs.py`
* `mos/backend/tests/test_analytics.py`
* `mos/frontend/src/lib/posthog.test.ts`
* `mos/frontend/src/lib/metaFunnelEvents.test.ts`

### Remediation approach

#### 5.11.1 Complete workspace-owned PostHog cutover

The repository already contains the planned shape and partial implementation. Make the operational rule strict:

* workspace settings are the only runtime source;
* artifact generation snapshots workspace settings into page payload;
* deployer consumes page payload tracking only;
* no destination-server env fallback;
* no Meta metadata piggyback for PostHog host overrides.

#### 5.11.2 Provider capture consistency

For every tracked event chain, MOS should be the source of truth:

* internal `/public/events` must accept the event;
* PostHog capture should use the same `eventId` or mapped Meta event ID where appropriate;
* Meta Pixel event should use the same event ID as server-side conversion when deduplication is expected;
* provider calls should not be considered successful if internal ingestion fails during validation.

During production runtime, provider calls can remain best-effort. During validation, internal ingestion failure should fail the smoke.

#### 5.11.3 Meta server-side purchase audit

For Shopify purchase events:

* verify checkout metadata carries session ID, visitor ID, click IDs, `_fbp`, `_fbc`, event source URL, selected variant, selling plan, quantity, and transition ID;
* verify server-side conversion uses active workspace pixel config;
* verify pixel ID in active tracking metadata matches default workspace config;
* fail loudly when active tracking config is inconsistent.

The existing `meta_conversions.py` already raises on missing active pixel ID or inconsistent pixel config; preserve this fail-closed behavior.

#### 5.11.4 Avoid proxy-dependent browser tracking for standalone

For standalone imported HTML deployments, direct provider script URLs should be embedded when configured, and deploy validation should ensure the bootstrap does not point at stale MOS proxy placeholders. The deploy service already validates deployed HTML fragments for Meta/PostHog bootstrap in standalone mode; extend that to include runtime identity and internal ingestion response checks.

### Validation steps

* Save a workspace PostHog config and confirm public page payload includes it.
* Build standalone artifact and confirm tracking is snapshotted.
* Remove legacy PostHog env vars in a non-production environment and confirm artifact generation still includes workspace config.
* Browser smoke:

  * `presell_page_view` -> MOS event success, PostHog `EnteredPresales`, Meta `EnteredPresales`;
  * `pre_sales_to_sales_click` -> MOS success, PostHog/Meta mapped event;
  * `sales_page_view` -> MOS success, PostHog/Meta `PageView` and `EnteredSales`;
  * `sales_to_checkout_click` -> MOS success, PostHog/Meta mapped event.
* Server-side smoke:

  * controlled Shopify order webhook with test metadata produces expected server-side conversion payload;
  * no raw PII is logged;
  * hashes are generated as expected.

### Rollback considerations

If workspace-owned PostHog cutover fails, do not reintroduce indefinite env fallback. Use a one-time backfill or a clearly time-boxed migration flag. Long-lived dual-read behavior recreates the same ownership problem.

---

## 5.12 Shopify funnel app, checkout attribution, variant/bundle handling, and sales-page transitions

### Current evidence

**Evidence:** The deployment runbook says Shopify bridge integration is required for Shopify connection/product mapping/checkout and requires `SHOPIFY_APP_BASE_URL` plus `SHOPIFY_INTERNAL_API_TOKEN`. It recommends a local bridge listener for colocated production installs rather than routing server-to-server checkout traffic through the public app hostname.

**Evidence:** `shopify_checkout.py` validates Shopify variant GID format, validates optional selling-plan GID format, serializes metadata into checkout attributes, calls the Shopify bridge `/v1/checkouts`, handles timeout/request/HTTP errors, and requires `checkoutUrl` plus `cartId` in the response.

**Evidence:** `checkoutAttribution.ts` builds checkout attribution props from click IDs, `_fbp`, `_fbc`, event source URL, page variant, experiment ID, CTA ID, and transition ID. It also appends checkout attributes to `/cart/` URLs and preserves checkout tracking URL params such as UTMs and click IDs.

**Evidence:** Standalone imported HTML tests cover prepared checkout reuse, purchase-mode inclusion in checkout selection, checkout timing props, and selected option values for pack/flavor.

### Suspected causes

**Inference:** Bundle failures can occur at several boundaries:

* imported HTML selector does not uniquely resolve selected pack/flavor;
* selected values do not match `ProductVariant.option_values`;
* purchase mode is not included or mismatches selling plan expectations;
* `ProductVariant` row is missing Shopify variant GID or selling plan ID;
* prepared checkout cache uses a key that does not include all selection dimensions;
* bridge env points to an unreachable or wrong Shopify app;
* final checkout URL loses attribution query params or cart attributes.

**Inference:** The checkout bridge code correctly fails closed for invalid variant/selling-plan GIDs, so a visible 409/502/504 is preferable to silently sending shoppers to a wrong bundle.

### Affected files/functions

* `mos/backend/app/services/shopify_checkout.py`
* `mos/frontend/src/lib/checkoutAttribution.ts`
* `mos/frontend/src/funnels/StandaloneImportedHtmlPage.tsx`
* `mos/frontend/src/funnels/importedHtmlRuntime.ts`
* `mos/backend/app/routers/public_funnels.py`

  * public checkout/prepare endpoints if present in full file
* `shopify-funnel-app`

  * checkout creation endpoint
  * webhook handler
* Product/variant models and repositories
* `mos/frontend/src/funnels/StandaloneImportedHtmlPage.test.tsx`

### Remediation approach

#### 5.12.1 Variant resolver hard validation

For imported HTML checkout bindings:

* selector must match exactly one element when marked required;
* extracted option names must match the configured product option names;
* extracted values must match one and only one variant;
* purchase mode must be included when subscription/selling plan is possible;
* mismatch returns a visible validation error in smoke, not a fallback variant.

#### 5.12.2 Prepared checkout cache key

Cache key must include:

* product slug;
* funnel slug;
* publication ID;
* page ID;
* binding ID;
* variant ID or option-value selection;
* purchase mode;
* selling plan ID;
* quantity;
* attribution transition ID where needed.

Do not reuse a prepared checkout across different bundles or purchase modes.

#### 5.12.3 Checkout metadata contract

Checkout metadata should include:

* visitor ID;
* session ID;
* publication ID;
* page ID;
* page slug;
* page stage;
* funnel ID;
* product slug;
* funnel slug;
* transition ID;
* CTA ID;
* selected offer;
* variant IDs;
* selling plan ID;
* UTMs;
* click IDs;
* `_fbp`/`_fbc` where available;
* event source URL.

The server should reject overlarge or malformed metadata rather than truncating silently.

#### 5.12.4 Sales-page transition instrumentation

For sales-page CTAs:

* emit `sales_to_checkout_click`;
* emit `checkout_click`;
* emit `checkout_redirect_started`;
* emit `checkout_pagehide`/`checkout_visibility_hidden` when applicable;
* preserve query params into checkout/cart URL;
* mark checkout timing props with transition ID.

The migration `0091` adds event types for timing diagnostics, so runtime and ingestion should use them consistently.

### Validation steps

* Unit tests:

  * invalid variant GID returns 409;
  * invalid selling plan GID returns 409;
  * Shopify bridge timeout returns 504;
  * bridge error returns controlled detail;
  * missing checkout URL/cart ID returns 502.
* Frontend tests:

  * selected pack/flavor maps to expected variant;
  * purchase mode included;
  * attribution props include UTMs/click IDs;
  * prepared checkout reused only for same selection.
* End-to-end smoke:

  * click sales CTA;
  * verify MOS events before navigation;
  * verify checkout URL contains expected attribution;
  * verify Shopify order webhook produces purchase attribution.

### Rollback considerations

Rollback should not point all checkout buttons to a generic product or fallback variant. If bundle resolution is unsafe, the safer rollback is to disable the affected CTA or return a controlled “checkout unavailable” message until the variant mapping is fixed.

---

## 5.13 Artifact host nginx configuration and release directory management

### Current evidence

**Evidence:** The deployer writes standalone artifact releases under `site-releases/<timestamp>` for standalone imported HTML, then atomically activates the release by symlinking `site` to the built release.

**Evidence:** The deployer generates nginx configs with a static root, asset caching routes, `/api/` proxying to the upstream API origin, optional root redirect for standalone imported HTML, and `try_files $uri $uri/index.html $uri/ =404` for static pages. It runs `nginx -t` and reloads nginx.

**Evidence:** The operational artifact summary shows active `brand-funnels-*` nginx sites, high-port listeners, static roots under `/opt/apps/brand-funnels-.../site`, upstream API proxying, and root redirects to sales pages for current Tenor standalone deployments.

**Evidence:** The artifact host has accumulated multiple Tenor tarballs, generated HTML files, direct patch scripts, backups, and release artifacts in root temp storage.

### Suspected causes

**Inference:** Release directories appear to be retained without a strict pruning/manifest policy. That is useful for rollback in the short term but becomes risky when accumulated size is large and operators cannot identify which release is active or valid.

**Inference:** The nginx root redirect to sales-page may be generated by code, not a manual mistake. However, the artifact summary showing root redirects should be treated as a deployment property to verify against the desired funnel entry policy.

**Inference:** Direct patch scripts on the artifact host can mutate active release files without updating the release directory manifest, making symlink rollback unreliable.

### Affected files/functions

* `mos/backend/cloudhand/adapters/deployer.py`

  * `_configure_funnel_artifact_site`
  * `_activate_funnel_artifact_site_release`
  * `_write_funnel_artifact_standalone_html_routes`
  * nginx config generation
* `/etc/nginx/sites-available/brand-funnels-*`
* `/etc/nginx/sites-enabled/brand-funnels-*`
* `/opt/apps/brand-funnels-*/site`
* `/opt/apps/brand-funnels-*/site-releases`
* deploy scratch directory on bridge/artifact host

### Remediation approach

#### 5.13.1 Release manifest and immutability

Every release directory must contain:

```text
mos-release-manifest.json
```

Fields:

* release ID;
* built at;
* deployed by;
* deploy job ID;
* source commit;
* artifact ID/version;
* render mode;
* product slug;
* funnel slug/token;
* funnel ID;
* publication ID;
* page ID/slug/stage list;
* root redirect target;
* upstream API origin;
* tracking provider config presence flags, not secrets;
* bridge version;
* static scan result;
* validation result.

After activation, release directories should be treated read-only. Any emergency patch should create a new release directory, not edit the active one in place.

#### 5.13.2 Nginx config manifest alignment

Generated nginx config should include comments with non-secret release identity:

```nginx
# MOS workload: brand-funnels-...
# MOS release: ...
# MOS artifact: ...
# MOS publication: ...
# MOS render_mode: standalone_imported_html
```

The active nginx config root should match the active `site` symlink. If nginx points to a direct release directory, that should be flagged as drift.

#### 5.13.3 Release pruning policy

Implement a safe retention policy:

* keep last 10 releases per workload;
* keep all releases from last 7 days;
* keep any release explicitly marked `pinned`;
* never delete the active `site` target;
* write a pruning log.

Do not run pruning during incident evidence capture. First archive metadata.

#### 5.13.4 Static host health checks

Add a per-workload static health endpoint file:

```text
/.mos/release.json
```

It can expose the manifest subset safe for public access:

* release ID;
* artifact version;
* publication ID;
* page slugs;
* build timestamp.

This supports smoke tests without SSH.

### Validation steps

* `nginx -t` must pass.
* `curl` root must redirect to expected explicit route.
* `curl` every page route must return 200.
* `curl /api/public/events` through artifact host proxy must reach the API and preserve host headers.
* `curl /.mos/release.json` returns current release metadata.
* Active `site` symlink target exists and contains manifest.
* No active release contains forbidden legacy quiz source strings.

### Rollback considerations

Rollback procedure:

1. Capture current symlink target and nginx config.
2. Select prior release by manifest, not timestamp guess.
3. Verify prior release route files and identity.
4. Atomically repoint `site` symlink.
5. Run `nginx -t`.
6. Reload nginx only after authorization.
7. Smoke exact public routes.
8. Record rollback manifest.

Do not delete the failed release until analysis is complete.

---

## 5.14 Bridge host systemd services and environment contract

### Current evidence

**Evidence:** The deployment runbook says backend API and Temporal worker share the same env/secrets, Postgres and Temporal are required, Clerk JWT settings are required, and Shopify bridge settings are required for checkout. It also states secrets should move to a deployment secret manager and `.env` files should stay out of images/artifacts.

**Evidence:** The README lists deploy-related runtime configuration, including `DEPLOY_ROOT_DIR`, `DEPLOY_PROJECT_ID`, public base URLs, Hetzner token, Bunny config, and Namecheap config. It warns that plan files can contain sensitive environment values and must be treated as sensitive deployment state.

**Evidence:** Journal snippets show expired Clerk JWT verification failures around the incident window.

**Evidence:** The operational context states production-like app checkouts on the bridge host are dirty, detached, and contain backup/patch files.

### Suspected causes

**Inference:** The bridge host is carrying too much mutable state:

* checked-out repo copies;
* env files;
* deploy root/plan state;
* job files;
* temporary artifacts;
* SSH/deploy credentials;
* possibly service-specific manual backups.

**Inference:** Expired JWT failures may be normal user/session churn, but they can obscure more important deploy/publish logs if not filtered and categorized.

**Inference:** The systemd/env contract may be under-documented for the split between:

* backend API;
* Temporal worker;
* frontend static app;
* Shopify bridge app;
* Cloudhand deploy runtime;
* artifact-host SSH credentials;
* PostHog/Meta workspace settings.

### Affected areas

* backend API systemd or compose service;
* Temporal worker systemd or compose service;
* Shopify bridge service;
* nginx reverse proxy service;
* deploy root;
* `.env.production`;
* systemd unit files;
* journal logs;
* Cloudhand SSH material;
* CI/CD secrets.

### Remediation approach

#### 5.14.1 Document env contract by service

Create a checked-in operational document:

```text
docs/ops/service-env-contract.md
```

For each service, list:

* required env var names;
* owner;
* source of truth;
* whether secret;
* allowed values or format;
* restart requirement;
* validation command.

Do not include values.

Service groups:

* MOS backend API;
* MOS worker;
* frontend build/runtime;
* Shopify bridge;
* Cloudhand deploy;
* artifact host nginx;
* provider integrations;
* observability.

#### 5.14.2 Add startup env validation

Backend startup should validate required env by feature gate:

* core API requires DB, Clerk, CORS, Temporal;
* deploy features require Cloudhand deploy env;
* Shopify checkout requires bridge URL/token;
* provider features require their provider configs.

Use clear startup warnings for disabled optional integrations and hard failures for required production integrations. Do not silently fall back to placeholder config in production.

#### 5.14.3 Service identity logging

At startup, each service should log:

* service name;
* source commit/image tag;
* environment name;
* migration head;
* deploy root path name only;
* enabled feature flags;
* no secret values.

#### 5.14.4 Separate deploy scratch from runtime

Move deploy scratch and evidence artifacts into controlled directories:

* `/var/lib/mos/deploy-state` for plans/jobs/artifacts;
* `/var/log/mos/deploy` for logs;
* `/var/lib/mos/evidence/<timestamp>` for incident capture;
* no root home temp accumulation.

Enforce permissions so only deploy user/service can read sensitive state.

### Validation steps

* `systemctl cat` or compose config shows expected service commands and env-file paths.
* `journalctl` startup logs include commit/image tag and migration head.
* backend `/health` and `/health/db` pass.
* worker connects to Temporal and task queue.
* Shopify bridge health endpoint passes from backend host.
* deploy root permissions prevent non-deploy users from reading plan files.
* no env files or secrets are present in static artifact releases.

### Rollback considerations

Env contract changes should be deployed with a compatibility window. New hard failures must be introduced behind production-readiness checks so an existing service does not fail restart due to an optional integration that is not yet configured. For required production paths such as DB, Clerk, and Shopify checkout, fail closed.

---

## 5.15 Tests, previews, authenticated validation, and smoke tests

### Current evidence

**Evidence:** CI runs backend migrations and tests, builds frontend, and builds images.

**Evidence:** The deployment runbook lists verification steps: health checks, backend tests, frontend build, migration head, Temporal checks, API smoke with real Clerk JWT, frontend sign-in smoke, and SPA route smoke.

**Evidence:** Existing frontend tests cover public funnel page rendering in standalone bundle mode, imported HTML page paths, PostHog events, wildcard routes, standalone imported HTML checkout preparation, Klaviyo capture, RMBC diagnostic events, Meta, and PostHog.

**Evidence:** Deploy service includes post-deploy tracking validation with Playwright, expected internal events, expected Meta events, expected PostHog events, HTML bootstrap validation, and provider event validation.

### Suspected causes

**Inference:** Existing tests are strong on browser-side event emission but insufficient on database acceptance of the exact generated page/publication IDs. The observed FK violation would pass a browser event-name test but fail when the event hits the real DB.

**Inference:** Smoke tests currently need real Clerk JWTs for authenticated API paths. The excluded raw script with hard-coded JWT material indicates operators may have used persistent secrets for smoke or deploy actions. That needs replacement with short-lived operator tokens or CI environment approvals.

### Affected files/functions

* `.github/workflows/docker-images.yml`
* `docs/deployment-runbook.md`
* `mos/backend/tests`
* `mos/frontend/src/**/*.test.ts(x)`
* `mos/backend/app/services/deploy.py`

  * post-deploy tracking validation
* `scripts/check_github_actions.py`
* `scripts/check_spa_routes.py`
* `mos/backend/SMOKE_TESTS.md`

### Remediation approach

#### 5.15.1 Add identity acceptance tests

Backend tests must cover:

* artifact payload identity audit;
* public event ingestion accepts generated IDs;
* public event ingestion rejects stale page IDs cleanly;
* duplicate event ID idempotency;
* invalid event type rejection;
* preview event no-op behavior.

#### 5.15.2 Add standalone artifact golden fixture

Create a fixture with:

* product;
* funnel;
* publication;
* quiz page;
* sales page;
* commerce variants;
* tracking config;
* imported HTML manifest.

Use it to test:

* artifact payload generation;
* static route rendering;
* nginx config generation in dry-run;
* event ingestion preflight;
* root redirect policy;
* forbidden legacy string scan.

#### 5.15.3 Add authenticated deploy dry-run

Create an authenticated dry-run validation command that does not apply infrastructure:

```text
python -m scripts.validate_standalone_funnel_deploy \
  --funnel-id <id> \
  --publication-id <id> \
  --render-mode standalone_imported_html \
  --no-apply
```

The command should:

* build artifact payload;
* run identity audit;
* render static artifact locally or in temp directory;
* run static scan;
* validate event ingestion preflight;
* output a manifest.

Do not require long-lived JWTs embedded in scripts. Use local operator auth flow or CI OIDC/approved environment secrets.

#### 5.15.4 Smoke test matrix

Minimum Tenor quiz smoke before production approval:

* static scan: no legacy source domains/scripts;
* route smoke: quiz route 200, sales route 200, root expected redirect;
* event smoke: quiz lead, question selected, quiz completed, CTA viewed, pre-sales-to-sales click;
* handoff smoke: sales URL contains stitch params;
* sales attribution smoke: sales page event has `fromPresale`;
* checkout smoke: selected bundle maps to expected variant;
* provider smoke: PostHog and Meta captures observed in validation trap;
* DB smoke: `funnel_events` contains expected event chain with exact page/publication IDs.

### Validation commands

Use repository-standard commands first:

```bash
cd mos/backend
.venv/bin/alembic upgrade head
.venv/bin/pytest
```

```bash
cd mos/frontend
npm ci
npm run build
npm test -- --run
```

Deploy dry-run commands should be added as part of remediation; do not invent that they already exist.

### Rollback considerations

Tests should block deploys, not repair them. If production smoke fails after activation, use manifest rollback or disable traffic at routing layer only after explicit authorization. Avoid test scripts that mutate production state as a side effect.

---

## 5.16 Observability, logging, alerting, and runbooks

### Current evidence

**Evidence:** The deployment runbook lists Langfuse observability env variables and operational verification checks.

**Evidence:** Journal evidence captured raw unhandled server exceptions for SQLAlchemy integrity failures and expired JWT failures.

**Evidence:** Deploy jobs write status files with phases such as publishing, artifact hydrated, plan patched, applying, reconciling Bunny, purging cache, validating tracking, and completed/failed. The deploy service stores job status and errors in JSON job files.

### Suspected causes

**Inference:** Logs currently expose the symptom but not enough structured identity context to diagnose quickly. A `page_id_fkey` violation says the page ID is invalid, but the operator also needs artifact ID, release ID, deploy job ID, route, page slug, and publication-page membership result.

**Inference:** Expired JWT noise should be separated from deploy/runtime errors. Otherwise, auth churn can hide production event ingestion failures.

### Affected files/functions

* `mos/backend/app/routers/public_funnels.py`
* `mos/backend/app/services/deploy.py`
* `mos/backend/cloudhand/adapters/deployer.py`
* backend logging config
* systemd/journal config
* deployment runbooks
* post-deploy validation scripts
* alerting integration

### Remediation approach

#### 5.16.1 Structured event-ingestion logging

For every rejected public event batch, log:

* reason code;
* publication ID;
* page ID;
* event type;
* event ID;
* product/funnel path if available;
* host/path;
* artifact/release IDs if present in props;
* no raw PII;
* no full user agent unless needed and sampled.

Use warning level for validation rejections and error level for unexpected exceptions.

#### 5.16.2 Deploy phase metrics

Emit metrics or structured logs for:

* publish started/succeeded/failed;
* artifact generated;
* identity audit passed/failed;
* plan patched;
* apply started/succeeded/failed;
* nginx test passed/failed;
* tracking validation passed/failed;
* rollback started/succeeded/failed.

#### 5.16.3 Alerts

Minimum alert set:

* `/public/events` 5xx rate above threshold;
* `funnel_events_page_id_fkey` appears in logs;
* deploy job failed in `applying_plan` or `validating_tracking`;
* artifact host disk usage above threshold;
* active release missing manifest;
* nginx config test failure;
* PostHog/Meta validation missing expected events;
* checkout bridge 5xx/timeout spike.

#### 5.16.4 Runbooks

Create runbooks:

* `docs/runbooks/standalone-funnel-deploy.md`
* `docs/runbooks/public-events-fk-violation.md`
* `docs/runbooks/standalone-artifact-rollback.md`
* `docs/runbooks/shopify-checkout-attribution.md`
* `docs/runbooks/posthog-meta-tracking-validation.md`
* `docs/runbooks/secret-exposure-response.md`

The FK violation runbook should start with evidence capture and identity audit, not DB constraint changes.

### Validation steps

* Inject a controlled invalid page ID in staging and verify:

  * 422 response;
  * structured log with reason;
  * no unhandled traceback;
  * alert fires only in staging test channel.
* Run a failed deploy validation and confirm job status includes failed phase and actionable error.
* Run disk usage alert simulation for artifact release directory.
* Confirm runbooks contain no secrets or public infrastructure IPs.

### Rollback considerations

Observability changes should be safe to roll forward. Avoid logging raw payload bodies because analytics props can include sensitive or campaign-specific information. If logs become too verbose, reduce sampling, not identity fields needed for incident diagnosis.

---

## 5.17 Secrets, credential hygiene, synthetic/fake data governance, and operational permissions

### Current evidence

**Evidence:** The deployment runbook says secrets live in `.env` locally, should move to a deployment secret manager, and should be kept out of images/artifacts.

**Evidence:** README warns plan files can contain sensitive environment values and are stored under `DEPLOY_ROOT_DIR`, so that directory must be treated as sensitive deployment state.

**Evidence:** The sanitized context says a raw script with hard-coded auth/JWT material was intentionally excluded from attachments and must be treated as a secret-hygiene risk.

**Evidence:** Root temp context lists deploy-related key files and many patch artifacts in operational scratch locations.

**Evidence:** Deploy RBAC is documented as not scoped to admin/operator roles; any authenticated org member can call deploy routes.

### Suspected causes

**Inference:** Emergency recovery likely encouraged storing short-term credentials, JWTs, SSH material, and patch scripts in convenient local files. Even if not committed, that creates leakage risk through shell history, backups, temp directories, file uploads, and copied artifacts.

**Inference:** Synthetic/fake data governance matters because funnel pages may include AI-generated testimonials, PDP examples, quiz answers, and generated imagery. Recovery should ensure validation events and synthetic smoke orders are clearly marked so they do not pollute analytics or customer reporting.

### Affected files/areas

* `.env`, `.env.production`, `.env.local`, service env files
* `DEPLOY_ROOT_DIR`
* root temp/scratch artifacts
* GitHub Actions secrets and variables
* Cloudhand plan files
* excluded hard-coded auth/JWT script
* Shopify internal token
* provider API keys
* deploy SSH credentials
* generated standalone artifacts
* synthetic/test event props

### Remediation approach

#### 5.17.1 Immediate secret hygiene

Do not ask for or inspect secret values. Instead:

1. Inventory secret locations by filename/path class only.
2. Identify any secrets that may have been copied into:

   * uploaded attachments;
   * root temp files;
   * deploy plan files;
   * patch scripts;
   * shell history;
   * static artifacts;
   * CI logs.
3. Rotate credentials that were present in excluded raw scripts or insecure scratch paths.
4. Delete or quarantine hard-coded credential scripts after rotation.
5. Replace hard-coded JWT smoke scripts with short-lived token acquisition or approved operator flow.

#### 5.17.2 Plan-state protection

* Restrict deploy root permissions.
* Encrypt or avoid storing secret env values in plan JSON.
* Store secret references, not secret values, where possible.
* Add static scan for secret-like patterns before artifact persistence.
* Prevent plan files from being served by nginx.

#### 5.17.3 Deploy permission model

Add explicit authorization checks:

* deploy read: admin/ops;
* plan save: admin/ops;
* workload patch: admin/ops;
* apply: admin only or ops with production environment approval;
* publish without deploy: existing workspace permission;
* publish with deploy: deploy permission required.

Transport-level loopback proxy check remains useful but insufficient.

#### 5.17.4 Synthetic/test data marking

Every validation event should include:

```json
{
  "validation": true,
  "validationRunId": "...",
  "environment": "staging|production-smoke",
  "excludeFromReporting": true
}
```

For production smoke events, decide whether to retain or exclude before the smoke. The Tenor quiz plan lists this as an open decision.

AI-generated testimonials or PDP examples should be marked according to existing synthetic flags and should not be presented as real customer evidence unless approved and compliant.

### Validation steps

* Secret scan repository, deploy plans, generated artifacts, and scratch directory metadata.
* Confirm no `.env` files are inside images/artifacts.
* Confirm deploy API rejects non-operator authenticated users.
* Confirm CI logs do not print secret values.
* Confirm validation events carry `validationRunId`.
* Confirm reporting filters exclude validation events where intended.

### Rollback considerations

Secret rotation can break integrations. Rotate in controlled order:

1. add new secret;
2. deploy config referencing new secret;
3. validate integration;
4. revoke old secret;
5. scan logs/artifacts for old secret fingerprints if safe to do so without printing values.

Do not roll back to old compromised credentials.

---

## 5.18 Part 2 operational remediation checklist

This checklist covers only the modules analyzed in Part 2.

### Code changes

* Add artifact identity audit helper:

  * `mos/backend/app/services/deploy.py`
  * new tests under `mos/backend/tests/test_deploy_artifact_identity.py`
* Add event ingestion validation:

  * `mos/backend/app/routers/public_funnels.py`
  * `mos/backend/tests/test_public_events_ingestion.py`
* Add explicit default route policy:

  * `mos/backend/app/schemas/funnels.py`
  * `mos/backend/app/services/deploy.py`
  * `mos/backend/cloudhand/adapters/deployer.py`
  * frontend deploy UI/API payload types
* Add release manifest writing:

  * `mos/backend/cloudhand/adapters/deployer.py`
  * `mos/backend/app/services/deploy.py`
* Centralize standalone bridge:

  * extract from `mos/backend/cloudhand/adapters/deployer.py`
  * reuse/build from frontend source or a dedicated bridge asset
* Add Tenor quiz static scan:

  * new backend service or deploy validation helper
  * test fixture with forbidden strings
* Add deploy RBAC:

  * `mos/backend/app/routers/deploy.py`
  * auth dependency or permission helper
* Add event validation observability:

  * structured logs in public event ingestion
  * deploy job phase logs
* Add secret scans and deploy plan permission checks:

  * scripts under `scripts/`
  * CI job or preflight command

### Test commands

```bash
cd mos/backend
.venv/bin/alembic upgrade head
.venv/bin/pytest
```

```bash
cd mos/frontend
npm ci
npm run build
npm test -- --run
```

Add new commands during implementation:

```bash
python -m scripts.validate_standalone_funnel_artifact --fixture tenor-quiz --no-apply
```

```bash
python -m scripts.scan_static_artifact --path <artifact-dir> --profile tenor-quiz
```

These commands are proposed remediation items, not confirmed existing scripts.

### Acceptance criteria for Part 2 scope

* A generated standalone artifact cannot be persisted if any page ID is invalid.
* Public event ingestion returns clean validation errors for invalid page IDs.
* Root redirect policy is explicit and test-covered.
* The Tenor quiz route can be made the entry/default route without relying on sales-page preference.
* Standalone bridge source is no longer hand-maintained in two divergent places.
* Checkout bundle selection fails closed on ambiguity.
* Artifact release directories contain non-secret manifests.
* Deploy API infrastructure mutation requires operator/admin permission.
* No hard-coded JWT/deploy credentials remain in scripts.
* Production smoke events are clearly marked.

Continue in Part 3.


## 6. Recovery plan

This section is an operational recovery plan, not a production-change authorization. Every step that reads, snapshots, validates, or prepares code is allowed as analysis/preparation. Every step that deploys, restarts, reloads, changes nginx, changes symlinks, mutates production DB rows, purges CDN, rotates production credentials, or changes production traffic requires an explicit human authorization gate.

### Evidence baseline for the recovery plan

**Evidence:** The repository already has a documented normal production path: CI/CD runs backend tests and Alembic migrations, builds the frontend, builds/pushes images, and the deployment runbook describes post-push verification with `scripts/check_github_actions.py --sha HEAD --wait --expect-production`.

**Evidence:** The README documents deploy integration gaps that directly matter for recovery: deploy RBAC is not scoped to operators, the proxy-only restriction is transport-level, no deploy queue/lock exists, concurrent applies can race shared plan/state artifacts, and plan files can contain sensitive env values.

**Evidence:** The standalone Tenor quiz plan requires a first-party MOS-managed pre-sales page, removal of legacy Mars/Heyflow dependencies, a same-origin funnel route, MOS/RMBC event emission, final handoff to the sales page, and an explicit production gate before deployment.

**Evidence:** The attached operational journal shows `funnel_events_page_id_fkey` violations for standalone HTML runtime events carrying a `publication_id`, `page_id`, pre-sales path, and `artifactMode: standalone_html`.

**Inference:** The safest recovery path is to stop treating the artifact host as a place to repair content directly. The durable fix belongs in repository code, artifact generation, deploy validation, event-ingestion validation, and release manifests.

---

## 6.1 Phase 0 — Freeze, evidence capture, and authorization boundaries

### Objective

Prevent additional state corruption and preserve enough evidence to identify exactly which source, artifact, release, runtime config, and database publication/page rows produced the observed Tenor standalone failures.

### Hard boundary

No deploy, restart, nginx reload, CDN purge, DB mutation, direct static patch, symlink switch, credential rotation, or production smoke that writes events should happen in Phase 0 without explicit authorization.

### Phase 0 actions

#### 0.1 Freeze mutation paths

* Disable or pause any ad hoc hotfix workflow that can patch artifact-host files directly.
* Do not run `apply_plan`, `publish+deploy`, direct SSH patch scripts, or manual nginx edits.
* Do not delete old release directories, tarballs, or patch scripts yet.
* Do not “clean up” dirty checkouts before capturing their state.

**Evidence:** A separate Tenor hotfix path exists in the bundle and the operational context includes many direct patch artifacts. The normal runbook already defines a repo/CI path, so emergency patching should not remain the default.

#### 0.2 Capture bridge host service state

Capture the following for each bridge-host service directory and runtime service:

```bash
pwd
git rev-parse --show-toplevel
git rev-parse HEAD
git status --short
git branch --show-current || true
git describe --always --dirty || true
git remote -v
```

For services:

```bash
systemctl list-units --type=service --all | grep -E 'mos|shopify|temporal|nginx' || true
systemctl status <service-name> --no-pager
systemctl cat <service-name>
```

Capture only env file paths and env variable names, not values:

```bash
systemctl show <service-name> -p Environment -p EnvironmentFiles
```

Do not print secrets.

#### 0.3 Capture artifact host release state

For each active standalone workload:

```bash
readlink -f /opt/apps/<workload>/site
find /opt/apps/<workload>/site-releases -maxdepth 1 -mindepth 1 -type d -printf '%TY-%Tm-%TdT%TH:%TM:%TS %p\n' | sort
du -sh /opt/apps/<workload> /opt/apps/<workload>/site /opt/apps/<workload>/site-releases 2>/dev/null
find /opt/apps/<workload>/site -maxdepth 4 -type f \( -name 'index.html' -o -name '*.json' \) | sort | head -200
```

For nginx:

```bash
nginx -T 2>/tmp/nginx-full-config.txt
ls -l /etc/nginx/sites-enabled
ls -l /etc/nginx/sites-available
```

Do not include public IPs in the final incident report. Replace infrastructure-specific host/IP values with “artifact host,” “bridge host,” “mOS API,” or equivalent labels.

#### 0.4 Capture deploy state

Capture:

* latest deploy plan path names;
* job JSON file names;
* publish job status JSON;
* artifact IDs/versions;
* workload names;
* plan modified timestamps;
* no secret values.

Do not attach raw plan files until they are redacted, because README explicitly warns plan files can contain sensitive env values.

#### 0.5 Capture database identity for affected funnel

Read-only queries only:

* affected funnel row;
* product row and route slug;
* active publication row;
* publication pages;
* funnel pages;
* page versions;
* page IDs embedded in current artifact HTML/config;
* recent `funnel_events` rows and failures by publication/page ID.

Do not update rows. Do not delete failed events. Do not create replacement pages yet.

#### 0.6 Capture public behavior without mutation

Allowed read-only checks:

```bash
curl -I <public-root-url>
curl -I <public-quiz-route>
curl -I <public-sales-route>
curl -s <public-route> | grep -E 'MOS_STANDALONE|publicationId|pageId|posthog|fbevents' | head
```

Avoid test interactions that emit production analytics until validation-event handling exists or explicit authorization is granted.

### Phase 0 exit criteria

* Current bridge host source state captured.
* Current artifact host symlink/nginx/release state captured.
* Current deploy plan/job/artifact metadata captured.
* Current database publication/page identity captured.
* No new production mutation performed.
* A human can answer:

  * active release directory;
  * active nginx config;
  * active publication ID;
  * page IDs embedded in current release;
  * whether embedded page IDs exist in DB;
  * whether current release has known provenance.

---

## 6.2 Phase 1 — Stop-the-bleeding changes to make current production understandable and prevent new corruption

### Objective

Introduce guardrails that prevent further unidentified artifacts, concurrent deploy races, and invalid event-ingestion crashes. Phase 1 should be code-first and can be deployed only after review.

### Phase 1 changes

#### 1.1 Add deploy lock

**Files:**

* `mos/backend/app/services/deploy.py`
* new: `mos/backend/app/services/deploy_locks.py`
* tests: `mos/backend/tests/test_deploy_locks.py`

**Behavior:**

* Acquire lock by `(plan_path, workload_name)` before `patch_workload_in_plan`, `apply_plan`, and publish job deploy section.
* Lock metadata should include job ID, actor user ID, org ID, workload, started timestamp.
* If lock exists and is not stale, fail with a clear `DeployError`.
* Stale-lock override requires an explicit operator-only path and should not be silent.

**Evidence:** The README documents that no deploy queue/lock exists and concurrent applies can race shared plan/state artifacts.

#### 1.2 Add deploy RBAC

**Files:**

* `mos/backend/app/routers/deploy.py`
* `mos/backend/app/auth/dependencies.py` or a new permission helper
* tests: `mos/backend/tests/test_deploy_authz.py`

**Behavior:**

* `GET /deploy/plans/latest`: admin/ops.
* `POST /deploy/plans`: admin/ops.
* `POST /deploy/plans/workloads`: admin/ops.
* `POST /deploy/plans/apply`: admin only or ops with explicit deploy permission.
* `POST /deploy/apply`: same as apply.

Do not rely on `_require_internal_proxy` as a policy boundary. Keep it, but add role/permission checks.

**Evidence:** Deploy routes currently require Clerk auth and a loopback proxy check, but README says RBAC is not scoped to admin/operator roles and proxy-only restriction is transport-level.

#### 1.3 Add structured event-ingestion validation

**Files:**

* `mos/backend/app/routers/public_funnels.py`
* `mos/backend/app/schemas/funnels.py`
* tests: `mos/backend/tests/test_public_events_ingestion.py`

**Behavior:**

* Validate publication exists.
* Validate `pageId` exists.
* Validate `pageId` belongs to the publication.
* Validate event type before insert.
* Validate duplicate `eventId` as idempotent.
* Return structured 422 for invalid page/publication relationships instead of allowing an unhandled FK exception.

**Evidence:** `PublicEventIn` includes `publicationId` and `pageId`, and `FunnelEvent` stores `page_id` as a FK to `funnel_pages`; the incident evidence shows a `funnel_events_page_id_fkey` failure for standalone runtime events.

#### 1.4 Add release manifest for new artifacts

**Files:**

* `mos/backend/cloudhand/adapters/deployer.py`
* `mos/backend/app/services/deploy.py`
* tests: `mos/backend/tests/test_cloudhand_deployer_release_manifest.py`

**Behavior:**

Each release directory gets:

```text
mos-release-manifest.json
```

Include no secrets. Include:

* deploy job ID;
* source commit if available;
* artifact ID/version;
* render mode;
* product slug;
* funnel token;
* funnel ID;
* publication ID;
* pages: `pageId`, slug, stage;
* default route target;
* upstream API origin host label, not secret;
* tracking provider flags;
* bridge version;
* static scan status.

#### 1.5 Disable direct artifact patching as a routine path

**Files:**

* `.github/workflows/tenor-tracking-hotfix.yml`
* docs: `docs/runbooks/standalone-funnel-emergency-hotfix.md`

**Behavior:**

* Either remove the workflow, restrict it to `workflow_dispatch` with production environment approval, or convert it to a read-only evidence collector.
* If emergency mutation remains possible, it must:

  * snapshot current release;
  * create a new release directory;
  * write a manifest;
  * run static scan;
  * require approval;
  * never edit active files in place.

### Phase 1 exit criteria

* New deploy operations cannot run concurrently against the same workload/plan.
* Non-operator users cannot mutate deploy plans or apply.
* Invalid public event page IDs return clean validation errors, not DB tracebacks.
* New releases have manifests.
* Direct hotfix path is disabled, restricted, or documented as emergency-only.

---

## 6.3 Phase 2 — Code fixes

### Objective

Fix the actual system boundaries: artifact identity, standalone bridge drift, root redirect policy, PostHog ownership, checkout identity, and validation.

### Phase 2 code fix groups

#### 2.1 Artifact identity audit

**Files:**

* `mos/backend/app/services/deploy.py`
* new: `mos/backend/app/services/funnel_artifact_identity.py`
* tests: `mos/backend/tests/test_funnel_artifact_identity.py`

**Implement:**

```python
def validate_funnel_artifact_identity(
    *,
    session,
    org_id: str,
    client_id: str,
    artifact_payload: dict[str, Any],
    expected_funnel_id: str,
    expected_publication_id: str,
) -> FunnelArtifactIdentityReport:
    ...
```

Checks:

* artifact has `meta.updatedFromFunnelId`;
* artifact has `meta.updatedFromPublicationId`;
* expected funnel exists;
* expected publication exists;
* publication belongs to expected funnel;
* every artifact page ID exists in `funnel_pages`;
* every artifact page ID belongs to expected funnel;
* every artifact page ID belongs to expected publication;
* every `pageMap` key is in publication pages;
* every `pageStageMap` key is in `pageMap`;
* every route slug is non-empty and slash-free;
* no duplicate canonical page slug.

Call this:

* after `build_client_funnel_runtime_artifact_payload`;
* before `persist_client_funnel_runtime_artifact`;
* before plan patch in `_run_funnel_publish_job`;
* before post-deploy validation.

#### 2.2 Explicit default route policy

**Files:**

* `mos/backend/app/schemas/funnels.py`
* `mos/backend/app/services/deploy.py`
* `mos/backend/cloudhand/adapters/deployer.py`
* `mos/frontend/src/api/funnels.ts`
* UI publish form if present
* tests:

  * `mos/backend/tests/test_cloudhand_deployer_funnel_proxy.py`
  * `mos/frontend/src/pages/research/funnels/funnelPublicUrls.test.ts`

**Add fields:**

```python
defaultRoutePolicy: Literal["entry_page", "sales_page", "explicit_slug", "none"] = "entry_page"
defaultPageSlug: Optional[str] = None
```

**Behavior:**

* `entry_page`: use publication entry.
* `sales_page`: use current behavior only when explicitly requested.
* `explicit_slug`: require `defaultPageSlug` and verify route exists.
* `none`: no nginx root redirect.

For Tenor quiz, the default must be `entry_page` after setting quiz as entry, or `explicit_slug: "quiz-v6"`.

#### 2.3 Event-ingestion idempotency and validation

**Files:**

* `mos/backend/app/routers/public_funnels.py`
* `mos/backend/app/db/repositories/funnel_events.py` if repository exists or add one
* tests: `mos/backend/tests/test_public_events_ingestion.py`

**Implement response shape:**

```json
{
  "ok": true,
  "ingested": 3,
  "deduped": 1,
  "rejected": 0,
  "errors": []
}
```

For validation failure:

```json
{
  "ok": false,
  "ingested": 0,
  "deduped": 0,
  "rejected": 1,
  "errors": [
    {
      "eventId": "...",
      "eventType": "...",
      "publicationId": "...",
      "pageId": "...",
      "code": "page_not_in_publication"
    }
  ]
}
```

**Do not** rewrite page IDs to “nearest” page. The evidence shows an identity mismatch; rewriting would hide it.

#### 2.4 Standalone bridge centralization

**Files:**

* `mos/frontend/src/funnels/standaloneBridge.ts` or new package path
* `mos/frontend/src/funnels/StandaloneImportedHtmlPage.tsx`
* `mos/backend/cloudhand/adapters/deployer.py`
* build script that emits standalone bridge asset
* tests:

  * `mos/frontend/src/funnels/StandaloneImportedHtmlPage.test.tsx`
  * `mos/backend/tests/test_cloudhand_deployer_standalone_bridge.py`

**Minimum implementation:**

* Move inline JS string out of `deployer.py` into a dedicated asset file.
* Deployer reads the asset and injects JSON config.
* Add a bridge version/hash to release manifest.
* Tests assert bridge includes required event endpoint and provider bootstrap behavior.

**Preferred implementation:**

* Use one TypeScript source for both public standalone runtime and static deploy bridge.
* Build into a standalone JS artifact consumed by Python deployer.
* Keep event mapping in shared helpers.

**Evidence:** The PostHog plan explicitly identifies duplicated standalone deploy bootstrap as drift risk and recommends moving the bridge out of inline Python ownership.

#### 2.5 Tenor quiz artifact sanitation and runtime contract

**Files:**

* new Tenor quiz source under the MOS-managed artifact workflow
* `mos/backend/app/services/deploy.py`
* `mos/backend/app/services/imported_html_runtime.py`
* tests:

  * `mos/backend/tests/test_tenor_quiz_artifact_scan.py`
  * `mos/frontend/src/funnels/StandaloneImportedHtmlPage.test.tsx`

**Implement static scan profile:**

Required absence:

* legacy source-brand domain strings;
* Heyflow runtime;
* old source-brand Shopify pixels/scripts;
* old canonical/base URLs;
* raw secret-like tokens.

Required presence:

* MOS standalone bridge marker;
* `/api/public/events`;
* expected product/funnel/publication/page config;
* pre-sales page stage;
* final sales destination path;
* quiz event names.

**Evidence:** The Tenor quiz plan says raw captured source still contained Heyflow, old Shopify scripts/pixels, old canonical/base URLs, and legal/footer remnants, and production should remove them.

#### 2.6 Workspace-owned PostHog cutover completion

**Files:**

* `mos/backend/app/services/public_runtime_tracking.py`
* `mos/backend/app/services/posthog_workspace_settings.py`
* `mos/backend/app/routers/analytics.py`
* `mos/backend/app/schemas/analytics.py`
* `mos/backend/app/services/deploy.py`
* `mos/backend/cloudhand/adapters/deployer.py`
* `mos/frontend/src/lib/posthog.ts`
* tests:

  * `mos/backend/tests/test_analytics.py`
  * `mos/backend/tests/test_imported_html_runtime.py`
  * `mos/backend/tests/test_cloudhand_deployer_funnel_proxy.py`
  * `mos/frontend/src/lib/posthog.test.ts`

**Implement:**

* Public runtime resolves PostHog only from workspace settings.
* Artifact build snapshots workspace settings.
* Standalone deployer consumes page payload tracking only.
* No runtime env fallback after migration.
* Preview pages omit PostHog.

**Evidence:** The workspace PostHog plan explicitly sets this target behavior and says not to keep runtime env fallbacks after cutover.

#### 2.7 Checkout/bundle validation

**Files:**

* `mos/frontend/src/funnels/StandaloneImportedHtmlPage.tsx`
* `mos/frontend/src/funnels/importedHtmlRuntime.ts`
* `mos/frontend/src/lib/checkoutAttribution.ts`
* `mos/backend/app/services/shopify_checkout.py`
* public checkout prepare/consume routes
* tests:

  * `mos/frontend/src/funnels/StandaloneImportedHtmlPage.test.tsx`
  * `mos/backend/tests/test_shopify_checkout.py`

**Implement:**

* required checkout selectors must match exactly once;
* option values must map to exactly one variant;
* purchase mode must be included in selection when needed;
* prepared checkout cache key must include selection, selling plan, quantity, publication/page, and binding;
* invalid variant/selling plan remains a hard error;
* checkout metadata includes transition ID and attribution props.

**Evidence:** The Shopify checkout service already validates Shopify variant and selling-plan GID format and fails with explicit HTTP errors when config/bridge responses are invalid.

### Phase 2 exit criteria

* Artifact identity audit blocks stale IDs.
* Public events no longer produce unhandled FK tracebacks.
* Root redirect policy is explicit.
* Standalone bridge is centralized or at least asset-owned outside inline Python.
* Tenor quiz artifact scan exists and fails on legacy source dependencies.
* PostHog runtime/deploy source is workspace-owned.
* Checkout selection is deterministic and fails closed.

---

## 6.4 Phase 3 — Data cleanup, backfill, and migrations

### Objective

Repair schema/data consistency without destroying evidence or masking defects.

### Phase 3 data work

#### 3.1 Migration status verification

Run:

```bash
cd mos/backend
.venv/bin/alembic current
.venv/bin/alembic heads
```

Confirm the database includes:

* `0089_rmbc_funnel_event_ids_and_types`;
* `0090_quiz_funnel_event_types`;
* `0091_checkout_redirect_timing_event_types`;
* `0088_client_posthog_settings` if workspace PostHog settings are expected.

**Evidence:** The attached migrations add event ID/idempotency, quiz event types, and checkout timing event types.

#### 3.2 Publication/page identity audit query

Read-only audit:

```sql
-- Publication pages whose base page row is missing.
SELECT pp.publication_id, pp.page_id
FROM funnel_publication_pages pp
LEFT JOIN funnel_pages fp ON fp.id = pp.page_id
WHERE fp.id IS NULL;

-- Events whose page is missing. Should be impossible with FK if inserted.
SELECT fe.id, fe.publication_id, fe.page_id
FROM funnel_events fe
LEFT JOIN funnel_pages fp ON fp.id = fe.page_id
WHERE fp.id IS NULL;

-- Active publication page membership for affected funnel.
SELECT f.id AS funnel_id, f.active_publication_id, pp.page_id, pp.slug_at_publish
FROM funnels f
JOIN funnel_publication_pages pp ON pp.publication_id = f.active_publication_id
WHERE f.id = :funnel_id;
```

Do not mutate results during audit.

#### 3.3 Artifact-vs-database audit

Extract page IDs embedded in active artifact release and compare to DB:

```bash
grep -RhoE '"pageId":"[^"]+"' /opt/apps/<workload>/site | sort -u
grep -RhoE '"publicationId":"[^"]+"' /opt/apps/<workload>/site | sort -u
```

Then compare with DB publication pages.

Do not include actual IDs in public incident summaries unless needed internally. Use labels in external documents.

#### 3.4 PostHog settings backfill

For each workspace with active published funnels:

* create or verify `client_posthog_settings`;
* use existing workspace settings if present;
* if backfilling from old env values, treat env as one-time seed only;
* do not keep env fallback.

**Evidence:** The PostHog plan recommends a controlled migration where global env is used only as one-time seed data and then removed as authoritative runtime source.

#### 3.5 Validation event governance

If production smoke events were emitted:

* identify by `validationRunId` or timestamp/session;
* decide whether to retain with `validation=true` or exclude in reporting;
* do not delete raw data without a reporting/governance decision.

The Tenor quiz plan explicitly leaves this as an open decision.

### Phase 3 exit criteria

* Migration head confirmed.
* Active Tenor artifact page IDs match DB publication pages or mismatch is documented.
* Workspace tracking settings present and authoritative.
* No destructive cleanup performed without evidence retention.
* Validation event handling policy decided.

---

## 6.5 Phase 4 — Deployment path consolidation

### Objective

Make the normal `main -> GitHub -> CI/CD -> MOS/Cloudhand deploy` path the only standard route for production changes.

### Phase 4 actions

#### 4.1 Remove or gate direct production mutation workflows

* Archive emergency hotfix workflow or make it approval-only.
* Remove hard-coded host paths and patch scripts from normal operations.
* Add `README`/runbook warnings: direct static host patches invalidate release provenance unless they create a new manifest-bearing release.

#### 4.2 Make standalone deploy dry-run first-class

Add a dry-run command that:

* publishes or selects a publication snapshot;
* builds artifact payload;
* runs identity audit;
* renders static artifact in temp directory;
* runs static scan;
* validates route map;
* validates tracking config;
* emits manifest;
* does not apply infrastructure.

Example proposed command:

```bash
cd mos/backend
.venv/bin/python -m app.tools.validate_standalone_deploy \
  --funnel-id "$FUNNEL_ID" \
  --publication-id "$PUBLICATION_ID" \
  --render-mode standalone_imported_html \
  --default-route-policy entry_page \
  --no-apply
```

This is a proposed implementation command, not evidence that the tool already exists.

#### 4.3 Require post-push verification

After merging recovery code to `main`, use the documented verification process:

```bash
python3 scripts/check_github_actions.py --sha HEAD --wait --expect-production
```

**Evidence:** The deployment runbook says a non-zero exit means incomplete deployment and the repair loop should remain open.

#### 4.4 Deploy artifact only after backend code is live

Because artifact generation is backend-controlled, ensure:

1. backend image with fixes is live;
2. migrations are applied;
3. event-ingestion validation exists;
4. deploy dry-run passes;
5. then request authorization to publish/deploy the Tenor artifact.

### Phase 4 exit criteria

* Emergency direct mutation path is disabled or gated.
* Dry-run standalone deployment exists.
* CI/CD path green.
* Backend with validation is deployed before new standalone artifact is generated.
* Human authorization gate is ready for production apply.

---

## 6.6 Phase 5 — Validation gates

### Objective

Only promote the Tenor standalone quiz/funnel after every identity, runtime, route, analytics, checkout, and provider gate passes.

### Gate 1 — Repository gate

Commands:

```bash
cd mos/backend
.venv/bin/alembic upgrade head
.venv/bin/pytest
```

```bash
cd mos/frontend
npm ci
npm run build
npm test -- --run
```

Acceptance:

* migrations apply;
* backend tests pass;
* frontend build passes;
* runtime tests pass;
* deploy identity tests pass;
* event ingestion tests pass.

### Gate 2 — Artifact dry-run gate

Run proposed dry-run validator.

Acceptance:

* artifact identity audit passes;
* all `pageId` values exist and belong to publication;
* all routes exist;
* no duplicate canonical slugs;
* root redirect policy is explicit;
* manifest generated;
* static scan passes;
* no forbidden legacy Tenor quiz source strings;
* PostHog/Meta config present only if workspace config says so.

### Gate 3 — Staging or non-production gate

Acceptance:

* route loads on desktop/mobile;
* quiz completes;
* sales handoff works;
* MOS event chain accepted by DB;
* PostHog captures observed;
* Meta events observed where configured;
* checkout CTA maps to correct variant/bundle;
* no unhandled exceptions in API logs;
* no `/public/events` 5xx;
* no FK violations.

### Gate 4 — Production authorization gate

Required explicit human authorization must specify:

* target workload;
* target artifact ID/version;
* target publication ID;
* target route;
* whether root redirect changes;
* whether production smoke events may be emitted;
* whether CDN purge is authorized;
* whether nginx reload is authorized if needed;
* rollback release target.

No production apply without this authorization.

### Gate 5 — Production smoke gate

After authorized deploy:

* fetch release manifest;
* load quiz route;
* complete one controlled validation path if authorized;
* verify sales handoff;
* verify internal events accepted;
* verify no FK errors;
* verify PostHog/Meta provider captures where configured;
* verify checkout click tracking remains operational;
* record validation run ID.

### Phase 5 exit criteria

* All gates passed.
* If any gate fails, do not continue to next gate.
* Failed gate produces an actionable issue and preserves logs/artifacts.

---

## 6.7 Phase 6 — Monitoring and ongoing release discipline

### Objective

Prevent recurrence by making drift, invalid identity, release sprawl, deploy races, and tracking failures visible early.

### Phase 6 controls

#### 6.7.1 Alerts

Alert on:

* `/public/events` 5xx rate;
* structured `page_not_in_publication` count;
* DB FK violation string if it ever reappears;
* deploy lock contention;
* deploy job failure phase;
* standalone artifact identity audit failure;
* artifact host disk usage;
* active release missing manifest;
* nginx config test failure;
* checkout bridge timeout/5xx spike;
* PostHog/Meta validation missing expected events.

#### 6.7.2 Scheduled audits

Daily or per-deploy:

* active releases have manifests;
* active manifests point to existing DB publication/page rows;
* deploy plan files are not world-readable;
* release directory size within threshold;
* no direct patch scripts remain executable in deploy scratch;
* no production service checkout is dirty.

#### 6.7.3 Runbook ownership

Add and assign owners for:

* standalone deploy;
* public event ingestion failure;
* artifact rollback;
* Shopify checkout attribution;
* PostHog/Meta tracking;
* secret exposure response.

#### 6.7.4 Release retention

Keep:

* active release;
* last 10 valid releases;
* all releases from last 7 days;
* pinned releases;
* incident releases until postmortem complete.

Prune only after manifest capture.

### Phase 6 exit criteria

* Monitoring covers recurrence modes.
* Runbooks exist.
* Release retention policy implemented.
* Direct production patches are exceptional and auditable.

---

# 7. Exact implementation checklist with file-level changes and test commands

## 7.1 Backend deploy and artifact identity

### `mos/backend/app/services/deploy.py`

Add:

* `validate_funnel_artifact_identity(...)` call after artifact payload build.
* `default_route_policy` and `default_page_slug` handling in workload/source_ref.
* deploy lock acquisition around plan patch/apply/publish deploy.
* post-deploy validation that checks internal event ingestion response, not only client-side observed event names.
* release manifest metadata passed into deployer source_ref or app spec.

Modify:

* `_run_funnel_publish_job`

  * after `hydrate_funnel_artifact_workload_patch`, run identity audit;
  * before `patch_workload_in_plan`, acquire lock;
  * before apply, write job phase `identity_validated`;
  * after validation, attach manifest summary to job result.
* `_build_funnel_tracking_validation_plan`

  * include validation run ID;
  * include expected publication/page ID response validation.
* `_apply_publish_job_artifact_render_mode`

  * preserve explicit default-route policy in source_ref.

Tests:

```bash
cd mos/backend
.venv/bin/pytest mos/backend/tests/test_funnel_artifact_identity.py
.venv/bin/pytest mos/backend/tests/test_deploy_locks.py
.venv/bin/pytest mos/backend/tests/test_cloudhand_deployer_funnel_proxy.py
```

## 7.2 Deploy locks

### New file: `mos/backend/app/services/deploy_locks.py`

Implement:

* lock path under deploy root, or DB-backed lock table;
* atomic acquisition;
* lock release in `finally`;
* stale lock inspection;
* no secret values in lock file.

Suggested lock payload:

```json
{
  "lockVersion": 1,
  "planPath": "...",
  "workloadName": "...",
  "jobId": "...",
  "orgId": "...",
  "userId": "...",
  "acquiredAt": "...",
  "process": "mos-backend"
}
```

Tests:

```bash
cd mos/backend
.venv/bin/pytest mos/backend/tests/test_deploy_locks.py
```

## 7.3 Deploy API authorization

### `mos/backend/app/routers/deploy.py`

Add dependency:

```python
def require_deploy_operator(auth: AuthContext = Depends(get_current_user)) -> AuthContext:
    ...
```

Apply to:

* latest plan;
* save plan;
* patch workload;
* workload domains;
* apply plan;
* apply alias.

Behavior:

* admin/ops allowed;
* other roles rejected with 403;
* log actor and attempted action.

Tests:

```bash
cd mos/backend
.venv/bin/pytest mos/backend/tests/test_deploy_authz.py
```

## 7.4 Public event ingestion validation

### `mos/backend/app/routers/public_funnels.py`

Add helper:

```python
def _validate_public_event_page_membership(
    *,
    session: Session,
    publication: FunnelPublication,
    event: PublicEventIn,
) -> PublicEventValidationResult:
    ...
```

Implement:

* valid UUID checks;
* page exists;
* page belongs to funnel;
* page belongs to publication;
* event type supported;
* duplicate event ID idempotent.

Return structured response.

Tests:

```bash
cd mos/backend
.venv/bin/pytest mos/backend/tests/test_public_events_ingestion.py
```

Must include test cases:

* valid event;
* duplicate `eventId`;
* invalid event type;
* page missing;
* page not in publication;
* publication missing;
* mixed publication IDs in same batch;
* empty events batch;
* site/preview no-op behavior if retained.

## 7.5 Database model/migration checks

### `mos/backend/app/db/models.py`

Do not remove FKs. Add indexes only if needed for validation performance:

* `funnel_publication_pages(publication_id, page_id)`;
* `funnel_pages(funnel_id, id)` if not already present.

### Alembic

Add migration only if index missing. Do not modify enum migrations unless missing in target DB.

Commands:

```bash
cd mos/backend
.venv/bin/alembic revision --autogenerate -m "add funnel publication page validation indexes"
.venv/bin/alembic upgrade head
.venv/bin/pytest
```

## 7.6 Release manifest

### `mos/backend/cloudhand/adapters/deployer.py`

Add:

* `_write_funnel_artifact_release_manifest(...)`
* call after writing static routes but before activation;
* include manifest in `site/.mos/release.json` or release root;
* include nginx comments with release identity.

Do not include:

* API keys;
* tokens;
* secret env values;
* public infrastructure IPs.

Tests:

```bash
cd mos/backend
.venv/bin/pytest mos/backend/tests/test_cloudhand_deployer_release_manifest.py
```

## 7.7 Default route policy

### `mos/backend/app/schemas/funnels.py`

Extend `FunnelPublishDeployRequest`:

```python
defaultRoutePolicy: Optional[Literal["entry_page", "sales_page", "explicit_slug", "none"]] = None
defaultPageSlug: Optional[str] = None
```

### `mos/frontend/src/api/funnels.ts`

Extend `PublishFunnelDeployPayload`:

```ts
defaultRoutePolicy?: "entry_page" | "sales_page" | "explicit_slug" | "none";
defaultPageSlug?: string;
```

### `mos/backend/cloudhand/adapters/deployer.py`

Replace implicit default logic for standalone deploys with policy-driven resolution.

Tests:

```bash
cd mos/backend
.venv/bin/pytest mos/backend/tests/test_cloudhand_deployer_default_route_policy.py
```

```bash
cd mos/frontend
npm test -- --run mos/frontend/src/pages/research/funnels/funnelPublicUrls.test.ts
```

## 7.8 Standalone bridge asset extraction

### New or modified files

* new: `mos/frontend/src/funnels/standaloneImportedHtmlBridge.ts`
* new generated asset: `mos/backend/app/static/standalone-imported-html-bridge.js` or equivalent
* modified: `mos/backend/cloudhand/adapters/deployer.py`
* modified: `mos/frontend/src/funnels/StandaloneImportedHtmlPage.tsx`
* modified tests: `mos/frontend/src/funnels/StandaloneImportedHtmlPage.test.tsx`

Build approach:

* frontend builds bridge asset;
* backend package includes built asset;
* deployer reads asset by path;
* deployer injects config JSON separately.

Tests:

```bash
cd mos/frontend
npm test -- --run mos/frontend/src/funnels/StandaloneImportedHtmlPage.test.tsx
npm run build
```

```bash
cd mos/backend
.venv/bin/pytest mos/backend/tests/test_cloudhand_deployer_standalone_bridge.py
```

## 7.9 Tenor quiz artifact scan

### New file: `mos/backend/app/services/static_artifact_scan.py`

Implement profile:

```python
TENOR_QUIZ_FORBIDDEN_PATTERNS = [...]
TENOR_QUIZ_REQUIRED_PATTERNS = [...]
```

### New tests

* `mos/backend/tests/test_tenor_quiz_artifact_scan.py`

Test cases:

* fails when legacy source domain appears;
* fails when Heyflow appears;
* fails when old Shopify pixel appears;
* passes clean MOS quiz artifact;
* reports file path and pattern label, not secret-like raw content.

Command:

```bash
cd mos/backend
.venv/bin/pytest mos/backend/tests/test_tenor_quiz_artifact_scan.py
```

## 7.10 PostHog workspace-owned cutover

### Files

* `mos/backend/app/services/public_runtime_tracking.py`
* `mos/backend/app/services/posthog_workspace_settings.py`
* `mos/backend/app/routers/analytics.py`
* `mos/backend/app/schemas/analytics.py`
* `mos/backend/app/services/deploy.py`
* `mos/backend/cloudhand/adapters/deployer.py`
* `mos/frontend/src/lib/posthog.ts`

Tests:

```bash
cd mos/backend
.venv/bin/pytest mos/backend/tests/test_analytics.py
.venv/bin/pytest mos/backend/tests/test_imported_html_runtime.py
.venv/bin/pytest mos/backend/tests/test_cloudhand_deployer_funnel_proxy.py
```

```bash
cd mos/frontend
npm test -- --run mos/frontend/src/lib/posthog.test.ts
```

## 7.11 Checkout and bundle handling

### Files

* `mos/frontend/src/funnels/StandaloneImportedHtmlPage.tsx`
* `mos/frontend/src/funnels/importedHtmlRuntime.ts`
* `mos/frontend/src/lib/checkoutAttribution.ts`
* `mos/backend/app/services/shopify_checkout.py`
* public checkout routes

Tests:

```bash
cd mos/frontend
npm test -- --run mos/frontend/src/funnels/StandaloneImportedHtmlPage.test.tsx
```

```bash
cd mos/backend
.venv/bin/pytest mos/backend/tests/test_shopify_checkout.py
```

## 7.12 CI/CD workflow hardening

### `.github/workflows/docker-images.yml`

Add jobs or steps:

* backend deploy identity tests;
* static artifact scan tests;
* frontend standalone bridge tests;
* secret scan for generated artifacts if available.

Do not print secrets.

### `.github/workflows/tenor-tracking-hotfix.yml`

Either:

* remove; or
* restrict to manual approved emergency use and make it manifest-producing.

## 7.13 Documentation

Add or update:

* `docs/runbooks/standalone-funnel-deploy.md`
* `docs/runbooks/public-events-fk-violation.md`
* `docs/runbooks/standalone-artifact-rollback.md`
* `docs/runbooks/shopify-checkout-attribution.md`
* `docs/runbooks/posthog-meta-tracking-validation.md`
* `docs/runbooks/secret-exposure-response.md`
* `docs/ops/service-env-contract.md`
* `docs/deployment-runbook.md`

Required content:

* authorization gates;
* evidence capture steps;
* no public IPs/secrets;
* rollback procedure;
* validation commands;
* expected failure modes.

---

# 8. Validation matrix with acceptance criteria

| Area                     | Evidence basis                                                    | Validation action                                           | Acceptance criteria                                                        | Failure response                                                            |
| ------------------------ | ----------------------------------------------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Repository CI            | CI runs backend tests/migrations and frontend build.              | Run backend pytest, Alembic, frontend build/tests.          | All tests pass; migration head clean.                                      | Do not deploy; fix code.                                                    |
| Deploy authorization     | README says deploy RBAC is not scoped.                            | Attempt deploy route as non-operator in test.               | 403; no plan mutation.                                                     | Block release until fixed.                                                  |
| Deploy lock              | README says no deploy queue/lock.                                 | Start two same-workload deploy jobs in test.                | One runs, one fails/queues cleanly.                                        | Block apply path.                                                           |
| Artifact identity        | FK violation showed bad page ID in runtime event.                 | Generate artifact and audit IDs against DB.                 | Every page ID exists and belongs to publication.                           | Do not persist/apply artifact.                                              |
| Public event ingestion   | `PublicEventIn` requires publication/page IDs.                    | POST valid and invalid events.                              | Valid inserts; invalid returns structured 422; duplicate event ID dedupes. | Fix ingestion validation before production.                                 |
| Event enum coverage      | Quiz and checkout migrations add event types.                     | Submit every expected quiz and checkout event type in test. | All expected types accepted.                                               | Add migration/enum sync.                                                    |
| Root redirect            | Deployer can redirect root to default route.                      | Dry-run nginx config and curl root in staging.              | Redirect matches explicit policy.                                          | Fix policy/config; do not deploy.                                           |
| Quiz artifact sanitation | Tenor plan requires removing legacy source scripts/dependencies.  | Static scan built artifact.                                 | No forbidden legacy strings; required MOS strings present.                 | Rebuild artifact; do not patch live.                                        |
| Standalone bridge        | PostHog plan identifies duplicated bootstrap drift.               | Compare bridge asset version/hash and run runtime tests.    | Deployer and frontend use canonical bridge asset or tested equivalent.     | Block standalone deploy.                                                    |
| PostHog workspace config | Plan requires workspace-owned config and no env fallback.         | Remove old env in staging; build artifact.                  | Tracking persists from workspace settings only.                            | Complete cutover/backfill.                                                  |
| Meta browser events      | Runtime maps pre-sales/sales events.                              | Playwright validation trap.                                 | Expected Meta calls observed with event IDs.                               | Fix event mapping or pixel config.                                          |
| MOS internal analytics   | FK failure was internal ingestion.                                | Smoke event chain through `/public/events`.                 | No 5xx; no FK errors; DB rows accepted.                                    | Roll back artifact or fix IDs.                                              |
| Shopify checkout         | Checkout service validates GIDs and bridge response.              | Resolve selected bundle and create checkout in staging.     | Exactly one variant; checkout URL/cart ID returned.                        | Fix variant mapping/bridge config.                                          |
| Attribution              | Checkout attribution preserves click IDs/UTMs.                    | Sales CTA smoke with UTMs/click IDs.                        | Checkout URL/attributes carry attribution.                                 | Fix runtime before production.                                              |
| Release manifest         | New remediation requirement.                                      | Inspect active release manifest.                            | Manifest exists, no secrets, IDs match DB.                                 | Mark release unknown-provenance; do not use for rollback unless authorized. |
| Nginx config             | Deployer runs `nginx -t` and reloads.                             | Dry-run config and `nginx -t` in authorized environment.    | Valid config; root/static/API routes correct.                              | Do not reload; fix config.                                                  |
| Secrets                  | Runbook says secrets stay out of artifacts/images.                | Secret scan repo/artifact/plan redacted copy.               | No secret-like values in artifact or logs.                                 | Rotate affected credentials and scrub.                                      |
| Observability            | Journal exposed unhandled FK error.                               | Trigger invalid event in staging.                           | Structured 422 log, no traceback.                                          | Fix logging/validation.                                                     |
| Rollback                 | Release directories exist by deployer design.                     | Select prior manifest release and dry-run symlink switch.   | Prior release validates against DB.                                        | Do not roll back to invalid release.                                        |

---

# 9. Risk register

| Risk                                                | Severity | Reversibility | Evidence/inference                                                                     | Mitigation                                                                     | Owner            |
| --------------------------------------------------- | -------: | ------------: | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ | ---------------- |
| Static artifact emits stale page IDs                | Critical |        Medium | Evidence: FK violation on `funnel_events.page_id`.                                     | Artifact identity audit; event-ingestion preflight; manifest.                  | Backend/deploy   |
| Direct artifact patches overwrite provenance        |     High |        Medium | Evidence: normal CI path exists; operational context includes patch artifacts.         | Disable/gate hotfix workflows; manifest-only release changes.                  | Ops              |
| Concurrent deploy applies race shared plan/state    |     High |        Medium | Evidence: README says no deploy queue/lock.                                            | Deploy locks by plan/workload.                                                 | Backend/deploy   |
| Non-operator can mutate deploy plans                |     High |        Medium | Evidence: README says RBAC not scoped.                                                 | Add deploy RBAC.                                                               | Backend/auth     |
| PostHog config leaks across workspaces              |     High |          High | Evidence: plan says global env is wrong boundary.                                      | Workspace settings only; one-time backfill; no env fallback.                   | Backend/frontend |
| Standalone bridge drift breaks tracking/checkout    |     High |        Medium | Evidence: plan calls out duplicated deployer bootstrap.                                | Centralize bridge asset; bridge version tests.                                 | Frontend/deploy  |
| Root redirect hides intended quiz entry             |   Medium |          High | Inference from deployer default sales-page preference.                                 | Explicit default route policy.                                                 | Backend/deploy   |
| Quiz artifact retains legacy source scripts         |     High |          High | Evidence: Tenor plan says source still contains Heyflow/Mars artifacts.                | Static scan; rebuild first-party quiz runtime.                                 | Frontend/content |
| Checkout maps to wrong bundle                       |     High |        Medium | Evidence: checkout resolver exists; tests cover variants.                              | Exact selector/variant validation; no fallback variant.                        | Frontend/backend |
| Provider analytics show events while MOS drops them |     High |        Medium | Inference from client-side provider calls and internal FK failure.                     | Validation requires MOS ingestion success before provider success.             | Analytics        |
| Production smoke pollutes reporting                 |   Medium |          High | Evidence: Tenor plan lists smoke event governance as open decision.                    | Mark validation events; reporting filters.                                     | Analytics/ops    |
| Secret exposure through plans/scripts               | Critical |        Medium | Evidence: README warns plan files can contain sensitive env; raw JWT script excluded.  | Secret scan, rotation, permissions, no hard-coded JWTs.                        | Security/ops     |
| Release directories grow unbounded                  |   Medium |          High | Inference from accumulated artifact-host releases.                                     | Retention policy after evidence capture.                                       | Ops              |
| Overly strict validation blocks urgent recovery     |   Medium |          High | Inference.                                                                             | Dry-run first; explicit emergency gate; clear error messages.                  | Incident lead    |
| Weak rollback target                                |     High |           Low | Inference from unknown-provenance releases.                                            | Only rollback to manifest-validated release; otherwise explicit authorization. | Ops              |
| Migration mismatch between code and DB              |     High |        Medium | Evidence: event enum migrations are recent.                                            | `alembic current/heads`, CI migration tests.                                   | Backend          |
| Expired JWT noise hides deploy failures             |      Low |          High | Evidence: journal included expired JWT errors.                                         | Categorized logs; filter auth noise in deploy incident dashboards.             | Backend/ops      |
| Shopify bridge unavailable                          |     High |          High | Evidence: runbook requires bridge URL/token for checkout.                              | Health check from backend; fail checkout cleanly.                              | Commerce         |
| CDN/cache serves old artifact after fix             |   Medium |        Medium | Inference.                                                                             | Manifest endpoint; authorized cache purge only.                                | Ops              |
| Artifact generated from wrong environment           | Critical |        Medium | Inference from DB/artifact mismatch possibility.                                       | Embed environment/release IDs; identity endpoint comparison.                   | Backend/deploy   |

---

# 10. Open questions and data that must be verified before any live intervention

## 10.1 Identity and publication questions

1. What is the exact active publication ID for the affected Tenor funnel?
2. Does the page ID embedded in the current static artifact exist in `funnel_pages`?
3. Does that page ID belong to the affected funnel?
4. Does that page ID belong to the active publication’s page set?
5. Was the artifact generated from the same database that receives `/public/events`?
6. Was the affected page deleted/recreated after artifact generation?
7. Was a publication override used during artifact generation?
8. Does the active artifact manifest exist? If not, can the embedded config be reconstructed?

## 10.2 Route and stage questions

1. Should the Tenor quiz be the publication entry page or an additional pre-sales route?
2. Should `/` redirect to quiz, sales-page, or return a controlled root response?
3. Should legacy `/presales/` remain live?
4. Should `/10-reasons-glp/` remain a pre-sales route or be replaced by `/quiz-v6/`?
5. Are custom pre-sales slugs expected to preserve their slugs exactly?
6. Should root redirect preserve all query params? The current redirect behavior should preserve query params; attribution likely depends on it.

## 10.3 Tenor quiz content questions

1. What is the approved final quiz source after removing legacy source-brand scripts?
2. Are raw answer labels allowed in analytics props, or only stable option IDs?
3. What are the stable question IDs and option IDs?
4. What is the required quiz version string?
5. Is result segmentation fixed or dynamic?
6. Should every answer path always route to the same sales page in this version? The plan says yes.

## 10.4 Analytics questions

1. Is Tenor workspace PostHog config already stored in `client_posthog_settings`?
2. Does the active sales page tracking config match workspace config?
3. Is Meta tracking active and workspace-pixel-consistent?
4. Should production smoke events be retained with validation markers or excluded from reporting?
5. What dashboard/reporting pipeline consumes `funnel_events`, and how does it handle validation events?
6. Are web vital events required for standalone quiz launch, or can they be disabled until identity validation is fixed?

## 10.5 Checkout and commerce questions

1. Which product variants should the Tenor sales page expose?
2. Which option names and values must the imported HTML selector resolve?
3. Are subscription/selling plan IDs required for the selected bundles?
4. Does Shopify bridge health pass from the backend host?
5. Does checkout attribution need query params, cart attributes, note attributes, or all three?
6. Is there a known mapping between selected quiz segment and sales-page bundle? The current Tenor plan says no answer-based routing for this version.

## 10.6 Deployment questions

1. What is the current deploy root path for MOS/Cloudhand?
2. Which plan file is authoritative?
3. Are there multiple active `brand-funnels-*` workloads for the same Tenor funnel?
4. Which release directory is currently active?
5. Which release directory is the last known good one?
6. Does any active release have a manifest?
7. Are Bunny/CDN layers in front of the artifact host for this route?
8. If CDN exists, is purge authorized after deploy?

## 10.7 Security and permissions questions

1. Which credentials were present in the excluded hard-coded JWT/auth script?
2. Were any secrets copied into root temp artifacts, deploy plans, CI logs, or static release directories?
3. Which credentials require rotation?
4. Which users currently have deploy route access?
5. Which CI/CD secrets can deploy to bridge/artifact hosts?
6. Are deploy plan files readable by non-deploy users?

## 10.8 Operational authorization questions

Before any live change, the approver must specify:

* target environment;
* exact workload;
* exact artifact ID/version;
* exact publication ID;
* whether apply is authorized;
* whether nginx reload is authorized;
* whether service restart is authorized;
* whether CDN purge is authorized;
* whether production validation events may be emitted;
* rollback target and criteria.

---

# 11. Final recommended sequence for a human-reviewed fix plan

## Step 1 — Declare freeze and capture evidence

Perform Phase 0 evidence capture. Do not mutate production. Store evidence in a dated, access-controlled location. Redact secrets and public infrastructure IPs from review documents.

## Step 2 — Verify the current active Tenor artifact identity

Extract embedded `publicationId`, `pageId`, `productSlug`, `funnelSlug`, page slug, and stage from current active release. Compare with database publication/page rows.

Expected result options:

* **Match:** FK error may come from a different route/release or a now-fixed transient issue.
* **Mismatch:** Current artifact is stale or generated from wrong identity; proceed to rebuild from repository path.
* **Insufficient evidence:** Keep production frozen and inspect release directory, deploy job state, and DB rows further.

## Step 3 — Patch event ingestion validation first

Implement and deploy clean validation for `/public/events` before republishing new standalone artifacts. This changes uncontrolled 500/FK failures into structured validation errors and prevents more opaque failures.

This step should be repository PR -> CI -> normal deploy. No direct production mutation.

## Step 4 — Add deploy RBAC and deploy lock

Implement deploy operator checks and same-workload locks. This prevents further accidental or concurrent corruption while the artifact path is being fixed.

## Step 5 — Add artifact identity audit and release manifest

Implement the artifact identity audit and manifest writer. A standalone artifact must not persist or apply if page/publication IDs do not match DB.

## Step 6 — Make root redirect explicit

Add `defaultRoutePolicy` and `defaultPageSlug`. For Tenor quiz, choose `entry_page` or `explicit_slug: quiz-v6` after human review. Do not rely on sales-page default preference.

## Step 7 — Centralize or extract standalone bridge runtime

At minimum, move the standalone bridge source out of inline Python and test its version/hash. Prefer a shared TypeScript-built bridge asset consumed by the deployer.

## Step 8 — Build clean Tenor quiz artifact

Use the Tenor quiz plan as the contract:

* no legacy source-brand scripts;
* no Heyflow;
* no old pixels/canonical/base URLs;
* first-party quiz runtime;
* MOS/RMBC event emission;
* same-origin route;
* final handoff to sales page;
* stable question/option IDs;
* no answer-based routing unless later approved.

## Step 9 — Run dry-run artifact validation

Run the new dry-run validator. Require:

* DB identity audit passes;
* static scan passes;
* route map passes;
* tracking config passes;
* checkout variant mapping passes;
* manifest generated;
* no deploy apply.

## Step 10 — Stage and smoke

Deploy to staging or a non-production route first. Validate:

* quiz route;
* sales route;
* event chain;
* provider captures;
* checkout mapping;
* no API errors;
* no FK errors.

## Step 11 — Human production authorization

Only after staging success, request explicit authorization for production apply. Include:

* artifact manifest;
* expected route behavior;
* root redirect behavior;
* smoke plan;
* rollback target;
* whether validation events may be written.

## Step 12 — Production deploy through normal path

Use `main -> GitHub -> CI/CD` for code. Use MOS/Cloudhand deployer for the standalone artifact only after backend fixes are live. Do not direct-patch static files.

## Step 13 — Production smoke and monitor

Run the authorized smoke. Check:

* release manifest;
* route responses;
* event ingestion success;
* no FK errors;
* PostHog/Meta observations;
* checkout click tracking;
* logs and alerts.

## Step 14 — Post-recovery cleanup

After the incident is stable:

* archive unknown-provenance releases;
* prune old releases by policy;
* rotate any exposed credentials;
* remove or gate emergency hotfix workflows;
* update runbooks;
* complete postmortem with root causes and prevention controls.

---

# 12. Final synthesis

The recovery should treat the Tenor standalone failure as a release-integrity and runtime-identity incident, not as a one-page HTML bug. The strongest evidence is the database FK violation from standalone runtime events: the artifact emitted a `pageId` that the backend could not accept for `funnel_events`. The system already has a normal CI/CD path and strong pieces of standalone validation, but it also has documented gaps: no deploy lock, insufficient deploy RBAC, sensitive plan state, and duplicated standalone bootstrap logic. The fix is to freeze mutation, capture evidence, add event-ingestion validation, add deploy locks/RBAC, require artifact identity audits and release manifests, centralize the standalone bridge, rebuild the Tenor quiz artifact cleanly, validate in staging, and only then deploy through the reviewed repository-controlled path.
