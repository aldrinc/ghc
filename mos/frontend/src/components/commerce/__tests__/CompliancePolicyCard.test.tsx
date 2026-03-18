import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CompliancePolicyCard } from "../CompliancePolicyCard";

// Mock compliance API hooks
const mockUpsertMutateAsync = vi.fn();
const mockSyncMutateAsync = vi.fn();
vi.mock("@/api/compliance", () => ({
  COMPLIANCE_RULESET_VERSION: "2025-06-01",
  useClientComplianceProfile: vi.fn(() => ({
    data: null,
    isLoading: false,
  })),
  useUpsertClientComplianceProfile: vi.fn(() => ({
    mutateAsync: mockUpsertMutateAsync,
    isPending: false,
  })),
  useSyncComplianceShopifyPolicyPages: vi.fn(() => ({
    mutateAsync: mockSyncMutateAsync,
    isPending: false,
  })),
}));

// Mock toast to prevent side effects
vi.mock("@/components/ui/toast", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

const baseProps = {
  workspaceId: "ws-1",
  workspaceName: "Acme Corp",
  shopifySyncShopDomain: "acme.myshopify.com",
  selectedShopDomainOption: { storefrontDomain: "acme.com", value: "acme.myshopify.com" },
  hasShopifyConnectionTarget: true,
};

/** Click the collapsible header to expand the form. */
async function expandCard() {
  const user = userEvent.setup();
  const header = screen.getByRole("button", { name: /compliance/i });
  await user.click(header);
}

describe("CompliancePolicyCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders section heading", () => {
    render(<CompliancePolicyCard {...baseProps} />);
    expect(screen.getByText("Compliance")).toBeInTheDocument();
  });

  it("shows form fields when expanded", async () => {
    render(<CompliancePolicyCard {...baseProps} />);
    await expandCard();
    expect(screen.getByText("Business models")).toBeInTheDocument();
    expect(screen.getByText("Legal business name")).toBeInTheDocument();
    expect(screen.getByText("Support email")).toBeInTheDocument();
    expect(screen.getByText("Support phone")).toBeInTheDocument();
    expect(screen.getByText("Support hours")).toBeInTheDocument();
  });

  it("pre-fills legal business name from workspace name", async () => {
    render(<CompliancePolicyCard {...baseProps} />);
    await expandCard();
    const legalNameInput = screen.getByPlaceholderText("The Honest Herbalist LLC");
    expect(legalNameInput).toHaveValue("Acme Corp");
  });

  it("defaults business models CSV to ecommerce", async () => {
    render(<CompliancePolicyCard {...baseProps} />);
    await expandCard();
    const modelsInput = screen.getByPlaceholderText("ecommerce");
    expect(modelsInput).toHaveValue("ecommerce");
  });

  it("renders save and generate buttons when expanded", async () => {
    render(<CompliancePolicyCard {...baseProps} />);
    await expandCard();
    expect(screen.getByRole("button", { name: /save profile/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate policy pages/i })).toBeInTheDocument();
  });

  it("disables generate button when no saved compliance profile", async () => {
    render(<CompliancePolicyCard {...baseProps} />);
    await expandCard();
    const generateBtn = screen.getByRole("button", { name: /generate policy pages/i });
    expect(generateBtn).toBeDisabled();
  });

  it("disables generate button when no Shopify connection", async () => {
    render(<CompliancePolicyCard {...baseProps} hasShopifyConnectionTarget={false} />);
    await expandCard();
    const generateBtn = screen.getByRole("button", { name: /generate policy pages/i });
    expect(generateBtn).toBeDisabled();
  });

  it("enables generate button when profile is saved and Shopify is connected", async () => {
    const { useClientComplianceProfile } = await import("@/api/compliance");
    vi.mocked(useClientComplianceProfile).mockReturnValue({
      data: {
        id: "p1",
        orgId: "org1",
        clientId: "ws-1",
        rulesetVersion: "2025-06-01",
        businessModels: ["ecommerce"],
        metadata: {},
        createdAt: "2025-01-01",
        updatedAt: "2025-06-01",
      },
      isLoading: false,
    } as any);

    render(<CompliancePolicyCard {...baseProps} hasShopifyConnectionTarget={true} />);
    await expandCard();
    const generateBtn = screen.getByRole("button", { name: /generate policy pages/i });
    expect(generateBtn).not.toBeDisabled();
  });

  it("shows no-profile message when profile not yet saved", async () => {
    const { useClientComplianceProfile } = await import("@/api/compliance");
    vi.mocked(useClientComplianceProfile).mockReturnValue({
      data: null,
      isLoading: false,
    } as any);

    render(<CompliancePolicyCard {...baseProps} />);
    expect(screen.getByText(/no profile saved yet/i)).toBeInTheDocument();
  });
});
