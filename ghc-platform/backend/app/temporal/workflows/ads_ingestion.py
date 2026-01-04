from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
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


@dataclass
class AdsIngestionInput:
    org_id: str
    client_id: str
    campaign_id: Optional[str]
    brand_discovery: Dict[str, Any]
    results_limit: Optional[int] = None
    run_creative_analysis: bool = False
    creative_analysis_max_ads: Optional[int] = None
    creative_analysis_concurrency: Optional[int] = None


@workflow.defn
class AdsIngestionWorkflow:
    @workflow.run
    async def run(self, input: AdsIngestionInput) -> Dict[str, Any]:
        upsert_result = await workflow.execute_activity(
            upsert_brands_and_identities_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "campaign_id": input.campaign_id,
                "brand_discovery": input.brand_discovery,
            },
            start_to_close_timeout=timedelta(minutes=2),
            schedule_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        ingest_result = await workflow.execute_activity(
            ingest_ads_for_identities_activity,
            {
                "research_run_id": upsert_result["research_run_id"],
                "brand_channel_identity_ids": upsert_result.get("brand_channel_identity_ids"),
                "results_limit": input.results_limit,
            },
            start_to_close_timeout=timedelta(minutes=30),
            schedule_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        ad_ids = ingest_result.get("ad_ids") if isinstance(ingest_result, dict) else None

        creative_analysis = None
        if input.run_creative_analysis:
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
            "creative_analysis": creative_analysis,
        }
