from __future__ import annotations

import pytest

from app.services.funnel_templates import get_funnel_template
from app.strategy_v2.errors import StrategyV2DecisionError
from app.strategy_v2.template_bridge import (
    apply_strategy_v2_template_patch,
    build_strategy_v2_template_bridge_v1,
    build_strategy_v2_template_patch_operations,
    inspect_strategy_v2_template_payload_validation,
    upgrade_strategy_v2_template_payload_fields,
    validate_strategy_v2_template_payload_fields,
)


def _faq_items() -> list[dict[str, str]]:
    return [
        {"question": "Is this medical advice?", "answer": "No, educational guidance only."},
        {"question": "Is this digital?", "answer": "Yes, instant access after purchase."},
        {"question": "How fast can I start?", "answer": "Most readers can start the same day."},
        {"question": "Does it work with multiple meds?", "answer": "Yes, it is built for medication-aware checks."},
        {"question": "Do I need prior experience?", "answer": "No, the guidance is written for beginners."},
        {"question": "Can I print it?", "answer": "Yes, you can print the worksheets and reference pages."},
        {"question": "Is there a refund policy?", "answer": "Yes, the guarantee terms explain the refund window."},
        {"question": "What support does it include?", "answer": "It includes practical prompts and clear next steps."},
    ]


def _faq_pills() -> list[dict[str, str]]:
    return [{"label": item["question"], "answer": item["answer"]} for item in _faq_items()]


def _sales_markdown() -> str:
    return """
# Headline

## Hero Stack: Safety First
This handbook gives you a practical safety-first system for home remedies.
[Get the handbook now](#offer)

## Problem Recap: Why Guessing Fails
Parents face conflicting advice and no clear reference path.
Uncertainty creates avoidable risk.

## Mechanism + Comparison: Structured Decisions
Use red-flag notes, routines, and trusted sourcing checks.
- Red-flag notes: Pause when contraindications appear
- Practical routines: Follow scenario-based steps
- Source checks: Verify author and listing authenticity
- Safety guardrails: Avoid risky combinations before acting
| Comparison point | Safety-first handbook | Typical marketplace guide |
|---|---|---|
| Author verification | Verifiable credentials and sourcing | Unknown background, weak sourcing |
| Red-flag markers | Built-in interaction and stop-sign flags | Generic overview with no guardrails |
| Organization | Scenario-based quick lookup | Randomized list format |
| Price transparency | Clear all-in offer details | Hidden add-ons and surprises |

## Identity Bridge: Built for Practical Families
You want clear guidance without hype.

## Social Proof: Parents use this daily
Families report faster, safer decisions and less second-guessing.

## CTA #1: Get Immediate Access
[Get the handbook now](#offer)

## What's Inside: Complete System
- Ask Better Questions
- Spot Red Flags Fast
- Check Interactions First
- Feel Safer Starting
Everything is organized for quick lookup.

## Bonus Stack + Value: Included extras
You also get a compact quick-start reference page.

## Guarantee: 30-Day Risk Free Guarantee
Try it for 30 days and request a refund if it is not a fit.
Why this guarantee exists
Because this is designed for practical, repeatable use.
You can start with confidence today.

## CTA #2: Move Forward
[Continue to offer](#offer)

## FAQ: Common Questions
Q: Is this medical advice?
A: No. It is an educational reference with safety guardrails.

Q: Is this digital?
A: Yes, it is delivered digitally for instant access.

Q: How fast can I start?
A: Most readers can start the same day.

Q: Does it work with multiple meds?
A: Yes, it is built for medication-aware checks.

Q: Do I need prior experience?
A: No, the guidance is written for beginners.

Q: Can I print it?
A: Yes, you can print the worksheets and reference pages.

Q: Is there a refund policy?
A: Yes, the guarantee terms explain the refund window.

Q: What support does it include?
A: It includes practical prompts and clear next steps.

## CTA #3 + P.S.: Final step
Use this reference before your next remedy decision.
[Get access now](#offer)
"""


def _valid_pre_sales_reasons() -> list[dict[str, object]]:
    return [
        {
            "number": 1,
            "title": "Conflicting advice is common",
            "body": "A structured checklist helps you evaluate signals quickly. It keeps next steps clear.",
            "image": {"alt": "Reader reviewing a medication-aware herbal checklist"},
        },
        {
            "number": 2,
            "title": "Red flags are easy to miss",
            "body": "Simple stop signs reduce rushed decisions. They make follow-up questions more precise.",
            "image": {"alt": "Highlighted stop-sign notes on a herbal screening worksheet"},
        },
        {
            "number": 3,
            "title": "Prep changes the appointment",
            "body": "Better notes shorten the back-and-forth. Families leave with clearer answers.",
            "image": {"alt": "Parent organizing questions before a practitioner visit"},
        },
        {
            "number": 4,
            "title": "One reference beats scattered tabs",
            "body": "A single workflow keeps safety checks in one place. It reduces second-guessing mid-decision.",
            "image": {"alt": "Open handbook beside a neat stack of notes"},
        },
        {
            "number": 5,
            "title": "Confidence comes from clear boundaries",
            "body": "Knowing when to pause lowers avoidable risk. That makes the next action easier to choose.",
            "image": {"alt": "Checklist with clear do-now and pause-now sections"},
        },
    ]


def _valid_sales_payload() -> dict[str, object]:
    return {
        "hero": {
            "purchase_title": "Calm, practical safety guidance for home remedies",
            "primary_cta_label": "Get the handbook now",
            "primary_cta_subbullets": ["Quick checklists", "Simple routines"],
        },
        "problem": {
            "title": "Why guesswork creates avoidable risk",
            "paragraphs": ["Advice is scattered and inconsistent.", "That uncertainty drives avoidable mistakes."],
            "emphasis_line": "A repeatable system reduces confusion fast.",
        },
            "mechanism": {
                "title": "How the system works",
                "paragraphs": ["Use a structured decision process."],
                "bullets": [
                    {"title": "Red-flag markers", "body": "Spot contraindications before you continue."},
                    {"title": "Scenario routines", "body": "Follow practical routines by common use-case."},
                    {"title": "Source checks", "body": "Verify credibility before using any listing."},
                    {"title": "Safety boundaries", "body": "Know when to pause, reduce, or avoid."},
                    {"title": "Clinician prompts", "body": "Use specific prompts to get direct, useful answers."},
                ],
            "callout": {
                "left_title": "Typical marketplace guides",
                "left_body": "Hard to verify, no clear safety markers.",
                "right_title": "Safety-first handbook",
                "right_body": "Verifiable, structured, and practical.",
            },
            "comparison": {
                "badge": "US vs THEM",
                "title": "Safety-first handbook vs marketplace books",
                "swipe_hint": "Swipe right to see comparison ->",
                "columns": {"pup": "SAFETY-FIRST HANDBOOK", "disposable": "MARKETPLACE BOOKS"},
                "rows": [
                    {
                        "label": "Author verification",
                        "pup": "Verified credentials and sourcing",
                        "disposable": "Unknown or unverifiable background",
                    },
                    {
                        "label": "Red-flag markers",
                        "pup": "Built-in contraindication markers",
                        "disposable": "No practical warning system",
                    },
                ],
            },
        },
        "social_proof": {
            "badge": "SOCIAL PROOF",
            "title": "Families use this daily",
            "rating_label": "Verified customer feedback",
            "summary": "Parents report calmer and safer decisions.",
        },
        "whats_inside": {
            "benefits": [
                "Spot Risks Faster",
                "Follow Clear Steps",
                "Ask Better Questions",
                "Feel More Confident",
            ],
            "offer_helper_text": "Instant digital access.",
        },
        "bonus": {
            "free_gifts_title": "Included quick-start page",
            "free_gifts_body": "A concise one-page reference.",
        },
        "guarantee": {
            "title": "30-Day Risk Free Guarantee",
            "paragraphs": ["If it is not a fit, request a refund."],
            "why_title": "Why this guarantee exists",
            "why_body": "It is built for practical repeatable use.",
            "closing_line": "Start confidently today.",
        },
        "faq": {
            "title": "Common questions",
            "items": _faq_items(),
        },
        "faq_pills": _faq_pills(),
        "marquee_items": [
            "Medication-aware",
            "Safety-first",
            "Clinician-ready notes",
            "Practical checklists",
        ],
        "urgency_message": "Selling out faster than expected. Secure your copy before this batch closes.",
        "cta_close": "Get access now",
    }


def test_inspect_template_payload_validation_pass_returns_normalized_fields() -> None:
    report = inspect_strategy_v2_template_payload_validation(
        template_id="sales-pdp",
        payload_fields=_valid_sales_payload(),
    )

    assert report["valid"] is True
    assert report["error_count"] == 0
    assert report["errors"] == []
    assert isinstance(report["validated_fields"], dict)
    assert report["validated_fields"]["hero"]["purchase_title"].startswith("Calm, practical safety guidance")


def test_inspect_template_payload_validation_reports_detailed_errors() -> None:
    invalid_payload = _valid_sales_payload()
    hero = dict(invalid_payload["hero"])
    hero["headline"] = "Wrong key"
    hero.pop("purchase_title", None)
    invalid_payload["hero"] = hero
    invalid_payload["problem_recap"] = {"headline": "Wrong top-level key"}

    report = inspect_strategy_v2_template_payload_validation(
        template_id="sales-pdp",
        payload_fields=invalid_payload,
        max_items=80,
    )

    assert report["valid"] is False
    assert report["error_count"] >= 3
    assert report["error_types"].get("missing", 0) >= 1
    assert report["error_types"].get("extra_forbidden", 0) >= 1
    assert isinstance(report["errors"], list)
    locations = [row["loc"] for row in report["errors"] if isinstance(row, dict)]
    assert "hero.purchase_title" in locations
    assert "hero.headline" in locations
    assert "problem_recap" in locations


def test_upgrade_sales_payload_normalizes_common_legacy_keys() -> None:
    legacy_payload = {
        "hero": {
            "headline": "Legacy Hero Headline",
            "primary_cta_label": "Get Access",
            "primary_cta_subbullets": ["Fast setup", "No subscription"],
            "primary_cta_url": "https://example.com/order",
        },
        "problem": {
            "heading": "Legacy Problem Heading",
            "body": "Legacy problem paragraph content.",
            "problem_image_alt": "legacy alt",
        },
        "mechanism": {
            "heading": "Legacy Mechanism Heading",
            "intro": "Legacy mechanism intro paragraph.",
            "bullets": [
                {"feature": "Point 1", "body": "Body 1"},
                {"feature": "Point 2", "body": "Body 2"},
                {"feature": "Point 3", "body": "Body 3"},
                {"feature": "Point 4", "body": "Body 4"},
                {"feature": "Point 5", "body": "Body 5"},
            ],
            "callout": {
                "leftTitle": "Old way",
                "leftBody": "Left body",
                "rightTitle": "New way",
                "rightBody": "Right body",
            },
            "comparison": {
                "badge": "Legacy Badge",
                "title": "Legacy Comparison",
                "swipeHint": "Swipe",
                "columns": {"left": "Our way", "right": "Other way"},
                "rows": [
                    {"feature": "Speed", "left": "Fast", "right": "Slow"},
                    {"feature": "Clarity", "left": "Clear", "right": "Confusing"},
                ],
            },
        },
        "social_proof": {
            "heading": "Legacy Social Heading",
            "testimonials": [{"quote": "Works great."}],
        },
        "whats_inside": {
            "heading": "Inside",
            "intro": "Everything you need.",
            "benefits": [
                "Start Faster",
                "Stay Consistent",
                "Ask Better Questions",
                "Act With Confidence",
            ],
        },
        "bonus": {
            "heading": "Legacy Bonus Heading",
            "items": [{"title": "Bonus A"}, {"title": "Bonus B"}],
        },
        "guarantee": {
            "heading": "45-Day Risk Free Guarantee",
            "body": "Try it and request a refund if needed.",
        },
        "faq": {
            "heading": "Legacy FAQ Heading",
            "items": _faq_items(),
        },
        "cta_close": {"cta_label": "Start now"},
        "problem_recap": {"heading": "Should be removed"},
        "schema": "legacy",
        "template_id": "sales-pdp",
    }

    upgraded = upgrade_strategy_v2_template_payload_fields(
        template_id="sales-pdp",
        payload_fields=legacy_payload,
    )
    validated = validate_strategy_v2_template_payload_fields(
        template_id="sales-pdp",
        payload_fields=upgraded,
    )

    assert validated["hero"]["purchase_title"] == "Legacy Hero Headline"
    assert validated["problem"]["title"] == "Legacy Problem Heading"
    assert validated["mechanism"]["comparison"]["columns"]["pup"] == "Our way"
    assert validated["faq_pills"][0]["label"] == "Is this medical advice?"
    assert "schema" not in upgraded
    assert "template_id" not in upgraded


def test_upgrade_sales_payload_normalizes_problem_recap_and_comparison_variants() -> None:
    legacy_payload = {
        "hero": {
            "headline": "Legacy hero headline",
            "primary_cta_label": "Get access",
            "trust_badges": ["Instant access", "No subscription"],
        },
        "problem_recap": {
            "headline": "Three avoidable safety errors",
            "errors": [
                {"number": 1, "title": "No interaction check", "body": "Parents are left to guess."},
                {"number": 2, "title": "No child flags", "body": "Child-specific contraindications are missing."},
            ],
        },
        "pain_bullets": [
            "No contraindication checklist",
            "No interaction screening workflow",
        ],
        "mechanism": {
            "headline": "Interaction triage workflow",
            "subheadline": "A practical process before any purchase decision.",
            "bullets": [
                {"feature": "Step 1", "body": "Inventory medications."},
                {"feature": "Step 2", "body": "Run contraindication flags."},
                {"feature": "Step 3", "body": "Cross-check sources."},
                {"feature": "Step 4", "body": "Prepare clinician questions."},
                {"feature": "Step 5", "body": "Escalate red flags immediately."},
            ],
            "callout": {
                "left_title": "Typical guide",
                "left_body": "Generic tips only",
                "right_title": "Workflow approach",
                "right_body": "Actionable checks",
            },
            "comparison": {
                "badge": "Comparison",
                "title": "Guide vs workflow",
                "swipe_hint": "Swipe",
                "columns": ["Typical Guide", "Paid Course", "Workflow Handbook"],
                "rows": [
                    {"feature": "Interaction screening", "values": ["No", "Partial", "Yes"]},
                    {"left": "Generic caution", "right": "Specific contraindication flags"},
                ],
            },
        },
        "social_proof": {
            "headline": "What readers report",
            "testimonials": [{"quote": "Clear and practical."}],
            "proof_note": "Specific questions improve clinician feedback.",
        },
        "whats_inside": {
            "headline": "Everything included",
            "benefits": [
                {"question": "Ask Better Questions", "answer": "Checklist and scripts."},
                {"title": "Spot Red Flags Fast", "body": "A printable safety screen."},
                {"title": "Check Interactions First", "body": "Medication cross-check prompts."},
                {"title": "Feel More Confident", "body": "Clearer next steps."},
            ],
        },
        "bonus": {
            "headline": "Bonus stack",
            "items": [{"title": "Question script"}],
            "total_value_statement": "Total bonus value included.",
        },
        "guarantee": {
            "headline": "60-Day Risk Free Guarantee",
            "body": "Request a refund within 60 days.",
            "badge_text": "Money-back",
        },
        "faq": {
            "headline": "FAQ",
            "items": _faq_items(),
        },
        "cta_close": {"cta_label": "Get access now"},
        "marquee_items": [
            "Interaction-first",
            "Medication-aware",
            "Practical checklists",
            "Clinician-ready",
        ],
        "urgency_message": "Selling out faster than expected.",
    }

    upgraded = upgrade_strategy_v2_template_payload_fields(
        template_id="sales-pdp",
        payload_fields=legacy_payload,
    )
    validated = validate_strategy_v2_template_payload_fields(
        template_id="sales-pdp",
        payload_fields=upgraded,
    )

    assert validated["problem"]["title"] == "Three avoidable safety errors"
    assert validated["problem"]["paragraphs"][0].startswith("Error 1")
    assert validated["mechanism"]["paragraphs"][0] == "A practical process before any purchase decision."
    assert validated["mechanism"]["comparison"]["rows"][0]["label"] == "Interaction screening"
    assert validated["mechanism"]["comparison"]["rows"][0]["pup"] == "Yes"
    assert validated["mechanism"]["comparison"]["rows"][0]["disposable"] == "No"
    assert validated["mechanism"]["comparison"]["rows"][1]["label"] == "Generic caution"
    assert validated["mechanism"]["comparison"]["rows"][1]["pup"] == "Specific contraindication flags"
    assert validated["hero"]["primary_cta_subbullets"] == ["Ask Better Questions", "Spot Red Flags Fast"]
    assert "pain_bullets" not in upgraded
    assert "proof_note" not in upgraded["social_proof"]
    assert "headline" not in upgraded["faq"]


def test_upgrade_sales_payload_derives_faq_items_and_cta_close_from_legacy_keys() -> None:
    legacy_payload = {
        "hero": {
            "headline": "Legacy hero",
            "primary_cta_label": "Get access now",
            "primary_cta_subbullets": ["Fast setup", "No subscription"],
        },
        "problem": {
            "headline": "Legacy problem",
            "body": "Legacy paragraph body.",
        },
        "mechanism": {
            "headline": "Legacy mechanism",
            "subheadline": "Mechanism summary paragraph.",
            "bullets": [
                {"title": "Step 1", "body": "Do this."},
                {"title": "Step 2", "body": "Do that."},
                {"title": "Step 3", "body": "Check signals."},
                {"title": "Step 4", "body": "Escalate when needed."},
                {"title": "Step 5", "body": "Use clinician prompts."},
            ],
            "callout": {
                "left_title": "Before",
                "left_body": "Guessing",
                "right_title": "After",
                "right_body": "Structured checks",
            },
            "comparison": {
                "badge": "Comparison",
                "title": "Before vs after",
                "swipe_hint": "Swipe",
                "columns": {"left": "Typical Guide", "right": "Workflow"},
                "rows": [{"feature": "Interaction checks", "left": "No", "right": "Yes"}],
            },
        },
        "social_proof": {"headline": "Social proof", "testimonials": [{"quote": "Works."}]},
        "whats_inside": {
            "benefits": [
                "Start Faster",
                "Stay On Track",
                "Ask Better Questions",
                "Feel More Certain",
            ],
            "headline": "Inside",
        },
        "bonus": {"headline": "Bonus", "free_gifts_body": "Included extras."},
        "guarantee": {"headline": "30-Day Risk Free Guarantee", "body": "Refund within 60 days."},
        "faq_pills": _faq_pills(),
        "marquee_items": ["Fast", "Practical", "Structured", "Safety-first"],
        "urgency_message": "Selling out quickly.",
        "cta_primary": {"label": "Start now"},
    }

    upgraded = upgrade_strategy_v2_template_payload_fields(
        template_id="sales-pdp",
        payload_fields=legacy_payload,
    )
    validated = validate_strategy_v2_template_payload_fields(
        template_id="sales-pdp",
        payload_fields=upgraded,
    )

    assert validated["faq"]["items"][0]["question"] == "Is this medical advice?"
    assert validated["faq"]["items"][0]["answer"] == "No, educational guidance only."
    assert validated["faq_pills"][1]["label"] == "Is this digital?"
    assert validated["cta_close"] == "Start now"


def test_upgrade_sales_payload_handles_two_column_rows_and_strips_known_drift_keys() -> None:
    legacy_payload = {
        "hero": {
            "headline": "Interaction triage workflow",
            "primary_cta_label": "Get access",
            "primary_cta_subbullets": ["Fast setup", "No subscription"],
            "primary_cta_url": "https://example.com/order",
        },
        "problem": {
            "headline": "Why this matters",
            "body": "Most clinicians have no structured herb-drug interaction workflow.",
        },
        "mechanism": {
            "headline": "How this works",
            "subheadline": "Run a clear screen before trying anything.",
            "bullets": [
                {"title": "Step 1", "body": "Build your list."},
                {"title": "Step 2", "body": "Check flags."},
                {"title": "Step 3", "body": "Cross-check sources."},
                {"title": "Step 4", "body": "Prepare questions."},
                {"title": "Step 5", "body": "Run final review."},
            ],
            "callout": {
                "left_title": "Typical guide",
                "left_body": "Generic and vague",
                "right_title": "Workflow",
                "right_body": "Specific and actionable",
            },
            "comparison": {
                "badge": "Comparison",
                "title": "Guide vs workflow",
                "swipe_hint": "Swipe",
                "columns": ["Standard Herbal Guides", "Interaction Triage Workflow"],
                "rows": [
                    ["Lists herbs and benefits", "Screens your specific med combination"],
                    ["No drug interaction guidance", "Contraindication flags built in"],
                ],
            },
        },
        "social_proof": {
            "headline": "What readers say",
            "testimonials": [{"quote": "This gave me a clear process."}],
            "proof_bar_items": ["47 guides reviewed"],
        },
        "whats_inside": {
            "headline": "Everything included",
            "benefits": [
                "Start Faster",
                "Stay On Track",
                "Ask Better Questions",
                "Feel More Certain",
            ],
            "main_product_title": "Legacy title",
            "main_product_body": "Legacy body",
        },
        "bonus": {
            "headline": "Bonus stack",
            "free_gifts_label": "Included free",
            "free_gifts_body": "Four support tools included.",
        },
        "guarantee": {
            "headline": "60-Day Risk Free Guarantee",
            "body": "Request a refund if not a fit.",
            "cta_label": "Start now",
            "cta_url": "https://example.com/order",
        },
        "faq": {"headline": "FAQ", "items": _faq_items()},
        "faq_pills": _faq_pills(),
        "marquee_items": ["Safety-first", "Practical", "Medication-aware", "Actionable"],
        "urgency_message": "Selling out faster than expected.",
        "cta_close": {"cta_label": "Get access now"},
    }

    upgraded = upgrade_strategy_v2_template_payload_fields(
        template_id="sales-pdp",
        payload_fields=legacy_payload,
    )
    validated = validate_strategy_v2_template_payload_fields(
        template_id="sales-pdp",
        payload_fields=upgraded,
    )

    assert validated["mechanism"]["comparison"]["rows"][0]["label"] == "Lists herbs and benefits"
    assert validated["mechanism"]["comparison"]["rows"][0]["disposable"] == "Lists herbs and benefits"
    assert validated["mechanism"]["comparison"]["rows"][0]["pup"] == "Screens your specific med combination"
    assert "proof_bar_items" not in upgraded["social_proof"]
    assert "main_product_title" not in upgraded["whats_inside"]
    assert "main_product_body" not in upgraded["whats_inside"]
    assert "free_gifts_label" not in upgraded["bonus"]
    assert "cta_label" not in upgraded["guarantee"]
    assert "cta_url" not in upgraded["guarantee"]


def test_upgrade_sales_payload_handles_feature_us_them_comparison_rows() -> None:
    legacy_payload = {
        "hero": {
            "headline": "Interaction triage workflow",
            "primary_cta_label": "Get access",
            "primary_cta_subbullets": ["Fast setup", "No subscription"],
        },
        "problem": {
            "headline": "Why this matters",
            "body": "Most shoppers are left to guess at herb-drug interactions.",
        },
        "mechanism": {
            "headline": "How this works",
            "subheadline": "Use a structured screen before trying anything.",
            "bullets": [
                {"title": "Step 1", "body": "List the herb and medication."},
                {"title": "Step 2", "body": "Check red flags."},
                {"title": "Step 3", "body": "Cross-check sources."},
                {"title": "Step 4", "body": "Prepare clinician questions."},
                {"title": "Step 5", "body": "Review final contraindications."},
            ],
            "callout": {
                "left_title": "Typical guide",
                "left_body": "Generic and vague",
                "right_title": "Workflow",
                "right_body": "Specific and actionable",
            },
            "comparison": {
                "badge": "US vs THEM",
                "title": "Interaction Triage Workflow vs. Random Google Searches",
                "swipe_hint": "Swipe to compare",
                "columns": ["Honest Herbalist Handbook", "Typical Herbal Guides"],
                "rows": [
                    {
                        "feature": "Herb-drug interaction screening",
                        "us": "Built-in triage checklist for every herb",
                        "them": "Rarely mentioned or buried in fine print",
                    }
                ],
            },
        },
        "social_proof": {
            "headline": "What readers say",
            "testimonials": [{"quote": "This gave me a clear process."}],
        },
        "whats_inside": {
            "benefits": [
                "Start Faster",
                "Stay On Track",
                "Ask Better Questions",
                "Feel More Certain",
            ],
            "headline": "Everything included",
        },
        "bonus": {
            "headline": "Bonus stack",
            "free_gifts_body": "Four support tools included.",
        },
        "guarantee": {
            "headline": "30-Day Risk Free Guarantee",
            "body": "Request a refund if not a fit.",
        },
        "faq": {"headline": "FAQ", "items": _faq_items()},
        "faq_pills": _faq_pills(),
        "marquee_items": ["Safety-first", "Practical", "Medication-aware", "Actionable"],
        "urgency_message": "Selling out faster than expected.",
        "cta_close": {"cta_label": "Get access now"},
    }

    upgraded = upgrade_strategy_v2_template_payload_fields(
        template_id="sales-pdp",
        payload_fields=legacy_payload,
    )
    validated = validate_strategy_v2_template_payload_fields(
        template_id="sales-pdp",
        payload_fields=upgraded,
    )

    row = validated["mechanism"]["comparison"]["rows"][0]
    assert row["label"] == "Herb-drug interaction screening"
    assert row["pup"] == "Built-in triage checklist for every herb"
    assert row["disposable"] == "Rarely mentioned or buried in fine print"


def test_upgrade_sales_payload_clamps_overlong_mechanism_bullet_body() -> None:
    long_body = "A" * 400
    legacy_payload = {
        "hero": {
            "headline": "Legacy hero",
            "primary_cta_label": "Get access now",
            "primary_cta_subbullets": ["Fast setup", "No subscription"],
        },
        "problem": {"headline": "Legacy problem", "body": "Legacy paragraph body."},
        "mechanism": {
            "headline": "Legacy mechanism",
            "subheadline": "Mechanism summary paragraph.",
            "bullets": [
                {"title": "Step 1", "body": long_body},
                {"title": "Step 2", "body": "Do that."},
                {"title": "Step 3", "body": "Check signals."},
                {"title": "Step 4", "body": "Escalate when needed."},
                {"title": "Step 5", "body": "Use clinician prompts."},
            ],
            "callout": {
                "left_title": "Before",
                "left_body": "Guessing",
                "right_title": "After",
                "right_body": "Structured checks",
            },
            "comparison": {
                "badge": "Comparison",
                "title": "Before vs after",
                "swipe_hint": "Swipe",
                "columns": {"left": "Typical Guide", "right": "Workflow"},
                "rows": [{"feature": "Interaction checks", "left": "No", "right": "Yes"}],
            },
        },
        "social_proof": {"headline": "Social proof", "testimonials": [{"quote": "Works."}]},
        "whats_inside": {
            "benefits": [
                "Start Faster",
                "Stay On Track",
                "Ask Better Questions",
                "Feel More Certain",
            ],
            "headline": "Inside",
        },
        "bonus": {"headline": "Bonus", "free_gifts_body": "Included extras."},
        "guarantee": {"headline": "30-Day Risk Free Guarantee", "body": "Refund within 60 days."},
        "faq_pills": _faq_pills(),
        "marquee_items": ["Fast", "Practical", "Structured", "Safety-first"],
        "urgency_message": "Selling out quickly.",
        "cta_primary": {"label": "Start now"},
    }

    upgraded = upgrade_strategy_v2_template_payload_fields(
        template_id="sales-pdp",
        payload_fields=legacy_payload,
    )
    validated = validate_strategy_v2_template_payload_fields(
        template_id="sales-pdp",
        payload_fields=upgraded,
    )

    assert len(validated["mechanism"]["bullets"][0]["body"]) <= 160
    assert validated["mechanism"]["bullets"][0]["body"] == "A" * 160


def test_upgrade_presales_payload_clamps_legacy_fields_to_contract_caps() -> None:
    reasons = _valid_pre_sales_reasons()
    reasons[0] = {
        "number": 1,
        "title": "Why long-form safety explanations need to be constrained for template payloads",
        "body": (
            "Sentence one explains the issue in detail. "
            "Sentence two adds practical context. "
            "Sentence three reinforces the action. "
            "Sentence four should be trimmed."
        ),
        "image": {"alt": "Checklist visual"},
    }
    legacy_payload = {
        "hero": {
            "title": "Safety-first herbal screening process " * 4,
            "subtitle": (
                "Parents keep hearing non-answers when they ask about interactions. "
                "A repeatable workflow helps them prepare better questions. "
                "This extra sentence should be clipped."
            ),
            "badges": [
                {
                    "label": "Safety-first",
                    "value": "Interaction triage workflow and practical guardrails",
                    "icon": {"alt": "Shield icon", "prompt": "simple shield icon"},
                }
            ],
        },
        "reasons": reasons,
        "marquee": [
            "Interaction Triage Workflow For Parents",
            "Contraindication Flag Checker With Extra Words",
        ],
        "pitch": {
            "title": "Use this practical system to make safer herbal decisions before your next appointment and avoid guesswork",
            "bullets": [
                "A" * 120,
                "B" * 120,
                "Structured preparation before decisions",
                "Better pharmacist conversations",
                "This fifth bullet should be dropped",
            ],
            "cta_label": "Continue to offer",
            "image": {"alt": "Pitch visual"},
        },
        "review_wall": {"title": "Trusted by practical families", "button_label": "Open full reviews"},
        "floating_cta": {"label": "Continue to offer"},
    }

    upgraded = upgrade_strategy_v2_template_payload_fields(
        template_id="pre-sales-listicle",
        payload_fields=legacy_payload,
    )
    validated = validate_strategy_v2_template_payload_fields(
        template_id="pre-sales-listicle",
        payload_fields=upgraded,
    )

    assert len(validated["hero"]["title"]) <= 90
    assert len(validated["hero"]["subtitle"]) <= 140
    assert validated["hero"]["subtitle"].count(".") <= 2
    assert len(validated["reasons"][0]["title"]) <= 72
    assert validated["reasons"][0]["body"].count(".") <= 3
    assert all(len(item) <= 24 for item in validated["marquee"])
    assert len(validated["pitch"]["title"]) <= 78
    assert len(validated["pitch"]["bullets"]) == 4


def test_template_bridge_builds_and_patches_sales_template() -> None:
    bridge = build_strategy_v2_template_bridge_v1(
        angle_run_id="wf-1:angle-1",
        template_id="sales-pdp",
        headline="The One Herb Mistake Parents Make",
        promise_contract={
            "loop_question": "What mistake creates risk?",
            "specific_promise": "Safer decisions with clear routines.",
            "delivery_test": "Provide clear stop-sign criteria.",
            "minimum_delivery": "Deliver by section 1.",
        },
        sales_page_markdown=_sales_markdown(),
        presell_markdown="## Hook/Lead\nExample",
    )

    assert bridge["template_id"] == "sales-pdp"
    assert bridge["template_patch"]
    assert bridge["copy_pack"]["cta"]["primary"] == "Get the handbook now"

    template = get_funnel_template("sales-pdp")
    assert template is not None
    patched = apply_strategy_v2_template_patch(
        base_puck_data=template.puck_data,
        operations=bridge["template_patch"],
        template_id="sales-pdp",
    )
    assert patched != template.puck_data


def test_template_bridge_rejects_unsupported_template() -> None:
    with pytest.raises(StrategyV2DecisionError, match="Unsupported template_id"):
        build_strategy_v2_template_bridge_v1(
            angle_run_id="wf-1:angle-1",
            template_id="pre-sales-listicle",
            headline="Headline",
            promise_contract={
                "loop_question": "Q",
                "specific_promise": "P",
                "delivery_test": "D",
                "minimum_delivery": "M",
            },
            sales_page_markdown=_sales_markdown(),
            presell_markdown="## Hook/Lead\nExample",
        )


def test_template_bridge_requires_faq_q_a_pairs() -> None:
    markdown = _sales_markdown().replace("Q:", "Question:").replace("?", ".")
    with pytest.raises(StrategyV2DecisionError, match="could not parse FAQ"):
        build_strategy_v2_template_bridge_v1(
            angle_run_id="wf-1:angle-1",
            template_id="sales-pdp",
            headline="Headline",
            promise_contract={
                "loop_question": "Q",
                "specific_promise": "P",
                "delivery_test": "D",
                "minimum_delivery": "M",
            },
            sales_page_markdown=markdown,
            presell_markdown="## Hook/Lead\nExample",
        )


def test_template_payload_patch_operations_apply_to_sales_template() -> None:
    fields = validate_strategy_v2_template_payload_fields(
        template_id="sales-pdp",
        payload_fields=_valid_sales_payload(),
    )
    operations = build_strategy_v2_template_patch_operations(template_id="sales-pdp", payload_fields=fields)
    template = get_funnel_template("sales-pdp")
    assert template is not None
    patched = apply_strategy_v2_template_patch(
        base_puck_data=template.puck_data,
        operations=operations,
        template_id="sales-pdp",
    )
    assert patched != template.puck_data
    sales_page = patched["content"][0]
    children = sales_page["props"]["content"]
    hero = next(item for item in children if item.get("type") == "SalesPdpHero")
    marquee = next(item for item in children if item.get("type") == "SalesPdpMarquee")
    assert hero["props"]["config"]["purchase"]["faqPills"][0]["label"] == "Is this medical advice?"
    assert hero["props"]["config"]["purchase"]["cta"]["urgency"]["message"] == (
        "Selling out faster than expected. Secure your copy before this batch closes."
    )
    assert marquee["props"]["config"]["items"][0] == "Medication-aware"


def test_template_payload_patch_operations_apply_to_presales_template() -> None:
    reasons = _valid_pre_sales_reasons()
    fields = validate_strategy_v2_template_payload_fields(
        template_id="pre-sales-listicle",
        payload_fields={
            "hero": {
                "title": "What if your remedy process felt clear and safe?",
                "subtitle": "A practical checklist before your next decision.",
                "badges": [
                    {
                        "label": "Safety-first guidance",
                        "icon": {"alt": "Safety shield icon", "prompt": "icon of medication safety shield"},
                    },
                    {
                        "label": "Practical routines",
                        "icon": {"alt": "Checklist icon", "prompt": "icon of practical checklist"},
                    },
                    {
                        "label": "Evidence-aware decisions",
                        "icon": {"alt": "Evidence icon", "prompt": "icon of evidence-backed decisions"},
                    },
                ],
            },
            "reasons": reasons,
            "marquee": ["Safety first", "Clear decisions"],
            "pitch": {
                "title": "Use the handbook for faster, safer choices",
                "bullets": [
                    "Simple steps",
                    "Clear boundaries",
                    "Faster prep",
                    "Better questions",
                ],
                "cta_label": "Continue to offer",
                "image": {"alt": "Printed handbook with quick-scan pages"},
            },
            "review_wall": {
                "title": "Trusted by practical families",
                "button_label": "Open full reviews",
            },
            "floating_cta": {"label": "Continue to offer"},
        },
    )
    operations = build_strategy_v2_template_patch_operations(
        template_id="pre-sales-listicle",
        payload_fields=fields,
    )
    template = get_funnel_template("pre-sales-listicle")
    assert template is not None
    patched = apply_strategy_v2_template_patch(
        base_puck_data=template.puck_data,
        operations=operations,
        template_id="pre-sales-listicle",
    )
    assert patched != template.puck_data
    pre_sales_page = patched["content"][0]
    children = pre_sales_page["props"]["content"]
    hero = next(item for item in children if item.get("type") == "PreSalesHero")
    reasons = next(item for item in children if item.get("type") == "PreSalesReasons")
    pitch = next(item for item in children if item.get("type") == "PreSalesPitch")
    review_wall = next(item for item in children if item.get("type") == "PreSalesReviewWall")
    floating_cta = next(item for item in children if item.get("type") == "PreSalesFloatingCta")
    assert hero["props"]["config"]["badges"][0]["value"]
    assert hero["props"]["config"]["badges"][0]["label"] == "5-Star Reviews"
    assert hero["props"]["config"]["badges"][0]["prompt"] == "icon of 5 star reviews"
    assert hero["props"]["config"]["badges"][1]["value"] == "24/7"
    assert hero["props"]["config"]["badges"][1]["label"] == "Customer Support"
    assert hero["props"]["config"]["badges"][2]["label"] == "Risk Free Trial"
    assert reasons["props"]["config"][0]["image"]["alt"] == "Reader reviewing a medication-aware herbal checklist"
    assert pitch["props"]["config"]["image"]["alt"] == "Printed handbook with quick-scan pages"
    assert pitch["props"]["config"]["cta"]["label"] == "Learn more"
    assert review_wall["props"]["config"]["title"].startswith("Over ")
    assert review_wall["props"]["config"]["title"].endswith("5 Star Reviews")
    assert review_wall["props"]["config"]["buttonLabel"] == "Open full reviews"
    assert floating_cta["props"]["config"]["label"] == "Learn more"
    assert not any(item.get("type") == "PreSalesReviews" for item in children)


def test_validate_presales_payload_normalizes_social_proof_badges() -> None:
    fields = validate_strategy_v2_template_payload_fields(
        template_id="pre-sales-listicle",
        payload_fields={
            "hero": {
                "title": "What if your remedy process felt clear and safe?",
                "subtitle": "A practical checklist before your next decision.",
                "badges": [
                    {
                        "label": "Original badge",
                        "icon": {"alt": "Original icon", "prompt": "icon of something else"},
                    }
                ],
            },
            "reasons": _valid_pre_sales_reasons(),
            "marquee": ["Safety first"],
            "pitch": {
                "title": "Use the handbook for faster, safer choices",
                "bullets": ["Simple steps", "Clear boundaries", "Faster prep", "Better questions"],
                "cta_label": "Learn more",
                "image": {"alt": "Pitch visual"},
            },
            "review_wall": {
                "title": "Trusted by practical families",
                "button_label": "Open full reviews",
            },
            "floating_cta": {"label": "Learn more"},
        },
    )

    assert len(fields["hero"]["badges"]) == 3
    assert fields["hero"]["badges"][0]["label"] == "5-Star Reviews"
    assert fields["hero"]["badges"][0]["value"]
    assert fields["hero"]["badges"][1]["value"] == "24/7"
    assert fields["hero"]["badges"][1]["label"] == "Customer Support"
    assert fields["hero"]["badges"][2]["label"] == "Risk Free Trial"
    assert fields["review_wall"]["title"].startswith("Over ")
    assert fields["review_wall"]["title"].endswith("5 Star Reviews")


def test_presales_template_payload_requires_at_least_five_reasons() -> None:
    payload = {
        "hero": {
            "title": "What if your remedy process felt clear and safe?",
            "subtitle": "A practical checklist before your next decision.",
            "badges": [
                {
                    "label": "Original badge",
                    "icon": {"alt": "Original icon", "prompt": "icon of something else"},
                }
            ],
        },
        "reasons": _valid_pre_sales_reasons()[:4],
        "marquee": ["Safety first"],
        "pitch": {
            "title": "Use the handbook for faster, safer choices",
            "bullets": ["Simple steps", "Clear boundaries", "Faster prep", "Better questions"],
            "cta_label": "Learn more",
            "image": {"alt": "Pitch visual"},
        },
        "review_wall": {
            "title": "Trusted by practical families",
            "button_label": "Open full reviews",
        },
        "floating_cta": {"label": "Learn more"},
    }

    with pytest.raises(StrategyV2DecisionError, match="reasons"):
        validate_strategy_v2_template_payload_fields(template_id="pre-sales-listicle", payload_fields=payload)


def test_sales_template_payload_requires_exactly_two_cta_subbullets() -> None:
    payload = _valid_sales_payload()
    hero = dict(payload["hero"])
    hero["primary_cta_subbullets"] = ["One", "Two", "Three"]
    payload["hero"] = hero
    with pytest.raises(StrategyV2DecisionError, match="TEMPLATE_PAYLOAD_VALIDATION"):
        validate_strategy_v2_template_payload_fields(template_id="sales-pdp", payload_fields=payload)


def test_sales_template_payload_rejects_hardcoded_cta_price() -> None:
    payload = _valid_sales_payload()
    hero = dict(payload["hero"])
    hero["primary_cta_label"] = "Get the handbook now - $49"
    payload["hero"] = hero

    with pytest.raises(StrategyV2DecisionError, match="hero.primary_cta_label"):
        validate_strategy_v2_template_payload_fields(template_id="sales-pdp", payload_fields=payload)


def test_sales_template_payload_requires_risk_free_guarantee_language() -> None:
    payload = _valid_sales_payload()
    guarantee = dict(payload["guarantee"])
    guarantee["title"] = "30-Day Confidence Guarantee"
    payload["guarantee"] = guarantee

    with pytest.raises(StrategyV2DecisionError, match="Risk Free Guarantee"):
        validate_strategy_v2_template_payload_fields(template_id="sales-pdp", payload_fields=payload)


def test_sales_template_payload_requires_at_least_eight_faqs() -> None:
    payload = _valid_sales_payload()
    faq = dict(payload["faq"])
    faq["items"] = faq["items"][:2]
    payload["faq"] = faq
    payload["faq_pills"] = payload["faq_pills"][:2]

    with pytest.raises(StrategyV2DecisionError, match="faq.items"):
        validate_strategy_v2_template_payload_fields(template_id="sales-pdp", payload_fields=payload)


def test_sales_template_payload_rejects_feature_style_whats_inside_benefits() -> None:
    payload = _valid_sales_payload()
    whats_inside = dict(payload["whats_inside"])
    whats_inside["benefits"] = [
        "Four-step Interaction Triage Workflow",
        "Source verification guide",
        "Printable quick-look pages",
        "Evidence-graded safety notes",
    ]
    payload["whats_inside"] = whats_inside

    with pytest.raises(StrategyV2DecisionError, match="benefits"):
        validate_strategy_v2_template_payload_fields(template_id="sales-pdp", payload_fields=payload)


def test_sales_template_payload_requires_mechanism_callout() -> None:
    payload = _valid_sales_payload()
    mechanism = dict(payload["mechanism"])
    mechanism.pop("callout")
    payload["mechanism"] = mechanism
    with pytest.raises(StrategyV2DecisionError, match="TEMPLATE_PAYLOAD_VALIDATION"):
        validate_strategy_v2_template_payload_fields(template_id="sales-pdp", payload_fields=payload)


def test_sales_template_payload_requires_comparison_metadata() -> None:
    payload = _valid_sales_payload()
    mechanism = dict(payload["mechanism"])
    comparison = dict(mechanism["comparison"])
    comparison.pop("title")
    mechanism["comparison"] = comparison
    payload["mechanism"] = mechanism
    with pytest.raises(StrategyV2DecisionError, match="TEMPLATE_PAYLOAD_VALIDATION"):
        validate_strategy_v2_template_payload_fields(template_id="sales-pdp", payload_fields=payload)


def test_sales_patch_uses_generated_bullet_titles_not_hardcoded_key_point() -> None:
    fields = validate_strategy_v2_template_payload_fields(
        template_id="sales-pdp",
        payload_fields=_valid_sales_payload(),
    )
    operations = build_strategy_v2_template_patch_operations(template_id="sales-pdp", payload_fields=fields)
    bullets_operation = next(
        operation
        for operation in operations
        if operation["component_type"] == "SalesPdpStorySolution" and operation["field_path"] == "props.config.bullets"
    )
    bullets = bullets_operation["value"]
    assert isinstance(bullets, list)
    assert bullets[0]["title"] == "Red-flag markers"
    assert all(item["title"] != "Key point" for item in bullets)
