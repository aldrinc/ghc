# EMBER Hermes Caching, Telemetry, and Retry Map

## Decision

- Provider-side prompt caching is now enabled for the direct Anthropic Hermes path without changing the configured model.
- Exact per-turn usage telemetry is now surfaced from Hermes into MOS.
- The strongest unchanged-input rerun problem is not in the strategy stages. It is concentrated in one page-copy revision cluster on a single thread.

## What Changed

### Direct Anthropic prompt caching

- Updated `/Users/aldrinclement/.hermes/hermes-agent/run_agent.py` so Claude prompt caching is enabled for direct Anthropic, not only OpenRouter.
- Added direct Anthropic usage extraction for:
  - `prompt_tokens`
  - `completion_tokens`
  - `total_tokens`
  - `cache_read_input_tokens`
  - `cache_creation_input_tokens`
- Removed the extra top-level Anthropic `cache_control` flag from the native shim. Anthropic expects the cache breakpoints on the blocks themselves; keeping the top-level flag caused invalid five-breakpoint payloads when Hermes used its normal system-and-3 strategy.
- Hermes now persists exact usage into:
  - the session JSON log
  - the Hermes `state.db` session row

### MOS telemetry plumbing

- Updated `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/hermes_sidecar.py` so a successful `run_turn()` must load exact usage from the Hermes session log and return it with the response.
- Updated `/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/agent_threads.py` so usage is stored in:
  - run outputs
  - assistant turn metadata
  - page-copy draft artifact payloads
  - page-copy batch reports

### Tests

- Updated `/Users/aldrinclement/Documents/programming/marketi/mos/backend/tests/test_hermes_sidecar.py`
- Updated `/Users/aldrinclement/Documents/programming/marketi/mos/backend/tests/test_agent_threads.py`

## Validation

### Repo validation

- `pytest /Users/aldrinclement/Documents/programming/marketi/mos/backend/tests/test_hermes_sidecar.py /Users/aldrinclement/Documents/programming/marketi/mos/backend/tests/test_agent_threads.py`
- `python -m compileall /Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/hermes_sidecar.py /Users/aldrinclement/Documents/programming/marketi/mos/backend/app/services/agent_threads.py`

### Prompt caching validation

Direct Anthropic raw API validation with a real EMBER-sized prompt prefix:

| Check | Result |
| --- | --- |
| First call | `cache_creation_input_tokens = 4852` |
| Second call | `cache_read_input_tokens = 4852` |

MOS sidecar service validation after the shim fix:

| Turn | Prompt Tokens | Completion Tokens | Cache Read Tokens | Cache Write Tokens |
| --- | ---: | ---: | ---: | ---: |
| First `run_turn()` | 7903 | 5 | 0 | 7900 |
| Resumed `run_turn()` | 6503 | 5 | 6172 | 328 |

Interpretation:

- The first turn writes almost the entire stable prompt prefix into Anthropic's cache.
- The resumed turn reads back most of that prefix from cache and only pays for the delta.

## Retry Map

## Scope note

- Strategy-stage reruns can be classified exactly because the runtime export hash changes when the mounted bundle changes.
- Page-copy reruns can only be classified from the stored run inputs, thread id, and slot counts. MOS does **not** currently persist a page-base snapshot hash at run start, so historical page-copy reruns are "best effort" rather than mathematically exact.

## Strategy stages

### Exact result

- No confirmed same-input reruns were found in the persisted strategy-stage outputs.

### Evidence

| Stage | Observed attempts | Exact same-input reruns? | Evidence |
| --- | ---: | --- | --- |
| `signal_report` | 3 runtime exports before final success | No | Export hashes changed across attempts: `3bd2df87...`, `791d8b49...`, `6c5ca073...` |
| `angle_library` | 1 | No | One persisted output only |
| `knowledge_base` | 2 visible runtime threads, 1 persisted output | Not provable as same-input | Final persisted export hash `bbeb90c8...`; earlier failed thread predates the stable export-id trace |
| `cso` | 1 | No | One persisted output only |
| `offer_document` | 1 | No | One persisted output only |
| `headline_pool` | 1 | No | One persisted output only |
| `presell_page` | 1 | No | One persisted output only |
| `sales_page` | 1 | No | One persisted output only |

### Conclusion

- The strategy pipeline did not repeatedly hammer the exact same approved working bundle.
- The visible stage churn came from changed runtime exports during buildout, not from re-running the exact same strategy state over and over.

## Page-copy runs

### Best-effort request signatures

The page-copy runs clustered into four signatures using the stored run inputs:

| Signature | Prompt family | Slots | Attempts | Notes |
| --- | --- | ---: | ---: | --- |
| `2a41cb34a0a3` | Initial rewrite | 159 | 3 | 1 provider-credit failure, then 2 completions on different threads |
| `4ed72fe93893` | First revision | 159 | 2 | 1 completion, 1 later run still marked `running` |
| `c409e113325c` | Initial rewrite after slot normalization | 140 | 2 | 1 completion, 1 provider-credit failure on a different thread |
| `847ed3a9bd0f` | Revision after slot normalization | 140 | 6 | Strongest unchanged-input rerun cluster |

### Strongest unchanged-input cluster

Signature `847ed3a9bd0f` is the clearest same-input repeat set:

| Run ID | Started (UTC) | Status | Thread | Root cause |
| --- | --- | --- | --- | --- |
| `405fe3f0-5b19-48b4-9b34-a1054e5342b1` | 2026-04-01T22:59:29Z | failed | `d0c8b460-637a-47e1-8975-f022491c9b2a` | Anthropic low-credit failure on resumed session |
| `a371596f-13a9-42d8-9acd-6ceb906badd3` | 2026-04-01T23:17:03Z | failed | same thread | JSON contract failure during slot repair |
| `2139dc7c-1cc1-42a1-8cca-74bb9e5a51ed` | 2026-04-01T23:21:04Z | failed | same thread | JSON contract failure during slot repair |
| `00eb6312-91c3-4ead-820f-d34aa6bb6642` | 2026-04-01T23:22:46Z | failed | same thread | Anthropic low-credit failure |
| `b39c8928-0346-4d99-b48c-55c7a1d75a77` | 2026-04-01T23:41:12Z | failed | same thread | Anthropic low-credit failure |
| `1d4cb7ba-70b6-40b1-9cd7-2a1ad04b406b` | 2026-04-01T23:43:38Z | completed | same thread | Final successful revision |

Why this counts as a likely same-input rerun cluster:

- Same prompt text
- Same slot count: `140`
- Same slot batch count: `23`
- Same output mode: `page_copy_slots`
- Same runtime model and settings
- Same thread id
- No successful revision was applied between the failures and the final success

### What this means

- There **was** repeated spend on unchanged or near-unchanged page-copy inputs.
- It was not spread evenly across the whole EMBER pipeline.
- It was concentrated in one recovery sequence caused by:
  - Anthropic account-credit interruptions
  - invalid JSON from the page-copy response contract

## Bottom line

- Your skepticism was directionally right for the strategy stages: I do **not** see evidence that the EMBER skills stages were repeatedly rerun against the exact same bundle state.
- The repeat-spend problem **was** real in page-copy, but it was localized to one revision loop, not the whole pipeline.
- The highest-signal savings change is now in place: provider-side prompt caching works on the direct Anthropic Hermes path and exact usage is captured per turn, so the next live page-copy run will show the real cache-read savings in MOS instead of forcing us to reconstruct them after the fact.
