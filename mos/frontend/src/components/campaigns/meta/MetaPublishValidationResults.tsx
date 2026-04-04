import { Badge } from "@/components/ui/badge";
import { useMetaPublishContext, shortId } from "./MetaPublishProvider";

function formatBudgetScopeLabel(scope?: "campaign" | "adset" | "mixed") {
  if (scope === "campaign") return "Campaign budget (CBO)";
  if (scope === "adset") return "Ad set budgets (ABO)";
  if (scope === "mixed") return "Mixed budget scopes";
  return null;
}

function formatMinorUnitsBudget(value?: number | null) {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return `$${(value / 100).toFixed(2)}/day`;
}

export function MetaPublishValidationResults() {
  const { publishValidation } = useMetaPublishContext();
  if (!publishValidation) return null;
  const budgetScopeLabel = formatBudgetScopeLabel(publishValidation.budgetScope);
  const campaignBudgetLabel = formatMinorUnitsBudget(publishValidation.campaignDailyBudget);

  return (
    <div className="mt-4 space-y-3 rounded-xl border border-border bg-surface-2 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="text-sm font-semibold text-content">Publish validation</div>
        <Badge tone={publishValidation.ok ? "success" : "danger"}>
          {publishValidation.ok ? "Ready to publish" : "Blocked"}
        </Badge>
        {publishValidation.publishDomain ? <Badge tone="neutral">{publishValidation.publishDomain}</Badge> : null}
        {budgetScopeLabel ? <Badge tone="neutral">{budgetScopeLabel}</Badge> : null}
        {campaignBudgetLabel ? <Badge tone="neutral">{campaignBudgetLabel}</Badge> : null}
      </div>
      {publishValidation.blockers.length ? (
        <div className="space-y-1 text-sm text-danger">
          {publishValidation.blockers.map((blocker) => (
            <div key={blocker}>{blocker}</div>
          ))}
        </div>
      ) : null}
      <div className="space-y-2">
        {publishValidation.items.map((item) => (
          <div key={`pv-${item.assetId}`} className="rounded-md border border-border bg-background px-3 py-2 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-content-muted">{shortId(item.assetId, 5)}</span>
              <Badge tone={item.status === "ok" ? "success" : "danger"}>
                {item.status === "ok" ? "OK" : "Blocked"}
              </Badge>
              {item.resolvedDestinationUrl ? (
                <span className="truncate text-content-muted">{item.resolvedDestinationUrl}</span>
              ) : null}
            </div>
            {item.blockers.length ? (
              <div className="mt-2 space-y-1 text-danger">
                {item.blockers.map((b) => <div key={`${item.assetId}-${b}`}>{b}</div>)}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
