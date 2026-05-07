# HTML Deploy Flow Rebuild Plan for Oracle Approval

Prepared May 7, 2026 for Oracle review.

This plan continues the prior Oracle analysis in `docs/plans/2026-05-05-mos-standalone-deployment-recovery-oracle-plan.md`. It does not reopen the original deployment recovery decision. It narrows the next implementation step to rebuilding the current standalone/imported HTML path into a production-gated HTML deploy flow.

## Decision

Rebuild the current standalone HTML deployment path as a first-class **HTML deploy flow** with explicit artifact kinds, a versioned manifest contract, a PostHog-focused RMBC analytics harness, Facebook conversion events, and fail-closed validation before any deployment is considered production viable.

Approved product decisions from the implementation planning thread:

- Canonical artifact spelling is `listicle`.
- Supported artifact kinds are `listicle`, `listicle_hybrid`, `quiz`, and `sales`.
- `listicle_hybrid` uses the same analytics and validation harness as `listicle`.
- The new manifest/schema version is exactly `html-deploy-v1`.
- RMBC diagnostic depth is mainly for PostHog.
- Facebook conversion events must be added to the analytics harness.
- The old standalone/imported HTML implementation should be rebuilt around production requirements, not treated as a thin rename.

## Oracle Continuity Context

The prior Oracle plan established the operating constraints and failure model:

- The problem class is control-plane integrity, not a single bad bundle.
- Repository code, migrations, tests, and CI are the durable source of truth.
- Direct production mutation is outside scope unless explicitly authorized in the current thread.
- Artifact identity must agree across MOS DB state, generated artifact payloads, static bridge config, public event ingestion, PostHog, and Meta/Facebook.
- The deployer and public runtime currently duplicate standalone bridge behavior, which creates drift risk.
- PostHog should be workspace-owned and snapshotted into artifacts, not read from destination-server environment fallbacks.
- Provider tracking should not be considered valid if first-party MOS ingestion fails during validation.
- Validation must fail closed with actionable diagnostics rather than silently falling back.

This plan is intended to satisfy those Oracle constraints while implementing the requested HTML deploy flow.

## Current System Surface

The current implementation still carries standalone/imported HTML naming and behavior through the system:

- Backend schema accepts `renderMode: "standalone_imported_html"` in `mos/backend/app/schemas/funnels.py`.
- Backend deploy constants and validation use `standalone_imported_html` in `mos/backend/app/services/deploy.py`.
- Cloudhand model enum uses `STANDALONE_IMPORTED_HTML` in `mos/backend/cloudhand/models.py`.
- Cloudhand deployer owns a large inline standalone bridge in `mos/backend/cloudhand/adapters/deployer.py`.
- Frontend public runtime uses `StandaloneImportedHtmlPage.tsx`.
- Frontend publish UI hardcodes `renderMode: "standalone_imported_html"` in `FunnelDetailPage.tsx`.
- The manifest schema is currently `imported-html-instrumentation-v1`.

The system already has useful pieces that should be preserved and upgraded:

- First-party `/api/public/events` ingestion.
- Event IDs and idempotency support in `funnel_events`.
- Existing RMBC and quiz event enum coverage.
- Existing PostHog and Meta browser mapping tests.
- Existing post-deploy tracking validation using Playwright.
- Existing artifact identity audit and release manifest work from the standalone recovery branch.

## Proposed Contract

### Render Mode

Introduce a canonical render mode:

```text
html_deploy
```

Implementation rule:

- New code and new deploy payloads use `html_deploy`.
- Existing `standalone_imported_html` values should not be silently accepted indefinitely.
- If existing local plan/artifact payloads need to be carried forward, implement an explicit one-time migration or rebuild path that reports exactly what was converted.
- After migration/rebuild, unknown or old render modes should fail with a clear deploy error.

### Manifest Schema

Introduce the new manifest version:

```text
html-deploy-v1
```

The manifest must be present for every HTML deploy page and must validate before deploy rendering.

Minimum shared shape:

```json
{
  "schemaVersion": "html-deploy-v1",
  "htmlArtifactKind": "listicle",
  "pageStage": "pre_sales",
  "bindings": [],
  "sections": [],
  "proofs": [],
  "ctas": []
}
```

Supported artifact kinds:

```text
listicle
listicle_hybrid
quiz
sales
```

Supported stage alignment:

| Artifact kind | Required stage | Harness |
| --- | --- | --- |
| `listicle` | `pre_sales` | listicle harness |
| `listicle_hybrid` | `pre_sales` | listicle harness |
| `quiz` | `pre_sales` | quiz harness |
| `sales` | `sales` | sales harness |

No `listical` alias should be added unless explicitly approved. Misspellings should fail cleanly.

## Analytics Harness

### Source Of Truth

During validation, first-party MOS ingestion is the source of truth.

Provider events are required for production viability, but provider calls do not override MOS ingestion:

```text
MOS event accepted
  -> PostHog capture observed when workspace PostHog is configured
  -> Facebook event observed when Meta/Facebook tracking is configured
```

If MOS ingestion fails, validation fails even if PostHog or Facebook captured an event.

### PostHog RMBC Layer

RMBC diagnostic depth is primarily for PostHog. The harness should send rich RMBC events/properties to PostHog while keeping MOS ingestion strict and queryable.

Shared properties for PostHog and MOS where available:

- `event_id`
- `timestamp`
- `session_id`
- `visitor_id` / `anonymous_id`
- `user_id` when known
- `click_id`
- `click_id_type`
- `product_slug`
- `funnel_slug`
- `publication_id`
- `page_id`
- `page_slug`
- `page_stage`
- `page_type`
- `page_variant`
- `html_artifact_kind`
- `experiment_id`
- `traffic_source`
- `referrer_type`
- `utm_source`
- `utm_medium`
- `utm_campaign`
- `utm_content`
- `campaign_id`
- `adset_id`
- `ad_id`
- `creative_id`
- `device_type`
- `viewport_width`
- `viewport_height`
- `browser_user_agent`
- `destination_url` when navigation/click event

RMBC diagnostic properties are required by artifact kind only when the manifest declares the relevant concept. Examples:

- Quiz: `quiz_id`, `quiz_version`, `quiz_variant`, `question_id`, `question_index`, `question_role`, `option_id`, `option_role`, `result_id`, `segment_id`, `recommendation_id`, `answer_path_id`, `mechanism_name`.
- Listicle: `section_id`, `proof_id`, `proof_type`, `cta_id`, `cta_position`, `angle`, `awareness_level`, `mechanism_name`, `offer_id`.
- Sales: `offer_id`, `sku`, `bundle_id`, `subscription_flag`, `price_point`, `selector_id`, `guarantee_id`, `guarantee_type`, `value_ratio`.

### Facebook Conversion Layer

The harness must emit the requested Facebook conversion events in addition to PostHog/MOS events.

The screenshot-provided Facebook events are:

| Facebook event name | Required trigger | Applies to |
| --- | --- | --- |
| `Entered Presales Page` | pre-sales HTML deploy page loads and the bridge is ready | `listicle`, `listicle_hybrid`, `quiz` |
| `PreSalesToSalesClick` | visitor clicks from pre-sales artifact to sales page | `listicle`, `listicle_hybrid`, `quiz` |
| `Entered Sales Page` | sales HTML deploy page loads | `sales`, and downstream sales page after pre-sales handoff |
| `SalesToCheckoutClicked` | visitor clicks sales CTA / checkout CTA | `sales` |

Facebook event payload rules:

- Include deterministic event IDs suitable for browser/server dedupe where applicable.
- Include `_fbp`, `_fbc`, `fbclid`, event source URL, user agent, and external ID when available.
- Preserve current fail-closed pixel consistency behavior for server-side conversions.
- Do not use RMBC-specific PostHog depth as a substitute for Facebook conversion events.

Naming note:

- Existing code references similar names such as `EnteredPresales`, `EnteredSales`, and `SalesToCheckoutClick`.
- The implementation must confirm the exact Facebook event names expected by the configured pixel/event manager.
- The requested screenshot names should be treated as the target external Facebook conversion names unless Oracle flags a platform naming constraint.

## Artifact Harness Requirements

### `listicle`

Use the RMBC presell/listicle specification as the PostHog diagnostic model.

Required MOS/PostHog chain:

```text
presell_page_view
scroll_depth
section_view
proof_view
cta_view
cta_click
offer_page_view
checkout_start
purchase
```

Required Facebook chain for deploy validation:

```text
Entered Presales Page
PreSalesToSalesClick
Entered Sales Page
SalesToCheckoutClicked
```

Minimum manifest requirements:

- `htmlArtifactKind: "listicle"`
- `pageStage: "pre_sales"`
- at least one CTA view target
- at least one internal navigation binding to the configured sales page
- scroll depth milestones
- section targets for major page regions
- proof targets when proof is present

### `listicle_hybrid`

Use the same harness as `listicle`.

`listicle_hybrid` remains a distinct artifact kind only for reporting, deploy intent, and future analysis. It should not fork validation logic unless a future approved requirement demands it.

Additional optional diagnostics may be allowed:

- offer stack view targets
- value stack view targets
- guarantee view targets
- selector interactions

If these are declared, they must validate. If not declared, the harness should not fabricate them.

### `quiz`

Use the RMBC quiz specification as the PostHog diagnostic model.

Required MOS/PostHog chain:

```text
EnteredPresales
QuizLeadViewed
QuizQuestionViewed
QuizOptionPresented
QuizOptionSelected
QuizQuestionSubmitted
QuizCompleted
QuizResultViewed
QuizCtaViewed
PreSalesToSalesClick
sales_page_view
purchase
```

Phase-two RMBC quiz depth should be supported by manifest-driven selectors/emitters:

- `QuizMechanismViewed`
- `QuizProofViewed`
- `QuizRecommendationViewed`
- `question_role`
- `option_role`
- `awareness_level`
- `sophistication_level`
- `angle_family`
- `hook_id`
- `promise_id`
- `mechanism_name`

Required Facebook chain for deploy validation:

```text
Entered Presales Page
PreSalesToSalesClick
Entered Sales Page
SalesToCheckoutClicked
```

Minimum manifest requirements:

- `htmlArtifactKind: "quiz"`
- `pageStage: "pre_sales"`
- stable quiz identity: `quiz_id`, `quiz_version`, `quiz_variant`
- question definitions with stable question IDs
- option definitions with stable option IDs
- result/recommendation targets
- at least one quiz CTA binding to the sales page

### `sales`

Use the RMBC sales page specification as the PostHog diagnostic model.

Required MOS/PostHog chain:

```text
sales_page_view
scroll_depth
section_view
product_detail_interaction
proof_view
offer_stack_view
selector_interaction
guarantee_view
purchase_intent_click
checkout_page_view
checkout_start
payment_info_entered
purchase
```

Required Facebook chain for deploy validation:

```text
Entered Sales Page
SalesToCheckoutClicked
```

Minimum manifest requirements:

- `htmlArtifactKind: "sales"`
- `pageStage: "sales"`
- at least one checkout or purchase-intent binding
- offer stack target
- CTA / purchase intent target
- checkout variant resolver that maps to exactly one variant
- declared selector interactions when selectors are present in the HTML

## Implementation Phases

### Phase 1 — Contract Rename And Schema

Files likely touched:

- `mos/backend/app/schemas/funnels.py`
- `mos/backend/app/services/deploy.py`
- `mos/backend/app/services/imported_html_runtime.py`
- `mos/backend/cloudhand/models.py`
- `mos/frontend/src/api/funnels.ts`
- `mos/frontend/src/types/funnels.ts`
- `mos/frontend/src/pages/research/funnels/FunnelDetailPage.tsx`

Work:

- Add `html_deploy` render mode.
- Add `html-deploy-v1` manifest schema.
- Add `htmlArtifactKind` enum.
- Enforce artifact-kind/page-stage compatibility.
- Rename user-facing text from standalone HTML to HTML deploy flow.
- Add explicit old-mode migration or clean rebuild error.

Exit criteria:

- API schemas accept `html_deploy`.
- New manifests validate.
- Old/unknown modes do not silently pass.

### Phase 2 — Runtime Bridge Ownership

Files likely touched:

- `mos/frontend/src/funnels/StandaloneImportedHtmlPage.tsx`
- `mos/frontend/src/funnels/importedHtmlRuntime.ts`
- `mos/backend/cloudhand/adapters/deployer.py`
- frontend runtime tests
- Cloudhand deployer tests

Work:

- Rename runtime surface to `HtmlDeployPage` / `htmlDeployRuntime`.
- Stop expanding standalone behavior as more inline Python-only script.
- Prefer a canonical TypeScript-owned runtime bridge artifact, or at minimum isolate shared event mapping so frontend and deployer cannot drift silently.
- Rename runtime globals and metadata from standalone naming to HTML deploy naming.
- Add bridge version/hash to release manifest.

Exit criteria:

- Public runtime and static deploy bridge have equivalent event behavior.
- Release manifest records bridge identity.
- Tests fail if bridge marker or event endpoint disappears.

### Phase 3 — PostHog RMBC Event Mapping

Files likely touched:

- `mos/frontend/src/lib/posthog.ts`
- `mos/frontend/src/funnels/HtmlDeployPage.tsx`
- `mos/backend/app/services/imported_html_runtime.py`
- `mos/backend/app/services/deploy.py`
- frontend PostHog tests
- backend manifest tests

Work:

- Build manifest-driven RMBC event emitters by artifact kind.
- Preserve canonical MOS event names while adding PostHog RMBC aliases where useful.
- Validate that required RMBC props exist or can be emitted.
- Do not fabricate quiz/listicle/sales metadata.

Exit criteria:

- Listicle/listicle_hybrid events map to PostHog presell diagnostics.
- Quiz events map to PostHog quiz diagnostics.
- Sales events map to PostHog sales diagnostics.
- Missing required RMBC selectors/IDs fail validation with specific messages.

### Phase 4 — Facebook Conversion Events

Files likely touched:

- `mos/frontend/src/lib/metaFunnelEvents.ts`
- `mos/frontend/src/lib/metaPixel.ts`
- `mos/frontend/src/funnels/HtmlDeployPage.tsx`
- `mos/backend/app/services/deploy.py`
- `mos/backend/app/services/meta_conversions.py`
- Meta/Facebook tests

Work:

- Add requested Facebook conversion events:
  - `Entered Presales Page`
  - `PreSalesToSalesClick`
  - `Entered Sales Page`
  - `SalesToCheckoutClicked`
- Preserve existing Meta attribution and dedupe behavior.
- Confirm browser events and server-side purchase events share usable attribution context.
- Keep provider events best-effort in production runtime but required in deploy validation.

Exit criteria:

- Playwright validation observes the expected Facebook conversion events by artifact kind.
- Meta/Facebook bootstrap is present only when configured.
- Pixel consistency checks remain fail-closed.

### Phase 5 — Validation Harness

Files likely touched:

- `mos/backend/app/services/deploy.py`
- `mos/backend/app/services/imported_html_runtime.py`
- `mos/backend/tests/test_imported_html_runtime.py`
- `mos/backend/tests/test_deploy.py`
- `mos/frontend/src/funnels/HtmlDeployPage.test.tsx`

Work:

- Upgrade static validation:
  - manifest schema
  - kind/stage compatibility
  - selectors exist
  - CTA/checkout bindings valid
  - assets localized/mirrored
  - no unresolved placeholders
  - no forbidden legacy source-brand scripts/domains when profile requires sanitation
- Upgrade browser validation:
  - open non-production validated URL
  - assert bridge boot
  - assert MOS event POST accepted
  - assert PostHog capture queue
  - assert Facebook event queue
  - click pre-sales to sales binding
  - click sales to checkout binding
  - verify path-specific expected event chains
- Add `htmlDeployValidationReport` to deploy output.

Exit criteria:

- Validation reports missing selectors, missing events, provider config issues, failed MOS ingestion, and tested URLs.
- Validation fails before production viability is claimed.
- No production mutation is required for validation.

### Phase 6 — Artifact, Routing, And Release Manifest

Files likely touched:

- `mos/backend/app/services/deploy.py`
- `mos/backend/cloudhand/adapters/deployer.py`
- Cloudhand model/tests

Work:

- Include `renderMode: "html_deploy"` in artifact/source refs.
- Include `htmlArtifactKind`, `htmlDeploySchemaVersion`, bridge hash/version, page-stage map, route policy, and validation summary in release manifest.
- Keep default route policy explicit.
- Preserve artifact identity audit from the prior recovery implementation.

Exit criteria:

- Every HTML deploy artifact is reproducible from artifact payload plus release manifest.
- Default route behavior is explicit and validated.
- Page/publication IDs are validated before deploy and accepted by MOS event ingestion during smoke.

### Phase 7 — Test Matrix

Backend tests:

- schema validation for all four artifact kinds
- invalid spelling fails
- old render mode migration/rebuild behavior
- manifest selector validation
- kind/stage mismatch validation
- deploy validation plan per artifact kind
- MOS event ingestion accepts generated page/publication IDs
- stale page ID rejection is clean
- duplicate event ID idempotency

Frontend tests:

- runtime page view events by artifact kind
- PostHog RMBC event captures
- Facebook conversion event mapping
- pre-sales to sales attribution
- sales to checkout attribution
- checkout variant resolver exact-match behavior

Integration/dry-run tests:

- render local static artifact
- run static scan
- run Playwright validation against local/non-prod URL
- assert `htmlDeployValidationReport`
- assert release manifest includes schema, artifact kind, bridge version/hash, route policy, and event expectations

Exit criteria:

- Existing backend and frontend suites pass.
- New HTML deploy tests pass.
- No test requires touching production.

## Production Viability Gate

An HTML deploy artifact is production viable only when all of these pass:

- Render mode is `html_deploy`.
- Manifest schema is `html-deploy-v1`.
- Artifact kind is one of `listicle`, `listicle_hybrid`, `quiz`, `sales`.
- Kind and page stage match.
- Required selectors exist.
- Required navigation/checkout bindings are valid.
- MOS first-party ingestion accepts the expected event chain.
- PostHog captures are observed when workspace PostHog is configured.
- Facebook conversion events are observed when Meta/Facebook tracking is configured.
- Page/publication IDs pass identity audit.
- Assets are localized/mirrored as required.
- Release manifest records route policy, bridge version/hash, tracking expectations, and validation result.
- Validation report contains no blocking errors.

## Explicit Non-Goals

- Do not deploy to production as part of this implementation.
- Do not restart production services.
- Do not mutate live nginx configs.
- Do not add silent fallbacks for old render modes, misspelled artifact kinds, missing tracking config, or missing selectors.
- Do not change any LLM/model configuration.
- Do not fabricate analytics metadata that is not present in the manifest or runtime context.

## Oracle Review Questions

Oracle should review and approve or modify these points before implementation:

1. Should `html_deploy` fully replace `standalone_imported_html`, with an explicit one-time migration/rebuild path for existing local plans?
2. Is `html-deploy-v1` the correct manifest schema name and boundary?
3. Should Facebook event external names use the screenshot labels exactly, including spaces, or should they map to the existing no-space Meta custom event names?
4. Is it acceptable that `listicle_hybrid` uses the exact `listicle` harness and only differs by `htmlArtifactKind`?
5. Should PostHog receive both canonical MOS event names and RMBC aliases, or only canonical names plus RMBC properties?
6. Should deploy validation require provider events only when workspace tracking is configured, while always requiring MOS first-party ingestion?
7. Should the Python deployer be refactored now to consume a built TypeScript bridge artifact, or should bridge unification be staged behind tests in this implementation cycle?

## Recommended Oracle Approval Outcome

Approve implementation with these guardrails:

- Implement the contract and validation first.
- Keep deployment mutation out of scope until local/non-production validation passes.
- Preserve the prior recovery safeguards for artifact identity, route policy, deploy RBAC, deploy locks, and release manifest.
- Treat MOS ingestion as the validation source of truth.
- Treat PostHog as the RMBC diagnostic destination.
- Treat Facebook events as conversion events required by the configured pixel/event manager.
- Fail closed with clear diagnostics instead of trying alternative paths.
