import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MetaIntegrationPanel } from "./MetaIntegrationPanel";

const mockGet = vi.fn();
const mockCreateConnection = vi.fn();
const mockCreateWorkspaceConfig = vi.fn();
const mockGetActiveConfig = vi.fn();
const mockListPipelineAssets = vi.fn();
const mockListConnections = vi.fn();
const mockListWorkspaceConfigs = vi.fn();
const mockListRemoteImages = vi.fn();
const mockListRemoteVideos = vi.fn();
const mockListRemoteCreatives = vi.fn();
const mockListRemoteCampaigns = vi.fn();
const mockListRemoteAdSets = vi.fn();
const mockListRemoteAds = vi.fn();
const mockSelectWorkspaceConfig = vi.fn();
const mockUpdateConnection = vi.fn();
const mockValidateConnection = vi.fn();

vi.mock("@/api/client", () => ({
  useApiClient: () => ({
    get: mockGet,
  }),
}));

vi.mock("@/api/meta", () => ({
  useMetaApi: () => ({
    createConnection: mockCreateConnection,
    createWorkspaceConfig: mockCreateWorkspaceConfig,
    getActiveConfig: mockGetActiveConfig,
    listPipelineAssets: mockListPipelineAssets,
    listConnections: mockListConnections,
    listWorkspaceConfigs: mockListWorkspaceConfigs,
    listRemoteImages: mockListRemoteImages,
    listRemoteVideos: mockListRemoteVideos,
    listRemoteCreatives: mockListRemoteCreatives,
    listRemoteCampaigns: mockListRemoteCampaigns,
    listRemoteAdSets: mockListRemoteAdSets,
    listRemoteAds: mockListRemoteAds,
    selectWorkspaceConfig: mockSelectWorkspaceConfig,
    updateConnection: mockUpdateConnection,
    validateConnection: mockValidateConnection,
  }),
}));

vi.mock("@/api/experiments", () => ({
  useExperiments: () => ({ data: [] }),
}));

vi.mock("@/contexts/WorkspaceContext", () => ({
  useWorkspace: () => ({
    workspace: { id: "ws-1", name: "Workspace One" },
  }),
}));

vi.mock("@/contexts/ProductContext", () => ({
  useProductContext: () => ({
    product: { id: "product-1", title: "Product One", client_id: "ws-1" },
  }),
}));

function renderPanel(submitSpy?: () => void) {
  return render(
    <form onSubmit={submitSpy}>
      <MetaIntegrationPanel />
    </form>,
  );
}

describe("MetaIntegrationPanel", () => {
  beforeEach(() => {
    const connection = {
      id: "connection-1",
      orgId: "org-1",
      name: "Clement Capital",
      adAccountId: "act_1343458560825162",
      adAccountName: "Clement Capital",
      businessManagerId: null,
      businessManagerName: null,
      graphApiVersion: "v24.0",
      graphApiBaseUrl: "https://graph.facebook.com",
      credentialType: "access_token",
      hasCredentials: false,
      tokenExpiresAt: null,
      status: "active",
      validationStatus: "invalid",
      lastValidatedAt: null,
      lastValidationError: "Meta connection 'Clement Capital' is missing an access token. Update the connection credentials.",
      metadata: {},
      usedByWorkspaces: [],
      createdByUserId: null,
      createdAt: "2026-03-18T00:00:00Z",
      updatedAt: "2026-03-18T00:00:00Z",
    };

    mockGet.mockResolvedValue([]);
    mockCreateConnection.mockResolvedValue(connection);
    mockCreateWorkspaceConfig.mockResolvedValue(undefined);
    mockGetActiveConfig.mockRejectedValue(new Error("No active Meta config selected for this workspace"));
    mockListPipelineAssets.mockResolvedValue([]);
    mockListConnections.mockResolvedValue([connection]);
    mockListWorkspaceConfigs.mockResolvedValue([]);
    mockListRemoteImages.mockResolvedValue({ data: [] });
    mockListRemoteVideos.mockResolvedValue({ data: [] });
    mockListRemoteCreatives.mockResolvedValue({ data: [] });
    mockListRemoteCampaigns.mockResolvedValue({ data: [] });
    mockListRemoteAdSets.mockResolvedValue({ data: [] });
    mockListRemoteAds.mockResolvedValue({ data: [] });
    mockSelectWorkspaceConfig.mockResolvedValue(undefined);
    mockUpdateConnection.mockImplementation(async (_connectionId, payload) => ({
      ...connection,
      hasCredentials: true,
      tokenExpiresAt: payload.tokenExpiresAt ?? null,
    }));
    mockValidateConnection.mockResolvedValue(connection);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("updates missing Meta credentials without submitting an enclosing form", async () => {
    const user = userEvent.setup();
    const submitSpy = vi.fn((event: SubmitEvent) => event.preventDefault());

    renderPanel(submitSpy);

    await screen.findByText("Org-connected ad accounts");

    const tokenInput = await screen.findByPlaceholderText("Paste access token to reconnect");
    await user.type(tokenInput, "meta-access-token");
    await user.click(screen.getByRole("button", { name: "Save token" }));

    await waitFor(() => {
      expect(mockUpdateConnection).toHaveBeenCalledWith("connection-1", {
        name: "Clement Capital",
        adAccountId: "act_1343458560825162",
        adAccountName: "Clement Capital",
        businessManagerId: undefined,
        businessManagerName: undefined,
        graphApiVersion: "v24.0",
        graphApiBaseUrl: "https://graph.facebook.com",
        accessToken: "meta-access-token",
        tokenExpiresAt: undefined,
        status: "active",
        metadata: {},
      });
    });
    expect(submitSpy).not.toHaveBeenCalled();
  });
});
