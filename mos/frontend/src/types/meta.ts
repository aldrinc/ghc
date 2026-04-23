export type MetaCreativeSpec = {
  id: string;
  asset_id: string;
  campaign_id?: string | null;
  experiment_id?: string | null;
  name?: string | null;
  primary_text?: string | null;
  headline?: string | null;
  description?: string | null;
  call_to_action_type?: string | null;
  destination_url?: string | null;
  page_id?: string | null;
  instagram_actor_id?: string | null;
  status?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
};

export type MetaAdSetSpec = {
  id: string;
  campaign_id?: string | null;
  experiment_id?: string | null;
  name?: string | null;
  status?: string | null;
  optimization_goal?: string | null;
  billing_event?: string | null;
  targeting?: Record<string, unknown> | null;
  placements?: Record<string, unknown> | null;
  daily_budget?: number | null;
  lifetime_budget?: number | null;
  bid_amount?: number | null;
  dsa_beneficiary?: string | null;
  dsa_payor?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  promoted_object?: Record<string, unknown> | null;
  conversion_domain?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
};

export type MetaAssetUpload = {
  id: string;
  asset_id: string;
  media_type?: string | null;
  meta_image_hash?: string | null;
  meta_video_id?: string | null;
  status?: string | null;
  created_at?: string;
};

export type MetaAdCreative = {
  id: string;
  asset_id?: string | null;
  meta_creative_id: string;
  name?: string | null;
  status?: string | null;
  created_at?: string;
};

export type MetaAd = {
  id: string;
  meta_ad_id: string;
  meta_adset_id: string;
  meta_creative_id: string;
  name?: string | null;
  status?: string | null;
  created_at?: string;
};

export type MetaCampaign = {
  id: string;
  meta_campaign_id: string;
  name?: string | null;
  objective?: string | null;
  status?: string | null;
  created_at?: string;
};

export type MetaPublishSelectionDecision = "excluded";

export type MetaPublishSelection = {
  id: string;
  campaignId: string;
  assetId: string;
  generationKey: string;
  decision: MetaPublishSelectionDecision;
  decidedByUserId?: string | null;
  createdAt: string;
  updatedAt: string;
};

export type MetaPublishSelectionMutation = {
  assetId: string;
  decision?: MetaPublishSelectionDecision | null;
};

export type MetaAdSetSpecUpdatePayload = {
  name?: string | null;
  optimizationGoal?: string | null;
  billingEvent?: string | null;
  targeting?: Record<string, unknown> | null;
  placements?: Record<string, unknown> | null;
  dailyBudget?: number | null;
  lifetimeBudget?: number | null;
  bidAmount?: number | null;
  dsaBeneficiary?: string | null;
  dsaPayor?: string | null;
  startTime?: string | null;
  endTime?: string | null;
  promotedObject?: Record<string, unknown> | null;
  conversionDomain?: string | null;
  metadata?: Record<string, unknown> | null;
};

export type MetaPublishPlanValidationItem = {
  assetId: string;
  creativeSpecId?: string | null;
  adsetSpecId?: string | null;
  bucketIndex?: number | null;
  resolvedDestinationUrl?: string | null;
  status: "ok" | "blocked";
  blockers: string[];
};

export type MetaPublishPlanValidation = {
  campaignId: string;
  generationKey: string;
  ok: boolean;
  includedCount: number;
  adsetCount: number;
  bucketCount: number;
  publishBaseUrl: string;
  publishDomain?: string | null;
  budgetScope?: "campaign" | "adset" | "mixed";
  campaignDailyBudget?: number | null;
  bucketDestinationUrls: string[];
  blockers: string[];
  items: MetaPublishPlanValidationItem[];
};

export type MetaPublishRunRequest = {
  generationKey: string;
  funnelId?: string | null;
  metaConfigId?: string | null;
  publishBaseUrl: string;
  campaignName: string;
  campaignObjective: string;
  buyingType?: string | null;
  specialAdCategories?: string[];
  campaignDailyBudget?: number | null;
  bucketCount?: number | null;
  bucketDestinationUrls?: string[];
};

export type MetaPublishRunItem = {
  id: string;
  assetId: string;
  creativeSpecId?: string | null;
  adsetSpecId?: string | null;
  status: string;
  resolvedDestinationUrl?: string | null;
  metaAssetUploadId?: string | null;
  metaCreativeId?: string | null;
  metaAdSetId?: string | null;
  metaAdId?: string | null;
  errorMessage?: string | null;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};

export type MetaPublishRun = {
  id: string;
  campaignId: string;
  generationKey: string;
  status: string;
  campaignName: string;
  campaignObjective: string;
  buyingType?: string | null;
  specialAdCategories: string[];
  publishBaseUrl: string;
  publishDomain?: string | null;
  metaConfigId?: string | null;
  adAccountId?: string | null;
  pageId?: string | null;
  metaCampaignId?: string | null;
  managementMetaCampaignId?: string | null;
  errorMessage?: string | null;
  metadata: Record<string, unknown>;
  items: MetaPublishRunItem[];
  createdByUserId?: string | null;
  createdAt: string;
  updatedAt: string;
  completedAt?: string | null;
};

export type MetaPipelineAsset = {
  asset: {
    id: string;
    public_id: string;
    status?: string | null;
    asset_kind?: string | null;
    client_id?: string | null;
    campaign_id?: string | null;
    experiment_id?: string | null;
    asset_brief_artifact_id?: string | null;
    file_status?: string | null;
    content_type?: string | null;
    width?: number | null;
    height?: number | null;
    created_at?: string;
    public_url?: string | null;
    ai_metadata?: Record<string, unknown> | null;
  };
  campaign?: { id: string; name: string } | null;
  experiment?: { id: string; name: string } | null;
  creative_spec?: MetaCreativeSpec | null;
  adset_specs?: MetaAdSetSpec[];
  meta?: {
    upload?: MetaAssetUpload | null;
    creatives?: MetaAdCreative[];
    ads?: MetaAd[];
    meta_campaign?: MetaCampaign | null;
  };
};

export type MetaConnectionWorkspaceUsage = {
  clientId: string;
  clientName: string;
  configId: string;
  configName: string;
  isDefault: boolean;
};

export type MetaAdAccountConnection = {
  id: string;
  orgId: string;
  name: string;
  adAccountId?: string | null;
  adAccountName?: string | null;
  businessManagerId?: string | null;
  businessManagerName?: string | null;
  graphApiVersion: string;
  graphApiBaseUrl: string;
  credentialType: string;
  hasCredentials: boolean;
  tokenExpiresAt?: string | null;
  status: string;
  validationStatus: string;
  lastValidatedAt?: string | null;
  lastValidationError?: string | null;
  metadata: Record<string, unknown>;
  usedByWorkspaces: MetaConnectionWorkspaceUsage[];
  createdByUserId?: string | null;
  createdAt: string;
  updatedAt: string;
};

export type MetaWorkspaceAdConfig = {
  id: string;
  orgId: string;
  clientId: string;
  connectionId: string;
  name: string;
  isDefault: boolean;
  status: string;
  pageId?: string | null;
  pageName?: string | null;
  instagramActorId?: string | null;
  pixelId?: string | null;
  dataSetId?: string | null;
  verifiedDomain?: string | null;
  verifiedDomainStatus?: string | null;
  trackingProvider?: string | null;
  trackingUrlParameters?: string | null;
  attributionClickWindow?: string | null;
  attributionViewWindow?: string | null;
  viewThroughEnabled?: boolean | null;
  validationStatus: string;
  lastValidatedAt?: string | null;
  lastValidationError?: string | null;
  metadata: Record<string, unknown>;
  createdByUserId?: string | null;
  createdAt: string;
  updatedAt: string;
  connection: MetaAdAccountConnection;
};

export type MetaAdAccountConnectionUpsertPayload = {
  name: string;
  adAccountId?: string | null;
  adAccountName?: string | null;
  businessManagerId?: string | null;
  businessManagerName?: string | null;
  graphApiVersion: string;
  graphApiBaseUrl?: string;
  accessToken?: string | null;
  tokenExpiresAt?: string | null;
  status?: string;
  metadata?: Record<string, unknown>;
};

export type MetaWorkspaceAdConfigCreatePayload = {
  connectionId: string;
  name: string;
  isDefault?: boolean;
  pageId?: string | null;
  pageName?: string | null;
  instagramActorId?: string | null;
  pixelId?: string | null;
  dataSetId?: string | null;
  verifiedDomain?: string | null;
  verifiedDomainStatus?: string | null;
  trackingProvider?: string | null;
  trackingUrlParameters?: string | null;
  attributionClickWindow?: string | null;
  attributionViewWindow?: string | null;
  viewThroughEnabled?: boolean | null;
  status?: string;
  metadata?: Record<string, unknown>;
};

export type MetaManagementPlanRequest = {
  metaCampaignId: string;
  clientId?: string | null;
  metaConfigId?: string | null;
  mode?: "plan_only" | "apply";
  datePreset?: string;
  includeRaw?: boolean;
  refresh?: boolean;
  benchmarkMode?: "disabled" | "best_effort" | "required";
  evaluateBenchmarks?: boolean | null;
  cutRules?: {
    minSpend?: number;
    maxCpm?: number;
    minLinkCtr?: number;
    maxLinkCpc?: number;
  } | null;
  eventMappings?: {
    landingPageViewActionType?: string;
    contentViewActionType?: string;
    addToCartActionType?: string;
    initiateCheckoutActionType?: string;
    purchaseActionType?: string;
    purchaseValueActionType?: string;
  } | null;
};

export type MetaManagementAdMetrics = {
  adId: string;
  adName: string;
  adsetId?: string | null;
  campaignId?: string | null;
  impressions: number;
  spend: number;
  cpm: number;
  frequency?: number | null;
  inlineLinkClicks?: number | null;
  linkCtrPct?: number | null;
  linkCpc?: number | null;
  hookRatePct?: number | null;
  holdRatePct?: number | null;
  atcRatioPct?: number | null;
  purchaseRatioPct?: number | null;
  aov?: number | null;
  raw: Record<string, unknown>;
  warnings: string[];
};

export type MetaManagementPlannedAction = {
  kind: string;
  metaAdId: string;
  reason: string;
  triggeredRules: string[];
  metrics: Record<string, unknown>;
};

export type MetaManagementAppliedAction = {
  kind: string;
  metaEntityId: string;
  status: string;
  requestPayload: Record<string, unknown>;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  error?: string | null;
};

export type MetaObjectStatusCount = {
  value: string;
  count: number;
};

export type MetaIssueSample = {
  adId: string;
  adName: string;
  adsetId?: string | null;
  status?: string | null;
  effectiveStatus?: string | null;
  errorCode?: number | null;
  errorSummary?: string | null;
  errorMessage?: string | null;
};

export type MetaObjectStateSummary = {
  campaignStatus?: string | null;
  campaignEffectiveStatus?: string | null;
  adsetCount: number;
  adCount: number;
  insightsRowCount: number;
  deliveryState: string;
  deliverySummary: string;
  adsetStatusCounts: MetaObjectStatusCount[];
  adsetEffectiveStatusCounts: MetaObjectStatusCount[];
  adStatusCounts: MetaObjectStatusCount[];
  adEffectiveStatusCounts: MetaObjectStatusCount[];
  issueCount: number;
  reviewPendingCount: number;
  issueSamples: MetaIssueSample[];
};

export type MetaManagementBenchmarkContext = {
  clientId: string;
  campaignId: string;
  metaCampaignId: string;
  datePreset: string;
  funnelId: string;
  publicationId: string;
  deliveryMode: string;
  profileId: string;
  priceCents?: number | null;
  priceDollars?: number | null;
  atcPriceBandId?: string | null;
  atcPriceBandLabel?: string | null;
  priceResolutionError?: string | null;
  profileUpdatedAt?: string | null;
};

export type MetaManagementFunnelSnapshot = {
  startedAt: string;
  endedAt: string;
  presellPageId?: string | null;
  salesPageId: string;
  presellPageViewSessions: number;
  presellCtaClickSessions: number;
  salesPageViewSessions: number;
  checkoutStartedSessions: number;
  orderCompletedSessions: number;
  presellCtrPct?: number | null;
  salesPdpAtcPct?: number | null;
  salesPdpPurchaseCvrPct?: number | null;
  checkoutCvrPct?: number | null;
};

export type MetaManagementBenchmarkEvaluationStatus =
  | "below_target"
  | "on_target"
  | "good"
  | "insufficient_data"
  | "unavailable"
  | "not_applicable";

export type MetaManagementBenchmarkEvaluation = {
  metricId: string;
  label: string;
  scope: string;
  status: MetaManagementBenchmarkEvaluationStatus;
  value?: number | null;
  unit: string;
  minimum?: number | null;
  target?: number | null;
  good?: number | null;
  numerator?: number | null;
  denominator?: number | null;
  reason?: string | null;
  context: Record<string, unknown>;
};

export type MetaManagementCustomMetricDefinition = {
  metricId: string;
  label: string;
  description: string;
  formula: string;
  sourcePlane: string;
  sourceClass: string;
  unit: string;
  numeratorLabel: string;
  denominatorLabel: string;
  minimum?: number | null;
  target?: number | null;
  good?: number | null;
};

export type MetaManagementCustomMetricEvaluationStatus =
  | "below_target"
  | "on_target"
  | "good"
  | "insufficient_data"
  | "unavailable"
  | "target_not_configured";

export type MetaManagementCustomMetricEvaluation = {
  metricId: string;
  scope: string;
  status: MetaManagementCustomMetricEvaluationStatus;
  value?: number | null;
  unit: string;
  numerator?: number | null;
  denominator?: number | null;
  minimum?: number | null;
  target?: number | null;
  good?: number | null;
  resolvedSources: string[];
  warnings: string[];
  reason?: string | null;
  recommendation?: string | null;
};

export type MetaManagementCustomMetricRow = {
  adId: string;
  adName: string;
  metrics: MetaManagementCustomMetricEvaluation[];
};

export type MetaManagementPlan = {
  mode: string;
  generatedAt: string;
  window: Record<string, unknown>;
  campaign: Record<string, unknown>;
  adsets: Record<string, unknown>[];
  objectState: MetaObjectStateSummary;
  observedActionTypes: Record<string, string[]>;
  rows: MetaManagementAdMetrics[];
  actions: MetaManagementPlannedAction[];
  appliedActions: MetaManagementAppliedAction[];
  warnings: string[];
  managementScope: "meta_only" | "meta_plus_funnel";
  benchmarkStatus: {
    requestedMode: "disabled" | "best_effort" | "required";
    available: boolean;
    reasonCode?: string | null;
    reason?: string | null;
  };
  benchmarkContext?: MetaManagementBenchmarkContext | null;
  funnelSnapshot?: MetaManagementFunnelSnapshot | null;
  benchmarkEvaluations: MetaManagementBenchmarkEvaluation[];
  customMetricDefinitions: MetaManagementCustomMetricDefinition[];
  customMetricSummary: MetaManagementCustomMetricEvaluation[];
  customMetricRows: MetaManagementCustomMetricRow[];
  artifacts?: {
    metricsSnapshotArtifactId?: string;
    recommendedActionsArtifactId?: string;
    approvalDecisionArtifactId?: string;
  };
};

export type MetaRemoteResponse<T> = {
  data: T[];
  paging?: Record<string, unknown>;
};

export type MetaRemoteImage = {
  hash: string;
  name?: string | null;
  url?: string | null;
  created_time?: string | null;
  updated_time?: string | null;
};

export type MetaRemoteVideo = {
  id: string;
  title?: string | null;
  status?: string | null;
  length?: number | null;
  created_time?: string | null;
  updated_time?: string | null;
  thumbnail_url?: string | null;
  source?: string | null;
};

export type MetaRemoteCreative = {
  id: string;
  name?: string | null;
  status?: string | null;
  object_story_spec?: Record<string, unknown> | null;
  created_time?: string | null;
  updated_time?: string | null;
};

export type MetaRemoteCampaign = {
  id: string;
  name?: string | null;
  status?: string | null;
  effective_status?: string | null;
  objective?: string | null;
  created_time?: string | null;
  updated_time?: string | null;
};

export type MetaRemoteAdSet = {
  id: string;
  name?: string | null;
  status?: string | null;
  effective_status?: string | null;
  campaign_id?: string | null;
  created_time?: string | null;
  updated_time?: string | null;
};

export type MetaRemoteAd = {
  id: string;
  name?: string | null;
  status?: string | null;
  effective_status?: string | null;
  adset_id?: string | null;
  campaign_id?: string | null;
  creative?: { id?: string } | null;
  created_time?: string | null;
  updated_time?: string | null;
};
