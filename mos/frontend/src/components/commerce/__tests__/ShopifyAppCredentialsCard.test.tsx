import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ShopifyAppCredentialsCard } from "../ShopifyAppCredentialsCard";

const baseProps = {
  workspaceId: "ws-1",
  shopifyAppApiKeyDraft: "",
  setShopifyAppApiKeyDraft: vi.fn(),
  shopifyAppApiSecretDraft: "",
  setShopifyAppApiSecretDraft: vi.fn(),
  hasConfiguredShopifyAppCredentials: false,
  isLoadingShopifyAppCredentials: false,
  shopifyAppCredentialsUpdatedAtLabel: "",
  isShopifyAppCredentialsMutating: false,
  hasShopifyConnectionTarget: false,
  onSave: vi.fn(),
};

describe("ShopifyAppCredentialsCard", () => {
  it("renders missing status by default", () => {
    render(<ShopifyAppCredentialsCard {...baseProps} />);
    expect(screen.getByText("App credentials")).toBeInTheDocument();
    expect(screen.getByText("Missing")).toBeInTheDocument();
  });

  it("shows updated timestamp when present", () => {
    render(
      <ShopifyAppCredentialsCard
        {...baseProps}
        hasConfiguredShopifyAppCredentials={true}
        shopifyAppCredentialsUpdatedAtLabel="3/18/2026, 4:12:00 PM"
      />,
    );
    expect(screen.getByText(/updated:/i)).toBeInTheDocument();
    expect(screen.getByText("Configured")).toBeInTheDocument();
  });

  it("disables save button until both fields are filled", () => {
    render(<ShopifyAppCredentialsCard {...baseProps} />);
    expect(screen.getByRole("button", { name: /save credentials/i })).toBeDisabled();
  });

  it("calls change handlers for both inputs", async () => {
    const user = userEvent.setup();
    render(<ShopifyAppCredentialsCard {...baseProps} />);
    await user.type(screen.getByPlaceholderText(/api key/i), "key-123");
    await user.type(screen.getByPlaceholderText(/api secret/i), "secret-456");
    expect(baseProps.setShopifyAppApiKeyDraft).toHaveBeenCalled();
    expect(baseProps.setShopifyAppApiSecretDraft).toHaveBeenCalled();
  });

  it("calls onSave when save button is clicked", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(
      <ShopifyAppCredentialsCard
        {...baseProps}
        shopifyAppApiKeyDraft="key-123"
        shopifyAppApiSecretDraft="secret-456"
        onSave={onSave}
      />,
    );
    await user.click(screen.getByRole("button", { name: /save credentials/i }));
    expect(onSave).toHaveBeenCalledTimes(1);
  });
});
