import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Tone = "neutral" | "accent" | "info" | "success" | "danger" | "warning";

export function Badge({ className, tone = "neutral", ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  const toneClasses: Record<Tone, string> = {
    neutral: "border border-border bg-surface-2 text-content-muted",
    accent: "border border-accent/30 bg-accent/10 text-accent",
    info: "border border-accent/30 bg-accent/10 text-accent",
    success: "border border-success/25 bg-success-bg text-success",
    danger: "border border-danger/25 bg-danger-bg text-danger",
    warning: "border border-warning/25 bg-warning-bg text-warning",
  };

  return (
    <span
      className={cn(
        "inline-flex h-[22px] items-center gap-2 whitespace-nowrap rounded-sm px-2 text-xs font-medium tracking-normal",
        toneClasses[tone],
        className
      )}
      {...props}
    />
  );
}
