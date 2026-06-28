# Implementation Plan: Connected Social Agents + TikTok Carousel Agent Foundation

Status: In progress  
Owner: Codex / Aldrin  
Date: 2026-05-22  
Source PRDs:

- `docs/plans/2026-05-22-meta-ads-social-agent-prd.md`
- `docs/plans/2026-05-22-larry-tiktok-carousel-agent-prd.md`

## Goal

Land the first implementation foundation for:

- Connected Social Agents.
- TikTok Carousel Agent.

This pass should create durable backend primitives, API surfaces, Postiz analytics/reconciliation adapter methods, and Hermes runtime profile registration. It should not perform live external writes, deploy, change production services, or change configured LLM models.

## Scope

### Implement

- Shared `agent_action_proposals` table and CRUD/approval endpoints.
- Connected social provider inventory/snapshot tables sufficient for future Meta/Postiz assets.
- Content growth program tables for TikTok carousel experiments and conversion sources.
- Backend schemas/repositories/routes for creating programs, experiments, variants, slide drafts, approval records, and read-only listings.
- Postiz client extensions for analytics and release-id reconciliation surfaces.
- Hermes runtime profiles:
  - `meta-ads-manager`
  - `social-media-manager`
  - `tiktok-carousel-growth-manager`
- Targeted tests for schema/API behavior and adapter payload construction where practical.

### Do Not Implement In This Pass

- Live Meta OAuth app approval flow.
- Full frontend builder/calendar UI.
- Direct TikTok publishing outside Postiz.
- Autonomous posting/spend changes.
- Model/provider changes.
- Production deployment or service restart.

## Acceptance

- New migration defines tables and indexes.
- FastAPI app imports and includes new routers.
- New schemas validate API payloads without fake data.
- Runtime registry exposes three new profiles.
- Tests pass for the new backend slices.
- `planctl verify` passes.

## Verification Commands

- `cd mos/backend && uv run pytest tests/test_connected_social_agents.py tests/test_tiktok_growth_programs.py`
- `/Users/aldrinclement/.codex/bin/planctl verify docs/plans/2026-05-22-connected-social-tiktok-implementation-plan.contract.json`

## Expected Files

- `mos/backend/app/db/models.py`
- `mos/backend/alembic/versions/0098_connected_social_growth_agents.py`
- `mos/backend/app/schemas/connected_social.py`
- `mos/backend/app/schemas/growth_programs.py`
- `mos/backend/app/db/repositories/connected_social.py`
- `mos/backend/app/db/repositories/growth_programs.py`
- `mos/backend/app/routers/connected_social.py`
- `mos/backend/app/routers/growth_programs.py`
- `mos/backend/app/main.py`
- `mos/backend/app/services/postiz_client.py`
- `mos/backend/app/services/skills_runtime_registry.py`
- `mos/backend/tests/test_connected_social_agents.py`
- `mos/backend/tests/test_tiktok_growth_programs.py`

## Speed Map

Parallelizable: local parallel reads only. Native sub-agents not used because the user did not explicitly ask for sub-agent delegation in this message.

Parallelization map:

- Data model and migration.
- Schemas/repositories/routes.
- Postiz adapter extensions.
- Runtime profile registration.
- Tests and proof.

Expected speed gain: moderate through local parallel file reads and focused test runs.

Fan-in: API tests become the integration point for models, routers, and runtime profile exposure.

## Stop Condition

Stop when the contract and targeted tests pass, or report blocked items with exact failing commands and reasons.
