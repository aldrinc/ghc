import { Badge } from "@/components/ui/badge";
import { useMetaPublishContext, formatDate, shortId } from "./MetaPublishProvider";

function readBudgetScope(value: unknown): "campaign" | "adset" | "mixed" | null {
  return value === "campaign" || value === "adset" || value === "mixed" ? value : null;
}

function readCampaignDailyBudget(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatBudgetScopeLabel(scope: "campaign" | "adset" | "mixed" | null): string | null {
  if (scope === "campaign") return "Campaign budget (CBO)";
  if (scope === "adset") return "Ad set budgets (ABO)";
  if (scope === "mixed") return "Mixed budget scopes";
  return null;
}

function formatMinorUnitsBudget(value: number | null): string | null {
  if (value == null) return null;
  return `$${(value / 100).toFixed(2)}/day`;
}

function publishStatusTone(status: string): "neutral" | "accent" | "success" | "danger" {
  if (status === "published") return "success";
  if (status === "partial_failed" || status === "running") return "accent";
  if (status === "failed") return "danger";
  return "neutral";
}

function readStage(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function formatStage(value: string | null): string | null {
  if (!value) return null;
  return value.replace(/_/g, " ");
}

export function MetaPublishHistoryPanel() {
  const { visiblePublishRuns, publishRunsLoading, publishRunsError } = useMetaPublishContext();

  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="text-base font-semibold text-content">Publish history</div>
      <div className="mt-1 text-sm text-content-muted">Stored Meta publish runs for this campaign.</div>

      {publishRunsLoading ? (
        <div className="mt-3 text-sm text-content-muted">Loading publish runs…</div>
      ) : publishRunsError ? (
        <div className="mt-3 text-sm text-danger">{publishRunsError}</div>
      ) : !visiblePublishRuns.length ? (
        <div className="mt-3 text-sm text-content-muted">No Meta publish runs yet.</div>
      ) : (
        <div className="mt-4 space-y-3">
          {visiblePublishRuns.map((run) => {
            const budgetScopeLabel = formatBudgetScopeLabel(readBudgetScope(run.metadata?.budgetScope));
            const campaignBudgetLabel = formatMinorUnitsBudget(readCampaignDailyBudget(run.metadata?.campaignDailyBudget));
            return (
              <div key={`run-${run.id}`} className="rounded-xl border border-border bg-surface-2 p-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="space-y-1">
                    <div className="text-sm font-semibold text-content">{run.campaignName}</div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={publishStatusTone(run.status)}>{run.status}</Badge>
                      <Badge tone="neutral">{run.generationKey}</Badge>
                      {run.metaCampaignId ? <Badge tone="neutral">Meta {shortId(run.metaCampaignId, 5)}</Badge> : null}
                      {budgetScopeLabel ? <Badge tone="neutral">{budgetScopeLabel}</Badge> : null}
                      {campaignBudgetLabel ? <Badge tone="neutral">{campaignBudgetLabel}</Badge> : null}
                    </div>
                  </div>
                  <div className="text-xs text-content-muted">{formatDate(run.createdAt)}</div>
                </div>
                {run.errorMessage ? <div className="mt-2 text-sm text-danger">{run.errorMessage}</div> : null}
                <div className="mt-3 space-y-2">
                  {run.items.map((item) => (
                    <div key={`run-item-${item.id}`} className="rounded-md border border-border bg-background px-3 py-2 text-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs text-content-muted">{shortId(item.assetId, 5)}</span>
                        <Badge tone={publishStatusTone(item.status)}>{item.status}</Badge>
                        {formatStage(
                          readStage(item.metadata?.failedStage) ||
                            readStage(item.metadata?.lastStage) ||
                            readStage(item.metadata?.currentStage),
                        ) ? (
                          <span className="text-xs text-content-muted">
                            Stage{" "}
                            {formatStage(
                              readStage(item.metadata?.failedStage) ||
                                readStage(item.metadata?.lastStage) ||
                                readStage(item.metadata?.currentStage),
                            )}
                          </span>
                        ) : null}
                        {item.metaAdId ? <span className="text-content-muted">Ad {shortId(item.metaAdId, 5)}</span> : null}
                        {item.metaCreativeId ? <span className="text-content-muted">Creative {shortId(item.metaCreativeId, 5)}</span> : null}
                        {item.metaAdSetId ? <span className="text-content-muted">Ad set {shortId(item.metaAdSetId, 5)}</span> : null}
                      </div>
                      {item.errorMessage ? <div className="mt-2 text-danger">{item.errorMessage}</div> : null}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
