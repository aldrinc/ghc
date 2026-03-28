from typing import cast

from openai.types.chat import ChatCompletionMessageParam

from loop.contracts import ReferenceBundle, RequirementsSpec, ValidationReport
from loop.execution_blocks import ExecutionBlock
from loop.frontend_developer_policy import build_frontend_developer_policy
from loop.prompts import (
    build_live_design_system_rules,
    compact_requirements_for_prompt,
    compact_validation_report_for_prompt,
    summarize_design_system_preflight_for_prompt,
    summarize_live_reference_for_prompt,
)
from prompts import system_prompt
from prompts.message_builder import Prompt, build_history_message
from prompts.policies import (
    build_judgment_policy,
    build_selected_stack_policy,
    build_template_output_policy,
    build_user_image_policy,
)
from prompts.prompt_types import Stack, UserTurnInput


def build_executor_create_prompt(
    reference_bundle: ReferenceBundle,
    requirements: RequirementsSpec,
    *,
    image_generation_enabled: bool,
    execution_block: ExecutionBlock | None = None,
) -> str:
    selected_stack = build_selected_stack_policy(reference_bundle.stack)
    image_policy = build_user_image_policy(image_generation_enabled)
    template_policy = build_template_output_policy()
    judgment_policy = build_judgment_policy()
    frontend_policy = build_frontend_developer_policy()
    scoped_requirements = _scoped_requirements_for_execution_block(
        requirements, execution_block
    )
    requirements_json = scoped_requirements.model_dump_json(indent=2)
    live_reference_block = ""
    if reference_bundle.live_reference is not None:
        live_reference_block = f"""

Live browser inspection context:
<live_reference>
{summarize_live_reference_for_prompt(reference_bundle.live_reference)}
</live_reference>"""
    live_design_system_rules = build_live_design_system_rules(
        reference_bundle, requirements
    )
    design_system_block = ""
    if reference_bundle.design_system_preflight is not None:
        design_system_block = f"""

Required design-system preflight:
        <design_system_preflight>
{summarize_design_system_preflight_for_prompt(reference_bundle.design_system_preflight)}
</design_system_preflight>"""
    execution_block_instructions = _execution_block_instructions(execution_block)
    return f"""
Generate code that matches the provided reference media as closely as possible.

{selected_stack}

{image_policy}
{template_policy}
{judgment_policy}
{frontend_policy}
{design_system_block}
{live_reference_block}
{live_design_system_rules}
{execution_block_instructions}

Use this validated requirements spec as the main source of truth:
<requirements_spec>
{requirements_json}
</requirements_spec>

Additional user request:
{reference_bundle.user_text or '(none provided)'}

Execution requirements:

- Satisfy `hard_constraints` before lower-priority refinements.
- Preserve anything covered by `preserve_requirements` unless the reference media or a higher-priority hard constraint requires changing it.
- Use `section_requirements` and `execution_plan` as the implementation blueprint.
- For every section in `section_requirements`, render one stable root element with the exact `data-section-id` value from that requirement's `section_id`. Do not omit these markers, do not rename them, and do not reuse the same marker for multiple sections.
- Build a working implementation, not a static approximation.
- Match the visible UI and behavior from the reference.
- When live browser inspection context is provided, honor the extracted design-system details for typography, colors, spacing, radii, shadows, and component styling unless a stronger screenshot/video cue clearly overrides them.
- When live browser inspection context is provided, you must implement and use the extracted design-system tokens in centralized theme variables or equivalent shared styling primitives.
- Do not replace extracted font-family names with substitutes. Keep the exact extracted names in the code and add fallbacks only after them.
- Treat `animation_requirements` as first-class requirements for video and interactive references.
- For video references, build the full end state described by the requirements, not just the opening sequence. Any component, section, or state called out in later checkpoints or acceptance criteria must exist in the implementation.
- Keep the result template-friendly and easy to edit later.
- Prefer clear structure over cleverness.
""".strip()


def build_executor_revision_prompt(
    reference_bundle: ReferenceBundle,
    requirements: RequirementsSpec,
    validation_report: ValidationReport,
    iteration: int,
    execution_block: ExecutionBlock | None = None,
) -> str:
    judgment_policy = build_judgment_policy()
    frontend_policy = build_frontend_developer_policy()
    scoped_requirements = _scoped_requirements_for_execution_block(
        requirements, execution_block
    )
    requirements_json = scoped_requirements.model_dump_json(indent=2)
    validation_json = compact_validation_report_for_prompt(
        validation_report
    ).model_dump_json(indent=2)
    live_reference_block = ""
    if reference_bundle.live_reference is not None:
        live_reference_block = f"""

Live browser inspection context:
<live_reference>
{summarize_live_reference_for_prompt(reference_bundle.live_reference)}
</live_reference>"""
    live_design_system_rules = build_live_design_system_rules(
        reference_bundle, requirements
    )
    design_system_block = ""
    if reference_bundle.design_system_preflight is not None:
        design_system_block = f"""

Required design-system preflight:
        <design_system_preflight>
{summarize_design_system_preflight_for_prompt(reference_bundle.design_system_preflight)}
</design_system_preflight>"""
    execution_block_instructions = _execution_block_instructions(execution_block)
    return f"""
Revise the current implementation using the validator feedback below.

This is iteration {iteration}.

Use the original requirements spec as the source of truth:
<requirements_spec>
{requirements_json}
</requirements_spec>

Use the validator report as the concrete patch plan:
<validation_report>
{validation_json}
</validation_report>

Original user request:
{reference_bundle.user_text or '(none provided)'}

{judgment_policy}
{frontend_policy}
{design_system_block}
{live_reference_block}
{live_design_system_rules}
{execution_block_instructions}

Revise the existing file instead of starting over unless the validator feedback makes a localized edit impossible.
Preserve the template-friendly structure while closing the identified fidelity gaps.
Honor the `hard_constraints`, preserve the `design_tokens`, and use `section_requirements` plus `execution_plan` to keep the implementation coherent while revising it.
Preserve existing `data-section-id` markers on section root elements and add any missing ones so every required section keeps a stable DOM identity across iterations.
Treat `preserve_requirements` and validator `strengths` as preserve-as-is guidance unless a higher-priority patch instruction explicitly requires a change.
Prefer targeted edits to the existing file over broad rewrites so existing working code is not lost.
When live browser inspection context is present, treat it as a high-confidence styling reference during revisions.
Do not remove or substitute away the extracted design-system tokens during revisions.
Treat `animation_requirements` as mandatory when the reference includes motion.
For video references, do not stop at fixing the opening sequence if later-state components or scenes are still missing from the implementation.
""".strip()


def build_executor_update_prompt(
    reference_bundle: ReferenceBundle,
    requirements: RequirementsSpec,
    iteration: int,
    execution_block: ExecutionBlock | None = None,
) -> str:
    judgment_policy = build_judgment_policy()
    frontend_policy = build_frontend_developer_policy()
    scoped_requirements = _scoped_requirements_for_execution_block(
        requirements, execution_block
    )
    requirements_json = scoped_requirements.model_dump_json(indent=2)
    live_reference_block = ""
    if reference_bundle.live_reference is not None:
        live_reference_block = f"""

Live browser inspection context:
<live_reference>
{summarize_live_reference_for_prompt(reference_bundle.live_reference)}
</live_reference>"""
    live_design_system_rules = build_live_design_system_rules(
        reference_bundle, requirements
    )
    design_system_block = ""
    if reference_bundle.design_system_preflight is not None:
        design_system_block = f"""

Required design-system preflight:
        <design_system_preflight>
{summarize_design_system_preflight_for_prompt(reference_bundle.design_system_preflight)}
</design_system_preflight>"""
    execution_block_instructions = _execution_block_instructions(execution_block)
    return f"""
Update the current implementation so it aligns with the requirements spec and the reference media.

This is iteration {iteration}.

Use the requirements spec as the source of truth:
<requirements_spec>
{requirements_json}
</requirements_spec>

Original user request:
{reference_bundle.user_text or '(none provided)'}

{judgment_policy}
{frontend_policy}
{design_system_block}
{live_reference_block}
{live_design_system_rules}
{execution_block_instructions}

Edit the existing file in place. Preserve and improve the template-friendly structure while bringing the implementation closer to the target result.
Follow the `execution_plan`, satisfy `hard_constraints`, and use `section_requirements` as the authoritative page blueprint.
Ensure every required section root keeps the exact `data-section-id` from `section_requirements.section_id`, and add any missing markers before doing deeper polish.
Treat `preserve_requirements` as keep-intact guidance and avoid rewriting sections that already satisfy the reference.
Prefer narrow edits to the current file over broad rewrites so existing working code is not lost.
When live browser inspection context is present, treat it as a high-confidence styling reference during updates.
Do not remove or substitute away the extracted design-system tokens during updates.
Treat `animation_requirements` as mandatory when the reference includes motion.
For video references, ensure the implementation covers all required end-state components and later checkpoints from the requirements, not just the initial hero or first animation beats.
""".strip()


def build_executor_update_messages(
    stack: Stack,
    prompt: UserTurnInput,
    file_state: dict[str, str],
    image_generation_enabled: bool,
) -> Prompt:
    path = file_state.get("path", "index.html")
    request_text = prompt.get("text", "").strip() or "Apply the requested update."
    selected_stack = build_selected_stack_policy(stack)
    image_policy = build_user_image_policy(image_generation_enabled)
    template_policy = build_template_output_policy()
    frontend_policy = build_frontend_developer_policy()
    bootstrap_text = f"""{selected_stack}

{image_policy}
{template_policy}
{frontend_policy}

You are editing an existing file.

<current_file path="{path}">
{file_state["content"]}
</current_file>

<change_request>
{request_text}
</change_request>"""
    return [
        cast(
            ChatCompletionMessageParam,
            {
                "role": "system",
                "content": system_prompt.SYSTEM_PROMPT,
            },
        ),
        build_history_message(
            {
                "role": "user",
                "text": bootstrap_text,
                "images": prompt.get("images", []),
                "videos": prompt.get("videos", []),
            }
        ),
    ]


def _execution_block_instructions(
    execution_block: ExecutionBlock | None,
) -> str:
    if execution_block is None:
        return ""

    lines = [
        "",
        "Current execution block:",
        f"- Title: {execution_block.title}",
        f"- Objective: {execution_block.objective}",
    ]
    if execution_block.section_names:
        lines.append(
            "- Scoped sections for this block: " + ", ".join(execution_block.section_names)
        )
    else:
        lines.append(
            "- Scoped sections for this block: page-wide polish and cross-section cleanup."
        )
    if execution_block.preserve_section_names:
        lines.append(
            "- Preserve these already-completed sections unless a higher-priority fix requires touching them: "
            + ", ".join(execution_block.preserve_section_names)
        )
    if execution_block.include_media:
        lines.append(
            "- Lightweight reference media is attached for this block; focus only on the scoped sections while keeping the global design system consistent."
        )
    else:
        lines.append(
            "- No extra reference media is attached for this block. Rely on the scoped requirements, the design-system preflight, and the current HTML."
        )
    return "\n".join(lines)


def _scoped_requirements_for_execution_block(
    requirements: RequirementsSpec,
    execution_block: ExecutionBlock | None,
) -> RequirementsSpec:
    scoped = compact_requirements_for_prompt(requirements)
    if execution_block is None:
        return scoped

    preserve_requirements = list(scoped.preserve_requirements)
    if execution_block.preserve_section_names:
        preserve_requirements.append(
            "Preserve already-completed sections unless a higher-priority fix requires changes: "
            + ", ".join(execution_block.preserve_section_names)
        )

    if not execution_block.section_names:
        return scoped.model_copy(update={"preserve_requirements": preserve_requirements})

    section_name_set = set(execution_block.section_names)
    scoped_sections = [
        section
        for section in scoped.section_requirements
        if section.name in section_name_set
    ]
    execution_plan = _filter_execution_plan_for_scope(
        scoped.execution_plan,
        section_name_set,
        keep_initial_global_steps=not execution_block.preserve_section_names,
    )

    return scoped.model_copy(
        update={
            "section_requirements": scoped_sections,
            "preserve_requirements": preserve_requirements,
            "execution_plan": execution_plan,
            "layout_requirements": _filter_requirement_list_for_scope(
                scoped.layout_requirements,
                section_name_set,
            ),
            "styling_requirements": _filter_requirement_list_for_scope(
                scoped.styling_requirements,
                section_name_set,
            ),
            "copy_requirements": _filter_requirement_list_for_scope(
                scoped.copy_requirements,
                section_name_set,
                include_global_context=False,
            ),
            "asset_requirements": _filter_requirement_list_for_scope(
                scoped.asset_requirements,
                section_name_set,
                include_global_context=False,
            ),
            "behavior_requirements": _filter_requirement_list_for_scope(
                scoped.behavior_requirements,
                section_name_set,
            ),
            "animation_requirements": _filter_requirement_list_for_scope(
                scoped.animation_requirements,
                section_name_set,
            ),
            "structure_guidance": _filter_requirement_list_for_scope(
                scoped.structure_guidance,
                section_name_set,
            ),
            "known_unknowns": _filter_requirement_list_for_scope(
                scoped.known_unknowns,
                section_name_set,
                include_global_context=False,
            ),
            "acceptance_criteria": _filter_requirement_list_for_scope(
                scoped.acceptance_criteria,
                section_name_set,
            ),
        }
    )


def _filter_requirement_list_for_scope(
    items: list[str],
    section_name_set: set[str],
    *,
    include_global_context: bool = True,
    max_items: int = 6,
) -> list[str]:
    if not section_name_set:
        return items[:max_items]

    matched_items = [
        item for item in items if _item_matches_section_scope(item, section_name_set)
    ]
    global_items = []
    if include_global_context:
        global_items = [
            item for item in items if _item_matches_global_scope(item)
        ]

    combined = _dedupe_preserving_order([*matched_items, *global_items])
    return combined[:max_items]


def _filter_execution_plan_for_scope(
    execution_plan: list[str],
    section_name_set: set[str],
    *,
    keep_initial_global_steps: bool,
) -> list[str]:
    if not section_name_set:
        return execution_plan[:6]

    matched_steps = [
        step for step in execution_plan if _item_matches_section_scope(step, section_name_set)
    ]
    global_steps = [step for step in execution_plan if _item_matches_global_scope(step)]
    leading_steps = execution_plan[:2] if keep_initial_global_steps else []
    combined = _dedupe_preserving_order([*leading_steps, *matched_steps, *global_steps])
    return combined[:6]


def _item_matches_section_scope(item: str, section_name_set: set[str]) -> bool:
    lowered_item = item.lower()
    return any(section_name.lower() in lowered_item for section_name in section_name_set)


def _item_matches_global_scope(item: str) -> bool:
    lowered_item = item.lower()
    return any(
        keyword in lowered_item
        for keyword in (
            "theme",
            "token",
            "design system",
            "responsive",
            "shell",
            "layout",
            "grid",
            "typography",
            "color",
            "spacing",
            "radius",
            "motion",
            "animation",
            "accessibility",
        )
    )


def _dedupe_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped
