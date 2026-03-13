import { useCallback, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import { useClientShopifyStatus } from "@/api/clients";
import { useFunnels } from "@/api/funnels";
import { useMetaApi } from "@/api/meta";
import { CampaignPaidAdsQaCard } from "@/components/campaigns/CampaignPaidAdsQaCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { resolveRequiredApiBaseUrl } from "@/lib/apiBaseUrl";
import {
  resolveConfiguredShopHostedOrigin,
  resolveShopHostedUrl,
  resolveWindowShopHostedOrigin,
} from "@/lib/shopHostedFunnels";
import type { AssetBrief } from "@/types/artifacts";
import type { Campaign } from "@/types/common";
import type { Funnel } from "@/types/funnels";
import type {
  MetaAdSetSpec,
  MetaPipelineAsset,
  MetaPublishPlanValidation,
  MetaPublishRun,
  MetaPublishSelection,
  MetaPublishSelectionDecision,
} from "@/types/meta";

type CampaignMetaAdsPanelProps = {
  campaign: Campaign;
  assetBriefs: AssetBrief[];
};

type MetaPackageView = "review" | "final";

type MetaPublishCampaignForm = {
  publishBaseUrl: string;
  campaignName: string;
  campaignObjective: string;
  buyingType: string;
  specialAdCategories: string;
};

type MetaPublishAdSetForm = {
  name: string;
  optimizationGoal: string;
  billingEvent: string;
  targetingJson: string;
  placementsJson: string;
  dailyBudget: string;
  lifetimeBudget: string;
  bidAmount: string;
  startTime: string;
  endTime: string;
  promotedObjectJson: string;
  conversionDomain: string;
};

type MetaReviewSetupIssue = {
  assetId: string;
  assetBriefId?: string | null;
  generationKey?: string | null;
  funnelId?: string | null;
  destinationPage?: string | null;
  normalizedDestinationPage?: string | null;
  issues: Array<{
    ruleId?: string | null;
    title?: string | null;
    message?: string | null;
  }>;
};

const apiBaseUrl = resolveRequiredApiBaseUrl();

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function shortId(value?: string | null, size = 6) {
  if (!value) return "—";
  return value.length > size * 2 ? `${value.slice(0, size)}…${value.slice(-size)}` : value;
}

function resolveAssetUrl(path?: string | null): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  return `${apiBaseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

function getErrorMessage(err: unknown) {
  if (typeof err === "string") return err;
  if (err && typeof err === "object" && "message" in err) {
    const apiError = err as ApiError;
    const detailMessage = (apiError.raw as { detail?: { message?: string } } | undefined)?.detail?.message;
    return detailMessage || apiError.message || "Request failed";
  }
  return "Request failed";
}

function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function readNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function readRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function formatFunnelLabel(funnel?: Funnel | null, fallbackFunnelId?: string | null): string {
  if (funnel) {
    const routeLabel = funnel.route_slug ? `/${funnel.route_slug}` : shortId(funnel.id, 4);
    return `${funnel.name} (${routeLabel})`;
  }
  if (fallbackFunnelId) {
    return `Funnel ${shortId(fallbackFunnelId, 4)}`;
  }
  return "Unknown funnel";
}

function getGenerationGroup(item: MetaPipelineAsset): {
  key: string;
  kind: "batch" | "remoteJob" | "asset";
  label: string;
} {
  const metadata = readRecord(item.asset.ai_metadata);
  const batchId = readString(metadata?.creativeGenerationBatchId);
  if (batchId) {
    return {
      key: `batch:${batchId}`,
      kind: "batch",
      label: `Batch ${shortId(batchId, 5)}`,
    };
  }

  const remoteJobId = readString(metadata?.remoteJobId);
  if (remoteJobId) {
    return {
      key: `remoteJob:${remoteJobId}`,
      kind: "remoteJob",
      label: `Render ${shortId(remoteJobId, 5)}`,
    };
  }

  return {
    key: `asset:${item.asset.id}`,
    kind: "asset",
    label: `Asset ${shortId(item.asset.id, 5)}`,
  };
}

function readHostname(value?: string | null): string | null {
  if (!value) return null;
  try {
    return new URL(value).hostname.replace(/^www\./i, "");
  } catch {
    return null;
  }
}

type CopyFieldProps = {
  label: string;
  value?: string | null;
  multiline?: boolean;
};

function CopyField({ label, value, multiline = false }: CopyFieldProps) {
  return (
    <div className="space-y-1">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-muted">{label}</div>
      <div
        className={[
          "rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-content",
          multiline ? "whitespace-pre-wrap leading-6" : "",
        ].join(" ")}
      >
        {value || "—"}
      </div>
    </div>
  );
}

type MetaFeedPreviewProps = {
  assetUrl: string | null;
  assetAlt: string;
  primaryText?: string | null;
  headline?: string | null;
  description?: string | null;
  cta?: string | null;
  destinationUrl?: string | null;
  specReady: boolean;
  specSourceLabel: string;
};

function MetaFeedPreview({
  assetUrl,
  assetAlt,
  primaryText,
  headline,
  description,
  cta,
  destinationUrl,
  specReady,
  specSourceLabel,
}: MetaFeedPreviewProps) {
  const hostname = readHostname(destinationUrl);

  return (
    <div className="overflow-hidden rounded-[22px] border border-border bg-surface text-content shadow-sm">
      <div className="border-b border-divider bg-surface-2 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-muted">Meta Feed Preview</div>
            <div className="text-xs text-content-muted">Sample layout using the prepared creative spec</div>
          </div>
          <span
            className={[
              "inline-flex rounded-full border px-2.5 py-1 text-[11px] font-semibold",
              specReady ? "border-success/30 bg-success/10 text-success" : "border-warning/30 bg-warning/10 text-warning",
            ].join(" ")}
          >
            {specSourceLabel}
          </span>
        </div>
      </div>

      {specReady ? (
        <>
          <div className="space-y-3 px-4 py-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted text-sm font-semibold text-content">
                B
              </div>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-content">Brand Page</div>
                <div className="text-xs text-content-muted">Sponsored</div>
              </div>
            </div>
            <div className="whitespace-pre-wrap text-[13px] leading-5 text-content">
              {primaryText || "Primary text missing from prepared spec."}
            </div>
          </div>

          <div className="border-y border-divider bg-surface-2">
            {assetUrl ? (
              <img src={assetUrl} alt={assetAlt} className="h-[320px] w-full object-contain" loading="lazy" />
            ) : (
              <div className="flex h-[320px] items-center justify-center px-4 text-sm text-content-muted">
                Generated remix preview missing.
              </div>
            )}
          </div>

          <div className="space-y-3 px-4 py-4">
            <div>
              <div className="text-[11px] uppercase tracking-[0.14em] text-content-muted">{hostname || "destination url missing"}</div>
              <div className="mt-1 text-[15px] font-semibold leading-5 text-content">
                {headline || "Headline missing from prepared spec."}
              </div>
              {description ? <div className="mt-1 text-sm leading-5 text-content-muted">{description}</div> : null}
            </div>
            <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-surface-2 px-3 py-2">
              <div className="text-xs text-content-muted">Call to action</div>
              <div className="rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground">
                {cta || "Learn More"}
              </div>
            </div>
          </div>
        </>
      ) : (
        <div className="flex min-h-[520px] items-center justify-center px-6 py-10 text-center text-sm leading-6 text-content-muted">
          Prepare Meta review to render the exact upload preview for this asset.
        </div>
      )}
    </div>
  );
}

function publishDecisionTone(
  decision?: MetaPublishSelectionDecision | null,
): "neutral" | "accent" | "success" | "danger" {
  if (decision === "excluded") return "danger";
  return "success";
}

function publishDecisionLabel(decision?: MetaPublishSelectionDecision | null): string {
  if (decision === "excluded") return "Excluded from Meta";
  return "Included by default";
}

function formatJsonInput(value: unknown): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "";
  }
}

function parseJsonObjectInput(value: string, label: string): Record<string, unknown> | null {
  const cleaned = value.trim();
  if (!cleaned) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(cleaned);
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

function parseIntegerInput(value: string, label: string): number | null {
  const cleaned = value.trim();
  if (!cleaned) return null;
  if (!/^-?\d+$/.test(cleaned)) {
    throw new Error(`${label} must be a whole number.`);
  }
  return Number(cleaned);
}

function toLocalDateTimeValue(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offsetDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return offsetDate.toISOString().slice(0, 16);
}

function fromLocalDateTimeValue(value: string): string | null {
  const cleaned = value.trim();
  if (!cleaned) return null;
  const date = new Date(cleaned);
  if (Number.isNaN(date.getTime())) {
    throw new Error("Date/time values must be valid.");
  }
  return date.toISOString();
}

function buildInitialPublishCampaignForm(reviewBaseUrl: string): MetaPublishCampaignForm {
  return {
    publishBaseUrl: reviewBaseUrl || "",
    campaignName: "",
    campaignObjective: "",
    buyingType: "",
    specialAdCategories: "",
  };
}

function buildAdSetForm(spec: MetaAdSetSpec): MetaPublishAdSetForm {
  return {
    name: spec.name || "",
    optimizationGoal: spec.optimization_goal || "",
    billingEvent: spec.billing_event || "",
    targetingJson: formatJsonInput(spec.targeting),
    placementsJson: formatJsonInput(spec.placements),
    dailyBudget: spec.daily_budget != null ? String(spec.daily_budget) : "",
    lifetimeBudget: spec.lifetime_budget != null ? String(spec.lifetime_budget) : "",
    bidAmount: spec.bid_amount != null ? String(spec.bid_amount) : "",
    startTime: toLocalDateTimeValue(spec.start_time),
    endTime: toLocalDateTimeValue(spec.end_time),
    promotedObjectJson: formatJsonInput(spec.promoted_object),
    conversionDomain: spec.conversion_domain || "",
  };
}

export function CampaignMetaAdsPanel({ campaign, assetBriefs }: CampaignMetaAdsPanelProps) {
  const queryClient = useQueryClient();
  const { post } = useApiClient();
  const shopifyStatusQuery = useClientShopifyStatus(campaign.client_id);
  const funnelsQuery = useFunnels({ campaignId: campaign.id });
  const {
    getConfig,
    listPipelineAssets,
    listPublishSelections,
    savePublishSelections,
    updateAdSetSpec,
    validatePublishPlan,
    listPublishRuns,
    createPublishRun,
  } = useMetaApi();
  const browserReviewBaseUrl = resolveWindowShopHostedOrigin();
  const storefrontDomain = useMemo(() => {
    const displayDomain = readString(shopifyStatusQuery.data?.displayShopDomain);
    if (displayDomain) return displayDomain;
    const shopDomain = readString(shopifyStatusQuery.data?.shopDomain);
    return shopDomain;
  }, [shopifyStatusQuery.data?.displayShopDomain, shopifyStatusQuery.data?.shopDomain]);
  const reviewBaseUrl = useMemo(() => {
    return resolveConfiguredShopHostedOrigin(storefrontDomain) || browserReviewBaseUrl;
  }, [browserReviewBaseUrl, storefrontDomain]);

  const [config, setConfig] = useState<{
    adAccountId: string;
    pageId?: string | null;
    graphApiVersion?: string | null;
  } | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [pipeline, setPipeline] = useState<MetaPipelineAsset[]>([]);
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [generatePending, setGeneratePending] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [preparePending, setPreparePending] = useState(false);
  const [prepareError, setPrepareError] = useState<string | null>(null);
  const [prepareIssues, setPrepareIssues] = useState<MetaReviewSetupIssue[]>([]);
  const [lastWorkflowRunId, setLastWorkflowRunId] = useState<string | null>(null);
  const [lastPreparedAt, setLastPreparedAt] = useState<string | null>(null);
  const [autoRefreshUntil, setAutoRefreshUntil] = useState<number | null>(null);
  const [latestGenerationOnly, setLatestGenerationOnly] = useState(true);
  const [selectedFunnelId, setSelectedFunnelId] = useState<string | null>(null);
  const [packageView, setPackageView] = useState<MetaPackageView>("review");
  const [publishSelections, setPublishSelections] = useState<MetaPublishSelection[]>([]);
  const [selectionLoading, setSelectionLoading] = useState(false);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const [selectionPendingAssetIds, setSelectionPendingAssetIds] = useState<string[]>([]);
  const [publishCampaignForm, setPublishCampaignForm] = useState<MetaPublishCampaignForm>(() =>
    buildInitialPublishCampaignForm(reviewBaseUrl),
  );
  const [publishAdSetForms, setPublishAdSetForms] = useState<Record<string, MetaPublishAdSetForm>>({});
  const [publishFormError, setPublishFormError] = useState<string | null>(null);
  const [publishValidation, setPublishValidation] = useState<MetaPublishPlanValidation | null>(null);
  const [publishValidationPending, setPublishValidationPending] = useState(false);
  const [publishPending, setPublishPending] = useState(false);
  const [publishRuns, setPublishRuns] = useState<MetaPublishRun[]>([]);
  const [publishRunsLoading, setPublishRunsLoading] = useState(false);
  const [publishRunsError, setPublishRunsError] = useState<string | null>(null);

  const assetBriefIds = useMemo(
    () => assetBriefs.map((brief) => brief.id).filter((briefId): briefId is string => Boolean(briefId)),
    [assetBriefs],
  );
  const briefById = useMemo(() => new Map(assetBriefs.map((brief) => [brief.id, brief])), [assetBriefs]);
  const funnelById = useMemo(
    () => new Map((funnelsQuery.data || []).map((funnel) => [funnel.id, funnel])),
    [funnelsQuery.data],
  );

  const refreshPipeline = useCallback(async () => {
    setPipelineLoading(true);
    setPipelineError(null);
    try {
      const data = await listPipelineAssets({
        campaignId: campaign.id,
      });
      setPipeline(data);
    } catch (err) {
      setPipeline([]);
      setPipelineError(getErrorMessage(err));
    } finally {
      setPipelineLoading(false);
    }
  }, [campaign.id, listPipelineAssets]);

  useEffect(() => {
    let cancelled = false;
    getConfig()
      .then((data) => {
        if (cancelled) return;
        setConfig({
          adAccountId: data.adAccountId,
          pageId: data.pageId,
          graphApiVersion: data.graphApiVersion,
        });
        setConfigError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setConfig(null);
        setConfigError(getErrorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [getConfig]);

  useEffect(() => {
    void refreshPipeline();
  }, [refreshPipeline]);

  useEffect(() => {
    if (!autoRefreshUntil) return;
    if (Date.now() >= autoRefreshUntil) {
      setAutoRefreshUntil(null);
      return;
    }
    const timer = window.setInterval(() => {
      if (Date.now() >= autoRefreshUntil) {
        window.clearInterval(timer);
        setAutoRefreshUntil(null);
        return;
      }
      void refreshPipeline();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [autoRefreshUntil, refreshPipeline]);

  const handleGenerateAssets = async () => {
    setGenerateError(null);
    if (!assetBriefIds.length) {
      setGenerateError("No asset briefs exist for this campaign yet.");
      return;
    }
    setGeneratePending(true);
    try {
      const response = await post<{ workflow_run_id: string }>(`/campaigns/${campaign.id}/creative/produce`, {
        assetBriefIds,
      });
      setLastWorkflowRunId(response.workflow_run_id);
      setAutoRefreshUntil(Date.now() + 3 * 60 * 1000);
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      await refreshPipeline();
    } catch (err) {
      setGenerateError(getErrorMessage(err));
    } finally {
      setGeneratePending(false);
    }
  };

  const handlePrepareMetaReview = async () => {
    setPrepareError(null);
    setPrepareIssues([]);
    if (!activeFunnelId) {
      setPrepareError("Pick one funnel in the Meta ads tab before preparing Meta review.");
      return;
    }
    if (!prepareAssetBriefIds.length) {
      setPrepareError(
        canPrepareMetaReview && latestGenerationSummary
          ? "No generated assets exist in the visible generation yet."
          : "Switch to the latest generation and select a funnel before preparing Meta review.",
      );
      return;
    }
    setPreparePending(true);
    try {
      await post(`/campaigns/${campaign.id}/meta/review-setup`, {
        assetBriefIds: prepareAssetBriefIds,
        funnelId: activeFunnelId,
        generationBatchId:
          latestGenerationOnly && latestGenerationSummary?.kind === "batch" ? latestGenerationBatchId : undefined,
      });
      setLastPreparedAt(new Date().toISOString());
      setPrepareIssues([]);
      await refreshPipeline();
    } catch (err) {
      const apiError = err as ApiError;
      const detail = readRecord((apiError.raw as { detail?: unknown } | undefined)?.detail);
      const invalidAssets = Array.isArray(detail?.invalidAssets) ? detail.invalidAssets : [];
      const parsedIssues: MetaReviewSetupIssue[] = invalidAssets
        .map((entry) => {
          const record = readRecord(entry);
          if (!record) return null;
          const issues = Array.isArray(record.issues)
            ? record.issues
                .map((issue) => {
                  const issueRecord = readRecord(issue);
                  if (!issueRecord) return null;
                  return {
                    ruleId: readString(issueRecord.ruleId),
                    title: readString(issueRecord.title),
                    message: readString(issueRecord.message),
                  };
                })
                .filter((issue): issue is NonNullable<typeof issue> => Boolean(issue))
            : [];
          return {
            assetId: readString(record.assetId) || "unknown",
            assetBriefId: readString(record.assetBriefId),
            generationKey: readString(record.generationKey),
            funnelId: readString(record.funnelId),
            destinationPage: readString(record.destinationPage),
            normalizedDestinationPage: readString(record.normalizedDestinationPage),
            issues,
          };
        })
        .filter((entry): entry is MetaReviewSetupIssue => Boolean(entry));
      setPrepareIssues(parsedIssues);
      setPrepareError(getErrorMessage(err));
    } finally {
      setPreparePending(false);
    }
  };

  const creativeSpecCount = useMemo(
    () => pipeline.filter((item) => Boolean(item.creative_spec?.id)).length,
    [pipeline],
  );
  const adsetSpecCount = useMemo(() => {
    const ids = new Set<string>();
    pipeline.forEach((item) => {
      (item.adset_specs || []).forEach((spec) => {
        if (spec.id) ids.add(spec.id);
      });
    });
    return ids.size;
  }, [pipeline]);
  const hasGeneratedAssets = pipeline.length > 0;
  const generationSummaries = useMemo(() => {
    const byGeneration = new Map<
      string,
      { key: string; kind: "batch" | "remoteJob" | "asset"; label: string; latestCreatedAt: number; count: number }
    >();
    pipeline.forEach((item) => {
      const generation = getGenerationGroup(item);
      const createdAt = item.asset.created_at ? new Date(item.asset.created_at).getTime() : 0;
      const existing = byGeneration.get(generation.key);
      if (!existing) {
        byGeneration.set(generation.key, {
          ...generation,
          latestCreatedAt: createdAt,
          count: 1,
        });
        return;
      }
      existing.latestCreatedAt = Math.max(existing.latestCreatedAt, createdAt);
      existing.count += 1;
    });
    return Array.from(byGeneration.values()).sort((a, b) => b.latestCreatedAt - a.latestCreatedAt);
  }, [pipeline]);
  const latestGenerationSummary = generationSummaries[0] ?? null;
  const latestGenerationKey = latestGenerationSummary?.key ?? null;
  const latestGenerationBatchId =
    latestGenerationSummary?.kind === "batch" ? latestGenerationSummary.key.slice("batch:".length) : null;
  const getPipelineItemFunnelId = useCallback(
    (item: MetaPipelineAsset) => {
      const briefId = readString(item.asset.ai_metadata?.assetBriefId);
      if (!briefId) return null;
      return readString(briefById.get(briefId)?.funnelId);
    },
    [briefById],
  );
  const latestGenerationPipeline = useMemo(() => {
    if (!latestGenerationKey) return [];
    return pipeline.filter((item) => getGenerationGroup(item).key === latestGenerationKey);
  }, [latestGenerationKey, pipeline]);
  const latestGenerationFunnelIds = useMemo(() => {
    const ids = new Set<string>();
    latestGenerationPipeline.forEach((item) => {
      const funnelId = getPipelineItemFunnelId(item);
      if (funnelId) ids.add(funnelId);
    });
    return Array.from(ids);
  }, [getPipelineItemFunnelId, latestGenerationPipeline]);
  const funnelScopeOptions = useMemo(
    () =>
      latestGenerationFunnelIds.map((funnelId) => ({
        label: formatFunnelLabel(funnelById.get(funnelId) || null, funnelId),
        value: funnelId,
      })),
    [funnelById, latestGenerationFunnelIds],
  );
  const latestGenerationUnmappedCount = useMemo(
    () => latestGenerationPipeline.filter((item) => !getPipelineItemFunnelId(item)).length,
    [getPipelineItemFunnelId, latestGenerationPipeline],
  );
  const activeFunnelId = selectedFunnelId || (latestGenerationFunnelIds.length === 1 ? latestGenerationFunnelIds[0] : null);
  const activeFunnel = activeFunnelId ? funnelById.get(activeFunnelId) || null : null;
  const activeFunnelLabel = activeFunnelId ? formatFunnelLabel(activeFunnel, activeFunnelId) : null;
  const visiblePublishRuns = useMemo(() => {
    if (!activeFunnelId) return publishRuns;
    return publishRuns.filter((run) => {
      const runFunnelId = readString(run.metadata?.funnelId);
      return !runFunnelId || runFunnelId === activeFunnelId;
    });
  }, [activeFunnelId, publishRuns]);
  const baseVisiblePipeline = useMemo(() => {
    if (!latestGenerationOnly || !latestGenerationKey) return pipeline;
    return pipeline.filter((item) => getGenerationGroup(item).key === latestGenerationKey);
  }, [latestGenerationKey, latestGenerationOnly, pipeline]);
  const visiblePipeline = useMemo(() => {
    if (!activeFunnelId) {
      return latestGenerationFunnelIds.length > 1 ? [] : baseVisiblePipeline;
    }
    return baseVisiblePipeline.filter((item) => getPipelineItemFunnelId(item) === activeFunnelId);
  }, [activeFunnelId, baseVisiblePipeline, getPipelineItemFunnelId, latestGenerationFunnelIds.length]);
  const latestGenerationScopedPipeline = useMemo(() => {
    if (!activeFunnelId) return [];
    return latestGenerationPipeline.filter((item) => getPipelineItemFunnelId(item) === activeFunnelId);
  }, [activeFunnelId, getPipelineItemFunnelId, latestGenerationPipeline]);
  const hiddenLegacyCount = useMemo(() => {
    if (!latestGenerationOnly || !latestGenerationKey) return 0;
    return pipeline.length - baseVisiblePipeline.length;
  }, [baseVisiblePipeline.length, latestGenerationKey, latestGenerationOnly, pipeline.length]);
  const hiddenOtherFunnelCount = useMemo(() => {
    if (!activeFunnelId) return 0;
    return baseVisiblePipeline.length - visiblePipeline.length;
  }, [activeFunnelId, baseVisiblePipeline.length, visiblePipeline.length]);
  const visibleMissingCreativeSpecCount = useMemo(
    () => visiblePipeline.filter((item) => !item.creative_spec?.id).length,
    [visiblePipeline],
  );
  const visibleAssetBriefIds = useMemo(() => {
    const ids = new Set<string>();
    visiblePipeline.forEach((item) => {
      const briefId = readString(item.asset.ai_metadata?.assetBriefId);
      if (briefId) ids.add(briefId);
    });
    return Array.from(ids);
  }, [visiblePipeline]);
  const prepareAssetBriefIds = useMemo(() => {
    return visibleAssetBriefIds;
  }, [visibleAssetBriefIds]);
  const selectionByAssetId = useMemo(
    () => new Map(publishSelections.map((selection) => [selection.assetId, selection])),
    [publishSelections],
  );
  const includedPackageItems = useMemo(
    () => latestGenerationScopedPipeline.filter((item) => selectionByAssetId.get(item.asset.id)?.decision !== "excluded"),
    [latestGenerationScopedPipeline, selectionByAssetId],
  );
  const excludedPackageCount = useMemo(
    () => latestGenerationScopedPipeline.filter((item) => selectionByAssetId.get(item.asset.id)?.decision === "excluded").length,
    [latestGenerationScopedPipeline, selectionByAssetId],
  );
  const canManagePublishPackage = latestGenerationOnly && Boolean(latestGenerationKey) && Boolean(activeFunnelId);
  const canPrepareMetaReview = latestGenerationOnly && Boolean(latestGenerationKey) && Boolean(activeFunnelId);
  const includedAdSetSpecs = useMemo(() => {
    const byId = new Map<string, MetaAdSetSpec>();
    includedPackageItems.forEach((item) => {
      (item.adset_specs || []).forEach((spec) => {
        if (!spec.id || byId.has(spec.id)) return;
        byId.set(spec.id, spec);
      });
    });
    return Array.from(byId.values());
  }, [includedPackageItems]);
  const groupedPipeline = useMemo(() => {
    const groups = new Map<
      number,
      {
        requirementIndex: number;
        title: string;
        funnelStage: string | null;
        items: MetaPipelineAsset[];
      }
    >();
    visiblePipeline.forEach((item) => {
      const requirementIndex = readNumber(item.asset.ai_metadata?.requirementIndex);
      const creativeMetadata = (item.creative_spec?.metadata_json || {}) as Record<string, unknown>;
      const swipeCopyPack = readRecord(item.asset.ai_metadata?.swipeCopyPack);
      const requirement = (creativeMetadata.requirement || {}) as Record<string, unknown>;
      const title =
        readString(requirement.hook) ||
        readString(item.creative_spec?.headline) ||
        readString(swipeCopyPack?.metaHeadline) ||
        readString(swipeCopyPack?.selectedVariation) ||
        readString(item.creative_spec?.name) ||
        item.asset.public_id;
      const funnelStage = readString(requirement.funnelStage) || readString(swipeCopyPack?.funnelStage);
      const key = requirementIndex ?? -1;
      const existing = groups.get(key);
      if (!existing) {
        groups.set(key, {
          requirementIndex: key,
          title,
          funnelStage,
          items: [item],
        });
        return;
      }
      existing.items.push(item);
    });
    return Array.from(groups.values())
      .sort((a, b) => a.requirementIndex - b.requirementIndex)
      .map((group) => ({
        ...group,
        items: group.items.sort((left, right) => {
          const leftSwipeInputs = readRecord(left.asset.ai_metadata?.swipeCopyInputs);
          const rightSwipeInputs = readRecord(right.asset.ai_metadata?.swipeCopyInputs);
          const leftSourceMedia = readRecord(leftSwipeInputs?.adImageOrVideo);
          const rightSourceMedia = readRecord(rightSwipeInputs?.adImageOrVideo);
          const leftLabel =
            readString(leftSourceMedia?.sourceLabel) || readString(left.asset.ai_metadata?.swipeSourceLabel) || left.asset.public_id;
          const rightLabel =
            readString(rightSourceMedia?.sourceLabel) || readString(right.asset.ai_metadata?.swipeSourceLabel) || right.asset.public_id;
          return leftLabel.localeCompare(rightLabel);
        }),
      }));
  }, [visiblePipeline]);

  useEffect(() => {
    if (!latestGenerationKey) return;
    setLatestGenerationOnly(true);
  }, [latestGenerationKey]);

  useEffect(() => {
    if (!latestGenerationFunnelIds.length) {
      setSelectedFunnelId(null);
      return;
    }
    if (latestGenerationFunnelIds.length === 1) {
      setSelectedFunnelId(latestGenerationFunnelIds[0]);
      return;
    }
    setSelectedFunnelId((current) => (current && latestGenerationFunnelIds.includes(current) ? current : null));
  }, [latestGenerationFunnelIds]);

  useEffect(() => {
    setPrepareError(null);
    setPrepareIssues([]);
    setPublishValidation(null);
    setPublishFormError(null);
  }, [activeFunnelId, latestGenerationKey]);

  useEffect(() => {
    if (!latestGenerationKey) {
      setPublishSelections([]);
      setSelectionError(null);
      setSelectionLoading(false);
      return;
    }

    let cancelled = false;
    setSelectionLoading(true);
    setSelectionError(null);
    listPublishSelections(campaign.id, latestGenerationKey)
      .then((data) => {
        if (cancelled) return;
        setPublishSelections(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setPublishSelections([]);
        setSelectionError(getErrorMessage(err));
      })
      .finally(() => {
        if (cancelled) return;
        setSelectionLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [campaign.id, latestGenerationKey, listPublishSelections]);

  useEffect(() => {
    setPublishCampaignForm((current) => {
      const cleanedCurrent = current.publishBaseUrl.trim();
      const browserDefault = (browserReviewBaseUrl || "").trim();
      if (cleanedCurrent && cleanedCurrent !== browserDefault) return current;
      return { ...current, publishBaseUrl: reviewBaseUrl || "" };
    });
  }, [browserReviewBaseUrl, reviewBaseUrl]);

  useEffect(() => {
    setPublishAdSetForms((current) => {
      const next: Record<string, MetaPublishAdSetForm> = {};
      includedAdSetSpecs.forEach((spec) => {
        next[spec.id] = current[spec.id] || buildAdSetForm(spec);
      });
      return next;
    });
  }, [includedAdSetSpecs]);

  useEffect(() => {
    let cancelled = false;
    setPublishRunsLoading(true);
    setPublishRunsError(null);
    listPublishRuns(campaign.id)
      .then((data) => {
        if (cancelled) return;
        setPublishRuns(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setPublishRuns([]);
        setPublishRunsError(getErrorMessage(err));
      })
      .finally(() => {
        if (cancelled) return;
        setPublishRunsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [campaign.id, listPublishRuns]);

  const handleSetPublishDecision = useCallback(
    async (assetId: string, decision: MetaPublishSelectionDecision | null) => {
      if (!latestGenerationKey) return;
      setSelectionError(null);
      setSelectionPendingAssetIds((current) => (current.includes(assetId) ? current : [...current, assetId]));
      try {
        const nextSelections = await savePublishSelections(campaign.id, {
          generationKey: latestGenerationKey,
          decisions: [{ assetId, decision }],
        });
        setPublishSelections(nextSelections);
      } catch (err) {
        setSelectionError(getErrorMessage(err));
      } finally {
        setSelectionPendingAssetIds((current) => current.filter((currentAssetId) => currentAssetId !== assetId));
      }
    },
    [campaign.id, latestGenerationKey, savePublishSelections],
  );

  const updatePublishCampaignField = useCallback(
    <K extends keyof MetaPublishCampaignForm>(field: K, value: MetaPublishCampaignForm[K]) => {
      setPublishCampaignForm((current) => ({ ...current, [field]: value }));
    },
    [],
  );

  const updatePublishAdSetField = useCallback(
    <K extends keyof MetaPublishAdSetForm>(adsetSpecId: string, field: K, value: MetaPublishAdSetForm[K]) => {
      setPublishAdSetForms((current) => ({
        ...current,
        [adsetSpecId]: {
          ...(current[adsetSpecId] || buildAdSetForm(includedAdSetSpecs.find((spec) => spec.id === adsetSpecId) || ({
            id: adsetSpecId,
            name: "",
            status: "draft",
          } as MetaAdSetSpec))),
          [field]: value,
        },
      }));
    },
    [includedAdSetSpecs],
  );

  const buildPublishRequestPayload = useCallback(() => {
    if (!latestGenerationKey) {
      throw new Error("No latest generation is selected for publish.");
    }
    if (!activeFunnelId) {
      throw new Error("Pick one funnel before validating or publishing the Meta package.");
    }
    return {
      generationKey: latestGenerationKey,
      funnelId: activeFunnelId,
      publishBaseUrl: publishCampaignForm.publishBaseUrl.trim(),
      campaignName: publishCampaignForm.campaignName.trim(),
      campaignObjective: publishCampaignForm.campaignObjective.trim(),
      buyingType: publishCampaignForm.buyingType.trim() || null,
      specialAdCategories: publishCampaignForm.specialAdCategories
        .split(",")
        .map((entry) => entry.trim())
        .filter(Boolean),
    };
  }, [activeFunnelId, latestGenerationKey, publishCampaignForm]);

  const persistPublishAdSetConfigs = useCallback(async () => {
    for (const spec of includedAdSetSpecs) {
      const form = publishAdSetForms[spec.id] || buildAdSetForm(spec);
      const payload = {
        name: form.name.trim() || null,
        optimizationGoal: form.optimizationGoal.trim() || null,
        billingEvent: form.billingEvent.trim() || null,
        targeting: parseJsonObjectInput(form.targetingJson, `${spec.name || spec.id} targeting`),
        placements: parseJsonObjectInput(form.placementsJson, `${spec.name || spec.id} placements`),
        dailyBudget: parseIntegerInput(form.dailyBudget, `${spec.name || spec.id} daily budget`),
        lifetimeBudget: parseIntegerInput(form.lifetimeBudget, `${spec.name || spec.id} lifetime budget`),
        bidAmount: parseIntegerInput(form.bidAmount, `${spec.name || spec.id} bid amount`),
        startTime: fromLocalDateTimeValue(form.startTime),
        endTime: fromLocalDateTimeValue(form.endTime),
        promotedObject: parseJsonObjectInput(form.promotedObjectJson, `${spec.name || spec.id} promoted object`),
        conversionDomain: form.conversionDomain.trim() || null,
      };
      await updateAdSetSpec(spec.id, payload);
    }
  }, [includedAdSetSpecs, publishAdSetForms, updateAdSetSpec]);

  const refreshPublishRuns = useCallback(async () => {
    setPublishRunsLoading(true);
    setPublishRunsError(null);
    try {
      const data = await listPublishRuns(campaign.id);
      setPublishRuns(data);
    } catch (err) {
      setPublishRunsError(getErrorMessage(err));
    } finally {
      setPublishRunsLoading(false);
    }
  }, [campaign.id, listPublishRuns]);

  const handleValidatePublishPlan = useCallback(async () => {
    setPublishFormError(null);
    setPublishValidation(null);
    setPublishValidationPending(true);
    try {
      await persistPublishAdSetConfigs();
      await refreshPipeline();
      const validation = await validatePublishPlan(campaign.id, buildPublishRequestPayload());
      setPublishValidation(validation);
      await refreshPublishRuns();
    } catch (err) {
      setPublishFormError(getErrorMessage(err));
      const apiError = err as ApiError;
      const validation = readRecord((apiError.raw as { detail?: unknown } | undefined)?.detail)?.validation;
      const validationRecord = readRecord(validation);
      if (validationRecord) {
        setPublishValidation(validationRecord as unknown as MetaPublishPlanValidation);
      }
    } finally {
      setPublishValidationPending(false);
    }
  }, [
    buildPublishRequestPayload,
    campaign.id,
    persistPublishAdSetConfigs,
    refreshPipeline,
    refreshPublishRuns,
    validatePublishPlan,
  ]);

  const handlePublishToMeta = useCallback(async () => {
    setPublishFormError(null);
    setPublishPending(true);
    try {
      await persistPublishAdSetConfigs();
      await refreshPipeline();
      const run = await createPublishRun(campaign.id, buildPublishRequestPayload());
      setPublishValidation((run.metadata.validation as MetaPublishPlanValidation | undefined) || null);
      await refreshPublishRuns();
    } catch (err) {
      setPublishFormError(getErrorMessage(err));
      const apiError = err as ApiError;
      const validation = readRecord((apiError.raw as { detail?: unknown } | undefined)?.detail)?.validation;
      const validationRecord = readRecord(validation);
      if (validationRecord) {
        setPublishValidation(validationRecord as unknown as MetaPublishPlanValidation);
      }
      await refreshPublishRuns();
    } finally {
      setPublishPending(false);
    }
  }, [
    buildPublishRequestPayload,
    campaign.id,
    createPublishRun,
    persistPublishAdSetConfigs,
    refreshPipeline,
    refreshPublishRuns,
  ]);

  return (
    <div className="space-y-4">
      <div className="border border-border bg-transparent p-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-base font-semibold text-content">Meta ads review</div>
            <div className="text-sm text-content-muted">
              Review internal Meta specs, exclude unwanted creatives, validate the final package, and publish paused to Meta.
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-content-muted">
            {config ? (
              <>
                <Badge tone="neutral">Ad account {shortId(config.adAccountId, 4)}</Badge>
                {config.pageId ? <Badge tone="neutral">Page {shortId(config.pageId, 4)}</Badge> : null}
                {config.graphApiVersion ? <Badge tone="neutral">{config.graphApiVersion}</Badge> : null}
              </>
            ) : configError ? (
              <span className="text-danger">{configError}</span>
            ) : (
              <span>Loading Meta config…</span>
            )}
          </div>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-4 xl:grid-cols-7">
          <div className="rounded-lg border border-border bg-surface px-3 py-2">
            <div className="text-xs uppercase tracking-wide text-content-muted">Briefs</div>
            <div className="mt-1 text-lg font-semibold text-content">{assetBriefIds.length}</div>
          </div>
          <div className="rounded-lg border border-border bg-surface px-3 py-2">
            <div className="text-xs uppercase tracking-wide text-content-muted">Generated assets</div>
            <div className="mt-1 text-lg font-semibold text-content">{pipeline.length}</div>
          </div>
          <div className="rounded-lg border border-border bg-surface px-3 py-2">
            <div className="text-xs uppercase tracking-wide text-content-muted">Creative specs</div>
            <div className="mt-1 text-lg font-semibold text-content">{creativeSpecCount}</div>
          </div>
          <div className="rounded-lg border border-border bg-surface px-3 py-2">
            <div className="text-xs uppercase tracking-wide text-content-muted">Ad set specs</div>
            <div className="mt-1 text-lg font-semibold text-content">{adsetSpecCount}</div>
          </div>
          <div className="rounded-lg border border-border bg-surface px-3 py-2">
            <div className="text-xs uppercase tracking-wide text-content-muted">Included</div>
            <div className="mt-1 text-lg font-semibold text-content">{includedPackageItems.length}</div>
          </div>
          <div className="rounded-lg border border-border bg-surface px-3 py-2">
            <div className="text-xs uppercase tracking-wide text-content-muted">Excluded</div>
            <div className="mt-1 text-lg font-semibold text-content">{excludedPackageCount}</div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button variant="primary" size="sm" onClick={handleGenerateAssets} disabled={generatePending || !assetBriefIds.length}>
            {generatePending ? "Starting…" : "Generate creatives"}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handlePrepareMetaReview}
            disabled={preparePending || !prepareAssetBriefIds.length || !hasGeneratedAssets || !canPrepareMetaReview}
          >
            {preparePending ? "Preparing…" : "Prepare Meta review"}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => void refreshPipeline()} disabled={pipelineLoading}>
            {pipelineLoading ? "Refreshing…" : "Refresh"}
          </Button>
          {generationSummaries.length > 1 ? (
            <Button variant="secondary" size="sm" onClick={() => setLatestGenerationOnly((current) => !current)}>
              {latestGenerationOnly ? "Show all generations" : "Show latest generation only"}
            </Button>
          ) : null}
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,280px)_minmax(0,1fr)]">
          <div className="space-y-1">
            <label className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Meta funnel scope</label>
            <Select
              value={activeFunnelId || ""}
              onValueChange={(value) => setSelectedFunnelId(readString(value))}
              options={
                funnelScopeOptions.length
                  ? [{ label: "Select funnel", value: "" }, ...funnelScopeOptions]
                  : [{ label: "No funnels in latest generation", value: "" }]
              }
              disabled={funnelScopeOptions.length <= 1}
            />
          </div>
          <div className="rounded-lg border border-border bg-surface px-3 py-2 text-sm text-content-muted">
            This Meta ads tab operates on one funnel at a time. Review prep, Meta QA, the final package, and publish all
            use the selected funnel scope.
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button
            variant={packageView === "review" ? "primary" : "secondary"}
            size="sm"
            onClick={() => setPackageView("review")}
          >
            Review candidates
          </Button>
          <Button
            variant={packageView === "final" ? "primary" : "secondary"}
            size="sm"
            onClick={() => {
              setLatestGenerationOnly(true);
              setPackageView("final");
            }}
          >
            Final Meta package ({includedPackageItems.length})
          </Button>
        </div>

        <div className="mt-2 space-y-1 text-sm text-content-muted">
          <div>Generate creatives runs the swipe-first remix flow and Stage 1 Gemini swipe copy generation for the current briefs.</div>
          <div>Prepare Meta review creates internal Meta creative specs from the selected funnel's stored swipe copy packs.</div>
          <div>Meta publish package scope is generation-scoped and funnel-scoped. Everything in the latest generation for the selected funnel is included by default unless excluded.</div>
          {lastWorkflowRunId ? <div>Latest creative workflow: <span className="font-mono">{lastWorkflowRunId}</span></div> : null}
          {lastPreparedAt ? <div>Latest Meta review prep: {formatDate(lastPreparedAt)}</div> : null}
          {autoRefreshUntil ? <div>Auto-refreshing this panel while creative generation completes.</div> : null}
          {!hasGeneratedAssets ? <div>Generate creatives first. Meta review stays disabled until campaign assets exist.</div> : null}
          {latestGenerationSummary ? <div>Visible generation focus: <span className="font-mono">{latestGenerationSummary.label}</span></div> : null}
          {activeFunnelLabel ? <div>Funnel scope: <span className="font-mono">{activeFunnelLabel}</span></div> : null}
          {hiddenLegacyCount ? <div>{hiddenLegacyCount} older or non-selected assets are currently hidden.</div> : null}
          {hiddenOtherFunnelCount ? <div>{hiddenOtherFunnelCount} assets from other funnels are hidden by the current Meta funnel scope.</div> : null}
          {latestGenerationFunnelIds.length > 1 && !activeFunnelId ? (
            <div className="text-warning">Pick one funnel to review the latest generation. Mixed-funnel Meta review is blocked.</div>
          ) : null}
          {latestGenerationUnmappedCount ? (
            <div className="text-warning">
              {latestGenerationUnmappedCount} latest-generation assets are missing an explicit asset brief funnel mapping.
            </div>
          ) : null}
          {!canManagePublishPackage ? (
            <div className="text-warning">Switch back to latest generation only and pick one funnel to manage the final Meta package.</div>
          ) : null}
          {funnelScopeOptions.length > 1 && !canPrepareMetaReview ? (
            <div className="text-warning">Prepare Meta review is disabled until one funnel is selected for the latest generation.</div>
          ) : null}
          {funnelScopeOptions.length <= 1 && funnelsQuery.isLoading ? <div>Loading funnel scope…</div> : null}
          {funnelsQuery.error ? <div className="text-danger">{getErrorMessage(funnelsQuery.error)}</div> : null}
          {selectionLoading ? <div>Loading saved Meta package exclusions…</div> : null}
          {visibleMissingCreativeSpecCount ? (
            <div className="text-warning">{visibleMissingCreativeSpecCount} visible generated assets still need internal Meta specs.</div>
          ) : null}
          {generateError ? <div className="text-danger">{generateError}</div> : null}
          {prepareError ? <div className="text-danger">{prepareError}</div> : null}
          {prepareIssues.length ? (
            <div className="space-y-2 rounded-lg border border-danger/30 bg-danger/5 px-3 py-3 text-sm text-danger">
              <div className="font-semibold">Meta review prep blocked for {prepareIssues.length} asset(s).</div>
              {prepareIssues.map((issue) => (
                <div key={`prepare-issue-${issue.assetId}`} className="rounded-md border border-danger/20 bg-background px-3 py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-content-muted">{shortId(issue.assetId, 5)}</span>
                    {issue.generationKey ? <Badge tone="neutral">{issue.generationKey}</Badge> : null}
                    {issue.assetBriefId ? <Badge tone="neutral">{issue.assetBriefId}</Badge> : null}
                    {issue.funnelId ? <Badge tone="neutral">{formatFunnelLabel(funnelById.get(issue.funnelId) || null, issue.funnelId)}</Badge> : null}
                  </div>
                  {issue.destinationPage ? (
                    <div className="mt-2 text-xs text-content-muted">
                      Destination page: {issue.destinationPage}
                      {issue.normalizedDestinationPage && issue.normalizedDestinationPage !== issue.destinationPage
                        ? ` -> ${issue.normalizedDestinationPage}`
                        : ""}
                    </div>
                  ) : null}
                  <div className="mt-2 space-y-1">
                    {issue.issues.map((assetIssue, index) => (
                      <div key={`prepare-issue-${issue.assetId}-${assetIssue.ruleId || index}`}>
                        {assetIssue.ruleId ? `${assetIssue.ruleId}: ` : ""}
                        {assetIssue.message || assetIssue.title || "Meta review prep issue"}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          {selectionError ? <div className="text-danger">{selectionError}</div> : null}
          {pipelineError ? <div className="text-danger">{pipelineError}</div> : null}
        </div>
      </div>

      <CampaignPaidAdsQaCard
        campaign={campaign}
        generationKey={latestGenerationKey}
        generationLabel={latestGenerationSummary?.label ?? null}
        funnelId={activeFunnelId}
        funnelLabel={activeFunnelLabel}
        enabled={canPrepareMetaReview}
        reviewBaseUrl={reviewBaseUrl}
      />

      {packageView === "final" ? (
        <div className="border border-border bg-transparent">
          <div className="border-b border-border px-4 py-3">
            <div className="text-base font-semibold text-content">Final Meta package</div>
            <div className="text-sm text-content-muted">
              Everything in the latest generation for the selected funnel is included by default. Excluded creatives are hidden here.
            </div>
          </div>

          {selectionLoading ? (
            <div className="px-4 py-3 text-sm text-content-muted">Loading final Meta package…</div>
          ) : !latestGenerationKey ? (
            <div className="px-4 py-3 text-sm text-content-muted">No latest generation is available yet.</div>
          ) : !activeFunnelId ? (
            <div className="px-4 py-3 text-sm text-content-muted">
              Pick one funnel above to see the final Meta package for this generation.
            </div>
          ) : !includedPackageItems.length ? (
            <div className="space-y-2 px-4 py-3 text-sm text-content-muted">
              <div>All latest-generation creatives are currently excluded from the final Meta package.</div>
              <div>Return to Review candidates and restore the creatives you want to send to Meta.</div>
            </div>
          ) : (
            <div className="space-y-4 px-4 py-4">
              {includedPackageItems.map((item) => {
                const assetUrl = resolveAssetUrl(item.asset.public_url);
                const creativeMetadata = (item.creative_spec?.metadata_json || {}) as Record<string, unknown>;
                const creativeSpecSource = readString(creativeMetadata.source);
                const reviewPaths = (creativeMetadata.reviewPaths || {}) as Record<string, string>;
                const preSalesUrl = resolveShopHostedUrl(reviewPaths["pre-sales"], reviewBaseUrl);
                const salesUrl = resolveShopHostedUrl(reviewPaths["sales"], reviewBaseUrl);
                const metaUploadPrimaryText = readString(item.creative_spec?.primary_text);
                const metaUploadHeadline = readString(item.creative_spec?.headline);
                const metaUploadDescription = readString(item.creative_spec?.description);
                const metaUploadCta = readString(item.creative_spec?.call_to_action_type);
                const metaDestinationUrl = readString(item.creative_spec?.destination_url);
                const resolvedMetaDestinationUrl =
                  resolveShopHostedUrl(metaDestinationUrl, reviewBaseUrl) || metaDestinationUrl;
                const generationGroup = getGenerationGroup(item);
                const pendingSelection = selectionPendingAssetIds.includes(item.asset.id);
                const metaSpecPreparedFromSwipeCopy = creativeSpecSource === "campaign_meta_review_setup_swipe_copy";
                const hasReadySpec = Boolean(item.creative_spec?.id);

                return (
                  <div key={`final-package-${item.asset.id}`} className="space-y-4 rounded-xl border border-border bg-surface p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="space-y-2">
                        <div className="text-sm font-semibold text-content">{item.creative_spec?.name || item.asset.public_id}</div>
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge tone="success">Included in final package</Badge>
                          {hasReadySpec ? <Badge tone="success">Meta spec ready</Badge> : <Badge tone="danger">Meta spec missing</Badge>}
                          {metaSpecPreparedFromSwipeCopy ? <Badge tone="success">Prepared from swipe copy</Badge> : null}
                          <Badge tone="neutral">{generationGroup.label}</Badge>
                          {activeFunnelLabel ? <Badge tone="neutral">{activeFunnelLabel}</Badge> : null}
                          {item.experiment?.name ? <Badge tone="neutral">{item.experiment.name}</Badge> : null}
                        </div>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        <Button
                          variant="destructive"
                          size="xs"
                          onClick={() => void handleSetPublishDecision(item.asset.id, "excluded")}
                          disabled={pendingSelection}
                        >
                          {pendingSelection ? "Saving…" : "Exclude from package"}
                        </Button>
                        {preSalesUrl ? (
                          <a href={preSalesUrl} target="_blank" rel="noreferrer">
                            <Button variant="secondary" size="xs">Open pre-sales</Button>
                          </a>
                        ) : null}
                        {salesUrl ? (
                          <a href={salesUrl} target="_blank" rel="noreferrer">
                            <Button variant="secondary" size="xs">Open sales</Button>
                          </a>
                        ) : null}
                      </div>
                    </div>

                    <div className="grid gap-4 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1fr)_minmax(0,1.1fr)]">
                      <div className="rounded-xl border border-border bg-surface p-3">
                        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-muted">Final Creative Asset</div>
                        <div className="mt-3 overflow-hidden rounded-lg border border-border bg-surface-2">
                          {assetUrl ? (
                            <img
                              src={assetUrl}
                              alt={item.asset.asset_kind || "Creative asset"}
                              className="h-[320px] w-full object-contain"
                              loading="lazy"
                            />
                          ) : (
                            <div className="flex h-[320px] items-center justify-center px-4 text-sm text-content-muted">
                              Generated remix preview missing.
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="rounded-xl border border-border bg-surface p-3">
                        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-muted">Exact Meta Upload Payload</div>
                        {hasReadySpec ? (
                          <div className="mt-3 space-y-3">
                            <CopyField label="Primary Text" value={metaUploadPrimaryText} multiline />
                            <CopyField label="Headline" value={metaUploadHeadline} />
                            <CopyField label="Description" value={metaUploadDescription} />
                            <div className="grid gap-3 sm:grid-cols-2">
                              <CopyField label="CTA Button" value={metaUploadCta} />
                              <CopyField label="Destination URL" value={resolvedMetaDestinationUrl} />
                            </div>
                            <div className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-content-muted">
                              {item.adset_specs?.length
                                ? `Linked ad set specs: ${item.adset_specs.map((spec) => spec.name || spec.id).join(", ")}`
                                : "No linked internal Meta ad set spec yet."}
                            </div>
                          </div>
                        ) : (
                          <div className="mt-3 rounded-lg border border-dashed border-border bg-surface-2 px-4 py-4 text-sm leading-6 text-content-muted">
                            This creative is in the final package, but the upload-ready Meta spec is still missing.
                          </div>
                        )}
                      </div>

                      <MetaFeedPreview
                        assetUrl={assetUrl}
                        assetAlt={item.asset.asset_kind || "Creative asset"}
                        primaryText={metaUploadPrimaryText}
                        headline={metaUploadHeadline}
                        description={metaUploadDescription}
                        cta={metaUploadCta}
                        destinationUrl={resolvedMetaDestinationUrl}
                        specReady={hasReadySpec}
                        specSourceLabel={hasReadySpec ? "Final Meta package" : "Spec missing"}
                      />
                    </div>
                  </div>
                );
              })}

              <div className="rounded-xl border border-border bg-surface p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-base font-semibold text-content">Publish setup</div>
                    <div className="text-sm text-content-muted">
                      Save the campaign and ad set inputs below, validate the final package, then publish paused to Meta.
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="secondary" size="sm" onClick={() => void handleValidatePublishPlan()} disabled={publishValidationPending || publishPending}>
                      {publishValidationPending ? "Validating…" : "Validate publish plan"}
                    </Button>
                    <Button variant="primary" size="sm" onClick={() => void handlePublishToMeta()} disabled={publishPending || publishValidationPending}>
                      {publishPending ? "Publishing…" : "Publish paused to Meta"}
                    </Button>
                  </div>
                </div>

                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  <div className="space-y-3">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-muted">Campaign Config</div>
                    <div className="space-y-3 rounded-xl border border-border bg-surface-2 p-3">
                      <label className="block space-y-1">
                        <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Publish Base URL</div>
                        <Input
                          value={publishCampaignForm.publishBaseUrl}
                          onChange={(event) => updatePublishCampaignField("publishBaseUrl", event.target.value)}
                          placeholder="https://shop.thehonestherbalist.com"
                        />
                      </label>
                      <label className="block space-y-1">
                        <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Meta Campaign Name</div>
                        <Input
                          value={publishCampaignForm.campaignName}
                          onChange={(event) => updatePublishCampaignField("campaignName", event.target.value)}
                          placeholder="Honest Herbalist Launch"
                        />
                      </label>
                      <label className="block space-y-1">
                        <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Campaign Objective</div>
                        <Input
                          value={publishCampaignForm.campaignObjective}
                          onChange={(event) => updatePublishCampaignField("campaignObjective", event.target.value)}
                          placeholder="OUTCOME_SALES"
                        />
                      </label>
                      <label className="block space-y-1">
                        <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Buying Type</div>
                        <Input
                          value={publishCampaignForm.buyingType}
                          onChange={(event) => updatePublishCampaignField("buyingType", event.target.value)}
                          placeholder="Optional"
                        />
                      </label>
                      <label className="block space-y-1">
                        <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Special Ad Categories</div>
                        <Input
                          value={publishCampaignForm.specialAdCategories}
                          onChange={(event) => updatePublishCampaignField("specialAdCategories", event.target.value)}
                          placeholder="Comma-separated, or leave blank"
                        />
                      </label>
                      <div className="rounded-md border border-border bg-background px-3 py-2 text-xs text-content-muted">
                        This publish path creates the Meta campaign, ad sets, and ads in <span className="font-semibold text-content">PAUSED</span> status.
                      </div>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-muted">Ad Set Specs</div>
                    {includedAdSetSpecs.length ? (
                      <div className="space-y-3">
                        {includedAdSetSpecs.map((spec) => {
                          const form = publishAdSetForms[spec.id] || buildAdSetForm(spec);
                          return (
                            <div key={`publish-adset-${spec.id}`} className="space-y-3 rounded-xl border border-border bg-surface-2 p-3">
                              <div className="flex flex-wrap items-center gap-2">
                                <div className="text-sm font-semibold text-content">{spec.name || spec.id}</div>
                                <Badge tone="neutral">{shortId(spec.id, 5)}</Badge>
                              </div>
                              <div className="grid gap-3 md:grid-cols-2">
                                <label className="block space-y-1">
                                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Name</div>
                                  <Input value={form.name} onChange={(event) => updatePublishAdSetField(spec.id, "name", event.target.value)} />
                                </label>
                                <label className="block space-y-1">
                                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Optimization Goal</div>
                                  <Input
                                    value={form.optimizationGoal}
                                    onChange={(event) => updatePublishAdSetField(spec.id, "optimizationGoal", event.target.value)}
                                    placeholder="OFFSITE_CONVERSIONS"
                                  />
                                </label>
                                <label className="block space-y-1">
                                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Billing Event</div>
                                  <Input
                                    value={form.billingEvent}
                                    onChange={(event) => updatePublishAdSetField(spec.id, "billingEvent", event.target.value)}
                                    placeholder="IMPRESSIONS"
                                  />
                                </label>
                                <label className="block space-y-1">
                                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Conversion Domain</div>
                                  <Input
                                    value={form.conversionDomain}
                                    onChange={(event) => updatePublishAdSetField(spec.id, "conversionDomain", event.target.value)}
                                    placeholder="Optional"
                                  />
                                </label>
                                <label className="block space-y-1">
                                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Daily Budget</div>
                                  <Input
                                    value={form.dailyBudget}
                                    onChange={(event) => updatePublishAdSetField(spec.id, "dailyBudget", event.target.value)}
                                    placeholder="Leave blank to use lifetime budget"
                                  />
                                </label>
                                <label className="block space-y-1">
                                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Lifetime Budget</div>
                                  <Input
                                    value={form.lifetimeBudget}
                                    onChange={(event) => updatePublishAdSetField(spec.id, "lifetimeBudget", event.target.value)}
                                    placeholder="Leave blank to use daily budget"
                                  />
                                </label>
                                <label className="block space-y-1">
                                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Bid Amount</div>
                                  <Input
                                    value={form.bidAmount}
                                    onChange={(event) => updatePublishAdSetField(spec.id, "bidAmount", event.target.value)}
                                    placeholder="Optional"
                                  />
                                </label>
                                <label className="block space-y-1">
                                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Start Time</div>
                                  <Input
                                    type="datetime-local"
                                    value={form.startTime}
                                    onChange={(event) => updatePublishAdSetField(spec.id, "startTime", event.target.value)}
                                  />
                                </label>
                                <label className="block space-y-1">
                                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">End Time</div>
                                  <Input
                                    type="datetime-local"
                                    value={form.endTime}
                                    onChange={(event) => updatePublishAdSetField(spec.id, "endTime", event.target.value)}
                                  />
                                </label>
                              </div>
                              <label className="block space-y-1">
                                <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Targeting JSON</div>
                                <Textarea
                                  value={form.targetingJson}
                                  onChange={(event) => updatePublishAdSetField(spec.id, "targetingJson", event.target.value)}
                                  placeholder='{"geo_locations":{"countries":["US"]}}'
                                />
                              </label>
                              <div className="grid gap-3 md:grid-cols-2">
                                <label className="block space-y-1">
                                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Placements JSON</div>
                                  <Textarea
                                    value={form.placementsJson}
                                    onChange={(event) => updatePublishAdSetField(spec.id, "placementsJson", event.target.value)}
                                    placeholder="Optional"
                                  />
                                </label>
                                <label className="block space-y-1">
                                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Promoted Object JSON</div>
                                  <Textarea
                                    value={form.promotedObjectJson}
                                    onChange={(event) => updatePublishAdSetField(spec.id, "promotedObjectJson", event.target.value)}
                                    placeholder='{"pixel_id":"...","custom_event_type":"PURCHASE"}'
                                  />
                                </label>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="rounded-xl border border-dashed border-border bg-surface-2 px-4 py-4 text-sm text-content-muted">
                        Included creatives do not have linked Meta ad set specs yet.
                      </div>
                    )}
                  </div>
                </div>

                {publishFormError ? <div className="mt-4 text-sm text-danger">{publishFormError}</div> : null}

                {publishValidation ? (
                  <div className="mt-4 space-y-3 rounded-xl border border-border bg-surface-2 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="text-sm font-semibold text-content">Publish validation</div>
                      <Badge tone={publishValidation.ok ? "success" : "danger"}>
                        {publishValidation.ok ? "Ready to publish" : "Blocked"}
                      </Badge>
                      {publishValidation.publishDomain ? <Badge tone="neutral">{publishValidation.publishDomain}</Badge> : null}
                    </div>
                    {publishValidation.blockers.length ? (
                      <div className="space-y-1 text-sm text-danger">
                        {publishValidation.blockers.map((blocker) => (
                          <div key={blocker}>{blocker}</div>
                        ))}
                      </div>
                    ) : null}
                    <div className="space-y-2">
                      {publishValidation.items.map((validationItem) => (
                        <div key={`publish-validation-${validationItem.assetId}`} className="rounded-md border border-border bg-background px-3 py-2 text-sm">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-mono text-xs text-content-muted">{shortId(validationItem.assetId, 5)}</span>
                            <Badge tone={validationItem.status === "ok" ? "success" : "danger"}>
                              {validationItem.status === "ok" ? "OK" : "Blocked"}
                            </Badge>
                            {validationItem.resolvedDestinationUrl ? (
                              <span className="truncate text-content-muted">{validationItem.resolvedDestinationUrl}</span>
                            ) : null}
                          </div>
                          {validationItem.blockers.length ? (
                            <div className="mt-2 space-y-1 text-danger">
                              {validationItem.blockers.map((blocker) => (
                                <div key={`${validationItem.assetId}-${blocker}`}>{blocker}</div>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>

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
                    {visiblePublishRuns.map((run) => (
                      <div key={`publish-run-${run.id}`} className="rounded-xl border border-border bg-surface-2 p-3">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div className="space-y-1">
                            <div className="text-sm font-semibold text-content">{run.campaignName}</div>
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge tone={run.status === "published" ? "success" : run.status === "failed" ? "danger" : "accent"}>
                                {run.status}
                              </Badge>
                              <Badge tone="neutral">{run.generationKey}</Badge>
                              {run.metaCampaignId ? <Badge tone="neutral">Meta {shortId(run.metaCampaignId, 5)}</Badge> : null}
                            </div>
                          </div>
                          <div className="text-xs text-content-muted">{formatDate(run.createdAt)}</div>
                        </div>
                        {run.errorMessage ? <div className="mt-2 text-sm text-danger">{run.errorMessage}</div> : null}
                        <div className="mt-3 space-y-2">
                          {run.items.map((runItem) => (
                            <div key={`publish-run-item-${runItem.id}`} className="rounded-md border border-border bg-background px-3 py-2 text-sm">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="font-mono text-xs text-content-muted">{shortId(runItem.assetId, 5)}</span>
                                <Badge tone={runItem.status === "published" ? "success" : runItem.status === "failed" ? "danger" : "accent"}>
                                  {runItem.status}
                                </Badge>
                                {runItem.metaAdId ? <span className="text-content-muted">Ad {shortId(runItem.metaAdId, 5)}</span> : null}
                                {runItem.metaCreativeId ? (
                                  <span className="text-content-muted">Creative {shortId(runItem.metaCreativeId, 5)}</span>
                                ) : null}
                                {runItem.metaAdSetId ? <span className="text-content-muted">Ad set {shortId(runItem.metaAdSetId, 5)}</span> : null}
                              </div>
                              {runItem.errorMessage ? <div className="mt-2 text-danger">{runItem.errorMessage}</div> : null}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      ) : null}

      {packageView === "review" ? (
        <div className="border border-border bg-transparent">
          <div className="border-b border-border px-4 py-3">
            <div className="text-base font-semibold text-content">Draft Meta-ready creatives</div>
            <div className="text-sm text-content-muted">
              Campaign assets, internal Meta creative specs, ad set specs, and funnel review links for the selected funnel.
            </div>
          </div>

          {pipelineLoading ? (
            <div className="px-4 py-3 text-sm text-content-muted">Loading Meta campaign assets…</div>
          ) : latestGenerationFunnelIds.length > 1 && !activeFunnelId ? (
            <div className="px-4 py-3 text-sm text-content-muted">
              Pick one funnel above before reviewing Meta-ready creatives for this generation.
            </div>
          ) : !visiblePipeline.length ? (
            <div className="px-4 py-3 text-sm text-content-muted">
              No campaign creative assets found yet. Generate creatives first.
            </div>
          ) : (
            <div className="divide-y divide-border">
              {groupedPipeline.map((group) => (
                <div key={`requirement-${group.requirementIndex}`} className="space-y-4 px-4 py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="text-sm font-semibold text-content">
                      Requirement {group.requirementIndex >= 0 ? group.requirementIndex + 1 : "—"}: {group.title}
                    </div>
                    {group.funnelStage ? <Badge tone="neutral">{group.funnelStage}</Badge> : null}
                    <Badge tone="neutral">{group.items.length} swipe remixes</Badge>
                  </div>

                  <div className="space-y-4">
                    {group.items.map((item) => {
                    const assetUrl = resolveAssetUrl(item.asset.public_url);
                    const creativeMetadata = (item.creative_spec?.metadata_json || {}) as Record<string, unknown>;
                    const creativeSpecSource = readString(creativeMetadata.source);
                    const reviewPaths = (creativeMetadata.reviewPaths || {}) as Record<string, string>;
                    const preSalesUrl = resolveShopHostedUrl(reviewPaths["pre-sales"], reviewBaseUrl);
                    const salesUrl = resolveShopHostedUrl(reviewPaths["sales"], reviewBaseUrl);
                    const swipeCopyInputs = readRecord(item.asset.ai_metadata?.swipeCopyInputs);
                    const swipeAdMedia = readRecord(swipeCopyInputs?.adImageOrVideo);
                    const sourceUrl = resolveAssetUrl(
                      readString(swipeAdMedia?.sourceUrl) || readString(item.asset.ai_metadata?.swipeSourceUrl),
                    );
                    const sourceLabel =
                      readString(swipeAdMedia?.sourceLabel) || readString(item.asset.ai_metadata?.swipeSourceLabel) || "Source swipe";
                    const sourceMediaType = readString(swipeAdMedia?.assetType);
                    const angleUsed = readString(swipeCopyInputs?.angleUsed);
                    const destinationPage = readString(swipeCopyInputs?.destinationPage);
                    const batchId = readString(item.asset.ai_metadata?.creativeGenerationBatchId);
                    const generationGroup = getGenerationGroup(item);
                    const swipeCopyPack = readRecord(item.asset.ai_metadata?.swipeCopyPack);
                    const metaUploadPrimaryText = readString(item.creative_spec?.primary_text);
                    const metaUploadHeadline = readString(item.creative_spec?.headline);
                    const metaUploadDescription = readString(item.creative_spec?.description);
                    const metaUploadCta = readString(item.creative_spec?.call_to_action_type);
                    const metaDestinationUrl = readString(item.creative_spec?.destination_url);
                    const swipeCandidatePrimaryText = readString(swipeCopyPack?.metaPrimaryText);
                    const swipeCandidateHeadline = readString(swipeCopyPack?.metaHeadline);
                    const swipeCandidateDescription = readString(swipeCopyPack?.metaDescription);
                    const swipeCandidateCta = readString(swipeCopyPack?.metaCta);
                    const previewMarkdown = readString(swipeCopyPack?.formattedVariationsMarkdown);
                    const previewVariation = readString(swipeCopyPack?.selectedVariation);
                    const resolvedMetaDestinationUrl =
                      resolveShopHostedUrl(metaDestinationUrl, reviewBaseUrl) || metaDestinationUrl;
                    const metaSpecPreparedFromSwipeCopy = creativeSpecSource === "campaign_meta_review_setup_swipe_copy";
                    const hasLegacyMetaSpec = Boolean(item.creative_spec?.id) && !metaSpecPreparedFromSwipeCopy;
                    const metaPreviewStatusLabel = item.creative_spec?.id
                      ? metaSpecPreparedFromSwipeCopy
                        ? "Prepared Meta spec"
                        : "Legacy Meta spec"
                      : "Spec missing";
                    const currentSelectionDecision = selectionByAssetId.get(item.asset.id)?.decision;
                    const isExcluded = currentSelectionDecision === "excluded";
                    const pendingSelection = selectionPendingAssetIds.includes(item.asset.id);
                    const publishDecision = isExcluded ? "excluded" : null;
                    const selectionDisabled = !canManagePublishPackage || pendingSelection;
                      return (
                        <div key={item.asset.id} className="space-y-4 rounded-xl border border-border bg-surface p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="space-y-2">
                            <div className="text-sm font-semibold text-content">{item.creative_spec?.name || item.asset.public_id}</div>
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge tone="neutral">Req {readNumber(item.asset.ai_metadata?.requirementIndex) ?? "—"}</Badge>
                              {previewVariation ? <Badge tone="neutral">{previewVariation}</Badge> : null}
                              <Badge tone={item.creative_spec?.id ? "success" : "accent"}>
                                {item.creative_spec?.id ? "Meta spec ready" : "Meta spec missing"}
                              </Badge>
                              {metaSpecPreparedFromSwipeCopy ? <Badge tone="success">Prepared from swipe copy</Badge> : null}
                              {hasLegacyMetaSpec ? <Badge tone="danger">Legacy Meta spec</Badge> : null}
                              {!item.creative_spec?.id && swipeCopyPack ? <Badge tone="accent">Swipe copy ready</Badge> : null}
                              <Badge tone="neutral">{item.asset.status || "draft"}</Badge>
                              <Badge tone="neutral">{generationGroup.label}</Badge>
                              {activeFunnelLabel ? <Badge tone="neutral">{activeFunnelLabel}</Badge> : null}
                              {batchId ? <Badge tone="neutral">Batch {shortId(batchId, 5)}</Badge> : null}
                              <Badge tone={publishDecisionTone(publishDecision)}>
                                {publishDecisionLabel(publishDecision)}
                              </Badge>
                            </div>
                          </div>

                          <div className="flex flex-wrap gap-2">
                            <Button
                              variant={isExcluded ? "secondary" : "destructive"}
                              size="xs"
                              onClick={() => void handleSetPublishDecision(item.asset.id, isExcluded ? null : "excluded")}
                              disabled={selectionDisabled}
                            >
                              {pendingSelection ? "Saving…" : isExcluded ? "Restore to package" : "Exclude from Meta"}
                            </Button>
                            {preSalesUrl ? (
                              <a href={preSalesUrl} target="_blank" rel="noreferrer">
                                <Button variant="secondary" size="xs">Open pre-sales</Button>
                              </a>
                            ) : null}
                            {salesUrl ? (
                              <a href={salesUrl} target="_blank" rel="noreferrer">
                                <Button variant="secondary" size="xs">Open sales</Button>
                              </a>
                            ) : null}
                          </div>
                        </div>

                        <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-[minmax(0,0.82fr)_minmax(0,0.82fr)_minmax(0,1fr)_minmax(0,1.1fr)]">
                          <div className="rounded-xl border border-border bg-surface p-3">
                            <div className="flex items-start justify-between gap-2">
                              <div>
                                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-muted">1 Source Swipe</div>
                                <div className="text-xs text-content-muted">Original swipe selected as the visual reference.</div>
                              </div>
                              {sourceMediaType ? <Badge tone="neutral">{sourceMediaType}</Badge> : null}
                            </div>
                            <div className="mt-3 overflow-hidden rounded-lg border border-border bg-surface-2">
                              {sourceUrl ? (
                                <img src={sourceUrl} alt={sourceLabel} className="h-[260px] w-full object-contain" loading="lazy" />
                              ) : (
                                <div className="flex h-[260px] items-center justify-center px-4 text-sm text-content-muted">
                                  Source swipe preview missing.
                                </div>
                              )}
                            </div>
                          </div>

                          <div className="rounded-xl border border-border bg-surface p-3">
                            <div className="flex items-start justify-between gap-2">
                              <div>
                                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-muted">2 Generated Remix</div>
                                <div className="text-xs text-content-muted">Rendered creative asset that pairs with the chosen copy.</div>
                              </div>
                              <Badge tone="neutral">{item.asset.asset_kind || "asset"}</Badge>
                            </div>
                            <div className="mt-3 overflow-hidden rounded-lg border border-border bg-surface-2">
                              {assetUrl ? (
                                <img
                                  src={assetUrl}
                                  alt={item.asset.asset_kind || "Creative asset"}
                                  className="h-[260px] w-full object-contain"
                                  loading="lazy"
                                />
                              ) : (
                                <div className="flex h-[260px] items-center justify-center px-4 text-sm text-content-muted">
                                  Generated remix preview missing.
                                </div>
                              )}
                            </div>
                            <div className="mt-3 flex flex-wrap items-center gap-2">
                              {item.creative_spec?.id ? <Badge tone="success">Ready for Meta review</Badge> : null}
                              {!item.creative_spec?.id ? <Badge tone="accent">Waiting for Meta prep</Badge> : null}
                              {metaSpecPreparedFromSwipeCopy ? <Badge tone="success">Copy linked</Badge> : null}
                              {hasLegacyMetaSpec ? <Badge tone="danger">Legacy copy source</Badge> : null}
                            </div>
                            {!item.creative_spec?.id ? (
                              <div className="mt-2 text-xs text-content-muted">
                                Prepare Meta review before this creative can be published to Meta.
                              </div>
                            ) : null}
                          </div>

                          <div className="rounded-xl border border-border bg-surface p-3">
                            <div className="flex items-start justify-between gap-2">
                              <div>
                                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-muted">3 Meta Upload Copy</div>
                                <div className="text-xs text-content-muted">This is the exact copy that would go into Meta for this ad.</div>
                              </div>
                              <Badge tone={item.creative_spec?.id ? "success" : "accent"}>{metaPreviewStatusLabel}</Badge>
                            </div>

                            {item.creative_spec?.id ? (
                              <div className="mt-3 space-y-3">
                                <CopyField label="Primary Text" value={metaUploadPrimaryText} multiline />
                                <CopyField label="Headline" value={metaUploadHeadline} />
                                <CopyField label="Description" value={metaUploadDescription} />
                                <div className="grid gap-3 sm:grid-cols-2">
                                  <CopyField label="CTA Button" value={metaUploadCta} />
                                  <CopyField label="Destination URL" value={resolvedMetaDestinationUrl} />
                                </div>
                              </div>
                            ) : (
                              <div className="mt-3 rounded-lg border border-dashed border-border bg-surface-2 px-4 py-4 text-sm leading-6 text-content-muted">
                                No upload-ready Meta creative spec exists yet.
                                {swipeCopyPack ? " Stage 1 swipe copy is available below, but it is not the current upload source." : ""}
                              </div>
                            )}
                          </div>

                          <MetaFeedPreview
                            assetUrl={assetUrl}
                            assetAlt={item.asset.asset_kind || "Creative asset"}
                            primaryText={metaUploadPrimaryText}
                            headline={metaUploadHeadline}
                            description={metaUploadDescription}
                            cta={metaUploadCta}
                            destinationUrl={resolvedMetaDestinationUrl}
                            specReady={Boolean(item.creative_spec?.id)}
                            specSourceLabel={metaSpecPreparedFromSwipeCopy ? "Prepared from swipe copy" : metaPreviewStatusLabel}
                          />
                        </div>

                        <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-[minmax(0,0.82fr)_minmax(0,1.1fr)_minmax(0,0.82fr)]">
                          <div className="rounded-xl border border-border bg-surface p-3">
                            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-muted">Creative Lineage</div>
                            <div className="mt-3 space-y-2 text-sm text-content">
                              <div><span className="text-content-muted">Asset ID:</span> <span className="font-mono">{item.asset.id}</span></div>
                              <div><span className="text-content-muted">Created:</span> {formatDate(item.asset.created_at)}</div>
                              <div><span className="text-content-muted">Angle:</span> {item.experiment?.name || item.experiment?.id || "—"}</div>
                              {destinationPage ? <div><span className="text-content-muted">Destination:</span> {destinationPage}</div> : null}
                              {angleUsed ? <div><span className="text-content-muted">Stage 1 angle:</span> {angleUsed}</div> : null}
                            </div>
                          </div>

                          <div className="rounded-xl border border-border bg-surface p-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-muted">Swipe Stage 1 Copy Source</div>
                              {previewVariation ? <Badge tone="neutral">{previewVariation}</Badge> : null}
                              {metaSpecPreparedFromSwipeCopy ? <Badge tone="success">Selected for Meta</Badge> : <Badge tone="accent">Candidate only</Badge>}
                            </div>
                            {swipeCopyPack ? (
                              <div className="mt-3 space-y-3">
                                <div className="grid gap-3 lg:grid-cols-2">
                                  <CopyField label="Swipe Primary Text" value={swipeCandidatePrimaryText} multiline />
                                  <div className="space-y-3">
                                    <CopyField label="Swipe Headline" value={swipeCandidateHeadline} />
                                    <CopyField label="Swipe Description" value={swipeCandidateDescription} />
                                    <CopyField label="Swipe CTA" value={swipeCandidateCta} />
                                  </div>
                                </div>
                                {previewMarkdown ? (
                                  <details className="rounded-lg border border-border bg-surface-2 px-3 py-2">
                                    <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">
                                      View full Stage 1 pack
                                    </summary>
                                    <pre className="mt-3 max-h-[240px] overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-content">
                                      {previewMarkdown}
                                    </pre>
                                  </details>
                                ) : null}
                              </div>
                            ) : (
                              <div className="mt-3 text-sm text-content-muted">No Stage 1 swipe copy pack is stored on this asset.</div>
                            )}
                          </div>

                          <div className="rounded-xl border border-border bg-surface p-3">
                            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-muted">Meta Wiring</div>
                            <div className="mt-3 space-y-3">
                              <div>
                                <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Ad set specs</div>
                                {(item.adset_specs || []).length ? (
                                  <div className="mt-2 space-y-2">
                                    {(item.adset_specs || []).map((spec) => (
                                      <div key={spec.id} className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm">
                                        <div className="font-semibold text-content">{spec.name || spec.id}</div>
                                        <div className="text-content-muted">Status: {spec.status || "draft"}</div>
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <div className="mt-2 text-sm text-content-muted">No internal Meta ad set spec yet.</div>
                                )}
                              </div>

                              <div>
                                <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Funnel review</div>
                                <div className="mt-2 flex flex-wrap gap-2">
                                  {preSalesUrl ? (
                                    <a href={preSalesUrl} target="_blank" rel="noreferrer">
                                      <Button variant="secondary" size="xs">Open pre-sales</Button>
                                    </a>
                                  ) : null}
                                  {salesUrl ? (
                                    <a href={salesUrl} target="_blank" rel="noreferrer">
                                      <Button variant="secondary" size="xs">Open sales</Button>
                                    </a>
                                  ) : null}
                                  {!preSalesUrl && !salesUrl ? (
                                    <div className="text-sm text-content-muted">No funnel review links on this creative spec yet.</div>
                                  ) : null}
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
