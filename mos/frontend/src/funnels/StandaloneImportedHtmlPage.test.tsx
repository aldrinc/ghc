import { render, waitFor } from "@testing-library/react";
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StandaloneImportedHtmlPage } from "@/funnels/StandaloneImportedHtmlPage";
import type { PublicCommerceVariant } from "@/types/commerce";
import type { PublicFunnelPage } from "@/types/funnels";

function buildPage(overrides?: Partial<PublicFunnelPage>): PublicFunnelPage {
  return {
    productSlug: "example-product",
    funnelId: "funnel-1",
    publicationId: "publication-1",
    pageId: "page-1",
    slug: "sales-page",
    stage: "sales",
    puckData: {
      root: { props: {} },
      content: [],
      zones: {},
    },
    pageMap: {
      "page-1": "sales-page",
    },
    pageStageMap: {
      "page-1": "sales",
    },
    designSystemTokens: null,
    tracking: null,
    nextPageId: null,
    ...overrides,
  };
}

function buildInstrumentationManifest() {
  return {
    schemaVersion: "imported-html-instrumentation-v1" as const,
    pageStage: "sales" as const,
    bindings: [
      {
        id: "main-cta-checkout",
        type: "checkout" as const,
        event: "click" as const,
        selector: "button#main-cta",
        trackEventType: "sales_to_checkout_click" as const,
        checkout: {
          mode: "public_checkout" as const,
          variantResolver: {
            type: "option_values" as const,
            optionSelectors: [
              { name: "Pack", source: "value" as const, selector: "input#mos-selected-pack" },
              { name: "Flavor", source: "value" as const, selector: "input#mos-selected-flavor" },
            ],
          },
        },
      },
    ],
  };
}

function buildVariants(): PublicCommerceVariant[] {
  return [
    {
      id: "variant-3x-watermelon",
      provider: "shopify",
      price: 8900,
      currency: "usd",
      option_values: {
        Pack: "3x",
        Flavor: "watermelon",
      },
    } as PublicCommerceVariant,
  ];
}

async function captureInjectedDocument(options?: {
  htmlDocument?: string;
  variants?: PublicCommerceVariant[];
  page?: Partial<PublicFunnelPage>;
}) {
  const documentOpenSpy = vi.spyOn(document, "open").mockImplementation(() => document);
  const documentWriteSpy = vi.spyOn(document, "write").mockImplementation(() => undefined);
  const documentCloseSpy = vi.spyOn(document, "close").mockImplementation(() => undefined);

  render(
    <StandaloneImportedHtmlPage
      page={buildPage(options?.page)}
      productSlug="example-product"
      funnelSlug="example-funnel"
      visitorId="visitor-1"
      sessionId="session-1"
      htmlDocument={options?.htmlDocument ?? "<html><body><button>Buy now</button></body></html>"}
      instrumentationManifest={buildInstrumentationManifest()}
      variants={options?.variants ?? buildVariants()}
      pagePathById={{ "page-1": "/example-product/example-funnel/sales-page" }}
      pageStageById={{ "page-1": "sales" }}
    />,
  );

  await waitFor(() => {
    expect(documentOpenSpy).toHaveBeenCalled();
    expect(documentWriteSpy).toHaveBeenCalled();
    expect(documentCloseSpy).toHaveBeenCalled();
  });

  return {
    injectedDocument: String(documentWriteSpy.mock.calls[0]?.[0] || ""),
  };
}

function extractRuntimeScript(injectedDocument: string): string {
  const matches = [...injectedDocument.matchAll(/<script>([\s\S]*?)<\/script>/gi)];
  const runtimeScript = matches.at(-1)?.[1] ?? "";
  if (!runtimeScript.trim()) {
    throw new Error("Failed to extract runtime script from injected standalone document.");
  }
  return runtimeScript;
}

describe("StandaloneImportedHtmlPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    delete window.__mosImportedHtmlStandalonePageId;
  });

  it("injects a lazy commerce loader into the standalone runtime script", async () => {
    const { injectedDocument } = await captureInjectedDocument({
      htmlDocument: "<html><body><button>Buy now</button></body></html>",
      variants: [],
    });
    expect(injectedDocument).toContain("loadCommerceVariants");
    expect(injectedDocument).toContain("/public/funnels/");
    expect(injectedDocument).toContain("/commerce");
    expect(injectedDocument).toContain('void trackEvent(');
    expect(injectedDocument).toContain("prepareCheckoutInBackground");
    expect(injectedDocument).toContain("syncCheckoutBindingWarmState");
    expect(injectedDocument).toContain("/public/checkout/prepare");
    expect(injectedDocument).toContain("consumePreparedCheckout");
    expect(injectedDocument).toContain("scheduleInitialWarmCheckoutBindings");
    expect(injectedDocument).toContain("Preparing secure checkout...");
    expect(injectedDocument).toContain("Secure checkout is unavailable right now.");
    expect(injectedDocument).toContain("aria-busy");
    expect(injectedDocument).toContain("waitForPreparedCheckout(cacheKey)");
    expect(injectedDocument).not.toContain('document.addEventListener("DOMContentLoaded", warmCheckoutBindingsSafely');
    expect(injectedDocument).not.toContain('window.addEventListener("load", warmCheckoutBindingsSafely');
    expect(injectedDocument).not.toContain("window.setTimeout(warmCheckoutBindingsSafely");
  });

  it("reuses the prepared checkout after checkout intent instead of creating a second checkout", async () => {
    const htmlDocument = `
      <html>
        <body>
          <input type="hidden" id="mos-selected-pack" value="3x" />
          <input type="hidden" id="mos-selected-flavor" value="watermelon" />
          <button id="main-cta">Buy now</button>
        </body>
      </html>
    `;
    const { injectedDocument } = await captureInjectedDocument({ htmlDocument });
    const runtimeScript = extractRuntimeScript(injectedDocument);
    const dom = new JSDOM(htmlDocument, {
      pretendToBeVisual: true,
      runScripts: "dangerously",
      url: "https://example.test/sales-page",
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/public/checkout/prepare/") && url.endsWith("/consume")) {
        return new Response(
          JSON.stringify({
            checkoutUrl: "#prepared-checkout",
            sessionId: "checkout-session-1",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      if (url.includes("/public/checkout/prepare")) {
        return new Response(
          JSON.stringify({
            preparedCheckoutId: "prepared-checkout-1",
            status: "ready",
            checkoutUrl: "#prepared-checkout",
            sessionId: "checkout-session-1",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      if (url.includes("/public/events")) {
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      throw new Error(`Unexpected fetch request: ${url}`);
    });
    dom.window.fetch = fetchMock as typeof dom.window.fetch;
    dom.window.console.error = vi.fn();

    dom.window.eval(runtimeScript);
    const countPrepareCalls = () =>
      fetchMock.mock.calls.filter(
        ([input]) =>
          String(input).includes("/public/checkout/prepare") &&
          !String(input).endsWith("/consume"),
      ).length;
    const countConsumeCalls = () =>
      fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/consume")).length;

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(countPrepareCalls()).toBe(1);
    expect(countConsumeCalls()).toBe(0);

    const button = dom.window.document.getElementById("main-cta");
    if (!(button instanceof dom.window.HTMLElement)) {
      throw new Error("Checkout button was not bound in the standalone runtime.");
    }

    button.dispatchEvent(new dom.window.Event("touchstart", { bubbles: true, cancelable: true }));
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(countPrepareCalls()).toBe(1);

    button.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true }));
    await new Promise((resolve) => setTimeout(resolve, 200));

    expect(countPrepareCalls()).toBe(1);
    expect(countConsumeCalls()).toBe(1);
    expect(dom.window.location.hash).toBe("#prepared-checkout");

    dom.window.close();
  });

  it("includes detected purchase mode in checkout selection for imported HTML pages", async () => {
    const htmlDocument = `
      <html>
        <body>
          <div id="quantity-selector" data-mode="subscribe"></div>
          <input type="hidden" id="mos-selected-pack" value="3x" />
          <input type="hidden" id="mos-selected-flavor" value="watermelon" />
          <button id="main-cta">Buy now</button>
        </body>
      </html>
    `;
    const { injectedDocument } = await captureInjectedDocument({ htmlDocument });
    const runtimeScript = extractRuntimeScript(injectedDocument);
    const dom = new JSDOM(htmlDocument, {
      pretendToBeVisual: true,
      runScripts: "dangerously",
      url: "https://example.test/sales-page",
    });

    const observedBodies: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/public/checkout/prepare")) {
        if (init?.body && typeof init.body === "string") {
          observedBodies.push(JSON.parse(init.body) as Record<string, unknown>);
        }
        return new Response(
          JSON.stringify({
            preparedCheckoutId: "prepared-checkout-1",
            status: "ready",
            checkoutUrl: "#prepared-checkout",
            sessionId: "checkout-session-1",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      if (url.includes("/public/events")) {
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      throw new Error(`Unexpected fetch request: ${url}`);
    });
    dom.window.fetch = fetchMock as typeof dom.window.fetch;
    dom.window.console.error = vi.fn();

    dom.window.eval(runtimeScript);
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(observedBodies[0]?.selection).toEqual({
      Pack: "3x",
      Flavor: "watermelon",
      PurchaseMode: "subscribe",
    });

    dom.window.close();
  });

  it("optimizes imported HTML image loading before injecting the document", async () => {
    const { injectedDocument } = await captureInjectedDocument({
      htmlDocument: `
        <html>
          <body>
            <img src="/hero.jpg" alt="Hero" />
            <img src="/gallery.jpg" alt="Gallery" />
          </body>
        </html>
      `,
    });

    expect(injectedDocument).toContain('src="/hero.jpg" alt="Hero" loading="eager" decoding="async" fetchpriority="high"');
    expect(injectedDocument).toContain('src="/gallery.jpg" alt="Gallery" loading="lazy" decoding="async" fetchpriority="low"');
  });

  it("restores Meta page view tracking for standalone sales pages", async () => {
    const { injectedDocument } = await captureInjectedDocument({
      htmlDocument: "<html><body><button id=\"main-cta\">Buy now</button></body></html>",
      page: {
        tracking: {
          provider: "meta",
          metaPixelId: "970868055499017",
        },
      },
    });
    const runtimeScript = extractRuntimeScript(injectedDocument);
    const dom = new JSDOM("<html><body><button id=\"main-cta\">Buy now</button></body></html>", {
      pretendToBeVisual: true,
      runScripts: "dangerously",
      url: "https://example.test/sales-page",
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/public/events")) {
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      throw new Error(`Unexpected fetch request: ${url}`);
    });
    dom.window.fetch = fetchMock as typeof dom.window.fetch;
    dom.window.console.error = vi.fn();
    dom.window.requestAnimationFrame = ((callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    }) as typeof dom.window.requestAnimationFrame;

    dom.window.eval(runtimeScript);
    await new Promise((resolve) => setTimeout(resolve, 20));

    const fbqQueue = dom.window.fbq?.queue ?? [];
    expect(fbqQueue).toEqual(
      expect.arrayContaining([
        ["init", "970868055499017"],
        ["track", "PageView", { page_stage: "sales" }],
        ["track", "ViewContent", { page_stage: "sales" }],
      ]),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/public/events"),
      expect.objectContaining({ method: "POST" }),
    );

    dom.window.close();
  });

  it("tracks EnteredSales for presale-attributed standalone sales pages", async () => {
    const { injectedDocument } = await captureInjectedDocument({
      htmlDocument: "<html><body><button id=\"main-cta\">Buy now</button></body></html>",
      page: {
        tracking: {
          provider: "meta",
          metaPixelId: "970868055499017",
        },
      },
    });
    const runtimeScript = extractRuntimeScript(injectedDocument);
    const dom = new JSDOM("<html><body><button id=\"main-cta\">Buy now</button></body></html>", {
      pretendToBeVisual: true,
      runScripts: "dangerously",
      url: "https://example.test/sales-page?src=presale",
    });
    const eventBodies: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/public/events")) {
        if (typeof init?.body === "string") {
          eventBodies.push(JSON.parse(init.body) as Record<string, unknown>);
        }
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      throw new Error(`Unexpected fetch request: ${url}`);
    });
    dom.window.fetch = fetchMock as typeof dom.window.fetch;
    dom.window.console.error = vi.fn();
    dom.window.requestAnimationFrame = ((callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    }) as typeof dom.window.requestAnimationFrame;

    dom.window.eval(runtimeScript);
    await new Promise((resolve) => setTimeout(resolve, 20));

    const fbqQueue = dom.window.fbq?.queue ?? [];
    expect(fbqQueue).toEqual(
      expect.arrayContaining([
        ["init", "970868055499017"],
        ["track", "PageView", { page_stage: "sales" }],
        ["trackCustom", "EnteredSales", { page_stage: "sales" }],
      ]),
    );
    expect(fbqQueue).not.toContainEqual(["track", "ViewContent", { page_stage: "sales" }]);
    expect(eventBodies[0]).toEqual(
      expect.objectContaining({
        events: [
          expect.objectContaining({
            eventType: "sales_page_view",
            props: expect.objectContaining({
              pageStage: "sales",
              fromPresale: true,
              presaleSignal: "url",
            }),
          }),
        ],
      }),
    );

    dom.window.close();
  });

  it("queues PostHog captures for standalone sales pages when tracking is configured", async () => {
    const { injectedDocument } = await captureInjectedDocument({
      htmlDocument: "<html><body><button id=\"main-cta\">Buy now</button></body></html>",
      page: {
        tracking: {
          provider: "posthog",
          mode: "public_funnel_runtime",
          posthogProjectApiKey: "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
          posthogApiHost: "https://us.i.posthog.com",
          posthogUiHost: "https://us.posthog.com",
          posthogDefaults: "2026-01-30",
          posthogPersonProfiles: "identified_only",
        },
      },
    });
    const runtimeScript = extractRuntimeScript(injectedDocument);
    const dom = new JSDOM("<html><body><button id=\"main-cta\">Buy now</button></body></html>", {
      pretendToBeVisual: true,
      runScripts: "dangerously",
      url: "https://example.test/sales-page?utm_source=meta&utm_campaign=test",
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/public/events")) {
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      throw new Error(`Unexpected fetch request: ${url}`);
    });
    dom.window.fetch = fetchMock as typeof dom.window.fetch;
    dom.window.console.error = vi.fn();
    dom.window.requestAnimationFrame = ((callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    }) as typeof dom.window.requestAnimationFrame;

    dom.window.eval(runtimeScript);
    await new Promise((resolve) => setTimeout(resolve, 20));

    const posthogRoot = dom.window.posthog as {
      _i?: unknown[];
      mosFunnel?: unknown[];
    };
    expect(posthogRoot._i).toEqual(
      expect.arrayContaining([
        [
          "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
          expect.objectContaining({
            api_host: "https://us.i.posthog.com",
            ui_host: "https://us.posthog.com",
            autocapture: false,
            capture_pageview: false,
            capture_pageleave: false,
            defaults: "2026-01-30",
            person_profiles: "identified_only",
          }),
          "mosFunnel",
        ],
      ]),
    );
    expect(posthogRoot.mosFunnel).toEqual(
      expect.arrayContaining([
        [
          "register",
          expect.objectContaining({
            productSlug: "example-product",
            funnelSlug: "example-funnel",
            publicationId: "publication-1",
          }),
        ],
        [
          "capture",
          "PageView",
          expect.objectContaining({
            productSlug: "example-product",
            funnelSlug: "example-funnel",
            publicationId: "publication-1",
            pageId: "page-1",
            pageSlug: "sales-page",
            pageStage: "sales",
            page_stage: "sales",
            visitorId: "visitor-1",
            sessionId: "session-1",
            internal_event_type: "sales_page_view",
            content_category: "sales_page",
            from_presale: false,
            $event_id: expect.any(String),
            utm: {
              utm_campaign: "test",
              utm_source: "meta",
            },
          }),
        ],
        [
          "capture",
          "ViewContent",
          expect.objectContaining({
            productSlug: "example-product",
            funnelSlug: "example-funnel",
            publicationId: "publication-1",
            pageId: "page-1",
            pageSlug: "sales-page",
            pageStage: "sales",
            page_stage: "sales",
            visitorId: "visitor-1",
            sessionId: "session-1",
            internal_event_type: "sales_page_view",
            content_category: "sales_page",
            from_presale: false,
            $event_id: expect.any(String),
            utm: {
              utm_campaign: "test",
              utm_source: "meta",
            },
          }),
        ],
      ]),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/public/events"),
      expect.objectContaining({ method: "POST" }),
    );

    dom.window.close();
  });

  it("defaults standalone PostHog person profiles to always when omitted", async () => {
    const { injectedDocument } = await captureInjectedDocument({
      htmlDocument: "<html><body><button id=\"main-cta\">Buy now</button></body></html>",
      page: {
        tracking: {
          provider: "posthog",
          mode: "public_funnel_runtime",
          posthogProjectApiKey: "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
          posthogApiHost: "https://us.i.posthog.com",
          posthogDefaults: "2026-01-30",
        },
      },
    });
    const runtimeScript = extractRuntimeScript(injectedDocument);
    const dom = new JSDOM("<html><body><button id=\"main-cta\">Buy now</button></body></html>", {
      pretendToBeVisual: true,
      runScripts: "dangerously",
      url: "https://example.test/sales-page",
    });
    dom.window.fetch = vi.fn(async () => new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })) as typeof dom.window.fetch;
    dom.window.console.error = vi.fn();
    dom.window.requestAnimationFrame = ((callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    }) as typeof dom.window.requestAnimationFrame;

    dom.window.eval(runtimeScript);
    await new Promise((resolve) => setTimeout(resolve, 20));

    const posthogRoot = dom.window.posthog as { _i?: unknown[] };
    expect(posthogRoot._i).toEqual(
      expect.arrayContaining([
        [
          "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
          expect.objectContaining({
            person_profiles: "always",
          }),
          "mosFunnel",
        ],
      ]),
    );

    dom.window.close();
  });
});
