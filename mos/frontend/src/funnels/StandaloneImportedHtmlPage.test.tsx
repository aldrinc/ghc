import { render, waitFor } from "@testing-library/react";
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StandaloneImportedHtmlPage } from "@/funnels/StandaloneImportedHtmlPage";
import type { PublicCommerceVariant } from "@/types/commerce";
import type { PublicFunnelPage } from "@/types/funnels";

function buildPage(): PublicFunnelPage {
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
}) {
  const documentOpenSpy = vi.spyOn(document, "open").mockImplementation(() => document);
  const documentWriteSpy = vi.spyOn(document, "write").mockImplementation(() => undefined);
  const documentCloseSpy = vi.spyOn(document, "close").mockImplementation(() => undefined);

  render(
    <StandaloneImportedHtmlPage
      page={buildPage()}
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
});
