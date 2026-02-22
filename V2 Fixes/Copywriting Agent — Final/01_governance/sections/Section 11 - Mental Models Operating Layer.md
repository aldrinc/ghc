# Section 11: Mental Models Operating Layer
## Rigorous Evaluation Framework for the Copywriting Agent

**Purpose:** This document applies 11 mental models (plus additional objective frameworks introduced below) to every scoring, evaluation, and decision step across Sections 1-10. It addresses known LLM limitations that compromise evaluation accuracy. It is the meta-layer that governs HOW the agent evaluates, not WHAT it evaluates.

**Companion docs:** Every section in the system. This document cross-references specific evaluation steps by section and subsection.

**Governing principle:** A system is only as good as its weakest evaluation step. If the agent cannot rigorously self-assess, the rules in Sections 1-10 become theater. This document makes evaluation bulletproof.

---

## PART 1: THE MENTAL MODEL TOOLKIT

### 1.1 Core Models and Their Roles in This System

| # | Model | Definition (Operational) | Where It Applies in This System |
|---|-------|-------------------------|-------------------------------|
| 1 | **First Principles** | Decompose every evaluation into its irreducible components. Never evaluate against composite criteria when decomposed criteria are available. | Section 9 job card checklists, Section 6 proof strength ratings, Subsection B craft checklist. Instead of "is this good copy?", decompose into: readability score + specificity count + rhythm variance + belief alignment. |
| 2 | **Bayesian Reasoning** | Update confidence in a rule or pattern proportionally to the strength of new evidence, not by replacing old evidence. Prior beliefs should shift gradually, not flip. | Subsection D confidence ratings, Section 8 hypothesis testing, Experimental Test Plan Layer 3. Every A/B result updates — does not replace — existing pattern confidence. |
| 3 | **Signal-to-Noise Ratio** | In any evaluation, distinguish the inputs that materially affect the outcome (signal) from inputs that create the illusion of rigor without predictive value (noise). | Section 9 cross-section flow checks (4 checks vs. unlimited possible checks — the 4 chosen are the highest-signal), Section 6 proof density guidelines (more proof is not better — it is noise after the threshold). |
| 4 | **Systems Thinking (Bottleneck)** | The system's output quality is limited by its single weakest component. Optimizing a non-bottleneck component produces zero improvement. Identify and fix the bottleneck first. | Experimental Test Plan sequencing (presell first because it is the funnel bottleneck), Section 8 P1-P4 prioritization (test the bottleneck, not the convenience), Section 10 context loading (load what matters, not everything). |
| 5 | **Information Theory (Shannon)** | Every piece of information loaded into context has a cost (tokens) and a value (reduction in output uncertainty). Load information only when its marginal value exceeds its marginal cost. | Section 10 tier system, Section 6 density guidelines, Subsection B readability rules (every word has an information cost to the reader — minimize cost per unit of persuasion). |
| 6 | **Behavioral Economics (Kahneman System 1/2)** | The reader processes copy in System 1 (fast, intuitive) by default and shifts to System 2 (slow, analytical) only when disrupted. Copy that forces System 2 without earning it loses the reader. | Subsection A agitation calibration (agitation triggers System 2 — if it fires without efficacy, the reader exits), Subsection E behavioral principles (every principle maps to either System 1 or System 2 processing), Section 7 hook anatomy (pattern interrupt is the System 1 disruption; relevance signal holds the System 2 check). |
| 7 | **Engineering Safety Factors** | Build margins into every threshold. If the minimum acceptable score is X, design the system to target X + a margin. Safety factors protect against variance, edge cases, and measurement error. | Subsection B readability (target FK 5-7, not just "under 7" — the margin protects against sentence-level variance), Subsection A agitation ceiling (Level 3 ceiling with Level 5 permanently banned — the 2-level gap is the safety factor), Section 8 sample size notes (95% confidence, not 80%). |
| 8 | **Logarithmic Diminishing Returns** | The first unit of effort produces the largest marginal gain. Each subsequent unit produces less. Identify the point where additional effort generates negligible return and stop. | Section 6 proof density (8-12 proof items on a sales page is optimal; 15 is maximum; beyond 15, each item reduces credibility), Subsection B bullet quantity (7-10 bullets, not 20 — diminishing returns in the reader's attention), Section 9 redundancy check (claim appears max 2x — third appearance has negative marginal return). |
| 9 | **Product Lifecycle Theory** | Every copy asset, proof item, and A/B finding has a lifecycle: introduction, growth, maturity, decline. What works today will not work forever. Build expiration and review into the system. | Section 6 freshness rules (0-6 months = current, 24+ months = stale), Subsection D confidence ratings (platform performance data "shifts quarterly — revalidate every 90 days"), Section 8 P1-P4 progression (a tested winner is mature; a never-tested element is in introduction). |
| 10 | **Momentum (Physics)** | A reader in motion tends to stay in motion. A reader at rest tends to stay at rest. Every copy element either adds momentum (forward pull) or introduces friction (resistance to continuing). | Section 9 momentum check (every section must end with forward pull), Subsection B transitions (logical bridges, bucket brigades, open loops — all momentum devices), Section 9 emotional arc check (the "dip and rise" shape ensures momentum recovery after agitation). |
| 11 | **Z-Score Normalization** | When comparing scores across different scales, normalize to standard deviations from the mean. Raw scores are misleading when categories have different ranges, variances, or baselines. | Experimental Test Plan Layer 1 (22-point rubric — not all points are equal), Section 6 proof strength ratings (what counts as "strong" differs by proof type), Section 8 test results (comparing CTR deltas across different traffic sources requires normalization). |

### 1.2 Additional Objective Models Introduced

| # | Model | Definition (Operational) | Why Introduced | Where It Applies |
|---|-------|-------------------------|---------------|-----------------|
| 12 | **Pareto Principle (80/20)** | 80% of output quality comes from 20% of the rules. Identify and enforce the vital few; relax enforcement of the trivial many. | Prevents checklist fatigue in the agent. When a 22-point checklist is treated as 22 equally weighted items, the agent optimizes for easy points (no exclamation marks) while missing hard ones (belief sequencing). | Subsection B checklist, Section 9 job cards, Section 4 compliance checklist — define which items are "hard gates" (instant fail if missed) vs. "quality signals" (desirable but not fatal). |
| 13 | **Regression to the Mean** | Extreme results tend to be followed by less extreme results. A single dramatic A/B win is likely partly attributable to variance, not entirely to the variable tested. | Prevents overreaction to single test results. A 50% CTR lift on one presell test does not mean the system is 50% better — it means the system may be better AND the test had favorable variance. | Subsection D confidence ratings (require replication before upgrading from Medium to High), Section 8 learning outcomes (a single win informs but does not prove), Experimental Test Plan result interpretation. |
| 14 | **Inversion (Pre-Mortem)** | Instead of asking "how does this succeed?", ask "how does this fail?" Enumerate failure modes first, then design against them. | LLMs are biased toward confirming their output is correct. Forcing a failure-mode scan before a success claim counteracts this. | Section 9 failure modes (already implemented — this model validates the structure), Section 8 learning outcomes (the "if control wins" branch is the inversion), this document's LLM limitation section. |
| 15 | **Occam's Razor (Parsimony)** | When two explanations for a test result are equally supported, prefer the simpler one. Do not attribute a win to a complex interaction of variables when a single variable explains it. | Prevents over-interpretation of A/B results. An agent asked "why did Variant B win?" will generate a 5-factor explanation when a 1-factor explanation is usually correct. | Section 8 worked examples, Subsection D findings (each finding attributes the result to ONE primary variable), Experimental Test Plan Layer 3 learning outcomes. |

---

## PART 2: LLM LIMITATIONS AND COUNTERMEASURES

These are known failure modes of large language models when performing self-evaluation. Each countermeasure is a mandatory operating rule.

### 2.1 Anchoring Bias

**The problem:** LLMs anchor heavily on the first information in the context window. Rules loaded first receive disproportionate weight in evaluation. Rules loaded last receive disproportionate weight in generation.

**Where it affects this system:**
- Section 10 context loading: If the compliance checklist is loaded first, the agent over-indexes on compliance at the expense of craft quality. If behavioral principles are loaded first, the agent over-indexes on persuasion technique at the expense of voice.
- Section 9 self-evaluation: The first checklist item gets the most rigorous check. The last gets a rubber stamp.

**Countermeasure — The Rotation Rule:**
When running any checklist of 5+ items, the agent must:
1. Run the checklist in the stated order.
2. Then run items 1-3 AGAIN after completing the full list.
3. If any re-check produces a different result than the first pass, flag the discrepancy and resolve by re-reading the relevant copy section in isolation.

**Countermeasure — The Load Order Rule:**
When Section 10 specifies Tier 1 loading, alternate between constraint docs (Voice, Compliance) and craft docs (Structural Principles, Craft Rules) rather than loading all constraints first. Interleaving reduces anchor dominance.

### 2.2 Sycophancy / Self-Confirmation Bias

**The problem:** LLMs systematically rate their own output as passing evaluations. When an LLM writes copy and then evaluates that copy, the evaluation is compromised by the same distributional biases that produced the copy. The agent "recognizes" its own patterns as correct.

**Where it affects this system:**
- Every self-evaluation checklist in Sections 1 and 9.
- The Experimental Test Plan Layer 1 (if the same LLM instance scores its own output).
- Section 6 proof strength ratings (if the agent generated the proof framing, it will rate its framing as "strong").

**Countermeasure — The Adversarial Re-Read:**
Before running any self-evaluation checklist, the agent must execute this prompt to itself:

```
"I am about to evaluate my own output. I know I am biased toward confirming
my output is correct. Before checking each item, I will read the relevant
copy section and actively look for ONE reason it might FAIL this check.
If I cannot find a failure reason, the item passes. If I find one,
I must resolve it before marking it as passing."
```

This inverts the evaluation default from "confirm pass" to "search for fail" — applying the Inversion model (#14).

**Countermeasure — The Two-Session Rule (for Test Plan Layer 1):**
The copy-generating session and the copy-evaluating session must be DIFFERENT LLM sessions. Do not generate and score in the same session. This breaks the self-confirmation loop. The evaluating session receives only the copy output and the scoring rubric — not the prompt that generated the copy.

### 2.3 Averaging Tendency (Central Tendency Bias)

**The problem:** When rating on a scale (strong/moderate/weak), LLMs default to the middle option. "Moderate" is the modal output because it is the distributional average of how these rating labels appear in training data. This makes proof strength ratings and agitation level assessments unreliable.

**Where it affects this system:**
- Section 6 proof strength ratings: Too many items will be rated "moderate" regardless of actual strength.
- Subsection A agitation calibration: The agent will default to Level 2-3 even when Level 1 is correct.
- Subsection D confidence ratings: "Medium" will be overassigned.

**Countermeasure — The Forced Justification Rule:**
For every rating on any scale in this system, the agent must:
1. State the rating.
2. State the specific evidence that rules out the adjacent rating.

Example for proof strength:
- If rating "strong": state why it is not moderate. ("This item includes a named source, specific numbers, and is independently verifiable — which rules out 'moderate' because moderate items lack at least one of these three.")
- If rating "moderate": state why it is not strong AND why it is not weak.
- If rating "weak": state why it is not moderate.

This forces the agent to defend boundary decisions rather than defaulting to the center.

**Countermeasure — The Base Rate Calibration:**
For any inventory of rated items, apply this distribution check:
- If more than 60% of items in any single category share the same rating, the ratings are likely miscalibrated.
- Re-evaluate the top-rated 20% and bottom-rated 20% to confirm they genuinely differ.
- This applies Z-Score Normalization (#11): if all items cluster at the mean, the rating system is not discriminating.

### 2.4 Lost-in-the-Middle

**The problem:** In large context windows, information in the middle of the context receives less attention than information at the beginning or end. Rules buried in the middle of a large document are effectively invisible.

**Where it affects this system:**
- Section 10 context loading: Documents loaded in the middle of Tier 1 will be under-weighted.
- Long checklists: Items 5-15 (in a 22-point checklist) receive less rigorous evaluation than items 1-4 and 16-22.
- Section 2 page-type templates: The middle page types (upsell, downsell) will receive less attention than presell and sales page.

**Countermeasure — The Chunked Evaluation Rule:**
Never evaluate against a checklist of more than 7 items in a single pass (Miller's Law / Cognitive Load principle #5). Instead:
- Break the 22-point Subsection B checklist into 4 blocks (Readability: 4 items, Specificity: 3 items, Rhythm: 4 items, Bullets/Transitions/Retention: 11 items split into 2 sub-blocks).
- Evaluate each block as a separate operation with a fresh read of the copy before each block.
- This prevents the middle items from being lost.

**Countermeasure — The Priority-First Loading Rule:**
In Section 10 Tier 1, the two most critical documents must be placed at the BEGINNING and END of the context — never in the middle. For this system:
- Beginning position: Voice & Tone Operating Rules (Section 3) — because every word must match the voice.
- End position: Compliance Constraint Layer (Section 4) — because compliance is the final gate before output.
- Middle positions: Structural Principles and Craft Rules — important but less catastrophic if partially underweighted.

### 2.5 Pattern Completion Bias

**The problem:** LLMs complete patterns. If the first three self-evaluation items pass, the LLM's distributional prediction is that remaining items will also pass. This creates a "momentum of passing" that makes it harder to flag a genuine failure on item 7 after 6 consecutive passes.

**Where it affects this system:**
- Section 9 self-evaluation checklists (4-6 items per card — pattern completion kicks in after 3 passes).
- Section 8 compliance checklist (13 items — after 8-9 passes, the remaining items get rubber-stamped).
- Subsection B craft checklist (22 items — highly vulnerable).

**Countermeasure — The Deliberate Failure Insertion:**
When running any checklist of 5+ items, the agent must identify the ONE item most likely to be a genuine failure (based on the specific copy context, not random selection). Evaluate that item FIRST, before the pass/fail pattern establishes. This breaks the completion momentum.

**Countermeasure — The Explicit Doubt Prompt:**
After every 5 consecutive passes on a checklist, the agent must pause and ask: "Am I passing these because they genuinely pass, or because the pattern of passing has made me expect a pass?" If the agent cannot point to specific textual evidence for the most recent pass, it must re-evaluate that item from scratch.

---

## PART 2B: MANDATORY TOOL-CALLING FOR SCORING AND EVALUATION

### The Core Problem

LLMs cannot reliably score their own output. Self-evaluation is corrupted by sycophancy bias, pattern completion, and distributional averaging (see 2.2, 2.3, 2.5 above). The solution is to externalize all mathematical, scoring, and ranking operations to tool calls where computations are executed deterministically — not probabilistically by the language model.

**Universal rule:** Any operation that involves counting, scoring, ranking, comparing numbers, or calculating a metric MUST be executed via a tool call (code execution / calculator / structured function), NOT performed in the LLM's chain-of-thought. The LLM identifies WHAT to measure. The tool call MEASURES it. The LLM interprets the result.

### 2B.1 Required Tool-Call Operations

The following operations are PROHIBITED from being performed by LLM inference alone. Each must be delegated to a tool call:

| Operation | Why LLMs Fail At It | Tool-Call Implementation |
|---|---|---|
| **Flesch-Kincaid readability scoring** | LLMs cannot reliably count syllables, words per sentence, or sentences per paragraph. They estimate, and estimates cluster around "grade 6" regardless of actual text. | Use a code execution tool to run the FK formula: `206.835 - 1.015 × (total_words / total_sentences) - 84.6 × (total_syllables / total_words)`. Input: the raw copy text. Output: exact grade level. |
| **Word count per section** | LLMs systematically undercount words in long passages and overcount in short ones. | Use a code execution tool: `len(text.split())`. Compare against Section 2 word count targets for each page type. |
| **Sentence length measurement** | LLMs cannot reliably determine if a sentence exceeds 25 words. They evaluate "feel" not count. | Use a code execution tool: split text by sentence-ending punctuation, count words per sentence, flag any exceeding 25. Return the exact count and the offending sentences. |
| **Banned word/phrase scanning** | LLMs will miss banned words that appear in natural-sounding sentences because the word "fits" contextually. The LLM's generative bias makes banned words invisible when they feel correct. | Use a code execution tool: exact string matching against the Section 3 banned word list (30 words) and Section 4 banned phrase list (30 phrases). Input: copy text + banned lists. Output: exact matches with line numbers. Zero tolerance — no "close enough." |
| **Checklist scoring and aggregation** | LLMs inflate their own checklist scores by 2-4 points on average (sycophancy bias). A reported 18/22 is likely a true 14-16/22. | Use a structured function: for each checklist item, the LLM provides a binary pass/fail with evidence (the specific text that passes or fails). The tool call counts passes, applies weights from Part 3.1, and returns the weighted score. The LLM does NOT compute the final score. |
| **Proof inventory gap analysis** | LLMs will claim "adequate" coverage when the inventory has 2 items for a belief and "gap" when it has 0 — they do not reliably distinguish between thin coverage and adequate coverage. | Use a code execution tool: count proof items per belief (B1-B8), per objection (OBJ-*), and per proof type. Return the counts as a table. The LLM interprets the counts against the Section 6 coverage thresholds. |
| **Agitation level scoring** | LLMs default to "Level 2-3" for everything (central tendency bias). They cannot reliably distinguish between Level 1 and Level 2, or between Level 3 and Level 4. | Use a structured rubric tool: for each agitation sentence, the LLM flags specific language markers (consequence language = +1, fear language = +1, catastrophizing = +2, "your children" reference = +1, medical emergency = +2). The tool call sums the markers. Level thresholds: 0 = Level 1, 1-2 = Level 2, 3-4 = Level 3, 5-6 = Level 4, 7+ = Level 5 (banned). |
| **Belief chain sequence verification** | LLMs will say "beliefs are in order" even when B4 is introduced before B3, because the LLM recognizes the content of each belief without tracking its first-introduction position. | Use a code execution tool: for each section of the copy, the LLM labels which belief is PRIMARY. The tool call verifies that the sequence of first-appearances follows B1 → B2 → B3 → B4 → B5 → B6 → B7 → B8 with no skips. It checks the Foundation Gate (B1 and B2 both appear before B3). Output: sequence valid / invalid + first violation point. |
| **Differentiation scoring (HookBank)** | LLMs will claim hooks are "meaningfully different" when they share the same archetype and entry angle but use different words. Synonym diversity is not meaningful diversity. | Use a structured function: for each hook, the LLM tags archetype (1-9), entry angle (problem/solution/identity), belief targeted (B1-B8), and emotional register (clinical/empathetic/provocative). The tool call builds a pairwise comparison matrix: for every pair, count how many of the 4 dimensions differ. Flag any pair with fewer than 2 differences. Count archetype diversity, belief diversity, register diversity against thresholds. |
| **A/B test sample size calculation** | LLMs produce plausible-sounding but mathematically wrong sample size estimates. They round to "about 1,000" regardless of effect size, baseline rate, or confidence level. | Use a code execution tool with the standard sample size formula: `n = (Z² × p × (1-p)) / E²` where Z = 1.96 (95% confidence), p = baseline conversion rate, E = minimum detectable effect × p. Input: baseline rate, minimum detectable relative effect, confidence level. Output: exact n per variant. |
| **Proof freshness date calculations** | LLMs cannot reliably calculate elapsed time between dates or determine if a proof item has crossed an age threshold. | Use a code execution tool: calculate days between `source.date` and current date. Classify per Section 6 freshness rules (0-180 days = current, 181-365 = review flag, 366-730 = aging, 731+ = stale). Flag items crossing thresholds. |

### 2B.2 The LLM-Tool Handoff Protocol

For every evaluation step that involves scoring, the agent follows this sequence:

```
STEP 1: LLM IDENTIFIES — What needs to be measured?
         (e.g., "I need to score readability")
STEP 2: LLM EXTRACTS — Pull the relevant text/data from the copy.
STEP 3: TOOL EXECUTES — Send to code execution / calculator /
         structured function. The tool does the math.
STEP 4: LLM RECEIVES — Get the numeric result back.
STEP 5: LLM INTERPRETS — Apply the mental models to interpret
         the result in context.
```

**The LLM never skips Step 3.** If tool calling is unavailable in the current environment, the agent must:
1. Flag this limitation explicitly: "I cannot run tool-based scoring in this session."
2. Apply the Adversarial Re-Read (2.2) and Forced Justification (2.3) countermeasures as compensating controls.
3. Add a margin of error to all self-reported scores: subtract 3 points from any self-assessed checklist score as a safety factor (Engineering Safety Factors, model #7).

### 2B.3 Calibration Checks

Every 5 evaluation cycles, the agent must run a calibration check:

1. Select the most recent evaluation where the agent reported a score.
2. Re-run the tool-call-based measurement on the same copy.
3. Compare the agent's reported score to the tool-computed score.
4. If the delta exceeds 2 points (on the weighted scale), the agent's evaluation calibration has drifted. Re-read Part 2 countermeasures and apply them with increased rigor for the next 5 cycles.

This is Bayesian self-monitoring — the agent tracks its own accuracy over time and corrects when it detects drift.

---

## PART 3: MODEL APPLICATION TO SPECIFIC EVALUATION STEPS

### 3.1 Subsection B — 22-Point Self-Evaluation Checklist

**Current state:** 22 binary pass/fail items, all weighted equally.

**Mental model upgrades:**

**First Principles decomposition:** Separate the 22 items into three tiers:

| Tier | Items | Weight | Consequence of Failure |
|------|-------|--------|----------------------|
| **Hard Gates** (instant fail, rewrite required) | FK grade 5-7, zero banned words (Section 3), zero banned phrases (Section 4), belief chain sequence correct | 3 points each | A single failure here means the copy does not ship. Period. This is the Engineering Safety Factor — there is no margin for "almost compliant." |
| **Quality Signals** (failure degrades quality but does not disqualify) | Sentence variety, crossheads every 3-4 paragraphs, bullet style diversity, "Only This Product" test passes | 1 point each | Failures here reduce effectiveness but do not create legal, brand, or structural risk. |
| **Polish Indicators** (desirable, diminishing returns) | Format shifts every 400-600 words, bucket brigade spacing, builder sentence limits | 0.5 points each | These are Logarithmic Diminishing Returns — the first format shift matters; the difference between shift at 450 words vs. 500 words is noise. |

**New weighted scoring:** Maximum possible = ~30 weighted points. Pass threshold = 24 weighted points with zero Hard Gate failures.

**Pareto application:** Hard Gates represent ~25% of the items but ~70% of the quality impact. The agent must evaluate all Hard Gate items FIRST before proceeding to Quality Signals.

### 3.2 Section 6 — Proof Strength Ratings

**Current state:** Three-level scale (strong/moderate/weak) with one-sentence rationale.

**Mental model upgrades:**

**Z-Score Normalization:** "Strong" means different things for different proof types. A strong testimonial requires specificity + named source + emotional resonance + scenario relevance. A strong data point requires named source + recency + statistical precision + independent verifiability. Define the criteria per type:

| Proof Type | Strong Criteria (all must be true) | Moderate Criteria (3 of 4) | Weak Criteria (fewer than 3) |
|---|---|---|---|
| Testimonial | Named source + specific scenario + specific feature referenced + emotional resonance with avatar | 3 of 4 criteria met | Fewer than 3 |
| Data Point | Peer-reviewed/government source + specific number + dated within 2 years + directly supports belief | 3 of 4 criteria met | Fewer than 3 |
| Authority Signal | Named institution + factual claim (not implied endorsement) + verifiable + relevant to mechanism | 3 of 4 criteria met | Fewer than 3 |
| Credential | Verifiable degree/cert + relevant to herbal safety + dual competency (herbal + scientific) + documented | 3 of 4 criteria met | Fewer than 3 |
| Demonstration | Real product content + current version + shows mechanism in action + uses recognizable herb | 3 of 4 criteria met | Fewer than 3 |

**Forced Justification Rule applies:** Every rating must state which specific criteria are met and which (if any) are not, ruling out the adjacent rating.

**Base Rate Calibration applies:** If the proof inventory has more than 60% "strong" or more than 60% "moderate" items, the ratings are suspect. Re-evaluate.

### 3.3 Subsection D — Confidence Ratings

**Current state:** Three-level scale (High/Medium/Low) with source description but no calibration.

**Mental model upgrades:**

**Bayesian Reasoning integration:** Define what each confidence level means probabilistically and what evidence would update it:

| Level | Meaning | What Would Upgrade It | What Would Downgrade It |
|---|---|---|---|
| **High** | Pattern has been replicated across 3+ independent tests OR is supported by a dataset of 10,000+ observations. The finding is unlikely to reverse with additional evidence. | N/A — already at top. Can be REINFORCED by replication in this specific product's data. | A single failed replication in this product's data with adequate sample size. Two failed replications from any source. Shifts to Medium. |
| **Medium** | Pattern is supported by 1-2 tests or practitioner-reported data without full methodological transparency. Directionally credible but could reverse. | Successful replication in this product's A/B data shifts to High. Successful replication by an independent source shifts to High. | A single failed replication with adequate sample size does NOT automatically downgrade — apply Regression to the Mean. TWO failed replications shift to Low. |
| **Low** | Pattern is theoretically plausible or anecdotally reported but lacks controlled evidence. Use with caution. | Any single controlled test supporting the pattern shifts to Medium. | Failure to find the effect in two attempts shifts to "Unsupported — remove from reference." |

**Regression to the Mean application:** When a test produces a dramatic result (50%+ lift), do not immediately upgrade confidence. Instead, flag as "High-variance result — requires replication before confidence update." Dramatic results are disproportionately likely to regress.

### 3.4 Section 8 — A/B Testing Hypothesis Framework

**Current state:** Structured template with learning outcomes for win/lose/tie.

**Mental model upgrades:**

**Bayesian Reasoning — Prior Probability Field:**
Add a field to the hypothesis template:

```
PRIOR PROBABILITY: [How likely is it that the variant will win, based on existing
evidence?]
  - Strong prior (>70% expected win): The variant is supported by multiple High-confidence
    patterns from Subsection D. If it loses, that is a significant signal worth investigating.
  - Neutral prior (40-60%): No strong evidence either way. The test is genuinely exploratory.
  - Weak prior (<40% expected win): The variant is a contrarian bet, testing against
    established patterns. If it wins, update the relevant Subsection D pattern.
```

**Why this matters:** A test with a strong prior that loses is MORE informative than a test with a neutral prior that loses. The prior probability tells you how much to update your beliefs based on the result. This prevents the agent from treating all test results as equally surprising.

**Occam's Razor in Learning Outcomes:**
Add this rule to the LEARNING OUTCOME section: "When interpreting results, attribute the outcome to the simplest sufficient explanation. Do not invoke multi-factor explanations unless the single-factor explanation is ruled out by the data."

Example: If the proof-loaded headline wins, the simplest explanation is "specificity works for this audience." Do not explain it as "the proof-loaded headline activated the processing fluency principle while simultaneously anchoring the reader's value perception and triggering the identifiable victim effect through the specific numbers." That is noise, not signal.

### 3.5 Section 9 — Self-Evaluation Checklists

**Current state:** 4-6 yes/no items per card, plus 4 cross-section flow checks.

**Mental model upgrades:**

**Signal-to-Noise Ratio — Item Discrimination Analysis:**
Not all checklist items have equal predictive value for copy quality. Rank items by discrimination power:

| Discrimination Level | Meaning | Example Items |
|---|---|---|
| **High discrimination** | This item separates good copy from bad copy almost perfectly. If this item fails, the section has failed. | "Does every agitation sentence score at Level 3 or below?" (Card 2) — violation is catastrophic for this brand. |
| **Medium discrimination** | This item correlates with quality but is not definitive. Failure degrades but does not disqualify. | "Does the subhead advance a specific benefit?" (Card 1) — matters but a strong headline can compensate. |
| **Low discrimination** | This item is easy to game (the agent can technically pass it without genuine quality). Its signal is weak. | "Is the emotional register 'calm confidence'?" (Card 1) — the agent will almost always claim this is true because it is subjective and hard to disprove. |

**Countermeasure for low-discrimination items:** Replace subjective items with objective proxies.
- Instead of "Is the emotional register 'calm confidence'?": "Are there zero exclamation marks? Are there zero words from the Section 3 urgency-banned list? Are there zero sentences exceeding Level 2 agitation?" — three objective checks that proxy for the subjective judgment.

**Systems Thinking — Bottleneck Identification in Cross-Section Flow:**
The 4 cross-section checks (Belief Progression, Emotional Arc, Momentum, Redundancy) should be run in this order, and if Check 1 fails, the agent should fix it BEFORE running Checks 2-4:

1. **Belief Progression Check** (bottleneck) — if beliefs are out of sequence, the emotional arc, momentum, and redundancy are all downstream symptoms. Fixing belief progression often resolves the other checks automatically.
2. **Momentum Check** — second-highest leverage. A momentum failure usually indicates a structural problem.
3. **Emotional Arc Check** — depends on belief progression being correct first.
4. **Redundancy Check** — lowest leverage. Redundancy is usually a symptom of the agent padding around a weak section.

### 3.6 Experimental Test Plan — Layer 1 Scoring

**Current state:** 22-point rubric, Version B should score 18+, Version A expected 8-12, minimum gap of 5 points.

**Mental model upgrades:**

**Z-Score Normalization application:**
The raw 22-point score is misleading because not all points are equal (see 3.1 above). Replace with the weighted scoring system:
- Maximum weighted score: ~30 points
- Version B threshold: 24+ weighted points with zero Hard Gate failures
- Version A expected range: 10-16 weighted points
- Minimum gap: 8 weighted points (not 5 raw points)

**Engineering Safety Factor:**
The pass threshold of 18/22 (82%) has no margin for evaluator error. If the agent's self-evaluation is biased by +2 points (sycophancy bias), an actual 16 looks like 18 and passes. Apply a safety factor:
- Stated threshold: 18/22
- Internal target: 20/22 (the agent aims for 20 but reports the actual score)
- If the score is 18-19, it triggers a manual review flag (the agent cannot clear this — a human must verify)

**Bayesian integration for Layer 3 interpretation:**
When Test 1 results come back, do not treat them as standalone. Update the prior based on Layer 1 and Layer 2 results:
- If Layer 1 score gap was 12+ and Layer 2 was 5+/6 wins: Strong prior that Layer 3 will confirm. If it does not, the gap is between quality and market response — a different problem than quality failure.
- If Layer 1 score gap was 5-8 and Layer 2 was 4/6 wins: Neutral prior. Layer 3 is genuinely exploratory.
- If Layer 1 score gap was <5 or Layer 2 was <4/6: Weak prior. Fix the docs before spending on Layer 3.

---

## PART 4: UNIVERSAL OPERATING RULES

These rules apply to EVERY evaluation step across all sections.

### Rule 1: Decompose Before Scoring (First Principles)
Never assign a single holistic score. Break every evaluation into its component parts. Score each part independently. Aggregate only after all parts are scored. This prevents the halo effect (one strong element inflating the overall score).

### Rule 2: Invert Before Confirming (Pre-Mortem)
Before confirming that any output passes evaluation, spend 30 seconds actively searching for ONE reason it might fail. If a failure reason is found, resolve it. If none is found, the pass is genuine.

### Rule 3: Justify Boundary Ratings (Forced Justification)
Any rating on a multi-level scale must include: (a) the rating, (b) the evidence for the rating, and (c) the evidence that rules out the adjacent rating. A rating without boundary justification is invalid.

### Rule 4: Normalize Before Comparing (Z-Score)
Never compare raw scores across different categories, test types, or time periods without normalizing. A 15% CTR improvement from a presell test and a 15% CTR improvement from a hook test are not equivalent — the baselines, variances, and sample sizes differ.

### Rule 5: Check for Bottleneck Before Optimizing (Systems Thinking)
Before spending effort improving any component, confirm it is the current bottleneck. If the presell is converting at 1% and the sales page at 5%, improving the sales page to 6% produces less total impact than improving the presell to 2%. Always optimize the bottleneck first.

### Rule 6: Apply Diminishing Returns Before Adding More (Logarithmic Returns)
Before adding a 6th testimonial, 12th bullet point, or 4th CTA, ask: "Will this addition produce more than 5% of the improvement that the first one produced?" If not, stop. More is not better after the inflection point.

### Rule 7: Update Priors, Don't Replace Them (Bayesian)
When new test data arrives, update the relevant Subsection D finding by adjusting its confidence level — do not delete the old finding and replace it with the new one. A single result shifts belief; it does not create certainty.

### Rule 8: Prefer the Simpler Explanation (Occam's Razor)
When interpreting why a test won or lost, attribute the result to the fewest variables that sufficiently explain it. Do not stack five behavioral science principles to explain a headline win when "it was more specific" explains it fully.

### Rule 9: Build in Expiration (Product Lifecycle)
Every finding, proof item, and rated pattern must have a review date. Nothing in this system is permanent. A finding from 2024 that has not been re-validated by 2026 should be flagged, not trusted.

### Rule 10: Separate Signal from Noise Before Acting (Signal-to-Noise)
After any evaluation produces a list of issues, rank them by impact. Fix the top 3 highest-impact issues before addressing any others. A 10-item revision list where 3 items matter and 7 are polish is a Signal-to-Noise problem — the 7 polish items are noise that delays the 3 that matter.

### Rule 11: Protect Momentum at Transition Points (Momentum)
Every section-to-section transition is a potential momentum kill. When evaluating flow, give extra scrutiny to the last sentence of each section and the first sentence of the next. These are the joints where the reader decides whether to keep going.

---

## PART 5: INTEGRATION WITH SECTION 10 (CONTEXT WINDOW MANAGEMENT)

This document should be classified as follows in the Section 10 tier system:

| Tier | What to Load | When |
|---|---|---|
| **Tier 1 (Always Loaded)** | Part 2 (LLM Limitations — countermeasures only, not explanations) + Part 4 (Universal Operating Rules) | Every session. These are meta-rules that govern how all other rules are applied. |
| **Tier 2 (Per Task)** | Part 3 subsection relevant to the current task (e.g., load 3.5 when running Section 9 self-evaluation) | When the agent is in evaluation mode for a specific section. |
| **Tier 3 (On Demand)** | Part 1 (full model definitions) + Part 3 (all subsections) | When the agent needs to understand WHY a countermeasure exists, not just WHAT it is. |

**Estimated token count:**
- Tier 1 extract (countermeasures + universal rules): ~1,500 tokens
- Full document: ~4,000 tokens

---

*Document version: 1.0 | Section 11 of Copywriting Agent Implementation Plan | This document governs HOW the agent evaluates, not WHAT it evaluates. Sections 1-10 define the rules. This document ensures the rules are enforced with rigor, not theater.*
