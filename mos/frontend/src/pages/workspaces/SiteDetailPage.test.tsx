import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SiteDetailPage } from "./SiteDetailPage";

const mockSiteState = vi.hoisted(() => ({
  value: null as Record<string, unknown> | null,
}));
const mockCreateSiteTemplateFromSite = vi.fn();

const designSystems = [
  {
    id: "ds-workspace",
    name: "Workspace Brand DS",
    tokens: {
      brand: { name: "Workspace Brand" },
      cssVars: {
        "--font-heading": "Fraunces",
        "--font-sans": "Public Sans",
        "--color-brand": "#224466",
        "--color-bg": "#f5f7fa",
        "--color-text": "#111827",
        "--color-cta": "#224466",
      },
    },
  },
  {
    id: "ds-specific",
    name: "Specific Theme DS",
    tokens: {
      brand: { name: "Specific Theme" },
      cssVars: {
        "--font-heading": "Instrument Serif",
        "--font-sans": "Manrope",
        "--color-brand": "#7c2d12",
        "--color-bg": "#fff7ed",
        "--color-text": "#431407",
        "--color-cta": "#c2410c",
      },
    },
  },
];

vi.mock("@/contexts/WorkspaceContext", () => ({
  useWorkspace: () => ({
    workspace: { id: "workspace-1", name: "Acme" },
  }),
}));

vi.mock("@/api/clients", () => ({
  useClient: () => ({
    data: { id: "workspace-1", design_system_id: "ds-workspace" },
  }),
}));

vi.mock("@/api/products", () => ({
  useProducts: () => ({
    data: [],
    isLoading: false,
  }),
}));

vi.mock("@/api/sites", () => ({
  useSite: () => ({
    data: mockSiteState.value,
    isLoading: false,
    error: null,
  }),
  useUpdateSite: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  }),
}));

vi.mock("@/api/siteFunnels", () => ({
  useSiteFunnels: () => ({ data: [], isLoading: false, error: null }),
  useCreateSiteFunnel: () => ({ mutateAsync: vi.fn(), isPending: false, isError: false, error: null }),
  useDeleteSiteFunnel: () => ({ mutateAsync: vi.fn(), isPending: false, isError: false, error: null }),
}));

vi.mock("@/api/siteProductBindings", () => ({
  useSiteProductBindings: () => ({ data: [], isLoading: false, error: null }),
  useCreateSiteProductBinding: () => ({ mutateAsync: vi.fn(), isPending: false, isError: false, error: null }),
  useDeleteSiteProductBinding: () => ({ mutateAsync: vi.fn(), isPending: false, isError: false, error: null }),
}));

vi.mock("@/api/designSystems", () => ({
  useDesignSystems: () => ({ data: designSystems }),
}));

vi.mock("@/api/siteTemplates", () => ({
  useCreateSiteTemplateFromSite: () => ({
    mutateAsync: mockCreateSiteTemplateFromSite,
    isPending: false,
    isError: false,
    error: null,
  }),
}));

vi.mock("@/pages/workspaces/sites/sitePreviewDefaults", () => ({
  useSitePreviewDefaults: () => ({
    data: { collectionHandle: null, categoryHandle: null },
    error: null,
  }),
}));

vi.mock("@/components/ui/toast", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

function buildSite(themeBindingMode: "standalone" | "workspace_default" | "design_system", designSystemId: string | null = null) {
  return {
    id: "site-1",
    clientId: "workspace-1",
    name: "Acme Store",
    description: "Store description",
    status: "draft",
    siteType: "ecommerce",
    siteFamily: "medusa-b2c-starter",
    commerceProvider: "medusa",
    productId: null,
    designSystemId,
    themeBindingMode,
    routeSlug: "acme-store",
    primaryDomain: null,
    templateId: null,
    entryPageId: "page-1",
    pages: [
      {
        id: "page-1",
        name: "Home",
        slug: "home",
        pageType: "home",
        templateId: null,
        ordering: 0,
        designSystemId: null,
        isEntry: true,
        latestDraftVersionId: null,
        latestApprovedVersionId: null,
      },
    ],
    createdAt: "2026-03-26T10:00:00Z",
    updatedAt: "2026-03-26T10:00:00Z",
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/workspaces/sites/site-1"]}>
      <Routes>
        <Route path="/workspaces/sites/:siteId" element={<SiteDetailPage />} />
        <Route path="/workspaces/sites/templates/:templateId" element={<div>Template Detail</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SiteDetailPage theme tab", () => {
  beforeEach(() => {
    mockSiteState.value = buildSite("standalone");
    mockCreateSiteTemplateFromSite.mockResolvedValue({ id: "template-1" });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the standalone theme state", async () => {
    const user = userEvent.setup();

    renderPage();
    await user.click(screen.getByRole("tab", { name: /Theme/i }));

    expect(screen.getAllByText("Standalone").length).toBeGreaterThan(0);
    expect(screen.getByText("Standalone mode")).toBeInTheDocument();
  });

  it("renders the workspace-default theme state", async () => {
    const user = userEvent.setup();
    mockSiteState.value = buildSite("workspace_default");

    renderPage();
    await user.click(screen.getByRole("tab", { name: /Theme/i }));

    expect(screen.getAllByText("Workspace brand").length).toBeGreaterThan(0);
    expect(screen.getByText("Workspace Brand DS")).toBeInTheDocument();
  });

  it("renders the selected design-system theme state", async () => {
    const user = userEvent.setup();
    mockSiteState.value = buildSite("design_system", "ds-specific");

    renderPage();
    await user.click(screen.getByRole("tab", { name: /Theme/i }));

    expect(screen.getAllByText("Design system").length).toBeGreaterThan(0);
    expect(screen.getByText("Specific Theme DS")).toBeInTheDocument();
  });

  it("creates a reusable template from the current site", async () => {
    const user = userEvent.setup();

    renderPage();

    await user.click(screen.getByRole("button", { name: /Save as Template/i }));
    const templateNameInput = screen.getByPlaceholderText("Omni One Product Template");
    await user.clear(templateNameInput);
    await user.type(templateNameInput, "OMNI One Product Template");
    await user.click(screen.getByRole("button", { name: /^Create Template$/i }));

    expect(mockCreateSiteTemplateFromSite).toHaveBeenCalledWith({
      siteId: "site-1",
      name: "OMNI One Product Template",
      description: "Store description",
    });
  });
});
