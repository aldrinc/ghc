# RMBC Quiz Funnel Analytics Spec

Prepared: May 4, 2026

## Decision

Instrument the quiz funnel as a diagnostic pre-sell surface with two required bridge events:

- `EnteredPresales` fires once on quiz entrance.
- `PreSalesToSalesClick` fires when the visitor exits the quiz/pre-sell experience toward the sales page.

The quiz should also track question exposure, option exposure, option selection, answer changes, completion, result/recommendation exposure, and downstream purchase economics. Do not treat quiz completion rate, result-page view rate, or sales-page click rate as the final winner signal. The real decision metrics are sales-page arrival, checkout behavior, purchase conversion, revenue per visitor, AOV, subscription attach where applicable, and buyer-quality guardrails.

## Purpose

This spec defines the analytics needed to diagnose a quiz funnel that sits before a sales page. The goal is not a generic event map. The goal is to make the quiz funnel explainable:

- Are visitors entering the quiz from the intended traffic sources?
- Do they understand the opening promise and start answering?
- Which questions or options create dropoff, hesitation, or disqualification?
- Which user-selected options map to better downstream intent and purchase quality?
- Does the quiz result/recommendation create a clean bridge to the sales page?
- Does the sales page preserve the promise created by the quiz?
- Are variants producing profitable buyers, not just more quiz completions or clicks?

## Funnel Chain

The full path should be queryable from traffic entry through buyer quality:

```text
entry_click
  -> EnteredPresales
  -> QuizQuestionViewed
  -> QuizOptionPresented
  -> QuizOptionSelected / QuizOptionDeselected
  -> QuizQuestionSubmitted
  -> QuizCompleted
  -> QuizResultViewed
  -> QuizRecommendationViewed
  -> QuizCtaViewed
  -> PreSalesToSalesClick
  -> sales_page_view
  -> purchase_intent_click
  -> checkout_page_view
  -> checkout_start
  -> payment_info_entered
  -> purchase
  -> subscription_start
  -> refund / chargeback / subscription_cancel / repeat_purchase
```

If instrumentation is limited, the minimum viable chain is:

```text
EnteredPresales
  -> QuizQuestionViewed
  -> QuizOptionSelected
  -> QuizCompleted
  -> QuizCtaViewed
  -> PreSalesToSalesClick
  -> sales_page_view
  -> purchase
```

## Critical Distinction

Do not call a quiz winner on quiz completion rate or sales-page click rate alone.

| Layer | Example Metrics | What It Measures |
| --- | --- | --- |
| Quiz engagement | `QuizQuestionViewed`, `QuizOptionSelected`, `QuizCompleted` | Whether visitors participate |
| Bridge intent | `QuizCtaViewed`, `PreSalesToSalesClick` | Whether visitors accept the recommendation and move downstream |
| Sales-page integrity | `sales_page_view / PreSalesToSalesClick` | Whether the handoff works technically and preserves tracking |
| Purchase conversion | `purchase / EnteredPresales`, `purchase / PreSalesToSalesClick` | Whether quiz intent becomes revenue |
| Revenue quality | `RPV`, `AOV`, `subscription_attach`, `refund_rate`, `chargeback_rate` | Whether the revenue is good revenue |

A quiz can increase completion or click-through by making questions easier, more curiosity-driven, or more flattering. That is not a win unless downstream purchase rate, revenue, and buyer quality hold or improve.

## Core Metrics

### 1. Click-To-Quiz Load Rate

**Stage:** Entry and message match

**Definition:** Percentage of upstream clicks that become a real quiz entrance.

**Formula:**

```text
EnteredPresales / entry_click
```

**Required events:**

- `entry_click`
- `EnteredPresales`

**Why it matters:** If this is broken, visitors never experience the quiz. Fix the traffic path before editing quiz copy.

**Diagnoses:**

- Broken URL or redirect chain
- Slow quiz load
- Tracking loss
- Bot or accidental clicks
- Upstream promise mismatch

### 2. Qualified Quiz Visitor Rate

**Stage:** Entry and traffic quality

**Definition:** Percentage of quiz entrances that show minimum human intent.

**Formula:**

```text
qualified_quiz_sessions / EnteredPresales
```

Recommended starting qualification:

```text
active_time >= 3 seconds
OR QuizQuestionViewed(question_index = 1)
OR any_option_interaction = true
```

**Required events:**

- `EnteredPresales`
- `QuizQuestionViewed`
- `QuizOptionSelected`
- active-time heartbeat or equivalent session activity

**Why it matters:** It separates real prospects from accidental clicks, bots, and low-intent traffic.

### 3. Quiz Start Rate

**Stage:** Opening promise and first-step clarity

**Definition:** Percentage of quiz entrants who see the first question.

**Formula:**

```text
QuizQuestionViewed(question_index = 1) / EnteredPresales
```

**Why it matters:** Low start rate means the quiz entrance screen, load behavior, or first screen promise is failing before the diagnostic portion begins.

**Diagnoses:**

- Opening screen unclear
- Start button hidden below fold on mobile
- Quiz loads slowly
- Lead promise does not match the ad/pre-sell angle
- Modal, cookie banner, or layout issue blocks the first step

### 4. First Answer Rate

**Stage:** Initial participation

**Definition:** Percentage of quiz entrants who select at least one option on question one.

**Formula:**

```text
QuizOptionSelected(question_index = 1) / EnteredPresales
```

**Why it matters:** The first question has to feel easy, relevant, and safe to answer. It should confirm the quiz is about the visitor's problem, not ask for high-friction information too early.

**Diagnoses:**

- First question is too personal or too hard
- Options do not match user self-perception
- The value of answering is unclear
- Multi-select behavior is confusing

### 5. Per-Question Completion Rate

**Stage:** Question flow

**Definition:** Percentage of visitors who submit each question after viewing it.

**Formula:**

```text
QuizQuestionSubmitted(question_id) / QuizQuestionViewed(question_id)
```

**Why it matters:** This identifies the exact question causing friction.

**Diagnoses:**

- Required answer is unclear
- None of the options fit
- Question asks for information before trust is earned
- Layout or tap targets fail on mobile
- Skip/continue state is unclear

### 6. Question Dropoff Rate

**Stage:** Question flow

**Definition:** Percentage of sessions that stop after viewing a question without submitting it.

**Formula:**

```text
(QuizQuestionViewed(question_id) - QuizQuestionSubmitted(question_id)) / QuizQuestionViewed(question_id)
```

**Why it matters:** It localizes abandonment to a specific question, option set, or UX pattern.

### 7. Option Selection Distribution

**Stage:** User-option tracking

**Definition:** Share of submitted answers choosing each option.

**Formula:**

```text
QuizOptionSelected(option_id) / QuizQuestionSubmitted(question_id)
```

For multi-select questions, track both:

```text
sessions_selecting_option / sessions_submitting_question
total_option_selections / total_submitted_answers
```

**Why it matters:** This is the core user-option telemetry. It shows audience composition, self-diagnosis patterns, qualification, and which answer paths produce downstream revenue.

**Required events:**

- `QuizOptionPresented`
- `QuizOptionSelected`
- `QuizOptionDeselected` for multi-select or editable questions
- `QuizQuestionSubmitted`

**Diagnoses:**

- Options do not cover the audience
- One option dominates because wording biases the answer
- High downstream refunds cluster around one option
- A high-volume option does not map to a strong result or offer
- A low-volume option produces high RPV and deserves a targeted variant

### 8. Option Change / Backtrack Rate

**Stage:** User-option confidence

**Definition:** Percentage of question viewers who change an answer, deselect an option, or go back to a previous question.

**Formulas:**

```text
QuizOptionDeselected / QuizOptionSelected
QuizBackClick / QuizQuestionViewed
sessions_with_answer_revision / QuizQuestionViewed
```

**Why it matters:** Answer changes can signal thoughtful engagement, but high rates usually mean question wording or option mapping is confusing.

### 9. Validation Error Rate

**Stage:** Quiz UX integrity

**Definition:** Percentage of question viewers who encounter a validation or continue-blocking error.

**Formula:**

```text
QuizValidationError / QuizQuestionViewed
```

**Why it matters:** Validation errors are friction, not persuasion data. Segment by device and browser before interpreting question performance.

### 10. Quiz Completion Rate

**Stage:** Completion and segmentation

**Definition:** Percentage of quiz entrants who complete the required question flow and receive or become eligible for a result.

**Formula:**

```text
QuizCompleted / EnteredPresales
```

Also track:

```text
QuizCompleted / qualified_quiz_sessions
QuizCompleted / QuizQuestionViewed(question_index = 1)
```

**Why it matters:** Completion is the quiz's main engagement output. It is not the final conversion signal.

**Diagnoses:**

- Too many questions
- Question order creates fatigue
- High-friction questions appear too early
- Progress indicator discourages completion
- Mobile experience is too slow or cramped

### 11. Result Assignment Rate

**Stage:** Recommendation logic

**Definition:** Percentage of completed quizzes that successfully produce a result segment and recommended sales-page destination.

**Formula:**

```text
QuizResultViewed / QuizCompleted
```

**Required properties:**

- `result_id`
- `segment_id`
- `recommendation_id`
- `offer_id`
- `destination_url`

**Why it matters:** If completion is healthy but result viewing fails, the issue is logic, rendering, or bridge setup.

### 12. Recommendation Engagement Rate

**Stage:** Result and offer bridge

**Definition:** Percentage of completed quiz sessions that view the recommended offer, result explanation, or bridge copy.

**Formula:**

```text
QuizRecommendationViewed / QuizCompleted
```

**Why it matters:** The result page must translate the user's answers into a credible reason to continue. This is the quiz equivalent of mechanism/proof comprehension.

**Diagnoses:**

- Result copy is too generic
- Recommendation does not reflect selected options
- Mechanism is not tied to answer path
- Proof or credibility is missing before the CTA
- Result page over-explains and loses momentum

### 13. Quiz CTA Exposure Rate

**Stage:** CTA and bridge behavior

**Definition:** Percentage of completed quiz sessions that see at least one sales-page CTA.

**Formula:**

```text
QuizCtaViewed / QuizCompleted
```

**Why it matters:** Low click rate may simply mean visitors never saw the ask.

### 14. Quiz-To-Sales Click Rate

**Stage:** Exit intent

**Definition:** Percentage of quiz entrants or completers who click from the quiz/pre-sell experience to the sales page.

**Formulas:**

```text
PreSalesToSalesClick / EnteredPresales
PreSalesToSalesClick / QuizCompleted
PreSalesToSalesClick / QuizCtaViewed
```

**Required event:**

- `PreSalesToSalesClick`

**Why it matters:** This is the quiz's primary bridge event, but it is still only an intermediate signal.

**Diagnoses:**

- CTA is vague
- Result does not create conviction
- Recommendation feels mismatched to selected answers
- Sales-page destination is not clear
- Result page lacks proof, mechanism, or risk reversal

### 15. Quiz-To-Sales Bridge Integrity Rate

**Stage:** Technical handoff

**Definition:** Percentage of quiz-to-sales clicks that become downstream sales page views.

**Formula:**

```text
sales_page_view / PreSalesToSalesClick
```

**Why it matters:** If visitors click but do not reach the sales page, the problem is usually technical, routing, or tracking-related.

**Diagnoses:**

- Broken destination URL
- Redirect issue
- Sales page loads slowly
- Click/session ID lost during handoff
- Result-specific destination route fails
- Mobile webview blocks the redirect

### 16. Quiz-Attributed Purchase Conversion Rate

**Stage:** Downstream purchase economics

**Definition:** Percentage of quiz entrants, completers, or sales-clickers who eventually purchase.

**Formulas:**

```text
purchase / EnteredPresales
purchase / QuizCompleted
purchase / PreSalesToSalesClick
```

**Why it matters:** This is the real conversion signal. It shows whether quiz participation and recommendation intent became money.

### 17. Revenue Per Quiz Visitor And EPC

**Stage:** Economics

**Definitions:**

- **RPQV:** Revenue per quiz visitor
- **EPC:** Revenue per upstream paid click

**Formulas:**

```text
RPQV = revenue / EnteredPresales
EPC = revenue / entry_click
```

**Why it matters:** A quiz can lower sales-click rate but improve revenue if it sends better-qualified buyers.

### 18. Answer Path Revenue Quality

**Stage:** User-option quality

**Definition:** Revenue and buyer-quality outcomes grouped by selected options, result segment, and answer path.

**Core cuts:**

```text
purchase / QuizOptionSelected(option_id)
RPQV by option_id
AOV by option_id
refund_rate by option_id
subscription_attach by option_id
chargeback_rate by option_id
```

**Why it matters:** This is how option tracking becomes useful. It shows which user-reported problems, goals, objections, or situations produce qualified buyers.

**Guardrail:** Do not optimize toward an answer path purely because it clicks. Require downstream purchase and buyer-quality checks.

### 19. Buyer Quality Score

**Stage:** Buyer-quality guardrails

**Definition:** Composite view of whether the quiz produces good buyers, not just more buyers.

Recommended components:

| Component | Formula | Direction |
| --- | --- | --- |
| Subscription attach | `subscription_purchase / total_purchase` | Higher is better |
| Refund rate | `refund / purchase` | Lower is better |
| Chargeback rate | `chargeback / purchase` | Lower is better |
| AOV | `total_revenue / purchase` | Higher is usually better |
| Repeat purchase | `customers_with_2plus_orders / total_customers` | Higher is better |

Suggested formula:

```text
buyer_quality_score = weighted score vs. 90-day baseline
```

Suggested weights:

- Subscription attach: 30%
- Refund rate: 25%
- Chargeback rate: 20%
- AOV: 15%
- Repeat purchase: 10%

## Event Schema

### Common Properties

Every event should include as many of these as possible:

| Property | Purpose |
| --- | --- |
| `event_id` | Deduplication |
| `timestamp` | Sequencing and attribution |
| `session_id` | Session stitching |
| `anonymous_id` or `user_id` | Visitor stitching |
| `click_id` | Ad/pre-sell/email click chain |
| `quiz_id` | Quiz identity |
| `quiz_version` | Versioned quiz content and logic |
| `quiz_variant` | A/B test variant |
| `experiment_id` | Experiment grouping |
| `page_id` | Page identity |
| `page_type` | `quiz_presell`, `sales_page`, `pdp`, `offer_page` |
| `traffic_source` | Paid social, native, search, email, organic, direct |
| `referrer_type` | Ad, advertorial, listicle, email, search, direct |
| `campaign_id` | Campaign segmentation |
| `adset_id` | Ad set segmentation |
| `ad_id` | Ad segmentation |
| `creative_id` | Creative diagnosis |
| `utm_source` | UTM source |
| `utm_medium` | UTM medium |
| `utm_campaign` | UTM campaign |
| `utm_content` | Angle or creative |
| `device_type` | Mobile, tablet, desktop |
| `viewport_width` | Layout QA |
| `viewport_height` | Layout QA |
| `browser` | Browser QA |
| `geo` | Market / region |
| `awareness_level` | RMBC awareness calibration |
| `angle` | Quiz or creative angle |
| `mechanism_name` | Mechanism being presented |
| `offer_id` | Recommended downstream offer |
| `sku` | Product identity where known |
| `price_point` | Price shown where known |
| `result_id` | Assigned quiz result |
| `segment_id` | Audience or diagnostic segment |
| `destination_url` | Handoff URL for bridge QA |

### Option Tracking Contract

Use stable IDs, not display copy, as the primary analytics keys.

- `question_id` must be stable inside a `quiz_version`.
- `option_id` must be stable inside a `question_id`.
- Do not reuse an `option_id` after changing the option's meaning.
- If the visible label changes but the meaning does not, keep the same `option_id` and update metadata.
- If the meaning changes, create a new `option_id`.
- For multi-select questions, emit one event per option selected/deselected and submit the final selected set on `QuizQuestionSubmitted`.
- For ranking or slider questions, store the structured value in `answer_value` and the normalized bucket in `answer_bucket`.
- Prefer configured categories and IDs over raw free-text answers.
- Do not collect raw PII or sensitive free text unless explicitly authorized and covered by the relevant privacy/compliance flow.
- Store human-readable labels in metadata tables when possible; analytics events should remain compact and stable.

### `EnteredPresales`

Fires once when the quiz/pre-sell experience is entered and the app can emit a first-party event.

Required properties:

- `event_id`
- `timestamp`
- `session_id`
- `anonymous_id` or `user_id`
- `click_id` when available
- `quiz_id`
- `quiz_version`
- `quiz_variant`
- `page_id`
- `page_type = quiz_presell`
- `device_type`

Recommended properties:

- `load_time_ms`
- `dom_interactive_ms`
- `viewport_width`
- `viewport_height`
- `referrer`
- `traffic_source`
- `campaign_id`
- `adset_id`
- `ad_id`
- `creative_id`
- `utm_source`
- `utm_medium`
- `utm_campaign`
- `utm_content`
- `angle`
- `mechanism_name`

Deduplication rule:

```text
one EnteredPresales per session_id + quiz_id + quiz_version + landing_page_instance
```

### `QuizQuestionViewed`

Fires when a question becomes visible.

Required properties:

- `session_id`
- `quiz_id`
- `quiz_version`
- `quiz_variant`
- `question_id`
- `question_key`
- `question_index`
- `question_type`
- `is_required`
- `timestamp`

Recommended properties:

- `progress_pct`
- `question_count`
- `section_id`
- `depth_pct`

### `QuizOptionPresented`

Fires when an answer option is visible to the user. This can be emitted as individual events or as an array on `QuizQuestionViewed` if the analytics destination supports structured arrays cleanly.

Required properties:

- `session_id`
- `quiz_id`
- `quiz_version`
- `quiz_variant`
- `question_id`
- `question_index`
- `option_id`
- `option_key`
- `option_position`
- `timestamp`

Recommended properties:

- `option_bucket`
- `option_category`
- `maps_to_segment_id`
- `maps_to_result_id`
- `maps_to_offer_id`

### `QuizOptionSelected`

Fires when a visitor selects an option.

Required properties:

- `session_id`
- `quiz_id`
- `quiz_version`
- `quiz_variant`
- `question_id`
- `question_index`
- `question_type`
- `option_id`
- `option_key`
- `option_position`
- `selection_order`
- `timestamp`

Recommended properties:

- `answer_value`
- `answer_bucket`
- `is_multi_select`
- `selected_count`
- `maps_to_segment_id`
- `maps_to_result_id`
- `maps_to_offer_id`

### `QuizOptionDeselected`

Fires when a visitor removes a selected option.

Required properties:

- `session_id`
- `quiz_id`
- `quiz_version`
- `quiz_variant`
- `question_id`
- `question_index`
- `option_id`
- `option_key`
- `timestamp`

### `QuizQuestionSubmitted`

Fires when the visitor advances past a question.

Required properties:

- `session_id`
- `quiz_id`
- `quiz_version`
- `quiz_variant`
- `question_id`
- `question_index`
- `question_type`
- `selected_option_ids`
- `timestamp`

Recommended properties:

- `time_on_question_ms`
- `answer_revision_count`
- `validation_error_count`
- `progress_pct`
- `next_question_id`

### `QuizBackClick`

Fires when the visitor returns to a previous question or step.

Required properties:

- `session_id`
- `quiz_id`
- `quiz_version`
- `quiz_variant`
- `from_question_id`
- `to_question_id`
- `timestamp`

### `QuizValidationError`

Fires when the quiz blocks progression because of missing or invalid input.

Required properties:

- `session_id`
- `quiz_id`
- `quiz_version`
- `quiz_variant`
- `question_id`
- `question_index`
- `error_type`
- `timestamp`

### `QuizCompleted`

Fires when the visitor completes the required question flow.

Required properties:

- `session_id`
- `quiz_id`
- `quiz_version`
- `quiz_variant`
- `question_count_answered`
- `result_id`
- `segment_id`
- `timestamp`

Recommended properties:

- `completion_time_ms`
- `answer_path_id`
- `answer_path_hash`
- `recommended_offer_id`
- `recommended_sku`
- `mechanism_name`

### `QuizResultViewed`

Fires when the result screen becomes visible.

Required properties:

- `session_id`
- `quiz_id`
- `quiz_version`
- `quiz_variant`
- `result_id`
- `segment_id`
- `timestamp`

Recommended properties:

- `result_template_id`
- `answer_path_id`
- `recommended_offer_id`
- `recommended_sku`

### `QuizRecommendationViewed`

Fires when the recommendation, mechanism bridge, or product/result explanation is visible.

Required properties:

- `session_id`
- `quiz_id`
- `quiz_version`
- `quiz_variant`
- `result_id`
- `recommendation_id`
- `offer_id`
- `timestamp`

Recommended properties:

- `section_id`
- `mechanism_name`
- `proof_type`
- `price_point`

### `QuizCtaViewed`

Fires when a sales-page CTA enters the viewport.

Required properties:

- `session_id`
- `quiz_id`
- `quiz_version`
- `quiz_variant`
- `cta_id`
- `cta_position`
- `result_id`
- `offer_id`
- `destination_url`
- `timestamp`

Recommended properties:

- `cta_text`
- `depth_pct`
- `section_id`

### `PreSalesToSalesClick`

Fires when the visitor clicks from the quiz/pre-sell experience to the downstream sales page.

Required properties:

- `event_id`
- `timestamp`
- `session_id`
- `anonymous_id` or `user_id`
- `click_id` when available
- `quiz_id`
- `quiz_version`
- `quiz_variant`
- `cta_id`
- `cta_position`
- `result_id`
- `segment_id`
- `offer_id`
- `destination_url`

Recommended properties:

- `cta_text`
- `click_number`
- `answer_path_id`
- `answer_path_hash`
- `recommended_sku`
- `mechanism_name`
- `selected_option_ids_by_question`
- `utm_source`
- `utm_medium`
- `utm_campaign`
- `utm_content`

Bridge requirement:

```text
PreSalesToSalesClick.session_id should stitch to sales_page_view.session_id.
PreSalesToSalesClick.click_id should carry through to purchase when available.
PreSalesToSalesClick.offer_id should match the downstream sales_page_view.offer_id.
```

### Downstream Events

Use the sales-page framework for downstream behavior. At minimum, the quiz spec needs:

- `sales_page_view`
- `section_view`
- `offer_stack_view`
- `selector_interaction`
- `purchase_intent_click`
- `checkout_page_view`
- `checkout_start`
- `payment_info_entered`
- `purchase`
- `subscription_start`
- `refund`
- `chargeback`
- `subscription_cancel`
- `repeat_purchase`

## Answer Path Modeling

The quiz should preserve three levels of answer data:

1. **Raw event stream:** every question view, option presented, option selected, deselected, submitted, and result viewed.
2. **Submitted answer snapshot:** final submitted answer set per question at quiz completion.
3. **Derived path metadata:** `segment_id`, `result_id`, `answer_path_id`, `answer_path_hash`, `recommendation_id`, `offer_id`.

Use `answer_path_hash` when the full path is too wide for event properties. Keep the mapping from hash to submitted answer set in a controlled analytics table. Do not make the hash the only source of truth.

## Diagnostic Matrix

| Symptom | Likely Problem | Metrics To Check | Recommended Action |
| --- | --- | --- | --- |
| Low click-to-quiz load | Broken link, slow load, redirect issue | `EnteredPresales / entry_click`, load time, device/browser split | Fix the technical path before copy changes |
| High entrance, low qualified visitor | Bad traffic or above-fold mismatch | Qualified quiz visitor rate, source, creative, device | Audit traffic source and opening promise |
| Low quiz start | Entrance screen or first-step UX issue | Quiz start rate, mobile viewport, load events | Tighten opening screen and ensure first question/start CTA is visible |
| Low first answer | First question feels hard, unsafe, or irrelevant | First answer rate, option selection distribution | Rewrite first question for easy self-identification |
| One question has high dropoff | Question-specific friction | Per-question completion and dropoff | Rewrite or reorder that question |
| High option changes | Confusing option set | Option change/backtrack rate | Clarify options, add `none_of_these` where appropriate |
| High validation errors | UX or input rule problem | Validation error rate by device/browser | Fix interaction states and required-field handling |
| High completion, low CTA exposure | Result page hides the ask | `QuizCtaViewed / QuizCompleted` | Move CTA into visible result/recommendation area |
| High CTA exposure, low click | Weak result-to-sales bridge | `PreSalesToSalesClick / QuizCtaViewed`, recommendation engagement | Strengthen result specificity, proof, and CTA clarity |
| High click, low sales-page view | Broken bridge | `sales_page_view / PreSalesToSalesClick` | Fix destination URL, redirect, load, or tracking |
| Good sales-page view, low purchase | Sales page or offer mismatch | purchase / sales page view, offer engagement | Audit sales-page message match and offer fit |
| Good quiz click, weak RPV | Curiosity clicks or low-value segments | RPV by result/option, AOV, purchase / click | Do not call winner; inspect option/result buyer quality |
| Purchases up, refunds up | Overqualification, oversold result, wrong-fit buyers | Refund rate by result/option, support tickets | Treat as buyer-quality guardrail failure |

## Dashboard Layout

### Daily Operating Dashboard

Use daily reporting to catch technical failures, traffic quality drops, and obvious funnel leaks.

| Metric | Segment By | Why It Matters |
| --- | --- | --- |
| Entry clicks | Source, campaign, creative | Denominator for traffic quality |
| `EnteredPresales` | Source, quiz, variant, device | Confirms quiz arrival |
| Click-to-quiz load rate | Source, device, browser | Detects broken links, load issues, tracking loss |
| Qualified quiz visitor rate | Source, creative, device | Separates real prospects from noise |
| Quiz start rate | Quiz, variant, device | Opening screen and first-step health |
| First answer rate | Question, variant, device | Initial participation |
| Per-question completion | Question, variant, device | Exact question-level leak |
| Option selection distribution | Question, option, source | Audience composition and answer-path mix |
| Option change/backtrack | Question, option, device | Confusion signal |
| Quiz completion rate | Quiz, variant, source | Full quiz participation |
| Result assignment rate | Result, segment, variant | Recommendation logic health |
| Quiz CTA exposure | CTA position, result, device | Whether visitors see the ask |
| `PreSalesToSalesClick` rate | CTA, result, option path | Bridge intent |
| Bridge integrity | Destination, device, browser | Technical handoff |
| Sales page views | Offer, result, variant | Downstream arrival |
| Purchases | Source, result, offer | Real conversion |
| Revenue / RPQV | Source, result, option | Paid acquisition viability |
| AOV | Offer, SKU, result | Order economics |
| Refund / chargeback | Result, option, offer | Buyer quality |
| Tracking chain integrity | Browser, device, source | Data reliability |

### Weekly Deep Dive

Use weekly analysis to decide what to test next.

- Which traffic sources produce quiz starts, completions, sales clicks, and purchases?
- Which questions cause the largest dropoff?
- Which options are selected most often, and which options produce the best downstream economics?
- Which answer paths create high clicks but weak purchase intent?
- Which result segments produce strong RPV, AOV, and low refunds?
- Does the result/recommendation preserve the mechanism and proof needed for the sales page?
- Does mobile underperform desktop at a specific question, result, or bridge step?
- Are active quiz variants valid by purchase volume and buyer-quality guardrails?

## Segmentation Requirements

Every metric should be sliceable by these dimensions:

| Segment | Why It Matters |
| --- | --- |
| Traffic source | Native, paid social, search, email, organic, affiliate, direct perform differently |
| Referrer type | Ad, advertorial, listicle, email, direct, search create different expectations |
| Campaign / ad set / creative | High CTR creative may send low-intent quiz visitors |
| UTM content | Tracks angle and promise |
| Quiz ID / version | Required when questions or logic change |
| Quiz variant / experiment ID | Required for A/B testing |
| Question ID | Localizes dropoff |
| Option ID | Core user-option analysis |
| Answer path ID/hash | Groups complete answer sequences |
| Result ID / segment ID | Connects diagnosis/recommendation to revenue |
| CTA position | Shows whether result CTA timing is right |
| Device / viewport / browser | Catches mobile and technical failures |
| Geo / market | Price sensitivity and buying intent vary |
| Awareness level | RMBC calibration from unaware to most-aware |
| Mechanism angle | Different mechanisms create different answer and buying behavior |
| Offer / SKU | Each recommendation can perform differently |
| Bundle / subscription | Needed for AOV and LTV |
| New vs returning | Returning users may answer and buy differently |

## False-Positive Guardrails

### 1. Do Not Declare Winners On Quiz Completion Alone

Completion is a diagnostic. Require purchase conversion, RPQV, and buyer-quality guardrails before calling a quiz winner.

### 2. Do Not Declare Winners On `PreSalesToSalesClick` Alone

The click is the bridge event. It is not proof of purchase intent quality. Require at least one of:

- Higher purchase conversion
- Higher RPQV or EPC
- Lower CPA
- Better ROAS
- Equal conversion with better AOV, subscription attach, or buyer quality

### 3. Require Purchase Volume

Quiz interactions happen more frequently than purchases. Test validity must include purchases per variant, not just question submissions or sales clicks.

### 4. Version Quiz Logic

Any change to question order, option meaning, scoring logic, result mapping, or destination offer should create a new `quiz_version` or explicit `logic_version`.

### 5. Preserve Option Identity

Do not compare option performance across versions if the option meaning changed. Treat it as a new option.

### 6. Monitor Tracking Loss

Track:

```text
EnteredPresales_with_click_id / EnteredPresales
PreSalesToSalesClick_with_session_id / PreSalesToSalesClick
sales_page_views_attributed_to_quiz / sales_page_view
purchases_attributed_to_quiz / purchase
```

If attribution breaks, pause interpretation before changing quiz copy or logic.

### 7. Watch Buyer Quality By Result And Option

Delayed guardrails should be sliceable by `result_id`, `segment_id`, `question_id`, and `option_id`:

- Refund rate
- Chargeback rate
- Subscription cancellation rate
- Support ticket rate
- AOV
- Repeat purchase or LTV where available

### 8. Separate Quiz Problems From Sales Page Problems

Use transition metrics:

```text
QuizCompleted / EnteredPresales
QuizCtaViewed / QuizCompleted
PreSalesToSalesClick / QuizCtaViewed
sales_page_view / PreSalesToSalesClick
purchase / sales_page_view
```

This prevents rewriting the quiz when the actual problem is the sales page, checkout, or bridge.

## Suggested Alert Rules

Use rolling local baselines instead of universal benchmarks. Start with 7-day or 14-day baselines by quiz, traffic source, and device.

| Alert | Rule | Severity |
| --- | --- | --- |
| Click-to-quiz load drop | More than 10% below baseline | Critical |
| Mobile load slowdown | Mobile p95 load time above target or 20% worse than baseline | High |
| Qualified visitor drop | Below 70% of baseline for 2 days | High |
| Quiz start collapse | Below 70% of baseline for 2 days | High |
| First answer drop | Below 75% of baseline | High |
| Question-level dropoff spike | Any question dropoff 25% worse than baseline | Medium |
| Validation error spike | More than 2x baseline | High |
| Result assignment failure | `QuizResultViewed / QuizCompleted` below 98% | Critical |
| Quiz CTA exposure drop | Below 80% of baseline | Medium |
| Sales click anomaly | `PreSalesToSalesClick` rate up or down more than 40% | Medium |
| Bridge break | `sales_page_view / PreSalesToSalesClick` below 97% | Critical |
| RPQV decline | Below 85% of baseline for 3 days | High |
| Refund spike | 30-day refund rate above 150% of 90-day baseline | Critical |
| Tracking chain integrity drop | Below 90% | Critical |

## Implementation Priority

Implement in this order:

1. `EnteredPresales`
2. `QuizQuestionViewed`
3. `QuizOptionPresented`
4. `QuizOptionSelected`
5. `QuizQuestionSubmitted`
6. `QuizCompleted`
7. `QuizResultViewed`
8. `QuizRecommendationViewed`
9. `QuizCtaViewed`
10. `PreSalesToSalesClick`
11. `sales_page_view`
12. `purchase_intent_click`
13. `checkout_page_view`
14. `checkout_start`
15. `purchase`
16. `refund` / `chargeback` / buyer-quality guardrails

If only the bare minimum is possible in the first pass, implement:

```text
EnteredPresales
QuizQuestionViewed
QuizOptionSelected
QuizCompleted
QuizCtaViewed
PreSalesToSalesClick
sales_page_view
purchase
```

## Final Recommendation

Build the quiz dashboard around the full diagnostic chain:

```text
Traffic arrives
  -> real prospect enters quiz
  -> first question earns participation
  -> each option captures a stable user signal
  -> quiz completion creates a usable segment/result
  -> recommendation bridges cleanly to the sales page
  -> sales page preserves intent
  -> checkout converts
  -> buyer quality stays healthy
```

The strongest quiz funnel is not the one with the highest completion rate or the most `PreSalesToSalesClick` events. It is the one that identifies the right visitors, routes them to the right offer, and produces the highest qualified revenue per quiz visitor while protecting AOV, subscription attach, refund rate, chargeback rate, and long-term buyer quality.
