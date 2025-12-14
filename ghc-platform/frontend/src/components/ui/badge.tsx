import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Tone = "neutral" | "accent" | "success" | "danger";

export function Badge({ className, tone = "neutral", ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  const toneClasses: Record<Tone, string> = {
    neutral: "bg-surface-2 text-content-muted border border-border",
    accent: "bg-accent/10 text-accent border border-accent/30",
    success: "bg-success/10 text-success border border-success/30",
    danger: "bg-danger/10 text-danger border border-danger/30",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold tracking-tight",
        toneClasses[tone],
        className
      )}
      {...props}
    />
  );
}
