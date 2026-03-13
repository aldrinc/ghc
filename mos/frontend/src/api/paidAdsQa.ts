export const PAID_ADS_QA_RULESET_VERSION = "paid_ads_policy_ruleset_v2";

export type PaidAdsQaPlatform = "meta" | "tiktok";
export type PaidAdsQaSeverity = "blocker" | "high" | "medium" | "low";
export type PaidAdsQaFindingStatus = "failed" | "needs_manual_review";
export type PaidAdsQaRunStatus = "passed" | "failed" | "needs_manual_review";

export type PaidAdsQaFinding = {
  id: string;
  ruleId: string;
  ruleType: "policy" | "operational_readiness";
  platform: PaidAdsQaPlatform;
  severity: PaidAdsQaSeverity;
  status: PaidAdsQaFindingStatus;
  title: string;
  message: string;
  artifactType: string;
  artifactRef?: string | null;
  fixGuidance: string[];
  evidence: Record<string, unknown>;
  needsVerification: boolean;
  sourceId: string;
  sourceTitle: string;
  sourceUrl?: string | null;
  policyAnchorQuote?: string | null;
  createdAt: string;
};

export type PaidAdsPlatformProfile = {
  id: string;
  orgId: string;
  clientId: string;
  platform: PaidAdsQaPlatform;
  rulesetVersion: string;
  businessManagerId?: string | null;
  businessManagerName?: string | null;
  pageId?: string | null;
  pageName?: string | null;
  adAccountId?: string | null;
  adAccountName?: string | null;
  paymentMethodType?: string | null;
  paymentMethodStatus?: string | null;
  pixelId?: string | null;
  dataSetId?: string | null;
  dataSetShopifyPartnerInstalled?: boolean | null;
  dataSetDataSharingLevel?: string | null;
  dataSetAssignedToAdAccount?: boolean | null;
  verifiedDomain?: string | null;
  verifiedDomainStatus?: string | null;
  attributionClickWindow?: string | null;
  attributionViewWindow?: string | null;
  viewThroughEnabled?: boolean | null;
  trackingProvider?: string | null;
  trackingUrlParameters?: string | null;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};

export type PaidAdsPlatformProfileUpsertPayload = {
  rulesetVersion: string;
  businessManagerId?: string;
  businessManagerName?: string;
  pageId?: string;
  pageName?: string;
  adAccountId?: string;
  adAccountName?: string;
  paymentMethodType?: string;
  paymentMethodStatus?: string;
  pixelId?: string;
  dataSetId?: string;
  dataSetShopifyPartnerInstalled?: boolean;
  dataSetDataSharingLevel?: string;
  dataSetAssignedToAdAccount?: boolean;
  verifiedDomain?: string;
  verifiedDomainStatus?: string;
  attributionClickWindow?: string;
  attributionViewWindow?: string;
  viewThroughEnabled?: boolean;
  trackingProvider?: string;
  trackingUrlParameters?: string;
  metadata?: Record<string, unknown>;
};

export type PaidAdsDnsRecord = {
  provider: string;
  recordType: string;
  host: string;
  domain: string;
  fqdn: string;
  value: string;
  ttl: number;
  status: string;
};

export type PaidAdsMetaDomainVerificationProvisionPayload = {
  txtValue: string;
  verifiedDomain?: string;
};

export type PaidAdsMetaDomainVerificationProvisionResponse = {
  funnelId: string;
  campaignId: string;
  clientId: string;
  verifiedDomain: string;
  verifiedDomainStatus?: string | null;
  dnsRecord: PaidAdsDnsRecord;
  profile: PaidAdsPlatformProfile;
};

export type PaidAdsQaRun = {
  id: string;
  orgId: string;
  clientId: string;
  campaignId?: string | null;
  platform: PaidAdsQaPlatform;
  subjectType: string;
  subjectId: string;
  rulesetVersion: string;
  status: PaidAdsQaRunStatus;
  blockerCount: number;
  highCount: number;
  mediumCount: number;
  lowCount: number;
  needsManualReviewCount: number;
  checkedRuleIds: string[];
  reportFilePath?: string | null;
  reportMarkdown: string;
  metadata: Record<string, unknown>;
  findings: PaidAdsQaFinding[];
  createdAt: string;
  completedAt?: string | null;
};
