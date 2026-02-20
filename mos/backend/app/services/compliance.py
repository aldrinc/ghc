from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

RULESET_VERSION = "meta_tiktok_compliance_ruleset_v1"
RULESET_EFFECTIVE_DATE = "2026-02-19"

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
            "sourceIds": ["meta.unacceptable_business_practices", "meta.ads_policies_intro"],
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
            {"sectionKey": "data_collected", "title": "What We Collect"},
            {"sectionKey": "data_usage", "title": "How We Use Data"},
            {"sectionKey": "data_sharing", "title": "How We Share Data"},
            {"sectionKey": "privacy_contact", "title": "Privacy Contact"},
            {"sectionKey": "effective_date", "title": "Effective Date"},
        ],
        "placeholders": [
            "legal_business_name",
            "support_email",
            "company_address_text",
            "effective_date",
        ],
        "templateMarkdown": (
            "# Privacy Policy\n\n"
            "**Operator:** {{legal_business_name}}  \n"
            "**Contact:** {{support_email}}  \n"
            "**Address:** {{company_address_text}}  \n"
            "**Effective date:** {{effective_date}}\n\n"
            "## What We Collect\n"
            "Document the data categories you collect through forms, checkout, analytics, and ad pixels.\n\n"
            "## How We Use Data\n"
            "Document each purpose (fulfillment, support, fraud prevention, analytics, marketing, legal).\n\n"
            "## How We Share Data\n"
            "List recipient categories and why each category receives data.\n\n"
            "## Privacy Contact\n"
            "State how users can submit privacy requests and expected response timeframe.\n"
        ),
    },
    "terms_of_service": {
        "pageKey": "terms_of_service",
        "title": "Terms of Service",
        "templateVersion": "v1",
        "description": "Commercial terms that must remain consistent with ad claims, pricing, and offer constraints.",
        "requiredSections": [
            {"sectionKey": "offer_scope", "title": "Offer Scope"},
            {"sectionKey": "pricing_terms", "title": "Pricing and Billing Terms"},
            {"sectionKey": "fulfillment_terms", "title": "Fulfillment and Access Terms"},
            {"sectionKey": "dispute_contact", "title": "Support and Disputes"},
            {"sectionKey": "effective_date", "title": "Effective Date"},
        ],
        "placeholders": ["legal_business_name", "support_email", "effective_date"],
        "templateMarkdown": (
            "# Terms of Service\n\n"
            "These terms govern purchases from {{legal_business_name}}.\n\n"
            "## Offer Scope\n"
            "Define what the customer receives, eligibility rules, and exclusions.\n\n"
            "## Pricing and Billing Terms\n"
            "State currency, taxes/fees handling, discount constraints, and billing timing.\n\n"
            "## Fulfillment and Access Terms\n"
            "State delivery/access method and timing by product type.\n\n"
            "## Support and Disputes\n"
            "State support channel(s) and dispute path. Contact: {{support_email}}.\n\n"
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
            {"sectionKey": "method", "title": "Refund Method"},
            {"sectionKey": "process", "title": "How to Request"},
            {"sectionKey": "exceptions", "title": "Exceptions"},
        ],
        "placeholders": ["legal_business_name", "support_email", "refund_window_days", "effective_date"],
        "templateMarkdown": (
            "# Returns and Refunds Policy\n\n"
            "This policy applies to purchases from {{legal_business_name}}.\n\n"
            "## Eligibility\n"
            "State what qualifies for return/refund and required condition.\n\n"
            "## Return/Refund Window\n"
            "State the exact timeframe (for example: {{refund_window_days}} days from delivery/purchase).\n\n"
            "## Refund Method\n"
            "State whether refunds return to original payment method, store credit, or both.\n\n"
            "## How to Request\n"
            "State exact steps and primary support contact: {{support_email}}.\n\n"
            "## Exceptions\n"
            "State non-refundable categories and legal exceptions.\n\n"
            "**Effective date:** {{effective_date}}\n"
        ),
    },
    "shipping_policy": {
        "pageKey": "shipping_policy",
        "title": "Shipping Policy",
        "templateVersion": "v1",
        "description": "Coverage, shipping charges, fulfillment timelines, and issue handling.",
        "requiredSections": [
            {"sectionKey": "coverage", "title": "Shipping Coverage"},
            {"sectionKey": "costs", "title": "Shipping Costs"},
            {"sectionKey": "timelines", "title": "Processing and Delivery Timelines"},
            {"sectionKey": "tracking", "title": "Tracking and Carrier Notes"},
            {"sectionKey": "issue_handling", "title": "Lost/Late Package Support"},
        ],
        "placeholders": ["support_email", "effective_date", "fulfillment_window"],
        "templateMarkdown": (
            "# Shipping Policy\n\n"
            "## Shipping Coverage\n"
            "List supported regions/countries and unsupported destinations.\n\n"
            "## Shipping Costs\n"
            "Explain the shipping cost model (flat/free/weight/rate table).\n\n"
            "## Processing and Delivery Timelines\n"
            "State processing and estimated delivery range (for example: {{fulfillment_window}}).\n\n"
            "## Tracking and Carrier Notes\n"
            "State tracking availability and where updates are visible.\n\n"
            "## Lost/Late Package Support\n"
            "State escalation path and contact: {{support_email}}.\n\n"
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
            {"sectionKey": "policy_links", "title": "Related Policy Links"},
        ],
        "placeholders": ["support_email", "support_phone", "support_hours_text", "response_time_commitment"],
        "templateMarkdown": (
            "# Contact and Support\n\n"
            "## Contact Channels\n"
            "- Email: {{support_email}}\n"
            "- Phone: {{support_phone}}\n\n"
            "## Support Hours\n"
            "{{support_hours_text}}\n\n"
            "## Expected Response Time\n"
            "{{response_time_commitment}}\n\n"
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
            {"sectionKey": "ownership", "title": "Ownership/Operator"},
            {"sectionKey": "license", "title": "Business License (Where Required)"},
        ],
        "placeholders": [
            "legal_business_name",
            "company_address_text",
            "operating_entity_name",
            "business_license_identifier",
        ],
        "templateMarkdown": (
            "# Company Information\n\n"
            "## Legal Entity\n"
            "{{legal_business_name}}\n\n"
            "## Registered/Business Address\n"
            "{{company_address_text}}\n\n"
            "## Ownership/Operator\n"
            "{{operating_entity_name}}\n\n"
            "## Business License (Where Required)\n"
            "{{business_license_identifier}}\n"
        ),
    },
    "subscription_terms_and_cancellation": {
        "pageKey": "subscription_terms_and_cancellation",
        "title": "Subscription Terms and Cancellation",
        "templateVersion": "v1",
        "description": "Recurring billing disclosures, consent mechanics, renewal behavior, and cancellation process.",
        "requiredSections": [
            {"sectionKey": "plans", "title": "Plans and Billing Interval"},
            {"sectionKey": "renewal", "title": "Renewal Behavior"},
            {"sectionKey": "consent", "title": "Recurring Billing Consent"},
            {"sectionKey": "cancellation", "title": "Cancellation Steps"},
            {"sectionKey": "subscription_refunds", "title": "Subscription Refund Rules"},
        ],
        "placeholders": [
            "legal_business_name",
            "subscription_plan_table",
            "cancellation_steps",
            "support_email",
            "effective_date",
        ],
        "templateMarkdown": (
            "# Subscription Terms and Cancellation\n\n"
            "These terms apply to recurring services provided by {{legal_business_name}}.\n\n"
            "## Plans and Billing Interval\n"
            "{{subscription_plan_table}}\n\n"
            "## Renewal Behavior\n"
            "State whether plans auto-renew and when charges are applied.\n\n"
            "## Recurring Billing Consent\n"
            "State how explicit consent is captured before checkout completion.\n\n"
            "## Cancellation Steps\n"
            "{{cancellation_steps}}\n\n"
            "## Subscription Refund Rules\n"
            "State refund and proration rules for subscription purchases.\n\n"
            "Contact: {{support_email}}  \n"
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
