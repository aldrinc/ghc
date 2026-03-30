// @vitest-environment jsdom

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SitePagePreviewPage } from "./SitePagePreviewPage";

const mockUseProducts = vi.fn();
const mockUseSite = vi.fn();
const mockUseSitePage = vi.fn();
const mockUseSiteMedusaConfig = vi.fn();
const mockSelectWorkspace = vi.fn();
const mockSetMedusaRuntimeConfig = vi.fn();

const workspaceState = {
  clients: [{ id: "workspace-1", name: "Acme", industry: "Supplements" }],
  workspace: null as { id: string; name: string } | null,
  selectWorkspace: mockSelectWorkspace,
  clearWorkspace: vi.fn(),
  isLoading: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
};

const previewSite = {
  id: "site-1",
  clientId: "workspace-1",
  name: "Preview Site",
  description: null,
  status: "draft",
  experienceKind: null,
  siteType: "ecommerce",
  siteFamily: "medusa-b2c-starter",
  commerceProvider: "medusa",
  productId: "product-1",
  designSystemId: null,
  themeBindingMode: "standalone" as const,
  entryPageId: "page-1",
  routeSlug: "preview-site",
  primaryDomain: null,
  templateId: null,
  pages: [
    {
      id: "page-1",
      name: "Home",
      slug: "home",
      pageType: "home",
      templateId: null,
      ordering: 0,
      isEntry: true,
      designSystemId: null,
      latestDraftVersionId: "draft-1",
      latestApprovedVersionId: null,
    },
  ],
  createdAt: "2026-03-26T10:00:00Z",
  updatedAt: "2026-03-26T10:00:00Z",
};

const previewPageDetail = {
  site: {
    id: "site-1",
    name: "Preview Site",
    routeSlug: "preview-site",
    siteFamily: "medusa-b2c-starter",
    siteType: "ecommerce",
    commerceProvider: "medusa",
    productId: "product-1",
    designSystemId: null,
    themeBindingMode: "standalone" as const,
  },
  page: {
    id: "page-1",
    siteId: "site-1",
    name: "Home",
    slug: "home",
    pageType: "home",
    templateId: null,
    ordering: 0,
    designSystemId: null,
  },
  latestDraft: {
    id: "draft-1",
    status: "draft" as const,
    puckData: { content: [], root: {}, zones: {} },
    createdAt: "2026-03-26T10:00:00Z",
  },
  latestApproved: null,
  designSystemTokens: null,
};

vi.mock("@/api/sites", () => ({
  useSite: (...args: unknown[]) => mockUseSite(...args),
  useSitePage: (...args: unknown[]) => mockUseSitePage(...args),
  useSiteMedusaConfig: (...args: unknown[]) => mockUseSiteMedusaConfig(...args),
}));

vi.mock("@/api/products", () => ({
  useProducts: (...args: unknown[]) => mockUseProducts(...args),
}));

vi.mock("@/contexts/WorkspaceContext", () => ({
  useWorkspace: () => workspaceState,
}));

vi.mock("@measured/puck", () => ({
  Render: () => <div>Preview Render</div>,
}));

vi.mock("@/components/design-system/DesignSystemProvider", () => ({
  DesignSystemProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/commerce/b2c/B2CRuntimeProvider", () => ({
  B2CRuntimeProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({ children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));

vi.mock("@/components/ui/badge", () => ({
  Badge: ({ children }: { children: ReactNode }) => <span>{children}</span>,
}));

vi.mock("@/funnels/puckConfig", () => ({
  createFunnelPuckConfig: () => ({}),
  FunnelRuntimeProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("@/funnels/puckData", () => ({
  normalizePuckData: () => ({ content: [], root: {}, zones: {} }),
}));

vi.mock("@/funnels/runtimePageMaps", () => ({
  buildRuntimePageMap: () => ({ home: "page-1" }),
  buildRuntimePageStageMap: () => ({}),
  buildRuntimePageTypeMap: () => ({ page_1: "home" }),
}));

vi.mock("@/funnels/runtimeRouting", () => ({
  parseSitePath: () => ({ countryCode: "us" }),
  shortUuidRouteToken: () => "preview-token",
}));

vi.mock("@/lib/medusa", () => ({
  setMedusaRuntimeConfig: (...args: unknown[]) => mockSetMedusaRuntimeConfig(...args),
}));

vi.mock("@/pages/workspaces/sites/sitePreviewRouting", () => ({
  buildSitePreviewPath: (siteId: string, routePath?: string | null) =>
    routePath ? `/workspaces/sites/${siteId}/preview/${routePath}` : `/workspaces/sites/${siteId}/preview`,
  resolveSitePreviewPage: () => previewSite.pages[0],
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/workspaces/sites/site-1/preview/us"]}>
      <Routes>
        <Route path="/workspaces/sites/:siteId/preview/*" element={<SitePagePreviewPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("SitePagePreviewPage", () => {
  beforeEach(() => {
    workspaceState.workspace = null;
    mockSelectWorkspace.mockReset();
    mockSetMedusaRuntimeConfig.mockReset();
    mockUseSite.mockReset();
    mockUseSitePage.mockReset();
    mockUseSiteMedusaConfig.mockReset();
    mockUseProducts.mockReset();

    mockUseSite.mockReturnValue({
      data: previewSite,
      isLoading: false,
      error: null,
    });
    mockUseSitePage.mockReturnValue({
      data: previewPageDetail,
      isLoading: false,
      error: null,
    });
    mockUseSiteMedusaConfig.mockReturnValue({
      data: { siteFamily: "medusa-b2c-starter", commerceProvider: "medusa", medusaConfig: null },
    });
    mockUseProducts.mockReturnValue({
      data: [{ id: "product-1", handle: "omni-creatine-gummy" }],
    });
  });

  it("loads preview data without a preselected workspace and restores the owning workspace", async () => {
    renderPage();

    expect(mockUseSite).toHaveBeenCalledWith("site-1", {
      clientId: null,
      requireWorkspace: false,
    });
    expect(mockUseSitePage).toHaveBeenCalledWith("site-1", "page-1", {
      clientId: "workspace-1",
    });

    await waitFor(() => {
      expect(mockSelectWorkspace).toHaveBeenCalledWith("workspace-1");
    });

    expect(screen.getByText("Preview Render")).toBeInTheDocument();
  });
});
