# Downstream Integration Guide — Offer Agent

**Purpose:** This document defines the data contract between the Offer Agent and any downstream consumer (e.g., a Copywriting Agent). It specifies what the Offer Agent produces, the exact schema, and how the downstream system should load and use it.

---

## What the Offer Agent Produces for Downstream

The Offer Agent produces two outputs consumed by downstream systems:

1. **Final Offer Document** (markdown) — the complete offer architecture (value stack, proof strategy, belief cascade, naming, pricing, guarantee, objections). Downstream agents use this as a RAG reference file for writing copy.

2. **Awareness-Angle-Matrix** (markdown + JSON) — per-angle, per-awareness-level framing guidance. This tells the downstream agent how to frame copy at each awareness level for the specific angle the Offer Agent processed.

---

## The Awareness-Angle-Matrix Contract

### When It's Produced

Step 2 (Market Calibration), Phase 7. This is the last phase of Step 2, after all awareness-level calibration and binding constraints are established.

### Why It Exists

Downstream copywriting systems typically have generic awareness-level rules (e.g., "at Problem-Aware, the headline articulates the problem better than the reader can"). But those rules don't specify how a SPECIFIC ANGLE changes its framing across levels. The dosage angle at Problem-Aware looks completely different from the dosage angle at Most-Aware.

The awareness-angle-matrix bridges this gap — it provides angle-specific framing guidance at every awareness level.

### JSON Schema

```yaml
angle_name: "{angle_name}"
awareness_framing:

  unaware:
    frame: "{1-2 sentences: how this angle is framed for someone who doesn't know they have this problem}"
    headline_direction: "{structural headline pattern — not a finished headline}"
    entry_emotion: "{the emotion the reader feels when they arrive}"
    exit_belief: "{what the reader must believe when they leave this page}"

  problem_aware:
    frame: "{1-2 sentences}"
    headline_direction: "{structural direction}"
    entry_emotion: "{emotion}"
    exit_belief: "{belief shift}"

  solution_aware:
    frame: "{1-2 sentences}"
    headline_direction: "{structural direction}"
    entry_emotion: "{emotion}"
    exit_belief: "{belief shift}"

  product_aware:
    frame: "{1-2 sentences}"
    headline_direction: "{structural direction}"
    entry_emotion: "{emotion}"
    exit_belief: "{belief shift}"

  most_aware:
    frame: "{1-2 sentences}"
    headline_direction: "{structural direction}"
    entry_emotion: "{emotion}"
    exit_belief: "{belief shift}"

constant_elements:
  - "{what stays the same across all awareness levels — e.g., UMP/UMS, core promise, angle definition}"

variable_elements:
  - "{what changes — e.g., proof type, headline pattern, CTA directness, agitation ceiling}"

product_name_first_appears: "{which awareness level — typically solution_aware or product_aware}"
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `frame` | string | 1-2 sentence description of how the angle is positioned at this awareness level. Governs the entire page's framing strategy. |
| `headline_direction` | string | Structural pattern for the headline — NOT a finished headline. Describes the type (story, problem-crystallization, differentiation, objection-resolution, or offer-forward). |
| `entry_emotion` | string | The dominant emotion the reader arrives with at this awareness level. The opening copy hooks into this emotion. |
| `exit_belief` | string | The belief the reader must hold when they finish this page. This is the minimum job-to-be-done for the page. |
| `constant_elements` | list | Elements that remain identical across all 5 awareness levels (UMP, UMS, core promise, angle definition). |
| `variable_elements` | list | Elements that shift per level (proof type, headline pattern, CTA directness, agitation ceiling, product name timing). |
| `product_name_first_appears` | string | The earliest awareness level where the product is named explicitly. Typically solution_aware or product_aware. |

### Worked Example — Dosage Angle

```yaml
angle_name: "dosage"
awareness_framing:

  unaware:
    frame: "Story-led. A mom describes giving her family herbs for years without ever knowing if the amounts were right. The word 'dosage' never appears — it's shown through a specific moment of doubt."
    headline_direction: "Identity/story — names a feeling or a moment, not a problem. 'She made her kids chamomile tea every night for three years before she thought to ask one question.'"
    entry_emotion: "Comfortable routine — she doesn't know she has a problem yet"
    exit_belief: "'Maybe I should check if I'm doing this right.'"

  problem_aware:
    frame: "Educational. Names the problem directly: most herb guides don't include dosing amounts, and the ones that do contradict each other. Explains WHY this is a problem (herbs aren't one-size-fits-all, kids need different amounts, some herbs interact with drugs)."
    headline_direction: "Problem-crystallization — articulates the problem better than the reader can. 'Most herb guides skip dosing amounts. Here is why that is more dangerous than you think.'"
    entry_emotion: "Vague anxiety — she knows something is off but can't name it"
    exit_belief: "'I need a reference that includes real amounts, not just herb names.'"

  solution_aware:
    frame: "Differentiation. She already knows herb references exist. This angle shows that most references skip the one thing that matters — verified dose amounts with kid/pregnancy flags. The mechanism is the safety-first framework."
    headline_direction: "Differentiation-first — draws a line between this product and the category norm. 'You have seen herb guides. This is the first one that tells you exactly how much.'"
    entry_emotion: "Frustration with existing options — she's tried guides that let her down"
    exit_belief: "'This specific reference solves the dosing gap that other guides leave open.'"

  product_aware:
    frame: "Objection-resolution. She knows about the Handbook. The dosage angle here addresses her remaining doubt: 'Is the dosing info actually specific enough to use, or is it just general ranges like everything else?'"
    headline_direction: "Objection-resolution — addresses the hesitation. 'You have seen the Handbook. Here is what the dose charts actually look like inside.'"
    entry_emotion: "Skeptical interest — she wants it to be real but has been burned before"
    exit_belief: "'The dosing info in this book is specific enough to actually use tonight.'"

  most_aware:
    frame: "Offer-forward. She's ready. The dosage angle just reinforces the core value prop in the offer line: 'Verified dose amounts for 50+ herbs. $49.'"
    headline_direction: "Offer-forward — product name + key benefit + CTA. 'The Honest Herbalist Handbook — real doses, real safety flags. Get it now.'"
    entry_emotion: "Ready to buy — just needs the button"
    exit_belief: "'I'm buying this now.'"

constant_elements:
  - "UMP: The only herbal reference with verified dose amounts for 50+ herbs including child/pregnancy flags"
  - "UMS: Safety-first dosing framework (clinical ranges, not folk wisdom)"
  - "Core promise: Know exactly how much of each herb to use"
  - "Angle definition: The dosage gap in herbal references"

variable_elements:
  - "Proof type: Story (unaware) → Statistics (problem) → Comparison (solution) → Inside look (product) → Social proof count (most)"
  - "Headline pattern: Story → Problem → Differentiation → Objection → Offer"
  - "CTA directness: None (unaware) → Soft editorial (problem/solution) → Direct (product/most)"
  - "Agitation ceiling: Low (unaware) → Medium (problem) → Low (solution+)"
  - "Product name timing: Not mentioned (unaware/problem) → Named (solution+)"

product_name_first_appears: "solution_aware"
```

---

## How a Downstream Consumer Loads This

The awareness-angle-matrix should be stored as a **Tier 1 shared context file** — loaded for EVERY workflow, alongside:

- `audience-product.md` (who the reader is, what the product is)
- `brand-voice.md` (voice rules, banned words)
- `compliance.md` (regulatory constraints)
- `mental-models.md` (self-evaluation framework)

### Lookup Pattern

When a downstream agent receives a task:

```json
{
  "angle": "dosage",
  "awareness_level": "problem_aware",
  "page_type": "advertorial"
}
```

It loads:
1. Generic awareness-level rules for `problem_aware` (from its own routing logic)
2. Angle-specific framing from `awareness-angle-matrix.md` → `dosage.awareness_framing.problem_aware`
3. Audience/product context from `audience-product.md`
4. Page-type constraints for `advertorial`

This gives the agent both the GENERIC rules and the SPECIFIC framing for the exact angle x awareness combination.

---

## File Naming and Storage

| File | Name | Location |
|------|------|----------|
| Matrix output | `awareness-angle-matrix.md` | Downstream system's shared context directory |
| Generation prompt | `awareness-angle-matrix-prompt.md` | This directory (`downstream-integration/`) |
| Technical spec | `awareness-angle-matrix-spec.md` | `docs/` directory |

---

## What Happens If No Downstream Consumer Exists

The awareness-angle-matrix is still produced by the Offer Agent as part of its standard output assembly. It is stored alongside the final offer document. If no downstream copywriting system is connected, the matrix serves as a reference document for human copywriters who need to understand how the angle should be framed at different awareness levels.

---

## Single-Angle Pipeline Note

The Offer Agent runs for ONE angle at a time. Each run produces one awareness-angle-matrix for one angle. To build matrices for multiple angles, run the pipeline multiple times. Each run's matrix is self-contained and can be appended to a multi-angle matrix file or stored separately.
