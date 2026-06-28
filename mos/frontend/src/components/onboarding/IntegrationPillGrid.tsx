import type { ReactNode } from "react";
import { AlertCircle, CheckCircle2, Circle, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type IntegrationStatus = "available" | "connected" | "running" | "disabled" | "blocked";

export type IntegrationPill = {
  id: string;
  label: string;
  status: IntegrationStatus;
  icon?: ReactNode;
  disabledReason?: ReactNode;
};

export type IntegrationPillGridProps = {
  items: IntegrationPill[];
  title?: string;
  className?: string;
  emptyLabel?: string;
};

const statusTone: Record<IntegrationStatus, "neutral" | "success" | "accent" | "danger"> = {
  available: "neutral",
  connected: "success",
  running: "accent",
  disabled: "neutral",
  blocked: "danger",
};

const statusLabel: Record<IntegrationStatus, string> = {
  available: "Available",
  connected: "Connected",
  running: "Running",
  disabled: "Disabled",
  blocked: "Blocked",
};

function StatusIcon({ status }: { status: IntegrationStatus }) {
  if (status === "connected") return <CheckCircle2 className="h-3.5 w-3.5 text-success" />;
  if (status === "running") return <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />;
  if (status === "blocked") return <AlertCircle className="h-3.5 w-3.5 text-danger" />;
  return <Circle className="h-3.5 w-3.5 text-content-muted" />;
}

export function IntegrationPillGrid({ items, title, className, emptyLabel = "No sources configured." }: IntegrationPillGridProps) {
  return (
    <section className={cn("space-y-3", className)} aria-label={title || "Supported source types"}>
      {title ? <h2 className="text-sm font-semibold text-content">{title}</h2> : null}
      {items.length ? (
        <div className="flex flex-wrap gap-2">
          {items.map((item) => (
            <div
              key={item.id}
              className={cn(
                "inline-flex min-h-9 max-w-full items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-sm",
                (item.status === "disabled" || item.status === "blocked") && "opacity-65",
              )}
              title={typeof item.disabledReason === "string" ? item.disabledReason : undefined}
            >
              <span className="flex shrink-0 items-center text-content-muted">{item.icon || <StatusIcon status={item.status} />}</span>
              <span className="truncate font-medium text-content">{item.label}</span>
              <Badge tone={statusTone[item.status]} className="shrink-0 py-0.5 text-[10px]">
                {statusLabel[item.status]}
              </Badge>
              {item.disabledReason ? <span className="sr-only">{item.disabledReason}</span> : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-content-muted">{emptyLabel}</p>
      )}
    </section>
  );
}
