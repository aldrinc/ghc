from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from app.db.enums import ArtifactTypeEnum, WorkflowKindEnum
from app.db.models import Artifact, Campaign, OnboardingPayload, ProductOffer, ResearchArtifact, WorkflowRun
from app.routers.workflows import _normalize_strategy_v2_artifact_refs
from app.strategy_v2.errors import (
    StrategyV2DecisionError,
    StrategyV2MissingContextError,
    StrategyV2SchemaValidationError,
)
from app.temporal.activities import strategy_v2_activities


@pytest.fixture(autouse=True)
def _stub_activity_heartbeat(monkeypatch):
    monkeypatch.setattr(strategy_v2_activities.activity, "heartbeat", lambda *_args, **_kwargs: None)


@pytest.fixture(autouse=True)
def _stub_prompt_file_uploads(monkeypatch):
    uploaded_logical_payloads: dict[str, dict[str, Any]] = {}

    def _fake_upload_openai_prompt_json_files(*, stage_label: str, logical_payloads: dict[str, Any], **_kwargs):
        uploaded_logical_payloads[stage_label] = dict(logical_payloads)
        return ({str(name): f"file-{stage_label}-{name}" for name in logical_payloads}, [])

    monkeypatch.setattr(
        strategy_v2_activities,
        "_upload_openai_prompt_json_files",
        _fake_upload_openai_prompt_json_files,
    )
    monkeypatch.setattr(
        strategy_v2_activities,
        "_cleanup_openai_prompt_files",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        strategy_v2_activities,
        "_TEST_STUB_PROMPT_LOGICAL_PAYLOADS",
        uploaded_logical_payloads,
        raising=False,
    )


@pytest.fixture(autouse=True)
def _stub_prompt_chain_runtime(monkeypatch):
    def _resolve_prompt_asset_stub(*, pattern: str, context: str):
        if "pipeline-orchestrator.md" in pattern:
            raw_text = (
                "step-01-avatar-brief.md\n"
                "step-02-market-calibration.md\n"
                "step-03-ump-ums-generation.md\n"
                "step-04-offer-construction.md\n"
                "step-05-self-evaluation-scoring.md\n"
            )
        else:
            raw_text = f"{context} template"
        return strategy_v2_activities.PromptAsset(
            absolute_path=Path(f"/tests/{pattern}"),
            relative_path=f"V2 Fixes/{pattern}",
            sha256=str(abs(hash((pattern, context)))),
            text=raw_text,
        )

    def _step05_evaluation_payload() -> dict[str, Any]:
        return {
            "variants": [
                {
                    "variant_id": "single_device",
                    "dimensions": {
                        "value_equation": {"raw_score": 8.0, "evidence_quality": "INFERRED"},
                        "objection_coverage": {"raw_score": 8.0, "evidence_quality": "OBSERVED"},
                        "competitive_differentiation": {"raw_score": 8.0, "evidence_quality": "INFERRED"},
                        "compliance_safety": {"raw_score": 8.5, "evidence_quality": "OBSERVED"},
                        "internal_consistency": {"raw_score": 8.0, "evidence_quality": "INFERRED"},
                        "clarity_simplicity": {"raw_score": 8.0, "evidence_quality": "INFERRED"},
                        "bottleneck_resilience": {"raw_score": 7.5, "evidence_quality": "INFERRED"},
                        "momentum_continuity": {"raw_score": 7.8, "evidence_quality": "INFERRED"},
                        "pricing_fidelity": {"raw_score": 8.0, "evidence_quality": "OBSERVED"},
                        "savings_fidelity": {"raw_score": 7.8, "evidence_quality": "OBSERVED"},
                        "best_value_fidelity": {"raw_score": 7.5, "evidence_quality": "INFERRED"},
                    },
                },
                {
                    "variant_id": "share_and_save",
                    "dimensions": {
                        "value_equation": {"raw_score": 8.2, "evidence_quality": "INFERRED"},
                        "objection_coverage": {"raw_score": 8.1, "evidence_quality": "OBSERVED"},
                        "competitive_differentiation": {"raw_score": 8.1, "evidence_quality": "INFERRED"},
                        "compliance_safety": {"raw_score": 8.6, "evidence_quality": "OBSERVED"},
                        "internal_consistency": {"raw_score": 8.1, "evidence_quality": "INFERRED"},
                        "clarity_simplicity": {"raw_score": 8.0, "evidence_quality": "INFERRED"},
                        "bottleneck_resilience": {"raw_score": 7.6, "evidence_quality": "INFERRED"},
                        "momentum_continuity": {"raw_score": 8.0, "evidence_quality": "INFERRED"},
                        "pricing_fidelity": {"raw_score": 8.4, "evidence_quality": "OBSERVED"},
                        "savings_fidelity": {"raw_score": 8.3, "evidence_quality": "OBSERVED"},
                        "best_value_fidelity": {"raw_score": 8.1, "evidence_quality": "INFERRED"},
                    },
                },
                {
                    "variant_id": "family_bundle",
                    "dimensions": {
                        "value_equation": {"raw_score": 7.8, "evidence_quality": "INFERRED"},
                        "objection_coverage": {"raw_score": 7.7, "evidence_quality": "OBSERVED"},
                        "competitive_differentiation": {"raw_score": 7.6, "evidence_quality": "INFERRED"},
                        "compliance_safety": {"raw_score": 8.4, "evidence_quality": "OBSERVED"},
                        "internal_consistency": {"raw_score": 7.7, "evidence_quality": "INFERRED"},
                        "clarity_simplicity": {"raw_score": 7.7, "evidence_quality": "INFERRED"},
                        "bottleneck_resilience": {"raw_score": 7.4, "evidence_quality": "INFERRED"},
                        "momentum_continuity": {"raw_score": 7.6, "evidence_quality": "INFERRED"},
                        "pricing_fidelity": {"raw_score": 8.7, "evidence_quality": "OBSERVED"},
                        "savings_fidelity": {"raw_score": 8.8, "evidence_quality": "OBSERVED"},
                        "best_value_fidelity": {"raw_score": 8.9, "evidence_quality": "INFERRED"},
                    },
                },
            ]
        }

    def _offer_variants_payload() -> list[dict[str, Any]]:
        return [
            {
                "variant_id": "single_device",
                "core_promise": "Overwhelm -> calm routine",
                "value_stack": [
                    {
                        "name": "Core handbook",
                        "dream_outcome": 8,
                        "perceived_likelihood": 7,
                        "time_delay": 4,
                        "effort_sacrifice": 3,
                        "novelty_classification": "INCREMENTAL",
                    },
                    {
                        "name": "Implementation checklist",
                        "dream_outcome": 8,
                        "perceived_likelihood": 8,
                        "time_delay": 4,
                        "effort_sacrifice": 3,
                        "novelty_classification": "NOVEL",
                    },
                    {
                        "name": "Decision worksheet",
                        "dream_outcome": 7,
                        "perceived_likelihood": 7,
                        "time_delay": 4,
                        "effort_sacrifice": 4,
                        "novelty_classification": "NOVEL",
                    },
                ],
                "guarantee": "30-day clarity guarantee",
                "pricing_rationale": "Single payment for recurring use",
                "pricing_metadata": {"list_price_cents": 9900, "offer_price_cents": 6900},
                "savings_metadata": {
                    "savings_amount_cents": 3000,
                    "savings_percent": 30.3,
                    "savings_basis": "vs_list_price",
                },
                "best_value_metadata": {
                    "is_best_value": False,
                    "rationale": "Lowest commitment option for first-time buyers.",
                    "compared_variant_ids": ["share_and_save", "family_bundle"],
                },
                "bonus_modules": {
                    "bonus-1": {"copy": "Nightly startup checklist for first use."},
                    "bonus-2": {"copy": "Troubleshooting map for routine disruptions."},
                    "bonus-3": {"copy": "Quick reference card for daily consistency."},
                },
                "objection_map": [
                    {"objection": "Will this fit my routine?", "source": "voc", "covered": True, "coverage_strength": 8},
                    {"objection": "Will this actually work?", "source": "voc", "covered": True, "coverage_strength": 8},
                    {"objection": "Is this worth the price?", "source": "research", "covered": True, "coverage_strength": 7},
                ],
                "dimension_scores": {
                    "competitive_differentiation": 8,
                    "compliance_safety": 9,
                    "internal_consistency": 8,
                    "clarity_simplicity": 8,
                    "bottleneck_resilience": 7,
                    "momentum_continuity": 8,
                    "pricing_fidelity": 8,
                    "savings_fidelity": 8,
                    "best_value_fidelity": 7,
                },
            },
            {
                "variant_id": "share_and_save",
                "core_promise": "Overwhelm -> calm routine",
                "value_stack": [
                    {
                        "name": "Core handbook",
                        "dream_outcome": 8,
                        "perceived_likelihood": 7,
                        "time_delay": 4,
                        "effort_sacrifice": 3,
                        "novelty_classification": "INCREMENTAL",
                    },
                    {
                        "name": "Quick-start map",
                        "dream_outcome": 8,
                        "perceived_likelihood": 8,
                        "time_delay": 3,
                        "effort_sacrifice": 3,
                        "novelty_classification": "NOVEL",
                    },
                    {
                        "name": "Decision worksheet",
                        "dream_outcome": 7,
                        "perceived_likelihood": 7,
                        "time_delay": 4,
                        "effort_sacrifice": 4,
                        "novelty_classification": "NOVEL",
                    },
                ],
                "guarantee": "60-day confidence guarantee",
                "pricing_rationale": "Action-oriented bundle value",
                "pricing_metadata": {"list_price_cents": 19800, "offer_price_cents": 11900},
                "savings_metadata": {
                    "savings_amount_cents": 7900,
                    "savings_percent": 39.9,
                    "savings_basis": "vs_list_price",
                },
                "best_value_metadata": {
                    "is_best_value": False,
                    "rationale": "Best for two-device households balancing value and flexibility.",
                    "compared_variant_ids": ["single_device", "family_bundle"],
                },
                "bonus_modules": {
                    "bonus-1": {"copy": "Shared setup workflow for two users."},
                    "bonus-2": {"copy": "Sync checklist to keep routines aligned."},
                    "bonus-3": {"copy": "Partner accountability prompts for follow-through."},
                },
                "objection_map": [
                    {"objection": "Will this fit my routine?", "source": "voc", "covered": True, "coverage_strength": 8},
                    {"objection": "Will this actually work?", "source": "voc", "covered": True, "coverage_strength": 8},
                    {"objection": "Is this worth the price?", "source": "research", "covered": True, "coverage_strength": 7},
                ],
                "dimension_scores": {
                    "competitive_differentiation": 8,
                    "compliance_safety": 9,
                    "internal_consistency": 8,
                    "clarity_simplicity": 8,
                    "bottleneck_resilience": 8,
                    "momentum_continuity": 8,
                    "pricing_fidelity": 8,
                    "savings_fidelity": 8,
                    "best_value_fidelity": 8,
                },
            },
            {
                "variant_id": "family_bundle",
                "core_promise": "Overwhelm -> calm routine",
                "value_stack": [
                    {
                        "name": "Core handbook",
                        "dream_outcome": 8,
                        "perceived_likelihood": 7,
                        "time_delay": 4,
                        "effort_sacrifice": 3,
                        "novelty_classification": "INCREMENTAL",
                    },
                    {
                        "name": "Comparison matrix",
                        "dream_outcome": 7,
                        "perceived_likelihood": 7,
                        "time_delay": 4,
                        "effort_sacrifice": 3,
                        "novelty_classification": "NOVEL",
                    },
                    {
                        "name": "Objection scripts",
                        "dream_outcome": 7,
                        "perceived_likelihood": 7,
                        "time_delay": 4,
                        "effort_sacrifice": 4,
                        "novelty_classification": "INCREMENTAL",
                    },
                ],
                "guarantee": "30-day clarity guarantee",
                "pricing_rationale": "Anchored bundle value",
                "pricing_metadata": {"list_price_cents": 29700, "offer_price_cents": 15900},
                "savings_metadata": {
                    "savings_amount_cents": 13800,
                    "savings_percent": 46.46,
                    "savings_basis": "vs_list_price",
                },
                "best_value_metadata": {
                    "is_best_value": True,
                    "rationale": "Highest total savings for family usage with the same core system.",
                    "compared_variant_ids": ["single_device", "share_and_save"],
                },
                "bonus_modules": {
                    "bonus-1": {"copy": "Family onboarding plan for multiple caregivers."},
                    "bonus-2": {"copy": "Shared escalation guide for off-pattern nights."},
                    "bonus-3": {"copy": "Printable family tracker for weekly review."},
                },
                "objection_map": [
                    {"objection": "Will this fit my routine?", "source": "voc", "covered": True, "coverage_strength": 7},
                    {"objection": "Will this actually work?", "source": "voc", "covered": True, "coverage_strength": 7},
                    {"objection": "Is this worth the price?", "source": "research", "covered": True, "coverage_strength": 7},
                ],
                "dimension_scores": {
                    "competitive_differentiation": 7,
                    "compliance_safety": 8,
                    "internal_consistency": 7,
                    "clarity_simplicity": 7,
                    "bottleneck_resilience": 7,
                    "momentum_continuity": 7,
                    "pricing_fidelity": 9,
                    "savings_fidelity": 9,
                    "best_value_fidelity": 9,
                },
            },
        ]

    def _fake_run_prompt_json_object(*, context: str, **_kwargs):
        advertorial_template_payload = {
            "hero": {
                "title": "Approved Headline",
                "subtitle": "Predictable evenings are possible with a mechanism-first approach.",
                "badges": [
                    {
                        "label": "Mechanism-first",
                        "icon": {"alt": "Mechanism icon", "prompt": "icon of mechanism-first process"},
                    },
                    {
                        "label": "Evidence-backed",
                        "icon": {"alt": "Evidence icon", "prompt": "icon of evidence-backed guidance"},
                    },
                    {
                        "label": "Practical nightly use",
                        "icon": {"alt": "Checklist icon", "prompt": "icon of nightly routine checklist"},
                    },
                ],
            },
            "reasons": [
                {
                    "number": 1,
                    "title": "Random fixes miss the real bottleneck",
                    "body": "Mechanism mismatch keeps restarting the same nightly stress loop.",
                    "image": {
                        "alt": "Caregiver reviewing a nightly routine checklist",
                    },
                }
            ],
            "marquee": [
                "Mechanism-first",
                "Evidence-backed",
                "Practical steps",
            ],
            "pitch": {
                "title": "See the full implementation offer",
                "bullets": [
                    "Checklist for nightly execution",
                    "Decision support for common setbacks",
                    "Mechanism-first guidance for routine resets",
                    "Clear next steps for tonight's implementation",
                ],
                "cta_label": "Continue to the offer",
                "image": {"alt": "Printed guide and checklist pages"},
            },
            "reviews": [
                {
                    "text": "We stopped guessing and the evening rhythm is finally stable.",
                    "author": "K. Parent",
                    "rating": 5,
                },
                {
                    "text": "The step-by-step flow made execution much easier for our routine.",
                    "author": "D. Caregiver",
                    "rating": 5,
                },
                {
                    "text": "Clear boundaries and practical guidance reduced our nightly stress fast.",
                    "author": "M. Family",
                    "rating": 5,
                },
            ],
            "review_wall": {
                "title": "What readers report after switching approach",
                "button_label": "Open full review examples",
            },
            "floating_cta": {
                "label": "Continue to offer",
            },
        }
        sales_template_payload = {
            "hero": {
                "purchase_title": "Start the mechanism-first evening system",
                "primary_cta_label": "Claim the system",
                "primary_cta_subbullets": [
                    "Fast implementation path",
                    "30-day confidence guarantee",
                ],
            },
            "problem": {
                "title": "Nightly friction keeps repeating",
                "paragraphs": [
                    "Most routines fail because they optimize effort instead of sequence.",
                ],
                "emphasis_line": "When sequence is wrong, consistency collapses.",
            },
            "mechanism": {
                "title": "Fix the sequence, then the outcomes follow",
                "paragraphs": [
                    "The system targets trigger timing and removes guesswork.",
                ],
                "bullets": [
                    {"title": "Trigger map", "body": "Identify sequence breakpoints before they cascade."},
                    {"title": "Execution order", "body": "Apply steps in a repeatable nightly progression."},
                    {"title": "Recovery branch", "body": "Handle misses without resetting the full routine."},
                    {"title": "Progress markers", "body": "Track wins and frictions with simple checkpoints."},
                    {"title": "Confidence anchor", "body": "Use evidence-backed cues to stay consistent under stress."},
                ],
                "callout": {
                    "left_title": "Why old routines fail",
                    "left_body": "They describe tasks but ignore trigger order.",
                    "right_title": "What this changes",
                    "right_body": "It aligns actions to sequence so consistency compounds.",
                },
                "comparison": {
                    "badge": "Side-by-side",
                    "title": "Mechanism-first system vs generic routines",
                    "swipe_hint": "Swipe to compare",
                    "columns": {
                        "pup": "Mechanism-first",
                        "disposable": "Generic routine",
                    },
                    "rows": [
                        {
                            "label": "Predictability",
                            "pup": "High once sequence is set",
                            "disposable": "Inconsistent",
                        }
                    ],
                },
            },
            "social_proof": {
                "badge": "Verified",
                "title": "Customer-backed clarity",
                "rating_label": "4.9 average confidence",
                "summary": "Families report fewer resets and calmer evenings.",
            },
            "whats_inside": {
                "benefits": [
                    "Start Faster",
                    "Stay On Track",
                    "Ask Better Questions",
                    "Feel More Certain",
                ],
                "offer_helper_text": "Everything needed to execute without guesswork.",
            },
            "bonus": {
                "free_gifts_title": "Included bonus assets",
                "free_gifts_body": "Rapid-start templates and scenario walkthroughs.",
            },
            "guarantee": {
                "title": "30-day confidence guarantee",
                "paragraphs": [
                    "Run the system and evaluate fit using measurable checkpoints.",
                ],
                "why_title": "Why this guarantee exists",
                "why_body": "The process is practical, testable, and low-friction.",
                "closing_line": "You can adopt this with clear downside protection.",
            },
            "faq": {
                "title": "Frequently asked questions",
                "items": [
                    {
                        "question": "How quickly can we start?",
                        "answer": "Most families can run the first sequence tonight.",
                    }
                ],
            },
            "faq_pills": [
                {
                    "label": "How quickly can we start?",
                    "answer": "Most families can run the first sequence tonight.",
                }
            ],
            "marquee_items": [
                "Mechanism-first",
                "Practical nightly use",
                "Evidence-backed",
                "Confidence guarantee",
            ],
            "urgency_message": "Selling out faster than expected. Claim your access before this launch closes.",
            "cta_close": "Start now and lock in consistent evenings.",
        }
        if context == "strategy_v2.agent0_output":
            payload = {
                "category_classification": {"primary": "sleep-support"},
                "strategy_habitats": [
                    {
                        "habitat_name": "reddit.com/r/sleep",
                        "habitat_type": "TEXT_COMMUNITY",
                        "url_pattern": "reddit.com/r/sleep",
                    }
                ],
                "apify_configs_tier1": [
                    {
                        "config_id": "tier1_reddit_sleep",
                        "actor_id": "practicaltools/apify-reddit-api",
                        "input": {
                            "startUrls": [{"url": "https://www.reddit.com/r/sleep"}],
                            "maxItems": 15,
                        },
                        "metadata": {
                            "target_id": "HT-001",
                            "platform": "reddit",
                            "mode": "subreddit_search",
                            "habitat_name": "reddit.com/r/sleep",
                            "habitat_type": "TEXT_COMMUNITY",
                        },
                    }
                ],
                "apify_configs_tier2": [
                    {
                        "config_id": "tier2_web_sleep",
                        "actor_id": "practicaltools/apify-reddit-api",
                        "input": {
                            "startUrls": [{"url": "https://www.reddit.com/r/Parenting"}],
                            "maxItems": 12,
                        },
                        "metadata": {"tier": "tier2", "intent": "community_discovery"},
                    }
                ],
                "manual_queries": ["sleep routine collapse", "bedtime routine fails"],
                "handoff_block": "Target caregiver communities with high frustration density.",
            }
        elif context == "strategy_v2.agent0b_output":
            payload = {
                "platform_priorities": ["tiktok", "instagram"],
                "configurations": [
                    {
                        "config_id": "tiktok_viral_01",
                        "platform": "tiktok",
                        "mode": "VIRAL_DISCOVERY",
                        "actor_id": "clockworks/tiktok-scraper",
                        "input": {
                            "profiles": ["https://www.tiktok.com/@duolingo"],
                            "maxItems": 20,
                        },
                        "metadata": {"priority": "high"},
                        "hook_theme": "timing failure",
                    },
                ],
                "handoff_block": "Focus on high-retention short-form educational clips.",
            }
        elif context == "strategy_v2.agent1_output":
            payload = {
                "report_markdown": "## Agent 1\nValidated runtime file coverage.",
                "agent_id": "agent1-test",
                "agent_version": "test.v1",
                "timestamp": "2026-03-08T23:00:00Z",
                "product_classification": {
                    "buyer_behavior": "CONSIDERED",
                    "purchase_emotion": "MIXED",
                "compliance_sensitivity": "MEDIUM",
                "price_sensitivity": "MID_TICKET_30_TO_100",
            },
            "file_assessments": _agent1_file_assessments_from_uploaded_manifest(),
            "observations": _agent1_observations_from_uploaded_manifest(),
            "gate_failures": [],
            "disconfirmation_flags": [
                "A small number of files could be noisy.",
                "Observed intent may cluster around adjacent problems.",
                "Platform mix may overweight text-based discussion.",
                ],
            }
        elif context == "strategy_v2.agent2_output":
            payload = {
                "mode": "DUAL",
                "input_count": len(_agent2_voc_observations_payload()),
                "output_count": len(_agent2_voc_observations_payload()),
                "decisions_by_evidence_id": _agent2_decisions_payload(),
                "accepted_observations": _agent2_accepted_observations_payload(),
                "validation_errors": [],
            }
        elif context == "strategy_v2.agent3_output":
            payload = {
                "angle_observations": _agent3_angle_observations_payload(),
                "angle_candidates": _agent3_angle_candidates_payload(),
            }
        elif context == "strategy_v2.offer.step01":
            payload = {
                "step_01_output": "## Avatar Synthesis\n- Caregivers under nightly routine pressure.",
                "key_findings": ["Stress spikes at bedtime", "High failure fatigue", "Price sensitivity present"],
            }
        elif context == "strategy_v2.offer.step02":
            payload = {
                "step_02_output": "## Calibration\n- Problem-aware market with medium sophistication.",
                "calibration": {
                    "awareness_level": {"assessment": "problem-aware"},
                    "sophistication_level": {"assessment": "medium"},
                    "lifecycle_stage": {"assessment": "growth"},
                    "competitor_count": 3,
                },
                "awareness_angle_matrix": {
                    "angle_name": "Mechanism-first relief",
                    "awareness_framing": {
                        "unaware": {
                            "frame": "narrative first",
                            "headline_direction": "curiosity lead",
                            "entry_emotion": "uncertain",
                            "exit_belief": "a hidden mechanism is involved",
                        },
                        "problem_aware": {
                            "frame": "name the pain",
                            "headline_direction": "problem crystallization",
                            "entry_emotion": "frustration",
                            "exit_belief": "the trigger pattern is explainable",
                        },
                        "solution_aware": {
                            "frame": "differentiate mechanism",
                            "headline_direction": "category contrast",
                            "entry_emotion": "skeptical hope",
                            "exit_belief": "mechanism-fit matters",
                        },
                        "product_aware": {
                            "frame": "implementation clarity",
                            "headline_direction": "proof plus process",
                            "entry_emotion": "cautious interest",
                            "exit_belief": "this solution is operationally clear",
                        },
                        "most_aware": {
                            "frame": "offer-first close",
                            "headline_direction": "direct action CTA",
                            "entry_emotion": "purchase readiness",
                            "exit_belief": "acting now is low risk",
                        },
                    },
                    "constant_elements": ["Core promise continuity"],
                    "variable_elements": ["headline", "proof", "cta"],
                    "product_name_first_appears": "product_aware",
                },
            }
        elif context == "strategy_v2.offer.step03":
            payload = {
                "pairs": [
                    {
                        "pair_id": "pair-a",
                        "ump_name": "Mechanism Gap",
                        "ums_name": "Evidence Protocol",
                        "dimensions": {
                            "competitive_uniqueness": {"score": 8, "evidence_quality": "OBSERVED"},
                            "voc_groundedness": {"score": 8, "evidence_quality": "OBSERVED"},
                            "believability": {"score": 7, "evidence_quality": "INFERRED"},
                            "mechanism_clarity": {"score": 8, "evidence_quality": "INFERRED"},
                            "angle_alignment": {"score": 9, "evidence_quality": "OBSERVED"},
                            "compliance_safety": {"score": 8, "evidence_quality": "OBSERVED"},
                            "memorability": {"score": 7, "evidence_quality": "INFERRED"},
                        },
                    },
                    {
                        "pair_id": "pair-b",
                        "ump_name": "Trigger Loop",
                        "ums_name": "Clarity Framework",
                        "dimensions": {
                            "competitive_uniqueness": {"score": 7, "evidence_quality": "INFERRED"},
                            "voc_groundedness": {"score": 8, "evidence_quality": "OBSERVED"},
                            "believability": {"score": 8, "evidence_quality": "INFERRED"},
                            "mechanism_clarity": {"score": 8, "evidence_quality": "OBSERVED"},
                            "angle_alignment": {"score": 8, "evidence_quality": "OBSERVED"},
                            "compliance_safety": {"score": 8, "evidence_quality": "OBSERVED"},
                            "memorability": {"score": 6, "evidence_quality": "INFERRED"},
                        },
                    },
                    {
                        "pair_id": "pair-c",
                        "ump_name": "Belief Trap",
                        "ums_name": "Belief Method",
                        "dimensions": {
                            "competitive_uniqueness": {"score": 7, "evidence_quality": "INFERRED"},
                            "voc_groundedness": {"score": 7, "evidence_quality": "OBSERVED"},
                            "believability": {"score": 8, "evidence_quality": "OBSERVED"},
                            "mechanism_clarity": {"score": 7, "evidence_quality": "INFERRED"},
                            "angle_alignment": {"score": 8, "evidence_quality": "OBSERVED"},
                            "compliance_safety": {"score": 9, "evidence_quality": "OBSERVED"},
                            "memorability": {"score": 7, "evidence_quality": "INFERRED"},
                        },
                    },
                ]
            }
        elif context == "strategy_v2.offer.step04":
            payload = {"variants": _offer_variants_payload()}
        elif context == "strategy_v2.offer.step05":
            payload = {
                "evaluation": _step05_evaluation_payload(),
                "revision_notes": "Improve weakest differentiators while preserving compliance safety.",
            }
        elif context == "strategy_v2.copy.headline_generation":
            payload = {
                "headline_candidates": [
                    "Why evenings keep undoing your whole day",
                    "The bedtime mechanism most routines miss",
                    "A predictable night routine without guesswork",
                ]
            }
        elif context == "strategy_v2.copy.promise_contract":
            payload = {
                "loop_question": "What changes when bedtime triggers are handled correctly?",
                "specific_promise": "Predictable evenings with lower stress and fewer resets.",
                "delivery_test": "Show mechanism mismatch, practical correction path, and evidence language.",
                "minimum_delivery": "Deliver by midpoint with clear implementation detail.",
            }
        elif context == "strategy_v2.copy.advertorial_template_payload":
            payload = {
                "template_payload": advertorial_template_payload,
            }
        elif context == "strategy_v2.copy.advertorial":
            payload = {
                "markdown": (
                    "# Approved Headline\n\n"
                    "## Hook/Lead\n"
                    "Predictable evenings are possible when you stop chasing random fixes.\n\n"
                    "## Problem Crystallization\n"
                    "The core pain is a routine bottleneck: stress spikes and the same problem repeats nightly.\n\n"
                    "## Failed Solutions\n"
                    "Families tried quick hacks, failed to hold the routine, and still ended up resetting the next day.\n\n"
                    "## Mechanism Reveal\n"
                    "The mechanism is timing mismatch, not lack of effort. Fix the mechanism and evenings stabilize.\n\n"
                    "## Proof + Bridge\n"
                    "Proof from real buyer language shows the mechanism shift works, and the offer bridges to implementation.\n\n"
                    "## Transition CTA\n"
                    "See the full offer and next-step system details now.\n"
                    "[Continue to the offer](/sales-page)."
                ),
                "template_payload": advertorial_template_payload,
            }
        elif context == "strategy_v2.copy.sales_template_payload_direct":
            payload = {
                "template_payload_json": json.dumps(sales_template_payload),
            }
        elif context == "strategy_v2.copy.sales_page_markdown":
            payload = {
                "markdown": (
                    "# Approved Headline — Sales Page\n\n"
                    "## Hero Stack\n"
                    "Offer summary: predictable evenings with a practical implementation system.\n"
                    "[Start the offer](/checkout).\n\n"
                    "## Problem Recap\n"
                    "The main struggle is repeated nighttime friction and stress from an unresolved bottleneck.\n\n"
                    "## Mechanism + Comparison\n"
                    "This mechanism-first method differs from generic routines and explains why older approaches fail.\n\n"
                    "## Identity Bridge\n"
                    "You are not inconsistent; the pain came from advice that ignored your real constraint.\n\n"
                    "## Social Proof\n"
                    "Proof includes direct buyer language, practical results, and evidence from lived routines.\n\n"
                    "## CTA #1\n"
                    "Get the full offer now with clear onboarding steps.\n"
                    "[Claim the system](/checkout).\n\n"
                    "## What's Inside\n"
                    "Inside the value stack: implementation checklist, timeline map, and decision support docs.\n\n"
                    "## Bonus Stack + Value\n"
                    "Bonus value stack includes rapid-start templates and scenario examples.\n\n"
                    "## Guarantee\n"
                    "Guarantee: 30-day confidence guarantee with compliance-safe expectations and safety guidance.\n\n"
                    "## CTA #2\n"
                    "Move forward with the offer while momentum is high.\n"
                    "[Start now](/checkout).\n\n"
                    "## FAQ\n"
                    "Proof and compliance notes: what this includes, what it does not claim, and safe usage boundaries.\n\n"
                    "## CTA #3 + P.S.\n"
                    "Final offer step: start today. Price: $49 one-time.\n"
                    "[Complete checkout](/checkout)."
                ),
            }
        elif context == "strategy_v2.copy.sales_template_payload":
            payload = {
                "template_payload_json": json.dumps(sales_template_payload),
            }
        elif context == "strategy_v2.copy.sales_page":
            payload = {
                "markdown": (
                    "# Approved Headline — Sales Page\n\n"
                    "## Hero Stack\n"
                    "Offer summary: predictable evenings with a practical implementation system.\n"
                    "[Start the offer](/checkout).\n\n"
                    "## Problem Recap\n"
                    "The main struggle is repeated nighttime friction and stress from an unresolved bottleneck.\n\n"
                    "## Mechanism + Comparison\n"
                    "This mechanism-first method differs from generic routines and explains why older approaches fail.\n\n"
                    "## Identity Bridge\n"
                    "You are not inconsistent; the pain came from advice that ignored your real constraint.\n\n"
                    "## Social Proof\n"
                    "Proof includes direct buyer language, practical results, and evidence from lived routines.\n\n"
                    "## CTA #1\n"
                    "Get the full offer now with clear onboarding steps.\n"
                    "[Claim the system](/checkout).\n\n"
                    "## What's Inside\n"
                    "Inside the value stack: implementation checklist, timeline map, and decision support docs.\n\n"
                    "## Bonus Stack + Value\n"
                    "Bonus value stack includes rapid-start templates and scenario examples.\n\n"
                    "## Guarantee\n"
                    "Guarantee: 30-day confidence guarantee with compliance-safe expectations and safety guidance.\n\n"
                    "## CTA #2\n"
                    "Move forward with the offer while momentum is high.\n"
                    "[Start now](/checkout).\n\n"
                    "## FAQ\n"
                    "Proof and compliance notes: what this includes, what it does not claim, and safe usage boundaries.\n\n"
                    "## CTA #3 + P.S.\n"
                    "Final offer step: start today. Price: $49 one-time.\n"
                    "[Complete checkout](/checkout)."
                ),
                "template_payload": sales_template_payload,
            }
        else:
            raise AssertionError(f"Unexpected prompt context in test stub: {context}")

        return payload, json.dumps(payload), {
            "context": context,
            "version": "test.v1",
            "prompt_path": f"/tests/{context}.md",
            "prompt_sha256": "test-sha256",
            "model_name": "test-model",
            "input_contract_version": "2.0.0",
            "output_contract_version": "2.0.0",
        }

    monkeypatch.setattr(strategy_v2_activities, "resolve_prompt_asset", _resolve_prompt_asset_stub)
    monkeypatch.setattr(strategy_v2_activities, "_run_prompt_json_object", _fake_run_prompt_json_object)


def _stub_ingest_strategy_v2_asset_data(**kwargs: Any) -> dict[str, Any]:
    apify_configs_raw = kwargs.get("apify_configs")
    apify_configs = (
        [row for row in apify_configs_raw if isinstance(row, dict)]
        if isinstance(apify_configs_raw, list)
        else []
    )
    config_count = len(apify_configs)
    first_config = apify_configs[0] if apify_configs else {}
    metadata = first_config.get("metadata") if isinstance(first_config.get("metadata"), dict) else {}
    config_id = str(first_config.get("config_id") or "cfg-1")
    target_id = str(metadata.get("target_id") or "HT-001")
    return {
        "candidate_assets": [],
        "social_video_observations": [],
        "external_voc_corpus": [
            {
                "voc_id": "APIFY_V0001",
                "source_url": "https://www.reddit.com/r/sleep/comments/abc123/example",
                "source_type": "REDDIT",
                "source_author": "user-1",
                "source_date": "2026-02-01",
                "quote": "Night routines keep failing after two days.",
                "compliance_risk": "YELLOW",
            }
        ],
        "proof_asset_candidates": [],
        "raw_runs": [
            {
                "actor_id": "practicaltools/apify-reddit-api",
                "run_id": "run-1",
                "dataset_id": "dataset-1",
                "config_id": config_id,
                "status": "SUCCEEDED",
                "config_metadata": {
                    "target_id": target_id,
                    "platform": "reddit",
                    "habitat_name": "reddit.com/r/sleep",
                    "habitat_type": "TEXT_COMMUNITY",
                },
                "input_payload": {
                    "startUrls": [{"url": "https://www.reddit.com/r/sleep"}],
                },
                "items": [
                    {
                        "source_url": "https://www.reddit.com/r/sleep/comments/abc123/example",
                        "title": "Example post",
                        "body": "Night routines keep failing after two days.",
                        "subreddit": "sleep",
                    }
                ],
            }
        ],
        "summary": {
            "strategy_config_run_count": config_count,
            "planned_actor_run_count": max(config_count, 1),
        },
    }


def _create_client_and_product(
    *,
    api_client,
    suffix: str,
    strategy_v2_enabled: bool,
    include_description: bool = True,
) -> tuple[str, str]:
    client_resp = api_client.post(
        "/clients",
        json={
            "name": f"Strategy {suffix}",
            "industry": "SaaS",
            "strategyV2Enabled": strategy_v2_enabled,
        },
    )
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    product_payload = {
        "clientId": client_id,
        "title": f"Product {suffix}",
    }
    if include_description:
        product_payload["description"] = "Product description"
    product_resp = api_client.post("/products", json=product_payload)
    assert product_resp.status_code == 201
    product_id = product_resp.json()["id"]
    return client_id, product_id


def _selected_angle_payload() -> dict:
    return {
        "angle_id": "A01",
        "angle_name": "Mechanism-first relief",
        "definition": {
            "who": "Busy caregivers",
            "pain_desire": "Overwhelm -> calm routine",
            "mechanism_why": "Mismatch between symptom and intervention timing",
            "belief_shift": {
                "before": "More effort will fix this",
                "after": "Correct timing unlocks predictable relief",
            },
            "trigger": "Late evening symptom spikes",
        },
        "evidence": {
            "supporting_voc_count": 5,
            "top_quotes": [
                {
                    "voc_id": "V001",
                    "quote": "I keep trying more things but nights still spiral.",
                    "adjusted_score": 82.0,
                },
                {
                    "voc_id": "V002",
                    "quote": "The routine collapses right when I need consistency most.",
                    "adjusted_score": 79.5,
                },
                {
                    "voc_id": "V003",
                    "quote": "I need a plan that still works when evenings get chaotic.",
                    "adjusted_score": 77.8,
                },
                {
                    "voc_id": "V004",
                    "quote": "We spent money on random fixes and still feel stuck.",
                    "adjusted_score": 76.2,
                },
                {
                    "voc_id": "V005",
                    "quote": "I want a clear system instead of guessing every night.",
                    "adjusted_score": 74.0,
                },
            ],
            "triangulation_status": "DUAL",
            "velocity_status": "STEADY",
            "contradiction_count": 0,
        },
        "hook_starters": [
            {
                "visual": "Parent at kitchen table",
                "opening_line": "Why evenings keep undoing your whole day.",
                "lever": "problem crystallization",
            }
        ],
    }


def _manual_hitl_fields(*, operator_note: str) -> dict[str, Any]:
    return {
        "decision_mode": "manual",
        "attestation": {
            "reviewed_evidence": True,
            "understands_impact": True,
        },
        "operator_note": operator_note,
    }


def _agent3_angle_candidates_payload(min_count: int = 10) -> list[dict]:
    candidates: list[dict] = []
    for index in range(min_count):
        candidate = _selected_angle_payload()
        candidate["angle_id"] = f"A{index + 1:02d}"
        candidate["angle_name"] = f"Mechanism-first relief {index + 1}"
        candidate["definition"]["trigger"] = f"Late evening symptom spikes #{index + 1}"
        candidates.append(candidate)
    return candidates


def _agent2_voc_observations_payload() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    quotes = [
        "I spent $300 on fixes and nights still fall apart after one bad evening.",
        "Every bedtime we panic because nothing we've tried sticks for more than two days.",
        "I want a step-by-step routine that works even when work runs late.",
        "I thought more supplements would fix it, but timing is what keeps breaking.",
        "I need a predictable plan so I stop feeling like I'm failing every night.",
    ]
    for index, quote in enumerate(quotes):
        rows.append(
            {
                "voc_id": f"V{index + 1:03d}",
                "evidence_id": f"E{index + 1:016X}",
                "source": "https://www.reddit.com/r/sleep" if index % 2 == 0 else "https://forum.sleephelp.com/thread",
                "source_type": "REDDIT" if index % 2 == 0 else "FORUM",
                "source_url": "https://www.reddit.com/r/sleep" if index % 2 == 0 else "https://forum.sleephelp.com/thread",
                "source_author": f"user_{index + 1}",
                "source_date": "2026-02-20",
                "is_hook": "N",
                "hook_format": "NONE",
                "hook_word_count": 0,
                "video_virality_tier": "BASELINE",
                "video_view_count": 0,
                "competitor_saturation": [],
                "in_whitespace": "Y",
                "evidence_ref": f"evidence::item[{index}]",
                "quote": quote,
                "specific_number": "Y" if "$" in quote else "N",
                "specific_product_brand": "N",
                "specific_event_moment": "Y",
                "specific_body_symptom": "N",
                "before_after_comparison": "Y",
                "crisis_language": "Y",
                "profanity_extreme_punctuation": "N",
                "physical_sensation": "N",
                "identity_change_desire": "Y",
                "word_count": max(12, len(quote.split())),
                "clear_trigger_event": "Y",
                "named_enemy": "N",
                "shiftable_belief": "Y",
                "expectation_vs_reality": "Y",
                "headline_ready": "Y",
                "usable_content_pct": "OVER_75_PCT",
                "personal_context": "Y",
                "long_narrative": "Y",
                "engagement_received": "Y",
                "real_person_signals": "Y",
                "moderated_community": "Y",
                "trigger_event": "Bedtime routine collapses after stress spike",
                "pain_problem": "Repeated nighttime breakdown despite trying many fixes",
                "desired_outcome": "Predictable nights without panic",
                "failed_prior_solution": "Random routines and supplement stacks failed",
                "enemy_blame": "Generic advice that ignores timing",
                "identity_role": "Exhausted caregiver",
                "fear_risk": "Fear of ongoing family burnout",
                "emotional_valence": "FRUSTRATION" if index % 2 == 0 else "ANXIETY",
                "durable_psychology": "Y",
                "market_specific": "N",
                "date_bracket": "LAST_6MO",
                "buyer_stage": "problem aware",
                "solution_sophistication": "EXPERIENCED",
                "compliance_risk": "GREEN",
            }
        )
    return rows


def _agent1_file_assessments_from_uploaded_manifest() -> dict[str, dict[str, Any]]:
    uploaded_payloads = getattr(strategy_v2_activities, "_TEST_STUB_PROMPT_LOGICAL_PAYLOADS", {})
    agent1_payloads = uploaded_payloads.get("agent1-prompt-chain")
    if not isinstance(agent1_payloads, dict):
        raise AssertionError("Agent 1 test stub is missing uploaded logical payloads for agent1-prompt-chain.")

    scraped_data_manifest = agent1_payloads.get("SCRAPED_DATA_FILES_JSON")
    if not isinstance(scraped_data_manifest, dict):
        raise AssertionError("Agent 1 test stub expected SCRAPED_DATA_FILES_JSON in uploaded logical payloads.")

    raw_files = scraped_data_manifest.get("raw_scraped_data_files")
    raw_file_rows = [row for row in raw_files if isinstance(row, dict)] if isinstance(raw_files, list) else []
    if not raw_file_rows:
        raise AssertionError("Agent 1 test stub expected raw_scraped_data_files to contain at least one file.")

    assessments: dict[str, dict[str, Any]] = {}
    for index, file_row in enumerate(raw_file_rows):
        source_file = str(file_row.get("file_name") or "").strip()
        if not source_file:
            continue
        habitat_name = str(file_row.get("habitat_name") or source_file).strip()
        habitat_type = str(file_row.get("habitat_type") or "TEXT_COMMUNITY").strip() or "TEXT_COMMUNITY"
        observation = _agent1_habitat_observation_payload(
            habitat_name=habitat_name,
            habitat_type=habitat_type,
            source_file=source_file,
        )
        observation["url_pattern"] = str(file_row.get("virtual_path") or habitat_name).strip() or habitat_name
        observation["items_in_file"] = int(file_row.get("item_count") or observation["items_in_file"])
        assessments[source_file] = _agent1_file_assessment_payload(
            observation=observation,
            include_in_mining_plan=index == 0,
        )

    if not assessments:
        raise AssertionError("Agent 1 test stub could not derive any file assessments from the uploaded manifest.")
    return assessments


def _agent1_observations_from_uploaded_manifest() -> list[dict[str, Any]]:
    uploaded_payloads = getattr(strategy_v2_activities, "_TEST_STUB_PROMPT_LOGICAL_PAYLOADS", {})
    agent1_payloads = uploaded_payloads.get("agent1-prompt-chain")
    if not isinstance(agent1_payloads, dict):
        raise AssertionError("Agent 1 test stub is missing uploaded logical payloads for agent1-prompt-chain.")

    scraped_data_manifest = agent1_payloads.get("SCRAPED_DATA_FILES_JSON")
    if not isinstance(scraped_data_manifest, dict):
        raise AssertionError("Agent 1 test stub expected SCRAPED_DATA_FILES_JSON in uploaded logical payloads.")

    raw_files = scraped_data_manifest.get("raw_scraped_data_files")
    raw_file_rows = [row for row in raw_files if isinstance(row, dict)] if isinstance(raw_files, list) else []
    observations: list[dict[str, Any]] = []
    for index, file_row in enumerate(raw_file_rows):
        source_file = str(file_row.get("file_name") or "").strip()
        if not source_file:
            continue
        habitat_name = str(file_row.get("habitat_name") or source_file).strip()
        habitat_type = str(file_row.get("habitat_type") or "TEXT_COMMUNITY").strip() or "TEXT_COMMUNITY"
        observation = _agent1_habitat_observation_payload(
            habitat_name=habitat_name,
            habitat_type=habitat_type,
            source_file=source_file,
        )
        observation["url_pattern"] = str(file_row.get("virtual_path") or habitat_name).strip() or habitat_name
        observation["items_in_file"] = int(file_row.get("item_count") or observation["items_in_file"])
        observations.append(
            _agent1_observation_payload(
                observation=observation,
                include_in_mining_plan=index == 0,
                priority_rank=1 if index == 0 else None,
            )
        )

    if not observations:
        raise AssertionError("Agent 1 test stub could not derive any observations from the uploaded manifest.")
    return observations


def _agent1_habitat_observation_payload(*, habitat_name: str, habitat_type: str, source_file: str) -> dict[str, Any]:
    observation_sheet = {
        "threads_50_plus": "Y",
        "threads_200_plus": "N",
        "threads_1000_plus": "N",
        "posts_last_3mo": "Y",
        "posts_last_6mo": "Y",
        "posts_last_12mo": "Y",
        "recency_ratio": "MAJORITY_RECENT",
        "exact_category": "Y",
        "purchasing_comparing": "Y",
        "personal_usage": "Y",
        "adjacent_only": "N",
        "first_person_narratives": "Y",
        "trigger_events": "Y",
        "fear_frustration_shame": "Y",
        "specific_dollar_or_time": "Y",
        "long_detailed_posts": "Y",
        "comparison_discussions": "Y",
        "price_value_mentions": "Y",
        "post_purchase_experience": "Y",
        "relevance_pct": "OVER_50_PCT",
        "dominated_by_offtopic": "N",
        "competitor_brands_mentioned": "Y",
        "competitor_brand_count": "1-3",
        "competitor_ads_present": "N",
        "trend_direction": "HIGHER",
        "seasonal_patterns": "N",
        "seasonal_description": "N/A",
        "habitat_age": "3_TO_7YR",
        "membership_trend": "GROWING",
        "post_frequency_trend": "INCREASING",
        "publicly_accessible": "Y",
        "text_based_content": "Y",
        "target_language": "Y",
        "no_rate_limiting": "Y",
        "purchase_intent_density": "SOME",
        "discusses_spending": "Y",
        "recommendation_threads": "Y",
        "reusability": "PATTERN_REUSABLE",
    }
    return {
        "habitat_name": habitat_name,
        "habitat_type": habitat_type,
        "url_pattern": habitat_name,
        "source_file": source_file,
        "items_in_file": 120,
        "data_quality": "CLEAN",
        "observation_sheet": observation_sheet,
        "language_samples": [
            {
                "sample_id": "S1",
                "evidence_ref": f"{source_file}::item[0]",
                "word_count": 180,
                "has_trigger_event": "Y",
                "has_failed_solution": "Y",
                "has_identity_language": "Y",
                "has_specific_outcome": "Y",
            }
        ],
        "video_extension": None,
        "competitive_overlap": {
            "competitors_in_data": ["Competitor A"],
            "overlap_level": "LOW",
            "whitespace_opportunity": "Y",
        },
        "trend_lifecycle": {
            "trend_direction": "HIGHER",
            "lifecycle_stage": "GROWING",
        },
        "mining_gate": {
            "status": "PASS",
            "failed_fields": [],
            "reason": "All mining requirements satisfied.",
        },
        "rank_score": 81,
        "estimated_yield": 28,
        "evidence_refs": [f"{source_file}::item[0]"],
    }


def _agent1_file_assessment_payload(
    *,
    observation: dict[str, Any],
    include_in_mining_plan: bool,
) -> dict[str, Any]:
    return {
        "decision": "OBSERVE",
        "exclude_reason": "",
        "observation_id": f"obs-{observation['source_file'].replace('.', '-')}",
        "include_in_mining_plan": include_in_mining_plan,
    }


def _agent1_observation_payload(
    *,
    observation: dict[str, Any],
    include_in_mining_plan: bool,
    priority_rank: int | None = None,
) -> dict[str, Any]:
    return {
        "observation_id": f"obs-{observation['source_file'].replace('.', '-')}",
        "habitat_name": observation["habitat_name"],
        "habitat_type": observation["habitat_type"],
        "url_pattern": observation["url_pattern"],
        "items_in_file": observation["items_in_file"],
        "data_quality": observation["data_quality"],
        "observation_sheet": observation["observation_sheet"],
        "language_samples": observation["language_samples"],
        "video_extension": observation["video_extension"],
        "competitive_overlap": observation["competitive_overlap"],
        "trend_lifecycle": observation["trend_lifecycle"],
        "mining_gate": observation["mining_gate"],
        "rank_score": observation["rank_score"],
        "estimated_yield": observation["estimated_yield"],
        "evidence_refs": observation["evidence_refs"],
        "priority_rank": priority_rank,
        "target_voc_types": ["PAIN_LANGUAGE"] if include_in_mining_plan else [],
        "sampling_strategy": (
            "Process chronologically across high-detail items first."
            if include_in_mining_plan
            else None
        ),
        "platform_behavior_note": (
            "Long-form narratives with high detail density."
            if include_in_mining_plan
            else None
        ),
        "compliance_flags": "",
    }


def _agent2_decisions_payload() -> dict[str, dict[str, Any]]:
    decisions: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(_agent2_voc_observations_payload(), start=1):
        evidence_id = str(row["evidence_id"])
        decisions[evidence_id] = {
            "decision": "ACCEPT",
            "observation_id": f"obs-{index:03d}",
            "reason": None,
            "note": "",
        }
    return decisions


def _agent2_accepted_observations_payload() -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for index, row in enumerate(_agent2_voc_observations_payload(), start=1):
        observations.append(
            {
                "observation_id": f"obs-{index:03d}",
                "quote": row["quote"],
                "is_hook": row["is_hook"],
                "hook_format": row["hook_format"],
                "hook_word_count": row["hook_word_count"],
                "video_virality_tier": row["video_virality_tier"],
                "video_view_count": row["video_view_count"],
                "competitor_saturation": row["competitor_saturation"],
                "in_whitespace": row["in_whitespace"],
                "specific_number": row["specific_number"],
                "specific_product_brand": row["specific_product_brand"],
                "specific_event_moment": row["specific_event_moment"],
                "specific_body_symptom": row["specific_body_symptom"],
                "before_after_comparison": row["before_after_comparison"],
                "crisis_language": row["crisis_language"],
                "profanity_extreme_punctuation": row["profanity_extreme_punctuation"],
                "physical_sensation": row["physical_sensation"],
                "identity_change_desire": row["identity_change_desire"],
                "word_count": row["word_count"],
                "clear_trigger_event": row["clear_trigger_event"],
                "named_enemy": row["named_enemy"],
                "shiftable_belief": row["shiftable_belief"],
                "expectation_vs_reality": row["expectation_vs_reality"],
                "headline_ready": row["headline_ready"],
                "usable_content_pct": row["usable_content_pct"],
                "personal_context": row["personal_context"],
                "long_narrative": row["long_narrative"],
                "engagement_received": row["engagement_received"],
                "real_person_signals": row["real_person_signals"],
                "moderated_community": row["moderated_community"],
                "trigger_event": row["trigger_event"],
                "pain_problem": row["pain_problem"],
                "desired_outcome": row["desired_outcome"],
                "failed_prior_solution": row["failed_prior_solution"],
                "enemy_blame": row["enemy_blame"],
                "identity_role": row["identity_role"],
                "fear_risk": row["fear_risk"],
                "emotional_valence": row["emotional_valence"],
                "durable_psychology": row["durable_psychology"],
                "market_specific": row["market_specific"],
                "date_bracket": row["date_bracket"],
                "buyer_stage": row["buyer_stage"],
                "solution_sophistication": row["solution_sophistication"],
                "compliance_risk": row["compliance_risk"],
            }
        )
    return observations


def _agent3_angle_observations_payload(min_count: int = 10) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(min_count):
        rows.append(
            {
                "angle_id": f"A{index + 1:02d}",
                "angle_name": f"Mechanism-first relief {index + 1}",
                "distinct_voc_items": 10 + index,
                "distinct_authors": 6 + index,
                "intensity_spike_count": 4 + (index % 3),
                "sleeping_giant_count": 2 + (index % 2),
                "aspiration_gap_4plus": "Y" if index % 2 == 0 else "N",
                "avg_adjusted_score": 64.0 + index,
                "crisis_language_count": 3 + (index % 2),
                "dollar_time_loss_count": 3 + (index % 3),
                "physical_symptom_count": 1 + (index % 2),
                "rage_shame_anxiety_count": 4 + (index % 3),
                "exhausted_sophistication_count": 2 + (index % 2),
                "product_addresses_pain": "Y",
                "product_feature_maps_to_mechanism": "Y",
                "outcome_achievable": "Y",
                "mechanism_factually_supportable": "Y",
                "supporting_voc_count": 6 + index,
                "items_above_60": 5 + (index % 3),
                "triangulation_status": "MULTI" if index % 2 == 0 else "DUAL",
                "contradiction_count": index % 2,
                "source_habitat_types": 3,
                "dominant_source_pct": 55.0,
                "green_count": 8,
                "yellow_count": 2,
                "red_count": 0,
                "expressible_without_red": "Y",
                "requires_disease_naming": "N",
                "velocity_status": "ACCELERATING" if index < 5 else "STEADY",
                "stage_UNAWARE_count": 1 + (index % 2),
                "stage_PROBLEM_AWARE_count": 3,
                "stage_SOLUTION_AWARE_count": 2,
                "stage_PRODUCT_AWARE_count": 2,
                "stage_MOST_AWARE_count": 1,
                "pain_chronicity": "CHRONIC",
                "trigger_seasonality": "ONGOING",
                "competitor_count_using_angle": "1-2",
                "recent_competitor_entry": "Y" if index % 3 == 0 else "N",
                "competitor_angle_overlap": "N",
                "pain_structural": "Y",
                "news_cycle_dependent": "N",
                "competitor_behavior_dependent": "N",
                "single_visual_expressible": "Y",
                "hook_under_12_words": "Y",
                "natural_villain_present": "Y",
                "language_registry_headline_exists": "Y",
                "segment_breadth": "MODERATE" if index % 2 == 0 else "BROAD",
                "pain_universality": "MODERATE" if index % 2 == 0 else "UNIVERSAL",
                "sa0_different_who": "Y",
                "sa0_different_trigger": "Y",
                "sa0_different_enemy": "Y",
                "sa0_different_belief": "Y",
                "sa0_different_mechanism": "Y",
            }
        )
    return rows


def _mock_scored_angles() -> dict[str, Any]:
    return {
        "angles": [
            {
                "angle_id": "A01",
                "final_score": 87.0,
                "confidence_range": (78.0, 94.0),
                "rank": 1,
                "components": {"demand_signal": 34.0, "evidence_quality": 42.0},
                "evidence_floor_gate": False,
            },
            {
                "angle_id": "A02",
                "final_score": 79.0,
                "confidence_range": (69.0, 88.0),
                "rank": 2,
                "components": {"demand_signal": 28.0, "evidence_quality": 35.0},
                "evidence_floor_gate": False,
            },
            {
                "angle_id": "A03",
                "final_score": 71.0,
                "confidence_range": (61.0, 82.0),
                "rank": 3,
                "components": {"demand_signal": 22.0, "evidence_quality": 31.0},
                "evidence_floor_gate": False,
            },
        ],
        "summary": {
            "total_angles": 3,
            "mean_score": 79.0,
            "std_score": 8.0,
            "gates_applied": 0,
            "lifecycle_distribution": {"EARLY_GROWTH": 3},
        },
    }


def test_extract_step4_entries_supports_bullets_and_multiline_quotes():
    content = """
- SOURCE: reddit.com/r/herbalism
- CATEGORY: H
- EMOTION: frustration
- INTENSITY: high
- BUYER_STAGE: problem aware
- SEGMENT_HINT: caregivers
"I keep trying routines
and nights still spiral."

SOURCE: forum.example.com
CATEGORY: C
EMOTION: hope
INTENSITY: medium
BUYER_STAGE: solution aware
SEGMENT_HINT: parents
"I want a routine that doesn't collapse after two days."
""".strip()

    entries = strategy_v2_activities._extract_step4_entries(content)
    assert len(entries) == 2
    assert entries[0]["source"] == "reddit.com/r/herbalism"
    assert "nights still spiral" in entries[0]["quote"]
    assert entries[1]["source"] == "forum.example.com"
    assert entries[1]["category"] == "C"


def test_extract_step4_entries_raises_when_no_tagged_blocks():
    with pytest.raises(StrategyV2MissingContextError):
        strategy_v2_activities._extract_step4_entries("no tagged blocks here")


def test_resolve_brand_voice_notes_requires_explicit_or_onboarding_context():
    stage2_stub = type("Stage2Stub", (), {"product_name": "Test Product"})()
    assert strategy_v2_activities._resolve_brand_voice_notes(
        explicit_notes="Direct, concrete, no hype.",
        onboarding_payload={},
        stage2=stage2_stub,  # type: ignore[arg-type]
    ) == "Direct, concrete, no hype."
    assert strategy_v2_activities._resolve_brand_voice_notes(
        explicit_notes="",
        onboarding_payload={"brand_voice_notes": "Grounded and practical."},
        stage2=stage2_stub,  # type: ignore[arg-type]
    ) == "Grounded and practical."

    with pytest.raises(StrategyV2MissingContextError):
        strategy_v2_activities._resolve_brand_voice_notes(
            explicit_notes="",
            onboarding_payload={"brand_story": "Not accepted as brand voice context anymore."},
            stage2=stage2_stub,  # type: ignore[arg-type]
        )


def test_normalize_novelty_classification_accepts_recognized_aliases():
    assert strategy_v2_activities._normalize_novelty_classification(
        "PACKAGING",
        field_name="variant.base.novelty",
    ) == "INCREMENTAL"
    assert strategy_v2_activities._normalize_novelty_classification(
        "Repackaged (structured, safety-first reference)",
        field_name="variant.base.novelty",
    ) == "INCREMENTAL"
    assert strategy_v2_activities._normalize_novelty_classification(
        "copycat",
        field_name="variant.base.novelty",
    ) == "REDUNDANT"
    assert strategy_v2_activities._normalize_novelty_classification(
        "novel",
        field_name="variant.base.novelty",
    ) == "NOVEL"
    assert strategy_v2_activities._normalize_novelty_classification(
        "Differentiator (interaction-aware organization)",
        field_name="variant.base.novelty",
    ) == "NOVEL"
    assert strategy_v2_activities._normalize_novelty_classification(
        "table_stakes",
        field_name="variant.base.novelty",
    ) == "INCREMENTAL"


def test_normalize_novelty_classification_rejects_unknown_values():
    with pytest.raises(StrategyV2SchemaValidationError):
        strategy_v2_activities._normalize_novelty_classification(
            "UNCLASSIFIED_WEIRD_BUCKET",
            field_name="variant.base.novelty",
        )


def test_normalize_angle_candidates_derives_supporting_voc_count_from_quotes():
    candidate = _selected_angle_payload()
    candidate["evidence"]["supporting_voc_count"] = 1

    normalized = strategy_v2_activities._normalize_angle_candidates([candidate])

    assert normalized[0]["evidence"]["supporting_voc_count"] == 5


def test_derive_awareness_level_primary_from_descriptive_assessment():
    calibration = {
        "awareness_level": {
            "assessment": (
                "Angle-specific dominant awareness is SOLUTION-AWARE "
                "(with a large PROBLEM-AWARE minority)."
            )
        }
    }
    assert strategy_v2_activities._derive_awareness_level_primary_from_calibration(calibration) == "Solution-Aware"


def test_derive_sophistication_level_from_descriptive_assessment():
    calibration = {
        "sophistication_level": {
            "assessment": (
                "Angle-specific sophistication is MODERATE but LOW-CONFIDENCE "
                "due to missing competitor assets."
            )
        }
    }
    assert strategy_v2_activities._derive_sophistication_level_from_calibration(calibration) == 3


def test_start_strategy_v2_requires_feature_flag(api_client, fake_temporal):
    client_id, product_id = _create_client_and_product(
        api_client=api_client,
        suffix="FlagOff",
        strategy_v2_enabled=False,
    )
    response = api_client.post(
        "/workflows/strategy-v2/start",
        json={"client_id": client_id, "product_id": product_id},
    )
    assert response.status_code == 409
    assert "Strategy V2 is disabled" in response.json()["detail"]
    assert fake_temporal.started == []


def test_start_strategy_v2_requires_product_description_or_override(api_client, fake_temporal):
    client_id, product_id = _create_client_and_product(
        api_client=api_client,
        suffix="MissingDescription",
        strategy_v2_enabled=True,
        include_description=False,
    )
    response = api_client.post(
        "/workflows/strategy-v2/start",
        json={
            "client_id": client_id,
            "product_id": product_id,
            "stage0_overrides": {"product_customizable": True},
            "business_model": "one-time",
            "funnel_position": "cold_traffic",
            "target_platforms": ["Meta"],
            "target_regions": ["US"],
            "existing_proof_assets": ["Customer testimonials"],
            "brand_voice_notes": "Direct, clear, non-hype voice.",
        },
    )
    assert response.status_code == 409
    assert "Product description is required" in response.json()["detail"]
    assert fake_temporal.started == []


def test_start_strategy_v2_allows_stage0_description_override(api_client, fake_temporal):
    client_id, product_id = _create_client_and_product(
        api_client=api_client,
        suffix="OverrideDescription",
        strategy_v2_enabled=True,
        include_description=False,
    )
    start = api_client.post(
        "/workflows/strategy-v2/start",
        json={
            "client_id": client_id,
            "product_id": product_id,
            "stage0_overrides": {
                "description": "Clear product description supplied at start.",
                "product_customizable": True,
            },
            "business_model": "one-time",
            "funnel_position": "cold_traffic",
            "target_platforms": ["Meta"],
            "target_regions": ["US"],
            "existing_proof_assets": ["Customer testimonials"],
            "brand_voice_notes": "Direct, clear, non-hype voice.",
        },
    )
    assert start.status_code == 200
    assert fake_temporal.started


def test_start_strategy_v2_and_send_all_hitl_signals(api_client, fake_temporal):
    client_id, product_id = _create_client_and_product(
        api_client=api_client,
        suffix="Signals",
        strategy_v2_enabled=True,
    )
    start = api_client.post(
        "/workflows/strategy-v2/start",
        json={
            "client_id": client_id,
            "product_id": product_id,
            "stage0_overrides": {"product_customizable": True},
            "business_model": "one-time",
            "funnel_position": "cold_traffic",
            "target_platforms": ["Meta"],
            "target_regions": ["US"],
            "existing_proof_assets": ["Customer testimonials"],
            "brand_voice_notes": "Direct, clear, non-hype voice.",
        },
    )
    assert start.status_code == 200
    run_id = start.json()["workflow_run_id"]
    assert fake_temporal.started

    proceed_research = api_client.post(
        f"/workflows/{run_id}/signals/strategy-v2/proceed-research",
        json={
            "proceed": True,
            **_manual_hitl_fields(
                operator_note="Reviewed foundational inputs and confirmed research should proceed.",
            ),
        },
    )
    assert proceed_research.status_code == 200

    confirm_assets = api_client.post(
        f"/workflows/{run_id}/signals/strategy-v2/confirm-competitor-assets",
        json={
            "confirmed_asset_refs": [
                "https://competitor-a.example/asset-1",
                "https://competitor-b.example/asset-2",
                "https://competitor-c.example/asset-3",
            ],
            "reviewed_candidate_ids": [
                "https://competitor-a.example/asset-1",
                "https://competitor-b.example/asset-2",
                "https://competitor-c.example/asset-3",
            ],
            **_manual_hitl_fields(
                operator_note="Reviewed three competitor assets and confirmed they are representative.",
            ),
        },
    )
    assert confirm_assets.status_code == 200

    angle_selection = api_client.post(
        f"/workflows/{run_id}/signals/strategy-v2/select-angle",
        json={
            "selected_angle": _selected_angle_payload(),
            "rejected_angle_ids": ["A02"],
            "reviewed_candidate_ids": ["A01", "A02"],
            **_manual_hitl_fields(
                operator_note="Selected the highest-evidence angle after reviewing candidate set.",
            ),
        },
    )
    assert angle_selection.status_code == 200

    ump_ums_selection = api_client.post(
        f"/workflows/{run_id}/signals/strategy-v2/select-ump-ums",
        json={
            "pair_id": "pair-a",
            "rejected_pair_ids": ["pair-b"],
            "reviewed_candidate_ids": ["pair-a", "pair-b"],
            **_manual_hitl_fields(
                operator_note="Selected pair-a because it best aligns with evidence and mechanism clarity.",
            ),
        },
    )
    assert ump_ums_selection.status_code == 200

    offer_winner = api_client.post(
        f"/workflows/{run_id}/signals/strategy-v2/select-offer-winner",
        json={
            "variant_id": "share_and_save",
            "rejected_variant_ids": ["family_bundle"],
            "reviewed_candidate_ids": ["share_and_save", "family_bundle"],
            **_manual_hitl_fields(
                operator_note="Variant A wins on composite score and decision confidence.",
            ),
        },
    )
    assert offer_winner.status_code == 200

    final_approval = api_client.post(
        f"/workflows/{run_id}/signals/strategy-v2/approve-final-copy",
        json={
            "approved": True,
            "reviewed_candidate_ids": ["copy-artifact-1"],
            **_manual_hitl_fields(
                operator_note="Reviewed copy quality gates and congruency checks; approved for launch.",
            ),
        },
    )
    assert final_approval.status_code == 200

    signal_names = [name for name, _args in fake_temporal.signals]
    assert "strategy_v2_proceed_research" in signal_names
    assert "strategy_v2_confirm_competitor_assets" in signal_names
    assert "strategy_v2_select_angle" in signal_names
    assert "strategy_v2_select_ump_ums" in signal_names
    assert "strategy_v2_select_offer_winner" in signal_names
    assert "strategy_v2_approve_final_copy" in signal_names


def test_strategy_v2_proceed_research_accepts_missing_attestation(api_client, fake_temporal):
    client_id, product_id = _create_client_and_product(
        api_client=api_client,
        suffix="AttestationRequired",
        strategy_v2_enabled=True,
    )
    start = api_client.post(
        "/workflows/strategy-v2/start",
        json={
            "client_id": client_id,
            "product_id": product_id,
            "stage0_overrides": {"product_customizable": True},
            "business_model": "one-time",
            "funnel_position": "cold_traffic",
            "target_platforms": ["Meta"],
            "target_regions": ["US"],
            "existing_proof_assets": ["Customer testimonials"],
            "brand_voice_notes": "Direct, clear, non-hype voice.",
        },
    )
    assert start.status_code == 200
    run_id = start.json()["workflow_run_id"]

    response = api_client.post(
        f"/workflows/{run_id}/signals/strategy-v2/proceed-research",
        json={
            "proceed": True,
        },
    )
    assert response.status_code == 200

    signal_names = [name for name, _args in fake_temporal.signals]
    assert "strategy_v2_proceed_research" in signal_names
    proceed_signal_args = next(args for name, args in fake_temporal.signals if name == "strategy_v2_proceed_research")
    proceed_payload = proceed_signal_args[0]
    assert proceed_payload["attestation"] == {
        "reviewed_evidence": True,
        "understands_impact": True,
    }


def test_workflow_research_artifact_endpoint_supports_artifact_scheme(
    api_client,
    db_session,
    auth_context,
):
    client_id, product_id = _create_client_and_product(
        api_client=api_client,
        suffix="ArtifactScheme",
        strategy_v2_enabled=True,
    )
    org_uuid = UUID(auth_context.org_id)
    client_uuid = UUID(client_id)
    product_uuid = UUID(product_id)

    workflow_run = WorkflowRun(
        org_id=org_uuid,
        client_id=client_uuid,
        product_id=product_uuid,
        campaign_id=None,
        temporal_workflow_id="strategy-v2-artifact-workflow",
        temporal_run_id="strategy-v2-artifact-run",
        kind=WorkflowKindEnum.strategy_v2,
    )
    db_session.add(workflow_run)
    db_session.commit()
    db_session.refresh(workflow_run)

    artifact = Artifact(
        org_id=org_uuid,
        client_id=client_uuid,
        product_id=product_uuid,
        campaign_id=None,
        type=ArtifactTypeEnum.strategy_v2_step_payload,
        data={"payload": {"hello": "world"}},
    )
    db_session.add(artifact)
    db_session.commit()
    db_session.refresh(artifact)

    research = ResearchArtifact(
        org_id=org_uuid,
        workflow_run_id=workflow_run.id,
        step_key="v2-01",
        title="Stage 0",
        doc_id=str(artifact.id),
        doc_url=f"artifact://{artifact.id}",
        prompt_sha256=None,
        summary="Stage 0 complete",
    )
    db_session.add(research)
    db_session.commit()

    response = api_client.get(f"/workflows/{workflow_run.id}/research/v2-01")
    assert response.status_code == 200
    payload = response.json()
    assert payload["step_key"] == "v2-01"
    assert payload["content"] == {"payload": {"hello": "world"}}


def test_strategy_v2_state_from_research_artifacts(api_client, db_session, auth_context):
    client_id, product_id = _create_client_and_product(
        api_client=api_client,
        suffix="StateFallback",
        strategy_v2_enabled=True,
    )
    org_uuid = UUID(auth_context.org_id)
    client_uuid = UUID(client_id)
    product_uuid = UUID(product_id)

    workflow_run = WorkflowRun(
        org_id=org_uuid,
        client_id=client_uuid,
        product_id=product_uuid,
        campaign_id=None,
        temporal_workflow_id="strategy-v2-state-workflow",
        temporal_run_id="strategy-v2-state-run",
        kind=WorkflowKindEnum.strategy_v2,
    )
    db_session.add(workflow_run)
    db_session.commit()
    db_session.refresh(workflow_run)

    step_artifact = Artifact(
        org_id=org_uuid,
        client_id=client_uuid,
        product_id=product_uuid,
        campaign_id=None,
        type=ArtifactTypeEnum.strategy_v2_step_payload,
        data={
            "payload": {
                "ranked_candidates": [
                    {
                        "angle": _selected_angle_payload(),
                        "score": 82.0,
                        "rank": 1,
                    }
                ]
            }
        },
    )
    db_session.add(step_artifact)
    db_session.commit()
    db_session.refresh(step_artifact)

    research = ResearchArtifact(
        org_id=org_uuid,
        workflow_run_id=workflow_run.id,
        step_key="v2-06",
        title="Angle synthesis",
        doc_id=str(step_artifact.id),
        doc_url=f"artifact://{step_artifact.id}",
        prompt_sha256=None,
        summary="Angles ready",
    )
    db_session.add(research)
    db_session.commit()

    response = api_client.get(f"/workflows/{workflow_run.id}")
    assert response.status_code == 200
    payload = response.json()
    state = payload["strategy_v2_state"]
    assert state["current_stage"] == "v2-07"
    assert state["required_signal_type"] == "strategy_v2_select_angle"
    assert state["pending_signal_type"] == "strategy_v2_select_angle"
    assert state["scored_candidate_summaries"]["angles"]
    pending_payload = state["pending_decision_payload"]
    assert isinstance(pending_payload, dict)
    assert isinstance(pending_payload.get("candidates"), list)
    assert pending_payload["candidates"][0]["angle_id"] == "A01"
    assert pending_payload["candidates"][0]["angle_name"] == "Mechanism-first relief"
    assert "score" not in pending_payload["candidates"][0]
    assert "pending_activity_progress" in payload
    assert isinstance(payload["pending_activity_progress"], list)


@pytest.mark.parametrize(
    ("step_key", "expected_stage", "expected_signal"),
    [
        ("v2-02b", "v2-02", None),
        ("v2-02", "v2-03", None),
        ("v2-03", "v2-03b", None),
        ("v2-03b", "v2-03c", None),
        ("v2-03c", "v2-04", None),
        ("v2-04", "v2-05a", None),
        ("v2-05a", "v2-05", None),
        ("v2-05", "v2-06", None),
    ],
)
def test_strategy_v2_state_from_research_artifacts_uses_explicit_stage2b_checkpoints(
    api_client,
    db_session,
    auth_context,
    step_key,
    expected_stage,
    expected_signal,
):
    client_id, product_id = _create_client_and_product(
        api_client=api_client,
        suffix=f"Stage2B{step_key}",
        strategy_v2_enabled=True,
    )
    org_uuid = UUID(auth_context.org_id)
    client_uuid = UUID(client_id)
    product_uuid = UUID(product_id)

    workflow_run = WorkflowRun(
        org_id=org_uuid,
        client_id=client_uuid,
        product_id=product_uuid,
        campaign_id=None,
        temporal_workflow_id=f"strategy-v2-{step_key}-workflow",
        temporal_run_id=f"strategy-v2-{step_key}-run",
        kind=WorkflowKindEnum.strategy_v2,
    )
    db_session.add(workflow_run)
    db_session.commit()
    db_session.refresh(workflow_run)

    step_artifact = Artifact(
        org_id=org_uuid,
        client_id=client_uuid,
        product_id=product_uuid,
        campaign_id=None,
        type=ArtifactTypeEnum.strategy_v2_step_payload,
        data={"payload": {"checkpoint": step_key}},
    )
    db_session.add(step_artifact)
    db_session.commit()
    db_session.refresh(step_artifact)

    research = ResearchArtifact(
        org_id=org_uuid,
        workflow_run_id=workflow_run.id,
        step_key=step_key,
        title=f"{step_key} payload",
        doc_id=str(step_artifact.id),
        doc_url=f"artifact://{step_artifact.id}",
        prompt_sha256=None,
        summary=f"{step_key} complete",
    )
    db_session.add(research)
    db_session.commit()

    response = api_client.get(f"/workflows/{workflow_run.id}")
    assert response.status_code == 200
    state = response.json()["strategy_v2_state"]
    assert state["current_stage"] == expected_stage
    assert state["required_signal_type"] == expected_signal
    assert state["pending_signal_type"] == expected_signal


def _stage2b_shared_context_stub() -> dict[str, Any]:
    return {
        "stage0": {"product_name": "Product"},
        "stage1": SimpleNamespace(
            category_niche="Sleep Support",
            competitor_urls=["https://competitor-a.example"],
        ),
        "stage1_data": {
            "category_niche": "Sleep Support",
            "competitor_urls": ["https://competitor-a.example"],
        },
        "precanon_research": {},
        "foundational_step_contents": {
            "01": "step01",
            "02": "{\"asset_observation_sheets\": [], \"compliance_landscape\": {\"red_pct\": 0, \"yellow_pct\": 0}}",
            "03": "step03",
            "04": "SOURCE: forum.example\n\"Quote\"",
            "06": "Avatar summary",
        },
        "foundational_step_summaries": {"06": "Avatar summary"},
        "confirmed_competitor_assets": [
            "https://competitor-a.example/asset-1",
            "https://competitor-b.example/asset-2",
            "https://competitor-c.example/asset-3",
        ],
        "competitor_analysis": {"asset_observation_sheets": [], "compliance_landscape": {"red_pct": 0.0, "yellow_pct": 0.0}},
        "avatar_brief_payload": {"summary": "avatar"},
    }


def _stage2b_foundational_artifact_ids() -> dict[str, str]:
    return {
        "v2-02.foundation.01": "artifact-01",
        "v2-02.foundation.02": "artifact-02",
        "v2-02.foundation.03": "artifact-03",
        "v2-02.foundation.04": "artifact-04",
        "v2-02.foundation.06": "artifact-06",
    }


def _agent1_scraped_manifest_stub(*, run_count: int = 1, item_count: int = 1) -> dict[str, Any]:
    runs = [
        {
            "actor_id": "practicaltools/apify-reddit-api",
            "run_id": f"run-{idx + 1}",
            "dataset_id": f"dataset-{idx + 1}",
            "config_id": f"cfg-{idx + 1}",
            "strategy_target_id": "HT-008",
            "status": "SUCCEEDED",
            "item_count": item_count,
            "requested_refs": ["https://www.reddit.com/r/herbalism/"],
            "virtual_path": f"/apify_output/raw_scraped_data/text_habitats/run-{idx + 1}.json",
        }
        for idx in range(run_count)
    ]
    raw_files = [
        {
            "file_name": f"run-{idx + 1}.json",
            "virtual_path": f"/apify_output/raw_scraped_data/text_habitats/run-{idx + 1}.json",
            "actor_id": "practicaltools/apify-reddit-api",
            "run_id": f"run-{idx + 1}",
            "dataset_id": f"dataset-{idx + 1}",
            "config_id": f"cfg-{idx + 1}",
            "strategy_target_id": "HT-008",
            "item_count": item_count,
            "requested_refs": ["https://www.reddit.com/r/herbalism/"],
            "items": [{"title": "sample", "source_url": "https://www.reddit.com/r/herbalism/"}],
        }
        for idx in range(run_count)
    ]
    return {
        "scraped_data_root": "/apify_output/",
        "raw_scraped_data_files": raw_files,
        "run_count": run_count,
        "total_run_count": run_count,
        "runs": runs,
        "candidate_asset_count": run_count,
        "social_video_observation_count": 0,
        "external_voc_row_count": 0,
        "competitor_asset_sheet_count": 0,
        "platform_breakdown": {"REDDIT": run_count},
    }


def _postprocess_manifest_stub() -> dict[str, Any]:
    return {
        "run_count": 1,
        "total_run_count": 1,
        "runs": [
            {
                "actor_id": "practicaltools/apify-reddit-api",
                "run_id": "run-1",
                "dataset_id": "dataset-1",
                "config_id": "cfg-1",
                "item_count": 1,
                "strategy_target_id": "HT-008",
            }
        ],
        "raw_scraped_data_files": [
            {
                "actor_id": "practicaltools/apify-reddit-api",
                "run_id": "run-1",
                "dataset_id": "dataset-1",
                "config_id": "cfg-1",
                "item_count": 1,
                "strategy_target_id": "HT-008",
            }
        ],
    }


def test_strategy_v2_apify_postprocess_uses_existing_collection_artifact_without_recollection(monkeypatch):
    monkeypatch.setattr(strategy_v2_activities, "_require_stage2b_shared_context", lambda **_kwargs: _stage2b_shared_context_stub())
    monkeypatch.setattr(
        strategy_v2_activities,
        "_ensure_foundational_step_payload_artifact_ids",
        lambda **kwargs: kwargs["existing_step_payload_artifact_ids"],
    )
    monkeypatch.setattr(strategy_v2_activities, "_require_step_payload_artifact_prerequisites", lambda **_kwargs: None)
    monkeypatch.setattr(strategy_v2_activities, "_require_agent00_executable_configs", lambda _payload: None)
    monkeypatch.setattr(strategy_v2_activities, "_require_agent00b_executable_configs", lambda _payload: None)
    monkeypatch.setattr(
        strategy_v2_activities,
        "_extract_apify_configs_from_agent_strategies",
        lambda **_kwargs: [{"config_id": "cfg-1"}],
    )
    monkeypatch.setattr(
        strategy_v2_activities,
        "_load_apify_collection_payload_for_postprocess",
        lambda **_kwargs: {
            "strategy_apify_configs": [{"config_id": "cfg-1"}],
            "apify_context": {
                "raw_runs": [
                    {
                        "actor_id": "practicaltools/apify-reddit-api",
                        "run_id": "run-1",
                        "dataset_id": "dataset-1",
                        "config_id": "cfg-1",
                        "status": "SUCCEEDED",
                        "items": [{"title": "sample"}],
                    }
                ],
                "social_video_observations": [],
                "external_voc_corpus": [],
                "proof_asset_candidates": [],
            },
            "strategy_config_run_count": 1,
            "planned_actor_run_count": 1,
            "executed_actor_run_count": 1,
            "failed_actor_run_count": 0,
        },
    )
    monkeypatch.setattr(
        strategy_v2_activities,
        "_ingest_strategy_v2_asset_data",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not recollect apify runs during postprocess")),
    )
    monkeypatch.setattr(strategy_v2_activities, "_validate_reddit_target_alignment", lambda **_kwargs: None)
    monkeypatch.setattr(strategy_v2_activities, "_extract_step4_entries", lambda _content: [])
    monkeypatch.setattr(strategy_v2_activities, "_extract_video_observations", lambda _analysis: [])
    monkeypatch.setattr(strategy_v2_activities, "_extract_video_source_allowlist", lambda _agent00b: [])
    monkeypatch.setattr(strategy_v2_activities, "_build_video_topic_keywords", lambda **_kwargs: [])
    monkeypatch.setattr(strategy_v2_activities, "_filter_metric_video_rows_for_scoring", lambda **_kwargs: ([], {}))
    monkeypatch.setattr(strategy_v2_activities, "_normalize_video_scored_rows", lambda rows: rows)
    monkeypatch.setattr(strategy_v2_activities, "transform_step4_entries_to_agent2_corpus", lambda _entries: [])
    monkeypatch.setattr(
        strategy_v2_activities,
        "_merge_voc_corpus_for_agent2",
        lambda **_kwargs: {"prompt_rows": [], "artifact_rows": [], "summary": {}},
    )
    monkeypatch.setattr(strategy_v2_activities, "_build_proof_candidates_from_voc", lambda **_kwargs: [])
    monkeypatch.setattr(strategy_v2_activities, "_build_scraped_data_manifest", lambda **_kwargs: _postprocess_manifest_stub())
    monkeypatch.setattr(strategy_v2_activities, "_record_agent_run", lambda **_kwargs: "agent-run-1")
    monkeypatch.setattr(strategy_v2_activities, "_persist_step_payload", lambda **_kwargs: "artifact-v2-03c")

    @contextmanager
    def _fake_session_scope():
        yield object()

    monkeypatch.setattr(strategy_v2_activities, "session_scope", _fake_session_scope)

    result = strategy_v2_activities.run_strategy_v2_voc_agent0b_apify_ingestion_activity(
        {
            "org_id": "org-1",
            "client_id": "client-1",
            "product_id": "product-1",
            "campaign_id": None,
            "workflow_run_id": "workflow-run-1",
            "operator_user_id": "operator-1",
            "stage0": {"product_name": "Product"},
            "stage1": {"category_niche": "Sleep Support"},
            "precanon_research": {"step_contents": {}, "step_summaries": {}},
            "stage1_artifact_id": "stage1-artifact-id",
            "confirmed_competitor_assets": [
                "https://competitor-a.example/asset-1",
                "https://competitor-b.example/asset-2",
                "https://competitor-c.example/asset-3",
            ],
            "existing_step_payload_artifact_ids": {
                **_stage2b_foundational_artifact_ids(),
                "v2-02": "artifact-v2-02",
                "v2-03": "artifact-v2-03",
                "v2-03b": "artifact-v2-03b",
            },
            "agent00_output": {"ok": True},
            "agent00b_output": {"ok": True},
            "competitor_analysis": {"asset_observation_sheets": [], "compliance_landscape": {"red_pct": 0.0, "yellow_pct": 0.0}},
            "apify_collection_artifact_id": "artifact-v2-03b",
        }
    )
    assert result["step_payload_artifact_id"] == "artifact-v2-03c"
    assert result["planned_actor_run_count"] == 1
    assert result["executed_actor_run_count"] == 1
    assert result["failed_actor_run_count"] == 0
    assert result["handoff_audit"]["manifest_total_run_count"] == 1


def test_strategy_v2_apify_postprocess_fails_when_collection_strategy_count_mismatches(monkeypatch):
    monkeypatch.setattr(strategy_v2_activities, "_require_stage2b_shared_context", lambda **_kwargs: _stage2b_shared_context_stub())
    monkeypatch.setattr(
        strategy_v2_activities,
        "_ensure_foundational_step_payload_artifact_ids",
        lambda **kwargs: kwargs["existing_step_payload_artifact_ids"],
    )
    monkeypatch.setattr(strategy_v2_activities, "_require_step_payload_artifact_prerequisites", lambda **_kwargs: None)
    monkeypatch.setattr(strategy_v2_activities, "_extract_step4_entries", lambda _content: [])
    monkeypatch.setattr(strategy_v2_activities, "_require_agent00_executable_configs", lambda _payload: None)
    monkeypatch.setattr(strategy_v2_activities, "_require_agent00b_executable_configs", lambda _payload: None)
    monkeypatch.setattr(
        strategy_v2_activities,
        "_extract_apify_configs_from_agent_strategies",
        lambda **_kwargs: [{"config_id": "cfg-1"}, {"config_id": "cfg-2"}],
    )
    monkeypatch.setattr(
        strategy_v2_activities,
        "_load_apify_collection_payload_for_postprocess",
        lambda **_kwargs: {
            "strategy_apify_configs": [{"config_id": "cfg-1"}],
            "apify_context": {
                "raw_runs": [
                    {
                        "actor_id": "practicaltools/apify-reddit-api",
                        "run_id": "run-1",
                        "dataset_id": "dataset-1",
                        "config_id": "cfg-1",
                        "status": "SUCCEEDED",
                        "items": [{"title": "sample"}],
                    }
                ],
            },
            "strategy_config_run_count": 1,
            "planned_actor_run_count": 1,
            "executed_actor_run_count": 1,
            "failed_actor_run_count": 0,
        },
    )

    with pytest.raises(StrategyV2SchemaValidationError, match="strategy_config_run_count does not match current strategy config count"):
        strategy_v2_activities.run_strategy_v2_voc_agent0b_apify_ingestion_activity(
            {
                "org_id": "org-1",
                "client_id": "client-1",
                "product_id": "product-1",
                "campaign_id": None,
                "workflow_run_id": "workflow-run-1",
                "operator_user_id": "operator-1",
                "stage0": {"product_name": "Product"},
                "stage1": {"category_niche": "Sleep Support"},
                "precanon_research": {"step_contents": {}, "step_summaries": {}},
                "stage1_artifact_id": "stage1-artifact-id",
                "confirmed_competitor_assets": [
                    "https://competitor-a.example/asset-1",
                    "https://competitor-b.example/asset-2",
                    "https://competitor-c.example/asset-3",
                ],
                "existing_step_payload_artifact_ids": {
                    **_stage2b_foundational_artifact_ids(),
                    "v2-02": "artifact-v2-02",
                    "v2-03": "artifact-v2-03",
                    "v2-03b": "artifact-v2-03b",
                },
                "agent00_output": {"ok": True},
                "agent00b_output": {"ok": True},
                "competitor_analysis": {"asset_observation_sheets": [], "compliance_landscape": {"red_pct": 0.0, "yellow_pct": 0.0}},
                "apify_collection_artifact_id": "artifact-v2-03b",
            }
        )


def test_strategy_v2_manifest_selection_prefers_platform_diversity(monkeypatch):
    def _run(actor_id: str, run_id: str, source_url: str) -> dict[str, Any]:
        return {
            "actor_id": actor_id,
            "run_id": run_id,
            "dataset_id": f"dataset-{run_id}",
            "status": "SUCCEEDED",
            "input_payload": {"startUrls": [{"url": source_url}]},
            "items": [{"title": f"title-{run_id}", "source_url": source_url}],
        }

    manifest = strategy_v2_activities._build_scraped_data_manifest(
        apify_context={
            "raw_runs": [
                _run("practicaltools/apify-reddit-api", "r1", "https://www.reddit.com/r/herbalism/"),
                _run("practicaltools/apify-reddit-api", "r2", "https://www.reddit.com/r/Perimenopause/"),
                _run("clockworks/tiktok-scraper", "t1", "https://www.tiktok.com/@herbalacademy/video/1"),
                _run("apify/instagram-scraper", "i1", "https://www.instagram.com/explore/tags/herbalism/"),
                _run("streamers/youtube-scraper", "y1", "https://www.youtube.com/watch?v=abc123"),
                _run("apify/web-scraper", "w1", "https://example.com/article"),
            ],
            "candidate_assets": [],
            "social_video_observations": [],
            "external_voc_corpus": [],
        },
        competitor_analysis={"asset_observation_sheets": []},
    )

    actors = [
        row.get("actor_id")
        for row in manifest.get("runs", [])
        if isinstance(row, dict) and isinstance(row.get("actor_id"), str)
    ]
    assert manifest["run_count"] == 6
    assert manifest["total_run_count"] == 6
    assert "practicaltools/apify-reddit-api" in actors
    assert "clockworks/tiktok-scraper" in actors
    assert "apify/instagram-scraper" in actors
    assert "streamers/youtube-scraper" in actors
    assert "apify/web-scraper" in actors


def test_strategy_v2_checkpoint_c1_fails_when_agent0_configs_missing(monkeypatch):
    monkeypatch.setattr(strategy_v2_activities, "_require_stage2b_shared_context", lambda **_kwargs: _stage2b_shared_context_stub())
    monkeypatch.setattr(strategy_v2_activities, "_validate_step_payload_lineage_prerequisites", lambda **_kwargs: None)
    monkeypatch.setattr(strategy_v2_activities, "_extract_step4_entries", lambda _content: [{"source": "forum.example"}])
    monkeypatch.setattr(
        strategy_v2_activities,
        "_run_prompt_json_object",
        lambda **_kwargs: (
            {"category_classification": {"primary": "sleep-support"}},
            "raw-output",
            {"prompt": "stub"},
        ),
    )

    with pytest.raises(StrategyV2SchemaValidationError, match="apify_configs"):
        strategy_v2_activities.run_strategy_v2_voc_agent0_habitat_strategy_activity(
            {
                "org_id": "org-1",
                "client_id": "client-1",
                "product_id": "product-1",
                "campaign_id": None,
                "workflow_run_id": "workflow-run-1",
                "operator_user_id": "operator-1",
                "stage0": {"product_name": "Product"},
                "stage1": {"category_niche": "Sleep Support"},
                "precanon_research": {"step_contents": {}, "step_summaries": {}},
                "stage1_artifact_id": "stage1-artifact-id",
                "confirmed_competitor_assets": [
                    "https://competitor-a.example/asset-1",
                    "https://competitor-b.example/asset-2",
                    "https://competitor-c.example/asset-3",
                ],
                "existing_step_payload_artifact_ids": _stage2b_foundational_artifact_ids(),
            }
        )


def test_strategy_v2_checkpoint_c3_requires_scraped_manifest(monkeypatch):
    monkeypatch.setattr(strategy_v2_activities, "_require_stage2b_shared_context", lambda **_kwargs: _stage2b_shared_context_stub())
    monkeypatch.setattr(strategy_v2_activities, "_validate_step_payload_lineage_prerequisites", lambda **_kwargs: None)

    with pytest.raises(StrategyV2MissingContextError, match="raw_scraped_data_files"):
        strategy_v2_activities.run_strategy_v2_voc_agent1_habitat_qualifier_activity(
            {
                "org_id": "org-1",
                "client_id": "client-1",
                "product_id": "product-1",
                "campaign_id": None,
                "workflow_run_id": "workflow-run-1",
                "operator_user_id": "operator-1",
                "stage0": {"product_name": "Product"},
                "stage1": {"category_niche": "Sleep Support"},
                "precanon_research": {"step_contents": {}, "step_summaries": {}},
                "stage1_artifact_id": "stage1-artifact-id",
                "confirmed_competitor_assets": [
                    "https://competitor-a.example/asset-1",
                    "https://competitor-b.example/asset-2",
                    "https://competitor-c.example/asset-3",
                ],
                "existing_step_payload_artifact_ids": {
                    **_stage2b_foundational_artifact_ids(),
                    "v2-02": "artifact-v2-02",
                    "v2-03": "artifact-v2-03",
                    "v2-03b": "artifact-v2-03b",
                    "v2-03c": "artifact-v2-03c",
                },
                "agent00_output": {"apify_configs_tier1": [{}], "apify_configs_tier2": [{}]},
                "agent00b_output": {"configurations": [{}]},
                "scraped_data_manifest": {},
                "video_scored": [],
                "competitor_analysis": {"asset_observation_sheets": [], "compliance_landscape": {"red_pct": 0.0, "yellow_pct": 0.0}},
            }
        )


def test_strategy_v2_checkpoint_c3_rejects_manifest_count_mismatch(monkeypatch):
    monkeypatch.setattr(strategy_v2_activities, "_require_stage2b_shared_context", lambda **_kwargs: _stage2b_shared_context_stub())
    monkeypatch.setattr(strategy_v2_activities, "_validate_step_payload_lineage_prerequisites", lambda **_kwargs: None)

    with pytest.raises(StrategyV2SchemaValidationError, match="total_run_count mismatch for Agent 1 handoff"):
        strategy_v2_activities.run_strategy_v2_voc_agent1_habitat_qualifier_activity(
            {
                "org_id": "org-1",
                "client_id": "client-1",
                "product_id": "product-1",
                "campaign_id": None,
                "workflow_run_id": "workflow-run-1",
                "operator_user_id": "operator-1",
                "stage0": {"product_name": "Product"},
                "stage1": {"category_niche": "Sleep Support"},
                "precanon_research": {"step_contents": {}, "step_summaries": {}},
                "stage1_artifact_id": "stage1-artifact-id",
                "confirmed_competitor_assets": [
                    "https://competitor-a.example/asset-1",
                    "https://competitor-b.example/asset-2",
                    "https://competitor-c.example/asset-3",
                ],
                "existing_step_payload_artifact_ids": {
                    **_stage2b_foundational_artifact_ids(),
                    "v2-02": "artifact-v2-02",
                    "v2-03": "artifact-v2-03",
                    "v2-03b": "artifact-v2-03b",
                    "v2-03c": "artifact-v2-03c",
                },
                "agent00_output": {"apify_configs_tier1": [{}], "apify_configs_tier2": [{}]},
                "agent00b_output": {"configurations": [{}]},
                "scraped_data_manifest": _agent1_scraped_manifest_stub(run_count=1, item_count=1),
                "video_scored": [],
                "strategy_config_run_count": 0,
                "planned_actor_run_count": 101,
                "executed_actor_run_count": 101,
                "failed_actor_run_count": 0,
                "competitor_analysis": {"asset_observation_sheets": [], "compliance_landscape": {"red_pct": 0.0, "yellow_pct": 0.0}},
            }
        )


def test_strategy_v2_checkpoint_c3_payload_upload_path_reaches_prompt_call(monkeypatch):
    monkeypatch.setattr(strategy_v2_activities, "_require_stage2b_shared_context", lambda **_kwargs: _stage2b_shared_context_stub())
    monkeypatch.setattr(strategy_v2_activities, "_validate_step_payload_lineage_prerequisites", lambda **_kwargs: None)
    monkeypatch.setattr(strategy_v2_activities, "_AGENT1_HABITAT_STRATEGY_MAX_CHARS", 32)
    monkeypatch.setattr(
        strategy_v2_activities,
        "_run_prompt_json_object",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("_run_prompt_json_object reached")),
    )

    with pytest.raises(AssertionError, match="_run_prompt_json_object reached"):
        strategy_v2_activities.run_strategy_v2_voc_agent1_habitat_qualifier_activity(
            {
                "org_id": "org-1",
                "client_id": "client-1",
                "product_id": "product-1",
                "campaign_id": None,
                "workflow_run_id": "workflow-run-1",
                "operator_user_id": "operator-1",
                "stage0": {"product_name": "Product"},
                "stage1": {"category_niche": "Sleep Support"},
                "precanon_research": {"step_contents": {}, "step_summaries": {}},
                "stage1_artifact_id": "stage1-artifact-id",
                "confirmed_competitor_assets": [
                    "https://competitor-a.example/asset-1",
                    "https://competitor-b.example/asset-2",
                    "https://competitor-c.example/asset-3",
                ],
                "existing_step_payload_artifact_ids": {
                    **_stage2b_foundational_artifact_ids(),
                    "v2-02": "artifact-v2-02",
                    "v2-03": "artifact-v2-03",
                    "v2-03b": "artifact-v2-03b",
                    "v2-03c": "artifact-v2-03c",
                },
                "agent00_output": {"large": "x" * 256},
                "agent00b_output": {"configurations": [{}]},
                "scraped_data_manifest": _agent1_scraped_manifest_stub(run_count=1, item_count=1),
                "video_scored": [],
                "strategy_config_run_count": 0,
                "planned_actor_run_count": 1,
                "executed_actor_run_count": 1,
                "failed_actor_run_count": 0,
                "competitor_analysis": {"asset_observation_sheets": [], "compliance_landscape": {"red_pct": 0.0, "yellow_pct": 0.0}},
            }
        )


def test_strategy_v2_checkpoint_c4_requires_agent1_handoff(monkeypatch):
    monkeypatch.setattr(strategy_v2_activities, "_require_stage2b_shared_context", lambda **_kwargs: _stage2b_shared_context_stub())
    monkeypatch.setattr(strategy_v2_activities, "_validate_step_payload_lineage_prerequisites", lambda **_kwargs: None)

    with pytest.raises(StrategyV2SchemaValidationError, match="agent01_output"):
        strategy_v2_activities.run_strategy_v2_voc_agent2_extraction_activity(
            {
                "org_id": "org-1",
                "client_id": "client-1",
                "product_id": "product-1",
                "campaign_id": None,
                "workflow_run_id": "workflow-run-1",
                "operator_user_id": "operator-1",
                "stage0": {"product_name": "Product"},
                "stage1": {"category_niche": "Sleep Support"},
                "precanon_research": {"step_contents": {}, "step_summaries": {}},
                "stage1_artifact_id": "stage1-artifact-id",
                "confirmed_competitor_assets": [
                    "https://competitor-a.example/asset-1",
                    "https://competitor-b.example/asset-2",
                    "https://competitor-c.example/asset-3",
                ],
                "existing_step_payload_artifact_ids": {
                    **_stage2b_foundational_artifact_ids(),
                    "v2-03": "artifact-v2-03",
                    "v2-03b": "artifact-v2-03b",
                    "v2-03c": "artifact-v2-03c",
                    "v2-04": "artifact-v2-04",
                },
                "agent01_output": None,
                "habitat_scored": {},
                "existing_corpus": [{"voc_id": "v1", "quote": "Quote", "source_url": "https://source.example"}],
                "merged_voc_artifact_rows": [],
                "corpus_selection_summary": {},
                "external_corpus_count": 0,
                "proof_asset_candidates": [],
                "competitor_analysis": {"asset_observation_sheets": [], "compliance_landscape": {"red_pct": 0.0, "yellow_pct": 0.0}},
            }
        )


def test_strategy_v2_checkpoint_c5_scores_voc_observations_when_voc_scored_missing(monkeypatch):
    monkeypatch.setattr(strategy_v2_activities, "_require_stage2b_shared_context", lambda **_kwargs: _stage2b_shared_context_stub())
    monkeypatch.setattr(strategy_v2_activities, "_validate_step_payload_lineage_prerequisites", lambda **_kwargs: None)
    monkeypatch.setattr(strategy_v2_activities, "_normalize_voc_observations", lambda rows: rows)
    monkeypatch.setattr(
        strategy_v2_activities,
        "score_voc_items",
        lambda rows: {
            "items": [{"adjusted_score": 1.0, "zero_evidence_gate": False} for _ in rows] or [{"adjusted_score": 1.0, "zero_evidence_gate": False}],
            "summary": {"count": len(rows)},
        },
    )
    monkeypatch.setattr(
        strategy_v2_activities,
        "_run_prompt_json_object",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("_run_prompt_json_object reached")),
    )

    with pytest.raises(AssertionError, match="_run_prompt_json_object reached"):
        strategy_v2_activities.run_strategy_v2_voc_agent3_synthesis_activity(
            {
                "org_id": "org-1",
                "client_id": "client-1",
                "product_id": "product-1",
                "campaign_id": None,
                "workflow_run_id": "workflow-run-1",
                "operator_user_id": "operator-1",
                "stage0": {"product_name": "Product"},
                "stage1": {"category_niche": "Sleep Support"},
                "precanon_research": {"step_contents": {}, "step_summaries": {}},
                "stage1_artifact_id": "stage1-artifact-id",
                "confirmed_competitor_assets": [
                    "https://competitor-a.example/asset-1",
                    "https://competitor-b.example/asset-2",
                    "https://competitor-c.example/asset-3",
                ],
                "existing_step_payload_artifact_ids": {
                    **_stage2b_foundational_artifact_ids(),
                    "v2-04": "artifact-v2-04",
                },
                "competitor_analysis": {"asset_observation_sheets": [], "compliance_landscape": {"red_pct": 0.0, "yellow_pct": 0.0}},
                "voc_observations": [
                    {
                        "voc_id": "V001",
                        "evidence_id": "E1111111111111111",
                        "quote": "Quote",
                        "source_url": "https://source.example",
                    }
                ],
                "voc_scored": None,
            }
        )


def test_normalize_strategy_v2_artifact_refs_promotes_nested_step_payload_ids():
    normalized = _normalize_strategy_v2_artifact_refs(
        {
            "step_payload_artifact_ids": {
                "v2-02i": "artifact-id-02i",
                "v2-06": "artifact-id-06",
            },
            "step_payload_v2_02i_artifact_id": "artifact-id-02i",
        }
    )
    assert normalized["v2-02i"] == "artifact-id-02i"
    assert normalized["v2-06"] == "artifact-id-06"
    assert normalized["step_payload_v2_06_artifact_id"] == "artifact-id-06"


def test_strategy_v2_state_includes_h2_candidates_from_ingestion_artifact(api_client, db_session, auth_context):
    client_id, product_id = _create_client_and_product(
        api_client=api_client,
        suffix="StateH2Candidates",
        strategy_v2_enabled=True,
    )
    org_uuid = UUID(auth_context.org_id)
    client_uuid = UUID(client_id)
    product_uuid = UUID(product_id)

    workflow_run = WorkflowRun(
        org_id=org_uuid,
        client_id=client_uuid,
        product_id=product_uuid,
        campaign_id=None,
        temporal_workflow_id="strategy-v2-state-h2-workflow",
        temporal_run_id="strategy-v2-state-h2-run",
        kind=WorkflowKindEnum.strategy_v2,
    )
    db_session.add(workflow_run)
    db_session.commit()
    db_session.refresh(workflow_run)

    stage1_artifact = Artifact(
        org_id=org_uuid,
        client_id=client_uuid,
        product_id=product_uuid,
        campaign_id=None,
        type=ArtifactTypeEnum.strategy_v2_stage1,
        data={
            "schema_version": "2.0.0",
            "stage": 1,
            "product_name": "Product",
            "description": "Desc",
            "price": "$49",
            "competitor_urls": ["https://competitor-a.example", "https://competitor-b.example", "https://competitor-c.example"],
            "product_customizable": True,
            "category_niche": "Health & Wellness",
            "market_maturity_stage": "Growth",
            "primary_segment": {
                "name": "Caregivers",
                "size_estimate": "Large",
                "key_differentiator": "Safety-first",
            },
            "bottleneck": "Trust",
            "positioning_gaps": [],
            "competitor_count_validated": 3,
            "primary_icps": ["Caregivers", "Parents", "Budget-conscious buyers"],
        },
    )
    db_session.add(stage1_artifact)

    proceed_artifact = Artifact(
        org_id=org_uuid,
        client_id=client_uuid,
        product_id=product_uuid,
        campaign_id=None,
        type=ArtifactTypeEnum.strategy_v2_step_payload,
        data={"payload": {"decision": {"proceed": True}}},
    )
    db_session.add(proceed_artifact)

    ingest_artifact = Artifact(
        org_id=org_uuid,
        client_id=client_uuid,
        product_id=product_uuid,
        campaign_id=None,
        type=ArtifactTypeEnum.strategy_v2_step_payload,
        data={
            "payload": {
                "selected_candidates": [
                    {
                        "candidate_id": "https://competitor-a.example/asset-1",
                        "source_ref": "https://competitor-a.example/asset-1",
                        "competitor_name": "Competitor A",
                        "platform": "WEB",
                        "candidate_asset_score": 90.0,
                        "eligible": True,
                    }
                ],
                "candidate_summary": {
                    "selected_candidate_count": 1,
                    "selection_limits": {
                        "max_candidates": strategy_v2_activities._H2_MAX_CANDIDATE_ASSETS
                    },
                },
            }
        },
    )
    db_session.add(ingest_artifact)
    db_session.commit()
    db_session.refresh(proceed_artifact)
    db_session.refresh(ingest_artifact)

    db_session.add_all(
        [
            ResearchArtifact(
                org_id=org_uuid,
                workflow_run_id=workflow_run.id,
                step_key="v2-02a",
                title="Research proceed",
                doc_id=str(proceed_artifact.id),
                doc_url=f"artifact://{proceed_artifact.id}",
                prompt_sha256=None,
                summary="Proceed",
            ),
            ResearchArtifact(
                org_id=org_uuid,
                workflow_run_id=workflow_run.id,
                step_key="v2-02i",
                title="Asset ingestion",
                doc_id=str(ingest_artifact.id),
                doc_url=f"artifact://{ingest_artifact.id}",
                prompt_sha256=None,
                summary="Candidates",
            ),
        ]
    )
    db_session.commit()

    response = api_client.get(f"/workflows/{workflow_run.id}")
    assert response.status_code == 200
    state = response.json()["strategy_v2_state"]
    assert state["pending_signal_type"] == "strategy_v2_confirm_competitor_assets"
    pending = state["pending_decision_payload"]
    assert isinstance(pending, dict)
    assert isinstance(pending.get("candidates"), list)
    assert pending["candidates"][0]["candidate_id"] == "https://competitor-a.example/asset-1"
    assert isinstance(pending.get("candidate_summary"), dict)


def test_strategy_v2_state_includes_proof_candidates_for_ump_ums_selection(
    api_client,
    db_session,
    auth_context,
):
    client_id, product_id = _create_client_and_product(
        api_client=api_client,
        suffix="StateProofCandidates",
        strategy_v2_enabled=True,
    )
    org_uuid = UUID(auth_context.org_id)
    client_uuid = UUID(client_id)
    product_uuid = UUID(product_id)

    workflow_run = WorkflowRun(
        org_id=org_uuid,
        client_id=client_uuid,
        product_id=product_uuid,
        campaign_id=None,
        temporal_workflow_id="strategy-v2-state-proof-workflow",
        temporal_run_id="strategy-v2-state-proof-run",
        kind=WorkflowKindEnum.strategy_v2,
    )
    db_session.add(workflow_run)
    db_session.commit()
    db_session.refresh(workflow_run)

    v2_08_artifact = Artifact(
        org_id=org_uuid,
        client_id=client_uuid,
        product_id=product_uuid,
        campaign_id=None,
        type=ArtifactTypeEnum.strategy_v2_step_payload,
        data={
            "payload": {
                "pair_scoring": {
                    "ranked_pairs": [
                        {
                            "pair_id": "pair-a",
                            "ump_text": "UMP A",
                            "ums_text": "UMS A",
                            "score": 8.6,
                        }
                    ]
                },
                "proof_asset_candidates": [
                    {
                        "proof_id": "proof_001",
                        "proof_note": "Timing sequence reduced wake-ups after two weeks.",
                        "source_refs": [
                            "https://forum.example.com/thread-1",
                            "https://competitor.example/asset-a",
                        ],
                        "evidence_count": 2,
                        "compliance_flag": "YELLOW",
                    }
                ],
            }
        },
    )
    db_session.add(v2_08_artifact)
    db_session.commit()
    db_session.refresh(v2_08_artifact)

    db_session.add(
        ResearchArtifact(
            org_id=org_uuid,
            workflow_run_id=workflow_run.id,
            step_key="v2-08",
            title="Offer pipeline output",
            doc_id=str(v2_08_artifact.id),
            doc_url=f"artifact://{v2_08_artifact.id}",
            prompt_sha256=None,
            summary="Ranked UMP/UMS pairs with proof suggestions",
        )
    )
    db_session.commit()

    response = api_client.get(f"/workflows/{workflow_run.id}")
    assert response.status_code == 200
    state = response.json()["strategy_v2_state"]
    assert state["pending_signal_type"] == "strategy_v2_select_ump_ums"
    pending = state["pending_decision_payload"]
    assert isinstance(pending, dict)
    assert isinstance(pending.get("candidates"), list)
    assert pending["candidates"][0]["pair_id"] == "pair-a"
    assert isinstance(pending.get("proof_asset_candidates"), list)
    assert pending["proof_asset_candidates"][0]["proof_id"] == "proof_001"


def test_finalize_copy_approval_rejects_system_operator_id(
    api_client,
    db_session,
    auth_context,
    monkeypatch,
):
    @contextmanager
    def _session_scope_override():
        yield db_session

    monkeypatch.setattr(strategy_v2_activities, "session_scope", _session_scope_override)
    client_id, product_id = _create_client_and_product(
        api_client=api_client,
        suffix="HumanGate",
        strategy_v2_enabled=True,
    )
    ensure_run = strategy_v2_activities.ensure_strategy_v2_workflow_run_activity(
        {
            "org_id": auth_context.org_id,
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": None,
            "temporal_workflow_id": "strategy-v2-human-gate-workflow",
            "temporal_run_id": "strategy-v2-human-gate-run",
        }
    )

    with pytest.raises(StrategyV2DecisionError):
        strategy_v2_activities.finalize_strategy_v2_copy_approval_activity(
            {
                "org_id": auth_context.org_id,
                "client_id": client_id,
                "product_id": product_id,
                "campaign_id": None,
                "workflow_run_id": ensure_run["workflow_run_id"],
                "final_approval_decision": {
                    "operator_user_id": "system-monitor",
                    "approved": True,
                    "reviewed_candidate_ids": ["copy-artifact-1"],
                    **_manual_hitl_fields(
                        operator_note="Reviewed evidence thoroughly and approve this copy package.",
                    ),
                },
                "copy_payload": {
                    "headline": "Approved headline",
                    "body_markdown": "Approved body",
                },
            }
        )


def test_campaign_planning_requires_strategy_v2_outputs_when_enabled(
    api_client,
    db_session,
    auth_context,
):
    client_id, product_id = _create_client_and_product(
        api_client=api_client,
        suffix="PlanningGate",
        strategy_v2_enabled=True,
    )
    org_uuid = UUID(auth_context.org_id)
    client_uuid = UUID(client_id)
    product_uuid = UUID(product_id)

    db_session.add(
        Artifact(
            org_id=org_uuid,
            client_id=client_uuid,
            product_id=product_uuid,
            campaign_id=None,
            type=ArtifactTypeEnum.client_canon,
            data={"brand": {"story": "Canon story"}},
        )
    )
    db_session.add(
        Artifact(
            org_id=org_uuid,
            client_id=client_uuid,
            product_id=product_uuid,
            campaign_id=None,
            type=ArtifactTypeEnum.metric_schema,
            data={"kpis": ["ctr"]},
        )
    )
    db_session.commit()

    campaign = Campaign(
        org_id=org_uuid,
        client_id=client_uuid,
        product_id=product_uuid,
        name="Planning Gate Campaign",
        channels=["meta"],
        asset_brief_types=["image"],
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)

    response = api_client.post(f"/campaigns/{campaign.id}/plan", json={})
    assert response.status_code == 409
    assert "Strategy V2 output missing" in response.json()["detail"]


def test_campaign_intent_allows_strategy_v2_enabled_client_without_canon_metric(
    api_client,
    db_session,
    auth_context,
    fake_temporal,
):
    client_id, product_id = _create_client_and_product(
        api_client=api_client,
        suffix="IntentV2Only",
        strategy_v2_enabled=True,
    )
    org_uuid = UUID(auth_context.org_id)
    client_uuid = UUID(client_id)
    product_uuid = UUID(product_id)

    db_session.add(
        Artifact(
            org_id=org_uuid,
            client_id=client_uuid,
            product_id=product_uuid,
            campaign_id=None,
            type=ArtifactTypeEnum.strategy_v2_stage3,
            data={
                "selected_angle": {"angle_id": "A01", "angle_name": "Mechanism-first relief", "evidence": {}},
                "ump": "UMP core",
                "ums": "UMS core",
                "core_promise": "Promise",
                "value_stack_summary": ["Stack item"],
                "variant_selected": "share_and_save",
            },
        )
    )
    db_session.add(
        Artifact(
            org_id=org_uuid,
            client_id=client_uuid,
            product_id=product_uuid,
            campaign_id=None,
            type=ArtifactTypeEnum.strategy_v2_offer,
            data={"selected_offer": {"variant_id": "share_and_save"}},
        )
    )
    db_session.add(
        Artifact(
            org_id=org_uuid,
            client_id=client_uuid,
            product_id=product_uuid,
            campaign_id=None,
            type=ArtifactTypeEnum.strategy_v2_copy,
            data={"approved_copy": {"headline": "Approved headline"}},
        )
    )
    db_session.add(
        Artifact(
            org_id=org_uuid,
            client_id=client_uuid,
            product_id=product_uuid,
            campaign_id=None,
            type=ArtifactTypeEnum.strategy_v2_copy_context,
            data={"audience_product_markdown": "Audience context", "brand_voice_markdown": "Voice context"},
        )
    )
    db_session.commit()

    response = api_client.post(
        f"/clients/{client_id}/intent",
        json={
            "campaignName": "V2 Intent",
            "productId": product_id,
            "channels": ["meta"],
            "assetBriefTypes": ["image"],
        },
    )
    assert response.status_code == 200
    assert response.json()["workflow_run_id"]
    assert fake_temporal.started


def test_strategy_v2_voc_pipeline_accepts_precanon_research_without_client_canon(
    api_client,
    db_session,
    auth_context,
    monkeypatch,
):
    @contextmanager
    def _session_scope_override():
        yield db_session

    monkeypatch.setattr(strategy_v2_activities, "session_scope", _session_scope_override)
    monkeypatch.setattr(
        strategy_v2_activities,
        "score_angles",
        lambda angle_observations, saturated_count: _mock_scored_angles(),
    )
    monkeypatch.setattr(strategy_v2_activities, "_require_agent00_executable_configs", lambda _payload: None)
    monkeypatch.setattr(strategy_v2_activities, "_require_agent00b_executable_configs", lambda _payload: None)
    monkeypatch.setattr(
        strategy_v2_activities,
        "_filter_metric_video_rows_for_scoring",
        lambda **kwargs: (
            [row for row in kwargs.get("video_rows", []) if isinstance(row, dict)],
            {
                "input_rows": len(kwargs.get("video_rows", [])),
                "missing_metrics": 0,
                "off_target_source": 0,
                "off_topic": 0,
                "kept_rows": len([row for row in kwargs.get("video_rows", []) if isinstance(row, dict)]),
            },
        ),
    )
    monkeypatch.setattr(strategy_v2_activities, "_AGENT1_COMPACTION_THRESHOLD", 200000)
    monkeypatch.setattr(
        strategy_v2_activities,
        "_run_agent2_extractor",
        lambda **_kwargs: {
            "mode": "DUAL",
            "voc_observations": [
                {
                    "voc_id": "V1",
                    "evidence_id": "E1111111111111111",
                    "source": "https://example.com",
                    "quote": "Sample VOC",
                }
            ],
            "rejected_items": [],
            "extraction_summary": {"input_count": 1, "output_count": 1, "rejected_count": 0},
            "prompt_provenance": {},
            "raw_outputs_preview": [],
        },
    )
    monkeypatch.setattr(strategy_v2_activities, "_normalize_voc_observations", lambda rows: rows)
    monkeypatch.setattr(
        strategy_v2_activities,
        "score_voc_items",
        lambda rows: {
            "items": [{"adjusted_score": 1.0, "zero_evidence_gate": False} for _ in rows] or [{"adjusted_score": 1.0, "zero_evidence_gate": False}],
            "summary": {"count": len(rows)},
        },
    )
    monkeypatch.setattr(strategy_v2_activities, "_require_voc_transition_quality", lambda **_kwargs: None)
    monkeypatch.setattr(strategy_v2_activities, "_validate_agent1_output_source_file_grounding", lambda **_kwargs: None)
    monkeypatch.setattr(
        strategy_v2_activities,
        "_ingest_strategy_v2_asset_data",
        _stub_ingest_strategy_v2_asset_data,
    )

    client_id, product_id = _create_client_and_product(
        api_client=api_client,
        suffix="PrecanonDirect",
        strategy_v2_enabled=True,
    )
    org_uuid = UUID(auth_context.org_id)
    client_uuid = UUID(client_id)
    product_uuid = UUID(product_id)

    onboarding_payload = OnboardingPayload(
        org_id=org_uuid,
        client_id=client_uuid,
        product_id=product_uuid,
        data={
            "product_name": "Product Prec",
            "product_description": "Detailed product description",
            "product_customizable": True,
            "competitor_urls": ["https://competitor-a.example"],
            "price": "$49",
        },
    )
    db_session.add(onboarding_payload)
    db_session.commit()
    db_session.refresh(onboarding_payload)

    ensure_run = strategy_v2_activities.ensure_strategy_v2_workflow_run_activity(
        {
            "org_id": auth_context.org_id,
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": None,
            "temporal_workflow_id": "strategy-v2-direct-precanon-workflow",
            "temporal_run_id": "strategy-v2-direct-precanon-run",
        }
    )
    workflow_run_id = ensure_run["workflow_run_id"]

    stage0_result = strategy_v2_activities.build_strategy_v2_stage0_activity(
        {
            "org_id": auth_context.org_id,
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": None,
            "workflow_run_id": workflow_run_id,
            "onboarding_payload_id": str(onboarding_payload.id),
            "stage0_overrides": {"product_customizable": True},
            "operator_user_id": "operator-1",
        }
    )

    step04_content = """
SOURCE: reddit.com/r/sleep
CATEGORY: H
EMOTION: frustration
INTENSITY: high
BUYER_STAGE: problem aware
SEGMENT_HINT: caregivers
"I keep trying more things but nights still spiral."

SOURCE: forum.sleephelp.com
CATEGORY: C
EMOTION: hope
INTENSITY: medium
BUYER_STAGE: problem aware
SEGMENT_HINT: parents
"I want a routine that doesn't collapse after two days."
""".strip()
    precanon_research = {
        "step_contents": {
            "01": "Category / Niche: Sleep Support\nValidated competitors: 3",
            "02": json.dumps(
                {
                    "asset_observation_sheets": [
                        {
                            "platform": "tiktok",
                            "views": 240000,
                            "followers": 18000,
                            "comments": 1200,
                            "shares": 400,
                            "likes": 5000,
                            "days_since_posted": 14,
                            "core_claim": "Night routine shift",
                            "competitor_name": "Competitor A",
                            "asset_id": "vid-1",
                        }
                    ],
                    "compliance_landscape": {"red_pct": 0.1, "yellow_pct": 0.2},
                }
            ),
            "03": "Deep research meta prompt output for step 03.",
            "04": step04_content,
            "06": (
                "- Exhausted caregivers with evening breakdown patterns\n"
                "- Parents juggling work and late-night setbacks\n"
                "- Buyers comparing routines after repeated failures\n"
                "Age range: 28-45\n"
                "Gender skew: predominantly female caregivers\n"
                "Platform habits: Reddit support threads, TikTok educational clips, Instagram routine reels\n"
                "Content consumption patterns: short-form troubleshooting videos, checklist posts, long-form forum threads\n"
                "Bottleneck: no consistent timing protocol"
            ),
        }
    }

    voc_angle_result = strategy_v2_activities.run_strategy_v2_voc_angle_pipeline_activity(
        {
            "org_id": auth_context.org_id,
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": None,
            "workflow_run_id": workflow_run_id,
            "stage0": stage0_result["stage0"],
            "precanon_research": precanon_research,
            "confirmed_competitor_assets": [
                "https://competitor-a.example/asset-1",
                "https://competitor-b.example/asset-2",
                "https://competitor-c.example/asset-3",
            ],
            "operator_user_id": "operator-1",
        }
    )

    assert isinstance(voc_angle_result["stage1"], dict)
    assert voc_angle_result["ranked_angle_candidates"]
    for step_key in ("01", "02", "03", "04", "06"):
        assert f"v2-02.foundation.{step_key}" in voc_angle_result["step_payload_artifact_ids"]


def test_strategy_v2_voc_pipeline_builds_foundational_research_from_onboarding_payload(
    api_client,
    db_session,
    auth_context,
    monkeypatch,
):
    @contextmanager
    def _session_scope_override():
        yield db_session

    monkeypatch.setattr(strategy_v2_activities, "session_scope", _session_scope_override)
    monkeypatch.setattr(
        strategy_v2_activities,
        "score_angles",
        lambda angle_observations, saturated_count: _mock_scored_angles(),
    )
    monkeypatch.setattr(strategy_v2_activities, "_require_agent00_executable_configs", lambda _payload: None)
    monkeypatch.setattr(strategy_v2_activities, "_require_agent00b_executable_configs", lambda _payload: None)
    monkeypatch.setattr(
        strategy_v2_activities,
        "_filter_metric_video_rows_for_scoring",
        lambda **kwargs: (
            [row for row in kwargs.get("video_rows", []) if isinstance(row, dict)],
            {
                "input_rows": len(kwargs.get("video_rows", [])),
                "missing_metrics": 0,
                "off_target_source": 0,
                "off_topic": 0,
                "kept_rows": len([row for row in kwargs.get("video_rows", []) if isinstance(row, dict)]),
            },
        ),
    )
    monkeypatch.setattr(strategy_v2_activities, "_AGENT1_COMPACTION_THRESHOLD", 200000)
    monkeypatch.setattr(
        strategy_v2_activities,
        "_run_agent2_extractor",
        lambda **_kwargs: {
            "mode": "DUAL",
            "voc_observations": [
                {
                    "voc_id": "V1",
                    "evidence_id": "E1111111111111111",
                    "source": "https://example.com",
                    "quote": "Sample VOC",
                }
            ],
            "rejected_items": [],
            "extraction_summary": {"input_count": 1, "output_count": 1, "rejected_count": 0},
            "prompt_provenance": {},
            "raw_outputs_preview": [],
        },
    )
    monkeypatch.setattr(strategy_v2_activities, "_normalize_voc_observations", lambda rows: rows)
    monkeypatch.setattr(
        strategy_v2_activities,
        "score_voc_items",
        lambda rows: {
            "items": [{"adjusted_score": 1.0, "zero_evidence_gate": False} for _ in rows] or [{"adjusted_score": 1.0, "zero_evidence_gate": False}],
            "summary": {"count": len(rows)},
        },
    )
    monkeypatch.setattr(strategy_v2_activities, "_require_voc_transition_quality", lambda **_kwargs: None)
    monkeypatch.setattr(strategy_v2_activities, "_validate_agent1_output_source_file_grounding", lambda **_kwargs: None)
    monkeypatch.setattr(
        strategy_v2_activities,
        "_ingest_strategy_v2_asset_data",
        _stub_ingest_strategy_v2_asset_data,
    )
    monkeypatch.setattr(
        strategy_v2_activities,
        "_run_foundational_research_from_onboarding",
        lambda **_kwargs: {
            "step_summaries": {
                "01": "Foundational summary",
                "03": "Meta-prompt summary",
                "04": "Deep research summary",
                "06": "Avatar summary",
            },
            "step_contents": {
                "01": "Category / Niche: Health & Wellness\nMarket Maturity: Growth\nValidated competitors: 3",
                "02": json.dumps(
                    {
                        "asset_observation_sheets": [
                            {
                                "platform": "tiktok",
                                "views": 240000,
                                "followers": 18000,
                                "comments": 1200,
                                "shares": 400,
                                "likes": 5000,
                                "days_since_posted": 14,
                                "core_claim": "Night routine shift",
                                "competitor_name": "Competitor A",
                                "asset_id": "vid-1",
                            }
                        ],
                        "compliance_landscape": {"red_pct": 0.1, "yellow_pct": 0.2},
                    }
                ),
                "03": "step3",
                "04": (
                    "SOURCE: reddit.com/r/herbalism\n"
                    "CATEGORY: H\n"
                    "EMOTION: frustration\n"
                    "INTENSITY: high\n"
                    "BUYER_STAGE: problem aware\n"
                    "SEGMENT_HINT: caregivers\n"
                    "\"I keep trying things and still feel overwhelmed.\""
                ),
                "06": (
                    "- Caregivers needing practical routines\n"
                    "- Parents researching safer alternatives\n"
                    "- Budget-conscious buyers seeking reliable outcomes\n"
                    "Age range: 30-50\n"
                    "Gender skew: female-leaning household decision makers\n"
                    "Platform habits: Reddit and YouTube for research, Instagram for examples\n"
                    "Content consumption patterns: evidence-led explainers, before/after breakdowns, checklists\n"
                    "Bottleneck: too much conflicting advice"
                ),
            },
        },
    )

    client_id, product_id = _create_client_and_product(
        api_client=api_client,
        suffix="InlineResearch",
        strategy_v2_enabled=True,
    )
    org_uuid = UUID(auth_context.org_id)
    client_uuid = UUID(client_id)
    product_uuid = UUID(product_id)

    onboarding_payload = OnboardingPayload(
        org_id=org_uuid,
        client_id=client_uuid,
        product_id=product_uuid,
        data={
            "product_name": "The Honest Herbalist Handbook",
            "brand_story": "We sell a natural remedies handbook.",
            "product_description": "A practical handbook for natural remedy routines at home.",
            "product_customizable": True,
            "product_category": "Health & Wellness",
            "competitor_urls": ["https://offer.ancientremediesrevived.com/c3-nb"],
            "primary_benefits": ["Simple routines", "Reference tables", "Daily implementation tips"],
        },
    )
    db_session.add(onboarding_payload)
    db_session.commit()
    db_session.refresh(onboarding_payload)

    ensure_run = strategy_v2_activities.ensure_strategy_v2_workflow_run_activity(
        {
            "org_id": auth_context.org_id,
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": None,
            "temporal_workflow_id": "strategy-v2-inline-onboarding-workflow",
            "temporal_run_id": "strategy-v2-inline-onboarding-run",
        }
    )
    workflow_run_id = ensure_run["workflow_run_id"]

    stage0_result = strategy_v2_activities.build_strategy_v2_stage0_activity(
        {
            "org_id": auth_context.org_id,
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": None,
            "workflow_run_id": workflow_run_id,
            "onboarding_payload_id": str(onboarding_payload.id),
            "stage0_overrides": {"product_customizable": True},
            "operator_user_id": "operator-1",
        }
    )

    voc_angle_result = strategy_v2_activities.run_strategy_v2_voc_angle_pipeline_activity(
        {
            "org_id": auth_context.org_id,
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": None,
            "workflow_run_id": workflow_run_id,
            "onboarding_payload_id": str(onboarding_payload.id),
            "stage0": stage0_result["stage0"],
            "confirmed_competitor_assets": [
                "https://competitor-a.example/asset-1",
                "https://competitor-b.example/asset-2",
                "https://competitor-c.example/asset-3",
            ],
            "operator_user_id": "operator-1",
        }
    )

    stage1 = voc_angle_result["stage1"]
    assert stage1["category_niche"] == "Health & Wellness"
    assert voc_angle_result["ranked_angle_candidates"]
    assert isinstance(voc_angle_result["competitor_analysis"].get("compliance_landscape"), dict)
    assert isinstance(voc_angle_result["video_scored"], list)
    foundational_ids = {
        step_key: artifact_id
        for step_key, artifact_id in voc_angle_result["step_payload_artifact_ids"].items()
        if step_key.startswith("v2-02.foundation.")
    }
    assert set(foundational_ids.keys()) == {
        "v2-02.foundation.01",
        "v2-02.foundation.02",
        "v2-02.foundation.03",
        "v2-02.foundation.04",
        "v2-02.foundation.06",
    }
    for artifact_id in foundational_ids.values():
        artifact = db_session.get(Artifact, UUID(artifact_id))
        assert artifact is not None
        assert artifact.type == ArtifactTypeEnum.strategy_v2_step_payload
    foundational_rows = (
        db_session.query(ResearchArtifact)
        .filter(ResearchArtifact.workflow_run_id == UUID(workflow_run_id))
        .filter(ResearchArtifact.step_key.like("v2-02.foundation.%"))
        .all()
    )
    assert {row.step_key for row in foundational_rows} == set(foundational_ids.keys())


def test_build_offer_variants_requires_nonempty_revision_notes(
    api_client,
    db_session,
    auth_context,
    monkeypatch,
):
    @contextmanager
    def _session_scope_override():
        yield db_session

    monkeypatch.setattr(strategy_v2_activities, "session_scope", _session_scope_override)

    original_run_prompt_json_object = strategy_v2_activities._run_prompt_json_object

    def _run_prompt_json_object_with_blank_revision_notes(*args, **kwargs):
        payload, raw_output, provenance = original_run_prompt_json_object(*args, **kwargs)
        if kwargs.get("context") == "strategy_v2.offer.step05":
            payload = dict(payload)
            payload["revision_notes"] = "   "
            raw_output = json.dumps(payload)
            provenance = dict(provenance)
            provenance["openai_response_id"] = "resp_test_step05"
        return payload, raw_output, provenance

    monkeypatch.setattr(
        strategy_v2_activities,
        "_run_prompt_json_object",
        _run_prompt_json_object_with_blank_revision_notes,
    )
    monkeypatch.setattr(
        strategy_v2_activities,
        "composite_scorer",
        lambda _evaluation, _config: {"any_passing": False},
    )

    client_id, product_id = _create_client_and_product(
        api_client=api_client,
        suffix="OfferVariantRevisionNotes",
        strategy_v2_enabled=True,
    )
    ensure_run = strategy_v2_activities.ensure_strategy_v2_workflow_run_activity(
        {
            "org_id": auth_context.org_id,
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": None,
            "temporal_workflow_id": "strategy-v2-offer-variants-revision-notes",
            "temporal_run_id": "strategy-v2-offer-variants-revision-notes-run",
        }
    )
    workflow_run_id = ensure_run["workflow_run_id"]

    stage2_payload = {
        "schema_version": "2.0.0",
        "stage": 2,
        "product_name": "Offer Variant Product",
        "description": "A detailed product description",
        "price": "$49",
        "competitor_urls": ["https://competitor-a.example"],
        "product_customizable": True,
        "category_niche": "Sleep Support",
        "product_category_keywords": ["sleep", "routine"],
        "market_maturity_stage": "Growth",
        "primary_segment": {
            "name": "Caregivers",
            "size_estimate": "Large",
            "key_differentiator": "Night routine instability",
        },
        "bottleneck": "No reliable night sequence",
        "positioning_gaps": ["Most offers ignore sequencing"],
        "competitor_count_validated": 3,
        "primary_icps": ["Working parents"],
        "selected_angle": _selected_angle_payload(),
        "compliance_constraints": {
            "overall_risk": "YELLOW",
            "red_flag_patterns": [],
            "platform_notes": "Avoid medical cure language.",
        },
        "buyer_behavior_archetype": "HIGH_TRUST",
        "purchase_emotion": "MIXED",
        "price_sensitivity": "medium",
    }

    offer_pipeline_output = {
        "pair_scoring": {
            "ranked_pairs": [
                {
                    "pair_id": "pair-a",
                    "ump_name": "Mechanism Gap",
                    "ums_name": "Evidence Protocol",
                }
            ]
        },
        "offer_input": {
            "product_brief": {
                "name": "Offer Variant Product",
                "description": "A detailed product description",
                "category": "Sleep Support",
                "price_cents": 4900,
                "currency": "USD",
                "business_model": "one-time",
                "funnel_position": "cold_traffic",
                "target_platforms": ["Meta"],
                "target_regions": ["US"],
                "product_customizable": True,
                "constraints": {
                    "compliance_sensitivity": "medium",
                    "existing_proof_assets": [],
                    "brand_voice_notes": "Direct and concrete.",
                },
            },
            "competitor_teardowns": "{}",
            "voc_research": "{}",
            "purple_ocean_research": "Purple ocean whitespace analysis.",
            "config": {
                "llm_model": "gpt-5.2-2025-12-11",
                "max_iterations": 2,
                "score_threshold": 8.5,
            },
        },
        "offer_prompt_chain": {
            "orchestrator_prompt_provenance": {
                "prompt_path": "V2 Fixes/Offer Agent — Final/prompts/pipeline-orchestrator.md",
                "prompt_sha256": "sha",
                "model_name": "gpt-5.2-2025-12-11",
                "input_contract_version": "2.0.0",
                "output_contract_version": "2.0.0",
            },
            "orchestrator_spec_excerpt": "Offer orchestrator contract excerpt.",
            "step_01_output": "Avatar findings",
            "step_02_output": "Market calibration findings",
        },
    }

    with pytest.raises(
        StrategyV2SchemaValidationError,
        match=r"response_id=resp_test_step05",
    ):
        strategy_v2_activities.build_strategy_v2_offer_variants_activity(
            {
                "org_id": auth_context.org_id,
                "client_id": client_id,
                "product_id": product_id,
                "campaign_id": None,
                "workflow_run_id": workflow_run_id,
                "stage2": stage2_payload,
                "offer_pipeline_output": offer_pipeline_output,
                "offer_data_readiness": {
                    "status": "ready",
                    "missing_fields": [],
                    "inconsistent_fields": [],
                    "context": {
                        "offer_format": "DISCOUNT_PLUS_3_BONUSES_V1",
                        "product_type": "digital",
                        "core_product": {"product_id": product_id, "title": "Offer Variant Product"},
                        "offer_id": "offer-1",
                        "offer_name": "Offer Variant Bundle",
                        "bonus_items": [
                            {
                                "bonus_id": "bonus-1",
                                "linked_product_id": "bonus-prod-1",
                                "title": "Bonus 1",
                                "product_type": "digital",
                                "position": 1,
                            },
                            {
                                "bonus_id": "bonus-2",
                                "linked_product_id": "bonus-prod-2",
                                "title": "Bonus 2",
                                "product_type": "digital",
                                "position": 2,
                            },
                            {
                                "bonus_id": "bonus-3",
                                "linked_product_id": "bonus-prod-3",
                                "title": "Bonus 3",
                                "product_type": "digital",
                                "position": 3,
                            },
                        ],
                        "pricing_metadata": {"list_price_cents": 9900, "offer_price_cents": 6900},
                        "savings_metadata": {
                            "savings_amount_cents": 3000,
                            "savings_percent": 30.3,
                            "savings_basis": "vs_list_price",
                        },
                        "bundle_contents": {
                            "core_product": {"product_id": product_id, "title": "Offer Variant Product"},
                            "offer_id": "offer-1",
                            "offer_name": "Offer Variant Bundle",
                            "bonuses": [
                                {"bonus_id": "bonus-1", "linked_product_id": "bonus-prod-1", "title": "Bonus 1"},
                                {"bonus_id": "bonus-2", "linked_product_id": "bonus-prod-2", "title": "Bonus 2"},
                                {"bonus_id": "bonus-3", "linked_product_id": "bonus-prod-3", "title": "Bonus 3"},
                            ],
                            "bonus_count": 3,
                        },
                    },
                },
                "ump_ums_selection_decision": {
                    "operator_user_id": "operator-1",
                    "pair_id": "pair-a",
                    "rejected_pair_ids": [],
                    "reviewed_candidate_ids": ["pair-a"],
                    **_manual_hitl_fields(
                        operator_note="Reviewed pair evidence and selected pair-a for highest plausibility.",
                    ),
                },
            }
        )


def test_strategy_v2_activity_integration_stage0_to_final_copy(
    api_client,
    db_session,
    auth_context,
    monkeypatch,
):
    @contextmanager
    def _session_scope_override():
        yield db_session

    monkeypatch.setattr(strategy_v2_activities, "session_scope", _session_scope_override)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        strategy_v2_activities,
        "run_headline_qa_loop",
        lambda **_kwargs: {
            "json": {
                "status": "PASS",
                "best_headline": "Approved Headline",
            }
        },
    )
    monkeypatch.setattr(
        strategy_v2_activities,
        "score_headline",
        lambda headline, page_type: {
            "result": {"headline": headline, "page_type": page_type},
            "composite": {"pct": 95.0, "hard_gate_pass": True},
            "json": {"headline": headline},
        },
    )
    monkeypatch.setattr(
        strategy_v2_activities,
        "build_page_data_from_body_text",
        lambda body_text, page_type=None: {"sections": [{"text": body_text[:200], "page_type": page_type}]},
    )
    monkeypatch.setattr(
        strategy_v2_activities,
        "_build_policy_footer_links",
        lambda **_kwargs: (
            [
                {"title": "Privacy Policy", "url": "https://example.com/privacy"},
                {"title": "Terms of Service", "url": "https://example.com/terms"},
            ],
            "Example Brand",
        ),
    )
    monkeypatch.setattr(
        strategy_v2_activities,
        "score_congruency_extended",
        lambda headline, page_data, promise_contract: {
            "headline": headline,
            "page_data": page_data,
            "promise_contract": promise_contract,
            "result": {
                "hp": [
                    ("HP1", "Number promise payment", 2, (True, "No number promise in headline (N/A -- auto-pass)")),
                ],
                "bh": [
                    ("BH1", "Theme coverage", 2, (True, "5/5 section topics connected to headline (100%)")),
                    ("BH3", "CTA alignment", 1, (True, "CTA echoes headline: approved ~ approved")),
                ],
                "pc": [
                    ("PC2", "Delivery test satisfied", 3, (True, "Keyword coverage: 3/3 (100%); Domain vocabulary hits: 5; DELIVERY SATISFIED")),
                ],
            },
            "composite": {"passed": True, "hard_gate_pass": True},
        },
    )
    class _QualityReportStub:
        def __init__(self, page_type: str) -> None:
            self._page_type = page_type

        def model_dump(self, mode: str = "python") -> dict[str, Any]:
            return {
                "schema_version": "2.0.0",
                "page_type": self._page_type,
                "passed": True,
                "total_words": 2000,
                "section_count": 12,
                "cta_count": 3,
                "first_cta_word_ratio": 0.3,
                "section_word_counts": [],
                "gates": [],
            }

    monkeypatch.setattr(
        strategy_v2_activities,
        "require_copy_page_quality",
        lambda markdown, page_contract, page_name: _QualityReportStub(page_contract.page_type),
    )
    monkeypatch.setattr(
        strategy_v2_activities,
        "score_angles",
        lambda angle_observations, saturated_count: _mock_scored_angles(),
    )
    monkeypatch.setattr(strategy_v2_activities, "_require_agent00_executable_configs", lambda _payload: None)
    monkeypatch.setattr(strategy_v2_activities, "_require_agent00b_executable_configs", lambda _payload: None)
    monkeypatch.setattr(
        strategy_v2_activities,
        "_filter_metric_video_rows_for_scoring",
        lambda **kwargs: (
            [row for row in kwargs.get("video_rows", []) if isinstance(row, dict)],
            {
                "input_rows": len(kwargs.get("video_rows", [])),
                "missing_metrics": 0,
                "off_target_source": 0,
                "off_topic": 0,
                "kept_rows": len([row for row in kwargs.get("video_rows", []) if isinstance(row, dict)]),
            },
        ),
    )
    monkeypatch.setattr(strategy_v2_activities, "_AGENT1_COMPACTION_THRESHOLD", 200000)
    monkeypatch.setattr(
        strategy_v2_activities,
        "_run_agent2_extractor",
        lambda **_kwargs: {
            "mode": "DUAL",
            "voc_observations": [
                {
                    "voc_id": "V1",
                    "evidence_id": "E1111111111111111",
                    "source": "https://example.com",
                    "quote": "Sample VOC",
                }
            ],
            "rejected_items": [],
            "extraction_summary": {"input_count": 1, "output_count": 1, "rejected_count": 0},
            "prompt_provenance": {},
            "raw_outputs_preview": [],
        },
    )
    monkeypatch.setattr(strategy_v2_activities, "_normalize_voc_observations", lambda rows: rows)
    monkeypatch.setattr(
        strategy_v2_activities,
        "score_voc_items",
        lambda rows: {
            "items": [{"adjusted_score": 1.0, "zero_evidence_gate": False} for _ in rows] or [{"adjusted_score": 1.0, "zero_evidence_gate": False}],
            "summary": {"count": len(rows)},
        },
    )
    monkeypatch.setattr(strategy_v2_activities, "_require_voc_transition_quality", lambda **_kwargs: None)
    monkeypatch.setattr(strategy_v2_activities, "_validate_agent1_output_source_file_grounding", lambda **_kwargs: None)
    monkeypatch.setattr(
        strategy_v2_activities,
        "_ingest_strategy_v2_asset_data",
        _stub_ingest_strategy_v2_asset_data,
    )

    client_id, product_id = _create_client_and_product(
        api_client=api_client,
        suffix="E2E",
        strategy_v2_enabled=True,
    )
    org_uuid = UUID(auth_context.org_id)
    client_uuid = UUID(client_id)
    product_uuid = UUID(product_id)

    onboarding_payload = OnboardingPayload(
        org_id=org_uuid,
        client_id=client_uuid,
        product_id=product_uuid,
        data={
            "product_name": "Product E2E",
            "product_description": "Detailed product description",
            "product_customizable": True,
            "competitor_urls": ["https://competitor-a.example"],
            "price": "$49",
        },
    )
    db_session.add(onboarding_payload)
    db_session.commit()
    db_session.refresh(onboarding_payload)

    competitor_analysis = {
        "asset_observation_sheets": [
            {
                "platform": "tiktok",
                "views": 240000,
                "followers": 18000,
                "comments": 1200,
                "shares": 400,
                "likes": 5000,
                "days_since_posted": 14,
                "core_claim": "Night routine shift",
                "competitor_name": "Competitor A",
                "asset_id": "vid-1",
            }
        ],
        "compliance_landscape": {
            "red_pct": 0.1,
            "yellow_pct": 0.2,
        },
    }
    step04_content = """
SOURCE: reddit.com/r/sleep
CATEGORY: H
EMOTION: frustration
INTENSITY: high
BUYER_STAGE: problem aware
SEGMENT_HINT: caregivers
"When evenings hit, I panic because nothing we've tried works."

SOURCE: reddit.com/r/sleep
CATEGORY: C
EMOTION: hope
INTENSITY: medium
BUYER_STAGE: problem aware
SEGMENT_HINT: caregivers
"I just want a predictable night routine that doesn't fail after 2 days."

SOURCE: forum.sleephelp.com
CATEGORY: G
EMOTION: anxiety
INTENSITY: high
BUYER_STAGE: problem aware
SEGMENT_HINT: parents
"We spent $300 on random fixes and still wake up exhausted."
""".strip()
    precanon_research = {
        "step_contents": {
            "01": (
                "Category / Niche: Sleep Support\n"
                "Validated competitors: 3\n"
                "- Gap: Most messaging ignores timing triggers\n"
                "Growth"
            ),
            "02": str(competitor_analysis).replace("'", '"'),
            "03": "Meta prompt synthesis for downstream deep research.",
            "04": step04_content,
            "06": (
                "- Exhausted working parents with unpredictable nights\n"
                "- Caregivers dealing with routine breakdowns\n"
                "- Families comparing costly options without clear outcomes\n"
                "Age range: 27-46\n"
                "Gender skew: mostly female caregivers with mixed-gender partners\n"
                "Platform habits: Reddit communities, TikTok bedtime tips, YouTube deep dives\n"
                "Content consumption patterns: short tutorials, practical scripts, long narrative testimonials\n"
                "Bottleneck: no consistent timing protocol"
            ),
        }
    }

    ensure_run = strategy_v2_activities.ensure_strategy_v2_workflow_run_activity(
        {
            "org_id": auth_context.org_id,
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": None,
            "temporal_workflow_id": "strategy-v2-e2e-workflow",
            "temporal_run_id": "strategy-v2-e2e-run",
        }
    )
    workflow_run_id = ensure_run["workflow_run_id"]

    stage0_result = strategy_v2_activities.build_strategy_v2_stage0_activity(
        {
            "org_id": auth_context.org_id,
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": None,
            "workflow_run_id": workflow_run_id,
            "onboarding_payload_id": str(onboarding_payload.id),
            "stage0_overrides": {"product_customizable": True},
            "operator_user_id": "operator-1",
        }
    )
    voc_angle_result = strategy_v2_activities.run_strategy_v2_voc_angle_pipeline_activity(
        {
            "org_id": auth_context.org_id,
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": None,
            "workflow_run_id": workflow_run_id,
            "stage0": stage0_result["stage0"],
            "precanon_research": precanon_research,
            "confirmed_competitor_assets": [
                "https://competitor-a.example/asset-1",
                "https://competitor-b.example/asset-2",
                "https://competitor-c.example/asset-3",
            ],
            "operator_user_id": "operator-1",
        }
    )
    selected_angle = voc_angle_result["ranked_angle_candidates"][0]["angle"]
    selected_angle["hook_starters"] = None
    voc_angle_result["ranked_angle_candidates"][0]["angle"]["hook_starters"] = None

    stage2_result = strategy_v2_activities.apply_strategy_v2_angle_selection_activity(
        {
            "org_id": auth_context.org_id,
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": None,
            "workflow_run_id": workflow_run_id,
            "stage1": voc_angle_result["stage1"],
            "ranked_angle_candidates": voc_angle_result["ranked_angle_candidates"],
            "angle_selection_decision": {
                "operator_user_id": "operator-1",
                "selected_angle": selected_angle,
                "rejected_angle_ids": [],
                "reviewed_candidate_ids": [str(selected_angle["angle_id"])],
                **_manual_hitl_fields(
                    operator_note="Selected the strongest angle after reviewing scored candidate evidence.",
                ),
            },
        }
    )
    offer_pipeline_output = strategy_v2_activities.run_strategy_v2_offer_pipeline_activity(
        {
            "org_id": auth_context.org_id,
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": None,
            "workflow_run_id": workflow_run_id,
            "stage2": stage2_result["stage2"],
            "competitor_analysis": voc_angle_result["competitor_analysis"],
            "angle_synthesis": {"ranked_candidates": voc_angle_result["ranked_angle_candidates"]},
            "business_model": "one-time",
            "funnel_position": "cold_traffic",
            "target_platforms": ["Meta", "TikTok"],
            "target_regions": ["US"],
            "existing_proof_assets": ["Customer testimonials"],
            "brand_voice_notes": "Direct, concrete, no hype.",
            "operator_user_id": "operator-1",
        }
    )
    pair_id = offer_pipeline_output["pair_scoring"]["ranked_pairs"][0]["pair_id"]

    offer_variants_output = strategy_v2_activities.build_strategy_v2_offer_variants_activity(
        {
            "org_id": auth_context.org_id,
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": None,
            "workflow_run_id": workflow_run_id,
            "stage2": stage2_result["stage2"],
            "offer_pipeline_output": offer_pipeline_output,
            "offer_data_readiness": {
                "status": "ready",
                "missing_fields": [],
                "inconsistent_fields": [],
                "context": {
                    "offer_format": "DISCOUNT_PLUS_3_BONUSES_V1",
                    "product_type": "digital",
                    "core_product": {"product_id": product_id, "title": "Offer Variant Product"},
                    "offer_id": "offer-1",
                    "offer_name": "Offer Variant Bundle",
                    "bonus_items": [
                        {
                            "bonus_id": "bonus-1",
                            "linked_product_id": "bonus-prod-1",
                            "title": "Bonus 1",
                            "product_type": "digital",
                            "position": 1,
                        },
                        {
                            "bonus_id": "bonus-2",
                            "linked_product_id": "bonus-prod-2",
                            "title": "Bonus 2",
                            "product_type": "digital",
                            "position": 2,
                        },
                        {
                            "bonus_id": "bonus-3",
                            "linked_product_id": "bonus-prod-3",
                            "title": "Bonus 3",
                            "product_type": "digital",
                            "position": 3,
                        },
                    ],
                    "pricing_metadata": {"list_price_cents": 9900, "offer_price_cents": 6900},
                    "savings_metadata": {
                        "savings_amount_cents": 3000,
                        "savings_percent": 30.3,
                        "savings_basis": "vs_list_price",
                    },
                    "bundle_contents": {
                        "core_product": {"product_id": product_id, "title": "Offer Variant Product"},
                        "offer_id": "offer-1",
                        "offer_name": "Offer Variant Bundle",
                        "bonuses": [
                            {"bonus_id": "bonus-1", "linked_product_id": "bonus-prod-1", "title": "Bonus 1"},
                            {"bonus_id": "bonus-2", "linked_product_id": "bonus-prod-2", "title": "Bonus 2"},
                            {"bonus_id": "bonus-3", "linked_product_id": "bonus-prod-3", "title": "Bonus 3"},
                        ],
                        "bonus_count": 3,
                    },
                },
            },
            "ump_ums_selection_decision": {
                "operator_user_id": "operator-1",
                "pair_id": pair_id,
                "rejected_pair_ids": [],
                "reviewed_candidate_ids": [pair_id],
                **_manual_hitl_fields(
                    operator_note="Selected this UMP/UMS pair based on fit, clarity, and risk profile.",
                ),
            },
        }
    )
    variant_id = offer_variants_output["variants"][0]["variant_id"]

    stage3_result = strategy_v2_activities.finalize_strategy_v2_offer_winner_activity(
        {
            "org_id": auth_context.org_id,
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": None,
            "workflow_run_id": workflow_run_id,
            "stage2": stage2_result["stage2"],
            "offer_pipeline_output": offer_pipeline_output,
            "offer_variants_output": offer_variants_output,
            "offer_winner_decision": {
                "operator_user_id": "operator-1",
                "variant_id": variant_id,
                "rejected_variant_ids": [],
                "reviewed_candidate_ids": [variant_id],
                **_manual_hitl_fields(
                    operator_note="Selected winner variant after reviewing scored variants and rationale.",
                ),
            },
            "brand_voice_notes": "Direct, concrete, no hype.",
            "compliance_notes": "Avoid medical cure claims.",
        }
    )
    assert stage3_result["awareness_matrix_artifact_id"]
    assert stage3_result.get("product_offer_id")
    synced_offer = db_session.query(ProductOffer).filter(
        ProductOffer.org_id == org_uuid,
        ProductOffer.id == UUID(stage3_result["product_offer_id"]),
    ).first()
    assert synced_offer is not None
    assert str(synced_offer.client_id) == client_id
    assert str(synced_offer.product_id) == product_id
    assert synced_offer.name == stage3_result["stage3"]["core_promise"]
    assert synced_offer.options_schema is not None
    assert synced_offer.options_schema.get("strategyV2Offer", {}).get("variant_id") == stage3_result["stage3"][
        "variant_selected"
    ]
    copy_result = strategy_v2_activities.run_strategy_v2_copy_pipeline_activity(
        {
            "org_id": auth_context.org_id,
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": None,
            "workflow_run_id": workflow_run_id,
            "stage3": stage3_result["stage3"],
            "copy_context": stage3_result["copy_context"],
            "operator_user_id": "operator-1",
        }
    )
    assert copy_result.get("step_payload_artifact_id")
    assert copy_result["copy_payload"]["copy_generation_mode"] == "template_payload_only"
    assert copy_result["copy_payload"]["template_payloads"]["pre-sales-listicle"]["fields"]
    assert copy_result["copy_payload"]["template_payloads"]["sales-pdp"]["fields"]
    assert copy_result["copy_payload"]["copy_contract_profile"]["profile_id"] == "strategy_v2_warm_presell_v1"
    assert copy_result["copy_payload"]["copy_input_packet"]["profile_id"] == "strategy_v2_warm_presell_v1"
    assert copy_result["copy_payload"]["semantic_gates"]["presell"]["passed"] is True
    assert copy_result["copy_payload"]["semantic_gates"]["sales_page"]["passed"] is True
    assert copy_result["copy_payload"]["copy_prompt_chain_provenance"]["passed"] is True
    assert copy_result["copy_payload"]["congruency"]["composite"]["hard_gate_pass"] is True
    final_result = strategy_v2_activities.finalize_strategy_v2_copy_approval_activity(
        {
            "org_id": auth_context.org_id,
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": None,
            "workflow_run_id": workflow_run_id,
            "final_approval_decision": {
                "operator_user_id": "operator-1",
                "approved": True,
                "reviewed_candidate_ids": ["copy-artifact-1"],
                **_manual_hitl_fields(
                    operator_note="Reviewed copy quality and congruency outputs and approve release.",
                ),
            },
            "copy_payload": copy_result["copy_payload"],
        }
    )
    assert final_result.get("step_payload_artifact_id")

    approved_artifact = db_session.query(Artifact).filter(
        Artifact.org_id == org_uuid,
        Artifact.id == UUID(final_result["approved_artifact_id"]),
    ).first()
    assert approved_artifact is not None
    assert approved_artifact.type == ArtifactTypeEnum.strategy_v2_copy
    assert isinstance(approved_artifact.data, dict)
    assert "approved_copy" in approved_artifact.data

    workflow_run = db_session.query(WorkflowRun).filter(
        WorkflowRun.org_id == org_uuid,
        WorkflowRun.id == UUID(workflow_run_id),
    ).first()
    assert workflow_run is not None
    assert workflow_run.status.value == "completed"
