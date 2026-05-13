# HTML Deploy Deterministic Validator Production Gap Plan

Decision: upgrade `html-deploy-v1` into a deterministic production gate for listicle/listicle-hybrid, quiz, and sales pages. A candidate bundle must not activate until the validator proves the artifact can send the required analytics and PostHog plus Meta can receive the expected events with the expected top-level attributes.

This plan is based on the read-only validation run against the current production quiz at `https://shoptenorco.com/8b89a76d/daily-drive-essentials/quiz/` and manual Postgres inspection on the MOS production database. No production deploys are part of this plan.

Implementation status on 2026-05-13: the first hard-gate slice is implemented in the separate validator worktree. It strengthens canonical handoff checks, blocks split/compact legacy references, requires `AddToCart` PostHog readback when checkout targets exist, preserves one canonical `session_id`/`visitor_id` through quiz/listicle-to-sales links, and adds a local quiz candidate fixture for staged validation.

## Current Findings

| Area | Finding | Required Fix |
| --- | --- | --- |
| Artifact shape | Current prod quiz has no visible `htmlArtifactKind` / clean `html-deploy-v1` marker. | Require all production funnel HTML to be emitted by `html-deploy-v1` with a manifest. |
| Static strip checks | Literal Mars/MenGoToMars regexes pass, but split strings remain, e.g. `["men","go","to","mars"].join("")`. | Add normalized forbidden-reference detection that reconstructs split literals and compact strings. |
| Quiz event delivery | Browser generated `QuizCompleted` exactly once, and PostHog eventually received required quiz events. | Keep duplicate detection, and make live PostHog readback mandatory for all required quiz events. |
| Canonical attributes | Quiz events use `anonymous_id`; `visitor_id`, `source_page_type`, `from_stage`, and `to_stage` are missing top-level. | Standardize canonical top-level fields across quiz/listicle/sales. |
| Sales handoff | Sales receives quiz handoff values in URL params, but sales events use a new top-level `session_id`. | Sales harness must promote inbound canonical handoff fields to top-level properties. |
| Meta proof | `fbq()` calls were observed for quiz presales/click events, but network receive proof was inconsistent unless navigating to sales. | Validator must prove Meta receive, not only `fbq()` invocation. |
| Postgres | Prod has quiz page topology, but `funnel_events` has zero `quiz_%` rows. | PostHog remains the analytics source of truth. Postgres checks are limited to topology/schema support and should not replace or outrank PostHog readback. |
| Local DB | Local Docker DB is behind app model and lacks `funnel_events.event_id`. | Add schema drift checks before running deterministic validator locally. |

## Additional Prod Listicle And Sales Findings

Validation run date: 2026-05-13.

Validated URLs:

- `https://shoptenorco.com/8b89a76d/daily-drive-essentials/10-reasons-glp/`
- `https://shoptenorco.com/8b89a76d/daily-drive-essentials/sales-page/`

Validation IDs:

- Listicle-to-sales: `codex-prod-listicle-c9ce2d3b7281`
- Sales standalone: `codex-prod-sales-4c22cca20521`

| Area | Finding | Required Fix |
| --- | --- | --- |
| Listicle static shape | The prod listicle is not a clean `html-deploy-v1` artifact. It has no visible artifact kind / manifest marker and uses a custom `tenor-rmbc-presell-tracking` script. | Rebuild listicle/listicle-hybrid through `html-deploy-v1`; fail deploys when artifact kind and manifest are missing. |
| Listicle legacy references | Static HTML still contains literal `mengotomars.com` and `Mars Health` references. | Extend forbidden-reference validation to block literal, compacted, split, and policy/link legacy references. |
| Listicle PostHog readback | PostHog received `presell_page_view`, `EnteredPresales`, `cta_view`, `cta_click`, `PreSalesToSalesClick`, scroll/section/proof events. | Keep live readback as required; event existence alone is not enough. |
| Listicle canonical attributes | `source_page_type` is missing from listicle entry and click rows. `PreSalesToSalesClick` has `from_stage=pre_sales` and `to_stage=sales`, but no `source_page_type=listical_presell`. | Require `source_page_type` on all presell entry/click events and validate it by page type. |
| Listicle click URL | The clicked sales URL preserved UTM/fbclid/src but did not carry canonical `session_id`, `visitor_id`, `click_id`, `source_page_type`, `from_stage`, or `to_stage`. | Handoff URL builder must append canonical fields for every presales-to-sales click. |
| Listicle-to-sales stitching | Sales events after the listicle click created a new `session_id` and `visitor_id`; the sales URL only had `fbclid`, `utm_content`, and `src=presale`. | Sales must receive canonical params from listicle and promote them to top-level event fields. |
| Sales URL param promotion | Even when the sales page was loaded with canonical params, PostHog `sales_page_view` and `EnteredSales` used a fresh top-level `session_id` / `visitor_id`; the inbound values existed only under `url_params`. | Sales harness must promote inbound `session_id`, `visitor_id`, `click_id`, `source_page_type`, `from_stage`, and `to_stage` before emitting sales events. |
| Sales click validation | Clicking the visible sales CTA produced a browser `fbq("track", "AddToCart")` call, but live PostHog readback did not show `AddToCart`, `SalesToCheckoutClick`, `SalesToCheckoutClicked`, `purchase_intent_click`, or `checkout_started`. Meta network receive for AddToCart was also not observed in this run. | Add deterministic sales CTA/cart/checkout validation and fail if checkout-intent events do not reach PostHog and Meta. |
| Sales manifest selectors | Runtime logged `Binding 'sales-shopbar-link' selector 'a.js-essentials-pro-bar-cta' matched no elements.` | Validator must distinguish optional vs required bindings; required bindings with zero matches should fail with a selector report. |
| Runtime console errors | Prod sales/listicle-to-sales runs logged PostHog capture failures. | Console/network capture errors from analytics scripts should be surfaced as validation findings and fail when tied to required events. |
| Postgres internal events | Production `funnel_events` rows for validation sales events used fresh sales-page session/visitor ids and did not promote source context; listicle presell tracking is effectively PostHog-only in this flow. | Postgres support reporting should explicitly state whether each page type is expected to persist internal events and report canonical context when rows exist. PostHog remains the blocking analytics readback. |

## Target Contract

The validator should treat a page as production viable only when all of these are true:

- The artifact is produced through `html-deploy-v1`.
- The artifact declares its page type: `listicle`, `listicle_hybrid`, `quiz`, or `sales`.
- The artifact includes a machine-readable instrumentation manifest.
- Required events are emitted in browser execution.
- Required events are received by PostHog live readback.
- Required Meta events are sent through the Meta Pixel endpoint and receive a successful response.
- Handoff events and sales-entry events carry canonical top-level attributes.
- Static and runtime checks find no forbidden legacy references.
- Candidate release remains staged until all checks pass.
- Runtime analytics console/network errors are absent for required events.
- Required selectors in the manifest exist and are actionable in the rendered DOM.

## Canonical Tracking Fields

Standardize on one funnel session identity:

- `session_id`: canonical funnel session id carried from presales/listicle/quiz into sales.
- `visitor_id`: canonical anonymous visitor id.
- `click_id`: canonical presales-to-sales transition id for the CTA click.
- `source_page_type`: `listical_presell` for listicle/listicle-hybrid presell, or `quiz_presell` for quiz presell.
- `from_stage`: `pre_sales`.
- `to_stage`: `sales`.
- `page_stage`: current page stage, such as `pre_sales` or `sales`.
- `content_category`: current page category, such as `presell_page`, `quiz_presell`, or `sales_page`.
- `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `fbclid`, `fbc`, `fbp` where available.

Compatibility rule:

- The harness may read old `rmbc_*` URL params for backward compatibility.
- New outgoing events must use canonical top-level fields.
- New outgoing URLs should prefer canonical params. Legacy aliases should only remain if explicitly needed for a transition window.
- Sales events must never require a join against `url_params` to recover the canonical funnel session.

## Required Events

Listicle and listicle-hybrid presell:

- `presell_page_view`
- `EnteredPresales`
- `qualified_session`
- `scroll_depth` milestones required by the manifest/spec
- `section_view` for required sections
- `proof_view` for required proof blocks
- `cta_view`
- `PreSalesToSalesClick`
- `cta_click` or internal equivalent when configured

Quiz presell:

- `EnteredPresales`
- `QuizLeadViewed`
- `QuizQuestionViewed`
- `QuizOptionPresented` when options are present in the manifest
- `QuizOptionSelected`
- `QuizQuestionSubmitted`
- `QuizCompleted`, exactly once per validated path
- `QuizResultViewed`
- `QuizRecommendationViewed`
- `QuizCtaViewed`
- `PreSalesToSalesClick`

Sales:

- `sales_page_view`
- `EnteredSales`
- Required section/proof/offer events from the sales manifest
- `SalesToCheckoutClick` / `SalesToCheckoutClicked` where configured
- `InitiateCheckout` or checkout-click equivalent where configured

Out of scope:

- Purchase completion and buyer-quality events. These are emitted directly by Shopify and should not block HTML deploy validation.

## Implementation Phases

### Phase 1: Contract Registry

Add a validator contract registry in `mos/backend/app/services/deploy.py` or a new small module used by it.

Tasks:

- Define page profiles: `listical_presell`, `quiz_presell`, and `sales_page`. Listicle-hybrid resolves to the listical presell profile.
- Define required events per profile.
- Define required fields per event family.
- Define destination requirements: browser capture, PostHog readback, Meta receive.
- Add structured error codes so validator output is reviewable, for example `missing_posthog_event`, `missing_top_level_field`, `legacy_reference`, `meta_receive_missing`.

Acceptance:

- Unit tests can ask the registry for required events/fields for all three page types.
- Listicle-hybrid resolves to the listicle harness contract.
- Quiz contract includes `QuizCompleted` uniqueness.

### Phase 2: Canonical Runtime Field Normalization

Update the html deploy analytics harnesses generated by `html-deploy-v1`.

Tasks:

- Emit `visitor_id` on all PostHog and Meta payloads.
- Emit `source_page_type`, `from_stage`, and `to_stage` on presales-to-sales click events.
- Emit `source_page_type` on presell page entry events.
- Append canonical handoff params to every outbound sales URL from listicle, listicle-hybrid, and quiz pages.
- Promote inbound URL params to top-level sales properties before `sales_page_view` and `EnteredSales`.
- Preserve `session_id` from presales/quiz/listicle into sales.
- Keep a local page session only under a distinct non-primary field if still needed, such as `page_session_id`.
- Read legacy `rmbc_session_id`, `rmbc_anonymous_id`, and `rmbc_click_id` only as migration inputs.
- Do not trigger `EnteredSales` on quiz final CTA; only sales page load can trigger it.

Acceptance:

- Browser-captured events show canonical fields on quiz/listicle clicks.
- Sales page `sales_page_view` and `EnteredSales` use the same canonical `session_id` as the upstream presell event.
- `url_params` is no longer required to stitch the funnel.
- Current prod listicle-to-sales failure mode is blocked: no activation when sales URL lacks canonical handoff fields.

### Phase 3: Static Artifact Validator

Strengthen static validation before browser execution.

Tasks:

- Require `html-deploy-v1` markers and manifest presence.
- Require known `htmlArtifactKind`.
- Validate manifest schema and required selector/action definitions.
- Validate declared tracking config: PostHog key, API host, UI host, Meta pixel id.
- Detect forbidden references with normalized scanning:
  - literal strings
  - compact strings
  - split array joins
  - escaped/minified string concatenation
  - URL-encoded forms
  - legacy policy/link selectors and inactive cleanup code that still embeds blocked domains
- Validate no disallowed legacy route tokens remain.
- Validate asset URLs and images are resolvable before runtime checks.

Acceptance:

- Current prod quiz split Mars/MenGoToMars token pattern fails static validation.
- Current prod listicle literal `mengotomars.com` / `Mars Health` references fail static validation.
- A valid `html-deploy-v1` page passes without requiring production activation.
- Static failures produce precise file/line/snippet context where possible.

### Phase 4: Browser Runtime Validator

Make browser validation deterministic and manifest-driven.

Tasks:

- Add validator path support for:
  - listicle/listicle-hybrid load, scroll, proof, CTA view, CTA click
  - quiz synthetic Heyflow path, completion, result/recommendation, final CTA
  - sales load, scroll/proof/offer, product CTA click, cart open, checkout click or mock checkout click
- Capture:
  - in-browser analytics events
  - PostHog client capture calls
  - Meta `fbq()` calls
  - Meta Pixel network requests
  - internal `/api/public/events` calls where configured
- Assert `QuizCompleted` fires exactly once.
- Assert quiz final CTA does not emit `EnteredSales`.
- Assert listicle and quiz CTA URLs include canonical handoff fields before navigation.
- Assert sales page load promotes inbound handoff fields before emitting sales events.
- Assert required selectors exist and are interactable; missing required selectors fail with selector id and CSS selector.
- Assert candidate route visual load and no blank page state.

Acceptance:

- A failing quiz event path reports exactly which event or field failed.
- Browser-only success cannot pass if PostHog live readback fails.
- A browser `fbq()` call alone cannot pass if Meta network receive is missing.
- No deployment promotion occurs from this step.

### Phase 5: Live PostHog Readback

Promote live PostHog readback from optional validation to required validation for HTML deploys.

Tasks:

- Poll HogQL until all required events are observed or timeout expires.
- Query by validation id across:
  - `$current_url`
  - `event_source_url`
  - `destination_url`
  - `url_params`
  - `path`
  - `utm_content`
  - `utm_campaign`
  - `fbclid`
- For each required event, validate top-level fields.
- Reject rows where handoff fields exist only under `url_params`.
- Validate that sales events preserve upstream `session_id`, `visitor_id`, `click_id`, `source_page_type`, `from_stage`, and `to_stage`.
- Validate listicle/listicle-hybrid `PreSalesToSalesClick` includes `source_page_type=listical_presell`.
- Validate sales checkout-intent events when checkout targets are configured:
  - `AddToCart` or `add_to_cart` when a product/cart CTA is clicked
  - `SalesToCheckoutClick` / `SalesToCheckoutClicked` when checkout is clicked
  - `purchase_intent_click` where emitted by the sales harness
- Treat delayed ingestion as expected by polling, not as an immediate failure.

Acceptance:

- The current prod quiz would fail because top-level canonical fields are missing.
- The current quiz-to-sales path would fail because sales creates a new primary `session_id`.
- The current listicle-to-sales path would fail because `source_page_type` is missing and sales creates a new primary `session_id`.
- The current sales standalone path would fail because inbound canonical params remain URL-param-only.
- Readback output includes observed events and missing/mismatched fields.

### Phase 6: Meta Receive Validation

Upgrade Meta validation from `fbq()` observation to receive proof.

Tasks:

- Capture `facebook.com/tr` requests and response status.
- Match Meta event names to required events:
  - `EnteredPresales`
  - `PreSalesToSalesClick`
  - `EnteredSales`
  - `AddToCart`
  - `SalesToCheckoutClick` / `SalesToCheckoutClicked` where configured
  - checkout/initiate events where configured
- Validate Meta payload includes event source URL, pixel id, external id, canonical session/click context where available, and source stage.
- Add a clean configuration requirement for any stronger Meta Events Manager readback if a Meta access token/test event code is available.
- Until Graph/API readback is configured, make network receive the required deterministic proof.

Acceptance:

- A queued `fbq()` call without a `facebook.com/tr` receive request fails.
- Sales Meta network receive stays covered.
- Quiz presales/click Meta events must prove receive or report `meta_receive_missing`.
- Sales product/checkout clicks must prove Meta receive for the configured checkout-intent events, not only queue `fbq()`.

### Phase 7: Integrated Lighthouse Performance Gate

Add Lighthouse to the same staged candidate validator report. Do not create a separate optimization validator or a separate promotion path.

Tasks:

- Run Lighthouse against the inactive candidate URLs by appending `mos_deploy_candidate_release=<candidate_id>`.
- Audit every page in the compiled `html-deploy-v1` validation plan, including listicle/listicle-hybrid, quiz, and sales pages.
- Run deterministic mobile and desktop profiles for each candidate page.
- Require mobile performance score `>= 85`.
- Require desktop performance score `>= 85`.
- Fail closed when the Lighthouse command, Chrome runtime, JSON report, or score is missing.
- Attach Lighthouse results to `htmlDeployValidationReport.lighthouseValidation` beside the tracking/browser/PostHog/Meta results.
- Keep optimization output as evidence inside the validator report; do not introduce a standalone optimization validator.

Acceptance:

- Candidate activation does not occur when any staged page scores below 85 on mobile or desktop.
- A broken Lighthouse runtime fails with a clean deploy error before promotion.
- The deploy response shows per-page/per-profile scores and key performance audits.
- Existing static, browser, PostHog, and Meta gates remain the same validator path.

### Phase 8: Postgres Support Report

Add read-only Postgres checks as a supporting report. This is not a replacement for PostHog readback, and Postgres event persistence is not the source of truth for quiz/listicle/sales analytics.

Tasks:

- Check schema drift:
  - required alembic version
  - `funnel_events.event_id` exists
  - required enum values exist
- Check active funnel topology:
  - active publication exists
  - quiz/listicle page is in active publication
  - presales page `next_page_id` points to sales page when expected
  - sales page exists in active publication
- Check whether quiz/listicle/sales internal events are expected to persist, and report the mode explicitly.
- If internal persistence is enabled, verify recent validation rows in `funnel_events` as supporting evidence only.
- If internal persistence is not expected for quiz/listicle/sales, report that explicitly so it does not masquerade as a missing PostHog analytics failure.
- For sales internal rows that do exist, report whether persisted `session_id`, `visitor_id`, `click_id`, `source_page_type`, `from_stage`, and `to_stage` match canonical handoff expectations.
- For listicle custom tracking, report whether internal persistence is unsupported, disabled, or missing.

Acceptance:

- Prod Daily Drive quiz topology check passes.
- Prod `quiz_%` internal persistence currently reports as missing/not-enabled rather than silently passing.
- Local DB drift is reported cleanly before local validator execution.
- Prod sales internal row mismatches are reported as support findings while PostHog readback remains the blocking analytics gate.

### Phase 9: Candidate Activation Gate

Wire all validator stages into the staged deployment gate.

Tasks:

- Keep candidate bundle inactive until static, browser, PostHog, Meta, and Lighthouse checks pass. Postgres topology/schema failures can block deploys when they indicate the active route/page graph is invalid; Postgres event persistence does not replace PostHog readback.
- Preserve the prior active bundle automatically on failure.
- Return a structured validation report with failures grouped by stage.
- Save the report to deploy metadata/log output for review.
- Ensure no legacy standalone/static replacement path can bypass this gate.

Acceptance:

- A failed validator run leaves the old production bundle active.
- The deployment response explains why the candidate was not promoted.
- Tests cover failure modes for static, browser, PostHog, Meta, and Postgres topology/support reporting.

## Test Plan

Unit tests:

- Contract registry returns correct events and fields by page type.
- Split legacy reference detector catches constructed Mars/MenGoToMars strings.
- Canonical handoff assertion rejects URL-param-only fields.
- Quiz duplicate checker rejects two `QuizCompleted` events.
- Sales handoff assertion rejects a new primary sales `session_id`.

Integration tests:

- Local listicle artifact passes static and browser checks.
- Local quiz fixture passes synthetic Heyflow path validation.
- Local sales fixture promotes inbound canonical params.
- Simulated PostHog readback passes only when events and fields match.
- Simulated Meta receive passes only when `facebook.com/tr` requests are observed.
- Simulated Lighthouse output passes only when mobile and desktop scores are `>= 85`.
- Simulated Lighthouse output fails before candidate promotion when either score is below `85`.

Manual validation:

- Run read-only prod quiz validation against current URL.
- Run read-only prod listicle-to-sales validation.
- Run read-only prod quiz-to-sales validation.
- Run Postgres topology/schema support report against prod.
- Confirm current prod quiz fails for known gaps before using this as a deployment gate.

## Rollout Plan

1. Implement registry/static/runtime/readback changes in the separate validator worktree.
2. Validate against local listicle fixture from `/Users/auggieclement/Downloads/ecomwize-share-clone/listicle.html`.
3. Validate against a local quiz fixture.
4. Run read-only validation against current prod quiz and listicle.
5. Fix harness gaps until local candidates pass.
6. Push branch and open PR to `main`.
7. After review and merge, use normal `main` to CI/CD path.
8. Only then deploy new HTML artifacts through `html-deploy-v1`.

## Open Decisions

- Do we keep legacy `rmbc_*` URL aliases during a short migration window, or remove them from all new outgoing URLs immediately?
- Do we have a Meta access token/test event code available for stronger Events Manager readback, or is Pixel network receive the accepted proof for now?

Resolved decisions:

- PostHog is the analytics source of truth.
- `visitor_id` is the canonical anonymous visitor field. `anonymous_id` and `rmbc_anonymous_id` may be read as migration inputs, but they do not satisfy the validator as output fields.

## Immediate Next Implementation Slice

Start with the smallest slice that would have caught the current prod quiz:

1. Add normalized forbidden-reference scanning for split legacy tokens.
2. Add canonical field requirements for quiz events and quiz-to-sales handoff.
3. Require PostHog live readback for all quiz required events.
4. Fail sales readback when handoff fields only exist under `url_params`.
5. Add Postgres topology/schema support report.
6. Add listicle/listicle-hybrid canonical handoff checks:
   - block missing `source_page_type`
   - block sales URLs that do not include canonical session/visitor/click/source fields
7. Add sales checkout-intent validation:
   - product CTA click
   - AddToCart/PostHog/Meta receive
   - SalesToCheckoutClick or mock checkout receive when checkout target is available
8. Fail required binding selectors that match no rendered element.
9. Add integrated Lighthouse mobile/desktop gating to the same candidate validator report.

This slice creates a hard gate for the actual regressions observed without changing the visual look or feel of any deployed page.
