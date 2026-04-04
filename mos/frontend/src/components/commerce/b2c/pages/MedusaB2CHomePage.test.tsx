import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const refreshProducts = vi.fn();
const navigateToStore = vi.fn();

const { themeState } = vi.hoisted(() => ({
  themeState: {
    value: {
      tokens: {},
      isThemed: false,
      ctaStyle: undefined as Record<string, string> | undefined,
    },
  },
}));

vi.mock("../B2CRuntimeProvider", () => ({
  useB2CRuntime: () => ({
    siteName: "Honest Herbalist",
    products: [],
    collections: [],
    productsLoading: false,
    refreshProducts,
    navigateToStore,
    navigateToCollection: vi.fn(),
    navigateToProduct: vi.fn(),
    categories: [],
    cart: { items: [] },
    customer: null,
    navigateToHome: vi.fn(),
    navigateToCategory: vi.fn(),
    navigateToCart: vi.fn(),
    navigateToAccount: vi.fn(),
  }),
  useImportedOneProductShellData: () => ({ status: "unavailable" }),
}));

vi.mock("@/api/client", () => ({
  useApiClient: () => ({
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    request: vi.fn(),
  }),
}));

vi.mock("../useB2CTheme", () => ({
  resolveB2CActionRadius: (tokens: { radiusMedium?: string; radiusLarge?: string }) =>
    tokens.radiusMedium || tokens.radiusLarge || "8px",
  resolveB2CBodyFont: (tokens: { fontBody?: string }) =>
    tokens.fontBody || 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  resolveB2CHeadingFont: (tokens: { fontHeading?: string; fontBody?: string }) =>
    tokens.fontHeading
    || tokens.fontBody
    || 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  resolveB2CPillRadius: (tokens: {
    radiusFull?: string;
    radiusMedium?: string;
    radiusLarge?: string;
  }) => tokens.radiusFull || tokens.radiusMedium || tokens.radiusLarge || "8px",
  useB2CTheme: () => ({
    tokens: themeState.value.tokens,
    isThemed: themeState.value.isThemed,
  }),
  useB2CCTATheme: () => ({
    style: themeState.value.ctaStyle,
    hoverStyle: undefined,
    isThemed: themeState.value.isThemed,
  }),
}));

import { MedusaB2CHomePage } from "./MedusaB2CHomePage";

describe("MedusaB2CHomePage", () => {
  afterEach(() => {
    refreshProducts.mockReset();
    navigateToStore.mockReset();
    themeState.value = {
      tokens: {},
      isThemed: false,
      ctaStyle: undefined,
    };
  });

  it("uses the site name and neutral shell copy in standalone mode", () => {
    render(<MedusaB2CHomePage />);

    expect(refreshProducts).toHaveBeenCalledWith({ limit: 8 });
    expect(screen.getByRole("heading", { name: "Honest Herbalist" })).toHaveStyle({
      fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    });
    expect(screen.getByRole("button", { name: "Shop all products" })).toHaveStyle({
      borderRadius: "8px",
    });
    expect(screen.queryByRole("heading", { name: "Welcome to our store" })).not.toBeInTheDocument();
    expect(screen.queryByText("B2C starter storefront")).not.toBeInTheDocument();
    expect(screen.queryByText("Powered by Medusa B2C starter")).not.toBeInTheDocument();
  });
});
