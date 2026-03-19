import { useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle2, Loader2, AlertTriangle, Rocket } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";
import { EmptyState } from "@/components/layout/EmptyState";
import { InlineWorkspacePicker } from "@/components/layout/InlineWorkspacePicker";
import { useWorkflows, useWorkflowDetail } from "@/api/workflows";
import { useLatestArtifact } from "@/api/artifacts";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Progress } from "@/components/ui/progress";
import {
  GATE_LABELS,
  GATE_EXPLANATIONS,
  GATE_SEQUENCE,
} from "@/components/workflows/StrategyGateProgress";
import type { StrategyV2PendingSignal } from "@/components/workflows/StrategyV2ReviewWorkspace";

/* ---------- progress-step maps ---------- */

const ONBOARDING_STEP_PROGRESS: Record<string, { pct: number; label: string }> = {
  gather_inputs: { pct: 10, label: "Gathering inputs..." },
  research_baseline: { pct: 25, label: "Running market research..." },
  research_competitors: { pct: 35, label: "Analyzing competitors..." },
  deep_research: { pct: 45, label: "Deep research in progress..." },
  canon_generation: { pct: 60, label: "Building brand canon..." },
  strategy_generation: { pct: 75, label: "Generating strategy..." },
  angle_scaffolding: { pct: 85, label: "Creating angle plans..." },
};

const STRATEGY_STAGE_PROGRESS: Record<string, { pct: number; label: string }> = {
  "v2-02.foundation": { pct: 10, label: "Gathering foundational data..." },
  "v2-02a": { pct: 15, label: "Pre-research phase..." },
  "v2-02b": { pct: 25, label: "Research ready for review" },
  "v2-02": { pct: 30, label: "Processing research..." },
  "v2-03": { pct: 40, label: "Synthesizing findings..." },
  "v2-04": { pct: 45, label: "Building analysis..." },
  "v2-05": { pct: 50, label: "Scoring candidates..." },
  "v2-06": { pct: 55, label: "Generating angles..." },
  "v2-03..v2-06": { pct: 50, label: "Processing stages 3-6..." },
  "v2-07": { pct: 60, label: "Evaluating messaging..." },
  "v2-08": { pct: 70, label: "Scoring messaging pairs..." },
  "v2-08b": { pct: 80, label: "Evaluating offers..." },
  "v2-09": { pct: 85, label: "Generating copy..." },
  "v2-10": { pct: 90, label: "Finalizing copy..." },
  "v2-11": { pct: 95, label: "Final review stage..." },
  completed: { pct: 100, label: "Complete" },
};

/* ---------- page mode ---------- */

type PageMode =
  | "onboarding-running"
  | "strategy-auto-running"
  | "strategy-needs-input"
  | "strategy-complete-no-campaign"
  | "campaigns-active"
  | "default";

/* ---------- helpers ---------- */

function formatDate(value?: string | null) {
  if (!value) return "\u2014";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatStepLabel(step: string) {
  return step
    .split("_")
    .map((chunk) => (chunk ? chunk[0].toUpperCase() + chunk.slice(1) : chunk))
    .join(" ");
}

/* ---------- component ---------- */

export function WorkspaceOverviewPage() {
  const navigate = useNavigate();
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const {
    data: workflows = [],
    isLoading: workflowsLoading,
    refetch: refetchWorkflows,
  } = useWorkflows();

  const workspaceWorkflows = useMemo(
    () =>
      workflows
        .filter(
          (wf) =>
            wf.client_id === workspace?.id &&
            (!product?.id || wf.product_id === product.id),
        )
        .sort(
          (a, b) =>
            new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
        ),
    [workflows, workspace?.id, product?.id],
  );

  const latestWorkflow = workspaceWorkflows[0];
  const { data: workflowDetail, refetch: refetchWorkflowDetail } =
    useWorkflowDetail(latestWorkflow?.id);
  const latestRun = workflowDetail?.run ?? latestWorkflow;
  const latestLog = workflowDetail?.logs?.[0];
  const isRunning = latestRun?.status === "running";

  /* strategy v2 specific data */
  const strategyV2State = workflowDetail?.strategy_v2_state;
  const pendingSignal = (strategyV2State?.pending_signal_type ??
    strategyV2State?.required_signal_type ??
    null) as StrategyV2PendingSignal | null;
  const strategyV2Launches = useMemo(
    () =>
      Array.isArray(workflowDetail?.strategy_v2_launches)
        ? workflowDetail.strategy_v2_launches
        : [],
    [workflowDetail?.strategy_v2_launches],
  );

  /* artifacts */
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

  /* polling for running workflows */
  useEffect(() => {
    if (!latestRun?.id || latestRun.status !== "running") return;
    const interval = window.setInterval(() => {
      void refetchWorkflows();
      void refetchWorkflowDetail();
    }, 15000);
    return () => window.clearInterval(interval);
  }, [latestRun?.id, latestRun?.status, refetchWorkflows, refetchWorkflowDetail]);

  /* compute page mode */
  const pageMode: PageMode = useMemo(() => {
    if (!latestRun) return "default";

    if (latestRun.kind === "client_onboarding" && latestRun.status === "running") {
      return "onboarding-running";
    }

    if (latestRun.kind === "strategy_v2") {
      if (pendingSignal) return "strategy-needs-input";
      if (latestRun.status === "running") return "strategy-auto-running";
      if (latestRun.status === "completed" && strategyV2Launches.length === 0)
        return "strategy-complete-no-campaign";
      if (strategyV2Launches.length > 0) return "campaigns-active";
    }

    return "default";
  }, [latestRun, pendingSignal, strategyV2Launches.length]);

  /* ---------- early returns: empty states ---------- */

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader
          title="Workspace overview"
          description="Select a workspace to view status and outputs."
        />
        <EmptyState
          title="No workspace selected"
          description="Choose a workspace to view status and outputs."
          actions={<InlineWorkspacePicker />}
        />
      </div>
    );
  }
  if (!product) {
    return (
      <div className="space-y-4">
        <PageHeader
          title="Workspace overview"
          description="Select a product to view product-scoped research."
        />
        <EmptyState
          title="No product selected"
          description="Choose a product from the header to view research and onboarding outputs."
        />
      </div>
    );
  }

  /* ---------- sub-renders ---------- */

  const header = (
    <PageHeader
      title={workspace.name}
      description={
        workspace.industry
          ? `${product.title} \u00b7 ${workspace.industry}`
          : `${product.title} \u00b7 Workspace overview`
      }
      actions={
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate("/strategy")}
          >
            View workflows
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => navigate("/workspaces/new")}
          >
            New onboarding
          </Button>
        </div>
      }
    />
  );

  /* --- three-card grid (original layout) --- */

  const threeCardGrid = (
    <div className="grid gap-4 md:grid-cols-3">
      {/* Latest workflow */}
      <div className="ds-card ds-card--md">
        <div className="text-sm font-semibold text-content">Latest workflow</div>
        {workflowsLoading ? (
          <div className="mt-2 text-xs text-content-muted">Loading\u2026</div>
        ) : latestRun ? (
          <div className="mt-2 space-y-2 text-xs text-content">
            <div className="flex items-center justify-between">
              <span className="font-semibold">{latestRun.kind}</span>
              <StatusBadge status={latestRun.status} />
            </div>
            <div className="text-content-muted">
              Started: {formatDate(latestRun.started_at)}
            </div>
            <div className="text-content-muted">
              Finished: {formatDate(latestRun.finished_at)}
            </div>
            <Button
              variant="secondary"
              size="xs"
              className="mt-2"
              onClick={() => navigate(`/strategy/${latestRun.id}`)}
            >
              Open workflow
            </Button>
            {isRunning ? (
              <Callout
                variant="warning"
                size="sm"
                title="Workflow running"
                icon={<Loader2 className="h-3.5 w-3.5 animate-spin" />}
                actions={
                  <span className="text-xs text-content-muted">
                    Auto-refreshing every 15s
                  </span>
                }
              >
                {latestLog ? (
                  <>
                    Latest activity: {formatStepLabel(latestLog.step)} (
                    {latestLog.status}) | {formatDate(latestLog.created_at)}
                  </>
                ) : (
                  <>Waiting for the first activity update...</>
                )}
              </Callout>
            ) : null}
          </div>
        ) : (
          <div className="mt-2 text-xs text-content-muted">
            No workflows yet. Start onboarding to kick off the first run.
          </div>
        )}
      </div>

      {/* Research highlights */}
      <div className="ds-card ds-card--md">
        <div className="text-sm font-semibold text-content">
          Research highlights
        </div>
        {Object.keys(researchHighlights || {}).length ? (
          <div className="mt-2 space-y-2 text-xs text-content-muted">
            {Object.entries(researchHighlights)
              .slice(0, 3)
              .map(([step, summary]) => (
                <div key={step} className="ds-card ds-card--sm bg-surface-2">
                  <div className="text-[11px] font-semibold text-content">
                    Step {step}
                  </div>
                  <div className="mt-1">{summary as string}</div>
                </div>
              ))}
          </div>
        ) : (
          <div className="mt-2 text-xs text-content-muted">
            Research will appear after onboarding runs.
          </div>
        )}
        <Button
          variant="link"
          size="xs"
          className="mt-2 px-0"
          onClick={() => navigate("/research/documents")}
        >
          View documents
        </Button>
      </div>

      {/* Strategy & angles */}
      <div className="ds-card ds-card--md">
        <div className="text-sm font-semibold text-content">
          Strategy &amp; angles
        </div>
        {strategy && (strategy.goal || strategy.hypothesis) ? (
          <div className="mt-2 text-xs text-content">
            <div className="font-semibold text-content">Goal</div>
            <div className="text-content-muted">{strategy.goal || "\u2014"}</div>
            <div className="font-semibold text-content mt-2">Hypothesis</div>
            <div className="text-content-muted">
              {strategy.hypothesis || "\u2014"}
            </div>
          </div>
        ) : (
          <div className="mt-2 text-xs text-content-muted">
            No strategy sheet yet.
          </div>
        )}
        <div className="mt-2 text-xs text-content-muted">
          Angles: {experiments?.length || 0}
        </div>
        <div className="mt-2 text-xs text-content-muted">
          Strategy sheets and angles are now reviewed inside each campaign.
        </div>
        <Button
          variant="secondary"
          size="xs"
          className="mt-2"
          onClick={() => navigate("/campaigns")}
        >
          View campaigns
        </Button>
      </div>
    </div>
  );

  /* --- mode-specific bodies --- */

  const renderOnboardingRunning = () => {
    const currentStep = latestLog?.step ?? "";
    const stepProgress =
      ONBOARDING_STEP_PROGRESS[currentStep] ?? { pct: 5, label: "Starting up..." };

    return (
      <div className="ds-card ds-card--md space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-content">
            Setting up your workspace
          </h2>
          <p className="mt-1 text-sm text-content-muted">
            Running market research and building your brand profile. When it
            finishes, we'll automatically start your strategy review.
          </p>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-content-muted">
            <span className="flex items-center gap-1.5">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />
              {stepProgress.label}
            </span>
            <span>{stepProgress.pct}%</span>
          </div>
          <Progress value={stepProgress.pct} />
        </div>

        <Callout variant="info" size="sm">
          You can leave this page &mdash; we'll keep working in the background.
          When we need your input, you'll see it here.
        </Callout>
      </div>
    );
  };

  const renderStrategyAutoRunning = () => {
    const currentStage = strategyV2State?.current_stage ?? "";
    const stageProgress =
      STRATEGY_STAGE_PROGRESS[currentStage] ?? { pct: 5, label: "Starting up..." };

    return (
      <div className="ds-card ds-card--md space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-content">
            Building your strategy
          </h2>
          <p className="mt-1 text-sm text-content-muted">
            The system is generating research, angles, and messaging options.
            We'll ask for your input when decisions are needed.
          </p>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-content-muted">
            <span className="flex items-center gap-1.5">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />
              {stageProgress.label}
            </span>
            <span>{stageProgress.pct}%</span>
          </div>
          <Progress value={stageProgress.pct} />
        </div>

        <p className="text-sm text-content-muted">
          Nothing to do yet &mdash; we'll let you know when we need you.
        </p>
      </div>
    );
  };

  const renderStrategyNeedsInput = () => {
    const gateIndex = pendingSignal
      ? GATE_SEQUENCE.indexOf(pendingSignal)
      : -1;
    const gateNumber = gateIndex >= 0 ? gateIndex + 1 : null;
    const gateLabel = pendingSignal ? GATE_LABELS[pendingSignal] : "Unknown gate";
    const gateExplanation = pendingSignal
      ? GATE_EXPLANATIONS[pendingSignal]
      : "";

    const hasGridData =
      Object.keys(researchHighlights || {}).length > 0 ||
      Boolean(strategy?.goal || strategy?.hypothesis) ||
      (experiments?.length ?? 0) > 0;

    return (
      <>
        <Callout
          variant="warning"
          icon={<AlertTriangle className="h-4 w-4" />}
          title="Your input is needed"
          actions={
            <Button
              variant="primary"
              size="sm"
              onClick={() => navigate(`/strategy/${latestRun!.id}`)}
            >
              Review and decide
            </Button>
          }
        >
          <div className="space-y-1">
            <p>
              <span className="font-medium">{gateLabel}:</span> {gateExplanation}
            </p>
            {gateNumber != null && (
              <p className="text-[11px] text-content-muted">
                Gate {gateNumber} of {GATE_SEQUENCE.length}
              </p>
            )}
          </div>
        </Callout>

        {hasGridData && threeCardGrid}
      </>
    );
  };

  const renderStrategyCompleteNoCampaign = () => (
    <div className="ds-card ds-card--md space-y-4">
      <div className="flex items-start gap-3">
        <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" />
        <div>
          <h2 className="text-lg font-semibold text-content">
            Strategy ready &mdash; launch your campaign
          </h2>
          <p className="mt-1 text-sm text-content-muted">
            Your strategy has been finalized. Review the outputs and launch your
            first campaign.
          </p>
        </div>
      </div>
      <Button
        variant="primary"
        size="sm"
        onClick={() => navigate(`/strategy/${latestRun!.id}`)}
      >
        Review strategy &amp; launch
      </Button>
    </div>
  );

  const renderCampaignsActive = () => (
    <>
      <div className="ds-card ds-card--md space-y-3">
        <div className="flex items-start gap-3">
          <Rocket className="mt-0.5 h-5 w-5 shrink-0 text-accent" />
          <div>
            <h2 className="text-lg font-semibold text-content">
              Campaigns active
            </h2>
            <p className="mt-1 text-sm text-content-muted">
              {strategyV2Launches.length} launch
              {strategyV2Launches.length === 1 ? "" : "es"} from your strategy.
            </p>
          </div>
        </div>

        <div className="space-y-2">
          {strategyV2Launches.slice(0, 5).map((launch) => (
            <div
              key={launch.id}
              className="ds-card ds-card--sm flex items-center justify-between bg-surface-2"
            >
              <div className="min-w-0 text-xs">
                <div className="font-semibold text-content truncate">
                  {launch.launch_key}
                </div>
                <div className="text-content-muted">
                  {launch.launch_type.replace(/_/g, " ")}
                  {launch.launch_status ? ` \u00b7 ${launch.launch_status}` : ""}
                </div>
              </div>
              {launch.campaign_id && (
                <StatusBadge status={launch.launch_status ?? "pending"} />
              )}
            </div>
          ))}
        </div>

        <Button
          variant="link"
          size="sm"
          className="px-0"
          onClick={() => navigate(`/strategy/${latestRun!.id}`)}
        >
          Manage strategy &amp; launch more angles &rarr;
        </Button>
      </div>

      {threeCardGrid}
    </>
  );

  /* ---------- main render ---------- */

  const modeBody = (() => {
    switch (pageMode) {
      case "onboarding-running":
        return renderOnboardingRunning();
      case "strategy-auto-running":
        return renderStrategyAutoRunning();
      case "strategy-needs-input":
        return renderStrategyNeedsInput();
      case "strategy-complete-no-campaign":
        return renderStrategyCompleteNoCampaign();
      case "campaigns-active":
        return renderCampaignsActive();
      case "default":
      default:
        return threeCardGrid;
    }
  })();

  return (
    <div className="space-y-4">
      {header}
      {modeBody}
    </div>
  );
}
