# pyright: reportUnknownVariableType=false
from typing import Literal, Mapping, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from prompts.prompt_types import Stack


class ViewportSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int = 1440
    height: int = 1024
    device: Literal["desktop", "mobile"] = "desktop"


class InteractionCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    trigger: str
    expected_result: str


class DesignTokenSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    colors: list[str] = Field(default_factory=list)
    typography: list[str] = Field(default_factory=list)
    spacing: list[str] = Field(default_factory=list)
    radii: list[str] = Field(default_factory=list)
    shadows: list[str] = Field(default_factory=list)
    motion: list[str] = Field(default_factory=list)


class SectionRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    purpose: str = ""
    layout: str = ""
    must_include: list[str] = Field(default_factory=list)
    styling: list[str] = Field(default_factory=list)
    copy_items: list[str] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)
    behaviors: list[str] = Field(default_factory=list)
    editable_fields: list[str] = Field(default_factory=list)


class RequirementsSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    template_goal: str = ""
    viewport: ViewportSpec = Field(default_factory=ViewportSpec)
    hard_constraints: list[str] = Field(default_factory=list)
    preserve_requirements: list[str] = Field(default_factory=list)
    design_tokens: DesignTokenSet = Field(default_factory=DesignTokenSet)
    section_requirements: list[SectionRequirement] = Field(default_factory=list)
    layout_requirements: list[str] = Field(default_factory=list)
    styling_requirements: list[str] = Field(default_factory=list)
    copy_requirements: list[str] = Field(default_factory=list)
    asset_requirements: list[str] = Field(default_factory=list)
    behavior_requirements: list[str] = Field(default_factory=list)
    animation_requirements: list[str] = Field(default_factory=list)
    structure_guidance: list[str] = Field(default_factory=list)
    execution_plan: list[str] = Field(default_factory=list)
    known_unknowns: list[str] = Field(default_factory=list)
    interaction_checkpoints: list[InteractionCheckpoint] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class ReferenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_mode: Literal["image", "video", "text"]
    stack: Stack
    user_text: str = ""
    images: list[str] = Field(default_factory=list)
    videos: list[str] = Field(default_factory=list)


class RenderArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    viewport_screenshot_data_url: str
    full_page_screenshot_data_url: str | None = None
    settled_viewport_screenshot_data_url: str | None = None
    settled_full_page_screenshot_data_url: str | None = None
    timeline_frames: list["RenderTimelineFrame"] = Field(default_factory=list)
    viewport: ViewportSpec = Field(default_factory=ViewportSpec)


class RenderTimelineFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    elapsed_ms: int
    viewport_screenshot_data_url: str


ValidationSeverity = Literal["critical", "major", "minor"]
ValidationIssueCategory = Literal[
    "layout",
    "styling",
    "copy",
    "imagery",
    "behavior",
    "animation",
    "structure",
]
ValidationVerdict = Literal["pass", "revise", "blocked"]

_SEVERITY_NORMALIZATION: dict[str, ValidationSeverity] = {
    "critical": "critical",
    "blocker": "critical",
    "high": "critical",
    "major": "major",
    "medium": "major",
    "warning": "major",
    "minor": "minor",
    "low": "minor",
    "info": "minor",
}
_CATEGORY_NORMALIZATION: dict[str, ValidationIssueCategory] = {
    "layout": "layout",
    "spacing": "layout",
    "alignment": "layout",
    "positioning": "layout",
    "responsiveness": "layout",
    "styling": "styling",
    "style": "styling",
    "visual": "styling",
    "visibility": "styling",
    "contrast": "styling",
    "color": "styling",
    "typography": "styling",
    "copy": "copy",
    "content": "copy",
    "text": "copy",
    "imagery": "imagery",
    "image": "imagery",
    "images": "imagery",
    "iconography": "imagery",
    "asset": "imagery",
    "assets": "imagery",
    "behavior": "behavior",
    "interaction": "behavior",
    "state": "behavior",
    "animation": "animation",
    "motion": "animation",
    "transition": "animation",
    "structure": "structure",
    "editability": "structure",
    "templating": "structure",
}
_VERDICT_NORMALIZATION: dict[str, ValidationVerdict] = {
    "pass": "pass",
    "passed": "pass",
    "approve": "pass",
    "approved": "pass",
    "revise": "revise",
    "retry": "revise",
    "needs_revision": "revise",
    "needs_revisions": "revise",
    "blocked": "blocked",
    "fail": "blocked",
    "failed": "blocked",
}


def _normalize_text_enum(
    value: object, mapping: Mapping[str, str], default: str
) -> str:
    if not isinstance(value, str):
        return default

    key = value.strip().lower().replace("-", "_").replace(" ", "_")
    return mapping.get(key, default)


def _normalize_score(value: object) -> object:
    if isinstance(value, bool):
        return value

    score: float
    if isinstance(value, (int, float)):
        score = float(value)
    elif isinstance(value, str):
        normalized = value.strip().rstrip("%")
        try:
            score = float(normalized)
        except ValueError:
            return value
    else:
        return value

    if 1.0 < score <= 100.0:
        return score / 100.0
    return score


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: ValidationSeverity = "major"
    category: ValidationIssueCategory = "layout"
    title: str
    observed: str
    expected: str
    fix_instructions: str

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, value: object) -> ValidationSeverity:
        return cast(
            ValidationSeverity,
            _normalize_text_enum(value, _SEVERITY_NORMALIZATION, "major"),
        )

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: object) -> ValidationIssueCategory:
        return cast(
            ValidationIssueCategory,
            _normalize_text_enum(value, _CATEGORY_NORMALIZATION, "layout"),
        )


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: ValidationVerdict = "revise"
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0)
    visual_fidelity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    behavior_fidelity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    animation_fidelity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    editability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)
    patch_instructions: list[str] = Field(default_factory=list)

    @field_validator("verdict", mode="before")
    @classmethod
    def normalize_verdict(cls, value: object) -> ValidationVerdict:
        return cast(
            ValidationVerdict,
            _normalize_text_enum(value, _VERDICT_NORMALIZATION, "revise"),
        )

    @field_validator(
        "overall_score",
        "visual_fidelity_score",
        "behavior_fidelity_score",
        "animation_fidelity_score",
        "editability_score",
        mode="before",
    )
    @classmethod
    def normalize_scores(cls, value: object) -> object:
        return _normalize_score(value)


class LoopIterationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iteration: int
    validation: ValidationReport


class LoopResumeState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: RequirementsSpec | None = None
    latest_validation: ValidationReport | None = None
    best_file_state: dict[str, str] | None = None
    completed_iterations: int = 0
    stop_reason: str | None = None


class LoopRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    requirements: RequirementsSpec
    iterations: list[LoopIterationRecord] = Field(default_factory=list)
    stop_reason: Literal["pass", "max_iterations", "blocked"]
    saved_code_path: str | None = None
    saved_run_dir: str | None = None
