import { useMemo } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLatestArtifact } from "@/api/artifacts";
import { useClientSwipes } from "@/api/swipes";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";

function parseAdsContext(raw: unknown): any | null {
  if (!raw) return null;
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (typeof raw === "object") return raw;
  return null;
}

export function CompetitorsPage() {
  const { workspace } = useWorkspace();
  const { latest: canonArtifact, isLoading } = useLatestArtifact({
    clientId: workspace?.id,
    type: "client_canon",
  });
  const { data: swipes = [], isLoading: swipesLoading } = useClientSwipes(workspace?.id);

  const adsContext = useMemo(() => {
    const rawResearch = (canonArtifact?.data as any)?.precanon_research || (canonArtifact?.data as any)?.precanonResearch;
    return parseAdsContext(rawResearch?.ads_context || rawResearch?.adsContext);
  }, [canonArtifact?.data]);

  const brands = (adsContext?.brands as any[]) || [];
  const crossBrand = adsContext?.cross_brand;

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Competitors" description="Select a workspace to view competitive insights." />
        <div className="ds-card ds-card--md ds-card--empty text-center text-sm">
          Choose a workspace from the sidebar.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Competitors"
        description="Competitor signal and ad ingestion summaries captured during onboarding."
      />

      {isLoading ? (
        <div className="ds-card ds-card--md text-sm text-content-muted shadow-none">Loading competitors…</div>
      ) : (
        <>
          {crossBrand ? (
            <div className="ds-card ds-card--md p-0 shadow-none">
              <div className="border-b border-border px-4 py-3">
                <div className="text-sm font-semibold text-content">Cross-brand trends</div>
                <div className="text-xs text-content-muted">Top destinations and CTA distribution across ingested ads.</div>
              </div>
              <div className="grid gap-4 p-4 md:grid-cols-2 text-sm">
                <div className="ds-card ds-card--sm bg-surface-2">
                  <div className="font-semibold text-content">Top destination domains</div>
                  <ul className="mt-2 space-y-1 text-xs text-content-muted">
                    {(crossBrand.top_destination_domains || []).map((entry: [string, number]) => (
                      <li key={entry[0]} className="flex items-center justify-between">
                        <span>{entry[0]}</span>
                        <span className="font-semibold text-content">{entry[1]}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="ds-card ds-card--sm bg-surface-2">
                  <div className="font-semibold text-content">CTA distribution</div>
                  <ul className="mt-2 space-y-1 text-xs text-content-muted">
                    {(crossBrand.cta_distribution || []).map((entry: [string, number]) => (
                      <li key={entry[0]} className="flex items-center justify-between">
                        <span>{entry[0]}</span>
                        <span className="font-semibold text-content">{entry[1]}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          ) : null}

          {brands.length ? (
            <div className="ds-card ds-card--md p-0 shadow-none">
              <div className="border-b border-border px-4 py-3">
                <div className="text-sm font-semibold text-content">Brands and ad footprint</div>
                <div className="text-xs text-content-muted">Pulled from ads ingestion during onboarding.</div>
              </div>
              <div className="overflow-x-auto">
                <Table variant="ghost">
                  <TableHeader>
                    <TableRow>
                      <TableHeadCell>Brand</TableHeadCell>
                      <TableHeadCell>Ad count</TableHeadCell>
                      <TableHeadCell>Active share</TableHeadCell>
                      <TableHeadCell>Top domains</TableHeadCell>
                      <TableHeadCell>Top CTAs</TableHeadCell>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {brands.map((brand: any) => (
                      <TableRow key={brand.brand_id}>
                        <TableCell className="font-semibold text-content">
                          {brand.brand_name || brand.brand_id}
                        </TableCell>
                        <TableCell className="text-xs text-content-muted">{brand.ad_count}</TableCell>
                        <TableCell className="text-xs text-content-muted">
                          {Math.round((brand.active_share || 0) * 100)}%
                        </TableCell>
                        <TableCell className="text-xs text-content-muted">
                          {(brand.top_destination_domains || []).map((d: [string, number]) => `${d[0]} (${d[1]})`).join(", ") || "—"}
                        </TableCell>
                        <TableCell className="text-xs text-content-muted">
                          {(brand.top_cta_types || []).map((d: [string, number]) => `${d[0]} (${d[1]})`).join(", ") || "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          ) : (
            <div className="ds-card ds-card--md ds-card--empty text-sm">
              No ads context found yet. Run onboarding to ingest competitor ads.
            </div>
          )}
        </>
      )}

      <div className="ds-card ds-card--md p-0">
        <div className="border-b border-border px-4 py-3">
          <div className="text-sm font-semibold text-content">Client swipes</div>
          <div className="text-xs text-content-muted">Saved competitive examples for this workspace.</div>
        </div>
        {swipesLoading ? (
          <div className="p-4 text-sm text-content-muted">Loading swipes…</div>
        ) : swipes.length ? (
          <div className="divide-y divide-border">
            {swipes.map((swipe) => (
              <div key={swipe.id} className="px-4 py-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold text-content">
                    {swipe.custom_title || swipe.custom_body || "Swipe"}
                  </div>
                  <div className="text-xs text-content-muted font-mono">{swipe.id.slice(0, 6)}…</div>
                </div>
                <div className="mt-1 text-xs text-content-muted">
                  {swipe.custom_channel || swipe.custom_format || swipe.company_swipe_id || "Channel not set"}
                </div>
                {swipe.tags?.length ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {swipe.tags.map((tag) => (
                      <span
                        key={tag}
                        className="rounded-full bg-surface-2 px-2 py-1 text-[11px] font-medium text-content-muted"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <div className="p-4 text-sm text-content-muted">No swipes saved for this workspace yet.</div>
        )}
      </div>
    </div>
  );
}
