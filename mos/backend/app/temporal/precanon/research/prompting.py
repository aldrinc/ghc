import hashlib
from typing import Mapping

from app.temporal.precanon import (
    CONTENT_BLOCK_TAG,
    STEP4_PROMPT_BLOCK_TAG,
    STEP_DEFINITIONS,
    SUMMARY_BLOCK_TAG,
    render_prompt_file,
)

from .types import PromptBuildRequest, PromptBuildResult


def _append_guardrails(
    base_prompt: str,
    *,
    summary_block_tag: str,
    content_block_tag: str,
    include_step4_prompt: bool,
) -> str:
    prompt = (
        base_prompt.rstrip()
        + "\n\nReturn only:\n"
        f"<{summary_block_tag}>Bounded summary of strongest findings.</{summary_block_tag}>\n"
        f"<{content_block_tag}>\n"
        "...full content per instructions...\n"
        f"</{content_block_tag}>"
    )
    if include_step4_prompt:
        prompt += (
            "\n"
            f"<{STEP4_PROMPT_BLOCK_TAG}>Deep research prompt to drive step 04.</{STEP4_PROMPT_BLOCK_TAG}>"
        )
    return prompt


def build_prompt(request: PromptBuildRequest) -> PromptBuildResult:
    if request.step_key not in STEP_DEFINITIONS and not request.prompt_override:
        raise ValueError(f"Unknown step_key: {request.step_key}")

    include_step4_prompt = request.step_key == "03"
    summary_tag = request.summary_block_tag or SUMMARY_BLOCK_TAG
    content_tag = request.content_block_tag or CONTENT_BLOCK_TAG

    if request.prompt_override:
        prompt_body = _append_guardrails(
            request.prompt_override,
            summary_block_tag=summary_tag,
            content_block_tag=content_tag,
            include_step4_prompt=include_step4_prompt,
        )
        prompt_sha256 = hashlib.sha256(prompt_body.encode("utf-8")).hexdigest()
        return PromptBuildResult(prompt_text=prompt_body, prompt_sha256=prompt_sha256)

    definition = STEP_DEFINITIONS[request.step_key]
    template_rendered, _ = render_prompt_file(definition.prompt_filename, request.variables)
    prompt_body = _append_guardrails(
        template_rendered,
        summary_block_tag=summary_tag,
        content_block_tag=content_tag,
        include_step4_prompt=include_step4_prompt,
    )
    prompt_sha256 = hashlib.sha256(prompt_body.encode("utf-8")).hexdigest()
    return PromptBuildResult(prompt_text=prompt_body, prompt_sha256=prompt_sha256)
