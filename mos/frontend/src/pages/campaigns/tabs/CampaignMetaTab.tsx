import { MetaPublishWorkspace } from "@/components/campaigns/meta";
import { useCampaignContext } from "@/contexts/CampaignContext";

export function CampaignMetaTab() {
  const { campaign, assetBriefs } = useCampaignContext();

  return <MetaPublishWorkspace campaign={campaign} assetBriefs={assetBriefs} />;
}
