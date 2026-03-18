import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { CampaignPaidAdsQaCard } from "@/components/campaigns/CampaignPaidAdsQaCard";
import { useMetaPublishContext } from "./MetaPublishProvider";

export function MetaQaPanel({ onAdvance }: { onAdvance?: () => void }) {
  const {
    campaign,
    latestGenerationKey,
    latestGenerationSummary,
    activeFunnelId,
    activeFunnelLabel,
    canPrepareMetaReview,
    reviewBaseUrl,
    requiresFunnelScope,
    creativeSpecCount,
    includedPackageItems,
  } = useMetaPublishContext();

  return (
    <div className="space-y-4">
      {/* Advance to publish */}
      {onAdvance && includedPackageItems.length > 0 ? (
        <div className="flex items-center justify-between rounded-lg border border-border bg-surface-2 px-4 py-3">
          <div className="text-sm text-content-muted">
            <span className="font-semibold text-content">{includedPackageItems.length}</span> creative{includedPackageItems.length !== 1 ? "s" : ""} ready to publish
          </div>
          <Button variant="primary" size="sm" onClick={onAdvance}>
            Continue to Publish &rarr;
          </Button>
        </div>
      ) : null}

      {creativeSpecCount === 0 ? (
        <Callout variant="warning" size="sm">
          Prepare Meta review before running QA. No creative specs exist yet.
        </Callout>
      ) : null}

      <CampaignPaidAdsQaCard
        campaign={campaign}
        generationKey={latestGenerationKey}
        generationLabel={latestGenerationSummary?.label ?? null}
        funnelId={activeFunnelId}
        funnelLabel={activeFunnelLabel}
        enabled={canPrepareMetaReview}
        reviewBaseUrl={reviewBaseUrl}
        requiresFunnelScope={requiresFunnelScope}
      />

    </div>
  );
}
