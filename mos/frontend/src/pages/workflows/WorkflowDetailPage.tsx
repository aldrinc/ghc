import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { CheckCircle2, Loader2 } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button, buttonClasses } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StatusBadge } from "@/components/StatusBadge";
import { StrategyV2ReviewWorkspace } from "@/components/workflows/StrategyV2ReviewWorkspace";
import { GATE_LABELS, GATE_SEQUENCE } from "@/components/workflows/StrategyGateProgress";
import { StrategyCompleteSummary } from "@/components/workflows/StrategyCompleteSummary";
import { LaunchConfigCard } from "@/components/workflows/LaunchConfigCard";
import { LaunchHubView } from "@/components/workflows/LaunchHubView";
import { useAssets } from "@/api/assets";
import { useClientShopifyStatus } from "@/api/clients";
import { useProduct } from "@/api/products";
import {
  useStopWorkflow,
  useStrategyV2LaunchAdditionalAngle,
  useStrategyV2LaunchAdditionalUms,
  useStrategyV2LaunchAngleCampaign,
  useWorkflowDetail,
  useWorkflowSignal,
  type StrategyV2LaunchActionResponse,
} from "@/api/workflows";
import { useProductContext } from "@/contexts/ProductContext";
import { ASSET_BRIEF_TYPE_OPTIONS, DEFAULT_ASSET_BRIEF_TYPES, type AssetBriefType } from "@/lib/assetBriefTypes";
import type { Asset, ResearchArtifactRef, StrategyV2LaunchRecord, StrategyV2State } from "@/types/common";

const EMPTY_RESEARCH_ARTIFACTS: ResearchArtifactRef[] = [];
const EMPTY_ARTIFACT_LIST: any[] = [];
const EMPTY_LAUNCH_RECORDS: StrategyV2LaunchRecord[] = [];

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatStepLabel(step: string) {
  return step
    .split("_")
    .map((chunk) => (chunk ? chunk[0].toUpperCase() + chunk.slice(1) : chunk))
    .join(" ");
}

function truncate(text?: string, max = 120) {
  if (!text) return "—";
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function isExternalDocUrl(value?: string | null): boolean {
  if (!value) return false;
  return value.startsWith("http://") || value.startsWith("https://");
}

function parseDelimitedValues(value: string): string[] {
  const values = value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
  const seen = new Set<string>();
  return values.filter((item) => {
    if (seen.has(item)) return false;
    seen.add(item);
    return true;
  });
}

function toErrorMessage(error: unknown): string {
  if (typeof error === "string") return error;
  if (error && typeof error === "object" && "message" in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  return "Request failed.";
}

function formatLaunchType(value: string): string {
  if (value === "initial_angle") return "Initial angle";
  if (value === "additional_ums") return "Additional UMS";
  if (value === "additional_angle") return "Additional angle";
  return value;
}

type StrategyV2PendingSignal =
  | "strategy_v2_proceed_research"
  | "strategy_v2_confirm_competitor_assets"
  | "strategy_v2_select_angle"
  | "strategy_v2_select_ump_ums"
  | "strategy_v2_select_offer_winner"
  | "strategy_v2_approve_final_copy";

type StrategyV2Candidate = {
  id: string;
  label: string;
  assetRef?: string;
  raw?: Record<string, unknown>;
};

function resolveStrategyV2PendingSignal(state?: StrategyV2State | null): StrategyV2PendingSignal | null {
  const raw = state?.pending_signal_type || state?.required_signal_type;
  if (
    raw === "strategy_v2_proceed_research" ||
    raw === "strategy_v2_confirm_competitor_assets" ||
    raw === "strategy_v2_select_angle" ||
    raw === "strategy_v2_select_ump_ums" ||
    raw === "strategy_v2_select_offer_winner" ||
    raw === "strategy_v2_approve_final_copy"
  ) {
    return raw;
  }
  return null;
}

export function WorkflowDetailPage() {
  const { workflowId } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch } = useWorkflowDetail(workflowId);
  const workflowSignal = useWorkflowSignal(workflowId);
  const stopWorkflow = useStopWorkflow();
  const launchAngleCampaign = useStrategyV2LaunchAngleCampaign(workflowId);
  const launchAdditionalUms = useStrategyV2LaunchAdditionalUms(workflowId);
  const launchAdditionalAngle = useStrategyV2LaunchAdditionalAngle(workflowId);
  const { product, products, selectProduct } = useProductContext();

  const run = data?.run;
  const runProduct = useMemo(
    () => products.find((item) => item.id === run?.product_id),
    [products, run?.product_id]
  );
  const {
    data: runProductDetail,
    isLoading: isLoadingRunProductDetail,
    isError: hasRunProductDetailError,
    refetch: refetchRunProductDetail,
  } = useProduct(run?.product_id || undefined);
  const researchArtifacts: ResearchArtifactRef[] = useMemo(
    () => (Array.isArray(data?.research_artifacts) ? (data?.research_artifacts as ResearchArtifactRef[]) : EMPTY_RESEARCH_ARTIFACTS),
    [data?.research_artifacts],
  );
  const stepSummaries = (data?.precanon_research?.step_summaries as Record<string, string> | undefined) || {};
  const canonStory = (data?.client_canon?.data?.brand as any)?.story as string | undefined;
  const isOnboarding = run?.kind === "client_onboarding";
  const isCampaignPlanning = run?.kind === "campaign_planning" || run?.kind === "campaign_intent";
  const isCreativeProduction = run?.kind === "creative_production";
  const isStrategyV2 = run?.kind === "strategy_v2";
  const approvalsDisabled = !run || run.status !== "running";
  const strategyV2State = data?.strategy_v2_state || null;
  const strategyV2PendingSignal = resolveStrategyV2PendingSignal(strategyV2State);
  const strategyV2PendingPayload = (strategyV2State?.pending_decision_payload || {}) as Record<string, unknown>;
  const strategyData = (data?.strategy_sheet?.data || {}) as any;
  const channelPlan = (strategyData.channelPlan as any[]) || [];
  const messaging = (strategyData.messaging as any[]) || [];
  const risks = (strategyData.risks as string[]) || [];
  const mitigations = (strategyData.mitigations as string[]) || [];
  const experimentArtifacts = useMemo(
    () => (Array.isArray(data?.experiment_specs) ? (data?.experiment_specs as any[]) : EMPTY_ARTIFACT_LIST),
    [data?.experiment_specs],
  );
  const assetBriefArtifacts = useMemo(
    () => (Array.isArray(data?.asset_briefs) ? (data?.asset_briefs as any[]) : EMPTY_ARTIFACT_LIST),
    [data?.asset_briefs],
  );
  const strategyV2Stage3Data = (data?.strategy_v2_stage3?.data || {}) as Record<string, unknown>;
  const strategyV2OfferData = (data?.strategy_v2_offer?.data || {}) as Record<string, unknown>;
  const strategyV2CopyCanonical = (data?.strategy_v2_copy_canonical || {}) as Record<string, unknown>;
  const strategyV2CopyContextData = (data?.strategy_v2_copy_context?.data || {}) as Record<string, unknown>;
  const strategyV2AwarenessData = (data?.strategy_v2_awareness_angle_matrix?.data || {}) as Record<string, unknown>;
  const strategyV2Launches = useMemo(
    () => (Array.isArray(data?.strategy_v2_launches) ? (data.strategy_v2_launches as StrategyV2LaunchRecord[]) : EMPTY_LAUNCH_RECORDS),
    [data?.strategy_v2_launches],
  );
  const latestLog = data?.logs?.[0];
  const {
    data: shopifyStatus,
    isLoading: isLoadingShopifyStatus,
    refetch: refetchShopifyStatus,
  } = useClientShopifyStatus(run?.client_id || undefined);
  const isShopifyLaunchReady = shopifyStatus?.state === "ready";
  const shopifyLaunchBlockedReason = !run?.client_id
    ? "This workflow run is missing client scope for Shopify validation."
    : isLoadingShopifyStatus
      ? "Checking Shopify connection status for this client."
      : !shopifyStatus
        ? "Shopify status is unavailable for this client."
        : isShopifyLaunchReady
          ? null
          : shopifyStatus.message || `Shopify connection state must be 'ready' (current: ${shopifyStatus.state}).`;

  const hasStrategyV2Copy = useMemo(
    () => Object.keys(strategyV2CopyCanonical).length > 0,
    [strategyV2CopyCanonical],
  );
  const strategyV2LaunchReady =
    isStrategyV2 &&
    run?.status === "completed" &&
    !strategyV2PendingSignal &&
    hasStrategyV2Copy;
  const strategyV2LaunchBlockedReason = !isStrategyV2
    ? "Launch actions are available for Strategy V2 workflows only."
    : !hasStrategyV2Copy
      ? "Launch requires canonical copy output."
      : strategyV2PendingSignal
        ? "Resolve the pending Strategy V2 gate before launching."
        : run?.status !== "completed"
          ? "Launch is available once the Strategy V2 run completes."
          : null;
  const primaryProductAsset = useMemo(() => {
    if (!runProductDetail?.primary_asset_id) return null;
    return (
      runProductDetail.assets.find(
        (asset) => asset.is_primary || asset.id === runProductDetail.primary_asset_id
      ) || null
    );
  }, [runProductDetail]);

  const productImageLaunchState: "ready" | "blocked" | "unknown" = !run?.product_id
    ? "blocked"
    : isLoadingRunProductDetail || hasRunProductDetailError || !runProductDetail
      ? "unknown"
      : !runProductDetail.primary_asset_id
        ? "blocked"
        : !primaryProductAsset
          ? "blocked"
          : primaryProductAsset.asset_kind !== "image"
            ? "blocked"
            : primaryProductAsset.file_status && primaryProductAsset.file_status !== "ready"
              ? "blocked"
              : !primaryProductAsset.public_id
                ? "blocked"
                : "ready";
  const productImageLaunchStatusMessage = !run?.product_id
    ? "This workflow run is missing product scope for primary image validation."
    : isLoadingRunProductDetail
      ? "Checking primary product image status for this product."
      : hasRunProductDetailError || !runProductDetail
        ? "Product details are temporarily unavailable. You can retry now, or launch and let the backend validate the primary image."
        : !runProductDetail.primary_asset_id
          ? "Add a primary product image in product setup before launching."
          : !primaryProductAsset
            ? "The configured primary product image could not be loaded."
            : primaryProductAsset.asset_kind !== "image"
              ? `Primary product asset must be an image before launch (current: ${primaryProductAsset.asset_kind}).`
              : primaryProductAsset.file_status && primaryProductAsset.file_status !== "ready"
                ? `Primary product image must finish processing before launch (current: ${primaryProductAsset.file_status}).`
                : !primaryProductAsset.public_id
                  ? "Primary product image is missing its public asset id and cannot be used for launch."
                  : null;
  const resolvedRunProductTitle = runProduct?.title || runProductDetail?.title || null;

  const strategyV2StateSummaries =
    (strategyV2State?.scored_candidate_summaries || {}) as Record<string, unknown>;
  const additionalAngleOptions = useMemo(() => {
    const raw = strategyV2StateSummaries.angles;
    if (!Array.isArray(raw)) return [] as Array<{ id: string; label: string }>;
    const seen = new Set<string>();
    const rows: Array<{ id: string; label: string }> = [];
    raw.forEach((item, index) => {
      if (!item || typeof item !== "object") return;
      const row = item as Record<string, unknown>;
      const nested = row.angle;
      const angle =
        nested && typeof nested === "object" ? (nested as Record<string, unknown>) : row;
      const id = String(angle.angle_id || row.angle_id || "").trim();
      if (!id || seen.has(id)) return;
      seen.add(id);
      const label = String(angle.angle_name || angle.angle_id || `Angle ${index + 1}`).trim();
      rows.push({ id, label });
    });
    return rows;
  }, [strategyV2StateSummaries.angles]);
  const additionalUmsOptions = useMemo(() => {
    const raw = strategyV2StateSummaries.ump_ums_pairs;
    if (!Array.isArray(raw)) return [] as Array<{ id: string; label: string }>;
    const seen = new Set<string>();
    const rows: Array<{ id: string; label: string }> = [];
    raw.forEach((item, index) => {
      if (!item || typeof item !== "object") return;
      const row = item as Record<string, unknown>;
      const id = String(row.ums_id || "").trim();
      if (!id || seen.has(id)) return;
      seen.add(id);
      const ump = String(row.ump_name || "").trim();
      const ums = String(row.ums_name || "").trim();
      const label = `${ump || "UMP"} / ${ums || id}`.trim() || `UMS ${index + 1}`;
      rows.push({ id, label });
    });
    return rows;
  }, [strategyV2StateSummaries.ump_ums_pairs]);
  const selectedAngleName = String(
    ((strategyV2Stage3Data.selected_angle as Record<string, unknown> | undefined)?.angle_name as string) || "",
  ).trim();

  const experimentSpecs = useMemo(() => {
    const latest = experimentArtifacts?.[0] as any;
    const data = (latest?.data || {}) as any;
    const specs = data.experimentSpecs || data.experiment_specs || [];
    if (!Array.isArray(specs)) return [];
    return specs.filter((spec: any) => spec && typeof spec === "object" && String(spec.id || "").trim());
  }, [experimentArtifacts]);

  const assetBriefs = useMemo(() => {
    const map = new Map<string, any>();
    assetBriefArtifacts.forEach((art: any) => {
      const data = (art?.data || {}) as any;
      const briefs = data.asset_briefs || data.assetBriefs || [];
      if (!Array.isArray(briefs)) return;
      briefs.forEach((brief: any) => {
        if (!brief || typeof brief !== "object") return;
        const id = String(brief.id || "").trim();
        if (!id || map.has(id)) return;
        map.set(id, brief);
      });
    });
    return Array.from(map.values());
  }, [assetBriefArtifacts]);

  const strategyV2Candidates = useMemo<StrategyV2Candidate[]>(() => {
    if (!strategyV2PendingSignal) return [];
    const candidates: StrategyV2Candidate[] = [];
    if (
      strategyV2PendingSignal === "strategy_v2_select_angle" ||
      strategyV2PendingSignal === "strategy_v2_select_ump_ums" ||
      strategyV2PendingSignal === "strategy_v2_select_offer_winner"
    ) {
      const rawCandidates = strategyV2PendingPayload.candidates;
      if (!Array.isArray(rawCandidates)) return [];
      rawCandidates.forEach((row, index) => {
        if (!row || typeof row !== "object") return;
        const candidate = row as Record<string, unknown>;
        let id = "";
        let label = "";
        let rawPayload: Record<string, unknown> = candidate;
        if (strategyV2PendingSignal === "strategy_v2_select_angle") {
          const nestedAngle = candidate.angle;
          const anglePayload =
            nestedAngle && typeof nestedAngle === "object"
              ? (nestedAngle as Record<string, unknown>)
              : candidate;
          id = String(anglePayload.angle_id || candidate.angle_id || "").trim();
          label = String(anglePayload.angle_name || anglePayload.angle_id || `Angle ${index + 1}`).trim();
          rawPayload = anglePayload;
        } else if (strategyV2PendingSignal === "strategy_v2_select_ump_ums") {
          id = String(candidate.pair_id || "").trim();
          const ump = String(candidate.ump_name || "").trim();
          const ums = String(candidate.ums_name || "").trim();
          label = `${ump || "UMP"} / ${ums || "UMS"}`.trim();
        } else {
          id = String(candidate.variant_id || "").trim();
          label = String(candidate.ump || candidate.variant_id || `Variant ${index + 1}`).trim();
        }
        if (!id) return;
        candidates.push({ id, label, raw: rawPayload });
      });
      return candidates;
    }

    if (strategyV2PendingSignal === "strategy_v2_confirm_competitor_assets") {
      const rawCandidates = strategyV2PendingPayload.candidates;
      if (!Array.isArray(rawCandidates)) return [];
      rawCandidates.forEach((row, index) => {
        if (!row || typeof row !== "object") return;
        const candidate = row as Record<string, unknown>;
        const candidateId = String(candidate.candidate_id || "").trim();
        const assetRef = String(candidate.source_ref || "").trim();
        if (!candidateId || !assetRef) return;
        const label = String(
          candidate.competitor_name || candidate.title || candidate.name || assetRef || `Competitor Candidate ${index + 1}`
        ).trim();
        candidates.push({
          id: candidateId,
          label,
          assetRef,
          raw: candidate,
        });
      });
      return candidates;
    }

    if (strategyV2PendingSignal === "strategy_v2_approve_final_copy") {
      const copyArtifactId = String(strategyV2PendingPayload.copy_artifact_id || "").trim();
      if (copyArtifactId) {
        const headline = String(strategyV2PendingPayload.headline || "").trim();
        candidates.push({
          id: copyArtifactId,
          label: headline ? `Copy artifact: ${truncate(headline, 80)}` : `Copy artifact: ${copyArtifactId}`,
          raw: { copy_artifact_id: copyArtifactId },
        });
      }
    }
    return candidates;
  }, [strategyV2PendingPayload, strategyV2PendingSignal]);

  const strategyCandidateIds = useMemo(
    () => strategyV2Candidates.map((candidate) => candidate.id),
    [strategyV2Candidates]
  );

  const [activeTab, setActiveTab] = useState<string>("review");
  const [launchStepUnlocked, setLaunchStepUnlocked] = useState(false);
  const [launchActionError, setLaunchActionError] = useState<string | null>(null);
  const [latestLaunchResponse, setLatestLaunchResponse] = useState<StrategyV2LaunchActionResponse | null>(null);
  const [launchChannelsInput, setLaunchChannelsInput] = useState("");
  const [launchAssetBriefTypes, setLaunchAssetBriefTypes] = useState<AssetBriefType[]>(DEFAULT_ASSET_BRIEF_TYPES);
  const [launchExperimentPolicy, setLaunchExperimentPolicy] = useState("");
  const [additionalUmsCampaignId, setAdditionalUmsCampaignId] = useState("");
  const [additionalUmsLaunchPrefix, setAdditionalUmsLaunchPrefix] = useState("");
  const [additionalUmsChannelsOverrideInput, setAdditionalUmsChannelsOverrideInput] = useState("");
  const [additionalUmsAssetBriefTypesOverride, setAdditionalUmsAssetBriefTypesOverride] = useState<AssetBriefType[]>([]);
  const [selectedAdditionalUmsIds, setSelectedAdditionalUmsIds] = useState<string[]>([]);
  const [selectedAdditionalAngleIds, setSelectedAdditionalAngleIds] = useState<string[]>([]);

  const anyLaunchPending =
    launchAngleCampaign.isPending ||
    launchAdditionalUms.isPending ||
    launchAdditionalAngle.isPending;

  useEffect(() => {
    setSelectedAdditionalUmsIds((prev) =>
      prev.filter((id) => additionalUmsOptions.some((option) => option.id === id)),
    );
  }, [additionalUmsOptions]);

  useEffect(() => {
    setSelectedAdditionalAngleIds((prev) =>
      prev.filter((id) => additionalAngleOptions.some((option) => option.id === id)),
    );
  }, [additionalAngleOptions]);

  useEffect(() => {
    if (additionalUmsCampaignId.trim()) return;
    const latestCampaignLaunch = strategyV2Launches.find(
      (row) => row.campaign_id && (row.launch_type === "initial_angle" || row.launch_type === "additional_angle"),
    );
    if (!latestCampaignLaunch?.campaign_id) return;
    setAdditionalUmsCampaignId(latestCampaignLaunch.campaign_id);
  }, [additionalUmsCampaignId, strategyV2Launches]);

  const [selectedExperimentIds, setSelectedExperimentIds] = useState<string[]>([]);
  useEffect(() => {
    setSelectedExperimentIds((prev) => {
      if (!prev.length) return prev;
      const allowed = new Set(
        experimentSpecs
          .map((spec: any) => String(spec?.id || "").trim())
          .filter(Boolean),
      );
      if (!allowed.size) return prev.length ? [] : prev;
      const next = prev.filter((id) => allowed.has(id));
      if (next.length === prev.length && next.every((id, index) => id === prev[index])) {
        return prev;
      }
      return next;
    });
  }, [experimentSpecs]);

  const allExperimentIds = useMemo(
    () => experimentSpecs.map((spec: any) => String(spec.id || "")).filter(Boolean),
    [experimentSpecs]
  );
  const allExperimentsSelected =
    allExperimentIds.length > 0 && allExperimentIds.every((id) => selectedExperimentIds.includes(id));
  const toggleExperimentSelection = (id: string) => {
    setSelectedExperimentIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  };
  const toggleAllExperiments = () => {
    setSelectedExperimentIds(allExperimentsSelected ? [] : allExperimentIds);
  };

  const generatedAssetIds = useMemo(() => {
    const ids = new Set<string>();
    (data?.logs || []).forEach((log) => {
      if (log.step !== "asset_generation" || log.status !== "completed") return;
      const out = log.payload_out as any;
      const assetIds = out?.asset_ids;
      if (!Array.isArray(assetIds)) return;
      assetIds.forEach((id: any) => {
        if (typeof id === "string" && id.trim()) ids.add(id.trim());
      });
    });
    return Array.from(ids);
  }, [data?.logs]);

  const { data: assets = [] } = useAssets(
    { campaignId: run?.campaign_id || undefined },
    { enabled: Boolean(isCreativeProduction && run?.campaign_id && generatedAssetIds.length) }
  );
  const generatedAssets: Asset[] = useMemo(() => {
    if (!generatedAssetIds.length) return [];
    const idSet = new Set(generatedAssetIds);
    return (assets || []).filter((asset) => idSet.has(asset.id));
  }, [assets, generatedAssetIds]);

  const [approvedAssetIds, setApprovedAssetIds] = useState<Set<string>>(new Set());
  const [rejectedAssetIds, setRejectedAssetIds] = useState<Set<string>>(new Set());

  const toggleApprovedAsset = (id: string) => {
    setApprovedAssetIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setRejectedAssetIds((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  };

  const toggleRejectedAsset = (id: string) => {
    setRejectedAssetIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setApprovedAssetIds((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  };

  useEffect(() => {
    if (!run || run.status !== "running") return;
    const interval = window.setInterval(() => {
      void refetch();
    }, 15000);
    return () => window.clearInterval(interval);
  }, [run?.status, refetch]);

  useEffect(() => {
    if (!isStrategyV2) return;
    if (strategyV2PendingSignal) {
      setActiveTab("review");
    } else if (strategyV2LaunchReady) {
      setActiveTab("launch");
    }
  }, [isStrategyV2, strategyV2PendingSignal, strategyV2LaunchReady]);
  const handleApproveExperiments = () => {
    workflowSignal.mutate({
      signal: "approve-experiments",
      body: { approved_ids: selectedExperimentIds, rejected_ids: [] },
    });
  };

  const handleApproveAssets = () => {
    workflowSignal.mutate({
      signal: "approve-assets",
      body: {
        approved_ids: Array.from(approvedAssetIds),
        rejected_ids: Array.from(rejectedAssetIds),
      },
    });
  };
  const handleStrategyV2SubmitSignal = (signal: string, body: Record<string, unknown>) => {
    workflowSignal.mutate({ signal, body });
  };
  const handleStopWorkflow = () => {
    if (!run?.id || stopWorkflow.isPending) return;
    stopWorkflow.mutate(run.id);
  };

  const toggleAdditionalUmsSelection = (id: string) => {
    setSelectedAdditionalUmsIds((prev) => (prev.includes(id) ? prev.filter((row) => row !== id) : [...prev, id]));
  };

  const toggleAdditionalAngleSelection = (id: string) => {
    setSelectedAdditionalAngleIds((prev) => (prev.includes(id) ? prev.filter((row) => row !== id) : [...prev, id]));
  };

  const toggleLaunchAssetBriefType = (value: AssetBriefType) => {
    setLaunchAssetBriefTypes((prev) =>
      prev.includes(value) ? prev.filter((item) => item !== value) : [...prev, value]
    );
  };

  const toggleAdditionalUmsAssetBriefTypeOverride = (value: AssetBriefType) => {
    setAdditionalUmsAssetBriefTypesOverride((prev) =>
      prev.includes(value) ? prev.filter((item) => item !== value) : [...prev, value]
    );
  };

  const handleLaunchAngleCampaign = async () => {
    setLaunchActionError(null);
    if (!isShopifyLaunchReady) {
      setLaunchActionError(shopifyLaunchBlockedReason || "Shopify connection must be ready before launch.");
      return;
    }
    const channels = parseDelimitedValues(launchChannelsInput);
    const assetBriefTypes = launchAssetBriefTypes;
    const experimentVariantPolicy = launchExperimentPolicy.trim();
    if (!channels.length) {
      setLaunchActionError("channels must include at least one non-empty value.");
      return;
    }
    if (!assetBriefTypes.length) {
      setLaunchActionError("Select at least one supported assetBriefType.");
      return;
    }
    if (!experimentVariantPolicy) {
      setLaunchActionError("experimentVariantPolicy is required.");
      return;
    }
    try {
      const response = await launchAngleCampaign.mutateAsync({
        channels,
        assetBriefTypes,
        experimentVariantPolicy,
      });
      setLatestLaunchResponse(response);
    } catch (error) {
      setLaunchActionError(toErrorMessage(error));
    }
  };

  const handleLaunchAdditionalUms = async () => {
    setLaunchActionError(null);
    if (!isShopifyLaunchReady) {
      setLaunchActionError(shopifyLaunchBlockedReason || "Shopify connection must be ready before launch.");
      return;
    }
    const campaignId = additionalUmsCampaignId.trim();
    const launchNamePrefix = additionalUmsLaunchPrefix.trim();
    if (!campaignId) {
      setLaunchActionError("campaignId is required for additional UMS launch.");
      return;
    }
    if (!selectedAdditionalUmsIds.length) {
      setLaunchActionError("Select at least one UMS id for additional UMS launch.");
      return;
    }
    if (!launchNamePrefix) {
      setLaunchActionError("launchNamePrefix is required for additional UMS launch.");
      return;
    }
    const channelsOverride = parseDelimitedValues(additionalUmsChannelsOverrideInput);
    const assetBriefTypesOverride = additionalUmsAssetBriefTypesOverride;
    try {
      const response = await launchAdditionalUms.mutateAsync({
        campaignId,
        umsSelectionIds: selectedAdditionalUmsIds,
        launchNamePrefix,
        ...(channelsOverride.length ? { channels: channelsOverride } : {}),
        ...(assetBriefTypesOverride.length ? { assetBriefTypes: assetBriefTypesOverride } : {}),
      });
      setLatestLaunchResponse(response);
    } catch (error) {
      setLaunchActionError(toErrorMessage(error));
    }
  };

  const handleLaunchAdditionalAngle = async () => {
    setLaunchActionError(null);
    if (!isShopifyLaunchReady) {
      setLaunchActionError(shopifyLaunchBlockedReason || "Shopify connection must be ready before launch.");
      return;
    }
    const channels = parseDelimitedValues(launchChannelsInput);
    const assetBriefTypes = launchAssetBriefTypes;
    if (!channels.length) {
      setLaunchActionError("channels must include at least one non-empty value.");
      return;
    }
    if (!assetBriefTypes.length) {
      setLaunchActionError("Select at least one supported assetBriefType.");
      return;
    }
    if (!selectedAdditionalAngleIds.length) {
      setLaunchActionError("Select at least one angle id for additional angle launch.");
      return;
    }
    try {
      const response = await launchAdditionalAngle.mutateAsync({
        selectedAngleIds: selectedAdditionalAngleIds,
        channels,
        assetBriefTypes,
      });
      setLatestLaunchResponse(response);
    } catch (error) {
      setLaunchActionError(toErrorMessage(error));
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title={
          isStrategyV2
            ? strategyV2LaunchReady
              ? strategyV2Launches.length
                ? "Strategy Hub"
                : "Strategy Complete"
              : "Strategy Review"
            : "Workflow detail"
        }
        description={
          isStrategyV2
            ? strategyV2LaunchReady
              ? strategyV2Launches.length
                ? `${strategyV2Launches.length} campaign${strategyV2Launches.length === 1 ? "" : "s"} launched. Launch more angles or iterations.`
                : "All decisions made. Ready to launch."
              : strategyV2PendingSignal
                ? `Gate ${GATE_SEQUENCE.indexOf(strategyV2PendingSignal) + 1} of 6: ${GATE_LABELS[strategyV2PendingSignal]}`
                : "Processing \u2014 we'll pause when a decision is needed."
            : resolvedRunProductTitle
              ? `Inspect research artifacts for ${resolvedRunProductTitle}.`
              : "Inspect research artifacts and unblock any required gates."
        }
        actions={
          <Menu>
            <MenuTrigger className={buttonClasses({ variant: "secondary", size: "sm" })}>Actions</MenuTrigger>
            <MenuContent>
              <MenuItem onClick={() => navigate("/strategy")}>Open all strategy runs</MenuItem>
              <MenuItem onClick={() => void refetch()}>Refresh now</MenuItem>
              {run?.id ? <MenuItem onClick={() => navigator.clipboard.writeText(run.id)}>Copy workflow ID</MenuItem> : null}
              {run?.status === "running" ? (
                <MenuItem onClick={handleStopWorkflow}>
                  {stopWorkflow.isPending ? "Stopping workflow…" : "Stop workflow"}
                </MenuItem>
              ) : null}
            </MenuContent>
          </Menu>
        }
      />

      {isLoading ? (
        <div className="ds-card ds-card--md text-sm text-content-muted shadow-none">Loading workflow…</div>
      ) : isError || !run ? (
        <div className="ds-card ds-card--md text-sm text-danger shadow-none">
          Workflow not found or failed to load.
        </div>
      ) : (
        <div className="space-y-4">
          {run.status === "running" ? (
            <Callout
              variant="warning"
              title="Workflow running"
              icon={<Loader2 className="h-4 w-4 animate-spin" />}
              actions={<span className="text-xs text-content-muted">Auto-refreshing every 15s</span>}
            >
              {latestLog ? (
                <>
                  Latest activity: {formatStepLabel(latestLog.step)} ({latestLog.status}) |{" "}
                  {formatDate(latestLog.created_at)}
                </>
              ) : (
                <>Waiting for the first activity update...</>
              )}
            </Callout>
          ) : null}
          {run?.product_id && product?.id && run.product_id !== product.id ? (
            <Callout
              variant="warning"
              title="This workflow is scoped to a different product"
              actions={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    selectProduct(run.product_id || "", {
                      title: resolvedRunProductTitle || undefined,
                      client_id: run.client_id || undefined,
                    })
                  }
                >
                  Switch product
                </Button>
              }
            >
              <>
                This workflow is scoped to{" "}
                <span className="font-semibold text-content">{resolvedRunProductTitle || run.product_id}</span>. Switch product
                to review artifacts in context.
              </>
            </Callout>
          ) : null}
          {isStrategyV2 ? (
            <>
              <Tabs value={activeTab} onValueChange={setActiveTab}>
                <TabsList>
                  <TabsTrigger value="review">Review</TabsTrigger>
                  <TabsTrigger value="outputs">Outputs</TabsTrigger>
                  <TabsTrigger value="launch" disabled={!strategyV2LaunchReady && run?.status !== "completed"}>
                    Launch {strategyV2LaunchReady ? "" : `(${6 - (GATE_SEQUENCE.indexOf(strategyV2PendingSignal!) + 1 || 0)} gates left)`}
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="review">
                  {strategyV2LaunchReady && run?.status === "completed" ? (
                    <StrategyCompleteSummary
                      selectedAngleName={selectedAngleName}
                      selectedUmpName={String(strategyV2Stage3Data.ump || "")}
                      selectedUmsName={String(strategyV2Stage3Data.ums || "")}
                      selectedVariantName={String(strategyV2OfferData.variant_selected || "")}
                      copyApproved={hasStrategyV2Copy}
                      onLaunchClick={() => setActiveTab("launch")}
                      hasLaunches={strategyV2Launches.length > 0}
                    />
                  ) : null}
                  <StrategyV2ReviewWorkspace
                    workflowId={workflowId}
                    runStatus={run.status}
                    pendingSignal={strategyV2PendingSignal}
                    pendingPayload={strategyV2PendingPayload}
                    strategyState={strategyV2State}
                    candidates={strategyV2Candidates}
                    candidateIds={strategyCandidateIds}
                    researchArtifacts={researchArtifacts}
                    stepSummaries={stepSummaries}
                    logs={data?.logs || []}
                    disabled={approvalsDisabled}
                    isSubmitting={workflowSignal.isPending}
                    onSubmitSignal={handleStrategyV2SubmitSignal}
                  />
                </TabsContent>

                <TabsContent value="outputs">
                  <div className="space-y-4">
                    <div className="ds-card ds-card--md p-0 shadow-none">
                      <div className="flex items-center justify-between border-b border-border px-4 py-3">
                        <div>
                          <div className="text-sm font-semibold text-content">Strategy V2 outputs</div>
                          <div className="text-xs text-content-muted">Canonical stage, offer, copy, and context artifacts.</div>
                        </div>
                      </div>
                      <div className="grid gap-3 p-4 md:grid-cols-2 text-xs text-content">
                        <div className="ds-card ds-card--sm bg-surface-2">
                          <div className="font-semibold text-content">Stage 3</div>
                          <div className="mt-1 text-content-muted">
                            Angle: {String((strategyV2Stage3Data.selected_angle as any)?.angle_name || "—")}
                          </div>
                          <div className="text-content-muted">UMP: {String(strategyV2Stage3Data.ump || "—")}</div>
                          <div className="text-content-muted">UMS: {String(strategyV2Stage3Data.ums || "—")}</div>
                        </div>
                        <div className="ds-card ds-card--sm bg-surface-2">
                          <div className="font-semibold text-content">Offer</div>
                          <div className="mt-1 text-content-muted">
                            Winner: {String((strategyV2OfferData.variant_selected as string) || "—")}
                          </div>
                          <div className="text-content-muted">
                            Composite score: {String(strategyV2OfferData.composite_score || "—")}
                          </div>
                          <div className="text-content-muted">
                            Guarantee: {String(strategyV2OfferData.guarantee_type || "—")}
                          </div>
                        </div>
                        <div className="ds-card ds-card--sm bg-surface-2 md:col-span-2">
                          <div className="font-semibold text-content">Copy (canonical)</div>
                          <div className="mt-1 text-content-muted">
                            Headline: {String(strategyV2CopyCanonical.headline || "—")}
                          </div>
                          <div className="text-content-muted">
                            Presell length: {String(String(strategyV2CopyCanonical.presell_markdown || "").length || 0)} chars
                          </div>
                          <div className="text-content-muted">
                            Sales length: {String(String(strategyV2CopyCanonical.sales_page_markdown || "").length || 0)} chars
                          </div>
                        </div>
                        <div className="ds-card ds-card--sm bg-surface-2">
                          <div className="font-semibold text-content">Awareness matrix</div>
                          <div className="mt-1 text-content-muted">
                            Angle name: {String(strategyV2AwarenessData.angle_name || "—")}
                          </div>
                        </div>
                        <div className="ds-card ds-card--sm bg-surface-2">
                          <div className="font-semibold text-content">Copy context</div>
                          <div className="mt-1 text-content-muted">
                            Context keys: {Object.keys(strategyV2CopyContextData || {}).length}
                          </div>
                        </div>
                      </div>
                    </div>

                    {researchArtifacts?.length ? (
                      <div className="ds-card ds-card--md p-0 shadow-none">
                        <div className="flex items-center justify-between border-b border-border px-4 py-3">
                          <div>
                            <div className="text-sm font-semibold text-content">Workflow research artifacts</div>
                            <div className="text-xs text-content-muted">Read summaries inline and open the persisted workflow file.</div>
                          </div>
                        </div>
                        <div className="overflow-x-auto">
                          <Table variant="ghost">
                            <TableHeader>
                              <TableRow>
                                <TableHeadCell>Step</TableHeadCell>
                                <TableHeadCell>Summary</TableHeadCell>
                                <TableHeadCell>Document</TableHeadCell>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {researchArtifacts.map((art) => {
                                const summary = art.summary || stepSummaries[art.step_key];
                                return (
                                  <TableRow key={art.doc_id}>
                                    <TableCell className="font-semibold text-content">Step {art.step_key}</TableCell>
                                    <TableCell className="text-sm text-content-muted">{truncate(summary, 120)}</TableCell>
                                    <TableCell className="text-right space-x-2">
                                      <Link to={`/strategy/${workflowId}/research/${art.step_key}`} className="text-sm">
                                        <Button variant="secondary" size="xs">View</Button>
                                      </Link>
                                      {isExternalDocUrl(art.doc_url) ? (
                                        <a href={art.doc_url} target="_blank" rel="noreferrer" className="text-primary underline text-xs">
                                          Open doc
                                        </a>
                                      ) : null}
                                    </TableCell>
                                  </TableRow>
                                );
                              })}
                            </TableBody>
                          </Table>
                        </div>
                      </div>
                    ) : null}
                  </div>
                </TabsContent>

                <TabsContent value="launch">
                  <div className="space-y-4">
                    {!strategyV2Launches.length ? (
                      <LaunchConfigCard
                        selectedAngleName={selectedAngleName}
                        isShopifyReady={isShopifyLaunchReady}
                        shopifyBlockedReason={shopifyLaunchBlockedReason}
                        productImageState={productImageLaunchState}
                        productImageStatusMessage={productImageLaunchStatusMessage}
                        isLaunching={anyLaunchPending}
                        onLaunch={async (config) => {
                          setLaunchActionError(null);
                          if (!isShopifyLaunchReady || productImageLaunchState === "blocked") {
                            setLaunchActionError(
                              shopifyLaunchBlockedReason ||
                                productImageLaunchStatusMessage ||
                                "Launch prerequisites are not satisfied."
                            );
                            return;
                          }
                          try {
                            const response = await launchAngleCampaign.mutateAsync(config);
                            setLatestLaunchResponse(response);
                          } catch (error) {
                            setLaunchActionError(toErrorMessage(error));
                          }
                        }}
                        onRefreshShopify={() => void refetchShopifyStatus()}
                        isLoadingShopify={isLoadingShopifyStatus}
                        onRefreshProductImage={() => void refetchRunProductDetail()}
                        isLoadingProductImage={isLoadingRunProductDetail}
                        productId={run?.product_id || undefined}
                        latestLaunchResponse={latestLaunchResponse}
                        launchError={launchActionError}
                      />
                    ) : (
                      <LaunchHubView
                        launches={strategyV2Launches}
                        angleOptions={additionalAngleOptions}
                        launchedAngleIds={new Set(strategyV2Launches.filter((l) => l.launch_type === "initial_angle" || l.launch_type === "additional_angle").map((l) => l.angle_id))}
                        umsOptions={additionalUmsOptions}
                        launchedUmsIds={new Set(strategyV2Launches.filter((l) => l.launch_type === "additional_ums" && l.selected_ums_id).map((l) => l.selected_ums_id!))}
                        defaultCampaignId={additionalUmsCampaignId}
                        isShopifyReady={isShopifyLaunchReady}
                        shopifyBlockedReason={shopifyLaunchBlockedReason}
                        productImageState={productImageLaunchState}
                        productImageStatusMessage={productImageLaunchStatusMessage}
                        onRefreshProductImage={() => void refetchRunProductDetail()}
                        isLoadingProductImage={isLoadingRunProductDetail}
                        productId={run?.product_id || undefined}
                        onLaunchAdditionalAngles={async (config) => {
                          setLaunchActionError(null);
                          if (!isShopifyLaunchReady || productImageLaunchState === "blocked") {
                            setLaunchActionError(
                              shopifyLaunchBlockedReason ||
                                productImageLaunchStatusMessage ||
                                "Launch prerequisites are not satisfied."
                            );
                            return;
                          }
                          try {
                            const response = await launchAdditionalAngle.mutateAsync({
                              selectedAngleIds: config.selectedAngleIds,
                              channels: config.channels,
                              assetBriefTypes: config.assetBriefTypes,
                            });
                            setLatestLaunchResponse(response);
                          } catch (error) {
                            setLaunchActionError(toErrorMessage(error));
                          }
                        }}
                        onLaunchAdditionalUms={async (config) => {
                          setLaunchActionError(null);
                          if (!isShopifyLaunchReady || productImageLaunchState === "blocked") {
                            setLaunchActionError(
                              shopifyLaunchBlockedReason ||
                                productImageLaunchStatusMessage ||
                                "Launch prerequisites are not satisfied."
                            );
                            return;
                          }
                          try {
                            const response = await launchAdditionalUms.mutateAsync(config);
                            setLatestLaunchResponse(response);
                          } catch (error) {
                            setLaunchActionError(toErrorMessage(error));
                          }
                        }}
                        isLaunching={anyLaunchPending}
                        launchError={launchActionError}
                        latestLaunchResponse={latestLaunchResponse}
                      />
                    )}
                  </div>
                </TabsContent>
              </Tabs>

              <details className="ds-card ds-card--md shadow-none">
                <summary className="text-sm font-semibold text-content cursor-pointer">
                  Run details
                </summary>
                <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-content">
                  <div>
                    <div className="text-content-muted">Status</div>
                    <div className="font-semibold"><StatusBadge status={run.status} /></div>
                  </div>
                  <div>
                    <div className="text-content-muted">ID</div>
                    <div className="font-mono text-[11px] text-content-muted">{run.id}</div>
                  </div>
                  <div>
                    <div className="text-content-muted">Kind</div>
                    <div className="font-semibold">{run.kind}</div>
                  </div>
                  <div>
                    <div className="text-content-muted">Workspace</div>
                    <div className="font-mono text-[11px] text-content-muted">{run.client_id || "—"}</div>
                  </div>
                  <div>
                    <div className="text-content-muted">Product</div>
                    <div className="font-mono text-[11px] text-content-muted">
                      {resolvedRunProductTitle || run.product_id || "—"}
                    </div>
                  </div>
                  <div>
                    <div className="text-content-muted">Started</div>
                    <div>{formatDate(run.started_at)}</div>
                  </div>
                  <div>
                    <div className="text-content-muted">Finished</div>
                    <div>{run.finished_at ? formatDate(run.finished_at) : "—"}</div>
                  </div>
                </div>
                {canonStory ? (
                  <div className="mt-3 ds-card ds-card--sm bg-surface-2 text-xs">
                    <div className="mb-1 font-semibold text-content">Canon story</div>
                    <p className="text-content-muted">{truncate(canonStory, 220)}</p>
                  </div>
                ) : null}
              </details>
            </>
          ) : (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="ds-card ds-card--md shadow-none">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm font-semibold text-content">Run overview</div>
                      <div className="text-xs text-content-muted">ID: <span className="font-mono">{run.id}</span></div>
                    </div>
                    <StatusBadge status={run.status} />
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-content">
                    <div>
                      <div className="text-content-muted">Kind</div>
                      <div className="font-semibold">{run.kind}</div>
                    </div>
                    <div>
                      <div className="text-content-muted">Workspace</div>
                      <div className="font-mono text-[11px] text-content-muted">{run.client_id || "—"}</div>
                    </div>
                    <div>
                      <div className="text-content-muted">Product</div>
                      <div className="font-mono text-[11px] text-content-muted">
                        {resolvedRunProductTitle || run.product_id || "—"}
                      </div>
                    </div>
                    <div>
                      <div className="text-content-muted">Started</div>
                      <div>{formatDate(run.started_at)}</div>
                    </div>
                    <div>
                      <div className="text-content-muted">Finished</div>
                      <div>{run.finished_at ? formatDate(run.finished_at) : "—"}</div>
                    </div>
                  </div>
                  {canonStory ? (
                    <div className="mt-3 ds-card ds-card--sm bg-surface-2 text-xs">
                      <div className="mb-1 font-semibold text-content">Canon story</div>
                      <p className="text-content-muted">{truncate(canonStory, 220)}</p>
                    </div>
                  ) : null}
                </div>

                <div className="ds-card ds-card--md shadow-none">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm font-semibold text-content">Review & gates</div>
                      <div className="text-xs text-content-muted">
                        {isOnboarding
                          ? "Onboarding is automatic and does not require approvals."
                          : isCreativeProduction
                            ? "Creative production waits for asset approvals."
                            : isCampaignPlanning
                              ? "Campaign planning waits for experiment approvals."
                              : "This workflow type has no manual gates."}
                      </div>
                    </div>
                  </div>
                  {isOnboarding ? (
                    <div className="mt-3 ds-card ds-card--sm bg-surface-2 text-xs text-content-muted">
                      No action required. This run will proceed automatically as activities complete.
                    </div>
                  ) : isCampaignPlanning ? (
                    <div className="mt-3 space-y-3 text-sm">
                      {experimentSpecs.length ? (
                        <>
                          <div className="flex flex-wrap items-center gap-4 text-xs text-content-muted">
                            <label className="flex items-center gap-2">
                              <input
                                type="checkbox"
                                className="h-4 w-4 rounded border border-border bg-surface text-accent"
                                checked={allExperimentsSelected}
                                onChange={toggleAllExperiments}
                              />
                              <span>Select all</span>
                            </label>
                            <span>{selectedExperimentIds.length} selected</span>
                          </div>
                          <Button
                            variant="primary"
                            size="sm"
                            onClick={handleApproveExperiments}
                            disabled={approvalsDisabled || workflowSignal.isPending || selectedExperimentIds.length === 0}
                          >
                            {workflowSignal.isPending ? "Sending…" : "Approve selected experiments"}
                          </Button>
                        </>
                      ) : (
                        <div className="ds-card ds-card--sm bg-surface-2 text-xs text-content-muted">
                          No experiment specs available yet.
                        </div>
                      )}
                      {approvalsDisabled ? (
                        <div className="text-xs text-content-muted">Approvals disabled because the run is not active.</div>
                      ) : null}
                    </div>
                  ) : isCreativeProduction ? (
                    <div className="mt-3 space-y-2 text-sm">
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={handleApproveAssets}
                        disabled={
                          approvalsDisabled ||
                          workflowSignal.isPending ||
                          (approvedAssetIds.size === 0 && rejectedAssetIds.size === 0)
                        }
                      >
                        {workflowSignal.isPending ? "Sending…" : "Send asset approvals"}
                      </Button>
                      <div className="text-xs text-content-muted">
                        {approvedAssetIds.size} approved · {rejectedAssetIds.size} rejected
                      </div>
                    </div>
                  ) : (
                    <div className="mt-3 ds-card ds-card--sm bg-surface-2 text-xs text-content-muted">
                      This workflow type has no manual gates.
                    </div>
                  )}
                </div>
              </div>

              {data?.pending_activity_progress?.length ? (
                <div className="ds-card ds-card--md p-0 shadow-none">
                  <div className="flex items-center justify-between border-b border-border px-4 py-3">
                    <div>
                      <div className="text-sm font-semibold text-content">Pending activity progress</div>
                      <div className="text-xs text-content-muted">Temporal heartbeat snapshots for active activities.</div>
                    </div>
                  </div>
                  <div className="space-y-2 p-4 text-xs text-content">
                    {data.pending_activity_progress.map((row) => (
                      <div key={`${row.activity_id}-${row.attempt || 0}`} className="ds-card ds-card--sm bg-surface-2">
                        <div className="font-semibold text-content">{row.activity_type || row.activity_id}</div>
                        <div className="mt-1 text-content-muted">
                          State: {row.state || "—"} · Attempt: {row.attempt || 0} · Last heartbeat:{" "}
                          {formatDate(row.last_heartbeat_time || null)}
                        </div>
                        {row.heartbeat_progress ? (
                          <div className="mt-1 text-content-muted">
                            Heartbeat: {truncate(JSON.stringify(row.heartbeat_progress), 200)}
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {researchArtifacts?.length ? (
                <div className="ds-card ds-card--md p-0 shadow-none">
                  <div className="flex items-center justify-between border-b border-border px-4 py-3">
                    <div>
                      <div className="text-sm font-semibold text-content">Workflow research artifacts</div>
                      <div className="text-xs text-content-muted">Read summaries inline and open the persisted workflow file.</div>
                    </div>
                  </div>
                  <div className="overflow-x-auto">
                    <Table variant="ghost">
                      <TableHeader>
                        <TableRow>
                          <TableHeadCell>Step</TableHeadCell>
                          <TableHeadCell>Summary</TableHeadCell>
                          <TableHeadCell>Document</TableHeadCell>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {researchArtifacts.map((art) => {
                          const summary = art.summary || stepSummaries[art.step_key];
                          return (
                            <TableRow key={art.doc_id}>
                              <TableCell className="font-semibold text-content">Step {art.step_key}</TableCell>
                              <TableCell className="text-sm text-content-muted">{truncate(summary, 120)}</TableCell>
                              <TableCell className="text-right space-x-2">
                                <Link to={`/strategy/${workflowId}/research/${art.step_key}`} className="text-sm">
                                  <Button variant="secondary" size="xs">View</Button>
                                </Link>
                                {isExternalDocUrl(art.doc_url) ? (
                                  <a href={art.doc_url} target="_blank" rel="noreferrer" className="text-primary underline text-xs">
                                    Open doc
                                  </a>
                                ) : null}
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              ) : null}
            </>
          )}

          {isCampaignPlanning && experimentSpecs.length ? (
            <div className="ds-card ds-card--md p-0 shadow-none">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <div>
                  <div className="text-sm font-semibold text-content">Angle specs</div>
                  <div className="text-xs text-content-muted">Generated from canon and metric schema.</div>
                </div>
              </div>
              <div className="space-y-3 p-4 text-sm">
                {experimentSpecs.map((exp: any) => {
                  const id = String(exp.id || "").trim();
                  if (!id) return null;
                  const isSelected = selectedExperimentIds.includes(id);
                  return (
                    <div key={id} className="ds-card ds-card--sm bg-surface-2">
                      <div className="flex items-start justify-between gap-3">
                        <label className="flex items-start gap-3">
                          <input
                            type="checkbox"
                            className="mt-0.5 h-4 w-4 rounded border border-border bg-surface text-accent"
                            checked={isSelected}
                            onChange={() => toggleExperimentSelection(id)}
                          />
                          <div>
                            <div className="text-sm font-semibold text-content">{exp.name || id}</div>
                            <div className="mt-1 text-xs text-content-muted">{truncate(exp.hypothesis, 200)}</div>
                            <div className="mt-2 text-xs text-content-muted">
                              Metrics: {(exp.metricIds || []).join(", ") || "—"} · Variants:{" "}
                              {(exp.variants || []).length}
                            </div>
                          </div>
                        </label>
                        <span className="text-xs text-content-muted font-mono">{id}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}

          {isCampaignPlanning && assetBriefs.length ? (
            <div className="ds-card ds-card--md p-0 shadow-none">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <div>
                  <div className="text-sm font-semibold text-content">Creative briefs</div>
                  <div className="text-xs text-content-muted">Derived from angle variants.</div>
                </div>
              </div>
              <div className="space-y-3 p-4 text-sm">
                {assetBriefs.map((brief: any) => {
                  const requirements = Array.isArray(brief.requirements) ? brief.requirements : [];
                  return (
                    <div key={brief.id} className="ds-card ds-card--sm bg-surface-2">
                      <div className="flex items-center justify-between">
                        <div className="text-sm font-semibold text-content">{brief.creativeConcept || brief.id}</div>
                        <span className="text-xs text-content-muted font-mono">{brief.id}</span>
                      </div>
                      <div className="mt-1 text-xs text-content-muted">
                        Angle: {brief.experimentId || "—"} · Requirements: {requirements.length}
                      </div>
                      {requirements.length ? (
                        <div className="mt-2 text-xs text-content-muted">
                          {requirements.map((r: any, idx: number) => (
                            <div key={idx}>
                              • {r.channel} / {r.format} {r.angle ? `– ${r.angle}` : ""}{" "}
                              {r.hook ? `(${truncate(r.hook, 60)})` : ""}
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}

          {isCreativeProduction ? (
            <div className="ds-card ds-card--md p-0 shadow-none">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <div>
                  <div className="text-sm font-semibold text-content">Generated assets</div>
                  <div className="text-xs text-content-muted">Approve or reject to finish creative production.</div>
                </div>
              </div>
              <div className="p-4">
                {generatedAssets.length ? (
                  <div className="space-y-3">
                    {generatedAssets.map((asset) => (
                      <div key={asset.id} className="ds-card ds-card--sm bg-surface-2">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="flex items-start gap-3">
                            <img
                              src={`/public/assets/${asset.public_id}`}
                              alt={asset.id}
                              className="h-20 w-20 rounded-md object-cover border border-border"
                              loading="lazy"
                            />
                            <div className="min-w-0">
                              <div className="text-sm font-semibold text-content">Asset</div>
                              <div className="mt-1 text-xs text-content-muted font-mono break-all">{asset.id}</div>
                              <div className="mt-2 text-xs text-content-muted">Status: {asset.status}</div>
                            </div>
                          </div>
                          <div className="flex items-center gap-4 text-xs text-content">
                            <label className="flex items-center gap-2">
                              <input
                                type="checkbox"
                                className="h-4 w-4 rounded border border-border bg-surface text-accent"
                                checked={approvedAssetIds.has(asset.id)}
                                onChange={() => toggleApprovedAsset(asset.id)}
                              />
                              <span>Approve</span>
                            </label>
                            <label className="flex items-center gap-2">
                              <input
                                type="checkbox"
                                className="h-4 w-4 rounded border border-border bg-surface text-accent"
                                checked={rejectedAssetIds.has(asset.id)}
                                onChange={() => toggleRejectedAsset(asset.id)}
                              />
                              <span>Reject</span>
                            </label>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : generatedAssetIds.length ? (
                  <div className="text-sm text-content-muted">Loading generated assets…</div>
                ) : (
                  <div className="text-sm text-content-muted">
                    No generated assets recorded yet. Wait for asset generation steps to complete.
                  </div>
                )}
              </div>
            </div>
          ) : null}

          {isCampaignPlanning ? (
            <div className="ds-card ds-card--md p-0 shadow-none">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <div>
                  <div className="text-sm font-semibold text-content">Strategy sheet</div>
                  <div className="text-xs text-content-muted">Goal, hypothesis, channel plan, and messaging.</div>
                </div>
              </div>
              <div className="space-y-3 p-4 text-sm text-content">
                <div>
                  <div className="text-xs font-semibold text-content-muted uppercase">Goal</div>
                  <div>{truncate(strategyData.goal || "—", 240)}</div>
                </div>
                <div>
                  <div className="text-xs font-semibold text-content-muted uppercase">Hypothesis</div>
                  <div>{truncate(strategyData.hypothesis || "—", 240)}</div>
                </div>
                <div>
                  <div className="text-xs font-semibold text-content-muted uppercase mb-1">Channel plan</div>
                  {channelPlan.length ? (
                    <Table variant="ghost">
                      <TableHeader>
                        <TableRow>
                          <TableHeadCell>Channel</TableHeadCell>
                          <TableHeadCell>Objective</TableHeadCell>
                          <TableHeadCell>Budget %</TableHeadCell>
                          <TableHeadCell>Notes</TableHeadCell>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {channelPlan.map((c, idx) => (
                          <TableRow key={idx}>
                            <TableCell>{c.channel}</TableCell>
                            <TableCell className="text-xs text-content-muted">{truncate(c.objective, 120)}</TableCell>
                            <TableCell className="text-xs text-content-muted">
                              {c.budgetSplitPercent ?? "—"}
                            </TableCell>
                            <TableCell className="text-xs text-content-muted">{truncate(c.notes, 120)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  ) : (
                    <div className="text-xs text-content-muted">No channel plan generated.</div>
                  )}
                </div>
                <div>
                  <div className="text-xs font-semibold text-content-muted uppercase mb-1">Messaging</div>
                  {messaging.length ? (
                    <div className="grid gap-2 md:grid-cols-2">
                      {messaging.map((m, idx) => (
                        <div key={idx} className="ds-card ds-card--sm bg-surface-2">
                          <div className="text-sm font-semibold text-content">{m.title}</div>
                        <div className="mt-1 text-xs text-content-muted">
                          Proof points: {(m.proofPoints || []).join("; ") || "—"}
                        </div>
                      </div>
                    ))}
                    </div>
                  ) : (
                    <div className="text-xs text-content-muted">No messaging pillars generated.</div>
                  )}
                </div>
                <div className="grid gap-2 md:grid-cols-2">
                  <div>
                    <div className="text-xs font-semibold text-content-muted uppercase">Risks</div>
                    <div className="mt-1 text-xs text-content-muted">
                      {risks.length ? risks.map((r, i) => <div key={i}>• {r}</div>) : "—"}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-content-muted uppercase">Mitigations</div>
                    <div className="mt-1 text-xs text-content-muted">
                      {mitigations.length ? mitigations.map((m, i) => <div key={i}>• {m}</div>) : "—"}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          {Object.keys(stepSummaries).length ? (
            <div className="ds-card ds-card--md shadow-none">
              <div className="text-sm font-semibold text-content">Step summaries</div>
              <div className="mt-2 grid gap-2 md:grid-cols-2">
                {Object.entries(stepSummaries).map(([step, summary]) => (
                  <div key={step} className="ds-card ds-card--sm bg-surface-2">
                    <div className="text-xs font-semibold text-content">Step {step}</div>
                    <div className="text-xs text-content-muted mt-1">{truncate(summary as string, 240)}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="ds-card ds-card--md p-0 shadow-none">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div>
                <div className="text-sm font-semibold text-content">Activity log</div>
                <div className="text-xs text-content-muted">Recent workflow events and signals.</div>
              </div>
            </div>
            <div className="overflow-x-auto">
              <Table variant="ghost">
                <TableHeader>
                  <TableRow>
                    <TableHeadCell>Step</TableHeadCell>
                    <TableHeadCell>Status</TableHeadCell>
                    <TableHeadCell>When</TableHeadCell>
                    <TableHeadCell>Error</TableHeadCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data?.logs?.length ? (
                    data.logs.map((log) => (
                      <TableRow key={log.id}>
                        <TableCell className="font-semibold text-content">{log.step}</TableCell>
                        <TableCell className="text-xs text-content-muted">{log.status}</TableCell>
                        <TableCell className="text-xs text-content-muted">{formatDate(log.created_at)}</TableCell>
                        <TableCell className="text-xs text-danger">{log.error || "—"}</TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell className="px-3 py-4 text-sm text-content-muted" colSpan={4}>
                        No logs recorded for this run yet.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
