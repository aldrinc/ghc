# Taskmaster AI Tasks (GPT‑5)

Generated from `prd.txt` using Taskmaster with `gpt-5` via the OpenAI provider.

## Task List (tag: master)

- [x] 1. Monorepo scaffolding and tooling — priority: high — status: done
- [x] 2. Dev infra: Docker Compose for Postgres + Temporal + PgAdmin — priority: high — deps: 1 — status: done
- [x] 3. Backend bootstrap (FastAPI + dependencies) — priority: high — deps: 1 — status: done
- [x] 4. Configuration settings and environment management — priority: high — deps: 3 — status: done
- [x] 5. Alembic setup and initial migrations for full schema — priority: high — deps: 2,3,4 — status: done
- [x] 6. SQLAlchemy 2.x ORM models and enums — priority: high — deps: 5 — status: done
- [x] 7. Repository layer (CRUD) for core entities — priority: high — deps: 6 — status: done
- [x] 8. Pydantic v2 schemas for artifacts (definition files) — priority: high — deps: 6 — status: done
- [x] 9. Schemas for swipe assets and API DTOs — priority: medium — deps: 6 — status: done
- [x] 10. Clerk JWT verification middleware and auth dependency — priority: high — deps: 3,4 — status: done
- [x] 11. FastAPI application assembly and router skeleton — priority: high — deps: 7,8,9,10 — status: done
- [x] 12. Temporal client helper and Worker process — priority: high — deps: 2,3,4 — status: done
- [x] 13. Workflow tracking repositories and status updater — priority: high — deps: 5,7,12 — status: done
- [x] 14. Temporal workflow: ClientOnboardingWorkflow — priority: high — deps: 12,8,13 — status: done
- [x] 15. Activities: client_onboarding_activities (LLM + DB) — priority: high — deps: 7,8,14 — status: done
- [x] 16. Routers: Artifacts API (list, latest-by-type) — priority: high — deps: 11,7,8,13,14,15 — status: done
- [x] 17. Routers: Clients API + onboarding starter — priority: high — deps: 11,7,13,14,15 — status: done
- [x] 18. Temporal workflow: CampaignPlanningWorkflow — priority: high — deps: 12,8,13 — status: done
- [x] 19. Activities: strategy_activities (build StrategySheet) — priority: medium — deps: 7,8,18 — status: done
- [x] 20. Routers: Campaigns API (+ plan workflow) — priority: high — deps: 11,7,13,18,19 — status: done
- [x] 21. Temporal workflows: ExperimentDesign, CreativeProduction, ExperimentCycle, PlaybookUpdate, TestCampaign — priority: high — deps: 12,8,13,18 — status: done
- [x] 22. Activities: experiments, assets, QA, signals, playbook — priority: medium — deps: 7,8,21 — status: done
- [x] 23. Routers: Workflows signals + Experiments/Assets/Swipes APIs — priority: high — deps: 11,7,9,13,14,18,21,22 — status: done
- [x] 24. Frontend setup: Vite + React + TS + Tailwind + ShadCN UI + Clerk — priority: high — deps: 1 — status: done
- [x] 25. Frontend API client, types, and core pages (Clients, Campaigns, Swipes, Onboarding/Approvals) — priority: high — deps: 24,16,20,23 — status: done
- [x] 26. Local Postgres with Docker Compose, apply Alembic migrations, and verify backend connectivity — priority: high — deps: 5,3 — status: done
- [x] 27. Run backend and Temporal worker locally, verify health, and smoke-test workflow registration — priority: high — deps: 3,12,21 — status: done
- [ ] 28. Run frontend against local backend/Temporal with Clerk auth and validate API-backed pages — priority: high — deps: 24,25,10,27 — status: pending
- [x] 29. Workflow triggers in UI — priority: high — deps: 28 — status: done
- [x] 30. Workflow approvals UI — priority: high — deps: 29 — status: done

## Notes

- Provider/model: `openai` / `gpt-5` (no gpt-4o-mini).
- Tasks are stored in `.taskmaster/tasks/tasks.json` under tag `master`.
- Update statuses with `task-master set-status <id> <status>` and regenerate this list as needed (sync command currently broken, so this file is manual).

## Local runbook (current state)

- Infra: `cd mos/infra && docker compose up -d` (Postgres on 5433, Temporal on 7234, Temporal UI on 8234). Temporal DB name is `temporal`.
- Backend env: `mos/backend/.env` already populated (DB URL uses port 5433, Clerk issuer/JWKS/audience, OpenAI key). Python env uses 3.11 in `.venv`; deps installed via pip.
- DB/migrations: `cd mos/backend && .venv/bin/alembic upgrade head` ran successfully; schema present (17 tables). Health check `/health/db` returns `{"db":"ok"}`.
- Services: backend `uvicorn app.main:app --port 8008 --reload` and Temporal worker `python -m app.temporal.worker` both running against Temporal at `localhost:7234`. Smoke workflow `TestCampaignWorkflow` executed end-to-end (seed org 23c24cde-9627-4b19-b308-81d612b41eac, client 9d0fb398-0133-47f3-9d19-ca6454ca2af6).
- Frontend: `cd mos/frontend && npm install` then `npm run dev -- --host --port 5275` (Vite, Clerk publishable key set in `.env.local`, API base http://localhost:8008). UI serves at http://localhost:5275; Clerk sign-in required. After signing in you can: create clients and start onboarding; create campaigns and start planning; view workflow runs, refresh, and send approval/stop signals from the Workflows tab.
- Auth/org: backend now requires a real Clerk JWT (no dev fallbacks) and expects an organization claim. Create a Clerk JWT template (e.g., `backend`) that includes `org_id: {{organization.id}}` (and optionally slug/role), then set `VITE_CLERK_JWT_TEMPLATE=backend` in `frontend/.env.local`. The frontend forces a fresh token (`skipCache`) so org selection updates immediately. Select an active organization in Clerk so the token contains org context. The backend will auto-create an org row when a new external org_id is seen.
- CORS: configure `BACKEND_CORS_ORIGINS` (JSON array) in `mos/backend/.env` to match the allowed frontend origins (defaults to localhost/127.0.0.1 on port 5275).
- Smoke tests: `mos/backend/SMOKE_TESTS.md` lists curl commands with Clerk dev JWTs. Automated API coverage lives in `mos/backend/tests` and runs via `.venv/bin/pytest`.
