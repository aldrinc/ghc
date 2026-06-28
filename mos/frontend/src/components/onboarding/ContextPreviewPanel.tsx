import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { AgentWorkLog, type AgentWorkLogEvent } from "./AgentWorkLog";
import { ReviewChangesPanel, type ReviewChangeItem } from "./ReviewChangesPanel";
import { SetupChecklist, type SetupChecklistItem } from "./SetupChecklist";

export type ContextSummaryItem = {
  label: string;
  value: ReactNode;
};

export type ContextPreviewPanelProps = {
  title?: string;
  description?: ReactNode;
  workspaceSummary?: ContextSummaryItem[];
  productSummary?: ContextSummaryItem[];
  productSummaryTitle?: string;
  checklist?: SetupChecklistItem[];
  workflowState?: ReactNode;
  generatedOutputs?: ReviewChangeItem[];
  blockers?: string[];
  workLog?: AgentWorkLogEvent[];
  className?: string;
};

function SummarySection({ title, items }: { title: string; items?: ContextSummaryItem[] }) {
  if (!items?.length) return null;
  return (
    <section className="space-y-2" aria-label={title}>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-content-muted">{title}</h3>
      <dl className="space-y-2">
        {items.map((item) => (
          <div key={item.label} className="grid grid-cols-[96px_minmax(0,1fr)] gap-3 text-sm">
            <dt className="truncate text-content-muted">{item.label}</dt>
            <dd className="min-w-0 text-content">{item.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function ContextPreviewPanel({
  title = "Setup context",
  description,
  workspaceSummary,
  productSummary,
  productSummaryTitle = "Product",
  checklist,
  workflowState,
  generatedOutputs,
  blockers,
  workLog,
  className,
}: ContextPreviewPanelProps) {
  const hasBlockers = Boolean(blockers?.length);

  return (
    <aside className={cn("space-y-5 rounded-md border border-border bg-surface px-4 py-4", className)} aria-label={title}>
      <div className="space-y-1">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-content">{title}</h2>
          {hasBlockers ? <Badge tone="danger">{blockers?.length} blocked</Badge> : null}
        </div>
        {description ? <p className="text-sm leading-5 text-content-muted">{description}</p> : null}
      </div>

      <SummarySection title="Workspace" items={workspaceSummary} />
      <SummarySection title={productSummaryTitle} items={productSummary} />

      {workflowState ? (
        <section className="space-y-2" aria-label="Workflow state">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-content-muted">Workflow state</h3>
          <div className="rounded-md border border-border bg-surface-2 px-3 py-3 text-sm text-content">{workflowState}</div>
        </section>
      ) : null}

      {checklist ? <SetupChecklist title="Source checklist" items={checklist} /> : null}
      {generatedOutputs ? <ReviewChangesPanel title="Generated outputs" items={generatedOutputs} /> : null}

      {blockers?.length ? (
        <section className="space-y-2" aria-label="Blockers">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-content-muted">Blockers</h3>
          <ul className="space-y-2">
            {blockers.map((blocker) => (
              <li key={blocker} className="rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
                {blocker}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {workLog ? <AgentWorkLog title="Work log" events={workLog} /> : null}
    </aside>
  );
}
