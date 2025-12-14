from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, Any, List, Optional

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.experiment_activities import build_experiment_specs_activity


@dataclass
class ExperimentDesignInput:
    org_id: str
    client_id: str
    campaign_id: str
    resource_constraints_id: Optional[str] = None


@workflow.defn
class ExperimentDesignWorkflow:
    def __init__(self) -> None:
        self.experiment_specs: List[Dict[str, Any]] = []
        self._approved_ids: List[str] = []
        self._rejected_ids: List[str] = []

    @workflow.signal
    def approve_experiments(self, payload: Any) -> None:
        approved_ids: List[str] = []
        rejected_ids: List[str] = []
        edited_specs: Optional[Dict[str, Dict[str, Any]]] = None
        if isinstance(payload, dict):
            approved_ids = payload.get("approved_ids") or payload.get("approvedIds") or []
            rejected_ids = payload.get("rejected_ids") or payload.get("rejectedIds") or []
            edited_specs = payload.get("edited_specs") or payload.get("editedSpecs")
        elif isinstance(payload, list):
            approved_ids = payload
        self._approved_ids = approved_ids or []
        self._rejected_ids = rejected_ids or []
        if edited_specs:
            for spec in self.experiment_specs:
                if spec.get("id") in edited_specs:
                    spec.update(edited_specs[spec["id"]])

    @workflow.run
    async def run(self, input: ExperimentDesignInput) -> None:
        result = await workflow.execute_activity(
            build_experiment_specs_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "campaign_id": input.campaign_id,
                "resource_constraints_id": input.resource_constraints_id,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )
        self.experiment_specs = result.get("experiment_specs", [])
        await workflow.wait_condition(lambda: len(self._approved_ids) > 0 or len(self._rejected_ids) > 0)
