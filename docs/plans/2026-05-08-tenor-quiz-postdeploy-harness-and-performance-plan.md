# Tenor Quiz Postdeploy Harness And Performance Plan

## Decision

Keep the deployed quiz hotfix in place. The production quiz now removes the legacy Mars/MenGoToMars footer after Replo/Heyflow renders, preserves the quiz tracking contract, and leaves the existing listicle and sales page unchanged.

The next implementation work should harden `html-deploy-v1` so this class of issue is caught automatically, then address mobile Lighthouse performance without changing the visual design.

## Deployed State

- URL: `https://shoptenorco.com/8b89a76d/daily-drive-essentials/quiz/`
- Final quiz artifact SHA256: `87d41d5a6bad731107a6c3eb6d3d3324ad9983e82e30ee6ecade99aede7f1933`
- Final release: `/opt/apps/brand-funnels-70124684-be65d76e/site-releases/20260508T161731Z-tenor-quiz-rmbc-harness-v5-footer-fix`
- Rollback backup: `/opt/apps/brand-funnels-70124684-be65d76e/backups/html-deploy-v1/quiz-before-rmbc-v5-footer-fix-20260508T161731Z.tgz`
- Previous v5 backup: `/opt/apps/brand-funnels-70124684-be65d76e/backups/html-deploy-v1/quiz-before-rmbc-v5-20260508T161025Z.tgz`
- Sales page SHA preserved: `7b64525154bc0dcb957f599b0132650e384e10fcdb0ffc14d061754559f738a2`
- Existing listicle SHA preserved: `2ace72021f170d32acd8b801ca5596cbddd124ea09bbfae35025934aa4634bbc`

## Validation Results

- Static HTML scan: no legacy Mars/MenGoToMars strings, old quiz hardwire blocks, old Mars bundle references, or `EnteredSales`.
- Remote quiz directory scan: only `index.html` plus the three expected quiz image files were present.
- Post-render browser scan: no forbidden DOM attributes, DOM snippets, or network requests after waiting for Replo/Heyflow to render.
- Images: all three quiz images returned `200` from the live URL.
- Analytics: required quiz RMBC/PostHog events fired, Meta emitted only `EnteredPresales` and `PreSalesToSalesClick`, and `EnteredSales` did not fire on quiz load or the final quiz CTA.
- Final CTA bridge: destination URL included `rmbc_session_id`, `rmbc_click_id`, `rmbc_quiz_id=5U9hkq9MFvvXQA8VV654`, UTMs, result/segment/offer fields, and answer hash.

Validation artifacts:

- `.local/server-pulls/tenor-quiz-live-rmbc-v5-validation-20260508T161731Z.json`
- `.local/server-pulls/tenor-quiz-live-forbidden-dom-debug-20260508T161731Z.json`
- `.local/server-pulls/live-tenor-quiz-after-rmbc-v5-footer-fix-20260508T161731Z.html`
- `.local/server-pulls/tenor-quiz-live-rmbc-v5-mobile-20260508T161731Z.png`

## Open Issues

1. **Mobile Lighthouse is below target.**
   - Mobile performance score: `49`
   - Desktop performance score: `91`
   - Mobile FCP: `6.8s`
   - Mobile LCP: `9.9s`
   - Mobile TBT: `420ms`
   - Mobile main-thread work: `4.8s`

2. **Non-quiz third-party app warning remains.**
   - The browser console reports `Alia launcher` merchant lookup failures.
   - This did not break quiz tracking, but the deploy harness should classify it separately from quiz analytics failures.

3. **The current deployed fix is artifact-local.**
   - The sanitizer now removes the legacy injected footer, but `html-deploy-v1` should own this as a reusable validation and cleanup rule for quiz deployments.

## Implementation Plan

### 1. Add Forbidden-Origin Gates To `html-deploy-v1`

- Add a static source scan before deployment.
- Add a post-render browser scan after deployment preview.
- Scan HTML source, live DOM attributes/text, script-injected DOM, and observed request URLs.
- Fail deployment on legacy brand origins, legacy pixel IDs, old hardwire analytics blocks, and forbidden quiz events.
- Store the forbidden patterns in deploy validation config so the shipped artifact never contains the literal forbidden domain as sanitizer source text.

Acceptance criteria:

- A quiz artifact with a post-render legacy footer fails validation.
- A quiz artifact with only the current sanitizer passes validation.
- Validation report lists the exact DOM node or request URL that caused failure.

### 2. Promote The Quiz Legal/Footer Sanitizer

- Move the current artifact-local legacy footer remover into the quiz shell builder.
- Remove legacy Replo legal/footer blocks from the DOM instead of only hiding them.
- Keep the Tenor footer visually unchanged.
- Add a regression test that loads the quiz with a synthetic injected legacy footer and confirms the final DOM is clean.

Acceptance criteria:

- No legacy legal links remain in `outerHTML` after Replo/Heyflow render.
- The clean Tenor footer appears once.
- Existing page screenshots remain visually equivalent except for removal of the legacy footer content.

### 3. Harden Quiz Analytics Validation

- Enforce the quiz event matrix:
  - Required: `EnteredPresales`, `QuizLeadViewed`, `QuizQuestionViewed`, `QuizOptionPresented`, `QuizOptionSelected`, `QuizQuestionSubmitted`, `QuizCompleted`, `QuizResultViewed`, `QuizRecommendationViewed`, `QuizCtaViewed`, `PreSalesToSalesClick`.
  - Forbidden on quiz: `EnteredSales`.
  - Meta allowed on quiz: `EnteredPresales`, `PreSalesToSalesClick`.
- Assert PostHog payloads use the canonical quiz source.
- Assert final CTA bridge parameters before navigation.
- Separate core quiz failures from unrelated third-party console warnings.
- Add optional PostHog dashboard readback only when a read-capable PostHog API key is explicitly supplied.

Acceptance criteria:

- Final quiz CTA cannot trigger `EnteredSales`.
- Missing or extra Meta events fail validation.
- Validation output names the failing event surface: RMBC, PostHog, Meta, Shopify/dataLayer, or browser DOM.

### 4. Mobile Performance Rework

- Convert the large quiz assets to responsive AVIF/WebP and keep JPEG/PNG fallbacks.
  - `tenor-quiz-listicle-reason-10.jpg`: about `895KB`
  - `t-level-decline-red-desktop.png`: about `809KB`
  - `t-level-decline-red-mobile.png`: about `767KB`
- Lazy-load offscreen final/result imagery and avoid fetching desktop-only assets on mobile.
- Preconnect/preload only the critical Heyflow assets needed for first paint.
- Defer Replo, Meta Pixel, Alia, axios, and other non-critical scripts until after first paint or first interaction while preserving event queues.
- Remove or gate the Alia extension on quiz pages if it is not required for the funnel.
- Trim unused Shopify/Replo/Alchemy CSS and JS from the standalone quiz artifact.
- Keep visual screenshots locked against the current production look.

Acceptance criteria:

- Mobile Lighthouse reaches `85+`.
- Desktop remains `85+`.
- No visual regression at mobile and desktop viewport captures.
- Analytics validation still passes after script deferral.

## Recommended Next Step

Implement items 1 through 3 first because they prevent bad deployments. Then run the mobile performance rework behind screenshot diff and analytics validation gates.
