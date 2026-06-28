import { Puck } from "@measured/puck";
import type { Data } from "@measured/puck";
import type { Viewport } from "@measured/puck";
import { useProducts } from "@/api/products";
import { useSiteProductBindings } from "@/api/siteProductBindings";
import { useSite, useSitePage, useUpdateSitePage, useCreateSitePageVersion, useSiteMedusaConfig } from "@/api/sites";
import { B2CRuntimeProvider } from "@/components/commerce/b2c/B2CRuntimeProvider";
import { isMedusaB2CRuntimeSite } from "@/components/commerce/b2c/runtimeSite";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { DialogContent, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toast";
import { PageAgentPanel } from "@/components/agents/PageAgentPanel";
import { isImportedTemplatePageData } from "@/components/agents/pageAgentAvailability";
import { useDesignSystems } from "@/api/designSystems";
import { createDesignSystemPlugin } from "@/funnels/puckDesignSystemPlugin";
import { createPuckFieldTypesPlugin } from "@/funnels/puckFieldTypesPlugin";
import { FunnelRuntimeProvider } from "@/funnels/funnelRuntime";
import { createFunnelPuckConfig, defaultFunnelPuckData } from "@/funnels/puckConfig";
import { normalizePuckData } from "@/funnels/puckData";
import { buildRuntimePageMap, buildRuntimePageStageMap, buildRuntimePageTypeMap } from "@/funnels/runtimePageMaps";
import { shortUuidRouteToken } from "@/funnels/runtimeRouting";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { setMedusaRuntimeConfig } from "@/lib/medusa";
import { useSitePreviewDefaults } from "@/pages/workspaces/sites/sitePreviewDefaults";
import { buildSitePagePreviewPath, buildSitePreviewPath, getSitePagePreviewErrorMessage } from "@/pages/workspaces/sites/sitePreviewRouting";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ChevronRight, ExternalLink, Loader2, MoreVertical, Save, Settings } from "lucide-react";
import { SITE_PAGE_EDITOR_THEME_INHERITANCE_COPY } from "./sitePageEditorCopy";

/* ------------------------------------------------------------------ */
/*  Breadcrumb                                                         */
/* ------------------------------------------------------------------ */

function Breadcrumb({ items }: { items: Array<{ label: string; href?: string }> }) {
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-xs text-content-muted">
      {items.map((item, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <ChevronRight className="h-3 w-3 shrink-0" />}
          {item.href ? (
            <Link to={item.href} className="hover:text-content transition-colors truncate max-w-[12rem]">
              {item.label}
            </Link>
          ) : (
            <span className="text-content font-medium truncate max-w-[12rem]">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

function clonePuckData<T>(value: T): T {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value)) as T;
}

type ImportedRuntimeSyncEntry = {
  frameId: string;
  sectionSourceId: string | null;
  revision: string;
  textOverrides: Array<Record<string, unknown>>;
  buttonOverrides: Array<Record<string, unknown>>;
  imageOverrides: Array<Record<string, unknown>>;
};

function collectImportedRuntimeSyncEntries(data: Data): ImportedRuntimeSyncEntry[] {
  const zones = (data.zones || {}) as Record<string, unknown>;
  const entries: ImportedRuntimeSyncEntry[] = [];

  const visitNodes = (nodes: unknown, currentSectionSourceId: string | null) => {
    if (!Array.isArray(nodes)) return;

    for (const node of nodes) {
      if (!node || typeof node !== "object") continue;
      const record = node as Record<string, unknown>;
      const type = typeof record.type === "string" ? record.type : "";
      const props = record.props && typeof record.props === "object" ? (record.props as Record<string, unknown>) : {};
      const nodeId = typeof props.id === "string" ? props.id : null;
      const nextSectionSourceId =
        type === "ImportedSection" && typeof props.sourceSectionId === "string"
          ? props.sourceSectionId
          : currentSectionSourceId;

      if (type === "ImportedRuntimeSection" && nodeId) {
        const textOverrides = Array.isArray(props.textOverrides)
          ? (props.textOverrides as Array<Record<string, unknown>>)
          : [];
        const buttonOverrides = Array.isArray(props.buttonOverrides)
          ? (props.buttonOverrides as Array<Record<string, unknown>>)
          : [];
        const imageOverrides = Array.isArray(props.imageOverrides)
          ? (props.imageOverrides as Array<Record<string, unknown>>)
          : [];
        entries.push({
          frameId: `imported-runtime-${nodeId}`,
          sectionSourceId: nextSectionSourceId,
          revision: JSON.stringify({ textOverrides, buttonOverrides, imageOverrides }),
          textOverrides,
          buttonOverrides,
          imageOverrides,
        });
      }

      if (nodeId) {
        for (const [zoneKey, zoneValue] of Object.entries(zones)) {
          if (zoneKey.startsWith(`${nodeId}:`)) {
            visitNodes(zoneValue, nextSectionSourceId);
          }
        }
      }
    }
  };

  visitNodes(data.content, null);
  return entries;
}

function escapeAttributeValue(value: string): string {
  return value.replaceAll("\\", "\\\\").replaceAll('"', '\\"');
}

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

export function SitePageEditorPage() {
  const navigate = useNavigate();
  const { siteId, pageId } = useParams<{ siteId: string; pageId: string }>();
  const { clients, selectWorkspace, workspace } = useWorkspace();
  const { data: site } = useSite(siteId || null, {
    clientId: null,
    requireWorkspace: false,
  });
  const resolvedClientId = site?.clientId || workspace?.id || null;
  const { data: products = [] } = useProducts(resolvedClientId || undefined);
  const { data: pageDetail, isLoading } = useSitePage(siteId, pageId, {
    clientId: resolvedClientId,
  });
  const { data: productBindings = [] } = useSiteProductBindings(siteId || null, {
    clientId: resolvedClientId,
  });
  const { data: medusaConfig } = useSiteMedusaConfig(siteId);
  const {
    data: previewDefaults,
    error: previewDefaultsError,
  } = useSitePreviewDefaults(siteId || null, site?.siteFamily || null, site?.commerceProvider || null);
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
  const hydratedVersionKeyRef = useRef<string | null>(null);
  const blockedVersionKeyRef = useRef<string | null>(null);

  /** Snapshot of the last-saved data so we can detect dirty state. */
  const savedDataRef = useRef<Data | null>(null);
  const isDirty = useMemo(() => {
    if (!savedDataRef.current) return false;
    return JSON.stringify(data) !== JSON.stringify(savedDataRef.current);
  }, [data]);

  const backHref = siteId ? `/workspaces/sites/${siteId}` : "/workspaces/sites";

  useEffect(() => {
    if (!pageId) return;
    hydratedVersionKeyRef.current = null;
    blockedVersionKeyRef.current = null;
    setData(defaultFunnelPuckData() as unknown as Data);
    setPuckKey(pageId);
    savedDataRef.current = null;
  }, [pageId]);

  const sourceVersionKey = useMemo(() => {
    if (!pageDetail || !pageId) return null;
    return `${pageId}:${pageDetail.latestDraft?.id || pageDetail.latestApproved?.id || "initial"}`;
  }, [pageDetail, pageId]);

  useEffect(() => {
    if (!pageDetail || !pageId || !sourceVersionKey) return;
    if (hydratedVersionKeyRef.current === sourceVersionKey) return;
    if (savedDataRef.current && isDirty) {
      if (blockedVersionKeyRef.current !== sourceVersionKey) {
        blockedVersionKeyRef.current = sourceVersionKey;
        toast.error(
          "A newer canonical page draft exists, but the editor has unsaved local changes. Save or reload before applying the agent update.",
        );
      }
      return;
    }

    const initial =
      (pageDetail.latestDraft?.puckData as Data | undefined) ||
      (pageDetail.latestApproved?.puckData as Data | undefined) ||
      (defaultFunnelPuckData() as unknown as Data);
    const normalized = normalizePuckData(initial, { designSystemTokens: pageDetail.designSystemTokens ?? null });
    setData(clonePuckData(normalized));
    savedDataRef.current = clonePuckData(normalized);
    setPuckKey(sourceVersionKey);
    setMetaName(pageDetail.page.name);
    setMetaSlug(pageDetail.page.slug);
    setMetaDesignSystemId(pageDetail.page.designSystemId || null);
    hydratedVersionKeyRef.current = sourceVersionKey;
    blockedVersionKeyRef.current = null;
  }, [isDirty, pageDetail, pageId, sourceVersionKey]);

  const pageOptions = useMemo(() => {
    return site?.pages?.map((p) => ({ label: p.name, value: p.id })) || [];
  }, [site?.pages]);

  const pageOptionsKey = useMemo(
    () => pageOptions.map((o) => `${o.value}:${o.label}`).join("|"),
    [pageOptions]
  );

  const config = useMemo(() => createFunnelPuckConfig(pageOptions), [pageOptionsKey]);
  const runtimePages = useMemo(() => site?.pages ?? [], [site?.pages]);
  const runtimePageMap = useMemo(() => buildRuntimePageMap(runtimePages), [runtimePages]);
  const runtimePageStageMap = useMemo(() => buildRuntimePageStageMap(runtimePages), [runtimePages]);
  const runtimePageTypeMap = useMemo(() => buildRuntimePageTypeMap(runtimePages), [runtimePages]);
  const productsById = useMemo(
    () => new Map(products.map((product) => [product.id, product])),
    [products]
  );
  const primaryProductHandle = useMemo(
    () => (site?.productId ? productsById.get(site.productId)?.handle?.trim() || null : null),
    [productsById, site?.productId]
  );
  const productHandlesByPageId = useMemo(() => {
    const next = new Map<string, string>();
    const sortedBindings = [...productBindings]
      .filter((binding) => binding.active)
      .sort((left, right) => {
        if (left.priority !== right.priority) {
          return left.priority - right.priority;
        }
        return left.createdAt.localeCompare(right.createdAt);
      });

    for (const binding of sortedBindings) {
      if (next.has(binding.sitePageId)) {
        continue;
      }
      const productHandle = productsById.get(binding.productId)?.handle?.trim();
      if (productHandle) {
        next.set(binding.sitePageId, productHandle);
      }
    }

    return next;
  }, [productBindings, productsById]);
  const previewPage = useMemo(() => {
    if (!pageDetail) {
      return null;
    }

    return {
      id: pageDetail.page.id,
      name: metaName || pageDetail.page.name,
      slug: metaSlug || pageDetail.page.slug,
      pageType: pageDetail.page.pageType,
      templateId: pageDetail.page.templateId,
      ordering: pageDetail.page.ordering,
      isEntry: site?.entryPageId === pageDetail.page.id,
      latestDraftVersionId: pageDetail.latestDraft?.id || null,
      latestApprovedVersionId: pageDetail.latestApproved?.id || null,
    };
  }, [metaName, metaSlug, pageDetail, site?.entryPageId]);
  const previewPageHref = useMemo(
    () =>
      siteId && previewPage
        ? buildSitePagePreviewPath(siteId, previewPage, {
            siteFamily: site?.siteFamily,
            commerceProvider: site?.commerceProvider,
            productHandle: productHandlesByPageId.get(previewPage.id) || primaryProductHandle,
            collectionHandle: previewDefaults?.collectionHandle,
            categoryHandle: previewDefaults?.categoryHandle,
          })
        : null,
    [
      previewDefaults?.categoryHandle,
      previewDefaults?.collectionHandle,
      previewPage,
      primaryProductHandle,
      productHandlesByPageId,
      site?.commerceProvider,
      site?.siteFamily,
      siteId,
    ]
  );
  const previewProductSlug = useMemo(
    () => shortUuidRouteToken(site?.productId || site?.id || ""),
    [site?.id, site?.productId]
  );
  const previewFunnelSlug = useMemo(
    () => site?.routeSlug || shortUuidRouteToken(site?.id || ""),
    [site?.id, site?.routeSlug]
  );
  const isB2CSiteEditor = isMedusaB2CRuntimeSite({
    siteFamily: site?.siteFamily,
    commerceProvider: site?.commerceProvider,
  }) && Object.keys(runtimePageTypeMap).length > 0;

  const currentPageName = useMemo(() => {
    const page = site?.pages?.find((p) => p.id === pageId);
    return page ? page.name : "Page";
  }, [site?.pages, pageId]);

  const designSystemTokens = pageDetail?.designSystemTokens ?? null;
  const designSystemPlugin = useMemo(
    () => createDesignSystemPlugin({ tokens: designSystemTokens }),
    [designSystemTokens]
  );
  const fieldTypesPlugin = useMemo(() => createPuckFieldTypesPlugin(), []);
  const plugins = useMemo(() => [designSystemPlugin, fieldTypesPlugin], [designSystemPlugin, fieldTypesPlugin]);
  const editorViewports = useMemo<Viewport[]>(
    () => [
      { width: 375, height: "auto", icon: "Smartphone", label: "Small" },
      { width: 768, height: "auto", icon: "Tablet", label: "Medium" },
      { width: 1280, height: "auto", icon: "Monitor", label: "Large" },
      { width: 1920, height: 1080, icon: "Monitor", label: "Desktop (1920\u00d71080)" },
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
  const importedRuntimeSyncEntries = useMemo(() => collectImportedRuntimeSyncEntries(data), [data]);
  const pageAgentEnabled = useMemo(() => isImportedTemplatePageData(data), [data]);
  const importedRuntimeSyncKey = useMemo(
    () =>
      importedRuntimeSyncEntries
        .map((entry) => `${entry.frameId}:${entry.sectionSourceId || ""}:${entry.revision}`)
        .join("|"),
    [importedRuntimeSyncEntries]
  );

  useEffect(() => {
    if (!settingsOpen) return;
    setDraftName(metaName);
    setDraftSlug(metaSlug);
    setDraftDesignSystemId(metaDesignSystemId || "");
  }, [settingsOpen, metaName, metaSlug, metaDesignSystemId]);

  useEffect(() => {
    const runtimeConfig = medusaConfig?.medusaConfig;
    if (!runtimeConfig?.available || !runtimeConfig.baseUrl || !runtimeConfig.publishableKey) {
      setMedusaRuntimeConfig(null);
      return () => setMedusaRuntimeConfig(null);
    }

    setMedusaRuntimeConfig({
      backendUrl: runtimeConfig.baseUrl,
      publishableKey: runtimeConfig.publishableKey,
      stripeAccountId: runtimeConfig.stripeAccountId || undefined,
      defaultCountryCode: "us",
    });

    return () => setMedusaRuntimeConfig(null);
  }, [medusaConfig?.medusaConfig]);

  useEffect(() => {
    if (!importedRuntimeSyncEntries.length) return;

    const syncImportedRuntimeSections = () => {
      const previewFrame = document.querySelector('iframe[name="preview-frame"]') as HTMLIFrameElement | null;
      const previewDocument = previewFrame?.contentDocument;
      if (!previewDocument) return;

      for (const entry of importedRuntimeSyncEntries) {
        const sectionSelector = entry.sectionSourceId
          ? `section[data-imported-section-id="${escapeAttributeValue(entry.sectionSourceId)}"] iframe`
          : "section[data-imported-section-id] iframe";
        const targetIframe = previewDocument.querySelector(sectionSelector) as HTMLIFrameElement | null;
        targetIframe?.contentWindow?.postMessage(
          {
            source: "mos-imported-runtime-host",
            frameId: entry.frameId,
            type: "update-overrides",
            revision: entry.revision,
            textOverrides: entry.textOverrides,
            buttonOverrides: entry.buttonOverrides,
            imageOverrides: entry.imageOverrides,
          },
          "*",
        );
      }
    };

    const animationFrameId = window.requestAnimationFrame(syncImportedRuntimeSections);
    const timeoutId = window.setTimeout(syncImportedRuntimeSections, 120);
    return () => {
      window.cancelAnimationFrame(animationFrameId);
      window.clearTimeout(timeoutId);
    };
  }, [importedRuntimeSyncEntries, importedRuntimeSyncKey]);

  const { data: designSystems = [] } = useDesignSystems(resolvedClientId || undefined);

  useEffect(() => {
    if (!resolvedClientId || workspace?.id === resolvedClientId) return;
    const matchingClient = clients.find((client) => client.id === resolvedClientId);
    if (!matchingClient) return;
    selectWorkspace(resolvedClientId);
  }, [clients, resolvedClientId, selectWorkspace, workspace?.id]);
  const designSystemOptions = useMemo(() => {
    return [
      { label: "Inherit from site theme", value: "" },
      ...designSystems.map((ds) => ({ label: ds.name, value: ds.id })),
    ];
  }, [designSystems]);

  const handlePuckChange = useCallback((nextData: Data) => {
    setData(clonePuckData(nextData));
  }, []);

  const handleSaveDraft = useCallback(() => {
    if (!siteId || !pageId) return;
    createVersion.mutate(
      { puckData: data, status: "draft" },
      {
        onSuccess: () => {
          savedDataRef.current = clonePuckData(data);
          toast.success("Draft saved");
        },
        onError: (err) => {
          toast.error(err instanceof Error ? err.message : "Failed to save draft");
        },
      },
    );
  }, [createVersion, data, pageId, siteId]);

  const openPreview = () => {
    if (!previewPageHref) {
      toast.error(
        getSitePagePreviewErrorMessage(previewPage || pageDetail?.page || { pageType: null }, {
          medusaPreviewDataError: previewDefaultsError,
        }),
      );
      return;
    }
    window.open(previewPageHref, "_blank", "noreferrer");
  };

  /* ---- Loading state ---- */
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

  /* ---- Status badge ---- */
  const statusBadge = isDirty ? (
    <Badge tone="warning">Unsaved changes</Badge>
  ) : pageDetail?.latestDraft ? (
    <Badge tone="neutral">Draft saved</Badge>
  ) : null;

  return (
    <div className="space-y-4">
      <PageHeader
        compact
        title={
          <span className="flex flex-wrap items-center gap-2">
            <span>{currentPageName}</span>
            {statusBadge}
          </span>
        }
        description={
          <Breadcrumb
            items={[
              { label: "Sites", href: "/workspaces/sites" },
              { label: site?.name || "Site", href: backHref },
              { label: currentPageName },
            ]}
          />
        }
        actions={
          <div className="flex items-center gap-2">
            {/* Page switcher – inline for quick access */}
            {site?.pages && site.pages.length > 1 && (
              <Select
                value={pageId || ""}
                onValueChange={(nextPageId) => {
                  if (!siteId || !nextPageId) return;
                  navigate(`/workspaces/sites/${siteId}/pages/${nextPageId}`);
                }}
                options={[
                  { label: "Switch page\u2026", value: "" },
                  ...pageOptions.map((o) => ({ label: o.label, value: o.value })),
                ]}
              />
            )}

            {/* Primary: Save Draft */}
            <Button
              size="sm"
              onClick={handleSaveDraft}
              disabled={createVersion.isPending || !isDirty}
            >
              {createVersion.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-2 h-4 w-4" />
              )}
              {createVersion.isPending ? "Saving\u2026" : "Save Draft"}
            </Button>

            {/* Secondary actions menu */}
            <Menu>
              <MenuTrigger className={buttonClasses({ variant: "secondary", size: "sm" })}>
                <MoreVertical className="h-4 w-4" />
              </MenuTrigger>
              <MenuContent className="w-56">
                <MenuItem onClick={() => navigate(backHref)}>
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  Back to Site
                </MenuItem>
                <MenuSeparator />
                <MenuItem onClick={() => setSettingsOpen(true)}>
                  <Settings className="mr-2 h-4 w-4" />
                  Page settings
                </MenuItem>
                <MenuItem
                  onClick={openPreview}
                  className={!previewPageHref ? "opacity-60" : undefined}
                >
                  <ExternalLink className="mr-2 h-4 w-4" />
                  Open preview
                </MenuItem>
              </MenuContent>
            </Menu>
          </div>
        }
      />

      {/* ---- Settings Dialog ---- */}
      <DialogRoot open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent>
          <div className="space-y-4">
            <div className="space-y-1">
              <DialogTitle>Page settings</DialogTitle>
              <p className="text-sm text-content-muted">Update the page name and slug for this site page.</p>
            </div>
            <div className="grid gap-3">
              <FormField label="Page name">
                <Input value={draftName} onChange={(e) => setDraftName(e.target.value)} />
              </FormField>
              <FormField label="Slug">
                <Input value={draftSlug} onChange={(e) => setDraftSlug(e.target.value)} />
              </FormField>
              <FormField label="Design system override" helper={SITE_PAGE_EDITOR_THEME_INHERITANCE_COPY}>
                <Select
                  value={draftDesignSystemId}
                  onValueChange={setDraftDesignSystemId}
                  options={designSystemOptions}
                />
              </FormField>
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
                        toast.success("Page settings saved");
                      },
                      onError: (err) => {
                        toast.error(err instanceof Error ? err.message : "Failed to save page settings");
                      },
                    }
                  );
                }}
                disabled={updatePage.isPending}
              >
                {updatePage.isPending ? "Saving\u2026" : "Save"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </DialogRoot>

      {/* ---- Editor ---- */}
      <div className="ds-card ds-card--md overflow-hidden p-0">
        <FunnelRuntimeProvider
          value={{
            productSlug: previewProductSlug || "preview-product",
            funnelSlug: previewFunnelSlug || "preview-site",
            pageMap: runtimePageMap,
            pageStageMap: runtimePageStageMap,
            pageTypeMap: runtimePageTypeMap,
            bundleMode: false,
            entrySlug: null,
            pageStage: undefined,
            trackEvent: undefined,
            commerce: null,
            commerceError: null,
            pageId: pageDetail.page.id,
            nextPageId: null,
            resolvePagePath: (slug: string) => buildSitePreviewPath(site?.id || siteId || "", slug),
            resolveSitePath: (sitePath: string) => buildSitePreviewPath(site?.id || siteId || "", sitePath),
          }}
        >
          {isB2CSiteEditor ? (
            <B2CRuntimeProvider
              siteFamily={site?.siteFamily || "medusa-b2c-starter"}
              siteName={site?.name || null}
              siteId={site?.id || null}
            >
              <Puck
                key={puckKey}
                config={config}
                data={data}
                onChange={handlePuckChange}
                ui={editorUi}
                viewports={editorViewports}
                plugins={plugins}
              />
            </B2CRuntimeProvider>
          ) : (
            <Puck
              key={puckKey}
              config={config}
              data={data}
              onChange={handlePuckChange}
              ui={editorUi}
              viewports={editorViewports}
              plugins={plugins}
            />
          )}
        </FunnelRuntimeProvider>
      </div>
      <PageAgentPanel
        defaultOpen
        clientId={site?.clientId || workspace?.id || null}
        productId={site?.productId || null}
        siteId={siteId || null}
        pageId={pageId || null}
        pageName={currentPageName}
        pageSlug={metaSlug || pageDetail.page.slug}
        mode="editor"
        enabled={pageAgentEnabled}
        unavailableReason="The Hermes page agent currently supports imported-template pages only."
      />
    </div>
  );
}
