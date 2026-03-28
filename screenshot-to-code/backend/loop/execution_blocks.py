from dataclasses import dataclass, replace

from loop.contracts import ReferenceBundle, RequirementsSpec, ValidationReport


MAX_SECTIONS_PER_EXECUTION_BLOCK = 3
EXECUTOR_TEXT_BUDGET_CHARS = 120_000
EXECUTOR_MEDIA_BUDGET_CHARS = 500_000


@dataclass(frozen=True)
class ExecutionBlock:
    title: str
    objective: str
    section_names: list[str]
    preserve_section_names: list[str]
    include_media: bool


def plan_execution_blocks(
    *,
    reference_bundle: ReferenceBundle,
    requirements: RequirementsSpec,
    file_state: dict[str, str] | None,
    validation_report: ValidationReport | None,
) -> list[ExecutionBlock]:
    current_html = file_state.get("content", "") if file_state else ""
    if current_html.strip():
        return [_single_update_block(requirements, validation_report)]

    section_names = [
        section.name.strip()
        for section in requirements.section_requirements
        if section.name.strip()
    ]
    if not section_names:
        return [
            ExecutionBlock(
                title="Global shell and theme",
                objective="Establish the centralized theme, page shell, and foundational structure before detailing sections.",
                section_names=[],
                preserve_section_names=[],
                include_media=True,
            )
        ]

    if not _should_chunk_initial_execution(reference_bundle, requirements, section_names):
        return [
            ExecutionBlock(
                title="Full page build",
                objective="Build the full page in one pass while honoring the centralized design system and all section blueprints.",
                section_names=section_names,
                preserve_section_names=[],
                include_media=True,
            )
        ]

    blocks: list[ExecutionBlock] = []
    for index, start in enumerate(range(0, len(section_names), MAX_SECTIONS_PER_EXECUTION_BLOCK)):
        chunk = section_names[start : start + MAX_SECTIONS_PER_EXECUTION_BLOCK]
        preserve_section_names = section_names[:start]
        title = (
            "Global shell, theme, and opening sections"
            if index == 0
            else f"Section group {index + 1}"
        )
        objective = _build_block_objective(
            chunk,
            preserve_section_names=preserve_section_names,
            is_first=index == 0,
        )
        blocks.append(
            ExecutionBlock(
                title=title,
                objective=objective,
                section_names=chunk,
                preserve_section_names=preserve_section_names,
                include_media=index == 0,
            )
        )

    if requirements.behavior_requirements or requirements.animation_requirements:
        blocks.append(
            ExecutionBlock(
                title="Global polish and interactions",
                objective=(
                    "Tighten cross-section polish, interactive states, and motion details without rewriting the completed sections."
                ),
                section_names=[],
                preserve_section_names=section_names,
                include_media=False,
            )
        )

    return blocks


def split_execution_block(block: ExecutionBlock) -> list[ExecutionBlock]:
    if len(block.section_names) <= 1:
        return []

    midpoint = max(1, len(block.section_names) // 2)
    left_sections = block.section_names[:midpoint]
    right_sections = block.section_names[midpoint:]
    left_block = replace(
        block,
        title=f"{block.title} (part 1)",
        section_names=left_sections,
        objective=_build_block_objective(
            left_sections,
            preserve_section_names=block.preserve_section_names,
            is_first=not block.preserve_section_names,
        ),
    )
    right_preserve = [*block.preserve_section_names, *left_sections]
    right_block = replace(
        block,
        title=f"{block.title} (part 2)",
        section_names=right_sections,
        preserve_section_names=right_preserve,
        include_media=False,
        objective=_build_block_objective(
            right_sections,
            preserve_section_names=right_preserve,
            is_first=False,
        ),
    )
    return [left_block, right_block]


def strip_execution_block_media(block: ExecutionBlock) -> ExecutionBlock:
    return replace(block, include_media=False)


def summarize_execution_blocks(blocks: list[ExecutionBlock]) -> str:
    return " | ".join(
        f"{index}. {block.title}: "
        + (
            ", ".join(block.section_names)
            if block.section_names
            else "page-wide polish"
        )
        for index, block in enumerate(blocks, start=1)
    )


def _single_update_block(
    requirements: RequirementsSpec,
    validation_report: ValidationReport | None,
) -> ExecutionBlock:
    revision_objective = (
        "Apply the validator patch plan while preserving the strongest existing sections and the centralized design system."
        if validation_report is not None
        else "Update the current implementation to align with the requirements without losing the existing working structure."
    )
    referenced_sections = _sections_referenced_by_validation(
        requirements, validation_report
    )
    return ExecutionBlock(
        title="Validator-guided update" if validation_report is not None else "Scoped update",
        objective=revision_objective,
        section_names=referenced_sections,
        preserve_section_names=[],
        include_media=False,
    )


def _should_chunk_initial_execution(
    reference_bundle: ReferenceBundle,
    requirements: RequirementsSpec,
    section_names: list[str],
) -> bool:
    if len(section_names) > MAX_SECTIONS_PER_EXECUTION_BLOCK:
        return True

    text_size = len(requirements.model_dump_json()) + len(reference_bundle.user_text)
    media_size = sum(len(image) for image in reference_bundle.images[:2])
    if reference_bundle.input_mode != "video":
        media_size += sum(len(video) for video in reference_bundle.videos[:1])
    if reference_bundle.live_reference is not None:
        for render in reference_bundle.live_reference.renders:
            label = render.label.lower()
            if "full-page" in label or "full page" in label:
                continue
            media_size += len(render.data_url)
            break

    return (
        text_size > EXECUTOR_TEXT_BUDGET_CHARS
        or media_size > EXECUTOR_MEDIA_BUDGET_CHARS
    )


def _build_block_objective(
    section_names: list[str],
    *,
    preserve_section_names: list[str],
    is_first: bool,
) -> str:
    scope = ", ".join(section_names) if section_names else "page-wide polish"
    if is_first:
        return (
            f"Build the shell, centralized theme, and the scoped sections for this block: {scope}. "
            "Leave room for later blocks instead of overfitting unrelated sections."
        )
    preserve_clause = ""
    if preserve_section_names:
        preserve_clause = (
            " Preserve the previously completed sections: "
            + ", ".join(preserve_section_names)
            + "."
        )
    return (
        f"Implement or refine only the scoped sections for this block: {scope}."
        + preserve_clause
    )


def _sections_referenced_by_validation(
    requirements: RequirementsSpec,
    validation_report: ValidationReport | None,
) -> list[str]:
    if validation_report is None:
        return []
    section_names = [
        section.name for section in requirements.section_requirements if section.name.strip()
    ]
    prioritized_sections = [
        result.name
        for result in validation_report.section_results
        if result.status in {"missing", "partial"} and result.name in section_names
    ]
    if prioritized_sections:
        return prioritized_sections
    matched: list[str] = []
    haystacks = [
        *[issue.title for issue in validation_report.issues],
        *[issue.observed for issue in validation_report.issues],
        *validation_report.patch_instructions,
    ]
    for section_name in section_names:
        section_key = section_name.lower()
        if any(section_key in haystack.lower() for haystack in haystacks):
            matched.append(section_name)
    return matched
