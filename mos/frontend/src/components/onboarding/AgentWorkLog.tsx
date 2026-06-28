import { AlertCircle, CheckCircle2, Circle, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type AgentWorkLogStatus = "pending" | "running" | "done" | "blocked" | "failed";

export type AgentWorkLogEvent = {
  id: string;
  label: string;
  status: AgentWorkLogStatus;
  detail?: string;
  timestamp?: string;
};

export type AgentWorkLogProps = {
  events: AgentWorkLogEvent[];
  title?: string;
  className?: string;
  emptyLabel?: string;
};

const statusTone: Record<AgentWorkLogStatus, "neutral" | "accent" | "success" | "danger"> = {
  pending: "neutral",
  running: "accent",
  done: "success",
  blocked: "danger",
  failed: "danger",
};

const statusLabel: Record<AgentWorkLogStatus, string> = {
  pending: "Pending",
  running: "Running",
  done: "Done",
  blocked: "Blocked",
  failed: "Failed",
};

function StatusIcon({ status }: { status: AgentWorkLogStatus }) {
  if (status === "done") return <CheckCircle2 className="h-3.5 w-3.5 text-success" />;
  if (status === "running") return <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />;
  if (status === "blocked" || status === "failed") return <AlertCircle className="h-3.5 w-3.5 text-danger" />;
  return <Circle className="h-3.5 w-3.5 text-content-muted" />;
}

export function AgentWorkLog({ events, title, className, emptyLabel = "No work has started yet." }: AgentWorkLogProps) {
  return (
    <section className={cn("space-y-3", className)} aria-label={title || "Agent work log"}>
      {title ? <h2 className="text-sm font-semibold text-content">{title}</h2> : null}
      {events.length ? (
        <ol className="space-y-2">
          {events.map((event) => (
            <li key={event.id} className="flex items-start gap-3 rounded-md border border-border bg-surface px-3 py-2.5">
              <span className="mt-1 shrink-0">
                <StatusIcon status={event.status} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-content">{event.label}</span>
                  <Badge tone={statusTone[event.status]} className="py-0.5 text-[10px]">
                    {statusLabel[event.status]}
                  </Badge>
                </div>
                {event.detail ? <p className="mt-1 text-xs leading-5 text-content-muted">{event.detail}</p> : null}
              </div>
              {event.timestamp ? <time className="shrink-0 text-xs text-content-muted">{event.timestamp}</time> : null}
            </li>
          ))}
        </ol>
      ) : (
        <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-content-muted">{emptyLabel}</p>
      )}
    </section>
  );
}
