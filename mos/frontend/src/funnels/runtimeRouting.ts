type DeployRuntimeConfig = {
  bundleMode?: boolean;
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

export function buildPublicFunnelPath(
  {
    productSlug,
    funnelSlug,
    slug,
    bundleMode,
  }: {
    productSlug: string;
    funnelSlug: string;
    slug?: string | null;
    bundleMode: boolean;
  },
): string {
  const normalizedProductSlug = normalizeRouteToken(productSlug);
  const normalizedFunnelSlug = normalizeRouteToken(funnelSlug);
  if (!normalizedProductSlug || !normalizedFunnelSlug) {
    throw new Error("productSlug and funnelSlug are required to build a public funnel path.");
  }

  const normalizedSlug = normalizeRouteToken(slug);
  if (bundleMode) {
    if (!normalizedSlug) {
      return `/${encodeURIComponent(normalizedProductSlug)}/${encodeURIComponent(normalizedFunnelSlug)}`;
    }
    return `/${encodeURIComponent(normalizedProductSlug)}/${encodeURIComponent(normalizedFunnelSlug)}/${encodeURIComponent(normalizedSlug)}`;
  }

  if (!normalizedSlug) {
    return `/f/${encodeURIComponent(normalizedProductSlug)}/${encodeURIComponent(normalizedFunnelSlug)}`;
  }
  return `/f/${encodeURIComponent(normalizedProductSlug)}/${encodeURIComponent(normalizedFunnelSlug)}/${encodeURIComponent(normalizedSlug)}`;
}
