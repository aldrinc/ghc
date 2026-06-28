import { cn } from "@/lib/utils";

type Status = "running" | "failed" | "completed" | "cancelled" | string;

const statusStyles: Record<string, string> = {
  running: "border-warning/25 bg-warning-bg text-warning",
  failed: "border-danger/25 bg-danger-bg text-danger",
  completed: "border-success/25 bg-success-bg text-success",
  cancelled: "border-border bg-surface-2 text-content-muted",
};

export function StatusBadge({ status, className }: { status: Status; className?: string }) {
  const color = statusStyles[status] || "bg-surface-2 text-content-muted border-border";
  const isRunning = status === "running";
  return (
    <span
      className={cn(
        "inline-flex h-[22px] items-center gap-2 whitespace-nowrap rounded-sm border px-2 text-xs font-medium capitalize tracking-normal",
        color,
        className
      )}
    >
      {isRunning ? (
        <span aria-hidden="true" className="h-2 w-2 animate-pulse rounded-full bg-warning shadow-[0_0_0_3px_var(--warning-bg)]" />
      ) : null}
      <span>{status}</span>
    </span>
  );
}
