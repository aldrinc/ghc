/** How the campaign delivers traffic to the offer. */
export type DeliveryMode = "internal_funnel" | "external_urls";

/** Standard destination page types. */
export type DestinationType = "pre_sales" | "sales" | "checkout" | "thank_you";

export type DeliveryValidationStatus =
  | "not_applicable"
  | "not_validated"
  | "valid"
  | "invalid";

/** Campaign-level delivery configuration. */
export interface CampaignDeliveryConfig {
  id?: string;
  campaignId?: string;
  clientId?: string;
  deliveryMode: DeliveryMode;
  preSalesUrl?: string;
  salesUrl?: string;
  checkoutUrl?: string;
  thankYouUrl?: string;
  validationStatus: DeliveryValidationStatus;
  validationError?: string;
  validatedAt?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface CampaignDeliveryValidationResult {
  field: "preSalesUrl" | "salesUrl" | "checkoutUrl" | "thankYouUrl";
  url: string;
  finalUrl?: string | null;
  statusCode?: number | null;
  passed: boolean;
  checks: string[];
  issues: string[];
}

export interface CampaignDeliveryValidationResponse {
  checkedAt: string;
  validationStatus: DeliveryValidationStatus;
  validationError?: string | null;
  results: CampaignDeliveryValidationResult[];
  delivery: CampaignDeliveryConfig;
}

export interface CampaignLaunchContextReadiness {
  ready: boolean;
  checkedAt: string;
  reason?: string | null;
  sourceStrategyV2WorkflowRunId?: string | null;
  sourceStrategyV2TemporalWorkflowId?: string | null;
  launchContextArtifactId?: string | null;
  refreshed: boolean;
  staleArtifactId?: string | null;
}

/** Default delivery config for campaigns that haven't been configured. */
export const DEFAULT_DELIVERY_CONFIG: CampaignDeliveryConfig = {
  deliveryMode: "internal_funnel",
  validationStatus: "not_applicable",
};
