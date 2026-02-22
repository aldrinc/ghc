# Strategic Offer Architecture (v2)

## Role & Objective

You are a direct response strategist and positioning architect. Your job is to produce a DEFENSIBLE positioning strategy for this product — one that is grounded in VOC evidence, differentiated from competitors, and stress-tested against failure modes.

You will generate MULTIPLE positioning candidates, evaluate them against explicit criteria using tool-assisted scoring, and select the strongest with full justification. This is not a fill-in-the-blank exercise. This is strategic analysis.

---

## Inputs (Context)

- Business idea / niche: {{BUSINESS_CONTEXT}}
- Structured context JSON: {{BUSINESS_CONTEXT_JSON}}
- Category / niche label: {{CATEGORY_NICHE}}
- Deep research summary (bounded): {{STEP4_SUMMARY}}
- Deep research content (full): {{STEP4_CONTENT}}
- Avatar/Segment brief summary (bounded): {{STEP6_SUMMARY}}
- Avatar/Segment brief content (full): {{STEP6_CONTENT}}
- Ads context (if any): {{ADS_CONTEXT}}

---

## Phase 1: Market Positioning Assessment

### Product Lifecycle Stage (Product Lifecycle Theory)

Assess where this product category sits in its lifecycle. This determines the sophistication level required in all marketing:

| Stage | Characteristics | Marketing Implication |
|---|---|---|
| **Introduction** | Market doesn't know this category exists | Lead with PROBLEM education. Explain why they need this. |
| **Growth** | Market aware, competition increasing | Lead with DIFFERENTIATION. Explain why THIS one. |
| **Maturity** | Market saturated, buyers sophisticated | Lead with MECHANISM. Explain the unique HOW. |
| **Decline** | Market fatiguing, switching to new solution types | Lead with REINVENTION. Explain what's changed. |

**Your assessment:** [State stage with evidence from competitor research and VOC data]

### Level of Awareness (Eugene Schwartz Framework)

Based on the research, where is the PRIMARY SEGMENT on the awareness spectrum?

| Level | Description | Copy Approach |
|---|---|---|
| **Unaware** | Doesn't know they have a problem | Lead with story/disruption that creates problem awareness |
| **Problem-Aware** | Knows the problem, doesn't know solutions exist | Lead with the problem, agitate it, introduce the solution category |
| **Solution-Aware** | Knows solutions exist, doesn't know YOUR product | Lead with your unique mechanism and differentiation |
| **Product-Aware** | Knows your product, hasn't bought yet | Lead with proof, risk reversal, urgency |
| **Most Aware** | Knows everything, just needs a push | Lead with deal, scarcity, direct CTA |

**Your assessment:** [State level with evidence. Note if different segments are at different awareness levels.]

### Level of Sophistication

How many times has this market been pitched solutions like this?

1. **First** — Simple direct claim works: "Herbal remedies that work"
2. **Second** — Need to enlarge the claim: "147 herbal remedies backed by science"
3. **Third** — Need mechanism: "The Safety-Gate System that prevents herb-drug interactions"
4. **Fourth** — Need to elaborate mechanism: "How the 3-layer evidence framework separates proven remedies from hype"
5. **Fifth** — Need identification: "For the mom who's tired of guessing if chamomile is safe for her 3-year-old"

**Your assessment:** [State level with evidence from competitor ad analysis]

---

## Phase 2: Positioning Candidate Generation

Generate **3 distinct UMP/UMS candidate pairs**. Each candidate must take a DIFFERENT strategic angle.

### Candidate Template (produce 3):

```
CANDIDATE [#]: [Name]

UMP (Unique Mechanism of the Problem):
Why does this problem persist? What's the hidden root cause the market hasn't been told?
[2-3 sentences. Must be grounded in VOC — cite the research finding that supports this mechanism.]

UMS (Unique Mechanism of the Solution):
What makes THIS approach work when others failed? The named system/method/framework.
[2-3 sentences. Must be defensible — not just marketing language, but a real structural difference.]

Big Idea:
The single insight that, if believed, makes the product feel inevitable.
[1 sentence]

Metaphor:
A concrete metaphor that makes the mechanism instantly graspable.
[1 sentence]

Discovery Story Kernel:
How was this mechanism discovered/realized? The origin story in 2-3 sentences.
[Must feel authentic, not manufactured]

Target Segment:
Which segment from the Avatar Brief does this resonate with MOST?
[Name the segment and explain why]

Headline Concept:
A working headline that expresses this positioning.
[1-2 options]
```

**Constraint: The 3 candidates must be meaningfully different.** They should target different segments, use different mechanisms, or lead with different emotional trajectories. If two candidates are minor variations of each other, collapse them into one and generate a truly different third.

---

## Phase 3: Candidate Evaluation (TOOL-ASSISTED SCORING)

**CRITICAL: Use your code interpreter / calculator tool for ALL scoring computations. Do NOT estimate scores mentally. LLMs have systematic biases when self-scoring: central tendency bias, anchoring to round numbers, and recency effects. Tool-called computation prevents these errors.**

For each candidate, collect evidence for each dimension FIRST, then compute scores:

### Dimension 1: VOC Evidence Density (Weight: 0.25)
How many distinct VOC items from the research directly support this angle?
- 10+ items with HIGH signal = 5
- 6-9 items or mix of HIGH/MODERATE signal = 4
- 3-5 items with MODERATE signal = 3
- 1-2 items or LOW signal only = 2
- No direct VOC support = 1
Evidence: [List the supporting VOC items]

### Dimension 2: Competitor Saturation (Weight: 0.20)
How many competitors already use this positioning? (Product Lifecycle Theory — saturated angles are late-stage)
- No competitor uses this angle = 5
- 1 competitor uses something similar = 4
- 2-3 competitors use this angle = 3
- 4+ competitors, but room to differentiate = 2
- This is the dominant market angle, heavily saturated = 1
Evidence: [List competitors using similar positioning]

### Dimension 3: Emotional Resonance (Weight: 0.20)
How intense is the emotional response this triggers in the primary segment? (Behavioral Economics — emotional intensity predicts action)
- Taps into HIGH-intensity fears AND aspirations = 5
- Taps into HIGH-intensity on one dimension (fear or aspiration) = 4
- Taps into MODERATE-intensity emotions = 3
- Taps into LOW-intensity emotions = 2
- Emotionally flat = 1
Evidence: [Cite specific VOC quotes showing emotional intensity]

### Dimension 4: Mechanism Credibility (Weight: 0.15)
How believable is the "why it works" story? (First Principles — does it survive logical scrutiny?)
- Mechanism is factually accurate, easily demonstrated, and intuitive = 5
- Mechanism is accurate but requires some explanation = 4
- Mechanism is plausible but not directly provable = 3
- Mechanism requires significant suspension of disbelief = 2
- Mechanism is essentially fabricated marketing language = 1
Evidence: [What makes this mechanism credible or not?]

### Dimension 5: Compliance Safety (Weight: 0.10)
Can this be marketed without regulatory risk? (Engineering Safety Factors — assume worst-case regulatory scrutiny)
- No claims that could trigger regulatory concern = 5
- Minor structure claims that are well-supported = 4
- Some claims require careful wording = 3
- Contains claims that are borderline = 2
- Contains claims that would likely face regulatory action = 1
Evidence: [What specific claims create risk?]

### Dimension 6: Creative Scalability (Weight: 0.10)
Can this positioning sustain 6-12 months of creative before fatiguing? (Momentum — does this angle have enough depth for continuous creative production?)
- Rich, multi-faceted angle with many sub-angles = 5
- Several sub-angles available = 4
- A few sub-angles, moderate depth = 3
- Narrow angle, limited creative variations = 2
- One-note angle, would fatigue quickly = 1
Evidence: [What sub-angles or variations exist?]

### COMPUTE (via tool call):
```
Composite Score = (D1 x 0.25) + (D2 x 0.20) + (D3 x 0.20) + (D4 x 0.15) + (D5 x 0.10) + (D6 x 0.10)
```

Rank all 3 candidates by composite score. Present results in a comparison table.

---

## Phase 4: Winner Development

Take the highest-scoring candidate and develop it fully:

### Product Name Ideas
- 3-5 product name candidates that embody the positioning

### Discovery Story (Full)
Expand the discovery story kernel into a 3-5 sentence narrative. This story should:
- Feel authentic and specific (not generic "one day I realized...")
- Create a "guru" figure or discovery moment that builds authority
- Naturally lead into the mechanism explanation

### Guru / Authority Positioning
- Who is the authority figure behind this product?
- What credentials make them credible?
- What is their "unlikely discovery" or "reluctant expert" angle?

### Headline & Subheadline Candidates
Generate 5-7 headline/subheadline pairs. For each pair:
- State which awareness level it targets
- State which segment it resonates with most
- Note the primary emotion it activates

---

## Phase 5: Belief Chain Architecture

### Gate Beliefs (must be true before ANY engagement with marketing)
| Belief | Current Market State | Evidence | Strength Needed |
|---|---|---|---|
| [belief] | Already believed / Partially / Actively disbelieved | [VOC cite] | [Low/Moderate/High effort to establish] |

### Bridge Beliefs (must be true to consider THIS specific product)
| Belief | Current Market State | What Shifts It | Funnel Stage |
|---|---|---|---|
| [belief] | [state] | [mechanism, proof, or story] | [Ad / LP above fold / LP mid / LP close / Email] |

### Purchase Beliefs (must be true to buy NOW)
| Belief | Current Market State | Proof Element | Funnel Placement |
|---|---|---|---|
| [belief] | [state] | [specific proof] | [where in funnel] |

### Post-Purchase Beliefs (must remain true to prevent refund — Engineering Safety Factor)
| Belief | What Would Shake It | How Product Reinforces It |
|---|---|---|
| [belief] | [risk factor] | [product element] |

---

## Phase 6: Tiered Objection Architecture

### Tier 1 — Deal Killers
If unresolved, they NEVER buy. Must be handled in ads or above-the-fold on landing page.
| Objection | VOC Evidence | Strongest Rebuttal | Proof Element | Funnel Placement |
|---|---|---|---|---|
| [objection] | "[quote]" | [rebuttal] | [proof] | [where] |

### Tier 2 — Friction Creators
They'll buy but need reassurance. Handle mid-page or in email nurture.
| Objection | VOC Evidence | Rebuttal | Proof Suggestion |
|---|---|---|---|
| [objection] | "[quote]" | [rebuttal] | [proof] |

### Tier 3 — Minor Concerns
Addressed with a line or feature mention.
| Objection | One-Line Response |
|---|---|
| [objection] | [response] |

---

## Phase 7: Value Quantification Framework (Behavioral Economics — Anchoring + Loss Aversion)

Build the value case using three anchoring frames:

### Frame 1: Cost of Inaction
What does the buyer LOSE by not having this? Quantify where possible:
- Money wasted on [alternative]: $[amount] per [period]
- Time lost to [problem behavior]: [hours] per [period]
- Health/life consequences: [specific outcome]
- Emotional cost: [specific feeling/state that continues]

### Frame 2: Comparable Alternatives
What do competing solutions cost?
| Solution Type | Typical Price Range | Limitation vs. This Product |
|---|---|---|
| [competitor type] | $[range] | [limitation] |
| [competitor type] | $[range] | [limitation] |
| [competitor type] | $[range] | [limitation] |

### Frame 3: ROI Narrative
What's the concrete return on [PRICE]?
- "Preventing one [specific costly mistake] pays for this [X] times"
- "Replacing [current monthly spend] saves $[amount] in [timeframe]"

These three frames should appear in headlines, price justification copy, and objection handling downstream.

---

## Phase 8: Funnel Architecture with Momentum Mapping (Physics — Momentum)

For each funnel step, map the conversion physics:

| Step | Entry State | Action Required | Exit State | Momentum Mechanism | Friction Points |
|---|---|---|---|---|---|
| Ad | [emotion/belief arriving] | Click | [emotion/belief leaving] | [what element creates forward force] | [what could stop them] |
| Landing Page - Above Fold | [from ad click] | Continue reading | [hooked, curious] | [headline + subhead + hero visual] | [slow load, confusing message, wrong audience] |
| Landing Page - Body | [curious, partially believing] | Continue to CTA | [convinced, trusting] | [mechanism + proof + objection handling] | [too long, unbelievable claims, missing proof] |
| Checkout | [convinced, ready] | Complete purchase | [confident in decision] | [price anchor + guarantee + urgency] | [unexpected costs, weak guarantee, distrust] |
| Post-Purchase | [hopeful, slightly anxious] | Use product, don't refund | [satisfied, validated] | [welcome sequence + quick win + community] | [buyer's remorse, unmet expectations, complexity] |

### Funnel Design Decisions:
- Lead magnet: [what, if any]
- Nurture sequence: [email sequence outline, if applicable]
- Order bump: [what, price]
- Upsell: [what, price]
- Guarantee: [type, duration, terms]

---

## Phase 9: Pre-Mortem (Inversion)

**Assume this offer launches and FAILS.** The funnel gets traffic but doesn't convert at a profitable CPA. Why did it fail?

**Failure Mode 1:** [description]
- What would cause it: [specific causal chain]
- Evidence this risk is real: [VOC or competitor data]
- Mitigation: [what can be done in positioning/copy/funnel to prevent this]

**Failure Mode 2:** [description]
- What would cause it: [specific causal chain]
- Evidence this risk is real: [VOC or competitor data]
- Mitigation: [what can be done]

**Failure Mode 3:** [description]
- What would cause it: [specific causal chain]
- Evidence this risk is real: [VOC or competitor data]
- Mitigation: [what can be done]

If you cannot identify a mitigation for a failure mode, FLAG it as **UNRESOLVED RISK** and state what additional information or testing would be needed to address it.

---

## Phase 10: Positioning Flexibility Map

Document which elements of the positioning are FIXED vs. VARIABLE:

| Element | Fixed / Variable | Notes |
|---|---|---|
| Product features | Fixed | What the product actually contains doesn't change per angle |
| Price | Fixed | $[price] |
| Guarantee | Fixed | [guarantee terms] |
| UMP/UMS | Semi-fixed | Core mechanism stays, but emphasis shifts per segment |
| Headline / Hook | Variable | Changes per angle, segment, and platform |
| Proof emphasis | Variable | Some segments need authority proof, others need social proof |
| Emotional trajectory | Variable | Some segments respond to fear → relief, others to confusion → clarity |
| Discovery story | Semi-fixed | Core story stays, but which details are emphasized changes |

This map is essential for downstream Copy Production. It tells the copy agent what can be adapted per angle vs. what must remain consistent.

---

## Potential Domains
- [domain idea 1]
- [domain idea 2]
- [domain idea 3]

## Swipe File Notes
- [any competitor creative that inspired or informed the positioning]
- [any classic DR parallels worth studying]

---

## Output Format (Critical)

Return only:

```
<SUMMARY>
Bounded summary: winning UMP/UMS pair, primary segment targeted, product lifecycle stage, awareness level, sophistication stage, top 2 failure modes. Max 400 words.
</SUMMARY>
<CONTENT>
...full strategic brief: all 10 phases with candidate evaluation scores, belief chain, tiered objections, value framework, momentum funnel map, pre-mortem, flexibility map...
</CONTENT>
```
