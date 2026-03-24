import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { SwipeCollectionSelector } from "@/components/campaigns/SwipeCollectionSelector";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useApiClient, type ApiError } from "@/api/client";
import { useMetaApi } from "@/api/meta";
import { useCampaignContext } from "@/contexts/CampaignContext";
import type { AdReviewItem } from "@/types/creativeReview";
import type { MetaPipelineAsset } from "@/types/meta";
import { CreativeReviewGrid } from "@/components/creative/CreativeReviewGrid";
import { AdDetailPanel } from "@/components/creative/AdDetailPanel";
import { useCreativeReview } from "@/hooks/useCreativeReview";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getErrorMessage(err: unknown) {
  if (typeof err === "string") return err;
  if (err && typeof err === "object" && "message" in err) return (err as ApiError).message || "Request failed";
  return "Request failed";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CampaignCreativeTab() {
  const navigate = useNavigate();
  const { post } = useApiClient();
  const { listPipelineAssets } = useMetaApi();
  const queryClient = useQueryClient();
  const {
    campaign,
    experimentSpecs,
    assetBriefs,
    briefsLoading,
    generatedAssetsByBriefId,
    generatedAssetTotal,
    briefsWithGeneratedAssets,
    campaignProductLoading,
  } = useCampaignContext();

  // ---- Local state --------------------------------------------------------
  const [selectedAssetBriefIds, setSelectedAssetBriefIds] = useState<string[]>([]);
  const [selectedSwipeCollectionId, setSelectedSwipeCollectionId] = useState<string | null>(null);
  const [creativeProductionPending, setCreativeProductionPending] = useState(false);
  const [creativeProductionError, setCreativeProductionError] = useState<string | null>(null);
  const [selectedCardIds, setSelectedCardIds] = useState<Set<string>>(new Set());
  const [detailItem, setDetailItem] = useState<AdReviewItem | null>(null);

  // ---- Derived lookups ----------------------------------------------------
  const experimentNameById = useMemo(() => {
    const map: Record<string, string> = {};
    experimentSpecs.forEach((spec) => {
      if (spec.id) map[spec.id] = spec.name || spec.id;
    });
    return map;
  }, [experimentSpecs]);

  const variantNameById = useMemo(() => {
    const map: Record<string, string> = {};
    experimentSpecs.forEach((spec) => {
      (spec.variants || []).forEach((variant) => {
        if (!variant?.id) return;
        map[variant.id] = variant.name || variant.id;
      });
    });
    return map;
  }, [experimentSpecs]);

  const briefById = useMemo(() => {
    const map = new Map<string, { brief: NonNullable<AdReviewItem["brief"]>; experimentName: string | null; variantName: string | null }>();
    assetBriefs.forEach((brief) => {
      map.set(brief.id, {
        brief,
        experimentName: brief.experimentId ? experimentNameById[brief.experimentId] ?? null : null,
        variantName: brief.variantId
          ? variantNameById[brief.variantId] ?? brief.variantName ?? null
          : brief.variantName ?? null,
      });
    });
    return map;
  }, [assetBriefs, experimentNameById, variantNameById]);

  const {
    data: pipelineAssets = [],
    isLoading: pipelineLoading,
    error: pipelineError,
  } = useQuery<MetaPipelineAsset[], ApiError>({
    queryKey: ["meta", "pipeline", "assets", campaign.id],
    queryFn: () => listPipelineAssets({ campaignId: campaign.id }),
    enabled: Boolean(campaign.id),
  });

  const scopedPipelineAssets = useMemo(() => {
    const validBriefIds = new Set(assetBriefs.map((brief) => brief.id));
    if (!validBriefIds.size) return [];
    return pipelineAssets.filter((item) => {
      const metadata = (item.asset.ai_metadata || {}) as Record<string, unknown>;
      return typeof metadata.assetBriefId === "string" && validBriefIds.has(metadata.assetBriefId);
    });
  }, [assetBriefs, pipelineAssets]);

  // ---- Transform into review items ----------------------------------------
  const reviewItems = useCreativeReview({
    pipelineAssets: scopedPipelineAssets,
    publishSelections: [],
    assetBriefs,
    qaRuns: [],
    experimentNameById,
    variantNameById,
  });

  // ---- Sync effects -------------------------------------------------------
  useEffect(() => {
    setSelectedAssetBriefIds((prev) => prev.filter((id) => assetBriefs.some((brief) => brief.id === id)));
  }, [assetBriefs]);

  // ---- Selection helpers --------------------------------------------------
  const allAssetBriefIds = useMemo(() => assetBriefs.map((brief) => brief.id).filter(Boolean), [assetBriefs]);
  const allAssetBriefsSelected =
    allAssetBriefIds.length > 0 && allAssetBriefIds.every((id) => selectedAssetBriefIds.includes(id));
  const toggleAssetBriefSelection = (id: string) => {
    setSelectedAssetBriefIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  };
  const toggleAllAssetBriefs = () => {
    setSelectedAssetBriefIds(allAssetBriefsSelected ? [] : allAssetBriefIds);
  };

  // ---- Handlers -----------------------------------------------------------
  const handleStartCreativeProduction = async () => {
    setCreativeProductionError(null);
    if (!selectedAssetBriefIds.length) {
      setCreativeProductionError("Select at least one creative brief to generate assets.");
      return;
    }
    if (!selectedSwipeCollectionId) {
      setCreativeProductionError("Select a swipe collection before generating assets.");
      return;
    }

    setCreativeProductionPending(true);
    try {
      const response = await post<{ workflow_run_id: string }>(`/campaigns/${campaign.id}/creative/produce`, {
        assetBriefIds: selectedAssetBriefIds,
        swipeCollectionId: selectedSwipeCollectionId,
      });
      if (!response?.workflow_run_id) {
        setCreativeProductionError("Creative production started but no workflow id was returned.");
        return;
      }
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      navigate(`/strategy/${response.workflow_run_id}`);
    } catch (err) {
      setCreativeProductionError(`Failed to start creative production: ${getErrorMessage(err)}`);
    } finally {
      setCreativeProductionPending(false);
    }
  };

  const handleCardClick = useCallback((item: AdReviewItem) => {
    setDetailItem(item);
  }, []);

  // ---- Render -------------------------------------------------------------
  return (
    <div className="space-y-6">
      {/* Brief management header */}
      <div className="border border-border bg-transparent p-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-base font-semibold text-content">Creative briefs</div>
            <div className="text-sm text-content-muted">
              {briefsLoading
                ? "Loading…"
                : `${assetBriefs.length} briefs · ${generatedAssetTotal} generated assets across ${briefsWithGeneratedAssets} briefs`}
            </div>
            {campaignProductLoading ? (
              <div className="mt-1 text-sm text-content-muted">Loading generated assets…</div>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              onClick={handleStartCreativeProduction}
              disabled={creativeProductionPending || selectedAssetBriefIds.length === 0 || !selectedSwipeCollectionId}
            >
              {creativeProductionPending ? "Starting…" : "Generate assets"}
            </Button>
          </div>
        </div>

        <SwipeCollectionSelector
          className="mt-4"
          campaignId={campaign.id}
          value={selectedSwipeCollectionId}
          onChange={setSelectedSwipeCollectionId}
        />

        {/* Brief selection (expanded by default when briefs exist) */}
        {assetBriefs.length > 0 ? (
          <details className="mt-3" open>
            <summary className="cursor-pointer text-xs font-semibold text-content-muted">
              Select briefs for generation ({selectedAssetBriefIds.length}/{assetBriefs.length} selected)
            </summary>
            <div className="mt-2 space-y-1">
              <label className="flex items-center gap-2 text-xs text-content-muted">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5 rounded border border-border bg-surface text-accent"
                  checked={allAssetBriefsSelected}
                  onChange={toggleAllAssetBriefs}
                />
                Select all
              </label>
              <div className="max-h-40 space-y-1 overflow-y-auto">
                {assetBriefs.map((brief) => {
                  const ctx = briefById.get(brief.id);
                  return (
                    <label key={brief.id} className="flex items-center gap-2 text-xs text-content">
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5 rounded border border-border bg-surface text-accent"
                        checked={selectedAssetBriefIds.includes(brief.id)}
                        onChange={() => toggleAssetBriefSelection(brief.id)}
                      />
                      <span className="truncate">
                        {brief.creativeConcept || brief.id}
                        {ctx?.experimentName ? ` · ${ctx.experimentName}` : ""}
                        {ctx?.variantName ? ` · ${ctx.variantName}` : ""}
                      </span>
                      {(generatedAssetsByBriefId.get(brief.id)?.length ?? 0) > 0 ? (
                        <Badge tone="success">{generatedAssetsByBriefId.get(brief.id)?.length}</Badge>
                      ) : null}
                    </label>
                  );
                })}
              </div>
            </div>
          </details>
        ) : !briefsLoading ? (
          <div className="mt-2 text-sm text-content-muted">
            Creative briefs will appear after angle specs are generated.
          </div>
        ) : null}

        {creativeProductionError ? (
          <div className="mt-2 text-sm text-danger">{creativeProductionError}</div>
        ) : null}
      </div>

      {/* Ad review grid */}
      {reviewItems.length > 0 ? (
        <CreativeReviewGrid
          items={reviewItems}
          selectedIds={selectedCardIds}
          onSelectionChange={setSelectedCardIds}
          onCardClick={handleCardClick}
        />
      ) : pipelineError ? (
        <div className="border border-danger/30 bg-danger/5 px-4 py-8 text-center text-sm text-danger">
          Failed to load campaign creative specs: {getErrorMessage(pipelineError)}
        </div>
      ) : pipelineLoading || campaignProductLoading ? (
        <div className="border border-border bg-transparent px-4 py-8 text-center text-sm text-content-muted">
          Loading campaign creative assets…
        </div>
      ) : !briefsLoading && !campaignProductLoading ? (
        <div className="border border-border bg-transparent px-4 py-8 text-center text-sm text-content-muted">
          No generated assets yet. Select briefs above and click "Generate assets" to create ads.
        </div>
      ) : null}

      {/* Detail slide-over */}
      <AdDetailPanel
        item={detailItem}
        open={detailItem !== null}
        onClose={() => setDetailItem(null)}
      />
    </div>
  );
}
