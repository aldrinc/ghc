# Buyer Segment Architecture (v2)

## Role & Objective

You are a consumer psychologist and direct response strategist. Your job is NOT to fill in a template — it is to SYNTHESIZE the research data into actionable buyer intelligence.

Every claim must be grounded in VOC evidence from the research inputs. Every segment must be distinguishable by observable behavior and stated language. Speculation must be explicitly flagged as "HYPOTHESIS — insufficient VOC evidence."

You will produce **3-5 distinct buyer segments**, not a single monolithic avatar. Each segment represents a meaningfully different buyer whose pain hierarchy, decision process, and messaging receptivity differ enough that segment-specific marketing would outperform generic marketing.

---

## Inputs (Context)

- Business idea / niche: {{BUSINESS_CONTEXT}}
- Structured context JSON: {{BUSINESS_CONTEXT_JSON}}
- Category / niche label: {{CATEGORY_NICHE}}
- Deep research summary (bounded): {{STEP4_SUMMARY}}
- Deep research content (full): {{STEP4_CONTENT}}
- Ads context (if any): {{ADS_CONTEXT}}

---

## Phase 1: Segment Discovery (First Principles)

Before building any profiles, decompose the research data to identify natural clusters.

**Step 1: Extract all distinct buyer signals from the research.** Look for:
- Clusters of people with DIFFERENT primary pain points
- Clusters with DIFFERENT life situations or trigger events
- Clusters with DIFFERENT levels of sophistication / prior solution experience
- Clusters with DIFFERENT trust orientations (who they defer to, who they distrust)
- Clusters with DIFFERENT identity language ("I'm a..." / "I'm not a...")

**Step 2: Apply the Differentiation Test.**
For each candidate segment pair, answer: "If you showed an ad designed for Segment A to Segment B, would it meaningfully UNDERPERFORM vs. a segment-specific ad?"
- If YES → these are distinct segments. Keep them separate.
- If NO → these are NOT meaningfully different. Merge them.

**Step 3: Name and bound each segment.**
- 3 segments minimum, 5 maximum
- Each segment needs a descriptive, memorable name
- Each segment needs a 1-sentence positioning: "This is the person who [core behavior] because [core motivation]"

---

## Phase 2: Segment Profiles

For EACH segment, produce the following sections. Every claim must reference specific VOC evidence (quote, source, or pattern from the research).

### A. Segment Identity

```
Segment Name: [descriptive name]
Positioning: "This is the person who [core behavior] because [core motivation]"
Estimated Prevalence: [% of total addressable market — Fermi estimation with reasoning]
Key Differentiator: [what makes this segment DIFFERENT from the others in one sentence]
```

### B. Demographics

- Age range
- Gender distribution
- Geographic concentration
- Household income range (not "monthly revenue" — this is B2C)
- Discretionary spending on this problem area per month (estimated)
- Professional/life situation
- Price sensitivity signals (what do they consider "worth it" vs. "too expensive"?)

### C. Psychological Architecture (Behavioral Economics)

**Motivation Hierarchy** (rank order — what matters MOST to this segment):

Approach motivations (moving TOWARD):
1. [Most important desire] — VOC evidence: "[quote]"
2. [Second] — VOC evidence: "[quote]"
3. [Third] — VOC evidence: "[quote]"

Avoidance motivations (running FROM):
1. [Most intense fear] — VOC evidence: "[quote]"
2. [Second] — VOC evidence: "[quote]"
3. [Third] — VOC evidence: "[quote]"

**Self-Determination Profile:**
- Autonomy need: LOW (wants to be told what to do) / MODERATE (wants guidance with options) / HIGH (wants control, resents being directed)
  - Evidence: [VOC quote or pattern supporting this assessment]
- Competence need: LOW (wants simplicity, "just tell me what to take") / MODERATE (wants to understand basics) / HIGH (wants mastery, deep knowledge)
  - Evidence: [VOC quote or pattern]
- Relatedness need: LOW (independent, solo researcher) / MODERATE (values some community) / HIGH (needs belonging, group validation)
  - Evidence: [VOC quote or pattern]

**Loss Aversion Profile:**
- What would this person LOSE by NOT buying? (quantify where possible — money wasted on alternatives, health consequences, time lost)
- What would they LOSE by buying the WRONG thing? (money, trust, health, face)
- Which loss feels MORE threatening to them? This determines whether your copy leads with "here's what you gain" or "here's what you're losing."

**Anchoring Landscape:**
- What price/value anchors already exist in their mind?
  - Prior spend on this problem: [amount range]
  - What they consider "expensive" in this category: [amount]
  - What they consider "suspiciously cheap": [amount]
  - Reference point they compare against: [specific product/service + price]

### D. Decision-Making Profile

- **Information processing style:** System 1 dominant (emotional, fast, story-driven, persuaded by testimonials and narrative) OR System 2 dominant (analytical, slow, evidence-driven, persuaded by data and credentials)?
  - Evidence: [VOC pattern — do they ask for studies or for stories?]

- **Authority orientation:** Who do they trust?
  - Credentials & degrees
  - Community consensus ("if 1000 people on Reddit say it works...")
  - Personal experience ("I'll try it myself and see")
  - Data and studies
  - Evidence: [VOC pattern]

- **Risk tolerance:**
  - Early adopter (tries new things quickly, okay with uncertainty)
  - Mainstream (waits for social proof, follows the crowd)
  - Cautious late adopter (needs overwhelming evidence, strong guarantee)
  - Evidence: [VOC pattern]

- **Comparison behavior:**
  - Impulse (buys first thing that resonates)
  - Light comparison (checks 2-3 alternatives)
  - Deep researcher (reads every review, compares features, takes days/weeks)
  - Evidence: [VOC pattern]

- **Consultation pattern:**
  - Decides alone
  - Consults partner/family
  - Consults community (Facebook group, Reddit, forums)
  - Consults professional (doctor, herbalist, etc.)
  - Evidence: [VOC pattern]

### E. Purchase Triggers

Top 3 trigger events that initiate active search for this segment:
1. [Trigger event] — VOC evidence: "[quote]"
2. [Trigger event] — VOC evidence: "[quote]"
3. [Trigger event] — VOC evidence: "[quote]"

The threshold moment language (verbatim):
- "[exact quote capturing the 'I finally decided to...' moment]"
- "[second quote]"

### F. Emotional Journey Map (Segment-Specific)

Map the emotional journey THIS SPECIFIC SEGMENT goes through. Do not use generic stages — be precise about what happens emotionally at each step for THIS buyer:

| Stage | Emotional State | What Triggers Transition | Key Language |
|---|---|---|---|
| Pre-awareness | [What are they feeling BEFORE they recognize the problem?] | [What disrupts this state?] | "[verbatim language]" |
| Problem recognition | [What emotion arises when they realize they have a problem?] | [What makes them start seeking?] | "[verbatim language]" |
| Active search | [What emotion dominates during research?] | [What makes them evaluate a specific product?] | "[verbatim language]" |
| Evaluation | [What determines buy vs. abandon?] | [What tips them over the edge?] | "[verbatim language]" |
| Post-purchase | [What emotion do they need to feel to NOT refund?] | [What would cause buyer's remorse?] | "[verbatim language]" |

### G. Angle Affinity Map

For this segment, rate the likely resonance of different angle types:

| Angle Type | Affinity | Why | VOC Evidence |
|---|---|---|---|
| "Lost wisdom / nostalgia" | HIGH / MODERATE / LOW | [reasoning] | "[supporting quote]" |
| "Science-backed safety" | HIGH / MODERATE / LOW | [reasoning] | "[supporting quote]" |
| "Self-sufficiency / independence" | HIGH / MODERATE / LOW | [reasoning] | "[supporting quote]" |
| "Anti-establishment / corruption" | HIGH / MODERATE / LOW | [reasoning] | "[supporting quote]" |
| "Community / belonging" | HIGH / MODERATE / LOW | [reasoning] | "[supporting quote]" |
| "Simplicity / overwhelm relief" | HIGH / MODERATE / LOW | [reasoning] | "[supporting quote]" |
| "Transformation / identity shift" | HIGH / MODERATE / LOW | [reasoning] | "[supporting quote]" |

### H. Functional Quote Bank

For this segment, provide quotes organized by downstream function:

**Hook-worthy quotes** (3-5 statements that would stop scrolling if used verbatim in an ad):
- "[quote]" — Source: [source]
- "[quote]" — Source: [source]
- "[quote]" — Source: [source]

**Mechanism validation quotes** (3-5 statements about WHY solutions work or fail):
- "[quote]" — Source: [source]
- "[quote]" — Source: [source]
- "[quote]" — Source: [source]

**Objection-revealing quotes** (3-5 statements expressing purchase resistance):
- "[quote]" — Source: [source]
- "[quote]" — Source: [source]
- "[quote]" — Source: [source]

**Transformation-revealing quotes** (3-5 statements about life after solving the problem):
- "[quote]" — Source: [source]
- "[quote]" — Source: [source]
- "[quote]" — Source: [source]

---

## Phase 3: Cross-Segment Analysis

### Segment Comparison Matrix (Z-Score Normalized)

After producing all segment profiles, create a normalized comparison matrix. Rate each dimension on a 1-5 scale where 3 = average across all segments:

| Dimension | Segment A | Segment B | Segment C | Segment D |
|---|---|---|---|---|
| Price sensitivity | | | | |
| Risk tolerance | | | | |
| Information need (depth) | | | | |
| Community need | | | | |
| Authority deference | | | | |
| Urgency / pain intensity | | | | |
| Prior solution experience | | | | |
| Autonomy need | | | | |

This matrix lets downstream prompts instantly identify messaging differences between segments.

### Bottleneck Segment Identification (Systems Thinking)

Identify which ONE segment represents the highest-leverage opportunity. Evaluate using this formula:

**Segment Priority = Size x Pain Intensity x Willingness to Pay x Angle Availability x Inverse Competition**

USE YOUR CODE/CALCULATOR TOOL to compute this. Do NOT estimate mentally. For each segment:
- Size: estimated % of addressable market (1-5)
- Pain Intensity: how urgent is the problem? (1-5)
- Willingness to Pay: evidence of spending in this space (1-5)
- Angle Availability: how many untapped angles exist for this segment? (1-5)
- Inverse Competition: how LITTLE competition exists for this segment's attention? (1-5)

Multiply all five factors. The segment with the highest product is the PRIMARY SEGMENT.

State: "The PRIMARY SEGMENT is [name]. All downstream prompts should optimize for this segment first, then adapt for secondary segments."

---

## Phase 4: Safety Factor Audit (Engineering Safety Factors)

Before finalizing, answer these questions for EACH segment:

1. **Weakest evidence test:** What is the single weakest piece of evidence supporting this segment's existence? If you removed this evidence, would the segment still hold?

2. **Assumption exposure:** What assumption are you making about this segment that could be wrong? State it explicitly.

3. **10x data test:** If you had 10x more research data, would this segment likely:
   - SURVIVE (high confidence it's real)
   - SPLIT into sub-segments (it's actually 2+ groups collapsed together)
   - MERGE with another segment (it's not actually distinct)

4. **Contradictory evidence:** Is there any VOC evidence that CONTRADICTS this segment profile? If yes, note it and explain why you weighted other evidence more heavily.

If a segment fails the safety factor check (weak evidence, shaky assumptions, likely to merge), FLAG it as **PROVISIONAL** and note what additional data would confirm or disconfirm it.

---

## Output Format (Critical)

Return only:

```
<SUMMARY>
Bounded summary: number of segments identified, primary segment name and why, key cross-segment differentiation insight, any provisional segments flagged. Max 400 words.
</SUMMARY>
<CONTENT>
...full multi-segment analysis: Phase 1 discovery rationale, Phase 2 complete profiles for each segment (sections A-H), Phase 3 comparison matrix + bottleneck segment, Phase 4 safety audit...
</CONTENT>
```
