import { describe, expect, it } from "vitest";
import {
  buildSitePagePreviewPath,
  buildSitePreviewPath,
  getSitePagePreviewErrorMessage,
  resolveSitePreviewPage,
} from "./sitePreviewRouting";
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
    expect(
      resolveSitePreviewPage(
        [
          ...pages,
          {
            id: "page-checkout",
            name: "Checkout",
            slug: "checkout",
            pageType: "checkout",
            templateId: "medusa-b2c-checkout",
            ordering: 3,
            isEntry: false,
            latestDraftVersionId: "draft-checkout",
            latestApprovedVersionId: "approved-checkout",
          },
        ],
        "us/checkout",
        "page-home",
      )?.id,
    ).toBe("page-checkout");
  });

  it("maps B2C policy routes back to the matching policy page type", () => {
    expect(
      resolveSitePreviewPage(
        [
          ...pages,
          {
            id: "page-privacy",
            name: "Privacy Policy",
            slug: "privacy-policy",
            pageType: "privacy_policy",
            templateId: "medusa-b2c-policy-privacy",
            ordering: 3,
            isEntry: false,
            latestDraftVersionId: "draft-privacy",
            latestApprovedVersionId: "approved-privacy",
          },
        ],
        "us/policies/privacy-policy",
        "page-home",
      )?.id,
    ).toBe("page-privacy");
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

  it("treats imported Medusa sites as B2C storefront previews", () => {
    expect(
      buildSitePagePreviewPath("site-123", pages[0], {
        siteFamily: "imported-template",
        commerceProvider: "medusa",
      }),
    ).toBe("/workspaces/sites/site-123/preview/us");
  });

  it("requires concrete route parameters for dynamic B2C pages", () => {
    expect(
      buildSitePagePreviewPath("site-123", pages[2], { siteFamily: "medusa-b2c-starter" }),
    ).toBeNull();
  });

  it("builds canonical B2C preview routes for collection and category pages when live handles are known", () => {
    expect(
      buildSitePagePreviewPath("site-123", {
        ...pages[1],
        id: "page-collection",
        name: "Collection",
        slug: "collection",
        pageType: "collection",
      }, {
        siteFamily: "medusa-b2c-starter",
        collectionHandle: "featured",
      }),
    ).toBe("/workspaces/sites/site-123/preview/us/collections/featured");

    expect(
      buildSitePagePreviewPath("site-123", {
        ...pages[1],
        id: "page-category",
        name: "Category",
        slug: "category",
        pageType: "category",
      }, {
        siteFamily: "medusa-b2c-starter",
        categoryHandle: "supplements",
      }),
    ).toBe("/workspaces/sites/site-123/preview/us/categories/supplements");
  });

  it("builds canonical B2C preview routes for policy pages", () => {
    expect(
      buildSitePagePreviewPath("site-123", {
        ...pages[0],
        id: "page-privacy",
        name: "Privacy Policy",
        slug: "privacy-policy",
        pageType: "privacy_policy",
        templateId: "medusa-b2c-policy-privacy",
      }, {
        siteFamily: "medusa-b2c-starter",
      }),
    ).toBe("/workspaces/sites/site-123/preview/us/policies/privacy-policy");

    expect(
      buildSitePagePreviewPath("site-123", {
        ...pages[0],
        id: "page-refund",
        name: "Refund Policy",
        slug: "refund-policy",
        pageType: "returns_refunds_policy",
        templateId: "medusa-b2c-policy-returns",
      }, {
        siteFamily: "medusa-b2c-starter",
      }),
    ).toBe("/workspaces/sites/site-123/preview/us/policies/refund-policy");
  });

  it("describes why order transfer previews cannot be opened without concrete params", () => {
    expect(
      getSitePagePreviewErrorMessage({
        ...pages[2],
        pageType: "order_transfer_accept",
      }),
    ).toBe(
      "This order transfer page needs a real order ID and transfer token before it can be previewed from the workspace.",
    );
  });
});
