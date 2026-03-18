import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { useMetaPublishContext, formatDate } from "./MetaPublishProvider";

export function MetaGeneratePanel() {
  const {
    assetBriefIds,
    hasGeneratedAssets,
    generatePending,
    generateError,
    handleGenerateAssets,
    preparePending,
    prepareAssetBriefIds,
    canPrepareMetaReview,
    handlePrepareMetaReview,
    lastWorkflowRunId,
    lastPreparedAt,
    autoRefreshUntil,
    pipelineLoading,
    refreshPipeline,
    generationSummaries,
    latestGenerationSummary,
    latestGenerationOnly,
    setLatestGenerationOnly,
    pipeline,
    creativeSpecCount,
  } = useMetaPublishContext();

  return (
    <div className="space-y-4">
      {/* Actions */}
      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="text-base font-semibold text-content">Generate &amp; prepare</div>
        <div className="mt-1 text-sm text-content-muted">
          Generate creative assets from briefs, then prepare internal Meta creative specs for review.
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button variant="primary" size="sm" onClick={() => void handleGenerateAssets()} disabled={generatePending || !assetBriefIds.length}>
            {generatePending ? "Starting…" : "Generate creatives"}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void handlePrepareMetaReview()}
            disabled={preparePending || !prepareAssetBriefIds.length || !hasGeneratedAssets || !canPrepareMetaReview}
          >
            {preparePending ? "Preparing…" : "Prepare Meta review"}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => void refreshPipeline()} disabled={pipelineLoading}>
            {pipelineLoading ? "Refreshing…" : "Refresh"}
          </Button>
          {generationSummaries.length > 1 ? (
            <Button variant="secondary" size="sm" onClick={() => setLatestGenerationOnly(!latestGenerationOnly)}>
              {latestGenerationOnly ? "Show all generations" : "Show latest generation only"}
            </Button>
          ) : null}
        </div>

        {generateError ? (
          <Callout variant="danger" size="sm" className="mt-3">{generateError}</Callout>
        ) : null}

        {autoRefreshUntil ? (
          <Callout variant="info" size="sm" className="mt-3">
            Auto-refreshing while creative generation completes.
          </Callout>
        ) : null}

        {!assetBriefIds.length ? (
          <Callout variant="warning" size="sm" className="mt-3">
            No asset briefs exist for this campaign yet. Complete the Angles phase to create briefs.
          </Callout>
        ) : null}
      </div>

      {/* Status summary */}
      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="text-sm font-semibold text-content">Generation status</div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-lg border border-border bg-surface-2 px-3 py-2">
            <div className="text-xs text-content-muted">Total assets</div>
            <div className="mt-1 text-lg font-semibold text-content">{pipeline.length}</div>
          </div>
          <div className="rounded-lg border border-border bg-surface-2 px-3 py-2">
            <div className="text-xs text-content-muted">With creative specs</div>
            <div className="mt-1 text-lg font-semibold text-content">{creativeSpecCount}</div>
          </div>
          <div className="rounded-lg border border-border bg-surface-2 px-3 py-2">
            <div className="text-xs text-content-muted">Generations</div>
            <div className="mt-1 text-lg font-semibold text-content">{generationSummaries.length}</div>
          </div>
          <div className="rounded-lg border border-border bg-surface-2 px-3 py-2">
            <div className="text-xs text-content-muted">Briefs</div>
            <div className="mt-1 text-lg font-semibold text-content">{assetBriefIds.length}</div>
          </div>
        </div>

        {/* Generation history */}
        {generationSummaries.length > 0 ? (
          <details className="mt-4">
            <summary className="cursor-pointer text-xs font-semibold text-content-muted">
              Generation history ({generationSummaries.length})
            </summary>
            <div className="mt-2 space-y-1">
              {generationSummaries.map((gen) => (
                <div key={gen.key} className="flex items-center justify-between gap-2 rounded-md border border-border bg-surface-2 px-3 py-2 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-content-muted">{gen.label}</span>
                    <Badge tone="neutral">{gen.count} assets</Badge>
                    {gen.key === latestGenerationSummary?.key ? <Badge tone="accent">Latest</Badge> : null}
                  </div>
                  <span className="text-xs text-content-muted">{formatDate(gen.latestCreatedAt ? new Date(gen.latestCreatedAt).toISOString() : null)}</span>
                </div>
              ))}
            </div>
          </details>
        ) : null}

        {lastWorkflowRunId ? (
          <div className="mt-3 text-xs text-content-muted">
            Latest creative workflow: <span className="font-mono">{lastWorkflowRunId}</span>
          </div>
        ) : null}
        {lastPreparedAt ? (
          <div className="mt-1 text-xs text-content-muted">
            Latest Meta review prep: {formatDate(lastPreparedAt)}
          </div>
        ) : null}
      </div>
    </div>
  );
}
