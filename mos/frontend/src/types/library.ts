export type MediaAssetStatus = "pending" | "succeeded" | "failed" | "partial";

export type MediaAsset =
  | {
      type: "image";
      url: string;
      thumbUrl?: string;
      fullUrl?: string;
      alt?: string;
      status?: MediaAssetStatus;
    }
  | {
      type: "video";
      url: string;
      thumbUrl?: string;
      posterUrl?: string;
      fullUrl?: string;
      status?: MediaAssetStatus;
    };

export type LibraryItemKind = "ad" | "teardown" | "swipe";

export type LibraryItem = {
  id: string;
  kind: LibraryItemKind;
  brandName: string;
  brandAvatarUrl?: string;
  platform?: string[];
  status?: "active" | "inactive" | "unknown";
  startAt?: string;
  endAt?: string;
  capturedAt?: string;
  headline?: string;
  body?: string;
  ctaText?: string;
  destinationUrl?: string;
  hookScore?: number;
  funnelStage?: string;
  media: MediaAsset[];
  /**
   * Raw payload from the API. Used to show the full ad record in detail view.
   * Keep as `unknown` to avoid accidental coupling to a specific API shape.
   */
  raw?: unknown;
  scores?: {
    performanceScore?: number;
    performanceStars?: number;
    winningScore?: number;
    confidence?: number;
    scoreVersion?: string;
  };
};
