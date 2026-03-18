import type { ComponentType } from "react";

/** Supported ad platform identifiers. */
export type AdPlatformId = "meta" | "tiktok" | "bing" | "google_ads";

/** Common props for platform-specific feed preview renderers. */
export interface PlatformPreviewProps {
  imageUrl: string | null;
  imageAlt: string;
  primaryText?: string | null;
  headline?: string | null;
  description?: string | null;
  cta?: string | null;
  destinationUrl?: string | null;
  specReady: boolean;
}

/** A component type that renders a platform feed preview. */
export type PlatformPreviewRenderer = ComponentType<PlatformPreviewProps>;

/**
 * Adapter interface for ad platform integrations.
 *
 * Each platform (Meta, TikTok, Bing, etc.) implements this interface
 * to plug into the publish workflow.
 */
export interface AdPlatformAdapter {
  id: AdPlatformId;
  label: string;
  FeedPreview: PlatformPreviewRenderer;
  PublishPanel: ComponentType<{ campaignId: string }>;
  PublishRunsList: ComponentType<{ campaignId: string }>;
}

/** Static definition of a supported ad platform. */
export interface AdPlatformDefinition {
  id: AdPlatformId;
  label: string;
  supportedCreativeFormats: string[];
  requiresDestinationUrl: boolean;
}

export const AD_PLATFORM_DEFINITIONS: Record<AdPlatformId, AdPlatformDefinition> = {
  meta: {
    id: "meta",
    label: "Meta Ads",
    supportedCreativeFormats: ["image", "video", "carousel"],
    requiresDestinationUrl: true,
  },
  tiktok: {
    id: "tiktok",
    label: "TikTok Ads",
    supportedCreativeFormats: ["video", "image"],
    requiresDestinationUrl: true,
  },
  bing: {
    id: "bing",
    label: "Bing Ads",
    supportedCreativeFormats: ["image"],
    requiresDestinationUrl: true,
  },
  google_ads: {
    id: "google_ads",
    label: "Google Ads",
    supportedCreativeFormats: ["image", "video"],
    requiresDestinationUrl: true,
  },
};
