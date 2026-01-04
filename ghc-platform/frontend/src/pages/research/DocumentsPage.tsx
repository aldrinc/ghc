import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useWorkflows, useWorkflowDetail } from "@/api/workflows";
import type { ResearchArtifactRef } from "@/types/common";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";

type DocumentRow = {
  key: string;
  workflowId: string;
  stepKey: string;
  summary: string;
  docUrl?: string;
  source?: "workflow" | "canon" | "mixed";
};

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="ds-card ds-card--md ds-card--empty text-center text-sm">
      <div className="text-content font-semibold">{title}</div>
      <div className="mt-1 text-content-muted">{description}</div>
    </div>
  );
}

export function DocumentsPage() {
  const navigate = useNavigate();
  const { workspace } = useWorkspace();
  const { data: workflows = [], isLoading: isWorkflowsLoading } = useWorkflows();
  const latestWorkflow = useMemo(() => {
    const workspaceRuns = workflows
      .filter((wf) => wf.client_id === workspace?.id)
      .sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());
    const onboarding = workspaceRuns.find((wf) => wf.kind === "client_onboarding");
    return onboarding || workspaceRuns[0];
  }, [workflows, workspace?.id]);
  const {
    data: workflowDetail,
    isLoading: isWorkflowDetailLoading,
  } = useWorkflowDetail(latestWorkflow?.id);

  const stepSummaries =
    (workflowDetail?.precanon_research?.step_summaries as Record<string, string> | undefined) || {};

  const rows: DocumentRow[] = useMemo(() => {
    if (!latestWorkflow?.id) return [];
    const artifacts = (workflowDetail?.research_artifacts || []) as ResearchArtifactRef[];
    const seen = new Set<string>();
    return artifacts.reduce<DocumentRow[]>((acc, art) => {
      const stepKey = art.step_key;
      if (!stepKey) return acc;
      const key = `${latestWorkflow.id}:${stepKey}`;
      if (seen.has(key)) return acc;
      seen.add(key);
      acc.push({
        key,
        workflowId: latestWorkflow.id,
        stepKey,
        summary: art.summary || stepSummaries[stepKey] || "",
        docUrl: art.doc_url || undefined,
        source: "workflow",
      });
      return acc;
    }, []);
  }, [latestWorkflow?.id, stepSummaries, workflowDetail?.research_artifacts]);

  const isLoading = isWorkflowsLoading || isWorkflowDetailLoading;

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Documents" description="Select a workspace to view research docs." />
        <EmptyState title="No workspace selected" description="Choose a workspace from the sidebar to load documents." />
      </div>
    );
  }

  return (
    <div className="space-y-4 max-w-6xl mx-auto">
      <PageHeader
        title="Documents"
        description="Research docs captured during onboarding and pre-canon research. View workflow steps and open full details."
      />

      {isLoading ? (
        <div className="ds-card ds-card--md text-sm text-content-muted shadow-none">Loading documents…</div>
      ) : !latestWorkflow?.id ? (
        <div className="space-y-3">
          <EmptyState
            title="No workflow found"
            description="Start a workflow for this workspace to generate research documents."
          />
          <div className="flex justify-center">
            <Button variant="secondary" size="sm" onClick={() => navigate("/workflows")}>
              View workflows
            </Button>
          </div>
        </div>
      ) : !rows.length ? (
        <div className="space-y-3">
          <EmptyState
            title="No research documents found"
            description="Run the workflow to generate research artifacts for this workspace."
          />
          <div className="flex justify-center">
            <Button variant="secondary" size="sm" onClick={() => navigate("/workflows")}>
              View workflows
            </Button>
          </div>
        </div>
      ) : (
        <div className="ds-card ds-card--md p-0 shadow-none">
          <div className="flex items-center justify-between border-b border-border/70 px-4 py-3">
            <div>
              <div className="text-sm font-semibold text-content">Research documents</div>
              <div className="text-xs text-content-muted">Open workflow-backed research detail pages.</div>
            </div>
            <Button variant="secondary" size="sm" onClick={() => navigate(`/workflows/${latestWorkflow.id}`)}>
              View workflow
            </Button>
          </div>
          <div className="overflow-x-auto">
            <Table variant="ghost">
              <TableHeader>
                <TableRow>
                  <TableHeadCell>Step</TableHeadCell>
                  <TableHeadCell>Summary</TableHeadCell>
                  <TableHeadCell className="text-right">Actions</TableHeadCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow
                    key={row.key}
                    hover
                    className="cursor-pointer"
                    onClick={() => navigate(`/workflows/${row.workflowId}/research/${row.stepKey}`)}
                  >
                    <TableCell className="font-semibold text-content">Step {row.stepKey}</TableCell>
                    <TableCell className="text-sm text-content-muted">
                      {row.summary || "No summary provided."}
                    </TableCell>
                    <TableCell className="text-right space-x-2">
                      <Button
                        variant="secondary"
                        size="xs"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/workflows/${row.workflowId}/research/${row.stepKey}`);
                        }}
                      >
                        View
                      </Button>
                      {row.docUrl ? (
                        <a
                          href={row.docUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-primary underline"
                          onClick={(e) => e.stopPropagation()}
                        >
                          Open doc
                        </a>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}
    </div>
  );
}
