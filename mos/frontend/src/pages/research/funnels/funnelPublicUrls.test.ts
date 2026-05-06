import { describe, expect, it } from "vitest";
import {
  buildCanonicalPublicPageSlug,
  buildFunnelDeployWorkloadName,
  buildStandalonePublicFunnelPath,
  buildStandalonePublicPagePath,
  joinPublicUrl,
  resolvePrimaryDeployedPublicBaseUrl,
} from "./funnelPublicUrls";

describe("funnelPublicUrls", () => {
  it("builds the funnel-scoped deploy workload name", () => {
    expect(
      buildFunnelDeployWorkloadName({
        client_id: "070d6cf7-1111-2222-3333-444444444444",
        id: "18ac0fe1-aaaa-bbbb-cccc-dddddddddddd",
      }),
    ).toBe("brand-funnels-070d6cf7-18ac0fe1");
  });

  it("builds the standalone public funnel base path", () => {
    expect(
      buildStandalonePublicFunnelPath({
        productSlug: "070d6cf7",
        funnelSlug: "18ac0fe1",
      }),
    ).toBe("/070d6cf7/18ac0fe1");
  });

  it("preserves the sales page slug in the public URL", () => {
    expect(
      buildStandalonePublicPagePath({
        productSlug: "070d6cf7",
        funnelSlug: "18ac0fe1",
        page: {
          id: "page-1",
          name: "Sales Page",
          slug: "sales-page",
          template_id: "sales-pdp",
        },
      }),
    ).toBe("/070d6cf7/18ac0fe1/sales-page");
  });

  it("canonicalizes legacy pre-sales slugs to presales", () => {
    expect(
      buildCanonicalPublicPageSlug({
        id: "page-2",
        name: "Pre-Sales Page",
        slug: "pre-sales",
        template_id: "pre-sales-listicle",
      }),
    ).toBe("presales");

    expect(
      buildStandalonePublicPagePath({
        productSlug: "070d6cf7",
        funnelSlug: "18ac0fe1",
        page: {
          id: "page-2",
          name: "Pre-Sales Page",
          slug: "pre-sales",
          template_id: "pre-sales-listicle",
        },
      }),
    ).toBe("/070d6cf7/18ac0fe1/presales");
  });

  it("preserves custom pre-sales slugs in the public URL", () => {
    expect(
      buildCanonicalPublicPageSlug({
        id: "page-3",
        name: "Focus Story A",
        slug: "focus-story-a",
        template_id: "pre-sales-listicle",
      }),
    ).toBe("focus-story-a");

    expect(
      buildStandalonePublicPagePath({
        productSlug: "070d6cf7",
        funnelSlug: "18ac0fe1",
        page: {
          id: "page-3",
          name: "Focus Story A",
          slug: "focus-story-a",
          template_id: "pre-sales-listicle",
        },
      }),
    ).toBe("/070d6cf7/18ac0fe1/focus-story-a");
  });

  it("prefers the configured deploy domain for public links", () => {
    const baseUrl = resolvePrimaryDeployedPublicBaseUrl({
      configuredDeployDomains: ["shop.shopemberco.com"],
      accessUrl: "https://preview.shopemberco.com/",
    });

    expect(joinPublicUrl(baseUrl, "/070d6cf7/18ac0fe1/sales-page")).toBe(
      "https://shop.shopemberco.com/070d6cf7/18ac0fe1/sales-page",
    );
  });
});
