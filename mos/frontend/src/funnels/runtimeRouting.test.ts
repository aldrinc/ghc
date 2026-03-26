import { describe, expect, it } from "vitest";
import { buildPublicFunnelPath, parseSitePath } from "./runtimeRouting";

describe("runtimeRouting", () => {
  it("parses country-prefixed product paths", () => {
    expect(parseSitePath("us/products/face-oil")).toEqual({
      countryCode: "us",
      pageType: "products",
      handle: "face-oil",
      nestedPath: [],
    });
  });

  it("parses nested category paths", () => {
    expect(parseSitePath("us/categories/skincare/serums")).toEqual({
      countryCode: "us",
      pageType: "categories",
      handle: "skincare",
      nestedPath: ["serums"],
    });
  });

  it("builds hosted nested storefront paths", () => {
    expect(
      buildPublicFunnelPath({
        productSlug: "starter-product",
        funnelSlug: "starter-site",
        bundleMode: false,
        sitePath: "us/account/profile",
      }),
    ).toBe("/f/starter-product/starter-site/us/account/profile");
  });

  it("preserves slash-delimited slugs for nested page redirects", () => {
    expect(
      buildPublicFunnelPath({
        productSlug: "starter-product",
        funnelSlug: "starter-site",
        bundleMode: false,
        slug: "account/profile",
      }),
    ).toBe("/f/starter-product/starter-site/account/profile");
  });
});
