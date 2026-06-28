# Campaign Publish Recovery Plan

## Decision

Do not publish the current creative package as-is. The lander/sales-page fixes help, but the blocking issues are now primarily in the ads themselves. The whole-campaign representative QA found that `80 / 83` logical ad groups require image regeneration or exclusion because the image creative itself carries true-positive policy risk.

The publishable path is a clean v4 package:

1. Fix the MOS landing-page snapshot bug so external ShopTenor pages are fetched as live HTML.
2. Rewrite the reusable copy units into neutral, non-personal, non-hidden-cause language.
3. Regenerate the failing image groups with a strict compliant creative brief.
4. Re-run representative QA once per logical group.
5. Publish a fresh Meta review draft with campaign off, ad sets/ads on in draft, U.S. only, start time 12:01 next day.

## Current QA Facts

- Logical groups audited: `83 / 83`
- Raw findings: `418`
- Adjusted findings after deduping repeated account check: `336`
- Likely true positives: `237`
- Confirmed false positives: `86`
- Likely false positives: `12`
- Needs review: `1`

## What Is Actually Blocking Ads

### Image-level blockers

`80 / 83` groups have `META-IMAGE-001` true positives. These cannot be fixed by changing primary text/headlines.

Common image problems:

- Doctor/lab coat/stethoscope/medical-scan authority cues
- Fake editorial, news, report, specialist, or research layouts
- Before/after body transformation framing
- Direct callouts like energy, drive, focus, stamina, not yourself, over 40
- Click-to-reveal, quiz-diagnosis, hidden reason, overlooked cause presentation
- Testimonial-style health bait

Action: regenerate or exclude. Do not reuse these images.

### Copy-level blockers

All reusable copy families need replacement or heavy rewrite:

- GLP: `COPY001`, `COPY002`, `COPY003`
- Quiz: `COPY011`, `COPY012`, `COPY013`, `COPY014`, `COPY015`, `COPY016`, `COPY017`, `COPY018`

Common copy problems:

- `you/your` tied to GLP use, prescription status, body, age, symptoms, energy, drive, stamina
- Hidden-cause language: secretly, quietly drain, overlooked reason, find out why, no one mentions
- Fake-authority or doctor framing
- Negative self-perception/body-shaming language
- Unsupported result certainty and survey/result framing

Action: rewrite once per copy unit, then reuse across matching destination only.

### Landing-page false positives

`META-LP-005`, `META-LP-006`, and likely `META-LP-007` are not reliable until MOS snapshot routing is fixed.

Root cause: production QA parses `shoptenorco.com/8b89a76d/daily-drive-essentials/...` as a MOS public funnel route and uses `inspectionSource: public_funnel_api` instead of fetching the live HTML. Direct live checks found privacy/contact/support on both GLP and quiz pages.

Action: fix snapshot routing before rerunning final QA.

### Account readiness needs review

`META-ACCOUNT-008` is one account/profile issue repeated across group-level runs.

MOS tracking is active, but the helper requires `SalesToCheckoutClick`. Current browser events include `Entered Funnel`, `PageView`, `ViewContent`, `PreSalesToSalesClick`, `AddToCart`, `Purchase`.

Action: decide whether to update the event contract for external-URL campaigns or add the expected event.

## Fastest Publishable Path

### Step 1: Patch MOS QA false positives

Code fix:

- Only use `_load_public_funnel_snapshot()` for MOS-managed public funnel hosts/routes.
- For external storefront domains like `shoptenorco.com`, use direct live HTTP fetch.
- Add test coverage showing ShopTenor external URLs are not parsed as MOS public-funnel API routes.
- Improve `META-ACCOUNT-008` evidence to list required, present, and missing events.

### Step 2: Create compliant copy replacements

Replace the current copy units with neutral versions.

Rules for rewritten copy:

- Testosterone is allowed as general category/product language.
- Do not say or imply `your testosterone`, `your GLP-1`, `your doctor`, `your prescription`, `your body`, `your energy`, `your drive`, or `your symptoms`.
- Do not claim hidden causes, secret effects, doctor omissions, or diagnostic quiz outcomes.
- Do not use shame/body-insecurity framing.
- Do not use fake research/news/doctor authority.
- Keep offer language simple: `52% off limited-time welcome offer`, `$35 welcome kit`, `90-day guarantee` where applicable.

Suggested GLP copy posture:

- General educational advertorial angle.
- Example direction: `A short guide for men comparing daily wellness support alongside modern weight-management routines.`
- CTA: `Read the guide` / `Learn more`.

Suggested quiz copy posture:

- Neutral routine preference quiz, not diagnostic/personalized health profile.
- Example direction: `Answer a few routine-preference questions and see how Daily Drive Essentials fits into a daily wellness routine.`
- CTA: `Take the quiz`.

### Step 3: Regenerate image package

Regenerate all groups with image true positives. That is effectively the whole package except three groups that could theoretically be copy-only fixed, but for consistency those should be regenerated too if they share risky copy families.

Image rules:

- No doctor/lab coat/stethoscope/medical-scan imagery.
- No before/after body comparison.
- No fake news, fake article, report, specialist, study, or research-style layouts.
- No direct personal callouts in on-image text.
- No hidden-cause or click-to-reveal framing.
- No shame or negative self-perception framing.
- Curated set: no product reference unless explicitly required by the approved reference.
- Tenor package: include product reference only for product-bearing source references.
- Use Tenor red `#ee1f2d`; avoid source orange.

Safe image directions:

- Clean product/offer visual where product reference is allowed.
- Neutral lifestyle routine scenes without symptom callouts.
- Ingredient/process visuals without medical authority cues.
- Simple offer card creative with `52% off limited-time welcome offer`, `$35 welcome kit`, and `90-day guarantee` where applicable.
- Editorial-looking should be avoided entirely for this recovery batch.

### Step 4: Rebuild Meta draft specs in MOS

Use the existing MOS campaign, but prepare a fresh review/publish version.

- Keep five ad sets.
- Keep U.S. only.
- Keep CBO.
- Keep start time defaulted to 12:01 AM next day.
- Keep campaign off.
- Keep ad sets and ads configured on, but in draft/not live.
- Remove or supersede the old creative specs/ad drafts tied to failing images.
- Do not reuse rejected Meta ad IDs; prepare fresh draft ads.

### Step 5: QA gate before Meta publish

Run QA in this order:

1. Landing-page snapshot sanity check for GLP and quiz live HTML.
2. Representative policy QA once per logical ad group.
3. Full paid ads QA gate on the selected generation key.
4. Meta review setup validator.
5. Publish draft to Meta only if policy QA passes or approved exceptions are explicitly documented.

## Practical Launch Recommendation

Do not try to save the current image set. The fastest safe path is to regenerate a clean v4 creative package with safer copy and image rules, then publish that package as a fresh Meta draft for review.

If timing is critical, launch a smaller first batch:

- 5 ad sets
- 2 to 3 clean concepts per destination
- 1 representative creative per concept with 1:1, 4:5, 9:16 siblings
- No risky editorial/medical/before-after formats

Then scale once Meta review clears.
