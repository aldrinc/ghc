# DeerFlow DSV4 Pro Step 1 1:1 Plan

## Objective

Run Strategy V2 foundational Step 1 for the Tenor production example through DeerFlow using `deepseek-v4-pro`, matching the GPT workflow input and execution contract as closely as the exported artifacts allow.

## Contract

1. Render the real Strategy V2 foundational Step 1 prompt from `V2 Fixes/Foundational Docs/clean_prompts/01_competitor_research_v2.md`.
2. Use the same tagged-output guardrail shape from `strategy_v2_activities._append_tagged_output_guardrails`.
3. Use the Tenor production Stage 0 artifact and recovered Strategy V2 context.
4. Use `CATEGORY_NICHE=supplement`, matching the production activity log.
5. Run through DeerFlow with `deepseek-v4-pro`, thinking enabled, web search/fetch enabled, no output-token cap.
6. Provide a calculator tool so scoring/ranking can be tool-computed.
7. Save raw output, parsed `<SUMMARY>` and `<CONTENT>`, event log, source manifest, and comparison against the GPT artifact.
8. Validate prompt shape, tags, citations, competitor coverage, scoring table, and completion of Phases 1-9.

## Known Delta

The production export does not include the raw `onboarding_payload` row used inside `BUSINESS_CONTEXT_JSON`. The run uses only concrete fields preserved in exported Stage 0, activity logs, workflow input, and Step 3 echo text. This delta is recorded in metadata.

## Verification

- Rendered prompt exists and contains the v2 Step 1 prompt, not the older PreCanon prompt.
- DeerFlow config exposes `web_search`, `web_fetch`, and `calculator`.
- Raw DSV4 output has `<SUMMARY>` and `<CONTENT>` blocks.
- Output includes Phase 1-9 headings.
- Output includes a ranked traction table with D1-D5 and scores.
- Output cites sources with URLs.
- Source manifest verifies.
- Plan contract verifies.
