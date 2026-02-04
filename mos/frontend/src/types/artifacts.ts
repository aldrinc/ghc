export interface Artifact<T = unknown> {
  id: string;
  org_id: string;
  client_id: string;
  product_id?: string | null;
  campaign_id?: string | null;
  type: string;
  version: number;
  data: T;
  created_at: string;
}

export interface PrecanonResearch {
  step_summaries?: Record<string, string>;
  step_contents?: Record<string, string>;
  artifact_refs?: ResearchArtifactRef[];
  prompt_shas?: Record<string, string>;
  ads_context?: unknown;
  ads_research_run_id?: string;
  research_highlights?: Record<string, unknown>;
}

export interface ClientCanon {
  clientId: string;
  brand: Record<string, unknown>;
  precanon_research?: PrecanonResearch;
  research_highlights?: Record<string, unknown>;
}

export interface MetricSchema {
  clientId: string;
  events: any[];
}

export interface StrategySheet {
  clientId: string;
  campaignId?: string | null;
  goal?: string;
  hypothesis?: string;
  channelPlan?: Array<{
    channel: string;
    objective?: string;
    budgetSplitPercent?: number;
    notes?: string;
  }>;
  messaging?: Array<{
    title?: string;
    proofPoints?: string[];
  }>;
  risks?: string[];
  mitigations?: string[];
}

export interface ExperimentSpec {
  id: string;
  name: string;
  hypothesis?: string;
  metricIds?: string[];
  variants?: Array<{
    id: string;
    name: string;
    description?: string;
    channels?: string[];
    guardrails?: string[];
  }>;
  sampleSizeEstimate?: number;
  durationDays?: number;
  budgetEstimate?: number;
}

export interface AssetBrief {
  id: string;
  clientId: string;
  campaignId?: string | null;
  experimentId?: string | null;
  variantId?: string | null;
  funnelId?: string | null;
  variantName?: string | null;
  creativeConcept?: string | null;
  requirements?: Array<{
    channel: string;
    format: string;
    angle?: string;
    hook?: string;
    funnelStage?: string;
  }>;
  toneGuidelines?: string[];
  constraints?: string[];
  visualGuidelines?: string[];
}
import type { ResearchArtifactRef } from "./common";
