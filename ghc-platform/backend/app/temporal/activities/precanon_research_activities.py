from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Tuple
import hashlib

from temporalio import activity

from app.db.base import SessionLocal
from app.db.repositories.onboarding_payloads import OnboardingPayloadsRepository
from app.llm import LLMClient, LLMGenerationParams
from app.google_clients import upload_text_file, create_folder
from app.temporal.precanon import (
    CONTENT_BLOCK_TAG,
    STEP4_PROMPT_BLOCK_TAG,
    SUMMARY_BLOCK_TAG,
    STEP_DEFINITIONS,
    truncate_bounded,
    render_prompt_file,
)


TAG_PATTERN = re.compile(r"<(?P<tag>[A-Z0-9_]+)>(?P<content>.*?)</(?P=tag)>", re.DOTALL)


def _now_iso() -> str:
    return datetime.utcnow().replace(tzinfo=None).isoformat() + "Z"


def _parse_tagged_blocks(text: str) -> Dict[str, str]:
    blocks: Dict[str, str] = {}
    for match in TAG_PATTERN.finditer(text):
        tag = match.group("tag")
        content = match.group("content").strip()
        blocks[tag] = content
    return blocks


@activity.defn
def fetch_onboarding_payload_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    onboarding_payload_id = params["onboarding_payload_id"]
    repo = OnboardingPayloadsRepository(SessionLocal())
    payload = repo.get(org_id=org_id, payload_id=onboarding_payload_id)
    return payload.data if payload and payload.data else {}


@activity.defn
def get_ads_context_stub_activity(params: Dict[str, Any]) -> Dict[str, str]:
    return {"ads_context": "Ad transparency scraping is not implemented; this is a placeholder context."}


def _render_prompt(step_key: str, variables: Mapping[str, str]) -> Tuple[str, str]:
    if step_key not in STEP_DEFINITIONS:
        raise ValueError(f"Unknown step_key: {step_key}")
    definition = STEP_DEFINITIONS[step_key]
    return render_prompt_file(definition.prompt_filename, variables)


@activity.defn
def generate_research_step_artifact_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates a research artifact for a given step.
    Expects params:
      - step_key, variables (for prompt placeholders)
      - model (optional), summary_max_chars, handoff_max_chars (optional)
      - llm_params: optional dict overriding model/temperature/max_tokens/reasoning/web_search
    Returns:
      - doc_id, doc_url, summary, prompt_sha256, created_at_iso
      - handoff (dict) when applicable (e.g., STEP4_PROMPT from step 3)
    """
    step_key: str = params["step_key"]
    variables: Mapping[str, str] = params.get("variables", {})
    requested_model: str = params.get("model") or "stub-model"
    summary_max_chars: int = params.get("summary_max_chars") or 1200
    handoff_max_chars: Optional[int] = params.get("handoff_max_chars")
    parent_folder_id: Optional[str] = params.get("parent_folder_id") or os.getenv(
        "RESEARCH_DRIVE_PARENT_FOLDER_ID"
    ) or os.getenv("PARENT_FOLDER_ID")
    title: str = params.get("title") or f"Research Step {step_key}"
    workflow_id: Optional[str] = params.get("workflow_id")
    allow_drive_stub: bool = params.get("allow_drive_stub", False)
    idea_folder_name: Optional[str] = params.get("idea_folder_name")
    idea_folder_id: Optional[str] = params.get("idea_folder_id")
    idea_folder_url: Optional[str] = params.get("idea_folder_url")
    if not idea_folder_name:
        # Fallback to business context as idea name
        idea_folder_name = (
            variables.get("BUSINESS_CONTEXT")
            or variables.get("BUSINESS_CONTEXT_JSON")
            or variables.get("IDEA")
            or variables.get("IDEA_NAME")
            or None
        )
    if not idea_folder_name:
        idea_folder_name = "idea"

    def _sanitize_name(name: str) -> str:
        cleaned = re.sub(r"[\\/:*?\"<>|]+", " ", name).strip()
        return cleaned[:250] if cleaned else "idea"

    override_prompt: Optional[str] = params.get("prompt_override")
    if override_prompt:
        # Always add output-format guardrails for override prompts to enforce tags.
        enforced_prompt = (
            override_prompt.strip()
            + "\n\nReturn only:\n"
            f"<{SUMMARY_BLOCK_TAG}>Bounded summary of strongest findings.</{SUMMARY_BLOCK_TAG}>\n"
            f"<{CONTENT_BLOCK_TAG}>\n"
            "...full content per instructions...\n"
            f"</{CONTENT_BLOCK_TAG}>"
        )
        template_rendered = enforced_prompt
        prompt_sha256 = hashlib.sha256(enforced_prompt.encode("utf-8")).hexdigest()
    else:
        if step_key == "04":
            raise ValueError(
                "Step 04 requires a prompt_override (STEP4_PROMPT from step 3) and should not use a static file."
            )
        template_rendered, _ = _render_prompt(step_key, variables)
        # Hard guardrails to force tagged output blocks even if the base prompt forgets to include them.
        template_rendered = (
            template_rendered
            + "\n\nReturn only:\n"
            f"<{SUMMARY_BLOCK_TAG}>Bounded summary of strongest findings.</{SUMMARY_BLOCK_TAG}>\n"
            f"<{CONTENT_BLOCK_TAG}>\n"
            "...full content per instructions...\n"
            f"</{CONTENT_BLOCK_TAG}>"
        )
        if step_key == "03":
            template_rendered += (
                "\n"
                f"<{STEP4_PROMPT_BLOCK_TAG}>Deep research prompt to drive step 04.</{STEP4_PROMPT_BLOCK_TAG}>"
            )
        prompt_sha256 = hashlib.sha256(template_rendered.encode("utf-8")).hexdigest()

    llm_params_payload = params.get("llm_params") or {}
    llm_params = LLMGenerationParams(
        model=llm_params_payload.get("model") or requested_model,
        max_tokens=llm_params_payload.get("max_tokens"),
        temperature=llm_params_payload.get("temperature", 0.2),
        use_reasoning=bool(llm_params_payload.get("use_reasoning", False)),
        use_web_search=bool(llm_params_payload.get("use_web_search", False)),
    )
    llm = LLMClient(default_model=llm_params.model)
    llm_output = llm.generate_text(template_rendered, llm_params)

    blocks = _parse_tagged_blocks(llm_output)
    summary = truncate_bounded(blocks.get(SUMMARY_BLOCK_TAG, ""), summary_max_chars)
    content = blocks.get(CONTENT_BLOCK_TAG, "")
    if not summary:
        raise ValueError(f"Missing <{SUMMARY_BLOCK_TAG}> block for step {step_key}")
    if not content and step_key != "03":
        # Fall back to raw output to avoid failing the workflow when the model drops the tag.
        content = llm_output

    handoff: Dict[str, Any] = {}
    if STEP4_PROMPT_BLOCK_TAG in blocks:
        step4_prompt_text = blocks[STEP4_PROMPT_BLOCK_TAG]
        handoff["step4_prompt"] = (
            truncate_bounded(step4_prompt_text, handoff_max_chars) if handoff_max_chars else step4_prompt_text
        )
        # For step 3, treat the STEP4_PROMPT as the primary content to persist.
        if step_key == "03":
            content = step4_prompt_text
    if step_key == "03" and STEP4_PROMPT_BLOCK_TAG not in blocks:
        # Fall back to the raw output as the deep research prompt rather than failing the workflow.
        handoff["step4_prompt"] = truncate_bounded(llm_output, handoff_max_chars) if handoff_max_chars else llm_output
        content = llm_output

    file_name_parts = [title]
    if workflow_id:
        file_name_parts.append(f"workflow-{workflow_id}")
    file_name_parts.append(f"step-{step_key}")
    file_name = " - ".join(file_name_parts)

    try:
        effective_parent = parent_folder_id
        if parent_folder_id:
            # Create or reuse the idea folder; if the caller passed one, keep it.
            if not idea_folder_id:
                folder = create_folder(_sanitize_name(idea_folder_name), parent_folder_id)
                idea_folder_id = folder.get("id") or idea_folder_id
                idea_folder_url = folder.get("webViewLink") or folder.get("webContentLink") or idea_folder_url
            effective_parent = idea_folder_id or parent_folder_id

        drive_file = upload_text_file(name=file_name, content=content, parent_folder_id=effective_parent)
        doc_id = drive_file.get("id", "")
        doc_url = drive_file.get("webViewLink") or drive_file.get("webContentLink") or ""
        if not doc_id or not doc_url:
            raise RuntimeError("Failed to persist research artifact to Drive")
    except Exception:
        if not allow_drive_stub:
            raise
        doc_id = f"drive-stub-{uuid.uuid4()}"
        doc_url = f"drive-stub://{doc_id}"

    return {
        "doc_id": doc_id,
        "doc_url": doc_url,
        "summary": summary,
        "content": content,
        "prompt_sha256": prompt_sha256,
        "created_at_iso": _now_iso(),
        "handoff": handoff or None,
        "idea_folder_id": idea_folder_id,
        "idea_folder_url": idea_folder_url,
    }
