from __future__ import annotations

import os
from types import SimpleNamespace
import pytest

import app.strategy_v2.scorers as scorer_module
from app.strategy_v2 import (
    StrategyV2MissingContextError,
    StrategyV2ScorerError,
    build_copy_context_files,
    build_page_data_from_body_text,
    calibration_consistency_checker,
    derive_compliance_sensitivity,
    extract_competitor_analysis,
    map_offer_pipeline_input,
    score_angles,
    score_congruency_extended,
    score_habitats,
    score_headline,
    score_videos,
    score_voc_items,
    translate_stage0,
    translate_stage1,
)
from app.strategy_v2.contracts import (
    AwarenessAngleMatrix,
    ProductBriefStage2,
    ProductBriefStage3,
)
from app.strategy_v2.scorers import run_headline_qa_loop, ump_ums_scorer


def _precanon_research_fixture() -> dict[str, object]:
    return {
        "step_contents": {
            "01": (
                "Category / Niche: Herbal Remedies\n"
                "Market Maturity: Growth\n"
                "Validated competitors: 3\n"
                "- Positioning gap: precise dosage references for families\n"
            ),
            "02": (
                '{"compliance_landscape":{"overall":{"red_pct":0.12,"yellow_pct":0.34}},'
                '"competitors":[{"name":"Competitor A"}]}'
            ),
            "06": (
                "1. Busy home herbal caregivers\n"
                "2. Parents seeking safer alternatives\n"
                "3. Price-conscious wellness buyers\n"
                "Bottleneck: confidence in dosage decisions\n"
            ),
        }
    }


def _selected_angle_payload() -> dict[str, object]:
    return {
        "angle_id": "A04",
        "angle_name": "The Dosage Gap",
        "definition": {
            "who": "Home herbal caregivers",
            "pain_desire": "Need confident, safe dosing for family use",
            "mechanism_why": "Most guides omit practical dosage clarity",
            "belief_shift": {
                "before": "General herb tips are enough",
                "after": "Specific dosing context prevents common mistakes",
            },
            "trigger": "Conflicting advice creates safety anxiety",
        },
        "evidence": {
            "supporting_voc_count": 12,
            "top_quotes": [
                {
                    "voc_id": "V001",
                    "quote": "I have herbs but no confidence in dose amounts.",
                    "adjusted_score": 74.2,
                }
            ],
            "triangulation_status": "DUAL",
            "velocity_status": "STEADY",
            "contradiction_count": 1,
        },
        "hook_starters": [
            {
                "visual": "Herb jars and a dosing notebook",
                "opening_line": "Most herbal guides skip the exact amount.",
                "lever": "safety certainty",
            }
        ],
    }


def _awareness_matrix_payload() -> dict[str, object]:
    framing = {
        "frame": "Angle framing example",
        "headline_direction": "headline structure",
        "entry_emotion": "uncertainty",
        "exit_belief": "confidence",
    }
    return {
        "angle_name": "The Dosage Gap",
        "awareness_framing": {
            "unaware": framing,
            "problem_aware": framing,
            "solution_aware": framing,
            "product_aware": framing,
            "most_aware": framing,
        },
        "constant_elements": ["UMP", "UMS", "Core Promise"],
        "variable_elements": ["Proof type", "CTA directness"],
        "product_name_first_appears": "product_aware",
    }


def _build_stage2() -> ProductBriefStage2:
    stage0 = translate_stage0(
        product_name="Honest Herbalist Handbook",
        product_description="Digital handbook for practical herbal safety and use.",
        onboarding_payload={"competitor_urls": ["https://example.com"]},
        stage0_overrides={"product_customizable": True, "price": "$49"},
    )
    stage1 = translate_stage1(stage0=stage0, precanon_research=_precanon_research_fixture())
    stage2_payload = stage1.model_dump(mode="python")
    stage2_payload.update(
        {
            "stage": 2,
            "selected_angle": _selected_angle_payload(),
            "compliance_constraints": {
                "overall_risk": "YELLOW",
                "red_flag_patterns": ["disease treatment claims"],
                "platform_notes": "Meta requires cautious framing.",
            },
            "buyer_behavior_archetype": "Safety-first evaluator",
            "purchase_emotion": "relief",
            "price_sensitivity": "medium",
        }
    )
    return ProductBriefStage2.model_validate(stage2_payload)


def _build_stage3() -> ProductBriefStage3:
    stage2 = _build_stage2()
    stage3_payload = stage2.model_dump(mode="python")
    stage3_payload.update(
        {
            "stage": 3,
            "ump": "The Dosage Guesswork Trap",
            "ums": "The Practical Safety Dosing System",
            "core_promise": "Give families practical herbal guidance with dosing clarity.",
            "value_stack_summary": [
                "Core handbook",
                "Interaction checklist",
                "Daily dosing quick-reference",
            ],
            "guarantee_type": "30-day satisfaction guarantee",
            "pricing_rationale": "Single purchase for ongoing family reference.",
            "awareness_level_primary": "Problem-Aware",
            "sophistication_level": 3,
            "composite_score": 6.8,
            "variant_selected": "variant_a",
        }
    )
    return ProductBriefStage3.model_validate(stage3_payload)


def test_translate_stage0_requires_product_customizable() -> None:
    with pytest.raises(StrategyV2MissingContextError):
        translate_stage0(
            product_name="Honest Herbalist Handbook",
            product_description="Digital herbal safety guide.",
            onboarding_payload={},
            stage0_overrides={},
        )


def test_translate_stage0_and_stage1_success() -> None:
    stage0 = translate_stage0(
        product_name="Honest Herbalist Handbook",
        product_description="Digital herbal safety guide.",
        onboarding_payload={"competitor_urls": ["https://example.com"]},
        stage0_overrides={"product_customizable": True, "price": "$49"},
    )
    assert stage0.stage == 0
    assert stage0.product_customizable is True

    stage1 = translate_stage1(stage0=stage0, precanon_research=_precanon_research_fixture())
    assert stage1.stage == 1
    assert stage1.category_niche == "Herbal Remedies"
    assert len(stage1.product_category_keywords) >= 3
    assert stage1.competitor_count_validated == 3
    assert len(stage1.primary_icps) >= 1


def test_translate_stage0_sets_tbd_price_when_unknown() -> None:
    stage0 = translate_stage0(
        product_name="Honest Herbalist Handbook",
        product_description="Digital herbal safety guide.",
        onboarding_payload={"competitor_urls": ["https://example.com"]},
        stage0_overrides={"product_customizable": True},
    )
    assert stage0.price == "TBD"


def test_translate_stage1_uses_structured_category_niche() -> None:
    stage0 = translate_stage0(
        product_name="Honest Herbalist Handbook",
        product_description="Digital herbal safety guide.",
        onboarding_payload={"competitor_urls": ["https://example.com"]},
        stage0_overrides={"product_customizable": True, "price": "$49"},
    )
    precanon_research = {
        "category_niche": "Health & Wellness",
        "step_contents": {
            "01": "Validated competitors: 3",
            "02": (
                '{"compliance_landscape":{"overall":{"red_pct":0.12,"yellow_pct":0.34}},'
                '"competitors":[{"name":"Competitor A"}]}'
            ),
            "06": (
                "1. Busy home herbal caregivers\n"
                "2. Families researching non-pharma options\n"
                "3. Skeptics needing sourcing transparency\n"
                "Bottleneck: confidence in dosage decisions\n"
            ),
        },
    }
    stage1 = translate_stage1(stage0=stage0, precanon_research=precanon_research)
    assert stage1.category_niche == "Health & Wellness"
    assert stage1.competitor_count_validated == 3


def test_translate_stage1_merges_competitor_urls_from_step1_content() -> None:
    stage0 = translate_stage0(
        product_name="Honest Herbalist Handbook",
        product_description="Digital herbal safety guide.",
        onboarding_payload={"competitor_urls": ["https://seed.example/one"]},
        stage0_overrides={"product_customizable": True, "price": "$49"},
    )
    precanon_research = {
        "step_contents": {
            "01": (
                "Category / Niche: Herbal Remedies\n"
                "Validated competitors: 3\n"
                "https://competitor-a.example/path\n"
                "https://competitor-b.example/path\n"
                "https://competitor-c.example/path\n"
            ),
            "02": (
                '{"compliance_landscape":{"overall":{"red_pct":0.12,"yellow_pct":0.34}},'
                '"competitors":[{"name":"Competitor A"}]}'
            ),
            "06": (
                "1. Busy home herbal caregivers\n"
                "2. Families researching non-pharma options\n"
                "3. Skeptics needing sourcing transparency\n"
                "Bottleneck: confidence in dosage decisions\n"
            ),
        },
    }

    stage1 = translate_stage1(stage0=stage0, precanon_research=precanon_research)
    assert stage1.competitor_urls == [
        "https://seed.example/one",
        "https://competitor-a.example/path",
        "https://competitor-b.example/path",
        "https://competitor-c.example/path",
    ]


def test_translate_stage1_accepts_primary_challenge_label_for_bottleneck() -> None:
    stage0 = translate_stage0(
        product_name="Honest Herbalist Handbook",
        product_description="Digital herbal safety guide.",
        onboarding_payload={"competitor_urls": ["https://example.com"]},
        stage0_overrides={"product_customizable": True, "price": "$49"},
    )
    precanon_research = {
        "step_contents": {
            "01": "Category / Niche: Herbal Remedies\nValidated competitors: 3",
            "02": (
                '{"compliance_landscape":{"overall":{"red_pct":0.12,"yellow_pct":0.34}},'
                '"competitors":[{"name":"Competitor A"}]}'
            ),
            "06": (
                "1. Busy home herbal caregivers\n"
                "2. Families researching non-pharma options\n"
                "3. Skeptics needing sourcing transparency\n"
                "Primary Challenge: confidence in dosage decisions\n"
            ),
        },
    }
    stage1 = translate_stage1(stage0=stage0, precanon_research=precanon_research)
    assert stage1.bottleneck == "confidence in dosage decisions"


def test_translate_stage1_accepts_primary_segment_statement_for_bottleneck() -> None:
    stage0 = translate_stage0(
        product_name="Honest Herbalist Handbook",
        product_description="Digital herbal safety guide.",
        onboarding_payload={"competitor_urls": ["https://example.com"]},
        stage0_overrides={"product_customizable": True, "price": "$49"},
    )
    precanon_research = {
        "step_contents": {
            "01": "Category / Niche: Herbal Remedies\nValidated competitors: 3",
            "02": (
                '{"compliance_landscape":{"overall":{"red_pct":0.12,"yellow_pct":0.34}},'
                '"competitors":[{"name":"Competitor A"}]}'
            ),
            "06": (
                "1. Busy home herbal caregivers\n"
                "2. Families researching non-pharma options\n"
                "3. Skeptics needing sourcing transparency\n"
                "The PRIMARY SEGMENT is Busy home herbal caregivers. "
                "All downstream prompts should optimize for this segment first.\n"
            ),
        },
    }
    stage1 = translate_stage1(stage0=stage0, precanon_research=precanon_research)
    assert stage1.bottleneck == "Busy home herbal caregivers"


def test_translate_stage1_accepts_bottleneck_segment_label_for_bottleneck() -> None:
    stage0 = translate_stage0(
        product_name="Honest Herbalist Handbook",
        product_description="Digital herbal safety guide.",
        onboarding_payload={"competitor_urls": ["https://example.com"]},
        stage0_overrides={"product_customizable": True, "price": "$49"},
    )
    precanon_research = {
        "step_contents": {
            "01": "Category / Niche: Herbal Remedies\nValidated competitors: 3",
            "02": (
                '{"compliance_landscape":{"overall":{"red_pct":0.12,"yellow_pct":0.34}},'
                '"competitors":[{"name":"Competitor A"}]}'
            ),
            "06": (
                "1. Busy home herbal caregivers\n"
                "2. Families researching non-pharma options\n"
                "3. Skeptics needing sourcing transparency\n"
                "Bottleneck Segment: Busy home herbal caregivers\n"
            ),
        },
    }
    stage1 = translate_stage1(stage0=stage0, precanon_research=precanon_research)
    assert stage1.bottleneck == "Busy home herbal caregivers"


def test_translate_stage1_accepts_inline_primary_segment_label_for_bottleneck() -> None:
    stage0 = translate_stage0(
        product_name="Honest Herbalist Handbook",
        product_description="Digital herbal safety guide.",
        onboarding_payload={"competitor_urls": ["https://example.com"]},
        stage0_overrides={"product_customizable": True, "price": "$49"},
    )
    precanon_research = {
        "step_contents": {
            "01": "Category / Niche: Herbal Remedies\nValidated competitors: 3",
            "02": (
                '{"compliance_landscape":{"overall":{"red_pct":0.12,"yellow_pct":0.34}},'
                '"competitors":[{"name":"Competitor A"}]}'
            ),
            "06": (
                "1. Busy home herbal caregivers\n"
                "2. Families researching non-pharma options\n"
                "3. Skeptics needing sourcing transparency\n"
                "Bounded summary: 5 buyer segments identified. PRIMARY SEGMENT: Busy home herbal caregivers. "
                "Key cross-segment differentiation insight follows.\n"
            ),
        },
    }
    stage1 = translate_stage1(stage0=stage0, precanon_research=precanon_research)
    assert stage1.bottleneck == "Busy home herbal caregivers"


def test_extract_competitor_analysis_and_compliance_sensitivity() -> None:
    analysis = extract_competitor_analysis(_precanon_research_fixture())
    assert "compliance_landscape" in analysis
    sensitivity = derive_compliance_sensitivity(analysis)
    assert sensitivity == "medium"


def test_offer_mapping_and_copy_context_bridge() -> None:
    stage2 = _build_stage2()
    offer_input = map_offer_pipeline_input(
        stage2=stage2,
        selected_angle_payload=_selected_angle_payload(),
        competitor_teardowns="Competitor teardown notes",
        voc_research="Filtered VOC corpus",
        purple_ocean_research="Purple Ocean findings",
        business_model="one-time",
        funnel_position="cold_traffic",
        target_platforms=["Meta", "TikTok"],
        target_regions=["US"],
        existing_proof_assets=["500+ customer testimonials"],
        brand_voice_notes="Clear, specific, anti-hype tone with practical confidence.",
        compliance_sensitivity="medium",
        llm_model="gpt-5.2-2025-12-11",
        max_iterations=2,
        score_threshold=5.5,
    )
    assert offer_input.config.llm_model == "gpt-5.2-2025-12-11"
    assert offer_input.product_brief.name == stage2.product_name
    assert offer_input.product_brief.constraints.compliance_sensitivity == "medium"

    stage3 = _build_stage3()
    matrix = AwarenessAngleMatrix.model_validate(_awareness_matrix_payload())
    copy_context = build_copy_context_files(
        stage3=stage3,
        awareness_angle_matrix=matrix,
        brand_voice_notes="Clear, specific, anti-hype tone with practical confidence.",
        compliance_notes="Avoid disease treatment claims and absolute outcomes.",
        voc_quotes=["I just want to know the right amount safely."],
    )
    assert "Audience + Product" in copy_context.audience_product_markdown
    assert "Awareness-Angle Matrix" in copy_context.awareness_angle_matrix_markdown
    assert "Brand Voice" in copy_context.brand_voice_markdown
    assert "Compliance" in copy_context.compliance_markdown
    assert len(copy_context.mental_models_markdown) > 50


def test_voc_angle_scorer_wrappers() -> None:
    habitat_results = score_habitats(
        [
            {
                "habitat_name": "Herbal Forum",
                "habitat_type": "REDDIT",
                "threads_50_plus": "Y",
                "posts_last_3mo": "Y",
                "recency_ratio": "MAJORITY_RECENT",
                "exact_category": "Y",
                "purchasing_comparing": "Y",
                "personal_usage": "Y",
                "first_person_narratives": "Y",
                "trigger_events": "Y",
                "fear_frustration_shame": "Y",
                "specific_dollar_or_time": "Y",
                "long_detailed_posts": "Y",
                "purchase_intent_density": "MOST",
                "discusses_spending": "Y",
                "recommendation_threads": "Y",
                "relevance_pct": "OVER_50_PCT",
                "competitor_brand_count": "1-3",
                "trend_direction": "HIGHER",
                "membership_trend": "GROWING",
                "post_frequency_trend": "INCREASING",
                "publicly_accessible": "Y",
                "text_based_content": "Y",
                "target_language": "Y",
                "no_rate_limiting": "Y",
            },
            {
                "habitat_name": "Supplement Reviews",
                "habitat_type": "TRUSTPILOT",
                "threads_200_plus": "Y",
                "posts_last_6mo": "Y",
                "recency_ratio": "BALANCED",
                "exact_category": "Y",
                "purchasing_comparing": "Y",
                "personal_usage": "Y",
                "first_person_narratives": "Y",
                "trigger_events": "Y",
                "fear_frustration_shame": "Y",
                "specific_dollar_or_time": "Y",
                "long_detailed_posts": "Y",
                "purchase_intent_density": "SOME",
                "discusses_spending": "Y",
                "recommendation_threads": "Y",
                "relevance_pct": "25_TO_50_PCT",
                "competitor_brand_count": "1-3",
                "trend_direction": "SAME",
                "membership_trend": "STABLE",
                "post_frequency_trend": "SAME",
                "publicly_accessible": "Y",
                "text_based_content": "Y",
                "target_language": "Y",
                "no_rate_limiting": "Y",
            },
        ]
    )
    assert "habitats" in habitat_results

    video_results = score_videos(
        [
            {
                "video_id": "vid-1",
                "platform": "tiktok",
                "views": 200000,
                "followers": 3000,
                "comments": 2500,
                "shares": 800,
                "likes": 12000,
                "days_since_posted": 5,
                "description": "Dosage safety checklist",
                "author": "creator-1",
            },
            {
                "video_id": "vid-2",
                "platform": "youtube",
                "views": 50000,
                "followers": 10000,
                "comments": 300,
                "shares": 100,
                "likes": 5000,
                "days_since_posted": 12,
                "description": "Herbal mistakes",
                "author": "creator-2",
            },
        ]
    )
    assert "videos" in video_results

    voc_results = score_voc_items(
        [
            {
                "voc_id": "V001",
                "specific_number": "Y",
                "specific_product_brand": "Y",
                "specific_event_moment": "Y",
                "specific_body_symptom": "Y",
                "before_after_comparison": "Y",
                "crisis_language": "Y",
                "profanity_extreme_punctuation": "N",
                "physical_sensation": "Y",
                "identity_change_desire": "Y",
                "word_count": 120,
                "clear_trigger_event": "Y",
                "named_enemy": "Y",
                "shiftable_belief": "Y",
                "expectation_vs_reality": "Y",
                "headline_ready": "Y",
                "usable_content_pct": "OVER_75_PCT",
                "personal_context": "Y",
                "long_narrative": "Y",
                "engagement_received": "Y",
                "real_person_signals": "Y",
                "moderated_community": "Y",
                "trigger_event": "new symptom",
                "pain_problem": "dose uncertainty",
                "desired_outcome": "safe dosing",
                "failed_prior_solution": "generic guide",
                "enemy_blame": "generic advice",
                "identity_role": "caregiver",
                "fear_risk": "interaction risk",
                "emotional_valence": "ANXIETY",
                "durable_psychology": "Y",
                "market_specific": "N",
                "date_bracket": "LAST_6MO",
                "buyer_stage": "PROBLEM_AWARE",
                "solution_sophistication": "EXPERIENCED",
                "compliance_risk": "YELLOW",
            },
            {
                "voc_id": "V002",
                "specific_number": "N",
                "specific_product_brand": "Y",
                "specific_event_moment": "Y",
                "specific_body_symptom": "N",
                "before_after_comparison": "N",
                "crisis_language": "N",
                "profanity_extreme_punctuation": "N",
                "physical_sensation": "N",
                "identity_change_desire": "Y",
                "word_count": 70,
                "clear_trigger_event": "Y",
                "named_enemy": "N",
                "shiftable_belief": "Y",
                "expectation_vs_reality": "N",
                "headline_ready": "Y",
                "usable_content_pct": "50_TO_75_PCT",
                "personal_context": "Y",
                "long_narrative": "N",
                "engagement_received": "Y",
                "real_person_signals": "Y",
                "moderated_community": "Y",
                "trigger_event": "conflicting advice",
                "pain_problem": "uncertainty",
                "desired_outcome": "clarity",
                "failed_prior_solution": "search results",
                "enemy_blame": "conflicting experts",
                "identity_role": "parent",
                "fear_risk": "making mistakes",
                "emotional_valence": "FRUSTRATION",
                "durable_psychology": "Y",
                "market_specific": "N",
                "date_bracket": "LAST_12MO",
                "buyer_stage": "PROBLEM_AWARE",
                "solution_sophistication": "EXPERIENCED",
                "compliance_risk": "GREEN",
            },
        ]
    )
    assert "items" in voc_results

    angle_results = score_angles(
        [
            {
                "angle_id": "A01",
                "angle_name": "The Dosage Gap",
                "distinct_voc_items": 15,
                "distinct_authors": 12,
                "intensity_spike_count": 5,
                "sleeping_giant_count": 3,
                "aspiration_gap_4plus": "Y",
                "avg_adjusted_score": 66,
                "crisis_language_count": 5,
                "dollar_time_loss_count": 3,
                "physical_symptom_count": 6,
                "rage_shame_anxiety_count": 9,
                "exhausted_sophistication_count": 4,
                "sa0_different_who": "Y",
                "sa0_different_trigger": "Y",
                "sa0_different_enemy": "Y",
                "sa0_different_belief": "Y",
                "sa0_different_mechanism": "N",
                "product_addresses_pain": "Y",
                "product_feature_maps_to_mechanism": "Y",
                "outcome_achievable": "Y",
                "mechanism_factually_supportable": "Y",
                "supporting_voc_count": 12,
                "items_above_60": 8,
                "contradiction_count": 1,
                "triangulation_status": "DUAL",
                "source_habitat_types": 3,
                "dominant_source_pct": 45,
                "green_count": 10,
                "yellow_count": 3,
                "red_count": 1,
                "expressible_without_red": "Y",
                "requires_disease_naming": "N",
                "velocity_status": "STEADY",
                "stage_UNAWARE_count": 1,
                "stage_PROBLEM_AWARE_count": 7,
                "stage_SOLUTION_AWARE_count": 4,
                "stage_PRODUCT_AWARE_count": 2,
                "stage_MOST_AWARE_count": 1,
                "pain_chronicity": "CHRONIC",
                "trigger_seasonality": "ONGOING",
                "competitor_count_using_angle": "1-2",
                "recent_competitor_entry": "Y",
                "pain_structural": "Y",
                "news_cycle_dependent": "N",
                "competitor_behavior_dependent": "N",
                "single_visual_expressible": "Y",
                "hook_under_12_words": "Y",
                "natural_villain_present": "Y",
                "language_registry_headline_exists": "Y",
                "segment_breadth": "MODERATE",
                "pain_universality": "MODERATE",
            }
        ],
        saturated_count=1,
    )
    assert "angles" in angle_results


def test_offer_and_copy_scorer_wrappers() -> None:
    calibration = calibration_consistency_checker(
        {
            "awareness_level": {"assessment": "problem-aware"},
            "sophistication_level": {"assessment": "high"},
            "lifecycle_stage": {"assessment": "growth"},
            "competitor_count": 6,
        }
    )
    assert calibration["passed"] is True

    ranked = ump_ums_scorer(
        [
            {
                "pair_id": "pair-1",
                "ump_name": "Problem Mechanism",
                "ums_name": "Solution Mechanism",
                "dimensions": {
                    "competitive_uniqueness": {"score": 8, "evidence_quality": "OBSERVED"},
                    "voc_groundedness": {"score": 8, "evidence_quality": "OBSERVED"},
                    "believability": {"score": 7, "evidence_quality": "INFERRED"},
                    "mechanism_clarity": {"score": 8, "evidence_quality": "INFERRED"},
                    "angle_alignment": {"score": 9, "evidence_quality": "OBSERVED"},
                    "compliance_safety": {"score": 8, "evidence_quality": "OBSERVED"},
                    "memorability": {"score": 7, "evidence_quality": "INFERRED"},
                },
            }
        ]
    )
    assert ranked["total_pairs"] == 1

    headline_result = score_headline(
        "Most Herb Guides Skip the One Dosing Detail Families Need",
        page_type="advertorial",
    )
    assert "composite" in headline_result

    body_text = (
        "1. The dosing detail most guides skip\n"
        "Families read ingredient lists but miss dosage context.\n"
        "2. Why this creates avoidable safety anxiety\n"
        "People fear interactions and guess amounts at home.\n"
        "3. What practical dosage confidence looks like\n"
        "A clear protocol reduces confusion and supports safer decisions.\n"
    )
    page_data = build_page_data_from_body_text(body_text)
    contract = {
        "loop_question": "How can families dose with confidence?",
        "specific_promise": "The page explains practical dosage context for safer decisions.",
        "delivery_test": "The body must contain dosage safety context",
        "minimum_delivery": "Begin in section 1.",
    }
    congruency = score_congruency_extended(
        headline="Most Herb Guides Skip the One Dosing Detail Families Need",
        page_data=page_data,
        promise_contract=contract,
    )
    assert "composite" in congruency


def test_build_page_data_from_advertorial_markdown_sections() -> None:
    body_text = (
        "# The Hidden Herbal Safety Gap\n\n"
        "## Problem Setup\n"
        "Most buyers struggle with contradictory dosage advice.\n\n"
        "## Mechanism Shift\n"
        "Interaction-aware guidance creates safer decisions.\n"
    )
    page_data = build_page_data_from_body_text(body_text, page_type="advertorial")
    assert page_data["section_titles"] == ["Problem Setup", "Mechanism Shift"]
    assert isinstance(page_data["sections"], list)
    assert len(page_data["sections"]) == 2


def test_qa_loop_wrapper_requires_explicit_api_key() -> None:
    with pytest.raises(StrategyV2ScorerError):
        run_headline_qa_loop(
            headline="Most Herb Guides Skip the One Dosing Detail Families Need",
            page_type="advertorial",
            max_iterations=2,
            min_tier="A",
            api_key="",
            model="claude-sonnet-4-20250514",
        )


def test_qa_loop_wrapper_normalizes_blank_anthropic_base_urls(monkeypatch) -> None:
    seen_env: dict[str, str | None] = {}

    def _fake_run_qa_loop(*_args, **_kwargs):
        seen_env["ANTHROPIC_BASE_URL"] = os.getenv("ANTHROPIC_BASE_URL")
        seen_env["ANTHROPIC_API_BASE_URL"] = os.getenv("ANTHROPIC_API_BASE_URL")
        return {"status": "PASS", "best_headline": "Fixed headline"}

    fake_module = SimpleNamespace(
        run_qa_loop=_fake_run_qa_loop,
        to_json=lambda raw: raw,
    )

    monkeypatch.setattr(scorer_module, "_load_module", lambda *_args, **_kwargs: fake_module)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "")
    monkeypatch.setenv("ANTHROPIC_API_BASE_URL", "")

    result = run_headline_qa_loop(
        headline="Most Herb Guides Skip the One Dosing Detail Families Need",
        page_type="advertorial",
        max_iterations=2,
        min_tier="A",
        api_key="test-api-key",
        model="claude-sonnet-4-20250514",
    )

    assert seen_env["ANTHROPIC_BASE_URL"] is None
    assert seen_env["ANTHROPIC_API_BASE_URL"] is None
    assert result["json"]["status"] == "PASS"


def test_qa_loop_wrapper_retries_transient_overload(monkeypatch) -> None:
    calls = {"count": 0}

    def _fake_run_qa_loop(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            print("  WARNING: LLM call failed: Error code: 529 - overloaded_error req_abc123")
            return {"status": "FAIL", "best_headline": "Draft", "total_iterations": 1}
        print("  INFO: retry succeeded req_def456")
        return {"status": "PASS", "best_headline": "Recovered headline", "total_iterations": 2}

    fake_module = SimpleNamespace(
        run_qa_loop=_fake_run_qa_loop,
        to_json=lambda raw: raw,
    )

    monkeypatch.setattr(scorer_module, "_load_module", lambda *_args, **_kwargs: fake_module)
    monkeypatch.setattr(scorer_module, "_HEADLINE_QA_TRANSIENT_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(scorer_module, "_HEADLINE_QA_TRANSIENT_RETRY_BASE_SECONDS", 0.0)

    result = run_headline_qa_loop(
        headline="Most Herb Guides Skip the One Dosing Detail Families Need",
        page_type="advertorial",
        max_iterations=2,
        min_tier="A",
        api_key="test-api-key",
        model="claude-sonnet-4-20250514",
    )

    diagnostics = result["diagnostics"]
    assert calls["count"] == 2
    assert result["json"]["status"] == "PASS"
    assert diagnostics["attempt_count"] == 2
    assert diagnostics["model"] == "claude-sonnet-4-20250514"
    assert diagnostics["max_iterations"] == 2
    assert diagnostics["min_tier"] == "A"
    assert diagnostics["call_timeout_seconds"] == 0.0
    assert diagnostics["call_max_retries"] == 0
    assert diagnostics["overloaded_error_count"] == 1
    assert diagnostics["warning_count"] == 1
    assert diagnostics["request_ids"] == ["req_abc123", "req_def456"]


def test_qa_loop_wrapper_collects_request_ids_from_result_metadata(monkeypatch) -> None:
    def _fake_run_qa_loop(*_args, **_kwargs):
        return {
            "status": "PASS",
            "best_headline": "Recovered headline",
            "total_iterations": 1,
            "request_ids": ["req_meta001", "req_meta002"],
        }

    def _fake_to_json(raw):
        return {
            "status": raw["status"],
            "best_headline": raw["best_headline"],
            "total_iterations": raw["total_iterations"],
            "metadata": {
                "request_ids": raw["request_ids"],
            },
        }

    fake_module = SimpleNamespace(
        run_qa_loop=_fake_run_qa_loop,
        to_json=_fake_to_json,
    )

    monkeypatch.setattr(scorer_module, "_load_module", lambda *_args, **_kwargs: fake_module)
    result = run_headline_qa_loop(
        headline="Most Herb Guides Skip the One Dosing Detail Families Need",
        page_type="advertorial",
        max_iterations=2,
        min_tier="A",
        api_key="test-api-key",
        model="claude-sonnet-4-20250514",
    )

    diagnostics = result["diagnostics"]
    assert diagnostics["request_ids"] == ["req_meta001", "req_meta002"]
    assert diagnostics["attempts"][0]["request_ids"] == ["req_meta001", "req_meta002"]


def test_qa_loop_wrapper_does_not_retry_without_overload_signal(monkeypatch) -> None:
    calls = {"count": 0}

    def _fake_run_qa_loop(*_args, **_kwargs):
        calls["count"] += 1
        print("  WARNING: LLM call failed: response parse error")
        return {"status": "FAIL", "best_headline": "Draft", "total_iterations": 1}

    fake_module = SimpleNamespace(
        run_qa_loop=_fake_run_qa_loop,
        to_json=lambda raw: raw,
    )

    monkeypatch.setattr(scorer_module, "_load_module", lambda *_args, **_kwargs: fake_module)
    monkeypatch.setattr(scorer_module, "_HEADLINE_QA_TRANSIENT_RETRY_ATTEMPTS", 3)
    monkeypatch.setattr(scorer_module, "_HEADLINE_QA_TRANSIENT_RETRY_BASE_SECONDS", 0.0)

    result = run_headline_qa_loop(
        headline="Most Herb Guides Skip the One Dosing Detail Families Need",
        page_type="advertorial",
        max_iterations=2,
        min_tier="A",
        api_key="test-api-key",
        model="claude-sonnet-4-20250514",
    )

    diagnostics = result["diagnostics"]
    assert calls["count"] == 1
    assert result["json"]["status"] == "FAIL"
    assert diagnostics["attempt_count"] == 1
    assert diagnostics["overloaded_error_count"] == 0
    assert diagnostics["warning_count"] == 1


def test_qa_loop_wrapper_retries_transient_timeout(monkeypatch) -> None:
    calls = {"count": 0}

    def _fake_run_qa_loop(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            print("  WARNING: LLM call failed: request timed out")
            return {"status": "FAIL", "best_headline": "Draft", "total_iterations": 1}
        return {"status": "PASS", "best_headline": "Recovered headline", "total_iterations": 2}

    fake_module = SimpleNamespace(
        run_qa_loop=_fake_run_qa_loop,
        to_json=lambda raw: raw,
    )

    monkeypatch.setattr(scorer_module, "_load_module", lambda *_args, **_kwargs: fake_module)
    monkeypatch.setattr(scorer_module, "_HEADLINE_QA_TRANSIENT_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(scorer_module, "_HEADLINE_QA_TRANSIENT_RETRY_BASE_SECONDS", 0.0)

    result = run_headline_qa_loop(
        headline="Most Herb Guides Skip the One Dosing Detail Families Need",
        page_type="advertorial",
        max_iterations=2,
        min_tier="A",
        api_key="test-api-key",
        model="claude-sonnet-4-20250514",
    )

    diagnostics = result["diagnostics"]
    assert calls["count"] == 2
    assert result["json"]["status"] == "PASS"
    assert diagnostics["attempt_count"] == 2
    assert diagnostics["timeout_error_count"] == 1
