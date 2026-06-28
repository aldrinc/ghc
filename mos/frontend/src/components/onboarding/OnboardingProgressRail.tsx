import { cn } from "@/lib/utils";

export type OnboardingProgressRailProps = {
  current?: number;
  total?: number;
  value?: number;
  label?: string;
  showCount?: boolean;
  showLabel?: boolean;
  className?: string;
};

function clampPercent(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function resolveProgress({ current, total, value }: Pick<OnboardingProgressRailProps, "current" | "total" | "value">) {
  if (typeof value === "number") return clampPercent(value);
  if (typeof current === "number" && typeof total === "number" && total > 0) {
    return clampPercent((current / total) * 100);
  }
  return 0;
}

export function OnboardingProgressRail({
  current,
  total,
  value,
  label = "Setup progress",
  showCount = true,
  showLabel = true,
  className,
}: OnboardingProgressRailProps) {
  const progress = resolveProgress({ current, total, value });
  const hasCount = typeof current === "number" && typeof total === "number";

  return (
    <div className={cn("space-y-2", className)}>
      {showLabel || showCount ? (
        <div className="flex items-center justify-between gap-3 text-xs">
          {showLabel ? <span className="font-medium text-content-muted">{label}</span> : <span aria-hidden="true" />}
          {showCount ? (
            <span className="shrink-0 font-mono text-content-muted">
              {hasCount ? `${current}/${total}` : `${Math.round(progress)}%`}
            </span>
          ) : null}
        </div>
      ) : null}
      <div
        className="h-[var(--first-run-rail-height)] w-full overflow-hidden rounded-full bg-border"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(progress)}
      >
        <div
          className="h-full rounded-full transition-[width]"
          style={{ width: `${progress}%`, backgroundColor: "var(--first-run-action)" }}
        />
      </div>
    </div>
  );
}
