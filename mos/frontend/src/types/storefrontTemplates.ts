export type StorefrontTemplateBindingRequirement = {
  key: string;
  label: string;
  source: string;
  description: string;
  required: boolean;
};

export type StorefrontTemplateStylePolicy = {
  lockedTokenGroups: string[];
  editableTokenGroups: string[];
};

export type StorefrontTemplateImportProvenance = {
  sourceType: string;
  sourceTemplateId: string;
  notes: string[];
};

export type StorefrontTemplateSummary = {
  id: string;
  name: string;
  description?: string | null;
  previewImage?: string | null;
  family: string;
  variant: string;
  version: string;
  pageType: string;
  configSlots: string[];
  requiredBindingKeys: string[];
};

export type StorefrontTemplateDetail = StorefrontTemplateSummary & {
  requiredBindings: StorefrontTemplateBindingRequirement[];
  stylePolicy: StorefrontTemplateStylePolicy;
  importProvenance: StorefrontTemplateImportProvenance;
  puckData: unknown;
};

export type StorefrontBindingPreviewRequirement = {
  key: string;
  label: string;
  source: string;
  required: boolean;
  status: "ready" | "missing" | "unsupported" | string;
  detail: string;
};

export type StorefrontBindingPreview = {
  templateId: string;
  clientId: string;
  productId?: string | null;
  productTitle?: string | null;
  variantId?: string | null;
  variantTitle?: string | null;
  variantProvider?: string | null;
  ready: boolean;
  requirements: StorefrontBindingPreviewRequirement[];
  notes: string[];
};

// Site Import Types
export type ThemePalette = {
  primary?: string | null;
  secondary?: string | null;
  surface?: string | null;
  accent?: string | null;
  text?: string | null;
  background?: string | null;
};

export type ThemeFonts = {
  primary?: string | null;
  heading?: string | null;
  body?: string | null;
  cta?: string | null;
};

export type ThemeSpacing = {
  density: "compact" | "comfortable" | "spacious";
  scale: string[];
};

export type ThemeCTA = {
  style: string;
  borderRadius?: string | null;
  padding?: string | null;
};

export type ThemeCandidate = {
  palette?: ThemePalette;
  fonts?: ThemeFonts;
  spacing?: ThemeSpacing;
  cta?: ThemeCTA;
  dataTheme?: string;
  fontUrls?: string[];
  fontCss?: string | null;
  cssVars?: Record<string, string | number>;
  funnelDefaults?: Record<string, unknown>;
  brand?: {
    name?: string | null;
    logoAssetPublicId?: string | null;
    logoOnDarkAssetPublicId?: string | null;
    logoAlt?: string | null;
  };
  diagnostics?: {
    sourceInputs?: {
      hasTailwindSource?: boolean;
      hasIndexCssSource?: boolean;
      designSystemHtmlPath?: string | null;
    };
    fidelity?: {
      fontDelivery?: string | null;
      backgroundStrategy?: string | null;
    };
    promotionReadiness?: {
      ready?: boolean;
      missingFields?: string[];
      notes?: string[];
    };
  };
  [key: string]: unknown;
};

export type NormalizedSection = {
  id: string;
  displayName?: string | null;
  sectionKey?: string | null;
  semanticTags: string[];
  sectionType: string;
  confidence: number;
  keyText: string[];
  keyMedia: string[];
  keyStyles: Record<string, unknown>;
  boundingBox?: { x: number; y: number; width: number; height: number } | null;
};

export type SiteImportSummary = {
  id: string;
  sourceUrl: string;
  sourceHostname?: string | null;
  pageTypeHint?: string | null;
  siteFamilyHint?: string | null;
  status: string;
  title?: string | null;
  suggestedTemplateFamily?: string | null;
  createdAt: string;
  updatedAt: string;
};

export type UpstreamTranscriptSummaryEvent = {
  type: string;
  variantIndex: number;
  captureIndex: number;
  capturedAt?: string | null;
  localSequence: number;
  status?: string;
  hasCode?: boolean;
  codeLength?: number;
  completed?: boolean;
  model?: string;
  error?: string;
  models?: string[];
  contentPreview?: string;
  contentLength?: number;
  source?: string;
  title?: string;
  toolName?: string;
  ok?: boolean;
};

export type SiteImportDetail = {
  id: string;
  sourceUrl: string;
  sourceHostname?: string | null;
  pageTypeHint?: string | null;
  siteFamilyHint?: string | null;
  status: string;
  inputMode: string;
  modelSlots: number[];
  title?: string | null;
  metaDescription?: string | null;
  suggestedTemplateFamily?: string | null;
  resolvedSiteFamily?: string | null;
  resolvedPageType?: string | null;
  resolvedTemplateId?: string | null;
  themeCandidate: ThemeCandidate;
  normalizedSections: NormalizedSection[];
  upstreamRequestPayload: Record<string, unknown>;
  upstreamTranscript: Record<string, unknown>[];
  upstreamTranscriptSummary: UpstreamTranscriptSummaryEvent[];
  upstreamVariants: Record<string, unknown>[];
  upstreamMetadata: Record<string, unknown>;
  adaptedSite: Record<string, unknown>;
  adaptedPages: Record<string, unknown>[];
  adaptedPuckData: Record<string, unknown>;
  generatorError?: string | null;
  failureStage?: string | null;
  savedSiteId?: string | null;
  synthesis?: SynthesisOutput;
  captureError?: string | null;
  createdAt: string;
  updatedAt: string;
};

export type SiteImportSnapshot = {
  id: string;
  htmlSnapshot: string;
  desktopScreenshotDataUrl: string;
  mobileScreenshotDataUrl: string;
  captureMetadata: Record<string, unknown>;
  createdAt: string;
};

// Variant Draft Types
export type TemplateVariantSummary = {
  id: string;
  name: string;
  family: string;
  pageType: string;
  status: string;
  siteImportId?: string | null;
  sourceType?: string | null;
  parentVariantId?: string | null;
  mutationPresetLabel?: string | null;
  createdAt: string;
  updatedAt: string;
};

export type TemplateVariantDetail = {
  id: string;
  name: string;
  family: string;
  pageType: string;
  status: string;
  siteImportId?: string | null;
  stylePresetId?: string | null;
  acceptedSections: NormalizedSection[];
  provenance: Record<string, unknown>;
  reviewNotes?: string | null;
  createdAt: string;
  updatedAt: string;
};

export type TemplateStylePreset = {
  id: string;
  name: string;
  status: string;
  tokens: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};

// API Request Types
export type CreateSiteImportRequest = {
  sourceUrl: string;
  pageTypeHint?: string;
  siteFamilyHint?: string;
};

export type ConvertImportRequest = {
  name: string;
  family: string;
  pageType: string;
  acceptedSectionIds: string[];
  reviewNotes?: string;
};

export type SaveSiteImportRequest = {
  importId: string;
  siteName: string;
  description?: string;
};

export type CreateVariantSiteRequest = {
  siteName?: string;
  description?: string;
};

export type SaveSiteImportCreatedPage = {
  pageId: string;
  pageType?: string | null;
  templateId?: string | null;
  versionId?: string | null;
};

export type SaveSiteImportResponse = {
  siteId: string;
  siteName: string;
  pageCount: number;
  entryPageType?: string | null;
  createdPages: SaveSiteImportCreatedPage[];
  createdAt: string;
};

export type CreateVariantSiteResponse = {
  siteId: string;
  siteName: string;
  pageCount: number;
  entryPageType?: string | null;
  createdPages: SaveSiteImportCreatedPage[];
  createdAt: string;
};

// Synthesis Types
export type BlockCoverageDetail = {
  sectionId: string;
  sectionType: string;
  mappedBlock: string | null;
  coverage: "exact" | "partial" | "missing";
  confidence: number;
};

export type BlockCoverageSummary = {
  totalSections: number;
  exactMatches: number;
  partialMatches: number;
  missingMatches: number;
  coverageScore: number;
};

export type MissingBlockRequest = {
  requestId: string;
  sectionType: string;
  reason: string;
  sourceSelector: string | null;
  textPreview: string | null;
  suggestedFamily: string;
  suggestedPageType: string;
};

export type SynthesisOutput = {
  targetFamily: string;
  targetPageType: string;
  blockCoverage: BlockCoverageSummary;
  blockCoverageDetails: BlockCoverageDetail[];
  missingBlockRequests: MissingBlockRequest[];
  synthesizedPuckData: Record<string, unknown>;
};

// =============================================================================
// Variant Mutation Preset Types
// =============================================================================

export type MutationPresetSummary = {
  id: string;
  label: string;
  description: string;
  families: string[];
  effects: string[];
};

export type MutationPresetPreview = {
  presetId: string;
  presetLabel: string;
  presetDescription: string;
  applicable: boolean;
  notApplicableReason?: string | null;
  effects: string[];
};

export type VariantProvenance = {
  sourceType: string;
  sourceUrl?: string | null;
  sourceHostname?: string | null;
  importedAt?: string | null;
  pageTypeHint?: string | null;
  parentVariantId?: string | null;
  parentVariantName?: string | null;
  mutationPresetId?: string | null;
  mutationPresetLabel?: string | null;
  mutationSummary?: string | null;
  synthesis?: Record<string, unknown> | null;
};

export type TemplateVariantDetailExtended = TemplateVariantDetail & {
  synthesizedPuckData?: Record<string, unknown> | null;
};

export type GenerateVariantsRequest = {
  presetIds: string[];
  generatedNames?: string[] | null;
};

export type GeneratedVariantSummary = {
  id: string;
  name: string;
  family: string;
  pageType: string;
  status: string;
  parentVariantId: string;
  mutationPresetId: string;
  mutationPresetLabel: string;
  mutationSummary: string;
  createdAt: string;
  updatedAt: string;
};

export type GenerateVariantsResponse = {
  generatedVariants: GeneratedVariantSummary[];
};

// =============================================================================
// Governance Types (Phase 5)
// =============================================================================

export type AssetValidationResult = {
  publicId: string;
  fieldPath: string[];
  blockType?: string | null;
  blockId?: string | null;
  status: "approved" | "pending" | "rejected" | "not_found" | string;
  assetId?: string | null;
};

export type StyleAuditFinding = {
  checkId: string;
  status: string;
  message: string;
  location: string;
  foreground?: string | null;
  background?: string | null;
  contrastRatio?: number | null;
  threshold?: number | null;
};

export type StyleAuditResult = {
  presetId?: string | null;
  presetName?: string | null;
  findings: StyleAuditFinding[];
  passed: boolean;
};

export type PuckDataStructureResult = {
  valid: boolean;
  errors: string[];
  warnings: string[];
};

export type ProvenanceEvent = {
  eventType: string;
  timestamp: string;
  actor?: string | null;
  metadata: Record<string, unknown>;
};

export type GovernanceReport = {
  variantId: string;
  readyForPublish: boolean;
  blockers: string[];
  warnings: string[];
  assetValidations: AssetValidationResult[];
  styleAudit?: StyleAuditResult | null;
  puckDataStructure?: PuckDataStructureResult | null;
  provenanceEvents: ProvenanceEvent[];
};

export type ApproveForPublishRequest = Record<string, never>;

export type ApproveForPublishResponse = {
  variantId: string;
  status: string;
  provenance: Record<string, unknown>;
  governanceReport: GovernanceReport;
};

// =============================================================================
// Create Draft from Template Types
// =============================================================================

export type CreateDraftFromTemplateRequest = {
  name: string;
  productId: string;
  variantId: string;
  reviewNotes?: string;
};

export type CreateDraftFromTemplateResponse = {
  variant: TemplateVariantDetailExtended;
  bindingPreview: StorefrontBindingPreview;
};

// Re-export import activity types for convenience
export type {
  ActivityEvent,
  UpstreamEventType,
  UpstreamTranscriptEntry,
  UpstreamVariantData,
  AgentEventMeta,
  VariantResultMeta,
  VariantErrorMeta,
  VariantModelsData,
  ToolEventData,
} from "./importActivity";
