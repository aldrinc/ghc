import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Copy, ExternalLink } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { useWorkflowDetail } from "@/api/workflows";
import type { ResearchArtifactRef } from "@/types/common";
import { MarkdownViewer } from "@/components/ui/MarkdownViewer";

type CanonArtifactRef = Pick<ResearchArtifactRef, "step_key" | "title" | "doc_url" | "doc_id">;

function isCanonArtifactRef(value: unknown): value is CanonArtifactRef {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.step_key === "string" &&
    typeof v.title === "string" &&
    typeof v.doc_url === "string" &&
    typeof v.doc_id === "string"
  );
}

export function ResearchDetailPage() {
  const { workflowId, stepKey } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, isError } = useWorkflowDetail(workflowId);
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<number | null>(null);

  const artifact: ResearchArtifactRef | undefined = useMemo(() => {
    const list = (data?.research_artifacts || []) as ResearchArtifactRef[];
    return list.find((a) => a.step_key === stepKey);
  }, [data?.research_artifacts, stepKey]);

  const canonArtifactRef = useMemo(() => {
    const raw = (data?.precanon_research as Record<string, unknown> | null)?.artifact_refs;
    if (!Array.isArray(raw)) return undefined;
    const match = raw.find((item) => isCanonArtifactRef(item) && item.step_key === stepKey);
    return isCanonArtifactRef(match) ? match : undefined;
  }, [data?.precanon_research, stepKey]);

  const stepSummaries = (data?.precanon_research?.step_summaries as Record<string, string> | undefined) || {};
  const stepContents = (data?.precanon_research?.step_contents as Record<string, string> | undefined) || {};

  const resolvedStepKey = stepKey || "";
  const resolvedTitle = (artifact?.title || canonArtifactRef?.title || "").trim();
  const hasTitle = Boolean(resolvedTitle);
  const summary = artifact?.summary || stepSummaries[resolvedStepKey] || "";
  const content = artifact?.content || stepContents[resolvedStepKey] || "";
  const docUrl = artifact?.doc_url || canonArtifactRef?.doc_url;

  const hasContent = Boolean(content?.trim());
  const displayContent = hasContent ? content : summary;
  const hasDisplayContent = Boolean(displayContent?.trim());
  const exists = Boolean(artifact || hasContent || summary?.trim() || docUrl);
  const missingTitle = Boolean(!isLoading && exists && !hasTitle);

  useEffect(() => {
    return () => {
      if (copyTimer.current) {
        window.clearTimeout(copyTimer.current);
      }
    };
  }, []);

  const handleCopyContent = async () => {
    if (!hasDisplayContent) return;
    const text = displayContent?.trim();
    if (!text) return;
    try {
      await navigator?.clipboard?.writeText(text);
      setCopied(true);
      if (copyTimer.current) window.clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="max-w-6xl mx-auto space-y-3">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-2 text-sm font-medium text-content-muted transition hover:text-content"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </button>

        <PageHeader
          title={hasTitle ? resolvedTitle : "Research document"}
          description={
            missingTitle
              ? `Missing title for step ${resolvedStepKey || "—"}.`
              : `Step ${resolvedStepKey || "—"} • Full research output captured during pre-canon.`
          }
          actions={
            hasDisplayContent || docUrl ? (
              <div className="flex items-center gap-2">
                {hasDisplayContent ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="text-content-muted hover:text-content"
                    aria-label="Copy document text"
                    title="Copy document text"
                    onClick={handleCopyContent}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                ) : null}
                {copied ? (
                  <span className="inline-flex items-center text-xs font-medium leading-none text-content">
                    Copied
                  </span>
                ) : null}
                {docUrl ? (
                  <Button
                    asChild
                    variant="ghost"
                    size="icon"
                    className="text-content-muted hover:text-content"
                    aria-label="Open document in a new tab"
                    title="Open document"
                  >
                    <a href={docUrl} target="_blank" rel="noreferrer">
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  </Button>
                ) : null}
              </div>
            ) : undefined
          }
        />
      </div>

      <div className="max-w-6xl mx-auto">
        {isLoading ? (
          <div className="ds-card ds-card--md text-sm text-content-muted">Loading…</div>
        ) : isError || !exists ? (
          <div className="ds-card ds-card--md text-sm text-danger">
            Research artifact not found for this step.
          </div>
        ) : missingTitle ? (
          <div className="ds-card ds-card--md text-sm text-danger">
            Missing research document title for step {resolvedStepKey || "—"}.
          </div>
        ) : (
          <div className="space-y-4">
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
    </div>
  );
}
