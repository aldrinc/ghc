# Strategy V2 Parser Replay Report

- Date: `2026-03-04`
- Workflow ID: `strategy-v2-0d3186be-2c4f-4d5d-a810-d87b3b35265e-dc897cce-ac0d-41d6-b857-66e7468080a5-502a0317-3e6a-484e-b114-1eaeee68b334-b206f2e3-0e28-4bec-b5f0-ab86f7a0ecf1`
- Run ID: `e4b2755c-5298-4df4-a890-766d20b1a401`
- Replay source: `mos/backend/artifact-downloads/strategy_v2_copy_loop_report_2026-03-04_run_e4b2755c.md`
- Extracted payload chars: `16000`

## What was replayed
- Used the captured `sales_template_payload_json_failed` block from the failed run report.
- Replayed parser path locally with current backend code.
- No AI prompts or workflow runs were rerun.

## Replay results
1. **Strict parser (`_parse_json_response_strict`)**
- Result: `FAIL`
- Error: `Failed to parse JSON object for 'sales_template_payload': Extra data: line 1 column 1530 (char 1529)`

2. **Legacy parser (`_parse_json_response`)**
- Result: `PASS` (incorrect behavior)
- Parsed top-level keys: `['hero', 'problem', 'problem_image_alt']`
- This shows the old parser accepted only the first JSON object fragment and silently ignored trailing content.

## Why this matters
- The strict parser now fails fast on malformed/trailing JSON instead of allowing partial-object parsing.
- Copy-loop retries are now short-circuited for sales payload parser/schema failures, so we do not regenerate full AI steps for that class of failure.

## Code changes validated
- Strict parser for sales payload JSON in copy pipeline.
- Sales payload normalization/upgrader applied before strict validation.
- Parser/schema failures treated as non-retryable for page generation attempts.
- Added tests for strict parsing, non-retryable classification, and legacy sales payload normalization.

## Test runs
- `pytest -q tests/test_strategy_v2_copy_pipeline_guards.py -k "parse_json_response_strict or non_retryable_sales_payload_failure"` -> `PASS`
- `pytest -q tests/test_strategy_v2_template_bridge.py -k "upgrade_sales_payload_normalizes_common_legacy_keys or inspect_template_payload_validation"` -> `PASS`
- `python -m py_compile app/strategy_v2/template_bridge.py app/temporal/activities/strategy_v2_activities.py` -> `PASS`
