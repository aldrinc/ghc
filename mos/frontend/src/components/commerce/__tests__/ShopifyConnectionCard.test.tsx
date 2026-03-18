import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ShopifyConnectionCard } from "../ShopifyConnectionCard";

function makeMutation(overrides?: Record<string, unknown>) {
  return { mutateAsync: vi.fn(), isPending: false, ...overrides };
}

const baseProps = {
  workspaceId: "ws-1",
  shopifyStatus: null as any,
  isLoadingShopifyStatus: false,
  refetchShopifyStatus: vi.fn(),
  shopifyState: "not_connected",
  installationState: "none",
  shopDomainOptions: [] as { label: string; storefrontDomain: string; value: string }[],
  connectedShopDomains: [] as string[],
  hasShopifyConnectionTarget: false,
  shopifyStatusTone: "neutral" as const,
  shopifyStatusLabel: "Not connected",
  shopifyStatusMessage: "Connect a Shopify store to get started.",
  installationStatusLabel: "None",
  isShopifyConnectionMutating: false,
  createShopifyInstallUrl: makeMutation(),
  setDefaultShop: makeMutation(),
  autoProvisionShopifyStorefrontToken: makeMutation(),
  updateShopifyInstallation: makeMutation(),
  disconnectShopifyInstallation: makeMutation(),
};

describe("ShopifyConnectionCard", () => {
  it("renders not-connected status and connect form", () => {
    render(<ShopifyConnectionCard {...baseProps} />);
    expect(screen.getByText("Not connected")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/example-shop/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^connect$/i })).toBeInTheDocument();
  });

  it("disables connect button when shop domain is empty", () => {
    render(<ShopifyConnectionCard {...baseProps} />);
    const btn = screen.getByRole("button", { name: /^connect$/i });
    expect(btn).toBeDisabled();
  });

  it("enables connect button after entering shop domain", async () => {
    const user = userEvent.setup();
    render(<ShopifyConnectionCard {...baseProps} />);
    const input = screen.getByPlaceholderText(/example-shop/);
    await user.type(input, "test-store.myshopify.com");
    const btn = screen.getByRole("button", { name: /^connect$/i });
    expect(btn).not.toBeDisabled();
  });

  it("shows disconnect button when connected", () => {
    render(
      <ShopifyConnectionCard
        {...baseProps}
        hasShopifyConnectionTarget={true}
        shopifyStatusTone="success"
        shopifyStatusLabel="Connected"
        connectedShopDomains={["test-store.myshopify.com"]}
      />,
    );
    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("test-store.myshopify.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^disconnect$/i })).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/example-shop/)).not.toBeInTheDocument();
  });

  it("shows manual token form when toggled", async () => {
    const user = userEvent.setup();
    render(
      <ShopifyConnectionCard
        {...baseProps}
        shopifyState="installed_missing_storefront_token"
        hasShopifyConnectionTarget={true}
      />,
    );
    const toggleBtn = screen.getByRole("button", { name: /enter manually/i });
    await user.click(toggleBtn);
    expect(screen.getByPlaceholderText(/storefront access token/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save token/i })).toBeInTheDocument();
  });

  it("shows retry automatic token button for missing-token state", () => {
    render(
      <ShopifyConnectionCard
        {...baseProps}
        shopifyState="installed_missing_storefront_token"
        hasShopifyConnectionTarget={true}
      />,
    );
    expect(screen.getByRole("button", { name: /retry automatic setup/i })).toBeInTheDocument();
  });

  it("shows default shop selector for multi-installation conflict", () => {
    render(
      <ShopifyConnectionCard
        {...baseProps}
        shopifyState="multiple_installations_conflict"
        shopifyStatus={{ shopDomains: ["a.myshopify.com", "b.myshopify.com"] } as any}
        shopDomainOptions={[
          { label: "a.myshopify.com", storefrontDomain: "", value: "a.myshopify.com" },
          { label: "b.myshopify.com", storefrontDomain: "", value: "b.myshopify.com" },
        ]}
        hasShopifyConnectionTarget={true}
      />,
    );
    expect(screen.getByRole("button", { name: /set default/i })).toBeInTheDocument();
  });

  it("shows loading state for status badge", () => {
    render(<ShopifyConnectionCard {...baseProps} isLoadingShopifyStatus={true} />);
    expect(screen.getByText("Checking\u2026")).toBeInTheDocument();
  });
});
