from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.client_onboarding_activities import (
        mark_client_onboarding_workflow_activity,
    )
    from app.temporal.activities.strategy_v2_activities import check_strategy_v2_enabled_activity
    from app.temporal.workflows.strategy_v2 import StrategyV2Input, StrategyV2Workflow


@dataclass
class ClientOnboardingInput:
    org_id: str
    client_id: str
    onboarding_payload_id: str
    product_id: str
    business_model: str | None = None
    funnel_position: str | None = None
    target_platforms: list[str] | None = None
    target_regions: list[str] | None = None
    existing_proof_assets: list[str] | None = None
    brand_voice_notes: str | None = None
    compliance_notes: str | None = None
    foundation_only: bool = True


@workflow.defn
class ClientOnboardingWorkflow:
    async def _mark_status(
        self,
        *,
        input: ClientOnboardingInput,
        status: str,
        error_message: str | None = None,
        payload_out: dict | None = None,
    ) -> None:
        info = workflow.info()
        await workflow.execute_activity(
            mark_client_onboarding_workflow_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "product_id": input.product_id,
                "temporal_workflow_id": info.workflow_id,
                "temporal_run_id": info.run_id,
                "status": status,
                "error_message": error_message,
                "payload_out": payload_out or {},
            },
            schedule_to_close_timeout=timedelta(minutes=2),
        )

    @workflow.run
    async def run(self, input: ClientOnboardingInput) -> None:
        try:
            strategy_v2_enabled_result = await workflow.execute_activity(
                check_strategy_v2_enabled_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                },
                schedule_to_close_timeout=timedelta(minutes=2),
            )
            strategy_v2_enabled = (
                bool(strategy_v2_enabled_result.get("enabled"))
                if isinstance(strategy_v2_enabled_result, dict)
                else False
            )
            if not strategy_v2_enabled:
                raise RuntimeError(
                    "Strategy V2 onboarding is required, but strategy_v2_enabled is false for this tenant/client."
                )

            strategy_result = await workflow.execute_child_workflow(
                StrategyV2Workflow.run,
                StrategyV2Input(
                    org_id=input.org_id,
                    client_id=input.client_id,
                    product_id=input.product_id,
                    onboarding_payload_id=input.onboarding_payload_id,
                    campaign_id=None,
                    operator_user_id="system",
                    business_model=input.business_model,
                    funnel_position=input.funnel_position,
                    target_platforms=list(input.target_platforms or []),
                    target_regions=list(input.target_regions or []),
                    existing_proof_assets=list(input.existing_proof_assets or []),
                    brand_voice_notes=input.brand_voice_notes,
                    compliance_notes=input.compliance_notes,
                    foundation_only=input.foundation_only,
                ),
                id=f"strategy-v2-{input.org_id}-{input.client_id}-{input.product_id}-{workflow.info().run_id}",
            )
            await self._mark_status(
                input=input,
                status="completed",
                payload_out=strategy_result if isinstance(strategy_result, dict) else {},
            )
        except Exception as exc:
            await self._mark_status(input=input, status="failed", error_message=str(exc))
            raise
