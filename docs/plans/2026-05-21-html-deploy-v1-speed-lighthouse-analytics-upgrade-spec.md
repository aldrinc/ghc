# Decision

Adopt the corrected production flow for HTML funnels and make it the lead framing everywhere in the `html-deploy-v1` upgrade spec:

**user-provided HTML → agent prepares production-ready `html-deploy-v1` artifact → Terraform deploy from the MOS server as jumphost → inactive candidate release → deterministic validation/report → activation**

This correction replaces any prior wording that implied GitHub, branches, or CI/CD were the source of funnel content. They are not.

- **GitHub is only source control for MOS server code and deployment machinery** such as validators, runtimes, and deploy orchestration.  
- **GitHub is not the source of funnel content.**
- **The funnel content source is user-provided HTML** supplied into the HTML-deploy process.
- The MOS-side **agent preparation/build phase** converts that HTML into a production-ready `html-deploy-v1` artifact by performing:
  - asset closure,
  - analytics instrumentation,
  - Lighthouse/speed optimization,
  - manifest correctness,
  - route/handoff contract generation,
  - validation metadata generation.
- After preparation, deployment proceeds through the **existing Terraform deployment flow from the MOS server jumphost**, not by direct/manual prod mutation.

Within that corrected process, make four upgrades mandatory for supported production HTML page types (`listicle`, `listicle_hybrid`, `quiz`, `sales`):

1. **Enable real render-time optimization** in the agent preparation/build path, including sales pages.
2. **Enable real optimization evidence validation and Lighthouse gating** for applicable candidate runs; no applicable run may return `"disabled"`.
3. **Replace the duplicated sales-page analytics harness with one shared runtime contract** so performance, analytics correctness, and supportability move together.
4. **Reduce production brittleness by separating responsibilities cleanly** across build, deploy, validation, and activation.

This spec preserves the hard constraints already established in the repo and docs:

- no legacy standalone/manual HTML deploy fallback,
- no fake validation data,
- hard errors over silent fallback,
- no direct/manual production mutation without explicit break-glass authorization,
- no LLM/model changes.

Primary source context for this spec:
- `mos/backend/app/services/deploy.py`
- `mos/backend/cloudhand/adapters/deployer.py` (via the supplied worktree observations plus referenced validator behavior)
- `mos/frontend/src/funnels/StandaloneImportedHtmlPage.tsx`
- `mos/frontend/src/lib/posthog.ts`
- `mos/frontend/src/lib/metaFunnelEvents.ts`
- `mos/backend/app/config.py`
- `mos/backend/scripts/validate_html_deploy_candidate_local.py`
- `docs/validation/html-deploy-v1-page-validation-spec.md`
- `docs/validation/html-deploy-v1-deterministic-validator-design.md`
- `docs/validation/html-deploy-v1-option-2-deterministic-validator-detailed-design.md`
- `docs/plans/2026-05-13-html-deploy-deterministic-validator-production-gap-plan.md`
- `docs/plans/2026-05-17-html-deploy-dynamic-quiz-sales-implementation-guide.md`
- `.local/oracle-html-deploy-lighthouse-spec-review.md`
- the current draft at `docs/plans/2026-05-21-html-deploy-v1-speed-lighthouse-analytics-upgrade-spec.md`

The central contradiction remains unchanged: the docs, config, helper code, and tests point toward deterministic real gating, but the current worktree still disables key gates in code. This spec resolves that contradiction in favor of **real execution and hard-fail behavior**.

---

# Current-state findings, severity ordered

| Severity | Finding | Evidence | Resolution |
|---|---|---|---|
| **Critical** | Optimization and Lighthouse validation exist but are hard-disabled. | In `mos/backend/app/services/deploy.py`, `_run_html_deploy_optimization_validation_sync(...)` and `_run_html_deploy_lighthouse_validation_sync(...)` return `"disabled"` before the real logic. Existing tests in `mos/backend/tests/test_deploy.py` already expect deterministic execution. | Remove disabled-path semantics for applicable candidate runs. Applicable means run-or-fail, never silently disable. |
| **Critical** | Render-time optimization is effectively off, and sales pages are outside the most valuable image optimization path. | Worktree observation on `mos/backend/cloudhand/adapters/deployer.py`: `_STANDALONE_ENABLE_HTML_DEPLOY_OPTIMIZATION = False`; compressed/responsive image rewriting is guarded by that flag and also currently excludes `page_stage == "sales"`. | Replace hardcoded flag with explicit rollout config and make optimization default-on for supported production HTML, including sales. |
| **Critical** | The sales/standalone analytics harness is duplicated, oversized, and likely contributing to Lighthouse/TBT/network contention. | `mos/frontend/src/funnels/StandaloneImportedHtmlPage.tsx` contains a very large embedded runtime. Similar analytics behavior already exists in `mos/frontend/src/lib/posthog.ts`, `mos/frontend/src/lib/metaFunnelEvents.ts`, and user-observed backend-generated runtime logic. | Collapse to one shared runtime contract and one event-mapping source of truth. |
| **High** | Tracked sales handoff validation still does not exactly validate the same URL contract users hit. | `StandaloneImportedHtmlPage.tsx` builds richer handoff URLs via `buildInternalNavigationUrl(...)`. `mos/backend/app/services/deploy.py` `_html_deploy_validation_targets(...)` synthesizes a narrower shape. `.local/oracle-html-deploy-lighthouse-spec-review.md` explicitly calls this out. | Introduce a canonical handoff query contract used by both runtime and validator. |
| **High** | `deploy.py` is too large and mixes orchestration with validator internals, browser automation, analytics semantics, candidate activation, and reporting. | `mos/backend/app/services/deploy.py` owns publish/apply orchestration and also plan compilation, browser validators, PostHog readback, Meta checks, optimization checks, Lighthouse helpers, and report assembly. | Reduce `deploy.py` to orchestration over time; move html-deploy validation into a dedicated package. |
| **High** | Prior spec framing incorrectly implied GitHub/CI/CD as funnel content source. | The corrected process context from the user supersedes earlier wording. The current draft already begins correcting this, but the framing is not yet consistently threaded through architecture, rollout, and ownership. | Make the corrected source/deploy model explicit in every lifecycle section. |
| **Medium** | Runtime boot behavior is timer-heavy and brittle. | `StandaloneImportedHtmlPage.tsx` uses repeated `setTimeout(..., 0/250/1000)` patterns across binding, view tracking, interaction tracking, page view, warm checkout, and layout fixups. | Replace with one idempotent bootstrap state machine and bounded deferred work. |
| **Medium** | Generic runtime still contains content-specific DOM heuristics. | `applyMobileSpacingFixes()` in `StandaloneImportedHtmlPage.tsx` searches by literal page text such as `"Load more comments..."`, `"Join 14,000+ Women"`, and `"HEALTH DISCLAIMER:"`. | Move template-specific cleanup into build-time transforms or template-specific manifest plugins; remove from generic runtime. |
| **Medium** | Naming and report semantics remain inconsistent. | `deploy.py` still uses legacy aliases around `standalone_imported_html`; report fields are duplicated (`trackingValidation`, `candidateTrackingValidation`, `htmlDeployValidationReport`); `"disabled"` status is misleading for applicable runs. | Standardize external naming on `html_deploy` and one canonical report path. |
| **Low but important** | Local validation can still produce false confidence. | `mos/backend/scripts/validate_html_deploy_candidate_local.py` calls currently disabled optimization/Lighthouse validators. | Local tooling must use the same real gates and report semantics as candidate validation. |

## Explicit stale-context resolution

Two stale assumptions must be retired everywhere:

1. **Funnel content does not come from GitHub.**  
   The repo contains deploy machinery, validator logic, shared runtime code, and Terraform/jumphost orchestration. Funnel deployments begin from **user-provided HTML**.

2. **A funnel deploy is not “code CI/CD.”**  
   The machinery code still follows normal source-control governance, but a funnel deployment is a **content preparation and artifact deployment flow**: provided HTML is prepared into an artifact, then deployed and validated.

---

# Role boundaries in the corrected process

This section is intentionally explicit because the corrected process model is the biggest review-sensitive change.

## 1. User-provided HTML

This is the **content source of truth** for a given HTML funnel deployment.

It owns:
- the incoming HTML content,
- any embedded asset references,
- the raw structure the user intends to deploy.

It does **not** own:
- production asset closure,
- analytics instrumentation,
- manifest generation,
- route contract generation,
- speed/Lighthouse optimization,
- deployment behavior,
- candidate validation behavior.

Implication: the system must assume user-provided HTML may be incomplete, non-optimized, or production-unsafe. The next phase exists to make it production-ready.

## 2. Agent build/preparation phase

This is the MOS-side preparation/build stage that transforms user HTML into a deployable `html-deploy-v1` artifact.

It owns:
- asset discovery and closure,
- stylesheet localization,
- image localization/rewrite,
- manifest generation and validation metadata,
- analytics harness attachment,
- route/handoff contract generation,
- optimization markers and metadata,
- candidate-ready artifact packaging.

It must fail hard on:
- unresolved required assets,
- missing required manifest contract,
- forbidden legacy references,
- invalid handoff contract generation,
- unsupported page-class requirements.

It must **not** silently fall back to:
- legacy standalone/manual HTML deployment,
- live production assets,
- external unresolved dependencies that bypass closure.

## 3. MOS server code in GitHub

The repository is the source of truth for:
- deploy orchestration code,
- validator code,
- shared runtime modules,
- Terraform/jumphost deployment machinery,
- tests and docs.

It is **not** the source of truth for funnel content.

This distinction matters operationally:
- changes to MOS deployment machinery still go through normal source-control review,
- but per-funnel deployments do not require funnel HTML to live in GitHub.

## 4. Terraform deployment from the MOS server jumphost

Once the agent-prepared artifact is ready, deployment goes through the existing Terraform path using the MOS server as jumphost.

This layer owns:
- plan application,
- artifact materialization into deployed infrastructure,
- inactive candidate release placement.

It does **not** own:
- funnel content authoring,
- analytics semantics,
- optimization policy,
- validation policy.

## 5. Candidate validation

This owns proof before activation.

It validates:
- static/resource correctness,
- optimization evidence,
- browser/runtime correctness,
- PostHog readback,
- Meta delivery,
- Lighthouse performance.

It consumes:
- the prepared artifact contract,
- the candidate release,
- the validation metadata produced during preparation.

It must not fabricate evidence or infer success from stubs.

## 6. Activation

Activation owns only the final promotion of the inactive candidate after a passing deterministic report.

It must:
- be blocked by any failed required gate,
- preserve the prior active release on failure,
- never mutate production directly to “make a candidate pass.”

## 7. Break-glass

Break-glass, if ever explicitly authorized, is outside the normal supported flow.

It does not:
- restore legacy/manual fallback as a standard path,
- weaken the artifact contract,
- justify silent bypasses.

---

# Target architecture/design

## Target state in one sentence

A user-supplied HTML input should be transformed by the MOS-side preparation agent into a closed, optimized, instrumented `html-deploy-v1` artifact, deployed as an inactive candidate via Terraform from the MOS server jumphost, validated deterministically, and activated only after one passing canonical report.

## End-to-end lifecycle

1. **User supplies HTML** to the HTML-deploy process.
2. **Agent prepares artifact**:
   - closes assets,
   - injects instrumentation/runtime config,
   - normalizes route contracts,
   - applies optimization,
   - emits validation metadata.
3. **Terraform deploy runs from MOS server jumphost**.
4. **Inactive candidate release** is created.
5. **Deterministic validation/report** runs on the candidate.
6. **Activation** occurs only if the canonical report passes.

## Architecture layers

### Layer A: Artifact preparation/build
Recommended owner: `mos/backend/cloudhand/adapters/deployer.py` plus adjacent preparation helpers.

Responsibilities:
- take user-provided HTML and build a production artifact,
- localize/close assets,
- apply deterministic optimization transforms,
- emit preparation metadata.

### Layer B: Shared standalone runtime
Recommended owner: new frontend runtime modules under something like `mos/frontend/src/funnels/htmlDeploy/runtime/*`, with `StandaloneImportedHtmlPage.tsx` reduced to a shell.

Responsibilities:
- bootstrap runtime from injected config,
- bind selectors from manifest,
- emit canonical events,
- expose `window.MOSStandaloneAnalytics`,
- perform bounded navigation flush.

### Layer C: Deterministic validator
Recommended owner: `mos/backend/app/services/html_deploy_validation/*`.

Responsibilities:
- compile validation plans and targets,
- validate canonical pages and tracked handoff URLs,
- run browser/resource/optimization/Lighthouse checks,
- validate PostHog and Meta delivery,
- emit one compact `htmlDeployValidationReport`.

### Layer D: Deploy orchestration
Owner: `mos/backend/app/services/deploy.py`.

Responsibilities:
- publish/hydrate,
- apply Terraform plan,
- create candidate release id,
- invoke validator,
- activate candidate on success,
- fail cleanly on any required phase.

---

# Detailed requirements

## Speed optimization requirements

## 1. Optimizer enablement

The current hardcoded optimizer-off state in `mos/backend/cloudhand/adapters/deployer.py` must be replaced by explicit rollout configuration.

### Requirements
- No hardcoded `False` gate for supported production HTML pages.
- Optimization must become **default-on** for applicable `html-deploy-v1` pages after rollout.
- If optimization is expected for an applicable production candidate and is not active, the build/preparation stage must fail with a hard error unless break-glass is explicitly present.
- Optional transforms may be skipped only when:
  - the candidate-localized original bytes remain valid,
  - the skip reason is recorded,
  - the page still passes full validation.

### Important current-gap resolution
The current exclusion of sales pages from compressed/responsive image rewriting must be removed. Sales pages are central to performance and cannot remain outside the optimization path.

## 2. Required preparation/build transforms

For applicable prepared artifacts, the build stage must include:

- Tailwind CDN runtime removal/replacement
- stylesheet localization
- HTML minification
- origin hints
- font preloads where applicable
- `data-mos-render-optimization` critical CSS injection
- LCP image preload
- explicit raster image attributes:
  - `decoding="async"`
  - explicit `loading`
  - explicit `fetchpriority`
- responsive/compressed image candidates when parity checks pass
- favicon normalization for `sales` and `pre_sales`

These align with the current observed behavior and validator expectations in `mos/backend/app/services/deploy.py`; this spec makes them mandatory and reportable.

## 3. Runtime performance requirements

The runtime attached to prepared HTML must stop doing avoidable work on the hot path.

### Required design shifts
- Replace the large inline analytics/runtime block in `mos/frontend/src/funnels/StandaloneImportedHtmlPage.tsx` with:
  - a small inline config/bootstrap payload,
  - a versioned same-origin runtime asset loaded with `defer`.
- Keep `window.MOSStandaloneAnalytics` as the public compatibility surface.
- Initialization must be **idempotent** and driven by one bootstrap coordinator.
- Subsystems must start only when the manifest requires them:
  - checkout warming only with checkout bindings,
  - quiz machinery only with quiz manifest fields,
  - email capture only with email bindings.

### Explicit anti-requirements
The generic runtime must not keep:
- repeated whole-document retries at 0/250/1000ms for many subsystems,
- content/text-search layout surgery,
- parallel analytics implementations.

## 4. Validation throughput requirements

Because the content source is user-provided HTML and artifact preparation may happen frequently, validation must stay bounded.

Required:
- compile validation targets once,
- run resource/optimization checks with bounded parallelism,
- run Lighthouse with bounded parallelism,
- if earlier correctness phases fail, Lighthouse should become `not_run` rather than adding latency without decision value.

---

## Lighthouse gate requirements

## 1. Applicability

For applicable `html_deploy` candidate runs:
- Lighthouse must run on canonical candidate page URLs,
- it must not return `"disabled"`,
- allowed statuses are:
  - `passed`
  - `failed`
  - `not_applicable`
  - `not_run`

## 2. Profiles and thresholds

Base configuration remains in `mos/backend/app/config.py`:
- `DEPLOY_HTML_DEPLOY_LIGHTHOUSE_ENABLED`
- `DEPLOY_HTML_DEPLOY_LIGHTHOUSE_COMMAND`
- `DEPLOY_HTML_DEPLOY_LIGHTHOUSE_TIMEOUT_SECONDS`
- `DEPLOY_HTML_DEPLOY_LIGHTHOUSE_MOBILE_MIN_SCORE`
- `DEPLOY_HTML_DEPLOY_LIGHTHOUSE_DESKTOP_MIN_SCORE`

Hard gate:
- mobile performance score **>= 85**
- desktop performance score **>= 85**

Also record:
- FCP
- LCP
- Speed Index
- TBT
- CLS

The current helper `_extract_lighthouse_audit_summary(...)` in `mos/backend/app/services/deploy.py` already supports this direction.

## 3. URL selection

- Lighthouse audits canonical pages only.
- Optimization/resource validation audits canonical pages plus tracked handoff URLs.
- Candidate URLs must include:
  - `mos_deploy_candidate_release`
  - validation cache bust
  - CDN cache bust where needed

## 4. Failure behavior

Applicable candidate runs must hard-fail on:
- missing command,
- executable not found,
- timeout,
- non-zero exit,
- missing JSON report,
- invalid JSON,
- missing performance score,
- score below threshold.

No silent skip. No implicit downgrade to “warning only.”

---

## Sales analytics harness fix requirements

## 1. One source of truth

The event-mapping contract must exist once.

### Required ownership
- `mos/frontend/src/lib/metaFunnelEvents.ts` is the authoritative Meta mapping layer.
- `mos/frontend/src/lib/posthog.ts` is the authoritative PostHog mapping layer.
- The standalone runtime consumes those shared contracts.
- Backend preparation/build code injects config and runtime hooks; it does not own event semantics.

This directly addresses the drift between `StandaloneImportedHtmlPage.tsx`, shared frontend libs, and backend-generated runtime behavior.

## 2. Remove semantic drift

Any change to:
- event names,
- aliases,
- required provider payload fields,
- handoff query params,
must update one shared contract and automatically apply to standalone runtime behavior.

Tests must assert parity between the shared contract and the emitted standalone behavior.

## 3. Slim the sales-page hot path without weakening correctness

The sales harness must preserve required correctness events while reducing avoidable main-thread and network load.

### Required runtime contract
Introduce an explicit **event scheduler** with priority classes:

- **Critical navigation events**
  - presales-to-sales click
  - sales-page entry
  - checkout click
- **Required provider projections**
  - PostHog required events/aliases
  - Meta required events
- **Deferred enrichments**
  - non-critical identify/register operations
  - optional warmups/retries
  - non-essential alias/background behavior

### Requirements
- Keep explicit emission of contract-required events.
- Replace fixed sleep-based flush behavior with:
  - queue-drained-or-deadline semantics,
  - bounded flush for navigation.
- Prefer `sendBeacon` or bounded `fetch(..., keepalive: true)` for first-party events where supported.
- Do not keep repeated timer retries for third-party sends on the critical path.

### Strong recommendation
For standalone html-deploy pages, disable or isolate non-essential PostHog features such as automatic pageview/pageleave behavior if explicit required event emission already covers the contract. This reduces duplicate work without weakening validated correctness.

## 4. Canonical handoff URL contract

This is the biggest correctness/support cleanup item.

`StandaloneImportedHtmlPage.tsx` currently generates richer presales→sales URLs than the validator synthesizes in `mos/backend/app/services/deploy.py`.

### Required design
Define a manifest-driven handoff contract with:
- fixed params:
  - `src`
  - `from`
  - `source_page_type`
  - `from_stage`
  - `to_stage`
  - `source_page`
  - `click_id_type`
- canonical carried params:
  - `session_id`
  - `visitor_id`
  - `anonymous_id` only if kept for compatibility
  - `click_id`
  - `campaign_id`
  - `ad_id`
  - `fbclid`
  - `utm_*`
- explicitly transitional legacy params, if still needed:
  - `rmbc_session_id`
  - `rmbc_anonymous_id`
  - `rmbc_click_id`

### Validation requirement
The validator must build tracked sales handoff URLs from this same contract, not from a handwritten helper with partial overlap.

## 5. Remove route-specific DOM heuristics from the generic runtime

The literal-text layout fixups in `StandaloneImportedHtmlPage.tsx` are not acceptable as generic runtime behavior.

Requirement:
- move them to build-time transforms or explicit template plugins,
- remove them from generic standalone runtime code.

---

## Validation and reporting requirements

## 1. One canonical report

Canonical output location:
- `result.deploy.htmlDeployValidationReport`

Legacy mirrors may temporarily exist for compatibility, but this is the single canonical contract.

## 2. Report contents

The report must contain:
- candidate release id,
- validated canonical pages,
- validated path results,
- optimization validation,
- Lighthouse validation,
- browser/resource/tracking results,
- PostHog/Meta results,
- compact failure list.

Applicable runs must not include:
- fake passes,
- placeholder evidence,
- `"disabled"`.

## 3. Phase ordering

Required validation order:
1. static/resource/tracking correctness,
2. optimization evidence,
3. Lighthouse,
4. activation.

Lighthouse never overrides correctness.

## 4. Local tooling alignment

`mos/backend/scripts/validate_html_deploy_candidate_local.py` must use the same report structure and real phase semantics as candidate validation.

If an applicable phase cannot run locally, local tooling must emit:
- `failed`, or
- `not_run` with explicit reason.

Not a misleading green pass.

---

## Code cleanup requirements

## 1. Backend extraction

Create or complete:
- `mos/backend/app/services/html_deploy_validation/`
  - `orchestrator.py`
  - `targets.py`
  - `optimization.py`
  - `lighthouse.py`
  - `browser_runner.py`
  - `report.py`

`mos/backend/app/services/deploy.py` should retain:
- publish/apply orchestration,
- candidate lifecycle,
- job state transitions,
- activation gating.

## 2. Naming cleanup

Externally standardize on:
- `html_deploy`

New report fields and operator-facing messages should stop using legacy “standalone imported html” naming for the supported production path.

## 3. Dead knob cleanup

Either wire or remove:
- disabled report statuses,
- contradictory helpers,
- duplicate report aliases,
- dead config knobs.

---

# Concrete module/file ownership recommendations

| Module/file | Recommended owner | Must own | Must not own |
|---|---|---|---|
| `mos/backend/app/services/deploy.py` | Deploy orchestration owner | publish/apply/candidate lifecycle, Terraform/jumphost orchestration, activation gate, job state | page-type rules, standalone analytics semantics, HTML parsing policy |
| `mos/backend/cloudhand/adapters/deployer.py` | Artifact preparation/build owner | user-HTML preparation, asset closure, render-time optimization, preparation metadata | PostHog/Meta event mapping |
| `mos/backend/app/services/html_deploy_validation/*` | Validation owner | target compilation, browser/resource/optimization/Lighthouse/PostHog/Meta validation, canonical report shaping | Terraform orchestration |
| `mos/frontend/src/funnels/StandaloneImportedHtmlPage.tsx` | Runtime shell owner | HTML injection, runtime config bootstrap, loading versioned runtime asset | duplicate analytics semantics |
| `mos/frontend/src/lib/posthog.ts` | Analytics semantics owner | canonical PostHog event mapping | selector/binding lifecycle |
| `mos/frontend/src/lib/metaFunnelEvents.ts` | Analytics semantics owner | canonical Meta event mapping | DOM/runtime orchestration |
| `mos/frontend/src/funnels/htmlDeploy/runtime/*` (new) | Standalone runtime owner | queue/transport/bindings/checkout/view tracking using shared mappings | independent taxonomy definitions |
| `mos/backend/scripts/validate_html_deploy_candidate_local.py` | Tooling owner | local candidate validation using same real phases/report | special-case “green” shortcuts |

Ownership rule: a change to handoff URL shape or analytics taxonomy is incomplete unless it updates the shared runtime contract, validator expectations, and parity tests together.

---

# Tests requirements

## Unit
- optimization validator executes for applicable candidate runs,
- Lighthouse validator executes for applicable candidate runs,
- no `"disabled"` regression,
- handoff contract parity between runtime and validator,
- sales pages included in optimization eligibility,
- canonical report statuses and schema.

## Frontend parity
- shared event mapping and standalone runtime emit the same required event matrix,
- standalone runtime no longer diverges from `posthog.ts` / `metaFunnelEvents.ts`,
- navigation flush behavior is bounded and testable.

## Integration
- broken asset closure from user-provided HTML fails preparation or optimization validation,
- missing critical CSS / LCP preload fails where applicable,
- missing Lighthouse tool/report/threshold fails candidate,
- tracked handoff URLs match real runtime contract,
- candidate activation is blocked on failed optimization or Lighthouse.

## Local tooling
- local validator exits non-zero on failed required phases,
- local report matches production report schema.

---

# Rollout

This rollout has two separate tracks and they must remain conceptually separate.

## A. Machinery code rollout

Changes to MOS server code, validator code, runtime modules, and Terraform/jumphost deploy machinery still go through the normal engineering/source-control path for the MOS codebase.

That is the rollout path for the **toolchain**, not for funnel content.

## B. Funnel deployment runtime flow

Once the upgraded machinery is live, each funnel deployment follows this corrected flow:

**user-provided HTML → agent prepares production-ready `html-deploy-v1` artifact → Terraform deploy from MOS server jumphost → inactive candidate release → deterministic validation/report → activation**

### Phase 0: alignment
- remove disabled early returns,
- replace hardcoded optimizer-off constant,
- standardize report statuses and canonical report path.

### Phase 1: runtime consolidation
- move heavy inline runtime logic out of `StandaloneImportedHtmlPage.tsx`,
- centralize analytics semantics,
- introduce manifest-driven handoff contract.

### Phase 2: candidate hard gates
- make optimization evidence blocking,
- make Lighthouse blocking at 85/85,
- keep activation candidate-only.

### Phase 3: cleanup
- remove content-specific DOM heuristics from the generic runtime,
- remove legacy naming from operator-facing surfaces,
- remove dead aliases and contradictory knobs.

---

# Operational failure modes

1. **User-provided HTML is malformed or incomplete**  
   Behavior: preparation fails with explicit asset/manifest/closure error. No silent fallback.

2. **Required asset closure cannot be achieved**  
   Behavior: preparation fails before deploy.

3. **Optimizer is disabled for an applicable page**  
   Behavior: candidate fails unless explicit break-glass exists.

4. **Shared runtime asset is missing or not served**  
   Behavior: static/resource validation fails.

5. **Tracked handoff contract cannot be built**  
   Behavior: presales→sales validation fails.

6. **Optional responsive image rewrite fails parity**  
   Behavior: keep candidate-localized original asset, record skip reason, continue only if the page still passes all gates.

7. **PostHog readback is missing**  
   Behavior: candidate fails even if browser attempted sends.

8. **Meta direct receive is missing**  
   Behavior: candidate fails even if `fbq()` was invoked.

9. **Lighthouse tooling/report is unavailable**  
   Behavior: candidate fails cleanly.

10. **Terraform apply from the MOS server jumphost fails**  
    Behavior: deploy job fails before candidate validation or activation.

11. **Earlier correctness phase fails**  
    Behavior: Lighthouse becomes `not_run`; candidate still fails.

12. **Break-glass requested**  
    Behavior: explicit, exceptional, recorded, time-bounded; does not reintroduce legacy/manual HTML fallback as a supported path.

---

# Acceptance criteria

This spec is complete when all of the following are true:

1. The lead process description everywhere is: **user-provided HTML → agent-prepared `html-deploy-v1` artifact → Terraform deploy from MOS server jumphost → inactive candidate → deterministic validation/report → activation**.
2. No section implies GitHub is the source of funnel content.
3. For applicable `html_deploy` candidate runs, `_run_html_deploy_optimization_validation_sync(...)` and `_run_html_deploy_lighthouse_validation_sync(...)` in `mos/backend/app/services/deploy.py` no longer return `"disabled"`.
4. Candidate activation is blocked when optimization evidence fails.
5. Candidate activation is blocked when mobile or desktop Lighthouse score is below 85.
6. Sales pages are included in the optimization/image-rewrite path, subject only to parity-safe candidate behavior.
7. `mos/frontend/src/funnels/StandaloneImportedHtmlPage.tsx` is reduced to runtime-shell responsibility and no longer contains a second authoritative analytics implementation.
8. Backend preparation/build code no longer owns standalone analytics semantics.
9. Tracked sales handoff URLs are generated from the same contract the runtime uses.
10. There is one canonical report path: `result.deploy.htmlDeployValidationReport`.
11. Local candidate validation uses the same real phase/report semantics as production candidate validation.
12. No legacy/manual HTML fallback is introduced.

---

# Review checklist

- [ ] Does the spec clearly say funnel content starts as **user-provided HTML**, not GitHub content?
- [ ] Does it clearly separate **MOS machinery code in GitHub** from **funnel content source**?
- [ ] Does it preserve the flow: user HTML → agent preparation → Terraform from MOS jumphost → candidate → validation → activation?
- [ ] Does it keep `html-deploy-v1` as the only supported production HTML deploy path?
- [ ] Does it avoid recommending direct/manual production mutation?
- [ ] Does it replace `"disabled"` with real execution or hard failure?
- [ ] Does it remove the hardcoded optimizer-off behavior?
- [ ] Does it include sales pages in optimization scope?
- [ ] Does it explicitly fix the duplicated sales/standalone analytics harness?
- [ ] Does it preserve analytics correctness while reducing Lighthouse/TBT/network pressure?
- [ ] Does it centralize the presales→sales handoff URL contract?
- [ ] Does it keep one canonical validation report?
- [ ] Does it reduce `deploy.py` to orchestration over time?
- [ ] Does it add parity coverage for standalone runtime behavior, not just shared helper coverage?
- [ ] Does rollout remain anchored in the MOS-jumphost Terraform deployment process rather than a GitHub-content deploy model?

