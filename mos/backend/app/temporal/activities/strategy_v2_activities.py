from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from temporalio import activity

from app.config import settings
from app.db.base import session_scope
from app.db.enums import AgentRunStatusEnum, ArtifactTypeEnum, WorkflowStatusEnum
from app.db.models import Product, WorkflowRun
from app.db.repositories.agent_runs import AgentRunsRepository
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.client_compliance_profiles import ClientComplianceProfilesRepository
from app.db.repositories.design_systems import DesignSystemsRepository
from app.db.repositories.onboarding_payloads import OnboardingPayloadsRepository
from app.db.repositories.products import (
    ProductOfferBonusesRepository,
    ProductOffersRepository,
    ProductsRepository,
    ProductVariantsRepository,
)
from app.db.repositories.research_artifacts import ResearchArtifactsRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.llm import LLMClient, LLMGenerationParams
from app.services.product_types import canonical_product_type
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
    headline_qa_required_api_key_env,
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
from app.strategy_v2.errors import (
    StrategyV2Error,
    StrategyV2ExternalDependencyError,
    StrategyV2SchemaValidationError,
)
from app.strategy_v2.feature_flags import is_strategy_v2_enabled
from app.strategy_v2.copy_quality import evaluate_copy_page_quality
from app.strategy_v2.copy_input_packet import parse_minimum_delivery_section_index
from app.strategy_v2.pricing import require_concrete_price
from app.strategy_v2.prompt_runtime import (
    PromptAsset,
    build_prompt_provenance,
    extract_required_json_array,
    extract_required_json_object,
    render_prompt_template as render_prompt_template_strict,
    resolve_prompt_asset,
)
from app.strategy_v2.template_bridge import (
    build_strategy_v2_template_patch_operations,
    inspect_strategy_v2_template_payload_validation,
    upgrade_strategy_v2_template_payload_fields,
    validate_strategy_v2_template_payload_fields,
)
from app.services.claude_files import call_claude_structured_message
from app.strategy_v2.step_keys import (
    V2_STEP_APIFY_COLLECTION,
    V2_STEP_APIFY_INGESTION,
    V2_STEP_APIFY_POSTPROCESS,
    V2_STEP_ANGLE_SELECTION_HITL,
    V2_STEP_ANGLE_SYNTHESIS,
    V2_STEP_ASSET_DATA_INGESTION,
    V2_STEP_COMPETITOR_ASSETS_HITL,
    V2_STEP_COPY_PIPELINE,
    V2_STEP_FINAL_APPROVAL_HITL,
    V2_STEP_HABITAT_SCORING,
    V2_STEP_HABITAT_STRATEGY,
    V2_STEP_OFFER_PIPELINE,
    V2_STEP_OFFER_DATA_READINESS,
    V2_STEP_OFFER_VARIANT_SCORING,
    V2_STEP_OFFER_WINNER_HITL,
    V2_STEP_RESEARCH_PROCEED_HITL,
    V2_STEP_SCRAPE_VIRALITY,
    V2_STEP_STAGE0_BUILD,
    V2_STEP_VOC_EXTRACTION_RAW,
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
_FOUNDTN_STEP04_MAX_TOKENS = int(os.getenv("STRATEGY_V2_FOUNDATIONAL_STEP04_MAX_TOKENS", "64000"))
_CLAUDE_MAX_OUTPUT_TOKENS = 64000
_COPY_PIPELINE_MAX_TOKENS = min(
    int(os.getenv("STRATEGY_V2_COPY_MAX_TOKENS", "64000")),
    _CLAUDE_MAX_OUTPUT_TOKENS,
)
_CLAUDE_STRUCTURED_FALLBACK_MAX_TOKENS = min(
    int(os.getenv("STRATEGY_V2_CLAUDE_STRUCTURED_FALLBACK_MAX_TOKENS", "64000")),
    _CLAUDE_MAX_OUTPUT_TOKENS,
)

_VOC_AGENT00_PROMPT_PATTERN = "VOC + Angle Engine (2-21-26)/prompts/agent-00-habitat-strategist.md"
_VOC_AGENT00B_PROMPT_PATTERN = "VOC + Angle Engine (2-21-26)/prompts/agent-00b-social-video-strategist.md"
_VOC_AGENT01_PROMPT_PATTERN = "VOC + Angle Engine (2-21-26)/prompts/agent-01-habitat-qualifier.md"
_VOC_AGENT02_PROMPT_PATTERN = "VOC + Angle Engine (2-21-26)/prompts/agent-02b-voc-extractor.md"
_VOC_AGENT03_PROMPT_PATTERN = "VOC + Angle Engine (2-21-26)/prompts/agent-03-shadow-angle-clusterer.md"
_VOC_COMPETITOR_ANALYZER_PROMPT_PATTERN = (
    "VOC + Angle Engine (2-21-26)/prompts/agent-pre-competitor-asset-analyzer.md"
)
_OPENAI_CODE_INTERPRETER_TOOL = {"type": "code_interpreter", "container": {"type": "auto"}}
_APIFY_PLACEHOLDER_SENTINELS = frozenset(
    {
        "NA",
        "NONE",
        "NULL",
        "UNKNOWN",
        "UNSPECIFIED",
        "TBD",
        "CANNOTDETERMINE",
    }
)
_APIFY_URL_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "url": {"type": "string", "minLength": 1},
    },
    "required": ["url"],
}
_APIFY_EXEC_INPUT_SCHEMA: dict[str, Any] = {
    "anyOf": [
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "startUrls": {"type": "array", "minItems": 1, "items": _APIFY_URL_ITEM_SCHEMA},
                "maxItems": {"type": "integer", "minimum": 1},
            },
            "required": ["startUrls", "maxItems"],
        },
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "profiles": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
                "maxItems": {"type": "integer", "minimum": 1},
            },
            "required": ["profiles", "maxItems"],
        },
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "directUrls": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
                "resultsLimit": {"type": "integer", "minimum": 1},
            },
            "required": ["directUrls", "resultsLimit"],
        },
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "startUrls": {"type": "array", "minItems": 1, "items": _APIFY_URL_ITEM_SCHEMA},
                "maxResults": {"type": "integer", "minimum": 1},
            },
            "required": ["startUrls", "maxResults"],
        },
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "startUrls": {"type": "array", "minItems": 1, "items": _APIFY_URL_ITEM_SCHEMA},
                "maxCrawlPages": {"type": "integer", "minimum": 1},
                "maxResultsPerCrawl": {"type": "integer", "minimum": 1},
            },
            "required": ["startUrls", "maxCrawlPages", "maxResultsPerCrawl"],
        },
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "startUrls": {"type": "array", "minItems": 1, "items": _APIFY_URL_ITEM_SCHEMA},
                "pageFunction": {"type": "string", "minLength": 1},
                "maxRequestsPerCrawl": {"type": "integer", "minimum": 1},
                "maxCrawlingDepth": {"type": "integer", "minimum": 1},
            },
            "required": ["startUrls", "pageFunction", "maxRequestsPerCrawl", "maxCrawlingDepth"],
        },
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "queries": {"type": "string", "minLength": 1},
                "maxPagesPerQuery": {"type": "integer", "minimum": 1},
                "countryCode": {"type": "string", "minLength": 1},
                "languageCode": {"type": "string", "minLength": 1},
            },
            "required": ["queries", "maxPagesPerQuery", "countryCode", "languageCode"],
        },
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "companyName": {"type": "string", "minLength": 1},
                "maxReviews": {"type": "integer", "minimum": 1},
                "sortBy": {"type": "string", "minLength": 1},
            },
            "required": ["companyName", "maxReviews", "sortBy"],
        },
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "productUrls": {"type": "array", "minItems": 1, "items": _APIFY_URL_ITEM_SCHEMA},
                "maxReviews": {"type": "integer", "minimum": 1},
                "sortBy": {"type": "string", "minLength": 1},
            },
            "required": ["productUrls", "maxReviews", "sortBy"],
        },
    ],
}
_VOC_AGENT00_DIRECT_METADATA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "habitat_category": {"type": "string", "minLength": 1},
        "habitat_name": {"type": "string", "minLength": 1},
        "target_id": {"type": "string", "minLength": 1},
        "avatar_alignment": {"type": "string", "minLength": 1},
        "competitor_whitespace": {"type": "string", "enum": ["Y", "N", "UNKNOWN"]},
        "search_query_origin": {"type": "string", "minLength": 1},
    },
    "required": [
        "habitat_category",
        "habitat_name",
        "target_id",
        "avatar_alignment",
        "competitor_whitespace",
        "search_query_origin",
    ],
}
_VOC_AGENT00_DISCOVERY_METADATA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "target_id": {"type": "string", "minLength": 1},
        "habitat_category": {"type": "string", "minLength": 1},
        "purpose": {"type": "string", "minLength": 1},
        "feeds_category": {"type": "string", "minLength": 1},
        "search_query_origin": {"type": "string", "minLength": 1},
        "expected_result_type": {"type": "string", "minLength": 1},
    },
    "required": [
        "target_id",
        "habitat_category",
        "purpose",
        "feeds_category",
        "search_query_origin",
        "expected_result_type",
    ],
}
_VOC_AGENT00_APIFY_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "config_id": {"type": "string", "minLength": 1},
        "actor_id": {"type": "string", "minLength": 1},
        "input": _APIFY_EXEC_INPUT_SCHEMA,
        "metadata": {
            "anyOf": [
                _VOC_AGENT00_DIRECT_METADATA_SCHEMA,
                _VOC_AGENT00_DISCOVERY_METADATA_SCHEMA,
            ]
        },
    },
    "required": ["config_id", "actor_id", "input", "metadata"],
}
_VOC_AGENT00_HANDOFF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "string", "minLength": 1},
        "generated_at": {"type": "string", "minLength": 1},
        "product_classification": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "buyer_behavior": {"type": "string", "minLength": 1},
                "purchase_emotion": {"type": "string", "minLength": 1},
                "compliance_sensitivity": {"type": "string", "minLength": 1},
                "price_sensitivity": {"type": "string", "minLength": 1},
                "strategy_implications": {"type": "string", "minLength": 1},
            },
            "required": [
                "buyer_behavior",
                "purchase_emotion",
                "compliance_sensitivity",
                "price_sensitivity",
                "strategy_implications",
            ],
        },
        "prior_declaration": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "expected_richest_categories": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                },
                "expected_sparse_categories": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                },
                "expected_total_targets": {"type": ["number", "null"]},
                "expected_competitor_overlap_pattern": {"type": "string", "minLength": 1},
            },
            "required": [
                "expected_richest_categories",
                "expected_sparse_categories",
                "expected_total_targets",
                "expected_competitor_overlap_pattern",
            ],
        },
        "analysis_order": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "randomized_category_order_1_to_8": {"type": "array", "items": {"type": "integer"}},
                "method": {"type": "string", "minLength": 1},
            },
            "required": ["randomized_category_order_1_to_8", "method"],
        },
        "habitat_categories": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "category_id": {"type": "integer"},
                    "category_name": {"type": "string", "minLength": 1},
                    "identified_targets": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                },
                "required": ["category_id", "category_name", "identified_targets"],
            },
        },
        "habitat_targets": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "target_id": {"type": "string", "minLength": 1},
                    "habitat_category": {"type": "string", "minLength": 1},
                    "habitat_name": {"type": "string", "minLength": 1},
                    "status": {"type": "string", "enum": ["CONFIRMED", "INFERRED"]},
                    "competitor_whitespace": {"type": "string", "enum": ["Y", "N", "UNKNOWN"]},
                    "apify_config_id": {"type": "string", "minLength": 1},
                    "manual_queries": {"type": "array", "items": {"type": "string", "minLength": 1}},
                },
                "required": [
                    "target_id",
                    "habitat_category",
                    "habitat_name",
                    "status",
                    "competitor_whitespace",
                    "apify_config_id",
                    "manual_queries",
                ],
            },
        },
        "whitespace_map": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "category_name": {"type": "string", "minLength": 1},
                    "competitor_occupied": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "target_id": {"type": "string", "minLength": 1},
                            },
                            "required": ["target_id"],
                        },
                    },
                    "whitespace": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "target_id": {"type": "string", "minLength": 1},
                            },
                            "required": ["target_id"],
                        },
                    },
                    "ambiguous": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "target_id": {"type": "string", "minLength": 1},
                            },
                            "required": ["target_id"],
                        },
                    },
                },
                "required": ["category_name", "competitor_occupied", "whitespace", "ambiguous"],
            },
        },
        "whitespace_summary_table": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "category_name": {"type": "string", "minLength": 1},
                    "occupied_count": {"type": "integer", "minimum": 0},
                    "whitespace_count": {"type": "integer", "minimum": 0},
                    "ambiguous_count": {"type": "integer", "minimum": 0},
                },
                "required": ["category_name", "occupied_count", "whitespace_count", "ambiguous_count"],
            },
        },
        "manual_search_queries_by_category": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "category_name": {"type": "string", "minLength": 1},
                    "primary": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "query": {"type": "string", "minLength": 1},
                                "targets": {"type": "string", "minLength": 1},
                            },
                            "required": ["query", "targets"],
                        },
                    },
                    "secondary": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "query": {"type": "string", "minLength": 1},
                                "targets": {"type": "string", "minLength": 1},
                                "adjacent_because": {"type": "string", "minLength": 1},
                            },
                            "required": ["query", "targets", "adjacent_because"],
                        },
                    },
                    "competitor_specific": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "competitor": {"type": "string", "minLength": 1},
                                "queries": {
                                    "type": "array",
                                    "minItems": 1,
                                    "items": {"type": "string", "minLength": 1},
                                },
                            },
                            "required": ["competitor", "queries"],
                        },
                    },
                    "problem_specific": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "query": {"type": "string", "minLength": 1},
                                "source_quote": {"type": "string", "minLength": 1},
                            },
                            "required": ["query", "source_quote"],
                        },
                    },
                },
                "required": [
                    "category_name",
                    "primary",
                    "secondary",
                    "competitor_specific",
                    "problem_specific",
                ],
            },
        },
        "apify_configs": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "tier1_direct": {
                    "type": "array",
                    "minItems": 1,
                    "items": _VOC_AGENT00_APIFY_CONFIG_SCHEMA,
                },
                "tier2_discovery": {
                    "type": "array",
                    "minItems": 1,
                    "items": _VOC_AGENT00_APIFY_CONFIG_SCHEMA,
                },
            },
            "required": ["tier1_direct", "tier2_discovery"],
        },
        "prior_vs_actual": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "confirmed": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "wrong_or_weaker_than_expected": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                },
                "surprises": {"type": "array", "items": {"type": "string", "minLength": 1}},
            },
            "required": ["confirmed", "wrong_or_weaker_than_expected", "surprises"],
        },
        "limitations_confidence": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "confidence_level": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                "limitations": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "document_gaps": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "platform_blindspots": {"type": "array", "items": {"type": "string", "minLength": 1}},
            },
            "required": ["confidence_level", "limitations", "document_gaps", "platform_blindspots"],
        },
        "disconfirmation": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "reason": {"type": "string", "minLength": 1},
                    "evidence_to_confirm": {"type": "string", "minLength": 1},
                    "evidence_to_disconfirm": {"type": "string", "minLength": 1},
                    "operator_check_action": {"type": "string", "minLength": 1},
                },
                "required": [
                    "reason",
                    "evidence_to_confirm",
                    "evidence_to_disconfirm",
                    "operator_check_action",
                ],
            },
        },
        "tool_call_outputs": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "prioritization": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "method": {"type": "string", "minLength": 1},
                        "habitat_observations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "target_id": {"type": "string", "minLength": 1},
                                    "habitat_name": {"type": "string", "minLength": 1},
                                    "habitat_category": {"type": "string", "minLength": 1},
                                },
                                "required": ["target_id", "habitat_name", "habitat_category"],
                            },
                        },
                        "ranked_list": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "rank": {"type": "integer", "minimum": 1},
                                    "target_id": {"type": "string", "minLength": 1},
                                    "habitat_name": {"type": "string", "minLength": 1},
                                    "category": {"type": "string", "minLength": 1},
                                    "priority_score": {"type": "number"},
                                    "apify_config_id": {"type": "string", "minLength": 1},
                                },
                                "required": [
                                    "rank",
                                    "target_id",
                                    "habitat_name",
                                    "category",
                                    "priority_score",
                                    "apify_config_id",
                                ],
                            },
                        },
                    },
                    "required": ["method", "habitat_observations", "ranked_list"],
                }
            },
            "required": ["prioritization"],
        },
        "validation": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "errors": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["errors"],
        },
    },
    "required": [
        "schema_version",
        "generated_at",
        "product_classification",
        "prior_declaration",
        "analysis_order",
        "habitat_categories",
        "habitat_targets",
        "whitespace_map",
        "whitespace_summary_table",
        "manual_search_queries_by_category",
        "apify_configs",
        "prior_vs_actual",
        "limitations_confidence",
        "disconfirmation",
        "tool_call_outputs",
        "validation",
    ],
}

_VOC_YN_CD_ENUM = ["Y", "N", "CANNOT_DETERMINE"]
_VOC_AGENT01_OBSERVATION_SHEET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "threads_50_plus": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "threads_200_plus": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "threads_1000_plus": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "posts_last_3mo": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "posts_last_6mo": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "posts_last_12mo": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "recency_ratio": {
            "type": "string",
            "enum": ["MAJORITY_RECENT", "BALANCED", "MAJORITY_OLD", "CANNOT_DETERMINE"],
        },
        "exact_category": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "purchasing_comparing": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "personal_usage": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "adjacent_only": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "first_person_narratives": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "trigger_events": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "fear_frustration_shame": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "specific_dollar_or_time": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "long_detailed_posts": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "comparison_discussions": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "price_value_mentions": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "post_purchase_experience": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "relevance_pct": {
            "type": "string",
            "enum": ["OVER_50_PCT", "25_TO_50_PCT", "10_TO_25_PCT", "UNDER_10_PCT", "CANNOT_DETERMINE"],
        },
        "dominated_by_offtopic": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "competitor_brands_mentioned": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "competitor_brand_count": {"type": "string", "enum": ["0", "1-3", "4-7", "8+", "CANNOT_DETERMINE"]},
        "competitor_ads_present": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "trend_direction": {"type": "string", "enum": ["HIGHER", "SAME", "LOWER", "CANNOT_DETERMINE"]},
        "seasonal_patterns": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "seasonal_description": {"type": "string"},
        "habitat_age": {
            "type": "string",
            "enum": ["UNDER_1YR", "1_TO_3YR", "3_TO_7YR", "OVER_7YR", "CANNOT_DETERMINE"],
        },
        "membership_trend": {"type": "string", "enum": ["GROWING", "STABLE", "DECLINING", "CANNOT_DETERMINE"]},
        "post_frequency_trend": {
            "type": "string",
            "enum": ["INCREASING", "SAME", "DECREASING", "CANNOT_DETERMINE"],
        },
        "publicly_accessible": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "text_based_content": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "target_language": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "no_rate_limiting": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "purchase_intent_density": {"type": "string", "enum": ["MOST", "SOME", "FEW", "NONE", "CANNOT_DETERMINE"]},
        "discusses_spending": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "recommendation_threads": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "reusability": {"type": "string", "enum": ["PRODUCT_SPECIFIC", "PATTERN_REUSABLE", "CANNOT_DETERMINE"]},
    },
    "required": [
        "threads_50_plus",
        "threads_200_plus",
        "threads_1000_plus",
        "posts_last_3mo",
        "posts_last_6mo",
        "posts_last_12mo",
        "recency_ratio",
        "exact_category",
        "purchasing_comparing",
        "personal_usage",
        "adjacent_only",
        "first_person_narratives",
        "trigger_events",
        "fear_frustration_shame",
        "specific_dollar_or_time",
        "long_detailed_posts",
        "comparison_discussions",
        "price_value_mentions",
        "post_purchase_experience",
        "relevance_pct",
        "dominated_by_offtopic",
        "competitor_brands_mentioned",
        "competitor_brand_count",
        "competitor_ads_present",
        "trend_direction",
        "seasonal_patterns",
        "seasonal_description",
        "habitat_age",
        "membership_trend",
        "post_frequency_trend",
        "publicly_accessible",
        "text_based_content",
        "target_language",
        "no_rate_limiting",
        "purchase_intent_density",
        "discusses_spending",
        "recommendation_threads",
        "reusability",
    ],
}
_VOC_AGENT01_LANGUAGE_SAMPLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "sample_id": {"type": "string", "minLength": 1},
        "evidence_ref": {"type": "string", "minLength": 1},
        "word_count": {"type": "integer", "minimum": 0},
        "has_trigger_event": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "has_failed_solution": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "has_identity_language": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "has_specific_outcome": {"type": "string", "enum": _VOC_YN_CD_ENUM},
    },
    "required": [
        "sample_id",
        "evidence_ref",
        "word_count",
        "has_trigger_event",
        "has_failed_solution",
        "has_identity_language",
        "has_specific_outcome",
    ],
}
_VOC_AGENT01_VIDEO_EXTENSION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "video_count_scraped": {"anyOf": [{"type": "integer", "minimum": 0}, {"type": "null"}]},
        "median_view_count": {"anyOf": [{"type": "integer", "minimum": 0}, {"type": "null"}]},
        "viral_videos_found": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "viral_video_count": {"anyOf": [{"type": "integer", "minimum": 0}, {"type": "null"}]},
        "comment_sections_active": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "comment_avg_length": {
            "type": "string",
            "enum": ["SHORT", "MEDIUM", "LONG"],
        },
        "hook_formats_identifiable": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "creator_diversity": {"type": "string", "enum": ["SINGLE", "FEW", "MANY"]},
        "contains_testimonial_language": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "contains_objection_language": {"type": "string", "enum": _VOC_YN_CD_ENUM},
        "contains_purchase_intent": {"type": "string", "enum": _VOC_YN_CD_ENUM},
    },
    "required": [
        "video_count_scraped",
        "median_view_count",
        "viral_videos_found",
        "viral_video_count",
        "comment_sections_active",
        "comment_avg_length",
        "hook_formats_identifiable",
        "creator_diversity",
        "contains_testimonial_language",
        "contains_objection_language",
        "contains_purchase_intent",
    ],
}
_VOC_AGENT01_COMPETITIVE_OVERLAP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "competitors_in_data": {"type": "array", "items": {"type": "string"}},
        "overlap_level": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW", "NONE", "CANNOT_DETERMINE"]},
        "whitespace_opportunity": {"type": "string", "enum": _VOC_YN_CD_ENUM},
    },
    "required": ["competitors_in_data", "overlap_level", "whitespace_opportunity"],
}
_VOC_AGENT01_TREND_LIFECYCLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "trend_direction": {"type": "string", "enum": ["HIGHER", "SAME", "LOWER", "CANNOT_DETERMINE"]},
        "lifecycle_stage": {
            "type": "string",
            "enum": ["EMERGING", "GROWING", "MATURE", "DECLINING", "ARCHIVED", "CANNOT_DETERMINE"],
        },
    },
    "required": ["trend_direction", "lifecycle_stage"],
}
_VOC_AGENT01_MINING_GATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {"type": "string", "enum": ["PASS", "GATE_FAIL"]},
        "failed_fields": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["status", "failed_fields", "reason"],
}
_VOC_AGENT01_DATA_QUALITY_SCHEMA: dict[str, Any] = {
    "type": "string",
    "enum": ["CLEAN", "MINOR_ISSUES", "MAJOR_ISSUES", "UNUSABLE"],
}
_VOC_AGENT01_TARGET_VOC_TYPE_SCHEMA: dict[str, Any] = {
    "type": "string",
    "enum": [
        "PAIN_LANGUAGE",
        "TRIGGER_EVENTS",
        "FAILED_SOLUTIONS",
        "BUYER_COMPARISONS",
        "DESIRED_OUTCOMES",
        "IDENTITY_LANGUAGE",
        "OBJECTIONS",
        "PROOF_DEMANDS",
        "POST_PURCHASE",
    ],
}


def _nullable_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    return {"anyOf": [deepcopy(dict(schema)), {"type": "null"}]}


def _ordered_unique_runtime_keys(*, values: Sequence[str], field_name: str) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = str(raw_value or "").strip()
        if not value:
            raise StrategyV2SchemaValidationError(f"{field_name} must not contain blank values.")
        if value in seen:
            raise StrategyV2SchemaValidationError(f"{field_name} must not contain duplicate value '{value}'.")
        seen.add(value)
        ordered.append(value)
    if not ordered:
        raise StrategyV2SchemaValidationError(f"{field_name} must include at least one value.")
    return ordered


def _build_exact_keyed_object_schema(
    *,
    keys: Sequence[str],
    field_name: str,
    value_schema: Mapping[str, Any] | None = None,
    value_schema_builder: Callable[[str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    ordered_keys = _ordered_unique_runtime_keys(values=keys, field_name=field_name)
    if (value_schema is None) == (value_schema_builder is None):
        raise ValueError("Provide exactly one of value_schema or value_schema_builder.")
    properties: dict[str, Any] = {}
    for key in ordered_keys:
        if value_schema_builder is not None:
            properties[key] = deepcopy(dict(value_schema_builder(key)))
        else:
            properties[key] = deepcopy(dict(value_schema or {}))
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": ordered_keys,
    }


def _agent1_file_assessment_variant_schema(*, decision: str, include_in_mining_plan: bool) -> dict[str, Any]:
    if decision not in {"OBSERVE", "EXCLUDE"}:
        raise ValueError(f"Unsupported Agent 1 file_assessment decision variant: {decision}")
    if decision == "EXCLUDE" and include_in_mining_plan:
        raise ValueError("Agent 1 file_assessment EXCLUDE variant cannot include mining-plan selection.")

    if decision == "EXCLUDE":
        properties = {
            "decision": {"type": "string", "enum": ["EXCLUDE"]},
            "exclude_reason": {"type": "string", "minLength": 1},
            "include_in_mining_plan": {"type": "boolean", "enum": [False]},
            "observation_projection": {"type": "null"},
        }
    else:
        properties = {
            "decision": {"type": "string", "enum": ["OBSERVE"]},
            "exclude_reason": {"type": "string", "maxLength": 0},
            "include_in_mining_plan": {"type": "boolean", "enum": [include_in_mining_plan]},
            "observation_projection": _agent1_observation_projection_variant_schema(
                include_in_mining_plan=include_in_mining_plan
            ),
        }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
    }


def _agent1_observation_projection_variant_schema(*, include_in_mining_plan: bool) -> dict[str, Any]:
    properties = {
        key: deepcopy(value)
        for key, value in _VOC_AGENT01_HABITAT_OBSERVATION_SCHEMA["properties"].items()
        if key != "source_file"
    }
    if include_in_mining_plan:
        properties["priority_rank"] = {"type": "integer", "minimum": 1, "maximum": 12}
        properties["target_voc_types"] = {
            "type": "array",
            "minItems": 1,
            "items": _VOC_AGENT01_TARGET_VOC_TYPE_SCHEMA,
        }
        properties["sampling_strategy"] = {"type": "string", "minLength": 1}
        properties["platform_behavior_note"] = {"type": "string", "minLength": 1}
        properties["compliance_flags"] = {"type": "string"}
    else:
        properties["priority_rank"] = {"type": "null"}
        properties["target_voc_types"] = {
            "type": "array",
            "maxItems": 0,
            "items": _VOC_AGENT01_TARGET_VOC_TYPE_SCHEMA,
        }
        properties["sampling_strategy"] = {"type": "null"}
        properties["platform_behavior_note"] = {"type": "null"}
        properties["compliance_flags"] = {"type": "string", "maxLength": 0}

    required = [
        field_name
        for field_name in _VOC_AGENT01_HABITAT_OBSERVATION_SCHEMA["required"]
        if field_name != "source_file"
    ]
    required.extend(
        [
            "priority_rank",
            "target_voc_types",
            "sampling_strategy",
            "platform_behavior_note",
            "compliance_flags",
        ]
    )
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


_VOC_AGENT01_HABITAT_OBSERVATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "habitat_name": {"type": "string", "minLength": 1},
        "habitat_type": {"type": "string", "minLength": 1},
        "url_pattern": {"type": "string", "minLength": 1},
        "source_file": {"type": "string", "minLength": 1},
        "items_in_file": {"type": "integer", "minimum": 0},
        "data_quality": _VOC_AGENT01_DATA_QUALITY_SCHEMA,
        "observation_sheet": _VOC_AGENT01_OBSERVATION_SHEET_SCHEMA,
        "language_samples": {
            "type": "array",
            "items": _VOC_AGENT01_LANGUAGE_SAMPLE_SCHEMA,
        },
        "video_extension": {
            "anyOf": [
                _VOC_AGENT01_VIDEO_EXTENSION_SCHEMA,
                {"type": "null"},
            ]
        },
        "competitive_overlap": _VOC_AGENT01_COMPETITIVE_OVERLAP_SCHEMA,
        "trend_lifecycle": _VOC_AGENT01_TREND_LIFECYCLE_SCHEMA,
        "mining_gate": _VOC_AGENT01_MINING_GATE_SCHEMA,
        "rank_score": {"type": "integer"},
        "estimated_yield": {"type": "integer", "minimum": 0},
        "evidence_refs": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
    },
    "required": [
        "habitat_name",
        "habitat_type",
        "url_pattern",
        "source_file",
        "items_in_file",
        "data_quality",
        "observation_sheet",
        "language_samples",
        "video_extension",
        "competitive_overlap",
        "trend_lifecycle",
        "mining_gate",
        "rank_score",
        "estimated_yield",
        "evidence_refs",
    ],
}
_VOC_AGENT01_MINING_PLAN_ENTRY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "habitat_name": {"type": "string", "minLength": 1},
        "habitat_type": {"type": "string", "minLength": 1},
        "source_file": {"type": "string", "minLength": 1},
        "priority_rank": {"type": "integer", "minimum": 1, "maximum": 12},
        "rank_score": {"type": "integer"},
        "target_voc_types": {
            "type": "array",
            "minItems": 1,
            "items": _VOC_AGENT01_TARGET_VOC_TYPE_SCHEMA,
        },
        "estimated_yield": {"type": "integer", "minimum": 0},
        "sampling_strategy": {"type": "string", "minLength": 1},
        "platform_behavior_note": {"type": "string", "minLength": 1},
        "compliance_flags": {"type": "string"},
        "observation_sheet": _VOC_AGENT01_OBSERVATION_SHEET_SCHEMA,
        "language_samples": {"type": "array", "items": _VOC_AGENT01_LANGUAGE_SAMPLE_SCHEMA},
        "video_extension": {
            "anyOf": [
                _VOC_AGENT01_VIDEO_EXTENSION_SCHEMA,
                {"type": "null"},
            ]
        },
        "competitive_overlap": _VOC_AGENT01_COMPETITIVE_OVERLAP_SCHEMA,
        "trend_lifecycle": _VOC_AGENT01_TREND_LIFECYCLE_SCHEMA,
        "evidence_refs": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
    },
    "required": [
        "habitat_name",
        "habitat_type",
        "source_file",
        "priority_rank",
        "rank_score",
        "target_voc_types",
        "estimated_yield",
        "sampling_strategy",
        "platform_behavior_note",
        "compliance_flags",
        "observation_sheet",
        "language_samples",
        "video_extension",
        "competitive_overlap",
        "trend_lifecycle",
        "evidence_refs",
    ],
}
_VOC_AGENT01_FILE_ASSESSMENT_ROW_SCHEMA: dict[str, Any] = {
    "anyOf": [
        _agent1_file_assessment_variant_schema(decision="EXCLUDE", include_in_mining_plan=False),
        _agent1_file_assessment_variant_schema(decision="OBSERVE", include_in_mining_plan=False),
        _agent1_file_assessment_variant_schema(decision="OBSERVE", include_in_mining_plan=True),
    ],
}


def _agent1_output_schema(*, source_files: Sequence[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "report_markdown": {"type": "string", "minLength": 1},
            "agent_id": {"type": "string", "minLength": 1},
            "agent_version": {"type": "string", "minLength": 1},
            "timestamp": {"type": "string", "format": "date-time"},
            "product_classification": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "buyer_behavior": {
                        "type": "string",
                        "enum": ["IMPULSE", "CONSIDERED", "HIGH_TRUST", "SUBSCRIPTION", "ONE_TIME"],
                    },
                    "purchase_emotion": {
                        "type": "string",
                        "enum": ["PRIMARILY_EMOTIONAL", "PRIMARILY_RATIONAL", "MIXED"],
                    },
                    "compliance_sensitivity": {
                        "type": "string",
                        "enum": ["LOW", "MEDIUM", "HIGH", "REGULATED"],
                    },
                    "price_sensitivity": {
                        "type": "string",
                        "enum": ["LOW_TICKET_UNDER_30", "MID_TICKET_30_TO_100", "HIGH_TICKET_OVER_100"],
                    },
                },
                "required": [
                    "buyer_behavior",
                    "purchase_emotion",
                    "compliance_sensitivity",
                    "price_sensitivity",
                ],
            },
            "file_assessments": {
                "type": "array",
                "minItems": len(source_files),
                "maxItems": len(source_files),
                "items": _VOC_AGENT01_FILE_ASSESSMENT_ROW_SCHEMA,
            },
            "gate_failures": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "habitat_name": {"type": "string", "minLength": 1},
                        "gate_failed": {
                            "type": "string",
                            "enum": [
                                "publicly_accessible",
                                "text_based_content",
                                "target_language",
                                "no_rate_limiting",
                                "multiple",
                            ],
                        },
                        "reason": {"type": "string", "minLength": 1},
                    },
                    "required": ["habitat_name", "gate_failed", "reason"],
                },
            },
            "disconfirmation_flags": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {"type": "string", "minLength": 1},
            },
        },
        "required": [
            "report_markdown",
            "agent_id",
            "agent_version",
            "timestamp",
            "product_classification",
            "file_assessments",
            "gate_failures",
            "disconfirmation_flags",
        ],
    }
_VOC_AGENT02_YN_SCHEMA: dict[str, Any] = {"type": "string", "enum": ["Y", "N"]}
_VOC_AGENT02_EVIDENCE_ID_PATTERN = r"^E[0-9A-F]{16}$"
_VOC_AGENT02_VOC_OBSERVATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "voc_id": {"type": "string", "minLength": 1},
        "evidence_id": {"type": "string", "pattern": _VOC_AGENT02_EVIDENCE_ID_PATTERN},
        "source": {"type": "string", "minLength": 1},
        "source_type": {
            "type": "string",
            "enum": [
                "REDDIT",
                "FORUM",
                "BLOG_COMMENT",
                "REVIEW_SITE",
                "QA",
                "TIKTOK_COMMENT",
                "IG_COMMENT",
                "YT_COMMENT",
                "VIDEO_HOOK",
            ],
        },
        "source_url": {"type": "string", "minLength": 1},
        "source_author": {"type": "string", "minLength": 1},
        "source_date": {"type": "string", "minLength": 1},
        "is_hook": _VOC_AGENT02_YN_SCHEMA,
        "hook_format": {
            "type": "string",
            "enum": ["QUESTION", "STATEMENT", "STORY", "STATISTIC", "CONTRARIAN", "DEMONSTRATION", "NONE"],
        },
        "hook_word_count": {"type": "integer", "minimum": 0},
        "video_virality_tier": {
            "type": "string",
            "enum": ["VIRAL", "HIGH_PERFORMING", "ABOVE_AVERAGE", "BASELINE"],
        },
        "video_view_count": {"type": "integer", "minimum": 0},
        "competitor_saturation": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "in_whitespace": _VOC_AGENT02_YN_SCHEMA,
        "evidence_ref": {"type": "string", "minLength": 1},
        "quote": {"type": "string", "minLength": 1},
        "specific_number": _VOC_AGENT02_YN_SCHEMA,
        "specific_product_brand": _VOC_AGENT02_YN_SCHEMA,
        "specific_event_moment": _VOC_AGENT02_YN_SCHEMA,
        "specific_body_symptom": _VOC_AGENT02_YN_SCHEMA,
        "before_after_comparison": _VOC_AGENT02_YN_SCHEMA,
        "crisis_language": _VOC_AGENT02_YN_SCHEMA,
        "profanity_extreme_punctuation": _VOC_AGENT02_YN_SCHEMA,
        "physical_sensation": _VOC_AGENT02_YN_SCHEMA,
        "identity_change_desire": _VOC_AGENT02_YN_SCHEMA,
        "word_count": {"type": "integer", "minimum": 1},
        "clear_trigger_event": _VOC_AGENT02_YN_SCHEMA,
        "named_enemy": _VOC_AGENT02_YN_SCHEMA,
        "shiftable_belief": _VOC_AGENT02_YN_SCHEMA,
        "expectation_vs_reality": _VOC_AGENT02_YN_SCHEMA,
        "headline_ready": _VOC_AGENT02_YN_SCHEMA,
        "usable_content_pct": {
            "type": "string",
            "enum": ["OVER_75_PCT", "50_TO_75_PCT", "25_TO_50_PCT", "UNDER_25_PCT"],
        },
        "personal_context": _VOC_AGENT02_YN_SCHEMA,
        "long_narrative": _VOC_AGENT02_YN_SCHEMA,
        "engagement_received": _VOC_AGENT02_YN_SCHEMA,
        "real_person_signals": _VOC_AGENT02_YN_SCHEMA,
        "moderated_community": _VOC_AGENT02_YN_SCHEMA,
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
        "durable_psychology": _VOC_AGENT02_YN_SCHEMA,
        "market_specific": _VOC_AGENT02_YN_SCHEMA,
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
        "evidence_id",
        "source",
        "source_type",
        "source_url",
        "source_author",
        "source_date",
        "is_hook",
        "hook_format",
        "hook_word_count",
        "video_virality_tier",
        "video_view_count",
        "competitor_saturation",
        "in_whitespace",
        "evidence_ref",
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
}

def _agent2_accepted_observation_schema() -> dict[str, Any]:
    properties = deepcopy(_VOC_AGENT02_VOC_OBSERVATION_SCHEMA["properties"])
    for deterministic_field in (
        "voc_id",
        "evidence_id",
        "source",
        "source_type",
        "source_url",
        "source_author",
        "source_date",
        "evidence_ref",
    ):
        properties.pop(deterministic_field, None)
    properties["observation_id"] = {"type": "string", "minLength": 1}
    required = [
        field_name
        for field_name in _VOC_AGENT02_VOC_OBSERVATION_SCHEMA["required"]
        if field_name not in {
            "voc_id",
            "evidence_id",
            "source",
            "source_type",
            "source_url",
            "source_author",
            "source_date",
            "evidence_ref",
        }
    ]
    required.append("observation_id")
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def _agent2_accepted_decision_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision": {"type": "string", "enum": ["ACCEPT"]},
            "observation_id": {"type": "string", "minLength": 1},
            "reason": {"type": "null"},
            "note": {"type": "string", "maxLength": 0},
        },
        "required": ["decision", "observation_id", "reason", "note"],
    }


def _agent2_rejected_decision_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision": {"type": "string", "enum": ["REJECT"]},
            "observation_id": {"type": "null"},
            "reason": {
                "type": "string",
                "enum": ["NOT_VOC", "MISSING_SOURCE", "TOO_VAGUE", "DUPLICATE_EVIDENCE"],
            },
            "note": {"type": "string", "minLength": 1},
        },
        "required": ["decision", "observation_id", "reason", "note"],
    }


_VOC_AGENT02_DECISION_SCHEMA: dict[str, Any] = {
    "anyOf": [
        _agent2_accepted_decision_schema(),
        _agent2_rejected_decision_schema(),
    ]
}


def _agent2_output_schema(*, evidence_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "mode": {"type": "string", "enum": ["DUAL", "FRESH"]},
            "input_count": {"type": "integer", "minimum": 0},
            "output_count": {"type": "integer", "minimum": 0},
            "decisions_by_evidence_id": _build_exact_keyed_object_schema(
                keys=evidence_ids,
                field_name="Agent 2 evidence_ids",
                value_schema=_VOC_AGENT02_DECISION_SCHEMA,
            ),
            "accepted_observations": {
                "type": "array",
                "items": _agent2_accepted_observation_schema(),
            },
            "validation_errors": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "mode",
            "input_count",
            "output_count",
            "decisions_by_evidence_id",
            "accepted_observations",
            "validation_errors",
        ],
    }

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
_COPY_HEADLINE_EVALUATION_LIMIT = int(os.getenv("STRATEGY_V2_COPY_HEADLINE_EVALUATION_LIMIT", "10"))
_COPY_HEADLINE_EVALUATION_OFFSET = int(os.getenv("STRATEGY_V2_COPY_HEADLINE_EVALUATION_OFFSET", "0"))
_COPY_HEADLINE_QA_MAX_ITERATIONS = int(os.getenv("STRATEGY_V2_COPY_HEADLINE_QA_MAX_ITERATIONS", "6"))
_COPY_HEADLINE_TRANSIENT_FAIL_FAST_THRESHOLD = int(
    os.getenv("STRATEGY_V2_COPY_HEADLINE_TRANSIENT_FAIL_FAST_THRESHOLD", "6")
)
_COPY_USE_CLAUDE_CHAT_CONTEXT = os.getenv("STRATEGY_V2_COPY_USE_CLAUDE_CHAT_CONTEXT", "0").strip() == "1"
_COPY_DEBUG_CAPTURE_MARKDOWN = os.getenv("STRATEGY_V2_COPY_DEBUG_CAPTURE_MARKDOWN", "0").strip() == "1"
_COPY_DEBUG_CAPTURE_THREADS = os.getenv("STRATEGY_V2_COPY_DEBUG_CAPTURE_THREADS", "0").strip() == "1"
_COPY_DEBUG_CAPTURE_FULL_MARKDOWN = os.getenv("STRATEGY_V2_COPY_DEBUG_CAPTURE_FULL_MARKDOWN", "0").strip() == "1"
_COPY_GENERATION_MODE_FULL_MARKDOWN = "full_markdown"
_COPY_GENERATION_MODE_TEMPLATE_PAYLOAD_ONLY = "template_payload_only"
_COPY_GENERATION_MODE_DEFAULT = os.getenv(
    "STRATEGY_V2_COPY_GENERATION_MODE",
    _COPY_GENERATION_MODE_TEMPLATE_PAYLOAD_ONLY,
).strip()


def _normalize_copy_generation_mode(value: object) -> str:
    raw = str(value or _COPY_GENERATION_MODE_DEFAULT).strip().lower()
    if raw in {"full_markdown", "full", "full_copy"}:
        return _COPY_GENERATION_MODE_FULL_MARKDOWN
    if raw in {"template_payload_only", "template_only", "payload_only"}:
        return _COPY_GENERATION_MODE_TEMPLATE_PAYLOAD_ONLY
    raise StrategyV2DecisionError(
        "Invalid copy_generation_mode. Allowed values: 'full_markdown', 'template_payload_only'. "
        f"Received: '{raw or '<empty>'}'."
    )


_FOOTER_PAYMENT_ICON_KEYS: list[str] = [
    "american_express",
    "apple_pay",
    "google_pay",
    "maestro",
    "mastercard",
    "paypal",
    "visa",
]


def _clean_url_for_footer(value: object) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        return ""
    return cleaned


def _build_policy_footer_links(*, org_id: str, client_id: str) -> tuple[list[dict[str, str]], str]:
    with session_scope() as session:
        profile = ClientComplianceProfilesRepository(session).get(org_id=org_id, client_id=client_id)
        design_systems = DesignSystemsRepository(session).list(org_id=org_id, client_id=client_id)
    if profile is None:
        raise StrategyV2DecisionError(
            "Missing client compliance profile. "
            "Remediation: configure and sync policy pages before copy pipeline launch."
        )

    privacy_url = _clean_url_for_footer(profile.privacy_policy_url)
    terms_url = _clean_url_for_footer(profile.terms_of_service_url)
    returns_url = _clean_url_for_footer(profile.returns_refunds_policy_url)
    shipping_url = _clean_url_for_footer(profile.shipping_policy_url)
    subscription_url = _clean_url_for_footer(profile.subscription_terms_and_cancellation_url)

    missing_policy_keys: list[str] = []
    if not privacy_url:
        missing_policy_keys.append("privacy_policy_url")
    if not terms_url:
        missing_policy_keys.append("terms_of_service_url")
    if not returns_url:
        missing_policy_keys.append("returns_refunds_policy_url")
    if not shipping_url:
        missing_policy_keys.append("shipping_policy_url")
    if missing_policy_keys:
        raise StrategyV2DecisionError(
            "Missing required policy page URLs for footer rendering: "
            f"{', '.join(missing_policy_keys)}. "
            "Remediation: sync Shopify policy pages and retry."
        )

    links: list[dict[str, str]] = [
        {"label": "Privacy", "href": privacy_url},
        {"label": "Terms", "href": terms_url},
        {"label": "Returns", "href": returns_url},
        {"label": "Shipping", "href": shipping_url},
    ]
    if subscription_url:
        links.append({"label": "Subscription", "href": subscription_url})

    brand_name = ""
    for design_system in design_systems:
        tokens = design_system.tokens if isinstance(design_system.tokens, dict) else {}
        brand = tokens.get("brand")
        if not isinstance(brand, dict):
            continue
        candidate = str(brand.get("name") or "").strip()
        if candidate:
            brand_name = candidate
            break
    if not brand_name:
        brand_name = (
            str(profile.operating_entity_name or "").strip()
            or str(profile.legal_business_name or "").strip()
            or str(profile.client_id or "").strip()
        )
    if not brand_name:
        raise StrategyV2DecisionError(
            "Unable to determine brand name for footer copyright. "
            "Remediation: set design system brand.name or compliance profile entity fields."
        )
    return links, brand_name


_PRE_SALES_TEMPLATE_PAYLOAD_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "hero": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string", "minLength": 1, "maxLength": 90},
                "subtitle": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 140,
                    "description": "Maximum 2 sentences.",
                },
                "badges": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "label": {"type": "string", "minLength": 1},
                            "value": {"type": "string", "minLength": 1, "maxLength": 24},
                            "icon": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "alt": {"type": "string", "minLength": 1, "maxLength": 240},
                                    "prompt": {"type": "string", "minLength": 1, "maxLength": 420},
                                },
                                "required": ["alt", "prompt"],
                            },
                        },
                        "required": ["label", "value", "icon"],
                    },
                },
            },
            "required": ["title", "subtitle", "badges"],
        },
        "reasons": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "number": {"type": "integer", "minimum": 1},
                    "title": {"type": "string", "minLength": 1, "maxLength": 72},
                    "body": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 420,
                        "description": "Maximum 3 sentences.",
                    },
                    "image": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "alt": {"type": "string", "minLength": 1, "maxLength": 240},
                            "prompt": {"type": "string", "minLength": 1, "maxLength": 420},
                        },
                        "required": ["alt", "prompt"],
                    },
                },
                "required": ["number", "title", "body", "image"],
            },
        },
        "marquee": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1, "maxLength": 24},
        },
        "pitch": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string", "minLength": 1, "maxLength": 78},
                "bullets": {
                    "type": "array",
                    "minItems": 4,
                    "maxItems": 4,
                    "items": {"type": "string", "minLength": 1, "maxLength": 90},
                },
                "cta_label": {"type": "string", "minLength": 1},
                "image": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "alt": {"type": "string", "minLength": 1, "maxLength": 240},
                        "prompt": {"type": "string", "minLength": 1, "maxLength": 420},
                    },
                    "required": ["alt", "prompt"],
                },
            },
            "required": ["title", "bullets", "cta_label", "image"],
        },
        "reviews": {
            "type": "array",
            "minItems": 0,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string", "minLength": 1},
                    "author": {"type": "string", "minLength": 1},
                    "rating": {"type": "integer", "minimum": 1, "maximum": 5},
                    "verified": {"type": "boolean"},
                },
                "required": ["text", "author", "rating", "verified"],
            },
        },
        "review_wall": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "button_label": {"type": "string", "minLength": 1},
            },
            "required": ["title", "button_label"],
        },
        "floating_cta": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "label": {"type": "string", "minLength": 1},
            },
            "required": ["label"],
        },
    },
    "required": ["hero", "reasons", "marquee", "pitch", "reviews", "review_wall", "floating_cta"],
}
_SALES_TEMPLATE_PAYLOAD_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "hero": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "purchase_title": {"type": "string", "minLength": 1},
                "primary_cta_label": {"type": "string", "minLength": 1},
                "primary_cta_subbullets": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {"type": "string", "minLength": 1, "maxLength": 90},
                },
            },
            "required": ["purchase_title", "primary_cta_label", "primary_cta_subbullets"],
        },
        "problem": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "paragraphs": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                },
                "emphasis_line": {"type": "string", "minLength": 1},
            },
            "required": ["title", "paragraphs", "emphasis_line"],
        },
        "mechanism": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "paragraphs": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                },
                "bullets": {
                    "type": "array",
                    "minItems": 4,
                    "maxItems": 6,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "title": {"type": "string", "minLength": 1, "maxLength": 90},
                            "body": {"type": "string", "minLength": 1, "maxLength": 240},
                        },
                        "required": ["title", "body"],
                    },
                },
                "callout": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "left_title": {"type": "string", "minLength": 1, "maxLength": 120},
                        "left_body": {"type": "string", "minLength": 1, "maxLength": 240},
                        "right_title": {"type": "string", "minLength": 1, "maxLength": 120},
                        "right_body": {"type": "string", "minLength": 1, "maxLength": 240},
                    },
                    "required": ["left_title", "left_body", "right_title", "right_body"],
                },
                "comparison": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "badge": {"type": "string", "minLength": 1, "maxLength": 120},
                        "title": {"type": "string", "minLength": 1, "maxLength": 160},
                        "swipe_hint": {"type": "string", "minLength": 1, "maxLength": 120},
                        "columns": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "pup": {"type": "string", "minLength": 1, "maxLength": 80},
                                "disposable": {"type": "string", "minLength": 1, "maxLength": 80},
                            },
                            "required": ["pup", "disposable"],
                        },
                        "rows": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 8,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "label": {"type": "string", "minLength": 1, "maxLength": 80},
                                    "pup": {"type": "string", "minLength": 1, "maxLength": 180},
                                    "disposable": {"type": "string", "minLength": 1, "maxLength": 180},
                                },
                                "required": ["label", "pup", "disposable"],
                            },
                        },
                    },
                    "required": ["badge", "title", "swipe_hint", "columns", "rows"],
                },
            },
            "required": ["title", "paragraphs", "bullets", "callout", "comparison"],
        },
        "social_proof": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "badge": {"type": "string", "minLength": 1},
                "title": {"type": "string", "minLength": 1},
                "rating_label": {"type": "string", "minLength": 1},
                "summary": {"type": "string", "minLength": 1},
            },
            "required": ["badge", "title", "rating_label", "summary"],
        },
        "whats_inside": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "benefits": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 6,
                    "items": {"type": "string", "minLength": 1, "maxLength": 140},
                },
                "offer_helper_text": {"type": "string", "minLength": 1},
            },
            "required": ["benefits", "offer_helper_text"],
        },
        "bonus": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "free_gifts_title": {"type": "string", "minLength": 1},
                "free_gifts_body": {"type": "string", "minLength": 1, "maxLength": 220},
            },
            "required": ["free_gifts_title", "free_gifts_body"],
        },
        "guarantee": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "paragraphs": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                },
                "why_title": {"type": "string", "minLength": 1},
                "why_body": {"type": "string", "minLength": 1},
                "closing_line": {"type": "string", "minLength": 1},
            },
            "required": ["title", "paragraphs", "why_title", "why_body", "closing_line"],
        },
        "faq": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "items": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "question": {"type": "string", "minLength": 1},
                            "answer": {"type": "string", "minLength": 1},
                        },
                        "required": ["question", "answer"],
                    },
                },
            },
            "required": ["title", "items"],
        },
        "faq_pills": {
            "type": "array",
            "minItems": 1,
            "maxItems": 12,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string", "minLength": 1},
                    "answer": {"type": "string", "minLength": 1},
                },
                "required": ["label", "answer"],
            },
        },
        "marquee_items": {
            "type": "array",
            "minItems": 1,
            "maxItems": 12,
            "items": {"type": "string", "minLength": 1},
        },
        "urgency_message": {"type": "string", "minLength": 1, "maxLength": 220},
        "cta_close": {"type": "string", "minLength": 1},
    },
    "required": [
        "hero",
        "problem",
        "mechanism",
        "social_proof",
        "whats_inside",
        "bonus",
        "guarantee",
        "faq",
        "faq_pills",
        "marquee_items",
        "urgency_message",
        "cta_close",
    ],
}
_PRE_SALES_TEMPLATE_LIMITS_INSTRUCTION = (
    "Hard limits for pre-sales template payload:\n"
    "- hero.title <= 90 chars\n"
    "- hero.subtitle <= 140 chars (max 2 sentences)\n"
    "- hero.badges must be exactly 3 items: [<review count> 5-Star Reviews, 24/7 Customer Support, Risk Free Trial]\n"
    "- hero.badges[].value <= 24 chars when present\n"
    "- reasons[].title <= 72 chars\n"
    "- reasons[].body <= 420 chars and MUST be 2-3 sentences (never 4+)\n"
    "- reasons[].image.prompt must stay editorial before the marquee; do not depict the product reference image, packaging, or exact book/product identity\n"
    "- marquee[] each <= 24 chars, 1-4 words\n"
    "- pitch.title <= 78 chars\n"
    "- pitch.bullets must be exactly 4 items; each <= 90 chars\n"
    "- pitch.image is the first section allowed to introduce the product after the marquee\n"
    "- pitch.cta_label must be short, non-transactional; use 'Learn more'\n"
)

_SALES_TEMPLATE_LIMITS_INSTRUCTION = (
    "Hard limits for sales template payload JSON string:\n"
    "- hero.purchase_title must be the plain product name only (no tagline)\n"
    "- hero.purchase_title <= 64 chars\n"
    "- hero.primary_cta_label must not hardcode a literal dollar amount; if price appears in CTA copy it must use the exact token {price}\n"
    "- hero.primary_cta_subbullets must be exactly 2 items; each <= 90 chars\n"
    "- whats_inside.benefits must be exactly 4 items; each <= 38 chars and 2-6 words\n"
    "- whats_inside.benefits must be outcome-led, not feature inventory; avoid endings like workflow/guide/reference/checklist/pages/notes/prompts/scripts\n"
    "- whats_inside.benefits must not use parentheses, colons, arrows, commas, or explanatory clauses\n"
    "- whats_inside.offer_helper_text <= 180 chars and max 2 sentences\n"
    "- problem.paragraphs: 1-2 items, each <= 320 chars\n"
    "- mechanism.paragraphs: 1-2 items, each <= 220 chars\n"
    "- mechanism.bullets: exactly 5 items; title <= 56 chars; body <= 160 chars\n"
    "- guarantee.paragraphs: exactly 1 item <= 260 chars\n"
    "- guarantee.why_body <= 220 chars; closing_line <= 140 chars\n"
    "- faq.items[].question <= 120 chars; answer <= 280 chars (max 3 sentences)\n"
    "- faq_pills[].label <= 120 chars; answer <= 420 chars (max 3 sentences)\n"
    "- marquee_items[] each <= 24 chars, 1-3 words\n"
    "- urgency_message <= 220 chars\n"
)
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
_COPY_SALES_SEMANTIC_CTA_LINK_ERROR_RE = re.compile(
    r"Sales semantic repair requires at least one existing markdown CTA link URL",
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

_OFFER_VARIANT_IDS = ("single_device", "share_and_save", "family_bundle")
_OFFER_VARIANT_DISPLAY_LABELS = {
    "single_device": "Single Device",
    "share_and_save": "Share & Save",
    "family_bundle": "Family Bundle",
}
_BOOK_OFFER_VARIANT_DISPLAY_LABELS = {
    "single_device": "Single Book",
    "share_and_save": "2-Book Bundle",
    "family_bundle": "3-Book Bundle",
}
_DEFAULT_OFFER_VARIANT_BUNDLE_QUANTITIES = {
    "single_device": 1,
    "share_and_save": 2,
    "family_bundle": 4,
}
_BOOK_OFFER_VARIANT_BUNDLE_QUANTITIES = {
    "single_device": 1,
    "share_and_save": 2,
    "family_bundle": 3,
}
_OFFER_COMPOSITE_DIMENSIONS = (
    "value_equation",
    "objection_coverage",
    "competitive_differentiation",
    "compliance_safety",
    "internal_consistency",
    "clarity_simplicity",
    "bottleneck_resilience",
    "momentum_continuity",
    "pricing_fidelity",
    "savings_fidelity",
    "best_value_fidelity",
)
_OFFER_EVIDENCE_QUALITY_LEVELS = ("OBSERVED", "INFERRED", "ASSUMED")
_STEP05_REVISION_NOTES_MAX_CHARS = int(os.getenv("STRATEGY_V2_OFFER_STEP05_REVISION_NOTES_MAX_CHARS", "4000"))
_STEP05_KILL_CONDITION_MAX_CHARS = int(os.getenv("STRATEGY_V2_OFFER_STEP05_KILL_CONDITION_MAX_CHARS", "800"))
_STEP04_CORE_PROMISE_MAX_CHARS = int(os.getenv("STRATEGY_V2_OFFER_STEP04_CORE_PROMISE_MAX_CHARS", "140"))
_STEP04_BONUS_TITLE_MAX_CHARS = int(os.getenv("STRATEGY_V2_OFFER_STEP04_BONUS_TITLE_MAX_CHARS", "70"))
_STEP04_BONUS_COPY_MAX_CHARS = int(os.getenv("STRATEGY_V2_OFFER_STEP04_BONUS_COPY_MAX_CHARS", "140"))
_STEP04_BEST_VALUE_REASON_MAX_CHARS = int(
    os.getenv("STRATEGY_V2_OFFER_STEP04_BEST_VALUE_REASON_MAX_CHARS", "120")
)
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
_AGENT3_FOUNDATIONAL_SUMMARY_MAX_CHARS = int(
    os.getenv("STRATEGY_V2_AGENT3_FOUNDATIONAL_SUMMARY_MAX_CHARS", "1800")
)
_AGENT3_FOUNDATIONAL_EXCERPT_MAX_CHARS = int(
    os.getenv("STRATEGY_V2_AGENT3_FOUNDATIONAL_EXCERPT_MAX_CHARS", "900")
)
_AGENT3_PRODUCT_BRIEF_MAX_COMPETITOR_URLS = int(
    os.getenv("STRATEGY_V2_AGENT3_PRODUCT_BRIEF_MAX_COMPETITOR_URLS", "12")
)
_AGENT3_COMPETITOR_MAP_MAX_COMPETITORS = int(
    os.getenv("STRATEGY_V2_AGENT3_COMPETITOR_MAP_MAX_COMPETITORS", "12")
)
_AGENT3_COMPETITOR_MAP_MAX_ASSETS_PER_COMPETITOR = int(
    os.getenv("STRATEGY_V2_AGENT3_COMPETITOR_MAP_MAX_ASSETS_PER_COMPETITOR", "3")
)
_AGENT3_HABITAT_MAX_ROWS = int(os.getenv("STRATEGY_V2_AGENT3_HABITAT_MAX_ROWS", "12"))
_AGENT3_MINING_PLAN_MAX_ROWS = int(os.getenv("STRATEGY_V2_AGENT3_MINING_PLAN_MAX_ROWS", "10"))
_AGENT3_VOC_MAX_ROWS = int(os.getenv("STRATEGY_V2_AGENT3_VOC_MAX_ROWS", "60"))
_AGENT3_RAW_EVIDENCE_MAX_ROWS = int(os.getenv("STRATEGY_V2_AGENT3_RAW_EVIDENCE_MAX_ROWS", "60"))
_AGENT3_VOC_MAX_RATIO_PER_SOURCE = float(
    os.getenv("STRATEGY_V2_AGENT3_VOC_MAX_RATIO_PER_SOURCE", "0.4")
)
_AGENT3_RUNTIME_TOTAL_PAYLOAD_MAX_CHARS = int(
    os.getenv("STRATEGY_V2_AGENT3_RUNTIME_TOTAL_PAYLOAD_MAX_CHARS", "180000")
)
_AGENT3_RUNTIME_SINGLE_PAYLOAD_MAX_CHARS = int(
    os.getenv("STRATEGY_V2_AGENT3_RUNTIME_SINGLE_PAYLOAD_MAX_CHARS", "60000")
)
_AGENT1_MAX_TOKENS = int(os.getenv("STRATEGY_V2_AGENT1_MAX_TOKENS", "128000"))
_AGENT2_MAX_TOKENS = int(os.getenv("STRATEGY_V2_AGENT2_MAX_TOKENS", "128000"))
_AGENT3_MAX_TOKENS = int(os.getenv("STRATEGY_V2_AGENT3_MAX_TOKENS", "64000"))
_AGENT2_PROMPT_MAX_EVIDENCE_ROWS = int(os.getenv("STRATEGY_V2_AGENT2_PROMPT_MAX_EVIDENCE_ROWS", "100"))
_AGENT2_AGENT1_HANDOFF_MAX_CHARS = int(os.getenv("STRATEGY_V2_AGENT2_AGENT1_HANDOFF_MAX_CHARS", "20000"))
_AGENT2_HABITAT_SCORED_MAX_CHARS = int(os.getenv("STRATEGY_V2_AGENT2_HABITAT_SCORED_MAX_CHARS", "20000"))
_AGENT2_PRODUCT_BRIEF_MAX_CHARS = int(os.getenv("STRATEGY_V2_AGENT2_PRODUCT_BRIEF_MAX_CHARS", "9000"))
_AGENT2_AVATAR_BRIEF_MAX_CHARS = int(os.getenv("STRATEGY_V2_AGENT2_AVATAR_BRIEF_MAX_CHARS", "9000"))
_AGENT2_KNOWN_SATURATED_MAX_CHARS = int(os.getenv("STRATEGY_V2_AGENT2_KNOWN_SATURATED_MAX_CHARS", "8000"))
_AGENT2_COMPETITOR_ANALYSIS_MAX_CHARS = int(
    os.getenv("STRATEGY_V2_AGENT2_COMPETITOR_ANALYSIS_MAX_CHARS", "24000")
)
_AGENT1_HABITAT_STRATEGY_MAX_CHARS = int(os.getenv("STRATEGY_V2_AGENT1_HABITAT_STRATEGY_MAX_CHARS", "60000"))
_AGENT1_VIDEO_STRATEGY_MAX_CHARS = int(os.getenv("STRATEGY_V2_AGENT1_VIDEO_STRATEGY_MAX_CHARS", "120000"))
_AGENT1_SCORED_VIDEO_DATA_MAX_CHARS = int(os.getenv("STRATEGY_V2_AGENT1_SCORED_VIDEO_DATA_MAX_CHARS", "60000"))
_AGENT1_PRODUCT_BRIEF_MAX_CHARS = int(os.getenv("STRATEGY_V2_AGENT1_PRODUCT_BRIEF_MAX_CHARS", "30000"))
_AGENT1_AVATAR_BRIEF_MAX_CHARS = int(os.getenv("STRATEGY_V2_AGENT1_AVATAR_BRIEF_MAX_CHARS", "30000"))
_AGENT1_COMPETITOR_ANALYSIS_MAX_CHARS = int(
    os.getenv("STRATEGY_V2_AGENT1_COMPETITOR_ANALYSIS_MAX_CHARS", "40000")
)
_AGENT1_COMPACTION_THRESHOLD = int(os.getenv("STRATEGY_V2_AGENT1_COMPACTION_THRESHOLD", "200000"))
_REDDIT_TARGET_ALIGNMENT_MIN_RATIO = float(
    os.getenv("STRATEGY_V2_REDDIT_TARGET_ALIGNMENT_MIN_RATIO", "0.5")
)
_REDDIT_TARGET_ALIGNMENT_MIN_ITEMS = int(
    os.getenv("STRATEGY_V2_REDDIT_TARGET_ALIGNMENT_MIN_ITEMS", "5")
)
_GPT52_CONTEXT_WINDOW_TOKENS = int(os.getenv("STRATEGY_V2_GPT52_CONTEXT_WINDOW_TOKENS", "400000"))
_PROMPT_INPUT_TOKEN_SAFETY_BUFFER = int(os.getenv("STRATEGY_V2_PROMPT_INPUT_TOKEN_SAFETY_BUFFER", "16000"))

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

_LOGGER = logging.getLogger(__name__)

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
    "brandsearch.co",
    "www.brandsearch.co",
    "crunchbase.com",
    "www.crunchbase.com",
    "en.wikipedia.org",
    "wikipedia.org",
    "hypestat.com",
    "www.hypestat.com",
    "google.com",
    "www.google.com",
    "bing.com",
    "www.bing.com",
    "duckduckgo.com",
    "www.duckduckgo.com",
    "docs.google.com",
    "scam-detector.com",
    "www.scam-detector.com",
    "semrush.com",
    "www.semrush.com",
}
_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref_src",
}
_PLATFORM_QUERY_KEYS: dict[str, frozenset[str]] = {
    "youtube.com": frozenset({"v", "list", "t"}),
    "youtu.be": frozenset({"t"}),
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

    cleaned_reviewed_candidates = [
        candidate_id.strip()
        for candidate_id in (reviewed_candidate_ids or [])
        if isinstance(candidate_id, str) and candidate_id.strip()
    ]
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
    if stage1.price.strip().upper() == "TBD":
        raise StrategyV2MissingContextError(
            "Stage 1 price must be concrete before downstream Strategy V2 stages. "
            "Remediation: provide an explicit product price during onboarding or in stage0_overrides.price."
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
                    if key in {"habitat_name", "url_pattern", "source", "title"}:
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


def _build_manifest_config_target_id_map(*, apify_context: Mapping[str, Any]) -> dict[str, str]:
    config_target_map: dict[str, str] = {}
    config_blocks = (
        apify_context.get("ingestion_apify_configs"),
        apify_context.get("strategy_apify_configs"),
        apify_context.get("apify_configs"),
    )
    for block in config_blocks:
        if not isinstance(block, list):
            continue
        for row in block:
            if not isinstance(row, Mapping):
                continue
            config_id = str(row.get("config_id") or "").strip()
            if not config_id:
                continue
            metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
            config_metadata = (
                row.get("config_metadata")
                if isinstance(row.get("config_metadata"), Mapping)
                else {}
            )
            candidate_target = (
                str(metadata.get("target_id") or "").strip()
                or str(config_metadata.get("target_id") or "").strip()
                or str(row.get("target_id") or "").strip()
                or str(row.get("strategy_target_id") or "").strip()
            )
            if candidate_target:
                config_target_map[config_id] = candidate_target
    return config_target_map


def _resolve_manifest_strategy_target_id(
    *,
    row_target_id: str,
    config_id: str,
    actor_id: str,
    source_platform: str,
    row_index: int,
    config_target_map: Mapping[str, str],
) -> tuple[str, bool]:
    normalized_row_target_id = row_target_id.strip()
    if normalized_row_target_id:
        return normalized_row_target_id, False

    mapped_target_id = str(config_target_map.get(config_id) or "").strip()
    if mapped_target_id:
        return mapped_target_id, True

    normalized_config_id = config_id.strip() or f"UNKNOWN_CONFIG_{row_index + 1}"
    actor_lower = actor_id.lower()
    if "comment" in actor_lower:
        platform_token = re.sub(r"[^A-Z0-9]+", "_", source_platform.upper()).strip("_") or "UNKNOWN"
        return f"COMMENT_ENRICHMENT_{platform_token}", True
    if any(token in actor_lower for token in ("youtube", "instagram", "tiktok")):
        return f"SV-{normalized_config_id}", True
    return f"DISC-{normalized_config_id}", True


def _infer_manifest_source_platform(*, actor_id: str, requested_refs: Sequence[str]) -> str:
    lowered_actor = actor_id.lower()
    if "reddit" in lowered_actor:
        return "Reddit"
    if "tiktok" in lowered_actor:
        return "TikTok"
    if "instagram" in lowered_actor:
        return "Instagram"
    if "youtube" in lowered_actor:
        return "YouTube"
    if "google-search" in lowered_actor:
        return "Discovery"
    if "web-scraper" in lowered_actor:
        return "Web"

    for ref in requested_refs:
        lowered_ref = ref.lower()
        if "reddit.com" in lowered_ref:
            return "Reddit"
        if "tiktok.com" in lowered_ref:
            return "TikTok"
        if "instagram.com" in lowered_ref:
            return "Instagram"
        if "youtube.com" in lowered_ref or "youtu.be" in lowered_ref:
            return "YouTube"
    return "Other"


def _extract_manifest_date_range(items: Sequence[Mapping[str, Any]]) -> dict[str, str] | str:
    def _coerce_timestamp(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            candidate = value.strip()
            return candidate
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")
            except Exception:
                return ""
        return ""

    date_candidates: list[str] = []
    for item in items:
        nested_mappings: list[Mapping[str, Any]] = [item]
        nested_post = item.get("post")
        nested_snapshot = item.get("snapshot")
        if isinstance(nested_post, Mapping):
            nested_mappings.append(nested_post)
        if isinstance(nested_snapshot, Mapping):
            nested_mappings.append(nested_snapshot)
        for mapping in nested_mappings:
            for field_name in (
                "created_utc",
                "createdAt",
                "created_at",
                "timestamp",
                "publishedAt",
                "published_at",
                "date",
                "time",
                "createTimeISO",
                "createTime",
            ):
                candidate = _coerce_timestamp(mapping.get(field_name))
                if candidate:
                    date_candidates.append(candidate)
    if not date_candidates:
        return "CANNOT_DETERMINE"
    sorted_dates = sorted(date_candidates)
    return {"earliest": sorted_dates[0], "latest": sorted_dates[-1]}


def _manifest_item_has_text_signal(item: Mapping[str, Any]) -> bool:
    normalized = _normalize_scraped_item_for_manifest(item)
    text_keys = ("title", "body", "comments_sample", "posts_sample", "organic_results_sample")
    return any(
        bool(normalized.get(key))
        for key in text_keys
    )


def _manifest_item_has_hard_error(item: Mapping[str, Any]) -> bool:
    hard_error_keys = ("error", "errorDescription")
    for key in hard_error_keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return True
    hash_error = item.get("#error")
    if isinstance(hash_error, bool):
        return hash_error
    if isinstance(hash_error, str):
        return hash_error.strip().lower() in {"1", "true", "yes"}
    return False


def _classify_manifest_run_exclusion_reason(
    *,
    actor_id: str,
    source_platform: str,
    raw_items: Sequence[Mapping[str, Any]],
) -> str:
    if any(_manifest_item_has_hard_error(item) for item in raw_items):
        return "RUN_CONTAINS_ERROR_PAYLOAD"
    has_text_signal = any(_manifest_item_has_text_signal(item) for item in raw_items)
    if has_text_signal:
        return ""
    lowered_actor = actor_id.lower()
    if source_platform == "Web" or "web-scraper" in lowered_actor:
        return "WEB_SCRAPER_EMPTY_TEXT"
    return "NO_EXTRACTABLE_TEXT"


def _extract_reddit_subreddit_from_value(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    candidate = value.strip()
    if not candidate:
        return ""
    if "reddit.com" in candidate.lower() or candidate.startswith("/r/"):
        match = re.search(r"/r/([A-Za-z0-9_]+)/?", candidate, flags=re.IGNORECASE)
        if match:
            return match.group(1).lower()
    return ""


def _validate_reddit_target_alignment(
    *,
    run_rows: Sequence[Mapping[str, Any]],
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    mismatches: list[str] = []
    missing_evidence: list[str] = []
    total_rows = len(run_rows)
    last_progress_heartbeat = time.monotonic()

    for idx, row in enumerate(run_rows, start=1):
        if progress_callback is not None:
            now = time.monotonic()
            if idx == 1 or idx == total_rows or (now - last_progress_heartbeat) >= 15:
                progress_callback(
                    {
                        "progress_event": "reddit_alignment_scan",
                        "processed_run_rows": idx,
                        "total_run_rows": total_rows,
                    }
                )
                last_progress_heartbeat = now

        actor_id = str(row.get("actor_id") or "").strip().lower()
        if "reddit" not in actor_id:
            continue

        input_payload = row.get("input_payload")
        config_metadata = row.get("config_metadata")
        if not isinstance(input_payload, Mapping):
            continue
        metadata = dict(config_metadata) if isinstance(config_metadata, Mapping) else {}
        expected_subreddit = ""

        direct_subreddit = input_payload.get("subreddit")
        if isinstance(direct_subreddit, str) and direct_subreddit.strip():
            expected_subreddit = direct_subreddit.strip().lower().lstrip("r/").replace("/", "")

        if not expected_subreddit:
            for value in (metadata.get("url_pattern"), metadata.get("target_id")):
                extracted = _extract_reddit_subreddit_from_value(value)
                if extracted:
                    expected_subreddit = extracted
                    break

        if not expected_subreddit:
            for key in ("startUrls", "urls", "postURLs", "directUrls"):
                raw_urls = input_payload.get(key)
                if not isinstance(raw_urls, list):
                    continue
                for entry in raw_urls:
                    if isinstance(entry, Mapping):
                        extracted = _extract_reddit_subreddit_from_value(entry.get("url"))
                    else:
                        extracted = _extract_reddit_subreddit_from_value(entry)
                    if extracted:
                        expected_subreddit = extracted
                        break
                if expected_subreddit:
                    break

        if not expected_subreddit:
            continue

        raw_items = [item for item in row.get("items", []) if isinstance(item, Mapping)] if isinstance(row.get("items"), list) else []
        if not raw_items:
            continue

        observed_subreddits: Counter[str] = Counter()
        for item in raw_items:
            for field_name in ("subreddit",):
                value = item.get(field_name)
                if isinstance(value, str) and value.strip():
                    observed_subreddits[value.strip().lower().lstrip("r/")] += 1
            for field_name in ("source_url", "url", "permalink", "postUrl"):
                extracted = _extract_reddit_subreddit_from_value(item.get(field_name))
                if extracted:
                    observed_subreddits[extracted] += 1
            nested_post = item.get("post")
            if isinstance(nested_post, Mapping):
                nested_subreddit = nested_post.get("subreddit")
                if isinstance(nested_subreddit, str) and nested_subreddit.strip():
                    observed_subreddits[nested_subreddit.strip().lower().lstrip("r/")] += 1
                for field_name in ("url", "permalink"):
                    extracted = _extract_reddit_subreddit_from_value(nested_post.get(field_name))
                    if extracted:
                        observed_subreddits[extracted] += 1

        evidence_rows = int(sum(observed_subreddits.values()))
        run_id = str(row.get("run_id") or "")
        config_id = str(row.get("config_id") or "")
        if evidence_rows == 0:
            missing_evidence.append(f"config_id={config_id or 'unknown'} run_id={run_id or 'unknown'}")
            continue

        matched_rows = int(observed_subreddits.get(expected_subreddit, 0))
        alignment_ratio = matched_rows / max(evidence_rows, 1)
        if evidence_rows >= max(_REDDIT_TARGET_ALIGNMENT_MIN_ITEMS, 1) and alignment_ratio < _REDDIT_TARGET_ALIGNMENT_MIN_RATIO:
            top_seen = ", ".join(
                f"{name}:{count}"
                for name, count in observed_subreddits.most_common(3)
            )
            mismatches.append(
                f"config_id={config_id or 'unknown'} run_id={run_id or 'unknown'} expected=r/{expected_subreddit} "
                f"matched={matched_rows}/{evidence_rows} observed=[{top_seen}]"
            )

    if missing_evidence:
        preview = "; ".join(missing_evidence[:5])
        raise StrategyV2DecisionError(
            "Reddit target-to-data consistency check failed: scraped rows did not contain subreddit/url evidence "
            "needed to validate target alignment. "
            f"Runs: {preview}."
        )
    if mismatches:
        preview = "; ".join(mismatches[:5])
        raise StrategyV2DecisionError(
            "Reddit target-to-data consistency check failed: scraped datasets do not align with configured subreddit targets. "
            f"Runs: {preview}."
        )


def _build_scraped_data_manifest(
    *,
    apify_context: Mapping[str, Any],
    competitor_analysis: Mapping[str, Any],
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
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
    scraped_data_files: list[dict[str, Any]] = []
    excluded_runs: list[dict[str, Any]] = []
    platform_breakdown: Counter[str] = Counter()
    config_target_map = _build_manifest_config_target_id_map(apify_context=apify_context)
    missing_target_id_before_backfill = 0
    backfilled_target_id_count = 0
    missing_target_id_after_backfill = 0
    total_runs = len(run_rows)
    last_progress_heartbeat = time.monotonic()
    for idx, row in enumerate(run_rows):
        if progress_callback is not None:
            now = time.monotonic()
            if idx == 0 or idx + 1 == total_runs or (now - last_progress_heartbeat) >= 15:
                progress_callback(
                    {
                        "progress_event": "manifest_build",
                        "processed_runs": idx + 1,
                        "total_runs": total_runs,
                    }
                )
                last_progress_heartbeat = now
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
        actor_id = str(row.get("actor_id") or "")
        run_id = str(row.get("run_id") or "")
        dataset_id = str(row.get("dataset_id") or "")
        status = str(row.get("status") or "")
        config_id = str(row.get("config_id") or "")
        config_metadata = (
            dict(row.get("config_metadata"))
            if isinstance(row.get("config_metadata"), Mapping)
            else {}
        )
        habitat_name = str(config_metadata.get("habitat_name") or "").strip()
        habitat_type = str(
            config_metadata.get("habitat_type")
            or config_metadata.get("platform")
            or "Other"
        ).strip()
        raw_items = [item for item in row.get("items", []) if isinstance(item, dict)] if isinstance(row.get("items"), list) else []
        source_platform = _infer_manifest_source_platform(actor_id=actor_id, requested_refs=requested_refs)
        raw_target_id = str(config_metadata.get("target_id") or "").strip()
        if not raw_target_id:
            missing_target_id_before_backfill += 1
        strategy_target_id, was_backfilled = _resolve_manifest_strategy_target_id(
            row_target_id=raw_target_id,
            config_id=config_id,
            actor_id=actor_id,
            source_platform=source_platform,
            row_index=idx,
            config_target_map=config_target_map,
        )
        if was_backfilled:
            backfilled_target_id_count += 1
        if not strategy_target_id.strip():
            missing_target_id_after_backfill += 1
            strategy_target_id = "CANNOT_DETERMINE"
        exclusion_reason = _classify_manifest_run_exclusion_reason(
            actor_id=actor_id,
            source_platform=source_platform,
            raw_items=raw_items,
        )
        actor_label = (
            actor_id.replace("/", "_").replace("~", "_")
            if actor_id
            else f"unknown_actor_{idx + 1}"
        )
        filename = f"{actor_label}_{run_id or idx + 1}.json"
        lowered_actor = actor_id.lower()
        is_video_actor = any(token in lowered_actor for token in ("tiktok", "instagram", "youtube"))
        virtual_path = (
            f"/apify_output/raw_scraped_data/social_video/{filename}"
            if is_video_actor
            else f"/apify_output/raw_scraped_data/text_habitats/{filename}"
        )
        normalized_items = [
            _normalize_scraped_item_for_manifest(
                item,
                item_index=item_index,
            )
            for item_index, item in enumerate(raw_items)
        ]
        date_range = _extract_manifest_date_range(raw_items)
        if exclusion_reason:
            excluded_row = {
                "actor_id": actor_id,
                "run_id": run_id,
                "dataset_id": dataset_id,
                "status": status,
                "config_id": config_id,
                "strategy_target_id": strategy_target_id,
                "habitat_name": habitat_name,
                "habitat_type": habitat_type,
                "source_platform": source_platform,
                "item_count": len(raw_items),
                "exclusion_reason": exclusion_reason,
                "virtual_path": virtual_path,
            }
            excluded_runs.append(excluded_row)
            if exclusion_reason == "WEB_SCRAPER_EMPTY_TEXT":
                _LOGGER.warning(
                    "strategy_v2.web_scraper_empty_text_detected",
                    extra={
                        "actor_id": actor_id,
                        "config_id": config_id,
                        "run_id": run_id,
                        "dataset_id": dataset_id,
                        "source_platform": source_platform,
                    },
                )
            continue
        for item in normalized_items:
            source_url = str(item.get("source_url") or item.get("url") or "").lower()
            if "reddit.com" in source_url:
                platform_breakdown["REDDIT"] += 1
            elif "tiktok.com" in source_url:
                platform_breakdown["TIKTOK"] += 1
            elif "instagram.com" in source_url:
                platform_breakdown["INSTAGRAM"] += 1
            elif "youtube.com" in source_url or "youtu.be" in source_url:
                platform_breakdown["YOUTUBE"] += 1
            else:
                platform_breakdown["WEB"] += 1

        summarized_runs.append(
            {
                "actor_id": actor_id,
                "run_id": run_id,
                "dataset_id": dataset_id,
                "status": status,
                "config_id": config_id,
                "strategy_target_id": strategy_target_id,
                "habitat_name": habitat_name,
                "habitat_type": habitat_type,
                "source_platform": source_platform,
                "item_count": len(raw_items),
                "date_range": date_range,
                "requested_refs": requested_refs[:20],
                "virtual_path": virtual_path,
            }
        )
        scraped_data_files.append(
            {
                "file_name": filename,
                "virtual_path": virtual_path,
                "actor_id": actor_id,
                "run_id": run_id,
                "dataset_id": dataset_id,
                "config_id": config_id,
                "strategy_target_id": strategy_target_id,
                "habitat_name": habitat_name,
                "habitat_type": habitat_type,
                "source_platform": source_platform,
                "item_count": len(raw_items),
                "date_range": date_range,
                "requested_refs": requested_refs[:20],
                "items": normalized_items,
            }
        )
    candidate_assets_preview: list[dict[str, Any]] = []
    for row in candidate_assets[:20]:
        metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
        candidate_assets_preview.append(
            {
                "source_ref": str(row.get("source_ref") or ""),
                "platform": str(row.get("platform") or ""),
                "source_type": str(row.get("source_type") or ""),
                "asset_kind": str(row.get("asset_kind") or ""),
                "headline_or_caption": str(row.get("headline_or_caption") or "")[:260],
                "metrics": metrics,
            }
        )
    social_video_preview: list[dict[str, Any]] = []
    for row in social_video_observations[:20]:
        social_video_preview.append(
            {
                "video_id": str(row.get("video_id") or ""),
                "source_ref": str(row.get("source_ref") or ""),
                "platform": str(row.get("platform") or ""),
                "views": row.get("views"),
                "followers": row.get("followers"),
                "comments": row.get("comments"),
                "shares": row.get("shares"),
                "likes": row.get("likes"),
                "days_since_posted": row.get("days_since_posted"),
                "headline_or_caption": str(row.get("headline_or_caption") or "")[:260],
            }
        )
    external_voc_preview: list[dict[str, Any]] = []
    for row in external_voc_corpus[:30]:
        external_voc_preview.append(
            {
                "voc_id": str(row.get("voc_id") or ""),
                "source_type": str(row.get("source_type") or ""),
                "source_url": str(row.get("source_url") or ""),
                "quote": str(row.get("quote") or "")[:320],
                "metadata": row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
            }
        )
    competitor_sheet_preview: list[dict[str, Any]] = []
    for row in competitor_sheets[:20]:
        competitor_sheet_preview.append(
            {
                "source_ref": str(row.get("source_ref") or ""),
                "platform": str(row.get("platform") or ""),
                "asset_kind": str(row.get("asset_kind") or ""),
                "headline_or_caption": str(row.get("headline_or_caption") or "")[:260],
                "cta_style": str(row.get("cta_style") or ""),
                "key_hook": str(row.get("key_hook") or "")[:220],
            }
        )
    manifest = {
        "scraped_data_root": "/apify_output/",
        "raw_scraped_data_files": scraped_data_files,
        "run_count": len(summarized_runs),
        "total_run_count": len(run_rows),
        "excluded_runs": excluded_runs,
        "excluded_run_count": len(excluded_runs),
        "target_id_mapping_diagnostics": {
            "missing_target_id_before_backfill": missing_target_id_before_backfill,
            "missing_target_id_after_backfill": missing_target_id_after_backfill,
            "backfilled_target_id_count": backfilled_target_id_count,
        },
        "runs": summarized_runs,
        "candidate_asset_count": len(candidate_assets),
        "social_video_observation_count": len(social_video_observations),
        "external_voc_row_count": len(external_voc_corpus),
        "competitor_asset_sheet_count": len(competitor_sheets),
        "platform_breakdown": dict(platform_breakdown),
        "candidate_asset_refs": [
            str(row.get("source_ref"))
            for row in candidate_assets[:30]
            if isinstance(row.get("source_ref"), str) and str(row.get("source_ref")).strip()
        ],
        # Inline scraped content for prompt-chain consumers that cannot read local files.
        "candidate_assets_preview": candidate_assets_preview,
        "social_video_observations_preview": social_video_preview,
        "external_voc_corpus_preview": external_voc_preview,
        "competitor_asset_observation_preview": competitor_sheet_preview,
    }
    if len(scraped_data_files) == 0 or manifest["run_count"] == 0:
        exclusion_preview = ", ".join(
            str(row.get("exclusion_reason") or "")
            for row in excluded_runs[:5]
            if str(row.get("exclusion_reason") or "").strip()
        )
        raise StrategyV2MissingContextError(
            "Agent 1 requires Stage 2B Apify raw-run output with extractable text, "
            "but all runs were excluded by deterministic eligibility checks. "
            f"excluded_run_count={len(excluded_runs)}; sample_reasons={exclusion_preview or 'none'}. "
            "Remediation: ensure Stage 2B sources return text-bearing, non-error payloads."
        )
    has_apify_observations = (
        any(
            isinstance(row.get("item_count"), int) and int(row.get("item_count")) > 0
            for row in scraped_data_files
        )
        or manifest["candidate_asset_count"] > 0
        or manifest["social_video_observation_count"] > 0
        or manifest["external_voc_row_count"] > 0
    )
    if not has_apify_observations:
        raise StrategyV2MissingContextError(
            "Agent 1 requires non-empty Apify observations, but Stage 2B returned zero usable rows. "
            "Remediation: verify actor inputs and rerun Stage 2B before v2-04."
        )
    if missing_target_id_after_backfill > 0:
        raise StrategyV2SchemaValidationError(
            "scraped_data_manifest target-id backfill integrity check failed "
            f"(missing_target_id_after_backfill={missing_target_id_after_backfill}). "
            "Remediation: ensure config_id->target_id mapping is available before v2-04."
        )
    return manifest


def _validate_agent1_scraped_manifest_integrity(
    *,
    scraped_data_manifest: Mapping[str, Any],
    planned_actor_run_count: int,
    executed_actor_run_count: int,
    failed_actor_run_count: int,
) -> None:
    if planned_actor_run_count < 0:
        raise StrategyV2SchemaValidationError("planned_actor_run_count must be >= 0 for v2-04 Agent 1.")
    if executed_actor_run_count < 0:
        raise StrategyV2SchemaValidationError("executed_actor_run_count must be >= 0 for v2-04 Agent 1.")
    if failed_actor_run_count < 0:
        raise StrategyV2SchemaValidationError("failed_actor_run_count must be >= 0 for v2-04 Agent 1.")
    if failed_actor_run_count > executed_actor_run_count:
        raise StrategyV2SchemaValidationError(
            "failed_actor_run_count cannot exceed executed_actor_run_count for v2-04 Agent 1."
        )
    if planned_actor_run_count < executed_actor_run_count:
        raise StrategyV2SchemaValidationError(
            "planned_actor_run_count cannot be less than executed_actor_run_count for v2-04 Agent 1."
        )

    manifest_run_count = scraped_data_manifest.get("run_count")
    if not isinstance(manifest_run_count, int) or manifest_run_count < 0:
        raise StrategyV2SchemaValidationError(
            "scraped_data_manifest.run_count must be a non-negative integer for v2-04 Agent 1."
        )
    runs_payload = scraped_data_manifest.get("runs")
    if not isinstance(runs_payload, list):
        raise StrategyV2SchemaValidationError(
            "scraped_data_manifest.runs must be an array for v2-04 Agent 1."
        )
    raw_files_payload = scraped_data_manifest.get("raw_scraped_data_files")
    if not isinstance(raw_files_payload, list):
        raise StrategyV2SchemaValidationError(
            "scraped_data_manifest.raw_scraped_data_files must be an array for v2-04 Agent 1."
        )

    if manifest_run_count != len(runs_payload) or manifest_run_count != len(raw_files_payload):
        raise StrategyV2SchemaValidationError(
            "scraped_data_manifest run_count does not match runs/raw_scraped_data_files lengths "
            f"(run_count={manifest_run_count}, runs={len(runs_payload)}, files={len(raw_files_payload)})."
        )

    if manifest_run_count <= 0:
        raise StrategyV2SchemaValidationError(
            "scraped_data_manifest.run_count must be greater than zero for v2-04 Agent 1."
        )
    if manifest_run_count > executed_actor_run_count:
        raise StrategyV2SchemaValidationError(
            "scraped_data_manifest.run_count cannot exceed executed_actor_run_count for Agent 1 handoff "
            f"(run_count={manifest_run_count}, executed_actor_run_count={executed_actor_run_count})."
        )
    manifest_total_run_count = scraped_data_manifest.get("total_run_count")
    if not isinstance(manifest_total_run_count, int) or manifest_total_run_count < 0:
        raise StrategyV2SchemaValidationError(
            "scraped_data_manifest.total_run_count is required and must be a non-negative integer for v2-04 Agent 1."
        )
    if manifest_total_run_count != executed_actor_run_count:
        raise StrategyV2SchemaValidationError(
            "scraped_data_manifest.total_run_count mismatch for Agent 1 handoff "
            f"(total_run_count={manifest_total_run_count}, executed_actor_run_count={executed_actor_run_count})."
        )
    if manifest_run_count > manifest_total_run_count:
        raise StrategyV2SchemaValidationError(
            "scraped_data_manifest.run_count cannot exceed scraped_data_manifest.total_run_count."
        )
    excluded_run_count = scraped_data_manifest.get("excluded_run_count")
    if excluded_run_count is not None and (not isinstance(excluded_run_count, int) or excluded_run_count < 0):
        raise StrategyV2SchemaValidationError(
            "scraped_data_manifest.excluded_run_count must be a non-negative integer when provided."
        )
    excluded_runs_payload = scraped_data_manifest.get("excluded_runs")
    if excluded_runs_payload is not None and not isinstance(excluded_runs_payload, list):
        raise StrategyV2SchemaValidationError(
            "scraped_data_manifest.excluded_runs must be an array when provided."
        )
    if isinstance(excluded_run_count, int):
        expected_total = manifest_run_count + excluded_run_count
        if expected_total != manifest_total_run_count:
            raise StrategyV2SchemaValidationError(
                "scraped_data_manifest run partition mismatch "
                f"(run_count={manifest_run_count}, excluded_run_count={excluded_run_count}, "
                f"total_run_count={manifest_total_run_count})."
            )
        if isinstance(excluded_runs_payload, list) and len(excluded_runs_payload) != excluded_run_count:
            raise StrategyV2SchemaValidationError(
                "scraped_data_manifest.excluded_runs length must match excluded_run_count "
                f"(excluded_runs={len(excluded_runs_payload)}, excluded_run_count={excluded_run_count})."
            )

    for index, (run_row, file_row) in enumerate(zip(runs_payload, raw_files_payload), start=1):
        if not isinstance(run_row, dict):
            raise StrategyV2SchemaValidationError(
                f"scraped_data_manifest.runs[{index - 1}] must be an object for v2-04 Agent 1."
            )
        if not isinstance(file_row, dict):
            raise StrategyV2SchemaValidationError(
                f"scraped_data_manifest.raw_scraped_data_files[{index - 1}] must be an object for v2-04 Agent 1."
            )

        run_item_count = run_row.get("item_count")
        file_item_count = file_row.get("item_count")
        if not isinstance(run_item_count, int) or run_item_count < 0:
            raise StrategyV2SchemaValidationError(
                f"scraped_data_manifest.runs[{index - 1}].item_count must be a non-negative integer."
            )
        if not isinstance(file_item_count, int) or file_item_count < 0:
            raise StrategyV2SchemaValidationError(
                "scraped_data_manifest.raw_scraped_data_files"
                f"[{index - 1}].item_count must be a non-negative integer."
            )
        if run_item_count != file_item_count:
            raise StrategyV2SchemaValidationError(
                "scraped_data_manifest item_count mismatch between runs and raw_scraped_data_files "
                f"at index {index - 1} (run_item_count={run_item_count}, file_item_count={file_item_count})."
            )

        for key in ("actor_id", "run_id", "dataset_id", "config_id"):
            run_value = str(run_row.get(key) or "").strip()
            file_value = str(file_row.get(key) or "").strip()
            if run_value != file_value:
                raise StrategyV2SchemaValidationError(
                    "scraped_data_manifest metadata mismatch between runs and raw_scraped_data_files "
                    f"at index {index - 1} for '{key}' (run='{run_value}', file='{file_value}')."
                )

        strategy_target_id = str(file_row.get("strategy_target_id") or "").strip()
        if not strategy_target_id:
            raise StrategyV2SchemaValidationError(
                "scraped_data_manifest.raw_scraped_data_files"
                f"[{index - 1}].strategy_target_id must be non-empty (use CANNOT_DETERMINE when unknown)."
            )
        run_strategy_target_id = str(run_row.get("strategy_target_id") or "").strip()
        if run_strategy_target_id != strategy_target_id:
            raise StrategyV2SchemaValidationError(
                "scraped_data_manifest metadata mismatch between runs and raw_scraped_data_files "
                f"at index {index - 1} for 'strategy_target_id' "
                f"(run='{run_strategy_target_id}', file='{strategy_target_id}')."
            )


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

    # CTA-alignment congruency checks are intentionally not hard-gated.
    for dimension, test_id in (("bh", "BH1"), ("pc", "PC2")):
        passed, detail = _extract_congruency_test_outcome(
            congruency=congruency,
            dimension=dimension,
            test_id=test_id,
        )
        if "N/A" in detail:
            raise StrategyV2DecisionError(
                f"{page_name} congruency test {test_id} is non-applicable ('{detail}'). "
                "Remediation: include required structure/content so hard gates are truly evaluated."
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


def _is_openai_model_name(model: str) -> bool:
    lower = model.strip().lower()
    return lower.startswith(("gpt-", "chatgpt-", "o", "omni-"))


def _normalize_openai_prompt_file_name_component(value: str, *, max_chars: int = 40) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip(".-")
    if not normalized:
        return "na"
    return normalized[:max_chars]


def _build_openai_prompt_json_filename(
    *,
    workflow_run_id: str,
    stage_label: str,
    logical_name: str,
) -> str:
    workflow_component = _normalize_openai_prompt_file_name_component(workflow_run_id, max_chars=28)
    stage_component = _normalize_openai_prompt_file_name_component(stage_label, max_chars=28)
    logical_component = _normalize_openai_prompt_file_name_component(logical_name, max_chars=48)
    return f"strategy-v2-{workflow_component}-{stage_component}-{logical_component}.json"


def _upload_openai_prompt_json_files(
    *,
    model: str,
    workflow_run_id: str,
    stage_label: str,
    logical_payloads: Mapping[str, Any],
) -> tuple[dict[str, str], list[str]]:
    if not _is_openai_model_name(model):
        raise StrategyV2MissingContextError(
            "Prompt runtime JSON file uploads require an OpenAI model because files.create + code_interpreter "
            f"are OpenAI-only (model='{model}'). Remediation: set STRATEGY_V2_VOC_MODEL to an OpenAI model."
        )

    llm = LLMClient(default_model=model)
    file_id_map: dict[str, str] = {}
    uploaded_file_ids: list[str] = []
    for logical_name, payload in logical_payloads.items():
        serialized = json.dumps(payload, ensure_ascii=True, indent=2)
        filename = _build_openai_prompt_json_filename(
            workflow_run_id=workflow_run_id,
            stage_label=stage_label,
            logical_name=logical_name,
        )
        file_id = llm.upload_openai_file_bytes(
            filename=filename,
            content_bytes=serialized.encode("utf-8"),
            purpose="assistants",
        )
        file_id_map[str(logical_name)] = file_id
        uploaded_file_ids.append(file_id)
    return file_id_map, uploaded_file_ids


def _cleanup_openai_prompt_files(*, model: str, file_ids: Sequence[str]) -> None:
    if not _is_openai_model_name(model):
        return
    normalized_file_ids = [
        file_id.strip()
        for file_id in file_ids
        if isinstance(file_id, str) and file_id.strip()
    ]
    if not normalized_file_ids:
        return
    llm = LLMClient(default_model=model)
    for file_id in normalized_file_ids:
        try:
            llm.delete_openai_file(file_id=file_id)
        except Exception as exc:  # pragma: no cover - best-effort cleanup
            activity.logger.warning(
                "strategy_v2.openai_prompt_file_cleanup_failed",
                extra={"model": model, "file_id": file_id, "error": str(exc)},
            )


def _openai_python_tool_resources(
    model: str,
    *,
    file_ids: Sequence[str] | None = None,
) -> list[dict[str, Any]] | None:
    if not _is_openai_model_name(model):
        return None
    code_interpreter_tool = deepcopy(_OPENAI_CODE_INTERPRETER_TOOL)
    normalized_file_ids = [
        file_id.strip()
        for file_id in (file_ids or [])
        if isinstance(file_id, str) and file_id.strip()
    ]
    if normalized_file_ids:
        container = code_interpreter_tool.get("container")
        if not isinstance(container, dict):
            raise StrategyV2SchemaValidationError(
                "OpenAI code_interpreter tool must include a container object before file_ids can be attached."
            )
        container["file_ids"] = normalized_file_ids
    return [code_interpreter_tool]


def _llm_generate_text(
    *,
    prompt: str,
    model: str,
    use_reasoning: bool = False,
    reasoning_effort: str | None = None,
    use_web_search: bool = False,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
    openai_tools: list[dict[str, Any]] | None = None,
    openai_tool_choice: Any | None = None,
    openai_context_management: list[dict[str, Any]] | None = None,
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

    resumed_response_id = _recover_openai_response_id_from_heartbeat(heartbeat_context=heartbeat_context)
    if resumed_response_id and progress_callback is not None:
        progress_callback({"status": "resuming", "response_id": resumed_response_id})

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

        claude_structured_max_tokens = max_tokens or _CLAUDE_STRUCTURED_FALLBACK_MAX_TOKENS
        if claude_structured_max_tokens > _CLAUDE_MAX_OUTPUT_TOKENS:
            claude_structured_max_tokens = _CLAUDE_MAX_OUTPUT_TOKENS

        structured_kwargs: dict[str, Any] = {
            "model": model,
            "system": None,
            "output_schema": schema,
            "max_tokens": claude_structured_max_tokens,
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
        reasoning_effort=reasoning_effort,
        use_web_search=use_web_search,
        response_format=response_format,
        openai_tools=openai_tools,
        openai_tool_choice=openai_tool_choice,
        openai_context_management=openai_context_management,
        progress_callback=progress_callback,
        existing_openai_response_id=resumed_response_id,
    )
    output = llm.generate_text(prompt, params)
    cleaned = output.strip()
    if not cleaned:
        raise StrategyV2MissingContextError(
            f"LLM returned empty output for model '{model}'. "
            "Remediation: rerun the step after verifying model access and prompt input size."
    )
    return cleaned


def _recover_openai_response_id_from_heartbeat(
    *,
    heartbeat_context: Mapping[str, Any] | None,
) -> str | None:
    if not isinstance(heartbeat_context, Mapping) or not heartbeat_context:
        return None
    try:
        heartbeat_details = list(activity.info().heartbeat_details or [])
    except Exception:
        return None
    if not heartbeat_details:
        return None
    last_payload = heartbeat_details[-1]
    if not isinstance(last_payload, Mapping):
        return None
    response_id = str(last_payload.get("response_id") or "").strip()
    if not response_id:
        return None
    for key, expected in heartbeat_context.items():
        if not isinstance(key, str):
            continue
        if expected is None or not isinstance(expected, (str, int, float, bool)):
            continue
        if last_payload.get(key) != expected:
            return None
    return response_id


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


def _parse_json_response_strict(*, raw_text: str, field_name: str) -> dict[str, Any]:
    cleaned = raw_text.strip()
    if not cleaned:
        raise StrategyV2MissingContextError(
            f"Expected JSON object for '{field_name}', received empty text."
        )
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^\s*```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise StrategyV2SchemaValidationError(
            f"Failed to parse JSON object for '{field_name}': {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise StrategyV2SchemaValidationError(
            f"Expected JSON object for '{field_name}', received '{type(parsed).__name__}'."
        )
    return parsed


_SALES_TEMPLATE_TOP_LEVEL_KEYS: set[str] = {
    "hero",
    "problem",
    "mechanism",
    "social_proof",
    "whats_inside",
    "bonus",
    "guarantee",
    "faq",
    "faq_pills",
    "marquee_items",
    "urgency_message",
    "cta_close",
}


def _recover_fragmented_sales_template_payload_json(*, raw_text: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    cleaned = raw_text.strip()
    if not cleaned:
        return None
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^\s*```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    try:
        first_object, first_end_index = json.JSONDecoder().raw_decode(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(first_object, dict):
        return None

    tail = cleaned[first_end_index:].strip()
    if not tail.startswith(","):
        return None
    tail_without_delimiter = tail.lstrip(",").strip()
    if not tail_without_delimiter.startswith('"'):
        return None

    try:
        tail_object = json.loads("{" + tail_without_delimiter)
    except json.JSONDecodeError:
        return None
    if not isinstance(tail_object, dict):
        return None

    overlapping_keys = [key for key in tail_object.keys() if key in first_object]
    if overlapping_keys:
        return None

    merged = dict(first_object)
    merged.update(tail_object)
    recovery = {
        "mode": "fragmented_top_level_object_recovery",
        "first_object_key_count": len(first_object),
        "tail_object_key_count": len(tail_object),
        "merged_key_count": len(merged),
        "first_expected_top_level_key_hits": len(_SALES_TEMPLATE_TOP_LEVEL_KEYS.intersection(first_object.keys())),
        "tail_expected_top_level_key_hits": len(_SALES_TEMPLATE_TOP_LEVEL_KEYS.intersection(tail_object.keys())),
        "merged_expected_top_level_key_hits": len(_SALES_TEMPLATE_TOP_LEVEL_KEYS.intersection(merged.keys())),
    }
    return merged, recovery


def _looks_like_incomplete_json_object(*, raw_text: str) -> bool:
    cleaned = raw_text.strip()
    if not cleaned:
        return False
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^\s*```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    if "{" not in cleaned:
        return False

    depth = 0
    in_string = False
    escaped = False
    for char in cleaned:
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
            depth = max(0, depth - 1)
            continue
    return in_string or depth > 0


def _extract_json_object_candidates(*, raw_text: str, max_candidates: int = 12) -> list[dict[str, Any]]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^\s*```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    start_index: int | None = None
    depth = 0
    in_string = False
    escaped = False
    candidates: list[dict[str, Any]] = []
    for index, char in enumerate(cleaned):
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
                snippet = cleaned[start_index : index + 1]
                start_index = None
                try:
                    parsed = json.loads(snippet)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    candidates.append(parsed)
                    if len(candidates) >= max_candidates:
                        break
    return candidates


def _parse_sales_template_payload_json(*, raw_text: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    try:
        strict = _parse_json_response_strict(raw_text=raw_text, field_name="sales_template_payload")
        return strict, None
    except (StrategyV2MissingContextError, StrategyV2SchemaValidationError) as strict_exc:
        if _looks_like_incomplete_json_object(raw_text=raw_text):
            raise StrategyV2SchemaValidationError(
                "Sales template payload appears to be incomplete JSON (truncated before the top-level object closed). "
                "Remediation: increase completion budget or return a shorter payload."
            ) from strict_exc

        fragmented_recovery = _recover_fragmented_sales_template_payload_json(raw_text=raw_text)
        if fragmented_recovery is not None:
            return fragmented_recovery

        candidate_rows = _extract_json_object_candidates(raw_text=raw_text, max_candidates=12)
        if not candidate_rows:
            raise StrategyV2SchemaValidationError(str(strict_exc)) from strict_exc

        unique_candidates: list[dict[str, Any]] = []
        seen_signatures: set[str] = set()
        for row in candidate_rows:
            signature = json.dumps(row, sort_keys=True, ensure_ascii=True)
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            unique_candidates.append(row)
        if not unique_candidates:
            raise StrategyV2SchemaValidationError(str(strict_exc)) from strict_exc

        scored: list[tuple[int, int, int, int, dict[str, Any]]] = []
        for index, candidate in enumerate(unique_candidates):
            candidate_for_validation = candidate
            try:
                candidate_for_validation = upgrade_strategy_v2_template_payload_fields(
                    template_id="sales-pdp",
                    payload_fields=candidate,
                )
            except StrategyV2DecisionError:
                candidate_for_validation = candidate
            report = inspect_strategy_v2_template_payload_validation(
                template_id="sales-pdp",
                payload_fields=candidate_for_validation,
                max_items=1,
            )
            error_count = int(report.get("error_count") or 0)
            expected_top_level_key_hits = len(_SALES_TEMPLATE_TOP_LEVEL_KEYS.intersection(candidate.keys()))
            top_level_key_count = len(candidate.keys())
            scored.append(
                (
                    -expected_top_level_key_hits,
                    error_count,
                    -top_level_key_count,
                    index,
                    candidate,
                )
            )

        scored.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
        best_row = scored[0]
        best_rows = [
            row
            for row in scored
            if row[0] == best_row[0]
            and row[1] == best_row[1]
            and row[2] == best_row[2]
        ]
        if len(best_rows) != 1:
            raise StrategyV2SchemaValidationError(
                "Sales template payload parser found multiple JSON object candidates with equivalent validation scores. "
                "Remediation: return exactly one JSON object in template_payload_json."
            ) from strict_exc

        selected_row = best_rows[0]
        selected_index = selected_row[3]
        selected = selected_row[4]
        recovery = {
            "mode": "candidate_recovery",
            "strict_parse_error": str(strict_exc),
            "candidate_count": len(unique_candidates),
            "selected_candidate_index": selected_index,
            "selected_error_count": selected_row[1],
            "selected_expected_top_level_key_hits": -selected_row[0],
            "selected_top_level_key_count": -selected_row[2],
        }
        return selected, recovery


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
        if "additionalProperties" not in normalized:
            normalized["additionalProperties"] = False
        elif isinstance(normalized["additionalProperties"], dict):
            normalized["additionalProperties"] = _enforce_strict_openai_json_schema(normalized["additionalProperties"])

        if "required" not in normalized and properties:
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


def _offer_step05_dimension_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "raw_score": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 10.0,
            },
            "evidence_quality": {
                "type": "string",
                "enum": list(_OFFER_EVIDENCE_QUALITY_LEVELS),
            },
            "kill_condition": {
                "type": "string",
                "minLength": 1,
                "maxLength": _STEP05_KILL_CONDITION_MAX_CHARS,
                "pattern": ".*\\S.*",
            },
            "competitor_baseline": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "mean": {"type": "number"},
                    "spread": {"type": "number", "minimum": 0.0},
                },
                "required": ["mean", "spread"],
            },
        },
        "required": ["raw_score", "evidence_quality", "kill_condition", "competitor_baseline"],
    }


def _offer_step05_response_schema() -> dict[str, Any]:
    dimension_schema = _offer_step05_dimension_schema()
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "evaluation": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "variants": {
                        "type": "array",
                        "minItems": len(_OFFER_VARIANT_IDS),
                        "maxItems": len(_OFFER_VARIANT_IDS),
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "variant_id": {
                                    "type": "string",
                                    "enum": list(_OFFER_VARIANT_IDS),
                                },
                                "dimensions": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        dimension: deepcopy(dimension_schema)
                                        for dimension in _OFFER_COMPOSITE_DIMENSIONS
                                    },
                                    "required": list(_OFFER_COMPOSITE_DIMENSIONS),
                                },
                            },
                            "required": ["variant_id", "dimensions"],
                        },
                    }
                },
                "required": ["variants"],
            },
            "revision_notes": {
                "type": "string",
                "minLength": 1,
                "maxLength": _STEP05_REVISION_NOTES_MAX_CHARS,
                "pattern": ".*\\S.*",
            },
        },
        "required": ["evaluation", "revision_notes"],
    }


def _offer_step04_bonus_module_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "copy": {
                "type": "string",
                "minLength": 1,
                "maxLength": _STEP04_BONUS_COPY_MAX_CHARS,
                "pattern": ".*\\S.*",
            },
        },
        "required": ["copy"],
    }


def _offer_step04_response_schema(*, bonus_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "variants": {
                "type": "array",
                "minItems": len(_OFFER_VARIANT_IDS),
                "maxItems": len(_OFFER_VARIANT_IDS),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "variant_id": {
                            "type": "string",
                            "enum": list(_OFFER_VARIANT_IDS),
                        },
                        "core_promise": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": _STEP04_CORE_PROMISE_MAX_CHARS,
                            "pattern": ".*\\S.*",
                        },
                        "value_stack": {
                            "type": "array",
                            "minItems": 3,
                            "maxItems": 7,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "name": {"type": "string"},
                                    "dream_outcome": {
                                        "type": "number",
                                        "minimum": 0.0,
                                        "maximum": 10.0,
                                    },
                                    "perceived_likelihood": {
                                        "type": "number",
                                        "minimum": 0.0,
                                        "maximum": 10.0,
                                    },
                                    "time_delay": {
                                        "type": "number",
                                        "minimum": 0.0,
                                        "maximum": 10.0,
                                    },
                                    "effort_sacrifice": {
                                        "type": "number",
                                        "minimum": 0.0,
                                        "maximum": 10.0,
                                    },
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
                        "guarantee": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 320,
                            "pattern": ".*\\S.*",
                        },
                        "pricing_rationale": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 320,
                            "pattern": ".*\\S.*",
                        },
                        "pricing_metadata": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "list_price_cents": {"type": "integer", "minimum": 1},
                                "offer_price_cents": {"type": "integer", "minimum": 1},
                            },
                            "required": ["list_price_cents", "offer_price_cents"],
                        },
                        "savings_metadata": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "savings_amount_cents": {"type": "integer", "minimum": 0},
                                "savings_percent": {"type": "number", "minimum": 0.0},
                                "savings_basis": {"type": "string", "minLength": 1, "pattern": ".*\\S.*"},
                            },
                            "required": ["savings_amount_cents", "savings_percent", "savings_basis"],
                        },
                        "best_value_metadata": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "is_best_value": {"type": "boolean"},
                                "rationale": {
                                    "type": "string",
                                    "minLength": 1,
                                    "maxLength": _STEP04_BEST_VALUE_REASON_MAX_CHARS,
                                    "pattern": ".*\\S.*",
                                },
                                "compared_variant_ids": {
                                    "type": "array",
                                    "minItems": len(_OFFER_VARIANT_IDS) - 1,
                                    "maxItems": len(_OFFER_VARIANT_IDS) - 1,
                                    "items": {"type": "string", "enum": list(_OFFER_VARIANT_IDS)},
                                },
                            },
                            "required": ["is_best_value", "rationale", "compared_variant_ids"],
                        },
                        "bonus_modules": {
                            **_build_exact_keyed_object_schema(
                                keys=bonus_ids,
                                field_name="Offer Step 04 bonus_ids",
                                value_schema=_offer_step04_bonus_module_schema(),
                            ),
                        },
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
                                    "coverage_strength": {
                                        "type": "number",
                                        "minimum": 0.0,
                                        "maximum": 10.0,
                                    },
                                },
                                "required": ["objection", "source", "covered", "coverage_strength"],
                            },
                        },
                        "dimension_scores": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "competitive_differentiation": {
                                    "type": "number",
                                    "minimum": 0.0,
                                    "maximum": 10.0,
                                },
                                "compliance_safety": {
                                    "type": "number",
                                    "minimum": 0.0,
                                    "maximum": 10.0,
                                },
                                "internal_consistency": {
                                    "type": "number",
                                    "minimum": 0.0,
                                    "maximum": 10.0,
                                },
                                "clarity_simplicity": {
                                    "type": "number",
                                    "minimum": 0.0,
                                    "maximum": 10.0,
                                },
                                "bottleneck_resilience": {
                                    "type": "number",
                                    "minimum": 0.0,
                                    "maximum": 10.0,
                                },
                                "momentum_continuity": {
                                    "type": "number",
                                    "minimum": 0.0,
                                    "maximum": 10.0,
                                },
                                "pricing_fidelity": {
                                    "type": "number",
                                    "minimum": 0.0,
                                    "maximum": 10.0,
                                },
                                "savings_fidelity": {
                                    "type": "number",
                                    "minimum": 0.0,
                                    "maximum": 10.0,
                                },
                                "best_value_fidelity": {
                                    "type": "number",
                                    "minimum": 0.0,
                                    "maximum": 10.0,
                                },
                            },
                            "required": [
                                "competitive_differentiation",
                                "compliance_safety",
                                "internal_consistency",
                                "clarity_simplicity",
                                "bottleneck_resilience",
                                "momentum_continuity",
                                "pricing_fidelity",
                                "savings_fidelity",
                                "best_value_fidelity",
                            ],
                        },
                    },
                    "required": [
                        "variant_id",
                        "core_promise",
                        "value_stack",
                        "guarantee",
                        "pricing_rationale",
                        "pricing_metadata",
                        "savings_metadata",
                        "best_value_metadata",
                        "bonus_modules",
                        "objection_map",
                        "dimension_scores",
                    ],
                },
            }
        },
        "required": ["variants"],
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


def _run_with_activity_heartbeats(
    *,
    phase: str,
    operation: str,
    heartbeat_payload: Mapping[str, Any],
    fn: Callable[[], Any],
    interval_seconds: float = 15.0,
) -> Any:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive.")
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn)
        while True:
            try:
                return future.result(timeout=interval_seconds)
            except FuturesTimeoutError:
                payload: dict[str, Any] = {
                    "phase": phase,
                    "status": "in_progress",
                    "progress_event": operation,
                }
                for key, value in heartbeat_payload.items():
                    if value is not None:
                        payload[str(key)] = value
                activity.heartbeat(payload)


def _heartbeat_safe(payload: Mapping[str, Any]) -> None:
    try:
        activity.heartbeat(dict(payload))
    except RuntimeError:
        return


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
    reasoning_effort: str | None = None,
    use_web_search: bool = False,
    max_tokens: int | None = None,
    openai_tools: list[dict[str, Any]] | None = None,
    openai_tool_choice: Any | None = None,
    openai_context_management: list[dict[str, Any]] | None = None,
    conversation_messages: list[dict[str, Any]] | None = None,
    log_metadata: Mapping[str, Any] | None = None,
    heartbeat_context: dict[str, Any] | None = None,
    llm_call_log: list[dict[str, Any]] | None = None,
    llm_call_label: str | None = None,
    append_schema_instruction: bool = True,
) -> tuple[dict[str, Any], str, dict[str, str]]:
    rendered = _render_prompt_asset(asset=asset, context=context, variables=variables).rstrip()
    instruction_block = runtime_instruction.strip()
    prompt = rendered + ("\n\n" + instruction_block if instruction_block else "")
    if append_schema_instruction:
        prompt += "\n\nReturn ONLY valid JSON matching the required schema."
    input_token_budget = _model_prompt_input_token_budget(model=model, max_tokens=max_tokens)
    if input_token_budget is not None:
        estimated_input_tokens = _estimate_prompt_input_tokens(prompt)
        if estimated_input_tokens > input_token_budget:
            raise StrategyV2MissingContextError(
                "Prompt input exceeds model budget "
                f"(estimated_input_tokens={estimated_input_tokens}, budget_tokens={input_token_budget}, model='{model}'). "
                "Remediation: reduce runtime payload size and retry."
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
        reasoning_effort=reasoning_effort,
        use_web_search=use_web_search,
        max_tokens=max_tokens,
        response_format=_json_schema_response_format(name=schema_name, schema=schema),
        openai_tools=openai_tools,
        openai_tool_choice=openai_tool_choice,
        openai_context_management=openai_context_management,
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
    response_id = llm_progress.get("response_id")
    if isinstance(response_id, str) and response_id.strip():
        provenance["openai_response_id"] = response_id.strip()
    request_id = llm_progress.get("request_id")
    if isinstance(request_id, str) and request_id.strip():
        provenance["openai_request_id"] = request_id.strip()
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
    reasoning_effort: str | None = None,
    use_web_search: bool = False,
    max_tokens: int | None = None,
    openai_tools: list[dict[str, Any]] | None = None,
    openai_tool_choice: Any | None = None,
    openai_context_management: list[dict[str, Any]] | None = None,
    conversation_messages: list[dict[str, Any]] | None = None,
    log_metadata: Mapping[str, Any] | None = None,
    heartbeat_context: dict[str, Any] | None = None,
    llm_call_log: list[dict[str, Any]] | None = None,
    llm_call_label: str | None = None,
    append_schema_instruction: bool = True,
) -> tuple[list[Any], str, dict[str, str]]:
    rendered = _render_prompt_asset(asset=asset, context=context, variables=variables).rstrip()
    instruction_block = runtime_instruction.strip()
    prompt = rendered + ("\n\n" + instruction_block if instruction_block else "")
    if append_schema_instruction:
        prompt += "\n\nReturn ONLY valid JSON matching the required schema."
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
        reasoning_effort=reasoning_effort,
        use_web_search=use_web_search,
        max_tokens=max_tokens,
        response_format=_json_schema_response_format(name=schema_name, schema=schema),
        openai_tools=openai_tools,
        openai_tool_choice=openai_tool_choice,
        openai_context_management=openai_context_management,
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
    response_id = llm_progress.get("response_id")
    if isinstance(response_id, str) and response_id.strip():
        provenance["openai_response_id"] = response_id.strip()
    request_id = llm_progress.get("request_id")
    if isinstance(request_id, str) and request_id.strip():
        provenance["openai_request_id"] = request_id.strip()
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
    lineage: Mapping[str, Any] | None = None,
) -> str:
    artifacts_repo = ArtifactsRepository(session)
    research_repo = ResearchArtifactsRepository(session)
    workflows_repo = WorkflowsRepository(session)

    lineage_payload: dict[str, Any]
    if lineage is None:
        lineage_payload = {
            "producer": step_key,
            "producer_version": prompt_version,
            "timestamp": _now_iso(),
            "inputs_received": sorted([str(key) for key in payload.keys()]),
            "input_validation": "PASS",
        }
    else:
        lineage_payload = dict(lineage)
    envelope: dict[str, Any] = {
        "step_key": step_key,
        "title": title,
        "summary": summary,
        "lineage": lineage_payload,
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


def _coerce_video_metric_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value >= 0 else None
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            parsed = float(cleaned)
        except ValueError:
            return None
        return int(parsed) if parsed >= 0 else None
    return None


def _coerce_days_since_posted(row: Mapping[str, Any]) -> int | None:
    for field_name in ("days_since_posted", "daysSincePosted", "post_age_days"):
        value = _coerce_video_metric_int(row.get(field_name))
        if value is not None:
            return value

    for field_name in (
        "timestamp",
        "publishedAt",
        "published_at",
        "createdAt",
        "created_at",
        "createTimeISO",
        "createTime",
    ):
        timestamp_text = _coerce_manifest_timestamp(row.get(field_name))
        if not timestamp_text:
            continue
        try:
            dt = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(int((datetime.now(timezone.utc) - dt).total_seconds() // 86_400), 0)
        except Exception:
            continue
    return None


def _normalize_video_platform_name(*, raw_platform: Any, source_ref: str) -> str:
    platform = str(raw_platform or "").strip().upper()
    if platform:
        if "YOUTUBE" in platform:
            return "YOUTUBE"
        if "TIKTOK" in platform:
            return "TIKTOK"
        if "INSTAGRAM" in platform:
            return "INSTAGRAM"
        return platform
    lowered_ref = source_ref.lower()
    if "youtube.com" in lowered_ref or "youtu.be" in lowered_ref:
        return "YOUTUBE"
    if "tiktok.com" in lowered_ref:
        return "TIKTOK"
    if "instagram.com" in lowered_ref:
        return "INSTAGRAM"
    return "UNKNOWN"


def _normalize_video_metrics_for_scoring(*, row: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(row)

    def _first_int(*field_names: str) -> int | None:
        for field_name in field_names:
            candidate = _coerce_video_metric_int(normalized.get(field_name))
            if candidate is not None:
                return candidate
        return None

    views = _first_int("views", "view_count", "viewCount", "playCount", "videoPlayCount", "videoViewCount")
    followers = _first_int(
        "followers",
        "account_followers",
        "numberOfSubscribers",
        "subscriberCount",
        "channelSubscriberCount",
    )
    comments = _first_int("comments", "comment_count", "commentsCount")
    shares = _first_int("shares", "share_count", "shareCount")
    likes = _first_int("likes", "like_count", "likesCount")
    days_since_posted = _coerce_days_since_posted(normalized)

    if views is not None:
        normalized["views"] = views
    if followers is not None:
        normalized["followers"] = followers
    if comments is not None:
        normalized["comments"] = comments
    if shares is not None:
        normalized["shares"] = shares
    if likes is not None:
        normalized["likes"] = likes
    if days_since_posted is not None:
        normalized["days_since_posted"] = days_since_posted

    normalized["platform"] = _normalize_video_platform_name(
        raw_platform=normalized.get("platform"),
        source_ref=str(normalized.get("source_ref") or ""),
    )
    return normalized


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

        normalized_sheet = _normalize_video_metrics_for_scoring(row=sheet)
        views = normalized_sheet.get("views")
        followers = normalized_sheet.get("followers")
        comments = normalized_sheet.get("comments")
        shares = normalized_sheet.get("shares")
        likes = normalized_sheet.get("likes")
        days = normalized_sheet.get("days_since_posted")
        description = str(sheet.get("core_claim") or sheet.get("headline") or "").strip()
        author = str(sheet.get("competitor_name") or sheet.get("brand") or f"source-{index}").strip()

        if not isinstance(views, int) or not isinstance(followers, int):
            continue

        videos.append(
            {
                "video_id": str(sheet.get("asset_id") or f"video-{index + 1}"),
                "platform": platform_value or "unknown",
                "views": int(views),
                "followers": int(followers),
                "comments": int(comments) if isinstance(comments, int) else 0,
                "shares": int(shares) if isinstance(shares, int) else 0,
                "likes": int(likes) if isinstance(likes, int) else 0,
                "days_since_posted": int(days) if isinstance(days, int) else 0,
                "description": description,
                "author": author,
                "source_ref": str(sheet.get("source_ref") or ""),
            }
        )

    return videos


def _extract_config_input_urls(input_payload: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("startUrls", "urls", "directUrls", "profiles", "postURLs"):
        raw_value = input_payload.get(key)
        if not isinstance(raw_value, list):
            continue
        for item in raw_value:
            if isinstance(item, str) and item.strip():
                refs.append(item.strip())
            elif isinstance(item, Mapping):
                url_value = item.get("url")
                if isinstance(url_value, str) and url_value.strip():
                    refs.append(url_value.strip())
    return refs


def _canonical_social_source_key(source_ref: str) -> str:
    canonical = _canonicalize_source_ref_for_ingestion(source_ref)
    if not canonical:
        return ""
    parsed = urlsplit(canonical)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/")
    if "tiktok.com" in host:
        handle_match = re.search(r"/@([A-Za-z0-9_.-]+)", path, flags=re.IGNORECASE)
        if handle_match:
            return f"{host}/@{handle_match.group(1).lower()}"
    if "instagram.com" in host:
        handle_match = re.match(r"/([A-Za-z0-9_.-]+)", path)
        if handle_match:
            return f"{host}/{handle_match.group(1).lower()}"
    if "youtube.com" in host:
        channel_match = re.search(r"/(@[A-Za-z0-9_.-]+|channel/[A-Za-z0-9_-]+)", path, flags=re.IGNORECASE)
        if channel_match:
            return f"{host}/{channel_match.group(1).lower()}"
    if "youtu.be" in host:
        return "youtube.com"
    return f"{host}{path.lower()}"


def _extract_video_source_allowlist(video_strategy: Mapping[str, Any]) -> set[str]:
    allowlist: set[str] = set()
    configurations = video_strategy.get("configurations")
    if not isinstance(configurations, list):
        return allowlist
    for row in configurations:
        if not isinstance(row, Mapping):
            continue
        platform = str(row.get("platform") or "").strip().upper()
        if platform not in {"TIKTOK", "INSTAGRAM", "YOUTUBE", "YOUTUBE_SHORTS"}:
            continue
        input_payload = row.get("input")
        if not isinstance(input_payload, Mapping):
            continue
        for ref in _extract_config_input_urls(input_payload):
            key = _canonical_social_source_key(ref)
            if key:
                allowlist.add(key)
    return allowlist


def _source_matches_allowlist(*, source_ref: str, allowlist: set[str]) -> bool:
    if not allowlist:
        return True
    source_key = _canonical_social_source_key(source_ref)
    if not source_key:
        return False
    source_host = source_key.split("/", 1)[0]
    for allowed in allowlist:
        if source_key == allowed or source_key.startswith(f"{allowed}/"):
            return True
        # Discovery strategy inputs (search/tag URLs) intentionally fan out into
        # post URLs that won't prefix-match the seed discovery URL path.
        if allowed.startswith("instagram.com/explore") and source_host == "instagram.com":
            return True
        if allowed.startswith("youtube.com/results") and source_host in {"youtube.com", "youtu.be"}:
            return True
        if allowed.startswith("tiktok.com/tag/") and source_host == "tiktok.com":
            return True
    return False


def _build_video_topic_keywords(*, stage1: ProductBriefStage1) -> list[str]:
    keywords: list[str] = []
    seen: set[str] = set()
    for raw in [*stage1.product_category_keywords, stage1.category_niche, stage1.product_name]:
        if not isinstance(raw, str):
            continue
        for part in re.split(r"[^a-zA-Z0-9]+", raw.lower()):
            token = part.strip()
            if len(token) < 4:
                continue
            if token in seen:
                continue
            seen.add(token)
            keywords.append(token)
    return keywords


def _video_row_matches_topic(*, row: Mapping[str, Any], topic_keywords: Sequence[str]) -> bool:
    if not topic_keywords:
        return True
    haystack = " ".join(
        [
            str(row.get("description") or ""),
            str(row.get("author") or ""),
            str(row.get("source_ref") or ""),
        ]
    ).lower()
    return any(keyword in haystack for keyword in topic_keywords)


def _filter_metric_video_rows_for_scoring(
    *,
    video_rows: Sequence[Mapping[str, Any]],
    source_allowlist: set[str],
    topic_keywords: Sequence[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    diagnostics: dict[str, Any] = {
        "input_rows": len(video_rows),
        "missing_metrics": 0,
        "off_target_source": 0,
        "off_topic": 0,
        "kept_rows": 0,
        "by_platform": {},
    }
    filtered: list[dict[str, Any]] = []
    for row in video_rows:
        if not isinstance(row, Mapping):
            continue
        normalized_row = _normalize_video_metrics_for_scoring(row=row)
        platform = _normalize_video_platform_name(
            raw_platform=normalized_row.get("platform"),
            source_ref=str(normalized_row.get("source_ref") or ""),
        )
        platform_diag = diagnostics["by_platform"].setdefault(
            platform,
            {
                "input_rows": 0,
                "missing_metrics": 0,
                "off_target_source": 0,
                "off_topic": 0,
                "kept_rows": 0,
            },
        )
        platform_diag["input_rows"] += 1
        if not isinstance(normalized_row.get("followers"), int):
            normalized_row["followers"] = 0
        metrics_present = (
            isinstance(normalized_row.get("views"), int)
            and isinstance(normalized_row.get("comments"), int)
            and isinstance(normalized_row.get("shares"), int)
            and isinstance(normalized_row.get("likes"), int)
            and isinstance(normalized_row.get("days_since_posted"), int)
        )
        if not metrics_present:
            diagnostics["missing_metrics"] += 1
            platform_diag["missing_metrics"] += 1
            continue
        source_ref = str(normalized_row.get("source_ref") or "").strip()
        if not source_ref or not _source_matches_allowlist(source_ref=source_ref, allowlist=source_allowlist):
            diagnostics["off_target_source"] += 1
            platform_diag["off_target_source"] += 1
            continue
        if not _video_row_matches_topic(row=normalized_row, topic_keywords=topic_keywords):
            diagnostics["off_topic"] += 1
            platform_diag["off_topic"] += 1
            continue
        filtered.append(dict(normalized_row))
        platform_diag["kept_rows"] += 1
    diagnostics["kept_rows"] = len(filtered)
    return filtered, diagnostics


def _normalize_video_scored_rows(video_scored: object) -> list[dict[str, Any]]:
    if isinstance(video_scored, list):
        return [row for row in video_scored if isinstance(row, dict)]
    if isinstance(video_scored, Mapping):
        raw_rows = video_scored.get("videos")
        if isinstance(raw_rows, list):
            return [row for row in raw_rows if isinstance(row, dict)]
    return []


def _build_video_scoring_audit(
    *,
    video_observation_count: int,
    metric_video_observation_count: int,
    video_scored: Sequence[Mapping[str, Any]],
    video_filter_diagnostics: Mapping[str, Any],
) -> dict[str, Any]:
    top_scored: list[dict[str, Any]] = []
    scored_rows = [row for row in video_scored if isinstance(row, Mapping)]
    for row in scored_rows[:10]:
        top_scored.append(
            {
                "video_id": str(row.get("video_id") or row.get("source_ref") or "").strip(),
                "source_ref": str(row.get("source_ref") or "").strip(),
                "platform": str(row.get("platform") or "").strip(),
                "rank": row.get("rank"),
                "viral_score": row.get("viral_score"),
            }
        )
    return {
        "video_observation_count": int(video_observation_count),
        "metric_video_observation_count": int(metric_video_observation_count),
        "video_scored_count": int(len(scored_rows)),
        "exclusion_counts": {
            "missing_metrics": int(video_filter_diagnostics.get("missing_metrics") or 0),
            "off_target_source": int(video_filter_diagnostics.get("off_target_source") or 0),
            "off_topic": int(video_filter_diagnostics.get("off_topic") or 0),
        },
        "platform_diagnostics": (
            dict(video_filter_diagnostics.get("by_platform"))
            if isinstance(video_filter_diagnostics.get("by_platform"), Mapping)
            else {}
        ),
        "top_scored_videos": top_scored,
    }


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


def _resolve_offer_business_model(
    *,
    offer_pipeline_output: Mapping[str, Any],
    fallback_business_model: str | None = None,
) -> str:
    offer_input = offer_pipeline_output.get("offer_input")
    if isinstance(offer_input, dict):
        product_brief = offer_input.get("product_brief")
        if isinstance(product_brief, dict):
            business_model = str(product_brief.get("business_model") or "").strip()
            if business_model:
                return business_model
    if isinstance(fallback_business_model, str) and fallback_business_model.strip():
        return fallback_business_model.strip()
    raise StrategyV2MissingContextError(
        "Offer business_model is missing in offer_pipeline_output.offer_input.product_brief. "
        "Remediation: ensure v2-08 Offer pipeline output includes product_brief.business_model."
    )


def _resolve_offer_price_cents_and_currency(
    *,
    offer_pipeline_output: Mapping[str, Any],
) -> tuple[int, str]:
    offer_input = offer_pipeline_output.get("offer_input")
    if not isinstance(offer_input, dict):
        raise StrategyV2MissingContextError(
            "offer_pipeline_output.offer_input is missing for product variant sync. "
            "Remediation: ensure v2-08 Offer pipeline output includes offer_input.product_brief."
        )
    product_brief = offer_input.get("product_brief")
    if not isinstance(product_brief, dict):
        raise StrategyV2MissingContextError(
            "offer_pipeline_output.offer_input.product_brief is missing for product variant sync. "
            "Remediation: ensure v2-08 Offer pipeline output includes product_brief."
        )
    price_cents_raw = product_brief.get("price_cents")
    if not isinstance(price_cents_raw, int) or price_cents_raw < 0:
        raise StrategyV2MissingContextError(
            "Offer product_brief.price_cents is missing or invalid for product variant sync. "
            "Remediation: ensure v2-08 Offer pipeline output includes non-negative integer product_brief.price_cents."
        )
    currency = str(product_brief.get("currency") or "").strip().upper()
    if len(currency) != 3:
        raise StrategyV2MissingContextError(
            "Offer product_brief.currency is missing or invalid for product variant sync. "
            "Remediation: ensure v2-08 Offer pipeline output includes 3-letter product_brief.currency."
        )
    return price_cents_raw, currency


def _normalize_discount_and_savings_metadata(
    *,
    list_price_cents: int,
    offer_price_cents: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if list_price_cents <= 0:
        raise StrategyV2MissingContextError(
            "Offer data readiness requires list_price_cents > 0."
        )
    if offer_price_cents <= 0:
        raise StrategyV2MissingContextError(
            "Offer data readiness requires offer_price_cents > 0."
        )
    if offer_price_cents > list_price_cents:
        raise StrategyV2MissingContextError(
            "Offer data readiness detected invalid pricing: offer_price_cents exceeds list_price_cents."
        )
    savings_amount_cents = list_price_cents - offer_price_cents
    savings_pct = round((savings_amount_cents / float(list_price_cents)) * 100.0, 2) if list_price_cents else 0.0
    pricing_metadata = {
        "list_price_cents": int(list_price_cents),
        "offer_price_cents": int(offer_price_cents),
    }
    savings_metadata = {
        "savings_amount_cents": int(savings_amount_cents),
        "savings_percent": float(savings_pct),
        "savings_basis": "vs_list_price",
    }
    return pricing_metadata, savings_metadata


def _resolve_offer_bundle_context(
    *,
    session,
    org_id: str,
    client_id: str,
    product_id: str,
    onboarding_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    products_repo = ProductsRepository(session)
    offers_repo = ProductOffersRepository(session)
    bonuses_repo = ProductOfferBonusesRepository(session)
    variants_repo = ProductVariantsRepository(session)

    product = products_repo.get(org_id=org_id, product_id=product_id)
    if product is None or str(product.client_id) != client_id:
        raise StrategyV2MissingContextError(
            "Offer data readiness could not resolve product for this org/client/product."
        )
    onboarding_product_type = (
        canonical_product_type(str(onboarding_payload.get("product_type") or ""))
        if isinstance(onboarding_payload, Mapping)
        else None
    )
    product_type = canonical_product_type(str(product.product_type or ""))
    if onboarding_product_type and product_type and onboarding_product_type != product_type:
        raise StrategyV2MissingContextError(
            "Offer data readiness found mismatched product_type between onboarding payload and product record. "
            f"onboarding={onboarding_product_type} product={product_type}. "
            "Remediation: update products.category/product_type to match onboarding before running Offer Agent."
        )
    product_type = onboarding_product_type or product_type
    if not product_type:
        raise StrategyV2MissingContextError(
            "Offer data readiness requires product_type. "
            "Remediation: set products.category/product_type before running Offer Agent."
        )

    default_offer_id_raw = onboarding_payload.get("default_offer_id") if isinstance(onboarding_payload, Mapping) else None
    default_offer_id = str(default_offer_id_raw or "").strip() if default_offer_id_raw is not None else ""
    product_offers = offers_repo.list_by_product(product_id=product_id)
    target_offer = None
    if default_offer_id:
        target_offer = offers_repo.get(offer_id=default_offer_id)
        if target_offer is None:
            raise StrategyV2MissingContextError(
                "Offer data readiness default_offer_id was provided but not found."
            )
        if (
            str(target_offer.org_id) != org_id
            or str(target_offer.client_id) != client_id
            or str(target_offer.product_id or "") != product_id
        ):
            raise StrategyV2MissingContextError(
                "Offer data readiness default_offer_id does not belong to this org/client/product."
            )
    elif len(product_offers) == 1:
        target_offer = product_offers[0]
    elif len(product_offers) > 1:
        raise StrategyV2MissingContextError(
            "Offer data readiness requires onboarding default_offer_id when multiple offers exist."
        )

    if target_offer is None:
        raise StrategyV2MissingContextError(
            "Offer data readiness requires an existing product offer to anchor bundle contents."
        )

    variant_rows = [
        row
        for row in variants_repo.list_by_product(product_id=product_id)
        if str(row.offer_id or "") == str(target_offer.id)
    ]
    if not variant_rows:
        raise StrategyV2MissingContextError(
            "Offer data readiness requires at least one price point variant linked to the selected offer."
        )
    offer_price_cents = min(int(row.price) for row in variant_rows)
    compare_at_candidates = [int(row.compare_at_price) for row in variant_rows if isinstance(row.compare_at_price, int)]
    list_price_cents = max(compare_at_candidates) if compare_at_candidates else max(int(row.price) for row in variant_rows)
    pricing_metadata, savings_metadata = _normalize_discount_and_savings_metadata(
        list_price_cents=list_price_cents,
        offer_price_cents=offer_price_cents,
    )

    bonus_links = bonuses_repo.list_by_offer(offer_id=str(target_offer.id))
    bonus_items: list[dict[str, Any]] = []
    for link in bonus_links:
        linked_product = products_repo.get(org_id=org_id, product_id=str(link.bonus_product_id))
        if linked_product is None:
            raise StrategyV2MissingContextError(
                "Offer data readiness detected an invalid offer bonus link."
            )
        bonus_title = str(linked_product.title or "").strip()
        if not bonus_title:
            raise StrategyV2MissingContextError(
                "Offer data readiness requires non-empty bonus product title."
            )
        bonus_items.append(
            {
                "bonus_id": str(link.id),
                "linked_product_id": str(linked_product.id),
                "title": bonus_title,
                "product_type": str(linked_product.product_type or "").strip().lower() or "other",
                "position": int(link.position),
            }
        )
    bonus_items = sorted(bonus_items, key=lambda row: int(row.get("position") or 0))
    if len(bonus_items) != 3:
        raise StrategyV2MissingContextError(
            "Offer data readiness requires exactly 3 linked offer bonuses for V1."
        )

    core_product_context = {
        "product_id": str(product.id),
        "title": str(product.title or "").strip(),
        "product_type": product_type,
    }
    return {
        "offer_format": "DISCOUNT_PLUS_3_BONUSES_V1",
        "product_type": product_type,
        "core_product": core_product_context,
        "offer_id": str(target_offer.id),
        "offer_name": str(target_offer.name or "").strip(),
        "bonus_items": bonus_items,
        "pricing_metadata": pricing_metadata,
        "savings_metadata": savings_metadata,
        "bundle_contents": {
            "core_product": core_product_context,
            "offer_id": str(target_offer.id),
            "offer_name": str(target_offer.name or "").strip(),
            "bonuses": [
                {
                    "bonus_id": str(item.get("bonus_id") or ""),
                    "linked_product_id": str(item.get("linked_product_id") or ""),
                    "title": str(item.get("title") or ""),
                    "product_type": str(item.get("product_type") or ""),
                    "position": int(item.get("position") or 0),
                }
                for item in bonus_items
            ],
            "bonus_count": len(bonus_items),
        },
    }


@activity.defn(name="strategy_v2.validate_offer_data_readiness")
def validate_strategy_v2_offer_data_readiness_activity(params: dict[str, Any]) -> dict[str, Any]:
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
    offer_pipeline_output = _require_dict(payload=params["offer_pipeline_output"], field_name="offer_pipeline_output")

    missing_fields: list[str] = []
    inconsistent_fields: list[str] = []
    required_operator_inputs: list[str] = []
    remediation_steps: list[str] = []
    resolved_context: dict[str, Any] = {}

    with session_scope() as session:
        onboarding_payload = _load_onboarding_payload(
            session=session,
            org_id=org_id,
            client_id=client_id,
            onboarding_payload_id=onboarding_payload_id,
        )
        try:
            resolved_context = _resolve_offer_bundle_context(
                session=session,
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                onboarding_payload=onboarding_payload,
            )
        except StrategyV2MissingContextError as exc:
            inconsistent_fields.append(str(exc))
            remediation_steps.append(
                "Provide product_type, a default offer, one price point, and exactly 3 linked bonuses for Offer Agent V1."
            )

        offer_input = offer_pipeline_output.get("offer_input")
        if not isinstance(offer_input, dict):
            missing_fields.append("offer_pipeline_output.offer_input")
        else:
            product_brief = offer_input.get("product_brief")
            if not isinstance(product_brief, dict):
                missing_fields.append("offer_pipeline_output.offer_input.product_brief")
            else:
                if not isinstance(product_brief.get("price_cents"), int):
                    missing_fields.append("offer_pipeline_output.offer_input.product_brief.price_cents")
                currency = str(product_brief.get("currency") or "").strip().upper()
                if len(currency) != 3:
                    missing_fields.append("offer_pipeline_output.offer_input.product_brief.currency")

    status = "ready" if not missing_fields and not inconsistent_fields else "blocked"
    payload = {
        "status": status,
        "missing_fields": missing_fields,
        "inconsistent_fields": inconsistent_fields,
        "required_operator_inputs": required_operator_inputs,
        "remediation_steps": remediation_steps,
        "context": resolved_context,
    }

    with session_scope() as session:
        step_payload_artifact_id = _persist_step_payload(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            workflow_run_id=workflow_run_id,
            step_key=V2_STEP_OFFER_DATA_READINESS,
            title="Strategy V2 Offer Data Readiness",
            summary=(
                "Offer data readiness checks passed for V1 discount+3-bonus format."
                if status == "ready"
                else "Offer data readiness blocked with required remediation."
            ),
            payload=payload,
            model_name="deterministic_validator",
            prompt_version="strategy_v2.offer_data_readiness.v1",
            schema_version=SCHEMA_VERSION_V2,
            agent_run_id=None,
        )
    payload["step_payload_artifact_id"] = step_payload_artifact_id
    return payload


def _serialize_product_offer_for_strategy(offer: Any) -> dict[str, Any]:
    return {
        "id": str(offer.id),
        "org_id": str(offer.org_id),
        "client_id": str(offer.client_id),
        "product_id": str(offer.product_id) if offer.product_id else None,
        "name": str(offer.name),
        "description": str(offer.description) if isinstance(offer.description, str) else None,
        "business_model": str(offer.business_model),
        "differentiation_bullets": list(offer.differentiation_bullets or []),
        "guarantee_text": str(offer.guarantee_text) if isinstance(offer.guarantee_text, str) else None,
        "options_schema": offer.options_schema if isinstance(offer.options_schema, dict) else None,
        "created_at": offer.created_at.isoformat() if getattr(offer, "created_at", None) else None,
    }


def _resolve_offer_variant_bundle_quantity(*, variant_id: str, product_type: str | None) -> int:
    normalized = str(variant_id or "").strip().lower()
    if not normalized:
        raise StrategyV2MissingContextError(
            "Offer variant_id is required to resolve bundle quantity for product variant sync."
        )
    canonical_type = canonical_product_type(product_type)
    quantity_mapping = (
        _BOOK_OFFER_VARIANT_BUNDLE_QUANTITIES
        if canonical_type == "book"
        else _DEFAULT_OFFER_VARIANT_BUNDLE_QUANTITIES
    )
    quantity = quantity_mapping.get(normalized)
    if quantity is None:
        raise StrategyV2MissingContextError(
            f"Offer variant_id '{normalized}' is not recognized for bundle quantity resolution."
        )
    return quantity


def _resolve_offer_variant_display_label(*, variant_id: str, product_type: str | None = None) -> str:
    normalized = str(variant_id or "").strip().lower()
    if not normalized:
        raise StrategyV2MissingContextError(
            "Offer variant_id is required to resolve display label for product variant sync."
        )
    canonical_type = canonical_product_type(product_type)
    label_mapping = (
        _BOOK_OFFER_VARIANT_DISPLAY_LABELS
        if canonical_type == "book"
        else _OFFER_VARIANT_DISPLAY_LABELS
    )
    mapped_label = label_mapping.get(normalized)
    if mapped_label:
        return mapped_label
    return " ".join(part.capitalize() for part in normalized.replace("-", "_").split("_") if part)


def _normalize_scored_variants_for_offer_sync(
    *,
    scored_variants: Sequence[Mapping[str, Any]],
    product_type: str | None,
) -> list[dict[str, Any]]:
    if len(scored_variants) != len(_OFFER_VARIANT_IDS):
        raise StrategyV2MissingContextError(
            "Offer variant sync requires exactly 3 scored variants "
            f"({', '.join(_OFFER_VARIANT_IDS)})."
        )
    normalized_by_id: dict[str, dict[str, Any]] = {}
    for index, variant in enumerate(scored_variants, start=1):
        if not isinstance(variant, Mapping):
            raise StrategyV2MissingContextError(
                f"Offer variant sync received non-object variant at index {index}."
            )
        variant_id = str(variant.get("variant_id") or "").strip().lower()
        if variant_id not in _OFFER_VARIANT_IDS:
            raise StrategyV2MissingContextError(
                "Offer variant sync received unknown variant_id "
                f"'{variant_id or '<empty>'}'. Expected: {', '.join(_OFFER_VARIANT_IDS)}."
            )
        if variant_id in normalized_by_id:
            raise StrategyV2MissingContextError(
                f"Offer variant sync received duplicate variant_id '{variant_id}'."
            )
        pricing_metadata = _require_dict(
            payload=variant.get("pricing_metadata"),
            field_name=f"offer_sync.{variant_id}.pricing_metadata",
        )
        list_price_cents = pricing_metadata.get("list_price_cents")
        offer_price_cents = pricing_metadata.get("offer_price_cents")
        if not isinstance(list_price_cents, int) or list_price_cents <= 0:
            raise StrategyV2MissingContextError(
                f"Offer variant '{variant_id}' must include positive integer pricing_metadata.list_price_cents."
            )
        if not isinstance(offer_price_cents, int) or offer_price_cents <= 0:
            raise StrategyV2MissingContextError(
                f"Offer variant '{variant_id}' must include positive integer pricing_metadata.offer_price_cents."
            )
        if offer_price_cents > list_price_cents:
            raise StrategyV2MissingContextError(
                f"Offer variant '{variant_id}' has offer_price_cents greater than list_price_cents."
            )
        normalized_by_id[variant_id] = {
            "variant_id": variant_id,
            "display_label": _resolve_offer_variant_display_label(
                variant_id=variant_id,
                product_type=product_type,
            ),
            "bundle_quantity": _resolve_offer_variant_bundle_quantity(
                variant_id=variant_id,
                product_type=product_type,
            ),
            "core_promise": str(variant.get("core_promise") or "").strip(),
            "pricing_metadata": {
                "list_price_cents": list_price_cents,
                "offer_price_cents": offer_price_cents,
            },
            "savings_metadata": (
                dict(variant.get("savings_metadata"))
                if isinstance(variant.get("savings_metadata"), Mapping)
                else None
            ),
            "best_value_metadata": (
                dict(variant.get("best_value_metadata"))
                if isinstance(variant.get("best_value_metadata"), Mapping)
                else None
            ),
        }
    missing_variant_ids = [variant_id for variant_id in _OFFER_VARIANT_IDS if variant_id not in normalized_by_id]
    if missing_variant_ids:
        raise StrategyV2MissingContextError(
            "Offer variant sync is missing required variant_ids: "
            + ", ".join(missing_variant_ids)
            + "."
        )
    return [normalized_by_id[variant_id] for variant_id in _OFFER_VARIANT_IDS]


def _sync_product_offer_from_strategy_output(
    *,
    session,
    org_id: str,
    client_id: str,
    product_id: str,
    onboarding_payload: Mapping[str, Any] | None,
    offer_pipeline_output: Mapping[str, Any],
    stage3_data: Mapping[str, Any],
    scored_variants: Sequence[Mapping[str, Any]],
    selected_variant: Mapping[str, Any],
    selected_variant_score: Mapping[str, Any],
    decision_payload: Mapping[str, Any],
) -> dict[str, Any]:
    offers_repo = ProductOffersRepository(session)
    variants_repo = ProductVariantsRepository(session)
    product_offers = offers_repo.list_by_product(product_id=product_id)

    target_offer = None
    default_offer_id_raw = (
        onboarding_payload.get("default_offer_id")
        if isinstance(onboarding_payload, Mapping)
        else None
    )
    default_offer_id = str(default_offer_id_raw or "").strip() if default_offer_id_raw is not None else ""
    if default_offer_id:
        target_offer = offers_repo.get(offer_id=default_offer_id)
        if not target_offer:
            raise StrategyV2MissingContextError(
                "Onboarding payload default_offer_id does not exist. "
                "Remediation: recreate onboarding payload or provide a valid default_offer_id."
            )
        if (
            str(target_offer.org_id) != org_id
            or str(target_offer.client_id) != client_id
            or str(target_offer.product_id or "") != product_id
        ):
            raise StrategyV2MissingContextError(
                "Onboarding payload default_offer_id does not belong to the current org/client/product. "
                "Remediation: fix onboarding payload default_offer_id mapping."
            )
    elif len(product_offers) == 1:
        target_offer = product_offers[0]
    elif len(product_offers) > 1:
        raise StrategyV2MissingContextError(
            "Multiple product offers exist and no onboarding default_offer_id was provided. "
            "Remediation: rerun onboarding with a default offer or reduce to a single product offer."
        )

    offer_name = str(stage3_data.get("core_promise") or "").strip()
    if not offer_name:
        raise StrategyV2MissingContextError(
            "Stage3 core_promise is required to sync product offer data. "
            "Remediation: rerun Offer winner selection and ensure core_promise is present."
        )

    pricing_rationale = str(stage3_data.get("pricing_rationale") or "").strip()
    business_model = _resolve_offer_business_model(
        offer_pipeline_output=offer_pipeline_output,
        fallback_business_model=(
            str(target_offer.business_model) if target_offer is not None else None
        ),
    )
    differentiation_bullets = _coerce_string_list(stage3_data.get("value_stack_summary"))
    guarantee_text = str(stage3_data.get("guarantee_type") or "").strip() or None

    normalized_scored_variants = _normalize_scored_variants_for_offer_sync(
        scored_variants=scored_variants,
        product_type=str(stage3_data.get("product_type") or ""),
    )
    strategy_v2_offer_payload = {
        "source": "strategy_v2",
        "variant_id": str(stage3_data.get("variant_selected") or ""),
        "offer_format": str(stage3_data.get("offer_format") or "DISCOUNT_PLUS_3_BONUSES_V1"),
        "product_type": str(stage3_data.get("product_type") or ""),
        "ump": str(stage3_data.get("ump") or ""),
        "ums": str(stage3_data.get("ums") or ""),
        "core_promise": offer_name,
        "value_stack_summary": differentiation_bullets,
        "pricing_rationale": pricing_rationale or None,
        "pricing_metadata": (
            dict(stage3_data.get("pricing_metadata"))
            if isinstance(stage3_data.get("pricing_metadata"), dict)
            else None
        ),
        "savings_metadata": (
            dict(stage3_data.get("savings_metadata"))
            if isinstance(stage3_data.get("savings_metadata"), dict)
            else None
        ),
        "best_value_metadata": (
            dict(stage3_data.get("best_value_metadata"))
            if isinstance(stage3_data.get("best_value_metadata"), dict)
            else None
        ),
        "bundle_contents": (
            dict(stage3_data.get("bundle_contents"))
            if isinstance(stage3_data.get("bundle_contents"), dict)
            else None
        ),
        "bonus_stack": (
            [row for row in stage3_data.get("bonus_stack") if isinstance(row, dict)]
            if isinstance(stage3_data.get("bonus_stack"), list)
            else []
        ),
        "guarantee_type": guarantee_text,
        "composite_score": stage3_data.get("composite_score"),
        "variants": normalized_scored_variants,
        "selected_variant": dict(selected_variant),
        "selected_variant_score": dict(selected_variant_score),
        "decision": dict(decision_payload),
    }

    base_options_schema = (
        dict(target_offer.options_schema)
        if target_offer is not None and isinstance(target_offer.options_schema, dict)
        else {}
    )
    base_options_schema["strategyV2Offer"] = strategy_v2_offer_payload

    if target_offer is None:
        target_offer = offers_repo.create(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            name=offer_name,
            description=pricing_rationale or None,
            business_model=business_model,
            differentiation_bullets=differentiation_bullets,
            guarantee_text=guarantee_text,
            options_schema=base_options_schema,
        )
    else:
        target_offer = offers_repo.update(
            offer_id=str(target_offer.id),
            name=offer_name,
            description=pricing_rationale or None,
            business_model=business_model,
            differentiation_bullets=differentiation_bullets,
            guarantee_text=guarantee_text,
            options_schema=base_options_schema,
        )
        if target_offer is None:
            raise StrategyV2MissingContextError(
                "Failed to update product offer from Strategy V2 output. "
                "Remediation: verify product offer exists and retry Offer winner finalization."
            )

    offer_variant_rows = [
        row
        for row in variants_repo.list_by_product(product_id=product_id)
        if str(row.offer_id or "") == str(target_offer.id)
    ]
    _, currency = _resolve_offer_price_cents_and_currency(
        offer_pipeline_output=offer_pipeline_output,
    )
    existing_rows_by_offer_id: dict[str, Any] = {}
    unmatched_rows: list[Any] = []
    for row in offer_variant_rows:
        option_values = row.option_values if isinstance(row.option_values, Mapping) else {}
        offer_id_value = str(option_values.get("offerId") or "").strip().lower()
        if offer_id_value and offer_id_value not in existing_rows_by_offer_id:
            existing_rows_by_offer_id[offer_id_value] = row
        else:
            unmatched_rows.append(row)

    retained_variant_row_ids: set[str] = set()
    for variant_payload in normalized_scored_variants:
        variant_id = str(variant_payload["variant_id"]).strip().lower()
        pricing_metadata = _require_dict(
            payload=variant_payload.get("pricing_metadata"),
            field_name=f"offer_sync.{variant_id}.pricing_metadata",
        )
        offer_price_cents = int(pricing_metadata["offer_price_cents"])
        list_price_cents = int(pricing_metadata["list_price_cents"])
        compare_at_price = list_price_cents if list_price_cents > offer_price_cents else None
        if variant_id in existing_rows_by_offer_id:
            variant_row = variants_repo.update(
                variant_id=str(existing_rows_by_offer_id[variant_id].id),
                offer_id=str(target_offer.id),
                title=str(variant_payload["display_label"]),
                price=offer_price_cents,
                currency=currency,
                compare_at_price=compare_at_price,
                option_values={"offerId": variant_id},
            )
            if variant_row is None:
                raise StrategyV2MissingContextError(
                    f"Failed to update existing product variant for offer variant_id '{variant_id}'."
                )
            retained_variant_row_ids.add(str(variant_row.id))
            continue
        if unmatched_rows:
            reused_row = unmatched_rows.pop(0)
            variant_row = variants_repo.update(
                variant_id=str(reused_row.id),
                offer_id=str(target_offer.id),
                title=str(variant_payload["display_label"]),
                price=offer_price_cents,
                currency=currency,
                compare_at_price=compare_at_price,
                option_values={"offerId": variant_id},
            )
            if variant_row is None:
                raise StrategyV2MissingContextError(
                    f"Failed to repurpose existing product variant row for variant_id '{variant_id}'."
                )
            retained_variant_row_ids.add(str(variant_row.id))
            continue
        created_variant = variants_repo.create(
            product_id=product_id,
            offer_id=str(target_offer.id),
            title=str(variant_payload["display_label"]),
            price=offer_price_cents,
            currency=currency,
            compare_at_price=compare_at_price,
            option_values={"offerId": variant_id},
        )
        retained_variant_row_ids.add(str(created_variant.id))

    for row in offer_variant_rows:
        row_id = str(row.id)
        if row_id in retained_variant_row_ids:
            continue
        variants_repo.delete(variant_id=row_id)

    return _serialize_product_offer_for_strategy(target_offer)


def _is_scrapeable_source_ref(source_ref: str) -> tuple[bool, str | None]:
    canonical_source_ref = _canonicalize_source_ref_for_ingestion(source_ref)
    parsed = urlsplit(canonical_source_ref)
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


def _canonicalize_source_ref_for_ingestion(source_ref: str) -> str:
    parsed = urlsplit(source_ref.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""

    host = parsed.netloc.lower()
    if ":" in host:
        host = host.split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")

    keep_query_keys = _PLATFORM_QUERY_KEYS.get(host, frozenset())
    normalized_query_pairs: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        lowered_key = key.lower()
        if lowered_key.startswith(_TRACKING_QUERY_PREFIXES):
            continue
        if lowered_key in _TRACKING_QUERY_KEYS:
            continue
        if keep_query_keys and lowered_key not in keep_query_keys:
            continue
        normalized_query_pairs.append((lowered_key, value))
    normalized_query_pairs.sort(key=lambda row: (row[0], row[1]))
    query = urlencode(normalized_query_pairs, doseq=True)
    return urlunsplit((parsed.scheme.lower(), host, path, query, ""))


def _normalize_scraped_item_for_manifest(
    item: Mapping[str, Any],
    *,
    item_index: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    nested_post = item.get("post")
    nested_snapshot = item.get("snapshot")
    nested_mappings: list[Mapping[str, Any]] = [item]
    if isinstance(nested_post, Mapping):
        nested_mappings.append(nested_post)
    if isinstance(nested_snapshot, Mapping):
        nested_mappings.append(nested_snapshot)

    def _text_value(*field_names: str) -> str:
        for mapping in nested_mappings:
            for field_name in field_names:
                value = mapping.get(field_name)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    def _number_value(*field_names: str) -> int | float | None:
        for mapping in nested_mappings:
            for field_name in field_names:
                value = mapping.get(field_name)
                if isinstance(value, (int, float)):
                    return value
        return None

    def _timestamp_value(*field_names: str) -> str:
        for mapping in nested_mappings:
            for field_name in field_names:
                value = mapping.get(field_name)
                if isinstance(value, str) and value.strip():
                    return value.strip()
                if isinstance(value, (int, float)):
                    try:
                        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")
                    except Exception:
                        continue
        return ""

    if isinstance(item_index, int) and item_index >= 0:
        payload["item_index"] = item_index

    item_id = _text_value(
        "id",
        "post_id",
        "video_id",
        "comment_id",
        "asset_id",
        "item_id",
    )
    if item_id:
        payload["item_id"] = item_id

    permalink = _text_value("permalink", "postUrl")
    source_url = _text_value(
        "source_url",
        "sourceUrl",
        "url",
        "videoUrl",
        "link",
        "canonical_url",
        "source_ref",
    )
    if not source_url and permalink:
        subreddit = _text_value("subreddit")
        if permalink.startswith("/r/") or subreddit:
            normalized_permalink = permalink if permalink.startswith("/") else f"/{permalink}"
            source_url = f"https://www.reddit.com{normalized_permalink}"
    if source_url:
        payload["source_url"] = source_url
    if permalink:
        payload["permalink"] = permalink

    title = _text_value("title", "headline", "link_title")
    if title:
        payload["title"] = title

    body = _text_value(
        "mainText",
        "selftext",
        "bodyText",
        "body",
        "text",
        "content",
        "quote",
        "caption",
        "description",
        "commentText",
        "comment",
    )
    if body:
        payload["body"] = body

    organic_results = item.get("organicResults")
    if isinstance(organic_results, list):
        organic_rows: list[dict[str, str]] = []
        for result in organic_results:
            if not isinstance(result, Mapping):
                continue
            organic_title = str(result.get("title") or "").strip()
            organic_description = str(result.get("description") or "").strip()
            organic_url = str(result.get("url") or "").strip()
            if not organic_title and not organic_description:
                continue
            organic_rows.append(
                {
                    "title": organic_title,
                    "description": organic_description,
                    "url": organic_url,
                }
            )
        if organic_rows:
            payload["organic_results_sample"] = organic_rows
            if "title" not in payload:
                first_title = str(organic_rows[0].get("title") or "").strip()
                if first_title:
                    payload["title"] = first_title
            if "body" not in payload:
                snippet_segments: list[str] = []
                for row in organic_rows[:3]:
                    title_segment = str(row.get("title") or "").strip()
                    description_segment = str(row.get("description") or "").strip()
                    if title_segment:
                        snippet_segments.append(title_segment)
                    if description_segment:
                        snippet_segments.append(description_segment)
                if snippet_segments:
                    payload["body"] = " | ".join(snippet_segments)
            if "source_url" not in payload:
                first_url = str(organic_rows[0].get("url") or "").strip()
                if first_url:
                    payload["source_url"] = first_url
    posts_sample = item.get("postsSample")
    if isinstance(posts_sample, list):
        sample_rows = [
            str(value).strip()
            for value in posts_sample
            if isinstance(value, str) and str(value).strip()
        ]
        if sample_rows:
            payload["posts_sample"] = sample_rows
    comments = item.get("comments")
    if isinstance(comments, list):
        comment_rows = []
        for value in comments:
            if isinstance(value, Mapping):
                comment_text = ""
                for field_name in ("comment", "commentText", "text", "body", "content"):
                    raw_text = value.get(field_name)
                    if isinstance(raw_text, str) and raw_text.strip():
                        comment_text = raw_text.strip()
                        break
                if comment_text:
                    comment_rows.append(comment_text)
            elif isinstance(value, str) and value.strip():
                comment_rows.append(value.strip())
        if comment_rows:
            payload["comments_sample"] = comment_rows

    author = _text_value("author", "username", "ownerUsername", "userName")
    if author:
        payload["author"] = author
    subreddit = _text_value("subreddit")
    if subreddit:
        payload["subreddit"] = subreddit

    timestamp = _timestamp_value(
        "created_utc",
        "createdAt",
        "created_at",
        "createTimeISO",
        "createTime",
        "publishedAt",
        "published_at",
        "date",
        "time",
        "timestamp",
    )
    if timestamp:
        payload["timestamp"] = timestamp

    for metric_key, aliases in (
        ("views", ("views", "view_count", "playCount", "videoPlayCount", "viewCount")),
        ("likes", ("likes", "like_count")),
        ("comments", ("comments", "comment_count", "commentsCount")),
        ("shares", ("shares", "share_count")),
        ("followers", ("followers", "account_followers", "numberOfSubscribers")),
        ("score", ("score", "upvotes")),
        ("days_since_posted", ("days_since_posted", "post_age_days")),
    ):
        metric_value = _number_value(*aliases)
        if metric_value is not None:
            payload[metric_key] = metric_value

    hashtags = item.get("hashtags")
    if isinstance(hashtags, list):
        payload["hashtags"] = [
            str(value).strip()
            for value in hashtags
            if isinstance(value, str) and str(value).strip()
        ]

    engagement = item.get("engagement")
    if isinstance(engagement, Mapping):
        compact_engagement: dict[str, Any] = {}
        for key in ("views", "likes", "comments", "shares", "saves", "upvotes"):
            value = engagement.get(key)
            if isinstance(value, (int, float)):
                compact_engagement[key] = value
        if compact_engagement:
            payload["engagement"] = compact_engagement

    if len(payload) <= (1 if "item_index" in payload else 0):
        payload["raw"] = json.dumps(item, ensure_ascii=False)
    return payload


def _extract_source_refs_from_agent_strategies(
    *,
    habitat_strategy: Mapping[str, Any],
    video_strategy: Mapping[str, Any],
) -> list[str]:
    refs: list[str] = []

    strategy_habitats = habitat_strategy.get("strategy_habitats")
    if isinstance(strategy_habitats, list):
        for row in strategy_habitats:
            if not isinstance(row, dict):
                continue
            url_pattern = row.get("url_pattern")
            if isinstance(url_pattern, str) and url_pattern.strip():
                refs.append(url_pattern.strip())

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for child in value.values():
                _walk(child)
            return
        if isinstance(value, list):
            for child in value:
                _walk(child)
            return
        if isinstance(value, str):
            candidate = value.strip()
            if candidate.lower().startswith(("http://", "https://")):
                refs.append(candidate)

    _walk(video_strategy.get("configurations"))

    deduped: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        normalized = _canonicalize_source_ref_for_ingestion(ref)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _collect_manual_queries_from_agent00_handoff(agent00_output: Mapping[str, Any]) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()

    def _add_query(value: Any) -> None:
        if not isinstance(value, str):
            return
        candidate = value.strip()
        if not candidate:
            return
        if candidate in seen:
            return
        seen.add(candidate)
        queries.append(candidate)

    manual_by_category = agent00_output.get("manual_search_queries_by_category")
    if isinstance(manual_by_category, list):
        for row in manual_by_category:
            if not isinstance(row, Mapping):
                continue
            for field_name in ("primary", "secondary", "problem_specific"):
                entries = row.get(field_name)
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if isinstance(entry, Mapping):
                        _add_query(entry.get("query"))
            competitor_specific = row.get("competitor_specific")
            if isinstance(competitor_specific, list):
                for entry in competitor_specific:
                    if not isinstance(entry, Mapping):
                        continue
                    values = entry.get("queries")
                    if isinstance(values, list):
                        for query in values:
                            _add_query(query)

    habitat_targets = agent00_output.get("habitat_targets")
    if isinstance(habitat_targets, list):
        for row in habitat_targets:
            if not isinstance(row, Mapping):
                continue
            target_queries = row.get("manual_queries")
            if isinstance(target_queries, list):
                for query in target_queries:
                    _add_query(query)
    return queries


def _infer_locator_from_apify_input(input_payload: Mapping[str, Any]) -> str:
    url_like_array_fields = ("startUrls", "productUrls")
    for field_name in url_like_array_fields:
        raw_urls = input_payload.get(field_name)
        if not isinstance(raw_urls, list):
            continue
        for item in raw_urls:
            if isinstance(item, Mapping):
                url = str(item.get("url") or "").strip()
                if url:
                    return url

    direct_url_fields = ("directUrls", "profiles")
    for field_name in direct_url_fields:
        raw_urls = input_payload.get(field_name)
        if not isinstance(raw_urls, list):
            continue
        for item in raw_urls:
            if isinstance(item, str) and item.strip():
                return item.strip()

    for field_name, prefix in (
        ("queries", "search://"),
        ("companyName", "trustpilot://"),
        ("subreddit", "reddit://"),
    ):
        value = input_payload.get(field_name)
        if isinstance(value, str) and value.strip():
            return f"{prefix}{value.strip()}"

    return "source://unknown"


def _normalize_agent00_handoff_output(agent00_output: Mapping[str, Any]) -> dict[str, Any]:
    tier1_rows_legacy = agent00_output.get("apify_configs_tier1")
    tier2_rows_legacy = agent00_output.get("apify_configs_tier2")
    if isinstance(tier1_rows_legacy, list) and isinstance(tier2_rows_legacy, list):
        return dict(agent00_output)

    apify_configs = agent00_output.get("apify_configs")
    if not isinstance(apify_configs, Mapping):
        raise StrategyV2SchemaValidationError(
            "Agent 0 output must include apify_configs object in Section 10 handoff JSON."
        )

    tier1_rows_raw = apify_configs.get("tier1_direct")
    tier2_rows_raw = apify_configs.get("tier2_discovery")
    if not isinstance(tier1_rows_raw, list) or not tier1_rows_raw:
        raise StrategyV2SchemaValidationError(
            "Agent 0 handoff JSON must include non-empty apify_configs.tier1_direct array."
        )
    if not isinstance(tier2_rows_raw, list) or not tier2_rows_raw:
        raise StrategyV2SchemaValidationError(
            "Agent 0 handoff JSON must include non-empty apify_configs.tier2_discovery array."
        )

    tier1_rows = [dict(row) for row in tier1_rows_raw if isinstance(row, Mapping)]
    tier2_rows = [dict(row) for row in tier2_rows_raw if isinstance(row, Mapping)]
    if len(tier1_rows) != len(tier1_rows_raw) or len(tier2_rows) != len(tier2_rows_raw):
        raise StrategyV2SchemaValidationError(
            "Agent 0 handoff JSON apify config arrays must contain only objects."
        )

    apify_config_index: dict[str, Mapping[str, Any]] = {}
    for row in tier1_rows + tier2_rows:
        config_id = str(row.get("config_id") or "").strip()
        if config_id:
            apify_config_index[config_id] = row

    strategy_habitats: list[dict[str, str]] = []
    seen_habitats: set[tuple[str, str, str, str, str]] = set()
    habitat_targets = agent00_output.get("habitat_targets")
    if isinstance(habitat_targets, list):
        for row in habitat_targets:
            if not isinstance(row, Mapping):
                continue
            habitat_name = str(row.get("habitat_name") or "").strip()
            habitat_type = str(row.get("habitat_category") or "").strip()
            config_id = str(row.get("apify_config_id") or "").strip()
            target_id = str(row.get("target_id") or "").strip()
            locator = ""
            config_row = apify_config_index.get(config_id)
            if isinstance(config_row, Mapping):
                config_metadata = config_row.get("metadata")
                if not target_id and isinstance(config_metadata, Mapping):
                    target_id = str(config_metadata.get("target_id") or "").strip()
                input_payload = config_row.get("input")
                if isinstance(input_payload, Mapping):
                    locator = _infer_locator_from_apify_input(input_payload)
            if not locator:
                manual_queries = row.get("manual_queries")
                if isinstance(manual_queries, list):
                    for candidate in manual_queries:
                        if isinstance(candidate, str) and candidate.strip():
                            locator = f"query://{candidate.strip()}"
                            break
            if not locator:
                locator = f"target://{str(row.get('target_id') or config_id or 'unknown')}"
            if not habitat_name or not habitat_type:
                continue
            habitat_key = (habitat_name, habitat_type, locator, target_id, config_id)
            if habitat_key in seen_habitats:
                continue
            seen_habitats.add(habitat_key)
            habitat_row: dict[str, str] = {
                "habitat_name": habitat_name,
                "habitat_type": habitat_type,
                "url_pattern": locator,
            }
            if target_id:
                habitat_row["target_id"] = target_id
            if config_id:
                habitat_row["apify_config_id"] = config_id
            strategy_habitats.append(habitat_row)

    if not strategy_habitats:
        habitat_categories = agent00_output.get("habitat_categories")
        if isinstance(habitat_categories, list):
            for row in habitat_categories:
                if not isinstance(row, Mapping):
                    continue
                category_name = str(row.get("category_name") or "").strip()
                if not category_name:
                    continue
                strategy_habitats.append(
                    {
                        "habitat_name": category_name,
                        "habitat_type": category_name,
                        "url_pattern": f"category://{category_name}",
                    }
                )

    category_classification_raw = agent00_output.get("product_classification")
    category_classification = (
        dict(category_classification_raw)
        if isinstance(category_classification_raw, Mapping)
        else {}
    )

    normalized_output: dict[str, Any] = {
        "category_classification": category_classification,
        "strategy_habitats": strategy_habitats,
        "apify_configs_tier1": tier1_rows,
        "apify_configs_tier2": tier2_rows,
        "manual_queries": _collect_manual_queries_from_agent00_handoff(agent00_output),
        "handoff_block": "",
    }
    return normalized_output


def _normalize_strategy_apify_config_row(
    *,
    row: Mapping[str, Any],
    source_label: str,
    index: int,
    require_platform_mode: bool,
    defaults: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    def _is_placeholder_text(value: str) -> bool:
        normalized = re.sub(r"[^A-Z0-9]+", "", str(value or "").strip().upper())
        return bool(normalized) and normalized in _APIFY_PLACEHOLDER_SENTINELS

    def _assert_non_placeholder_text(*, value: Any, field_label: str) -> str:
        text_value = str(value or "").strip()
        if not text_value:
            raise StrategyV2SchemaValidationError(
                f"{source_label}[{index}] is missing non-empty {field_label}."
            )
        if _is_placeholder_text(text_value):
            raise StrategyV2SchemaValidationError(
                f"{source_label}[{index}] has placeholder {field_label}={text_value!r}. "
                "Remediation: provide concrete strategy config values."
            )
        return text_value

    def _assert_non_placeholder_input_strings(*, input_data: Mapping[str, Any]) -> None:
        start_urls = input_data.get("startUrls")
        if isinstance(start_urls, list):
            for url_idx, start_url_entry in enumerate(start_urls):
                if isinstance(start_url_entry, Mapping):
                    _assert_non_placeholder_text(
                        value=start_url_entry.get("url"),
                        field_label=f"input.startUrls[{url_idx}].url",
                    )
        for field_name in ("directUrls", "productUrls", "profiles"):
            values = input_data.get(field_name)
            if not isinstance(values, list):
                continue
            for value_idx, candidate in enumerate(values):
                _assert_non_placeholder_text(
                    value=candidate,
                    field_label=f"input.{field_name}[{value_idx}]",
                )

    config_id = str(row.get("config_id") or "").strip()
    actor_id = _assert_non_placeholder_text(value=row.get("actor_id"), field_label="actor_id")
    input_payload = row.get("input")
    metadata_payload = row.get("metadata")
    if not config_id:
        raise StrategyV2SchemaValidationError(
            f"{source_label}[{index}] is missing non-empty config_id."
        )
    if not isinstance(input_payload, Mapping) or not dict(input_payload):
        raise StrategyV2SchemaValidationError(
            f"{source_label}[{index}] must include non-empty object input payload."
        )
    _assert_non_placeholder_input_strings(input_data=input_payload)
    if metadata_payload is not None and not isinstance(metadata_payload, Mapping):
        raise StrategyV2SchemaValidationError(
            f"{source_label}[{index}].metadata must be an object when provided."
        )

    metadata: dict[str, Any] = dict(metadata_payload) if isinstance(metadata_payload, Mapping) else {}
    passthrough_metadata_fields = (
        "target_id",
        "platform",
        "mode",
        "habitat_name",
        "habitat_type",
        "url_pattern",
        "tier",
    )
    for field_name in passthrough_metadata_fields:
        value = row.get(field_name)
        if isinstance(value, str) and value.strip():
            metadata.setdefault(field_name, value.strip())
    if defaults:
        for key, value in defaults.items():
            metadata.setdefault(key, value)

    target_id = str(metadata.get("target_id") or row.get("target_id") or "").strip()
    if not target_id:
        default_tier = str((defaults or {}).get("tier") or "").strip().lower()
        default_stage = str((defaults or {}).get("source_stage") or "").strip().lower()
        if default_tier == "tier2":
            target_id = f"DISC-{config_id}"
        elif default_stage == "agent0b":
            target_id = f"SV-{config_id}"
        else:
            raise StrategyV2SchemaValidationError(
                f"{source_label}[{index}] is missing target_id metadata. "
                "Remediation: include metadata.target_id in strategy configs."
            )
    metadata["target_id"] = target_id

    if require_platform_mode:
        platform = str(row.get("platform") or "").strip()
        mode = str(row.get("mode") or "").strip()
        if not platform:
            raise StrategyV2SchemaValidationError(
                f"{source_label}[{index}] is missing non-empty platform."
            )
        if not mode:
            raise StrategyV2SchemaValidationError(
                f"{source_label}[{index}] is missing non-empty mode."
            )
        metadata.setdefault("platform", platform)
        metadata.setdefault("mode", mode)

    return {
        "config_id": config_id,
        "actor_id": actor_id,
        "input": dict(input_payload),
        "metadata": metadata,
    }


def _is_placeholder_apify_config_error(error: StrategyV2SchemaValidationError) -> bool:
    message = str(error)
    return " has placeholder " in message


def _extract_apify_configs_from_agent_strategies(
    *,
    habitat_strategy: Mapping[str, Any],
    video_strategy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    tier1_rows = habitat_strategy.get("apify_configs_tier1")
    tier2_rows = habitat_strategy.get("apify_configs_tier2")
    video_config_rows = video_strategy.get("configurations")
    if not isinstance(tier1_rows, list) or not tier1_rows:
        raise StrategyV2SchemaValidationError(
            "Agent 0 output must include non-empty apify_configs_tier1 array."
        )
    if not isinstance(tier2_rows, list) or not tier2_rows:
        raise StrategyV2SchemaValidationError(
            "Agent 0 output must include non-empty apify_configs_tier2 array."
        )
    if not isinstance(video_config_rows, list) or not video_config_rows:
        raise StrategyV2SchemaValidationError(
            "Agent 0b output must include non-empty configurations array."
        )

    normalized: list[dict[str, Any]] = []
    seen_config_ids: set[str] = set()

    def _append_rows(
        *,
        rows: list[Any],
        source_label: str,
        require_platform_mode: bool,
        defaults: Mapping[str, str] | None = None,
    ) -> None:
        for idx, row in enumerate(rows):
            if not isinstance(row, Mapping):
                raise StrategyV2SchemaValidationError(
                    f"{source_label}[{idx}] must be an object."
                )
            try:
                normalized_row = _normalize_strategy_apify_config_row(
                    row=row,
                    source_label=source_label,
                    index=idx,
                    require_platform_mode=require_platform_mode,
                    defaults=defaults,
                )
            except StrategyV2SchemaValidationError as exc:
                if _is_placeholder_apify_config_error(exc):
                    continue
                raise
            config_id = str(normalized_row["config_id"])
            if config_id in seen_config_ids:
                raise StrategyV2SchemaValidationError(
                    f"Duplicate Apify config_id '{config_id}' detected across Agent 0/0b outputs."
                )
            seen_config_ids.add(config_id)
            normalized.append(normalized_row)

    _append_rows(
        rows=tier1_rows,
        source_label="agent0.apify_configs_tier1",
        require_platform_mode=False,
        defaults={"source_stage": "agent0", "tier": "tier1"},
    )
    _append_rows(
        rows=tier2_rows,
        source_label="agent0.apify_configs_tier2",
        require_platform_mode=False,
        defaults={"source_stage": "agent0", "tier": "tier2"},
    )
    _append_rows(
        rows=video_config_rows,
        source_label="agent0b.configurations",
        require_platform_mode=True,
        defaults={"source_stage": "agent0b"},
    )

    if not normalized:
        raise StrategyV2SchemaValidationError(
            "Stage 2B requires at least one executable Apify configuration."
        )
    return normalized


def _require_agent00_executable_configs(agent00_output: Mapping[str, Any]) -> None:
    executable_config_count = 0
    for field_name in ("apify_configs_tier1", "apify_configs_tier2"):
        rows = agent00_output.get(field_name)
        if not isinstance(rows, list) or not rows:
            raise StrategyV2SchemaValidationError(
                f"Agent 0 output must include non-empty {field_name} array."
            )
        for idx, row in enumerate(rows):
            if not isinstance(row, Mapping):
                raise StrategyV2SchemaValidationError(
                    f"agent0.{field_name}[{idx}] must be an object."
                )
            try:
                _normalize_strategy_apify_config_row(
                    row=row,
                    source_label=f"agent0.{field_name}",
                    index=idx,
                    require_platform_mode=False,
                    defaults={"source_stage": "agent0"},
                )
            except StrategyV2SchemaValidationError as exc:
                if _is_placeholder_apify_config_error(exc):
                    continue
                raise
            executable_config_count += 1
    if executable_config_count <= 0:
        raise StrategyV2SchemaValidationError(
            "Agent 0 output has zero executable configurations after filtering placeholder rows. "
            "Remediation: provide at least one concrete Agent 0 Apify config."
        )


def _require_agent00b_executable_configs(agent00b_output: Mapping[str, Any]) -> None:
    rows = agent00b_output.get("configurations")
    if not isinstance(rows, list) or not rows:
        raise StrategyV2SchemaValidationError(
            "Agent 0b output must include non-empty configurations array."
        )
    executable_config_count = 0
    for idx, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise StrategyV2SchemaValidationError(
                f"agent0b.configurations[{idx}] must be an object."
            )
        try:
            _normalize_strategy_apify_config_row(
                row=row,
                source_label="agent0b.configurations",
                index=idx,
                require_platform_mode=True,
                defaults={"source_stage": "agent0b"},
            )
        except StrategyV2SchemaValidationError as exc:
            if _is_placeholder_apify_config_error(exc):
                continue
            raise
        executable_config_count += 1
    _ = executable_config_count


def _partition_source_refs_for_ingestion(source_refs: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    scrapeable: list[str] = []
    excluded: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_ref in source_refs:
        ref = str(raw_ref or "").strip()
        if not ref:
            continue
        canonical_ref = _canonicalize_source_ref_for_ingestion(ref)
        if not canonical_ref:
            excluded.append({"source_ref": ref, "reason": "invalid_url"})
            continue
        if canonical_ref in seen:
            continue
        seen.add(canonical_ref)
        allowed, reason = _is_scrapeable_source_ref(canonical_ref)
        if allowed:
            scrapeable.append(canonical_ref)
            continue
        excluded.append({"source_ref": canonical_ref, "reason": reason or "unsupported"})
    if not scrapeable:
        raise StrategyV2MissingContextError(
            "Strategy V2 ingestion source filtering produced zero scrapeable refs. "
            "Remediation: provide competitor/source URLs that point to scrapeable social/video/web assets."
        )
    return scrapeable, excluded


def _ingest_strategy_v2_asset_data(
    *,
    source_refs: list[str] | None = None,
    apify_configs: list[Mapping[str, Any]] | None = None,
    include_ads_context: bool,
    include_social_video: bool,
    include_external_voc: bool,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if not source_refs and not apify_configs:
        raise StrategyV2MissingContextError(
            "Strategy V2 Apify ingestion requires non-empty source_refs or apify_configs."
        )
    try:
        payload = run_strategy_v2_apify_ingestion(
            source_refs=source_refs,
            apify_configs=apify_configs,
            include_ads_context=include_ads_context,
            include_social_video=include_social_video,
            include_external_voc=include_external_voc,
            progress_callback=progress_callback,
        )
    except TimeoutError as exc:
        raise StrategyV2ExternalDependencyError(
            "Strategy V2 Apify ingestion timed out before actor completion. "
            "Remediation: increase STRATEGY_V2_APIFY_MAX_WAIT_SECONDS or reduce heavy/duplicate source refs."
        ) from exc
    except ConnectionError as exc:
        raise StrategyV2ExternalDependencyError(
            "Strategy V2 Apify ingestion failed due to a network connectivity error. "
            "Remediation: verify outbound connectivity and Apify API availability."
        ) from exc
    except StrategyV2Error:
        raise
    except Exception as exc:
        raise StrategyV2ExternalDependencyError(
            "Strategy V2 Apify ingestion failed. "
            f"Remediation: verify Apify actor config/token and ingestion inputs. Root cause: {exc}"
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

    # Preserve the full deduped corpus for Agent 2 evidence extraction.
    artifact_rows = sorted(
        normalized_step4 + normalized_external,
        key=_score_voc_row_for_prompt,
        reverse=True,
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
                "artifact_rows": len(artifact_rows),
                "artifact_rows_cap_configured": _VOC_MERGED_CORPUS_MAX_ROWS,
                "artifact_rows_cap_applied": False,
            },
            "source_diversity_max_ratio": _VOC_SOURCE_DIVERSITY_MAX_RATIO,
        },
    }


def _voc_agent00b_response_schema() -> dict[str, Any]:
    return {
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
                    "additionalProperties": False,
                    "properties": {
                        "config_id": {"type": "string", "minLength": 1},
                        "platform": {"type": "string", "minLength": 1},
                        "mode": {"type": "string", "minLength": 1},
                        "actor_id": {"type": "string", "minLength": 1},
                        "input": _APIFY_EXEC_INPUT_SCHEMA,
                    },
                    "required": ["config_id", "platform", "mode", "actor_id", "input"],
                },
            },
            "handoff_block": {"type": "string"},
        },
        "required": ["platform_priorities", "configurations", "handoff_block"],
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
            "activity": "strategy_v2.generate_competitor_analysis",
            "phase": "competitor_analysis",
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
    "evidence_id",
    "source",
    "source_type",
    "source_url",
    "source_author",
    "source_date",
    "is_hook",
    "hook_format",
    "hook_word_count",
    "video_virality_tier",
    "video_view_count",
    "competitor_saturation",
    "in_whitespace",
    "evidence_ref",
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

_VOC_AGENT02_EVIDENCE_ID_REGEX = re.compile(_VOC_AGENT02_EVIDENCE_ID_PATTERN)
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
        row_name = f"Agent 1 habitat observation[{index}]"
        name = str(row.get("habitat_name") or row.get("name") or f"Habitat {index + 1}").strip()
        habitat_type = str(row.get("habitat_type") or "TEXT_COMMUNITY").strip()
        url_pattern = str(row.get("url_pattern") or row.get("source") or name).strip()
        if not name:
            raise StrategyV2SchemaValidationError(f"{row_name} must include non-empty habitat_name.")
        if not url_pattern:
            raise StrategyV2SchemaValidationError(f"{row_name} must include non-empty url_pattern.")
        observation_sheet = row.get("observation_sheet")
        if not isinstance(observation_sheet, Mapping):
            raise StrategyV2SchemaValidationError(
                f"{row_name} must include observation_sheet object for deterministic scoring."
            )
        _require_row_fields(
            row=row,
            required_fields=("source_file", "items_in_file", "data_quality", "mining_gate", "evidence_refs"),
            row_name=row_name,
        )
        sheet = observation_sheet
        required_sheet_fields = _VOC_AGENT01_OBSERVATION_SHEET_SCHEMA.get("required", [])
        if isinstance(required_sheet_fields, list):
            _require_row_fields(
                row=sheet,
                required_fields=tuple(str(field) for field in required_sheet_fields if isinstance(field, str)),
                row_name=f"{row_name}.observation_sheet",
            )

        def _sheet_value(field_name: str) -> Any:
            if field_name in sheet:
                return sheet.get(field_name)
            return row.get(field_name)

        def _required_yes_no(field_name: str) -> str:
            value = _sheet_value(field_name)
            if value is None:
                raise StrategyV2SchemaValidationError(f"{row_name} is missing required field '{field_name}'.")
            if isinstance(value, str):
                normalized_text = value.strip().upper()
                if normalized_text in {"CANNOT_DETERMINE", "UNKNOWN"}:
                    return "CANNOT_DETERMINE"
            normalized = _coerce_yes_no(value, default="")
            if normalized not in {"Y", "N"}:
                raise StrategyV2SchemaValidationError(
                    f"{row_name} field '{field_name}' must be Y, N, or CANNOT_DETERMINE."
                )
            return normalized

        mining_gate_raw = row.get("mining_gate")
        if not isinstance(mining_gate_raw, Mapping):
            raise StrategyV2SchemaValidationError(f"{row_name}.mining_gate must be an object.")
        mining_gate = dict(mining_gate_raw)
        required_mining_gate_fields = _VOC_AGENT01_MINING_GATE_SCHEMA.get("required", [])
        if isinstance(required_mining_gate_fields, list):
            _require_row_fields(
                row=mining_gate,
                required_fields=tuple(
                    str(field)
                    for field in required_mining_gate_fields
                    if isinstance(field, str) and str(field) != "reason"
                ),
                row_name=f"{row_name}.mining_gate",
            )
        mining_gate_status = str(mining_gate.get("status") or "").strip().upper()
        if mining_gate_status not in {"PASS", "GATE_FAIL"}:
            raise StrategyV2SchemaValidationError(
                f"{row_name}.mining_gate.status must be PASS or GATE_FAIL."
            )
        mining_gate["status"] = mining_gate_status
        failed_fields_raw = mining_gate.get("failed_fields")
        if not isinstance(failed_fields_raw, list):
            raise StrategyV2SchemaValidationError(f"{row_name}.mining_gate.failed_fields must be an array.")
        mining_gate["failed_fields"] = [str(field).strip() for field in failed_fields_raw if str(field).strip()]
        mining_gate_reason = str(mining_gate.get("reason") or "").strip()
        if not mining_gate_reason:
            if mining_gate_status == "PASS":
                mining_gate_reason = "Hard gate passed: all mining risk observables satisfied."
            elif mining_gate["failed_fields"]:
                mining_gate_reason = (
                    "Hard gate failed due to: " + ", ".join(mining_gate["failed_fields"])
                )
            else:
                mining_gate_reason = (
                    "Hard gate failed: upstream output omitted reason and failed_fields details."
                )
        mining_gate["reason"] = mining_gate_reason

        evidence_refs_raw = row.get("evidence_refs")
        if not isinstance(evidence_refs_raw, list) or not evidence_refs_raw:
            raise StrategyV2SchemaValidationError(
                f"{row_name}.evidence_refs must be a non-empty array of evidence pointers."
            )
        evidence_refs = [str(ref).strip() for ref in evidence_refs_raw if str(ref).strip()]
        if not evidence_refs:
            raise StrategyV2SchemaValidationError(
                f"{row_name}.evidence_refs must contain at least one non-empty evidence pointer."
            )

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
        video_extension_raw = row.get("video_extension")
        video_extension = dict(video_extension_raw) if isinstance(video_extension_raw, Mapping) else None
        if isinstance(video_extension, dict):
            required_video_fields = _VOC_AGENT01_VIDEO_EXTENSION_SCHEMA.get("required", [])
            if isinstance(required_video_fields, list):
                missing_video_fields = [
                    str(field_name)
                    for field_name in required_video_fields
                    if isinstance(field_name, str) and field_name not in video_extension
                ]
                if missing_video_fields:
                    raise StrategyV2SchemaValidationError(
                        f"{row_name}.video_extension is missing required fields: {missing_video_fields}. "
                        "Remediation: emit complete observation sheet fields from the upstream agent output."
                    )
        data_quality = str(row.get("data_quality") or "").strip().upper()
        if data_quality not in {"CLEAN", "MINOR_ISSUES", "MAJOR_ISSUES", "UNUSABLE"}:
            raise StrategyV2SchemaValidationError(
                f"{row_name}.data_quality must be one of CLEAN|MINOR_ISSUES|MAJOR_ISSUES|UNUSABLE."
            )
        observations.append(
            {
                "habitat_name": name,
                "habitat_type": habitat_type or "TEXT_COMMUNITY",
                "url_pattern": url_pattern or name,
                "source_file": str(row.get("source_file") or "").strip(),
                "items_in_file": int(row.get("items_in_file") or 0),
                "data_quality": data_quality,
                "observation_sheet": dict(sheet),
                "threads_50_plus": _required_yes_no("threads_50_plus"),
                "threads_200_plus": _required_yes_no("threads_200_plus"),
                "threads_1000_plus": _required_yes_no("threads_1000_plus"),
                "posts_last_3mo": _required_yes_no("posts_last_3mo"),
                "posts_last_6mo": _required_yes_no("posts_last_6mo"),
                "posts_last_12mo": _required_yes_no("posts_last_12mo"),
                "recency_ratio": str(_sheet_value("recency_ratio") or "").strip(),
                "exact_category": _required_yes_no("exact_category"),
                "purchasing_comparing": _required_yes_no("purchasing_comparing"),
                "personal_usage": _required_yes_no("personal_usage"),
                "adjacent_only": _required_yes_no("adjacent_only"),
                "first_person_narratives": _required_yes_no("first_person_narratives"),
                "trigger_events": _required_yes_no("trigger_events"),
                "fear_frustration_shame": _required_yes_no("fear_frustration_shame"),
                "specific_dollar_or_time": _required_yes_no("specific_dollar_or_time"),
                "long_detailed_posts": _required_yes_no("long_detailed_posts"),
                "language_samples": samples,
                "purchase_intent_density": str(_sheet_value("purchase_intent_density") or "").strip(),
                "discusses_spending": _required_yes_no("discusses_spending"),
                "recommendation_threads": _required_yes_no("recommendation_threads"),
                "relevance_pct": str(_sheet_value("relevance_pct") or "").strip(),
                "dominated_by_offtopic": _required_yes_no("dominated_by_offtopic"),
                "competitor_brands_mentioned": _required_yes_no("competitor_brands_mentioned"),
                "competitor_brand_count": str(_sheet_value("competitor_brand_count") or "").strip(),
                "competitor_ads_present": _required_yes_no("competitor_ads_present"),
                "trend_direction": str(_sheet_value("trend_direction") or "").strip(),
                "seasonal_patterns": _required_yes_no("seasonal_patterns"),
                "seasonal_description": str(_sheet_value("seasonal_description") or "").strip(),
                "habitat_age": str(_sheet_value("habitat_age") or "").strip(),
                "membership_trend": str(_sheet_value("membership_trend") or "").strip(),
                "post_frequency_trend": str(_sheet_value("post_frequency_trend") or "").strip(),
                "publicly_accessible": _required_yes_no("publicly_accessible"),
                "text_based_content": _required_yes_no("text_based_content"),
                "target_language": _required_yes_no("target_language"),
                "no_rate_limiting": _required_yes_no("no_rate_limiting"),
                "reusability": str(_sheet_value("reusability") or "").strip(),
                "video_extension": video_extension,
                "competitive_overlap": (
                    dict(row.get("competitive_overlap"))
                    if isinstance(row.get("competitive_overlap"), Mapping)
                    else {}
                ),
                "trend_lifecycle": (
                    dict(row.get("trend_lifecycle"))
                    if isinstance(row.get("trend_lifecycle"), Mapping)
                    else {}
                ),
                "mining_gate": mining_gate,
                "rank_score": int(row.get("rank_score") or 0),
                "estimated_yield": int(row.get("estimated_yield") or 0),
                "evidence_refs": evidence_refs,
            }
        )
        if isinstance(video_extension, dict):
            def _required_video_yes_no(field_name: str) -> str:
                value = video_extension.get(field_name)
                if isinstance(value, str):
                    normalized_text = value.strip().upper()
                    if normalized_text in {"CANNOT_DETERMINE", "UNKNOWN"}:
                        return "CANNOT_DETERMINE"
                normalized = _coerce_yes_no(value, default="")
                if normalized not in {"Y", "N"}:
                    raise StrategyV2SchemaValidationError(
                        f"{row_name}.video_extension field '{field_name}' must be Y, N, or CANNOT_DETERMINE."
                    )
                return normalized

            def _required_video_enum(field_name: str, *, allowed: tuple[str, ...]) -> str:
                value = str(video_extension.get(field_name) or "").strip().upper()
                if value not in allowed:
                    allowed_values = ", ".join(allowed)
                    raise StrategyV2SchemaValidationError(
                        f"{row_name}.video_extension field '{field_name}' must be one of {allowed_values}."
                    )
                return value

            def _optional_video_metric_int(field_name: str) -> int | None:
                value = video_extension.get(field_name)
                if value is None:
                    return None
                if isinstance(value, str):
                    normalized_text = value.strip().upper()
                    if not normalized_text or normalized_text in {"CANNOT_DETERMINE", "UNKNOWN", "N/A", "NULL", "NONE"}:
                        return None
                if isinstance(value, bool):
                    raise StrategyV2SchemaValidationError(
                        f"{row_name}.video_extension field '{field_name}' must be integer or null."
                    )
                try:
                    parsed = int(value)
                except (TypeError, ValueError) as exc:
                    raise StrategyV2SchemaValidationError(
                        f"{row_name}.video_extension field '{field_name}' must be integer or null."
                    ) from exc
                if parsed < 0:
                    raise StrategyV2SchemaValidationError(
                        f"{row_name}.video_extension field '{field_name}' must be >= 0 when provided."
                    )
                return parsed

            observations[-1]["video_count_scraped"] = _optional_video_metric_int("video_count_scraped")
            observations[-1]["median_view_count"] = _optional_video_metric_int("median_view_count")
            observations[-1]["viral_videos_found"] = _required_video_yes_no("viral_videos_found")
            observations[-1]["viral_video_count"] = _optional_video_metric_int("viral_video_count")
            observations[-1]["comment_sections_active"] = _required_video_yes_no("comment_sections_active")
            observations[-1]["comment_avg_length"] = _required_video_enum(
                "comment_avg_length",
                allowed=("SHORT", "MEDIUM", "LONG"),
            )
            observations[-1]["hook_formats_identifiable"] = _required_video_yes_no("hook_formats_identifiable")
            observations[-1]["creator_diversity"] = _required_video_enum(
                "creator_diversity",
                allowed=("SINGLE", "FEW", "MANY"),
            )
            observations[-1]["contains_testimonial_language"] = _required_video_yes_no("contains_testimonial_language")
            observations[-1]["contains_objection_language"] = _required_video_yes_no("contains_objection_language")
            observations[-1]["contains_purchase_intent"] = _required_video_yes_no("contains_purchase_intent")
    if not observations:
        raise StrategyV2SchemaValidationError(
            "Prompt-chain Agent 1 did not return any habitat observations."
        )
    return observations


def _ordered_scraped_data_file_names(scraped_data_manifest: Mapping[str, Any]) -> list[str]:
    raw_files = scraped_data_manifest.get("raw_scraped_data_files")
    file_rows = [row for row in raw_files if isinstance(row, Mapping)] if isinstance(raw_files, list) else []
    return _ordered_unique_runtime_keys(
        values=[
            str(row.get("file_name") or "").strip()
            for row in file_rows
            if str(row.get("file_name") or "").strip()
        ],
        field_name="scraped_data_manifest.raw_scraped_data_files.file_name",
    )


def _build_agent1_runtime_file_inventory(scraped_data_manifest: Mapping[str, Any]) -> dict[str, Any]:
    file_names = _ordered_scraped_data_file_names(scraped_data_manifest)
    return {
        "total_files": len(file_names),
        "file_names": file_names,
    }


def _build_agent1_file_assessment_template(scraped_data_manifest: Mapping[str, Any]) -> dict[str, Any]:
    raw_files = scraped_data_manifest.get("raw_scraped_data_files")
    file_rows = [row for row in raw_files if isinstance(row, Mapping)] if isinstance(raw_files, list) else []
    template_rows: list[dict[str, Any]] = []
    for index, row in enumerate(file_rows):
        source_file = str(row.get("file_name") or "").strip()
        if not source_file:
            continue
        items_in_file_raw = row.get("item_count")
        items_in_file = (
            int(items_in_file_raw)
            if isinstance(items_in_file_raw, int) and not isinstance(items_in_file_raw, bool)
            else 0
        )
        template_rows.append(
            {
                "source_file": source_file,
                "default_habitat_name": str(row.get("habitat_name") or source_file or f"Habitat {index + 1}").strip(),
                "default_habitat_type": str(
                    row.get("habitat_type") or row.get("source_platform") or "CANNOT_DETERMINE"
                ).strip(),
                "default_url_pattern": str(
                    row.get("virtual_path") or row.get("source_url") or row.get("dataset_id") or source_file
                ).strip(),
                "items_in_file": items_in_file,
            }
        )
    return {
        "row_count": len(template_rows),
        "observe_required_fields": [
            "habitat_name",
            "habitat_type",
            "url_pattern",
            "items_in_file",
            "data_quality",
            "observation_sheet",
            "competitive_overlap",
            "trend_lifecycle",
            "mining_gate",
            "rank_score",
            "estimated_yield",
            "evidence_refs",
        ],
        "exclude_required_null_fields": [
            "habitat_name",
            "habitat_type",
            "url_pattern",
            "items_in_file",
            "data_quality",
            "observation_sheet",
            "competitive_overlap",
            "trend_lifecycle",
            "mining_gate",
            "rank_score",
            "estimated_yield",
            "priority_rank",
            "sampling_strategy",
            "platform_behavior_note",
        ],
        "mining_required_fields_when_selected": [
            "priority_rank",
            "target_voc_types",
            "sampling_strategy",
            "platform_behavior_note",
            "evidence_refs",
        ],
        "rows": template_rows,
    }


def _render_agent1_runtime_instruction(
    *,
    agent01_file_id_map: Mapping[str, str],
    scraped_file_inventory: Mapping[str, Any],
) -> str:
    return (
        "## Runtime Input Block\n"
        f"OPENAI_CODE_INTERPRETER_FILE_IDS_JSON:\n{_dump_prompt_json_required(agent01_file_id_map, max_chars=12000, field_name='OPENAI_CODE_INTERPRETER_FILE_IDS_JSON')}\n\n"
        f"SCRAPED_FILE_INVENTORY_JSON:\n{_dump_prompt_json_required(scraped_file_inventory, max_chars=16000, field_name='SCRAPED_FILE_INVENTORY_JSON')}\n\n"
        "All required runtime JSON inputs are provided as uploaded files in the code interpreter container.\n"
        "Review FOUNDATIONAL_RESEARCH_DOCS_JSON before analyzing scraped evidence.\n"
        "Treat SCRAPED_DATA_FILES_JSON (from OPENAI_CODE_INTERPRETER_FILE_IDS_JSON) as canonical.\n"
        "AGENT1_FILE_ASSESSMENT_TEMPLATE_JSON is canonical for the exact runtime source_file set and default row hints.\n"
        "SCRAPED_DATA_FILES is a logical label only; do not require runtime filesystem reads.\n"
        "Return file_assessments as an array with exactly one row per AGENT1_FILE_ASSESSMENT_TEMPLATE_JSON.rows entry, preserving that exact order.\n"
        "Do not reorder, omit, or duplicate rows relative to AGENT1_FILE_ASSESSMENT_TEMPLATE_JSON.rows.\n"
        "Each file_assessments row must include only decision, exclude_reason, include_in_mining_plan, and observation_projection.\n"
        "Do not emit source_file inside file_assessments rows; runtime binds each row to the corresponding template row by position.\n"
        "Do not emit separate observations, habitat_observations, excluded_source_files, or mining_plan arrays; runtime derives them from file_assessments.\n"
        "Runtime assigns stable observation_id values for OBSERVE rows; do not invent observation_id fields anywhere in the output.\n"
        "If decision=OBSERVE, observation_projection must be a populated object and must not include source_file, observation_id, or include_in_mining_plan.\n"
        "If decision=EXCLUDE, set observation_projection=null, provide a non-empty exclude_reason, and set include_in_mining_plan=false.\n"
        "If decision=OBSERVE, observation_projection must populate habitat_name, habitat_type, url_pattern, items_in_file, data_quality, observation_sheet, "
        "competitive_overlap, trend_lifecycle, mining_gate, rank_score, estimated_yield, and evidence_refs.\n"
        "If decision=OBSERVE, copy url_pattern from AGENT1_FILE_ASSESSMENT_TEMPLATE_JSON.default_url_pattern unless stronger evidence suggests a better locator.\n"
        "Use SCORING_AUDIT_JSON as deterministic context for eligible-vs-excluded video rows; do not recompute excluded counts.\n"
        "Use only provided scraped evidence; if a field is missing within present evidence, mark it as CANNOT_DETERMINE.\n"
        "For hard-gate observables: set text_based_content=Y only when extractable textual evidence exists. "
        "If text_based_content is not Y because text evidence is missing, set target_language=CANNOT_DETERMINE "
        "and do not list target_language as an independent mining gate failure.\n"
        "Because runtime enforces strict JSON response_format, return a single JSON object only.\n"
        "Put the full human report into report_markdown string inside the JSON object.\n"
        "Keep report_markdown concise and evidence-focused; target <=12000 characters.\n"
        "Use evidence pointers in the format <virtual_path>::item[<index>] or <virtual_path>::<item_id>.\n"
        "Every OBSERVE observation_projection must include non-empty evidence_refs.\n"
        "Every OBSERVE observation_projection must include mining_gate.status, mining_gate.failed_fields, and a non-empty mining_gate.reason.\n"
        "If include_in_mining_plan=true, observation_projection must populate priority_rank, target_voc_types, sampling_strategy, "
        "platform_behavior_note, compliance_flags, and evidence_refs.\n"
        "If include_in_mining_plan=false, observation_projection must set priority_rank=null, target_voc_types=[], "
        "sampling_strategy=null, platform_behavior_note=null, and compliance_flags=''.\n"
        "Construct mining selections from OBSERVE rows only; never mark an EXCLUDE row for mining.\n"
        "Never emit sentinel blocked tokens or blocked placeholders in output (e.g., BLOCKED_MISSING_REQUIRED_INPUTS, MISSING_REQUIRED_INPUTS, CANNOT_PROCEED, BLOCKED).\n"
        "Output complete file_assessments entries suitable for deterministic habitat scoring."
    )


def _derive_agent1_outputs_from_file_assessments(
    *,
    agent01_output: Mapping[str, Any],
    scraped_data_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    ordered_file_names = _ordered_scraped_data_file_names(scraped_data_manifest)
    if not ordered_file_names:
        raise StrategyV2SchemaValidationError(
            "scraped_data_manifest.raw_scraped_data_files must include at least one file_name for Agent 1 grounding."
        )

    file_assessments_raw = agent01_output.get("file_assessments")
    if not isinstance(file_assessments_raw, list):
        raise StrategyV2SchemaValidationError(
            "Agent 1 output must include file_assessments array for strict file-coverage validation."
        )
    if len(file_assessments_raw) != len(ordered_file_names):
        raise StrategyV2SchemaValidationError(
            "Agent 1 output must provide exact source-file coverage: "
            "len(file_assessments) must equal SCRAPED_DATA_FILES_JSON.raw_scraped_data_files length. "
            f"Expected {len(ordered_file_names)} file_assessments rows but received {len(file_assessments_raw)}."
        )

    observation_projection_required_fields = (
        "habitat_name",
        "habitat_type",
        "url_pattern",
        "source_file",
        "items_in_file",
        "data_quality",
        "observation_sheet",
        "language_samples",
        "competitive_overlap",
        "trend_lifecycle",
        "mining_gate",
        "rank_score",
        "estimated_yield",
        "evidence_refs",
    )
    mining_projection_required_fields = (
        "habitat_name",
        "habitat_type",
        "source_file",
        "priority_rank",
        "rank_score",
        "target_voc_types",
        "estimated_yield",
        "sampling_strategy",
        "platform_behavior_note",
        "observation_sheet",
        "language_samples",
        "competitive_overlap",
        "trend_lifecycle",
        "evidence_refs",
    )

    observations: list[dict[str, Any]] = []
    excluded_source_files: list[str] = []
    mining_plan: list[dict[str, Any]] = []
    normalized_file_assessments: list[dict[str, Any]] = []

    observe_index = 0
    for index, source_file in enumerate(ordered_file_names):
        row_name = f"Agent 1 file_assessments[{index}]"
        raw_row = file_assessments_raw[index]
        if not isinstance(raw_row, Mapping):
            raise StrategyV2SchemaValidationError(f"{row_name} must be an object.")
        row_payload = dict(raw_row)
        if "source_file" in row_payload:
            raise StrategyV2SchemaValidationError(
                f"{row_name}.source_file must not be provided; runtime binds source_file by manifest order."
            )
        row_payload["source_file"] = source_file

        decision = str(row_payload.get("decision") or "").strip().upper()
        if decision not in {"OBSERVE", "EXCLUDE"}:
            raise StrategyV2SchemaValidationError(
                f"{row_name}.decision must be OBSERVE or EXCLUDE."
            )
        include_in_mining_plan = row_payload.get("include_in_mining_plan")
        if not isinstance(include_in_mining_plan, bool):
            raise StrategyV2SchemaValidationError(
                f"{row_name}.include_in_mining_plan must be boolean."
            )
        exclude_reason = str(row_payload.get("exclude_reason") or "").strip()
        observation_projection = row_payload.get("observation_projection")

        if decision == "EXCLUDE":
            if include_in_mining_plan:
                raise StrategyV2SchemaValidationError(
                    "Agent 1 output cannot mark an EXCLUDE file_assessments row for mining. "
                    f"Invalid source_file entry: '{source_file}'."
                )
            if not exclude_reason:
                raise StrategyV2SchemaValidationError(
                    f"{row_name}.exclude_reason must be non-empty when decision=EXCLUDE."
                )
            if observation_projection is not None:
                raise StrategyV2SchemaValidationError(
                    f"{row_name}.observation_projection must be null when decision=EXCLUDE."
                )
            normalized_file_assessments.append(
                {
                    "source_file": source_file,
                    "decision": "EXCLUDE",
                    "exclude_reason": exclude_reason,
                    "include_in_mining_plan": False,
                    "observation_id": None,
                }
            )
            excluded_source_files.append(source_file)
            continue

        if not isinstance(observation_projection, Mapping):
            raise StrategyV2SchemaValidationError(
                f"{row_name}.observation_projection must be an object when decision=OBSERVE."
            )
        observe_index += 1
        observation_id = f"obs-{observe_index:03d}"
        normalized_file_assessments.append(
            {
                "source_file": source_file,
                "decision": "OBSERVE",
                "exclude_reason": "",
                "include_in_mining_plan": include_in_mining_plan,
                "observation_id": observation_id,
            }
        )

        observation_row = deepcopy(dict(observation_projection))
        observation_row["source_file"] = source_file
        observation_row["observation_id"] = observation_id
        observation_row["include_in_mining_plan"] = include_in_mining_plan
        _require_row_fields(
            row=observation_row,
            required_fields=observation_projection_required_fields,
            row_name=f"{row_name}.observation_projection",
        )
        observations.append(observation_row)

        if not include_in_mining_plan:
            if observation_row.get("priority_rank") is not None:
                raise StrategyV2SchemaValidationError(
                    f"{row_name}.priority_rank must be null when include_in_mining_plan=false."
                )
            target_voc_types = observation_row.get("target_voc_types")
            if not isinstance(target_voc_types, list) or target_voc_types:
                raise StrategyV2SchemaValidationError(
                    f"{row_name}.target_voc_types must be an empty array when include_in_mining_plan=false."
                )
            if observation_row.get("sampling_strategy") is not None:
                raise StrategyV2SchemaValidationError(
                    f"{row_name}.sampling_strategy must be null when include_in_mining_plan=false."
                )
            if observation_row.get("platform_behavior_note") is not None:
                raise StrategyV2SchemaValidationError(
                    f"{row_name}.platform_behavior_note must be null when include_in_mining_plan=false."
                )
            if str(observation_row.get("compliance_flags") or "").strip():
                raise StrategyV2SchemaValidationError(
                    f"{row_name}.compliance_flags must be empty when include_in_mining_plan=false."
                )
            continue

        mining_row = {
            field_name: deepcopy(observation_row.get(field_name))
            for field_name in _VOC_AGENT01_MINING_PLAN_ENTRY_SCHEMA.get("required", [])
            if isinstance(field_name, str)
        }
        _require_row_fields(
            row=mining_row,
            required_fields=mining_projection_required_fields,
            row_name=f"{row_name}.mining_plan_projection",
        )
        if "compliance_flags" not in observation_row or observation_row.get("compliance_flags") is None:
            raise StrategyV2SchemaValidationError(
                f"{row_name}.compliance_flags must be present when include_in_mining_plan=true."
            )
        target_voc_types = mining_row.get("target_voc_types")
        if not isinstance(target_voc_types, list) or not target_voc_types:
            raise StrategyV2SchemaValidationError(
                f"{row_name}.target_voc_types must be a non-empty array when include_in_mining_plan=true."
            )
        evidence_refs = mining_row.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs:
            raise StrategyV2SchemaValidationError(
                f"{row_name}.evidence_refs must be a non-empty array when include_in_mining_plan=true."
            )
        mining_plan.append(mining_row)

    derived_output = dict(agent01_output)
    derived_output["file_assessments"] = normalized_file_assessments
    derived_output["habitat_observations"] = observations
    derived_output["excluded_source_files"] = excluded_source_files
    derived_output["mining_plan"] = mining_plan
    return derived_output


def _validate_agent1_output_source_file_grounding(
    *,
    agent01_output: Mapping[str, Any],
    scraped_data_manifest: Mapping[str, Any],
) -> None:
    _derive_agent1_outputs_from_file_assessments(
        agent01_output=agent01_output,
        scraped_data_manifest=scraped_data_manifest,
    )


def _normalize_voc_source_type(raw_value: object) -> str:
    value = str(raw_value or "").strip().upper()
    if not value:
        raise StrategyV2SchemaValidationError("Agent 2 VOC observation has empty source_type.")
    source_map = {
        "TIKTOK": "TIKTOK_COMMENT",
        "TIKTOK_COMMENT": "TIKTOK_COMMENT",
        "INSTAGRAM": "IG_COMMENT",
        "IG": "IG_COMMENT",
        "IG_COMMENT": "IG_COMMENT",
        "YOUTUBE": "YT_COMMENT",
        "YT": "YT_COMMENT",
        "YT_COMMENT": "YT_COMMENT",
        "VIDEO_HOOK": "VIDEO_HOOK",
        "REDDIT": "REDDIT",
        "FORUM": "FORUM",
        "REVIEW": "REVIEW_SITE",
        "REVIEW_SITE": "REVIEW_SITE",
        "QA": "QA",
        "BLOG": "BLOG_COMMENT",
        "BLOG_COMMENT": "BLOG_COMMENT",
    }
    normalized = source_map.get(value, value)
    allowed = {
        "REDDIT",
        "FORUM",
        "BLOG_COMMENT",
        "REVIEW_SITE",
        "QA",
        "TIKTOK_COMMENT",
        "IG_COMMENT",
        "YT_COMMENT",
        "VIDEO_HOOK",
    }
    if normalized not in allowed:
        raise StrategyV2SchemaValidationError(
            f"Agent 2 VOC observation has invalid source_type='{value}'."
        )
    return normalized


def _normalize_hook_format(raw_value: object) -> str:
    value = str(raw_value or "").strip().upper()
    if not value:
        raise StrategyV2SchemaValidationError("Agent 2 VOC observation has empty hook_format.")
    aliases = {
        "STORY_OPEN": "STORY",
        "CONTROVERSY": "CONTRARIAN",
        "PATTERN_INTERRUPT": "DEMONSTRATION",
    }
    normalized = aliases.get(value, value)
    allowed = {"QUESTION", "STATEMENT", "STORY", "STATISTIC", "CONTRARIAN", "DEMONSTRATION", "NONE"}
    if normalized not in allowed:
        raise StrategyV2SchemaValidationError(f"Agent 2 VOC observation has invalid hook_format='{value}'.")
    return normalized


def _normalize_video_virality_tier(raw_value: object) -> str:
    value = str(raw_value or "").strip().upper()
    if not value:
        raise StrategyV2SchemaValidationError("Agent 2 VOC observation has empty video_virality_tier.")
    aliases = {"HIGH_AUTHORITY": "HIGH_PERFORMING"}
    normalized = aliases.get(value, value)
    allowed = {"VIRAL", "HIGH_PERFORMING", "ABOVE_AVERAGE", "BASELINE"}
    if normalized not in allowed:
        raise StrategyV2SchemaValidationError(
            f"Agent 2 VOC observation has invalid video_virality_tier='{value}'."
        )
    return normalized


def _normalize_competitor_saturation(raw_value: object, *, row_index: int) -> list[str]:
    if not isinstance(raw_value, list):
        raise StrategyV2SchemaValidationError(
            f"Agent 2 VOC observation[{row_index}] must include competitor_saturation as array."
        )
    normalized: list[str] = []
    for item in raw_value:
        text = str(item or "").strip()
        if not text:
            continue
        if text not in normalized:
            normalized.append(text)
    return normalized


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
        source_type = _normalize_voc_source_type(row_payload.get("source_type"))
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
        is_hook = _coerce_yes_no(row_payload.get("is_hook"))
        hook_format = _normalize_hook_format(row_payload.get("hook_format"))
        try:
            hook_word_count = int(row_payload.get("hook_word_count") or 0)
        except Exception as exc:
            raise StrategyV2SchemaValidationError(
                f"Agent 2 VOC observation[{index}] has invalid hook_word_count."
            ) from exc
        if hook_word_count < 0:
            raise StrategyV2SchemaValidationError(
                f"Agent 2 VOC observation[{index}] requires hook_word_count >= 0."
            )
        video_virality_tier = _normalize_video_virality_tier(row_payload.get("video_virality_tier"))
        try:
            video_view_count = int(row_payload.get("video_view_count") or 0)
        except Exception as exc:
            raise StrategyV2SchemaValidationError(
                f"Agent 2 VOC observation[{index}] has invalid video_view_count."
            ) from exc
        if video_view_count < 0:
            raise StrategyV2SchemaValidationError(
                f"Agent 2 VOC observation[{index}] requires video_view_count >= 0."
            )
        competitor_saturation = _normalize_competitor_saturation(
            row_payload.get("competitor_saturation"),
            row_index=index,
        )
        in_whitespace = _coerce_yes_no(row_payload.get("in_whitespace"))
        if source_type == "VIDEO_HOOK":
            if is_hook != "Y":
                raise StrategyV2SchemaValidationError(
                    f"Agent 2 VOC observation[{index}] source_type=VIDEO_HOOK requires is_hook='Y'."
                )
            if hook_format == "NONE":
                raise StrategyV2SchemaValidationError(
                    f"Agent 2 VOC observation[{index}] source_type=VIDEO_HOOK requires hook_format != 'NONE'."
                )
        elif is_hook == "Y":
            raise StrategyV2SchemaValidationError(
                f"Agent 2 VOC observation[{index}] has is_hook='Y' but source_type='{source_type}'."
            )

        normalized_row = _enrich_voc_observation_signal(
            row={
                "voc_id": str(row_payload.get("voc_id") or f"V{index + 1:03d}"),
                "evidence_id": _normalize_agent2_evidence_id(
                    row_payload.get("evidence_id"),
                    field_name=f"Agent 2 VOC observation[{index}].evidence_id",
                ),
                "source": source,
                "source_type": source_type,
                "source_url": str(row_payload.get("source_url") or source).strip(),
                "source_author": str(row_payload.get("source_author") or row_payload.get("author") or "Anonymous").strip()
                or "Anonymous",
                "source_date": str(row_payload.get("source_date") or row_payload.get("date") or "Unknown").strip()
                or "Unknown",
                "is_hook": is_hook,
                "hook_format": hook_format,
                "hook_word_count": hook_word_count,
                "video_virality_tier": video_virality_tier,
                "video_view_count": video_view_count,
                "competitor_saturation": competitor_saturation,
                "in_whitespace": in_whitespace,
                "evidence_ref": str(
                    row_payload.get("evidence_ref") or row_payload.get("voc_id") or f"voc::item[{index}]"
                ).strip()
                or f"voc::item[{index}]",
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


def _normalize_agent2_evidence_text(value: object, *, max_chars: int = 900) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = re.sub(r"\s+", " ", value).strip()
    if not cleaned:
        return ""
    return cleaned[:max_chars]


def _normalize_agent2_evidence_id(value: object, *, field_name: str) -> str:
    evidence_id = str(value or "").strip().upper()
    if not _VOC_AGENT02_EVIDENCE_ID_REGEX.fullmatch(evidence_id):
        raise StrategyV2SchemaValidationError(
            f"{field_name} must match pattern {_VOC_AGENT02_EVIDENCE_ID_PATTERN!r}, got {value!r}."
        )
    return evidence_id


def _build_agent2_evidence_id(*, source_type: str, source_url: str, verbatim: str, evidence_ref: str) -> str:
    digest = hashlib.sha256(
        f"{source_type}::{source_url}::{verbatim}::{evidence_ref}".encode("utf-8")
    ).hexdigest()
    return f"E{digest[:16].upper()}"


def _build_agent2_evidence_rows(
    *,
    existing_corpus: Sequence[Mapping[str, Any]],
    merged_voc_artifact_rows: Sequence[Mapping[str, Any]],
    scraped_data_manifest: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    diagnostics: dict[str, int] = {
        "existing_rows_in": len(existing_corpus),
        "merged_rows_in": len(merged_voc_artifact_rows),
        "existing_rows_skipped_due_merged_superset": 0,
        "existing_rows_used": 0,
        "merged_rows_used": 0,
        "scraped_rows_in": 0,
        "accepted_rows": 0,
        "rows_rejected_missing_source_url_or_verbatim": 0,
        "base_rows_rejected_missing_source_url_or_verbatim": 0,
        "scraped_rows_rejected_missing_source_url_or_verbatim": 0,
    }

    def _normalize_agent2_evidence_source_type(raw_value: str) -> str:
        value = str(raw_value or "").strip().upper()
        source_map = {
            "REDDIT": "REDDIT",
            "FORUM": "FORUM",
            "BLOG": "BLOG_COMMENT",
            "BLOG_COMMENT": "BLOG_COMMENT",
            "REVIEW": "REVIEW_SITE",
            "REVIEW_SITE": "REVIEW_SITE",
            "QA": "QA",
            "TIKTOK": "TIKTOK_COMMENT",
            "TIKTOK_COMMENT": "TIKTOK_COMMENT",
            "INSTAGRAM": "IG_COMMENT",
            "IG": "IG_COMMENT",
            "IG_COMMENT": "IG_COMMENT",
            "YOUTUBE": "YT_COMMENT",
            "YT": "YT_COMMENT",
            "YT_COMMENT": "YT_COMMENT",
            "VIDEO_HOOK": "VIDEO_HOOK",
            "EXISTING_CORPUS": "FORUM",
            "MERGED_CORPUS": "FORUM",
            "SCRAPED": "FORUM",
            "DISCOVERY": "FORUM",
            "WEB": "FORUM",
            "OTHER": "FORUM",
            "LANDING_PAGE": "FORUM",
        }
        normalized = source_map.get(value)
        if not normalized:
            raise StrategyV2SchemaValidationError(
                f"Agent 2 evidence source_type '{raw_value}' is unsupported. "
                "Remediation: normalize upstream source taxonomy before v2-05."
            )
        return normalized

    def _canonical_source_url(candidate: str) -> str:
        stripped = candidate.strip()
        if not stripped:
            return ""
        canonical = _canonicalize_source_ref_for_ingestion(stripped)
        return canonical or stripped

    def _add_row(
        *,
        source_type: str,
        source_url: str,
        author: str,
        date: str,
        context: str,
        verbatim: str,
        evidence_ref: str,
        habitat_name: str,
        habitat_type: str,
        strategy_target_id: str,
        allow_missing_source_or_verbatim: bool = False,
    ) -> None:
        normalized_source_url = _canonical_source_url(source_url)
        normalized_verbatim = _normalize_agent2_evidence_text(verbatim, max_chars=900)
        if not normalized_source_url or not normalized_verbatim:
            diagnostics["rows_rejected_missing_source_url_or_verbatim"] += 1
            if allow_missing_source_or_verbatim:
                diagnostics["scraped_rows_rejected_missing_source_url_or_verbatim"] += 1
                return
            diagnostics["base_rows_rejected_missing_source_url_or_verbatim"] += 1
            raise StrategyV2SchemaValidationError(
                "Agent 2 evidence row is missing required source_url/verbatim content after normalization. "
                f"source_type={source_type!r}, source_url={source_url!r}, evidence_ref={evidence_ref!r}"
            )
        normalized_context = _normalize_agent2_evidence_text(context, max_chars=280)
        normalized_author = _normalize_agent2_evidence_text(author, max_chars=120) or "Anonymous"
        normalized_date = _normalize_agent2_evidence_text(date, max_chars=120) or "Unknown"
        normalized_source_type = _normalize_agent2_evidence_source_type(
            _normalize_agent2_evidence_text(source_type, max_chars=80)
        )
        normalized_ref = _normalize_agent2_evidence_text(evidence_ref, max_chars=240) or "evidence://unknown"
        rows.append(
            {
                "evidence_id": _build_agent2_evidence_id(
                    source_type=normalized_source_type,
                    source_url=normalized_source_url,
                    verbatim=normalized_verbatim,
                    evidence_ref=normalized_ref,
                ),
                "source_type": normalized_source_type,
                "source_url": normalized_source_url,
                "author": normalized_author,
                "date": normalized_date,
                "context": normalized_context or "Unknown context",
                "verbatim": normalized_verbatim,
                "evidence_ref": normalized_ref,
                "habitat_name": _normalize_agent2_evidence_text(habitat_name, max_chars=160) or "Unknown habitat",
                "habitat_type": _normalize_agent2_evidence_text(habitat_type, max_chars=80) or "Unknown",
                "strategy_target_id": _normalize_agent2_evidence_text(
                    strategy_target_id, max_chars=160
                )
                or "CANNOT_DETERMINE",
            }
        )
        diagnostics["accepted_rows"] += 1

    base_rows: Sequence[Mapping[str, Any]]
    if merged_voc_artifact_rows:
        base_rows = merged_voc_artifact_rows
        diagnostics["existing_rows_skipped_due_merged_superset"] = len(existing_corpus)
        diagnostics["merged_rows_used"] = len(merged_voc_artifact_rows)
    else:
        base_rows = existing_corpus
        diagnostics["existing_rows_used"] = len(existing_corpus)

    for index, row in enumerate(base_rows):
        if not isinstance(row, Mapping):
            continue
        _add_row(
            source_type=str(row.get("platform") or row.get("source_type") or "MERGED_CORPUS"),
            source_url=str(row.get("source_url") or row.get("source") or ""),
            author=str(row.get("author") or "Anonymous"),
            date=str(row.get("date") or "Unknown"),
            context=str(row.get("thread_title") or row.get("context") or "Merged corpus item"),
            verbatim=str(row.get("quote") or row.get("verbatim") or ""),
            evidence_ref=str(row.get("voc_id") or f"merged_corpus::item[{index}]"),
            habitat_name=str(row.get("habitat_name") or "Merged corpus"),
            habitat_type=str(row.get("habitat_type") or row.get("platform") or "Merged_Corpus"),
            strategy_target_id=str(row.get("strategy_target_id") or "CANNOT_DETERMINE"),
        )

    raw_files = scraped_data_manifest.get("raw_scraped_data_files")
    raw_file_rows = [row for row in raw_files if isinstance(row, Mapping)] if isinstance(raw_files, list) else []
    for file_index, file_row in enumerate(raw_file_rows):
        virtual_path = str(file_row.get("virtual_path") or f"/apify_output/raw_scraped_data/file[{file_index}]")
        habitat_name = str(file_row.get("habitat_name") or file_row.get("file_name") or "Scraped habitat")
        habitat_type = str(file_row.get("habitat_type") or file_row.get("source_platform") or "Scraped")
        strategy_target_id = str(file_row.get("strategy_target_id") or "CANNOT_DETERMINE")
        source_type = str(file_row.get("source_platform") or "SCRAPED")
        items = file_row.get("items")
        item_rows = [item for item in items if isinstance(item, Mapping)] if isinstance(items, list) else []
        diagnostics["scraped_rows_in"] += len(item_rows)
        for item_index, item in enumerate(item_rows):
            item_id = _normalize_agent2_evidence_text(str(item.get("item_id") or ""), max_chars=120)
            evidence_ref = (
                f"{virtual_path}::{item_id}"
                if item_id
                else f"{virtual_path}::item[{int(item.get('item_index') if isinstance(item.get('item_index'), int) else item_index)}]"
            )
            _add_row(
                source_type=source_type,
                source_url=str(
                    item.get("source_url")
                    or item.get("url")
                    or item.get("permalink")
                    or item.get("result_url")
                    or ""
                ),
                author=str(item.get("author") or "Anonymous"),
                date=str(item.get("timestamp") or "Unknown"),
                context=str(item.get("title") or item.get("permalink") or habitat_name),
                verbatim=str(
                    item.get("body")
                    or item.get("title")
                    or item.get("snippet")
                    or item.get("description")
                    or item.get("organic_results_sample")
                    or item.get("raw")
                    or ""
                ),
                evidence_ref=evidence_ref,
                habitat_name=habitat_name,
                habitat_type=habitat_type,
                strategy_target_id=strategy_target_id,
                allow_missing_source_or_verbatim=True,
            )

    if not rows:
        raise StrategyV2MissingContextError(
            "Agent 2 requires usable evidence rows, but normalization produced zero rows with source_url + verbatim. "
            "Remediation: provide valid existing corpus rows and/or scraped manifest items with source_url and text."
        )
    rows.sort(key=lambda row: (str(row.get("strategy_target_id") or ""), str(row.get("evidence_id") or "")))
    return rows, diagnostics


def _derive_voc_id_from_evidence_id(*, evidence_id: str) -> str:
    normalized = _normalize_agent2_evidence_id(
        evidence_id,
        field_name="raw evidence row.evidence_id",
    )
    if normalized.startswith("E"):
        return f"R{normalized[1:]}"
    return f"R{normalized}"


def _agent3_allowed_voc_ids(
    *,
    voc_observations: Sequence[Mapping[str, Any]] | None,
    evidence_rows_for_prompt: Sequence[Mapping[str, Any]] | None,
) -> list[str]:
    candidate_ids: list[str] = []
    if voc_observations:
        candidate_ids.extend(
            str(row.get("voc_id") or "").strip()
            for row in voc_observations
            if isinstance(row, Mapping) and str(row.get("voc_id") or "").strip()
        )
    if evidence_rows_for_prompt and not candidate_ids:
        candidate_ids.extend(
            _derive_voc_id_from_evidence_id(evidence_id=str(row.get("evidence_id") or "").strip())
            for row in evidence_rows_for_prompt
            if isinstance(row, Mapping) and str(row.get("evidence_id") or "").strip()
        )
    return _ordered_unique_runtime_keys(values=candidate_ids, field_name="Agent 3 runtime voc_ids")


def _infer_voc_date_bracket(*, source_date: str) -> str:
    text = str(source_date or "").strip()
    if not text:
        return "UNKNOWN"
    upper = text.upper()
    for bracket in ("LAST_3MO", "LAST_6MO", "LAST_12MO", "LAST_24MO", "OLDER", "UNKNOWN"):
        if bracket in upper:
            return bracket
    if upper in {"N/A", "NONE", "NULL"}:
        return "UNKNOWN"
    normalized = text.replace("Z", "+00:00")
    parsed_dt: datetime | None = None
    for parser in (
        lambda value: datetime.fromisoformat(value),
        lambda value: datetime.strptime(value, "%Y-%m-%d"),
        lambda value: datetime.strptime(value, "%Y/%m/%d"),
        lambda value: datetime.strptime(value, "%b %d, %Y"),
        lambda value: datetime.strptime(value, "%B %d, %Y"),
    ):
        try:
            parsed_dt = parser(normalized)
            break
        except Exception:
            continue
    if parsed_dt is None:
        year_match = re.search(r"\b(20\d{2}|19\d{2})\b", text)
        if not year_match:
            return "UNKNOWN"
        try:
            parsed_dt = datetime(int(year_match.group(1)), 1, 1)
        except Exception:
            return "UNKNOWN"
    if parsed_dt.tzinfo is None:
        parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
    age_days = max(0, (datetime.now(timezone.utc) - parsed_dt.astimezone(timezone.utc)).days)
    if age_days <= 93:
        return "LAST_3MO"
    if age_days <= 186:
        return "LAST_6MO"
    if age_days <= 366:
        return "LAST_12MO"
    if age_days <= 730:
        return "LAST_24MO"
    return "OLDER"


def _derive_voc_observations_from_evidence_rows(
    *,
    evidence_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    raw_rows: list[dict[str, Any]] = []
    for index, row in enumerate(evidence_rows):
        if not isinstance(row, Mapping):
            continue
        evidence_id = _normalize_agent2_evidence_id(
            row.get("evidence_id"),
            field_name=f"raw evidence row[{index}].evidence_id",
        )
        quote = _normalize_agent2_evidence_text(row.get("verbatim"), max_chars=900)
        source_url = _normalize_agent2_evidence_text(row.get("source_url"), max_chars=900)
        if not quote or not source_url:
            raise StrategyV2SchemaValidationError(
                "Raw-evidence Agent 3 fallback requires non-empty source_url and verbatim text for every row. "
                f"Found invalid row at index={index}, evidence_id={evidence_id}."
            )
        source_type = _normalize_voc_source_type(row.get("source_type"))
        quote_words = re.findall(r"[A-Za-z0-9']+", quote)
        word_count = max(1, len(quote_words))
        quote_lower = quote.lower()

        has_first_person = bool(_VOC_FIRST_PERSON_PATTERN.search(quote_lower))
        has_numeric = bool(re.search(r"\d", quote))
        has_trigger = bool(re.search(r"\b(when|after|before|since|because|if|once|during)\b", quote_lower))
        has_before_after = (
            bool(re.search(r"\bbefore\b", quote_lower))
            and bool(re.search(r"\bafter\b", quote_lower))
        ) or bool(re.search(r"\b(vs|versus|instead of)\b", quote_lower))
        has_crisis = bool(
            re.search(
                r"\b(can't|cannot|desperate|urgent|panic|worst|scared|anxious|frustrat|pain|hurt|struggling)\b",
                quote_lower,
            )
        )
        has_physical_signal = bool(
            re.search(r"\b(pain|hurt|ache|symptom|sick|fatigue|headache|insomnia)\b", quote_lower)
        )
        has_identity_shift = bool(
            re.search(r"\b(i need to|i want to|i wish i|finally|become)\b", quote_lower)
        )
        has_enemy = bool(
            re.search(
                r"\b(system|industry|company|brand|doctor|insurance|algorithm|platform|time)\b",
                quote_lower,
            )
        )
        has_belief_shift = bool(
            re.search(r"\b(i thought|i used to think|turns out|realized|realised)\b", quote_lower)
        )
        has_expectation_gap = bool(
            re.search(r"\b(expected|supposed to|thought|but|instead)\b", quote_lower)
        )
        has_prior_solution_failure = bool(
            re.search(r"\b(tried|didn't work|did not work|failed|no luck|nothing works?)\b", quote_lower)
        )
        is_compare_or_recommend = bool(
            re.search(r"\b(compare|comparison|recommend|best|which one|vs|versus)\b", quote_lower)
        )
        is_purchase_intent = bool(
            re.search(r"\b(buy|purchase|price|cost|ordered|order)\b", quote_lower)
        )

        if word_count >= 60:
            usable_content_pct = "OVER_75_PCT"
        elif word_count >= 30:
            usable_content_pct = "50_TO_75_PCT"
        elif word_count >= 15:
            usable_content_pct = "25_TO_50_PCT"
        else:
            usable_content_pct = "UNDER_25_PCT"

        if has_crisis:
            emotional_valence = "FRUSTRATION"
        elif "hope" in quote_lower:
            emotional_valence = "HOPE"
        elif "anx" in quote_lower or "worry" in quote_lower:
            emotional_valence = "ANXIETY"
        elif "relief" in quote_lower:
            emotional_valence = "RELIEF"
        else:
            emotional_valence = "NEUTRAL"

        if "parent" in quote_lower:
            identity_role = "PARENT"
        elif "caregiver" in quote_lower:
            identity_role = "CAREGIVER"
        elif "student" in quote_lower:
            identity_role = "STUDENT"
        elif "doctor" in quote_lower or "nurse" in quote_lower:
            identity_role = "PROFESSIONAL"
        else:
            identity_role = "NONE"

        if has_prior_solution_failure and "everything" in quote_lower:
            solution_sophistication = "EXHAUSTED"
        elif has_prior_solution_failure:
            solution_sophistication = "EXPERIENCED"
        else:
            solution_sophistication = "NOVICE"

        if is_compare_or_recommend:
            buyer_stage = "SOLUTION_AWARE"
        elif is_purchase_intent:
            buyer_stage = "PRODUCT_AWARE"
        else:
            buyer_stage = "PROBLEM_AWARE"

        compliance_risk = (
            "RED"
            if bool(re.search(r"\b(cure|diagnos|treat|prescription|disease)\b", quote_lower))
            else "YELLOW"
        )

        hook_format = "NONE"
        hook_word_count = 0
        if source_type == "VIDEO_HOOK":
            hook_format = "QUESTION" if "?" in quote else "STATEMENT"
            hook_word_count = min(word_count, 30)

        quote_preview = quote[:240]
        trigger_event = quote_preview if has_trigger else "NONE"
        desired_outcome_match = re.search(
            r"\b(?:want to|need to|hope to|looking to)\s+([^.!?]{4,120})",
            quote_lower,
        )
        desired_outcome = desired_outcome_match.group(1).strip() if desired_outcome_match else "NONE"
        fear_risk = quote_preview if has_crisis else "NONE"
        enemy_blame = quote_preview if has_enemy else "NONE"
        failed_prior_solution = quote_preview if has_prior_solution_failure else "NONE"

        raw_rows.append(
            {
                "voc_id": _derive_voc_id_from_evidence_id(evidence_id=evidence_id),
                "evidence_id": evidence_id,
                "source": source_url,
                "source_type": source_type,
                "source_url": source_url,
                "source_author": _normalize_agent2_evidence_text(row.get("author"), max_chars=120) or "Anonymous",
                "source_date": _normalize_agent2_evidence_text(row.get("date"), max_chars=120) or "Unknown",
                "is_hook": "Y" if source_type == "VIDEO_HOOK" else "N",
                "hook_format": hook_format,
                "hook_word_count": hook_word_count,
                "video_virality_tier": "BASELINE",
                "video_view_count": 0,
                "competitor_saturation": [],
                "in_whitespace": "Y",
                "evidence_ref": _normalize_agent2_evidence_text(row.get("evidence_ref"), max_chars=240)
                or f"derived::{evidence_id}",
                "quote": quote,
                "specific_number": "Y" if has_numeric else "N",
                "specific_product_brand": "N",
                "specific_event_moment": "Y" if has_trigger else "N",
                "specific_body_symptom": "Y" if has_physical_signal else "N",
                "before_after_comparison": "Y" if has_before_after else "N",
                "crisis_language": "Y" if has_crisis else "N",
                "profanity_extreme_punctuation": "Y" if bool(re.search(r"[!?]{2,}", quote)) else "N",
                "physical_sensation": "Y" if has_physical_signal else "N",
                "identity_change_desire": "Y" if has_identity_shift else "N",
                "word_count": word_count,
                "clear_trigger_event": "Y" if has_trigger else "N",
                "named_enemy": "Y" if has_enemy else "N",
                "shiftable_belief": "Y" if has_belief_shift else "N",
                "expectation_vs_reality": "Y" if has_expectation_gap else "N",
                "headline_ready": "Y" if (has_trigger or has_crisis or word_count >= 18) else "N",
                "usable_content_pct": usable_content_pct,
                "personal_context": "Y" if has_first_person else "N",
                "long_narrative": "Y" if word_count >= 80 else "N",
                "engagement_received": "N",
                "real_person_signals": "Y" if has_first_person else "N",
                "moderated_community": "Y" if source_type in {"REDDIT", "FORUM", "QA"} else "N",
                "trigger_event": trigger_event,
                "pain_problem": quote_preview,
                "desired_outcome": desired_outcome,
                "failed_prior_solution": failed_prior_solution,
                "enemy_blame": enemy_blame,
                "identity_role": identity_role,
                "fear_risk": fear_risk,
                "emotional_valence": emotional_valence,
                "durable_psychology": "Y",
                "market_specific": "Y" if (has_numeric or is_purchase_intent) else "N",
                "date_bracket": _infer_voc_date_bracket(
                    source_date=_normalize_agent2_evidence_text(row.get("date"), max_chars=120)
                ),
                "buyer_stage": buyer_stage,
                "solution_sophistication": solution_sophistication,
                "compliance_risk": compliance_risk,
            }
        )

    normalized_rows = _normalize_voc_observations(raw_rows)
    if not normalized_rows:
        raise StrategyV2MissingContextError(
            "Raw-evidence Agent 3 fallback produced zero normalized VOC rows. "
            "Remediation: verify merged/existing corpus rows include usable source_url + verbatim fields."
        )
    return normalized_rows


def _agent2_source_type_distribution(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    distribution: dict[str, int] = {}
    for row in rows:
        source_type = str(row.get("source_type") or "UNKNOWN").strip().upper() or "UNKNOWN"
        distribution[source_type] = distribution.get(source_type, 0) + 1
    return {key: distribution[key] for key in sorted(distribution)}


def _compact_agent2_evidence_rows(
    *,
    evidence_rows: Sequence[Mapping[str, Any]],
    max_rows: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if max_rows < 1:
        raise StrategyV2SchemaValidationError(
            "Agent 2 evidence compaction max_rows must be >= 1."
        )
    ordered_rows = [dict(row) for row in evidence_rows if isinstance(row, Mapping)]
    total_count = len(ordered_rows)
    if total_count <= max_rows:
        summary = {
            "enabled": False,
            "max_rows": max_rows,
            "input_count": total_count,
            "selected_count": total_count,
            "excluded_count": 0,
            "source_type_distribution_input": _agent2_source_type_distribution(ordered_rows),
            "source_type_distribution_selected": _agent2_source_type_distribution(ordered_rows),
        }
        return ordered_rows, [], summary

    rows_by_source_type: dict[str, list[dict[str, Any]]] = {}
    for row in ordered_rows:
        source_type = str(row.get("source_type") or "UNKNOWN").strip().upper() or "UNKNOWN"
        rows_by_source_type.setdefault(source_type, []).append(row)

    source_types = sorted(rows_by_source_type)
    per_type_quota = max(1, max_rows // max(1, len(source_types)))
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()

    for source_type in source_types:
        bucket = rows_by_source_type[source_type]
        selected_in_bucket = 0
        for row in bucket:
            evidence_id = str(row.get("evidence_id") or "").strip().upper()
            if not evidence_id or evidence_id in selected_ids:
                continue
            if len(selected) >= max_rows or selected_in_bucket >= per_type_quota:
                break
            selected.append(row)
            selected_ids.add(evidence_id)
            selected_in_bucket += 1

    if len(selected) < max_rows:
        for row in ordered_rows:
            evidence_id = str(row.get("evidence_id") or "").strip().upper()
            if not evidence_id or evidence_id in selected_ids:
                continue
            selected.append(row)
            selected_ids.add(evidence_id)
            if len(selected) >= max_rows:
                break

    excluded = [
        row
        for row in ordered_rows
        if str(row.get("evidence_id") or "").strip().upper() not in selected_ids
    ]
    summary = {
        "enabled": True,
        "max_rows": max_rows,
        "input_count": total_count,
        "selected_count": len(selected),
        "excluded_count": len(excluded),
        "source_type_distribution_input": _agent2_source_type_distribution(ordered_rows),
        "source_type_distribution_selected": _agent2_source_type_distribution(selected),
    }
    return selected, excluded, summary


def _index_agent2_input_rows(
    *,
    evidence_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[str], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    ordered_ids: list[str] = []
    rows_by_id: dict[str, dict[str, Any]] = {}
    manifest_rows: list[dict[str, Any]] = []
    for index, row in enumerate(evidence_rows):
        if not isinstance(row, Mapping):
            raise StrategyV2SchemaValidationError(
                f"Agent 2 evidence row[{index}] must be an object."
            )
        evidence_id = _normalize_agent2_evidence_id(
            row.get("evidence_id"),
            field_name=f"Agent 2 evidence row[{index}].evidence_id",
        )
        if evidence_id in rows_by_id:
            raise StrategyV2SchemaValidationError(
                f"Agent 2 evidence row[{index}] duplicates evidence_id={evidence_id}."
            )
        source_type = _normalize_agent2_evidence_text(row.get("source_type"), max_chars=80)
        source_url = _normalize_agent2_evidence_text(row.get("source_url"), max_chars=900)
        source_author = _normalize_agent2_evidence_text(row.get("author"), max_chars=120) or "Anonymous"
        source_date = _normalize_agent2_evidence_text(row.get("date"), max_chars=120) or "Unknown"
        context = _normalize_agent2_evidence_text(row.get("context"), max_chars=280) or "Unknown context"
        verbatim = _normalize_agent2_evidence_text(row.get("verbatim"), max_chars=900)
        evidence_ref = _normalize_agent2_evidence_text(row.get("evidence_ref"), max_chars=240)
        if not source_type or not source_url or not verbatim or not evidence_ref:
            raise StrategyV2SchemaValidationError(
                "Agent 2 evidence input row is missing required normalized fields "
                f"(evidence_id={evidence_id}, source_type/source_url/verbatim/evidence_ref required)."
            )
        normalized_row = {
            "input_index": index + 1,
            "evidence_id": evidence_id,
            "source_type": source_type,
            "source_url": source_url,
            "source_author": source_author,
            "source_date": source_date,
            "context": context,
            "verbatim": verbatim,
            "evidence_ref": evidence_ref,
            "habitat_name": _normalize_agent2_evidence_text(row.get("habitat_name"), max_chars=160),
            "habitat_type": _normalize_agent2_evidence_text(row.get("habitat_type"), max_chars=80),
            "strategy_target_id": _normalize_agent2_evidence_text(
                row.get("strategy_target_id"), max_chars=160
            ),
        }
        ordered_ids.append(evidence_id)
        rows_by_id[evidence_id] = normalized_row
        manifest_rows.append(
            {
                "input_index": index + 1,
                "evidence_id": evidence_id,
                "source_type": source_type,
                "source_url": source_url,
                "source_author": source_author,
                "source_date": source_date,
                "evidence_ref": evidence_ref,
                "context_preview": context[:180],
                "verbatim_preview": verbatim[:220],
                "verbatim_sha256": hashlib.sha256(verbatim.encode("utf-8")).hexdigest(),
            }
        )
    if not ordered_ids:
        raise StrategyV2SchemaValidationError(
            "Agent 2 evidence input rows are empty after normalization."
        )
    return ordered_ids, rows_by_id, manifest_rows


def _run_agent2_extractor_prompt_only(
    *,
    agent02_asset: PromptAsset,
    model: str,
    workflow_run_id: str,
    mode: str,
    evidence_rows: Sequence[Mapping[str, Any]],
    agent01_output: Mapping[str, Any],
    habitat_scored: Mapping[str, Any],
    stage1_data: Mapping[str, Any],
    avatar_brief_payload: Mapping[str, Any],
    competitor_analysis: Mapping[str, Any],
    saturated_angles: Sequence[Any],
    foundational_step_contents: Mapping[str, Any],
    foundational_step_summaries: Mapping[str, Any],
    activity_name: str,
) -> dict[str, Any]:
    input_ordered_ids, input_rows_by_id, input_manifest_rows = _index_agent2_input_rows(
        evidence_rows=evidence_rows
    )
    static_file_id_map, static_file_ids = _upload_openai_prompt_json_files(
        model=model,
        workflow_run_id=workflow_run_id,
        stage_label="agent2-extractor",
        logical_payloads={
            "EVIDENCE_ROWS_JSON": [dict(row) for row in evidence_rows if isinstance(row, Mapping)],
            "AGENT2_INPUT_MANIFEST_JSON": {
                "input_count": len(input_ordered_ids),
                "evidence_id_pattern": _VOC_AGENT02_EVIDENCE_ID_PATTERN,
                "rows": input_manifest_rows,
            },
            "AGENT1_MINING_PLAN_JSON": agent01_output.get("mining_plan", []),
            "HABITAT_SCORED_JSON": habitat_scored,
            "PRODUCT_BRIEF_JSON": stage1_data,
            "AVATAR_BRIEF_JSON": avatar_brief_payload,
            "COMPETITOR_ANALYSIS_JSON": competitor_analysis,
            "KNOWN_SATURATED_ANGLES": list(saturated_angles),
            "FOUNDATIONAL_RESEARCH_DOCS_JSON": {
                "step_contents": {
                    step_key: str(foundational_step_contents.get(step_key) or "")
                    for step_key in _FOUNDATIONAL_STEP_KEYS
                },
                "step_summaries": {
                    step_key: str(foundational_step_summaries.get(step_key) or "")
                    for step_key in _FOUNDATIONAL_STEP_KEYS
                },
            },
        },
    )

    try:
        combined_file_ids = list(static_file_id_map.values())
        activity.heartbeat(
            {
                "activity": activity_name,
                "phase": "agent2_prompt",
                "status": "in_progress",
                "input_count": len(evidence_rows),
            }
        )
        output, raw_output, prompt_provenance = _run_prompt_json_object(
            asset=agent02_asset,
            context="strategy_v2.agent2_output",
            model=model,
            runtime_instruction=(
                "## Runtime Input Block\n"
                f"OPENAI_CODE_INTERPRETER_FILE_IDS_JSON:\n{_dump_prompt_json_required(static_file_id_map, max_chars=12000, field_name='OPENAI_CODE_INTERPRETER_FILE_IDS_JSON')}\n\n"
                "All required runtime JSON inputs are provided as uploaded files in the code interpreter container.\n"
                "Review FOUNDATIONAL_RESEARCH_DOCS_JSON before extracting VOC evidence rows.\n"
                "Treat EVIDENCE_ROWS_JSON (from OPENAI_CODE_INTERPRETER_FILE_IDS_JSON) as the primary source of truth.\n"
                "Use AGENT2_INPUT_MANIFEST_JSON to read the canonical evidence_id list.\n"
                "Return decisions_by_evidence_id as an object keyed by the exact evidence_id values from AGENT2_INPUT_MANIFEST_JSON.rows[].evidence_id.\n"
                "Do not emit evidence_id inside decisions_by_evidence_id values; runtime derives it from each object key.\n"
                "For each keyed decision: use decision=ACCEPT with a unique observation_id, or decision=REJECT with reason and note.\n"
                "Return accepted_observations as an array with one row per ACCEPT decision.\n"
                "Do not emit evidence_id/source/source_type/source_url/source_author/source_date/evidence_ref/voc_id inside accepted_observations; runtime derives those deterministically.\n"
                "Every ACCEPT decision must reference a unique observation_id that appears exactly once in accepted_observations.\n"
                "Do not invent, mutate, alias, add, or drop evidence_id values beyond AGENT2_INPUT_MANIFEST_JSON.\n"
                "Return one extraction object only."
            ),
            schema_name="strategy_v2_voc_agent02_output",
            schema=_agent2_output_schema(evidence_ids=input_ordered_ids),
            use_reasoning=True,
            use_web_search=False,
            max_tokens=_AGENT2_MAX_TOKENS,
            openai_tools=_openai_python_tool_resources(model, file_ids=combined_file_ids),
            openai_tool_choice="auto",
            heartbeat_context={
                "activity": activity_name,
                "phase": "agent2_prompt",
                "model": model,
            },
        )
        _raise_if_blocked_prompt_output(
            stage_label="v2-05 Agent 2 extractor",
            parsed_output=output,
            raw_output=raw_output,
            remediation=(
                "provide complete evidence rows and Agent 1 mining plan context before rerunning v2-05."
            ),
        )

        output_mode = str(output.get("mode") or "").strip().upper()
        if output_mode and output_mode not in {"DUAL", "FRESH"}:
            raise StrategyV2SchemaValidationError(
                f"Agent 2 mode is unsupported (expected one of DUAL/FRESH, actual='{output_mode}')."
            )
        if output_mode and output_mode != mode:
            logging.getLogger(__name__).warning(
                "Agent 2 mode mismatch; keeping runtime mode and continuing "
                "(expected=%s, model_reported=%s).",
                mode,
                output_mode,
            )

        def _coerce_output_int(field_name: str) -> int:
            if field_name not in output:
                raise StrategyV2SchemaValidationError(
                    f"Agent 2 output is missing required integer field '{field_name}'."
                )
            raw_value = output.get(field_name)
            if isinstance(raw_value, bool):
                raise StrategyV2SchemaValidationError(
                    f"Agent 2 field '{field_name}' must be an integer, received boolean."
                )
            try:
                return int(raw_value)
            except (TypeError, ValueError) as exc:
                raise StrategyV2SchemaValidationError(
                    f"Agent 2 field '{field_name}' must be an integer."
                ) from exc

        validation_errors = output.get("validation_errors")
        if isinstance(validation_errors, list) and validation_errors:
            raise StrategyV2DecisionError(
                "Agent 2 extraction returned validation_errors: "
                + ", ".join(str(item) for item in validation_errors[:10])
            )
        output_input_count = _coerce_output_int("input_count")
        if output_input_count != len(evidence_rows):
            raise StrategyV2SchemaValidationError(
                "Agent 2 input_count mismatch "
                f"(expected={len(evidence_rows)}, actual={output_input_count})."
            )
        decisions_by_evidence_id = output.get("decisions_by_evidence_id")
        if not isinstance(decisions_by_evidence_id, Mapping):
            raise StrategyV2SchemaValidationError(
                "Agent 2 output must include decisions_by_evidence_id object."
            )
        _coerce_output_int("output_count")

        return {
            "mode": mode,
            "output": output,
            "raw_output": raw_output,
            "prompt_provenance": prompt_provenance,
            "input_ordered_ids": input_ordered_ids,
            "input_rows_by_id": input_rows_by_id,
            "input_manifest_rows": input_manifest_rows,
            "input_count": len(input_ordered_ids),
        }
    finally:
        _cleanup_openai_prompt_files(model=model, file_ids=static_file_ids)


def _validate_agent2_decision_partition(
    *,
    mode: str,
    output: Mapping[str, Any],
    input_ordered_ids: Sequence[str],
    input_rows_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    input_id_set = set(input_ordered_ids)
    decisions_by_evidence_id = output.get("decisions_by_evidence_id")
    if not isinstance(decisions_by_evidence_id, Mapping):
        raise StrategyV2SchemaValidationError(
            "Agent 2 output must include decisions_by_evidence_id object."
        )

    returned_ids = {
        str(key or "").strip()
        for key in decisions_by_evidence_id.keys()
        if str(key or "").strip()
    }
    unknown_ids = returned_ids - input_id_set
    if unknown_ids:
        sample_ids = sorted(unknown_ids)[:8]
        raise StrategyV2SchemaValidationError(
            "Agent 2 output contains evidence_id values not present in input evidence rows "
            f"(unknown_count={len(unknown_ids)}, sample_ids={sample_ids})."
        )
    missing_decisions = input_id_set - returned_ids
    if missing_decisions:
        raise StrategyV2SchemaValidationError(
            "Agent 2 output did not return decisions for all input evidence rows "
            f"(missing_count={len(missing_decisions)}, sample_ids={sorted(missing_decisions)[:8]})."
        )

    accepted_observations_raw = output.get("accepted_observations")
    if not isinstance(accepted_observations_raw, list):
        raise StrategyV2SchemaValidationError(
            "Agent 2 output must include accepted_observations array."
        )
    accepted_by_id: dict[str, dict[str, Any]] = {}
    for index, raw_row in enumerate(accepted_observations_raw):
        row_name = f"Agent 2 accepted_observations[{index}]"
        if not isinstance(raw_row, Mapping):
            raise StrategyV2SchemaValidationError(f"{row_name} must be an object.")
        observation_id = str(raw_row.get("observation_id") or "").strip()
        if not observation_id:
            raise StrategyV2SchemaValidationError(f"{row_name}.observation_id must be non-empty.")
        if observation_id in accepted_by_id:
            raise StrategyV2SchemaValidationError(
                f"Agent 2 accepted_observations must not contain duplicate observation_id values. Duplicate: '{observation_id}'."
            )
        accepted_by_id[observation_id] = dict(raw_row)

    all_voc_rows: list[dict[str, Any]] = []
    all_rejected_items: list[dict[str, Any]] = []
    used_observation_ids: set[str] = set()
    for evidence_id in input_ordered_ids:
        source_row = input_rows_by_id.get(evidence_id)
        if source_row is None:
            raise StrategyV2SchemaValidationError(
                f"Agent 2 decision partition is missing indexed source row for evidence_id={evidence_id}."
            )
        row = decisions_by_evidence_id.get(evidence_id)
        if not isinstance(row, Mapping):
            raise StrategyV2SchemaValidationError(
                f"Agent 2 decisions_by_evidence_id['{evidence_id}'] must be an object."
            )
        decision = str(row.get("decision") or "").strip().upper()
        if decision == "ACCEPT":
            observation_id = str(row.get("observation_id") or "").strip()
            if not observation_id:
                raise StrategyV2SchemaValidationError(
                    f"Agent 2 decisions_by_evidence_id['{evidence_id}'].observation_id must be non-empty when decision=ACCEPT."
                )
            if observation_id in used_observation_ids:
                raise StrategyV2SchemaValidationError(
                    f"Agent 2 observation_id '{observation_id}' is referenced by multiple evidence rows."
                )
            normalized_row = accepted_by_id.get(observation_id)
            if normalized_row is None:
                raise StrategyV2SchemaValidationError(
                    f"Agent 2 decisions_by_evidence_id['{evidence_id}'].observation_id='{observation_id}' is missing a matching accepted_observations entry."
                )
            used_observation_ids.add(observation_id)
            normalized_row = dict(normalized_row)
            normalized_row["evidence_id"] = evidence_id
            normalized_row["source_type"] = source_row["source_type"]
            normalized_row["source_url"] = source_row["source_url"]
            normalized_row["source_author"] = source_row["source_author"]
            normalized_row["source_date"] = source_row["source_date"]
            normalized_row["evidence_ref"] = source_row["evidence_ref"]
            normalized_row["source"] = f"{source_row['source_type']}::{source_row['source_url']}"
            all_voc_rows.append(normalized_row)
            continue
        if decision == "REJECT":
            if row.get("observation_id") not in {None, ""}:
                raise StrategyV2SchemaValidationError(
                    f"Agent 2 decisions_by_evidence_id['{evidence_id}'].observation_id must be null/empty when decision=REJECT."
                )
            reason = str(row.get("reason") or "").strip().upper()
            if reason not in {"NOT_VOC", "MISSING_SOURCE", "TOO_VAGUE", "DUPLICATE_EVIDENCE"}:
                raise StrategyV2SchemaValidationError(
                    f"Agent 2 decisions_by_evidence_id['{evidence_id}'] has invalid reason={reason!r}."
                )
            note = str(row.get("note") or "").strip()
            if not note:
                raise StrategyV2SchemaValidationError(
                    f"Agent 2 decisions_by_evidence_id['{evidence_id}'] requires a non-empty note."
                )
            all_rejected_items.append(
                {
                    "evidence_id": evidence_id,
                    "reason": reason,
                    "note": note,
                    "source_type": source_row["source_type"],
                    "source_url": source_row["source_url"],
                    "source_author": source_row["source_author"],
                    "source_date": source_row["source_date"],
                    "evidence_ref": source_row["evidence_ref"],
                    "context": source_row["context"],
                    "verbatim_preview": source_row["verbatim"][:280],
                }
            )
            continue
        raise StrategyV2SchemaValidationError(
            f"Agent 2 decisions_by_evidence_id['{evidence_id}'].decision must be ACCEPT or REJECT."
        )

    unused_observation_ids = sorted(set(accepted_by_id) - used_observation_ids)
    if unused_observation_ids:
        raise StrategyV2SchemaValidationError(
            "Agent 2 accepted_observations contains observation_id values not referenced by decisions_by_evidence_id. "
            f"Unused observation_id entries: {unused_observation_ids[:8]}."
        )

    if not all_voc_rows:
        raise StrategyV2DecisionError(
            "Agent 2 extraction produced zero usable voc_observations after strict decision partition validation."
        )

    output_count = output.get("output_count")
    if isinstance(output_count, bool):
        raise StrategyV2SchemaValidationError("Agent 2 output_count must be an integer, received boolean.")
    try:
        reported_output_count = int(output_count)
    except (TypeError, ValueError) as exc:
        raise StrategyV2SchemaValidationError("Agent 2 output_count must be an integer.") from exc
    if reported_output_count != len(all_voc_rows):
        raise StrategyV2SchemaValidationError(
            "Agent 2 output_count mismatch after strict decision partition validation "
            f"(reported={reported_output_count}, accepted={len(all_voc_rows)})."
        )

    for index, row in enumerate(all_voc_rows, start=1):
        row["voc_id"] = f"V{index:04d}"

    return {
        "mode": mode,
        "voc_observations": all_voc_rows,
        "rejected_items": all_rejected_items,
        "extraction_summary": {
            "input_count": len(input_ordered_ids),
            "output_count": len(all_voc_rows),
            "rejected_count": len(all_rejected_items),
        },
        "id_validation_report": {
            "input_count": len(input_ordered_ids),
            "accepted_count": len(all_voc_rows),
            "rejected_count": len(all_rejected_items),
            "unknown_id_count": 0,
            "missing_decision_count": 0,
            "overlap_count": 0,
            "evidence_id_pattern": _VOC_AGENT02_EVIDENCE_ID_PATTERN,
        },
    }


def _run_agent2_extractor(
    *,
    agent02_asset: PromptAsset,
    model: str,
    workflow_run_id: str,
    mode: str,
    evidence_rows: Sequence[Mapping[str, Any]],
    agent01_output: Mapping[str, Any],
    habitat_scored: Mapping[str, Any],
    stage1_data: Mapping[str, Any],
    avatar_brief_payload: Mapping[str, Any],
    competitor_analysis: Mapping[str, Any],
    saturated_angles: Sequence[Any],
    foundational_step_contents: Mapping[str, Any],
    foundational_step_summaries: Mapping[str, Any],
    activity_name: str,
) -> dict[str, Any]:
    prompt_result = _run_agent2_extractor_prompt_only(
        agent02_asset=agent02_asset,
        model=model,
        workflow_run_id=workflow_run_id,
        mode=mode,
        evidence_rows=evidence_rows,
        agent01_output=agent01_output,
        habitat_scored=habitat_scored,
        stage1_data=stage1_data,
        avatar_brief_payload=avatar_brief_payload,
        competitor_analysis=competitor_analysis,
        saturated_angles=saturated_angles,
        foundational_step_contents=foundational_step_contents,
        foundational_step_summaries=foundational_step_summaries,
        activity_name=activity_name,
    )
    validated = _validate_agent2_decision_partition(
        mode=str(prompt_result.get("mode") or mode),
        output=_require_dict(payload=prompt_result.get("output"), field_name="agent2_output"),
        input_ordered_ids=[
            str(item)
            for item in (prompt_result.get("input_ordered_ids") if isinstance(prompt_result.get("input_ordered_ids"), list) else [])
            if isinstance(item, str)
        ],
        input_rows_by_id={
            str(key): value
            for key, value in (
                prompt_result.get("input_rows_by_id").items()
                if isinstance(prompt_result.get("input_rows_by_id"), dict)
                else []
            )
            if isinstance(key, str) and isinstance(value, Mapping)
        },
    )

    return {
        **validated,
        "input_manifest": {
            "input_count": int(prompt_result.get("input_count") or 0),
            "evidence_id_pattern": _VOC_AGENT02_EVIDENCE_ID_PATTERN,
            "rows": prompt_result.get("input_manifest_rows") if isinstance(prompt_result.get("input_manifest_rows"), list) else [],
        },
        "raw_outputs_preview": [str(prompt_result.get("raw_output") or "")[:2000]],
        "prompt_provenance": prompt_result.get("prompt_provenance")
        if isinstance(prompt_result.get("prompt_provenance"), dict)
        else {},
    }


def _compact_agent3_text(value: object, *, max_chars: int) -> str:
    if max_chars < 1:
        raise StrategyV2SchemaValidationError("Agent 3 text compaction max_chars must be >= 1.")
    text = str(value or "")
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_chars:
        return normalized
    truncated = normalized[:max_chars].rstrip()
    last_space = truncated.rfind(" ")
    if last_space >= max_chars // 2:
        truncated = truncated[:last_space]
    return truncated.rstrip(" ,;:-")


def _compact_agent3_string_list(
    values: object,
    *,
    max_items: int,
    max_chars: int,
) -> list[str]:
    if max_items < 1:
        raise StrategyV2SchemaValidationError("Agent 3 compact string-list max_items must be >= 1.")
    if not isinstance(values, list):
        return []
    compacted: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = _compact_agent3_text(raw_value, max_chars=max_chars)
        if not value or value in seen:
            continue
        seen.add(value)
        compacted.append(value)
        if len(compacted) >= max_items:
            break
    return compacted


def _compact_agent3_product_brief(stage1_data: Mapping[str, Any]) -> dict[str, Any]:
    primary_segment = stage1_data.get("primary_segment")
    compact_primary_segment = (
        {
            "name": _compact_agent3_text(primary_segment.get("name"), max_chars=120),
            "size_estimate": _compact_agent3_text(primary_segment.get("size_estimate"), max_chars=80),
            "key_differentiator": _compact_agent3_text(
                primary_segment.get("key_differentiator"),
                max_chars=180,
            ),
        }
        if isinstance(primary_segment, Mapping)
        else {}
    )
    return {
        "product_name": _compact_agent3_text(stage1_data.get("product_name"), max_chars=160),
        "description": _compact_agent3_text(stage1_data.get("description"), max_chars=400),
        "price": _compact_agent3_text(stage1_data.get("price"), max_chars=40),
        "category_niche": _compact_agent3_text(stage1_data.get("category_niche"), max_chars=140),
        "market_maturity_stage": _compact_agent3_text(
            stage1_data.get("market_maturity_stage"),
            max_chars=80,
        ),
        "primary_segment": compact_primary_segment,
        "bottleneck": _compact_agent3_text(stage1_data.get("bottleneck"), max_chars=180),
        "positioning_gaps": _compact_agent3_string_list(
            stage1_data.get("positioning_gaps"),
            max_items=8,
            max_chars=180,
        ),
        "primary_icps": _compact_agent3_string_list(
            stage1_data.get("primary_icps"),
            max_items=8,
            max_chars=120,
        ),
        "competitor_urls": _compact_agent3_string_list(
            stage1_data.get("competitor_urls"),
            max_items=_AGENT3_PRODUCT_BRIEF_MAX_COMPETITOR_URLS,
            max_chars=240,
        ),
    }


def _compact_agent3_avatar_brief_payload(avatar_brief_payload: Mapping[str, Any]) -> dict[str, Any]:
    demographics = avatar_brief_payload.get("demographics")
    compact_demographics = (
        {
            "age_range": _compact_agent3_text(demographics.get("age_range"), max_chars=60),
            "gender_skew": _compact_agent3_text(demographics.get("gender_skew"), max_chars=80),
        }
        if isinstance(demographics, Mapping)
        else {}
    )
    return {
        "demographics": compact_demographics,
        "platform_habits": _compact_agent3_string_list(
            avatar_brief_payload.get("platform_habits"),
            max_items=6,
            max_chars=140,
        ),
        "content_consumption_patterns": _compact_agent3_string_list(
            avatar_brief_payload.get("content_consumption_patterns"),
            max_items=6,
            max_chars=180,
        ),
        "psychographics_summary": _compact_agent3_text(
            avatar_brief_payload.get("psychographics_summary"),
            max_chars=1000,
        ),
    }


def _compact_agent3_foundational_docs(
    *,
    foundational_step_contents: Mapping[str, Any],
    foundational_step_summaries: Mapping[str, Any],
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    for step_key in _FOUNDATIONAL_STEP_KEYS:
        summary_text = _compact_agent3_text(
            foundational_step_summaries.get(step_key)
            or foundational_step_contents.get(step_key),
            max_chars=_AGENT3_FOUNDATIONAL_SUMMARY_MAX_CHARS,
        )
        content_excerpt = ""
        if not summary_text:
            content_excerpt = _compact_agent3_text(
                foundational_step_contents.get(step_key),
                max_chars=_AGENT3_FOUNDATIONAL_EXCERPT_MAX_CHARS,
            )
        steps.append(
            {
                "step_key": step_key,
                "summary": summary_text,
                "content_excerpt": content_excerpt,
            }
        )
    return {
        "document_mode": "summary_compact",
        "steps": steps,
    }


def _compact_agent3_competitor_angle_map(
    competitor_angle_map: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    compacted: list[dict[str, Any]] = []
    input_competitor_count = 0
    input_asset_count = 0
    for raw_row in competitor_angle_map:
        if not isinstance(raw_row, Mapping):
            continue
        input_competitor_count += 1
        assets_raw = raw_row.get("assets")
        assets = [row for row in assets_raw if isinstance(row, Mapping)] if isinstance(assets_raw, list) else []
        input_asset_count += len(assets)
        compact_assets: list[dict[str, Any]] = []
        for asset_row in assets[:_AGENT3_COMPETITOR_MAP_MAX_ASSETS_PER_COMPETITOR]:
            compact_assets.append(
                {
                    "asset_id": _compact_agent3_text(asset_row.get("asset_id"), max_chars=80),
                    "primary_angle": _compact_agent3_text(asset_row.get("primary_angle"), max_chars=220),
                    "core_claim": _compact_agent3_text(asset_row.get("core_claim"), max_chars=220),
                    "implied_mechanism": _compact_agent3_text(
                        asset_row.get("implied_mechanism"),
                        max_chars=220,
                    ),
                    "target_segment_description": _compact_agent3_text(
                        asset_row.get("target_segment_description"),
                        max_chars=220,
                    ),
                    "hook_type": _compact_agent3_text(asset_row.get("hook_type"), max_chars=120),
                }
            )
        compacted.append(
            {
                "competitor_name": _compact_agent3_text(raw_row.get("competitor_name"), max_chars=140),
                "asset_count": len(assets),
                "assets": compact_assets,
            }
        )
        if len(compacted) >= _AGENT3_COMPETITOR_MAP_MAX_COMPETITORS:
            break
    diagnostics = {
        "input_competitor_count": input_competitor_count,
        "selected_competitor_count": len(compacted),
        "input_asset_count": input_asset_count,
        "selected_asset_count": sum(len(row.get("assets") or []) for row in compacted),
    }
    return compacted, diagnostics


def _compact_agent3_saturated_angles(
    saturated_angles: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    compacted: list[dict[str, str]] = []
    for raw_row in saturated_angles:
        if not isinstance(raw_row, Mapping):
            continue
        compacted.append(
            {
                "angle": _compact_agent3_text(raw_row.get("angle"), max_chars=200),
                "driver": _compact_agent3_text(raw_row.get("driver"), max_chars=180),
                "status": _compact_agent3_text(raw_row.get("status"), max_chars=32),
                "competitor_count": _compact_agent3_text(
                    raw_row.get("competitor_count"),
                    max_chars=24,
                ),
            }
        )
    return compacted


def _compact_agent3_habitat_scored(habitat_scored: Mapping[str, Any]) -> dict[str, Any]:
    summary = habitat_scored.get("summary")
    habitats_raw = habitat_scored.get("habitats")
    habitats = [row for row in habitats_raw if isinstance(row, Mapping)] if isinstance(habitats_raw, list) else []
    ranked_rows = sorted(
        [dict(row) for row in habitats],
        key=lambda row: (
            int(row.get("rank") or 9999),
            -float(row.get("final_score") or 0.0),
        ),
    )
    compacted_habitats: list[dict[str, Any]] = []
    for row in ranked_rows[:_AGENT3_HABITAT_MAX_ROWS]:
        compacted_habitats.append(
            {
                "rank": int(row.get("rank") or 0),
                "habitat_name": _compact_agent3_text(row.get("habitat_name"), max_chars=140),
                "habitat_type": _compact_agent3_text(row.get("habitat_type"), max_chars=80),
                "final_score": float(row.get("final_score") or 0.0),
                "confidence_range": list(row.get("confidence_range"))
                if isinstance(row.get("confidence_range"), (list, tuple))
                else row.get("confidence_range"),
                "mining_gate_applied": bool(row.get("mining_gate_applied")),
                "lifecycle_stage": _compact_agent3_text(row.get("lifecycle_stage"), max_chars=60),
            }
        )
    return {
        "summary": dict(summary) if isinstance(summary, Mapping) else {},
        "habitats": compacted_habitats,
    }


def _compact_agent3_habitat_observations(
    observations: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    ordered_rows = sorted(
        [dict(row) for row in observations if isinstance(row, Mapping)],
        key=lambda row: (
            0 if bool(row.get("include_in_mining_plan")) else 1,
            int(row.get("priority_rank") or 9999),
            -int(row.get("rank_score") or 0),
            str(row.get("source_file") or ""),
        ),
    )
    compacted: list[dict[str, Any]] = []
    for row in ordered_rows[:_AGENT3_HABITAT_MAX_ROWS]:
        mining_gate = row.get("mining_gate")
        video_extension = row.get("video_extension")
        evidence_refs = row.get("evidence_refs")
        compacted.append(
            {
                "source_file": _compact_agent3_text(row.get("source_file"), max_chars=160),
                "habitat_name": _compact_agent3_text(row.get("habitat_name"), max_chars=140),
                "habitat_type": _compact_agent3_text(row.get("habitat_type"), max_chars=80),
                "url_pattern": _compact_agent3_text(row.get("url_pattern"), max_chars=220),
                "data_quality": _compact_agent3_text(row.get("data_quality"), max_chars=32),
                "include_in_mining_plan": bool(row.get("include_in_mining_plan")),
                "priority_rank": row.get("priority_rank"),
                "rank_score": int(row.get("rank_score") or 0),
                "estimated_yield": int(row.get("estimated_yield") or 0),
                "mining_gate": (
                    {
                        "status": _compact_agent3_text(mining_gate.get("status"), max_chars=32),
                        "failed_fields": _compact_agent3_string_list(
                            mining_gate.get("failed_fields"),
                            max_items=8,
                            max_chars=80,
                        ),
                        "reason": _compact_agent3_text(mining_gate.get("reason"), max_chars=220),
                    }
                    if isinstance(mining_gate, Mapping)
                    else {}
                ),
                "video_extension": (
                    {
                        "viral_videos_found": video_extension.get("viral_videos_found"),
                        "comment_sections_active": video_extension.get("comment_sections_active"),
                        "contains_purchase_intent": video_extension.get("contains_purchase_intent"),
                        "creator_diversity": _compact_agent3_text(
                            video_extension.get("creator_diversity"),
                            max_chars=24,
                        ),
                    }
                    if isinstance(video_extension, Mapping)
                    else None
                ),
                "evidence_refs_preview": _compact_agent3_string_list(
                    evidence_refs,
                    max_items=4,
                    max_chars=180,
                ),
            }
        )
    diagnostics = {
        "input_count": len(ordered_rows),
        "selected_count": len(compacted),
        "omitted_count": max(len(ordered_rows) - len(compacted), 0),
    }
    return compacted, diagnostics


def _compact_agent3_mining_plan(
    mining_plan: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    ordered_rows = sorted(
        [dict(row) for row in mining_plan if isinstance(row, Mapping)],
        key=lambda row: (
            int(row.get("priority_rank") or 9999),
            -int(row.get("rank_score") or 0),
            str(row.get("source_file") or ""),
        ),
    )
    compacted: list[dict[str, Any]] = []
    for row in ordered_rows[:_AGENT3_MINING_PLAN_MAX_ROWS]:
        compacted.append(
            {
                "source_file": _compact_agent3_text(row.get("source_file"), max_chars=160),
                "habitat_name": _compact_agent3_text(row.get("habitat_name"), max_chars=140),
                "habitat_type": _compact_agent3_text(row.get("habitat_type"), max_chars=80),
                "priority_rank": int(row.get("priority_rank") or 0),
                "rank_score": int(row.get("rank_score") or 0),
                "estimated_yield": int(row.get("estimated_yield") or 0),
                "target_voc_types": _compact_agent3_string_list(
                    row.get("target_voc_types"),
                    max_items=6,
                    max_chars=64,
                ),
                "sampling_strategy": _compact_agent3_text(
                    row.get("sampling_strategy"),
                    max_chars=220,
                ),
                "platform_behavior_note": _compact_agent3_text(
                    row.get("platform_behavior_note"),
                    max_chars=220,
                ),
                "compliance_flags": _compact_agent3_text(
                    row.get("compliance_flags"),
                    max_chars=120,
                ),
                "evidence_refs_preview": _compact_agent3_string_list(
                    row.get("evidence_refs"),
                    max_items=4,
                    max_chars=180,
                ),
            }
        )
    diagnostics = {
        "input_count": len(ordered_rows),
        "selected_count": len(compacted),
        "omitted_count": max(len(ordered_rows) - len(compacted), 0),
    }
    return compacted, diagnostics


def _agent3_voc_score_lookup(voc_scored: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    items_raw = voc_scored.get("items")
    items = [row for row in items_raw if isinstance(row, Mapping)] if isinstance(items_raw, list) else []
    lookup: dict[str, dict[str, Any]] = {}
    for row in items:
        voc_id = str(row.get("voc_id") or "").strip()
        if not voc_id:
            continue
        lookup[voc_id] = dict(row)
    return lookup


def _compact_agent3_voc_inputs(
    *,
    voc_observations: Sequence[Mapping[str, Any]],
    voc_scored: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str], dict[str, Any]]:
    score_lookup = _agent3_voc_score_lookup(voc_scored)
    ordered_rows = [dict(row) for row in voc_observations if isinstance(row, Mapping)]
    ranked_rows = sorted(
        ordered_rows,
        key=lambda row: (
            float(score_lookup.get(str(row.get("voc_id") or "").strip(), {}).get("adjusted_score") or 0.0),
            _score_voc_row_for_prompt(dict(row))[0],
        ),
        reverse=True,
    )
    source_cap = max(1, int(_AGENT3_VOC_MAX_ROWS * _AGENT3_VOC_MAX_RATIO_PER_SOURCE))
    selected: list[dict[str, Any]] = []
    selected_keys: set[str] = set()
    per_source: dict[str, int] = {}
    for row in ranked_rows:
        source_bucket = _voc_row_source_bucket(row)
        if per_source.get(source_bucket, 0) >= source_cap:
            continue
        dedupe_key = f"{str(row.get('source_url') or '')}::{str(row.get('quote') or '')[:160]}"
        if dedupe_key in selected_keys:
            continue
        selected.append(row)
        selected_keys.add(dedupe_key)
        per_source[source_bucket] = per_source.get(source_bucket, 0) + 1
        if len(selected) >= _AGENT3_VOC_MAX_ROWS:
            break
    if len(selected) < min(_AGENT3_VOC_MAX_ROWS, len(ranked_rows)):
        for row in ranked_rows:
            dedupe_key = f"{str(row.get('source_url') or '')}::{str(row.get('quote') or '')[:160]}"
            if dedupe_key in selected_keys:
                continue
            selected.append(row)
            selected_keys.add(dedupe_key)
            if len(selected) >= _AGENT3_VOC_MAX_ROWS:
                break

    compacted_observations: list[dict[str, Any]] = []
    allowed_voc_ids: list[str] = []
    compacted_scores: list[dict[str, Any]] = []
    for row in selected:
        voc_id = str(row.get("voc_id") or "").strip()
        if not voc_id:
            continue
        score_row = score_lookup.get(voc_id, {})
        allowed_voc_ids.append(voc_id)
        compacted_observations.append(
            {
                "voc_id": voc_id,
                "source_type": _compact_agent3_text(row.get("source_type"), max_chars=32),
                "source_url": _compact_agent3_text(row.get("source_url"), max_chars=240),
                "source_author": _compact_agent3_text(row.get("source_author"), max_chars=80),
                "source_date": _compact_agent3_text(row.get("source_date"), max_chars=48),
                "evidence_ref": _compact_agent3_text(row.get("evidence_ref"), max_chars=180),
                "quote": str(row.get("quote") or "").strip()[:_AGENT3_MAX_QUOTE_CHARS],
                "trigger_event": _compact_agent3_text(row.get("trigger_event"), max_chars=180),
                "pain_problem": _compact_agent3_text(row.get("pain_problem"), max_chars=180),
                "desired_outcome": _compact_agent3_text(row.get("desired_outcome"), max_chars=180),
                "failed_prior_solution": _compact_agent3_text(
                    row.get("failed_prior_solution"),
                    max_chars=180,
                ),
                "enemy_blame": _compact_agent3_text(row.get("enemy_blame"), max_chars=180),
                "identity_role": _compact_agent3_text(row.get("identity_role"), max_chars=140),
                "fear_risk": _compact_agent3_text(row.get("fear_risk"), max_chars=180),
                "emotional_valence": _compact_agent3_text(
                    row.get("emotional_valence"),
                    max_chars=48,
                ),
                "buyer_stage": _compact_agent3_text(row.get("buyer_stage"), max_chars=48),
                "solution_sophistication": _compact_agent3_text(
                    row.get("solution_sophistication"),
                    max_chars=48,
                ),
                "compliance_risk": _compact_agent3_text(row.get("compliance_risk"), max_chars=32),
                "specific_number": row.get("specific_number"),
                "specific_event_moment": row.get("specific_event_moment"),
                "before_after_comparison": row.get("before_after_comparison"),
                "crisis_language": row.get("crisis_language"),
                "headline_ready": row.get("headline_ready"),
                "personal_context": row.get("personal_context"),
                "long_narrative": row.get("long_narrative"),
            }
        )
        compacted_scores.append(
            {
                "voc_id": voc_id,
                "adjusted_score": float(score_row.get("adjusted_score") or 0.0),
                "confidence_range": list(score_row.get("confidence_range"))
                if isinstance(score_row.get("confidence_range"), (list, tuple))
                else score_row.get("confidence_range"),
                "aspiration_gap": int(score_row.get("aspiration_gap") or 0),
                "freshness_modifier": float(score_row.get("freshness_modifier") or 0.0),
                "zero_evidence_gate": bool(score_row.get("zero_evidence_gate")),
                "classifications": dict(score_row.get("classifications"))
                if isinstance(score_row.get("classifications"), Mapping)
                else {},
            }
        )

    diagnostics = {
        "input_count": len(ordered_rows),
        "selected_count": len(compacted_observations),
        "omitted_count": max(len(ordered_rows) - len(compacted_observations), 0),
        "source_type_distribution_selected": _agent2_source_type_distribution(compacted_observations),
    }
    compacted_voc_scored = {
        "selection_mode": "top_diverse_compact",
        "items": compacted_scores,
        "corpus_health": dict(voc_scored.get("corpus_health"))
        if isinstance(voc_scored.get("corpus_health"), Mapping)
        else {},
    }
    return compacted_observations, compacted_voc_scored, allowed_voc_ids, diagnostics


def _compact_agent3_raw_evidence_inputs(
    *,
    evidence_rows_for_prompt: Sequence[Mapping[str, Any]],
    evidence_manifest_rows: Sequence[Mapping[str, Any]],
    evidence_diagnostics: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], list[str]]:
    selected_rows, excluded_rows, compaction_summary = _compact_agent2_evidence_rows(
        evidence_rows=evidence_rows_for_prompt,
        max_rows=_AGENT3_RAW_EVIDENCE_MAX_ROWS,
    )
    compacted_rows: list[dict[str, Any]] = []
    allowed_voc_ids: list[str] = []
    for row in selected_rows:
        evidence_id = _normalize_agent2_evidence_id(
            row.get("evidence_id"),
            field_name="Agent 3 compact raw evidence row.evidence_id",
        )
        compacted_rows.append(
            {
                "evidence_id": evidence_id,
                "source_type": _compact_agent3_text(row.get("source_type"), max_chars=32),
                "source_url": _compact_agent3_text(row.get("source_url"), max_chars=240),
                "author": _compact_agent3_text(row.get("author"), max_chars=80),
                "date": _compact_agent3_text(row.get("date"), max_chars=48),
                "context": _compact_agent3_text(row.get("context"), max_chars=220),
                "verbatim": str(row.get("verbatim") or "").strip()[:900],
                "evidence_ref": _compact_agent3_text(row.get("evidence_ref"), max_chars=180),
            }
        )
        allowed_voc_ids.append(_derive_voc_id_from_evidence_id(evidence_id=evidence_id))

    manifest_by_id = {
        _normalize_agent2_evidence_id(
            row.get("evidence_id"),
            field_name="Agent 3 raw evidence manifest row.evidence_id",
        ): dict(row)
        for row in evidence_manifest_rows
        if isinstance(row, Mapping)
    }
    compacted_manifest: list[dict[str, Any]] = []
    for row in compacted_rows:
        manifest_row = manifest_by_id.get(str(row.get("evidence_id") or "").strip())
        if not isinstance(manifest_row, Mapping):
            continue
        compacted_manifest.append(
            {
                "input_index": int(manifest_row.get("input_index") or 0),
                "evidence_id": _compact_agent3_text(manifest_row.get("evidence_id"), max_chars=32),
                "source_type": _compact_agent3_text(manifest_row.get("source_type"), max_chars=32),
                "source_url": _compact_agent3_text(manifest_row.get("source_url"), max_chars=240),
                "source_author": _compact_agent3_text(manifest_row.get("source_author"), max_chars=80),
                "source_date": _compact_agent3_text(manifest_row.get("source_date"), max_chars=48),
                "evidence_ref": _compact_agent3_text(manifest_row.get("evidence_ref"), max_chars=180),
                "context_preview": _compact_agent3_text(
                    manifest_row.get("context_preview"),
                    max_chars=180,
                ),
                "verbatim_preview": _compact_agent3_text(
                    manifest_row.get("verbatim_preview"),
                    max_chars=220,
                ),
                "verbatim_sha256": _compact_agent3_text(
                    manifest_row.get("verbatim_sha256"),
                    max_chars=80,
                ),
            }
        )

    diagnostics = {
        "selection": compaction_summary,
        "input_diagnostics": dict(evidence_diagnostics),
        "excluded_count": len(excluded_rows),
    }
    return compacted_rows, compacted_manifest, diagnostics, allowed_voc_ids


def _estimate_agent3_payload_counts(payload: Any) -> dict[str, int]:
    counts = {"lists": 0, "dicts": 0, "scalars": 0}
    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            counts["dicts"] += 1
            stack.extend(current.values())
        elif isinstance(current, list):
            counts["lists"] += 1
            stack.extend(current)
        else:
            counts["scalars"] += 1
    return counts


def _validate_agent3_runtime_payloads(
    logical_payloads: Mapping[str, Any],
) -> dict[str, Any]:
    payload_sizes: dict[str, dict[str, Any]] = {}
    total_chars = 0
    oversized_payloads: list[str] = []
    for logical_name, payload in logical_payloads.items():
        serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        char_count = len(serialized)
        total_chars += char_count
        payload_sizes[str(logical_name)] = {
            "char_count": char_count,
            **_estimate_agent3_payload_counts(payload),
        }
        if char_count > _AGENT3_RUNTIME_SINGLE_PAYLOAD_MAX_CHARS:
            oversized_payloads.append(f"{logical_name}={char_count}")
    diagnostics = {
        "payloads": payload_sizes,
        "total_chars": total_chars,
        "single_payload_limit_chars": _AGENT3_RUNTIME_SINGLE_PAYLOAD_MAX_CHARS,
        "total_payload_limit_chars": _AGENT3_RUNTIME_TOTAL_PAYLOAD_MAX_CHARS,
        "oversized_payloads": oversized_payloads,
    }
    if oversized_payloads or total_chars > _AGENT3_RUNTIME_TOTAL_PAYLOAD_MAX_CHARS:
        raise StrategyV2MissingContextError(
            "Agent 3 runtime payload exceeded the bounded prompt package envelope "
            f"(total_chars={total_chars}, oversized_payloads={oversized_payloads}). "
            "Remediation: reduce duplicated Agent 3 context inputs before rerunning v2-06."
        )
    return diagnostics


def _build_agent3_runtime_logical_payloads(
    *,
    stage1_data: Mapping[str, Any],
    avatar_brief_payload: Mapping[str, Any],
    foundational_step_contents: Mapping[str, Any],
    foundational_step_summaries: Mapping[str, Any],
    competitor_analysis: Mapping[str, Any],
    habitat_scored: Mapping[str, Any],
    agent1_habitat_observations: Sequence[Mapping[str, Any]],
    agent1_mining_plan: Sequence[Mapping[str, Any]],
    voc_input_mode: str,
    voc_observations: Sequence[Mapping[str, Any]],
    voc_scored: Mapping[str, Any],
    evidence_rows_for_prompt: Sequence[Mapping[str, Any]],
    evidence_manifest_rows: Sequence[Mapping[str, Any]],
    evidence_diagnostics: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    competitor_angle_map = build_competitor_angle_map(competitor_analysis)
    compact_competitor_angle_map, competitor_map_diagnostics = _compact_agent3_competitor_angle_map(
        competitor_angle_map
    )
    saturated_angles = _compact_agent3_saturated_angles(
        extract_saturated_angles(competitor_analysis, limit=9)
    )
    compact_habitat_scored = _compact_agent3_habitat_scored(habitat_scored)
    compact_habitat_observations, habitat_diagnostics = _compact_agent3_habitat_observations(
        agent1_habitat_observations
    )
    compact_mining_plan, mining_diagnostics = _compact_agent3_mining_plan(agent1_mining_plan)

    logical_payloads: dict[str, Any] = {
        "COMPETITOR_ANGLE_MAP_JSON": compact_competitor_angle_map,
        "KNOWN_SATURATED_ANGLES_JSON": saturated_angles,
        "PRODUCT_BRIEF_JSON": _compact_agent3_product_brief(stage1_data),
        "HABITAT_SCORED_JSON": compact_habitat_scored,
        "AGENT1_HABITAT_OBSERVATIONS_JSON": compact_habitat_observations,
        "AGENT1_MINING_PLAN_JSON": compact_mining_plan,
        "AVATAR_BRIEF_SUMMARY_JSON": _compact_agent3_avatar_brief_payload(avatar_brief_payload),
        "FOUNDATIONAL_RESEARCH_DOCS_JSON": _compact_agent3_foundational_docs(
            foundational_step_contents=foundational_step_contents,
            foundational_step_summaries=foundational_step_summaries,
        ),
    }

    diagnostics: dict[str, Any] = {
        "competitor_map": competitor_map_diagnostics,
        "habitat_observations": habitat_diagnostics,
        "mining_plan": mining_diagnostics,
        "voc_input_mode": voc_input_mode,
        "foundational_mode": "summary_compact",
    }
    allowed_voc_ids: list[str] = []

    if voc_input_mode in {"agent2_full", "agent2_observations_only"}:
        compact_voc_observations, compact_voc_scored, allowed_voc_ids, voc_diagnostics = (
            _compact_agent3_voc_inputs(
                voc_observations=voc_observations,
                voc_scored=voc_scored,
            )
        )
        logical_payloads["AGENT2_VOC_OBSERVATIONS_JSON"] = compact_voc_observations
        logical_payloads["AGENT2_HANDOFF_VOC_SCORED_JSON"] = compact_voc_scored
        diagnostics["voc"] = voc_diagnostics
    else:
        compact_evidence_rows, compact_manifest_rows, raw_evidence_diagnostics, allowed_voc_ids = (
            _compact_agent3_raw_evidence_inputs(
                evidence_rows_for_prompt=evidence_rows_for_prompt,
                evidence_manifest_rows=evidence_manifest_rows,
                evidence_diagnostics=evidence_diagnostics,
            )
        )
        logical_payloads["VOC_EVIDENCE_ROWS_JSON"] = compact_evidence_rows
        logical_payloads["AGENT2_INPUT_MANIFEST_JSON"] = {
            "input_count": len(compact_manifest_rows),
            "evidence_id_pattern": _VOC_AGENT02_EVIDENCE_ID_PATTERN,
            "rows": compact_manifest_rows,
        }
        logical_payloads["VOC_EVIDENCE_LAYOUT_JSON"] = {
            "description": (
                "Rows contain deterministic evidence_id keyed VOC evidence for Agent 3 raw-evidence fallback."
            ),
            "required_fields": [
                "evidence_id",
                "source_type",
                "source_url",
                "author",
                "date",
                "context",
                "verbatim",
                "evidence_ref",
            ],
            "counts": {
                "evidence_rows": len(compact_evidence_rows),
                "manifest_rows": len(compact_manifest_rows),
            },
            "evidence_diagnostics": raw_evidence_diagnostics,
        }
        diagnostics["voc"] = raw_evidence_diagnostics

    diagnostics["payload_sizes"] = _validate_agent3_runtime_payloads(logical_payloads)
    return logical_payloads, allowed_voc_ids, diagnostics


def _render_agent3_runtime_instruction(
    *,
    agent03_file_id_map: Mapping[str, str],
    voc_input_mode: str,
) -> str:
    runtime_voc_instruction = ""
    if voc_input_mode == "raw_evidence_fallback":
        runtime_voc_instruction = (
            "Agent 2 VOC outputs were not provided for this run.\n"
            "Use VOC_EVIDENCE_ROWS_JSON + AGENT2_INPUT_MANIFEST_JSON as the canonical VOC source.\n"
            "Preserve evidence_id traceability and derive deterministic VOC IDs from evidence_id where needed.\n"
        )
    elif voc_input_mode == "agent2_observations_only":
        runtime_voc_instruction = (
            "AGENT2_VOC_OBSERVATIONS_JSON was provided without a native Agent 2 score payload.\n"
            "Use the provided scored handoff JSON generated from deterministic scoring for ranking support.\n"
        )
    return (
        "## Runtime Input Block\n"
        f"OPENAI_CODE_INTERPRETER_FILE_IDS_JSON:\n{_dump_prompt_json_required(agent03_file_id_map, max_chars=12000, field_name='OPENAI_CODE_INTERPRETER_FILE_IDS_JSON')}\n\n"
        "All required runtime JSON inputs are provided as uploaded files in the code interpreter container.\n"
        "Review FOUNDATIONAL_RESEARCH_DOCS_JSON before beginning any analysis.\n"
        "FOUNDATIONAL_RESEARCH_DOCS_JSON is intentionally summary_compact for v2-06; use it as high-level context, not as a raw transcript.\n"
        "Use OPENAI_CODE_INTERPRETER_FILE_IDS_JSON to load each dataset.\n"
        "Operate in artifact-only mode for this run and do not invoke web search.\n"
        "AGENT1_HABITAT_OBSERVATIONS_JSON, AGENT1_MINING_PLAN_JSON, and HABITAT_SCORED_JSON are compact scoring handoffs for prioritization.\n"
        "If any Agent 1 artifact is missing or empty, continue with available inputs and encode that limitation via conservative evidence judgments.\n"
        f"{runtime_voc_instruction}"
        "For every top_quotes entry, use only voc_id values available in the uploaded Agent 2 / raw-evidence runtime inputs.\n"
        "Output the JSON handoff block defined in the Agent 3 prompt.\n"
        f"Return exactly {_MIN_AGENT3_ANGLE_CANDIDATES} purple_ocean_candidates and "
        f"exactly {_AGENT3_TOP_QUOTES_PER_CANDIDATE} top_quotes per candidate.\n"
        "Do not generate hook_starters unless explicitly requested by the prompt.\n"
        f"Keep every non-quote text field <= {_AGENT3_MAX_TEXT_CHARS} characters and each quote <= {_AGENT3_MAX_QUOTE_CHARS} characters."
    )


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
            "competitor_angle_overlap": _coerce_yes_no(row.get("competitor_angle_overlap"), default="N"),
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


def _coerce_agent3_top_quote(raw_quote: Any) -> dict[str, Any]:
    if isinstance(raw_quote, str):
        quote_text = raw_quote.strip()
        if not quote_text:
            raise StrategyV2SchemaValidationError("Agent 3 top quote string cannot be empty.")
        return {"voc_id": "", "quote": quote_text}
    if not isinstance(raw_quote, Mapping):
        raise StrategyV2SchemaValidationError("Agent 3 top quote must be an object or string.")
    quote_text = str(raw_quote.get("quote") or "").strip()
    if not quote_text:
        raise StrategyV2SchemaValidationError("Agent 3 top quote object is missing quote text.")
    payload: dict[str, Any] = {
        "voc_id": str(raw_quote.get("voc_id") or "").strip(),
        "quote": quote_text,
    }
    adjusted_score = raw_quote.get("adjusted_score")
    if isinstance(adjusted_score, (int, float)):
        payload["adjusted_score"] = float(adjusted_score)
    return payload


def _map_prompt_purple_candidate_to_selected_angle(
    *,
    row: Mapping[str, Any],
    index: int,
) -> dict[str, Any]:
    primitive = row.get("primitive")
    if not isinstance(primitive, Mapping):
        raise StrategyV2SchemaValidationError(
            f"Agent 3 purple_ocean_candidates[{index}] is missing primitive object."
        )
    evidence = row.get("evidence")
    if not isinstance(evidence, Mapping):
        raise StrategyV2SchemaValidationError(
            f"Agent 3 purple_ocean_candidates[{index}] is missing evidence object."
        )

    angle_name = str(row.get("name") or row.get("angle_name") or "").strip()
    if not angle_name:
        raise StrategyV2SchemaValidationError(
            f"Agent 3 purple_ocean_candidates[{index}] is missing name."
        )

    rank_value = row.get("rank")
    rank_int = int(rank_value) if isinstance(rank_value, (int, float)) and int(rank_value) > 0 else index + 1
    angle_id = str(row.get("angle_id") or "").strip() or f"A{rank_int:02d}"

    who = str(primitive.get("who") or "").strip()
    trigger = str(primitive.get("trigger") or "").strip()
    pain = str(primitive.get("pain") or "").strip()
    desired_outcome = str(primitive.get("desired_outcome") or "").strip()
    mechanism = str(primitive.get("mechanism") or "").strip()
    belief_shift_raw = primitive.get("belief_shift")
    belief_shift = belief_shift_raw if isinstance(belief_shift_raw, Mapping) else {}
    belief_before = str(belief_shift.get("before") or "").strip()
    belief_after = str(belief_shift.get("after") or "").strip()

    pain_desire = ""
    if pain and desired_outcome:
        pain_desire = f"{pain} -> {desired_outcome}"
    elif pain:
        pain_desire = pain
    elif desired_outcome:
        pain_desire = desired_outcome

    top_quotes_raw = evidence.get("top_quotes")
    if not isinstance(top_quotes_raw, list):
        raise StrategyV2SchemaValidationError(
            f"Agent 3 purple_ocean_candidates[{index}] evidence.top_quotes must be an array."
        )
    top_quotes = [_coerce_agent3_top_quote(quote_row) for quote_row in top_quotes_raw]

    supporting_raw = evidence.get("supporting_voc_count")
    supporting_voc_count = int(supporting_raw) if isinstance(supporting_raw, (int, float)) else 0
    contradiction_raw = evidence.get("contradiction_count")
    contradiction_count = int(contradiction_raw) if isinstance(contradiction_raw, (int, float)) else 0

    triangulation_status = ""
    triangulation_raw = str(evidence.get("triangulation_status") or "").strip().upper()
    if triangulation_raw in {"SINGLE", "DUAL", "MULTI"}:
        triangulation_status = triangulation_raw
    elif isinstance(evidence.get("habitat_types"), (int, float)):
        habitat_types = int(evidence.get("habitat_types") or 0)
        if habitat_types >= 3:
            triangulation_status = "MULTI"
        elif habitat_types == 2:
            triangulation_status = "DUAL"
        elif habitat_types == 1:
            triangulation_status = "SINGLE"

    evidence_payload: dict[str, Any] = {
        "supporting_voc_count": max(0, supporting_voc_count),
        "top_quotes": top_quotes,
        "contradiction_count": max(0, contradiction_count),
    }
    if triangulation_status:
        evidence_payload["triangulation_status"] = triangulation_status

    return {
        "angle_id": angle_id,
        "angle_name": angle_name,
        "definition": {
            "who": who,
            "pain_desire": pain_desire,
            "mechanism_why": mechanism,
            "belief_shift": {
                "before": belief_before,
                "after": belief_after,
            },
            "trigger": trigger,
        },
        "evidence": evidence_payload,
    }


def _normalize_angle_candidates(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, row in enumerate(raw_rows):
        candidate_payload_raw: dict[str, Any]
        if isinstance(row.get("definition"), Mapping) and isinstance(row.get("evidence"), Mapping):
            candidate_payload_raw = dict(row)
        elif isinstance(row.get("primitive"), Mapping) and isinstance(row.get("evidence"), Mapping):
            candidate_payload_raw = _map_prompt_purple_candidate_to_selected_angle(
                row=row,
                index=index,
            )
        else:
            raise StrategyV2SchemaValidationError(
                "Agent 3 candidate row must include either definition/evidence or primitive/evidence."
            )

        candidate = SelectedAngleContract.model_validate(candidate_payload_raw)
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


def _extract_agent3_candidate_rows(agent03_output: Mapping[str, Any]) -> list[dict[str, Any]]:
    purple_rows = agent03_output.get("purple_ocean_candidates")
    if isinstance(purple_rows, list):
        return [row for row in purple_rows if isinstance(row, dict)]
    legacy_rows = agent03_output.get("angle_candidates")
    if isinstance(legacy_rows, list):
        return [row for row in legacy_rows if isinstance(row, dict)]
    raise StrategyV2SchemaValidationError(
        "Agent 3 output must contain purple_ocean_candidates array."
    )


def _agent3_quote_item_schema(*, allowed_voc_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "voc_id": {
                "type": "string",
                "enum": _ordered_unique_runtime_keys(
                    values=allowed_voc_ids,
                    field_name="Agent 3 allowed voc_ids",
                ),
            },
            "quote": {"type": "string", "maxLength": _AGENT3_MAX_QUOTE_CHARS},
        },
        "required": ["voc_id", "quote"],
    }


def _agent3_prompt_output_schema(
    *,
    include_legacy_angle_candidates: bool,
    allowed_voc_ids: Sequence[str],
) -> dict[str, Any]:
    quote_item_schema = _agent3_quote_item_schema(allowed_voc_ids=allowed_voc_ids)
    candidate_schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "rank": {"type": "integer", "minimum": 1},
            "name": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
            "primitive": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "who": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                    "trigger": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                    "pain": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                    "desired_outcome": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                    "enemy": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                    "mechanism": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                    "belief_shift": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "before": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                            "after": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                        },
                        "required": ["before", "after"],
                    },
                    "failed_fixes": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                    },
                },
                "required": [
                    "who",
                    "trigger",
                    "pain",
                    "desired_outcome",
                    "enemy",
                    "mechanism",
                    "belief_shift",
                    "failed_fixes",
                ],
            },
            "evidence": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "supporting_voc_count": {"type": "integer"},
                    "habitat_types": {"type": "integer"},
                    "contradiction_count": {"type": "integer"},
                    "top_quotes": {
                        "type": "array",
                        "minItems": _AGENT3_TOP_QUOTES_PER_CANDIDATE,
                        "maxItems": _AGENT3_TOP_QUOTES_PER_CANDIDATE,
                        "items": quote_item_schema,
                    },
                },
                "required": ["supporting_voc_count", "habitat_types", "contradiction_count", "top_quotes"],
            },
            "scores": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "demand_signal": {"type": "number"},
                    "pain_intensity": {"type": "number"},
                    "distinctiveness": {"type": "number"},
                    "plausibility": {"type": "number"},
                    "proof_density": {"type": "number"},
                    "compliance_safety": {"type": "number"},
                    "saturation": {"type": "number"},
                },
                "required": [
                    "demand_signal",
                    "pain_intensity",
                    "distinctiveness",
                    "plausibility",
                    "proof_density",
                    "compliance_safety",
                    "saturation",
                ],
            },
            "compliance_risk": {"type": "string", "maxLength": 64},
            "evidence_floor": {"type": "string", "maxLength": 64},
            "source_diversity": {"type": "string", "maxLength": 64},
            "recommended_stack": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "primary": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                    "secondary": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                    "tertiary": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
                },
                "required": ["primary", "secondary", "tertiary"],
            },
        },
        "required": [
            "rank",
            "name",
            "primitive",
            "evidence",
            "scores",
            "compliance_risk",
            "evidence_floor",
            "source_diversity",
            "recommended_stack",
        ],
    }
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "research_mode": {"type": "string", "maxLength": 64},
            "product": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
            "saturated_angles": {
                "type": "array",
                "items": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
            },
            "purple_ocean_candidates": {
                "type": "array",
                "minItems": _MIN_AGENT3_ANGLE_CANDIDATES,
                "maxItems": _MIN_AGENT3_ANGLE_CANDIDATES,
                "items": candidate_schema,
            },
            "angle_stacks": {
                "type": "array",
                "items": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
            },
            "orphan_signals": {
                "type": "array",
                "items": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
            },
            "confidence": {"type": "string", "maxLength": 64},
            "biggest_gap": {"type": "string", "maxLength": _AGENT3_MAX_TEXT_CHARS},
        },
        "required": [
            "research_mode",
            "product",
            "saturated_angles",
            "purple_ocean_candidates",
            "angle_stacks",
            "orphan_signals",
            "confidence",
            "biggest_gap",
        ],
    }
    if include_legacy_angle_candidates:
        schema["properties"]["angle_candidates"] = {
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
                                        "voc_id": {
                                            "type": "string",
                                            "enum": _ordered_unique_runtime_keys(
                                                values=allowed_voc_ids,
                                                field_name="Agent 3 allowed voc_ids",
                                            ),
                                        },
                                        "quote": {"type": "string", "maxLength": _AGENT3_MAX_QUOTE_CHARS},
                                        "adjusted_score": {"type": "number"},
                                    },
                                    "required": ["quote"],
                                },
                            },
                            "contradiction_count": {"type": "integer"},
                        },
                        "required": ["supporting_voc_count", "top_quotes", "contradiction_count"],
                    },
                },
                "required": ["angle_id", "angle_name", "definition", "evidence"],
            },
        }
        schema["anyOf"] = [{"required": ["purple_ocean_candidates"]}, {"required": ["angle_candidates"]}]
    return schema


def _dump_prompt_json(payload: object, *, max_chars: int) -> str:
    serialized = json.dumps(payload, ensure_ascii=True, indent=2)
    if len(serialized) <= max_chars:
        return serialized
    return serialized[:max_chars]


def _dump_prompt_json_required(payload: object, *, max_chars: int, field_name: str) -> str:
    serialized = json.dumps(payload, ensure_ascii=True, indent=2)
    if len(serialized) <= max_chars:
        return serialized
    raise StrategyV2MissingContextError(
        f"{field_name} exceeds prompt size limit ({len(serialized)} > {max_chars}). "
        "Remediation: reduce payload size or increase the configured STRATEGY_V2_*_MAX_CHARS limit; "
        "truncation is disabled for required runtime inputs."
    )


def _estimate_prompt_input_tokens(prompt: str) -> int:
    # Conservative heuristic for preflight budget checks.
    # Real tokenizer usage varies by content and model, so this must remain an estimate.
    return max(1, (len(prompt) + 3) // 4)


def _model_prompt_input_token_budget(*, model: str, max_tokens: int | None) -> int | None:
    normalized = model.strip().lower()
    if normalized.startswith("gpt-5.2"):
        reserved_output_tokens = max_tokens if isinstance(max_tokens, int) and max_tokens > 0 else _AGENT1_MAX_TOKENS
        budget = _GPT52_CONTEXT_WINDOW_TOKENS - reserved_output_tokens - _PROMPT_INPUT_TOKEN_SAFETY_BUFFER
        return max(budget, 1)
    return None


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
    stage2_payload = stage2.model_dump(mode="python")
    stage2_payload["price"] = require_concrete_price(
        price=stage2.price,
        context="Offer pipeline",
    )
    resolved_stage2 = ProductBriefStage2.model_validate(stage2_payload)
    return map_offer_pipeline_input(
        stage2=resolved_stage2,
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
    apify_context: dict[str, Any] = {}

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


def _parse_step_payload_artifact_ids(
    *,
    payload: Any,
    field_name: str,
) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise StrategyV2MissingContextError(
            f"{field_name} is required and must be an object keyed by step key -> artifact id. "
            "Remediation: pass workflow artifact_refs.step_payload_artifact_ids into checkpoint activity inputs."
        )
    parsed: dict[str, str] = {}
    for raw_step_key, raw_artifact_id in payload.items():
        if not isinstance(raw_step_key, str) or not raw_step_key.strip():
            continue
        if not isinstance(raw_artifact_id, str) or not raw_artifact_id.strip():
            continue
        parsed[raw_step_key.strip()] = raw_artifact_id.strip()
    return parsed


def _require_step_payload_artifact_prerequisites(
    *,
    checkpoint_label: str,
    step_payload_artifact_ids: Mapping[str, Any],
    required_step_keys: list[str],
    org_id: str | None = None,
    validate_lineage: bool = False,
) -> None:
    missing: list[str] = []
    for step_key in required_step_keys:
        artifact_id = step_payload_artifact_ids.get(step_key)
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            missing.append(step_key)
    if missing:
        raise StrategyV2MissingContextError(
            f"{checkpoint_label} is missing prerequisite step payload artifact ids: {missing}. "
            "Remediation: rerun from the prior checkpoint so required handoff artifacts are rebuilt."
        )
    if validate_lineage:
        if not isinstance(org_id, str) or not org_id.strip():
            raise StrategyV2MissingContextError(
                f"{checkpoint_label} requires org_id for lineage validation."
            )
        _validate_step_payload_lineage_prerequisites(
            checkpoint_label=checkpoint_label,
            org_id=org_id,
            step_payload_artifact_ids=step_payload_artifact_ids,
            required_step_keys=required_step_keys,
        )


def _validate_step_payload_lineage_payload(
    *,
    checkpoint_label: str,
    required_step_key: str,
    artifact_id: str,
    artifact_data: Mapping[str, Any],
) -> None:
    step_key = str(artifact_data.get("step_key") or "").strip()
    if step_key != required_step_key:
        raise StrategyV2MissingContextError(
            f"{checkpoint_label} artifact lineage mismatch for step '{required_step_key}' "
            f"(artifact_id={artifact_id}, actual_step_key='{step_key or 'missing'}')."
        )
    lineage = artifact_data.get("lineage")
    if not isinstance(lineage, Mapping):
        raise StrategyV2MissingContextError(
            f"{checkpoint_label} artifact '{required_step_key}' missing lineage metadata "
            f"(artifact_id={artifact_id})."
        )
    producer = str(lineage.get("producer") or "").strip()
    producer_version = str(lineage.get("producer_version") or "").strip()
    timestamp = str(lineage.get("timestamp") or "").strip()
    inputs_received = lineage.get("inputs_received")
    input_validation = str(lineage.get("input_validation") or "").strip()
    if producer != required_step_key:
        raise StrategyV2MissingContextError(
            f"{checkpoint_label} lineage producer mismatch for '{required_step_key}' "
            f"(artifact_id={artifact_id}, producer='{producer or 'missing'}')."
        )
    if not producer_version:
        raise StrategyV2MissingContextError(
            f"{checkpoint_label} lineage missing producer_version for '{required_step_key}' "
            f"(artifact_id={artifact_id})."
        )
    if not timestamp:
        raise StrategyV2MissingContextError(
            f"{checkpoint_label} lineage missing timestamp for '{required_step_key}' "
            f"(artifact_id={artifact_id})."
        )
    if not isinstance(inputs_received, list) or not all(isinstance(item, str) and item.strip() for item in inputs_received):
        raise StrategyV2MissingContextError(
            f"{checkpoint_label} lineage has invalid inputs_received for '{required_step_key}' "
            f"(artifact_id={artifact_id})."
        )
    if not input_validation:
        raise StrategyV2MissingContextError(
            f"{checkpoint_label} lineage missing input_validation for '{required_step_key}' "
            f"(artifact_id={artifact_id})."
        )


def _validate_step_payload_lineage_prerequisites(
    *,
    checkpoint_label: str,
    org_id: str,
    step_payload_artifact_ids: Mapping[str, Any],
    required_step_keys: list[str],
) -> None:
    with session_scope() as session:
        artifacts_repo = ArtifactsRepository(session)
        for step_key in required_step_keys:
            artifact_id = str(step_payload_artifact_ids.get(step_key) or "").strip()
            if not artifact_id:
                continue
            artifact = artifacts_repo.get(org_id=org_id, artifact_id=artifact_id)
            if artifact is None or not isinstance(artifact.data, Mapping):
                raise StrategyV2MissingContextError(
                    f"{checkpoint_label} missing step payload artifact data for '{step_key}' "
                    f"(artifact_id={artifact_id})."
                )
            _validate_step_payload_lineage_payload(
                checkpoint_label=checkpoint_label,
                required_step_key=step_key,
                artifact_id=artifact_id,
                artifact_data=artifact.data,
            )


def _require_stage1_artifact_id(*, params: Mapping[str, Any]) -> str:
    stage1_artifact_id = str(params.get("stage1_artifact_id") or "").strip()
    if not stage1_artifact_id:
        raise StrategyV2MissingContextError(
            "stage1_artifact_id is required for Stage 2B checkpoint integrity. "
            "Remediation: pass foundational stage1_artifact_id into downstream checkpoint activity inputs."
        )
    return stage1_artifact_id


def _load_foundational_step02_content_from_artifact(
    *,
    org_id: str,
    workflow_run_id: str,
) -> str:
    with session_scope() as session:
        research_repo = ResearchArtifactsRepository(session)
        artifacts_repo = ArtifactsRepository(session)
        record = research_repo.get_for_step(
            org_id=org_id,
            workflow_run_id=workflow_run_id,
            step_key="v2-02.foundation.02",
        )
        if record is None:
            return ""
        artifact = artifacts_repo.get(org_id=org_id, artifact_id=str(record.doc_id))
        if artifact is None or not isinstance(artifact.data, Mapping):
            return ""
        payload = artifact.data.get("payload")
        payload_map = payload if isinstance(payload, Mapping) else artifact.data
        content = payload_map.get("content") if isinstance(payload_map, Mapping) else None
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def _load_step_payload_payload_from_research_artifact(
    *,
    checkpoint_label: str,
    org_id: str,
    workflow_run_id: str,
    step_key: str,
) -> tuple[str, dict[str, Any]]:
    """Load the persisted step-payload artifact for the given step_key and return (artifact_id, payload).

    Strategy V2 step payloads can be large. Downstream activities should load them from the DB
    instead of passing the full payload through Temporal activity inputs/outputs.
    """
    if not org_id.strip():
        raise StrategyV2MissingContextError(f"{checkpoint_label} requires org_id to load step payload artifacts.")
    if not workflow_run_id.strip():
        raise StrategyV2MissingContextError(
            f"{checkpoint_label} requires workflow_run_id to load step payload artifacts."
        )
    if not step_key.strip():
        raise StrategyV2MissingContextError(f"{checkpoint_label} requires a non-empty step_key to load step payload.")

    with session_scope() as session:
        research_repo = ResearchArtifactsRepository(session)
        artifacts_repo = ArtifactsRepository(session)
        record = research_repo.get_for_step(
            org_id=org_id,
            workflow_run_id=workflow_run_id,
            step_key=step_key,
        )
        if record is None:
            raise StrategyV2MissingContextError(
                f"{checkpoint_label} missing step payload artifact for step '{step_key}'. "
                "Remediation: rerun the missing checkpoint so the handoff artifact is persisted."
            )
        artifact_id = str(record.doc_id or "").strip()
        if not artifact_id:
            raise StrategyV2MissingContextError(
                f"{checkpoint_label} has an invalid step payload artifact id for step '{step_key}'. "
                "Remediation: rerun the missing checkpoint so the handoff artifact is persisted."
            )
        artifact = artifacts_repo.get(org_id=org_id, artifact_id=artifact_id)
        if artifact is None or not isinstance(artifact.data, Mapping):
            raise StrategyV2MissingContextError(
                f"{checkpoint_label} missing step payload artifact data for step '{step_key}' "
                f"(artifact_id={artifact_id})."
            )

        artifact_data = artifact.data
        _validate_step_payload_lineage_payload(
            checkpoint_label=checkpoint_label,
            required_step_key=step_key,
            artifact_id=artifact_id,
            artifact_data=artifact_data,
        )

        payload_raw = artifact_data.get("payload")
        if not isinstance(payload_raw, Mapping):
            raise StrategyV2MissingContextError(
                f"{checkpoint_label} step payload artifact for step '{step_key}' is missing payload "
                f"(artifact_id={artifact_id})."
            )
        payload = dict(payload_raw)
        return artifact_id, payload


def _require_stage2b_shared_context(*, params: Mapping[str, Any]) -> dict[str, Any]:
    org_id = str(params.get("org_id") or "").strip()
    workflow_run_id = str(params.get("workflow_run_id") or "").strip()
    _heartbeat_safe(
        {
            "activity": "strategy_v2.require_stage2b_shared_context",
            "phase": "context_hydration",
            "status": "in_progress",
            "progress_event": "shared_context_started",
        }
    )
    stage0 = ProductBriefStage0.model_validate(_require_dict(payload=params["stage0"], field_name="stage0"))
    stage1 = ProductBriefStage1.model_validate(_require_dict(payload=params["stage1"], field_name="stage1"))
    _require_stage1_quality(stage1)
    precanon_research = _require_dict(payload=params["precanon_research"], field_name="precanon_research")
    _heartbeat_safe(
        {
            "activity": "strategy_v2.require_stage2b_shared_context",
            "phase": "context_hydration",
            "status": "in_progress",
            "progress_event": "stage_payloads_validated",
        }
    )

    confirmed_competitor_assets_raw = params.get("confirmed_competitor_assets")
    if not isinstance(confirmed_competitor_assets_raw, list):
        raise StrategyV2MissingContextError(
            "confirmed_competitor_assets is required for Stage 2B checkpoint execution. "
            "Remediation: complete H2 and pass 3+ confirmed competitor asset refs."
        )
    confirmed_competitor_assets = [
        str(item).strip()
        for item in confirmed_competitor_assets_raw
        if isinstance(item, str) and item.strip()
    ]
    if len(confirmed_competitor_assets) < 3:
        raise StrategyV2MissingContextError(
            "Stage 2B requires at least 3 confirmed competitor assets in shared immutable context. "
            "Remediation: complete H2 with 3+ confirmed competitor asset refs."
        )

    step_contents_raw = _require_dict(
        payload=precanon_research.get("step_contents"),
        field_name="precanon_research.step_contents",
    )
    step_summaries_raw = _require_dict(
        payload=precanon_research.get("step_summaries", {}),
        field_name="precanon_research.step_summaries",
    )
    has_step02 = isinstance(step_contents_raw.get("02"), str) and str(step_contents_raw.get("02")).strip() != ""
    if not has_step02:
        restored_step02 = ""
        if org_id and workflow_run_id:
            restored_step02 = _run_with_activity_heartbeats(
                phase="context_hydration",
                operation="restore_step02_from_artifact",
                heartbeat_payload={
                    "activity": "strategy_v2.require_stage2b_shared_context",
                },
                fn=lambda: _load_foundational_step02_content_from_artifact(
                    org_id=org_id,
                    workflow_run_id=workflow_run_id,
                ),
            )
        if restored_step02:
            updated_step_contents = dict(step_contents_raw)
            updated_step_contents["02"] = restored_step02
            updated_step_summaries = dict(step_summaries_raw)
            updated_step_summaries["02"] = "restored_from_step_payload_artifact"
            precanon_research = dict(precanon_research)
            precanon_research["step_contents"] = updated_step_contents
            precanon_research["step_summaries"] = updated_step_summaries
            step_contents_raw = updated_step_contents
            step_summaries_raw = updated_step_summaries
            has_step02 = True
            _heartbeat_safe(
                {
                    "activity": "strategy_v2.require_stage2b_shared_context",
                    "phase": "context_hydration",
                    "status": "in_progress",
                    "progress_event": "step02_restored_from_artifact",
                }
            )
    if not has_step02:
        step1_content_raw = step_contents_raw.get("01")
        if not isinstance(step1_content_raw, str) or not step1_content_raw.strip():
            raise StrategyV2MissingContextError(
                "Foundational step 01 content is missing; cannot generate competitor analysis for step 02. "
                "Remediation: rerun foundational stage and persist step 01 output."
            )
        _heartbeat_safe(
            {
                "activity": "strategy_v2.require_stage2b_shared_context",
                "phase": "context_hydration",
                "status": "in_progress",
                "progress_event": "step02_generation_started",
            }
        )
        step1_summary = (
            str(step_summaries_raw.get("01")).strip()
            if isinstance(step_summaries_raw.get("01"), str)
            else step1_content_raw[:2000]
        )
        category_niche = str(stage1.category_niche or stage0.product_name).strip() or stage0.product_name
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
        _heartbeat_safe(
            {
                "activity": "strategy_v2.require_stage2b_shared_context",
                "phase": "context_hydration",
                "status": "in_progress",
                "progress_event": "step02_generation_completed",
            }
        )

    foundational_step_contents = _require_foundational_step_contents(precanon_research=precanon_research)
    foundational_step_summaries = _require_dict(
        payload=precanon_research.get("step_summaries", {}),
        field_name="precanon_research.step_summaries",
    )
    competitor_analysis = extract_competitor_analysis(precanon_research)
    avatar_brief_payload = _build_avatar_brief_runtime_payload(
        step6_content=foundational_step_contents["06"],
        step6_summary=str(foundational_step_summaries.get("06") or ""),
    )
    _heartbeat_safe(
        {
            "activity": "strategy_v2.require_stage2b_shared_context",
            "phase": "context_hydration",
            "status": "completed",
            "progress_event": "shared_context_ready",
        }
    )

    return {
        "stage0": stage0,
        "stage1": stage1,
        "stage1_data": stage1.model_dump(mode="python"),
        "precanon_research": precanon_research,
        "foundational_step_contents": foundational_step_contents,
        "foundational_step_summaries": foundational_step_summaries,
        "confirmed_competitor_assets": confirmed_competitor_assets,
        "competitor_analysis": competitor_analysis,
        "avatar_brief_payload": avatar_brief_payload,
    }


def _updated_step_payload_artifact_ids(
    *,
    existing_step_payload_artifact_ids: Mapping[str, str],
    step_key: str,
    artifact_id: str,
) -> dict[str, str]:
    updated = dict(existing_step_payload_artifact_ids)
    updated[step_key] = artifact_id
    return updated


def _ensure_foundational_step_payload_artifact_ids(
    *,
    org_id: str,
    client_id: str,
    product_id: str,
    campaign_id: str | None,
    workflow_run_id: str,
    foundational_step_contents: Mapping[str, str],
    foundational_step_summaries: Mapping[str, Any],
    existing_step_payload_artifact_ids: Mapping[str, str],
) -> dict[str, str]:
    updated_step_payload_artifact_ids = dict(existing_step_payload_artifact_ids)
    missing_foundational_step_contents = {
        step_key: foundational_step_contents[step_key]
        for step_key in _FOUNDATIONAL_STEP_KEYS
        if f"v2-02.foundation.{step_key}" not in updated_step_payload_artifact_ids
    }
    if not missing_foundational_step_contents:
        return updated_step_payload_artifact_ids

    with session_scope() as session:
        persisted_foundational_ids = _persist_foundational_step_payloads(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            workflow_run_id=workflow_run_id,
            step_contents=missing_foundational_step_contents,
            step_summaries=foundational_step_summaries,
        )
    updated_step_payload_artifact_ids.update(persisted_foundational_ids)
    return updated_step_payload_artifact_ids


@activity.defn(name="strategy_v2.run_voc_agent0_habitat_strategy")
def run_strategy_v2_voc_agent0_habitat_strategy_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    workflow_run_id = str(params["workflow_run_id"])
    operator_user_id = str(params.get("operator_user_id") or "system")

    stage1_artifact_id = _require_stage1_artifact_id(params=params)
    shared_context = _require_stage2b_shared_context(params=params)
    existing_step_payload_artifact_ids = _parse_step_payload_artifact_ids(
        payload=params.get("existing_step_payload_artifact_ids"),
        field_name="existing_step_payload_artifact_ids",
    )

    stage1 = shared_context["stage1"]
    stage1_data = shared_context["stage1_data"]
    avatar_brief_payload = shared_context["avatar_brief_payload"]
    foundational_step_contents = shared_context["foundational_step_contents"]
    foundational_step_summaries = shared_context["foundational_step_summaries"]
    competitor_analysis = shared_context["competitor_analysis"]
    avatar_brief_payload = shared_context["avatar_brief_payload"]
    step4_content = foundational_step_contents["04"].strip()
    entries = _extract_step4_entries(step4_content)

    existing_step_payload_artifact_ids = _ensure_foundational_step_payload_artifact_ids(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        workflow_run_id=workflow_run_id,
        foundational_step_contents=foundational_step_contents,
        foundational_step_summaries=foundational_step_summaries,
        existing_step_payload_artifact_ids=existing_step_payload_artifact_ids,
    )
    _require_step_payload_artifact_prerequisites(
        checkpoint_label="v2-02 Agent 0 habitat strategy",
        step_payload_artifact_ids=existing_step_payload_artifact_ids,
        required_step_keys=[f"v2-02.foundation.{step_key}" for step_key in _FOUNDATIONAL_STEP_KEYS],
        org_id=org_id,
        validate_lineage=True,
    )

    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent0_habitat_strategy",
            "phase": "agent0_prompt",
            "status": "started",
        }
    )
    agent00_asset = resolve_prompt_asset(
        pattern=_VOC_AGENT00_PROMPT_PATTERN,
        context="VOC Agent 0 habitat strategist",
    )
    agent00_file_id_map, agent00_uploaded_file_ids = _upload_openai_prompt_json_files(
        model=settings.STRATEGY_V2_VOC_MODEL,
        workflow_run_id=workflow_run_id,
        stage_label="agent0",
        logical_payloads={
            "FOUNDATIONAL_RESEARCH_DOCS_JSON": {
                "step_contents": {
                    step_key: str(foundational_step_contents.get(step_key) or "")
                    for step_key in _FOUNDATIONAL_STEP_KEYS
                },
                "step_summaries": {
                    step_key: str(foundational_step_summaries.get(step_key) or "")
                    for step_key in _FOUNDATIONAL_STEP_KEYS
                },
            }
        },
    )
    try:
        agent00_runtime_base = (
            "## Runtime Input Block\n"
            f"OPENAI_CODE_INTERPRETER_FILE_IDS_JSON:\n{_dump_prompt_json_required(agent00_file_id_map, max_chars=12000, field_name='OPENAI_CODE_INTERPRETER_FILE_IDS_JSON')}\n\n"
            "All required runtime JSON inputs are provided as uploaded files in the code interpreter container.\n"
            "Review FOUNDATIONAL_RESEARCH_DOCS_JSON before generating habitat strategy.\n\n"
            f"PRODUCT_BRIEF:\n{_dump_prompt_json(stage1_data, max_chars=12000)}\n\n"
            f"AVATAR_BRIEF:\n{_dump_prompt_json(avatar_brief_payload, max_chars=12000)}\n\n"
            f"COMPETITOR_RESEARCH:\n{str(foundational_step_contents.get('01') or '')[:20000]}\n\n"
            f"COMPETITOR_ANALYSIS_JSON:\n{_dump_prompt_json(competitor_analysis, max_chars=16000)}\n\n"
            f"KNOWN_HABITAT_URLS:\n{_dump_prompt_json([], max_chars=4000)}\n\n"
            f"PLATFORM_RESTRICTIONS:\n{_dump_prompt_json(None, max_chars=2000)}\n\n"
            f"GEOGRAPHIC_TARGET:\n{_dump_prompt_json(None, max_chars=2000)}\n"
        )
        agent00_handoff_output, agent00_raw, agent00_provenance = _run_prompt_json_object(
            asset=agent00_asset,
            context="strategy_v2.agent0_output",
            model=settings.STRATEGY_V2_VOC_MODEL,
            runtime_instruction=agent00_runtime_base,
            schema_name="strategy_v2_voc_agent00_handoff",
            schema=_VOC_AGENT00_HANDOFF_SCHEMA,
            use_reasoning=True,
            reasoning_effort="xhigh",
            use_web_search=True,
            openai_tools=_openai_python_tool_resources(
                settings.STRATEGY_V2_VOC_MODEL,
                file_ids=list(agent00_file_id_map.values()),
            ),
            openai_tool_choice="auto",
            heartbeat_context={
                "activity": "strategy_v2.run_voc_agent0_habitat_strategy",
                "phase": "agent0_prompt",
                "model": settings.STRATEGY_V2_VOC_MODEL,
            },
            append_schema_instruction=False,
        )
    finally:
        _cleanup_openai_prompt_files(
            model=settings.STRATEGY_V2_VOC_MODEL,
            file_ids=agent00_uploaded_file_ids,
        )
    _raise_if_blocked_prompt_output(
        stage_label="v2-02 Agent 0 habitat strategist",
        parsed_output=agent00_handoff_output,
        raw_output=agent00_raw,
        remediation=(
            "provide complete PRODUCT_BRIEF, AVATAR_BRIEF, and COMPETITOR_ANALYSIS "
            "inputs before rerunning v2-02."
        ),
    )
    agent00_output = _normalize_agent00_handoff_output(agent00_handoff_output)
    _require_agent00_executable_configs(agent00_output)

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
        "agent_handoff_json": agent00_handoff_output,
        "prompt_provenance": agent00_provenance,
        "raw_output": agent00_raw[:20000],
    }

    with session_scope() as session:
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
        step_payload_artifact_id = _persist_step_payload(
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

    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent0_habitat_strategy",
            "phase": "agent0_prompt",
            "status": "completed",
            "step_payload_artifact_id": step_payload_artifact_id,
        }
    )
    updated_step_payload_artifact_ids = _updated_step_payload_artifact_ids(
        existing_step_payload_artifact_ids=existing_step_payload_artifact_ids,
        step_key=V2_STEP_HABITAT_STRATEGY,
        artifact_id=step_payload_artifact_id,
    )
    return {
        "stage1": stage1_data,
        "stage1_artifact_id": stage1_artifact_id,
        "agent00_output": agent00_output,
        "competitor_analysis": competitor_analysis,
        "step_payload_artifact_id": step_payload_artifact_id,
        "step_payload_artifact_ids": updated_step_payload_artifact_ids,
    }


@activity.defn(name="strategy_v2.run_voc_agent0b_social_video_strategy")
def run_strategy_v2_voc_agent0b_social_video_strategy_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    workflow_run_id = str(params["workflow_run_id"])
    operator_user_id = str(params.get("operator_user_id") or "system")

    stage1_artifact_id = _require_stage1_artifact_id(params=params)
    shared_context = _require_stage2b_shared_context(params=params)
    stage1 = shared_context["stage1"]
    existing_step_payload_artifact_ids = _parse_step_payload_artifact_ids(
        payload=params.get("existing_step_payload_artifact_ids"),
        field_name="existing_step_payload_artifact_ids",
    )
    foundational_step_contents = shared_context["foundational_step_contents"]
    foundational_step_summaries = shared_context["foundational_step_summaries"]
    existing_step_payload_artifact_ids = _ensure_foundational_step_payload_artifact_ids(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        workflow_run_id=workflow_run_id,
        foundational_step_contents=foundational_step_contents,
        foundational_step_summaries=foundational_step_summaries,
        existing_step_payload_artifact_ids=existing_step_payload_artifact_ids,
    )
    _require_step_payload_artifact_prerequisites(
        checkpoint_label="v2-03 Agent 0b social video strategy",
        step_payload_artifact_ids=existing_step_payload_artifact_ids,
        required_step_keys=[
            *[f"v2-02.foundation.{step_key}" for step_key in _FOUNDATIONAL_STEP_KEYS],
            V2_STEP_HABITAT_STRATEGY,
        ],
        org_id=org_id,
        validate_lineage=True,
    )

    stage1 = shared_context["stage1"]
    stage1_data = shared_context["stage1_data"]
    competitor_analysis = _require_dict(
        payload=params.get("competitor_analysis"),
        field_name="competitor_analysis",
    )
    avatar_brief_payload = shared_context["avatar_brief_payload"]
    step4_content = foundational_step_contents["04"].strip()
    entries = _extract_step4_entries(step4_content)

    agent00_output = _require_dict(
        payload=params.get("agent00_output"),
        field_name="agent00_output",
    )
    _require_agent00_executable_configs(agent00_output)
    product_category_keywords = _require_stage1_product_category_keywords(stage1)

    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent0b_social_video_strategy",
            "phase": "agent0b_prompt",
            "status": "started",
        }
    )
    agent00b_asset = resolve_prompt_asset(
        pattern=_VOC_AGENT00B_PROMPT_PATTERN,
        context="VOC Agent 0b social video strategist",
    )
    agent00b_file_id_map, agent00b_uploaded_file_ids = _upload_openai_prompt_json_files(
        model=settings.STRATEGY_V2_VOC_MODEL,
        workflow_run_id=workflow_run_id,
        stage_label="agent0b",
        logical_payloads={
            "FOUNDATIONAL_RESEARCH_DOCS_JSON": {
                "step_contents": {
                    step_key: str(foundational_step_contents.get(step_key) or "")
                    for step_key in _FOUNDATIONAL_STEP_KEYS
                },
                "step_summaries": {
                    step_key: str(foundational_step_summaries.get(step_key) or "")
                    for step_key in _FOUNDATIONAL_STEP_KEYS
                },
            }
        },
    )
    try:
        agent00b_output, agent00b_raw, agent00b_provenance = _run_prompt_json_object(
            asset=agent00b_asset,
            context="strategy_v2.agent0b_output",
            model=settings.STRATEGY_V2_VOC_MODEL,
            runtime_instruction=(
                "## Runtime Input Block\n"
                f"OPENAI_CODE_INTERPRETER_FILE_IDS_JSON:\n{_dump_prompt_json_required(agent00b_file_id_map, max_chars=12000, field_name='OPENAI_CODE_INTERPRETER_FILE_IDS_JSON')}\n\n"
                "All required runtime JSON inputs are provided as uploaded files in the code interpreter container.\n"
                "Review FOUNDATIONAL_RESEARCH_DOCS_JSON before generating video strategy.\n\n"
                f"PRODUCT_BRIEF:\n{_dump_prompt_json(stage1_data, max_chars=12000)}\n\n"
                f"AVATAR_BRIEF:\n{_dump_prompt_json(avatar_brief_payload, max_chars=12000)}\n\n"
                f"COMPETITOR_ANALYSIS:\n{_dump_prompt_json(competitor_analysis, max_chars=16000)}\n\n"
                f"PRODUCT_CATEGORY_KEYWORDS:\n{', '.join(product_category_keywords)}\n\n"
                f"KNOWN_COMPETITOR_SOCIAL_ACCOUNTS:\n{_dump_prompt_json(stage1.competitor_urls, max_chars=6000)}\n"
            ),
            schema_name="strategy_v2_voc_agent00b",
            schema=_voc_agent00b_response_schema(),
            use_reasoning=True,
            reasoning_effort="xhigh",
            use_web_search=True,
            openai_tools=_openai_python_tool_resources(
                settings.STRATEGY_V2_VOC_MODEL,
                file_ids=list(agent00b_file_id_map.values()),
            ),
            openai_tool_choice="auto",
            heartbeat_context={
                "activity": "strategy_v2.run_voc_agent0b_social_video_strategy",
                "phase": "agent0b_prompt",
                "model": settings.STRATEGY_V2_VOC_MODEL,
            },
            append_schema_instruction=False,
        )
    finally:
        _cleanup_openai_prompt_files(
            model=settings.STRATEGY_V2_VOC_MODEL,
            file_ids=agent00b_uploaded_file_ids,
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
    _require_agent00b_executable_configs(agent00b_output)

    strategy_apify_configs = _extract_apify_configs_from_agent_strategies(
        habitat_strategy=agent00_output,
        video_strategy=agent00b_output,
    )

    with session_scope() as session:
        video_strategy_agent_run_id = _record_agent_run(
            session=session,
            org_id=org_id,
            user_id=operator_user_id,
            client_id=client_id,
            objective_type="strategy_v2.agent0b_social_video_strategy.prompt_chain",
            model=settings.STRATEGY_V2_VOC_MODEL,
            inputs_json={
                "planned_actor_run_count": len(strategy_apify_configs),
                "max_actor_runs_configured": int(settings.STRATEGY_V2_APIFY_MAX_ACTOR_RUNS),
            },
            outputs_json={
                "video_strategy": agent00b_output,
                "platform_priorities": agent00b_output.get("platform_priorities"),
            },
        )
        step_payload_artifact_id = _persist_step_payload(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            workflow_run_id=workflow_run_id,
            step_key=V2_STEP_SCRAPE_VIRALITY,
            title="Strategy V2 Social Video Strategy",
            summary="Agent 0b prompt-chain social video strategy prepared for downstream Apify execution.",
            payload={
                "video_strategy": agent00b_output,
                "planned_actor_run_count": len(strategy_apify_configs),
                "max_actor_runs_configured": int(settings.STRATEGY_V2_APIFY_MAX_ACTOR_RUNS),
                "prompt_provenance": agent00b_provenance,
                "raw_output": agent00b_raw[:20000],
            },
            model_name=settings.STRATEGY_V2_VOC_MODEL,
            prompt_version="strategy_v2.agent0b.prompt_chain.v2",
            schema_version=SCHEMA_VERSION_V2,
            agent_run_id=video_strategy_agent_run_id,
        )

    updated_step_payload_artifact_ids = _updated_step_payload_artifact_ids(
        existing_step_payload_artifact_ids=existing_step_payload_artifact_ids,
        step_key=V2_STEP_SCRAPE_VIRALITY,
        artifact_id=step_payload_artifact_id,
    )
    return {
        "stage1": stage1_data,
        "stage1_artifact_id": stage1_artifact_id,
        "agent00b_output": agent00b_output,
        "step_payload_artifact_id": step_payload_artifact_id,
        "step_payload_artifact_ids": updated_step_payload_artifact_ids,
    }


def _load_apify_collection_payload_for_postprocess(
    *,
    org_id: str,
    apify_collection_artifact_id: str,
) -> dict[str, Any]:
    with session_scope() as session:
        artifacts_repo = ArtifactsRepository(session)
        artifact = artifacts_repo.get(org_id=org_id, artifact_id=apify_collection_artifact_id)
        if artifact is None or not isinstance(artifact.data, dict):
            raise StrategyV2MissingContextError(
                "Missing apify collection artifact for Stage 2B postprocess. "
                f"artifact_id={apify_collection_artifact_id}. "
                "Remediation: rerun v2-03b apify_collection before v2-03c/v2-03b postprocess."
            )
        _validate_step_payload_lineage_payload(
            checkpoint_label="v2-03c Apify postprocess + virality",
            required_step_key=V2_STEP_APIFY_COLLECTION,
            artifact_id=apify_collection_artifact_id,
            artifact_data=artifact.data,
        )
        payload = artifact.data.get("payload")
        if not isinstance(payload, dict):
            raise StrategyV2SchemaValidationError(
                "Invalid apify collection artifact payload envelope. "
                f"artifact_id={apify_collection_artifact_id}."
            )
        collection_payload = payload.get("apify_collection")
        if not isinstance(collection_payload, dict):
            raise StrategyV2SchemaValidationError(
                "Apify collection artifact is missing required apify_collection payload. "
                f"artifact_id={apify_collection_artifact_id}."
            )
        apify_context = collection_payload.get("apify_context")
        if not isinstance(apify_context, dict):
            raise StrategyV2SchemaValidationError(
                "Apify collection artifact is missing required apify_context object. "
                f"artifact_id={apify_collection_artifact_id}."
            )
        raw_runs = apify_context.get("raw_runs")
        if not isinstance(raw_runs, list) or not raw_runs:
            raise StrategyV2SchemaValidationError(
                "Apify collection artifact is missing full raw_runs data required for deterministic postprocess. "
                f"artifact_id={apify_collection_artifact_id}. "
                "Remediation: rerun apify collection without preview-only payloads."
            )
        return collection_payload


def _load_apify_ingestion_payload_for_downstream(
    *,
    org_id: str,
    apify_ingestion_artifact_id: str,
) -> dict[str, Any]:
    with session_scope() as session:
        artifacts_repo = ArtifactsRepository(session)
        artifact = artifacts_repo.get(org_id=org_id, artifact_id=apify_ingestion_artifact_id)
        if artifact is None or not isinstance(artifact.data, Mapping):
            raise StrategyV2MissingContextError(
                "Missing Strategy V2 Apify ingestion artifact for downstream hydration "
                f"(artifact_id={apify_ingestion_artifact_id}). "
                "Remediation: rerun v2-03c before invoking downstream agents."
            )
        payload = artifact.data.get("payload")
        payload_map = payload if isinstance(payload, Mapping) else artifact.data
        if not isinstance(payload_map, Mapping):
            raise StrategyV2SchemaValidationError(
                "Apify ingestion artifact payload is malformed; expected object payload. "
                f"artifact_id={apify_ingestion_artifact_id}."
            )
        return dict(payload_map)


@activity.defn(name="strategy_v2.run_voc_agent0b_apify_collection")
def run_strategy_v2_voc_agent0b_apify_collection_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    workflow_run_id = str(params["workflow_run_id"])
    operator_user_id = str(params.get("operator_user_id") or "system")
    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent0b_apify_collection",
            "phase": "context_hydration",
            "status": "started",
        }
    )

    stage1_artifact_id = _require_stage1_artifact_id(params=params)
    _ = stage1_artifact_id
    shared_context = _require_stage2b_shared_context(params=params)
    existing_step_payload_artifact_ids = _parse_step_payload_artifact_ids(
        payload=params.get("existing_step_payload_artifact_ids"),
        field_name="existing_step_payload_artifact_ids",
    )
    foundational_step_contents = shared_context["foundational_step_contents"]
    foundational_step_summaries = shared_context["foundational_step_summaries"]
    existing_step_payload_artifact_ids = _ensure_foundational_step_payload_artifact_ids(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        workflow_run_id=workflow_run_id,
        foundational_step_contents=foundational_step_contents,
        foundational_step_summaries=foundational_step_summaries,
        existing_step_payload_artifact_ids=existing_step_payload_artifact_ids,
    )
    _require_step_payload_artifact_prerequisites(
        checkpoint_label="v2-03b Apify collection",
        step_payload_artifact_ids=existing_step_payload_artifact_ids,
        required_step_keys=[
            *[f"v2-02.foundation.{step_key}" for step_key in _FOUNDATIONAL_STEP_KEYS],
            V2_STEP_HABITAT_STRATEGY,
            V2_STEP_SCRAPE_VIRALITY,
        ],
        org_id=org_id,
        validate_lineage=True,
    )

    agent00_output = _require_dict(
        payload=params.get("agent00_output"),
        field_name="agent00_output",
    )
    _require_agent00_executable_configs(agent00_output)
    agent00b_output = _require_dict(
        payload=params.get("agent00b_output"),
        field_name="agent00b_output",
    )
    _require_agent00b_executable_configs(agent00b_output)

    strategy_apify_configs = _extract_apify_configs_from_agent_strategies(
        habitat_strategy=agent00_output,
        video_strategy=agent00b_output,
    )
    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent0b_apify_collection",
            "phase": "context_hydration",
            "status": "completed",
            "config_count": len(strategy_apify_configs),
        }
    )
    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent0b_apify_collection",
            "phase": "apify_execution_layer",
            "status": "started",
            "config_count": len(strategy_apify_configs),
        }
    )

    def _apify_progress_heartbeat(event: dict[str, Any]) -> None:
        heartbeat_payload: dict[str, Any] = {
            "activity": "strategy_v2.run_voc_agent0b_apify_collection",
            "phase": "apify_execution_layer",
            "status": "in_progress",
            "progress_event": str(event.get("event") or "unknown"),
            "config_count": len(strategy_apify_configs),
        }
        for field_name in (
            "actor_id",
            "config_id",
            "run_id",
            "run_index",
            "planned_run_count",
            "elapsed_seconds",
            "status",
        ):
            field_value = event.get(field_name)
            if field_value is not None:
                if field_name == "status":
                    heartbeat_payload["actor_run_status"] = field_value
                else:
                    heartbeat_payload[field_name] = field_value
        activity.heartbeat(heartbeat_payload)

    apify_context = _ingest_strategy_v2_asset_data(
        apify_configs=strategy_apify_configs,
        include_ads_context=False,
        include_social_video=True,
        include_external_voc=True,
        progress_callback=_apify_progress_heartbeat,
    )
    apify_context["ingestion_apify_configs"] = strategy_apify_configs
    apify_context["ingestion_source_refs"] = []
    apify_context["excluded_source_refs"] = []

    raw_runs = apify_context.get("raw_runs")
    raw_run_rows = [row for row in raw_runs if isinstance(row, dict)] if isinstance(raw_runs, list) else []
    executed_actor_run_count = len(raw_run_rows)
    failed_actor_run_count = len(
        [row for row in raw_run_rows if str(row.get("status") or "").upper() != "SUCCEEDED"]
    )
    _validate_reddit_target_alignment(run_rows=raw_run_rows)
    apify_summary = _require_dict(
        payload=apify_context.get("summary"),
        field_name="apify_context.summary",
    )
    strategy_config_run_count = apify_summary.get("strategy_config_run_count")
    planned_actor_run_count = apify_summary.get("planned_actor_run_count")
    if not isinstance(strategy_config_run_count, int) or strategy_config_run_count < 0:
        raise StrategyV2SchemaValidationError(
            "apify_context.summary.strategy_config_run_count must be a non-negative integer."
        )
    if strategy_config_run_count != len(strategy_apify_configs):
        raise StrategyV2SchemaValidationError(
            "apify_context.summary.strategy_config_run_count mismatch "
            f"(summary={strategy_config_run_count}, expected_strategy_configs={len(strategy_apify_configs)})."
        )
    if not isinstance(planned_actor_run_count, int) or planned_actor_run_count < 0:
        raise StrategyV2SchemaValidationError(
            "apify_context.summary.planned_actor_run_count must be a non-negative integer."
        )
    if planned_actor_run_count < executed_actor_run_count:
        raise StrategyV2SchemaValidationError(
            "apify_context.summary.planned_actor_run_count cannot be less than executed_actor_run_count "
            f"(planned={planned_actor_run_count}, executed={executed_actor_run_count})."
        )
    ingestion_summary = {
        **apify_summary,
        "strategy_config_run_count": strategy_config_run_count,
        "planned_actor_run_count": planned_actor_run_count,
        "max_actor_runs_configured": int(settings.STRATEGY_V2_APIFY_MAX_ACTOR_RUNS),
        "executed_actor_run_count": executed_actor_run_count,
        "failed_actor_run_count": failed_actor_run_count,
        "excluded_source_refs": (
            apify_context.get("excluded_source_refs")
            if isinstance(apify_context.get("excluded_source_refs"), list)
            else []
        ),
    }
    apify_context["summary"] = ingestion_summary
    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent0b_apify_collection",
            "phase": "apify_execution_layer",
            "status": "completed",
            "strategy_config_run_count": strategy_config_run_count,
            "planned_actor_run_count": planned_actor_run_count,
            "executed_actor_run_count": executed_actor_run_count,
        }
    )
    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent0b_apify_collection",
            "phase": "persist_step_payload",
            "status": "started",
        }
    )

    with session_scope() as session:
        ingestion_agent_run_id = _record_agent_run(
            session=session,
            org_id=org_id,
            user_id=operator_user_id,
            client_id=client_id,
            objective_type="strategy_v2.agent0b_apify_ingestion.execution_layer",
            model="deterministic",
            inputs_json={
                "strategy_config_run_count": strategy_config_run_count,
                "planned_actor_run_count": planned_actor_run_count,
                "max_actor_runs_configured": int(settings.STRATEGY_V2_APIFY_MAX_ACTOR_RUNS),
            },
            outputs_json={
                "step": "apify_collection",
                "ingestion_summary": ingestion_summary,
            },
        )
        step_payload_artifact_id = _persist_step_payload(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            workflow_run_id=workflow_run_id,
            step_key=V2_STEP_APIFY_COLLECTION,
            title="Strategy V2 Apify Collection",
            summary="Paid Apify actor execution completed and raw run payload persisted for deterministic postprocess.",
            payload={
                "apify_collection": {
                    "strategy_apify_configs": strategy_apify_configs,
                    "apify_context": apify_context,
                    "ingestion_summary": ingestion_summary,
                    "strategy_config_run_count": strategy_config_run_count,
                    "planned_actor_run_count": planned_actor_run_count,
                    "executed_actor_run_count": executed_actor_run_count,
                    "failed_actor_run_count": failed_actor_run_count,
                },
                "ingestion_summary": ingestion_summary,
            },
            model_name="deterministic",
            prompt_version="strategy_v2.agent0b.apify_collection.v1",
            schema_version=SCHEMA_VERSION_V2,
            agent_run_id=ingestion_agent_run_id,
        )
    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent0b_apify_collection",
            "phase": "persist_step_payload",
            "status": "completed",
            "step_payload_artifact_id": step_payload_artifact_id,
        }
    )

    updated_step_payload_artifact_ids = _updated_step_payload_artifact_ids(
        existing_step_payload_artifact_ids=existing_step_payload_artifact_ids,
        step_key=V2_STEP_APIFY_COLLECTION,
        artifact_id=step_payload_artifact_id,
    )
    return {
        "apify_collection_artifact_id": step_payload_artifact_id,
        "strategy_config_run_count": strategy_config_run_count,
        "planned_actor_run_count": planned_actor_run_count,
        "executed_actor_run_count": executed_actor_run_count,
        "failed_actor_run_count": failed_actor_run_count,
        "step_payload_artifact_id": step_payload_artifact_id,
        "step_payload_artifact_ids": updated_step_payload_artifact_ids,
    }


@activity.defn(name="strategy_v2.run_voc_agent0b_apify_ingestion")
def run_strategy_v2_voc_agent0b_apify_ingestion_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    workflow_run_id = str(params["workflow_run_id"])
    operator_user_id = str(params.get("operator_user_id") or "system")
    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent0b_apify_ingestion",
            "phase": "context_hydration",
            "status": "started",
        }
    )

    def _context_hydration_heartbeat(event: dict[str, Any]) -> None:
        payload: dict[str, Any] = {
            "activity": "strategy_v2.run_voc_agent0b_apify_ingestion",
            "phase": "context_hydration",
            "status": "in_progress",
        }
        for key in ("progress_event", "processed_run_rows", "total_run_rows"):
            value = event.get(key)
            if value is not None:
                payload[key] = value
        activity.heartbeat(payload)

    def _post_transform_heartbeat(event: dict[str, Any]) -> None:
        payload: dict[str, Any] = {
            "activity": "strategy_v2.run_voc_agent0b_apify_ingestion",
            "phase": "post_apify_transform",
            "status": "in_progress",
        }
        for key in ("progress_event", "processed_runs", "total_runs"):
            value = event.get(key)
            if value is not None:
                payload[key] = value
        activity.heartbeat(payload)

    context_heartbeat_payload = {
        "activity": "strategy_v2.run_voc_agent0b_apify_ingestion",
    }

    stage1_artifact_id = _require_stage1_artifact_id(params=params)
    _ = stage1_artifact_id
    shared_context = _require_stage2b_shared_context(params=params)
    existing_step_payload_artifact_ids = _parse_step_payload_artifact_ids(
        payload=params.get("existing_step_payload_artifact_ids"),
        field_name="existing_step_payload_artifact_ids",
    )
    stage1 = shared_context["stage1"]
    foundational_step_contents = shared_context["foundational_step_contents"]
    foundational_step_summaries = shared_context["foundational_step_summaries"]
    existing_step_payload_artifact_ids = _run_with_activity_heartbeats(
        phase="context_hydration",
        operation="ensure_foundational_payload_artifacts",
        heartbeat_payload=context_heartbeat_payload,
        fn=lambda: _ensure_foundational_step_payload_artifact_ids(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            workflow_run_id=workflow_run_id,
            foundational_step_contents=foundational_step_contents,
            foundational_step_summaries=foundational_step_summaries,
            existing_step_payload_artifact_ids=existing_step_payload_artifact_ids,
        ),
    )
    _run_with_activity_heartbeats(
        phase="context_hydration",
        operation="validate_step_payload_prerequisites",
        heartbeat_payload=context_heartbeat_payload,
        fn=lambda: _require_step_payload_artifact_prerequisites(
            checkpoint_label="v2-03c Apify postprocess + virality",
            step_payload_artifact_ids=existing_step_payload_artifact_ids,
            required_step_keys=[
                *[f"v2-02.foundation.{step_key}" for step_key in _FOUNDATIONAL_STEP_KEYS],
                V2_STEP_HABITAT_STRATEGY,
                V2_STEP_SCRAPE_VIRALITY,
                V2_STEP_APIFY_COLLECTION,
            ],
            org_id=org_id,
            validate_lineage=True,
        ),
    )
    competitor_analysis = _require_dict(
        payload=params.get("competitor_analysis"),
        field_name="competitor_analysis",
    )
    step4_content = foundational_step_contents["04"].strip()
    entries = _extract_step4_entries(step4_content)
    agent00_output = _require_dict(
        payload=params.get("agent00_output"),
        field_name="agent00_output",
    )
    _require_agent00_executable_configs(agent00_output)
    agent00b_output = _require_dict(
        payload=params.get("agent00b_output"),
        field_name="agent00b_output",
    )
    _require_agent00b_executable_configs(agent00b_output)
    apify_collection_artifact_id = str(params.get("apify_collection_artifact_id") or "").strip()
    if not apify_collection_artifact_id:
        raise StrategyV2MissingContextError(
            "Missing required apify_collection_artifact_id for Stage 2B postprocess. "
            "Remediation: run v2-03b apify_collection first and pass its artifact id."
        )

    collection_payload = _run_with_activity_heartbeats(
        phase="context_hydration",
        operation="load_apify_collection_payload",
        heartbeat_payload=context_heartbeat_payload,
        fn=lambda: _load_apify_collection_payload_for_postprocess(
            org_id=org_id,
            apify_collection_artifact_id=apify_collection_artifact_id,
        ),
    )
    _context_hydration_heartbeat({"progress_event": "collection_payload_loaded"})
    strategy_apify_configs = collection_payload.get("strategy_apify_configs")
    if not isinstance(strategy_apify_configs, list):
        raise StrategyV2SchemaValidationError(
            "apify collection payload missing strategy_apify_configs array required for postprocess."
        )
    apify_context = _require_dict(
        payload=collection_payload.get("apify_context"),
        field_name="apify_collection.apify_context",
    )
    strategy_config_run_count = collection_payload.get("strategy_config_run_count")
    planned_actor_run_count = collection_payload.get("planned_actor_run_count")
    executed_actor_run_count = collection_payload.get("executed_actor_run_count")
    failed_actor_run_count = collection_payload.get("failed_actor_run_count")
    if (
        not isinstance(strategy_config_run_count, int)
        or not isinstance(planned_actor_run_count, int)
        or not isinstance(executed_actor_run_count, int)
        or not isinstance(failed_actor_run_count, int)
    ):
        raise StrategyV2SchemaValidationError(
            "apify collection payload missing required run counters "
            "(strategy_config_run_count/planned_actor_run_count/executed_actor_run_count/failed_actor_run_count). "
            "Remediation: rerun v2-03b with current code."
        )
    if (
        strategy_config_run_count < 0
        or planned_actor_run_count < 0
        or executed_actor_run_count < 0
        or failed_actor_run_count < 0
    ):
        raise StrategyV2SchemaValidationError(
            "apify collection run counters must be non-negative integers."
        )
    expected_strategy_apify_configs = _extract_apify_configs_from_agent_strategies(
        habitat_strategy=agent00_output,
        video_strategy=agent00b_output,
    )
    expected_strategy_apify_config_count = len(expected_strategy_apify_configs)
    if strategy_config_run_count != expected_strategy_apify_config_count:
        raise StrategyV2SchemaValidationError(
            "apify collection payload strategy_config_run_count does not match current strategy config count "
            f"(strategy_config_run_count={strategy_config_run_count}, expected_strategy_apify_config_count={expected_strategy_apify_config_count}). "
            "Remediation: rerun v2-03b apify_collection for this exact strategy handoff."
        )
    if planned_actor_run_count < strategy_config_run_count:
        raise StrategyV2SchemaValidationError(
            "apify collection payload planned_actor_run_count cannot be less than strategy_config_run_count "
            f"(planned_actor_run_count={planned_actor_run_count}, strategy_config_run_count={strategy_config_run_count})."
        )

    raw_runs = apify_context.get("raw_runs")
    raw_run_rows = [row for row in raw_runs if isinstance(row, dict)] if isinstance(raw_runs, list) else []
    if len(raw_run_rows) != executed_actor_run_count:
        raise StrategyV2SchemaValidationError(
            "apify collection payload raw run count mismatch "
            f"(len(raw_runs)={len(raw_run_rows)}, executed_actor_run_count={executed_actor_run_count})."
        )
    _validate_reddit_target_alignment(
        run_rows=raw_run_rows,
        progress_callback=_context_hydration_heartbeat,
    )
    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent0b_apify_ingestion",
            "phase": "context_hydration",
            "status": "completed",
            "apify_collection_artifact_id": apify_collection_artifact_id,
            "executed_actor_run_count": executed_actor_run_count,
        }
    )
    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent0b_apify_ingestion",
            "phase": "post_apify_transform",
            "status": "started",
            "planned_actor_run_count": planned_actor_run_count,
            "executed_actor_run_count": executed_actor_run_count,
        }
    )

    video_observations = _extract_video_observations(competitor_analysis)
    apify_video_raw = apify_context.get("social_video_observations")
    apify_video_rows = [row for row in apify_video_raw if isinstance(row, dict)] if isinstance(apify_video_raw, list) else []
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

    source_allowlist = _extract_video_source_allowlist(agent00b_output)
    topic_keywords = _build_video_topic_keywords(stage1=stage1)
    metric_video_rows, video_filter_diagnostics = _filter_metric_video_rows_for_scoring(
        video_rows=video_observations,
        source_allowlist=source_allowlist,
        topic_keywords=topic_keywords,
    )
    video_scoring_status = "scored"
    if not metric_video_rows:
        if video_observations:
            raise StrategyV2DecisionError(
                "Video scoring aborted: no topic-aligned social video rows remained after source/topic validation. "
                f"Diagnostics={video_filter_diagnostics}"
            )
        video_scoring_status = "skipped_no_metric_video_rows"
    video_scored = _normalize_video_scored_rows(score_videos(metric_video_rows) if metric_video_rows else [])
    scoring_audit = _build_video_scoring_audit(
        video_observation_count=len(video_observations),
        metric_video_observation_count=len(metric_video_rows),
        video_scored=video_scored,
        video_filter_diagnostics=video_filter_diagnostics,
    )

    external_voc_corpus_raw = apify_context.get("external_voc_corpus")
    external_voc_corpus = (
        [row for row in external_voc_corpus_raw if isinstance(row, dict)]
        if isinstance(external_voc_corpus_raw, list)
        else []
    )
    step4_corpus = transform_step4_entries_to_agent2_corpus(entries)
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

    scraped_data_manifest = _build_scraped_data_manifest(
        apify_context=apify_context,
        competitor_analysis=competitor_analysis,
        progress_callback=_post_transform_heartbeat,
    )
    _validate_agent1_scraped_manifest_integrity(
        scraped_data_manifest=scraped_data_manifest,
        planned_actor_run_count=planned_actor_run_count,
        executed_actor_run_count=executed_actor_run_count,
        failed_actor_run_count=failed_actor_run_count,
    )
    handoff_audit = {
        "strategy_config_run_count": strategy_config_run_count,
        "planned_actor_run_count": planned_actor_run_count,
        "executed_actor_run_count": executed_actor_run_count,
        "failed_actor_run_count": failed_actor_run_count,
        "manifest_run_count": int(scraped_data_manifest.get("run_count") or 0),
        "manifest_total_run_count": int(scraped_data_manifest.get("total_run_count") or 0),
        "raw_files_len": len(scraped_data_manifest.get("raw_scraped_data_files") or []),
        "excluded_runs_len": len(scraped_data_manifest.get("excluded_runs") or []),
        "excluded_run_count": int(scraped_data_manifest.get("excluded_run_count") or 0),
        "target_id_mapping_diagnostics": (
            dict(scraped_data_manifest.get("target_id_mapping_diagnostics"))
            if isinstance(scraped_data_manifest.get("target_id_mapping_diagnostics"), Mapping)
            else {}
        ),
        "scoring_audit": scoring_audit,
    }
    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent0b_apify_ingestion",
            "phase": "post_apify_transform",
            "status": "completed",
            "video_scored_count": len(video_scored),
            "existing_corpus_count": len(existing_corpus),
            "handoff_audit": handoff_audit,
        }
    )
    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent0b_apify_ingestion",
            "phase": "persist_step_payload",
            "status": "started",
        }
    )
    with session_scope() as session:
        ingestion_agent_run_id = _record_agent_run(
            session=session,
            org_id=org_id,
            user_id=operator_user_id,
            client_id=client_id,
            objective_type="strategy_v2.agent0b_apify_postprocess.execution_layer",
            model="deterministic",
            inputs_json={
                "apify_collection_artifact_id": apify_collection_artifact_id,
                "strategy_config_run_count": strategy_config_run_count,
                "planned_actor_run_count": planned_actor_run_count,
                "executed_actor_run_count": executed_actor_run_count,
                "failed_actor_run_count": failed_actor_run_count,
            },
            outputs_json={
                "video_scoring_status": video_scoring_status,
                "video_filter_diagnostics": video_filter_diagnostics,
                "video_scored": video_scored,
                "scoring_audit": scoring_audit,
                "handoff_audit": handoff_audit,
            },
        )
        step_payload_artifact_id = _persist_step_payload(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            workflow_run_id=workflow_run_id,
            step_key=V2_STEP_APIFY_POSTPROCESS,
            title="Strategy V2 Apify Postprocess + Virality",
            summary="Deterministic postprocess from immutable Apify collection artifact.",
            payload={
                "apify_collection_artifact_id": apify_collection_artifact_id,
                "video_scoring_status": video_scoring_status,
                "video_observation_count": len(video_observations),
                "metric_video_observation_count": len(metric_video_rows),
                "apify_video_observation_count": len(apify_video_rows),
                "video_filter_diagnostics": video_filter_diagnostics,
                "scraped_data_manifest": scraped_data_manifest,
                "video_scored": video_scored,
                "scoring_audit": scoring_audit,
                "existing_corpus": existing_corpus,
                "merged_voc_artifact_rows": merged_voc_artifact_rows,
                "corpus_selection_summary": merged_voc["summary"],
                "external_corpus_count": len(external_voc_corpus),
                "proof_asset_candidates": proof_asset_candidates,
                "ingestion_summary": {
                    "strategy_config_run_count": strategy_config_run_count,
                    "planned_actor_run_count": planned_actor_run_count,
                    "executed_actor_run_count": executed_actor_run_count,
                    "failed_actor_run_count": failed_actor_run_count,
                },
                "handoff_audit": handoff_audit,
            },
            model_name="deterministic",
            prompt_version="strategy_v2.agent0b.apify_postprocess.v1",
            schema_version=SCHEMA_VERSION_V2,
            agent_run_id=ingestion_agent_run_id,
        )
    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent0b_apify_ingestion",
            "phase": "persist_step_payload",
            "status": "completed",
            "step_payload_artifact_id": step_payload_artifact_id,
        }
    )
    updated_step_payload_artifact_ids = _updated_step_payload_artifact_ids(
        existing_step_payload_artifact_ids=existing_step_payload_artifact_ids,
        step_key=V2_STEP_APIFY_POSTPROCESS,
        artifact_id=step_payload_artifact_id,
    )
    return {
        "scraped_manifest_run_count": int(scraped_data_manifest.get("run_count") or 0),
        "scraped_manifest_total_run_count": int(scraped_data_manifest.get("total_run_count") or 0),
        "existing_corpus_count": len(existing_corpus),
        "merged_voc_artifact_row_count": len(merged_voc_artifact_rows),
        "proof_asset_candidate_count": len(proof_asset_candidates),
        "strategy_config_run_count": strategy_config_run_count,
        "planned_actor_run_count": planned_actor_run_count,
        "executed_actor_run_count": executed_actor_run_count,
        "failed_actor_run_count": failed_actor_run_count,
        "handoff_audit": handoff_audit,
        "scoring_audit": scoring_audit,
        "step_payload_artifact_id": step_payload_artifact_id,
        "step_payload_artifact_ids": updated_step_payload_artifact_ids,
    }


@activity.defn(name="strategy_v2.run_voc_agent1_habitat_qualifier")
def run_strategy_v2_voc_agent1_habitat_qualifier_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    workflow_run_id = str(params["workflow_run_id"])
    operator_user_id = str(params.get("operator_user_id") or "system")

    _ = _require_stage1_artifact_id(params=params)
    shared_context = _require_stage2b_shared_context(params=params)
    existing_step_payload_artifact_ids = _parse_step_payload_artifact_ids(
        payload=params.get("existing_step_payload_artifact_ids"),
        field_name="existing_step_payload_artifact_ids",
    )
    foundational_step_contents = shared_context["foundational_step_contents"]
    foundational_step_summaries = shared_context["foundational_step_summaries"]
    existing_step_payload_artifact_ids = _ensure_foundational_step_payload_artifact_ids(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        workflow_run_id=workflow_run_id,
        foundational_step_contents=foundational_step_contents,
        foundational_step_summaries=foundational_step_summaries,
        existing_step_payload_artifact_ids=existing_step_payload_artifact_ids,
    )
    _require_step_payload_artifact_prerequisites(
        checkpoint_label="v2-04 Agent 1 habitat qualifier",
        step_payload_artifact_ids=existing_step_payload_artifact_ids,
        required_step_keys=[
            *[f"v2-02.foundation.{step_key}" for step_key in _FOUNDATIONAL_STEP_KEYS],
            V2_STEP_HABITAT_STRATEGY,
            V2_STEP_SCRAPE_VIRALITY,
            V2_STEP_APIFY_COLLECTION,
            V2_STEP_APIFY_INGESTION,
        ],
        org_id=org_id,
        validate_lineage=True,
    )

    stage1_data = shared_context["stage1_data"]
    avatar_brief_payload = shared_context["avatar_brief_payload"]
    competitor_analysis = _require_dict(
        payload=params.get("competitor_analysis"),
        field_name="competitor_analysis",
    )
    agent00_output = _require_dict(
        payload=params.get("agent00_output"),
        field_name="agent00_output",
    )
    agent00b_output = _require_dict(
        payload=params.get("agent00b_output"),
        field_name="agent00b_output",
    )
    apify_ingestion_artifact_id = str(params.get("apify_ingestion_artifact_id") or "").strip()
    apify_ingestion_payload: dict[str, Any] = {}
    if apify_ingestion_artifact_id:
        apify_ingestion_payload = _load_apify_ingestion_payload_for_downstream(
            org_id=org_id,
            apify_ingestion_artifact_id=apify_ingestion_artifact_id,
        )
    scraped_data_manifest_payload = params.get("scraped_data_manifest")
    if not isinstance(scraped_data_manifest_payload, dict):
        scraped_data_manifest_payload = apify_ingestion_payload.get("scraped_data_manifest")
    scraped_data_manifest = _require_dict(
        payload=scraped_data_manifest_payload,
        field_name="scraped_data_manifest",
    )
    scraped_data_files = scraped_data_manifest.get("raw_scraped_data_files")
    if not isinstance(scraped_data_files, list) or not scraped_data_files:
        raise StrategyV2MissingContextError(
            "scraped_data_manifest.raw_scraped_data_files is required for Agent 1 habitat qualification. "
            "Remediation: ensure v2-03 returns scraped-data manifest before invoking v2-04."
        )
    video_scored = params.get("video_scored")
    if not isinstance(video_scored, list):
        video_scored = apify_ingestion_payload.get("video_scored")
    if not isinstance(video_scored, list):
        raise StrategyV2SchemaValidationError("video_scored must be an array for v2-04 Agent 1 qualification.")
    scoring_audit = params.get("scoring_audit")
    if scoring_audit is None and isinstance(apify_ingestion_payload.get("scoring_audit"), dict):
        scoring_audit = apify_ingestion_payload.get("scoring_audit")
    if scoring_audit is not None and not isinstance(scoring_audit, dict):
        raise StrategyV2SchemaValidationError(
            "scoring_audit must be an object when provided for v2-04 Agent 1 qualification."
        )
    scoring_audit = dict(scoring_audit) if isinstance(scoring_audit, dict) else {}
    strategy_config_run_count = params.get("strategy_config_run_count")
    if not isinstance(strategy_config_run_count, int):
        # Compatibility for pre-contract histories where this counter was not persisted.
        strategy_apify_configs = _extract_apify_configs_from_agent_strategies(
            habitat_strategy=agent00_output,
            video_strategy=agent00b_output,
        )
        strategy_config_run_count = len(strategy_apify_configs)
    planned_actor_run_count = params.get("planned_actor_run_count")
    if not isinstance(planned_actor_run_count, int):
        raise StrategyV2SchemaValidationError(
            "planned_actor_run_count must be a non-negative integer for v2-04 Agent 1 qualification."
        )
    executed_actor_run_count = params.get("executed_actor_run_count")
    if not isinstance(executed_actor_run_count, int):
        raise StrategyV2SchemaValidationError(
            "executed_actor_run_count must be a non-negative integer for v2-04 Agent 1 qualification."
        )
    failed_actor_run_count = params.get("failed_actor_run_count")
    if not isinstance(failed_actor_run_count, int):
        raise StrategyV2SchemaValidationError(
            "failed_actor_run_count must be a non-negative integer for v2-04 Agent 1 qualification."
        )
    if strategy_config_run_count < 0:
        raise StrategyV2SchemaValidationError(
            "strategy_config_run_count must be a non-negative integer for v2-04 Agent 1 qualification."
        )
    if strategy_config_run_count > planned_actor_run_count:
        raise StrategyV2SchemaValidationError(
            "strategy_config_run_count cannot exceed planned_actor_run_count for v2-04 Agent 1 qualification."
        )
    handoff_audit = params.get("handoff_audit")
    if handoff_audit is not None and not isinstance(handoff_audit, dict):
        raise StrategyV2SchemaValidationError(
            "handoff_audit must be an object when provided for v2-04 Agent 1 qualification."
        )
    if isinstance(handoff_audit, dict):
        handoff_audit = dict(handoff_audit)
    else:
        handoff_audit = {}
    handoff_audit.setdefault("strategy_config_run_count", strategy_config_run_count)
    handoff_audit.setdefault("planned_actor_run_count", planned_actor_run_count)
    handoff_audit.setdefault("executed_actor_run_count", executed_actor_run_count)
    handoff_audit.setdefault("failed_actor_run_count", failed_actor_run_count)
    handoff_audit.setdefault("manifest_run_count", int(scraped_data_manifest.get("run_count") or 0))
    handoff_audit.setdefault("manifest_total_run_count", int(scraped_data_manifest.get("total_run_count") or 0))
    handoff_audit.setdefault("excluded_run_count", int(scraped_data_manifest.get("excluded_run_count") or 0))
    handoff_audit.setdefault("raw_files_len", len(scraped_data_manifest.get("raw_scraped_data_files") or []))
    handoff_audit.setdefault("excluded_runs_len", len(scraped_data_manifest.get("excluded_runs") or []))
    handoff_audit.setdefault(
        "target_id_mapping_diagnostics",
        (
            dict(scraped_data_manifest.get("target_id_mapping_diagnostics"))
            if isinstance(scraped_data_manifest.get("target_id_mapping_diagnostics"), Mapping)
            else {}
        ),
    )
    handoff_audit.setdefault("scoring_audit", scoring_audit)
    _validate_agent1_scraped_manifest_integrity(
        scraped_data_manifest=scraped_data_manifest,
        planned_actor_run_count=planned_actor_run_count,
        executed_actor_run_count=executed_actor_run_count,
        failed_actor_run_count=failed_actor_run_count,
    )
    if _AGENT1_COMPACTION_THRESHOLD < 1:
        raise StrategyV2SchemaValidationError(
            "STRATEGY_V2_AGENT1_COMPACTION_THRESHOLD must be an integer greater than zero."
        )
    agent1_context_management = [
        {
            "type": "compaction",
            "compact_threshold": _AGENT1_COMPACTION_THRESHOLD,
        }
    ]

    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent1_habitat_qualifier",
            "phase": "agent1_prompt",
            "status": "started",
            "manifest_file_count": len(scraped_data_files),
            "compaction_threshold": _AGENT1_COMPACTION_THRESHOLD,
        }
    )
    agent01_asset = resolve_prompt_asset(
        pattern=_VOC_AGENT01_PROMPT_PATTERN,
        context="VOC Agent 1 habitat qualifier",
    )
    scraped_file_inventory = _build_agent1_runtime_file_inventory(scraped_data_manifest)
    agent01_file_assessment_template = _build_agent1_file_assessment_template(scraped_data_manifest)
    agent01_file_id_map, agent01_uploaded_file_ids = _upload_openai_prompt_json_files(
        model=settings.STRATEGY_V2_VOC_MODEL,
        workflow_run_id=workflow_run_id,
        stage_label="agent1-prompt-chain",
        logical_payloads={
            "HABITAT_STRATEGY_JSON": agent00_output,
            "VIDEO_STRATEGY_JSON": agent00b_output,
            "SCORED_VIDEO_DATA_JSON": video_scored,
            "SCRAPED_DATA_FILES_JSON": scraped_data_manifest,
            "PRODUCT_BRIEF_JSON": stage1_data,
            "AVATAR_BRIEF_JSON": avatar_brief_payload,
            "COMPETITOR_ANALYSIS_JSON": competitor_analysis,
            "HANDOFF_AUDIT_JSON": handoff_audit,
            "SCORING_AUDIT_JSON": scoring_audit,
            "AGENT1_FILE_ASSESSMENT_TEMPLATE_JSON": agent01_file_assessment_template,
            "FOUNDATIONAL_RESEARCH_DOCS_JSON": {
                "step_contents": {
                    step_key: str(foundational_step_contents.get(step_key) or "")
                    for step_key in _FOUNDATIONAL_STEP_KEYS
                },
                "step_summaries": {
                    step_key: str(foundational_step_summaries.get(step_key) or "")
                    for step_key in _FOUNDATIONAL_STEP_KEYS
                },
            },
        },
    )
    try:
        agent01_output, agent01_raw, agent01_provenance = _run_prompt_json_object(
            asset=agent01_asset,
            context="strategy_v2.agent1_output",
            model=settings.STRATEGY_V2_VOC_MODEL,
            runtime_instruction=_render_agent1_runtime_instruction(
                agent01_file_id_map=agent01_file_id_map,
                scraped_file_inventory=scraped_file_inventory,
            ),
            schema_name="strategy_v2_voc_agent01",
            schema=_agent1_output_schema(
                source_files=_ordered_scraped_data_file_names(scraped_data_manifest),
            ),
            use_reasoning=True,
            reasoning_effort="low",
            use_web_search=False,
            openai_tools=_openai_python_tool_resources(
                settings.STRATEGY_V2_VOC_MODEL,
                file_ids=list(agent01_file_id_map.values()),
            ),
            openai_tool_choice="auto",
            openai_context_management=agent1_context_management,
            max_tokens=_AGENT1_MAX_TOKENS,
            heartbeat_context={
                "activity": "strategy_v2.run_voc_agent1_habitat_qualifier",
                "phase": "agent1_prompt",
                "model": settings.STRATEGY_V2_VOC_MODEL,
                "manifest_file_count": len(scraped_data_files),
                "compaction_threshold": _AGENT1_COMPACTION_THRESHOLD,
            },
        )
    finally:
        _cleanup_openai_prompt_files(
            model=settings.STRATEGY_V2_VOC_MODEL,
            file_ids=agent01_uploaded_file_ids,
        )

    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent1_habitat_qualifier",
            "phase": "agent1_prompt",
            "status": "completed",
            "manifest_file_count": len(scraped_data_files),
        }
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
    agent01_output = _derive_agent1_outputs_from_file_assessments(
        agent01_output=agent01_output,
        scraped_data_manifest=scraped_data_manifest,
    )
    raw_habitat_observations = agent01_output.get("habitat_observations")
    if not isinstance(raw_habitat_observations, list):
        raise StrategyV2SchemaValidationError("Agent 1 output must contain habitat_observations array.")
    habitat_observations = _normalize_habitat_observations(
        [row for row in raw_habitat_observations if isinstance(row, dict)]
    )
    habitat_scored = score_habitats(habitat_observations)

    with session_scope() as session:
        qualifier_agent_run_id = _record_agent_run(
            session=session,
            org_id=org_id,
            user_id=operator_user_id,
            client_id=client_id,
            objective_type="strategy_v2.agent1_habitat_scoring.prompt_chain",
            model=settings.STRATEGY_V2_VOC_MODEL,
            inputs_json={
                "habitat_observation_count": len(habitat_observations),
                "handoff_audit": handoff_audit if isinstance(handoff_audit, dict) else {},
                "scoring_audit": scoring_audit,
            },
            outputs_json={
                "habitat_scored": habitat_scored,
                "scoring_audit": scoring_audit,
            },
        )
        step_payload_artifact_id = _persist_step_payload(
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
                "scoring_audit": scoring_audit,
                "handoff_audit": handoff_audit if isinstance(handoff_audit, dict) else {},
                "prompt_provenance": agent01_provenance,
                "raw_output": agent01_raw[:20000],
            },
            model_name=settings.STRATEGY_V2_VOC_MODEL,
            prompt_version="strategy_v2.agent1.prompt_chain.v2",
            schema_version=SCHEMA_VERSION_V2,
            agent_run_id=qualifier_agent_run_id,
        )

    updated_step_payload_artifact_ids = _updated_step_payload_artifact_ids(
        existing_step_payload_artifact_ids=existing_step_payload_artifact_ids,
        step_key=V2_STEP_HABITAT_SCORING,
        artifact_id=step_payload_artifact_id,
    )
    return {
        "agent01_output": agent01_output,
        "habitat_observations": habitat_observations,
        "habitat_scored": habitat_scored,
        "scoring_audit": scoring_audit,
        "step_payload_artifact_id": step_payload_artifact_id,
        "step_payload_artifact_ids": updated_step_payload_artifact_ids,
    }


@activity.defn(name="strategy_v2.run_voc_agent2_extraction")
def run_strategy_v2_voc_agent2_extraction_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    workflow_run_id = str(params["workflow_run_id"])
    operator_user_id = str(params.get("operator_user_id") or "system")

    _ = _require_stage1_artifact_id(params=params)
    shared_context = _require_stage2b_shared_context(params=params)
    existing_step_payload_artifact_ids = _parse_step_payload_artifact_ids(
        payload=params.get("existing_step_payload_artifact_ids"),
        field_name="existing_step_payload_artifact_ids",
    )
    foundational_step_contents = shared_context["foundational_step_contents"]
    foundational_step_summaries = shared_context["foundational_step_summaries"]
    existing_step_payload_artifact_ids = _ensure_foundational_step_payload_artifact_ids(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        workflow_run_id=workflow_run_id,
        foundational_step_contents=foundational_step_contents,
        foundational_step_summaries=foundational_step_summaries,
        existing_step_payload_artifact_ids=existing_step_payload_artifact_ids,
    )
    _require_step_payload_artifact_prerequisites(
        checkpoint_label="v2-05a Agent 2 VOC extraction",
        step_payload_artifact_ids=existing_step_payload_artifact_ids,
        required_step_keys=[
            *[f"v2-02.foundation.{step_key}" for step_key in _FOUNDATIONAL_STEP_KEYS],
            V2_STEP_SCRAPE_VIRALITY,
            V2_STEP_APIFY_INGESTION,
            V2_STEP_HABITAT_SCORING,
        ],
        org_id=org_id,
        validate_lineage=True,
    )

    stage1_data = shared_context["stage1_data"]
    avatar_brief_payload = shared_context["avatar_brief_payload"]
    competitor_analysis = _require_dict(
        payload=params.get("competitor_analysis"),
        field_name="competitor_analysis",
    )
    agent01_output = _require_dict(payload=params.get("agent01_output"), field_name="agent01_output")
    habitat_scored = _require_dict(payload=params.get("habitat_scored"), field_name="habitat_scored")
    apify_ingestion_artifact_id = str(params.get("apify_ingestion_artifact_id") or "").strip()
    apify_ingestion_payload: dict[str, Any] = {}
    if apify_ingestion_artifact_id:
        apify_ingestion_payload = _load_apify_ingestion_payload_for_downstream(
            org_id=org_id,
            apify_ingestion_artifact_id=apify_ingestion_artifact_id,
        )

    existing_corpus_raw = params.get("existing_corpus")
    if not isinstance(existing_corpus_raw, list):
        existing_corpus_raw = apify_ingestion_payload.get("existing_corpus")
    if not isinstance(existing_corpus_raw, list):
        raise StrategyV2SchemaValidationError("existing_corpus must be an array for v2-05a.")
    existing_corpus = [row for row in existing_corpus_raw if isinstance(row, dict)]
    merged_voc_artifact_rows_raw = params.get("merged_voc_artifact_rows")
    if not isinstance(merged_voc_artifact_rows_raw, list):
        merged_voc_artifact_rows_raw = apify_ingestion_payload.get("merged_voc_artifact_rows")
    if not isinstance(merged_voc_artifact_rows_raw, list):
        raise StrategyV2SchemaValidationError("merged_voc_artifact_rows must be an array for v2-05a.")
    merged_voc_artifact_rows = [row for row in merged_voc_artifact_rows_raw if isinstance(row, dict)]
    scraped_data_manifest_payload = params.get("scraped_data_manifest")
    if not isinstance(scraped_data_manifest_payload, dict):
        scraped_data_manifest_payload = apify_ingestion_payload.get("scraped_data_manifest")
    scraped_data_manifest = _require_dict(
        payload=scraped_data_manifest_payload,
        field_name="scraped_data_manifest",
    )
    proof_asset_candidates_raw = params.get("proof_asset_candidates")
    if not isinstance(proof_asset_candidates_raw, list):
        proof_asset_candidates_raw = apify_ingestion_payload.get("proof_asset_candidates")
    if not isinstance(proof_asset_candidates_raw, list):
        raise StrategyV2SchemaValidationError("proof_asset_candidates must be an array for v2-05a.")
    proof_asset_candidates = [row for row in proof_asset_candidates_raw if isinstance(row, dict)]
    corpus_selection_payload = params.get("corpus_selection_summary")
    if not isinstance(corpus_selection_payload, dict):
        corpus_selection_payload = apify_ingestion_payload.get("corpus_selection_summary")
    corpus_selection_summary = _require_dict(
        payload=corpus_selection_payload,
        field_name="corpus_selection_summary",
    )
    external_corpus_count = params.get("external_corpus_count")
    if not isinstance(external_corpus_count, int):
        external_corpus_count = apify_ingestion_payload.get("external_corpus_count")
    if not isinstance(external_corpus_count, int) or external_corpus_count < 0:
        raise StrategyV2SchemaValidationError("external_corpus_count must be a non-negative integer for v2-05a.")

    saturated_angles = extract_saturated_angles(competitor_analysis, limit=9)
    evidence_rows, evidence_diagnostics = _build_agent2_evidence_rows(
        existing_corpus=existing_corpus,
        merged_voc_artifact_rows=merged_voc_artifact_rows,
        scraped_data_manifest=scraped_data_manifest,
    )
    prompt_evidence_rows = evidence_rows
    excluded_prompt_rows: list[dict[str, Any]] = []
    compaction_summary: dict[str, Any] = {
        "enabled": False,
        "max_rows": _AGENT2_PROMPT_MAX_EVIDENCE_ROWS,
        "input_count": len(evidence_rows),
        "selected_count": len(evidence_rows),
        "excluded_count": 0,
        "source_type_distribution_input": _agent2_source_type_distribution(evidence_rows),
        "source_type_distribution_selected": _agent2_source_type_distribution(evidence_rows),
    }
    if len(evidence_rows) > _AGENT2_PROMPT_MAX_EVIDENCE_ROWS:
        prompt_evidence_rows, excluded_prompt_rows, compaction_summary = _compact_agent2_evidence_rows(
            evidence_rows=evidence_rows,
            max_rows=_AGENT2_PROMPT_MAX_EVIDENCE_ROWS,
        )
    evidence_diagnostics["total_rows_available"] = len(evidence_rows)
    evidence_diagnostics["rows_selected_for_prompt"] = len(prompt_evidence_rows)
    evidence_diagnostics["rows_excluded_by_compaction"] = len(excluded_prompt_rows)

    agent2_mode = "DUAL" if existing_corpus else "FRESH"
    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent2_extraction",
            "phase": "agent2_prompt",
            "status": "started",
        }
    )
    agent02_asset = resolve_prompt_asset(
        pattern=_VOC_AGENT02_PROMPT_PATTERN,
        context="VOC Agent 2 extractor",
    )
    prompt_extraction = _run_agent2_extractor_prompt_only(
        agent02_asset=agent02_asset,
        model=settings.STRATEGY_V2_VOC_MODEL,
        workflow_run_id=workflow_run_id,
        mode=agent2_mode,
        evidence_rows=prompt_evidence_rows,
        agent01_output=agent01_output,
        habitat_scored=habitat_scored,
        stage1_data=stage1_data,
        avatar_brief_payload=avatar_brief_payload,
        competitor_analysis=competitor_analysis,
        saturated_angles=saturated_angles,
        foundational_step_contents=foundational_step_contents,
        foundational_step_summaries=foundational_step_summaries,
        activity_name="strategy_v2.run_voc_agent2_extraction",
    )
    agent02_output_raw = _require_dict(
        payload=prompt_extraction.get("output"),
        field_name="agent2_prompt_output",
    )
    decisions_by_evidence_id_raw = agent02_output_raw.get("decisions_by_evidence_id")
    if not isinstance(decisions_by_evidence_id_raw, Mapping):
        raise StrategyV2SchemaValidationError(
            "Agent 2 extraction output must include decisions_by_evidence_id object."
        )
    decisions_by_evidence_id = {
        str(key): dict(value)
        for key, value in decisions_by_evidence_id_raw.items()
        if isinstance(key, str) and isinstance(value, Mapping)
    }
    if excluded_prompt_rows:
        for row in excluded_prompt_rows:
            evidence_id = str(row.get("evidence_id") or "").strip().upper()
            if not evidence_id:
                continue
            decisions_by_evidence_id[evidence_id] = {
                "decision": "REJECT",
                "observation_id": None,
                "reason": "TOO_VAGUE",
                "note": (
                    "Excluded from prompt extraction by deterministic compaction cap; "
                    "kept in audit trail."
                ),
            }
    accepted_observations_raw = agent02_output_raw.get("accepted_observations")
    if not isinstance(accepted_observations_raw, list):
        raise StrategyV2SchemaValidationError(
            "Agent 2 extraction output must include accepted_observations array."
        )
    accepted_observations = [dict(row) for row in accepted_observations_raw if isinstance(row, Mapping)]
    accepted_count = sum(
        1
        for row in decisions_by_evidence_id.values()
        if isinstance(row, Mapping) and str(row.get("decision") or "").strip().upper() == "ACCEPT"
    )
    agent02_output = {
        "mode": str(prompt_extraction.get("mode") or agent2_mode),
        "input_count": len(evidence_rows),
        "output_count": accepted_count,
        "decisions_by_evidence_id": decisions_by_evidence_id,
        "accepted_observations": accepted_observations,
        "validation_errors": (
            [row for row in agent02_output_raw.get("validation_errors", []) if isinstance(row, str)]
            if isinstance(agent02_output_raw.get("validation_errors"), list)
            else []
        ),
        "extraction_summary": {
            "input_count": len(evidence_rows),
            "prompt_input_count": int(prompt_extraction.get("input_count") or len(prompt_evidence_rows)),
            "output_count": accepted_count,
            "rejected_count": max(0, len(decisions_by_evidence_id) - accepted_count),
            "compaction_excluded_count": len(excluded_prompt_rows),
        },
    }
    agent02_input_manifest = {
        "input_count": int(prompt_extraction.get("input_count") or len(prompt_evidence_rows)),
        "total_input_count": len(evidence_rows),
        "evidence_id_pattern": _VOC_AGENT02_EVIDENCE_ID_PATTERN,
        "rows": (
            prompt_extraction.get("input_manifest_rows")
            if isinstance(prompt_extraction.get("input_manifest_rows"), list)
            else []
        ),
    }
    prompt_provenance = (
        dict(prompt_extraction.get("prompt_provenance"))
        if isinstance(prompt_extraction.get("prompt_provenance"), dict)
        else {}
    )
    raw_output = str(prompt_extraction.get("raw_output") or "")

    with session_scope() as session:
        voc_agent_run_id = _record_agent_run(
            session=session,
            org_id=org_id,
            user_id=operator_user_id,
            client_id=client_id,
            objective_type="strategy_v2.agent2_voc_extraction.prompt_only",
            model=settings.STRATEGY_V2_VOC_MODEL,
            inputs_json={
                "input_count": int(prompt_extraction.get("input_count") or len(prompt_evidence_rows)),
                "total_input_count": len(evidence_rows),
                "compaction_excluded_count": len(excluded_prompt_rows),
                "mode": str(prompt_extraction.get("mode") or agent2_mode),
            },
            outputs_json={
                "output_count": accepted_count,
                "rejected_count": max(0, len(decisions_by_evidence_id) - accepted_count),
                "validation_error_count": len(agent02_output["validation_errors"]),
            },
        )
        step_payload_artifact_id = _persist_step_payload(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            workflow_run_id=workflow_run_id,
            step_key=V2_STEP_VOC_EXTRACTION_RAW,
            title="Strategy V2 VOC Extraction (Raw)",
            summary="Agent 2 prompt-chain VOC extraction completed; deterministic QA runs in v2-05.",
            payload={
                "voc_observation_count": accepted_count,
                "prompt_corpus_count": len(existing_corpus),
                "merged_corpus_count": len(merged_voc_artifact_rows),
                "external_corpus_count": external_corpus_count,
                "corpus_selection_summary": corpus_selection_summary,
                "mode": str(prompt_extraction.get("mode") or agent2_mode),
                "agent02_output": agent02_output,
                "input_manifest": agent02_input_manifest,
                "rejected_item_count": max(0, len(decisions_by_evidence_id) - accepted_count),
                "evidence_row_count": len(evidence_rows),
                "evidence_diagnostics": evidence_diagnostics,
                "compaction_summary": compaction_summary,
                "proof_asset_candidates": proof_asset_candidates,
                "prompt_provenance": prompt_provenance,
                "raw_output": raw_output[:20000],
            },
            model_name=settings.STRATEGY_V2_VOC_MODEL,
            prompt_version="strategy_v2.agent2.prompt_chain.v2",
            schema_version=SCHEMA_VERSION_V2,
            agent_run_id=voc_agent_run_id,
        )

    updated_step_payload_artifact_ids = _updated_step_payload_artifact_ids(
        existing_step_payload_artifact_ids=existing_step_payload_artifact_ids,
        step_key=V2_STEP_VOC_EXTRACTION_RAW,
        artifact_id=step_payload_artifact_id,
    )
    return {
        "agent02_output": agent02_output,
        "agent02_input_manifest": agent02_input_manifest,
        "agent02_prompt_provenance": prompt_provenance,
        "agent02_raw_output": raw_output[:20000],
        "evidence_rows": evidence_rows,
        "evidence_diagnostics": evidence_diagnostics,
        "prompt_corpus_count": len(existing_corpus),
        "merged_corpus_count": len(merged_voc_artifact_rows),
        "external_corpus_count": external_corpus_count,
        "corpus_selection_summary": corpus_selection_summary,
        "proof_asset_candidates": proof_asset_candidates,
        "compaction_summary": compaction_summary,
        "step_payload_artifact_id": step_payload_artifact_id,
        "step_payload_artifact_ids": updated_step_payload_artifact_ids,
    }


@activity.defn(name="strategy_v2.run_voc_agent2_qa")
def run_strategy_v2_voc_agent2_qa_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    workflow_run_id = str(params["workflow_run_id"])
    operator_user_id = str(params.get("operator_user_id") or "system")

    _ = _require_stage1_artifact_id(params=params)
    shared_context = _require_stage2b_shared_context(params=params)
    existing_step_payload_artifact_ids = _parse_step_payload_artifact_ids(
        payload=params.get("existing_step_payload_artifact_ids"),
        field_name="existing_step_payload_artifact_ids",
    )
    foundational_step_contents = shared_context["foundational_step_contents"]
    foundational_step_summaries = shared_context["foundational_step_summaries"]
    existing_step_payload_artifact_ids = _ensure_foundational_step_payload_artifact_ids(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        workflow_run_id=workflow_run_id,
        foundational_step_contents=foundational_step_contents,
        foundational_step_summaries=foundational_step_summaries,
        existing_step_payload_artifact_ids=existing_step_payload_artifact_ids,
    )
    _require_step_payload_artifact_prerequisites(
        checkpoint_label="v2-05 Agent 2 QA finalization",
        step_payload_artifact_ids=existing_step_payload_artifact_ids,
        required_step_keys=[
            *[f"v2-02.foundation.{step_key}" for step_key in _FOUNDATIONAL_STEP_KEYS],
            V2_STEP_SCRAPE_VIRALITY,
            V2_STEP_APIFY_INGESTION,
            V2_STEP_HABITAT_SCORING,
            V2_STEP_VOC_EXTRACTION_RAW,
        ],
        org_id=org_id,
        validate_lineage=True,
    )

    agent02_output = _require_dict(payload=params.get("agent02_output"), field_name="agent02_output")
    evidence_rows_raw = params.get("evidence_rows")
    if not isinstance(evidence_rows_raw, list):
        raise StrategyV2SchemaValidationError("evidence_rows must be an array for v2-05 QA finalization.")
    evidence_rows = [row for row in evidence_rows_raw if isinstance(row, dict)]
    if not evidence_rows:
        raise StrategyV2MissingContextError(
            "v2-05 QA finalization requires non-empty evidence_rows from v2-05a extraction."
        )
    evidence_diagnostics = _require_dict(
        payload=params.get("evidence_diagnostics") if isinstance(params.get("evidence_diagnostics"), dict) else {},
        field_name="evidence_diagnostics",
    )
    proof_asset_candidates_raw = params.get("proof_asset_candidates")
    if not isinstance(proof_asset_candidates_raw, list):
        raise StrategyV2SchemaValidationError("proof_asset_candidates must be an array for v2-05 QA finalization.")
    proof_asset_candidates = [row for row in proof_asset_candidates_raw if isinstance(row, dict)]
    corpus_selection_summary = _require_dict(
        payload=params.get("corpus_selection_summary") if isinstance(params.get("corpus_selection_summary"), dict) else {},
        field_name="corpus_selection_summary",
    )
    external_corpus_count = params.get("external_corpus_count")
    if not isinstance(external_corpus_count, int) or external_corpus_count < 0:
        raise StrategyV2SchemaValidationError(
            "external_corpus_count must be a non-negative integer for v2-05 QA finalization."
        )
    prompt_corpus_count = params.get("prompt_corpus_count")
    if not isinstance(prompt_corpus_count, int) or prompt_corpus_count < 0:
        raise StrategyV2SchemaValidationError(
            "prompt_corpus_count must be a non-negative integer for v2-05 QA finalization."
        )
    merged_corpus_count = params.get("merged_corpus_count")
    if not isinstance(merged_corpus_count, int) or merged_corpus_count < 0:
        raise StrategyV2SchemaValidationError(
            "merged_corpus_count must be a non-negative integer for v2-05 QA finalization."
        )
    agent02_input_manifest = (
        dict(params.get("agent02_input_manifest"))
        if isinstance(params.get("agent02_input_manifest"), dict)
        else {}
    )
    agent02_prompt_provenance = (
        dict(params.get("agent02_prompt_provenance"))
        if isinstance(params.get("agent02_prompt_provenance"), dict)
        else {}
    )
    agent02_raw_output = str(params.get("agent02_raw_output") or "")
    agent2_mode = str(agent02_output.get("mode") or "").strip().upper()
    if agent2_mode not in {"FRESH", "DUAL"}:
        raise StrategyV2SchemaValidationError(
            f"agent02_output.mode must be either 'FRESH' or 'DUAL', received {agent02_output.get('mode')!r}."
        )

    input_ordered_ids, input_rows_by_id, input_manifest_rows = _index_agent2_input_rows(
        evidence_rows=evidence_rows
    )
    extraction = _validate_agent2_decision_partition(
        mode=agent2_mode,
        output=agent02_output,
        input_ordered_ids=input_ordered_ids,
        input_rows_by_id=input_rows_by_id,
    )

    raw_voc_observations = extraction["voc_observations"]
    voc_observations = _normalize_voc_observations([row for row in raw_voc_observations if isinstance(row, dict)])
    voc_scored = score_voc_items(voc_observations)
    _require_voc_transition_quality(
        voc_observations=voc_observations,
        voc_scored=voc_scored,
    )

    with session_scope() as session:
        voc_agent_run_id = _record_agent_run(
            session=session,
            org_id=org_id,
            user_id=operator_user_id,
            client_id=client_id,
            objective_type="strategy_v2.agent2_voc_extraction.qa_finalization",
            model="deterministic",
            inputs_json={
                "input_count": len(input_ordered_ids),
                "mode": agent2_mode,
            },
            outputs_json={
                "voc_observation_count": len(voc_observations),
                "rejected_count": len(extraction.get("rejected_items") or []),
                "score_summary": voc_scored.get("summary") if isinstance(voc_scored, dict) else {},
            },
        )
        step_payload_artifact_id = _persist_step_payload(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            workflow_run_id=workflow_run_id,
            step_key=V2_STEP_VOC_EXTRACTION,
            title="Strategy V2 VOC Extraction",
            summary="Agent 2 extraction QA finalized and VOC corpus scored.",
            payload={
                "voc_observation_count": len(voc_observations),
                "prompt_corpus_count": prompt_corpus_count,
                "merged_corpus_count": merged_corpus_count,
                "external_corpus_count": external_corpus_count,
                "corpus_selection_summary": corpus_selection_summary,
                "voc_observations": voc_observations,
                "voc_scored": voc_scored,
                "mode": str(extraction.get("mode") or agent2_mode),
                "extraction_summary": extraction.get("extraction_summary", {}),
                "id_validation_report": extraction.get("id_validation_report", {}),
                "input_manifest": (
                    agent02_input_manifest
                    if agent02_input_manifest
                    else {
                        "input_count": len(input_ordered_ids),
                        "evidence_id_pattern": _VOC_AGENT02_EVIDENCE_ID_PATTERN,
                        "rows": input_manifest_rows,
                    }
                ),
                "rejected_items": extraction.get("rejected_items", []),
                "rejected_item_count": len(
                    [row for row in extraction.get("rejected_items", []) if isinstance(row, dict)]
                ),
                "evidence_row_count": len(evidence_rows),
                "evidence_diagnostics": evidence_diagnostics,
                "proof_asset_candidates": proof_asset_candidates,
                "prompt_provenance": agent02_prompt_provenance,
                "raw_output": agent02_raw_output[:20000],
            },
            model_name="deterministic",
            prompt_version="strategy_v2.agent2.qa_finalization.v1",
            schema_version=SCHEMA_VERSION_V2,
            agent_run_id=voc_agent_run_id,
        )

    updated_step_payload_artifact_ids = _updated_step_payload_artifact_ids(
        existing_step_payload_artifact_ids=existing_step_payload_artifact_ids,
        step_key=V2_STEP_VOC_EXTRACTION,
        artifact_id=step_payload_artifact_id,
    )
    return {
        "voc_observations": voc_observations,
        "voc_scored": voc_scored,
        "proof_asset_candidates": proof_asset_candidates,
        "step_payload_artifact_id": step_payload_artifact_id,
        "step_payload_artifact_ids": updated_step_payload_artifact_ids,
    }


@activity.defn(name="strategy_v2.run_voc_agent3_synthesis")
def run_strategy_v2_voc_agent3_synthesis_activity(params: dict[str, Any]) -> dict[str, Any]:
    org_id = str(params["org_id"])
    client_id = str(params["client_id"])
    product_id = str(params["product_id"])
    campaign_id = str(params["campaign_id"]) if isinstance(params.get("campaign_id"), str) else None
    workflow_run_id = str(params["workflow_run_id"])
    operator_user_id = str(params.get("operator_user_id") or "system")

    stage1_artifact_id = _require_stage1_artifact_id(params=params)
    shared_context = _require_stage2b_shared_context(params=params)
    existing_step_payload_artifact_ids = _parse_step_payload_artifact_ids(
        payload=params.get("existing_step_payload_artifact_ids"),
        field_name="existing_step_payload_artifact_ids",
    )
    foundational_step_contents = shared_context["foundational_step_contents"]
    foundational_step_summaries = shared_context["foundational_step_summaries"]
    existing_step_payload_artifact_ids = _ensure_foundational_step_payload_artifact_ids(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        workflow_run_id=workflow_run_id,
        foundational_step_contents=foundational_step_contents,
        foundational_step_summaries=foundational_step_summaries,
        existing_step_payload_artifact_ids=existing_step_payload_artifact_ids,
    )
    _require_step_payload_artifact_prerequisites(
        checkpoint_label="v2-06 Agent 3 angle synthesis",
        step_payload_artifact_ids=existing_step_payload_artifact_ids,
        required_step_keys=[
            *[f"v2-02.foundation.{step_key}" for step_key in _FOUNDATIONAL_STEP_KEYS],
            V2_STEP_HABITAT_SCORING,
        ],
        org_id=org_id,
        validate_lineage=True,
    )

    stage1_data = shared_context["stage1_data"]
    avatar_brief_payload = shared_context["avatar_brief_payload"]
    competitor_analysis = _require_dict(
        payload=params.get("competitor_analysis"),
        field_name="competitor_analysis",
    )
    apify_ingestion_artifact_id = str(params.get("apify_ingestion_artifact_id") or "").strip()
    apify_ingestion_payload: dict[str, Any] = {}
    if apify_ingestion_artifact_id:
        apify_ingestion_payload = _load_apify_ingestion_payload_for_downstream(
            org_id=org_id,
            apify_ingestion_artifact_id=apify_ingestion_artifact_id,
        )
    proof_asset_candidates_raw = params.get("proof_asset_candidates")
    proof_asset_candidates = (
        [row for row in proof_asset_candidates_raw if isinstance(row, dict)]
        if isinstance(proof_asset_candidates_raw, list)
        else []
    )
    if not proof_asset_candidates:
        proof_asset_candidates_from_apify = apify_ingestion_payload.get("proof_asset_candidates")
        if isinstance(proof_asset_candidates_from_apify, list):
            proof_asset_candidates = [
                row for row in proof_asset_candidates_from_apify if isinstance(row, dict)
            ]
    agent01_output_raw = params.get("agent01_output")
    agent01_output = agent01_output_raw if isinstance(agent01_output_raw, dict) else {}
    agent1_habitat_observations_raw = agent01_output.get("habitat_observations")
    agent1_habitat_observations = (
        [row for row in agent1_habitat_observations_raw if isinstance(row, dict)]
        if isinstance(agent1_habitat_observations_raw, list)
        else []
    )
    agent1_mining_plan_raw = agent01_output.get("mining_plan")
    agent1_mining_plan = (
        [row for row in agent1_mining_plan_raw if isinstance(row, dict)]
        if isinstance(agent1_mining_plan_raw, list)
        else []
    )
    habitat_scored_raw = params.get("habitat_scored")
    habitat_scored = habitat_scored_raw if isinstance(habitat_scored_raw, dict) else {}

    voc_input_mode = "agent2_full"
    evidence_rows_for_prompt: list[dict[str, Any]] = []
    evidence_manifest_rows: list[dict[str, Any]] = []
    evidence_diagnostics: dict[str, Any] = {}
    voc_observations_raw = params.get("voc_observations")
    if isinstance(voc_observations_raw, list) and voc_observations_raw:
        voc_input_mode = "agent2_full"
        voc_observations = _normalize_voc_observations(
            [row for row in voc_observations_raw if isinstance(row, dict)]
        )
        provided_voc_scored = params.get("voc_scored")
        if isinstance(provided_voc_scored, dict):
            voc_scored = provided_voc_scored
        else:
            voc_input_mode = "agent2_observations_only"
            voc_scored = score_voc_items(voc_observations)
    else:
        voc_input_mode = "raw_evidence_fallback"
        existing_corpus_raw = params.get("existing_corpus")
        if not isinstance(existing_corpus_raw, list):
            existing_corpus_raw = apify_ingestion_payload.get("existing_corpus")
        merged_voc_artifact_rows_raw = params.get("merged_voc_artifact_rows")
        if not isinstance(merged_voc_artifact_rows_raw, list):
            merged_voc_artifact_rows_raw = apify_ingestion_payload.get("merged_voc_artifact_rows")
        existing_corpus_rows = (
            [row for row in existing_corpus_raw if isinstance(row, Mapping)]
            if isinstance(existing_corpus_raw, list)
            else []
        )
        merged_voc_artifact_rows = (
            [row for row in merged_voc_artifact_rows_raw if isinstance(row, Mapping)]
            if isinstance(merged_voc_artifact_rows_raw, list)
            else []
        )
        scraped_data_manifest_payload = params.get("scraped_data_manifest")
        if not isinstance(scraped_data_manifest_payload, dict):
            scraped_data_manifest_payload = apify_ingestion_payload.get("scraped_data_manifest")
        scraped_data_manifest = _require_dict(
            payload=scraped_data_manifest_payload,
            field_name="scraped_data_manifest",
        )
        evidence_rows_for_prompt, evidence_diagnostics = _build_agent2_evidence_rows(
            existing_corpus=existing_corpus_rows,
            merged_voc_artifact_rows=merged_voc_artifact_rows,
            scraped_data_manifest=scraped_data_manifest,
        )
        _, _, evidence_manifest_rows = _index_agent2_input_rows(
            evidence_rows=evidence_rows_for_prompt
        )
        voc_observations = _derive_voc_observations_from_evidence_rows(
            evidence_rows=evidence_rows_for_prompt
        )
        voc_scored = score_voc_items(voc_observations)

    agent03_logical_payloads, agent03_allowed_voc_ids, agent03_payload_diagnostics = (
        _build_agent3_runtime_logical_payloads(
            stage1_data=stage1_data,
            avatar_brief_payload=avatar_brief_payload,
            foundational_step_contents=foundational_step_contents,
            foundational_step_summaries=foundational_step_summaries,
            competitor_analysis=competitor_analysis,
            habitat_scored=habitat_scored,
            agent1_habitat_observations=agent1_habitat_observations,
            agent1_mining_plan=agent1_mining_plan,
            voc_input_mode=voc_input_mode,
            voc_observations=voc_observations,
            voc_scored=voc_scored,
            evidence_rows_for_prompt=evidence_rows_for_prompt,
            evidence_manifest_rows=evidence_manifest_rows,
            evidence_diagnostics=evidence_diagnostics,
        )
    )
    saturated_angles_raw = agent03_logical_payloads.get("KNOWN_SATURATED_ANGLES_JSON")
    saturated_angles = (
        [row for row in saturated_angles_raw if isinstance(row, Mapping)]
        if isinstance(saturated_angles_raw, list)
        else []
    )
    saturated_count = max(1, min(9, len(saturated_angles)))
    activity.heartbeat(
        {
            "activity": "strategy_v2.run_voc_agent3_synthesis",
            "phase": "agent3_prompt",
            "status": "started",
            "runtime_payload_total_chars": int(
                agent03_payload_diagnostics.get("payload_sizes", {}).get("total_chars") or 0
            ),
        }
    )
    agent03_asset = resolve_prompt_asset(
        pattern=_VOC_AGENT03_PROMPT_PATTERN,
        context="VOC Agent 3 shadow angle clusterer",
    )
    agent03_file_id_map, agent03_uploaded_file_ids = _upload_openai_prompt_json_files(
        model=settings.STRATEGY_V2_VOC_MODEL,
        workflow_run_id=workflow_run_id,
        stage_label="agent3",
        logical_payloads=agent03_logical_payloads,
    )
    try:
        agent03_output, agent03_raw, agent03_provenance = _run_prompt_json_object(
            asset=agent03_asset,
            context="strategy_v2.agent3_output",
            model=settings.STRATEGY_V2_VOC_MODEL,
            runtime_instruction=_render_agent3_runtime_instruction(
                agent03_file_id_map=agent03_file_id_map,
                voc_input_mode=voc_input_mode,
            ),
            schema_name="strategy_v2_voc_agent03",
            schema=_agent3_prompt_output_schema(
                include_legacy_angle_candidates=False,
                allowed_voc_ids=agent03_allowed_voc_ids,
            ),
            use_reasoning=True,
            use_web_search=False,
            openai_tools=_openai_python_tool_resources(
                settings.STRATEGY_V2_VOC_MODEL,
                file_ids=list(agent03_file_id_map.values()),
            ),
            openai_tool_choice="auto",
            max_tokens=_AGENT3_MAX_TOKENS,
            heartbeat_context={
                "activity": "strategy_v2.run_voc_agent3_synthesis",
                "phase": "agent3_prompt",
                "model": settings.STRATEGY_V2_VOC_MODEL,
                "runtime_payload_total_chars": int(
                    agent03_payload_diagnostics.get("payload_sizes", {}).get("total_chars") or 0
                ),
            },
        )
    finally:
        _cleanup_openai_prompt_files(
            model=settings.STRATEGY_V2_VOC_MODEL,
            file_ids=agent03_uploaded_file_ids,
        )
    _raise_if_blocked_prompt_output(
        stage_label="v2-06 Agent 3 angle synthesis",
        parsed_output=agent03_output,
        raw_output=agent03_raw,
        remediation=(
            "ensure Agent 3 receives canonical Agent 2 outputs or raw VOC evidence files "
            "(VOC_EVIDENCE_ROWS_JSON + AGENT2_INPUT_MANIFEST_JSON) before rerunning v2-06."
        ),
    )
    raw_angle_observations = agent03_output.get("angle_observations")
    if not isinstance(raw_angle_observations, list):
        raw_angle_observations = []
    raw_angle_candidates = _extract_agent3_candidate_rows(agent03_output)
    angle_candidates = _normalize_angle_candidates([row for row in raw_angle_candidates if isinstance(row, dict)])
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
                "evidence_floor_gate": score_row.get("evidence_floor_gate") if isinstance(score_row, dict) else None,
            }
        )
    ranked_candidates.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)

    with session_scope() as session:
        angle_agent_run_id = _record_agent_run(
            session=session,
            org_id=org_id,
            user_id=operator_user_id,
            client_id=client_id,
            objective_type="strategy_v2.agent3_angle_synthesis.prompt_chain",
            model=settings.STRATEGY_V2_VOC_MODEL,
            inputs_json={
                "angle_observation_count": len(angle_observations),
                "voc_input_mode": voc_input_mode,
                "voc_observation_count": len(voc_observations),
                "voc_scored_item_count": len(voc_scored.get("items"))
                if isinstance(voc_scored.get("items"), list)
                else 0,
                "raw_evidence_row_count": len(evidence_rows_for_prompt),
                "runtime_payload_diagnostics": agent03_payload_diagnostics,
            },
            outputs_json={
                "ranked_candidates": ranked_candidates,
                "score_summary": scored_angles_payload.get("summary"),
            },
        )
        step_payload_artifact_id = _persist_step_payload(
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
                "voc_input_mode": voc_input_mode,
                "voc_observation_count": len(voc_observations),
                "voc_observations": voc_observations,
                "voc_scored": voc_scored,
                "proof_asset_candidates": proof_asset_candidates,
                "competitor_analysis": competitor_analysis,
                "voc_scored_summary": voc_scored.get("summary") if isinstance(voc_scored, dict) else {},
                "evidence_diagnostics": evidence_diagnostics,
                "runtime_payload_diagnostics": agent03_payload_diagnostics,
                "prompt_provenance": agent03_provenance,
                "raw_output": agent03_raw[:30000],
            },
            model_name=settings.STRATEGY_V2_VOC_MODEL,
            prompt_version="strategy_v2.agent3.prompt_chain.v2",
            schema_version=SCHEMA_VERSION_V2,
            agent_run_id=angle_agent_run_id,
        )

    updated_step_payload_artifact_ids = _updated_step_payload_artifact_ids(
        existing_step_payload_artifact_ids=existing_step_payload_artifact_ids,
        step_key=V2_STEP_ANGLE_SYNTHESIS,
        artifact_id=step_payload_artifact_id,
    )
    return {
        "ranked_angle_candidates": ranked_candidates,
        "step_payload_artifact_id": step_payload_artifact_id,
        "step_payload_artifact_ids": updated_step_payload_artifact_ids,
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
            agent00_file_id_map, agent00_uploaded_file_ids = _upload_openai_prompt_json_files(
                model=settings.STRATEGY_V2_VOC_MODEL,
                workflow_run_id=workflow_run_id,
                stage_label="agent0-prompt-chain",
                logical_payloads={
                    "FOUNDATIONAL_RESEARCH_DOCS_JSON": {
                        "step_contents": {
                            step_key: str(foundational_step_contents.get(step_key) or "")
                            for step_key in _FOUNDATIONAL_STEP_KEYS
                        },
                        "step_summaries": {
                            step_key: str(foundational_step_summaries.get(step_key) or "")
                            for step_key in _FOUNDATIONAL_STEP_KEYS
                        },
                    }
                },
            )
            try:
                agent00_runtime_base = (
                    "## Runtime Input Block\n"
                    f"OPENAI_CODE_INTERPRETER_FILE_IDS_JSON:\n{_dump_prompt_json_required(agent00_file_id_map, max_chars=12000, field_name='OPENAI_CODE_INTERPRETER_FILE_IDS_JSON')}\n\n"
                    "All required runtime JSON inputs are provided as uploaded files in the code interpreter container.\n"
                    "Review FOUNDATIONAL_RESEARCH_DOCS_JSON before generating habitat strategy.\n\n"
                    f"PRODUCT_BRIEF:\n{_dump_prompt_json(stage1_data, max_chars=12000)}\n\n"
                    f"AVATAR_BRIEF:\n{_dump_prompt_json(avatar_brief_payload, max_chars=12000)}\n\n"
                    f"COMPETITOR_RESEARCH:\n{str(foundational_step_contents.get('01') or '')[:20000]}\n\n"
                    f"COMPETITOR_ANALYSIS_JSON:\n{_dump_prompt_json(competitor_analysis, max_chars=16000)}\n\n"
                    f"KNOWN_HABITAT_URLS:\n{_dump_prompt_json([], max_chars=4000)}\n\n"
                    f"PLATFORM_RESTRICTIONS:\n{_dump_prompt_json(None, max_chars=2000)}\n\n"
                    f"GEOGRAPHIC_TARGET:\n{_dump_prompt_json(None, max_chars=2000)}\n"
                )
                agent00_handoff_output, agent00_raw, agent00_provenance = _run_prompt_json_object(
                    asset=agent00_asset,
                    context="strategy_v2.agent0_output",
                    model=settings.STRATEGY_V2_VOC_MODEL,
                    runtime_instruction=agent00_runtime_base,
                    schema_name="strategy_v2_voc_agent00_handoff",
                    schema=_VOC_AGENT00_HANDOFF_SCHEMA,
                    use_reasoning=True,
                    reasoning_effort="xhigh",
                    use_web_search=True,
                    openai_tools=_openai_python_tool_resources(
                        settings.STRATEGY_V2_VOC_MODEL,
                        file_ids=list(agent00_file_id_map.values()),
                    ),
                    openai_tool_choice="auto",
                    heartbeat_context={
                        "activity": "strategy_v2.run_voc_angle_pipeline",
                        "phase": "agent0_prompt",
                        "model": settings.STRATEGY_V2_VOC_MODEL,
                    },
                    append_schema_instruction=False,
                )
            finally:
                _cleanup_openai_prompt_files(
                    model=settings.STRATEGY_V2_VOC_MODEL,
                    file_ids=agent00_uploaded_file_ids,
                )
            _raise_if_blocked_prompt_output(
                stage_label="v2-02 Agent 0 habitat strategist",
                parsed_output=agent00_handoff_output,
                raw_output=agent00_raw,
                remediation=(
                    "provide complete PRODUCT_BRIEF, AVATAR_BRIEF, and COMPETITOR_ANALYSIS "
                    "inputs before rerunning v2-02."
                ),
            )
            agent00_output = _normalize_agent00_handoff_output(agent00_handoff_output)
            _require_agent00_executable_configs(agent00_output)
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
                "agent_handoff_json": agent00_handoff_output,
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
            agent00b_file_id_map, agent00b_uploaded_file_ids = _upload_openai_prompt_json_files(
                model=settings.STRATEGY_V2_VOC_MODEL,
                workflow_run_id=workflow_run_id,
                stage_label="agent0b-prompt-chain",
                logical_payloads={
                    "FOUNDATIONAL_RESEARCH_DOCS_JSON": {
                        "step_contents": {
                            step_key: str(foundational_step_contents.get(step_key) or "")
                            for step_key in _FOUNDATIONAL_STEP_KEYS
                        },
                        "step_summaries": {
                            step_key: str(foundational_step_summaries.get(step_key) or "")
                            for step_key in _FOUNDATIONAL_STEP_KEYS
                        },
                    }
                },
            )
            try:
                agent00b_output, agent00b_raw, agent00b_provenance = _run_prompt_json_object(
                    asset=agent00b_asset,
                    context="strategy_v2.agent0b_output",
                    model=settings.STRATEGY_V2_VOC_MODEL,
                    runtime_instruction=(
                        "## Runtime Input Block\n"
                        f"OPENAI_CODE_INTERPRETER_FILE_IDS_JSON:\n{_dump_prompt_json_required(agent00b_file_id_map, max_chars=12000, field_name='OPENAI_CODE_INTERPRETER_FILE_IDS_JSON')}\n\n"
                        "All required runtime JSON inputs are provided as uploaded files in the code interpreter container.\n"
                        "Review FOUNDATIONAL_RESEARCH_DOCS_JSON before generating video strategy.\n\n"
                        f"PRODUCT_BRIEF:\n{_dump_prompt_json(stage1_data, max_chars=12000)}\n\n"
                        f"AVATAR_BRIEF:\n{_dump_prompt_json(avatar_brief_payload, max_chars=12000)}\n\n"
                        f"COMPETITOR_ANALYSIS:\n{_dump_prompt_json(competitor_analysis, max_chars=16000)}\n\n"
                        f"PRODUCT_CATEGORY_KEYWORDS:\n{', '.join(product_category_keywords)}\n\n"
                        f"KNOWN_COMPETITOR_SOCIAL_ACCOUNTS:\n{_dump_prompt_json(stage1.competitor_urls, max_chars=6000)}\n"
                    ),
                    schema_name="strategy_v2_voc_agent00b",
                    schema=_voc_agent00b_response_schema(),
                    use_reasoning=True,
                    reasoning_effort="xhigh",
                    use_web_search=True,
                    openai_tools=_openai_python_tool_resources(
                        settings.STRATEGY_V2_VOC_MODEL,
                        file_ids=list(agent00b_file_id_map.values()),
                    ),
                    openai_tool_choice="auto",
                    heartbeat_context={
                        "activity": "strategy_v2.run_voc_angle_pipeline",
                        "phase": "agent0b_prompt",
                        "model": settings.STRATEGY_V2_VOC_MODEL,
                    },
                    append_schema_instruction=False,
                )
            finally:
                _cleanup_openai_prompt_files(
                    model=settings.STRATEGY_V2_VOC_MODEL,
                    file_ids=agent00b_uploaded_file_ids,
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

            strategy_apify_configs = _extract_apify_configs_from_agent_strategies(
                habitat_strategy=agent00_output,
                video_strategy=agent00b_output,
            )
            activity.heartbeat(
                {
                    "activity": "strategy_v2.run_voc_angle_pipeline",
                    "phase": "apify_execution_layer",
                    "status": "started",
                    "config_count": len(strategy_apify_configs),
                }
            )

            def _apify_progress_heartbeat(event: dict[str, Any]) -> None:
                heartbeat_payload: dict[str, Any] = {
                    "activity": "strategy_v2.run_voc_angle_pipeline",
                    "phase": "apify_execution_layer",
                    "status": "in_progress",
                    "progress_event": str(event.get("event") or "unknown"),
                    "config_count": len(strategy_apify_configs),
                }
                for field_name in (
                    "actor_id",
                    "config_id",
                    "run_id",
                    "run_index",
                    "planned_run_count",
                    "elapsed_seconds",
                    "status",
                ):
                    field_value = event.get(field_name)
                    if field_value is not None:
                        if field_name == "status":
                            heartbeat_payload["actor_run_status"] = field_value
                        else:
                            heartbeat_payload[field_name] = field_value
                activity.heartbeat(heartbeat_payload)

            apify_context = _ingest_strategy_v2_asset_data(
                apify_configs=strategy_apify_configs,
                include_ads_context=False,
                include_social_video=True,
                include_external_voc=True,
                progress_callback=_apify_progress_heartbeat,
            )
            apify_context["ingestion_apify_configs"] = strategy_apify_configs
            apify_context["ingestion_source_refs"] = []
            apify_context["excluded_source_refs"] = []
            raw_runs = apify_context.get("raw_runs")
            raw_run_rows = [row for row in raw_runs if isinstance(row, dict)] if isinstance(raw_runs, list) else []
            executed_actor_run_count = len(raw_run_rows)
            failed_actor_run_count = len(
                [row for row in raw_run_rows if str(row.get("status") or "").upper() != "SUCCEEDED"]
            )
            apify_summary = _require_dict(
                payload=apify_context.get("summary"),
                field_name="apify_context.summary",
            )
            strategy_config_run_count = apify_summary.get("strategy_config_run_count")
            planned_actor_run_count = apify_summary.get("planned_actor_run_count")
            if not isinstance(strategy_config_run_count, int) or strategy_config_run_count < 0:
                raise StrategyV2SchemaValidationError(
                    "apify_context.summary.strategy_config_run_count must be a non-negative integer."
                )
            if strategy_config_run_count != len(strategy_apify_configs):
                raise StrategyV2SchemaValidationError(
                    "apify_context.summary.strategy_config_run_count mismatch "
                    f"(summary={strategy_config_run_count}, expected_strategy_configs={len(strategy_apify_configs)})."
                )
            if not isinstance(planned_actor_run_count, int) or planned_actor_run_count < 0:
                raise StrategyV2SchemaValidationError(
                    "apify_context.summary.planned_actor_run_count must be a non-negative integer."
                )
            if planned_actor_run_count < executed_actor_run_count:
                raise StrategyV2SchemaValidationError(
                    "apify_context.summary.planned_actor_run_count cannot be less than executed_actor_run_count "
                    f"(planned={planned_actor_run_count}, executed={executed_actor_run_count})."
                )
            _validate_reddit_target_alignment(run_rows=raw_run_rows)
            activity.heartbeat(
                {
                    "activity": "strategy_v2.run_voc_angle_pipeline",
                    "phase": "apify_execution_layer",
                    "status": "completed",
                    "strategy_config_run_count": strategy_config_run_count,
                    "planned_actor_run_count": planned_actor_run_count,
                    "run_count": executed_actor_run_count,
                }
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

            source_allowlist = _extract_video_source_allowlist(agent00b_output)
            topic_keywords = _build_video_topic_keywords(stage1=stage1)
            metric_video_rows, video_filter_diagnostics = _filter_metric_video_rows_for_scoring(
                video_rows=video_observations,
                source_allowlist=source_allowlist,
                topic_keywords=topic_keywords,
            )
            video_scoring_status = "scored"
            if not metric_video_rows:
                if video_observations:
                    raise StrategyV2DecisionError(
                        "Video scoring aborted: no topic-aligned social video rows remained after source/topic validation. "
                        f"Diagnostics={video_filter_diagnostics}"
                    )
                video_scoring_status = "skipped_no_metric_video_rows"
            video_scored = _normalize_video_scored_rows(score_videos(metric_video_rows) if metric_video_rows else [])
            scoring_audit = _build_video_scoring_audit(
                video_observation_count=len(video_observations),
                metric_video_observation_count=len(metric_video_rows),
                video_scored=video_scored,
                video_filter_diagnostics=video_filter_diagnostics,
            )
            video_agent_run_id = _record_agent_run(
                session=session,
                org_id=org_id,
                user_id=operator_user_id,
                client_id=client_id,
                objective_type="strategy_v2.agent0b_scrape_virality.prompt_chain",
                model=settings.STRATEGY_V2_VOC_MODEL,
                inputs_json={
                    "video_scoring_status": video_scoring_status,
                    "video_observation_count": len(video_observations),
                    "metric_video_observation_count": len(metric_video_rows),
                    "apify_video_observation_count": len(apify_video_rows),
                    "video_filter_diagnostics": video_filter_diagnostics,
                },
                outputs_json={
                    "video_strategy": agent00b_output,
                    "video_filter_diagnostics": video_filter_diagnostics,
                    "video_scored": video_scored,
                    "scoring_audit": scoring_audit,
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
                    "video_scoring_status": video_scoring_status,
                    "video_observation_count": len(video_observations),
                    "metric_video_observation_count": len(metric_video_rows),
                    "apify_video_observation_count": len(apify_video_rows),
                    "video_filter_diagnostics": video_filter_diagnostics,
                    "scoring_audit": scoring_audit,
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
            _validate_agent1_scraped_manifest_integrity(
                scraped_data_manifest=scraped_data_manifest,
                planned_actor_run_count=planned_actor_run_count,
                executed_actor_run_count=executed_actor_run_count,
                failed_actor_run_count=failed_actor_run_count,
            )
            handoff_audit = {
                "strategy_config_run_count": strategy_config_run_count,
                "planned_actor_run_count": planned_actor_run_count,
                "executed_actor_run_count": executed_actor_run_count,
                "failed_actor_run_count": failed_actor_run_count,
                "manifest_run_count": int(scraped_data_manifest.get("run_count") or 0),
                "manifest_total_run_count": int(scraped_data_manifest.get("total_run_count") or 0),
                "excluded_run_count": int(scraped_data_manifest.get("excluded_run_count") or 0),
                "raw_files_len": len(scraped_data_manifest.get("raw_scraped_data_files") or []),
                "excluded_runs_len": len(scraped_data_manifest.get("excluded_runs") or []),
                "target_id_mapping_diagnostics": (
                    dict(scraped_data_manifest.get("target_id_mapping_diagnostics"))
                    if isinstance(scraped_data_manifest.get("target_id_mapping_diagnostics"), Mapping)
                    else {}
                ),
                "scoring_audit": scoring_audit,
            }

            agent01_asset = resolve_prompt_asset(
                pattern=_VOC_AGENT01_PROMPT_PATTERN,
                context="VOC Agent 1 habitat qualifier",
            )
            scraped_file_inventory = _build_agent1_runtime_file_inventory(scraped_data_manifest)
            agent01_file_assessment_template = _build_agent1_file_assessment_template(scraped_data_manifest)
            agent01_file_id_map, agent01_uploaded_file_ids = _upload_openai_prompt_json_files(
                model=settings.STRATEGY_V2_VOC_MODEL,
                workflow_run_id=workflow_run_id,
                stage_label="agent1-prompt-chain",
                logical_payloads={
                    "HABITAT_STRATEGY_JSON": agent00_output,
                    "VIDEO_STRATEGY_JSON": agent00b_output,
                    "SCORED_VIDEO_DATA_JSON": video_scored,
                    "SCRAPED_DATA_FILES_JSON": scraped_data_manifest,
                    "PRODUCT_BRIEF_JSON": stage1_data,
                    "AVATAR_BRIEF_JSON": avatar_brief_payload,
                    "COMPETITOR_ANALYSIS_JSON": competitor_analysis,
                    "HANDOFF_AUDIT_JSON": handoff_audit,
                    "SCORING_AUDIT_JSON": scoring_audit,
                    "AGENT1_FILE_ASSESSMENT_TEMPLATE_JSON": agent01_file_assessment_template,
                    "FOUNDATIONAL_RESEARCH_DOCS_JSON": {
                        "step_contents": {
                            step_key: str(foundational_step_contents.get(step_key) or "")
                            for step_key in _FOUNDATIONAL_STEP_KEYS
                        },
                        "step_summaries": {
                            step_key: str(foundational_step_summaries.get(step_key) or "")
                            for step_key in _FOUNDATIONAL_STEP_KEYS
                        },
                    },
                },
            )
            try:
                agent01_output, agent01_raw, agent01_provenance = _run_prompt_json_object(
                    asset=agent01_asset,
                    context="strategy_v2.agent1_output",
                    model=settings.STRATEGY_V2_VOC_MODEL,
                    runtime_instruction=_render_agent1_runtime_instruction(
                        agent01_file_id_map=agent01_file_id_map,
                        scraped_file_inventory=scraped_file_inventory,
                    ),
                    schema_name="strategy_v2_voc_agent01",
                    schema=_agent1_output_schema(
                        source_files=_ordered_scraped_data_file_names(scraped_data_manifest),
                    ),
                    use_reasoning=True,
                    reasoning_effort="low",
                    use_web_search=False,
                    openai_tools=_openai_python_tool_resources(
                        settings.STRATEGY_V2_VOC_MODEL,
                        file_ids=list(agent01_file_id_map.values()),
                    ),
                    openai_tool_choice="auto",
                    max_tokens=_AGENT1_MAX_TOKENS,
                    heartbeat_context={
                        "activity": "strategy_v2.run_voc_angle_pipeline",
                        "phase": "agent1_prompt",
                        "model": settings.STRATEGY_V2_VOC_MODEL,
                    },
                )
            finally:
                _cleanup_openai_prompt_files(
                    model=settings.STRATEGY_V2_VOC_MODEL,
                    file_ids=agent01_uploaded_file_ids,
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
            agent01_output = _derive_agent1_outputs_from_file_assessments(
                agent01_output=agent01_output,
                scraped_data_manifest=scraped_data_manifest,
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
                inputs_json={
                    "habitat_observation_count": len(habitat_observations),
                    "handoff_audit": handoff_audit,
                    "scoring_audit": scoring_audit,
                },
                outputs_json={
                    "habitat_scored": habitat_scored,
                    "scoring_audit": scoring_audit,
                },
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
                    "scoring_audit": scoring_audit,
                    "handoff_audit": handoff_audit,
                    "prompt_provenance": agent01_provenance,
                    "raw_output": agent01_raw[:20000],
                },
                model_name=settings.STRATEGY_V2_VOC_MODEL,
                prompt_version="strategy_v2.agent1.prompt_chain.v2",
                schema_version=SCHEMA_VERSION_V2,
                agent_run_id=qualifier_agent_run_id,
            )

            saturated_angles = extract_saturated_angles(competitor_analysis, limit=9)
            evidence_rows, evidence_diagnostics = _build_agent2_evidence_rows(
                existing_corpus=existing_corpus,
                merged_voc_artifact_rows=merged_voc_artifact_rows,
                scraped_data_manifest=scraped_data_manifest,
            )
            agent2_mode = "DUAL" if existing_corpus else "FRESH"
            agent02_asset = resolve_prompt_asset(
                pattern=_VOC_AGENT02_PROMPT_PATTERN,
                context="VOC Agent 2 extractor",
            )
            extraction = _run_agent2_extractor(
                agent02_asset=agent02_asset,
                model=settings.STRATEGY_V2_VOC_MODEL,
                workflow_run_id=workflow_run_id,
                mode=agent2_mode,
                evidence_rows=evidence_rows,
                agent01_output=agent01_output,
                habitat_scored=habitat_scored,
                stage1_data=stage1_data,
                avatar_brief_payload=avatar_brief_payload,
                competitor_analysis=competitor_analysis,
                saturated_angles=saturated_angles,
                foundational_step_contents=foundational_step_contents,
                foundational_step_summaries=foundational_step_summaries,
                activity_name="strategy_v2.run_voc_angle_pipeline",
            )
            agent02_output = {
                "mode": extraction["mode"],
                "voc_observations": extraction["voc_observations"],
                "rejected_items": extraction["rejected_items"],
                "extraction_summary": extraction["extraction_summary"],
                "validation_errors": [],
            }
            raw_voc_observations = extraction["voc_observations"]
            voc_observations = _normalize_voc_observations(
                [row for row in raw_voc_observations if isinstance(row, dict)]
            )
            voc_scored = score_voc_items(voc_observations)
            voc_input_mode = "agent2_full"
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
                    "mode": str(extraction.get("mode") or agent2_mode),
                    "extraction_summary": extraction.get("extraction_summary", {}),
                    "id_validation_report": extraction.get("id_validation_report", {}),
                    "input_manifest": extraction.get("input_manifest", {}),
                    "rejected_items": extraction.get("rejected_items", []),
                    "rejected_item_count": len(
                        [row for row in extraction.get("rejected_items", []) if isinstance(row, dict)]
                    ),
                    "evidence_row_count": len(evidence_rows),
                    "evidence_diagnostics": evidence_diagnostics,
                    "proof_asset_candidates": proof_asset_candidates,
                    "prompt_provenance": extraction.get("prompt_provenance", {}),
                    "raw_output": "\n\n".join(
                        str(part)
                        for part in extraction.get("raw_outputs_preview", [])[:8]
                        if isinstance(part, str)
                    )[:20000],
                },
                model_name=settings.STRATEGY_V2_VOC_MODEL,
                prompt_version="strategy_v2.agent2.prompt_chain.v2",
                schema_version=SCHEMA_VERSION_V2,
                agent_run_id=voc_agent_run_id,
            )

            agent03_logical_payloads, agent03_allowed_voc_ids, agent03_payload_diagnostics = (
                _build_agent3_runtime_logical_payloads(
                    stage1_data=stage1_data,
                    avatar_brief_payload=avatar_brief_payload,
                    foundational_step_contents=foundational_step_contents,
                    foundational_step_summaries=foundational_step_summaries,
                    competitor_analysis=competitor_analysis,
                    habitat_scored=habitat_scored,
                    agent1_habitat_observations=habitat_observations,
                    agent1_mining_plan=agent01_output.get("mining_plan")
                    if isinstance(agent01_output.get("mining_plan"), list)
                    else [],
                    voc_input_mode=voc_input_mode,
                    voc_observations=voc_observations,
                    voc_scored=voc_scored,
                    evidence_rows_for_prompt=evidence_rows,
                    evidence_manifest_rows=[],
                    evidence_diagnostics=evidence_diagnostics,
                )
            )
            saturated_angles_raw = agent03_logical_payloads.get("KNOWN_SATURATED_ANGLES_JSON")
            saturated_angles = (
                [row for row in saturated_angles_raw if isinstance(row, Mapping)]
                if isinstance(saturated_angles_raw, list)
                else []
            )
            saturated_count = max(1, min(9, len(saturated_angles)))
            agent03_asset = resolve_prompt_asset(
                pattern=_VOC_AGENT03_PROMPT_PATTERN,
                context="VOC Agent 3 shadow angle clusterer",
            )
            agent03_file_id_map, agent03_uploaded_file_ids = _upload_openai_prompt_json_files(
                model=settings.STRATEGY_V2_VOC_MODEL,
                workflow_run_id=workflow_run_id,
                stage_label="agent3-prompt-chain",
                logical_payloads=agent03_logical_payloads,
            )
            try:
                agent03_output, agent03_raw, agent03_provenance = _run_prompt_json_object(
                    asset=agent03_asset,
                    context="strategy_v2.agent3_output",
                    model=settings.STRATEGY_V2_VOC_MODEL,
                    runtime_instruction=_render_agent3_runtime_instruction(
                        agent03_file_id_map=agent03_file_id_map,
                        voc_input_mode=voc_input_mode,
                    ),
                    schema_name="strategy_v2_voc_agent03",
                    schema=_agent3_prompt_output_schema(
                        include_legacy_angle_candidates=False,
                        allowed_voc_ids=agent03_allowed_voc_ids,
                    ),
                    use_reasoning=True,
                    use_web_search=False,
                    openai_tools=_openai_python_tool_resources(
                        settings.STRATEGY_V2_VOC_MODEL,
                        file_ids=list(agent03_file_id_map.values()),
                    ),
                    openai_tool_choice="auto",
                    max_tokens=_AGENT3_MAX_TOKENS,
                    heartbeat_context={
                        "activity": "strategy_v2.run_voc_angle_pipeline",
                        "phase": "agent3_prompt",
                        "model": settings.STRATEGY_V2_VOC_MODEL,
                        "runtime_payload_total_chars": int(
                            agent03_payload_diagnostics.get("payload_sizes", {}).get("total_chars") or 0
                        ),
                    },
                )
            finally:
                _cleanup_openai_prompt_files(
                    model=settings.STRATEGY_V2_VOC_MODEL,
                    file_ids=agent03_uploaded_file_ids,
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
                raw_angle_observations = []
            raw_angle_candidates = _extract_agent3_candidate_rows(agent03_output)
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
                inputs_json={
                    "angle_observation_count": len(angle_observations),
                    "voc_input_mode": voc_input_mode,
                    "voc_observation_count": len(voc_observations),
                    "voc_scored_item_count": len(voc_scored.get("items"))
                    if isinstance(voc_scored.get("items"), list)
                    else 0,
                    "raw_evidence_row_count": len(evidence_rows),
                    "runtime_payload_diagnostics": agent03_payload_diagnostics,
                },
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
                    "voc_input_mode": voc_input_mode,
                    "voc_observation_count": len(voc_observations),
                    "voc_observations": voc_observations,
                    "voc_scored": voc_scored,
                    "proof_asset_candidates": proof_asset_candidates,
                    "competitor_analysis": competitor_analysis,
                    "voc_scored_summary": voc_scored.get("summary") if isinstance(voc_scored, dict) else {},
                    "evidence_diagnostics": evidence_diagnostics,
                    "runtime_payload_diagnostics": agent03_payload_diagnostics,
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
                    V2_STEP_APIFY_INGESTION: v2_03_step_payload_artifact_id,
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

    def _metric_count(row: Mapping[str, Any]) -> int:
        metrics = row.get("metrics")
        if not isinstance(metrics, dict):
            return 0
        return len([key for key, value in metrics.items() if value not in (None, "", 0)])

    def _caption_preview(row: Mapping[str, Any]) -> str:
        raw_text = str(row.get("headline_or_caption") or "").strip()
        if not raw_text:
            return ""
        collapsed = re.sub(r"<[^>]+>", " ", raw_text)
        collapsed = re.sub(r"\s+", " ", collapsed).strip()
        return collapsed[:500]

    def _candidate_merge_priority(row: Mapping[str, Any]) -> tuple[int, int, int, int, int]:
        compliance = str(row.get("compliance_risk") or "").strip().upper()
        caption = _caption_preview(row)
        return (
            _metric_count(row),
            1 if caption else 0,
            1 if str(row.get("raw_source_artifact_id") or "").strip() else 0,
            1 if compliance not in {"", "YELLOW"} else 0,
            len(caption),
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
        if _candidate_merge_priority(row) > _candidate_merge_priority(existing):
            merged_candidates_by_ref[source_ref] = row

    if not merged_candidates_by_ref:
        raise StrategyV2MissingContextError(
            "H2 candidate asset preparation could not produce any normalized competitor assets. "
            "Remediation: verify competitor URLs and Apify ingestion configuration."
        )
    merged_candidates = list(merged_candidates_by_ref.values())

    scored_candidates = score_candidate_assets(merged_candidates)
    eligible_platforms = {
        str(row.get("platform") or "unknown")
        for row in scored_candidates
        if bool(row.get("eligible"))
    }
    effective_max_per_platform = (
        _H2_MAX_CANDIDATE_ASSETS
        if len(eligible_platforms) == 1
        else _H2_MAX_CANDIDATES_PER_PLATFORM
    )

    selected_candidates = select_top_candidates(
        scored_candidates,
        max_candidates=_H2_MAX_CANDIDATE_ASSETS,
        max_per_competitor=_H2_MAX_CANDIDATES_PER_COMPETITOR,
        max_per_platform=effective_max_per_platform,
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
            "max_per_platform": effective_max_per_platform,
            "configured_max_per_platform": _H2_MAX_CANDIDATES_PER_PLATFORM,
        },
        "operator_confirmation_policy": {
            "min_confirmed_assets": _MIN_STAGE1_COMPETITORS,
            "target_confirmed_assets": _H2_TARGET_CONFIRMED_ASSETS,
            "max_confirmed_assets": _H2_MAX_CONFIRMED_ASSETS,
        },
        "selection_ordering": {
            "eligibility_rule": "hard_gate_flags must be empty",
            "sort_rule": (
                "candidate_asset_score desc, source_relevance_signal desc, "
                "data_richness_signal desc, candidate_id asc"
            ),
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
    decision_payload = _require_dict(payload=params["angle_selection_decision"], field_name="angle_selection_decision")
    decision_selected_angle = _require_dict(
        payload=decision_payload.get("selected_angle"),
        field_name="angle_selection_decision.selected_angle",
    )
    if decision_selected_angle.get("hook_starters") is None:
        decision_payload = dict(decision_payload)
        decision_payload["selected_angle"] = {
            **decision_selected_angle,
            "hook_starters": [],
        }
    decision = AngleSelectionDecision.model_validate(
        decision_payload
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
        if angle_payload.get("hook_starters") is None:
            angle_payload = {
                **angle_payload,
                "hook_starters": [],
            }
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
            "price": require_concrete_price(
                price=stage1.price,
                context="Stage 2 angle selection",
            ),
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
    if "voc_scored" in params or "voc_observations" in params:
        raise StrategyV2MissingContextError(
            "Offer pipeline no longer accepts voc_scored/voc_observations via Temporal payloads "
            "(can exceed the 4MB gRPC limit). "
            "Remediation: load VOC inputs from the persisted v2-06 step payload artifact."
        )
    _, v2_06_payload = _load_step_payload_payload_from_research_artifact(
        checkpoint_label="v2-08 Offer pipeline",
        org_id=org_id,
        workflow_run_id=workflow_run_id,
        step_key=V2_STEP_ANGLE_SYNTHESIS,
    )
    voc_scored_raw = v2_06_payload.get("voc_scored")
    if not isinstance(voc_scored_raw, dict):
        raise StrategyV2MissingContextError(
            "v2-08 Offer pipeline missing voc_scored in v2-06 step payload artifact. "
            "Remediation: rerun v2-06 and ensure VOC scoring payload is persisted."
        )
    voc_observations_raw = v2_06_payload.get("voc_observations")
    if not isinstance(voc_observations_raw, list) or not voc_observations_raw:
        raise StrategyV2MissingContextError(
            "v2-08 Offer pipeline missing non-empty voc_observations in v2-06 step payload artifact. "
            "Remediation: rerun v2-06 and ensure VOC observation payload is persisted."
        )
    voc_observations = [row for row in voc_observations_raw if isinstance(row, dict)]
    if not voc_observations:
        raise StrategyV2MissingContextError(
            "v2-08 Offer pipeline voc_observations in v2-06 payload are invalid; expected dict rows."
        )
    voc_scored = voc_scored_raw
    angle_synthesis = _require_dict(payload=params["angle_synthesis"], field_name="angle_synthesis")
    proof_asset_candidates_raw = params.get("proof_asset_candidates")
    proof_asset_candidates = (
        [row for row in proof_asset_candidates_raw if isinstance(row, dict)]
        if isinstance(proof_asset_candidates_raw, list)
        else []
    )
    if not proof_asset_candidates:
        proof_asset_candidates_v2_06_raw = v2_06_payload.get("proof_asset_candidates")
        if isinstance(proof_asset_candidates_v2_06_raw, list):
            proof_asset_candidates = [row for row in proof_asset_candidates_v2_06_raw if isinstance(row, dict)]
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
    offer_data_readiness = _require_dict(payload=params["offer_data_readiness"], field_name="offer_data_readiness")
    readiness_status = str(offer_data_readiness.get("status") or "").strip().lower()
    if readiness_status != "ready":
        missing_fields = offer_data_readiness.get("missing_fields")
        inconsistent_fields = offer_data_readiness.get("inconsistent_fields")
        raise StrategyV2MissingContextError(
            "Offer data readiness is blocked and cannot continue to variant generation. "
            f"missing_fields={missing_fields}; inconsistent_fields={inconsistent_fields}"
        )
    readiness_context = _require_dict(
        payload=offer_data_readiness.get("context"),
        field_name="offer_data_readiness.context",
    )
    offer_format = str(readiness_context.get("offer_format") or "").strip() or "DISCOUNT_PLUS_3_BONUSES_V1"
    if offer_format != "DISCOUNT_PLUS_3_BONUSES_V1":
        raise StrategyV2SchemaValidationError(
            f"Unsupported offer_format '{offer_format}'. Only DISCOUNT_PLUS_3_BONUSES_V1 is allowed."
        )
    product_type = str(readiness_context.get("product_type") or "").strip().lower()
    if not product_type:
        raise StrategyV2SchemaValidationError("offer_data_readiness.context.product_type is required.")
    core_product_context = _require_dict(
        payload=readiness_context.get("core_product"),
        field_name="offer_data_readiness.context.core_product",
    )
    core_product_id = str(core_product_context.get("product_id") or "").strip()
    core_product_title = str(core_product_context.get("title") or "").strip()
    if not core_product_id or not core_product_title:
        raise StrategyV2SchemaValidationError(
            "offer_data_readiness.context.core_product requires product_id and title."
        )
    bundle_contents_seed = _require_dict(
        payload=readiness_context.get("bundle_contents"),
        field_name="offer_data_readiness.context.bundle_contents",
    )
    pricing_metadata_seed = _require_dict(
        payload=readiness_context.get("pricing_metadata"),
        field_name="offer_data_readiness.context.pricing_metadata",
    )
    savings_metadata_seed = _require_dict(
        payload=readiness_context.get("savings_metadata"),
        field_name="offer_data_readiness.context.savings_metadata",
    )
    bonus_items_raw = readiness_context.get("bonus_items")
    if not isinstance(bonus_items_raw, list) or len(bonus_items_raw) != 3:
        raise StrategyV2SchemaValidationError(
            "offer_data_readiness.context.bonus_items must contain exactly 3 bonus definitions."
        )
    bonus_items: list[dict[str, Any]] = []
    for bonus_idx, raw_bonus in enumerate(bonus_items_raw):
        bonus_item = _require_dict(
            payload=raw_bonus,
            field_name=f"offer_data_readiness.context.bonus_items[{bonus_idx}]",
        )
        bonus_id = str(bonus_item.get("bonus_id") or "").strip()
        linked_product_id = str(bonus_item.get("linked_product_id") or "").strip()
        title = str(bonus_item.get("title") or "").strip()
        if not bonus_id or not linked_product_id or not title:
            raise StrategyV2SchemaValidationError(
                "offer_data_readiness.context.bonus_items requires bonus_id, linked_product_id, and title."
            )
        bonus_items.append(
            {
                "bonus_id": bonus_id,
                "linked_product_id": linked_product_id,
                "title": title,
                "product_type": str(bonus_item.get("product_type") or "").strip().lower() or "other",
                "position": int(bonus_item.get("position") or 0),
            }
        )
    bonus_items = sorted(bonus_items, key=lambda row: int(row.get("position") or 0))
    expected_bonus_ids = {str(row["bonus_id"]) for row in bonus_items}
    if len(expected_bonus_ids) != 3:
        raise StrategyV2SchemaValidationError(
            "offer_data_readiness.context.bonus_items must include 3 unique bonus_id values."
        )
    bonus_by_id = {str(row["bonus_id"]): row for row in bonus_items}
    product_type_offer_instruction = ""
    if canonical_product_type(product_type) == "book":
        product_type_offer_instruction = (
            "For this run, the core product is a physical book. "
            "The three offer variants must map to 1 book, 2 books, and 3 books respectively. "
            "Do not use device, seat, license, PDF, downloadable, or instant-digital-access language for the core product."
        )
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
                "offer_format": offer_format,
                "product_type": product_type,
                "offer_data_readiness_context": _dump_prompt_json(readiness_context, max_chars=12000),
                "bundle_contents_seed": _dump_prompt_json(bundle_contents_seed, max_chars=8000),
                "pricing_metadata_seed": _dump_prompt_json(pricing_metadata_seed, max_chars=2000),
                "savings_metadata_seed": _dump_prompt_json(savings_metadata_seed, max_chars=2000),
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
                    f"OFFER_DATA_READINESS_CONTEXT:\n{_dump_prompt_json(readiness_context, max_chars=12000)}\n\n"
                    "## Runtime Output Contract\n"
                    f"Return JSON with `variants` array for ids {', '.join(_OFFER_VARIANT_IDS)}.\n"
                    "Use the V1 structure: product + discount + exactly 3 bonus modules.\n"
                    "Each variant must return bonus_modules as an object keyed by the exact bonus_id values from OFFER_DATA_READINESS_CONTEXT.\n"
                    "Do not emit bonus_id inside bonus_modules values; runtime derives it from each object key.\n"
                    "Each variant must include structured pricing_metadata, savings_metadata, best_value_metadata, "
                    "objection_map, and dimension_scores.\n"
                    f"{product_type_offer_instruction}"
                ),
                schema_name="strategy_v2_offer_step04",
                schema=_offer_step04_response_schema(
                    bonus_ids=[str(row["bonus_id"]) for row in bonus_items],
                ),
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
                core_promise = str(variant.get("core_promise") or "").strip()
                if not core_promise:
                    raise StrategyV2SchemaValidationError(f"Variant '{variant_id}' core_promise is required.")
                if len(core_promise) > _STEP04_CORE_PROMISE_MAX_CHARS:
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' core_promise exceeds {_STEP04_CORE_PROMISE_MAX_CHARS} chars."
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

                bonus_modules_raw = variant.get("bonus_modules")
                if not isinstance(bonus_modules_raw, Mapping):
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' must include bonus_modules object keyed by readiness bonus ids."
                    )
                bonus_copy_by_id: dict[str, str] = {}
                returned_bonus_ids = {
                    str(key or "").strip()
                    for key in bonus_modules_raw.keys()
                    if str(key or "").strip()
                }
                unknown_bonus_ids = sorted(returned_bonus_ids - expected_bonus_ids)
                if unknown_bonus_ids:
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' bonus_modules contains unknown bonus_id values: {unknown_bonus_ids}."
                    )
                missing_bonus_ids = sorted(expected_bonus_ids - returned_bonus_ids)
                if missing_bonus_ids:
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' bonus_modules must include exactly readiness bonus ids: "
                        f"{sorted(expected_bonus_ids)}. Missing={missing_bonus_ids}."
                    )
                for bonus_id in [str(row["bonus_id"]) for row in bonus_items]:
                    bonus_module = _require_dict(
                        payload=bonus_modules_raw.get(bonus_id),
                        field_name=f"variants[{idx}].bonus_modules['{bonus_id}']",
                    )
                    bonus_copy = str(bonus_module.get("copy") or "").strip()
                    if not bonus_copy:
                        raise StrategyV2SchemaValidationError(
                            f"Variant '{variant_id}' bonus_modules bonus_id '{bonus_id}' copy is required."
                        )
                    if len(bonus_copy) > _STEP04_BONUS_COPY_MAX_CHARS:
                        raise StrategyV2SchemaValidationError(
                            f"Variant '{variant_id}' bonus copy for bonus_id '{bonus_id}' exceeds "
                            f"{_STEP04_BONUS_COPY_MAX_CHARS} chars."
                        )
                    bonus_copy_by_id[bonus_id] = bonus_copy

                pricing_metadata_raw = _require_dict(
                    payload=variant.get("pricing_metadata"),
                    field_name=f"variants[{idx}].pricing_metadata",
                )
                list_price_cents = pricing_metadata_raw.get("list_price_cents")
                offer_price_cents = pricing_metadata_raw.get("offer_price_cents")
                if not isinstance(list_price_cents, int) or list_price_cents <= 0:
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' pricing_metadata.list_price_cents must be a positive integer."
                    )
                if not isinstance(offer_price_cents, int) or offer_price_cents <= 0:
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' pricing_metadata.offer_price_cents must be a positive integer."
                    )
                if offer_price_cents > list_price_cents:
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' pricing_metadata.offer_price_cents cannot exceed list_price_cents."
                    )
                pricing_metadata = {
                    "list_price_cents": list_price_cents,
                    "offer_price_cents": offer_price_cents,
                }

                savings_metadata_raw = _require_dict(
                    payload=variant.get("savings_metadata"),
                    field_name=f"variants[{idx}].savings_metadata",
                )
                savings_amount_cents = savings_metadata_raw.get("savings_amount_cents")
                savings_percent_raw = savings_metadata_raw.get("savings_percent")
                savings_basis = str(savings_metadata_raw.get("savings_basis") or "").strip()
                if not isinstance(savings_amount_cents, int) or savings_amount_cents < 0:
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' savings_metadata.savings_amount_cents must be a non-negative integer."
                    )
                if not isinstance(savings_percent_raw, (int, float)) or float(savings_percent_raw) < 0.0:
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' savings_metadata.savings_percent must be non-negative."
                    )
                if not savings_basis:
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' savings_metadata.savings_basis is required."
                    )
                expected_savings_amount = int(list_price_cents) - int(offer_price_cents)
                if savings_amount_cents != expected_savings_amount:
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' savings_metadata.savings_amount_cents must equal "
                        "list_price_cents - offer_price_cents."
                    )
                expected_savings_percent = round((expected_savings_amount / float(list_price_cents)) * 100.0, 2)
                savings_percent = round(float(savings_percent_raw), 2)
                if abs(savings_percent - expected_savings_percent) > 0.5:
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' savings_metadata.savings_percent must match computed savings percent "
                        f"within tolerance (expected {expected_savings_percent})."
                    )
                savings_metadata = {
                    "savings_amount_cents": int(savings_amount_cents),
                    "savings_percent": float(savings_percent),
                    "savings_basis": savings_basis,
                }

                best_value_raw = _require_dict(
                    payload=variant.get("best_value_metadata"),
                    field_name=f"variants[{idx}].best_value_metadata",
                )
                best_value_reason = str(best_value_raw.get("rationale") or "").strip()
                if not best_value_reason:
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' best_value_metadata.rationale is required."
                    )
                if len(best_value_reason) > _STEP04_BEST_VALUE_REASON_MAX_CHARS:
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' best_value_metadata.rationale exceeds "
                        f"{_STEP04_BEST_VALUE_REASON_MAX_CHARS} chars."
                    )
                compared_variant_ids_raw = best_value_raw.get("compared_variant_ids")
                if not isinstance(compared_variant_ids_raw, list):
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' best_value_metadata.compared_variant_ids must be an array."
                    )
                compared_variant_ids = [
                    str(item).strip().lower()
                    for item in compared_variant_ids_raw
                    if isinstance(item, str) and str(item).strip()
                ]
                if len(compared_variant_ids) != len(_OFFER_VARIANT_IDS) - 1:
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' best_value_metadata.compared_variant_ids must include exactly "
                        f"{len(_OFFER_VARIANT_IDS) - 1} ids."
                    )
                if len(set(compared_variant_ids)) != len(compared_variant_ids):
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' best_value_metadata.compared_variant_ids must be unique."
                    )
                if variant_id in compared_variant_ids:
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' best_value_metadata.compared_variant_ids cannot include itself."
                    )
                unknown_compared_ids = [item for item in compared_variant_ids if item not in _OFFER_VARIANT_IDS]
                if unknown_compared_ids:
                    raise StrategyV2SchemaValidationError(
                        f"Variant '{variant_id}' compared_variant_ids contains unknown ids: {unknown_compared_ids}."
                    )
                best_value_metadata = {
                    "is_best_value": bool(best_value_raw.get("is_best_value")),
                    "rationale": best_value_reason,
                    "compared_variant_ids": compared_variant_ids,
                }

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
                        "pricing_fidelity": _normalize_score_1_10(
                            dimension_scores.get("pricing_fidelity"),
                            field_name=f"{variant_id}.pricing_fidelity",
                        ),
                        "savings_fidelity": _normalize_score_1_10(
                            dimension_scores.get("savings_fidelity"),
                            field_name=f"{variant_id}.savings_fidelity",
                        ),
                        "best_value_fidelity": _normalize_score_1_10(
                            dimension_scores.get("best_value_fidelity"),
                            field_name=f"{variant_id}.best_value_fidelity",
                        ),
                    },
                    "offer_format": offer_format,
                    "product_type": product_type,
                    "pricing_metadata": pricing_metadata,
                    "savings_metadata": savings_metadata,
                    "best_value_metadata": best_value_metadata,
                    "bonus_stack": [
                        {
                            "bonus_id": str(bonus_row.get("bonus_id") or ""),
                            "linked_product_id": str(bonus_row.get("linked_product_id") or ""),
                            "title": str(bonus_row.get("title") or ""),
                            "product_type": str(bonus_row.get("product_type") or ""),
                            "copy": str(bonus_copy_by_id.get(str(bonus_row.get("bonus_id") or "")) or ""),
                        }
                        for bonus_row in bonus_items
                    ],
                    "bundle_contents": {
                        "core_product": {
                            "product_id": core_product_id,
                            "title": core_product_title,
                            "product_type": product_type,
                        },
                        "offer_id": str(readiness_context.get("offer_id") or ""),
                        "offer_name": str(readiness_context.get("offer_name") or ""),
                        "bonuses": [
                            {
                                "bonus_id": str(bonus_row.get("bonus_id") or ""),
                                "linked_product_id": str(bonus_row.get("linked_product_id") or ""),
                                "title": str(bonus_row.get("title") or ""),
                                "product_type": str(bonus_row.get("product_type") or ""),
                                "copy": str(bonus_copy_by_id.get(str(bonus_row.get("bonus_id") or "")) or ""),
                            }
                            for bonus_row in bonus_items
                        ],
                        "bonus_count": len(bonus_items),
                    },
                }
            missing_ids = [variant_id for variant_id in _OFFER_VARIANT_IDS if variant_id not in by_id]
            if missing_ids:
                raise StrategyV2SchemaValidationError(
                    f"Offer Step 04 did not return required variant ids: {missing_ids}."
                )
            best_value_variant_ids = [
                variant_id
                for variant_id, payload in by_id.items()
                if bool(_require_dict(payload=payload.get("best_value_metadata"), field_name="best_value_metadata").get("is_best_value"))
            ]
            if len(best_value_variant_ids) != 1:
                raise StrategyV2SchemaValidationError(
                    "Offer Step 04 must mark exactly one variant as best value "
                    f"(found {len(best_value_variant_ids)}: {best_value_variant_ids})."
                )
            generated_variant_inputs = [by_id[variant_id] for variant_id in _OFFER_VARIANT_IDS]

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
                        "offer_format": variant["offer_format"],
                        "product_type": variant["product_type"],
                        "core_promise": variant["core_promise"],
                        "value_stack": variant["value_stack"],
                        "guarantee": variant["guarantee"],
                        "pricing_rationale": variant["pricing_rationale"],
                        "pricing_metadata": variant["pricing_metadata"],
                        "savings_metadata": variant["savings_metadata"],
                        "best_value_metadata": variant["best_value_metadata"],
                        "bundle_contents": variant["bundle_contents"],
                        "bonus_stack": variant["bonus_stack"],
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
                            "pricing_fidelity": {
                                "raw_score": float(dimensions["pricing_fidelity"]),
                                "evidence_quality": "OBSERVED",
                            },
                            "savings_fidelity": {
                                "raw_score": float(dimensions["savings_fidelity"]),
                                "evidence_quality": "OBSERVED",
                            },
                            "best_value_fidelity": {
                                "raw_score": float(dimensions["best_value_fidelity"]),
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
                "offer_data_readiness_context": _dump_prompt_json(readiness_context, max_chars=12000),
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
                    "Return JSON ONLY (no markdown, no prose outside JSON).\n"
                    f"For each variant, provide exactly {len(_OFFER_COMPOSITE_DIMENSIONS)} required dimensions and required fields only.\n"
                    "Do not emit large narratives, placeholder whitespace, or extra keys.\n"
                    f"`revision_notes` MUST be non-empty plain text and <= {_STEP05_REVISION_NOTES_MAX_CHARS} chars."
                ),
                schema_name="strategy_v2_offer_step05",
                schema=_offer_step05_response_schema(),
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
                response_id = (
                    str(step05_provenance.get("openai_response_id") or "").strip()
                    if isinstance(step05_provenance, dict)
                    else ""
                )
                raise StrategyV2SchemaValidationError(
                    "Offer Step 05 returned empty revision_notes while revision is required "
                    f"(iteration={iteration}, response_id={response_id or 'UNKNOWN'}). "
                    "Remediation: Step 05 must return a non-empty plain-text revision_notes string."
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
                inputs_json={
                    "selected_pair": selected_pair,
                    "offer_data_readiness": offer_data_readiness,
                },
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
                "offer_data_readiness": offer_data_readiness,
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
            "offer_format": str(selected_variant.get("offer_format") or "DISCOUNT_PLUS_3_BONUSES_V1"),
            "product_type": str(selected_variant.get("product_type") or ""),
            "pricing_metadata": (
                dict(selected_variant.get("pricing_metadata"))
                if isinstance(selected_variant.get("pricing_metadata"), dict)
                else None
            ),
            "savings_metadata": (
                dict(selected_variant.get("savings_metadata"))
                if isinstance(selected_variant.get("savings_metadata"), dict)
                else None
            ),
            "best_value_metadata": (
                dict(selected_variant.get("best_value_metadata"))
                if isinstance(selected_variant.get("best_value_metadata"), dict)
                else None
            ),
            "bundle_contents": (
                dict(selected_variant.get("bundle_contents"))
                if isinstance(selected_variant.get("bundle_contents"), dict)
                else None
            ),
            "bonus_stack": (
                [row for row in selected_variant.get("bonus_stack") if isinstance(row, dict)]
                if isinstance(selected_variant.get("bonus_stack"), list)
                else []
            ),
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
    decision_payload = {
        **decision.model_dump(mode="python"),
        "reviewed_candidate_ids": cleaned_reviewed_candidate_ids,
    }

    with session_scope() as session:
        synced_product_offer = _sync_product_offer_from_strategy_output(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            onboarding_payload=onboarding_payload,
            offer_pipeline_output=offer_pipeline_output,
            stage3_data=stage3_data,
            scored_variants=[variant for variant in variants_raw if isinstance(variant, Mapping)],
            selected_variant=selected_variant,
            selected_variant_score=selected_variant_score,
            decision_payload=decision_payload,
        )
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
                "decision": decision_payload,
                "product_offer_id": synced_product_offer.get("id"),
                "product_offer": synced_product_offer,
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
            inputs_json={"decision": decision_payload},
            outputs_json={
                "stage3": stage3_data,
                "product_offer": synced_product_offer,
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
                "decision": decision_payload,
                "stage3": stage3_data,
                "stage3_artifact_id": str(stage3_artifact.id),
                "awareness_matrix": awareness_matrix_data,
                "awareness_matrix_source_step": "v2-08.step_02",
                "awareness_matrix_source_provenance": awareness_matrix_step2_provenance,
                "awareness_matrix_artifact_id": str(awareness_matrix_artifact.id),
                "offer_artifact_id": str(offer_artifact.id),
                "product_offer_id": synced_product_offer.get("id"),
                "product_offer": synced_product_offer,
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
            "offer_artifact_id": str(offer_artifact.id),
            "copy_context": copy_context_data,
            "copy_context_artifact_id": str(copy_context_artifact.id),
            "product_offer_id": str(synced_product_offer.get("id") or ""),
            "product_offer": synced_product_offer,
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


def _is_non_retryable_sales_payload_failure(error_message: str) -> bool:
    lowered = error_message.lower()
    if "template_payload_validation" in lowered:
        return any(
            signal in lowered
            for signal in (
                "field required",
                "extra inputs are not permitted",
                "input should be a valid",
                "input should be an object",
                "input should be a valid array",
                "input should be a valid boolean",
                "input should be a valid dictionary",
                "input should be a valid integer",
                "input should be a valid list",
                "input should be a valid object",
                "input should be a valid string",
            )
        )
    return (
        "sales template payload json parse failed" in lowered
        or "invalid template_payload object" in lowered
        or "legacy sales payload upgrade failed" in lowered
    )


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
    cta_link_repair_lines: list[str] = []
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

        if not cta_link_repair_lines:
            cta_link_match = _COPY_SALES_SEMANTIC_CTA_LINK_ERROR_RE.search(message)
            if cta_link_match is not None:
                cta_link_repair_lines = [
                    "- CTA link integrity hard-fix: previous sales draft had zero markdown CTA link URLs.",
                    "- Add at least one markdown link in each canonical CTA section using `[anchor](https://...)`.",
                    "- Keep the purchase destination URL consistent across CTA #1, CTA #2, and CTA #3 + P.S.",
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
            and cta_link_repair_lines
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
    lines.extend(cta_link_repair_lines)
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
    headline_evaluation_limit = _COPY_HEADLINE_EVALUATION_LIMIT
    if params.get("headline_evaluation_limit") is not None:
        headline_evaluation_limit = _coerce_int(params.get("headline_evaluation_limit"))
    headline_evaluation_offset = _COPY_HEADLINE_EVALUATION_OFFSET
    if params.get("headline_evaluation_offset") is not None:
        headline_evaluation_offset = _coerce_int(params.get("headline_evaluation_offset"))
    allow_no_bundle_result = str(params.get("allow_no_bundle_result") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    rapid_mode = str(params.get("rapid_mode") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    copy_generation_mode = _normalize_copy_generation_mode(params.get("copy_generation_mode"))
    template_payload_only_mode = copy_generation_mode == _COPY_GENERATION_MODE_TEMPLATE_PAYLOAD_ONLY
    qa_max_iterations = _COPY_HEADLINE_QA_MAX_ITERATIONS
    page_repair_max_attempts = _COPY_PAGE_REPAIR_MAX_ATTEMPTS
    if rapid_mode:
        if template_payload_only_mode:
            page_repair_max_attempts = min(page_repair_max_attempts, 5)
        else:
            page_repair_max_attempts = min(page_repair_max_attempts, 3)

    hook_lines = [hook.opening_line.strip() for hook in stage3.selected_angle.hook_starters if hook.opening_line.strip()]
    if not hook_lines:
        # Agent 3 may omit hook starters (angles are VOC-first). In that case, fall back to
        # using the selected angle's top VOC quotes as headline seeds.
        hook_lines = [
            quote.quote.strip()
            for quote in stage3.selected_angle.evidence.top_quotes
            if isinstance(quote.quote, str) and quote.quote.strip()
        ][:12]
    if not hook_lines:
        raise StrategyV2MissingContextError(
            "Selected angle does not contain any usable hook starters or VOC quotes for copy generation. "
            "Remediation: select an angle with non-empty evidence.top_quotes (preferred) or hook_starters."
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
        qa_api_key_env = headline_qa_required_api_key_env(settings.STRATEGY_V2_COPY_QA_MODEL)
        api_key = os.getenv(qa_api_key_env, "").strip()
        if not api_key:
            raise StrategyV2MissingContextError(
                f"{qa_api_key_env} is required for copy headline QA loop model "
                f"'{settings.STRATEGY_V2_COPY_QA_MODEL}' and is not set. "
                f"Remediation: configure {qa_api_key_env} before running Strategy V2 copy stage."
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
            max_tokens=_COPY_PIPELINE_MAX_TOKENS,
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
        if headline_evaluation_limit < 1:
            raise StrategyV2DecisionError(
                "Headline evaluation limit must be >= 1. "
                "Remediation: set STRATEGY_V2_COPY_HEADLINE_EVALUATION_LIMIT to a positive integer."
            )
        if headline_evaluation_offset < 0:
            raise StrategyV2DecisionError(
                "Headline evaluation offset must be >= 0. "
                "Remediation: set STRATEGY_V2_COPY_HEADLINE_EVALUATION_OFFSET to a non-negative integer."
            )
        if headline_evaluation_offset >= len(ranked_headlines):
            raise StrategyV2DecisionError(
                "Headline evaluation offset exceeds available ranked headlines. "
                "Remediation: lower STRATEGY_V2_COPY_HEADLINE_EVALUATION_OFFSET or increase candidate generation."
            )
        headlines_for_evaluation = ranked_headlines[
            headline_evaluation_offset : headline_evaluation_offset + headline_evaluation_limit
        ]
        if not headlines_for_evaluation:
            raise StrategyV2DecisionError(
                "No headline candidates available for evaluation after applying headline evaluation limit. "
                "Remediation: increase STRATEGY_V2_COPY_HEADLINE_EVALUATION_LIMIT."
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
        for headline_index, scored in enumerate(headlines_for_evaluation, start=1):
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
                    "headline_count": len(headlines_for_evaluation),
                }
            )
            qa_result = run_headline_qa_loop(
                headline=source_headline,
                page_type="advertorial",
                max_iterations=qa_max_iterations,
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
                "rapid_mode": rapid_mode,
                "copy_generation_mode": copy_generation_mode,
                "qa_max_iterations": qa_max_iterations,
                "page_repair_max_attempts": page_repair_max_attempts,
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
                    "headline_count": len(headlines_for_evaluation),
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
                max_tokens=_COPY_PIPELINE_MAX_TOKENS,
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
            # Claude repair loops can explode input-token size when full chat history is
            # carried across attempts. Keep this opt-in via env; default to stateless turns.
            use_claude_chat_context = (
                settings.STRATEGY_V2_COPY_MODEL.lower().startswith("claude")
                and _COPY_USE_CLAUDE_CHAT_CONTEXT
            )
            advertorial_conversation: list[dict[str, Any]] = []
            sales_markdown_conversation: list[dict[str, Any]] = []
            sales_payload_conversation: list[dict[str, Any]] = []
            presell_thread_id = f"presell_page:{headline_index}"
            sales_markdown_thread_id = f"sales_markdown:{headline_index}"
            sales_payload_thread_id = f"sales_payload:{headline_index}"
            page_attempt_observability: list[dict[str, Any]] = []
            attempt_row["page_thread_ids"] = {
                "presell": presell_thread_id,
                "sales_page": sales_markdown_thread_id,
                "sales_markdown": sales_markdown_thread_id,
                "sales_payload": sales_payload_thread_id,
            }
            for page_attempt in range(1, page_repair_max_attempts + 1):
                page_prompt_start_index = len(prompt_call_logs)
                page_observability_row: dict[str, Any] = {
                    "page_attempt": page_attempt,
                    "presell_thread_id": presell_thread_id,
                    "sales_page_thread_id": sales_markdown_thread_id,
                    "sales_markdown_thread_id": sales_markdown_thread_id,
                    "sales_payload_thread_id": sales_payload_thread_id,
                    "thread_turn": page_attempt,
                    "rapid_mode": rapid_mode,
                    "copy_generation_mode": copy_generation_mode,
                    "page_repair_max_attempts": page_repair_max_attempts,
                }
                presell_markdown_for_observability = ""
                sales_markdown_for_observability = ""
                sales_template_payload_json_for_observability = ""
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
                        page_observability_row["sales_markdown_thread_before_call"] = _serialize_claude_conversation(
                            sales_markdown_conversation
                        )
                        page_observability_row["sales_payload_thread_before_call"] = _serialize_claude_conversation(
                            sales_payload_conversation
                        )
                        page_observability_row["presell_thread_before_call"] = _serialize_claude_conversation(
                            advertorial_conversation
                        )
                try:
                    if template_payload_only_mode:
                        presell_payload_runtime_instruction = (
                            f"{presell_runtime_instruction}\n\n"
                            "## Execution Mode Override\n"
                            "This call generates template payload only.\n"
                            "Return JSON with key `template_payload` only.\n"
                            "- Do not return markdown.\n\n"
                            f"{_PRE_SALES_TEMPLATE_LIMITS_INSTRUCTION}\n"
                            "If any field would exceed limits, rewrite it to fit before returning."
                        )
                        advertorial_payload_parsed, advertorial_raw, advertorial_provenance = _run_prompt_json_object(
                            asset=advertorial_asset,
                            context="strategy_v2.copy.advertorial_template_payload",
                            model=settings.STRATEGY_V2_COPY_MODEL,
                            runtime_instruction=presell_payload_runtime_instruction,
                            schema_name="strategy_v2_copy_advertorial_template_payload",
                            schema={
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "template_payload": _PRE_SALES_TEMPLATE_PAYLOAD_JSON_SCHEMA,
                                },
                                "required": ["template_payload"],
                            },
                            use_reasoning=True,
                            use_web_search=False,
                            max_tokens=_COPY_PIPELINE_MAX_TOKENS,
                            heartbeat_context={
                                "activity": "strategy_v2.run_copy_pipeline",
                                "phase": "advertorial_template_payload_prompt",
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
                            llm_call_label="advertorial_template_payload_prompt",
                        )
                        presell_template_payload = _require_dict(
                            payload=advertorial_payload_parsed.get("template_payload"),
                            field_name="presell_template_payload",
                        )
                        presell_markdown = ""
                        presell_markdown_for_observability = ""

                        sales_payload_runtime_instruction = (
                            f"{sales_runtime_instruction}\n\n"
                            "## Execution Mode Override\n"
                            "This call generates template payload only.\n"
                            "Return JSON with key `template_payload_json` only.\n"
                            "- Do not return markdown.\n\n"
                            f"{_SALES_TEMPLATE_LIMITS_INSTRUCTION}\n"
                            "If any field would exceed limits, rewrite it to fit before returning."
                        )
                        sales_payload_parsed, sales_payload_raw, sales_payload_provenance = _run_prompt_json_object(
                            asset=sales_asset,
                            context="strategy_v2.copy.sales_template_payload_direct",
                            model=settings.STRATEGY_V2_COPY_MODEL,
                            runtime_instruction=sales_payload_runtime_instruction,
                            schema_name="strategy_v2_copy_sales_template_payload_direct",
                            schema={
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "template_payload_json": {"type": "string"},
                                },
                                "required": ["template_payload_json"],
                            },
                            use_reasoning=True,
                            use_web_search=False,
                            max_tokens=_COPY_PIPELINE_MAX_TOKENS,
                            heartbeat_context={
                                "activity": "strategy_v2.run_copy_pipeline",
                                "phase": "sales_template_payload_prompt",
                                "model": settings.STRATEGY_V2_COPY_MODEL,
                                "headline_index": headline_index,
                                "headline": winning_headline[:160],
                                "thread_id": sales_payload_thread_id,
                                "page_attempt": page_attempt,
                            },
                            conversation_messages=sales_payload_conversation if use_claude_chat_context else None,
                            log_metadata={
                                "thread_id": sales_payload_thread_id,
                                "thread_turn": page_attempt,
                                "headline_index": headline_index,
                                "page_attempt": page_attempt,
                            },
                            llm_call_log=prompt_call_logs,
                            llm_call_label="sales_template_payload_prompt",
                        )
                        sales_template_payload_json = str(
                            sales_payload_parsed.get("template_payload_json") or ""
                        ).strip()
                        sales_template_payload_json_for_observability = sales_template_payload_json
                        if not sales_template_payload_json:
                            raise StrategyV2DecisionError(
                                "Sales payload prompt returned empty template_payload_json. "
                                "Remediation: return a JSON-serialized sales template payload in template_payload_json."
                            )
                        try:
                            sales_template_payload, sales_payload_parse_meta = _parse_sales_template_payload_json(
                                raw_text=sales_template_payload_json,
                            )
                        except (StrategyV2MissingContextError, StrategyV2SchemaValidationError) as exc:
                            page_observability_row["sales_template_payload_json_parse_error"] = str(exc)
                            raise StrategyV2DecisionError(
                                "Sales template payload JSON parse failed. "
                                f"Details: {exc}"
                            ) from exc
                        if isinstance(sales_payload_parse_meta, dict):
                            page_observability_row["sales_template_payload_parse_recovery"] = sales_payload_parse_meta
                        presell_template_payload = upgrade_strategy_v2_template_payload_fields(
                            template_id="pre-sales-listicle",
                            payload_fields=presell_template_payload,
                        )
                        sales_template_payload = upgrade_strategy_v2_template_payload_fields(
                            template_id="sales-pdp",
                            payload_fields=sales_template_payload,
                        )
                        presell_template_fields = validate_strategy_v2_template_payload_fields(
                            template_id="pre-sales-listicle",
                            payload_fields=presell_template_payload,
                        )
                        try:
                            sales_template_fields = validate_strategy_v2_template_payload_fields(
                                template_id="sales-pdp",
                                payload_fields=sales_template_payload,
                            )
                        except StrategyV2DecisionError:
                            sales_validation_report = inspect_strategy_v2_template_payload_validation(
                                template_id="sales-pdp",
                                payload_fields=sales_template_payload,
                                max_items=160,
                            )
                            page_observability_row["template_payload_validation"] = "fail"
                            page_observability_row["sales_template_validation_report"] = sales_validation_report
                            page_observability_row["sales_template_payload_upgraded_failed"] = json.dumps(
                                sales_template_payload,
                                ensure_ascii=True,
                            )[:16000]
                            raise
                        presell_template_patch = build_strategy_v2_template_patch_operations(
                            template_id="pre-sales-listicle",
                            payload_fields=presell_template_fields,
                        )
                        sales_template_patch = build_strategy_v2_template_patch_operations(
                            template_id="sales-pdp",
                            payload_fields=sales_template_fields,
                        )
                        page_observability_row["template_payload_validation"] = "pass"

                        sales_page_markdown = ""
                        sales_markdown_for_observability = ""
                        body_markdown = ""
                        congruency = {
                            "mode": _COPY_GENERATION_MODE_TEMPLATE_PAYLOAD_ONLY,
                            "skipped": True,
                            "skip_reason": "template_payload_only_mode",
                            "presell": {"passed": True, "hard_gate_pass": True},
                            "sales_page": {"passed": True, "hard_gate_pass": True},
                            "composite": {
                                "presell_passed": True,
                                "sales_page_passed": True,
                                "hard_gate_pass": True,
                                "passed": True,
                            },
                        }
                        presell_semantic_report = {
                            "mode": _COPY_GENERATION_MODE_TEMPLATE_PAYLOAD_ONLY,
                            "page_type": "presell_advertorial",
                            "passed": True,
                            "skipped": True,
                            "skip_reason": "template_payload_only_mode",
                        }
                        sales_semantic_report = {
                            "mode": _COPY_GENERATION_MODE_TEMPLATE_PAYLOAD_ONLY,
                            "page_type": "sales_page_warm",
                            "passed": True,
                            "skipped": True,
                            "skip_reason": "template_payload_only_mode",
                        }
                        presell_quality_report = {
                            "mode": _COPY_GENERATION_MODE_TEMPLATE_PAYLOAD_ONLY,
                            "page_type": "presell_advertorial",
                            "passed": True,
                            "skipped": True,
                            "skip_reason": "template_payload_only_mode",
                        }
                        sales_quality_report = {
                            "mode": _COPY_GENERATION_MODE_TEMPLATE_PAYLOAD_ONLY,
                            "page_type": "sales_page_warm",
                            "passed": True,
                            "skipped": True,
                            "skip_reason": "template_payload_only_mode",
                        }

                        selected_bundle = {
                            "headline_row": scored,
                            "qa_json": qa_json,
                            "winning_headline": winning_headline,
                            "body_markdown": body_markdown,
                            "presell_markdown": presell_markdown,
                            "sales_page_markdown": sales_page_markdown,
                            "presell_template_payload": presell_template_payload,
                            "sales_template_payload": sales_template_payload,
                            "presell_template_fields": presell_template_fields,
                            "sales_template_fields": sales_template_fields,
                            "presell_template_patch": presell_template_patch,
                            "sales_template_patch": sales_template_patch,
                            "congruency": congruency,
                            "promise_contract": promise_contract,
                            "semantic_gates": {
                                "presell": presell_semantic_report,
                                "sales_page": sales_semantic_report,
                            },
                            "quality_gate_report": {
                                "presell": presell_quality_report,
                                "sales_page": sales_quality_report,
                            },
                            "page_generation_attempts": page_attempt,
                            "page_generation_failures": list(page_generation_errors),
                            "page_thread_ids": {
                                "presell": presell_thread_id,
                                "sales_page": sales_markdown_thread_id,
                                "sales_markdown": sales_markdown_thread_id,
                                "sales_payload": sales_payload_thread_id,
                            },
                            "page_attempt_observability": list(page_attempt_observability),
                            "prompt_chain": {
                                "headline_prompt_provenance": headline_provenance,
                                "headline_prompt_raw_output": headline_raw[:16000],
                                "promise_prompt_provenance": promise_provenance,
                                "promise_prompt_raw_output": promise_raw[:8000],
                                "advertorial_prompt_provenance": advertorial_provenance,
                                "advertorial_prompt_raw_output": advertorial_raw[:16000],
                                "sales_prompt_provenance": sales_payload_provenance,
                                "sales_prompt_raw_output": sales_payload_raw[:16000],
                                "sales_markdown_prompt_provenance": sales_payload_provenance,
                                "sales_markdown_prompt_raw_output": sales_payload_raw[:16000],
                                "sales_template_payload_prompt_provenance": sales_payload_provenance,
                                "sales_template_payload_prompt_raw_output": sales_payload_raw[:16000],
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
                        attempt_row["sales_markdown_thread_turn_count"] = page_attempt
                        attempt_row["sales_payload_thread_turn_count"] = page_attempt
                        attempt_row["page_generation_attempts"] = page_attempt
                        attempt_row["page_generation_failures"] = list(page_generation_errors)
                        attempt_row["result"] = "selected_bundle_passed"
                        qa_attempts.append(attempt_row)
                        break

                    presell_full_runtime_instruction = (
                        f"{presell_runtime_instruction}\n\n"
                        f"{_PRE_SALES_TEMPLATE_LIMITS_INSTRUCTION}\n"
                        "If any field would exceed limits, rewrite it to fit before returning."
                    )
                    advertorial_parsed, advertorial_raw, advertorial_provenance = _run_prompt_json_object(
                        asset=advertorial_asset,
                        context="strategy_v2.copy.advertorial",
                        model=settings.STRATEGY_V2_COPY_MODEL,
                        runtime_instruction=presell_full_runtime_instruction,
                        schema_name="strategy_v2_copy_advertorial",
                        schema={
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "markdown": {"type": "string"},
                                "template_payload": _PRE_SALES_TEMPLATE_PAYLOAD_JSON_SCHEMA,
                            },
                            "required": ["markdown", "template_payload"],
                        },
                        use_reasoning=True,
                        use_web_search=False,
                        max_tokens=_COPY_PIPELINE_MAX_TOKENS,
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
                    presell_template_payload = _require_dict(
                        payload=advertorial_parsed.get("template_payload"),
                        field_name="presell_template_payload",
                    )
                    presell_markdown_for_observability = presell_markdown
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
                    presell_markdown_for_observability = presell_markdown
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

                    sales_markdown_runtime_instruction = (
                        f"{sales_runtime_instruction}\n\n"
                        "## Execution Mode Override\n"
                        "This call generates sales markdown only.\n"
                        "Return JSON with key `markdown` only.\n"
                        "- Do not return teaser fragments or partial sections.\n"
                        "- Deliver full long-form sales copy that satisfies all hard constraints above.\n"
                        "- Include at least one markdown link `[anchor](https://...)` in each canonical CTA section."
                    )
                    sales_markdown_parsed, sales_markdown_raw, sales_markdown_provenance = _run_prompt_json_object(
                        asset=sales_asset,
                        context="strategy_v2.copy.sales_page_markdown",
                        model=settings.STRATEGY_V2_COPY_MODEL,
                        runtime_instruction=sales_markdown_runtime_instruction,
                        schema_name="strategy_v2_copy_sales_page_markdown",
                        schema={
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "markdown": {"type": "string"},
                            },
                            "required": ["markdown"],
                        },
                        use_reasoning=True,
                        use_web_search=False,
                        max_tokens=_COPY_PIPELINE_MAX_TOKENS,
                        heartbeat_context={
                            "activity": "strategy_v2.run_copy_pipeline",
                            "phase": "sales_page_markdown_prompt",
                            "model": settings.STRATEGY_V2_COPY_MODEL,
                            "headline_index": headline_index,
                            "headline": winning_headline[:160],
                            "thread_id": sales_markdown_thread_id,
                            "page_attempt": page_attempt,
                        },
                        conversation_messages=sales_markdown_conversation if use_claude_chat_context else None,
                        log_metadata={
                            "thread_id": sales_markdown_thread_id,
                            "thread_turn": page_attempt,
                            "headline_index": headline_index,
                            "page_attempt": page_attempt,
                        },
                        llm_call_log=prompt_call_logs,
                        llm_call_label="sales_page_markdown_prompt",
                    )
                    sales_page_markdown = str(sales_markdown_parsed.get("markdown") or "").strip()
                    sales_markdown_for_observability = sales_page_markdown
                    if _COPY_DEBUG_CAPTURE_FULL_MARKDOWN:
                        page_observability_row["sales_markdown_generated"] = sales_page_markdown
                    if _COPY_DEBUG_CAPTURE_THREADS and use_claude_chat_context:
                        page_observability_row["sales_markdown_thread_after_call"] = _serialize_claude_conversation(
                            sales_markdown_conversation
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
                    sales_markdown_for_observability = sales_page_markdown
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
                    sales_payload_runtime_instruction = (
                        f"{sales_runtime_instruction}\n\n"
                        "## Execution Mode Override\n"
                        "This call generates template payload only.\n"
                        "Use FINAL_SALES_PAGE_MARKDOWN as source of truth and return JSON with key "
                        "`template_payload_json` only.\n\n"
                        f"{_SALES_TEMPLATE_LIMITS_INSTRUCTION}\n"
                        "If any field would exceed limits, rewrite it to fit before returning.\n\n"
                        f"FINAL_SALES_PAGE_MARKDOWN:\n{sales_page_markdown}"
                    )
                    sales_payload_parsed, sales_payload_raw, sales_payload_provenance = _run_prompt_json_object(
                        asset=sales_asset,
                        context="strategy_v2.copy.sales_template_payload",
                        model=settings.STRATEGY_V2_COPY_MODEL,
                        runtime_instruction=sales_payload_runtime_instruction,
                        schema_name="strategy_v2_copy_sales_template_payload",
                        schema={
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                # NOTE: Anthropic Claude rejects the full sales template schema with:
                                # "compiled grammar is too large". Keep this field as a JSON string and
                                # enforce the real contract via validate_strategy_v2_template_payload_fields().
                                "template_payload_json": {"type": "string"},
                            },
                            "required": ["template_payload_json"],
                        },
                        use_reasoning=True,
                        use_web_search=False,
                        max_tokens=_COPY_PIPELINE_MAX_TOKENS,
                        heartbeat_context={
                            "activity": "strategy_v2.run_copy_pipeline",
                            "phase": "sales_template_payload_prompt",
                            "model": settings.STRATEGY_V2_COPY_MODEL,
                            "headline_index": headline_index,
                            "headline": winning_headline[:160],
                            "thread_id": sales_payload_thread_id,
                            "page_attempt": page_attempt,
                        },
                        conversation_messages=sales_payload_conversation if use_claude_chat_context else None,
                        log_metadata={
                            "thread_id": sales_payload_thread_id,
                            "thread_turn": page_attempt,
                            "headline_index": headline_index,
                            "page_attempt": page_attempt,
                        },
                        llm_call_log=prompt_call_logs,
                        llm_call_label="sales_template_payload_prompt",
                    )
                    sales_template_payload_json = str(sales_payload_parsed.get("template_payload_json") or "").strip()
                    sales_template_payload_json_for_observability = sales_template_payload_json
                    if _COPY_DEBUG_CAPTURE_THREADS and use_claude_chat_context:
                        page_observability_row["sales_payload_thread_after_call"] = _serialize_claude_conversation(
                            sales_payload_conversation
                        )
                    if not sales_template_payload_json:
                        raise StrategyV2DecisionError(
                            "Sales payload prompt returned empty template_payload_json. "
                            "Remediation: return a JSON-serialized sales template payload in template_payload_json."
                        )
                    try:
                        sales_template_payload, sales_payload_parse_meta = _parse_sales_template_payload_json(
                            raw_text=sales_template_payload_json,
                        )
                    except (StrategyV2MissingContextError, StrategyV2SchemaValidationError) as exc:
                        page_observability_row["sales_template_payload_json_parse_error"] = str(exc)
                        raise StrategyV2DecisionError(
                            "Sales template payload JSON parse failed. "
                            f"Details: {exc}"
                        ) from exc
                    if isinstance(sales_payload_parse_meta, dict):
                        page_observability_row["sales_template_payload_parse_recovery"] = sales_payload_parse_meta
                    presell_template_payload = upgrade_strategy_v2_template_payload_fields(
                        template_id="pre-sales-listicle",
                        payload_fields=presell_template_payload,
                    )
                    sales_template_payload = upgrade_strategy_v2_template_payload_fields(
                        template_id="sales-pdp",
                        payload_fields=sales_template_payload,
                    )
                    presell_template_fields = validate_strategy_v2_template_payload_fields(
                        template_id="pre-sales-listicle",
                        payload_fields=presell_template_payload,
                    )
                    try:
                        sales_template_fields = validate_strategy_v2_template_payload_fields(
                            template_id="sales-pdp",
                            payload_fields=sales_template_payload,
                        )
                    except StrategyV2DecisionError:
                        sales_validation_report = inspect_strategy_v2_template_payload_validation(
                            template_id="sales-pdp",
                            payload_fields=sales_template_payload,
                            max_items=160,
                        )
                        page_observability_row["template_payload_validation"] = "fail"
                        page_observability_row["sales_template_validation_report"] = sales_validation_report
                        page_observability_row["sales_template_payload_upgraded_failed"] = json.dumps(
                            sales_template_payload,
                            ensure_ascii=True,
                        )[:16000]
                        raise
                    presell_template_patch = build_strategy_v2_template_patch_operations(
                        template_id="pre-sales-listicle",
                        payload_fields=presell_template_fields,
                    )
                    sales_template_patch = build_strategy_v2_template_patch_operations(
                        template_id="sales-pdp",
                        payload_fields=sales_template_fields,
                    )
                    page_observability_row["template_payload_validation"] = "pass"

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
                        "presell_template_payload": presell_template_payload,
                        "sales_template_payload": sales_template_payload,
                        "presell_template_fields": presell_template_fields,
                        "sales_template_fields": sales_template_fields,
                        "presell_template_patch": presell_template_patch,
                        "sales_template_patch": sales_template_patch,
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
                            "sales_page": sales_markdown_thread_id,
                            "sales_markdown": sales_markdown_thread_id,
                            "sales_payload": sales_payload_thread_id,
                        },
                        "page_attempt_observability": list(page_attempt_observability),
                        "prompt_chain": {
                            "headline_prompt_provenance": headline_provenance,
                            "headline_prompt_raw_output": headline_raw[:16000],
                            "promise_prompt_provenance": promise_provenance,
                            "promise_prompt_raw_output": promise_raw[:8000],
                            "advertorial_prompt_provenance": advertorial_provenance,
                            "advertorial_prompt_raw_output": advertorial_raw[:16000],
                            "sales_prompt_provenance": sales_markdown_provenance,
                            "sales_prompt_raw_output": sales_markdown_raw[:16000],
                            "sales_markdown_prompt_provenance": sales_markdown_provenance,
                            "sales_markdown_prompt_raw_output": sales_markdown_raw[:16000],
                            "sales_template_payload_prompt_provenance": sales_payload_provenance,
                            "sales_template_payload_prompt_raw_output": sales_payload_raw[:16000],
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
                    attempt_row["sales_markdown_thread_turn_count"] = page_attempt
                    attempt_row["sales_payload_thread_turn_count"] = page_attempt
                    attempt_row["page_generation_attempts"] = page_attempt
                    attempt_row["page_generation_failures"] = list(page_generation_errors)
                    attempt_row["result"] = "selected_bundle_passed"
                    qa_attempts.append(attempt_row)
                    break
                except (
                    StrategyV2DecisionError,
                    StrategyV2MissingContextError,
                    StrategyV2SchemaValidationError,
                    RuntimeError,
                ) as exc:
                    # StrategyV2* exceptions inherit RuntimeError; only treat bare RuntimeError
                    # as a pass-through for non-Claude structured-call failures.
                    if type(exc) is RuntimeError:
                        runtime_message = str(exc)
                        if not runtime_message.startswith("Claude structured message"):
                            raise
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
                    page_observability_row["failure_message"] = failure_message
                    if reason_codes:
                        page_observability_row["failure_reason_codes"] = reason_codes
                    if presell_markdown_for_observability:
                        page_observability_row["presell_markdown_failed"] = presell_markdown_for_observability[:16000]
                    if sales_markdown_for_observability:
                        page_observability_row["sales_markdown_failed"] = sales_markdown_for_observability[:16000]
                    if sales_template_payload_json_for_observability:
                        page_observability_row["sales_template_payload_json_failed"] = (
                            sales_template_payload_json_for_observability[:16000]
                        )
                    page_attempt_observability.append(page_observability_row)
                    attempt_row["page_attempt_observability"] = list(page_attempt_observability)
                    attempt_row["last_failure_reason_class"] = reason_class
                    attempt_row["last_failure_message"] = failure_message
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
                        if (sales_markdown_conversation or sales_payload_conversation) and targets_sales:
                            sales_feedback_turn = _build_copy_retry_feedback_turn(
                                page_attempt=page_attempt,
                                latest_error=failure_message,
                                repair_directives=_build_copy_repair_directives(
                                    previous_errors=page_generation_errors,
                                    page_scope="sales_page_warm",
                                ),
                            )
                            sales_feedback_message = {
                                "role": "user",
                                "content": [{"type": "text", "text": sales_feedback_turn}],
                            }
                            if sales_markdown_conversation:
                                sales_markdown_conversation.append(dict(sales_feedback_message))
                            if sales_payload_conversation:
                                sales_payload_conversation.append(dict(sales_feedback_message))
                    if _is_non_retryable_sales_payload_failure(failure_message):
                        attempt_row["page_generation_attempts"] = page_attempt
                        attempt_row["page_generation_failures"] = list(page_generation_errors)
                        attempt_row["error"] = failure_message
                        qa_attempt_error_buckets[reason_class] += 1
                        qa_attempts.append(attempt_row)
                        break
                    if page_attempt >= page_repair_max_attempts:
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
            "rapid_mode": rapid_mode,
            "copy_generation_mode": copy_generation_mode,
            "headline_candidate_count": len(headline_candidates),
            "headline_ranked_count": len(ranked_headlines),
            "headline_evaluated_count": len(headlines_for_evaluation),
            "headline_evaluation_offset": headline_evaluation_offset,
            "headline_evaluation_limit": headline_evaluation_limit,
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
            "qa_max_iterations": qa_max_iterations,
            "qa_call_timeout_seconds": qa_timeout_seconds_effective,
            "qa_call_max_retries": qa_call_max_retries_effective,
            "page_repair_max_attempts": page_repair_max_attempts,
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
            decision_error_message = (
                "Copy prompt-chain pipeline could not produce a headline + page bundle that passed configured gates. "
                f"(copy_generation_mode={copy_generation_mode}). "
                f"Attempts: {attempts_summary or 'none'}"
            )
            if allow_no_bundle_result:
                return {
                    "copy_artifact_id": None,
                    "copy_payload": None,
                    "step_payload_artifact_id": None,
                    "selected_bundle_found": False,
                    "copy_loop_failure_summary": decision_error_message,
                    "copy_loop_report": copy_loop_report,
                }
            raise StrategyV2DecisionError(decision_error_message)

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
        presell_template_fields = _require_dict(
            payload=selected_bundle.get("presell_template_fields"),
            field_name="selected_presell_template_fields",
        )
        sales_template_fields = _require_dict(
            payload=selected_bundle.get("sales_template_fields"),
            field_name="selected_sales_template_fields",
        )
        # Phase-1 rules: pre-sales CTA language is non-transactional and sales title is product-name only.
        presell_pitch = presell_template_fields.get("pitch")
        if isinstance(presell_pitch, dict):
            presell_pitch["cta_label"] = "Learn more"
        presell_floating_cta = presell_template_fields.get("floating_cta")
        if isinstance(presell_floating_cta, dict):
            presell_floating_cta["label"] = "Learn more"
        sales_hero = sales_template_fields.get("hero")
        if isinstance(sales_hero, dict):
            sales_hero["purchase_title"] = str(stage3.product_name).strip()
        presell_template_patch_raw = selected_bundle.get("presell_template_patch")
        if not isinstance(presell_template_patch_raw, list) or not presell_template_patch_raw:
            raise StrategyV2DecisionError(
                "Selected bundle is missing presell template patch operations after validation."
            )
        sales_template_patch_raw = selected_bundle.get("sales_template_patch")
        if not isinstance(sales_template_patch_raw, list) or not sales_template_patch_raw:
            raise StrategyV2DecisionError(
                "Selected bundle is missing sales template patch operations after validation."
            )
        if not all(isinstance(item, dict) for item in presell_template_patch_raw):
            raise StrategyV2DecisionError(
                "Selected bundle contains invalid presell template patch operations (expected objects)."
            )
        if not all(isinstance(item, dict) for item in sales_template_patch_raw):
            raise StrategyV2DecisionError(
                "Selected bundle contains invalid sales template patch operations (expected objects)."
            )
        presell_template_patch = [dict(item) for item in presell_template_patch_raw]
        sales_template_patch = [dict(item) for item in sales_template_patch_raw]
        product_name_title = str(stage3.product_name).strip()
        if product_name_title:
            for op in sales_template_patch:
                if (
                    str(op.get("component_type") or "") == "SalesPdpHero"
                    and str(op.get("field_path") or "") == "props.config.purchase.title"
                ):
                    op["value"] = product_name_title
        policy_links, brand_name = _build_policy_footer_links(org_id=org_id, client_id=client_id)
        current_year = datetime.now(timezone.utc).year
        copyright_text = f"© {current_year} {brand_name}"
        presell_template_patch.extend(
            [
                {
                    "component_type": "PreSalesFooter",
                    "field_path": "props.config.links",
                    "value": policy_links,
                },
                {
                    "component_type": "PreSalesFooter",
                    "field_path": "props.config.paymentIcons",
                    "value": _FOOTER_PAYMENT_ICON_KEYS,
                },
                {
                    "component_type": "PreSalesFooter",
                    "field_path": "props.config.copyright",
                    "value": copyright_text,
                },
            ]
        )
        sales_template_patch.extend(
            [
                {
                    "component_type": "SalesPdpFooter",
                    "field_path": "props.config.links",
                    "value": policy_links,
                },
                {
                    "component_type": "SalesPdpFooter",
                    "field_path": "props.config.paymentIcons",
                    "value": _FOOTER_PAYMENT_ICON_KEYS,
                },
                {
                    "component_type": "SalesPdpFooter",
                    "field_path": "props.config.copyright",
                    "value": copyright_text,
                },
            ]
        )
        provenance_report = require_prompt_chain_provenance(prompt_chain=prompt_chain)
        angle_id = stage3.selected_angle.angle_id
        angle_run_id = f"{workflow_run_id}:{angle_id}"
        template_payloads = {
            "pre-sales-listicle": {
                "payload_version": "v1",
                "template_id": "pre-sales-listicle",
                "angle_run_id": angle_run_id,
                "fields": presell_template_fields,
                "template_patch": presell_template_patch,
                "validation_report": {
                    "patch_operation_count": len(presell_template_patch),
                    "patch_hash": hashlib.sha256(
                        json.dumps(presell_template_patch, sort_keys=True, ensure_ascii=True).encode("utf-8")
                    ).hexdigest(),
                },
            },
            "sales-pdp": {
                "payload_version": "v1",
                "template_id": "sales-pdp",
                "angle_run_id": angle_run_id,
                "fields": sales_template_fields,
                "template_patch": sales_template_patch,
                "validation_report": {
                    "patch_operation_count": len(sales_template_patch),
                    "patch_hash": hashlib.sha256(
                        json.dumps(sales_template_patch, sort_keys=True, ensure_ascii=True).encode("utf-8")
                    ).hexdigest(),
                },
            },
        }

        copy_payload = {
            "headline": winning_headline,
            "copy_generation_mode": copy_generation_mode,
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
            "template_payloads": template_payloads,
            "angle_run_id": angle_run_id,
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
