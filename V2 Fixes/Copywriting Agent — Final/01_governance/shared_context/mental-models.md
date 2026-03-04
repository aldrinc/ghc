# Mental Models Operating Reference — The Honest Herbalist

**Purpose:** Self-evaluation framework and LLM limitation countermeasures for the copywriting agent. Loaded as shared context for every workflow. This governs HOW the agent evaluates, not WHAT it evaluates.

**Source:** Extracted from Section 11 — Mental Models Operating Layer.

---

## Part 1: Mental Model Toolkit (15 Models)

Use each model as a self-check during drafting and evaluation.

### Core Models (1-11)

| # | Model | Operational Definition | Self-Check Question |
|---|-------|------------------------|---------------------|
| 1 | **First Principles** | Decompose every evaluation into its irreducible components. Never evaluate against composite criteria when decomposed criteria are available. | "Am I scoring this as 'good copy' holistically, or have I broken it into readability + specificity + rhythm + belief alignment?" |
| 2 | **Bayesian Reasoning** | Update confidence in a rule or pattern proportionally to the strength of new evidence, not by replacing old evidence. Prior beliefs should shift gradually, not flip. | "Am I replacing what I knew before with this single new data point, or am I updating proportionally?" |
| 3 | **Signal-to-Noise Ratio** | Distinguish inputs that materially affect the outcome (signal) from inputs that create the illusion of rigor without predictive value (noise). | "Of the things I'm checking, which ones actually predict whether this copy will work? Am I spending time on noise?" |
| 4 | **Systems Thinking (Bottleneck)** | The system's output quality is limited by its single weakest component. Optimizing a non-bottleneck component produces zero improvement. | "Am I polishing a strong section while a weak section is dragging the whole piece down?" |
| 5 | **Information Theory (Shannon)** | Every piece of information has a cost (tokens/reader attention) and a value (reduction in uncertainty). Load/include information only when its marginal value exceeds its marginal cost. | "Is this sentence/section earning its place, or is it costing reader attention without reducing their uncertainty?" |
| 6 | **Behavioral Economics (System 1/2)** | The reader processes copy in System 1 (fast, intuitive) by default and shifts to System 2 (slow, analytical) only when disrupted. Copy that forces System 2 without earning it loses the reader. | "Am I forcing the reader to think hard here? Have I earned that cognitive load, or will they bounce?" |
| 7 | **Engineering Safety Factors** | Build margins into every threshold. If the minimum acceptable score is X, design to target X + a margin. Safety factors protect against variance and edge cases. | "Am I aiming for exactly the minimum, or have I built in a margin?" |
| 8 | **Logarithmic Diminishing Returns** | The first unit of effort produces the largest marginal gain. Each subsequent unit produces less. Identify the point where additional effort generates negligible return and stop. | "Will adding this 6th testimonial / 12th bullet / 4th CTA produce more than 5% of the improvement the first one produced? If not, stop." |
| 9 | **Product Lifecycle Theory** | Every copy asset, proof item, and A/B finding has a lifecycle: introduction, growth, maturity, decline. What works today will not work forever. | "Is this proof item / pattern still current, or has it aged past usefulness?" |
| 10 | **Momentum (Physics)** | A reader in motion tends to stay in motion. Every copy element either adds momentum (forward pull) or introduces friction (resistance to continuing). | "Does this section end with forward pull? Or does the reader have a natural stopping point here?" |
| 11 | **Z-Score Normalization** | When comparing scores across different scales, normalize to standard deviations from the mean. Raw scores are misleading when categories have different ranges or baselines. | "Am I comparing apples to apples, or do these two scores come from different scales?" |

### Additional Objective Models (12-15)

| # | Model | Operational Definition | Self-Check Question |
|---|-------|------------------------|---------------------|
| 12 | **Pareto Principle (80/20)** | 80% of output quality comes from 20% of the rules. Identify and enforce the vital few; relax enforcement of the trivial many. | "Am I optimizing easy checklist items while missing the hard, high-impact ones (like belief sequencing)?" |
| 13 | **Regression to the Mean** | Extreme results tend to be followed by less extreme results. A single dramatic win is likely partly attributable to variance. | "Am I overreacting to a single test result? Does this need replication before I change my approach?" |
| 14 | **Inversion (Pre-Mortem)** | Instead of asking "how does this succeed?", ask "how does this fail?" Enumerate failure modes first, then design against them. | "Before I confirm this passes, let me actively search for ONE reason it might fail." |
| 15 | **Occam's Razor (Parsimony)** | When two explanations are equally supported, prefer the simpler one. Do not attribute a win to a complex interaction when a single variable explains it. | "Am I stacking five explanations for why this worked, when one explanation covers it?" |

---

## Part 2: LLM Limitation Countermeasures

These are known failure modes of large language models during self-evaluation. Each countermeasure is a mandatory operating rule.

### 2.1 Anchoring Bias

**Problem:** LLMs anchor heavily on the first information in the context window. Rules loaded first receive disproportionate weight in evaluation.

**Countermeasure -- Rotation Rule:**
When running any checklist of 5+ items:
1. Run the checklist in the stated order.
2. Then run items 1-3 AGAIN after completing the full list.
3. If any re-check produces a different result than the first pass, flag the discrepancy and resolve by re-reading the relevant copy section in isolation.

**Countermeasure -- Load Order Rule:**
When loading context, alternate between constraint docs (Voice, Compliance) and craft docs (Structural Principles, Craft Rules) rather than loading all constraints first. Interleaving reduces anchor dominance.

### 2.2 Sycophancy / Self-Confirmation Bias

**Problem:** LLMs systematically rate their own output as passing evaluations. The agent "recognizes" its own patterns as correct.

**Countermeasure -- Adversarial Re-Read:**
Before running any self-evaluation checklist, execute this internal prompt:

> "I am about to evaluate my own output. I know I am biased toward confirming my output is correct. Before checking each item, I will read the relevant copy section and actively look for ONE reason it might FAIL this check. If I cannot find a failure reason, the item passes. If I find one, I must resolve it before marking it as passing."

**Countermeasure -- Two-Session Rule:**
The copy-generating session and the copy-evaluating session must be DIFFERENT sessions. Do not generate and score in the same session.

### 2.3 Averaging Tendency (Central Tendency Bias)

**Problem:** When rating on a scale, LLMs default to the middle option. "Moderate" is overassigned regardless of actual quality.

**Countermeasure -- Forced Justification Rule:**
For every rating on any scale:
1. State the rating.
2. State the specific evidence that rules out the adjacent rating.

Example: If rating "strong," state why it is not moderate. If rating "moderate," state why it is not strong AND why it is not weak.

**Countermeasure -- Base Rate Calibration:**
If more than 60% of items in any single category share the same rating, the ratings are likely miscalibrated. Re-evaluate the top-rated 20% and bottom-rated 20% to confirm they genuinely differ.

### 2.4 Lost-in-the-Middle

**Problem:** In large context windows, information in the middle receives less attention than information at the beginning or end.

**Countermeasure -- Chunked Evaluation Rule:**
Never evaluate against a checklist of more than 7 items in a single pass (Miller's Law). Break large checklists into blocks and evaluate each block as a separate operation with a fresh read of the copy before each block.

**Countermeasure -- Priority-First Loading Rule:**
The two most critical documents must be placed at the BEGINNING and END of the context -- never in the middle.

### 2.5 Pattern Completion Bias

**Problem:** If the first three self-evaluation items pass, the LLM predicts remaining items will also pass, creating "momentum of passing."

**Countermeasure -- Deliberate Failure Insertion:**
When running any checklist of 5+ items, identify the ONE item most likely to be a genuine failure. Evaluate that item FIRST, before the pass/fail pattern establishes.

**Countermeasure -- Explicit Doubt Prompt:**
After every 5 consecutive passes, pause and ask: "Am I passing these because they genuinely pass, or because the pattern of passing has made me expect a pass?" If specific textual evidence cannot be cited for the most recent pass, re-evaluate from scratch.

---

## Part 3: Mandatory Tool-Calling for Scoring

**Universal rule:** Any operation that involves counting, scoring, ranking, comparing numbers, or calculating a metric MUST be executed via a tool call, NOT performed in chain-of-thought.

### Operations That Must Be Tool-Called (Never LLM-Estimated)

| Operation | Why LLMs Fail | What To Do |
|---|---|---|
| **Flesch-Kincaid readability scoring** | LLMs cannot reliably count syllables or words per sentence. Estimates cluster around "grade 6" regardless of actual text. | Run FK formula via code execution. |
| **Word count per section** | LLMs systematically undercount in long passages, overcount in short ones. | Use `len(text.split())` via code execution. |
| **Sentence length measurement** | LLMs evaluate "feel" not count. | Split by sentence-ending punctuation, count words per sentence, flag any exceeding 25. |
| **Banned word/phrase scanning** | LLMs miss banned words that "fit" contextually. | Exact string matching via code execution against both banned lists (30 words from Voice + 30 phrases from Compliance). |
| **Checklist scoring and aggregation** | LLMs inflate their own checklist scores by 2-4 points on average. | For each item: LLM provides binary pass/fail with evidence. Tool counts passes, applies weights, returns weighted score. |
| **Belief chain sequence verification** | LLMs say "beliefs are in order" without tracking first-introduction position. | For each section: LLM labels primary belief. Tool verifies B1-B5 sequence with no skips. |

### LLM-Tool Handoff Protocol

```
STEP 1: LLM IDENTIFIES — What needs to be measured?
STEP 2: LLM EXTRACTS — Pull the relevant text/data from the copy.
STEP 3: TOOL EXECUTES — Send to code execution. The tool does the math.
STEP 4: LLM RECEIVES — Get the numeric result back.
STEP 5: LLM INTERPRETS — Apply the mental models to interpret the result.
```

**If tool calling is unavailable:**
1. Flag the limitation explicitly: "I cannot run tool-based scoring in this session."
2. Apply the Adversarial Re-Read and Forced Justification countermeasures as compensating controls.
3. Subtract 3 points from any self-assessed checklist score as a safety factor.

---

## Part 4: Universal Operating Rules

These rules apply to EVERY evaluation step across all sections.

| Rule | Model | What To Do |
|---|---|---|
| **Rule 1: Decompose Before Scoring** | First Principles | Never assign a single holistic score. Break every evaluation into component parts. Score each independently. Aggregate only after all parts are scored. |
| **Rule 2: Invert Before Confirming** | Pre-Mortem | Before confirming any output passes, actively search for ONE reason it might fail. If found, resolve it. If none found, the pass is genuine. |
| **Rule 3: Justify Boundary Ratings** | Forced Justification | Any rating on a multi-level scale must include: (a) the rating, (b) evidence for the rating, (c) evidence that rules out the adjacent rating. |
| **Rule 4: Normalize Before Comparing** | Z-Score | Never compare raw scores across different categories or time periods without normalizing for different baselines, variances, and sample sizes. |
| **Rule 5: Check for Bottleneck Before Optimizing** | Systems Thinking | Before improving any component, confirm it is the current bottleneck. Always optimize the bottleneck first. |
| **Rule 6: Apply Diminishing Returns Before Adding More** | Logarithmic Returns | Before adding more of anything, ask: "Will this addition produce more than 5% of the improvement that the first one produced?" If not, stop. |
| **Rule 7: Update Priors, Don't Replace Them** | Bayesian | When new test data arrives, adjust confidence levels -- do not delete old findings and replace them. A single result shifts belief; it does not create certainty. |
| **Rule 8: Prefer the Simpler Explanation** | Occam's Razor | Attribute results to the fewest variables that sufficiently explain them. Do not stack five behavioral science principles when "it was more specific" covers it. |
| **Rule 9: Build in Expiration** | Product Lifecycle | Every finding, proof item, and rated pattern must have a review date. Nothing in this system is permanent. |
| **Rule 10: Separate Signal from Noise Before Acting** | Signal-to-Noise | After any evaluation produces a list of issues, rank by impact. Fix the top 3 highest-impact issues before addressing any others. |
| **Rule 11: Protect Momentum at Transition Points** | Momentum | Every section-to-section transition is a potential momentum kill. Give extra scrutiny to the last sentence of each section and the first sentence of the next. |

---

## Checklist Tier Weighting (for Self-Evaluation)

| Tier | Items | Weight | Consequence of Failure |
|------|-------|--------|----------------------|
| **Hard Gates** (instant fail, rewrite required) | FK grade 5-7, zero banned words, zero banned phrases, belief chain sequence correct | 3 points each | A single failure here means the copy does not ship. No margin. |
| **Quality Signals** (failure degrades quality but does not disqualify) | Sentence variety, crossheads every 3-4 paragraphs, bullet style diversity, "Only This Product" test passes | 1 point each | Failures reduce effectiveness but do not create legal, brand, or structural risk. |
| **Polish Indicators** (desirable, diminishing returns) | Format shifts every 400-600 words, bucket brigade spacing, builder sentence limits | 0.5 points each | The first format shift matters; the difference between 450 words and 500 words is noise. |

**Scoring:** Maximum ~30 weighted points. Pass threshold = 24 weighted points with zero Hard Gate failures. Hard Gates represent ~25% of items but ~70% of quality impact -- evaluate them FIRST.

---

## Cross-Section Flow Checks (Priority Order)

Run in this order. If Check 1 fails, fix it BEFORE running Checks 2-4:

1. **Belief Progression Check** (bottleneck) -- if beliefs are out of sequence, emotional arc, momentum, and redundancy are all downstream symptoms. Fixing belief progression often resolves the other checks automatically.
2. **Momentum Check** -- second-highest leverage. A momentum failure usually indicates a structural problem.
3. **Emotional Arc Check** -- depends on belief progression being correct first.
4. **Redundancy Check** -- lowest leverage. Redundancy is usually a symptom of padding around a weak section.

---

*This document governs HOW the agent evaluates, not WHAT it evaluates. Sections 1-10 define the rules. This document ensures the rules are enforced with rigor, not theater.*
