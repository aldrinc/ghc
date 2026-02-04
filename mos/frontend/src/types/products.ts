export interface Product {
  id: string;
  org_id: string;
  client_id: string;
  name: string;
  description?: string | null;
  category?: string | null;
  primary_benefits: string[];
  feature_bullets: string[];
  guarantee_text?: string | null;
  disclaimers: string[];
  primary_asset_id?: string | null;
  primary_asset_url?: string | null;
  created_at: string;
}

export interface ProductOffer {
  id: string;
  org_id: string;
  client_id: string;
  product_id: string | null;
  name: string;
  description?: string | null;
  business_model: string;
  differentiation_bullets: string[];
  guarantee_text?: string | null;
  options_schema?: Record<string, unknown> | null;
  created_at: string;
  pricePoints?: ProductOfferPricePoint[];
}

export interface ProductOfferPricePoint {
  id: string;
  offer_id: string;
  label: string;
  amount_cents: number;
  currency: string;
  provider?: string | null;
  external_price_id?: string | null;
  option_values?: Record<string, unknown> | null;
}

export interface ProductDetail extends Product {
  offers: ProductOffer[];
}

export interface ProductAsset {
  id: string;
  org_id: string;
  client_id: string;
  product_id?: string | null;
  public_id: string;
  asset_kind: string;
  channel_id: string;
  format: string;
  content: Record<string, unknown>;
  storage_key?: string | null;
  content_type?: string | null;
  size_bytes?: number | null;
  width?: number | null;
  height?: number | null;
  alt?: string | null;
  file_source?: string | null;
  file_status?: string | null;
  ai_metadata?: Record<string, unknown> | null;
  tags: string[];
  created_at: string;
  download_url?: string | null;
  is_primary: boolean;
}
