import { render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const loadProductByHandle = vi.fn();

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

import { MedusaB2CProductPage } from "./MedusaB2CProductPage";

describe("MedusaB2CProductPage", () => {
  afterEach(() => {
    loadProductByHandle.mockReset();
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
  });
});
