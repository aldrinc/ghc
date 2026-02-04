import { useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";
import { useWorkflows, useWorkflowDetail } from "@/api/workflows";
import { useLatestArtifact } from "@/api/artifacts";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";

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

export function WorkspaceOverviewPage() {
  const navigate = useNavigate();
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const { data: workflows = [], isLoading: workflowsLoading, refetch: refetchWorkflows } = useWorkflows();

  const workspaceWorkflows = useMemo(
    () =>
      workflows
        .filter((wf) => wf.client_id === workspace?.id && (!product?.id || wf.product_id === product.id))
        .sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime()),
    [workflows, workspace?.id, product?.id]
  );
  const latestWorkflow = workspaceWorkflows[0];
  const { data: workflowDetail, refetch: refetchWorkflowDetail } = useWorkflowDetail(latestWorkflow?.id);
  const latestRun = workflowDetail?.run ?? latestWorkflow;
  const latestLog = workflowDetail?.logs?.[0];
  const isRunning = latestRun?.status === "running";

  const { latest: canonArtifact } = useLatestArtifact({
    clientId: workspace?.id,
    productId: product?.id,
    type: "client_canon",
  });
  const { latest: strategyArtifact } = useLatestArtifact({
    clientId: workspace?.id,
    productId: product?.id,
    type: "strategy_sheet",
  });
  const { latest: experimentsArtifact } = useLatestArtifact({
    clientId: workspace?.id,
    productId: product?.id,
    type: "experiment_spec",
  });

  const researchHighlights =
    (workflowDetail?.research_highlights as Record<string, string>) ||
    (workflowDetail?.precanon_research as any)?.step_summaries ||
    (canonArtifact?.data as any)?.precanon_research?.step_summaries ||
    {};
  const strategy = (workflowDetail?.strategy_sheet?.data ||
    strategyArtifact?.data ||
    {}) as Record<string, any>;
  const experiments =
    (workflowDetail?.experiment_specs as any[]) ||
    (experimentsArtifact?.data as any)?.experimentSpecs ||
    [];

  useEffect(() => {
    if (!latestRun?.id || latestRun.status !== "running") return;
    const interval = window.setInterval(() => {
      void refetchWorkflows();
      void refetchWorkflowDetail();
    }, 15000);
    return () => window.clearInterval(interval);
  }, [latestRun?.id, latestRun?.status, refetchWorkflows, refetchWorkflowDetail]);

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Workspace overview" description="Select a workspace to view status and outputs." />
        <div className="ds-card ds-card--md ds-card--empty text-center text-sm">
          Choose a workspace from the sidebar or workspace list.
        </div>
      </div>
    );
  }
  if (!product) {
    return (
      <div className="space-y-4">
        <PageHeader title="Workspace overview" description="Select a product to view product-scoped research." />
        <div className="ds-card ds-card--md ds-card--empty text-center text-sm">
          Choose a product from the header to view research and onboarding outputs.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title={workspace.name}
        description={
          workspace.industry ? `${product.name} · ${workspace.industry}` : `${product.name} · Workspace overview`
        }
        actions={
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => navigate("/workflows")}>
              View workflows
            </Button>
            <Button variant="primary" size="sm" onClick={() => navigate("/workspaces/new")}>
              New onboarding
            </Button>
          </div>
        }
      />

      <div className="grid gap-4 md:grid-cols-3">
        <div className="ds-card ds-card--md">
          <div className="text-sm font-semibold text-content">Latest workflow</div>
          {workflowsLoading ? (
            <div className="mt-2 text-xs text-content-muted">Loading…</div>
          ) : latestRun ? (
            <div className="mt-2 space-y-2 text-xs text-content">
              <div className="flex items-center justify-between">
                <span className="font-semibold">{latestRun.kind}</span>
                <StatusBadge status={latestRun.status} />
              </div>
              <div className="text-content-muted">Started: {formatDate(latestRun.started_at)}</div>
              <div className="text-content-muted">Finished: {formatDate(latestRun.finished_at)}</div>
              <Button
                variant="secondary"
                size="xs"
                className="mt-2"
                onClick={() => navigate(`/workflows/${latestRun.id}`)}
              >
                Open workflow
              </Button>
              {isRunning ? (
                <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
                  <div className="flex items-center gap-2">
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-700" />
                    <span className="font-semibold">Workflow running</span>
                    <span className="text-amber-800/80">Auto-refreshing every 15s</span>
                  </div>
                  {latestLog ? (
                    <div className="mt-1 text-amber-800">
                      Latest activity: {formatStepLabel(latestLog.step)} ({latestLog.status}) |{" "}
                      {formatDate(latestLog.created_at)}
                    </div>
                  ) : (
                    <div className="mt-1 text-amber-800">Waiting for the first activity update...</div>
                  )}
                </div>
              ) : null}
            </div>
          ) : (
            <div className="mt-2 text-xs text-content-muted">
              No workflows yet. Start onboarding to kick off the first run.
            </div>
          )}
        </div>

        <div className="ds-card ds-card--md">
          <div className="text-sm font-semibold text-content">Research highlights</div>
          {Object.keys(researchHighlights || {}).length ? (
            <div className="mt-2 space-y-2 text-xs text-content-muted">
              {Object.entries(researchHighlights)
                .slice(0, 3)
                .map(([step, summary]) => (
                  <div key={step} className="ds-card ds-card--sm bg-surface-2">
                    <div className="text-[11px] font-semibold text-content">Step {step}</div>
                    <div className="mt-1">{summary as string}</div>
                  </div>
                ))}
            </div>
          ) : (
            <div className="mt-2 text-xs text-content-muted">Research will appear after onboarding runs.</div>
          )}
          <Button variant="link" size="xs" className="mt-2 px-0" onClick={() => navigate("/research/documents")}>
            View documents
          </Button>
        </div>

        <div className="ds-card ds-card--md">
          <div className="text-sm font-semibold text-content">Strategy & angles</div>
          {strategy && (strategy.goal || strategy.hypothesis) ? (
            <div className="mt-2 text-xs text-content">
              <div className="font-semibold text-content">Goal</div>
              <div className="text-content-muted">{strategy.goal || "—"}</div>
              <div className="font-semibold text-content mt-2">Hypothesis</div>
              <div className="text-content-muted">{strategy.hypothesis || "—"}</div>
            </div>
          ) : (
            <div className="mt-2 text-xs text-content-muted">No strategy sheet yet.</div>
          )}
          <div className="mt-2 text-xs text-content-muted">Angles: {experiments?.length || 0}</div>
          <div className="mt-2 text-xs text-content-muted">
            Strategy sheets and angles are now reviewed inside each campaign.
          </div>
          <Button variant="secondary" size="xs" className="mt-2" onClick={() => navigate("/campaigns")}>
            View campaigns
          </Button>
        </div>
      </div>
    </div>
  );
}
