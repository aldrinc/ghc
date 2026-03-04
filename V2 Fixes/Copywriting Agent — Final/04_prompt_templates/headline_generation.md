# Prompt Template: Headline Generation

## When to Use
When generating headlines for any page type (listicle, advertorial, sales page, meta ad, email, etc.) at any awareness level.

## Required Inputs (Gather Before Starting)

| Input | Source | Required? |
|-------|--------|-----------|
| Awareness level | Task brief or S5 routing table | YES |
| Page type | Task brief | YES |
| Angle | Task brief or angle engine | YES |
| Beliefs to target | Task brief (B1-B8) | YES |
| Upstream headline | Previous page in funnel (if any) | If applicable |
| VOC data | Research artifacts or customer interviews | Strongly recommended |

## Context Loading (Step 1)

Load these documents in this order:

```
1. 01_governance/shared_context/audience-product.md    → WHO is the reader, WHAT is the product
2. 01_governance/shared_context/brand-voice.md         → Banned words, voice rules, emotional register
3. 01_governance/sections/Section 5 - Awareness-Level Routing Logic.md
   → Section 5.2: Per-level copy construction rules for confirmed awareness level
4. 02_engines/headline_engine/WORKFLOW.md
   → Section 4: Page-type calibration for confirmed page type
   → Section 3: Archetype table filtered to awareness level + page type
5. 02_engines/headline_engine/reference/dr-headline-engine.md
   → Formula library filtered to matching archetypes
```

## Working Memory Template

Extract and hold these before writing:

```
WORKING_LEVEL: {awareness_level}
PAGE_TYPE: {page_type}
ANGLE: {angle}
BELIEFS_TO_TARGET: {B1-B8 subset}

FROM S5:
  - Headline formula: {formula description}
  - Lead strategy: {lead approach}
  - Agitation ceiling: {level 1-5}
  - What to avoid: {constraints}

FROM WORKFLOW.MD SECTION 4:
  - Word count: {range}
  - Tone: {tone description}
  - Primary Laws: {which of the 7 Laws to emphasize}
  - Best archetypes: {archetype list}

FROM VOC DATA:
  - Key phrases: {reader's own words}
  - Private behaviors: {what she does when no one is watching}
  - Identity language: {how she describes herself}
  - Emotional confessions: {what she admits in private}
```

## Execution Steps

### Step 2: Select Archetypes
Choose 3-5 archetypes from the filtered table. Prioritize archetypes that:
- Match the awareness level
- Fit the page type
- Can carry the target beliefs
- Have formula support in the reference library

### Step 3: Generate Headlines
For each archetype, generate 2-3 headlines using the formulas. Apply:
- **Law 1 (Open Loop):** Create a curiosity gap the reader must click to close
- **Law 2 (Emotional Trigger):** Connect to a real emotion from VOC data
- **Law 3 (Unique Mechanism):** Tease the mechanism without revealing it
- **Law 4 (Specificity):** Use concrete numbers, names, or details
- **Law 5 (Identity):** Mirror how the reader sees herself
- **Law 6 (Credibility):** Include a credibility signal
- **Law 7 (Pattern Interrupt):** Break the reader's scroll pattern

### Step 4: Score Headlines
Run each headline through `03_scorers/headline_scorer_v2.py`. Discard any that:
- Score below B tier (< 28/44)
- Fail any hard gate (BC1, BC2, BC3)
- Contain banned words from brand-voice.md

### Step 4.5: Extract Promise Contract
For each headline scoring B tier or above, extract a Promise Contract:

```json
{
  "loop_question": "The question the headline plants in the reader's mind",
  "specific_promise": "What the reader expects to learn/discover/receive",
  "delivery_test": "Concrete pass/fail test the body must satisfy",
  "minimum_delivery": "Where in the body the promise must begin + resolve"
}
```

Save as `{headline_slug}_promise_contract.json`.

### Step 5: Select Winners
Rank headlines by:
1. Scorer tier (S > A > B)
2. Promise Contract deliverability (can the body actually pay this off?)
3. Message match to upstream headline (if applicable)
4. Belief chain coverage across the batch

## Output Format
Use the schema at `05_schemas/headline_output.json` for structured output.

## Verification
After body copy is written, run `03_scorers/headline_body_congruency.py` to verify the Promise Contract was fulfilled. Target: 75%+ (14.25/19).
