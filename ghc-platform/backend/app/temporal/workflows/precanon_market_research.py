from __future__ import annotations

from datetime import timedelta
import json
import os
from typing import Any, Dict, List, Optional

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.precanon_research_activities import (
        fetch_onboarding_payload_activity,
        generate_research_step_artifact_activity,
        get_ads_context_stub_activity,
    )
    from app.temporal.precanon import (
        PreCanonMarketResearchInput,
        STEP_DEFINITIONS,
    )

DEFAULT_MODEL = os.getenv("LLM_DEFAULT_MODEL", "gpt-5.2-2025-12-11")
DEFAULT_REASONING_MODEL = os.getenv("PRECANON_REASONING_MODEL", DEFAULT_MODEL)
STEP_LLM_CONFIG: Dict[str, Dict[str, Any]] = {
    "01": {
        "model": os.getenv("PRECANON_STEP01_MODEL", DEFAULT_REASONING_MODEL),
        "use_reasoning": True,
        "use_web_search": True,
    },
    "03": {
        "model": os.getenv("PRECANON_STEP03_MODEL", DEFAULT_REASONING_MODEL),
        "use_reasoning": True,
    },
    "04": {
        "model": os.getenv("PRECANON_STEP04_MODEL", "o3-deep-research-2025-06-26"),
        "use_web_search": True,
        "max_tokens": int(os.getenv("PRECANON_STEP04_MAX_TOKENS", "64000")),
    },
    "06": {
        "model": os.getenv("PRECANON_STEP06_MODEL", DEFAULT_REASONING_MODEL),
        "use_reasoning": True,
    },
    "07": {
        "model": os.getenv("PRECANON_STEP07_MODEL", DEFAULT_REASONING_MODEL),
        "use_reasoning": True,
    },
    "08": {
        "model": os.getenv("PRECANON_STEP08_MODEL", DEFAULT_REASONING_MODEL),
        "use_reasoning": True,
    },
    "09": {
        "model": os.getenv("PRECANON_STEP09_MODEL", DEFAULT_REASONING_MODEL),
        "use_reasoning": True,
    },
}


def _safe_json_dump(data: Dict[str, Any]) -> str:
    try:
        return json.dumps(data, ensure_ascii=True)
    except Exception:
        return "{}"


def _build_base_variables(
    *,
    org_id: str,
    client_id: str,
    onboarding_payload_id: str,
    payload: Dict[str, Any],
    ads_context: Dict[str, Any],
) -> Dict[str, str]:
    # Derive a concise idea string for prompts/folder naming.
    idea = payload.get("idea")
    if not idea:
        offers = payload.get("offers") or []
        idea = offers[0] if offers else None
    if not idea:
        story = (payload.get("brand_story") or "").strip()
        idea = story.split("\n")[0][:200] if story else None
    business_context = idea or payload.get("business_type") or "Client business context"

    category_niche = payload.get("industry") or payload.get("category") or payload.get("niche") or "general"
    return {
        "ORG_ID": org_id,
        "CLIENT_ID": client_id,
        "ONBOARDING_PAYLOAD_ID": onboarding_payload_id,
        "BUSINESS_CONTEXT": str(business_context),
        "BUSINESS_CONTEXT_JSON": _safe_json_dump(payload),
        "CATEGORY_NICHE": str(category_niche),
        "ADS_CONTEXT": ads_context.get("ads_context") or "",
    }


def _llm_params_for_step(step_key: str) -> Dict[str, Any]:
    config = STEP_LLM_CONFIG.get(step_key, {})
    model = config.get("model") or DEFAULT_MODEL
    return {
        "model": model,
        "use_reasoning": bool(config.get("use_reasoning", False)),
        "use_web_search": bool(config.get("use_web_search", False)),
    }


@workflow.defn
class PreCanonMarketResearchWorkflow:
    @workflow.run
    async def run(self, input: PreCanonMarketResearchInput) -> Dict[str, Any]:
        payload = await workflow.execute_activity(
            fetch_onboarding_payload_activity,
            {"org_id": input.org_id, "onboarding_payload_id": input.onboarding_payload_id},
            start_to_close_timeout=timedelta(minutes=2),
            schedule_to_close_timeout=timedelta(minutes=10),
        )
        ads_context = await workflow.execute_activity(
            get_ads_context_stub_activity,
            {"org_id": input.org_id, "client_id": input.client_id},
            start_to_close_timeout=timedelta(minutes=1),
            schedule_to_close_timeout=timedelta(minutes=5),
        )

        base_vars = _build_base_variables(
            org_id=input.org_id,
            client_id=input.client_id,
            onboarding_payload_id=input.onboarding_payload_id,
            payload=payload or {},
            ads_context=ads_context or {},
        )

        idea_folder_id: Optional[str] = None
        idea_folder_url: Optional[str] = None
        artifacts: List[Any] = []
        step_summaries: Dict[str, str] = {}
        prompt_shas: Dict[str, str] = {}
        step_contents: Dict[str, str] = {}
        step4_prompt: Optional[str] = None

        async def _run_step(
            step_key: str,
            extra_vars: Dict[str, str],
            *,
            prompt_override: Optional[str] = None,
            summary_max_override: Optional[int] = None,
            handoff_max_override: Optional[int] = None,
        ):
            nonlocal idea_folder_id, idea_folder_url, step4_prompt
            definition = STEP_DEFINITIONS[step_key]
            vars_for_step = {**base_vars, **extra_vars}
            llm_params = _llm_params_for_step(step_key)
            params = {
                "step_key": step_key,
                "variables": vars_for_step,
                "model": llm_params["model"],
                "llm_params": llm_params,
                "summary_max_chars": summary_max_override or definition.summary_max_chars,
                "handoff_max_chars": handoff_max_override or definition.handoff_max_chars,
                "title": definition.title,
                "workflow_id": workflow.info().workflow_id,
                "idea_folder_id": idea_folder_id,
                "idea_folder_url": idea_folder_url,
            }
            if prompt_override:
                params["prompt_override"] = prompt_override

            timeouts = {
                "schedule_to_close_timeout": timedelta(minutes=30),
                "start_to_close_timeout": timedelta(minutes=10),
            }
            if step_key == "04":
                timeouts = {
                    "schedule_to_close_timeout": timedelta(minutes=90),
                    "start_to_close_timeout": timedelta(minutes=40),
                }

            result = await workflow.execute_activity(generate_research_step_artifact_activity, params, **timeouts)

            idea_folder_id = result.get("idea_folder_id") or idea_folder_id
            idea_folder_url = result.get("idea_folder_url") or idea_folder_url

            ref = {
                "step_key": step_key,
                "doc_url": result["doc_url"],
                "doc_id": result["doc_id"],
                "summary": result.get("summary", ""),
                "content": result.get("content", ""),
                "prompt_sha256": result.get("prompt_sha256", ""),
                "created_at_iso": result.get("created_at_iso", ""),
            }
            artifacts.append(ref)
            step_summaries[step_key] = ref["summary"]
            step_contents[step_key] = ref.get("content", "")
            prompt_shas[step_key] = ref["prompt_sha256"]

            handoff = result.get("handoff") or {}
            if handoff and "step4_prompt" in handoff:
                step4_prompt = handoff["step4_prompt"]

            return ref

        # Step 1
        step1_ref = await _run_step("01", {})

        # Step 3 (needs step1 summary and ads context)
        await _run_step(
            "03",
            {"STEP1_SUMMARY": step_summaries.get("01", ""), "ADS_CONTEXT": base_vars.get("ADS_CONTEXT", "")},
            handoff_max_override=STEP_DEFINITIONS["03"].handoff_max_chars,
        )
        # Fallback: if the activity didn't populate handoff but returned content, use it as the step4 prompt.
        if not step4_prompt:
            maybe_prompt = step_contents.get("03", "")
            if maybe_prompt:
                step4_prompt = maybe_prompt

        # Step 4 uses the generated prompt from step 3
        if not step4_prompt:
            step4_prompt = "STEP4_PROMPT missing from step 3; using placeholder prompt."

        if not step4_prompt:
            raise RuntimeError("STEP4_PROMPT was not returned from step 3; cannot run deep research (step 4).")

        await _run_step(
            "04",
            {
                "ADS_CONTEXT": base_vars.get("ADS_CONTEXT", ""),
            },
            prompt_override=step4_prompt,
        )
        step4_summary = step_summaries.get("04", "")

        # Step 6 depends on step 4
        step6_ref = await _run_step(
            "06",
            {"STEP4_SUMMARY": step4_summary, "ADS_CONTEXT": base_vars.get("ADS_CONTEXT", "")},
        )

        # Step 7 depends on step 4 & 6
        step7_ref = await _run_step(
            "07",
            {
                "STEP4_SUMMARY": step4_summary,
                "STEP6_SUMMARY": step6_ref["summary"],
                "ADS_CONTEXT": base_vars.get("ADS_CONTEXT", ""),
            },
        )

        # Step 8 depends on step 4,6,7
        step8_ref = await _run_step(
            "08",
            {
                "STEP4_SUMMARY": step4_summary,
                "STEP6_SUMMARY": step6_ref["summary"],
                "STEP7_SUMMARY": step7_ref["summary"],
                "ADS_CONTEXT": base_vars.get("ADS_CONTEXT", ""),
            },
        )

        # Step 9 depends on 4,6,7,8
        await _run_step(
            "09",
            {
                "STEP4_SUMMARY": step4_summary,
                "STEP6_SUMMARY": step6_ref["summary"],
                "STEP7_SUMMARY": step7_ref["summary"],
                "STEP8_SUMMARY": step8_ref["summary"],
                "ADS_CONTEXT": base_vars.get("ADS_CONTEXT", ""),
            },
        )

        canon_context: Dict[str, Any] = {
            "step_summaries": step_summaries,
            "step_contents": step_contents,
            "artifact_refs": [
                {"step_key": a["step_key"], "doc_url": a["doc_url"], "doc_id": a["doc_id"]} for a in artifacts
            ],
            "prompt_shas": prompt_shas,
            "ads_context": base_vars.get("ADS_CONTEXT", ""),
            "idea_folder_id": idea_folder_id,
            "idea_folder_url": idea_folder_url,
            "onboarding_context": {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "onboarding_payload_id": input.onboarding_payload_id,
                "business_context": base_vars.get("BUSINESS_CONTEXT", ""),
                "category_niche": base_vars.get("CATEGORY_NICHE", ""),
            },
        }

        return {"artifacts": artifacts, "canon_context": canon_context}
