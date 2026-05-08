# Paid Ads QA LLM Policy Prompt Review

## Decision

The new paid ads policy classification path uses an LLM to classify the full Meta ad experience:

- ad copy
- generated image creative
- landing-page context

The implementation does **not** use OCR for image inspection. It sends the image bytes to the LLM as an `input_image` data URL and asks the model to use visual understanding.

The implementation also does **not** use deterministic policy heuristics for the new Meta policy classification. Deterministic checks remain only for operational readiness items such as missing destination URLs, unreachable landing pages, under-construction pages, privacy/contact markers, missing ad set specs, and publish-plan completeness.

## Runtime Settings

Configured in `mos/backend/app/config.py`:

```python
PAID_ADS_QA_LLM_MODEL: str = "gpt-5.4-mini"
PAID_ADS_QA_LLM_REASONING_EFFORT: str = "high"
PAID_ADS_QA_LLM_TIMEOUT_SECONDS: float = 60.0
```

The LLM request requires:

```python
OPENAI_API_KEY
```

If `OPENAI_API_KEY` is missing, the QA run fails closed with `META-POLICY-LLM-001` rather than silently skipping policy classification.

## Request Method

The workflow calls the OpenAI Responses API:

```python
client.responses.create(
    model=model,
    reasoning={"effort": reasoning_effort},
    input=[
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": USER_CONTENT,
        },
    ],
)
```

`USER_CONTENT` always includes one `input_text` item containing the JSON classification context. It also includes one `input_image` item when the asset image is available.

```python
[
    {
        "type": "input_text",
        "text": json.dumps(context, ensure_ascii=False, sort_keys=True),
    },
    {
        "type": "input_image",
        "image_url": "data:image/jpeg;base64,...",
    },
]
```

## Exact System Prompt

This is the exact prompt currently sent as the system message:

```text
You are MOS paid ads QA. Classify the provided Meta ad copy, landing page text, and image against the supplied rule ids. Use LLM visual understanding for the image; do not invoke OCR tools or external lookups. Use the supplied policy examples as classification guidance and the campaign-specific rejected references only as calibration; do not overfit to one industry, one product category, or one exact phrase. The word 'testosterone' is allowed by itself when it is general product, category, or educational language. Flag personal-attribute risk when the ad asserts or strongly implies a user's own protected health, body, medical, age, financial, voting, or identity attribute. Flag unacceptable-business-practices risk when the ad experience uses deceptive, misleading, hidden-cause, sensational, fake-authority, or bait-style framing. Return strict JSON with keys passed, findings, and revisionGuidance. Each finding must use one of the supplied rule ids and include status, title, message, evidence.policyTrace, and fixGuidance.
```

## User Context Payload

The user message is a JSON object with this top-level structure:

```json
{
  "task": "Meta paid ads policy classification",
  "method": "LLM-only policy classification for copy, image, and landing-page risk.",
  "rules": [],
  "policyExamples": {},
  "campaignSpecificRejectedReferences": [],
  "ad": {},
  "landingPage": {},
  "outputContract": {}
}
```

## Rules Supplied To The LLM

The prompt supplies these rule IDs and classification instructions.

### META-COPY-002

```json
{
  "ruleId": "META-COPY-002",
  "policyTrace": "Meta Privacy Violations and Personal Attributes",
  "classify": "Ad copy asserts or implies private knowledge about the viewer."
}
```

### META-COPY-003

```json
{
  "ruleId": "META-COPY-003",
  "policyTrace": "Meta Discriminatory Practices",
  "classify": "Ad copy excludes protected classes or expresses discriminatory access."
}
```

### META-COPY-004

```json
{
  "ruleId": "META-COPY-004",
  "policyTrace": "Meta SIEP",
  "classify": "Ad copy appears to involve social issues, elections, or politics."
}
```

### META-COPY-005

```json
{
  "ruleId": "META-COPY-005",
  "policyTrace": "Meta Health and Wellness negative self-perception",
  "classify": "Ad copy attempts to generate shame or negative self-perception."
}
```

### META-COPY-006

```json
{
  "ruleId": "META-COPY-006",
  "policyTrace": "Meta Privacy Violations and Personal Attributes",
  "classify": "Ad copy makes a direct personal health/body/medical attribute claim about the viewer. General category/product language is allowed when it does not assert or imply knowledge of the viewer's own condition."
}
```

### META-UBP-001

```json
{
  "ruleId": "META-UBP-001",
  "policyTrace": "Meta Unacceptable Business Practices",
  "classify": "Ad experience uses deceptive, misleading, sensational, fake-authority, or hidden-cause framing around a product, service, scheme, offer, or health/body outcome."
}
```

### META-IMAGE-001

```json
{
  "ruleId": "META-IMAGE-001",
  "policyTrace": "Meta policy review of ad creative media",
  "classify": "Image creative visually reinforces a policy risk, including fake authority/news/science framing, misleading medical implication, before/after body-result framing, or direct personal-attribute callout."
}
```

### META-LP-007

```json
{
  "ruleId": "META-LP-007",
  "policyTrace": "Meta landing-page and ad-experience review",
  "classify": "Landing page materially reinforces UBP, personal-attribute, or health-result exaggeration risk from the ad."
}
```

## Policy Examples Supplied To The LLM

The examples are intentionally broader than the Tenor campaign. They are grouped by Meta policy source and are used as classification guidance, not as hardcoded keyword rules.

### Privacy Violations And Personal Attributes

Source:

```text
https://transparency.meta.com/policies/ad-standards/objectionable-content/privacy-violations-personal-attributes/
```

Payload:

```json
{
  "sourceUrl": "https://transparency.meta.com/policies/ad-standards/objectionable-content/privacy-violations-personal-attributes/",
  "guidance": [
    "Allowed: product or service availability framed generally, including general health-condition treatment availability.",
    "Allowed: passing age-range or demographic references when they do not assert the viewer personally has that attribute.",
    "Allowed: using you/your language without tying it to a personal attribute.",
    "Not allowed: asking whether the viewer has a medical condition or other protected personal attribute.",
    "Not allowed: implying the advertiser knows the viewer's medical information, voting status, financial status, identity, or age.",
    "Not allowed: using you/your/other language to reference a protected personal attribute."
  ]
}
```

Notes:

- This uses Meta’s own distinction between broad/general references and direct or indirect assertions about the viewer.
- The classifier should not flag `you` or `your` by itself.
- The classifier should flag `you` or `your` when it is connected to protected attributes such as medical status, physical or mental health, age, financial status, voting status, name, or identity.

### Health And Wellness

Source:

```text
https://transparency.meta.com/policies/ad-standards/restricted-goods-services/health-wellness/
```

Payload:

```json
{
  "sourceUrl": "https://transparency.meta.com/policies/ad-standards/restricted-goods-services/health-wellness/",
  "guidance": [
    "Allowed: health, dietary, or weight-loss products when targeted appropriately and presented without negative self-perception tactics.",
    "Allowed: illustrating product or service use and realistic impact over time without shame, insecurity, or perfect-body framing.",
    "Not allowed: copy that exploits insecurities, body-shaming, or negative body image to promote a health-related product.",
    "Not allowed: side-by-side weight-loss transformation comparisons tied to product use.",
    "Not allowed: close-up visuals pinching fat or isolating a body area to create negative self-perception."
  ]
}
```

Notes:

- This prevents the image classifier from relying only on text.
- The image review should consider layout, body imagery, before/after framing, close-up body-area emphasis, and negative self-perception cues.

### Unacceptable Business Practices

Source:

```text
https://transparency.meta.com/policies/ad-standards/fraud-scams/unacceptable-business-practices/
```

Payload:

```json
{
  "sourceUrl": "https://transparency.meta.com/policies/ad-standards/fraud-scams/unacceptable-business-practices/",
  "guidance": [
    "Not allowed: deceptive or misleading promotion of products, services, schemes, or offers.",
    "Not allowed: bait-style framing where the ad creates a misleading reason to click and the destination does not substantiate it clearly.",
    "Not allowed: fake authority, fake news, or fake scientific framing that could mislead people about the product, service, or offer.",
    "Not allowed: exaggerated health-result or hidden-cause framing used to pressure action or collect money/personal information.",
    "Review holistically across image, copy, destination, offer clarity, business identity, and substantiation."
  ]
}
```

Notes:

- This block is deliberately cross-industry.
- It covers product, service, scheme, and offer framing rather than only supplement or health ads.
- Campaign-specific rejected references are separated from this general policy block so the model does not treat the Tenor campaign as the entire policy universe.

## Campaign-Specific Rejected References

These references are passed as calibration examples only:

```json
[
  {
    "reference": "GLP-1s are secretly crashing your testosterone.",
    "calibrationOnly": true,
    "riskTypes": ["hidden-cause/sensational framing", "personal health/body attribute phrasing"]
  },
  {
    "reference": "Doctors did not mention what this weight loss protocol may do to your testosterone.",
    "calibrationOnly": true,
    "riskTypes": ["medical authority framing", "personal health/body attribute phrasing"]
  },
  {
    "reference": "If you are over 40 and gaining weight, this quiz explains what may be happening.",
    "calibrationOnly": true,
    "riskTypes": ["age/body personal-attribute phrasing"]
  },
  {
    "reference": "Researchers found a hidden reason men may lose their drive during rapid weight loss.",
    "calibrationOnly": true,
    "riskTypes": ["research authority framing", "hidden-cause framing"]
  }
]
```

These examples should help the classifier understand the previous rejection family without forcing the model to classify every campaign as if it were a GLP/testosterone campaign.

## Ad Payload

Each creative spec is sent to the LLM in this shape:

```json
{
  "creativeSpecId": "meta_creative_spec_id",
  "assetId": "asset_id",
  "primaryText": "Meta primary text",
  "headline": "Meta headline",
  "description": "Meta description",
  "combinedCopy": "primaryText headline description",
  "destinationUrl": "https://example.com/presale"
}
```

`combinedCopy` is created by joining the primary text, headline, and description. No regex policy classification is performed on this copy in the new policy path.

## Landing Page Payload

When the destination can be fetched, the LLM receives the landing-page snapshot:

```json
{
  "requestedUrl": "https://example.com/presale",
  "finalUrl": "https://example.com/presale",
  "statusCode": 200,
  "bodyText": "full landing page text",
  "inspectionSource": "http_fetch"
}
```

For MOS public funnel pages, the service extracts all text fragments from the public funnel API payload:

```json
{
  "requestedUrl": "https://example.com/f/product/funnel/pre-sales",
  "finalUrl": "https://example.com/f/product/funnel/pre-sales",
  "statusCode": 200,
  "bodyText": "full extracted funnel metadata and puckData text",
  "inspectionSource": "public_funnel_api"
}
```

The previous 50,000-character truncation was removed. The intent is to analyze the full page text.

If landing-page context is not available, the LLM context uses:

```json
{
  "bodyText": null,
  "note": "Landing page was not available for LLM policy classification."
}
```

## Image Payload

The image is loaded from the MOS asset `storage_key` through `MediaStorage.download_bytes(...)`.

The image is then sent as:

```json
{
  "type": "input_image",
  "image_url": "data:image/jpeg;base64,..."
}
```

The prompt explicitly says:

```text
Use LLM visual understanding for the image; do not invoke OCR tools or external lookups.
```

## Required LLM Output

The supplied output contract is:

```json
{
  "passed": "boolean",
  "findings": [
    {
      "ruleId": "one supplied rule id",
      "status": "failed or needs_manual_review",
      "title": "short title",
      "message": "policy-grounded explanation",
      "evidence": {
        "policyTrace": ["source/rationale bullets"],
        "observations": []
      },
      "fixGuidance": ["specific edits needed"]
    }
  ],
  "revisionGuidance": ["optional campaign repair guidance"]
}
```

The parser requires:

- `findings` must be a list.
- `ruleId` must be one of the supported LLM policy rule IDs.
- `status` must be `failed` or `needs_manual_review`.
- unsupported rule IDs fail closed as `META-POLICY-LLM-001`.
- invalid JSON fails closed as `META-POLICY-LLM-001`.

## Supported LLM Rule IDs

The implementation accepts only these LLM policy rule IDs:

```text
META-POLICY-LLM-001
META-COPY-002
META-COPY-003
META-COPY-004
META-COPY-005
META-COPY-006
META-UBP-001
META-IMAGE-001
META-LP-007
```

## Fail-Closed Behavior

The QA run emits `META-POLICY-LLM-001` when classification cannot complete.

Examples:

- `OPENAI_API_KEY` missing
- model setting missing
- image asset missing
- asset has no `storage_key`
- asset is not an `image/*` content type
- media storage cannot load image bytes
- LLM returns no text
- LLM returns invalid JSON
- LLM returns unsupported rule IDs
- LLM returns unsupported statuses

## Metadata Injection For Tests Or Precomputed Reviews

The code supports a precomputed LLM review block in either asset metadata or creative spec metadata:

```json
{
  "paidAdsQaLlmPolicyReview": {
    "model": "gpt-5.4-mini",
    "reasoningEffort": "high",
    "passed": false,
    "findings": [
      {
        "ruleId": "META-UBP-001",
        "status": "failed",
        "title": "Unacceptable business practices risk",
        "message": "The LLM policy review traced hidden-cause health framing to Meta UBP risk.",
        "evidence": {
          "policyTrace": ["Meta Unacceptable Business Practices"]
        },
        "fixGuidance": ["Remove hidden-cause framing."]
      }
    ],
    "revisionGuidance": ["Rewrite the ad hook as neutral educational framing."]
  }
}
```

This is used in tests so the test suite does not call the live model.

## Meta Policy Trace In Ruleset

The ruleset now includes the Meta Unacceptable Business Practices source:

```json
{
  "sourceId": "meta.unacceptable_business_practices",
  "platform": "meta",
  "sourceKind": "official_policy",
  "title": "Unacceptable Business Practices",
  "url": "https://transparency.meta.com/policies/ad-standards/fraud-scams/unacceptable-business-practices/",
  "lastUpdated": null,
  "regionScope": "Global",
  "needsVerification": true
}
```

The user-facing trace for the campaign-specific risks is:

- `META-COPY-006`: personal attribute risk when the ad asserts or implies the viewer has a protected attribute, including health/body/medical, age, financial, voting, identity, or similar personal status.
- `META-UBP-001`: unacceptable-business-practices risk when the ad experience uses deceptive, misleading, hidden-cause, sensational, fake-authority, or bait-style framing.
- `META-IMAGE-001`: image creative visually reinforcing misleading authority, fake science/news, before/after body-result framing, or direct personal-attribute callouts.
- `META-LP-007`: landing page materially reinforcing those same risks.

## Explicit Testosterone Handling

The implementation intentionally does **not** treat `testosterone` as a policy violation by itself.

Allowed examples:

```text
Testosterone support is discussed in this educational article.
Learn about testosterone and men's health.
Daily wellness support for healthy testosterone.
```

Risky examples:

```text
GLP-1s are secretly crashing your testosterone.
Doctors did not mention what this weight loss protocol may do to your testosterone.
If you are over 40 and gaining weight, this quiz explains what may be happening.
```

Why these examples are risky:

- Hidden-cause or sensational framing maps to `META-UBP-001`.
- Direct viewer-attribute phrasing maps to `META-COPY-006`.
- Medical or research authority framing can amplify the UBP risk when the claim is not clearly substantiated by the full destination.

## Six Rejected Pattern Coverage

The regression test covers these patterns:

```text
GLP-1s are secretly crashing your testosterone.
Doctors did not mention what this weight loss protocol may do to your testosterone.
If you are over 40 and gaining weight, this quiz explains what may be happening.
Your energy is dropping and your gut will not budge.
Researchers found a hidden reason men may lose their drive during rapid weight loss.
This old-school mistake may be secretly crashing men's results.
```

Expected coverage:

- hidden-cause or fake-discovery framing -> `META-UBP-001`
- direct viewer health/body/age phrasing -> `META-COPY-006`
- plain general testosterone language -> no finding

## Publish Gate Behavior

Meta publish validation now blocks unless the latest completed campaign-level Meta paid ads QA run:

- exists
- uses the current ruleset
- matches the publish `generationKey`
- covers every selected creative asset
- has status `passed`

The gate is implemented before Meta campaign/ad set/creative/ad creation. A failed or missing QA run blocks publish validation and prevents the publish run from starting.

## What Remains Deterministic

The following remain deterministic because they are operational readiness checks, not policy interpretation:

- campaign has Meta creative specs
- campaign has Meta ad set specs
- ready assets have prepared Meta specs
- destination URL exists
- destination URL resolves to an absolute public URL
- destination URL fetch succeeds
- landing page returns non-error HTTP status
- landing page does not look under construction
- landing page exposes privacy marker
- landing page exposes contact/support marker
- publish plan has selected assets
- selected assets have ad set assignment
- targeting, placement, budget, and Meta workspace fields are complete

The new Meta policy classification itself is LLM-based.
