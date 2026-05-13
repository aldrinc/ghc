# html-deploy-v1 Page Validation Spec

Decision: production HTML funnel pages must deploy and validate through `html-deploy-v1`. Legacy standalone deploy flows, ad hoc route-scoped HTML copies, and manual production HTML replacements are not acceptable production deploy paths unless there is an explicit break-glass approval in the current thread.

This spec covers the three supported production page classes:

- `listicle` and `listicle_hybrid`
- `quiz`
- `sales`

## Required Artifact Contract

Every deployed page must include an instrumentation manifest:

```json
{
  "schemaVersion": "html-deploy-v1",
  "htmlArtifactKind": "listicle | listicle_hybrid | quiz | sales",
  "pageStage": "pre_sales | sales",
  "bindings": []
}
```

Page-stage requirements:

| Artifact kind | Required page stage | Harness |
|---|---:|---|
| `listicle` | `pre_sales` | Listicle presales harness |
| `listicle_hybrid` | `pre_sales` | Listicle presales harness |
| `quiz` | `pre_sales` | Quiz presales harness |
| `sales` | `sales` | Sales harness |

## Global Validation Gates

These gates apply to every `html-deploy-v1` page.

### Deployment Path

- The page must deploy through `html-deploy-v1`.
- Production deploys must prefer the `main` -> GitHub -> CI/CD path.
- Direct production access is only allowed with explicit approval in the current thread.
- Direct production access must still use the `html-deploy-v1` artifact contract.

### Static HTML Safety

The deployed HTML must not contain forbidden legacy references:

- `mengotomars.com`
- `Mars Men`
- `Mars Health`
- `shopmars`
- `mymars`
- legacy route token `c9095d`

The deployed browser runtime must also not request forbidden legacy URLs.

### Asset Validation

The HTML deploy flow must validate image references before the artifact is considered production viable:

- `img[src]`
- `img[srcset]`
- `source[srcset]`
- route-local assets
- uploaded public asset URLs

Missing image assets must fail deploy validation. Broken browser images must fail post-deploy validation.

### Tracking Bootstrap Validation

When tracking is configured:

- Meta Pixel must load through the MOS proxy.
- Direct legacy or foreign Meta scripts are rejected.
- PostHog bootstrap must be present.
- PostHog `api_host`, `ui_host`, defaults, and person-profile settings must match the published tracking config.
- `/public/events` requests must return 2xx.

### Live PostHog Readback

Production validation must prove events landed in PostHog, not only that the browser attempted to send them.

Required production configuration:

```text
DEPLOY_TRACKING_VALIDATION_REQUIRE_POSTHOG_READBACK=true
DEPLOY_TRACKING_VALIDATION_POSTHOG_READBACK_API_KEY=<PostHog project read key>
DEPLOY_TRACKING_VALIDATION_POSTHOG_READBACK_TIMEOUT_SECONDS=120
DEPLOY_TRACKING_VALIDATION_POSTHOG_READBACK_POLL_SECONDS=7
```

The validator appends a unique deploy-validation token to the entry URL, executes the page path, then polls PostHog until the required events are queryable for that token.

## Listicle And Listicle Hybrid Validation

`listicle` and `listicle_hybrid` both use the listicle presales harness.

### Required Navigation Binding

The presales page must include an internal navigation binding to the sales page:

```json
{
  "type": "internal_navigation",
  "selector": "#to-sales",
  "targetPageId": "<sales-page-id>",
  "trackEventType": "pre_sales_to_sales_click"
}
```

### Required Browser Path

The validator must execute:

```text
listicle/listicle_hybrid page load
-> visible sales CTA click
-> sales page load
-> sales checkout CTA click
```

### Required PostHog Readback Events

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

### Required Meta Events

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

### Required RMBC Bridge Fields

`PreSalesToSalesClick` must include:

```text
rmbc_session_id
rmbc_anonymous_id
rmbc_click_id
destination_url
from_stage=pre_sales
to_stage=sales
```

The `destination_url` must preserve:

```text
rmbc_session_id
rmbc_anonymous_id
rmbc_click_id
src=presale
```

Downstream sales events must stitch back to the click using the same bridge values:

```text
sales_page_view.rmbc_session_id == PreSalesToSalesClick.rmbc_session_id
sales_page_view.rmbc_anonymous_id == PreSalesToSalesClick.rmbc_anonymous_id
sales_page_view.rmbc_click_id == PreSalesToSalesClick.rmbc_click_id
EnteredSales.rmbc_session_id == PreSalesToSalesClick.rmbc_session_id
EnteredSales.rmbc_anonymous_id == PreSalesToSalesClick.rmbc_anonymous_id
EnteredSales.rmbc_click_id == PreSalesToSalesClick.rmbc_click_id
```

## Quiz Funnel Validation

`quiz` uses the quiz presales harness. It inherits every listicle presales-to-sales bridge requirement and adds quiz-specific event requirements.

### Required Browser Path

The validator must execute:

```text
quiz page load
-> quiz lead/question/options flow
-> quiz result view
-> quiz final CTA click
-> sales page load
-> sales checkout CTA click
```

### Required PostHog Readback Events

Quiz funnels must include the shared presales-to-sales events:

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

Quiz funnels must also include quiz-specific readback events:

```text
QuizLeadViewed
QuizQuestionViewed
QuizOptionSelected
QuizCompleted
QuizResultViewed
QuizCtaViewed
```

### Required Meta Events

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

### Quiz-Specific Sales Entry Rule

`EnteredSales` must not fire on:

- quiz page load
- quiz question navigation
- quiz result render
- quiz final CTA click before navigation completes

`EnteredSales` may fire only after the browser reaches the sales page and records `sales_page_view`.

### Required Quiz Bridge Fields

The quiz final CTA must preserve the RMBC bridge fields into the sales URL:

```text
rmbc_session_id
rmbc_anonymous_id
rmbc_click_id
rmbc_quiz_id
rmbc_quiz_version
rmbc_quiz_variant
rmbc_result_id
rmbc_segment_id
rmbc_offer_id
rmbc_answer_path_hash
session_id
anonymous_id
click_id
click_id_type=rmbc_click_id
bridge_click_id
src=presale
from=quiz
from_stage=pre_sales
to_stage=sales
source_page=quiz
source_page_type=quiz_presell
mos_session_id
mos_visitor_id
```

Downstream `sales_page_view` and `EnteredSales` must preserve the same bridge values.

## Sales Page Validation

`sales` uses the sales harness.

### Required Checkout Binding

The sales page must include a checkout binding:

```json
{
  "type": "checkout",
  "selector": "#checkout-btn",
  "trackEventType": "sales_to_checkout_click",
  "checkout": {
    "mode": "public_checkout"
  }
}
```

### Required Browser Path

The validator must execute:

```text
sales page load
-> sales checkout CTA click
```

For presales-attributed validation, the sales page must also be reached from a listicle/listicle-hybrid or quiz start page.

### Required PostHog Readback Events

```text
sales_page_view
EnteredSales
SalesToCheckoutClick
SalesToCheckoutClicked
```

### Required Meta Events

```text
PageView
EnteredSales
ViewContent
SalesToCheckoutClick
SalesToCheckoutClicked
```

### Required Sales Event Context

`sales_page_view` and `EnteredSales` must include:

```text
product_slug
funnel_slug
publication_id
page_id
page_slug
page_stage=sales
content_category=sales_page
session_id
visitor_id
```

When reached from a presales page, they must also include:

```text
rmbc_session_id
rmbc_anonymous_id
rmbc_click_id
src=presale
```

### Sales Entry Regression Guard

A sales page is not production-valid if it emits only `sales_page_view`.

It must emit:

```text
sales_page_view
EnteredSales
```

Both events must be visible in live PostHog readback for the same deploy-validation token.

## Regression Classes This Spec Prevents

### Sales Page Alias Regression

Prior failure:

```text
sales_page_view landed in PostHog
Meta EnteredSales fired
PostHog EnteredSales did not land
```

Required guard:

```text
PostHog readback must include both sales_page_view and EnteredSales.
```

### Presales-To-Sales Stitching Regression

Prior failure:

```text
PreSalesToSalesClick fired
sales_page_view fired
bridge fields were missing or inconsistent
funnel attribution broke between pages
```

Required guard:

```text
PreSalesToSalesClick.destination_url must include RMBC bridge fields.
Downstream sales_page_view and EnteredSales must contain the same bridge values.
```

### Quiz Final CTA Regression

Prior failure risk:

```text
Quiz final CTA could navigate to sales without preserving all RMBC bridge params.
```

Required guard:

```text
Quiz final CTA must preserve quiz and RMBC bridge fields into sales.
EnteredSales must fire only after sales_page_view.
Quiz-specific PostHog events must land before the sales transition is considered valid.
```
