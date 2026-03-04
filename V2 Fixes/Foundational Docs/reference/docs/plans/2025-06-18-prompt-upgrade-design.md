# Prompt Upgrade Design Doc: 0.1% Agentic DR Operation

**Date:** 2025-06-18
**Status:** Approved
**Scope:** Upgrade 5 existing prompts (03, 06, 07, 08, 09) into 4 bulletproof agentic prompts

---

## Executive Summary

Upgrade the foundational prompt chain from fill-in-the-blank templates to analytically rigorous, mental-model-driven agent prompts that produce structured, confidence-weighted, downstream-ready output. The prompts target model-agnostic execution (Claude, GPT-4o, Gemini Deep Research) within a custom agent framework.

---

## Approach: Structural Upgrade + Selective Mental Model Embedding

Each prompt gets structurally redesigned AND gets the 3-5 most impactful mental models embedded as explicit reasoning steps, chosen per prompt based on where that prompt's outputs are weakest.

### Cross-Cutting Design Principles

1. **Tool-calling for all scoring/ranking:** LLMs have poor self-calibration on numerical scales. All quantitative evaluation steps instruct the agent to use code interpreter / calculator tools. Never estimate composite scores mentally.

2. **Evidence-grounded claims:** Every assertion in every output must cite its VOC/data source. Speculation flagged as "HYPOTHESIS."

3. **Structured output alongside narrative:** All outputs use both human-readable narrative AND structured data (JSON-compatible tags, matrices, comparison tables) for downstream agent consumption.

4. **Output format compatibility:** All prompts preserve `<SUMMARY>` and `<CONTENT>` tag structure for framework compatibility.

---

## Mental Models Applied Per Prompt

| Mental Model | 03 Research | 06 Avatar | 07 Offer | 08 Beliefs |
|---|---|---|---|---|
| First Principles | X | X | X | X |
| Bayesian Reasoning | X | | | X |
| Signal-to-Noise Ratio | X | | | |
| Systems Thinking (Bottleneck) | X | X | | X |
| Information Theory | X | | | X |
| Behavioral Economics | | X | X | X |
| Engineering Safety Factors | | X | X | X |
| Z-Score Normalization | | X | | X |
| Product Lifecycle Theory | | | X | |
| Momentum (Physics) | | | X | |
| Inversion / Pre-Mortem | | | X | |

---

## Prompt 1: Deep Research (03) — Upgrade Design

**File:** `03_deep_research_prompt_v2.md`

### Changes from Current
1. **Collapse meta-hop** — Single parameterized prompt replaces prompt-engineer-writes-a-prompt architecture
2. **Expand to 9 research categories** (add Purchase Triggers, Decision Friction, upgrade Identity)
3. **Quote bank taxonomy** — Each quote tagged with: category, emotion, intensity, buyer_stage, segment_hint
4. **Signal-to-Noise filter** — Explicit S/N assessment after collection (5+ sources = HIGH, 2-4 = MODERATE, 1 = LOW)
5. **Bayesian confidence scoring** — Each finding rated LOW/MODERATE/HIGH with evidence justification
6. **Bottleneck identification** — Final synthesis identifies the #1 market constraint

### Mental Models Embedded
- Signal-to-Noise Ratio (evidence weighting)
- Bayesian Reasoning (confidence scoring)
- First Principles (decompose to fundamental needs)
- Information Theory (maximize information density per quote)
- Systems Thinking (bottleneck identification)

---

## Prompt 2: Avatar Brief (06) — Upgrade Design

**File:** `06_avatar_brief_v2.md`

### Changes from Current
1. **Replace template with analytical synthesis mandate** — Not "fill in blanks" but "analyze data, identify patterns, weigh evidence"
2. **Multi-segment architecture** — 3-5 distinct buyer segments, each with differentiation test
3. **Psychological architecture per segment** — Self-Determination Theory (autonomy/competence/relatedness), loss aversion profile, anchoring susceptibility
4. **Decision-making profile** — Information processing style, authority orientation, risk tolerance, comparison behavior
5. **Angle affinity mapping** — Which angle types resonate with which segments
6. **Z-Score normalized comparison matrix** — Dimensions normalized across segments for instant downstream comparison
7. **Engineering safety factor check** — Weakest evidence, assumptions, 10x-data test
8. **Bottleneck segment identification** — Which segment is highest-leverage opportunity
9. **Quotes restructured by function** — Hook-worthy, mechanism validation, objection-revealing, transformation-revealing

### Mental Models Embedded
- First Principles (irreducible psychological needs)
- Behavioral Economics (loss aversion, anchoring, framing)
- Systems Thinking (bottleneck segment)
- Z-Score Normalization (segment comparison)
- Engineering Safety Factors (self-audit)

---

## Prompt 3: Offer Brief (07) — Upgrade Design

**File:** `07_offer_brief_v2.md`

### Changes from Current
1. **Replace template with strategic positioning engine** — Generate 3 UMP/UMS candidates, evaluate, select winner with justification
2. **6-dimension candidate evaluation** — VOC evidence, saturation, emotional resonance, mechanism credibility, compliance, scalability. Scored via tool calling.
3. **Structured belief chain architecture** — Gate → Bridge → Purchase → Post-Purchase beliefs
4. **Tiered objection architecture** — Tier 1 deal-killers, Tier 2 friction, Tier 3 minor. Each with rebuttal + VOC evidence + funnel placement
5. **Value quantification framework** — Cost of inaction, comparable alternatives, ROI narrative
6. **Pre-mortem / Inversion** — Assume failure, identify 3 most likely causes, mitigation strategies
7. **Product lifecycle positioning** — Stage assessment with evidence, determines copy sophistication
8. **Funnel as momentum chain** — Entry state → action → exit state → momentum mechanism → friction points per step

### Mental Models Embedded
- First Principles (mechanism credibility)
- Inversion / Pre-Mortem (stress test positioning)
- Engineering Safety Factors (compliance, risk mitigation)
- Product Lifecycle Theory (category maturity assessment)
- Momentum (funnel physics)
- Behavioral Economics (value anchoring, loss aversion)

---

## Prompt 4: Belief Architecture (merged 08+09) — Upgrade Design

**File:** `08_belief_architecture_v2.md`

### Changes from Current
1. **Merge 08 + 09** into single prompt with two output layers (analytical + production)
2. **Belief discovery from first principles** — Work backwards from purchase moment through World → Problem → Approach → Product → Purchase beliefs
3. **Belief dependency mapping** — Graph of which beliefs must precede which
4. **Conversion Impact Scoring via tool calling** — 4 dimensions (current state, leverage, shiftability, proof availability), weighted formula, Z-score normalized. ALL computation via code tool.
5. **Belief × Segment matrix** — Priority per segment, flag universal beliefs
6. **Proof architecture per belief** — Information-theoretic proof type selection (which proof carries most information per attention cost?)
7. **Copy-ready output layer** — "I believe that..." statements targeting top-ranked beliefs + tiered objection rebuttals
8. **Safety factor check** — Unresolved Tier 1 objections, proof gaps, dependency chain gaps

### Mental Models Embedded
- Bayesian Reasoning (updating belief state estimates with evidence)
- Z-Score Normalization (standardized priority scoring)
- Behavioral Economics (framing, loss aversion in proof selection)
- Systems Thinking (belief dependency bottlenecks)
- Information Theory (proof information density)
- Engineering Safety Factors (gap analysis)

---

## File Mapping

| Original File | Upgraded File | Notes |
|---|---|---|
| `03_deep_research_prompt.md` | `03_deep_research_prompt_v2.md` | Collapsed meta-hop, 9 categories |
| `06_avatar_brief.md` | `06_avatar_brief_v2.md` | Complete redesign, multi-segment |
| `07_offer_brief.md` | `07_offer_brief_v2.md` | Strategic engine, candidate eval |
| `08_necessary_beliefs_prompt1.md` | `08_belief_architecture_v2.md` | Merged with 09 |
| `09_i_believe_statements.md` | (merged into 08) | Absorbed as Layer 2 |

---

## Build Order

1. `03_deep_research_prompt_v2.md` — Foundation; all downstream prompts depend on its output quality
2. `06_avatar_brief_v2.md` — Segments feed offer brief, beliefs, and copy
3. `07_offer_brief_v2.md` — Positioning feeds belief architecture
4. `08_belief_architecture_v2.md` — Beliefs bridge positioning to copy production
