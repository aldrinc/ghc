import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { Globe, Edit, ExternalLink, Loader2, ArrowLeft, LayoutGrid, Settings, Funnel, FileText, Package, Palette, Plus, Trash2 } from "lucide-react";

import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProducts } from "@/api/products";
import { useSite } from "@/api/sites";
import { useSiteFunnels, useCreateSiteFunnel, useDeleteSiteFunnel } from "@/api/siteFunnels";
import { useCreateSiteProductBinding, useDeleteSiteProductBinding, useSiteProductBindings } from "@/api/siteProductBindings";
import { EmptyState } from "@/components/layout/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { buildSitePagePreviewPath } from "@/pages/workspaces/sites/sitePreviewRouting";

function formatPageType(pageType: string | null): string {
  if (!pageType) return "Unknown";
  return pageType
    .split("_")
    .map((token) => (token ? token[0].toUpperCase() + token.slice(1) : token))
    .join(" ");
}

function formatSiteFamily(family: string | null): string {
  if (!family) return "Unknown";
  return family
    .split("-")
    .map((token) => (token ? token[0].toUpperCase() + token.slice(1) : token))
    .join(" ");
}

function formatCommerceProvider(provider: string | null): string {
  if (!provider) return "None";
  return provider.charAt(0).toUpperCase() + provider.slice(1);
}

function formatSiteType(siteType: string | null): string {
  if (!siteType) return "Unknown";
  return siteType
    .split("_")
    .map((token) => (token ? token[0].toUpperCase() + token.slice(1) : token))
    .join(" ");
}

function formatFunnelStatus(status: string): "success" | "warning" | "danger" | "neutral" {
  if (status === "active") return "success";
  if (status === "draft") return "warning";
  if (status === "archived") return "danger";
  return "neutral";
}

function getErrorMessage(error: unknown, fallback: string): string {
  const candidate = error as { message?: unknown } | null;
  if (candidate && typeof candidate.message === "string") {
    return candidate.message;
  }
  return fallback;
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "Unknown";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

export function SiteDetailPage() {
  const { siteId } = useParams<{ siteId: string }>();
  const { workspace } = useWorkspace();
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
  const createFunnel = useCreateSiteFunnel(siteId || null);
  const deleteFunnel = useDeleteSiteFunnel(siteId || null);
  const createBinding = useCreateSiteProductBinding(siteId || null);
  const deleteBinding = useDeleteSiteProductBinding(siteId || null);

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
  const pagePreviewHrefs = useMemo(() => {
    const next = new Map<string, string | null>();
    if (!siteId) {
      return next;
    }

    for (const page of sortedPages) {
      next.set(
        page.id,
        buildSitePagePreviewPath(siteId, page, {
          siteFamily: site?.siteFamily,
          productHandle: productHandlesByPageId.get(page.id) || primaryProductHandle,
        }),
      );
    }

    return next;
  }, [primaryProductHandle, productHandlesByPageId, site?.siteFamily, siteId, sortedPages]);
  const entryPage = useMemo(
    () => sortedPages.find((page) => page.id === site?.entryPageId) || null,
    [site?.entryPageId, sortedPages],
  );
  const entryPreviewHref = useMemo(
    () => (entryPage ? pagePreviewHrefs.get(entryPage.id) || null : null),
    [entryPage, pagePreviewHrefs],
  );
  const productOptions = useMemo(
    () => [
      { label: productsLoading ? "Loading products..." : "Select a product", value: "" },
      ...products.map((product) => ({ label: product.title, value: product.id })),
    ],
    [products, productsLoading],
  );
  const pageOptions = useMemo(
    () => [
      { label: "Select a page", value: "" },
      ...sortedPages.map((page) => ({
        label: `${page.name} (/${page.slug})`,
        value: page.id,
      })),
    ],
    [sortedPages],
  );
  const funnelOptions = useMemo(
    () => [
      { label: "Site-wide binding", value: "" },
      ...funnels.map((funnel) => ({ label: funnel.name, value: funnel.id })),
    ],
    [funnels],
  );

  useEffect(() => {
    if (isFunnelsRoute && activeTab !== "funnels") {
      setActiveTab("funnels");
    }
    if (!isFunnelsRoute && activeTab === "funnels") {
      setActiveTab("overview");
    }
  }, [activeTab, isFunnelsRoute]);

  const handleTabChange = (nextTab: typeof activeTab) => {
    setActiveTab(nextTab);
    if (!siteId) return;
    if (nextTab === "funnels") {
      navigate(`/workspaces/sites/${siteId}/funnels`);
      return;
    }
    if (isFunnelsRoute) {
      navigate(`/workspaces/sites/${siteId}`);
    }
  };

  const openCreateFunnelForm = () => {
    setNewFunnelName("");
    setNewFunnelDescription("");
    setNewFunnelEntryPageId(site?.entryPageId || "");
    setNewFunnelProductId(site?.productId || "");
    setShowCreateFunnelForm(true);
  };

  const openCreateBindingForm = () => {
    const defaultPage = sortedPages.find((page) => page.pageType === "product_detail") ?? sortedPages[0];
    setSelectedBindingProductId(site?.productId || "");
    setSelectedBindingPageId(defaultPage?.id || "");
    setSelectedBindingFunnelId("");
    setBindingRole(defaultPage?.pageType || "product_detail");
    setShowCreateBindingForm(true);
  };

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Site" description="View site details." />
        <EmptyState
          title="No workspace selected"
          description="Select a workspace to view site details."
        />
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <PageHeader title="Site" description="View site details.">
          <div className="flex items-center gap-2 text-sm text-content-muted">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading site...
          </div>
        </PageHeader>
      </div>
    );
  }

  if (error || !site) {
    return (
      <div className="space-y-4">
        <PageHeader title="Site" description="View site details." />
        <div className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
          {getErrorMessage(error, "Failed to load site.")}
        </div>
        <Button variant="outline" onClick={() => navigate("/workspaces/sites")}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Sites
        </Button>
      </div>
    );
  }

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
      setNewFunnelName("");
      setNewFunnelDescription("");
      setNewFunnelEntryPageId("");
      setNewFunnelProductId("");
    } catch (error) {
      console.error("Failed to create funnel:", error);
    }
  };

  const handleDeleteFunnel = async (funnelId: string) => {
    setDeletingFunnelId(funnelId);
    try {
      await deleteFunnel.mutateAsync(funnelId);
    } finally {
      setDeletingFunnelId(null);
    }
  };

  const handleBindingPageChange = (pageId: string) => {
    setSelectedBindingPageId(pageId);
    const selectedPage = sortedPages.find((page) => page.id === pageId);
    setBindingRole(selectedPage?.pageType || "product_detail");
  };

  const handleCreateBinding = async () => {
    const resolvedRole = bindingRole.trim();
    if (!selectedBindingProductId || !selectedBindingPageId || !resolvedRole) return;
    try {
      await createBinding.mutateAsync({
        productId: selectedBindingProductId,
        sitePageId: selectedBindingPageId,
        siteFunnelId: selectedBindingFunnelId || undefined,
        pageRole: resolvedRole,
      });
      setShowCreateBindingForm(false);
      setSelectedBindingProductId("");
      setSelectedBindingPageId("");
      setSelectedBindingFunnelId("");
      setBindingRole("");
    } catch (error) {
      console.error("Failed to create product binding:", error);
    }
  };

  const handleDeleteBinding = async (bindingId: string) => {
    setDeletingBindingId(bindingId);
    try {
      await deleteBinding.mutateAsync(bindingId);
    } finally {
      setDeletingBindingId(null);
    }
  };

  const primaryProductLabel = site.productId
    ? productsById.get(site.productId)?.title || `${site.productId.slice(0, 8)}...`
    : "Not set";
  const openPreview = (previewHref: string | null) => {
    if (!previewHref) {
      toast.error("This page needs a concrete storefront route before it can be previewed from the workspace.");
      return;
    }
    window.open(previewHref, "_blank", "noreferrer");
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={site.name}
        description={site.description || `${formatSiteFamily(site.siteFamily)} site`}
      >
        <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-content-muted">
          <Badge tone="neutral">Workspace: {workspace.name}</Badge>
          <Badge tone={site.status === "published" ? "success" : "neutral"}>{site.status}</Badge>
        </div>
      </PageHeader>

      <Tabs value={activeTab} onValueChange={(v) => handleTabChange(v as typeof activeTab)}>
        <TabsList className="w-full sm:w-auto flex-wrap">
          <TabsTrigger value="overview" className="flex items-center gap-2">
            <LayoutGrid className="h-4 w-4" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="pages" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Pages
            <Badge tone="neutral" className="ml-1">{site.pages.length}</Badge>
          </TabsTrigger>
          <TabsTrigger value="funnels" className="flex items-center gap-2">
            <Funnel className="h-4 w-4" />
            Funnels
            <Badge tone="neutral" className="ml-1">{funnels.length}</Badge>
          </TabsTrigger>
          <TabsTrigger value="products" className="flex items-center gap-2">
            <Package className="h-4 w-4" />
            Products
            <Badge tone="neutral" className="ml-1">{productBindings.length}</Badge>
          </TabsTrigger>
          <TabsTrigger value="theme" className="flex items-center gap-2">
            <Palette className="h-4 w-4" />
            Theme
          </TabsTrigger>
          <TabsTrigger value="settings" className="flex items-center gap-2">
            <Settings className="h-4 w-4" />
            Settings
          </TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-4">
          {/* Site Metadata */}
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
              <div>
                <div className="text-sm font-semibold text-content">Site Information</div>
                <div className="text-xs text-content-muted">
                  Metadata and configuration for this site.
                </div>
              </div>
              <Badge tone="accent">{formatSiteFamily(site.siteFamily)}</Badge>
            </div>

            <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                  Type
                </div>
                <div className="mt-1 text-sm font-semibold text-content">
                  {formatSiteType(site.siteType)}
                </div>
              </div>

              <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                  Family
                </div>
                <div className="mt-1 text-sm font-semibold text-content">
                  {formatSiteFamily(site.siteFamily)}
                </div>
              </div>

              <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                  Commerce Provider
                </div>
                <div className="mt-1 text-sm font-semibold text-content">
                  {formatCommerceProvider(site.commerceProvider)}
                </div>
              </div>

              <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                  Status
                </div>
                <div className="mt-1">
                  <Badge tone={site.status === "published" ? "success" : "neutral"}>
                    {site.status}
                  </Badge>
                </div>
              </div>
            </div>

            {/* Design System Inheritance */}
            <div className="mt-4 rounded-xl border border-border bg-surface-2 px-4 py-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                Design System
              </div>
              <div className="mt-1 text-sm text-content">
                {site.designSystemId ? (
                  <span className="flex items-center gap-2">
                    <span className="font-semibold">Custom override</span>
                    <span className="text-content-muted">({site.designSystemId})</span>
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <span className="font-semibold">Workspace default</span>
                    <span className="text-content-muted">(inherited from brand settings)</span>
                  </span>
                )}
              </div>
            </div>

            {/* Provenance */}
            <div className="mt-4 rounded-xl border border-border bg-surface-2 px-4 py-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                Provenance
              </div>
              <div className="mt-1 text-sm text-content">
                {site.templateId ? (
                  <span>Created from template: <span className="font-semibold">{site.templateId}</span></span>
                ) : (
                  <span>Created from site family: <span className="font-semibold">{formatSiteFamily(site.siteFamily)}</span></span>
                )}
              </div>
            </div>

            {/* Route Info */}
            {(site.routeSlug || site.primaryDomain) && (
              <div className="mt-4 rounded-xl border border-border bg-surface-2 px-4 py-3">
                <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                  Routing
                </div>
                <div className="mt-1 space-y-1 text-sm text-content">
                  {site.routeSlug && (
                    <div>Route slug: <span className="font-semibold">/{site.routeSlug}</span></div>
                  )}
                  {site.primaryDomain && (
                    <div>Domain: <span className="font-semibold">{site.primaryDomain}</span></div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Quick Stats */}
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-2xl border border-border bg-surface px-4 py-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                Pages
              </div>
              <div className="mt-1 text-2xl font-semibold text-content">{site.pages.length}</div>
              <div className="mt-2">
                <Button variant="link" size="xs" className="px-0" onClick={() => setActiveTab("pages")}>
                  View pages →
                </Button>
              </div>
            </div>
            <div className="rounded-2xl border border-border bg-surface px-4 py-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                Funnels
              </div>
              <div className="mt-1 text-2xl font-semibold text-content">{funnels.length}</div>
              <div className="mt-2">
                <Button variant="link" size="xs" className="px-0" onClick={() => handleTabChange("funnels")}>
                  View funnels →
                </Button>
              </div>
            </div>
            <div className="rounded-2xl border border-border bg-surface px-4 py-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                Product Bindings
              </div>
              <div className="mt-1 text-2xl font-semibold text-content">{productBindings.length}</div>
              <div className="mt-2">
                <Button variant="link" size="xs" className="px-0" onClick={() => setActiveTab("products")}>
                  View products →
                </Button>
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="text-sm font-semibold text-content">Quick Actions</div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                variant="outline"
                onClick={() => navigate("/workspaces/sites")}
              >
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back to Sites
              </Button>
              {site.entryPageId && (
                <Button
                  onClick={() =>
                    navigate(`/workspaces/sites/${site.id}/pages/${site.entryPageId}`)
                  }
                >
                  <Edit className="mr-2 h-4 w-4" />
                  Edit Entry Page
                </Button>
              )}
              {entryPreviewHref ? (
                <Button variant="outline" onClick={() => openPreview(entryPreviewHref)}>
                  <ExternalLink className="mr-2 h-4 w-4" />
                  Preview Entry Page
                </Button>
              ) : null}
            </div>
          </div>
        </TabsContent>

        {/* Pages Tab */}
        <TabsContent value="pages" className="space-y-4">
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
              <div>
                <div className="text-sm font-semibold text-content">Pages</div>
                <div className="text-xs text-content-muted">
                  Site pages that make up this site.
                </div>
              </div>
              <Badge tone="neutral">{site.pages.length} pages</Badge>
            </div>

            {site.pages.length === 0 ? (
              <div className="py-6 text-sm text-content-muted">
                No pages found for this site.
              </div>
            ) : (
              <div className="mt-4 space-y-2">
                {sortedPages.map((page) => {
                  const previewHref = pagePreviewHrefs.get(page.id) || null;

                  return (
                    <div
                      key={page.id}
                      className={cn(
                        "rounded-xl border px-4 py-3 transition-colors",
                        "border-border bg-surface-2 hover:border-accent/40"
                      )}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-content">{page.name}</span>
                            {page.isEntry && (
                              <Badge tone="accent" className="text-xs">
                                Entry
                              </Badge>
                            )}
                          </div>
                          <div className="mt-1 flex items-center gap-3 text-xs text-content-muted">
                            <span>{formatPageType(page.pageType)}</span>
                            <span>•</span>
                            <span>/{page.slug}</span>
                            {page.templateId && (
                              <>
                                <span>•</span>
                                <span>Template: {page.templateId}</span>
                              </>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => openPreview(previewHref)}
                          >
                            <ExternalLink className="mr-1 h-3 w-3" />
                            Preview
                          </Button>
                          {page.latestDraftVersionId && (
                            <Badge tone="warning" className="text-xs">
                              Draft
                            </Badge>
                          )}
                          {page.latestApprovedVersionId && (
                            <Badge tone="success" className="text-xs">
                              Approved
                            </Badge>
                          )}
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              navigate(`/workspaces/sites/${site.id}/pages/${page.id}`)
                            }
                          >
                            <Edit className="mr-1 h-3 w-3" />
                            Edit
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

        {/* Funnels Tab */}
        <TabsContent value="funnels" className="space-y-4">
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
              <div>
                <div className="text-sm font-semibold text-content">Funnels</div>
                <div className="text-xs text-content-muted">
                  Marketing funnels attached to this site.
                </div>
              </div>
              <Button size="sm" onClick={openCreateFunnelForm}>
                <Plus className="mr-1 h-4 w-4" />
                New Funnel
              </Button>
            </div>

            {funnelsLoading ? (
              <div className="py-6 text-sm text-content-muted">
                <Loader2 className="mr-2 h-4 w-4 animate-spin inline" />
                Loading funnels...
              </div>
            ) : funnelsError ? (
              <div className="py-6 text-sm text-danger">
                {getErrorMessage(funnelsError, "Failed to load funnels for this site.")}
              </div>
            ) : funnels.length === 0 ? (
              <div className="py-6 text-sm text-content-muted">
                No funnels yet. Create a funnel to define a marketing path through your site pages.
              </div>
            ) : (
              <div className="mt-4 space-y-2">
                {funnels.map((funnel) => (
                  <div
                    key={funnel.id}
                    className={cn(
                      "rounded-xl border px-4 py-3 transition-colors",
                      "border-border bg-surface-2 hover:border-accent/40"
                    )}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-content">{funnel.name}</span>
                          <Badge tone={formatFunnelStatus(funnel.status)} className="text-xs">
                            {funnel.status}
                          </Badge>
                        </div>
                        <div className="mt-1 text-xs text-content-muted">
                          {funnel.description || "No description"}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => navigate(`/workspaces/sites/${site.id}/funnels/${funnel.id}`)}
                        >
                          <Edit className="mr-1 h-3 w-3" />
                          Manage
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => handleDeleteFunnel(funnel.id)}
                          disabled={deletingFunnelId === funnel.id}
                        >
                          {deletingFunnelId === funnel.id ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Trash2 className="h-3 w-3" />
                          )}
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Create Funnel Modal */}
          {showCreateFunnelForm && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
              <div className="w-full max-w-md rounded-2xl border border-border bg-surface p-6">
                <div className="mb-4">
                  <div className="text-lg font-semibold text-content">Create New Funnel</div>
                  <div className="mt-1 text-sm text-content-muted">
                    Create a marketing funnel for this site.
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-content">Funnel Name</label>
                    <Input
                      placeholder="e.g., Lead Magnet Funnel"
                      value={newFunnelName}
                      onChange={(e) => setNewFunnelName(e.target.value)}
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-content">Description (optional)</label>
                    <Input
                      placeholder="A brief description of this funnel"
                      value={newFunnelDescription}
                      onChange={(e) => setNewFunnelDescription(e.target.value)}
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-content">Entry Page</label>
                    <Select
                      options={pageOptions}
                      value={newFunnelEntryPageId}
                      onValueChange={setNewFunnelEntryPageId}
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-content">Product (optional)</label>
                    <Select
                      options={productOptions}
                      value={newFunnelProductId}
                      onValueChange={setNewFunnelProductId}
                    />
                  </div>

                  <div className="flex gap-2">
                    <Button
                      onClick={handleCreateFunnel}
                      disabled={!newFunnelName.trim() || createFunnel.isPending}
                      className="flex-1"
                    >
                      {createFunnel.isPending ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Creating...
                        </>
                      ) : (
                        <>
                          <Plus className="mr-2 h-4 w-4" />
                          Create Funnel
                        </>
                      )}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => {
                        setShowCreateFunnelForm(false);
                        setNewFunnelName("");
                        setNewFunnelDescription("");
                        setNewFunnelEntryPageId("");
                        setNewFunnelProductId("");
                      }}
                      disabled={createFunnel.isPending}
                    >
                      Cancel
                    </Button>
                  </div>

                  {createFunnel.isError && (
                    <div className="rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
                      {getErrorMessage(createFunnel.error, "Failed to create funnel. Please try again.")}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </TabsContent>

        {/* Products Tab */}
        <TabsContent value="products" className="space-y-4">
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
              <div>
                <div className="text-sm font-semibold text-content">Product Bindings</div>
                <div className="text-xs text-content-muted">
                  Bind products to site pages without leaving this site.
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Badge tone="neutral">{productBindings.length} bindings</Badge>
                <Button size="sm" onClick={openCreateBindingForm} disabled={productsLoading || products.length === 0}>
                  <Plus className="mr-1 h-4 w-4" />
                  New Binding
                </Button>
              </div>
            </div>

            {bindingsLoading ? (
              <div className="py-6 text-sm text-content-muted">
                <Loader2 className="mr-2 h-4 w-4 animate-spin inline" />
                Loading product bindings...
              </div>
            ) : bindingsError ? (
              <div className="py-6 text-sm text-danger">
                {getErrorMessage(bindingsError, "Failed to load product bindings for this site.")}
              </div>
            ) : productBindings.length === 0 ? (
              <div className="py-6 text-sm text-content-muted">
                {products.length === 0
                  ? "No products available in this workspace yet. Create a product first, then bind it here."
                  : "No product bindings yet. Add one here to connect a product to a specific site page."}
              </div>
            ) : (
              <div className="mt-4 space-y-2">
                {productBindings.map((binding) => (
                  <div
                    key={binding.id}
                    className={cn(
                      "rounded-xl border px-4 py-3 transition-colors",
                      "border-border bg-surface-2 hover:border-accent/40"
                    )}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-content">
                            {productsById.get(binding.productId)?.title || `Product ${binding.productId.slice(0, 8)}...`}
                          </span>
                          <Badge tone={binding.active ? "success" : "neutral"} className="text-xs">
                            {binding.active ? "Active" : "Inactive"}
                          </Badge>
                        </div>
                        <div className="mt-1 text-xs text-content-muted">
                          Page: {binding.page?.name || "Unknown page"}
                          {binding.page?.slug ? ` (/${binding.page.slug})` : ""}
                          {" • "}
                          Role: {binding.pageRole}
                          {binding.funnel?.name ? ` • Funnel: ${binding.funnel.name}` : " • Scope: site-wide"}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {binding.sitePageId ? (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => navigate(`/workspaces/sites/${site.id}/pages/${binding.sitePageId}`)}
                          >
                            <Edit className="mr-1 h-3 w-3" />
                            Edit Page
                          </Button>
                        ) : null}
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => handleDeleteBinding(binding.id)}
                          disabled={deletingBindingId === binding.id}
                        >
                          {deletingBindingId === binding.id ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Trash2 className="h-3 w-3" />
                          )}
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {showCreateBindingForm && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
              <div className="w-full max-w-md rounded-2xl border border-border bg-surface p-6">
                <div className="mb-4">
                  <div className="text-lg font-semibold text-content">Bind Product to Site</div>
                  <div className="mt-1 text-sm text-content-muted">
                    Choose the product, page, and role to attach inside this site.
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-content">Product</label>
                    <Select
                      options={productOptions}
                      value={selectedBindingProductId}
                      onValueChange={setSelectedBindingProductId}
                      disabled={productsLoading}
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-content">Page</label>
                    <Select
                      options={pageOptions}
                      value={selectedBindingPageId}
                      onValueChange={handleBindingPageChange}
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-content">Role</label>
                    <Input
                      placeholder="e.g., product_detail"
                      value={bindingRole}
                      onChange={(e) => setBindingRole(e.target.value)}
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-content">Funnel Scope (optional)</label>
                    <Select
                      options={funnelOptions}
                      value={selectedBindingFunnelId}
                      onValueChange={setSelectedBindingFunnelId}
                    />
                  </div>

                  <div className="rounded-xl border border-border bg-surface-2 px-3 py-2 text-xs text-content-muted">
                    Use a site-wide binding for default product mapping, or scope it to a funnel when the same site
                    needs different product flows.
                  </div>

                  <div className="flex gap-2">
                    <Button
                      onClick={handleCreateBinding}
                      disabled={
                        createBinding.isPending ||
                        !selectedBindingProductId ||
                        !selectedBindingPageId ||
                        !bindingRole.trim()
                      }
                      className="flex-1"
                    >
                      {createBinding.isPending ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Binding...
                        </>
                      ) : (
                        <>
                          <Plus className="mr-2 h-4 w-4" />
                          Create Binding
                        </>
                      )}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => {
                        setShowCreateBindingForm(false);
                        setSelectedBindingProductId("");
                        setSelectedBindingPageId("");
                        setSelectedBindingFunnelId("");
                        setBindingRole("");
                      }}
                      disabled={createBinding.isPending}
                    >
                      Cancel
                    </Button>
                  </div>

                  {createBinding.isError && (
                    <div className="rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
                      {getErrorMessage(createBinding.error, "Failed to create product binding. Please try again.")}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </TabsContent>

        {/* Theme Tab */}
        <TabsContent value="theme" className="space-y-4">
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
              <div>
                <div className="text-sm font-semibold text-content">Site Theme</div>
                <div className="text-xs text-content-muted">
                  Design system and visual settings for this site.
                </div>
              </div>
            </div>
            <div className="py-8 text-center">
              <div className="text-sm text-content-muted">
                Theme management coming soon. This site currently inherits from the workspace design system.
              </div>
              {site.designSystemId && (
                <div className="mt-4 text-sm text-content">
                  Custom design system: <span className="font-semibold">{site.designSystemId}</span>
                </div>
              )}
            </div>
          </div>
        </TabsContent>

        {/* Settings Tab */}
        <TabsContent value="settings" className="space-y-4">
          <div className="rounded-2xl border border-border bg-surface px-4 py-4">
            <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
              <div>
                <div className="text-sm font-semibold text-content">Site Settings</div>
                <div className="text-xs text-content-muted">
                  Review the live site configuration and jump to the relevant editor.
                </div>
              </div>
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                  Routing
                </div>
                <div className="mt-3 space-y-2 text-sm text-content">
                  <div>
                    Route slug:{" "}
                    <span className="font-semibold">{site.routeSlug ? `/${site.routeSlug}` : "Not set"}</span>
                  </div>
                  <div>
                    Primary domain:{" "}
                    <span className="font-semibold">{site.primaryDomain || "Not set"}</span>
                  </div>
                  <div>
                    Entry page:{" "}
                    <span className="font-semibold">
                      {sortedPages.find((page) => page.id === site.entryPageId)?.name || "Not set"}
                    </span>
                  </div>
                </div>
                {site.entryPageId ? (
                  <div className="mt-4">
                    <Button size="sm" variant="outline" onClick={() => navigate(`/workspaces/sites/${site.id}/pages/${site.entryPageId}`)}>
                      <Edit className="mr-2 h-4 w-4" />
                      Open Entry Page
                    </Button>
                  </div>
                ) : null}
              </div>

              <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                  Commerce
                </div>
                <div className="mt-3 space-y-2 text-sm text-content">
                  <div>
                    Provider: <span className="font-semibold">{formatCommerceProvider(site.commerceProvider)}</span>
                  </div>
                  <div>
                    Primary product: <span className="font-semibold">{primaryProductLabel}</span>
                  </div>
                  <div>
                    Product bindings: <span className="font-semibold">{productBindings.length}</span>
                  </div>
                  <div>
                    Funnels: <span className="font-semibold">{funnels.length}</span>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => setActiveTab("products")}>
                    <Package className="mr-2 h-4 w-4" />
                    Open Products
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => handleTabChange("funnels")}>
                    <Funnel className="mr-2 h-4 w-4" />
                    Open Funnels
                  </Button>
                </div>
              </div>

              <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                  Theme & Provenance
                </div>
                <div className="mt-3 space-y-2 text-sm text-content">
                  <div>
                    Design system:{" "}
                    <span className="font-semibold">{site.designSystemId || "Workspace default"}</span>
                  </div>
                  <div>
                    Site family: <span className="font-semibold">{formatSiteFamily(site.siteFamily)}</span>
                  </div>
                  <div>
                    Site type: <span className="font-semibold">{formatSiteType(site.siteType)}</span>
                  </div>
                  <div>
                    Origin:{" "}
                    <span className="font-semibold">
                      {site.templateId ? `Template ${site.templateId}` : `Family ${formatSiteFamily(site.siteFamily)}`}
                    </span>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-border bg-surface-2 px-4 py-3">
                <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                  Lifecycle
                </div>
                <div className="mt-3 space-y-2 text-sm text-content">
                  <div>
                    Status: <span className="font-semibold">{site.status}</span>
                  </div>
                  <div>
                    Created: <span className="font-semibold">{formatDateTime(site.createdAt)}</span>
                  </div>
                  <div>
                    Updated: <span className="font-semibold">{formatDateTime(site.updatedAt)}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
