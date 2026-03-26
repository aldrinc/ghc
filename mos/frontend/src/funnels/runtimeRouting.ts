import { resolveRequiredApiBaseUrl } from "@/lib/apiBaseUrl";

type DeployRuntimeConfig = {
  bundleMode?: boolean;
  defaultProductSlug?: string;
  defaultFunnelSlug?: string;
};

const SHORT_ID_LENGTH = 8;
const SHORT_ID_PATTERN = /^[0-9a-f]{8}$/;

declare global {
  interface Window {
    __MOS_DEPLOY_RUNTIME__?: DeployRuntimeConfig;
  }
}

function getDeployRuntimeConfig(): DeployRuntimeConfig {
  if (typeof window === "undefined") {
    return {};
  }
  const candidate = window.__MOS_DEPLOY_RUNTIME__;
  if (!candidate || typeof candidate !== "object") {
    return {};
  }
  return candidate;
}

export function normalizeRouteToken(value: string | null | undefined): string {
  const normalized = (value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^-+|-+$/g, "");
  return normalized;
}

export function shortUuidRouteToken(value: string | null | undefined): string {
  const normalized = (value || "").trim().toLowerCase();
  if (!normalized) return "";
  const prefix = normalized.split("-", 1)[0].slice(0, SHORT_ID_LENGTH);
  if (!SHORT_ID_PATTERN.test(prefix)) {
    return "";
  }
  return prefix;
}

export function isStandaloneBundleMode(): boolean {
  return Boolean(getDeployRuntimeConfig().bundleMode);
}

export function resolvePublicApiBaseUrl(): string {
  if (isStandaloneBundleMode()) {
    return "/api";
  }
  return resolveRequiredApiBaseUrl();
}

export function getStandaloneDefaultRoute(): { productSlug: string; funnelSlug: string } | null {
  const config = getDeployRuntimeConfig();
  const productSlug = normalizeRouteToken(config.defaultProductSlug);
  const funnelSlug = normalizeRouteToken(config.defaultFunnelSlug);
  if (!productSlug || !funnelSlug) {
    return null;
  }
  return { productSlug, funnelSlug };
}

export function buildPublicFunnelPath(
  {
    productSlug,
    funnelSlug,
    slug,
    bundleMode,
    sitePath,
  }: {
    productSlug: string;
    funnelSlug: string;
    slug?: string | null;
    bundleMode: boolean;
    sitePath?: string | null;
  },
): string {
  const normalizedProductSlug = normalizeRouteToken(productSlug);
  const normalizedFunnelSlug = normalizeRouteToken(funnelSlug);
  if (!normalizedProductSlug || !normalizedFunnelSlug) {
    throw new Error("productSlug and funnelSlug are required to build a public funnel path.");
  }

  const normalizedSlug = normalizeRouteToken(slug);
  const normalizedSitePath = sitePath ? sitePath.replace(/^\//, "") : "";
  const nestedSlugPath = typeof slug === "string" && slug.includes("/") ? slug.replace(/^\//, "") : "";
  
  if (bundleMode) {
    if (!normalizedSlug && !normalizedSitePath && !nestedSlugPath) {
      return `/${encodeURIComponent(normalizedProductSlug)}/${encodeURIComponent(normalizedFunnelSlug)}`;
    }
    if (normalizedSitePath) {
      return `/${encodeURIComponent(normalizedProductSlug)}/${encodeURIComponent(normalizedFunnelSlug)}/${normalizedSitePath}`;
    }
    if (nestedSlugPath) {
      return `/${encodeURIComponent(normalizedProductSlug)}/${encodeURIComponent(normalizedFunnelSlug)}/${nestedSlugPath}`;
    }
    return `/${encodeURIComponent(normalizedProductSlug)}/${encodeURIComponent(normalizedFunnelSlug)}/${encodeURIComponent(normalizedSlug)}`;
  }

  if (!normalizedSlug && !normalizedSitePath && !nestedSlugPath) {
    return `/f/${encodeURIComponent(normalizedProductSlug)}/${encodeURIComponent(normalizedFunnelSlug)}`;
  }
  if (normalizedSitePath) {
    return `/f/${encodeURIComponent(normalizedProductSlug)}/${encodeURIComponent(normalizedFunnelSlug)}/${normalizedSitePath}`;
  }
  if (nestedSlugPath) {
    return `/f/${encodeURIComponent(normalizedProductSlug)}/${encodeURIComponent(normalizedFunnelSlug)}/${nestedSlugPath}`;
  }
  return `/f/${encodeURIComponent(normalizedProductSlug)}/${encodeURIComponent(normalizedFunnelSlug)}/${encodeURIComponent(normalizedSlug)}`;
}

/**
 * Parse a nested site path into its components.
 * Supports paths like: us/store, us/collections/summer, us/products/face-oil
 */
export function parseSitePath(sitePath: string): {
  countryCode: string | null;
  pageType: string;
  handle: string | null;
  nestedPath: string[];
} {
  const parts = sitePath.replace(/^\//, "").split("/").filter(Boolean);
  
  if (parts.length === 0) {
    return { countryCode: null, pageType: "home", handle: null, nestedPath: [] };
  }
  
  // First part could be a country code (2 chars) or a page type
  const firstPart = parts[0];
  const isCountryCode = /^[a-z]{2}$/i.test(firstPart);
  
  const countryCode = isCountryCode ? firstPart.toLowerCase() : null;
  const pathParts = isCountryCode ? parts.slice(1) : parts;
  
  if (pathParts.length === 0) {
    return { countryCode, pageType: "home", handle: null, nestedPath: [] };
  }
  
  const pageType = pathParts[0];
  const handle = pathParts[1] || null;
  const nestedPath = pathParts.slice(2);
  
  return { countryCode, pageType, handle, nestedPath };
}

/**
 * Build a site path from components.
 */
export function buildSitePath(options: {
  countryCode?: string | null;
  pageType?: string;
  handle?: string | null;
  nestedPath?: string[];
}): string {
  const parts: string[] = [];
  
  if (options.countryCode) {
    parts.push(options.countryCode.toLowerCase());
  }
  
  if (options.pageType && options.pageType !== "home") {
    parts.push(options.pageType);
  }
  
  if (options.handle) {
    parts.push(options.handle);
  }
  
  if (options.nestedPath?.length) {
    parts.push(...options.nestedPath);
  }
  
  return parts.join("/");
}
