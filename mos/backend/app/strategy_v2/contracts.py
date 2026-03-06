from __future__ import annotations

from typing import Any, Literal, Mapping, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.strategy_v2.errors import StrategyV2SchemaValidationError


SCHEMA_VERSION_V2 = "2.0.0"


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProductBriefStageBase(StrictContract):
    schema_version: Literal["2.0.0"] = SCHEMA_VERSION_V2
    product_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    price: str = Field(min_length=1)
    competitor_urls: list[str] = Field(default_factory=list)
    product_customizable: bool


class ProductBriefStage0(ProductBriefStageBase):
    stage: Literal[0] = 0


class PrimarySegment(StrictContract):
    name: str = Field(min_length=1)
    size_estimate: str = Field(min_length=1)
    key_differentiator: str = Field(min_length=1)


class ProductBriefStage1(ProductBriefStageBase):
    stage: Literal[1] = 1
    category_niche: str = Field(min_length=1)
    product_category_keywords: list[str] = Field(default_factory=list)
    market_maturity_stage: Literal["Introduction", "Growth", "Maturity", "Decline"] | None = None
    primary_segment: PrimarySegment
    bottleneck: str = Field(min_length=1)
    positioning_gaps: list[str] = Field(default_factory=list)
    competitor_count_validated: int | None = None
    primary_icps: list[str] = Field(default_factory=list)


class BeliefShift(StrictContract):
    before: str = Field(min_length=1)
    after: str = Field(min_length=1)


class SelectedAngleDefinition(StrictContract):
    who: str = Field(min_length=1)
    pain_desire: str = Field(min_length=1)
    mechanism_why: str = Field(min_length=1)
    belief_shift: BeliefShift
    trigger: str = Field(min_length=1)


class SelectedAngleEvidenceQuote(StrictContract):
    voc_id: str = ""
    quote: str = Field(min_length=1)
    adjusted_score: float | None = None


class SelectedAngleEvidence(StrictContract):
    supporting_voc_count: int = Field(ge=0)
    top_quotes: list[SelectedAngleEvidenceQuote] = Field(default_factory=list)
    triangulation_status: Literal["SINGLE", "DUAL", "MULTI"] | None = None
    velocity_status: Literal["ACCELERATING", "STEADY", "DECELERATING"] | None = None
    contradiction_count: int = Field(default=0, ge=0)


class HookStarter(StrictContract):
    visual: str = Field(min_length=1)
    opening_line: str = Field(min_length=1)
    lever: str = Field(min_length=1)


class SelectedAngleContract(StrictContract):
    angle_id: str = Field(min_length=1)
    angle_name: str = Field(min_length=1)
    definition: SelectedAngleDefinition
    evidence: SelectedAngleEvidence
    hook_starters: list[HookStarter] = Field(default_factory=list)


class ComplianceConstraints(StrictContract):
    overall_risk: Literal["GREEN", "YELLOW", "RED"]
    red_flag_patterns: list[str] = Field(default_factory=list)
    platform_notes: str | None = None


class ProductBriefStage2(ProductBriefStage1):
    stage: Literal[2] = 2
    selected_angle: SelectedAngleContract
    compliance_constraints: ComplianceConstraints | None = None
    buyer_behavior_archetype: str | None = None
    purchase_emotion: str | None = None
    price_sensitivity: Literal["low", "medium", "high"] | None = None


class ProductBriefStage3(ProductBriefStage2):
    stage: Literal[3] = 3
    ump: str = Field(min_length=1)
    ums: str = Field(min_length=1)
    core_promise: str = Field(min_length=1)
    value_stack_summary: list[str] = Field(default_factory=list)
    guarantee_type: str | None = None
    pricing_rationale: str | None = None
    awareness_level_primary: Literal[
        "Unaware", "Problem-Aware", "Solution-Aware", "Product-Aware", "Most-Aware"
    ] | None = None
    sophistication_level: int | None = Field(default=None, ge=1, le=5)
    composite_score: float | None = None
    variant_selected: str | None = None
    offer_format: Literal["DISCOUNT_PLUS_3_BONUSES_V1"] | None = None
    product_type: str | None = None
    pricing_metadata: dict[str, Any] | None = None
    savings_metadata: dict[str, Any] | None = None
    best_value_metadata: dict[str, Any] | None = None
    bundle_contents: dict[str, Any] | None = None
    bonus_stack: list[dict[str, Any]] = Field(default_factory=list)


class AwarenessLevelFraming(StrictContract):
    frame: str = Field(min_length=1)
    headline_direction: str = Field(min_length=1)
    entry_emotion: str = Field(min_length=1)
    exit_belief: str = Field(min_length=1)


class AwarenessFramingMap(StrictContract):
    unaware: AwarenessLevelFraming
    problem_aware: AwarenessLevelFraming
    solution_aware: AwarenessLevelFraming
    product_aware: AwarenessLevelFraming
    most_aware: AwarenessLevelFraming


class AwarenessAngleMatrix(StrictContract):
    angle_name: str = Field(min_length=1)
    awareness_framing: AwarenessFramingMap
    constant_elements: list[str] = Field(default_factory=list)
    variable_elements: list[str] = Field(default_factory=list)
    product_name_first_appears: str | None = None


class OfferPipelineConfig(StrictContract):
    llm_model: str = Field(min_length=1)
    max_iterations: int = Field(default=2, ge=1, le=5)
    score_threshold: float = Field(default=5.5, ge=0.0, le=10.0)


class OfferProductConstraints(StrictContract):
    compliance_sensitivity: Literal["low", "medium", "high"]
    existing_proof_assets: list[str] = Field(default_factory=list)
    brand_voice_notes: str = Field(min_length=1)


class OfferProductBrief(StrictContract):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    category: str = Field(min_length=1)
    price_cents: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    business_model: str = Field(min_length=1)
    funnel_position: str = Field(min_length=1)
    target_platforms: list[str] = Field(default_factory=list, min_length=1)
    target_regions: list[str] = Field(default_factory=list, min_length=1)
    product_customizable: bool
    constraints: OfferProductConstraints


class OfferPipelineInput(StrictContract):
    product_brief: OfferProductBrief
    selected_angle: SelectedAngleContract
    competitor_teardowns: str = Field(min_length=1)
    voc_research: str = Field(min_length=1)
    purple_ocean_research: str = Field(min_length=1)
    config: OfferPipelineConfig


class CopyContextFiles(StrictContract):
    audience_product_markdown: str = Field(min_length=1)
    brand_voice_markdown: str = Field(min_length=1)
    compliance_markdown: str = Field(min_length=1)
    mental_models_markdown: str = Field(min_length=1)
    awareness_angle_matrix_markdown: str = Field(min_length=1)


class CandidateAssetMetrics(StrictContract):
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    followers: int | None = Field(default=None, ge=0)
    days_since_posted: int | None = Field(default=None, ge=0)
    date_posted: str | None = None


class CompetitorAssetCandidate(StrictContract):
    candidate_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    competitor_name: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    asset_kind: Literal["VIDEO", "IMAGE", "TEXT", "PAGE"] = "PAGE"
    headline_or_caption: str = ""
    metrics: CandidateAssetMetrics = Field(default_factory=CandidateAssetMetrics)
    proof_type: str = "NONE"
    running_duration: str = "UNKNOWN"
    estimated_spend_tier: str = "UNKNOWN"
    compliance_risk: Literal["GREEN", "YELLOW", "RED"] = "YELLOW"
    raw_source_artifact_id: str | None = None


class SocialVideoObservation(StrictContract):
    video_id: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    views: int = Field(ge=0)
    followers: int = Field(ge=0)
    comments: int = Field(ge=0)
    shares: int = Field(ge=0)
    likes: int = Field(ge=0)
    days_since_posted: int = Field(ge=0)
    description: str = ""
    author: str = ""
    source_ref: str = Field(min_length=1)


class VocEngagement(StrictContract):
    likes: int = Field(default=0, ge=0)
    replies: int = Field(default=0, ge=0)


class ExternalVocCorpusItem(StrictContract):
    voc_id: str = Field(min_length=1)
    source_type: Literal[
        "REDDIT",
        "FORUM",
        "BLOG_COMMENT",
        "REVIEW_SITE",
        "QA",
        "TIKTOK_COMMENT",
        "IG_COMMENT",
        "YT_COMMENT",
        "VIDEO_HOOK",
    ]
    source_role: Literal["COMMENT", "HOOK"]
    source_role_reason: str | None = None
    source_url: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    author: str = "Unknown"
    date: str = "Unknown"
    quote: str = Field(min_length=1)
    is_hook: Literal["Y", "N"] = "N"
    hook_format: Literal["QUESTION", "STATEMENT", "STORY", "STATISTIC", "CONTRARIAN", "DEMONSTRATION", "NONE"] = "NONE"
    hook_word_count: int = Field(default=0, ge=0)
    video_virality_tier: Literal["VIRAL", "HIGH_PERFORMING", "ABOVE_AVERAGE", "BASELINE"] | None = None
    video_view_count: int | None = Field(default=None, ge=0)
    thread_title: str | None = None
    engagement: VocEngagement = Field(default_factory=VocEngagement)
    compliance_risk: Literal["GREEN", "YELLOW", "RED"] = "YELLOW"


class ProofAssetCandidate(StrictContract):
    proof_id: str = Field(min_length=1)
    proof_note: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=2, max_length=5)
    evidence_count: int = Field(ge=2)
    compliance_flag: Literal["GREEN", "YELLOW", "RED"] = "YELLOW"


DecisionMode = Literal["manual", "internal_automation"]


class DecisionAttestation(StrictContract):
    reviewed_evidence: bool
    understands_impact: bool


class AngleSelectionDecision(StrictContract):
    operator_user_id: str = Field(min_length=1)
    decision_mode: DecisionMode = "manual"
    selected_angle: SelectedAngleContract
    rejected_angle_ids: list[str] = Field(default_factory=list)
    reviewed_candidate_ids: list[str] = Field(default_factory=list)
    attestation: DecisionAttestation
    operator_note: str | None = None


class ResearchProceedDecision(StrictContract):
    operator_user_id: str = Field(min_length=1)
    decision_mode: DecisionMode = "manual"
    proceed: bool
    attestation: DecisionAttestation
    operator_note: str | None = None


class CompetitorAssetConfirmationDecision(StrictContract):
    operator_user_id: str = Field(min_length=1)
    decision_mode: DecisionMode = "manual"
    confirmed_asset_refs: list[str] = Field(min_length=3, max_length=15)
    reviewed_candidate_ids: list[str] = Field(default_factory=list)
    attestation: DecisionAttestation
    operator_note: str | None = None


class UmpUmsSelectionDecision(StrictContract):
    operator_user_id: str = Field(min_length=1)
    decision_mode: DecisionMode = "manual"
    pair_id: str = Field(min_length=1)
    rejected_pair_ids: list[str] = Field(default_factory=list)
    reviewed_candidate_ids: list[str] = Field(default_factory=list)
    attestation: DecisionAttestation
    operator_note: str | None = None


class OfferWinnerSelectionDecision(StrictContract):
    operator_user_id: str = Field(min_length=1)
    decision_mode: DecisionMode = "manual"
    variant_id: str = Field(min_length=1)
    rejected_variant_ids: list[str] = Field(default_factory=list)
    reviewed_candidate_ids: list[str] = Field(default_factory=list)
    attestation: DecisionAttestation
    operator_note: str | None = None


class FinalCopyApprovalDecision(StrictContract):
    operator_user_id: str = Field(min_length=1)
    decision_mode: DecisionMode = "manual"
    approved: bool
    reviewed_candidate_ids: list[str] = Field(default_factory=list)
    attestation: DecisionAttestation
    operator_note: str | None = None


ContractModelT = TypeVar("ContractModelT", bound=BaseModel)


def _format_validation_errors(exc: ValidationError) -> str:
    entries: list[str] = []
    for issue in exc.errors():
        location = ".".join(str(part) for part in issue.get("loc", ()))
        message = str(issue.get("msg", "validation error"))
        entries.append(f"{location}: {message}" if location else message)
    return "; ".join(entries)


def validate_contract(
    *,
    payload: Mapping[str, object],
    model: type[ContractModelT],
    contract_name: str,
) -> ContractModelT:
    try:
        return model.model_validate(dict(payload))
    except ValidationError as exc:
        raise StrategyV2SchemaValidationError(
            f"{contract_name} validation failed: {_format_validation_errors(exc)}"
        ) from exc


def validate_stage0(payload: Mapping[str, object]) -> ProductBriefStage0:
    return validate_contract(payload=payload, model=ProductBriefStage0, contract_name="ProductBriefStage0")


def validate_stage1(payload: Mapping[str, object]) -> ProductBriefStage1:
    return validate_contract(payload=payload, model=ProductBriefStage1, contract_name="ProductBriefStage1")


def validate_stage2(payload: Mapping[str, object]) -> ProductBriefStage2:
    return validate_contract(payload=payload, model=ProductBriefStage2, contract_name="ProductBriefStage2")


def validate_stage3(payload: Mapping[str, object]) -> ProductBriefStage3:
    return validate_contract(payload=payload, model=ProductBriefStage3, contract_name="ProductBriefStage3")
