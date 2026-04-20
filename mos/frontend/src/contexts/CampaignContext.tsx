import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  useCampaign,
  useCampaignDelivery,
  useCampaignLaunchContextReadiness,
  useCampaignStrategyV2Launches,
} from "@/api/campaigns";
import { type ApiError } from "@/api/client";
import { useArtifacts, useLatestArtifact } from "@/api/artifacts";
import { useFunnels } from "@/api/funnels";
import { useMetaApi } from "@/api/meta";
import { useProduct } from "@/api/products";
import { useWorkflows, useWorkflowLogs } from "@/api/workflows";
import { useProductContext } from "@/contexts/ProductContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import {
  groupPipelineAssetsByBriefId,
  selectLatestProductionBatchPipelineAssets,
} from "@/lib/campaignProductionBatch";
import type { Artifact, AssetBrief, ExperimentSpec, StrategySheet } from "@/types/artifacts";
import type { Campaign, StrategyV2LaunchRecord, WorkflowRun } from "@/types/common";
import type { CampaignDeliveryConfig, CampaignLaunchContextReadiness } from "@/types/delivery";
import type { ProductAsset } from "@/types/products";
import type { MetaPipelineAsset } from "@/types/meta";

// ---------------------------------------------------------------------------
// Derived types
// ---------------------------------------------------------------------------

export type FunnelRecord = {
  id: string;
  name: string;
  status: string;
  experiment_spec_id?: string | null;
  updated_at?: string | null;
  [key: string]: unknown;
};

// ---------------------------------------------------------------------------
// Context value
// ---------------------------------------------------------------------------

type CampaignContextValue = {
  // Core
  campaignId: string;
  campaign: Campaign;

  // Workspace / product
  workspaceName: string | null;
  campaignProductLabel: string | null;
  campaignProductId: string | undefined;
  campaignProductDetail: { assets?: ProductAsset[] } | undefined;
  campaignProductLoading: boolean;

  // Workflows
  workflows: WorkflowRun[];
  workflowsLoading: boolean;
  campaignWorkflows: WorkflowRun[];

  // Strategy
  strategyArtifact: Artifact | null;
  strategyLoading: boolean;
  strategy: StrategySheet;

  // Experiments / angles
  experimentArtifacts: Artifact[];
  experimentsLoading: boolean;
  experimentSpecs: ExperimentSpec[];

  // Asset briefs
  assetBriefArtifacts: Artifact[];
  briefsLoading: boolean;
  assetBriefs: AssetBrief[];
  generatedAssetsByBriefId: Map<string, MetaPipelineAsset[]>;
  generatedAssetTotal: number;
  briefsWithGeneratedAssets: number;
  generatedAssetsLoading: boolean;
  latestGeneratedBatchId: string | null;

  // Funnels
  funnels: FunnelRecord[];
  funnelsLoading: boolean;

  // Strategy V2 launches
  campaignLaunches: StrategyV2LaunchRecord[];
  campaignStrategyV2LaunchesLoading: boolean;
  launchByFunnelId: Map<string, StrategyV2LaunchRecord>;

  // Delivery / readiness
  deliveryConfig: CampaignDeliveryConfig | null;
  deliveryLoading: boolean;
  launchContextReadiness: CampaignLaunchContextReadiness | null;
  launchContextReadinessLoading: boolean;

  // Funnel workflow state
  funnelLogs: Array<{ id: string; step: string; status: string; error?: string | null; created_at: string }>;
  latestFunnelWorkflow: WorkflowRun | undefined;
};

const CampaignCtx = createContext<CampaignContextValue | undefined>(undefined);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

const EMPTY_ARTIFACTS: Artifact[] = [];

export function CampaignProvider({
  campaignId,
  children,
}: {
  campaignId: string;
  children: ReactNode;
}) {
  const { workspace, clients } = useWorkspace();
  const { product, products } = useProductContext();
  const { listPipelineAssets } = useMetaApi();

  // ---- Core campaign data ------------------------------------------------
  const { data: campaign } = useCampaign(campaignId);

  // ---- Workflows ---------------------------------------------------------
  const { data: workflows = [], isLoading: workflowsLoading } = useWorkflows();
  const campaignWorkflows = useMemo(() => {
    if (!campaignId) return [];
    return workflows
      .filter((wf) => wf.campaign_id === campaignId)
      .sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());
  }, [campaignId, workflows]);

  const funnelWorkflows = useMemo(
    () => campaignWorkflows.filter((wf) => wf.kind === "campaign_funnel_generation"),
    [campaignWorkflows],
  );
  const latestFunnelWorkflow = funnelWorkflows[0];
  const { data: funnelLogs = [] } = useWorkflowLogs(latestFunnelWorkflow?.id);

  // ---- Artifacts ---------------------------------------------------------
  const strategyFilters = useMemo(() => ({ campaignId, type: "strategy_sheet" }), [campaignId]);
  const experimentFilters = useMemo(() => ({ campaignId, type: "experiment_spec" }), [campaignId]);
  const assetBriefFilters = useMemo(() => ({ campaignId, type: "asset_brief" }), [campaignId]);

  const { latest: strategyArtifact, isLoading: strategyLoading } = useLatestArtifact(strategyFilters);
  const { data: experimentArtifacts = EMPTY_ARTIFACTS, isLoading: experimentsLoading } =
    useArtifacts(experimentFilters);
  const { data: assetBriefArtifacts = EMPTY_ARTIFACTS, isLoading: briefsLoading } =
    useArtifacts(assetBriefFilters);

  // ---- Funnels -----------------------------------------------------------
  const { data: funnels = [], isLoading: funnelsLoading } = useFunnels(
    campaignId ? { campaignId } : undefined,
  );

  // ---- Strategy V2 launches ----------------------------------------------
  const { data: campaignStrategyV2Launches = [], isLoading: campaignStrategyV2LaunchesLoading } =
    useCampaignStrategyV2Launches(campaignId);
  const { data: deliveryConfig, isLoading: deliveryLoading } = useCampaignDelivery(campaignId);
  const { data: launchContextReadiness, isLoading: launchContextReadinessLoading } =
    useCampaignLaunchContextReadiness(campaignId);

  // ---- Product -----------------------------------------------------------
  const campaignProductId = campaign?.product_id || product?.id;
  const { data: campaignProductDetail, isLoading: campaignProductLoading } = useProduct(
    campaignProductId || undefined,
  );

  const {
    data: pipelineAssets = [],
    isLoading: generatedAssetsLoading,
  } = useQuery<MetaPipelineAsset[], ApiError>({
    queryKey: ["meta", "pipeline", "assets", campaignId],
    queryFn: () => listPipelineAssets({ campaignId }),
    enabled: Boolean(campaignId),
  });

  // ---- Derived: workspace name -------------------------------------------
  const workspaceName = useMemo(() => {
    if (!campaign?.client_id) return null;
    if (workspace?.id === campaign.client_id) return workspace.name;
    return clients.find((client) => client.id === campaign.client_id)?.name ?? null;
  }, [campaign?.client_id, workspace?.id, workspace?.name, clients]);

  const campaignProduct = useMemo(
    () => products.find((item) => item.id === campaign?.product_id),
    [products, campaign?.product_id],
  );
  const campaignProductLabel = campaignProduct?.title || campaign?.product_id || null;

  // ---- Derived: strategy -------------------------------------------------
  const strategy = useMemo(
    () => (strategyArtifact?.data || {}) as StrategySheet,
    [strategyArtifact?.data],
  );

  // ---- Derived: experiment specs -----------------------------------------
  const experimentSpecs = useMemo(() => {
    const latest = experimentArtifacts?.[0];
    const data = (latest?.data || {}) as {
      experimentSpecs?: ExperimentSpec[];
      experiment_specs?: ExperimentSpec[];
    };
    const specs = data.experimentSpecs || (data as Record<string, unknown>).experiment_specs || [];
    if (!Array.isArray(specs)) return [];
    return specs.filter(
      (spec) => spec && typeof spec === "object" && Boolean((spec as ExperimentSpec).id),
    );
  }, [experimentArtifacts]);

  // ---- Derived: asset briefs ---------------------------------------------
  const assetBriefs = useMemo(() => {
    const map = new Map<string, AssetBrief>();
    assetBriefArtifacts.forEach((art) => {
      const data = (art.data || {}) as {
        asset_briefs?: AssetBrief[];
        assetBriefs?: AssetBrief[];
      };
      const briefs = data.asset_briefs || data.assetBriefs || [];
      briefs.forEach((brief) => {
        if (!brief || typeof brief !== "object") return;
        const id = (brief as AssetBrief).id;
        if (!id || map.has(id)) return;
        map.set(id, brief as AssetBrief);
      });
    });
    return Array.from(map.values());
  }, [assetBriefArtifacts]);

  // ---- Derived: generated assets by brief --------------------------------
  const { batchId: latestGeneratedBatchId, assets: latestGeneratedPipelineAssets } = useMemo(() => {
    return selectLatestProductionBatchPipelineAssets(
      pipelineAssets,
      assetBriefs.map((brief) => brief.id),
    );
  }, [assetBriefs, pipelineAssets]);

  const generatedAssetsByBriefId = useMemo(() => {
    return groupPipelineAssetsByBriefId(latestGeneratedPipelineAssets);
  }, [latestGeneratedPipelineAssets]);

  const generatedAssetTotal = useMemo(
    () =>
      Array.from(generatedAssetsByBriefId.values()).reduce(
        (sum, assets) => sum + assets.length,
        0,
      ),
    [generatedAssetsByBriefId],
  );

  const briefsWithGeneratedAssets = useMemo(
    () =>
      Array.from(generatedAssetsByBriefId.values()).filter((assets) => assets.length > 0).length,
    [generatedAssetsByBriefId],
  );

  // ---- Derived: launches -------------------------------------------------
  const campaignLaunches = useMemo(() => {
    return [...(campaignStrategyV2Launches as StrategyV2LaunchRecord[])].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );
  }, [campaignStrategyV2Launches]);

  const launchByFunnelId = useMemo(() => {
    const map = new Map<string, StrategyV2LaunchRecord>();
    campaignLaunches.forEach((row) => {
      if (!row.funnel_id || map.has(row.funnel_id)) return;
      map.set(row.funnel_id, row);
    });
    return map;
  }, [campaignLaunches]);

  // ---- Build context value -----------------------------------------------
  const value = useMemo<CampaignContextValue | undefined>(() => {
    if (!campaign) return undefined;
    return {
      campaignId,
      campaign,
      workspaceName,
      campaignProductLabel,
      campaignProductId,
      campaignProductDetail,
      campaignProductLoading,
      workflows,
      workflowsLoading,
      campaignWorkflows,
      strategyArtifact: strategyArtifact ?? null,
      strategyLoading,
      strategy,
      experimentArtifacts,
      experimentsLoading,
      experimentSpecs,
      assetBriefArtifacts,
      briefsLoading,
      assetBriefs,
      generatedAssetsByBriefId,
      generatedAssetTotal,
      briefsWithGeneratedAssets,
      generatedAssetsLoading,
      latestGeneratedBatchId,
      funnels: funnels as FunnelRecord[],
      funnelsLoading,
      campaignLaunches,
      campaignStrategyV2LaunchesLoading,
      launchByFunnelId,
      deliveryConfig: deliveryConfig ?? null,
      deliveryLoading,
      launchContextReadiness: launchContextReadiness ?? null,
      launchContextReadinessLoading,
      funnelLogs: funnelLogs as CampaignContextValue["funnelLogs"],
      latestFunnelWorkflow,
    };
  }, [
    campaign,
    campaignId,
    workspaceName,
    campaignProductLabel,
    campaignProductId,
    campaignProductDetail,
    campaignProductLoading,
    workflows,
    workflowsLoading,
    campaignWorkflows,
    strategyArtifact,
    strategyLoading,
    strategy,
    experimentArtifacts,
    experimentsLoading,
    experimentSpecs,
    assetBriefArtifacts,
    briefsLoading,
    assetBriefs,
    generatedAssetsByBriefId,
    generatedAssetTotal,
    briefsWithGeneratedAssets,
    generatedAssetsLoading,
    latestGeneratedBatchId,
    funnels,
    funnelsLoading,
    campaignLaunches,
    campaignStrategyV2LaunchesLoading,
    launchByFunnelId,
    deliveryConfig,
    deliveryLoading,
    launchContextReadiness,
    launchContextReadinessLoading,
    funnelLogs,
    latestFunnelWorkflow,
  ]);

  return <CampaignCtx.Provider value={value}>{children}</CampaignCtx.Provider>;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useCampaignContext() {
  const ctx = useContext(CampaignCtx);
  if (!ctx) {
    throw new Error("useCampaignContext must be used within a CampaignProvider");
  }
  return ctx;
}

/**
 * Returns the context or undefined when the campaign data is still loading.
 * Useful in the layout shell where we need to render loading/error states.
 */
export function useCampaignContextOptional() {
  return useContext(CampaignCtx);
}
