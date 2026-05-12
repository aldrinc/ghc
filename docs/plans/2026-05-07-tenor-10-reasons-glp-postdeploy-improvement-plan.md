# Tenor 10 Reasons GLP Postdeploy Improvement Plan

## Decision

Keep the route-scoped deployment live. The deployed listicle page passed the image, route hash, PostHog ingestion, Meta harness, and sales-page hash-safety checks. Create a follow-up implementation patch because mobile Lighthouse scored 84, below the 85+ bar, and strict RMBC validation found analytics field-level misses.

## Evidence

- Deployed route: `https://shoptenorco.com/8b89a76d/daily-drive-essentials/10-reasons-glp/`
- Deployed route hash: `8680aad83fd55f769982634b6c63ff00b08009a9eb656b945b00cff82208eacf`
- Sales page hash remained unchanged: `f5e9a9ef80d0eb1c6f46dbb4828feef71c8320c92fa39fbdf5ec4f2ada26550a`
- Local and live listicle image validation: 17 visible images, 0 broken.
- Live asset HEAD validation: 40 checked, 0 bad.
- PostHog API readback for the validation token returned 35 events.
- Meta harness attempted `EnteredPresales` and `PreSalesToSalesClick` with outbound Facebook requests blocked during validation.
- Lighthouse: mobile 84, desktop 100.

## Tracking Fixes

1. Add a normalized `click_id` common property.
   - Derive it from the best available inbound attribution parameter, in this order: `fbclid`, `gclid`, `gbraid`, `wbraid`, `msclkid`, `ttclid`, `twclid`, `nbt`.
   - Keep the raw platform IDs as top-level properties and inside `url_params`.
   - Error during validation if a click ID parameter is present but normalized `click_id` is missing.

2. Add `depth_pct` to `section_view`.
   - Current events include `scroll_depth_pct`, but the RMBC presell spec calls out `depth_pct`.
   - Set `depth_pct` to the current scroll percent at the moment the section intersects.
   - Preserve `scroll_depth_pct` for compatibility.

3. Extend the HTML deploy analytics validator.
   - Validate required fields by artifact type: `listicle`, `listicle_hybrid`, `quiz`, `sales`.
   - For listicle and listicle hybrid, require PostHog readback for `presell_page_view`, `scroll_depth`, `section_view`, `proof_view`, `cta_view`, `cta_click`, and `PreSalesToSalesClick`.
   - Require intercepted Meta validation for `EnteredPresales` and `PreSalesToSalesClick`.
   - Emit a human-readable failure report with the event name, missing field, observed count, and validation token.

## Performance Fixes

1. Add a mobile Lighthouse gate to `html-deploy-v1`.
   - Run mobile and desktop Lighthouse against the staged or postdeploy URL.
   - Fail production viability below 85 unless the deploy is explicitly approved as an exception.
   - Save JSON reports and summarize score, LCP, FCP, CLS, TBT, and top opportunities.

2. Reduce unused CSS in the deploy artifact.
   - Lighthouse reported about 88 KiB estimated unused CSS on mobile.
   - Add an artifact optimization step that removes unused CSS with a conservative safelist for runtime-generated classes, responsive breakpoints, footer/header classes, CTA classes, and analytics selectors.
   - The validator should run visual and event checks after CSS pruning, not before.

3. Protect mobile LCP.
   - Ensure the mobile hero/LCP image has explicit `width`, `height`, responsive `srcset`, `sizes`, `loading="eager"`, `decoding="async"`, and `fetchpriority="high"`.
   - Keep all below-the-fold reason images lazy.
   - Add a validator assertion that only the intended above-the-fold images are eager.

4. Add artifact budgets.
   - Warn above 500 KiB HTML.
   - Fail above 750 KiB HTML unless explicitly approved.
   - Fail any single above-the-fold image above the configured mobile budget.

## Downstream Sales Page Follow-Up

The listicle deploy did not alter the sales page, but the end-to-end browser run exposed existing downstream sales-page issues:

- One visible broken sales-page image: `accelerated_btn_greens-fb332e3ac7-5bfd774127.webp`
- Sales-page script errors from Shopify product scripts and one `Cannot use import statement outside a module` error.

These should be handled in a separate sales-page cleanup patch because they affect the user journey after the listicle CTA, but they were not introduced by this deployment.

## Acceptance Criteria

- Mobile Lighthouse score is `>= 85`; desktop remains `>= 85`.
- PostHog API readback has all required RMBC listicle events with no missing required fields.
- Meta harness validation shows `EnteredPresales` and `PreSalesToSalesClick`.
- Listicle visible-image validation remains at 0 broken images on desktop and mobile.
- Sales page hash-safety guard remains in place for listicle-only deploys.
- Backup path and rollback command are emitted for every production deploy.
