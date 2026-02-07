import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useBrandRelationshipsApi, type BrandRelationship } from "@/api/brands";
import { useExploreApi } from "@/api/explore";
import { normalizeExploreAdToLibraryItem } from "@/lib/library";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";
import { LibraryCard } from "@/components/library/LibraryCard";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { channelDisplayName } from "@/lib/channels";
import type { LibraryItem } from "@/types/library";
import { AdsIngestionRetryCallout } from "@/components/ads/AdsIngestionRetryCallout";

const PAGE_SIZE = 60;

const channelOptions = [
  { value: "", label: "All channels" },
  { value: "META_ADS_LIBRARY", label: "Meta" },
  { value: "TIKTOK_CREATIVE_CENTER", label: "TikTok" },
  { value: "GOOGLE_ADS_TRANSPARENCY", label: "Google" },
];

const statusOptions = [
  { value: "", label: "Any status" },
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
  { value: "unknown", label: "Unknown" },
];

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

function formatSourceType(value?: string | null) {
  if (!value) return "Unknown";
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function LoadingGrid() {
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-3 sm:gap-4">
      {Array.from({ length: 6 }).map((_, idx) => (
        <div
          key={idx}
          className="ds-card ds-card--md flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-none animate-pulse"
        >
          <div className="relative">
            <div className="aspect-[4/5] w-full bg-muted" />
            <div className="pointer-events-none absolute inset-0 flex flex-col justify-between p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="h-5 w-20 rounded-full bg-black/20" />
                <div className="h-5 w-12 rounded-full bg-black/20" />
              </div>
              <div className="h-4 w-24 rounded-full bg-black/20" />
            </div>
          </div>
          <div className="space-y-2 px-3 pb-3 pt-3">
            <div className="h-3 w-3/4 rounded bg-muted" />
            <div className="h-3 w-5/6 rounded bg-muted" />
            <div className="h-3 w-1/2 rounded bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}

function ResearchAdsTab() {
  const { listAds } = useExploreApi();
  const { listRelationships } = useBrandRelationshipsApi();
  const { workspace } = useWorkspace();
  const { product } = useProductContext();

  const [query, setQuery] = useState("");
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("");
  const [brandId, setBrandId] = useState("");
  const [brandOptions, setBrandOptions] = useState<{ value: string; label: string }[]>([]);
  const [brandsLoading, setBrandsLoading] = useState(false);
  const [brandError, setBrandError] = useState<string | null>(null);
  const [limitPerBrand, setLimitPerBrand] = useState<number | undefined>(undefined);
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [count, setCount] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState(0);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  const filtersKeyRef = useRef<string>("");

  const errorMessage = useCallback((err: any, fallback: string) => {
    const msg = err?.message;
    return typeof msg === "string" ? msg : fallback;
  }, []);

  useEffect(() => {
    if (!workspace?.id || !product?.id) {
      setBrandOptions([]);
      setBrandsLoading(false);
      setBrandError("Workspace and product are required to load brands.");
      return;
    }

    let cancelled = false;
    setBrandsLoading(true);
    listRelationships({
      clientId: workspace.id,
      productId: product.id,
      relationshipType: "competitor",
      sort: "name",
      direction: "asc",
      limit: 200,
    })
      .then((resp) => {
        if (cancelled) return;
        const options =
          (resp?.items ?? []).map((brand) => {
            const name = brand.brand_name || brand.primary_domain || brand.primary_website_url || "Unknown brand";
            const domain = brand.primary_domain || brand.primary_website_url;
            const label = domain && domain !== name ? `${name} (${domain})` : name;
            return { value: brand.brand_id, label };
          }) || [];
        setBrandOptions(options);
        setBrandError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setBrandOptions([]);
        setBrandError(errorMessage(err, "Failed to load brands"));
      })
      .finally(() => {
        if (!cancelled) {
          setBrandsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [errorMessage, listRelationships, product?.id, workspace?.id]);

  const baseParams = useMemo(
    () => ({
      q: query || undefined,
      channels: channel ? [channel] : undefined,
      status: status ? [status] : undefined,
      brandIds: brandId ? [brandId] : undefined,
      clientId: workspace?.id,
      productId: product?.id,
      limitPerBrand: limitPerBrand || undefined,
      sort: "last_seen",
    }),
    [brandId, channel, limitPerBrand, product?.id, query, status, workspace?.id],
  );

  const filtersKey = useMemo(() => JSON.stringify(baseParams), [baseParams]);

  useEffect(() => {
    filtersKeyRef.current = filtersKey;
  }, [filtersKey]);

  useEffect(() => {
    if (!workspace?.id || !product?.id) {
      setItems([]);
      setCount(0);
      setHasMore(false);
      setError("Workspace and product are required to view ads.");
      setLoading(false);
      return;
    }

    let cancelled = false;
    filtersKeyRef.current = filtersKey;
    setItems([]);
    setCount(0);
    setHasMore(false);
    setNextOffset(0);
    setLoading(true);
    setError(null);
    setLoadingMore(false);
    listAds({
      ...baseParams,
      limit: PAGE_SIZE,
      offset: 0,
    })
      .then((resp) => {
        if (cancelled || filtersKeyRef.current !== filtersKey) return;
        const normalized = (resp?.items ?? []).map(normalizeExploreAdToLibraryItem);
        setError(null);
        const totalCount = resp?.count ?? normalized.length;
        setItems(normalized);
        setCount(totalCount);
        setHasMore(normalized.length < totalCount);
        setNextOffset(normalized.length);
      })
      .catch((err) => {
        if (cancelled || filtersKeyRef.current !== filtersKey) return;
        setItems([]);
        setCount(0);
        setHasMore(false);
        setError(errorMessage(err, "Failed to load ads"));
      })
      .finally(() => {
        if (cancelled || filtersKeyRef.current !== filtersKey) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [baseParams, errorMessage, filtersKey, listAds, product?.id, workspace?.id]);

  const loadMore = useCallback(() => {
    if (loading || loadingMore || !hasMore) return;
    const currentKey = filtersKeyRef.current;
    setLoadingMore(true);
    listAds({
      ...baseParams,
      limit: PAGE_SIZE,
      offset: nextOffset,
    })
      .then((resp) => {
        if (filtersKeyRef.current !== currentKey) return;
        const normalized = (resp?.items ?? []).map(normalizeExploreAdToLibraryItem);
        const totalCount = resp?.count ?? count;
        setItems((prev) => {
          const nextItems = [...prev, ...normalized];
          const resolvedCount = totalCount ?? nextItems.length;
          setCount(resolvedCount);
          setHasMore(normalized.length > 0 && nextItems.length < resolvedCount);
          setNextOffset(nextItems.length);
          return nextItems;
        });
        setError(null);
      })
      .catch((err) => {
        if (filtersKeyRef.current !== currentKey) return;
        setError(errorMessage(err, "Failed to load ads"));
      })
      .finally(() => {
        if (filtersKeyRef.current !== currentKey) return;
        setLoadingMore(false);
      });
  }, [baseParams, count, errorMessage, hasMore, listAds, loading, loadingMore, nextOffset]);

  useEffect(() => {
    const node = loadMoreRef.current;
    if (!node || !hasMore) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          loadMore();
        }
      },
      { rootMargin: "300px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, loadMore]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search ads"
          className="min-w-[180px] flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm shadow-inner focus:border-slate-400 focus:outline-none"
        />
        <select
          value={channel}
          onChange={(e) => setChannel(e.target.value)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-inner focus:border-slate-400 focus:outline-none"
        >
          {channelOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-inner focus:border-slate-400 focus:outline-none"
        >
          {statusOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <select
          value={brandId}
          onChange={(e) => setBrandId(e.target.value)}
          className="min-w-[200px] rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-inner focus:border-slate-400 focus:outline-none"
          aria-label="Filter by brand"
        >
          <option value="">{brandsLoading ? "Loading brands..." : "All brands"}</option>
          {brandOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <select
          value={limitPerBrand ?? ""}
          onChange={(e) => setLimitPerBrand(e.target.value ? Number(e.target.value) : undefined)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-inner focus:border-slate-400 focus:outline-none"
        >
          <option value="">All per brand</option>
          <option value="5">Max 5 / brand</option>
          <option value="10">Max 10 / brand</option>
          <option value="20">Max 20 / brand</option>
        </select>
      </div>

      {brandError && <div className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">{brandError}</div>}
      {error && <div className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">{error}</div>}

      {loading ? (
        <LoadingGrid />
      ) : items.length ? (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-3 sm:gap-4">
          {items.map((item) => (
            <LibraryCard key={item.id} item={item} />
          ))}
        </div>
      ) : (
        <div className="ds-card ds-card--md ds-card--empty text-sm">No ads found for this product.</div>
      )}

      {hasMore ? (
        <div ref={loadMoreRef} className="flex items-center justify-center py-6 text-sm text-content-muted">
          {loadingMore ? "Loading more ads…" : "Scroll for more ads"}
        </div>
      ) : null}
    </div>
  );
}

function ResearchBrandsTab() {
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const { listRelationships } = useBrandRelationshipsApi();

  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("last_seen");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");
  const [brands, setBrands] = useState<BrandRelationship[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadBrands = useCallback(
    async (opts?: { cancelRef?: { cancelled: boolean } }) => {
      const { cancelRef } = opts || {};
      if (!workspace?.id || !product?.id) {
        setBrands([]);
        setCount(0);
        setError("Workspace and product are required to view brands.");
        return;
      }
      setLoading(true);
      try {
        const resp = await listRelationships({
          q: query || undefined,
          clientId: workspace.id,
          productId: product.id,
          relationshipType: "competitor",
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
        if (!cancelRef?.cancelled) {
          setLoading(false);
        }
      }
    },
    [direction, listRelationships, product?.id, query, sort, workspace?.id],
  );

  useEffect(() => {
    const cancelRef = { cancelled: false };
    loadBrands({ cancelRef });
    return () => {
      cancelRef.cancelled = true;
    };
  }, [loadBrands]);

  const sortLabel = sortOptions.find((opt) => opt.value === sort)?.label || "Last seen";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
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
      </div>

      <div className="flex flex-col gap-1 text-xs text-slate-600 sm:flex-row sm:items-center sm:justify-between">
        <span>
          Showing {brands.length} of {count || brands.length} brands
        </span>
        <div className="flex flex-wrap items-center gap-3 text-slate-500">
          <span>Sorting: {sortLabel} ({direction})</span>
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
                <TableHeadCell>Source</TableHeadCell>
                <TableHeadCell>Ads</TableHeadCell>
                <TableHeadCell>Active share</TableHeadCell>
                <TableHeadCell>Channels</TableHeadCell>
                <TableHeadCell>Last seen</TableHeadCell>
                <TableHeadCell>Linked</TableHeadCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {brands.map((brand) => {
                const activeShare = brand.ad_count ? Math.round((brand.active_count / brand.ad_count) * 100) : null;
                return (
                  <TableRow key={brand.relationship_id}>
                    <TableCell className="font-semibold text-content">
                      <div>{brand.brand_name || brand.brand_id}</div>
                      <div className="text-xs text-content-muted">
                        {brand.primary_domain || brand.primary_website_url || "—"}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-content-muted">
                      <div className="font-semibold text-content">{formatSourceType(brand.source_type)}</div>
                      <div>{brand.source_id ? `${brand.source_id.slice(0, 6)}…` : "—"}</div>
                    </TableCell>
                    <TableCell className="text-xs text-content-muted">{brand.ad_count}</TableCell>
                    <TableCell className="text-xs text-content-muted">
                      {activeShare === null ? "—" : `${activeShare}%`}
                    </TableCell>
                    <TableCell className="text-xs text-content-muted">
                      <div className="flex flex-wrap gap-1">
                        {(brand.channels || []).length
                          ? brand.channels.map((channel) => (
                              <Badge key={channel} variant="outline">
                                {channelDisplayName(channel)}
                              </Badge>
                            ))
                          : "—"}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-content-muted">{formatDate(brand.last_seen_at)}</TableCell>
                    <TableCell className="text-xs text-content-muted">{formatDate(brand.created_at)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      ) : (
        <div className="ds-card ds-card--md ds-card--empty text-sm">
          No competitor brands linked to this product yet.
        </div>
      )}
    </div>
  );
}

export function ResearchPage() {
  const { workspace } = useWorkspace();
  const { product } = useProductContext();
  const [searchParams, setSearchParams] = useSearchParams();

  const tabParam = searchParams.get("tab");
  const activeTab = tabParam === "brands" ? "brands" : "ads";

  const handleTabChange = (value: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", value);
    setSearchParams(next, { replace: true });
  };

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Research" description="Select a workspace to view ads and brands." />
        <div className="ds-card ds-card--md ds-card--empty text-center text-sm">
          Choose a workspace from the sidebar.
        </div>
      </div>
    );
  }
  if (!product) {
    return (
      <div className="space-y-4">
        <PageHeader title="Research" description="Select a product to view ads and brands." />
        <div className="ds-card ds-card--md ds-card--empty text-center text-sm">
          Choose a product from the header to view research.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Research"
        description={`Ads and competitor brands for ${product.name}.`}
      />
      <AdsIngestionRetryCallout clientId={workspace?.id} productId={product?.id} />

      <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-4">
        <TabsList className="w-full justify-start">
          <TabsTrigger value="ads">Ads</TabsTrigger>
          <TabsTrigger value="brands">Brands</TabsTrigger>
        </TabsList>
        <TabsContent value="ads">
          <ResearchAdsTab />
        </TabsContent>
        <TabsContent value="brands">
          <ResearchBrandsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
