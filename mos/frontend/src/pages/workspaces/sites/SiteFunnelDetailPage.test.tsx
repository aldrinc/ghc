import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { SiteFunnelDetailPage } from "./SiteFunnelDetailPage";

const mockPrepareSiteFunnel = vi.fn();
const mockPublishSite = vi.fn();

vi.mock("@/contexts/WorkspaceContext", () => ({
  useWorkspace: () => ({
    workspace: { id: "workspace-1", name: "Acme" },
  }),
}));

vi.mock("@/api/sites", () => ({
  useSite: () => ({
    data: {
      id: "site-1",
      name: "Acme Site",
      pages: [],
    },
    isLoading: false,
  }),
  usePublishSite: () => ({
    mutateAsync: mockPublishSite,
    isPending: false,
  }),
}));

vi.mock("@/api/siteFunnels", () => ({
  useSiteFunnel: () => ({
    data: {
      id: "funnel-1",
      siteId: "site-1",
      name: "EMBER Sales Funnel",
      description: "Imported funnel",
      status: "draft",
      funnelType: "html_template",
      entryPageId: null,
      productId: "product-1",
      selectedOfferId: null,
      templateImportId: "template-import-1",
      templateImportLabel: "EMBER Sales HTML",
      pageIntent: "sales",
      campaignId: "campaign-1",
      selectedAngleId: "angle-1",
      preparedPageId: "page-1",
      preparedPageSlug: "ember-sales-funnel-sales-page",
      latestPreparedVersionId: "version-1",
      preparationReadiness: {
        status: "prepared",
        selectedAngleName: "Focus Restored",
        copy: { ready: true, required: true, source: "generated_for_selected_angle" },
        navigation: { ready: true },
        checkout: { ready: true },
        tracking: { ready: false, required: true },
      },
      preparedAt: "2026-04-08T20:00:00Z",
      trackingConfig: null,
      steps: [],
      createdAt: "2026-04-08T20:00:00Z",
      updatedAt: "2026-04-08T20:00:00Z",
    },
    isLoading: false,
  }),
  useUpdateSiteFunnel: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateSiteFunnelStep: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteSiteFunnelStep: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePrepareSiteFunnel: () => ({
    mutateAsync: mockPrepareSiteFunnel,
    isPending: false,
  }),
}));

describe("SiteFunnelDetailPage", () => {
  beforeEach(() => {
    mockPrepareSiteFunnel.mockReset();
    mockPrepareSiteFunnel.mockResolvedValue({});
    mockPublishSite.mockReset();
    mockPublishSite.mockResolvedValue({ routeSlug: "acme-site" });
  });

  it("shows preparation state and triggers prepare", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={["/workspaces/sites/site-1/funnels/funnel-1"]}>
        <Routes>
          <Route path="/workspaces/sites/:siteId/funnels/:funnelId" element={<SiteFunnelDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Template Preparation")).toBeInTheDocument();
    expect(screen.getByText("/ember-sales-funnel-sales-page")).toBeInTheDocument();
    expect(screen.getByText("Generated for selected angle")).toBeInTheDocument();
    expect(screen.getByText("Needs configuration")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Publish Site/i })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /Prepare Template/i }));

    expect(mockPrepareSiteFunnel).toHaveBeenCalledWith({});
  });
});
