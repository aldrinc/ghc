import type {
  StrategySkillsBundleItem,
  StrategySkillsBundle,
} from "@/api/productStrategySkills";
import type { useRunStrategySkillsStage, useApproveStrategyRole } from "@/api/productStrategySkills";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MarkdownViewer } from "@/components/ui/MarkdownViewer";

export type StageDefinition = {
  key: string;
  label: string;
  role: string;
  selectionType?: "angle" | "headline";
  approvalRequired?: boolean;
};

type StageStepProps = {
  stage: StageDefinition;
  stageIndex: number;
  isActive: boolean;
  isUpcoming: boolean;
  workingItem?: StrategySkillsBundleItem | null;
  approvedItem?: StrategySkillsBundleItem | null;
  approvedBundle?: StrategySkillsBundle | null;
  runStage: ReturnType<typeof useRunStrategySkillsStage>;
  approveRole: ReturnType<typeof useApproveStrategyRole>;
};

function previewContent(item?: StrategySkillsBundleItem | null): { format: string; content: string } | null {
  if (!item) return null;
  const artifactData = item.artifactData ?? {};
  const documentFormat = String(artifactData.documentFormat ?? "").trim().toLowerCase();
  if (documentFormat === "markdown") {
    return { format: "markdown", content: String(artifactData.markdown ?? "").trim() };
  }
  if (documentFormat === "text") {
    return { format: "text", content: String(artifactData.text ?? "").trim() };
  }
  if (documentFormat === "json") {
    return { format: "json", content: JSON.stringify(artifactData.json ?? {}, null, 2) };
  }
  return { format: "unknown", content: JSON.stringify(artifactData, null, 2) };
}

export function StageStep({
  stage,
  stageIndex,
  isActive,
  isUpcoming,
  workingItem,
  approvedItem,
  approvedBundle,
  runStage,
  approveRole,
}: StageStepProps) {
  const needsApproval =
    Boolean(stage.approvalRequired) &&
    Boolean(workingItem) &&
    workingItem?.artifactId !== approvedItem?.artifactId;

  const isCompleted = Boolean(approvedItem);
  const hasDraft = Boolean(workingItem);

  if (isUpcoming && !hasDraft && !isCompleted) {
    return (
      <div className="ds-card ds-card--sm opacity-50 shadow-none">
        <div className="flex items-center gap-3 px-4 py-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-2 text-xs font-semibold text-content-muted">
            {stageIndex + 1}
          </span>
          <div>
            <div className="text-sm font-medium text-content-muted">{stage.label}</div>
          </div>
        </div>
      </div>
    );
  }

  const preview = previewContent(workingItem);
  const approvedPreview = previewContent(approvedItem);

  return (
    <div
      className={`ds-card ds-card--sm shadow-none ${isActive ? "ring-1 ring-accent/20" : ""}`}
      id={`step-stage-${stage.key}`}
    >
      <div className="flex items-center justify-between gap-3 px-4 py-3">
        <div className="flex items-center gap-3">
          <span
            className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
              isCompleted && !needsApproval
                ? "bg-success/10 text-success"
                : hasDraft
                  ? "bg-accent/10 text-accent"
                  : "bg-surface-2 text-content-muted"
            }`}
          >
            {stageIndex + 1}
          </span>
          <div>
            <div className="text-sm font-semibold text-content">{stage.label}</div>
            <div className="text-xs text-content-muted">{stage.role.replace(/_/g, " ")}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isCompleted && !needsApproval ? (
            <Badge tone="success">Approved</Badge>
          ) : hasDraft ? (
            <Badge tone="neutral">Draft</Badge>
          ) : null}
          <Button
            size="xs"
            variant={hasDraft ? "secondary" : "primary"}
            onClick={() => void runStage.mutateAsync({ stageKey: stage.key })}
            disabled={runStage.isPending}
          >
            {runStage.isPending ? "Running..." : hasDraft ? "Re-run" : "Run"}
          </Button>
          {needsApproval ? (
            <Button
              size="xs"
              onClick={() => void approveRole.mutateAsync({ role: stage.role })}
              disabled={approveRole.isPending}
            >
              {approveRole.isPending ? "Approving..." : "Approve"}
            </Button>
          ) : null}
        </div>
      </div>

      {hasDraft && preview?.content ? (
        <details className="border-t border-border">
          <summary className="cursor-pointer px-4 py-2 text-xs font-medium text-content-muted hover:text-content">
            Preview draft artifact
          </summary>
          <div className="border-t border-border">
            {preview.format === "markdown" ? (
              <div className="py-2">
                <MarkdownViewer content={preview.content} />
              </div>
            ) : (
              <pre className="overflow-x-auto whitespace-pre-wrap px-4 py-3 text-xs text-content-muted">
                {preview.content}
              </pre>
            )}
          </div>
        </details>
      ) : null}

      {isCompleted && approvedPreview?.content ? (
        <details className="border-t border-border">
          <summary className="cursor-pointer px-4 py-2 text-xs font-medium text-content-muted hover:text-content">
            Preview approved artifact
          </summary>
          <div className="border-t border-border">
            {approvedPreview.format === "markdown" ? (
              <div className="py-2">
                <MarkdownViewer content={approvedPreview.content} />
              </div>
            ) : (
              <pre className="overflow-x-auto whitespace-pre-wrap px-4 py-3 text-xs text-content-muted">
                {approvedPreview.content}
              </pre>
            )}
          </div>
        </details>
      ) : null}
    </div>
  );
}
