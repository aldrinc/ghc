import type { AdPlatformAdapter } from "@/types/adPlatform";
import { MetaFeedPreview } from "./MetaFeedPreview";
import { MetaPublishPanel } from "./MetaPublishPanel";
import { MetaPublishRunsList } from "./MetaPublishRunsList";

/**
 * Meta Ads platform adapter.
 * Implements AdPlatformAdapter to plug into the publish workflow.
 */
export const MetaAdapter: AdPlatformAdapter = {
  id: "meta",
  label: "Meta Ads",
  FeedPreview: MetaFeedPreview,
  PublishPanel: MetaPublishPanel,
  PublishRunsList: MetaPublishRunsList,
};
