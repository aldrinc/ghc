import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { useWorkflowDetail } from "@/api/workflows";
import type { ResearchArtifactRef } from "@/types/common";

export function ResearchDetailPage() {
  const { workflowId, stepKey } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, isError } = useWorkflowDetail(workflowId);

  const artifact: ResearchArtifactRef | undefined = useMemo(() => {
    const list = data?.research_artifacts || [];
    return list.find((a) => a.step_key === stepKey);
  }, [data?.research_artifacts, stepKey]);

  const stepSummaries = (data?.precanon_research?.step_summaries as Record<string, string> | undefined) || {};
  const stepContents = (data?.precanon_research?.step_contents as Record<string, string> | undefined) || {};

  const summary = artifact?.summary || stepSummaries[stepKey || ""] || "";
  const content = artifact?.content || stepContents[stepKey || ""] || "";

  return (
    <div className="space-y-4">
      <PageHeader
        title={`Research Step ${stepKey}`}
        description="Full research output captured during pre-canon."
        actions={
          <Button variant="secondary" size="sm" onClick={() => navigate(-1)}>
            Back
          </Button>
        }
      />

      {isLoading ? (
        <div className="rounded-lg border border-border bg-surface p-4 text-sm text-content-muted">Loading…</div>
      ) : isError || !artifact ? (
        <div className="rounded-lg border border-border bg-surface p-4 text-sm text-danger">
          Research artifact not found for this step.
        </div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-lg border border-border bg-surface p-4 shadow-sm">
            <div className="text-sm font-semibold text-content">Summary</div>
            <div className="mt-2 whitespace-pre-line text-sm text-content">{summary || "No summary available."}</div>
          </div>
          <div className="rounded-lg border border-border bg-surface p-4 shadow-sm">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-content">Full content</div>
              {artifact.doc_url ? (
                <a className="text-xs text-primary underline" href={artifact.doc_url} target="_blank" rel="noreferrer">
                  Open doc
                </a>
              ) : null}
            </div>
            <div className="mt-2 whitespace-pre-line text-sm text-content">
              {content || "No content captured for this step."}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
