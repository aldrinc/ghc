import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { Globe, Edit, ExternalLink, Loader2, ArrowLeft, LayoutGrid, Settings, Funnel, FileText, Package, Palette, Plus, Trash2, Check, AlertCircle, LayoutTemplate } from "lucide-react";

import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useClient } from "@/api/clients";
import { useProducts } from "@/api/products";
import { useSite, useUpdateSite, type SiteThemeBindingMode } from "@/api/sites";
import { useSiteFunnels, useCreateSiteFunnel, useDeleteSiteFunnel } from "@/api/siteFunnels";
import { useCreateSiteProductBinding, useDeleteSiteProductBinding, useSiteProductBindings } from "@/api/siteProductBindings";
import { useCreateSiteTemplateFromSite } from "@/api/siteTemplates";
import { useDesignSystems } from "@/api/designSystems";
import { MedusaConnectionCard } from "@/components/commerce/MedusaConnectionCard";
import { EmptyState } from "@/components/layout/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { DialogContent, DialogRoot, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import {
  formatSiteType,
  formatCommerceProvider,
  formatSiteFamily,
  formatPageType,
  formatFunnelStatus,
  formatDateTime,
  getErrorMessage,
} from "@/lib/siteFormatters";
import { useSitePreviewDefaults } from "@/pages/workspaces/sites/sitePreviewDefaults";
import { buildSitePagePreviewPath, getSitePagePreviewErrorMessage } from "@/pages/workspaces/sites/sitePreviewRouting";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function getThemeBindingLabel(mode: SiteThemeBindingMode | null | undefined): string {
  switch (mode) {
    case "standalone": return "Standalone";
    case "workspace_default": return "Workspace brand";
    case "design_system": return "Design system";
    default: return "Not set";
  }
}

function getThemeBindingDescription(mode: SiteThemeBindingMode | null | undefined): string {
  switch (mode) {
    case "standalone": return "Uses generic styling without brand tokens";
    case "workspace_default": return "Inherits the workspace default design system";
    case "design_system": return "Uses a specific design system for this site";
    default: return "Theme source not configured";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function readTokenString(cssVars: Record<string, unknown>, ...keys: string[]): string | null {
  for (const key of keys) {
    const candidate = cssVars[key];
    if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
  }
  return null;
}

function summarizeDesignSystem(tokens: unknown) {
  if (!isRecord(tokens)) {
    return { brandName: null, hasLogo: false, hasFonts: false, headingFont: null, bodyFont: null, keyColors: [] as Array<{ label: string; value: string }> };
  }
  const brand = isRecord(tokens.brand) ? tokens.brand : {};
  const cssVars = isRecord(tokens.cssVars) ? tokens.cssVars : {};
  const headingFont = readTokenString(cssVars, "--font-heading");
  const bodyFont = readTokenString(cssVars, "--font-sans", "--font-body");
  return {
    brandName: typeof brand.name === "string" && brand.name.trim() ? brand.name.trim() : null,
    hasLogo: typeof brand.logoAssetPublicId === "string" && brand.logoAssetPublicId.trim().length > 0,
    hasFonts: Boolean(headingFont || bodyFont),
    headingFont,
    bodyFont,
    keyColors: [
      { label: "Brand", value: readTokenString(cssVars, "--color-brand") || "Not set" },
      { label: "Background", value: readTokenString(cssVars, "--color-bg", "--color-page-bg") || "Not set" },
      { label: "Text", value: readTokenString(cssVars, "--color-text") || "Not set" },
      { label: "CTA", value: readTokenString(cssVars, "--color-cta") || "Not set" },
    ],
  };
}

/* ------------------------------------------------------------------ */
/*  Skeletons                                                          */
/* ------------------------------------------------------------------ */

function StatCardSkeleton() {
  return (
    <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
      <Skeleton className="h-3 w-20 mb-2" />
      <Skeleton className="h-6 w-12" />
    </div>
  );
}

function RowSkeleton() {
  return (
    <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="space-y-2 flex-1">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-3 w-56" />
        </div>
        <Skeleton className="h-8 w-16 rounded" />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

export function SiteDetailPage() {
  const { siteId } = useParams<{ siteId: string }>();
  const { workspace } = useWorkspace();
  const { data: workspaceClient } = useClient(workspace?.id);
  const location = useLocation();
  const navigate = useNavigate();
  const { data: site, isLoading, error } = useSite(siteId || null);
  const { data: products = [], isLoading: productsLoading } = useProducts(workspace?.id);
  const { data: funnels = [], isLoading: funnelsLoading, error: funnelsError } = useSiteFunnels(siteId || null);
  const {
    data: productBindings = [],
    isLoading: bindingsLoading,
    error: bindingsError,
  } = useSiteProductBindings(siteId || null);
  const {
    data: previewDefaults,
    error: previewDefaultsError,
  } = useSitePreviewDefaults(siteId || null, site?.siteFamily || null, site?.commerceProvider || null);
  const { data: designSystems = [] } = useDesignSystems(workspace?.id);
  const createFunnel = useCreateSiteFunnel(siteId || null);
  const deleteFunnel = useDeleteSiteFunnel(siteId || null);
  const createBinding = useCreateSiteProductBinding(siteId || null);
  const deleteBinding = useDeleteSiteProductBinding(siteId || null);
  const updateSite = useUpdateSite(siteId || null);
  const createTemplateFromSite = useCreateSiteTemplateFromSite();

  const isFunnelsRoute = useMemo(() => location.pathname.includes("/funnels"), [location.pathname]);
  const [activeTab, setActiveTab] = useState<"overview" | "pages" | "funnels" | "products" | "theme" | "settings">(
    isFunnelsRoute ? "funnels" : "overview"
  );
  const [showCreateFunnelForm, setShowCreateFunnelForm] = useState(false);
  const [newFunnelName, setNewFunnelName] = useState("");
  const [newFunnelDescription, setNewFunnelDescription] = useState("");
  const [newFunnelEntryPageId, setNewFunnelEntryPageId] = useState("");
  const [newFunnelProductId, setNewFunnelProductId] = useState("");
  const [showCreateBindingForm, setShowCreateBindingForm] = useState(false);
  const [selectedBindingProductId, setSelectedBindingProductId] = useState("");
  const [selectedBindingPageId, setSelectedBindingPageId] = useState("");
  const [selectedBindingFunnelId, setSelectedBindingFunnelId] = useState("");
  const [bindingRole, setBindingRole] = useState("");
  const [deletingFunnelId, setDeletingFunnelId] = useState<string | null>(null);
  const [deletingBindingId, setDeletingBindingId] = useState<string | null>(null);
  const [showCreateTemplateDialog, setShowCreateTemplateDialog] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const [templateDescription, setTemplateDescription] = useState("");

  // Theme tab state
  const [themeBindingMode, setThemeBindingMode] = useState<SiteThemeBindingMode>("standalone");
  const [selectedDesignSystemId, setSelectedDesignSystemId] = useState<string>("");
  const [isEditingTheme, setIsEditingTheme] = useState(false);

  useEffect(() => {
    if (site) {
      setThemeBindingMode(site.themeBindingMode || "standalone");
      setSelectedDesignSystemId(site.designSystemId || "");
    }
  }, [site]);

  const sortedPages = useMemo(
    () => [...(site?.pages ?? [])].sort((a, b) => a.ordering - b.ordering),
    [site?.pages],
  );
  const productsById = useMemo(
    () => new Map(products.map((product) => [product.id, product])),
    [products],
  );
  const primaryProductHandle = useMemo(
    () => (site?.productId ? productsById.get(site.productId)?.handle?.trim() || null : null),
    [productsById, site?.productId],
  );
  const productHandlesByPageId = useMemo(() => {
    const next = new Map<string, string>();
    const sorted = [...productBindings]
      .filter((b) => b.active)
      .sort((a, b) => (a.priority !== b.priority ? a.priority - b.priority : a.createdAt.localeCompare(b.createdAt)));
    for (const binding of sorted) {
      if (next.has(binding.sitePageId)) continue;
      const h = productsById.get(binding.productId)?.handle?.trim();
      if (h) next.set(binding.sitePageId, h);
    }
    return next;
  }, [productBindings, productsById]);
  const activeProductBindings = useMemo(() => productBindings.filter((b) => b.active), [productBindings]);
  const activeBoundProducts = useMemo(() => {
    const ordered: string[] = [];
    const seen = new Set<string>();
    for (const b of activeProductBindings) {
      if (seen.has(b.productId)) continue;
      seen.add(b.productId);
      ordered.push(b.productId);
    }
    return ordered.map((pid) => ({ id: pid, title: productsById.get(pid)?.title || `Product ${pid.slice(0, 8)}...` }));
  }, [activeProductBindings, productsById]);

  const pagePreviewHrefs = useMemo(() => {
    const map = new Map<string, string | null>();
    if (!siteId) return map;
    for (const page of sortedPages) {
      map.set(page.id, buildSitePagePreviewPath(siteId, page, {
        siteFamily: site?.siteFamily,
        commerceProvider: site?.commerceProvider,
        productHandle: productHandlesByPageId.get(page.id) || primaryProductHandle,
        collectionHandle: previewDefaults?.collectionHandle,
        categoryHandle: previewDefaults?.categoryHandle,
      }));
    }
    return map;
  }, [
    previewDefaults?.categoryHandle,
    previewDefaults?.collectionHandle,
    primaryProductHandle,
    productHandlesByPageId,
    site?.commerceProvider,
    site?.siteFamily,
    siteId,
    sortedPages,
  ]);

  const entryPage = useMemo(() => sortedPages.find((p) => p.id === site?.entryPageId) || null, [site?.entryPageId, sortedPages]);
  const entryPreviewHref = useMemo(() => (entryPage ? pagePreviewHrefs.get(entryPage.id) || null : null), [entryPage, pagePreviewHrefs]);
  const productOptions = useMemo(() => [
    { label: productsLoading ? "Loading products..." : "Select a product", value: "" },
    ...products.map((p) => ({ label: p.title, value: p.id })),
  ], [products, productsLoading]);
  const pageOptions = useMemo(() => [
    { label: "Select a page", value: "" },
    ...sortedPages.map((p) => ({ label: `${p.name} (/${p.slug})`, value: p.id })),
  ], [sortedPages]);
  const funnelOptions = useMemo(() => [
    { label: "Site-wide binding", value: "" },
    ...funnels.map((f) => ({ label: f.name, value: f.id })),
  ], [funnels]);
  const designSystemOptions = useMemo(() => [
    { label: "Select a design system", value: "" },
    ...designSystems.map((ds) => ({ label: ds.name, value: ds.id })),
  ], [designSystems]);

  const selectedDesignSystem = useMemo(() => designSystems.find((ds) => ds.id === selectedDesignSystemId), [designSystems, selectedDesignSystemId]);
  const workspaceDefaultDesignSystem = useMemo(() => designSystems.find((ds) => ds.id === workspaceClient?.design_system_id) || null, [designSystems, workspaceClient?.design_system_id]);
  const effectiveThemeMode = themeBindingMode || site?.themeBindingMode || "standalone";
  const effectiveDesignSystem = useMemo(() => {
    if (effectiveThemeMode === "design_system") return selectedDesignSystem || null;
    if (effectiveThemeMode === "workspace_default") return workspaceDefaultDesignSystem;
    return null;
  }, [effectiveThemeMode, selectedDesignSystem, workspaceDefaultDesignSystem]);
  const effectiveThemeSummary = useMemo(() => summarizeDesignSystem(effectiveDesignSystem?.tokens), [effectiveDesignSystem?.tokens]);

  useEffect(() => {
    if (isFunnelsRoute && activeTab !== "funnels") setActiveTab("funnels");
    if (!isFunnelsRoute && activeTab === "funnels") setActiveTab("overview");
  }, [activeTab, isFunnelsRoute]);

  const handleTabChange = (nextTab: typeof activeTab) => {
    setActiveTab(nextTab);
    if (!siteId) return;
    if (nextTab === "funnels") { navigate(`/workspaces/sites/${siteId}/funnels`); return; }
    if (isFunnelsRoute) navigate(`/workspaces/sites/${siteId}`);
  };

  const openCreateFunnelForm = () => {
    setNewFunnelName(""); setNewFunnelDescription("");
    setNewFunnelEntryPageId(site?.entryPageId || "");
    setNewFunnelProductId(site?.productId || "");
    setShowCreateFunnelForm(true);
  };

  const openCreateBindingForm = () => {
    const defaultPage = sortedPages.find((p) => p.pageType === "product_detail") ?? sortedPages[0];
    setSelectedBindingProductId(site?.productId || "");
    setSelectedBindingPageId(defaultPage?.id || "");
    setSelectedBindingFunnelId("");
    setBindingRole(defaultPage?.pageType || "product_detail");
    setShowCreateBindingForm(true);
  };

  const openCreateTemplateDialog = () => {
    if (!siteId || !site) return;
    setTemplateName(`${site.name} Template`);
    setTemplateDescription(site.description || "");
    setShowCreateTemplateDialog(true);
  };

  const handleSaveTheme = async () => {
    if (!siteId) return;
    try {
      await updateSite.mutateAsync({
        themeBindingMode,
        designSystemId: themeBindingMode === "design_system" ? selectedDesignSystemId || null : null,
      });
      setIsEditingTheme(false);
      toast.success("Theme settings saved");
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to save theme settings"));
    }
  };

  const handleCancelThemeEdit = () => {
    if (site) { setThemeBindingMode(site.themeBindingMode || "standalone"); setSelectedDesignSystemId(site.designSystemId || ""); }
    setIsEditingTheme(false);
  };

  const handleCreateTemplate = async () => {
    if (!siteId || !site || !templateName.trim()) return;
    try {
      const template = await createTemplateFromSite.mutateAsync({
        siteId,
        name: templateName.trim(),
        description: templateDescription.trim() || undefined,
      });
      setShowCreateTemplateDialog(false);
      toast.success("Template created");
      navigate(`/workspaces/sites/templates/${template.id}`);
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to create site template"));
    }
  };

  const siteUsesExplicitBindingsOnly = !site?.productId && activeProductBindings.length > 0;
  const openPagePreview = (page: typeof sortedPages[number], previewHref: string | null) => {
    if (!previewHref) { toast.error(getSitePagePreviewErrorMessage(page, { medusaPreviewDataError: previewDefaultsError })); return; }
    window.open(previewHref, "_blank", "noreferrer");
  };

  const handleCreateFunnel = async () => {
    if (!newFunnelName.trim()) return;
    try {
      await createFunnel.mutateAsync({
        name: newFunnelName.trim(),
        description: newFunnelDescription.trim() || undefined,
        entryPageId: newFunnelEntryPageId || undefined,
        productId: newFunnelProductId || undefined,
      });
      setShowCreateFunnelForm(false);
      toast.success("Funnel created");
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to create funnel"));
    }
  };

  const handleDeleteFunnel = async (funnelId: string) => {
    setDeletingFunnelId(funnelId);
    try {
      await deleteFunnel.mutateAsync(funnelId);
      toast.success("Funnel deleted");
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to delete funnel"));
    } finally {
      setDeletingFunnelId(null);
    }
  };

  const handleBindingPageChange = (pid: string) => {
    setSelectedBindingPageId(pid);
    const p = sortedPages.find((page) => page.id === pid);
    setBindingRole(p?.pageType || "product_detail");
  };

  const handleCreateBinding = async () => {
    if (!selectedBindingProductId || !selectedBindingPageId || !bindingRole.trim()) return;
    try {
      await createBinding.mutateAsync({
        productId: selectedBindingProductId,
        sitePageId: selectedBindingPageId,
        siteFunnelId: selectedBindingFunnelId || undefined,
        pageRole: bindingRole.trim(),
      });
      setShowCreateBindingForm(false);
      toast.success("Product binding created");
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to create product binding"));
    }
  };

  const handleDeleteBinding = async (bindingId: string) => {
    setDeletingBindingId(bindingId);
    try {
      await deleteBinding.mutateAsync(bindingId);
      toast.success("Binding removed");
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to delete binding"));
    } finally {
      setDeletingBindingId(null);
    }
  };

  const primaryProductLabel = site?.productId
    ? productsById.get(site.productId)?.title || `${site.productId.slice(0, 8)}...`
    : "Not set";

  const themeUsageItems = [
    { label: "Logo / Brand name", description: "Header and footer brand display" },
    { label: "Typography", description: "Heading and body font families" },
    { label: "Colors", description: "Background, text, border, and CTA colors" },
    { label: "Border radius", description: "Component corner rounding" },
  ];

  /* ---- early returns ---- */
  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Site" description="View site details." />
        <EmptyState title="No workspace selected" description="Select a workspace to view site details." />
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <PageHeader title="Site" description="Loading site details...">
          <div className="flex items-center gap-2 text-sm text-content-muted">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading...
          </div>
        </PageHeader>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatCardSkeleton /><StatCardSkeleton /><StatCardSkeleton /><StatCardSkeleton />
        </div>
      </div>
    );
  }

  if (error || !site) {
    return (
      <div className="space-y-4">
        <PageHeader title="Site" description="View site details." />
        <Callout variant="danger">{getErrorMessage(error, "Failed to load site.")}</Callout>
        <Button variant="outline" onClick={() => navigate("/workspaces/sites")}>
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to Sites
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ---- Header — slim badges ---- */}
      <PageHeader
        title={site.name}
        description={site.description || `${formatSiteFamily(site.siteFamily)} site`}
      >
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Badge tone={site.status === "published" ? "success" : "neutral"}>{site.status}</Badge>
          <Badge tone="neutral">{getThemeBindingLabel(site.themeBindingMode)}</Badge>
        </div>
      </PageHeader>

      {/* ---- Tabs — horizontal scroll on mobile ---- */}
      <Tabs value={activeTab} onValueChange={(v) => handleTabChange(v as typeof activeTab)}>
        <TabsList className="w-full overflow-x-auto sm:w-auto">
          <TabsTrigger value="overview" className="flex items-center gap-2"><LayoutGrid className="h-4 w-4" />Overview</TabsTrigger>
          <TabsTrigger value="pages" className="flex items-center gap-2"><FileText className="h-4 w-4" />Pages<Badge tone="neutral" className="ml-1">{site.pages.length}</Badge></TabsTrigger>
          <TabsTrigger value="funnels" className="flex items-center gap-2"><Funnel className="h-4 w-4" />Funnels<Badge tone="neutral" className="ml-1">{funnels.length}</Badge></TabsTrigger>
          <TabsTrigger value="products" className="flex items-center gap-2"><Package className="h-4 w-4" />Products<Badge tone="neutral" className="ml-1">{productBindings.length}</Badge></TabsTrigger>
          <TabsTrigger value="theme" className="flex items-center gap-2"><Palette className="h-4 w-4" />Theme</TabsTrigger>
          <TabsTrigger value="settings" className="flex items-center gap-2"><Settings className="h-4 w-4" />Settings</TabsTrigger>
        </TabsList>

        {/* ================================================================ */}
        {/*  OVERVIEW TAB — consolidated                                      */}
        {/* ================================================================ */}
        <TabsContent value="overview" className="space-y-4">
          {/* Key-value metadata row */}
          <div className="ds-section-card">
            <div className="ds-section-card__header">
              <div>
                <div className="text-sm font-semibold text-content">Site Details</div>
                <div className="text-xs text-content-muted">Metadata, routing, and provenance.</div>
              </div>
              <Badge tone="accent">{formatSiteFamily(site.siteFamily)}</Badge>
            </div>

            <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
              <div><dt className="text-overline">Type</dt><dd className="mt-0.5 font-medium text-content">{formatSiteType(site.siteType)}</dd></div>
              <div><dt className="text-overline">Commerce</dt><dd className="mt-0.5 font-medium text-content">{formatCommerceProvider(site.commerceProvider)}</dd></div>
              <div><dt className="text-overline">Status</dt><dd className="mt-0.5"><Badge tone={site.status === "published" ? "success" : "neutral"}>{site.status}</Badge></dd></div>
              <div><dt className="text-overline">Theme Source</dt><dd className="mt-0.5 font-medium text-content">{getThemeBindingLabel(site.themeBindingMode)}</dd></div>
              {site.routeSlug && <div><dt className="text-overline">Route Slug</dt><dd className="mt-0.5 font-medium text-content">/{site.routeSlug}</dd></div>}
              {site.primaryDomain && <div><dt className="text-overline">Domain</dt><dd className="mt-0.5 font-medium text-content">{site.primaryDomain}</dd></div>}
              <div><dt className="text-overline">Origin</dt><dd className="mt-0.5 font-medium text-content">{site.templateId ? `Template` : `Family: ${formatSiteFamily(site.siteFamily)}`}</dd></div>
              <div><dt className="text-overline">Default Product</dt><dd className="mt-0.5 font-medium text-content">{primaryProductLabel}</dd></div>
              {activeBoundProducts.length > 0 && (
                <div><dt className="text-overline">Bound Products</dt><dd className="mt-0.5 font-medium text-content">{activeBoundProducts.length <= 2 ? activeBoundProducts.map((p) => p.title).join(", ") : `${activeBoundProducts.length} products`}</dd></div>
              )}
            </dl>
          </div>

          {/* Quick Stats */}
          <div className="grid gap-4 md:grid-cols-3">
            {[
              { label: "Pages", count: site.pages.length, action: () => setActiveTab("pages"), cta: "View pages" },
              { label: "Funnels", count: funnels.length, action: () => handleTabChange("funnels"), cta: "View funnels" },
              { label: "Product Bindings", count: productBindings.length, action: () => setActiveTab("products"), cta: "View products" },
            ].map((stat) => (
              <div key={stat.label} className="ds-section-card">
                <div className="text-overline">{stat.label}</div>
                <div className="mt-1 text-2xl font-semibold text-content">{stat.count}</div>
                <div className="mt-2">
                  <Button variant="link" size="xs" className="px-0" onClick={stat.action}>{stat.cta} &rarr;</Button>
                </div>
              </div>
            ))}
          </div>

          {/* Quick Actions */}
          <div className="ds-section-card">
            <div className="text-sm font-semibold text-content">Quick Actions</div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => navigate("/workspaces/sites")}><ArrowLeft className="mr-2 h-4 w-4" />Back to Sites</Button>
              <Button variant="outline" onClick={openCreateTemplateDialog}>
                <LayoutTemplate className="mr-2 h-4 w-4" />
                Save as Template
              </Button>
              {site.entryPageId && (
                <Button onClick={() => navigate(`/workspaces/sites/${site.id}/pages/${site.entryPageId}`)}><Edit className="mr-2 h-4 w-4" />Edit Entry Page</Button>
              )}
              {entryPage && (
                <Button variant="outline" onClick={() => openPagePreview(entryPage, entryPreviewHref)} className={!entryPreviewHref ? "opacity-60" : undefined}>
                  <ExternalLink className="mr-2 h-4 w-4" />Preview Entry Page
                </Button>
              )}
            </div>
          </div>
        </TabsContent>

        {/* ================================================================ */}
        {/*  PAGES TAB                                                        */}
        {/* ================================================================ */}
        <TabsContent value="pages" className="space-y-4">
          <div className="ds-section-card">
            <div className="ds-section-card__header">
              <div><div className="text-sm font-semibold text-content">Pages</div><div className="text-xs text-content-muted">Site pages that make up this site.</div></div>
              <Badge tone="neutral">{site.pages.length} pages</Badge>
            </div>

            {site.pages.length === 0 ? (
              <EmptyState title="No pages" description="No pages found for this site." />
            ) : (
              <div className="space-y-2">
                {sortedPages.map((page) => {
                  const previewHref = pagePreviewHrefs.get(page.id) || null;
                  // Show only the most relevant badge
                  const versionBadge = page.latestDraftVersionId
                    ? <Badge tone="warning" className="text-xs">Draft</Badge>
                    : page.latestApprovedVersionId
                      ? <Badge tone="success" className="text-xs">Approved</Badge>
                      : null;

                  return (
                    <div
                      key={page.id}
                      className={cn("rounded-xl border px-4 py-3 transition-colors", "border-border bg-surface-2 hover:border-accent/40")}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-content truncate">{page.name}</span>
                            {page.isEntry && <Badge tone="accent" className="text-xs">Entry</Badge>}
                            {versionBadge}
                          </div>
                          <div className="mt-1 flex items-center gap-2 text-xs text-content-muted">
                            <span>{formatPageType(page.pageType)}</span>
                            <span>&bull;</span>
                            <span>/{page.slug}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <Button size="sm" variant="outline" onClick={() => openPagePreview(page, previewHref)}>
                            <ExternalLink className="mr-1 h-3 w-3" />Preview
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => navigate(`/workspaces/sites/${site.id}/pages/${page.id}`)}>
                            <Edit className="mr-1 h-3 w-3" />Edit
                          </Button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </TabsContent>

        {/* ================================================================ */}
        {/*  FUNNELS TAB                                                      */}
        {/* ================================================================ */}
        <TabsContent value="funnels" className="space-y-4">
          <div className="ds-section-card">
            <div className="ds-section-card__header">
              <div><div className="text-sm font-semibold text-content">Funnels</div><div className="text-xs text-content-muted">Marketing funnels attached to this site.</div></div>
              <Button size="sm" onClick={openCreateFunnelForm}><Plus className="mr-1 h-4 w-4" />New Funnel</Button>
            </div>

            {funnelsLoading ? (
              <div className="space-y-2"><RowSkeleton /><RowSkeleton /></div>
            ) : funnelsError ? (
              <Callout variant="danger" size="sm">{getErrorMessage(funnelsError, "Failed to load funnels.")}</Callout>
            ) : funnels.length === 0 ? (
              <EmptyState title="No funnels yet" description="Create a funnel to define a marketing path through your site pages." />
            ) : (
              <div className="space-y-2">
                {funnels.map((funnel) => (
                  <div key={funnel.id} className={cn("rounded-xl border px-4 py-3 transition-colors", "border-border bg-surface-2 hover:border-accent/40")}>
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-content">{funnel.name}</span>
                          <Badge tone={formatFunnelStatus(funnel.status)} className="text-xs">{funnel.status}</Badge>
                        </div>
                        <div className="mt-1 text-xs text-content-muted">{funnel.description || "No description"}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button size="sm" variant="outline" onClick={() => navigate(`/workspaces/sites/${site.id}/funnels/${funnel.id}`)}><Edit className="mr-1 h-3 w-3" />Manage</Button>
                        <Button size="sm" variant="destructive" onClick={() => handleDeleteFunnel(funnel.id)} disabled={deletingFunnelId === funnel.id}>
                          {deletingFunnelId === funnel.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Create Funnel Dialog */}
          <DialogRoot open={showCreateFunnelForm} onOpenChange={(open) => { if (!open) setShowCreateFunnelForm(false); }}>
            <DialogContent>
              <div className="space-y-1">
                <DialogTitle>Create New Funnel</DialogTitle>
                <DialogDescription>Create a marketing funnel for this site.</DialogDescription>
              </div>
              <div className="mt-4 space-y-4">
                <FormField label="Funnel Name" required>
                  <Input placeholder="e.g., Lead Magnet Funnel" value={newFunnelName} onChange={(e) => setNewFunnelName(e.target.value)} />
                </FormField>
                <FormField label="Description" helper="Optional.">
                  <Input placeholder="A brief description of this funnel" value={newFunnelDescription} onChange={(e) => setNewFunnelDescription(e.target.value)} />
                </FormField>
                <FormField label="Entry Page">
                  <Select options={pageOptions} value={newFunnelEntryPageId} onValueChange={setNewFunnelEntryPageId} />
                </FormField>
                <FormField label="Product" helper="Optional.">
                  <Select options={productOptions} value={newFunnelProductId} onValueChange={setNewFunnelProductId} />
                </FormField>
                <div className="flex items-center justify-end gap-2 pt-2">
                  <Button variant="outline" onClick={() => setShowCreateFunnelForm(false)} disabled={createFunnel.isPending}>Cancel</Button>
                  <Button onClick={handleCreateFunnel} disabled={!newFunnelName.trim() || createFunnel.isPending}>
                    {createFunnel.isPending ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Creating...</> : <><Plus className="mr-2 h-4 w-4" />Create Funnel</>}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </DialogRoot>
        </TabsContent>

        {/* ================================================================ */}
        {/*  PRODUCTS TAB                                                     */}
        {/* ================================================================ */}
        <TabsContent value="products" className="space-y-4">
          <div className="ds-section-card">
            <div className="ds-section-card__header">
              <div><div className="text-sm font-semibold text-content">Product Bindings</div><div className="text-xs text-content-muted">Bind products to site pages without leaving this site.</div></div>
              <div className="flex items-center gap-2">
                <Badge tone="neutral">{productBindings.length} bindings</Badge>
                <Button size="sm" onClick={openCreateBindingForm} disabled={productsLoading || products.length === 0}><Plus className="mr-1 h-4 w-4" />New Binding</Button>
              </div>
            </div>

            {siteUsesExplicitBindingsOnly && (
              <Callout variant="warning" size="sm" className="mb-3">
                This site has no default product. Product routing depends entirely on the explicit bindings below.
              </Callout>
            )}

            {bindingsLoading ? (
              <div className="space-y-2"><RowSkeleton /><RowSkeleton /></div>
            ) : bindingsError ? (
              <Callout variant="danger" size="sm">{getErrorMessage(bindingsError, "Failed to load product bindings.")}</Callout>
            ) : productBindings.length === 0 ? (
              <EmptyState
                title="No product bindings yet"
                description={products.length === 0
                  ? "No products available in this workspace yet. Create a product first."
                  : "Add a binding to connect a product to a specific site page."}
              />
            ) : (
              <div className="space-y-2">
                {productBindings.map((binding) => (
                  <div key={binding.id} className={cn("rounded-xl border px-4 py-3 transition-colors", "border-border bg-surface-2 hover:border-accent/40")}>
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-content">{productsById.get(binding.productId)?.title || `Product ${binding.productId.slice(0, 8)}...`}</span>
                          <Badge tone={binding.active ? "success" : "neutral"} className="text-xs">{binding.active ? "Active" : "Inactive"}</Badge>
                        </div>
                        <div className="mt-1 text-xs text-content-muted">
                          Page: {binding.page?.name || "Unknown"}{binding.page?.slug ? ` (/${binding.page.slug})` : ""} &bull; Role: {binding.pageRole}{binding.funnel?.name ? ` \u2022 Funnel: ${binding.funnel.name}` : " \u2022 Scope: site-wide"}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {binding.sitePageId && (
                          <Button size="sm" variant="outline" onClick={() => navigate(`/workspaces/sites/${site.id}/pages/${binding.sitePageId}`)}><Edit className="mr-1 h-3 w-3" />Edit Page</Button>
                        )}
                        <Button size="sm" variant="destructive" onClick={() => handleDeleteBinding(binding.id)} disabled={deletingBindingId === binding.id}>
                          {deletingBindingId === binding.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Create Binding Dialog */}
          <DialogRoot open={showCreateBindingForm} onOpenChange={(open) => { if (!open) setShowCreateBindingForm(false); }}>
            <DialogContent>
              <div className="space-y-1">
                <DialogTitle>Bind Product to Site</DialogTitle>
                <DialogDescription>Choose the product, page, and role to attach inside this site.</DialogDescription>
              </div>
              <div className="mt-4 space-y-4">
                <FormField label="Product" required>
                  <Select options={productOptions} value={selectedBindingProductId} onValueChange={setSelectedBindingProductId} disabled={productsLoading} />
                </FormField>
                <FormField label="Page" required>
                  <Select options={pageOptions} value={selectedBindingPageId} onValueChange={handleBindingPageChange} />
                </FormField>
                <FormField label="Role" required>
                  <Input placeholder="e.g., product_detail" value={bindingRole} onChange={(e) => setBindingRole(e.target.value)} />
                </FormField>
                <FormField label="Funnel Scope" helper="Use a site-wide binding for default product mapping, or scope it to a funnel when the same site needs different product flows.">
                  <Select options={funnelOptions} value={selectedBindingFunnelId} onValueChange={setSelectedBindingFunnelId} />
                </FormField>
                <div className="flex items-center justify-end gap-2 pt-2">
                  <Button variant="outline" onClick={() => setShowCreateBindingForm(false)} disabled={createBinding.isPending}>Cancel</Button>
                  <Button onClick={handleCreateBinding} disabled={createBinding.isPending || !selectedBindingProductId || !selectedBindingPageId || !bindingRole.trim()}>
                    {createBinding.isPending ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Binding...</> : <><Plus className="mr-2 h-4 w-4" />Create Binding</>}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </DialogRoot>
        </TabsContent>

        {/* ================================================================ */}
        {/*  THEME TAB (kept largely intact — already well-structured)        */}
        {/* ================================================================ */}
        <TabsContent value="theme" className="space-y-4">
          {/* Theme Source Settings */}
          <div className="ds-section-card">
            <div className="ds-section-card__header">
              <div><div className="text-sm font-semibold text-content">Site Theme</div><div className="text-xs text-content-muted">Choose how this site receives its visual identity.</div></div>
              {!isEditingTheme ? (
                <Button size="sm" variant="outline" onClick={() => setIsEditingTheme(true)}><Edit className="mr-1 h-3 w-3" />Edit</Button>
              ) : (
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={handleCancelThemeEdit} disabled={updateSite.isPending}>Cancel</Button>
                  <Button size="sm" onClick={handleSaveTheme} disabled={updateSite.isPending || (themeBindingMode === "design_system" && !selectedDesignSystemId)}>
                    {updateSite.isPending ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <Check className="mr-1 h-3 w-3" />}Save
                  </Button>
                </div>
              )}
            </div>

            <div className="space-y-4">
              {!isEditingTheme ? (
                <div className="rounded-xl border border-border bg-surface-2 px-4 py-4">
                  <div className="flex items-start gap-3">
                    <div className={cn("mt-0.5 h-2 w-2 rounded-full", site.themeBindingMode === "standalone" ? "bg-neutral-400" : site.themeBindingMode === "workspace_default" ? "bg-accent" : site.themeBindingMode === "design_system" ? "bg-success" : "bg-neutral-400")} />
                    <div className="flex-1">
                      <div className="text-sm font-semibold text-content">{getThemeBindingLabel(site.themeBindingMode)}</div>
                      <div className="mt-1 text-xs text-content-muted">{getThemeBindingDescription(site.themeBindingMode)}</div>
                      {site.themeBindingMode === "design_system" && site.designSystemId && (
                        <div className="mt-2 text-xs text-content">Design system ID: <code className="bg-surface px-1 py-0.5 rounded">{site.designSystemId}</code></div>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="space-y-2">
                    {[
                      { value: "standalone", label: "Standalone", description: "Use generic styling without brand tokens" },
                      { value: "workspace_default", label: "Workspace brand", description: "Inherit the workspace default design system" },
                      { value: "design_system", label: "Specific design system", description: "Select a design system to apply to this site" },
                    ].map((option) => (
                      <label key={option.value} className={cn("flex items-start gap-3 rounded-xl border p-3 cursor-pointer transition-colors", themeBindingMode === option.value ? "border-accent bg-accent/5" : "border-border bg-surface-2 hover:border-accent/40")}>
                        <input type="radio" name="themeBindingMode" value={option.value} checked={themeBindingMode === option.value} onChange={(e) => setThemeBindingMode(e.target.value as SiteThemeBindingMode)} className="mt-0.5" />
                        <div className="flex-1">
                          <div className="text-sm font-medium text-content">{option.label}</div>
                          <div className="text-xs text-content-muted">{option.description}</div>
                        </div>
                      </label>
                    ))}
                  </div>
                  {themeBindingMode === "design_system" && (
                    <FormField label="Design System">
                      <Select options={designSystemOptions} value={selectedDesignSystemId} onValueChange={setSelectedDesignSystemId} />
                      {designSystems.length === 0 && (
                        <Callout variant="warning" size="sm" className="mt-2" icon={<AlertCircle className="h-3 w-3" />}>
                          No design systems available. Create one in the Brand Design System page first.
                        </Callout>
                      )}
                    </FormField>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Effective Theme Summary */}
          <div className="ds-section-card">
            <div className="ds-section-card__header">
              <div><div className="text-sm font-semibold text-content">Effective Theme</div><div className="text-xs text-content-muted">What this site will actually receive based on the current theme source.</div></div>
            </div>

            <div className="space-y-3">
              {effectiveThemeMode === "standalone" ? (
                <div className="rounded-xl border border-border bg-surface-2 px-4 py-4">
                  <div className="flex items-start gap-3">
                    <div className="h-2 w-2 rounded-full bg-neutral-400 mt-1.5" />
                    <div>
                      <div className="text-sm font-medium text-content">Standalone mode</div>
                      <div className="text-xs text-content-muted mt-1">This site uses generic styling without brand-specific tokens. The storefront will display with neutral colors and default typography.</div>
                    </div>
                  </div>
                </div>
              ) : effectiveThemeMode === "workspace_default" ? (
                <div className="rounded-xl border border-border bg-surface-2 px-4 py-4">
                  <div className="flex items-start gap-3">
                    <div className="h-2 w-2 rounded-full bg-accent mt-1.5" />
                    <div className="flex-1">
                      <div className="text-sm font-medium text-content">{workspaceDefaultDesignSystem?.name || "Workspace brand"}</div>
                      <div className="text-xs text-content-muted mt-1">{workspaceDefaultDesignSystem ? "Inherits the workspace default design system. Changes to the workspace brand will automatically apply here." : "Configured to use the workspace brand, but the workspace does not currently have a default design system."}</div>
                      {workspaceDefaultDesignSystem && (
                        <div className="mt-3 grid gap-3 sm:grid-cols-2">
                          <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs text-content-muted">Brand: <span className="font-medium text-content">{effectiveThemeSummary.brandName || workspace.name}</span></div>
                          <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs text-content-muted">Logo: <span className="font-medium text-content">{effectiveThemeSummary.hasLogo ? "Yes" : "No"}</span></div>
                          <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs text-content-muted">Heading font: <span className="font-medium text-content">{effectiveThemeSummary.headingFont || "Default"}</span></div>
                          <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs text-content-muted">Body font: <span className="font-medium text-content">{effectiveThemeSummary.bodyFont || "Default"}</span></div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="rounded-xl border border-border bg-surface-2 px-4 py-4">
                  <div className="flex items-start gap-3">
                    <div className="h-2 w-2 rounded-full bg-success mt-1.5" />
                    <div className="flex-1">
                      <div className="text-sm font-medium text-content">{effectiveDesignSystem?.name || "Design system"}</div>
                      <div className="text-xs text-content-muted mt-1">{effectiveDesignSystem ? "Uses a specific design system. Changes to that design system will apply here." : "Select a design system to preview the effective theme."}</div>
                      {effectiveDesignSystem && (
                        <div className="mt-3 grid gap-3 sm:grid-cols-2">
                          <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs text-content-muted">Brand: <span className="font-medium text-content">{effectiveThemeSummary.brandName || effectiveDesignSystem.name}</span></div>
                          <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs text-content-muted">Logo: <span className="font-medium text-content">{effectiveThemeSummary.hasLogo ? "Yes" : "No"}</span></div>
                          <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs text-content-muted">Heading font: <span className="font-medium text-content">{effectiveThemeSummary.headingFont || "Default"}</span></div>
                          <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs text-content-muted">Body font: <span className="font-medium text-content">{effectiveThemeSummary.bodyFont || "Default"}</span></div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Color swatches */}
              {effectiveDesignSystem && (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {effectiveThemeSummary.keyColors.map((token) => (
                    <div key={token.label} className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                      <div className="text-overline">{token.label}</div>
                      <div className="mt-2 flex items-center gap-2 text-xs text-content">
                        <span
                          className={cn("inline-flex h-4 w-4 rounded border", token.value === "Not set" ? "border-dashed border-border" : "border-border")}
                          style={token.value !== "Not set" ? { background: token.value } : undefined}
                        />
                        <span className="truncate font-medium">{token.value}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Runtime Usage Summary */}
          <div className="ds-section-card">
            <div className="ds-section-card__header">
              <div><div className="text-sm font-semibold text-content">Theme Usage in B2C Starter</div><div className="text-xs text-content-muted">Where the current B2C starter storefront uses the site theme today.</div></div>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {themeUsageItems.map((item) => (
                <div key={item.label} className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                  <div className="text-sm font-medium text-content">{item.label}</div>
                  <div className="text-xs text-content-muted mt-1">{item.description}</div>
                </div>
              ))}
            </div>
            <Callout variant="neutral" size="sm" icon={<AlertCircle className="h-4 w-4" />} className="mt-3">
              <span className="font-medium text-content">Note:</span> Page-level design system overrides take precedence over site theme settings.
              Individual pages can still specify their own design system in the page editor.
            </Callout>
          </div>
        </TabsContent>

        {/* ================================================================ */}
        {/*  SETTINGS TAB                                                     */}
        {/* ================================================================ */}
        <TabsContent value="settings" className="space-y-4">
          <div className="ds-section-card">
            <div className="ds-section-card__header">
              <div><div className="text-sm font-semibold text-content">Site Settings</div><div className="text-xs text-content-muted">Review the live site configuration and jump to the relevant editor.</div></div>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              {/* Routing */}
              <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                <div className="text-overline">Routing</div>
                <div className="mt-3 space-y-2 text-sm text-content">
                  <div>Route slug: <span className="font-semibold">{site.routeSlug ? `/${site.routeSlug}` : "Not set"}</span></div>
                  <div>Primary domain: <span className="font-semibold">{site.primaryDomain || "Not set"}</span></div>
                  <div>Entry page: <span className="font-semibold">{sortedPages.find((p) => p.id === site.entryPageId)?.name || "Not set"}</span></div>
                </div>
                {site.entryPageId && (
                  <div className="mt-4"><Button size="sm" variant="outline" onClick={() => navigate(`/workspaces/sites/${site.id}/pages/${site.entryPageId}`)}><Edit className="mr-2 h-4 w-4" />Open Entry Page</Button></div>
                )}
              </div>

              {/* Commerce */}
              <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                <div className="text-overline">Commerce</div>
                <div className="mt-3 space-y-2 text-sm text-content">
                  <div>Provider: <span className="font-semibold">{formatCommerceProvider(site.commerceProvider)}</span></div>
                  <div>Primary product: <span className="font-semibold">{primaryProductLabel}</span></div>
                  <div>Product bindings: <span className="font-semibold">{productBindings.length}</span></div>
                  <div>Funnels: <span className="font-semibold">{funnels.length}</span></div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => setActiveTab("products")}><Package className="mr-2 h-4 w-4" />Open Products</Button>
                  <Button size="sm" variant="outline" onClick={() => handleTabChange("funnels")}><Funnel className="mr-2 h-4 w-4" />Open Funnels</Button>
                </div>
              </div>

              {/* Theme & Provenance */}
              <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                <div className="text-overline">Theme &amp; Provenance</div>
                <div className="mt-3 space-y-2 text-sm text-content">
                  <div>Theme source: <span className="font-semibold">{getThemeBindingLabel(site.themeBindingMode)}</span></div>
                  <div>Design system: <span className="font-semibold">{site.designSystemId || "None (inherited)"}</span></div>
                  <div>Site family: <span className="font-semibold">{formatSiteFamily(site.siteFamily)}</span></div>
                  <div>Site type: <span className="font-semibold">{formatSiteType(site.siteType)}</span></div>
                  <div>Origin: <span className="font-semibold">{site.templateId ? `Template ${site.templateId}` : `Family ${formatSiteFamily(site.siteFamily)}`}</span></div>
                </div>
                <div className="mt-4"><Button size="sm" variant="outline" onClick={() => setActiveTab("theme")}><Palette className="mr-2 h-4 w-4" />Open Theme</Button></div>
              </div>

              {/* Lifecycle */}
              <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                <div className="text-overline">Lifecycle</div>
                <div className="mt-3 space-y-2 text-sm text-content">
                  <div>Status: <span className="font-semibold">{site.status}</span></div>
                  <div>Created: <span className="font-semibold">{formatDateTime(site.createdAt)}</span></div>
                  <div>Updated: <span className="font-semibold">{formatDateTime(site.updatedAt)}</span></div>
                </div>
              </div>
            </div>

            {site.commerceProvider?.toLowerCase() === "medusa" && (
              <div className="mt-4"><MedusaConnectionCard clientId={workspace.id} productId={site.productId || undefined} /></div>
            )}
          </div>
        </TabsContent>
      </Tabs>

      <DialogRoot open={showCreateTemplateDialog} onOpenChange={setShowCreateTemplateDialog}>
        <DialogContent>
          <div className="space-y-1">
            <DialogTitle>Create Site Template</DialogTitle>
            <DialogDescription>
              Save this site as a reusable workspace starter.
            </DialogDescription>
          </div>

          <div className="mt-4 space-y-4">
            <FormField label="Template Name" required>
              <Input
                placeholder="Omni One Product Template"
                value={templateName}
                onChange={(event) => setTemplateName(event.target.value)}
              />
            </FormField>

            <FormField label="Description" helper="Optional summary shown in the Templates tab.">
              <Input
                placeholder="Reusable one-product store starter"
                value={templateDescription}
                onChange={(event) => setTemplateDescription(event.target.value)}
              />
            </FormField>

            <div className="flex items-center justify-end gap-2 pt-2">
              <Button
                variant="outline"
                onClick={() => setShowCreateTemplateDialog(false)}
                disabled={createTemplateFromSite.isPending}
              >
                Cancel
              </Button>
              <Button
                onClick={handleCreateTemplate}
                disabled={!templateName.trim() || createTemplateFromSite.isPending}
              >
                {createTemplateFromSite.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Creating...
                  </>
                ) : (
                  <>
                    <LayoutTemplate className="mr-2 h-4 w-4" />
                    Create Template
                  </>
                )}
              </Button>
            </div>
          </div>
        </DialogContent>
      </DialogRoot>
    </div>
  );
}
