from __future__ import annotations

import asyncio
import concurrent.futures

from temporalio.worker import Worker

from app.config import settings
from app.llm_ops import initialize_agenta, shutdown_agenta
from app.observability import initialize_langfuse, shutdown_langfuse
from app.temporal.client import get_temporal_client
from app.temporal.workflows import placeholders as placeholder_workflow
from app.temporal.workflows.client_onboarding import ClientOnboardingWorkflow
from app.temporal.workflows.campaign_planning import CampaignPlanningWorkflow
from app.temporal.workflows.campaign_intent import CampaignIntentWorkflow
from app.temporal.workflows.campaign_funnel_generation import CampaignFunnelGenerationWorkflow
from app.temporal.workflows.campaign_funnel_media_enrichment import CampaignFunnelMediaEnrichmentWorkflow
from app.temporal.workflows.experiment_design import ExperimentDesignWorkflow
from app.temporal.workflows.creative_production import CreativeProductionWorkflow
from app.temporal.workflows.swipe_image_ad import SwipeImageAdWorkflow
from app.temporal.workflows.experiment_cycle import ExperimentCycleWorkflow
from app.temporal.workflows.playbook_update import PlaybookUpdateWorkflow
from app.temporal.workflows.test_campaign import TestCampaignWorkflow
from app.temporal.workflows.precanon_market_research import PreCanonMarketResearchWorkflow
from app.temporal.workflows.ads_ingestion import AdsIngestionWorkflow, AdsIngestionRetryWorkflow
from app.temporal.workflows.ad_creative_analysis import AdsCreativeAnalysisWorkflow
from app.temporal.workflows.strategy_v2 import StrategyV2Workflow
from app.temporal.workflows.strategy_v2_launch import (
    StrategyV2AngleCampaignLaunchWorkflow,
    StrategyV2AngleIterationWorkflow,
)
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
    enrich_funnel_page_media_activity,
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
from app.temporal.activities.strategy_v2_activities import (
    apply_strategy_v2_angle_selection_activity,
    build_strategy_v2_foundational_research_activity,
    build_strategy_v2_offer_variants_activity,
    build_strategy_v2_stage0_activity,
    check_strategy_v2_enabled_activity,
    ensure_strategy_v2_workflow_run_activity,
    finalize_strategy_v2_competitor_assets_confirmation_activity,
    finalize_strategy_v2_copy_approval_activity,
    finalize_strategy_v2_offer_winner_activity,
    finalize_strategy_v2_research_proceed_activity,
    mark_strategy_v2_failed_activity,
    prepare_strategy_v2_competitor_asset_candidates_activity,
    run_strategy_v2_copy_pipeline_activity,
    run_strategy_v2_offer_pipeline_activity,
    run_strategy_v2_voc_agent0_habitat_strategy_activity,
    run_strategy_v2_voc_agent0b_apify_collection_activity,
    run_strategy_v2_voc_agent0b_social_video_strategy_activity,
    run_strategy_v2_voc_agent0b_apify_ingestion_activity,
    run_strategy_v2_voc_agent1_habitat_qualifier_activity,
    run_strategy_v2_voc_agent2_extraction_activity,
    run_strategy_v2_voc_agent3_synthesis_activity,
    run_strategy_v2_voc_angle_pipeline_activity,
)
from app.temporal.activities.strategy_v2_launch_activities import (
    create_strategy_v2_launch_artifacts_activity,
    persist_strategy_v2_launch_record_activity,
)


async def main() -> None:
    initialize_agenta()
    initialize_langfuse()
    client = await get_temporal_client()
    try:
        primary_workflows = [
            placeholder_workflow.PlaceholderWorkflow,
            ClientOnboardingWorkflow,
            PreCanonMarketResearchWorkflow,
            CampaignPlanningWorkflow,
            CampaignIntentWorkflow,
            CampaignFunnelGenerationWorkflow,
            CampaignFunnelMediaEnrichmentWorkflow,
            ExperimentDesignWorkflow,
            CreativeProductionWorkflow,
            SwipeImageAdWorkflow,
            ExperimentCycleWorkflow,
            PlaybookUpdateWorkflow,
            AdsIngestionWorkflow,
            AdsIngestionRetryWorkflow,
            AdsCreativeAnalysisWorkflow,
            TestCampaignWorkflow,
            StrategyV2Workflow,
            StrategyV2AngleCampaignLaunchWorkflow,
            StrategyV2AngleIterationWorkflow,
        ]
        primary_activities = [
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
            enrich_funnel_page_media_activity,
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
            check_strategy_v2_enabled_activity,
            ensure_strategy_v2_workflow_run_activity,
            build_strategy_v2_stage0_activity,
            build_strategy_v2_foundational_research_activity,
            finalize_strategy_v2_research_proceed_activity,
            prepare_strategy_v2_competitor_asset_candidates_activity,
            finalize_strategy_v2_competitor_assets_confirmation_activity,
            run_strategy_v2_voc_agent0_habitat_strategy_activity,
            run_strategy_v2_voc_agent0b_apify_collection_activity,
            run_strategy_v2_voc_agent0b_social_video_strategy_activity,
            run_strategy_v2_voc_agent0b_apify_ingestion_activity,
            run_strategy_v2_voc_agent1_habitat_qualifier_activity,
            run_strategy_v2_voc_agent2_extraction_activity,
            run_strategy_v2_voc_agent3_synthesis_activity,
            run_strategy_v2_voc_angle_pipeline_activity,
            apply_strategy_v2_angle_selection_activity,
            run_strategy_v2_offer_pipeline_activity,
            build_strategy_v2_offer_variants_activity,
            finalize_strategy_v2_offer_winner_activity,
            run_strategy_v2_copy_pipeline_activity,
            finalize_strategy_v2_copy_approval_activity,
            mark_strategy_v2_failed_activity,
            create_strategy_v2_launch_artifacts_activity,
            persist_strategy_v2_launch_record_activity,
        ]

        with (
            concurrent.futures.ThreadPoolExecutor(max_workers=16) as primary_activity_executor,
            concurrent.futures.ThreadPoolExecutor(
                max_workers=max(1, settings.TEMPORAL_MEDIA_ENRICHMENT_ACTIVITY_WORKERS)
            ) as media_activity_executor,
        ):
            primary_worker = Worker(
                client,
                task_queue=settings.TEMPORAL_TASK_QUEUE,
                workflows=primary_workflows,
                activities=primary_activities,
                activity_executor=primary_activity_executor,
            )

            media_queue = settings.TEMPORAL_MEDIA_ENRICHMENT_TASK_QUEUE
            if media_queue == settings.TEMPORAL_TASK_QUEUE:
                await primary_worker.run()
            else:
                media_worker = Worker(
                    client,
                    task_queue=media_queue,
                    workflows=[CampaignFunnelMediaEnrichmentWorkflow],
                    activities=[enrich_funnel_page_media_activity],
                    activity_executor=media_activity_executor,
                )
                await asyncio.gather(primary_worker.run(), media_worker.run())
    finally:
        shutdown_langfuse()
        shutdown_agenta()


if __name__ == "__main__":
    asyncio.run(main())
