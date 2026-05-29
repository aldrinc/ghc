import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SiteDetailPage } from "./SiteDetailPage";

const mockSiteState = vi.hoisted(() => ({
  value: null as Record<string, unknown> | null,
}));
const mockFunnelsState = vi.hoisted(() => ({
  value: [] as Array<Record<string, unknown>>,
}));
const mockCreateSiteTemplateFromSite = vi.fn();
const mockCreateSiteFunnelTemplateImport = vi.fn();

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

vi.mock("@/api/campaigns", () => ({
  useCampaignsForProduct: () => ({ data: [], isLoading: false }),
  useCampaignCreativeContextAngles: () => ({ data: null, isLoading: false }),
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
  useSiteFunnels: () => ({ data: mockFunnelsState.value, isLoading: false, error: null }),
  useCreateSiteFunnel: () => ({ mutateAsync: vi.fn(), isPending: false, isError: false, error: null }),
  useDeleteSiteFunnel: () => ({ mutateAsync: vi.fn(), isPending: false, isError: false, error: null }),
}));

vi.mock("@/api/siteFunnelTemplateImports", () => ({
  useSiteFunnelTemplateImports: () => ({ data: [], isLoading: false, error: null }),
  useCreateSiteFunnelTemplateImport: () => ({
    mutateAsync: mockCreateSiteFunnelTemplateImport,
    isPending: false,
    isError: false,
    error: null,
  }),
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
    activeSitePublicationId: null,
    lastPublishedAt: null,
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
        <Route path="/workspaces/sites/:siteId/funnels" element={<SiteDetailPage />} />
        <Route path="/workspaces/sites/templates/:templateId" element={<div>Template Detail</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SiteDetailPage theme tab", () => {
  beforeEach(() => {
    mockSiteState.value = buildSite("standalone");
    mockFunnelsState.value = [];
    mockCreateSiteTemplateFromSite.mockResolvedValue({ id: "template-1" });
    mockCreateSiteFunnelTemplateImport.mockResolvedValue({ id: "html-import-1" });
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

  it("imports preserved html from the funnels tab", async () => {
    const user = userEvent.setup();

    renderPage();

    await user.click(screen.getByRole("tab", { name: /Funnels/i }));
    await user.click(screen.getByRole("button", { name: /Import HTML/i }));
    await user.type(screen.getByPlaceholderText("e.g., Ember Hero Landing Template"), "EMBER Sales Template");
    await user.type(screen.getByPlaceholderText("Paste your HTML here..."), "<!doctype html><html><body><h1>EMBER</h1></body></html>");
    await user.click(screen.getByRole("button", { name: /Import Template/i }));

    expect(mockCreateSiteFunnelTemplateImport).toHaveBeenCalledWith({
      sourceLabel: "EMBER Sales Template",
      htmlDocument: "<!doctype html><html><body><h1>EMBER</h1></body></html>",
    });
  });

  it("shows imported html funnel publication status in the funnels tab", async () => {
    const user = userEvent.setup();
    mockSiteState.value = {
      ...buildSite("standalone"),
      activeSitePublicationId: "publication-1234",
      lastPublishedAt: "2026-04-08T11:45:00Z",
    };
    mockFunnelsState.value = [
      {
        id: "funnel-1",
        siteId: "site-1",
        name: "EMBER Sales Funnel",
        description: "Imported funnel",
        status: "draft",
        funnelType: "html_template",
        entryPageId: null,
        productId: "product-1",
        selectedOfferId: null,
        templateImportId: "template-1",
        templateImportLabel: "EMBER Sales HTML",
        pageIntent: "sales",
        campaignId: "campaign-1",
        selectedAngleId: "angle-1",
        preparedPageId: "page-2",
        preparedPageSlug: "ember-sales-page",
        latestPreparedVersionId: "version-1",
        preparationReadiness: {},
        preparedAt: "2026-04-08T11:40:00Z",
        trackingConfig: null,
        createdAt: "2026-04-08T11:30:00Z",
        updatedAt: "2026-04-08T11:40:00Z",
      },
      {
        id: "funnel-2",
        siteId: "site-1",
        name: "EMBER Pre-sales Funnel",
        description: "Imported pre-sales funnel",
        status: "draft",
        funnelType: "html_template",
        entryPageId: null,
        productId: "product-1",
        selectedOfferId: null,
        templateImportId: "template-2",
        templateImportLabel: "EMBER Presell HTML",
        pageIntent: "pre_sales",
        campaignId: "campaign-2",
        selectedAngleId: "angle-2",
        preparedPageId: "page-3",
        preparedPageSlug: "ember-presell-page",
        latestPreparedVersionId: "version-2",
        preparationReadiness: {},
        preparedAt: "2026-04-08T11:50:00Z",
        trackingConfig: null,
        createdAt: "2026-04-08T11:32:00Z",
        updatedAt: "2026-04-08T11:50:00Z",
      },
    ];

    renderPage();

    await user.click(screen.getByRole("tab", { name: /Funnels/i }));

    expect(screen.getByText("Site Funnel Publishing")).toBeInTheDocument();
    expect(screen.getByText("publicat...")).toBeInTheDocument();
    expect(screen.getByText("Published")).toBeInTheDocument();
    expect(screen.getByText("Ready to publish")).toBeInTheDocument();
  });
});
