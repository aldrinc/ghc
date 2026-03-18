import { useCallback, useEffect, useMemo, useState } from "react";
import { useMetaApi } from "@/api/meta";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Select, type SelectOption } from "@/components/ui/select";
import type { MetaManagementBenchmarkEvaluation, MetaManagementPlan, MetaPublishRun } from "@/types/meta";
import { formatDate, shortId, useMetaPublishContext } from "./MetaPublishProvider";

const DATE_PRESET_OPTIONS: SelectOption[] = [
  { label: "Today", value: "today" },
  { label: "Yesterday", value: "yesterday" },
  { label: "Last 3 days", value: "last_3d" },
  { label: "Last 7 days", value: "last_7d" },
];

function getErrorMessage(err: unknown) {
  if (typeof err === "string") return err;
  if (err && typeof err === "object" && "message" in err) {
    const message = (err as { message?: string }).message;
    return message || "Request failed";
  }
  return "Request failed";
}

function formatPct(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return `${value.toFixed(1)}%`;
}

function benchmarkStatusTone(status: MetaManagementBenchmarkEvaluation["status"]): "neutral" | "accent" | "success" | "danger" {
  if (status === "good") return "success";
  if (status === "on_target") return "accent";
  if (status === "below_target") return "danger";
  return "neutral";
}

function benchmarkStatusLabel(status: MetaManagementBenchmarkEvaluation["status"]): string {
  return status.replace(/_/g, " ");
}

function recommendationForEvaluation(evaluation: MetaManagementBenchmarkEvaluation): string | null {
  if (evaluation.status === "below_target") {
    if (evaluation.metricId === "ad_link_ctr_pct") {
      return "Creative clickthrough is below benchmark. Refresh the hook, first frame, and headline before scaling spend.";
    }
    if (evaluation.metricId === "presell_ctr_pct") {
      return "The pre-sell page is not moving enough visitors forward. Rework the headline, CTA placement, and bridge into the offer.";
    }
    if (evaluation.metricId === "sales_pdp_atc_pct") {
      return "The sales page is weak for its price band. Tighten offer clarity, proof, and CTA density above the fold.";
    }
    if (evaluation.metricId === "sales_pdp_purchase_cvr_pct") {
      return "Sales-page conversion is below benchmark. Audit message-match, proof quality, and objection handling.";
    }
    if (evaluation.metricId === "checkout_cvr_pct") {
      return "Checkout completion is below target. Inspect checkout friction, payment errors, and trust elements.";
    }
  }
  return evaluation.reason || null;
}

function runLabel(run: MetaPublishRun): string {
  const campaignLabel = run.campaignName || "Published campaign";
  const createdLabel = formatDate(run.createdAt);
  const metaLabel = run.metaCampaignId ? `Meta ${shortId(run.metaCampaignId, 5)}` : "No Meta id";
  return `${campaignLabel} · ${createdLabel} · ${metaLabel}`;
}

export function MetaManagementPanel() {
  const { campaign, visiblePublishRuns, publishRunsLoading, publishRunsError } = useMetaPublishContext();
  const { planManagement } = useMetaApi();
  const [datePreset, setDatePreset] = useState("last_3d");
  const [selectedRunId, setSelectedRunId] = useState("");
  const [plan, setPlan] = useState<MetaManagementPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runnableRuns = useMemo(
    () => visiblePublishRuns.filter((run) => typeof run.metaCampaignId === "string" && run.metaCampaignId.trim()),
    [visiblePublishRuns],
  );

  useEffect(() => {
    setSelectedRunId((current) => {
      if (current && runnableRuns.some((run) => run.id === current)) return current;
      return runnableRuns[0]?.id || "";
    });
  }, [runnableRuns]);

  const selectedRun = useMemo(
    () => runnableRuns.find((run) => run.id === selectedRunId) || runnableRuns[0] || null,
    [runnableRuns, selectedRunId],
  );

  const runOptions = useMemo<SelectOption[]>(
    () =>
      runnableRuns.map((run) => ({
        label: runLabel(run),
        value: run.id,
      })),
    [runnableRuns],
  );

  const loadPlan = useCallback(async () => {
    if (!selectedRun?.metaCampaignId) {
      setPlan(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const nextPlan = await planManagement({
        metaCampaignId: selectedRun.metaCampaignId,
        clientId: campaign.client_id,
        metaConfigId: selectedRun.metaConfigId || undefined,
        datePreset,
        mode: "plan_only",
        evaluateBenchmarks: true,
      });
      setPlan(nextPlan);
    } catch (err) {
      setPlan(null);
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [campaign.client_id, datePreset, planManagement, selectedRun]);

  useEffect(() => {
    if (!selectedRun?.metaCampaignId) {
      setPlan(null);
      return;
    }
    void loadPlan();
  }, [loadPlan, selectedRun?.metaCampaignId]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-border bg-surface p-4">
        <div>
          <div className="text-base font-semibold text-content">Manage live benchmarks</div>
          <div className="mt-1 text-sm text-content-muted">
            Compare ad CTR and first-party funnel conversion metrics against the Meta management benchmark profile.
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <div className="min-w-[220px]">
            <Select value={selectedRunId} onValueChange={setSelectedRunId} options={runOptions} disabled={!runOptions.length} />
          </div>
          <div className="w-[140px]">
            <Select value={datePreset} onValueChange={setDatePreset} options={DATE_PRESET_OPTIONS} disabled={!runOptions.length} />
          </div>
          <Button variant="secondary" size="sm" onClick={() => void loadPlan()} disabled={!selectedRun || loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </Button>
        </div>
      </div>

      {publishRunsLoading ? <div className="px-4 py-3 text-sm text-content-muted">Loading publish runs…</div> : null}
      {publishRunsError ? (
        <Callout variant="danger" size="sm">
          {publishRunsError}
        </Callout>
      ) : null}
      {!publishRunsLoading && !publishRunsError && !runnableRuns.length ? (
        <Callout variant="warning" size="sm">
          Publish a Meta campaign first. The Manage phase only evaluates live campaigns that have a saved `metaCampaignId`.
        </Callout>
      ) : null}
      {error ? (
        <Callout variant="danger" size="sm">
          {error}
        </Callout>
      ) : null}

      {plan ? (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {plan.benchmarkEvaluations.map((evaluation) => (
              <div key={evaluation.metricId} className="rounded-xl border border-border bg-surface p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-xs uppercase tracking-wide text-content-muted">{evaluation.label}</div>
                    <div className="mt-1 text-2xl font-semibold text-content">{formatPct(evaluation.value)}</div>
                  </div>
                  <Badge tone={benchmarkStatusTone(evaluation.status)}>{benchmarkStatusLabel(evaluation.status)}</Badge>
                </div>
                <div className="mt-3 space-y-1 text-xs text-content-muted">
                  {evaluation.minimum != null ? <div>Minimum {formatPct(evaluation.minimum)}</div> : null}
                  {evaluation.target != null ? <div>Target {formatPct(evaluation.target)}</div> : null}
                  {evaluation.good != null ? <div>Good {formatPct(evaluation.good)}</div> : null}
                  {evaluation.denominator != null ? (
                    <div>
                      Volume {evaluation.numerator ?? 0}/{evaluation.denominator}
                    </div>
                  ) : null}
                </div>
                {recommendationForEvaluation(evaluation) ? (
                  <div className="mt-3 text-sm text-content-muted">{recommendationForEvaluation(evaluation)}</div>
                ) : null}
              </div>
            ))}
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.4fr,1fr]">
            <div className="rounded-xl border border-border bg-surface p-4">
              <div className="text-base font-semibold text-content">Ad-level snapshot</div>
              <div className="mt-1 text-sm text-content-muted">Raw Meta ad metrics plus any pause recommendations from the current ruleset.</div>
              {!plan.rows.length ? (
                <div className="mt-3 text-sm text-content-muted">No ad rows were returned for this window.</div>
              ) : (
                <div className="mt-4 overflow-x-auto">
                  <table className="min-w-full text-left text-sm">
                    <thead className="text-xs uppercase tracking-wide text-content-muted">
                      <tr>
                        <th className="pb-2 pr-4">Ad</th>
                        <th className="pb-2 pr-4">Spend</th>
                        <th className="pb-2 pr-4">CTR</th>
                        <th className="pb-2 pr-4">CPC</th>
                        <th className="pb-2 pr-4">CPM</th>
                        <th className="pb-2">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {plan.rows.map((row) => {
                        const action = plan.actions.find((entry) => entry.metaAdId === row.adId);
                        return (
                          <tr key={row.adId} className="border-t border-border/70">
                            <td className="py-2 pr-4">
                              <div className="font-medium text-content">{row.adName || row.adId}</div>
                              <div className="text-xs text-content-muted">{shortId(row.adId, 5)}</div>
                            </td>
                            <td className="py-2 pr-4 text-content">${row.spend.toFixed(2)}</td>
                            <td className="py-2 pr-4 text-content">{formatPct(row.linkCtrPct)}</td>
                            <td className="py-2 pr-4 text-content">{row.linkCpc != null ? `$${row.linkCpc.toFixed(2)}` : "—"}</td>
                            <td className="py-2 pr-4 text-content">${row.cpm.toFixed(2)}</td>
                            <td className="py-2 text-content">
                              {action ? (
                                <div className="space-y-1">
                                  <Badge tone="danger">Pause recommended</Badge>
                                  <div className="text-xs text-content-muted">{action.reason}</div>
                                </div>
                              ) : (
                                <span className="text-content-muted">No action</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="space-y-4">
              <div className="rounded-xl border border-border bg-surface p-4">
                <div className="text-base font-semibold text-content">Funnel context</div>
                <div className="mt-3 space-y-2 text-sm text-content-muted">
                  <div>Generated {formatDate(plan.generatedAt)}</div>
                  <div>Window {String(plan.window.datePreset || "—")}</div>
                  {plan.benchmarkContext?.deliveryMode ? <div>Delivery {plan.benchmarkContext.deliveryMode}</div> : null}
                  {plan.benchmarkContext?.priceDollars != null ? (
                    <div>Price ${plan.benchmarkContext.priceDollars.toFixed(2)}</div>
                  ) : null}
                  {plan.benchmarkContext?.atcPriceBandLabel ? <div>ATC band {plan.benchmarkContext.atcPriceBandLabel}</div> : null}
                  {plan.benchmarkContext?.profileUpdatedAt ? <div>Profile updated {formatDate(plan.benchmarkContext.profileUpdatedAt)}</div> : null}
                </div>
                {plan.benchmarkContext?.priceResolutionError ? (
                  <div className="mt-3 rounded-md border border-border bg-background px-3 py-2 text-xs text-content-muted">
                    {plan.benchmarkContext.priceResolutionError}
                  </div>
                ) : null}
              </div>

              {plan.actions.length ? (
                <Callout variant="warning" size="sm" title="Rule-triggered actions">
                  {plan.actions.length} ad{plan.actions.length === 1 ? "" : "s"} hit the current cut rules in this window.
                </Callout>
              ) : (
                <Callout variant="success" size="sm" title="Rule-triggered actions">
                  No ad-level pause actions were triggered in this window.
                </Callout>
              )}

              {plan.warnings.length ? (
                <div className="rounded-xl border border-border bg-surface p-4">
                  <div className="text-base font-semibold text-content">Warnings</div>
                  <div className="mt-3 space-y-2 text-sm text-content-muted">
                    {plan.warnings.map((warning) => (
                      <div key={warning}>{warning}</div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
