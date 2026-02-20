export interface Product {
  id: string;
  org_id: string;
  client_id: string;
  title: string;
  description?: string | null;
  product_type?: string | null;
  handle?: string | null;
  vendor?: string | null;
  tags: string[];
  template_suffix?: string | null;
  published_at?: string | null;
  shopify_product_gid?: string | null;
  primary_benefits: string[];
  feature_bullets: string[];
  guarantee_text?: string | null;
  disclaimers: string[];
  primary_asset_id?: string | null;
  primary_asset_url?: string | null;
  created_at: string;
}

export interface ProductVariant {
  id: string;
  offer_id?: string | null;
  product_id?: string | null;
  title: string;
  price: number;
  currency: string;
  provider?: string | null;
  external_price_id?: string | null;
  option_values?: Record<string, unknown> | null;
  compare_at_price?: number | null;
  sku?: string | null;
  barcode?: string | null;
  requires_shipping?: boolean;
  taxable?: boolean;
  weight?: number | string | null;
  weight_unit?: string | null;
  inventory_quantity?: number | null;
  inventory_policy?: string | null;
  inventory_management?: string | null;
  incoming?: boolean | null;
  next_incoming_date?: string | null;
  unit_price?: number | null;
  unit_price_measurement?: Record<string, unknown> | null;
  quantity_rule?: Record<string, unknown> | null;
  quantity_price_breaks?: Record<string, unknown>[] | null;
  shopify_last_synced_at?: string | null;
  shopify_last_sync_error?: string | null;
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
  expires_at?: string | null;
  download_url?: string | null;
  is_primary: boolean;
}

export interface ProductOfferBonusProduct {
  id: string;
  title: string;
  description?: string | null;
  product_type?: string | null;
  shopify_product_gid?: string | null;
}

export interface ProductOfferBonus {
  id: string;
  position: number;
  created_at: string;
  bonus_product: ProductOfferBonusProduct;
}

export interface ProductOffer {
  id: string;
  org_id: string;
  client_id: string;
  product_id?: string | null;
  name: string;
  description?: string | null;
  business_model: string;
  differentiation_bullets: string[];
  guarantee_text?: string | null;
  options_schema?: Record<string, unknown> | null;
  created_at: string;
  bonuses: ProductOfferBonus[];
}

export interface CreativeBriefAssetGroup {
  assetBriefId: string;
  assets: ProductAsset[];
}

export interface ProductDetail extends Product {
  variants: ProductVariant[];
  assets: ProductAsset[];
  creative_brief_assets: CreativeBriefAssetGroup[];
  offers: ProductOffer[];
}
