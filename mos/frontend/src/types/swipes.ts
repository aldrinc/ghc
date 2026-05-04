export type SwipeAssetType = "image" | "video" | "carousel" | "unknown";
export type SwipeAssetTypeFilter = SwipeAssetType | "all";

export interface CompanySwipeAsset {
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
  share_url?: string;
  brand_id?: string;
  external_ad_id?: string;
  external_platform_ad_id?: string;
  days_active?: number;
  used_count?: number;
  performance_score?: number;
  performance_score_data?: Record<string, any>;
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
  review_status?: "pending_review" | "approved" | "rejected" | "stale_after_sync" | string;
  reviewed_at?: string;
  reviewed_by_user_id?: string;
  source_first_seen_at?: string;
  source_last_seen_at?: string;
  source_last_synced_at?: string;
  source_payload_hash?: string;
  source_content_changed_at?: string;
  source_metadata_json?: Record<string, any>;
  active?: boolean;
  active_in_library?: boolean;
  ad_library_object?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
  snapshot?: Record<string, any>;
  extra_texts?: any[];
  media?: CompanySwipeMedia[];
}

export interface ClientSwipeAsset {
  id: string;
  org_id: string;
  client_id: string;
  company_swipe_id?: string;
  tags: string[];
  custom_title?: string;
  custom_body?: string;
  custom_channel?: string;
  custom_format?: string;
}

export interface CompanySwipeMedia {
  id: string;
  org_id: string;
  swipe_asset_id: string;
  media_asset_id?: string;
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
}

export interface SwipeCollection {
  id: string;
  org_id: string;
  name: string;
  kind: string;
  cloned_from_collection_id?: string | null;
  created_by_user_id?: string | null;
  created_at: string;
  writable: boolean;
  item_count: number;
  analysis_counts: Record<string, number>;
}

export interface SwipeCollectionDetail extends SwipeCollection {
  swipes: CompanySwipeAsset[];
}

export interface SwipeCollectionCreateRequest {
  name: string;
  kind: "uploaded" | "curated";
}

export interface SwipeCollectionCloneRequest {
  name: string;
}

export interface SwipeCollectionItemsRequest {
  swipeAssetIds: string[];
}

export interface SwipeReviewFilter {
  source?: "gethookd" | "all";
  reviewStatus?: "pending" | "approved" | "rejected" | "stale" | "all";
  search?: string;
  collectionId?: string;
  clientId?: string;
  changedSince?: "last_sync" | "last_7_days" | "all";
  notInLaunchCollection?: boolean;
}

export interface SwipeReviewBulkRequest {
  swipeAssetIds: string[];
  collectionId?: string;
}

export interface GetHookdInboxSummary {
  latestRunId?: string | null;
  latestRunStartedAt?: string | null;
  rawImportedCount: number;
  eligibleStaticImageCount: number;
  duplicateCollapsedCount: number;
  excludedNonStaticCount: number;
  reviewLimit: number;
  returnedCount: number;
  defaultAssetType: SwipeAssetType;
}

export interface GetHookdInboxResponse {
  summary: GetHookdInboxSummary;
  swipes: CompanySwipeAsset[];
}
