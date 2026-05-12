# Animated Swipe GIF Model Comparison Prompt

Decision: use a separate animated swipe flow that inherits the current swipe-image constraints, but do not ask a video model to render locked template elements. The model may generate only non-critical visual texture or photographic motion. Text, charts, axes, badges, UI chrome, product/logo placement, brand colors, masks, timing, crops, and output conversion must be rendered deterministically from a template manifest.

## Constraint Lineage

This prompt mirrors the current swipe-image flow constraints:

- Asset brief context: `creativeConcept`, selected `requirements[requirementIndex]`, `constraints`, `toneGuidelines`, and `visualGuidelines`.
- Requirement context: `channel`, `format`, `funnelStage`, `destinationType`, `destinationLabel`, `angle`, and `hook`.
- Brand/product context: brand name, product name, audience, brand colors/fonts, must-avoid claims, product assets.
- Swipe preservation: preserve source design DNA, native UI/screenshot chrome, spatial relationships, typography zones, aspect ratio, framing, lighting, visual energy, and realism cues.
- Product reference rules: use product references only when the source template contains a competitor product slot. Keep packaging form factor, replace competitor branding, do not invent ingredients, servings, certifications, guarantees, or efficacy claims.
- Compliance and copy rules: use only approved visible source copy or explicit final copy, obey constraints over aggressive direct-response style, and do not reveal hidden mechanisms in feed-style copy unless explicitly approved.

## Post-Pilot Finding

The first `sora-2` item `05` pilot showed the failure mode we should design around:

- Sora treated the reference as inspiration rather than a locked template.
- It invented extra line points and an extra `WITH TENOR` label on the chart line.
- It drifted from the brand red/orange into white and golden glow artifacts.
- It changed axis-label sizes and orientation.
- It inserted a product bottle even though source item `05` has no competitor product slot.

Conclusion: prompt-only fidelity is not enough for production GIF recreation. The generic solution must be a hybrid deterministic renderer, not a full-frame video prompt.

## Deterministic Renderer Contract

Every animated swipe template should be converted into a `template_manifest` before generation. The manifest becomes the source of truth for all locked elements.

```json
{
  "templateId": "",
  "source": {
    "url": "",
    "sha256": "",
    "width": 0,
    "height": 0,
    "durationSeconds": 0,
    "frameCount": 0
  },
  "canvas": {
    "width": 0,
    "height": 0,
    "aspectRatio": "1:1",
    "cornerRadius": 0,
    "safeCrop": null
  },
  "productReplacement": {
    "hasCompetitorProductSlot": false,
    "slotMask": null,
    "slotBox": null,
    "replacementRequired": false
  },
  "brandReplacement": {
    "sourceBrandText": [],
    "targetBrandText": [],
    "accentColor": "",
    "fontFamily": "",
    "letterSpacing": 0
  },
  "lockedLayers": [
    {
      "id": "",
      "type": "text|axis|chart_line|shape|badge|ui_chrome|logo|product|mask",
      "sourceBox": [0, 0, 0, 0],
      "targetBox": [0, 0, 0, 0],
      "color": "",
      "fontSize": null,
      "fontWeight": null,
      "rotationDegrees": 0,
      "text": null,
      "path": null,
      "timing": {
        "startSeconds": 0,
        "endSeconds": 0,
        "easing": "source"
      },
      "locked": true
    }
  ],
  "generativeLayers": [
    {
      "id": "",
      "type": "background_texture|photo_subject|lifestyle_motion",
      "mask": null,
      "prompt": ""
    }
  ]
}
```

Hard manifest rules:

- If `productReplacement.hasCompetitorProductSlot` is `false`, no product reference may be inserted into the output.
- If a layer is `locked: true`, the model never renders it. The renderer draws it after generation.
- Text layers must preserve source font size, orientation, spacing, position, color role, and reading order unless the manifest explicitly overrides them.
- Chart lines must preserve the source path geometry. Brand recoloring is allowed, but extra points, glows, duplicate labels, and path simplification are not.
- Axis labels, tick labels, captions, badges, and compliance text are deterministic overlays. They are not part of the video-model prompt.
- Brand accent colors come from the brand/design system or product page extraction. They are stored as hex values in the manifest, then rendered by code. The model is not trusted to choose the color.

## Render Modes

Use the lowest-variance render mode that fits the source template.

| Source template type | Render mode | Model role |
| --- | --- | --- |
| Chart, graph, counter, badges, text-heavy ad graphic | Fully deterministic animation | None, except optional background texture generation |
| Static design with subtle particles/light | Deterministic layers over source-matched generated/cleaned background | Generate background only |
| Product/badge composition with a visible competitor product | Deterministic product/logo/badge/text replacement | Generate background only if needed |
| Lifestyle/photo/UGC motion with little text | Hybrid video generation plus deterministic overlays | Generate subject/background motion |
| Complex cinematic video | Video generation with deterministic final overlays | Generate motion only |

Item `05` belongs in the first row. The product must not appear because the source template has no competitor product slot.

## Model Handling

- `sora-2` / `sora-2-pro`: use only for generative layers. Attach masked/keyframe references only when a model-rendered region is needed. Convert the MP4 output to GIF or animated WebP after deterministic overlays are applied.
- `veo-3.1-*`: use only for generative layers. Attach masked/keyframe references only when a model-rendered region is needed. Convert the video output to GIF or animated WebP after deterministic overlays are applied.
- `gpt-image-2`, `gemini-3.1-flash-image-preview`, and `gemini-3-pro-image-preview`: run as still-image/keyframe baselines only. Do not score them as GIF generation models because they do not produce animated output.

## Real Mars Source GIFs

Use these as the first comparison batch. These are the animated assets extracted from `https://mengotomars.com/pages/10-reasons-glp-shop`.

| Item | Source duration | Frames | Source size | Listicle heading |
| --- | ---: | ---: | --- | --- |
| 01 | 2.40s | 2 | 1368x1368 | It stops the muscle loss that makes you "skinny fat" instead of actually fit |
| 03 | 4.80s | 4 | 672x672 | It brings back the sex drive that GLP-1s quietly kill |
| 04 | 2.90s | 29 | 798x798 | It maintains your strength while the scale drops so you don't become weak |
| 05 | 2.86s | 16 | 996x996 | It delivers all-day energy without stimulants because your body needs real fuel |
| 07 | 7.20s | 7 | 672x672 | It works WITH your body, not like TRT that shuts down natural production |
| 09 | 4.80s | 4 | 1008x1008 | It's natural, third-party tested, and safe* |
| 10 | 2.80s | 14 | 672x672 | Join the 429,576+ men who refuse to lose their edge while losing weight |

## Input Payload

Fill this with real MOS values before each model run. Do not fabricate missing fields. If a value is unknown, use `null`, `[]`, or omit optional arrays, then let the prompt preserve only what is actually known.

```json
{
  "runId": "",
  "modelUnderTest": "",
  "brand": {
    "brandName": "",
    "productName": "",
    "audience": "",
    "brandColorsFonts": "",
    "mustAvoidClaims": [],
    "assets": {
      "productReferenceAssetIds": [],
      "productReferenceUrls": [],
      "logoAssetIds": [],
      "logoUrls": []
    }
  },
  "assetBrief": {
    "assetBriefId": "",
    "campaignId": "",
    "funnelId": "",
    "variantId": "",
    "variantName": "",
    "creativeConcept": "",
    "requirementIndex": 0,
    "requirement": {
      "channel": "",
      "format": "animated_image",
      "funnelStage": "",
      "destinationType": "",
      "destinationLabel": "",
      "angle": "",
      "hook": ""
    },
    "constraints": [],
    "toneGuidelines": [],
    "visualGuidelines": []
  },
  "sourceTemplate": {
    "itemNumber": "",
    "heading": "",
    "sourceUrl": "",
    "mimeType": "image/gif",
    "width": 0,
    "height": 0,
    "durationSeconds": 0,
    "frameCount": 0,
    "visibleText": [],
    "motionNotes": [],
    "keyframeDescriptions": [],
    "templateManifest": {
      "templateId": "",
      "productReplacement": {
        "hasCompetitorProductSlot": false,
        "replacementRequired": false
      },
      "lockedLayerIds": [],
      "generativeLayerIds": []
    }
  },
  "finalCopy": {
    "onScreenText": [],
    "badges": [],
    "disclaimers": [],
    "cta": ""
  },
  "generation": {
    "targetAspectRatio": "1:1",
    "targetDurationSeconds": 0,
    "targetOutput": "mp4_then_gif",
    "looping": true,
    "renderMode": "deterministic|hybrid|model_only_exploration",
    "modelMayRenderText": false,
    "modelMayRenderCharts": false,
    "modelMayInsertProduct": false
  }
}
```

## Universal Generation Prompt

Use this exact prompt body for every model. Put the filled JSON payload after `INPUT JSON`.

```text
ROLE
You are a direct-response creative strategist, motion designer, and performance ad art director. Your task is to recreate the attached source animated ad as a new branded animated creative while preserving the source template's design DNA and motion logic.

PRIMARY OBJECTIVE
Generate only the model-rendered region described by INPUT JSON `sourceTemplate.templateManifest.generativeLayerIds`. The final GIF will be assembled by a deterministic renderer. Do not render locked template layers.

INPUTS
You will receive:
- INPUT JSON containing brand, product, asset brief, selected requirement, source template metadata, final copy, and generation settings.
- Source template reference media: the original GIF when supported, plus extracted keyframes when the model requires still image references.
- Product reference images and/or logo references only when `sourceTemplate.templateManifest.productReplacement.hasCompetitorProductSlot` is true.

HARD RULES
1. Preserve the source template's design DNA inside the model-rendered region only. Do not redesign the full composition.
2. Preserve spatial fidelity inside the model-rendered region only. Overall placement, text, chart paths, product slots, and overlays are handled by the deterministic renderer.
3. Preserve the animation logic for the model-rendered region only. Locked chart motion, counter motion, badge appearance, and typography timing are handled by the deterministic renderer.
4. Preserve aspect ratio and framing. The output is 1:1 unless the input JSON states otherwise. Do not add gutters, borders, blurred sidebars, device frames, or extra margins that are not in the source.
5. Preserve native UI or overlay chrome when present. If the source includes social UI, screenshot chrome, badges, labels, ratings, interface rows, chart axes, or caption blocks, treat them as required layout zones.
6. Swap product identity only when the template manifest says a competitor product slot exists. If no competitor product slot exists, do not insert any product, bottle, packshot, logo, capsule, pouch, or packaging.
7. When product replacement is explicitly enabled, product references are the source of truth. Keep packaging form factor, silhouette, closure style, material, label layout, visible brand marks, packaging colors, and container construction recognizable. Do not convert a pouch into a bottle, jar, tub, box, or another format.
8. Do not invent ingredients, servings, certifications, guarantees, clinical claims, efficacy claims, social proof numbers, awards, badges, or third-party testing claims. Use only source-visible information or explicit final copy from INPUT JSON.
9. If a detail is missing, unreadable, or unsupported by INPUT JSON, keep it minimal or omit it. Do not guess.
10. Do not render locked text. On-screen text, chart labels, badges, disclaimers, CTAs, and ratings are deterministic overlays unless INPUT JSON explicitly sets `generation.modelMayRenderText` to true.
11. Respect asset brief constraints. Obey `constraints`, `toneGuidelines`, `visualGuidelines`, `angle`, `hook`, `funnelStage`, and destination context from INPUT JSON. If these conflict with aggressive ad styling, obey the constraints first.
12. Keep direct-response clarity. The first frame should immediately communicate the same scroll-stopping visual hook as the source. The animation should be understandable without sound.
13. For human subjects, keep realism believable: natural skin texture, imperfect posture, practical lighting, slight asymmetry, normal body proportions, realistic hands, and non-editorial camera feel unless the source itself is polished.
14. Avoid AI artifacts: no warped text, malformed hands, duplicated limbs, impossible packaging, unreadable labels where text is meant to be readable, flickering product identity, or inconsistent faces/bodies between frames.
15. Do not add extra chart points, glows, labels, duplicate phrases, icons, badges, products, or text not present in the manifest. If a locked layer is visible in the reference, ignore it as something the deterministic renderer will draw.

MOTION REQUIREMENTS
- Target duration is `generation.targetDurationSeconds`. If the model only supports fixed durations, generate motion that can sit behind deterministic layers for that duration and end on a clean loopable frame.
- Keep motion restrained when the source is a designed ad graphic. Do not add cinematic camera moves, scene changes, or new shots unless the source has them.
- For chart or typography-heavy source GIFs, the preferred model output is no output: render fully deterministically. If a model must be called, generate background texture only.
- For product/badge source GIFs, keep the product and badges anchored; animate reveal, shimmer, small scale, particle, or spotlight effects only if the source uses similar motion.
- For before/after or customer collage source GIFs, preserve the source's grid/panel rhythm and do not invent unsupported transformation claims.

OUTPUT REQUIREMENT
Return one finished video for the generative layer only, suitable for deterministic compositing and conversion to GIF/animated WebP. Do not return analysis text, storyboard text, markdown, JSON, captions, chart labels, or explanatory overlays in the rendered creative.

INPUT JSON
{{INPUT_JSON}}
```

## Static Keyframe Baseline Prompt

Use only for still-image models. This is not a GIF-generation comparison; it measures how well a still model can recreate the most important frame.

```text
Create the strongest single keyframe for the animated ad described in INPUT JSON. Preserve the same design DNA, spatial fidelity, typography zones, product identity rules, compliance constraints, and visual guidelines as the Universal Generation Prompt. Output one static 1:1 image representing the first frame or most commercially important frame of the source animation. Do not invent unsupported claims, badges, numbers, certifications, or packaging details.

INPUT JSON
{{INPUT_JSON}}
```

## Quality Judge Prompt

Use this after each generation. Attach the source GIF or source keyframe sheet, the generated output, and the filled INPUT JSON.

```text
You are judging an AI-generated animated ad recreation against a source swipe template and a strict asset brief.

Return valid JSON only.

Score each category from 1 to 5:
- designDnaFidelity: source palette, texture, visual energy, layout zones, and overall ad type.
- spatialFidelity: placement, spacing, scale, crop, typography zones, badge/icon positions, and reading order.
- motionFidelity: timing, sequence, loop feel, animation style, chart/counter/badge/customer collage behavior.
- productIdentityAccuracy: packaging form factor, colors, logo/label consistency, no invented product details.
- copyAndCompliance: on-screen text accuracy, no unsupported claims, no invented numbers/certifications/guarantees, respects INPUT JSON constraints.
- outputUsability: whether the result is good enough to test on a listicle page after deterministic GIF conversion.

Also return:
- topStrengths: 1-3 short bullets.
- blockingIssues: 0-5 short bullets, only issues that would block production use.
- recommendedAction: one of ["ship", "minor_edit", "regenerate_same_prompt", "adjust_prompt", "reject_model_for_this_template"].
- productionNotes: one concise paragraph.

JSON shape:
{
  "modelUnderTest": "",
  "sourceTemplateItem": "",
  "scores": {
    "designDnaFidelity": 0,
    "spatialFidelity": 0,
    "motionFidelity": 0,
    "productIdentityAccuracy": 0,
    "copyAndCompliance": 0,
    "outputUsability": 0
  },
  "weightedScore100": 0,
  "topStrengths": [],
  "blockingIssues": [],
  "recommendedAction": "",
  "productionNotes": ""
}
```

Suggested weights for `weightedScore100`:

- designDnaFidelity: 20
- spatialFidelity: 20
- motionFidelity: 20
- productIdentityAccuracy: 15
- copyAndCompliance: 15
- outputUsability: 10

## Comparison Run Rules

- Use the same filled INPUT JSON for every model in the same item test.
- Use the same source keyframes for every model.
- Use the same product reference images for every model.
- Use the same requested aspect ratio and nearest available duration for every model where possible.
- Record billable seconds, model, provider, output URL, conversion settings, prompt hash, source hash, and judge score.
- Do not retry with alternate prompts during the comparison batch. If a model fails, record the clean failure and move on only when that model was explicitly included in the authorized batch.
