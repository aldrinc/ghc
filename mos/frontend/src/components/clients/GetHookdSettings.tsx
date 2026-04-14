import { useMemo, useState } from "react";
import {
  useClientGetHookdCredentials,
  useClientGetHookdSyncFeeds,
  useCreateClientGetHookdSyncFeed,
  useDeleteClientGetHookdSyncFeed,
  useUpdateClientGetHookdCredentials,
  useUpdateClientGetHookdSyncFeed,
} from "@/api/clients";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { GetHookdSyncFeed, GetHookdSyncFeedFilters } from "@/types/common";

const DEFAULT_MAX_PAGES_PER_RUN = 1;
const DEFAULT_PER_PAGE = 10;
const DEFAULT_PLATFORMS = "facebook,instagram";
const DEFAULT_STATUS = "active";
const DEFAULT_SORT_COLUMN = "days_active";
const DEFAULT_SORT_DIRECTION = "desc";
const DEFAULT_ADS_PER_BRAND_LIMIT = 3;
const DEFAULT_PERFORMANCE_SCORES = ["optimized", "winning"];

const PERFORMANCE_OPTIONS = [
  { label: "Testing", value: "testing" },
  { label: "Scaling", value: "scaling" },
  { label: "Growing", value: "growing" },
  { label: "Optimized", value: "optimized" },
  { label: "Winning", value: "winning" },
] as const;

const GETHOOKD_NICHE_OPTIONS = [
  { label: "All niches", value: "" },
  { label: "Accessories", value: "1" },
  { label: "Alcohol", value: "2" },
  { label: "App/Software", value: "3" },
  { label: "Automotive", value: "4" },
  { label: "Beauty", value: "5" },
  { label: "Book/Publishing", value: "6" },
  { label: "Business/Professional", value: "7" },
  { label: "Charity/NFP", value: "8" },
  { label: "Info", value: "9" },
  { label: "Entertainment", value: "10" },
  { label: "Fashion", value: "11" },
  { label: "Finance", value: "12" },
  { label: "Food/Drink", value: "13" },
  { label: "Games", value: "14" },
  { label: "Government", value: "15" },
  { label: "Health/Wellness", value: "16" },
  { label: "Home/Garden", value: "17" },
  { label: "Insurance", value: "18" },
  { label: "Jewelry/Watches", value: "19" },
  { label: "Kids/Baby", value: "20" },
  { label: "Media/News", value: "21" },
  { label: "Medical", value: "22" },
  { label: "Pets", value: "23" },
  { label: "Real Estate", value: "24" },
  { label: "Service Business", value: "25" },
  { label: "Sports/Outdoors", value: "26" },
  { label: "Tech", value: "27" },
  { label: "Travel", value: "28" },
  { label: "Other", value: "29" },
  { label: "Supplements", value: "30" },
] as const;

const PERFORMANCE_LABELS = Object.fromEntries(
  PERFORMANCE_OPTIONS.map((option) => [option.value, option.label]),
) as Record<string, string>;

function getErrorMessage(err: unknown) {
  if (typeof err === "string") return err;
  if (err && typeof err === "object" && "message" in err) {
    return String((err as { message?: unknown }).message || "Request failed");
  }
  return "Request failed";
}

function splitCsv(value?: string | null): string[] {
  return String(value || "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function humanizeCsv(values: string[] | undefined, labels: Record<string, string>) {
  if (!values?.length) return "—";
  return values.map((value) => labels[value] || value).join(", ");
}

function getNicheLabel(value?: string | null) {
  return (
    GETHOOKD_NICHE_OPTIONS.find((option) => option.value === String(value || ""))?.label ||
    String(value || "All niches")
  );
}

type FeedDraft = {
  name: string;
  query: string;
  niche: string;
  status: string;
  performanceScores: string[];
  adsPerBrandLimit: string;
  activeAdsCount: string;
  maxPagesPerRun: string;
  perPage: string;
  enabled: boolean;
};

const EMPTY_DRAFT: FeedDraft = {
  name: "",
  query: "",
  niche: "",
  status: DEFAULT_STATUS,
  performanceScores: [...DEFAULT_PERFORMANCE_SCORES],
  adsPerBrandLimit: String(DEFAULT_ADS_PER_BRAND_LIMIT),
  activeAdsCount: "",
  maxPagesPerRun: String(DEFAULT_MAX_PAGES_PER_RUN),
  perPage: String(DEFAULT_PER_PAGE),
  enabled: true,
};

function buildFeedFilters(draft: FeedDraft): GetHookdSyncFeedFilters {
  const performanceScores = uniqueStrings(draft.performanceScores);
  const adsPerBrandLimit = Number(draft.adsPerBrandLimit || DEFAULT_ADS_PER_BRAND_LIMIT);
  const activeAdsCount = Number(draft.activeAdsCount || 0);

  return {
    query: draft.query.trim(),
    platforms: DEFAULT_PLATFORMS,
    niche: draft.niche || undefined,
    performance_scores: (performanceScores.length ? performanceScores : DEFAULT_PERFORMANCE_SCORES).join(","),
    status: draft.status || DEFAULT_STATUS,
    sort_column: DEFAULT_SORT_COLUMN,
    sort_direction: DEFAULT_SORT_DIRECTION,
    ads_per_brand_limit:
      Number.isFinite(adsPerBrandLimit) && adsPerBrandLimit > 0
        ? adsPerBrandLimit
        : DEFAULT_ADS_PER_BRAND_LIMIT,
    active_ads_count:
      Number.isFinite(activeAdsCount) && activeAdsCount > 0 ? activeAdsCount : undefined,
  };
}

function buildDraftFromFeed(feed: GetHookdSyncFeed): FeedDraft {
  const filters = feed.filters || {};
  const performanceScores = uniqueStrings(splitCsv(filters.performance_scores));
  return {
    name: feed.name,
    query: String(filters.query || ""),
    niche: String(filters.niche || ""),
    status: String(filters.status || DEFAULT_STATUS),
    performanceScores:
      performanceScores.length > 0 ? performanceScores : [...DEFAULT_PERFORMANCE_SCORES],
    adsPerBrandLimit: String(filters.ads_per_brand_limit || DEFAULT_ADS_PER_BRAND_LIMIT),
    activeAdsCount: String(filters.active_ads_count || ""),
    maxPagesPerRun: String(feed.maxPagesPerRun || DEFAULT_MAX_PAGES_PER_RUN),
    perPage: String(feed.perPage || DEFAULT_PER_PAGE),
    enabled: feed.enabled,
  };
}

export function GetHookdSettings({ clientId }: { clientId: string }) {
  const { data: credentials, error: credentialsError } = useClientGetHookdCredentials(clientId);
  const { data: feeds = [], error: feedsError } = useClientGetHookdSyncFeeds(clientId);
  const updateCredentials = useUpdateClientGetHookdCredentials(clientId);
  const createFeed = useCreateClientGetHookdSyncFeed(clientId);
  const updateFeed = useUpdateClientGetHookdSyncFeed(clientId);
  const deleteFeed = useDeleteClientGetHookdSyncFeed(clientId);

  const [token, setToken] = useState("");
  const [draft, setDraft] = useState<FeedDraft>(EMPTY_DRAFT);
  const [editingFeedId, setEditingFeedId] = useState<string | null>(null);

  const activeFeedCount = useMemo(() => feeds.filter((feed) => feed.enabled).length, [feeds]);

  const handleSaveFeed = async () => {
    const payload = {
      name: draft.name,
      enabled: draft.enabled,
      filters: buildFeedFilters(draft),
      maxPagesPerRun: Number(draft.maxPagesPerRun || DEFAULT_MAX_PAGES_PER_RUN),
      perPage: Number(draft.perPage || DEFAULT_PER_PAGE),
    };
    if (editingFeedId) {
      await updateFeed.mutateAsync({ feedId: editingFeedId, payload });
    } else {
      await createFeed.mutateAsync(payload);
    }
    setDraft(EMPTY_DRAFT);
    setEditingFeedId(null);
  };

  const handleEditFeed = (feed: GetHookdSyncFeed) => {
    setEditingFeedId(feed.id);
    setDraft(buildDraftFromFeed(feed));
  };

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-base font-semibold text-content">GetHookd credentials</div>
            <div className="text-sm text-content-muted">
              Store the workspace token used by nightly GetHookd sync.
            </div>
          </div>
          <Badge tone={credentials?.hasCredentials ? "success" : "warning"}>
            {credentials?.hasCredentials ? "Configured" : "Not configured"}
          </Badge>
        </div>
        <div className="mt-4 flex flex-wrap gap-3">
          <Input
            value={token}
            onChange={(event) => setToken(event.target.value)}
            type="password"
            placeholder="Paste GetHookd API token"
            className="min-w-[320px] flex-1"
          />
          <Button
            onClick={() => updateCredentials.mutate({ apiToken: token })}
            disabled={!token.trim() || updateCredentials.isPending}
          >
            Save token
          </Button>
        </div>
        {credentials?.lastValidatedAt ? (
          <div className="mt-2 text-xs text-content-muted">
            Last validated {new Date(credentials.lastValidatedAt).toLocaleString()}
          </div>
        ) : null}
        {credentials?.lastValidationError ? (
          <Callout
            variant="danger"
            size="sm"
            className="mt-3"
            title="Credential validation failed"
          >
            {credentials.lastValidationError}
          </Callout>
        ) : null}
        {credentialsError ? (
          <Callout
            variant="danger"
            size="sm"
            className="mt-3"
            title="Failed to load credentials"
          >
            {getErrorMessage(credentialsError)}
          </Callout>
        ) : null}
      </div>

      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-base font-semibold text-content">GetHookd sync feeds</div>
            <div className="text-sm text-content-muted">
              Define the exact Explore filters saved and reused for nightly sync.
            </div>
          </div>
          <div className="flex gap-2">
            <Badge tone="neutral">{feeds.length} feeds</Badge>
            <Badge tone="success">{activeFeedCount} active</Badge>
          </div>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Input
            value={draft.name}
            onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
            placeholder="Feed name"
          />
          <Input
            value={draft.query}
            onChange={(event) => setDraft((current) => ({ ...current, query: event.target.value }))}
            placeholder="Explore query"
          />
          <Select
            value={draft.niche}
            onValueChange={(value) => setDraft((current) => ({ ...current, niche: value }))}
            options={GETHOOKD_NICHE_OPTIONS.map((option) => ({
              label: option.label,
              value: option.value,
            }))}
          />
          <Select
            value={draft.status}
            onValueChange={(value) => setDraft((current) => ({ ...current, status: value }))}
            options={[
              { label: "Still running", value: "active" },
              { label: "Inactive", value: "inactive" },
            ]}
          />
          <Input
            value={draft.adsPerBrandLimit}
            onChange={(event) =>
              setDraft((current) => ({ ...current, adsPerBrandLimit: event.target.value }))
            }
            placeholder="Ads per brand limit"
          />
          <Input
            value={draft.activeAdsCount}
            onChange={(event) =>
              setDraft((current) => ({ ...current, activeAdsCount: event.target.value }))
            }
            placeholder="Min brand active ads"
          />
          <Input
            value={draft.maxPagesPerRun}
            onChange={(event) =>
              setDraft((current) => ({ ...current, maxPagesPerRun: event.target.value }))
            }
            placeholder="Max pages"
          />
          <Input
            value={draft.perPage}
            onChange={(event) => setDraft((current) => ({ ...current, perPage: event.target.value }))}
            placeholder="Per page"
          />
          <label className="flex items-center gap-2 text-sm text-content-muted">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(event) => setDraft((current) => ({ ...current, enabled: event.target.checked }))}
            />
            Enabled
          </label>
        </div>

        <div className="mt-3 space-y-2 rounded-lg border border-border bg-surface-2 p-3">
          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">
            Performance buckets
          </div>
          <div className="flex flex-wrap gap-2">
            {PERFORMANCE_OPTIONS.map((option) => {
              const checked = draft.performanceScores.includes(option.value);
              return (
                <label
                  key={option.value}
                  className="flex items-center gap-2 rounded-full border border-border px-3 py-1 text-sm text-content-muted"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        performanceScores: event.target.checked
                          ? uniqueStrings([...current.performanceScores, option.value])
                          : current.performanceScores.filter((value) => value !== option.value),
                      }))
                    }
                  />
                  {option.label}
                </label>
              );
            })}
          </div>
        </div>

        <div className="mt-3 flex gap-2">
          <Button
            onClick={() => void handleSaveFeed()}
            disabled={!draft.name.trim() || createFeed.isPending || updateFeed.isPending}
          >
            {editingFeedId ? "Update feed" : "Create feed"}
          </Button>
          {editingFeedId ? (
            <Button
              variant="secondary"
              onClick={() => {
                setEditingFeedId(null);
                setDraft(EMPTY_DRAFT);
              }}
            >
              Cancel
            </Button>
          ) : null}
        </div>

        <div className="mt-4 space-y-3">
          {feeds.map((feed) => {
            const filters = feed.filters || {};
            const performanceValues = splitCsv(filters.performance_scores);
            return (
              <div key={feed.id} className="rounded-lg border border-border bg-surface-2 p-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-content">{feed.name}</div>
                    <div className="mt-1 text-xs text-content-muted">
                      Query: {String(filters.query || "—")}
                    </div>
                    <div className="mt-1 text-xs text-content-muted">
                      Platforms: {String(filters.platforms || DEFAULT_PLATFORMS)}
                    </div>
                    <div className="mt-1 text-xs text-content-muted">
                      Niche: {getNicheLabel(filters.niche)} · Status:{" "}
                      {filters.status === "inactive" ? "Inactive" : "Still running"}
                    </div>
                    <div className="mt-1 text-xs text-content-muted">
                      Performance: {humanizeCsv(performanceValues, PERFORMANCE_LABELS)} · Ads/brand:{" "}
                      {String(filters.ads_per_brand_limit || DEFAULT_ADS_PER_BRAND_LIMIT)}
                    </div>
                    <div className="mt-1 text-xs text-content-muted">
                      Min brand active ads: {String(filters.active_ads_count || "—")}
                    </div>
                    <div className="mt-1 text-xs text-content-muted">
                      {feed.maxPagesPerRun} pages · {feed.perPage} per page
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Badge tone={feed.enabled ? "success" : "neutral"}>
                      {feed.enabled ? "Enabled" : "Disabled"}
                    </Badge>
                    <Button size="sm" variant="secondary" onClick={() => handleEditFeed(feed)}>
                      Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() =>
                        updateFeed.mutate({
                          feedId: feed.id,
                          payload: { enabled: !feed.enabled },
                        })
                      }
                    >
                      {feed.enabled ? "Disable" : "Enable"}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => deleteFeed.mutate(feed.id)}>
                      Delete
                    </Button>
                  </div>
                </div>
              </div>
            );
          })}
          {!feeds.length ? (
            <div className="text-sm text-content-muted">No sync feeds configured yet.</div>
          ) : null}
        </div>

        {feedsError ? (
          <Callout variant="danger" size="sm" className="mt-3" title="Failed to load sync feeds">
            {getErrorMessage(feedsError)}
          </Callout>
        ) : null}
      </div>
    </div>
  );
}
