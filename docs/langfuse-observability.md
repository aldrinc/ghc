# Langfuse Observability

This project now supports Langfuse tracing across backend LLM workflows.

## Enable tracing

Set the following environment variables in backend runtime env (local: `mos/backend/.env`; Docker deploy: repo-root `.env.production`; or your secret manager):

```env
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
# Optional override. If set, this is used instead of LANGFUSE_HOST.
LANGFUSE_BASE_URL=
LANGFUSE_ENVIRONMENT=development
LANGFUSE_RELEASE=
LANGFUSE_SAMPLE_RATE=1.0
LANGFUSE_DEBUG=false
LANGFUSE_REQUIRED=false
LANGFUSE_AUTH_CHECK=true
LANGFUSE_TIMEOUT_SECONDS=20
```

If `LANGFUSE_REQUIRED=true`, startup fails when tracing is disabled.
If `LANGFUSE_AUTH_CHECK=true`, startup fails when Langfuse host/keys are invalid.

## Cloud to self-host migration

No code changes are required.

1. Keep `LANGFUSE_ENABLED=true`.
2. Point `LANGFUSE_HOST` (or `LANGFUSE_BASE_URL`) to your self-hosted Langfuse endpoint.
3. Rotate `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` to the self-hosted project keys.
4. Restart API + Temporal worker processes.

## What is traced

- Shared LLM client calls (`OpenAI`, `Anthropic`, `Gemini`).
- Deep research OpenAI flows.
- Claude chat streaming route.
- Gemini ad breakdown and swipe-image generation activities.
- Agent tool-run context (mapped to `agent_run` / tool-call identifiers).

Trace context is attached with existing workflow identifiers (`workflow_run_id`, `temporal_workflow_id`, `agent_run_id`) so Langfuse UI can be filtered by MOS run IDs.

## Troubleshooting missing traces

1. Clear Langfuse UI filters (especially `Trace Name` and `Environment`) and widen time range before concluding traces are missing.
2. Confirm both API and Temporal worker have `LANGFUSE_ENABLED=true` and valid keys in the same runtime env.
3. Set `LANGFUSE_ENVIRONMENT` explicitly (for example `production`) so traces are easy to locate by environment.
4. Keep `LANGFUSE_AUTH_CHECK=true` and `LANGFUSE_REQUIRED=true` in production so misconfiguration fails at startup instead of silently dropping traces.
