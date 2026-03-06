# Strategy V2 Copy Loop Report

- Workflow ID: `strategy-v2-0d3186be-2c4f-4d5d-a810-d87b3b35265e-dc897cce-ac0d-41d6-b857-66e7468080a5-502a0317-3e6a-484e-b114-1eaeee68b334-b206f2e3-0e28-4bec-b5f0-ab86f7a0ecf1`
- Run ID: `3e2082eb-08b6-4bf6-a5e1-62e1a11ddec1`
- Started (UTC): `2026-03-04T20:12:42.813361Z`
- Closed (UTC): `2026-03-04T20:18:16.212531Z`
- Status: `FAILED`

## Result summary

- selected_bundle_found: `false`
- copy_artifact_id: `null`
- failure summary:
  - `Copy prompt-chain pipeline could not produce a headline + page bundle that passed QA and congruency gates.`
  - last error: `PRESELL_ADVERTORIAL_WORD_FLOOR`, `PRESELL_ADVERTORIAL_SECTION_COUNT`, `PRESELL_MECHANISM_DEPTH`

## Copy loop metrics

```json
{
  "started_at": "2026-03-04T20:12:42.934149+00:00",
  "finished_at": "2026-03-04T20:18:16.025802+00:00",
  "headline_candidate_count": 15,
  "headline_ranked_count": 14,
  "headline_evaluated_count": 1,
  "headline_evaluation_offset": 0,
  "headline_evaluation_limit": 1,
  "qa_attempt_count": 1,
  "qa_pass_count": 1,
  "qa_fail_count": 1,
  "qa_total_iterations": 4,
  "qa_average_iterations": 4,
  "failure_breakdown": {
    "depth_structure_fail": 1
  }
}
```

## Prompt call summary

```json
{
  "total_calls": 7,
  "calls_by_label": {
    "headline_prompt": 1,
    "promise_contract_prompt": 1,
    "advertorial_prompt": 5
  },
  "calls_by_model": {
    "claude-sonnet-4-6": 7
  },
  "token_totals": {
    "input_tokens": 85691,
    "output_tokens": 12315,
    "total_tokens": 98006,
    "reasoning_tokens": 0,
    "cached_input_tokens": 0
  },
  "request_ids": [
    "req_011CYiegcjD181VD6ULHoHRj",
    "req_011CYiehoiXn4GTUwjrGWKgq",
    "req_011CYiei9SBxEbrzc3ZioDcj",
    "req_011CYiemrRMpE3dPoDc7VjFb",
    "req_011CYietiS65WpJqAsHEvKsj",
    "req_011CYieyKxsQDJgY9oQHJCq5",
    "req_011CYif3nFXvv41CxjtDrHov"
  ]
}
```

## QA rejection trace (attempt 1)

- source_headline: `New Warning: Wellness Guide mistakes that put parents at risk and why parents miss them`
- winning_headline: `New Study Reveals Why Most Herbal Guides Put Your Kids at Risk`
- qa_status: `PASS` (headline QA)
- page_generation_attempts: `5`
- final rejection class: `depth_structure_fail`
- final reason codes:
  - `PRESELL_ADVERTORIAL_WORD_FLOOR`
  - `PRESELL_ADVERTORIAL_SECTION_COUNT`
  - `PRESELL_MECHANISM_DEPTH`

Page attempt failures:
1. `PRESELL_ADVERTORIAL_WORD_FLOOR` + `PRESELL_ADVERTORIAL_SECTION_COUNT` + `PRESELL_MECHANISM_DEPTH`
2. `PRESELL_ADVERTORIAL_WORD_CEILING`
3. `PRESELL_ADVERTORIAL_WORD_FLOOR` + `PRESELL_ADVERTORIAL_SECTION_COUNT` + `PRESELL_MECHANISM_DEPTH`
4. `PRESELL_ADVERTORIAL_WORD_FLOOR` + `PRESELL_ADVERTORIAL_SECTION_COUNT` + `PRESELL_MECHANISM_DEPTH`
5. `PRESELL_ADVERTORIAL_WORD_FLOOR` + `PRESELL_ADVERTORIAL_SECTION_COUNT` + `PRESELL_MECHANISM_DEPTH`

## Notes

- This run no longer failed with Anthropic `compiled grammar is too large`.
- No sales-page call was made in this run because advertorial gate failures prevented progression.
