import { AlertCircle, CheckCircle2, MinusCircle, PlusCircle, RefreshCw, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type ReviewChangeStatus = "added" | "updated" | "deleted" | "missing" | "blocked";

export type ReviewChangeItem = {
  id: string;
  label: string;
  status: ReviewChangeStatus;
  detail?: string;
};

export type ReviewChangesPanelProps = {
  items: ReviewChangeItem[];
  title?: string;
  className?: string;
  emptyLabel?: string;
};

const statusTone: Record<ReviewChangeStatus, "success" | "accent" | "danger" | "warning"> = {
  added: "success",
  updated: "accent",
  deleted: "danger",
  missing: "warning",
  blocked: "danger",
};

const statusLabel: Record<ReviewChangeStatus, string> = {
  added: "Added",
  updated: "Updated",
  deleted: "Deleted",
  missing: "Missing",
  blocked: "Blocked",
};

function StatusIcon({ status }: { status: ReviewChangeStatus }) {
  if (status === "added") return <PlusCircle className="h-4 w-4 text-success" />;
  if (status === "updated") return <RefreshCw className="h-4 w-4 text-accent" />;
  if (status === "deleted") return <Trash2 className="h-4 w-4 text-danger" />;
  if (status === "missing") return <MinusCircle className="h-4 w-4 text-warning" />;
  return <AlertCircle className="h-4 w-4 text-danger" />;
}

export function ReviewChangesPanel({
  items,
  title = "Review changes",
  className,
  emptyLabel = "No changes to review.",
}: ReviewChangesPanelProps) {
  return (
    <section className={cn("space-y-3", className)} aria-label={title}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-content">{title}</h2>
        <Badge tone="neutral">{items.length}</Badge>
      </div>
      {items.length ? (
        <div className="divide-y divide-border rounded-md border border-border bg-surface">
          {items.map((item) => (
            <div key={item.id} className="flex items-start gap-3 px-3 py-3">
              <span className="mt-0.5 shrink-0">
                <StatusIcon status={item.status} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-content">{item.label}</span>
                  <Badge tone={statusTone[item.status]}>{statusLabel[item.status]}</Badge>
                </div>
                {item.detail ? <p className="mt-1 text-sm leading-5 text-content-muted">{item.detail}</p> : null}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-content-muted">{emptyLabel}</p>
      )}
    </section>
  );
}
