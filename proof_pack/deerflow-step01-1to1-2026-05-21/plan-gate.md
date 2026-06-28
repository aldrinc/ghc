# Strategy V2 Step 1 DeerFlow Plan Gate

## Goal Artifact

Run the same Strategy V2 foundational Step 1 competitor research process used by GPT, but through DeerFlow with DeepSeek V4 Pro. Preserve prompt parity, tool access, output shape, citations, and scoring behavior.

Success means:
- The rendered prompt comes from `V2 Fixes/Foundational Docs/clean_prompts/01_competitor_research_v2.md`.
- The same `<SUMMARY>` and `<CONTENT>` guardrail is applied.
- DeerFlow exposes web search, web fetch, and calculator tooling.
- Output completes Phases 1-9 with cited competitor research and D1-D5 scoring.
- The result is auditable against the GPT production Step 1 artifact.

## Problem Log

- Earlier evaluation used the wrong Step 1 prompt path, so the report was not 1:1 with the production Strategy V2 flow.
- DSV4 Pro cannot be judged fairly from a shallow final-only or smoke harness when the production GPT path used a tool-enabled research process.
- DeerFlow file-write tools caused a stall in Attempt 1 when DSV4 emitted an empty `write_file` call.
- The production export does not include the raw onboarding payload, so context must be reconstructed only from exported concrete evidence.

## Root-Cause Diagnosis

Root cause: process parity was not enforced as a machine-checkable contract before execution.

5-why chain:
- Why was the output bad? It was produced from the wrong/non-production prompt path.
- Why did that happen? The foundational prompt mapping was assumed instead of traced through `strategy_v2_activities.py`.
- Why did the harness diverge? The run was optimized for a DeerFlow smoke path before confirming production Step 1 semantics.
- Why did the first full run stall? DeerFlow exposed persistence tools that production GPT Step 1 did not need the model to call directly.
- Why could this recur? Without prompt-hash, tool-call, and artifact validation, a run can look complete while being non-1:1.

## Current Machine

Manual investigation plus ad hoc DeerFlow execution. Prompt source, guardrails, model config, tool access, citations, and scored outputs were not all verified in one contract.

## Designed Machine

Use a proof-pack wrapper:
- Render production Strategy V2 Step 1 from the real code path.
- Store prompt hashes and rendered variables.
- Run DSV4 Pro in DeerFlow with web search, web fetch, calculator, thinking enabled, and no output-token cap.
- Persist final output outside model file-write tools.
- Postprocess event logs for tool calls, URLs, tags, phase coverage, D1-D5 scoring, and citation counts.
- Verify source manifest, provenance, lane proof, and plan contract.

## Worst-Day Test

If DSV4 Pro produces a polished but shallow report, validation must catch missing phases, missing tags, missing calculator use, missing citation URLs, or wrong prompt path.

If DeerFlow tool calls stall, the run must fail visibly and preserve the attempt log instead of silently promoting a partial artifact.

## Leading And Lagging Metrics

Leading:
- Prompt path and prompt hash match Strategy V2 Step 1.
- Tool-call count includes web search/fetch and calculator.
- Citation URL count is nonzero and recorded.
- Tags and phase headings pass parser checks.

Lagging:
- Content length and coverage are comparable to the GPT Step 1 reference.
- Competitor list and scoring table are useful enough for downstream foundational docs.
- Cost/time profile is visible before replacing GPT as primary.

## Owner Date Review

Owner: Codex execution agent.

Date: 2026-05-21.

Review point: after DeerFlow output, postprocess validation, source manifest, provenance check, and planctl verification complete.

## Stop Condition

Stop only when one of these is true:
- The 1:1 DeerFlow Step 1 run passes validation and proof gates.
- A blocker requires missing external data, credentials, money, or production access.
- The run fails in a reproducible way with logs and repair notes preserved.
