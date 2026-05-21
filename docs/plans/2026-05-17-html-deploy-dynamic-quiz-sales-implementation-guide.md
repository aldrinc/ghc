# html-deploy-v1 Dynamic Quiz And Sales Implementation Guide

Decision: dynamic quiz and sales-page deployments should remain inside `html-deploy-v1`, fail closed, and activate only after deterministic candidate validation proves static structure, browser behavior, PostHog readback, direct Meta Pixel delivery, and sales handoff correctness.

This guide turns the current inventory into an implementation plan for production-ready, non-brittle, fast funnel deployments where operators can change quiz copy, questions, answers, flow, results, and sales-page copy without breaking analytics or deployment safety.

## Non-Negotiables

- Production HTML funnel deployment uses `html-deploy-v1` only.
- No legacy standalone HTML fallback, route-scoped artifact swap, runtime-bundle fallback, or manual production HTML replacement.
- Missing config, missing bindings, missing selectors, missing analytics, broken image assets, invalid branch coverage, and destination readback failures must hard-fail with clean errors.
- Direct production changes are out of scope unless explicitly authorized in the current thread.
- Meta proxy is removed from the production contract. Meta Pixel must load directly from `https://connect.facebook.net/en_US/fbevents.js`.
- `/__mos/meta/*` must be treated as a legacy path and rejected by static and browser validation.

## Target Architecture

The target system has four layers:

1. Authoring contract: structured quiz and sales template data that is the source of truth.
2. Artifact compiler: generates HTML, stable data attributes, and the `html-deploy-v1` instrumentation manifest from the same source.
3. Candidate deploy: writes an inactive release that can be validated through the deployed nginx/candidate route behavior.
4. Deterministic validator: compiles the manifest into validation paths, exercises the candidate in a browser, and proves event delivery.

The deployment service should orchestrate these layers. It should not infer quiz flow, guess selectors from text, invent fallback bindings, or silently convert unsupported artifacts.

## Implementation Phases

### Phase 1: Make The Dynamic Quiz Contract First-Class

Create a tracked schema/model for quiz templates. Recommended backend module:

```text
mos/backend/app/services/html_deploy_templates/quiz_contract.py
```

Required fields:

```python
class QuizTemplateContract(BaseModel):
    quizId: str
    quizVersion: str
    quizVariant: str
    questions: list[QuizQuestionContract]
    options: list[QuizOptionContract]
    flows: list[QuizValidationFlow]
    results: list[QuizResultContract]
    finalCta: QuizFinalCtaContract
    salesTargetPageId: str
```

Question fields:

- `questionId`
- `questionVersion`
- `questionText`
- `questionIndex`
- `questionType`: `single_select`, `multi_select`, `free_text`, or another explicitly supported type
- `required`
- `selectorId`

Option fields:

- `questionId`
- `optionId`
- `optionVersion`
- `optionText`
- `optionIndex`
- `selectorId`
- `submitOnSelect`
- optional scoring or branch metadata

Result fields:

- `resultId`
- `resultVersion`
- `segmentId`
- `offerId`
- `resultSelectorId`
- `expectedSalesTargetPageId`

Flow fields:

- `flowId`
- `description`
- `steps[]`
- `expectedResultId`
- `expectedSegmentId`
- `expectedOfferId`
- `expectedFinalCtaSelectorId`

Acceptance criteria:

- Copy-only edits can update `questionText` and `optionText` without changing stable IDs.
- Semantic answer meaning changes require `optionVersion` or `optionId` change.
- Flow or result logic changes require `quizVersion` change.
- Every result is reachable by at least one declared validation flow.
- New quiz artifacts without declared flows fail preflight.

### Phase 2: Compile HTML And Manifest Atomically

The authoring system should never separately edit quiz HTML and instrumentation metadata. Add a compiler that emits both:

- rendered/imported HTML with stable `data-*` attributes;
- `html-deploy-v1` manifest with matching selectors, events, bindings, quiz fields, validation flows, and sales handoff metadata.

Recommended generated attributes:

```html
data-html-deploy-kind="quiz"
data-quiz-id="..."
data-quiz-version="..."
data-quiz-question-id="..."
data-quiz-option-id="..."
data-quiz-result-id="..."
data-funnel-cta="quiz-final"
data-html-deploy-target-id="..."
```

Selectors in the manifest should reference generated data attributes, not copy text, CSS utility classes, or visual hierarchy.

Acceptance criteria:

- A changed question label does not change the selector.
- A changed option label does not change the selector.
- Reordering questions updates `questionIndex` but keeps stable IDs when meaning is unchanged.
- Removing a question fails if any flow still references it.
- Removing an option fails if any flow or result rule still references it.

### Phase 3: Extend The Manifest Schema

Extend `ImportedHtmlInstrumentationManifest` to support declared validation flows and result expectations.

Recommended fields:

```json
{
  "quizValidationFlows": [
    {
      "flowId": "primary",
      "steps": [
        {"questionId": "goal", "optionIds": ["lose-weight"]},
        {"questionId": "timeline", "optionIds": ["thirty-days"]}
      ],
      "expectedResultId": "starter-plan",
      "expectedSegmentId": "weight-loss",
      "expectedOfferId": "starter-offer",
      "expectedFinalCtaSelector": "[data-funnel-cta='quiz-final']"
    }
  ]
}
```

Validation rules:

- `flowId` must be unique.
- Every step must reference a known question.
- Every selected option must reference a known option for that question.
- Every result must be covered by at least one flow.
- Multi-select questions must declare explicit submission behavior.
- Final CTA must point to the configured sales page.

Compatibility:

- Existing `selectionOrder` can remain as a single-path compatibility field.
- New dynamic quiz templates should require `quizValidationFlows`.
- Transitional compatibility should be explicitly scoped, visible in reports, and not used for new production templates.

### Phase 4: Extract The Validator Package

Move validator logic out of the monolithic deploy service into:

```text
mos/backend/app/services/html_deploy_validation/
  contracts.py
  registry.py
  compiler.py
  static_checks.py
  browser_runner.py
  event_capture.py
  assertions.py
  report.py
  destinations/posthog.py
  destinations/meta_pixel.py
```

Responsibilities:

- `contracts.py`: page-type contracts for `listicle`, `listicle_hybrid`, `quiz`, and `sales`.
- `registry.py`: maps `htmlArtifactKind` to contract.
- `compiler.py`: turns manifest plus publication metadata into validation requirements.
- `static_checks.py`: verifies manifest, forbidden refs, direct Meta Pixel bootstrap, PostHog bootstrap, selectors, and assets.
- `browser_runner.py`: executes declared actions only.
- `event_capture.py`: normalizes MOS public events, PostHog browser events, PostHog readback rows, and direct Meta Pixel requests.
- `assertions.py`: validates required events, props, ordering, dedupe, and cross-page handoff relationships.
- `report.py`: emits compact human-reviewable and machine-readable validation evidence.
- `destinations/posthog.py`: polls live PostHog readback.
- `destinations/meta_pixel.py`: validates direct Pixel network delivery and optional Meta test-event confirmation.

Acceptance criteria:

- `deploy.py` invokes the package as an orchestrator.
- Page-specific validation rules live in contracts, not scattered branches.
- Adding a page type requires a contract and tests.
- Validation report remains compact enough for fast review.

### Phase 5: Remove Meta Proxy Completely

The production contract is direct browser Pixel delivery.

Required behavior:

- Generated HTML includes `https://connect.facebook.net/en_US/fbevents.js`.
- Runtime calls `fbq("init", pixelId)` and emits configured Pixel events.
- Static validation rejects `/__mos/meta/*`.
- Static validation rejects missing direct Meta Pixel bootstrap when Meta tracking is configured.
- Browser validation records direct Pixel network requests and fails on missing required events or HTTP errors.
- Nginx config does not define `/__mos/meta/*`.
- Local validation servers do not stub `/__mos/meta/*`.

Code cleanup checklist:

- Remove unused Meta proxy helpers.
- Remove local preview/server stubs for `/__mos/meta/fbevents.js`, `/__mos/meta/tr/`, `/__mos/meta/signals/config/*`, and related routes.
- Rename future validation adapters to `meta_pixel`, not `meta_proxy`.
- Keep tests that assert proxy routes are absent.
- Add tests that any `/__mos/meta/*` reference in deployed HTML fails validation.

### Phase 6: Harden Sales Template Changes

Sales-page copy edits are safe only if checkout and add-to-cart bindings remain stable.

Add or enforce a sales template contract:

```python
class SalesTemplateContract(BaseModel):
    salesPageId: str
    salesPageVersion: str
    productSlug: str
    offerId: str | None
    variantSelectors: list[SalesVariantSelector]
    addToCartTargets: list[SalesActionTarget]
    checkoutTargets: list[SalesActionTarget]
```

Rules:

- Copy-only edits do not change selectors.
- CTA replacement regenerates stable selectors and bindings.
- Checkout target must resolve to a valid configured checkout URL or checkout intent.
- Variant-dependent checkout must prove variant selection and checkout event attributes.

Required sales validation:

- `sales_page_view`
- `EnteredSales`
- `SalesToCheckoutClick`
- `SalesToCheckoutClicked`
- checkout URL or checkout intent interception
- canonical `session_id`, `visitor_id` or `anonymous_id`, `click_id`, `source_page_type`, `from_stage`, and `to_stage`
- `product_slug`, `funnel_slug`, `publication_id`, and `page_id`

### Phase 7: Candidate Activation Gate

Activation should stay candidate-first:

1. Build inactive release.
2. Serve it through candidate route/query param.
3. Run static validation.
4. Run browser validation for every declared path.
5. Run live PostHog readback.
6. Validate direct Meta Pixel network delivery.
7. Persist validation report.
8. Activate candidate only after all required gates pass.

Activation must fail closed. The previous active release remains active on failure.

### Phase 8: Testing Plan

Backend unit tests:

- manifest rejects quiz without `quizId`, `quizVersion`, or `quizVariant`;
- manifest rejects unknown question/option references;
- manifest rejects duplicated option IDs per question;
- manifest rejects missing validation flow on new dynamic quiz templates;
- manifest rejects uncovered result IDs;
- direct Meta Pixel is required when Meta tracking is configured;
- `/__mos/meta/*` in HTML or runtime requests fails validation.

Backend integration tests:

- quiz copy-only edit preserves stable IDs and selectors;
- quiz option text edit preserves `optionId`;
- quiz branch edit requires version bump;
- quiz multi-branch candidate validates every declared flow;
- sales copy-only edit preserves checkout binding;
- sales CTA replacement updates binding and validates checkout event attributes;
- candidate release is not activated on validation failure.

Frontend tests:

- runtime emits quiz view, option presented, selected, submitted, completed, result viewed, and CTA viewed events with stable IDs and current copy;
- runtime does not fire `EnteredSales` before sales page load;
- final CTA preserves canonical handoff fields;
- direct Meta Pixel bootstrap is used;
- no `/__mos/meta/*` URL appears in rendered standalone funnel pages.

Smoke tests:

- local candidate validation with mocked PostHog and direct Meta network routes;
- staging candidate validation with live PostHog readback;
- production activation dry-run report for a quiz-to-sales path;
- production activation dry-run report for direct sales page.

### Phase 9: Rollout Sequence

PR 1: Meta proxy removal alignment.

- Update docs and specs.
- Remove proxy stubs and unused helpers.
- Add forbidden `/__mos/meta/*` validation.
- Keep direct Meta Pixel tests green.

PR 2: Quiz contract and compiler.

- Add schema.
- Add compiler tests.
- Emit stable attributes.
- Emit manifest from contract.

PR 3: Manifest validation flows.

- Add `quizValidationFlows`.
- Validate flow references.
- Preserve `selectionOrder` compatibility for legacy artifacts only.

PR 4: Validator extraction.

- Extract current behavior without changing deploy semantics.
- Preserve report shape.
- Add contract registry.

PR 5: Multi-flow browser validation.

- Execute all declared quiz flows.
- Validate expected result, segment, offer, final CTA, and sales handoff per path.

PR 6: Production enforcement.

- Require live PostHog readback for production candidate activation.
- Require direct Meta Pixel network proof.
- Require persisted validation report.
- Fail all new dynamic quiz artifacts without declared validation flows.

## Definition Of Done

- Operators can change quiz copy without selector churn.
- Operators can change questions, answers, branches, and results only through a structured contract that updates HTML and manifest together.
- Every reachable result path has browser validation.
- Sales copy changes preserve stable checkout bindings.
- Sales CTA/template changes regenerate and validate bindings.
- PostHog readback proves required events landed with top-level canonical attributes.
- Direct Meta Pixel network validation proves required Pixel events were sent successfully.
- `/__mos/meta/*` is rejected in static HTML, runtime requests, nginx config, and validation docs.
- Candidate release activation is impossible until all required gates pass.
- Failure reports identify the missing selector, event, field, branch, destination, or asset without asking an operator to infer root cause.
