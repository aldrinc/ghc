/**
 * Asset review types for shared review components.
 * These types support GetHookd swipe review, creative review, and library review.
 */

import type { MediaAsset } from "./library";

export type ReviewStatus = "pending_review" | "approved" | "rejected" | "stale_after_sync";

export type AssetSource = "gethookd" | "upload" | "catalog" | "unknown";

export type PerformanceTier = "winning" | "optimized" | "active" | "inactive";

/**
 * Normalized asset review item for use in review grids.
 * This is intentionally generic to support swipes, creative assets, and library items.
 */
export interface AssetReviewItem {
  id: string;
  kind: "swipe" | "ad" | "creative";
  
  // Display
  brandName: string;
  brandAvatarUrl?: string;
  headline?: string;
  body?: string;
  ctaText?: string;
  media: MediaAsset[];
  
  // Platform/Channel
  platform: string[];
  channel?: string;
  
  // Review metadata
  reviewStatus: ReviewStatus;
  reviewedAt?: string;
  reviewedBy?: string;
  
  // Source metadata
  source: AssetSource;
  sourceFirstSeenAt?: string;
  sourceLastSeenAt?: string;
  sourceLastSyncedAt?: string;
  
  // Performance metadata (GetHookd specific)
  performanceScore?: number;
  performanceTier?: PerformanceTier;
  daysActive?: number;
  usedCount?: number;
  
  // Collection membership
  collectionIds: string[];
  isInLaunchCollection: boolean;
  
  // Landing/destination
  destinationUrl?: string;
  destinationHostname?: string;
  
  // Status
  status?: "active" | "inactive" | "unknown";
  
  // Raw payload for detail view
  raw?: unknown;
}

/**
 * Filter state for asset review grids.
 */
export interface AssetReviewFilterState {
  search: string;
  reviewStatus: ReviewStatus | "all";
  source: AssetSource | "all";
  inLaunchCollection: boolean | null; // null = all, true = in launch, false = not in launch
  changedSince: "last_sync" | "last_7_days" | "all";
  platform: string | "all";
}

/**
 * Bulk action types for asset review.
 */
export type AssetReviewBulkAction = 
  | { type: "add_to_collection"; collectionIds: string[] }
  | { type: "reject" }
  | { type: "mark_pending" };

/**
 * Campaign swipe default response from backend.
 */
export interface CampaignSwipeDefault {
  swipeCollectionId: string | null;
  swipeCollectionName: string | null;
  readySwipeCount: number;
}

/**
 * GetHookd credential status (token is never exposed).
 */
export interface GetHookdCredentialStatus {
  configured: boolean;
  lastValidatedAt?: string;
  lastValidationError?: string;
}

/**
 * GetHookd sync feed definition.
 */
export interface GetHookdSyncFeed {
  id: string;
  clientId: string;
  name: string;
  enabled: boolean;
  filters: {
    query?: string;
    platforms?: string[];
    niche?: string;
    adFormat?: string;
    location?: string;
    language?: string;
    performanceScores?: PerformanceTier[];
    status?: string;
    sortColumn?: string;
    sortDirection?: "asc" | "desc";
  };
  maxPagesPerRun: number;
  perPage: number;
  createdAt: string;
  updatedAt: string;
}

/**
 * Request to create/update a GetHookd sync feed.
 */
export interface GetHookdSyncFeedRequest {
  name: string;
  enabled: boolean;
  filters: {
    query?: string;
    platforms?: string[];
    niche?: string;
    adFormat?: string;
    location?: string;
    language?: string;
    performanceScores?: PerformanceTier[];
    status?: string;
    sortColumn?: string;
    sortDirection?: "asc" | "desc";
  };
  maxPagesPerRun: number;
  perPage: number;
}

/**
 * Extended company swipe asset with review metadata.
 * This extends the base CompanySwipeAsset with GetHookd-specific fields.
 */
export interface CompanySwipeAssetWithReview {
  id: string;
  org_id: string;
  source_kind?: string;
  origin_system?: string;
  title?: string;
  body?: string;
  platforms?: string;
  cta_type?: string;
  cta_text?: string;
  display_format?: string;
  landing_page?: string;
  link_description?: string;
  ad_source_link?: string;
  brand_id?: string;
  external_ad_id?: string;
  external_platform_ad_id?: string;
  analysis_status?: string;
  analysis_error?: string;
  analysis_model?: string;
  analysis_updated_at?: string;
  ad_unit_format?: string;
  placement_shape?: string;
  channel?: string;
  destination_type?: string;
  funnel_stage?: string;
  angle_family?: string;
  hook_type?: string;
  visual_archetype?: string;
  product_presence?: string;
  proof_type?: string;
  claim_risk?: string;
  product_image_policy?: string;
  active?: boolean;
  active_in_library?: boolean;
  ad_library_object?: Record<string, any>;
  snapshot?: Record<string, any>;
  extra_texts?: any[];
  media?: CompanySwipeMediaWithReview[];
  
  // Review metadata
  review_status?: ReviewStatus;
  reviewed_at?: string;
  reviewed_by_user_id?: string;
  
  // Source tracking
  source_first_seen_at?: string;
  source_last_seen_at?: string;
  source_last_synced_at?: string;
  source_payload_hash?: string;
  source_content_changed_at?: string;
  source_metadata_json?: Record<string, any>;
  
  // Performance metadata
  performance_score?: number;
  days_active?: number;
  used_count?: number;
  
  // Collection membership
  collection_ids?: string[];
}

export interface CompanySwipeMediaWithReview {
  id: string;
  org_id: string;
  swipe_asset_id: string;
  external_media_id?: string;
  path?: string;
  url?: string;
  thumbnail_path?: string;
  thumbnail_url?: string;
  disk?: string;
  type?: string;
  mime_type?: string;
  size_bytes?: number;
  video_length?: number;
  download_url?: string;
  media_asset_id?: string;
}
