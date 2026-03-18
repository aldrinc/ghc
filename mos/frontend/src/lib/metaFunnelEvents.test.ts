import { describe, expect, it } from "vitest";

import { mapRuntimeEventToMetaPixelEvents } from "./metaFunnelEvents";

describe("mapRuntimeEventToMetaPixelEvents", () => {
  it("maps funnel entries to a Meta custom event", () => {
    expect(
      mapRuntimeEventToMetaPixelEvents({
        eventType: "Entered Funnel",
        props: { pageStage: "pre_sales" },
      }),
    ).toEqual([
      {
        eventName: "Entered Funnel",
        method: "trackCustom",
        params: { page_stage: "pre_sales" },
      },
    ]);
  });

  it("maps pre-sales page views to Meta PageView", () => {
    expect(
      mapRuntimeEventToMetaPixelEvents({
        eventType: "pre_sales_page_view",
        props: { pageStage: "pre_sales" },
      }),
    ).toEqual([{ eventName: "PageView", params: { page_stage: "pre_sales" } }]);
  });

  it("maps sales page views to Meta PageView and ViewContent", () => {
    expect(
      mapRuntimeEventToMetaPixelEvents({
        eventType: "sales_page_view",
        props: { pageStage: "sales" },
      }),
    ).toEqual([
      { eventName: "PageView", params: { page_stage: "sales" } },
      { eventName: "ViewContent", params: { page_stage: "sales" } },
    ]);
  });

  it("maps pre-sales to sales clicks to a Meta custom event", () => {
    expect(
      mapRuntimeEventToMetaPixelEvents({
        eventType: "pre_sales_to_sales_click",
        props: { fromStage: "pre_sales", toStage: "sales" },
      }),
    ).toEqual([
      {
        eventName: "PreSalesToSalesClick",
        method: "trackCustom",
        params: {
          from_stage: "pre_sales",
          to_stage: "sales",
        },
      },
    ]);
  });

  it("maps sales checkout clicks with a variant to AddToCart", () => {
    expect(
      mapRuntimeEventToMetaPixelEvents({
        eventType: "sales_to_checkout_click",
        props: { variantId: "variant_123" },
      }),
    ).toEqual([
      {
        eventName: "AddToCart",
        params: {
          content_ids: ["variant_123"],
          content_type: "product",
          num_items: 1,
        },
      },
    ]);
  });

  it("does not map custom clicks without a variant", () => {
    expect(
      mapRuntimeEventToMetaPixelEvents({
        eventType: "custom_page_click",
        props: { href: "https://example.com" },
      }),
    ).toEqual([]);
  });
});
