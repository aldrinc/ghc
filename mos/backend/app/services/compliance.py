from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

RULESET_VERSION = "meta_tiktok_compliance_ruleset_v1"
RULESET_EFFECTIVE_DATE = "2026-02-27"

ALLOWED_BUSINESS_MODELS = {
    "ecommerce",
    "saas_subscription",
    "digital_product",
    "online_service",
    "lead_generation",
}

_CLASSIFICATION_RANK = {
    "not_applicable": 0,
    "strongly_recommended": 1,
    "required": 2,
}

_PAGE_KEY_TO_PROFILE_URL_FIELD = {
    "privacy_policy": "privacy_policy_url",
    "terms_of_service": "terms_of_service_url",
    "returns_refunds_policy": "returns_refunds_policy_url",
    "shipping_policy": "shipping_policy_url",
    "contact_support": "contact_support_url",
    "company_information": "company_information_url",
    "subscription_terms_and_cancellation": "subscription_terms_and_cancellation_url",
}

_PAGE_ORDER = [
    "privacy_policy",
    "terms_of_service",
    "returns_refunds_policy",
    "shipping_policy",
    "contact_support",
    "company_information",
    "subscription_terms_and_cancellation",
]

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")

_RULESET: dict[str, Any] = {
    "version": RULESET_VERSION,
    "effectiveDate": RULESET_EFFECTIVE_DATE,
    "description": (
        "Baseline compliance ruleset for pre-upload website legitimacy checks before Meta submissions, "
        "aligned to Meta and TikTok primary policy/help sources listed in internal compliance research."
    ),
    "sources": [
        {
            "sourceId": "tiktok.ad_format_and_functionality",
            "platform": "tiktok",
            "title": "Ad format and functionality | TikTok Advertising Policies",
            "url": "https://ads.tiktok.com/help/article/tiktok-ads-policy-ad-format-and-functionality",
            "lastUpdated": "2026-01",
        },
        {
            "sourceId": "tiktok.landing_page_best_practices",
            "platform": "tiktok",
            "title": "Best practices for your landing page",
            "url": "https://ads.tiktok.com/help/article/ad-review-checklist-landing-page?lang=en",
            "lastUpdated": "2025-09",
        },
        {
            "sourceId": "tiktok.data_collection_standards",
            "platform": "tiktok",
            "title": "Data Collection Standards",
            "url": "https://ads.tiktok.com/help/article/data-collection-standards",
            "lastUpdated": "2025-02",
        },
        {
            "sourceId": "tiktok.after_conversion_experience",
            "platform": "tiktok",
            "title": "TikTok After Conversion Experience Policy",
            "url": "https://ads.tiktok.com/help/article/tiktok-after-conversion-experience-policy",
            "lastUpdated": "2025-02",
        },
        {
            "sourceId": "tiktok.misleading_and_false_content",
            "platform": "tiktok",
            "title": "Misleading and false content | TikTok Advertising Policies",
            "url": "https://ads.tiktok.com/help/article/tiktok-ads-policy-misleading-and-false-content",
            "lastUpdated": "2025-11",
        },
        {
            "sourceId": "tiktok.lead_ads_privacy_practices",
            "platform": "tiktok",
            "title": "About privacy policies for lead generation ads",
            "url": "https://ads.tiktok.com/help/article/explaining-privacy-practices-to-lead-generation-ads-users?lang=en",
            "lastUpdated": None,
        },
        {
            "sourceId": "tiktok.instant_form_requirements",
            "platform": "tiktok",
            "title": "How to create an Instant Form",
            "url": "https://ads.tiktok.com/help/article/build-instant-form",
            "lastUpdated": None,
        },
        {
            "sourceId": "meta.ads_policies_intro",
            "platform": "meta",
            "title": "Introduction to the Advertising Standards",
            "url": "https://www.facebook.com/policies/ads/",
            "lastUpdated": None,
        },
        {
            "sourceId": "meta.subscription_services",
            "platform": "meta",
            "title": "Subscription Services | Transparency Center",
            "url": "https://transparency.meta.com/policies/ad-standards/content-specific-restrictions/subscription-services/",
            "lastUpdated": None,
        },
        {
            "sourceId": "meta.unacceptable_business_practices",
            "platform": "meta",
            "title": "Unacceptable Business Practices | Transparency Center",
            "url": "https://transparency.meta.com/policies/ad-standards/fraud-scams/unacceptable-business-practices/",
            "lastUpdated": "2024-07-25",
        },
        {
            "sourceId": "meta.fraud_scams_deceptive_practices",
            "platform": "meta",
            "title": "Fraud, Scams and Deceptive Practices | Transparency Center",
            "url": "https://transparency.meta.com/policies/ad-standards/fraud-scams/fraud-scams-deceptive-practices/",
            "lastUpdated": "2025-11-12",
        },
        {
            "sourceId": "meta.privacy_violations_personal_attributes",
            "platform": "meta",
            "title": "Privacy Violations and Personal Attributes | Transparency Center",
            "url": "https://transparency.meta.com/policies/ad-standards/objectionable-content/privacy-violations-personal-attributes/",
            "lastUpdated": "2024-06-26",
        },
        {
            "sourceId": "meta.spam",
            "platform": "meta",
            "title": "Spam | Transparency Center",
            "url": "https://transparency.meta.com/policies/ad-standards/business-assets/spam/",
            "lastUpdated": None,
        },
        {
            "sourceId": "meta.lead_ads_privacy",
            "platform": "meta",
            "title": "About Lead Ads with Instant Form",
            "url": "https://www.facebook.com/business/help/761812391313386",
            "lastUpdated": None,
        },
    ],
    "rules": [
        {
            "ruleId": "tiktok.ecommerce.valid_information",
            "platform": "tiktok",
            "classification": "required",
            "summary": (
                "Ecommerce landing pages must include valid contact/company/privacy/terms/refund/shipping information."
            ),
            "appliesToModels": ["ecommerce"],
            "pageKeys": [
                "privacy_policy",
                "terms_of_service",
                "returns_refunds_policy",
                "shipping_policy",
                "contact_support",
                "company_information",
            ],
            "sourceIds": ["tiktok.ad_format_and_functionality"],
        },
        {
            "ruleId": "tiktok.data_collection.privacy_disclosure",
            "platform": "tiktok",
            "classification": "required",
            "summary": "Landing pages that collect/use data must clearly disclose it via privacy policy.",
            "appliesToModels": [
                "ecommerce",
                "saas_subscription",
                "digital_product",
                "online_service",
                "lead_generation",
            ],
            "pageKeys": ["privacy_policy"],
            "sourceIds": ["tiktok.data_collection_standards"],
        },
        {
            "ruleId": "tiktok.lead_gen.privacy_policy_link",
            "platform": "tiktok",
            "classification": "required",
            "summary": "Lead ads and instant forms must clearly link to the advertiser privacy policy.",
            "appliesToModels": ["lead_generation"],
            "pageKeys": ["privacy_policy"],
            "sourceIds": [
                "tiktok.ad_format_and_functionality",
                "tiktok.lead_ads_privacy_practices",
                "tiktok.instant_form_requirements",
            ],
        },
        {
            "ruleId": "tiktok.landing_page.functionality_and_access",
            "platform": "tiktok",
            "classification": "required",
            "summary": (
                "Landing pages must be functional, not under construction, and must not gate core content behind "
                "personal-info collection or forced software downloads."
            ),
            "appliesToModels": [
                "ecommerce",
                "saas_subscription",
                "digital_product",
                "online_service",
                "lead_generation",
            ],
            "pageKeys": [],
            "sourceIds": ["tiktok.ad_format_and_functionality"],
        },
        {
            "ruleId": "tiktok.landing_page.mobile_identity_best_practice",
            "platform": "tiktok",
            "classification": "strongly_recommended",
            "summary": "Landing pages should be mobile-friendly and include visible company/policy identity in footer.",
            "appliesToModels": [
                "ecommerce",
                "saas_subscription",
                "digital_product",
                "online_service",
                "lead_generation",
            ],
            "pageKeys": ["company_information", "contact_support", "privacy_policy", "terms_of_service"],
            "sourceIds": ["tiktok.landing_page_best_practices"],
        },
        {
            "ruleId": "tiktok.subscriptions.recurring_disclosure",
            "platform": "tiktok",
            "classification": "required",
            "summary": "Subscriptions require upfront recurring-charge disclosure, explicit opt-in, and easy cancellation.",
            "appliesToModels": ["saas_subscription"],
            "pageKeys": ["subscription_terms_and_cancellation"],
            "sourceIds": ["tiktok.after_conversion_experience"],
        },
        {
            "ruleId": "tiktok.post_purchase.refund_support",
            "platform": "tiktok",
            "classification": "required",
            "summary": "Post-purchase support requires clear refund policy and accessible support.",
            "appliesToModels": ["ecommerce", "digital_product", "online_service", "saas_subscription"],
            "pageKeys": ["returns_refunds_policy", "contact_support"],
            "sourceIds": ["tiktok.after_conversion_experience"],
        },
        {
            "ruleId": "tiktok.inconsistent_terms_guardrail",
            "platform": "tiktok",
            "classification": "required",
            "summary": "Ad and landing-page promo/price/terms must stay consistent.",
            "appliesToModels": ["ecommerce", "saas_subscription", "digital_product", "online_service"],
            "pageKeys": ["terms_of_service"],
            "sourceIds": ["tiktok.misleading_and_false_content"],
        },
        {
            "ruleId": "meta.ad_to_landing.match",
            "platform": "meta",
            "classification": "required",
            "summary": "Products and services promoted in ads must match the corresponding landing page.",
            "appliesToModels": [
                "ecommerce",
                "saas_subscription",
                "digital_product",
                "online_service",
                "lead_generation",
            ],
            "pageKeys": ["terms_of_service"],
            "sourceIds": ["meta.ads_policies_intro"],
        },
        {
            "ruleId": "meta.lead_ads.privacy_policy",
            "platform": "meta",
            "classification": "required",
            "summary": "Lead Ads instant forms require privacy policy disclosure link.",
            "appliesToModels": ["lead_generation"],
            "pageKeys": ["privacy_policy"],
            "sourceIds": ["meta.lead_ads_privacy"],
        },
        {
            "ruleId": "meta.subscription.recurring_billing",
            "platform": "meta",
            "classification": "required",
            "summary": "Subscription promotions must clearly disclose price and recurring billing interval.",
            "appliesToModels": ["saas_subscription"],
            "pageKeys": ["subscription_terms_and_cancellation"],
            "sourceIds": ["meta.subscription_services"],
        },
        {
            "ruleId": "meta.privacy.no_private_info_abuse",
            "platform": "meta",
            "classification": "required",
            "summary": "Ads must avoid privacy violations and abusive collection/use of private information.",
            "appliesToModels": [
                "ecommerce",
                "saas_subscription",
                "digital_product",
                "online_service",
                "lead_generation",
            ],
            "pageKeys": ["privacy_policy"],
            "sourceIds": ["meta.privacy_violations_personal_attributes"],
        },
        {
            "ruleId": "meta.legitimacy.business_transparency",
            "platform": "meta",
            "classification": "strongly_recommended",
            "summary": "Business transparency signals reduce deceptive-business risk during review.",
            "appliesToModels": [
                "ecommerce",
                "saas_subscription",
                "digital_product",
                "online_service",
                "lead_generation",
            ],
            "pageKeys": ["company_information", "contact_support", "terms_of_service"],
            "sourceIds": [
                "meta.unacceptable_business_practices",
                "meta.fraud_scams_deceptive_practices",
                "meta.ads_policies_intro",
            ],
        },
        {
            "ruleId": "meta.spam.deceptive_links_guardrail",
            "platform": "meta",
            "classification": "strongly_recommended",
            "summary": "Landing pages and links should avoid spam-like or deceptive-link behavior.",
            "appliesToModels": [
                "ecommerce",
                "saas_subscription",
                "digital_product",
                "online_service",
                "lead_generation",
            ],
            "pageKeys": ["contact_support", "terms_of_service", "privacy_policy"],
            "sourceIds": ["meta.spam"],
        },
    ],
}

_POLICY_TEMPLATES: dict[str, dict[str, Any]] = {
    "privacy_policy": {
        "pageKey": "privacy_policy",
        "title": "Privacy Policy",
        "templateVersion": "v1",
        "description": "Data collection, usage, sharing, and rights disclosures for website visitors and customers.",
        "requiredSections": [
            {"sectionKey": "owner_identity", "title": "Owner and Controller Identity"},
            {"sectionKey": "data_collected", "title": "Data We Collect"},
            {"sectionKey": "data_usage", "title": "How We Use Data"},
            {"sectionKey": "data_sharing", "title": "How We Share Data"},
            {"sectionKey": "user_choices", "title": "User Choices and Controls"},
            {"sectionKey": "security_retention", "title": "Security and Retention"},
            {"sectionKey": "privacy_contact", "title": "Privacy Contact"},
            {"sectionKey": "policy_updates", "title": "Policy Updates and Effective Date"},
        ],
        "placeholders": [
            "legal_business_name",
            "support_email",
            "company_address_text",
            "effective_date",
            "privacy_data_collected",
            "privacy_data_usage",
            "privacy_data_sharing",
            "privacy_user_choices",
            "privacy_security_retention",
            "privacy_update_notice",
        ],
        "templateMarkdown": (
            "# Privacy Policy\n\n"
            "**Operator:** {{legal_business_name}}  \n"
            "**Contact:** {{support_email}}  \n"
            "**Address:** {{company_address_text}}  \n"
            "**Effective date:** {{effective_date}}\n\n"
            "## Owner and Controller Identity\n"
            "{{legal_business_name}} is responsible for the collection and use of personal information described on "
            "this page.\n\n"
            "## Data We Collect\n"
            "{{privacy_data_collected}}\n\n"
            "## How We Use Data\n"
            "{{privacy_data_usage}}\n\n"
            "## How We Share Data\n"
            "{{privacy_data_sharing}}\n\n"
            "## User Choices and Controls\n"
            "{{privacy_user_choices}}\n\n"
            "## Security and Retention\n"
            "{{privacy_security_retention}}\n\n"
            "## Privacy Contact\n"
            "For privacy questions or requests, contact {{support_email}}.\n\n"
            "## Policy Updates and Effective Date\n"
            "{{privacy_update_notice}}\n\n"
            "**Effective date:** {{effective_date}}\n"
        ),
    },
    "terms_of_service": {
        "pageKey": "terms_of_service",
        "title": "Terms of Service",
        "templateVersion": "v1",
        "description": "Commercial terms that must remain consistent with ad claims, pricing, and offer constraints.",
        "requiredSections": [
            {"sectionKey": "business_identity", "title": "Business Identity"},
            {"sectionKey": "offer_scope", "title": "Offer Scope and Eligibility"},
            {"sectionKey": "pricing_terms", "title": "Pricing and Billing Terms"},
            {"sectionKey": "fulfillment_terms", "title": "Fulfillment and Access Terms"},
            {"sectionKey": "refund_cancellation_links", "title": "Refund and Cancellation Links"},
            {"sectionKey": "disclaimers", "title": "Limitations and Disclaimers"},
            {"sectionKey": "dispute_contact", "title": "Support Contact"},
            {"sectionKey": "effective_date", "title": "Effective Date"},
        ],
        "placeholders": [
            "legal_business_name",
            "company_address_text",
            "support_email",
            "effective_date",
            "terms_offer_scope",
            "terms_eligibility",
            "terms_pricing_billing",
            "terms_fulfillment_access",
            "terms_refund_cancellation",
            "terms_disclaimers",
        ],
        "templateMarkdown": (
            "# Terms of Service\n\n"
            "These terms govern purchases from {{legal_business_name}}.\n\n"
            "## Business Identity\n"
            "**Legal business name:** {{legal_business_name}}  \n"
            "**Business address:** {{company_address_text}}\n\n"
            "## Offer Scope and Eligibility\n"
            "{{terms_offer_scope}}\n\n"
            "{{terms_eligibility}}\n\n"
            "## Pricing and Billing Terms\n"
            "{{terms_pricing_billing}}\n\n"
            "## Fulfillment and Access Terms\n"
            "{{terms_fulfillment_access}}\n\n"
            "## Refund and Cancellation Links\n"
            "{{terms_refund_cancellation}}\n\n"
            "## Limitations and Disclaimers\n"
            "{{terms_disclaimers}}\n\n"
            "## Support Contact\n"
            "Contact: {{support_email}}\n\n"
            "**Effective date:** {{effective_date}}\n"
        ),
    },
    "returns_refunds_policy": {
        "pageKey": "returns_refunds_policy",
        "title": "Returns and Refunds Policy",
        "templateVersion": "v1",
        "description": "Eligibility, time windows, process, and payout method for refunds/returns.",
        "requiredSections": [
            {"sectionKey": "eligibility", "title": "Eligibility"},
            {"sectionKey": "window", "title": "Return/Refund Window"},
            {"sectionKey": "process", "title": "How to Request"},
            {"sectionKey": "method_timing", "title": "Refund Method and Timing"},
            {"sectionKey": "fees", "title": "Fees and Deductions"},
            {"sectionKey": "exceptions", "title": "Exceptions"},
            {"sectionKey": "support_contact", "title": "Support Contact"},
        ],
        "placeholders": [
            "legal_business_name",
            "support_email",
            "effective_date",
            "refund_eligibility",
            "refund_window_policy",
            "refund_request_steps",
            "refund_method_timing",
            "refund_fees_deductions",
            "refund_exceptions",
        ],
        "templateMarkdown": (
            "# Returns and Refunds Policy\n\n"
            "This policy applies to purchases from {{legal_business_name}}.\n\n"
            "## Eligibility\n"
            "{{refund_eligibility}}\n\n"
            "## Return/Refund Window\n"
            "{{refund_window_policy}}\n\n"
            "## How to Request\n"
            "{{refund_request_steps}}\n\n"
            "## Refund Method and Timing\n"
            "{{refund_method_timing}}\n\n"
            "## Fees and Deductions\n"
            "{{refund_fees_deductions}}\n\n"
            "## Exceptions\n"
            "{{refund_exceptions}}\n\n"
            "## Support Contact\n"
            "{{support_email}}\n\n"
            "**Effective date:** {{effective_date}}\n"
        ),
    },
    "shipping_policy": {
        "pageKey": "shipping_policy",
        "title": "Shipping Policy",
        "templateVersion": "v1",
        "description": "Coverage, shipping charges, fulfillment timelines, and issue handling.",
        "requiredSections": [
            {"sectionKey": "coverage", "title": "Shipping Regions"},
            {"sectionKey": "processing_time", "title": "Processing Time"},
            {"sectionKey": "options_costs", "title": "Shipping Options and Costs"},
            {"sectionKey": "delivery_estimates", "title": "Delivery Estimates"},
            {"sectionKey": "tracking", "title": "Tracking"},
            {"sectionKey": "address_changes", "title": "Address Changes"},
            {"sectionKey": "lost_damaged", "title": "Lost or Damaged Packages"},
            {"sectionKey": "customs_duties", "title": "Customs and Duties"},
            {"sectionKey": "return_address", "title": "Return Address"},
            {"sectionKey": "support_contact", "title": "Shipping Support Contact"},
            {"sectionKey": "effective_date", "title": "Effective Date"},
        ],
        "placeholders": [
            "support_email",
            "effective_date",
            "shipping_regions",
            "shipping_processing_time",
            "shipping_options_costs",
            "shipping_delivery_estimates",
            "shipping_tracking",
            "shipping_address_changes",
            "shipping_lost_damaged",
            "shipping_customs_duties",
            "shipping_return_address",
        ],
        "templateMarkdown": (
            "# Shipping Policy\n\n"
            "## Shipping Regions\n"
            "{{shipping_regions}}\n\n"
            "## Processing Time\n"
            "{{shipping_processing_time}}\n\n"
            "## Shipping Options and Costs\n"
            "{{shipping_options_costs}}\n\n"
            "## Delivery Estimates\n"
            "{{shipping_delivery_estimates}}\n\n"
            "## Tracking\n"
            "{{shipping_tracking}}\n\n"
            "## Address Changes\n"
            "{{shipping_address_changes}}\n\n"
            "## Lost or Damaged Packages\n"
            "{{shipping_lost_damaged}}\n\n"
            "## Customs and Duties\n"
            "{{shipping_customs_duties}}\n\n"
            "## Return Address\n"
            "{{shipping_return_address}}\n\n"
            "## Shipping Support Contact\n"
            "{{support_email}}\n\n"
            "**Effective date:** {{effective_date}}\n"
        ),
    },
    "contact_support": {
        "pageKey": "contact_support",
        "title": "Contact and Support",
        "templateVersion": "v1",
        "description": "Accessible support channels and response-time commitments.",
        "requiredSections": [
            {"sectionKey": "contact_channels", "title": "Contact Channels"},
            {"sectionKey": "support_hours", "title": "Support Hours"},
            {"sectionKey": "response_sla", "title": "Expected Response Time"},
            {"sectionKey": "order_help", "title": "Order and Account Help"},
            {"sectionKey": "business_address", "title": "Business Address"},
            {"sectionKey": "policy_links", "title": "Related Policy Links"},
        ],
        "placeholders": [
            "support_email",
            "support_phone",
            "support_hours_text",
            "response_time_commitment",
            "support_order_help_links",
            "company_address_text",
        ],
        "templateMarkdown": (
            "# Contact and Support\n\n"
            "## Contact Channels\n"
            "- Email: {{support_email}}\n"
            "- Phone: {{support_phone}}\n\n"
            "## Support Hours\n"
            "{{support_hours_text}}\n\n"
            "## Expected Response Time\n"
            "{{response_time_commitment}}\n\n"
            "## Order and Account Help\n"
            "{{support_order_help_links}}\n\n"
            "## Business Address\n"
            "{{company_address_text}}\n\n"
            "## Related Policy Links\n"
            "Link to returns/refunds, shipping, privacy, and subscription terms (if applicable).\n"
        ),
    },
    "company_information": {
        "pageKey": "company_information",
        "title": "Company Information",
        "templateVersion": "v1",
        "description": "Legal entity and ownership transparency details.",
        "requiredSections": [
            {"sectionKey": "legal_identity", "title": "Legal Entity"},
            {"sectionKey": "address", "title": "Registered/Business Address"},
            {"sectionKey": "brand_name", "title": "Customer-Facing Brand Name"},
            {"sectionKey": "ownership", "title": "Ownership/Operator"},
            {"sectionKey": "license", "title": "Business License (Where Required)"},
            {"sectionKey": "support_contact", "title": "Support Contact"},
        ],
        "placeholders": [
            "legal_business_name",
            "company_address_text",
            "brand_name",
            "operating_entity_name",
            "business_license_identifier",
            "support_email",
            "support_phone",
        ],
        "templateMarkdown": (
            "# Company Information\n\n"
            "## Legal Entity\n"
            "{{legal_business_name}}\n\n"
            "## Registered/Business Address\n"
            "{{company_address_text}}\n\n"
            "## Customer-Facing Brand Name\n"
            "{{brand_name}}\n\n"
            "## Ownership/Operator\n"
            "{{operating_entity_name}}\n\n"
            "## Business License (Where Required)\n"
            "{{business_license_identifier}}\n\n"
            "## Support Contact\n"
            "Email: {{support_email}}  \n"
            "Phone: {{support_phone}}\n"
        ),
    },
    "subscription_terms_and_cancellation": {
        "pageKey": "subscription_terms_and_cancellation",
        "title": "Subscription Terms and Cancellation",
        "templateVersion": "v1",
        "description": "Recurring billing disclosures, consent mechanics, renewal behavior, and cancellation process.",
        "requiredSections": [
            {"sectionKey": "included_features", "title": "Included Features"},
            {"sectionKey": "plans", "title": "Plans, Price, and Billing Interval"},
            {"sectionKey": "renewal", "title": "Auto-Renew Behavior"},
            {"sectionKey": "trial_terms", "title": "Trial Terms"},
            {"sectionKey": "consent", "title": "Recurring Billing Consent"},
            {"sectionKey": "cancellation", "title": "Cancellation Steps"},
            {"sectionKey": "subscription_refunds", "title": "Subscription Refund Rules"},
            {"sectionKey": "billing_support", "title": "Billing Support Contact"},
            {"sectionKey": "effective_date", "title": "Effective Date"},
        ],
        "placeholders": [
            "legal_business_name",
            "subscription_included_features",
            "subscription_plan_table",
            "subscription_auto_renew_terms",
            "subscription_trial_terms",
            "subscription_explicit_consent",
            "cancellation_steps",
            "subscription_refund_rules",
            "subscription_billing_support",
            "support_email",
            "effective_date",
        ],
        "templateMarkdown": (
            "# Subscription Terms and Cancellation\n\n"
            "These terms apply to recurring services provided by {{legal_business_name}}.\n\n"
            "## Included Features\n"
            "{{subscription_included_features}}\n\n"
            "## Plans, Price, and Billing Interval\n"
            "{{subscription_plan_table}}\n\n"
            "## Auto-Renew Behavior\n"
            "{{subscription_auto_renew_terms}}\n\n"
            "## Trial Terms\n"
            "{{subscription_trial_terms}}\n\n"
            "## Recurring Billing Consent\n"
            "{{subscription_explicit_consent}}\n\n"
            "## Cancellation Steps\n"
            "{{cancellation_steps}}\n\n"
            "## Subscription Refund Rules\n"
            "{{subscription_refund_rules}}\n\n"
            "## Billing Support Contact\n"
            "{{subscription_billing_support}}\n\n"
            "Primary support email: {{support_email}}  \n"
            "**Effective date:** {{effective_date}}\n"
        ),
    },
}


def list_rulesets() -> list[dict[str, Any]]:
    return [
        {
            "version": _RULESET["version"],
            "effectiveDate": _RULESET["effectiveDate"],
            "description": _RULESET["description"],
            "sourceCount": len(_RULESET["sources"]),
            "ruleCount": len(_RULESET["rules"]),
        }
    ]


def get_ruleset(*, version: str) -> dict[str, Any]:
    if version != RULESET_VERSION:
        raise KeyError(f"Unknown compliance ruleset version: {version}")
    return deepcopy(_RULESET)


def normalize_business_models(values: list[str]) -> list[str]:
    if not values:
        raise ValueError("businessModels must include at least one business model.")

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        cleaned = raw.strip().lower()
        if cleaned not in ALLOWED_BUSINESS_MODELS:
            valid = ", ".join(sorted(ALLOWED_BUSINESS_MODELS))
            raise ValueError(f"Invalid business model '{raw}'. Valid values: {valid}.")
        if cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def list_policy_templates() -> list[dict[str, Any]]:
    ordered: list[dict[str, Any]] = []
    for page_key in _PAGE_ORDER:
        template = _POLICY_TEMPLATES[page_key]
        ordered.append(deepcopy(template))
    return ordered


def get_policy_template(*, page_key: str) -> dict[str, Any]:
    if page_key not in _POLICY_TEMPLATES:
        raise KeyError(f"Unknown policy template key: {page_key}")
    return deepcopy(_POLICY_TEMPLATES[page_key])


def list_policy_page_keys() -> list[str]:
    return list(_PAGE_ORDER)


def get_profile_url_field_for_page_key(*, page_key: str) -> str:
    if page_key not in _PAGE_KEY_TO_PROFILE_URL_FIELD:
        raise KeyError(f"Unknown policy template key: {page_key}")
    return _PAGE_KEY_TO_PROFILE_URL_FIELD[page_key]


def get_policy_page_handle(*, page_key: str) -> str:
    if page_key not in _POLICY_TEMPLATES:
        raise KeyError(f"Unknown policy template key: {page_key}")
    return page_key.replace("_", "-")


def render_policy_template_markdown(
    *,
    page_key: str,
    placeholder_values: dict[str, str],
) -> str:
    template = get_policy_template(page_key=page_key)
    template_markdown = template["templateMarkdown"]
    expected_placeholders = template["placeholders"]

    missing_placeholders: list[str] = []
    normalized_values: dict[str, str] = {}
    for placeholder in expected_placeholders:
        raw_value = placeholder_values.get(placeholder)
        if raw_value is None or not raw_value.strip():
            missing_placeholders.append(placeholder)
            continue
        normalized_values[placeholder] = raw_value.strip()

    if missing_placeholders:
        missing = ", ".join(sorted(missing_placeholders))
        raise ValueError(
            f"Missing placeholder values for page '{page_key}': {missing}."
        )

    def _replace(match: re.Match[str]) -> str:
        placeholder = match.group(1)
        if placeholder not in normalized_values:
            raise ValueError(
                f"Missing placeholder value for page '{page_key}': {placeholder}."
            )
        return normalized_values[placeholder]

    rendered = _PLACEHOLDER_RE.sub(_replace, template_markdown)
    unresolved = sorted({match.group(1) for match in _PLACEHOLDER_RE.finditer(rendered)})
    if unresolved:
        unresolved_str = ", ".join(unresolved)
        raise ValueError(
            f"Unresolved placeholders remain for page '{page_key}': {unresolved_str}."
        )
    return rendered


def _max_classification(current: str, candidate: str) -> str:
    if _CLASSIFICATION_RANK[candidate] > _CLASSIFICATION_RANK[current]:
        return candidate
    return current


def build_page_requirements(
    *,
    ruleset_version: str,
    business_models: list[str],
    page_urls: dict[str, str | None],
) -> dict[str, Any]:
    if ruleset_version != RULESET_VERSION:
        raise ValueError(
            f"Unsupported rulesetVersion '{ruleset_version}'. Supported version: '{RULESET_VERSION}'."
        )

    normalized_models = normalize_business_models(business_models)

    page_matrix: dict[str, dict[str, Any]] = {
        page_key: {
            "pageKey": page_key,
            "title": _POLICY_TEMPLATES[page_key]["title"],
            "classification": "not_applicable",
            "triggeredRuleIds": [],
            "configuredUrl": (page_urls.get(page_key) or None),
            "configured": bool((page_urls.get(page_key) or "").strip()),
            "profileUrlField": _PAGE_KEY_TO_PROFILE_URL_FIELD[page_key],
        }
        for page_key in _PAGE_ORDER
    }

    for rule in _RULESET["rules"]:
        applies_to = set(rule["appliesToModels"])
        if not set(normalized_models).intersection(applies_to):
            continue
        for page_key in rule["pageKeys"]:
            if page_key not in page_matrix:
                continue
            entry = page_matrix[page_key]
            entry["classification"] = _max_classification(entry["classification"], rule["classification"])
            if rule["ruleId"] not in entry["triggeredRuleIds"]:
                entry["triggeredRuleIds"].append(rule["ruleId"])

    pages = [page_matrix[page_key] for page_key in _PAGE_ORDER]
    missing_required_page_keys = [
        page["pageKey"]
        for page in pages
        if page["classification"] == "required" and not page["configured"]
    ]
    missing_recommended_page_keys = [
        page["pageKey"]
        for page in pages
        if page["classification"] == "strongly_recommended" and not page["configured"]
    ]

    return {
        "rulesetVersion": ruleset_version,
        "businessModels": normalized_models,
        "pages": pages,
        "missingRequiredPageKeys": missing_required_page_keys,
        "missingRecommendedPageKeys": missing_recommended_page_keys,
    }
