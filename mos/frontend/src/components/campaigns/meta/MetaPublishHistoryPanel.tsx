import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useMetaApi } from "@/api/meta";
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

function summaryText(run: { metadata?: Record<string, unknown> | null }) {
  const resultSummary =
    run.metadata && typeof run.metadata === "object" && run.metadata.resultSummary && typeof run.metadata.resultSummary === "object"
      ? (run.metadata.resultSummary as Record<string, unknown>)
      : null;
  if (!resultSummary) return null;
  const total = typeof resultSummary.totalCount === "number" ? resultSummary.totalCount : null;
  const published = typeof resultSummary.publishedCount === "number" ? resultSummary.publishedCount : null;
  const failed = typeof resultSummary.failedCount === "number" ? resultSummary.failedCount : null;
  if (total == null || published == null || failed == null) return null;
  return `${published}/${total} published · ${failed} failed`;
}

export function MetaPublishHistoryPanel() {
  const { campaign, visiblePublishRuns, publishRunsLoading, publishRunsError } = useMetaPublishContext();
  const { getPublishRun } = useMetaApi();
  const [expandedRunIds, setExpandedRunIds] = useState<string[]>([]);
  const [detailsByRunId, setDetailsByRunId] = useState<Record<string, { items: typeof visiblePublishRuns[number]["items"]; error?: string }>>(
    {},
  );
  const [loadingRunIds, setLoadingRunIds] = useState<string[]>([]);

  const toggleRun = async (runId: string) => {
    const isOpen = expandedRunIds.includes(runId);
    if (isOpen) {
      setExpandedRunIds((current) => current.filter((id) => id !== runId));
      return;
    }
    setExpandedRunIds((current) => [...current, runId]);
    if (detailsByRunId[runId] || loadingRunIds.includes(runId)) return;
    setLoadingRunIds((current) => [...current, runId]);
    try {
      const detail = await getPublishRun(campaign.id, runId);
      setDetailsByRunId((current) => ({ ...current, [runId]: { items: detail.items } }));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load publish run details.";
      setDetailsByRunId((current) => ({ ...current, [runId]: { items: [], error: message } }));
    } finally {
      setLoadingRunIds((current) => current.filter((id) => id !== runId));
    }
  };

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
            const isExpanded = expandedRunIds.includes(run.id);
            const detail = detailsByRunId[run.id];
            const itemRows = detail?.items || [];
            const detailsLoading = loadingRunIds.includes(run.id);
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
                    {summaryText(run) ? <div className="text-xs text-content-muted">{summaryText(run)}</div> : null}
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="text-xs text-content-muted">{formatDate(run.createdAt)}</div>
                    <Button variant="secondary" size="sm" onClick={() => void toggleRun(run.id)}>
                      {isExpanded ? "Hide items" : "Show items"}
                    </Button>
                  </div>
                </div>
                {run.errorMessage ? <div className="mt-2 text-sm text-danger">{run.errorMessage}</div> : null}
                {isExpanded ? (
                  <div className="mt-3 space-y-2">
                    {detailsLoading ? <div className="text-sm text-content-muted">Loading run items…</div> : null}
                    {detail?.error ? <div className="text-sm text-danger">{detail.error}</div> : null}
                    {!detailsLoading && !detail?.error && !itemRows.length ? (
                      <div className="text-sm text-content-muted">No publish items were stored for this run.</div>
                    ) : null}
                    {itemRows.map((item) => (
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
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
