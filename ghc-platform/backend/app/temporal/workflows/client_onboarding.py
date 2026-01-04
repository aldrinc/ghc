from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Optional

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.client_onboarding_activities import (
        build_client_canon_activity,
        build_metric_schema_activity,
        persist_client_onboarding_artifacts_activity,
    )
    from app.temporal.precanon import PreCanonMarketResearchInput
    from app.temporal.workflows.precanon_market_research import PreCanonMarketResearchWorkflow


@dataclass
class ClientOnboardingInput:
    org_id: str
    client_id: str
    onboarding_payload_id: str


@workflow.defn
class ClientOnboardingWorkflow:
    def __init__(self) -> None:
        self.canon: Optional[Dict[str, Any]] = None
        self.metric_schema: Optional[Dict[str, Any]] = None
        self._canon_approved = False
        self._metric_approved = False

    @workflow.signal
    def approve_canon(self, payload: Any) -> None:
        """
        Accepts either a boolean (approved) or a dict with keys approved/updated_canon/updatedCanon.
        Using a single payload keeps signal invocation simple from HTTP.
        """
        approved = payload if isinstance(payload, bool) else bool(payload.get("approved", False))
        updated_canon = None
        if isinstance(payload, dict):
            updated_canon = payload.get("updated_canon") or payload.get("updatedCanon")
        if approved and updated_canon:
            self.canon = updated_canon
        self._canon_approved = approved

    @workflow.signal
    def approve_metric_schema(self, payload: Any) -> None:
        approved = payload if isinstance(payload, bool) else bool(payload.get("approved", False))
        updated_schema = None
        if isinstance(payload, dict):
            updated_schema = payload.get("updated_schema") or payload.get("updatedSchema")
        if approved and updated_schema:
            self.metric_schema = updated_schema
        self._metric_approved = approved

    @workflow.run
    async def run(self, input: ClientOnboardingInput) -> None:
        research = await workflow.execute_child_workflow(
            PreCanonMarketResearchWorkflow.run,
            PreCanonMarketResearchInput(
                org_id=input.org_id,
                client_id=input.client_id,
                onboarding_payload_id=input.onboarding_payload_id,
            ),
        )
        # research is a dict with artifacts and canon_context
        precanon_ctx = research.get("canon_context", {}) if isinstance(research, dict) else {}
        precanon_artifacts = research.get("artifacts", []) if isinstance(research, dict) else []

        self.canon = await workflow.execute_activity(
            build_client_canon_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "onboarding_payload_id": input.onboarding_payload_id,
                "precanon_research": precanon_ctx,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )

        await workflow.wait_condition(lambda: self._canon_approved)

        self.metric_schema = await workflow.execute_activity(
            build_metric_schema_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "onboarding_payload_id": input.onboarding_payload_id,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )

        await workflow.wait_condition(lambda: self._metric_approved)

        await workflow.execute_activity(
            persist_client_onboarding_artifacts_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "canon": self.canon,
                "metric_schema": self.metric_schema,
                "research_artifacts": precanon_artifacts,
                "temporal_workflow_id": workflow.info().workflow_id,
                "temporal_run_id": workflow.info().run_id,
            },
            schedule_to_close_timeout=timedelta(minutes=2),
        )
