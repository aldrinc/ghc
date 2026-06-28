import { PropsWithChildren, ReactNode } from "react";

type PageHeaderProps = PropsWithChildren<{
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  compact?: boolean;
}>;

export function PageHeader({ title, description, actions, children, compact = false }: PageHeaderProps) {
  const containerClass = compact ? "flex flex-col gap-2 border-b border-border pb-3" : "flex flex-col gap-3 border-b border-border pb-5";
  const titleClass = compact ? "font-display text-lg font-normal text-content" : "font-display text-2xl font-normal text-content";
  const descriptionClass = compact ? "text-xs leading-relaxed text-content-muted" : "text-md leading-relaxed text-content-muted";
  return (
    <div className={containerClass}>
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className={titleClass}>{title}</h2>
          {description ? <p className={descriptionClass}>{description}</p> : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </div>
  );
}
