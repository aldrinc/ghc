import { Puck } from "@measured/puck";
import type { Data } from "@measured/puck";
import { useFunnel, useFunnelPage, useSaveFunnelDraft, useUpdateFunnelPage } from "@/api/funnels";
import { useProduct } from "@/api/products";
import { CommerceRuntimeProvider } from "@/components/commerce/CommerceBlocks";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { DialogContent, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { Select } from "@/components/ui/select";
import { useDesignSystems } from "@/api/designSystems";
import { createFunnelAiPlugin } from "@/funnels/puckAiPlugin";
import { createDesignSystemPlugin } from "@/funnels/puckDesignSystemPlugin";
import { createPuckFieldTypesPlugin } from "@/funnels/puckFieldTypesPlugin";
import { createFunnelPuckConfig, defaultFunnelPuckData, FunnelRuntimeProvider } from "@/funnels/puckConfig";
import { normalizePuckData } from "@/funnels/puckData";
import { buildRuntimePageMap, buildRuntimePageStageMap, buildRuntimePageTypeMap } from "@/funnels/runtimePageMaps";
import { buildPublicFunnelPath, shortUuidRouteToken } from "@/funnels/runtimeRouting";
import { resolveRequiredApiBaseUrl } from "@/lib/apiBaseUrl";
import { resolveShopHostedUrl, resolveWindowShopHostedOrigin } from "@/lib/shopHostedFunnels";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import type { SiteCommerceData } from "@/types/commerce";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

async function parsePublicError(resp: Response): Promise<string> {
  let raw: unknown;
  try {
    raw = await resp.clone().json();
  } catch {
    raw = await resp.text();
  }
  const detail = (raw as { detail?: unknown })?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  const message = (raw as { message?: unknown })?.message;
  if (typeof message === "string" && message.trim()) return message;
  if (typeof raw === "string" && raw.trim()) return raw;
  return resp.statusText || "Request failed";
}

export function FunnelPageEditorPage() {
  const navigate = useNavigate();
  const { funnelId, pageId } = useParams();
  const { workspace } = useWorkspace();
  const { data: funnel } = useFunnel(funnelId);
  const { data: funnelProduct } = useProduct(funnel?.product_id || undefined);
  const { data: pageDetail, isLoading } = useFunnelPage(funnelId, pageId);
  const saveDraft = useSaveFunnelDraft();
  const updatePage = useUpdateFunnelPage();

  const [data, setData] = useState<Data>(() => defaultFunnelPuckData() as unknown as Data);
  const [puckKey, setPuckKey] = useState(() => pageId || "puck");
  const [metaName, setMetaName] = useState("");
  const [metaSlug, setMetaSlug] = useState("");
  const [metaDesignSystemId, setMetaDesignSystemId] = useState<string | null>(null);
  const [metaNextPageId, setMetaNextPageId] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftSlug, setDraftSlug] = useState("");
  const [draftDesignSystemId, setDraftDesignSystemId] = useState("");
  const [draftNextPageId, setDraftNextPageId] = useState("");
  const [siteCommerce, setSiteCommerce] = useState<SiteCommerceData | null>(null);
  const [siteCommerceLoading, setSiteCommerceLoading] = useState(false);
  const [siteCommerceError, setSiteCommerceError] = useState<string | null>(null);
  const initializedPageIdRef = useRef<string | null>(null);
  const backHref = funnelId ? `/research/funnels/${funnelId}` : "/research/funnels";

  useEffect(() => {
    if (!pageId) return;
    if (initializedPageIdRef.current === pageId) return;
    setData(defaultFunnelPuckData() as unknown as Data);
    setPuckKey(pageId);
  }, [pageId]);

  useEffect(() => {
    if (!pageDetail) return;
    if (!pageId) return;
    if (initializedPageIdRef.current === pageId) return;
    initializedPageIdRef.current = pageId;
    const initial =
      (pageDetail.latestDraft?.puck_data as Data | undefined) ||
      (pageDetail.latestApproved?.puck_data as Data | undefined) ||
      (defaultFunnelPuckData() as unknown as Data);
    setData(normalizePuckData(initial, { designSystemTokens: pageDetail.designSystemTokens ?? null }));
    setPuckKey(`${pageId}:${pageDetail.latestDraft?.id || pageDetail.latestApproved?.id || "initial"}`);
    setMetaName(pageDetail.page.name);
    setMetaSlug(pageDetail.page.slug);
    setMetaDesignSystemId(pageDetail.page.design_system_id || null);
    setMetaNextPageId(pageDetail.page.next_page_id || null);
  }, [pageDetail, pageId]);

  const pageOptions = useMemo(() => {
    return funnel?.pages?.map((p) => ({ label: `${p.name} (${p.slug})`, value: p.id })) || [];
  }, [funnel?.pages]);
  const nextPageOptions = useMemo(
    () => [
      { label: "No next page", value: "" },
      ...(funnel?.pages || [])
        .filter((p) => p.id !== pageId)
        .map((p) => ({ label: `${p.name} (${p.slug})`, value: p.id })),
    ],
    [funnel?.pages, pageId]
  );

  const pageOptionsKey = useMemo(
    () => pageOptions.map((o) => `${o.value}:${o.label}`).join("|"),
    [pageOptions]
  );

  const config = useMemo(() => createFunnelPuckConfig(pageOptions), [pageOptionsKey]);
  const runtimePages = useMemo(
    () => (funnel?.pages?.length ? funnel.pages : pageDetail?.page ? [pageDetail.page] : []),
    [funnel?.pages, pageDetail?.page]
  );
  const runtimePageMap = useMemo(() => buildRuntimePageMap(runtimePages), [runtimePages]);
  const runtimePageStageMap = useMemo(() => buildRuntimePageStageMap(runtimePages), [runtimePages]);
  const runtimePageTypeMap = useMemo(() => buildRuntimePageTypeMap(runtimePages), [runtimePages]);
  const isSiteEditor = Object.keys(runtimePageTypeMap).length > 0;

  const currentPageLabel = useMemo(() => {
    const page = funnel?.pages?.find((p) => p.id === pageId);
    return page ? `${page.name} (${page.slug})` : "Page";
  }, [funnel?.pages, pageId]);
  const runtimeProductSlug = shortUuidRouteToken(funnelProduct?.id || funnel?.product_id || "");
  const runtimeFunnelSlug = shortUuidRouteToken(funnel?.id || "");
  const publicOrigin = resolveWindowShopHostedOrigin();
  const publicPageHref = useMemo(() => {
    const slug = (metaSlug || pageDetail?.page.slug || "").trim();
    if (!runtimeProductSlug || !runtimeFunnelSlug || !slug) return null;
    const path = buildPublicFunnelPath({
      productSlug: runtimeProductSlug,
      funnelSlug: runtimeFunnelSlug,
      slug,
      bundleMode: false,
    });
    return resolveShopHostedUrl(path, publicOrigin);
  }, [metaSlug, pageDetail?.page.slug, publicOrigin, runtimeFunnelSlug, runtimeProductSlug]);

  const apiBaseUrl = resolveRequiredApiBaseUrl();
  const clerkTokenTemplate = import.meta.env.VITE_CLERK_JWT_TEMPLATE || "backend";
  const designSystemTokens = pageDetail?.designSystemTokens ?? null;
  const aiPlugin = useMemo(
    () =>
      createFunnelAiPlugin({
        funnelId,
        pageId,
        templateId: pageDetail?.page?.template_id || undefined,
        ideaWorkspaceId: workspace?.id,
        apiBaseUrl,
        clerkTokenTemplate,
      }),
    [funnelId, pageId, pageDetail?.page?.template_id, workspace?.id, apiBaseUrl, clerkTokenTemplate]
  );
  const designSystemPlugin = useMemo(
    () => createDesignSystemPlugin({ tokens: designSystemTokens }),
    [designSystemTokens]
  );
  const fieldTypesPlugin = useMemo(() => createPuckFieldTypesPlugin(), []);
  const plugins = useMemo(
    () => [designSystemPlugin, fieldTypesPlugin, aiPlugin],
    [designSystemPlugin, fieldTypesPlugin, aiPlugin]
  );
  const editorViewports = useMemo(
    () => [
      { width: 375, height: "auto", icon: "Smartphone", label: "Small" },
      { width: 768, height: "auto", icon: "Tablet", label: "Medium" },
      { width: 1280, height: "auto", icon: "Monitor", label: "Large" },
      { width: 1920, height: 1080, icon: "Monitor", label: "Desktop (1920×1080)" },
    ],
    []
  );
  const editorUi = useMemo(
    () => ({
      viewports: {
        current: { width: 1920, height: 1080 as const },
        controlsVisible: true,
        options: editorViewports,
      },
    }),
    [editorViewports]
  );

  useEffect(() => {
    if (!settingsOpen) return;
    setDraftName(metaName);
    setDraftSlug(metaSlug);
    setDraftDesignSystemId(metaDesignSystemId || "");
    setDraftNextPageId(metaNextPageId || "");
  }, [settingsOpen, metaDesignSystemId, metaName, metaNextPageId, metaSlug]);

  const { data: designSystems = [] } = useDesignSystems(funnel?.client_id || workspace?.id);
  const designSystemOptions = useMemo(() => {
    return [
      { label: "Workspace default", value: "" },
      ...designSystems.map((ds) => ({ label: ds.name, value: ds.id })),
    ];
  }, [designSystems]);

  useEffect(() => {
    if (!isSiteEditor || !runtimeProductSlug || !runtimeFunnelSlug) {
      setSiteCommerce(null);
      setSiteCommerceLoading(false);
      setSiteCommerceError(null);
      return;
    }

    const controller = new AbortController();
    const url = `${apiBaseUrl}/public/funnels/${encodeURIComponent(runtimeProductSlug)}/${encodeURIComponent(runtimeFunnelSlug)}/site/commerce`;

    setSiteCommerceLoading(true);
    setSiteCommerceError(null);

    fetch(url, { signal: controller.signal })
      .then(async (resp) => {
        if (!resp.ok) {
          throw new Error(await parsePublicError(resp));
        }
        return (await resp.json()) as SiteCommerceData;
      })
      .then((nextSiteCommerce) => {
        if (!controller.signal.aborted) {
          setSiteCommerce(nextSiteCommerce);
        }
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setSiteCommerce(null);
        setSiteCommerceError(err instanceof Error ? err.message : "Unable to load site commerce preview.");
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setSiteCommerceLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, [apiBaseUrl, isSiteEditor, runtimeFunnelSlug, runtimeProductSlug]);

  return (
    <div className="space-y-4">
      <PageHeader
        compact
        title={
          <span className="flex flex-wrap items-center gap-2">
            <span>{currentPageLabel}</span>
            {pageDetail?.latestDraft ? <Badge tone="neutral">Draft saved</Badge> : null}
          </span>
        }
        description={funnel ? `Funnel: ${funnel.name}` : "Edit funnel page"}
        actions={
          <Menu>
            <MenuTrigger className={buttonClasses({ variant: "secondary", size: "sm" })}>Actions</MenuTrigger>
            <MenuContent className="w-64">
              <MenuItem onClick={() => navigate(backHref)}>Back</MenuItem>
              {funnel?.pages?.length ? (
                <>
                  <MenuSeparator />
                  <div className="px-2 py-1.5">
                    <Select
                      value={pageId || ""}
                      onValueChange={(nextPageId) => {
                        if (!funnelId || !nextPageId) return;
                        navigate(`/research/funnels/${funnelId}/pages/${nextPageId}`);
                      }}
                      options={[
                        { label: "Select page", value: "" },
                        ...pageOptions.map((o) => ({ label: o.label, value: o.value })),
                      ]}
                    />
                  </div>
                </>
              ) : null}
              <MenuSeparator />
              <MenuItem onClick={() => setSettingsOpen(true)}>Edit settings</MenuItem>
              <MenuItem
                onClick={() => {
                  if (!publicPageHref) return;
                  window.open(publicPageHref, "_blank", "noreferrer");
                }}
                className={!publicPageHref ? "pointer-events-none opacity-60" : undefined}
              >
                Open public page
              </MenuItem>
              <MenuSeparator />
              <MenuItem
                onClick={() => {
                  if (!funnelId || !pageId || saveDraft.isPending) return;
                  saveDraft.mutate({ funnelId, pageId, puckData: data });
                }}
                className={saveDraft.isPending ? "pointer-events-none opacity-60" : undefined}
              >
                {saveDraft.isPending ? "Saving draft..." : "Save draft"}
              </MenuItem>
            </MenuContent>
          </Menu>
        }
      />

      <DialogRoot open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent>
          <div className="space-y-4">
            <div className="space-y-1">
              <DialogTitle>Page settings</DialogTitle>
              <p className="text-sm text-content-muted">
                Update the page name, slug, default next page, and design system override.
              </p>
            </div>
            <div className="grid gap-3">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Page name</label>
                <Input value={draftName} onChange={(e) => setDraftName(e.target.value)} />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Slug</label>
                <Input value={draftSlug} onChange={(e) => setDraftSlug(e.target.value)} />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Design system override</label>
                <Select
                  value={draftDesignSystemId}
                  onValueChange={setDraftDesignSystemId}
                  options={designSystemOptions}
                />
                <div className="text-xs text-content-muted">
                  Leave as workspace default to inherit the brand tokens.
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Next page</label>
                <Select
                  value={draftNextPageId}
                  onValueChange={setDraftNextPageId}
                  options={nextPageOptions}
                />
                <div className="text-xs text-content-muted">
                  `nextPage` CTAs on this page will route here.
                </div>
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 pt-2">
              <Button variant="secondary" size="sm" onClick={() => setSettingsOpen(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => {
                  if (!funnelId || !pageId) return;
                  updatePage.mutate(
                    {
                      funnelId,
                      pageId,
                      payload: {
                        name: draftName,
                        slug: draftSlug,
                        designSystemId: draftDesignSystemId || null,
                        nextPageId: draftNextPageId || null,
                      },
                    },
                    {
                      onSuccess: () => {
                        setMetaName(draftName);
                        setMetaSlug(draftSlug);
                        setMetaDesignSystemId(draftDesignSystemId || null);
                        setMetaNextPageId(draftNextPageId || null);
                        setSettingsOpen(false);
                      },
                    }
                  );
                }}
                disabled={updatePage.isPending}
              >
                {updatePage.isPending ? "Saving..." : "Save"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </DialogRoot>

      {isLoading || !pageDetail ? (
        <div className="ds-card ds-card--md text-sm text-content-muted">Loading editor...</div>
      ) : (
        <>
          <div className="ds-card ds-card--md p-0 overflow-hidden">
            {siteCommerceLoading ? (
              <div className="h-0.5 animate-pulse bg-content/80" aria-hidden="true" />
            ) : null}
            {siteCommerceError ? (
              <div className="border-b border-danger/20 bg-danger/5 px-4 py-3 text-sm text-danger">
                Site commerce preview failed to load. {siteCommerceError}
              </div>
            ) : null}
            <FunnelRuntimeProvider
              value={{
                productSlug: runtimeProductSlug,
                funnelSlug: runtimeFunnelSlug,
                pageMap: runtimePageMap,
                pageStageMap: runtimePageStageMap,
                pageTypeMap: runtimePageTypeMap,
                pageId: pageDetail.page.id,
                nextPageId: pageDetail.page.next_page_id ?? null,
              }}
            >
              {isSiteEditor ? (
                <CommerceRuntimeProvider
                  productSlug={runtimeProductSlug}
                  funnelSlug={runtimeFunnelSlug}
                  apiBaseUrl={apiBaseUrl}
                  initialRegions={siteCommerce?.regions || []}
                  initialProducts={siteCommerce?.products || []}
                  initialCollections={siteCommerce?.collections || []}
                  initialCategories={siteCommerce?.categories || []}
                  initialCurrentProduct={siteCommerce?.currentProduct || null}
                  initialCurrentCategory={siteCommerce?.currentCategory || null}
                  siteFamily={siteCommerce?.siteFamily || null}
                  commerceProvider={siteCommerce?.commerceProvider || null}
                  storeName={siteCommerce?.storeName || null}
                >
                  <Puck
                    key={puckKey}
                    config={config}
                    data={data}
                    onChange={setData}
                    ui={editorUi}
                    viewports={editorViewports}
                    plugins={plugins}
                  />
                </CommerceRuntimeProvider>
              ) : (
                <Puck
                  key={puckKey}
                  config={config}
                  data={data}
                  onChange={setData}
                  ui={editorUi}
                  viewports={editorViewports}
                  plugins={plugins}
                />
              )}
            </FunnelRuntimeProvider>
          </div>
        </>
      )}
    </div>
  );
}
