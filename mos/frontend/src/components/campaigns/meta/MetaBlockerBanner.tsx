import { Callout } from "@/components/ui/callout";
import { Badge } from "@/components/ui/badge";
import { useMetaPublishContext, formatFunnelLabel, shortId } from "./MetaPublishProvider";

export function MetaBlockerBanner() {
  const {
    requiresFunnelScope,
    latestGenerationFunnelIds,
    activeFunnelId,
    latestGenerationUnmappedCount,
    canManagePublishPackage,
    funnelScopeOptions,
    canPrepareMetaReview,
    funnelsLoading,
    funnelsError,
    selectionLoading,
    visibleMissingCreativeSpecCount,
    generateError,
    prepareError,
    prepareIssues,
    selectionError,
    pipelineError,
    configError,
    hasGeneratedAssets,
    autoRefreshUntil,
    funnelById,
  } = useMetaPublishContext();

  const warnings: string[] = [];
  const errors: string[] = [];

  // Warnings
  if (requiresFunnelScope && latestGenerationFunnelIds.length > 1 && !activeFunnelId) {
    warnings.push("Pick one funnel to review the latest generation. Mixed-funnel Meta review is blocked.");
  }
  if (requiresFunnelScope && latestGenerationUnmappedCount) {
    warnings.push(`${latestGenerationUnmappedCount} latest-generation assets are missing an explicit asset brief funnel mapping.`);
  }
  if (!canManagePublishPackage) {
    warnings.push(
      requiresFunnelScope
        ? "Switch back to latest generation only and pick one funnel to manage the final Meta package."
        : "Switch back to latest generation only to manage the final Meta package.",
    );
  }
  if (requiresFunnelScope && funnelScopeOptions.length > 1 && !canPrepareMetaReview) {
    warnings.push("Prepare Meta review is disabled until one funnel is selected for the latest generation.");
  }
  if (visibleMissingCreativeSpecCount) {
    warnings.push(`${visibleMissingCreativeSpecCount} visible generated assets still need internal Meta specs.`);
  }
  if (!hasGeneratedAssets) {
    warnings.push("Generate creatives first. Meta review stays disabled until campaign assets exist.");
  }

  // Errors
  if (configError) errors.push(configError);
  if (generateError) errors.push(generateError);
  if (prepareError) errors.push(prepareError);
  if (selectionError) errors.push(selectionError);
  if (pipelineError) errors.push(pipelineError);
  if (funnelsError) errors.push(String(funnelsError));

  // Loading states
  if (funnelsLoading && requiresFunnelScope && funnelScopeOptions.length <= 1) {
    // quiet — just loading
  }
  if (selectionLoading) {
    // quiet — loading
  }

  if (!warnings.length && !errors.length && !prepareIssues.length && !autoRefreshUntil) return null;

  return (
    <div className="space-y-2">
      {autoRefreshUntil ? (
        <Callout variant="info" size="sm">
          Auto-refreshing while creative generation completes.
        </Callout>
      ) : null}

      {errors.length > 0 ? (
        <Callout variant="danger" size="sm" title={errors.length === 1 ? errors[0] : `${errors.length} errors`}>
          {errors.length > 1 ? (
            <ul className="mt-1 list-inside list-disc space-y-0.5">
              {errors.map((err, i) => <li key={i}>{err}</li>)}
            </ul>
          ) : null}
        </Callout>
      ) : null}

      {prepareIssues.length > 0 ? (
        <Callout variant="danger" size="sm" title={`Meta review prep blocked for ${prepareIssues.length} asset(s)`}>
          <div className="mt-2 space-y-2">
            {prepareIssues.map((issue) => (
              <div key={`issue-${issue.assetId}`} className="rounded-md border border-danger/20 bg-background px-3 py-2 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-content-muted">{shortId(issue.assetId, 5)}</span>
                  {issue.generationKey ? <Badge tone="neutral">{issue.generationKey}</Badge> : null}
                  {issue.assetBriefId ? <Badge tone="neutral">{issue.assetBriefId}</Badge> : null}
                  {issue.funnelId ? (
                    <Badge tone="neutral">{formatFunnelLabel(funnelById.get(issue.funnelId) || null, issue.funnelId)}</Badge>
                  ) : null}
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
                  {issue.issues.map((assetIssue, idx) => (
                    <div key={`${issue.assetId}-${assetIssue.ruleId || idx}`}>
                      {assetIssue.ruleId ? `${assetIssue.ruleId}: ` : ""}
                      {assetIssue.message || assetIssue.title || "Meta review prep issue"}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Callout>
      ) : null}

      {warnings.length > 0 ? (
        <Callout variant="warning" size="sm" title={warnings.length === 1 ? warnings[0] : `${warnings.length} items need attention`}>
          {warnings.length > 1 ? (
            <ul className="mt-1 list-inside list-disc space-y-0.5">
              {warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          ) : null}
        </Callout>
      ) : null}
    </div>
  );
}
