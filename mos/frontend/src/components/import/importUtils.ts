/**
 * Shared utility functions for import-related components.
 */

import type { SiteImportDetail } from "@/types/storefrontTemplates";

/** Capitalise each underscore-separated token: "model_slot" → "Model Slot" */
export function formatSlot(slot: string): string {
  return slot
    .split("_")
    .map((token) => (token ? token[0].toUpperCase() + token.slice(1) : token))
    .join(" ");
}

/** Build a human-readable label from a model id or slot number. */
export function formatImportModelLabel(modelId?: string, modelSlot?: number): string | undefined {
  if (modelId) return modelId;
  if (modelSlot === 1) return "Slot 1 · Gemini";
  if (modelSlot === 2) return "Slot 2 · Claude Opus";
  return undefined;
}

/** Resolve family → default page-type mapping for the convert form. */
export function resolveFamilyDefaults(family?: string | null): { family: string; pageType: string } {
  if (family === "listicle-presell" || family === "pre-sales-listicle") {
    return { family: "listicle-presell", pageType: "pre_sell" };
  }
  return { family: "sales-pdp", pageType: "product_detail" };
}

/** True when the import is still in an active processing stage. */
export function isImportActiveStatus(status?: string | null): boolean {
  return Boolean(status && ["queued", "capturing", "generating", "adapting", "running"].includes(status));
}

/** True when the import detail is flagged as review-only (no site runtime created). */
export function isReviewOnlyImport(detail?: SiteImportDetail | null): boolean {
  return detail?.upstreamMetadata?.["reviewOnly"] === true;
}

/** Safely read a string value from a plain record using key fallbacks. */
export function readProvenanceString(record: Record<string, unknown> | undefined, ...keys: string[]): string | undefined {
  if (!record) return undefined;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return undefined;
}

/** Extract a user-facing error message from an unknown value. */
export function readQueryError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

/** Map a binding-preview requirement status to a Badge tone. */
export function requirementTone(status: string): "success" | "warning" | "danger" | "neutral" {
  if (status === "ready") return "success";
  if (status === "unsupported") return "danger";
  if (status === "missing") return "warning";
  return "neutral";
}
