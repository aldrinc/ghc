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
        ingest_ads_for_identities_activity,
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
                "creative_analysis": None,
            }

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

        creative_analysis = None
        if input.run_creative_analysis and ad_ids:
            handle = await workflow.start_child_workflow(
                AdsCreativeAnalysisWorkflow.run,
                AdsCreativeAnalysisInput(
                    org_id=input.org_id,
                    client_id=input.client_id,
                    research_run_id=upsert_result["research_run_id"],
                    ad_ids=ad_ids,
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

        # Build and persist the same ads_context we pass upstream (includes breakdown summaries when available).
        context_result = await workflow.execute_activity(
            build_ads_context_activity,
            {"research_run_id": upsert_result["research_run_id"], "ad_ids": ad_ids},
            start_to_close_timeout=timedelta(minutes=5),
            schedule_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=3, backoff_coefficient=2.0),
        )
        return {
            "research_run_id": upsert_result["research_run_id"],
            "ads_context": context_result.get("ads_context"),
            "ingest_status": ingest_status,
            "ingest_reason": ingest_reason,
            "ingest_error": ingest_error,
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

        creative_analysis = None
        if input.run_creative_analysis and ad_ids:
            handle = await workflow.start_child_workflow(
                AdsCreativeAnalysisWorkflow.run,
                AdsCreativeAnalysisInput(
                    org_id=input.org_id or "",
                    client_id=input.client_id or "",
                    research_run_id=input.research_run_id,
                    ad_ids=ad_ids,
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
                "creative_analysis": creative_analysis,
            }

        context_result = await workflow.execute_activity(
            build_ads_context_activity,
            {"research_run_id": input.research_run_id, "ad_ids": ad_ids},
            start_to_close_timeout=timedelta(minutes=5),
            schedule_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=3, backoff_coefficient=2.0),
        )

        return {
            "research_run_id": input.research_run_id,
            "ads_context": context_result.get("ads_context"),
            "ingest_status": ingest_status,
            "ingest_reason": ingest_reason,
            "ingest_error": ingest_error,
            "creative_analysis": creative_analysis,
        }
