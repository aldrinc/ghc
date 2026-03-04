# Prompt: Generate Awareness-Level Angle Framing Matrix

## Context

The copywriting agent already has:
- **Section 5 (Awareness-Level Routing Logic)** — tells it HOW to write at each awareness level (lead strategy, headline formula, section emphasis, proof approach, CTA approach, word count, agitation ceiling)
- **audience-product.md** — tells it WHO the reader is and WHAT the product is
- **brand-voice.md + compliance.md** — tells it the guardrails

What the copywriting agent does NOT have: **how each angle changes its framing across awareness levels.**

Section 5 says "at Problem-Aware, the headline articulates the problem better than the reader can." But it doesn't say what that looks like for the DOSAGE angle vs. the DRUG INTERACTION angle vs. the AI SLOP angle. The angle engine needs to produce this mapping.

## What to Produce

For every angle the angle engine / VOC synthesizer outputs, add an `awareness_framing` object that contains the angle's framing at each of the 5 awareness levels.

### Required Fields Per Angle Per Awareness Level

```
angle_name: "dosage"
awareness_framing:
  unaware:
    frame: [1-2 sentence description of how this angle is framed for an unaware reader]
    headline_direction: [What the headline sounds like at this level — not a finished headline, but the structural direction]
    entry_emotion: [The emotion the reader feels when they arrive — what you're hooking into]
    exit_belief: [What the reader must believe when they leave this page]

  problem_aware:
    frame: [1-2 sentence description]
    headline_direction: [structural direction]
    entry_emotion: [emotion you're hooking into]
    exit_belief: [belief shift]

  solution_aware:
    frame: [1-2 sentence description]
    headline_direction: [structural direction]
    entry_emotion: [emotion you're hooking into]
    exit_belief: [belief shift]

  product_aware:
    frame: [1-2 sentence description]
    headline_direction: [structural direction]
    entry_emotion: [emotion you're hooking into]
    exit_belief: [belief shift]

  most_aware:
    frame: [1-2 sentence description]
    headline_direction: [structural direction]
    entry_emotion: [emotion you're hooking into]
    exit_belief: [belief shift]
```

### Example (for the "dosage" angle)

```
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
```

## How the Copywriting Agent Uses This

When the copywriting agent receives a task like:
```
angle: "dosage"
awareness_level: "problem_aware"
page_type: "advertorial"
```

It loads:
1. **Section 5.2 → Problem-Aware rules** (lead strategy, headline formula, proof approach, etc.)
2. **This file → dosage.awareness_framing.problem_aware** (frame, headline_direction, entry_emotion, exit_belief)
3. **audience-product.md** (who the reader is, product details)
4. **Presales and Sales Page General Constraints** (page-type specs)

And now it has everything needed to write an awareness-matched, angle-specific headline and page.

## Instructions for the Offer Agent / Angle Engine

Produce this `awareness_framing` object for EVERY angle that the VOC synthesizer or angle engine outputs. Store it alongside the angle definition so the copywriting agent can look it up by `angle_name` + `awareness_level`.

The output file should be named `awareness-angle-matrix.md` and stored in the shared directory alongside `audience-product.md`, `brand-voice.md`, and `compliance.md`.
