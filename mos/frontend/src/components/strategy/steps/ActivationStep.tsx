import type { StrategySkillsBundle } from "@/api/productStrategySkills";
import type { useActivateStrategyHandoff } from "@/api/productStrategySkills";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

type ActivationStepProps = {
  isActive: boolean;
  isCompleted: boolean;
  isUpcoming: boolean;
  pendingHandoffBundles: StrategySkillsBundle[];
  historicalHandoffBundles: StrategySkillsBundle[];
  activateHandoff: ReturnType<typeof useActivateStrategyHandoff>;
};

function formatDate(value?: string | null) {
  if (!value) return "\u2014";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function shortId(value?: string | null) {
  const text = String(value ?? "").trim();
  if (!text) return "\u2014";
  return text.length > 12 ? `${text.slice(0, 8)}\u2026` : text;
}

function roleLabel(role: string) {
  return role.replace(/^foundational:/, "").replace(/_/g, " ");
}

export function ActivationStep({
  isActive,
  isCompleted,
  isUpcoming,
  pendingHandoffBundles,
  historicalHandoffBundles,
  activateHandoff,
}: ActivationStepProps) {
  if (isCompleted && !pendingHandoffBundles.length) {
    return (
      <details className="ds-card ds-card--sm shadow-none">
        <summary className="flex cursor-pointer items-center gap-2 px-4 py-3">
          <span className="text-sm font-semibold text-content">Activate</span>
          <Badge tone="success">Live</Badge>
        </summary>
        <div className="border-t border-border px-4 py-3 text-sm text-content-muted">
          The approved bundle is active and live for sites and campaigns.
        </div>
      </details>
    );
  }

  if (isUpcoming && !pendingHandoffBundles.length) {
    return (
      <div className="ds-card ds-card--sm opacity-50 shadow-none">
        <div className="px-4 py-3">
          <div className="text-sm font-semibold text-content-muted">Activate</div>
          <div className="mt-1 text-xs text-content-muted">
            Activate a reviewed bundle to make it live for sites and campaigns.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`ds-card ds-card--sm shadow-none ${isActive ? "ring-1 ring-accent/20" : ""}`}
      id="step-activation"
    >
      <div className="px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-semibold text-content">Activate</div>
          {pendingHandoffBundles.length ? (
            <Badge tone="warning">{pendingHandoffBundles.length} pending</Badge>
          ) : null}
        </div>
        <div className="mt-1 text-xs text-content-muted">
          Activate a reviewed snapshot to switch the live strategy state for sites and campaigns.
        </div>
      </div>

      {pendingHandoffBundles.length ? (
        <div className="border-t border-border px-4 py-4 space-y-3">
          {pendingHandoffBundles.map((bundle) => (
            <div key={bundle.id} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface-2 px-4 py-3">
              <div>
                <div className="text-sm font-medium text-content">
                  Reviewed snapshot
                </div>
                <div className="text-xs text-content-muted">
                  {bundle.items.length} roles &middot; {formatDate(bundle.approvedAt ?? bundle.createdAt)} &middot;{" "}
                  <span className="font-mono">{shortId(bundle.id)}</span>
                </div>
              </div>
              <Button
                size="sm"
                onClick={() => void activateHandoff.mutateAsync({ bundleId: bundle.id })}
                disabled={activateHandoff.isPending}
              >
                {activateHandoff.isPending ? "Activating..." : "Activate"}
              </Button>
            </div>
          ))}
        </div>
      ) : null}

      {historicalHandoffBundles.length ? (
        <details className="border-t border-border">
          <summary className="cursor-pointer px-4 py-2 text-xs font-medium text-content-muted hover:text-content">
            Bundle history ({historicalHandoffBundles.length} snapshots)
          </summary>
          <div className="border-t border-border px-4 py-3 space-y-2">
            {historicalHandoffBundles.slice(0, 5).map((bundle) => (
              <div key={bundle.id} className="text-xs text-content-muted">
                <span className="font-mono">{shortId(bundle.id)}</span> &middot;{" "}
                {bundle.items.length} roles &middot;{" "}
                {formatDate(bundle.approvedAt ?? bundle.createdAt)}
              </div>
            ))}
            {historicalHandoffBundles.length > 5 ? (
              <div className="text-xs text-content-muted">
                {historicalHandoffBundles.length - 5} older snapshots not shown.
              </div>
            ) : null}
          </div>
        </details>
      ) : null}
    </div>
  );
}
