import { MetaPublishWorkspace } from "@/components/campaigns/meta";
import { useCampaignContext } from "@/contexts/CampaignContext";

/**
 * Meta-specific publish panel.
 * Delegates to the refactored MetaPublishWorkspace with stepper-driven layout.
 */
export function MetaPublishPanel({ campaignId }: { campaignId: string }) {
  const { campaign, assetBriefs } = useCampaignContext();

  return <MetaPublishWorkspace campaign={campaign} assetBriefs={assetBriefs} />;
}
