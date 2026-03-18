import { ArrowLeft, ChevronRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { MarkdownViewer } from "@/components/ui/MarkdownViewer";

export type FileRuntimeState = {
  status: "idle" | "loading" | "loaded" | "error";
  reviewed: boolean;
  content: string;
  error: string;
};

type ReviewFile = {
  id: string;
  title: string;
  subtitle?: string;
  stepKey?: string;
  artifactId?: string;
};

/**
 * Renders the file reader panel for reviewing strategy documents.
 * Shows the file title, loading state, markdown content, and action buttons.
 */
export function StrategyReviewFilePanel({
  file,
  runtime,
  backLabel,
  onBack,
  onMarkReviewed,
  onNextFile,
}: {
  file: ReviewFile;
  runtime: FileRuntimeState | undefined;
  backLabel: string;
  onBack: () => void;
  onMarkReviewed: () => void;
  onNextFile: () => void;
}) {
  return (
    <div className="ds-card ds-card--md space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
        <Button variant="ghost" size="xs" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
          {backLabel}
        </Button>
        <div className="text-right">
          <div className="text-xs font-semibold text-content">{file.title}</div>
          <div className="text-[11px] text-content-muted font-mono">
            {file.stepKey ? `step=${file.stepKey}` : ""}
            {file.artifactId ? ` artifact=${file.artifactId}` : ""}
          </div>
        </div>
      </div>

      {runtime?.status === "loading" ? (
        <div className="flex items-center gap-2 text-sm text-content-muted">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading full file...
        </div>
      ) : runtime?.status === "error" ? (
        <Callout variant="danger" title="Failed to load file">
          {runtime.error || "The selected file could not be loaded."}
        </Callout>
      ) : (
        <MarkdownViewer content={runtime?.content || ""} />
      )}

      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border pt-3">
        <Button
          variant="secondary"
          size="sm"
          onClick={onMarkReviewed}
          disabled={runtime?.status !== "loaded"}
        >
          Mark reviewed
        </Button>
        <Button
          variant="primary"
          size="sm"
          onClick={onNextFile}
          disabled={runtime?.status !== "loaded"}
        >
          Next required file
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
