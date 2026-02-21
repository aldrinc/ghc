import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button, buttonClasses } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/StatusBadge";
import { useAssets } from "@/api/assets";
import { useStopWorkflow, useWorkflowDetail, useWorkflowSignal } from "@/api/workflows";
import { useProductContext } from "@/contexts/ProductContext";
import type { Asset, ResearchArtifactRef } from "@/types/common";

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

export function WorkflowDetailPage() {
  const { workflowId } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch } = useWorkflowDetail(workflowId);
  const workflowSignal = useWorkflowSignal(workflowId);
  const stopWorkflow = useStopWorkflow();
  const { product, products, selectProduct } = useProductContext();

  const run = data?.run;
  const runProduct = useMemo(
    () => products.find((item) => item.id === run?.product_id),
    [products, run?.product_id]
  );
  const researchArtifacts: ResearchArtifactRef[] = useMemo(
    () => (data?.research_artifacts || []) as ResearchArtifactRef[],
    [data?.research_artifacts]
  );
  const stepSummaries = (data?.precanon_research?.step_summaries as Record<string, string> | undefined) || {};
  const canonStory = (data?.client_canon?.data?.brand as any)?.story as string | undefined;
  const isOnboarding = run?.kind === "client_onboarding";
  const isCampaignPlanning = run?.kind === "campaign_planning" || run?.kind === "campaign_intent";
  const isCreativeProduction = run?.kind === "creative_production";
  const approvalsDisabled = !run || run.status !== "running";
  const strategyData = (data?.strategy_sheet?.data || {}) as any;
  const channelPlan = (strategyData.channelPlan as any[]) || [];
  const messaging = (strategyData.messaging as any[]) || [];
  const risks = (strategyData.risks as string[]) || [];
  const mitigations = (strategyData.mitigations as string[]) || [];
  const experimentArtifacts = data?.experiment_specs || [];
  const assetBriefArtifacts = data?.asset_briefs || [];
  const latestLog = data?.logs?.[0];

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

  const [selectedExperimentIds, setSelectedExperimentIds] = useState<string[]>([]);
  useEffect(() => {
    setSelectedExperimentIds((prev) => prev.filter((id) => experimentSpecs.some((spec: any) => spec.id === id)));
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
  const handleStopWorkflow = () => {
    if (!run?.id || stopWorkflow.isPending) return;
    stopWorkflow.mutate(run.id);
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Workflow detail"
        description={
          runProduct?.name
            ? `Inspect research artifacts for ${runProduct.name}.`
            : "Inspect research artifacts and unblock any required gates."
        }
        actions={
          <Menu>
            <MenuTrigger className={buttonClasses({ variant: "secondary", size: "sm" })}>Actions</MenuTrigger>
            <MenuContent>
              <MenuItem onClick={() => navigate("/workflows")}>Open all workflows</MenuItem>
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
                      name: runProduct?.name,
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
                <span className="font-semibold text-content">{runProduct?.name || run.product_id}</span>. Switch product
                to review artifacts in context.
              </>
            </Callout>
          ) : null}
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
                    {runProduct?.name || run.product_id || "—"}
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

          {researchArtifacts?.length ? (
            <div className="ds-card ds-card--md p-0 shadow-none">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <div>
                  <div className="text-sm font-semibold text-content">Pre-canon research artifacts</div>
                  <div className="text-xs text-content-muted">Read summaries inline; open docs for full files.</div>
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
                            <Link to={`/workflows/${workflowId}/research/${art.step_key}`} className="text-sm">
                              <Button variant="secondary" size="xs">View</Button>
                            </Link>
                            <a href={art.doc_url} target="_blank" rel="noreferrer" className="text-primary underline text-xs">
                              Open doc
                            </a>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </div>
          ) : null}

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
