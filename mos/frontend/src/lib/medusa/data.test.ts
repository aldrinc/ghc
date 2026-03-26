import { afterEach, describe, expect, it, vi } from "vitest";

const {
  cartCreate,
  regionList,
  getCountryCode,
  setCartId,
  getMedusaRuntimeConfig,
} = vi.hoisted(() => ({
  cartCreate: vi.fn(),
  regionList: vi.fn(),
  getCountryCode: vi.fn(() => "us"),
  setCartId: vi.fn(),
  getMedusaRuntimeConfig: vi.fn(() => null),
}));

vi.mock("./config", () => ({
  getMedusaClient: () => ({
    store: {
      cart: {
        create: cartCreate,
      },
      region: {
        list: regionList,
      },
    },
  }),
  getMedusaRuntimeConfig,
}));

vi.mock("./session", () => ({
  getCartId: vi.fn(),
  setCartId,
  getAuthToken: vi.fn(),
  setAuthToken: vi.fn(),
  getCountryCode,
}));

import { createCart, MedusaApiError } from "./data";

describe("medusa cart creation", () => {
  afterEach(() => {
    cartCreate.mockReset();
    regionList.mockReset();
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
});
