import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { useWorkflowDetail } from "@/api/workflows";
import type { ResearchArtifactRef } from "@/types/common";
import { MarkdownViewer } from "@/components/ui/MarkdownViewer";

export function ResearchDetailPage() {
  const { workflowId, stepKey } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, isError } = useWorkflowDetail(workflowId);

  const artifact: ResearchArtifactRef | undefined = useMemo(() => {
    const list = (data?.research_artifacts || []) as ResearchArtifactRef[];
    return list.find((a) => a.step_key === stepKey);
  }, [data?.research_artifacts, stepKey]);

  const stepSummaries = (data?.precanon_research?.step_summaries as Record<string, string> | undefined) || {};
  const stepContents = (data?.precanon_research?.step_contents as Record<string, string> | undefined) || {};

  const resolvedStepKey = stepKey || "";
  const summary = artifact?.summary || stepSummaries[resolvedStepKey] || "";
  const content = artifact?.content || stepContents[resolvedStepKey] || "";
  const docUrl = artifact?.doc_url;

  const hasContent = Boolean(content?.trim());
  const displayContent = hasContent ? content : summary;
  const hasDisplayContent = Boolean(displayContent?.trim());
  const exists = Boolean(artifact || hasContent || summary?.trim() || docUrl);

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <PageHeader
        title={`Research Step ${resolvedStepKey || "—"}`}
        description="Full research output captured during pre-canon."
        actions={
          <Button variant="secondary" size="sm" onClick={() => navigate(-1)}>
            Back
          </Button>
        }
      />

      {isLoading ? (
        <div className="ds-card ds-card--md text-sm text-content-muted">Loading…</div>
      ) : isError || !exists ? (
        <div className="ds-card ds-card--md text-sm text-danger">
          Research artifact not found for this step.
        </div>
      ) : (
        <div className="space-y-4">
          {docUrl ? (
            <div className="flex justify-end">
              <a className="text-xs text-primary underline" href={docUrl} target="_blank" rel="noreferrer">
                Open doc
              </a>
            </div>
          ) : null}
          {hasDisplayContent ? (
            <MarkdownViewer content={displayContent} />
          ) : (
            <div className="mx-auto w-full max-w-[75ch] ds-card ds-card--md ds-card--empty text-sm">
              {docUrl
                ? "No inline content available. Open the linked doc to view the full file."
                : "No content captured for this step."}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
