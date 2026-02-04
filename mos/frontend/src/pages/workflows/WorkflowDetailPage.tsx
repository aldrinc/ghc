import { useEffect, useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/StatusBadge";
import { useWorkflowDetail, useWorkflowSignal } from "@/api/workflows";
import { useProductContext } from "@/contexts/ProductContext";
import type { ResearchArtifactRef } from "@/types/common";

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
  const { data, isLoading, isError, refetch } = useWorkflowDetail(workflowId);
  const signal = useWorkflowSignal(workflowId);
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
  const isCampaignPlanning = run?.kind === "campaign_planning";
  const approvalsDisabled = !run || run.status !== "running";
  const strategyData = (data?.strategy_sheet?.data || {}) as any;
  const channelPlan = (strategyData.channelPlan as any[]) || [];
  const messaging = (strategyData.messaging as any[]) || [];
  const risks = (strategyData.risks as string[]) || [];
  const mitigations = (strategyData.mitigations as string[]) || [];
  const experimentArtifacts = data?.experiment_specs || [];
  const assetBriefArtifacts = data?.asset_briefs || [];
  const latestLog = data?.logs?.[0];

  useEffect(() => {
    if (!run || run.status !== "running") return;
    const interval = window.setInterval(() => {
      void refetch();
    }, 15000);
    return () => window.clearInterval(interval);
  }, [run?.status, refetch]);

  const handleApproveCanon = () => {
    signal.mutate({ signal: "approve-canon", body: { approved: true } });
  };

  const handleApproveMetric = () => {
    signal.mutate({ signal: "approve-metric-schema", body: { approved: true } });
  };

  const handleApproveStrategy = () => {
    signal.mutate({ signal: "approve-strategy", body: { approved: true } });
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Workflow detail"
        description={
          runProduct?.name
            ? `Inspect research artifacts for ${runProduct.name}.`
            : "Inspect research artifacts and send approvals to unblock downstream steps."
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
            <div className="ds-card ds-card--md bg-amber-50 text-amber-900 text-sm shadow-none">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin text-amber-700" />
                  <span className="font-semibold">Workflow running</span>
                </div>
                <span className="text-xs text-amber-800/80">Auto-refreshing every 15s</span>
              </div>
              {latestLog ? (
                <div className="mt-2 text-xs text-amber-800">
                  Latest activity: {formatStepLabel(latestLog.step)} ({latestLog.status}) |{" "}
                  {formatDate(latestLog.created_at)}
                </div>
              ) : (
                <div className="mt-2 text-xs text-amber-800">Waiting for the first activity update...</div>
              )}
            </div>
          ) : null}
          {run?.product_id && product?.id && run.product_id !== product.id ? (
            <div className="ds-card ds-card--md bg-amber-50 text-amber-900 text-sm shadow-none flex items-center justify-between">
              <div>
                This workflow is scoped to{" "}
                <span className="font-semibold">{runProduct?.name || run.product_id}</span>. Switch product to review
                artifacts in context.
              </div>
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
            </div>
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
                  <div className="text-sm font-semibold text-content">Review & approvals</div>
                  <div className="text-xs text-content-muted">
                    {isOnboarding
                      ? "Approve canon and metric schema to let onboarding finish."
                      : isCampaignPlanning
                      ? "Review the strategy sheet and approve to continue."
                      : "This workflow type has no manual approvals."}
                  </div>
                </div>
              </div>
              {isOnboarding ? (
                <div className="mt-3 space-y-2 text-sm">
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleApproveCanon}
                    disabled={approvalsDisabled || signal.isPending}
                  >
                    {signal.isPending ? "Sending…" : "Approve canon"}
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={handleApproveMetric}
                    disabled={approvalsDisabled || signal.isPending}
                  >
                    {signal.isPending ? "Sending…" : "Approve metric schema"}
                  </Button>
                  {approvalsDisabled ? (
                    <div className="text-xs text-content-muted">Approvals disabled because the run is not active.</div>
                  ) : null}
                </div>
              ) : isCampaignPlanning ? (
                <div className="mt-3 space-y-2 text-sm">
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleApproveStrategy}
                    disabled={approvalsDisabled || signal.isPending}
                  >
                    {signal.isPending ? "Sending…" : "Approve strategy sheet"}
                  </Button>
                  {approvalsDisabled ? (
                    <div className="text-xs text-content-muted">Approvals disabled because the run is not active.</div>
                  ) : null}
                </div>
              ) : (
                <div className="mt-3 ds-card ds-card--sm bg-surface-2 text-xs text-content-muted">
                  This workflow type has no manual approvals.
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

          {isCampaignPlanning && experimentArtifacts?.length ? (
            <div className="ds-card ds-card--md p-0 shadow-none">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <div>
                  <div className="text-sm font-semibold text-content">Angle specs</div>
                  <div className="text-xs text-content-muted">Generated from canon and metric schema.</div>
                </div>
              </div>
              <div className="space-y-3 p-4 text-sm">
                {experimentArtifacts.map((art) => {
                  const specs = (art.data as any)?.experimentSpecs || [];
                  return specs.map((exp: any) => (
                    <div key={`${art.id}-${exp.id}`} className="ds-card ds-card--sm bg-surface-2">
                      <div className="flex items-center justify-between">
                        <div className="text-sm font-semibold text-content">{exp.name || exp.id}</div>
                        <span className="text-xs text-content-muted font-mono">{exp.id}</span>
                      </div>
                      <div className="mt-1 text-xs text-content-muted">{truncate(exp.hypothesis, 200)}</div>
                      <div className="mt-2 text-xs text-content-muted">
                        Metrics: {(exp.metricIds || []).join(", ") || "—"} · Variants: {(exp.variants || []).length}
                      </div>
                    </div>
                  ));
                })}
              </div>
            </div>
          ) : null}

          {isCampaignPlanning && assetBriefArtifacts?.length ? (
            <div className="ds-card ds-card--md p-0 shadow-none">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <div>
                  <div className="text-sm font-semibold text-content">Creative briefs</div>
                  <div className="text-xs text-content-muted">Derived from angle variants.</div>
                </div>
              </div>
              <div className="space-y-3 p-4 text-sm">
                {assetBriefArtifacts.map((art) => {
                  const briefs = (art.data as any)?.asset_briefs || [];
                  return briefs.map((brief: any) => {
                    const requirements = brief.requirements || [];
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
                                • {r.channel} / {r.format} {r.angle ? `– ${r.angle}` : ""} {r.hook ? `(${truncate(r.hook, 60)})` : ""}
                              </div>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    );
                  });
                })}
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
