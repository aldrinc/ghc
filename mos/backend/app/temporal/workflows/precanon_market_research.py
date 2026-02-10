from __future__ import annotations

from datetime import timedelta
import json
import os
from typing import Any, Dict, List, Optional
import logging
from dataclasses import asdict

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.llm import LLMGenerationParams
    from app.temporal.activities.precanon_research_activities import (
        ensure_idea_folder_activity,
        fetch_onboarding_payload_activity,
        generate_step01_output_activity,
        generate_step015_output_activity,
        generate_step03_output_activity,
        generate_step06_output_activity,
        generate_step07_output_activity,
        generate_step08_output_activity,
        generate_step09_output_activity,
        persist_artifact_activity,
        run_step04_deep_research_activity,
    )
    from app.temporal.activities.competitor_table_activities import extract_competitors_table_activity
    from app.temporal.activities.competitor_facebook_activities import resolve_competitor_facebook_pages_activity
    from app.temporal.activities.competitor_brand_discovery_activities import (
        build_competitor_brand_discovery_activity,
    )
    from app.temporal.precanon import (
        PreCanonMarketResearchInput,
        STEP_DEFINITIONS,
    )
    from app.temporal.precanon.research import (
        IdeaFolderRequest,
        PersistArtifactRequest,
        PromptBuildRequest,
        ResearchBaseContext,
        StepGenerationRequest,
        build_prompt,
        parse_step_output,
    )
    from app.schemas.competitors import ExtractCompetitorsRequest, ResolveFacebookRequest
    from app.temporal.workflows.ads_ingestion import AdsIngestionWorkflow, AdsIngestionInput

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("LLM_DEFAULT_MODEL", "gpt-5.2-2025-12-11")
DEFAULT_REASONING_MODEL = os.getenv("PRECANON_REASONING_MODEL", "gpt-5.2-2025-12-11")
DEFAULT_PARENT_FOLDER_ID = os.getenv("RESEARCH_DRIVE_PARENT_FOLDER_ID") or os.getenv("PARENT_FOLDER_ID")
STEP04_START_TO_CLOSE_MINUTES = int(os.getenv("PRECANON_STEP04_START_TO_CLOSE_MINUTES", "360"))
STEP04_SCHEDULE_TO_CLOSE_MINUTES = int(os.getenv("PRECANON_STEP04_SCHEDULE_TO_CLOSE_MINUTES", "420"))
STEP_LLM_CONFIG: Dict[str, Dict[str, Any]] = {
    "01": {
        "model": os.getenv("PRECANON_STEP01_MODEL", DEFAULT_REASONING_MODEL),
        "use_reasoning": True,
        "use_web_search": True,
    },
    "015": {
        "model": os.getenv("PRECANON_STEP015_MODEL", DEFAULT_REASONING_MODEL),
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
    product_id: str,
    payload: Dict[str, Any],
    ads_context: Dict[str, Any],
) -> Dict[str, str]:
    # Derive a concise idea string for prompts/folder naming.
    idea = payload.get("product_name") or payload.get("idea")
    if not idea:
        offers = payload.get("offers") or []
        idea = offers[0] if offers else None
    if not idea:
        story = (payload.get("brand_story") or "").strip()
        idea = story.split("\n")[0][:200] if story else None
    business_context = idea or payload.get("business_type") or "Client business context"

    category_niche = (
        payload.get("product_category")
        or payload.get("industry")
        or payload.get("category")
        or payload.get("niche")
        or "general"
    )
    ads_ctx_raw: Any = ads_context
    if isinstance(ads_context, dict):
        ads_ctx_raw = ads_context.get("ads_context") if "ads_context" in ads_context else ads_context
    ads_ctx_str = _safe_json_dump(ads_ctx_raw) if ads_ctx_raw else ""
    return {
        "ORG_ID": org_id,
        "CLIENT_ID": client_id,
        "ONBOARDING_PAYLOAD_ID": onboarding_payload_id,
        "PRODUCT_ID": product_id,
        "BUSINESS_CONTEXT": str(business_context),
        "BUSINESS_CONTEXT_JSON": _safe_json_dump(payload),
        "CATEGORY_NICHE": str(category_niche),
        "ADS_CONTEXT": ads_ctx_str,
    }


def _llm_params_for_step(step_key: str) -> LLMGenerationParams:
    config = STEP_LLM_CONFIG.get(step_key, {})
    model = config.get("model") or DEFAULT_MODEL
    return LLMGenerationParams(
        model=model,
        use_reasoning=bool(config.get("use_reasoning", False)),
        use_web_search=bool(config.get("use_web_search", False)),
        max_tokens=config.get("max_tokens"),
    )


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
        ads_context = {"ads_context": ""}
        base_vars = _build_base_variables(
            org_id=input.org_id,
            client_id=input.client_id,
            onboarding_payload_id=input.onboarding_payload_id,
            product_id=input.product_id,
            payload=payload or {},
            ads_context=ads_context or {},
        )
        base_context = ResearchBaseContext(
            org_id=input.org_id,
            client_id=input.client_id,
            product_id=input.product_id,
            onboarding_payload_id=input.onboarding_payload_id,
            idea_workspace_id=workflow.info().workflow_id,
            workflow_id=workflow.info().workflow_id,
            workflow_run_id=workflow.info().run_id,
            parent_workflow_id=getattr(workflow.info(), "parent", None).workflow_id
            if getattr(workflow.info(), "parent", None)
            else None,
            parent_run_id=getattr(workflow.info(), "parent", None).run_id
            if getattr(workflow.info(), "parent", None)
            else None,
            parent_folder_id=DEFAULT_PARENT_FOLDER_ID,
            idea_folder_name=base_vars.get("BUSINESS_CONTEXT") or base_vars.get("BUSINESS_CONTEXT_JSON") or "idea",
        )

        artifacts: List[Any] = []
        step_summaries: Dict[str, str] = {}
        step_contents: Dict[str, str] = {}
        prompt_shas: Dict[str, str] = {}
        step_jobs: Dict[str, Any] = {}
        handoffs: Dict[str, Any] = {}
        step4_prompt: Optional[str] = None
        ads_research_run_id: Optional[str] = None
        ads_creative_analysis: Optional[Dict[str, Any]] = None
        ads_ingestion_status: Optional[str] = None
        ads_ingestion_reason: Optional[str] = None
        ads_ingestion_error: Optional[str] = None

        generation_activities = {
            "01": generate_step01_output_activity,
            "015": generate_step015_output_activity,
            "03": generate_step03_output_activity,
            "04": run_step04_deep_research_activity,
            "06": generate_step06_output_activity,
            "07": generate_step07_output_activity,
            "08": generate_step08_output_activity,
            "09": generate_step09_output_activity,
        }

        async def _ensure_idea_folder() -> None:
            nonlocal base_context
            if base_context.idea_folder_id or not base_context.parent_folder_id:
                return
            folder_result = await workflow.execute_activity(
                ensure_idea_folder_activity,
                IdeaFolderRequest(
                    parent_folder_id=base_context.parent_folder_id,
                    idea_folder_name=base_context.idea_folder_name,
                ),
                summary="Precanon – ensure idea folder",
                start_to_close_timeout=timedelta(minutes=2),
                schedule_to_close_timeout=timedelta(minutes=5),
            )
            base_context.idea_folder_id = folder_result.idea_folder_id or base_context.idea_folder_id
            base_context.idea_folder_url = folder_result.idea_folder_url or base_context.idea_folder_url

        async def _run_step(
            step_key: str,
            extra_vars: Dict[str, str],
            *,
            prompt_override: Optional[str] = None,
            summary_max_override: Optional[int] = None,
            handoff_max_override: Optional[int] = None,
        ):
            nonlocal base_context, step4_prompt
            definition = STEP_DEFINITIONS[step_key]
            if step_key == "04" and not prompt_override:
                raise ValueError("Step 04 requires a prompt_override from step 3 handoff.")

            vars_for_step = {**base_vars, **extra_vars}
            prompt_request = PromptBuildRequest(
                step_key=step_key,
                variables=vars_for_step,
                prompt_override=prompt_override,
            )
            prompt_result = build_prompt(prompt_request)
            llm_params = _llm_params_for_step(step_key)
            generation_request = StepGenerationRequest(
                step_key=step_key,
                prompt_text=prompt_result.prompt_text,
                prompt_sha256=prompt_result.prompt_sha256,
                llm_params=llm_params,
                title=definition.title,
                org_id=input.org_id,
                client_id=input.client_id,
                onboarding_payload_id=input.onboarding_payload_id,
                workflow_id=base_context.workflow_id,
                workflow_run_id=base_context.workflow_run_id,
                parent_workflow_id=base_context.parent_workflow_id,
                parent_run_id=base_context.parent_run_id,
            )
            generation_activity = generation_activities.get(step_key)
            if not generation_activity:
                raise ValueError(f"No generation activity registered for step {step_key}")
            generation_timeouts = {
                "schedule_to_close_timeout": timedelta(minutes=30),
                "start_to_close_timeout": timedelta(minutes=10),
            }
            if step_key == "01":
                generation_timeouts = {
                    "schedule_to_close_timeout": timedelta(minutes=60),
                    "start_to_close_timeout": timedelta(minutes=60),
                    "retry_policy": RetryPolicy(maximum_attempts=1),
                }
            if step_key == "015":
                generation_timeouts = {
                    "schedule_to_start_timeout": timedelta(minutes=60),
                    "schedule_to_close_timeout": timedelta(minutes=60),
                    "start_to_close_timeout": timedelta(minutes=60),
                    "retry_policy": RetryPolicy(maximum_attempts=1),
                }
            if step_key == "04":
                generation_timeouts = {
                    "schedule_to_close_timeout": timedelta(minutes=STEP04_SCHEDULE_TO_CLOSE_MINUTES),
                    "start_to_close_timeout": timedelta(minutes=STEP04_START_TO_CLOSE_MINUTES),
                    "retry_policy": RetryPolicy(maximum_attempts=1),
                }

            generation_result = await workflow.execute_activity(
                generation_activity,
                generation_request,
                summary=f"Precanon Step {step_key} – {definition.title} (generate)",
                **generation_timeouts,
            )

            parsed = parse_step_output(
                step_key=step_key,
                raw_output=generation_result.raw_output,
                summary_max_chars=summary_max_override or definition.summary_max_chars,
                handoff_max_chars=handoff_max_override or definition.handoff_max_chars,
            )

            await _ensure_idea_folder()

            persist_request = PersistArtifactRequest(
                step_key=step_key,
                title=definition.title,
                summary=parsed.summary,
                content=parsed.content,
                prompt_sha256=prompt_result.prompt_sha256,
                org_id=input.org_id,
                client_id=input.client_id,
                product_id=input.product_id,
                campaign_id=None,
                idea_workspace_id=base_context.idea_workspace_id,
                workflow_id=base_context.workflow_id,
                workflow_run_id=base_context.workflow_run_id,
                parent_workflow_id=base_context.parent_workflow_id,
                parent_run_id=base_context.parent_run_id,
                parent_folder_id=base_context.parent_folder_id,
                idea_folder_id=base_context.idea_folder_id,
                idea_folder_url=base_context.idea_folder_url,
                idea_folder_name=base_context.idea_folder_name,
                allow_drive_stub=base_context.allow_drive_stub,
                allow_claude_stub=base_context.allow_claude_stub,
            )
            persist_timeouts = {
                "start_to_close_timeout": timedelta(minutes=5),
                "schedule_to_close_timeout": timedelta(minutes=15),
            }
            if step_key == "01":
                persist_timeouts["retry_policy"] = RetryPolicy(maximum_attempts=1)
            if step_key == "015":
                persist_timeouts["retry_policy"] = RetryPolicy(maximum_attempts=1)
            persist_result = await workflow.execute_activity(
                persist_artifact_activity,
                persist_request,
                summary=f"Precanon Step {step_key} – {definition.title} (persist)",
                **persist_timeouts,
            )
            base_context.idea_folder_id = persist_result.idea_folder_id or base_context.idea_folder_id
            base_context.idea_folder_url = persist_result.idea_folder_url or base_context.idea_folder_url

            ref = {
                "step_key": step_key,
                "title": definition.title,
                "doc_url": persist_result.doc_url,
                "doc_id": persist_result.doc_id,
                "summary": parsed.summary,
                "prompt_sha256": prompt_result.prompt_sha256,
                "created_at_iso": persist_result.created_at_iso,
            }
            artifacts.append(ref)
            step_summaries[step_key] = parsed.summary
            step_contents[step_key] = parsed.content
            prompt_shas[step_key] = prompt_result.prompt_sha256
            if generation_result.job:
                step_jobs[step_key] = asdict(generation_result.job)
            if parsed.handoff:
                handoffs[step_key] = parsed.handoff
                if step_key == "03" and "step4_prompt" in parsed.handoff:
                    if "<STEP4_PROMPT>" in generation_result.raw_output:
                        step4_prompt = parsed.content
                    else:
                        step4_prompt = parsed.handoff["step4_prompt"]

            return {"parsed": parsed, "ref": ref, "handoff": parsed.handoff}

        # Step 1
        step1_result = await _run_step("01", {})
        step1_content = step1_result["parsed"].content

        # Step 2a: extract structured competitor rows from the latest detailed table in Step 1.
        extract_result = await workflow.execute_activity(
            extract_competitors_table_activity,
            ExtractCompetitorsRequest(step1_content=step1_content),
            start_to_close_timeout=timedelta(minutes=2),
            schedule_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        competitor_table = (extract_result.chosen_table_markdown or "").strip()
        if not competitor_table:
            raise RuntimeError(
                "Step 01.5 requires a competitor table extracted from Step 01, but none was found."
            )

        product_name = (base_vars.get("CATEGORY_NICHE") or "").strip()
        if not product_name:
            raise RuntimeError(
                "Step 01.5 requires PRODUCT_NAME (category/niche) but CATEGORY_NICHE was empty."
            )

        # Step 1.5: run purple ocean angle research using competitor table outputs.
        await _run_step(
            "015",
            {
                "PRODUCT_NAME": product_name,
                "COMPETITOR_TABLE": competitor_table,
            },
        )

        # Step 2b: resolve Facebook pages for competitors via LLM + web search.
        resolve_result = await workflow.execute_activity(
            resolve_competitor_facebook_pages_activity,
            ResolveFacebookRequest(
                competitors=extract_result.competitors,
                category_niche=base_vars.get("CATEGORY_NICHE"),
                org_id=input.org_id,
                client_id=input.client_id,
            ),
            start_to_close_timeout=timedelta(minutes=10),
            schedule_to_close_timeout=timedelta(minutes=20),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        # Persist resolution mapping as a Step 02 artifact for debugging/traceability.
        await _ensure_idea_folder()
        resolution_content = resolve_result.model_dump_json(indent=2)
        resolution_persist_result = await workflow.execute_activity(
            persist_artifact_activity,
            PersistArtifactRequest(
                step_key="02",
                title="Competitor Facebook Page Resolution",
                summary=f"Resolved Facebook pages for {len(resolve_result.competitors)} competitors.",
                content=resolution_content,
                prompt_sha256="",
                org_id=input.org_id,
                client_id=input.client_id,
                product_id=input.product_id,
                campaign_id=None,
                idea_workspace_id=base_context.idea_workspace_id,
                workflow_id=base_context.workflow_id,
                workflow_run_id=base_context.workflow_run_id,
                parent_workflow_id=base_context.parent_workflow_id,
                parent_run_id=base_context.parent_run_id,
                parent_folder_id=base_context.parent_folder_id,
                idea_folder_id=base_context.idea_folder_id,
                idea_folder_url=base_context.idea_folder_url,
                idea_folder_name=base_context.idea_folder_name,
                allow_drive_stub=base_context.allow_drive_stub,
                allow_claude_stub=base_context.allow_claude_stub,
            ),
            summary="Precanon Step 02 – Competitor Facebook Page Resolution (persist)",
            start_to_close_timeout=timedelta(minutes=5),
            schedule_to_close_timeout=timedelta(minutes=15),
        )
        artifacts.append(
            {
                "step_key": "02",
                "title": "Competitor Facebook Page Resolution",
                "doc_url": resolution_persist_result.doc_url,
                "doc_id": resolution_persist_result.doc_id,
                "summary": f"Resolved Facebook pages for {len(resolve_result.competitors)} competitors.",
                "prompt_sha256": "",
                "created_at_iso": resolution_persist_result.created_at_iso,
            }
        )

        # Derive competitor brand discovery from enriched competitors and kick off ad scraping for ads_context.
        discovery_result = await workflow.execute_activity(
            build_competitor_brand_discovery_activity,
            {"competitors": [c.model_dump(mode="json") for c in resolve_result.competitors]},
            start_to_close_timeout=timedelta(minutes=2),
            schedule_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        brand_discovery = discovery_result.get("brand_discovery")
        if brand_discovery:
            try:
                ads_run = await workflow.execute_child_workflow(
                    AdsIngestionWorkflow.run,
                    AdsIngestionInput(
                        org_id=input.org_id,
                        client_id=input.client_id,
                        product_id=input.product_id,
                        campaign_id=None,
                        brand_discovery=brand_discovery,
                        results_limit=50,
                        run_creative_analysis=True,
                        creative_analysis_max_ads=None,
                        creative_analysis_concurrency=None,
                    ),
                )
                ads_research_run_id = ads_run.get("research_run_id") if isinstance(ads_run, dict) else None
                ads_creative_analysis = ads_run.get("creative_analysis") if isinstance(ads_run, dict) else None
                ads_ingestion_status = ads_run.get("ingest_status") if isinstance(ads_run, dict) else None
                ads_ingestion_reason = ads_run.get("ingest_reason") if isinstance(ads_run, dict) else None
                ads_ingestion_error = ads_run.get("ingest_error") if isinstance(ads_run, dict) else None
                ads_ctx_value = ads_run.get("ads_context") if isinstance(ads_run, dict) else None
                if not ads_ctx_value:
                    logger.warning(
                        "Ads ingestion returned empty context; continuing with stub.",
                        extra={
                            "workflow_id": workflow.info().workflow_id,
                            "ads_ingestion_status": ads_ingestion_status,
                            "ads_ingestion_reason": ads_ingestion_reason,
                            "ads_research_run_id": ads_research_run_id,
                        },
                    )
                    ads_ctx_value = {
                        "status": ads_ingestion_status or "empty",
                        "reason": ads_ingestion_reason or "ads_context_missing",
                    }
                    if ads_ingestion_error:
                        ads_ctx_value["error"] = ads_ingestion_error
                ads_context = {"ads_context": ads_ctx_value}
                base_vars["ADS_CONTEXT"] = _safe_json_dump(ads_ctx_value)
            except Exception as exc:  # noqa: BLE001
                ads_ingestion_status = "failed"
                ads_ingestion_reason = "ads_ingestion_workflow_failed"
                ads_ingestion_error = str(exc)
                logger.error(
                    "Ads ingestion workflow failed; continuing without ads context.",
                    extra={
                        "workflow_id": workflow.info().workflow_id,
                        "error": ads_ingestion_error,
                    },
                )
                ads_ctx_value = {
                    "status": ads_ingestion_status,
                    "reason": ads_ingestion_reason,
                    "error": ads_ingestion_error,
                }
                ads_context = {"ads_context": ads_ctx_value}
                base_vars["ADS_CONTEXT"] = _safe_json_dump(ads_ctx_value)
        else:
            logger.warning(
                "Brand discovery did not produce any records; ads context will remain empty.",
                extra={"workflow_id": workflow.info().workflow_id},
            )

        # Step 3 (needs step1 summary and ads context)
        step3_result = await _run_step(
            "03",
            {"STEP1_SUMMARY": step_summaries.get("01", ""), "ADS_CONTEXT": base_vars.get("ADS_CONTEXT", "")},
            handoff_max_override=STEP_DEFINITIONS["03"].handoff_max_chars,
        )

        # Step 4 prompt: prefer the full <STEP4_PROMPT> content captured as Step 3 `content`.
        step4_prompt = step3_result["parsed"].content
        if not step4_prompt:
            maybe_handoff = step3_result["handoff"] or {}
            step4_prompt = maybe_handoff.get("step4_prompt") if isinstance(maybe_handoff, dict) else None

        if not step4_prompt:
            raise RuntimeError("STEP4_PROMPT was not returned from step 3; cannot run deep research (step 4).")

        step4_result = await _run_step(
            "04",
            {"ADS_CONTEXT": base_vars.get("ADS_CONTEXT", "")},
            prompt_override=step4_prompt,
        )
        step4_summary = step4_result["parsed"].summary

        # Step 6 depends on step 4
        step6_result = await _run_step(
            "06",
            {
                "STEP4_SUMMARY": step4_summary,
                "STEP4_CONTENT": step_contents.get("04", ""),
                "ADS_CONTEXT": base_vars.get("ADS_CONTEXT", ""),
            },
        )

        # Step 7 depends on step 4 & 6
        step7_result = await _run_step(
            "07",
            {
                "STEP4_SUMMARY": step4_summary,
                "STEP6_SUMMARY": step6_result["parsed"].summary,
                "STEP4_CONTENT": step_contents.get("04", ""),
                "STEP6_CONTENT": step_contents.get("06", ""),
                "ADS_CONTEXT": base_vars.get("ADS_CONTEXT", ""),
            },
        )

        # Step 8 depends on step 4,6,7
        step8_result = await _run_step(
            "08",
            {
                "STEP4_SUMMARY": step4_summary,
                "STEP6_SUMMARY": step6_result["parsed"].summary,
                "STEP7_SUMMARY": step7_result["parsed"].summary,
                "STEP4_CONTENT": step_contents.get("04", ""),
                "STEP6_CONTENT": step_contents.get("06", ""),
                "STEP7_CONTENT": step7_result["parsed"].content,
                "ADS_CONTEXT": base_vars.get("ADS_CONTEXT", ""),
            },
        )

        # Step 9 depends on 4,6,7,8
        await _run_step(
            "09",
            {
                "STEP4_SUMMARY": step4_summary,
                "STEP6_SUMMARY": step6_result["parsed"].summary,
                "STEP7_SUMMARY": step7_result["parsed"].summary,
                "STEP8_SUMMARY": step8_result["parsed"].summary,
                "STEP4_CONTENT": step_contents.get("04", ""),
                "STEP6_CONTENT": step_contents.get("06", ""),
                "STEP7_CONTENT": step7_result["parsed"].content,
                "STEP8_CONTENT": step8_result["parsed"].content,
                "ADS_CONTEXT": base_vars.get("ADS_CONTEXT", ""),
            },
        )

        canon_context: Dict[str, Any] = {
            "step_summaries": step_summaries,
            "step_contents": step_contents,
            "artifact_refs": [
                {
                    "step_key": a["step_key"],
                    "title": a["title"],
                    "doc_url": a["doc_url"],
                    "doc_id": a["doc_id"],
                }
                for a in artifacts
            ],
            "prompt_shas": prompt_shas,
            "ads_context": base_vars.get("ADS_CONTEXT", ""),
            "ads_research_run_id": ads_research_run_id,
            "ads_creative_analysis": ads_creative_analysis,
            "ads_ingestion_status": ads_ingestion_status,
            "ads_ingestion_reason": ads_ingestion_reason,
            "ads_ingestion_error": ads_ingestion_error,
            "idea_folder_id": base_context.idea_folder_id,
            "idea_folder_url": base_context.idea_folder_url,
            "onboarding_context": {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "onboarding_payload_id": input.onboarding_payload_id,
                "business_context": base_vars.get("BUSINESS_CONTEXT", ""),
                "category_niche": base_vars.get("CATEGORY_NICHE", ""),
            },
            "deep_research_jobs": step_jobs,
            "handoffs": handoffs,
        }

        return {"artifacts": artifacts, "canon_context": canon_context}
