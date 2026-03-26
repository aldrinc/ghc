export type FunnelStatus = "draft" | "published" | "disabled" | "archived";

import type { DesignSystemTokens } from "@/types/designSystems";
import type { MedusaRuntimeConfig } from "@/lib/medusa/config";

export type Funnel = {
  id: string;
  org_id: string;
  client_id: string;
  product_id?: string | null;
  selected_offer_id?: string | null;
  campaign_id: string | null;
  experiment_spec_id?: string | null;
  design_system_id?: string | null;
  name: string;
  description: string | null;
  status: FunnelStatus;
  route_slug: string;
  public_id: string;
  entry_page_id: string | null;
  active_publication_id: string | null;
  created_at: string;
  updated_at: string;
};

export type FunnelPage = {
  id: string;
  funnel_id: string;
  name: string;
  slug: string;
  next_page_id?: string | null;
  template_id?: string | null;
  design_system_id?: string | null;
  ordering: number;
  created_at: string;
  updated_at: string;
  latestDraftVersionId?: string | null;
  latestApprovedVersionId?: string | null;
};

export type FunnelDetail = Funnel & {
  pages: FunnelPage[];
  canPublish: boolean;
};

export type FunnelPageVersionStatus = "draft" | "approved";

export type FunnelPageVersion = {
  id: string;
  page_id: string;
  status: FunnelPageVersionStatus;
  puck_data: unknown;
  source: string;
  ai_metadata: unknown | null;
  created_at: string;
};

export type FunnelPageDetail = {
  page: FunnelPage;
  latestDraft: FunnelPageVersion | null;
  latestApproved: FunnelPageVersion | null;
  designSystemTokens?: DesignSystemTokens | null;
};

export type PublicFunnelMeta = {
  productSlug: string;
  funnelSlug: string;
  funnelId: string;
  publicationId: string;
  entrySlug: string;
  pages: { pageId: string; slug: string }[];
  medusaRuntimeConfig?: MedusaRuntimeConfig | null;
};

export type PublicFunnelStage = "pre_sales" | "sales" | "checkout" | "thank_you" | "custom";

// Site page types for commerce experiences
export type SitePageType =
  | "home"
  | "store"
  | "collection"
  | "category"
  | "product_detail"
  | "cart"
  | "checkout"
  | "account_dashboard"
  | "account_profile"
  | "account_addresses"
  | "account_orders"
  | "account_order_detail"
  | "order_confirmed"
  | "order_transfer"
  | "order_transfer_accept"
  | "order_transfer_decline";

export type PublicFunnelPage = {
  productSlug: string;
  funnelId: string;
  publicationId: string;
  pageId: string;
  slug: string;
  stage: PublicFunnelStage;
  puckData: unknown;
  pageMap: Record<string, string>;
  pageStageMap: Record<string, PublicFunnelStage>;
  pageTypeMap?: Record<string, SitePageType>;
  designSystemTokens?: DesignSystemTokens | null;
  metadata?: {
    title: string;
    description: string;
    lang: string;
    brandName?: string | null;
  };
  tracking?: {
    provider: string;
    mode: string;
    metaPixelId?: string | null;
  } | null;
  nextPageId?: string | null;
  redirectToSlug?: string;
};

export type FunnelImageAsset = {
  assetId: string;
  publicId: string;
  width: number | null;
  height: number | null;
  url: string;
};

export type FunnelAIChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type FunnelAIAttachment = {
  assetId: string;
  publicId: string;
  filename?: string | null;
  contentType?: string | null;
  width?: number | null;
  height?: number | null;
};

export type FunnelPageAIGenerateResponse = {
  assistantMessage: string;
  puckData: unknown;
  draftVersionId: string;
  generatedImages: Array<Record<string, unknown>>;
  imagePlans: Array<Record<string, unknown>>;
};

export type FunnelTemplateSummary = {
  id: string;
  name: string;
  description?: string | null;
  previewImage?: string | null;
};

export type FunnelTemplateDetail = FunnelTemplateSummary & {
  puckData: unknown;
};
