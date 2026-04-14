import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SitesPage } from "./SitesPage";

const mockCreateSite = vi.fn();
const mockInstantiateTemplate = vi.fn();

vi.mock("@/contexts/WorkspaceContext", () => ({
  useWorkspace: () => ({
    workspace: { id: "workspace-1", name: "Acme" },
  }),
}));

vi.mock("@/contexts/ProductContext", () => ({
  useProductContext: () => ({
    product: { id: "product-1", title: "Active Product", client_id: "workspace-1" },
    products: [
      { id: "product-1", title: "Active Product", client_id: "workspace-1" },
      { id: "product-2", title: "Second Product", client_id: "workspace-1" },
    ],
    isLoading: false,
  }),
}));

vi.mock("@/api/sites", () => ({
  useSites: () => ({ data: [], isLoading: false }),
  useSiteFamilies: () => ({
    data: [
      {
        family: "medusa-b2c-starter",
        name: "Medusa B2C Starter",
        description: "A starter storefront.",
        siteType: "ecommerce",
        commerceProvider: "medusa",
        themeRequirement: "optional",
        pageCount: 16,
      },
    ],
    isLoading: false,
  }),
  useCreateSite: () => ({
    mutateAsync: mockCreateSite,
    isPending: false,
    error: null,
  }),
}));

vi.mock("@/api/siteTemplates", () => ({
  useSiteTemplates: () => ({ data: [], isLoading: false }),
  useInstantiateSiteTemplate: () => ({
    mutateAsync: mockInstantiateTemplate,
    isPending: false,
    error: null,
  }),
}));

vi.mock("@/api/siteImports", () => ({
  useSiteImports: () => ({ data: [], isLoading: false }),
}));

vi.mock("@/api/designSystems", () => ({
  useDesignSystems: () => ({ data: [] }),
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/workspaces/sites/templates"]}>
      <SitesPage />
    </MemoryRouter>,
  );
}

describe("SitesPage", () => {
  beforeEach(() => {
    mockCreateSite.mockResolvedValue({ id: "site-1" });
    mockInstantiateTemplate.mockResolvedValue({ siteId: "site-from-template-1" });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("sends the selected theme binding mode when creating a site", async () => {
    const user = userEvent.setup();

    renderPage();

    await user.click(screen.getByRole("button", { name: /Medusa B2C Starter/i }));
    await user.click(screen.getByRole("radio", { name: /Use workspace brand/i }));
    await user.click(screen.getByRole("button", { name: "Create Site" }));

    await waitFor(() => {
      expect(mockCreateSite).toHaveBeenCalledWith(
        expect.objectContaining({
          clientId: "workspace-1",
          family: "medusa-b2c-starter",
          name: "Medusa B2C Starter Site",
          productId: "product-1",
          themeBindingMode: "workspace_default",
        }),
      );
    });
  });
});
