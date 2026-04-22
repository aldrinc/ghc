import { afterEach, describe, expect, it } from "vitest";
import {
  getStandaloneDefaultPageRoute,
  getStandalonePreloadedFunnelData,
  resolvePreferredPublicFunnelSlug,
} from "@/funnels/runtimeRouting";

declare global {
  interface Window {
    __MOS_DEPLOY_RUNTIME__?: Record<string, unknown>;
  }
}

describe("runtimeRouting standalone preload helpers", () => {
  afterEach(() => {
    delete window.__MOS_DEPLOY_RUNTIME__;
  });

  it("returns the embedded preloaded funnel data when the route matches", () => {
    window.__MOS_DEPLOY_RUNTIME__ = {
      bundleMode: true,
      defaultProductSlug: "070d6cf7",
      defaultFunnelSlug: "ember-funnel",
      defaultEntrySlug: "presales",
      preloadedFunnel: {
        productSlug: "070d6cf7",
        funnelSlug: "ember-funnel",
        meta: {
          productSlug: "070d6cf7",
          funnelSlug: "ember-funnel",
          funnelId: "funnel-id",
          publicationId: "publication-id",
          entrySlug: "presales",
          pages: [{ pageId: "page-1", slug: "presales" }],
        },
        commerce: {
          productSlug: "070d6cf7",
          funnelSlug: "ember-funnel",
          funnelId: "funnel-id",
          product: {
            id: "product-id",
            org_id: "org-id",
            client_id: "client-id",
            name: "Ember",
            variants: [],
            variants_count: 0,
          },
        },
        pages: {
          presales: {
            productSlug: "070d6cf7",
            funnelId: "funnel-id",
            publicationId: "publication-id",
            pageId: "page-1",
            slug: "presales",
            stage: "pre_sales",
            puckData: { root: { props: { title: "Presales" } }, content: [], zones: {} },
            pageMap: { "page-1": "presales" },
            pageStageMap: { "page-1": "pre_sales" },
          },
        },
      },
    };

    expect(getStandaloneDefaultPageRoute()).toEqual({
      productSlug: "070d6cf7",
      funnelSlug: "ember-funnel",
      slug: "presales",
    });

    const preloaded = getStandalonePreloadedFunnelData({
      productSlug: "070d6cf7",
      funnelSlug: "ember-funnel",
    });

    expect(preloaded?.meta?.entrySlug).toBe("presales");
    expect(preloaded?.pages.presales?.slug).toBe("presales");
    expect(preloaded?.commerce?.product.name).toBe("Ember");
  });

  it("returns null when the requested route does not match the embedded funnel", () => {
    window.__MOS_DEPLOY_RUNTIME__ = {
      bundleMode: true,
      preloadedFunnel: {
        productSlug: "070d6cf7",
        funnelSlug: "ember-funnel",
        pages: {},
      },
    };

    const preloaded = getStandalonePreloadedFunnelData({
      productSlug: "other-product",
      funnelSlug: "ember-funnel",
    });

    expect(preloaded).toBeNull();
  });

  it("prefers the sales page when resolving a no-slug public funnel redirect", () => {
    expect(
      resolvePreferredPublicFunnelSlug({
        entrySlug: "presales",
        pages: [
          { pageId: "page-1", slug: "presales" },
          { pageId: "page-2", slug: "sales-page" },
        ],
      }),
    ).toBe("sales-page");
  });

  it("falls back to the published entry slug when there is no sales page", () => {
    expect(
      resolvePreferredPublicFunnelSlug({
        entrySlug: "presales",
        pages: [{ pageId: "page-1", slug: "presales" }],
      }),
    ).toBe("presales");
  });
});
