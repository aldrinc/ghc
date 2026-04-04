import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PostizSettings } from "./PostizSettings";

const postizCredentials = {
  hasCredentials: true,
  baseUrl: "https://postiz.example.com",
  authType: "api_key",
};

const postizChannels = [
  {
    id: "channel-1",
    postizIntegrationId: "int-1",
    postizChannelId: "int-1",
    identifier: "instagram",
    name: "Instagram",
    profile: "acme",
    pictureUrl: null,
    disabled: false,
    isDefault: false,
    metadata: {},
    lastSyncedAt: null,
    createdAt: "2026-03-26T00:00:00Z",
    updatedAt: "2026-03-26T00:00:00Z",
  },
];

const postizProfiles = [
  {
    id: "profile-1",
    name: "Default",
    isDefault: true,
    defaultChannelIds: ["channel-1"],
    timezone: "UTC",
    shortLink: false,
    providerSettings: {},
    postizPostingProfileId: null,
    metadata: {},
    createdAt: "2026-03-26T00:00:00Z",
    updatedAt: "2026-03-26T00:00:00Z",
  },
];

const postizPosts = {
  posts: [
    {
      id: "publication-1",
      postizPostId: "post-1",
      postizPostIds: ["post-1", "post-2"],
      content: "Queued social post",
      postType: "schedule",
      scheduledFor: "2026-03-27T10:00:00Z",
      targetChannels: { channel_ids: ["channel-1"] },
      mediaUrls: [],
      linkUrl: null,
      status: "scheduled",
      postizPostStatus: "QUEUE",
      releaseUrls: ["https://example.com/post/1", "https://example.com/post/2"],
      errorPayload: null,
      lastSyncedAt: "2026-03-26T00:00:00Z",
      createdAt: "2026-03-26T00:00:00Z",
      updatedAt: "2026-03-26T00:00:00Z",
    },
  ],
  total: 1,
};

vi.mock("@/api/clients", () => ({
  useClientPostizCredentials: () => ({ data: postizCredentials, error: null }),
  useClientPostizChannels: () => ({ data: postizChannels, error: null }),
  useClientPostizPostingProfiles: () => ({ data: postizProfiles }),
  useClientPostizPosts: () => ({ data: postizPosts }),
  useUpdateClientPostizCredentials: () => ({ mutate: vi.fn(), isPending: false }),
  useValidateClientPostizCredentials: () => ({ mutate: vi.fn(), isPending: false }),
  useSyncClientPostizChannels: () => ({ mutate: vi.fn(), isPending: false }),
  useClientPostizConnectUrl: () => ({ mutateAsync: vi.fn().mockResolvedValue({ connectUrl: "https://postiz.example.com/oauth" }), isPending: false }),
  usePrepareClientPostizLaunch: () => ({ mutateAsync: vi.fn().mockResolvedValue({ launchUrl: "https://postiz.example.com/launches", autoConfiguredCredentials: false }), isPending: false }),
  useCreateClientPostizPostingProfile: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateClientPostizPostingProfile: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateClientPostizPost: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteClientPostizPost: () => ({ mutate: vi.fn() }),
  useSyncClientPostizPost: () => ({ mutate: vi.fn() }),
}));

describe("PostizSettings", () => {
  it("renders the main Postiz sections", () => {
    render(<PostizSettings clientId="client-1" />);

    expect(screen.getByText("Postiz credentials")).toBeInTheDocument();
    expect(screen.getByText("Open Postiz")).toBeInTheDocument();
    expect(screen.getByText("Channels")).toBeInTheDocument();
    expect(screen.getByText("Posting profiles")).toBeInTheDocument();
    expect(screen.getByText("Publish now or schedule once")).toBeInTheDocument();
    expect(screen.getByText("Recent publication history")).toBeInTheDocument();
    expect(screen.getByText("QUEUE")).toBeInTheDocument();
    expect(screen.getByText("Open release URL 2")).toBeInTheDocument();
  });
});
