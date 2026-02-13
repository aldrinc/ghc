import React, { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, ChevronLeft, ChevronRight, Search } from "lucide-react";

/**
 * -----------------------------
 * Standardized data schema
 * -----------------------------
 *
 * The UI is driven entirely by `ReviewsResponse`.
 * If you fetch from a backend, return this shape (or map your API response into it).
 */

export type ISODateString = string; // ISO 8601 (e.g. "2026-02-04T00:00:00.000Z")
export type CountryCode = string; // ISO 3166-1 alpha-2 (e.g. "US")

export type ReviewRating = 1 | 2 | 3 | 4 | 5;

export type ReviewsSort = "most_recent" | "highest_rating" | "lowest_rating" | "most_helpful";

export interface ReviewsQuery {
  /** Used for server-side fetching; keep in sync with your route params */
  productId: string;

  /** Filters */
  search?: string;
  rating?: ReviewRating;
  hasMedia?: boolean;
  country?: CountryCode;
  topicId?: string;

  /** Ordering */
  sort?: ReviewsSort;

  /** Pagination */
  page?: number; // 1-indexed
  pageSize?: number;
}

export interface MediaAsset {
  id: string;
  type: "image" | "video";
  url: string;
  alt?: string;
  width?: number;
  height?: number;
}

export interface ReviewAuthor {
  name: string;
  avatarUrl?: string;
  verifiedBuyer?: boolean;
}

export interface Review {
  id: string;
  rating: ReviewRating;
  title: string;
  body: string;
  createdAt: ISODateString;

  author: ReviewAuthor;

  /** Optional enrichment */
  country?: CountryCode;
  media?: MediaAsset[];
  topicIds?: string[];
  helpfulCount?: number;
}

export interface RatingBreakdownItem {
  rating: ReviewRating;
  count: number;
}

export interface Topic {
  id: string;
  label: string;
  count?: number;
}

export interface ReviewsSummary {
  averageRating: number; // 0..5
  totalReviews: number;
  breakdown: RatingBreakdownItem[]; // should include 5..1

  /** “Customers say” paragraph(s) */
  customersSay: string;

  /** Popular topics chips */
  topics: Topic[];

  /** Gallery thumbnails shown in “Reviews with images” */
  mediaGallery: MediaAsset[];
}

export interface ReviewsFilterOptions {
  ratings: Array<{ value: ReviewRating; label: string; count?: number }>;
  countries: Array<{ code: CountryCode; label: string; count?: number }>;
  sorts: Array<{ value: ReviewsSort; label: string }>;
}

export interface ReviewsPagination {
  page: number; // 1-indexed
  pageSize: number;
  totalReviews: number;
  totalPages: number;
}

export interface ReviewsResponse {
  productId: string;
  summary: ReviewsSummary;
  filters: ReviewsFilterOptions;
  pagination: ReviewsPagination;
  reviews: Review[];
}

export type SalesPdpReviewsConfig = {
  /** Used for in-page nav (header links use `#reviews`). */
  id: string;
  data: ReviewsResponse;
};

type SalesPdpReviewsProps = {
  config?: SalesPdpReviewsConfig;
  configJson?: string;

  /**
   * Optional: lift query changes to your app so you can fetch server-side.
   * If not provided, the demo filters locally.
   */
  onQueryChange?: (q: ReviewsQuery) => void;

  onWriteReview?: () => void;
  onReadSummaryByTopics?: () => void;
};

function describeValue(value: unknown): string {
  if (value === null) return "null";
  if (value === undefined) return "undefined";
  if (Array.isArray(value)) return `array(len=${value.length})`;
  if (typeof value === "object") {
    const keys = Object.keys(value as Record<string, unknown>).slice(0, 12);
    return `object(keys=${keys.join(",")}${keys.length === 12 ? ",…" : ""})`;
  }
  return `${typeof value}(${String(value).slice(0, 120)})`;
}

export function SalesPdpReviews({
  config,
  configJson,
  onQueryChange,
  onWriteReview,
  onReadSummaryByTopics,
}: SalesPdpReviewsProps) {
  let parsed: SalesPdpReviewsConfig | null = null;
  if (typeof configJson === "string" && configJson.trim()) {
    try {
      parsed = JSON.parse(configJson) as SalesPdpReviewsConfig;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      throw new Error(`SalesPdpReviews.configJson must be valid JSON. Received error: ${message}`);
    }
  }
  const resolved = parsed ?? config;
  if (!resolved) {
    throw new Error(
      `SalesPdpReviews requires props.config or props.configJson. Received config=${describeValue(config)} configJson=${describeValue(configJson)}.`
    );
  }
  if (!resolved.id || typeof resolved.id !== "string") {
    throw new Error(`SalesPdpReviews.config.id (string) is required. Received ${describeValue(resolved.id)}.`);
  }
  if (!resolved.data || typeof resolved.data !== "object") {
    throw new Error(`SalesPdpReviews.config.data (ReviewsResponse) is required. Received ${describeValue(resolved.data)}.`);
  }

  const data = resolved.data;

  const [query, setQuery] = useState<ReviewsQuery>(() => ({
    productId: data.productId,
    page: 1,
    pageSize: 10,
    sort: "most_recent",
  }));

  useEffect(() => {
    // Keep product id in sync if the prop changes.
    setQuery((q) => ({ ...q, productId: data.productId }));
  }, [data.productId]);

  useEffect(() => {
    onQueryChange?.(query);
  }, [query, onQueryChange]);

  const filtered = useMemo(() => {
    // If you provide onQueryChange, you probably want server-side filtering.
    // We keep local filtering here purely for a self-contained demo.
    let items = [...data.reviews];

    if (query.search?.trim()) {
      const s = query.search.trim().toLowerCase();
      items = items.filter((r) => `${r.title} ${r.body} ${r.author.name}`.toLowerCase().includes(s));
    }

    if (query.rating) items = items.filter((r) => r.rating === query.rating);

    if (query.hasMedia) {
      items = items.filter((r) => (r.media?.length ?? 0) > 0);
    }

    if (query.country) items = items.filter((r) => r.country === query.country);

    if (query.topicId) {
      items = items.filter((r) => r.topicIds?.includes(query.topicId!));
    }

    const sort = query.sort ?? "most_recent";
    items.sort((a, b) => {
      if (sort === "most_recent") {
        return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
      }
      if (sort === "highest_rating") return b.rating - a.rating;
      if (sort === "lowest_rating") return a.rating - b.rating;
      // most_helpful
      return (b.helpfulCount ?? 0) - (a.helpfulCount ?? 0);
    });

    return items;
  }, [data.reviews, query]);

  const page = query.page ?? 1;
  const pageSize = query.pageSize ?? 10;
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paged = filtered.slice((page - 1) * pageSize, page * pageSize);

  const activeSortLabel =
    data.filters.sorts.find((s) => s.value === (query.sort ?? "most_recent"))?.label ?? "Most recent";

  return (
    <section id={resolved.id} className="w-full bg-background">
      <div className="mx-auto max-w-6xl px-4 py-14 md:px-6">
        <h2 className="text-center font-serif text-5xl tracking-tight text-content">Reviews</h2>

        {/* Summary row */}
        <div className="mx-auto mt-10 max-w-5xl">
          <div className="flex flex-col items-center justify-between gap-10 md:flex-row md:gap-0">
            <div className="flex items-center gap-5">
              <div className="text-6xl font-medium tracking-tight text-content">
                {data.summary.averageRating.toFixed(1)}
              </div>
              <div className="flex flex-col">
                <StarRating value={data.summary.averageRating} size="md" />
                <div className="mt-1 text-sm text-content-muted">
                  Based on {formatNumber(data.summary.totalReviews)} reviews
                </div>
              </div>
            </div>

            <div className="hidden h-16 w-px bg-divider md:block" />

            <div className="w-full max-w-sm md:w-[420px] md:px-8">
              <RatingBreakdown breakdown={normalizeBreakdown(data.summary.breakdown)} total={data.summary.totalReviews} />
            </div>

            <div className="hidden h-16 w-px bg-divider md:block" />

            <button
              type="button"
              onClick={onWriteReview}
              className="inline-flex h-11 items-center justify-center rounded-full bg-primary px-7 text-sm font-semibold text-primary-foreground shadow-sm transition-colors hover:bg-accent-hover active:bg-accent-active focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              Write A Review
            </button>
          </div>
        </div>

        {/* Customers say */}
        <div className="mx-auto mt-14 max-w-5xl">
          <h3 className="text-xl font-semibold text-content">Customers say</h3>
          <p className="mt-4 max-w-4xl text-sm leading-6 text-content-muted">{data.summary.customersSay}</p>

          <button
            type="button"
            onClick={onReadSummaryByTopics}
            className="mt-6 inline-flex h-10 items-center justify-center rounded-full border border-border bg-transparent px-6 text-sm font-semibold text-content transition-colors hover:bg-hover active:bg-active focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            Read summary by topics
          </button>

          <div className="mt-10 h-px w-full bg-divider" />
        </div>

        {/* Reviews with images */}
        <div className="mx-auto mt-10 max-w-5xl">
          <div className="text-sm font-semibold text-content">Reviews with images</div>
          <MediaGallery items={data.summary.mediaGallery} />

          {/* Filters */}
          <div className="mt-6 flex flex-col gap-3 md:flex-row md:items-center md:gap-4">
            <SearchInput
              value={query.search ?? ""}
              onChange={(v) => setQuery((q) => ({ ...q, page: 1, search: v || undefined }))}
              placeholder="Search reviews"
            />

            <PillSelect
              value={query.rating ? String(query.rating) : ""}
              onChange={(v) =>
                setQuery((q) => ({
                  ...q,
                  page: 1,
                  rating: (v ? (Number(v) as ReviewRating) : undefined) as ReviewRating | undefined,
                }))
              }
              placeholder="Rating"
              options={[
                { value: "", label: "Rating" },
                ...data.filters.ratings.map((r) => ({
                  value: String(r.value),
                  label: r.count != null ? `${r.value} star (${formatNumber(r.count)})` : `${r.value} star`,
                })),
              ]}
            />

            <PillSwitch
              label="With media"
              checked={Boolean(query.hasMedia)}
              onCheckedChange={(checked) => setQuery((q) => ({ ...q, page: 1, hasMedia: checked || undefined }))}
            />

            <PillSelect
              value={query.country ?? ""}
              onChange={(v) => setQuery((q) => ({ ...q, page: 1, country: v || undefined }))}
              placeholder="Country"
              options={[
                { value: "", label: "Country" },
                ...data.filters.countries.map((c) => ({
                  value: c.code,
                  label: c.count != null ? `${c.label} (${formatNumber(c.count)})` : c.label,
                })),
              ]}
            />
          </div>

          {/* Popular topics */}
          <div className="mt-5">
            <div className="text-sm font-semibold text-content">Popular topics</div>
            <TopicChips
              topics={data.summary.topics}
              activeTopicId={query.topicId}
              onTopicClick={(topicId) =>
                setQuery((q) => ({
                  ...q,
                  page: 1,
                  topicId: q.topicId === topicId ? undefined : topicId,
                }))
              }
            />
          </div>

          {/* Sort */}
          <div className="mt-10 flex items-center justify-end">
            <div className="flex items-center gap-2 text-sm text-content-muted">
              <span>Sort by:</span>
              <div className="relative">
                <select
                  className="appearance-none bg-transparent pr-6 font-semibold text-content outline-none"
                  value={query.sort ?? "most_recent"}
                  onChange={(e) => setQuery((q) => ({ ...q, page: 1, sort: e.target.value as ReviewsSort }))}
                  aria-label={`Sort by: ${activeSortLabel}`}
                >
                  {data.filters.sorts.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-0 top-1/2 h-4 w-4 -translate-y-1/2 text-content-muted" />
              </div>
            </div>
          </div>

          {/* Reviews list */}
          <div className="mt-6 border-t border-divider">
            {paged.map((r) => (
              <ReviewRow key={r.id} review={r} />
            ))}

            <Pagination page={page} totalPages={totalPages} onPageChange={(next) => setQuery((q) => ({ ...q, page: next }))} />
          </div>
        </div>
      </div>
    </section>
  );
}

/**
 * -----------------------------
 * Subcomponents
 * -----------------------------
 */

function RatingBreakdown({
  breakdown,
  total,
}: {
  breakdown: { rating: ReviewRating; count: number }[];
  total: number;
}) {
  return (
    <div className="space-y-2">
      {breakdown
        .slice()
        .sort((a, b) => b.rating - a.rating)
        .map((row) => {
          const pct = total > 0 ? (row.count / total) * 100 : 0;
          return (
            <div key={row.rating} className="flex items-center gap-3">
              <div className="flex w-12 items-center gap-1 text-sm text-content">
                <span className="tabular-nums">{row.rating}</span>
                <StarGlyph className="h-4 w-4 text-accent" filled />
              </div>

              <div className="h-2 flex-1 rounded-full bg-muted">
                <div className="h-2 rounded-full bg-accent" style={{ width: `${pct}%` }} />
              </div>

              <div className="w-14 text-right text-sm tabular-nums text-accent">{formatNumber(row.count)}</div>
            </div>
          );
        })}
    </div>
  );
}

function MediaGallery({ items }: { items: MediaAsset[] }) {
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(true);

  const updateScrollButtons = () => {
    const el = scrollerRef.current;
    if (!el) return;
    const maxScrollLeft = el.scrollWidth - el.clientWidth;
    setCanScrollLeft(el.scrollLeft > 0);
    setCanScrollRight(el.scrollLeft < maxScrollLeft - 1);
  };

  useEffect(() => {
    updateScrollButtons();
    const el = scrollerRef.current;
    if (!el) return;
    const onScroll = () => updateScrollButtons();
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [items.length]);

  const scrollByPx = (px: number) => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollBy({ left: px, behavior: "smooth" });
  };

  return (
    <div className="relative mt-4">
      {canScrollLeft && (
        <button
          type="button"
          aria-label="Scroll left"
          onClick={() => scrollByPx(-420)}
          className="absolute left-1 top-1/2 z-10 -translate-y-1/2 rounded-full bg-overlay/80 p-2 text-white shadow-sm backdrop-blur transition-colors hover:bg-overlay focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
      )}

      {canScrollRight && (
        <button
          type="button"
          aria-label="Scroll right"
          onClick={() => scrollByPx(420)}
          className="absolute right-1 top-1/2 z-10 -translate-y-1/2 rounded-full bg-overlay/80 p-2 text-white shadow-sm backdrop-blur transition-colors hover:bg-overlay focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          <ChevronRight className="h-5 w-5" />
        </button>
      )}

      <div
        ref={scrollerRef}
        className="flex gap-2 overflow-x-auto scroll-smooth pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {items.map((m) => (
          <div key={m.id} className="relative h-[118px] w-[165px] flex-none overflow-hidden rounded-lg bg-surface/60">
            <img src={m.url} alt={m.alt ?? "Review media"} className="h-full w-full object-cover" loading="lazy" />
          </div>
        ))}
      </div>
    </div>
  );
}

function SearchInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="relative w-full md:max-w-[260px]">
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-10 w-full rounded-full border border-input-border bg-input pl-11 pr-4 text-sm text-content shadow-sm transition placeholder:text-content-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:border-input-border-focus"
      />
      <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-content-muted" />
    </div>
  );
}

function PillSelect({
  value,
  onChange,
  placeholder,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <div className="relative w-full md:w-auto">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 w-full appearance-none rounded-full border border-input-border bg-input px-4 pr-10 text-sm text-content shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:border-input-border-focus md:w-[200px]"
        aria-label={placeholder}
      >
        {options.map((o) => (
          <option key={`${o.value}-${o.label}`} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 text-content-muted" />
    </div>
  );
}

function PillSwitch({
  label,
  checked,
  onCheckedChange,
}: {
  label: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onCheckedChange(!checked)}
      className="flex h-10 w-full items-center justify-between gap-3 rounded-full border border-input-border bg-input px-4 text-sm text-content shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:border-input-border-focus md:w-[200px]"
      aria-pressed={checked}
    >
      <span className="text-content">{label}</span>
      <span className={"relative h-5 w-9 rounded-full transition " + (checked ? "bg-primary" : "bg-muted")}>
        <span
          className={
            "absolute top-0.5 h-4 w-4 rounded-full bg-surface shadow-sm transition " +
            (checked ? "left-[18px]" : "left-0.5")
          }
        />
      </span>
    </button>
  );
}

function TopicChips({
  topics,
  activeTopicId,
  onTopicClick,
}: {
  topics: Topic[];
  activeTopicId?: string;
  onTopicClick: (topicId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? topics : topics.slice(0, 8);

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      {visible.map((t) => {
        const active = t.id === activeTopicId;
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => onTopicClick(t.id)}
            className={
              "rounded-full border px-4 py-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-background " +
              (active
                ? "border-transparent bg-primary text-primary-foreground"
                : "border-border bg-surface text-content hover:bg-hover active:bg-active")
            }
          >
            {t.label}
          </button>
        );
      })}

      {topics.length > 8 && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="ml-1 text-sm font-semibold text-content underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  );
}

function ReviewRow({ review }: { review: Review }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = review.body.length > 240;
  const shown = expanded || !isLong ? review.body : `${review.body.slice(0, 240)}…`;

  return (
    <div className="flex gap-4 py-8">
      <Avatar name={review.author.name} url={review.author.avatarUrl} />

      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-sm font-semibold text-content">{review.author.name}</div>
            {review.author.verifiedBuyer && (
              <div className="mt-1 inline-flex items-center gap-2 text-xs text-content-muted">
                <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-primary text-primary-foreground">
                  <Check className="h-3 w-3" />
                </span>
                Verified Buyer
              </div>
            )}
          </div>

          <div className="text-sm tabular-nums text-content-muted">{formatDateMMDDYY(review.createdAt)}</div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <StarRating value={review.rating} size="sm" />
          <div className="text-sm font-semibold text-content">{review.title}</div>
        </div>

        <div className="mt-4 text-sm leading-6 text-content">
          {shown}
          {isLong && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="ml-2 font-semibold text-content underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              {expanded ? "Show less" : "Read more"}
            </button>
          )}
        </div>

        {review.media?.length ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {review.media.slice(0, 4).map((m) => (
              <img key={m.id} src={m.url} alt={m.alt ?? "Review media"} className="h-20 w-28 rounded-md object-cover" loading="lazy" />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Pagination({
  page,
  totalPages,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  if (totalPages <= 1) return null;

  return (
    <div className="flex items-center justify-between border-t border-divider py-6">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPageChange(Math.max(1, page - 1))}
        className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-4 py-2 text-sm font-semibold text-content shadow-sm transition-colors hover:bg-hover active:bg-active disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <ChevronLeft className="h-4 w-4" />
        Prev
      </button>

      <div className="text-sm text-content-muted">
        Page <span className="font-semibold text-content">{page}</span> of{" "}
        <span className="font-semibold text-content">{totalPages}</span>
      </div>

      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onPageChange(Math.min(totalPages, page + 1))}
        className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-4 py-2 text-sm font-semibold text-content shadow-sm transition-colors hover:bg-hover active:bg-active disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        Next
        <ChevronRight className="h-4 w-4" />
      </button>
    </div>
  );
}

function Avatar({ name, url }: { name: string; url?: string }) {
  const initials = name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");

  return (
    <div className="h-11 w-11 flex-none overflow-hidden rounded-full bg-muted">
      {url ? (
        <img src={url} alt={name} className="h-full w-full object-cover" />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-xs font-semibold text-content-muted">
          {initials || "U"}
        </div>
      )}
    </div>
  );
}

function StarRating({ value, size }: { value: number; size: "sm" | "md" }) {
  const iconSize = size === "md" ? "h-5 w-5" : "h-4 w-4";

  return (
    <div className="flex items-center gap-1" aria-label={`${value} out of 5 stars`}>
      {Array.from({ length: 5 }).map((_, i) => {
        const fill = clamp(value - i, 0, 1);
        return (
          <div key={i} className={`relative ${iconSize}`}>
            <StarGlyph className={`${iconSize} text-border`} filled={false} />
            <div className="absolute inset-0 overflow-hidden" style={{ width: `${fill * 100}%` }}>
              <StarGlyph className={`${iconSize} text-accent`} filled />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function StarGlyph({ className, filled }: { className?: string; filled: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth={filled ? 0 : 2}>
      <path d="M12 2.5l2.98 6.16 6.8.99-4.9 4.77 1.16 6.77L12 18.98 5.96 21.19l1.16-6.77-4.9-4.77 6.8-.99L12 2.5z" />
    </svg>
  );
}

/**
 * -----------------------------
 * Helpers
 * -----------------------------
 */

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

function formatNumber(n: number) {
  return new Intl.NumberFormat(undefined).format(n);
}

function formatDateMMDDYY(iso: ISODateString) {
  const d = new Date(iso);
  // If the backend sends a date-only string (e.g. "2026-02-04"), Date() will treat it as UTC.
  // That’s usually fine for review dates.
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const yy = String(d.getFullYear()).slice(-2);
  return `${mm}/${dd}/${yy}`;
}

function normalizeBreakdown(items: RatingBreakdownItem[]) {
  const map = new Map(items.map((i) => [i.rating, i.count]));
  const all: ReviewRating[] = [5, 4, 3, 2, 1];
  return all.map((r) => ({ rating: r, count: map.get(r) ?? 0 }));
}
