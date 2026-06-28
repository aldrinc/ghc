# Landing Page Image Generation Operator Flow

## Decision

Add an explicit **visual reference prep** step to the landing page workflow.

The image brief is necessary, but it is not sufficient by itself to produce the final page images we want. Operators should prepare:

- a **local sample set** for standard landing-page/PDP images
- a **separate testimonial sample set** for testimonial/social-proof images

That step should happen before full-batch image generation.

## Where This Sits In The Overall Flow

This should sit after the campaign/page context is ready and before full image generation.

| Step | Purpose | Output |
| --- | --- | --- |
| 1. Strategy / offer / copy / design system | Lock the product truth and page direction | approved strategy context |
| 2. Asset brief generation | Define the image requirements and creative concepts | approved asset brief |
| 3. Visual reference prep | Choose the local sample sets used as design DNA | approved page-image sample set + approved testimonial sample set |
| 4. Standard page image spike | Validate one image first | one reviewed test image |
| 5. Standard page image batch | Generate the full non-testimonial image set | reviewed page-image bundle |
| 6. Testimonial spike | Validate one or a few testimonial examples first | reviewed testimonial test images |
| 7. Testimonial batch | Generate the final testimonial set | reviewed testimonial bundle |
| 8. Final page assembly / creative production | Use the approved image sources in page or campaign execution | final page-ready image inventory |

## Why This Step Exists

What we learned from the Tenor PDP flow:

- The asset brief is good for **concept and requirement selection**.
- The local sample set is what gives us the **visual structure and design DNA** for the actual images.
- We should not run the entire batch first. We should run **one image as a spike**, review it, correct context, and only then run the remainder.
- Testimonials should not be treated as “just another page image.” They need their own **sample set and runtime framing**.

## Inputs

### Standard landing page / PDP images

Required:

- approved asset brief
- approved campaign creative context or equivalent product truth
- real product reference image(s)
- local sample image set for the target page type

Examples of target sample sets:

- PDP carousel supplements
- advertorial/listicle image examples
- comparison blocks
- infographic-style images

### Testimonials

Required:

- approved page/campaign context
- real product reference image(s)
- separate local testimonial sample set
- explicit testimonial framing rules

Examples of testimonial framing rules:

- customer vs founder-led
- no text vs text allowed
- no badges / no UI / no quote marks
- product visible vs product secondary

## Standard Page Image Process

### 1. Curate a local sample set

Pick a folder of example images that represent the visual direction for the page type.

This set is the **visual source material**, not the strategy source of truth.

### 2. Map the sample set to the page requirements

For each sample image, decide:

- which image requirement or slot it maps to
- whether it is hero / benefit / details / guarantee / how-to-use / mechanism / lifestyle / etc.

Do not start by generating everything. Start with the first high-signal example.

### 3. Run a one-image spike

Generate one image using the current flow and the chosen sample.

The goal of the spike is not throughput. The goal is to validate:

- product truth fidelity
- label fidelity
- whether the flow is inheriting the wrong traits from the source image
- whether the composition is translating correctly

### 4. Review and correct context

If the spike is wrong, correct the runtime guidance before generating the rest.

Typical issues to catch here:

- source-only flavor traits leaking through
- wrong dosage form or product form
- wrong label or packaging redesign
- wrong props or consumption scene
- text overlays that should not exist

This step should prefer **runtime/context correction first**, before code changes.

### 5. Lock the approved guidance

Once the first image looks correct enough, lock the generation notes for the remainder of the set.

Examples:

- keep the real bottle/label faithful
- preserve layout/composition from the sample
- do not inherit source-only product semantics
- no text overlays unless explicitly desired

### 6. Run the remaining non-testimonial images

Generate the rest of the page-image set using the same approved framing.

### 7. Save a review bundle

Save all generated outputs into a single review folder with:

- images
- manifest
- any stage-one prompt traces that are useful for debugging

### 8. Approve the page-image source set

The approved outputs become the working image inventory for:

- page assembly
- campaign swipe collection seeding
- later creative production reference use

## Testimonial Image Process

### 1. Create a separate testimonial sample set

Testimonials must have their own reference set.

Do not reuse the standard PDP/page-image sample set for testimonials.

The testimonial sample set should represent the exact testimonial family you want:

- UGC-style testimonial photos
- social-style testimonial images
- quote-driven testimonial examples
- no-text testimonial lifestyle images

### 2. Define testimonial mode before generation

Set the intended framing before you run the batch.

Typical operator decisions:

- customer testimonial vs founder authority
- no text on image vs testimonial text allowed
- product prominent vs product secondary
- lifestyle testimonial vs social-comment testimonial

### 3. Run a small testimonial spike

Generate one or a few testimonial examples first.

Validate:

- wrong founder/doctor framing is not leaking in
- text/no-text behavior is correct
- product presence is correct
- testimonial style matches the intended sample set

### 4. Correct runtime framing if needed

If the spike is wrong, adjust the runtime context and rerun.

Examples:

- remove founder/MD framing
- force customer lifestyle testimonial framing
- explicitly forbid text overlays
- explicitly forbid badges/UI/quote cards when not desired

### 5. Run the final testimonial batch

Only after the spike is approved should the final testimonial batch be generated.

### 6. Save a testimonial review bundle

Save the final testimonial outputs in their own bundle, separate from the standard page-image bundle.

## Operator Rules

- Do not rely on the image brief alone to determine the final visual treatment.
- Always start with a **sample set**.
- Always run a **small spike first**.
- Keep standard page images and testimonial images as **separate flows**.
- Prefer **runtime/context corrections** before changing code.
- Only change code if the same failure pattern is clearly reusable across campaigns.

## Definition Of Done

This step is complete when:

- the standard page-image sample set is curated
- the testimonial sample set is curated
- at least one spike image has been reviewed for each path
- the runtime guidance is stable enough to run the remainder
- the generated outputs are saved into clear review bundles
- the approved outputs are ready to be used in page assembly or creative production

## References

- [Swipe Image Add Flow](./swipe-image-add-flow.md)
- [Marketing Ad Copy Flow Analysis](./marketing-ad-copy-flow-analysis-2026-03-17.md)
- [Testimonial Service End to End](./testimonial-service-end-to-end.md)
- [Swipe Testimonial Workflow](./swipe-testimonial-workflow.md)
