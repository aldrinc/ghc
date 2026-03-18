import { useMemo } from "react";
import type { WorkflowRun } from "@/types/common";
import type { ExperimentSpec, AssetBrief } from "@/types/artifacts";

export type PipelinePhase =
  | "strategy"
  | "angles"
  | "delivery"
  | "creative"
  | "publish_prep"
  | "publish_launch";

export type PhaseStatus = "not_started" | "in_progress" | "completed";

export type PipelinePhaseInfo = {
  phase: PipelinePhase;
  label: string;
  status: PhaseStatus;
  route: string;
};

/**
 * Derives the pipeline phase statuses from campaign data.
 * Each phase's completion is determined by inspecting existing state —
 * no new backend endpoints are required.
 */
export function useCampaignPipeline({
  campaignWorkflows,
  hasStrategyArtifact,
  experimentSpecs,
  assetBriefs,
  funnelCount,
  generatedAssetTotal,
}: {
  campaignWorkflows: WorkflowRun[];
  hasStrategyArtifact: boolean;
  experimentSpecs: ExperimentSpec[];
  assetBriefs: AssetBrief[];
  funnelCount: number;
  generatedAssetTotal: number;
}): PipelinePhaseInfo[] {
  return useMemo(() => {
    // Strategy: complete when campaign strategy output exists. Strategy V2
    // source runs are product-scoped for launched angle campaigns, so they
    // do not appear in the campaign-scoped workflow list.
    const strategyWorkflow = campaignWorkflows.find(
      (wf) => wf.kind === "strategy_v2" && wf.status === "completed",
    );
    const strategyRunning = campaignWorkflows.some(
      (wf) => wf.kind === "strategy_v2" && wf.status === "running",
    );
    const strategyStatus: PhaseStatus = hasStrategyArtifact || strategyWorkflow
      ? "completed"
      : strategyRunning
        ? "in_progress"
        : "not_started";

    // Angles: complete when experiment specs exist
    const anglesStatus: PhaseStatus = experimentSpecs.length > 0 ? "completed" : "not_started";

    // Delivery: complete when funnels exist (internal mode)
    const deliveryStatus: PhaseStatus = funnelCount > 0 ? "completed" : "not_started";

    // Creative: complete when generated assets exist
    const creativeRunning = campaignWorkflows.some(
      (wf) =>
        (wf.kind === "creative_production" || wf.kind === "campaign_creative_production") &&
        wf.status === "running",
    );
    const creativeStatus: PhaseStatus = generatedAssetTotal > 0
      ? "completed"
      : creativeRunning
        ? "in_progress"
        : assetBriefs.length > 0
          ? "not_started"
          : "not_started";

    // Publish prep: complete when a Meta review setup has run
    const publishPrepWorkflow = campaignWorkflows.find(
      (wf) => wf.kind === "meta_review_setup" && wf.status === "completed",
    );
    const publishPrepRunning = campaignWorkflows.some(
      (wf) => wf.kind === "meta_review_setup" && wf.status === "running",
    );
    const publishPrepStatus: PhaseStatus = publishPrepWorkflow
      ? "completed"
      : publishPrepRunning
        ? "in_progress"
        : "not_started";

    // Publish launch: complete when a publish run has succeeded
    const publishLaunchWorkflow = campaignWorkflows.find(
      (wf) => wf.kind === "meta_publish" && wf.status === "completed",
    );
    const publishLaunchStatus: PhaseStatus = publishLaunchWorkflow ? "completed" : "not_started";

    return [
      { phase: "strategy", label: "Strategy", status: strategyStatus, route: "strategy" },
      { phase: "angles", label: "Angles", status: anglesStatus, route: "angles" },
      { phase: "delivery", label: "Delivery", status: deliveryStatus, route: "delivery" },
      { phase: "creative", label: "Creative", status: creativeStatus, route: "creative" },
      { phase: "publish_prep", label: "Prep", status: publishPrepStatus, route: "publish" },
      { phase: "publish_launch", label: "Publish", status: publishLaunchStatus, route: "publish" },
    ];
  }, [campaignWorkflows, hasStrategyArtifact, experimentSpecs, assetBriefs, funnelCount, generatedAssetTotal]);
}
