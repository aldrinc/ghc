# Langfuse Observability

This project now supports Langfuse tracing across backend LLM workflows.

## Enable tracing

Set the following environment variables in `mos/backend/.env` (or your deployment secret store):

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
LANGFUSE_TIMEOUT_SECONDS=20
```

If `LANGFUSE_ENABLED=true` and keys are missing, the backend fails fast with a clear config error.

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
