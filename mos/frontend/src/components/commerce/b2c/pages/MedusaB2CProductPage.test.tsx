import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const loadProductByHandle = vi.fn();
const { themeState } = vi.hoisted(() => ({
  themeState: {
    value: {
      tokens: {},
      isThemed: false,
      ctaStyle: undefined as Record<string, string> | undefined,
    },
  },
}));

vi.mock("@/funnels/puckConfig", () => ({
  useFunnelRuntime: () => ({
    productSlug: "starter-product",
    funnelSlug: "starter-site",
  }),
}));

vi.mock("../B2CRuntimeProvider", () => ({
  useB2CRuntime: () => ({
    siteName: "Honest Herbalist",
    categories: [],
    collections: [],
    cart: { items: [] },
    customer: null,
    navigateToHome: vi.fn(),
    navigateToStore: vi.fn(),
    navigateToCollection: vi.fn(),
    navigateToCategory: vi.fn(),
    currentProduct: {
      id: "prod_123",
      title: "The Honest Herbalist Handbook",
      description: "A product detail test fixture.",
      thumbnail: null,
      variants: [
        {
          id: "variant_123",
          title: "Default",
          prices: [{ amount: 4900, currency_code: "usd" }],
        },
      ],
    },
    cartLoading: false,
    loadProductByHandle,
    addToCart: vi.fn(),
    navigateToCart: vi.fn(),
    navigateToAccount: vi.fn(),
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
  resolveB2CSurfaceRadius: (tokens: { radiusLarge?: string; radiusMedium?: string }) =>
    tokens.radiusLarge || tokens.radiusMedium || "12px",
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

import { MedusaB2CProductPage } from "./MedusaB2CProductPage";

describe("MedusaB2CProductPage", () => {
  afterEach(() => {
    cleanup();
    loadProductByHandle.mockReset();
    themeState.value = {
      tokens: {},
      isThemed: false,
      ctaStyle: undefined,
    };
  });

  it("loads the bound product handle from a workspace preview route", async () => {
    const result = render(
      <MemoryRouter
        initialEntries={[
          "/workspaces/sites/b8f94ba2-761a-491c-b7b4-05247032b8e6/preview/us/products/the-honest-herbalist-handbook",
        ]}
      >
        <MedusaB2CProductPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(loadProductByHandle).toHaveBeenCalledWith("the-honest-herbalist-handbook");
    });

    expect(result.getByTestId("b2c-starter-header")).toBeInTheDocument();
    expect(result.getByTestId("b2c-starter-footer")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Add to Cart" })).toHaveStyle({
      borderRadius: "8px",
    });
    expect(screen.queryByText("B2C starter storefront")).not.toBeInTheDocument();
    expect(screen.queryByText("Powered by Medusa B2C starter")).not.toBeInTheDocument();
  });

  it("applies the site theme to the product title and primary CTA", async () => {
    themeState.value = {
      isThemed: true,
      tokens: {
        colorText: "rgb(17, 24, 39)",
        colorTextMuted: "rgb(75, 85, 99)",
        colorPrimary: "rgb(12, 74, 110)",
        colorPrimaryText: "rgb(255, 255, 255)",
        colorBackgroundAlt: "rgb(240, 249, 255)",
        colorBorder: "rgb(186, 230, 253)",
        fontHeading: "Fraunces",
        radiusFull: "999px",
        radiusLarge: "24px",
        radiusMedium: "16px",
      },
      ctaStyle: {
        backgroundColor: "rgb(12, 74, 110)",
        color: "rgb(255, 255, 255)",
        borderColor: "rgb(12, 74, 110)",
      },
    };

    render(
      <MemoryRouter initialEntries={["/products/the-honest-herbalist-handbook"]}>
        <MedusaB2CProductPage />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "The Honest Herbalist Handbook" })).toHaveStyle({
      fontFamily: "Fraunces",
      color: "rgb(17, 24, 39)",
    });
    expect(await screen.findByRole("button", { name: "Add to Cart" })).toHaveStyle({
      backgroundColor: "rgb(12, 74, 110)",
      color: "rgb(255, 255, 255)",
    });
  });

  it("uses a visible default add to cart CTA when no theme is applied", async () => {
    render(
      <MemoryRouter initialEntries={["/products/the-honest-herbalist-handbook"]}>
        <MedusaB2CProductPage />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("button", { name: "Add to Cart" })).toHaveStyle({
      backgroundColor: "rgb(17, 24, 39)",
      color: "rgb(255, 255, 255)",
    });
  });
});
