type DeployRuntimeConfig = {
  funnelSlug?: string;
  bundleMode?: boolean;
};

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

export function isStandaloneBundleMode(): boolean {
  return Boolean(getDeployRuntimeConfig().bundleMode);
}

export function getStandaloneFunnelSlug(): string | null {
  const funnelSlug = (getDeployRuntimeConfig().funnelSlug || "").trim();
  return funnelSlug || null;
}

export function buildPublicFunnelPath(
  {
    funnelSlug,
    slug,
    bundleMode,
  }: {
    funnelSlug: string;
    slug?: string | null;
    bundleMode: boolean;
  },
): string {
  const normalizedFunnelSlug = (funnelSlug || "").trim();
  if (!normalizedFunnelSlug) {
    return "/";
  }

  const normalizedSlug = (slug || "").trim();
  if (bundleMode) {
    if (!normalizedSlug) {
      return `/${encodeURIComponent(normalizedFunnelSlug)}`;
    }
    return `/${encodeURIComponent(normalizedFunnelSlug)}/${encodeURIComponent(normalizedSlug)}`;
  }

  if (!normalizedSlug) {
    return `/f/${encodeURIComponent(normalizedFunnelSlug)}`;
  }
  return `/f/${encodeURIComponent(normalizedFunnelSlug)}/${encodeURIComponent(normalizedSlug)}`;
}
