import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { DialogContent, DialogDescription, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { useArtifacts, useLatestArtifact } from "@/api/artifacts";
import { useApiClient, type ApiError } from "@/api/client";
import { useCampaign, useUpdateExperimentSpecs } from "@/api/campaigns";
import { useFunnels } from "@/api/funnels";
import { useWorkflowLogs, useWorkflows, useWorkflowSignal } from "@/api/workflows";
import { useProductContext } from "@/contexts/ProductContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { cn } from "@/lib/utils";
import type { Artifact, AssetBrief, ExperimentSpec, StrategySheet } from "@/types/artifacts";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function truncate(text?: string, max = 120) {
  if (!text) return "—";
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

const funnelToneMap: Record<string, "neutral" | "accent" | "success" | "danger"> = {
  draft: "neutral",
  published: "success",
  disabled: "danger",
  archived: "neutral",
};

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

  const [experimentDrafts, setExperimentDrafts] = useState<ExperimentSpec[]>([]);
  const [selectedExperimentIds, setSelectedExperimentIds] = useState<string[]>([]);
  const [selectedAssetBriefIds, setSelectedAssetBriefIds] = useState<string[]>([]);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingSpec, setEditingSpec] = useState<ExperimentSpec | null>(null);
  const [editingJson, setEditingJson] = useState("");
  const [editingError, setEditingError] = useState<string | null>(null);
  const [funnelGenerationPending, setFunnelGenerationPending] = useState(false);
  const [funnelGenerationError, setFunnelGenerationError] = useState<string | null>(null);
  const [funnelCreationRequested, setFunnelCreationRequested] = useState(false);

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
  const strategyWorkflow =
    campaignWorkflows.find((wf) => wf.kind === "campaign_planning" && wf.status === "running") ??
    campaignWorkflows.find((wf) => wf.kind === "campaign_intent" && wf.status === "running");
  const intentWorkflow = campaignWorkflows.find(
    (wf) => wf.kind === "campaign_intent" && wf.status === "running"
  );
  const funnelWorkflow = campaignWorkflows.find(
    (wf) => wf.kind === "campaign_funnel_generation" && wf.status === "running"
  );

  const strategySignal = useWorkflowSignal(strategyWorkflow?.id);
  const intentSignal = useWorkflowSignal(intentWorkflow?.id);
  const canApproveStrategy = Boolean(strategyWorkflow?.id);
  const canApproveAssetBriefs = Boolean(intentWorkflow?.id);
  const isFunnelGenerationActive =
    funnelGenerationPending ||
    funnelCreationRequested ||
    (Boolean(funnelWorkflow?.id) && funnels.length === 0);

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
    const map = new Map<string, ExperimentSpec>();
    experimentArtifacts.forEach((art) => {
      const data = (art.data || {}) as {
        experimentSpecs?: ExperimentSpec[];
        experiment_specs?: ExperimentSpec[];
      };
      const specs = data.experimentSpecs || (data as any).experiment_specs || [];
      specs.forEach((spec) => {
        if (!spec || typeof spec !== "object") return;
        const id = (spec as ExperimentSpec).id;
        if (!id || map.has(id)) return;
        map.set(id, spec as ExperimentSpec);
      });
    });
    return Array.from(map.values());
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

  const allExperimentIds = useMemo(() => experimentDrafts.map((spec) => spec.id).filter(Boolean), [experimentDrafts]);
  const allExperimentsSelected =
    allExperimentIds.length > 0 && allExperimentIds.every((id) => selectedExperimentIds.includes(id));
  const toggleExperimentSelection = (id: string) => {
    setSelectedExperimentIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  };
  const toggleAllExperiments = () => {
    setSelectedExperimentIds(allExperimentsSelected ? [] : allExperimentIds);
  };

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
    setEditingJson(JSON.stringify(spec, null, 2));
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

  const handleSaveSpec = () => {
    if (!editingSpec) return;
    let parsed: ExperimentSpec;
    try {
      const raw = JSON.parse(editingJson);
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
        setEditingError("Angle spec must be a JSON object.");
        return;
      }
      parsed = raw as ExperimentSpec;
    } catch {
      setEditingError("Invalid JSON. Check for missing commas or quotes.");
      return;
    }

    if (!parsed.id || parsed.id !== editingSpec.id) {
      setEditingError("Angle spec id cannot be changed.");
      return;
    }
    if (!parsed.name) {
      setEditingError("Angle spec must include a name.");
      return;
    }
    if (!Array.isArray(parsed.metricIds) || parsed.metricIds.length === 0) {
      setEditingError("Angle spec must include at least one metric id.");
      return;
    }
    if (!Array.isArray(parsed.variants) || parsed.variants.length === 0) {
      setEditingError("Angle spec must include at least one variant.");
      return;
    }
    const invalidVariant = parsed.variants.find(
      (variant) => !variant || typeof variant !== "object" || !variant.id || !variant.name
    );
    if (invalidVariant) {
      setEditingError("Each variant must include id and name.");
      return;
    }

    const nextSpecs = experimentDrafts.map((spec) => (spec.id === parsed.id ? parsed : spec));
    setExperimentDrafts(nextSpecs);
    updateExperimentSpecs.mutate(
      { experimentSpecs: nextSpecs },
      {
        onSuccess: () => {
          setEditDialogOpen(false);
          setEditingSpec(null);
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
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="strategy">Strategy</TabsTrigger>
          <TabsTrigger value="experiments">Angles</TabsTrigger>
          <TabsTrigger value="assets">Creative briefs</TabsTrigger>
          <TabsTrigger value="funnels">Funnels</TabsTrigger>
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
                  {canApproveStrategy ? (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => strategySignal.mutate({ signal: "approve-strategy", body: { approved: true } })}
                      disabled={!strategyArtifact || strategySignal.isPending}
                    >
                      {strategySignal.isPending ? "Sending…" : "Approve strategy"}
                    </Button>
                  ) : null}
                </div>
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
                            <TableCell className="text-sm text-content-muted">{truncate(plan.objective, 120)}</TableCell>
                            <TableCell className="text-sm text-content-muted">{plan.budgetSplitPercent ?? "—"}</TableCell>
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
                          <div className="text-base font-semibold text-content">{msg.title || "Messaging pillar"}</div>
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
                    {mitigations.length ? mitigations.map((risk, idx) => <div key={`mitigation-${idx}`}>• {risk}</div>) : "—"}
                  </div>
                </div>
              </div>
            </div>
          )}
        </TabsContent>

        <TabsContent value="experiments" flush>
          {experimentsLoading ? (
            <div className="border border-border bg-transparent px-4 py-3 text-base text-content-muted">
              Loading angles…
            </div>
          ) : experimentDrafts.length ? (
            <div className="border border-border bg-transparent">
              <div className="border-b border-border px-4 py-3">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-base font-semibold text-content">Angle specs</div>
                    <div className="text-sm text-content-muted">Generated from canon and metric schema.</div>
                  </div>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleCreateFunnels}
                    disabled={
                      funnelGenerationPending || isFunnelGenerationActive || selectedExperimentIds.length === 0
                    }
                  >
                    {funnelGenerationPending || isFunnelGenerationActive ? "Creating…" : "Create funnels"}
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
                      checked={allExperimentsSelected}
                      onChange={toggleAllExperiments}
                    />
                    <span>Select all</span>
                  </label>
                  <span>{selectedExperimentIds.length} selected</span>
                  {updateExperimentSpecs.isPending ? <span>Saving edits…</span> : null}
                </div>
                <div className="mt-2 space-y-2 text-sm text-content-muted">
                  <div>
                    Creating funnels uses the default pre-sales + sales templates and generates creative briefs for the
                    selected angles.
                  </div>
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
              <div className="divide-y divide-border">
                {experimentDrafts.map((exp) => {
                  const isSelected = selectedExperimentIds.includes(exp.id);
                  return (
                    <div key={exp.id} className="px-4 py-3 text-base">
                      <div className="flex flex-wrap items-start justify-between gap-4">
                        <div className="flex items-start gap-3">
                          <input
                            type="checkbox"
                            className={cn(
                              "mt-1 h-4 w-4 rounded border border-border bg-surface text-accent",
                              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
                            )}
                            checked={isSelected}
                            onChange={() => toggleExperimentSelection(exp.id)}
                          />
                          <div>
                            <div className="flex flex-wrap items-center gap-2">
                              <div className="font-semibold text-content">{exp.name || exp.id}</div>
                              <div className="text-sm text-content-muted font-mono">{exp.id}</div>
                            </div>
                            <div className="mt-1 text-sm text-content-muted">
                              {exp.hypothesis || "No hypothesis set."}
                            </div>
                            <div className="mt-2 text-sm text-content-muted">
                              Metrics: {(exp.metricIds || []).join(", ") || "—"} · Variants:{" "}
                              {(exp.variants || []).length}
                            </div>
                            <div className="mt-2 text-sm text-content-muted">
                              Sample size: {exp.sampleSizeEstimate ?? "—"} · Duration: {exp.durationDays ?? "—"} days ·
                              Budget: {exp.budgetEstimate ?? "—"}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            variant="secondary"
                            size="xs"
                            onClick={() => openEditSpec(exp)}
                            disabled={updateExperimentSpecs.isPending}
                          >
                            Edit JSON
                          </Button>
                        </div>
                      </div>
                      {exp.variants?.length ? (
                        <div className="mt-3 space-y-2">
                          {exp.variants.map((variant) => (
                            <div key={variant.id} className="border border-border bg-transparent px-3 py-2 text-sm">
                              <div className="flex items-center justify-between">
                                <div className="font-semibold text-content">{variant.name || variant.id}</div>
                                <div className="font-mono text-sm text-content-muted">{variant.id}</div>
                              </div>
                              <div className="mt-1 text-content-muted">
                                {variant.description || "No variant description."}
                              </div>
                              <div className="mt-1 text-content-muted">
                                Channels: {(variant.channels || []).join(", ") || "—"}
                              </div>
                              {variant.guardrails?.length ? (
                                <div className="mt-1 text-content-muted">
                                  Guardrails: {variant.guardrails.join("; ")}
                                </div>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="border border-border bg-transparent px-4 py-3 text-base">
              No angle specs generated yet. Approve the strategy step to trigger angles.
            </div>
          )}
        </TabsContent>

        <TabsContent value="assets" flush>
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
                  {canApproveAssetBriefs ? (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() =>
                        intentSignal.mutate({
                          signal: "approve-asset-briefs",
                          body: { approved_ids: selectedAssetBriefIds },
                        })
                      }
                      disabled={intentSignal.isPending || selectedAssetBriefIds.length === 0}
                    >
                      {intentSignal.isPending ? "Sending…" : "Approve creative briefs"}
                    </Button>
                  ) : null}
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
                </div>
                {canApproveAssetBriefs ? (
                  <div className="mt-2 text-sm text-content-muted">
                    Approving creative briefs marks them ready for creative production.
                  </div>
                ) : null}
              </div>
              <div className="divide-y divide-border">
                {assetBriefs.map((brief) => {
                  const isSelected = selectedAssetBriefIds.includes(brief.id);
                  const experimentLabel = brief.experimentId
                    ? experimentNameById[brief.experimentId] || brief.experimentId
                    : "—";
                  const variantLabel =
                    brief.variantName ||
                    (brief.variantId ? variantNameById[brief.variantId] || brief.variantId : "—");
                  const funnelLabel = brief.funnelId ? funnelNameById[brief.funnelId] || brief.funnelId : "—";
                  return (
                    <div key={brief.id} className="px-4 py-3 text-base">
                      <div className="flex flex-wrap items-start justify-between gap-4">
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
                          <div>
                            <div className="flex flex-wrap items-center gap-2">
                              <div className="font-semibold text-content">{brief.creativeConcept || brief.id}</div>
                              <div className="text-sm text-content-muted font-mono">{brief.id}</div>
                            </div>
                            <div className="mt-1 text-sm text-content-muted">
                              Angle: {experimentLabel} · Variant: {variantLabel} · Requirements:{" "}
                              {(brief.requirements || []).length}
                            </div>
                            <div className="mt-1 text-sm text-content-muted">Funnel: {funnelLabel}</div>
                          </div>
                        </div>
                      </div>
                      {brief.requirements?.length ? (
                        <div className="mt-2 grid gap-1 text-sm text-content-muted">
                          {brief.requirements.map((req, idx) => (
                            <div key={`${brief.id}-req-${idx}`}>
                              • {req.channel} / {req.format} {req.angle ? `– ${req.angle}` : ""}{" "}
                              {req.hook ? `(${truncate(req.hook, 60)})` : ""}
                            </div>
                          ))}
                        </div>
                      ) : null}
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
                            <Button variant="secondary" size="xs" onClick={() => navigate(`/research/funnels/${funnel.id}`)}>
                              Open
                            </Button>
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

      <DialogRoot
        open={editDialogOpen}
        onOpenChange={(open) => {
          setEditDialogOpen(open);
          if (!open) {
            setEditingSpec(null);
            setEditingError(null);
          }
        }}
      >
        <DialogContent className="max-w-3xl">
          <div className="space-y-2">
            <DialogTitle>Edit angle spec</DialogTitle>
            <DialogDescription>
              Update the angle JSON before approving. IDs must remain stable so downstream assets can link correctly.
            </DialogDescription>
            {editingSpec ? (
              <div className="text-sm text-content-muted">
                Angle ID: <span className="font-mono">{editingSpec.id}</span>
              </div>
            ) : null}
          </div>
          <div className="mt-4 space-y-2">
            <label className="text-sm font-semibold text-content">Angle JSON</label>
            <textarea
              rows={16}
              value={editingJson}
              onChange={(e) => {
                setEditingJson(e.target.value);
                setEditingError(null);
              }}
              className={cn(
                "w-full rounded-md border border-border bg-surface px-3 py-2 text-base text-content",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
              )}
            />
            {editingError ? <div className="text-sm text-danger">{editingError}</div> : null}
          </div>
          <div className="mt-4 flex items-center justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setEditDialogOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleSaveSpec} disabled={updateExperimentSpecs.isPending}>
              {updateExperimentSpecs.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </DialogContent>
      </DialogRoot>
    </div>
  );
}
