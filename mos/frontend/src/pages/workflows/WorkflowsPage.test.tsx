import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WorkflowsPage } from "@/pages/workflows/WorkflowsPage";

const mockUseWorkflows = vi.fn();
const mockUseWorkspace = vi.fn();
const mockUseProductContext = vi.fn();

vi.mock("@/api/workflows", () => ({
  useWorkflows: (...args: unknown[]) => mockUseWorkflows(...args),
  useStopWorkflow: () => ({
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
  }),
}));

vi.mock("@/api/clients", () => ({
  useClients: () => ({ data: [] }),
}));

vi.mock("@/contexts/WorkspaceContext", () => ({
  useWorkspace: () => mockUseWorkspace(),
}));

vi.mock("@/contexts/ProductContext", () => ({
  useProductContext: () => mockUseProductContext(),
}));

vi.mock("@/components/strategy/StrategySkillsWorkflowPanel", () => ({
  StrategySkillsWorkflowPanel: () => <div>Skills Workflow</div>,
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <WorkflowsPage />
    </MemoryRouter>,
  );
}

describe("WorkflowsPage", () => {
  beforeEach(() => {
    mockUseWorkspace.mockReturnValue({
      workspace: { id: "client-1", name: "Acme" },
    });
    mockUseProductContext.mockReturnValue({
      product: { id: "product-1", title: "Handbook", client_id: "client-1" },
      isLoading: false,
    });
    mockUseWorkflows.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("waits for the active product before enabling the workflows query", () => {
    mockUseProductContext.mockReturnValue({
      product: null,
      isLoading: true,
    });

    renderPage();

    expect(mockUseWorkflows).toHaveBeenCalledWith(undefined, { enabled: false });
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("requests workflows with both the workspace and product ids", () => {
    renderPage();

    expect(mockUseWorkflows).toHaveBeenCalledWith(
      { clientId: "client-1", productId: "product-1" },
      { enabled: true },
    );
    expect(screen.getByText("Workflow Run History")).toBeInTheDocument();
  });
});
