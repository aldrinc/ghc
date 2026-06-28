# DSV4 vs GPT Foundational Steps 03/04 Comparison

## Result

Step 03: **PASS**. DSV4 produced a valid tailored Step 04 prompt.

Step 04: **FAIL**. DSV4 used the research harness heavily, then returned only: `I now have enough data to produce the comprehensive report. Let me write it now.`. Same-thread continuation also failed, producing empty output.

Do **not** default Step 04 to DSV4/DeerFlow yet.

## Scope

- Step 01 was already tested in `proof_pack/deerflow-step01-1to1-2026-05-21`.
- This run covered only Step 03 and Step 04.
- Step 06 was not run.

## Metrics

| Metric | GPT Step 03 | DSV4 Step 03 | GPT Step 04 | DSV4 Step 04 |
|---|---:|---:|---:|---:|
| Summary chars | 1200 | 1269 | 1800 | 0 |
| Content chars | 14474 | 312 | 290 | 81 |
| Elapsed seconds | 91.69 | 181.532 | 396.83 | 513.256 |
| Web searches | 0 | 0 | unknown | 69 |
| Web fetches | 0 | 0 | unknown | 17 |
| Input tokens | unknown | 13676 | unknown | 1749776 |
| Output tokens | unknown | 5578 | unknown | 9350 |

## Cost

- Step 03 promo cost: $0.0092
- Failed Step 04 promo cost: $0.1158
- Failed Step 04 continuation promo cost: $0.0012
- Total promo cost for this test: $0.1262
- Post-promo list equivalent: $0.2977

## Comparison Read

Step 03 is safe to keep testing. It is slower than GPT but usable, and produced a much larger tailored Step 04 prompt.

Step 04 is not safe to default. The harness did real research, but the final-output transition failed. The failure mode is actionable: force a two-phase Step 04 harness where research evidence is persisted, then a separate no-tool synthesis pass writes the tagged report from captured evidence.

GPT production Step 04 also looks brittle in the persisted artifact: the stored content is only 290 chars while the bounded summary is 1800 chars. That means Step 04 needs output-contract repair regardless of provider.
