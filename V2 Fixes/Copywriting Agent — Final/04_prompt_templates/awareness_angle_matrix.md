# Prompt Template: Awareness-Angle Matrix Generation

## When to Use
When you have a new angle (from VOC research, competitor analysis, or angle brainstorming) and need to define how that angle frames across all 5 awareness levels.

## Why This Matters
Section 5 tells the agent HOW to write at each awareness level (lead strategy, headline formula, etc.). But it doesn't tell the agent how a SPECIFIC ANGLE changes its framing across levels. The dosage angle at Problem-Aware looks completely different from the dosage angle at Most-Aware. This matrix provides that mapping.

## Required Inputs

| Input | Source |
|-------|--------|
| Angle name and definition | Angle engine or task brief |
| Section 5 awareness-level rules | 01_governance/sections/Section 5 |
| Audience-product context | 01_governance/shared_context/audience-product.md |
| VOC data for this angle | Research artifacts or customer interviews |

## Output Structure

For each angle, produce an `awareness_framing` object with entries for all 5 levels:

```yaml
angle_name: "{angle}"
awareness_framing:

  unaware:
    frame: "{1-2 sentences: how this angle is framed for someone who doesn't know they have this problem}"
    headline_direction: "{structural direction, not a finished headline}"
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
```

## Key Principles Per Level

| Level | Frame Strategy | Headline Direction | Entry Emotion |
|-------|---------------|-------------------|---------------|
| Unaware | Story-led. Show the problem through a moment, not a lecture. | Identity/story — names a feeling, not a problem | Comfortable routine |
| Problem-Aware | Educational. Name the problem directly and explain why it matters. | Problem-crystallization — articulate it better than the reader can | Vague anxiety |
| Solution-Aware | Differentiation. She knows solutions exist. Show why THIS one is structurally different. | Differentiation-first — draw a line between this and the category | Frustration with existing options |
| Product-Aware | Objection-resolution. She knows the product. Address remaining doubts. | Objection-resolution — address the hesitation directly | Skeptical interest |
| Most-Aware | Offer-forward. She's ready. Lead with the offer. | Offer-forward — product name + key benefit + CTA | Ready to buy |

## How the Copywriting Agent Uses This

When receiving a task like `angle: "dosage", awareness_level: "problem_aware", page_type: "advertorial"`, the agent loads:

1. **S5.2 → Problem-Aware rules** (generic per-level construction rules)
2. **This matrix → dosage.problem_aware** (angle-specific framing at this level)
3. **audience-product.md** (who + what)
4. **Page constraints** (page-type specs)

This gives the agent both the GENERIC rules (S5) and the SPECIFIC framing (this matrix) for the exact angle × awareness combination.

## Storage
Save the completed matrix as `awareness-angle-matrix.md` in the shared context folder alongside `audience-product.md`, `brand-voice.md`, and `compliance.md`.
