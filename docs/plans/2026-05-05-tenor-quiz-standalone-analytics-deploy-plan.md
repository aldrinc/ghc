# Tenor Quiz Standalone Analytics Deploy Plan

Prepared: May 5, 2026

## Decision

Deploy the Tenor quiz as a MOS-managed standalone pre-sales page on `shoptenorco.com`, using the existing MOS standalone analytics bridge and the RMBC quiz funnel analytics spec as the event contract.

The quiz should not ship as the raw Mengotomars Shopify capture. The production artifact should remove the old Mars Shopify pixels, Mars storefront scripts, Mars base/canonical URLs, and the Heyflow dependency, then replace them with a first-party quiz runtime that emits MOS/RMBC events and always hands off to the Tenor sales page.

Target sales destination:

```text
https://shoptenorco.com/8b89a76d/daily-drive-essentials/sales-page/
```

## Current Findings

- Local quiz source is `/Users/auggieclement/Documents/GitHub/ghc/local-sites/mengotomars-quiz-v6/index.html`.
- That file still contains `heyflow-wrapper`, `assets.prd.heyflow.com`, `mengotomars.com` Shopify scripts, Mars web pixels, Mars canonical/base URLs, and Mars legal/footer remnants.
- The live Tenor sales page already has MOS standalone tracking installed:
  - event endpoint: `/api/public/events`
  - product slug: `8b89a76d`
  - page stage: `sales`
  - PostHog API host: `https://ten.shoptenorco.com`
  - Meta pixel wiring present
  - checkout click bindings already emit `sales_to_checkout_click`
- The live sales page already recognizes pre-sales attribution via:
  - same-origin pre-sales referrer
  - `src=presale`
  - session storage key scoped to MOS product/funnel context
- The RMBC spec requires `EnteredPresales` and `PreSalesToSalesClick` as bridge events, plus answer-path diagnostics.
- MOS already stores public funnel events in `funnel_events` through `POST /public/events`.
- MOS currently supports broad event types such as `presell_page_view`, `pre_sales_to_sales_click`, `cta_view`, `proof_view`, `section_view`, `selector_interaction`, and `purchase`, but does not yet have first-class quiz-specific event enum values.

## Production Architecture

### Hosting

Deploy the quiz under the existing Tenor same-origin funnel path, preferably:

```text
https://shoptenorco.com/8b89a76d/daily-drive-essentials/quiz-v6/
```

Same-origin matters because the current sales page bridge uses session storage scoped by MOS product/funnel context. Keeping the quiz on `shoptenorco.com` avoids losing attribution across domains.

If we instead deploy a separate subdomain, the sales page runtime must be updated to read `quiz_session_id` / `session_id` query params because session storage will not cross origins.

### Runtime

Create a first-party static quiz runtime instead of relying on Heyflow:

- `index.html` for markup and Tenor styling
- `assets/` for existing approved quiz imagery
- `tenor-quiz.js` for step state, validation, answer capture, progress, and redirect
- `tenor-quiz-analytics.js` for MOS/RMBC event emission

The runtime should use the same MOS standalone context as the sales page:

- `productSlug: "8b89a76d"`
- same Tenor funnel slug/context used by the sales page deploy
- `pageStage: "pre_sales"`
- published `publicationId` and quiz `pageId` from MOS
- workspace tracking config inherited from Tenor PostHog/Meta settings

## Analytics Event Contract

### Bridge Events

Use existing MOS event types for the required RMBC bridge:

| RMBC event | MOS event type | Notes |
| --- | --- | --- |
| `EnteredPresales` | `presell_page_view` | Fire once when quiz shell is ready and first screen can render. MOS maps this to Meta `EnteredPresales`. |
| `PreSalesToSalesClick` | `pre_sales_to_sales_click` | Fire immediately before final redirect to the sales page. |

Add `props.rmbcEventName` with the RMBC name so reporting can preserve the spec language.

### Quiz Diagnostic Events

Add new MOS enum values and runtime types:

- `quiz_lead_viewed`
- `quiz_question_viewed`
- `quiz_option_presented`
- `quiz_option_selected`
- `quiz_option_deselected`
- `quiz_question_submitted`
- `quiz_completed`
- `quiz_result_viewed`
- `quiz_mechanism_viewed`
- `quiz_proof_viewed`
- `quiz_recommendation_viewed`
- `quiz_cta_viewed`

Each event should include the shared context:

- `eventId`
- `sessionId`
- `visitorId`
- `quizId: "tenor-daily-drive-quiz-v6"`
- `quizVersion`
- `quizVariant`
- `productSlug`
- `funnelSlug`
- `publicationId`
- `pageId`
- `pageStage: "pre_sales"`
- `path`
- `referrer`
- UTMs and click IDs
- `deviceType`, viewport width, browser user agent

Question and option events should use stable IDs, not raw display text as the primary identifier. Raw text can be included only as secondary debug copy when approved.

## Quiz Instrumentation Map

Define a local question registry:

| Step | Question role | Required events |
| --- | --- | --- |
| Lead/start screen | opening promise | `quiz_lead_viewed`, `presell_page_view` |
| Age | qualification | question viewed, options presented, selected, submitted |
| Main goal/concern | desire/pain | question viewed, options presented, selected, submitted |
| Stress/low-T indicators | mechanism/risk | question viewed, options presented, selected, submitted |
| Energy crash | pain severity | question viewed, options presented, selected, submitted |
| Timeline | awareness/sophistication | question viewed, options presented, selected, submitted |
| Desired outcome | promise/segment | question viewed, options presented, selected, submitted |
| Body composition | identity/qualification | question viewed, options presented, selected, submitted |
| Sleep | mechanism/risk | question viewed, options presented, selected, submitted |
| Family history | risk factor | question viewed, options presented, selected, submitted |
| Processed food | risk/mechanism | question viewed, options presented, selected, submitted |
| Loading/analyzing | result build | `quiz_completed` once required questions are answered |
| Result summary | result/brief | `quiz_result_viewed` |
| T-level mechanism/proof | mechanism/proof | `quiz_mechanism_viewed`, `quiz_proof_viewed` |
| Recommendation page | offer bridge | `quiz_recommendation_viewed`, `quiz_cta_viewed` |
| Final CTA | sales handoff | `pre_sales_to_sales_click`, then redirect |

## Handoff Requirements

The final CTA always redirects to the Tenor sales page. No answer-based routing for this version.

Append stitchable params:

- `src=presale`
- `quiz_id=tenor-daily-drive-quiz-v6`
- `quiz_version`
- `quiz_variant`
- `quiz_session_id`
- `result_id`
- `segment_id`
- `answer_path_id` or `answer_path_hash`
- original `utm_*`
- original click IDs such as `fbclid`, `gclid`, `ttclid`, `msclkid`

Before navigation:

1. Emit `quiz_cta_viewed` when the CTA enters the viewport.
2. Emit `pre_sales_to_sales_click` with `destination_url`.
3. Navigate to the sales page only after the event dispatch has been queued through the MOS standalone bridge pattern.

## Implementation Steps

### 1. Prepare the Quiz Artifact

- Copy the current approved quiz visual state into a clean standalone HTML artifact.
- Remove Mars Shopify scripts, Mars web pixels, old Mars canonical/base tags, and Mengotomars legal links.
- Remove Heyflow and rebuild the quiz steps as first-party HTML/JS.
- Keep Tenor-approved fonts and assets from the Tenor workspace.
- Keep final sales destination hard-coded to the Tenor sales page.

### 2. Extend MOS Event Types

- Add an Alembic migration for quiz-specific `funnel_event_type` values.
- Update `FunnelEventTypeEnum`.
- Update frontend runtime event typing.
- Add backend tests that reject unsupported values cleanly and accept the new quiz event chain.

### 3. Add Quiz Analytics Runtime

- Implement the RMBC event helper in the quiz artifact.
- Reuse the MOS standalone payload shape:
  - `eventId`
  - `eventType`
  - `occurredAt`
  - `publicationId`
  - `pageId`
  - `visitorId`
  - `sessionId`
  - `path`
  - `referrer`
  - `utm`
  - `props`
- Register PostHog/Meta captures through the existing MOS tracking config instead of standalone ad hoc snippets.
- Emit clean console errors for failed tracking configuration; do not silently switch to unrelated providers.

### 4. Add MOS Standalone Page Config

- Add or update a Tenor funnel page with:
  - slug: `quiz-v6`
  - stage: `pre_sales`
  - render mode: `standalone_imported_html`
  - tracking inherited from the Tenor workspace
  - instrumentation manifest for final CTA visibility/clicks if using the standard bridge
- Ensure the page uses the same MOS product/funnel context as the sales page so session storage can stitch.

### 5. Validate Locally

Run automated checks before any production action:

- Static scan confirms no `mengotomars.com`, Mars Shopify pixel, or Heyflow dependency remains in the deploy artifact.
- Playwright click-through completes the quiz and lands on the Tenor sales URL.
- Network capture confirms the minimum chain:
  - `presell_page_view`
  - `quiz_question_viewed`
  - `quiz_option_selected`
  - `quiz_question_submitted`
  - `quiz_completed`
  - `quiz_result_viewed`
  - `quiz_cta_viewed`
  - `pre_sales_to_sales_click`
- Sales URL contains `src=presale`, UTMs/click IDs, and quiz IDs.
- Sales page records `sales_page_view` with `fromPresale: true`.

### 6. Stage Deployment

- Publish to a non-production/staging route first.
- Validate in browser on desktop and mobile.
- Query MOS `funnel_events` for the staged publication/page IDs and verify event order, uniqueness, and props.
- Confirm PostHog receives mapped captures under the Tenor project.

### 7. Production Gate

Production deploy requires explicit approval in the current thread.

Once approved:

- Use the normal `main -> GitHub -> CI/CD` path when possible.
- Use Cloudhand/MOS deployer only through the existing deployment workflow.
- Reference the approved operator SSH key only if the approved deploy path requires bridge-host access.
- Do not print, copy, commit, or inspect the SSH key contents.
- Do not restart production services or make direct live changes unless explicitly approved.

### 8. Production Smoke

After deployment:

- Load the production quiz route.
- Complete one controlled smoke path.
- Verify final URL is the Tenor sales page, not Mengotomars.
- Verify MOS events for the production publication/page IDs.
- Verify PostHog captures under the Tenor project.
- Verify sales page attribution has `fromPresale: true`.
- Verify checkout click tracking still works on the sales page.

## Open Decisions

- Final route: use `/quiz-v6/` or replace the existing `/presales/` page.
- Whether to add a sales-page runtime change to read `quiz_session_id` query params, useful if the quiz is not deployed on the exact same origin/context.
- Whether raw answer labels are allowed in analytics props, or whether reporting should use stable option IDs only.
- Whether production smoke events should be left in analytics marked as validation events or removed from reporting.

## Files Likely Touched

- `mos/backend/app/db/enums.py`
- `mos/backend/alembic/versions/*_quiz_funnel_event_types.py`
- `mos/backend/app/schemas/funnels.py`
- `mos/frontend/src/lib/funnelTracking.ts`
- `mos/frontend/src/lib/metaFunnelEvents.ts`
- `mos/frontend/src/lib/posthog.ts`
- `mos/frontend/src/funnels/StandaloneImportedHtmlPage.tsx`
- `mos/backend/cloudhand/adapters/deployer.py`
- `mos/backend/tests/test_analytics.py`
- `mos/backend/tests/test_cloudhand_deployer_funnel_proxy.py`
- new Tenor quiz artifact source under the MOS-managed standalone artifact workflow
