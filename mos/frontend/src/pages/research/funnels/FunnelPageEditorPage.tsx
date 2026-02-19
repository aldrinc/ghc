import { Puck } from "@measured/puck";
import type { Data } from "@measured/puck";
import { useFunnel, useFunnelPage, useSaveFunnelDraft, useUpdateFunnelPage } from "@/api/funnels";
import { useProduct } from "@/api/products";
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
import { createFunnelPuckConfig, defaultFunnelPuckData, FunnelRuntimeProvider } from "@/funnels/puckConfig";
import { normalizePuckData } from "@/funnels/puckData";
import { buildPublicFunnelPath, shortUuidRouteToken } from "@/funnels/runtimeRouting";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

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
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftSlug, setDraftSlug] = useState("");
  const [draftDesignSystemId, setDraftDesignSystemId] = useState("");
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
  }, [pageDetail, pageId]);

  const pageOptions = useMemo(() => {
    return funnel?.pages?.map((p) => ({ label: p.name, value: p.id })) || [];
  }, [funnel?.pages]);

  const pageOptionsKey = useMemo(
    () => pageOptions.map((o) => `${o.value}:${o.label}`).join("|"),
    [pageOptions]
  );

  const config = useMemo(() => createFunnelPuckConfig(pageOptions), [pageOptionsKey]);
  const runtimePageMap = useMemo(() => {
    const entries = funnel?.pages?.map((p) => [p.id, p.slug]) ?? [];
    return Object.fromEntries(entries);
  }, [funnel?.pages]);

  const currentPageLabel = useMemo(() => {
    const page = funnel?.pages?.find((p) => p.id === pageId);
    return page ? `${page.name} (${page.slug})` : "Page";
  }, [funnel?.pages, pageId]);
  const runtimeProductSlug = shortUuidRouteToken(funnelProduct?.id || funnel?.product_id || "");
  const runtimeFunnelSlug = shortUuidRouteToken(funnel?.id || "");
  const publicPageHref = useMemo(() => {
    const slug = (metaSlug || pageDetail?.page.slug || "").trim();
    if (!runtimeProductSlug || !runtimeFunnelSlug || !slug) return null;
    return buildPublicFunnelPath({ productSlug: runtimeProductSlug, funnelSlug: runtimeFunnelSlug, slug, bundleMode: false });
  }, [metaSlug, pageDetail?.page.slug, runtimeFunnelSlug, runtimeProductSlug]);

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8008";
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
  const plugins = useMemo(() => [designSystemPlugin, aiPlugin], [designSystemPlugin, aiPlugin]);
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
  }, [settingsOpen, metaName, metaSlug, metaDesignSystemId]);

  const { data: designSystems = [] } = useDesignSystems(funnel?.client_id || workspace?.id);
  const designSystemOptions = useMemo(() => {
    return [
      { label: "Workspace default", value: "" },
      ...designSystems.map((ds) => ({ label: ds.name, value: ds.id })),
    ];
  }, [designSystems]);

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
              <p className="text-sm text-content-muted">Update the page name and slug for this funnel page.</p>
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
                      },
                    },
                    {
                      onSuccess: () => {
                        setMetaName(draftName);
                        setMetaSlug(draftSlug);
                        setMetaDesignSystemId(draftDesignSystemId || null);
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
            <FunnelRuntimeProvider
              value={{
                productSlug: runtimeProductSlug,
                funnelSlug: runtimeFunnelSlug,
                pageMap: runtimePageMap,
                pageId: pageDetail.page.id,
                nextPageId: pageDetail.page.next_page_id ?? null,
              }}
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
            </FunnelRuntimeProvider>
          </div>
        </>
      )}
    </div>
  );
}
