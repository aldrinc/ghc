# Offer Scoring Framework

**Version**: 2.0
**System**: Offer Agent Pipeline
**Principle**: LLMs assess. Tools score. Humans decide.

---

## 1. Core Architecture: Why LLMs Must Never Score Themselves

### The Problem

LLMs are structurally biased toward self-validation. When asked to both *generate* and *evaluate* their own output, three failure modes emerge:

1. **Confirmation bias**: The same reasoning patterns that produced the output also evaluate it. If the LLM thinks "this bonus addresses the objection," it will rate the objection coverage as strong for the same (potentially flawed) reason it chose the mapping.

2. **Score inflation**: LLMs default to positive framing. Without external constraints, self-assessed scores cluster in the 7-9 range regardless of actual quality. In v1 testing, an offer scored 7.9/10 raw. After applying engineering safety factors, it dropped to 6.05 — a 24% derating that revealed genuine weaknesses the LLM would never have flagged on its own.

3. **Unfalsifiability**: When the same system generates claims and evaluates them, there is no adversarial check. The evaluation can't catch what the generator can't see.

### The Solution: Separation of Concerns

```
LLM Role                          Tool Role                        Human Role
-----------                       ---------                        ----------
Generate offer elements           Compute scores from ratings      Select UMP/UMS (Step 3)
Provide dimensional ratings       Apply safety factors             Select final variant (post-Step 5)
Classify evidence quality         Apply dimension weights           Override when HUMAN_REVIEW flagged
State kill conditions             Compute Z-scores vs baseline     Validate against market knowledge
Identify structural weaknesses    Determine PASS/REVISE/HUMAN_REVIEW  Make go/no-go decision
Assess momentum and coherence     Rank variants deterministically  Break ties between close variants
Generate revision notes           Flag suspicious patterns         Provide missing data
```

**The LLM never sees a composite score, never computes a pass/fail, and never decides whether to iterate.** These are all tool outputs consumed by the orchestrator.

---

## 2. Mental Models as Scoring Infrastructure

Each mental model is not a suggestion — it is a *procedure* with failure triggers that constrain LLM output into scorable structure.

### 2.1 Engineering Safety Factors

**What it does**: Discounts scores based on how well-supported the evidence is.

**Why it matters**: An LLM claiming "this offer is strongly differentiated" based on its own reasoning (ASSUMED) should count for less than the same claim backed by direct competitor data comparison (OBSERVED).

**Implementation**:

| Evidence Quality | Safety Factor | Meaning |
|:---:|:---:|:---|
| OBSERVED | 0.9 | Directly verified against provided data (competitor teardowns, VOC quotes, explicit product features) |
| INFERRED | 0.75 | Logically derived from observed data with stated inference chain |
| ASSUMED | 0.6 | Not supported by provided data — LLM reasoning only |

**Formula**: `safety_adjusted_score = raw_score x safety_factor`

**How it prevents inflation**: A dimension rated 8/10 with OBSERVED evidence produces 7.2. The same 8/10 with ASSUMED evidence produces 4.8. This is a 33% penalty for unsubstantiated claims — exactly what we want.

**Failure trigger**: If >40% of all assessments across all dimensions are classified ASSUMED, the evaluation is structurally weak and should be flagged.

---

### 2.2 First Principles Decomposition

**What it does**: Forces every claim to be decomposed into atomic observations before scoring.

**Implementation in scoring context**:

For every dimensional rating the LLM provides:
1. State the claim (e.g., "Objection coverage is strong")
2. List 2-5 atomic observations that support it
3. Classify each observation as OBSERVED / INFERRED / ASSUMED
4. If >50% of supporting observations are ASSUMED, downgrade to HYPOTHESIS

**How it feeds scoring**: The evidence classification from decomposition directly determines the safety factor applied to that dimension's score.

**Failure trigger**: If the LLM cannot list atomic observations for a rating, it is confabulating. The tool should receive an ASSUMED classification.

---

### 2.3 Information Theory (Novelty Assessment)

**What it does**: Measures how much *new* information the offer adds beyond what competitors already provide.

**Implementation**:

Every offer element is classified against the competitor baseline:

| Classification | Weight | Meaning |
|:---:|:---:|:---|
| NOVEL | 1.0 | Not present in any competitor offer — genuinely new |
| INCREMENTAL | 0.3 | Present in some form but meaningfully improved |
| REDUNDANT | 0.0 | Table stakes — present in most/all competitor offers |

**Formula**: `information_value = weighted_sum / total_elements`

**Threshold**: information_value >= 0.35 (passes), < 0.35 (fails)

**Why 0.35**: An offer with all REDUNDANT elements scores 0. An offer with all NOVEL elements scores 1.0. The 0.35 threshold means at least ~35% of the offer's value comes from genuinely new or meaningfully improved elements. Below this, the offer doesn't differentiate enough to justify the buyer's attention cost.

**Failure trigger**: The LLM classifies elements against the provided competitor teardowns, not against its general knowledge. If no competitor data is provided, ALL classifications must be ASSUMED.

---

### 2.4 Behavioral Economics (Hormozi Value Equation)

**What it does**: Scores each offer element against the four levers of perceived value.

**The equation**: `Value = (Dream Outcome x Perceived Likelihood) / (Time Delay x Effort & Sacrifice)`

**Lever rating convention**:

| Lever | Scale | Direction | Better for buyer |
|:---:|:---:|:---:|:---:|
| Dream Outcome | 1-10 | Higher = bigger result | Higher |
| Perceived Likelihood | 1-10 | Higher = more believable | Higher |
| Time Delay | 1-10 | 1=instant, 10=slow | Lower |
| Effort & Sacrifice | 1-10 | 1=effortless, 10=extreme | Lower |

**Score normalization**: The tool inverts the denominator levers using `(11 - raw_value)` so that all higher values mean better scores. Final output is normalized to a 1-10 scale.

**Cap detection**: If any element rates time_delay <= 1 or effort_sacrifice <= 1 (claiming instant/effortless), the tool flags this for human review. Nothing is truly zero-delay, zero-effort.

**Why per-element, not aggregate**: The aggregate score hides lever imbalances. In v1 testing, the core handbook scored 1.50 (high effort/delay) while bonuses scored 8+ (low effort/delay). This insight — bonuses compensate for core product friction — is invisible in an aggregate score.

---

### 2.5 Falsifiability (Kill Conditions)

**What it does**: Forces every major assessment to state the conditions under which it would be wrong.

**Implementation in scoring**: Every dimension assessment must include:
- **Kill condition**: "This rating would be wrong if: [specific, observable condition]"
- **Upgrade condition**: "Confidence would increase if: [specific, observable condition]"

**How it feeds scoring**: Kill conditions are stored in the composite scorer output. They do not affect the numerical score but provide decision context for human reviewers.

**Failure trigger**: If a kill condition is too vague to be tested (e.g., "this would change if circumstances were different"), it is unfalsifiable. The assessment should be flagged.

---

### 2.6 Z-Score Normalization

**What it does**: Positions each dimensional score relative to the competitive baseline.

**Implementation**:

```
z_score = (safety_adjusted_score - competitor_baseline_mean) / competitor_baseline_spread
```

**Interpretation**:
- z > 1.0: This dimension is meaningfully above the competitive average
- z between -1.0 and 1.0: Within normal competitive range
- z < -1.0: This dimension is meaningfully below the competitive average — a red flag

**Why it matters**: A raw score of 7/10 means nothing without context. 7/10 in a market where competitors average 4/10 is excellent. 7/10 where competitors average 8/10 is below par.

**Data source**: Competitor baselines come from the provided competitor teardowns analyzed in Step 5 (self-evaluation). The LLM estimates mean and spread from the teardown data.

---

### 2.7 Systems Thinking (Dependency & Bottleneck Analysis)

**What it does**: Identifies single points of failure and fragility in the offer structure.

**Implementation in scoring**: The "Bottleneck Resilience" dimension evaluates:
1. **Removal test**: If the strongest element were removed, would the offer still be viable?
2. **Dependency chains**: Elements that only work if another element is present
3. **Guarantee dependency**: Would the offer compel purchase without its special guarantee?
4. **Proof dependency**: Would claims be credible without external proof (mechanism transparency alone)?

**How it feeds scoring**: This dimension is weighted 0.10 in the composite score but serves as a structural integrity check. A high-scoring offer with low bottleneck resilience is fragile — any single failure can cascade.

---

### 2.8 Momentum Analysis (Force Diagram)

**What it does**: Evaluates the buyer's psychological journey through the offer.

**Implementation in scoring**: The "Momentum Continuity" dimension evaluates:
1. Every transition point in the offer sequence for net thrust vs. drag
2. Whether the price reveal occurs at maximum accumulated momentum
3. Whether the CTA arrives at peak accumulated momentum
4. Whether hidden momentum breaks exist (points the offer claims are positive but evaluation identifies as negative)

**How it feeds scoring**: Weighted 0.15 in composite — one of the three highest-weight dimensions because momentum breaks cause immediate bounces regardless of offer quality.

---

## 3. The Six Scoring Tools

### Tool Invocation Map

| Pipeline Step | Tool Called | What It Scores | Input Source |
|:---:|:---:|:---|:---|
| Step 2 | `calibration_consistency_checker` | Market calibration logical consistency | Step 2 JSON |
| Step 3 | `ump_ums_scorer` | UMP/UMS pair quality across 7 dimensions | Step 3 JSON |
| Step 4 | `hormozi_scorer` | Value equation per offer element | Step 4 JSON (per variant) |
| Step 4 | `objection_coverage_calculator` | Objection coverage gaps | Step 4 JSON (per variant) |
| Step 4 | `novelty_calculator` | Information value vs competitors | Step 4 JSON (per variant) |
| Step 5 | `composite_scorer` | 8-dimension composite with safety factors | Step 5 JSON (all variants) |

---

### 3.1 Calibration Consistency Checker

**Purpose**: Catch logical contradictions in market calibration before they propagate to offer construction.

**Input**: Market calibration JSON with awareness, sophistication, lifecycle assessments.

**What it checks** (conflict rules):

| Condition | Severity | Rationale |
|:---|:---:|:---|
| Introduction lifecycle + Most-aware buyers | ERROR | Introduction markets don't have most-aware buyers |
| Maturity lifecycle + Low sophistication | WARNING | Mature markets typically have sophisticated buyers |
| Unaware audience + 10+ competitors | ERROR | If 10+ companies are selling, audience is at least problem-aware |
| Decline lifecycle + Low sophistication | WARNING | Markets decline because buyers are exhausted |
| Most-aware + Low sophistication | WARNING | Awareness and sophistication typically correlate |

**Output**: `{ passed: bool, error_count, warning_count, conflicts[] }`

**Pass/Fail logic**: ERRORs cause failure. WARNINGs are advisory only.

---

### 3.2 UMP/UMS Scorer

**Purpose**: Rank 3-5 UMP/UMS paired sets to inform human selection.

**Input**: Array of UMP/UMS pairs, each with 7-dimension ratings (1-10) and evidence classifications.

**Dimensions and weights**:

| Dimension | Weight | What It Measures |
|:---|:---:|:---|
| Competitive Uniqueness | 0.20 | Is this mechanism absent from competitor offers? |
| VOC Groundedness | 0.20 | Does the mechanism address what the audience actually says/feels? |
| Believability | 0.15 | Will a skeptical buyer accept this mechanism explanation? |
| Mechanism Clarity | 0.15 | Can this be explained in one sentence without jargon? |
| Angle Alignment | 0.10 | Does this mechanism naturally serve the selected angle? |
| Compliance Safety | 0.10 | Can this mechanism be marketed without regulatory risk? |
| Memorability | 0.10 | Will the buyer remember and repeat this mechanism name? |

**Computation**:
1. For each pair, for each dimension: `adjusted = raw_score x safety_factor(evidence_quality)`
2. `composite = sum(adjusted x weight) across all 7 dimensions`
3. Rank pairs by composite descending
4. Report per-pair: composite, strongest/weakest dimensions, evidence summary, delta from top

**Output**: Ranked pairs with composite scores, presented to human for selection.

**Key design decision**: The tool ranks but does not select. A lower-ranked pair might be strategically correct for reasons the tool can't assess (brand alignment, existing assets, team capabilities). The human decides.

---

### 3.3 Hormozi Value Equation Scorer

**Purpose**: Score each offer element's perceived value and expose lever imbalances.

**Input**: Value stack JSON with per-element lever ratings.

**Computation per element**:
```
numerator = dream_outcome x perceived_likelihood
time_inv = 11 - time_delay
effort_inv = 11 - effort_sacrifice
raw_value = (numerator x time_inv x effort_inv) / 1000
value_score = clamp(raw_value, 0.1, 10.0)
```

**Aggregate**: `average(value_score across all elements)`

**Diagnostic outputs**:
- Per-element scores (exposes which elements drive value vs. which drag)
- Lever averages (exposes systemic lever weaknesses)
- Lever diagnosis (flags dream_outcome < 6, likelihood < 6, time_delay > 5, effort > 5)
- Cap warnings (flags any time_delay or effort_sacrifice rated 1)

**v2 fixes from v1 testing**:
- v1 used ratio format (values around 0.5-1.5) — not human-readable
- v2 normalizes to 1-10 scale
- v2 inverts denominator levers properly: lower time_delay/effort_sacrifice (better for buyer) produces higher scores
- v2 flags suspicious 1/1 ratings on delay/effort

---

### 3.4 Objection Coverage Calculator

**Purpose**: Identify uncovered objections and flag suspicious patterns.

**Input**: Objection mapping JSON (objection, source, covered, coverage_strength, mapped_element).

**Computation**:
```
coverage_pct = (covered_count / total_objections) x 100
```

**Diagnostic checks**:
1. **Suspicious perfect coverage**: If coverage_pct == 100%, flag it. In practice, unknown-unknown objections always exist. Perfect coverage means the LLM is mapping too generously.
2. **Unknown-unknown check**: Verify the prompt forced generation of 2-3 hypothetical objections (source = "hypothesized"). If absent, flag as "missing unknown-unknown generation."
3. **Weak coverage**: Identify covered objections with coverage_strength < 5 — technically covered but poorly addressed.

**Output**: Coverage stats, uncovered list, weak coverage list, warnings.

---

### 3.5 Novelty Calculator

**Purpose**: Measure information value of the offer vs. competitor baseline.

**Input**: Element classifications JSON (element_name, classification: NOVEL/INCREMENTAL/REDUNDANT).

**Computation**:
```
weighted_sum = sum(NOVEL x 1.0 + INCREMENTAL x 0.3 + REDUNDANT x 0.0)
information_value = weighted_sum / total_elements
meets_threshold = information_value >= 0.35
```

**Output**: Information value, per-classification counts, threshold pass/fail, lists of most redundant and most novel elements.

---

### 3.6 Composite Scorer

**Purpose**: Compute the final pass/revise/human_review verdict across 8 dimensions for all offer variants.

**Input**: Evaluation JSON with per-variant, per-dimension data (raw_score, evidence_quality, competitor_baseline, kill_condition).

**The 8 dimensions and their weights**:

| Dimension | Weight | What It Measures |
|:---|:---:|:---|
| Value Equation | 0.15 | Hormozi lever balance and strength |
| Objection Coverage | 0.15 | Completeness of objection addressing |
| Competitive Differentiation | 0.15 | Novelty and positioning vs. competitors |
| Compliance Safety | 0.10 | Regulatory risk level |
| Internal Consistency | 0.10 | Coherence of angle, UMP/UMS, elements |
| Clarity & Simplicity | 0.10 | Cognitive load and comprehensibility |
| Bottleneck Resilience | 0.10 | Single-point-of-failure fragility |
| Momentum Continuity | 0.15 | Psychological flow through the offer |

**Weight rationale**: The three highest-weight dimensions (0.15 each) — value equation, objection coverage, competitive differentiation, and momentum continuity — are the four dimensions where failure most directly causes buyer abandonment. Compliance (0.10) is critical but binary (either safe or not). Internal consistency, clarity, and resilience (0.10 each) are structural quality indicators that affect conversion but are more forgiving.

**Computation per variant**:
```
FOR EACH dimension:
    safety_factor = lookup(evidence_quality)  # 0.9 / 0.75 / 0.6
    safety_adjusted = raw_score x safety_factor

    IF competitor_baseline available:
        z_score = (safety_adjusted - baseline_mean) / baseline_spread

    weighted_contribution = safety_adjusted x dimension_weight

composite_raw = sum(raw_score x weight)
composite_safety_adjusted = sum(weighted_contribution)
```

**Verdict logic**:

| Condition | Verdict | Next Action |
|:---|:---:|:---|
| composite_safety_adjusted >= 5.5 | PASS | Present to human for variant selection |
| composite_safety_adjusted < 5.5 AND iteration < max_iterations | REVISE | Re-run Step 4 with revision notes targeting bottom 2 dimensions |
| composite_safety_adjusted < 5.5 AND iteration >= max_iterations | HUMAN_REVIEW | Flag for human with specific questions |

**Multi-variant handling (v2)**:
- Each variant scored independently
- Variants ranked by composite_safety_adjusted
- Passing variants identified
- Best variant for revision targeting identified (if no variants pass)

---

## 4. Scoring Flow: End-to-End

### Step 2: Calibration Validation

```
LLM produces → calibration JSON (awareness, sophistication, lifecycle)
                    ↓
Tool: calibration_consistency_checker
                    ↓
Result: passed = true/false + conflict list
                    ↓
If ERROR: halt pipeline, surface conflicts for human resolution
If WARNINGS only: proceed with warnings noted
```

### Step 3: UMP/UMS Selection

```
LLM produces → 3-5 UMP/UMS pairs with 7-dimension ratings
                    ↓
Tool: ump_ums_scorer
                    ↓
Result: ranked pairs with composites + diagnostics
                    ↓
Presented to human → human selects pair
                    ↓
Selected pair → injected into Step 4
```

### Step 4: Per-Variant Element Scoring

```
LLM produces → base offer + 2-3 variants (each with value stack, objection mapping, novelty classifications)
                    ↓
FOR EACH variant (base + variants):
    Tool: hormozi_scorer(value_stack)     → element scores + lever diagnostics
    Tool: objection_coverage_calculator   → coverage gaps + warnings
    Tool: novelty_calculator              → information value + threshold check
                    ↓
Scored variants → passed to Step 5
```

### Step 5: Composite Evaluation

```
LLM produces → 8-dimension evaluation per variant (raw scores + evidence + baselines + kill conditions)
                    ↓
Tool: composite_scorer(evaluation, config)
                    ↓
Result: per-variant composites + verdicts + variant ranking
                    ↓
IF any PASS:  → present passing variants to human for selection
IF all REVISE: → extract revision notes for best variant → re-run Step 4
IF HUMAN_REVIEW: → flag with specific questions → human decides
```

---

## 5. Anti-Inflation Mechanisms

These are the specific checks that prevent the LLM from gaming the scoring system.

### 5.1 Evidence Classification Enforcement

Every dimensional rating MUST be accompanied by an evidence classification. The LLM does not get to choose the safety factor — the tool applies it automatically based on the classification.

**LLM incentive to inflate evidence quality**: The LLM might classify INFERRED evidence as OBSERVED to avoid the penalty.

**Countermeasure**: Step 5 (self-evaluation) independently re-verifies evidence classifications from Step 4. If Step 5 finds evidence that was classified OBSERVED but cannot be traced to specific provided data, it must reclassify as INFERRED or ASSUMED.

### 5.2 Perfect Coverage Warning

If objection coverage hits 100%, the tool flags it as suspicious. This forces the human to verify whether the LLM was genuinely thorough or just mapped too generously.

**Additional check**: The prompt forces generation of 2-3 "unknown-unknown" objections (source = "hypothesized"). If these are absent, the tool warns about missing adversarial objection generation.

### 5.3 Cap Detection

If any Hormozi lever is rated at the extreme (time_delay = 1 or effort_sacrifice = 1), the tool flags it. Nothing is truly instant and effortless — the buyer still has to find the file, open it, and scan it.

### 5.4 Cross-Step Verification

Step 5 does NOT take Step 4's self-assessments at face value. It independently re-evaluates:
- Novelty classifications (re-checks against competitor teardowns)
- Objection coverage claims (re-verifies mapping strength)
- Momentum map (re-assesses net force at each transition)
- UMP/UMS coherence (verifies against Step 3 selected pair)
- Binding constraint compliance (verifies against Step 2 constraints)

### 5.5 Multi-Variant Comparison

By generating a base offer + 2-3 structural variants and scoring each independently, the system creates a competitive environment. If the base offer scores 7.2 but a variant scores 5.8, the variant exposes weaknesses the base may hide. Conversely, if all variants score similarly, it suggests the scoring is stable and not an artifact of a single construction approach.

---

## 6. Human Decision Points

### 6.1 UMP/UMS Selection (Post-Step 3)

**What the human sees**: Ranked UMP/UMS pairs with:
- Composite scores (safety-adjusted)
- Per-dimension breakdown (which dimensions are strong/weak per pair)
- Evidence summary (how much of the assessment is OBSERVED vs. ASSUMED)
- Strategic notes from the LLM (qualitative reasoning for each pair)
- Delta from top pair (how far behind the leader each alternative is)

**What the human decides**: Which pair to use. The tool ranking is advisory — the human may choose a lower-ranked pair for strategic reasons (existing brand assets, compliance concerns, personal market knowledge).

### 6.2 Variant Selection (Post-Step 5)

**What the human sees**: All variants with:
- Composite scores and verdicts
- Per-dimension scores with evidence quality
- Cross-variant analysis (best-in-dimension map, complementary elements)
- Variant hypothesis assessment (did the structural test confirm its hypothesis?)

**What the human decides**: Which variant (or hybrid) to finalize.

### 6.3 HUMAN_REVIEW Escalation

**When it triggers**: After max iterations (default: 2), if no variant passes the threshold (default: 5.5).

**What the human sees**: Specific questions about:
- Which dimensions remain weak and why
- Whether the issue is data quality (upstream research problem) or structural (offer construction problem)
- What additional data/decisions would resolve the weakness

---

## 7. Scoring Configuration

These parameters are configurable per pipeline run:

| Parameter | Default | Description |
|:---|:---:|:---|
| `score_threshold` | 5.5 | Minimum composite_safety_adjusted for PASS |
| `max_iterations` | 2 | Maximum Step 4 → Step 5 iteration loops |
| `novelty_threshold` | 0.35 | Minimum information_value for novelty pass |

### Dimension weights (advanced):

| Dimension | Default Weight | Adjustable? |
|:---|:---:|:---:|
| value_equation | 0.15 | Yes |
| objection_coverage | 0.15 | Yes |
| competitive_differentiation | 0.15 | Yes |
| compliance_safety | 0.10 | Yes |
| internal_consistency | 0.10 | Yes |
| clarity_simplicity | 0.10 | Yes |
| bottleneck_resilience | 0.10 | Yes |
| momentum_continuity | 0.15 | Yes |

Weights must sum to 1.0. Adjustments should be rare and justified by market-specific factors (e.g., increasing compliance_safety weight for health/finance products).

### UMP/UMS dimension weights:

| Dimension | Default Weight |
|:---|:---:|
| competitive_uniqueness | 0.20 |
| voc_groundedness | 0.20 |
| believability | 0.15 |
| mechanism_clarity | 0.15 |
| angle_alignment | 0.10 |
| compliance_safety | 0.10 |
| memorability | 0.10 |

### Safety factor values:

| Evidence Quality | Safety Factor |
|:---|:---:|
| OBSERVED | 0.9 |
| INFERRED | 0.75 |
| ASSUMED | 0.6 |

These are not adjustable. The 0.9/0.75/0.6 spread is calibrated to create meaningful derating without making the system unusable. A 10% penalty for OBSERVED (acknowledging even direct evidence has some uncertainty) and a 40% penalty for ASSUMED (acknowledging unsubstantiated claims should count for much less) creates the right incentive structure.

---

## 8. Diagnostic Outputs

Every tool returns a `diagnosis` string in addition to structured data. These are human-readable summaries designed for quick triage:

**Calibration**: "Passed: True | Errors: 0 | Warnings: 1"
**UMP/UMS**: "Top pair: X/Y (score: 6.8, raw: 8.05). Spread: 0.8"
**Hormozi**: "Aggregate: 5.61/10 across 3 elements. Best: Z (8.1), Worst: W (3.14). Lever issues: effort is high."
**Objection**: "Coverage: 60%. 2 uncovered, 1 weak. Unknown-unknowns: yes."
**Novelty**: "Information value: 0.55 (PASSES 0.35 threshold). 3 novel, 1 incremental, 2 redundant."
**Composite**: "Best: variant_a (5.66, verdict: PASS). Passing variants: variant_a, base."

---

## 9. Implementation Reference

All scoring tools are implemented in: `test/scoring_tools.py`

Function signatures:

```python
def calibration_consistency_checker(calibration: dict) -> dict
def ump_ums_scorer(pairs: list[dict]) -> dict
def hormozi_scorer(value_stack: dict) -> dict
def objection_coverage_calculator(mapping: dict) -> dict
def novelty_calculator(elements: dict) -> dict
def composite_scorer(evaluation: dict, config: dict | None = None) -> dict
```

Run smoke test: `python3 test/scoring_tools.py`

Pipeline orchestrator specification: `prompts/pipeline-orchestrator.md`

---

## 10. What This Framework Does NOT Cover

1. **Upstream research quality**: The scoring framework assumes provided inputs (VOC, competitor teardowns, purple ocean research) are high quality. Garbage in, garbage out. If the upstream research is thin, the offer will score well against a weak baseline — a meaningless pass.

2. **Creative quality**: The framework scores structural completeness, competitive positioning, and logical coherence. It does NOT assess whether the copy is compelling, whether the hook is attention-grabbing, or whether the naming is memorable. Those are downstream agent concerns (Copywriting Agent).

3. **Market validation**: Scoring tells you the offer is *structurally sound*. It does not tell you the market will buy it. Only traffic and conversion data validate market fit.

4. **Long-term brand effects**: An offer can score perfectly on all 8 dimensions and still erode brand trust over time if it's too aggressive. This is a strategic human judgment call, not a scoring tool output.
