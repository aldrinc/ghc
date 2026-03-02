from __future__ import annotations

from app.strategy_v2.copy_contract_spec import default_copy_contract_profile, get_page_contract
from app.strategy_v2.copy_input_packet import parse_minimum_delivery_section_index
from app.strategy_v2.copy_quality import evaluate_copy_page_quality
from app.strategy_v2.copy_semantic_gates import evaluate_copy_page_semantic_gates
from app.strategy_v2.scorers import build_page_data_from_body_text, score_congruency_extended


def _repeat_words(token: str, count: int) -> str:
    return " ".join([token] * count)


def test_cta_count_ignores_url_path_tokens_and_keeps_marketer_cta_sections() -> None:
    profile = default_copy_contract_profile()
    contract = get_page_contract(profile=profile, page_type="sales_page_warm")
    markdown = (
        "# Headline\n\n"
        f"## Hero Stack\n{_repeat_words('offer', 160)} [Read the method](/checkout)\n\n"
        f"## Problem Recap\n{_repeat_words('problem', 220)} health claims require proof and context.\n\n"
        f"## Mechanism + Comparison\n{_repeat_words('mechanism', 220)}\n\n"
        f"## Identity Bridge\n{_repeat_words('identity', 160)}\n\n"
        f"## Social Proof\n{_repeat_words('proof', 230)}\n\n"
        "## CTA #1\nMove forward now. [Continue checkout](/checkout)\n\n"
        f"## What's Inside\n{_repeat_words('value', 180)}\n\n"
        f"## Bonus Stack + Value\n{_repeat_words('bonus', 170)}\n\n"
        f"## Guarantee\n{_repeat_words('guarantee', 100)}\n\n"
        "## CTA #2\nGet access now. [Complete purchase](/checkout)\n\n"
        f"## FAQ\n{_repeat_words('compliance', 180)} more safety claims and constraints.\n\n"
        "## CTA #3 + P.S.\nFinal action. [Get access](/checkout)\n"
    )
    report = evaluate_copy_page_quality(markdown=markdown, page_contract=contract)
    gate_keys = {gate.gate_key for gate in report.gates}
    assert "CTA_SECTION_COUNT" not in gate_keys
    assert "CTA_LEAKAGE_NON_CTA" not in gate_keys


def test_cta_leakage_gate_flags_transactional_anchor_text_outside_cta_sections() -> None:
    profile = default_copy_contract_profile()
    contract = get_page_contract(profile=profile, page_type="sales_page_warm")
    markdown = (
        "# Headline\n\n"
        f"## Hero Stack\n{_repeat_words('offer', 160)} [Start checkout](/learn-more)\n\n"
        f"## Problem Recap\n{_repeat_words('problem', 220)}\n\n"
        f"## Mechanism + Comparison\n{_repeat_words('mechanism', 220)}\n\n"
        f"## Identity Bridge\n{_repeat_words('identity', 160)}\n\n"
        f"## Social Proof\n{_repeat_words('proof', 230)}\n\n"
        "## CTA #1\nMove forward now. [Continue checkout](/checkout)\n\n"
        f"## What's Inside\n{_repeat_words('value', 180)}\n\n"
        f"## Bonus Stack + Value\n{_repeat_words('bonus', 170)}\n\n"
        f"## Guarantee\n{_repeat_words('guarantee', 100)}\n\n"
        "## CTA #2\nGet access now. [Complete purchase](/checkout)\n\n"
        f"## FAQ\n{_repeat_words('compliance', 180)}\n\n"
        "## CTA #3 + P.S.\nFinal action. [Get access](/checkout)\n"
    )
    report = evaluate_copy_page_quality(markdown=markdown, page_contract=contract)
    gate_keys = {gate.gate_key for gate in report.gates}
    reason_codes = {gate.reason_code for gate in report.gates}
    assert "CTA_LEAKAGE_NON_CTA" not in gate_keys
    assert "SALES_PAGE_WARM_CTA_LEAKAGE" not in reason_codes


def test_problem_recap_and_faq_do_not_count_as_cta_from_transition_phrase_or_url_tokens() -> None:
    profile = default_copy_contract_profile()
    contract = get_page_contract(profile=profile, page_type="sales_page_warm")
    markdown = (
        "# Headline\n\n"
        f"## Hero Stack\n{_repeat_words('offer', 160)} [Read the method](/checkout)\n\n"
        "## Problem Recap\n"
        f"{_repeat_words('problem', 220)} "
        "This is explanatory context only and may mention continue to offer.\n"
        "[Continue to offer](/offer)\n\n"
        f"## Mechanism + Comparison\n{_repeat_words('mechanism', 220)}\n\n"
        f"## Identity Bridge\n{_repeat_words('identity', 160)}\n\n"
        f"## Social Proof\n{_repeat_words('proof', 230)}\n\n"
        "## CTA #1\nMove forward now. [Continue checkout](/checkout)\n\n"
        f"## What's Inside\n{_repeat_words('value', 180)}\n\n"
        f"## Bonus Stack + Value\n{_repeat_words('bonus', 170)}\n\n"
        f"## Guarantee\n{_repeat_words('guarantee', 100)}\n\n"
        "## CTA #2\nGet access now. [Complete purchase](/checkout)\n\n"
        "## FAQ\n"
        f"{_repeat_words('compliance', 180)} "
        "Informational answer only, not a purchase instruction, with [learn more](/offer).\n\n"
        "## CTA #3 + P.S.\nFinal action. [Get access](/checkout)\n"
    )
    report = evaluate_copy_page_quality(markdown=markdown, page_contract=contract)
    gate_keys = {gate.gate_key for gate in report.gates}
    assert "CTA_SECTION_COUNT" not in gate_keys
    assert "CTA_LEAKAGE_NON_CTA" not in gate_keys


def test_non_cta_sections_with_in_order_to_phrase_do_not_trigger_cta_leakage() -> None:
    profile = default_copy_contract_profile()
    contract = get_page_contract(profile=profile, page_type="sales_page_warm")
    markdown = (
        "# Headline\n\n"
        f"## Hero Stack\n{_repeat_words('offer', 160)} [Read the method](/checkout)\n\n"
        "## Problem Recap\n"
        f"{_repeat_words('problem', 220)} "
        "This section explains context in order to compare safe options.\n\n"
        f"## Mechanism + Comparison\n{_repeat_words('mechanism', 220)}\n\n"
        f"## Identity Bridge\n{_repeat_words('identity', 160)}\n\n"
        f"## Social Proof\n{_repeat_words('proof', 230)}\n\n"
        "## CTA #1\nMove forward now. [Continue checkout](/checkout)\n\n"
        f"## What's Inside\n{_repeat_words('value', 180)}\n\n"
        f"## Bonus Stack + Value\n{_repeat_words('bonus', 170)}\n\n"
        f"## Guarantee\n{_repeat_words('guarantee', 100)}\n\n"
        "## CTA #2\nGet access now. [Complete purchase](/checkout)\n\n"
        "## FAQ\n"
        f"{_repeat_words('compliance', 180)} "
        "This answer exists in order to clarify boundaries.\n\n"
        "## CTA #3 + P.S.\nFinal action. [Get access](/checkout)\n"
    )
    report = evaluate_copy_page_quality(markdown=markdown, page_contract=contract)
    gate_keys = {gate.gate_key for gate in report.gates}
    assert "CTA_LEAKAGE_NON_CTA" not in gate_keys


def test_sales_quality_report_does_not_include_first_cta_ratio_gate() -> None:
    profile = default_copy_contract_profile()
    contract = get_page_contract(profile=profile, page_type="sales_page_warm")
    markdown = (
        "# Headline\n\n"
        f"## Hero Stack\n{_repeat_words('offer', 160)} [Start here](/checkout)\n\n"
        f"## Problem Recap\n{_repeat_words('problem', 220)}\n\n"
        f"## Mechanism + Comparison\n{_repeat_words('mechanism', 220)}\n\n"
        f"## Identity Bridge\n{_repeat_words('identity', 160)}\n\n"
        f"## Social Proof\n{_repeat_words('proof', 230)}\n\n"
        "## CTA #1\nMove forward now. [Continue checkout](/checkout)\n\n"
        f"## What's Inside\n{_repeat_words('value', 180)}\n\n"
        f"## Bonus Stack + Value\n{_repeat_words('bonus', 170)}\n\n"
        f"## Guarantee\n{_repeat_words('guarantee', 100)}\n\n"
        "## CTA #2\nGet access now. [Complete purchase](/checkout)\n\n"
        f"## FAQ\n{_repeat_words('compliance', 180)}\n\n"
        "## CTA #3 + P.S.\nFinal action. [Get access](/checkout)\n"
    )
    report = evaluate_copy_page_quality(markdown=markdown, page_contract=contract)
    gate_keys = {gate.gate_key for gate in report.gates}
    reason_codes = {gate.reason_code for gate in report.gates}
    assert "FIRST_CTA_POSITION" not in gate_keys
    assert "SALES_FIRST_CTA_POSITION" not in reason_codes


def test_semantic_first_cta_window_uses_canonical_cta_sections_only() -> None:
    profile = default_copy_contract_profile()
    contract = get_page_contract(profile=profile, page_type="sales_page_warm")
    markdown = (
        "# Headline\n\n"
        "## Hero Stack\nOffer and mechanism details. [Start here](/checkout)\n\n"
        "## Problem Recap\n"
        "Problem and pain recap with explanatory bridge text. "
        "You can continue to offer later. [Continue to offer](/offer)\n\n"
        "## Mechanism + Comparison\nMechanism and comparison details.\n\n"
        "## Identity Bridge\nIdentity and belief shift text.\n\n"
        "## Social Proof\nProof, evidence, and testimonial references.\n\n"
        "## CTA #1\nCheckout decision and purchase prompt. [Continue checkout](/checkout)\n\n"
        "## What's Inside\nValue stack and deliverables.\n\n"
        "## Bonus Stack + Value\nBonus and stack details.\n\n"
        "## Guarantee\nGuarantee and risk reversal details.\n\n"
        "## CTA #2\nOrder now. [Complete purchase](/checkout)\n\n"
        "## FAQ\nSafety/compliance answers and boundaries.\n\n"
        "## CTA #3 + P.S.\nFinal checkout reminder. [Buy now](/checkout)\n"
    )
    promise_contract = {
        "loop_question": "What changes?",
        "specific_promise": "faster safer decisions",
        "delivery_test": "The body must contain mechanism details and proof language.",
        "minimum_delivery": "Begin in Section 1. Substantially resolved by Section 2.",
    }
    report = evaluate_copy_page_semantic_gates(
        markdown=markdown,
        page_contract=contract,
        promise_contract=promise_contract,
    )
    assert report.first_cta_section_index == 6
    gate_keys = {gate.gate_key for gate in report.gate_results}
    assert "MARKDOWN_LINK_FLOOR" not in gate_keys
    assert "GUARANTEE_NEAR_CTA" not in gate_keys


def test_parse_minimum_delivery_prefers_resolved_boundary_section() -> None:
    boundary = parse_minimum_delivery_section_index(
        minimum_delivery="Begin in Section 1. Substantially resolved by Section 2.",
        total_sections=6,
    )
    assert boundary == 2


def test_promise_timing_uses_delivery_test_terms_before_specific_promise_noise() -> None:
    profile = default_copy_contract_profile()
    contract = get_page_contract(profile=profile, page_type="presell_advertorial")
    markdown = (
        "# Headline\n\n"
        "## Hook/Lead: Dosing Safety Trigger\n"
        "This section explains a dosing checklist and interaction warning for safer decisions.\n\n"
        "## Problem Crystallization: Dosing Guesswork Costs\n"
        "Pain and bottleneck language with specific frustration context.\n\n"
        "## Failed Solutions: Tried Advice Still Failed\n"
        "What she tried and why it failed.\n\n"
        "## Mechanism Reveal: Why Interaction Risk Escalates\n"
        "Mechanism explanation with root cause detail.\n\n"
        "## Proof + Bridge: Evidence for Checklist Decisions\n"
        "Proof language and bridge to offer. [Continue](/offer)\n\n"
        "## Transition CTA: Next Step\n"
        "Continue to offer. [Continue checkout](/offer)\n"
    )
    promise_contract = {
        "loop_question": "What changes?",
        "specific_promise": "unintentionally following pediatric children choosing commonly",
        "delivery_test": "The body must contain dosing checklist and interaction warning details.",
        "minimum_delivery": "Begin in Section 1. Substantially resolved by Section 2.",
    }
    report = evaluate_copy_page_semantic_gates(
        markdown=markdown,
        page_contract=contract,
        promise_contract=promise_contract,
    )
    promise_gate = next(g for g in report.gate_results if g.gate_key == "PROMISE_DELIVERY_TIMING")
    assert promise_gate.passed is True


def test_sales_proof_depth_near_miss_is_rejected_with_reason_code() -> None:
    profile = default_copy_contract_profile()
    contract = get_page_contract(profile=profile, page_type="sales_page_warm")
    markdown = (
        "# Headline\n\n"
        f"## Hero Stack\n{_repeat_words('offer', 150)} [Start here](/checkout)\n\n"
        f"## Problem Recap\n{_repeat_words('problem', 220)}\n\n"
        f"## Mechanism + Comparison\n{_repeat_words('mechanism', 220)}\n\n"
        f"## Identity Bridge\n{_repeat_words('identity', 160)}\n\n"
        f"## Social Proof\n{_repeat_words('proof', 190)}\n\n"
        "## CTA #1\nBuy now. [Continue checkout](/checkout)\n\n"
        f"## What's Inside\n{_repeat_words('value', 180)}\n\n"
        f"## Bonus Stack + Value\n{_repeat_words('bonus', 170)}\n\n"
        f"## Guarantee\n{_repeat_words('guarantee', 90)}\n\n"
        "## CTA #2\nGet access now. [Complete purchase](/checkout)\n\n"
        f"## FAQ\n{_repeat_words('compliance', 180)}\n\n"
        "## CTA #3 + P.S.\nFinal action. [Get access](/checkout)\n"
    )
    report = evaluate_copy_page_quality(markdown=markdown, page_contract=contract)
    proof_gate = next(g for g in report.gates if g.reason_code == "SALES_PROOF_DEPTH")
    assert proof_gate.passed is False
    assert "proof_words=" in proof_gate.detail
    assert "required>=220" in proof_gate.detail


def test_bh1_regression_fixture_canonical_only_titles_fail() -> None:
    headline = "How to Spot AI-Generated Herb Books (And What to Use Instead)"
    body = (
        "## Hook/Lead\nx\n\n"
        "## Problem Crystallization\nx\n\n"
        "## Failed Solutions\nx\n\n"
        "## Mechanism Reveal\nx\n\n"
        "## Proof + Bridge\nx\n\n"
        "## Transition CTA\nx\n"
    )
    page_data = build_page_data_from_body_text(body, page_type="advertorial")
    result = score_congruency_extended(
        headline=headline,
        page_data=page_data,
        promise_contract={
            "loop_question": "How?",
            "specific_promise": "Learn how to spot AI-generated herb books.",
            "delivery_test": "The body must explain a concrete method to identify AI-generated herb books.",
            "minimum_delivery": "Begin in Section 1. Substantially resolved by Section 2.",
        },
    )
    bh1 = next(row for row in result["result"]["bh"] if row[0] == "BH1")
    assert bh1[3][0] is False
    assert "0/6" in bh1[3][1]


def test_bh1_regression_fixture_topic_linked_titles_pass() -> None:
    headline = "How to Spot AI-Generated Herb Books (And What to Use Instead)"
    body = (
        "## Hook/Lead: AI-Generated Herb Books Warning\nx\n\n"
        "## Problem Crystallization: AI-Generated Herb Books Are Hard to Spot\nx\n\n"
        "## Failed Solutions: Why AI-Generated Herb Books Keep Passing Reviews\nx\n\n"
        "## Mechanism Reveal: How to Spot AI-Generated Herb Books Quickly\nx\n\n"
        "## Proof + Bridge: Buyers Who Avoided AI-Generated Herb Books\nx\n\n"
        "## Transition CTA: What to Use Instead of AI-Generated Herb Books\nx\n"
    )
    page_data = build_page_data_from_body_text(body, page_type="advertorial")
    result = score_congruency_extended(
        headline=headline,
        page_data=page_data,
        promise_contract={
            "loop_question": "How?",
            "specific_promise": "Learn how to spot AI-generated herb books.",
            "delivery_test": "The body must explain a concrete method to identify AI-generated herb books.",
            "minimum_delivery": "Begin in Section 1. Substantially resolved by Section 2.",
        },
    )
    bh1 = next(row for row in result["result"]["bh"] if row[0] == "BH1")
    assert bh1[3][0] is True
