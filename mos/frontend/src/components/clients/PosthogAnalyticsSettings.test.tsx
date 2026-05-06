import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PosthogAnalyticsSettings } from "./PosthogAnalyticsSettings";

const parseSnippetMock = vi.fn();
const saveSettingsMock = vi.fn();

const baseSettings = {
  hasSettings: true,
  enabled: true,
  projectApiKey: "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
  apiHost: "https://emb.shopemberco.com",
  uiHost: "https://us.posthog.com",
  defaults: "2026-01-30",
  personProfiles: "identified_only" as const,
  sourceMode: "structured" as const,
  sourceSnippet: null,
  resolvedTracking: {
    provider: "posthog" as const,
    mode: "public_funnel_runtime" as const,
    posthogProjectApiKey: "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
    posthogApiHost: "https://emb.shopemberco.com",
    posthogUiHost: "https://us.posthog.com",
    posthogDefaults: "2026-01-30",
    posthogPersonProfiles: "identified_only" as const,
  },
  createdAt: "2026-04-22T00:00:00Z",
  updatedAt: "2026-04-22T00:00:00Z",
};

vi.mock("@/api/clients", () => ({
  useClientPosthogSettings: () => ({ data: baseSettings, error: null }),
  useUpdateClientPosthogSettings: () => ({ mutateAsync: saveSettingsMock, isPending: false }),
  useParseClientPosthogSnippet: () => ({ mutateAsync: parseSnippetMock, isPending: false }),
}));

describe("PosthogAnalyticsSettings", () => {
  it("renders the workspace analytics sections", () => {
    render(<PosthogAnalyticsSettings clientId="client-1" />);

    expect(screen.getByText("Workspace analytics")).toBeInTheDocument();
    expect(screen.getByText("Import PostHog snippet")).toBeInTheDocument();
    expect(screen.getByText("Resolved runtime preview")).toBeInTheDocument();
    expect(screen.getByText("Preview behavior")).toBeInTheDocument();
  });

  it("parses a snippet and updates the canonical form fields", async () => {
    parseSnippetMock.mockResolvedValueOnce({
      ...baseSettings,
      sourceMode: "snippet",
      sourceSnippet: "<script>posthog.init(...)</script>",
      apiHost: "https://proxy.example.com",
      resolvedTracking: {
        ...baseSettings.resolvedTracking,
        posthogApiHost: "https://proxy.example.com",
      },
      updatedAt: "2026-04-22T01:00:00Z",
    });

    const user = userEvent.setup();
    render(<PosthogAnalyticsSettings clientId="client-1" />);

    fireEvent.change(screen.getByPlaceholderText("<script>posthog.init(...)</script>"), {
      target: {
        value: "<script>posthog.init('abc', { api_host: 'https://proxy.example.com' })</script>",
      },
    });
    await user.click(screen.getByText("Parse snippet"));

    await waitFor(() => {
      expect(parseSnippetMock).toHaveBeenCalledWith({
        snippet: "<script>posthog.init('abc', { api_host: 'https://proxy.example.com' })</script>",
      });
    });
    expect(screen.getByDisplayValue("https://proxy.example.com")).toBeInTheDocument();
    expect(screen.getByText(/proxy\.example\.com/)).toBeInTheDocument();
  });
});
