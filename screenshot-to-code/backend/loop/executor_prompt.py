from typing import cast

from openai.types.chat import ChatCompletionMessageParam

from loop.contracts import ReferenceBundle, RequirementsSpec, ValidationReport
from loop.frontend_developer_policy import build_frontend_developer_policy
from loop.prompts import (
    compact_requirements_for_prompt,
    compact_validation_report_for_prompt,
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
) -> str:
    selected_stack = build_selected_stack_policy(reference_bundle.stack)
    image_policy = build_user_image_policy(image_generation_enabled)
    template_policy = build_template_output_policy()
    judgment_policy = build_judgment_policy()
    frontend_policy = build_frontend_developer_policy()
    requirements_json = compact_requirements_for_prompt(requirements).model_dump_json(
        indent=2
    )
    return f"""
Generate code that matches the provided reference media as closely as possible.

{selected_stack}

{image_policy}
{template_policy}
{judgment_policy}
{frontend_policy}

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
- Build a working implementation, not a static approximation.
- Match the visible UI and behavior from the reference.
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
) -> str:
    judgment_policy = build_judgment_policy()
    frontend_policy = build_frontend_developer_policy()
    requirements_json = compact_requirements_for_prompt(requirements).model_dump_json(
        indent=2
    )
    validation_json = compact_validation_report_for_prompt(
        validation_report
    ).model_dump_json(indent=2)
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

Revise the existing file instead of starting over unless the validator feedback makes a localized edit impossible.
Preserve the template-friendly structure while closing the identified fidelity gaps.
Honor the `hard_constraints`, preserve the `design_tokens`, and use `section_requirements` plus `execution_plan` to keep the implementation coherent while revising it.
Treat `preserve_requirements` and validator `strengths` as preserve-as-is guidance unless a higher-priority patch instruction explicitly requires a change.
Prefer targeted edits to the existing file over broad rewrites so existing working code is not lost.
Treat `animation_requirements` as mandatory when the reference includes motion.
For video references, do not stop at fixing the opening sequence if later-state components or scenes are still missing from the implementation.
""".strip()


def build_executor_update_prompt(
    reference_bundle: ReferenceBundle,
    requirements: RequirementsSpec,
    iteration: int,
) -> str:
    judgment_policy = build_judgment_policy()
    frontend_policy = build_frontend_developer_policy()
    requirements_json = compact_requirements_for_prompt(requirements).model_dump_json(
        indent=2
    )
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

Edit the existing file in place. Preserve and improve the template-friendly structure while bringing the implementation closer to the target result.
Follow the `execution_plan`, satisfy `hard_constraints`, and use `section_requirements` as the authoritative page blueprint.
Treat `preserve_requirements` as keep-intact guidance and avoid rewriting sections that already satisfy the reference.
Prefer narrow edits to the current file over broad rewrites so existing working code is not lost.
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
