import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { Globe, Edit, ExternalLink, Loader2, ArrowLeft, LayoutGrid, Settings, Funnel, FileText, Package, Palette, Plus, Trash2 } from "lucide-react";

import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useSite } from "@/api/sites";
import { useSiteFunnels, useCreateSiteFunnel, useDeleteSiteFunnel } from "@/api/siteFunnels";
import { useSiteProductBindings } from "@/api/siteProductBindings";
import { EmptyState } from "@/components/layout/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

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

export function SiteDetailPage() {
  const { siteId } = useParams<{ siteId: string }>();
  const { workspace } = useWorkspace();
  const location = useLocation();
  const navigate = useNavigate();
  const { data: site, isLoading, error } = useSite(siteId || null);
  const { data: funnels = [], isLoading: funnelsLoading } = useSiteFunnels(siteId || null);
  const { data: productBindings = [], isLoading: bindingsLoading } = useSiteProductBindings(siteId || null);
  const createFunnel = useCreateSiteFunnel(siteId || null);
  const deleteFunnel = useDeleteSiteFunnel(siteId || null);

  const isFunnelsRoute = useMemo(() => location.pathname.includes("/funnels"), [location.pathname]);
  const [activeTab, setActiveTab] = useState<"overview" | "pages" | "funnels" | "products" | "theme" | "settings">(
    isFunnelsRoute ? "funnels" : "overview"
  );
  const [showCreateFunnelForm, setShowCreateFunnelForm] = useState(false);
  const [newFunnelName, setNewFunnelName] = useState("");
  const [newFunnelDescription, setNewFunnelDescription] = useState("");
  const [deletingFunnelId, setDeletingFunnelId] = useState<string | null>(null);

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
          {error instanceof Error ? error.message : "Failed to load site."}
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
      });
      setShowCreateFunnelForm(false);
      setNewFunnelName("");
      setNewFunnelDescription("");
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
                <Button variant="link" size="xs" className="px-0" onClick={() => setActiveTab("funnels")}>
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
                {[...site.pages]
                  .sort((a, b) => a.ordering - b.ordering)
                  .map((page) => (
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
                  ))}
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
              <Button size="sm" onClick={() => setShowCreateFunnelForm(true)}>
                <Plus className="mr-1 h-4 w-4" />
                New Funnel
              </Button>
            </div>

            {funnelsLoading ? (
              <div className="py-6 text-sm text-content-muted">
                <Loader2 className="mr-2 h-4 w-4 animate-spin inline" />
                Loading funnels...
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
                      }}
                      disabled={createFunnel.isPending}
                    >
                      Cancel
                    </Button>
                  </div>

                  {createFunnel.isError && (
                    <div className="rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
                      {createFunnel.error instanceof Error
                        ? createFunnel.error.message
                        : "Failed to create funnel. Please try again."}
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
                  Products with dedicated page assignments in this site.
                </div>
              </div>
              <Badge tone="neutral">{productBindings.length} bindings</Badge>
            </div>

            {bindingsLoading ? (
              <div className="py-6 text-sm text-content-muted">
                <Loader2 className="mr-2 h-4 w-4 animate-spin inline" />
                Loading product bindings...
              </div>
            ) : productBindings.length === 0 ? (
              <div className="py-6 text-sm text-content-muted">
                No product bindings yet. Products can be assigned to specific pages from the product detail page.
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
                            Product: {binding.productId.slice(0, 8)}...
                          </span>
                          <Badge tone={binding.active ? "success" : "neutral"} className="text-xs">
                            {binding.active ? "Active" : "Inactive"}
                          </Badge>
                        </div>
                        <div className="mt-1 text-xs text-content-muted">
                          Page: {binding.page.name} (/{binding.page.slug}) • Role: {binding.pageRole}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => navigate(`/workspaces/sites/${site.id}/pages/${binding.sitePageId}`)}
                        >
                          <Edit className="mr-1 h-3 w-3" />
                          Edit Page
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
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
                  Configure site-level settings.
                </div>
              </div>
            </div>
            <div className="py-8 text-center">
              <div className="text-sm text-content-muted">
                Site settings management coming soon.
              </div>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
