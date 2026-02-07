import { useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { useExploreApi, type ExploreBrand } from "@/api/explore";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { channelDisplayName } from "@/lib/channels";
import { AdsIngestionRetryCallout } from "@/components/ads/AdsIngestionRetryCallout";

const sortOptions = [
  { value: "last_seen", label: "Last seen" },
  { value: "ad_count", label: "Ad count" },
  { value: "active", label: "Active ads" },
  { value: "name", label: "Name" },
];

function formatDate(value?: string | null) {
  if (!value) return "—";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return "—";
  return dt.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function ExploreBrandsPage() {
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const { listBrands, hideBrand, unhideBrand } = useExploreApi();

  const [query, setQuery] = useState("");
  const [includeHidden, setIncludeHidden] = useState(false);
  const [sort, setSort] = useState("last_seen");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");
  const [scope, setScope] = useState<"workspace" | "global">(
    workspace && product ? "workspace" : "global"
  );

  const [brands, setBrands] = useState<ExploreBrand[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatingBrandId, setUpdatingBrandId] = useState<string | null>(null);

  useEffect(() => {
    if ((!workspace || !product) && scope === "workspace") {
      setScope("global");
    }
  }, [scope, workspace, product]);

  const scopedClientId = scope === "workspace" ? workspace?.id : undefined;
  const scopedProductId = scope === "workspace" ? product?.id : undefined;

  const loadBrands = useCallback(
    async (opts?: { cancelRef?: { cancelled: boolean }; silent?: boolean }) => {
      const { cancelRef, silent } = opts || {};
      if (!silent) {
        setLoading(true);
      }
      try {
        const resp = await listBrands({
          q: query || undefined,
          clientId: scopedClientId,
          productId: scopedProductId,
          includeHidden,
          sort,
          direction,
        });
        if (cancelRef?.cancelled) return;
        const normalized = resp?.items ?? [];
        setBrands(normalized);
        setCount(resp?.count ?? normalized.length);
        setError(null);
      } catch (err: any) {
        if (cancelRef?.cancelled) return;
        setBrands([]);
        setCount(0);
        setError(err?.message || "Failed to load brands");
      } finally {
        if (!silent && !cancelRef?.cancelled) {
          setLoading(false);
        }
      }
    },
    [direction, includeHidden, listBrands, query, scopedClientId, scopedProductId, sort],
  );

  useEffect(() => {
    const cancelRef = { cancelled: false };
    loadBrands({ cancelRef });
    return () => {
      cancelRef.cancelled = true;
    };
  }, [loadBrands]);

  const filtersActive = useMemo(
    () => Boolean(query || includeHidden || sort !== "last_seen" || direction !== "desc" || scope === "global"),
    [direction, includeHidden, query, scope, sort],
  );

  const resetFilters = () => {
    setQuery("");
    setIncludeHidden(false);
    setSort("last_seen");
    setDirection("desc");
    setScope(workspace && product ? "workspace" : "global");
  };

  const toggleVisibility = useCallback(
    async (brand: ExploreBrand) => {
      setUpdatingBrandId(brand.brand_id);
      try {
        if (brand.hidden) {
          await unhideBrand(brand.brand_id);
        } else {
          await hideBrand(brand.brand_id);
        }
        await loadBrands({ silent: true });
      } catch (err: any) {
        setError(err?.message || "Failed to update brand");
      } finally {
        setUpdatingBrandId(null);
      }
    },
    [hideBrand, loadBrands, unhideBrand],
  );

  const sortLabel = sortOptions.find((opt) => opt.value === sort)?.label || "Last seen";

  return (
    <div className="space-y-4">
      <PageHeader
        title="Explore Brands"
        description="Org-wide brand inventory with ad counts, channels, and visibility controls."
      />
      {scope === "workspace" ? (
        <AdsIngestionRetryCallout clientId={workspace?.id} productId={product?.id} />
      ) : null}
      {workspace && !product ? (
        <div className="ds-card ds-card--md ds-card--empty text-sm">
          Select a product to scope explore results to your workspace.
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        <select
          value={scope}
          onChange={(e) => setScope(e.target.value as "workspace" | "global")}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-inner focus:border-slate-400 focus:outline-none"
        >
          <option value="workspace" disabled={!workspace || !product}>
            Workspace only{workspace?.name ? ` (${workspace.name})` : ""}
          </option>
          <option value="global">All org brands (global)</option>
        </select>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search brands or domains"
          className="min-w-[200px] flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm shadow-inner focus:border-slate-400 focus:outline-none"
        />
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-inner focus:border-slate-400 focus:outline-none"
        >
          {sortOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => setDirection((d) => (d === "asc" ? "desc" : "asc"))}
          className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
        >
          {direction === "asc" ? "Ascending" : "Descending"}
        </button>
        <label className="flex items-center gap-2 text-xs font-semibold text-slate-600">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-slate-300 text-slate-700 focus:ring-slate-400"
            checked={includeHidden}
            onChange={(e) => setIncludeHidden(e.target.checked)}
          />
          Show hidden
        </label>
        {filtersActive ? (
          <button
            type="button"
            onClick={resetFilters}
            className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
          >
            Reset
          </button>
        ) : null}
      </div>

      <div className="flex flex-col gap-1 text-xs text-slate-600 sm:flex-row sm:items-center sm:justify-between">
        <span>
          Showing {brands.length} of {count || brands.length} brands
        </span>
        <div className="flex flex-wrap items-center gap-3 text-slate-500">
          <span>Scope: {scope === "workspace" ? workspace?.name || "Workspace" : "Global"}</span>
          <span>Sorting: {sortLabel} ({direction})</span>
          <span>Hidden brands: {includeHidden ? "included" : "filtered out"}</span>
        </div>
      </div>

      {error && <div className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">{error}</div>}

      {loading ? (
        <div className="ds-card ds-card--md text-sm text-content-muted shadow-none">Loading brands…</div>
      ) : brands.length ? (
        <div className="ds-card ds-card--md p-0 shadow-sm">
          <Table variant="surface" size={2}>
            <TableHeader>
              <TableRow>
                <TableHeadCell>Brand</TableHeadCell>
                <TableHeadCell>Ads</TableHeadCell>
                <TableHeadCell>Active share</TableHeadCell>
                <TableHeadCell>Channels</TableHeadCell>
                <TableHeadCell>First seen</TableHeadCell>
                <TableHeadCell>Last seen</TableHeadCell>
                <TableHeadCell className="text-right">Visibility</TableHeadCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {brands.map((brand) => {
                const activeShare =
                  brand.ad_count > 0 ? Math.round(((brand.active_count || 0) / brand.ad_count) * 100) : 0;
                return (
                  <TableRow key={brand.brand_id}>
                    <TableCell className="align-top">
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-content">{brand.brand_name || "Unknown brand"}</span>
                          {brand.hidden ? <Badge className="text-[11px]">Hidden</Badge> : null}
                        </div>
                        <div className="text-xs text-content-muted">
                          {brand.primary_domain || brand.primary_website_url || "No domain on file"}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm font-semibold text-content">
                      <div className="flex flex-col gap-0.5">
                        <span>{brand.ad_count ?? 0} total</span>
                        <span className="text-xs text-content-muted">
                          {brand.active_count ?? 0} active · {brand.inactive_count ?? 0} inactive
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-content">
                      <div className="flex flex-col gap-0.5">
                        <span className="font-semibold">{activeShare}%</span>
                        <span className="text-xs text-content-muted">Active share</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-content">
                      {brand.channels?.length ? (
                        <div className="flex flex-wrap gap-1">
                          {brand.channels
                            .filter(Boolean)
                            .map((channel) => (
                              <Badge key={`${brand.brand_id}-${channel}`} className="text-[11px]">
                                {channelDisplayName(channel)}
                              </Badge>
                            ))}
                        </div>
                      ) : (
                        <span className="text-xs text-content-muted">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-content">{formatDate(brand.first_seen_at)}</TableCell>
                    <TableCell className="text-sm text-content">{formatDate(brand.last_seen_at)}</TableCell>
                    <TableCell className="text-right">
                      <button
                        type="button"
                        onClick={() => toggleVisibility(brand)}
                        disabled={updatingBrandId === brand.brand_id}
                        className="inline-flex items-center justify-end rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
                      >
                        {brand.hidden ? "Unhide" : "Hide"}
                      </button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      ) : (
        <div className="ds-card ds-card--md ds-card--empty text-sm">No brands match these filters yet.</div>
      )}
    </div>
  );
}
