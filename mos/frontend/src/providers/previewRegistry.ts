import type { AdPlatformId, PlatformPreviewRenderer } from "@/types/adPlatform";
import { MetaFeedPreview } from "./meta/MetaFeedPreview";

/**
 * Maps ad platform IDs to their feed preview components.
 *
 * To add a new platform preview, import the component and add it here.
 * The Creative tab uses this to render the correct preview per ad.
 */
export const previewRenderers: Partial<Record<AdPlatformId, PlatformPreviewRenderer>> = {
  meta: MetaFeedPreview,
  // tiktok: TikTokFeedPreview,  // Future
  // bing: BingSearchPreview,     // Future
};

export function getPreviewRenderer(platform: AdPlatformId): PlatformPreviewRenderer | null {
  return previewRenderers[platform] ?? null;
}
