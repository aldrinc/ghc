import { Render } from "@measured/puck";
import type { Data } from "@measured/puck";
import { useEffect, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Edit, Loader2 } from "lucide-react";
import { useSite, useSiteMedusaConfig, useSitePage } from "@/api/sites";
import { DesignSystemProvider } from "@/components/design-system/DesignSystemProvider";
import { B2CRuntimeProvider } from "@/components/commerce/b2c/B2CRuntimeProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { createFunnelPuckConfig, FunnelRuntimeProvider } from "@/funnels/puckConfig";
import { normalizePuckData } from "@/funnels/puckData";
import {
  buildRuntimePageMap,
  buildRuntimePageStageMap,
  buildRuntimePageTypeMap,
} from "@/funnels/runtimePageMaps";
import { parseSitePath, shortUuidRouteToken } from "@/funnels/runtimeRouting";
import { setMedusaRuntimeConfig } from "@/lib/medusa";
import { buildSitePreviewPath, resolveSitePreviewPage } from "@/pages/workspaces/sites/sitePreviewRouting";

export function SitePagePreviewPage() {
  const navigate = useNavigate();
  const params = useParams();
  const siteId = params.siteId || null;
  const previewPath = params["*"] || "";

  const { data: site, isLoading: siteLoading, error: siteError } = useSite(siteId);
  const resolvedPage = useMemo(
    () => (site ? resolveSitePreviewPage(site.pages, previewPath, site.entryPageId) : null),
    [previewPath, site]
  );
  const { data: pageDetail, isLoading: pageLoading, error: pageError } = useSitePage(siteId, resolvedPage?.id || null);
  const { data: medusaConfig } = useSiteMedusaConfig(siteId);

  const pageOptions = useMemo(
    () => site?.pages?.map((page) => ({ label: page.name, value: page.id })) || [],
    [site?.pages]
  );
  const pageOptionsKey = useMemo(
    () => pageOptions.map((option) => `${option.value}:${option.label}`).join("|"),
    [pageOptions]
  );
  const config = useMemo(() => createFunnelPuckConfig(pageOptions), [pageOptionsKey]);
  const runtimePages = useMemo(() => site?.pages ?? [], [site?.pages]);
  const runtimePageMap = useMemo(() => buildRuntimePageMap(runtimePages), [runtimePages]);
  const runtimePageStageMap = useMemo(() => buildRuntimePageStageMap(runtimePages), [runtimePages]);
  const runtimePageTypeMap = useMemo(() => buildRuntimePageTypeMap(runtimePages), [runtimePages]);
  const parsedSitePath = useMemo(() => parseSitePath(previewPath), [previewPath]);
  const normalizedPuckData = useMemo(() => {
    if (!pageDetail) return null;
    const initial =
      (pageDetail.latestDraft?.puckData as Data | undefined) ||
      (pageDetail.latestApproved?.puckData as Data | undefined);
    if (!initial) return null;
    return normalizePuckData(initial, { designSystemTokens: pageDetail.designSystemTokens ?? null });
  }, [pageDetail]);
  const previewPageHref = useMemo(
    () => (siteId && resolvedPage ? buildSitePreviewPath(siteId, resolvedPage.slug) : null),
    [resolvedPage, siteId]
  );
  const previewBasePath = useMemo(() => (siteId ? buildSitePreviewPath(siteId) : null), [siteId]);
  const previewProductSlug = useMemo(
    () => shortUuidRouteToken(site?.productId || site?.id || ""),
    [site?.id, site?.productId]
  );
  const previewFunnelSlug = useMemo(
    () => site?.routeSlug || shortUuidRouteToken(site?.id || ""),
    [site?.id, site?.routeSlug]
  );
  const isB2CSitePreview = site?.siteFamily === "medusa-b2c-starter" && Object.keys(runtimePageTypeMap).length > 0;

  useEffect(() => {
    const runtimeConfig = medusaConfig?.medusaConfig;
    if (!runtimeConfig?.available || !runtimeConfig.baseUrl || !runtimeConfig.publishableKey) {
      setMedusaRuntimeConfig(null);
      return () => setMedusaRuntimeConfig(null);
    }

    setMedusaRuntimeConfig({
      backendUrl: runtimeConfig.baseUrl,
      publishableKey: runtimeConfig.publishableKey,
      defaultCountryCode: "us",
    });

    return () => setMedusaRuntimeConfig(null);
  }, [medusaConfig?.medusaConfig]);

  if (siteLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center gap-3 bg-surface text-sm text-content-muted">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading site preview...
      </div>
    );
  }

  if (siteError || !site) {
    return (
      <div className="min-h-screen bg-surface p-6">
        <div className="mx-auto max-w-3xl rounded-2xl border border-danger/20 bg-danger/5 p-6 text-sm text-danger">
          {siteError instanceof Error ? siteError.message : "Failed to load site preview."}
        </div>
      </div>
    );
  }

  if (!resolvedPage) {
    return (
      <div className="min-h-screen bg-surface p-6">
        <div className="mx-auto max-w-4xl space-y-4">
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => navigate(`/workspaces/sites/${site.id}`)}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Site
            </Button>
          </div>
          <div className="rounded-2xl border border-danger/20 bg-danger/5 p-6 text-sm text-danger">
            No site page matches the preview path `{previewPath || "/"}`.
          </div>
        </div>
      </div>
    );
  }

  if (pageLoading || !pageDetail || !normalizedPuckData) {
    return (
      <div className="flex min-h-screen items-center justify-center gap-3 bg-surface text-sm text-content-muted">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading page preview...
      </div>
    );
  }

  if (pageError) {
    return (
      <div className="min-h-screen bg-surface p-6">
        <div className="mx-auto max-w-3xl rounded-2xl border border-danger/20 bg-danger/5 p-6 text-sm text-danger">
          {pageError instanceof Error ? pageError.message : "Failed to load page preview."}
        </div>
      </div>
    );
  }

  const previewRuntimeValue = {
    productSlug: previewProductSlug || "preview-product",
    funnelSlug: previewFunnelSlug || "preview-site",
    pageMap: runtimePageMap,
    pageStageMap: runtimePageStageMap,
    pageTypeMap: runtimePageTypeMap,
    pageId: pageDetail.page.id,
    nextPageId: null,
    resolvePagePath: (slug: string) => buildSitePreviewPath(site.id, slug),
    resolveSitePath: (sitePath: string) => buildSitePreviewPath(site.id, sitePath),
  };

  return (
    <div className="min-h-screen bg-surface">
      <div className="sticky top-0 z-40 border-b border-border bg-surface/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="truncate text-sm font-semibold text-content">{site.name}</span>
              <Badge tone="neutral">{resolvedPage.name}</Badge>
              {previewPath ? (
                <span className="truncate text-xs text-content-muted">
                  {previewPath}
                </span>
              ) : null}
            </div>
            <div className="mt-1 text-xs text-content-muted">
              {isB2CSitePreview && previewBasePath
                ? `B2C preview route: ${buildSitePreviewPath(site.id, parsedSitePath.countryCode || resolvedPage.slug)}`
                : `Preview route: ${previewPageHref || buildSitePreviewPath(site.id)}`}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" onClick={() => navigate(`/workspaces/sites/${site.id}`)}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Site
            </Button>
            <Button variant="outline" onClick={() => navigate(`/workspaces/sites/${site.id}/pages/${resolvedPage.id}`)}>
              <Edit className="mr-2 h-4 w-4" />
              Edit Page
            </Button>
          </div>
        </div>
      </div>

      <FunnelRuntimeProvider value={previewRuntimeValue}>
        {isB2CSitePreview ? (
          <B2CRuntimeProvider
            siteFamily="medusa-b2c-starter"
            siteName={site.name}
            initialCountryCode={parsedSitePath.countryCode || undefined}
          >
            <DesignSystemProvider tokens={pageDetail.designSystemTokens}>
              <Render config={config} data={normalizedPuckData as unknown as Data} />
            </DesignSystemProvider>
          </B2CRuntimeProvider>
        ) : (
          <DesignSystemProvider tokens={pageDetail.designSystemTokens}>
            <Render config={config} data={normalizedPuckData as unknown as Data} />
          </DesignSystemProvider>
        )}
      </FunnelRuntimeProvider>
    </div>
  );
}
