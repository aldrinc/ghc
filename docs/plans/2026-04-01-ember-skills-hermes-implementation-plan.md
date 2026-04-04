# EMBER Skills + Hermes Implementation Plan

**Date:** 2026-04-01
**Status:** Draft for final review before implementation

## Decision

Build the EMBER refactor around four explicit layers:

1. MOS-owned system skills assets
2. Workspace/product-scoped strategy artifacts
3. Site/page runtime bindings
4. Later campaign compatibility projection

Hermes sidecar is the primary execution runtime.

MOS remains the source of truth for:

- installed skills and methodology assets
- releases and runtime profiles
- generated strategy artifacts
- approvals and bundle activation
- site/page bindings
- downstream compatibility artifacts

This implementation will not use the old approved EMBER outputs as inputs to the new local validation run.

Those approved outputs are oracle material only. They will be used after generation for diffing and quality review, not for seeding the new strategy bundle.

## Core Scope Model

### 1. System scope

Purpose: reusable operating system assets for all future strategy work.

Includes:

- skills registry
- skill releases
- methodology references
- doctrine files
- runtime profiles
- runtime bundle export metadata

These assets come from the `mos_strategy_v3` repo, but they must be copied into MOS-owned records and referenced from there at runtime.

### 2. Workspace/product strategy scope

Purpose: strategy outputs for one product before campaigns exist.

For this project:

- workspace: `Ember Gummies`
- product: `Ember: Brain Clarity Protocol`

Includes:

- foundational inputs
- signal report
- angle library
- angle selection
- knowledge base
- CSO
- offer document
- headline pool
- headline selection
- presell page
- sales page
- approvals for the human-gated steps

These are the real source-of-truth business artifacts for the new flow.

### 3. Site/page scope

Purpose: bind an approved strategy bundle to real template-backed pages and let Hermes generate draft page versions.

Includes:

- site instances
- page instances
- page context bindings
- Hermes page-copy runs
- draft page versions
- operator review and publish

### 4. Campaign scope

Purpose: later downstream delivery and publishing.

Includes:

- creative publishing
- asset briefs
- ad copy packs
- experiment specs
- launch and reporting artifacts

Campaigns should reference an approved strategy bundle. They should not own the upstream strategy artifacts.

## What This Plan Intentionally Does Not Do

- It does not replace MOS core docs or foundational docs.
- It does not make Hermes the system of record.
- It does not seed the validation campaign with preapproved EMBER offer/headline/page outputs.
- It does not silently invent missing foundational or approval artifacts.
- It does not depend on filesystem bundle paths at runtime after the skills system is wired.

## Local Validation Goal

Prove that MOS can:

1. ingest the V3 skills repo and methodology as MOS-owned assets
2. seed an EMBER strategy run from foundational inputs only
3. run Hermes stage by stage
4. persist strategy artifacts and human approvals in MOS
5. normalize approved strategy outputs into MOS compatibility contracts
6. instantiate `OMNI One Product Store`
7. run Hermes page-copy on the local Ember site
8. produce a reviewable draft page in the editor and preview

## Current State

### What exists

- A local `Ember Gummies` workspace and `Ember: Brain Clarity Protocol` product already exist.
- A manual EMBER validation campaign already exists and works as the current compatibility bridge.
- Prod foundational exports are now available locally under:
  - `/Users/aldrinclement/Documents/programming/mos_strategy_v3/FutrGroup-Hookd-Project/EMBER/prod-sync`
- The local site template `OMNI One Product Store` already exists in the DB.
- Hermes sidecar already exists and has a file-based EMBER bundle path.

### What is missing

- No native `skills` provider in campaign creative context.
- No `skill_*` artifact family in the DB enum layer.
- No MOS-owned skills registry or release model in code.
- No product-scoped strategy bundle model.
- Hermes still mounts EMBER from local files instead of MOS-owned assets and generated strategy state.
- No first-class stage runner for angle generation, approval, CSO, offer, headlines, and pages.
- No local page-copy flow bound to approved strategy bundle state.

## Architecture To Implement

## A. System Skills Asset Layer

Use new MOS-owned metadata tables based on the refactor PRD:

- `skill_packages`
- `skill_package_releases`
- `runtime_profiles`
- `workspace_skill_bindings`
- `runtime_bundle_exports`

Use these tables to represent:

- what skill exists
- which immutable release is active
- which files belong to the release
- which runtime profiles can mount those files
- which workspace/product is bound to which release set

### Import rule

The source repo remains the authoring location.

MOS stores:

- registry metadata
- release metadata
- checksums
- included-file manifests
- profile membership
- runtime export history

Hermes consumes MOS-selected releases, not arbitrary repo paths.

## B. Strategy Artifact Layer

Continue using the existing `artifacts` table for item-level payloads.

Add new artifact types:

- `skill_foundational_input`
- `skill_angle_library`
- `skill_angle_selection`
- `skill_knowledge_base`
- `skill_signal_report`
- `skill_cso`
- `skill_offer_document`
- `skill_headline_pool`
- `skill_headline_selection`
- `skill_presell_page`
- `skill_sales_page`
- `skill_brand_profile`
- `skill_runtime_bundle`

Use bundle tables from the PRD to group them:

- `project_doc_bundles`
- `project_doc_bundle_items`

For this implementation, the main bundle types are:

- `foundational_docs`
- `skills_handoff`
- `normalized_creative_context`

### Scope rule

These bundles are product-scoped in v1:

- `org_id`
- `client_id`
- `product_id`
- `campaign_id = null`

Campaign-level activation comes later as a downstream projection.

## C. Site/Page Runtime Layer

Reuse the current site runtime:

- `Site`
- `SitePage`
- `SitePageVersion`
- `SitePageContextBinding`

For this slice, bind pages to the approved strategy bundle using `SitePageContextBinding`.

The binding payload should include:

- active strategy bundle id
- selected angle artifact id
- selected offer artifact id
- selected copy-context artifact ids or derived refs
- page type
- runtime profile

No new page storage model is required to prove the flow locally.

## D. Campaign Compatibility Layer

Do not make campaigns the source of truth.

Do keep the existing compatibility seam for later downstream systems by projecting from the approved product-scoped strategy bundle into:

- `campaign_loaded_angles`
- `campaign_loaded_offer`
- `campaign_loaded_copy`
- `campaign_loaded_copy_context`
- `campaign_creative_context`

This projection happens only when needed by campaign-driven systems or when a site/page flow still depends on that packet shape.

## Required Hermes Runtime Model

Hermes must stop treating EMBER as a hardcoded filesystem bundle and instead consume MOS-built runtime projections.

### Runtime profiles to support now

- `strategy`
- `offer`
- `copy`
- `page-copy`

### Runtime projection inputs

#### Strategy-stage projection

- selected skills release assets
- methodology references
- doctrine files
- foundational inputs
- current stage outputs already approved
- explicit stage instructions

#### Page-copy projection

- selected skills release assets
- approved strategy bundle
- selected angle summary
- selected offer summary
- selected copy context
- site/page metadata
- current page `puck_data`
- slot map or bounded patch rules

### Runtime rule

Hermes owns the live loop.

MOS owns:

- what is mounted
- what stage is being run
- what inputs are approved
- where outputs are persisted
- whether the next stage is allowed to proceed

## Human Gates

The local validation run should preserve explicit HITL steps.

Required human-gated transitions:

1. approve foundational input bundle as ready
2. select approved angle from generated angle library
3. approve CSO
4. approve offer document
5. select approved headline
6. approve presell page
7. approve sales page
8. review page-copy draft before publish

No downstream stage should auto-progress past these gates.

## Detailed Stage Flow

### Stage 0: System skills import

Input:

- `mos_strategy_v3` repo

Output:

- skill packages
- skill releases
- runtime profiles
- workspace/product binding to selected release set

Review gate:

- confirm imported release manifest and profile membership

### Stage 1: Foundational seed import

Input:

- prod-synced foundational exports under `EMBER/prod-sync/foundational`

Output:

- `foundational_docs` bundle
- `skill_foundational_input` artifacts

Review gate:

- confirm bundle completeness
- explicitly record any missing required source item

Important:

- The current prod snapshot is missing `v2-02.foundation.02`.
- The system should surface that fact clearly.
- If a later strategy stage truly requires it, the run must stop with a clean missing-input error.

### Stage 2: Signal report generation

Input:

- foundational bundle
- selected skills release

Output:

- `skill_signal_report`

Review gate:

- operator approves or rejects

### Stage 3: Angle library generation

Input:

- foundational bundle
- signal report
- selected skills release

Output:

- `skill_angle_library`

Review gate:

- operator selects one angle
- persist `skill_angle_selection`

### Stage 4: Knowledge base generation

Input:

- foundational bundle
- signal report
- selected angle

Output:

- `skill_knowledge_base`

Review gate:

- operator approves or requests rerun

### Stage 5: CSO generation

Input:

- foundational bundle
- signal report
- selected angle
- knowledge base

Output:

- `skill_cso`

Review gate:

- operator approves or requests rerun

### Stage 6: Offer generation

Input:

- selected angle
- knowledge base
- CSO

Output:

- `skill_offer_document`

Review gate:

- operator approves or requests rerun

### Stage 7: Headline generation

Input:

- selected angle
- knowledge base
- CSO
- offer document

Output:

- `skill_headline_pool`

Review gate:

- operator selects approved headline
- persist `skill_headline_selection`

### Stage 8: Page generation

Input:

- selected angle
- knowledge base
- CSO
- offer document
- headline selection

Output:

- `skill_presell_page`
- `skill_sales_page`

Review gate:

- operator approves each page independently

### Stage 9: Approved strategy bundle activation

Input:

- approved strategy artifacts

Output:

- `skills_handoff` bundle

Review gate:

- confirm activatable bundle roles are present
- mark one active product-scoped strategy bundle

### Stage 10: Site/page execution

Input:

- active product-scoped strategy bundle
- instantiated `OMNI One Product Store` site
- page binding

Output:

- Hermes-generated `SitePageVersion` draft

Review gate:

- operator reviews diff and preview
- operator publishes or iterates

## Code Changes

## 1. Data model

Modify:

- `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/db/enums.py`
- `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/db/models.py`
- `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/db/migrations/versions/*`

Add:

- new `skill_*` artifact types
- bundle tables from the PRD
- skills registry / release / runtime profile tables

Decision:

- use explicit tables for registry and bundles now
- do not hide bundle semantics inside JSON-only artifacts

## 2. Strategy and compatibility services

Modify:

- `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/schemas/campaign_creative_context.py`
- `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/campaign_creative_context.py`

Add:

- native `skills` provider
- product-scoped skills bundle loader
- bundle readiness validation
- downstream compatibility normalizer

Rule:

- `skills` provider reads product-scoped approved bundles
- campaign compatibility artifacts are derived, not primary

## 3. Skills registry and runtime export services

Add new services:

- `mos/backend/app/services/skills_registry.py`
- `mos/backend/app/services/skills_releases.py`
- `mos/backend/app/services/runtime_bundle_exports.py`

Responsibilities:

- import repo skills into MOS-owned registry/release rows
- validate release manifests
- resolve runtime profile mounts
- build runtime bundle manifests for Hermes

## 4. Hermes sidecar integration

Modify:

- `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/hermes_sidecar.py`

Required changes:

- remove EMBER hardcoded file-bundle assumptions as the primary path
- support MOS-composed bundle projection
- support stage-specific strategy runs
- support page-copy runs bound to strategy bundle state

## 5. Strategy-stage execution services

Add new services or scripts:

- `mos/backend/app/services/strategy_skills.py`
- `mos/backend/scripts/run_ember_strategy_stage.py`
- `mos/backend/scripts/import_v3_skill_release.py`
- `mos/backend/scripts/import_ember_foundational_bundle.py`

Responsibilities:

- run one stage at a time
- persist draft artifact
- halt on missing prerequisites
- require explicit approval/selection before next stage

## 6. Site/page execution

Modify or add:

- `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/site_page_ai.py`
- `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/site_templates.py`
- new `mos/backend/app/services/site_page_copy_agent.py`

Responsibilities:

- instantiate real template-backed pages
- write page context bindings from approved strategy bundle state
- invoke Hermes `page-copy`
- persist new `SitePageVersion` drafts

## 7. API and operator surfaces

Modify or add routers for:

- skills release import and inspection
- product-scoped strategy bundle listing
- stage run endpoints
- approval endpoints
- bundle activation
- runtime export preview

Existing routers likely to touch:

- `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/routers/campaigns.py`
- `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/routers/site_templates.py`
- `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/routers/sites.py`

New product/workspace-scoped routes are preferred over campaign-scoped routes for the strategy stages.

## Validation Sequence

### Phase 1: Registry and import validation

- import V3 skills repo into MOS
- inspect registry rows, release rows, and runtime profiles
- verify checksums and manifest composition

### Phase 2: Foundational-to-strategy validation

- import foundational bundle only
- run Hermes stages from signal report through pages
- stop at each human gate
- persist all generated artifacts

### Phase 3: Strategy-to-site validation

- activate approved product-scoped strategy bundle
- instantiate `OMNI One Product Store`
- bind site entry page to strategy bundle
- run Hermes page-copy
- review draft page version

### Phase 4: Regression review

- compare generated outputs against:
  - current manual EMBER compatibility packet
  - current approved EMBER docs in `mos_strategy_v3`

Oracle use:

- only for quality comparison after generation
- never as a seed input to the new validation run

## Acceptance Criteria

This plan is successful when all of the following are true:

- MOS can store the V3 skills repo as first-class system assets.
- MOS can bind a workspace/product to a selected skills release.
- Hermes can run strategy stages using MOS-owned runtime projections.
- Strategy artifacts are stored at product scope, not campaign scope.
- Human gates are enforced between angle, offer, headline, and page stages.
- MOS can activate one approved product-scoped strategy bundle.
- A local Ember site can be instantiated from `OMNI One Product Store`.
- Hermes can write a new draft `SitePageVersion` against that site.
- Preview validation passes on the generated draft.
- Downstream compatibility projection is still possible for later campaign use.

## Explicit Risks

- Product-vs-campaign scope drift:
  - fix by making product scope the source of truth and campaign scope derived only when needed.
- Runtime path drift:
  - fix by loading Hermes from MOS releases, not filesystem assumptions.
- Missing foundational item:
  - fix by surfacing hard readiness errors instead of synthesizing substitutes.
- Angle stage under-modeling:
  - fix by making angle library and angle selection first-class artifacts.
- Approved oracle leakage:
  - fix by keeping old approved outputs out of the new strategy run inputs.

## Open Review Questions

- Do we want a single `skill_foundational_input` family for the imported foundation, or do we want typed foundational artifact roles immediately?
- Should strategy-stage runs get a new `WorkflowKindEnum.strategy_skills`, or should v1 use scripts and add workflow rows immediately?
- Do we want page-copy to reuse `site_page_ai.py` directly, or introduce a separate `site_page_copy_agent.py` from the start?
- Should bundle activation stay product-scoped only in v1, with campaigns always referencing the active product bundle?

## Recommended First Slice

Implement in this order:

1. skills registry, releases, runtime profiles
2. new `skill_*` artifact enums and bundle tables
3. product-scoped strategy bundle services
4. Hermes runtime composition from MOS-owned assets
5. foundational import script
6. signal report and angle stages with approvals
7. CSO, offer, headline, and page stages
8. site instantiation and Hermes page-copy

This sequence gets us to a real local EMBER validation run with the fewest architectural reversals.
