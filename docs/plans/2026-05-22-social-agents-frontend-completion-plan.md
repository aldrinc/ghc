# Implementation Plan: Social Agents Frontend Completion

Status: In progress  
Owner: Codex / Aldrin  
Date: 2026-05-22  

## Goal

Make the Connected Social Agents and TikTok Carousel Agent backend usable inside MOS without moving posting, scheduling, publishing, or post lifecycle state out of Postiz.

## Scope

Implement:

- Frontend types and API hooks for connected social assets, action proposals, growth programs, experiments, variants, conversion sources, conversion events, and Postiz handoff proposals.
- Workspace execution page for Social Agents.
- Navigation route under Execution.
- Operator workflow for:
  - inspect Postiz channel/profile readiness
  - create a TikTok carousel growth program
  - create a conversion source
  - draft a six-slide variant
  - approve the variant
  - create a Postiz handoff proposal
  - view action proposal queue
- Targeted frontend test.

Do not implement:

- Live Postiz execution from the growth page.
- Social posting state replication in growth-program tables.
- Production deployment, service restart, or model changes.

## Design Notes

Visual thesis: quiet operations console with one clear work path, dense status, and no marketing hero.

Content plan:

- Workspace readiness and Postiz ownership boundary.
- TikTok carousel workflow.
- Connected social inventory and action queue.

Interaction thesis:

- Simple tabbed work surface.
- Fast form-to-queue flow.
- Status badges and compact tables for review.

## Acceptance

- `/workspaces/execution/social-agents` renders with a selected workspace.
- Page has a no-workspace empty state.
- API hooks invalidate relevant queries after mutations.
- Postiz handoff form never calls the Postiz publish endpoint directly.
- Tests cover the page contract.
- `planctl verify` passes.

## Verification Commands

- `cd mos/frontend && npm run test:unit -- src/pages/workspaces/SocialAgentsPage.test.tsx`
- `cd mos/frontend && npm run build`
- `/Users/aldrinclement/.codex/bin/planctl verify docs/plans/2026-05-22-social-agents-frontend-completion-plan.contract.json`

## Expected Files

- `mos/frontend/src/types/socialAgents.ts`
- `mos/frontend/src/api/socialAgents.ts`
- `mos/frontend/src/pages/workspaces/SocialAgentsPage.tsx`
- `mos/frontend/src/pages/workspaces/SocialAgentsPage.test.tsx`
- `mos/frontend/src/App.tsx`
- `mos/frontend/src/app/AppShell.tsx`
- `mos/frontend/src/app/routes.tsx`

## Speed Map

Parallelizable: local reads and verification only.

Single-agent reason: frontend page, hooks, routes, and tests are tightly coupled and easier to integrate in one lane.

Validation owner: main thread.

Stop when tests, build, browser smoke, proof gates, and contract pass.
