from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.meta_management_activities import (
        MetaManagementMonitorActivityInput,
        MetaManagementMonitorActivityOutput,
        run_meta_management_monitor_activity,
    )

logger = logging.getLogger(__name__)


@dataclass
class MetaManagementMonitorInput:
    org_id: str
    campaign_id: str
    date_preset: str = "last_3d"


@workflow.defn
class MetaManagementMonitorWorkflow:
    @workflow.run
    async def run(self, input: MetaManagementMonitorInput) -> MetaManagementMonitorActivityOutput:
        logger.info(
            "meta_management_monitor.started",
            extra={
                "org_id": input.org_id,
                "campaign_id": input.campaign_id,
            },
        )
        return await workflow.execute_activity(
            run_meta_management_monitor_activity,
            MetaManagementMonitorActivityInput(
                org_id=input.org_id,
                campaign_id=input.campaign_id,
                date_preset=input.date_preset,
            ),
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
