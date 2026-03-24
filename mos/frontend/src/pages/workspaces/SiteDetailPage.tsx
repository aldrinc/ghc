import { useParams, useNavigate } from "react-router-dom";
import { Globe, Edit, ExternalLink, Loader2, Layers3, ArrowLeft } from "lucide-react";

import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useSite } from "@/api/sites";
import { EmptyState } from "@/components/layout/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

export function SiteDetailPage() {
  const { siteId } = useParams<{ siteId: string }>();
  const { workspace } = useWorkspace();
  const navigate = useNavigate();
  const { data: site, isLoading, error } = useSite(siteId || null);

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

      {/* Site Metadata */}
      <section className="space-y-4">
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
        </div>
      </section>

      {/* Pages */}
      <section className="space-y-4">
        <div className="rounded-2xl border border-border bg-surface px-4 py-4">
          <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
            <div>
              <div className="text-sm font-semibold text-content">Pages</div>
              <div className="text-xs text-content-muted">
                Site pages generated from the family blueprint.
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
                            navigate(`/research/funnels/${site.id}/pages/${page.id}`)
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
      </section>

      {/* Actions */}
      <section className="space-y-4">
        <div className="rounded-2xl border border-border bg-surface px-4 py-4">
          <div className="text-sm font-semibold text-content">Actions</div>
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
                  navigate(`/research/funnels/${site.id}/pages/${site.entryPageId}`)
                }
              >
                <Edit className="mr-2 h-4 w-4" />
                Edit Entry Page
              </Button>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}