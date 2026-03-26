import { Puck } from "@measured/puck";
import type { Data } from "@measured/puck";
import { useSite, useSitePage, useUpdateSitePage, useCreateSitePageVersion } from "@/api/sites";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { DialogContent, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { Select } from "@/components/ui/select";
import { useDesignSystems } from "@/api/designSystems";
import { createDesignSystemPlugin } from "@/funnels/puckDesignSystemPlugin";
import { createFunnelPuckConfig, defaultFunnelPuckData, FunnelRuntimeProvider } from "@/funnels/puckConfig";
import { normalizePuckData } from "@/funnels/puckData";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Loader2 } from "lucide-react";

export function SitePageEditorPage() {
  const navigate = useNavigate();
  const { siteId, pageId } = useParams<{ siteId: string; pageId: string }>();
  const { workspace } = useWorkspace();
  const { data: site } = useSite(siteId);
  const { data: pageDetail, isLoading } = useSitePage(siteId, pageId);
  const updatePage = useUpdateSitePage(siteId, pageId);
  const createVersion = useCreateSitePageVersion(siteId, pageId);

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
  const backHref = siteId ? `/workspaces/sites/${siteId}` : "/workspaces/sites";

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
      (pageDetail.latestDraft?.puckData as Data | undefined) ||
      (pageDetail.latestApproved?.puckData as Data | undefined) ||
      (defaultFunnelPuckData() as unknown as Data);
    setData(normalizePuckData(initial, { designSystemTokens: pageDetail.designSystemTokens ?? null }));
    setPuckKey(`${pageId}:${pageDetail.latestDraft?.id || pageDetail.latestApproved?.id || "initial"}`);
    setMetaName(pageDetail.page.name);
    setMetaSlug(pageDetail.page.slug);
    setMetaDesignSystemId(pageDetail.page.designSystemId || null);
  }, [pageDetail, pageId]);

  const pageOptions = useMemo(() => {
    return site?.pages?.map((p) => ({ label: p.name, value: p.id })) || [];
  }, [site?.pages]);

  const pageOptionsKey = useMemo(
    () => pageOptions.map((o) => `${o.value}:${o.label}`).join("|"),
    [pageOptions]
  );

  const config = useMemo(() => createFunnelPuckConfig(pageOptions), [pageOptionsKey]);
  const runtimePageMap = useMemo(() => {
    const entries = site?.pages?.map((p) => [p.id, p.slug]) ?? [];
    return Object.fromEntries(entries);
  }, [site?.pages]);

  const currentPageLabel = useMemo(() => {
    const page = site?.pages?.find((p) => p.id === pageId);
    return page ? `${page.name} (${page.slug})` : "Page";
  }, [site?.pages, pageId]);

  const designSystemTokens = pageDetail?.designSystemTokens ?? null;
  const designSystemPlugin = useMemo(
    () => createDesignSystemPlugin({ tokens: designSystemTokens }),
    [designSystemTokens]
  );
  const plugins = useMemo(() => [designSystemPlugin], [designSystemPlugin]);
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

  const { data: designSystems = [] } = useDesignSystems(workspace?.id);
  const designSystemOptions = useMemo(() => {
    return [
      { label: "Workspace default", value: "" },
      ...designSystems.map((ds) => ({ label: ds.name, value: ds.id })),
    ];
  }, [designSystems]);

  const handleSaveDraft = () => {
    if (!siteId || !pageId) return;
    createVersion.mutate({ puckData: data, status: "draft" });
  };

  if (isLoading || !pageDetail) {
    return (
      <div className="space-y-4">
        <PageHeader title="Site Page Editor" description="Loading page editor...">
          <div className="flex items-center gap-2 text-sm text-content-muted">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading...
          </div>
        </PageHeader>
      </div>
    );
  }

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
        description={site ? `Site: ${site.name}` : "Edit site page"}
        actions={
          <Menu>
            <MenuTrigger className={buttonClasses({ variant: "secondary", size: "sm" })}>Actions</MenuTrigger>
            <MenuContent className="w-64">
              <MenuItem onClick={() => navigate(backHref)}>
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back to Site
              </MenuItem>
              {site?.pages?.length ? (
                <>
                  <MenuSeparator />
                  <div className="px-2 py-1.5">
                    <Select
                      value={pageId || ""}
                      onValueChange={(nextPageId) => {
                        if (!siteId || !nextPageId) return;
                        navigate(`/workspaces/sites/${siteId}/pages/${nextPageId}`);
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
              <MenuSeparator />
              <MenuItem
                onClick={handleSaveDraft}
                className={createVersion.isPending ? "pointer-events-none opacity-60" : undefined}
              >
                {createVersion.isPending ? "Saving draft..." : "Save draft"}
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
              <p className="text-sm text-content-muted">Update the page name and slug for this site page.</p>
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
                  if (!siteId || !pageId) return;
                  updatePage.mutate(
                    {
                      name: draftName,
                      slug: draftSlug,
                      designSystemId: draftDesignSystemId || null,
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

      <div className="ds-card ds-card--md p-0 overflow-hidden">
        <FunnelRuntimeProvider
          value={{
            productSlug: "",
            funnelSlug: site?.routeSlug || siteId || "",
            pageMap: runtimePageMap,
            pageStageMap: {},
            pageTypeMap: {},
            bundleMode: false,
            entrySlug: null,
            pageStage: undefined,
            trackEvent: undefined,
            commerce: null,
            commerceError: null,
            pageId: pageDetail.page.id,
            nextPageId: null,
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
    </div>
  );
}
