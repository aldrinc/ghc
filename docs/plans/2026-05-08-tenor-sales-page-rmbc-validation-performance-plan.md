# Tenor Sales Page RMBC Validation And Performance Plan

## Decision

Use the deployed sales page as the live validation baseline, but do not call the reusable sales-page deploy flow complete until the missing harness and production-quality gates below are implemented.

The production route now proves that the required sales events can fire and land in PostHog, and that the required Meta events are emitted. The remaining work is to make that validation automatic for every future sales artifact, fix the missing first-class attribution fields, and make performance/accessibility/best-practices failures block deploys before a page is considered production viable.

## Current Artifact

- Source: `/Users/auggieclement/Documents/GitHub/ghc/.local/tenor-sales-speed-optimized-v2-deploy/index.html`
- Intended production route: `https://shoptenorco.com/8b89a76d/daily-drive-essentials/sales-page/`
- Required analytics reference: `/Users/auggieclement/Downloads/rmbc-sales-page-metrics-framework.md`
- Required Meta sales events: `EnteredSales`, `SalesToCheckoutClick`
- Production backup created before deploy: `/opt/apps/brand-funnels-70124684-be65d76e/backups/html-deploy-v1/sales-page-before-20260508T024244Z.tgz`
- Latest redeploy backup: `/opt/apps/brand-funnels-70124684-be65d76e/backups/html-deploy-v1/sales-page-before-20260508T030227Z.tgz`
- Latest deployed source hash: `7cd5f7d5c37111204f571c7f98a89d17f8e37b70e449960a0bd6817098b6c3ca`

## Validation Evidence

- Local predeploy validation: `/Users/auggieclement/Documents/GitHub/ghc/.local/server-pulls/tenor-sales-speed-v2-predeploy-validation.json`
- Local checkout-flow validation with modal closed: `/Users/auggieclement/Documents/GitHub/ghc/.local/server-pulls/sales_checkout_close_modal_1778207223064.json`
- Mobile Lighthouse: `/Users/auggieclement/Documents/GitHub/ghc/.local/server-pulls/tenor-sales-lighthouse-mobile-1778207223064.json`
- Desktop Lighthouse: `/Users/auggieclement/Documents/GitHub/ghc/.local/server-pulls/tenor-sales-lighthouse-desktop-1778207223064.json`
- Live browser analytics and image validation: `/Users/auggieclement/Documents/GitHub/ghc/.local/server-pulls/sales_live_rmbc_1778208322541.json`
- Live PostHog readback: `/Users/auggieclement/Documents/GitHub/ghc/.local/server-pulls/sales_live_rmbc_1778208322541-posthog-readback.json`
- Live mobile Lighthouse: `/Users/auggieclement/Documents/GitHub/ghc/.local/server-pulls/tenor-sales-live-lighthouse-mobile-sales_live_lh_1778208322541.json`
- Live desktop Lighthouse: `/Users/auggieclement/Documents/GitHub/ghc/.local/server-pulls/tenor-sales-live-lighthouse-desktop-sales_live_lh_1778208322541.json`
- Latest redeploy browser analytics and image validation: `/Users/auggieclement/Documents/GitHub/ghc/.local/server-pulls/sales_redeploy_rmbc2_20260508T030227Z.json`
- Latest redeploy PostHog readback: `/Users/auggieclement/Documents/GitHub/ghc/.local/server-pulls/sales_redeploy_rmbc2_20260508T030227Z-posthog-readback.json`
- Latest redeploy mobile Lighthouse: `/Users/auggieclement/Documents/GitHub/ghc/.local/server-pulls/tenor-sales-live-lighthouse-mobile-sales_redeploy_lh_20260508T030227Z.json`
- Latest redeploy desktop Lighthouse: `/Users/auggieclement/Documents/GitHub/ghc/.local/server-pulls/tenor-sales-live-lighthouse-desktop-sales_redeploy_lh_20260508T030227Z.json`

## Analytics Status

Live desktop and mobile validation pass the required direct PostHog sales-page event sequence once the Mars offer modal is closed before clicking the primary CTA.

Direct PostHog capture observed:

- `sales_page_view`
- `offer_page_view`
- `qualified_session`
- `scroll_depth`
- `section_view`
- `proof_view`
- `cta_view`
- `offer_stack_view`
- `trust_element_view`
- `guarantee_view`
- `selector_interaction`
- `subscription_selected`
- `AddToCart`
- `SalesToCheckoutClick`
- `purchase_intent_click`

Meta pixel beacons observed:

- `PageView`
- `EnteredSales`
- `AddToCart`
- `SalesToCheckoutClick`

Earlier generic MOS bridge validation observed these event names before the latest redeploy:

- `sales_page_view`
- `offer_page_view`
- `qualified_session`
- `scroll_depth`
- `cta_view`
- `sales_to_checkout_click`
- `checkout_started`

Latest PostHog readback observed `42` matching events for validation token `sales_redeploy_rmbc2_20260508T030227Z`, including:

- `sales_page_view`: `2`
- `AddToCart`: `2`
- `SalesToCheckoutClick`: `2`
- `purchase_intent_click`: `2`

The latest browser pass observed Meta event names and event IDs, but the Meta custom-data payloads are empty. The harness must now fail when `event_source_url`, `value`, and `currency` are missing from Meta checkout-intent beacons.

The latest browser pass did not observe healthy MOS bridge delivery because `/api/public/events` returned `502`; the harness must not count MOS bridge events as healthy until the endpoint returns 2xx.

Image validation observed `0` visible broken images on desktop and mobile.

## Current Blockers

1. Campaign/ad attribution fields are not promoted to top-level PostHog properties.
   - Latest live readback for `sales_redeploy_rmbc2_20260508T030227Z` confirmed required sales events landed in PostHog.
   - `campaign_id`, `adset_id`, `ad_id`, `creative_id`, and `experiment_id` are present inside `url_params`, but they are `null` as top-level PostHog properties.
   - The harness should promote those URL params to first-class properties on every sales event so RMBC reporting can segment without JSON extraction.

2. Meta event names fire, but Meta custom-data payloads are empty on the latest artifact.
   - Browser validation saw `PageView`, `EnteredSales`, `AddToCart`, and `SalesToCheckoutClick`.
   - The pixel requests include event IDs, but `cd` was empty for the required sales events.
   - `EnteredSales` is missing `event_source_url`.
   - `AddToCart` and `SalesToCheckoutClick` are missing `event_source_url`, `value`, and `currency` in Meta custom data.
   - This is a tracking-quality regression versus the prior validation and must be fixed in the sales harness/page patching layer.

3. MOS bridge delivery is not healthy.
   - Latest desktop and mobile browser validation observed repeated `https://shoptenorco.com/api/public/events` `502` responses.
   - Direct PostHog events landed despite the bridge failure, but the deploy flow should not mark MOS bridge validation as passed until the endpoint is 2xx and emits `sales_to_checkout_click` and `checkout_started`.

4. Mobile Lighthouse is still below the `85+` target.
   - Latest live mobile performance is `66`.
   - Main mobile misses: FCP `2.9 s`, LCP `8.7 s`, Speed Index `5.6 s`, and TTI `8.9 s`.
   - Remaining mobile optimization opportunities: `188 KiB` properly sized image savings, `259 KiB` offscreen image savings, `60 KiB` unused CSS savings, `98 KiB` unused JS savings, `3,235` DOM nodes, and missing mobile preconnect hints.
   - Production compression is working, so compression is no longer the primary blocker.

5. Desktop performance regressed and is now below the `85+` target.
   - Latest live desktop performance is `64`.
   - Desktop CLS is `0.939`, which is the largest new performance regression and must be treated as a blocker.
   - Desktop LCP is `2.1 s`, with `241 KiB` properly sized image savings, `59 KiB` unused CSS savings, `86 KiB` unused JS savings, `3,060` DOM nodes, and missing preconnect hints.
   - Latest live desktop accessibility is `91`, best practices is `74`, and SEO is `92`.

6. Browser console errors and API bridge errors are still present.
   - `Cannot read properties of null (reading 'getAttribute')` from Shopify theme script.
   - `Cannot use import statement outside a module`.
   - `Cannot read properties of null (reading 'setAttribute')` from product form/product info scripts.
   - `[StandaloneImportedHtmlArtifact] Binding 'sales-shopbar-link' selector 'a.js-essentials-pro-bar-cta' matched no elements.`
   - Live Lighthouse also observed repeated `https://shoptenorco.com/api/public/events` `502` responses.
   - These do not block the required PostHog/Meta events after modal close, but they are production-quality issues and Lighthouse flags them.

7. Accessibility and SEO misses are not yet part of the deploy gate.
   - Review dots use invalid `aria-selected` attributes without compatible tab roles.
   - A `tablist` wrapper contains plain buttons instead of required tab children.
   - Footer headings use `role="button"` on incompatible heading elements.
   - Several red/blue CTA and pill treatments miss contrast thresholds.
   - Review dots are too small for touch target requirements.
   - Some footer links have no discernible accessible name.
   - Header menu anchors use `href="javascript:void(0)"`, which Lighthouse flags as not crawlable.
   - The charset declaration is missing or appears too late in the HTML.

8. The Mars offer modal blocks the primary CTA in automated and real interaction flow until closed.
   - This appears intentional, but validation must explicitly test both modal-visible and modal-closed states.
   - The latest artifact uses `[data-tenor-mars-offer-close]`, so the reusable harness must include that selector.
   - The sales harness should treat the modal close path as part of the required checkout validation path.

## Lighthouse Status

Latest live Lighthouse against production:

- Mobile: `66` performance, `93` accessibility, `75` best practices, `92` SEO.
- Desktop: `64` performance, `91` accessibility, `74` best practices, `92` SEO.

Mobile and desktop are both below the `85+` performance target. The latest desktop regression is driven mainly by CLS `0.939`.

Production gzip/Brotli is working. The deploy flow should keep compression verification, but the next performance work should focus on mobile LCP/TTI, image sizing/lazy loading, DOM size, and unused CSS/JS.

## Implementation Plan

### 1. Add A Sales RMBC Predeploy Gate

Build a sales-page harness validation command that loads the artifact locally and fails on:

- Missing direct PostHog capture for required RMBC sales events.
- Missing Meta `EnteredSales` or `SalesToCheckoutClick`.
- Missing Meta event IDs, missing `event_source_url`, or missing `value`/`currency` on checkout-intent events.
- Empty Meta custom-data payloads on required sales events.
- Missing MOS bridge `sales_to_checkout_click` or `checkout_started`.
- Any non-2xx response from the MOS analytics bridge such as `/api/public/events`.
- Visible broken images.
- Browser console errors, once the existing Shopify null/import errors are fixed.
- Checkout URL missing UTM, click ID, visitor/session, `cta_id`, transition, selected pack, and subscription attributes.

The gate should exercise:

- Page load.
- Scroll milestones and view targets.
- Plan selector changes.
- Modal-visible state.
- Modal close action.
- `[data-tenor-mars-offer-close]` and any future route-specific modal close selectors.
- Primary sales CTA click.
- Cart drawer checkout click with outbound checkout navigation safely intercepted during validation.

### 2. Add A PostHog Readback Gate

After live deploy, query PostHog by a unique `codex_validation` token and require:

- `sales_page_view`
- `AddToCart`
- `SalesToCheckoutClick`
- `purchase_intent_click`
- Required common properties from the RMBC spec, including `session_id`, `anonymous_id` or visitor ID, `click_id`, `page_id`, `page_type`, `page_variant`, `traffic_source`, `campaign_id`, `adset_id`, `ad_id`, `creative_id`, `offer_id`, `sku`, `price_point`, `bundle_id`, and `subscription_flag`.

If the personal API key is invalid, the command should stop with a clean error that says readback authentication failed.

Also validate property placement, not only property presence:

- Promote and assert top-level `campaign_id`, `adset_id`, `ad_id`, `creative_id`, and `experiment_id`.
- Keep the full `url_params` object as supporting context, but do not rely on nested JSON for primary RMBC reporting dimensions.
- Fail the readback gate when required dimensions only exist in `url_params`.

### 2a. Fix Meta Sales Custom Data

Restore Meta custom-data payloads for sales events:

- `EnteredSales` must include `event_source_url` and sales content category.
- `AddToCart` must include `event_source_url`, `content_category`, `cta_id`, `value`, and `currency`.
- `SalesToCheckoutClick` must include `event_source_url`, `content_category`, `cta_id`, `value`, and `currency`.
- All required Meta events must keep stable event IDs for dedupe with PostHog/server-side events.
- The validation harness must parse the `facebook.com/tr/` requests and fail if `cd` is empty.

### 3. Fix The Sales Artifact Runtime Errors

Patch or strip the Shopify-dependent scripts that assume missing DOM nodes exist inside the standalone HTML artifact:

- Add null guards around the `getAttribute` and `setAttribute` paths.
- Correct the script tag that throws `Cannot use import statement outside a module`.
- Remove or rebind the `sales-shopbar-link` instrumentation target so the standalone artifact does not log missing-selector errors.
- Fix `/api/public/events` `502` responses before allowing the MOS bridge to count as healthy.
- Re-run Playwright and Lighthouse until `errors-in-console` is green.

### 4. Make The Sales Artifact Mobile-First

To reach `85+` on mobile:

- Confirm production gzip/Brotli for HTML, CSS, and JS after CDN purge.
- Keep the production compression check, but treat it as a guard rather than the main optimization path because live compression is already passing.
- Prioritize the mobile LCP element with the correct mobile image candidate, `fetchpriority="high"`, and only one eager hero image.
- Add mobile `preconnect`/`dns-prefetch` hints for required third-party origins.
- Reduce the standalone HTML payload by pruning unused Shopify/theme CSS and JS for this route.
- Defer noncritical Shopify scripts, carousels, reviews, FAQ, flavor dropdown images, and modal content until interaction or viewport proximity.
- Keep required analytics available early, but use tiny direct beacons for required first-page events before loading heavier vendor scripts.
- Generate smaller responsive image candidates for the current rendered dimensions.
- Fix oversized thumbnail/image `sizes` definitions that cause 416w/768w assets to load where much smaller candidates would do.
- Lazy-load offscreen flavor dropdown thumbnails and non-critical product carousel images.
- Reduce DOM size from roughly `3,200` nodes toward a target under `1,500` by lazy-rendering reviews, hidden modal content, and non-visible product variants.
- Stabilize desktop layout shifts, especially image, review, modal, and cart drawer areas, until CLS is below `0.1`.
- Treat desktop CLS over `0.1` as a hard deploy failure; the latest artifact measured `0.939`.

### 5. Add Accessibility, SEO, And Best-Practices Gates

Require the deploy validation command to fail on high-confidence Lighthouse/axe misses that are under our control:

- Invalid ARIA attributes and roles.
- Missing required ARIA children for tab/tablist patterns.
- Contrast failures on CTA, pill, review, and disclaimer text.
- Touch targets smaller than `24px` where the control is interactive.
- Links without discernible accessible names.
- Non-crawlable `javascript:void(0)` anchors in copied Shopify header/menu markup.
- Charset missing from the first `1024` bytes of the HTML.
- Console errors and Chrome Issues panel warnings from first-party code.

### 6. Set Production Deploy Safety Gates

Before swapping production:

- Hash the current live sales page.
- Backup the existing route file and route asset directory.
- Confirm listicle route hash is unchanged.
- Upload only the sales route artifact/assets.
- Purge only the sales page URL from CDN.
- Validate live images.
- Validate live analytics capture and PostHog readback.
- Run live Lighthouse mobile and desktop.
- Stop and restore from backup if images break, required analytics are missing, or unrelated routes change.

## Next Implementation Work

The next implementation pass should update the reusable `html-deploy-v1` sales harness so future sales pages fail before deploy when any of the current live misses recur.
