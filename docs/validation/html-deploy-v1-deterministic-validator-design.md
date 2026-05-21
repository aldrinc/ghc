# html-deploy-v1 Deterministic Validator Design

Decision: replace the current ad hoc deploy validation with a schema-driven deterministic validator for `html-deploy-v1`. The validator should compile a page-type contract from the artifact manifest, execute a declared browser path, verify exact event payloads at send time, and prove destination receipt through PostHog readback plus Meta delivery evidence.

This design builds on [html-deploy-v1-page-validation-spec.md](./html-deploy-v1-page-validation-spec.md).

## Problem

The current validator catches many failures, but it is still too procedural and too dependent on broad browser observations. That allowed two regressions:

- A sales deploy preserved `sales_page_view` and Meta `EnteredSales`, but lost the PostHog `EnteredSales` alias required by reporting.
- Listicle and quiz handoffs navigated to the sales page, but missing or inconsistent RMBC bridge fields broke attribution between `PreSalesToSalesClick` and downstream sales events.

The core issue is that the validation code did not treat the spec as a deterministic contract. It checked that calls happened, but not always that the exact required event names, attributes, relationships, and destination receipts existed for each page type.

## Goals

- Validate `listicle`, `listicle_hybrid`, `quiz`, and `sales` through one deterministic `html-deploy-v1` contract system.
- Make future page types additive through a contract registry, not one-off deploy code.
- Prove three layers for each required event:
  - artifact can produce the event;
  - browser/runtime sends the event with the expected attributes;
  - destination receives the event in the expected format.
- Fail closed with clear errors. No fallback deploy path should mask missing tracking.
- Produce a compact machine-readable report that can be attached to deploy jobs and PR checks.

## Non-Goals

- This is not a visual QA replacement. Visual parity, Lighthouse, and screenshot checks should remain separate validators that can share the same runner/report format.
- This is not a generic analytics warehouse. The readback queries should be tightly scoped to one validation run token.
- This should not depend on inferred button text or heuristic user flows when the manifest can declare deterministic selectors and actions.

## Solution Options

### Option 1: Patch The Current Validator

Keep the validator inside `mos/backend/app/services/deploy.py` and add more assertions.

Benefits:

- Fastest path.
- Minimal code movement.
- Lower immediate migration risk.

Problems:

- The file is already carrying too much deploy, browser, and analytics logic.
- Future page types will add more branching.
- It remains easy to validate “some event happened” rather than the exact contract.

Verdict: useful for immediate hotfixes, not robust enough as the long-term validator.

### Option 2: Schema-Driven Validator Inside MOS Backend

Create a dedicated backend validation package that compiles a contract from the artifact manifest and runs deterministic validation phases.

Benefits:

- One source of truth for page-type contracts.
- Clear separation between static artifact checks, browser send checks, and destination readback checks.
- Easy to add future page types by registering a new contract.
- Can run inside deploy jobs, CI, and local validation.

Problems:

- Requires a small refactor out of `deploy.py`.
- Requires new report schemas and destination adapters.

Verdict: recommended.

### Option 3: Separate Validator Service

Build a standalone validator service or CLI that MOS invokes after publishing.

Benefits:

- Clean isolation.
- Can run distributed validation jobs.
- Easier to scale if validation becomes heavy.

Problems:

- More infrastructure before we have a stable contract.
- Harder to wire into current publish jobs.
- More places for secrets and auth to drift.

Verdict: attractive later, overkill for the next implementation.

## Recommended Architecture

Build a dedicated package:

```text
mos/backend/app/services/html_deploy_validation/
  __init__.py
  contracts.py
  registry.py
  compiler.py
  static_checks.py
  browser_runner.py
  event_capture.py
  assertions.py
  report.py
  destinations/
    __init__.py
    posthog.py
    meta.py
```

`deploy.py` should only orchestrate:

```text
artifact payload
-> validation compiler
-> static checks
-> browser runner
-> destination adapters
-> report persistence
-> pass/fail deploy decision
```

## Contract Model

Each page type is represented as data, not hard-coded branching.

```python
class HtmlDeployPageContract(BaseModel):
    artifact_kind: Literal["listicle", "listicle_hybrid", "quiz", "sales"]
    page_stage: Literal["pre_sales", "sales"]
    required_manifest_bindings: list[BindingRequirement]
    browser_flow: BrowserFlow
    required_events: list[EventRequirement]
    relationship_assertions: list[RelationshipAssertion]
    forbidden_events: list[ForbiddenEventRequirement] = []
```

The registry maps artifact kinds to contracts:

```python
HTML_DEPLOY_CONTRACTS = {
    "listicle": ListicleContract,
    "listicle_hybrid": ListicleContract,
    "quiz": QuizContract,
    "sales": SalesContract,
}
```

Future page types add one registry entry and one contract definition.

## Event Requirement Model

Every expected event should define its required destinations and attributes.

```python
class EventRequirement(BaseModel):
    logical_name: str
    stage: str
    required_internal_event: str | None = None
    required_posthog_event: str | None = None
    required_meta_event: str | None = None
    required_props: list[PropRequirement]
    allowed_after: EventOrderingRequirement | None = None
    destination_receipt: list[Literal["posthog", "meta_pixel", "meta_test_events"]]
```

Example for sales entry:

```yaml
logical_name: sales_entry
required_internal_event: sales_page_view
required_posthog_event: EnteredSales
required_meta_event: EnteredSales
required_props:
  - page_stage == sales
  - content_category in [sales, sales_page]
  - session_id exists
  - visitor_id exists
destination_receipt:
  - posthog
  - meta_pixel
```

## Validation Phases

### Phase 1: Manifest Compilation

Input:

- artifact payload
- publication id
- access URL
- page manifests

Output:

- compiled validation plan
- path plans
- event requirements
- relationship assertions

Failure examples:

- missing `schemaVersion: html-deploy-v1`
- unsupported `htmlArtifactKind`
- `quiz` page not marked `pre_sales`
- `sales` page missing checkout binding
- listicle missing internal navigation binding to sales

### Phase 2: Static Artifact Validation

Checks:

- HTML contains the correct instrumentation manifest.
- HTML contains no forbidden legacy references.
- PostHog and Meta bootstrap snippets match the configured tracking payload.
- Meta Pixel loads directly from `https://connect.facebook.net/en_US/fbevents.js`.
- MOS Meta proxy paths such as `/__mos/meta/*` are rejected.
- Image references in `src` and `srcset` resolve to deployed assets.
- The artifact render mode is `html_deploy`.

This phase proves the artifact is structurally able to emit the expected calls.

### Phase 3: Deterministic Browser Flow

The runner executes only declared flow steps.

Example listicle flow:

```yaml
steps:
  - goto: entry_url
  - wait_for_event: EnteredPresales
  - click: internal_navigation.selector
  - wait_for_url: sales_page.url
  - wait_for_event: sales_page_view
  - click: checkout.selector
  - wait_for_event: SalesToCheckoutClick
```

Example quiz flow:

```yaml
steps:
  - goto: quiz_url
  - wait_for_event: QuizLeadViewed
  - execute_quiz_driver: declared_quiz_flow
  - wait_for_event: QuizResultViewed
  - click: final_cta.selector
  - wait_for_url: sales_page.url
  - wait_for_event: sales_page_view
  - assert_forbidden_before_event:
      forbidden: EnteredSales
      before: sales_page_view
```

Quiz should not rely on “first visible option” forever. The manifest should declare a deterministic validation path:

```json
{
  "validationFlow": {
    "type": "quiz",
    "steps": [
      {"selector": "[data-question='q1'] [data-option='a']", "action": "click"},
      {"selector": "[data-question='q1'] [data-next]", "action": "click"}
    ],
    "finalCtaSelector": "[data-tenor-final-cta]"
  }
}
```

For existing quiz artifacts that do not yet declare `validationFlow`, the compiler can use the current Heyflow driver as a transitional compatibility mode, but production validation should warn until the flow is declared. Once existing artifacts are migrated, undeclared quiz flows should fail.

### Phase 4: Send-Time Payload Validation

The browser runner captures outbound calls before they leave the page:

- `/api/public/events`
- PostHog capture endpoint
- direct Meta Pixel endpoint

For each captured event, the validator parses the request payload into a normalized event envelope:

```python
class ObservedEvent(BaseModel):
    destination: Literal["mos_public_events", "posthog", "meta"]
    event_name: str
    event_id: str | None
    validation_id: str
    url: str
    props: dict[str, Any]
    response_status: int | None
    response_ok: bool | None
```

Assertions:

- required event exists
- event name matches exactly
- required attributes exist
- attribute values match expected constants
- no forbidden events fired
- response status is 2xx where applicable

This phase proves the artifact can send the call in the expected format.

### Phase 5: Destination Receipt Validation

The validator must prove destination receipt independently of browser-side intent.

#### PostHog

PostHog receipt is proven with HogQL readback using a unique validation id.

Validation id placement:

- `mos_deploy_validation_id`
- `utm_campaign`
- `utm_content`
- `$current_url`
- `event_source_url`
- `destination_url`
- `url_params`

Readback requirements:

- query until timeout
- require exact event names
- require expected attributes
- require bridge values to match between pre-sales click and sales events
- fail with observed event list if missing

#### Meta

Meta browser pixel does not provide the same simple query surface as PostHog. The deterministic validator should support two receipt levels.

Level 1, required:

- Browser sends Meta event directly to Meta Pixel endpoints.
- Meta endpoint returns a successful response.
- Validator records event name, event id, pixel id, payload fields, response status, and response body hash.

Level 2, recommended when credentials are configured:

- Add a Meta validation adapter that uses Meta test-event infrastructure or a validation-only Conversions API mirror.
- Include `test_event_code` or equivalent validation marker only in validation runs.
- Query/confirm the event through the configured Meta validation API when supported.

The validator report must distinguish:

```text
meta_delivery_proof=direct_pixel_network
meta_delivery_proof=meta_test_event_confirmed
```

Production deploys should require at least `direct_pixel_network`. Environments with Meta validation credentials can require `meta_test_event_confirmed`.

## Page Type Contracts

### Listicle And Listicle Hybrid

Required flow:

```text
pre_sales load
-> sales CTA click
-> sales load
-> checkout CTA click
```

Required PostHog receipt:

```text
presell_page_view
EnteredPresales
cta_click
PreSalesToSalesClick
sales_page_view
EnteredSales
SalesToCheckoutClick
SalesToCheckoutClicked
```

Required Meta delivery:

```text
PageView
EnteredPresales
PreSalesToSalesClick
PageView
EnteredSales
ViewContent
SalesToCheckoutClick
SalesToCheckoutClicked
```

Required relationship assertions:

```text
PreSalesToSalesClick.destination_url contains rmbc_session_id
PreSalesToSalesClick.destination_url contains rmbc_anonymous_id
PreSalesToSalesClick.destination_url contains rmbc_click_id
sales_page_view.rmbc_session_id == PreSalesToSalesClick.rmbc_session_id
EnteredSales.rmbc_session_id == PreSalesToSalesClick.rmbc_session_id
sales_page_view.rmbc_click_id == PreSalesToSalesClick.rmbc_click_id
EnteredSales.rmbc_click_id == PreSalesToSalesClick.rmbc_click_id
```

### Quiz

Required flow:

```text
quiz load
-> deterministic quiz answer path
-> result view
-> final CTA click
-> sales load
-> checkout CTA click
```

Required PostHog receipt:

```text
EnteredPresales
QuizLeadViewed
QuizQuestionViewed
QuizOptionSelected
QuizCompleted
QuizResultViewed
QuizCtaViewed
PreSalesToSalesClick
sales_page_view
EnteredSales
SalesToCheckoutClick
SalesToCheckoutClicked
```

Required forbidden event assertion:

```text
EnteredSales must not fire before sales_page_view.
```

Required relationship assertions:

```text
quiz final CTA destination contains RMBC bridge params
quiz final CTA destination contains quiz params
sales_page_view preserves RMBC bridge params
EnteredSales preserves RMBC bridge params
```

### Sales

Required flow:

```text
sales load
-> checkout CTA click
```

Required PostHog receipt:

```text
sales_page_view
EnteredSales
SalesToCheckoutClick
SalesToCheckoutClicked
```

Required Meta delivery:

```text
PageView
EnteredSales
ViewContent
SalesToCheckoutClick
SalesToCheckoutClicked
```

Required context:

```text
page_stage=sales
content_category=sales_page
product_slug exists
funnel_slug exists
publication_id exists
page_id exists
page_slug exists
session_id exists
visitor_id exists
```

## Report Format

The validator should write one JSON report per run.

```json
{
  "schemaVersion": "html-deploy-validator-v1",
  "validationId": "deploy-validation-...",
  "artifactKind": "quiz",
  "renderMode": "html_deploy",
  "origin": "https://shoptenorco.com",
  "startUrl": "...",
  "salesUrl": "...",
  "status": "passed",
  "phases": {
    "manifest": {"status": "passed"},
    "static": {"status": "passed"},
    "browserSend": {"status": "passed"},
    "posthogReadback": {"status": "passed"},
    "metaDelivery": {"status": "passed", "proof": "direct_pixel_network"}
  },
  "observedEvents": [],
  "assertions": [],
  "failures": []
}
```

The deploy job should persist this report and include a compact summary:

```text
html-deploy-v1 validation passed
artifactKind=quiz
posthogReadback=confirmed
metaDelivery=direct_pixel_network
bridgeStitching=confirmed
```

## Failure Message Requirements

Every failure should identify:

- phase
- page URL
- event name
- destination
- missing or mismatched property
- observed value
- expected value
- validation id

Example:

```text
PostHog readback failed for sales page:
missing event EnteredSales for validation id deploy-validation-abc.
Observed events: sales_page_view, SalesToCheckoutClick.
This page is not production-valid because sales_page_view without EnteredSales breaks RMBC/Meta destination reporting.
```

## Implementation Plan

### Step 1: Extract Current Validation From deploy.py

Move validation functions into `html_deploy_validation/` without changing behavior:

- tracking plan compiler
- static HTML checks
- browser runner
- observed event assertions
- PostHog readback

Acceptance:

- Existing deploy tests pass.
- Public function from `deploy.py` still returns the same validation summary.

### Step 2: Add Contract Registry

Create page-type contracts for:

- `listicle`
- `listicle_hybrid`
- `quiz`
- `sales`

Acceptance:

- Unsupported `htmlArtifactKind` fails.
- Incorrect `pageStage` fails.
- Missing required bindings fail.

### Step 3: Normalize Observed Events

Implement event normalization for:

- MOS internal events
- PostHog browser capture
- PostHog readback rows
- direct Meta Pixel requests
- direct Meta Pixel responses

Acceptance:

- The same assertion code can validate send-time events and destination readback events.

### Step 4: Add Deterministic Browser Flow Runner

Compile each path into declared actions:

- `goto`
- `click`
- `wait_for_url`
- `wait_for_event`
- `assert_forbidden_before_event`
- `execute_quiz_flow`

Acceptance:

- Listicle and sales paths use manifest selectors only.
- Quiz has a declared validation flow or transitional Heyflow driver.
- Missing selectors fail with a clean error.

### Step 5: Implement Destination Adapters

PostHog adapter:

- HogQL query by validation id
- bounded polling
- exact event/property validation

Meta adapter:

- proxy-forward response validation
- event payload validation
- optional Meta test-event confirmation when credentials are configured

Acceptance:

- The validator can prove `artifact sent` and `destination received` separately.

### Step 6: Add Relationship Assertion Engine

Implement reusable assertions:

- property exists
- property equals
- property in set
- URL contains query params
- event A property equals event B property
- event B occurs only after event A
- forbidden event absent before condition

Acceptance:

- Presales-to-sales bridge stitching is expressed as data.
- Quiz `EnteredSales` timing rule is expressed as data.

### Step 7: Wire Into Publish Job

Deploy job behavior:

- validation runs after artifact deploy and CDN purge
- failure marks publish job failed
- no production-ready result without validator pass
- report is stored with the publish job result

Acceptance:

- A page missing PostHog `EnteredSales` fails.
- A page missing RMBC bridge fields fails.
- A page with direct Meta Pixel delivery failure fails.

## Configuration

Recommended production settings:

```text
DEPLOY_TRACKING_VALIDATION_REQUIRE_POSTHOG_READBACK=true
DEPLOY_TRACKING_VALIDATION_POSTHOG_READBACK_API_KEY=<secret>
DEPLOY_TRACKING_VALIDATION_POSTHOG_READBACK_TIMEOUT_SECONDS=120
DEPLOY_TRACKING_VALIDATION_POSTHOG_READBACK_POLL_SECONDS=7
DEPLOY_TRACKING_VALIDATION_REQUIRE_META_DELIVERY=true
DEPLOY_TRACKING_VALIDATION_REQUIRE_META_TEST_EVENT_CONFIRMATION=false
```

Optional Meta test-event settings:

```text
DEPLOY_TRACKING_VALIDATION_META_TEST_EVENT_CODE=<secret>
DEPLOY_TRACKING_VALIDATION_META_ACCESS_TOKEN=<secret>
DEPLOY_TRACKING_VALIDATION_REQUIRE_META_TEST_EVENT_CONFIRMATION=true
```

## Test Plan

Unit tests:

- contract registry rejects unsupported types
- listicle contract compiles expected events
- quiz contract compiles quiz-specific events
- sales contract requires `EnteredSales`
- bridge relationship assertions fail on missing params
- PostHog adapter polls until events land
- Meta adapter fails on non-2xx direct Pixel delivery

Integration tests:

- deploy a local listicle + sales artifact and validate readback against mocked PostHog/Meta adapters
- deploy a local quiz + sales artifact and validate quiz-specific events
- assert `EnteredSales` does not fire before sales page load
- assert missing `SalesToCheckoutClicked` fails

Production smoke:

- run validator against a staging route with real PostHog readback
- run validator against direct Meta Pixel network delivery in delivery-proof mode
- store validation report as deploy artifact evidence

## Migration Strategy

1. Keep the current validator as the compatibility runner while extracting it into the new package.
2. Add contract registry and report format.
3. Enable strict listicle/sales contracts.
4. Enable strict quiz contracts with transitional Heyflow driver.
5. Require declared quiz `validationFlow` for all new quiz artifacts.
6. Disable legacy standalone/manual deploy paths for production HTML funnels.

## Open Decisions

1. Should production require direct Meta Pixel network delivery only, or Meta test-event confirmation when credentials are available?
2. Should quiz artifacts without declared `validationFlow` fail immediately, or warn during a short migration window?
3. Should validation reports be stored as deploy-job JSON only, or also persisted as first-class artifact records?
4. Should CI run destination adapters against mocked services only, with live destination validation reserved for post-deploy?

## Recommended Next Step

Implement Option 2 in two PRs:

1. Extract and contract-compile the current validator without behavior changes.
2. Add destination adapters, relationship assertions, and strict page-type contracts.

This keeps the first PR reviewable while moving us toward the deterministic validator that prevents the exact tracking regressions we saw in the sales, listicle, and quiz deployments.
