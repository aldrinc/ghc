import re
from typing import Dict

from app.temporal.precanon import (
    CONTENT_BLOCK_TAG,
    STEP4_PROMPT_BLOCK_TAG,
    SUMMARY_BLOCK_TAG,
    truncate_bounded,
)

from .types import ParsedStepOutput


TAG_PATTERN = re.compile(r"<(?P<tag>[A-Z0-9_]+)>(?P<content>.*?)</(?P=tag)>", re.DOTALL)


def _parse_tagged_blocks(text: str) -> Dict[str, str]:
    blocks: Dict[str, str] = {}
    for match in TAG_PATTERN.finditer(text):
        tag = match.group("tag")
        content = match.group("content").strip()
        blocks[tag] = content
    return blocks


def parse_step_output(
    *,
    step_key: str,
    raw_output: str,
    summary_max_chars: int,
    handoff_max_chars: int | None,
) -> ParsedStepOutput:
    blocks = _parse_tagged_blocks(raw_output)
    summary = truncate_bounded(blocks.get(SUMMARY_BLOCK_TAG, ""), summary_max_chars)
    content = blocks.get(CONTENT_BLOCK_TAG, "")
    if not summary:
        raise ValueError(f"Missing <{SUMMARY_BLOCK_TAG}> block for step {step_key}")
    if not content and step_key != "03":
        content = raw_output

    handoff = None
    if STEP4_PROMPT_BLOCK_TAG in blocks:
        step4_prompt_text = blocks[STEP4_PROMPT_BLOCK_TAG]
        step4_prompt = (
            truncate_bounded(step4_prompt_text, handoff_max_chars) if handoff_max_chars else step4_prompt_text
        )
        handoff = {"step4_prompt": step4_prompt}
        if step_key == "03":
            content = step4_prompt_text
    elif step_key == "03":
        fallback_prompt = truncate_bounded(raw_output, handoff_max_chars) if handoff_max_chars else raw_output
        content = raw_output
        handoff = {"step4_prompt": fallback_prompt}

    return ParsedStepOutput(summary=summary, content=content, handoff=handoff)
