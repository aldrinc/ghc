import { buildRuntimePageMap } from "@/funnels/runtimePageMaps";
import { buildPublicFunnelPath, shortUuidRouteToken } from "@/funnels/runtimeRouting";

type FunnelLike = {
  client_id?: string | null;
  id?: string | null;
};

type FunnelPageLike = {
  id?: string | null;
  slug?: string | null;
  name?: string | null;
  template_id?: string | null;
  templateId?: string | null;
};

function cleanOptionalText(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed || null;
}

export function buildFunnelDeployWorkloadName(funnel: FunnelLike | null | undefined): string | undefined {
  const clientToken = shortUuidRouteToken(funnel?.client_id || "");
  const funnelToken = shortUuidRouteToken(funnel?.id || "");
  if (!clientToken || !funnelToken) return undefined;
  return `brand-funnels-${clientToken}-${funnelToken}`;
}

export function buildCanonicalPublicPageSlug(page: FunnelPageLike | null | undefined): string | null {
  const pageId = cleanOptionalText(page?.id) || "__page__";
  const pageMap = buildRuntimePageMap([
    {
      id: pageId,
      slug: page?.slug,
      name: page?.name,
      template_id: page?.template_id,
      templateId: page?.templateId,
    },
  ]);
  return pageMap[pageId] ?? cleanOptionalText(page?.slug);
}

export function buildStandalonePublicFunnelPath({
  productSlug,
  funnelSlug,
}: {
  productSlug: string | null | undefined;
  funnelSlug: string | null | undefined;
}): string | null {
  const normalizedProductSlug = cleanOptionalText(productSlug);
  const normalizedFunnelSlug = cleanOptionalText(funnelSlug);
  if (!normalizedProductSlug || !normalizedFunnelSlug) return null;
  return buildPublicFunnelPath({
    productSlug: normalizedProductSlug,
    funnelSlug: normalizedFunnelSlug,
    bundleMode: true,
  });
}

export function buildStandalonePublicPagePath({
  productSlug,
  funnelSlug,
  page,
}: {
  productSlug: string | null | undefined;
  funnelSlug: string | null | undefined;
  page: FunnelPageLike | null | undefined;
}): string | null {
  const normalizedProductSlug = cleanOptionalText(productSlug);
  const normalizedFunnelSlug = cleanOptionalText(funnelSlug);
  const pageSlug = buildCanonicalPublicPageSlug(page);
  if (!normalizedProductSlug || !normalizedFunnelSlug || !pageSlug) return null;
  return buildPublicFunnelPath({
    productSlug: normalizedProductSlug,
    funnelSlug: normalizedFunnelSlug,
    slug: pageSlug,
    bundleMode: true,
  });
}

export function resolvePrimaryDeployedPublicBaseUrl({
  configuredDeployDomains,
  accessUrl,
}: {
  configuredDeployDomains: string[];
  accessUrl?: string | null;
}): string | null {
  const hostname = configuredDeployDomains.map((value) => (value || "").trim()).find(Boolean);
  if (hostname) {
    return `https://${hostname}`;
  }
  const cleanedAccessUrl = cleanOptionalText(accessUrl);
  if (!cleanedAccessUrl) return null;
  return cleanedAccessUrl.replace(/\/+$/, "");
}

export function joinPublicUrl(baseUrl: string | null | undefined, path: string | null | undefined): string | null {
  const normalizedBaseUrl = cleanOptionalText(baseUrl);
  const normalizedPath = cleanOptionalText(path);
  if (!normalizedBaseUrl || !normalizedPath) return null;
  return `${normalizedBaseUrl.replace(/\/+$/, "")}${normalizedPath}`;
}
