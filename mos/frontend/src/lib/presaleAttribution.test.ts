import { beforeEach, describe, expect, it } from "vitest";

import {
  buildPresaleAttributedInternalPath,
  resolvePresaleAttributionSource,
} from "./presaleAttribution";

describe("presaleAttribution", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("adds src=presale and preserves existing query params for internal navigation", () => {
    expect(
      buildPresaleAttributedInternalPath(
        "/f/example-product/example-funnel/sales-page",
        "?utm_source=meta&checkout=success",
      ),
    ).toBe("/f/example-product/example-funnel/sales-page?utm_source=meta&src=presale");
  });

  it("prefers the explicit url param over other attribution signals", () => {
    const storage = window.sessionStorage;
    storage.setItem("from_presale:example-product:example-funnel", "1");

    expect(
      resolvePresaleAttributionSource({
        search: "?src=presale",
        storage,
        productSlug: "example-product",
        funnelSlug: "example-funnel",
        referrer: "https://example.test/f/example-product/example-funnel/presales",
        preSalesPaths: ["/f/example-product/example-funnel/presales"],
        origin: "https://example.test",
      }),
    ).toBe("url");
  });

  it("falls back to session storage when the url param is absent", () => {
    const storage = window.sessionStorage;
    storage.setItem("from_presale:example-product:example-funnel", "1");

    expect(
      resolvePresaleAttributionSource({
        search: "",
        storage,
        productSlug: "example-product",
        funnelSlug: "example-funnel",
      }),
    ).toBe("session");
  });

  it("uses same-origin referrer as a last fallback", () => {
    expect(
      resolvePresaleAttributionSource({
        search: "",
        storage: window.sessionStorage,
        productSlug: "example-product",
        funnelSlug: "example-funnel",
        referrer: "https://example.test/f/example-product/example-funnel/presales?utm_source=meta",
        preSalesPaths: ["/f/example-product/example-funnel/presales"],
        origin: "https://example.test",
      }),
    ).toBe("referrer");
  });
});
