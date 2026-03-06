# Honest Herbalist Full Funnel Generation Report 2026-03-05

## Summary
- Source Strategy V2 run id: `732c4f5c-7d12-42bf-8014-75c9bfd00230`
- Selected angle: `A02 - Herb–Drug Interaction 'Non-Answer' Fix`
- Variant id: `variant_a`
- Fresh raw copy artifact id: `dfca4247-571b-4883-b982-a0c5802408ac`
- Latest approved copy artifact id used downstream: `19a74f1a-5a78-4808-b1be-dd9d19967c33`
- New campaign id: `7fa83f2e-9ed3-410d-a764-77139cb42a35`
- Funnel generation workflow run id: `e8ec01ab-23e7-4af2-9efc-483bb67f4b1a`
- Temporal workflow id: `campaign-funnels-0d3186be-2c4f-4d5d-a810-d87b3b35265e-7fa83f2e-9ed3-410d-a764-77139cb42a35-19bad24d-9295-4ef6-9582-4d1671b3b03f`
- Generated funnel id: `39286aab-b136-4c5a-b140-9aa74d20dbb7`
- Route slug: `ang-a02-full-funnel-review-20260305-191236-funnel-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow`
- Asset brief artifact id: `50f0e535-1f45-4b95-a740-d483d9455cc3`

## Review URLs
- Pre-sales: `http://127.0.0.1:5275/f/502a0317/ang-a02-full-funnel-review-20260305-191236-funnel-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/pre-sales`
- Sales: `http://127.0.0.1:5275/f/502a0317/ang-a02-full-funnel-review-20260305-191236-funnel-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow/sales`

## Validation Notes
- Pre-sales preview payload resolves through `/public/funnels/502a0317/.../pages/pre-sales` and reports brand metadata for `The Honest Herbalist`.
- Sales preview payload resolves through `/public/funnels/502a0317/.../pages/sales` and reports brand metadata for `The Honest Herbalist`.
- Pre-sales page has `4` saved versions; latest version includes `generatedTestimonials` and `testimonialsProvenance` in `ai_metadata`.
- Sales page has `3` saved versions; latest version includes generated image metadata in `ai_metadata`.
- Pre-sales payload currently contains `14` unique `assetPublicId` references plus `3` icon asset references.
- Sales payload currently contains `28` unique `assetPublicId` references.

## Important Runtime Note
- The original campaign funnel workflow created the funnel pages and media-enriched them successfully, but then failed on the follow-up asset-brief step because this product had no Claude context-file registrations for the new workflow workspace id.
- I remediated that by registering the required Claude context for the workflow workspace and then running the asset-brief activity directly.
- The campaign now has a generated asset-brief artifact and the funnel pages themselves are populated for review.
