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

export type HtmlDeployArtifactKind = "listicle" | "listicle_hybrid" | "quiz" | "sales";

export type ImportedHtmlTrackEventType =
  | "pre_sales_to_sales_click"
  | "sales_to_checkout_click"
  | "checkout_started"
  | "selector_interaction"
  | "product_detail_interaction"
  | "custom_page_click";

export type ImportedHtmlOptionSelector = {
  name: string;
  selector: string;
  source: "value" | "text";
};

export type ImportedHtmlVariantResolver =
  | {
      type: "fixed";
      variantId: string;
    }
  | {
      type: "option_values";
      optionSelectors: ImportedHtmlOptionSelector[];
    };

export type ImportedHtmlCheckoutConfig =
  | {
      mode: "public_checkout";
      variantResolver: ImportedHtmlVariantResolver;
    }
  | {
      mode: "external_checkout_url";
      variantResolver: ImportedHtmlVariantResolver;
      externalUrlsByVariant: Array<{
        variantId: string;
        url: string;
      }>;
    };

export type ImportedHtmlInstrumentationBinding =
  | {
      id: string;
      type: "internal_navigation";
      selector: string;
      event: "click";
      targetPageId: string;
      trackEventType: ImportedHtmlTrackEventType;
    }
  | {
      id: string;
      type: "checkout";
      selector: string;
      event: "click";
      trackEventType: ImportedHtmlTrackEventType;
      checkout: ImportedHtmlCheckoutConfig;
    }
  | {
      id: string;
      type: "track_only";
      selector: string;
      event: "click";
      trackEventType: ImportedHtmlTrackEventType;
    };

export type ImportedHtmlViewTarget = {
  id: string;
  selector: string;
  label?: string | null;
  proofType?: string | null;
  sectionId?: string | null;
  ctaPosition?: number | null;
  questionId?: string | null;
  questionText?: string | null;
  questionIndex?: number | null;
  questionType?: string | null;
  questionRole?: string | null;
  isRequired?: boolean | null;
  optionId?: string | null;
  optionText?: string | null;
  optionIndex?: number | null;
  optionPosition?: number | null;
  optionRole?: string | null;
  selectionOrder?: number | null;
  submitOnSelect?: boolean | null;
  resultId?: string | null;
  segmentId?: string | null;
  screenIndex?: number | null;
  screenName?: string | null;
  route?: string | null;
  hash?: string | null;
  titleContains?: string | null;
  requiredBreakpoints?: number[];
  recommendationId?: string | null;
  screenIndex?: number | null;
  screenName?: string | null;
  route?: string | null;
  hash?: string | null;
  titleContains?: string | null;
  requiredBreakpoints?: number[];
  offerId?: string | null;
  sku?: string | null;
  mechanismName?: string | null;
  guaranteeType?: string | null;
  interactionType?: string | null;
  selectedValue?: string | null;
  event?: "click" | "change" | "input" | null;
  source?: "value" | "text" | "checked" | null;
  quizId?: string | null;
  quizVersion?: string | null;
  quizVariant?: string | null;
  answerPathId?: string | null;
  angle?: string | null;
  awarenessLevel?: string | null;
  sophisticationLevel?: string | null;
  angleFamily?: string | null;
  hookId?: string | null;
  promiseId?: string | null;
  bundleId?: string | null;
  pricePoint?: string | null;
  guaranteeId?: string | null;
  guaranteeDuration?: string | null;
  valueTotal?: number | null;
  actualPrice?: number | null;
  valueRatio?: number | null;
  clickType?: string | null;
  targetOfferId?: string | null;
  destinationUrl?: string | null;
  elementId?: string | null;
  subscriptionFlag?: boolean | null;
};

export type ImportedHtmlInstrumentationManifest = {
  schemaVersion: "html-deploy-v1";
  htmlArtifactKind: HtmlDeployArtifactKind;
  pageStage: PublicFunnelStage;
  quizId?: string | null;
  quizVersion?: string | null;
  quizVariant?: string | null;
  bindings: ImportedHtmlInstrumentationBinding[];
  sections?: ImportedHtmlViewTarget[];
  proofs?: ImportedHtmlViewTarget[];
  ctas?: ImportedHtmlViewTarget[];
  offerStacks?: ImportedHtmlViewTarget[];
  valueStacks?: ImportedHtmlViewTarget[];
  priceReveals?: ImportedHtmlViewTarget[];
  guarantees?: ImportedHtmlViewTarget[];
  trustElements?: ImportedHtmlViewTarget[];
  quizLeads?: ImportedHtmlViewTarget[];
  quizQuestions?: ImportedHtmlViewTarget[];
  quizOptions?: ImportedHtmlViewTarget[];
  quizSubmissions?: ImportedHtmlViewTarget[];
  quizScrollTargets?: ImportedHtmlViewTarget[];
  quizResults?: ImportedHtmlViewTarget[];
  quizMechanisms?: ImportedHtmlViewTarget[];
  quizRecommendations?: ImportedHtmlViewTarget[];
  quizScrollTargets?: ImportedHtmlViewTarget[];
  productDetails?: ImportedHtmlViewTarget[];
  selectors?: ImportedHtmlViewTarget[];
};

// Site page types for commerce experiences
export type SitePageType =
  | "home"
  | "store"
  | "collection"
  | "category"
  | "product_detail"
  | "cart"
  | "checkout"
  | "privacy_policy"
  | "terms_of_service"
  | "returns_refunds_policy"
  | "shipping_policy"
  | "contact_support"
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
    posthogProjectApiKey?: string | null;
    posthogApiHost?: string | null;
    posthogUiHost?: string | null;
    posthogDefaults?: string | null;
    posthogPersonProfiles?: "identified_only" | "always" | null;
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
  category?: string | null;
};

export type FunnelTemplateDetail = FunnelTemplateSummary & {
  puckData: unknown;
};
