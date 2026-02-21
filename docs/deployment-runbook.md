# Deployment Runbook (mOS Platform)

This doc captures what is required to ship the current stack (FastAPI + Temporal worker + Vite/React frontend).

## Services & Prereqs
- Postgres 16 reachable by the API and worker (migrations live in `mos/backend/alembic`).
- Temporal server/UI reachable by the worker and API; default dev compose exposes `temporal:7233` inside the network and `localhost:7234` on the host.
- Clerk instance with an org-bearing JWT template (used by backend auth and frontend).
- LLM providers: OpenAI (required), Anthropic/Gemini (optional but used by several activities).
- Google Drive access for research artifacts (service account or OAuth) and Apify token for ads ingestion.

## Environment configuration
- Backend core: `ENVIRONMENT`, `DATABASE_URL`, `CLERK_JWT_ISSUER`, `CLERK_JWKS_URL`, `CLERK_AUDIENCE`, `BACKEND_CORS_ORIGINS`, `TEMPORAL_NAMESPACE`, `TEMPORAL_TASK_QUEUE`, `OPENAI_API_KEY`, `OPENAI_WEBHOOK_SECRET`.
- Observability (Langfuse): `LANGFUSE_ENABLED`, `LANGFUSE_REQUIRED`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`/`LANGFUSE_BASE_URL`, `LANGFUSE_ENVIRONMENT`, `LANGFUSE_SAMPLE_RATE`, `LANGFUSE_AUTH_CHECK`, `LANGFUSE_TIMEOUT_SECONDS`.
- LLM/research tuning: `LLM_DEFAULT_MODEL`, `LLM_REQUEST_TIMEOUT`, `LLM_REQUEST_RETRIES`, `LLM_POLL_INTERVAL_SECONDS`, `LLM_POLL_TIMEOUT_SECONDS`, `DEEP_RESEARCH_POLL_TIMEOUT_SECONDS`, `O3_DEEP_RESEARCH_MAX_OUTPUT_TOKENS`, `PRECANON_STEP04_MODEL`, `PRECANON_STEP04_MAX_TOKENS`, `PRECANON_STEP04_START_TO_CLOSE_MINUTES`, `PRECANON_STEP04_SCHEDULE_TO_CLOSE_MINUTES`, `PRECANON_STEP0{1,3,6,7,8,9}_MODEL`.
- Google/Drive: `GOOGLE_APPLICATION_CREDENTIALS` (preferred) or `GOOGLE_CLIENT_EMAIL`/`GOOGLE_PRIVATE_KEY`; optional OAuth `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/`GOOGLE_REFRESH_TOKEN`; `RESEARCH_DRIVE_PARENT_FOLDER_ID` or `PARENT_FOLDER_ID`.
- Ads ingestion: `APIFY_API_TOKEN`, optional `APIFY_META_ACTOR_ID`, `APIFY_META_ACTIVE_STATUS`, `APIFY_META_COUNTRY_CODE`, and tuning knobs `ADS_CONTEXT_MAX_MEDIA_ASSETS`, `ADS_CONTEXT_MAX_BREAKDOWN_ADS`, `ADS_CONTEXT_MAX_HIGHLIGHT_ADS`, `ADS_CONTEXT_MAX_ADS_PER_BRAND`, `ADS_CONTEXT_PRIMARY_TEXT_LIMIT`, `ADS_CONTEXT_HEADLINE_LIMIT`.
- Shopify bridge integration (required for Shopify connection/product mapping/checkout): `SHOPIFY_APP_BASE_URL`, `SHOPIFY_INTERNAL_API_TOKEN`, optional `SHOPIFY_ORDER_WEBHOOK_SECRET`.
  - `SHOPIFY_APP_BASE_URL` should point to your deployed `shopify-funnel-app` host (for example `https://shopify.moshq.app`).
  - `SHOPIFY_INTERNAL_API_TOKEN` must match the token configured on `shopify-funnel-app`.
- LLM providers: `ANTHROPIC_API_KEY`, `ANTHROPIC_API_BASE_URL` (optional), `GEMINI_API_KEY`, `OPENAI_BASE_URL` (optional).
- Unsplash: `UNSPLASH_ACCESS_KEY` for stock image lookups during funnel image generation.
- Frontend: set `VITE_CLERK_PUBLISHABLE_KEY`, `VITE_API_BASE_URL` (point to deployed backend), and `VITE_CLERK_JWT_TEMPLATE` (defaults to `backend`).
- Secrets live in `.env` locally; move them to your deployment secret manager and keep `.env` files out of images/artifacts.

## Build and release
- Database: `cd mos/backend && .venv/bin/alembic upgrade head` (applies migrations up to `0013_ad_scores.py`).
- Backend API (Python 3.11): `cd mos/backend && .venv/bin/pip install . && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8008`.
- Temporal worker: `cd mos/backend && .venv/bin/python -m app.temporal.worker` (shares the same env/secrets as the API).
- Frontend: `cd mos/frontend && npm ci && npm run build`; serve `mos/frontend/dist` via a static server (e.g., nginx, Vercel, S3+CloudFront). Use `.env.production` to inject deploy-time `VITE_*` values.
- Local infra helper: `cd mos/infra && docker compose up -d` brings up Postgres (5433), Temporal (7234), Temporal UI (8234), and PgAdmin (8081). Swap to managed services for production.
- Containerization: build backend image `docker build -t mos-backend -f mos/backend/Dockerfile mos/backend` (override command to run the worker: `docker run ... python -m app.temporal.worker`); build frontend image `docker build -t mos-frontend -f mos/frontend/Dockerfile mos/frontend --build-arg VITE_API_BASE_URL=https://api.example.com --build-arg VITE_CLERK_PUBLISHABLE_KEY=... --build-arg VITE_CLERK_JWT_TEMPLATE=backend`.
- CI/CD: `.github/workflows/docker-images.yml` runs backend pytest + alembic against Postgres, builds the frontend, then builds/pushes images to GHCR (main only). Deploy job (guarded by `ENABLE_PRODUCTION_CD` repo var or manual dispatch) SSHes to a target host and runs `docker compose -f mos/infra/docker-compose.deploy.yml up -d`; requires `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_PATH`, `GHCR_USERNAME`, and `GHCR_TOKEN` secrets plus a `.env.production` file on the host.
- Deploy compose: `mos/infra/docker-compose.deploy.yml` expects `.env.production` two directories up (repo root) with all backend/worker env vars. Set `IMAGE_REGISTRY`/`IMAGE_TAG` to point at GHCR images.

## Verification checklist
- Health: `curl -i https://<backend>/health` and `/health/db`.
- Tests: `cd mos/backend && .venv/bin/pytest` (currently passing); `cd mos/frontend && npm run build` (passing, with a chunk-size warning).
- Migrations: `cd mos/backend && .venv/bin/alembic current` should report head.
- Temporal: confirm namespace/task queue reachable and workflows visible in Temporal UI.
- API smoke: follow `mos/backend/SMOKE_TESTS.md` with a real Clerk JWT to exercise clients, campaigns, workflows, artifacts, assets, and swipes.
- Frontend: sign in via Clerk, create a client, start onboarding, run campaign planning, and verify workflow detail/approvals and library tabs against the deployed API.

## Known gaps / follow-ups
- Frontend bundle emits a >500 kB chunk; consider code-splitting or adjusting `build.chunkSizeWarningLimit` if this impacts your hosting limits.
- Taskmaster task 28 (“run frontend against local backend/Temporal with Clerk auth”) is still pending; complete it as a final pre-deploy validation pass.
