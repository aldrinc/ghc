# DSV4 Pro DeerFlow vs GPT Production Step 1

## Verdict

DSV4 Pro in DeerFlow passed process parity for Strategy V2 Step 1:

- Correct production prompt: `V2 Fixes/Foundational Docs/clean_prompts/01_competitor_research_v2.md`
- Correct tagged output guardrail: `<SUMMARY>` and `<CONTENT>`
- Tool-enabled research: `web_search`, `web_fetch`, and `calculator`
- No output-token cap
- Completed Phases 1-9
- Produced ranked D1-D5 traction scoring

It is stronger than the GPT production artifact on completeness, because the GPT run hit a tool-call limit before calculator scoring and explicitly refused to output a computed ranking.

It is weaker than GPT on provenance discipline. DSV4 produced a more complete report, but `provcheck` still found 86 warnings for factual-looking values without nearby source/provenance. `provcheck` status passed, but this is not clean enough to make it primary without a stricter citation/provenance wrapper.

## Run Metrics

| Metric | GPT production Step 1 | DSV4 Pro DeerFlow Step 1 |
|---|---:|---:|
| Prompt path | Strategy V2 Step 1 | Strategy V2 Step 1 |
| Model | `gpt-5.2-2025-12-11` | `deepseek-v4-pro` |
| Elapsed | 520.16s | 629.112s |
| Raw/content chars | 25,082 | 36,515 raw / 34,880 content |
| Output tokens | not exported in local artifact | 18,463 |
| Total tokens | not exported in local artifact | 692,433 |
| Web search calls | not exported as count | 40 |
| Web fetch calls | not exported as count | 4 |
| Calculator calls | blocked before completion | 2 |
| Citation URLs | present | 43 |
| Unique URLs observed | not counted | 347 |
| Phase coverage | Phases 1-9 present | Phases 1-9 present |
| Scored ranking | blocked | present |

## Stronger In DSV4

- Completes the required calculator-based D1-D5 scoring and rank table.
- Covers a wider competitor universe: 18 discovered competitors and 15 validated competitors.
- Gives more usable competitor detail: positioning, ICP, proof type, pricing, unique claim, funnel patterns, CTA patterns, offer mechanics.
- Produces more downstream-useful synthesis: top opportunity, red flags, maturity level, positioning gaps, and #1 strategic lane.
- Uses DeerFlow tool evidence instead of a final-only LLM answer.

## Weaker In DSV4

- More expensive in context/tool usage: 692,433 total tokens for one Step 1 run.
- More citation/provenance slippage: `provcheck` passed but emitted 86 warnings.
- More confident tone on some market-size, revenue, and traffic claims. These should be source-led and line-level cited before canonical promotion.
- Mixes direct supplement competitors and adjacent TRT/telehealth competitors in the top scoring table. Useful strategically, but it can distort supplement-only prioritization unless downstream docs explicitly separate direct vs adjacent.
- Source quality is mixed: competitor pages and financial disclosures are solid; market-research aggregator pages, social posts, and third-party revenue databases need labeling as estimates or directional evidence.

## Known 1:1 Delta

The raw production onboarding payload was not present in the local export. The DeerFlow prompt used a reconstructed onboarding payload from concrete exported evidence:

- Stage 0 artifact
- Strategy V2 activity log
- workflow run metadata
- Step 03 echo context

This is the only material context delta I found.

## Recommendation

Do not make DSV4 Pro primary yet.

Use it as the Step 1 sidecar for 2-3 more brands with a stricter wrapper:

- Force every numeric claim to carry a nearby source.
- Separate direct supplement competitors from adjacent telehealth competitors before scoring.
- Keep calculator scoring mandatory.
- Cap tool loops by evidence quality, not output length.
- Persist outside model file-write tools to avoid the empty `write_file` stall seen in Attempt 1.

Primary promotion threshold: same prompt parity, complete scoring, no blocked phases, and near-zero provenance warnings.
