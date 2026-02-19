# Meta + TikTok Compliance Ruleset v1

- Version: `meta_tiktok_compliance_ruleset_v1`
- Effective date: `2026-02-19`
- Scope: pre-upload compliance checks for landing-page legitimacy and policy-page completeness before any Meta asset upload.

## Source baseline

This ruleset is grounded in primary policy/help sources referenced in internal research:

- TikTok Ad format and functionality: `https://ads.tiktok.com/help/article/tiktok-ads-policy-ad-format-and-functionality`
- TikTok Data Collection Standards: `https://ads.tiktok.com/help/article/data-collection-standards`
- TikTok After Conversion Experience Policy: `https://ads.tiktok.com/help/article/tiktok-after-conversion-experience-policy`
- TikTok Misleading and false content: `https://ads.tiktok.com/help/article/tiktok-ads-policy-misleading-and-false-content`
- Meta Advertising Standards intro: `https://www.facebook.com/policies/ads/`
- Meta Subscription Services: `https://transparency.meta.com/policies/ad-standards/content-specific-restrictions/subscription-services/`
- Meta Unacceptable Business Practices: `https://transparency.meta.com/policies/ad-standards/fraud-scams/unacceptable-business-practices/`
- Meta Lead Ads privacy help: `https://www.facebook.com/business/help/761812391313386`

## Business models supported

- `ecommerce`
- `saas_subscription`
- `digital_product`
- `online_service`
- `lead_generation`

## Canonical policy pages in v1

- `privacy_policy`
- `terms_of_service`
- `returns_refunds_policy`
- `shipping_policy`
- `contact_support`
- `company_information`
- `subscription_terms_and_cancellation`

## Notes

- This ruleset intentionally encodes only explicit/strongly-supported policy drivers from the listed sources.
- For fields that are market-contingent (for example business-license disclosures), template placeholders are provided and must be completed only where legally applicable.
- Any future policy revisions should create a new ruleset version rather than mutating this version in place.
