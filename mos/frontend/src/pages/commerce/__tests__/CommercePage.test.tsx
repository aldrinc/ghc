import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { CommercePage } from "../CommercePage";

// Mock WorkspaceContext
const mockWorkspace = { id: "ws-1", name: "Acme Corp", industry: "ecommerce" };
vi.mock("@/contexts/WorkspaceContext", () => ({
  useWorkspace: vi.fn(() => ({ workspace: mockWorkspace })),
}));

// Mock ShopifyTab to keep tests focused on page-level behavior
vi.mock("../ShopifyTab", () => ({
  ShopifyTab: () => <div data-testid="shopify-tab-content">Shopify tab content</div>,
}));

function renderPage(initialEntries = ["/commerce"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <CommercePage />
    </MemoryRouter>,
  );
}

describe("CommercePage", () => {
  it("renders page header with workspace info", () => {
    renderPage();
    expect(screen.getByText("Commerce")).toBeInTheDocument();
    expect(screen.getByText("Acme Corp · ecommerce")).toBeInTheDocument();
  });

  it("renders Shopify tab by default", () => {
    renderPage();
    expect(screen.getByText("Shopify")).toBeInTheDocument();
    expect(screen.getByTestId("shopify-tab-content")).toBeInTheDocument();
  });

  it("renders Shopify tab when ?tab=shopify is set", () => {
    renderPage(["/commerce?tab=shopify"]);
    expect(screen.getByTestId("shopify-tab-content")).toBeInTheDocument();
  });

  it("shows empty state when no workspace is selected", async () => {
    const { useWorkspace } = await import("@/contexts/WorkspaceContext");
    vi.mocked(useWorkspace).mockReturnValueOnce({ workspace: null } as ReturnType<typeof useWorkspace>);

    renderPage();
    expect(screen.getByText(/select a workspace/i)).toBeInTheDocument();
    expect(screen.queryByTestId("shopify-tab-content")).not.toBeInTheDocument();
  });

  it("renders Shopify tab trigger as a button", () => {
    renderPage();
    const trigger = screen.getByRole("tab", { name: "Shopify" });
    expect(trigger).toBeInTheDocument();
  });
});
