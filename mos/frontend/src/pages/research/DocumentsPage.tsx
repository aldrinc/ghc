import { useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";
import { useWorkflows, useWorkflowDetail } from "@/api/workflows";
import type { ResearchArtifactRef } from "@/types/common";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";

type DocumentRow = {
  key: string;
  workflowId: string;
  stepKey: string;
  summary: string;
  docUrl?: string;
  source?: "workflow" | "canon" | "mixed";
};

type CanonArtifactRef = Pick<ResearchArtifactRef, "step_key" | "doc_url" | "doc_id">;

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="ds-card ds-card--md ds-card--empty text-center text-sm">
      <div className="text-content font-semibold">{title}</div>
      <div className="mt-1 text-content-muted">{description}</div>
    </div>
  );
}

function getErrorMessage(error: unknown) {
  if (!error) return "Unknown error";
  if (typeof error === "string") return error;
  if (typeof (error as { message?: unknown })?.message === "string") return (error as { message: string }).message;
  return "Failed to load data";
}

function isCanonArtifactRef(value: unknown): value is CanonArtifactRef {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return typeof v.step_key === "string" && typeof v.doc_url === "string" && typeof v.doc_id === "string";
}

export function DocumentsPage() {
  const navigate = useNavigate();
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const {
    data: workflows = [],
    isLoading: isWorkflowsLoading,
    isError: isWorkflowsError,
    error: workflowsError,
    refetch: refetchWorkflows,
  } = useWorkflows();
  const latestWorkflow = useMemo(() => {
    const workspaceRuns = workflows
      .filter((wf) => wf.client_id === workspace?.id && (!product?.id || wf.product_id === product.id))
      .sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());
    const onboarding = workspaceRuns.find((wf) => wf.kind === "client_onboarding");
    return onboarding || workspaceRuns[0];
  }, [workflows, workspace?.id, product?.id]);
  const {
    data: workflowDetail,
    isLoading: isWorkflowDetailLoading,
    isError: isWorkflowDetailError,
    error: workflowDetailError,
    refetch: refetchWorkflowDetail,
  } = useWorkflowDetail(latestWorkflow?.id);

  const stepSummaries =
    (workflowDetail?.precanon_research?.step_summaries as Record<string, string> | undefined) || {};
  const canonArtifactRefs: CanonArtifactRef[] = useMemo(() => {
    const raw = (workflowDetail?.precanon_research as Record<string, unknown> | null)?.artifact_refs;
    if (!Array.isArray(raw)) return [];
    return raw.filter(isCanonArtifactRef);
  }, [workflowDetail?.precanon_research]);

  const rows: DocumentRow[] = useMemo(() => {
    if (!latestWorkflow?.id) return [];
    const workflowArtifacts = (workflowDetail?.research_artifacts || []) as ResearchArtifactRef[];
    const canonByStep = new Map<string, CanonArtifactRef>();
    canonArtifactRefs.forEach((ref) => {
      canonByStep.set(ref.step_key, ref);
    });

    const out: DocumentRow[] = [];
    const seenSteps = new Set<string>();

    workflowArtifacts.forEach((art) => {
      const stepKey = art.step_key;
      if (!stepKey) return;
      if (seenSteps.has(stepKey)) return;
      seenSteps.add(stepKey);

      const canonRef = canonByStep.get(stepKey);
      out.push({
        key: `${latestWorkflow.id}:${stepKey}`,
        workflowId: latestWorkflow.id,
        stepKey,
        summary: art.summary || stepSummaries[stepKey] || "",
        docUrl: art.doc_url || canonRef?.doc_url || undefined,
        source: canonRef ? "mixed" : "workflow",
      });
    });

    canonArtifactRefs.forEach((ref) => {
      const stepKey = ref.step_key;
      if (!stepKey) return;
      if (seenSteps.has(stepKey)) return;
      seenSteps.add(stepKey);
      out.push({
        key: `${latestWorkflow.id}:${stepKey}`,
        workflowId: latestWorkflow.id,
        stepKey,
        summary: stepSummaries[stepKey] || "",
        docUrl: ref.doc_url || undefined,
        source: "canon",
      });
    });

    return out;
  }, [canonArtifactRefs, latestWorkflow?.id, stepSummaries, workflowDetail?.research_artifacts]);

  const isLoading = isWorkflowsLoading || isWorkflowDetailLoading;

  useEffect(() => {
    if (!workflowDetail?.run || workflowDetail.run.status !== "running") return;
    const interval = window.setInterval(() => {
      void refetchWorkflowDetail();
    }, 15000);
    return () => window.clearInterval(interval);
  }, [workflowDetail?.run?.status, refetchWorkflowDetail]);

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Documents" description="Select a workspace to view research docs." />
        <div className="max-w-6xl mx-auto">
          <EmptyState title="No workspace selected" description="Choose a workspace from the sidebar to load documents." />
        </div>
      </div>
    );
  }
  if (!product) {
    return (
      <div className="space-y-4">
        <PageHeader title="Documents" description="Select a product to view research docs." />
        <div className="max-w-6xl mx-auto">
          <EmptyState title="No product selected" description="Choose a product from the header to load documents." />
        </div>
      </div>
    );
  }

  if (isWorkflowsError || isWorkflowDetailError) {
    const message = getErrorMessage(isWorkflowsError ? workflowsError : workflowDetailError);
    return (
      <div className="space-y-4">
        <PageHeader title="Documents" description={`Research docs captured during onboarding for ${product.name}.`} />
        <div className="max-w-6xl mx-auto space-y-3">
          <EmptyState title="Failed to load documents" description={message} />
          <div className="flex justify-center">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                refetchWorkflows();
                if (latestWorkflow?.id) refetchWorkflowDetail();
              }}
            >
              Retry
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Documents"
        description={`Research docs captured during onboarding for ${product.name}.`}
      />

      <div className="max-w-6xl mx-auto">
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
              title={workflowDetail?.run?.status === "running" ? "No documents yet" : "No research documents found"}
              description={
                workflowDetail?.run?.status === "running"
                  ? "This workflow is still running. Documents will appear here as each step completes."
                  : "Run the workflow to generate research artifacts for this workspace."
              }
            />
            <div className="flex justify-center">
              <Button variant="secondary" size="sm" onClick={() => navigate(`/workflows/${latestWorkflow.id}`)}>
                View workflow
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
                      <TableCell className="font-semibold text-content">
                        <div className="flex items-center gap-2">
                          <span>Step {row.stepKey}</span>
                          {row.source === "canon" ? <Badge>Canon</Badge> : null}
                          {row.source === "mixed" ? <Badge tone="accent">Canon + Workflow</Badge> : null}
                        </div>
                      </TableCell>
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
    </div>
  );
}
