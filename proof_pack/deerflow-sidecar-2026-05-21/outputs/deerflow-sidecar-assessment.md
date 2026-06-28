# DeerFlow Sidecar Assessment

## Verdict

DeerFlow sidecar execution is viable for Step 01 research, but not ready to make primary without a production wrapper.

## What Passed

- DeerFlow configured with DeepSeek V4 Pro, Serper search, Jina fetch, local sandbox, and token usage enabled.
- Doctor passed with expected warnings only.
- Final-only Step 01 smoke completed in 175.839 seconds.
- Tool usage stayed inside bounds: 2 web searches and 2 web fetches.
- Source manifest verification passed.
- `provcheck` passed with 11 warnings.

## Main Weaknesses

- DeepSeek V4 Pro got stuck when asked to stream a large `write_file` tool call. Wrapper should persist final output, not ask the model to write the report file.
- Final Markdown included process chatter before the report. Wrapper should strip interim assistant text and retain only the final report block.
- Citation claims are better than the GPT example, but not strict enough. `provcheck` warnings and line review show some factual-looking values lacked nearby provenance.
- Snippet-only evidence was mixed into the competitor list. Production schema needs `evidence_tier` per claim: `full_page`, `snippet`, or `secondary`.
- The model self-graded as PASS. The orchestrator should grade pass/fail, not the model.

## Recommendation

Use DeerFlow as the Step 01-03 sidecar harness, with a wrapper that owns file writing, citation validation, source manifests, evidence-tier tagging, and structured JSON output. Do not plug this directly into the primary workflow yet.
