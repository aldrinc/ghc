# GHC Backend

## Deep research background jobs
- Step 4 of the pre-canon workflow now runs via OpenAI background `responses` and persists to `deep_research_jobs`.
- Set `OPENAI_API_KEY` and `OPENAI_WEBHOOK_SECRET` in `.env`; run migrations (`alembic upgrade head`) to add the table.
- Webhook endpoint: `POST /openai/webhook` (raw body, OpenAI signature verified). Expose it via ngrok when testing locally.
- Manual controls: `GET /deep-research/jobs/{job_id}`, `POST /deep-research/jobs/{job_id}/refresh`, `POST /deep-research/jobs/{job_id}/cancel`.
- Temporal activity falls back to polling until a terminal status; webhooks reconcile final state and persist `output_text` + full response JSON.
