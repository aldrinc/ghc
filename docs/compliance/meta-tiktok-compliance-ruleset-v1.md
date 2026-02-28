# Meta + TikTok Compliance Ruleset v1

- Version: `meta_tiktok_compliance_ruleset_v1`
- Effective date: `2026-02-27`
- Scope: pre-upload compliance checks for landing-page legitimacy and policy-page completeness before Meta and TikTok ad traffic.

## Source baseline

This ruleset is grounded in primary policy/help sources referenced in internal research:

- TikTok Ad format and functionality: `https://ads.tiktok.com/help/article/tiktok-ads-policy-ad-format-and-functionality`
- TikTok Landing page best practices: `https://ads.tiktok.com/help/article/ad-review-checklist-landing-page?lang=en`
- TikTok Data Collection Standards: `https://ads.tiktok.com/help/article/data-collection-standards`
- TikTok After Conversion Experience Policy: `https://ads.tiktok.com/help/article/tiktok-after-conversion-experience-policy`
- TikTok Misleading and false content: `https://ads.tiktok.com/help/article/tiktok-ads-policy-misleading-and-false-content`
- TikTok Lead ads privacy practices: `https://ads.tiktok.com/help/article/explaining-privacy-practices-to-lead-generation-ads-users?lang=en`
- TikTok Instant form requirements: `https://ads.tiktok.com/help/article/build-instant-form`
- Meta Advertising Standards intro: `https://www.facebook.com/policies/ads/`
- Meta Subscription Services: `https://transparency.meta.com/policies/ad-standards/content-specific-restrictions/subscription-services/`
- Meta Unacceptable Business Practices: `https://transparency.meta.com/policies/ad-standards/fraud-scams/unacceptable-business-practices/`
- Meta Fraud, Scams and Deceptive Practices: `https://transparency.meta.com/policies/ad-standards/fraud-scams/fraud-scams-deceptive-practices/`
- Meta Privacy Violations and Personal Attributes: `https://transparency.meta.com/policies/ad-standards/objectionable-content/privacy-violations-personal-attributes/`
- Meta Spam: `https://transparency.meta.com/policies/ad-standards/business-assets/spam/`
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

## Rule inventory

- `tiktok.ecommerce.valid_information` (`required`)
- `tiktok.data_collection.privacy_disclosure` (`required`)
- `tiktok.lead_gen.privacy_policy_link` (`required`)
- `tiktok.landing_page.functionality_and_access` (`required`)
- `tiktok.landing_page.mobile_identity_best_practice` (`strongly_recommended`)
- `tiktok.subscriptions.recurring_disclosure` (`required`)
- `tiktok.post_purchase.refund_support` (`required`)
- `tiktok.inconsistent_terms_guardrail` (`required`)
- `meta.ad_to_landing.match` (`required`)
- `meta.lead_ads.privacy_policy` (`required`)
- `meta.subscription.recurring_billing` (`required`)
- `meta.privacy.no_private_info_abuse` (`required`)
- `meta.legitimacy.business_transparency` (`strongly_recommended`)
- `meta.spam.deceptive_links_guardrail` (`strongly_recommended`)

## Notes

- This ruleset intentionally encodes only explicit/strongly-supported policy drivers from the listed sources.
- For fields that are market-contingent (for example business-license disclosures), template placeholders are provided and must be completed only where legally applicable.
- Any future policy revisions should create a new ruleset version rather than mutating this version in place.
