from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.ads_ingestion_activities import list_ads_for_run_activity
    from app.temporal.activities.ad_breakdown_activities import (
        generate_ad_breakdown_activity,
        persist_teardown_from_breakdown_activity,
    )

DEFAULT_MAX_ADS_PER_RUN = 100
DEFAULT_BREAKDOWN_CONCURRENCY = 3


@dataclass
class AdsCreativeAnalysisInput:
    org_id: str
    client_id: str
    research_run_id: str
    ad_ids: Optional[List[str]] = None
    max_ads: Optional[int] = None
    concurrency: Optional[int] = None


@workflow.defn
class AdsCreativeAnalysisWorkflow:
    @workflow.run
    async def run(self, input: AdsCreativeAnalysisInput) -> Dict[str, Any]:
        if input.ad_ids is not None:
            ad_ids = list(input.ad_ids)
        else:
            listing = await workflow.execute_activity(
                list_ads_for_run_activity,
                {"research_run_id": input.research_run_id},
                start_to_close_timeout=timedelta(minutes=2),
                schedule_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            ad_ids = list(listing.get("ad_ids") or [])

        if not ad_ids:
            return {"ad_count": 0, "succeeded": 0, "failed": 0, "skipped": 0}

        effective_max = input.max_ads or DEFAULT_MAX_ADS_PER_RUN
        if effective_max and len(ad_ids) > effective_max:
            ad_ids = ad_ids[:effective_max]

        concurrency = input.concurrency or DEFAULT_BREAKDOWN_CONCURRENCY
        semaphore = workflow.asyncio.Semaphore(max(1, concurrency))

        results: List[Dict[str, Any]] = []

        async def _run_for_ad(ad_id: str) -> None:
            async with semaphore:
                breakdown_res = await workflow.execute_activity(
                    generate_ad_breakdown_activity,
                    {
                        "org_id": input.org_id,
                        "client_id": input.client_id,
                        "research_run_id": input.research_run_id,
                        "ad_id": ad_id,
                    },
                    start_to_close_timeout=timedelta(minutes=5),
                    schedule_to_close_timeout=timedelta(minutes=10),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                job_id = breakdown_res.get("job_id") if isinstance(breakdown_res, dict) else None
                teardown_status: Dict[str, Any] | None = None
                if breakdown_res.get("status") == "succeeded" and job_id:
                    teardown_status = await workflow.execute_activity(
                        persist_teardown_from_breakdown_activity,
                        {
                            "org_id": input.org_id,
                            "client_id": input.client_id,
                            "research_run_id": input.research_run_id,
                            "ad_id": ad_id,
                            "job_id": job_id,
                        },
                        start_to_close_timeout=timedelta(minutes=5),
                        schedule_to_close_timeout=timedelta(minutes=10),
                        retry_policy=RetryPolicy(maximum_attempts=1),
                    )
                results.append(
                    {
                        "ad_id": ad_id,
                        "breakdown": breakdown_res or {},
                        "teardown": teardown_status or {},
                    }
                )

        tasks = [workflow.asyncio.create_task(_run_for_ad(ad_id)) for ad_id in ad_ids]
        await workflow.wait(tasks)

        succeeded = 0
        failed = 0
        skipped = 0
        for r in results:
            breakdown = r.get("breakdown") or {}
            teardown = r.get("teardown") or {}
            status = breakdown.get("status")
            if status == "succeeded":
                if teardown.get("status") == "succeeded":
                    succeeded += 1
                elif teardown.get("status") == "skipped":
                    skipped += 1
                else:
                    failed += 1
            elif status == "skipped":
                skipped += 1
            else:
                failed += 1

        return {
            "ad_count": len(ad_ids),
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
        }
