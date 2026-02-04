import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useWorkflows } from "@/api/workflows";
import { StatusBadge } from "@/components/StatusBadge";
import type { WorkflowRun } from "@/types/common";

function needsAttention(run: WorkflowRun) {
  return run.status === "failed" || run.status === "running";
}

export function TasksPage() {
  const { data: workflows, isLoading } = useWorkflows();
  const navigate = useNavigate();

  const attentionList = useMemo(() => (workflows || []).filter(needsAttention), [workflows]);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Tasks & Approvals"
        description="Workflows that are running, failed, or awaiting review."
      />

      <div className="ds-card ds-card--md p-0 shadow-none">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <div className="text-sm font-semibold text-content">Needs attention</div>
            <div className="text-xs text-content-muted">
              Showing running or failed workflows. Approvals are triggered from the workflow detail view.
            </div>
          </div>
          <Button variant="secondary" size="sm" onClick={() => navigate("/workflows")}>
            View all workflows
          </Button>
        </div>

        {isLoading ? (
          <div className="p-4 text-sm text-content-muted">Loading workflows…</div>
        ) : (
          <ScrollArea className="max-h-[480px]">
            <ul className="divide-y divide-border">
              {attentionList.map((wf) => (
                <li key={wf.id} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-surface-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-content">{wf.kind}</span>
                      <StatusBadge status={wf.status} />
                    </div>
                    <div className="text-xs text-content-muted">
                      Client: {wf.client_id || "—"} · Campaign: {wf.campaign_id || "—"}
                    </div>
                    <div className="text-xs text-content-muted">Started: {wf.started_at}</div>
                  </div>
                  <Button variant="primary" size="sm" onClick={() => navigate(`/workflows/${wf.id}`)}>
                    Review
                  </Button>
                </li>
              ))}
              {!attentionList.length && (
                <li className="px-4 py-4 text-sm text-content-muted">No workflows need attention right now.</li>
              )}
            </ul>
          </ScrollArea>
        )}
      </div>
    </div>
  );
}
