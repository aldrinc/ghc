from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import os
from typing import Any, Dict, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.ads_ingestion_activities import (
        upsert_brands_and_identities_activity,
        fetch_ad_library_page_totals_activity,
        ingest_ads_for_identities_activity,
        select_ads_for_context_activity,
        build_ads_context_activity,
    )
    from app.temporal.workflows.ad_creative_analysis import (
        AdsCreativeAnalysisInput,
        AdsCreativeAnalysisWorkflow,
    )

INGEST_ACTIVITY_START_TO_CLOSE_HOURS = int(os.getenv("ADS_INGEST_START_TO_CLOSE_HOURS", "6"))
INGEST_ACTIVITY_SCHEDULE_TO_CLOSE_HOURS = int(os.getenv("ADS_INGEST_SCHEDULE_TO_CLOSE_HOURS", "6"))


@dataclass
class AdsIngestionInput:
    org_id: str
    client_id: str
    product_id: Optional[str]
    campaign_id: Optional[str]
    brand_discovery: Dict[str, Any]
    results_limit: Optional[int] = None
    run_creative_analysis: bool = False
    creative_analysis_max_ads: Optional[int] = None
    creative_analysis_concurrency: Optional[int] = None


@dataclass
class AdsIngestionRetryInput:
    research_run_id: str
    results_limit: Optional[int] = None
    brand_channel_identity_ids: Optional[list[str]] = None
    run_creative_analysis: bool = False
    creative_analysis_max_ads: Optional[int] = None
    creative_analysis_concurrency: Optional[int] = None
    org_id: Optional[str] = None
    client_id: Optional[str] = None


@workflow.defn
class AdsIngestionWorkflow:
    @workflow.run
    async def run(self, input: AdsIngestionInput) -> Dict[str, Any]:
        upsert_result: Dict[str, Any] = {}
        try:
            upsert_result = await workflow.execute_activity(
                upsert_brands_and_identities_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "brand_discovery": input.brand_discovery,
                },
                start_to_close_timeout=timedelta(minutes=2),
                schedule_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception as exc:  # noqa: BLE001
            ingest_status = "failed"
            ingest_reason = "upsert_activity_failed"
            ingest_error = str(exc)
            workflow.logger.error(
                "ads_ingestion.upsert_activity_failed",
                extra={
                    "workflow_id": workflow.info().workflow_id,
                    "run_id": workflow.info().run_id,
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "error": ingest_error,
                },
            )
            # No research_run_id exists if we couldn't upsert/create it.
            return {
                "research_run_id": None,
                "ads_context": None,
                "ingest_status": ingest_status,
                "ingest_reason": ingest_reason,
                "ingest_error": ingest_error,
                "ad_library_totals": None,
                "creative_analysis": None,
            }

        identity_ids = upsert_result.get("brand_channel_identity_ids") or []
        if not identity_ids:
            # No channel identities means we have nothing to ingest (e.g., competitor FB resolution returned no pages).
            ingest_status = "skipped"
            ingest_reason = "no_identities"
            ads_context = {
                "brands": [],
                "cross_brand": {"top_destination_domains": [], "cta_distribution": []},
                "status": ingest_status,
                "reason": ingest_reason,
            }
            return {
                "research_run_id": upsert_result["research_run_id"],
                "ads_context": ads_context,
                "ingest_status": ingest_status,
                "ingest_reason": ingest_reason,
                "ingest_error": None,
                "ad_library_totals": None,
                "creative_analysis": None,
            }

        ad_library_totals = await workflow.execute_activity(
            fetch_ad_library_page_totals_activity,
            {
                "research_run_id": upsert_result["research_run_id"],
                "brand_channel_identity_ids": identity_ids,
            },
            start_to_close_timeout=timedelta(minutes=30),
            schedule_to_close_timeout=timedelta(minutes=45),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        ingest_result: Dict[str, Any] = {}
        ingest_status: Optional[str] = None
        ingest_reason: Optional[str] = None
        ingest_error: Optional[str] = None
        ad_ids = None
        try:
            ingest_result = await workflow.execute_activity(
                ingest_ads_for_identities_activity,
                {
                    "research_run_id": upsert_result["research_run_id"],
                    "brand_channel_identity_ids": upsert_result.get("brand_channel_identity_ids"),
                    "results_limit": input.results_limit,
                },
                start_to_close_timeout=timedelta(hours=INGEST_ACTIVITY_START_TO_CLOSE_HOURS),
                schedule_to_close_timeout=timedelta(hours=INGEST_ACTIVITY_SCHEDULE_TO_CLOSE_HOURS),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            if isinstance(ingest_result, dict):
                ad_ids = ingest_result.get("ad_ids")
                ingest_status = ingest_result.get("status")
                ingest_reason = ingest_result.get("reason")
        except Exception as exc:  # noqa: BLE001
            ingest_status = "failed"
            ingest_reason = "ingest_activity_failed"
            ingest_error = str(exc)
            workflow.logger.error(
                "ads_ingestion.ingest_activity_failed",
                extra={
                    "workflow_id": workflow.info().workflow_id,
                    "run_id": workflow.info().run_id,
                    "research_run_id": upsert_result.get("research_run_id"),
                    "error": ingest_error,
                },
            )

        selection_result = await workflow.execute_activity(
            select_ads_for_context_activity,
            {"research_run_id": upsert_result["research_run_id"]},
            start_to_close_timeout=timedelta(minutes=2),
            schedule_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        selected_ad_ids = selection_result.get("ad_ids") if isinstance(selection_result, dict) else None
        selection_meta = selection_result.get("selection") if isinstance(selection_result, dict) else None

        creative_analysis = None
        if input.run_creative_analysis and selected_ad_ids:
            handle = None
            try:
                handle = await workflow.start_child_workflow(
                    AdsCreativeAnalysisWorkflow.run,
                    AdsCreativeAnalysisInput(
                        org_id=input.org_id,
                        client_id=input.client_id,
                        research_run_id=upsert_result["research_run_id"],
                        ad_ids=selected_ad_ids,
                        max_ads=input.creative_analysis_max_ads,
                        concurrency=input.creative_analysis_concurrency,
                    ),
                )
                creative_analysis_result = await handle
                creative_analysis = {
                    "workflow_id": handle.id,
                    "first_execution_run_id": handle.first_execution_run_id,
                    "result": creative_analysis_result if isinstance(creative_analysis_result, dict) else {},
                }
            except Exception as exc:  # noqa: BLE001
                # Creative analysis is non-critical for ingestion; keep returning the research_run_id so callers can retry.
                error_msg = str(exc)
                workflow.logger.error(
                    "ads_ingestion.creative_analysis_failed",
                    extra={
                        "workflow_id": workflow.info().workflow_id,
                        "run_id": workflow.info().run_id,
                        "research_run_id": upsert_result.get("research_run_id"),
                        "child_workflow_id": getattr(handle, "id", None),
                        "child_first_execution_run_id": getattr(handle, "first_execution_run_id", None),
                        "error": error_msg,
                    },
                )
                creative_analysis = {
                    "workflow_id": getattr(handle, "id", None),
                    "first_execution_run_id": getattr(handle, "first_execution_run_id", None),
                    "error": error_msg,
                }

        # Build and persist the same ads_context we pass upstream (includes breakdown summaries when available).
        ads_context = None
        try:
            context_result = await workflow.execute_activity(
                build_ads_context_activity,
                {
                    "research_run_id": upsert_result["research_run_id"],
                    "ad_ids": selected_ad_ids,
                    "selection": selection_meta,
                },
                start_to_close_timeout=timedelta(minutes=5),
                schedule_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(maximum_attempts=3, backoff_coefficient=2.0),
            )
            if isinstance(context_result, dict):
                ads_context = context_result.get("ads_context")
        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            workflow.logger.error(
                "ads_ingestion.build_ads_context_failed",
                extra={
                    "workflow_id": workflow.info().workflow_id,
                    "run_id": workflow.info().run_id,
                    "research_run_id": upsert_result.get("research_run_id"),
                    "error": error_msg,
                },
            )
            # Keep a non-empty stub so upstream workflows don't lose error context.
            ads_context = {
                "brands": [],
                "cross_brand": {"top_destination_domains": [], "cta_distribution": []},
                "warning": "ads_context generation failed; continuing without ads context",
                "error": error_msg,
            }
        return {
            "research_run_id": upsert_result["research_run_id"],
            "ads_context": ads_context,
            "ingest_status": ingest_status,
            "ingest_reason": ingest_reason,
            "ingest_error": ingest_error,
            "ad_library_totals": ad_library_totals if isinstance(ad_library_totals, dict) else {},
            "ad_selection": selection_result if isinstance(selection_result, dict) else {},
            "creative_analysis": creative_analysis,
        }


@workflow.defn
class AdsIngestionRetryWorkflow:
    @workflow.run
    async def run(self, input: AdsIngestionRetryInput) -> Dict[str, Any]:
        if input.run_creative_analysis and (not input.org_id or not input.client_id):
            raise ValueError("org_id and client_id are required when run_creative_analysis is true.")

        ingest_result: Dict[str, Any] = {}
        ingest_status: Optional[str] = None
        ingest_reason: Optional[str] = None
        ingest_error: Optional[str] = None
        ad_ids = None

        try:
            ingest_result = await workflow.execute_activity(
                ingest_ads_for_identities_activity,
                {
                    "research_run_id": input.research_run_id,
                    "brand_channel_identity_ids": input.brand_channel_identity_ids,
                    "results_limit": input.results_limit,
                },
                start_to_close_timeout=timedelta(hours=INGEST_ACTIVITY_START_TO_CLOSE_HOURS),
                schedule_to_close_timeout=timedelta(hours=INGEST_ACTIVITY_SCHEDULE_TO_CLOSE_HOURS),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "No brand channel identities found for research run" in msg:
                ingest_status = "skipped"
                ingest_reason = "no_identities"
                ingest_error = msg
            else:
                raise

        if ingest_status != "skipped" and isinstance(ingest_result, dict):
            ad_ids = ingest_result.get("ad_ids")
            ingest_status = ingest_result.get("status")
            ingest_reason = ingest_result.get("reason")

        ad_library_totals = None
        if ingest_status != "skipped":
            ad_library_totals = await workflow.execute_activity(
                fetch_ad_library_page_totals_activity,
                {
                    "research_run_id": input.research_run_id,
                    "brand_channel_identity_ids": input.brand_channel_identity_ids,
                },
                start_to_close_timeout=timedelta(minutes=30),
                schedule_to_close_timeout=timedelta(minutes=45),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )

        selection_result = None
        selected_ad_ids = None
        selection_meta = None
        if ingest_status != "skipped":
            selection_result = await workflow.execute_activity(
                select_ads_for_context_activity,
                {"research_run_id": input.research_run_id},
                start_to_close_timeout=timedelta(minutes=2),
                schedule_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            selected_ad_ids = selection_result.get("ad_ids") if isinstance(selection_result, dict) else None
            selection_meta = selection_result.get("selection") if isinstance(selection_result, dict) else None

        creative_analysis = None
        if input.run_creative_analysis and selected_ad_ids:
            handle = None
            try:
                handle = await workflow.start_child_workflow(
                    AdsCreativeAnalysisWorkflow.run,
                    AdsCreativeAnalysisInput(
                        org_id=input.org_id or "",
                        client_id=input.client_id or "",
                        research_run_id=input.research_run_id,
                        ad_ids=selected_ad_ids,
                        max_ads=input.creative_analysis_max_ads,
                        concurrency=input.creative_analysis_concurrency,
                    ),
                )
                creative_analysis_result = await handle
                creative_analysis = {
                    "workflow_id": handle.id,
                    "first_execution_run_id": handle.first_execution_run_id,
                    "result": creative_analysis_result if isinstance(creative_analysis_result, dict) else {},
                }
            except Exception as exc:  # noqa: BLE001
                error_msg = str(exc)
                workflow.logger.error(
                    "ads_ingestion_retry.creative_analysis_failed",
                    extra={
                        "workflow_id": workflow.info().workflow_id,
                        "run_id": workflow.info().run_id,
                        "research_run_id": input.research_run_id,
                        "child_workflow_id": getattr(handle, "id", None),
                        "child_first_execution_run_id": getattr(handle, "first_execution_run_id", None),
                        "error": error_msg,
                    },
                )
                creative_analysis = {
                    "workflow_id": getattr(handle, "id", None),
                    "first_execution_run_id": getattr(handle, "first_execution_run_id", None),
                    "error": error_msg,
                }

        if ingest_status == "skipped":
            ads_context = {
                "brands": [],
                "cross_brand": {"top_destination_domains": [], "cta_distribution": []},
                "status": ingest_status,
                "reason": ingest_reason,
            }
            return {
                "research_run_id": input.research_run_id,
                "ads_context": ads_context,
                "ingest_status": ingest_status,
                "ingest_reason": ingest_reason,
                "ingest_error": ingest_error,
                "ad_library_totals": None,
                "ad_selection": None,
                "creative_analysis": creative_analysis,
            }

        ads_context = None
        try:
            context_result = await workflow.execute_activity(
                build_ads_context_activity,
                {"research_run_id": input.research_run_id, "ad_ids": selected_ad_ids, "selection": selection_meta},
                start_to_close_timeout=timedelta(minutes=5),
                schedule_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(maximum_attempts=3, backoff_coefficient=2.0),
            )
            if isinstance(context_result, dict):
                ads_context = context_result.get("ads_context")
        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            workflow.logger.error(
                "ads_ingestion_retry.build_ads_context_failed",
                extra={
                    "workflow_id": workflow.info().workflow_id,
                    "run_id": workflow.info().run_id,
                    "research_run_id": input.research_run_id,
                    "error": error_msg,
                },
            )
            ads_context = {
                "brands": [],
                "cross_brand": {"top_destination_domains": [], "cta_distribution": []},
                "warning": "ads_context generation failed; continuing without ads context",
                "error": error_msg,
            }

        return {
            "research_run_id": input.research_run_id,
            "ads_context": ads_context,
            "ingest_status": ingest_status,
            "ingest_reason": ingest_reason,
            "ingest_error": ingest_error,
            "ad_library_totals": ad_library_totals if isinstance(ad_library_totals, dict) else {},
            "ad_selection": selection_result if isinstance(selection_result, dict) else {},
            "creative_analysis": creative_analysis,
        }
