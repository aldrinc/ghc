from __future__ import annotations

import json
import pytest

from app.strategy_v2 import (
    ProductBriefStage3,
    default_copy_contract_profile,
    get_page_contract,
    build_copy_stage4_input_packet,
    render_copy_headline_runtime_instruction,
    render_copy_page_runtime_instruction,
    require_copy_page_semantic_quality,
    require_prompt_chain_provenance,
)
from app.strategy_v2.errors import (
    StrategyV2DecisionError,
    StrategyV2MissingContextError,
    StrategyV2SchemaValidationError,
)
from app.temporal.activities.strategy_v2_activities import (
    _CLAUDE_STRUCTURED_FALLBACK_MAX_TOKENS,
    _build_headline_candidate_pool,
    _build_copy_repair_directives,
    _llm_generate_text,
    _headline_numeric_promise_is_compatible,
    _normalize_sales_cta_section_titles,
    _repair_markdown_cta_label_for_congruency,
    _repair_markdown_for_headline_term_coverage,
    _repair_markdown_for_promise_delivery_timing,
    _repair_markdown_headings_for_congruency,
    _repair_sales_markdown_for_quality,
    _repair_sales_markdown_for_semantic_structure,
    _build_stage3_risk_headline_templates,
)


def _stage3_payload() -> dict[str, object]:
    quote = "I keep trying fixes and still feel stuck when bedtime gets chaotic."
    return {
        "schema_version": "2.0.0",
        "stage": 3,
        "product_name": "Routine Reset System",
        "description": "A practical behavior system for predictable evenings.",
        "price": "$49",
        "competitor_urls": ["https://competitor.example"],
        "product_customizable": True,
        "category_niche": "Sleep Support",
        "market_maturity_stage": "Growth",
        "primary_segment": {
            "name": "Working caregivers",
            "size_estimate": "Large",
            "key_differentiator": "Need practical implementation and clear safety boundaries",
        },
        "bottleneck": "Timing mismatch in nightly routine",
        "positioning_gaps": ["Most alternatives avoid mechanism-level clarity"],
        "competitor_count_validated": 3,
        "primary_icps": [
            "Working caregivers with unpredictable evenings",
            "Parents handling repeated nighttime routine breakdown",
            "Families comparing expensive options without clear process",
        ],
        "selected_angle": {
            "angle_id": "A01",
            "angle_name": "Mechanism-first relief",
            "definition": {
                "who": "Working caregivers",
                "pain_desire": "Overwhelm -> predictable evenings",
                "mechanism_why": "Mismatch between symptom timing and intervention sequence",
                "belief_shift": {
                    "before": "More effort alone will fix evenings",
                    "after": "Mechanism-fit sequencing creates predictable evenings",
                },
                "trigger": "Late-evening routine collapse",
            },
            "evidence": {
                "supporting_voc_count": 8,
                "top_quotes": [
                    {"voc_id": "V001", "quote": quote, "adjusted_score": 82.0},
                    {"voc_id": "V002", "quote": quote, "adjusted_score": 81.0},
                    {"voc_id": "V003", "quote": quote, "adjusted_score": 80.0},
                    {"voc_id": "V004", "quote": quote, "adjusted_score": 79.0},
                    {"voc_id": "V005", "quote": quote, "adjusted_score": 78.0},
                ],
                "triangulation_status": "DUAL",
                "velocity_status": "STEADY",
                "contradiction_count": 0,
            },
            "hook_starters": [
                {
                    "visual": "Kitchen table at night",
                    "opening_line": "Why evenings keep unraveling after 8 PM.",
                    "lever": "problem crystallization",
                }
            ],
        },
        "compliance_constraints": {
            "overall_risk": "YELLOW",
            "red_flag_patterns": ["disease cure claims"],
            "platform_notes": "Use specific, supportable language.",
        },
        "buyer_behavior_archetype": "Safety-first evaluator",
        "purchase_emotion": "relief",
        "price_sensitivity": "medium",
        "ump": "Trigger Timing Gap",
        "ums": "Evening Sequence Protocol",
        "core_promise": "Predictable evenings with less stress and fewer resets.",
        "value_stack_summary": [
            "Core implementation handbook",
            "Nightly sequence checklist",
            "Recovery protocol for off-nights",
        ],
        "guarantee_type": "30-day confidence guarantee",
        "pricing_rationale": "One-time purchase for reusable implementation system",
        "awareness_level_primary": "Problem-Aware",
        "sophistication_level": 3,
        "composite_score": 7.2,
        "variant_selected": "variant_a",
    }


def _copy_context_payload() -> dict[str, str]:
    return {
        "audience_product_markdown": (
            "# Audience + Product\n\n"
            "## Audience\n"
            "### Demographics\n"
            "- Primary segment: Working caregivers\n"
            "- Segment size estimate: Large\n"
            "- Key differentiator: Need practical implementation\n"
            "- ICP 1: Caregivers with repeated nighttime stress\n"
            "- ICP 2: Parents balancing work and home routines\n"
            "- ICP 3: Families seeking consistency\n\n"
            "### Pain Points\n"
            "- Routine breaks at the same trigger point\n"
            "- Bottleneck: timing mismatch\n"
            "- Trigger context: bedtime collapse\n\n"
            "### Goals\n"
            "- Predictable evenings\n"
            "- Lower stress at transition points\n"
            "- Maintain consistency through disruptions\n\n"
            "## Product\n"
            "- Name: Routine Reset System\n"
            "- Description: Practical sequence-based implementation\n"
            "- Price: $49\n\n"
            "## Selected Angle\n"
            "- Angle: Mechanism-first relief\n\n"
            "## Offer Core\n"
            "- UMP: Trigger Timing Gap\n"
            "- UMS: Evening Sequence Protocol\n"
            "- Core Promise: Predictable evenings\n\n"
            "## Value Stack\n"
            "- Core implementation handbook\n"
            "- Nightly sequence checklist\n"
            "- Recovery protocol\n"
        ),
        "brand_voice_markdown": "# Brand Voice\n\n- Direct\n- Practical\n- No hype",
        "compliance_markdown": (
            "# Compliance\n\n"
            "- Avoid disease cure claims\n"
            "- Use supportable language\n"
            "- Keep expectations realistic\n"
        ),
        "mental_models_markdown": "# Mental Models\n\n- Causality over correlation\n- Mechanism over hype",
        "awareness_angle_matrix_markdown": (
            "# Awareness-Angle Matrix\n\n"
            "## Unaware\n- Frame: Narrative\n"
            "## Problem-Aware\n- Frame: Pain clarity\n"
            "## Solution-Aware\n- Frame: Mechanism contrast\n"
            "## Product-Aware\n- Frame: Process detail\n"
            "## Most-Aware\n- Frame: Direct offer\n"
            "## Constant Elements\n- UMP\n- UMS\n"
            "## Variable Elements\n- Headline\n- CTA\n"
            "## Product Name First Appears\n- product_aware\n"
        ),
    }


def _presell_markdown() -> str:
    return (
        "# Approved Headline\n\n"
        "## Hook/Lead\n"
        "Predictable evenings are possible when the trigger mechanism is handled correctly.\n\n"
        "## Problem Crystallization\n"
        "The pain and bottleneck show up when routines break at the same point every night.\n\n"
        "## Failed Solutions\n"
        "Families tried quick fixes, failed to sustain them, and still repeated the same reset loop.\n\n"
        "## Mechanism Reveal\n"
        "The mechanism is timing mismatch; once corrected, stress drops and outcomes stabilize.\n\n"
        "## Proof + Bridge\n"
        "Proof from buyer quotes shows the mechanism shift works, and the offer bridges to implementation.\n\n"
        "## Transition CTA\n"
        "Continue to the full offer and implementation steps.\n"
        "[Continue to offer](/sales-page).\n"
    )


def _sales_markdown() -> str:
    return (
        "# Approved Headline — Sales\n\n"
        "## Hero Stack\n"
        "Offer overview: predictable evenings through a mechanism-first implementation system.\n"
        "[Start here](/checkout).\n\n"
        "## Problem Recap\n"
        "The main struggle is recurring nighttime friction and stress from unresolved bottlenecks.\n\n"
        "## Mechanism + Comparison\n"
        "This mechanism approach contrasts with generic routines that fail under pressure.\n\n"
        "## Identity Bridge\n"
        "You are not failing; the pain came from advice that ignored your actual constraints.\n\n"
        "## Social Proof + CTA Window\n"
        "Proof from real buyer language shows practical results and stronger consistency.\n\n"
        "## CTA #1\n"
        "Access the offer now.\n"
        "[Get the system](/checkout).\n\n"
        "## What's Inside\n"
        "Inside the value stack: checklists, templates, and implementation guidance.\n\n"
        "## Bonus Stack + Value\n"
        "Bonus value includes rapid-start scripts and exception handling examples.\n\n"
        "## Guarantee\n"
        "Guarantee terms include risk reversal with compliance-safe expectations and safety boundaries.\n\n"
        "## CTA #2\n"
        "Move ahead with the full offer.\n"
        "[Continue checkout](/checkout).\n\n"
        "## FAQ\n"
        "Proof and compliance details explain safe usage boundaries and expected outcomes.\n\n"
        "## CTA #3 + P.S.\n"
        "Final offer: start today. Price: $49 one-time.\n"
        "[Complete purchase](/checkout).\n"
    )


def test_copy_input_packet_and_runtime_blocks_build_successfully() -> None:
    profile = default_copy_contract_profile()
    stage3 = ProductBriefStage3.model_validate(_stage3_payload())
    packet = build_copy_stage4_input_packet(
        stage3=stage3,
        copy_context_payload=_copy_context_payload(),
        hook_lines=["Why evenings keep unraveling after 8 PM."],
        profile=profile,
    )

    headline_runtime = render_copy_headline_runtime_instruction(packet=packet)
    assert "COPY_PROFILE_ID" in headline_runtime
    assert "HOOK_LINES_JSON" in headline_runtime

    promise_contract = {
        "loop_question": "What changes when the trigger mechanism is corrected?",
        "specific_promise": "Predictable evenings with less stress and fewer resets.",
        "delivery_test": "Show mechanism mismatch and practical correction path.",
        "minimum_delivery": "Deliver by midpoint with clear implementation detail.",
    }
    page_runtime = render_copy_page_runtime_instruction(
        packet=packet,
        headline="Approved Headline",
        promise_contract=promise_contract,
        page_contract=get_page_contract(profile=profile, page_type="presell_advertorial"),
    )
    assert "PAGE_SECTION_CONTRACT_JSON" in page_runtime
    assert "PROMISE_CONTRACT_JSON" in page_runtime
    assert "CTA Budget Rules (strict)" in page_runtime
    assert "Non-CTA sections may include informational links" in page_runtime
    assert "URL path tokens alone do not count as CTA intent." in page_runtime

    sales_page_runtime = render_copy_page_runtime_instruction(
        packet=packet,
        headline="Approved Headline",
        promise_contract=promise_contract,
        page_contract=get_page_contract(profile=profile, page_type="sales_page_warm"),
    )
    assert "Place the first CTA before" not in sales_page_runtime


def test_copy_repair_directives_add_cta_budget_fix_when_cta_count_fails() -> None:
    directives = _build_copy_repair_directives(
        previous_errors=[
            "Presell advertorial failed copy depth/structure gates. PRESELL_ADVERTORIAL_CTA_COUNT: cta_count=4, required_range=[1,2]"
        ]
    )

    assert "CTA cadence hard-fix" in directives
    assert "required_range=[1,2]" in directives
    assert "never above 2" in directives
    assert "URL path tokens alone do not count as CTA intent." in directives
    assert "Canonical CTA sections are headings that contain `CTA` or `Continue to Offer`." in directives


def test_copy_repair_directives_add_sales_proof_hard_fix() -> None:
    directives = _build_copy_repair_directives(
        previous_errors=[
            (
                "Sales page failed copy depth/structure gates. "
                "SALES_PROOF_DEPTH: proof_words=188, required>=220"
            )
        ]
    )

    assert "Proof depth hard-fix" in directives
    assert "required>=220" in directives
    assert "First CTA placement hard-fix" not in directives


def test_copy_repair_directives_add_heading_and_promise_timing_hard_fixes() -> None:
    directives = _build_copy_repair_directives(
        previous_errors=[
            "Presell advertorial congruency test BH1 failed: 0/6 section topics connected to headline (0%)",
            (
                "Presell advertorial failed semantic copy gates. "
                "PROMISE_DELIVERY_TIMING: No promise terms delivered by section boundary 1."
            ),
        ]
    )

    assert "Heading congruency hard-fix" in directives
    assert "Promise timing hard-fix" in directives


def test_copy_repair_directives_add_semantic_structure_hard_fixes_for_sales_scope() -> None:
    directives = _build_copy_repair_directives(
        previous_errors=[
            (
                "Sales page failed semantic copy gates. "
                "REQUIRED_SECTION_COVERAGE: Missing required sections: What's Inside, Bonus Stack + Value, FAQ, CTA #3 + P.S.; "
                "BELIEF_SEQUENCE_ORDER: Required section ordering is broken for belief progression."
            )
        ],
        page_scope="sales_page_warm",
    )

    assert "Required section coverage hard-fix" in directives
    assert "What's Inside" in directives
    assert "CTA #3 + P.S." in directives
    assert "Belief sequence hard-fix" in directives
    assert "Hero Stack -> Problem Recap" in directives


def test_copy_repair_directives_add_word_budget_hard_fixes() -> None:
    directives = _build_copy_repair_directives(
        previous_errors=[
            (
                "Sales page failed copy depth/structure gates. "
                "SALES_PAGE_WARM_WORD_FLOOR: total_words=1686, required>=1800; "
                "SALES_PAGE_WARM_WORD_CEILING: total_words=3522, required<=3500"
            )
        ]
    )

    assert "Word floor hard-fix" in directives
    assert "required>=1800" in directives
    assert "Word ceiling hard-fix" in directives
    assert "required<=3500" in directives


def test_copy_repair_directives_scope_filters_cross_page_errors() -> None:
    previous_errors = [
        "Presell advertorial failed semantic copy gates. REQUIRED_SECTION_COVERAGE: Missing required sections: Transition CTA",
        "Sales page failed semantic copy gates. REQUIRED_SECTION_COVERAGE: Missing required sections: CTA #3 + P.S.",
    ]

    sales_directives = _build_copy_repair_directives(
        previous_errors=previous_errors,
        page_scope="sales_page_warm",
    )
    presell_directives = _build_copy_repair_directives(
        previous_errors=previous_errors,
        page_scope="presell_advertorial",
    )

    assert "CTA #3 + P.S." in sales_directives
    assert "Transition CTA" not in sales_directives
    assert "Transition CTA" in presell_directives
    assert "CTA #3 + P.S." not in presell_directives


def test_stage3_risk_headline_templates_include_risk_patterns() -> None:
    stage3 = ProductBriefStage3.model_validate(_stage3_payload())
    templates = _build_stage3_risk_headline_templates(stage3)

    assert len(templates) >= 3
    assert any(template.startswith("New Warning:") for template in templates)
    assert any("Before You Trust Any" in template for template in templates)
    assert all("risk" in template.lower() for template in templates)
    assert all(" 7 " not in f" {template.lower()} " for template in templates)


def test_headline_numeric_promise_compatibility_matches_expected_sections() -> None:
    assert _headline_numeric_promise_is_compatible(
        headline="Before You Trust Any Herbal Guide, Check 6 Red Flags",
        expected_item_count=6,
    )
    assert not _headline_numeric_promise_is_compatible(
        headline="Before You Trust Any Herbal Guide, Check 7 Red Flags",
        expected_item_count=6,
    )
    assert _headline_numeric_promise_is_compatible(
        headline="A Safety-First Herbal Buying Checklist",
        expected_item_count=6,
    )


def test_headline_candidate_pool_prioritizes_risk_templates_before_truncation() -> None:
    prompt_headlines = [f"Prompt headline {index}" for index in range(1, 13)]
    hooks = [f"Hook headline {index}" for index in range(1, 4)]
    risk_templates = ["Risk A", "Risk B", "Risk C"]
    pool = _build_headline_candidate_pool(
        prompt_headlines=prompt_headlines,
        hook_lines=hooks,
        risk_headline_templates=risk_templates,
        fallback_candidates=["Core Promise", "UMP"],
        max_candidates=15,
    )

    assert pool[:3] == risk_templates
    assert "Hook headline 1" not in pool
    assert len(pool) == 15


def test_sales_markdown_repair_boosts_proof_depth_only() -> None:
    stage3 = ProductBriefStage3.model_validate(_stage3_payload())
    profile = default_copy_contract_profile()
    sales_contract = get_page_contract(profile=profile, page_type="sales_page_warm")
    markdown = (
        "# Headline\n\n"
        "## Hero Stack\n"
        "Core offer summary.\n\n"
        "## Problem Recap\n"
        "Problem recap text.\n\n"
        "## Mechanism + Comparison\n"
        "Mechanism text.\n\n"
        "## Identity Bridge\n"
        "Identity bridge text.\n\n"
        "## Social Proof\n"
        "A short proof note.\n\n"
        "## What's Inside\n"
        "Value stack details.\n\n"
        "## Bonus Stack + Value\n"
        "Bonus details.\n\n"
        "## Guarantee\n"
        "Guarantee details.\n\n"
        "## CTA #1\n"
        "Buy now.\n"
        "[Get access](/checkout)\n\n"
        "## FAQ\n"
        "FAQ details.\n\n"
        "## CTA #2\n"
        "Continue checkout.\n"
        "[Continue checkout](/checkout)\n\n"
        "## CTA #3 + P.S.\n"
        "Final CTA text.\n"
        "[Complete purchase](/checkout)\n"
    )

    repaired = _repair_sales_markdown_for_quality(
        markdown=markdown,
        stage3=stage3,
        page_contract=sales_contract,
    )

    assert "Additional buyer evidence:" in repaired


def test_sales_semantic_structure_repair_adds_missing_tail_sections_in_contract_order() -> None:
    stage3 = ProductBriefStage3.model_validate(_stage3_payload())
    profile = default_copy_contract_profile()
    sales_contract = get_page_contract(profile=profile, page_type="sales_page_warm")
    promise_contract = {
        "loop_question": "What changes when counterfeit guidance is filtered out?",
        "specific_promise": "Safer remedy decisions with clearer source validation.",
        "delivery_test": "Show concrete red flags and practical checks in early sections.",
        "minimum_delivery": "Deliver by section 2.",
    }
    markdown = (
        "# Headline\n\n"
        "## Hero Stack\n"
        "Offer summary.\n"
        "[Start here](/checkout)\n\n"
        "## Problem Recap\n"
        "Problem recap.\n\n"
        "## Mechanism + Comparison\n"
        "Mechanism details.\n\n"
        "## Identity Bridge\n"
        "Identity bridge.\n\n"
        "## Social Proof + CTA Window\n"
        "Proof details.\n\n"
        "## CTA #1\n"
        "Primary action.\n"
        "[Get access](/checkout)\n\n"
        "## CTA #2\n"
        "Second action.\n"
        "[Continue checkout](/checkout)\n"
    )

    repaired = _repair_sales_markdown_for_semantic_structure(
        markdown=markdown,
        stage3=stage3,
        promise_contract=promise_contract,
        page_contract=sales_contract,
    )

    required_headings = [
        "Hero Stack",
        "Problem Recap",
        "Mechanism + Comparison",
        "Identity Bridge",
        "Social Proof",
        "CTA #1",
        "What's Inside",
        "Bonus Stack + Value",
        "Guarantee",
        "CTA #2",
        "FAQ",
        "CTA #3 + P.S.",
    ]
    indices = [repaired.find(f"## {heading}") for heading in required_headings]
    assert all(index >= 0 for index in indices)
    assert indices == sorted(indices)
    assert "[Complete purchase](/checkout)" in repaired


def test_sales_cta_title_normalization_renumbers_cta_sections_from_one() -> None:
    markdown = (
        "# Headline\n\n"
        "## Hero Stack\nOffer summary.\n\n"
        "## Transition CTA\nPrimary action.\n\n"
        "## FAQ\nInformational details.\n\n"
        "## CTA #4 + P.S.\nFinal action.\n"
    )

    repaired = _normalize_sales_cta_section_titles(markdown=markdown)

    assert "## Transition CTA #1" in repaired
    assert "## CTA #2 + P.S." in repaired
    assert "## CTA #4 + P.S." not in repaired


def test_sales_cta_title_normalization_renumbers_post_social_ctas_from_one() -> None:
    markdown = (
        "# Headline\n\n"
        "## Hero Stack\nOffer summary.\n\n"
        "## CTA #5\nEarly CTA teaser.\n\n"
        "## Problem Recap\nProblem recap.\n\n"
        "## Mechanism + Comparison\nMechanism details.\n\n"
        "## Identity Bridge\nIdentity bridge.\n\n"
        "## Social Proof\nProof details.\n\n"
        "## CTA #2\nPrimary post-proof CTA.\n\n"
        "## CTA #3 + P.S.\nFinal post-proof CTA.\n"
    )

    repaired = _normalize_sales_cta_section_titles(markdown=markdown)

    assert "## CTA #5" in repaired
    assert "## CTA #1" in repaired
    assert "## CTA #2 + P.S." in repaired
    assert "## CTA #3 + P.S." not in repaired


def test_sales_cta_title_normalization_moves_cta_after_social_when_missing_post_social_cta() -> None:
    markdown = (
        "# Headline\n\n"
        "## Hero Stack\nOffer summary.\n\n"
        "## CTA #2\nEarly CTA.\n\n"
        "## Problem Recap\nProblem recap.\n\n"
        "## Mechanism + Comparison\nMechanism details.\n\n"
        "## Identity Bridge\nIdentity bridge.\n\n"
        "## Social Proof\nProof details.\n\n"
        "## What's Inside\nValue stack.\n\n"
        "## FAQ\nFAQ details.\n"
    )

    repaired = _normalize_sales_cta_section_titles(markdown=markdown)

    assert repaired.find("## Social Proof") < repaired.find("## CTA #1")
    assert "## CTA #2" not in repaired


def test_heading_repair_adds_headline_terms_to_marker_only_sections() -> None:
    markdown = (
        "# Headline\n\n"
        "## Hook/Lead\n"
        "Lead copy.\n\n"
        "## Problem Crystallization\n"
        "Problem copy.\n\n"
        "## Transition CTA\n"
        "[Continue to offer](/sales-page)\n"
    )
    repaired = _repair_markdown_headings_for_congruency(
        markdown=markdown,
        headline="Before You Trust Any Herbal Guide, Check 7 Counterfeit Red Flags",
    )

    assert "## Hook/Lead: trust herbal guide" in repaired
    assert "## Problem Crystallization: trust herbal guide" in repaired
    assert "## Transition CTA: trust herbal guide" in repaired


def test_cta_label_repair_adds_headline_term_to_last_cta_link() -> None:
    markdown = (
        "# Headline\n\n"
        "## Hook/Lead: trust herbal guide\n"
        "Lead copy.\n\n"
        "## Transition CTA: trust herbal guide\n"
        "[Continue to offer](/sales-page)\n"
    )
    repaired = _repair_markdown_cta_label_for_congruency(
        markdown=markdown,
        headline="Before You Trust Any Herbal Guide, Check 7 Counterfeit Red Flags",
    )

    assert "[Continue to offer trust](/sales-page)" in repaired


def test_headline_term_coverage_repair_injects_missing_terms() -> None:
    markdown = (
        "# Headline\n\n"
        "## Hook/Lead: trust herbal guide\n"
        "Lead copy about trust and herbal guide.\n\n"
        "## Transition CTA: trust herbal guide\n"
        "[Continue to offer trust](/sales-page)\n"
    )
    repaired = _repair_markdown_for_headline_term_coverage(
        markdown=markdown,
        headline="Before You Trust Any Herbal Guide, Check Counterfeit Red Flags",
    )

    assert "Headline coverage terms:" in repaired
    assert "counterfeit" in repaired.lower()


def test_promise_timing_repair_injects_terms_into_early_section_when_missing() -> None:
    markdown = (
        "# Headline\n\n"
        "## Hook/Lead: herbal checklist\n"
        "Opening section without promise terms.\n\n"
        "## Problem Crystallization: herbal checklist\n"
        "More context and framing.\n"
    )
    repaired = _repair_markdown_for_promise_delivery_timing(
        markdown=markdown,
        promise_contract={
            "loop_question": "Why do pediatric mistakes happen so often?",
            "specific_promise": "Avoid unsafe interactions using practical dosing boundaries.",
            "delivery_test": "Explain pediatric interaction and dosing risk early.",
            "minimum_delivery": "Resolve by section 1.",
        },
    )

    assert "Promise checkpoint:" in repaired
    assert "pediatric" in repaired.lower()
    assert "Safety detail:" in repaired


def test_copy_input_packet_rejects_sparse_copy_context() -> None:
    stage3 = ProductBriefStage3.model_validate(_stage3_payload())
    bad_context = _copy_context_payload()
    bad_context["audience_product_markdown"] = "# Audience + Product\n\n## Audience\n- Thin"

    with pytest.raises(StrategyV2MissingContextError):
        build_copy_stage4_input_packet(
            stage3=stage3,
            copy_context_payload=bad_context,
            hook_lines=["Why evenings keep unraveling after 8 PM."],
            profile=default_copy_contract_profile(),
        )


def test_semantic_gates_accept_contract_aligned_markdown() -> None:
    profile = default_copy_contract_profile()
    promise_contract = {
        "loop_question": "What changes when the trigger mechanism is corrected?",
        "specific_promise": "Predictable evenings with less stress and fewer resets.",
        "delivery_test": "Show mechanism mismatch and practical correction path.",
        "minimum_delivery": "Deliver by midpoint with clear implementation detail.",
    }

    presell_report = require_copy_page_semantic_quality(
        markdown=_presell_markdown(),
        page_contract=get_page_contract(profile=profile, page_type="presell_advertorial"),
        promise_contract=promise_contract,
        page_name="Presell advertorial",
    )
    sales_report = require_copy_page_semantic_quality(
        markdown=_sales_markdown(),
        page_contract=get_page_contract(profile=profile, page_type="sales_page_warm"),
        promise_contract=promise_contract,
        page_name="Sales page",
    )

    assert presell_report.passed is True
    assert sales_report.passed is True


def test_semantic_gates_reject_missing_required_sections() -> None:
    profile = default_copy_contract_profile()
    promise_contract = {
        "loop_question": "What changes when the trigger mechanism is corrected?",
        "specific_promise": "Predictable evenings with less stress and fewer resets.",
        "delivery_test": "Show mechanism mismatch and practical correction path.",
        "minimum_delivery": "Deliver by midpoint with clear implementation detail.",
    }

    with pytest.raises(StrategyV2DecisionError):
        require_copy_page_semantic_quality(
            markdown="# Headline\n\n## Hook/Lead\nOnly one section.",
            page_contract=get_page_contract(profile=profile, page_type="presell_advertorial"),
            promise_contract=promise_contract,
            page_name="Presell advertorial",
        )


def test_prompt_chain_provenance_report_requires_all_fields() -> None:
    passing = require_prompt_chain_provenance(
        prompt_chain={
            "headline_prompt_provenance": {
                "prompt_path": "p1.md",
                "prompt_sha256": "abc",
                "model_name": "model",
                "input_contract_version": "2.0.0",
                "output_contract_version": "2.0.0",
            },
            "headline_prompt_raw_output": "{}",
            "promise_prompt_provenance": {
                "prompt_path": "p2.md",
                "prompt_sha256": "def",
                "model_name": "model",
                "input_contract_version": "2.0.0",
                "output_contract_version": "2.0.0",
            },
            "promise_prompt_raw_output": "{}",
            "advertorial_prompt_provenance": {
                "prompt_path": "p3.md",
                "prompt_sha256": "ghi",
                "model_name": "model",
                "input_contract_version": "2.0.0",
                "output_contract_version": "2.0.0",
            },
            "advertorial_prompt_raw_output": "{}",
            "sales_prompt_provenance": {
                "prompt_path": "p4.md",
                "prompt_sha256": "jkl",
                "model_name": "model",
                "input_contract_version": "2.0.0",
                "output_contract_version": "2.0.0",
            },
            "sales_prompt_raw_output": "{}",
        }
    )
    assert passing.passed is True

    with pytest.raises(StrategyV2SchemaValidationError):
        require_prompt_chain_provenance(
            prompt_chain={
                "headline_prompt_provenance": {},
                "headline_prompt_raw_output": "",
            }
        )


def test_llm_generate_text_uses_claude_structured_output_when_schema_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_structured_call(
        *,
        model: str,
        system: str | None,
        user_content: list[dict[str, object]],
        output_schema: dict[str, object],
        max_tokens: int,
        temperature: float,
    ) -> dict[str, object]:
        captured["model"] = model
        captured["system"] = system
        captured["user_content"] = user_content
        captured["output_schema"] = output_schema
        captured["max_tokens"] = max_tokens
        captured["temperature"] = temperature
        return {
            "parsed": {"headline": "Counterfeit checklist for safer herbal buying"},
            "raw": {"id": "msg_test"},
            "text": "",
            "request_id": "req_test_123",
            "stop_reason": "end_turn",
            "usage": {"input": 111, "output": 22},
        }

    monkeypatch.setattr(
        "app.temporal.activities.strategy_v2_activities.call_claude_structured_message",
        _fake_structured_call,
    )

    progress_sink: dict[str, object] = {}
    output = _llm_generate_text(
        prompt="Return one headline JSON object.",
        model="claude-haiku-4-5-20251001",
        progress_sink=progress_sink,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "headline_result",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"headline": {"type": "string"}},
                    "required": ["headline"],
                },
            },
        },
    )

    assert captured["model"] == "claude-haiku-4-5-20251001"
    assert captured["temperature"] == 0.0
    assert captured["max_tokens"] == _CLAUDE_STRUCTURED_FALLBACK_MAX_TOKENS
    assert captured["system"] is None
    assert captured["user_content"] == [{"type": "text", "text": "Return one headline JSON object."}]
    assert isinstance(captured["output_schema"], dict)
    assert json.loads(output) == {"headline": "Counterfeit checklist for safer herbal buying"}
    assert progress_sink["request_id"] == "req_test_123"
    assert progress_sink["stop_reason"] == "end_turn"
    assert progress_sink["input_tokens"] == 111
    assert progress_sink["output_tokens"] == 22
    assert progress_sink["total_tokens"] == 133


def test_llm_generate_text_uses_explicit_claude_messages_when_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_structured_call(
        *,
        model: str,
        system: str | None,
        output_schema: dict[str, object],
        max_tokens: int,
        temperature: float,
        user_content: list[dict[str, object]] | None = None,
        messages: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        captured["model"] = model
        captured["system"] = system
        captured["user_content"] = user_content
        captured["messages"] = messages
        captured["output_schema"] = output_schema
        captured["max_tokens"] = max_tokens
        captured["temperature"] = temperature
        return {
            "parsed": {"headline": "Rewritten headline"},
            "raw": {"id": "msg_test"},
            "text": "",
            "request_id": "req_ctx_123",
            "stop_reason": "end_turn",
            "usage": {"input": 120, "output": 30},
        }

    monkeypatch.setattr(
        "app.temporal.activities.strategy_v2_activities.call_claude_structured_message",
        _fake_structured_call,
    )

    conversation_messages = [
        {"role": "user", "content": [{"type": "text", "text": "Draft a headline."}]},
        {"role": "assistant", "content": [{"type": "text", "text": "{\"headline\":\"Draft\"}"}]},
        {"role": "user", "content": [{"type": "text", "text": "Fix IA2 and PT9 failures."}]},
    ]
    output = _llm_generate_text(
        prompt="This prompt should not be sent when claude_messages is provided.",
        model="claude-haiku-4-5-20251001",
        claude_messages=conversation_messages,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "headline_result",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"headline": {"type": "string"}},
                    "required": ["headline"],
                },
            },
        },
    )

    assert captured["model"] == "claude-haiku-4-5-20251001"
    assert captured["messages"] == conversation_messages
    assert captured["user_content"] is None
    assert captured["temperature"] == 0.0
    assert captured["max_tokens"] == _CLAUDE_STRUCTURED_FALLBACK_MAX_TOKENS
    assert json.loads(output) == {"headline": "Rewritten headline"}
