import type { AdPlatformId } from "./adPlatform";
import type { PaidAdsQaFinding } from "@/api/paidAdsQa";
import type { AssetBrief } from "./artifacts";

/** Summarises QA violations for a single ad card. */
export type CardViolationSummary = {
  total: number;
  blocker: number;
  high: number;
  medium: number;
  low: number;
  maxSeverity: "blocker" | "high" | "medium" | "low" | null;
};

export const EMPTY_VIOLATION_SUMMARY: CardViolationSummary = {
  total: 0,
  blocker: 0,
  high: 0,
  medium: 0,
  low: 0,
  maxSeverity: null,
};

/**
 * Represents a single reviewable ad in the creative review grid.
 * Combines asset, creative spec, QA findings, and brief metadata.
 */
export type AdReviewItem = {
  // Core identity
  assetId: string;
  specId: string | null;

  // Display data
  imageUrl: string | null;
  imageAlt: string;
  assetKind: "image" | "video" | string;
  format: string;
  width: number | null;
  height: number | null;

  // Ad copy (from creative spec or swipe copy pack fallback)
  primaryText: string | null;
  headline: string | null;
  description: string | null;
  cta: string | null;
  destinationUrl: string | null;
  copySource: "creative_spec" | "swipe_copy_pack" | "none";

  // Context
  platform: AdPlatformId;
  briefId: string | null;
  experimentName: string | null;
  variantName: string | null;
  angle: string | null;
  hook: string | null;
  funnelStage: string | null;
  selectedVariation: string | null;
  requirementIndex: number | null;

  // Lineage
  sourceSwipeLabel: string | null;
  sourceSwipeUrl: string | null;
  generationGroup: string | null;
  createdAt: string;

  // Status
  specReady: boolean;
  publishDecision: "excluded" | null;
  violations: CardViolationSummary;
  findings: PaidAdsQaFinding[];

  // Full objects for detail panel
  brief: AssetBrief | null;
};
