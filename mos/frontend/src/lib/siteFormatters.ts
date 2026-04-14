/**
 * Shared formatting helpers used across site management pages.
 *
 * Previously duplicated between SitesPage, SiteDetailPage, and others.
 */

/** Capitalise each underscore-separated token: "product_detail" -> "Product Detail" */
export function formatSiteType(siteType: string | null): string {
  if (!siteType) return "Unknown";
  return siteType
    .split("_")
    .map((token) => (token ? token[0].toUpperCase() + token.slice(1) : token))
    .join(" ");
}

/** Capitalise the first letter of a commerce provider name. */
export function formatCommerceProvider(provider: string | null): string {
  if (!provider) return "None";
  return provider.charAt(0).toUpperCase() + provider.slice(1);
}

/** Capitalise each hyphen-separated token: "medusa-b2c-starter" -> "Medusa B2c Starter" */
export function formatSiteFamily(family: string | null): string {
  if (!family) return "Unknown";
  return family
    .split("-")
    .map((token) => (token ? token[0].toUpperCase() + token.slice(1) : token))
    .join(" ");
}

/** Capitalise each underscore-separated token in a page-type string. */
export function formatPageType(pageType: string | null): string {
  if (!pageType) return "Unknown";
  return pageType
    .split("_")
    .map((token) => (token ? token[0].toUpperCase() + token.slice(1) : token))
    .join(" ");
}

/** Map import status to a Badge tone. */
export function formatImportStatus(status: string): "success" | "warning" | "danger" | "neutral" {
  if (status === "completed") return "success";
  if (["queued", "capturing", "generating", "adapting", "running"].includes(status)) return "warning";
  if (status === "failed") return "danger";
  return "neutral";
}

/** Map funnel status to a Badge tone. */
export function formatFunnelStatus(status: string): "success" | "warning" | "danger" | "neutral" {
  if (status === "active") return "success";
  if (status === "draft") return "warning";
  if (status === "archived") return "danger";
  return "neutral";
}

/** Format an ISO date string as a human-readable local date + time. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "Unknown";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

/** Extract a user-facing error message from an unknown thrown value. */
export function getErrorMessage(error: unknown, fallback: string): string {
  const candidate = error as { message?: unknown } | null;
  if (candidate && typeof candidate.message === "string") {
    return candidate.message;
  }
  return fallback;
}
