import type { CompanySwipeAsset } from "@/types/swipes";
import type { AssetReviewItem, ReviewStatus } from "@/types/assetReview";
import {
  resolveSwipeAssetType,
  mapSwipePlatforms,
  mapSwipeImages,
  mapSwipeVideos,
  mapSwipeStoredMedia,
} from "@/lib/library";

function extractHostname(url?: string | null): string | undefined {
  if (!url) return undefined;
  try {
    return new URL(url).hostname;
  } catch {
    return undefined;
  }
}

/**
 * Strip HTML tags and decode common HTML entities so card previews
 * render clean plain text instead of raw markup.
 *
 * Decodes entities FIRST so that double-encoded tags like
 * `&lt;br /&gt;` become real tags before the strip pass.
 */
function stripHtml(raw: string): string {
  // 1. Decode HTML entities first (handles double-encoded markup)
  let text = raw
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ");
  // 2. Now strip all tags (including freshly-decoded ones)
  text = text
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/<[^>]+>/g, "");
  // 3. Collapse runs of whitespace
  text = text.replace(/\s{2,}/g, " ").trim();
  return text;
}

function toReviewStatus(raw?: string): ReviewStatus {
  switch (raw) {
    case "approved":
      return "approved";
    case "rejected":
      return "rejected";
    case "stale_after_sync":
      return "stale_after_sync";
    default:
      return "pending_review";
  }
}

/**
 * Normalizes a CompanySwipeAsset into an AssetReviewItem for use in the shared review grid.
 *
 * IMPORTANT: Uses swipe.id (internal ID) as the normalized id, not external_ad_id,
 * because bulk action APIs (approve/reject/markPending) require internal IDs.
 */
export function normalizeSwipeToAssetReviewItem(swipe: CompanySwipeAsset): AssetReviewItem {
  const snapshot =
    (swipe as any)?.snapshot ||
    (swipe as any)?.ad_library_object?.snapshot ||
    swipe.ad_library_object ||
    {};

  const title = snapshot?.title || swipe.title;
  const pageName = snapshot?.page_name || title || "Saved swipe";

  const snapshotBody = snapshot?.body;
  const body =
    typeof snapshotBody?.text === "string"
      ? snapshotBody.text
      : typeof snapshotBody === "string"
      ? snapshotBody
      : typeof swipe.body === "string"
      ? swipe.body
      : undefined;

  const ctaText = snapshot?.cta_text || swipe.cta_text;
  const destinationUrl = snapshot?.link_url || swipe.landing_page || swipe.ad_source_link;

  const snapshotImages = mapSwipeImages(snapshot, title || pageName);
  const snapshotVideos = mapSwipeVideos(snapshot, snapshotImages[0]?.thumbUrl);
  const storedMedia = mapSwipeStoredMedia(swipe.media, title || pageName);

  const media = [...snapshotVideos, ...snapshotImages];
  if (storedMedia.length) {
    media.push(...storedMedia);
  }

  const platform = mapSwipePlatforms(swipe, snapshot);

  return {
    id: swipe.id,
    kind: "swipe",
    brandName: pageName ? stripHtml(pageName) : pageName,
    headline: title ? stripHtml(title) : title,
    body: body ? stripHtml(body) : body,
    ctaText: ctaText ? stripHtml(ctaText) : ctaText,
    media,
    platform,
    reviewStatus: toReviewStatus(swipe.review_status),
    reviewedAt: swipe.reviewed_at,
    source: "gethookd",
    sourceFirstSeenAt: swipe.source_first_seen_at,
    sourceLastSeenAt: swipe.source_last_seen_at,
    sourceLastSyncedAt: swipe.source_last_synced_at,
    performanceScore: swipe.performance_score,
    daysActive: swipe.days_active,
    usedCount: swipe.used_count,
    collectionIds: [],
    isInLaunchCollection: false,
    destinationUrl,
    destinationHostname: extractHostname(destinationUrl),
    assetType: resolveSwipeAssetType(swipe),
    status: swipe.active === true ? "active" : swipe.active === false ? "inactive" : undefined,
    raw: swipe,
  };
}
