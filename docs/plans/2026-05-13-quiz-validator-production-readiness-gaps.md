# Quiz Validator Production Readiness Gaps

Decision: the current Tenor quiz funnel cannot be marked traffic-ready from this validation run. The GitHub deploy succeeded, but the attempted `html-deploy-v1` funnel publish failed before replacement because the Sales Page artifact is still on the legacy imported-HTML manifest schema. A manual PostHog readback against the currently deployed production quiz also found gaps that the validator should report deterministically.

## Evidence

- Main/self-deploy status: GitHub deploy and apply completed successfully before the publish attempt.
- Publish job: `e2c5ae1c-3639-4a1e-a263-b9fa62f39af2`.
- Publish result: failed during `publishing_funnel`.
- Blocking error: `Page 'Sales Page' imported HTML runtime validation failed. instrumentationManifest.schemaVersion must be 'html-deploy-v1'. Rebuild this page with the HTML deploy manifest contract instead of the legacy imported HTML schema.`
- Manual production readback run id: `codex_prod_quiz_rerun_20260513T1810`.
- Manual report: `.local/live-validation-20260513/current-prod-quiz-posthog-codex_prod_quiz_rerun_20260513T1810.json`.

## Current Findings

The current production quiz path does complete quiz to sales to checkout click when the final CTA is activated reliably.

Direct PostHog readback eventually observed:

- `EnteredPresales`: 1
- `QuizLeadViewed`: 1
- `QuizQuestionViewed`: 16
- `QuizOptionSelected`: 10
- `QuizCompleted`: 1
- `QuizResultViewed`: 1
- `QuizRecommendationViewed`: 1
- `QuizCtaViewed`: 1
- `PreSalesToSalesClick`: 1
- `sales_page_view`: 1
- `EnteredSales`: 1
- `SalesToCheckoutClick`: 1
- `SalesToCheckoutClicked`: 1

Important passes:

- `QuizCompleted` did not double fire in the manual run.
- `EnteredSales` landed once, after the sales page load.
- The quiz final CTA preserved the expected URL bridge params into the sales URL.

Important failures or gaps:

- Current production quiz HTML does not expose an `html-deploy-v1` manifest or `MOS_HTML_DEPLOY_BRIDGE_START` marker.
- Current production sales HTML declares `schemaVersion: imported-html-instrumentation-v1`.
- The sales page top-level PostHog `session_id` and `click_id` are not the quiz bridge values in the currently deployed legacy sales artifact. The quiz bridge values are present in `url_params` / `event_source_url`, but the top-level sales fields use a new sales-page session and the paid `fbclid`.
- `PreSalesToSalesClick` has some required handoff fields only inside `destination_url` / Meta custom data, not as first-class PostHog fields.
- Meta network validation observed `EnteredPresales`, `PreSalesToSalesClick`, `PageView`, `EnteredSales`, `SalesToCheckoutClick`, and `SalesToCheckoutClicked`; `ViewContent` was not observed in the manual run.
- The deploy/readback query path should include `properties.path`. Checkout events were present in PostHog, but the first readback query missed them until a follow-up query included `properties.path`.
- Current production quiz still contains split-token Mars cleanup code in inline JavaScript. Even if intended as a stripper, the validator should flag legacy brand tokens inside deployed quiz/sales artifacts.

## Implementation Plan

1. Rebuild the Sales Page artifact under the `html-deploy-v1` contract.
   - Require `instrumentationManifest.schemaVersion = html-deploy-v1`.
   - Require `htmlArtifactKind = sales`.
   - Require `pageStage = sales`.
   - Preserve the current visual page output.
   - Keep checkout bindings and product/variant mappings intact.

2. Rebuild or republish the Quiz artifact under the `html-deploy-v1` contract.
   - Require `htmlArtifactKind = quiz`.
   - Require the quiz presales harness.
   - Keep the visible quiz experience unchanged.
   - Remove legacy Mars references, including split-token/constructed references.

3. Upgrade static artifact validation.
   - Fail any production quiz/listicle/sales artifact without an `html-deploy-v1` manifest.
   - Fail legacy `imported-html-instrumentation-v1` manifests.
   - Fail missing `htmlArtifactKind`.
   - Fail forbidden legacy domains and brand references, including constructed patterns such as separate `Mars` + `Health` tokens in the same script block.

4. Upgrade quiz browser-path validation.
   - Execute `quiz load -> quiz completion -> result/CTA view -> final CTA -> sales load -> checkout click`.
   - Activate the final CTA through a robust DOM click after scrolling into view.
   - Fail if the browser does not reach `/sales-page/`.
   - Fail if checkout CTA cannot be activated.

5. Upgrade PostHog live readback.
   - Always require live PostHog readback in production validation.
   - Query by validation token across `properties.path`, `$current_url`, `event_source_url`, `destination_url`, `url_params`, `utm`, and campaign fields.
   - Include enough timeout/polling budget for delayed checkout-event materialization.
   - Require all quiz-to-sales-to-checkout events from the spec.
   - Require `QuizCompleted` exactly once.
   - Require `EnteredSales` exactly once and only after `sales_page_view`.

6. Upgrade bridge validation.
   - Standardize on one canonical funnel `session_id` across quiz/listicle to sales.
   - Require top-level `session_id`, `anonymous_id` or `visitor_id`, `click_id`, `source_page_type`, `from_stage`, and `to_stage` on `PreSalesToSalesClick`.
   - Require `source_page_type = quiz_presell` for quiz and `listicle_presell` for listicle/listicle-hybrid.
   - Require sales `sales_page_view`, `EnteredSales`, `SalesToCheckoutClick`, and `SalesToCheckoutClicked` to stitch to the presales click through top-level canonical fields, not only `url_params`.
   - Continue preserving `url_params` for diagnostics, but do not treat nested-only values as production-valid.

7. Upgrade Meta validation.
   - Require Meta network proof for `PageView`, `EnteredPresales`, `PreSalesToSalesClick`, `EnteredSales`, `ViewContent`, `SalesToCheckoutClick`, and `SalesToCheckoutClicked`.
   - Require `EnteredSales` Meta `event_source_url` to be the sales page URL.
   - Fail if `EnteredSales` is observed on quiz before sales load.

8. Add deterministic tests.
   - Unit test manifest rejection for missing/legacy schemas.
   - Unit test PostHog readback query matching `properties.path`.
   - Unit test row-level bridge validation for top-level canonical fields.
   - Playwright contract test with a fixture quiz artifact proving the full browser path and readback requirement shape.
   - Regression test for `QuizCompleted` double-fire prevention.

9. Deployment gate behavior.
   - Treat any validator failure as a failed publish.
   - Do not present a publish as production-ready unless the validator report includes passing static checks, browser-path checks, Meta checks, and PostHog live readback checks.
   - Report the old/new artifact status explicitly so reviewers can tell whether a failed publish left the old artifact in place.

## Acceptance Criteria

- A future quiz/listicle/sales deployment fails before being marked production-valid if any page is not `html-deploy-v1`.
- The validator catches the current legacy sales manifest failure.
- The validator catches missing top-level bridge fields rather than accepting values only inside `url_params`.
- The validator catches missing Meta `ViewContent`.
- The validator readback finds checkout events by validation token without a manual follow-up query.
- The validator report is sufficient to prove a quiz funnel is traffic-ready from enter to checkout click/mock checkout.
