# Strategy V2 Backend Implementation Plan

## Status Legend
- `[ ]` pending
- `[x]` completed

## Phase 1: Contracts, Models, and Feature Flag
- [x] Add strict Pydantic schema models for Stage 0-3 contracts.
- [x] Add schema version enforcement helpers and hard-fail error classes.
- [x] Add `strategy_v2_enabled` workspace/client-level flag support in settings and retrieval.
- [x] Add workflow/artifact enum values and migration for Strategy V2 outputs.
- [x] Compile/type-check backend after phase edits.

## Phase 2: Translation Layer and Scorer Wrappers
- [x] Implement translation mappers for Stage 0/1 inputs from current artifacts.
- [x] Implement Offer input mapping and Offer->Copy bridge mapping.
- [x] Integrate deterministic scorer wrappers for VOC/Angle, Offer, and Copy scorers via Python imports.
- [x] Add unit tests for mappers and scorer wrappers.
- [x] Compile/type-check backend after phase edits.

## Phase 3: Temporal Workflow and Activities
- [x] Add Strategy V2 Temporal workflow with step keys `v2-01` to `v2-11`.
- [x] Add activities for VOC+Angle, Offer pipeline, Copy pipeline, and artifact persistence.
- [x] Add explicit HITL signal gates: angle select, UMP/UMS select, offer winner, final copy approval.
- [x] Persist decision payloads and operator metadata as research artifacts.
- [x] Compile/type-check backend after phase edits.

## Phase 4: API Integration and Onboarding Wiring
- [x] Expose Strategy V2 workflow state, pending decisions, summaries, and artifact refs in workflows API.
- [x] Add explicit API endpoints for all Strategy V2 HITL decisions.
- [x] Wire Strategy V2 launch from onboarding completion and standalone trigger path.
- [x] Wire downstream campaign workflows to consume V2 artifacts first, with explicit errors if required artifacts are missing.
- [x] Compile/type-check backend after phase edits.

## Phase 5: Tests and Rollout Controls
- [x] Add Temporal workflow pause/resume tests for signal flow.
- [x] Add Stage 0->final copy integration test with artifact checks.
- [x] Add feature-flag gated rollout behavior tests.
- [x] Run full backend test suite and capture results.
- [x] Compile/type-check backend after phase edits.

## Completion
- [x] All phases complete.
