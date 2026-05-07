import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { capturePostHogEvent } from "./posthog";

const tracking = {
  provider: "posthog",
  mode: "public_funnel_runtime",
  posthogProjectApiKey: "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
  posthogApiHost: "https://us.i.posthog.com",
  posthogUiHost: "https://us.posthog.com",
  posthogDefaults: "2026-01-30",
  posthogPersonProfiles: "identified_only" as const,
};

describe("capturePostHogEvent", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-22T12:00:00Z"));
    window.history.replaceState({}, "", "/sales-page?utm_source=meta&utm_campaign=test");
    Object.defineProperty(document, "referrer", {
      configurable: true,
      value: "https://example.com/presale",
    });
    document.cookie = "_fbp=fb.1.1710000000.browser; path=/";
  });

  afterEach(() => {
    vi.useRealTimers();
    delete window.posthog;
    document.cookie = "_fbp=; Max-Age=0; path=/";
    document.cookie = "_fbc=; Max-Age=0; path=/";
    document.head.innerHTML = "";
    document.body.innerHTML = "";
  });

  it("maps sales page views to Meta-matching PostHog captures", () => {
    capturePostHogEvent({
      tracking,
      distinctId: "visitor-1",
      productSlug: "example-product",
      funnelSlug: "example-funnel",
      publicationId: "publication-1",
      pageId: "page-1",
      pageSlug: "sales-page",
      pageStage: "sales",
      sessionId: "session-1",
      eventType: "sales_page_view",
      props: {
        pageStage: "sales",
        fromPresale: true,
      },
      utm: {
        utm_source: "meta",
        utm_campaign: "test",
      },
    });

    const posthogRoot = window.posthog as {
      mosFunnel?: unknown[];
    };
    expect(posthogRoot.mosFunnel).toEqual(
      expect.arrayContaining([
        [
          "capture",
          "PageView",
          expect.objectContaining({
            internal_event_type: "sales_page_view",
            content_category: "sales_page",
            from_presale: true,
            page_stage: "sales",
            $event_id: expect.any(String),
          }),
        ],
        [
          "capture",
          "EnteredSales",
          expect.objectContaining({
            internal_event_type: "sales_page_view",
            content_category: "sales_page",
            from_presale: true,
            page_stage: "sales",
            $event_id: expect.any(String),
          }),
        ],
      ]),
    );
  });

  it("defaults person profiles to identified_only when tracking omits the setting", () => {
    const trackingWithoutPersonProfiles = { ...tracking };
    delete (trackingWithoutPersonProfiles as { posthogPersonProfiles?: string }).posthogPersonProfiles;

    capturePostHogEvent({
      tracking: trackingWithoutPersonProfiles,
      distinctId: "visitor-1",
      productSlug: "example-product",
      funnelSlug: "example-funnel",
      publicationId: "publication-1",
      pageId: "page-1",
      pageSlug: "sales-page",
      pageStage: "sales",
      sessionId: "session-1",
      eventType: "sales_page_view",
      props: {
        pageStage: "sales",
      },
      utm: {},
    });

    const root = window.posthog as { _i?: unknown[] };
    expect(root._i).toEqual(
      expect.arrayContaining([
        [
          "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
          expect.objectContaining({
            capture_pageview: true,
            capture_pageleave: true,
            person_profiles: "identified_only",
          }),
          "mosFunnel",
        ],
      ]),
    );
  });

  it("maps checkout clicks to AddToCart and the checkout transition event", () => {
    capturePostHogEvent({
      tracking,
      distinctId: "visitor-1",
      productSlug: "example-product",
      funnelSlug: "example-funnel",
      publicationId: "publication-1",
      pageId: "page-1",
      pageSlug: "sales-page",
      pageStage: "sales",
      sessionId: "session-1",
      eventType: "sales_to_checkout_click",
      props: {
        pageStage: "sales",
        variantId: "variant-123",
      },
      utm: {},
    });

    const posthogRoot = window.posthog as {
      mosFunnel?: unknown[];
    };
    expect(posthogRoot.mosFunnel).toEqual(
      expect.arrayContaining([
        [
          "capture",
          "AddToCart",
          expect.objectContaining({
            internal_event_type: "sales_to_checkout_click",
            content_ids: ["variant-123"],
            content_type: "product",
            num_items: 1,
            $event_id: expect.any(String),
          }),
        ],
        [
          "capture",
          "SalesToCheckoutClick",
          expect.objectContaining({
            internal_event_type: "sales_to_checkout_click",
            from_stage: "sales",
            to_stage: "checkout",
            $event_id: expect.any(String),
          }),
        ],
      ]),
    );
  });

  it("maps custom page clicks to the CTA link click event name", () => {
    capturePostHogEvent({
      tracking,
      distinctId: "visitor-1",
      productSlug: "example-product",
      funnelSlug: "example-funnel",
      publicationId: "publication-1",
      pageId: "page-1",
      pageSlug: "sales-page",
      pageStage: "sales",
      sessionId: "session-1",
      eventType: "custom_page_click",
      props: {
        pageStage: "sales",
        href: "#shop",
      },
      utm: {},
    });

    const posthogRoot = window.posthog as {
      mosFunnel?: unknown[];
    };
    expect(posthogRoot.mosFunnel).toEqual(
      expect.arrayContaining([
        [
          "capture",
          "CTA Link Click",
          expect.objectContaining({
            internal_event_type: "custom_page_click",
            href: "#shop",
            content_category: "sales_page",
            $event_id: expect.any(String),
          }),
        ],
      ]),
    );
  });
});
