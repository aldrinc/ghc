import { useCallback, useEffect, useMemo, useState } from "react";
import { useMetaApi } from "@/api/meta";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Select, type SelectOption } from "@/components/ui/select";
import type {
  MetaManagementBenchmarkEvaluation,
  MetaManagementCustomMetricDefinition,
  MetaManagementCustomMetricEvaluation,
  MetaManagementPlan,
  MetaObjectStatusCount,
  MetaPublishRun,
} from "@/types/meta";
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

function formatWhole(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return value.toLocaleString();
}

function benchmarkStatusTone(
  status: MetaManagementBenchmarkEvaluation["status"],
): "neutral" | "accent" | "success" | "danger" {
  if (status === "good") return "success";
  if (status === "on_target") return "accent";
  if (status === "below_target") return "danger";
  return "neutral";
}

function benchmarkStatusLabel(status: MetaManagementBenchmarkEvaluation["status"]): string {
  return status.replace(/_/g, " ");
}

function customMetricStatusTone(
  status: MetaManagementCustomMetricEvaluation["status"],
): "neutral" | "accent" | "success" | "danger" {
  if (status === "good") return "success";
  if (status === "on_target") return "accent";
  if (status === "below_target") return "danger";
  return "neutral";
}

function customMetricStatusLabel(status: MetaManagementCustomMetricEvaluation["status"]): string {
  return status.replace(/_/g, " ");
}

function kpiLabel(definition?: MetaManagementCustomMetricDefinition): string {
  if (!definition) return "Target not configured";
  if (definition.target != null) {
    return `Target ${formatPct(definition.target)}`;
  }
  if (definition.minimum != null && definition.good != null) {
    return `KPI ${formatPct(definition.minimum)}-${formatPct(definition.good)}`;
  }
  if (definition.minimum != null) {
    return `KPI >${formatPct(definition.minimum)}`;
  }
  if (definition.good != null) {
    return `Good ${formatPct(definition.good)}`;
  }
  return "Target not configured";
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

function customMetricRecommendation(metric: MetaManagementCustomMetricEvaluation): string | null {
  return metric.recommendation || metric.reason || null;
}

function runLabel(run: MetaPublishRun): string {
  const campaignLabel = run.campaignName || "Published campaign";
  const createdLabel = formatDate(run.createdAt);
  const trackedMetaCampaignId = run.managementMetaCampaignId || run.metaCampaignId;
  const metaLabel = trackedMetaCampaignId ? `Meta ${shortId(trackedMetaCampaignId, 5)}` : "No Meta id";
  return `${campaignLabel} · ${createdLabel} · ${metaLabel}`;
}

function runManagementMetaCampaignId(run: MetaPublishRun | null): string | null {
  if (!run) return null;
  const overrideId = typeof run.managementMetaCampaignId === "string" ? run.managementMetaCampaignId.trim() : "";
  if (overrideId) return overrideId;
  const publishedId = typeof run.metaCampaignId === "string" ? run.metaCampaignId.trim() : "";
  return publishedId || null;
}

function runDeliveryMode(run: MetaPublishRun | null): string | null {
  const metadata = run?.metadata;
  if (!metadata || typeof metadata !== "object") return null;
  const campaignDelivery =
    "campaignDelivery" in metadata && metadata.campaignDelivery && typeof metadata.campaignDelivery === "object"
      ? metadata.campaignDelivery
      : null;
  if (!campaignDelivery || !("deliveryMode" in campaignDelivery)) return null;
  return typeof campaignDelivery.deliveryMode === "string" ? campaignDelivery.deliveryMode : null;
}

function deliveryStateTone(deliveryState: string): "neutral" | "accent" | "success" | "danger" {
  if (deliveryState === "delivering") return "success";
  if (deliveryState === "review_blocked" || deliveryState === "ads_with_issues") return "danger";
  if (deliveryState === "paused" || deliveryState === "archived") return "accent";
  return "neutral";
}

function deliveryStateLabel(deliveryState: string): string {
  return deliveryState.replace(/_/g, " ");
}

function statusCountSummary(counts: MetaObjectStatusCount[]): string {
  if (!counts.length) return "—";
  return counts.map((entry) => `${entry.value} ${entry.count}`).join(" · ");
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
    () => visiblePublishRuns.filter((run) => Boolean(runManagementMetaCampaignId(run))),
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

  const customMetricDefinitions = useMemo(() => {
    const entries = (plan?.customMetricDefinitions || []).map((definition) => [definition.metricId, definition] as const);
    return new Map(entries);
  }, [plan?.customMetricDefinitions]);

  const runOptions = useMemo<SelectOption[]>(
    () =>
      runnableRuns.map((run) => ({
        label: runLabel(run),
        value: run.id,
      })),
    [runnableRuns],
  );

  const loadPlan = useCallback(async () => {
    const trackedMetaCampaignId = runManagementMetaCampaignId(selectedRun);
    if (!trackedMetaCampaignId) {
      setPlan(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const nextPlan = await planManagement({
        metaCampaignId: trackedMetaCampaignId,
        clientId: campaign.client_id,
        metaConfigId: selectedRun?.metaConfigId || undefined,
        datePreset,
        mode: "plan_only",
        benchmarkMode: "best_effort",
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
    if (!runManagementMetaCampaignId(selectedRun)) {
      setPlan(null);
      return;
    }
    void loadPlan();
  }, [loadPlan, selectedRun]);

  const deliveryMode = runDeliveryMode(selectedRun) || plan?.benchmarkContext?.deliveryMode || null;
  const benchmarkUnavailableReason = plan?.benchmarkStatus.reason || null;
  const showBenchmarkCards = Boolean(plan?.benchmarkEvaluations.length);
  const publishedMetaCampaignId =
    typeof selectedRun?.metaCampaignId === "string" && selectedRun.metaCampaignId.trim()
      ? selectedRun.metaCampaignId.trim()
      : null;
  const trackedMetaCampaignId = runManagementMetaCampaignId(selectedRun);
  const hasManagementOverride = Boolean(
    trackedMetaCampaignId && publishedMetaCampaignId && trackedMetaCampaignId !== publishedMetaCampaignId,
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-border bg-surface p-4">
        <div>
          <div className="text-base font-semibold text-content">Manage live Meta campaigns</div>
          <div className="mt-1 text-sm text-content-muted">
            Review object state, Meta-derived custom metrics, rule-triggered actions, and funnel benchmarks when first-party data is available.
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
      {hasManagementOverride ? (
        <Callout variant="warning" size="sm" title="Managing a rebound Meta target">
          This run was originally published to Meta {shortId(publishedMetaCampaignId || "", 5)}, but management is
          currently bound to Meta {shortId(trackedMetaCampaignId || "", 5)}.
        </Callout>
      ) : null}
      {error ? (
        <Callout variant="danger" size="sm">
          {error}
        </Callout>
      ) : null}

      {plan ? (
        <>
          <div className="rounded-xl border border-border bg-surface p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-base font-semibold text-content">Live object state</div>
                <div className="mt-1 text-sm text-content-muted">{plan.objectState.deliverySummary}</div>
              </div>
              <Badge tone={deliveryStateTone(plan.objectState.deliveryState)}>
                {deliveryStateLabel(plan.objectState.deliveryState)}
              </Badge>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-xl border border-border/70 bg-background p-4">
                <div className="text-xs uppercase tracking-wide text-content-muted">Campaign state</div>
                <div className="mt-2 text-sm font-medium text-content">
                  {plan.objectState.campaignEffectiveStatus || plan.objectState.campaignStatus || "—"}
                </div>
                <div className="mt-1 text-xs text-content-muted">Configured {plan.objectState.campaignStatus || "—"}</div>
              </div>
              <div className="rounded-xl border border-border/70 bg-background p-4">
                <div className="text-xs uppercase tracking-wide text-content-muted">Ad sets</div>
                <div className="mt-2 text-2xl font-semibold text-content">{plan.objectState.adsetCount}</div>
                <div className="mt-1 text-xs text-content-muted">{statusCountSummary(plan.objectState.adsetEffectiveStatusCounts)}</div>
              </div>
              <div className="rounded-xl border border-border/70 bg-background p-4">
                <div className="text-xs uppercase tracking-wide text-content-muted">Ads</div>
                <div className="mt-2 text-2xl font-semibold text-content">{plan.objectState.adCount}</div>
                <div className="mt-1 text-xs text-content-muted">{statusCountSummary(plan.objectState.adEffectiveStatusCounts)}</div>
              </div>
              <div className="rounded-xl border border-border/70 bg-background p-4">
                <div className="text-xs uppercase tracking-wide text-content-muted">Review blockers</div>
                <div className="mt-2 text-2xl font-semibold text-content">{plan.objectState.reviewPendingCount}</div>
                <div className="mt-1 text-xs text-content-muted">
                  Issues {plan.objectState.issueCount} · Insight rows {plan.objectState.insightsRowCount}
                </div>
              </div>
            </div>
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <div className="rounded-xl border border-border/70 bg-background p-4">
                <div className="text-xs uppercase tracking-wide text-content-muted">Ad set status counts</div>
                <div className="mt-2 text-sm text-content">{statusCountSummary(plan.objectState.adsetStatusCounts)}</div>
                <div className="mt-2 text-xs text-content-muted">
                  Effective {statusCountSummary(plan.objectState.adsetEffectiveStatusCounts)}
                </div>
              </div>
              <div className="rounded-xl border border-border/70 bg-background p-4">
                <div className="text-xs uppercase tracking-wide text-content-muted">Ad status counts</div>
                <div className="mt-2 text-sm text-content">{statusCountSummary(plan.objectState.adStatusCounts)}</div>
                <div className="mt-2 text-xs text-content-muted">
                  Effective {statusCountSummary(plan.objectState.adEffectiveStatusCounts)}
                </div>
              </div>
            </div>
            {plan.objectState.issueSamples.length ? (
              <div className="mt-4 rounded-xl border border-border/70 bg-background p-4">
                <div className="text-sm font-semibold text-content">Issue samples</div>
                <div className="mt-1 text-sm text-content-muted">
                  Representative ads returned by Meta with review or issue metadata.
                </div>
                <div className="mt-4 overflow-x-auto">
                  <table className="min-w-full text-left text-sm">
                    <thead className="text-xs uppercase tracking-wide text-content-muted">
                      <tr>
                        <th className="pb-2 pr-4">Ad</th>
                        <th className="pb-2 pr-4">State</th>
                        <th className="pb-2 pr-4">Issue</th>
                        <th className="pb-2">Message</th>
                      </tr>
                    </thead>
                    <tbody>
                      {plan.objectState.issueSamples.map((sample) => (
                        <tr key={sample.adId} className="border-t border-border/70 align-top">
                          <td className="py-2 pr-4">
                            <div className="font-medium text-content">{sample.adName || sample.adId}</div>
                            <div className="text-xs text-content-muted">{shortId(sample.adId, 5)}</div>
                          </td>
                          <td className="py-2 pr-4 text-content">{sample.effectiveStatus || sample.status || "—"}</td>
                          <td className="py-2 pr-4 text-content">
                            {sample.errorSummary || (sample.errorCode != null ? `Error ${sample.errorCode}` : "—")}
                          </td>
                          <td className="py-2 text-content-muted">{sample.errorMessage || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
          </div>

          {plan.customMetricSummary.length ? (
            <div className="rounded-xl border border-border bg-surface p-4">
              <div className="text-base font-semibold text-content">Meta derived custom metrics</div>
              <div className="mt-1 text-sm text-content-muted">
                Meta-estimated ratios computed from raw insight primitives. These stay separate from MOS first-party funnel benchmarks.
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                {plan.customMetricSummary.map((metric) => {
                  const definition = customMetricDefinitions.get(metric.metricId);
                  return (
                    <div key={metric.metricId} className="rounded-xl border border-border/70 bg-background p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-xs uppercase tracking-wide text-content-muted">
                            {definition?.label || metric.metricId}
                          </div>
                          <div className="mt-1 text-2xl font-semibold text-content">{formatPct(metric.value)}</div>
                        </div>
                        <Badge tone={customMetricStatusTone(metric.status)}>{customMetricStatusLabel(metric.status)}</Badge>
                      </div>
                      {definition?.formula ? <div className="mt-3 text-xs text-content-muted">{definition.formula}</div> : null}
                      <div className="mt-2 space-y-1 text-xs text-content-muted">
                        <div>{kpiLabel(definition)}</div>
                        <div>
                          {definition?.numeratorLabel || "Numerator"} {formatWhole(metric.numerator)} /{" "}
                          {definition?.denominatorLabel || "Denominator"} {formatWhole(metric.denominator)}
                        </div>
                        {metric.resolvedSources.length ? <div>Sources {metric.resolvedSources.join(", ")}</div> : null}
                      </div>
                      {customMetricRecommendation(metric) ? (
                        <div className="mt-3 text-sm text-content-muted">{customMetricRecommendation(metric)}</div>
                      ) : null}
                      {metric.warnings.length ? (
                        <div className="mt-3 rounded-md border border-border bg-surface px-3 py-2 text-xs text-content-muted">
                          {metric.warnings.join(", ")}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}

          {!plan.benchmarkStatus.available ? (
            <Callout variant="warning" size="sm" title="Funnel benchmarks unavailable">
              {benchmarkUnavailableReason || "This campaign is being managed with Meta-native metrics only."}
            </Callout>
          ) : null}

          {showBenchmarkCards ? (
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
          ) : null}

          <div className="grid gap-4 xl:grid-cols-[1.4fr,1fr]">
            <div className="rounded-xl border border-border bg-surface p-4">
              <div className="text-base font-semibold text-content">Ad-level snapshot</div>
              <div className="mt-1 text-sm text-content-muted">Raw Meta ad metrics plus any pause recommendations from the current ruleset.</div>
              {!plan.rows.length ? (
                <div className="mt-3 rounded-md border border-border bg-background px-3 py-2 text-sm text-content-muted">
                  {plan.objectState.deliverySummary}
                </div>
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
              {plan.customMetricRows.length ? (
                <div className="rounded-xl border border-border bg-surface p-4">
                  <div className="text-base font-semibold text-content">Per-ad derived metric report</div>
                  <div className="mt-1 text-sm text-content-muted">
                    Strategy-facing view of the custom metrics for each ad in the selected window.
                  </div>
                  <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full text-left text-sm">
                      <thead className="text-xs uppercase tracking-wide text-content-muted">
                        <tr>
                          <th className="pb-2 pr-4">Ad</th>
                          <th className="pb-2 pr-4">ATC</th>
                          <th className="pb-2 pr-4">IC</th>
                          <th className="pb-2 pr-4">CVR</th>
                          <th className="pb-2 pr-4">Purchase</th>
                          <th className="pb-2">Video hold</th>
                        </tr>
                      </thead>
                      <tbody>
                        {plan.customMetricRows.map((row) => {
                          const metricMap = new Map(row.metrics.map((metric) => [metric.metricId, metric] as const));
                          const atc = metricMap.get("meta_atc_ratio_pct");
                          const ic = metricMap.get("meta_ic_ratio_pct");
                          const conversion = metricMap.get("meta_conversion_rate_pct");
                          const purchase = metricMap.get("meta_purchase_ratio_pct");
                          const videoHold = metricMap.get("meta_video_hold_rate_pct");
                          return (
                            <tr key={row.adId} className="border-t border-border/70 align-top">
                              <td className="py-2 pr-4">
                                <div className="font-medium text-content">{row.adName || row.adId}</div>
                                <div className="text-xs text-content-muted">{shortId(row.adId, 5)}</div>
                              </td>
                              {[atc, ic, conversion, purchase, videoHold].map((metric, index) => (
                                <td key={`${row.adId}-${index}`} className="py-2 pr-4 text-content">
                                  <div>{formatPct(metric?.value)}</div>
                                  <div className="text-xs text-content-muted">
                                    {formatWhole(metric?.numerator)} / {formatWhole(metric?.denominator)}
                                  </div>
                                </td>
                              ))}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}

              <div className="rounded-xl border border-border bg-surface p-4">
                <div className="text-base font-semibold text-content">Management context</div>
                <div className="mt-3 space-y-2 text-sm text-content-muted">
                  <div>Generated {formatDate(plan.generatedAt)}</div>
                  <div>Window {String(plan.window.datePreset || "—")}</div>
                  <div>Scope {plan.managementScope === "meta_plus_funnel" ? "Meta + funnel" : "Meta only"}</div>
                  {deliveryMode ? <div>Delivery {deliveryMode}</div> : null}
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
