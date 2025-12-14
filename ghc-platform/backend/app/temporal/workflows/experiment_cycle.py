from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import List

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.signal_activities import (
        ensure_experiment_configured_activity,
        fetch_experiment_results_activity,
        build_experiment_report_activity,
    )


@dataclass
class ExperimentCycleInput:
    org_id: str
    client_id: str
    campaign_id: str
    experiment_ids: List[str]


@workflow.defn
class ExperimentCycleWorkflow:
    def __init__(self) -> None:
        self._should_stop = False

    @workflow.signal
    def stop(self) -> None:
        self._should_stop = True

    @workflow.run
    async def run(self, input: ExperimentCycleInput) -> None:
        await workflow.execute_activity(
            ensure_experiment_configured_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "campaign_id": input.campaign_id,
                "experiment_ids": input.experiment_ids,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )

        while not self._should_stop:
            await workflow.sleep(60)
            results = await workflow.execute_activity(
                fetch_experiment_results_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "campaign_id": input.campaign_id,
                    "experiment_ids": input.experiment_ids,
                },
                schedule_to_close_timeout=timedelta(minutes=2),
            )
            if results.get("all_experiments_ready"):
                break

        await workflow.execute_activity(
            build_experiment_report_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "campaign_id": input.campaign_id,
                "experiment_ids": input.experiment_ids,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )
