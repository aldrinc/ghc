import { useEffect, useMemo, useState } from "react";
import {
  useClientPostizChannels,
  useClientPostizConnectUrl,
  useClientPostizCredentials,
  useClientPostizPostingProfiles,
  useClientPostizPosts,
  usePrepareClientPostizLaunch,
  useCreateClientPostizPost,
  useCreateClientPostizPostingProfile,
  useDeleteClientPostizPost,
  useSyncClientPostizChannels,
  useSyncClientPostizPost,
  useUpdateClientPostizCredentials,
  useUpdateClientPostizPostingProfile,
  useValidateClientPostizCredentials,
} from "@/api/clients";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import type { PostizChannel, PostizPostingProfile } from "@/types/common";

const CONNECT_PROVIDERS = [
  "facebook",
  "instagram",
  "linkedin",
  "linkedin-page",
  "threads",
  "bluesky",
  "x",
  "youtube",
  "tiktok",
  "reddit",
  "pinterest",
  "wordpress",
  "medium",
  "discord",
  "slack",
].map((value) => ({ label: value, value }));

function getErrorMessage(err: unknown) {
  if (typeof err === "string") return err;
  if (err && typeof err === "object" && "message" in err) {
    return String((err as { message?: unknown }).message || "Request failed");
  }
  return "Request failed";
}

function parseJsonRecord(value: string): Record<string, unknown> {
  const trimmed = value.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("JSON must be an object.");
  }
  return parsed as Record<string, unknown>;
}

function prettyJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

function parseLines(value: string) {
  return value
    .split("\n")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function getPublicationStatusValue(status?: string | null) {
  return (status || "").trim().toUpperCase();
}

function getPublicationTone(status?: string | null) {
  const normalized = getPublicationStatusValue(status);
  if (normalized === "ERROR" || normalized === "FAILED") return "warning";
  if (normalized === "PUBLISHED") return "success";
  return "neutral";
}

function formatChannels(channels: PostizChannel[], selectedIds: string[], onToggle: (id: string) => void) {
  return (
    <div className="grid gap-2 md:grid-cols-2">
      {channels.map((channel) => {
        const checked = selectedIds.includes(channel.id);
        return (
          <label
            key={channel.id}
            className="flex items-start gap-3 rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm"
          >
            <input type="checkbox" checked={checked} onChange={() => onToggle(channel.id)} className="mt-1" />
            <span className="min-w-0 flex-1">
              <span className="block font-medium text-content">{channel.name}</span>
              <span className="block text-xs text-content-muted">
                {channel.identifier}
                {channel.profile ? ` · ${channel.profile}` : ""}
                {channel.disabled ? " · disabled" : ""}
              </span>
            </span>
          </label>
        );
      })}
    </div>
  );
}

export function PostizSettings({ clientId }: { clientId: string }) {
  const { data: credentials, error: credentialsError } = useClientPostizCredentials(clientId);
  const { data: channels = [], error: channelsError } = useClientPostizChannels(clientId);
  const { data: profiles = [] } = useClientPostizPostingProfiles(clientId);
  const { data: posts } = useClientPostizPosts(clientId);

  const saveCredentials = useUpdateClientPostizCredentials(clientId);
  const validateCredentials = useValidateClientPostizCredentials(clientId);
  const syncChannels = useSyncClientPostizChannels(clientId);
  const connectUrlMutation = useClientPostizConnectUrl(clientId);
  const prepareLaunch = usePrepareClientPostizLaunch(clientId);
  const createProfile = useCreateClientPostizPostingProfile(clientId);
  const updateProfile = useUpdateClientPostizPostingProfile(clientId);
  const createPost = useCreateClientPostizPost(clientId);
  const deletePost = useDeleteClientPostizPost(clientId);
  const syncPost = useSyncClientPostizPost(clientId);

  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [providerIdentifier, setProviderIdentifier] = useState(CONNECT_PROVIDERS[0]?.value || "instagram");
  const [connectUrl, setConnectUrl] = useState<string | null>(null);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [profileName, setProfileName] = useState("");
  const [profileTimezone, setProfileTimezone] = useState("UTC");
  const [profileShortLink, setProfileShortLink] = useState("false");
  const [profileIsDefault, setProfileIsDefault] = useState(true);
  const [profileChannelIds, setProfileChannelIds] = useState<string[]>([]);
  const [profileProviderSettings, setProfileProviderSettings] = useState("{}");
  const [profileError, setProfileError] = useState<string | null>(null);
  const [connectUrlError, setConnectUrlError] = useState<string | null>(null);

  const [publishProfileId, setPublishProfileId] = useState("");
  const [publishType, setPublishType] = useState<"now" | "schedule">("now");
  const [publishContent, setPublishContent] = useState("");
  const [publishScheduledFor, setPublishScheduledFor] = useState("");
  const [publishChannelIds, setPublishChannelIds] = useState<string[]>([]);
  const [publishMediaUrls, setPublishMediaUrls] = useState("");
  const [publishProviderSettings, setPublishProviderSettings] = useState("{}");
  const [publishError, setPublishError] = useState<string | null>(null);

  const defaultProfile = useMemo(() => profiles.find((profile) => profile.isDefault) || null, [profiles]);

  useEffect(() => {
    setBaseUrl(credentials?.baseUrl || "");
  }, [credentials?.baseUrl]);

  useEffect(() => {
    if (!defaultProfile) return;
    setPublishProfileId(defaultProfile.id);
    setPublishChannelIds(defaultProfile.defaultChannelIds || []);
    setPublishProviderSettings(prettyJson(defaultProfile.providerSettings));
  }, [defaultProfile?.id, defaultProfile?.updatedAt]);

  const handleToggleProfileChannel = (channelId: string) => {
    setProfileChannelIds((current) =>
      current.includes(channelId) ? current.filter((value) => value !== channelId) : [...current, channelId],
    );
  };

  const handleTogglePublishChannel = (channelId: string) => {
    setPublishChannelIds((current) =>
      current.includes(channelId) ? current.filter((value) => value !== channelId) : [...current, channelId],
    );
  };

  const resetProfileForm = () => {
    setProfileId(null);
    setProfileName("");
    setProfileTimezone("UTC");
    setProfileShortLink("false");
    setProfileIsDefault(true);
    setProfileChannelIds([]);
    setProfileProviderSettings("{}");
    setProfileError(null);
  };

  const loadProfile = (profile: PostizPostingProfile) => {
    setProfileId(profile.id);
    setProfileName(profile.name);
    setProfileTimezone(profile.timezone || "UTC");
    setProfileShortLink(String(Boolean(profile.shortLink)));
    setProfileIsDefault(profile.isDefault);
    setProfileChannelIds(profile.defaultChannelIds || []);
    setProfileProviderSettings(prettyJson(profile.providerSettings));
    setProfileError(null);
  };

  const applyProfileToPublish = (profileIdValue: string) => {
    setPublishProfileId(profileIdValue);
    const profile = profiles.find((entry) => entry.id === profileIdValue);
    if (!profile) return;
    setPublishChannelIds(profile.defaultChannelIds || []);
    setPublishProviderSettings(prettyJson(profile.providerSettings));
  };

  const handleSaveProfile = async () => {
    try {
      setProfileError(null);
      const payload = {
        name: profileName,
        timezone: profileTimezone || null,
        shortLink: profileShortLink === "true",
        isDefault: profileIsDefault,
        defaultChannelIds: profileChannelIds,
        providerSettings: parseJsonRecord(profileProviderSettings),
      };
      if (profileId) {
        await updateProfile.mutateAsync({ profileId, payload });
      } else {
        await createProfile.mutateAsync(payload);
      }
      resetProfileForm();
    } catch (error) {
      setProfileError(getErrorMessage(error));
    }
  };

  const handlePublish = async () => {
    try {
      setPublishError(null);
      await createPost.mutateAsync({
        content: publishContent,
        postType: publishType,
        scheduledFor: publishType === "schedule" && publishScheduledFor ? new Date(publishScheduledFor).toISOString() : null,
        channelIds: publishChannelIds,
        mediaUrls: parseLines(publishMediaUrls),
        postingProfileId: publishProfileId || null,
        providerSettingsByIdentifier: parseJsonRecord(publishProviderSettings),
      });
      setPublishContent("");
      setPublishScheduledFor("");
      setPublishMediaUrls("");
    } catch (error) {
      setPublishError(getErrorMessage(error));
    }
  };

  const handleOpenPostiz = async () => {
    try {
      const session = await prepareLaunch.mutateAsync();
      window.location.assign(session.launchUrl);
    } catch {
      // Error toast is handled in the mutation.
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-base font-semibold text-content">Postiz credentials</div>
            <div className="text-sm text-content-muted">
              Store the workspace-specific Postiz base URL and API key. MOS can sign you into the local Postiz UI and jump straight to Launches.
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={() => void handleOpenPostiz()} disabled={prepareLaunch.isPending}>
              Open Postiz
            </Button>
            <Badge tone={credentials?.hasCredentials ? "success" : "warning"}>
              {credentials?.hasCredentials ? "Configured" : "Not configured"}
            </Badge>
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto]">
          <Input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="http://localhost:4007/api" />
          <Input value={apiKey} onChange={(event) => setApiKey(event.target.value)} type="password" placeholder="Paste Postiz API key" />
          <Button onClick={() => saveCredentials.mutate({ baseUrl, apiKey })} disabled={!baseUrl.trim() || !apiKey.trim() || saveCredentials.isPending}>
            Save
          </Button>
          <Button variant="secondary" onClick={() => validateCredentials.mutate()} disabled={!credentials?.hasCredentials || validateCredentials.isPending}>
            Validate
          </Button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-content-muted">
          <span>Auth type: {credentials?.authType || "api_key"}</span>
          {credentials?.lastValidatedAt ? <span>Last validated {new Date(credentials.lastValidatedAt).toLocaleString()}</span> : null}
        </div>
        {credentials?.lastValidationError ? (
          <Callout variant="danger" size="sm" className="mt-3" title="Validation error">
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
            <div className="text-base font-semibold text-content">Channels</div>
            <div className="text-sm text-content-muted">Sync connected Postiz channels, then use posting profiles to define defaults.</div>
          </div>
          <div className="flex gap-2">
            <Badge tone="neutral">{channels.length} synced</Badge>
            <Button variant="secondary" onClick={() => syncChannels.mutate()} disabled={syncChannels.isPending || !credentials?.hasCredentials}>
              Sync channels
            </Button>
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-[220px_auto]">
          <Select value={providerIdentifier} onValueChange={setProviderIdentifier} options={CONNECT_PROVIDERS} />
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              onClick={async () => {
                try {
                  setConnectUrlError(null);
                  const result = await connectUrlMutation.mutateAsync(providerIdentifier);
                  setConnectUrl(result.connectUrl);
                } catch (error) {
                  setConnectUrlError(getErrorMessage(error));
                }
              }}
              disabled={!credentials?.hasCredentials || connectUrlMutation.isPending}
            >
              Generate connect URL
            </Button>
            {connectUrl ? (
              <>
                <Button variant="secondary" onClick={() => window.open(connectUrl, "_blank", "noopener,noreferrer")}>
                  Open URL
                </Button>
                <Button variant="ghost" onClick={() => navigator.clipboard.writeText(connectUrl)}>
                  Copy URL
                </Button>
              </>
            ) : null}
          </div>
        </div>
        <div className="mt-3 text-xs text-content-muted">
          Use this to start the OAuth flow in Postiz, then resync channels after the provider callback finishes inside Postiz.
        </div>
        {connectUrlError ? (
          <Callout variant="danger" size="sm" className="mt-3" title="Connect URL failed">
            {connectUrlError}
          </Callout>
        ) : null}
        <div className="mt-4 space-y-3">
          {channels.map((channel) => (
            <div key={channel.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface-2 px-3 py-2">
              <div>
                <div className="text-sm font-medium text-content">{channel.name}</div>
                <div className="text-xs text-content-muted">
                  {channel.identifier}
                  {channel.profile ? ` · ${channel.profile}` : ""}
                  {channel.lastSyncedAt ? ` · synced ${new Date(channel.lastSyncedAt).toLocaleString()}` : ""}
                </div>
              </div>
              <div className="flex gap-2">
                <Badge tone={channel.disabled ? "warning" : "success"}>{channel.disabled ? "Disabled" : "Ready"}</Badge>
                {channel.isDefault ? <Badge tone="neutral">Profile default</Badge> : null}
              </div>
            </div>
          ))}
          {!channels.length ? <div className="text-sm text-content-muted">No Postiz channels synced yet.</div> : null}
        </div>
        {channelsError ? (
          <Callout variant="danger" size="sm" className="mt-3" title="Failed to load channels">
            {getErrorMessage(channelsError)}
          </Callout>
        ) : null}
      </div>

      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-base font-semibold text-content">Posting profiles</div>
            <div className="text-sm text-content-muted">Save reusable timezone, short-link, channel, and provider-settings defaults.</div>
          </div>
          <Badge tone="neutral">{profiles.length} profiles</Badge>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <Input value={profileName} onChange={(event) => setProfileName(event.target.value)} placeholder="Profile name" />
          <Input value={profileTimezone} onChange={(event) => setProfileTimezone(event.target.value)} placeholder="Timezone (e.g. UTC, America/New_York)" />
          <Select value={profileShortLink} onValueChange={setProfileShortLink} options={[{ label: "Short links off", value: "false" }, { label: "Short links on", value: "true" }]} />
          <label className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-content-muted">
            <input type="checkbox" checked={profileIsDefault} onChange={(event) => setProfileIsDefault(event.target.checked)} />
            Make this the default posting profile
          </label>
          <div className="rounded-md border border-dashed border-border px-3 py-2 text-xs text-content-muted">
            Some providers require extra JSON. Store it here once per profile and reuse it in the publish composer.
          </div>
        </div>
        <div className="mt-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Default channels</div>
          {formatChannels(channels, profileChannelIds, handleToggleProfileChannel)}
        </div>
        <div className="mt-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Provider settings JSON</div>
          <Textarea value={profileProviderSettings} onChange={(event) => setProfileProviderSettings(event.target.value)} rows={8} placeholder='{"instagram":{"__type":"instagram","post_type":"post","collaborators":[]}}' />
        </div>
        {profileError ? (
          <Callout variant="danger" size="sm" className="mt-3" title="Invalid profile input">
            {profileError}
          </Callout>
        ) : null}
        <div className="mt-4 flex gap-2">
          <Button onClick={() => void handleSaveProfile()} disabled={!profileName.trim() || createProfile.isPending || updateProfile.isPending}>
            {profileId ? "Update profile" : "Create profile"}
          </Button>
          {profileId ? (
            <Button variant="secondary" onClick={resetProfileForm}>
              Cancel edit
            </Button>
          ) : null}
        </div>
        <div className="mt-4 space-y-3">
          {profiles.map((profile) => (
            <div key={profile.id} className="rounded-lg border border-border bg-surface-2 p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-content">{profile.name}</div>
                  <div className="mt-1 text-xs text-content-muted">
                    {profile.timezone || "No timezone"} · shortLink {String(Boolean(profile.shortLink))} · {profile.defaultChannelIds.length} default channels
                  </div>
                </div>
                <div className="flex gap-2">
                  {profile.isDefault ? <Badge tone="success">Default</Badge> : null}
                  <Button size="sm" variant="secondary" onClick={() => loadProfile(profile)}>
                    Edit
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => applyProfileToPublish(profile.id)}>
                    Use in composer
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-base font-semibold text-content">Publish now or schedule once</div>
            <div className="text-sm text-content-muted">Manual composer for direct Postiz publishing. Channels that need provider JSON will fail cleanly until you supply it.</div>
          </div>
          <Badge tone={publishType === "schedule" ? "warning" : "success"}>{publishType === "schedule" ? "Scheduled" : "Publish now"}</Badge>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <Select value={publishType} onValueChange={(value) => setPublishType(value as "now" | "schedule")} options={[{ label: "Publish now", value: "now" }, { label: "Schedule once", value: "schedule" }]} />
          <Select
            value={publishProfileId}
            onValueChange={applyProfileToPublish}
            options={[{ label: "No profile", value: "" }, ...profiles.map((profile) => ({ label: profile.name, value: profile.id }))]}
          />
          <Input value={publishScheduledFor} onChange={(event) => setPublishScheduledFor(event.target.value)} type="datetime-local" disabled={publishType !== "schedule"} />
        </div>
        <div className="mt-4">
          <Textarea value={publishContent} onChange={(event) => setPublishContent(event.target.value)} rows={5} placeholder="Write the social post copy here." />
        </div>
        <div className="mt-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Target channels</div>
          {formatChannels(channels, publishChannelIds, handleTogglePublishChannel)}
        </div>
        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Media URLs</div>
            <Textarea value={publishMediaUrls} onChange={(event) => setPublishMediaUrls(event.target.value)} rows={6} placeholder={"https://cdn.example.com/image-1.png\nhttps://cdn.example.com/image-2.png"} />
          </div>
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">Provider settings JSON</div>
            <Textarea value={publishProviderSettings} onChange={(event) => setPublishProviderSettings(event.target.value)} rows={6} placeholder='{"x":{"__type":"x","who_can_reply_post":"everyone"}}' />
            <div className="mt-2 text-xs text-content-muted">
              Key this object by provider identifier, not channel id. Put provider-specific link fields here too. Example: <code>instagram</code>, <code>x</code>, <code>linkedin-page</code>.
            </div>
          </div>
        </div>
        {publishError ? (
          <Callout variant="danger" size="sm" className="mt-3" title="Publish request failed">
            {publishError}
          </Callout>
        ) : null}
        <div className="mt-4 flex gap-2">
          <Button onClick={() => void handlePublish()} disabled={!publishContent.trim() || !publishChannelIds.length || createPost.isPending || (publishType === "schedule" && !publishScheduledFor)}>
            {publishType === "schedule" ? "Schedule post" : "Publish post"}
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              setPublishContent("");
              setPublishScheduledFor("");
              setPublishMediaUrls("");
              setPublishProviderSettings(defaultProfile ? prettyJson(defaultProfile.providerSettings) : "{}");
              setPublishChannelIds(defaultProfile?.defaultChannelIds || []);
            }}
          >
            Reset
          </Button>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-base font-semibold text-content">Recent publication history</div>
            <div className="text-sm text-content-muted">MOS stores submission history and lets you resync the latest Postiz state on demand.</div>
          </div>
          <Badge tone="neutral">{posts?.total || 0} records</Badge>
        </div>
        <div className="mt-4 overflow-hidden">
          <Table variant="ghost">
            <TableHeader>
              <TableRow>
                <TableHeadCell>Status</TableHeadCell>
                <TableHeadCell>Mode</TableHeadCell>
                <TableHeadCell>Content</TableHeadCell>
                <TableHeadCell>Updated</TableHeadCell>
                <TableHeadCell>Actions</TableHeadCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(posts?.posts || []).map((post) => (
                <TableRow key={post.id}>
                  <TableCell>
                    <Badge tone={getPublicationTone(post.postizPostStatus || post.status)}>
                      {post.postizPostStatus || post.status}
                    </Badge>
                    {post.postizPostStatus && getPublicationStatusValue(post.postizPostStatus) !== getPublicationStatusValue(post.status) ? (
                      <div className="mt-1 text-xs text-content-muted">MOS record: {post.status}</div>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-content-muted">{post.postType}</TableCell>
                  <TableCell>
                    <div className="max-w-[420px] truncate text-sm text-content">{post.content}</div>
                    {post.releaseUrls?.length
                      ? post.releaseUrls.map((releaseUrl, index) => (
                          <a
                            key={releaseUrl}
                            href={releaseUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="block text-xs text-brand underline-offset-2 hover:underline"
                          >
                            {post.releaseUrls.length > 1 ? `Open release URL ${index + 1}` : "Open release URL"}
                          </a>
                        ))
                      : null}
                  </TableCell>
                  <TableCell className="text-xs text-content-muted">{new Date(post.updatedAt).toLocaleString()}</TableCell>
                  <TableCell>
                    <div className="flex gap-2">
                      <Button size="sm" variant="secondary" onClick={() => syncPost.mutate(post.id)}>
                        Sync
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => deletePost.mutate(post.id)}>
                        Delete
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {!posts?.posts?.length ? (
                <TableRow>
                  <TableCell colSpan={5} className="px-3 py-3 text-sm text-content-muted">
                    No Postiz publications yet.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
