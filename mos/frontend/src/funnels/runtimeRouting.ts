import { resolveRequiredApiBaseUrl } from "@/lib/apiBaseUrl";
import type { PublicFunnelCommerce } from "@/types/commerce";
import type { PublicFunnelMeta, PublicFunnelPage } from "@/types/funnels";

type StandalonePreloadedFunnel = {
  productSlug?: string;
  funnelSlug?: string;
  meta?: PublicFunnelMeta | null;
  commerce?: PublicFunnelCommerce | null;
  pages?: Record<string, PublicFunnelPage>;
};

type DeployRuntimeConfig = {
  bundleMode?: boolean;
  defaultProductSlug?: string;
  defaultFunnelSlug?: string;
  defaultEntrySlug?: string;
  preloadedFunnel?: StandalonePreloadedFunnel;
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
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

export function getStandaloneDefaultFunnelSlug(): string | null {
  return getStandaloneDefaultRoute()?.funnelSlug ?? null;
}

export function resolvePreferredPublicFunnelSlug(
  meta:
    | Pick<PublicFunnelMeta, "entrySlug" | "pages">
    | null
    | undefined,
): string | null {
  const pageSlugs = new Set(
    Array.isArray(meta?.pages)
      ? meta.pages
          .map((page) => normalizeRouteToken(page?.slug))
          .filter((slug): slug is string => Boolean(slug))
      : [],
  );

  for (const candidate of ["sales-page", "sales"]) {
    if (pageSlugs.has(candidate)) {
      return candidate;
    }
  }

  const entrySlug = normalizeRouteToken(meta?.entrySlug);
  return entrySlug || null;
}

export function getStandalonePreloadedFunnelData(
  options?: {
    productSlug?: string | null;
    funnelSlug?: string | null;
  },
): StandalonePreloadedFunnel | null {
  const config = getDeployRuntimeConfig();
  const candidate = config.preloadedFunnel;
  if (!isRecord(candidate)) {
    return null;
  }

  const productSlug = normalizeRouteToken(String(candidate.productSlug || ""));
  const funnelSlug = normalizeRouteToken(String(candidate.funnelSlug || ""));
  if (!productSlug || !funnelSlug) {
    return null;
  }

  const requestedProductSlug = normalizeRouteToken(options?.productSlug);
  if (requestedProductSlug && requestedProductSlug !== productSlug) {
    return null;
  }
  const requestedFunnelSlug = normalizeRouteToken(options?.funnelSlug);
  if (requestedFunnelSlug && requestedFunnelSlug !== funnelSlug) {
    return null;
  }

  const rawPages = candidate.pages;
  const pages: Record<string, PublicFunnelPage> = {};
  if (isRecord(rawPages)) {
    for (const [rawSlug, payload] of Object.entries(rawPages)) {
      const normalizedSlug = normalizeRouteToken(rawSlug);
      if (!normalizedSlug || !isRecord(payload)) {
        continue;
      }
      pages[normalizedSlug] = payload as unknown as PublicFunnelPage;
    }
  }

  return {
    productSlug,
    funnelSlug,
    meta: isRecord(candidate.meta) ? (candidate.meta as PublicFunnelMeta) : null,
    commerce: isRecord(candidate.commerce) ? (candidate.commerce as PublicFunnelCommerce) : null,
    pages,
  };
}

export function getStandaloneDefaultPageRoute(): { productSlug: string; funnelSlug: string; slug: string } | null {
  const defaultRoute = getStandaloneDefaultRoute();
  const config = getDeployRuntimeConfig();
  const slug = normalizeRouteToken(config.defaultEntrySlug);
  if (!defaultRoute || !slug) {
    return null;
  }
  return {
    ...defaultRoute,
    slug,
  };
}

export function buildStandalonePublicPagePath(
  {
    productSlug,
    slug,
  }: {
    productSlug: string;
    slug: string;
  },
): string {
  const normalizedProductSlug = normalizeRouteToken(productSlug);
  const normalizedSlug = normalizeRouteToken(slug);
  if (!normalizedProductSlug || !normalizedSlug) {
    throw new Error("productSlug and slug are required to build a standalone public page path.");
  }
  return `/${encodeURIComponent(normalizedProductSlug)}/${encodeURIComponent(normalizedSlug)}`;
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
