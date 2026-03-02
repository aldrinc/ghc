from __future__ import annotations

import pytest

from app.services.funnel_templates import get_funnel_template
from app.strategy_v2.errors import StrategyV2DecisionError
from app.strategy_v2.template_bridge import (
    apply_strategy_v2_template_patch,
    build_strategy_v2_template_bridge_v1,
    build_strategy_v2_template_patch_operations,
    validate_strategy_v2_template_payload_fields,
)


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
- Safety stop-sign index
- Red-flag interaction notes
- Authenticity buying checklist
Everything is organized for quick lookup.

## Bonus Stack + Value: Included extras
You also get a compact quick-start reference page.

## Guarantee: 30-day confidence promise
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

## CTA #3 + P.S.: Final step
Use this reference before your next remedy decision.
[Get access now](#offer)
"""


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
            ],
            "callout": {
                "left_title": "Typical marketplace guides",
                "left_body": "Hard to verify, no clear safety markers.",
                "right_title": "Safety-first handbook",
                "right_body": "Verifiable, structured, and practical.",
            },
            "comparison": {
                "badge": "SIDE-BY-SIDE COMPARISON",
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
            "benefits": ["Stop-sign index", "Interaction notes"],
            "offer_helper_text": "Instant digital access.",
        },
        "bonus": {
            "free_gifts_title": "Included quick-start page",
            "free_gifts_body": "A concise one-page reference.",
        },
        "guarantee": {
            "title": "Try it with confidence",
            "paragraphs": ["If it is not a fit, request a refund."],
            "why_title": "Why this guarantee exists",
            "why_body": "It is built for practical repeatable use.",
            "closing_line": "Start confidently today.",
        },
        "faq": {
            "title": "Common questions",
            "items": [{"question": "Is this medical advice?", "answer": "No, educational guidance only."}],
        },
        "cta_close": "Get access now",
    }


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


def test_template_payload_patch_operations_apply_to_presales_template() -> None:
    fields = validate_strategy_v2_template_payload_fields(
        template_id="pre-sales-listicle",
        payload_fields={
            "hero": {
                "title": "What if your remedy process felt clear and safe?",
                "subtitle": "A practical checklist before your next decision.",
                "badges": [
                    {"label": "Safety-first guidance"},
                    {"label": "Practical routines"},
                    {"label": "Evidence-aware decisions"},
                ],
            },
            "reasons": [
                {
                    "number": 1,
                    "title": "Conflicting advice is common",
                    "body": "A structured checklist helps you evaluate signals quickly.",
                }
            ],
            "marquee": ["Safety first", "Clear decisions"],
            "pitch": {
                "title": "Use the handbook for faster, safer choices",
                "bullets": ["Simple steps", "Clear boundaries"],
                "cta_label": "Continue to offer",
            },
            "reviews": [
                {"text": "I stopped guessing and now make calmer calls.", "author": "A. Parent", "rating": 5},
                {"text": "The safety notes are easy to scan in the moment.", "author": "J. Caregiver", "rating": 5},
                {"text": "Finally a reference that is practical and clear.", "author": "R. Family", "rating": 5},
            ],
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
    reviews = next(item for item in children if item.get("type") == "PreSalesReviews")
    review_wall = next(item for item in children if item.get("type") == "PreSalesReviewWall")
    assert hero["props"]["config"]["badges"][0]["label"] == "Safety-first guidance"
    assert reviews["props"]["config"]["slides"][0]["text"] == "I stopped guessing and now make calmer calls."
    assert reviews["props"]["config"]["slides"][0]["author"] == "A. Parent"
    assert review_wall["props"]["config"]["buttonLabel"] == "Open full reviews"


def test_sales_template_payload_requires_exactly_two_cta_subbullets() -> None:
    payload = _valid_sales_payload()
    hero = dict(payload["hero"])
    hero["primary_cta_subbullets"] = ["One", "Two", "Three"]
    payload["hero"] = hero
    with pytest.raises(StrategyV2DecisionError, match="TEMPLATE_PAYLOAD_VALIDATION"):
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
