import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OnboardingWizard } from "./OnboardingWizard";

const mocks = vi.hoisted(() => ({
  useCreateClient: vi.fn(),
  createClient: vi.fn(),
  createClientPending: false,
  extractContext: vi.fn(),
  extractContextPending: false,
  startSetup: vi.fn(),
  startSetupPending: false,
  foundationReadiness: {
    status: "foundation_pending",
    should_gate_overview: true,
    reason: "waiting_for_strategy_v2_foundation_bundle",
    required_step_keys: [],
    present_step_keys: [],
    missing_step_keys: [],
    checked_at: new Date().toISOString(),
  },
  signOut: vi.fn(),
}));

vi.mock("@clerk/clerk-react", () => ({
  useClerk: () => ({ signOut: mocks.signOut }),
}));

vi.mock("@/api/clients", () => ({
  useCreateClient: (options?: { showSuccessToast?: boolean }) => {
    mocks.useCreateClient(options);
    return { mutateAsync: mocks.createClient, isPending: mocks.createClientPending };
  },
  useExtractMarketingAgentContext: () => ({ mutateAsync: mocks.extractContext, isPending: mocks.extractContextPending }),
  useStartMarketingAgentSetup: () => ({ mutateAsync: mocks.startSetup, isPending: mocks.startSetupPending }),
  useClientFoundationReadiness: () => ({ data: mocks.foundationReadiness }),
}));

vi.mock("@/api/workflows", () => ({
  useWorkflowDetail: () => ({ data: undefined, refetch: vi.fn() }),
}));

vi.mock("@/components/ui/toast", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/contexts/ProductContext", () => ({
  useProductContext: () => ({ selectProduct: vi.fn() }),
}));

vi.mock("@/contexts/WorkspaceContext", () => ({
  useWorkspace: () => ({ selectWorkspace: vi.fn() }),
}));

function wizardElement(props: Partial<ComponentProps<typeof OnboardingWizard>> = {}) {
  return (
    <MemoryRouter>
      <OnboardingWizard variant="page" {...props} />
    </MemoryRouter>
  );
}

function renderWizard(props: Partial<ComponentProps<typeof OnboardingWizard>> = {}) {
  return render(wizardElement(props));
}

describe("OnboardingWizard marketing-agent setup", () => {
  beforeEach(() => {
    mocks.createClientPending = false;
    mocks.extractContextPending = false;
    mocks.startSetupPending = false;
    mocks.createClient.mockResolvedValue({ id: "client-1", name: "Operator workspace" });
    mocks.extractContext.mockResolvedValue({
      provider: "context_dev",
      domain: "example.com",
      business_url: "https://example.com",
      competitor_urls: ["https://competitor.example"],
      raw_artifact_id: "artifact-1",
      fields: {
        business_model: { value: "SaaS subscription" },
        offering_kind: { value: "software" },
        offering_type: { value: "analytics software" },
        offering_name: { value: "Revenue Dashboard" },
        offering_description: { value: "Software for revenue operators." },
        category: { value: "B2B SaaS" },
      },
      requests: {},
    });
    mocks.startSetup.mockResolvedValue({
      workflow_run_id: "workflow-1",
      temporal_workflow_id: "temporal-1",
      product_id: "product-1",
      product_name: "Revenue Dashboard",
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("starts with one focused workspace question", () => {
    renderWizard();

    expect(mocks.useCreateClient).toHaveBeenCalledWith({ showSuccessToast: false });
    expect(screen.getByRole("heading", { name: "What should we call this workspace?" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Setup progress" })).toHaveAttribute("aria-valuenow", "12");
    expect(screen.getByText("2-minute setup")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Previous" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Workspace name")).toBeInTheDocument();
    expect(screen.getByText("Workspace name")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Continue/ })).toBeDisabled();
    expect(screen.queryByPlaceholderText("Enter the business or workspace name")).not.toBeInTheDocument();
    expect(screen.queryByRole("listbox", { name: "Business model" })).not.toBeInTheDocument();
    expect(screen.queryByText("Brand source summary")).not.toBeInTheDocument();
  });

  it("keeps Continue disabled until the current input step is valid", async () => {
    const user = userEvent.setup();
    renderWizard();

    expect(screen.getByRole("button", { name: /Continue/ })).toBeDisabled();
    await user.type(screen.getByLabelText("Workspace name"), "Operator workspace");
    expect(screen.getByRole("button", { name: /Continue/ })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.click(screen.getByRole("option", { name: /Already live business/ }));

    expect(screen.getByRole("button", { name: /Continue/ })).toBeDisabled();
    await user.type(screen.getByLabelText("Business website URL"), "not a url");
    expect(screen.getByRole("button", { name: /Continue/ })).toBeDisabled();
    await user.clear(screen.getByLabelText("Business website URL"));
    await user.type(screen.getByLabelText("Business website URL"), "example.com");
    expect(screen.getByRole("button", { name: /Continue/ })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: /Continue/ }));

    expect(screen.getByRole("button", { name: /Continue/ })).toBeEnabled();
    await user.type(screen.getByLabelText("Competitor websites"), "bad url");
    expect(screen.getByRole("button", { name: /Continue/ })).toBeDisabled();
    await user.clear(screen.getByLabelText("Competitor websites"));
    expect(screen.getByRole("button", { name: /Continue/ })).toBeEnabled();
  });

  it("branches into the new-business product/service path", async () => {
    const user = userEvent.setup();
    const view = renderWizard();

    await user.type(screen.getByLabelText("Workspace name"), "Operator workspace");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    expect(screen.getByRole("progressbar", { name: "Setup progress" })).toHaveAttribute("aria-valuenow", "24");
    expect(screen.queryByRole("button", { name: /Continue/ })).not.toBeInTheDocument();
    expect(view.container.querySelector('[data-onboarding-icon="business-new"]')).not.toBeNull();
    expect(view.container.querySelector('[data-onboarding-icon="business-existing"]')).not.toBeNull();
    await user.click(screen.getByRole("option", { name: /New business/ }));

    expect(screen.getByRole("listbox", { name: "Business model" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Setup progress" })).toHaveAttribute("aria-valuenow", "36");
    expect(screen.getByRole("button", { name: "Previous" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Continue/ })).not.toBeInTheDocument();
    expect(view.container.querySelector('[data-onboarding-icon="model-service"]')).not.toBeNull();
    expect(view.container.querySelector('[data-onboarding-icon="model-affiliate"]')).not.toBeNull();
    expect(screen.queryByText("Pick the closest model. You can refine this later.")).not.toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: /Service business/ }));

    expect(screen.getByRole("heading", { name: "What service do you provide?" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "What do you sell or plan to sell?" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Continue/ })).toBeDisabled();
    await user.type(screen.getByLabelText("Offer name"), "Growth Sprint");
    expect(screen.getByRole("button", { name: /Continue/ })).toBeEnabled();
  });

  it("routes affiliate through promoted offer type", async () => {
    const user = userEvent.setup();
    renderWizard();

    await user.type(screen.getByLabelText("Workspace name"), "Affiliate workspace");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.click(screen.getByRole("option", { name: /New business/ }));
    await user.click(screen.getByRole("option", { name: /Affiliate/ }));

    expect(screen.getByRole("heading", { name: "What kind of offer are you promoting?" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Continue/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: /Software or SaaS/ }));

    expect(screen.getByRole("heading", { name: "What is the software called?" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Offer name"), "Partner CRM");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.type(screen.getByLabelText("Offer description"), "Affiliate promotion for a CRM platform.");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.click(screen.getByRole("option", { name: /Set pricing later/ }));
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.click(screen.getByRole("button", { name: "Create workspace" }));

    expect(mocks.startSetup).toHaveBeenCalledWith({
      clientId: "client-1",
      payload: expect.objectContaining({
        business_model: "affiliate",
        offering_kind: "software",
        offering_type: "software",
        offering_name: "Partner CRM",
      }),
    });
  });

  it("requires an explanation for other business models", async () => {
    const user = userEvent.setup();
    renderWizard();

    await user.type(screen.getByLabelText("Workspace name"), "Other workspace");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.click(screen.getByRole("option", { name: /New business/ }));
    await user.click(screen.getByRole("option", { name: /^Other/ }));

    expect(screen.getByLabelText("Custom business model")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Continue/ })).toBeDisabled();
    await user.type(screen.getByLabelText("Custom business model"), "Paid community for independent consultants");
    expect(screen.getByRole("button", { name: /Continue/ })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: /Continue/ }));

    expect(screen.getByRole("heading", { name: "What should your agent work on first?" })).toBeInTheDocument();
  });

  it("uses Context.dev extraction for existing-business review", async () => {
    const user = userEvent.setup();
    renderWizard();

    await user.type(screen.getByLabelText("Workspace name"), "Operator workspace");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    expect(screen.getByRole("heading", { name: "Is this a new or already live business?" })).toBeInTheDocument();
    expect(screen.getByText("We'll start from scratch or research your existing business to get you setup.")).toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: /Already live business/ }));
    await user.type(screen.getByLabelText("Business website URL"), "example.com");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.type(screen.getByLabelText("Competitor websites"), "competitor.example");
    await user.click(screen.getByRole("button", { name: /Continue/ }));

    expect(mocks.createClient).toHaveBeenCalledWith({
      name: "Operator workspace",
      strategyV2Enabled: true,
    });
    expect(mocks.extractContext).toHaveBeenCalledWith({
      clientId: "client-1",
      payload: {
        business_url: "https://example.com",
        competitor_urls: ["https://competitor.example"],
      },
    });
    expect(await screen.findByRole("heading", { name: "Review workspace" })).toBeInTheDocument();
    expect(mocks.extractContext).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Previous" }));
    expect(screen.getByRole("heading", { name: "Any competitors your agent should know about?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    expect(await screen.findByRole("heading", { name: "Review workspace" })).toBeInTheDocument();
    expect(mocks.extractContext).toHaveBeenCalledTimes(1);

    expect(screen.getByText("Revenue Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Optional gap")).toBeInTheDocument();
    expect(screen.queryByLabelText("Offer name")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Edit all details" }));
    const offerNameInput = screen.getByLabelText("Offer name");
    const doneButton = screen.getByRole("button", { name: "Done" });
    expect(offerNameInput).toHaveValue("Revenue Dashboard");
    expect(doneButton).toBeEnabled();
    await user.clear(offerNameInput);
    expect(doneButton).toBeDisabled();
    await user.type(offerNameInput, "Revenue Dashboard");
    expect(doneButton).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByLabelText("Offer name")).not.toBeInTheDocument();
  });

  it("shows the loading button while checking an existing site", async () => {
    const user = userEvent.setup();
    const view = renderWizard();

    await user.type(screen.getByLabelText("Workspace name"), "Operator workspace");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.click(screen.getByRole("option", { name: /Already live business/ }));
    await user.type(screen.getByLabelText("Business website URL"), "example.com");
    await user.click(screen.getByRole("button", { name: /Continue/ }));

    expect(screen.getByRole("heading", { name: "Any competitors your agent should know about?" })).toBeInTheDocument();

    mocks.extractContextPending = true;
    view.rerender(wizardElement());

    const loadingButton = screen.getByRole("button", { name: /Checking site/ });
    expect(loadingButton).toBeDisabled();
    expect(loadingButton).toHaveAttribute("aria-busy", "true");
    expect(loadingButton.querySelector(".animate-spin")).not.toBeNull();
  });

  it("submits a service setup without requiring price", async () => {
    const user = userEvent.setup();
    const view = renderWizard();

    await user.type(screen.getByLabelText("Workspace name"), "Service workspace");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.click(screen.getByRole("option", { name: /New business/ }));
    await user.click(screen.getByRole("option", { name: /Service business/ }));
    await user.type(screen.getByLabelText("Offer name"), "Growth Sprint");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.type(screen.getByLabelText("Offer description"), "A service that improves customer acquisition.");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    expect(screen.getByRole("heading", { name: "How do you charge for your service?" })).toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: /Set pricing later/ }));
    expect(screen.getByRole("heading", { name: "Any competitors your agent should know about?" })).toBeInTheDocument();
    expect(screen.getByText("Optional")).toBeInTheDocument();
    expect(screen.queryByText("Optional — useful when you already know direct alternatives.")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.click(screen.getByRole("button", { name: "Create workspace" }));

    expect(mocks.startSetup).toHaveBeenCalledWith({
      clientId: "client-1",
      payload: expect.objectContaining({
        business_type: "new",
        input_mode: "manual_seed",
        business_model: "service_business",
        offering_kind: "service",
        offering_name: "Growth Sprint",
        price: undefined,
        starting_rate: undefined,
        metadata: expect.objectContaining({ pricing_status: "later" }),
      }),
    });
    expect(await screen.findByRole("heading", { name: "Setting up your workspace" })).toBeInTheDocument();
    expect(screen.getByText("Up to 20 minutes")).toBeInTheDocument();
    expect(screen.getByText("Email when ready")).toBeInTheDocument();
    expect(screen.getByText("mOS agent researching the market")).toBeInTheDocument();
    expect(screen.getByText("mOS agent building foundational docs")).toBeInTheDocument();
    expect(view.container.querySelector('[data-onboarding-icon="setup-workspace"]')).not.toBeNull();
    expect(view.container.querySelector('[data-onboarding-icon="setup-docs"]')).not.toBeNull();
    expect(screen.queryByText("Marketing agent ready")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open workspace" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
    expect(
      screen.queryByText(
        /setup state is tracked by foundational readiness, not by onboarding run completion/i,
      ),
    ).not.toBeInTheDocument();
  });

  it("hides setup logout when the page already has a close action", async () => {
    const user = userEvent.setup();
    renderWizard({
      showSetupLogout: false,
      pageHeaderEndAction: <button type="button" aria-label="Close onboarding">Close</button>,
    });

    await user.type(screen.getByLabelText("Workspace name"), "Second workspace");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.click(screen.getByRole("option", { name: /New business/ }));
    await user.click(screen.getByRole("option", { name: /Service business/ }));
    await user.type(screen.getByLabelText("Offer name"), "Growth Sprint");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.type(screen.getByLabelText("Offer description"), "A service that improves customer acquisition.");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.click(screen.getByRole("option", { name: /Set pricing later/ }));
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.click(screen.getByRole("button", { name: "Create workspace" }));

    expect(await screen.findByRole("heading", { name: "Setting up your workspace" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close onboarding" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Log out" })).not.toBeInTheDocument();
  });

  it("allows service pricing to use monthly or a custom charge model", async () => {
    const user = userEvent.setup();
    renderWizard();

    await user.type(screen.getByLabelText("Workspace name"), "Custom service workspace");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.click(screen.getByRole("option", { name: /New business/ }));
    await user.click(screen.getByRole("option", { name: /Service business/ }));
    await user.type(screen.getByLabelText("Offer name"), "Growth Sprint");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.type(screen.getByLabelText("Offer description"), "A service that improves customer acquisition.");
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.click(screen.getByRole("option", { name: /I know enough to add it now/ }));

    expect(screen.getByRole("option", { name: "Monthly" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Other" })).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Pricing model"), "other");
    await user.type(screen.getByLabelText("Price"), "99/mo");
    expect(screen.getByRole("button", { name: /Continue/ })).toBeDisabled();
    await user.type(screen.getByLabelText("Custom pricing model"), "Monthly minimum");
    expect(screen.getByRole("button", { name: /Continue/ })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.click(screen.getByRole("button", { name: "Create workspace" }));

    expect(mocks.startSetup).toHaveBeenCalledWith({
      clientId: "client-1",
      payload: expect.objectContaining({
        business_type: "new",
        business_model: "service_business",
        offering_kind: "service",
        offering_name: "Growth Sprint",
        pricing_model: "Monthly minimum",
        starting_rate: "99/mo",
      }),
    });
  });
});
