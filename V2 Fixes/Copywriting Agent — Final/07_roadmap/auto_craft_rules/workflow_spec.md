# Workflow: Auto-Generate Sentence-Level Craft Rules (Subsection B)

## Purpose
This workflow produces a complete, ready-to-use Sentence-Level Craft Rules document for any product/brand using web research + existing foundational docs. No human editing required.

## Prerequisites (RAG inputs)
Before running this workflow, the following foundational docs must exist:
1. **Avatar Brief** -- demographics, pain points, emotional drivers, psychographic profile
2. **Offer Brief** -- product description, pricing, positioning, awareness level, belief chains
3. **Competitor Research** -- who the competitors are, how they position, their copy patterns

## The 5-Step Agent Prompt Chain

---

### STEP 1: Category Readability & Conversion Research
**Type:** Web research
**Dependencies:** Avatar Brief (for audience demographics)

```
PROMPT:

You are a conversion rate optimization researcher. Research the
following for the category: [PRODUCT CATEGORY] targeting
[AUDIENCE DEMOGRAPHICS from Avatar Brief].

1. What is the optimal readability level (Flesch-Kincaid grade,
   Flesch Reading Ease, Gunning Fog) for this category's landing
   pages? Find data from Unbounce, Portent, CXL, PMC studies,
   or similar CRO research. Get SPECIFIC numbers, not general
   advice.

2. What is the optimal sentence length range? Average and maximum.

3. What is the optimal paragraph length for:
   - Sales pages
   - Advertorial/presell pages
   - Emails

4. What is the audience's reading behavior? (Mobile vs desktop
   split, scanning patterns, attention span data)

5. Does long-form or short-form copy convert better for this
   category at this price point? Under what conditions?

Return specific data points with sources. Prefer studies with
large sample sizes over single case studies. Note confidence
level for each finding.
```

---

### STEP 2: Specificity & Trust Pattern Research
**Type:** Web research
**Dependencies:** Offer Brief (for product positioning), Competitor Research (for market sophistication level)

```
PROMPT:

You are a direct response copywriting researcher specializing in
[PRODUCT CATEGORY]. The market sophistication level is
[HIGH/MEDIUM/LOW -- derive from Competitor Research].

Research:

1. Does specific copy ("reduces cortisol by 31%") outperform
   vague copy ("helps with stress") in this category? Find
   split-test evidence, practitioner consensus, or case studies.

2. How do high-converting "honest brands" in this category
   handle specificity while staying compliant? Analyze 3-5
   trust-first brands. What sentence patterns do they use?
   Extract actual copy examples.

3. What are the compliance constraints for claims in this
   category? (FDA structure/function vs disease claims, FTC
   substantiation requirements, platform-specific rules). How
   do top copywriters make compliant claims feel as compelling
   as non-compliant ones?

4. What words/phrases DESTROY trust in this audience vs. BUILD
   trust? Find practitioner data or A/B test evidence on:
   - Words that trigger skepticism
   - Words that build credibility
   - The hedging spectrum ("may help" vs "helps" vs "will help")

5. What is the Eugene Schwartz market sophistication stage for
   this category? What does that imply for copy strategy?

Return raw findings with sources. Include specific copy examples.
```

---

### STEP 3: Bullet & Fascination Research
**Type:** Web research
**Dependencies:** None (general DR knowledge)

```
PROMPT:

You are a direct response copywriting researcher. Research bullet
copy (fascination) mechanics:

1. What are the established bullet/fascination formulas from top
   DR practitioners? (Mel Martin, Bencivenga, Stefan Georgi,
   Clayton Makepeace, Copy Hackers). Document each formula with
   examples.

2. Do traditional curiosity-heavy fascination bullets work for
   trust-sensitive, anti-hype audiences? Or does a different
   style perform better? Find practitioner insights or test data.

3. What makes a bullet feel manipulative vs. genuinely
   compelling to educated audiences?

4. What is the optimal number of bullets per context (offer
   stack, email, bonus description)?

5. How should blind bullets (withholding) be balanced with open
   bullets (giving away value) for trust-sensitive audiences?

Return raw findings with sources and specific examples.
```

---

### STEP 4: Transition & Retention Research
**Type:** Web research
**Dependencies:** None (general CRO knowledge)

```
PROMPT:

Research transition and retention techniques for long-form
health/wellness copy:

1. What specific techniques prevent reader drop-off in long-form
   pages? Rank by evidence strength. (Crossheads, bucket
   brigades, open loops, pattern interrupts, sticky CTAs, etc.)

2. What CAUSES drop-off? What should be avoided?

3. What is the optimal frequency for:
   - Crossheads (sub-headlines)
   - Bucket brigades
   - Format shifts (bold, callouts, tables)
   - Open loops

4. For trust-sensitive audiences, which pattern interrupts
   maintain trust vs. which feel manipulative?

5. What does the Zeigarnik Effect research say about open loops
   in marketing copy? How to use it ethically?

Return raw findings with sources.
```

---

### STEP 5: Synthesis Into Final Rules Document
**Type:** RAG synthesis (uses outputs from Steps 1-4 + all foundational docs)
**Dependencies:** All previous steps + Avatar Brief + Offer Brief + Competitor Research

```
PROMPT:

You are a senior direct response copywriter creating the
definitive sentence-level craft rules for a copywriting agent.
You have the following inputs:

[INSERT: Avatar Brief]
[INSERT: Offer Brief]
[INSERT: Competitor Research summary]
[INSERT: Step 1 output (readability data)]
[INSERT: Step 2 output (specificity & trust data)]
[INSERT: Step 3 output (bullet mechanics data)]
[INSERT: Step 4 output (transition & retention data)]

Create a complete "Sentence-Level Craft Rules" document with
these sections:

1. READABILITY STANDARD
   - Non-negotiable readability targets (use the specific data
     from Step 1)
   - Sentence length rules with targets per type (punch/
     workhorse/builder)
   - Word choice hierarchy specific to this audience

2. SPECIFICITY RULES
   - The specificity hierarchy (5 levels, most specific to least)
   - The "Only This Product" test (specific to this product)
   - Compliant specificity patterns (how to be specific within
     regulatory constraints -- use Step 2 data)
   - Include a reframe table: [What you want to say] ->
     [Compliant + specific version] -> [Why it works]

3. SENTENCE RHYTHM AND CADENCE
   - The three sentence types with length ranges and usage rules
   - A worked example showing good rhythm for this brand voice
   - Paragraph length rules per context
   - The end-of-sentence rule
   - One idea per sentence rule

4. BULLET MECHANICS
   - The bullet formula specific to this brand (adapted from
     Step 3 research to match brand positioning)
   - 4 bullet styles ranked by brand fit (adapt traditional
     formulas for this audience's trust sensitivity)
   - Bullet anti-patterns (what never to do)
   - Quantity and placement rules per context
   - Diversity rule

5. TRANSITION CRAFT
   - Forward momentum rule
   - 3 transition techniques ranked by brand fit
   - Approved and non-approved bucket brigade phrases
   - Open loop rules with payoff requirement
   - Transition anti-patterns

6. PATTERN INTERRUPTS AND RETENTION DEVICES
   - Approved devices with frequency guidelines
   - Devices to avoid (specific to brand positioning)
   - The payoff rule

7. SELF-EVALUATION CHECKLIST
   - A structured checklist the agent runs after every copy
     block (readability, specificity, rhythm, bullets,
     transitions, retention -- all pass/fail questions)

8. EVIDENCE BASE
   - List every research finding and source that informed
     these rules

RULES FOR WRITING THIS DOCUMENT:
- Every rule must be specific enough to produce a clear yes/no
  when checked
- Every rule must be opinionated -- not "consider varying
  sentence length" but "sentences over 25 words are never
  acceptable"
- Every rule must be grounded in the research data -- cite the
  evidence that supports it
- Calibrate everything to this specific brand positioning,
  audience, and market sophistication level
- Include worked examples using this product/brand wherever
  possible
- The total document should be 2,500-3,500 words
- Write as operating rules, not as advice or suggestions
```

---

## Output
The result of Step 5 is a complete, ready-to-use Subsection B document that goes directly into the agent's RAG as a persistent reference.

## Replication Notes
- This workflow runs for any product/brand by changing the inputs (Avatar Brief, Offer Brief, Competitor Research)
- Steps 1-4 (web research) take ~15-30 minutes each for an agent with web access
- Step 5 (synthesis) takes ~5 minutes
- Total: approximately 1-2 hours of agent time, zero human time
- The quality of the output depends on the quality of the foundational docs -- especially the Avatar Brief (audience specificity) and Offer Brief (brand positioning clarity)
