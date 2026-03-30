import re

from llm import Llm
from loop.contracts import (
    ReferenceBundle,
    RenderArtifact,
    RequirementsSpec,
    SectionRequirement,
    SectionValidationResult,
    ValidationIssue,
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
    is_functionality_first_focus,
)


MAX_VALIDATOR_SOURCE_IMAGES = 2
MAX_VALIDATOR_DELTA_SOURCE_IMAGES = 1
MAX_VALIDATOR_LIVE_RENDERS = 1
MAX_VALIDATOR_TIMELINE_FRAMES = 4
MAX_VALIDATOR_DELTA_TIMELINE_FRAMES = 3
FUNCTIONALITY_FIRST_PASS_BEHAVIOR_SCORE = 0.95
FUNCTIONALITY_FIRST_PASS_ANIMATION_SCORE = 0.95
FUNCTIONALITY_FIRST_PASS_EDITABILITY_SCORE = 0.9


def _apply_score_cap(current: float, cap: float) -> float:
    return min(current, cap)


def _apply_score_floor(current: float, floor: float) -> float:
    return max(current, floor)


def _append_labeled_media(
    parts: list[GeminiPart],
    *,
    label: str,
    data_url: str,
) -> None:
    parts.append(text_part(label))
    parts.append(data_url_to_part(data_url))


def _is_delta_validation(
    *,
    iteration: int,
    prior_validation: ValidationReport | None,
) -> bool:
    return prior_validation is not None


def _is_full_page_live_render(label: str) -> bool:
    normalized = label.lower()
    return "full-page" in normalized or "full page" in normalized


def _select_live_renders(reference_bundle: ReferenceBundle) -> list[tuple[str, str]]:
    if reference_bundle.live_reference is None:
        return []

    renders = reference_bundle.live_reference.renders
    if not renders:
        return []

    preferred = [render for render in renders if not _is_full_page_live_render(render.label)]
    selected = preferred[:MAX_VALIDATOR_LIVE_RENDERS] or renders[:MAX_VALIDATOR_LIVE_RENDERS]
    return [
        (
            f"Live browser render {index} ({render.label}) from {reference_bundle.live_reference.url}:",
            render.data_url,
        )
        for index, render in enumerate(selected, start=1)
    ]


def _needs_pagewide_context(prior_validation: ValidationReport | None) -> bool:
    if prior_validation is None:
        return True
    if not prior_validation.issues and not prior_validation.patch_instructions:
        return True

    if any(
        issue.category in {"layout", "structure"}
        for issue in prior_validation.issues
    ):
        return True

    pagewide_keywords = {
        "layout",
        "page",
        "viewport",
        "header",
        "footer",
        "section",
        "stack",
        "spacing",
        "overflow",
    }
    return any(
        keyword in instruction.lower()
        for instruction in prior_validation.patch_instructions
        for keyword in pagewide_keywords
    )


def _needs_settled_renders(
    reference_bundle: ReferenceBundle,
    requirements: RequirementsSpec,
) -> bool:
    return bool(
        reference_bundle.input_mode == "video"
        or requirements.behavior_requirements
        or requirements.animation_requirements
        or requirements.interaction_checkpoints
    )


def _sample_timeline_frames(render_artifact: RenderArtifact) -> list[tuple[str, str]]:
    return _sample_timeline_frames_with_limit(
        render_artifact,
        max_frames=MAX_VALIDATOR_TIMELINE_FRAMES,
    )


def _sample_timeline_frames_with_limit(
    render_artifact: RenderArtifact,
    *,
    max_frames: int,
) -> list[tuple[str, str]]:
    frames = render_artifact.timeline_frames
    if not frames:
        return []
    if len(frames) <= max_frames:
        selected_frames = frames
    else:
        last_index = len(frames) - 1
        candidate_indices = [
            round(index * last_index / max(max_frames - 1, 1))
            for index in range(max_frames)
        ]
        selected_frames = []
        seen: set[int] = set()
        for index in candidate_indices:
            if index in seen:
                continue
            seen.add(index)
            selected_frames.append(frames[index])
    return [
        (
            "Rendered candidate timeline checkpoint "
            f"{index} ({frame.label}, approx t+{frame.elapsed_ms}ms):",
            frame.viewport_screenshot_data_url,
        )
        for index, frame in enumerate(selected_frames, start=1)
    ]


def _reference_media_parts(
    reference_bundle: ReferenceBundle,
    *,
    iteration: int,
    prior_validation: ValidationReport | None,
) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    if reference_bundle.input_mode == "image":
        image_limit = (
            MAX_VALIDATOR_DELTA_SOURCE_IMAGES
            if _is_delta_validation(iteration=iteration, prior_validation=prior_validation)
            else MAX_VALIDATOR_SOURCE_IMAGES
        )
        for index, image in enumerate(
            reference_bundle.images[:image_limit],
            start=1,
        ):
            parts.append((f"Source image {index}:", image))
    elif reference_bundle.input_mode == "video":
        for index, video in enumerate(reference_bundle.videos[:1], start=1):
            parts.append((f"Source video {index}:", video))

    parts.extend(_select_live_renders(reference_bundle))
    return parts


def _candidate_media_parts(
    reference_bundle: ReferenceBundle,
    requirements: RequirementsSpec,
    render_artifact: RenderArtifact,
    *,
    iteration: int,
    prior_validation: ValidationReport | None,
) -> list[tuple[str, str]]:
    parts = [
        (
            "Rendered candidate viewport screenshot:",
            render_artifact.viewport_screenshot_data_url,
        )
    ]

    include_settled = _needs_settled_renders(reference_bundle, requirements)
    include_pagewide = _needs_pagewide_context(prior_validation)
    is_delta = _is_delta_validation(
        iteration=iteration,
        prior_validation=prior_validation,
    )
    if reference_bundle.input_mode == "image":
        if render_artifact.full_page_screenshot_data_url and (include_pagewide or not is_delta):
            parts.append(
                (
                    "Rendered candidate full-page screenshot:",
                    render_artifact.full_page_screenshot_data_url,
                )
            )
        if include_settled and render_artifact.settled_viewport_screenshot_data_url:
            parts.append(
                (
                    "Rendered candidate settled viewport screenshot (after animations have had time to finish):",
                    render_artifact.settled_viewport_screenshot_data_url,
                )
            )
        if (
            include_settled
            and render_artifact.settled_full_page_screenshot_data_url
            and (include_pagewide or not is_delta)
        ):
            parts.append(
                (
                    "Rendered candidate settled full-page screenshot (after animations have had time to finish):",
                    render_artifact.settled_full_page_screenshot_data_url,
                )
            )
        return parts

    if render_artifact.settled_viewport_screenshot_data_url:
        parts.append(
            (
                "Rendered candidate settled viewport screenshot (after animations have had time to finish):",
                render_artifact.settled_viewport_screenshot_data_url,
            )
        )
    if (
        not render_artifact.timeline_frames
        and render_artifact.full_page_screenshot_data_url
        and (include_pagewide or not is_delta)
    ):
        parts.append(
            (
                "Rendered candidate full-page screenshot:",
                render_artifact.full_page_screenshot_data_url,
            )
        )
    if (
        include_settled
        and not render_artifact.timeline_frames
        and render_artifact.settled_full_page_screenshot_data_url
        and (include_pagewide or not is_delta)
    ):
        parts.append(
            (
                "Rendered candidate settled full-page screenshot (after animations have had time to finish):",
                render_artifact.settled_full_page_screenshot_data_url,
            )
        )
    timeline_limit = (
        MAX_VALIDATOR_DELTA_TIMELINE_FRAMES if is_delta else MAX_VALIDATOR_TIMELINE_FRAMES
    )
    parts.extend(
        _sample_timeline_frames_with_limit(
            render_artifact,
            max_frames=timeline_limit,
        )
    )
    return parts


def _extract_design_token_names(requirements: RequirementsSpec) -> list[str]:
    token_values = [
        *requirements.design_tokens.colors,
        *requirements.design_tokens.typography,
        *requirements.design_tokens.spacing,
        *requirements.design_tokens.radii,
        *requirements.design_tokens.shadows,
        *requirements.design_tokens.motion,
    ]
    names: list[str] = []
    seen: set[str] = set()
    for token in token_values:
        match = re.match(r"\s*(--[a-zA-Z0-9_-]+)\s*:", token)
        if match is None:
            continue
        name = match.group(1)
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _extract_live_font_names(reference_bundle: ReferenceBundle) -> list[str]:
    font_names: list[str] = []
    seen: set[str] = set()
    preflight_typography = (
        reference_bundle.design_system_preflight.typography
        if reference_bundle.design_system_preflight is not None
        else []
    )
    live_typography = (
        reference_bundle.live_reference.design_system.typography
        if reference_bundle.live_reference is not None
        else []
    )
    for typography_entry in [*preflight_typography, *live_typography]:
        match = re.search(r"font\s+(.+?);", typography_entry)
        if match is None:
            continue
        for part in match.group(1).split(","):
            normalized = part.strip().strip('"').strip("'")
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in {"sans-serif", "serif", "monospace", "arial"}:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            font_names.append(normalized)
    return font_names


def _normalize_section_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return normalized.strip("-")


def _extract_declared_section_ids(current_html: str) -> set[str]:
    if not current_html:
        return set()

    patterns = (
        r'data-section-id\s*=\s*"([^"]+)"',
        r"data-section-id\s*=\s*'([^']+)'",
        r'data-section-id\s*=\s*\{\s*"([^"]+)"\s*\}',
        r"data-section-id\s*=\s*\{\s*'([^']+)'\s*\}",
    )
    declared_ids: set[str] = set()
    for pattern in patterns:
        for match in re.findall(pattern, current_html, flags=re.IGNORECASE):
            normalized = _normalize_section_id(match)
            if normalized:
                declared_ids.add(normalized)
    return declared_ids


def _is_section_coverage_issue(issue: ValidationIssue) -> bool:
    if issue.category != "structure":
        return False

    haystack = " ".join(
        [
            issue.title,
            issue.observed,
            issue.expected,
            issue.fix_instructions,
        ]
    ).lower()
    coverage_markers = (
        "required sections are missing",
        "required sections are only partially implemented",
        "required section coverage is incomplete",
        "section coverage exists but is still incomplete",
        "missing sections:",
        "partially implemented sections",
    )
    return any(marker in haystack for marker in coverage_markers)


def _is_section_coverage_instruction(instruction: str) -> bool:
    normalized = instruction.strip().lower()
    return normalized.startswith("insert the missing `") or normalized.startswith(
        "finish the partially implemented `"
    )


def _apply_score_floor(current: float, floor: float) -> float:
    return max(current, floor)


def _required_sections(
    requirements: RequirementsSpec,
) -> list[tuple[int, SectionRequirement]]:
    return [
        (index, section)
        for index, section in enumerate(requirements.section_requirements)
        if section.name.strip()
    ]


def _section_location_hint(
    requirements: RequirementsSpec,
    section_index: int,
) -> str:
    required_sections = _required_sections(requirements)
    ordered_names = [section.name.strip() for _, section in required_sections]
    if not ordered_names:
        return "in the main page flow"

    current_name = requirements.section_requirements[section_index].name.strip()
    try:
        ordered_index = ordered_names.index(current_name)
    except ValueError:
        return "in the main page flow"

    previous_name = ordered_names[ordered_index - 1] if ordered_index > 0 else ""
    next_name = (
        ordered_names[ordered_index + 1]
        if ordered_index + 1 < len(ordered_names)
        else ""
    )
    if previous_name and next_name:
        return (
            f"between the existing `{previous_name}` section and the existing `{next_name}` section"
        )
    if previous_name:
        return f"after the existing `{previous_name}` section"
    if next_name:
        return f"before the existing `{next_name}` section"
    return "as the primary section in the main page flow"


def _section_requirements_scope_summary(section: SectionRequirement) -> str:
    scope_bits: list[str] = []
    if section.must_include:
        scope_bits.append("required elements: " + ", ".join(section.must_include[:3]))
    if section.copy_items:
        scope_bits.append("required copy: " + ", ".join(section.copy_items[:2]))
    if section.behaviors:
        scope_bits.append("required behaviors: " + ", ".join(section.behaviors[:2]))
    if not scope_bits:
        return "the matching `section_requirements` entry"
    return "; ".join(scope_bits)


def _missing_section_fix_instruction(
    requirements: RequirementsSpec,
    *,
    section_index: int,
    section: SectionRequirement,
) -> str:
    location_hint = _section_location_hint(requirements, section_index)
    return (
        f"Insert the missing `{section.name}` section {location_hint}. Build it from "
        f"{_section_requirements_scope_summary(section)} while preserving the surrounding sections and shared theme."
    )


def _partial_section_fix_instruction(
    section: SectionRequirement,
) -> str:
    return (
        f"Finish the partially implemented `{section.name}` section in place. Keep any working container and styling that already match, "
        f"but add the missing details from {_section_requirements_scope_summary(section)}."
    )


def _prepend_unique_instructions(
    existing: list[str],
    new_instructions: list[str],
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for instruction in [*new_instructions, *existing]:
        if instruction in seen:
            continue
        seen.add(instruction)
        result.append(instruction)
    return result


def _enforce_section_coverage(
    report: ValidationReport,
    *,
    requirements: RequirementsSpec,
    reference_bundle: ReferenceBundle,
    current_html: str = "",
) -> ValidationReport:
    required_sections = _required_sections(requirements)
    if not required_sections:
        return report

    declared_section_ids = _extract_declared_section_ids(current_html)
    required_lookup = {
        section.section_id: (index, section)
        for index, section in required_sections
    }
    matched_results: dict[str, SectionValidationResult] = {}
    extra_results: list[SectionValidationResult] = []
    recovered_section_ids: set[str] = set()
    for result in report.section_results:
        section_id = result.section_id
        if section_id in required_lookup and section_id not in matched_results:
            canonical_section = required_lookup[section_id][1]
            adjusted_quality_score = result.quality_score
            if result.status == "missing":
                adjusted_quality_score = 0.0
            elif result.status == "partial":
                adjusted_quality_score = min(adjusted_quality_score, 0.79)

            if result.status == "missing" and section_id in declared_section_ids:
                recovered_section_ids.add(section_id)
                matched_results[section_id] = result.model_copy(
                    update={
                        "name": canonical_section.name,
                        "section_id": canonical_section.section_id,
                        "status": "present",
                        "quality_score": max(result.quality_score, 0.8),
                        "summary": (
                            "Exact `data-section-id` markup in the current HTML confirms this required section root already exists, so missing-section coverage was overridden deterministically."
                        ),
                        "fix_instructions": "",
                    }
                )
            else:
                matched_results[section_id] = result.model_copy(
                    update={
                        "name": canonical_section.name,
                        "section_id": canonical_section.section_id,
                        "quality_score": adjusted_quality_score,
                    }
                )
            continue
        extra_results.append(result)

    ordered_results: list[SectionValidationResult] = []
    missing_sections: list[tuple[int, SectionRequirement]] = []
    partial_sections: list[tuple[int, SectionRequirement]] = []
    for index, section in required_sections:
        result = matched_results.get(section.section_id)
        if result is None:
            if section.section_id in declared_section_ids:
                recovered_section_ids.add(section.section_id)
                result = SectionValidationResult(
                    name=section.name,
                    section_id=section.section_id,
                    status="present",
                    quality_score=0.8,
                    summary=(
                        "Exact `data-section-id` markup in the current HTML confirms this required section root already exists, so coverage was recovered deterministically."
                    ),
                )
            else:
                result = SectionValidationResult(
                    name=section.name,
                    section_id=section.section_id,
                    status="missing",
                    quality_score=0.0,
                    summary=(
                        "This required section was not assessed by the validator, so coverage is treated as missing until the section is implemented and revalidated."
                    ),
                    fix_instructions=_missing_section_fix_instruction(
                        requirements,
                        section_index=index,
                        section=section,
                    ),
                )
        if result.status == "missing":
            missing_sections.append((index, section))
        elif result.status == "partial":
            partial_sections.append((index, section))
            if not result.fix_instructions:
                result = result.model_copy(
                    update={
                        "fix_instructions": _partial_section_fix_instruction(section),
                    }
                )
        ordered_results.append(result)

    if (
        not missing_sections
        and not partial_sections
        and ordered_results == report.section_results
        and not recovered_section_ids
    ):
        return report

    issues = [issue for issue in report.issues if not _is_section_coverage_issue(issue)]
    patch_instructions = [
        instruction
        for instruction in report.patch_instructions
        if not _is_section_coverage_instruction(instruction)
    ]
    summary = report.summary
    verdict = report.verdict
    overall_cap = report.overall_score
    visual_cap = report.visual_fidelity_score
    behavior_cap = report.behavior_fidelity_score
    animation_cap = report.animation_fidelity_score
    editability_cap = report.editability_score
    summary_additions: list[str] = []
    coverage_patch_instructions: list[str] = []
    recovered_section_names = [
        required_lookup[section_id][1].name
        for section_id in sorted(recovered_section_ids)
        if section_id in required_lookup
    ]
    if recovered_section_names:
        summary_additions.append(
            "Deterministic DOM coverage checks confirmed these required section roots already exist via exact `data-section-id` markers: "
            + ", ".join(recovered_section_names)
            + "."
        )

    if missing_sections:
        missing_names = [section.name for _, section in missing_sections]
        issues.append(
            ValidationIssue(
                severity="critical",
                category="structure",
                title="Required sections are missing from the implementation",
                observed=(
                    "The current candidate does not yet contain every required top-to-bottom page section. Missing sections: "
                    + ", ".join(missing_names)
                    + "."
                ),
                expected=(
                    "Every section listed in `section_requirements` should exist in the implementation before the loop spends more time polishing already-good sections."
                ),
                fix_instructions=(
                    "Implement the missing sections in the required page order before refining local styling. Use the matching `section_requirements` entries as the source of truth and preserve the surrounding completed sections."
                ),
            )
        )
        coverage_patch_instructions.extend(
            _missing_section_fix_instruction(
                requirements,
                section_index=index,
                section=section,
            )
            for index, section in missing_sections
        )
        verdict = "revise"
        overall_cap = min(overall_cap, 0.55)
        visual_cap = min(visual_cap, 0.72)
        behavior_cap = min(behavior_cap, 0.72)
        animation_cap = min(animation_cap, 0.72)
        editability_cap = min(editability_cap, 0.65)
        summary_additions.append(
            "Required section coverage is incomplete, so the loop should restore the missing sections before deeper polish."
        )

    if partial_sections:
        partial_names = [section.name for _, section in partial_sections]
        issues.append(
            ValidationIssue(
                severity="major",
                category="structure",
                title="Required sections are only partially implemented",
                observed=(
                    "Some required sections exist only as partial matches and still miss meaningful structure, copy, assets, or behaviors: "
                    + ", ".join(partial_names)
                    + "."
                ),
                expected=(
                    "Each required section should be fully present and structurally faithful before higher-fidelity polish work begins."
                ),
                fix_instructions=(
                    "Complete the partially implemented sections in place, preserving any accurate shell that already exists while filling the missing requirements from `section_requirements`."
                ),
            )
        )
        coverage_patch_instructions.extend(
            _partial_section_fix_instruction(section) for _, section in partial_sections
        )
        verdict = "revise"
        overall_cap = min(overall_cap, 0.78)
        visual_cap = min(visual_cap, 0.82)
        behavior_cap = min(behavior_cap, 0.82)
        animation_cap = min(animation_cap, 0.82)
        editability_cap = min(editability_cap, 0.8)
        summary_additions.append(
            "Section coverage exists but is still incomplete in places, so the next round should finish those sections before local polish."
        )

    if reference_bundle.input_mode != "video":
        animation_cap = report.animation_fidelity_score

    overall_score = _apply_score_cap(report.overall_score, overall_cap)
    visual_score = _apply_score_cap(report.visual_fidelity_score, visual_cap)
    behavior_score = _apply_score_cap(report.behavior_fidelity_score, behavior_cap)
    animation_score = _apply_score_cap(report.animation_fidelity_score, animation_cap)
    editability_score = _apply_score_cap(report.editability_score, editability_cap)

    low_score_pattern = report.overall_score <= 0.56 or (
        report.visual_fidelity_score <= 0.72
        and report.behavior_fidelity_score <= 0.72
    )
    has_noncoverage_critical = any(issue.severity == "critical" for issue in issues)
    has_noncoverage_major = any(issue.severity == "major" for issue in issues)
    should_restore_false_positive_cap = (
        bool(recovered_section_ids)
        and not missing_sections
        and not partial_sections
        and low_score_pattern
        and not has_noncoverage_critical
        and not has_noncoverage_major
    )
    if should_restore_false_positive_cap:
        overall_score = _apply_score_floor(overall_score, 0.84)
        visual_score = _apply_score_floor(visual_score, 0.86)
        behavior_score = _apply_score_floor(behavior_score, 0.86)
        editability_score = _apply_score_floor(editability_score, 0.88)
        if reference_bundle.input_mode == "video":
            animation_score = _apply_score_floor(animation_score, 0.86)
        summary_additions.append(
            "The prior low section-coverage score cap was removed because the missing-section finding was contradicted by exact DOM markers, so remaining scoring reflects only the non-coverage issues still visible."
        )
        if not issues:
            verdict = "pass"

    updated_summary = " ".join(
        part for part in [summary.strip(), *summary_additions] if part
    )

    return report.model_copy(
        update={
            "verdict": verdict,
            "overall_score": overall_score,
            "visual_fidelity_score": visual_score,
            "behavior_fidelity_score": behavior_score,
            "animation_fidelity_score": animation_score,
            "editability_score": editability_score,
            "summary": updated_summary,
            "section_results": [*ordered_results, *extra_results],
            "issues": issues,
            "patch_instructions": _prepend_unique_instructions(
                patch_instructions,
                coverage_patch_instructions,
            ),
        }
    )


def _has_css_custom_property_declaration(current_html: str, token_name: str) -> bool:
    pattern = re.compile(rf"{re.escape(token_name)}\s*:")
    return pattern.search(current_html) is not None


def _enforce_design_system_usage(
    report: ValidationReport,
    *,
    reference_bundle: ReferenceBundle,
    requirements: RequirementsSpec,
    current_html: str,
) -> ValidationReport:
    if (
        reference_bundle.live_reference is None
        and reference_bundle.design_system_preflight is None
    ):
        return report

    issues = list(report.issues)
    patch_instructions = list(report.patch_instructions)
    summary = report.summary
    verdict = report.verdict
    overall_cap = 1.0
    visual_cap = 1.0
    editability_cap = 1.0

    token_names = _extract_design_token_names(requirements)
    required_decl_tokens = [
        name
        for name in token_names
        if name in {"--font-body", "--font-heading", "--color-text-primary", "--color-bg-main"}
        or name.startswith("--color-")
    ]
    missing_decl_tokens = [
        name
        for name in required_decl_tokens[:8]
        if not _has_css_custom_property_declaration(current_html, name)
    ]
    if missing_decl_tokens:
        issues.append(
            ValidationIssue(
                severity="critical",
                category="structure",
                title="Missing centralized live design-system token declarations",
                observed=(
                    "The current HTML does not declare required extracted theme tokens such as "
                    + ", ".join(missing_decl_tokens[:4])
                    + "."
                ),
                expected=(
                    "The current HTML should declare centralized CSS custom properties for the extracted live design system in a stable shared location such as :root or an equivalent theme block."
                ),
                fix_instructions=(
                    "Add the missing extracted theme tokens to a centralized theme block in the current HTML (for example in <style> :root { ... }). Include exact typography and color token names from the requirements spec, then keep the rest of the structure intact."
                ),
            )
        )
        patch_instructions.append(
            "In the main <style> theme block, declare the missing extracted CSS custom properties from `design_tokens` (including the exact font and color tokens) before any component-specific styling."
        )
        verdict = "revise"
        overall_cap = min(overall_cap, 0.55)
        visual_cap = min(visual_cap, 0.6)
        editability_cap = min(editability_cap, 0.65)

    required_usage_tokens = [
        token_name
        for token_name in token_names
        if token_name in {"--font-body", "--font-heading", "--color-text-primary"}
    ]
    required_usages = [f"var({token_name})" for token_name in required_usage_tokens]
    missing_usages = [usage for usage in required_usages if usage not in current_html]
    if missing_usages:
        issues.append(
            ValidationIssue(
                severity="major",
                category="styling",
                title="Extracted design-system tokens are not being applied",
                observed=(
                    "The current HTML does not apply required extracted theme variables such as "
                    + ", ".join(missing_usages)
                    + "."
                ),
                expected=(
                    "Major text and surface styling should consume the centralized extracted theme tokens instead of bypassing them with unrelated hardcoded values."
                ),
                fix_instructions=(
                    "Update the main typography and color styling in the current HTML so body, headings, and primary surfaces use the extracted theme variables via var(...), while preserving the existing layout and behavior."
                ),
            )
        )
        patch_instructions.append(
            "Update body, heading, and primary surface rules to use the extracted CSS variables via "
            + ", ".join(missing_usages)
            + " and the required color tokens instead of bypassing the centralized theme."
        )
        verdict = "revise"
        overall_cap = min(overall_cap, 0.72)
        visual_cap = min(visual_cap, 0.75)
        editability_cap = min(editability_cap, 0.78)

    live_font_names = _extract_live_font_names(reference_bundle)
    missing_font_names = [
        font_name for font_name in live_font_names[:4] if font_name not in current_html
    ]
    if missing_font_names:
        issues.append(
            ValidationIssue(
                severity="critical",
                category="styling",
                title="Exact extracted font-family names are missing",
                observed=(
                    "The current HTML substitutes away extracted live font-family names such as "
                    + ", ".join(missing_font_names)
                    + "."
                ),
                expected=(
                    "The exact font-family names extracted from the live reference should appear in the code, with any fallback fonts listed after them rather than replacing them."
                ),
                fix_instructions=(
                    "In the centralized typography tokens and the body/heading rules, restore the exact extracted font-family names from the live design system, then keep any fallback fonts after those exact names."
                ),
            )
        )
        patch_instructions.append(
            "Replace substituted font-family declarations in the theme block with the exact extracted live font-family names, keeping any fallbacks after the extracted names."
        )
        verdict = "revise"
        overall_cap = min(overall_cap, 0.55)
        visual_cap = min(visual_cap, 0.6)
        editability_cap = min(editability_cap, 0.7)

    if issues == report.issues:
        return report

    if summary:
        summary = summary + " The implementation still fails mandatory live design-system enforcement checks."
    else:
        summary = "The implementation fails mandatory live design-system enforcement checks."

    return report.model_copy(
        update={
            "verdict": verdict,
            "overall_score": _apply_score_cap(report.overall_score, overall_cap),
            "visual_fidelity_score": _apply_score_cap(
                report.visual_fidelity_score, visual_cap
            ),
            "editability_score": _apply_score_cap(report.editability_score, editability_cap),
            "summary": summary,
            "issues": issues,
            "patch_instructions": patch_instructions,
        }
    )


def _tighten_validation_report(
    report: ValidationReport, *, reference_bundle: ReferenceBundle
) -> ValidationReport:
    functionality_first_focus = is_functionality_first_focus(reference_bundle)
    original_imagery_issues = [
        issue for issue in report.issues if issue.category == "imagery"
    ]
    effective_issues = [
        issue.model_copy(update={"severity": "minor"})
        if functionality_first_focus and issue.category == "imagery"
        else issue
        for issue in report.issues
    ]
    critical_issues = [
        issue
        for issue in effective_issues
        if issue.severity == "critical" and issue.category != "imagery"
    ]
    major_issues = [
        issue
        for issue in effective_issues
        if issue.severity == "major" and issue.category != "imagery"
    ]
    minor_issues = [
        issue
        for issue in effective_issues
        if issue.severity == "minor" and issue.category != "imagery"
    ]

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
    if len([issue for issue in effective_issues if issue.category != "imagery"]) >= 5:
        overall_cap = min(overall_cap, 0.85)

    if functionality_first_focus and original_imagery_issues:
        if any(issue.severity == "critical" for issue in original_imagery_issues):
            visual_cap = min(visual_cap, 0.6)
        elif any(issue.severity == "major" for issue in original_imagery_issues):
            visual_cap = min(
                visual_cap, 0.8 if len(original_imagery_issues) == 1 else 0.72
            )
        elif len(original_imagery_issues) >= 3:
            visual_cap = min(visual_cap, 0.9)

    if reference_bundle.input_mode == "video":
        if any(issue.category == "animation" for issue in effective_issues):
            animation_cap = min(animation_cap, 0.78)
            overall_cap = min(overall_cap, 0.75)
        if any(issue.category == "behavior" for issue in effective_issues):
            behavior_cap = min(behavior_cap, 0.8)
            overall_cap = min(overall_cap, 0.78)

    visual_score = _apply_score_cap(report.visual_fidelity_score, visual_cap)
    behavior_score = _apply_score_cap(report.behavior_fidelity_score, behavior_cap)
    animation_score = _apply_score_cap(report.animation_fidelity_score, animation_cap)
    editability_score = _apply_score_cap(report.editability_score, editability_cap)

    if functionality_first_focus:
        dimension_ceiling = min(
            behavior_score,
            editability_score,
            animation_score if reference_bundle.input_mode == "video" else 1.0,
        )
    else:
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
    if functionality_first_focus:
        imagery_only_gaps = bool(original_imagery_issues) and not critical_issues and not major_issues
        if imagery_only_gaps:
            overall_focus_floor = min(
                behavior_score,
                editability_score,
                animation_score if reference_bundle.input_mode == "video" else 1.0,
            )
            overall_score = _apply_score_floor(overall_score, overall_focus_floor)
            behavior_ready = behavior_score >= FUNCTIONALITY_FIRST_PASS_BEHAVIOR_SCORE
            animation_ready = (
                True
                if reference_bundle.input_mode != "video"
                else animation_score >= FUNCTIONALITY_FIRST_PASS_ANIMATION_SCORE
            )
            editability_ready = (
                editability_score >= FUNCTIONALITY_FIRST_PASS_EDITABILITY_SCORE
            )
            if verdict == "revise" and behavior_ready and animation_ready and editability_ready:
                verdict = "pass"

    return report.model_copy(
        update={
            "verdict": verdict,
            "overall_score": overall_score,
            "visual_fidelity_score": visual_score,
            "behavior_fidelity_score": behavior_score,
            "animation_fidelity_score": animation_score,
            "editability_score": editability_score,
            "issues": effective_issues,
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
        prior_validation: ValidationReport | None = None,
    ) -> ValidationReport:
        parts: list[GeminiPart] = [
            text_part(
                build_validator_prompt(
                    reference_bundle,
                    requirements,
                    current_html,
                    iteration,
                    prior_validation,
                )
            )
        ]

        for label, data_url in _reference_media_parts(
            reference_bundle,
            iteration=iteration,
            prior_validation=prior_validation,
        ):
            _append_labeled_media(parts, label=label, data_url=data_url)

        for label, data_url in _candidate_media_parts(
            reference_bundle,
            requirements,
            render_artifact,
            iteration=iteration,
            prior_validation=prior_validation,
        ):
            _append_labeled_media(parts, label=label, data_url=data_url)

        report = await generate_structured_output(
            api_key=self._gemini_api_key,
            model_name=self._model_name,
            thinking_level="high",
            system_instruction=VALIDATOR_SYSTEM_INSTRUCTION,
            parts=parts,
            response_schema=ValidationReport,
        )
        coverage_enforced = _enforce_section_coverage(
            report,
            requirements=requirements,
            reference_bundle=reference_bundle,
            current_html=current_html,
        )
        tightened = _tighten_validation_report(
            coverage_enforced,
            reference_bundle=reference_bundle,
        )
        return _enforce_design_system_usage(
            tightened,
            reference_bundle=reference_bundle,
            requirements=requirements,
            current_html=current_html,
        )

    @property
    def model(self) -> Llm:
        return Llm.GEMINI_3_1_PRO_PREVIEW_HIGH
