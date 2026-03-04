# Integration Strategy V2 Plan

## 1) Decision And Scope

This plan makes **Strategy V2 the baseline system of record** for product strategy outputs.

Baseline means:

1. Downstream workflows consume Strategy V2 artifacts first and exclusively.
2. Strategy V2 HITL gates are first-class UI actions, not backend-only operations.
3. Legacy pre-canon/canon workflow paths are removed after cutover, not silently retained.

This plan explicitly covers:

1. Backend prerequisite enforcement and workflow orchestration.
2. Downstream workflow and artifact integration.
3. UI contract, component, and page-level changes.
4. Function-level downstream input validation and data-flow safety.
5. Migration and decommissioning of pre-canon runtime dependencies.

## 2) Non-Negotiable Constraints

1. No hidden fallback paths.
2. No model substitution or model changes without explicit authorization.
3. Fail fast with clear, actionable errors when required data is missing.
4. Keep decision attribution auditable (human gate decisions must be attributable).

## 3) Current State Audit (Code-Backed)

## 3.1 Backend: implemented and usable

1. Strategy V2 workflow exists with staged execution and HITL gates:
   `mos/backend/app/temporal/workflows/strategy_v2.py`.
2. Strategy V2 start endpoint exists:
   `POST /workflows/strategy-v2/start` in `mos/backend/app/routers/workflows.py`.
3. Strategy V2 signal endpoints exist:
   1. `POST /workflows/{id}/signals/strategy-v2/select-angle`
   2. `POST /workflows/{id}/signals/strategy-v2/select-ump-ums`
   3. `POST /workflows/{id}/signals/strategy-v2/select-offer-winner`
   4. `POST /workflows/{id}/signals/strategy-v2/approve-final-copy`
4. Workflow detail payload includes Strategy V2 state and Strategy V2 output artifacts.
5. Strategy V2 activities persist step payload artifacts and workflow-bound research references.
6. Campaign and funnel routes already call Strategy V2 downstream prerequisite helper.

## 3.2 Backend gaps that block clean baseline cutover

1. `Artifact` rows are not workflow-run scoped:
   `mos/backend/app/db/models.py` (`Artifact` has no `workflow_run_id`).
2. `require_strategy_v2_outputs_if_enabled` only checks existence of `strategy_v2_offer` and `strategy_v2_copy`, not final approval semantics or same-run provenance:
   `mos/backend/app/strategy_v2/downstream.py`.
3. `strategy_v2_copy` is written before final approval (`v2-10`) and at final approval (`v2-11`), so existence does not imply approved baseline.
4. Downstream generators still include canon/pre-canon dependencies:
   1. `build_strategy_sheet_activity` still reads `client_canon` + `metric_schema`.
   2. `build_experiment_specs_activity` still falls back to pre-canon angle extraction.
5. Metric dependency mismatch:
   onboarding now runs Strategy V2 child workflow, but experiment generation still requires metric IDs.
6. Worker still registers pre-canon workflow and activities:
   `mos/backend/app/temporal/worker.py`.

## 3.3 Frontend: implemented and usable

1. Workflow detail and research pages exist and poll running workflows.
2. Generic signal hook exists (`useWorkflowSignal`) and can send arbitrary signal payloads.
3. Campaign page can trigger funnel generation and creative production.

## 3.4 Frontend gaps that block Strategy V2 baseline operation

1. No dedicated Strategy V2 HITL gate UI.
2. `WorkflowDetail` TS type does not include Strategy V2 fields returned by backend.
3. Multiple pages still present canon/pre-canon language and assumptions.
4. Research detail assumes `content` is string; Strategy V2 step payload returns object JSON (`artifact://`) and can break string-only rendering.
5. Document/workflow tables still show external "Open doc" links for `artifact://` URLs.
6. Onboarding wizard does not submit required `product_customizable`.
7. UI client creation path does not set `strategyV2Enabled` explicitly.

## 4) End-To-End Data Flow And Downstream Integration

## 4.1 Target flow (source of truth)

```mermaid
flowchart TD
  A[Onboarding Wizard UI] --> B[POST /clients]
  A --> C[POST /clients/{id}/onboarding]
  C --> D[ClientOnboardingWorkflow]
  D --> E[StrategyV2Workflow child]

  E --> E1[v2-01 stage0]
  E1 --> E2[v2-02..v2-06 VOC/angles]
  E2 --> G1{HITL: select angle}
  G1 --> E3[v2-07 stage2]
  E3 --> E4[v2-08 offer pipeline]
  E4 --> G2{HITL: select UMP/UMS}
  G2 --> E5[v2-08b variant scoring]
  E5 --> G3{HITL: select offer winner}
  G3 --> E6[v2-09 stage3+offer+copy context]
  E6 --> E7[v2-10 copy pipeline]
  E7 --> G4{HITL: approve final copy}
  G4 --> E8[v2-11 approved baseline]

  E8 --> H[Campaign Planning/Intent allowed]
  H --> I[Strategy Sheet]
  H --> J[Experiment Specs]
  J --> K{HITL: approve experiments}
  K --> L[Asset Briefs]
  L --> M[Funnel Generation]
  M --> N[Media Enrichment]
  L --> O[Creative Production]
```

## 4.2 Downstream operational flow (with entry points)

```text
Workspace Onboarding
  -> /clients/{id}/onboarding
  -> ClientOnboardingWorkflow
  -> StrategyV2Workflow (child)
  -> Approved Strategy V2 baseline

Campaign Planning Path
  -> /campaigns/{campaign_id}/plan
  -> CampaignPlanningWorkflow
  -> build_strategy_sheet_activity
  -> build_experiment_specs_activity
  -> approve_experiments signal
  -> fetch_experiment_specs_activity
  -> create_asset_briefs_for_experiments_activity

Campaign Intent Path
  -> /clients/{client_id}/intent
  -> CampaignIntentWorkflow
  -> create_campaign_activity
  -> build_strategy_sheet_activity
  -> build_experiment_specs_activity
  -> approve_experiments signal

Funnel Path
  -> /campaigns/{campaign_id}/funnels/generate
  -> CampaignFunnelGenerationWorkflow
  -> fetch_experiment_specs_activity
  -> create_funnels_from_experiments_activity
  -> create_funnel_drafts_activity
  -> (optional) CampaignFunnelMediaEnrichmentWorkflow
  -> enrich_funnel_page_media_activity
  -> create_asset_briefs_for_experiments_activity (with funnel_map)

Creative Path
  -> /campaigns/{campaign_id}/creative/produce
  -> CreativeProductionWorkflow
  -> generate_assets_for_brief_activity
  -> approve_assets signal
```

## 4.3 Strategy V2 artifact contract map

| Artifact Type | Produced At | Required For | Consumer |
| --- | --- | --- | --- |
| `strategy_v2_stage3` | v2-09 | Angle/offer canonicalization | Strategy/experiment generation |
| `strategy_v2_offer` | v2-09 | Offer winner baseline | Strategy/brief generation |
| `strategy_v2_copy_context` | v2-09 | Copy grounding context | Asset brief/context generation |
| `strategy_v2_copy` (pre-approval) | v2-10 | Draft copy candidate | HITL final approval |
| `strategy_v2_copy` (approved envelope) | v2-11 | Approved baseline gate | Downstream prereq enforcement |
| `strategy_v2_awareness_angle_matrix` | v2-08 and v2-09 | Awareness framing | Strategy/copy context |
| `strategy_v2_step_payload` + research refs | all stages | UI stage rendering and auditability | Workflow detail + research pages |

## 5) UI Integration Blueprint (Expanded)

## 5.1 UX objective

Replace "pre-canon review" UX with **Strategy V2 pipeline operations UX**:

1. Operators see what stage is active.
2. Operators can complete required gate decisions in-page.
3. Operators can inspect generated artifacts in typed views.
4. Operators cannot submit invalid or out-of-stage decisions.

## 5.2 Page-by-page UI changes

### A) `WorkspaceOnboardingPage` + `OnboardingWizard`

Files:

1. `mos/frontend/src/pages/workspaces/WorkspaceOnboardingPage.tsx`
2. `mos/frontend/src/components/clients/OnboardingWizard.tsx`
3. `mos/frontend/src/api/clients.ts`

Changes:

1. Add `product_customizable` field in product step and include it in onboarding payload.
2. Update onboarding copy from canon/pre-canon language to Strategy V2 baseline language.
3. Update `useCreateClient` payload to set `strategyV2Enabled: true` for onboarding-created clients.
4. Keep strict client-side validation (no silent defaults for required backend fields).

Why:

1. Backend onboarding schema requires `product_customizable`.
2. Strategy V2 enablement must be deterministic for onboarding.

### B) `WorkflowsPage`

File:

1. `mos/frontend/src/pages/workflows/WorkflowsPage.tsx`

Changes:

1. Add Strategy V2 run quick filters and labels for pending HITL stage.
2. Add quick action: open Strategy V2 gate panel when `run.kind === "strategy_v2"`.

Why:

1. Operators need fast triage of blocked Strategy V2 runs.

### C) `WorkflowDetailPage` (major)

File:

1. `mos/frontend/src/pages/workflows/WorkflowDetailPage.tsx`

New components:

1. `mos/frontend/src/components/workflows/StrategyV2GatePanel.tsx`
2. `mos/frontend/src/components/workflows/StrategyV2StageTimeline.tsx`
3. `mos/frontend/src/components/workflows/StrategyV2CandidateTable.tsx`
4. `mos/frontend/src/components/workflows/StrategyV2CopyApprovalCard.tsx`

Changes:

1. Detect `run.kind === "strategy_v2"` and show dedicated Strategy V2 mode.
2. Add stage timeline based on `strategy_v2_state.current_stage`.
3. Render gate UIs based on `strategy_v2_state.pending_signal_type`.
4. Submit typed payloads for each Strategy V2 signal.
5. Replace "Pre-canon research artifacts" panel with "Strategy V2 artifacts" panel.
6. Remove `canonStory`/pre-canon-centric summary card for Strategy V2 runs.
7. Disable gate controls when run is not `running`.

Why:

1. Existing detail page handles campaign/creative gates but not Strategy V2 HITL gates.
2. Current copy and cards are pre-canon centric and do not represent Strategy V2 state.

### D) `ResearchDetailPage`

File:

1. `mos/frontend/src/pages/workflows/ResearchDetailPage.tsx`

Changes:

1. Render string content via markdown viewer.
2. Render object/array content as formatted JSON viewer.
3. Guard all `.trim()` and string operations by type checks.
4. Suppress external open action for `artifact://` URLs.

Why:

1. Strategy V2 step payload retrieval returns JSON objects for `artifact://` records.

### E) `DocumentsPage`

File:

1. `mos/frontend/src/pages/research/DocumentsPage.tsx`

Changes:

1. Use `research_artifacts` as primary source for workflow docs.
2. For `artifact://` URLs, show only in-app "View" action.
3. Replace canon/mixed badges with Strategy V2 stage labels when run kind is Strategy V2.

Why:

1. `artifact://` URLs are backend references, not browser-openable docs.

### F) `WorkspaceOverviewPage`, `ExperimentsPage`, `CampaignDetailPage`

Files:

1. `mos/frontend/src/pages/workspaces/WorkspaceOverviewPage.tsx`
2. `mos/frontend/src/pages/experiments/ExperimentsPage.tsx`
3. `mos/frontend/src/pages/campaigns/CampaignDetailPage.tsx`

Changes:

1. Replace copy that says "generated from canon and metric schema" with Strategy V2 baseline language.
2. Update labels from "angles" to "experiment specs from Strategy V2 baseline" where appropriate.
3. Keep operational campaign controls but update guidance text to Strategy V2 terms.

Why:

1. Terminology mismatch creates operator confusion and wrong mental model.

## 5.3 Frontend type + API contract updates

Files:

1. `mos/frontend/src/types/common.ts`
2. `mos/frontend/src/api/workflows.ts`

Required additions:

1. Extend `WorkflowDetail` with:
   1. `strategy_v2_state`
   2. `strategy_v2_stage3`
   3. `strategy_v2_offer`
   4. `strategy_v2_copy`
   5. `strategy_v2_copy_context`
   6. `strategy_v2_awareness_angle_matrix`
2. Define typed Strategy V2 decision payloads.
3. Add typed signal hooks:
   1. `useStrategyV2SelectAngle`
   2. `useStrategyV2SelectUmpUms`
   3. `useStrategyV2SelectOfferWinner`
   4. `useStrategyV2ApproveFinalCopy`
4. Add `useStartStrategyV2Workflow` helper for manual retrigger cases.

## 5.4 Gate payload contracts (UI must honor exactly)

| Gate | Endpoint | Required payload |
| --- | --- | --- |
| Select angle | `/signals/strategy-v2/select-angle` | `{ operator_user_id, selected_angle, rejected_angle_ids, operator_note? }` |
| Select UMP/UMS | `/signals/strategy-v2/select-ump-ums` | `{ operator_user_id, pair_id, rejected_pair_ids, operator_note? }` |
| Select offer winner | `/signals/strategy-v2/select-offer-winner` | `{ operator_user_id, variant_id, rejected_variant_ids, operator_note? }` |
| Approve final copy | `/signals/strategy-v2/approve-final-copy` | `{ operator_user_id, approved: true, operator_note? }` |

Implementation note:

1. Server should derive `operator_user_id` from auth context and stop trusting raw frontend values.

## 5.5 UI state rules

1. Gate actions only enabled when `run.status === "running"`.
2. Gate action only enabled when `pending_signal_type` matches the gate.
3. Client-side payload validation runs before sending (required fields, candidate membership).
4. Show exact backend error message and preserve operator selections.
5. After signal success, refetch workflow detail and logs immediately.

## 5.6 UI acceptance criteria

1. All four Strategy V2 gates can be completed from `WorkflowDetailPage`.
2. No runtime errors when viewing Strategy V2 research payload artifacts.
3. No dead external links for `artifact://` documents.
4. Onboarding payload always includes `product_customizable`.
5. New onboarding-created clients are Strategy V2 enabled by default.

## 6) Downstream Input Validation Audit

Status legend:

1. `Pass`: input contract is validated well.
2. `Partial`: key validations exist, but there are contract/data-integrity gaps.
3. `Fail`: missing critical validation for safe operation.

| Layer | Function/Endpoint | Validation Coverage | Status | Gap / Required Fix |
| --- | --- | --- | --- | --- |
| Router | `POST /clients/{id}/intent` | Validates client/product existence, ownership, channels, assetBriefTypes, Strategy V2 prereq | Pass | Keep |
| Router | `POST /campaigns` | Validates channels/asset_brief_types and product ownership | Pass | Keep |
| Router | `POST /campaigns/{id}/plan` | Validates campaign/product presence + Strategy V2 prereq helper | Partial | Helper must enforce final approval and run provenance |
| Router | `POST /campaigns/{id}/funnels/generate` | Validates campaign state, dedupe, duplicate experiments, requested IDs | Pass | Keep |
| Router | `POST /campaigns/{id}/creative/produce` | Validates campaign/product, requested brief IDs exist | Pass | Keep |
| Router | `POST /workflows/{id}/signals/approve-experiments` | Forwards payload without strict list-type validation | Partial | Enforce array-of-string payload schema |
| Router | Strategy V2 signal endpoints | Validates payload against strict decision contracts | Partial | Must enforce pending stage and server-injected operator identity |
| Helper | `require_strategy_v2_outputs_if_enabled` | Checks offer+copy existence | Fail | Must require approved final copy and completed run for same client/product/run |
| Activity | `create_campaign_activity` | Validates name/product/channels/types | Partial | Add product-client ownership validation for defense-in-depth |
| Activity | `build_strategy_sheet_activity` | Validates product, campaign channels/types, output sections | Partial | Still canon/metric dependent; must become Strategy V2-first |
| Activity | `build_experiment_specs_activity` | Strong schema/field/channel/metric checks | Partial | Still metric + canon/pre-canon coupled; remove pre-canon dependency |
| Activity | `fetch_experiment_specs_activity` | Validates campaign and non-empty match | Partial | Add strict type validation for `experiment_ids` input |
| Activity | `create_asset_briefs_for_experiments_activity` | Strong validation incl variant coverage, channel/format allow-lists | Pass | Keep; tighten funnel_map value type checks |
| Activity | `create_funnel_drafts_activity` | Strong campaign/product/page/template/design-system checks | Pass | Keep |
| Activity | `create_funnels_from_experiments_activity` | Strong experiment/variant object checks + strategy existence | Pass | Keep |
| Activity | `enrich_funnel_page_media_activity` | Validates required IDs/prompt and logs status | Pass | Keep |
| Workflow | `CampaignFunnelGenerationWorkflow` | Validates experiment ids, variants, concurrency, batch result shapes | Pass | Keep |
| Workflow | `CreativeProductionWorkflow` | Validates non-empty brief IDs and output asset IDs | Pass | Keep |
| Activity | `generate_assets_for_brief_activity` | Strong brief/requirements/format/swipe-source checks | Pass | Keep |

## 6.1 Critical hardening tasks generated by audit

1. Replace downstream prereq helper with approved-baseline gate:
   1. require Strategy V2 run status `completed`
   2. require `v2-11` step payload exists
   3. require approved copy envelope from final approval
2. Add run provenance to artifact retrieval:
   1. add `workflow_run_id` to `artifacts`
   2. query artifacts by run where applicable
3. Enforce signal stage matching:
   1. reject out-of-stage Strategy V2 decisions at API layer
4. Derive operator identity server-side for Strategy V2 decisions.
5. Add explicit payload schema for `approve-experiments` signal endpoint.

## 7) Backend Integration Plan (Revised Workstreams)

## Workstream A: Contract Hardening (P0)

1. Onboarding contract parity:
   1. UI sends `product_customizable`.
   2. Backend continues strict schema validation.
2. Explicit Strategy V2 enablement at client creation.
3. Strategy V2 decision identity injection from auth context.

## Workstream B: Run-Bound Artifact Integrity (P0)

1. Add `workflow_run_id` to `Artifact`.
2. Add run-scoped repository queries and indexes.
3. Use run-scoped reads in downstream resolvers and workflow detail.

## Workstream C: Downstream Gate Enforcement (P0)

1. Replace helper logic in `mos/backend/app/strategy_v2/downstream.py`:
   1. approved final step proof
   2. same-run artifact provenance
2. Update planning/intent/funnel route prereq checks to use strict gate result.

## Workstream D: Downstream Refactor To Strategy V2 Inputs (P0/P1)

1. `build_strategy_sheet_activity`:
   1. remove canon-first assumptions
   2. use Strategy V2 stage3/offer/copy/copy_context/matrix as primary input contracts
2. `build_experiment_specs_activity`:
   1. remove pre-canon angle fallback requirement
   2. use Strategy V2 selected angle and stage3 as mandatory angle source
3. Preserve strict errors when expected Strategy V2 inputs are missing.

## Workstream E: Metric Dependency Resolution (P0)

Current problem:

1. Experiment generation requires metric IDs.
2. Strategy V2 onboarding path does not generate metric artifact.

Implementation:

1. Keep current metric_schema consumer contract for now.
2. Generate `metric_schema` alongside Strategy V2 onboarding output.
3. Defer metric model redesign to separate initiative.

## Workstream F: UI Strategy V2 Operations Layer (P0)

1. Implement page and component changes in Section 5.
2. Add typed API hooks and payload contracts.
3. Add stage-aware signal submission rules.

## Workstream G: Research/Documents Alignment (P1)

1. JSON-safe rendering for research detail.
2. `artifact://` safe action handling.
3. Strategy V2 terminology update across pages.

## Workstream H: Legacy Decommissioning (P1/P2)

1. Remove pre-canon workflow and activity registration from worker.
2. Remove pre-canon-dependent UI data paths for core workflow progression.
3. Keep explicit migration completion check before deletion.

## 8) Migration And Rollout

## Phase 0: Inventory + readiness

1. Enumerate client/product pairs:
   1. Strategy V2 approved complete
   2. Strategy V2 in-progress/pending gate
   3. no Strategy V2 run
2. Identify onboarding payloads missing `product_customizable`.
3. Identify clients not explicitly Strategy V2-enabled.

## Phase 1: P0 canary

1. Deploy Workstreams A, B, C, F.
2. Canary on internal org/client set.
3. Validate:
   1. onboarding -> Strategy V2 gates -> planning/intent -> experiments -> briefs -> funnels -> creative

## Phase 2: Downstream refactor

1. Deploy Workstreams D and E.
2. Validate no pre-canon dependency in planning and experiment generation path.

## Phase 3: UI and docs alignment

1. Deploy Workstream G.
2. Validate no runtime rendering errors for artifact-backed JSON content.

## Phase 4: Legacy removal

1. Deploy Workstream H.
2. Remove pre-canon workflow from active worker config.

## 9) Test Plan

## 9.1 Backend tests

1. Add/extend tests for:
   1. strict Strategy V2 final-approval prerequisite enforcement
   2. run-scoped artifact reads
   3. stage-mismatch signal rejection
   4. operator identity server injection
   5. downstream generation using Strategy V2-only source contracts
   6. metric availability in onboarding Strategy V2 path
2. Extend:
   1. `mos/backend/tests/test_strategy_v2_workflow_api.py`
   2. `mos/backend/tests/test_strategy_v2_workflow_ordering.py`
   3. `mos/backend/tests/test_client_onboarding_v2_ordering.py`
   4. `mos/backend/tests/test_campaign_funnel_generation_selection.py`
   5. `mos/backend/tests/test_campaign_intent_activities.py`

## 9.2 Frontend tests

1. Component tests for Strategy V2 gate panel payload construction and disable rules.
2. Research detail regression tests for JSON content rendering.
3. Documents page tests for `artifact://` link behavior.
4. Onboarding wizard test for required `product_customizable`.
5. API hook tests for typed Strategy V2 signal wrappers.

## 10) Risk Register

1. Risk: downstream starts before final Strategy V2 approval.
   Mitigation: strict approved-baseline gate + run provenance.
2. Risk: stale artifact selected from a different run.
   Mitigation: run-bound artifact schema and queries.
3. Risk: workflow dead-end from out-of-stage signal.
   Mitigation: pending-stage enforcement at signal API.
4. Risk: experiment generation fails due metric dependency.
   Mitigation: generate metric schema in Strategy V2 onboarding path.
5. Risk: UI runtime errors on Strategy V2 payload artifacts.
   Mitigation: JSON-safe render path and strong type guards.

## 11) Definition Of Done

Integration is done when all are true:

1. Strategy V2 onboarding can be fully operated from UI, including all four HITL gates.
2. Campaign intent/planning/funnel/creative flows run end-to-end from Strategy V2 approved baseline.
3. Downstream prerequisite gate enforces final approval and same-run provenance.
4. No core progression path depends on pre-canon/canon workflow artifacts.
5. Worker no longer executes pre-canon workflow in production queues.
6. Downstream input validation matrix has no `Fail` rows and no unresolved `Partial` rows.
