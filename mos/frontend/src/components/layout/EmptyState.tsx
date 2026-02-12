import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

export type EmptyStateProps = Omit<HTMLAttributes<HTMLDivElement>, "title"> & {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
};

export function EmptyState({ title, description, actions, className, ...props }: EmptyStateProps) {
  return (
    <div className={cn("ds-card ds-card--md ds-card--empty text-sm", className)} {...props}>
      <div className={cn(actions ? "flex items-start justify-between gap-4" : "")}>
        <div className="min-w-0">
          {title ? <div className="font-semibold text-content">{title}</div> : null}
          {description ? <div className={cn(title ? "mt-1 text-content-muted" : "text-content-muted")}>{description}</div> : null}
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </div>
    </div>
  );
}

