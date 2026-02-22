# Prompt Template: Promise Contract Extraction

## When to Use
After generating a headline that scores B tier or above. This is Step 4.5 in the Headline Engine — the bridge between headline generation and body copy writing.

## What Is a Promise Contract?
Every headline makes an implicit promise. The Promise Contract formalizes that promise into 4 testable fields so the body copy can be held accountable.

## Extraction Procedure

### Step 1: Identify the Loop Question
Read the headline and ask: **What question does this plant in the reader's mind?**

Common loop questions:
- **"What?"** — The headline names something specific the reader doesn't know yet
- **"How?"** — The headline implies a method, system, or process
- **"Why?"** — The headline challenges an assumption
- **"Where?"** — The headline implies a location, source, or reference
- **"Who?"** — The headline implies a person, authority, or group

Example:
- Headline: "The Most Dangerous Detail Missing From Nearly Every Herbal Guide"
- Loop question: **"What?"** (What is the dangerous detail?)

### Step 2: Define the Specific Promise
Write 1-2 sentences describing **exactly what the reader expects** after reading this headline.

Rules:
- Be specific — not "the reader will learn something useful" but "the reader will learn what specific detail is missing and why it matters"
- Include the mechanism if the headline implies one
- Match the awareness level — a Problem-Aware reader expects problem validation, not a product pitch

### Step 3: Write the Delivery Test
Create a **concrete, binary (pass/fail) test** that the body copy must satisfy.

Format: "The body must [specific action] within [word/section boundary]."

Examples:
- "The body must name the specific missing detail within the first 200 words."
- "The body must demonstrate at least one concrete structural difference between this product and typical alternatives within the first 400 words."
- "The body must provide at least 3 specific examples of the claimed benefit within the first 3 sections."

Rules:
- Must be testable by a scorer (not subjective)
- Must include a word count or section boundary
- Must reference concrete content (names, numbers, examples), not vague quality

### Step 4: Set Minimum Delivery Timing
Specify WHERE in the body the promise must:
1. **Begin resolving** — where the first signal of delivery appears
2. **Be substantially complete** — where the reader should feel the promise has been paid off

Format: "Begin in [section/position]. Substantially resolved by [section/position]."

## Output Schema

```json
{
  "loop_question": "What?",
  "specific_promise": "The reader will learn what specific detail is missing from most herbal guides and why its absence creates real risk.",
  "delivery_test": "The body must name the specific missing detail (dosing information) within the first 200 words and provide at least two concrete consequences of its absence.",
  "minimum_delivery": "Begin in Section 1 (headline/sub-head). Substantially resolved by Section 2 (problem crystallization)."
}
```

## Verification

After body copy is written, the Promise Contract is enforced by:
```bash
python3 03_scorers/headline_body_congruency.py body.md promise_contract.json
```

The PC2 test (Delivery Test Satisfied) is a **HARD GATE** worth 3 points. If it fails, the entire score fails regardless of other test results.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Promise too vague ("reader learns something") | Add specifics — WHAT do they learn? |
| Delivery test untestable ("body feels satisfying") | Make binary — does the body NAME X within Y words? |
| Timing too loose ("somewhere in the body") | Pin to sections or word counts |
| Promise doesn't match headline | Re-read the headline — what would a READER expect? |
| Over-promising (headline says "7 secrets", body has 4) | Delivery test must match the headline's number |
