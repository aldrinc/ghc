export type SocialProviderAsset = {
  id: string;
  connectionId?: string | null;
  provider: string;
  providerAssetId: string;
  assetType: string;
  displayName: string;
  parentProviderAssetId?: string | null;
  capabilityFlags: string[];
  status: string;
  metadata: Record<string, unknown>;
  lastSyncedAt?: string | null;
  createdAt: string;
  updatedAt: string;
};

export type AgentActionProposal = {
  id: string;
  campaignId?: string | null;
  sourceAgentRunId?: string | null;
  actionType: string;
  targetProvider: string;
  targetAssetId?: string | null;
  targetAssetType?: string | null;
  beforeSnapshot: Record<string, unknown>;
  proposedAfter: Record<string, unknown>;
  rationale?: string | null;
  riskLabel: string;
  requiredCapability?: string | null;
  status: string;
  approvedByUserId?: string | null;
  approvedAt?: string | null;
  executedAt?: string | null;
  providerResponse?: Record<string, unknown> | null;
  rollbackHint: Record<string, unknown>;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};

export type ConversionSource = {
  id: string;
  provider: string;
  name: string;
  status: string;
  goalEvents: string[];
  config: Record<string, unknown>;
  credentialsMetadata: Record<string, unknown>;
  lastSyncedAt?: string | null;
  lastError?: string | null;
  createdAt: string;
  updatedAt: string;
};

export type ContentGrowthProgram = {
  id: string;
  productId?: string | null;
  campaignId?: string | null;
  conversionSourceId?: string | null;
  name: string;
  objective: string;
  platformKey: string;
  formatKey: string;
  authorityMode: string;
  status: string;
  settings: Record<string, unknown>;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};

export type ContentExperiment = {
  id: string;
  growthProgramId: string;
  name: string;
  hypothesis: string;
  hookFamily?: string | null;
  ctaFamily?: string | null;
  audience?: string | null;
  status: string;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};

export type ContentVariantSlideInput = {
  slideIndex: number;
  visualRole?: string | null;
  prompt?: string | null;
  overlayText: string;
  sourceAssetId?: string | null;
  renderedAssetId?: string | null;
  renderStatus?: string;
  rendererVersion?: string | null;
  metadata?: Record<string, unknown>;
};

export type ContentVariantSlide = ContentVariantSlideInput & {
  id: string;
  renderStatus: string;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};

export type ContentVariant = {
  id: string;
  growthProgramId: string;
  experimentId?: string | null;
  platformKey: string;
  formatKey: string;
  title?: string | null;
  caption?: string | null;
  cta?: string | null;
  slideCount: number;
  status: string;
  approvedByUserId?: string | null;
  approvedAt?: string | null;
  storyboard: Record<string, unknown>;
  providerPayload: Record<string, unknown>;
  metadata: Record<string, unknown>;
  slides: ContentVariantSlide[];
  createdAt: string;
  updatedAt: string;
};

export type ContentGrowthProgramInput = {
  name: string;
  objective: string;
  platformKey?: string;
  formatKey?: string;
  authorityMode?: string;
  status?: string;
  settings?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
};

export type ConversionSourceInput = {
  provider: string;
  name: string;
  status?: string;
  goalEvents?: string[];
  config?: Record<string, unknown>;
  credentialsMetadata?: Record<string, unknown>;
};

export type ContentExperimentInput = {
  name: string;
  hypothesis: string;
  hookFamily?: string | null;
  ctaFamily?: string | null;
  audience?: string | null;
  status?: string;
  metadata?: Record<string, unknown>;
};

export type ContentVariantInput = {
  experimentId?: string | null;
  platformKey?: string;
  formatKey?: string;
  title?: string | null;
  caption?: string | null;
  cta?: string | null;
  slideCount?: number;
  status?: string;
  storyboard?: Record<string, unknown>;
  providerPayload?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  slides?: ContentVariantSlideInput[];
};

export type PostizHandoffProposalInput = {
  content?: string | null;
  postType?: "draft" | "schedule" | "now";
  scheduledFor?: string | null;
  channelIds?: string[];
  mediaUrls?: string[];
  linkUrl?: string | null;
  postingProfileId?: string | null;
  providerSettingsByIdentifier?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
};

export type PostizHandoffProposal = {
  proposalId: string;
  actionType: string;
  targetProvider: string;
  growthProgramId: string;
  variantId: string;
  status: string;
  postizPayload: Record<string, unknown>;
  createdAt: string;
};

export type ConversionEventInput = {
  conversionSourceId: string;
  providerEventId: string;
  eventName: string;
  occurredAt: string;
  value?: string | null;
  currency?: string | null;
  contentVariantId?: string | null;
  postizPostId?: string | null;
  postizChannelId?: string | null;
  attribution?: Record<string, unknown>;
  rawPayload?: Record<string, unknown>;
  provenance?: string;
};
