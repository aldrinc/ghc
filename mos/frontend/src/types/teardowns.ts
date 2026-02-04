export interface Teardown {
  id: string;
  org_id: string;
  creative_id: string;
  brand_id?: string;
  brand_name?: string;
  channel?: string;
  creative_fingerprint?: string;
  primary_media_asset_url?: string;
  client_id?: string;
  campaign_id?: string;
  research_run_id?: string;
  schema_version: number;
  captured_at?: string;
  funnel_stage?: string;
  one_liner?: string;
  algorithmic_thesis?: string;
  hook_score?: number;
  raw_payload: Record<string, unknown>;
  is_canonical: boolean;
  created_at?: string;
  updated_at?: string;
}
