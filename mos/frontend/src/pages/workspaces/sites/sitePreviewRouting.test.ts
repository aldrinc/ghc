import { describe, expect, it } from "vitest";
import { buildSitePagePreviewPath, buildSitePreviewPath, resolveSitePreviewPage } from "./sitePreviewRouting";
import type { SitePage } from "@/api/sites";

const pages: SitePage[] = [
  {
    id: "page-home",
    name: "Home",
    slug: "home",
    pageType: "home",
    templateId: "medusa-b2c-home",
    ordering: 0,
    isEntry: true,
    latestDraftVersionId: "draft-home",
    latestApprovedVersionId: "approved-home",
  },
  {
    id: "page-store",
    name: "Storefront",
    slug: "storefront",
    pageType: "store",
    templateId: "medusa-b2c-store",
    ordering: 1,
    isEntry: false,
    latestDraftVersionId: "draft-store",
    latestApprovedVersionId: "approved-store",
  },
  {
    id: "page-product",
    name: "Product",
    slug: "product",
    pageType: "product_detail",
    templateId: "medusa-b2c-product",
    ordering: 2,
    isEntry: false,
    latestDraftVersionId: "draft-product",
    latestApprovedVersionId: "approved-product",
  },
];

describe("sitePreviewRouting", () => {
  it("builds preview paths with and without a route path", () => {
    expect(buildSitePreviewPath("site-123")).toBe("/workspaces/sites/site-123/preview");
    expect(buildSitePreviewPath("site-123", "storefront")).toBe("/workspaces/sites/site-123/preview/storefront");
    expect(buildSitePreviewPath("site-123", "/us/products/face-oil/")).toBe(
      "/workspaces/sites/site-123/preview/us/products/face-oil"
    );
  });

  it("resolves the entry page when no preview path is provided", () => {
    expect(resolveSitePreviewPage(pages, "", "page-home")?.id).toBe("page-home");
  });

  it("prefers an exact slug match when one exists", () => {
    expect(resolveSitePreviewPage(pages, "storefront", "page-home")?.id).toBe("page-store");
  });

  it("maps site-style paths back to the matching site page type", () => {
    expect(resolveSitePreviewPage(pages, "us/products/face-oil", "page-home")?.id).toBe("page-product");
    expect(resolveSitePreviewPage(pages, "us/store", "page-home")?.id).toBe("page-store");
  });

  it("builds canonical B2C preview routes for static storefront pages", () => {
    expect(
      buildSitePagePreviewPath("site-123", pages[0], { siteFamily: "medusa-b2c-starter" }),
    ).toBe("/workspaces/sites/site-123/preview/us");
    expect(
      buildSitePagePreviewPath("site-123", pages[1], { siteFamily: "medusa-b2c-starter" }),
    ).toBe("/workspaces/sites/site-123/preview/us/store");
  });

  it("builds canonical B2C preview routes for bound product pages", () => {
    expect(
      buildSitePagePreviewPath("site-123", pages[2], {
        siteFamily: "medusa-b2c-starter",
        productHandle: "face-oil",
      }),
    ).toBe("/workspaces/sites/site-123/preview/us/products/face-oil");
  });

  it("requires concrete route parameters for dynamic B2C pages", () => {
    expect(
      buildSitePagePreviewPath("site-123", pages[2], { siteFamily: "medusa-b2c-starter" }),
    ).toBeNull();
  });
});
