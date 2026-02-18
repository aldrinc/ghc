from __future__ import annotations

import asyncio
import concurrent.futures

from temporalio.worker import Worker

from app.config import settings
from app.observability import initialize_langfuse, shutdown_langfuse
from app.temporal.client import get_temporal_client
from app.temporal.workflows import placeholders as placeholder_workflow
from app.temporal.workflows.client_onboarding import ClientOnboardingWorkflow
from app.temporal.workflows.campaign_planning import CampaignPlanningWorkflow
from app.temporal.workflows.campaign_intent import CampaignIntentWorkflow
from app.temporal.workflows.campaign_funnel_generation import CampaignFunnelGenerationWorkflow
from app.temporal.workflows.experiment_design import ExperimentDesignWorkflow
from app.temporal.workflows.creative_production import CreativeProductionWorkflow
from app.temporal.workflows.swipe_image_ad import SwipeImageAdWorkflow
from app.temporal.workflows.experiment_cycle import ExperimentCycleWorkflow
from app.temporal.workflows.playbook_update import PlaybookUpdateWorkflow
from app.temporal.workflows.test_campaign import TestCampaignWorkflow
from app.temporal.workflows.precanon_market_research import PreCanonMarketResearchWorkflow
from app.temporal.workflows.ads_ingestion import AdsIngestionWorkflow, AdsIngestionRetryWorkflow
from app.temporal.workflows.ad_creative_analysis import AdsCreativeAnalysisWorkflow
from app.temporal.activities import placeholders as placeholder_activities
from app.temporal.activities.client_onboarding_activities import (
    build_client_canon_activity,
    build_design_system_activity,
    build_metric_schema_activity,
    persist_client_onboarding_artifacts_activity,
)
from app.temporal.activities.precanon_research_activities import (
    ensure_idea_folder_activity,
    fetch_onboarding_payload_activity,
    generate_step01_output_activity,
    generate_step015_output_activity,
    generate_step03_output_activity,
    generate_step06_output_activity,
    generate_step07_output_activity,
    generate_step08_output_activity,
    generate_step09_output_activity,
    persist_artifact_activity,
    run_step04_deep_research_activity,
)
from app.temporal.activities.competitor_table_activities import extract_competitors_table_activity
from app.temporal.activities.competitor_facebook_activities import resolve_competitor_facebook_pages_activity
from app.temporal.activities.competitor_brand_discovery_activities import (
    build_competitor_brand_discovery_activity,
)
from app.temporal.activities.strategy_activities import build_strategy_sheet_activity
from app.temporal.activities.experiment_activities import (
    build_experiment_specs_activity,
    fetch_experiment_specs_activity,
    create_asset_briefs_for_experiments_activity,
)
from app.temporal.activities.campaign_intent_activities import (
    create_campaign_activity,
    create_funnel_drafts_activity,
    create_funnels_from_experiments_activity,
)
from app.temporal.activities.asset_activities import generate_assets_for_brief_activity, persist_assets_activity
from app.temporal.activities.qa_activities import run_brand_qa_activity, run_compliance_qa_activity
from app.temporal.activities.signal_activities import (
    ensure_experiment_configured_activity,
    fetch_experiment_results_activity,
    build_experiment_report_activity,
)
from app.temporal.activities.playbook_activities import update_playbook_from_reports_activity
from app.temporal.activities.ads_ingestion_activities import (
    upsert_brands_and_identities_activity,
    fetch_ad_library_page_totals_activity,
    ingest_ads_for_identities_activity,
    select_ads_for_context_activity,
    build_ads_context_activity,
    list_ads_for_run_activity,
)
from app.temporal.activities.ad_breakdown_activities import (
    generate_ad_breakdown_activity,
    persist_teardown_from_breakdown_activity,
)
from app.temporal.activities.swipe_image_ad_activities import (
    generate_swipe_image_ad_activity,
)


async def main() -> None:
    initialize_langfuse()
    client = await get_temporal_client()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as activity_executor:
            worker = Worker(
                client,
                task_queue=settings.TEMPORAL_TASK_QUEUE,
                workflows=[
                    placeholder_workflow.PlaceholderWorkflow,
                    ClientOnboardingWorkflow,
                    PreCanonMarketResearchWorkflow,
                    CampaignPlanningWorkflow,
                    CampaignIntentWorkflow,
                    CampaignFunnelGenerationWorkflow,
                    ExperimentDesignWorkflow,
                    CreativeProductionWorkflow,
                    SwipeImageAdWorkflow,
                    ExperimentCycleWorkflow,
                    PlaybookUpdateWorkflow,
                    AdsIngestionWorkflow,
                    AdsIngestionRetryWorkflow,
                    AdsCreativeAnalysisWorkflow,
                    TestCampaignWorkflow,
                ],
                activities=[
                    placeholder_activities.noop_activity,
                    build_client_canon_activity,
                    build_design_system_activity,
                    build_metric_schema_activity,
                    persist_client_onboarding_artifacts_activity,
                    fetch_onboarding_payload_activity,
                    extract_competitors_table_activity,
                    resolve_competitor_facebook_pages_activity,
                    build_competitor_brand_discovery_activity,
                    ensure_idea_folder_activity,
                    generate_step01_output_activity,
                    generate_step015_output_activity,
                    generate_step03_output_activity,
                    run_step04_deep_research_activity,
                    generate_step06_output_activity,
                    generate_step07_output_activity,
                    generate_step08_output_activity,
                    generate_step09_output_activity,
                    persist_artifact_activity,
                    build_strategy_sheet_activity,
                    build_experiment_specs_activity,
                    fetch_experiment_specs_activity,
                    create_asset_briefs_for_experiments_activity,
                    create_campaign_activity,
                    create_funnel_drafts_activity,
                    create_funnels_from_experiments_activity,
                    generate_assets_for_brief_activity,
                    persist_assets_activity,
                    run_brand_qa_activity,
                    run_compliance_qa_activity,
                    ensure_experiment_configured_activity,
                    fetch_experiment_results_activity,
                    build_experiment_report_activity,
                    update_playbook_from_reports_activity,
                    upsert_brands_and_identities_activity,
                    fetch_ad_library_page_totals_activity,
                    ingest_ads_for_identities_activity,
                    select_ads_for_context_activity,
                    build_ads_context_activity,
                    list_ads_for_run_activity,
                    generate_ad_breakdown_activity,
                    persist_teardown_from_breakdown_activity,
                    generate_swipe_image_ad_activity,
                ],
                activity_executor=activity_executor,
            )
            await worker.run()
    finally:
        shutdown_langfuse()


if __name__ == "__main__":
    asyncio.run(main())
