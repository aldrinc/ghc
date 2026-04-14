import { afterEach, describe, expect, it, vi } from "vitest";

const {
  cartCreate,
  cartRetrieve,
  productList,
  regionList,
  getCartId,
  getCountryCode,
  setCartId,
  getMedusaRuntimeConfig,
} = vi.hoisted(() => ({
  cartCreate: vi.fn(),
  cartRetrieve: vi.fn(),
  productList: vi.fn(),
  regionList: vi.fn(),
  getCartId: vi.fn(() => null),
  getCountryCode: vi.fn(() => "us"),
  setCartId: vi.fn(),
  getMedusaRuntimeConfig: vi.fn(() => null),
}));

vi.mock("./config", () => ({
  getMedusaClient: () => ({
    store: {
      cart: {
        create: cartCreate,
        retrieve: cartRetrieve,
      },
      product: {
        list: productList,
      },
      region: {
        list: regionList,
      },
    },
  }),
  getMedusaRuntimeConfig,
}));

vi.mock("./session", () => ({
  getCartId,
  setCartId,
  getAuthToken: vi.fn(),
  setAuthToken: vi.fn(),
  getCountryCode,
}));

import { createCart, getOrCreateCart, getProductByHandle, MedusaApiError } from "./data";

describe("medusa cart creation", () => {
  afterEach(() => {
    cartCreate.mockReset();
    cartRetrieve.mockReset();
    productList.mockReset();
    regionList.mockReset();
    getCartId.mockReset();
    getCartId.mockReturnValue(null);
    getCountryCode.mockReset();
    getCountryCode.mockReturnValue("us");
    getMedusaRuntimeConfig.mockReset();
    getMedusaRuntimeConfig.mockReturnValue(null);
    setCartId.mockReset();
  });

  it("creates carts with a resolved region id for the active country", async () => {
    regionList.mockResolvedValue({
      regions: [
        {
          id: "reg_us",
          name: "United States",
          currency_code: "usd",
          countries: [{ iso_2: "us", display_name: "United States" }],
        },
      ],
    });
    cartCreate.mockResolvedValue({
      cart: {
        id: "cart_123",
        region_id: "reg_us",
        currency_code: "usd",
      },
    });

    const cart = await createCart();

    expect(regionList).toHaveBeenCalledTimes(1);
    expect(cartCreate).toHaveBeenCalledWith({ region_id: "reg_us" });
    expect(setCartId).toHaveBeenCalledWith("cart_123");
    expect(cart.id).toBe("cart_123");
  });

  it("prefers an explicit region id over region lookup", async () => {
    cartCreate.mockResolvedValue({
      cart: {
        id: "cart_456",
        region_id: "reg_direct",
        currency_code: "usd",
      },
    });

    await createCart({ regionId: "reg_direct", countryCode: "ca" });

    expect(regionList).not.toHaveBeenCalled();
    expect(cartCreate).toHaveBeenCalledWith({ region_id: "reg_direct" });
  });

  it("throws a clear error when no Medusa region matches the selected country", async () => {
    regionList.mockResolvedValue({
      regions: [
        {
          id: "reg_ca",
          name: "Canada",
          currency_code: "cad",
          countries: [{ iso_2: "ca", display_name: "Canada" }],
        },
      ],
    });

    await expect(createCart({ countryCode: "us" })).rejects.toEqual(
      expect.objectContaining<Partial<MedusaApiError>>({
        name: "MedusaApiError",
        message: "No Medusa region is configured for country code 'us'.",
      }),
    );
    expect(cartCreate).not.toHaveBeenCalled();
  });

  it("creates a fresh cart when stored cart is already completed", async () => {
    getCartId.mockReturnValue("cart_completed");
    cartRetrieve.mockResolvedValue({
      cart: {
        id: "cart_completed",
        region_id: "reg_us",
        currency_code: "usd",
        completed_at: "2026-03-30T22:00:00.000Z",
      },
    });
    regionList.mockResolvedValue({
      regions: [
        {
          id: "reg_us",
          name: "United States",
          currency_code: "usd",
          countries: [{ iso_2: "us", display_name: "United States" }],
        },
      ],
    });
    cartCreate.mockResolvedValue({
      cart: {
        id: "cart_fresh",
        region_id: "reg_us",
        currency_code: "usd",
      },
    });

    const cart = await getOrCreateCart();

    expect(cartRetrieve).toHaveBeenCalledWith("cart_completed");
    expect(setCartId).toHaveBeenCalledWith(null);
    expect(setCartId).toHaveBeenCalledWith("cart_fresh");
    expect(cart.id).toBe("cart_fresh");
  });

  it("returns the Medusa product when the handle matches exactly", async () => {
    productList.mockResolvedValue({
      products: [{ id: "prod_exact", handle: "omni-creatine-gummy", title: "OMNI Creatine Gummy" }],
    });

    const product = await getProductByHandle("omni-creatine-gummy");

    expect(product).toMatchObject({ id: "prod_exact", handle: "omni-creatine-gummy" });
    expect(productList).toHaveBeenCalledTimes(1);
    expect(productList).toHaveBeenCalledWith({ handle: "omni-creatine-gummy" });
  });

  it("falls back to a partial Medusa handle match when the exact handle is missing", async () => {
    productList
      .mockResolvedValueOnce({ products: [] })
      .mockResolvedValueOnce({
        products: [{ id: "prod_partial", handle: "omni-creatine-gummies", title: "OMNI Creatine Gummies" }],
        count: 1,
        offset: 0,
        limit: 50,
      });

    const product = await getProductByHandle("omni-creatine-gummy");

    expect(product).toMatchObject({ id: "prod_partial", handle: "omni-creatine-gummies" });
    expect(productList).toHaveBeenCalledTimes(2);
    expect(productList).toHaveBeenNthCalledWith(1, { handle: "omni-creatine-gummy" });
    expect(productList).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        limit: 50,
        offset: 0,
      }),
    );
  });
});
