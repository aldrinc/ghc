import { cn } from "@/lib/utils";

type Status = "running" | "failed" | "completed" | "cancelled" | string;

const statusStyles: Record<string, string> = {
  running: "bg-warning/10 text-warning border-warning/30",
  failed: "bg-danger/10 text-danger border-danger/30",
  completed: "bg-success/10 text-success border-success/30",
  cancelled: "bg-surface-2 text-content-muted border-border",
};

export function StatusBadge({ status, className }: { status: Status; className?: string }) {
  const color = statusStyles[status] || "bg-surface-2 text-content-muted border-border";
  const isRunning = status === "running";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-semibold capitalize",
        color,
        className
      )}
    >
      {isRunning ? <span aria-hidden="true" className="h-2 w-2 animate-pulse rounded-full bg-warning" /> : null}
      <span>{status}</span>
    </span>
  );
}
