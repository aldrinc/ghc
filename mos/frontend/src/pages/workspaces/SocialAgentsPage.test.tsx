import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SocialAgentsPage } from "./SocialAgentsPage";

const mocks = vi.hoisted(() => ({
  workspace: { id: "client-1", name: "Acme" } as { id: string; name: string } | null,
  createProgram: vi.fn(),
  createConversionSource: vi.fn(),
  createExperiment: vi.fn(),
  createVariant: vi.fn(),
  approveVariant: vi.fn(),
  createHandoff: vi.fn(),
  approveProposal: vi.fn(),
  apiPost: vi.fn(),
  postizChannels: [] as Record<string, unknown>[],
  postizProfiles: [] as Record<string, unknown>[],
  programs: [] as Record<string, unknown>[],
  conversionSources: [] as Record<string, unknown>[],
  experiments: [] as Record<string, unknown>[],
  variants: [] as Record<string, unknown>[],
  providerAssets: [] as Record<string, unknown>[],
  proposals: [] as Record<string, unknown>[],
}));

vi.mock("@/contexts/WorkspaceContext", () => ({
  useWorkspace: () => ({
    workspace: mocks.workspace,
    clients: mocks.workspace ? [mocks.workspace] : [],
    selectWorkspace: vi.fn(),
    isLoading: false,
  }),
}));

vi.mock("@/api/clients", () => ({
  useClientPostizChannels: () => ({
    data: mocks.postizChannels,
  }),
  useClientPostizPostingProfiles: () => ({
    data: mocks.postizProfiles,
  }),
}));

vi.mock("@/api/client", () => ({
  useApiClient: () => ({
    post: mocks.apiPost,
  }),
}));

vi.mock("@/api/socialAgents", () => ({
  useGrowthPrograms: () => ({
    data: mocks.programs,
  }),
  useConversionSources: () => ({ data: mocks.conversionSources }),
  useContentExperiments: () => ({
    data: mocks.experiments,
  }),
  useContentVariants: () => ({
    data: mocks.variants,
  }),
  useSocialProviderAssets: () => ({
    data: mocks.providerAssets,
  }),
  useAgentActionProposals: () => ({
    data: mocks.proposals,
  }),
  useCreateGrowthProgram: () => ({ mutateAsync: mocks.createProgram, isPending: false }),
  useCreateConversionSource: () => ({ mutateAsync: mocks.createConversionSource, isPending: false }),
  useCreateContentExperiment: () => ({ mutateAsync: mocks.createExperiment, isPending: false }),
  useCreateContentVariant: () => ({ mutateAsync: mocks.createVariant, isPending: false }),
  useApproveContentVariant: () => ({ mutateAsync: mocks.approveVariant, isPending: false }),
  useCreatePostizHandoffProposal: () => ({ mutateAsync: mocks.createHandoff, isPending: false }),
  useApproveAgentActionProposal: () => ({ mutateAsync: mocks.approveProposal, isPending: false }),
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/workspaces/execution/social-agents"]}>
      <SocialAgentsPage />
    </MemoryRouter>,
  );
}

describe("SocialAgentsPage", () => {
  beforeEach(() => {
    mocks.workspace = { id: "client-1", name: "Acme" };
    mocks.postizChannels = [
      {
        id: "channel-1",
        postizIntegrationId: "integration-1",
        postizChannelId: "postiz-channel-1",
        identifier: "tiktok-acme",
        name: "Acme TikTok",
        disabled: false,
        isDefault: true,
        metadata: {},
        createdAt: "2026-05-22T00:00:00Z",
        updatedAt: "2026-05-22T00:00:00Z",
      },
    ];
    mocks.postizProfiles = [
      {
        id: "profile-1",
        name: "Default profile",
        isDefault: true,
        defaultChannelIds: ["channel-1"],
        providerSettings: {},
        metadata: {},
        createdAt: "2026-05-22T00:00:00Z",
        updatedAt: "2026-05-22T00:00:00Z",
      },
    ];
    mocks.programs = [
      {
        id: "program-1",
        name: "TikTok Carousel Growth Loop",
        objective: "Find carousel hooks that create source-backed conversions.",
        platformKey: "tiktok",
        formatKey: "tiktok_carousel",
        authorityMode: "approval_required",
        status: "active",
        settings: {},
        metadata: {},
        createdAt: "2026-05-22T00:00:00Z",
        updatedAt: "2026-05-22T00:00:00Z",
      },
    ];
    mocks.conversionSources = [];
    mocks.experiments = [
      {
        id: "experiment-1",
        growthProgramId: "program-1",
        name: "Hook test batch",
        hypothesis: "Problem-aware hooks win.",
        status: "active",
        metadata: {},
        createdAt: "2026-05-22T00:00:00Z",
        updatedAt: "2026-05-22T00:00:00Z",
      },
    ];
    mocks.variants = [
      {
        id: "variant-1",
        growthProgramId: "program-1",
        experimentId: "experiment-1",
        platformKey: "tiktok",
        formatKey: "tiktok_carousel",
        title: "Problem-aware carousel",
        caption: "A practical carousel draft for Postiz review.",
        cta: "Try the app",
        slideCount: 6,
        status: "approved",
        storyboard: {},
        providerPayload: {},
        metadata: {},
        slides: [
          "The real problem is not motivation",
          "Your workflow leaks attention",
          "Small misses compound fast",
          "The fix starts with a cleaner loop",
          "Track the signal, not the noise",
          "Try it this week",
        ].map((overlayText, index) => ({
          id: `slide-${index + 1}`,
          slideIndex: index + 1,
          overlayText,
          renderStatus: "draft",
          metadata: {},
          createdAt: "2026-05-22T00:00:00Z",
          updatedAt: "2026-05-22T00:00:00Z",
        })),
        createdAt: "2026-05-22T00:00:00Z",
        updatedAt: "2026-05-22T00:00:00Z",
      },
    ];
    mocks.providerAssets = [
      {
        id: "asset-1",
        provider: "tiktok",
        providerAssetId: "acct-1",
        assetType: "account",
        displayName: "Acme TikTok",
        capabilityFlags: ["publish"],
        status: "active",
        metadata: {},
        createdAt: "2026-05-22T00:00:00Z",
        updatedAt: "2026-05-22T00:00:00Z",
      },
    ];
    mocks.proposals = [
      {
        id: "proposal-1",
        actionType: "postiz_handoff",
        targetProvider: "postiz",
        targetAssetId: "variant-1",
        targetAssetType: "post",
        beforeSnapshot: {},
        proposedAfter: {},
        riskLabel: "low",
        status: "pending",
        rollbackHint: {},
        metadata: {},
        createdAt: "2026-05-22T00:00:00Z",
        updatedAt: "2026-05-22T00:00:00Z",
      },
    ];
    mocks.createProgram.mockResolvedValue({ id: "program-2" });
    mocks.createConversionSource.mockResolvedValue({ id: "source-1" });
    mocks.createExperiment.mockResolvedValue({ id: "experiment-2" });
    mocks.createVariant.mockResolvedValue({ id: "variant-2" });
    mocks.approveVariant.mockResolvedValue({ id: "variant-1", status: "approved" });
    mocks.createHandoff.mockResolvedValue({ proposalId: "proposal-2" });
    mocks.approveProposal.mockResolvedValue({ id: "proposal-1", status: "approved" });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the simplified Marketing Agent workbench", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "Marketing Agent" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Set mission" })).toBeInTheDocument();
    expect(screen.getByText("Postiz ready")).toBeInTheDocument();
    expect(screen.getAllByText("TikTok Carousel Growth Loop").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Setup screen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review screen" })).toBeInTheDocument();
    expect(screen.getByText("TikTok carousel")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Choose Program" })).not.toBeInTheDocument();
  });

  it("creates a Postiz handoff proposal instead of publishing directly", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Review screen" }));
    expect(screen.getByRole("button", { name: /Add assets/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Add assets/i }));

    await user.type(
      screen.getByLabelText("Carousel media URLs"),
      [
        "https://cdn.example.test/slide-1.png",
        "https://cdn.example.test/slide-2.png",
        "https://cdn.example.test/slide-3.png",
        "https://cdn.example.test/slide-4.png",
        "https://cdn.example.test/slide-5.png",
        "https://cdn.example.test/slide-6.png",
      ].join("\n"),
    );
    const handoffButton = screen.getByRole("button", { name: /Send to Postiz/i });
    await user.click(handoffButton);

    await waitFor(() => {
      expect(mocks.createHandoff).toHaveBeenCalledWith({
        variantId: "variant-1",
        payload: expect.objectContaining({
          content: expect.stringContaining("POV: your routine looks calm"),
          postType: "draft",
          channelIds: ["channel-1"],
          mediaUrls: [
            "https://cdn.example.test/slide-1.png",
            "https://cdn.example.test/slide-2.png",
            "https://cdn.example.test/slide-3.png",
            "https://cdn.example.test/slide-4.png",
            "https://cdn.example.test/slide-5.png",
            "https://cdn.example.test/slide-6.png",
          ],
          providerSettingsByIdentifier: {},
        }),
      });
    });
  });

  it("requires six source images before rendering PNG assets", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Review screen" }));
    const renderButton = screen.getByRole("button", { name: "Render" });
    expect(renderButton).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Media" }));

    await user.type(
      screen.getByLabelText("Source image URLs"),
      [
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E",
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E",
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E",
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E",
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E",
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E",
      ].join("\n"),
    );

    expect(renderButton).toBeEnabled();
  });

  it("keeps the no-mission state focused on setup", () => {
    mocks.programs = [];
    mocks.experiments = [];
    mocks.variants = [];

    renderPage();

    expect(screen.getByRole("heading", { name: "Set mission" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
    expect(screen.getByText("Set the mission.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add Conversion Source step" })).not.toBeInTheDocument();
  });

  it("keeps Postiz handoff disabled until the selected variant is approved", async () => {
    const user = userEvent.setup();
    mocks.variants = [{ ...mocks.variants[0], status: "draft" }];
    renderPage();

    await user.click(screen.getByRole("button", { name: "Review screen" }));
    await user.click(screen.getByRole("button", { name: "Media" }));
    await user.type(
      screen.getByLabelText("Carousel media URLs"),
      [
        "https://cdn.example.test/slide-1.png",
        "https://cdn.example.test/slide-2.png",
        "https://cdn.example.test/slide-3.png",
        "https://cdn.example.test/slide-4.png",
        "https://cdn.example.test/slide-5.png",
        "https://cdn.example.test/slide-6.png",
      ].join("\n"),
    );

    expect(screen.getByRole("button", { name: /Approve draft/i })).toBeEnabled();
    expect(screen.queryByRole("button", { name: /Send to Postiz/i })).not.toBeInTheDocument();
  });

  it("keeps review visual-first with slide cards and collapsed editor fields", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Review screen" }));

    expect(screen.getAllByTestId("slide-preview-card")).toHaveLength(6);
    expect(screen.queryByLabelText("Source image URLs")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Carousel media URLs")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit slide 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add asset for slide 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Regenerate slide 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Add assets/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Media" }));

    expect(screen.getByLabelText("Source image URLs")).toBeInTheDocument();
    expect(screen.getByLabelText("Carousel media URLs")).toBeInTheDocument();
  });

  it("keeps agent proposals behind the action queue approval gate", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /Approvals/i }));

    const queuePanel = screen.getByRole("heading", { name: "Action Queue" }).closest("section");
    expect(queuePanel).not.toBeNull();
    expect(within(queuePanel as HTMLElement).getByText("postiz_handoff")).toBeInTheDocument();

    await user.click(within(queuePanel as HTMLElement).getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(mocks.approveProposal).toHaveBeenCalledWith({
        proposalId: "proposal-1",
        notes: "Approved from Social Agents action queue",
      });
    });
  });

  it("renders an empty state without a workspace", () => {
    mocks.workspace = null;

    renderPage();

    expect(screen.getByText("No workspace selected")).toBeInTheDocument();
    expect(screen.getByText("Choose a workspace to open the agent workbench.")).toBeInTheDocument();
  });
});
