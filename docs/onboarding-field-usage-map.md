# Onboarding Field Usage Map

## Scope

This document maps the current onboarding wizard fields to:

1. where each field is validated,
2. where it is persisted,
3. which downstream code paths consume it,
4. whether that consumption is part of the active onboarding path or only a secondary/legacy reader.

Update as of March 19, 2026:

- The onboarding wizard no longer collects `client_industry`, `primary_benefits`, `feature_bullets`, `guarantee_text`, `disclaimers`, `goals`, or `funnel_notes`.
- The onboarding wizard no longer uploads or requires the primary product image.
- A primary product image is now enforced at Strategy Hub launch time instead, alongside Shopify readiness.
- Some sections below still describe downstream readers for removed fields because the backend schema and other product-management surfaces still support them.

Primary sources:

- `mos/frontend/src/components/clients/OnboardingWizard.tsx`
- `mos/backend/app/schemas/onboarding.py`
- `mos/backend/app/routers/clients.py`
- `mos/backend/app/temporal/workflows/client_onboarding.py`
- `mos/backend/app/temporal/workflows/strategy_v2.py`
- `mos/backend/app/temporal/activities/strategy_v2_activities.py`

## The Actual Runtime Path

The current happy path is:

1. The wizard collects basics, one product, and Strategy V2 operator inputs.
2. If needed, the frontend creates the client/workspace first.
3. The frontend upserts a compliance profile before onboarding starts.
4. `POST /clients/{client_id}/onboarding` creates:
   - a `product`,
   - a default `product_offer`,
   - a default `product_variant`,
   - an `onboarding_payload` record.
5. `ClientOnboardingWorkflow` immediately starts `StrategyV2Workflow`.
6. Later, before campaign launch, Strategy Hub requires Shopify readiness and a valid primary product image on the product record.

Important: the current `ClientOnboardingWorkflow` does **not** directly run the old canon/metric/design-system activities. Those still exist and can read onboarding payloads later, but they are not the direct onboarding execution path anymore.

## Hard Constraints And Mismatches

- The wizard supports only **one** product right now. The frontend blocks more than one product.
- `business_type="existing"` is exposed in the UI, but the backend returns `501 Not Implemented` for anything except `"new"`.
- The primary product image is **not part of the onboarding API contract** and is no longer collected in the onboarding wizard.
- Strategy Hub launch now blocks if the product has no ready primary image or if the primary asset is not a usable image.
- `client_industry`, `goals`, and `funnel_notes` are no longer collected in the onboarding wizard.
- `product_category` is still collected, but it remains payload context rather than a core Strategy V2 contract field.

## Removed From The Current Wizard

These fields are no longer collected during onboarding because they are not strict requirements for starting Strategy V2:

- `client_industry`
- `primary_benefits`
- `feature_bullets`
- `guarantee_text`
- `disclaimers`
- `goals`
- `funnel_notes`

They still have downstream readers in some legacy or secondary flows, but they can be collected later from product setup or other editing surfaces if needed.

## Field Breakdown

### Basics Step

#### `client_name`

- UI requirement:
  - Required only when the wizard is creating a new client.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:204-218`, `mos/frontend/src/components/clients/OnboardingWizard.tsx:295-306`
- Persistence:
  - Stored on the client record through `useCreateClient`.
  - Also sent as `legalBusinessName` when the compliance profile is created.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:297-301`, `mos/frontend/src/components/clients/OnboardingWizard.tsx:419-430`
- Why it exists:
  - Needed to create/select the workspace and to seed compliance/business identity data.
- Downstream use:
  - Used as the workspace/client name everywhere the client record is shown.
  - Used later as brand name in design-system generation and the fallback logo prompt.
  - Source: `mos/backend/app/temporal/activities/client_onboarding_activities.py:302-308`, `mos/backend/app/temporal/activities/client_onboarding_activities.py:331-367`

#### `client_industry`

- UI requirement:
  - No longer collected in the onboarding wizard.
- Persistence:
  - Still supported on the client record outside onboarding.
- Why it exists:
  - Extra brand context. It does not drive the core onboarding contract.
- Downstream use:
  - Secondary reader only: design-system generation and fallback logo prompt use it for brand styling context.
  - Source: `mos/backend/app/temporal/activities/client_onboarding_activities.py:307-308`, `mos/backend/app/temporal/activities/client_onboarding_activities.py:339-343`

#### `business_type`

- UI/API requirement:
  - Present in the API schema.
  - Source: `mos/backend/app/schemas/onboarding.py:10`
- Persistence:
  - Stored in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11162-11172`
- Why it exists:
  - It appears intended to distinguish onboarding paths for new vs existing businesses.
- Active downstream use:
  - The backend currently rejects anything except `"new"`.
  - Source: `mos/backend/app/routers/clients.py:11088-11092`
- Secondary use:
  - Older payload readers use it as fallback context in pre-canon research and metric-schema heuristics.
  - Source: `mos/backend/app/temporal/workflows/precanon_market_research.py:117-139`, `mos/backend/app/temporal/activities/client_onboarding_activities.py:94-101`
- Current assessment:
  - This field is more of a path selector / future flag than a rich downstream input in the current active flow.

#### `brand_story`

- UI/API requirement:
  - Required in the wizard and required by the onboarding schema.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:213-218`, `mos/backend/app/schemas/onboarding.py:11`
- Persistence:
  - Stored in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11162-11172`
- Why it exists:
  - Gives the system brand context before research and copy generation.
- Active downstream use:
  - It is carried inside `onboarding_payload` and therefore enters Strategy V2 foundational prompt context through `BUSINESS_CONTEXT_JSON`.
  - Source: `mos/backend/app/temporal/activities/strategy_v2_activities.py:8385-8392`
- Secondary use:
  - Used directly by Shopify theme sync prompt context.
  - Used by the old client canon builder.
  - Used by design-system generation and the fallback logo prompt.
  - Source: `mos/backend/app/routers/clients.py:4110-4126`, `mos/backend/app/temporal/activities/client_onboarding_activities.py:40-67`, `mos/backend/app/temporal/activities/client_onboarding_activities.py:280-343`

### Product Step

#### `product_name`

- UI/API requirement:
  - Required.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:315-317`, `mos/backend/app/schemas/onboarding.py:12`
- Persistence:
  - Stored as `product.title`.
  - Used as the default offer name.
  - Used as the default variant title.
  - Also stored in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11108-11131`, `mos/backend/app/routers/clients.py:11133-11160`, `mos/backend/app/routers/clients.py:11162-11172`
- Why it exists:
  - It is the canonical product identity for both the persisted product record and Stage 0 strategy inputs.
- Active downstream use:
  - Stage 0 translation uses it as the product brief name.
  - Foundational research uses it in business context.
  - Strategy V2 later uses it throughout stage artifacts and offer construction.
  - Source: `mos/backend/app/strategy_v2/translation.py:398-455`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:8385-8392`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:12756-12763`

#### `product_description`

- UI/API requirement:
  - Required.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:319-321`, `mos/backend/app/schemas/onboarding.py:23`
- Persistence:
  - Stored as `product.description`.
  - Used as the default offer description.
  - Stored in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11108-11131`, `mos/backend/app/routers/clients.py:11137-11139`, `mos/backend/app/routers/clients.py:11162-11172`
- Why it exists:
  - It is required by Stage 0 translation and foundational research context.
- Active downstream use:
  - Stage 0 translation uses it as `description`.
  - Foundational research uses it inside `BUSINESS_CONTEXT`.
  - Source: `mos/backend/app/strategy_v2/translation.py:410-460`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:8385-8392`

#### `price`

- UI/API requirement:
  - Required.
  - Backend validates it as a concrete price, not vague text.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:323-325`, `mos/backend/app/schemas/onboarding.py:13`, `mos/backend/app/schemas/onboarding.py:56-62`
- Persistence:
  - Converted into cents/currency and stored on the default variant.
  - Also stored in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11150-11160`, `mos/backend/app/routers/clients.py:11162-11172`
- Why it exists:
  - Stage 0 and the Offer Agent require an explicit price point.
- Active downstream use:
  - Stage 0 translation carries the price forward.
  - Offer pipeline resolves it into `price_cents` / `currency`.
  - Source: `mos/backend/app/strategy_v2/translation.py:431-464`, `mos/backend/app/strategy_v2/translation.py:772-779`

#### `product_type`

- UI/API requirement:
  - Required.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:327-329`, `mos/backend/app/schemas/onboarding.py:14`
- Persistence:
  - Canonicalized before save and persisted to `product.product_type`.
  - Also stored in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11111-11117`, `mos/backend/app/routers/clients.py:11162-11172`
- Why it exists:
  - It drives product-specific logic in theme generation, funnel AI, and offer readiness.
- Active downstream use:
  - Strategy V2 offer-data readiness checks that onboarding/product record types agree and fails if they mismatch.
  - Funnel AI uses it to specialize image prompt behavior, especially for books.
  - Shopify theme content planning serializes it into product context.
  - Source: `mos/backend/app/temporal/activities/strategy_v2_activities.py:6276-6293`, `mos/backend/app/services/funnel_ai.py:2692-2734`, `mos/backend/app/services/funnel_ai.py:3054-3062`, `mos/backend/app/services/shopify_theme_content_planner.py:221-242`
- Notes:
  - This is one of the most important persisted product fields after name/description/price.

#### `product_category`

- UI/API requirement:
  - Optional.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:734-744`, `mos/backend/app/schemas/onboarding.py:24`
- Persistence:
  - Stored only in `onboarding_payload.data`.
  - It is **not** written onto the `products` table by the onboarding route.
  - Source: `mos/backend/app/routers/clients.py:11108-11131`, `mos/backend/app/routers/clients.py:11162-11172`
- Why it exists:
  - It provides a more explicit niche/category label for research than generic product type.
- Active downstream use:
  - Foundational research prefers `product_category` as `category_niche`, then falls back to `product.product_type`.
  - Pre-canon base variables also use it as `CATEGORY_NICHE`.
  - Source: `mos/backend/app/temporal/activities/strategy_v2_activities.py:8364-8375`, `mos/backend/app/temporal/workflows/precanon_market_research.py:121-139`
- Secondary use:
  - Design-system generation reads it from the onboarding payload.
  - Source: `mos/backend/app/temporal/activities/client_onboarding_activities.py:296-312`

#### `primary_benefits`

- UI/API requirement:
  - No longer collected in the onboarding wizard.
  - Still supported by the backend schema and product surfaces.
- Persistence:
  - Stored on `product.primary_benefits`.
  - Also used to seed `offer.differentiation_bullets`.
  - Stored in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11118-11121`, `mos/backend/app/routers/clients.py:11139-11140`, `mos/backend/app/routers/clients.py:11162-11172`
- Why it exists:
  - It gives immediate value props before Strategy V2 has rebuilt the offer.
- Downstream use:
  - Included in design-system generation context.
  - Included in Shopify theme product context.
  - Included in Funnel AI product serialization.
  - Included in swipe image ad product context.
  - Source: `mos/backend/app/temporal/activities/client_onboarding_activities.py:311-315`, `mos/backend/app/services/shopify_theme_content_planner.py:225-242`, `mos/backend/app/services/funnel_ai.py:4222-4241`, `mos/backend/app/temporal/activities/swipe_image_ad_activities.py:1276-1286`
- Notes:
  - Later Strategy V2 offer sync can replace the initial offer differentiation bullets with stage-derived value-stack summaries.
  - Source: `mos/backend/app/temporal/activities/strategy_v2_activities.py:7007-7047`

#### `feature_bullets`

- UI/API requirement:
  - No longer collected in the onboarding wizard.
  - Still supported by the backend schema and product surfaces.
- Persistence:
  - Stored on `product.feature_bullets`.
  - Stored in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11120-11121`, `mos/backend/app/routers/clients.py:11162-11172`
- Why it exists:
  - Provides structured product specifics for later generators.
- Downstream use:
  - Included in design-system generation context.
  - Included in Shopify theme product context.
  - Included in Funnel AI product serialization.
  - Included in swipe image ad product context.
  - Source: `mos/backend/app/temporal/activities/client_onboarding_activities.py:312-315`, `mos/backend/app/services/shopify_theme_content_planner.py:231-241`, `mos/backend/app/services/funnel_ai.py:4227-4232`, `mos/backend/app/temporal/activities/swipe_image_ad_activities.py:1283-1286`

#### `guarantee_text`

- UI/API requirement:
  - No longer collected in the onboarding wizard.
  - Still supported by the backend schema and product surfaces.
- Persistence:
  - Stored on `product.guarantee_text`.
  - Also seeds `offer.guarantee_text`.
  - Stored in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11122-11123`, `mos/backend/app/routers/clients.py:11141-11142`, `mos/backend/app/routers/clients.py:11162-11172`
- Why it exists:
  - Gives the initial product/offer a guarantee before Strategy V2 rewrites the offer.
- Downstream use:
  - Included in design-system context.
  - Included in Shopify theme product context.
  - Included in Funnel AI and swipe product serialization.
  - Source: `mos/backend/app/temporal/activities/client_onboarding_activities.py:313-315`, `mos/backend/app/services/shopify_theme_content_planner.py:236-242`, `mos/backend/app/services/funnel_ai.py:4229-4232`, `mos/backend/app/temporal/activities/swipe_image_ad_activities.py:1283-1286`
- Notes:
  - Later Strategy V2 winner sync overwrites the offer guarantee with the selected stage-3 guarantee.
  - Source: `mos/backend/app/temporal/activities/strategy_v2_activities.py:7014-7047`

#### `disclaimers`

- UI/API requirement:
  - No longer collected in the onboarding wizard.
  - Still supported by the backend schema and product surfaces.
- Persistence:
  - Stored on `product.disclaimers`.
  - Stored in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11124-11125`, `mos/backend/app/routers/clients.py:11162-11172`
- Why it exists:
  - This is reusable compliance language for product/context-aware generators.
- Active downstream use:
  - Final Strategy V2 winner selection merges onboarding disclaimers into `compliance_notes`.
  - Source: `mos/backend/app/temporal/activities/strategy_v2_activities.py:9016-9053`
- Additional downstream use:
  - Included in design-system context, Shopify theme context, Funnel AI product serialization, and swipe product serialization.
  - Source: `mos/backend/app/temporal/activities/client_onboarding_activities.py:313-315`, `mos/backend/app/services/shopify_theme_content_planner.py:236-240`, `mos/backend/app/services/funnel_ai.py:4229-4232`, `mos/backend/app/temporal/activities/swipe_image_ad_activities.py:1283-1286`

#### `goals`

- UI/API requirement:
  - No longer collected in the onboarding wizard.
- Persistence:
  - Stored only in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11162-11172`
- Why it exists:
  - Meant to capture business intent beyond the core Strategy V2 operator inputs.
- Current downstream use:
  - Secondary reader only: legacy metric-schema heuristics inspect goals.
  - Secondary reader only: design-system generation includes goals in prompt context.
  - Source: `mos/backend/app/temporal/activities/client_onboarding_activities.py:94-105`, `mos/backend/app/temporal/activities/client_onboarding_activities.py:284-320`
- Current assessment:
  - Helpful context, but not part of the active Strategy V2 contract.

#### `competitor_urls`

- UI/API requirement:
  - Optional, but validated when present.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:396-414`, `mos/backend/app/schemas/onboarding.py:32-46`
- Persistence:
  - Stored only in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11162-11172`
- Why it exists:
  - Seeds competitor discovery and ads-context ingestion instead of forcing the system to discover competitors from scratch.
- Active downstream use:
  - Stage 0 translation carries `competitor_urls` into the initial product brief.
  - Foundational research uses them as `seed_refs` for ingestion.
  - Stage 1 merges them with discovered competitor URLs and requires at least 3 validated competitors.
  - Later H2 asset prep also expects competitor URLs to exist in stage 1.
  - Source: `mos/backend/app/strategy_v2/translation.py:441-464`, `mos/backend/app/strategy_v2/translation.py:518-564`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:8632-8669`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:16837-16840`
- Secondary use:
  - Included in design-system context.
  - Source: `mos/backend/app/temporal/activities/client_onboarding_activities.py:284-319`

#### `primary_image_file`

- UI/API requirement:
  - No longer collected in the onboarding wizard.
  - Not part of `OnboardingStartRequest`.
- Persistence:
  - Uploaded separately to `POST /products/{product_id}/assets`.
  - Then assigned to `product.primary_asset_id` via `PATCH /products/{product_id}`.
- Why it exists:
  - This is the visual reference for downstream creative/template generation and campaign launch readiness. It is not needed to create the product/offer/variant records themselves.
- Active downstream use:
  - Funnel AI collects product image asset public IDs and fails if none exist.
  - Testimonial hero image generation requires a primary product image.
  - Swipe image ad generation may require active source product images.
  - Shopify theme image generation can require approved product images for product visual context.
  - Strategy Hub launch now blocks until the product has a ready primary image.
- Current assessment:
  - This requirement belongs at launch time, not onboarding time.

### Strategy V2 Operator Step

#### `product_customizable`

- UI/API requirement:
  - Required by the API schema as a boolean.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:366-377`, `mos/backend/app/schemas/onboarding.py:15`
- Persistence:
  - Stored in `onboarding_payload.data`.
  - Carried into Strategy V2 stage artifacts.
  - It is **not** stored on the product record.
  - Source: `mos/backend/app/routers/clients.py:11162-11172`, `mos/backend/app/strategy_v2/translation.py:448-465`
- Why it exists:
  - It tells the Offer Agent whether it may recommend changing the product itself or must work with a fixed product.
- Active downstream use:
  - Stage 0 translation throws if this field is missing.
  - Offer pipeline maps it into `product_brief.product_customizable`.
  - Offer Agent prompts branch on it:
    - Step 03 changes mechanism logic depending on whether the product can be reshaped.
    - Step 04 requires or skips a product-shaping recommendations section based on it.
  - Source: `mos/backend/app/strategy_v2/translation.py:421-429`, `mos/backend/app/strategy_v2/translation.py:754-817`, `V2 Fixes/Offer Agent — Final/prompts/pipeline-orchestrator.md:32-40`, `V2 Fixes/Offer Agent — Final/prompts/step-03-ump-ums-generation.md:148-150`, `V2 Fixes/Offer Agent — Final/prompts/step-04-offer-construction.md:176-176`
- This is the answer to “why is product customizable needed?”:
  - Because the Strategy V2/Offer pipeline uses it as a hard constraint on what kinds of offers and product-shaping recommendations are valid.

#### `business_model`

- UI/API requirement:
  - Required.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:342-345`, `mos/backend/app/schemas/onboarding.py:16`
- Persistence:
  - Used immediately to create/update the compliance profile.
  - Stored on the default offer.
  - Passed into `ClientOnboardingWorkflow` and `StrategyV2Workflow`.
  - Stored in `onboarding_payload.data`.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:420-430`, `mos/backend/app/routers/compliance.py:364-397`, `mos/backend/app/routers/clients.py:11133-11148`, `mos/backend/app/routers/clients.py:11174-11189`
- Why it exists:
  - It is both a compliance/business identity field and an Offer Agent contract field.
- Active downstream use:
  - Offer pipeline refuses to run without it.
  - Offer product brief includes it.
  - Launch extraction later re-reads it from the v2-08 payload.
  - Source: `mos/backend/app/temporal/activities/strategy_v2_activities.py:17312-17324`, `mos/backend/app/strategy_v2/translation.py:779-783`, `mos/backend/app/strategy_v2/launches.py:247-257`

#### `funnel_position`

- UI/API requirement:
  - Required.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:346-348`, `mos/backend/app/schemas/onboarding.py:17`
- Persistence:
  - Passed into the onboarding and Strategy V2 workflows and stored in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11162-11189`
- Why it exists:
  - The Offer Agent needs to know whether it is building for cold traffic, retargeting, post-nurture, etc.
- Active downstream use:
  - Offer pipeline refuses to run without it.
  - Included in `product_brief`.
  - Launch extraction re-reads it later.
  - Source: `mos/backend/app/temporal/activities/strategy_v2_activities.py:17325-17329`, `mos/backend/app/strategy_v2/translation.py:784-788`, `mos/backend/app/strategy_v2/launches.py:247-257`

#### `target_platforms`

- UI/API requirement:
  - Required list.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:350-352`, `mos/backend/app/schemas/onboarding.py:18`
- Persistence:
  - Passed into the workflows and stored in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11162-11189`
- Why it exists:
  - The Offer Agent contract needs to know where the offer/copy will be used.
- Active downstream use:
  - Offer pipeline refuses to run without at least one platform.
  - Included in `product_brief`.
  - Launch extraction re-reads it later.
  - Source: `mos/backend/app/temporal/activities/strategy_v2_activities.py:17330-17335`, `mos/backend/app/strategy_v2/translation.py:789-793`, `mos/backend/app/strategy_v2/launches.py:228-257`

#### `target_regions`

- UI/API requirement:
  - Required list.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:354-356`, `mos/backend/app/schemas/onboarding.py:19`
- Persistence:
  - Passed into the workflows and stored in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11162-11189`
- Why it exists:
  - Regional targeting is part of the offer/copy context contract.
- Active downstream use:
  - Offer pipeline refuses to run without at least one region.
  - Included in `product_brief`.
  - Launch extraction re-reads it later.
  - Source: `mos/backend/app/temporal/activities/strategy_v2_activities.py:17337-17342`, `mos/backend/app/strategy_v2/translation.py:794-798`, `mos/backend/app/strategy_v2/launches.py:228-257`

#### `existing_proof_assets`

- UI/API requirement:
  - Required list.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:358-360`, `mos/backend/app/schemas/onboarding.py:20`
- Persistence:
  - Passed into the workflows and stored in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11162-11189`
- Why it exists:
  - The Offer Agent is explicitly told not to fabricate proof and to build the offer around proof that already exists.
- Active downstream use:
  - Offer pipeline refuses to run without it.
  - Included in `product_brief.constraints.existing_proof_assets`.
  - Prompt docs explicitly reference it when constructing proof strategy.
  - Launch extraction re-reads it later.
  - Source: `mos/backend/app/temporal/activities/strategy_v2_activities.py:17344-17349`, `mos/backend/app/strategy_v2/translation.py:806-810`, `mos/backend/app/strategy_v2/launches.py:230-257`, `V2 Fixes/Offer Agent — Final/prompts/step-01-avatar-brief.md:131-136`, `V2 Fixes/Offer Agent — Final/prompts/step-04-offer-construction.md:170-176`
- This is the answer to “why are proof assets needed?”:
  - Because the offer logic is supposed to use real proof, not invented proof.

#### `brand_voice_notes`

- UI/API requirement:
  - Required.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:362-364`, `mos/backend/app/schemas/onboarding.py:21`
- Persistence:
  - Passed into the workflows and stored in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11162-11189`
- Why it exists:
  - Strategy V2 uses it as a hard copy-style constraint, not as a nice-to-have note.
- Active downstream use:
  - Offer pipeline refuses to run without it.
  - Included in `product_brief.constraints.brand_voice_notes`.
  - If the explicit runtime param is empty during offer-winner finalization, Strategy V2 falls back to the onboarding payload value.
  - It is injected into final copy-context files.
  - Source: `mos/backend/app/temporal/activities/strategy_v2_activities.py:17351-17365`, `mos/backend/app/strategy_v2/translation.py:811-815`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:8995-9013`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:19142-19197`

#### `compliance_notes`

- UI/API requirement:
  - Optional.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:985-994`, `mos/backend/app/schemas/onboarding.py:22`
- Persistence:
  - Saved into compliance-profile metadata during the frontend pre-submit step.
  - Passed into the workflows when non-empty.
  - Stored in `onboarding_payload.data`.
  - Source: `mos/frontend/src/components/clients/OnboardingWizard.tsx:423-429`, `mos/backend/app/routers/clients.py:11162-11189`
- Why it exists:
  - It lets the operator add explicit legal/compliance guardrails beyond structured rules and product disclaimers.
- Active downstream use:
  - Offer winner finalization merges these notes with onboarding disclaimers, stage-2 compliance constraints, and a standard “avoid absolute guarantees” rule to build final `compliance_notes` for copy context.
  - Source: `mos/backend/app/temporal/activities/strategy_v2_activities.py:9016-9053`, `mos/backend/app/temporal/activities/strategy_v2_activities.py:19147-19197`

#### `funnel_notes`

- UI/API requirement:
  - No longer collected in the onboarding wizard.
- Persistence:
  - Stored only in `onboarding_payload.data`.
  - Source: `mos/backend/app/routers/clients.py:11162-11172`
- Why it exists:
  - Free-form extra context.
- Current downstream use:
  - Secondary reader only: design-system generation includes it in prompt context.
  - Source: `mos/backend/app/temporal/activities/client_onboarding_activities.py:286-320`, `mos/backend/app/services/design_system_generation.py:148-156`
- Current assessment:
  - This is not a core active Strategy V2 contract field today.

## What Is Actually Critical Today

If the goal is to keep only fields that are clearly justified by the current active onboarding path, the strongest fields are:

- `brand_story`
- `product_name`
- `product_description`
- `price`
- `product_type`
- `product_customizable`
- `business_model`
- `funnel_position`
- `target_platforms`
- `target_regions`
- `existing_proof_assets`
- `brand_voice_notes`
- `competitor_urls` if you want seeded competitor research instead of discovery-from-scratch

The weaker / more secondary-context fields in the current implementation are:

- `client_industry`
- `product_category`
- `goals`
- `funnel_notes`
- `business_type` beyond gating `"new"` vs `"existing"`

## Short Answers To The Two Examples

### Why is `product_customizable` needed?

Because the Offer Agent treats it as a hard decision boundary:

- if `true`, it can recommend changing the product itself,
- if `false`, it must keep the product fixed and only change framing/offer structure.

If it is missing, Stage 0 translation fails. The prompt set also branches on it for UMS generation and offer construction.

### Why is the primary product image needed?

Not because the onboarding POST itself needs it. The backend can start onboarding without the image.

It is needed because later asset-driven systems expect a real product image:

- Funnel AI product-image overrides,
- testimonial hero rendering,
- swipe-image-ad reference selection,
- Shopify theme image generation / image-slot planning.

Strategy Hub now enforces that requirement right before campaign launch, which is the point where those downstream systems actually become relevant.
