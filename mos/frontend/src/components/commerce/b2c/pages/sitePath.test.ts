import { describe, expect, it } from "vitest";
import { extractB2CSitePath, resolveB2CSitePath } from "./sitePath";

const runtime = {
  productSlug: "starter-product",
  funnelSlug: "starter-site",
};

describe("B2C site path helpers", () => {
  it("extracts preview-mode storefront paths", () => {
    expect(
      extractB2CSitePath(
        "/workspaces/sites/b8f94ba2-761a-491c-b7b4-05247032b8e6/preview/us/products/the-honest-herbalist-handbook",
        runtime,
      ),
    ).toBe("us/products/the-honest-herbalist-handbook");
  });

  it("extracts hosted storefront paths", () => {
    expect(
      extractB2CSitePath(
        "/f/starter-product/starter-site/us/categories/herbal-guides",
        runtime,
      ),
    ).toBe("us/categories/herbal-guides");
  });

  it("extracts bundle storefront paths", () => {
    expect(
      extractB2CSitePath(
        "/starter-product/starter-site/us/collections/featured",
        runtime,
      ),
    ).toBe("us/collections/featured");
  });

  it("parses preview product routes into the expected site path parts", () => {
    expect(
      resolveB2CSitePath(
        "/workspaces/sites/b8f94ba2-761a-491c-b7b4-05247032b8e6/preview/us/products/the-honest-herbalist-handbook",
        runtime,
      ),
    ).toEqual({
      countryCode: "us",
      pageType: "products",
      handle: "the-honest-herbalist-handbook",
      nestedPath: [],
    });
  });
});
