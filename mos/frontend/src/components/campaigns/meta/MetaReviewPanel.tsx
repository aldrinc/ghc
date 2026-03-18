import { useCallback, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { CreativeReviewGrid } from "@/components/creative/CreativeReviewGrid";
import { AdDetailPanel } from "@/components/creative/AdDetailPanel";
import { useCreativeReview } from "@/hooks/useCreativeReview";
import type { AdReviewItem } from "@/types/creativeReview";
import { useMetaPublishContext } from "./MetaPublishProvider";

export function MetaReviewPanel({ onAdvance }: { onAdvance?: () => void }) {
  const {
    campaign,
    assetBriefs,
    visiblePipeline,
    latestGenerationScopedPipeline,
    creativeReviewQaRuns,
    creativeQaFilteringEnabled,
    creativeQaNotice,
    includedPackageItems,
    excludedPackageCount,
    selectionByAssetId,
    publishSelections,
    handleSetPublishDecision,
    canManagePublishPackage,
    selectionPendingAssetIds,
    latestGenerationFunnelIds,
    activeFunnelId,
    requiresFunnelScope,
    pipelineLoading,
    hiddenLegacyCount,
    hiddenOtherFunnelCount,
  } = useMetaPublishContext();

  const [view, setView] = useState<"review" | "final">("review");
  const [selectedCardIds, setSelectedCardIds] = useState<Set<string>>(new Set());
  const [detailItem, setDetailItem] = useState<AdReviewItem | null>(null);

  // Use the existing transform hook to convert pipeline assets to review items
  const experimentNameById = useMemo(() => {
    const map: Record<string, string> = {};
    visiblePipeline.forEach((item) => {
      if (item.experiment?.name && item.experiment?.id) map[item.experiment.id] = item.experiment.name;
    });
    return map;
  }, [visiblePipeline]);

  const variantNameById = useMemo<Record<string, string>>(() => ({}), []);

  const activePipeline = view === "final" ? includedPackageItems : visiblePipeline;

  const reviewItems = useCreativeReview({
    pipelineAssets: activePipeline,
    publishSelections,
    assetBriefs,
    qaRuns: creativeReviewQaRuns,
    experimentNameById,
    variantNameById,
  });

  const handleCardClick = useCallback((item: AdReviewItem) => {
    setDetailItem(item);
  }, []);

  const handleExcludeFromDetail = useCallback(
    (assetId: string) => {
      void handleSetPublishDecision(assetId, "excluded");
    },
    [handleSetPublishDecision],
  );

  const handleBulkExclude = useCallback(async () => {
    for (const id of selectedCardIds) {
      await handleSetPublishDecision(id, "excluded");
    }
    setSelectedCardIds(new Set());
  }, [handleSetPublishDecision, selectedCardIds]);

  const handleBulkRestore = useCallback(async () => {
    for (const id of selectedCardIds) {
      await handleSetPublishDecision(id, null);
    }
    setSelectedCardIds(new Set());
  }, [handleSetPublishDecision, selectedCardIds]);

  const needsFunnelScope = requiresFunnelScope && latestGenerationFunnelIds.length > 1 && !activeFunnelId;

  return (
    <div className="space-y-4">
      {/* Advance to next step */}
      {onAdvance && includedPackageItems.length > 0 && !pipelineLoading ? (
        <div className="flex items-center justify-between rounded-lg border border-border bg-surface-2 px-4 py-3">
          <div className="text-sm text-content-muted">
            <span className="font-semibold text-content">{includedPackageItems.length}</span> creative{includedPackageItems.length !== 1 ? "s" : ""} in final package
            {excludedPackageCount > 0 ? (
              <span> · {excludedPackageCount} excluded</span>
            ) : null}
          </div>
          <Button variant="primary" size="sm" onClick={onAdvance}>
            Continue to QA &rarr;
          </Button>
        </div>
      ) : null}

      {/* View toggle */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button
            variant={view === "review" ? "primary" : "secondary"}
            size="sm"
            onClick={() => setView("review")}
          >
            All candidates ({visiblePipeline.length})
          </Button>
          <Button
            variant={view === "final" ? "primary" : "secondary"}
            size="sm"
            onClick={() => setView("final")}
          >
            Final package ({includedPackageItems.length})
          </Button>
          {excludedPackageCount > 0 ? (
            <Badge tone="danger">{excludedPackageCount} excluded</Badge>
          ) : null}
        </div>

        {/* Bulk actions */}
        {selectedCardIds.size > 0 && canManagePublishPackage ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-content-muted">{selectedCardIds.size} selected</span>
            <Button variant="destructive" size="xs" onClick={() => void handleBulkExclude()}>
              Exclude selected
            </Button>
            <Button variant="secondary" size="xs" onClick={() => void handleBulkRestore()}>
              Restore selected
            </Button>
          </div>
        ) : null}
      </div>

      {/* Hidden items info */}
      {(hiddenLegacyCount > 0 || hiddenOtherFunnelCount > 0) ? (
        <div className="text-xs text-content-muted">
          {hiddenLegacyCount > 0 ? `${hiddenLegacyCount} older assets hidden. ` : ""}
          {hiddenOtherFunnelCount > 0 ? `${hiddenOtherFunnelCount} assets from other funnels hidden.` : ""}
        </div>
      ) : null}

      {/* States */}
      {pipelineLoading ? (
        <div className="text-sm text-content-muted">Loading Meta campaign assets…</div>
      ) : needsFunnelScope ? (
        <Callout variant="warning" size="sm">
          Pick one funnel above before reviewing Meta-ready creatives for this generation.
        </Callout>
      ) : reviewItems.length === 0 ? (
        <div className="border border-border bg-transparent px-4 py-8 text-center text-sm text-content-muted">
          {view === "final"
            ? "All creatives are excluded. Return to All candidates and restore the creatives you want."
            : "No campaign creative assets found yet. Generate creatives first."}
        </div>
      ) : (
        <div className="space-y-3">
          {creativeQaNotice ? (
            <Callout variant="warning" size="sm">
              {creativeQaNotice}
            </Callout>
          ) : null}
          <CreativeReviewGrid
            items={reviewItems}
            selectedIds={selectedCardIds}
            onSelectionChange={setSelectedCardIds}
            onCardClick={handleCardClick}
            violationFilterEnabled={creativeQaFilteringEnabled}
          />
        </div>
      )}

      {/* Detail slide-over */}
      <AdDetailPanel
        item={detailItem}
        open={detailItem !== null}
        onClose={() => setDetailItem(null)}
        onExclude={canManagePublishPackage ? handleExcludeFromDetail : undefined}
      />
    </div>
  );
}
