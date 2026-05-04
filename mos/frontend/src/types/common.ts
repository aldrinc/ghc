import type { AssetBriefType } from "@/lib/assetBriefTypes";

export interface Client {
  id: string;
  org_id: string;
  name: string;
  industry?: string;
  design_system_id?: string | null;
}

export interface Campaign {
  id: string;
  org_id: string;
  client_id: string;
  product_id?: string | null;
  name: string;
  channels?: string[];
  asset_brief_types?: AssetBriefType[];
  default_swipe_collection_id?: string | null;
}

export interface CampaignSwipeDefault {
  swipeCollectionId: string | null;
  swipeCollectionName: string | null;
  readySwipeCount: number;
}

export interface GetHookdCredentials {
  hasCredentials: boolean;
  lastValidatedAt?: string | null;
  lastValidationError?: string | null;
}

export interface PostizCredentials {
  hasCredentials: boolean;
  baseUrl?: string | null;
  authType?: string | null;
  lastValidatedAt?: string | null;
  lastValidationError?: string | null;
}

export interface PostizBrowserLaunchSession {
  launchUrl: string;
  autoConfiguredCredentials: boolean;
}

export interface PostizChannel {
  id: string;
  postizIntegrationId: string;
  postizChannelId: string;
  identifier: string;
  name: string;
  profile?: string | null;
  pictureUrl?: string | null;
  disabled: boolean;
  isDefault: boolean;
  metadata: Record<string, unknown>;
  lastSyncedAt?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface PostizPostingProfile {
  id: string;
  name: string;
  isDefault: boolean;
  defaultChannelIds: string[];
  timezone?: string | null;
  shortLink?: boolean | null;
  providerSettings: Record<string, unknown>;
  postizPostingProfileId?: string | null;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface PostizPostingProfileInput {
  name: string;
  isDefault?: boolean;
  defaultChannelIds?: string[];
  timezone?: string | null;
  shortLink?: boolean | null;
  providerSettings?: Record<string, unknown>;
}

export interface PostizPostingProfileUpdateInput extends Partial<PostizPostingProfileInput> {}

export interface PostizPublication {
  id: string;
  postizPostId?: string | null;
  postizPostIds?: string[];
  content: string;
  postType: string;
  scheduledFor?: string | null;
  targetChannels: Record<string, unknown>;
  mediaUrls: string[];
  linkUrl?: string | null;
  status: string;
  postizPostStatus?: string | null;
  releaseUrls: string[];
  errorPayload?: Record<string, unknown> | null;
  lastSyncedAt?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface PostizPublicationListResponse {
  posts: PostizPublication[];
  total: number;
}

export interface PostizCreatePostInput {
  content: string;
  postType: "now" | "schedule" | "draft";
  scheduledFor?: string | null;
  channelIds: string[];
  mediaUrls?: string[];
  linkUrl?: string | null;
  postingProfileId?: string | null;
  providerSettingsByIdentifier?: Record<string, unknown>;
}

export interface GetHookdSyncFeedFilters {
  query?: string;
  sort_column?: "created_at" | "start_date" | "days_active" | "used_count";
  sort_direction?: "asc" | "desc";
  start_date?: string;
  end_date?: string;
  status?: "active" | "inactive";
  ad_format?: string;
  run_time?: number;
  language?: string;
  platform?: string;
  niche?: string;
  location?: string;
  performance_scores?: string;
  used_count?: number;
  video_lengths?: string;
  eu_transparency?: number;
  eu_total_reach?: number;
  gender_audience?: string;
  age_audience?: string;
  ad_spend_range?: string;
  excluded_brands?: string;
  creative_categories?: string;
  cta_types?: string;
  ads_per_brand_limit?: number;
  active_ads_count?: number;
  platforms?: string;
}

export interface GetHookdSyncFeed {
  id: string;
  name: string;
  enabled: boolean;
  filters: GetHookdSyncFeedFilters;
  maxPagesPerRun: number;
  perPage: number;
  createdAt: string;
  updatedAt: string;
}

export interface GetHookdSyncFeedInput {
  name: string;
  enabled?: boolean;
  filters: GetHookdSyncFeedFilters;
  maxPagesPerRun?: number;
  perPage?: number;
}

export interface GetHookdSyncFeedUpdateInput extends Partial<GetHookdSyncFeedInput> {}

export interface WorkflowRun {
  id: string;
  org_id: string;
  client_id?: string | null;
  product_id?: string | null;
  campaign_id?: string | null;
  temporal_workflow_id: string;
  temporal_run_id: string;
  kind: string;
  status: string;
  started_at: string;
  finished_at?: string | null;
}

export interface PendingActivityProgress {
  activity_id: string;
  activity_type: string;
  state?: string | null;
  attempt?: number;
  last_worker_identity?: string;
  last_started_time?: string | null;
  last_heartbeat_time?: string | null;
  scheduled_time?: string | null;
  expiration_time?: string | null;
  heartbeat_progress?: Record<string, unknown> | null;
}

export interface StrategyV2State {
  workflow_run_id?: string;
  current_stage?: string;
  pending_signal_type?: string | null;
  required_signal_type?: string | null;
  pending_decision_payload?: Record<string, unknown> | null;
  scored_candidate_summaries?: Record<string, unknown> | null;
  artifact_refs?: Record<string, string> | null;
}

export interface StrategyV2LaunchRecord {
  id: string;
  launch_type: "initial_angle" | "additional_ums" | "additional_angle";
  launch_key: string;
  campaign_id?: string | null;
  funnel_id?: string | null;
  angle_id: string;
  angle_run_id: string;
  selected_ums_id?: string | null;
  selected_variant_id?: string | null;
  launch_index?: number | null;
  launch_workflow_run_id?: string | null;
  launch_temporal_workflow_id?: string | null;
  launch_status?: string | null;
  created_by_user?: string | null;
  created_at: string;
}

export interface ActivityLog {
  id: string;
  workflow_run_id: string;
  step: string;
  status: string;
  payload_in?: Record<string, unknown> | null;
  payload_out?: Record<string, unknown> | null;
  error?: string | null;
  created_at: string;
}

export interface Artifact {
  id: string;
  org_id: string;
  client_id: string;
  product_id?: string | null;
  campaign_id?: string | null;
  type: string;
  version: number;
  data: Record<string, unknown>;
  created_by_user?: string | null;
  created_at: string;
}

export interface Asset {
  id: string;
  org_id: string;
  client_id: string;
  campaign_id?: string | null;
  experiment_id?: string | null;
  product_id?: string | null;
  funnel_id?: string | null;
  public_id: string;
  asset_kind: string;
  channel_id: string;
  format: string;
  status: string;
  storage_key?: string | null;
  content_type?: string | null;
  width?: number | null;
  height?: number | null;
  file_status?: string | null;
  created_at: string;
  tags?: string[];
}

export interface ResearchArtifactRef {
  step_key: string;
  title?: string;
  doc_url: string;
  doc_id: string;
  summary?: string;
  content?: unknown;
}

export interface Experiment {
  id: string;
  org_id: string;
  client_id: string;
  campaign_id: string;
  name: string;
  status?: string;
  experiment_spec_artifact_id?: string;
  created_at?: string;
}

export interface WorkflowDetail {
  run: WorkflowRun;
  logs: ActivityLog[];
  client_canon?: Artifact | null;
  metric_schema?: Artifact | null;
  strategy_sheet?: Artifact | null;
  experiment_specs?: Artifact[] | null;
  asset_briefs?: Artifact[] | null;
  precanon_research?: Record<string, unknown> | null;
  research_artifacts?: ResearchArtifactRef[] | null;
  research_highlights?: Record<string, unknown> | null;
  temporal_status?: string | null;
  pending_activity_progress?: PendingActivityProgress[] | null;
  strategy_v2_state?: StrategyV2State | null;
  strategy_v2_stage3?: Artifact | null;
  strategy_v2_offer?: Artifact | null;
  strategy_v2_copy?: Artifact | null;
  strategy_v2_copy_canonical?: Record<string, unknown> | null;
  strategy_v2_copy_context?: Artifact | null;
  strategy_v2_awareness_angle_matrix?: Artifact | null;
  strategy_v2_launches?: StrategyV2LaunchRecord[] | null;
}
