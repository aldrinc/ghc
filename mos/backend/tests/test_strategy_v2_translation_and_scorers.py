from __future__ import annotations

import json
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


def test_translate_stage1_requires_concrete_price() -> None:
    stage0 = translate_stage0(
        product_name="Honest Herbalist Handbook",
        product_description="Digital herbal safety guide.",
        onboarding_payload={"competitor_urls": ["https://seed.example/one"]},
        stage0_overrides={"product_customizable": True},
    )

    with pytest.raises(StrategyV2MissingContextError, match="Stage 1 translation requires a concrete price"):
        translate_stage1(stage0=stage0, precanon_research=_precanon_research_fixture())


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


def test_translate_stage1_uses_primary_segment_statement_to_select_primary_segment_profile() -> None:
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
            "04": "Bottleneck: confidence in dosage decisions\n",
            "06": (
                "### Segment A\n"
                "- Segment Name: Busy home herbal caregivers\n"
                "- Estimated Prevalence: Common among daily supplement buyers\n"
                "- Key Differentiator: They want simple and repeatable routines\n"
                "\n"
                "### Segment B\n"
                "- Segment Name: Families researching non-pharma options\n"
                "- Estimated Prevalence: Smaller but highly motivated cohort\n"
                "- Key Differentiator: They compare ingredient sourcing across brands\n"
                "\n"
                "### Segment C\n"
                "- Segment Name: Skeptics needing sourcing transparency\n"
                "- Estimated Prevalence: Narrow but high-intent segment\n"
                "- Key Differentiator: They need proof before trusting claims\n"
                "\n"
                "The PRIMARY SEGMENT is Segment B: Families researching non-pharma options.\n"
            ),
        },
    }
    stage1 = translate_stage1(stage0=stage0, precanon_research=precanon_research)
    assert stage1.primary_segment.name == "Families researching non-pharma options"
    assert stage1.primary_segment.size_estimate == "Smaller but highly motivated cohort"
    assert stage1.primary_segment.key_differentiator == "They compare ingredient sourcing across brands"
    assert stage1.bottleneck == "confidence in dosage decisions"


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


def test_translate_stage1_requires_explicit_bottleneck_when_only_primary_segment_statement_is_present() -> None:
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
    with pytest.raises(StrategyV2MissingContextError, match="requires a non-empty bottleneck"):
        translate_stage1(stage0=stage0, precanon_research=precanon_research)


def test_translate_stage1_filters_citation_urls_and_parses_segment_blocks_from_foundational_docs() -> None:
    stage0 = translate_stage0(
        product_name="Ember: Brain Clarity Protocol",
        product_description="Creatine gummies designed for perimenopausal women.",
        onboarding_payload={},
        stage0_overrides={"product_customizable": False, "price": "$40"},
    )
    precanon_research = {
        "step_contents": {
            "01": (
                "Category / Niche: Supplements for women age 42-58\n"
                "### Validated competitors (13)\n"
                "- Ember Wellness https://emberwellness.example/products/brain-clarity "
                "https://www.similarweb.com/website/emberwellness.example\n"
                "- MenoLabs https://menolabs.example/products/memory-support "
                "https://www.trustpilot.com/review/menolabs.example\n"
                "- Clarity Keeper https://claritykeeper.example/protocol https://reference.example/brain-fog.pdf\n"
                "- Press mention https://www.prnewswire.com/news-releases/ember-brain-clarity.html\n"
                "Introduction calls are common during customer onboarding.\n"
            ),
            "02": (
                '{"compliance_landscape":{"overall":{"red_pct":0.12,"yellow_pct":0.34}},'
                '"competitors":[{"name":"Competitor A"}]}'
            ),
            "04": "#1 Bottleneck to Solve: fear of losing credibility at work when brain fog shows up\n",
            "06": (
                "### Segment A\n"
                "- Segment Name: Credibility-on-the-line Knowledge Worker\n"
                "- Estimated Prevalence: Dominant in the live VOC corpus across professional women 42-58\n"
                "- Key Differentiator: Their urgency spikes when verbal fluency slips threaten visible competence\n"
                "\n"
                "### Segment B\n"
                "- Segment Name: Exhausted Midlife Caregiver\n"
                "- Estimated Prevalence: Secondary segment with recurring family-management overload\n"
                "- Key Differentiator: They need a format that fits fragmented routines\n"
                "\n"
                "### Segment C\n"
                "- Segment Name: Prevention-Oriented Optimizer\n"
                "- Estimated Prevalence: Smaller but premium-leaning early adopter segment\n"
                "- Key Differentiator: They respond to proactive performance framing and regimen precision\n"
                "\n"
                "The PRIMARY SEGMENT is Segment A: Credibility-on-the-line Knowledge Worker.\n"
            ),
        }
    }

    stage1 = translate_stage1(stage0=stage0, precanon_research=precanon_research)

    assert stage1.competitor_count_validated == 13
    assert stage1.competitor_urls == [
        "https://emberwellness.example/products/brain-clarity",
        "https://menolabs.example/products/memory-support",
        "https://claritykeeper.example/protocol",
    ]
    assert stage1.market_maturity_stage is None
    assert stage1.primary_icps == [
        "Credibility-on-the-line Knowledge Worker",
        "Exhausted Midlife Caregiver",
        "Prevention-Oriented Optimizer",
    ]
    assert stage1.primary_segment.name == "Credibility-on-the-line Knowledge Worker"
    assert stage1.primary_segment.size_estimate == "Dominant in the live VOC corpus across professional women 42-58"
    assert (
        stage1.primary_segment.key_differentiator
        == "Their urgency spikes when verbal fluency slips threaten visible competence"
    )
    assert stage1.bottleneck == "fear of losing credibility at work when brain fog shows up"


def test_translate_stage1_uses_primary_segment_key_differentiator_when_bottleneck_label_is_missing() -> None:
    stage0 = translate_stage0(
        product_name="Ember: Brain Clarity Protocol",
        product_description="Creatine gummies designed for perimenopausal women.",
        onboarding_payload={},
        stage0_overrides={"product_customizable": False, "price": "$40"},
    )
    precanon_research = {
        "step_contents": {
            "01": "Category / Niche: Supplements for women age 42-58\nValidated competitors (3)\n",
            "02": (
                '{"compliance_landscape":{"overall":{"red_pct":0.12,"yellow_pct":0.34}},'
                '"competitors":[{"name":"Competitor A"}]}'
            ),
            "06": (
                "### Step 3: Named & bounded segments (3-5)\n"
                "1) Credibility-on-the-line Knowledge Worker\n"
                "2) Hormone-Restricted Relief Seeker\n"
                "3) Evidence-First Protocol Optimizer\n"
                "\n"
                "# Segment A - Credibility-on-the-line Knowledge Worker\n"
                "## A. Segment Identity\n"
                "Segment Name: Credibility-on-the-line Knowledge Worker\n"
                "Estimated Prevalence: Large cluster in the live VOC set\n"
                "Key Differentiator: Their primary pain is public and professional competence loss\n"
                "\n"
                "# Segment B - Hormone-Restricted Relief Seeker\n"
                "## A. Segment Identity\n"
                "Segment Name: Hormone-Restricted Relief Seeker\n"
                "Estimated Prevalence: Secondary but recurring cluster\n"
                "Key Differentiator: They need clear non-hormonal safety framing\n"
                "\n"
                "# Segment C - Evidence-First Protocol Optimizer\n"
                "## A. Segment Identity\n"
                "Segment Name: Evidence-First Protocol Optimizer\n"
                "Estimated Prevalence: Smaller high-information cluster\n"
                "Key Differentiator: They demand dose transparency and proof before trying anything\n"
                "\n"
                "The PRIMARY SEGMENT is Segment A: Credibility-on-the-line Knowledge Worker.\n"
            ),
        }
    }

    stage1 = translate_stage1(stage0=stage0, precanon_research=precanon_research)

    assert stage1.primary_segment.name == "Credibility-on-the-line Knowledge Worker"
    assert stage1.bottleneck == "Their primary pain is public and professional competence loss"


def test_translate_stage1_extracts_identity_threat_cluster_label_as_bottleneck() -> None:
    stage0 = translate_stage0(
        product_name="Ember: Brain Clarity Protocol",
        product_description="Creatine gummies designed for perimenopausal women.",
        onboarding_payload={},
        stage0_overrides={"product_customizable": False, "price": "$40"},
    )
    precanon_research = {
        "step_contents": {
            "01": "Category / Niche: Supplements for women age 42-58\nValidated competitors (3)\n",
            "02": (
                '{"compliance_landscape":{"overall":{"red_pct":0.12,"yellow_pct":0.34}},'
                '"competitors":[{"name":"Competitor A"}]}'
            ),
            "06": (
                "1. Career-load women managing visible cognitive pressure\n"
                "2. Exhausted caregivers juggling home and symptom load\n"
                "3. Prevention-oriented optimizers seeking regimen precision\n"
                "\n"
                "## Phase 1: Segment Discovery\n"
                "### Step 1: Distinct buyer signals (VOC-grounded clusters)\n"
                "**Identity-threat clusters**\n"
                "- Career competence threat / workplace humiliation: "
                "“brain fog… I miss details constantly”; “50-something female in tech”\n"
            ),
        }
    }

    stage1 = translate_stage1(stage0=stage0, precanon_research=precanon_research)

    assert stage1.bottleneck == "Career competence threat / workplace humiliation"


def test_translate_stage1_extracts_numbered_distress_cluster_label_as_bottleneck() -> None:
    stage0 = translate_stage0(
        product_name="Ember: Brain Clarity Protocol",
        product_description="Creatine gummies designed for perimenopausal women.",
        onboarding_payload={},
        stage0_overrides={"product_customizable": False, "price": "$40"},
    )
    precanon_research = {
        "step_contents": {
            "01": "Category / Niche: Supplements for women age 42-58\nValidated competitors (3)\n",
            "02": (
                '{"compliance_landscape":{"overall":{"red_pct":0.12,"yellow_pct":0.34}},'
                '"competitors":[{"name":"Competitor A"}]}'
            ),
            "06": (
                "## Phase 1 — Segment Discovery\n"
                "### Step 1: Distinct buyer signals (clusters found in VOC)\n"
                "1) **Work-performance shame + word-finding failures**\n"
                "- \"I lose the thread mid-sentence in meetings\"\n"
                "2) Symptom-stack overwhelm during caregiving hours\n"
                "- \"Everything hits at once by 4pm\"\n"
                "3) Prevention-minded protocol optimizers\n"
                "- \"I want to stay sharp before it gets worse\"\n"
            ),
        }
    }

    stage1 = translate_stage1(stage0=stage0, precanon_research=precanon_research)

    assert stage1.bottleneck == "Work-performance shame + word-finding failures"


def test_translate_stage1_derives_competitor_domains_from_validated_reference_blocks() -> None:
    stage0 = translate_stage0(
        product_name="Ember: Brain Clarity Protocol",
        product_description="Creatine gummies designed for perimenopausal women.",
        onboarding_payload={},
        stage0_overrides={"product_customizable": False, "price": "$40"},
    )
    precanon_research = {
        "step_contents": {
            "01": (
                "Category / Niche: Supplements for women age 42-58\n"
                "### Validated competitors (3)\n"
                "1) **O Positiv** - passes bar\n"
                "- Similarweb: 2.6M visits. "
                "([similarweb.com](https://www.similarweb.com/website/opositiv.com/))\n"
                "2) **Happy Mammoth** - passes bar\n"
                "- Trustpilot: 12,348 reviews. "
                "([trustpilot.com](https://www.trustpilot.com/review/happymammoth.com))\n"
                "3) **Bonafide (hellobonafide.com)** - passes bar\n"
                "- Retail expansion press release indicates Target distribution. "
                "([bankingpressreleases.com](https://bankingpressreleases.com/article/846036254-bonafide-health-announces-expansion))\n"
            ),
            "02": (
                '{"compliance_landscape":{"overall":{"red_pct":0.12,"yellow_pct":0.34}},'
                '"competitors":[{"name":"Competitor A"}]}'
            ),
            "04": "Bottleneck: fear of losing credibility when brain fog shows up at work\n",
            "06": (
                "# Segment A - Credibility-on-the-line Knowledge Worker\n"
                "Segment Name: Credibility-on-the-line Knowledge Worker\n"
                "Estimated Prevalence: Large cluster in the live VOC set\n"
                "Key Differentiator: Their primary pain is public and professional competence loss\n"
                "\n"
                "# Segment B - Hormone-Restricted Relief Seeker\n"
                "Segment Name: Hormone-Restricted Relief Seeker\n"
                "Estimated Prevalence: Secondary but recurring cluster\n"
                "Key Differentiator: They need clear non-hormonal safety framing\n"
                "\n"
                "# Segment C - Evidence-First Protocol Optimizer\n"
                "Segment Name: Evidence-First Protocol Optimizer\n"
                "Estimated Prevalence: Smaller high-information cluster\n"
                "Key Differentiator: They demand dose transparency and proof before trying anything\n"
                "\n"
                "The PRIMARY SEGMENT is Segment A: Credibility-on-the-line Knowledge Worker.\n"
            ),
        }
    }

    stage1 = translate_stage1(stage0=stage0, precanon_research=precanon_research)

    assert stage1.competitor_urls == [
        "https://opositiv.com/",
        "https://happymammoth.com/",
        "https://hellobonafide.com/",
    ]


def test_translate_stage1_unwraps_wrapped_foundational_payloads_and_keeps_validated_competitors_clean() -> None:
    stage0 = translate_stage0(
        product_name="Ember: Brain Clarity Protocol",
        product_description="Creatine gummies designed for perimenopausal women.",
        onboarding_payload={},
        stage0_overrides={"product_customizable": False, "price": "$40"},
    )
    step01 = json.dumps(
        {
            "source": "precanon_research.step_contents",
            "content": (
                "## Phase 2: Discover Competitors (Direct + Adjacent)\n"
                "| Candidate | URL | Type | Notes |\n"
                "|---|---:|---|---|\n"
                "| O Positiv | `https://opositivcare.com/` | Direct | Menopause supplement brand |\n"
                "| Bonafide | `https://hellobonafide.com/` | Direct | Women's health nutraceuticals |\n"
                "| Happy Mammoth | `https://happymammoths.us/products/hormone-harmony` | Direct | Hormone Harmony product |\n"
                "| Estroven | `https://estroven.com/` | Direct | Menopause relief brand |\n"
                "| Perelel | `https://perelelhealth.com/` | Adjacent | Perimenopause pack |\n"
                "| MenoLabs | `https://menolabs.com/` | Direct | Tracker app plus supplements |\n"
                "| Amberen | `https://amberen.com/products/amberen-advanced-menopause-relief-capsules-3-month-supply` | Direct | Menopause relief product |\n"
                "| MaryRuth Organics | `https://www.maryruthorganics.com/products/organic-menopause-gummies` | Adjacent | Dedicated menopause gummies |\n"
                "| Life Extension | `https://www.lifeextension.com/` | Adjacent | Large supplement incumbent |\n"
                "\n"
                "## Phase 3: Validate Battle-Tested Competitors\n"
                "### Validated set (9)\n"
                "1) **Life Extension** (`lifeextension.com`)\n"
                "- Traffic: ~1.04M visits. ([semrush.com](https://www.semrush.com/website/lifeextension.com/overview/?source=trending-websites&utm_source=openai))\n"
                "- Content authority: monthly magazine. ([lifeextension.com](https://www.lifeextension.com/about/media-press-pass?utm_source=openai))\n"
                "2) **Happy Mammoth**\n"
                "- Traffic: 1,535,938 monthly web visits via Crunchbase. ([crunchbase.com](https://www.crunchbase.com/organization/happy-mammoth?utm_source=openai))\n"
                "3) **MaryRuth Organics**\n"
                "- Traffic: 2,284,920 monthly web visits via Crunchbase. ([crunchbase.com](https://www.crunchbase.com/organization/maryruth-organics?utm_source=openai))\n"
                "- Market presence: Target distribution. ([maryruthorganics.com](https://www.maryruthorganics.com/blogs/press-and-news/maryruth-s-products-for-infants-now-available-in-almost-2-000-target-stores?utm_source=openai))\n"
                "4) **Estroven**\n"
                "- Longevity: first produced in 1997. ([en.wikipedia.org](https://en.wikipedia.org/wiki/Amerifit_Brands?utm_source=openai))\n"
                "5) **O Positiv**\n"
                "- Traffic: 994,892 monthly web visits via Crunchbase. ([crunchbase.com](https://www.crunchbase.com/organization/flo-vitamins?utm_source=openai))\n"
                "- Market penetration: verified reviews on the homepage. ([opositivcare.com](https://opositivcare.com/?utm_source=openai))\n"
                "6) **Bonafide Health**\n"
                "- Traffic: 211.33K visits. ([semrush.com](https://www.semrush.com/website/hellobonafide.com/overview/))\n"
                "- Retail expansion: 1,800+ Target stores. ([crunchbase.com](https://www.crunchbase.com/organization/jds-therapeutics-llc-the-parent-company-of-bonafide-and-nutrition-21?utm_source=openai))\n"
                "7) **Perelel**\n"
                "- Funding: $27M round. ([beautyindependent.com](https://www.beautyindependent.com/prelude-growth-leads-27m-round-perelel-womens-wellness-heats-up/?utm_source=openai))\n"
                "8) **MenoLabs**\n"
                "- Company maturity: acquired by Amyris. ([crunchbase.com](https://www.crunchbase.com/organization/menolabs/company_financials?utm_source=openai))\n"
                "9) **Amberen (Biogix / Alliance Pharma acquisition mentioned in market report)**\n"
                "- Market transaction: Alliance Pharma acquired Biogix. ([pswordpress-production.s3.amazonaws.com](https://pswordpress-production.s3.amazonaws.com/2023/11/Menopause_The-600-Billion-Opportunity-in-Femtech_PreScouter-2023.pdf?utm_source=openai))\n"
                "- Brand site indicates it is active. ([amberen.com](https://amberen.com/products/amberen-advanced-menopause-relief-capsules-3-month-supply?utm_source=openai))\n"
                "\n"
                "## Phase 8: Market Maturity Assessment\n"
                "### Product lifecycle stage: **Maturity (with ongoing innovation/line extensions)**\n"
            ),
            "bounded_summary": "Validated competitors (battle-tested with non-trivial traction evidence): 9.",
            "foundational_step_key": "01",
        }
    )
    step04 = json.dumps(
        {
            "source": "precanon_research.step_contents",
            "content": (
                "## D) Victories, Failures, Complaints & Frustrations\n"
                "- Failures people report: nothing changed, side effects, or they quit early.\n"
                "\n"
                "## Bottleneck Identification\n"
                '- #1 unresolved pain/unmet need: "I need my brain back" (focus + word recall + mental energy) in a way that is reliable, non-hormone-required, and does not add new problems.\n'
            ),
            "bounded_summary": "#1 bottleneck: a trustworthy, repeatable, hormone-optional cognitive solution.",
            "foundational_step_key": "04",
        }
    )
    step06 = json.dumps(
        {
            "source": "precanon_research.step_contents",
            "content": (
                "## Phase 1 - Segment Discovery\n"
                "### Step 3: Segment names & bounds (3-5)\n"
                "1) Workplace Edge Protectors - protect professional competence and verbal fluency.\n"
                "2) ADHD-Peri System Crashers - peri turns ADHD from manageable to unmanageable.\n"
                "3) Evidence-Hawk Supplement Skeptics - demand dosing and proof.\n"
                "4) Format Friction Strugglers - adherence is the top problem.\n"
                "5) Side-Effect Sentinels - high sensitivity to bloat, palpitations, and hair loss fears.\n"
                "\n"
                "## Segment 1: Workplace Edge Protectors\n"
                "- Segment Name: Workplace Edge Protectors\n"
                "- Estimated Prevalence: 25% of the live VOC set\n"
                "- Key Differentiator: Primary pain is public competence loss\n"
                "\n"
                "## Segment 2: ADHD-Peri System Crashers\n"
                "- Segment Name: ADHD-Peri System Crashers\n"
                "- Estimated Prevalence: Secondary but intense segment\n"
                "- Key Differentiator: Their coping systems suddenly stop working\n"
                "\n"
                "## Segment 3: Evidence-Hawk Supplement Skeptics\n"
                "- Segment Name: Evidence-Hawk Supplement Skeptics\n"
                "- Estimated Prevalence: Large skeptical cluster\n"
                "- Key Differentiator: They demand proof before trusting claims\n"
                "\n"
                "## Segment 4: Format Friction Strugglers\n"
                "- Segment Name: Format Friction Strugglers\n"
                "- Estimated Prevalence: Medium-sized adherence-driven cluster\n"
                "- Key Differentiator: They want a format they will actually take\n"
                "\n"
                "## Segment 5: Side-Effect Sentinels\n"
                "- Segment Name: Side-Effect Sentinels\n"
                "- Estimated Prevalence: Smaller but high-anxiety cluster\n"
                "- Key Differentiator: Safety and tolerability beat outcomes-first copy\n"
                "\n"
                'The PRIMARY SEGMENT is "Workplace Edge Protectors."\n'
            ),
            "bounded_summary": "Bounded summary: 5 distinct buyer segments identified. PRIMARY SEGMENT: Workplace Edge Protectors.",
            "foundational_step_key": "06",
        }
    )
    precanon_research = {
        "category_niche": "Supplements for women age 42-58",
        "step_contents": {
            "01": step01,
            "02": (
                '{"compliance_landscape":{"overall":{"red_pct":0.12,"yellow_pct":0.34}},'
                '"competitors":[{"name":"Competitor A"}]}'
            ),
            "04": step04,
            "06": step06,
        },
    }

    stage1 = translate_stage1(stage0=stage0, precanon_research=precanon_research)

    assert stage1.competitor_count_validated == 9
    assert stage1.competitor_urls == [
        "https://www.lifeextension.com/",
        "https://happymammoths.us/products/hormone-harmony",
        "https://www.maryruthorganics.com/products/organic-menopause-gummies",
        "https://estroven.com/",
        "https://opositivcare.com/",
        "https://hellobonafide.com/",
        "https://perelelhealth.com/",
        "https://menolabs.com/",
        "https://amberen.com/products/amberen-advanced-menopause-relief-capsules-3-month-supply",
    ]
    assert stage1.market_maturity_stage == "Maturity"
    assert "I need my brain back" in stage1.bottleneck
    assert stage1.primary_icps == [
        "Workplace Edge Protectors",
        "ADHD-Peri System Crashers",
        "Evidence-Hawk Supplement Skeptics",
        "Format Friction Strugglers",
        "Side-Effect Sentinels",
    ]
    assert stage1.primary_segment.name == "Workplace Edge Protectors"
    assert stage1.primary_segment.size_estimate == "25% of the live VOC set"
    assert stage1.primary_segment.key_differentiator == "Primary pain is public competence loss"


def test_translate_stage1_handles_live_primary_niche_validation_tables_and_profile_blocks() -> None:
    stage0 = translate_stage0(
        product_name="Ember: Brain Clarity Protocol",
        product_description="Creatine gummies designed for perimenopausal women.",
        onboarding_payload={},
        stage0_overrides={"product_customizable": True, "price": "$40"},
    )
    precanon_research = {
        "step_contents": {
            "01": (
                "## Phase 1 — Understand & Formalize the Idea (Evidence-only)\n"
                "### 6) Market definition (keep visible)\n"
                '**Primary niche:** "Hormone-free DTC menopause/perimenopause supplements positioned for brain fog / focus / cognitive clarity."\n'
                "\n"
                "## Phase 2 — Discover Competitors (Direct + Adjacent; candidates collected)\n"
                "| Candidate | URL | Type | What they do (1 line) |\n"
                "|---|---|---|---|\n"
                "| O Positiv MENO | opositiv.com/products/meno-menopause-gummy-vitamins-s2 | Direct | Hormone-free menopause gummy. ([opositiv.com](https://opositiv.com/products/meno-menopause-gummy-vitamins-s2?utm_source=openai)) |\n"
                "| Happy Mammoth Hormone Harmony | happymammoths.us/products/hormone-harmony | Direct | Menopause hormone support. ([happymammoths.us](https://happymammoths.us/products/hormone-harmony?utm_source=openai)) |\n"
                "| HUM Fan Club | nordstrom.com listing | Direct | Retail listing with substantial review volume. ([nordstrom.com](https://www.nordstrom.com/s/fan-club-multi-symptom-relief-for-perimenopause-menopause-supplement/6971955?utm_source=openai)) |\n"
                "| Brainzyme Focus | brainzyme.com/products/brainzyme-focus-brain-fog-menopause | Adjacent | Menopause brain fog support. ([brainzyme.com](https://www.brainzyme.com/products/brainzyme-focus-brain-fog-menopause?utm_source=openai)) |\n"
                "\n"
                "## Phase 3 — Validate “Battle-Tested” (ONLY those with non-trivial traction signals)\n"
                "| Competitor | Included? | Why it passes bar (1–2 bullets; evidence) |\n"
                "|---|---:|---|\n"
                "| O Positiv | Yes | Large traffic estimate present. |\n"
                "| Happy Mammoth | Yes | Product page shows thousands of reviews. |\n"
                "| HUM Fan Club | Yes | Nordstrom listing shows meaningful review volume. |\n"
                "| Brainzyme | No | Useful adjacent angle but weaker traction in this run. |\n"
                "\n"
                "## Phase 8 — Market Maturity Assessment (evidence-based)\n"
                "### Product lifecycle stage: **Maturity**\n"
            ),
            "04": (
                "## Bottleneck Identification\n"
                "### #1 biggest unresolved pain / unmet need / broken expectation\n"
                "A trustworthy, menopause-relevant brain fog solution that feels safe, believable, and easy to stick with.\n"
            ),
            "06": (
                "## Phase 1: Segment Discovery\n"
                "### Step 3 — Segment names & bounds (3)\n"
                "1) **Word-Work Panic Performers** — high-performing, word-based careers; embarrassment triggers action.\n"
                "2) **Hormone-Cautious Protocol Experimenters** — try sleep/exercise/supplements before committing hard.\n"
                "3) **Format-Driven, Side-Effect-Sensitive Convenience Seekers** — GI tolerance and adherence determine conversion.\n"
                "\n"
                "## Phase 2: Segment Profiles\n"
                "# 1) Word-Work Panic Performers\n"
                "### A. Segment Identity\n"
                "- **Segment Name:** Word-Work Panic Performers\n"
                "- **Estimated Prevalence (Fermi):** **~25%** of peri/meno women 42–58.\n"
                "- **Key Differentiator:** Their #1 pain is *public performance failure* (meetings/emails/conversations), not general wellness.\n"
                "\n"
                "# 2) Hormone-Cautious Protocol Experimenters\n"
                "### A. Segment Identity\n"
                "- **Segment Name:** Hormone-Cautious Protocol Experimenters\n"
                "- **Estimated Prevalence:** **~30%** across the live VOC set.\n"
                "- **Key Differentiator:** They buy *a protocol*, not a pill.\n"
                "\n"
                "# 3) Format-Driven, Side-Effect-Sensitive Convenience Seekers\n"
                "### A. Segment Identity\n"
                "- **Segment Name:** Format-Driven, Side-Effect-Sensitive Convenience Seekers\n"
                "- **Estimated Prevalence:** **~15%** with strong tolerability signals.\n"
                "- **Key Differentiator:** Conversion hinges on *tolerability + dosing practicality*, not motivation.\n"
                "\n"
                "## Phase 3: Bottleneck Segment Identification (computed)\n"
                "**PRIMARY SEGMENT = Word-Work Panic Performers.**\n"
            ),
        }
    }

    stage1 = translate_stage1(stage0=stage0, precanon_research=precanon_research)

    assert stage1.category_niche == (
        "Hormone-free DTC menopause/perimenopause supplements positioned for brain fog / focus / cognitive clarity."
    )
    assert stage1.market_maturity_stage == "Maturity"
    assert stage1.competitor_count_validated == 3
    assert stage1.competitor_urls == [
        "https://opositiv.com/products/meno-menopause-gummy-vitamins-s2",
        "https://happymammoths.us/products/hormone-harmony",
        "https://www.nordstrom.com/s/fan-club-multi-symptom-relief-for-perimenopause-menopause-supplement/6971955",
    ]
    assert stage1.primary_icps == [
        "Word-Work Panic Performers",
        "Hormone-Cautious Protocol Experimenters",
        "Format-Driven, Side-Effect-Sensitive Convenience Seekers",
    ]
    assert stage1.primary_segment.name == "Word-Work Panic Performers"
    assert stage1.primary_segment.size_estimate == "~25% of peri/meno women 42–58."
    assert stage1.primary_segment.key_differentiator == (
        "Their #1 pain is public performance failure (meetings/emails/conversations), not general wellness."
    )
    assert stage1.bottleneck == (
        "A trustworthy, menopause-relevant brain fog solution that feels safe, believable, and easy to stick with."
    )


def test_translate_stage1_handles_april_2026_live_foundational_shape() -> None:
    stage0 = translate_stage0(
        product_name="Ember: Brain Clarity Protocol",
        product_description="Creatine gummies designed for perimenopausal women.",
        onboarding_payload={},
        stage0_overrides={"product_customizable": True, "price": "$40"},
    )
    precanon_research = {
        "category_niche": "Supplements for women age 42-58",
        "step_contents": {
            "01": (
                "### 6) Market definition (keep visible)\n"
                '**Primary niche:** "DTC menopause/perimenopause supplements (often gummies/capsules) '
                'claiming multi-symptom relief, with a sub-pocket of creatine-driven \'brain+strength\' products."\n'
                "\n"
                "## Phase 2 — Discover Competitors (Direct + Adjacent)\n"
                "| Candidate | URL | Type | What it is |\n"
                "|---|---:|---|---|\n"
                "| O Positiv | `https://opositiv.com/` | Direct | Menopause supplement brand |\n"
                "| Alloy | `https://es.semrush.com/website/myalloy.com/overview/` | Adjacent | Menopause care service |\n"
                "| Midi Health | `https://hypestat.com/info/joinmidi.com` | Adjacent | Menopause specialist clinic |\n"
                "| Equelle | `https://hypestat.com/info/equelle.com` | Direct | Menopause supplement site |\n"
                "| Brainzyme | `https://hypestat.com/info/brainzyme.com` | Adjacent | Menopause brain fog support |\n"
                "\n"
                "## Phase 3 — Validate Battle-Tested Competitors\n"
                "### Validated competitors (5)\n"
                "1) **O Positiv** — traction evidence. "
                "([hypestat.com](https://hypestat.com/info/opositiv.com))\n"
                "2) **Alloy** — traction evidence. "
                "([semrush.com](https://www.semrush.com/website/myalloy.com/overview/))\n"
                "3) **Midi Health** — traction evidence. "
                "([hypestat.com](https://hypestat.com/info/joinmidi.com))\n"
                "4) **Equelle** — traction evidence. "
                "([hypestat.com](https://hypestat.com/info/equelle.com))\n"
                "5) **Brainzyme** — traction evidence. "
                "([hypestat.com](https://hypestat.com/info/brainzyme.com))\n"
                "\n"
                "## Phase 8 — Market Maturity Assessment\n"
                "### Product lifecycle stage: Growth → early maturity\n"
            ),
            "04": (
                "3) Bottleneck Identification (most important)\n"
                "#1 unresolved pain / unmet need / broken expectation:\n"
                "“I need my brain back, but I don’t have time to experiment—and I don’t trust convenient "
                "formats (gummies) to be real, stable, and correctly dosed.”\n"
                "\n"
                "- Quality failures: “MOLD!!” + “not consistent.”\n"
            ),
            "06": (
                "## Phase 1: Segment Discovery\n"
                "### Step 3 — Segments named & bounded (5)\n"
                "1) **Boardroom Word-Loss Achiever** — work-performance failures drive urgency.\n"
                "2) **Caregiver Slow-Fade + Dementia-Fear** — reassurance and a plan.\n"
                "3) **Proof-First Anti-Scam Analyst** — only buys when proof is explicit.\n"
                "4) **Side-Effect Sensitive Scale-Watcher (PRIMARY CANDIDATE)** — wants cognitive upside "
                "but quits fast when bloat, GI, palpitations, or hair fears show up.\n"
                "5) **Supplement-Overwhelmed Convenience Seeker** — wants an easy, consistent routine.\n"
                "\n"
                "## Phase 2: Segment Profiles\n"
                "# Segment 1 — Boardroom Word-Loss Achiever\n"
                "## A) Segment Identity\n"
                "**Segment Name:** Boardroom Word-Loss Achiever\n"
                "**Estimated Prevalence:** ~25% of TAM\n"
                "**Key Differentiator:** Her purchase urgency is driven by public work slips.\n"
                "\n"
                "# Segment 4 — Side-Effect Sensitive Scale-Watcher (PRIMARY)\n"
                "## A) Segment Identity\n"
                "**Segment Name:** Side-Effect Sensitive Scale-Watcher\n"
                "**Estimated Prevalence:** ~20% of TAM (Fermi): bloat/scale is HIGH SIGNAL and side effects recur.\n"
                "**Key Differentiator:** Her decision is dominated by tolerability and perceived body-risk.\n"
                "\n"
                "## Phase 3: Cross-Segment Analysis\n"
                "**The PRIMARY SEGMENT is: Side-Effect Sensitive Scale-Watcher.**\n"
            ),
        },
    }

    stage1 = translate_stage1(stage0=stage0, precanon_research=precanon_research)

    assert stage1.category_niche.startswith("DTC menopause/perimenopause supplements")
    assert stage1.competitor_urls == [
        "https://opositiv.com/",
        "https://myalloy.com/",
        "https://joinmidi.com/",
        "https://equelle.com/",
        "https://brainzyme.com/",
    ]
    assert stage1.competitor_count_validated == 5
    assert stage1.bottleneck.startswith("I need my brain back")
    assert stage1.primary_segment.name == "Side-Effect Sensitive Scale-Watcher"
    assert stage1.primary_segment.size_estimate.startswith("~20%")
    assert stage1.primary_segment.key_differentiator.startswith(
        "Her decision is dominated by tolerability and perceived body-risk"
    )
    assert any("creatine" in keyword for keyword in stage1.product_category_keywords)


def test_translate_stage1_handles_validated_competitor_set_tables_with_multiline_niche_and_bold_bottleneck() -> None:
    stage0 = translate_stage0(
        product_name="Ember: Brain Clarity Protocol",
        product_description="Creatine gummies designed for perimenopausal women.",
        onboarding_payload={},
        stage0_overrides={"product_customizable": True, "price": "$40"},
    )
    precanon_research = {
        "category_niche": "Supplements for women age 42-58",
        "step_contents": {
            "01": json.dumps(
                {
                    "source": "precanon_research.step_contents",
                    "content": (
                        "## Phase 1: Understand & Formalize the Idea\n"
                        "**Primary niche (filter for later phases):**\n"
                        "**Perimenopause brain-fog supplement protocols, specifically creatine-forward gummies/supplements for women 42–58.**\n"
                        "\n"
                        "### Candidate competitor set (unfiltered)\n"
                        "| Candidate | URL | Type | What they do / who they serve |\n"
                        "|---|---|---:|---|\n"
                        "| Goli | goli.com | Adjacent | Large gummy supplement brand. ([de.semrush.com](https://de.semrush.com/website/goli.com/overview/?utm_source=openai)) |\n"
                        "| Happy Mammoth | store.happymammoth.com | Adjacent | Women's hormone support brand. ([brandsearch.co](https://brandsearch.co/brands/store.happymammoth.com?utm_source=openai)) |\n"
                        "| Perelel | perelelhealth.com | Adjacent | Women's supplement packs. ([milled.com](https://milled.com/perelel/introducing-mens-multi-support-pack-wV_BzPwQuroAjC8E?utm_source=openai)) |\n"
                        "\n"
                        "## Phase 3: Validate “Battle-Tested” Competitors (filter to non-trivial traction)\n"
                        "### Validation rule applied\n"
                        "Only include brands with meaningful traffic or clear market proof.\n"
                        "\n"
                        "### Validated competitor set (3)\n"
                        "| Competitor | Why it passes “battle-tested” bar (evidence) |\n"
                        "|---|---|\n"
                        "| **Goli (goli.com)** | Semrush shows strong traffic. ([de.semrush.com](https://de.semrush.com/website/goli.com/overview/?utm_source=openai)) |\n"
                        "| **Happy Mammoth (store.happymammoth.com / happymammoth.com)** | BrandSearch shows strong traffic and revenue. ([brandsearch.co](https://brandsearch.co/brands/store.happymammoth.com?utm_source=openai)) |\n"
                        "| **Perelel (perelelhealth.com)** | Semrush competitors page shows meaningful traffic. ([semrush.com](https://www.semrush.com/website/perelelhealth.com/competitors/?utm_source=openai)) |\n"
                        "\n"
                        "### Product lifecycle stage: Growth → early maturity\n"
                    ),
                    "bounded_summary": "Validated competitor set (3).",
                    "foundational_step_key": "01",
                }
            ),
            "04": json.dumps(
                {
                    "source": "precanon_research.step_contents",
                    "content": (
                        "# Bottleneck Identification (single biggest unresolved need)\n"
                        "**Biggest unresolved need:** A **peri-specific, creatine-first brain fog protocol** that feels *safe* and *works*, **in a gummy form people actually trust**.\n"
                    ),
                    "bounded_summary": "Biggest unresolved need captured.",
                    "foundational_step_key": "04",
                }
            ),
            "06": json.dumps(
                {
                    "source": "precanon_research.step_contents",
                    "content": (
                        "## Phase 1: Segment Discovery\n"
                        "### Step 3 — Segment names & bounds (3)\n"
                        "1) Boardroom Blankers (High-Performing Knowledge Workers)\n"
                        "2) Care-Betrayed Self-Experimenters (Community-First Protocol Builders)\n"
                        "3) Hormone-Cautious Non-Hormone Seekers (HRT-Avoidant but Protocol-Oriented)\n"
                        "\n"
                        "## Segment 1 — Boardroom Blankers (High-Performing Knowledge Workers)\n"
                        "- Segment Name: Boardroom Blankers (High-Performing Knowledge Workers)\n"
                        "- Estimated Prevalence: ~30% of Ember's TAM\n"
                        "- Key Differentiator: Their primary pain is status/competence exposure (not just discomfort).\n"
                        "\n"
                        "## Segment 2 — Care-Betrayed Self-Experimenters (Community-First Protocol Builders)\n"
                        "- Segment Name: Care-Betrayed Self-Experimenters (Community-First Protocol Builders)\n"
                        "- Estimated Prevalence: ~25% of Ember's TAM\n"
                        "- Key Differentiator: They share and iterate on protocols before buying.\n"
                        "\n"
                        "## Segment 3 — Hormone-Cautious Non-Hormone Seekers (HRT-Avoidant but Protocol-Oriented)\n"
                        "- Segment Name: Hormone-Cautious Non-Hormone Seekers (HRT-Avoidant but Protocol-Oriented)\n"
                        "- Estimated Prevalence: ~20% of Ember's TAM\n"
                        "- Key Differentiator: They want a non-hormonal protocol they can trust.\n"
                        "\n"
                        "**The PRIMARY SEGMENT is: _Boardroom Blankers (High-Performing Knowledge Workers)_.**\n"
                    ),
                    "bounded_summary": "Primary segment is Boardroom Blankers.",
                    "foundational_step_key": "06",
                }
            ),
        },
    }

    stage1 = translate_stage1(stage0=stage0, precanon_research=precanon_research)

    assert stage1.category_niche == (
        "Perimenopause brain-fog supplement protocols, specifically creatine-forward gummies/supplements for women 42–58."
    )
    assert stage1.market_maturity_stage == "Growth"
    assert stage1.competitor_count_validated == 3
    assert stage1.competitor_urls == [
        "https://goli.com/",
        "https://store.happymammoth.com/",
        "https://perelelhealth.com/",
    ]
    assert stage1.bottleneck == (
        "A peri-specific, creatine-first brain fog protocol that feels safe and works, in a gummy form people actually trust."
    )
    assert stage1.primary_segment.name == "Boardroom Blankers (High-Performing Knowledge Workers)"


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


def test_qa_loop_wrapper_supports_baseten_provider_prefix(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _DummyChatCompletions:
        def create(self, **kwargs):  # noqa: ANN003
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Kimi-fixed headline"), finish_reason="stop")],
                usage=SimpleNamespace(prompt_tokens=9, completion_tokens=4),
                _request_id="req_kimi_123",
            )

    class _DummyChat:
        def __init__(self) -> None:
            self.completions = _DummyChatCompletions()

    class _DummyOpenAI:
        def __init__(self, **kwargs):  # noqa: ANN003
            captured["client_kwargs"] = kwargs
            self.chat = _DummyChat()

    def _fake_run_qa_loop(*args, **_kwargs):
        response = fake_module.call_llm(
            "Rewrite this headline",
            args[4],
            args[5],
            messages=[{"role": "user", "content": "Rewrite this headline"}],
        )
        return {
            "status": "PASS",
            "best_headline": response["text"],
            "total_iterations": 2,
        }

    def _fake_to_json(raw):
        return {
            "status": raw["status"],
            "best_headline": raw["best_headline"],
            "total_iterations": raw["total_iterations"],
            "metadata": {"request_ids": ["req_kimi_123"]},
        }

    fake_module = SimpleNamespace(
        run_qa_loop=_fake_run_qa_loop,
        to_json=_fake_to_json,
    )

    monkeypatch.setattr(scorer_module, "_load_module", lambda *_args, **_kwargs: fake_module)
    monkeypatch.setattr(scorer_module, "get_openai_client_class", lambda: _DummyOpenAI)
    monkeypatch.setenv("BASETEN_BASE_URL", "")

    result = run_headline_qa_loop(
        headline="Most Herb Guides Skip the One Dosing Detail Families Need",
        page_type="advertorial",
        max_iterations=2,
        min_tier="A",
        api_key="test-baseten-key",
        model="baseten:moonshotai/Kimi-K2.5",
    )

    diagnostics = result["diagnostics"]
    assert result["json"]["status"] == "PASS"
    assert result["json"]["best_headline"] == "Kimi-fixed headline"
    assert diagnostics["provider"] == "baseten"
    assert diagnostics["request_ids"] == ["req_kimi_123"]
    assert captured["client_kwargs"]["base_url"] == "https://inference.baseten.co/v1"  # type: ignore[index]
    assert captured["kwargs"]["model"] == "moonshotai/Kimi-K2.5"  # type: ignore[index]
    assert captured["kwargs"]["extra_body"] == {"chat_template_args": {"enable_thinking": True}}  # type: ignore[index]
