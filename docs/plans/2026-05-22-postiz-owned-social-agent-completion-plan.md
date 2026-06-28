# Implementation Plan: Postiz-Owned Social Agent Completion

Status: In progress  
Owner: Codex / Aldrin  
Date: 2026-05-22  

## Goal

Complete the next implementation slice for Connected Social Agents and the TikTok Carousel Agent while preserving Postiz as the system of record for posting, scheduling, publishing, and social post status.

## Decision

mOS should not create a second social posting product.

mOS owns:

- agent strategy and reasoning inputs
- content growth programs
- carousel variants and slides
- approvals
- Postiz handoff/action proposals
- conversion sources and conversion events
- source-backed attribution references

Postiz owns:

- connected social channels used for publishing
- composer/calendar/scheduling/publishing
- post ids, release ids, post status, and post lifecycle
- provider-specific posting details

## Implement

- Remove the new `content_publications`, `content_performance_snapshots`, and `content_attributions` layer from the growth-program migration and ORM models.
- Remove the growth-program `/publications` API that duplicates Postiz posting state.
- Add an approval-gated Postiz handoff endpoint for an approved variant:
  - validates the growth program and variant
  - requires variant approval
  - creates an `agent_action_proposals` record targeting Postiz
  - stores the intended Postiz composer payload in `proposed_after_json`
- Extend conversion events with optional `contentVariantId`, `postizPostId`, and `postizChannelId` references so conversion data can point at Postiz-owned posts without cloning Postiz state.
- Update runtime profiles to say Postiz remains the posting system of record.
- Update targeted tests and proof artifacts.

## Do Not Implement

- Do not execute live Postiz writes.
- Do not replicate Postiz calendar/post status tables in the growth-program layer.
- Do not change models/providers.
- Do not deploy or restart services.

## Acceptance

- No new `content_publications` table/class/route remains in the Connected Social/TikTok growth slice.
- Approved TikTok carousel variants can create Postiz action proposals.
- Unapproved variants cannot create Postiz handoff proposals.
- Conversion events can reference concrete Postiz ids without local post duplication.
- Targeted backend tests pass.
- `planctl verify` passes.

## Verification Commands

- `cd mos/backend && uv run pytest tests/test_connected_social_agents.py tests/test_tiktok_growth_programs.py`
- `cd mos/backend && uv run python -m py_compile app/routers/growth_programs.py app/schemas/growth_programs.py app/db/repositories/growth_programs.py app/db/models.py app/services/skills_runtime_registry.py`
- `cd mos/backend && uv run alembic heads`
- `/Users/aldrinclement/.codex/bin/planctl verify docs/plans/2026-05-22-postiz-owned-social-agent-completion-plan.contract.json`

## Expected Files

- `mos/backend/app/db/models.py`
- `mos/backend/alembic/versions/0098_connected_social_growth_agents.py`
- `mos/backend/app/schemas/growth_programs.py`
- `mos/backend/app/db/repositories/growth_programs.py`
- `mos/backend/app/routers/growth_programs.py`
- `mos/backend/app/services/skills_runtime_registry.py`
- `mos/backend/tests/test_connected_social_agents.py`
- `mos/backend/tests/test_tiktok_growth_programs.py`
- `docs/plans/2026-05-22-larry-tiktok-carousel-agent-prd.md`

## Speed Map

Parallelizable: local parallel reads and verification only.

Parallelization map:

- Schema/model/migration correction.
- Router/repository handoff endpoint.
- Runtime profile and PRD wording update.
- Tests/proof.

Single-agent reason: edits touch shared models, migration, router, schemas, and tests where one integration pass is safer than split writers.

Expected speed gain: local parallel reads/checks reduce wait time; native sub-agents are not worth coordination cost for this narrow correction.

Token spend justification: single-lane implementation keeps review faster.

Write ownership: main thread owns all listed files.

Fan-in plan: targeted backend tests and contract verification.

Validation owner: main thread.

Meta-tooling opportunity: later add a guard test that rejects new social-posting ledger tables outside Postiz.

## Stop Condition

Stop when tests, compile, migration head, lane proof, plan gate, source manifests, proof dashboard, and `planctl verify` pass.
