import { describe, expect, it } from "vitest";

import { mapRuntimeEventToMetaPixel } from "./metaFunnelEvents";

describe("mapRuntimeEventToMetaPixel", () => {
  it("maps funnel entry to Meta ViewContent", () => {
    expect(mapRuntimeEventToMetaPixel({ eventType: "funnel_enter" })).toEqual({
      eventName: "ViewContent",
    });
  });

  it("maps page view to Meta PageView", () => {
    expect(mapRuntimeEventToMetaPixel({ eventType: "page_view" })).toEqual({
      eventName: "PageView",
    });
  });

  it("maps PDP CTA clicks with a variant to InitiateCheckout", () => {
    expect(
      mapRuntimeEventToMetaPixel({
        eventType: "cta_click",
        props: { variantId: "variant_123" },
      }),
    ).toEqual({
      eventName: "InitiateCheckout",
      params: {
        content_ids: ["variant_123"],
        content_type: "product",
        num_items: 1,
      },
    });
  });

  it("does not map generic CTA clicks without a variant", () => {
    expect(
      mapRuntimeEventToMetaPixel({
        eventType: "cta_click",
        props: { href: "https://example.com" },
      }),
    ).toBeNull();
  });
});
