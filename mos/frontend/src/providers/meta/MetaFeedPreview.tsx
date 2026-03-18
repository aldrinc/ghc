// Re-export the canonical MetaFeedPreview from the campaigns module.
// The provider adapter references this file but the implementation
// lives in campaigns/meta to avoid duplication.
export { MetaFeedPreview } from "@/components/campaigns/meta/MetaFeedPreview";
