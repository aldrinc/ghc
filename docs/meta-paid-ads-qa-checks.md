# Meta Pre-Publish QA Checks

## What This Step Is

This is the deterministic QA step that runs in the Meta ads workflow before final packaging and publish.

It is not an LLM reviewer. It does not rewrite copy, does not fix issues, and does not publish anything to Meta. It evaluates the currently prepared Meta review package and records a markdown report with findings.

## Scope

- Runs on Meta only at the campaign level.
- Uses the latest prepared Meta creative specs for the selected generation.
- If the campaign uses internal funnel delivery, QA is funnel-scoped and requires one explicit funnel.
- If the campaign uses external URL delivery, QA uses the campaign delivery config instead of funnel scope.
- Refreshes the client Meta account profile from Meta Graph before evaluation where live validation is supported.

## Important Review Note

This ruleset mixes two kinds of checks:

- MOS operational launch checklist items: internal readiness requirements we want satisfied before launch.
- Meta policy-backed checks: checks mapped to official Meta policy pages or policy-adjacent review requirements.

Marketing should review both categories separately, because not every blocker is an explicit Meta policy violation.

## Checks That Happen Before The QA Run

The workflow has a prep step before QA: `Prepare Meta review`.

That step already blocks some assets from entering QA if they are missing core Meta review data, especially:

- missing destination mapping
- missing resolved destination URL
- missing required swipe-copy metadata
- obvious copy-policy issues from the same private-information, discrimination, and negative-self-perception patterns used by QA

In practice, the QA run is the broader pre-publish review, but it is not the first place issues can surface.

## Status Logic

- `failed`: at least one failing finding exists.
- `needs_manual_review`: no failing findings exist, but at least one manual-review finding exists.
- `passed`: no failing or manual-review findings exist.

## What It Checks

### 1. Account Readiness Checks

These are mostly MOS launch-readiness checks against the saved Meta platform profile.

| Rule ID | Severity | Basis | Check |
| --- | --- | --- | --- |
| `META-ACCOUNT-001` | blocker | MOS checklist | Business Manager ID must be configured. |
| `META-ACCOUNT-002` | blocker | MOS checklist | Meta Page ID must be configured. |
| `META-ACCOUNT-003` | blocker | MOS checklist | Meta Ad Account ID must be configured. |
| `META-ACCOUNT-004` | blocker | MOS checklist | Payment method status must be `active` or `configured`. |
| `META-ACCOUNT-005` | high | MOS checklist | Payment method type should be `credit_card`. |
| `META-ACCOUNT-006` | blocker | MOS checklist | Pixel ID must be configured. |
| `META-ACCOUNT-007` | blocker | MOS checklist | Data Set must exist and be assigned to the ad account. |
| `META-ACCOUNT-008` | high | MOS checklist | Data Set should be installed via the Shopify partner path and use `maximum` data sharing. |
| `META-ACCOUNT-009` | blocker | MOS checklist | Verified domain must exist and status must be `verified`. |
| `META-ACCOUNT-010` | high | MOS checklist | Attribution should be `7d` click and `1d` view. |
| `META-ACCOUNT-011` | high | MOS checklist | View-through should be disabled (`false`). |
| `META-ACCOUNT-012` | medium | MOS checklist | Tracking provider and tracking URL parameters should be recorded. |

### 2. Campaign Readiness Checks

These confirm the Meta review package is actually prepared for the scoped generation.

| Rule ID | Severity | Basis | Check |
| --- | --- | --- | --- |
| `META-CAMPAIGN-001` | blocker | MOS checklist | Campaign must have prepared Meta creative specs. |
| `META-CAMPAIGN-002` | blocker | MOS checklist | Campaign must have draft Meta ad set specs. |

Additional campaign-level guardrail:

- If there are ready assets in the scoped generation that do not yet have prepared Meta creative specs, QA fails the campaign with `META-CAMPAIGN-001`.

### 3. Creative Copy Checks

These run against the combined Meta ad copy fields: `primary_text`, `headline`, and `description`.

| Rule ID | Severity | Basis | Check |
| --- | --- | --- | --- |
| `META-COPY-002` | blocker | Meta policy | Flags copy that appears to ask for or imply private/personal information. |
| `META-COPY-003` | blocker | Meta policy | Flags discriminatory or exclusionary language. |
| `META-COPY-004` | high | Meta policy | Flags possible social issues, elections, or politics content for manual review. |
| `META-COPY-005` | high | Meta policy | Flags negative self-perception or shaming language. |

Current keyword heuristics include patterns such as:

- Private information: phrases like "we know you have...", "your medical...", "enter your SSN...", "enter your credit card...".
- Discrimination: phrases like "not for seniors", "only for women", "exclude men".
- SIEP: words like "vote", "election", "candidate", "senate", "governor", "political".
- Negative self-perception: words like "ugly", "fat", "ashamed", "embarrassed", "hide your body".

This is heuristic pattern matching, not a full semantic policy review.

### 4. Destination and Landing Page Checks

These run per prepared Meta creative spec.

| Rule ID | Severity | Basis | Check |
| --- | --- | --- | --- |
| `META-LP-001` | blocker | MOS checklist | Creative spec must have a destination URL. |
| `META-LP-002` | blocker | MOS checklist | Destination must resolve to an absolute public URL. |
| `META-LP-003` | blocker | Meta policy / basic functionality | Destination must be fetchable and not return an error status. |
| `META-LP-004` | blocker | Meta policy / basic functionality | Destination must not appear unfinished or under construction. |
| `META-LP-005` | high | Meta policy | Destination should visibly reference privacy handling or a privacy policy. |
| `META-LP-006` | medium | MOS checklist | Destination should visibly expose contact or support information. |

Current landing-page heuristics include:

- Incomplete page markers: `under construction`, `coming soon`, `launching soon`, `page not found`, `404`.
- Privacy marker: the page text contains `privacy`.
- Contact marker: the page text contains `contact`, `support`, `help center`, `customer service`, a `mailto:` link, or a phone-number-like string.

## How It Validates Inputs

### Meta Account Profile Refresh

Before campaign QA runs, the system attempts to refresh the client Meta profile from Meta Graph and validate:

- Page ID and page name
- Ad account ID and ad account name
- Business Manager ID and name
- Payment source presence and inferred payment type
- Pixel list and selected pixel
- Data Set assignment to the ad account

The refreshed metadata is stored with validation details such as API version, validation time, and source of each resolved value.

### Fields That Are Still Manual

The current Graph refresh does not populate these checklist fields for QA and they remain manual:

- verified domain
- verified domain status
- attribution click window
- attribution view window
- view-through enabled
- data sharing level
- Shopify partner installation state
- tracking provider
- tracking URL parameters

### Landing Page Fetch Strategy

When checking destination pages, the service:

- Resolves the destination URL from the prepared creative spec metadata.
- Converts relative review paths into a public absolute URL using the selected storefront host or configured public base URL.
- Tries to inspect public funnel content through the public funnel API when the destination matches a known funnel route.
- Falls back to a direct HTTP fetch for other public URLs.
- Extracts visible text and runs keyword-based checks against that text.

## What It Does Not Check Yet

- It does not review images or video creatives for policy issues.
- It does not validate claim substantiation, before/after imagery, or category-specific regulated-ad rules.
- It does not guarantee full Meta policy compliance.
- It does not correct copy or landing pages automatically.
- It does not publish to Meta.

## Review Guidance For Marketing

Marketing review should focus on four questions:

1. Are the MOS checklist items the right launch gates, or are any too strict or too loose?
2. Are the copy heuristics catching the right categories of risky language without over-flagging normal marketing copy?
3. Are the landing-page checks aligned with what the team expects to be present before paid traffic goes live?
4. Are there additional claim, creative, or category-specific checks that should exist before publish?

## Implementation References

- Frontend trigger: `mos/frontend/src/components/campaigns/CampaignPaidAdsQaCard.tsx`
- QA panel wrapper: `mos/frontend/src/components/campaigns/meta/MetaQaPanel.tsx`
- Run endpoint: `mos/backend/app/routers/paid_ads_qa.py`
- Main evaluator: `mos/backend/app/services/paid_ads_qa.py`
- Versioned ruleset: `mos/backend/app/static/paid_ads_policy_rules/meta_tiktok_v1.json`
