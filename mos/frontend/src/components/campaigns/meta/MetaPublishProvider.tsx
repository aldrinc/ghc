import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import { useCampaignDelivery } from "@/api/campaigns";
import { useClientShopifyStatus } from "@/api/clients";
import { useFunnels } from "@/api/funnels";
import type { PaidAdsQaRun } from "@/api/paidAdsQa";
import { useMetaApi } from "@/api/meta";
import {
  META_AUTOMATIC_PLACEMENTS,
  META_DEFAULT_CAMPAIGN_DAILY_BUDGET_MINOR_UNITS,
  META_DEFAULT_BROAD_INT_TARGETING,
  META_DEFAULT_PUBLISH_ATTRIBUTION_SPEC,
  formatPlacementPresetJson,
} from "@/lib/metaAdsConstants";
import { resolveMetaCreativeQaState } from "@/lib/metaCreativeQa";
import {
  resolveConfiguredShopHostedOrigin,
  resolveShopHostedUrl,
  resolveWindowShopHostedOrigin,
} from "@/lib/shopHostedFunnels";
import { resolveRequiredApiBaseUrl } from "@/lib/apiBaseUrl";
import type { AssetBrief } from "@/types/artifacts";
import type { Campaign } from "@/types/common";
import type { Funnel } from "@/types/funnels";
import type {
  MetaAdSetSpec,
  MetaPipelineAsset,
  MetaPublishPlanValidation,
  MetaPublishRun,
  MetaPublishSelection,
  MetaPublishSelectionDecision,
} from "@/types/meta";

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

export type MetaPackageView = "review" | "final";

export type MetaWorkflowPhase = "generate" | "review" | "qa" | "publish" | "manage";

export type MetaPublishCampaignForm = {
  publishBaseUrl: string;
  campaignName: string;
  campaignObjective: string;
  buyingType: string;
  specialAdCategories: string;
  campaignDailyBudget: string;
  bucketCount: string;
  bucketDestinationUrls: string[];
};

export type MetaPublishAdSetForm = {
  name: string;
  optimizationGoal: string;
  billingEvent: string;
  targetingJson: string;
  placementsJson: string;
  attributionSpecJson: string;
  dailyBudget: string;
  lifetimeBudget: string;
  dsaBeneficiary: string;
  dsaPayor: string;
  startTime: string;
  endTime: string;
  promotedPixelId: string;
  promotedCustomEventType: string;
  promotedObjectJson: string;
  conversionDomain: string;
};

export type MetaReviewSetupIssue = {
  assetId: string;
  assetBriefId?: string | null;
  generationKey?: string | null;
  funnelId?: string | null;
  destinationPage?: string | null;
  normalizedDestinationPage?: string | null;
  issues: Array<{
    ruleId?: string | null;
    title?: string | null;
    message?: string | null;
  }>;
};

export type GenerationSummary = {
  key: string;
  kind: "batch" | "remoteJob" | "asset";
  label: string;
  latestCreatedAt: number;
  count: number;
};

export type GroupedPipelineEntry = {
  requirementIndex: number;
  title: string;
  funnelStage: string | null;
  items: MetaPipelineAsset[];
};

// ---------------------------------------------------------------------------
// Utilities (extracted from monolith)
// ---------------------------------------------------------------------------

const apiBaseUrl = resolveRequiredApiBaseUrl();
const DEFAULT_META_PUBLISH_BUCKET_COUNT = 5;
const MAX_META_PUBLISH_BUCKET_COUNT = 8;

export function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function shortId(value?: string | null, size = 6) {
  if (!value) return "—";
  return value.length > size * 2 ? `${value.slice(0, size)}…${value.slice(-size)}` : value;
}

export function resolveAssetUrl(path?: string | null): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  return `${apiBaseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

function getErrorMessage(err: unknown) {
  if (typeof err === "string") return err;
  if (err && typeof err === "object" && "message" in err) {
    const apiError = err as ApiError;
    const detailMessage = (apiError.raw as { detail?: { message?: string } } | undefined)?.detail?.message;
    return detailMessage || apiError.message || "Request failed";
  }
  return "Request failed";
}

export function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function readNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function readRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function formatFunnelLabel(funnel?: Funnel | null, fallbackFunnelId?: string | null): string {
  if (funnel) {
    const routeLabel = funnel.route_slug ? `/${funnel.route_slug}` : shortId(funnel.id, 4);
    return `${funnel.name} (${routeLabel})`;
  }
  if (fallbackFunnelId) {
    return `Funnel ${shortId(fallbackFunnelId, 4)}`;
  }
  return "Unknown funnel";
}

function getGenerationGroup(item: MetaPipelineAsset): {
  key: string;
  kind: "batch" | "remoteJob" | "asset";
  label: string;
} {
  const metadata = readRecord(item.asset.ai_metadata);
  const batchId = readString(metadata?.creativeGenerationBatchId);
  if (batchId) {
    return { key: `batch:${batchId}`, kind: "batch", label: `Batch ${shortId(batchId, 5)}` };
  }
  const remoteJobId = readString(metadata?.remoteJobId);
  if (remoteJobId) {
    return { key: `remoteJob:${remoteJobId}`, kind: "remoteJob", label: `Render ${shortId(remoteJobId, 5)}` };
  }
  return { key: `asset:${item.asset.id}`, kind: "asset", label: `Asset ${shortId(item.asset.id, 5)}` };
}

export function formatJsonInput(value: unknown): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "";
  }
}

export function formatJsonArrayInput(value: unknown): string {
  if (!Array.isArray(value)) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "";
  }
}

export function parseJsonObjectInput(value: string, label: string): Record<string, unknown> | null {
  const cleaned = value.trim();
  if (!cleaned) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(cleaned);
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

export function parseJsonObjectArrayInput(value: string, label: string): Record<string, unknown>[] | null {
  const cleaned = value.trim();
  if (!cleaned) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(cleaned);
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
  if (!Array.isArray(parsed) || parsed.some((item) => !item || typeof item !== "object" || Array.isArray(item))) {
    throw new Error(`${label} must be a JSON array of objects.`);
  }
  return parsed as Record<string, unknown>[];
}

export function parseIntegerInput(value: string, label: string): number | null {
  const cleaned = value.trim();
  if (!cleaned) return null;
  if (!/^-?\d+$/.test(cleaned)) {
    throw new Error(`${label} must be a whole number.`);
  }
  return Number(cleaned);
}

function readBucketIndex(metadata: Record<string, unknown> | null | undefined): number | null {
  const raw = metadata?.bucketIndex;
  if (typeof raw === "number" && Number.isInteger(raw)) return raw;
  if (typeof raw === "string" && /^\d+$/.test(raw.trim())) return Number(raw.trim());
  return null;
}

function sortBucketSpecs(specs: MetaAdSetSpec[]): MetaAdSetSpec[] {
  return [...specs].sort((left, right) => {
    const leftBucketIndex = readBucketIndex(left.metadata_json);
    const rightBucketIndex = readBucketIndex(right.metadata_json);
    if (leftBucketIndex != null && rightBucketIndex != null && leftBucketIndex !== rightBucketIndex) {
      return leftBucketIndex - rightBucketIndex;
    }
    if (leftBucketIndex != null && rightBucketIndex == null) return -1;
    if (leftBucketIndex == null && rightBucketIndex != null) return 1;
    return left.id.localeCompare(right.id);
  });
}

function clampPublishBucketCount(value: number): number {
  return Math.min(MAX_META_PUBLISH_BUCKET_COUNT, Math.max(1, value));
}

function resizeBucketDestinationUrls(urls: string[], bucketCount: number): string[] {
  const next = urls.slice(0, bucketCount);
  while (next.length < bucketCount) next.push("");
  return next;
}

export function toLocalDateTimeValue(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offsetDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return offsetDate.toISOString().slice(0, 16);
}

export function fromLocalDateTimeValue(value: string): string | null {
  const cleaned = value.trim();
  if (!cleaned) return null;
  const date = new Date(cleaned);
  if (Number.isNaN(date.getTime())) {
    throw new Error("Date/time values must be valid.");
  }
  return date.toISOString();
}

function formatPublishCampaignDate(value = new Date()): string {
  const month = value.getMonth() + 1;
  const day = value.getDate();
  const year = String(value.getFullYear()).slice(-2);
  return `${month}/${day}/${year}`;
}

function buildDefaultPublishCampaignName(campaignName: string): string {
  const cleaned = campaignName.trim() || "Campaign";
  return `[${formatPublishCampaignDate()}] - [${cleaned}] - [CBO] - [Broad/Int]`;
}

function cloneDefaultAttributionSpec(): Record<string, unknown>[] {
  return META_DEFAULT_PUBLISH_ATTRIBUTION_SPEC.map((entry) => ({ ...entry }));
}

function resolveAdSetAttributionSpec(spec: MetaAdSetSpec): Record<string, unknown>[] {
  const metadata = readRecord(spec.metadata_json);
  const rawValue = metadata?.attributionSpec;
  if (Array.isArray(rawValue) && rawValue.every((item) => item && typeof item === "object" && !Array.isArray(item))) {
    return rawValue as Record<string, unknown>[];
  }
  return cloneDefaultAttributionSpec();
}

export function buildAdSetForm(
  spec: MetaAdSetSpec,
  defaults?: {
    pageName?: string | null;
  },
): MetaPublishAdSetForm {
  const promotedObject = readRecord(spec.promoted_object);
  const optimizationGoal = spec.optimization_goal || "OFFSITE_CONVERSIONS";
  const defaultPageName = readString(defaults?.pageName) || "";
  const targetingDefaults = spec.targeting ?? META_DEFAULT_BROAD_INT_TARGETING;
  const placementDefaults = spec.placements ?? META_AUTOMATIC_PLACEMENTS;
  return {
    name: spec.name || "",
    optimizationGoal,
    billingEvent: spec.billing_event || "IMPRESSIONS",
    targetingJson: formatJsonInput(targetingDefaults),
    placementsJson: formatJsonInput(placementDefaults) || formatPlacementPresetJson(META_AUTOMATIC_PLACEMENTS),
    attributionSpecJson: formatJsonArrayInput(resolveAdSetAttributionSpec(spec)),
    dailyBudget: spec.daily_budget != null ? String(spec.daily_budget) : "",
    lifetimeBudget: spec.lifetime_budget != null ? String(spec.lifetime_budget) : "",
    dsaBeneficiary: readString(spec.dsa_beneficiary) || defaultPageName,
    dsaPayor: readString(spec.dsa_payor) || defaultPageName,
    startTime: toLocalDateTimeValue(spec.start_time),
    endTime: toLocalDateTimeValue(spec.end_time),
    promotedPixelId: readString(promotedObject?.pixel_id) || "",
    promotedCustomEventType: readString(promotedObject?.custom_event_type) || "",
    promotedObjectJson: formatJsonInput(spec.promoted_object),
    conversionDomain: spec.conversion_domain || "",
  };
}

function buildPromotedObjectPayload(
  form: MetaPublishAdSetForm,
  options: {
    specLabel: string;
    defaultPixelId?: string | null;
  },
): Record<string, unknown> | null {
  const { specLabel, defaultPixelId } = options;
  const existing = parseJsonObjectInput(form.promotedObjectJson, `${specLabel} promoted object`) || {};
  const optimizationGoal = form.optimizationGoal.trim().toUpperCase();
  const pixelId = form.promotedPixelId.trim() || readString(existing.pixel_id) || readString(defaultPixelId) || "";
  const customEventType = form.promotedCustomEventType.trim() || readString(existing.custom_event_type) || "";

  if (optimizationGoal === "OFFSITE_CONVERSIONS") {
    if (!pixelId) {
      throw new Error(
        `${specLabel} needs a pixel ID for OFFSITE_CONVERSIONS. Validate the active Meta workspace config or enter the pixel ID explicitly.`,
      );
    }
    if (!customEventType) {
      throw new Error(`${specLabel} needs a conversion event for OFFSITE_CONVERSIONS.`);
    }
  }

  const promotedObject: Record<string, unknown> = { ...existing };
  if (pixelId) promotedObject.pixel_id = pixelId;
  else delete promotedObject.pixel_id;
  if (customEventType) promotedObject.custom_event_type = customEventType;
  else delete promotedObject.custom_event_type;

  return Object.keys(promotedObject).length ? promotedObject : null;
}

export function publishDecisionTone(
  decision?: MetaPublishSelectionDecision | null,
): "neutral" | "accent" | "success" | "danger" {
  if (decision === "excluded") return "danger";
  return "success";
}

export function publishDecisionLabel(decision?: MetaPublishSelectionDecision | null): string {
  if (decision === "excluded") return "Excluded from Meta";
  return "Included by default";
}

// ---------------------------------------------------------------------------
// Context value type
// ---------------------------------------------------------------------------

type MetaPublishContextValue = {
  // Props passthrough
  campaign: Campaign;
  assetBriefs: AssetBrief[];

  // Config
  config: {
    adAccountId: string;
    pageId?: string | null;
    pageName?: string | null;
    pixelId?: string | null;
    graphApiVersion?: string | null;
    validationStatus?: string | null;
    lastValidatedAt?: string | null;
    lastValidationError?: string | null;
  } | null;
  configError: string | null;

  // Pipeline
  pipeline: MetaPipelineAsset[];
  pipelineLoading: boolean;
  pipelineError: string | null;
  refreshPipeline: () => Promise<void>;

  // Generation
  generatePending: boolean;
  generateError: string | null;
  selectedSwipeCollectionId: string | null;
  setSelectedSwipeCollectionId: (value: string | null) => void;
  handleGenerateAssets: () => Promise<void>;
  autoRefreshUntil: number | null;
  lastWorkflowRunId: string | null;

  // Preparation
  preparePending: boolean;
  prepareError: string | null;
  prepareIssues: MetaReviewSetupIssue[];
  lastPreparedAt: string | null;
  handlePrepareMetaReview: () => Promise<void>;

  // Scope & view
  latestGenerationOnly: boolean;
  setLatestGenerationOnly: (value: boolean) => void;
  selectedFunnelId: string | null;
  setSelectedFunnelId: (value: string | null) => void;
  packageView: MetaPackageView;
  setPackageView: (value: MetaPackageView) => void;

  // Derived generation
  assetBriefIds: string[];
  briefById: Map<string, AssetBrief>;
  funnelById: Map<string, Funnel>;
  isExternalDelivery: boolean;
  requiresFunnelScope: boolean;
  hasGeneratedAssets: boolean;
  creativeSpecCount: number;
  adsetSpecCount: number;
  generationSummaries: GenerationSummary[];
  latestGenerationSummary: GenerationSummary | null;
  latestGenerationKey: string | null;
  latestGenerationBatchId: string | null;

  // Derived funnel scope
  latestGenerationFunnelIds: string[];
  funnelScopeOptions: Array<{ label: string; value: string }>;
  latestGenerationUnmappedCount: number;
  activeFunnelId: string | null;
  activeFunnel: Funnel | null;
  activeFunnelLabel: string | null;
  funnelsLoading: boolean;
  funnelsError: unknown;

  // Derived pipeline visibility
  visiblePipeline: MetaPipelineAsset[];
  latestGenerationScopedPipeline: MetaPipelineAsset[];
  hiddenLegacyCount: number;
  hiddenOtherFunnelCount: number;
  visibleMissingCreativeSpecCount: number;
  prepareAssetBriefIds: string[];
  groupedPipeline: GroupedPipelineEntry[];

  // Package
  canManagePublishPackage: boolean;
  canPrepareMetaReview: boolean;
  creativeReviewQaRuns: PaidAdsQaRun[];
  creativeQaFilteringEnabled: boolean;
  creativeQaNotice: string | null;
  includedPackageItems: MetaPipelineAsset[];
  excludedPackageCount: number;
  availableBucketCount: number;
  includedAdSetSpecs: MetaAdSetSpec[];
  publishSelections: MetaPublishSelection[];
  selectionByAssetId: Map<string, MetaPublishSelection>;
  selectionLoading: boolean;
  selectionError: string | null;
  selectionPendingAssetIds: string[];
  handleSetPublishDecision: (assetId: string, decision: MetaPublishSelectionDecision | null) => Promise<void>;

  // Publish forms
  publishCampaignForm: MetaPublishCampaignForm;
  publishBucketCount: number;
  updatePublishCampaignField: <K extends keyof MetaPublishCampaignForm>(field: K, value: MetaPublishCampaignForm[K]) => void;
  setPublishBucketCount: (value: string) => void;
  updatePublishBucketDestinationUrl: (bucketIndex: number, value: string) => void;
  publishAdSetForms: Record<string, MetaPublishAdSetForm>;
  updatePublishAdSetField: <K extends keyof MetaPublishAdSetForm>(specId: string, field: K, value: MetaPublishAdSetForm[K]) => void;
  publishFormError: string | null;

  // Publish validation & execution
  publishValidation: MetaPublishPlanValidation | null;
  publishValidationPending: boolean;
  publishPending: boolean;
  handleValidatePublishPlan: () => Promise<void>;
  handlePublishToMeta: () => Promise<void>;

  // Publish runs
  publishRuns: MetaPublishRun[];
  visiblePublishRuns: MetaPublishRun[];
  publishRunsLoading: boolean;
  publishRunsError: string | null;

  // Review base URL
  reviewBaseUrl: string | null;

  // Workflow phase
  currentPhase: MetaWorkflowPhase;

  // Utility for pipeline item funnel
  getPipelineItemFunnelId: (item: MetaPipelineAsset) => string | null;
};

const MetaPublishCtx = createContext<MetaPublishContextValue | undefined>(undefined);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function MetaPublishProvider({
  campaign,
  assetBriefs,
  children,
}: {
  campaign: Campaign;
  assetBriefs: AssetBrief[];
  children: ReactNode;
}) {
  const queryClient = useQueryClient();
  const { get, post } = useApiClient();
  const shopifyStatusQuery = useClientShopifyStatus(campaign.client_id);
  const deliveryQuery = useCampaignDelivery(campaign.id);
  const funnelsQuery = useFunnels({ campaignId: campaign.id });
  const {
    getConfig,
    listPipelineAssets,
    listPublishSelections,
    savePublishSelections,
    updateAdSetSpec,
    validatePublishPlan,
    listPublishRuns,
    createPublishRun,
  } = useMetaApi();

  const browserReviewBaseUrl = resolveWindowShopHostedOrigin();
  const storefrontDomain = useMemo(() => {
    const displayDomain = readString(shopifyStatusQuery.data?.displayShopDomain);
    if (displayDomain) return displayDomain;
    return readString(shopifyStatusQuery.data?.shopDomain);
  }, [shopifyStatusQuery.data?.displayShopDomain, shopifyStatusQuery.data?.shopDomain]);

  const reviewBaseUrl = useMemo(
    () => resolveConfiguredShopHostedOrigin(storefrontDomain) || browserReviewBaseUrl,
    [browserReviewBaseUrl, storefrontDomain],
  );

  // ---- State ----------------------------------------------------------------
  const [config, setConfig] = useState<{
    adAccountId: string;
    pageId?: string | null;
    pageName?: string | null;
    pixelId?: string | null;
    graphApiVersion?: string | null;
    validationStatus?: string | null;
    lastValidatedAt?: string | null;
    lastValidationError?: string | null;
  } | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [pipeline, setPipeline] = useState<MetaPipelineAsset[]>([]);
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [generatePending, setGeneratePending] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [selectedSwipeCollectionId, setSelectedSwipeCollectionId] = useState<string | null>(null);
  const [preparePending, setPreparePending] = useState(false);
  const [prepareError, setPrepareError] = useState<string | null>(null);
  const [prepareIssues, setPrepareIssues] = useState<MetaReviewSetupIssue[]>([]);
  const [lastWorkflowRunId, setLastWorkflowRunId] = useState<string | null>(null);
  const [lastPreparedAt, setLastPreparedAt] = useState<string | null>(null);
  const [autoRefreshUntil, setAutoRefreshUntil] = useState<number | null>(null);
  const [latestGenerationOnly, setLatestGenerationOnly] = useState(true);
  const [selectedFunnelId, setSelectedFunnelId] = useState<string | null>(null);
  const [packageView, setPackageView] = useState<MetaPackageView>("review");
  const [publishSelections, setPublishSelections] = useState<MetaPublishSelection[]>([]);
  const [selectionLoading, setSelectionLoading] = useState(false);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const [selectionPendingAssetIds, setSelectionPendingAssetIds] = useState<string[]>([]);
  const [qaRuns, setQaRuns] = useState<PaidAdsQaRun[]>([]);
  const [qaRunsLoading, setQaRunsLoading] = useState(false);
  const [qaRunsError, setQaRunsError] = useState<string | null>(null);
  const [publishCampaignForm, setPublishCampaignForm] = useState<MetaPublishCampaignForm>(() => ({
    publishBaseUrl: reviewBaseUrl || "",
    campaignName: buildDefaultPublishCampaignName(campaign.name),
    campaignObjective: "OUTCOME_SALES",
    buyingType: "AUCTION",
    specialAdCategories: "",
    campaignDailyBudget: String(META_DEFAULT_CAMPAIGN_DAILY_BUDGET_MINOR_UNITS),
    bucketCount: String(DEFAULT_META_PUBLISH_BUCKET_COUNT),
    bucketDestinationUrls: resizeBucketDestinationUrls([], DEFAULT_META_PUBLISH_BUCKET_COUNT),
  }));
  const [publishAdSetForms, setPublishAdSetForms] = useState<Record<string, MetaPublishAdSetForm>>({});
  const [publishFormError, setPublishFormError] = useState<string | null>(null);
  const [publishValidation, setPublishValidation] = useState<MetaPublishPlanValidation | null>(null);
  const [publishValidationPending, setPublishValidationPending] = useState(false);
  const [publishPending, setPublishPending] = useState(false);
  const [publishRuns, setPublishRuns] = useState<MetaPublishRun[]>([]);
  const [publishRunsLoading, setPublishRunsLoading] = useState(false);
  const [publishRunsError, setPublishRunsError] = useState<string | null>(null);

  // ---- Derived lookups ------------------------------------------------------
  const assetBriefIds = useMemo(
    () => assetBriefs.map((b) => b.id).filter((id): id is string => Boolean(id)),
    [assetBriefs],
  );
  const briefById = useMemo(() => new Map(assetBriefs.map((b) => [b.id, b])), [assetBriefs]);
  const funnelById = useMemo(
    () => new Map((funnelsQuery.data || []).map((f) => [f.id, f])),
    [funnelsQuery.data],
  );
  const isExternalDelivery = deliveryQuery.data?.deliveryMode === "external_urls";
  const requiresFunnelScope = !isExternalDelivery;

  // ---- Callbacks ------------------------------------------------------------
  const refreshPipeline = useCallback(async () => {
    setPipelineLoading(true);
    setPipelineError(null);
    try {
      const data = await listPipelineAssets({ campaignId: campaign.id });
      setPipeline(data);
    } catch (err) {
      setPipeline([]);
      setPipelineError(getErrorMessage(err));
    } finally {
      setPipelineLoading(false);
    }
  }, [campaign.id, listPipelineAssets]);

  const getPipelineItemFunnelId = useCallback(
    (item: MetaPipelineAsset) => {
      const briefId = readString(item.asset.ai_metadata?.assetBriefId);
      if (!briefId) return null;
      return readString(briefById.get(briefId)?.funnelId);
    },
    [briefById],
  );

  // ---- Effects: config & pipeline loading -----------------------------------
  useEffect(() => {
    let cancelled = false;
    getConfig(campaign.client_id)
      .then((data) => {
        if (cancelled) return;
        setConfig({
          adAccountId: data.adAccountId,
          pageId: data.pageId,
          pageName: data.pageName,
          pixelId: data.pixelId,
          graphApiVersion: data.graphApiVersion,
          validationStatus: data.validationStatus,
          lastValidatedAt: data.lastValidatedAt,
          lastValidationError: data.lastValidationError,
        });
        setConfigError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setConfig(null);
        setConfigError(getErrorMessage(err));
      });
    return () => { cancelled = true; };
  }, [campaign.client_id, getConfig]);

  useEffect(() => { void refreshPipeline(); }, [refreshPipeline]);

  useEffect(() => {
    if (!autoRefreshUntil) return;
    if (Date.now() >= autoRefreshUntil) { setAutoRefreshUntil(null); return; }
    const timer = window.setInterval(() => {
      if (Date.now() >= autoRefreshUntil) { window.clearInterval(timer); setAutoRefreshUntil(null); return; }
      void refreshPipeline();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [autoRefreshUntil, refreshPipeline]);

  // ---- Derived: generation summaries ----------------------------------------
  const creativeSpecCount = useMemo(
    () => pipeline.filter((item) => Boolean(item.creative_spec?.id)).length,
    [pipeline],
  );
  const adsetSpecCount = useMemo(() => {
    const ids = new Set<string>();
    pipeline.forEach((item) => (item.adset_specs || []).forEach((spec) => { if (spec.id) ids.add(spec.id); }));
    return ids.size;
  }, [pipeline]);
  const hasGeneratedAssets = pipeline.length > 0;

  const generationSummaries = useMemo(() => {
    const byGen = new Map<string, GenerationSummary>();
    pipeline.forEach((item) => {
      const gen = getGenerationGroup(item);
      const createdAt = item.asset.created_at ? new Date(item.asset.created_at).getTime() : 0;
      const existing = byGen.get(gen.key);
      if (!existing) {
        byGen.set(gen.key, { ...gen, latestCreatedAt: createdAt, count: 1 });
        return;
      }
      existing.latestCreatedAt = Math.max(existing.latestCreatedAt, createdAt);
      existing.count += 1;
    });
    return Array.from(byGen.values()).sort((a, b) => b.latestCreatedAt - a.latestCreatedAt);
  }, [pipeline]);

  const latestGenerationSummary = generationSummaries[0] ?? null;
  const latestGenerationKey = latestGenerationSummary?.key ?? null;
  const latestGenerationBatchId =
    latestGenerationSummary?.kind === "batch" ? latestGenerationSummary.key.slice("batch:".length) : null;

  // ---- Derived: funnel scope ------------------------------------------------
  const latestGenerationPipeline = useMemo(() => {
    if (!latestGenerationKey) return [];
    return pipeline.filter((item) => getGenerationGroup(item).key === latestGenerationKey);
  }, [latestGenerationKey, pipeline]);

  const latestGenerationFunnelIds = useMemo(() => {
    const ids = new Set<string>();
    latestGenerationPipeline.forEach((item) => {
      const fid = getPipelineItemFunnelId(item);
      if (fid) ids.add(fid);
    });
    return Array.from(ids);
  }, [getPipelineItemFunnelId, latestGenerationPipeline]);

  const funnelScopeOptions = useMemo(
    () => latestGenerationFunnelIds.map((fid) => ({
      label: formatFunnelLabel(funnelById.get(fid) || null, fid),
      value: fid,
    })),
    [funnelById, latestGenerationFunnelIds],
  );

  const latestGenerationUnmappedCount = useMemo(
    () => latestGenerationPipeline.filter((item) => !getPipelineItemFunnelId(item)).length,
    [getPipelineItemFunnelId, latestGenerationPipeline],
  );

  const activeFunnelId = selectedFunnelId || (latestGenerationFunnelIds.length === 1 ? latestGenerationFunnelIds[0] : null);
  const activeFunnel = activeFunnelId ? funnelById.get(activeFunnelId) || null : null;
  const activeFunnelLabel = isExternalDelivery
    ? "External destinations"
    : activeFunnelId
      ? formatFunnelLabel(activeFunnel, activeFunnelId)
      : null;

  // ---- Derived: pipeline visibility -----------------------------------------
  const baseVisiblePipeline = useMemo(() => {
    if (!latestGenerationOnly || !latestGenerationKey) return pipeline;
    return pipeline.filter((item) => getGenerationGroup(item).key === latestGenerationKey);
  }, [latestGenerationKey, latestGenerationOnly, pipeline]);

  const visiblePipeline = useMemo(() => {
    if (!activeFunnelId) {
      return requiresFunnelScope && latestGenerationFunnelIds.length > 1 ? [] : baseVisiblePipeline;
    }
    return baseVisiblePipeline.filter((item) => getPipelineItemFunnelId(item) === activeFunnelId);
  }, [activeFunnelId, baseVisiblePipeline, getPipelineItemFunnelId, latestGenerationFunnelIds.length, requiresFunnelScope]);

  const latestGenerationScopedPipeline = useMemo(() => {
    if (!activeFunnelId) return requiresFunnelScope ? [] : latestGenerationPipeline;
    return latestGenerationPipeline.filter((item) => getPipelineItemFunnelId(item) === activeFunnelId);
  }, [activeFunnelId, getPipelineItemFunnelId, latestGenerationPipeline, requiresFunnelScope]);

  const hiddenLegacyCount = useMemo(() => {
    if (!latestGenerationOnly || !latestGenerationKey) return 0;
    return pipeline.length - baseVisiblePipeline.length;
  }, [baseVisiblePipeline.length, latestGenerationKey, latestGenerationOnly, pipeline.length]);

  const hiddenOtherFunnelCount = useMemo(() => {
    if (!requiresFunnelScope || !activeFunnelId) return 0;
    return baseVisiblePipeline.length - visiblePipeline.length;
  }, [activeFunnelId, baseVisiblePipeline.length, requiresFunnelScope, visiblePipeline.length]);

  const visibleMissingCreativeSpecCount = useMemo(
    () => visiblePipeline.filter((item) => !item.creative_spec?.id).length,
    [visiblePipeline],
  );

  const visibleAssetBriefIds = useMemo(() => {
    const ids = new Set<string>();
    visiblePipeline.forEach((item) => {
      const bid = readString(item.asset.ai_metadata?.assetBriefId);
      if (bid) ids.add(bid);
    });
    return Array.from(ids);
  }, [visiblePipeline]);

  const prepareAssetBriefIds = visibleAssetBriefIds;

  // ---- Derived: publish selections ------------------------------------------
  const selectionByAssetId = useMemo(
    () => new Map(publishSelections.map((s) => [s.assetId, s])),
    [publishSelections],
  );
  const includedPackageItems = useMemo(
    () => latestGenerationScopedPipeline.filter((item) => selectionByAssetId.get(item.asset.id)?.decision !== "excluded"),
    [latestGenerationScopedPipeline, selectionByAssetId],
  );
  const excludedPackageCount = useMemo(
    () => latestGenerationScopedPipeline.filter((item) => selectionByAssetId.get(item.asset.id)?.decision === "excluded").length,
    [latestGenerationScopedPipeline, selectionByAssetId],
  );

  const canManagePublishPackage = latestGenerationOnly && Boolean(latestGenerationKey) && (!requiresFunnelScope || Boolean(activeFunnelId));
  const canPrepareMetaReview = latestGenerationOnly && Boolean(latestGenerationKey) && (!requiresFunnelScope || Boolean(activeFunnelId));
  const creativeQaState = useMemo(
    () =>
      resolveMetaCreativeQaState({
        runs: qaRuns,
        generationKey: latestGenerationKey,
        funnelId: activeFunnelId,
        requiresFunnelScope,
        qaRunsLoading,
        qaRunsError,
      }),
    [activeFunnelId, latestGenerationKey, qaRuns, qaRunsError, qaRunsLoading, requiresFunnelScope],
  );

  const availableBucketSpecs = useMemo(() => {
    const byId = new Map<string, MetaAdSetSpec>();
    includedPackageItems.forEach((item) => {
      (item.adset_specs || []).forEach((spec) => { if (!spec.id || byId.has(spec.id)) return; byId.set(spec.id, spec); });
    });
    return sortBucketSpecs(Array.from(byId.values()));
  }, [includedPackageItems]);
  const availableBucketCount = availableBucketSpecs.length;
  const publishBucketCount = useMemo(() => {
    const cleaned = publishCampaignForm.bucketCount.trim();
    if (!cleaned || !/^\d+$/.test(cleaned)) return DEFAULT_META_PUBLISH_BUCKET_COUNT;
    return clampPublishBucketCount(Number(cleaned));
  }, [publishCampaignForm.bucketCount]);
  const includedAdSetSpecs = useMemo(
    () => availableBucketSpecs.slice(0, publishBucketCount),
    [availableBucketSpecs, publishBucketCount],
  );

  // ---- Derived: grouped pipeline --------------------------------------------
  const groupedPipeline = useMemo(() => {
    const groups = new Map<number, GroupedPipelineEntry>();
    visiblePipeline.forEach((item) => {
      const reqIdx = readNumber(item.asset.ai_metadata?.requirementIndex);
      const creativeMetadata = (item.creative_spec?.metadata_json || {}) as Record<string, unknown>;
      const swipeCopyPack = readRecord(item.asset.ai_metadata?.swipeCopyPack);
      const requirement = (creativeMetadata.requirement || {}) as Record<string, unknown>;
      const title =
        readString(requirement.hook) ||
        readString(item.creative_spec?.headline) ||
        readString(swipeCopyPack?.metaHeadline) ||
        readString(swipeCopyPack?.selectedVariation) ||
        readString(item.creative_spec?.name) ||
        item.asset.public_id;
      const funnelStage = readString(requirement.funnelStage) || readString(swipeCopyPack?.funnelStage);
      const key = reqIdx ?? -1;
      const existing = groups.get(key);
      if (!existing) {
        groups.set(key, { requirementIndex: key, title, funnelStage, items: [item] });
        return;
      }
      existing.items.push(item);
    });
    return Array.from(groups.values())
      .sort((a, b) => a.requirementIndex - b.requirementIndex)
      .map((group) => ({
        ...group,
        items: group.items.sort((left, right) => {
          const li = readRecord(left.asset.ai_metadata?.swipeCopyInputs);
          const ri = readRecord(right.asset.ai_metadata?.swipeCopyInputs);
          const lm = readRecord(li?.adImageOrVideo);
          const rm = readRecord(ri?.adImageOrVideo);
          const ll = readString(lm?.sourceLabel) || readString(left.asset.ai_metadata?.swipeSourceLabel) || left.asset.public_id;
          const rl = readString(rm?.sourceLabel) || readString(right.asset.ai_metadata?.swipeSourceLabel) || right.asset.public_id;
          return ll.localeCompare(rl);
        }),
      }));
  }, [visiblePipeline]);

  const visiblePublishRuns = useMemo(() => {
    if (!requiresFunnelScope || !activeFunnelId) return publishRuns;
    return publishRuns.filter((run) => {
      const runFunnelId = readString(run.metadata?.funnelId);
      return !runFunnelId || runFunnelId === activeFunnelId;
    });
  }, [activeFunnelId, publishRuns, requiresFunnelScope]);

  // ---- Sync effects ---------------------------------------------------------
  useEffect(() => {
    if (!latestGenerationKey) return;
    setLatestGenerationOnly(true);
  }, [latestGenerationKey]);

  useEffect(() => {
    if (!latestGenerationFunnelIds.length) { setSelectedFunnelId(null); return; }
    if (latestGenerationFunnelIds.length === 1) { setSelectedFunnelId(latestGenerationFunnelIds[0]); return; }
    setSelectedFunnelId((cur) => (cur && latestGenerationFunnelIds.includes(cur) ? cur : null));
  }, [latestGenerationFunnelIds]);

  useEffect(() => {
    setPrepareError(null);
    setPrepareIssues([]);
    setPublishValidation(null);
    setPublishFormError(null);
  }, [activeFunnelId, latestGenerationKey]);

  useEffect(() => {
    let cancelled = false;
    setQaRunsLoading(true);
    setQaRunsError(null);
    get<PaidAdsQaRun[]>(`/campaigns/${campaign.id}/paid-ads-qa/runs?limit=50`)
      .then((data) => {
        if (cancelled) return;
        setQaRuns(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setQaRuns([]);
        setQaRunsError(getErrorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setQaRunsLoading(false);
      });
    return () => { cancelled = true; };
  }, [campaign.id, get]);

  useEffect(() => {
    if (!latestGenerationKey) {
      setPublishSelections([]); setSelectionError(null); setSelectionLoading(false);
      return;
    }
    let cancelled = false;
    setSelectionLoading(true);
    setSelectionError(null);
    listPublishSelections(campaign.id, latestGenerationKey)
      .then((data) => { if (!cancelled) setPublishSelections(data); })
      .catch((err) => { if (!cancelled) { setPublishSelections([]); setSelectionError(getErrorMessage(err)); } })
      .finally(() => { if (!cancelled) setSelectionLoading(false); });
    return () => { cancelled = true; };
  }, [campaign.id, latestGenerationKey, listPublishSelections]);

  useEffect(() => {
    setPublishCampaignForm((cur) => {
      const cleanedCur = cur.publishBaseUrl.trim();
      const browserDefault = (browserReviewBaseUrl || "").trim();
      if (cleanedCur && cleanedCur !== browserDefault) return cur;
      return { ...cur, publishBaseUrl: reviewBaseUrl || "" };
    });
  }, [browserReviewBaseUrl, reviewBaseUrl]);

  useEffect(() => {
    setPublishAdSetForms((cur) => {
      const next: Record<string, MetaPublishAdSetForm> = { ...cur };
      includedAdSetSpecs.forEach((spec) => {
        const seeded = buildAdSetForm(spec, { pageName: config?.pageName });
        const existing = cur[spec.id];
        if (!existing) {
          next[spec.id] = seeded;
          return;
        }
        next[spec.id] = {
          ...existing,
          dsaBeneficiary: existing.dsaBeneficiary.trim() || seeded.dsaBeneficiary,
          dsaPayor: existing.dsaPayor.trim() || seeded.dsaPayor,
        };
      });
      return next;
    });
  }, [config?.pageName, includedAdSetSpecs]);

  useEffect(() => {
    let cancelled = false;
    setPublishRunsLoading(true);
    setPublishRunsError(null);
    listPublishRuns(campaign.id)
      .then((data) => { if (!cancelled) setPublishRuns(data); })
      .catch((err) => { if (!cancelled) { setPublishRuns([]); setPublishRunsError(getErrorMessage(err)); } })
      .finally(() => { if (!cancelled) setPublishRunsLoading(false); });
    return () => { cancelled = true; };
  }, [campaign.id, listPublishRuns]);

  // ---- Action handlers ------------------------------------------------------
  const handleGenerateAssets = useCallback(async () => {
    setGenerateError(null);
    if (!assetBriefIds.length) { setGenerateError("No asset briefs exist for this campaign yet."); return; }
    if (!selectedSwipeCollectionId) {
      setGenerateError("Select a swipe collection before generating creatives.");
      return;
    }
    setGeneratePending(true);
    try {
      const response = await post<{ workflow_run_id: string }>(`/campaigns/${campaign.id}/creative/produce`, {
        assetBriefIds,
        swipeCollectionId: selectedSwipeCollectionId,
      });
      setLastWorkflowRunId(response.workflow_run_id);
      setAutoRefreshUntil(Date.now() + 3 * 60 * 1000);
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      await refreshPipeline();
    } catch (err) {
      setGenerateError(getErrorMessage(err));
    } finally {
      setGeneratePending(false);
    }
  }, [assetBriefIds, campaign.id, post, queryClient, refreshPipeline, selectedSwipeCollectionId]);

  const handlePrepareMetaReview = useCallback(async () => {
    setPrepareError(null);
    setPrepareIssues([]);
    if (requiresFunnelScope && !activeFunnelId) {
      setPrepareError("Pick one funnel in the Meta ads tab before preparing Meta review.");
      return;
    }
    if (!prepareAssetBriefIds.length) {
      setPrepareError(
        canPrepareMetaReview && latestGenerationSummary
          ? "No generated assets exist in the visible generation yet."
          : "Switch to the latest generation and select a funnel before preparing Meta review.",
      );
      return;
    }
    setPreparePending(true);
    try {
      await post(`/campaigns/${campaign.id}/meta/review-setup`, {
        assetBriefIds: prepareAssetBriefIds,
        funnelId: requiresFunnelScope ? activeFunnelId : undefined,
        generationBatchId: latestGenerationOnly && latestGenerationSummary?.kind === "batch" ? latestGenerationBatchId : undefined,
        bucketCount: publishBucketCount,
      });
      setLastPreparedAt(new Date().toISOString());
      setPrepareIssues([]);
      await refreshPipeline();
    } catch (err) {
      const apiError = err as ApiError;
      const detail = readRecord((apiError.raw as { detail?: unknown } | undefined)?.detail);
      const invalidAssets = Array.isArray(detail?.invalidAssets) ? detail.invalidAssets : [];
      const parsedIssues: MetaReviewSetupIssue[] = [];
      for (const entry of invalidAssets) {
        const record = readRecord(entry);
        if (!record) continue;
        const issues: MetaReviewSetupIssue["issues"] = [];
        if (Array.isArray(record.issues)) {
          for (const issue of record.issues) {
            const ir = readRecord(issue);
            if (ir) issues.push({ ruleId: readString(ir.ruleId), title: readString(ir.title), message: readString(ir.message) });
          }
        }
        parsedIssues.push({
          assetId: readString(record.assetId) || "unknown",
          assetBriefId: readString(record.assetBriefId),
          generationKey: readString(record.generationKey),
          funnelId: readString(record.funnelId),
          destinationPage: readString(record.destinationPage),
          normalizedDestinationPage: readString(record.normalizedDestinationPage),
          issues,
        });
      }
      setPrepareIssues(parsedIssues);
      setPrepareError(getErrorMessage(err));
    } finally {
      setPreparePending(false);
    }
  }, [activeFunnelId, campaign.id, canPrepareMetaReview, latestGenerationBatchId, latestGenerationOnly, latestGenerationSummary, post, prepareAssetBriefIds, publishBucketCount, refreshPipeline, requiresFunnelScope]);

  const handleSetPublishDecision = useCallback(
    async (assetId: string, decision: MetaPublishSelectionDecision | null) => {
      if (!latestGenerationKey) return;
      setSelectionError(null);
      setSelectionPendingAssetIds((cur) => (cur.includes(assetId) ? cur : [...cur, assetId]));
      try {
        const next = await savePublishSelections(campaign.id, { generationKey: latestGenerationKey, decisions: [{ assetId, decision }] });
        setPublishSelections(next);
      } catch (err) {
        setSelectionError(getErrorMessage(err));
      } finally {
        setSelectionPendingAssetIds((cur) => cur.filter((id) => id !== assetId));
      }
    },
    [campaign.id, latestGenerationKey, savePublishSelections],
  );

  const updatePublishCampaignField = useCallback(
    <K extends keyof MetaPublishCampaignForm>(field: K, value: MetaPublishCampaignForm[K]) => {
      setPublishCampaignForm((cur) => ({ ...cur, [field]: value }));
    },
    [],
  );

  const setPublishBucketCount = useCallback((value: string) => {
    setPublishCampaignForm((cur) => {
      const cleaned = value.trim();
      if (!cleaned) {
        return { ...cur, bucketCount: value };
      }
      if (!/^\d+$/.test(cleaned)) {
        return { ...cur, bucketCount: value };
      }
      const nextBucketCount = clampPublishBucketCount(Number(cleaned));
      return {
        ...cur,
        bucketCount: String(nextBucketCount),
        bucketDestinationUrls: resizeBucketDestinationUrls(cur.bucketDestinationUrls, nextBucketCount),
      };
    });
  }, []);

  const updatePublishBucketDestinationUrl = useCallback((bucketIndex: number, value: string) => {
    setPublishCampaignForm((cur) => {
      const nextBucketCount = publishBucketCount;
      const nextUrls = resizeBucketDestinationUrls(cur.bucketDestinationUrls, nextBucketCount);
      nextUrls[bucketIndex - 1] = value;
      return {
        ...cur,
        bucketDestinationUrls: nextUrls,
      };
    });
  }, [publishBucketCount]);

  const updatePublishAdSetField = useCallback(
    <K extends keyof MetaPublishAdSetForm>(specId: string, field: K, value: MetaPublishAdSetForm[K]) => {
      setPublishAdSetForms((cur) => ({
        ...cur,
        [specId]: {
          ...(cur[specId] ||
            buildAdSetForm(
              includedAdSetSpecs.find((s) => s.id === specId) || ({ id: specId, name: "", status: "draft" } as MetaAdSetSpec),
              { pageName: config?.pageName },
            )),
          [field]: value,
        },
      }));
    },
    [config?.pageName, includedAdSetSpecs],
  );

  const buildPublishRequestPayload = useCallback(() => {
    if (!latestGenerationKey) throw new Error("No latest generation is selected for publish.");
    if (requiresFunnelScope && !activeFunnelId) throw new Error("Pick one funnel before validating or publishing the Meta package.");
    const bucketCount = parseIntegerInput(publishCampaignForm.bucketCount, "Bucket count");
    if (bucketCount == null) {
      throw new Error("Bucket count is required.");
    }
    if (bucketCount < 1 || bucketCount > MAX_META_PUBLISH_BUCKET_COUNT) {
      throw new Error(`Bucket count must be between 1 and ${MAX_META_PUBLISH_BUCKET_COUNT}.`);
    }
    const bucketDestinationUrls = resizeBucketDestinationUrls(
      publishCampaignForm.bucketDestinationUrls,
      bucketCount,
    ).map((entry) => entry.trim());
    const nonEmptyBucketDestinationUrlCount = bucketDestinationUrls.filter(Boolean).length;
    if (
      nonEmptyBucketDestinationUrlCount > 0 &&
      nonEmptyBucketDestinationUrlCount !== bucketCount
    ) {
      throw new Error(
        "Provide either all bucket destination URLs or leave every bucket destination override blank.",
      );
    }
    return {
      generationKey: latestGenerationKey,
      funnelId: requiresFunnelScope ? activeFunnelId : null,
      publishBaseUrl: publishCampaignForm.publishBaseUrl.trim(),
      campaignName: publishCampaignForm.campaignName.trim(),
      campaignObjective: publishCampaignForm.campaignObjective.trim(),
      buyingType: publishCampaignForm.buyingType.trim() || null,
      specialAdCategories: publishCampaignForm.specialAdCategories.split(",").map((e) => e.trim()).filter(Boolean),
      campaignDailyBudget: parseIntegerInput(publishCampaignForm.campaignDailyBudget, "Campaign daily budget"),
      bucketCount,
      bucketDestinationUrls:
        nonEmptyBucketDestinationUrlCount === bucketCount ? bucketDestinationUrls : [],
    };
  }, [activeFunnelId, latestGenerationKey, publishCampaignForm, requiresFunnelScope]);

  const persistPublishAdSetConfigs = useCallback(async () => {
    for (const spec of includedAdSetSpecs) {
      const form = publishAdSetForms[spec.id] || buildAdSetForm(spec, { pageName: config?.pageName });
      const attributionSpec =
        parseJsonObjectArrayInput(form.attributionSpecJson, `${spec.name || spec.id} attribution spec`) || cloneDefaultAttributionSpec();
      const existingMetadata = readRecord(spec.metadata_json) || {};
      await updateAdSetSpec(spec.id, {
        name: form.name.trim() || null,
        optimizationGoal: form.optimizationGoal.trim() || null,
        billingEvent: form.billingEvent.trim() || null,
        targeting: parseJsonObjectInput(form.targetingJson, `${spec.name || spec.id} targeting`),
        placements: parseJsonObjectInput(form.placementsJson, `${spec.name || spec.id} placements`),
        dailyBudget: parseIntegerInput(form.dailyBudget, `${spec.name || spec.id} daily budget`),
        lifetimeBudget: parseIntegerInput(form.lifetimeBudget, `${spec.name || spec.id} lifetime budget`),
        bidAmount: null,
        dsaBeneficiary: form.dsaBeneficiary.trim() || readString(config?.pageName) || null,
        dsaPayor: form.dsaPayor.trim() || readString(config?.pageName) || null,
        startTime: fromLocalDateTimeValue(form.startTime),
        endTime: fromLocalDateTimeValue(form.endTime),
        promotedObject: buildPromotedObjectPayload(form, {
          specLabel: spec.name || spec.id,
          defaultPixelId:
            config?.validationStatus === "valid" && config?.lastValidatedAt
              ? config.pixelId
              : null,
        }),
        conversionDomain: form.conversionDomain.trim() || null,
        metadata: {
          ...existingMetadata,
          attributionSpec,
        },
      });
    }
  }, [config?.lastValidatedAt, config?.pageName, config?.pixelId, config?.validationStatus, includedAdSetSpecs, publishAdSetForms, updateAdSetSpec]);

  const refreshPublishRuns = useCallback(async () => {
    setPublishRunsLoading(true);
    setPublishRunsError(null);
    try {
      setPublishRuns(await listPublishRuns(campaign.id));
    } catch (err) {
      setPublishRunsError(getErrorMessage(err));
    } finally {
      setPublishRunsLoading(false);
    }
  }, [campaign.id, listPublishRuns]);

  const handleValidatePublishPlan = useCallback(async () => {
    setPublishFormError(null);
    setPublishValidation(null);
    setPublishValidationPending(true);
    try {
      await persistPublishAdSetConfigs();
      await refreshPipeline();
      setPublishValidation(await validatePublishPlan(campaign.id, buildPublishRequestPayload()));
    } catch (err) {
      setPublishFormError(getErrorMessage(err));
      const apiError = err as ApiError;
      const v = readRecord((apiError.raw as { detail?: unknown } | undefined)?.detail)?.validation;
      if (readRecord(v)) setPublishValidation(readRecord(v) as unknown as MetaPublishPlanValidation);
    } finally {
      setPublishValidationPending(false);
    }
  }, [buildPublishRequestPayload, campaign.id, persistPublishAdSetConfigs, refreshPipeline, refreshPublishRuns, validatePublishPlan]);

  const handlePublishToMeta = useCallback(async () => {
    setPublishFormError(null);
    setPublishPending(true);
    try {
      await persistPublishAdSetConfigs();
      await refreshPipeline();
      const run = await createPublishRun(campaign.id, buildPublishRequestPayload());
      setPublishValidation((run.metadata.validation as MetaPublishPlanValidation | undefined) || null);
      await refreshPublishRuns();
    } catch (err) {
      setPublishFormError(getErrorMessage(err));
      const apiError = err as ApiError;
      const v = readRecord((apiError.raw as { detail?: unknown } | undefined)?.detail)?.validation;
      if (readRecord(v)) setPublishValidation(readRecord(v) as unknown as MetaPublishPlanValidation);
      await refreshPublishRuns();
    } finally {
      setPublishPending(false);
    }
  }, [buildPublishRequestPayload, campaign.id, createPublishRun, persistPublishAdSetConfigs, refreshPipeline, refreshPublishRuns]);

  // ---- Workflow phase -------------------------------------------------------
  const currentPhase = useMemo<MetaWorkflowPhase>(() => {
    if (!hasGeneratedAssets) return "generate";
    if (creativeSpecCount === 0) return "generate";
    return "review";
  }, [hasGeneratedAssets, creativeSpecCount]);

  // ---- Build context value --------------------------------------------------
  const value = useMemo<MetaPublishContextValue>(
    () => ({
      campaign,
      assetBriefs,
      config,
      configError,
      pipeline,
      pipelineLoading,
      pipelineError,
      refreshPipeline,
      generatePending,
      generateError,
      selectedSwipeCollectionId,
      setSelectedSwipeCollectionId,
      handleGenerateAssets,
      autoRefreshUntil,
      lastWorkflowRunId,
      preparePending,
      prepareError,
      prepareIssues,
      lastPreparedAt,
      handlePrepareMetaReview,
      latestGenerationOnly,
      setLatestGenerationOnly,
      selectedFunnelId,
      setSelectedFunnelId,
      packageView,
      setPackageView,
      assetBriefIds,
      briefById,
      funnelById,
      isExternalDelivery,
      requiresFunnelScope,
      hasGeneratedAssets,
      creativeSpecCount,
      adsetSpecCount,
      generationSummaries,
      latestGenerationSummary,
      latestGenerationKey,
      latestGenerationBatchId,
      latestGenerationFunnelIds,
      funnelScopeOptions,
      latestGenerationUnmappedCount,
      activeFunnelId,
      activeFunnel,
      activeFunnelLabel,
      funnelsLoading: funnelsQuery.isLoading,
      funnelsError: funnelsQuery.error,
      visiblePipeline,
      latestGenerationScopedPipeline,
      hiddenLegacyCount,
      hiddenOtherFunnelCount,
      visibleMissingCreativeSpecCount,
      prepareAssetBriefIds,
      groupedPipeline,
      canManagePublishPackage,
      canPrepareMetaReview,
      creativeReviewQaRuns: creativeQaState.reviewRuns,
      creativeQaFilteringEnabled: creativeQaState.filteringEnabled,
      creativeQaNotice: creativeQaState.notice,
      includedPackageItems,
      excludedPackageCount,
      availableBucketCount,
      includedAdSetSpecs,
      publishSelections,
      selectionByAssetId,
      selectionLoading,
      selectionError,
      selectionPendingAssetIds,
      handleSetPublishDecision,
      publishCampaignForm,
      publishBucketCount,
      updatePublishCampaignField,
      setPublishBucketCount,
      updatePublishBucketDestinationUrl,
      publishAdSetForms,
      updatePublishAdSetField,
      publishFormError,
      publishValidation,
      publishValidationPending,
      publishPending,
      handleValidatePublishPlan,
      handlePublishToMeta,
      publishRuns,
      visiblePublishRuns,
      publishRunsLoading,
      publishRunsError,
      reviewBaseUrl,
      currentPhase,
      getPipelineItemFunnelId,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally wide deps
    [
      campaign, assetBriefs, config, configError, pipeline, pipelineLoading, pipelineError, refreshPipeline,
      generatePending, generateError, selectedSwipeCollectionId, handleGenerateAssets, autoRefreshUntil, lastWorkflowRunId,
      preparePending, prepareError, prepareIssues, lastPreparedAt, handlePrepareMetaReview,
      latestGenerationOnly, selectedFunnelId, packageView,
      assetBriefIds, briefById, funnelById, isExternalDelivery, requiresFunnelScope,
      hasGeneratedAssets, creativeSpecCount, adsetSpecCount,
      generationSummaries, latestGenerationSummary, latestGenerationKey, latestGenerationBatchId,
      latestGenerationFunnelIds, funnelScopeOptions, latestGenerationUnmappedCount,
      activeFunnelId, activeFunnel, activeFunnelLabel, funnelsQuery.isLoading, funnelsQuery.error,
      visiblePipeline, latestGenerationScopedPipeline, hiddenLegacyCount, hiddenOtherFunnelCount,
      visibleMissingCreativeSpecCount, prepareAssetBriefIds, groupedPipeline,
      canManagePublishPackage, canPrepareMetaReview, includedPackageItems, excludedPackageCount,
      creativeQaState,
      availableBucketCount, includedAdSetSpecs, publishBucketCount, publishSelections, selectionByAssetId, selectionLoading, selectionError, selectionPendingAssetIds,
      handleSetPublishDecision, publishCampaignForm, updatePublishCampaignField, setPublishBucketCount, updatePublishBucketDestinationUrl,
      publishAdSetForms, updatePublishAdSetField, publishFormError,
      publishValidation, publishValidationPending, publishPending,
      handleValidatePublishPlan, handlePublishToMeta,
      publishRuns, visiblePublishRuns, publishRunsLoading, publishRunsError,
      reviewBaseUrl, currentPhase, getPipelineItemFunnelId,
    ],
  );

  return <MetaPublishCtx.Provider value={value}>{children}</MetaPublishCtx.Provider>;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useMetaPublishContext() {
  const ctx = useContext(MetaPublishCtx);
  if (!ctx) throw new Error("useMetaPublishContext must be used within a MetaPublishProvider");
  return ctx;
}
