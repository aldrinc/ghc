import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { useCampaignContext } from "@/contexts/CampaignContext";

type Tone = "neutral" | "accent" | "success" | "danger";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function CampaignOverviewTab() {
  const navigate = useNavigate();
  const {
    campaign,
    workspaceName,
    campaignProductLabel,
    workflowsLoading,
    campaignWorkflows,
    strategyArtifact,
    strategyLoading,
    experimentSpecs,
    experimentsLoading,
    assetBriefs,
    briefsLoading,
    funnels,
    funnelsLoading,
    campaignLaunches,
    campaignStrategyV2LaunchesLoading,
    latestFunnelWorkflow,
  } = useCampaignContext();

  const latestWorkflow = campaignWorkflows[0];

  const funnelWorkflowFailed = Boolean(latestFunnelWorkflow?.status === "failed" && funnels.length === 0);
  const isFunnelGenerationActive = Boolean(
    campaignWorkflows.find((wf) => wf.kind === "campaign_funnel_generation" && wf.status === "running"),
  );

  const funnelStepState = funnelsLoading
    ? "Loading"
    : isFunnelGenerationActive
      ? "Generating"
      : funnelWorkflowFailed
        ? "Failed"
        : funnels.length
          ? "Ready"
          : "Missing";
  const funnelStepTone: Tone =
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

  const flowSteps: Array<{ label: string; state: string; tone: Tone; detail: string; tab: string }> = [
    {
      label: "Strategy sheet",
      state: strategyLoading ? "Loading" : strategyArtifact ? "Ready" : "Missing",
      tone: strategyLoading ? "accent" : strategyArtifact ? "success" : "neutral",
      detail: strategyArtifact ? `Updated ${formatDate(strategyArtifact.created_at)}` : "Not generated yet",
      tab: "strategy",
    },
    {
      label: "Angle specs",
      state: experimentsLoading ? "Loading" : experimentSpecs.length ? "Ready" : "Missing",
      tone: experimentsLoading ? "accent" : experimentSpecs.length ? "success" : "neutral",
      detail: experimentSpecs.length ? `${experimentSpecs.length} specs` : "No specs yet",
      tab: "angles",
    },
    {
      label: "Creative briefs",
      state: briefsLoading ? "Loading" : assetBriefs.length ? "Ready" : "Missing",
      tone: briefsLoading ? "accent" : assetBriefs.length ? "success" : "neutral",
      detail: assetBriefs.length ? `${assetBriefs.length} briefs` : "No briefs yet",
      tab: "creative",
    },
    {
      label: "Funnels",
      state: funnelStepState,
      tone: funnelStepTone,
      detail: funnelStepDetail,
      tab: "delivery",
    },
  ];

  const campaignAngleIdentity = useMemo(() => {
    const row = campaignLaunches.find(
      (launch) => launch.launch_type === "initial_angle" || launch.launch_type === "additional_angle",
    );
    if (!row) return null;
    return {
      angle_id: row.angle_id,
      angle_run_id: row.angle_run_id,
      launch_type: row.launch_type,
      selected_ums_id: row.selected_ums_id || "primary",
    };
  }, [campaignLaunches]);

  return (
    <>
      {/* Flow status — primary content, clickable rows navigate to tabs */}
      <div className="border border-border bg-transparent p-4">
        <div className="text-base font-semibold text-content">Flow status</div>
        <div className="mt-3 space-y-1">
          {flowSteps.map((step) => (
            <button
              key={step.label}
              type="button"
              className="flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left transition-colors hover:bg-surface-2"
              onClick={() => navigate(step.tab)}
            >
              <div>
                <div className="text-sm font-semibold text-content">{step.label}</div>
                <div className="text-xs text-content-muted">{step.detail}</div>
              </div>
              <Badge tone={step.tone}>{step.state}</Badge>
            </button>
          ))}
        </div>
      </div>

      {/* Latest workflow */}
      <div className="border border-border bg-transparent p-4">
        <div className="text-base font-semibold text-content">Latest workflow</div>
        {workflowsLoading ? (
          <div className="mt-2 text-sm text-content-muted">Loading…</div>
        ) : latestWorkflow ? (
          <div className="mt-2 flex items-center justify-between text-sm text-content">
            <div className="flex items-center gap-3">
              <span className="font-semibold">{latestWorkflow.kind}</span>
              <StatusBadge status={latestWorkflow.status} />
              <span className="text-xs text-content-muted">{formatDate(latestWorkflow.started_at)}</span>
            </div>
            <Button
              variant="secondary"
              size="xs"
              onClick={() => navigate(`/strategy/${latestWorkflow.id}`)}
            >
              Open
            </Button>
          </div>
        ) : (
          <div className="mt-2 text-sm text-content-muted">No workflows yet for this campaign.</div>
        )}
      </div>

      <div className="mt-4 border border-border bg-transparent p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-base font-semibold text-content">Strategy V2 angle identity</div>
            <div className="text-sm text-content-muted">
              Campaign lineage from Strategy V2 launch records.
            </div>
          </div>
          {campaignStrategyV2LaunchesLoading ? <Badge tone="accent">Loading</Badge> : null}
        </div>
        {campaignAngleIdentity ? (
          <div className="mt-3 grid gap-2 text-sm text-content md:grid-cols-2">
            <div className="rounded-md border border-border bg-surface-2 px-3 py-2">
              <div className="text-xs text-content-muted">Angle ID</div>
              <div className="font-mono">{campaignAngleIdentity.angle_id}</div>
            </div>
            <div className="rounded-md border border-border bg-surface-2 px-3 py-2">
              <div className="text-xs text-content-muted">Angle run ID</div>
              <div className="font-mono">{campaignAngleIdentity.angle_run_id}</div>
            </div>
            <div className="rounded-md border border-border bg-surface-2 px-3 py-2">
              <div className="text-xs text-content-muted">Launch type</div>
              <div>{campaignAngleIdentity.launch_type}</div>
            </div>
            <div className="rounded-md border border-border bg-surface-2 px-3 py-2">
              <div className="text-xs text-content-muted">Latest UMS group</div>
              <div>{campaignAngleIdentity.selected_ums_id}</div>
            </div>
          </div>
        ) : (
          <div className="mt-3 text-sm text-content-muted">
            No Strategy V2 launch lineage found for this campaign yet.
          </div>
        )}
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
                      <Button variant="secondary" size="xs" onClick={() => navigate(`/strategy/${wf.id}`)}>
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
    </>
  );
}
