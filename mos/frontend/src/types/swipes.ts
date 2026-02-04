export interface CompanySwipeAsset {
  id: string;
  org_id: string;
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
  active?: boolean;
  active_in_library?: boolean;
  ad_library_object?: Record<string, any>;
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
