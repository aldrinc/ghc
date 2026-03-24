import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Layers3, Plus, Loader2, Globe, ExternalLink, AlertTriangle } from "lucide-react";

import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";
import { useSites, useSiteFamilies, useCreateSite } from "@/api/sites";
import { EmptyState } from "@/components/layout/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

function formatSiteType(siteType: string | null): string {
  if (!siteType) return "Unknown";
  return siteType
    .split("_")
    .map((token) => (token ? token[0].toUpperCase() + token.slice(1) : token))
    .join(" ");
}

function formatCommerceProvider(provider: string | null): string {
  if (!provider) return "None";
  return provider.charAt(0).toUpperCase() + provider.slice(1);
}

function formatSiteFamily(family: string | null): string {
  if (!family) return "Unknown";
  return family
    .split("-")
    .map((token) => (token ? token[0].toUpperCase() + token.slice(1) : token))
    .join(" ");
}

export function SitesPage() {
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const navigate = useNavigate();
  const { data: sites = [], isLoading: sitesLoading } = useSites();
  const { data: families = [], isLoading: familiesLoading } = useSiteFamilies();
  const createSite = useCreateSite();

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [selectedFamily, setSelectedFamily] = useState<string | null>(null);
  const [siteName, setSiteName] = useState("");
  const [siteDescription, setSiteDescription] = useState("");

  const handleCreateSite = async () => {
    if (!workspace?.id || !selectedFamily || !siteName.trim() || !product?.id) return;

    try {
      const result = await createSite.mutateAsync({
        clientId: workspace.id,
        family: selectedFamily,
        name: siteName.trim(),
        description: siteDescription.trim() || undefined,
        productId: product.id,
      });
      setShowCreateForm(false);
      setSiteName("");
      setSiteDescription("");
      setSelectedFamily(null);
      navigate(`/workspaces/sites/${result.id}`);
    } catch (error) {
      console.error("Failed to create site:", error);
    }
  };

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Sites" description="Manage your ecommerce sites." />
        <EmptyState
          title="No workspace selected"
          description="Select a workspace to manage sites."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Sites"
        description="Create and manage ecommerce sites backed by the Medusa B2B starter."
      >
        <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-content-muted">
          <Badge tone="neutral">Workspace: {workspace.name}</Badge>
        </div>
      </PageHeader>

      {/* Site Families Section */}
      <section className="space-y-4">
        <div className="rounded-2xl border border-border bg-surface px-4 py-4">
          <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
            <div>
              <div className="text-sm font-semibold text-content">Site Families</div>
              <div className="text-xs text-content-muted">
                Choose a starter template to create a new site.
              </div>
            </div>
            <Badge tone="neutral">{families.length} families</Badge>
          </div>

          {familiesLoading ? (
            <div className="py-6 text-sm text-content-muted">
              <Loader2 className="mr-2 h-4 w-4 animate-spin inline" />
              Loading site families...
            </div>
          ) : (
            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              {families.map((family) => (
                <button
                  key={family.family}
                  type="button"
                  onClick={() => {
                    setSelectedFamily(family.family);
                    setSiteName(`${family.name} Site`);
                    setShowCreateForm(true);
                  }}
                  className={cn(
                    "rounded-xl border px-4 py-4 text-left transition-colors",
                    "border-border bg-surface-2 hover:border-accent/40 hover:bg-surface"
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-content-muted">
                        {formatCommerceProvider(family.commerceProvider)}
                      </div>
                      <div className="mt-1 text-base font-semibold text-content">{family.name}</div>
                    </div>
                    <Badge tone="accent">{family.pageCount} pages</Badge>
                  </div>
                  <div className="mt-2 text-sm text-content-muted">{family.description}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Existing Sites Section */}
      <section className="space-y-4">
        <div className="rounded-2xl border border-border bg-surface px-4 py-4">
          <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
            <div>
              <div className="text-sm font-semibold text-content">Your Sites</div>
              <div className="text-xs text-content-muted">
                Sites created for this workspace.
              </div>
            </div>
            <Badge tone="neutral">{sites.length} sites</Badge>
          </div>

          {sitesLoading ? (
            <div className="py-6 text-sm text-content-muted">
              <Loader2 className="mr-2 h-4 w-4 animate-spin inline" />
              Loading sites...
            </div>
          ) : sites.length === 0 ? (
            <div className="py-6 text-sm text-content-muted">
              No sites created yet. Choose a site family above to get started.
            </div>
          ) : (
            <div className="mt-4 space-y-2">
              {sites.map((site) => (
                <button
                  key={site.id}
                  type="button"
                  onClick={() => navigate(`/workspaces/sites/${site.id}`)}
                  className={cn(
                    "w-full rounded-xl border px-4 py-3 text-left transition-colors",
                    "border-border bg-surface-2 hover:border-accent/40 hover:bg-surface"
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="text-sm font-semibold text-content">{site.name}</div>
                      <div className="mt-1 text-xs text-content-muted">
                        {formatSiteFamily(site.siteFamily)} • {formatSiteType(site.siteType)}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge tone={site.status === "published" ? "success" : "neutral"}>
                        {site.status}
                      </Badge>
                      <ExternalLink className="h-4 w-4 text-content-muted" />
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Create Site Modal */}
      {showCreateForm && selectedFamily && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-2xl border border-border bg-surface p-6">
            <div className="mb-4">
              <div className="text-lg font-semibold text-content">Create New Site</div>
              <div className="mt-1 text-sm text-content-muted">
                Creating a site from the {formatSiteFamily(selectedFamily)} template.
              </div>
            </div>

            {!product && (
              <div className="mb-4 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 text-sm text-warning">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <div>
                    <div className="font-medium">Product required</div>
                    <div className="mt-1 text-xs">
                      Sites require a product context for publication. Select a product in the header to create a site.
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Site Name</label>
                <Input
                  placeholder="My Ecommerce Site"
                  value={siteName}
                  onChange={(e) => setSiteName(e.target.value)}
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Description (optional)</label>
                <Input
                  placeholder="A brief description of your site"
                  value={siteDescription}
                  onChange={(e) => setSiteDescription(e.target.value)}
                />
              </div>

              {product && (
                <div className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-xs text-content-muted">
                  <div className="font-semibold text-content">Product</div>
                  <div className="mt-1">{product.title}</div>
                </div>
              )}

              <div className="flex gap-2">
                <Button
                  onClick={handleCreateSite}
                  disabled={!siteName.trim() || !product?.id || createSite.isPending}
                  className="flex-1"
                >
                  {createSite.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Creating...
                    </>
                  ) : (
                    <>
                      <Plus className="mr-2 h-4 w-4" />
                      Create Site
                    </>
                  )}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowCreateForm(false);
                    setSelectedFamily(null);
                    setSiteName("");
                    setSiteDescription("");
                  }}
                  disabled={createSite.isPending}
                >
                  Cancel
                </Button>
              </div>

              {createSite.isError && (
                <div className="rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
                  {createSite.error instanceof Error
                    ? createSite.error.message
                    : "Failed to create site. Please try again."}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}