# Upstream Integration — Connecting to the Offer Agent

**Purpose:** This document explains how to receive and load the awareness-angle-matrix produced by the upstream Offer Agent. If no Offer Agent is available, it also explains how to generate the matrix standalone.

---

## What the Offer Agent Produces

The Offer Agent produces an `awareness-angle-matrix.md` file as part of its pipeline output (Step 2, Phase 7 — Market Calibration). This file contains per-angle, per-awareness-level framing guidance with 4 fields at each level:

| Field | Description |
|-------|-------------|
| `frame` | 1-2 sentence description of how the angle is positioned at this awareness level |
| `headline_direction` | Structural headline pattern (not a finished headline) |
| `entry_emotion` | The emotion the reader arrives with — what the opening copy hooks into |
| `exit_belief` | The belief the reader must hold when they finish the page |

Plus:
- `constant_elements` — what stays the same across all awareness levels (UMP, UMS, core promise)
- `variable_elements` — what shifts per level (proof type, headline pattern, CTA directness)
- `product_name_first_appears` — earliest level where the product is named

---

## Where to Place It

Store the file at:

```
01_governance/shared_context/awareness-angle-matrix.md
```

This makes it a **Tier 1 shared context file**, loaded by EVERY workflow alongside:

- `audience-product.md`
- `brand-voice.md`
- `compliance.md`
- `mental-models.md`

---

## How It Loads

When the system receives a task like:

```json
{
  "angle": "dosage",
  "awareness_level": "problem_aware",
  "page_type": "advertorial"
}
```

The workflow loads:

1. **Section 5 rules** for `problem_aware` (generic per-level construction rules)
2. **awareness-angle-matrix** → `dosage.awareness_framing.problem_aware` (angle-specific framing at this level)
3. **audience-product.md** (who the reader is, what the product is)
4. **Page-type constraints** for `advertorial`

This gives the agent both the GENERIC awareness-level rules (from Section 5) and the SPECIFIC angle framing (from the matrix) for the exact combination requested.

---

## If No Offer Agent Is Available

You can generate the awareness-angle-matrix standalone using the prompt template at:

```
04_prompt_templates/awareness_angle_matrix.md
```

To generate manually:

1. Load `01_governance/shared_context/audience-product.md` (filled in for your brand)
2. Load `01_governance/sections/Section 5 - Awareness-Level Routing Logic.md`
3. Define your angle (name, definition, VOC data)
4. Follow the prompt template to produce the `awareness_framing` object for all 5 levels
5. Save the output as `01_governance/shared_context/awareness-angle-matrix.md`

The system works identically whether the matrix comes from an upstream Offer Agent or is generated standalone.

---

## Multiple Angles

The Offer Agent processes one angle at a time. If you have multiple angles, you will receive one matrix per angle. You can either:

- **Append** all angle matrices into a single `awareness-angle-matrix.md` file (the system looks up by `angle_name`)
- **Store separately** as `awareness-angle-matrix-{angle_name}.md` and load the relevant one per task

The first approach (single file, multiple angles) is recommended for simplicity.
