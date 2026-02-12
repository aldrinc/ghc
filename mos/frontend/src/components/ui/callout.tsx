import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

type CalloutVariant = "neutral" | "info" | "success" | "warning" | "danger";
type CalloutSize = "sm" | "md";

export type CalloutProps = Omit<HTMLAttributes<HTMLDivElement>, "title"> & {
  variant: CalloutVariant;
  size?: CalloutSize;
  title?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
};

export function Callout({
  variant,
  size = "md",
  title,
  icon,
  actions,
  children,
  className,
  ...props
}: CalloutProps) {
  const containerVariant: Record<CalloutVariant, string> = {
    neutral: "border-border bg-surface text-content",
    info: "border-accent/30 bg-accent/10 text-content",
    success: "border-success/30 bg-success/5 text-content",
    warning: "border-warning/30 bg-warning/5 text-content",
    danger: "border-danger/30 bg-danger/5 text-content",
  };

  const accentText: Record<CalloutVariant, string> = {
    neutral: "text-content",
    info: "text-accent",
    success: "text-success",
    warning: "text-warning",
    danger: "text-danger",
  };

  const padding: Record<CalloutSize, string> = {
    sm: "px-3 py-2",
    md: "px-4 py-3",
  };

  return (
    <div
      className={cn("rounded-md border", padding[size], containerVariant[variant], className)}
      {...props}
    >
      <div className={cn("flex flex-col gap-2", actions ? "sm:flex-row sm:items-center sm:justify-between" : "")}>
        <div className={cn("min-w-0", icon ? "flex items-start gap-2" : "")}>
          {icon ? <div className={cn("mt-0.5 shrink-0", accentText[variant])}>{icon}</div> : null}
          <div className="min-w-0">
            {title ? (
              <div className={cn("font-semibold leading-tight", accentText[variant])}>{title}</div>
            ) : null}
            {children ? (
              <div className={cn(title ? "mt-0.5 text-xs text-content-muted" : "text-sm text-content")}>
                {children}
              </div>
            ) : null}
          </div>
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </div>
    </div>
  );
}

