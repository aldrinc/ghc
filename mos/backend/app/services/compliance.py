from __future__ import annotations

from copy import deepcopy
from html import escape
from pathlib import Path
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

_POLICY_TEMPLATE_FILENAME_BY_PAGE_KEY = {
    "privacy_policy": "privacy_policy.md",
    "terms_of_service": "terms_of_service.md",
    "returns_refunds_policy": "returns_refunds_policy.md",
    "shipping_policy": "shipping_policy.md",
    "company_information": "company_information.md",
    "subscription_terms_and_cancellation": "subscription_terms_and_cancellation.md",
}

_THEME_MANAGED_POLICY_TEMPLATE_MARKDOWN_BY_PAGE_KEY = {
    "contact_support": (
        "# Contact and Support\n\n"
        "This page is theme-managed and should use the storefront contact-form template.\n"
    )
}

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")
_STRONG_RE = re.compile(r"\*\*(.+?)\*\*")

_DEFAULT_POLICY_PLACEHOLDER_VALUES: dict[str, str] = {
    "effective_date": "2026-02-27",
    "privacy_data_collected": (
        "We collect device details, browsing activity, order information (including contact, billing, and "
        "shipping details), and support interactions, including analytics and ad-attribution events."
    ),
    "privacy_data_usage": (
        "Personal information is used to operate the store, process payments and shipping, provide support, "
        "screen orders for risk or fraud, and improve site and marketing performance."
    ),
    "privacy_data_sharing": (
        "Data is shared only with service providers that support checkout, fulfillment, analytics, and messaging, "
        "or when required by law."
    ),
    "privacy_user_choices": (
        "Customers can opt out of marketing where available and can request access, correction, or deletion by "
        "contacting support."
    ),
    "privacy_security_retention": (
        "Reasonable technical and organizational safeguards are applied, and data is retained only as long as needed "
        "for business and legal purposes."
    ),
    "privacy_update_notice": (
        "This policy may be updated periodically to reflect operational, legal, or regulatory changes, and updates "
        "are published on this page."
    ),
    "terms_offer_scope": (
        "Use of this website and related services is conditioned on acceptance of these Terms and posted "
        "policy notices."
    ),
    "terms_eligibility": (
        "By using the site or placing an order, customers agree to these Terms and confirm they will comply "
        "with applicable laws."
    ),
    "terms_pricing_billing": (
        "Prices and charges are shown before purchase confirmation, and payment authorization is required before "
        "order fulfillment."
    ),
    "terms_fulfillment_access": (
        "Order acceptance, shipping, and service access remain subject to availability, fraud screening, and "
        "operational constraints."
    ),
    "terms_refund_cancellation": (
        "Refund and cancellation terms are defined in the Returns and Refunds Policy and Shipping Policy available "
        "in the site footer."
    ),
    "terms_disclaimers": (
        "Services are provided on an as-is and as-available basis to the fullest extent permitted by law."
    ),
    "terms_dispute_resolution": (
        "To the fullest extent permitted by law, disputes arising from these Terms are resolved through binding "
        "arbitration in the United States before one arbitrator."
    ),
    "terms_governing_law": "These Terms are governed by the laws of the United States.",
    "refund_eligibility": (
        "Returns are eligible within 90 days when items are unused, in original packaging, and include proof "
        "of purchase."
    ),
    "refund_window_policy": (
        "Returns can be requested within 90 days of delivery, and cancellations requested within 12 hours are "
        "eligible for full refund when fulfillment has not started."
    ),
    "refund_request_steps": (
        "Contact support with order details and return reason before sending any item back; unauthorized returns "
        "are not accepted."
    ),
    "refund_method_timing": (
        "Approved refunds are issued to the original payment method after review and may take up to 5 business "
        "days to post."
    ),
    "refund_fees_deductions": (
        "Return shipping charges are customer responsibility unless the item was incorrect or defective; "
        "non-refundable service charges may apply after fulfillment."
    ),
    "refund_exceptions": (
        "Final-sale, refused-delivery, abuse-related, and certain post-delivery loss claims may be excluded or "
        "resolved at the business's discretion where law allows."
    ),
    "shipping_regions": (
        "We ship to the United States and Australia, with worldwide tracked shipping available for many regions."
    ),
    "shipping_processing_time": (
        "Typical delivery windows are: USA 1-3 business days, Australia 1-4 business days, Worldwide tracked "
        "4-13 business days, and PO Box or military addresses 4-30 business days."
    ),
    "shipping_options_costs": (
        "Shipping options and costs are shown at checkout, including free shipping routes where available."
    ),
    "shipping_delivery_estimates": (
        "Estimated delivery windows vary by destination, including domestic and international ranges shown at "
        "checkout."
    ),
    "shipping_tracking": (
        "Tracked shipping updates are provided once an order has been dispatched."
    ),
    "shipping_address_changes": (
        "Address changes and cancellation requests must be submitted promptly and cannot be guaranteed after "
        "fulfillment begins."
    ),
    "shipping_lost_damaged": (
        "Lost, delayed, or damaged delivery issues should be reported to support promptly for claim review and next "
        "steps."
    ),
    "shipping_customs_duties": (
        "International customs duties, import taxes, and related fees are the customer's responsibility unless "
        "explicitly stated otherwise."
    ),
    "shipping_return_address": (
        "Return shipments must be sent to the return address provided by support after return authorization."
    ),
    "support_order_help_links": (
        "Order tracking: /pages/track-your-order | FAQ: /pages/faqs | Contact support: /pages/contact"
    ),
    "support_hours_text": "24/7",
    "response_time_commitment": "30 minutes",
}

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
        "description": (
            "Ecommerce privacy disclosures with explicit data-use, marketing, and user-rights sections "
            "modeled after current production policy structure."
        ),
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
            "brand_name",
            "website_url",
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
            "## Privacy Policy for {{brand_name}}\n\n"
            "**Effective Date: {{effective_date}}**\n\n"
            "{{legal_business_name}} (\"{{brand_name}}\", \"we\", \"us\", \"our\") is committed to safeguarding "
            "the privacy of users who interact with {{website_url}}.\n\n"
            "This Privacy Policy explains what information we collect, how we use it, and the measures we take "
            "to protect it.\n\n"
            "By accessing or using our services, you agree to this Privacy Policy.\n\n"
            "## Information We Collect\n"
            "1. **Personal Information**\n"
            "We may collect personal information such as name, email address, shipping/billing details, and "
            "contact information when you place an order, create an account, or contact support.\n\n"
            "2. **Usage Information**\n"
            "We collect information about interactions with our website, including pages viewed, time on page, "
            "clicks, and conversion events.\n\n"
            "3. **Device Information**\n"
            "We may collect technical details about the device and browser used to access our services.\n\n"
            "{{privacy_data_collected}}\n\n"
            "## How We Use Your Information\n"
            "1. **To Provide Services**\n"
            "We use collected information to operate the store, process payments, fulfill orders, provide support, "
            "and improve customer experience.\n\n"
            "2. **Marketing and Communication**\n"
            "Where permitted, we may use your contact details to send promotional communications and updates.\n\n"
            "3. **Analytics and Improvement**\n"
            "We use analytics to understand usage behavior and improve website and service performance.\n\n"
            "{{privacy_data_usage}}\n\n"
            "## Sharing Your Information\n"
            "We do not sell personal information. We may share data with service providers required to operate "
            "the business and as required by law.\n\n"
            "{{privacy_data_sharing}}\n\n"
            "## Security\n"
            "We apply reasonable safeguards to protect personal information from unauthorized access, alteration, "
            "disclosure, or destruction.\n\n"
            "{{privacy_security_retention}}\n\n"
            "## Your Choices\n"
            "You may request access, correction, or deletion of personal information where applicable, and you may "
            "opt out of marketing communications.\n\n"
            "{{privacy_user_choices}}\n\n"
            "## Changes to This Privacy Policy\n"
            "We may update this Privacy Policy at any time. Updated versions are posted on this page.\n\n"
            "{{privacy_update_notice}}\n\n"
            "## Contact Us\n"
            "If you have questions about this Privacy Policy, contact us at {{support_email}}.\n\n"
            "Business address: {{company_address_text}}\n"
        ),
    },
    "terms_of_service": {
        "pageKey": "terms_of_service",
        "title": "Terms of Service",
        "templateVersion": "v1",
        "description": (
            "Storefront terms based on current production structure, including order controls, disputes, "
            "and governing-law disclosures."
        ),
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
            "brand_name",
            "website_url",
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
            "terms_dispute_resolution",
            "terms_governing_law",
        ],
        "templateMarkdown": (
            "# Terms of Service\n\n"
            "## Terms and Conditions {{brand_name}}\n"
            "**Effective Date: {{effective_date}}**\n\n"
            "These Terms and Conditions (\"Terms\") govern your use of {{website_url}} and the services provided "
            "by {{brand_name}}, operated by {{legal_business_name}} and located at {{company_address_text}} "
            "(\"we\", \"us\", \"our\").\n\n"
            "By accessing or using our website and purchasing our products, you agree to be bound by these Terms.\n\n"
            "Please read them carefully before placing an order.\n\n"
            "## 1. Eligibility to Purchase\n"
            "To place an order with {{brand_name}}, you must be at least 18 years old and have a valid payment "
            "method accepted at checkout.\n\n"
            "{{terms_eligibility}}\n\n"
            "## 2. Product Information\n"
            "We make every effort to ensure products shown on our website are accurately described. Slight "
            "variations in color, size, or texture may occur due to screen settings and material characteristics.\n\n"
            "All products are subject to availability, and we reserve the right to withdraw products at any time.\n\n"
            "{{terms_offer_scope}}\n\n"
            "## 3. Order Process & Contract\n"
            "After placing an order, you will receive an email acknowledgment. This acknowledgment does not "
            "constitute acceptance of your order.\n\n"
            "Order acceptance occurs once payment is successfully processed and the order has been dispatched "
            "(or access has been delivered for non-physical products).\n\n"
            "We reserve the right to refuse or cancel any order for reasons including product availability, "
            "pricing/content errors, suspected fraud, or other reasons at our discretion.\n\n"
            "## 4. Pricing & Payment Terms\n"
            "All prices are shown at checkout and may exclude taxes, duties, or shipping unless stated otherwise.\n\n"
            "Accepted payment methods are shown at checkout and may vary by region.\n\n"
            "Prices and product availability are subject to change without notice.\n\n"
            "{{terms_pricing_billing}}\n\n"
            "## 5. Shipping & Delivery\n"
            "Delivery timelines are estimates and can vary because of customs processing, carrier constraints, "
            "weather, or other external factors outside our control.\n\n"
            "{{terms_fulfillment_access}}\n\n"
            "## 6. Returns & Exchanges\n"
            "Returns and exchanges are handled under our posted refund and returns terms.\n\n"
            "{{terms_refund_cancellation}}\n\n"
            "## 7. Limitation of Liability\n"
            "To the maximum extent permitted by applicable law, our total liability for any claim related to "
            "products or services is limited to the amount you paid for the relevant order.\n\n"
            "We are not liable for indirect, incidental, punitive, or consequential damages arising from use of "
            "our products, services, or website.\n\n"
            "{{terms_disclaimers}}\n\n"
            "## 8. Intellectual Property Rights\n"
            "All website content, including text, graphics, logos, images, product names, and designs, is owned "
            "by {{brand_name}} and/or its licensors.\n\n"
            "You may not reproduce, duplicate, copy, sell, resell, or exploit any content without prior written "
            "permission.\n\n"
            "## 9. Privacy Policy\n"
            "Your submission of personal information through our store is governed by our Privacy Policy.\n\n"
            "## 10. Force Majeure\n"
            "We are not liable for delays or failure to perform obligations due to causes beyond reasonable "
            "control, including natural disasters, labor disputes, war, carrier outages, infrastructure failures, "
            "or government action.\n\n"
            "## 11. Governing Law and Jurisdiction\n"
            "{{terms_governing_law}}\n\n"
            "{{terms_dispute_resolution}}\n\n"
            "## 12. Changes to Terms\n"
            "We reserve the right to update or modify these Terms at any time.\n\n"
            "Changes take effect when posted on this page. Continued use of the website after updates constitutes "
            "acceptance of the revised Terms.\n\n"
            "## 13. Contact Information\n"
            "For questions about these Terms, contact us at {{support_email}}.\n"
        ),
    },
    "returns_refunds_policy": {
        "pageKey": "returns_refunds_policy",
        "title": "Returns and Refunds Policy",
        "templateVersion": "v1",
        "description": (
            "Returns and refunds terms modeled after current production policy flow, including cancellation windows, "
            "condition checks, and processing timelines."
        ),
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
            "brand_name",
            "website_url",
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
            "We have a return window for eligible purchases. Return eligibility, timelines, and processing rules "
            "are described below.\n\n"
            "## Return Window\n"
            "{{refund_window_policy}}\n\n"
            "## Eligibility for Returns\n"
            "To be eligible for a return, items must be in the same condition received, unused/unworn, with "
            "original tags and packaging, and accompanied by proof of purchase.\n\n"
            "{{refund_eligibility}}\n\n"
            "## How to Start a Return\n"
            "Contact support before sending any return.\n\n"
            "{{refund_request_steps}}\n\n"
            "## Damages and Issues\n"
            "Please inspect your order upon delivery and contact us immediately if an item is defective, damaged, "
            "or incorrect so we can evaluate and resolve the issue.\n\n"
            "## Exceptions / Non-Returnable Items\n"
            "Certain item categories may be non-returnable (for example, final-sale, personalized, perishable, "
            "hygiene, hazardous, or gift-card products) where permitted by law.\n\n"
            "{{refund_exceptions}}\n\n"
            "## Exchanges\n"
            "The fastest way to get a different item is to return the original eligible item first, and place a "
            "separate order for the replacement item after return approval.\n\n"
            "## EU 14-Day Cooling-Off Period\n"
            "Where required by law (including eligible EU orders), customers may cancel or return an order within "
            "14 days of receipt without justification, provided eligibility conditions are met.\n\n"
            "## Refunds\n"
            "After we receive and inspect your return, we will notify you whether the refund is approved.\n\n"
            "Approved refunds are sent to the original payment method.\n\n"
            "{{refund_method_timing}}\n\n"
            "{{refund_fees_deductions}}\n\n"
            "If your refund has not posted within the disclosed time window, contact {{support_email}}.\n\n"
            "**Effective date:** {{effective_date}}\n"
        ),
    },
    "shipping_policy": {
        "pageKey": "shipping_policy",
        "title": "Shipping Policy",
        "templateVersion": "v1",
        "description": (
            "Shipping terms aligned with current production flow for processing windows, delivery expectations, "
            "tracking, and exceptions."
        ),
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
            "brand_name",
            "website_url",
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
            "## Shipping Policy for {{brand_name}}\n\n"
            "Welcome to {{brand_name}}'s Shipping Policy. This page outlines terms that apply to shipment and "
            "delivery for orders placed through {{website_url}}.\n\n"
            "By placing an order, you agree to these shipping terms.\n\n"
            "## 1. Order Processing\n"
            "Orders are typically processed on business days after purchase.\n\n"
            "{{shipping_processing_time}}\n\n"
            "## 2. Shipping Methods\n"
            "Available shipping methods are shown at checkout, along with estimated delivery windows.\n\n"
            "{{shipping_delivery_estimates}}\n\n"
            "## 3. Shipping Locations\n"
            "We ship to approved destinations based on carrier availability and legal constraints.\n\n"
            "{{shipping_regions}}\n\n"
            "## 4. Shipping Costs\n"
            "Shipping charges are calculated at checkout based on selected method and destination.\n\n"
            "{{shipping_options_costs}}\n\n"
            "## 5. Customs and Duties\n"
            "For international shipments, customs fees, duties, or import taxes may apply and are generally the "
            "recipient's responsibility unless stated otherwise.\n\n"
            "{{shipping_customs_duties}}\n\n"
            "## 6. Order Tracking\n"
            "Tracking details are provided after dispatch when available.\n\n"
            "{{shipping_tracking}}\n\n"
            "## 7. Shipping Delays\n"
            "Estimated delivery windows are not guaranteed. Delays can occur due to weather, customs, carrier "
            "constraints, or other factors outside our control.\n\n"
            "## 8. Lost or Stolen Packages\n"
            "If a shipment is lost, delayed, damaged, or marked delivered but not received, contact support "
            "promptly so we can assist with investigation and next steps.\n\n"
            "{{shipping_lost_damaged}}\n\n"
            "## 9. Returns Due to Shipping Issues\n"
            "If an order is returned due to address or delivery issues, we will contact you to arrange reshipment "
            "where possible.\n\n"
            "{{shipping_address_changes}}\n\n"
            "Return shipments must be sent only to the authorized return address provided by support.\n\n"
            "{{shipping_return_address}}\n\n"
            "## Contact Us\n"
            "If you have questions about shipping, contact {{support_email}}.\n\n"
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

_template_keys = set(_POLICY_TEMPLATES)
_file_map_keys = set(_POLICY_TEMPLATE_FILENAME_BY_PAGE_KEY)
_theme_managed_markdown_keys = set(_THEME_MANAGED_POLICY_TEMPLATE_MARKDOWN_BY_PAGE_KEY)
_covered_keys = _file_map_keys | _theme_managed_markdown_keys
if _template_keys != _covered_keys:
    missing_template_coverage = sorted(_template_keys - _covered_keys)
    extra_template_coverage = sorted(_covered_keys - _template_keys)
    raise RuntimeError(
        "Compliance policy template coverage mismatch. "
        f"missing={missing_template_coverage} extra={extra_template_coverage}"
    )


def _resolve_policy_templates_directory() -> Path:
    service_file = Path(__file__).resolve()
    for parent in service_file.parents:
        candidate = parent / "docs" / "compliance" / "policy-templates"
        if candidate.is_dir():
            return candidate
    raise RuntimeError(
        "Unable to locate compliance policy template directory. "
        "Expected 'docs/compliance/policy-templates' in this repository."
    )


_POLICY_TEMPLATES_DIRECTORY = _resolve_policy_templates_directory()


def _load_policy_template_markdown(*, page_key: str) -> str:
    theme_managed_template_markdown = _THEME_MANAGED_POLICY_TEMPLATE_MARKDOWN_BY_PAGE_KEY.get(page_key)
    if theme_managed_template_markdown is not None:
        return theme_managed_template_markdown

    filename = _POLICY_TEMPLATE_FILENAME_BY_PAGE_KEY.get(page_key)
    if not filename:
        raise KeyError(f"Unknown policy template key: {page_key}")

    template_path = _POLICY_TEMPLATES_DIRECTORY / filename
    try:
        markdown = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(
            f"Failed to read compliance policy template markdown for page '{page_key}' "
            f"from '{template_path}'."
        ) from exc

    if not markdown.strip():
        raise RuntimeError(
            f"Compliance policy template markdown is empty for page '{page_key}' at '{template_path}'."
        )
    return markdown


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
        ordered.append(get_policy_template(page_key=page_key))
    return ordered


def get_policy_template(*, page_key: str) -> dict[str, Any]:
    if page_key not in _POLICY_TEMPLATES:
        raise KeyError(f"Unknown policy template key: {page_key}")
    template = deepcopy(_POLICY_TEMPLATES[page_key])
    template["templateMarkdown"] = _load_policy_template_markdown(page_key=page_key)
    return template


def list_policy_page_keys() -> list[str]:
    return list(_PAGE_ORDER)


def get_profile_url_field_for_page_key(*, page_key: str) -> str:
    if page_key not in _PAGE_KEY_TO_PROFILE_URL_FIELD:
        raise KeyError(f"Unknown policy template key: {page_key}")
    return _PAGE_KEY_TO_PROFILE_URL_FIELD[page_key]


def get_policy_page_handle(*, page_key: str) -> str:
    if page_key not in _POLICY_TEMPLATES:
        raise KeyError(f"Unknown policy template key: {page_key}")
    if page_key == "contact_support":
        return "contact"
    return page_key.replace("_", "-")


def markdown_to_shopify_html(markdown: str) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    paragraph_lines: list[str] = []
    list_items: list[str] = []

    def render_inline_markdown(text: str) -> str:
        rendered_parts: list[str] = []
        cursor = 0
        for match in _STRONG_RE.finditer(text):
            start, end = match.span()
            if start > cursor:
                rendered_parts.append(escape(text[cursor:start]))
            strong_text = match.group(1).strip()
            if not strong_text:
                rendered_parts.append(escape(match.group(0)))
            else:
                rendered_parts.append(f"<strong>{escape(strong_text)}</strong>")
            cursor = end
        if cursor < len(text):
            rendered_parts.append(escape(text[cursor:]))
        return "".join(rendered_parts)

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        text_parts: list[str] = []
        for index, part in enumerate(paragraph_lines):
            stripped = part.strip()
            if not stripped:
                continue
            text_parts.append(render_inline_markdown(stripped))
            if part.endswith("  "):
                text_parts.append("<br/>")
                continue
            if index < len(paragraph_lines) - 1:
                text_parts.append(" ")
        text = "".join(text_parts).strip()
        if text:
            output.append(f"<p>{text}</p>")
        paragraph_lines.clear()

    def flush_list() -> None:
        if not list_items:
            return
        output.append("<ul>")
        output.extend(list_items)
        output.append("</ul>")
        list_items.clear()

    for raw_line in lines:
        stripped_line = raw_line.strip()
        if not stripped_line:
            flush_paragraph()
            flush_list()
            continue

        if stripped_line.startswith("# "):
            flush_paragraph()
            flush_list()
            output.append(f"<h1>{render_inline_markdown(stripped_line[2:].strip())}</h1>")
            continue

        if stripped_line.startswith("## "):
            flush_paragraph()
            flush_list()
            output.append(f"<h2>{render_inline_markdown(stripped_line[3:].strip())}</h2>")
            continue

        if stripped_line.startswith("- "):
            flush_paragraph()
            list_items.append(f"<li>{render_inline_markdown(stripped_line[2:].strip())}</li>")
            continue

        flush_list()
        paragraph_lines.append(raw_line)

    flush_paragraph()
    flush_list()

    rendered = "\n".join(output).strip()
    if not rendered:
        raise ValueError("Rendered policy content is empty and cannot be synced.")
    return rendered


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
            raw_value = _DEFAULT_POLICY_PLACEHOLDER_VALUES.get(placeholder)
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


def resolve_theme_contact_page_values(
    *,
    placeholder_values: dict[str, str],
) -> dict[str, str]:
    mapping = {
        "supportEmail": "support_email",
        "supportPhone": "support_phone",
        "supportHours": "support_hours_text",
        "businessAddress": "company_address_text",
    }
    missing_placeholders: list[str] = []
    resolved_values: dict[str, str] = {}

    for response_key, placeholder_key in mapping.items():
        raw_value = placeholder_values.get(placeholder_key)
        if raw_value is None or not raw_value.strip():
            raw_value = _DEFAULT_POLICY_PLACEHOLDER_VALUES.get(placeholder_key)
        if raw_value is None or not raw_value.strip():
            missing_placeholders.append(placeholder_key)
            continue
        resolved_values[response_key] = raw_value.strip()

    if missing_placeholders:
        missing = ", ".join(sorted(missing_placeholders))
        raise ValueError(
            "Missing placeholder values for theme-managed contact page: "
            f"{missing}."
        )

    return resolved_values


def render_theme_contact_page_body_html(
    *,
    placeholder_values: dict[str, str],
) -> str:
    contact_values = resolve_theme_contact_page_values(
        placeholder_values=placeholder_values
    )
    escaped_email = escape(contact_values["supportEmail"])
    escaped_phone = escape(contact_values["supportPhone"])
    escaped_hours = escape(contact_values["supportHours"]).replace("\n", "<br/>")
    escaped_address = escape(contact_values["businessAddress"]).replace("\n", "<br/>")

    return (
        "<h1>Contact and Support</h1>\n"
        "<p>Use the contact form on this page to reach our support team.</p>\n"
        f"<p><strong>Email:</strong> <a href=\"mailto:{escaped_email}\">{escaped_email}</a></p>\n"
        f"<p><strong>Phone:</strong> {escaped_phone}<br/>{escaped_hours}</p>\n"
        f"<p><strong>Business address:</strong><br/>{escaped_address}</p>"
    )


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
