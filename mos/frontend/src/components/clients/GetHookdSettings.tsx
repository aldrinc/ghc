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
import type { GetHookdSyncFeed } from "@/types/common";

function getErrorMessage(err: unknown) {
  if (typeof err === "string") return err;
  if (err && typeof err === "object" && "message" in err) {
    return String((err as { message?: unknown }).message || "Request failed");
  }
  return "Request failed";
}

type FeedDraft = {
  name: string;
  query: string;
  maxPagesPerRun: string;
  perPage: string;
  enabled: boolean;
};

const EMPTY_DRAFT: FeedDraft = {
  name: "",
  query: "",
  maxPagesPerRun: "5",
  perPage: "100",
  enabled: true,
};

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
      filters: { query: draft.query },
      maxPagesPerRun: Number(draft.maxPagesPerRun || 5),
      perPage: Number(draft.perPage || 100),
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
    setDraft({
      name: feed.name,
      query: String(feed.filters?.query || ""),
      maxPagesPerRun: String(feed.maxPagesPerRun || 5),
      perPage: String(feed.perPage || 100),
      enabled: feed.enabled,
    });
  };

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-base font-semibold text-content">GetHookd credentials</div>
            <div className="text-sm text-content-muted">Store the workspace token used by nightly GetHookd sync.</div>
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
          <Button onClick={() => updateCredentials.mutate({ apiToken: token })} disabled={!token.trim() || updateCredentials.isPending}>
            Save token
          </Button>
        </div>
        {credentials?.lastValidatedAt ? (
          <div className="mt-2 text-xs text-content-muted">Last validated {new Date(credentials.lastValidatedAt).toLocaleString()}</div>
        ) : null}
        {credentials?.lastValidationError ? (
          <Callout variant="danger" size="sm" className="mt-3" title="Credential validation failed">
            {credentials.lastValidationError}
          </Callout>
        ) : null}
        {credentialsError ? (
          <Callout variant="danger" size="sm" className="mt-3" title="Failed to load credentials">
            {getErrorMessage(credentialsError)}
          </Callout>
        ) : null}
      </div>

      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-base font-semibold text-content">GetHookd sync feeds</div>
            <div className="text-sm text-content-muted">Define the bounded Explore searches used during nightly sync.</div>
          </div>
          <div className="flex gap-2">
            <Badge tone="neutral">{feeds.length} feeds</Badge>
            <Badge tone="success">{activeFeedCount} active</Badge>
          </div>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <Input value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} placeholder="Feed name" />
          <Input value={draft.query} onChange={(event) => setDraft((current) => ({ ...current, query: event.target.value }))} placeholder="Explore query" />
          <Input value={draft.maxPagesPerRun} onChange={(event) => setDraft((current) => ({ ...current, maxPagesPerRun: event.target.value }))} placeholder="Max pages" />
          <Input value={draft.perPage} onChange={(event) => setDraft((current) => ({ ...current, perPage: event.target.value }))} placeholder="Per page" />
          <label className="flex items-center gap-2 text-sm text-content-muted">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(event) => setDraft((current) => ({ ...current, enabled: event.target.checked }))}
            />
            Enabled
          </label>
        </div>
        <div className="mt-3 flex gap-2">
          <Button onClick={() => void handleSaveFeed()} disabled={!draft.name.trim() || createFeed.isPending || updateFeed.isPending}>
            {editingFeedId ? "Update feed" : "Create feed"}
          </Button>
          {editingFeedId ? (
            <Button variant="secondary" onClick={() => { setEditingFeedId(null); setDraft(EMPTY_DRAFT); }}>
              Cancel
            </Button>
          ) : null}
        </div>

        <div className="mt-4 space-y-3">
          {feeds.map((feed) => (
            <div key={feed.id} className="rounded-lg border border-border bg-surface-2 p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-content">{feed.name}</div>
                  <div className="mt-1 text-xs text-content-muted">Query: {String(feed.filters?.query || "—")}</div>
                  <div className="mt-1 text-xs text-content-muted">{feed.maxPagesPerRun} pages · {feed.perPage} per page</div>
                </div>
                <div className="flex gap-2">
                  <Badge tone={feed.enabled ? "success" : "neutral"}>{feed.enabled ? "Enabled" : "Disabled"}</Badge>
                  <Button size="sm" variant="secondary" onClick={() => handleEditFeed(feed)}>Edit</Button>
                  <Button size="sm" variant="secondary" onClick={() => updateFeed.mutate({ feedId: feed.id, payload: { enabled: !feed.enabled } })}>
                    {feed.enabled ? "Disable" : "Enable"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => deleteFeed.mutate(feed.id)}>Delete</Button>
                </div>
              </div>
            </div>
          ))}
          {!feeds.length ? <div className="text-sm text-content-muted">No sync feeds configured yet.</div> : null}
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
