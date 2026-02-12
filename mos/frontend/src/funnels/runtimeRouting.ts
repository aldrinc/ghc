type DeployRuntimeConfig = {
  publicId?: string;
  rootDomainMode?: boolean;
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

export function getStandalonePublicId(): string | null {
  const publicId = (getDeployRuntimeConfig().publicId || "").trim();
  return publicId || null;
}

export function isStandaloneRootModeForPublicId(publicId: string | null | undefined): boolean {
  const cfg = getDeployRuntimeConfig();
  if (!cfg.rootDomainMode) {
    return false;
  }
  const runtimePublicId = (cfg.publicId || "").trim();
  if (!runtimePublicId) {
    return false;
  }
  if (!publicId) {
    return true;
  }
  return runtimePublicId === publicId;
}

export function buildPublicFunnelPath(
  {
    publicId,
    slug,
    entrySlug,
    rootMode,
  }: {
    publicId: string;
    slug?: string | null;
    entrySlug?: string | null;
    rootMode: boolean;
  },
): string {
  const normalizedPublicId = (publicId || "").trim();
  if (!normalizedPublicId) {
    return "/";
  }

  const normalizedSlug = (slug || "").trim();
  const normalizedEntrySlug = (entrySlug || "").trim();
  if (rootMode) {
    if (!normalizedSlug || (normalizedEntrySlug && normalizedSlug === normalizedEntrySlug)) {
      return "/";
    }
    return `/${encodeURIComponent(normalizedSlug)}`;
  }

  if (!normalizedSlug) {
    return `/f/${encodeURIComponent(normalizedPublicId)}`;
  }
  return `/f/${encodeURIComponent(normalizedPublicId)}/${encodeURIComponent(normalizedSlug)}`;
}
