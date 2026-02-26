from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.strategy_v2_activities import check_strategy_v2_enabled_activity
    from app.temporal.workflows.strategy_v2 import StrategyV2Input, StrategyV2Workflow


@dataclass
class ClientOnboardingInput:
    org_id: str
    client_id: str
    onboarding_payload_id: str
    product_id: str
    business_model: str
    funnel_position: str
    target_platforms: list[str]
    target_regions: list[str]
    existing_proof_assets: list[str]
    brand_voice_notes: str
    compliance_notes: str | None = None


@workflow.defn
class ClientOnboardingWorkflow:
    @workflow.run
    async def run(self, input: ClientOnboardingInput) -> None:
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

        await workflow.start_child_workflow(
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
                target_platforms=list(input.target_platforms),
                target_regions=list(input.target_regions),
                existing_proof_assets=list(input.existing_proof_assets),
                brand_voice_notes=input.brand_voice_notes,
                compliance_notes=input.compliance_notes,
            ),
            id=f"strategy-v2-{input.org_id}-{input.client_id}-{input.product_id}-{workflow.info().run_id}",
            parent_close_policy=workflow.ParentClosePolicy.ABANDON,
        )
