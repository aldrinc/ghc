from llm import Llm
from loop.contracts import (
    ReferenceBundle,
    RenderArtifact,
    RequirementsSpec,
    ValidationReport,
)
from loop.gemini import (
    GeminiPart,
    data_url_to_part,
    generate_structured_output,
    text_part,
)
from loop.validator_prompt import (
    VALIDATOR_SYSTEM_INSTRUCTION,
    build_validator_prompt,
)


def _apply_score_cap(current: float, cap: float) -> float:
    return min(current, cap)


def _tighten_validation_report(
    report: ValidationReport, *, reference_bundle: ReferenceBundle
) -> ValidationReport:
    critical_issues = [issue for issue in report.issues if issue.severity == "critical"]
    major_issues = [issue for issue in report.issues if issue.severity == "major"]
    minor_issues = [issue for issue in report.issues if issue.severity == "minor"]

    visual_cap = 1.0
    behavior_cap = 1.0
    animation_cap = 1.0
    editability_cap = 1.0
    overall_cap = 1.0

    if critical_issues:
        overall_cap = min(overall_cap, 0.55)
        for issue in critical_issues:
            if issue.category in {"layout", "styling", "copy", "imagery"}:
                visual_cap = min(visual_cap, 0.6)
            if issue.category == "behavior":
                behavior_cap = min(behavior_cap, 0.55)
            if issue.category == "animation":
                animation_cap = min(animation_cap, 0.5)
            if issue.category == "structure":
                editability_cap = min(editability_cap, 0.65)

    if major_issues:
        major_cap = 0.78 if len(major_issues) == 1 else 0.7
        overall_cap = min(overall_cap, major_cap)
        for issue in major_issues:
            if issue.category in {"layout", "styling", "copy", "imagery"}:
                visual_cap = min(visual_cap, 0.8 if len(major_issues) == 1 else 0.72)
            if issue.category == "behavior":
                behavior_cap = min(
                    behavior_cap, 0.78 if len(major_issues) == 1 else 0.7
                )
                overall_cap = min(overall_cap, 0.74)
            if issue.category == "animation":
                animation_cap = min(
                    animation_cap, 0.75 if len(major_issues) == 1 else 0.68
                )
                overall_cap = min(overall_cap, 0.72)
            if issue.category == "structure":
                editability_cap = min(
                    editability_cap, 0.8 if len(major_issues) == 1 else 0.72
                )

    if len(minor_issues) >= 3:
        overall_cap = min(overall_cap, 0.9)
    if len(report.issues) >= 5:
        overall_cap = min(overall_cap, 0.85)

    if reference_bundle.input_mode == "video":
        if any(issue.category == "animation" for issue in report.issues):
            animation_cap = min(animation_cap, 0.78)
            overall_cap = min(overall_cap, 0.75)
        if any(issue.category == "behavior" for issue in report.issues):
            behavior_cap = min(behavior_cap, 0.8)
            overall_cap = min(overall_cap, 0.78)

    visual_score = _apply_score_cap(report.visual_fidelity_score, visual_cap)
    behavior_score = _apply_score_cap(report.behavior_fidelity_score, behavior_cap)
    animation_score = _apply_score_cap(report.animation_fidelity_score, animation_cap)
    editability_score = _apply_score_cap(report.editability_score, editability_cap)

    dimension_ceiling = min(
        visual_score,
        behavior_score,
        editability_score,
        animation_score if reference_bundle.input_mode == "video" else 1.0,
    )
    overall_score = min(report.overall_score, overall_cap, dimension_ceiling)

    verdict = report.verdict
    if verdict == "pass" and (critical_issues or major_issues):
        verdict = "revise"

    return report.model_copy(
        update={
            "verdict": verdict,
            "overall_score": overall_score,
            "visual_fidelity_score": visual_score,
            "behavior_fidelity_score": behavior_score,
            "animation_fidelity_score": animation_score,
            "editability_score": editability_score,
        }
    )


class LoopValidator:
    def __init__(self, gemini_api_key: str):
        self._gemini_api_key = gemini_api_key
        self._model_name = "gemini-3.1-pro-preview"

    async def validate(
        self,
        *,
        reference_bundle: ReferenceBundle,
        requirements: RequirementsSpec,
        render_artifact: RenderArtifact,
        current_html: str,
        iteration: int,
    ) -> ValidationReport:
        parts: list[GeminiPart] = [
            text_part(
                build_validator_prompt(
                    reference_bundle, requirements, current_html, iteration
                )
            )
        ]

        for index, image in enumerate(reference_bundle.images, start=1):
            parts.append(text_part(f"Source image {index}:"))
            parts.append(data_url_to_part(image))

        for index, video in enumerate(reference_bundle.videos, start=1):
            parts.append(text_part(f"Source video {index}:"))
            parts.append(data_url_to_part(video))

        parts.append(text_part("Rendered candidate viewport screenshot:"))
        parts.append(data_url_to_part(render_artifact.viewport_screenshot_data_url))

        if render_artifact.full_page_screenshot_data_url:
            parts.append(text_part("Rendered candidate full-page screenshot:"))
            parts.append(data_url_to_part(render_artifact.full_page_screenshot_data_url))

        if render_artifact.settled_viewport_screenshot_data_url:
            parts.append(
                text_part(
                    "Rendered candidate settled viewport screenshot (after animations have had time to finish):"
                )
            )
            parts.append(
                data_url_to_part(render_artifact.settled_viewport_screenshot_data_url)
            )

        if render_artifact.settled_full_page_screenshot_data_url:
            parts.append(
                text_part(
                    "Rendered candidate settled full-page screenshot (after animations have had time to finish):"
                )
            )
            parts.append(
                data_url_to_part(render_artifact.settled_full_page_screenshot_data_url)
            )

        for index, frame in enumerate(render_artifact.timeline_frames, start=1):
            parts.append(
                text_part(
                    "Rendered candidate timeline checkpoint "
                    f"{index} ({frame.label}, approx t+{frame.elapsed_ms}ms):"
                )
            )
            parts.append(data_url_to_part(frame.viewport_screenshot_data_url))

        report = await generate_structured_output(
            api_key=self._gemini_api_key,
            model_name=self._model_name,
            thinking_level="high",
            system_instruction=VALIDATOR_SYSTEM_INSTRUCTION,
            parts=parts,
            response_schema=ValidationReport,
        )
        return _tighten_validation_report(report, reference_bundle=reference_bundle)

    @property
    def model(self) -> Llm:
        return Llm.GEMINI_3_1_PRO_PREVIEW_HIGH
