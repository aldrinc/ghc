from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.strategy_v2.contracts import SCHEMA_VERSION_V2, StrictContract


CopySignalType = Literal[
    "hook_or_quote",
    "pain_or_bottleneck",
    "failed_solution_logic",
    "mechanism_signal",
    "proof_signal",
    "offer_signal",
    "value_stack_signal",
    "guarantee_signal",
    "pricing_signal",
    "compliance_signal",
]


class CopySectionContract(StrictContract):
    section_key: str = Field(min_length=1)
    canonical_title: str = Field(min_length=1)
    belief_stage: str = Field(min_length=1)
    title_markers: list[str] = Field(min_length=1)
    required_signals: list[CopySignalType] = Field(default_factory=list)
    requires_markdown_link: bool = False


class CopyPageContract(StrictContract):
    page_type: Literal["presell_advertorial", "sales_page_warm"]
    required_sections: list[CopySectionContract] = Field(min_length=1)
    expected_belief_sequence: list[str] = Field(min_length=1)
    min_markdown_links: int = Field(default=1, ge=0)
    first_cta_section_max: int = Field(default=6, ge=1)
    require_guarantee_near_cta: bool = False


class CopyContractProfile(StrictContract):
    schema_version: Literal["2.0.0"] = SCHEMA_VERSION_V2
    profile_id: Literal["strategy_v2_warm_presell_v1"] = "strategy_v2_warm_presell_v1"
    source_of_truth_paths: list[str] = Field(min_length=1)
    presell_advertorial: CopyPageContract
    sales_page_warm: CopyPageContract


class CopyPageQualityThresholds(StrictContract):
    page_type: Literal["presell_advertorial", "sales_page_warm"]
    word_floor: int = Field(ge=1)
    word_ceiling: int = Field(ge=1)
    min_sections: int = Field(ge=1)
    cta_min: int = Field(ge=0)
    cta_max: int = Field(ge=0)
    mechanism_depth_floor: int | None = Field(default=None, ge=0)
    offer_depth_floor: int | None = Field(default=None, ge=0)
    proof_depth_floor: int | None = Field(default=None, ge=0)
    guarantee_depth_floor: int | None = Field(default=None, ge=0)


def get_copy_quality_thresholds(*, page_type: Literal["presell_advertorial", "sales_page_warm"]) -> CopyPageQualityThresholds:
    if page_type == "presell_advertorial":
        return CopyPageQualityThresholds(
            page_type="presell_advertorial",
            # Source-of-truth normalization:
            # - Section 2 template: advertorial 800-1200 with end CTA
            # - DR constraints: advertorial may run longer depending proof depth
            # Runtime profile keeps strict floor and bounded ceiling for warm-presell execution.
            word_floor=800,
            word_ceiling=1600,
            min_sections=6,
            cta_min=1,
            cta_max=3,
            mechanism_depth_floor=150,
            offer_depth_floor=90,
        )
    return CopyPageQualityThresholds(
        page_type="sales_page_warm",
        # Source-of-truth normalization:
        # - Warm traffic guidance: 1800-2800 target
        # - DR constraints hard ceiling retained at 3500 for controllable long-form range
        word_floor=1800,
        word_ceiling=3500,
        min_sections=10,
        cta_min=3,
        cta_max=4,
        proof_depth_floor=220,
        guarantee_depth_floor=80,
    )


def default_copy_contract_profile() -> CopyContractProfile:
    return CopyContractProfile(
        source_of_truth_paths=[
            "V2 Fixes/Copywriting Agent — Final/SYSTEM_README.md",
            "V2 Fixes/Copywriting Agent — Final/ARCHITECTURE_MAP.md",
            "V2 Fixes/Copywriting Agent — Final/04_prompt_templates/advertorial_writing.md",
            "V2 Fixes/Copywriting Agent — Final/04_prompt_templates/sales_page_writing.md",
            "V2 Fixes/Copywriting Agent — Final/01_governance/sections/Section 2 - Page-Type Templates.md",
            "V2 Fixes/Copywriting Agent — Final/01_governance/sections/Section 9 - Section-Level Job Definitions.md",
        ],
        presell_advertorial=CopyPageContract(
            page_type="presell_advertorial",
            required_sections=[
                CopySectionContract(
                    section_key="hook_lead",
                    canonical_title="Hook/Lead",
                    belief_stage="B1",
                    title_markers=["hook", "lead", "problem reality"],
                    required_signals=["hook_or_quote"],
                ),
                CopySectionContract(
                    section_key="problem_crystallization",
                    canonical_title="Problem Crystallization",
                    belief_stage="B1-B2",
                    title_markers=["problem crystallization", "problem"],
                    required_signals=["pain_or_bottleneck"],
                ),
                CopySectionContract(
                    section_key="failed_solutions",
                    canonical_title="Failed Solutions",
                    belief_stage="B2-B3",
                    title_markers=["failed solutions", "failed", "what she tried"],
                    required_signals=["failed_solution_logic"],
                ),
                CopySectionContract(
                    section_key="mechanism_reveal",
                    canonical_title="Mechanism Reveal",
                    belief_stage="B3",
                    title_markers=["mechanism reveal", "mechanism exposure", "mechanism"],
                    required_signals=["mechanism_signal"],
                ),
                CopySectionContract(
                    section_key="proof_bridge",
                    canonical_title="Proof + Bridge",
                    belief_stage="B3-B4",
                    title_markers=["proof + bridge", "proof and bridge", "proof"],
                    required_signals=["proof_signal", "offer_signal"],
                ),
                CopySectionContract(
                    section_key="transition_cta",
                    canonical_title="Transition CTA",
                    belief_stage="B4",
                    title_markers=["transition cta", "continue to offer", "cta"],
                    required_signals=["offer_signal"],
                    requires_markdown_link=True,
                ),
            ],
            expected_belief_sequence=["B1", "B1-B2", "B2-B3", "B3", "B3-B4", "B4"],
            min_markdown_links=1,
            first_cta_section_max=6,
            require_guarantee_near_cta=False,
        ),
        sales_page_warm=CopyPageContract(
            page_type="sales_page_warm",
            required_sections=[
                CopySectionContract(
                    section_key="hero_stack",
                    canonical_title="Hero Stack",
                    belief_stage="B5",
                    title_markers=["hero stack", "hero", "offer mechanism"],
                    required_signals=["offer_signal"],
                    requires_markdown_link=True,
                ),
                CopySectionContract(
                    section_key="problem_recap",
                    canonical_title="Problem Recap",
                    belief_stage="B1-B4 recap",
                    title_markers=["problem recap", "problem"],
                    required_signals=["pain_or_bottleneck"],
                ),
                CopySectionContract(
                    section_key="mechanism_comparison",
                    canonical_title="Mechanism + Comparison",
                    belief_stage="B5",
                    title_markers=["mechanism + comparison", "mechanism", "comparison"],
                    required_signals=["mechanism_signal"],
                ),
                CopySectionContract(
                    section_key="identity_bridge",
                    canonical_title="Identity Bridge",
                    belief_stage="B6",
                    title_markers=["identity bridge", "identity"],
                    required_signals=[],
                ),
                CopySectionContract(
                    section_key="social_proof",
                    canonical_title="Social Proof",
                    belief_stage="B5-B6",
                    title_markers=["social proof", "proof and buyer language", "proof"],
                    required_signals=["proof_signal"],
                ),
                CopySectionContract(
                    section_key="cta_1",
                    canonical_title="CTA #1",
                    belief_stage="B7-B8",
                    title_markers=["cta #1", "cta 1", "first cta", "purchase decision"],
                    required_signals=["offer_signal"],
                    requires_markdown_link=True,
                ),
                CopySectionContract(
                    section_key="whats_inside",
                    canonical_title="What's Inside",
                    belief_stage="B5",
                    title_markers=["what's inside", "whats inside", "inside"],
                    required_signals=["value_stack_signal"],
                ),
                CopySectionContract(
                    section_key="bonus_stack",
                    canonical_title="Bonus Stack + Value",
                    belief_stage="B7",
                    title_markers=["bonus stack", "value stack", "bonus"],
                    required_signals=["value_stack_signal"],
                ),
                CopySectionContract(
                    section_key="guarantee",
                    canonical_title="Guarantee",
                    belief_stage="B8",
                    title_markers=["guarantee", "risk reversal"],
                    required_signals=["guarantee_signal"],
                ),
                CopySectionContract(
                    section_key="cta_2",
                    canonical_title="CTA #2",
                    belief_stage="B7-B8",
                    title_markers=["cta #2", "cta 2", "second cta"],
                    required_signals=["offer_signal"],
                    requires_markdown_link=True,
                ),
                CopySectionContract(
                    section_key="faq",
                    canonical_title="FAQ",
                    belief_stage="B5-B8",
                    title_markers=["faq", "questions"],
                    required_signals=["compliance_signal"],
                ),
                CopySectionContract(
                    section_key="cta_3_ps",
                    canonical_title="CTA #3 + P.S.",
                    belief_stage="B8",
                    title_markers=["cta #3", "cta 3", "p.s", "ps"],
                    required_signals=["offer_signal"],
                    requires_markdown_link=True,
                ),
            ],
            expected_belief_sequence=[
                "B5",
                "B1-B4 recap",
                "B5",
                "B6",
                "B5-B6",
                "B7-B8",
                "B5",
                "B7",
                "B8",
                "B7-B8",
                "B5-B8",
                "B8",
            ],
            min_markdown_links=3,
            first_cta_section_max=5,
            require_guarantee_near_cta=True,
        ),
    )


def get_page_contract(*, profile: CopyContractProfile, page_type: Literal["presell_advertorial", "sales_page_warm"]) -> CopyPageContract:
    if page_type == "presell_advertorial":
        return profile.presell_advertorial
    return profile.sales_page_warm
