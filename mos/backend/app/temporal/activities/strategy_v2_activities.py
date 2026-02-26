from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping
import urllib.request
from urllib.parse import urlsplit

from sqlalchemy import select
from temporalio import activity

from app.config import settings
from app.db.base import session_scope
from app.db.enums import AgentRunStatusEnum, ArtifactTypeEnum, WorkflowStatusEnum
from app.db.models import Product, WorkflowRun
from app.db.repositories.agent_runs import AgentRunsRepository
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.onboarding_payloads import OnboardingPayloadsRepository
from app.db.repositories.research_artifacts import ResearchArtifactsRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.llm import LLMClient, LLMGenerationParams
from app.strategy_v2 import (
    AngleSelectionDecision,
    AwarenessAngleMatrix,
    CompetitorAssetConfirmationDecision,
    FinalCopyApprovalDecision,
    OfferWinnerSelectionDecision,
    ProductBriefStage0,
    ProductBriefStage1,
    ProductBriefStage2,
    ProductBriefStage3,
    ResearchProceedDecision,
    StrategyV2DecisionError,
    StrategyV2MissingContextError,
    UmpUmsSelectionDecision,
    build_copy_stage4_input_packet,
    build_copy_context_files,
    build_competitor_angle_map,
    build_page_data_from_body_text,
    default_copy_contract_profile,
    calibration_consistency_checker,
    composite_scorer,
    get_page_contract,
    derive_compliance_sensitivity,
    render_copy_headline_runtime_instruction,
    render_copy_page_runtime_instruction,
    require_copy_page_quality,
    require_copy_page_semantic_quality,
    require_prompt_chain_provenance,
    extract_competitor_analysis,
    extract_saturated_angles,
    hormozi_scorer,
    map_offer_pipeline_input,
    novelty_calculator,
    objection_coverage_calculator,
    run_headline_qa_loop,
    run_strategy_v2_apify_ingestion,
    score_angles,
    score_candidate_assets,
    score_congruency_extended,
    score_habitats,
    score_headline,
    score_videos,
    score_voc_items,
    select_top_candidates,
    build_url_candidates,
    transform_step4_entries_to_agent2_corpus,
    translate_stage0,
    translate_stage1,
    ump_ums_scorer,
)
from app.strategy_v2.contracts import (
    SCHEMA_VERSION_V2,
    SelectedAngleContract,
    validate_stage2,
    validate_stage3,
)
from app.strategy_v2.errors import StrategyV2Error, StrategyV2SchemaValidationError
from app.strategy_v2.feature_flags import is_strategy_v2_enabled
from app.strategy_v2.copy_quality import evaluate_copy_page_quality
from app.strategy_v2.copy_input_packet import parse_minimum_delivery_section_index
from app.strategy_v2.prompt_runtime import (
    PromptAsset,
    build_prompt_provenance,
    extract_required_json_array,
    extract_required_json_object,
    render_prompt_template as render_prompt_template_strict,
    resolve_prompt_asset,
)
from app.services.claude_files import call_claude_structured_message
from app.strategy_v2.step_keys import (
    V2_STEP_ANGLE_SELECTION_HITL,
    V2_STEP_ANGLE_SYNTHESIS,
    V2_STEP_ASSET_DATA_INGESTION,
    V2_STEP_COMPETITOR_ASSETS_HITL,
    V2_STEP_COPY_PIPELINE,
    V2_STEP_FINAL_APPROVAL_HITL,
    V2_STEP_HABITAT_SCORING,
    V2_STEP_HABITAT_STRATEGY,
    V2_STEP_OFFER_PIPELINE,
    V2_STEP_OFFER_VARIANT_SCORING,
    V2_STEP_OFFER_WINNER_HITL,
    V2_STEP_RESEARCH_PROCEED_HITL,
    V2_STEP_SCRAPE_VIRALITY,
    V2_STEP_STAGE0_BUILD,
    V2_STEP_VOC_EXTRACTION,
)
from app.temporal.precanon.research import parse_step_output


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_dict(*, payload: object, field_name: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise StrategyV2SchemaValidationError(f"Expected '{field_name}' to be an object.")
    return payload


_FOUNDATIONAL_PROMPT_01_PATTERN = "Foundational Docs/clean_prompts/01_competitor_research_v2.md"
_FOUNDATIONAL_PROMPT_03_PATTERN = "Foundational Docs/clean_prompts/03_deep_research_meta_prompt_v2.md"
_FOUNDATIONAL_PROMPT_06_PATTERN = "Foundational Docs/clean_prompts/06_avatar_brief_v2.md"

_FOUNDTN_STEP01_SUMMARY_MAX = 1500
_FOUNDTN_STEP03_SUMMARY_MAX = 1200
_FOUNDTN_STEP03_PROMPT_MAX = 40000
_FOUNDTN_STEP04_SUMMARY_MAX = 1800
_FOUNDTN_STEP06_SUMMARY_MAX = 1500

_FOUNDTN_STEP01_MODEL = os.getenv("STRATEGY_V2_FOUNDATIONAL_STEP01_MODEL", settings.STRATEGY_V2_VOC_MODEL)
_FOUNDTN_STEP03_MODEL = os.getenv("STRATEGY_V2_FOUNDATIONAL_STEP03_MODEL", settings.STRATEGY_V2_VOC_MODEL)
_FOUNDTN_STEP04_MODEL = os.getenv("STRATEGY_V2_FOUNDATIONAL_STEP04_MODEL", settings.STRATEGY_V2_VOC_MODEL)
_FOUNDTN_STEP06_MODEL = os.getenv("STRATEGY_V2_FOUNDATIONAL_STEP06_MODEL", settings.STRATEGY_V2_VOC_MODEL)
_FOUNDTN_STEP04_MAX_TOKENS = int(os.getenv("STRATEGY_V2_FOUNDATIONAL_STEP04_MAX_TOKENS", "12000"))

_VOC_AGENT00_PROMPT_PATTERN = "VOC + Angle Engine (2-21-26)/prompts/agent-00-habitat-strategist.md"
_VOC_AGENT00B_PROMPT_PATTERN = "VOC + Angle Engine (2-21-26)/prompts/agent-00b-social-video-strategist.md"
_VOC_AGENT01_PROMPT_PATTERN = "VOC + Angle Engine (2-21-26)/prompts/agent-01-habitat-qualifier.md"
_VOC_AGENT02_PROMPT_PATTERN = "VOC + Angle Engine (2-21-26)/prompts/agent-02-voc-extractor.md"
_VOC_AGENT03_PROMPT_PATTERN = "VOC + Angle Engine (2-21-26)/prompts/agent-03-shadow-angle-clusterer.md"
_VOC_COMPETITOR_ANALYZER_PROMPT_PATTERN = (
    "VOC + Angle Engine (2-21-26)/prompts/agent-pre-competitor-asset-analyzer.md"
)

_OFFER_STEP01_PROMPT_PATTERN = "Offer Agent */prompts/step-01-avatar-brief.md"
_OFFER_STEP02_PROMPT_PATTERN = "Offer Agent */prompts/step-02-market-calibration.md"
_OFFER_STEP03_PROMPT_PATTERN = "Offer Agent */prompts/step-03-ump-ums-generation.md"
_OFFER_STEP04_PROMPT_PATTERN = "Offer Agent */prompts/step-04-offer-construction.md"
_OFFER_STEP05_PROMPT_PATTERN = "Offer Agent */prompts/step-05-self-evaluation-scoring.md"
_OFFER_ORCHESTRATOR_PROMPT_PATTERN = "Offer Agent */prompts/pipeline-orchestrator.md"

_COPY_HEADLINE_PROMPT_PATTERN = "Copywriting Agent */04_prompt_templates/headline_generation.md"
_COPY_PROMISE_PROMPT_PATTERN = "Copywriting Agent */04_prompt_templates/promise_contract_extraction.md"
_COPY_ADVERTORIAL_PROMPT_PATTERN = "Copywriting Agent */04_prompt_templates/advertorial_writing.md"
_COPY_SALES_PROMPT_PATTERN = "Copywriting Agent */04_prompt_templates/sales_page_writing.md"
_COPY_PAGE_REPAIR_MAX_ATTEMPTS = int(os.getenv("STRATEGY_V2_COPY_PAGE_REPAIR_MAX_ATTEMPTS", "5"))
_COPY_HEADLINE_MAX_CANDIDATES = int(os.getenv("STRATEGY_V2_COPY_HEADLINE_MAX_CANDIDATES", "15"))
_COPY_HEADLINE_QA_MAX_ITERATIONS = int(os.getenv("STRATEGY_V2_COPY_HEADLINE_QA_MAX_ITERATIONS", "6"))
_COPY_HEADLINE_TRANSIENT_FAIL_FAST_THRESHOLD = int(
    os.getenv("STRATEGY_V2_COPY_HEADLINE_TRANSIENT_FAIL_FAST_THRESHOLD", "6")
)
_COPY_DEBUG_CAPTURE_MARKDOWN = os.getenv("STRATEGY_V2_COPY_DEBUG_CAPTURE_MARKDOWN", "0").strip() == "1"
_COPY_DEBUG_CAPTURE_THREADS = os.getenv("STRATEGY_V2_COPY_DEBUG_CAPTURE_THREADS", "0").strip() == "1"
_COPY_DEBUG_CAPTURE_FULL_MARKDOWN = os.getenv("STRATEGY_V2_COPY_DEBUG_CAPTURE_FULL_MARKDOWN", "0").strip() == "1"
_COPY_WORD_FLOOR_ERROR_RE = re.compile(
    r"(?P<reason>[A-Z_]+_WORD_FLOOR):\s*total_words=(?P<current>\d+),\s*required>=(?P<min>\d+)",
    re.IGNORECASE,
)
_COPY_WORD_CEILING_ERROR_RE = re.compile(
    r"(?P<reason>[A-Z_]+_WORD_CEILING):\s*total_words=(?P<current>\d+),\s*required<=(?P<max>\d+)",
    re.IGNORECASE,
)
_COPY_CTA_COUNT_ERROR_RE = re.compile(
    r"(?P<reason>[A-Z_]+_CTA_COUNT):\s*cta_count=(?P<current>\d+),\s*required_range=\[(?P<min>\d+),(?P<max>\d+)\]",
    re.IGNORECASE,
)
_COPY_SALES_PROOF_DEPTH_ERROR_RE = re.compile(
    r"SALES_PROOF_DEPTH:\s*proof_words=(?P<current>\d+),\s*required>=(?P<min>\d+)",
    re.IGNORECASE,
)
_COPY_CONGRUENCY_BH1_ERROR_RE = re.compile(
    r"congruency test BH1 failed:\s*(?P<detail>.+)",
    re.IGNORECASE,
)
_COPY_PROMISE_DELIVERY_TIMING_ERROR_RE = re.compile(
    r"PROMISE_DELIVERY_TIMING:\s*(?P<detail>.+)",
    re.IGNORECASE,
)
_COPY_REQUIRED_SECTION_COVERAGE_ERROR_RE = re.compile(
    r"REQUIRED_SECTION_COVERAGE:\s*Missing required sections:\s*(?P<sections>[^;]+)",
    re.IGNORECASE,
)
_COPY_REQUIRED_SIGNAL_COVERAGE_ERROR_RE = re.compile(
    r"REQUIRED_SIGNAL_COVERAGE:\s*(?P<detail>[^;]+)",
    re.IGNORECASE,
)
_COPY_BELIEF_SEQUENCE_ORDER_ERROR_RE = re.compile(
    r"BELIEF_SEQUENCE_ORDER:\s*(?P<detail>[^;]+)",
    re.IGNORECASE,
)
_MARKDOWN_LINK_CAPTURE_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_CTA_HEADING_ANY_RE = re.compile(r"\bcta\b", re.IGNORECASE)
_CONTINUE_TO_OFFER_HEADING_RE = re.compile(r"\bcontinue\s+to\s+offer\b", re.IGNORECASE)
_CTA_HEADING_RENUMBER_RE = re.compile(r"\bcta(?:\s*#?\s*\d+)?\b", re.IGNORECASE)
_NON_CTA_HEADING_RE = re.compile(r"\bnon[-\s]*cta\b", re.IGNORECASE)

_COPY_PRESELL_CANONICAL_SECTION_ORDER = (
    "Hook/Lead",
    "Problem Crystallization",
    "Failed Solutions",
    "Mechanism Reveal",
    "Proof + Bridge",
    "Transition CTA",
)
_COPY_SALES_CANONICAL_SECTION_ORDER = (
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
)

_HEADLINE_ANCHOR_STOPWORDS = {
    "about",
    "after",
    "before",
    "check",
    "from",
    "have",
    "into",
    "most",
    "that",
    "their",
    "these",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
    "your",
}
_PROMISE_TERM_STOPWORDS = {
    "about",
    "after",
    "before",
    "being",
    "by",
    "deliver",
    "delivery",
    "first",
    "from",
    "have",
    "include",
    "minimum",
    "must",
    "page",
    "promise",
    "section",
    "sections",
    "specific",
    "terms",
    "that",
    "this",
    "timing",
    "what",
    "when",
    "with",
    "your",
}
_PC2_DOMAIN_REPAIR_TERMS = (
    "interaction",
    "contraindicated",
    "dosing",
    "toxicity",
    "side-effect",
    "risk",
)
_HEADLINE_NUMBER_WORDS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

_PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Z0-9_]+)\}\}")

_UMP_UMS_DIMENSIONS = (
    "competitive_uniqueness",
    "voc_groundedness",
    "believability",
    "mechanism_clarity",
    "angle_alignment",
    "compliance_safety",
    "memorability",
)

_OFFER_VARIANT_IDS = ("base", "variant_a", "variant_b")
_OFFER_ORCHESTRATOR_REQUIRED_STEP_PROMPTS = (
    "step-01-avatar-brief.md",
    "step-02-market-calibration.md",
    "step-03-ump-ums-generation.md",
    "step-04-offer-construction.md",
    "step-05-self-evaluation-scoring.md",
)

_MIN_STAGE1_COMPETITORS = 3
_MIN_STAGE1_PRIMARY_ICPS = 3
_MIN_SELECTED_ANGLE_SUPPORTING_VOC = 5
_MIN_SELECTED_ANGLE_TOP_QUOTES = 5
_MIN_AGENT3_ANGLE_CANDIDATES = 10
_MAX_AGENT3_ANGLE_OBSERVATIONS = 24
_AGENT3_TOP_QUOTES_PER_CANDIDATE = 5
_AGENT3_HOOK_STARTERS_PER_CANDIDATE = 3
_AGENT3_MAX_TEXT_CHARS = 280
_AGENT3_MAX_QUOTE_CHARS = 320
_AGENT1_MAX_TOKENS = int(os.getenv("STRATEGY_V2_AGENT1_MAX_TOKENS", "16000"))
_AGENT2_MAX_TOKENS = int(os.getenv("STRATEGY_V2_AGENT2_MAX_TOKENS", "64000"))
_AGENT3_MAX_TOKENS = int(os.getenv("STRATEGY_V2_AGENT3_MAX_TOKENS", "32000"))

_H2_MAX_CANDIDATE_ASSETS = int(os.getenv("STRATEGY_V2_H2_MAX_CANDIDATE_ASSETS", "40"))
_H2_MAX_CANDIDATES_PER_COMPETITOR = int(os.getenv("STRATEGY_V2_H2_MAX_CANDIDATES_PER_COMPETITOR", "3"))
_H2_MAX_CANDIDATES_PER_PLATFORM = int(os.getenv("STRATEGY_V2_H2_MAX_CANDIDATES_PER_PLATFORM", "10"))
_H2_TARGET_CONFIRMED_ASSETS = int(os.getenv("STRATEGY_V2_H2_TARGET_CONFIRMED_ASSETS", "12"))
_H2_MAX_CONFIRMED_ASSETS = int(os.getenv("STRATEGY_V2_H2_MAX_CONFIRMED_ASSETS", "15"))

_VOC_MERGED_CORPUS_MAX_ROWS = int(os.getenv("STRATEGY_V2_VOC_MERGED_CORPUS_MAX_ROWS", "400"))
_VOC_PROMPT_CORPUS_ROWS = int(os.getenv("STRATEGY_V2_VOC_PROMPT_CORPUS_ROWS", "80"))
_VOC_PROMPT_STEP4_ROWS = int(os.getenv("STRATEGY_V2_VOC_PROMPT_STEP4_ROWS", "40"))
_VOC_PROMPT_EXTERNAL_ROWS = int(os.getenv("STRATEGY_V2_VOC_PROMPT_EXTERNAL_ROWS", "40"))
_VOC_SOURCE_DIVERSITY_MAX_RATIO = float(os.getenv("STRATEGY_V2_VOC_SOURCE_DIVERSITY_MAX_RATIO", "0.25"))
_VOC_MIN_OBSERVATIONS_GATE = int(os.getenv("STRATEGY_V2_VOC_MIN_OBSERVATIONS_GATE", "5"))
_VOC_MIN_NON_ZERO_SCORE_RATIO = float(os.getenv("STRATEGY_V2_VOC_MIN_NON_ZERO_SCORE_RATIO", "0.35"))
_VOC_MAX_ZERO_EVIDENCE_RATIO = float(os.getenv("STRATEGY_V2_VOC_MAX_ZERO_EVIDENCE_RATIO", "0.60"))
_VOC_MIN_SOURCE_BUCKETS = int(os.getenv("STRATEGY_V2_VOC_MIN_SOURCE_BUCKETS", "2"))

_ANGLE_MIN_STD_SCORE = float(os.getenv("STRATEGY_V2_ANGLE_MIN_STD_SCORE", "0.5"))
_ANGLE_MIN_NON_FLOOR_CANDIDATES = int(os.getenv("STRATEGY_V2_ANGLE_MIN_NON_FLOOR_CANDIDATES", "3"))
_ANGLE_MIN_TOP_DEMAND_SIGNAL = float(os.getenv("STRATEGY_V2_ANGLE_MIN_TOP_DEMAND_SIGNAL", "5.0"))
_ANGLE_SELECTION_MIN_DEMAND_SIGNAL = float(
    os.getenv("STRATEGY_V2_ANGLE_SELECTION_MIN_DEMAND_SIGNAL", "5.0")
)
_ANGLE_SELECTION_MIN_EVIDENCE_QUALITY = float(
    os.getenv("STRATEGY_V2_ANGLE_SELECTION_MIN_EVIDENCE_QUALITY", "5.0")
)

_FOUNDATIONAL_STEP_KEYS = ("01", "02", "03", "04", "06")
_FOUNDATIONAL_STEP_ARTIFACT_META: dict[str, dict[str, str]] = {
    "01": {
        "title": "Strategy V2 Foundational Step 01 Raw Output",
        "summary": "Raw foundational competitor landscape output for step 01.",
    },
    "02": {
        "title": "Strategy V2 Foundational Step 02 Raw Output",
        "summary": "Raw foundational competitor analysis JSON for step 02.",
    },
    "03": {
        "title": "Strategy V2 Foundational Step 03 Raw Output",
        "summary": "Raw foundational deep-research meta prompt output for step 03.",
    },
    "04": {
        "title": "Strategy V2 Foundational Step 04 Raw Output",
        "summary": "Raw foundational tagged deep-research corpus for step 04.",
    },
    "06": {
        "title": "Strategy V2 Foundational Step 06 Raw Output",
        "summary": "Raw foundational avatar brief output for step 06.",
    },
}

_BLOCKED_OPERATOR_USER_IDS = {
    "system",
    "system-monitor",
    "automation",
    "auto-approver",
}
_BLOCKED_OPERATOR_PREFIXES = ("system-", "bot-", "auto-")
_AUTO_SELECTION_NOTE_PATTERN = re.compile(
    r"\b(auto[-\s]?select(?:ed|ion)?|automation|automated|bot[-\s]?driven)\b",
    flags=re.IGNORECASE,
)
_MIN_HITL_OPERATOR_NOTE_LEN = 20
_HITL_POLICY_MODE_ENV = "STRATEGY_V2_HITL_POLICY_MODE"
_HITL_POLICY_PRODUCTION_STRICT = "production_strict"
_HITL_POLICY_INTERNAL_VALIDATION = "internal_validation"

_BLOCKED_PROMPT_OUTPUT_TOKENS = (
    "BLOCKED_MISSING_REQUIRED_INPUTS",
    "MISSING_REQUIRED_INPUTS",
    "CANNOT_PROCEED",
)
_PROMPT_BLOCK_SIGNAL_KEYS = (
    "status",
    "mode",
    "handoff_block",
    "error",
    "errors",
    "reason",
    "message",
    "blocking_reason",
)
_AVATAR_PLATFORM_TOKENS = (
    "tiktok",
    "instagram",
    "youtube",
    "reddit",
    "facebook",
    "meta",
    "x",
    "twitter",
    "pinterest",
)
_NON_SCRAPEABLE_SOURCE_HOSTS = {
    "apify.com",
    "www.apify.com",
    "google.com",
    "www.google.com",
    "bing.com",
    "www.bing.com",
    "duckduckgo.com",
    "www.duckduckgo.com",
    "docs.google.com",
}


def _require_human_operator_user_id(*, operator_user_id: str, decision_name: str) -> str:
    cleaned = operator_user_id.strip()
    if not cleaned:
        raise StrategyV2DecisionError(
            f"{decision_name} requires a non-empty operator_user_id."
        )
    lowered = cleaned.lower()
    if lowered in _BLOCKED_OPERATOR_USER_IDS or any(lowered.startswith(prefix) for prefix in _BLOCKED_OPERATOR_PREFIXES):
        raise StrategyV2DecisionError(
            f"{decision_name} requires an explicit human operator_user_id; received '{cleaned}'. "
            "Remediation: submit decision signal with a real operator identity."
        )
    return cleaned


def _current_hitl_policy_mode() -> str:
    mode = str(os.getenv(_HITL_POLICY_MODE_ENV, _HITL_POLICY_PRODUCTION_STRICT) or "").strip().lower()
    if mode not in {_HITL_POLICY_PRODUCTION_STRICT, _HITL_POLICY_INTERNAL_VALIDATION}:
        raise StrategyV2DecisionError(
            f"Unsupported HITL policy mode '{mode}' from {_HITL_POLICY_MODE_ENV}. "
            f"Expected '{_HITL_POLICY_PRODUCTION_STRICT}' or '{_HITL_POLICY_INTERNAL_VALIDATION}'."
        )
    return mode


def _enforce_decision_integrity_policy(
    *,
    decision_name: str,
    decision_mode: str,
    operator_note: str | None,
    attestation_reviewed_evidence: bool,
    attestation_understands_impact: bool,
    reviewed_candidate_ids: list[str] | None,
    require_reviewed_candidates: bool,
    selected_candidate_id: str | None = None,
) -> list[str]:
    policy_mode = _current_hitl_policy_mode()
    normalized_mode = str(decision_mode or "").strip().lower()
    if normalized_mode not in {"manual", "internal_automation"}:
        raise StrategyV2DecisionError(
            f"{decision_name} has unsupported decision_mode '{decision_mode}'. "
            "Remediation: use decision_mode='manual' (or 'internal_automation' only in internal_validation mode)."
        )
    if policy_mode == _HITL_POLICY_PRODUCTION_STRICT and normalized_mode != "manual":
        raise StrategyV2DecisionError(
            f"{decision_name} rejects decision_mode='{normalized_mode}' in production_strict mode. "
            "Remediation: submit an explicit manual decision."
        )

    if policy_mode == _HITL_POLICY_PRODUCTION_STRICT:
        if not attestation_reviewed_evidence or not attestation_understands_impact:
            raise StrategyV2DecisionError(
                f"{decision_name} requires attestation.reviewed_evidence=true and "
                "attestation.understands_impact=true in production_strict mode."
            )
        note = str(operator_note or "").strip()
        if len(note) < _MIN_HITL_OPERATOR_NOTE_LEN:
            raise StrategyV2DecisionError(
                f"{decision_name} operator_note is too short for audit quality "
                f"(len={len(note)}, required>={_MIN_HITL_OPERATOR_NOTE_LEN}). "
                "Remediation: provide concrete rationale referencing reviewed evidence."
            )
        if _AUTO_SELECTION_NOTE_PATTERN.search(note):
            raise StrategyV2DecisionError(
                f"{decision_name} operator_note includes automation markers, which are not allowed in production_strict mode."
            )

    cleaned_reviewed_candidates = [
        candidate_id.strip()
        for candidate_id in (reviewed_candidate_ids or [])
        if isinstance(candidate_id, str) and candidate_id.strip()
    ]
    if require_reviewed_candidates and not cleaned_reviewed_candidates:
        raise StrategyV2DecisionError(
            f"{decision_name} requires reviewed_candidate_ids for audit completeness."
        )
    if selected_candidate_id and cleaned_reviewed_candidates:
        if selected_candidate_id not in set(cleaned_reviewed_candidates):
            raise StrategyV2DecisionError(
                f"{decision_name} selected candidate '{selected_candidate_id}' is not present in reviewed_candidate_ids."
            )
    return cleaned_reviewed_candidates


def _require_stage1_quality(stage1: ProductBriefStage1) -> None:
    if stage1.competitor_count_validated is None or stage1.competitor_count_validated < _MIN_STAGE1_COMPETITORS:
        raise StrategyV2MissingContextError(
            f"Stage 1 requires at least {_MIN_STAGE1_COMPETITORS} validated competitors. "
            "Remediation: rerun foundational step 01 and include explicit validated competitor count."
        )
    if len(stage1.primary_icps) < _MIN_STAGE1_PRIMARY_ICPS:
        raise StrategyV2MissingContextError(
            f"Stage 1 requires at least {_MIN_STAGE1_PRIMARY_ICPS} primary ICP segments. "
            "Remediation: rerun foundational step 06 and include 3+ explicit ICP lines."
        )
    if not stage1.bottleneck.strip():
        raise StrategyV2MissingContextError(
            "Stage 1 bottleneck is empty. Remediation: include a non-empty bottleneck line in step 06."
        )
    segment = stage1.primary_segment
    if not segment.name.strip() or not segment.size_estimate.strip() or not segment.key_differentiator.strip():
        raise StrategyV2MissingContextError(
            "Stage 1 primary_segment is incomplete. "
            "Remediation: populate name, size_estimate, and key_differentiator in step 06 synthesis."
        )
    if not stage1.price.strip():
        raise StrategyV2MissingContextError(
            "Stage 1 price is empty. Remediation: provide explicit price or 'TBD' in Stage 0."
        )


def _require_stage1_product_category_keywords(stage1: ProductBriefStage1) -> list[str]:
    keywords = [
        str(item).strip()
        for item in stage1.product_category_keywords
        if isinstance(item, str) and str(item).strip()
    ]
    deduped: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        normalized = keyword.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(keyword)
    if len(deduped) < 3:
        raise StrategyV2MissingContextError(
            "Agent 0b requires product_category_keywords with at least 3 entries. "
            "Remediation: ensure Stage 1 includes explicit category keywords from foundational step 01."
        )
    return deduped


def _normalize_avatar_brief_text(step6_content: str) -> str:
    normalized = step6_content.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.translate(
        str.maketrans(
            {
                "–": "-",
                "—": "-",
                "−": "-",
                "•": "-",
                "\u00A0": " ",
            }
        )
    )
    # Step-06 output often contains markdown emphasis around field labels.
    normalized = normalized.replace("**", "").replace("__", "")
    return normalized


def _extract_avatar_field(*, step6_content: str, patterns: tuple[str, ...]) -> str | None:
    search_texts = [step6_content, _normalize_avatar_brief_text(step6_content)]
    seen: set[str] = set()
    for search_text in search_texts:
        if search_text in seen:
            continue
        seen.add(search_text)
        for pattern in patterns:
            match = re.search(pattern, search_text)
            if not match:
                continue
            value = str(match.group(1) or "").strip().strip("-").strip()
            if value:
                return value
    return None


def _extract_avatar_list_field(*, step6_content: str, patterns: tuple[str, ...]) -> list[str]:
    value = _extract_avatar_field(step6_content=step6_content, patterns=patterns)
    if not value:
        return []
    return [item.strip() for item in re.split(r"[;,|/]", value) if item.strip()]


def _extract_platform_habits(*, step6_content: str) -> list[str]:
    explicit = _extract_avatar_list_field(
        step6_content=step6_content,
        patterns=(
            r"(?im)^\s*(?:[-*]\s*)?platform(?:\s+habits|\s+usage|\s+behavior)?\s*[:=]\s*(.+)$",
            r"(?im)^\s*(?:[-*]\s*)?platforms?\s*[:=]\s*(.+)$",
        ),
    )
    if explicit:
        return explicit
    inferred: list[str] = []
    for line in step6_content.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if any(token in lowered for token in _AVATAR_PLATFORM_TOKENS):
            inferred.append(cleaned)
    return inferred


def _extract_content_patterns(*, step6_content: str) -> list[str]:
    explicit = _extract_avatar_list_field(
        step6_content=step6_content,
        patterns=(
            r"(?im)^\s*(?:[-*]\s*)?content(?:\s+consumption)?\s+patterns?\s*[:=]\s*(.+)$",
            r"(?im)^\s*(?:[-*]\s*)?content\s+format(?:\s+preference)?\s*[:=]\s*(.+)$",
        ),
    )
    if explicit:
        return explicit
    inferred: list[str] = []
    for line in step6_content.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if any(token in lowered for token in ("content", "format", "watch", "read", "consum", "short-form")):
            inferred.append(cleaned)
    return inferred


def _build_avatar_brief_runtime_payload(*, step6_content: str, step6_summary: str) -> dict[str, Any]:
    normalized_step6_content = _normalize_avatar_brief_text(step6_content)
    age_range = _extract_avatar_field(
        step6_content=normalized_step6_content,
        patterns=(
            r"(?im)^\s*(?:[-*]\s*)?age(?:\s+range)?\s*[:=]\s*(.+)$",
            r"(?im)^\s*(?:[-*]\s*)?demographics?.*age[^:]*[:=]\s*(.+)$",
        ),
    )
    if not age_range:
        heuristic_age_match = re.search(
            r"(?im)\bage\b[^\n]{0,40}?((?:\d{2}\s*[-]\s*\d{2})(?:[^\n]{0,120})?)",
            normalized_step6_content,
        )
        if heuristic_age_match:
            age_range = str(heuristic_age_match.group(1) or "").strip()
    gender_skew = _extract_avatar_field(
        step6_content=normalized_step6_content,
        patterns=(
            r"(?im)^\s*(?:[-*]\s*)?gender(?:\s+distribution|\s+skew)?\s*[:=]\s*(.+)$",
            r"(?im)^\s*(?:[-*]\s*)?demographics?.*gender[^:]*[:=]\s*(.+)$",
        ),
    )
    if not gender_skew:
        for raw_line in normalized_step6_content.splitlines():
            line = raw_line.strip().lstrip("-* ").strip()
            if not line:
                continue
            lowered = line.lower()
            if "gender" in lowered:
                if ":" in line:
                    candidate = line.split(":", 1)[1].strip()
                else:
                    candidate = line
                if candidate:
                    gender_skew = candidate
                    break
    platform_habits = _extract_platform_habits(step6_content=normalized_step6_content)
    content_patterns = _extract_content_patterns(step6_content=normalized_step6_content)

    missing: list[str] = []
    if not age_range:
        missing.append("age_range")
    if not gender_skew:
        missing.append("gender_skew")
    if not platform_habits:
        missing.append("platform_habits")
    if not content_patterns:
        missing.append("content_consumption_patterns")
    if missing:
        raise StrategyV2MissingContextError(
            "Agent 0b requires structured AVATAR_BRIEF fields that are missing from foundational step 06: "
            f"{missing}. Remediation: regenerate step 06 with explicit demographics, platform habits, and content patterns."
        )

    return {
        "demographics": {
            "age_range": age_range,
            "gender_skew": gender_skew,
        },
        "platform_habits": platform_habits[:8],
        "content_consumption_patterns": content_patterns[:8],
        "psychographics_summary": step6_summary.strip()[:1200],
    }


def _extract_block_markers_from_payload(payload: Any) -> list[str]:
    findings: list[str] = []
    stack: list[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if isinstance(value, (dict, list)):
                    stack.append(value)
                elif isinstance(value, str):
                    upper_value = value.strip().upper()
                    if key in _PROMPT_BLOCK_SIGNAL_KEYS:
                        for token in _BLOCKED_PROMPT_OUTPUT_TOKENS:
                            if token in upper_value:
                                findings.append(f"{key}={token}")
                    if key in {"missing_required_inputs", "required_inputs_missing"} and value.strip():
                        findings.append(f"{key}=present")
                elif key in {"missing_required_inputs", "required_inputs_missing"} and isinstance(value, list) and value:
                    findings.append(f"{key}=present")
        elif isinstance(current, list):
            stack.extend(current)
    return sorted(set(findings))


def _raise_if_blocked_prompt_output(
    *,
    stage_label: str,
    parsed_output: Mapping[str, Any],
    raw_output: str,
    remediation: str,
) -> None:
    findings = _extract_block_markers_from_payload(parsed_output)
    if findings:
        raise StrategyV2DecisionError(
            f"{stage_label} returned blocked/cannot-proceed output ({'; '.join(sorted(set(findings)))}). "
            f"Remediation: {remediation}"
        )


def _build_scraped_data_manifest(
    *,
    apify_context: Mapping[str, Any],
    competitor_analysis: Mapping[str, Any],
) -> dict[str, Any]:
    raw_runs = apify_context.get("raw_runs")
    run_rows = [row for row in raw_runs if isinstance(row, dict)] if isinstance(raw_runs, list) else []
    candidate_assets = (
        [row for row in apify_context.get("candidate_assets", []) if isinstance(row, dict)]
        if isinstance(apify_context.get("candidate_assets"), list)
        else []
    )
    social_video_observations = (
        [row for row in apify_context.get("social_video_observations", []) if isinstance(row, dict)]
        if isinstance(apify_context.get("social_video_observations"), list)
        else []
    )
    external_voc_corpus = (
        [row for row in apify_context.get("external_voc_corpus", []) if isinstance(row, dict)]
        if isinstance(apify_context.get("external_voc_corpus"), list)
        else []
    )
    competitor_sheets = (
        [row for row in competitor_analysis.get("asset_observation_sheets", []) if isinstance(row, dict)]
        if isinstance(competitor_analysis.get("asset_observation_sheets"), list)
        else []
    )
    summarized_runs: list[dict[str, Any]] = []
    for row in run_rows:
        input_payload = row.get("input_payload")
        requested_refs: list[str] = []
        if isinstance(input_payload, dict):
            for key in ("startUrls", "urls", "directUrls", "profiles", "postURLs"):
                raw_value = input_payload.get(key)
                if not isinstance(raw_value, list):
                    continue
                for item in raw_value:
                    if isinstance(item, str) and item.strip():
                        requested_refs.append(item.strip())
                    elif isinstance(item, dict):
                        url_value = item.get("url")
                        if isinstance(url_value, str) and url_value.strip():
                            requested_refs.append(url_value.strip())
        summarized_runs.append(
            {
                "actor_id": str(row.get("actor_id") or ""),
                "run_id": str(row.get("run_id") or ""),
                "dataset_id": str(row.get("dataset_id") or ""),
                "status": str(row.get("status") or ""),
                "item_count": len(row.get("items")) if isinstance(row.get("items"), list) else 0,
                "requested_refs": requested_refs[:20],
            }
        )
    manifest = {
        "run_count": len(summarized_runs),
        "runs": summarized_runs,
        "candidate_asset_count": len(candidate_assets),
        "social_video_observation_count": len(social_video_observations),
        "external_voc_row_count": len(external_voc_corpus),
        "competitor_asset_sheet_count": len(competitor_sheets),
        "candidate_asset_refs": [
            str(row.get("source_ref"))
            for row in candidate_assets[:30]
            if isinstance(row.get("source_ref"), str) and str(row.get("source_ref")).strip()
        ],
    }
    if (
        manifest["run_count"] == 0
        and manifest["candidate_asset_count"] == 0
        and manifest["social_video_observation_count"] == 0
        and manifest["external_voc_row_count"] == 0
        and manifest["competitor_asset_sheet_count"] == 0
    ):
        raise StrategyV2MissingContextError(
            "Agent 1 requires scraped-data context manifest, but no Apify/competitor dataset metadata was available. "
            "Remediation: run asset ingestion and pass apify_context with candidate/social/VOC rows."
        )
    return manifest


def _require_voc_transition_quality(
    *,
    voc_observations: list[dict[str, Any]],
    voc_scored: Mapping[str, Any],
) -> None:
    scored_items_raw = voc_scored.get("items")
    if not isinstance(scored_items_raw, list) or not scored_items_raw:
        raise StrategyV2DecisionError(
            "v2-05 VOC scoring returned no scored items. "
            "Remediation: ensure Agent 2 emits complete VOC observation sheets."
        )
    scored_items = [row for row in scored_items_raw if isinstance(row, dict)]
    if len(scored_items) < _VOC_MIN_OBSERVATIONS_GATE:
        raise StrategyV2DecisionError(
            f"v2-05 VOC quality gate failed: observations={len(scored_items)} "
            f"(required>={_VOC_MIN_OBSERVATIONS_GATE}). Remediation: increase qualified VOC extraction volume."
        )

    non_zero_scores = sum(1 for row in scored_items if float(row.get("adjusted_score") or 0.0) > 0.0)
    zero_evidence_rows = sum(1 for row in scored_items if bool(row.get("zero_evidence_gate")))
    non_zero_ratio = non_zero_scores / len(scored_items)
    zero_evidence_ratio = zero_evidence_rows / len(scored_items)

    source_buckets = {
        str(row.get("source") or "").strip().lower()
        for row in voc_observations
        if isinstance(row.get("source"), str) and str(row.get("source")).strip()
    }
    if len(source_buckets) < _VOC_MIN_SOURCE_BUCKETS:
        raise StrategyV2DecisionError(
            "v2-05 VOC quality gate failed: source diversity too low "
            f"(unique_sources={len(source_buckets)}, required>={_VOC_MIN_SOURCE_BUCKETS}). "
            "Remediation: include VOC from additional habitat/source buckets."
        )
    if non_zero_ratio < _VOC_MIN_NON_ZERO_SCORE_RATIO:
        raise StrategyV2DecisionError(
            "v2-05 VOC quality gate failed: non-zero score ratio too low "
            f"(ratio={non_zero_ratio:.2f}, required>={_VOC_MIN_NON_ZERO_SCORE_RATIO:.2f}). "
            "Remediation: fix Agent 2 observation completeness before scoring."
        )
    if zero_evidence_ratio > _VOC_MAX_ZERO_EVIDENCE_RATIO:
        raise StrategyV2DecisionError(
            "v2-05 VOC quality gate failed: zero-evidence incidence too high "
            f"(ratio={zero_evidence_ratio:.2f}, max={_VOC_MAX_ZERO_EVIDENCE_RATIO:.2f}). "
            "Remediation: rerun Agent 2 with full observation-sheet fields and richer source rows."
        )


def _require_angle_transition_quality(
    *,
    scored_angles_payload: Mapping[str, Any],
) -> None:
    summary = scored_angles_payload.get("summary")
    if not isinstance(summary, dict):
        raise StrategyV2DecisionError(
            "v2-06 angle scoring missing summary payload. "
            "Remediation: verify score_angles output contract."
        )
    std_score = float(summary.get("std_score") or 0.0)
    if std_score < _ANGLE_MIN_STD_SCORE:
        raise StrategyV2DecisionError(
            "v2-06 angle quality gate failed: score distribution is flat "
            f"(std_score={std_score:.2f}, required>={_ANGLE_MIN_STD_SCORE:.2f}). "
            "Remediation: improve upstream VOC evidence quality before angle synthesis."
        )

    scored_rows_raw = scored_angles_payload.get("angles")
    if not isinstance(scored_rows_raw, list) or not scored_rows_raw:
        raise StrategyV2DecisionError(
            "v2-06 angle scoring returned no angle rows. "
            "Remediation: ensure Agent 3 returned valid angle observations."
        )
    scored_rows = [row for row in scored_rows_raw if isinstance(row, dict)]
    non_floor_count = sum(1 for row in scored_rows if not bool(row.get("evidence_floor_gate")))
    if non_floor_count < _ANGLE_MIN_NON_FLOOR_CANDIDATES:
        raise StrategyV2DecisionError(
            "v2-06 angle quality gate failed: too few candidates cleared evidence floor "
            f"(non_floor={non_floor_count}, required>={_ANGLE_MIN_NON_FLOOR_CANDIDATES}). "
            "Remediation: increase supporting VOC evidence per candidate."
        )

    top_ranked = sorted(scored_rows, key=lambda row: float(row.get("final_score") or 0.0), reverse=True)[:3]
    if not top_ranked:
        raise StrategyV2DecisionError("v2-06 angle quality gate failed: missing top-ranked candidates.")
    for row in top_ranked:
        components = row.get("components")
        demand_signal = (
            float(components.get("demand_signal") or 0.0)
            if isinstance(components, dict)
            else 0.0
        )
        if demand_signal < _ANGLE_MIN_TOP_DEMAND_SIGNAL:
            raise StrategyV2DecisionError(
                "v2-06 angle quality gate failed: top candidate demand_signal too low "
                f"(angle_id={row.get('angle_id')}, demand_signal={demand_signal:.2f}, "
                f"required>={_ANGLE_MIN_TOP_DEMAND_SIGNAL:.2f}). "
                "Remediation: improve VOC extraction and angle evidence mapping."
            )


def _require_selected_angle_evidence_quality(*, selected_angle: SelectedAngleContract) -> None:
    evidence = selected_angle.evidence
    if evidence.supporting_voc_count < _MIN_SELECTED_ANGLE_SUPPORTING_VOC:
        raise StrategyV2DecisionError(
            f"Selected angle '{selected_angle.angle_id}' does not meet evidence density gate: "
            f"supporting_voc_count={evidence.supporting_voc_count}, "
            f"required>={_MIN_SELECTED_ANGLE_SUPPORTING_VOC}."
        )
    quote_count = len(evidence.top_quotes)
    if quote_count < _MIN_SELECTED_ANGLE_TOP_QUOTES:
        raise StrategyV2DecisionError(
            f"Selected angle '{selected_angle.angle_id}' does not meet quote depth gate: "
            f"top_quotes={quote_count}, required>={_MIN_SELECTED_ANGLE_TOP_QUOTES}."
        )
    for quote in evidence.top_quotes:
        cleaned_quote = quote.quote.strip()
        if len(cleaned_quote) < 12:
            raise StrategyV2DecisionError(
                f"Selected angle '{selected_angle.angle_id}' contains an underspecified evidence quote "
                f"(voc_id={quote.voc_id}). Remediation: provide full quote text from VOC source."
            )


def _require_selected_angle_score_quality(*, ranked_candidate_row: Mapping[str, Any]) -> None:
    if bool(ranked_candidate_row.get("evidence_floor_gate")):
        raise StrategyV2DecisionError(
            "Selected angle failed quality gate because evidence_floor_gate=true. "
            "Remediation: select a candidate that cleared the evidence floor."
        )
    score = float(ranked_candidate_row.get("score") or 0.0)
    if score <= 20.0:
        raise StrategyV2DecisionError(
            "Selected angle failed quality gate because its score is at or below evidence floor "
            f"(score={score:.1f}). Remediation: select a higher-evidence angle candidate."
        )

    components = ranked_candidate_row.get("components")
    if not isinstance(components, dict):
        raise StrategyV2DecisionError(
            "Selected angle is missing scored components required for quality validation. "
            "Remediation: rerun v2-06 to produce full score components."
        )

    demand_signal = float(components.get("demand_signal") or 0.0)
    evidence_quality = float(components.get("evidence_quality") or 0.0)
    if demand_signal < _ANGLE_SELECTION_MIN_DEMAND_SIGNAL:
        raise StrategyV2DecisionError(
            "Selected angle failed demand-signal gate "
            f"(demand_signal={demand_signal:.1f}, required>={_ANGLE_SELECTION_MIN_DEMAND_SIGNAL:.1f}). "
            "Remediation: choose an angle with stronger validated demand."
        )
    if evidence_quality < _ANGLE_SELECTION_MIN_EVIDENCE_QUALITY:
        raise StrategyV2DecisionError(
            "Selected angle failed evidence-quality gate "
            f"(evidence_quality={evidence_quality:.1f}, required>={_ANGLE_SELECTION_MIN_EVIDENCE_QUALITY:.1f}). "
            "Remediation: choose an angle with stronger evidence quality."
        )


def _extract_congruency_test_outcome(
    *,
    congruency: Mapping[str, Any],
    dimension: str,
    test_id: str,
) -> tuple[bool, str]:
    result = _require_dict(payload=congruency.get("result"), field_name="congruency.result")
    tests = result.get(dimension)
    if not isinstance(tests, list):
        raise StrategyV2SchemaValidationError(f"congruency.result.{dimension} must be a list.")
    for row in tests:
        if not isinstance(row, (list, tuple)) or len(row) != 4:
            continue
        if str(row[0]) != test_id:
            continue
        outcome = row[3]
        if not isinstance(outcome, (list, tuple)) or len(outcome) < 2:
            raise StrategyV2SchemaValidationError(
                f"congruency.result.{dimension}.{test_id} outcome format is invalid."
            )
        return bool(outcome[0]), str(outcome[1])
    raise StrategyV2SchemaValidationError(
        f"Missing congruency test '{test_id}' in dimension '{dimension}'."
    )


def _require_congruency_quality(*, congruency: Mapping[str, Any], page_name: str) -> None:
    composite = _require_dict(payload=congruency.get("composite"), field_name=f"{page_name}.congruency.composite")
    if not bool(composite.get("passed", False)):
        raise StrategyV2DecisionError(
            f"{page_name} congruency failed threshold/hard-gate composite checks."
        )

    for dimension, test_id in (("bh", "BH1"), ("bh", "BH3"), ("pc", "PC2")):
        passed, detail = _extract_congruency_test_outcome(
            congruency=congruency,
            dimension=dimension,
            test_id=test_id,
        )
        if "N/A" in detail:
            raise StrategyV2DecisionError(
                f"{page_name} congruency test {test_id} is non-applicable ('{detail}'). "
                "Remediation: include required structure/CTA/content so hard gates are truly evaluated."
            )
        if not passed:
            raise StrategyV2DecisionError(
                f"{page_name} congruency test {test_id} failed: {detail}"
            )


def _repo_root_with_v2_fixes() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "V2 Fixes"
        if candidate.exists() and candidate.is_dir():
            return parent
    raise StrategyV2MissingContextError(
        "Unable to locate 'V2 Fixes' directory from backend runtime path. "
        "Remediation: run backend from repository root with V2 Fixes assets present."
    )


def _resolve_single_v2_file(*, pattern: str, context: str) -> Path:
    root = _repo_root_with_v2_fixes()
    matches = sorted((root / "V2 Fixes").glob(pattern))
    if len(matches) != 1:
        raise StrategyV2MissingContextError(
            f"Expected exactly one file for {context} pattern '{pattern}', found {len(matches)}. "
            "Remediation: verify V2 Fixes prompt assets are present and unique."
        )
    return matches[0]


def _read_v2_prompt(*, pattern: str, context: str) -> str:
    prompt_path = _resolve_single_v2_file(pattern=pattern, context=context)
    prompt_text = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt_text:
        raise StrategyV2MissingContextError(
            f"Resolved {context} prompt is empty: {prompt_path}. "
            "Remediation: restore prompt contents in V2 Fixes."
        )
    return prompt_text


def _render_prompt_template(*, template: str, variables: Mapping[str, str], context: str) -> str:
    placeholders = set(_PLACEHOLDER_PATTERN.findall(template))
    missing = sorted(name for name in placeholders if name not in variables)
    if missing:
        raise StrategyV2MissingContextError(
            f"Missing placeholders for {context} prompt: {missing}. "
            "Remediation: provide all required Strategy V2 foundational variables."
        )

    def _replace(match: re.Match[str]) -> str:
        return str(variables.get(match.group(1), ""))

    return _PLACEHOLDER_PATTERN.sub(_replace, template)


def _append_tagged_output_guardrails(*, prompt_text: str, include_step4_prompt: bool = False) -> str:
    tagged = (
        prompt_text.rstrip()
        + "\n\nReturn ONLY tagged blocks in this exact structure:\n"
        + "<SUMMARY>Bounded summary.</SUMMARY>\n"
        + "<CONTENT>Full output.</CONTENT>\n"
    )
    if include_step4_prompt:
        tagged += "<STEP4_PROMPT>Executable deep research prompt for step 04.</STEP4_PROMPT>\n"
    return tagged


def _llm_generate_text(
    *,
    prompt: str,
    model: str,
    use_reasoning: bool = False,
    use_web_search: bool = False,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
    claude_messages: list[dict[str, Any]] | None = None,
    heartbeat_context: dict[str, Any] | None = None,
    progress_sink: dict[str, Any] | None = None,
) -> str:
    progress_callback: Callable[[dict[str, Any]], None] | None = None
    if heartbeat_context is not None or progress_sink is not None:
        context_payload = dict(heartbeat_context or {})

        def _progress_callback(progress: dict[str, Any]) -> None:
            if progress_sink is not None:
                progress_sink.clear()
                progress_sink.update(progress)
            if heartbeat_context is not None:
                payload = dict(context_payload)
                payload.update(progress)
                activity.heartbeat(payload)

        progress_callback = _progress_callback

    llm = LLMClient(default_model=model)
    if model.lower().startswith("claude") and response_format is not None:
        json_schema_config = response_format.get("json_schema") if isinstance(response_format, dict) else None
        schema = json_schema_config.get("schema") if isinstance(json_schema_config, dict) else None
        if not isinstance(schema, dict):
            raise StrategyV2SchemaValidationError(
                "Claude structured-output call requires a JSON schema object under "
                "response_format['json_schema']['schema']."
            )

        if progress_callback is not None:
            progress_callback({"status": "submitted", "llm_phase": "structured_json"})

        structured_kwargs: dict[str, Any] = {
            "model": model,
            "system": None,
            "output_schema": schema,
            "max_tokens": max_tokens or 4096,
            "temperature": 0.0,
        }
        if claude_messages is not None:
            if not isinstance(claude_messages, list) or not claude_messages:
                raise StrategyV2SchemaValidationError(
                    "Claude structured-output call requires a non-empty claude_messages list when provided."
                )
            structured_kwargs["messages"] = claude_messages
        else:
            structured_kwargs["user_content"] = [{"type": "text", "text": prompt}]

        structured_response = call_claude_structured_message(**structured_kwargs)
        parsed = structured_response.get("parsed")
        if parsed is None:
            raise StrategyV2SchemaValidationError(
                f"Claude structured-output call returned empty parsed payload for model '{model}'."
            )
        request_id = str(structured_response.get("request_id") or "").strip()
        stop_reason = str(structured_response.get("stop_reason") or "").strip()
        usage = structured_response.get("usage")
        output = json.dumps(parsed, ensure_ascii=False)
        if progress_callback is not None:
            progress_payload: dict[str, Any] = {
                "status": "completed",
                "llm_phase": "structured_json",
                "output_chars": len(output),
            }
            if request_id:
                progress_payload["request_id"] = request_id
            if stop_reason:
                progress_payload["stop_reason"] = stop_reason
            if isinstance(usage, dict):
                input_tokens = usage.get("input")
                output_tokens = usage.get("output")
                if isinstance(input_tokens, int) and input_tokens > 0:
                    progress_payload["input_tokens"] = input_tokens
                if isinstance(output_tokens, int) and output_tokens > 0:
                    progress_payload["output_tokens"] = output_tokens
                if isinstance(input_tokens, int) and isinstance(output_tokens, int):
                    progress_payload["total_tokens"] = input_tokens + output_tokens
            progress_callback(progress_payload)
        cleaned = output.strip()
        if not cleaned:
            raise StrategyV2MissingContextError(
                f"LLM returned empty output for model '{model}'. "
                "Remediation: rerun the step after verifying model access and prompt input size."
            )
        return cleaned

    params = LLMGenerationParams(
        model=model,
        max_tokens=max_tokens,
        use_reasoning=use_reasoning,
        use_web_search=use_web_search,
        response_format=response_format,
        progress_callback=progress_callback,
    )
    output = llm.generate_text(prompt, params)
    cleaned = output.strip()
    if not cleaned:
        raise StrategyV2MissingContextError(
            f"LLM returned empty output for model '{model}'. "
            "Remediation: rerun the step after verifying model access and prompt input size."
        )
    return cleaned


def _parse_json_response(*, raw_text: str, field_name: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = _extract_first_json_object(raw_text)
    if not isinstance(parsed, dict):
        raise StrategyV2SchemaValidationError(
            f"Expected JSON object for '{field_name}', received '{type(parsed).__name__}'."
        )
    return parsed


def _enforce_strict_openai_json_schema(node: Any) -> Any:
    if isinstance(node, list):
        return [_enforce_strict_openai_json_schema(item) for item in node]
    if not isinstance(node, dict):
        return node

    normalized: dict[str, Any] = {
        key: _enforce_strict_openai_json_schema(value) for key, value in node.items()
    }
    if normalized.get("type") == "object":
        raw_properties = normalized.get("properties")
        properties = raw_properties if isinstance(raw_properties, dict) else {}
        normalized["properties"] = properties
        normalized["additionalProperties"] = False
        normalized["required"] = [key for key in properties.keys()]

    for combiner_key in ("anyOf", "oneOf", "allOf"):
        combiner = normalized.get(combiner_key)
        if isinstance(combiner, list):
            normalized[combiner_key] = [_enforce_strict_openai_json_schema(item) for item in combiner]
    if isinstance(normalized.get("not"), dict):
        normalized["not"] = _enforce_strict_openai_json_schema(normalized["not"])
    if isinstance(normalized.get("items"), dict):
        normalized["items"] = _enforce_strict_openai_json_schema(normalized["items"])

    return normalized


def _json_schema_response_format(*, name: str, schema: dict[str, Any]) -> dict[str, Any]:
    strict_schema = _enforce_strict_openai_json_schema(deepcopy(schema))
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": strict_schema,
        },
    }


def _render_prompt_asset(
    *,
    asset: PromptAsset,
    context: str,
    variables: Mapping[str, str] | None,
) -> str:
    if variables is None:
        variables = {}
    return render_prompt_template_strict(template=asset.text, variables=variables, context=context)


def _run_prompt_json_object(
    *,
    asset: PromptAsset,
    context: str,
    model: str,
    runtime_instruction: str,
    schema_name: str,
    schema: dict[str, Any],
    variables: Mapping[str, str] | None = None,
    use_reasoning: bool = True,
    use_web_search: bool = False,
    max_tokens: int | None = None,
    conversation_messages: list[dict[str, Any]] | None = None,
    log_metadata: Mapping[str, Any] | None = None,
    heartbeat_context: dict[str, Any] | None = None,
    llm_call_log: list[dict[str, Any]] | None = None,
    llm_call_label: str | None = None,
) -> tuple[dict[str, Any], str, dict[str, str]]:
    rendered = _render_prompt_asset(asset=asset, context=context, variables=variables)
    prompt = (
        rendered.rstrip()
        + "\n\n"
        + runtime_instruction.strip()
        + "\n\nReturn ONLY valid JSON matching the required schema."
    )
    claude_messages: list[dict[str, Any]] | None = None
    claude_user_turn: dict[str, Any] | None = None
    if conversation_messages is not None:
        if not model.lower().startswith("claude"):
            raise StrategyV2SchemaValidationError(
                "conversation_messages are only supported for Claude structured-output prompts."
            )
        claude_user_turn = {
            "role": "user",
            "content": [{"type": "text", "text": prompt}],
        }
        claude_messages = list(conversation_messages)
        claude_messages.append(claude_user_turn)
    llm_progress: dict[str, Any] = {}
    started_monotonic = time.monotonic()
    raw_output = _llm_generate_text(
        prompt=prompt,
        model=model,
        use_reasoning=use_reasoning,
        use_web_search=use_web_search,
        max_tokens=max_tokens,
        response_format=_json_schema_response_format(name=schema_name, schema=schema),
        claude_messages=claude_messages,
        heartbeat_context=heartbeat_context,
        progress_sink=llm_progress,
    )
    if conversation_messages is not None and claude_user_turn is not None:
        conversation_messages.append(claude_user_turn)
        conversation_messages.append(
            {
                "role": "assistant",
                "content": [{"type": "text", "text": raw_output}],
            }
        )
    elapsed_seconds = round(time.monotonic() - started_monotonic, 3)
    if llm_call_log is not None:
        log_row: dict[str, Any] = {
            "label": llm_call_label or context,
            "context": context,
            "model": model,
            "elapsed_seconds": elapsed_seconds,
            "output_chars": len(raw_output),
        }
        if log_metadata:
            for key, value in log_metadata.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    log_row[str(key)] = value
        if claude_messages is not None:
            log_row["conversation_message_count"] = len(claude_messages)
        if llm_progress:
            for key in (
                "response_id",
                "request_id",
                "status",
                "elapsed_seconds",
                "stop_reason",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "reasoning_tokens",
                "cached_input_tokens",
            ):
                value = llm_progress.get(key)
                if value is not None:
                    log_row[key] = value
        llm_call_log.append(log_row)
    parsed = extract_required_json_object(raw_text=raw_output, field_name=context)
    provenance = build_prompt_provenance(
        asset=asset,
        model_name=model,
        input_contract_version="2.0.0",
        output_contract_version="2.0.0",
    ).to_dict()
    return parsed, raw_output, provenance


def _run_prompt_json_array(
    *,
    asset: PromptAsset,
    context: str,
    model: str,
    runtime_instruction: str,
    schema_name: str,
    schema: dict[str, Any],
    variables: Mapping[str, str] | None = None,
    use_reasoning: bool = True,
    use_web_search: bool = False,
    max_tokens: int | None = None,
    conversation_messages: list[dict[str, Any]] | None = None,
    log_metadata: Mapping[str, Any] | None = None,
    heartbeat_context: dict[str, Any] | None = None,
    llm_call_log: list[dict[str, Any]] | None = None,
    llm_call_label: str | None = None,
) -> tuple[list[Any], str, dict[str, str]]:
    rendered = _render_prompt_asset(asset=asset, context=context, variables=variables)
    prompt = (
        rendered.rstrip()
        + "\n\n"
        + runtime_instruction.strip()
        + "\n\nReturn ONLY valid JSON matching the required schema."
    )
    claude_messages: list[dict[str, Any]] | None = None
    if conversation_messages is not None:
        if not model.lower().startswith("claude"):
            raise StrategyV2SchemaValidationError(
                "conversation_messages are only supported for Claude structured-output prompts."
            )
        claude_messages = list(conversation_messages)
        claude_messages.append(
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }
        )
    llm_progress: dict[str, Any] = {}
    started_monotonic = time.monotonic()
    raw_output = _llm_generate_text(
        prompt=prompt,
        model=model,
        use_reasoning=use_reasoning,
        use_web_search=use_web_search,
        max_tokens=max_tokens,
        response_format=_json_schema_response_format(name=schema_name, schema=schema),
        claude_messages=claude_messages,
        heartbeat_context=heartbeat_context,
        progress_sink=llm_progress,
    )
    elapsed_seconds = round(time.monotonic() - started_monotonic, 3)
    if llm_call_log is not None:
        log_row: dict[str, Any] = {
            "label": llm_call_label or context,
            "context": context,
            "model": model,
            "elapsed_seconds": elapsed_seconds,
            "output_chars": len(raw_output),
        }
        if log_metadata:
            for key, value in log_metadata.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    log_row[str(key)] = value
        if claude_messages is not None:
            log_row["conversation_message_count"] = len(claude_messages)
        if llm_progress:
            for key in (
                "response_id",
                "request_id",
                "status",
                "elapsed_seconds",
                "stop_reason",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "reasoning_tokens",
                "cached_input_tokens",
            ):
                value = llm_progress.get(key)
                if value is not None:
                    log_row[key] = value
        llm_call_log.append(log_row)
    parsed = extract_required_json_array(raw_text=raw_output, field_name=context)
    provenance = build_prompt_provenance(
        asset=asset,
        model_name=model,
        input_contract_version="2.0.0",
        output_contract_version="2.0.0",
    ).to_dict()
    return parsed, raw_output, provenance


def _normalize_score_1_10(value: object, *, field_name: str) -> float:
    if not isinstance(value, (int, float)):
        raise StrategyV2SchemaValidationError(f"Expected numeric score for '{field_name}'.")
    score = float(value)
    if score < 0.0 or score > 10.0:
        raise StrategyV2SchemaValidationError(
            f"Score for '{field_name}' must be within 0-10 inclusive, received {score}."
        )
    return score


def _normalize_evidence_quality(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StrategyV2SchemaValidationError(f"Missing evidence_quality for '{field_name}'.")
    normalized = value.strip().upper()
    if normalized not in {"OBSERVED", "INFERRED", "ASSUMED"}:
        raise StrategyV2SchemaValidationError(
            f"Invalid evidence_quality '{value}' for '{field_name}'. Expected OBSERVED|INFERRED|ASSUMED."
        )
    return normalized


def _normalize_novelty_classification(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StrategyV2SchemaValidationError(f"Missing novelty classification for '{field_name}'.")
    normalized = value.strip().upper()
    if normalized in {"NOVEL", "INCREMENTAL", "REDUNDANT"}:
        return normalized

    if "NOVEL" in normalized:
        return "NOVEL"
    if "INCREMENTAL" in normalized:
        return "INCREMENTAL"
    if "REDUNDANT" in normalized:
        return "REDUNDANT"

    # Offer variant prompts occasionally emit richer wording like
    # "PACKAGING" / "REPACKAGED (...)" for non-net-new mechanics.
    if any(
        token in normalized
        for token in (
            "REPACK",
            "PACKAG",
            "POSITION",
            "CURAT",
            "REMIX",
            "TABLE STAKE",
            "TABLE_STAKE",
        )
    ):
        return "INCREMENTAL"
    if any(token in normalized for token in ("COPYCAT", "ME TOO", "SAME AS", "COMMODIT")):
        return "REDUNDANT"
    if any(
        token in normalized
        for token in (
            "DIFFERENTIAT",
            "DIFFERENTIATOR",
            "DISTINCT",
            "UNIQUE",
            "BREAKTHROUGH",
            "NEW MECHANISM",
            "NET NEW",
            "PROPRIETARY",
        )
    ):
        return "NOVEL"

    raise StrategyV2SchemaValidationError(
        f"Invalid novelty classification '{normalized}' for '{field_name}'. "
        "Expected NOVEL|INCREMENTAL|REDUNDANT or a recognized synonym."
    )


def _resolve_workflow_run(
    *,
    session,
    org_id: str,
    temporal_workflow_id: str,
    temporal_run_id: str,
) -> WorkflowRun:
    stmt = (
        select(WorkflowRun)
        .where(
            WorkflowRun.org_id == org_id,
            WorkflowRun.temporal_workflow_id == temporal_workflow_id,
            WorkflowRun.temporal_run_id == temporal_run_id,
        )
        .order_by(WorkflowRun.started_at.desc())
    )
    run = session.scalars(stmt).first()
    if not run:
        raise StrategyV2MissingContextError(
            "Workflow run was not found for Strategy V2 temporal ids. "
            "Remediation: ensure workflow run registration executes before stage activities."
        )
    return run


def _record_agent_run(
    *,
    session,
    org_id: str,
    user_id: str,
    client_id: str,
    objective_type: str,
    model: str,
    inputs_json: dict[str, Any],
    outputs_json: dict[str, Any],
) -> str:
    runs_repo = AgentRunsRepository(session)
    run = runs_repo.create_run(
        org_id=org_id,
        user_id=user_id,
        client_id=client_id,
        objective_type=objective_type,
        model=model,
        inputs_json=inputs_json,
    )
    runs_repo.finish_run(
        run_id=str(run.id),
        status=AgentRunStatusEnum.completed,
        outputs_json=outputs_json,
    )
    return str(run.id)


def _log_workflow_activity_safe(
    *,
    workflow_run_id: str,
    step: str,
    status: str,
    payload_in: dict[str, Any] | None = None,
    payload_out: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    try:
        with session_scope() as session:
            WorkflowsRepository(session).log_activity(
                workflow_run_id=workflow_run_id,
                step=step,
                status=status,
                payload_in=payload_in,
                payload_out=payload_out,
                error=error,
            )
    except Exception:
        activity.logger.exception(
            "strategy_v2.workflow_log_failed",
            extra={
                "workflow_run_id": workflow_run_id,
                "step": step,
                "status": status,
            },
        )


def _persist_step_payload(
    *,
    session,
    org_id: str,
    client_id: str,
    product_id: str,
    campaign_id: str | None,
    workflow_run_id: str,
    step_key: str,
    title: str,
    summary: str,
    payload: dict[str, Any],
    model_name: str,
    prompt_version: str,
    schema_version: str,
    agent_run_id: str | None,
) -> str:
    artifacts_repo = ArtifactsRepository(session)
    research_repo = ResearchArtifactsRepository(session)
    workflows_repo = WorkflowsRepository(session)

    envelope: dict[str, Any] = {
        "step_key": step_key,
        "title": title,
        "summary": summary,
        "payload": payload,
        "model": model_name,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "agent_run_id": agent_run_id,
        "created_at": _now_iso(),
    }
    artifact = artifacts_repo.insert(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        artifact_type=ArtifactTypeEnum.strategy_v2_step_payload,
        data=envelope,
    )
    artifact_id = str(artifact.id)
    research_repo.upsert(
        org_id=org_id,
        workflow_run_id=workflow_run_id,
        step_key=step_key,
        title=title,
        doc_id=artifact_id,
        doc_url=f"artifact://{artifact_id}",
        prompt_sha256=None,
        summary=summary,
    )
    workflows_repo.log_activity(
        workflow_run_id=workflow_run_id,
        step=step_key,
        status="completed",
        payload_out={
            "artifact_id": artifact_id,
            "model": model_name,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "agent_run_id": agent_run_id,
        },
    )
    activity.logger.info(
        "strategy_v2.step.persisted",
        extra={
            "workflow_id": workflow_run_id,
            "step_key": step_key,
            "agent_run_id": agent_run_id,
            "model": model_name,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "artifact_id": artifact_id,
        },
    )
    return artifact_id


def _extract_first_json_object(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if not text:
        raise StrategyV2MissingContextError(
            "Cannot parse JSON object from empty text. Remediation: verify upstream artifact content."
        )
    start_index: int | None = None
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if start_index is None:
            if char == "{":
                start_index = index
                depth = 1
            continue

        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                parsed = json.loads(text[start_index : index + 1])
                if isinstance(parsed, dict):
                    return parsed
                break
    raise StrategyV2MissingContextError(
        "Failed to parse required JSON object from text content. Remediation: inspect upstream step output."
    )


def _extract_step4_entries(step4_content: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    quote_buffer: list[str] = []
    collecting_quote = False

    field_prefixes = {
        "source": "SOURCE:",
        "category": "CATEGORY:",
        "emotion": "EMOTION:",
        "intensity": "INTENSITY:",
        "buyer_stage": "BUYER_STAGE:",
        "segment_hint": "SEGMENT_HINT:",
    }
    required_fields = tuple(field_prefixes.keys()) + ("quote",)

    def _reset_entry() -> None:
        nonlocal current, quote_buffer, collecting_quote
        current = {}
        quote_buffer = []
        collecting_quote = False

    def _finalize_entry() -> None:
        if all(isinstance(current.get(key), str) and current[key].strip() for key in required_fields):
            entries.append({key: current[key].strip() for key in required_fields})

    def _clean_line(raw_line: str) -> str:
        return raw_line.strip().lstrip("-* ").strip()

    _reset_entry()
    for raw_line in step4_content.splitlines():
        line = _clean_line(raw_line)
        if not line:
            if collecting_quote:
                quote_buffer.append("")
            continue

        upper_line = line.upper()
        if upper_line.startswith(field_prefixes["source"]):
            if current:
                _finalize_entry()
                _reset_entry()
            current["source"] = line.split(":", 1)[1].strip()
            continue

        if not current:
            continue

        matched_field = None
        for field_name, prefix in field_prefixes.items():
            if upper_line.startswith(prefix):
                current[field_name] = line.split(":", 1)[1].strip()
                matched_field = field_name
                break
        if matched_field is not None:
            continue

        if not collecting_quote:
            if '"' not in line:
                continue
            opening_idx = line.find('"')
            remainder = line[opening_idx + 1 :]
            if '"' in remainder:
                current["quote"] = remainder.split('"', 1)[0].strip()
            else:
                collecting_quote = True
                quote_buffer = [remainder]
            continue

        if '"' in line:
            closing_idx = line.find('"')
            quote_buffer.append(line[:closing_idx])
            current["quote"] = "\n".join(quote_buffer).strip()
            collecting_quote = False
            quote_buffer = []
            continue
        quote_buffer.append(line)

    if current:
        _finalize_entry()

    if not entries:
        raise StrategyV2MissingContextError(
            "No tagged VOC entries were parsed from precanon step 04 content. "
            "Remediation: rerun step 04 with tagged SOURCE/CATEGORY/EMOTION blocks."
        )
    return entries


def _extract_video_observations(competitor_analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    sheets = competitor_analysis.get("asset_observation_sheets")
    if not isinstance(sheets, list):
        return []

    videos: list[dict[str, Any]] = []
    for index, sheet in enumerate(sheets):
        if not isinstance(sheet, dict):
            continue
        platform_value = str(sheet.get("platform") or "").lower()
        if not any(name in platform_value for name in ("tiktok", "youtube", "instagram")):
            continue

        views = sheet.get("views") or sheet.get("view_count")
        followers = sheet.get("followers") or sheet.get("account_followers")
        comments = sheet.get("comments") or sheet.get("comment_count") or 0
        shares = sheet.get("shares") or sheet.get("share_count") or 0
        likes = sheet.get("likes") or sheet.get("like_count") or 0
        days = sheet.get("days_since_posted") or sheet.get("post_age_days") or 30
        description = str(sheet.get("core_claim") or sheet.get("headline") or "").strip()
        author = str(sheet.get("competitor_name") or sheet.get("brand") or f"source-{index}").strip()

        if not isinstance(views, (int, float)) or not isinstance(followers, (int, float)):
            continue

        videos.append(
            {
                "video_id": str(sheet.get("asset_id") or f"video-{index + 1}"),
                "platform": platform_value or "unknown",
                "views": int(views),
                "followers": int(followers),
                "comments": int(comments) if isinstance(comments, (int, float)) else 0,
                "shares": int(shares) if isinstance(shares, (int, float)) else 0,
                "likes": int(likes) if isinstance(likes, (int, float)) else 0,
                "days_since_posted": int(days) if isinstance(days, (int, float)) else 30,
                "description": description,
                "author": author,
                "source_ref": str(sheet.get("source_ref") or ""),
            }
        )

    return videos


def _map_buyer_stage(raw_stage: str) -> str:
    normalized = raw_stage.strip().lower()
    if "unaware" in normalized:
        return "UNAWARE"
    if "problem" in normalized:
        return "PROBLEM_AWARE"
    if "solution" in normalized:
        return "SOLUTION_AWARE"
    if "product" in normalized:
        return "PRODUCT_AWARE"
    if "most" in normalized:
        return "MOST_AWARE"
    return "UNKNOWN"


def _load_product(session, *, org_id: str, client_id: str, product_id: str) -> Product:
    product = session.scalars(
        select(Product).where(
            Product.org_id == org_id,
            Product.client_id == client_id,
            Product.id == product_id,
        )
    ).first()
    if not product:
        raise StrategyV2MissingContextError(
            f"Product not found for Strategy V2 (product_id={product_id}). "
            "Remediation: attach a valid product before starting Strategy V2."
        )
    return product


def _load_onboarding_payload(
    *,
    session,
    org_id: str,
    client_id: str,
    onboarding_payload_id: str | None,
) -> dict[str, Any]:
    onboarding_repo = OnboardingPayloadsRepository(session)
    record = None
    if onboarding_payload_id:
        record = onboarding_repo.get(org_id=org_id, payload_id=onboarding_payload_id)
    if not record:
        record = onboarding_repo.latest_for_client(org_id=org_id, client_id=client_id)
    if not record or not isinstance(record.data, dict):
        return {}
    payload: dict[str, Any] = {}
    for key, value in record.data.items():
        payload[str(key)] = value
    return payload


def _coerce_string_list(raw: object) -> list[str]:
    values: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                values.append(item.strip())
    return values


def _is_scrapeable_source_ref(source_ref: str) -> tuple[bool, str | None]:
    parsed = urlsplit(source_ref.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False, "invalid_url"

    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path or "/"

    if host in _NON_SCRAPEABLE_SOURCE_HOSTS:
        return False, "non_scrapeable_host"

    if host.endswith("reddit.com"):
        if path.startswith("/r/") or path.startswith("/user/") or "/comments/" in path:
            return True, None
        return False, "reddit_path_not_supported"

    if host.endswith("tiktok.com"):
        if "/@" in path or "/video/" in path or "/tag/" in path:
            return True, None
        return False, "tiktok_path_not_supported"

    if host.endswith("instagram.com"):
        if path.startswith("/reel/") or path.startswith("/p/") or len([part for part in path.split("/") if part]) == 1:
            return True, None
        return False, "instagram_path_not_supported"

    if host.endswith("youtube.com") or host.endswith("youtu.be"):
        if path.startswith("/watch") or path.startswith("/shorts/") or path.startswith("/@") or path.startswith("/channel/"):
            return True, None
        return False, "youtube_path_not_supported"

    if host.endswith("facebook.com") or host.endswith("fb.com"):
        if path and path != "/":
            return True, None
        return False, "facebook_path_not_supported"

    return True, None


def _partition_source_refs_for_ingestion(source_refs: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    scrapeable: list[str] = []
    excluded: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_ref in source_refs:
        ref = str(raw_ref or "").strip()
        if not ref:
            continue
        if ref in seen:
            continue
        seen.add(ref)
        allowed, reason = _is_scrapeable_source_ref(ref)
        if allowed:
            scrapeable.append(ref)
            continue
        excluded.append({"source_ref": ref, "reason": reason or "unsupported"})
    if not scrapeable:
        raise StrategyV2MissingContextError(
            "Strategy V2 ingestion source filtering produced zero scrapeable refs. "
            "Remediation: provide competitor/source URLs that point to scrapeable social/video/web assets."
        )
    return scrapeable, excluded


def _ingest_strategy_v2_asset_data(
    *,
    source_refs: list[str],
    include_ads_context: bool,
    include_social_video: bool,
    include_external_voc: bool,
) -> dict[str, Any]:
    try:
        payload = run_strategy_v2_apify_ingestion(
            source_refs=source_refs,
            include_ads_context=include_ads_context,
            include_social_video=include_social_video,
            include_external_voc=include_external_voc,
        )
    except Exception as exc:
        raise StrategyV2MissingContextError(
            "Strategy V2 Apify ingestion failed. "
            f"Remediation: verify Apify actor config/token and source refs. Root cause: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise StrategyV2SchemaValidationError(
            "Strategy V2 Apify ingestion returned an invalid payload type."
        )
    return payload


def _voc_row_source_bucket(row: Mapping[str, Any]) -> str:
    source_url = str(row.get("source_url") or "").strip().lower()
    domain_match = re.match(r"^https?://([^/]+)", source_url)
    if domain_match:
        domain = domain_match.group(1)
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    source_type = str(row.get("source_type") or "").strip().lower()
    if source_type:
        return source_type
    if "reddit.com" in source_url:
        return "reddit"
    if "tiktok.com" in source_url:
        return "tiktok"
    if "instagram.com" in source_url:
        return "instagram"
    if "youtube.com" in source_url or "youtu.be" in source_url:
        return "youtube"
    return "web"


def _parse_voc_recency_days(raw_date: str) -> int:
    value = raw_date.strip()
    if not value or value.lower() == "unknown":
        return 365
    for candidate in (value, value.replace("Z", "+00:00")):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
            return max(int(delta.total_seconds() // 86400), 0)
        except ValueError:
            continue
    return 365


def _score_voc_row_for_prompt(row: Mapping[str, Any]) -> tuple[float, str]:
    quote = str(row.get("quote") or "").strip()
    voc_id = str(row.get("voc_id") or "")
    if not quote:
        return 0.0, voc_id

    specificity = 0.0
    if re.search(r"\d", quote):
        specificity += 0.4
    if any(token in quote.lower() for token in ("week", "day", "month", "hour", "year", "%", "$")):
        specificity += 0.3
    if len(quote) >= 80:
        specificity += 0.3

    engagement_payload = row.get("engagement")
    likes = 0
    replies = 0
    if isinstance(engagement_payload, dict):
        likes_raw = engagement_payload.get("likes")
        replies_raw = engagement_payload.get("replies")
        likes = int(likes_raw) if isinstance(likes_raw, (int, float)) else 0
        replies = int(replies_raw) if isinstance(replies_raw, (int, float)) else 0
    engagement_score = min((likes + (2 * replies)) / 200.0, 1.0)

    recency_days = _parse_voc_recency_days(str(row.get("date") or "Unknown"))
    recency_score = 1.0 if recency_days <= 30 else 0.7 if recency_days <= 90 else 0.4 if recency_days <= 180 else 0.2

    total = (0.45 * specificity) + (0.30 * engagement_score) + (0.25 * recency_score)
    return total, voc_id


def _dedupe_voc_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        quote = re.sub(r"\s+", " ", str(row.get("quote") or "").strip().lower())
        source_url = str(row.get("source_url") or "").strip().lower()
        if not quote or not source_url:
            continue
        key = (source_url, quote[:260])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _select_diverse_voc_rows(
    rows: list[dict[str, Any]],
    *,
    max_rows: int,
    max_ratio_per_source: float,
) -> list[dict[str, Any]]:
    if max_rows <= 0:
        return []
    source_cap = max(1, int(max_rows * max_ratio_per_source))
    selected: list[dict[str, Any]] = []
    per_source: dict[str, int] = {}
    ranked = sorted(rows, key=_score_voc_row_for_prompt, reverse=True)
    selected_keys: set[str] = set()
    for row in ranked:
        source_bucket = _voc_row_source_bucket(row)
        if per_source.get(source_bucket, 0) >= source_cap:
            continue
        row_key = f"{str(row.get('source_url') or '')}::{str(row.get('quote') or '')[:120]}"
        if row_key in selected_keys:
            continue
        selected.append(row)
        selected_keys.add(row_key)
        per_source[source_bucket] = per_source.get(source_bucket, 0) + 1
        if len(selected) >= max_rows:
            break
    if len(selected) < max_rows:
        for row in ranked:
            row_key = f"{str(row.get('source_url') or '')}::{str(row.get('quote') or '')[:120]}"
            if row_key in selected_keys:
                continue
            selected.append(row)
            selected_keys.add(row_key)
            if len(selected) >= max_rows:
                break
    return selected


def _merge_voc_corpus_for_agent2(
    *,
    step4_rows: list[dict[str, Any]],
    external_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_step4 = _dedupe_voc_rows([row for row in step4_rows if isinstance(row, dict)])
    normalized_external = _dedupe_voc_rows([row for row in external_rows if isinstance(row, dict)])

    ranked_step4 = sorted(normalized_step4, key=_score_voc_row_for_prompt, reverse=True)
    ranked_external = sorted(normalized_external, key=_score_voc_row_for_prompt, reverse=True)

    prompt_rows: list[dict[str, Any]] = []
    selected_keys: set[str] = set()

    def _add_rows(rows: list[dict[str, Any]], *, limit: int) -> None:
        for row in rows:
            voc_id = str(row.get("voc_id") or "")
            quote = str(row.get("quote") or "").strip()
            source_url = str(row.get("source_url") or "").strip()
            if not quote or not source_url:
                continue
            dedupe_key = f"{source_url}::{quote[:120]}"
            if dedupe_key in selected_keys:
                continue
            prompt_rows.append(row)
            selected_keys.add(dedupe_key)
            if len(prompt_rows) >= limit:
                return

    _add_rows(ranked_step4, limit=min(_VOC_PROMPT_STEP4_ROWS, _VOC_PROMPT_CORPUS_ROWS))
    _add_rows(ranked_external, limit=min(_VOC_PROMPT_CORPUS_ROWS, _VOC_PROMPT_STEP4_ROWS + _VOC_PROMPT_EXTERNAL_ROWS))

    if len(prompt_rows) < _VOC_PROMPT_CORPUS_ROWS:
        combined_remaining = ranked_step4 + ranked_external
        _add_rows(combined_remaining, limit=_VOC_PROMPT_CORPUS_ROWS)

    prompt_rows = _select_diverse_voc_rows(
        prompt_rows,
        max_rows=_VOC_PROMPT_CORPUS_ROWS,
        max_ratio_per_source=_VOC_SOURCE_DIVERSITY_MAX_RATIO,
    )

    artifact_rows = _select_diverse_voc_rows(
        normalized_step4 + normalized_external,
        max_rows=_VOC_MERGED_CORPUS_MAX_ROWS,
        max_ratio_per_source=1.0,
    )
    if not prompt_rows:
        raise StrategyV2MissingContextError(
            "Merged VOC corpus selection produced zero prompt rows. "
            "Remediation: provide Step 04 entries and/or external Apify VOC rows with quote + source_url."
        )
    return {
        "prompt_rows": prompt_rows,
        "artifact_rows": artifact_rows,
        "summary": {
            "step4_input_count": len(step4_rows),
            "external_input_count": len(external_rows),
            "step4_deduped_count": len(normalized_step4),
            "external_deduped_count": len(normalized_external),
            "prompt_row_count": len(prompt_rows),
            "artifact_row_count": len(artifact_rows),
            "selection_targets": {
                "prompt_rows": _VOC_PROMPT_CORPUS_ROWS,
                "prompt_step4_rows": _VOC_PROMPT_STEP4_ROWS,
                "prompt_external_rows": _VOC_PROMPT_EXTERNAL_ROWS,
                "artifact_rows": _VOC_MERGED_CORPUS_MAX_ROWS,
            },
            "source_diversity_max_ratio": _VOC_SOURCE_DIVERSITY_MAX_RATIO,
        },
    }


def _build_proof_candidates_from_voc(
    *,
    voc_rows: list[dict[str, Any]],
    competitor_analysis: Mapping[str, Any],
) -> list[dict[str, Any]]:
    sheets = competitor_analysis.get("asset_observation_sheets")
    competitor_refs: list[str] = []
    if isinstance(sheets, list):
        competitor_refs = [
            str(row.get("source_ref")).strip()
            for row in sheets
            if isinstance(row, dict) and isinstance(row.get("source_ref"), str) and str(row.get("source_ref")).strip()
        ]

    ranked_rows = sorted(
        [row for row in voc_rows if isinstance(row, dict)],
        key=_score_voc_row_for_prompt,
        reverse=True,
    )
    candidates: list[dict[str, Any]] = []
    seen_notes: set[str] = set()
    for idx, row in enumerate(ranked_rows):
        quote = re.sub(r"\s+", " ", str(row.get("quote") or "").strip())
        if not quote:
            continue
        source_url = str(row.get("source_url") or "").strip()
        if not source_url:
            continue
        second_ref = next((ref for ref in competitor_refs if ref != source_url), "")
        if not second_ref:
            continue
        note = quote[:220]
        if note in seen_notes:
            continue
        seen_notes.add(note)
        compliance = str(row.get("compliance_risk") or "YELLOW").upper()
        if compliance == "RED":
            continue
        candidates.append(
            {
                "proof_id": f"proof_{idx + 1:03d}",
                "proof_note": note,
                "source_refs": [source_url, second_ref],
                "evidence_count": 2,
                "compliance_flag": "GREEN" if compliance == "GREEN" else "YELLOW",
            }
        )
        if len(candidates) >= 10:
            break
    return candidates


def _resolve_category_niche(*, onboarding_payload: Mapping[str, Any], product: Product) -> str:
    payload_category = onboarding_payload.get("product_category")
    if isinstance(payload_category, str) and payload_category.strip():
        return payload_category.strip()

    if isinstance(product.product_type, str) and product.product_type.strip():
        return product.product_type.strip()

    raise StrategyV2MissingContextError(
        "Strategy V2 foundational research requires a category niche but none was found. "
        "Remediation: provide onboarding payload product_category or set product.product_type."
    )


def _build_foundational_variables(
    *,
    stage0: ProductBriefStage0,
    onboarding_payload: Mapping[str, Any],
    category_niche: str,
    ads_context: str,
) -> dict[str, str]:
    business_context = f"{stage0.product_name}: {stage0.description}".strip()
    context_payload = {
        "stage0": stage0.model_dump(mode="python"),
        "onboarding_payload": dict(onboarding_payload),
    }
    return {
        "BUSINESS_CONTEXT": business_context,
        "BUSINESS_CONTEXT_JSON": json.dumps(context_payload, ensure_ascii=True),
        "CATEGORY_NICHE": category_niche,
        "ADS_CONTEXT": ads_context,
    }


def _run_tagged_foundational_step(
    *,
    step_key: str,
    prompt_text: str,
    model: str,
    summary_max_chars: int,
    include_step4_prompt: bool = False,
    handoff_max_chars: int | None = None,
    use_reasoning: bool = True,
    use_web_search: bool = False,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    guarded_prompt = _append_tagged_output_guardrails(
        prompt_text=prompt_text,
        include_step4_prompt=include_step4_prompt,
    )
    raw_output = _llm_generate_text(
        prompt=guarded_prompt,
        model=model,
        use_reasoning=use_reasoning,
        use_web_search=use_web_search,
        max_tokens=max_tokens,
        heartbeat_context={
            "activity": "strategy_v2.run_voc_angle_pipeline",
            "phase": "foundational",
            "step_key": step_key,
            "model": model,
        },
    )
    try:
        parsed = parse_step_output(
            step_key=step_key,
            raw_output=raw_output,
            summary_max_chars=summary_max_chars,
            handoff_max_chars=handoff_max_chars,
        )
    except Exception as exc:
        raise StrategyV2MissingContextError(
            f"Failed to parse tagged foundational step output for step {step_key}: {exc}. "
            "Remediation: rerun foundational step with tagged output format enabled."
        ) from exc
    return {
        "summary": parsed.summary,
        "content": parsed.content,
        "handoff": parsed.handoff or {},
    }


def _generate_competitor_analysis_json(
    *,
    stage0: ProductBriefStage0,
    category_niche: str,
    step1_summary: str,
    step1_content: str,
    confirmed_competitor_assets: list[str],
) -> dict[str, Any]:
    if len(confirmed_competitor_assets) < 3:
        raise StrategyV2MissingContextError(
            "Stage 2A competitor analysis requires at least 3 confirmed competitor assets. "
            "Remediation: complete H2 with 3+ asset references."
        )
    competitor_asset_analyzer = resolve_prompt_asset(
        pattern=_VOC_COMPETITOR_ANALYZER_PROMPT_PATTERN,
        context="VOC competitor asset analyzer",
    )
    parsed, _raw, _provenance = _run_prompt_json_object(
        asset=competitor_asset_analyzer,
        context="strategy_v2.competitor_asset_analysis",
        model=settings.STRATEGY_V2_VOC_MODEL,
        runtime_instruction=(
            "## Runtime Input Block\n"
            f"COMPETITOR_ASSETS:\n{_dump_prompt_json(confirmed_competitor_assets, max_chars=24000)}\n\n"
            f"PRODUCT_BRIEF:\n{_dump_prompt_json(stage0.model_dump(mode='python'), max_chars=10000)}\n\n"
            f"KNOWN_COMPETITORS:\n{_dump_prompt_json(list(stage0.competitor_urls), max_chars=6000)}\n\n"
            f"CATEGORY_CONTEXT:\n{category_niche}\n\n"
            f"STEP1_SUMMARY:\n{step1_summary[:10000]}\n\n"
            f"STEP1_CONTENT:\n{step1_content[:20000]}\n\n"
            "## Runtime Output Contract\n"
            "Return ONLY competitor_analysis JSON with observation sheets, saturation/whitespace maps, "
            "messaging patterns, compliance landscape, competitors, and key findings."
        ),
        schema_name="strategy_v2_competitor_analysis",
        schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "asset_observation_sheets": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "asset_id": {"type": "string"},
                            "competitor_name": {"type": "string"},
                            "brand": {"type": "string"},
                            "primary_angle": {"type": "string"},
                            "core_claim": {"type": "string"},
                            "implied_mechanism": {"type": "string"},
                            "target_segment_description": {"type": "string"},
                            "hook_type": {"type": "string"},
                            "source_ref": {"type": "string"},
                        },
                        "required": [
                            "asset_id",
                            "competitor_name",
                            "brand",
                            "primary_angle",
                            "core_claim",
                            "implied_mechanism",
                            "target_segment_description",
                            "hook_type",
                            "source_ref",
                        ],
                    },
                },
                "compliance_landscape": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "red_pct": {"type": "number"},
                        "yellow_pct": {"type": "number"},
                        "overall": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "red_pct": {"type": "number"},
                                "yellow_pct": {"type": "number"},
                            },
                            "required": ["red_pct", "yellow_pct"],
                        },
                    },
                    "required": ["red_pct", "yellow_pct", "overall"],
                },
                "saturation_map": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "angle": {"type": "string"},
                            "angle_name": {"type": "string"},
                            "driver": {"type": "string"},
                            "status": {"type": "string"},
                            "competitor_count": {"type": "string"},
                        },
                        "required": ["angle", "angle_name", "driver", "status", "competitor_count"],
                    },
                },
            },
            "required": ["asset_observation_sheets", "compliance_landscape", "saturation_map"],
        },
        use_reasoning=True,
        use_web_search=False,
        heartbeat_context={
            "activity": "strategy_v2.run_voc_angle_pipeline",
            "phase": "foundational",
            "step_key": "02",
            "model": settings.STRATEGY_V2_VOC_MODEL,
        },
    )
    if not isinstance(parsed, dict):
        raise StrategyV2SchemaValidationError("competitor_analysis output must be a JSON object.")
    compliance = _require_dict(
        payload=parsed.get("compliance_landscape"),
        field_name="competitor_analysis.compliance_landscape",
    )
    red = compliance.get("red_pct")
    yellow = compliance.get("yellow_pct")
    if (not isinstance(red, (int, float)) or not isinstance(yellow, (int, float))) and isinstance(
        compliance.get("overall"), dict
    ):
        overall = _require_dict(payload=compliance.get("overall"), field_name="competitor_analysis.compliance_landscape.overall")
        red = overall.get("red_pct")
        yellow = overall.get("yellow_pct")
    if not isinstance(red, (int, float)) or not isinstance(yellow, (int, float)):
        raise StrategyV2SchemaValidationError(
            "competitor_analysis.compliance_landscape must include numeric red_pct and yellow_pct."
        )
    parsed["compliance_landscape"] = {
        "red_pct": max(0.0, min(1.0, float(red))),
        "yellow_pct": max(0.0, min(1.0, float(yellow))),
    }
    if not isinstance(parsed.get("competitor_urls"), list):
        parsed["competitor_urls"] = list(stage0.competitor_urls)
    sheets = parsed.get("asset_observation_sheets")
    if not isinstance(sheets, list):
        raise StrategyV2SchemaValidationError(
            "competitor_analysis.asset_observation_sheets must be an array."
        )
    return parsed


def _run_foundational_research_without_step02(
    *,
    stage0: ProductBriefStage0,
    onboarding_payload: Mapping[str, Any],
    product: Product,
    workflow_run_id: str,
) -> dict[str, Any]:
    _log_workflow_activity_safe(
        workflow_run_id=workflow_run_id,
        step="v2-02.foundation",
        status="started",
        payload_in={"model": settings.STRATEGY_V2_VOC_MODEL},
    )

    def _log_step_start(step_key: str, *, model: str, use_web_search: bool) -> float:
        started_at = time.monotonic()
        _log_workflow_activity_safe(
            workflow_run_id=workflow_run_id,
            step=f"v2-02.foundation.{step_key}",
            status="started",
            payload_in={"model": model, "use_web_search": use_web_search},
        )
        return started_at

    def _log_step_done(step_key: str, started_at: float, *, summary: str, content: str) -> None:
        elapsed_seconds = round(time.monotonic() - started_at, 2)
        summary_excerpt = " ".join(summary.split())[:280] if summary else ""
        content_excerpt = " ".join(content.split())[:280] if content else ""
        _log_workflow_activity_safe(
            workflow_run_id=workflow_run_id,
            step=f"v2-02.foundation.{step_key}",
            status="completed",
            payload_out={
                "elapsed_seconds": elapsed_seconds,
                "summary_chars": len(summary),
                "content_chars": len(content),
                "summary_excerpt": summary_excerpt,
                "content_excerpt": content_excerpt,
            },
        )

    category_niche = _resolve_category_niche(onboarding_payload=onboarding_payload, product=product)
    seed_refs = [url for url in stage0.competitor_urls if isinstance(url, str) and url.strip()]
    if seed_refs:
        scrapeable_seed_refs, excluded_seed_refs = _partition_source_refs_for_ingestion(seed_refs)
        asset_data_context = _ingest_strategy_v2_asset_data(
            source_refs=scrapeable_seed_refs,
            include_ads_context=True,
            include_social_video=False,
            include_external_voc=False,
        )
        asset_data_context["excluded_source_refs"] = excluded_seed_refs
        asset_data_context["ingestion_source_refs"] = scrapeable_seed_refs
        ads_context = str(asset_data_context.get("ads_context") or "").strip()
    else:
        asset_data_context = {
            "enabled": False,
            "summary": {"run_count": 0},
        }
        ads_context = json.dumps(
            {
                "source": "seed_urls_only",
                "seed_url_count": 0,
                "candidate_asset_count": 0,
                "platform_breakdown": {},
                "top_asset_refs": [],
            },
            ensure_ascii=True,
        )
    if not ads_context:
        raise StrategyV2MissingContextError(
            "Foundational research requires ADS_CONTEXT but ingestion returned empty context. "
            "Remediation: verify Strategy V2 Apify ingestion settings and competitor URLs."
        )
    variables = _build_foundational_variables(
        stage0=stage0,
        onboarding_payload=onboarding_payload,
        category_niche=category_niche,
        ads_context=ads_context,
    )

    prompt_01 = _render_prompt_template(
        template=_read_v2_prompt(pattern=_FOUNDATIONAL_PROMPT_01_PATTERN, context="foundational step 01"),
        variables=variables,
        context="foundational step 01",
    )
    step_01_started = _log_step_start("01", model=_FOUNDTN_STEP01_MODEL, use_web_search=True)
    step01 = _run_tagged_foundational_step(
        step_key="01",
        prompt_text=prompt_01,
        model=_FOUNDTN_STEP01_MODEL,
        summary_max_chars=_FOUNDTN_STEP01_SUMMARY_MAX,
        use_reasoning=True,
        use_web_search=True,
    )
    _log_step_done("01", step_01_started, summary=str(step01["summary"]), content=str(step01["content"]))

    vars_03 = dict(variables)
    vars_03["STEP1_SUMMARY"] = step01["summary"]
    vars_03["STEP1_CONTENT"] = step01["content"]
    prompt_03 = _render_prompt_template(
        template=_read_v2_prompt(pattern=_FOUNDATIONAL_PROMPT_03_PATTERN, context="foundational step 03"),
        variables=vars_03,
        context="foundational step 03",
    )
    step_03_started = _log_step_start("03", model=_FOUNDTN_STEP03_MODEL, use_web_search=False)
    step03 = _run_tagged_foundational_step(
        step_key="03",
        prompt_text=prompt_03,
        model=_FOUNDTN_STEP03_MODEL,
        summary_max_chars=_FOUNDTN_STEP03_SUMMARY_MAX,
        include_step4_prompt=True,
        handoff_max_chars=_FOUNDTN_STEP03_PROMPT_MAX,
        use_reasoning=True,
        use_web_search=False,
    )
    _log_step_done("03", step_03_started, summary=str(step03["summary"]), content=str(step03["content"]))

    step4_prompt = str((step03.get("handoff") or {}).get("step4_prompt") or "").strip()
    if not step4_prompt:
        raise StrategyV2MissingContextError(
            "Foundational step 03 did not produce STEP4_PROMPT content. "
            "Remediation: rerun step 03 with valid tagged output blocks."
        )
    step_04_started = _log_step_start("04", model=_FOUNDTN_STEP04_MODEL, use_web_search=True)
    step04 = _run_tagged_foundational_step(
        step_key="04",
        prompt_text=step4_prompt,
        model=_FOUNDTN_STEP04_MODEL,
        summary_max_chars=_FOUNDTN_STEP04_SUMMARY_MAX,
        use_reasoning=True,
        use_web_search=True,
        max_tokens=_FOUNDTN_STEP04_MAX_TOKENS,
    )
    _log_step_done("04", step_04_started, summary=str(step04["summary"]), content=str(step04["content"]))

    vars_06 = dict(variables)
    vars_06["STEP4_SUMMARY"] = step04["summary"]
    vars_06["STEP4_CONTENT"] = step04["content"]
    prompt_06 = _render_prompt_template(
        template=_read_v2_prompt(pattern=_FOUNDATIONAL_PROMPT_06_PATTERN, context="foundational step 06"),
        variables=vars_06,
        context="foundational step 06",
    )
    step_06_started = _log_step_start("06", model=_FOUNDTN_STEP06_MODEL, use_web_search=False)
    step06 = _run_tagged_foundational_step(
        step_key="06",
        prompt_text=prompt_06,
        model=_FOUNDTN_STEP06_MODEL,
        summary_max_chars=_FOUNDTN_STEP06_SUMMARY_MAX,
        use_reasoning=True,
        use_web_search=False,
    )
    _log_step_done("06", step_06_started, summary=str(step06["summary"]), content=str(step06["content"]))

    _log_workflow_activity_safe(
        workflow_run_id=workflow_run_id,
        step="v2-02.foundation",
        status="completed",
        payload_out={
            "step_keys": ["01", "03", "04", "06"],
            "category_niche": category_niche,
        },
    )
    return {
        "category_niche": category_niche,
        "asset_data_context": asset_data_context,
        "step_summaries": {
            "01": str(step01["summary"]),
            "03": str(step03["summary"]),
            "04": str(step04["summary"]),
            "06": str(step06["summary"]),
        },
        "step_contents": {
            "01": str(step01["content"]),
            "03": str(step03["content"]),
            "04": str(step04["content"]),
            "06": str(step06["content"]),
        },
    }


def _run_foundational_research_from_onboarding(
    *,
    stage0: ProductBriefStage0,
    onboarding_payload: Mapping[str, Any],
    product: Product,
    workflow_run_id: str,
    confirmed_competitor_assets: list[str],
) -> dict[str, Any]:
    _log_workflow_activity_safe(
        workflow_run_id=workflow_run_id,
        step="v2-02.foundation",
        status="started",
        payload_in={"model": settings.STRATEGY_V2_VOC_MODEL},
    )

    def _log_step_start(step_key: str, *, model: str, use_web_search: bool) -> float:
        started_at = time.monotonic()
        activity.logger.info(
            "strategy_v2.foundational.step.start",
            extra={
                "step_key": step_key,
                "model": model,
                "use_web_search": use_web_search,
            },
        )
        _log_workflow_activity_safe(
            workflow_run_id=workflow_run_id,
            step=f"v2-02.foundation.{step_key}",
            status="started",
            payload_in={
                "model": model,
                "use_web_search": use_web_search,
            },
        )
        return started_at

    def _log_step_done(step_key: str, started_at: float, *, summary: str, content: str) -> None:
        elapsed_seconds = round(time.monotonic() - started_at, 2)
        summary_excerpt = " ".join(summary.split())[:280] if summary else ""
        content_excerpt = " ".join(content.split())[:280] if content else ""
        activity.logger.info(
            "strategy_v2.foundational.step.completed",
            extra={
                "step_key": step_key,
                "elapsed_seconds": elapsed_seconds,
                "summary_chars": len(summary),
                "content_chars": len(content),
                "summary_excerpt": summary_excerpt,
                "content_excerpt": content_excerpt,
            },
        )
        _log_workflow_activity_safe(
            workflow_run_id=workflow_run_id,
            step=f"v2-02.foundation.{step_key}",
            status="completed",
            payload_out={
                "elapsed_seconds": elapsed_seconds,
                "summary_chars": len(summary),
                "content_chars": len(content),
                "summary_excerpt": summary_excerpt,
                "content_excerpt": content_excerpt,
            },
        )

    category_niche = _resolve_category_niche(onboarding_payload=onboarding_payload, product=product)
    seed_refs = [url for url in stage0.competitor_urls if isinstance(url, str) and url.strip()]
    if seed_refs:
        scrapeable_seed_refs, excluded_seed_refs = _partition_source_refs_for_ingestion(seed_refs)
        asset_data_context = _ingest_strategy_v2_asset_data(
            source_refs=scrapeable_seed_refs,
            include_ads_context=True,
            include_social_video=False,
            include_external_voc=False,
        )
        asset_data_context["excluded_source_refs"] = excluded_seed_refs
        asset_data_context["ingestion_source_refs"] = scrapeable_seed_refs
        ads_context = str(asset_data_context.get("ads_context") or "").strip()
    else:
        asset_data_context = {
            "enabled": False,
            "summary": {"run_count": 0},
        }
        ads_context = json.dumps(
            {
                "source": "seed_urls_only",
                "seed_url_count": 0,
                "candidate_asset_count": 0,
                "platform_breakdown": {},
                "top_asset_refs": [],
            },
            ensure_ascii=True,
        )
    if not ads_context:
        raise StrategyV2MissingContextError(
            "Foundational research requires ADS_CONTEXT but ingestion returned empty context. "
            "Remediation: verify Strategy V2 Apify ingestion settings and competitor URLs."
        )
    variables = _build_foundational_variables(
        stage0=stage0,
        onboarding_payload=onboarding_payload,
        category_niche=category_niche,
        ads_context=ads_context,
    )

    prompt_01 = _render_prompt_template(
        template=_read_v2_prompt(pattern=_FOUNDATIONAL_PROMPT_01_PATTERN, context="foundational step 01"),
        variables=variables,
        context="foundational step 01",
    )
    step_01_started = _log_step_start("01", model=_FOUNDTN_STEP01_MODEL, use_web_search=True)
    step01 = _run_tagged_foundational_step(
        step_key="01",
        prompt_text=prompt_01,
        model=_FOUNDTN_STEP01_MODEL,
        summary_max_chars=_FOUNDTN_STEP01_SUMMARY_MAX,
        use_reasoning=True,
        use_web_search=True,
    )
    _log_step_done("01", step_01_started, summary=str(step01["summary"]), content=str(step01["content"]))

    vars_03 = dict(variables)
    vars_03["STEP1_SUMMARY"] = step01["summary"]
    vars_03["STEP1_CONTENT"] = step01["content"]
    prompt_03 = _render_prompt_template(
        template=_read_v2_prompt(pattern=_FOUNDATIONAL_PROMPT_03_PATTERN, context="foundational step 03"),
        variables=vars_03,
        context="foundational step 03",
    )
    step_03_started = _log_step_start("03", model=_FOUNDTN_STEP03_MODEL, use_web_search=False)
    step03 = _run_tagged_foundational_step(
        step_key="03",
        prompt_text=prompt_03,
        model=_FOUNDTN_STEP03_MODEL,
        summary_max_chars=_FOUNDTN_STEP03_SUMMARY_MAX,
        include_step4_prompt=True,
        handoff_max_chars=_FOUNDTN_STEP03_PROMPT_MAX,
        use_reasoning=True,
        use_web_search=False,
    )
    _log_step_done("03", step_03_started, summary=str(step03["summary"]), content=str(step03["content"]))

    step4_prompt = str((step03.get("handoff") or {}).get("step4_prompt") or "").strip()
    if not step4_prompt:
        raise StrategyV2MissingContextError(
            "Foundational step 03 did not produce STEP4_PROMPT content. "
            "Remediation: rerun step 03 with valid tagged output blocks."
        )
    step_04_started = _log_step_start("04", model=_FOUNDTN_STEP04_MODEL, use_web_search=True)
    step04 = _run_tagged_foundational_step(
        step_key="04",
        prompt_text=step4_prompt,
        model=_FOUNDTN_STEP04_MODEL,
        summary_max_chars=_FOUNDTN_STEP04_SUMMARY_MAX,
        use_reasoning=True,
        use_web_search=True,
        max_tokens=_FOUNDTN_STEP04_MAX_TOKENS,
    )
    _log_step_done("04", step_04_started, summary=str(step04["summary"]), content=str(step04["content"]))

    vars_06 = dict(variables)
    vars_06["STEP4_SUMMARY"] = step04["summary"]
    vars_06["STEP4_CONTENT"] = step04["content"]
    prompt_06 = _render_prompt_template(
        template=_read_v2_prompt(pattern=_FOUNDATIONAL_PROMPT_06_PATTERN, context="foundational step 06"),
        variables=vars_06,
        context="foundational step 06",
    )
    step_06_started = _log_step_start("06", model=_FOUNDTN_STEP06_MODEL, use_web_search=False)
    step06 = _run_tagged_foundational_step(
        step_key="06",
        prompt_text=prompt_06,
        model=_FOUNDTN_STEP06_MODEL,
        summary_max_chars=_FOUNDTN_STEP06_SUMMARY_MAX,
        use_reasoning=True,
        use_web_search=False,
    )
    _log_step_done("06", step_06_started, summary=str(step06["summary"]), content=str(step06["content"]))

    step_02_started = _log_step_start("02", model=settings.STRATEGY_V2_VOC_MODEL, use_web_search=True)
    competitor_analysis = _generate_competitor_analysis_json(
        stage0=stage0,
        category_niche=category_niche,
        step1_summary=str(step01["summary"]),
        step1_content=str(step01["content"]),
        confirmed_competitor_assets=confirmed_competitor_assets,
    )
    _log_step_done(
        "02",
        step_02_started,
        summary=f"competitors={len(competitor_analysis.get('competitor_urls', []))}",
        content=json.dumps(competitor_analysis, ensure_ascii=True),
    )

    _log_workflow_activity_safe(
        workflow_run_id=workflow_run_id,
        step="v2-02.foundation",
        status="completed",
        payload_out={
            "step_keys": ["01", "03", "04", "06", "02"],
            "category_niche": category_niche,
        },
    )

    return {
        "category_niche": category_niche,
        "asset_data_context": asset_data_context,
        "step_summaries": {
            "01": str(step01["summary"]),
            "03": str(step03["summary"]),
            "04": str(step04["summary"]),
            "06": str(step06["summary"]),
        },
        "step_contents": {
            "01": str(step01["content"]),
            "02": json.dumps(competitor_analysis, ensure_ascii=True),
            "03": str(step03["content"]),
            "04": str(step04["content"]),
            "06": str(step06["content"]),
        },
    }


def _resolve_brand_voice_notes(
    *,
    explicit_notes: str,
    onboarding_payload: Mapping[str, Any] | None,
    stage2: ProductBriefStage2,
) -> str:
    cleaned_explicit = explicit_notes.strip()
    if cleaned_explicit:
        return cleaned_explicit

    if onboarding_payload is not None:
        value = onboarding_payload.get("brand_voice_notes")
        if isinstance(value, str) and value.strip():
            return value.strip()

    raise StrategyV2MissingContextError(
        f"Brand voice notes are required for offer winner finalization ({stage2.product_name}) but were missing. "
        "Remediation: provide `brand_voice_notes` in workflow start input or onboarding payload."
    )


def _resolve_compliance_notes(
    *,
    explicit_notes: str,
    onboarding_payload: Mapping[str, Any] | None,
    stage2: ProductBriefStage2,
    compliance_sensitivity: str | None = None,
) -> str:
    lines: list[str] = []
    cleaned_explicit = explicit_notes.strip()
    if cleaned_explicit:
        lines.extend(line.strip() for line in cleaned_explicit.splitlines() if line.strip())
    if onboarding_payload is not None:
        disclaimers = _coerce_string_list(onboarding_payload.get("disclaimers"))
        if disclaimers:
            lines.extend(disclaimers)

    constraints = stage2.compliance_constraints
    if constraints is not None:
        lines.append(f"Overall risk: {constraints.overall_risk}")
        if constraints.platform_notes:
            lines.append(constraints.platform_notes)
        lines.extend(f"Avoid: {pattern}" for pattern in constraints.red_flag_patterns)
    if compliance_sensitivity:
        lines.append(f"Competitor compliance sensitivity: {compliance_sensitivity}")
    contradiction_count = stage2.selected_angle.evidence.contradiction_count
    lines.append(f"Selected angle contradiction count: {contradiction_count}")
    lines.append("Avoid absolute guarantees and keep claims specific, supportable, and non-diagnostic.")

    deduped_lines: list[str] = []
    for line in lines:
        cleaned = line.strip().lstrip("-* ").strip()
        if cleaned and cleaned not in deduped_lines:
            deduped_lines.append(cleaned)
    if not deduped_lines:
        raise StrategyV2MissingContextError(
            "Compliance context is empty after merge. Remediation: provide operator compliance notes or source constraints."
        )
    return "\n".join(f"- {item}" for item in deduped_lines)


def _coerce_yes_no(value: object, *, default: str = "N") -> str:
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in {"Y", "N"}:
            return normalized
    if isinstance(value, bool):
        return "Y" if value else "N"
    return default


_VOC_REQUIRED_FIELDS = (
    "voc_id",
    "source",
    "quote",
    "specific_number",
    "specific_product_brand",
    "specific_event_moment",
    "specific_body_symptom",
    "before_after_comparison",
    "crisis_language",
    "profanity_extreme_punctuation",
    "physical_sensation",
    "identity_change_desire",
    "word_count",
    "clear_trigger_event",
    "named_enemy",
    "shiftable_belief",
    "expectation_vs_reality",
    "headline_ready",
    "usable_content_pct",
    "personal_context",
    "long_narrative",
    "engagement_received",
    "real_person_signals",
    "moderated_community",
    "trigger_event",
    "pain_problem",
    "desired_outcome",
    "failed_prior_solution",
    "enemy_blame",
    "identity_role",
    "fear_risk",
    "emotional_valence",
    "durable_psychology",
    "market_specific",
    "date_bracket",
    "buyer_stage",
    "solution_sophistication",
    "compliance_risk",
)

_VOC_INTENSITY_FIELDS = (
    "crisis_language",
    "profanity_extreme_punctuation",
    "physical_sensation",
    "identity_change_desire",
)

_VOC_ANGLE_FIELDS = (
    "clear_trigger_event",
    "named_enemy",
    "shiftable_belief",
    "expectation_vs_reality",
    "headline_ready",
)

_VOC_CREDIBILITY_FIELDS = (
    "personal_context",
    "long_narrative",
    "engagement_received",
    "real_person_signals",
    "moderated_community",
)

_VOC_FIRST_PERSON_PATTERN = re.compile(r"\b(i|i['’]?m|i['’]?ve|me|my|mine|we|our|us)\b", flags=re.IGNORECASE)
_VOC_INTENSITY_TOKEN_PATTERN = re.compile(
    r"\b(pain|hurt|anxiety|anxious|fear|frustrat|stress|worry|risk|danger|sick|flu|cold|infection|cough)\b",
    flags=re.IGNORECASE,
)
_VOC_ANGLE_CONTEXT_PATTERN = re.compile(
    r"\b(when|after|before|because|if|without|instead|vs|versus)\b",
    flags=re.IGNORECASE,
)


def _require_row_fields(
    *,
    row: Mapping[str, Any],
    required_fields: tuple[str, ...],
    row_name: str,
) -> None:
    missing: list[str] = []
    for field_name in required_fields:
        if field_name not in row:
            missing.append(field_name)
            continue
        value = row.get(field_name)
        if value is None:
            missing.append(field_name)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(field_name)
    if missing:
        raise StrategyV2SchemaValidationError(
            f"{row_name} is missing required fields: {missing}. "
            "Remediation: emit complete observation sheet fields from the upstream agent output."
        )


def _all_no_flags(row: Mapping[str, Any], fields: tuple[str, ...]) -> bool:
    return all(_coerce_yes_no(row.get(field_name)) == "N" for field_name in fields)


def _enrich_voc_observation_signal(*, row: dict[str, Any]) -> dict[str, Any]:
    quote = str(row.get("quote") or "")
    quote_lower = quote.lower()
    source = str(row.get("source") or "").lower()

    if _all_no_flags(row, _VOC_CREDIBILITY_FIELDS):
        if any(token in source for token in ("reddit.com", "forum", "community", "comment", "thread")):
            row["moderated_community"] = "Y"
        elif _VOC_FIRST_PERSON_PATTERN.search(quote_lower):
            row["personal_context"] = "Y"
        elif len(quote) >= 180:
            row["long_narrative"] = "Y"

    if _all_no_flags(row, _VOC_ANGLE_FIELDS):
        if _VOC_ANGLE_CONTEXT_PATTERN.search(quote_lower):
            row["expectation_vs_reality"] = "Y"
        elif len(quote) >= 180:
            row["headline_ready"] = "Y"

    if _all_no_flags(row, _VOC_INTENSITY_FIELDS):
        if _VOC_INTENSITY_TOKEN_PATTERN.search(quote_lower):
            row["crisis_language"] = "Y"

    return row


def _normalize_habitat_observations(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for index, row in enumerate(raw_rows):
        name = str(row.get("habitat_name") or row.get("name") or f"Habitat {index + 1}").strip()
        habitat_type = str(row.get("habitat_type") or "TEXT_COMMUNITY").strip()
        url_pattern = str(row.get("url_pattern") or row.get("source") or name).strip()

        samples_raw = row.get("language_samples")
        samples: list[dict[str, Any]] = []
        if isinstance(samples_raw, list):
            for sample in samples_raw[:5]:
                if not isinstance(sample, dict):
                    continue
                samples.append(
                    {
                        "word_count": int(sample.get("word_count") or 0),
                        "has_trigger_event": _coerce_yes_no(sample.get("has_trigger_event")),
                        "has_failed_solution": _coerce_yes_no(sample.get("has_failed_solution")),
                        "has_identity_language": _coerce_yes_no(sample.get("has_identity_language")),
                        "has_specific_outcome": _coerce_yes_no(sample.get("has_specific_outcome")),
                    }
                )
        observations.append(
            {
                "habitat_name": name,
                "habitat_type": habitat_type or "TEXT_COMMUNITY",
                "url_pattern": url_pattern or name,
                "threads_50_plus": _coerce_yes_no(row.get("threads_50_plus")),
                "threads_200_plus": _coerce_yes_no(row.get("threads_200_plus")),
                "threads_1000_plus": _coerce_yes_no(row.get("threads_1000_plus")),
                "posts_last_3mo": _coerce_yes_no(row.get("posts_last_3mo")),
                "posts_last_6mo": _coerce_yes_no(row.get("posts_last_6mo")),
                "posts_last_12mo": _coerce_yes_no(row.get("posts_last_12mo")),
                "recency_ratio": str(row.get("recency_ratio") or "CANNOT_DETERMINE"),
                "exact_category": _coerce_yes_no(row.get("exact_category"), default="Y"),
                "purchasing_comparing": _coerce_yes_no(row.get("purchasing_comparing")),
                "personal_usage": _coerce_yes_no(row.get("personal_usage")),
                "adjacent_only": _coerce_yes_no(row.get("adjacent_only")),
                "first_person_narratives": _coerce_yes_no(row.get("first_person_narratives")),
                "trigger_events": _coerce_yes_no(row.get("trigger_events")),
                "fear_frustration_shame": _coerce_yes_no(row.get("fear_frustration_shame")),
                "specific_dollar_or_time": _coerce_yes_no(row.get("specific_dollar_or_time")),
                "long_detailed_posts": _coerce_yes_no(row.get("long_detailed_posts")),
                "language_samples": samples,
                "purchase_intent_density": str(row.get("purchase_intent_density") or "SOME"),
                "discusses_spending": _coerce_yes_no(row.get("discusses_spending")),
                "recommendation_threads": _coerce_yes_no(row.get("recommendation_threads")),
                "relevance_pct": str(row.get("relevance_pct") or "25_TO_50_PCT"),
                "dominated_by_offtopic": _coerce_yes_no(row.get("dominated_by_offtopic")),
                "competitor_brand_count": str(row.get("competitor_brand_count") or "0"),
                "competitor_ads_present": _coerce_yes_no(row.get("competitor_ads_present")),
                "trend_direction": str(row.get("trend_direction") or "CANNOT_DETERMINE"),
                "habitat_age": str(row.get("habitat_age") or "CANNOT_DETERMINE"),
                "membership_trend": str(row.get("membership_trend") or "CANNOT_DETERMINE"),
                "post_frequency_trend": str(row.get("post_frequency_trend") or "CANNOT_DETERMINE"),
                "publicly_accessible": _coerce_yes_no(row.get("publicly_accessible"), default="Y"),
                "text_based_content": _coerce_yes_no(row.get("text_based_content"), default="Y"),
                "target_language": _coerce_yes_no(row.get("target_language"), default="Y"),
                "no_rate_limiting": _coerce_yes_no(row.get("no_rate_limiting"), default="Y"),
            }
        )
    if not observations:
        raise StrategyV2SchemaValidationError(
            "Prompt-chain Agent 1 did not return any habitat observations."
        )
    return observations


def _normalize_voc_observations(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for index, row in enumerate(raw_rows):
        row_payload = dict(row)
        if "source" not in row_payload and isinstance(row_payload.get("source_url"), str):
            row_payload["source"] = str(row_payload.get("source_url") or "")
        _require_row_fields(
            row=row_payload,
            required_fields=_VOC_REQUIRED_FIELDS,
            row_name=f"Agent 2 VOC observation[{index}]",
        )

        quote = str(row_payload.get("quote") or "").strip()
        source = str(row_payload.get("source") or "").strip()
        buyer_stage = _map_buyer_stage(str(row_payload.get("buyer_stage") or "UNKNOWN"))
        solution_sophistication = str(row_payload.get("solution_sophistication") or "UNKNOWN").strip().upper()
        if solution_sophistication not in {"NOVICE", "EXPERIENCED", "EXHAUSTED"}:
            solution_sophistication = "UNKNOWN"
        compliance = str(row_payload.get("compliance_risk") or "YELLOW").strip().upper()
        if compliance not in {"GREEN", "YELLOW", "RED"}:
            compliance = "YELLOW"
        try:
            word_count = int(row_payload.get("word_count") or 0)
        except Exception as exc:
            raise StrategyV2SchemaValidationError(
                f"Agent 2 VOC observation[{index}] has invalid word_count."
            ) from exc
        if word_count <= 0:
            raise StrategyV2SchemaValidationError(
                f"Agent 2 VOC observation[{index}] requires word_count > 0."
            )
        usable_content_pct = str(row_payload.get("usable_content_pct") or "").strip().upper()
        if usable_content_pct not in {"OVER_75_PCT", "50_TO_75_PCT", "25_TO_50_PCT", "UNDER_25_PCT"}:
            raise StrategyV2SchemaValidationError(
                f"Agent 2 VOC observation[{index}] has invalid usable_content_pct='{usable_content_pct}'."
            )
        date_bracket = str(row_payload.get("date_bracket") or "").strip().upper()
        if date_bracket not in {"LAST_3MO", "LAST_6MO", "LAST_12MO", "LAST_24MO", "OLDER", "UNKNOWN"}:
            raise StrategyV2SchemaValidationError(
                f"Agent 2 VOC observation[{index}] has invalid date_bracket='{date_bracket}'."
            )
        emotional_valence = str(row_payload.get("emotional_valence") or "").strip().upper()
        if emotional_valence not in {
            "RELIEF",
            "RAGE",
            "SHAME",
            "PRIDE",
            "ANXIETY",
            "HOPE",
            "FRUSTRATION",
            "NEUTRAL",
        }:
            raise StrategyV2SchemaValidationError(
                f"Agent 2 VOC observation[{index}] has invalid emotional_valence='{emotional_valence}'."
            )

        normalized_row = _enrich_voc_observation_signal(
            row={
                "voc_id": str(row_payload.get("voc_id") or f"V{index + 1:03d}"),
                "source": source,
                "quote": quote,
                "specific_number": _coerce_yes_no(row_payload.get("specific_number")),
                "specific_product_brand": _coerce_yes_no(row_payload.get("specific_product_brand")),
                "specific_event_moment": _coerce_yes_no(row_payload.get("specific_event_moment")),
                "specific_body_symptom": _coerce_yes_no(row_payload.get("specific_body_symptom")),
                "before_after_comparison": _coerce_yes_no(row_payload.get("before_after_comparison")),
                "crisis_language": _coerce_yes_no(row_payload.get("crisis_language")),
                "profanity_extreme_punctuation": _coerce_yes_no(row_payload.get("profanity_extreme_punctuation")),
                "physical_sensation": _coerce_yes_no(row_payload.get("physical_sensation")),
                "identity_change_desire": _coerce_yes_no(row_payload.get("identity_change_desire")),
                "word_count": word_count,
                "clear_trigger_event": _coerce_yes_no(row_payload.get("clear_trigger_event")),
                "named_enemy": _coerce_yes_no(row_payload.get("named_enemy")),
                "shiftable_belief": _coerce_yes_no(row_payload.get("shiftable_belief")),
                "expectation_vs_reality": _coerce_yes_no(row_payload.get("expectation_vs_reality")),
                "headline_ready": _coerce_yes_no(row_payload.get("headline_ready")),
                "usable_content_pct": usable_content_pct,
                "personal_context": _coerce_yes_no(row_payload.get("personal_context")),
                "long_narrative": _coerce_yes_no(row_payload.get("long_narrative")),
                "engagement_received": _coerce_yes_no(row_payload.get("engagement_received")),
                "real_person_signals": _coerce_yes_no(row_payload.get("real_person_signals")),
                "moderated_community": _coerce_yes_no(row_payload.get("moderated_community")),
                "trigger_event": str(row_payload.get("trigger_event") or "").strip(),
                "pain_problem": str(row_payload.get("pain_problem") or "").strip(),
                "desired_outcome": str(row_payload.get("desired_outcome") or "").strip(),
                "failed_prior_solution": str(row_payload.get("failed_prior_solution") or "").strip(),
                "enemy_blame": str(row_payload.get("enemy_blame") or "").strip(),
                "identity_role": str(row_payload.get("identity_role") or "").strip(),
                "fear_risk": str(row_payload.get("fear_risk") or "").strip(),
                "emotional_valence": emotional_valence,
                "durable_psychology": _coerce_yes_no(row_payload.get("durable_psychology")),
                "market_specific": _coerce_yes_no(row_payload.get("market_specific")),
                "date_bracket": date_bracket,
                "buyer_stage": buyer_stage,
                "solution_sophistication": solution_sophistication,
                "compliance_risk": compliance,
            }
        )
        observations.append(normalized_row)
    if not observations:
        raise StrategyV2SchemaValidationError(
            "Prompt-chain Agent 2 did not return any VOC observations."
        )
    return observations


def _derive_angle_observation_seed_from_candidate(candidate: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(candidate, Mapping):
        return {}
    evidence_payload = candidate.get("evidence")
    if not isinstance(evidence_payload, Mapping):
        return {}

    top_quotes_raw = evidence_payload.get("top_quotes")
    top_quotes = [row for row in top_quotes_raw if isinstance(row, Mapping)] if isinstance(top_quotes_raw, list) else []

    adjusted_scores: list[float] = []
    unique_voc_ids: set[str] = set()
    for row in top_quotes:
        score_value = row.get("adjusted_score")
        if isinstance(score_value, (int, float)):
            adjusted_scores.append(float(score_value))
        voc_id = str(row.get("voc_id") or "").strip()
        if voc_id:
            unique_voc_ids.add(voc_id)

    supporting_from_quotes = max(len(unique_voc_ids), len(top_quotes))
    supporting_raw = evidence_payload.get("supporting_voc_count")
    supporting_count = int(supporting_raw) if isinstance(supporting_raw, (int, float)) else 0
    supporting_count = max(supporting_count, supporting_from_quotes)

    contradiction_raw = evidence_payload.get("contradiction_count")
    contradiction_count = int(contradiction_raw) if isinstance(contradiction_raw, (int, float)) else 0
    contradiction_count = max(0, contradiction_count)

    triangulation_status = str(evidence_payload.get("triangulation_status") or "SINGLE").strip().upper()
    if triangulation_status not in {"SINGLE", "DUAL", "MULTI"}:
        triangulation_status = "SINGLE"

    velocity_status = str(evidence_payload.get("velocity_status") or "STEADY").strip().upper()
    if velocity_status not in {"ACCELERATING", "STEADY", "DECELERATING"}:
        velocity_status = "STEADY"

    avg_adjusted_score = (sum(adjusted_scores) / len(adjusted_scores)) if adjusted_scores else 0.0
    items_above_60 = sum(1 for score in adjusted_scores if score >= 60.0)
    intensity_spike_count = sum(1 for score in adjusted_scores if score >= 70.0)
    sleeping_giant_count = sum(1 for score in adjusted_scores if 55.0 <= score < 70.0)

    if supporting_count >= 9:
        competitor_count_using_angle = "6+"
    elif supporting_count >= 6:
        competitor_count_using_angle = "3-5"
    elif supporting_count >= 3:
        competitor_count_using_angle = "1-2"
    else:
        competitor_count_using_angle = "0"

    if supporting_count >= 10:
        segment_breadth = "BROAD"
        pain_universality = "UNIVERSAL"
    elif supporting_count >= 5:
        segment_breadth = "MODERATE"
        pain_universality = "MODERATE"
    else:
        segment_breadth = "NARROW"
        pain_universality = "SUBGROUP"

    if triangulation_status == "MULTI":
        source_habitat_types = 3
        dominant_source_pct = 55.0
    elif triangulation_status == "DUAL":
        source_habitat_types = 2
        dominant_source_pct = 70.0
    else:
        source_habitat_types = 1
        dominant_source_pct = 100.0

    stage_problem_aware = max(1, supporting_count // 2) if supporting_count else 0
    stage_solution_aware = max(1, supporting_count // 3) if supporting_count >= 3 else 0
    stage_product_aware = max(1, supporting_count // 4) if supporting_count >= 4 else 0

    return {
        "distinct_voc_items": supporting_count,
        "distinct_authors": max(1, min(supporting_count, len(top_quotes))) if supporting_count else 0,
        "intensity_spike_count": intensity_spike_count,
        "sleeping_giant_count": sleeping_giant_count,
        "aspiration_gap_4plus": "Y" if avg_adjusted_score >= 60.0 else "N",
        "avg_adjusted_score": round(avg_adjusted_score, 2),
        "crisis_language_count": intensity_spike_count,
        "dollar_time_loss_count": 0,
        "physical_symptom_count": 0,
        "rage_shame_anxiety_count": max(0, contradiction_count),
        "exhausted_sophistication_count": max(0, supporting_count // 4),
        "supporting_voc_count": supporting_count,
        "items_above_60": items_above_60,
        "triangulation_status": triangulation_status,
        "contradiction_count": contradiction_count,
        "source_habitat_types": source_habitat_types,
        "dominant_source_pct": dominant_source_pct,
        "green_count": max(0, supporting_count - contradiction_count),
        "yellow_count": min(supporting_count, contradiction_count),
        "red_count": 0,
        "expressible_without_red": "Y",
        "requires_disease_naming": "N",
        "velocity_status": velocity_status,
        "stage_UNAWARE_count": 0,
        "stage_PROBLEM_AWARE_count": stage_problem_aware,
        "stage_SOLUTION_AWARE_count": stage_solution_aware,
        "stage_PRODUCT_AWARE_count": stage_product_aware,
        "stage_MOST_AWARE_count": 0,
        "competitor_count_using_angle": competitor_count_using_angle,
        "recent_competitor_entry": "Y" if velocity_status == "ACCELERATING" else "N",
        "segment_breadth": segment_breadth,
        "pain_universality": pain_universality,
    }


def _normalize_angle_observations(
    raw_rows: list[dict[str, Any]],
    *,
    saturated_count: int,
    candidate_lookup: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    candidate_lookup_map: dict[str, Mapping[str, Any]] = {}
    if isinstance(candidate_lookup, Mapping):
        for angle_id, row in candidate_lookup.items():
            if isinstance(angle_id, str) and angle_id.strip() and isinstance(row, Mapping):
                candidate_lookup_map[angle_id.strip()] = row

    merged_rows: list[dict[str, Any]] = []
    seen_angle_ids: set[str] = set()
    for index, raw_row in enumerate(raw_rows):
        row = dict(raw_row)
        angle_id = str(row.get("angle_id") or "").strip() or f"A{index + 1:02d}"
        row["angle_id"] = angle_id
        candidate_seed = _derive_angle_observation_seed_from_candidate(candidate_lookup_map.get(angle_id))
        merged_row = {**candidate_seed, **row}
        if not str(merged_row.get("angle_name") or "").strip():
            candidate_name = candidate_lookup_map.get(angle_id, {}).get("angle_name")
            merged_row["angle_name"] = str(candidate_name or f"Angle {index + 1}")
        merged_rows.append(merged_row)
        seen_angle_ids.add(angle_id)

    for angle_id, candidate in candidate_lookup_map.items():
        if angle_id in seen_angle_ids:
            continue
        seed = _derive_angle_observation_seed_from_candidate(candidate)
        merged_rows.append(
            {
                **seed,
                "angle_id": angle_id,
                "angle_name": str(candidate.get("angle_name") or f"Angle {len(merged_rows) + 1}"),
            }
        )

    observations: list[dict[str, Any]] = []
    for index, row in enumerate(merged_rows):
        obs: dict[str, Any] = {
            "angle_id": str(row.get("angle_id") or f"A{index + 1:02d}"),
            "angle_name": str(row.get("angle_name") or f"Angle {index + 1}"),
            "distinct_voc_items": int(row.get("distinct_voc_items") or 0),
            "distinct_authors": int(row.get("distinct_authors") or 0),
            "intensity_spike_count": int(row.get("intensity_spike_count") or 0),
            "sleeping_giant_count": int(row.get("sleeping_giant_count") or 0),
            "aspiration_gap_4plus": _coerce_yes_no(row.get("aspiration_gap_4plus")),
            "avg_adjusted_score": float(row.get("avg_adjusted_score") or 0.0),
            "crisis_language_count": int(row.get("crisis_language_count") or 0),
            "dollar_time_loss_count": int(row.get("dollar_time_loss_count") or 0),
            "physical_symptom_count": int(row.get("physical_symptom_count") or 0),
            "rage_shame_anxiety_count": int(row.get("rage_shame_anxiety_count") or 0),
            "exhausted_sophistication_count": int(row.get("exhausted_sophistication_count") or 0),
            "product_addresses_pain": _coerce_yes_no(row.get("product_addresses_pain"), default="Y"),
            "product_feature_maps_to_mechanism": _coerce_yes_no(
                row.get("product_feature_maps_to_mechanism"), default="Y"
            ),
            "outcome_achievable": _coerce_yes_no(row.get("outcome_achievable"), default="Y"),
            "mechanism_factually_supportable": _coerce_yes_no(
                row.get("mechanism_factually_supportable"), default="Y"
            ),
            "supporting_voc_count": int(row.get("supporting_voc_count") or 0),
            "items_above_60": int(row.get("items_above_60") or 0),
            "triangulation_status": str(row.get("triangulation_status") or "SINGLE"),
            "contradiction_count": int(row.get("contradiction_count") or 0),
            "source_habitat_types": int(row.get("source_habitat_types") or 1),
            "dominant_source_pct": float(row.get("dominant_source_pct") or 100.0),
            "green_count": int(row.get("green_count") or 0),
            "yellow_count": int(row.get("yellow_count") or 0),
            "red_count": int(row.get("red_count") or 0),
            "expressible_without_red": _coerce_yes_no(row.get("expressible_without_red"), default="Y"),
            "requires_disease_naming": _coerce_yes_no(row.get("requires_disease_naming"), default="N"),
            "velocity_status": str(row.get("velocity_status") or "STEADY"),
            "stage_UNAWARE_count": int(row.get("stage_UNAWARE_count") or 0),
            "stage_PROBLEM_AWARE_count": int(row.get("stage_PROBLEM_AWARE_count") or 0),
            "stage_SOLUTION_AWARE_count": int(row.get("stage_SOLUTION_AWARE_count") or 0),
            "stage_PRODUCT_AWARE_count": int(row.get("stage_PRODUCT_AWARE_count") or 0),
            "stage_MOST_AWARE_count": int(row.get("stage_MOST_AWARE_count") or 0),
            "pain_chronicity": str(row.get("pain_chronicity") or "CHRONIC"),
            "trigger_seasonality": str(row.get("trigger_seasonality") or "ONGOING"),
            "competitor_count_using_angle": str(row.get("competitor_count_using_angle") or "1-2"),
            "recent_competitor_entry": _coerce_yes_no(row.get("recent_competitor_entry"), default="N"),
            "pain_structural": _coerce_yes_no(row.get("pain_structural"), default="Y"),
            "news_cycle_dependent": _coerce_yes_no(row.get("news_cycle_dependent"), default="N"),
            "competitor_behavior_dependent": _coerce_yes_no(row.get("competitor_behavior_dependent"), default="N"),
            "single_visual_expressible": _coerce_yes_no(row.get("single_visual_expressible"), default="Y"),
            "hook_under_12_words": _coerce_yes_no(row.get("hook_under_12_words"), default="Y"),
            "natural_villain_present": _coerce_yes_no(row.get("natural_villain_present"), default="Y"),
            "language_registry_headline_exists": _coerce_yes_no(
                row.get("language_registry_headline_exists"), default="Y"
            ),
            "segment_breadth": str(row.get("segment_breadth") or "MODERATE"),
            "pain_universality": str(row.get("pain_universality") or "MODERATE"),
        }
        for saturated_idx in range(saturated_count):
            obs[f"sa{saturated_idx}_different_who"] = _coerce_yes_no(
                row.get(f"sa{saturated_idx}_different_who"),
                default="Y" if saturated_idx == 0 else "N",
            )
            obs[f"sa{saturated_idx}_different_trigger"] = _coerce_yes_no(
                row.get(f"sa{saturated_idx}_different_trigger"),
                default="Y" if saturated_idx == 0 else "N",
            )
            obs[f"sa{saturated_idx}_different_enemy"] = _coerce_yes_no(
                row.get(f"sa{saturated_idx}_different_enemy"),
                default="Y" if saturated_idx == 0 else "N",
            )
            obs[f"sa{saturated_idx}_different_belief"] = _coerce_yes_no(
                row.get(f"sa{saturated_idx}_different_belief"),
                default="Y" if saturated_idx == 0 else "N",
            )
            obs[f"sa{saturated_idx}_different_mechanism"] = _coerce_yes_no(
                row.get(f"sa{saturated_idx}_different_mechanism"),
                default="Y" if saturated_idx == 0 else "N",
            )
        observations.append(obs)
    if not observations:
        raise StrategyV2SchemaValidationError(
            "Prompt-chain Agent 3 did not return angle observations."
        )
    return observations


def _normalize_angle_candidates(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in raw_rows:
        candidate = SelectedAngleContract.model_validate(row)
        candidate_payload = candidate.model_dump(mode="python")
        evidence_payload = candidate_payload.get("evidence")
        if isinstance(evidence_payload, dict):
            top_quotes = evidence_payload.get("top_quotes")
            if isinstance(top_quotes, list):
                # Keep evidence density internally consistent with the quoted VOC rows.
                derived_supporting_voc_count = len(
                    {
                        str(quote_row.get("voc_id") or "").strip()
                        for quote_row in top_quotes
                        if isinstance(quote_row, dict) and str(quote_row.get("voc_id") or "").strip()
                    }
                )
                current_supporting_voc_count = int(evidence_payload.get("supporting_voc_count") or 0)
                evidence_payload["supporting_voc_count"] = max(
                    current_supporting_voc_count,
                    derived_supporting_voc_count,
                )
        candidates.append(candidate_payload)
    if not candidates:
        raise StrategyV2SchemaValidationError(
            "Prompt-chain Agent 3 did not return any angle candidates."
        )
    return candidates


def _dump_prompt_json(payload: object, *, max_chars: int) -> str:
    serialized = json.dumps(payload, ensure_ascii=True, indent=2)
    if len(serialized) <= max_chars:
        return serialized
    return serialized[:max_chars]


def _resolve_price_from_reference_urls(*, urls: list[str]) -> str:
    cleaned_urls = [str(url).strip() for url in urls if isinstance(url, str) and str(url).strip()]
    if not cleaned_urls:
        raise StrategyV2MissingContextError(
            "Unable to resolve fallback offer price because competitor URLs are missing. "
            "Remediation: provide at least one valid competitor URL in stage2.competitor_urls."
        )

    request_errors: list[str] = []
    price_candidates: list[tuple[float, str]] = []
    for url in cleaned_urls:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; marketi-strategy-v2/1.0)",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                html = response.read().decode("utf-8", errors="ignore")
        except Exception as exc:
            request_errors.append(f"{url}: {exc}")
            continue

        text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
        text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue

        for match in re.finditer(r"\$\s*([0-9]{1,5}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)", text):
            raw_amount = match.group(1).replace(",", "")
            try:
                amount = float(raw_amount)
            except ValueError:
                continue
            context_window = text[max(0, match.start() - 42) : min(len(text), match.end() + 42)].lower()
            if any(
                token in context_window
                for token in ("shipping", "ship", "delivery", "tax", "fee", "installment", "/mo", "per month")
            ):
                continue
            rendered_amount = f"${int(amount)}" if amount.is_integer() else f"${amount:.2f}".rstrip("0").rstrip(".")
            price_candidates.append((amount, rendered_amount))

    if price_candidates:
        return sorted(price_candidates, key=lambda item: item[0], reverse=True)[0][1]

    if request_errors:
        raise StrategyV2MissingContextError(
            "Unable to resolve fallback offer price from competitor URLs. "
            f"Remediation: ensure at least one reference URL is reachable and contains offer pricing. "
            f"Request errors: {request_errors}"
        )

    raise StrategyV2MissingContextError(
        "Unable to resolve fallback offer price from competitor URLs because no non-shipping $amount "
        "patterns were detected. Remediation: provide explicit stage2.price or competitor pages with "
        "visible offer pricing."
    )


def _map_offer_pipeline_input_with_price_resolution(
    *,
    stage2: ProductBriefStage2,
    selected_angle_payload: Mapping[str, object],
    competitor_teardowns: str,
    voc_research: str,
    purple_ocean_research: str,
    business_model: str,
    funnel_position: str,
    target_platforms: list[str],
    target_regions: list[str],
    existing_proof_assets: list[str],
    brand_voice_notes: str,
    compliance_sensitivity: str,
    llm_model: str,
    max_iterations: int,
    score_threshold: float,
):
    def _map_with_stage2(stage2_payload: ProductBriefStage2) -> Any:
        return map_offer_pipeline_input(
            stage2=stage2_payload,
            selected_angle_payload=selected_angle_payload,
            competitor_teardowns=competitor_teardowns,
            voc_research=voc_research,
            purple_ocean_research=purple_ocean_research,
            business_model=business_model,
            funnel_position=funnel_position,
            target_platforms=target_platforms,
            target_regions=target_regions,
            existing_proof_assets=existing_proof_assets,
            brand_voice_notes=brand_voice_notes,
            compliance_sensitivity=compliance_sensitivity,
            llm_model=llm_model,
            max_iterations=max_iterations,
            score_threshold=score_threshold,
        )

    try:
        return _map_with_stage2(stage2)
    except StrategyV2MissingContextError:
        if str(stage2.price or "").strip().upper() != "TBD":
            raise
        resolved_price = _resolve_price_from_reference_urls(urls=list(stage2.competitor_urls))
        resolved_stage2 = stage2.model_copy(update={"price": resolved_price})
        return _map_with_stage2(resolved_stage2)


_AWARENESS_LEVEL_KEYS = (
    "unaware",
    "problem_aware",
    "solution_aware",
    "product_aware",
    "most_aware",
)
_AWARENESS_REQUIRED_FIELDS = (
    "frame",
    "headline_direction",
    "entry_emotion",
    "exit_belief",
)


def _normalize_awareness_level_framing(
    *,
    awareness_level_key: str,
    payload: object,
) -> dict[str, str]:
    framing = _require_dict(payload=payload, field_name=f"awareness_framing.{awareness_level_key}")
    normalized: dict[str, str] = {}
    missing_fields: list[str] = []
    for field_name in _AWARENESS_REQUIRED_FIELDS:
        raw_value = framing.get(field_name)
        if isinstance(raw_value, str) and raw_value.strip():
            normalized[field_name] = raw_value.strip()
            continue
        missing_fields.append(field_name)
    if missing_fields:
        raise StrategyV2SchemaValidationError(
            f"awareness_framing.{awareness_level_key} is missing required fields: {missing_fields}. "
            "Remediation: regenerate Step 02 awareness matrix with fully populated framing rows."
        )
    return normalized


def _validate_awareness_angle_matrix_payload(*, payload: object) -> AwarenessAngleMatrix:
    matrix = _require_dict(payload=payload, field_name="awareness_angle_matrix")
    angle_name = str(matrix.get("angle_name") or "").strip()
    if not angle_name:
        raise StrategyV2SchemaValidationError(
            "awareness_angle_matrix.angle_name is required and must be non-empty."
        )
    awareness_framing_raw = _require_dict(
        payload=matrix.get("awareness_framing"),
        field_name="awareness_angle_matrix.awareness_framing",
    )
    awareness_framing: dict[str, dict[str, str]] = {}
    for awareness_level_key in _AWARENESS_LEVEL_KEYS:
        awareness_framing[awareness_level_key] = _normalize_awareness_level_framing(
            awareness_level_key=awareness_level_key,
            payload=awareness_framing_raw.get(awareness_level_key),
        )
    constant_elements = [
        item.strip()
        for item in (matrix.get("constant_elements") or [])
        if isinstance(item, str) and item.strip()
    ]
    variable_elements = [
        item.strip()
        for item in (matrix.get("variable_elements") or [])
        if isinstance(item, str) and item.strip()
    ]
    product_name_first_appears_raw = matrix.get("product_name_first_appears")
    product_name_first_appears = (
        str(product_name_first_appears_raw).strip()
        if isinstance(product_name_first_appears_raw, str) and product_name_first_appears_raw.strip()
        else None
    )
    return AwarenessAngleMatrix.model_validate(
        {
            "angle_name": angle_name,
            "awareness_framing": awareness_framing,
            "constant_elements": constant_elements,
            "variable_elements": variable_elements,
            "product_name_first_appears": product_name_first_appears,
        }
    )


@activity.defn(name="strategy_v2.ensure_workflow_run")
def ensure_strategy_v2_workflow_run_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    temporal_workflow_id = str(params["temporal_workflow_id"])
    temporal_run_id = str(params["temporal_run_id"])

    with session_scope() as session:
        workflows_repo = WorkflowsRepository(session)
        existing = workflows_repo.get_by_temporal_ids(
            org_id=org_id,
            temporal_workflow_id=temporal_workflow_id,
            temporal_run_id=temporal_run_id,
        )
        run = existing or workflows_repo.create_run(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            temporal_workflow_id=temporal_workflow_id,
            temporal_run_id=temporal_run_id,
            kind="strategy_v2",
        )
        workflows_repo.log_activity(
            workflow_run_id=str(run.id),
            step="strategy_v2",
            status="started",
            payload_in={
                "client_id": client_id,
                "product_id": product_id,
                "campaign_id": campaign_id,
            },
        )
        return {"workflow_run_id": str(run.id)}


@activity.defn(name="strategy_v2.build_stage0")
def build_strategy_v2_stage0_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    workflow_run_id = str(params["workflow_run_id"])
    onboarding_payload_id = str(params["onboarding_payload_id"]) if isinstance(params.get("onboarding_payload_id"), str) else None
    stage0_overrides = _require_dict(payload=params.get("stage0_overrides", {}), field_name="stage0_overrides")
    operator_user_id = str(params.get("operator_user_id") or "system")

    with session_scope() as session:
        product = _load_product(session, org_id=org_id, client_id=client_id, product_id=product_id)
        onboarding_payload = _load_onboarding_payload(
            session=session,
            org_id=org_id,
            client_id=client_id,
            onboarding_payload_id=onboarding_payload_id,
        )

        stage0 = translate_stage0(
            product_name=str(product.title) if product.title else None,
            product_description=str(product.description) if product.description else None,
            onboarding_payload=onboarding_payload,
            stage0_overrides=stage0_overrides,
        )
        stage0_data = stage0.model_dump(mode="python")

        artifacts_repo = ArtifactsRepository(session)
        stage0_artifact = artifacts_repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.strategy_v2_stage0,
            data=stage0_data,
        )

        agent_run_id = _record_agent_run(
            session=session,
            org_id=org_id,
            user_id=operator_user_id,
            client_id=client_id,
            objective_type="strategy_v2.stage0_translation",
            model="deterministic",
            inputs_json={"stage0_overrides": stage0_overrides},
            outputs_json=stage0_data,
        )
        step_payload_artifact_id = _persist_step_payload(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            workflow_run_id=workflow_run_id,
            step_key=V2_STEP_STAGE0_BUILD,
            title="Strategy V2 Stage 0 Build",
            summary="Stage 0 product brief contract generated and validated.",
            payload={"stage0": stage0_data, "stage0_artifact_id": str(stage0_artifact.id)},
            model_name="deterministic",
            prompt_version="strategy_v2.stage0.v1",
            schema_version=SCHEMA_VERSION_V2,
            agent_run_id=agent_run_id,
        )

        return {
            "stage0": stage0_data,
            "stage0_artifact_id": str(stage0_artifact.id),
            "step_payload_artifact_id": step_payload_artifact_id,
            "agent_run_id": agent_run_id,
        }


def _require_foundational_step_contents(*, precanon_research: Mapping[str, Any]) -> dict[str, str]:
    step_contents_raw = _require_dict(
        payload=precanon_research.get("step_contents"),
        field_name="precanon_research.step_contents",
    )
    step_contents: dict[str, str] = {}
    for step_key in _FOUNDATIONAL_STEP_KEYS:
        content = step_contents_raw.get(step_key)
        if not isinstance(content, str) or not content.strip():
            raise StrategyV2MissingContextError(
                f"Missing foundational step content '{step_key}' required for traceable artifact persistence. "
                f"Remediation: rerun foundational research and include step {step_key} output in "
                "precanon_research.step_contents."
            )
        step_contents[step_key] = content
    return step_contents


def _persist_foundational_step_payloads(
    *,
    session,
    org_id: str,
    client_id: str,
    product_id: str,
    campaign_id: str | None,
    workflow_run_id: str,
    step_contents: Mapping[str, str],
    step_summaries: Mapping[str, Any],
) -> dict[str, str]:
    persisted_ids: dict[str, str] = {}
    for step_key in sorted(step_contents.keys()):
        metadata = _FOUNDATIONAL_STEP_ARTIFACT_META.get(
            step_key,
            {
                "title": f"Strategy V2 Foundational Step {step_key} Raw Output",
                "summary": f"Raw foundational output for step {step_key}.",
            },
        )
        payload: dict[str, Any] = {
            "foundational_step_key": step_key,
            "source": "precanon_research.step_contents",
            "content": step_contents[step_key],
        }
        bounded_summary = step_summaries.get(step_key)
        if isinstance(bounded_summary, str) and bounded_summary.strip():
            payload["bounded_summary"] = bounded_summary.strip()

        persisted_ids[f"v2-02.foundation.{step_key}"] = _persist_step_payload(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            workflow_run_id=workflow_run_id,
            step_key=f"v2-02.foundation.{step_key}",
            title=metadata["title"],
            summary=metadata["summary"],
            payload=payload,
            model_name="deterministic",
            prompt_version="strategy_v2.foundation_artifact_persist.v1",
            schema_version=SCHEMA_VERSION_V2,
            agent_run_id=None,
        )
    return persisted_ids


@activity.defn(name="strategy_v2.build_foundational_research")
def build_strategy_v2_foundational_research_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    workflow_run_id = str(params["workflow_run_id"])
    onboarding_payload_id = (
        str(params["onboarding_payload_id"])
        if isinstance(params.get("onboarding_payload_id"), str)
        else None
    )
    stage0 = ProductBriefStage0.model_validate(_require_dict(payload=params["stage0"], field_name="stage0"))
    provided_precanon_research = params.get("precanon_research")
    precanon_research: dict[str, Any] | None = (
        _require_dict(payload=provided_precanon_research, field_name="precanon_research")
        if provided_precanon_research is not None
        else None
    )
    provided_stage1_payload = params.get("stage1")
    provided_stage1_artifact_id = (
        str(params["stage1_artifact_id"])
        if isinstance(params.get("stage1_artifact_id"), str) and str(params.get("stage1_artifact_id")).strip()
        else None
    )
    existing_step_payload_artifact_ids_raw = params.get("existing_step_payload_artifact_ids")
    existing_step_payload_artifact_ids: dict[str, str] = {}
    if isinstance(existing_step_payload_artifact_ids_raw, dict):
        for key, value in existing_step_payload_artifact_ids_raw.items():
            if isinstance(key, str) and isinstance(value, str) and value.strip():
                existing_step_payload_artifact_ids[key] = value.strip()
    apify_context_raw = params.get("apify_context")
    apify_context: dict[str, Any] = (
        _require_dict(payload=apify_context_raw, field_name="apify_context")
        if apify_context_raw is not None
        else {}
    )

    with session_scope() as session:
        if precanon_research is None:
            onboarding_payload = _load_onboarding_payload(
                session=session,
                org_id=org_id,
                client_id=client_id,
                onboarding_payload_id=onboarding_payload_id,
            )
            if not onboarding_payload:
                raise StrategyV2MissingContextError(
                    "Strategy V2 requires onboarding payload context when precomputed research is not provided. "
                    "Remediation: provide onboarding_payload_id or pass explicit precanon_research payload."
                )
            product = _load_product(session, org_id=org_id, client_id=client_id, product_id=product_id)
            precanon_research = _run_foundational_research_without_step02(
                stage0=stage0,
                onboarding_payload=onboarding_payload,
                product=product,
                workflow_run_id=workflow_run_id,
            )

        step_contents_raw = _require_dict(
            payload=precanon_research.get("step_contents"),
            field_name="precanon_research.step_contents",
        )
        foundational_keys = ("01", "03", "04", "06")
        foundational_step_contents: dict[str, str] = {}
        for step_key in foundational_keys:
            content = step_contents_raw.get(step_key)
            if not isinstance(content, str) or not content.strip():
                raise StrategyV2MissingContextError(
                    f"Missing foundational step content '{step_key}' required for H1 review. "
                    "Remediation: rerun foundational research and include steps 01/03/04/06."
                )
            foundational_step_contents[step_key] = content

        foundational_step_summaries = _require_dict(
            payload=precanon_research.get("step_summaries", {}),
            field_name="precanon_research.step_summaries",
        )

        stage1 = translate_stage1(
            stage0=stage0,
            precanon_research={
                "category_niche": precanon_research.get("category_niche"),
                "step_contents": {
                    "01": foundational_step_contents["01"],
                    "06": foundational_step_contents["06"],
                },
            },
        )
        _require_stage1_quality(stage1)
        stage1_data = stage1.model_dump(mode="python")

        artifacts_repo = ArtifactsRepository(session)
        stage1_artifact = artifacts_repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.strategy_v2_stage1,
            data=stage1_data,
        )
        foundational_step_payload_artifact_ids = _persist_foundational_step_payloads(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            workflow_run_id=workflow_run_id,
            step_contents=foundational_step_contents,
            step_summaries=foundational_step_summaries,
        )

        return {
            "stage1": stage1_data,
            "stage1_artifact_id": str(stage1_artifact.id),
            "precanon_research": {
                "category_niche": precanon_research.get("category_niche"),
                "step_summaries": dict(foundational_step_summaries),
                "step_contents": dict(foundational_step_contents),
                "asset_data_context": (
                    precanon_research.get("asset_data_context")
                    if isinstance(precanon_research.get("asset_data_context"), dict)
                    else None
                ),
            },
            "step_payload_artifact_ids": foundational_step_payload_artifact_ids,
        }


@activity.defn(name="strategy_v2.run_voc_angle_pipeline")
def run_strategy_v2_voc_angle_pipeline_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    onboarding_payload_id = (
        str(params["onboarding_payload_id"])
        if isinstance(params.get("onboarding_payload_id"), str)
        else None
    )
    workflow_run_id = str(params["workflow_run_id"])
    operator_user_id = str(params.get("operator_user_id") or "system")
    confirmed_competitor_assets_raw = params.get("confirmed_competitor_assets")
    if not isinstance(confirmed_competitor_assets_raw, list):
        raise StrategyV2MissingContextError(
            "confirmed_competitor_assets is required for Strategy V2 Stage 2A parity. "
            "Remediation: complete H2 and pass 3+ confirmed competitor asset refs."
        )
    confirmed_competitor_assets = [
        str(item).strip()
        for item in confirmed_competitor_assets_raw
        if isinstance(item, str) and item.strip()
    ]
    if len(confirmed_competitor_assets) < 3:
        raise StrategyV2MissingContextError(
            "Strategy V2 requires at least 3 confirmed competitor assets before Stage 2A analysis. "
            "Remediation: complete H2 with 3+ asset references."
        )
    stage0 = ProductBriefStage0.model_validate(_require_dict(payload=params["stage0"], field_name="stage0"))
    provided_precanon_research = params.get("precanon_research")
    precanon_research: dict[str, Any] | None = (
        _require_dict(payload=provided_precanon_research, field_name="precanon_research")
        if provided_precanon_research is not None
        else None
    )
    provided_stage1_payload = params.get("stage1")
    provided_stage1_artifact_id = (
        str(params["stage1_artifact_id"])
        if isinstance(params.get("stage1_artifact_id"), str) and str(params.get("stage1_artifact_id")).strip()
        else None
    )
    existing_step_payload_artifact_ids_raw = params.get("existing_step_payload_artifact_ids")
    existing_step_payload_artifact_ids: dict[str, str] = {}
    if isinstance(existing_step_payload_artifact_ids_raw, dict):
        for key, value in existing_step_payload_artifact_ids_raw.items():
            if isinstance(key, str) and isinstance(value, str) and value.strip():
                existing_step_payload_artifact_ids[key] = value.strip()
    apify_context_raw = params.get("apify_context")
    apify_context: dict[str, Any] = (
        _require_dict(payload=apify_context_raw, field_name="apify_context")
        if apify_context_raw is not None
        else {}
    )

    with session_scope() as session:
        activity.heartbeat(
            {
                "activity": "strategy_v2.run_voc_angle_pipeline",
                "phase": "post_stage0_init",
                "status": "started",
            }
        )
        if precanon_research is None:
            onboarding_payload = _load_onboarding_payload(
                session=session,
                org_id=org_id,
                client_id=client_id,
                onboarding_payload_id=onboarding_payload_id,
            )
            if not onboarding_payload:
                raise StrategyV2MissingContextError(
                    "Strategy V2 requires onboarding payload context when precomputed research is not provided. "
                    "Remediation: provide onboarding_payload_id or pass explicit precanon_research payload."
                )
            product = _load_product(session, org_id=org_id, client_id=client_id, product_id=product_id)
            precanon_research = _run_foundational_research_from_onboarding(
                stage0=stage0,
                onboarding_payload=onboarding_payload,
                product=product,
                workflow_run_id=workflow_run_id,
                confirmed_competitor_assets=confirmed_competitor_assets,
            )
        if not apify_context and isinstance(precanon_research.get("asset_data_context"), dict):
            apify_context = dict(precanon_research.get("asset_data_context") or {})
        social_video_rows = apify_context.get("social_video_observations")
        external_voc_rows = apify_context.get("external_voc_corpus")
        needs_social_refresh = not isinstance(social_video_rows, list) or len(social_video_rows) == 0
        needs_external_refresh = not isinstance(external_voc_rows, list) or len(external_voc_rows) == 0
        if needs_social_refresh or needs_external_refresh:
            source_refs = list(stage0.competitor_urls) + confirmed_competitor_assets
            scrapeable_source_refs, excluded_source_refs = _partition_source_refs_for_ingestion(
                [ref for ref in source_refs if isinstance(ref, str) and ref.strip()]
            )
            apify_context = _ingest_strategy_v2_asset_data(
                source_refs=scrapeable_source_refs,
                include_ads_context=False,
                include_social_video=needs_social_refresh,
                include_external_voc=needs_external_refresh,
            )
            apify_context["ingestion_source_refs"] = scrapeable_source_refs
            apify_context["excluded_source_refs"] = excluded_source_refs
        activity.heartbeat(
            {
                "activity": "strategy_v2.run_voc_angle_pipeline",
                "phase": "foundation",
                "status": "completed",
            }
        )

        step_contents_raw = _require_dict(
            payload=precanon_research.get("step_contents"),
            field_name="precanon_research.step_contents",
        )
        has_step02 = isinstance(step_contents_raw.get("02"), str) and str(step_contents_raw.get("02")).strip() != ""
        if not has_step02:
            step1_content_raw = step_contents_raw.get("01")
            if not isinstance(step1_content_raw, str) or not step1_content_raw.strip():
                raise StrategyV2MissingContextError(
                    "Foundational step 01 content is missing; cannot generate competitor analysis for step 02. "
                    "Remediation: rerun foundational stage and persist step 01 output."
                )
            step_summaries_raw = _require_dict(
                payload=precanon_research.get("step_summaries", {}),
                field_name="precanon_research.step_summaries",
            )
            step1_summary = (
                str(step_summaries_raw.get("01")).strip()
                if isinstance(step_summaries_raw.get("01"), str)
                else step1_content_raw[:2000]
            )
            category_match = re.search(r"(?im)^\s*category\s*/\s*niche\s*:\s*(.+)$", step1_content_raw)
            category_niche = category_match.group(1).strip() if category_match else stage0.product_name
            competitor_analysis_generated = _generate_competitor_analysis_json(
                stage0=stage0,
                category_niche=category_niche,
                step1_summary=step1_summary,
                step1_content=step1_content_raw,
                confirmed_competitor_assets=confirmed_competitor_assets,
            )
            updated_step_contents = dict(step_contents_raw)
            updated_step_contents["02"] = json.dumps(competitor_analysis_generated, ensure_ascii=True)
            updated_step_summaries = dict(step_summaries_raw)
            updated_step_summaries["02"] = (
                f"competitors={len(competitor_analysis_generated.get('competitor_urls', []))}; "
                f"assets={len(competitor_analysis_generated.get('asset_observation_sheets', []))}"
            )
            precanon_research = dict(precanon_research)
            precanon_research["step_contents"] = updated_step_contents
            precanon_research["step_summaries"] = updated_step_summaries

        foundational_step_contents = _require_foundational_step_contents(precanon_research=precanon_research)
        foundational_step_summaries = _require_dict(
            payload=precanon_research.get("step_summaries", {}),
            field_name="precanon_research.step_summaries",
        )
        foundational_step_payload_artifact_ids = dict(existing_step_payload_artifact_ids)
        missing_step_contents = {
            step_key: content
            for step_key, content in foundational_step_contents.items()
            if f"v2-02.foundation.{step_key}" not in foundational_step_payload_artifact_ids
        }
        if missing_step_contents:
            foundational_step_payload_artifact_ids.update(
                _persist_foundational_step_payloads(
                    session=session,
                    org_id=org_id,
                    client_id=client_id,
                    product_id=product_id,
                    campaign_id=campaign_id,
                    workflow_run_id=workflow_run_id,
                    step_contents=missing_step_contents,
                    step_summaries=foundational_step_summaries,
                )
            )

        if provided_stage1_payload is not None:
            stage1 = ProductBriefStage1.model_validate(
                _require_dict(payload=provided_stage1_payload, field_name="stage1")
            )
        else:
            stage1 = translate_stage1(stage0=stage0, precanon_research=precanon_research)
        _require_stage1_quality(stage1)
        stage1_data = stage1.model_dump(mode="python")
        activity.heartbeat(
            {
                "activity": "strategy_v2.run_voc_angle_pipeline",
                "phase": "stage1",
                "status": "translated",
            }
        )

        artifacts_repo = ArtifactsRepository(session)
        if provided_stage1_artifact_id:
            stage1_artifact_id = provided_stage1_artifact_id
        else:
            stage1_artifact = artifacts_repo.insert(
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                artifact_type=ArtifactTypeEnum.strategy_v2_stage1,
                data=stage1_data,
            )
            stage1_artifact_id = str(stage1_artifact.id)
        activity.heartbeat(
            {
                "activity": "strategy_v2.run_voc_angle_pipeline",
                "phase": "stage1",
                "status": "artifact_persisted",
                "artifact_id": stage1_artifact_id,
            }
        )

        if True:
            step4_content = foundational_step_contents["04"].strip()
            entries = _extract_step4_entries(step4_content)
            competitor_analysis = extract_competitor_analysis(precanon_research)
            step4_corpus = transform_step4_entries_to_agent2_corpus(entries)
            external_voc_corpus_raw = apify_context.get("external_voc_corpus")
            external_voc_corpus = (
                [row for row in external_voc_corpus_raw if isinstance(row, dict)]
                if isinstance(external_voc_corpus_raw, list)
                else []
            )
            merged_voc = _merge_voc_corpus_for_agent2(
                step4_rows=step4_corpus,
                external_rows=external_voc_corpus,
            )
            existing_corpus = merged_voc["prompt_rows"]
            merged_voc_artifact_rows = merged_voc["artifact_rows"]
            proof_asset_candidates_raw = apify_context.get("proof_asset_candidates")
            proof_asset_candidates = (
                [row for row in proof_asset_candidates_raw if isinstance(row, dict)]
                if isinstance(proof_asset_candidates_raw, list)
                else []
            )
            if not proof_asset_candidates:
                proof_asset_candidates = _build_proof_candidates_from_voc(
                    voc_rows=merged_voc_artifact_rows,
                    competitor_analysis=competitor_analysis,
                )
            activity.heartbeat(
                {
                    "activity": "strategy_v2.run_voc_angle_pipeline",
                    "phase": "prompt_chain",
                    "status": "enabled",
                    "entry_count": len(entries),
                }
            )
            avatar_brief_payload = _build_avatar_brief_runtime_payload(
                step6_content=foundational_step_contents["06"],
                step6_summary=str(foundational_step_summaries.get("06") or ""),
            )
            product_category_keywords = _require_stage1_product_category_keywords(stage1)

            agent00_asset = resolve_prompt_asset(
                pattern=_VOC_AGENT00_PROMPT_PATTERN,
                context="VOC Agent 0 habitat strategist",
            )
            agent00_output, agent00_raw, agent00_provenance = _run_prompt_json_object(
                asset=agent00_asset,
                context="strategy_v2.agent0_output",
                model=settings.STRATEGY_V2_VOC_MODEL,
                runtime_instruction=(
                    "## Runtime Input Block\n"
                    f"PRODUCT_BRIEF:\n{_dump_prompt_json(stage1_data, max_chars=12000)}\n\n"
                    f"AVATAR_BRIEF:\n{_dump_prompt_json(avatar_brief_payload, max_chars=12000)}\n\n"
                    f"AVATAR_BRIEF_SUMMARY:\n{str(foundational_step_summaries.get('06') or '')[:4000]}\n\n"
                    f"COMPETITOR_RESEARCH_SUMMARY:\n{str(foundational_step_summaries.get('01') or '')[:6000]}\n\n"
                    f"COMPETITOR_ANALYSIS:\n{_dump_prompt_json(competitor_analysis, max_chars=16000)}\n\n"
                    "Output a strict JSON object with strategy_habitats and optional manual_queries."
                ),
                schema_name="strategy_v2_voc_agent00",
                schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "category_classification": {"type": "object", "additionalProperties": True},
                        "strategy_habitats": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                                "properties": {
                                    "habitat_name": {"type": "string", "minLength": 1},
                                    "habitat_type": {"type": "string", "minLength": 1},
                                    "url_pattern": {"type": "string", "minLength": 1},
                                },
                                "required": ["habitat_name", "habitat_type", "url_pattern"],
                            },
                        },
                        "manual_queries": {"type": "array", "items": {"type": "string", "minLength": 1}},
                        "handoff_block": {"type": "string"},
                    },
                    "required": ["strategy_habitats"],
                },
                use_reasoning=True,
                use_web_search=False,
                heartbeat_context={
                    "activity": "strategy_v2.run_voc_angle_pipeline",
                    "phase": "agent0_prompt",
                    "model": settings.STRATEGY_V2_VOC_MODEL,
                },
            )
            _raise_if_blocked_prompt_output(
                stage_label="v2-02 Agent 0 habitat strategist",
                parsed_output=agent00_output,
                raw_output=agent00_raw,
                remediation=(
                    "provide complete PRODUCT_BRIEF, AVATAR_BRIEF, and COMPETITOR_ANALYSIS "
                    "inputs before rerunning v2-02."
                ),
            )
            habitat_strategy_payload = {
                "category_niche": stage1.category_niche,
                "competitor_urls": stage1.competitor_urls,
                "source_count": len({entry["source"] for entry in entries}),
                "foundational_step_summaries": {
                    key: value
                    for key, value in foundational_step_summaries.items()
                    if key in {"01", "03", "04", "06"} and isinstance(value, str)
                },
                "agent_output": agent00_output,
                "prompt_provenance": agent00_provenance,
                "raw_output": agent00_raw[:20000],
            }
            habitat_agent_run_id = _record_agent_run(
                session=session,
                org_id=org_id,
                user_id=operator_user_id,
                client_id=client_id,
                objective_type="strategy_v2.agent0_habitat_strategy.prompt_chain",
                model=settings.STRATEGY_V2_VOC_MODEL,
                inputs_json={"stage1": stage1_data},
                outputs_json=habitat_strategy_payload,
            )
            v2_02_step_payload_artifact_id = _persist_step_payload(
                session=session,
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                workflow_run_id=workflow_run_id,
                step_key=V2_STEP_HABITAT_STRATEGY,
                title="Strategy V2 Habitat Strategy",
                summary="Agent 0 prompt-chain habitat strategy prepared from foundational context.",
                payload=habitat_strategy_payload,
                model_name=settings.STRATEGY_V2_VOC_MODEL,
                prompt_version="strategy_v2.agent0.prompt_chain.v2",
                schema_version=SCHEMA_VERSION_V2,
                agent_run_id=habitat_agent_run_id,
            )

            agent00b_asset = resolve_prompt_asset(
                pattern=_VOC_AGENT00B_PROMPT_PATTERN,
                context="VOC Agent 0b social video strategist",
            )
            agent00b_output, agent00b_raw, agent00b_provenance = _run_prompt_json_object(
                asset=agent00b_asset,
                context="strategy_v2.agent0b_output",
                model=settings.STRATEGY_V2_VOC_MODEL,
                runtime_instruction=(
                    "## Runtime Input Block\n"
                    f"PRODUCT_BRIEF:\n{_dump_prompt_json(stage1_data, max_chars=12000)}\n\n"
                    f"AVATAR_BRIEF:\n{_dump_prompt_json(avatar_brief_payload, max_chars=12000)}\n\n"
                    f"COMPETITOR_ANALYSIS:\n{_dump_prompt_json(competitor_analysis, max_chars=16000)}\n\n"
                    f"PRODUCT_CATEGORY_KEYWORDS:\n{', '.join(product_category_keywords)}\n\n"
                    f"KNOWN_COMPETITOR_SOCIAL_ACCOUNTS:\n{_dump_prompt_json(stage1.competitor_urls, max_chars=6000)}\n\n"
                    "Output a strict JSON object with platform strategy and configuration summaries."
                ),
                schema_name="strategy_v2_voc_agent00b",
                schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "platform_priorities": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "configurations": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                                "properties": {
                                    "config_id": {"type": "string", "minLength": 1},
                                    "platform": {"type": "string", "minLength": 1},
                                    "mode": {"type": "string", "minLength": 1},
                                },
                                "required": ["config_id", "platform", "mode"],
                            },
                        },
                        "handoff_block": {"type": "string"},
                    },
                    "required": ["platform_priorities", "configurations"],
                },
                use_reasoning=True,
                use_web_search=False,
                heartbeat_context={
                    "activity": "strategy_v2.run_voc_angle_pipeline",
                    "phase": "agent0b_prompt",
                    "model": settings.STRATEGY_V2_VOC_MODEL,
                },
            )
            _raise_if_blocked_prompt_output(
                stage_label="v2-03 Agent 0b social video strategist",
                parsed_output=agent00b_output,
                raw_output=agent00b_raw,
                remediation=(
                    "supply PRODUCT_BRIEF, structured AVATAR_BRIEF, COMPETITOR_ANALYSIS, "
                    "and PRODUCT_CATEGORY_KEYWORDS before rerunning v2-03."
                ),
            )

            video_observations = _extract_video_observations(competitor_analysis)
            apify_video_raw = apify_context.get("social_video_observations")
            apify_video_rows = (
                [row for row in apify_video_raw if isinstance(row, dict)]
                if isinstance(apify_video_raw, list)
                else []
            )
            seen_video_ids: set[str] = {
                str(row.get("video_id") or row.get("source_ref") or "").strip()
                for row in video_observations
                if isinstance(row, dict)
            }
            for row in apify_video_rows:
                video_id = str(row.get("video_id") or row.get("source_ref") or "").strip()
                if not video_id or video_id in seen_video_ids:
                    continue
                seen_video_ids.add(video_id)
                video_observations.append(row)

            metric_video_rows = [
                row
                for row in video_observations
                if isinstance(row, dict)
                and isinstance(row.get("views"), int)
                and isinstance(row.get("followers"), int)
                and isinstance(row.get("comments"), int)
                and isinstance(row.get("shares"), int)
                and isinstance(row.get("likes"), int)
                and isinstance(row.get("days_since_posted"), int)
            ]
            if not metric_video_rows:
                raise StrategyV2MissingContextError(
                    "v2-03 requires at least one social video observation with numeric metrics "
                    "(views, followers, comments, shares, likes, days_since_posted). "
                    "Remediation: enrich competitor_analysis.asset_observation_sheets or external Apify video rows."
                )
            video_scored = score_videos(metric_video_rows)
            video_agent_run_id = _record_agent_run(
                session=session,
                org_id=org_id,
                user_id=operator_user_id,
                client_id=client_id,
                objective_type="strategy_v2.agent0b_scrape_virality.prompt_chain",
                model=settings.STRATEGY_V2_VOC_MODEL,
                inputs_json={
                    "video_observation_count": len(video_observations),
                    "metric_video_observation_count": len(metric_video_rows),
                    "apify_video_observation_count": len(apify_video_rows),
                },
                outputs_json={
                    "video_strategy": agent00b_output,
                    "video_scored": video_scored,
                },
            )
            v2_03_step_payload_artifact_id = _persist_step_payload(
                session=session,
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                workflow_run_id=workflow_run_id,
                step_key=V2_STEP_SCRAPE_VIRALITY,
                title="Strategy V2 Scrape + Virality",
                summary="Agent 0b prompt-chain social video strategy and deterministic virality scoring.",
                payload={
                    "video_observation_count": len(video_observations),
                    "metric_video_observation_count": len(metric_video_rows),
                    "apify_video_observation_count": len(apify_video_rows),
                    "video_strategy": agent00b_output,
                    "video_scored": video_scored,
                    "prompt_provenance": agent00b_provenance,
                    "raw_output": agent00b_raw[:20000],
                },
                model_name=settings.STRATEGY_V2_VOC_MODEL,
                prompt_version="strategy_v2.agent0b.prompt_chain.v2",
                schema_version=SCHEMA_VERSION_V2,
                agent_run_id=video_agent_run_id,
            )
            scraped_data_manifest = _build_scraped_data_manifest(
                apify_context=apify_context,
                competitor_analysis=competitor_analysis,
            )

            agent01_asset = resolve_prompt_asset(
                pattern=_VOC_AGENT01_PROMPT_PATTERN,
                context="VOC Agent 1 habitat qualifier",
            )
            agent01_output, agent01_raw, agent01_provenance = _run_prompt_json_object(
                asset=agent01_asset,
                context="strategy_v2.agent1_output",
                model=settings.STRATEGY_V2_VOC_MODEL,
                runtime_instruction=(
                    "## Runtime Input Block\n"
                    f"HABITAT_STRATEGY_JSON:\n{_dump_prompt_json(agent00_output, max_chars=9000)}\n\n"
                    f"VIDEO_STRATEGY_JSON:\n{_dump_prompt_json(agent00b_output, max_chars=9000)}\n\n"
                    f"SCORED_VIDEO_DATA_JSON:\n{_dump_prompt_json(video_scored, max_chars=9000)}\n\n"
                    f"SCRAPED_DATA_FILES_JSON:\n{_dump_prompt_json(scraped_data_manifest, max_chars=10000)}\n\n"
                    f"PRODUCT_BRIEF:\n{_dump_prompt_json(stage1_data, max_chars=9000)}\n\n"
                    f"AVATAR_BRIEF:\n{_dump_prompt_json(avatar_brief_payload, max_chars=9000)}\n\n"
                    f"COMPETITOR_ANALYSIS_JSON:\n{_dump_prompt_json(competitor_analysis, max_chars=10000)}\n\n"
                    "If any detail is absent, continue with best-effort qualification using available evidence "
                    "and mark unknowns as CANNOT_DETERMINE.\n"
                    "Never emit sentinel blocked tokens in output.\n"
                    "Output habitat_observations suitable for deterministic habitat scoring."
                ),
                schema_name="strategy_v2_voc_agent01",
                schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "habitat_observations": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                                "properties": {
                                    "habitat_name": {"type": "string", "minLength": 1},
                                    "habitat_type": {"type": "string", "minLength": 1},
                                    "url_pattern": {"type": "string", "minLength": 1},
                                },
                                "required": ["habitat_name", "habitat_type", "url_pattern"],
                            },
                        },
                        "mining_plan": {
                            "type": "array",
                            "items": {"type": "object", "additionalProperties": True},
                        },
                    },
                    "required": ["habitat_observations"],
                },
                use_reasoning=True,
                use_web_search=False,
                max_tokens=_AGENT1_MAX_TOKENS,
                heartbeat_context={
                    "activity": "strategy_v2.run_voc_angle_pipeline",
                    "phase": "agent1_prompt",
                    "model": settings.STRATEGY_V2_VOC_MODEL,
                },
            )
            _raise_if_blocked_prompt_output(
                stage_label="v2-04 Agent 1 habitat qualifier",
                parsed_output=agent01_output,
                raw_output=agent01_raw,
                remediation=(
                    "provide valid scraped-data manifest, habitat/video strategy handoff, "
                    "and complete product/avatar context before rerunning v2-04."
                ),
            )
            raw_habitat_observations = agent01_output.get("habitat_observations")
            if not isinstance(raw_habitat_observations, list):
                raise StrategyV2SchemaValidationError("Agent 1 output must contain habitat_observations array.")
            habitat_observations = _normalize_habitat_observations(
                [row for row in raw_habitat_observations if isinstance(row, dict)]
            )
            habitat_scored = score_habitats(habitat_observations)
            qualifier_agent_run_id = _record_agent_run(
                session=session,
                org_id=org_id,
                user_id=operator_user_id,
                client_id=client_id,
                objective_type="strategy_v2.agent1_habitat_scoring.prompt_chain",
                model=settings.STRATEGY_V2_VOC_MODEL,
                inputs_json={"habitat_observation_count": len(habitat_observations)},
                outputs_json=habitat_scored,
            )
            v2_04_step_payload_artifact_id = _persist_step_payload(
                session=session,
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                workflow_run_id=workflow_run_id,
                step_key=V2_STEP_HABITAT_SCORING,
                title="Strategy V2 Habitat Scoring",
                summary="Agent 1 prompt-chain habitat observations qualified with deterministic scoring.",
                payload={
                    "habitat_observation_count": len(habitat_observations),
                    "habitat_observations": habitat_observations,
                    "habitat_scored": habitat_scored,
                    "prompt_provenance": agent01_provenance,
                    "raw_output": agent01_raw[:20000],
                },
                model_name=settings.STRATEGY_V2_VOC_MODEL,
                prompt_version="strategy_v2.agent1.prompt_chain.v2",
                schema_version=SCHEMA_VERSION_V2,
                agent_run_id=qualifier_agent_run_id,
            )

            saturated_angles = extract_saturated_angles(competitor_analysis, limit=9)
            agent02_asset = resolve_prompt_asset(
                pattern=_VOC_AGENT02_PROMPT_PATTERN,
                context="VOC Agent 2 extractor",
            )
            agent02_output, agent02_raw, agent02_provenance = _run_prompt_json_object(
                asset=agent02_asset,
                context="strategy_v2.agent2_output",
                model=settings.STRATEGY_V2_VOC_MODEL,
                runtime_instruction=(
                    "## Runtime Input Block\n"
                    "DUAL_MODE_REQUIRED: true\n"
                    f"AGENT1_HANDOFF_JSON:\n{_dump_prompt_json(agent01_output, max_chars=12000)}\n\n"
                    f"PRODUCT_BRIEF_JSON:\n{_dump_prompt_json(stage1_data, max_chars=9000)}\n\n"
                    f"AVATAR_BRIEF:\n{_dump_prompt_json(avatar_brief_payload, max_chars=9000)}\n\n"
                    f"AVATAR_SUMMARY:\n{str(foundational_step_summaries.get('06') or '')[:4000]}\n\n"
                    f"EXISTING_VOC_CORPUS_JSON:\n{_dump_prompt_json(existing_corpus, max_chars=30000)}\n\n"
                    f"VOC_CORPUS_SELECTION_SUMMARY_JSON:\n{_dump_prompt_json(merged_voc['summary'], max_chars=6000)}\n\n"
                    f"KNOWN_SATURATED_ANGLES:\n{_dump_prompt_json(saturated_angles, max_chars=8000)}\n\n"
                    "Output voc_observations suitable for deterministic VOC scoring."
                ),
                schema_name="strategy_v2_voc_agent02",
                schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "mode": {"type": "string", "minLength": 1},
                        "voc_observations": {
                            "type": "array",
                            "minItems": 5,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "voc_id": {"type": "string", "minLength": 1},
                                    "source": {"type": "string", "minLength": 1},
                                    "quote": {"type": "string", "minLength": 1},
                                    "specific_number": {"type": "string", "enum": ["Y", "N"]},
                                    "specific_product_brand": {"type": "string", "enum": ["Y", "N"]},
                                    "specific_event_moment": {"type": "string", "enum": ["Y", "N"]},
                                    "specific_body_symptom": {"type": "string", "enum": ["Y", "N"]},
                                    "before_after_comparison": {"type": "string", "enum": ["Y", "N"]},
                                    "crisis_language": {"type": "string", "enum": ["Y", "N"]},
                                    "profanity_extreme_punctuation": {"type": "string", "enum": ["Y", "N"]},
                                    "physical_sensation": {"type": "string", "enum": ["Y", "N"]},
                                    "identity_change_desire": {"type": "string", "enum": ["Y", "N"]},
                                    "word_count": {"type": "integer", "minimum": 1},
                                    "clear_trigger_event": {"type": "string", "enum": ["Y", "N"]},
                                    "named_enemy": {"type": "string", "enum": ["Y", "N"]},
                                    "shiftable_belief": {"type": "string", "enum": ["Y", "N"]},
                                    "expectation_vs_reality": {"type": "string", "enum": ["Y", "N"]},
                                    "headline_ready": {"type": "string", "enum": ["Y", "N"]},
                                    "usable_content_pct": {
                                        "type": "string",
                                        "enum": ["OVER_75_PCT", "50_TO_75_PCT", "25_TO_50_PCT", "UNDER_25_PCT"],
                                    },
                                    "personal_context": {"type": "string", "enum": ["Y", "N"]},
                                    "long_narrative": {"type": "string", "enum": ["Y", "N"]},
                                    "engagement_received": {"type": "string", "enum": ["Y", "N"]},
                                    "real_person_signals": {"type": "string", "enum": ["Y", "N"]},
                                    "moderated_community": {"type": "string", "enum": ["Y", "N"]},
                                    "trigger_event": {"type": "string", "minLength": 1},
                                    "pain_problem": {"type": "string", "minLength": 1},
                                    "desired_outcome": {"type": "string", "minLength": 1},
                                    "failed_prior_solution": {"type": "string", "minLength": 1},
                                    "enemy_blame": {"type": "string", "minLength": 1},
                                    "identity_role": {"type": "string", "minLength": 1},
                                    "fear_risk": {"type": "string", "minLength": 1},
                                    "emotional_valence": {
                                        "type": "string",
                                        "enum": [
                                            "RELIEF",
                                            "RAGE",
                                            "SHAME",
                                            "PRIDE",
                                            "ANXIETY",
                                            "HOPE",
                                            "FRUSTRATION",
                                            "NEUTRAL",
                                        ],
                                    },
                                    "durable_psychology": {"type": "string", "enum": ["Y", "N"]},
                                    "market_specific": {"type": "string", "enum": ["Y", "N"]},
                                    "date_bracket": {
                                        "type": "string",
                                        "enum": ["LAST_3MO", "LAST_6MO", "LAST_12MO", "LAST_24MO", "OLDER", "UNKNOWN"],
                                    },
                                    "buyer_stage": {"type": "string", "minLength": 1},
                                    "solution_sophistication": {
                                        "type": "string",
                                        "enum": ["NOVICE", "EXPERIENCED", "EXHAUSTED", "UNKNOWN"],
                                    },
                                    "compliance_risk": {"type": "string", "enum": ["GREEN", "YELLOW", "RED"]},
                                },
                                "required": [
                                    "voc_id",
                                    "source",
                                    "quote",
                                    "specific_number",
                                    "specific_product_brand",
                                    "specific_event_moment",
                                    "specific_body_symptom",
                                    "before_after_comparison",
                                    "crisis_language",
                                    "profanity_extreme_punctuation",
                                    "physical_sensation",
                                    "identity_change_desire",
                                    "word_count",
                                    "clear_trigger_event",
                                    "named_enemy",
                                    "shiftable_belief",
                                    "expectation_vs_reality",
                                    "headline_ready",
                                    "usable_content_pct",
                                    "personal_context",
                                    "long_narrative",
                                    "engagement_received",
                                    "real_person_signals",
                                    "moderated_community",
                                    "trigger_event",
                                    "pain_problem",
                                    "desired_outcome",
                                    "failed_prior_solution",
                                    "enemy_blame",
                                    "identity_role",
                                    "fear_risk",
                                    "emotional_valence",
                                    "durable_psychology",
                                    "market_specific",
                                    "date_bracket",
                                    "buyer_stage",
                                    "solution_sophistication",
                                    "compliance_risk",
                                ],
                            },
                        },
                    },
                    "required": ["mode", "voc_observations"],
                },
                use_reasoning=True,
                use_web_search=False,
                max_tokens=_AGENT2_MAX_TOKENS,
                heartbeat_context={
                    "activity": "strategy_v2.run_voc_angle_pipeline",
                    "phase": "agent2_prompt",
                    "model": settings.STRATEGY_V2_VOC_MODEL,
                },
            )
            _raise_if_blocked_prompt_output(
                stage_label="v2-05 Agent 2 VOC extractor",
                parsed_output=agent02_output,
                raw_output=agent02_raw,
                remediation=(
                    "provide valid Agent 1 handoff, product/avatar briefs, and corpus context before rerunning v2-05."
                ),
            )
            raw_voc_observations = agent02_output.get("voc_observations")
            if not isinstance(raw_voc_observations, list):
                raise StrategyV2SchemaValidationError("Agent 2 output must contain voc_observations array.")
            voc_observations = _normalize_voc_observations(
                [row for row in raw_voc_observations if isinstance(row, dict)]
            )
            voc_scored = score_voc_items(voc_observations)
            _require_voc_transition_quality(
                voc_observations=voc_observations,
                voc_scored=voc_scored,
            )
            voc_agent_run_id = _record_agent_run(
                session=session,
                org_id=org_id,
                user_id=operator_user_id,
                client_id=client_id,
                objective_type="strategy_v2.agent2_voc_extraction.prompt_chain",
                model=settings.STRATEGY_V2_VOC_MODEL,
                inputs_json={"voc_observation_count": len(voc_observations)},
                outputs_json=voc_scored,
            )
            v2_05_step_payload_artifact_id = _persist_step_payload(
                session=session,
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                workflow_run_id=workflow_run_id,
                step_key=V2_STEP_VOC_EXTRACTION,
                title="Strategy V2 VOC Extraction",
                summary="Agent 2 prompt-chain VOC corpus extracted and scored.",
                payload={
                    "voc_observation_count": len(voc_observations),
                    "prompt_corpus_count": len(existing_corpus),
                    "merged_corpus_count": len(merged_voc_artifact_rows),
                    "external_corpus_count": len(external_voc_corpus),
                    "corpus_selection_summary": merged_voc["summary"],
                    "voc_observations": voc_observations,
                    "voc_scored": voc_scored,
                    "mode": str(agent02_output.get("mode") or "DUAL"),
                    "proof_asset_candidates": proof_asset_candidates,
                    "prompt_provenance": agent02_provenance,
                    "raw_output": agent02_raw[:20000],
                },
                model_name=settings.STRATEGY_V2_VOC_MODEL,
                prompt_version="strategy_v2.agent2.prompt_chain.v2",
                schema_version=SCHEMA_VERSION_V2,
                agent_run_id=voc_agent_run_id,
            )

            competitor_angle_map = build_competitor_angle_map(competitor_analysis)
            saturated_count = max(1, min(9, len(saturated_angles)))
            agent03_asset = resolve_prompt_asset(
                pattern=_VOC_AGENT03_PROMPT_PATTERN,
                context="VOC Agent 3 shadow angle clusterer",
            )
            agent03_output, agent03_raw, agent03_provenance = _run_prompt_json_object(
                asset=agent03_asset,
                context="strategy_v2.agent3_output",
                model=settings.STRATEGY_V2_VOC_MODEL,
                runtime_instruction=(
                    "## Runtime Input Block\n"
                    f"AGENT2_HANDOFF_VOC_SCORED_JSON:\n{_dump_prompt_json(voc_scored, max_chars=30000)}\n\n"
                    f"AGENT2_VOC_OBSERVATIONS_JSON:\n{_dump_prompt_json(voc_observations, max_chars=24000)}\n\n"
                    f"COMPETITOR_ANGLE_MAP_JSON:\n{_dump_prompt_json(competitor_angle_map, max_chars=16000)}\n\n"
                    f"KNOWN_SATURATED_ANGLES_JSON:\n{_dump_prompt_json(saturated_angles, max_chars=10000)}\n\n"
                    f"PRODUCT_BRIEF_JSON:\n{_dump_prompt_json(stage1_data, max_chars=9000)}\n\n"
                    f"AVATAR_BRIEF_SUMMARY:\n{str(foundational_step_summaries.get('06') or '')[:4000]}\n\n"
                    "Output both angle_observations and angle_candidates.\n"
                    f"Return exactly {_MIN_AGENT3_ANGLE_CANDIDATES} angle_candidates, "
                    f"exactly {_AGENT3_TOP_QUOTES_PER_CANDIDATE} top_quotes per candidate, "
                    f"and exactly {_AGENT3_HOOK_STARTERS_PER_CANDIDATE} hook_starters per candidate.\n"
                    f"Keep every non-quote text field <= {_AGENT3_MAX_TEXT_CHARS} characters and each quote <= {_AGENT3_MAX_QUOTE_CHARS} characters."
                ),
                schema_name="strategy_v2_voc_agent03",
                schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "angle_observations": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": _MAX_AGENT3_ANGLE_OBSERVATIONS,
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                                "properties": {
                                    "angle_id": {"type": "string", "maxLength": 32},
                                    "angle_name": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                                },
                                "required": ["angle_id", "angle_name"],
                            },
                        },
                        "angle_candidates": {
                            "type": "array",
                            "minItems": _MIN_AGENT3_ANGLE_CANDIDATES,
                            "maxItems": _MIN_AGENT3_ANGLE_CANDIDATES,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "angle_id": {"type": "string", "maxLength": 32},
                                    "angle_name": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                                    "definition": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "properties": {
                                            "who": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                                            "pain_desire": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                                            "mechanism_why": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                                            "belief_shift": {
                                                "type": "object",
                                                "additionalProperties": False,
                                                "properties": {
                                                    "before": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                                                    "after": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                                                },
                                                "required": ["before", "after"],
                                            },
                                            "trigger": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                                        },
                                        "required": ["who", "pain_desire", "mechanism_why", "belief_shift", "trigger"],
                                    },
                                    "evidence": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "properties": {
                                            "supporting_voc_count": {"type": "integer"},
                                            "top_quotes": {
                                                "type": "array",
                                                "minItems": _AGENT3_TOP_QUOTES_PER_CANDIDATE,
                                                "maxItems": _AGENT3_TOP_QUOTES_PER_CANDIDATE,
                                                "items": {
                                                    "type": "object",
                                                    "additionalProperties": False,
                                                    "properties": {
                                                        "voc_id": {"type": "string", "maxLength": 64},
                                                        "quote": {"type": "string", "maxLength": _AGENT3_MAX_QUOTE_CHARS},
                                                        "adjusted_score": {"type": "number"},
                                                    },
                                                    "required": ["voc_id", "quote", "adjusted_score"],
                                                },
                                            },
                                            "triangulation_status": {
                                                "type": "string",
                                                "enum": ["SINGLE", "DUAL", "MULTI"],
                                            },
                                            "velocity_status": {
                                                "type": "string",
                                                "enum": ["ACCELERATING", "STEADY", "DECELERATING"],
                                            },
                                            "contradiction_count": {"type": "integer"},
                                        },
                                        "required": [
                                            "supporting_voc_count",
                                            "top_quotes",
                                            "triangulation_status",
                                            "velocity_status",
                                            "contradiction_count",
                                        ],
                                    },
                                    "hook_starters": {
                                        "type": "array",
                                        "minItems": _AGENT3_HOOK_STARTERS_PER_CANDIDATE,
                                        "maxItems": _AGENT3_HOOK_STARTERS_PER_CANDIDATE,
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "visual": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                                                "opening_line": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                                                "lever": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                                            },
                                            "required": ["visual", "opening_line", "lever"],
                                        },
                                    },
                                },
                                "required": ["angle_id", "angle_name", "definition", "evidence", "hook_starters"],
                            },
                        },
                    },
                    "required": ["angle_observations", "angle_candidates"],
                },
                use_reasoning=True,
                use_web_search=False,
                max_tokens=_AGENT3_MAX_TOKENS,
                heartbeat_context={
                    "activity": "strategy_v2.run_voc_angle_pipeline",
                    "phase": "agent3_prompt",
                    "model": settings.STRATEGY_V2_VOC_MODEL,
                },
            )
            _raise_if_blocked_prompt_output(
                stage_label="v2-06 Agent 3 angle synthesis",
                parsed_output=agent03_output,
                raw_output=agent03_raw,
                remediation=(
                    "ensure Agent 2 produced complete high-quality VOC observations before rerunning v2-06."
                ),
            )
            raw_angle_observations = agent03_output.get("angle_observations")
            if not isinstance(raw_angle_observations, list):
                raise StrategyV2SchemaValidationError("Agent 3 output must contain angle_observations array.")
            raw_angle_candidates = agent03_output.get("angle_candidates")
            if not isinstance(raw_angle_candidates, list):
                raise StrategyV2SchemaValidationError("Agent 3 output must contain angle_candidates array.")
            angle_candidates = _normalize_angle_candidates(
                [row for row in raw_angle_candidates if isinstance(row, dict)]
            )
            candidate_lookup = {
                str(candidate.get("angle_id")): candidate
                for candidate in angle_candidates
                if isinstance(candidate, dict) and isinstance(candidate.get("angle_id"), str)
            }
            angle_observations = _normalize_angle_observations(
                [row for row in raw_angle_observations if isinstance(row, dict)],
                saturated_count=saturated_count,
                candidate_lookup=candidate_lookup,
            )
            if len(angle_candidates) < _MIN_AGENT3_ANGLE_CANDIDATES:
                raise StrategyV2DecisionError(
                    "Agent 3 did not return enough angle candidates for HITL selection quality. "
                    f"Received={len(angle_candidates)}, required>={_MIN_AGENT3_ANGLE_CANDIDATES}. "
                    "Remediation: rerun stage v2-06 with richer VOC inputs and stronger competitor-angle mapping."
                )
            scored_angles_payload = score_angles(angle_observations, saturated_count=saturated_count)
            _require_angle_transition_quality(scored_angles_payload=scored_angles_payload)
            scored_angle_rows = scored_angles_payload.get("angles")
            scored_lookup: dict[str, dict[str, Any]] = {}
            if isinstance(scored_angle_rows, list):
                for row in scored_angle_rows:
                    if isinstance(row, dict) and isinstance(row.get("angle_id"), str):
                        scored_lookup[row["angle_id"]] = row
            ranked_candidates: list[dict[str, Any]] = []
            for candidate in angle_candidates:
                candidate_id = candidate.get("angle_id")
                score_row = scored_lookup.get(str(candidate_id))
                ranked_candidates.append(
                    {
                        "angle": candidate,
                        "score": score_row.get("final_score") if isinstance(score_row, dict) else None,
                        "confidence_range": score_row.get("confidence_range") if isinstance(score_row, dict) else None,
                        "rank": score_row.get("rank") if isinstance(score_row, dict) else None,
                        "components": score_row.get("components") if isinstance(score_row, dict) else None,
                        "evidence_floor_gate": (
                            score_row.get("evidence_floor_gate")
                            if isinstance(score_row, dict)
                            else None
                        ),
                    }
                )
            ranked_candidates.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
            angle_agent_run_id = _record_agent_run(
                session=session,
                org_id=org_id,
                user_id=operator_user_id,
                client_id=client_id,
                objective_type="strategy_v2.agent3_angle_synthesis.prompt_chain",
                model=settings.STRATEGY_V2_VOC_MODEL,
                inputs_json={"angle_observation_count": len(angle_observations)},
                outputs_json={
                    "ranked_candidates": ranked_candidates,
                    "score_summary": scored_angles_payload.get("summary"),
                },
            )
            v2_06_step_payload_artifact_id = _persist_step_payload(
                session=session,
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                workflow_run_id=workflow_run_id,
                step_key=V2_STEP_ANGLE_SYNTHESIS,
                title="Strategy V2 Angle Synthesis",
                summary="Agent 3 prompt-chain angle candidates synthesized and ranked.",
                payload={
                    "ranked_candidates": ranked_candidates,
                    "scorecard": scored_angles_payload,
                    "stage1_artifact_id": stage1_artifact_id,
                    "angle_observations": angle_observations,
                    "prompt_provenance": agent03_provenance,
                    "raw_output": agent03_raw[:30000],
                },
                model_name=settings.STRATEGY_V2_VOC_MODEL,
                prompt_version="strategy_v2.agent3.prompt_chain.v2",
                schema_version=SCHEMA_VERSION_V2,
                agent_run_id=angle_agent_run_id,
            )

            return {
                "stage1": stage1_data,
                "stage1_artifact_id": stage1_artifact_id,
                "step_payload_artifact_ids": {
                    **foundational_step_payload_artifact_ids,
                    V2_STEP_HABITAT_STRATEGY: v2_02_step_payload_artifact_id,
                    V2_STEP_SCRAPE_VIRALITY: v2_03_step_payload_artifact_id,
                    V2_STEP_HABITAT_SCORING: v2_04_step_payload_artifact_id,
                    V2_STEP_VOC_EXTRACTION: v2_05_step_payload_artifact_id,
                    V2_STEP_ANGLE_SYNTHESIS: v2_06_step_payload_artifact_id,
                },
                "competitor_analysis": competitor_analysis,
                "habitat_scored": habitat_scored,
                "video_scored": video_scored,
                "voc_observations": voc_observations,
                "voc_scored": voc_scored,
                "merged_voc_corpus": merged_voc_artifact_rows,
                "proof_asset_candidates": proof_asset_candidates,
                "apify_context_summary": (
                    apify_context.get("summary") if isinstance(apify_context.get("summary"), dict) else None
                ),
                "ranked_angle_candidates": ranked_candidates,
            }


@activity.defn(name="strategy_v2.finalize_research_proceed")
def finalize_strategy_v2_research_proceed_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    workflow_run_id = str(params["workflow_run_id"])

    stage1 = ProductBriefStage1.model_validate(_require_dict(payload=params["stage1"], field_name="stage1"))
    decision = ResearchProceedDecision.model_validate(
        _require_dict(payload=params["research_proceed_decision"], field_name="research_proceed_decision")
    )
    decision_operator_user_id = _require_human_operator_user_id(
        operator_user_id=decision.operator_user_id,
        decision_name="Research proceed gate",
    )
    _enforce_decision_integrity_policy(
        decision_name="Research proceed gate",
        decision_mode=decision.decision_mode,
        operator_note=decision.operator_note,
        attestation_reviewed_evidence=decision.attestation.reviewed_evidence,
        attestation_understands_impact=decision.attestation.understands_impact,
        reviewed_candidate_ids=None,
        require_reviewed_candidates=False,
    )
    if not decision.proceed:
        raise StrategyV2DecisionError(
            "Research proceed decision must explicitly set proceed=true to continue Strategy V2. "
            "Remediation: submit a proceed=true decision after research quality review."
        )
    _require_stage1_quality(stage1)

    payload = {
        "decision": decision.model_dump(mode="python"),
        "stage1_quality_snapshot": {
            "competitor_count_validated": stage1.competitor_count_validated,
            "primary_icp_count": len(stage1.primary_icps),
            "bottleneck": stage1.bottleneck,
        },
        "stage1_summary": {
            "category_niche": stage1.category_niche,
            "primary_segment": stage1.primary_segment.model_dump(mode="python"),
        },
    }

    with session_scope() as session:
        agent_run_id = _record_agent_run(
            session=session,
            org_id=org_id,
            user_id=decision_operator_user_id,
            client_id=client_id,
            objective_type="strategy_v2.research_proceed_gate",
            model="human_decision",
            inputs_json={"decision": decision.model_dump(mode="python")},
            outputs_json=payload,
        )
        step_payload_artifact_id = _persist_step_payload(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            workflow_run_id=workflow_run_id,
            step_key=V2_STEP_RESEARCH_PROCEED_HITL,
            title="Strategy V2 Research Proceed HITL",
            summary="Human-approved foundational research quality gate.",
            payload=payload,
            model_name="human_decision",
            prompt_version="strategy_v2.research_proceed.v1",
            schema_version=SCHEMA_VERSION_V2,
            agent_run_id=agent_run_id,
        )
        return {"step_payload_artifact_id": step_payload_artifact_id}


@activity.defn(name="strategy_v2.prepare_competitor_asset_candidates")
def prepare_strategy_v2_competitor_asset_candidates_activity(params: dict[str, Any]) -> dict[str, Any]:
    stage1 = ProductBriefStage1.model_validate(_require_dict(payload=params["stage1"], field_name="stage1"))
    _require_stage1_quality(stage1)

    raw_refs = [url for url in stage1.competitor_urls if isinstance(url, str) and url.strip()]
    if not raw_refs:
        raise StrategyV2MissingContextError(
            "H2 candidate asset preparation requires stage1.competitor_urls, but none were available. "
            "Remediation: supply 3+ competitor asset refs in Stage 1 before proceeding to H2."
        )

    scrapeable_refs, excluded_source_refs = _partition_source_refs_for_ingestion(raw_refs)
    raw_candidates = build_url_candidates(scrapeable_refs)
    apify_context = _ingest_strategy_v2_asset_data(
        source_refs=scrapeable_refs,
        include_ads_context=True,
        include_social_video=True,
        include_external_voc=True,
    )
    apify_context["excluded_source_refs"] = excluded_source_refs
    apify_context["ingestion_source_refs"] = scrapeable_refs
    apify_candidates_raw = apify_context.get("candidate_assets")
    apify_candidates = (
        [row for row in apify_candidates_raw if isinstance(row, dict)]
        if isinstance(apify_candidates_raw, list)
        else []
    )

    merged_candidates_by_ref: dict[str, dict[str, Any]] = {}
    for row in raw_candidates + apify_candidates:
        source_ref = str(row.get("source_ref") or "").strip()
        if not source_ref:
            continue
        existing = merged_candidates_by_ref.get(source_ref)
        if existing is None:
            merged_candidates_by_ref[source_ref] = row
            continue
        existing_metrics = existing.get("metrics")
        row_metrics = row.get("metrics")
        existing_metric_count = (
            len([key for key, value in existing_metrics.items() if value not in (None, "", 0)])
            if isinstance(existing_metrics, dict)
            else 0
        )
        row_metric_count = (
            len([key for key, value in row_metrics.items() if value not in (None, "", 0)])
            if isinstance(row_metrics, dict)
            else 0
        )
        if row_metric_count > existing_metric_count:
            merged_candidates_by_ref[source_ref] = row

    if not merged_candidates_by_ref:
        raise StrategyV2MissingContextError(
            "H2 candidate asset preparation could not produce any normalized competitor assets. "
            "Remediation: verify competitor URLs and Apify ingestion configuration."
        )
    merged_candidates = list(merged_candidates_by_ref.values())

    scored_candidates = score_candidate_assets(merged_candidates)
    selected_candidates = select_top_candidates(
        scored_candidates,
        max_candidates=_H2_MAX_CANDIDATE_ASSETS,
        max_per_competitor=_H2_MAX_CANDIDATES_PER_COMPETITOR,
        max_per_platform=_H2_MAX_CANDIDATES_PER_PLATFORM,
    )
    eligible_count = len([row for row in scored_candidates if bool(row.get("eligible"))])

    if len(selected_candidates) < _MIN_STAGE1_COMPETITORS:
        raise StrategyV2MissingContextError(
            "H2 requires at least 3 scored candidate assets after hard-gate filtering, "
            f"but only {len(selected_candidates)} were eligible "
            f"(stage1_urls={len(raw_refs)}, scrapeable_urls={len(scrapeable_refs)}, eligible={eligible_count}). "
            "Remediation: provide additional valid competitor asset refs before H2."
        )

    selected_by_platform = Counter(str(row.get("platform") or "unknown") for row in selected_candidates)
    selected_by_competitor = Counter(str(row.get("competitor_name") or "unknown") for row in selected_candidates)
    candidate_summary = {
        "stage1_url_count": len(raw_refs),
        "scrapeable_url_count": len(scrapeable_refs),
        "excluded_source_refs": excluded_source_refs,
        "normalized_candidate_count": len(merged_candidates),
        "seed_url_candidate_count": len(raw_candidates),
        "apify_candidate_count": len(apify_candidates),
        "eligible_candidate_count": eligible_count,
        "selected_candidate_count": len(selected_candidates),
        "selected_candidate_ids": [
            str(row.get("candidate_id"))
            for row in selected_candidates
            if isinstance(row.get("candidate_id"), str) and str(row.get("candidate_id")).strip()
        ],
        "selection_limits": {
            "max_candidates": _H2_MAX_CANDIDATE_ASSETS,
            "max_per_competitor": _H2_MAX_CANDIDATES_PER_COMPETITOR,
            "max_per_platform": _H2_MAX_CANDIDATES_PER_PLATFORM,
        },
        "operator_confirmation_policy": {
            "min_confirmed_assets": _MIN_STAGE1_COMPETITORS,
            "target_confirmed_assets": _H2_TARGET_CONFIRMED_ASSETS,
            "max_confirmed_assets": _H2_MAX_CONFIRMED_ASSETS,
        },
        "selection_ordering": {
            "eligibility_rule": "hard_gate_flags must be empty",
            "sort_rule": "candidate_asset_score desc, candidate_id asc",
            "diversity_caps_applied": True,
        },
        "selected_by_platform": dict(selected_by_platform),
        "selected_by_competitor": dict(selected_by_competitor),
        "apify_summary": (
            apify_context.get("summary") if isinstance(apify_context.get("summary"), dict) else None
        ),
    }

    step_payload_artifact_id: str | None = None
    workflow_run_id = params.get("workflow_run_id")
    if isinstance(workflow_run_id, str) and workflow_run_id.strip():
        org_id = str(params["org_id"])
        client_id = str(params["client_id"])
        product_id = str(params["product_id"])
        campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
        with session_scope() as session:
            step_payload_artifact_id = _persist_step_payload(
                session=session,
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                workflow_run_id=workflow_run_id,
                step_key=V2_STEP_ASSET_DATA_INGESTION,
                title="Strategy V2 Asset Data Ingestion",
                summary="Apify-backed candidate/social/VOC context prepared for Strategy V2.",
                payload={
                    "apify_context": apify_context,
                    "candidate_summary": candidate_summary,
                    "selected_candidates": selected_candidates,
                },
                model_name="deterministic",
                prompt_version="strategy_v2.asset_ingestion.v1",
                schema_version=SCHEMA_VERSION_V2,
                agent_run_id=None,
            )

    result: dict[str, Any] = {
        "candidates": selected_candidates,
        "candidate_summary": candidate_summary,
        "apify_context": {
            "ads_context": apify_context.get("ads_context"),
            "social_video_observations": apify_context.get("social_video_observations"),
            "external_voc_corpus": apify_context.get("external_voc_corpus"),
            "proof_asset_candidates": apify_context.get("proof_asset_candidates"),
            "summary": apify_context.get("summary"),
        },
    }
    if step_payload_artifact_id:
        result["step_payload_artifact_id"] = step_payload_artifact_id
    return result


@activity.defn(name="strategy_v2.finalize_competitor_assets_confirmation")
def finalize_strategy_v2_competitor_assets_confirmation_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    workflow_run_id = str(params["workflow_run_id"])

    stage1 = ProductBriefStage1.model_validate(_require_dict(payload=params["stage1"], field_name="stage1"))
    candidate_assets_raw = params.get("competitor_asset_candidates")
    if not isinstance(candidate_assets_raw, list):
        raise StrategyV2MissingContextError(
            "Competitor assets confirmation requires competitor_asset_candidates from H2 preparation. "
            "Remediation: pass scored H2 candidates into confirmation activity."
        )
    candidate_assets = [row for row in candidate_assets_raw if isinstance(row, dict)]
    if len(candidate_assets) < _MIN_STAGE1_COMPETITORS:
        raise StrategyV2MissingContextError(
            "Competitor assets confirmation requires at least 3 scored candidate assets in context. "
            f"Received={len(candidate_assets)}. "
            "Remediation: rerun candidate preparation with 3+ valid asset refs."
        )

    decision = CompetitorAssetConfirmationDecision.model_validate(
        _require_dict(
            payload=params["competitor_asset_confirmation_decision"],
            field_name="competitor_asset_confirmation_decision",
        )
    )
    decision_operator_user_id = _require_human_operator_user_id(
        operator_user_id=decision.operator_user_id,
        decision_name="Competitor assets confirmation gate",
    )
    cleaned_reviewed_candidate_ids = _enforce_decision_integrity_policy(
        decision_name="Competitor assets confirmation gate",
        decision_mode=decision.decision_mode,
        operator_note=decision.operator_note,
        attestation_reviewed_evidence=decision.attestation.reviewed_evidence,
        attestation_understands_impact=decision.attestation.understands_impact,
        reviewed_candidate_ids=decision.reviewed_candidate_ids,
        require_reviewed_candidates=True,
    )
    _require_stage1_quality(stage1)
    cleaned_asset_refs = [ref.strip() for ref in decision.confirmed_asset_refs if ref.strip()]
    if len(cleaned_asset_refs) < _MIN_STAGE1_COMPETITORS:
        raise StrategyV2DecisionError(
            f"Competitor asset confirmation requires {_MIN_STAGE1_COMPETITORS}-{_H2_MAX_CONFIRMED_ASSETS} "
            "confirmed asset references. "
            f"Received={len(cleaned_asset_refs)}. Remediation: provide at least {_MIN_STAGE1_COMPETITORS} "
            "competitor asset refs before continuing to Stage 2A."
        )
    if len(cleaned_asset_refs) > _H2_MAX_CONFIRMED_ASSETS:
        raise StrategyV2DecisionError(
            f"Competitor asset confirmation supports at most {_H2_MAX_CONFIRMED_ASSETS} confirmed asset refs "
            f"to protect downstream prompt context. Received={len(cleaned_asset_refs)}. "
            "Remediation: narrow confirmation to the highest-confidence scored candidates."
        )

    candidate_id_set = {
        str(row.get("candidate_id")).strip()
        for row in candidate_assets
        if isinstance(row.get("candidate_id"), str) and str(row.get("candidate_id")).strip()
    }
    if not candidate_id_set:
        raise StrategyV2MissingContextError(
            "Competitor assets confirmation received candidate assets with no candidate_id values. "
            "Remediation: provide normalized H2 candidate rows with candidate_id."
        )

    candidate_ref_set = {
        str(row.get("source_ref")).strip()
        for row in candidate_assets
        if isinstance(row.get("source_ref"), str) and str(row.get("source_ref")).strip()
    }
    if len(candidate_ref_set) < _MIN_STAGE1_COMPETITORS:
        raise StrategyV2MissingContextError(
            "Competitor assets confirmation context has fewer than 3 candidate source refs. "
            f"Received={len(candidate_ref_set)}. Remediation: add more scored candidate assets."
        )

    reviewed_unknown = sorted(set(cleaned_reviewed_candidate_ids) - candidate_id_set)
    if reviewed_unknown:
        raise StrategyV2DecisionError(
            "Competitor assets confirmation reviewed_candidate_ids included unknown candidate IDs: "
            f"{reviewed_unknown}. Remediation: review candidates from H2 payload and submit valid candidate IDs."
        )

    unknown_confirmed_refs = sorted(set(cleaned_asset_refs) - candidate_ref_set)
    if unknown_confirmed_refs:
        raise StrategyV2DecisionError(
            "Competitor assets confirmation included confirmed_asset_refs not present in scored H2 candidates: "
            f"{unknown_confirmed_refs}. Remediation: confirm assets from H2 candidate source_ref values."
        )

    candidate_summary = params.get("candidate_summary")
    if candidate_summary is not None and not isinstance(candidate_summary, dict):
        raise StrategyV2SchemaValidationError("candidate_summary must be an object when provided.")

    payload = {
        "decision": {
            **decision.model_dump(mode="python"),
            "confirmed_asset_refs": cleaned_asset_refs,
            "reviewed_candidate_ids": cleaned_reviewed_candidate_ids,
        },
        "competitor_urls_from_stage1": list(stage1.competitor_urls),
        "confirmed_asset_count": len(cleaned_asset_refs),
        "candidate_summary": candidate_summary or {
            "candidate_count": len(candidate_assets),
            "candidate_ref_count": len(candidate_ref_set),
            "operator_confirmation_policy": {
                "min_confirmed_assets": _MIN_STAGE1_COMPETITORS,
                "target_confirmed_assets": _H2_TARGET_CONFIRMED_ASSETS,
                "max_confirmed_assets": _H2_MAX_CONFIRMED_ASSETS,
            },
        },
    }

    with session_scope() as session:
        agent_run_id = _record_agent_run(
            session=session,
            org_id=org_id,
            user_id=decision_operator_user_id,
            client_id=client_id,
            objective_type="strategy_v2.competitor_assets_confirmation_gate",
            model="human_decision",
            inputs_json={"decision": decision.model_dump(mode="python")},
            outputs_json=payload,
        )
        step_payload_artifact_id = _persist_step_payload(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            workflow_run_id=workflow_run_id,
            step_key=V2_STEP_COMPETITOR_ASSETS_HITL,
            title="Strategy V2 Competitor Assets HITL",
            summary="Human-confirmed competitor assets before Stage 2A analysis.",
            payload=payload,
            model_name="human_decision",
            prompt_version="strategy_v2.competitor_assets_confirmation.v1",
            schema_version=SCHEMA_VERSION_V2,
            agent_run_id=agent_run_id,
        )
        return {
            "confirmed_asset_refs": cleaned_asset_refs,
            "step_payload_artifact_id": step_payload_artifact_id,
        }


@activity.defn(name="strategy_v2.apply_angle_selection")
def apply_strategy_v2_angle_selection_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    workflow_run_id = str(params["workflow_run_id"])

    stage1 = ProductBriefStage1.model_validate(_require_dict(payload=params["stage1"], field_name="stage1"))
    decision = AngleSelectionDecision.model_validate(
        _require_dict(payload=params["angle_selection_decision"], field_name="angle_selection_decision")
    )
    ranked_candidates_raw = params.get("ranked_angle_candidates")
    if not isinstance(ranked_candidates_raw, list) or not ranked_candidates_raw:
        raise StrategyV2MissingContextError(
            "Ranked angle candidates are required for angle decision integrity validation. "
            "Remediation: pass v2-06 ranked candidates into angle selection activity."
        )
    candidate_lookup: dict[str, SelectedAngleContract] = {}
    candidate_row_lookup: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(ranked_candidates_raw):
        row_payload = _require_dict(payload=row, field_name=f"ranked_angle_candidates[{index}]")
        angle_payload = _require_dict(payload=row_payload.get("angle"), field_name=f"ranked_angle_candidates[{index}].angle")
        candidate = SelectedAngleContract.model_validate(angle_payload)
        candidate_lookup[candidate.angle_id] = candidate
        candidate_row_lookup[candidate.angle_id] = row_payload

    selected_candidate = candidate_lookup.get(decision.selected_angle.angle_id)
    selected_candidate_row = candidate_row_lookup.get(decision.selected_angle.angle_id)
    if selected_candidate is None:
        raise StrategyV2DecisionError(
            f"Selected angle '{decision.selected_angle.angle_id}' was not in the presented ranked candidates. "
            "Remediation: choose an angle_id from v2-06 candidate list."
        )
    if decision.selected_angle.model_dump(mode="python") != selected_candidate.model_dump(mode="python"):
        raise StrategyV2DecisionError(
            f"Selected angle payload for '{decision.selected_angle.angle_id}' does not match the presented candidate. "
            "Remediation: submit the exact selected angle object from v2-06 candidate payload."
        )
    decision_operator_user_id = _require_human_operator_user_id(
        operator_user_id=decision.operator_user_id,
        decision_name="Angle selection",
    )
    cleaned_reviewed_candidate_ids = _enforce_decision_integrity_policy(
        decision_name="Angle selection",
        decision_mode=decision.decision_mode,
        operator_note=decision.operator_note,
        attestation_reviewed_evidence=decision.attestation.reviewed_evidence,
        attestation_understands_impact=decision.attestation.understands_impact,
        reviewed_candidate_ids=decision.reviewed_candidate_ids,
        require_reviewed_candidates=True,
        selected_candidate_id=decision.selected_angle.angle_id,
    )
    _require_stage1_quality(stage1)
    _require_selected_angle_evidence_quality(selected_angle=decision.selected_angle)
    if selected_candidate_row is not None:
        _require_selected_angle_score_quality(ranked_candidate_row=selected_candidate_row)

    stage2_payload: dict[str, Any] = stage1.model_dump(mode="python")
    stage2_payload.update(
        {
            "stage": 2,
            "selected_angle": decision.selected_angle.model_dump(mode="python"),
            "compliance_constraints": {
                "overall_risk": "GREEN"
                if decision.selected_angle.evidence.contradiction_count == 0
                else "YELLOW",
                "red_flag_patterns": [],
                "platform_notes": "Use platform-safe framing from selected angle evidence.",
            },
            "buyer_behavior_archetype": "Evidence-seeking buyer",
            "purchase_emotion": "relief",
            "price_sensitivity": "medium",
        }
    )
    stage2 = validate_stage2(stage2_payload)
    stage2_data = stage2.model_dump(mode="python")

    with session_scope() as session:
        artifacts_repo = ArtifactsRepository(session)
        stage2_artifact = artifacts_repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.strategy_v2_stage2,
            data=stage2_data,
        )

        agent_run_id = _record_agent_run(
            session=session,
            org_id=org_id,
            user_id=decision_operator_user_id,
            client_id=client_id,
            objective_type="strategy_v2.angle_selection_gate",
            model="human_decision",
            inputs_json={"decision": decision.model_dump(mode="python")},
            outputs_json={"stage2": stage2_data},
        )
        step_payload_artifact_id = _persist_step_payload(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            workflow_run_id=workflow_run_id,
            step_key=V2_STEP_ANGLE_SELECTION_HITL,
            title="Strategy V2 Angle Selection HITL",
            summary="Human-selected angle applied to Stage 2 contract.",
            payload={
                "decision": {
                    **decision.model_dump(mode="python"),
                    "reviewed_candidate_ids": cleaned_reviewed_candidate_ids,
                },
                "stage2": stage2_data,
                "stage2_artifact_id": str(stage2_artifact.id),
            },
            model_name="human_decision",
            prompt_version="strategy_v2.angle_selection.v1",
            schema_version=SCHEMA_VERSION_V2,
            agent_run_id=agent_run_id,
        )
        return {
            "stage2": stage2_data,
            "stage2_artifact_id": str(stage2_artifact.id),
            "step_payload_artifact_id": step_payload_artifact_id,
        }


def _require_offer_operator_inputs(params: Mapping[str, Any]) -> dict[str, Any]:
    business_model = str(params.get("business_model") or "").strip()
    funnel_position = str(params.get("funnel_position") or "").strip()
    target_platforms_raw = params.get("target_platforms")
    target_regions_raw = params.get("target_regions")
    existing_proof_assets_raw = params.get("existing_proof_assets")
    brand_voice_notes = str(params.get("brand_voice_notes") or "").strip()

    if not business_model:
        raise StrategyV2MissingContextError(
            "Missing required Offer operator input: business_model. "
            "Remediation: provide business_model at Strategy V2 start."
        )
    if not funnel_position:
        raise StrategyV2MissingContextError(
            "Missing required Offer operator input: funnel_position. "
            "Remediation: provide funnel_position at Strategy V2 start."
        )
    if not isinstance(target_platforms_raw, list) or not any(
        isinstance(item, str) and item.strip() for item in target_platforms_raw
    ):
        raise StrategyV2MissingContextError(
            "Missing required Offer operator input: target_platforms. "
            "Remediation: provide at least one target platform at Strategy V2 start."
        )
    if not isinstance(target_regions_raw, list) or not any(
        isinstance(item, str) and item.strip() for item in target_regions_raw
    ):
        raise StrategyV2MissingContextError(
            "Missing required Offer operator input: target_regions. "
            "Remediation: provide at least one target region at Strategy V2 start."
        )
    if not isinstance(existing_proof_assets_raw, list) or not any(
        isinstance(item, str) and item.strip() for item in existing_proof_assets_raw
    ):
        raise StrategyV2MissingContextError(
            "Missing required Offer operator input: existing_proof_assets. "
            "Remediation: provide at least one proof asset note at Strategy V2 start."
        )
    if not brand_voice_notes:
        raise StrategyV2MissingContextError(
            "Missing required Offer operator input: brand_voice_notes. "
            "Remediation: provide brand_voice_notes at Strategy V2 start."
        )

    return {
        "business_model": business_model,
        "funnel_position": funnel_position,
        "target_platforms": [str(item).strip() for item in target_platforms_raw if isinstance(item, str) and item.strip()],
        "target_regions": [str(item).strip() for item in target_regions_raw if isinstance(item, str) and item.strip()],
        "existing_proof_assets": [
            str(item).strip() for item in existing_proof_assets_raw if isinstance(item, str) and item.strip()
        ],
        "brand_voice_notes": brand_voice_notes,
    }


def _tokenize_relevance_terms(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) >= 4}


def _filter_voc_for_selected_angle(
    *,
    voc_scored: Mapping[str, Any],
    voc_observations: list[dict[str, Any]],
    selected_angle: SelectedAngleContract,
) -> dict[str, Any]:
    scored_items_raw = voc_scored.get("items")
    if not isinstance(scored_items_raw, list):
        raise StrategyV2SchemaValidationError(
            "voc_scored.items is required for selected-angle VOC filtering."
        )
    scored_lookup: dict[str, dict[str, Any]] = {}
    for row in scored_items_raw:
        if isinstance(row, dict) and isinstance(row.get("voc_id"), str):
            scored_lookup[str(row["voc_id"])] = row

    selected_voc_ids = {quote.voc_id for quote in selected_angle.evidence.top_quotes}
    trigger_tokens = _tokenize_relevance_terms(selected_angle.definition.trigger)
    pain_tokens = _tokenize_relevance_terms(selected_angle.definition.pain_desire.split("->", 1)[0])

    merged_rows: list[dict[str, Any]] = []
    for row in voc_observations:
        if not isinstance(row, dict):
            continue
        voc_id = str(row.get("voc_id") or "").strip()
        if not voc_id:
            continue
        score_row = scored_lookup.get(voc_id, {})
        merged_rows.append(
            {
                **row,
                "adjusted_score": float(score_row.get("adjusted_score") or 0.0),
                "classifications": score_row.get("classifications"),
                "components": score_row.get("components"),
            }
        )
    if not merged_rows:
        raise StrategyV2MissingContextError(
            "No VOC observation rows were available for selected-angle filtering. "
            "Remediation: rerun Agent 2 and pass voc_observations into Stage 3."
        )

    def _relevance(row: Mapping[str, Any]) -> tuple[int, float]:
        score = 0
        voc_id = str(row.get("voc_id") or "")
        if voc_id in selected_voc_ids:
            score += 100
        trigger_text = " ".join(
            str(row.get(field) or "") for field in ("trigger_event", "pain_problem", "fear_risk")
        ).lower()
        tokens = _tokenize_relevance_terms(trigger_text)
        if trigger_tokens.intersection(tokens):
            score += 20
        if pain_tokens.intersection(tokens):
            score += 20
        if str(row.get("shiftable_belief") or "").upper() == "Y":
            score += 5
        if str(row.get("headline_ready") or "").upper() == "Y":
            score += 3
        return score, float(row.get("adjusted_score") or 0.0)

    ranked = sorted(merged_rows, key=_relevance, reverse=True)
    primary = [row for row in ranked if _relevance(row)[0] > 0]
    secondary = [row for row in ranked if _relevance(row)[0] == 0]

    selected_rows: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for row in primary:
        voc_id = str(row.get("voc_id"))
        if voc_id in selected_ids:
            continue
        selected_rows.append(row)
        selected_ids.add(voc_id)
        if len(selected_rows) >= 80:
            break
    if len(selected_rows) < 40:
        for row in secondary:
            voc_id = str(row.get("voc_id"))
            if voc_id in selected_ids:
                continue
            selected_rows.append(row)
            selected_ids.add(voc_id)
            if len(selected_rows) >= 40:
                break
    selected_rows = selected_rows[:80]
    if not selected_rows:
        raise StrategyV2MissingContextError(
            "Selected-angle VOC filtering produced zero items. "
            "Remediation: verify selected angle evidence voc_ids and Agent 2 VOC corpus integrity."
        )

    return {
        "items": selected_rows,
        "selection_meta": {
            "selected_angle_id": selected_angle.angle_id,
            "selected_quote_voc_ids": sorted(selected_voc_ids),
            "filtered_item_count": len(selected_rows),
        },
    }


def _derive_awareness_level_primary_from_calibration(calibration: Mapping[str, Any]) -> str:
    awareness = _require_dict(payload=calibration.get("awareness_level"), field_name="calibration.awareness_level")
    raw_candidates = [
        awareness.get("angle_specific_assessment"),
        awareness.get("primary_audience_level"),
        awareness.get("assessment"),
        awareness.get("broad_market_assessment"),
    ]
    mapping = {
        "unaware": "Unaware",
        "problem aware": "Problem-Aware",
        "problem-aware": "Problem-Aware",
        "solution aware": "Solution-Aware",
        "solution-aware": "Solution-Aware",
        "product aware": "Product-Aware",
        "product-aware": "Product-Aware",
        "most aware": "Most-Aware",
        "most-aware": "Most-Aware",
    }
    phrase_order: tuple[tuple[str, str], ...] = (
        ("most-aware", "Most-Aware"),
        ("most aware", "Most-Aware"),
        ("product-aware", "Product-Aware"),
        ("product aware", "Product-Aware"),
        ("solution-aware", "Solution-Aware"),
        ("solution aware", "Solution-Aware"),
        ("problem-aware", "Problem-Aware"),
        ("problem aware", "Problem-Aware"),
        ("unaware", "Unaware"),
    )
    for raw in raw_candidates:
        if not isinstance(raw, str):
            continue
        normalized = raw.strip().lower()
        if normalized in mapping:
            return mapping[normalized]
        hits: list[tuple[int, str]] = []
        for phrase, canonical in phrase_order:
            position = normalized.find(phrase)
            if position >= 0:
                hits.append((position, canonical))
        if hits:
            hits.sort(key=lambda item: item[0])
            return hits[0][1]
    raise StrategyV2MissingContextError(
        "Offer Step 2 calibration is missing a usable awareness assessment. "
        "Remediation: ensure step-02-market-calibration output includes awareness_level assessment fields."
    )


def _derive_sophistication_level_from_calibration(calibration: Mapping[str, Any]) -> int:
    sophistication = _require_dict(
        payload=calibration.get("sophistication_level"),
        field_name="calibration.sophistication_level",
    )
    raw_candidates = [
        sophistication.get("assessment"),
        sophistication.get("angle_specific_assessment"),
        sophistication.get("broad_market_assessment"),
    ]
    mapping = {
        "low": 1,
        "novice": 2,
        "moderate": 3,
        "medium": 3,
        "high": 4,
        "very-high": 5,
        "very high": 5,
        "exhausted": 5,
    }
    for raw in raw_candidates:
        if isinstance(raw, (int, float)):
            value = int(raw)
            if 1 <= value <= 5:
                return value
        if isinstance(raw, str):
            normalized = raw.strip().lower()
            if normalized in mapping:
                return mapping[normalized]
            digit_match = re.search(r"\b([1-5])\b", normalized)
            if digit_match:
                return int(digit_match.group(1))
            phrase_levels: tuple[tuple[str, int], ...] = (
                ("very-high", 5),
                ("very high", 5),
                ("exhausted", 5),
                ("high", 4),
                ("moderate", 3),
                ("medium", 3),
                ("novice", 2),
                ("low", 1),
            )
            hits: list[tuple[int, int]] = []
            for phrase, level in phrase_levels:
                match = re.search(rf"\b{re.escape(phrase)}\b", normalized)
                if match:
                    hits.append((match.start(), level))
            if hits:
                hits.sort(key=lambda item: item[0])
                return hits[0][1]

    claim_dimension = sophistication.get("claim_dimension")
    if isinstance(claim_dimension, dict):
        level = claim_dimension.get("level")
        if isinstance(level, (int, float)) and 1 <= int(level) <= 5:
            return int(level)
        if isinstance(level, str) and level.strip().isdigit():
            value = int(level.strip())
            if 1 <= value <= 5:
                return value

    raise StrategyV2MissingContextError(
        "Offer Step 2 calibration is missing a usable sophistication assessment. "
        "Remediation: ensure step-02-market-calibration output includes sophistication_level assessment fields."
    )


@activity.defn(name="strategy_v2.run_offer_pipeline")
def run_strategy_v2_offer_pipeline_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    workflow_run_id = str(params["workflow_run_id"])
    operator_user_id = str(params.get("operator_user_id") or "system")
    stage2 = ProductBriefStage2.model_validate(_require_dict(payload=params["stage2"], field_name="stage2"))
    _require_selected_angle_evidence_quality(selected_angle=stage2.selected_angle)
    competitor_analysis = _require_dict(payload=params["competitor_analysis"], field_name="competitor_analysis")
    voc_scored = _require_dict(payload=params["voc_scored"], field_name="voc_scored")
    voc_observations_raw = params.get("voc_observations")
    if not isinstance(voc_observations_raw, list):
        raise StrategyV2MissingContextError(
            "voc_observations is required for selected-angle Offer input mapping. "
            "Remediation: pass Agent 2 voc_observations into the offer pipeline."
        )
    voc_observations = [row for row in voc_observations_raw if isinstance(row, dict)]
    if not voc_observations:
        raise StrategyV2MissingContextError(
            "voc_observations is empty; cannot build selected-angle VOC research payload."
        )
    angle_synthesis = _require_dict(payload=params["angle_synthesis"], field_name="angle_synthesis")
    proof_asset_candidates_raw = params.get("proof_asset_candidates")
    proof_asset_candidates = (
        [row for row in proof_asset_candidates_raw if isinstance(row, dict)]
        if isinstance(proof_asset_candidates_raw, list)
        else []
    )
    operator_inputs = _require_offer_operator_inputs(params)

    compliance_sensitivity = derive_compliance_sensitivity(competitor_analysis)
    competitor_teardowns = json.dumps(competitor_analysis, ensure_ascii=True, indent=2)
    filtered_voc_payload = _filter_voc_for_selected_angle(
        voc_scored=voc_scored,
        voc_observations=voc_observations,
        selected_angle=stage2.selected_angle,
    )
    if not proof_asset_candidates:
        proof_asset_candidates = _build_proof_candidates_from_voc(
            voc_rows=[row for row in filtered_voc_payload.get("items", []) if isinstance(row, dict)],
            competitor_analysis=competitor_analysis,
        )
    voc_research = json.dumps(filtered_voc_payload, ensure_ascii=True, indent=2)
    purple_ocean_research = json.dumps(angle_synthesis, ensure_ascii=True, indent=2)

    offer_input = _map_offer_pipeline_input_with_price_resolution(
        stage2=stage2,
        selected_angle_payload=stage2.selected_angle.model_dump(mode="python"),
        competitor_teardowns=competitor_teardowns,
        voc_research=voc_research,
        purple_ocean_research=purple_ocean_research,
        business_model=operator_inputs["business_model"],
        funnel_position=operator_inputs["funnel_position"],
        target_platforms=operator_inputs["target_platforms"],
        target_regions=operator_inputs["target_regions"],
        existing_proof_assets=operator_inputs["existing_proof_assets"],
        brand_voice_notes=operator_inputs["brand_voice_notes"],
        compliance_sensitivity=compliance_sensitivity,
        llm_model=settings.STRATEGY_V2_OFFER_MODEL,
        max_iterations=2,
        score_threshold=5.5,
    )

    if True:
        prompt_vars_base = {
            "product_brief": _dump_prompt_json(offer_input.product_brief.model_dump(mode="python"), max_chars=14000),
            "selected_angle": _dump_prompt_json(offer_input.selected_angle.model_dump(mode="python"), max_chars=12000),
            "competitor_teardowns": competitor_teardowns[:24000],
            "voc_research": voc_research[:24000],
            "purple_ocean_research": purple_ocean_research[:20000],
            "product_name": stage2.product_name,
            "angle_name": stage2.selected_angle.angle_name,
        }
        orchestrator_asset = resolve_prompt_asset(
            pattern=_OFFER_ORCHESTRATOR_PROMPT_PATTERN,
            context="Offer Agent pipeline orchestrator",
        )
        missing_orchestrator_steps = [
            step_name
            for step_name in _OFFER_ORCHESTRATOR_REQUIRED_STEP_PROMPTS
            if step_name not in orchestrator_asset.text
        ]
        if missing_orchestrator_steps:
            raise StrategyV2MissingContextError(
                "Offer orchestrator prompt is missing required step references: "
                f"{missing_orchestrator_steps}. Remediation: restore canonical Offer Agent "
                "pipeline-orchestrator.md with step-01..step-05 contract links."
            )
        orchestrator_provenance = build_prompt_provenance(
            asset=orchestrator_asset,
            model_name=settings.STRATEGY_V2_OFFER_MODEL,
            input_contract_version="2.0.0",
            output_contract_version="2.0.0",
        ).to_dict()

        step01_asset = resolve_prompt_asset(
            pattern=_OFFER_STEP01_PROMPT_PATTERN,
            context="Offer Agent Step 01 Avatar Brief",
        )
        step01_parsed, step01_raw, step01_provenance = _run_prompt_json_object(
            asset=step01_asset,
            context="strategy_v2.offer.step01",
            model=settings.STRATEGY_V2_OFFER_MODEL,
            variables=prompt_vars_base,
            runtime_instruction=(
                "## Runtime Output Contract\n"
                "Generate Step 01 avatar synthesis and return a JSON object with:\n"
                "1) step_01_output: markdown string\n"
                "2) key_findings: array of strings"
            ),
            schema_name="strategy_v2_offer_step01",
            schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "step_01_output": {"type": "string"},
                    "key_findings": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["step_01_output", "key_findings"],
            },
            use_reasoning=True,
            use_web_search=False,
            heartbeat_context={
                "activity": "strategy_v2.run_offer_pipeline",
                "phase": "step01_prompt",
                "model": settings.STRATEGY_V2_OFFER_MODEL,
            },
        )
        step_01_output = str(step01_parsed.get("step_01_output") or "").strip()
        if not step_01_output:
            raise StrategyV2SchemaValidationError("Offer Step 01 prompt returned empty step_01_output.")

        step02_asset = resolve_prompt_asset(
            pattern=_OFFER_STEP02_PROMPT_PATTERN,
            context="Offer Agent Step 02 Market Calibration",
        )
        step02_vars = {
            **prompt_vars_base,
            "step_01_output": step_01_output[:20000],
        }
        step02_schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "step_02_output": {"type": "string"},
                "calibration": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "awareness_level": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {"assessment": {"type": "string"}},
                            "required": ["assessment"],
                        },
                        "sophistication_level": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {"assessment": {"type": "string"}},
                            "required": ["assessment"],
                        },
                        "lifecycle_stage": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {"assessment": {"type": "string"}},
                            "required": ["assessment"],
                        },
                        "competitor_count": {"type": "number"},
                    },
                    "required": [
                        "awareness_level",
                        "sophistication_level",
                        "lifecycle_stage",
                        "competitor_count",
                    ],
                },
                "awareness_angle_matrix": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "angle_name": {"type": "string"},
                        "awareness_framing": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "unaware": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "frame": {"type": "string"},
                                        "headline_direction": {"type": "string"},
                                        "entry_emotion": {"type": "string"},
                                        "exit_belief": {"type": "string"},
                                    },
                                    "required": ["frame", "headline_direction", "entry_emotion", "exit_belief"],
                                },
                                "problem_aware": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "frame": {"type": "string"},
                                        "headline_direction": {"type": "string"},
                                        "entry_emotion": {"type": "string"},
                                        "exit_belief": {"type": "string"},
                                    },
                                    "required": ["frame", "headline_direction", "entry_emotion", "exit_belief"],
                                },
                                "solution_aware": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "frame": {"type": "string"},
                                        "headline_direction": {"type": "string"},
                                        "entry_emotion": {"type": "string"},
                                        "exit_belief": {"type": "string"},
                                    },
                                    "required": ["frame", "headline_direction", "entry_emotion", "exit_belief"],
                                },
                                "product_aware": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "frame": {"type": "string"},
                                        "headline_direction": {"type": "string"},
                                        "entry_emotion": {"type": "string"},
                                        "exit_belief": {"type": "string"},
                                    },
                                    "required": ["frame", "headline_direction", "entry_emotion", "exit_belief"],
                                },
                                "most_aware": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "frame": {"type": "string"},
                                        "headline_direction": {"type": "string"},
                                        "entry_emotion": {"type": "string"},
                                        "exit_belief": {"type": "string"},
                                    },
                                    "required": ["frame", "headline_direction", "entry_emotion", "exit_belief"],
                                },
                            },
                            "required": [
                                "unaware",
                                "problem_aware",
                                "solution_aware",
                                "product_aware",
                                "most_aware",
                            ],
                        },
                        "constant_elements": {"type": "array", "items": {"type": "string"}},
                        "variable_elements": {"type": "array", "items": {"type": "string"}},
                        "product_name_first_appears": {"type": "string"},
                    },
                    "required": [
                        "angle_name",
                        "awareness_framing",
                        "constant_elements",
                        "variable_elements",
                        "product_name_first_appears",
                    ],
                },
            },
            "required": ["step_02_output", "calibration", "awareness_angle_matrix"],
        }

        step02_parsed: dict[str, Any] = {}
        step02_raw = ""
        step02_provenance: dict[str, str] = {}
        calibration: dict[str, Any] | None = None
        calibration_result: dict[str, Any] | None = None
        matrix_data: dict[str, Any] | None = None
        step_02_output = ""
        retry_feedback: str | None = None

        for step02_attempt in range(1, 3):
            retry_clause = ""
            if retry_feedback:
                retry_clause = (
                    "\n\n## Retry Correction\n"
                    f"The previous output failed validation: {retry_feedback}\n"
                    "Regenerate a fully populated awareness_angle_matrix with non-empty frame, "
                    "headline_direction, entry_emotion, and exit_belief for all five awareness levels."
                )
            step02_parsed, step02_raw, step02_provenance = _run_prompt_json_object(
                asset=step02_asset,
                context="strategy_v2.offer.step02",
                model=settings.STRATEGY_V2_OFFER_MODEL,
                variables=step02_vars,
                runtime_instruction=(
                    "## Runtime Input Block\n"
                    f"STEP_01_OUTPUT:\n{step_01_output[:16000]}\n\n"
                    "## Runtime Output Contract\n"
                    "Return JSON with step_02_output markdown, calibration object, and awareness_angle_matrix."
                    + retry_clause
                ),
                schema_name="strategy_v2_offer_step02",
                schema=step02_schema,
                use_reasoning=True,
                use_web_search=False,
                heartbeat_context={
                    "activity": "strategy_v2.run_offer_pipeline",
                    "phase": "step02_prompt",
                    "attempt": step02_attempt,
                    "model": settings.STRATEGY_V2_OFFER_MODEL,
                },
            )

            step_02_output = str(step02_parsed.get("step_02_output") or "").strip()
            if not step_02_output:
                raise StrategyV2SchemaValidationError("Offer Step 02 prompt returned empty step_02_output.")
            calibration = _require_dict(payload=step02_parsed.get("calibration"), field_name="step02.calibration")
            calibration_result = calibration_consistency_checker(calibration)
            try:
                matrix_data = _validate_awareness_angle_matrix_payload(
                    payload=step02_parsed.get("awareness_angle_matrix")
                ).model_dump(mode="python")
                break
            except StrategyV2SchemaValidationError as exc:
                if step02_attempt >= 2:
                    raise StrategyV2SchemaValidationError(
                        "Offer Step 02 awareness matrix failed validation after 2 attempts. "
                        f"Last error: {exc}"
                    ) from exc
                retry_feedback = str(exc)

        if calibration is None or calibration_result is None or matrix_data is None:
            raise StrategyV2SchemaValidationError(
                "Offer Step 02 did not produce a valid calibration + awareness matrix bundle."
            )

        step03_asset = resolve_prompt_asset(
            pattern=_OFFER_STEP03_PROMPT_PATTERN,
            context="Offer Agent Step 03 UMP/UMS Generation",
        )
        step03_vars = {
            **prompt_vars_base,
            "step_01_output": step_01_output[:20000],
            "step_02_output": step_02_output[:20000],
        }
        step03_parsed, step03_raw, step03_provenance = _run_prompt_json_object(
            asset=step03_asset,
            context="strategy_v2.offer.step03",
            model=settings.STRATEGY_V2_OFFER_MODEL,
            variables=step03_vars,
            runtime_instruction=(
                "## Runtime Input Block\n"
                f"STEP_01_OUTPUT:\n{step_01_output[:12000]}\n\n"
                f"STEP_02_OUTPUT:\n{step_02_output[:12000]}\n\n"
                "## Runtime Output Contract\n"
                "Return a JSON object with a `pairs` array (3-5 UMP/UMS pairs), each including all 7 dimensions."
            ),
            schema_name="strategy_v2_offer_step03",
            schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "pairs": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 5,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "pair_id": {"type": "string"},
                                "ump_name": {"type": "string"},
                                "ums_name": {"type": "string"},
                                "dimensions": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "competitive_uniqueness": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "score": {"type": "number"},
                                                "evidence_quality": {
                                                    "type": "string",
                                                    "enum": ["OBSERVED", "INFERRED", "ASSUMED"],
                                                },
                                            },
                                            "required": ["score", "evidence_quality"],
                                        },
                                        "voc_groundedness": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "score": {"type": "number"},
                                                "evidence_quality": {
                                                    "type": "string",
                                                    "enum": ["OBSERVED", "INFERRED", "ASSUMED"],
                                                },
                                            },
                                            "required": ["score", "evidence_quality"],
                                        },
                                        "believability": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "score": {"type": "number"},
                                                "evidence_quality": {
                                                    "type": "string",
                                                    "enum": ["OBSERVED", "INFERRED", "ASSUMED"],
                                                },
                                            },
                                            "required": ["score", "evidence_quality"],
                                        },
                                        "mechanism_clarity": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "score": {"type": "number"},
                                                "evidence_quality": {
                                                    "type": "string",
                                                    "enum": ["OBSERVED", "INFERRED", "ASSUMED"],
                                                },
                                            },
                                            "required": ["score", "evidence_quality"],
                                        },
                                        "angle_alignment": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "score": {"type": "number"},
                                                "evidence_quality": {
                                                    "type": "string",
                                                    "enum": ["OBSERVED", "INFERRED", "ASSUMED"],
                                                },
                                            },
                                            "required": ["score", "evidence_quality"],
                                        },
                                        "compliance_safety": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "score": {"type": "number"},
                                                "evidence_quality": {
                                                    "type": "string",
                                                    "enum": ["OBSERVED", "INFERRED", "ASSUMED"],
                                                },
                                            },
                                            "required": ["score", "evidence_quality"],
                                        },
                                        "memorability": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "score": {"type": "number"},
                                                "evidence_quality": {
                                                    "type": "string",
                                                    "enum": ["OBSERVED", "INFERRED", "ASSUMED"],
                                                },
                                            },
                                            "required": ["score", "evidence_quality"],
                                        },
                                    },
                                    "required": [
                                        "competitive_uniqueness",
                                        "voc_groundedness",
                                        "believability",
                                        "mechanism_clarity",
                                        "angle_alignment",
                                        "compliance_safety",
                                        "memorability",
                                    ],
                                },
                            },
                            "required": ["pair_id", "ump_name", "ums_name", "dimensions"],
                        },
                    }
                },
                "required": ["pairs"],
            },
            use_reasoning=True,
            use_web_search=False,
            heartbeat_context={
                "activity": "strategy_v2.run_offer_pipeline",
                "phase": "step03_prompt",
                "model": settings.STRATEGY_V2_OFFER_MODEL,
            },
        )
        raw_pairs = step03_parsed.get("pairs")
        if not isinstance(raw_pairs, list) or not raw_pairs:
            raise StrategyV2SchemaValidationError("Offer Step 03 prompt returned no pairs.")
        generated_pairs: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for idx, raw_pair in enumerate(raw_pairs):
            pair = _require_dict(payload=raw_pair, field_name=f"step03.pairs[{idx}]")
            pair_id_raw = str(pair.get("pair_id") or "").strip()
            pair_id = re.sub(r"[^a-z0-9\\-]+", "-", pair_id_raw.lower()).strip("-") or f"pair-{idx + 1}"
            if pair_id in seen_ids:
                pair_id = f"{pair_id}-{idx + 1}"
            seen_ids.add(pair_id)
            dimensions_raw = _require_dict(payload=pair.get("dimensions"), field_name=f"step03.pairs[{idx}].dimensions")
            normalized_dimensions: dict[str, Any] = {}
            for dim in _UMP_UMS_DIMENSIONS:
                dim_data = _require_dict(
                    payload=dimensions_raw.get(dim),
                    field_name=f"step03.pairs[{idx}].dimensions.{dim}",
                )
                normalized_dimensions[dim] = {
                    "score": _normalize_score_1_10(
                        dim_data.get("score"),
                        field_name=f"step03.pairs[{idx}].{dim}.score",
                    ),
                    "evidence_quality": _normalize_evidence_quality(
                        dim_data.get("evidence_quality"),
                        field_name=f"step03.pairs[{idx}].{dim}.evidence_quality",
                    ),
                }
            generated_pairs.append(
                {
                    "pair_id": pair_id,
                    "ump_name": str(pair.get("ump_name") or "").strip(),
                    "ums_name": str(pair.get("ums_name") or "").strip(),
                    "dimensions": normalized_dimensions,
                }
            )

        pair_scoring = ump_ums_scorer(generated_pairs)
        if not isinstance(pair_scoring.get("ranked_pairs"), list) or not pair_scoring.get("ranked_pairs"):
            raise StrategyV2MissingContextError(
                "UMP/UMS scoring returned no ranked pairs. "
                "Remediation: rerun offer pipeline with valid generated pair candidates."
            )

        with session_scope() as session:
            artifacts_repo = ArtifactsRepository(session)
            matrix_artifact = artifacts_repo.insert(
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                artifact_type=ArtifactTypeEnum.strategy_v2_awareness_angle_matrix,
                data=matrix_data,
            )
            agent_run_id = _record_agent_run(
                session=session,
                org_id=org_id,
                user_id=operator_user_id,
                client_id=client_id,
                objective_type="strategy_v2.offer_pipeline.prompt_chain",
                model=settings.STRATEGY_V2_OFFER_MODEL,
                inputs_json={"stage2": stage2.model_dump(mode="python")},
                outputs_json={
                    "calibration": calibration,
                    "calibration_result": calibration_result,
                    "generated_pairs": generated_pairs,
                    "pair_scoring": pair_scoring,
                },
            )
            payload = {
                "offer_input": offer_input.model_dump(mode="python"),
                "calibration": calibration,
                "calibration_result": calibration_result,
                "awareness_angle_matrix": matrix_data,
                "generated_pairs": generated_pairs,
                "pair_scoring": pair_scoring,
                "compliance_sensitivity": compliance_sensitivity,
                "selected_angle_voc": filtered_voc_payload.get("selection_meta"),
                "proof_asset_candidates": proof_asset_candidates,
                "awareness_matrix_artifact_id": str(matrix_artifact.id),
                "offer_prompt_chain": {
                    "orchestrator_spec_excerpt": orchestrator_asset.text[:12000],
                    "orchestrator_prompt_provenance": orchestrator_provenance,
                    "step_01_output": step_01_output,
                    "step_02_output": step_02_output,
                    "step_03_output_raw": step03_raw[:30000],
                    "prompt_provenance": {
                        "step_01": step01_provenance,
                        "step_02": step02_provenance,
                        "step_03": step03_provenance,
                    },
                },
            }
            step_payload_artifact_id = _persist_step_payload(
                session=session,
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                workflow_run_id=workflow_run_id,
                step_key=V2_STEP_OFFER_PIPELINE,
                title="Strategy V2 Offer Pipeline",
                summary="Offer prompt-chain calibration complete and UMP/UMS pairs ranked.",
                payload=payload,
                model_name=settings.STRATEGY_V2_OFFER_MODEL,
                prompt_version="strategy_v2.offer_pipeline.prompt_chain.v2",
                schema_version=SCHEMA_VERSION_V2,
                agent_run_id=agent_run_id,
            )
            payload["step_payload_artifact_id"] = step_payload_artifact_id
            return payload

@activity.defn(name="strategy_v2.build_offer_variants")
def build_strategy_v2_offer_variants_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    workflow_run_id = str(params["workflow_run_id"])
    stage2 = ProductBriefStage2.model_validate(_require_dict(payload=params["stage2"], field_name="stage2"))
    offer_pipeline_output = _require_dict(payload=params["offer_pipeline_output"], field_name="offer_pipeline_output")
    decision = UmpUmsSelectionDecision.model_validate(
        _require_dict(payload=params["ump_ums_selection_decision"], field_name="ump_ums_selection_decision")
    )
    decision_operator_user_id = _require_human_operator_user_id(
        operator_user_id=decision.operator_user_id,
        decision_name="UMP/UMS selection",
    )
    cleaned_reviewed_candidate_ids = _enforce_decision_integrity_policy(
        decision_name="UMP/UMS selection",
        decision_mode=decision.decision_mode,
        operator_note=decision.operator_note,
        attestation_reviewed_evidence=decision.attestation.reviewed_evidence,
        attestation_understands_impact=decision.attestation.understands_impact,
        reviewed_candidate_ids=decision.reviewed_candidate_ids,
        require_reviewed_candidates=True,
        selected_candidate_id=decision.pair_id,
    )

    pair_scoring = _require_dict(payload=offer_pipeline_output.get("pair_scoring"), field_name="pair_scoring")
    ranked_pairs_raw = pair_scoring.get("ranked_pairs")
    if not isinstance(ranked_pairs_raw, list):
        raise StrategyV2MissingContextError(
            "Offer pipeline ranked pairs are missing. Remediation: rerun step v2-08 before selecting UMP/UMS."
        )
    selected_pair = None
    for pair in ranked_pairs_raw:
        if isinstance(pair, dict) and str(pair.get("pair_id")) == decision.pair_id:
            selected_pair = pair
            break
    if not isinstance(selected_pair, dict):
        raise StrategyV2DecisionError(
            f"Selected UMP/UMS pair '{decision.pair_id}' was not found in ranked pairs."
        )

    offer_input_payload = _require_dict(
        payload=offer_pipeline_output.get("offer_input"),
        field_name="offer_pipeline_output.offer_input",
    )
    offer_config = _require_dict(
        payload=offer_input_payload.get("config"),
        field_name="offer_pipeline_output.offer_input.config",
    )
    raw_threshold = offer_config.get("score_threshold")
    raw_max_iterations = offer_config.get("max_iterations")
    if not isinstance(raw_threshold, (int, float)):
        raise StrategyV2SchemaValidationError("offer_input.config.score_threshold must be numeric.")
    if not isinstance(raw_max_iterations, int):
        raise StrategyV2SchemaValidationError("offer_input.config.max_iterations must be an integer.")
    score_threshold = float(raw_threshold)
    max_iterations = max(1, raw_max_iterations)

    competitor_teardowns_text = str(offer_input_payload.get("competitor_teardowns") or "").strip()
    voc_research_text = str(offer_input_payload.get("voc_research") or "").strip()
    if not competitor_teardowns_text or not voc_research_text:
        raise StrategyV2MissingContextError(
            "Offer pipeline output is missing competitor_teardowns/voc_research context for variant generation."
        )
    competitor_analysis = _parse_json_response(
        raw_text=competitor_teardowns_text,
        field_name="offer_input.competitor_teardowns",
    )
    voc_scored = _parse_json_response(
        raw_text=voc_research_text,
        field_name="offer_input.voc_research",
    )

    if True:
        offer_prompt_chain = _require_dict(
            payload=offer_pipeline_output.get("offer_prompt_chain"),
            field_name="offer_pipeline_output.offer_prompt_chain",
        )
        orchestrator_prompt_provenance = _require_dict(
            payload=offer_prompt_chain.get("orchestrator_prompt_provenance"),
            field_name="offer_pipeline_output.offer_prompt_chain.orchestrator_prompt_provenance",
        )
        if not str(orchestrator_prompt_provenance.get("prompt_path") or "").strip():
            raise StrategyV2MissingContextError(
                "Offer prompt-chain orchestrator provenance is missing prompt_path. "
                "Remediation: rerun step v2-08 so Step 04/05 execute under canonical orchestrator control."
            )
        orchestrator_spec_excerpt = str(offer_prompt_chain.get("orchestrator_spec_excerpt") or "").strip()
        if not orchestrator_spec_excerpt:
            raise StrategyV2MissingContextError(
                "Offer prompt-chain orchestrator excerpt is missing. "
                "Remediation: rerun step v2-08 and persist orchestrator contract metadata."
            )
        step_01_output = str(offer_prompt_chain.get("step_01_output") or "").strip()
        step_02_output = str(offer_prompt_chain.get("step_02_output") or "").strip()
        if not step_01_output or not step_02_output:
            raise StrategyV2MissingContextError(
                "Offer prompt-chain Step 01/02 outputs are required for Step 04 construction. "
                "Remediation: rerun offer pipeline to regenerate complete prompt-chain outputs."
            )

        purple_ocean_research = str(offer_input_payload.get("purple_ocean_research") or "").strip()
        if not purple_ocean_research:
            raise StrategyV2MissingContextError(
                "offer_input.purple_ocean_research is required for Offer Step 04 prompt execution."
            )

        iteration = 1
        revision_guidance: str | None = None
        scored_variants: list[dict[str, Any]] = []
        composite_results: dict[str, Any] = {}
        generated_variant_inputs: list[dict[str, Any]] = []
        prompt_chain_iterations: list[dict[str, Any]] = []

        step04_asset = resolve_prompt_asset(
            pattern=_OFFER_STEP04_PROMPT_PATTERN,
            context="Offer Agent Step 04 Offer Construction",
        )
        step05_asset = resolve_prompt_asset(
            pattern=_OFFER_STEP05_PROMPT_PATTERN,
            context="Offer Agent Step 05 Evaluation",
        )

        while True:
            step04_vars = {
                "product_brief": _dump_prompt_json(offer_input_payload.get("product_brief", {}), max_chars=14000),
                "selected_angle": _dump_prompt_json(stage2.selected_angle.model_dump(mode="python"), max_chars=12000),
                "competitor_teardowns": competitor_teardowns_text[:22000],
                "voc_research": voc_research_text[:22000],
                "purple_ocean_research": purple_ocean_research[:18000],
                "step_01_output": step_01_output[:20000],
                "step_02_output": step_02_output[:20000],
                "selected_ump_ums": _dump_prompt_json(selected_pair, max_chars=6000),
                "revision_notes": (revision_guidance or "First run — no revision notes"),
                "product_name": stage2.product_name,
                "angle_name": stage2.selected_angle.angle_name,
            }
            step04_parsed, step04_raw, step04_provenance = _run_prompt_json_object(
                asset=step04_asset,
                context="strategy_v2.offer.step04",
                model=settings.STRATEGY_V2_OFFER_MODEL,
                variables=step04_vars,
                runtime_instruction=(
                    "## Runtime Input Block\n"
                    f"STEP_01_OUTPUT:\n{step_01_output[:12000]}\n\n"
                    f"STEP_02_OUTPUT:\n{step_02_output[:12000]}\n\n"
                    "## Runtime Output Contract\n"
                    "Return JSON with `variants` array for ids base, variant_a, variant_b.\n"
                    "Each variant must include core_promise, value_stack (with scoring levers), "
                    "guarantee, pricing_rationale, objection_map, and dimension_scores."
                ),
                schema_name="strategy_v2_offer_step04",
                schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "variants": {
                            "type": "array",
                            "minItems": 3,
                            "maxItems": 3,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "variant_id": {"type": "string"},
                                    "core_promise": {"type": "string"},
                                    "value_stack": {
                                        "type": "array",
                                        "minItems": 3,
                                        "maxItems": 7,
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "name": {"type": "string"},
                                                "dream_outcome": {"type": "number"},
                                                "perceived_likelihood": {"type": "number"},
                                                "time_delay": {"type": "number"},
                                                "effort_sacrifice": {"type": "number"},
                                                "novelty_classification": {"type": "string"},
                                            },
                                            "required": [
                                                "name",
                                                "dream_outcome",
                                                "perceived_likelihood",
                                                "time_delay",
                                                "effort_sacrifice",
                                                "novelty_classification",
                                            ],
                                        },
                                    },
                                    "guarantee": {"type": "string"},
                                    "pricing_rationale": {"type": "string"},
                                    "objection_map": {
                                        "type": "array",
                                        "minItems": 3,
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "objection": {"type": "string"},
                                                "source": {"type": "string"},
                                                "covered": {"type": "boolean"},
                                                "coverage_strength": {"type": "number"},
                                            },
                                            "required": ["objection", "source", "covered", "coverage_strength"],
                                        },
                                    },
                                    "dimension_scores": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "properties": {
                                            "competitive_differentiation": {"type": "number"},
                                            "compliance_safety": {"type": "number"},
                                            "internal_consistency": {"type": "number"},
                                            "clarity_simplicity": {"type": "number"},
                                            "bottleneck_resilience": {"type": "number"},
                                            "momentum_continuity": {"type": "number"},
                                        },
                                        "required": [
                                            "competitive_differentiation",
                                            "compliance_safety",
                                            "internal_consistency",
                                            "clarity_simplicity",
                                            "bottleneck_resilience",
                                            "momentum_continuity",
                                        ],
                                    },
                                },
                                "required": [
                                    "variant_id",
                                    "core_promise",
                                    "value_stack",
                                    "guarantee",
                                    "pricing_rationale",
                                    "objection_map",
                                    "dimension_scores",
                                ],
                            },
                        }
                    },
                    "required": ["variants"],
                },
                use_reasoning=True,
                use_web_search=False,
                heartbeat_context={
                    "activity": "strategy_v2.build_offer_variants",
                    "phase": "step04_prompt",
                    "iteration": iteration,
                    "model": settings.STRATEGY_V2_OFFER_MODEL,
                },
            )

            raw_variants = step04_parsed.get("variants")
            if not isinstance(raw_variants, list):
                raise StrategyV2SchemaValidationError("Offer Step 04 output is missing variants array.")
            by_id: dict[str, dict[str, Any]] = {}
            for idx, raw_variant in enumerate(raw_variants):
                variant = _require_dict(payload=raw_variant, field_name=f"variants[{idx}]")
                variant_id = str(variant.get("variant_id") or "").strip().lower()
                if variant_id not in _OFFER_VARIANT_IDS:
                    raise StrategyV2SchemaValidationError(
                        f"Invalid variant_id '{variant_id}'. Expected exactly: {', '.join(_OFFER_VARIANT_IDS)}."
                    )
                value_stack_raw = variant.get("value_stack")
                if not isinstance(value_stack_raw, list) or not value_stack_raw:
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' is missing value_stack entries."
                    )
                normalized_stack: list[dict[str, Any]] = []
                novelty_rows: list[dict[str, Any]] = []
                for element_idx, raw_element in enumerate(value_stack_raw):
                    element = _require_dict(
                        payload=raw_element,
                        field_name=f"variants[{idx}].value_stack[{element_idx}]",
                    )
                    element_name = str(element.get("name") or "").strip()
                    if not element_name:
                        raise StrategyV2SchemaValidationError(
                            f"variants[{idx}].value_stack[{element_idx}].name is required."
                        )
                    novelty_class = _normalize_novelty_classification(
                        element.get("novelty_classification"),
                        field_name=f"{variant_id}.novelty_classification",
                    )
                    normalized_stack.append(
                        {
                            "name": element_name,
                            "hormozi_levers": {
                                "dream_outcome": _normalize_score_1_10(
                                    element.get("dream_outcome"),
                                    field_name=f"{variant_id}.dream_outcome",
                                ),
                                "perceived_likelihood": _normalize_score_1_10(
                                    element.get("perceived_likelihood"),
                                    field_name=f"{variant_id}.perceived_likelihood",
                                ),
                                "time_delay": _normalize_score_1_10(
                                    element.get("time_delay"),
                                    field_name=f"{variant_id}.time_delay",
                                ),
                                "effort_sacrifice": _normalize_score_1_10(
                                    element.get("effort_sacrifice"),
                                    field_name=f"{variant_id}.effort_sacrifice",
                                ),
                            },
                        }
                    )
                    novelty_rows.append({"element_name": element_name, "classification": novelty_class})

                objection_map_raw = variant.get("objection_map")
                if not isinstance(objection_map_raw, list) or not objection_map_raw:
                    raise StrategyV2SchemaValidationError(f"Variant '{variant_id}' objection_map is required.")
                normalized_objections: list[dict[str, Any]] = []
                for objection_idx, objection_raw in enumerate(objection_map_raw):
                    objection = _require_dict(
                        payload=objection_raw,
                        field_name=f"variants[{idx}].objection_map[{objection_idx}]",
                    )
                    normalized_objections.append(
                        {
                            "objection": str(objection.get("objection") or "").strip(),
                            "source": str(objection.get("source") or "").strip() or "inferred",
                            "covered": bool(objection.get("covered")),
                            "coverage_strength": _normalize_score_1_10(
                                objection.get("coverage_strength"),
                                field_name=f"{variant_id}.coverage_strength",
                            ),
                        }
                    )

                dimension_scores = _require_dict(
                    payload=variant.get("dimension_scores"),
                    field_name=f"variants[{idx}].dimension_scores",
                )
                by_id[variant_id] = {
                    "variant_id": variant_id,
                    "core_promise": str(variant.get("core_promise") or "").strip(),
                    "value_stack": [row["name"] for row in normalized_stack],
                    "value_stack_scoring": normalized_stack,
                    "novelty_rows": novelty_rows,
                    "guarantee": str(variant.get("guarantee") or "").strip(),
                    "pricing_rationale": str(variant.get("pricing_rationale") or "").strip(),
                    "objection_map": normalized_objections,
                    "dimension_scores": {
                        "competitive_differentiation": _normalize_score_1_10(
                            dimension_scores.get("competitive_differentiation"),
                            field_name=f"{variant_id}.competitive_differentiation",
                        ),
                        "compliance_safety": _normalize_score_1_10(
                            dimension_scores.get("compliance_safety"),
                            field_name=f"{variant_id}.compliance_safety",
                        ),
                        "internal_consistency": _normalize_score_1_10(
                            dimension_scores.get("internal_consistency"),
                            field_name=f"{variant_id}.internal_consistency",
                        ),
                        "clarity_simplicity": _normalize_score_1_10(
                            dimension_scores.get("clarity_simplicity"),
                            field_name=f"{variant_id}.clarity_simplicity",
                        ),
                        "bottleneck_resilience": _normalize_score_1_10(
                            dimension_scores.get("bottleneck_resilience"),
                            field_name=f"{variant_id}.bottleneck_resilience",
                        ),
                        "momentum_continuity": _normalize_score_1_10(
                            dimension_scores.get("momentum_continuity"),
                            field_name=f"{variant_id}.momentum_continuity",
                        ),
                    },
                }
            missing_ids = [variant_id for variant_id in _OFFER_VARIANT_IDS if variant_id not in by_id]
            if missing_ids:
                raise StrategyV2SchemaValidationError(
                    f"Offer Step 04 did not return required variant ids: {missing_ids}."
                )
            generated_variant_inputs = [by_id["base"], by_id["variant_a"], by_id["variant_b"]]

            scored_variants = []
            evaluation_variants: list[dict[str, Any]] = []
            for variant in generated_variant_inputs:
                value_score = hormozi_scorer({"elements": variant["value_stack_scoring"]})
                objection_score = objection_coverage_calculator({"objections": variant["objection_map"]})
                novelty_score = novelty_calculator({"classifications": variant["novelty_rows"]})
                dimensions = variant["dimension_scores"]
                scored_variants.append(
                    {
                        "variant_id": variant["variant_id"],
                        "core_promise": variant["core_promise"],
                        "value_stack": variant["value_stack"],
                        "guarantee": variant["guarantee"],
                        "pricing_rationale": variant["pricing_rationale"],
                        "value_score": value_score,
                        "objection_score": objection_score,
                        "novelty_score": novelty_score,
                        "dimension_scores": dimensions,
                    }
                )
                evaluation_variants.append(
                    {
                        "variant_id": variant["variant_id"],
                        "dimensions": {
                            "value_equation": {
                                "raw_score": float(value_score.get("aggregate_value_score", 0.0)),
                                "evidence_quality": "INFERRED",
                            },
                            "objection_coverage": {
                                "raw_score": float(objection_score.get("coverage_pct", 0.0)) / 10.0,
                                "evidence_quality": "OBSERVED",
                            },
                            "competitive_differentiation": {
                                "raw_score": float(dimensions["competitive_differentiation"]),
                                "evidence_quality": "INFERRED",
                            },
                            "compliance_safety": {
                                "raw_score": float(dimensions["compliance_safety"]),
                                "evidence_quality": "OBSERVED",
                            },
                            "internal_consistency": {
                                "raw_score": float(dimensions["internal_consistency"]),
                                "evidence_quality": "INFERRED",
                            },
                            "clarity_simplicity": {
                                "raw_score": float(dimensions["clarity_simplicity"]),
                                "evidence_quality": "INFERRED",
                            },
                            "bottleneck_resilience": {
                                "raw_score": float(dimensions["bottleneck_resilience"]),
                                "evidence_quality": "INFERRED",
                            },
                            "momentum_continuity": {
                                "raw_score": float(dimensions["momentum_continuity"]),
                                "evidence_quality": "INFERRED",
                            },
                        },
                    }
                )

            step05_vars = {
                "competitor_teardowns": competitor_teardowns_text[:22000],
                "step_01_output": step_01_output[:20000],
                "step_02_output": step_02_output[:20000],
                "selected_ump_ums": _dump_prompt_json(selected_pair, max_chars=6000),
                "step_04_output": _dump_prompt_json({"variants": generated_variant_inputs}, max_chars=30000),
                "product_name": stage2.product_name,
                "angle_name": stage2.selected_angle.angle_name,
            }
            step05_parsed, step05_raw, step05_provenance = _run_prompt_json_object(
                asset=step05_asset,
                context="strategy_v2.offer.step05",
                model=settings.STRATEGY_V2_OFFER_MODEL,
                variables=step05_vars,
                runtime_instruction=(
                    "## Runtime Input Block\n"
                    f"STEP_01_OUTPUT:\n{step_01_output[:10000]}\n\n"
                    f"STEP_02_OUTPUT:\n{step_02_output[:10000]}\n\n"
                    f"STEP_04_OUTPUT_JSON:\n{_dump_prompt_json({'variants': generated_variant_inputs}, max_chars=30000)}\n\n"
                    "## Runtime Output Contract\n"
                    "Return JSON with `evaluation` object (variants + dimensions) and `revision_notes` text."
                ),
                schema_name="strategy_v2_offer_step05",
                schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "evaluation": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "variants": {
                                    "type": "array",
                                    "minItems": 1,
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "properties": {
                                            "variant_id": {"type": "string"},
                                            "dimensions": {"type": "object", "additionalProperties": True},
                                        },
                                        "required": ["variant_id", "dimensions"],
                                    },
                                }
                            },
                            "required": ["variants"],
                        },
                        "revision_notes": {"type": "string"},
                    },
                    "required": ["evaluation", "revision_notes"],
                },
                use_reasoning=True,
                use_web_search=False,
                heartbeat_context={
                    "activity": "strategy_v2.build_offer_variants",
                    "phase": "step05_prompt",
                    "iteration": iteration,
                    "model": settings.STRATEGY_V2_OFFER_MODEL,
                },
            )
            evaluation = _require_dict(payload=step05_parsed.get("evaluation"), field_name="step05.evaluation")
            composite_results = composite_scorer(
                evaluation,
                {
                    "score_threshold": score_threshold,
                    "current_iteration": iteration,
                    "max_iterations": max_iterations,
                },
            )
            prompt_chain_iterations.append(
                {
                    "iteration": iteration,
                    "step_04_provenance": step04_provenance,
                    "step_05_provenance": step05_provenance,
                    "step_04_raw_output": step04_raw[:24000],
                    "step_05_raw_output": step05_raw[:24000],
                }
            )
            if bool(composite_results.get("any_passing")) or iteration >= max_iterations:
                break

            revision_text = str(step05_parsed.get("revision_notes") or "").strip()
            if not revision_text:
                raise StrategyV2SchemaValidationError(
                    "Offer Step 05 returned empty revision_notes while revision is required."
                )
            revision_guidance = revision_text
            iteration += 1

        with session_scope() as session:
            agent_run_id = _record_agent_run(
                session=session,
                org_id=org_id,
                user_id=decision_operator_user_id,
                client_id=client_id,
                objective_type="strategy_v2.offer_variant_generation_scoring.prompt_chain",
                model=settings.STRATEGY_V2_OFFER_MODEL,
                inputs_json={"selected_pair": selected_pair},
                outputs_json={
                    "iteration_count": iteration,
                    "composite": composite_results,
                    "variant_count": len(scored_variants),
                },
            )
            payload = {
                "selected_pair": selected_pair,
                "ump_ums_decision": {
                    **decision.model_dump(mode="python"),
                    "reviewed_candidate_ids": cleaned_reviewed_candidate_ids,
                },
                "iteration_count": iteration,
                "max_iterations": max_iterations,
                "score_threshold": score_threshold,
                "generated_variant_inputs": generated_variant_inputs,
                "variants": scored_variants,
                "composite_results": composite_results,
                "orchestrator_prompt_provenance": orchestrator_prompt_provenance,
                "orchestrator_spec_excerpt": orchestrator_spec_excerpt,
                "offer_prompt_chain_iterations": prompt_chain_iterations,
            }
            step_payload_artifact_id = _persist_step_payload(
                session=session,
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                workflow_run_id=workflow_run_id,
                step_key=V2_STEP_OFFER_VARIANT_SCORING,
                title="Strategy V2 Offer Variant Scoring",
                summary="Offer prompt-chain variants scored and ranked for winner selection.",
                payload=payload,
                model_name=settings.STRATEGY_V2_OFFER_MODEL,
                prompt_version="strategy_v2.offer_variants.prompt_chain.v2",
                schema_version=SCHEMA_VERSION_V2,
                agent_run_id=agent_run_id,
            )
            payload["step_payload_artifact_id"] = step_payload_artifact_id
            return payload

@activity.defn(name="strategy_v2.finalize_offer_winner")
def finalize_strategy_v2_offer_winner_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    onboarding_payload_id = (
        str(params["onboarding_payload_id"])
        if isinstance(params.get("onboarding_payload_id"), str)
        else None
    )
    workflow_run_id = str(params["workflow_run_id"])
    stage2 = ProductBriefStage2.model_validate(_require_dict(payload=params["stage2"], field_name="stage2"))
    _require_selected_angle_evidence_quality(selected_angle=stage2.selected_angle)
    offer_variants_output = _require_dict(payload=params["offer_variants_output"], field_name="offer_variants_output")
    offer_pipeline_output = _require_dict(payload=params["offer_pipeline_output"], field_name="offer_pipeline_output")
    decision = OfferWinnerSelectionDecision.model_validate(
        _require_dict(payload=params["offer_winner_decision"], field_name="offer_winner_decision")
    )
    decision_operator_user_id = _require_human_operator_user_id(
        operator_user_id=decision.operator_user_id,
        decision_name="Offer winner selection",
    )
    cleaned_reviewed_candidate_ids = _enforce_decision_integrity_policy(
        decision_name="Offer winner selection",
        decision_mode=decision.decision_mode,
        operator_note=decision.operator_note,
        attestation_reviewed_evidence=decision.attestation.reviewed_evidence,
        attestation_understands_impact=decision.attestation.understands_impact,
        reviewed_candidate_ids=decision.reviewed_candidate_ids,
        require_reviewed_candidates=True,
        selected_candidate_id=decision.variant_id,
    )
    brand_voice_notes_raw = str(params.get("brand_voice_notes") or "")
    compliance_notes_raw = str(params.get("compliance_notes") or "")
    onboarding_payload: Mapping[str, Any] | None = None
    if onboarding_payload_id:
        with session_scope() as session:
            onboarding_payload = _load_onboarding_payload(
                session=session,
                org_id=org_id,
                client_id=client_id,
                onboarding_payload_id=onboarding_payload_id,
            )

    variants_raw = offer_variants_output.get("variants")
    if not isinstance(variants_raw, list):
        raise StrategyV2MissingContextError(
            "Offer variants are missing before final winner selection. "
            "Remediation: complete offer variant scoring first."
        )
    selected_variant = None
    for variant in variants_raw:
        if isinstance(variant, dict) and str(variant.get("variant_id")) == decision.variant_id:
            selected_variant = variant
            break
    if not isinstance(selected_variant, dict):
        raise StrategyV2DecisionError(
            f"Selected offer variant '{decision.variant_id}' was not found in scored variants."
        )

    selected_pair = _require_dict(payload=offer_variants_output.get("selected_pair"), field_name="selected_pair")
    composite_results = _require_dict(
        payload=offer_variants_output.get("composite_results"),
        field_name="composite_results",
    )
    variant_scores_raw = composite_results.get("variants")
    variant_scores: list[dict[str, Any]] = []
    if isinstance(variant_scores_raw, list):
        for item in variant_scores_raw:
            if isinstance(item, dict):
                variant_scores.append(item)
    selected_variant_score = next(
        (row for row in variant_scores if str(row.get("variant_id")) == decision.variant_id),
        None,
    )
    if not isinstance(selected_variant_score, dict):
        raise StrategyV2MissingContextError(
            "Missing composite score row for selected variant. "
            "Remediation: verify composite_scorer output before winner selection."
        )
    calibration = _require_dict(payload=offer_pipeline_output.get("calibration"), field_name="calibration")
    awareness_level_primary = _derive_awareness_level_primary_from_calibration(calibration)
    sophistication_level = _derive_sophistication_level_from_calibration(calibration)

    stage3_payload: dict[str, Any] = stage2.model_dump(mode="python")
    stage3_payload.update(
        {
            "stage": 3,
            "ump": str(selected_pair.get("ump_name") or ""),
            "ums": str(selected_pair.get("ums_name") or ""),
            "core_promise": str(selected_variant.get("core_promise") or ""),
            "value_stack_summary": list(selected_variant.get("value_stack") or []),
            "guarantee_type": str(selected_variant.get("guarantee") or ""),
            "pricing_rationale": str(selected_variant.get("pricing_rationale") or ""),
            "awareness_level_primary": awareness_level_primary,
            "sophistication_level": sophistication_level,
            "composite_score": float(selected_variant_score.get("composite_safety_adjusted") or 0.0),
            "variant_selected": decision.variant_id,
        }
    )
    stage3 = validate_stage3(stage3_payload)
    stage3_data = stage3.model_dump(mode="python")

    awareness_matrix_payload = _require_dict(
        payload=offer_pipeline_output.get("awareness_angle_matrix"),
        field_name="awareness_angle_matrix",
    )
    awareness_matrix = AwarenessAngleMatrix.model_validate(awareness_matrix_payload)
    awareness_matrix_data = awareness_matrix.model_dump(mode="python")
    offer_prompt_chain = _require_dict(
        payload=offer_pipeline_output.get("offer_prompt_chain"),
        field_name="offer_prompt_chain",
    )
    offer_prompt_provenance = _require_dict(
        payload=offer_prompt_chain.get("prompt_provenance"),
        field_name="offer_prompt_chain.prompt_provenance",
    )
    awareness_matrix_step2_provenance = _require_dict(
        payload=offer_prompt_provenance.get("step_02"),
        field_name="offer_prompt_chain.prompt_provenance.step_02",
    )
    quotes = [quote.quote for quote in stage3.selected_angle.evidence.top_quotes]
    brand_voice_notes = _resolve_brand_voice_notes(
        explicit_notes=brand_voice_notes_raw,
        onboarding_payload=onboarding_payload,
        stage2=stage2,
    )
    compliance_notes = _resolve_compliance_notes(
        explicit_notes=compliance_notes_raw,
        onboarding_payload=onboarding_payload,
        stage2=stage2,
        compliance_sensitivity=(
            str(offer_pipeline_output.get("compliance_sensitivity")).strip()
            if offer_pipeline_output.get("compliance_sensitivity") is not None
            else None
        ),
    )
    copy_context = build_copy_context_files(
        stage3=stage3,
        awareness_angle_matrix=awareness_matrix,
        brand_voice_notes=brand_voice_notes,
        compliance_notes=compliance_notes,
        voc_quotes=quotes,
    )
    copy_context_data = copy_context.model_dump(mode="python")

    with session_scope() as session:
        artifacts_repo = ArtifactsRepository(session)
        stage3_artifact = artifacts_repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.strategy_v2_stage3,
            data=stage3_data,
        )
        awareness_matrix_artifact = artifacts_repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.strategy_v2_awareness_angle_matrix,
            data=awareness_matrix_data,
        )
        offer_artifact = artifacts_repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.strategy_v2_offer,
            data={
                "stage3": stage3_data,
                "selected_variant": selected_variant,
                "selected_variant_score": selected_variant_score,
                "decision": {
                    **decision.model_dump(mode="python"),
                    "reviewed_candidate_ids": cleaned_reviewed_candidate_ids,
                },
            },
        )
        copy_context_artifact = artifacts_repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.strategy_v2_copy_context,
            data=copy_context_data,
        )

        agent_run_id = _record_agent_run(
            session=session,
            org_id=org_id,
            user_id=decision_operator_user_id,
            client_id=client_id,
            objective_type="strategy_v2.offer_winner_selection",
            model="human_decision",
            inputs_json={"decision": decision.model_dump(mode="python")},
            outputs_json={
                "stage3": stage3_data,
                "copy_context_artifact_id": str(copy_context_artifact.id),
                "awareness_matrix_artifact_id": str(awareness_matrix_artifact.id),
            },
        )
        step_payload_artifact_id = _persist_step_payload(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            workflow_run_id=workflow_run_id,
            step_key=V2_STEP_OFFER_WINNER_HITL,
            title="Strategy V2 Offer Winner HITL",
            summary="Human-selected offer winner promoted to Stage 3 and copy context.",
            payload={
                "decision": {
                    **decision.model_dump(mode="python"),
                    "reviewed_candidate_ids": cleaned_reviewed_candidate_ids,
                },
                "stage3": stage3_data,
                "stage3_artifact_id": str(stage3_artifact.id),
                "awareness_matrix": awareness_matrix_data,
                "awareness_matrix_source_step": "v2-08.step_02",
                "awareness_matrix_source_provenance": awareness_matrix_step2_provenance,
                "awareness_matrix_artifact_id": str(awareness_matrix_artifact.id),
                "offer_artifact_id": str(offer_artifact.id),
                "copy_context_artifact_id": str(copy_context_artifact.id),
            },
            model_name="human_decision",
            prompt_version="strategy_v2.offer_winner.v1",
            schema_version=SCHEMA_VERSION_V2,
            agent_run_id=agent_run_id,
        )
        return {
            "stage3": stage3_data,
            "stage3_artifact_id": str(stage3_artifact.id),
            "awareness_matrix": awareness_matrix_data,
            "awareness_matrix_artifact_id": str(awareness_matrix_artifact.id),
            "copy_context": copy_context_data,
            "copy_context_artifact_id": str(copy_context_artifact.id),
            "step_payload_artifact_id": step_payload_artifact_id,
        }


def _choose_best_headline(scored: list[dict[str, Any]]) -> dict[str, Any]:
    if not scored:
        raise StrategyV2MissingContextError(
            "No headline candidates were scored. Remediation: provide at least one valid hook starter."
        )
    ranked = sorted(
        scored,
        key=lambda row: float(_require_dict(payload=row["composite"], field_name="headline_composite").get("pct") or 0.0),
        reverse=True,
    )
    top = ranked[0]
    composite = _require_dict(payload=top["composite"], field_name="headline_composite")
    if not bool(composite.get("hard_gate_pass", False)):
        raise StrategyV2DecisionError(
            "Top headline candidate failed hard gates (BC1/BC2/BC3). "
            "Remediation: revise angle hooks or source compliant headline text."
        )
    return top


def _extract_bullet_lines(
    markdown_text: str,
    *,
    max_items: int,
    allow_plain_lines: bool = False,
) -> list[str]:
    lines: list[str] = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        value = line[2:].strip()
        if not value:
            continue
        lines.append(value)
        if len(lines) >= max_items:
            break
    if lines or not allow_plain_lines:
        return lines

    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
        if len(lines) >= max_items:
            break
    return lines


def _build_stage3_risk_headline_templates(stage3: ProductBriefStage3) -> list[str]:
    compliance_risk = str(stage3.compliance_constraints.overall_risk or "").strip().upper()
    context_blob = " ".join(
        [
            stage3.product_name,
            stage3.category_niche,
            stage3.description,
            stage3.selected_angle.angle_name,
            stage3.selected_angle.definition.pain_desire,
            stage3.selected_angle.definition.mechanism_why,
        ]
        + list(stage3.primary_icps)
    ).lower()
    has_risk_signal = any(
        token in context_blob
        for token in (
            "risk",
            "safety",
            "danger",
            "warning",
            "interaction",
            "counterfeit",
            "fake",
            "harm",
            "mislead",
        )
    )
    if compliance_risk not in {"YELLOW", "RED"} and not has_risk_signal:
        return []

    category_lower = stage3.category_niche.lower()
    if "herb" in category_lower:
        focus_phrase = "herbal guide"
    elif "supplement" in category_lower:
        focus_phrase = "supplement guide"
    elif "wellness" in category_lower:
        focus_phrase = "wellness guide"
    else:
        focus_phrase = "guide"

    audience_blob = " ".join(
        [
            stage3.selected_angle.definition.who,
            stage3.primary_segment.name,
            *stage3.primary_icps,
        ]
    ).lower()
    if any(token in audience_blob for token in ("parent", "mom", "dad", "family")):
        audience_plural = "parents"
        risk_target = "kids"
    elif any(token in audience_blob for token in ("caregiver", "carer")):
        audience_plural = "caregivers"
        risk_target = "families"
    elif "women" in audience_blob:
        audience_plural = "women"
        risk_target = "families"
    else:
        audience_plural = "buyers"
        risk_target = "buyers"

    focus_title = focus_phrase.title()
    return [
        f"New Warning: {focus_title} mistakes that put {audience_plural} at risk and why {audience_plural} miss them",
        f"Before You Trust Any {focus_title}, Check the Errors That Can Put {risk_target} at Risk",
        f"{focus_title} errors that put {risk_target} at risk and why most {audience_plural} miss the warning",
    ]


def _build_headline_candidate_pool(
    *,
    prompt_headlines: list[object],
    hook_lines: list[str],
    risk_headline_templates: list[str],
    fallback_candidates: list[str],
    max_candidates: int,
) -> list[str]:
    ordered_candidates = (
        risk_headline_templates
        + [str(item).strip() for item in prompt_headlines if isinstance(item, str) and item.strip()]
        + [line.strip() for line in hook_lines if line.strip()]
        + [candidate.strip() for candidate in fallback_candidates if candidate.strip()]
    )
    deduped = list(dict.fromkeys(item for item in ordered_candidates if item))
    if len(deduped) > max_candidates:
        return deduped[:max_candidates]
    return deduped


def _parse_h2_section_blocks(markdown: str) -> tuple[list[str], list[dict[str, Any]]]:
    prefix_lines: list[str] = []
    sections: list[dict[str, Any]] = []
    current_title: str | None = None
    current_lines: list[str] = []
    seen_h2 = False
    for raw_line in markdown.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("## "):
            seen_h2 = True
            if current_title is not None:
                sections.append({"title": current_title, "lines": list(current_lines)})
            current_title = stripped[3:].strip()
            current_lines = []
            continue
        if current_title is not None:
            current_lines.append(raw_line)
            continue
        if not seen_h2:
            prefix_lines.append(raw_line)
    if current_title is not None:
        sections.append({"title": current_title, "lines": list(current_lines)})
    return prefix_lines, sections


def _render_h2_section_blocks(prefix_lines: list[str], sections: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    if prefix_lines:
        lines.extend(prefix_lines)
        lines.append("")
    for index, section in enumerate(sections):
        title = str(section.get("title") or "").strip()
        lines.append(f"## {title}")
        section_lines = [str(line) for line in section.get("lines", [])]
        lines.extend(section_lines)
        if index < len(sections) - 1:
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def _extract_claude_message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    text_parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "text":
            continue
        chunk = str(item.get("text") or "").strip()
        if chunk:
            text_parts.append(chunk)
    return "\n".join(text_parts).strip()


def _serialize_claude_conversation(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for index, message in enumerate(messages, start=1):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip()
        if not role:
            continue
        serialized.append(
            {
                "turn": index,
                "role": role,
                "text": _extract_claude_message_text(message),
            }
        )
    return serialized


def _extract_headline_anchor_terms(headline: str, *, max_terms: int = 3) -> list[str]:
    terms: list[str] = []
    for token in re.findall(r"[a-zA-Z]{4,}", headline.lower()):
        if token in _HEADLINE_ANCHOR_STOPWORDS:
            continue
        if token in terms:
            continue
        terms.append(token)
        if len(terms) >= max_terms:
            break
    return terms


def _extract_headline_number_promise(headline: str) -> int | None:
    digit_match = re.search(r"\b(\d{1,2})\b", headline)
    if digit_match is not None:
        return int(digit_match.group(1))
    lowered = headline.lower()
    for word, value in sorted(_HEADLINE_NUMBER_WORDS.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            return value
    return None


def _headline_numeric_promise_is_compatible(
    *,
    headline: str,
    expected_item_count: int,
) -> bool:
    promised_count = _extract_headline_number_promise(headline)
    if promised_count is None:
        return True
    return promised_count == expected_item_count


def _title_contains_anchor_term(title: str, anchor_terms: list[str]) -> bool:
    lowered = title.lower()
    return any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in anchor_terms)


def _repair_markdown_headings_for_congruency(
    *,
    markdown: str,
    headline: str,
) -> str:
    anchor_terms = _extract_headline_anchor_terms(headline=headline)
    if not anchor_terms:
        return markdown
    anchor_phrase = " ".join(anchor_terms)
    prefix_lines, sections = _parse_h2_section_blocks(markdown)
    if not sections:
        return markdown

    changed = False
    for section in sections:
        title = str(section.get("title") or "").strip()
        if not title:
            continue
        if _title_contains_anchor_term(title=title, anchor_terms=anchor_terms):
            continue
        if ":" in title:
            section["title"] = f"{title} ({anchor_phrase})"
        else:
            section["title"] = f"{title}: {anchor_phrase}"
        changed = True

    if not changed:
        return markdown
    return _render_h2_section_blocks(prefix_lines, sections)


def _repair_markdown_cta_label_for_congruency(
    *,
    markdown: str,
    headline: str,
) -> str:
    anchor_terms = _extract_headline_anchor_terms(headline=headline)
    if not anchor_terms:
        return markdown
    prefix_lines, sections = _parse_h2_section_blocks(markdown)
    if not sections:
        return markdown

    cta_indices = [
        index
        for index, section in enumerate(sections)
        if "cta" in str(section.get("title") or "").lower()
    ]
    target_index = cta_indices[-1] if cta_indices else len(sections) - 1
    target_lines = [str(line) for line in sections[target_index].get("lines", [])]
    changed = False
    for line_index, line in enumerate(target_lines):
        match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", line)
        if match is None:
            continue
        anchor_text = match.group(1).strip()
        url = match.group(2).strip()
        if _title_contains_anchor_term(title=anchor_text, anchor_terms=anchor_terms):
            break
        updated_anchor = f"{anchor_text} {anchor_terms[0]}".strip()
        target_lines[line_index] = line[: match.start()] + f"[{updated_anchor}]({url})" + line[match.end() :]
        changed = True
        break

    if not changed:
        return markdown
    sections[target_index]["lines"] = target_lines
    return _render_h2_section_blocks(prefix_lines, sections)


def _repair_markdown_for_headline_term_coverage(
    *,
    markdown: str,
    headline: str,
) -> str:
    coverage_terms = _extract_headline_anchor_terms(headline=headline, max_terms=8)
    if not coverage_terms:
        return markdown

    body_lower = markdown.lower()
    missing_terms = [
        term
        for term in coverage_terms
        if not re.search(rf"\b{re.escape(term)}\b", body_lower)
    ]
    if not missing_terms:
        return markdown

    prefix_lines, sections = _parse_h2_section_blocks(markdown)
    if not sections:
        return markdown

    first_section_lines = [str(line) for line in sections[0].get("lines", [])]
    first_section_lines.extend(
        [
            "",
            f"Headline coverage terms: {', '.join(missing_terms[:6])}.",
        ]
    )
    sections[0]["lines"] = first_section_lines
    return _render_h2_section_blocks(prefix_lines, sections)


def _extract_promise_terms_for_timing_repair(
    *,
    promise_contract: Mapping[str, Any],
    max_terms: int = 6,
) -> list[str]:
    source_blob = " ".join(
        [
            str(promise_contract.get("delivery_test") or ""),
            str(promise_contract.get("specific_promise") or ""),
            str(promise_contract.get("loop_question") or ""),
        ]
    ).lower()
    terms: list[str] = []
    for token in re.findall(r"[a-zA-Z]{4,}", source_blob):
        if token in _PROMISE_TERM_STOPWORDS:
            continue
        if token in terms:
            continue
        terms.append(token)
        if len(terms) >= max_terms:
            break
    return terms


def _repair_markdown_for_promise_delivery_timing(
    *,
    markdown: str,
    promise_contract: Mapping[str, Any],
) -> str:
    prefix_lines, sections = _parse_h2_section_blocks(markdown)
    if not sections:
        return markdown

    boundary = parse_minimum_delivery_section_index(
        minimum_delivery=str(promise_contract.get("minimum_delivery") or ""),
        total_sections=len(sections),
    )
    boundary_index = max(1, min(len(sections), boundary))
    early_text = "\n".join(
        "\n".join(str(line) for line in section.get("lines", []))
        for section in sections[:boundary_index]
    ).lower()
    terms = _extract_promise_terms_for_timing_repair(promise_contract=promise_contract)
    if not terms and not _PC2_DOMAIN_REPAIR_TERMS:
        return markdown

    changed = False
    first_section_lines = [str(line) for line in sections[0].get("lines", [])]

    promise_covered_early = bool(terms) and any(
        re.search(rf"\b{re.escape(term)}\b", early_text)
        for term in terms
    )
    if terms and not promise_covered_early:
        lead_terms = ", ".join(terms[:3])
        first_section_lines.extend(
            [
                "",
                f"Promise checkpoint: {lead_terms}.",
            ]
        )
        changed = True

    body_lower = markdown.lower()
    domain_hits = sum(
        1
        for term in _PC2_DOMAIN_REPAIR_TERMS
        if re.search(rf"\b{re.escape(term)}\b", body_lower)
    )
    if domain_hits < 5:
        first_section_lines.extend(
            [
                "",
                (
                    "Safety detail: interaction risk, contraindicated use, dosing boundaries, "
                    "toxicity risk, and side-effect checks."
                ),
            ]
        )
        changed = True

    if not changed:
        return markdown

    sections[0]["lines"] = first_section_lines
    return _render_h2_section_blocks(prefix_lines, sections)


def _repair_markdown_for_congruency_and_semantics(
    *,
    markdown: str,
    headline: str,
    promise_contract: Mapping[str, Any],
) -> str:
    repaired = _repair_markdown_headings_for_congruency(markdown=markdown, headline=headline)
    repaired = _repair_markdown_cta_label_for_congruency(markdown=repaired, headline=headline)
    repaired = _repair_markdown_for_headline_term_coverage(markdown=repaired, headline=headline)
    repaired = _repair_markdown_for_promise_delivery_timing(
        markdown=repaired,
        promise_contract=promise_contract,
    )
    return repaired


def _repair_sales_markdown_for_quality(
    *,
    markdown: str,
    stage3: ProductBriefStage3,
    page_contract: Any,
) -> str:
    report = evaluate_copy_page_quality(markdown=markdown, page_contract=page_contract)
    failed_codes = {gate.reason_code for gate in report.gates if not gate.passed}
    if not failed_codes:
        return markdown

    prefix_lines, sections = _parse_h2_section_blocks(markdown)
    if not sections:
        return markdown

    changed = False
    if "SALES_PROOF_DEPTH" in failed_codes:
        proof_index = next(
            (
                index
                for index, section in enumerate(sections)
                if any(
                    token in str(section.get("title") or "").lower()
                    for token in ("proof", "testimonial", "evidence", "case")
                )
            ),
            None,
        )
        quote_lines = [
            f'- "{quote.quote.strip()}"'
            for quote in stage3.selected_angle.evidence.top_quotes
            if quote.quote.strip()
        ][:5]
        if proof_index is not None and quote_lines:
            sections[proof_index]["lines"].extend(
                [
                    "",
                    "Additional buyer evidence:",
                    *quote_lines,
                ]
            )
            changed = True

    if not changed:
        return markdown
    return _render_h2_section_blocks(prefix_lines, sections)


def _normalize_sales_cta_section_titles(
    *,
    markdown: str,
) -> str:
    prefix_lines, sections = _parse_h2_section_blocks(markdown)
    if not sections:
        return markdown

    changed = False
    social_proof_index: int | None = None
    for index, section in enumerate(sections):
        title = str(section.get("title") or "").strip().lower()
        if "social proof" in title or "proof and buyer language" in title:
            social_proof_index = index
            break
    if social_proof_index is None:
        for index, section in enumerate(sections):
            title = str(section.get("title") or "").strip().lower()
            if re.search(r"\bproof\b", title):
                social_proof_index = index
                break

    cta_indices: list[int] = []
    for index, section in enumerate(sections):
        title = str(section.get("title") or "").strip()
        if not title:
            continue
        if _NON_CTA_HEADING_RE.search(title):
            continue
        if _CTA_HEADING_ANY_RE.search(title) or _CONTINUE_TO_OFFER_HEADING_RE.search(title):
            cta_indices.append(index)

    if not cta_indices:
        return markdown

    if social_proof_index is not None:
        post_social_cta_indices = [index for index in cta_indices if index > social_proof_index]
    else:
        post_social_cta_indices = list(cta_indices)

    if social_proof_index is not None and not post_social_cta_indices and cta_indices:
        move_index = cta_indices[-1]
        moved_section = sections.pop(move_index)
        if move_index < social_proof_index:
            social_proof_index -= 1
        insert_index = min(len(sections), social_proof_index + 1)
        sections.insert(insert_index, moved_section)
        changed = True

        cta_indices = []
        for index, section in enumerate(sections):
            title = str(section.get("title") or "").strip()
            if not title:
                continue
            if _NON_CTA_HEADING_RE.search(title):
                continue
            if _CTA_HEADING_ANY_RE.search(title) or _CONTINUE_TO_OFFER_HEADING_RE.search(title):
                cta_indices.append(index)
        post_social_cta_indices = [index for index in cta_indices if index > social_proof_index]

    target_indices = post_social_cta_indices or cta_indices

    for sequence, index in enumerate(target_indices, start=1):
        section = sections[index]
        title = str(section.get("title") or "").strip()
        if _CTA_HEADING_RENUMBER_RE.search(title):
            updated_title = _CTA_HEADING_RENUMBER_RE.sub(f"CTA #{sequence}", title, count=1)
        elif _CONTINUE_TO_OFFER_HEADING_RE.search(title):
            updated_title = _CONTINUE_TO_OFFER_HEADING_RE.sub(f"CTA #{sequence}", title, count=1)
        else:
            updated_title = f"CTA #{sequence}: {title}"
        if updated_title != title:
            section["title"] = updated_title
            changed = True

    if not changed:
        return markdown
    return _render_h2_section_blocks(prefix_lines, sections)


def _normalize_heading_marker_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _extract_first_markdown_link_url(markdown: str) -> str | None:
    match = _MARKDOWN_LINK_CAPTURE_RE.search(markdown or "")
    if match is None:
        return None
    url = str(match.group(1) or "").strip()
    return url or None


def _canonicalize_section_title(*, original_title: str, canonical_title: str) -> str:
    cleaned_original = str(original_title or "").strip()
    if not cleaned_original:
        return canonical_title
    if _normalize_heading_marker_text(cleaned_original).startswith(_normalize_heading_marker_text(canonical_title)):
        return cleaned_original
    if ":" in cleaned_original:
        suffix = cleaned_original.split(":", 1)[1].strip()
        if suffix:
            return f"{canonical_title}: {suffix}"
    return canonical_title


def _build_missing_sales_section_lines(
    *,
    section_key: str,
    stage3: ProductBriefStage3,
    promise_contract: Mapping[str, Any],
    cta_url: str | None,
) -> list[str]:
    value_stack = [
        str(item).strip()
        for item in (stage3.value_stack_summary or [])
        if str(item).strip()
    ]
    if not value_stack:
        value_stack = [
            "Safety-first handbook with red-flag decision checkpoints",
            "Authenticity checklist for avoiding counterfeit sources",
            "At-home routine map with dosing boundary reminders",
        ]
    core_promise = str(
        stage3.core_promise
        or promise_contract.get("specific_promise")
        or "Safer at-home remedy decisions with less guesswork."
    ).strip()
    loop_question = str(
        promise_contract.get("loop_question")
        or "How do we avoid avoidable safety mistakes?"
    ).strip()
    delivery_test = str(
        promise_contract.get("delivery_test")
        or "Show concrete safety checks and counterfeit red flags."
    ).strip()
    guarantee_label = str(stage3.guarantee_type or "30-day confidence guarantee").strip()
    pricing_rationale = str(stage3.pricing_rationale or "").strip()
    price_label = str(stage3.price or "the listed offer price").strip()

    if section_key == "whats_inside":
        lines = ["Inside this reference stack, you get:"]
        lines.extend(f"- {item}" for item in value_stack[:4])
        lines.extend(
            [
                "",
                (
                    f"Each component is mapped to one promise: {core_promise} "
                    "without relying on random marketplace advice."
                ),
                (
                    f"We also answer the core loop question directly: {loop_question}. "
                    "That means each section points to a practical decision, not vague theory."
                ),
            ]
        )
        return lines

    if section_key == "bonus_stack":
        bonus_items = value_stack[1:4] or value_stack[:3]
        lines = ["Bonus stack and value framing:"]
        lines.extend(f"- Bonus deliverable: {item}" for item in bonus_items)
        value_line = f"The current offer is {price_label}."
        if pricing_rationale:
            value_line += f" Pricing rationale: {pricing_rationale}"
        lines.extend(
            [
                "",
                value_line,
                (
                    "Combined, these bonuses reduce guesswork when selecting sources, "
                    "checking contraindications, and deciding when to pause or skip."
                ),
            ]
        )
        return lines

    if section_key == "guarantee":
        return [
            (
                f"{guarantee_label} with explicit risk reversal: if the handbook does not deliver "
                "clearer, safer remedy decisions, request a refund under the guarantee terms."
            ),
            (
                "This guarantee is about decision clarity and practical safety boundaries, "
                "not disease-treatment claims. Use common-sense caution and follow label directions."
            ),
            (
                "If you are pregnant, managing pediatric care, or handling medication interactions, "
                "use the red-flag checks first and consult a licensed clinician or pharmacist."
            ),
        ]

    if section_key == "faq":
        return [
            (
                "**Q: How does this help with medication interactions or contraindications?**\n"
                "A: The framework highlights interaction risk and contraindication checks before use. "
                "If there is uncertainty, pause and consult a pharmacist or doctor."
            ),
            (
                "**Q: Is this medical advice for diagnosis or treatment?**\n"
                "A: No. It is a safety-first reference for at-home decision support, not a substitute for "
                "professional care or emergency guidance."
            ),
            (
                "**Q: Can I use this for pregnancy or pediatric situations?**\n"
                "A: Use the red-flag guidance first, keep dosing boundaries conservative, and involve "
                "a qualified clinician whenever risk factors are present."
            ),
        ]

    if section_key in {"cta_1", "cta_2", "cta_3_ps"}:
        if not cta_url:
            raise StrategyV2DecisionError(
                "Sales semantic repair requires at least one existing markdown CTA link URL "
                "to populate missing CTA sections."
            )
        lines = [
            "Ready to move forward with the safety-first handbook?",
            f"[Complete purchase]({cta_url})",
        ]
        if section_key == "cta_3_ps":
            lines.extend(
                [
                    "",
                    (
                        "P.S. Re-run the authenticity checklist and safety red flags before buying any "
                        "new remedy book so you avoid counterfeit or low-trust sources."
                    ),
                ]
            )
        return lines

    return [
        (
            f"{core_promise} Start with this delivery checkpoint: {delivery_test}"
        )
    ]


def _repair_sales_markdown_for_semantic_structure(
    *,
    markdown: str,
    stage3: ProductBriefStage3,
    promise_contract: Mapping[str, Any],
    page_contract: Any,
) -> str:
    if str(getattr(page_contract, "page_type", "")) != "sales_page_warm":
        return markdown

    prefix_lines, sections = _parse_h2_section_blocks(markdown)
    if not sections:
        return markdown

    cta_url = _extract_first_markdown_link_url(markdown)
    remaining_indices = set(range(len(sections)))
    rebuilt_sections: list[dict[str, Any]] = []

    for required in page_contract.required_sections:
        matched_index: int | None = None
        for index in sorted(remaining_indices):
            title = str(sections[index].get("title") or "")
            normalized_title = _normalize_heading_marker_text(title)
            if any(marker in normalized_title for marker in required.title_markers):
                matched_index = index
                break

        if matched_index is None:
            rebuilt_sections.append(
                {
                    "title": required.canonical_title,
                    "lines": _build_missing_sales_section_lines(
                        section_key=required.section_key,
                        stage3=stage3,
                        promise_contract=promise_contract,
                        cta_url=cta_url,
                    ),
                }
            )
            continue

        remaining_indices.remove(matched_index)
        original = sections[matched_index]
        rebuilt_sections.append(
            {
                "title": _canonicalize_section_title(
                    original_title=str(original.get("title") or ""),
                    canonical_title=required.canonical_title,
                ),
                "lines": [str(line) for line in original.get("lines", [])],
            }
        )

    # Keep non-CTA leftovers for context while avoiding accidental CTA count inflation.
    for index in sorted(remaining_indices):
        title = str(sections[index].get("title") or "").strip()
        if _CTA_HEADING_ANY_RE.search(title) or _CONTINUE_TO_OFFER_HEADING_RE.search(title):
            continue
        rebuilt_sections.append(
            {
                "title": title,
                "lines": [str(line) for line in sections[index].get("lines", [])],
            }
        )

    rebuilt_markdown = _render_h2_section_blocks(prefix_lines, rebuilt_sections)
    if rebuilt_markdown.strip() == markdown.strip():
        return markdown
    return rebuilt_markdown


def _classify_copy_attempt_error(error_message: str) -> str:
    lowered = error_message.lower()
    if "headline qa loop did not reach pass status" in lowered:
        return "headline_qa_fail"
    if "semantic copy gates" in lowered:
        return "semantic_gate_fail"
    if "copy depth/structure gates" in lowered:
        return "depth_structure_fail"
    if "congruency" in lowered:
        return "congruency_fail"
    if "promise contract extraction returned empty" in lowered:
        return "promise_contract_fail"
    return "other"


_COPY_REASON_CODE_RE = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\s*:")
_COPY_CONGRUENCY_TEST_RE = re.compile(r"\b(BH\d+|PC\d+)\b")


def _extract_copy_reason_codes(error_message: str, *, limit: int = 20) -> list[str]:
    if not isinstance(error_message, str) or not error_message.strip():
        return []
    collected: list[str] = []

    def _append(code: str) -> None:
        normalized = code.strip().upper()
        if not normalized or normalized in collected:
            return
        collected.append(normalized)

    for match in _COPY_REASON_CODE_RE.finditer(error_message):
        _append(match.group(1))
        if len(collected) >= limit:
            return collected
    for match in _COPY_CONGRUENCY_TEST_RE.finditer(error_message):
        _append(match.group(1))
        if len(collected) >= limit:
            return collected
    return collected


def _coerce_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return 0
        try:
            return int(float(cleaned))
        except ValueError:
            return 0
    return 0


def _coerce_float(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return 0.0
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    return 0.0


def _coerce_string_list(value: object, *, limit: int = 25) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if not text or text in cleaned:
            continue
        cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def _filter_copy_repair_errors(
    *,
    previous_errors: list[str],
    page_scope: str | None,
    limit: int,
) -> list[str]:
    scoped: list[str] = []
    for item in previous_errors:
        message = item.strip()
        if not message:
            continue
        lowered = message.lower()
        if page_scope == "presell_advertorial" and "sales page" in lowered:
            continue
        if page_scope == "sales_page_warm" and "presell advertorial" in lowered:
            continue
        scoped.append(message)
    return scoped[-limit:]


def _canonical_copy_order_for_scope(page_scope: str | None) -> tuple[str, ...]:
    if page_scope == "presell_advertorial":
        return _COPY_PRESELL_CANONICAL_SECTION_ORDER
    if page_scope == "sales_page_warm":
        return _COPY_SALES_CANONICAL_SECTION_ORDER
    return ()


def _build_copy_repair_directives(
    *,
    previous_errors: list[str],
    page_scope: str | None = None,
    limit: int = 3,
) -> str:
    if not previous_errors:
        return ""
    recent = _filter_copy_repair_errors(
        previous_errors=previous_errors,
        page_scope=page_scope,
        limit=limit,
    )
    if not recent:
        return ""

    word_floor_repair_lines: list[str] = []
    word_ceiling_repair_lines: list[str] = []
    cta_repair_lines: list[str] = []
    proof_repair_lines: list[str] = []
    section_coverage_repair_lines: list[str] = []
    belief_sequence_repair_lines: list[str] = []
    signal_coverage_repair_lines: list[str] = []
    heading_congruency_repair_lines: list[str] = []
    promise_timing_repair_lines: list[str] = []
    canonical_section_order = _canonical_copy_order_for_scope(page_scope)
    for message in reversed(recent):
        if not word_floor_repair_lines:
            floor_match = _COPY_WORD_FLOOR_ERROR_RE.search(message)
            if floor_match is not None:
                current_words = int(floor_match.group("current"))
                minimum_words = int(floor_match.group("min"))
                gap_words = max(0, minimum_words - current_words)
                word_floor_repair_lines = [
                    (
                        "- Word floor hard-fix: previous total_words="
                        f"{current_words}; required>={minimum_words}."
                    ),
                    (
                        f"- Add at least {gap_words} net words of concrete detail while preserving "
                        "all canonical section headings."
                    ),
                    "- Expand mechanism/proof/value sections first; do not pad with generic filler.",
                ]

        if not word_ceiling_repair_lines:
            ceiling_match = _COPY_WORD_CEILING_ERROR_RE.search(message)
            if ceiling_match is not None:
                current_words = int(ceiling_match.group("current"))
                max_words = int(ceiling_match.group("max"))
                trim_words = max(0, current_words - max_words)
                word_ceiling_repair_lines = [
                    (
                        "- Word ceiling hard-fix: previous total_words="
                        f"{current_words}; required<={max_words}."
                    ),
                    f"- Remove at least {trim_words} excess words by tightening repetition.",
                    "- Keep every required canonical section heading intact while trimming.",
                ]

        if not cta_repair_lines:
            cta_match = _COPY_CTA_COUNT_ERROR_RE.search(message)
            if cta_match is not None:
                cta_current = int(cta_match.group("current"))
                cta_min = int(cta_match.group("min"))
                cta_max = int(cta_match.group("max"))
                cta_repair_lines = [
                    f"- CTA cadence hard-fix: previous cta_count={cta_current}; required_range=[{cta_min},{cta_max}].",
                    f"- Keep canonical CTA sections in range [{cta_min},{cta_max}] and never above {cta_max}.",
                    "- Canonical CTA sections are headings that contain `CTA` or `Continue to Offer`.",
                    "- URL path tokens alone do not count as CTA intent.",
                    "- Keep explicit purchase directives (buy/order/checkout/add-to-cart/complete-purchase) inside canonical CTA sections.",
                ]

        if not proof_repair_lines:
            proof_match = _COPY_SALES_PROOF_DEPTH_ERROR_RE.search(message)
            if proof_match is not None:
                proof_current = int(proof_match.group("current"))
                proof_min = int(proof_match.group("min"))
                proof_repair_lines = [
                    f"- Proof depth hard-fix: previous proof_words={proof_current}; required>={proof_min}.",
                    f"- Expand proof/evidence/testimonial sections to at least {proof_min} cumulative words.",
                    "- Add concrete buyer language, outcome detail, and explicit evidence framing (proof/testimonial/evidence/case).",
                ]

        if not section_coverage_repair_lines:
            coverage_match = _COPY_REQUIRED_SECTION_COVERAGE_ERROR_RE.search(message)
            if coverage_match is not None:
                missing_sections = [
                    part.strip().rstrip(".")
                    for part in coverage_match.group("sections").split(",")
                    if part and part.strip()
                ]
                section_coverage_repair_lines = [
                    "- Required section coverage hard-fix: previous draft omitted canonical sections.",
                ]
                if missing_sections:
                    section_coverage_repair_lines.append(
                        "- Add these exact canonical H2 markers: " + ", ".join(missing_sections) + "."
                    )
                section_coverage_repair_lines.extend(
                    [
                        "- Keep marker format as `## <Canonical Marker>: <Topical Phrase>`.",
                        "- Do not replace canonical markers with synonyms.",
                    ]
                )

        if not belief_sequence_repair_lines:
            order_match = _COPY_BELIEF_SEQUENCE_ORDER_ERROR_RE.search(message)
            if order_match is not None:
                belief_sequence_repair_lines = [
                    "- Belief sequence hard-fix: required section ordering failed in the previous attempt.",
                ]
                if canonical_section_order:
                    belief_sequence_repair_lines.append(
                        "- Keep canonical H2 order exactly as: " + " -> ".join(canonical_section_order) + "."
                    )
                belief_sequence_repair_lines.append(
                    "- Keep CTA #3 + P.S. as the final CTA section in the sequence."
                )

        if not signal_coverage_repair_lines:
            signal_match = _COPY_REQUIRED_SIGNAL_COVERAGE_ERROR_RE.search(message)
            if signal_match is not None:
                signal_detail = signal_match.group("detail").strip().rstrip(".")
                signal_coverage_repair_lines = [
                    "- Required signal coverage hard-fix: deterministic signal checks failed.",
                    f"- Missing signals to address: {signal_detail}.",
                    "- Add explicit signal language in each affected section (mechanism/proof/offer/compliance as specified).",
                ]

        if not heading_congruency_repair_lines:
            bh1_match = _COPY_CONGRUENCY_BH1_ERROR_RE.search(message)
            if bh1_match is not None:
                heading_congruency_repair_lines = [
                    "- Heading congruency hard-fix: BH1 failed in the previous attempt.",
                    "- Every H2 heading must include a topical phrase containing headline terms, not marker-only headings.",
                    "- Use format: `## <Canonical Marker>: <Headline-aligned topical phrase>` for all sections.",
                ]

        if not promise_timing_repair_lines:
            promise_timing_match = _COPY_PROMISE_DELIVERY_TIMING_ERROR_RE.search(message)
            if promise_timing_match is not None:
                promise_timing_repair_lines = [
                    "- Promise timing hard-fix: PROMISE_DELIVERY_TIMING failed in the previous attempt.",
                    "- Deliver concrete DELIVERY_TEST language in sections 1-2 before the structural pivot.",
                    "- Include at least one explicit early sentence using Promise Contract terms from loop_question/specific_promise/delivery_test.",
                ]

        if (
            cta_repair_lines
            and proof_repair_lines
            and section_coverage_repair_lines
            and belief_sequence_repair_lines
            and signal_coverage_repair_lines
            and heading_congruency_repair_lines
            and promise_timing_repair_lines
        ):
            break

    lines = [
        "- Previous attempt failed deterministic gates. Rewrite from scratch and fix all listed failures.",
    ]
    lines.extend(f"- {message}" for message in recent)
    lines.extend(word_floor_repair_lines)
    lines.extend(word_ceiling_repair_lines)
    lines.extend(cta_repair_lines)
    lines.extend(proof_repair_lines)
    lines.extend(section_coverage_repair_lines)
    lines.extend(belief_sequence_repair_lines)
    lines.extend(signal_coverage_repair_lines)
    lines.extend(heading_congruency_repair_lines)
    lines.extend(promise_timing_repair_lines)
    lines.append("- Preserve the same core angle and promise while fixing structure/depth/congruency failures.")
    return "\n".join(lines)


def _build_copy_retry_feedback_turn(
    *,
    page_attempt: int,
    latest_error: str,
    repair_directives: str,
) -> str:
    lines = [
        f"Previous draft attempt {page_attempt} failed deterministic QA gates.",
        "Use this failure feedback to revise in-context and return a corrected full rewrite.",
        "",
        "Validation failure details:",
        latest_error.strip(),
    ]
    if repair_directives.strip():
        lines.extend(
            [
                "",
                "Required fixes:",
                repair_directives.strip(),
            ]
        )
    lines.extend(
        [
            "",
            "Rewrite the page from start to finish while preserving the core angle and promise contract.",
            "Return only schema-valid JSON for this page.",
        ]
    )
    return "\n".join(lines)


def _summarize_prompt_call_logs(call_logs: list[dict[str, Any]]) -> dict[str, Any]:
    by_label: Counter[str] = Counter()
    by_model: Counter[str] = Counter()
    token_totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "reasoning_tokens": 0,
        "cached_input_tokens": 0,
    }
    for row in call_logs:
        label = str(row.get("label") or "").strip()
        model = str(row.get("model") or "").strip()
        if label:
            by_label[label] += 1
        if model:
            by_model[model] += 1
        for key in token_totals:
            value = row.get(key)
            if isinstance(value, int) and value > 0:
                token_totals[key] += value
    prompt_request_ids = _coerce_string_list([row.get("request_id") for row in call_logs], limit=50)
    return {
        "total_calls": len(call_logs),
        "calls_by_label": dict(by_label),
        "calls_by_model": dict(by_model),
        "token_totals": token_totals,
        "request_ids": prompt_request_ids,
    }


@activity.defn(name="strategy_v2.run_copy_pipeline")
def run_strategy_v2_copy_pipeline_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    workflow_run_id = str(params["workflow_run_id"])
    stage3 = ProductBriefStage3.model_validate(_require_dict(payload=params["stage3"], field_name="stage3"))
    _require_selected_angle_evidence_quality(selected_angle=stage3.selected_angle)
    copy_context = _require_dict(payload=params["copy_context"], field_name="copy_context")
    operator_user_id = str(params.get("operator_user_id") or "system")

    hook_lines = [hook.opening_line.strip() for hook in stage3.selected_angle.hook_starters if hook.opening_line.strip()]
    if not hook_lines:
        raise StrategyV2MissingContextError(
            "Selected angle does not contain hook starters for copy generation. "
            "Remediation: select an angle with hook_starters populated."
        )
    copy_contract_profile = default_copy_contract_profile()
    copy_input_packet = build_copy_stage4_input_packet(
        stage3=stage3,
        copy_context_payload=copy_context,
        hook_lines=hook_lines,
        profile=copy_contract_profile,
    )
    copy_loop_started_at = _now_iso()
    prompt_call_logs: list[dict[str, Any]] = []
    qa_attempt_error_buckets: Counter[str] = Counter()
    qa_attempts: list[dict[str, Any]] = []

    if True:
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise StrategyV2MissingContextError(
                "ANTHROPIC_API_KEY is required for copy headline QA loop and is not set. "
                "Remediation: configure ANTHROPIC_API_KEY before running Strategy V2 copy stage."
            )

        headline_asset = resolve_prompt_asset(
            pattern=_COPY_HEADLINE_PROMPT_PATTERN,
            context="Copywriting headline generation template",
        )
        headline_parsed, headline_raw, headline_provenance = _run_prompt_json_object(
            asset=headline_asset,
            context="strategy_v2.copy.headline_generation",
            model=settings.STRATEGY_V2_COPY_MODEL,
            runtime_instruction=render_copy_headline_runtime_instruction(packet=copy_input_packet),
            schema_name="strategy_v2_copy_headlines",
            schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "headline_candidates": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 12,
                        "items": {"type": "string"},
                    }
                },
                "required": ["headline_candidates"],
            },
            use_reasoning=True,
            use_web_search=False,
            heartbeat_context={
                "activity": "strategy_v2.run_copy_pipeline",
                "phase": "headline_prompt",
                "model": settings.STRATEGY_V2_COPY_MODEL,
            },
            log_metadata={
                "thread_id": "headline_generation",
                "thread_turn": 1,
            },
            llm_call_log=prompt_call_logs,
            llm_call_label="headline_prompt",
        )
        prompt_headlines = headline_parsed.get("headline_candidates")
        if not isinstance(prompt_headlines, list):
            raise StrategyV2SchemaValidationError("Headline generation prompt returned invalid headline_candidates.")
        risk_headline_templates = _build_stage3_risk_headline_templates(stage3)
        headline_candidates = _build_headline_candidate_pool(
            prompt_headlines=prompt_headlines,
            hook_lines=hook_lines,
            risk_headline_templates=risk_headline_templates,
            fallback_candidates=[stage3.core_promise, stage3.ump],
            max_candidates=_COPY_HEADLINE_MAX_CANDIDATES,
        )
        if not headline_candidates:
            raise StrategyV2SchemaValidationError("Headline generation prompt returned no usable headlines.")

        scored_headlines: list[dict[str, Any]] = []
        for candidate in headline_candidates:
            result = score_headline(candidate, page_type="advertorial")
            scored_headlines.append(
                {
                    "headline": candidate,
                    "result": result["result"],
                    "composite": result["composite"],
                    "json": result["json"],
                }
            )
        ranked_headlines = sorted(
            scored_headlines,
            key=lambda row: float(
                _require_dict(payload=row["composite"], field_name="headline_composite").get("pct") or 0.0
            ),
            reverse=True,
        )

        promise_asset = resolve_prompt_asset(
            pattern=_COPY_PROMISE_PROMPT_PATTERN,
            context="Copywriting promise contract extraction template",
        )
        advertorial_asset = resolve_prompt_asset(
            pattern=_COPY_ADVERTORIAL_PROMPT_PATTERN,
            context="Copywriting advertorial writing template",
        )
        sales_asset = resolve_prompt_asset(
            pattern=_COPY_SALES_PROMPT_PATTERN,
            context="Copywriting sales page writing template",
        )
        presell_page_contract = get_page_contract(
            profile=copy_contract_profile,
            page_type="presell_advertorial",
        )
        sales_page_contract = get_page_contract(
            profile=copy_contract_profile,
            page_type="sales_page_warm",
        )
        expected_presell_items = len(presell_page_contract.required_sections)
        ranked_headlines = [
            row
            for row in ranked_headlines
            if _headline_numeric_promise_is_compatible(
                headline=str(row.get("headline") or ""),
                expected_item_count=expected_presell_items,
            )
        ]
        if not ranked_headlines:
            raise StrategyV2DecisionError(
                "All headline candidates with numeric promises are incompatible with presell section count "
                f"(expected_items={expected_presell_items}). "
                "Remediation: generate non-numeric headlines or align promised list count with page sections."
            )

        selected_bundle: dict[str, Any] | None = None
        qa_warning_count_total = 0
        qa_overloaded_error_count_total = 0
        qa_timeout_error_count_total = 0
        qa_transient_attempt_count_total = 0
        qa_timeout_seconds_effective: float | None = None
        qa_call_max_retries_effective: int | None = None
        qa_model_effective = settings.STRATEGY_V2_COPY_QA_MODEL
        headline_qa_transient_fail_streak = 0
        headline_qa_transient_fail_fast_triggered = False
        for headline_index, scored in enumerate(ranked_headlines, start=1):
            source_headline = str(scored.get("headline") or "").strip()
            if not source_headline:
                continue
            headline_thread_id = f"headline_qa:{headline_index}"
            activity.heartbeat(
                {
                    "activity": "strategy_v2.run_copy_pipeline",
                    "phase": "headline_qa",
                    "status": "started",
                    "headline_index": headline_index,
                    "headline_count": len(ranked_headlines),
                }
            )
            qa_result = run_headline_qa_loop(
                headline=source_headline,
                page_type="advertorial",
                max_iterations=_COPY_HEADLINE_QA_MAX_ITERATIONS,
                min_tier="A",
                api_key=api_key,
                model=settings.STRATEGY_V2_COPY_QA_MODEL,
            )
            qa_json = _require_dict(payload=qa_result.get("json"), field_name="qa_json")
            qa_diagnostics = qa_result.get("diagnostics")
            qa_diag_map = qa_diagnostics if isinstance(qa_diagnostics, dict) else {}
            qa_warning_count = _coerce_int(qa_diag_map.get("warning_count"))
            qa_overloaded_error_count = _coerce_int(qa_diag_map.get("overloaded_error_count"))
            qa_timeout_error_count = _coerce_int(qa_diag_map.get("timeout_error_count"))
            qa_transient_attempt_count = _coerce_int(qa_diag_map.get("attempt_count"))
            qa_call_timeout_seconds = _coerce_float(qa_diag_map.get("call_timeout_seconds"))
            qa_call_max_retries = _coerce_int(qa_diag_map.get("call_max_retries"))
            qa_model = str(qa_diag_map.get("model") or settings.STRATEGY_V2_COPY_QA_MODEL).strip()
            qa_request_ids = _coerce_string_list(qa_diag_map.get("request_ids"), limit=12)
            if qa_timeout_seconds_effective is None and qa_call_timeout_seconds > 0:
                qa_timeout_seconds_effective = qa_call_timeout_seconds
            if qa_call_max_retries_effective is None and qa_call_max_retries >= 0:
                qa_call_max_retries_effective = qa_call_max_retries
            if qa_model:
                qa_model_effective = qa_model
            qa_warning_count_total += qa_warning_count
            qa_overloaded_error_count_total += qa_overloaded_error_count
            qa_timeout_error_count_total += qa_timeout_error_count
            qa_transient_attempt_count_total += qa_transient_attempt_count
            qa_status = str(qa_json.get("status") or "").strip().upper()
            winning_headline = str(qa_json.get("best_headline") or source_headline).strip()
            qa_last_failing_tests: list[str] = []
            qa_iterations_payload = qa_json.get("iterations")
            if isinstance(qa_iterations_payload, list) and qa_iterations_payload:
                qa_last_iteration = qa_iterations_payload[-1]
                if isinstance(qa_last_iteration, dict):
                    qa_last_failing_tests = _coerce_string_list(
                        qa_last_iteration.get("failing_tests"),
                        limit=25,
                    )
            attempt_row: dict[str, Any] = {
                "source_headline": source_headline,
                "headline_thread_id": headline_thread_id,
                "qa_status": qa_status or "UNKNOWN",
                "qa_iterations": int(qa_json.get("total_iterations") or 0),
                "qa_best_tier": qa_json.get("best_tier"),
                "qa_best_pct": qa_json.get("best_pct"),
                "qa_warning_count": qa_warning_count,
                "qa_overloaded_error_count": qa_overloaded_error_count,
                "qa_timeout_error_count": qa_timeout_error_count,
                "qa_transient_attempt_count": qa_transient_attempt_count,
            }
            if qa_last_failing_tests:
                attempt_row["qa_last_failing_tests"] = qa_last_failing_tests
            if qa_model:
                attempt_row["qa_model"] = qa_model
            if qa_call_timeout_seconds > 0:
                attempt_row["qa_call_timeout_seconds"] = qa_call_timeout_seconds
            if qa_call_max_retries >= 0:
                attempt_row["qa_call_max_retries"] = qa_call_max_retries
            if qa_request_ids:
                attempt_row["qa_request_ids"] = qa_request_ids
            activity.heartbeat(
                {
                    "activity": "strategy_v2.run_copy_pipeline",
                    "phase": "headline_qa",
                    "status": "completed",
                    "headline_index": headline_index,
                    "headline_count": len(ranked_headlines),
                    "qa_status": qa_status or "UNKNOWN",
                    "qa_iterations": attempt_row["qa_iterations"],
                    "qa_best_tier": attempt_row["qa_best_tier"],
                    "qa_request_id": qa_request_ids[0] if qa_request_ids else None,
                }
            )
            if not winning_headline:
                attempt_row["error"] = "QA returned an empty best_headline."
                qa_attempt_error_buckets[_classify_copy_attempt_error(str(attempt_row["error"]))] += 1
                qa_attempts.append(attempt_row)
                continue
            attempt_row["winning_headline"] = winning_headline
            if qa_status != "PASS":
                attempt_row["error"] = "Headline QA loop did not reach PASS status."
                qa_attempt_error_buckets[_classify_copy_attempt_error(str(attempt_row["error"]))] += 1
                qa_attempts.append(attempt_row)
                if qa_overloaded_error_count > 0 or qa_timeout_error_count > 0:
                    headline_qa_transient_fail_streak += 1
                    if (
                        headline_qa_transient_fail_streak >= _COPY_HEADLINE_TRANSIENT_FAIL_FAST_THRESHOLD
                    ):
                        headline_qa_transient_fail_fast_triggered = True
                        break
                else:
                    headline_qa_transient_fail_streak = 0
                continue

            promise_parsed, promise_raw, promise_provenance = _run_prompt_json_object(
                asset=promise_asset,
                context="strategy_v2.copy.promise_contract",
                model=settings.STRATEGY_V2_COPY_MODEL,
                runtime_instruction=(
                    "## Runtime Input Block\n"
                    f"HEADLINE:\n{winning_headline}\n\n"
                    f"AWARENESS_LEVEL:\n{stage3.awareness_level_primary or 'Problem-Aware'}\n\n"
                    "## Runtime Output Contract\n"
                    "Return promise contract JSON with loop_question, specific_promise, delivery_test, minimum_delivery."
                ),
                schema_name="strategy_v2_copy_promise_contract",
                schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "loop_question": {"type": "string"},
                        "specific_promise": {"type": "string"},
                        "delivery_test": {"type": "string"},
                        "minimum_delivery": {"type": "string"},
                    },
                    "required": ["loop_question", "specific_promise", "delivery_test", "minimum_delivery"],
                },
                use_reasoning=True,
                use_web_search=False,
                heartbeat_context={
                    "activity": "strategy_v2.run_copy_pipeline",
                    "phase": "promise_contract_prompt",
                    "model": settings.STRATEGY_V2_COPY_MODEL,
                    "headline_index": headline_index,
                    "headline": winning_headline[:160],
                    "thread_id": f"promise_contract:{headline_index}",
                },
                log_metadata={
                    "thread_id": f"promise_contract:{headline_index}",
                    "thread_turn": 1,
                },
                llm_call_log=prompt_call_logs,
                llm_call_label="promise_contract_prompt",
            )
            promise_contract = {
                "loop_question": str(promise_parsed.get("loop_question") or "").strip(),
                "specific_promise": str(promise_parsed.get("specific_promise") or "").strip(),
                "delivery_test": str(promise_parsed.get("delivery_test") or "").strip(),
                "minimum_delivery": str(promise_parsed.get("minimum_delivery") or "").strip(),
            }
            if not all(promise_contract.values()):
                attempt_row["error"] = "Promise Contract extraction returned empty required fields."
                qa_attempt_error_buckets[_classify_copy_attempt_error(str(attempt_row["error"]))] += 1
                qa_attempts.append(attempt_row)
                continue

            page_generation_errors: list[str] = []
            use_claude_chat_context = settings.STRATEGY_V2_COPY_MODEL.lower().startswith("claude")
            advertorial_conversation: list[dict[str, Any]] = []
            sales_conversation: list[dict[str, Any]] = []
            presell_thread_id = f"presell_page:{headline_index}"
            sales_thread_id = f"sales_page:{headline_index}"
            page_attempt_observability: list[dict[str, Any]] = []
            attempt_row["page_thread_ids"] = {
                "presell": presell_thread_id,
                "sales_page": sales_thread_id,
            }
            for page_attempt in range(1, _COPY_PAGE_REPAIR_MAX_ATTEMPTS + 1):
                page_prompt_start_index = len(prompt_call_logs)
                page_observability_row: dict[str, Any] = {
                    "page_attempt": page_attempt,
                    "presell_thread_id": presell_thread_id,
                    "sales_page_thread_id": sales_thread_id,
                    "thread_turn": page_attempt,
                }
                presell_repair_directives = _build_copy_repair_directives(
                    previous_errors=page_generation_errors,
                    page_scope="presell_advertorial",
                )
                sales_repair_directives = _build_copy_repair_directives(
                    previous_errors=page_generation_errors,
                    page_scope="sales_page_warm",
                )
                presell_runtime_instruction = render_copy_page_runtime_instruction(
                    packet=copy_input_packet,
                    headline=winning_headline,
                    promise_contract=promise_contract,
                    page_contract=presell_page_contract,
                    repair_directives=presell_repair_directives,
                )
                sales_runtime_instruction = render_copy_page_runtime_instruction(
                    packet=copy_input_packet,
                    headline=winning_headline,
                    promise_contract=promise_contract,
                    page_contract=sales_page_contract,
                    repair_directives=sales_repair_directives,
                )
                if _COPY_DEBUG_CAPTURE_THREADS:
                    page_observability_row["sales_prompt_runtime_instruction"] = sales_runtime_instruction
                    page_observability_row["presell_prompt_runtime_instruction"] = presell_runtime_instruction
                    if use_claude_chat_context:
                        page_observability_row["sales_thread_before_call"] = _serialize_claude_conversation(
                            sales_conversation
                        )
                        page_observability_row["presell_thread_before_call"] = _serialize_claude_conversation(
                            advertorial_conversation
                        )
                try:
                    advertorial_parsed, advertorial_raw, advertorial_provenance = _run_prompt_json_object(
                        asset=advertorial_asset,
                        context="strategy_v2.copy.advertorial",
                        model=settings.STRATEGY_V2_COPY_MODEL,
                        runtime_instruction=presell_runtime_instruction,
                        schema_name="strategy_v2_copy_advertorial",
                        schema={
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {"markdown": {"type": "string"}},
                            "required": ["markdown"],
                        },
                        use_reasoning=True,
                        use_web_search=False,
                        max_tokens=_FOUNDTN_STEP04_MAX_TOKENS,
                        heartbeat_context={
                            "activity": "strategy_v2.run_copy_pipeline",
                            "phase": "advertorial_prompt",
                            "model": settings.STRATEGY_V2_COPY_MODEL,
                            "headline_index": headline_index,
                            "headline": winning_headline[:160],
                            "thread_id": presell_thread_id,
                            "page_attempt": page_attempt,
                        },
                        conversation_messages=advertorial_conversation if use_claude_chat_context else None,
                        log_metadata={
                            "thread_id": presell_thread_id,
                            "thread_turn": page_attempt,
                            "headline_index": headline_index,
                            "page_attempt": page_attempt,
                        },
                        llm_call_log=prompt_call_logs,
                        llm_call_label="advertorial_prompt",
                    )
                    presell_markdown = str(advertorial_parsed.get("markdown") or "").strip()
                    if _COPY_DEBUG_CAPTURE_FULL_MARKDOWN:
                        page_observability_row["presell_markdown_generated"] = presell_markdown
                    if _COPY_DEBUG_CAPTURE_THREADS and use_claude_chat_context:
                        page_observability_row["presell_thread_after_call"] = _serialize_claude_conversation(
                            advertorial_conversation
                        )
                    presell_markdown = _repair_markdown_for_congruency_and_semantics(
                        markdown=presell_markdown,
                        headline=winning_headline,
                        promise_contract=promise_contract,
                    )
                    presell_quality_report = require_copy_page_quality(
                        markdown=presell_markdown,
                        page_contract=presell_page_contract,
                        page_name="Presell advertorial",
                    )
                    presell_semantic_report = require_copy_page_semantic_quality(
                        markdown=presell_markdown,
                        page_contract=presell_page_contract,
                        promise_contract=promise_contract,
                        page_name="Presell advertorial",
                    )

                    sales_parsed, sales_raw, sales_provenance = _run_prompt_json_object(
                        asset=sales_asset,
                        context="strategy_v2.copy.sales_page",
                        model=settings.STRATEGY_V2_COPY_MODEL,
                        runtime_instruction=sales_runtime_instruction,
                        schema_name="strategy_v2_copy_sales_page",
                        schema={
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {"markdown": {"type": "string"}},
                            "required": ["markdown"],
                        },
                        use_reasoning=True,
                        use_web_search=False,
                        max_tokens=_FOUNDTN_STEP04_MAX_TOKENS,
                        heartbeat_context={
                            "activity": "strategy_v2.run_copy_pipeline",
                            "phase": "sales_page_prompt",
                            "model": settings.STRATEGY_V2_COPY_MODEL,
                            "headline_index": headline_index,
                            "headline": winning_headline[:160],
                            "thread_id": sales_thread_id,
                            "page_attempt": page_attempt,
                        },
                        conversation_messages=sales_conversation if use_claude_chat_context else None,
                        log_metadata={
                            "thread_id": sales_thread_id,
                            "thread_turn": page_attempt,
                            "headline_index": headline_index,
                            "page_attempt": page_attempt,
                        },
                        llm_call_log=prompt_call_logs,
                        llm_call_label="sales_page_prompt",
                    )
                    sales_page_markdown = str(sales_parsed.get("markdown") or "").strip()
                    if _COPY_DEBUG_CAPTURE_FULL_MARKDOWN:
                        page_observability_row["sales_markdown_generated"] = sales_page_markdown
                    if _COPY_DEBUG_CAPTURE_THREADS and use_claude_chat_context:
                        page_observability_row["sales_thread_after_call"] = _serialize_claude_conversation(
                            sales_conversation
                        )
                    sales_page_markdown = _repair_sales_markdown_for_quality(
                        markdown=sales_page_markdown,
                        stage3=stage3,
                        page_contract=sales_page_contract,
                    )
                    sales_page_markdown = _repair_sales_markdown_for_semantic_structure(
                        markdown=sales_page_markdown,
                        stage3=stage3,
                        promise_contract=promise_contract,
                        page_contract=sales_page_contract,
                    )
                    sales_page_markdown = _repair_markdown_for_congruency_and_semantics(
                        markdown=sales_page_markdown,
                        headline=winning_headline,
                        promise_contract=promise_contract,
                    )
                    sales_page_markdown = _normalize_sales_cta_section_titles(
                        markdown=sales_page_markdown,
                    )
                    if _COPY_DEBUG_CAPTURE_FULL_MARKDOWN:
                        page_observability_row["sales_markdown_final"] = sales_page_markdown
                        page_observability_row["presell_markdown_final"] = presell_markdown
                    if _COPY_DEBUG_CAPTURE_MARKDOWN:
                        page_observability_row["presell_section_titles"] = [
                            str(section.get("title") or "")
                            for section in _parse_h2_section_blocks(presell_markdown)[1]
                        ]
                        page_observability_row["sales_section_titles"] = [
                            str(section.get("title") or "")
                            for section in _parse_h2_section_blocks(sales_page_markdown)[1]
                        ]
                        page_observability_row["presell_markdown_preview"] = presell_markdown[:8000]
                        page_observability_row["sales_markdown_preview"] = sales_page_markdown[:8000]
                    sales_quality_preview = evaluate_copy_page_quality(
                        markdown=sales_page_markdown,
                        page_contract=sales_page_contract,
                    )
                    if _COPY_DEBUG_CAPTURE_MARKDOWN:
                        page_observability_row["sales_quality_preview"] = sales_quality_preview.model_dump(
                            mode="python"
                        )
                    sales_quality_report = require_copy_page_quality(
                        markdown=sales_page_markdown,
                        page_contract=sales_page_contract,
                        page_name="Sales page",
                    )
                    sales_semantic_report = require_copy_page_semantic_quality(
                        markdown=sales_page_markdown,
                        page_contract=sales_page_contract,
                        promise_contract=promise_contract,
                        page_name="Sales page",
                    )

                    body_markdown = f"{presell_markdown}\n\n---\n\n{sales_page_markdown}"
                    presell_page_data = build_page_data_from_body_text(presell_markdown, page_type="advertorial")
                    presell_congruency = score_congruency_extended(
                        headline=winning_headline,
                        page_data=presell_page_data,
                        promise_contract=promise_contract,
                    )
                    _require_congruency_quality(congruency=presell_congruency, page_name="Presell advertorial")

                    sales_page_data = build_page_data_from_body_text(sales_page_markdown, page_type="sales_page")
                    sales_congruency = score_congruency_extended(
                        headline=winning_headline,
                        page_data=sales_page_data,
                        promise_contract=promise_contract,
                    )
                    _require_congruency_quality(congruency=sales_congruency, page_name="Sales page")

                    presell_composite = _require_dict(
                        payload=presell_congruency.get("composite"),
                        field_name="presell_congruency_composite",
                    )
                    sales_composite = _require_dict(
                        payload=sales_congruency.get("composite"),
                        field_name="sales_congruency_composite",
                    )
                    congruency = {
                        "presell": presell_congruency,
                        "sales_page": sales_congruency,
                        "composite": {
                            "presell_passed": bool(presell_composite.get("passed", False)),
                            "sales_page_passed": bool(sales_composite.get("passed", False)),
                            "hard_gate_pass": bool(presell_composite.get("hard_gate_pass", False))
                            and bool(sales_composite.get("hard_gate_pass", False)),
                            "passed": bool(presell_composite.get("passed", False))
                            and bool(sales_composite.get("passed", False)),
                        },
                    }
                    selected_bundle = {
                        "headline_row": scored,
                        "qa_json": qa_json,
                        "winning_headline": winning_headline,
                        "body_markdown": body_markdown,
                        "presell_markdown": presell_markdown,
                        "sales_page_markdown": sales_page_markdown,
                        "congruency": congruency,
                        "promise_contract": promise_contract,
                        "semantic_gates": {
                            "presell": presell_semantic_report.model_dump(mode="python"),
                            "sales_page": sales_semantic_report.model_dump(mode="python"),
                        },
                        "quality_gate_report": {
                            "presell": presell_quality_report.model_dump(mode="python"),
                            "sales_page": sales_quality_report.model_dump(mode="python"),
                        },
                        "page_generation_attempts": page_attempt,
                        "page_generation_failures": list(page_generation_errors),
                        "page_thread_ids": {
                            "presell": presell_thread_id,
                            "sales_page": sales_thread_id,
                        },
                        "page_attempt_observability": list(page_attempt_observability),
                        "prompt_chain": {
                            "headline_prompt_provenance": headline_provenance,
                            "headline_prompt_raw_output": headline_raw[:16000],
                            "promise_prompt_provenance": promise_provenance,
                            "promise_prompt_raw_output": promise_raw[:8000],
                            "advertorial_prompt_provenance": advertorial_provenance,
                            "advertorial_prompt_raw_output": advertorial_raw[:16000],
                            "sales_prompt_provenance": sales_provenance,
                            "sales_prompt_raw_output": sales_raw[:16000],
                        },
                    }
                    page_prompt_request_ids = _coerce_string_list(
                        [row.get("request_id") for row in prompt_call_logs[page_prompt_start_index:]],
                        limit=12,
                    )
                    if page_prompt_request_ids:
                        attempt_row["page_prompt_request_ids"] = page_prompt_request_ids
                        page_observability_row["request_ids"] = page_prompt_request_ids
                    page_observability_row["status"] = "pass"
                    page_attempt_observability.append(page_observability_row)
                    attempt_row["page_attempt_observability"] = list(page_attempt_observability)
                    attempt_row["presell_thread_turn_count"] = page_attempt
                    attempt_row["sales_page_thread_turn_count"] = page_attempt
                    attempt_row["page_generation_attempts"] = page_attempt
                    attempt_row["page_generation_failures"] = list(page_generation_errors)
                    attempt_row["result"] = "selected_bundle_passed"
                    qa_attempts.append(attempt_row)
                    break
                except StrategyV2DecisionError as exc:
                    failure_message = str(exc)
                    page_generation_errors.append(failure_message)
                    reason_class = _classify_copy_attempt_error(failure_message)
                    reason_codes = _extract_copy_reason_codes(failure_message)
                    page_prompt_request_ids = _coerce_string_list(
                        [row.get("request_id") for row in prompt_call_logs[page_prompt_start_index:]],
                        limit=12,
                    )
                    if page_prompt_request_ids:
                        attempt_row["page_prompt_request_ids"] = page_prompt_request_ids
                        page_observability_row["request_ids"] = page_prompt_request_ids
                    page_observability_row["status"] = "fail"
                    page_observability_row["failure_reason_class"] = reason_class
                    if reason_codes:
                        page_observability_row["failure_reason_codes"] = reason_codes
                    page_attempt_observability.append(page_observability_row)
                    attempt_row["page_attempt_observability"] = list(page_attempt_observability)
                    attempt_row["last_failure_reason_class"] = reason_class
                    if reason_codes:
                        attempt_row["last_failure_reason_codes"] = reason_codes
                    if use_claude_chat_context:
                        lowered_failure = failure_message.lower()
                        targets_presell = "sales page" not in lowered_failure
                        targets_sales = "presell advertorial" not in lowered_failure
                        if advertorial_conversation and targets_presell:
                            presell_feedback_turn = _build_copy_retry_feedback_turn(
                                page_attempt=page_attempt,
                                latest_error=failure_message,
                                repair_directives=_build_copy_repair_directives(
                                    previous_errors=page_generation_errors,
                                    page_scope="presell_advertorial",
                                ),
                            )
                            advertorial_conversation.append(
                                {
                                    "role": "user",
                                    "content": [{"type": "text", "text": presell_feedback_turn}],
                                }
                            )
                        if sales_conversation and targets_sales:
                            sales_feedback_turn = _build_copy_retry_feedback_turn(
                                page_attempt=page_attempt,
                                latest_error=failure_message,
                                repair_directives=_build_copy_repair_directives(
                                    previous_errors=page_generation_errors,
                                    page_scope="sales_page_warm",
                                ),
                            )
                            sales_conversation.append(
                                {
                                    "role": "user",
                                    "content": [{"type": "text", "text": sales_feedback_turn}],
                                }
                            )
                    if page_attempt >= _COPY_PAGE_REPAIR_MAX_ATTEMPTS:
                        attempt_row["page_generation_attempts"] = page_attempt
                        attempt_row["page_generation_failures"] = list(page_generation_errors)
                        attempt_row["error"] = failure_message
                        qa_attempt_error_buckets[reason_class] += 1
                        qa_attempts.append(attempt_row)

            if selected_bundle is not None:
                break

        qa_total_iterations = sum(
            int(row.get("qa_iterations") or 0)
            for row in qa_attempts
            if isinstance(row.get("qa_iterations"), int) or isinstance(row.get("qa_iterations"), float)
        )
        qa_request_id_flat: list[str] = []
        for row in qa_attempts:
            qa_request_id_flat.extend(_coerce_string_list(row.get("qa_request_ids"), limit=12))
        qa_request_ids = _coerce_string_list(qa_request_id_flat, limit=80)
        qa_request_id_missing_count = sum(
            1
            for row in qa_attempts
            if _coerce_int(row.get("qa_iterations")) > 1
            and not _coerce_string_list(row.get("qa_request_ids"), limit=1)
        )
        copy_loop_report = {
            "started_at": copy_loop_started_at,
            "finished_at": _now_iso(),
            "headline_candidate_count": len(headline_candidates),
            "headline_ranked_count": len(ranked_headlines),
            "qa_attempt_count": len(qa_attempts),
            "qa_pass_count": sum(1 for row in qa_attempts if str(row.get("qa_status") or "").upper() == "PASS"),
            "qa_fail_count": sum(1 for row in qa_attempts if row.get("error")),
            "qa_total_iterations": qa_total_iterations,
            "qa_average_iterations": round(qa_total_iterations / len(qa_attempts), 2) if qa_attempts else 0.0,
            "qa_warning_count": qa_warning_count_total,
            "qa_overloaded_error_count": qa_overloaded_error_count_total,
            "qa_timeout_error_count": qa_timeout_error_count_total,
            "qa_transient_attempt_count": qa_transient_attempt_count_total,
            "qa_model": qa_model_effective,
            "qa_call_timeout_seconds": qa_timeout_seconds_effective,
            "qa_call_max_retries": qa_call_max_retries_effective,
            "qa_request_ids": qa_request_ids,
            "qa_request_id_missing_count": qa_request_id_missing_count,
            "qa_transient_fail_fast_triggered": headline_qa_transient_fail_fast_triggered,
            "failure_breakdown": dict(qa_attempt_error_buckets),
            "prompt_call_summary": _summarize_prompt_call_logs(prompt_call_logs),
            "prompt_calls": prompt_call_logs,
            "qa_attempts": qa_attempts,
            "selected_bundle_found": selected_bundle is not None,
        }

        if selected_bundle is None:
            headline_qa_fail_rows = [
                row for row in qa_attempts if str(row.get("error") or "") == "Headline QA loop did not reach PASS status."
            ]
            transient_overload_only = (
                bool(qa_attempts)
                and len(headline_qa_fail_rows) == len(qa_attempts)
                and (qa_overloaded_error_count_total > 0 or qa_timeout_error_count_total > 0)
            )
            attempt_fragments: list[str] = []
            for row in qa_attempts:
                if not row.get("error"):
                    continue
                fragment = f"{row.get('source_headline')}: {row.get('error')}"
                request_ids_for_attempt = _coerce_string_list(row.get("qa_request_ids"), limit=3)
                if request_ids_for_attempt:
                    fragment += f" (qa_request_ids={','.join(request_ids_for_attempt)})"
                attempt_fragments.append(fragment)
            attempts_summary = "; ".join(attempt_fragments)
            with session_scope() as session:
                WorkflowsRepository(session).log_activity(
                    workflow_run_id=workflow_run_id,
                    step="v2-10.copy_loop_report",
                    status="failed",
                    payload_out={"copy_loop_report": copy_loop_report},
                    error="Copy loop failed to produce a passable bundle.",
                )
            if transient_overload_only:
                raise StrategyV2Error(
                    "Copy prompt-chain pipeline encountered transient headline QA provider overload "
                    f"(overloaded_errors={qa_overloaded_error_count_total}, timeout_errors={qa_timeout_error_count_total}, "
                    f"qa_attempts={len(qa_attempts)}). "
                    "Retry the activity after model capacity recovers."
                )
            raise StrategyV2DecisionError(
                "Copy prompt-chain pipeline could not produce a headline + page bundle that passed QA and congruency gates. "
                f"Attempts: {attempts_summary or 'none'}"
            )

        top = _require_dict(payload=selected_bundle.get("headline_row"), field_name="selected_headline_row")
        qa_json = _require_dict(payload=selected_bundle.get("qa_json"), field_name="selected_qa_json")
        winning_headline = str(selected_bundle.get("winning_headline") or "").strip()
        body_markdown = str(selected_bundle.get("body_markdown") or "")
        presell_markdown = str(selected_bundle.get("presell_markdown") or "")
        sales_page_markdown = str(selected_bundle.get("sales_page_markdown") or "")
        congruency = _require_dict(payload=selected_bundle.get("congruency"), field_name="selected_congruency")
        promise_contract = _require_dict(
            payload=selected_bundle.get("promise_contract"),
            field_name="selected_promise_contract",
        )
        prompt_chain = _require_dict(
            payload=selected_bundle.get("prompt_chain"),
            field_name="selected_prompt_chain",
        )
        semantic_gates = _require_dict(
            payload=selected_bundle.get("semantic_gates"),
            field_name="selected_semantic_gates",
        )
        quality_gate_report = _require_dict(
            payload=selected_bundle.get("quality_gate_report"),
            field_name="selected_quality_gate_report",
        )
        provenance_report = require_prompt_chain_provenance(prompt_chain=prompt_chain)

        copy_payload = {
            "headline": winning_headline,
            "body_markdown": body_markdown,
            "presell_markdown": presell_markdown,
            "sales_page_markdown": sales_page_markdown,
            "headline_scoring": top,
            "headline_qa": qa_json,
            "headline_attempts": qa_attempts,
            "congruency": congruency,
            "promise_contract": promise_contract,
            "promise_contracts": {
                "presell": promise_contract,
                "sales_page": promise_contract,
            },
            "copy_contract_profile": copy_contract_profile.model_dump(mode="python"),
            "copy_input_packet": copy_input_packet.model_dump(mode="python"),
            "semantic_gates": semantic_gates,
            "quality_gate_report": quality_gate_report,
            "copy_prompt_chain": prompt_chain,
            "copy_prompt_chain_provenance": provenance_report.model_dump(mode="python"),
            "copy_loop_report": copy_loop_report,
        }

        with session_scope() as session:
            artifacts_repo = ArtifactsRepository(session)
            copy_artifact = artifacts_repo.insert(
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                artifact_type=ArtifactTypeEnum.strategy_v2_copy,
                data=copy_payload,
            )
            agent_run_id = _record_agent_run(
                session=session,
                org_id=org_id,
                user_id=operator_user_id,
                client_id=client_id,
                objective_type="strategy_v2.copy_pipeline.prompt_chain",
                model=settings.STRATEGY_V2_COPY_MODEL,
                inputs_json={"stage3": stage3.model_dump(mode="python")},
                outputs_json={"copy_artifact_id": str(copy_artifact.id), "headline": winning_headline},
            )
            step_payload_artifact_id = _persist_step_payload(
                session=session,
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                workflow_run_id=workflow_run_id,
                step_key=V2_STEP_COPY_PIPELINE,
                title="Strategy V2 Copy Pipeline",
                summary="Copy prompt-chain generated and passed deterministic scoring gates.",
                payload={
                    "copy_artifact_id": str(copy_artifact.id),
                    "copy_payload": copy_payload,
                },
                model_name=settings.STRATEGY_V2_COPY_MODEL,
                prompt_version="strategy_v2.copy_pipeline.prompt_chain.v2",
                schema_version=SCHEMA_VERSION_V2,
                agent_run_id=agent_run_id,
            )
            WorkflowsRepository(session).log_activity(
                workflow_run_id=workflow_run_id,
                step="v2-10.copy_loop_report",
                status="completed",
                payload_out={"copy_loop_report": copy_loop_report},
            )
            return {
                "copy_artifact_id": str(copy_artifact.id),
                "copy_payload": copy_payload,
                "step_payload_artifact_id": step_payload_artifact_id,
            }

@activity.defn(name="strategy_v2.finalize_copy_approval")
def finalize_strategy_v2_copy_approval_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    workflow_run_id = str(params["workflow_run_id"])
    decision = FinalCopyApprovalDecision.model_validate(
        _require_dict(payload=params["final_approval_decision"], field_name="final_approval_decision")
    )
    decision_operator_user_id = _require_human_operator_user_id(
        operator_user_id=decision.operator_user_id,
        decision_name="Final copy approval",
    )
    cleaned_reviewed_candidate_ids = _enforce_decision_integrity_policy(
        decision_name="Final copy approval",
        decision_mode=decision.decision_mode,
        operator_note=decision.operator_note,
        attestation_reviewed_evidence=decision.attestation.reviewed_evidence,
        attestation_understands_impact=decision.attestation.understands_impact,
        reviewed_candidate_ids=decision.reviewed_candidate_ids,
        require_reviewed_candidates=True,
    )
    copy_payload = _require_dict(payload=params["copy_payload"], field_name="copy_payload")

    if not decision.approved:
        raise StrategyV2DecisionError(
            "Final copy approval decision rejected output. Workflow cannot continue without explicit approval."
        )

    with session_scope() as session:
        artifacts_repo = ArtifactsRepository(session)
        approved_artifact = artifacts_repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.strategy_v2_copy,
            data={
                "approved_copy": copy_payload,
                "decision": {
                    **decision.model_dump(mode="python"),
                    "reviewed_candidate_ids": cleaned_reviewed_candidate_ids,
                },
                "approved_at": _now_iso(),
            },
        )
        workflows_repo = WorkflowsRepository(session)
        workflows_repo.set_status(
            org_id=org_id,
            workflow_run_id=workflow_run_id,
            status=WorkflowStatusEnum.completed,
            finished_at=datetime.now(timezone.utc),
        )
        agent_run_id = _record_agent_run(
            session=session,
            org_id=org_id,
            user_id=decision_operator_user_id,
            client_id=client_id,
            objective_type="strategy_v2.final_copy_approval",
            model="human_decision",
            inputs_json={"decision": decision.model_dump(mode="python")},
            outputs_json={"approved_artifact_id": str(approved_artifact.id)},
        )
        step_payload_artifact_id = _persist_step_payload(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            workflow_run_id=workflow_run_id,
            step_key=V2_STEP_FINAL_APPROVAL_HITL,
            title="Strategy V2 Final Approval HITL",
            summary="Final copy approval recorded and workflow completed.",
            payload={
                "decision": {
                    **decision.model_dump(mode="python"),
                    "reviewed_candidate_ids": cleaned_reviewed_candidate_ids,
                },
                "approved_artifact_id": str(approved_artifact.id),
            },
            model_name="human_decision",
            prompt_version="strategy_v2.final_approval.v1",
            schema_version=SCHEMA_VERSION_V2,
            agent_run_id=agent_run_id,
        )
        return {
            "approved_artifact_id": str(approved_artifact.id),
            "step_payload_artifact_id": step_payload_artifact_id,
        }


@activity.defn(name="strategy_v2.mark_failed")
def mark_strategy_v2_failed_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    workflow_run_id = str(params["workflow_run_id"])
    error_message = str(params.get("error_message") or "Strategy V2 workflow failed")
    with session_scope() as session:
        workflows_repo = WorkflowsRepository(session)
        workflows_repo.set_status(
            org_id=org_id,
            workflow_run_id=workflow_run_id,
            status=WorkflowStatusEnum.failed,
            finished_at=datetime.now(timezone.utc),
        )
        workflows_repo.log_activity(
            workflow_run_id=workflow_run_id,
            step="strategy_v2",
            status="failed",
            error=error_message,
        )
    return {"ok": True}


@activity.defn(name="strategy_v2.check_enabled")
def check_strategy_v2_enabled_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    with session_scope() as session:
        enabled = is_strategy_v2_enabled(session=session, org_id=org_id, client_id=client_id)
    return {"enabled": enabled}
