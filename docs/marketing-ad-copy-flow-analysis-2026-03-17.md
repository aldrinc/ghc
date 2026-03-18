# Marketing Ad Copy Flow Analysis

Date: March 17, 2026

## Scope

This report explains how the current paid social ad copy and image generation flow works in the codebase, then analyzes the active campaign:

- Campaign ID: `62a95f2d-f67a-462f-8c5e-e850b1a1df60`
- Campaign name: `ang-A01--interaction-first-safety-checker--l1`
- Client: `The Honest Herbalist`
- Product: `The Honest Herbalist Handbook`
- Channels: `facebook`, `instagram`
- Asset brief types: `image`
- Campaign created at: March 11, 2026 15:20:38 UTC

This analysis is based on:

- Live campaign rows in the local Postgres dev database on `localhost:5433`
- Stored campaign artifacts, creative specs, and generated asset metadata
- Downloaded generated images and product-reference images from object storage
- The backend workflow and activity code that creates briefs, copy packs, swipe prompts, and Meta creative specs

## Executive Summary

The current system does not have one unified "ad copy flow" for Meta image ads.

It has two sibling branches:

1. A Meta copy branch that generates `metaPrimaryText`, `metaHeadline`, `metaDescription`, and CTA in an ad copy pack.
2. A swipe-adaptation image branch that generates a new image prompt from a competitor swipe reference and can invent separate on-image headline/body/CTA text.

Those two branches meet only at persistence time, when the generated asset keeps both:

- the rendered image prompt and image output in `asset.ai_metadata`
- the Meta copy pack in `asset.ai_metadata.swipeCopyPack`

Then Meta review setup creates `meta_creative_specs` from `swipeCopyPack`, not from the image prompt and not from the rendered image.

That means the pipeline is currently swipe-aware, but not copy-aware:

- it is strongly aware of the competitor swipe’s layout, typography zones, and design DNA
- it is not strongly constrained to keep the rendered image text aligned with the finalized Meta headline and primary text for the same asset

In this campaign, that is exactly what happened.

## What The Flow Actually Does

### 1. Strategy V2 launch creates campaign scaffolding

The upstream Strategy V2 launch flow creates:

- a campaign
- a strategy sheet artifact
- an experiment spec artifact
- an asset brief artifact
- workspace context docs for downstream generation

The asset brief is intentionally sparse. For this campaign, the initial brief only says:

- angle: `Interaction-First Safety Checker`
- hook: `Interaction-First Safety Checker framed for Contraindications-First Monographs`
- one Facebook image requirement
- one Instagram image requirement
- creative concept: `Interaction-First Safety Checker conversion creative`
- tone guidelines: `Clear`, `Specific`, `Evidence-led`
- visual guideline: `Keep hierarchy simple`

It does not contain:

- a finalized Meta headline
- finalized Meta primary text
- on-image headline/body/CTA
- detailed product-specific visual direction
- any requirement that the image echo the Meta headline verbatim

### 2. Asset generation creates an ad copy pack

When creative production starts, the system first creates an `ad_copy_pack` artifact for each image requirement.

This step uses attached strategy, offer, copy, and copy-context documents as source of truth and produces one copy pack per image requirement.

Important detail:

- the prompt explicitly says the swipe image-ad flow owns all on-image text generation
- the copy pack is responsible for Meta body/headline/description only

For this campaign, the `ad_copy_pack` artifact is:

- Artifact ID: `fdb8fb75-d0f5-4024-86e2-7c48cfdedc66`
- Created at: March 12, 2026 16:28:19 UTC

It contains 2 copy packs:

- `cp-fb-0-exp-A01-single_device`
- `cp-ig-1-exp-A01-single_device`

Example Facebook Meta copy from that artifact:

- Meta headline: `Check Herb–Drug Interactions Before You Mix`
- Meta primary text: long explanatory copy about missing herb-drug interaction coverage, contraindications-first entries, evidence-strength keys, and included inserts

This is the last point in the system where Meta copy is generated as a first-class, requirement-level object.

### 3. Creative generation plan explodes one brief into many swipe-derived executions

The system then creates a `creative_generation_plan` artifact that fans each image requirement out across the default swipe library.

For this campaign:

- Latest plan artifact examined: `16f0c786-317c-41e4-8d8b-90ceac4037b4`
- Plan item count: `60`

The fan-out logic is:

- 2 requirements in the brief
- multiplied by the curated default swipe set
- each plan item bound to one swipe source label and one copy-pack id

So a single vague brief becomes dozens of swipe-specific executions.

### 4. Swipe-image generation runs per plan item

Each image plan item calls `generate_swipe_image_ad_activity(...)`.

That activity does three distinct things:

1. Resolve the competitor swipe image.
2. Generate a swipe-specific copy pack with Gemini.
3. Generate a render prompt from the swipe prompt template plus the competitor image, then send that extracted prompt to the image renderer.

This is the critical break point.

The image prompt generation step does **not** take the already-generated Meta copy pack as a direct input.

Instead it uses:

- the generic swipe prompt template
- runtime inputs: brand and angle
- the competitor swipe image
- an optional product reference image
- Gemini File Search bundles containing brand/offer/strategy/copy/asset-brief docs

It does **not** include the `ad_copy_pack` artifact in the Gemini File Search bundles.

The `ad_copy_pack_id` is passed into the activity, but only for provenance and later metadata annotation. It is not used to constrain the generated image prompt text.

### 4A. Swipe copy is not generated from the finished creative

The sequencing here is easy to misunderstand, because the stored asset ends up containing both the rendered creative metadata and the swipe copy metadata.

In the actual code path, the swipe-specific copy pack is generated **before** the image-render prompt is sent to Gemini and before the final image is rendered.

That swipe copy generation step takes these direct inputs:

- the source swipe image or video itself
- the platform inferred from the channel
- the requirement angle
- the destination type
- the requirement metadata from the asset brief
- project docs from Gemini File Search
- an optional product reference image

It does **not** take these direct inputs:

- the final rendered image
- OCR or extracted text from the rendered image
- the final image prompt text
- the renderer output metadata

So the system is not doing "generate creative, inspect creative, then write congruent copy."

It is doing "use the same upstream context to independently generate:

- a swipe-specific copy pack
- a swipe-specific image prompt"

Those are sibling outputs, not parent/child outputs.

### 4B. What actually makes swipe copy somewhat aligned

There is some shared context between swipe copy generation and image prompt generation.

Both branches are exposed to overlapping inputs such as:

- the same swipe source asset
- the same asset brief requirement
- the same angle
- the same brand and campaign context
- the same optional product reference image
- the same Gemini File Search document bundles

That is enough to create broad thematic alignment.

It is **not** enough to guarantee congruence with the finalized creative because there is no direct enforcement that:

- the image headline mirrors the swipe copy headline
- the image body text matches the swipe copy primary text
- the image claims stay within the swipe copy guardrails
- the rendered image text is read back and reconciled against the stored Meta copy

### 5. Rendered assets are stored with both branches side by side

Each stored asset keeps:

- `swipeCopyPack`: the structured Meta copy pack
- `promptUsed`: the final image-render prompt
- `swipePromptExtractedRaw`: the markdown-extracted image prompt
- `swipePromptInputText`: the generic swipe template input
- swipe source metadata
- product-reference attachment metadata

This means the persisted asset contains evidence of both branches, but there is no step that forces those branches to match before the asset is accepted.

### 6. Meta review setup ignores the rendered image text

Later, campaign Meta review setup creates `meta_creative_specs` from `asset.ai_metadata.swipeCopyPack`.

That means:

- Meta `primary_text`, `headline`, and `description` come from the structured copy pack
- the image itself comes from the swipe-render branch
- there is no reconciliation step that checks whether the image’s on-image text matches the Meta headline/body

### 7. Existing QA is copy-only, not image-copy congruence QA

The current paid ads QA checks:

- Meta copy policy issues in `primary_text`, `headline`, and `description`
- landing page/destination readiness

It does not inspect:

- rendered image text
- image prompt text
- OCR of the generated image
- congruence between image headline and Meta headline
- congruence between image claims and copy-pack guardrails

So the system has no automated gate for the exact problem you observed.

## What Happened In This Campaign

### Campaign-level shape

For campaign `62a95f2d-f67a-462f-8c5e-e850b1a1df60`:

- Asset brief requirements: `2`
- Creative generation plan items: `60`
- Generated assets persisted: `48`
- Meta creative specs persisted: `39`

This is important operationally:

- one abstract brief turned into dozens of swipe-derived assets
- any mismatch pattern is amplified across the default swipe set

### Product-reference usage is inconsistent by swipe profile

Of the 48 generated assets:

- `33` had a product reference image attached
- `15` had no product reference image attached

This is not random.

It is controlled by the curated swipe profile file:

- `boss_babe.jpg` is marked `requires_product_image: false`
- `grocery.jpg` is marked `requires_product_image: false`
- `care_bag.jpg` is marked `requires_product_image: true`

So some variants are intentionally allowed to render with no product image anchor at all, based only on the swipe’s composition profile.

## Deeper Analysis: Primary Text vs Headline vs Image

Below are the clearest examples from the generated assets.

### Example A: Instagram authority portrait

- Asset ID: `670744ee-0104-419e-9651-3ca7488db4d7`
- Swipe source: `boss_babe.jpg`
- Product reference attached: `false`

Meta copy saved for the asset:

- Headline: `The Hidden Reason Your Thyroid Meds Stop Working`
- Primary text: thyroid-medication-specific copy about supplements neutralizing prescriptions

Rendered image:

- Expert portrait
- On-image headline: `Pharmacist: People Taking Prescription Meds Make One Dangerous Supplement Mistake`
- CTA: `Read this 3-min guide`

Analysis:

- The Meta copy is thyroid-specific.
- The image is only generic prescription-meds authority framing.
- The rendered image had no product reference image attached.
- The system preserved the swipe’s portrait-authority pattern, not the Meta copy’s specificity.

Result:

- topical overlap exists at a broad level
- specific semantic alignment does not
- the image is not "aware" of the final Meta headline; it is only broadly aware of the angle family

### Example B: Instagram dark interaction warning

- Asset ID: `0fd736fe-43df-4483-8bec-1fe574d906a1`
- Swipe source: `_initial_swipe_contact_sheet.jpg`
- Product reference attached: `true`

Meta copy saved for the asset:

- Headline: `The Hidden Prescription Clash Nobody Warns About`
- Primary text: curiosity-driven prescription/supplement blind-spot copy

Rendered image:

- Book, pill bottles, herbs, on-image badge and body text
- Main on-image headline: `NEW GUIDE EXPOSES DANGEROUS INTERACTIONS INSTANTLY`
- Supporting on-image body: says the handbook can `detect toxic herb-drug combos in seconds`, give `instant peace of mind`, and `help keep natural healing safe`

Analysis:

- The Meta headline and image headline are different.
- The image reveals a specific mechanism and capability that the Meta copy avoids.
- More seriously, the image text contradicts the copy pack’s own guardrails.

The copy pack guardrails for this campaign include:

- do not use `safe` / `safety` as a guaranteed outcome
- do not promise prevention of adverse reactions or side effects
- do not imply comprehensive interaction coverage

But the image prompt/output says:

- `SAFE`
- `detect toxic herb-drug combos in seconds`
- `instant peace of mind`
- `helps keep natural healing safe`

Result:

- this is not only incongruence
- it is a guardrail breach introduced by the image branch

### Example C: Facebook text-only card

- Asset ID: `41574860-93fe-432d-a2d1-4e85a1663f4b`
- Swipe source: `grocery.jpg`
- Product reference attached: `false`

Meta copy saved for the asset:

- Headline: `The Fatal Flaw Hidden In Your Morning Routine`
- Primary text: prescription/supplement blind-spot copy

Rendered image:

- Manifesto-style text card
- On-image lead: `You’ve been guessing. Old herb guides count on it.`
- Lower line: `There is a safer way to use herbs. We built it.`

Analysis:

- The rendered card closely follows the source swipe’s text-card composition.
- It generates an entirely separate on-image copy system.
- It also introduces a stronger solution reveal than the Meta headline.
- There is no product reference image to anchor the visual.

Result:

- image copy is swipe-led, not Meta-copy-led

### Example D: Facebook caregiving lifestyle scene

- Asset ID: `04da046d-349d-45f6-b6ea-201f4502705c`
- Swipe source: `care_bag.jpg`
- Product reference attached: `true`

Meta copy saved for the asset:

- Headline: `The Fatal Flaw In Most Online Herb Advice`
- Primary text: doctor-visit tension, hidden detail, online advice blind spot

Rendered image:

- Warm mother/baby living room scene
- Product placed on table
- On-image text: `Healing Comes Naturally. The Handbook Checks the Meds.`
- CTA: `Get Your Copy`

Analysis:

- The image inherits the swipe’s warm caregiving commercial structure.
- The Meta copy is warning-led and anxiety/uncertainty-led.
- The image is softer, more lifestyle/offer-oriented, and less problem-first.

Result:

- the image and Meta copy are directionally related but not the same ad concept

## Why The Mismatch Happens

### Root cause 1: The copy branch and image branch are separate siblings

The most important architectural fact is this:

- the Meta copy pack is generated first
- the image prompt is generated later
- but the image prompt generator is not fed the Meta copy pack as a required conditioning input

So the image generator does not have a contract like:

- use this exact headline
- use this exact body copy
- stay within these exact claims guardrails

Instead it receives:

- swipe design DNA
- brand + angle
- project docs
- optional product image

That is not enough to guarantee congruence with finalized Meta copy.

### Root cause 2: The swipe template explicitly prioritizes preserving competitor design DNA

The swipe prompt template is very explicit about what matters:

- preserve the original swipe’s visual identity
- preserve layout zones
- preserve text-zone structure
- faithfully adapt the competitor creative into a new prompt

This makes the system very good at producing swipe-like creatives.

It does not make the system good at ensuring that the rendered image is a visual extension of the finalized Meta copy pack.

### Root cause 3: The image branch is allowed to invent on-image copy

The architecture intentionally says:

- Meta copy pack owns Meta copy
- swipe image-ad flow owns on-image headline/body/CTA

That means by design:

- there can be one headline in the Meta spec
- and another headline in the image itself

There is no shared canonical source for both.

### Root cause 4: The image branch does not inherit the copy pack guardrails as enforceable constraints

Although the asset keeps both `swipeCopyPack` and the image prompt/output, there is no enforcement step that checks:

- whether image claims violate `claimsGuardrails`
- whether on-image text reveals what the Meta branch intentionally kept blind
- whether on-image promise intensity exceeds the Meta copy

So image prompt generation can drift into harder claims than the copy branch allowed.

### Root cause 5: Product image attachment is static-swipe-policy-driven, not campaign-semantic

Whether a product reference image is attached is decided by the curated swipe filename profile.

That means:

- `boss_babe.jpg` gets no product reference because the source swipe has no product
- `grocery.jpg` gets no product reference because the source swipe is text-only

This is reasonable for design preservation, but it weakens brand/product anchoring exactly on the kinds of swipes that most need semantic anchoring.

For the thyroid-specific portrait asset, that matters:

- the image stayed generic
- no product reference was attached
- the Meta copy stayed specific

## The Short Version

The pipeline is not failing because it cannot "see images" in a literal sense.

It is failing because the system contract does not define one canonical copy object that both:

- populates Meta `primary_text` / `headline`
- and constrains the image’s on-image headline/body/CTA

Today the system asks two different generators to do two related but separate jobs:

- one writes the Meta ad copy
- the other adapts a swipe into a rendered image with its own copy system

That is why the image and the primary text feel like different ads.

## Bottom Line

For this campaign, the mismatch is real and explainable:

- the asset brief is too abstract to anchor image/copy congruence by itself
- the ad copy pack and swipe-image prompt are generated on separate branches
- the swipe-image branch is driven by competitor composition fidelity, not by the final Meta headline
- the final Meta creative spec is built from the copy pack only
- no QA step checks the rendered image against the Meta copy or the copy-pack guardrails

So the current pipeline is not a single congruent ad-generation pipeline.

It is a copy pipeline plus a swipe-adaptation image pipeline that happen to be attached to the same asset record.
