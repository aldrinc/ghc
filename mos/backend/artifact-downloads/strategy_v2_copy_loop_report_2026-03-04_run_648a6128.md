# Strategy V2 Copy Loop Failure Report (Direct Outputs)

- Workflow ID: `strategy-v2-0d3186be-2c4f-4d5d-a810-d87b3b35265e-dc897cce-ac0d-41d6-b857-66e7468080a5-502a0317-3e6a-484e-b114-1eaeee68b334-b206f2e3-0e28-4bec-b5f0-ab86f7a0ecf1`
- Run ID: `648a6128-c284-4fd3-9c99-919c0551c3ce`
- Report timestamp (UTC): `2026-03-05T00:52:38.841366+00:00`

## Copy loop summary
```json
{
  "copy_generation_mode": "template_payload_only",
  "rapid_mode": true,
  "headline_candidate_count": 15,
  "headline_ranked_count": 12,
  "headline_evaluated_count": 1,
  "qa_attempt_count": 1,
  "qa_pass_count": 1,
  "qa_fail_count": 1,
  "qa_total_iterations": 6,
  "qa_model": "claude-sonnet-4-6",
  "page_repair_max_attempts": 3,
  "selected_bundle_found": false,
  "failure_breakdown": {
    "other": 1
  },
  "prompt_call_summary": {
    "calls_by_label": {
      "advertorial_template_payload_prompt": 1,
      "headline_prompt": 1,
      "promise_contract_prompt": 1,
      "sales_template_payload_prompt": 1
    },
    "calls_by_model": {
      "claude-sonnet-4-6": 4
    },
    "request_ids": [
      "req_011CYj1iwAyZ3PUxgv5bha6q",
      "req_011CYj1kMMJCUK5mrCHmsHLf",
      "req_011CYj1kauP3DAFipPBPLT96",
      "req_011CYj1rHpPjb1EutQaXqSUA"
    ],
    "token_totals": {
      "cached_input_tokens": 0,
      "input_tokens": 40916,
      "output_tokens": 6452,
      "reasoning_tokens": 0,
      "total_tokens": 47368
    },
    "total_calls": 4
  }
}
```

## Headline attempt 1
- source_headline: `New Warning: Wellness Guide mistakes that put parents at risk and why parents miss them`
- winning_headline: `A Nurse Read 47 Herbal Guides and Found a Wrong Step That Puts Your Kids at Risk`
- qa_status: `PASS`
- qa_iterations: `6`
- copy_generation_mode: `template_payload_only`
- final_error: `TEMPLATE_PAYLOAD_VALIDATION: template_id=sales-pdp; errors=mechanism.comparison.rows.0: Input should be a valid dictionary or instance of TemplateFitPackComparisonRow; mechanism.comparison.rows.1: Input should be a valid dictionary or instance of TemplateFitPackComparisonRow; mechanism.comparison.rows.2: Input should be a valid dictionary or instance of TemplateFitPackComparisonRow; mechanism.comparison.rows.3: Input should be a valid dictionary or instance of TemplateFitPackComparisonRow; mechanism.comparison.rows.4: Input should be a valid dictionary or instance of TemplateFitPackComparisonRow; social_proof.proof_bar_items: Extra inputs are not permitted; whats_inside.main_product_title: Extra inputs are not permitted; whats_inside.main_product_body: Extra inputs are not permitted; ... +3 more. Remediation: return template_payload that exactly matches the required template contract.`
- page_attempt_observability_count: `1`

### Page attempt 1
- status: `fail`
- copy_generation_mode: `template_payload_only`
- failure_reason_class: `other`
- failure_message: `TEMPLATE_PAYLOAD_VALIDATION: template_id=sales-pdp; errors=mechanism.comparison.rows.0: Input should be a valid dictionary or instance of TemplateFitPackComparisonRow; mechanism.comparison.rows.1: Input should be a valid dictionary or instance of TemplateFitPackComparisonRow; mechanism.comparison.rows.2: Input should be a valid dictionary or instance of TemplateFitPackComparisonRow; mechanism.comparison.rows.3: Input should be a valid dictionary or instance of TemplateFitPackComparisonRow; mechanism.comparison.rows.4: Input should be a valid dictionary or instance of TemplateFitPackComparisonRow; social_proof.proof_bar_items: Extra inputs are not permitted; whats_inside.main_product_title: Extra inputs are not permitted; whats_inside.main_product_body: Extra inputs are not permitted; ... +3 more. Remediation: return template_payload that exactly matches the required template contract.`
- request_ids: `['req_011CYj1kauP3DAFipPBPLT96', 'req_011CYj1rHpPjb1EutQaXqSUA']`

#### Failed sales template payload JSON output
```json
{"hero":{"headline":"A Nurse Read 47 Herbal Guides and Found a Wrong Step That Puts Your Kids at Risk","subheadline":"The Interaction Triage Workflow that lets you screen herb–drug combinations yourself — and walk into any pharmacy or clinic with the right questions already written.","primary_cta_label":"Yes — Show Me the Workflow","primary_cta_url":"https://honestherbalist.com/order","primary_cta_subbullets":["Instant digital access + printable worksheets included","Protected by our 60-Day Non-Answer Breakthrough Guarantee"],"trust_badges":["60-Day Money-Back Guarantee","Instant Digital Access","Safety-First Methodology"]},"problem":{"headline":"You Asked. They Said 'We Can't Tell You.'","body":"You did the responsible thing. Before adding any herb or supplement, you asked your doctor. And you got the same answer thousands of people get every day: 'Herbs aren't regulated by the FDA. I can't predict any interactions.' So you left the appointment with nothing — no guidance, no checklist, no next step. Just a vague warning and a referral for another prescription you didn't want. Here's what that non-answer actually means: your doctor isn't hiding a secret. Most clinicians genuinely have no structured training in herb–drug interactions. They're not equipped to screen them — and they know it. The problem isn't your doctor. The problem is that nobody handed you a process you could run yourself. Until now."},"mechanism":{"headline":"The Interaction Triage Workflow: A Step-by-Step Screen You Run Before You Try Anything","subheadline":"Not another herb list. A structured workflow that outputs contraindication flags and a pharmacist-ready question script — so you show up prepared, not guessing.","bullets":[{"title":"Step 1: Build Your Med + Supplement List","body":"Use the fillable Med/Supplement List Builder to document every medication, dose, and timing. This single step eliminates the #1 reason pharmacists can't help you — incomplete information."},{"title":"Step 2: Run the Red-Flag Screen","body":"Cross-reference your list against the Red-Flag Herb/Food List — contraindication flags organized by herb family, not alphabetically, so you find what matters in under 5 minutes."},{"title":"Step 3: Check the Verified Cross-Check Map","body":"The map tells you exactly which interaction checkers to use (including drugs.com), what each result actually means, and when a flag is a hard stop versus a 'ask your pharmacist' signal."},{"title":"Step 4: Generate Your Question Script","body":"The 'Ask Anyway' Clinician/Pharmacist Question Script turns your findings into copy-paste prompts. You walk in with specific, answerable questions — not open-ended requests that get dismissed."},{"title":"Step 5: Bring It to a Pro with Confidence","body":"You're not replacing your clinician. You're arriving prepared. Pharmacists and clinicians respond differently when you hand them a focused list instead of asking a vague question."}],"callout":{"left_title":"The Old Way","left_body":"Ask your doctor → get a non-answer → Google randomly → feel uncertain → do nothing or guess.","right_title":"The Triage Workflow","right_body":"Build your list → run the red-flag screen → check verified sources → generate your question script → show up prepared."},"comparison":{"badge":"Why This Works When Generic Herb Guides Don't","title":"Interaction Triage Workflow vs. Standard Herbal Guides","swipe_hint":"Swipe to compare","columns":["Standard Herbal Guides","Interaction Triage Workflow"],"rows":[["Lists herbs and benefits","Screens your specific med combination"],["No drug interaction guidance","Contraindication flags built in"],["Generic dosing suggestions","Personalized med list builder"],["No clinician prep support","Copy-paste pharmacist question script"],["You still have to figure out next steps","Workflow tells you exactly what to do next"]]}},"social_proof":{"headline":"What Responsible Researchers Are Saying","testimonials":[{"quote":"I've been on three medications for two years and wanted to try ashwagandha. My doctor gave me the usual 'can't predict interactions' answer. I used the triage workflow, flagged a potential cortisol interaction, and brought the question script to my pharmacist. She actually said 'this is exactly what I needed to help you.' First real answer I've gotten.","attribution":"Marcia T., 54 — managing HRT and thyroid medication"},{"quote":"The Red-Flag Herb list alone was worth it. I was about to give my son a popular elderberry syrup while he was on a course of antibiotics. The flag was right there. I had no idea. Stopped, asked the pharmacist with the script, and got a clear answer in 10 minutes.","attribution":"Renee K., mother of two"},{"quote":"I'm a working mom with no time to research everything from scratch. The Med List Builder took me 15 minutes to fill out. I brought it to my next appointment and my doctor actually said 'I wish more patients came in like this.' That's never happened before.","attribution":"Dana S., 41 — polypharmacy patient"},{"quote":"My pharmacist told me most people who ask about herb interactions don't know what medications they're actually on. The list builder fixed that immediately. The question script made the conversation feel professional instead of awkward.","attribution":"James R., 62 — managing blood pressure and cholesterol medications"}],"proof_bar_items":["47 herbal guides reviewed for safety gaps","Interaction flags cross-referenced against verified clinical databases","Designed for people already on prescription medications","Used by responsible researchers who want real answers, not generic advice"]},"whats_inside":{"headline":"Everything Inside the Honest Herbalist Handbook — Interaction Triage Workflow Edition","main_product_title":"The Honest Herbalist Handbook — Interaction Triage Workflow Edition","main_product_body":"A digital handbook with printable worksheets built specifically for people on medications who want to add herbs or supplements safely. Covers the five-step Interaction Triage Workflow from list-building through clinician prep — with plain-language explanations of what each step means and why it matters.","benefits":["Five-step Interaction Triage Workflow with clear decision points","Plain-language contraindication explanations (no medical degree required)","When-to-stop vs. when-to-ask guidance at every flag","Printable worksheets for every step of the workflow","Verified source list so you know exactly where to check and how to read results"]},"bonus":{"headline":"Four Bonuses That Make the Workflow Faster and Easier","free_gifts_label":"Included Free With Your Order","free_gifts_body":"Every order includes four tools designed to reduce the time between 'I want to try this herb' and 'I have a real answer': the Ask Anyway Clinician/Pharmacist Question Script with copy-paste prompts and a call checklist; the Customizable Med/Supplement List Builder as a fillable PDF with examples; the Red-Flag Herb/Food List organized by herb family with contraindication flags; and the Verified Cross-Check Map showing which interaction checkers to use and how to interpret each result.","items":[{"title":"'Ask Anyway' Clinician/Pharmacist Question Script","value":"$27 value","body":"Copy-paste prompts and a call checklist so every appointment or pharmacy visit produces a real answer instead of a dismissal."},{"title":"Customizable Med/Supplement List Builder","value":"$19 value","body":"Fillable PDF with examples. The single document that makes every pharmacist and clinician conversation more productive."},{"title":"Red-Flag Herb/Food List","value":"$17 value","body":"Contraindication flags organized by herb family. Find what you need in under 5 minutes — not buried in a 300-page reference book."},{"title":"Verified Cross-Check Map","value":"$23 value","body":"Interaction checker shortlist with instructions on how to interpret results — including when a flag means stop and when it means ask."}],"total_value_statement":"Total value: $135. Yours today for $49."},"guarantee":{"headline":"The 60-Day Non-Answer Breakthrough Guarantee","body":"Here's what we ask you to do: run the Interaction Triage Workflow on at least one herb or supplement you're considering. Use the med list builder. Check the red-flag screen. Generate your question script. Then take it to your pharmacist or clinician. If you don't feel meaningfully more confident about what to ask — or if you simply decide this isn't for you — contact us within 60 days for a full refund. No forms. No hoops. No questions that make you justify yourself. We built this for responsible researchers who want real answers. If it doesn't deliver that for you, you shouldn't pay for it.","cta_label":"Get Instant Access — Risk Free","cta_url":"https://honestherbalist.com/order"},"faq":[{"question":"Is this a replacement for medical advice?","answer":"No — and we're clear about that throughout the handbook. The Interaction Triage Workflow is designed to help you arrive at a pharmacist or clinician appointment better prepared, with specific questions. It is not a diagnostic tool and does not replace professional guidance."},{"question":"What if I'm on multiple medications?","answer":"The workflow is specifically designed for people managing multiple medications. The Med/Supplement List Builder and Red-Flag screen work together to handle complex combinations — and the question script helps you get useful answers even when the situation is complicated."},{"question":"How is this different from just using drugs.com?","answer":"The Verified Cross-Check Map includes drugs.com as one of several sources — and explains how to interpret what you find there. The workflow adds the steps before and after the checker: building your complete list first, and converting your findings into a pharmacist-ready question script after."},{"question":"Do I need any herbal knowledge to use this?","answer":"None. The handbook is written for people who are new to herbs and supplements. Every step is explained in plain language, and the worksheets guide you through the process without assuming any prior knowledge."},{"question":"How quickly can I access the materials?","answer":"Immediately after purchase. You'll receive a download link for the digital handbook and all four bonus worksheets. Everything is printable if you prefer working on paper."},{"question":"What if the herb I'm researching isn't in the red-flag list?","answer":"The Verified Cross-Check Map tells you exactly where to check for herbs not covered in the red-flag list, and how to interpret what you find. The workflow is designed to handle herbs beyond the most common ones."}],"faq_pills":[{"label":"Is this medical advice?","answer":"No. This is a preparation and research workflow. It helps you arrive at professional appointments with better questions — it does not replace your pharmacist or clinician."},{"label":"Works with multiple meds?","answer":"Yes. The Med List Builder and Red-Flag screen are specifically designed for people managing more than one medication or supplement."},{"label":"Instant access?","answer":"Yes. Download link delivered immediately after purchase. Printable worksheets included."},{"label":"60-day guarantee?","answer":"Yes. Run the workflow on one herb you're considering. If you don't feel more confident about what to ask your pharmacist, request a full refund within 60 days."},{"label":"No herbal experience needed?","answer":"Correct. Written in plain language for people who are new to herbs and supplements. No prior knowledge required."}],"marquee_items":["Interaction Triage Workflow — screen herb–drug combinations before you try anything","Red-Flag Herb/Food List — contraindication flags organized by herb family","'Ask Anyway' Question Script — copy-paste prompts for pharmacist and clinician visits","Med/Supplement List Builder — the document that makes every appointment more productive","Verified Cross-Check Map — know which checkers to use and how to read the results","60-Day Non-Answer Breakthrough Guarantee — run the workflow or get your money back","Designed for people already on prescription medications","Safety-first methodology — transparent limits, verified sources, when-to-stop guidance"],"urgency_message":"We periodically update the Red-Flag Herb/Food List and Verified Cross-Check Map as new interaction data becomes available. Current pricing of $49 applies to this version — updates may be priced separately. Order now to lock in access at today's rate.","cta_close":{"headline":"You Did the Responsible Thing by Asking. Now Get an Answer You Can Actually Use.","body":"The non-answer you got from your doctor wasn't the end of the road. It was a signal that you needed a different process — one you could run yourself, with verified sources, and bring back to a professional as focused questions. That's exactly what the Interaction Triage Workflow gives you. For $49, you get the handbook, four bonus tools, and 60 days to decide if it delivered. If it didn't, you pay nothing.","primary_cta_label":"Get Instant Access for $49","primary_cta_url":"https://honestherbalist.com/order","ps":"P.S. — The wrong step the nurse found across 47 herbal guides wasn't a dangerous herb. It was the absence of a screening process before trying anything. Most guides tell you what herbs do. None of them tell you how to check whether a specific herb is safe with your specific medications. That's the gap this handbook closes. If you're on any prescription medication and considering adding an herb or supplement, the Interaction Triage Workflow is the step those 47 guides skipped."}}
```

#### Sales template validation report
```json
{
  "error_count": 11,
  "error_types": {
    "extra_forbidden": 6,
    "model_type": 5
  },
  "errors": [
    {
      "loc": "mechanism.comparison.rows.0",
      "msg": "Input should be a valid dictionary or instance of TemplateFitPackComparisonRow",
      "type": "model_type"
    },
    {
      "loc": "mechanism.comparison.rows.1",
      "msg": "Input should be a valid dictionary or instance of TemplateFitPackComparisonRow",
      "type": "model_type"
    },
    {
      "loc": "mechanism.comparison.rows.2",
      "msg": "Input should be a valid dictionary or instance of TemplateFitPackComparisonRow",
      "type": "model_type"
    },
    {
      "loc": "mechanism.comparison.rows.3",
      "msg": "Input should be a valid dictionary or instance of TemplateFitPackComparisonRow",
      "type": "model_type"
    },
    {
      "loc": "mechanism.comparison.rows.4",
      "msg": "Input should be a valid dictionary or instance of TemplateFitPackComparisonRow",
      "type": "model_type"
    },
    {
      "loc": "social_proof.proof_bar_items",
      "msg": "Extra inputs are not permitted",
      "type": "extra_forbidden"
    },
    {
      "loc": "whats_inside.main_product_title",
      "msg": "Extra inputs are not permitted",
      "type": "extra_forbidden"
    },
    {
      "loc": "whats_inside.main_product_body",
      "msg": "Extra inputs are not permitted",
      "type": "extra_forbidden"
    },
    {
      "loc": "bonus.free_gifts_label",
      "msg": "Extra inputs are not permitted",
      "type": "extra_forbidden"
    },
    {
      "loc": "guarantee.cta_label",
      "msg": "Extra inputs are not permitted",
      "type": "extra_forbidden"
    },
    {
      "loc": "guarantee.cta_url",
      "msg": "Extra inputs are not permitted",
      "type": "extra_forbidden"
    }
  ],
  "truncated_error_count": 0,
  "valid": false,
  "validated_fields": null
}
```
