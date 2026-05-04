import { useMemo, useState, type HTMLInputTypeAttribute } from "react";
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

const DEFAULT_MAX_PAGES_PER_RUN = 0;
const DEFAULT_PER_PAGE = 20;

const STATUS_OPTIONS = [
  { label: "API default", value: "" },
  { label: "Active", value: "active" },
  { label: "Inactive", value: "inactive" },
] as const;

const SORT_COLUMN_OPTIONS = [
  { label: "API default", value: "" },
  { label: "Newest (created_at)", value: "created_at" },
  { label: "Start date", value: "start_date" },
  { label: "Days active", value: "days_active" },
  { label: "Used count", value: "used_count" },
] as const;

const SORT_DIRECTION_OPTIONS = [
  { label: "API default", value: "" },
  { label: "Descending", value: "desc" },
  { label: "Ascending", value: "asc" },
] as const;

const EU_TRANSPARENCY_OPTIONS = [
  { label: "Any", value: "" },
  { label: "EU transparency only", value: "1" },
  { label: "Exclude EU transparency", value: "0" },
] as const;

const FILTER_LABELS: Array<[keyof GetHookdSyncFeedFilters, string]> = [
  ["query", "Query"],
  ["platform", "Platform"],
  ["ad_format", "Ad format"],
  ["status", "Status"],
  ["sort_column", "Sort column"],
  ["sort_direction", "Sort direction"],
  ["start_date", "Start date"],
  ["end_date", "End date"],
  ["run_time", "Run time"],
  ["language", "Language"],
  ["niche", "Niche"],
  ["performance_scores", "Performance scores"],
  ["used_count", "Used count"],
  ["video_lengths", "Video lengths"],
  ["eu_transparency", "EU transparency"],
  ["eu_total_reach", "EU total reach"],
  ["gender_audience", "Gender audience"],
  ["age_audience", "Age audience"],
  ["location", "Location"],
  ["ad_spend_range", "Ad spend range"],
  ["excluded_brands", "Excluded brands"],
  ["creative_categories", "Creative categories"],
  ["cta_types", "CTA types"],
  ["active_ads_count", "Active ads count"],
  ["ads_per_brand_limit", "Ads per brand limit"],
];

type FeedDraft = {
  name: string;
  query: string;
  platform: string;
  adFormat: string;
  status: string;
  sortColumn: string;
  sortDirection: string;
  startDate: string;
  endDate: string;
  runTime: string;
  language: string;
  niche: string;
  performanceScores: string;
  usedCount: string;
  videoLengths: string;
  euTransparency: string;
  euTotalReach: string;
  genderAudience: string;
  ageAudience: string;
  location: string;
  adSpendRange: string;
  excludedBrands: string;
  creativeCategories: string;
  ctaTypes: string;
  activeAdsCount: string;
  adsPerBrandLimit: string;
  maxPagesPerRun: string;
  perPage: string;
  enabled: boolean;
};

const EMPTY_DRAFT: FeedDraft = {
  name: "",
  query: "",
  platform: "",
  adFormat: "",
  status: "",
  sortColumn: "",
  sortDirection: "",
  startDate: "",
  endDate: "",
  runTime: "",
  language: "",
  niche: "",
  performanceScores: "",
  usedCount: "",
  videoLengths: "",
  euTransparency: "",
  euTotalReach: "",
  genderAudience: "",
  ageAudience: "",
  location: "",
  adSpendRange: "",
  excludedBrands: "",
  creativeCategories: "",
  ctaTypes: "",
  activeAdsCount: "",
  adsPerBrandLimit: "",
  maxPagesPerRun: String(DEFAULT_MAX_PAGES_PER_RUN),
  perPage: String(DEFAULT_PER_PAGE),
  enabled: true,
};

function getErrorMessage(err: unknown) {
  if (typeof err === "string") return err;
  if (err && typeof err === "object" && "message" in err) {
    return String((err as { message?: unknown }).message || "Request failed");
  }
  return "Request failed";
}

function cleanText(value: string): string | undefined {
  const cleaned = String(value || "").trim();
  return cleaned || undefined;
}

function parseOptionalInt(
  value: string,
  {
    fieldLabel,
    min,
    max,
  }: {
  fieldLabel: string;
  min: number;
  max?: number;
}): number | undefined {
  const cleaned = cleanText(value);
  if (!cleaned) return undefined;
  const parsed = Number(cleaned);
  if (!Number.isInteger(parsed)) {
    throw new Error(`${fieldLabel} must be an integer.`);
  }
  if (parsed < min) {
    throw new Error(`${fieldLabel} must be ${min} or greater.`);
  }
  if (typeof max === "number" && parsed > max) {
    throw new Error(`${fieldLabel} must be ${max} or less.`);
  }
  return parsed;
}

function parseRequiredInt(
  value: string,
  {
    fieldLabel,
    min,
    max,
  }: {
  fieldLabel: string;
  min: number;
  max?: number;
}): number {
  const parsed = parseOptionalInt(value, { fieldLabel, min, max });
  if (typeof parsed !== "number") {
    throw new Error(`${fieldLabel} is required.`);
  }
  return parsed;
}

function buildFeedFilters(draft: FeedDraft): GetHookdSyncFeedFilters {
  return {
    query: cleanText(draft.query),
    platform: cleanText(draft.platform),
    ad_format: cleanText(draft.adFormat),
    status: (cleanText(draft.status) as GetHookdSyncFeedFilters["status"]) || undefined,
    sort_column:
      (cleanText(draft.sortColumn) as GetHookdSyncFeedFilters["sort_column"]) || undefined,
    sort_direction:
      (cleanText(draft.sortDirection) as GetHookdSyncFeedFilters["sort_direction"]) || undefined,
    start_date: cleanText(draft.startDate),
    end_date: cleanText(draft.endDate),
    run_time: parseOptionalInt(draft.runTime, { fieldLabel: "Run time", min: 1 }),
    language: cleanText(draft.language),
    niche: cleanText(draft.niche),
    performance_scores: cleanText(draft.performanceScores),
    used_count: parseOptionalInt(draft.usedCount, { fieldLabel: "Used count", min: 1 }),
    video_lengths: cleanText(draft.videoLengths),
    eu_transparency: parseOptionalInt(draft.euTransparency, {
      fieldLabel: "EU transparency",
      min: 0,
      max: 1,
    }),
    eu_total_reach: parseOptionalInt(draft.euTotalReach, {
      fieldLabel: "EU total reach",
      min: 0,
    }),
    gender_audience: cleanText(draft.genderAudience),
    age_audience: cleanText(draft.ageAudience),
    location: cleanText(draft.location),
    ad_spend_range: cleanText(draft.adSpendRange),
    excluded_brands: cleanText(draft.excludedBrands),
    creative_categories: cleanText(draft.creativeCategories),
    cta_types: cleanText(draft.ctaTypes),
    active_ads_count: parseOptionalInt(draft.activeAdsCount, {
      fieldLabel: "Active ads count",
      min: 1,
    }),
    ads_per_brand_limit: parseOptionalInt(draft.adsPerBrandLimit, {
      fieldLabel: "Ads per brand limit",
      min: 1,
      max: 50,
    }),
  };
}

function readFilterText(filters: GetHookdSyncFeedFilters, ...keys: Array<keyof GetHookdSyncFeedFilters>) {
  for (const key of keys) {
    const value = filters[key];
    if (value === undefined || value === null) continue;
    const cleaned = String(value).trim();
    if (cleaned) return cleaned;
  }
  return "";
}

function buildDraftFromFeed(feed: GetHookdSyncFeed): FeedDraft {
  const filters = feed.filters || {};
  return {
    name: feed.name,
    query: readFilterText(filters, "query"),
    platform: readFilterText(filters, "platform", "platforms"),
    adFormat: readFilterText(filters, "ad_format"),
    status: readFilterText(filters, "status"),
    sortColumn: readFilterText(filters, "sort_column"),
    sortDirection: readFilterText(filters, "sort_direction"),
    startDate: readFilterText(filters, "start_date"),
    endDate: readFilterText(filters, "end_date"),
    runTime: readFilterText(filters, "run_time"),
    language: readFilterText(filters, "language"),
    niche: readFilterText(filters, "niche"),
    performanceScores: readFilterText(filters, "performance_scores"),
    usedCount: readFilterText(filters, "used_count"),
    videoLengths: readFilterText(filters, "video_lengths"),
    euTransparency: readFilterText(filters, "eu_transparency"),
    euTotalReach: readFilterText(filters, "eu_total_reach"),
    genderAudience: readFilterText(filters, "gender_audience"),
    ageAudience: readFilterText(filters, "age_audience"),
    location: readFilterText(filters, "location"),
    adSpendRange: readFilterText(filters, "ad_spend_range"),
    excludedBrands: readFilterText(filters, "excluded_brands"),
    creativeCategories: readFilterText(filters, "creative_categories"),
    ctaTypes: readFilterText(filters, "cta_types"),
    activeAdsCount: readFilterText(filters, "active_ads_count"),
    adsPerBrandLimit: readFilterText(filters, "ads_per_brand_limit"),
    maxPagesPerRun: String(feed.maxPagesPerRun ?? DEFAULT_MAX_PAGES_PER_RUN),
    perPage: String(feed.perPage ?? DEFAULT_PER_PAGE),
    enabled: feed.enabled,
  };
}

function summarizeFilters(filters: GetHookdSyncFeedFilters): string[] {
  const summary: string[] = [];
  for (const [key, label] of FILTER_LABELS) {
    const value = filters[key];
    if (value === undefined || value === null || value === "") continue;
    if (key === "eu_transparency") {
      summary.push(`${label}: ${Number(value) === 1 ? "Yes" : "No"}`);
      continue;
    }
    summary.push(`${label}: ${String(value)}`);
  }
  return summary;
}

type DraftFieldKey = Exclude<keyof FeedDraft, "enabled">;

type FieldConfig = {
  key: DraftFieldKey;
  label: string;
  placeholder?: string;
  type?: HTMLInputTypeAttribute;
};

const API_FILTER_FIELDS: FieldConfig[] = [
  { key: "query", label: "Query", placeholder: "supplements" },
  { key: "platform", label: "Platform (CSV)", placeholder: "facebook,instagram" },
  { key: "adFormat", label: "Ad format (CSV)", placeholder: "image" },
  { key: "niche", label: "Niche (CSV ids)", placeholder: "30" },
  { key: "location", label: "Location (CSV)", placeholder: "US,DE" },
  { key: "language", label: "Language (CSV)", placeholder: "EN,ES" },
  { key: "performanceScores", label: "Performance scores (CSV)", placeholder: "growing,optimized,winning" },
  { key: "videoLengths", label: "Video lengths (CSV)", placeholder: "less_than_1_min,1_to_3_min" },
  { key: "genderAudience", label: "Gender audience (CSV)", placeholder: "men,women" },
  { key: "ageAudience", label: "Age audience (CSV)", placeholder: "25-34,35-44" },
  { key: "adSpendRange", label: "Ad spend range (CSV)", placeholder: "3,4" },
  { key: "excludedBrands", label: "Excluded brand ids (CSV)", placeholder: "10,11" },
  { key: "creativeCategories", label: "Creative categories (CSV)", placeholder: "17,18" },
  { key: "ctaTypes", label: "CTA types (CSV)", placeholder: "SHOP_NOW,LEARN_MORE" },
  { key: "startDate", label: "Start date", type: "date" },
  { key: "endDate", label: "End date", type: "date" },
  { key: "runTime", label: "Run time (days)", type: "number", placeholder: "7" },
  { key: "usedCount", label: "Used count", type: "number", placeholder: "3" },
  { key: "euTotalReach", label: "EU total reach", type: "number", placeholder: "200" },
  { key: "activeAdsCount", label: "Active ads count", type: "number", placeholder: "5" },
  { key: "adsPerBrandLimit", label: "Ads per brand limit", type: "number", placeholder: "4" },
];

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
  const [formError, setFormError] = useState<string | null>(null);

  const activeFeedCount = useMemo(() => feeds.filter((feed) => feed.enabled).length, [feeds]);

  const setDraftValue = (key: DraftFieldKey, value: string) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const handleSaveFeed = async () => {
    try {
      const payload = {
        name: draft.name.trim(),
        enabled: draft.enabled,
        filters: buildFeedFilters(draft),
        maxPagesPerRun: parseRequiredInt(draft.maxPagesPerRun, {
          fieldLabel: "Page cap",
          min: 0,
        }),
        perPage: parseRequiredInt(draft.perPage, {
          fieldLabel: "Per page",
          min: 1,
          max: 100,
        }),
      };
      if (!payload.name) {
        throw new Error("Feed name is required.");
      }
      if (editingFeedId) {
        await updateFeed.mutateAsync({ feedId: editingFeedId, payload });
      } else {
        await createFeed.mutateAsync(payload);
      }
      setDraft(EMPTY_DRAFT);
      setEditingFeedId(null);
      setFormError(null);
    } catch (err) {
      setFormError(getErrorMessage(err));
    }
  };

  const handleEditFeed = (feed: GetHookdSyncFeed) => {
    setEditingFeedId(feed.id);
    setDraft(buildDraftFromFeed(feed));
    setFormError(null);
  };

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-base font-semibold text-content">GetHookd credentials</div>
            <div className="text-sm text-content-muted">
              Store the workspace token used by GetHookd Explore sync.
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
              These fields map directly to documented Explore API parameters. Leave a field blank to omit it.
            </div>
          </div>
          <div className="flex gap-2">
            <Badge tone="neutral">{feeds.length} feeds</Badge>
            <Badge tone="success">{activeFeedCount} active</Badge>
          </div>
        </div>

        <Callout variant="info" size="sm" className="mt-4" title="Sync behavior">
          `perPage` is passed directly to GetHookd. `Page cap` is a MOS operator override: `0` fetches all pages, any positive integer caps the sync.
        </Callout>

        {formError ? (
          <Callout variant="danger" size="sm" className="mt-4" title="Invalid feed configuration">
            {formError}
          </Callout>
        ) : null}

        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="space-y-1">
            <div className="text-xs font-medium uppercase tracking-[0.14em] text-content-muted">Feed name</div>
            <Input
              value={draft.name}
              onChange={(event) => setDraftValue("name", event.target.value)}
              placeholder="Feed name"
            />
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium uppercase tracking-[0.14em] text-content-muted">Status</div>
            <Select
              value={draft.status}
              onValueChange={(value) => setDraftValue("status", value)}
              options={STATUS_OPTIONS.map((option) => ({ label: option.label, value: option.value }))}
            />
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium uppercase tracking-[0.14em] text-content-muted">Sort column</div>
            <Select
              value={draft.sortColumn}
              onValueChange={(value) => setDraftValue("sortColumn", value)}
              options={SORT_COLUMN_OPTIONS.map((option) => ({ label: option.label, value: option.value }))}
            />
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium uppercase tracking-[0.14em] text-content-muted">Sort direction</div>
            <Select
              value={draft.sortDirection}
              onValueChange={(value) => setDraftValue("sortDirection", value)}
              options={SORT_DIRECTION_OPTIONS.map((option) => ({ label: option.label, value: option.value }))}
            />
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium uppercase tracking-[0.14em] text-content-muted">Per page</div>
            <Input
              value={draft.perPage}
              onChange={(event) => setDraftValue("perPage", event.target.value)}
              type="number"
              min={1}
              max={100}
              placeholder="20"
            />
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium uppercase tracking-[0.14em] text-content-muted">Page cap</div>
            <Input
              value={draft.maxPagesPerRun}
              onChange={(event) => setDraftValue("maxPagesPerRun", event.target.value)}
              type="number"
              min={0}
              placeholder="0"
            />
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium uppercase tracking-[0.14em] text-content-muted">EU transparency</div>
            <Select
              value={draft.euTransparency}
              onValueChange={(value) => setDraftValue("euTransparency", value)}
              options={EU_TRANSPARENCY_OPTIONS.map((option) => ({
                label: option.label,
                value: option.value,
              }))}
            />
          </div>
          <label className="flex items-center gap-2 pt-6 text-sm text-content-muted">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(event) =>
                setDraft((current) => ({ ...current, enabled: event.target.checked }))
              }
            />
            Enabled
          </label>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {API_FILTER_FIELDS.map((field) => (
            <div key={field.key} className="space-y-1">
              <div className="text-xs font-medium uppercase tracking-[0.14em] text-content-muted">
                {field.label}
              </div>
              <Input
                value={draft[field.key]}
                onChange={(event) => setDraftValue(field.key, event.target.value)}
                placeholder={field.placeholder}
                type={field.type}
              />
            </div>
          ))}
        </div>

        <div className="mt-4 flex gap-2">
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
                setFormError(null);
              }}
            >
              Cancel
            </Button>
          ) : null}
        </div>

        <div className="mt-4 space-y-3">
          {feeds.map((feed) => {
            const filterSummary = summarizeFilters(feed.filters || {});
            return (
              <div key={feed.id} className="rounded-lg border border-border bg-surface-2 p-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-content">{feed.name}</div>
                    <div className="mt-1 text-xs text-content-muted">
                      {feed.maxPagesPerRun === 0
                        ? `All pages · ${feed.perPage} per page`
                        : `${feed.maxPagesPerRun} page cap · ${feed.perPage} per page`}
                    </div>
                    {filterSummary.length ? (
                      <div className="mt-2 space-y-1">
                        {filterSummary.map((entry) => (
                          <div key={entry} className="text-xs text-content-muted">
                            {entry}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="mt-2 text-xs text-content-muted">No API filters configured.</div>
                    )}
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
