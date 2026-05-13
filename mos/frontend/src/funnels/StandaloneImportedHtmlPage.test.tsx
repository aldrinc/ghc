import { render, waitFor } from "@testing-library/react";
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StandaloneImportedHtmlPage } from "@/funnels/StandaloneImportedHtmlPage";
import type { PublicCommerceVariant } from "@/types/commerce";
import type { ImportedHtmlInstrumentationManifest, PublicFunnelPage, PublicFunnelStage } from "@/types/funnels";

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
    schemaVersion: "html-deploy-v1" as const,
    htmlArtifactKind: "sales" as const,
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
  instrumentationManifest?: ImportedHtmlInstrumentationManifest;
  variants?: PublicCommerceVariant[];
  page?: Partial<PublicFunnelPage>;
  pagePathById?: Record<string, string>;
  pageStageById?: Record<string, PublicFunnelStage>;
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
      instrumentationManifest={options?.instrumentationManifest ?? buildInstrumentationManifest()}
      variants={options?.variants ?? buildVariants()}
      pagePathById={options?.pagePathById ?? { "page-1": "/example-product/example-funnel/sales-page" }}
      pageStageById={options?.pageStageById ?? { "page-1": "sales" }}
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
    expect(injectedDocument).toContain("Opening secure checkout...");
    expect(injectedDocument).toContain("Secure checkout is unavailable right now.");
    expect(injectedDocument).toContain("aria-busy");
    expect(injectedDocument).toContain("waitForPreparedCheckout(cacheKey)");
    expect(injectedDocument).not.toContain('document.addEventListener("DOMContentLoaded", warmCheckoutBindingsSafely');
    expect(injectedDocument).not.toContain('window.addEventListener("load", warmCheckoutBindingsSafely');
    expect(injectedDocument).not.toContain("window.setTimeout(warmCheckoutBindingsSafely");
  });

  it("submits Klaviyo email capture bindings and identifies PostHog without sending the email to MOS events", async () => {
    const htmlDocument = `
      <html>
        <body>
          <form id="ContactFooter">
            <input name="contact[email]" type="email" value="ALICE@EXAMPLE.COM" />
            <button type="submit">Join</button>
          </form>
        </body>
      </html>
    `;
    const instrumentationManifest: ImportedHtmlInstrumentationManifest = {
      schemaVersion: "html-deploy-v1",
      htmlArtifactKind: "sales",
      pageStage: "sales",
      bindings: [
        {
          id: "tenor-footer-newsletter",
          type: "email_capture",
          event: "submit",
          selector: "form#ContactFooter",
          trackEventType: "email_capture_submit",
          emailCapture: {
            provider: "klaviyo",
            emailSelector: "input[name='contact[email]']",
            source: "shoptenorco_daily_drive_sales_footer",
            successMessage: "You're on the list.",
            klaviyo: {
              publicApiKey: "VHSTxF",
              revision: "2026-04-15",
              listId: "TenorList123",
            },
          },
        },
      ],
    };
    const { injectedDocument } = await captureInjectedDocument({
      htmlDocument,
      instrumentationManifest,
      variants: [],
      page: {
        tracking: {
          provider: "posthog",
          mode: "public_funnel_runtime",
          posthogProjectApiKey: "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
          posthogApiHost: "https://us.i.posthog.com",
          posthogUiHost: "https://us.posthog.com",
          posthogDefaults: "2026-01-30",
          posthogPersonProfiles: "always",
        },
      },
    });
    const runtimeScript = extractRuntimeScript(injectedDocument);
    const dom = new JSDOM(htmlDocument, {
      pretendToBeVisual: true,
      runScripts: "dangerously",
      url: "https://shoptenorco.com/8b89a76d/daily-drive-essentials/sales-page/?utm_source=meta",
    });
    dom.window.HTMLFormElement.prototype.reportValidity = vi.fn(() => true);
    const eventBodies: Array<Record<string, unknown>> = [];
    const klaviyoBodies: Array<Record<string, unknown>> = [];
    const klaviyoHeaders: Array<HeadersInit | undefined> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith("https://a.klaviyo.com/client/subscriptions")) {
        if (typeof init?.body === "string") {
          klaviyoBodies.push(JSON.parse(init.body) as Record<string, unknown>);
        }
        klaviyoHeaders.push(init?.headers);
        return new Response(null, { status: 202 });
      }
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
    (dom.window as typeof dom.window & { klaviyo: unknown[] }).klaviyo = [];

    dom.window.eval(runtimeScript);
    const form = dom.window.document.getElementById("ContactFooter");
    if (!(form instanceof dom.window.HTMLFormElement)) {
      throw new Error("Email capture form was not found.");
    }
    form.dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));

    await waitFor(() => {
      expect(klaviyoBodies).toHaveLength(1);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("https://a.klaviyo.com/client/subscriptions?company_id=VHSTxF"),
      expect.objectContaining({ method: "POST" }),
    );
    expect(klaviyoHeaders[0]).toEqual(
      expect.objectContaining({
        Accept: "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
        revision: "2026-04-15",
      }),
    );
    expect(klaviyoBodies[0]).toEqual(
      expect.objectContaining({
        data: expect.objectContaining({
          type: "subscription",
          relationships: {
            list: {
              data: {
                type: "list",
                id: "TenorList123",
              },
            },
          },
          attributes: expect.objectContaining({
            custom_source: "shoptenorco_daily_drive_sales_footer",
            profile: {
              data: {
                type: "profile",
                attributes: expect.objectContaining({
                  email: "alice@example.com",
                  subscriptions: {
                    email: {
                      marketing: {
                        consent: "SUBSCRIBED",
                      },
                    },
                  },
                  properties: expect.objectContaining({
                    capture_source: "shoptenorco_daily_drive_sales_footer",
                    product_slug: "example-product",
                    funnel_slug: "example-funnel",
                    page_slug: "sales-page",
                    page_stage: "sales",
                    binding_id: "tenor-footer-newsletter",
                    utm: {
                      utm_source: "meta",
                    },
                  }),
                }),
              },
            },
          }),
        }),
      }),
    );
    expect(dom.window.document.body.textContent).toContain("You're on the list.");
    expect(JSON.stringify(eventBodies)).not.toContain("alice@example.com");
    const posthogRoot = (dom.window as typeof dom.window & {
      posthog?: { mosFunnel?: unknown[] };
    }).posthog;
    expect(posthogRoot?.mosFunnel).toEqual(
      expect.arrayContaining([
        [
          "identify",
          "alice@example.com",
          expect.objectContaining({
            email: "alice@example.com",
            capture_source: "shoptenorco_daily_drive_sales_footer",
            external_id: "visitor-1",
            visitor_id: "visitor-1",
          }),
        ],
      ]),
    );
    expect((dom.window as typeof dom.window & { klaviyo: unknown[] }).klaviyo).toEqual(
      expect.arrayContaining([
        ["identify", { email: "alice@example.com" }],
        [
          "track",
          "Email Capture Submitted",
          expect.objectContaining({
            binding_id: "tenor-footer-newsletter",
            source: "shoptenorco_daily_drive_sales_footer",
          }),
        ],
      ]),
    );

    dom.window.close();
  });

  it("redispatches Tenor popup submits only after Klaviyo accepts the subscription", async () => {
    const htmlDocument = `
      <html>
        <body>
          <form data-tenor-mars-offer-form>
            <input name="email" type="email" value="popup@example.com" />
            <button type="submit">Unlock</button>
          </form>
        </body>
      </html>
    `;
    const instrumentationManifest: ImportedHtmlInstrumentationManifest = {
      schemaVersion: "html-deploy-v1",
      htmlArtifactKind: "sales",
      pageStage: "sales",
      bindings: [
        {
          id: "tenor-popup-52-off-email",
          type: "email_capture",
          event: "submit",
          selector: "form[data-tenor-mars-offer-form]",
          trackEventType: "email_capture_submit",
          emailCapture: {
            provider: "klaviyo",
            emailSelector: "input[name='email']",
            source: "shoptenorco_daily_drive_sales_popup",
            successBehavior: "redispatch_submit",
            klaviyo: {
              publicApiKey: "VHSTxF",
              revision: "2026-04-15",
            },
          },
        },
      ],
    };
    const { injectedDocument } = await captureInjectedDocument({
      htmlDocument,
      instrumentationManifest,
      variants: [],
    });
    const runtimeScript = extractRuntimeScript(injectedDocument);
    const dom = new JSDOM(htmlDocument, {
      pretendToBeVisual: true,
      runScripts: "dangerously",
      url: "https://shoptenorco.com/8b89a76d/daily-drive-essentials/sales-page/",
    });
    dom.window.HTMLFormElement.prototype.reportValidity = vi.fn(() => true);
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("https://a.klaviyo.com/client/subscriptions")) {
        return new Response(null, { status: 202 });
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
    const form = dom.window.document.querySelector("form[data-tenor-mars-offer-form]");
    if (!(form instanceof dom.window.HTMLFormElement)) {
      throw new Error("Popup form was not found.");
    }
    let popupSubmitCount = 0;
    form.addEventListener("submit", (event) => {
      popupSubmitCount += 1;
      event.preventDefault();
    });
    form.dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));

    await waitFor(() => {
      expect(popupSubmitCount).toBe(1);
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("https://a.klaviyo.com/client/subscriptions?company_id=VHSTxF"),
      expect.objectContaining({ method: "POST" }),
    );

    dom.window.close();
  });

  it("tracks RMBC sales-page diagnostic views and interactions from the manifest", async () => {
    const htmlDocument = `
      <html>
        <body>
          <section id="offer-stack">Choose your bundle</section>
          <section id="value-stack">Save more with the three-pack</section>
          <section id="price-reveal">$89 today</section>
          <section id="guarantee">90-day guarantee</section>
          <section id="trust">Trusted by daily drivers</section>
          <select id="purchase-mode">
            <option value="subscribe" selected>Subscribe and save</option>
          </select>
          <button id="ingredients">Supplement facts</button>
        </body>
      </html>
    `;
    const instrumentationManifest: ImportedHtmlInstrumentationManifest = {
      schemaVersion: "html-deploy-v1",
      htmlArtifactKind: "sales",
      pageStage: "sales",
      bindings: [],
      offerStacks: [{ id: "offer-stack", selector: "#offer-stack", label: "Offer stack" }],
      valueStacks: [{ id: "value-stack", selector: "#value-stack", label: "Value stack" }],
      priceReveals: [{ id: "price-reveal", selector: "#price-reveal", label: "Price reveal" }],
      guarantees: [{ id: "guarantee", selector: "#guarantee", label: "Guarantee" }],
      trustElements: [{ id: "trust", selector: "#trust", label: "Trust" }],
      selectors: [
        {
          id: "purchase-mode",
          selector: "#purchase-mode",
          label: "Purchase mode",
          event: "change",
          source: "value",
          interactionType: "purchase_mode",
          offerId: "brain-clarity-stack",
        },
      ],
      productDetails: [
        {
          id: "ingredients",
          selector: "#ingredients",
          label: "Supplement facts",
          event: "click",
          source: "text",
          interactionType: "supplement_facts_open",
          elementId: "ingredients",
        },
      ],
    };
    const { injectedDocument } = await captureInjectedDocument({
      htmlDocument,
      instrumentationManifest,
      variants: [],
    });
    const runtimeScript = extractRuntimeScript(injectedDocument);
    const dom = new JSDOM(htmlDocument, {
      pretendToBeVisual: true,
      runScripts: "dangerously",
      url: "https://shoptenorco.com/8b89a76d/daily-drive-essentials/sales-page/",
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
    class ImmediateIntersectionObserver {
      private readonly callback: IntersectionObserverCallback;

      constructor(callback: IntersectionObserverCallback) {
        this.callback = callback;
      }

      observe(element: Element) {
        this.callback(
          [{ isIntersecting: true, intersectionRatio: 1, target: element } as IntersectionObserverEntry],
          this as unknown as IntersectionObserver,
        );
      }

      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
    }
    Object.defineProperty(dom.window, "IntersectionObserver", {
      configurable: true,
      writable: true,
      value: ImmediateIntersectionObserver,
    });
    dom.window.fetch = fetchMock as typeof dom.window.fetch;
    dom.window.console.error = vi.fn();
    dom.window.requestAnimationFrame = ((callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    }) as typeof dom.window.requestAnimationFrame;

    dom.window.eval(runtimeScript);
    const purchaseMode = dom.window.document.getElementById("purchase-mode");
    const ingredients = dom.window.document.getElementById("ingredients");
    if (!(purchaseMode instanceof dom.window.HTMLSelectElement) || !(ingredients instanceof dom.window.HTMLElement)) {
      throw new Error("RMBC diagnostic controls were not found.");
    }
    purchaseMode.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
    ingredients.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true }));

    await waitFor(() => {
      const trackedEvents = eventBodies.flatMap((body) =>
        Array.isArray(body.events) ? (body.events as Array<Record<string, unknown>>) : [],
      );
      const eventTypes = trackedEvents.map((event) => event.eventType);
      expect(eventTypes).toEqual(
        expect.arrayContaining([
          "offer_stack_view",
          "value_stack_view",
          "price_reveal_view",
          "guarantee_view",
          "trust_element_view",
          "selector_interaction",
          "subscription_selected",
          "product_detail_interaction",
        ]),
      );
      expect(trackedEvents.find((event) => event.eventType === "selector_interaction")?.props).toEqual(
        expect.objectContaining({
          selectorId: "purchase-mode",
          selectedValue: "subscribe",
          interactionType: "purchase_mode",
          offer_id: "brain-clarity-stack",
        }),
      );
      expect(trackedEvents.find((event) => event.eventType === "product_detail_interaction")?.props).toEqual(
        expect.objectContaining({
          productDetailId: "ingredients",
          element_id: "ingredients",
          selectedValue: "Supplement facts",
        }),
      );
    });

    dom.window.close();
  });

  it("tracks quiz manifest targets with RMBC diagnostic properties", async () => {
    const htmlDocument = `
      <html>
        <body>
          <section id="lead">Lead</section>
          <section id="q1">Question one</section>
          <button id="o1">Often</button>
          <section id="result">Result</section>
          <section id="mechanism">Mechanism</section>
          <a id="to-sales">Continue</a>
        </body>
      </html>
    `;
    const instrumentationManifest: ImportedHtmlInstrumentationManifest = {
      schemaVersion: "html-deploy-v1",
      htmlArtifactKind: "quiz",
      pageStage: "pre_sales",
      quizId: "brain-quiz",
      quizVersion: "v1",
      quizVariant: "control",
      bindings: [
        {
          id: "to-sales",
          type: "internal_navigation",
          selector: "#to-sales",
          event: "click",
          targetPageId: "page-sales",
          trackEventType: "pre_sales_to_sales_click",
        },
      ],
      ctas: [{ id: "to-sales", selector: "#to-sales", ctaPosition: 1 }],
      quizLeads: [{ id: "lead", selector: "#lead", quizId: "brain-quiz" }],
      quizQuestions: [
        {
          id: "q1",
          selector: "#q1",
          quizId: "brain-quiz",
          questionId: "q1",
          questionIndex: 1,
          questionRole: "symptom",
        },
      ],
      quizOptions: [
        {
          id: "o1",
          selector: "#o1",
          quizId: "brain-quiz",
          questionId: "q1",
          optionId: "o1",
          optionRole: "high_intent",
        },
      ],
      quizResults: [{ id: "result", selector: "#result", resultId: "fog-pattern" }],
      quizMechanisms: [{ id: "mechanism", selector: "#mechanism", mechanismName: "daily-drive" }],
    };
    const { injectedDocument } = await captureInjectedDocument({
      htmlDocument,
      instrumentationManifest,
      variants: [],
      page: {
        pageId: "page-quiz",
        slug: "quiz",
        stage: "pre_sales",
        nextPageId: "page-sales",
        pageMap: { "page-quiz": "quiz", "page-sales": "sales-page" },
        pageStageMap: { "page-quiz": "pre_sales", "page-sales": "sales" },
      },
      pagePathById: {
        "page-quiz": "/example-product/example-funnel/quiz",
        "page-sales": "/example-product/example-funnel/sales-page",
      },
      pageStageById: {
        "page-quiz": "pre_sales",
        "page-sales": "sales",
      },
    });
    const runtimeScript = extractRuntimeScript(injectedDocument);
    const dom = new JSDOM(htmlDocument, {
      pretendToBeVisual: true,
      runScripts: "dangerously",
      url: "https://example.test/quiz",
    });
    const eventBodies: Array<Record<string, unknown>> = [];
    dom.window.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
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
    }) as typeof dom.window.fetch;
    class ImmediateIntersectionObserver {
      private readonly callback: IntersectionObserverCallback;

      constructor(callback: IntersectionObserverCallback) {
        this.callback = callback;
      }

      observe(element: Element) {
        this.callback(
          [{ isIntersecting: true, intersectionRatio: 1, target: element } as IntersectionObserverEntry],
          this as unknown as IntersectionObserver,
        );
      }

      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
    }
    Object.defineProperty(dom.window, "IntersectionObserver", {
      configurable: true,
      writable: true,
      value: ImmediateIntersectionObserver,
    });
    dom.window.requestAnimationFrame = ((callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    }) as typeof dom.window.requestAnimationFrame;

    dom.window.eval(runtimeScript);

    await waitFor(() => {
      const trackedEvents = eventBodies.flatMap((body) =>
        Array.isArray(body.events) ? (body.events as Array<Record<string, unknown>>) : [],
      );
      expect(trackedEvents.map((event) => event.eventType)).toEqual(
        expect.arrayContaining([
          "quiz_lead_viewed",
          "quiz_question_viewed",
          "quiz_option_presented",
          "quiz_result_viewed",
          "quiz_mechanism_viewed",
          "quiz_cta_viewed",
        ]),
      );
      expect(trackedEvents.find((event) => event.eventType === "quiz_question_viewed")?.props).toEqual(
        expect.objectContaining({
          quiz_id: "brain-quiz",
          question_id: "q1",
          question_index: 1,
          question_role: "symptom",
        }),
      );
      expect(trackedEvents.find((event) => event.eventType === "quiz_option_presented")?.props).toEqual(
        expect.objectContaining({
          option_id: "o1",
          option_role: "high_intent",
        }),
      );
    });

    dom.window.close();
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
    let consumeResolved = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/public/checkout/prepare/") && url.endsWith("/consume")) {
        await new Promise((resolve) => setTimeout(resolve, 150));
        consumeResolved = true;
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
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(countPrepareCalls()).toBe(1);
    expect(countConsumeCalls()).toBe(1);
    expect(dom.window.location.hash).toBe("#prepared-checkout");
    expect(consumeResolved).toBe(false);
    await new Promise((resolve) => setTimeout(resolve, 180));
    expect(consumeResolved).toBe(true);

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
      url: "https://example.test/sales-page?fbclid=fb-click-123&experiment_id=exp-1&debug=1",
    });
    dom.window.document.cookie = "_fbp=fb.1.1710000000.browser";
    dom.window.document.cookie = "_fbc=fb.1.1710000001.fb-click-123";

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
    expect(observedBodies[0]).toEqual(
      expect.objectContaining({
        clickId: "fb-click-123",
        clickIdType: "fbclid",
        fbp: "fb.1.1710000000.browser",
        fbc: "fb.1.1710000001.fb-click-123",
        externalId: "visitor-1",
        eventSourceUrl: expect.stringContaining("fbclid=fb-click-123"),
        pageVariant: "sales-page",
        experimentId: "exp-1",
        ctaId: "main-cta-checkout",
      }),
    );
    expect(observedBodies[0]).not.toHaveProperty("urlParams");

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

  it("tracks sales-entry events for direct standalone sales page loads", async () => {
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
        ["init", "970868055499017", expect.objectContaining({ external_id: "visitor-1" })],
        [
          "track",
          "PageView",
          expect.objectContaining({ page_stage: "sales", external_id: "visitor-1" }),
          expect.objectContaining({ eventID: expect.any(String) }),
        ],
        [
          "trackCustom",
          "EnteredSales",
          expect.objectContaining({ page_stage: "sales", external_id: "visitor-1" }),
          expect.objectContaining({ eventID: expect.any(String) }),
        ],
        [
          "track",
          "ViewContent",
          expect.objectContaining({ page_stage: "sales", external_id: "visitor-1" }),
          expect.objectContaining({ eventID: expect.any(String) }),
        ],
      ]),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/public/events"),
      expect.objectContaining({ method: "POST" }),
    );

    dom.window.close();
  });

  it("maps standalone add-to-cart and checkout-started events to Meta commerce events", async () => {
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

    const analytics = (dom.window as typeof dom.window & {
      MOSStandaloneAnalytics?: {
        trackEvent: (eventType: string, props?: Record<string, unknown>) => void;
      };
    }).MOSStandaloneAnalytics;
    analytics?.trackEvent("sales_to_checkout_click", { variantId: "variant-3x-watermelon" });
    analytics?.trackEvent("checkout_started", { variantId: "variant-3x-watermelon" });

    const fbqQueue = dom.window.fbq?.queue ?? [];
    expect(fbqQueue).toEqual(
      expect.arrayContaining([
        [
          "track",
          "AddToCart",
          expect.objectContaining({
            content_ids: ["variant-3x-watermelon"],
            content_type: "product",
            num_items: 1,
          }),
          expect.objectContaining({ eventID: expect.any(String) }),
        ],
        [
          "track",
          "InitiateCheckout",
          expect.objectContaining({
            content_ids: ["variant-3x-watermelon"],
            content_type: "product",
            num_items: 1,
          }),
          expect.objectContaining({ eventID: expect.any(String) }),
        ],
      ]),
    );

    dom.window.close();
  });

  it("tracks EnteredSales for presale-attributed standalone sales page loads", async () => {
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
        ["init", "970868055499017", expect.objectContaining({ external_id: "visitor-1" })],
        [
          "track",
          "PageView",
          expect.objectContaining({ page_stage: "sales", external_id: "visitor-1" }),
          expect.objectContaining({ eventID: expect.any(String) }),
        ],
        [
          "trackCustom",
          "EnteredSales",
          expect.objectContaining({ page_stage: "sales", external_id: "visitor-1" }),
          expect.objectContaining({ eventID: expect.any(String) }),
        ],
        [
          "track",
          "ViewContent",
          expect.objectContaining({ page_stage: "sales", external_id: "visitor-1" }),
          expect.objectContaining({ eventID: expect.any(String) }),
        ],
      ]),
    );
    expect(eventBodies[0]).toEqual(
      expect.objectContaining({
        events: [
          expect.objectContaining({
            eventId: expect.any(String),
            eventType: "sales_page_view",
            props: expect.objectContaining({
              eventId: expect.any(String),
              pageStage: "sales",
              external_id: "visitor-1",
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
	      url: "https://example.test/sales-page?utm_source=meta&utm_campaign=test&fbclid=fb-click-456",
	    });
	    dom.window.document.cookie = "_fbp=fb.1.1710000000.browser";
	    dom.window.document.cookie = "_fbc=fb.1.1710000001.fb-click-456";
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

    const posthogRoot = dom.window.posthog as {
      _i?: unknown[];
      mosFunnel?: unknown[] & { __loaded?: true };
    };
    if (posthogRoot.mosFunnel) {
      posthogRoot.mosFunnel.__loaded = true;
    }
    expect(posthogRoot._i).toEqual(
      expect.arrayContaining([
        [
          "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
          expect.objectContaining({
            api_host: "https://us.i.posthog.com",
            ui_host: "https://us.posthog.com",
            autocapture: false,
            capture_pageview: true,
            capture_pageleave: true,
            defaults: "2026-01-30",
            person_profiles: "identified_only",
          }),
          "mosFunnel",
        ],
      ]),
    );
    await waitFor(() => {
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
            "sales_page_view",
            expect.objectContaining({
              productSlug: "example-product",
              product_slug: "example-product",
              funnelSlug: "example-funnel",
              funnel_slug: "example-funnel",
              publicationId: "publication-1",
              publication_id: "publication-1",
              pageId: "page-1",
              page_id: "page-1",
              pageSlug: "sales-page",
              page_slug: "sales-page",
              pageStage: "sales",
              page_stage: "sales",
              internal_event_type: "sales_page_view",
              canonical_event_type: "sales_page_view",
              posthog_event_role: "canonical",
              content_category: "sales_page",
              from_presale: false,
              $event_id: expect.any(String),
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
              external_id: "visitor-1",
              sessionId: "session-1",
              internal_event_type: "sales_page_view",
              content_category: "sales_page",
              from_presale: false,
              meta_event_name: "PageView",
              meta_event_id: expect.any(String),
              action_source: "website",
              fbp: "fb.1.1710000000.browser",
              fbc: "fb.1.1710000001.fb-click-456",
              fbclid: "fb-click-456",
              event_source_url: expect.stringContaining("fbclid=fb-click-456"),
              $event_id: expect.any(String),
              utm: {
                utm_campaign: "test",
                utm_source: "meta",
              },
            }),
          ],
          [
            "capture",
            "EnteredSales",
            expect.objectContaining({
              productSlug: "example-product",
              funnelSlug: "example-funnel",
              publicationId: "publication-1",
              pageId: "page-1",
              pageSlug: "sales-page",
              pageStage: "sales",
              page_stage: "sales",
              visitorId: "visitor-1",
              external_id: "visitor-1",
              sessionId: "session-1",
              internal_event_type: "sales_page_view",
              content_category: "sales_page",
              from_presale: false,
              meta_event_name: "EnteredSales",
              meta_event_id: expect.any(String),
              action_source: "website",
              fbp: "fb.1.1710000000.browser",
              fbc: "fb.1.1710000001.fb-click-456",
              fbclid: "fb-click-456",
              event_source_url: expect.stringContaining("fbclid=fb-click-456"),
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
              external_id: "visitor-1",
              sessionId: "session-1",
              internal_event_type: "sales_page_view",
              content_category: "sales_page",
              from_presale: false,
              meta_event_name: "ViewContent",
              meta_event_id: expect.any(String),
              action_source: "website",
              fbp: "fb.1.1710000000.browser",
              fbc: "fb.1.1710000001.fb-click-456",
              fbclid: "fb-click-456",
              event_source_url: expect.stringContaining("fbclid=fb-click-456"),
              $event_id: expect.any(String),
              utm: {
                utm_campaign: "test",
                utm_source: "meta",
              },
            }),
          ],
        ]),
      );
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/public/events"),
      expect.objectContaining({ method: "POST" }),
    );

    dom.window.close();
  });

  it("queues RMBC PostHog events and CTA props for standalone presales pages", async () => {
    const htmlDocument = `
      <html>
        <body>
          <section id="hero">
            <a id="to-sales" href="#">Try it now</a>
          </section>
          <section id="proof">Clinically backed proof</section>
        </body>
      </html>
    `;
    const instrumentationManifest: ImportedHtmlInstrumentationManifest = {
      schemaVersion: "html-deploy-v1",
      htmlArtifactKind: "listicle",
      pageStage: "pre_sales",
      sections: [{ id: "hero", selector: "#hero", label: "Hero" }],
      proofs: [{ id: "proof", selector: "#proof", proofType: "clinical", sectionId: "hero" }],
      ctas: [{ id: "primary-cta", selector: "#to-sales", ctaPosition: 1 }],
      bindings: [
        {
          id: "primary-cta",
          type: "internal_navigation",
          event: "click",
          selector: "#to-sales",
          targetPageId: "page-sales",
          trackEventType: "pre_sales_to_sales_click",
        },
      ],
    };
    const { injectedDocument } = await captureInjectedDocument({
      htmlDocument,
      instrumentationManifest,
      variants: [],
      page: {
        stage: "pre_sales",
        slug: "10-reasons-glp",
        pageMap: {
          "page-1": "10-reasons-glp",
          "page-sales": "sales-page",
        },
        pageStageMap: {
          "page-1": "pre_sales",
          "page-sales": "sales",
        },
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
      pagePathById: {
        "page-1": "/example-product/example-funnel/10-reasons-glp",
        "page-sales": "/example-product/example-funnel/sales-page",
      },
      pageStageById: {
        "page-1": "pre_sales",
        "page-sales": "sales",
      },
    });
    const runtimeScript = extractRuntimeScript(injectedDocument);
    const dom = new JSDOM(htmlDocument, {
      pretendToBeVisual: true,
      runScripts: "dangerously",
      url: "https://example.test/10-reasons-glp",
    });
    dom.window.document.cookie = "_fbp=fb.1.1710000000.browser";
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
    class ImmediateIntersectionObserver {
      private readonly callback: IntersectionObserverCallback;

      constructor(callback: IntersectionObserverCallback) {
        this.callback = callback;
      }

      observe(element: Element) {
        this.callback(
          [
            {
              isIntersecting: true,
              intersectionRatio: 1,
              target: element,
            } as IntersectionObserverEntry,
          ],
          this as unknown as IntersectionObserver,
        );
      }

      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
    }
    dom.window.IntersectionObserver = ImmediateIntersectionObserver as typeof dom.window.IntersectionObserver;

    dom.window.eval(runtimeScript);
    const posthogRoot = dom.window.posthog as {
      mosFunnel?: unknown[] & { __loaded?: true };
    };
    if (posthogRoot.mosFunnel) {
      posthogRoot.mosFunnel.__loaded = true;
    }
    await new Promise((resolve) => setTimeout(resolve, 20));
    dom.window.document.querySelector<HTMLAnchorElement>("#to-sales")?.click();
    await new Promise((resolve) => setTimeout(resolve, 400));

    expect(posthogRoot.mosFunnel).toEqual(
      expect.arrayContaining([
        [
          "capture",
          "pre_sales_page_view",
          expect.objectContaining({
            internal_event_type: "pre_sales_page_view",
            canonical_event_type: "pre_sales_page_view",
            posthog_event_role: "canonical",
            content_category: "pre_sales_page",
          }),
        ],
        [
          "capture",
          "presell_page_view",
          expect.objectContaining({
            internal_event_type: "pre_sales_page_view",
            canonical_event_type: "presell_page_view",
            posthog_event_role: "rmbc_alias",
          }),
        ],
        [
          "capture",
          "section_view",
          expect.objectContaining({
            sectionId: "hero",
            section_id: "hero",
            depth_pct: expect.any(Number),
          }),
        ],
        [
          "capture",
          "proof_view",
          expect.objectContaining({
            proofId: "proof",
            proof_id: "proof",
            proofType: "clinical",
            proof_type: "clinical",
          }),
        ],
        [
          "capture",
          "cta_view",
          expect.objectContaining({
            ctaId: "primary-cta",
            cta_id: "primary-cta",
            ctaPosition: 1,
            cta_position: 1,
          }),
        ],
        [
          "capture",
          "cta_click",
          expect.objectContaining({
            internal_event_type: "pre_sales_to_sales_click",
            canonical_event_type: "cta_click",
            posthog_event_role: "rmbc_alias",
            ctaId: "primary-cta",
            cta_id: "primary-cta",
            ctaPosition: 1,
            cta_position: 1,
            destinationUrl: expect.stringMatching(
              /\/sales-page\?.*rmbc_session_id=session-1.*rmbc_anonymous_id=visitor-1.*rmbc_click_id=/,
            ),
            destination_url: expect.stringMatching(
              /\/sales-page\?.*rmbc_session_id=session-1.*rmbc_anonymous_id=visitor-1.*rmbc_click_id=/,
            ),
            clickId: expect.stringMatching(/^click_publication-1_page-1_primary-cta_1_/),
            click_id: expect.stringMatching(/^click_publication-1_page-1_primary-cta_1_/),
            clickIdType: "rmbc_click_id",
            click_id_type: "rmbc_click_id",
            rmbcClickId: expect.stringMatching(/^click_publication-1_page-1_primary-cta_1_/),
            rmbc_click_id: expect.stringMatching(/^click_publication-1_page-1_primary-cta_1_/),
          }),
        ],
      ]),
    );
    const capturedNames = (posthogRoot.mosFunnel || [])
      .filter((entry): entry is unknown[] => Array.isArray(entry) && entry[0] === "capture")
      .map((entry) => entry[1]);
    expect(capturedNames).not.toContain("EnteredSales");
    expect(capturedNames).not.toContain("Entered Sales Page");

    dom.window.close();
  });
});
