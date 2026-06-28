import { AlertCircle, CheckCircle2, Circle, Loader2 } from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type SetupChecklistStatus = "pending" | "running" | "done" | "blocked";

export type SetupChecklistItem = {
  id: string;
  label: string;
  details?: string;
  status: SetupChecklistStatus;
  icon?: ReactNode;
};

export type SetupChecklistProps = {
  items: SetupChecklistItem[];
  title?: string;
  className?: string;
  emptyLabel?: string;
};

const statusLabel: Record<SetupChecklistStatus, string> = {
  pending: "Pending",
  running: "Running",
  done: "Done",
  blocked: "Blocked",
};

const statusTone: Record<SetupChecklistStatus, "neutral" | "accent" | "success" | "danger"> = {
  pending: "neutral",
  running: "accent",
  done: "success",
  blocked: "danger",
};

function StatusIcon({ status }: { status: SetupChecklistStatus }) {
  if (status === "done") return <CheckCircle2 className="h-4 w-4 text-success" />;
  if (status === "running") return <Loader2 className="h-4 w-4 animate-spin text-accent" />;
  if (status === "blocked") return <AlertCircle className="h-4 w-4 text-danger" />;
  return <Circle className="h-4 w-4 text-content-muted" />;
}

export function SetupChecklist({ items, title, className, emptyLabel = "No setup items yet." }: SetupChecklistProps) {
  return (
    <section className={cn("space-y-3", className)} aria-label={title || "Setup checklist"}>
      {title ? <h2 className="text-sm font-semibold text-content">{title}</h2> : null}
      {items.length ? (
        <div className="divide-y divide-border rounded-md border border-border bg-surface">
          {items.map((item) => (
            <div key={item.id} className="flex items-start gap-3 px-3 py-3">
              <span className={cn("mt-0.5 shrink-0", item.icon && "mos-setup-checklist-icon")}>
                {item.icon || <StatusIcon status={item.status} />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-content">{item.label}</span>
                  <Badge tone={statusTone[item.status]}>{statusLabel[item.status]}</Badge>
                </div>
                {item.details ? <p className="mt-1 text-sm leading-5 text-content-muted">{item.details}</p> : null}
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
