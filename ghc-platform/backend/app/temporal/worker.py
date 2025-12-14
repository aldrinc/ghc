from __future__ import annotations

import asyncio
import concurrent.futures

from temporalio.worker import Worker

from app.config import settings
from app.temporal.client import get_temporal_client
from app.temporal.workflows import placeholders as placeholder_workflow
from app.temporal.workflows.client_onboarding import ClientOnboardingWorkflow
from app.temporal.workflows.campaign_planning import CampaignPlanningWorkflow
from app.temporal.workflows.experiment_design import ExperimentDesignWorkflow
from app.temporal.workflows.creative_production import CreativeProductionWorkflow
from app.temporal.workflows.experiment_cycle import ExperimentCycleWorkflow
from app.temporal.workflows.playbook_update import PlaybookUpdateWorkflow
from app.temporal.workflows.test_campaign import TestCampaignWorkflow
from app.temporal.workflows.precanon_market_research import PreCanonMarketResearchWorkflow
from app.temporal.activities import placeholders as placeholder_activities
from app.temporal.activities.client_onboarding_activities import (
    build_client_canon_activity,
    build_metric_schema_activity,
    persist_client_onboarding_artifacts_activity,
)
from app.temporal.activities.precanon_research_activities import (
    fetch_onboarding_payload_activity,
    get_ads_context_stub_activity,
    generate_research_step_artifact_activity,
)
from app.temporal.activities.strategy_activities import build_strategy_sheet_activity
from app.temporal.activities.experiment_activities import (
    build_experiment_specs_activity,
    create_asset_briefs_for_experiments_activity,
)
from app.temporal.activities.asset_activities import generate_assets_for_brief_activity, persist_assets_activity
from app.temporal.activities.qa_activities import run_brand_qa_activity, run_compliance_qa_activity
from app.temporal.activities.signal_activities import (
    ensure_experiment_configured_activity,
    fetch_experiment_results_activity,
    build_experiment_report_activity,
)
from app.temporal.activities.playbook_activities import update_playbook_from_reports_activity


async def main() -> None:
    client = await get_temporal_client()
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as activity_executor:
        worker = Worker(
            client,
            task_queue=settings.TEMPORAL_TASK_QUEUE,
            workflows=[
                placeholder_workflow.PlaceholderWorkflow,
                ClientOnboardingWorkflow,
                PreCanonMarketResearchWorkflow,
                CampaignPlanningWorkflow,
                ExperimentDesignWorkflow,
                CreativeProductionWorkflow,
                ExperimentCycleWorkflow,
                PlaybookUpdateWorkflow,
                TestCampaignWorkflow,
            ],
            activities=[
                placeholder_activities.noop_activity,
                build_client_canon_activity,
                build_metric_schema_activity,
                persist_client_onboarding_artifacts_activity,
                fetch_onboarding_payload_activity,
                get_ads_context_stub_activity,
                generate_research_step_artifact_activity,
                build_strategy_sheet_activity,
                build_experiment_specs_activity,
                create_asset_briefs_for_experiments_activity,
                generate_assets_for_brief_activity,
                persist_assets_activity,
                run_brand_qa_activity,
                run_compliance_qa_activity,
                ensure_experiment_configured_activity,
                fetch_experiment_results_activity,
                build_experiment_report_activity,
                update_playbook_from_reports_activity,
            ],
            activity_executor=activity_executor,
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
