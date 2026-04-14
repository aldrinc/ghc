import { describe, expect, it } from "vitest";
import {
  matchesVariantOptionValues,
  resolveExternalCheckoutUrlForVariant,
} from "@/funnels/importedHtmlRuntime";

describe("matchesVariantOptionValues", () => {
  it("matches a variant when every option value aligns", () => {
    expect(
      matchesVariantOptionValues(
        {
          id: "variant-1",
          title: "Default",
          price: 4900,
          currency: "USD",
          option_values: { Package: "Starter", Flavor: "Mint" },
        },
        { Package: "Starter", Flavor: "Mint" },
      ),
    ).toBe(true);
  });

  it("returns false when an option differs", () => {
    expect(
      matchesVariantOptionValues(
        {
          id: "variant-1",
          title: "Default",
          price: 4900,
          currency: "USD",
          option_values: { Package: "Starter" },
        },
        { Package: "Clinical" },
      ),
    ).toBe(false);
  });
});

describe("resolveExternalCheckoutUrlForVariant", () => {
  it("returns the mapped URL for the selected variant", () => {
    expect(
      resolveExternalCheckoutUrlForVariant(
        [
          { variantId: "variant-1", url: "https://shop.example.com/cart/starter" },
          { variantId: "variant-2", url: "https://shop.example.com/cart/clinical" },
        ],
        "variant-2",
      ),
    ).toBe("https://shop.example.com/cart/clinical");
  });

  it("returns null when no mapping exists", () => {
    expect(resolveExternalCheckoutUrlForVariant([], "variant-1")).toBeNull();
  });
});
