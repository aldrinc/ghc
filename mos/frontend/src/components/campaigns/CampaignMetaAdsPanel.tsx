import { useCallback, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import { useMetaApi } from "@/api/meta";
import { CampaignPaidAdsQaCard } from "@/components/campaigns/CampaignPaidAdsQaCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { resolveRequiredApiBaseUrl } from "@/lib/apiBaseUrl";
import type { AssetBrief } from "@/types/artifacts";
import type { Campaign } from "@/types/common";
import type { MetaPipelineAsset } from "@/types/meta";

type CampaignMetaAdsPanelProps = {
  campaign: Campaign;
  assetBriefs: AssetBrief[];
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

function resolveReviewUrl(path?: string | null): string | null {
  if (!path || typeof window === "undefined" || !window.location?.origin) return null;
  return `${window.location.origin}${path}`;
}

function getErrorMessage(err: unknown) {
  if (typeof err === "string") return err;
  if (err && typeof err === "object" && "message" in err) return (err as ApiError).message || "Request failed";
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
    <div className="overflow-hidden rounded-[22px] border border-slate-200 bg-white text-slate-900 shadow-sm">
      <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">Meta Feed Preview</div>
            <div className="text-xs text-slate-500">Sample layout using the prepared creative spec</div>
          </div>
          <span
            className={[
              "inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold",
              specReady ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700",
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
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-200 text-sm font-semibold text-slate-700">
                B
              </div>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-slate-900">Brand Page</div>
                <div className="text-xs text-slate-500">Sponsored</div>
              </div>
            </div>
            <div className="whitespace-pre-wrap text-[13px] leading-5 text-slate-800">
              {primaryText || "Primary text missing from prepared spec."}
            </div>
          </div>

          <div className="border-y border-slate-200 bg-slate-50">
            {assetUrl ? (
              <img src={assetUrl} alt={assetAlt} className="h-[320px] w-full object-contain" loading="lazy" />
            ) : (
              <div className="flex h-[320px] items-center justify-center px-4 text-sm text-slate-500">
                Generated remix preview missing.
              </div>
            )}
          </div>

          <div className="space-y-3 px-4 py-4">
            <div>
              <div className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{hostname || "destination url missing"}</div>
              <div className="mt-1 text-[15px] font-semibold leading-5 text-slate-900">
                {headline || "Headline missing from prepared spec."}
              </div>
              {description ? <div className="mt-1 text-sm leading-5 text-slate-600">{description}</div> : null}
            </div>
            <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
              <div className="text-xs text-slate-500">Call to action</div>
              <div className="rounded-full bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white">
                {cta || "Learn More"}
              </div>
            </div>
          </div>
        </>
      ) : (
        <div className="flex min-h-[520px] items-center justify-center px-6 py-10 text-center text-sm leading-6 text-slate-500">
          Prepare Meta review to render the exact upload preview for this asset.
        </div>
      )}
    </div>
  );
}

export function CampaignMetaAdsPanel({ campaign, assetBriefs }: CampaignMetaAdsPanelProps) {
  const queryClient = useQueryClient();
  const { post } = useApiClient();
  const { getConfig, listPipelineAssets } = useMetaApi();

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
  const [lastWorkflowRunId, setLastWorkflowRunId] = useState<string | null>(null);
  const [lastPreparedAt, setLastPreparedAt] = useState<string | null>(null);
  const [autoRefreshUntil, setAutoRefreshUntil] = useState<number | null>(null);
  const [latestGenerationOnly, setLatestGenerationOnly] = useState(true);

  const assetBriefIds = useMemo(
    () => assetBriefs.map((brief) => brief.id).filter((briefId): briefId is string => Boolean(briefId)),
    [assetBriefs],
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
    if (!prepareAssetBriefIds.length) {
      setPrepareError(
        latestGenerationOnly && latestGenerationSummary
          ? "No generated assets exist in the visible generation yet."
          : "No asset briefs exist for this campaign yet.",
      );
      return;
    }
    setPreparePending(true);
    try {
      await post(`/campaigns/${campaign.id}/meta/review-setup`, {
        assetBriefIds: prepareAssetBriefIds,
        generationBatchId:
          latestGenerationOnly && latestGenerationSummary?.kind === "batch" ? latestGenerationBatchId : undefined,
      });
      setLastPreparedAt(new Date().toISOString());
      await refreshPipeline();
    } catch (err) {
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
  const latestGenerationBatchId = latestGenerationSummary?.kind === "batch" ? latestGenerationSummary.key.slice("batch:".length) : null;
  const visiblePipeline = useMemo(() => {
    if (!latestGenerationOnly || !latestGenerationKey) return pipeline;
    return pipeline.filter((item) => getGenerationGroup(item).key === latestGenerationKey);
  }, [latestGenerationKey, latestGenerationOnly, pipeline]);
  const hiddenLegacyCount = useMemo(() => {
    if (!latestGenerationOnly || !latestGenerationKey) return 0;
    return pipeline.length - visiblePipeline.length;
  }, [latestGenerationKey, latestGenerationOnly, pipeline.length, visiblePipeline.length]);
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
    if (latestGenerationOnly && latestGenerationKey) return visibleAssetBriefIds;
    return assetBriefIds;
  }, [assetBriefIds, latestGenerationKey, latestGenerationOnly, visibleAssetBriefIds]);
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

  return (
    <div className="space-y-4">
      <div className="border border-border bg-transparent p-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-base font-semibold text-content">Meta ads review</div>
            <div className="text-sm text-content-muted">
              Internal draft setup only. Nothing on this tab publishes to Meta.
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

        <div className="mt-4 grid gap-3 md:grid-cols-4">
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
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button variant="primary" size="sm" onClick={handleGenerateAssets} disabled={generatePending || !assetBriefIds.length}>
            {generatePending ? "Starting…" : "Generate creatives"}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handlePrepareMetaReview}
            disabled={preparePending || !prepareAssetBriefIds.length || !hasGeneratedAssets}
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

        <div className="mt-2 space-y-1 text-sm text-content-muted">
          <div>Generate creatives runs the swipe-first remix flow and Stage 1 Gemini swipe copy generation for the current briefs.</div>
          <div>Prepare Meta review creates internal Meta creative specs from the selected asset's stored swipe copy pack.</div>
          {lastWorkflowRunId ? <div>Latest creative workflow: <span className="font-mono">{lastWorkflowRunId}</span></div> : null}
          {lastPreparedAt ? <div>Latest Meta review prep: {formatDate(lastPreparedAt)}</div> : null}
          {autoRefreshUntil ? <div>Auto-refreshing this panel while creative generation completes.</div> : null}
          {!hasGeneratedAssets ? <div>Generate creatives first. Meta review stays disabled until campaign assets exist.</div> : null}
          {latestGenerationSummary ? <div>Visible generation focus: <span className="font-mono">{latestGenerationSummary.label}</span></div> : null}
          {hiddenLegacyCount ? <div>{hiddenLegacyCount} older or non-selected assets are currently hidden.</div> : null}
          {visibleMissingCreativeSpecCount ? (
            <div className="text-warning">{visibleMissingCreativeSpecCount} visible generated assets still need internal Meta specs.</div>
          ) : null}
          {generateError ? <div className="text-danger">{generateError}</div> : null}
          {prepareError ? <div className="text-danger">{prepareError}</div> : null}
          {pipelineError ? <div className="text-danger">{pipelineError}</div> : null}
        </div>
      </div>

      <CampaignPaidAdsQaCard campaign={campaign} />

      <div className="border border-border bg-transparent">
        <div className="border-b border-border px-4 py-3">
          <div className="text-base font-semibold text-content">Draft Meta-ready creatives</div>
          <div className="text-sm text-content-muted">
            Campaign assets, internal Meta creative specs, ad set specs, and funnel review links.
          </div>
        </div>

        {pipelineLoading ? (
          <div className="px-4 py-3 text-sm text-content-muted">Loading Meta campaign assets…</div>
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
                    const preSalesUrl = resolveReviewUrl(reviewPaths["pre-sales"]);
                    const salesUrl = resolveReviewUrl(reviewPaths["sales"]);
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
                    const metaSpecPreparedFromSwipeCopy = creativeSpecSource === "campaign_meta_review_setup_swipe_copy";
                    const hasLegacyMetaSpec = Boolean(item.creative_spec?.id) && !metaSpecPreparedFromSwipeCopy;
                    const metaPreviewStatusLabel = item.creative_spec?.id
                      ? metaSpecPreparedFromSwipeCopy
                        ? "Prepared Meta spec"
                        : "Legacy Meta spec"
                      : "Spec missing";
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
                              {batchId ? <Badge tone="neutral">Batch {shortId(batchId, 5)}</Badge> : null}
                            </div>
                          </div>

                          <div className="flex flex-wrap gap-2">
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
                            <div className="mt-3 space-y-2">
                              <div className="text-sm font-semibold text-content">{sourceLabel}</div>
                              <div className="text-xs leading-5 text-content-muted">
                                This is the swipe the system grounded the remix on before preparing any Meta creative spec.
                              </div>
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
                                  <CopyField label="Destination URL" value={metaDestinationUrl} />
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
                            destinationUrl={metaDestinationUrl}
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
    </div>
  );
}
