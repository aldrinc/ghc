import { useCallback, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import { useMetaApi } from "@/api/meta";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AssetBrief } from "@/types/artifacts";
import type { Campaign } from "@/types/common";
import type { MetaPipelineAsset } from "@/types/meta";

type CampaignMetaAdsPanelProps = {
  campaign: Campaign;
  assetBriefs: AssetBrief[];
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8008";

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
    if (!assetBriefIds.length) {
      setPrepareError("No asset briefs exist for this campaign yet.");
      return;
    }
    setPreparePending(true);
    try {
      await post(`/campaigns/${campaign.id}/meta/review-setup`, { assetBriefIds });
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
  const missingCreativeSpecCount = useMemo(
    () => pipeline.filter((item) => !item.creative_spec?.id).length,
    [pipeline],
  );
  const hasGeneratedAssets = pipeline.length > 0;

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
            disabled={preparePending || !assetBriefIds.length || !hasGeneratedAssets}
          >
            {preparePending ? "Preparing…" : "Prepare Meta review"}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => void refreshPipeline()} disabled={pipelineLoading}>
            {pipelineLoading ? "Refreshing…" : "Refresh"}
          </Button>
        </div>

        <div className="mt-2 space-y-1 text-sm text-content-muted">
          <div>Generate creatives runs the campaign creative-service flow for all current briefs.</div>
          <div>Prepare Meta review creates internal draft creative/ad set objects from the generated assets.</div>
          {lastWorkflowRunId ? <div>Latest creative workflow: <span className="font-mono">{lastWorkflowRunId}</span></div> : null}
          {lastPreparedAt ? <div>Latest Meta review prep: {formatDate(lastPreparedAt)}</div> : null}
          {autoRefreshUntil ? <div>Auto-refreshing this panel while creative generation completes.</div> : null}
          {!hasGeneratedAssets ? <div>Generate creatives first. Meta review stays disabled until campaign assets exist.</div> : null}
          {missingCreativeSpecCount ? <div className="text-warning">{missingCreativeSpecCount} generated assets still need internal Meta specs.</div> : null}
          {generateError ? <div className="text-danger">{generateError}</div> : null}
          {prepareError ? <div className="text-danger">{prepareError}</div> : null}
          {pipelineError ? <div className="text-danger">{pipelineError}</div> : null}
        </div>
      </div>

      <div className="border border-border bg-transparent">
        <div className="border-b border-border px-4 py-3">
          <div className="text-base font-semibold text-content">Draft Meta-ready creatives</div>
          <div className="text-sm text-content-muted">
            Campaign assets, internal Meta creative specs, ad set specs, and funnel review links.
          </div>
        </div>

        {pipelineLoading ? (
          <div className="px-4 py-3 text-sm text-content-muted">Loading Meta campaign assets…</div>
        ) : !pipeline.length ? (
          <div className="px-4 py-3 text-sm text-content-muted">
            No campaign creative assets found yet. Generate creatives first.
          </div>
        ) : (
          <div className="divide-y divide-border">
            {pipeline.map((item) => {
              const assetUrl = resolveAssetUrl(item.asset.public_url);
              const creativeMetadata = (item.creative_spec?.metadata_json || {}) as Record<string, unknown>;
              const reviewPaths = (creativeMetadata.reviewPaths || {}) as Record<string, string>;
              const preSalesUrl = resolveReviewUrl(reviewPaths["pre-sales"]);
              const salesUrl = resolveReviewUrl(reviewPaths["sales"]);
              return (
                <div key={item.asset.id} className="grid gap-4 px-4 py-4 xl:grid-cols-[220px_minmax(0,1fr)]">
                  <div className="overflow-hidden rounded-lg border border-border bg-surface-2">
                    {assetUrl ? (
                      <img
                        src={assetUrl}
                        alt={item.asset.asset_kind || "Creative asset"}
                        className="h-[220px] w-full object-contain"
                        loading="lazy"
                      />
                    ) : (
                      <div className="flex h-[220px] items-center justify-center text-sm text-content-muted">
                        No preview
                      </div>
                    )}
                  </div>

                  <div className="min-w-0 space-y-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="text-sm font-semibold text-content">{item.creative_spec?.name || item.asset.public_id}</div>
                      <Badge tone={item.creative_spec?.id ? "success" : "accent"}>
                        {item.creative_spec?.id ? "Creative spec ready" : "Spec missing"}
                      </Badge>
                      <Badge tone="neutral">{item.asset.status || "draft"}</Badge>
                    </div>

                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="rounded-lg border border-border bg-surface p-3">
                        <div className="text-xs uppercase tracking-wide text-content-muted">Asset</div>
                        <div className="mt-2 space-y-1 text-sm text-content">
                          <div><span className="text-content-muted">Asset ID:</span> <span className="font-mono">{item.asset.id}</span></div>
                          <div><span className="text-content-muted">Created:</span> {formatDate(item.asset.created_at)}</div>
                          <div><span className="text-content-muted">Angle:</span> {item.experiment?.name || item.experiment?.id || "—"}</div>
                        </div>
                      </div>

                      <div className="rounded-lg border border-border bg-surface p-3">
                        <div className="text-xs uppercase tracking-wide text-content-muted">Creative spec</div>
                        {item.creative_spec ? (
                          <div className="mt-2 space-y-2 text-sm text-content">
                            <div>
                              <div className="text-xs uppercase tracking-wide text-content-muted">Primary text</div>
                              <div>{item.creative_spec.primary_text || "—"}</div>
                            </div>
                            <div>
                              <div className="text-xs uppercase tracking-wide text-content-muted">Headline</div>
                              <div>{item.creative_spec.headline || "—"}</div>
                            </div>
                            <div>
                              <div className="text-xs uppercase tracking-wide text-content-muted">Description</div>
                              <div>{item.creative_spec.description || "—"}</div>
                            </div>
                          </div>
                        ) : (
                          <div className="mt-2 text-sm text-content-muted">No internal Meta creative spec yet.</div>
                        )}
                      </div>
                    </div>

                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="rounded-lg border border-border bg-surface p-3">
                        <div className="text-xs uppercase tracking-wide text-content-muted">Ad set specs</div>
                        {(item.adset_specs || []).length ? (
                          <div className="mt-2 space-y-2">
                            {item.adset_specs.map((spec) => (
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

                      <div className="rounded-lg border border-border bg-surface p-3">
                        <div className="text-xs uppercase tracking-wide text-content-muted">Funnel review</div>
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
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
