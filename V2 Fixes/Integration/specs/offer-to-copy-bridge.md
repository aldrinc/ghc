# Offer-to-Copy Bridge

**Purpose:** Transforms the Offer Agent's output into the Copywriting Agent's shared context files, ensuring copy execution is grounded in the offer's strategic decisions.

**When to use:** After Stage 3 (Offer Architecture) completes and before Stage 4 (Copy Execution) begins.

---

## Files to Populate

| File | Location | Source |
|------|----------|--------|
| `audience-product.md` | `Copywriting Agent — Final/01_governance/shared_context/` | Offer Agent Steps 1, 3, 4 + Agent 2 VOC |
| `awareness-angle-matrix.md` | `Copywriting Agent — Final/01_governance/shared_context/` | Offer Agent Step 2 Phase 7 |
| `brand-voice.md` | `Copywriting Agent — Final/01_governance/shared_context/` | Operator configures |
| `compliance.md` | `Copywriting Agent — Final/01_governance/shared_context/` | All upstream compliance data |

---

## audience-product.md Population Guide

Reference template: `Copywriting Agent — Final/01_governance/shared_context/audience-product.md`

### Target Audience Summary

| Placeholder | Source | Offer Agent Location |
|------------|--------|---------------------|
| `{BRAND_NAME}` | Seed input | `product_brief.name` |
| `{TARGET_AGE_RANGE}` | Offer Agent Step 1 | Avatar Brief output → Demographics section |
| `{EXTENDED_AGE_RANGE}` | Offer Agent Step 1 | Avatar Brief output → Demographics → extended range |
| `{GENDER_SKEW}` | Offer Agent Step 1 | Avatar Brief output → Demographics → gender split |
| `{PRIMARY_MARKETS}` | Seed or operator | `product_brief.target_regions` |
| `{BUDGET_RANGE}` | Offer Agent Step 1 or infer | Avatar Brief → spending behavior, or infer from product price |
| `{UPSELL_BUDGET_NOTE}` | Offer Agent Step 4 | If upsell/downsell exists, note budget ceiling |
| `{PROFESSIONAL_BACKGROUNDS}` | Offer Agent Step 1 | Avatar Brief → Psychographic/demographic section |
| `{PSYCHOGRAPHIC_IDENTITY_1-5}` | Offer Agent Step 1 | Avatar Brief → Identity markers / psychographic profiles. Use the role/identity language from the selected angle's WHO field. |
| `{EMOTIONAL_DRIVER_1-3}` | Offer Agent Step 1 | Avatar Brief → Emotional drivers. Align with selected angle's emotional valence. |
| `{DRIVER_1-3_EXPLANATION}` | Offer Agent Step 1 | Avatar Brief → explanations of each driver |
| `{KEY_MINDSET_DESCRIPTION}` | Offer Agent Step 1 | Avatar Brief → Worldview/mindset section. Should reflect the belief_shift.BEFORE state. |

### Pain Points

| Placeholder | Source | Offer Agent Location |
|------------|--------|---------------------|
| `{PAIN_POINT_1-3_TITLE}` | Offer Agent Step 1 + selected angle | Avatar Brief → Pain points, prioritized by the selected angle's PAIN dimension |
| `{PAIN_1-3_DETAIL_A-C}` | Agent 2 VOC corpus (filtered) | Top VOC items per pain. Use verbatim quotes or close paraphrases. |
| `{EMOTIONAL_FEAR_1-3}` | Offer Agent Step 1 | Avatar Brief → Fear hierarchy. Align with selected angle's Fear/Risk dimension. |

### Goals & Aspirations

| Placeholder | Source | Offer Agent Location |
|------------|--------|---------------------|
| `{SHORT_TERM_GOAL_1-3}` | Offer Agent Step 1 | Avatar Brief → Desired outcomes (immediate/tactical) |
| `{LONG_TERM_GOAL_1-3}` | Offer Agent Step 1 | Avatar Brief → Desired outcomes (identity-level/aspirational) |

### Product Summary

| Placeholder | Source | Offer Agent Location |
|------------|--------|---------------------|
| `{PRODUCT_NAME}` | Seed input | `product_brief.name` |
| `{PRICE_POINT}` | Offer Agent Step 4 | Final Offer Doc → pricing section (may differ from seed if offer construction adjusted it) |
| `{PRODUCT_FORMAT}` | Offer Agent Step 4 | Final Offer Doc → format (e.g., "digital guide," "supplement bottle," "course") |
| `{PRODUCT_POSITIONING}` | Offer Agent Step 2 | Market Calibration → positioning statement. This should reflect the selected angle's mechanism. |
| `{CORE_CONTENT_1-7}` | Offer Agent Step 4 | Final Offer Doc → value stack → core components (what the buyer gets) |
| `{BONUS_1-4_NAME}` | Offer Agent Step 4 | Final Offer Doc → bonus stack → names |
| `{BONUS_1-4_DESCRIPTION}` | Offer Agent Step 4 | Final Offer Doc → bonus stack → descriptions |
| `{GUARANTEE_TERMS}` | Offer Agent Step 4 | Final Offer Doc → guarantee section |

### Unique Mechanisms

| Placeholder | Source | Offer Agent Location |
|------------|--------|---------------------|
| `{UMP_TITLE}` | Offer Agent Step 3 | Selected UMP → title/name |
| `{UMP_DESCRIPTION}` | Offer Agent Step 3 | Selected UMP → description |
| `{UMS_TITLE}` | Offer Agent Step 3 | Selected UMS → title/name |
| `{UMS_COMPONENT_1-5}` | Offer Agent Step 3 | Selected UMS → component breakdown |

### Key Differentiators

| Placeholder | Source | Offer Agent Location |
|------------|--------|---------------------|
| `{KEY_DIFFERENTIATOR_SUMMARY}` | Offer Agent Step 2 | Market Calibration → differentiation analysis |
| `{DIFFERENTIATION_PILLARS}` | Offer Agent Step 2 | From "structural, specific, unexpected" framework |

### Belief Chain

| Placeholder | Source | Mapping Rule |
|------------|--------|-------------|
| `{BELIEF_1}` | Offer Agent Step 4 Phase 10 | Map cascade element: "The problem is real and getting worse" |
| `{BELIEF_2}` | Offer Agent Step 4 Phase 10 | Map cascade element: "The problem has a hidden root cause" (UMP) |
| `{BELIEF_3}` | Offer Agent Step 4 Phase 10 | Map cascade element: "A solution category addresses the root cause" |
| `{BELIEF_4}` | Offer Agent Step 4 Phase 10 | Map cascade element: "This product is the best version" (UMS) |
| `{BELIEF_5}` | Offer Agent Step 4 Phase 10 | Map cascade element: "The offer is fair and I should act now" |

See **Belief Architecture Mapping** section below for detailed rules.

### Awareness & Sophistication

| Placeholder | Source | Offer Agent Location |
|------------|--------|---------------------|
| `{CONSCIOUSNESS_LEVEL}` | Offer Agent Step 2 | Market Calibration output |
| `{AWARENESS_LEVEL}` | Offer Agent Step 2 | Market Calibration → primary awareness level |
| `{SOPHISTICATION_STAGE}` | Offer Agent Step 2 | Market Calibration → sophistication level (1-5) |

### Objections

| Placeholder | Source | Offer Agent Location |
|------------|--------|---------------------|
| `{OBJECTION_CATEGORY_1-6}` | Offer Agent Step 4 | Final Offer Doc → objection handling section. Categories typically include: Price, Trust, Effectiveness, Complexity, Risk, Timing. |
| `{OBJECTIONS_1-6}` | Offer Agent Step 4 | Specific objections per category |

### Audience Voice

| Placeholder | Source | Offer Agent Location |
|------------|--------|---------------------|
| `{VOC_QUOTE_1-6}` | Agent 2 VOC corpus (filtered) | Select the 6 most "headline-ready" quotes from the selected angle's cluster. Prioritize quotes where observation sheet has `headline_ready: Y`. These must be REAL quotes from the corpus — never invented. |

---

## awareness-angle-matrix.md

**Source:** Offer Agent Step 2, Phase 7 output

**Action:** Copy the complete awareness-angle-matrix output from the Offer Agent and save it directly as:

```
Copywriting Agent — Final/01_governance/shared_context/awareness-angle-matrix.md
```

This file contains per-awareness-level framing with: `frame`, `headline_direction`, `entry_emotion`, `exit_belief`, plus `constant_elements`, `variable_elements`, and `product_name_first_appears`.

No transformation needed — the Offer Agent produces this in the exact format the Copywriting Agent expects.

**Reference:** See `Copywriting Agent — Final/UPSTREAM-INTEGRATION.md` for full documentation.

---

## Belief Architecture Mapping

### Overview

The Offer Agent produces a **belief cascade** (Step 4, Phase 10) — the sequence of beliefs a buyer must hold to purchase. The Copywriting Agent uses **B1-B5** to structure which beliefs are advanced in which copy sections.

These are complementary frameworks:
- **Offer Agent belief cascade** = WHAT must be believed (strategic content)
- **Copywriting Agent B1-B5** = WHERE each belief is advanced (structural placement)

### Mapping Table

| Offer Agent Belief Cascade Element | Copy B# | Copy Section Where Advanced | What Copy Must Accomplish |
|-----------------------------------|---------|---------------------------|--------------------------|
| "The problem is real and getting worse" | B1 | Presell: Sections 1-2 | Validate the reader's pain, make it tangible and urgent |
| "The problem has a hidden root cause" (UMP) | B2 | Presell: Sections 2-3 | Introduce the Unique Mechanism of the Problem — reframe WHY the problem persists |
| "A solution exists that addresses the root cause" | B3 | Presell: Sections 3-4 | Bridge from UMP to solution territory without naming the product yet |
| "This specific product is the best version" (UMS) | B4 | Presell: Section 5 + Sales: Sections 1-4 | Introduce the product, explain UMS, demonstrate mechanism |
| "The offer is fair and I should act now" | B5 | Sales: Sections 5-12 | Value stack, social proof, guarantee, risk reversal, CTA |

### How to Apply

1. Read the Offer Agent's belief cascade output (Step 4, Phase 10)
2. Identify which cascade element maps to which B# per the table above
3. Use the Offer Agent's exact language for each belief — do not rephrase
4. If the cascade has more than 5 elements, combine the two most closely related beliefs into one B#
5. If the cascade has fewer than 5 elements, split the broadest belief into sub-beliefs
6. The copy team should reference both B# (structural) and the cascade (strategic) when writing

### Verification

After populating B1-B5, check:
- [ ] B1 corresponds to problem validation (presell opening)
- [ ] B2 introduces the UMP (reframes why the problem exists)
- [ ] B3 bridges to solutions (without naming the product)
- [ ] B4 introduces the product and UMS
- [ ] B5 closes with offer justification and CTA
- [ ] The belief sequence is PROGRESSIVE (each builds on the previous)
- [ ] No belief requires information the reader hasn't received yet

---

## Compliance Context Transfer

### Sources

Compile compliance data from all upstream systems:

1. **Agent 3 compliance block** — per-angle GREEN/YELLOW/RED counts, expressibility flags, platform notes
2. **Competitor Asset Analyzer** — `compliance_landscape` from `competitor_analysis.json`: overall distribution, per-competitor profiles, RED/YELLOW flag patterns
3. **Offer Agent** — any compliance flags raised during Steps 2-4

### Target File

If `Copywriting Agent — Final/01_governance/shared_context/compliance.md` exists, update it. If not, create it with:

```markdown
# Compliance Context

## Overall Risk Level
[GREEN / YELLOW / RED — from the selected angle's compliance assessment]

## RED Flag Patterns to Avoid
[List specific claim patterns that are RED-flagged across upstream systems.
Describe the pattern WITHOUT reproducing prohibited language.]

## YELLOW Flag Patterns (Use With Caution)
[List patterns that are borderline — acceptable with careful framing]

## Platform-Specific Notes
- **Meta:** [notes from Agent 3 + competitor analysis]
- **TikTok:** [notes]
- **YouTube:** [notes]
- **Google:** [notes]

## Prohibited Language
[Compile from all upstream compliance gates. Never use: treat, cure, diagnose,
or any disease-specific claim language identified as RED.]

## Approved Reframes
[For any borderline claims, list the compliant reframe suggested by Agent 3
or the Offer Agent. Format: "Instead of [RED pattern], use [GREEN reframe]"]
```

---

## Checklist

Before starting Stage 4 (Copy Execution), verify:

- [ ] `audience-product.md` — all {PLACEHOLDER} fields replaced with real data
- [ ] `audience-product.md` — VOC quotes are real (from Agent 2 corpus), not invented
- [ ] `audience-product.md` — B1-B5 beliefs are from the Offer Agent's cascade, not generic
- [ ] `awareness-angle-matrix.md` — placed from Offer Agent Step 2 output
- [ ] `brand-voice.md` — configured by operator (or use defaults)
- [ ] `compliance.md` — populated with upstream compliance data
- [ ] No {PLACEHOLDER} tags remain in any shared context file
- [ ] UMP and UMS match the Offer Agent's selected pair exactly
