import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type FirstRunShellProps = {
  children: ReactNode;
  context?: ReactNode;
  progressRail?: ReactNode;
  visual?: ReactNode;
  centered?: boolean;
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
  taskClassName?: string;
  contextClassName?: string;
  visualClassName?: string;
};

export function FirstRunShell({
  children,
  context,
  progressRail,
  visual,
  centered,
  title,
  description,
  actions,
  className,
  taskClassName,
  contextClassName,
  visualClassName,
}: FirstRunShellProps) {
  if (centered) {
    return (
      <section className={cn("first-run-surface mx-auto flex min-h-[calc(100svh-5rem)] w-full items-center justify-center px-4 py-10 sm:py-14", className)}>
        <main className={cn("w-full max-w-[520px] space-y-7", taskClassName)}>
          {progressRail ? <div className="pb-2">{progressRail}</div> : null}
          {(title || description || actions) ? (
            <header className="space-y-3">
              {actions ? <div className="first-run-header-actions">{actions}</div> : null}
              {title ? <h1 className="first-run-title max-w-[520px] text-content">{title}</h1> : null}
              {description ? <p className="first-run-body max-w-[48ch]">{description}</p> : null}
            </header>
          ) : null}
          {children}
        </main>
      </section>
    );
  }

  if (visual) {
    return (
      <section className={cn("first-run-surface mx-auto w-full max-w-6xl px-4 py-4 sm:px-6", className)}>
        <div className="grid min-h-[min(760px,calc(100svh-2rem))] overflow-hidden rounded-card border border-border bg-background shadow-sm lg:grid-cols-[minmax(360px,520px)_minmax(320px,1fr)]">
          <main className={cn("flex min-w-0 flex-col justify-center px-8 py-10 sm:px-12 lg:px-16", taskClassName)}>
            {progressRail ? <div className="mb-10">{progressRail}</div> : null}
            {(title || description || actions) ? (
              <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0 space-y-2">
                  <div className="mb-4 flex h-9 w-9 items-center justify-center rounded-[9px] border border-border bg-surface text-sm font-semibold text-content shadow-xs">
                    M
                  </div>
                  {title ? <h1 className="first-run-title font-semibold text-content">{title}</h1> : null}
                  {description ? <p className="max-w-md text-sm leading-6 text-content-muted">{description}</p> : null}
                </div>
                {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
              </header>
            ) : null}
            {children}
          </main>
          <aside className={cn("hidden min-h-full overflow-hidden lg:block", visualClassName)}>{visual}</aside>
        </div>
      </section>
    );
  }

  return (
    <section className={cn("first-run-surface mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8", className)}>
      {progressRail ? <div className="lg:hidden">{progressRail}</div> : null}

      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_360px] xl:grid-cols-[minmax(0,1fr)_400px]">
        <main className={cn("min-w-0 space-y-6", taskClassName)}>
          {(title || description || actions) ? (
            <header className="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0 space-y-1">
                {title ? <h1 className="first-run-title font-semibold text-content">{title}</h1> : null}
                {description ? <p className="max-w-2xl text-sm leading-6 text-content-muted">{description}</p> : null}
              </div>
              {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
            </header>
          ) : null}
          {children}
        </main>

        {(context || progressRail) ? (
          <aside className={cn("min-w-0 space-y-4 lg:sticky lg:top-4 lg:self-start", contextClassName)}>
            {progressRail ? <div className="hidden lg:block">{progressRail}</div> : null}
            {context}
          </aside>
        ) : null}
      </div>
    </section>
  );
}
