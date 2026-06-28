# DeerFlow Sidecar Execution Plan

## Goal

Run DeerFlow as a local sidecar spike for foundational docs Step 01 using DeepSeek V4 Pro, Serper, and Jina, without touching production workflow behavior.

## Acceptance

- DeerFlow source is present under `.local/deer-flow`.
- Native DeerFlow config and run path are inspected.
- A local-only sidecar config or wrapper exists outside tracked code.
- A small Step 01 smoke run executes, or the blocker is captured with exact logs.
- Proof artifacts record command output, config shape, and run status.

## Work Items

- Clone or refresh DeerFlow into `.local/deer-flow`.
- Inspect model, search, crawler, and sandbox configuration.
- Configure DeepSeek V4 Pro, Serper, and Jina for local execution only.
- Run a minimal Step 01 sidecar smoke test.
- Verify the proof pack and summarize readiness.
