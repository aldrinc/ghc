import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { AlertDialog, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { DialogContent, DialogDescription, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useArtifacts, useLatestArtifact } from "@/api/artifacts";
import { useApiClient, type ApiError } from "@/api/client";
import { useCampaign, useUpdateExperimentSpecs } from "@/api/campaigns";
import { useDeleteFunnel, useFunnels } from "@/api/funnels";
import { useProduct } from "@/api/products";
import { useWorkflowLogs, useWorkflows, useWorkflowSignal } from "@/api/workflows";
import { useProductContext } from "@/contexts/ProductContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { cn } from "@/lib/utils";
import type { Artifact, AssetBrief, ExperimentSpec, StrategySheet } from "@/types/artifacts";
import type { ProductAsset } from "@/types/products";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function truncate(text?: string, max = 120) {
  if (!text) return "—";
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function formatBytes(value?: number | null): string | null {
  if (value === null || value === undefined) return null;
  if (value === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let idx = 0;
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024;
    idx += 1;
  }
  return `${size.toFixed(size < 10 && idx > 0 ? 1 : 0)} ${units[idx]}`;
}

function assetLabel(asset: ProductAsset): string {
  const filename = asset.ai_metadata?.filename;
  if (typeof filename === "string" && filename.trim()) return filename;
  if (asset.content_type) return asset.content_type;
  return `Asset ${asset.id.slice(0, 8)}`;
}

function GeneratedAssetCarousel({
  assets,
  selectedAssetId,
  onSelect,
}: {
  assets: ProductAsset[];
  selectedAssetId: string;
  onSelect: (assetId: string) => void;
}) {
  const stripRef = useRef<HTMLDivElement | null>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const updateScrollState = useCallback(() => {
    const el = stripRef.current;
    if (!el) return;
    const maxScrollLeft = el.scrollWidth - el.clientWidth;
    setCanScrollLeft(el.scrollLeft > 0);
    setCanScrollRight(el.scrollLeft < maxScrollLeft - 1);
  }, []);

  useEffect(() => {
    const el = stripRef.current;
    if (!el) return;

    updateScrollState();

    const onScroll = () => updateScrollState();
    el.addEventListener("scroll", onScroll, { passive: true });

    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => updateScrollState()) : null;
    observer?.observe(el);

    return () => {
      el.removeEventListener("scroll", onScroll);
      observer?.disconnect();
    };
  }, [updateScrollState, assets.length]);

  const scrollByPage = (direction: "left" | "right") => {
    const el = stripRef.current;
    if (!el) return;
    const delta = Math.round(el.clientWidth * 0.85) * (direction === "left" ? -1 : 1);
    el.scrollBy({ left: delta, behavior: "smooth" });
  };

  if (!assets.length) return null;

  return (
    <div className="relative">
      {canScrollLeft ? (
        <button
          type="button"
          aria-label="Scroll left"
          onClick={() => scrollByPage("left")}
          className={cn(
            "absolute left-1 top-1/2 z-10 inline-flex h-8 w-8 -translate-y-1/2 items-center justify-center",
            "rounded-full border border-border bg-surface/90 text-content shadow-sm backdrop-blur",
            "transition hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
          )}
        >
          {"<"}
        </button>
      ) : null}
      {canScrollRight ? (
        <button
          type="button"
          aria-label="Scroll right"
          onClick={() => scrollByPage("right")}
          className={cn(
            "absolute right-1 top-1/2 z-10 inline-flex h-8 w-8 -translate-y-1/2 items-center justify-center",
            "rounded-full border border-border bg-surface/90 text-content shadow-sm backdrop-blur",
            "transition hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
          )}
        >
          {">"}
        </button>
      ) : null}

      <div
        ref={stripRef}
        className={cn(
          "flex gap-2 overflow-x-auto overscroll-x-contain pb-1",
          "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        )}
      >
        {assets.map((asset) => {
          const thumbUrl = asset.download_url || undefined;
          const thumbIsImage = asset.asset_kind === "image";
          const thumbSelected = selectedAssetId === asset.id;
          return (
            <button
              key={asset.id}
              type="button"
              onClick={(e) => {
                onSelect(asset.id);
                e.currentTarget.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
              }}
              className={cn(
                "flex-none overflow-hidden rounded-md border bg-surface-2 text-left transition",
                "h-20 w-20",
                thumbSelected ? "border-accent ring-2 ring-accent/20" : "border-border hover:border-accent/50"
              )}
              title={assetLabel(asset)}
            >
              {thumbIsImage && thumbUrl ? (
                <img
                  src={thumbUrl}
                  alt={asset.alt || assetLabel(asset)}
                  className="h-full w-full object-cover"
                  loading="lazy"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-[10px] font-semibold uppercase text-content-muted">
                  {asset.asset_kind}
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function normalizeListText(value: string) {
  const items = value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);

  // Preserve order while removing duplicates.
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item)) return false;
    seen.add(item);
    return true;
  });
}

type ExperimentVariantEditDraft = {
  id: string;
  name: string;
  description: string;
  channelsText: string;
  guardrailsText: string;
};

type ExperimentSpecEditDraft = {
  id: string;
  name: string;
  hypothesis: string;
  metricIdsText: string;
  sampleSizeEstimateText: string;
  durationDaysText: string;
  budgetEstimateText: string;
  variants: ExperimentVariantEditDraft[];
};

const funnelToneMap: Record<string, "neutral" | "accent" | "success" | "danger"> = {
  draft: "neutral",
  published: "success",
  disabled: "danger",
  archived: "neutral",
};

const READABILITY_MAX_WIDTH_CLASS = "w-full max-w-4xl";

const EMPTY_ARTIFACTS: Artifact[] = [];

export function CampaignDetailPage() {
  const { campaignId } = useParams();
  const navigate = useNavigate();
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace, clients } = useWorkspace();
  const { product, products, selectProduct } = useProductContext();
  const { data: campaign, isLoading: campaignLoading, isError: campaignError } = useCampaign(campaignId);
  const { data: workflows = [], isLoading: workflowsLoading } = useWorkflows();
  const updateExperimentSpecs = useUpdateExperimentSpecs(campaignId);
  const deleteFunnel = useDeleteFunnel();

  const [experimentDrafts, setExperimentDrafts] = useState<ExperimentSpec[]>([]);
  const [selectedExperimentIds, setSelectedExperimentIds] = useState<string[]>([]);
  const [selectedAssetBriefIds, setSelectedAssetBriefIds] = useState<string[]>([]);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingSpec, setEditingSpec] = useState<ExperimentSpec | null>(null);
  const [editingDraft, setEditingDraft] = useState<ExperimentSpecEditDraft | null>(null);
  const [editingError, setEditingError] = useState<string | null>(null);
  const [funnelGenerationPending, setFunnelGenerationPending] = useState(false);
  const [funnelGenerationError, setFunnelGenerationError] = useState<string | null>(null);
  const [funnelCreationRequested, setFunnelCreationRequested] = useState(false);
  const [creativeProductionPending, setCreativeProductionPending] = useState(false);
  const [creativeProductionError, setCreativeProductionError] = useState<string | null>(null);
  const [selectedPreviewAssetByBrief, setSelectedPreviewAssetByBrief] = useState<Record<string, string>>({});
  const [publishedDeleteTarget, setPublishedDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  const [deletePendingFunnelId, setDeletePendingFunnelId] = useState<string | null>(null);

  const strategyFilters = useMemo(() => (campaignId ? { campaignId, type: "strategy_sheet" } : {}), [campaignId]);
  const experimentFilters = useMemo(() => (campaignId ? { campaignId, type: "experiment_spec" } : {}), [campaignId]);
  const assetBriefFilters = useMemo(() => (campaignId ? { campaignId, type: "asset_brief" } : {}), [campaignId]);

  const { latest: strategyArtifact, isLoading: strategyLoading } = useLatestArtifact(strategyFilters);
  const { data: experimentArtifacts = EMPTY_ARTIFACTS, isLoading: experimentsLoading } = useArtifacts(experimentFilters);
  const { data: assetBriefArtifacts = EMPTY_ARTIFACTS, isLoading: briefsLoading } = useArtifacts(assetBriefFilters);
  const { data: funnels = [], isLoading: funnelsLoading } = useFunnels(campaignId ? { campaignId } : undefined);

  const campaignWorkflows = useMemo(() => {
    if (!campaignId) return [];
    return workflows
      .filter((wf) => wf.campaign_id === campaignId)
      .sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());
  }, [campaignId, workflows]);
  const funnelWorkflows = useMemo(
    () => campaignWorkflows.filter((wf) => wf.kind === "campaign_funnel_generation"),
    [campaignWorkflows]
  );
  const latestFunnelWorkflow = funnelWorkflows[0];
  const { data: funnelLogs = [] } = useWorkflowLogs(latestFunnelWorkflow?.id);
  const latestWorkflow = campaignWorkflows[0];
  const planningWorkflow = campaignWorkflows.find((wf) => wf.kind === "campaign_planning" && wf.status === "running");
  const funnelWorkflow = campaignWorkflows.find(
    (wf) => wf.kind === "campaign_funnel_generation" && wf.status === "running"
  );
  const hasRunningFunnelWorkflow = Boolean(funnelWorkflow?.id);

  const planningSignal = useWorkflowSignal(planningWorkflow?.id);
  const canApproveExperiments = Boolean(planningWorkflow?.id);
  const isFunnelGenerationActive =
    funnelGenerationPending ||
    funnelCreationRequested ||
    hasRunningFunnelWorkflow;

  const latestFunnelFailure = useMemo(() => {
    if (!funnelLogs.length) return null;
    const failures = funnelLogs.filter((log) => log.status === "failed");
    if (!failures.length) return null;
    return [...failures].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    )[0];
  }, [funnelLogs]);
  const funnelFailureSummary = useMemo(() => {
    if (!latestFunnelFailure) return null;
    const stepLabel = latestFunnelFailure.step.replace(/_/g, " ");
    const when = formatDate(latestFunnelFailure.created_at);
    const detail = latestFunnelFailure.error || "Unknown error.";
    return `${stepLabel} failed at ${when}. ${detail}`;
  }, [latestFunnelFailure]);

  const workspaceName = useMemo(() => {
    if (!campaign?.client_id) return null;
    if (workspace?.id === campaign.client_id) return workspace.name;
    return clients.find((client) => client.id === campaign.client_id)?.name ?? null;
  }, [campaign?.client_id, workspace?.id, workspace?.name, clients]);
  const campaignProductId = campaign?.product_id || product?.id;
  const { data: campaignProductDetail, isLoading: campaignProductLoading } = useProduct(campaignProductId || undefined);

  const campaignProduct = useMemo(
    () => products.find((item) => item.id === campaign?.product_id),
    [products, campaign?.product_id]
  );

  const strategy = useMemo(() => (strategyArtifact?.data || {}) as StrategySheet, [strategyArtifact?.data]);
  const channelPlan = strategy.channelPlan || [];
  const messaging = strategy.messaging || [];
  const risks = strategy.risks || [];
  const mitigations = strategy.mitigations || [];

  const experimentSpecs = useMemo(() => {
    const latest = experimentArtifacts?.[0];
    const data = (latest?.data || {}) as {
      experimentSpecs?: ExperimentSpec[];
      experiment_specs?: ExperimentSpec[];
    };
    const specs = data.experimentSpecs || (data as any).experiment_specs || [];
    if (!Array.isArray(specs)) return [];
    return specs.filter((spec) => spec && typeof spec === "object" && Boolean((spec as ExperimentSpec).id));
  }, [experimentArtifacts]);

  const experimentNameById = useMemo(() => {
    const map: Record<string, string> = {};
    experimentDrafts.forEach((spec) => {
      if (spec.id) map[spec.id] = spec.name || spec.id;
    });
    return map;
  }, [experimentDrafts]);
  const funnelNameById = useMemo(() => {
    const map: Record<string, string> = {};
    funnels.forEach((funnel) => {
      if (funnel.id) map[funnel.id] = funnel.name || funnel.id;
    });
    return map;
  }, [funnels]);
  const existingFunnelExperimentIds = useMemo(() => {
    const ids = new Set<string>();
    funnels.forEach((funnel) => {
      if (!funnel.experiment_spec_id) return;
      const normalized = funnel.experiment_spec_id.trim();
      if (normalized) ids.add(normalized);
    });
    return ids;
  }, [funnels]);
  const selectedExperimentsWithFunnels = useMemo(
    () => selectedExperimentIds.filter((id) => existingFunnelExperimentIds.has(id)),
    [selectedExperimentIds, existingFunnelExperimentIds]
  );
  const selectedExperimentsWithFunnelsLabel = useMemo(
    () => selectedExperimentsWithFunnels.map((id) => experimentNameById[id] || id).join(", "),
    [selectedExperimentsWithFunnels, experimentNameById]
  );

  const variantNameById = useMemo(() => {
    const map: Record<string, string> = {};
    experimentDrafts.forEach((spec) => {
      (spec.variants || []).forEach((variant) => {
        if (!variant?.id) return;
        map[variant.id] = variant.name || variant.id;
      });
    });
    return map;
  }, [experimentDrafts]);

  const assetBriefs = useMemo(() => {
    const map = new Map<string, AssetBrief>();
    assetBriefArtifacts.forEach((art) => {
      const data = (art.data || {}) as { asset_briefs?: AssetBrief[]; assetBriefs?: AssetBrief[] };
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
  const generatedAssetsByBriefId = useMemo(() => {
    const assets = campaignProductDetail?.assets || [];
    const validBriefIds = new Set(assetBriefs.map((brief) => brief.id));
    const mapped = new Map<string, ProductAsset[]>();
    assets.forEach((asset) => {
      const metadata = asset.ai_metadata || {};
      const briefId = typeof metadata.assetBriefId === "string" ? metadata.assetBriefId : null;
      if (!briefId || !validBriefIds.has(briefId)) return;
      const group = mapped.get(briefId);
      if (group) {
        group.push(asset);
      } else {
        mapped.set(briefId, [asset]);
      }
    });
    return mapped;
  }, [campaignProductDetail?.assets, assetBriefs]);
  const generatedAssetTotal = useMemo(
    () =>
      Array.from(generatedAssetsByBriefId.values()).reduce((sum, assets) => {
        return sum + assets.length;
      }, 0),
    [generatedAssetsByBriefId]
  );
  const briefsWithGeneratedAssets = useMemo(
    () => Array.from(generatedAssetsByBriefId.values()).filter((assets) => assets.length > 0).length,
    [generatedAssetsByBriefId]
  );

  useEffect(() => {
    setExperimentDrafts(experimentSpecs);
  }, [experimentSpecs]);

  useEffect(() => {
    setSelectedExperimentIds((prev) => prev.filter((id) => experimentSpecs.some((spec) => spec.id === id)));
  }, [experimentSpecs]);

  useEffect(() => {
    setSelectedAssetBriefIds((prev) => prev.filter((id) => assetBriefs.some((brief) => brief.id === id)));
  }, [assetBriefs]);

  useEffect(() => {
    if (funnels.length && funnelCreationRequested) {
      setFunnelCreationRequested(false);
    }
  }, [funnels.length, funnelCreationRequested]);

  useEffect(() => {
    setSelectedPreviewAssetByBrief((prev) => {
      const next: Record<string, string> = {};
      generatedAssetsByBriefId.forEach((assets, briefId) => {
        if (!assets.length) return;
        const previousSelection = prev[briefId];
        if (previousSelection && assets.some((asset) => asset.id === previousSelection)) {
          next[briefId] = previousSelection;
          return;
        }
        next[briefId] = assets[0].id;
      });
      return next;
    });
  }, [generatedAssetsByBriefId]);

  const allExperimentIds = useMemo(() => experimentDrafts.map((spec) => spec.id).filter(Boolean), [experimentDrafts]);
  const allExperimentsSelected =
    allExperimentIds.length > 0 && allExperimentIds.every((id) => selectedExperimentIds.includes(id));
  const toggleExperimentSelection = (id: string) => {
    setSelectedExperimentIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  };
  const toggleAllExperiments = () => {
    setSelectedExperimentIds(allExperimentsSelected ? [] : allExperimentIds);
  };

  const selectedVariantCount = useMemo(() => {
    if (!selectedExperimentIds.length) return 0;
    const selected = new Set(selectedExperimentIds);
    return experimentDrafts.reduce((sum, spec) => {
      if (!selected.has(spec.id)) return sum;
      return sum + (spec.variants?.length || 0);
    }, 0);
  }, [experimentDrafts, selectedExperimentIds]);

  const allAssetBriefIds = useMemo(() => assetBriefs.map((brief) => brief.id).filter(Boolean), [assetBriefs]);
  const allAssetBriefsSelected =
    allAssetBriefIds.length > 0 && allAssetBriefIds.every((id) => selectedAssetBriefIds.includes(id));
  const toggleAssetBriefSelection = (id: string) => {
    setSelectedAssetBriefIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  };
  const toggleAllAssetBriefs = () => {
    setSelectedAssetBriefIds(allAssetBriefsSelected ? [] : allAssetBriefIds);
  };

  const openEditSpec = (spec: ExperimentSpec) => {
    setEditingSpec(spec);
    setEditingDraft({
      id: spec.id,
      name: spec.name || "",
      hypothesis: spec.hypothesis || "",
      metricIdsText: (spec.metricIds || []).join("\n"),
      sampleSizeEstimateText: spec.sampleSizeEstimate ? String(spec.sampleSizeEstimate) : "",
      durationDaysText: spec.durationDays ? String(spec.durationDays) : "",
      budgetEstimateText: spec.budgetEstimate ? String(spec.budgetEstimate) : "",
      variants: (spec.variants || []).map((variant) => ({
        id: variant.id,
        name: variant.name || "",
        description: variant.description || "",
        channelsText: (variant.channels || []).join("\n"),
        guardrailsText: (variant.guardrails || []).join("\n"),
      })),
    });
    setEditingError(null);
    setEditDialogOpen(true);
  };

  const getErrorMessage = (err: unknown) => {
    if (typeof err === "string") return err;
    if (err && typeof err === "object" && "message" in err) return (err as ApiError).message || "Request failed";
    return "Request failed";
  };

  const handleCreateFunnels = async () => {
    setFunnelGenerationError(null);
    if (!campaign) {
      setFunnelGenerationError("Campaign is required to start funnel generation.");
      return;
    }
    if (!campaign.id) {
      setFunnelGenerationError("Campaign id is missing.");
      return;
    }
    if (!selectedExperimentIds.length) {
      setFunnelGenerationError("Select at least one angle to create funnels.");
      return;
    }
    if (selectedExperimentsWithFunnels.length) {
      setFunnelGenerationError(
        `Funnels already exist for: ${selectedExperimentsWithFunnelsLabel}. Unselect those angles before creating funnels.`
      );
      return;
    }
    if (hasRunningFunnelWorkflow) {
      setFunnelGenerationError(
        "A funnel generation workflow is already running for this campaign. Wait for it to finish before creating more."
      );
      return;
    }
    if (!campaign.product_id && !product?.id) {
      setFunnelGenerationError("Campaign is missing a product. Attach a product to start funnel generation.");
      return;
    }
    if (!campaign.channels?.length) {
      setFunnelGenerationError("Campaign is missing channels. Add channels before creating funnels.");
      return;
    }
    if (!campaign.asset_brief_types?.length) {
      setFunnelGenerationError("Campaign is missing creative brief types. Add them before creating funnels.");
      return;
    }

    setFunnelGenerationPending(true);
    setFunnelCreationRequested(true);
    try {
      const response = await post<{ workflow_run_id: string }>(
        `/campaigns/${campaign.id}/funnels/generate`,
        {
          experimentIds: selectedExperimentIds,
          generateTestimonials: true,
        }
      );
      if (!response?.workflow_run_id) {
        setFunnelGenerationError("Funnel generation started but no workflow id was returned.");
        setFunnelCreationRequested(false);
        return;
      }
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      queryClient.invalidateQueries({ queryKey: ["funnels"] });
    } catch (err) {
      setFunnelGenerationError(`Failed to start funnel generation: ${getErrorMessage(err)}`);
      setFunnelCreationRequested(false);
    } finally {
      setFunnelGenerationPending(false);
    }
  };

  const handleApproveExperiments = () => {
    if (!planningWorkflow?.id) return;
    planningSignal.mutate({
      signal: "approve-experiments",
      body: { approved_ids: selectedExperimentIds, rejected_ids: [] },
    });
  };

  const handleStartCreativeProduction = async () => {
    setCreativeProductionError(null);
    if (!campaign) {
      setCreativeProductionError("Campaign is required to start creative production.");
      return;
    }
    if (!campaign.id) {
      setCreativeProductionError("Campaign id is missing.");
      return;
    }
    if (!selectedAssetBriefIds.length) {
      setCreativeProductionError("Select at least one creative brief to generate assets.");
      return;
    }

    setCreativeProductionPending(true);
    try {
      const response = await post<{ workflow_run_id: string }>(`/campaigns/${campaign.id}/creative/produce`, {
        assetBriefIds: selectedAssetBriefIds,
      });
      if (!response?.workflow_run_id) {
        setCreativeProductionError("Creative production started but no workflow id was returned.");
        return;
      }
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      navigate(`/workflows/${response.workflow_run_id}`);
    } catch (err) {
      setCreativeProductionError(`Failed to start creative production: ${getErrorMessage(err)}`);
    } finally {
      setCreativeProductionPending(false);
    }
  };

  const performFunnelDelete = async (funnelId: string) => {
    setDeletePendingFunnelId(funnelId);
    try {
      await deleteFunnel.mutateAsync({ funnelId });
    } finally {
      setDeletePendingFunnelId((current) => (current === funnelId ? null : current));
    }
  };

  const requestFunnelDelete = async (funnel: { id: string; name: string; status: string }) => {
    if (funnel.status === "published") {
      setPublishedDeleteTarget({ id: funnel.id, name: funnel.name });
      return;
    }
    try {
      await performFunnelDelete(funnel.id);
    } catch {
      // Mutation surfaces errors through toast.
    }
  };

  const confirmPublishedFunnelDelete = async () => {
    if (!publishedDeleteTarget) return;
    try {
      await performFunnelDelete(publishedDeleteTarget.id);
      setPublishedDeleteTarget(null);
    } catch {
      // Mutation surfaces errors through toast.
    }
  };

  const handleSaveSpec = () => {
    if (!editingSpec || !editingDraft) {
      setEditingError("Angle spec is required to save edits.");
      return;
    }

    const parseOptionalPositiveInt = (raw: string, label: string) => {
      const trimmed = raw.trim();
      if (!trimmed) return { value: undefined as number | undefined };
      const num = Number(trimmed);
      if (!Number.isFinite(num) || !Number.isInteger(num)) {
        return { error: `${label} must be a whole number.` };
      }
      if (num <= 0) {
        return { error: `${label} must be greater than 0.` };
      }
      return { value: num };
    };

    if (!editingDraft.id || editingDraft.id !== editingSpec.id) {
      setEditingError("Angle spec id cannot be changed.");
      return;
    }

    const name = editingDraft.name.trim();
    if (!name) {
      setEditingError("Angle name is required.");
      return;
    }

    const metricIds = normalizeListText(editingDraft.metricIdsText);
    if (!metricIds.length) {
      setEditingError("Angle must include at least one metric id.");
      return;
    }

    if (!editingDraft.variants.length) {
      setEditingError("Angle must include at least one variant.");
      return;
    }

    const nextVariants = editingDraft.variants.map((variant) => {
      const variantName = variant.name.trim();
      const description = variant.description.trim();
      const channels = normalizeListText(variant.channelsText);
      const guardrails = normalizeListText(variant.guardrailsText);
      return {
        id: variant.id,
        name: variantName,
        ...(description ? { description } : {}),
        ...(channels.length ? { channels } : {}),
        ...(guardrails.length ? { guardrails } : {}),
      };
    });

    const invalidVariant = nextVariants.find((variant) => !variant.id || !variant.name);
    if (invalidVariant) {
      setEditingError("Each variant must include an id and a name.");
      return;
    }

    const sampleSizeResult = parseOptionalPositiveInt(editingDraft.sampleSizeEstimateText, "Sample size");
    if (sampleSizeResult.error) {
      setEditingError(sampleSizeResult.error);
      return;
    }
    const durationResult = parseOptionalPositiveInt(editingDraft.durationDaysText, "Duration (days)");
    if (durationResult.error) {
      setEditingError(durationResult.error);
      return;
    }
    const budgetResult = parseOptionalPositiveInt(editingDraft.budgetEstimateText, "Budget");
    if (budgetResult.error) {
      setEditingError(budgetResult.error);
      return;
    }

    const parsed: ExperimentSpec = {
      ...editingSpec,
      id: editingSpec.id,
      name,
      hypothesis: editingDraft.hypothesis.trim() || undefined,
      metricIds,
      variants: nextVariants,
      sampleSizeEstimate: sampleSizeResult.value,
      durationDays: durationResult.value,
      budgetEstimate: budgetResult.value,
    };

    const nextSpecs = experimentDrafts.map((spec) => (spec.id === parsed.id ? parsed : spec));
    setExperimentDrafts(nextSpecs);
    updateExperimentSpecs.mutate(
      { experimentSpecs: nextSpecs },
      {
        onSuccess: () => {
          setEditDialogOpen(false);
          setEditingSpec(null);
          setEditingDraft(null);
        },
      }
    );
  };

  if (!campaignId) {
    return (
      <div className="space-y-4 text-base">
        <PageHeader title="Campaign detail" description="Campaign ID is required to load this view." />
        <div className="border border-border bg-transparent px-4 py-3 text-base text-danger">
          Campaign ID missing from the URL.
        </div>
      </div>
    );
  }

  if (campaignLoading) {
    return (
      <div className="space-y-4 text-base">
        <PageHeader title="Campaign detail" description="Loading campaign overview." />
        <div className="border border-border bg-transparent px-4 py-3 text-base text-content-muted">
          Loading campaign…
        </div>
      </div>
    );
  }

  if (campaignError || !campaign) {
    return (
      <div className="space-y-4 text-base">
        <PageHeader title="Campaign detail" description="Campaign detail could not be loaded." />
        <div className="border border-border bg-transparent px-4 py-3 text-base text-danger">
          Campaign not found.
        </div>
      </div>
    );
  }

  const funnelWorkflowFailed = Boolean(latestFunnelWorkflow?.status === "failed" && funnels.length === 0);
  const funnelStepState = funnelsLoading
    ? "Loading"
    : isFunnelGenerationActive
      ? "Generating"
      : funnelWorkflowFailed
        ? "Failed"
        : funnels.length
          ? "Ready"
          : "Missing";
  const funnelStepTone =
    funnelsLoading || isFunnelGenerationActive
      ? "accent"
      : funnelWorkflowFailed
        ? "danger"
        : funnels.length
          ? "success"
          : "neutral";
  const funnelStepDetail = isFunnelGenerationActive
    ? "Creating funnels…"
    : funnelWorkflowFailed
      ? "Generation failed"
      : funnels.length
        ? `${funnels.length} funnels`
        : "No funnels yet";

  const flowSteps = [
    {
      label: "Strategy sheet",
      state: strategyLoading ? "Loading" : strategyArtifact ? "Ready" : "Missing",
      tone: strategyLoading ? "accent" : strategyArtifact ? "success" : "neutral",
      detail: strategyArtifact ? `Updated ${formatDate(strategyArtifact.created_at)}` : "Not generated yet",
    },
    {
      label: "Angle specs",
      state: experimentsLoading ? "Loading" : experimentDrafts.length ? "Ready" : "Missing",
      tone: experimentsLoading ? "accent" : experimentDrafts.length ? "success" : "neutral",
      detail: experimentDrafts.length ? `${experimentDrafts.length} specs` : "No specs yet",
    },
    {
      label: "Creative briefs",
      state: briefsLoading ? "Loading" : assetBriefs.length ? "Ready" : "Missing",
      tone: briefsLoading ? "accent" : assetBriefs.length ? "success" : "neutral",
      detail: assetBriefs.length ? `${assetBriefs.length} briefs` : "No briefs yet",
    },
    {
      label: "Funnels",
      state: funnelStepState,
      tone: funnelStepTone,
      detail: funnelStepDetail,
    },
  ];

  const campaignProductLabel = campaignProduct?.name || campaign.product_id || null;
  const productMismatch =
    Boolean(campaign.product_id) && Boolean(product?.id) && campaign.product_id !== product?.id;
  const productMissing = Boolean(campaign.product_id) && !product?.id;

  return (
    <div className="space-y-6 text-base">
      <PageHeader
        title={campaign.name}
        description={
          workspaceName
            ? `${workspaceName}${campaignProductLabel ? ` · ${campaignProductLabel}` : ""} · Campaign detail`
            : "Campaign detail"
        }
        actions={
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => navigate("/campaigns")}>
              Back to campaigns
            </Button>
          </div>
        }
      >
        <div className="mt-2 text-sm text-content-muted">
          Campaign ID: <span className="font-mono">{campaign.id}</span>
        </div>
      </PageHeader>

      {productMismatch || productMissing ? (
        <Callout
          variant="warning"
          title="This campaign is scoped to a different product"
          actions={
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                selectProduct(campaign.product_id || "", {
                  name: campaignProduct?.name,
                  client_id: campaign.client_id,
                })
              }
            >
              Switch product
            </Button>
          }
        >
          <>
            This campaign is scoped to{" "}
            <span className="font-semibold text-content">{campaignProductLabel || "a product"}</span>. Switch products to
            review artifacts and planning in context.
          </>
        </Callout>
      ) : null}

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview" className="data-[selected]:!text-black">
            Overview
          </TabsTrigger>
          <TabsTrigger value="strategy" className="data-[selected]:!text-black">
            Strategy
          </TabsTrigger>
          <TabsTrigger value="experiments" className="data-[selected]:!text-black">
            Angles
          </TabsTrigger>
          <TabsTrigger value="assets" className="data-[selected]:!text-black">
            Creative briefs
          </TabsTrigger>
          <TabsTrigger value="funnels" className="data-[selected]:!text-black">
            Funnels
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" flush>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="border border-border bg-transparent p-4">
              <div className="text-base font-semibold text-content">Campaign</div>
              <div className="mt-2 space-y-1 text-sm text-content-muted">
                <div>
                  <span className="text-content">Workspace:</span> {workspaceName || campaign.client_id}
                </div>
                <div>
                  <span className="text-content">Product:</span> {campaignProductLabel || "—"}
                </div>
                <div>
                  <span className="text-content">Campaign ID:</span> <span className="font-mono">{campaign.id}</span>
                </div>
              </div>
            </div>

            <div className="border border-border bg-transparent p-4">
              <div className="text-base font-semibold text-content">Latest workflow</div>
              {workflowsLoading ? (
                <div className="mt-2 text-sm text-content-muted">Loading workflows…</div>
              ) : latestWorkflow ? (
                <div className="mt-2 space-y-1 text-sm text-content">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">{latestWorkflow.kind}</span>
                    <StatusBadge status={latestWorkflow.status} />
                  </div>
                  <div className="text-content-muted">Started: {formatDate(latestWorkflow.started_at)}</div>
                  <div className="text-content-muted">Finished: {formatDate(latestWorkflow.finished_at)}</div>
                  <Button
                    variant="secondary"
                    size="xs"
                    className="mt-2"
                    onClick={() => navigate(`/workflows/${latestWorkflow.id}`)}
                  >
                    Open workflow
                  </Button>
                </div>
              ) : (
                <div className="mt-2 text-sm text-content-muted">No workflows yet for this campaign.</div>
              )}
            </div>

            <div className="border border-border bg-transparent p-4">
              <div className="text-base font-semibold text-content">Flow status</div>
              <div className="mt-2 space-y-2">
                {flowSteps.map((step) => (
                  <div key={step.label} className="flex items-center justify-between gap-2">
                    <div>
                      <div className="text-sm font-semibold text-content">{step.label}</div>
                      <div className="text-sm text-content-muted">{step.detail}</div>
                    </div>
                    <Badge tone={step.tone}>{step.state}</Badge>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="border border-border bg-transparent">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div>
                <div className="text-base font-semibold text-content">Workflow runs</div>
                <div className="text-sm text-content-muted">All runs tied to this campaign.</div>
              </div>
            </div>
            {campaignWorkflows.length ? (
              <div className="overflow-x-auto">
                <Table variant="ghost">
                  <TableHeader>
                    <TableRow>
                      <TableHeadCell>Kind</TableHeadCell>
                      <TableHeadCell>Status</TableHeadCell>
                      <TableHeadCell>Started</TableHeadCell>
                      <TableHeadCell>Actions</TableHeadCell>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {campaignWorkflows.map((wf) => (
                      <TableRow key={wf.id}>
                        <TableCell className="text-base font-semibold text-content">{wf.kind}</TableCell>
                        <TableCell>
                          <StatusBadge status={wf.status} />
                        </TableCell>
                        <TableCell className="text-sm text-content-muted">{formatDate(wf.started_at)}</TableCell>
                        <TableCell className="text-right">
                          <Button variant="secondary" size="xs" onClick={() => navigate(`/workflows/${wf.id}`)}>
                            Open
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <div className="px-4 py-3 text-sm text-content-muted">No workflow runs yet.</div>
            )}
          </div>
        </TabsContent>

        <TabsContent value="strategy" flush>
          <div className={READABILITY_MAX_WIDTH_CLASS}>
            {strategyLoading ? (
              <div className="border border-border bg-transparent px-4 py-3 text-base text-content-muted">
                Loading strategy sheet…
              </div>
            ) : !strategyArtifact ? (
              <div className="border border-border bg-transparent px-4 py-3 text-base">
                No strategy sheet generated yet.
              </div>
            ) : (
              <div className="space-y-4">
                <div className="border border-border bg-transparent p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-base font-semibold text-content">Strategy sheet</div>
                      <div className="text-sm text-content-muted">
                        Updated {formatDate(strategyArtifact.created_at)}
                      </div>
                    </div>
                  </div>
                  <div className="mt-2 text-sm text-content-muted">Strategy sheets are auto-approved.</div>
                  <div className="mt-4 space-y-3 text-base text-content">
                    <div>
                      <div className="text-sm font-semibold text-content-muted uppercase">Goal</div>
                      <div>{truncate(strategy.goal || "—", 240)}</div>
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-content-muted uppercase">Hypothesis</div>
                      <div>{truncate(strategy.hypothesis || "—", 240)}</div>
                    </div>
                  </div>
                </div>

                <div className="border border-border bg-transparent">
                  <div className="border-b border-border px-4 py-3">
                    <div className="text-base font-semibold text-content">Channel plan</div>
                    <div className="text-sm text-content-muted">Budget split and objectives by channel.</div>
                  </div>
                  <div className="p-4">
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
                          {channelPlan.map((plan, idx) => (
                            <TableRow key={`${plan.channel}-${idx}`}>
                              <TableCell>{plan.channel}</TableCell>
                              <TableCell className="text-sm text-content-muted">
                                {truncate(plan.objective, 120)}
                              </TableCell>
                              <TableCell className="text-sm text-content-muted">
                                {plan.budgetSplitPercent ?? "—"}
                              </TableCell>
                              <TableCell className="text-sm text-content-muted">{truncate(plan.notes, 120)}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    ) : (
                      <div className="text-sm text-content-muted">No channel plan generated yet.</div>
                    )}
                  </div>
                </div>

                <div className="border border-border bg-transparent">
                  <div className="border-b border-border px-4 py-3">
                    <div className="text-base font-semibold text-content">Messaging</div>
                    <div className="text-sm text-content-muted">Proof points and story arcs.</div>
                  </div>
                  <div className="p-4">
                    {messaging.length ? (
                      <div className="grid gap-2 md:grid-cols-2">
                        {messaging.map((msg, idx) => (
                          <div key={`${msg.title}-${idx}`} className="border border-border bg-transparent p-3">
                            <div className="text-base font-semibold text-content">
                              {msg.title || "Messaging pillar"}
                            </div>
                            <div className="mt-1 text-sm text-content-muted">
                              Proof points: {(msg.proofPoints || []).join("; ") || "—"}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-sm text-content-muted">No messaging pillars generated yet.</div>
                    )}
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="border border-border bg-transparent p-4">
                    <div className="text-base font-semibold text-content">Risks</div>
                    <div className="mt-2 text-sm text-content-muted">
                      {risks.length ? risks.map((risk, idx) => <div key={`risk-${idx}`}>• {risk}</div>) : "—"}
                    </div>
                  </div>
                  <div className="border border-border bg-transparent p-4">
                    <div className="text-base font-semibold text-content">Mitigations</div>
                    <div className="mt-2 text-sm text-content-muted">
                      {mitigations.length
                        ? mitigations.map((risk, idx) => <div key={`mitigation-${idx}`}>• {risk}</div>)
                        : "—"}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </TabsContent>

        <TabsContent value="experiments" flush>
          <div className={READABILITY_MAX_WIDTH_CLASS}>
            {experimentsLoading ? (
              <div className="border border-border bg-transparent px-4 py-3 text-base text-content-muted">
                Loading angles…
              </div>
            ) : experimentDrafts.length ? (
              <div className="rounded-xl border border-border bg-transparent">
                <div className="border-b border-border px-4 py-3">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-base font-semibold text-content">Angle specs</div>
                      <div className="text-sm text-content-muted">Generated from canon and metric schema.</div>
                    </div>
                    <div className="flex items-center gap-2">
                      {canApproveExperiments ? (
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={handleApproveExperiments}
                          disabled={planningSignal.isPending || selectedExperimentIds.length === 0}
                        >
                          {planningSignal.isPending ? "Sending…" : "Approve experiments"}
                        </Button>
                      ) : null}
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={handleCreateFunnels}
                        disabled={
                          funnelGenerationPending ||
                          isFunnelGenerationActive ||
                          selectedExperimentIds.length === 0 ||
                          selectedExperimentsWithFunnels.length > 0
                        }
                      >
                        {funnelGenerationPending || isFunnelGenerationActive ? "Creating…" : "Create funnels"}
                      </Button>
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-4 text-sm text-content-muted">
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        className={cn(
                          "h-4 w-4 rounded border border-border bg-surface text-accent",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
                        )}
                        checked={allExperimentsSelected}
                        onChange={toggleAllExperiments}
                      />
                      <span>Select all</span>
                    </label>
                    <span>
                      {selectedExperimentIds.length} angles selected · {selectedVariantCount} variants included
                    </span>
                    {updateExperimentSpecs.isPending ? <span>Saving edits…</span> : null}
                  </div>
                  <div className="mt-2 space-y-2 text-sm text-content-muted">
                    <div>Approving experiments unblocks campaign planning to generate creative briefs downstream.</div>
                    <div>
                      Creating funnels uses the default pre-sales + sales templates and generates creative briefs for
                      the selected angles.
                    </div>
                    <div>Selection is per angle spec. Selecting an angle includes all of its variants below.</div>
                    {selectedExperimentsWithFunnels.length ? (
                      <div className="text-danger">
                        Funnels already exist for: {selectedExperimentsWithFunnelsLabel}. Unselect these angles to
                        avoid duplicate workflows.
                      </div>
                    ) : null}
                    {hasRunningFunnelWorkflow ? (
                      <div className="text-danger">
                        A funnel generation workflow is already running for this campaign. Wait for completion before
                        creating more funnels.
                      </div>
                    ) : null}
                    {funnelGenerationError ? <div className="text-danger">{funnelGenerationError}</div> : null}
                    {funnelFailureSummary ? (
                      <div className="rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
                        <div className="font-semibold">Funnel generation failed</div>
                        <div>{funnelFailureSummary}</div>
                        {latestFunnelWorkflow?.id ? (
                          <Button
                            variant="secondary"
                            size="xs"
                            className="mt-2"
                            onClick={() => navigate(`/workflows/${latestFunnelWorkflow.id}`)}
                          >
                            Open workflow
                          </Button>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                  {isFunnelGenerationActive ? (
                    <div className="mt-2 text-sm text-content-muted">
                      Creating funnels… They will appear in the Funnels tab once ready.
                    </div>
                  ) : null}
                </div>
                <div className="space-y-4 p-4">
                  {experimentDrafts.map((exp) => {
                    const isSelected = selectedExperimentIds.includes(exp.id);
                    return (
                      <div
                        key={exp.id}
                        className={cn(
                          "rounded-xl border border-border bg-surface p-4 shadow-sm",
                          isSelected && "border-accent/30 ring-2 ring-accent/10"
                        )}
                      >
                        <div className="flex flex-wrap items-start justify-between gap-4">
                          <div className="flex min-w-0 items-start gap-3">
                            <input
                              type="checkbox"
                              className={cn(
                                "mt-1 h-4 w-4 rounded border border-border bg-surface text-accent",
                                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
                              )}
                              checked={isSelected}
                              onChange={() => toggleExperimentSelection(exp.id)}
                            />
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <div className="text-base font-semibold text-content">{exp.name || exp.id}</div>
                                {isSelected ? <Badge tone="accent">Selected</Badge> : null}
                                {existingFunnelExperimentIds.has(exp.id) ? <Badge tone="neutral">Funnels created</Badge> : null}
                                <Badge tone="neutral">{(exp.variants || []).length} variants</Badge>
                              </div>
                              <div className="mt-0.5 text-xs font-mono text-content-muted">{exp.id}</div>
                              {exp.hypothesis ? (
                                <div className="mt-2 text-sm text-content-muted">{exp.hypothesis}</div>
                              ) : null}
                              <div className="mt-3 flex flex-wrap gap-2 text-xs text-content-muted">
                                <span className="rounded-full bg-muted px-2.5 py-1">
                                  Metrics: {(exp.metricIds || []).join(", ") || "—"}
                                </span>
                                <span className="rounded-full bg-muted px-2.5 py-1">
                                  Sample size: {exp.sampleSizeEstimate ?? "—"}
                                </span>
                                <span className="rounded-full bg-muted px-2.5 py-1">
                                  Duration: {exp.durationDays ?? "—"} days
                                </span>
                                <span className="rounded-full bg-muted px-2.5 py-1">
                                  Budget: {exp.budgetEstimate ?? "—"}
                                </span>
                              </div>
                            </div>
                          </div>
                          <div className="flex shrink-0 items-center gap-2">
                            <Button
                              variant="secondary"
                              size="xs"
                              onClick={() => openEditSpec(exp)}
                              disabled={updateExperimentSpecs.isPending}
                            >
                              Edit angle
                            </Button>
                          </div>
                        </div>

                        {exp.variants?.length ? (
                          <div className="mt-4 rounded-lg bg-muted p-3">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                                Variants
                              </div>
                              <div className="text-xs text-content-muted">Included when angle is selected</div>
                            </div>
                            <div className="mt-2 space-y-2">
                              {exp.variants.map((variant) => (
                                <div key={variant.id} className="rounded-md bg-surface px-3 py-2">
                                  <div className="flex flex-wrap items-start justify-between gap-2">
                                    <div className="min-w-0">
                                      <div className="text-sm font-semibold text-content">
                                        {variant.name || variant.id}
                                      </div>
                                      {variant.description ? (
                                        <div className="mt-1 text-sm text-content-muted">{variant.description}</div>
                                      ) : null}
                                    </div>
                                    <div className="shrink-0 font-mono text-xs text-content-muted">{variant.id}</div>
                                  </div>
                                  <div className="mt-2 text-xs text-content-muted">
                                    Channels: {(variant.channels || []).join(", ") || "—"}
                                  </div>
                                  {variant.guardrails?.length ? (
                                    <div className="mt-1 text-xs text-content-muted">
                                      Guardrails: {variant.guardrails.join("; ")}
                                    </div>
                                  ) : null}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : (
                          <div className="mt-4 text-sm text-content-muted">No variants.</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="border border-border bg-transparent px-4 py-3 text-base">
                No angle specs generated yet. Start campaign planning to generate angles.
              </div>
            )}
          </div>
        </TabsContent>

        <TabsContent value="assets" flush>
          <div className={READABILITY_MAX_WIDTH_CLASS}>
            {briefsLoading ? (
              <div className="border border-border bg-transparent px-4 py-3 text-base text-content-muted">
                Loading creative briefs…
              </div>
            ) : assetBriefs.length ? (
              <div className="border border-border bg-transparent">
                <div className="border-b border-border px-4 py-3">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-base font-semibold text-content">Creative briefs</div>
                      <div className="text-sm text-content-muted">Requirements derived from angle variants.</div>
                    </div>
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={handleStartCreativeProduction}
                      disabled={creativeProductionPending || selectedAssetBriefIds.length === 0}
                    >
                      {creativeProductionPending ? "Starting…" : "Generate assets"}
                    </Button>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-4 text-sm text-content-muted">
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        className={cn(
                          "h-4 w-4 rounded border border-border bg-surface text-accent",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
                        )}
                        checked={allAssetBriefsSelected}
                        onChange={toggleAllAssetBriefs}
                      />
                      <span>Select all</span>
                    </label>
                    <span>{selectedAssetBriefIds.length} selected</span>
                    <span>
                      Generated: {generatedAssetTotal} assets across {briefsWithGeneratedAssets}/{assetBriefs.length} briefs
                    </span>
                  </div>
                  <div className="mt-2 text-sm text-content-muted">
                    Generating assets triggers creative production for the selected briefs.
                  </div>
                  {campaignProductLoading ? (
                    <div className="mt-1 text-sm text-content-muted">Loading generated assets…</div>
                  ) : null}
                  {creativeProductionError ? (
                    <div className="mt-2 text-sm text-danger">{creativeProductionError}</div>
                  ) : null}
                </div>
                <div className="divide-y divide-border">
                  {assetBriefs.map((brief) => {
                    const isSelected = selectedAssetBriefIds.includes(brief.id);
                    const generatedAssets = generatedAssetsByBriefId.get(brief.id) || [];
                    const experimentLabel = brief.experimentId
                      ? experimentNameById[brief.experimentId] || brief.experimentId
                      : "—";
                    const variantLabel =
                      brief.variantName ||
                      (brief.variantId ? variantNameById[brief.variantId] || brief.variantId : "—");
                    const funnelLabel = brief.funnelId ? funnelNameById[brief.funnelId] || brief.funnelId : "—";
                    const selectedPreviewAssetId = selectedPreviewAssetByBrief[brief.id];
                    const featuredAsset =
                      generatedAssets.find((asset) => asset.id === selectedPreviewAssetId) || generatedAssets[0];
                    const featuredAssetUrl = featuredAsset?.download_url || undefined;
                    const featuredIsImage = featuredAsset?.asset_kind === "image";
                    const featuredIsVideo = featuredAsset?.asset_kind === "video";
                    const featuredSize = featuredAsset ? formatBytes(featuredAsset.size_bytes) : null;
                    return (
                      <div key={brief.id} className="px-4 py-3 text-base">
                        <div className="grid gap-4 xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
                          <div className="min-w-0">
                            <div className="flex items-start gap-3">
                              <input
                                type="checkbox"
                                className={cn(
                                  "mt-1 h-4 w-4 rounded border border-border bg-surface text-accent",
                                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
                                )}
                                checked={isSelected}
                                onChange={() => toggleAssetBriefSelection(brief.id)}
                              />
                              <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-2">
                                  <div className="font-semibold text-content">{brief.creativeConcept || brief.id}</div>
                                  <div className="text-sm text-content-muted font-mono">{brief.id}</div>
                                  {generatedAssets.length ? (
                                    <Badge tone="success">{generatedAssets.length} generated</Badge>
                                  ) : (
                                    <Badge tone="neutral">No generated assets</Badge>
                                  )}
                                </div>
                                <div className="mt-1 text-sm text-content-muted">
                                  Angle: {experimentLabel} · Variant: {variantLabel} · Requirements:{" "}
                                  {(brief.requirements || []).length}
                                </div>
                                <div className="mt-1 text-sm text-content-muted">Funnel: {funnelLabel}</div>
                              </div>
                            </div>

                            {brief.requirements?.length ? (
                              <div className="mt-3 grid gap-1 text-sm text-content-muted">
                                {brief.requirements.map((req, idx) => (
                                  <div key={`${brief.id}-req-${idx}`}>
                                    • {req.channel} / {req.format} {req.angle ? `– ${req.angle}` : ""}{" "}
                                    {req.hook ? `(${truncate(req.hook, 60)})` : ""}
                                  </div>
                                ))}
                              </div>
                            ) : null}
                          </div>

                          <div className="min-w-0 rounded-lg border border-border bg-surface p-3">
                            {featuredAsset ? (
                              <div className="space-y-3">
                                <div className="overflow-hidden rounded-md border border-border bg-surface-2">
                                  {featuredIsImage && featuredAssetUrl ? (
                                    <img
                                      src={featuredAssetUrl}
                                      alt={featuredAsset.alt || assetLabel(featuredAsset)}
                                      className="h-[420px] w-full object-contain"
                                      loading="lazy"
                                    />
                                  ) : featuredIsVideo && featuredAssetUrl ? (
                                    <video src={featuredAssetUrl} controls className="h-[420px] w-full bg-black" />
                                  ) : (
                                    <div className="flex h-[420px] items-center justify-center text-sm font-semibold uppercase text-content-muted">
                                      No preview available
                                    </div>
                                  )}
                                </div>
                                <div className="flex flex-wrap items-start justify-between gap-2">
                                  <div className="min-w-0">
                                    <div className="truncate text-sm font-semibold text-content">
                                      {assetLabel(featuredAsset)}
                                    </div>
                                    <div className="text-xs text-content-muted">
                                      {featuredAsset.content_type || featuredAsset.asset_kind}
                                      {featuredSize ? ` · ${featuredSize}` : ""}
                                      {` · Created ${formatDate(featuredAsset.created_at)}`}
                                    </div>
                                  </div>
                                  {featuredAssetUrl ? (
                                    <a
                                      className="text-xs font-semibold text-primary hover:underline"
                                      href={featuredAssetUrl}
                                      target="_blank"
                                      rel="noreferrer"
                                    >
                                      Open full size
                                    </a>
                                  ) : null}
                                </div>
                                <GeneratedAssetCarousel
                                  assets={generatedAssets}
                                  selectedAssetId={featuredAsset.id}
                                  onSelect={(assetId) =>
                                    setSelectedPreviewAssetByBrief((prev) => ({ ...prev, [brief.id]: assetId }))
                                  }
                                />
                              </div>
                            ) : (
                              <div className="text-xs text-content-muted">No generated assets for this brief yet.</div>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="border border-border bg-transparent px-4 py-3 text-base">
                Creative briefs will appear after angle specs are generated.
              </div>
            )}
          </div>
        </TabsContent>

        <TabsContent value="funnels" flush>
          <div className="flex items-center justify-between">
            <div>
              <div className="text-base font-semibold text-content">Funnels</div>
              <div className="text-sm text-content-muted">
                Funnels are managed in the funnels workspace and can be edited anytime.
              </div>
            </div>
            <Button variant="secondary" size="sm" onClick={() => navigate("/research/funnels")}>
              View all funnels
            </Button>
          </div>
          <div className="mt-4">
            {funnelsLoading ? (
              <div className="border border-border bg-transparent px-4 py-3 text-base text-content-muted">
                Loading funnels…
              </div>
            ) : funnels.length ? (
              <div className="border border-border bg-transparent">
                <div className="overflow-x-auto">
                  <Table variant="ghost">
                    <TableHeader>
                      <TableRow>
                        <TableHeadCell>Name</TableHeadCell>
                        <TableHeadCell>Status</TableHeadCell>
                        <TableHeadCell>Updated</TableHeadCell>
                        <TableHeadCell />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {funnels.map((funnel) => (
                        <TableRow key={funnel.id}>
                          <TableCell>
                            <Link
                              to={`/research/funnels/${funnel.id}`}
                              className="font-semibold text-content hover:underline"
                            >
                              {funnel.name}
                            </Link>
                            {funnel.description ? (
                              <div className="mt-1 text-sm text-content-muted">{funnel.description}</div>
                            ) : null}
                          </TableCell>
                          <TableCell>
                            <Badge tone={funnelToneMap[funnel.status] || "neutral"}>{funnel.status}</Badge>
                          </TableCell>
                          <TableCell className="text-sm text-content-muted">{formatDate(funnel.updated_at)}</TableCell>
                          <TableCell className="text-right">
                            <div className="flex items-center justify-end gap-2">
                              <Button variant="secondary" size="xs" onClick={() => navigate(`/research/funnels/${funnel.id}`)}>
                                Open
                              </Button>
                              <Button
                                variant="destructive"
                                size="xs"
                                onClick={() => void requestFunnelDelete(funnel)}
                                disabled={deleteFunnel.isPending}
                              >
                                {deletePendingFunnelId === funnel.id ? "Deleting…" : "Delete"}
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            ) : isFunnelGenerationActive ? (
              <div className="border border-border bg-transparent px-4 py-3 text-base text-content-muted">
                Creating funnels… This can take a few minutes. We’ll attach the pre-sales + sales pages to this campaign
                when ready.
              </div>
            ) : (
              <div className="border border-border bg-transparent px-4 py-3 text-base">
                No funnels connected to this campaign yet.
              </div>
            )}
          </div>
        </TabsContent>
      </Tabs>

      <AlertDialog
        open={Boolean(publishedDeleteTarget)}
        onOpenChange={(open) => {
          if (!open && !deleteFunnel.isPending) setPublishedDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogTitle>Delete published funnel?</AlertDialogTitle>
          <AlertDialogDescription>
            This funnel is currently published. Deleting it will remove the funnel and all of its pages.
          </AlertDialogDescription>
          {publishedDeleteTarget ? (
            <div className="mt-3 rounded-md border border-border bg-surface-2 px-3 py-2 text-sm">
              <span className="font-semibold text-content">{publishedDeleteTarget.name}</span>
            </div>
          ) : null}
          <div className="mt-6 flex items-center justify-end gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setPublishedDeleteTarget(null)}
              disabled={deleteFunnel.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => void confirmPublishedFunnelDelete()}
              disabled={deleteFunnel.isPending}
            >
              {deletePendingFunnelId === publishedDeleteTarget?.id ? "Deleting…" : "Delete funnel"}
            </Button>
          </div>
        </AlertDialogContent>
      </AlertDialog>

      <DialogRoot
        open={editDialogOpen}
        onOpenChange={(open) => {
          setEditDialogOpen(open);
          if (!open) {
            setEditingSpec(null);
            setEditingDraft(null);
            setEditingError(null);
          }
        }}
      >
        <DialogContent className="max-w-4xl">
          <div className="space-y-2">
            <DialogTitle>Edit angle</DialogTitle>
            <DialogDescription>
              Update angle and variant details. IDs are locked so downstream assets can link correctly.
            </DialogDescription>
            {editingSpec ? (
              <div className="text-sm text-content-muted">
                Angle ID: <span className="font-mono">{editingSpec.id}</span>
              </div>
            ) : null}
          </div>

          {editingError ? (
            <div className="mt-4 rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
              {editingError}
            </div>
          ) : null}

          {editingDraft ? (
            <div className="mt-4 max-h-[70vh] space-y-6 overflow-y-auto pr-1">
              <div className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-content">Angle name</label>
                    <Input
                      value={editingDraft.name}
                      onChange={(e) => {
                        const value = e.target.value;
                        setEditingDraft((prev) => (prev ? { ...prev, name: value } : prev));
                        setEditingError(null);
                      }}
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-content">Metrics (one per line)</label>
                    <Textarea
                      rows={4}
                      value={editingDraft.metricIdsText}
                      onChange={(e) => {
                        const value = e.target.value;
                        setEditingDraft((prev) => (prev ? { ...prev, metricIdsText: value } : prev));
                        setEditingError(null);
                      }}
                      required
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-semibold text-content">Hypothesis</label>
                  <Textarea
                    rows={3}
                    value={editingDraft.hypothesis}
                    onChange={(e) => {
                      const value = e.target.value;
                      setEditingDraft((prev) => (prev ? { ...prev, hypothesis: value } : prev));
                      setEditingError(null);
                    }}
                  />
                </div>

                <div className="grid gap-4 md:grid-cols-3">
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-content">Sample size</label>
                    <Input
                      type="number"
                      min={1}
                      step={1}
                      value={editingDraft.sampleSizeEstimateText}
                      onChange={(e) => {
                        const value = e.target.value;
                        setEditingDraft((prev) => (prev ? { ...prev, sampleSizeEstimateText: value } : prev));
                        setEditingError(null);
                      }}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-content">Duration (days)</label>
                    <Input
                      type="number"
                      min={1}
                      step={1}
                      value={editingDraft.durationDaysText}
                      onChange={(e) => {
                        const value = e.target.value;
                        setEditingDraft((prev) => (prev ? { ...prev, durationDaysText: value } : prev));
                        setEditingError(null);
                      }}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-content">Budget</label>
                    <Input
                      type="number"
                      min={1}
                      step={1}
                      value={editingDraft.budgetEstimateText}
                      onChange={(e) => {
                        const value = e.target.value;
                        setEditingDraft((prev) => (prev ? { ...prev, budgetEstimateText: value } : prev));
                        setEditingError(null);
                      }}
                    />
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div className="text-sm font-semibold text-content">Variants</div>
                  <div className="text-xs text-content-muted">Variant IDs are locked.</div>
                </div>
                <div className="space-y-3">
                  {editingDraft.variants.map((variant) => (
                    <div key={variant.id} className="rounded-xl bg-muted p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="text-sm font-semibold text-content">
                          Variant: {variant.name || variant.id}
                        </div>
                        <div className="text-xs font-mono text-content-muted">{variant.id}</div>
                      </div>

                      <div className="mt-3 grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                          <label className="text-sm font-semibold text-content">Name</label>
                          <Input
                            value={variant.name}
                            onChange={(e) => {
                              const value = e.target.value;
                              setEditingDraft((prev) => {
                                if (!prev) return prev;
                                return {
                                  ...prev,
                                  variants: prev.variants.map((item) =>
                                    item.id === variant.id ? { ...item, name: value } : item
                                  ),
                                };
                              });
                              setEditingError(null);
                            }}
                            required
                          />
                        </div>
                        <div className="space-y-2">
                          <label className="text-sm font-semibold text-content">Channels (one per line)</label>
                          <Textarea
                            rows={3}
                            value={variant.channelsText}
                            onChange={(e) => {
                              const value = e.target.value;
                              setEditingDraft((prev) => {
                                if (!prev) return prev;
                                return {
                                  ...prev,
                                  variants: prev.variants.map((item) =>
                                    item.id === variant.id ? { ...item, channelsText: value } : item
                                  ),
                                };
                              });
                              setEditingError(null);
                            }}
                          />
                        </div>
                      </div>

                      <div className="mt-3 space-y-2">
                        <label className="text-sm font-semibold text-content">Description</label>
                        <Textarea
                          rows={3}
                          value={variant.description}
                          onChange={(e) => {
                            const value = e.target.value;
                            setEditingDraft((prev) => {
                              if (!prev) return prev;
                              return {
                                ...prev,
                                variants: prev.variants.map((item) =>
                                  item.id === variant.id ? { ...item, description: value } : item
                                ),
                              };
                            });
                            setEditingError(null);
                          }}
                        />
                      </div>

                      <div className="mt-3 space-y-2">
                        <label className="text-sm font-semibold text-content">Guardrails (one per line)</label>
                        <Textarea
                          rows={3}
                          value={variant.guardrailsText}
                          onChange={(e) => {
                            const value = e.target.value;
                            setEditingDraft((prev) => {
                              if (!prev) return prev;
                              return {
                                ...prev,
                                variants: prev.variants.map((item) =>
                                  item.id === variant.id ? { ...item, guardrailsText: value } : item
                                ),
                              };
                            });
                            setEditingError(null);
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="mt-4 rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
              No angle loaded for editing.
            </div>
          )}

          <div className="mt-4 flex items-center justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setEditDialogOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleSaveSpec} disabled={updateExperimentSpecs.isPending || !editingDraft}>
              {updateExperimentSpecs.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </DialogContent>
      </DialogRoot>
    </div>
  );
}
