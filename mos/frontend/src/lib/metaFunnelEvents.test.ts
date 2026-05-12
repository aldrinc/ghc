import { describe, expect, it } from "vitest";

import { CTA_LINK_CLICK_EVENT_NAME, mapRuntimeEventToMetaPixelEvents } from "./metaFunnelEvents";

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

  it("maps direct sales page views to Meta PageView and sales conversion events", () => {
    expect(
      mapRuntimeEventToMetaPixelEvents({
        eventType: "sales_page_view",
        props: { pageStage: "sales" },
      }),
    ).toEqual([
      { eventName: "PageView", params: { page_stage: "sales" } },
      { eventName: "Entered Sales Page", method: "trackCustom", params: { page_stage: "sales" } },
      { eventName: "EnteredSales", method: "trackCustom", params: { page_stage: "sales" } },
      { eventName: "ViewContent", params: { page_stage: "sales" } },
    ]);
  });

  it("maps attributed sales page views to Meta PageView and sales conversion events", () => {
    expect(
      mapRuntimeEventToMetaPixelEvents({
        eventType: "sales_page_view",
        props: { pageStage: "sales", fromPresale: true },
      }),
    ).toEqual([
      { eventName: "PageView", params: { page_stage: "sales" } },
      { eventName: "Entered Sales Page", method: "trackCustom", params: { page_stage: "sales" } },
      { eventName: "EnteredSales", method: "trackCustom", params: { page_stage: "sales" } },
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

  it("does not emit sales-entry Meta events for pre-sales to sales clicks", () => {
    const mapped = mapRuntimeEventToMetaPixelEvents({
      eventType: "pre_sales_to_sales_click",
      props: { fromStage: "pre_sales", toStage: "sales", pageStage: "pre_sales" },
    });

    expect(mapped.map((event) => event.eventName)).toEqual(["PreSalesToSalesClick"]);
    expect(mapped).not.toEqual(
      expect.arrayContaining([
        expect.objectContaining({ eventName: "EnteredSales" }),
        expect.objectContaining({ eventName: "Entered Sales Page" }),
      ]),
    );
  });

  it("maps add-to-cart purchase intent to the Meta AddToCart event", () => {
    expect(
      mapRuntimeEventToMetaPixelEvents({
        eventType: "add_to_cart",
        props: { variantId: "variant-123" },
      }),
    ).toEqual([
      {
        eventName: "AddToCart",
        params: {
          content_ids: ["variant-123"],
          content_type: "product",
          num_items: 1,
        },
      },
    ]);
  });

  it("maps sales checkout clicks with a variant to AddToCart and a checkout click", () => {
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
      {
        eventName: "SalesToCheckoutClick",
        method: "trackCustom",
        params: {
          from_stage: "sales",
          to_stage: "checkout",
        },
      },
      {
        eventName: "SalesToCheckoutClicked",
        method: "trackCustom",
        params: {
          from_stage: "sales",
          to_stage: "checkout",
        },
      },
    ]);
  });

  it("maps custom clicks to a CTA link click custom event", () => {
    expect(
      mapRuntimeEventToMetaPixelEvents({
        eventType: "custom_page_click",
        props: { href: "https://example.com" },
      }),
    ).toEqual([
      {
        eventName: CTA_LINK_CLICK_EVENT_NAME,
        method: "trackCustom",
        params: { href: "https://example.com" },
      },
    ]);
  });

  it("maps checkout starts to Meta InitiateCheckout", () => {
    expect(
      mapRuntimeEventToMetaPixelEvents({
        eventType: "checkout_started",
        props: { variantId: "variant_123" },
      }),
    ).toEqual([
      {
        eventName: "InitiateCheckout",
        params: {
          content_ids: ["variant_123"],
          content_type: "product",
          num_items: 1,
        },
      },
    ]);
  });
});
