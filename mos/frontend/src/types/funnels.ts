export type FunnelStatus = "draft" | "published" | "disabled" | "archived";

import type { DesignSystemTokens } from "@/types/designSystems";

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
  publicId: string;
  funnelId: string;
  publicationId: string;
  entrySlug: string;
  pages: { pageId: string; slug: string }[];
};

export type PublicFunnelPage = {
  funnelId: string;
  publicationId: string;
  pageId: string;
  slug: string;
  puckData: unknown;
  pageMap: Record<string, string>;
  designSystemTokens?: DesignSystemTokens | null;
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
