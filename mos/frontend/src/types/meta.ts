export type MetaCreativeSpec = {
  id: string;
  asset_id: string;
  campaign_id?: string | null;
  experiment_id?: string | null;
  name?: string | null;
  primary_text?: string | null;
  headline?: string | null;
  description?: string | null;
  call_to_action_type?: string | null;
  destination_url?: string | null;
  page_id?: string | null;
  instagram_actor_id?: string | null;
  status?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type MetaAdSetSpec = {
  id: string;
  campaign_id?: string | null;
  experiment_id?: string | null;
  name?: string | null;
  status?: string | null;
  optimization_goal?: string | null;
  billing_event?: string | null;
  targeting?: Record<string, unknown> | null;
  placements?: Record<string, unknown> | null;
  daily_budget?: number | null;
  lifetime_budget?: number | null;
  bid_amount?: number | null;
  start_time?: string | null;
  end_time?: string | null;
  promoted_object?: Record<string, unknown> | null;
  conversion_domain?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type MetaAssetUpload = {
  id: string;
  asset_id: string;
  media_type?: string | null;
  meta_image_hash?: string | null;
  meta_video_id?: string | null;
  status?: string | null;
  created_at?: string;
};

export type MetaAdCreative = {
  id: string;
  asset_id?: string | null;
  meta_creative_id: string;
  name?: string | null;
  status?: string | null;
  created_at?: string;
};

export type MetaAd = {
  id: string;
  meta_ad_id: string;
  meta_adset_id: string;
  meta_creative_id: string;
  name?: string | null;
  status?: string | null;
  created_at?: string;
};

export type MetaCampaign = {
  id: string;
  meta_campaign_id: string;
  name?: string | null;
  objective?: string | null;
  status?: string | null;
  created_at?: string;
};

export type MetaPipelineAsset = {
  asset: {
    id: string;
    public_id: string;
    status?: string | null;
    asset_kind?: string | null;
    client_id?: string | null;
    campaign_id?: string | null;
    experiment_id?: string | null;
    asset_brief_artifact_id?: string | null;
    file_status?: string | null;
    content_type?: string | null;
    width?: number | null;
    height?: number | null;
    created_at?: string;
    public_url?: string | null;
  };
  campaign?: { id: string; name: string } | null;
  experiment?: { id: string; name: string } | null;
  creative_spec?: MetaCreativeSpec | null;
  adset_specs?: MetaAdSetSpec[];
  meta?: {
    upload?: MetaAssetUpload | null;
    creatives?: MetaAdCreative[];
    ads?: MetaAd[];
    meta_campaign?: MetaCampaign | null;
  };
};

export type MetaRemoteResponse<T> = {
  data: T[];
  paging?: Record<string, unknown>;
};

export type MetaRemoteImage = {
  hash: string;
  name?: string | null;
  url?: string | null;
  created_time?: string | null;
  updated_time?: string | null;
};

export type MetaRemoteVideo = {
  id: string;
  title?: string | null;
  status?: string | null;
  length?: number | null;
  created_time?: string | null;
  updated_time?: string | null;
  thumbnail_url?: string | null;
  source?: string | null;
};

export type MetaRemoteCreative = {
  id: string;
  name?: string | null;
  status?: string | null;
  object_story_spec?: Record<string, unknown> | null;
  created_time?: string | null;
  updated_time?: string | null;
};

export type MetaRemoteCampaign = {
  id: string;
  name?: string | null;
  status?: string | null;
  effective_status?: string | null;
  objective?: string | null;
  created_time?: string | null;
  updated_time?: string | null;
};

export type MetaRemoteAdSet = {
  id: string;
  name?: string | null;
  status?: string | null;
  effective_status?: string | null;
  campaign_id?: string | null;
  created_time?: string | null;
  updated_time?: string | null;
};

export type MetaRemoteAd = {
  id: string;
  name?: string | null;
  status?: string | null;
  effective_status?: string | null;
  adset_id?: string | null;
  campaign_id?: string | null;
  creative?: { id?: string } | null;
  created_time?: string | null;
  updated_time?: string | null;
};
