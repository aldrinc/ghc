# Prompt Template: Presell Advertorial Writing

## When to Use
When writing a presell advertorial (editorial-style page that builds beliefs B1-B4 before the reader hits the sales page).

## Required Inputs

| Input | Source | Required? |
|-------|--------|-----------|
| Winning headline | Headline engine output (scored B+ tier) | YES |
| Promise Contract JSON | Step 4.5 extraction | YES |
| Awareness level | Task brief (typically Problem-Aware for cold traffic) | YES |
| Page type | "Advertorial" / "Presell" | YES |
| Angle | Task brief | YES |
| Target beliefs | B1-B4 (presell belief chain) | YES |
| Traffic source | Cold (Meta/TikTok) or Warm (email/organic) | YES |

## Context Loading

```
1. 01_governance/shared_context/audience-product.md    → Product details, audience
2. 01_governance/shared_context/brand-voice.md         → Voice rules, banned words
3. 01_governance/shared_context/compliance.md          → Platform-specific compliance
4. 01_governance/sections/Section 2 - Page-Type Templates.md
   → Advertorial template (structure, word counts, section jobs)
5. 01_governance/sections/Section 9 - Section-Level Job Definitions.md
   → Per-section entry/exit beliefs, CHECK gates
6. 01_governance/sections/Subsection A - Structural Principles.md
   → Belief chain architecture (B1-B4 for presell)
7. 01_governance/sections/Subsection B - Sentence-Level Craft Rules.md
   → Craft rules (rhythm, transitions, readability)
8. 02_engines/promise_contract/PROMISE_CONTRACT_SYSTEM.md
   → How the contract governs body structure
9. Promise Contract JSON for the winning headline
```

## Advertorial Blueprint

### Structure (6 sections, 800-1,200 words)

| Section | Belief Job | Word Target | Key Rule |
|---------|------------|-------------|----------|
| 1. Hook/Lead | Capture + B1 seed | 80-120w | Must pass "would a magazine print this?" test |
| 2. Problem Crystallization | B1 (problem is real) + B2 (problem is urgent) | 150-200w | Name 3 concrete consequences the reader recognizes |
| 3. Failed Solutions | B2 reinforcement + B3 seed | 100-150w | Name what she's tried, why it didn't work |
| 4. Mechanism Reveal | B3 (solution category exists) | 150-200w | Name the mechanism without naming the product |
| 5. Proof + Bridge | B3 + B4 seed (this product delivers) | 150-200w | Social proof, specificity, credibility signals |
| 6. Transition CTA | B4 (I should look at this) | 50-80w | Editorial-style transition, NOT hard sell |

### Promise Contract Integration
- The Promise Contract's `delivery_test` must be satisfied within the body
- Check `minimum_delivery` for WHERE the promise must begin resolving
- The `loop_question` from the headline must be answered — don't leave it hanging

### Section-Level CHECKs (from S9)
After writing each section, verify:
- CHECK 1: Does this section advance the belief it's assigned?
- CHECK 2: Is the emotional arc progressing (not repeating)?
- CHECK 3: Does momentum build (no stalling)?
- CHECK 4: Is there redundancy with previous sections?
- CHECK 5: Is the Promise Contract being delivered on schedule?

## Writing Rules

### From Brand Voice
- No hype words (never, amazing, revolutionary, etc.)
- No disease claims
- Maintain editorial tone — reader should feel like she's reading an article, not an ad
- Use the reader's own language from VOC data

### From Compliance
- No specific health claims without qualification
- No before/after promises
- Platform-appropriate disclosures

### From Craft Rules (Subsection B)
- Paragraphs: 1-3 sentences max
- Sentence length: vary between 5-25 words
- No passive voice in the first or last sentence of any section
- Transitions: every paragraph must connect to the one before it

## Scoring

After writing, run:
```bash
python3 03_scorers/headline_body_congruency.py advertorial.md promise_contract.json
```

**Target:** 75%+ (14.25/19). PC2 hard gate must PASS.

## Output Format
- Markdown file with section headers
- Word doc (via python-docx) for Google Drive review
- Promise Contract JSON alongside for scorer verification
