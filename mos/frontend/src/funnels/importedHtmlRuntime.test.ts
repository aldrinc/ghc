import { describe, expect, it } from "vitest";
import {
  matchesVariantOptionValues,
  optimizeImportedHtmlDocument,
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

describe("optimizeImportedHtmlDocument", () => {
  it("keeps the early above-the-fold images eager and defers the rest", () => {
    const optimized = optimizeImportedHtmlDocument(`
      <!DOCTYPE html>
      <html>
        <body>
          <img src="/flag.png" alt="Flag" class="h-4 w-auto" />
          <img src="/stars.png" alt="Stars" class="h-4 object-contain" />
          <img src="/hero.jpg" alt="Hero" class="w-full block aspect-[21/9] object-cover" />
          <img src="/avatar.jpg" alt="Avatar" class="w-10 h-10 rounded-full" />
          <img src="/gallery-1.jpg" alt="Gallery 1" />
          <img src="/gallery-2.jpg" alt="Gallery 2" loading="lazy" />
        </body>
      </html>
    `);

    expect(optimized).toContain('src="/flag.png" alt="Flag" class="h-4 w-auto" loading="eager" decoding="async" fetchpriority="high"');
    expect(optimized).toContain('src="/stars.png" alt="Stars" class="h-4 object-contain" loading="lazy" decoding="async" fetchpriority="low"');
    expect(optimized).toContain(
      'src="/hero.jpg" alt="Hero" class="w-full block aspect-[21/9] object-cover" loading="eager" decoding="async" fetchpriority="high"',
    );
    expect(optimized).toContain('src="/avatar.jpg" alt="Avatar" class="w-10 h-10 rounded-full" loading="lazy" decoding="async" fetchpriority="low"');
    expect(optimized).toContain('src="/gallery-1.jpg" alt="Gallery 1" loading="lazy" decoding="async" fetchpriority="low"');
    expect(optimized).toContain('src="/gallery-2.jpg" alt="Gallery 2" loading="lazy" decoding="async" fetchpriority="low"');
  });
});
