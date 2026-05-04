import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ImportedRuntimeSection } from "./ImportedRuntimeSection";

const { apiClientMocks, commerceRuntimeMocks, runtimeMocks } = vi.hoisted(() => ({
  apiClientMocks: {
    get: vi.fn(),
  },
  commerceRuntimeMocks: {
    value: null as
      | {
          siteId?: string | null;
          siteClientId?: string | null;
          loadProductByHandle?: (handle: string) => Promise<unknown>;
          refreshCart?: () => Promise<void>;
          addToCart?: (variantId: string, quantity: number) => Promise<void>;
          replaceCartWithVariant?: (variantId: string, quantity: number) => Promise<unknown>;
          navigateToCheckout?: () => void;
        }
      | null,
  },
  runtimeMocks: {
    resolveRuntimeSitePath: vi.fn((_runtime: unknown, sitePath: string) => `/preview/${sitePath}`),
  },
}));

vi.mock("@/api/client", () => ({
  useApiClient: () => ({
    get: apiClientMocks.get,
  }),
}));

vi.mock("@/components/commerce/b2c", () => ({
  useMaybeB2CRuntime: () => commerceRuntimeMocks.value,
}));

vi.mock("./importedRuntimeFrameAssets", () => ({
  importedRuntimeFrameAssets: {
    reactUmdSource: "window.React = { createElement: () => null, Fragment: 'fragment' };",
    reactDomUmdSource: "window.ReactDOM = { createRoot: () => ({ render: () => null }) };",
  },
}));

vi.mock("@/funnels/puckConfig", async () => {
  const actual = await vi.importActual<typeof import("@/funnels/puckConfig")>("@/funnels/puckConfig");
  return {
    ...actual,
    useFunnelRuntime: () => ({
      productSlug: "honest-herbalist",
      funnelSlug: "preview",
    }),
    resolveRuntimeSitePath: runtimeMocks.resolveRuntimeSitePath,
  };
});

describe("ImportedRuntimeSection", () => {
  it("keeps the same iframe mounted when a nested override item mutates in place", async () => {
    apiClientMocks.get.mockReset();
    commerceRuntimeMocks.value = null;
    const textOverrides = [{ originalText: "Hero", text: "Hero" }];
    const runtimeSource = `const ImportedSection = () => React.createElement("div", null, "Hero");`;

    const { rerender } = render(
      <ImportedRuntimeSection
        id="hero-section"
        sectionLabel="Hero"
        runtimeSource={runtimeSource}
        textOverrides={textOverrides}
      />,
    );

    const frame = (await screen.findByTitle("Hero")) as HTMLIFrameElement;
    const originalSrcdoc = frame.getAttribute("srcdoc") || frame.srcdoc;
    await waitFor(() => {
      expect(originalSrcdoc).toContain('"text":"Hero"');
    });

    textOverrides[0].text = "Updated Hero";
    rerender(
      <ImportedRuntimeSection
        id="hero-section"
        sectionLabel="Hero"
        runtimeSource={runtimeSource}
        textOverrides={textOverrides}
      />,
    );

    await waitFor(() => {
      const currentFrame = screen.getByTitle("Hero") as HTMLIFrameElement;
      expect(currentFrame).toBe(frame);
      expect(currentFrame.getAttribute("srcdoc") || currentFrame.srcdoc).toBe(originalSrcdoc);
    });
  });

  it("scrolls the parent page when the imported runtime requests an in-page anchor navigation", async () => {
    apiClientMocks.get.mockReset();
    commerceRuntimeMocks.value = null;
    const runtimeSource = `const ImportedSection = () => React.createElement("div", null, "Hero");`;
    const target = document.createElement("section");
    target.setAttribute("data-imported-section-id", "product-purchase-section");
    const scrollIntoView = vi.fn();
    target.scrollIntoView = scrollIntoView;
    document.body.appendChild(target);

    render(
      <ImportedRuntimeSection
        id="hero-section"
        sectionLabel="Hero"
        runtimeSource={runtimeSource}
      />,
    );

    await screen.findByTitle("Hero");

    window.dispatchEvent(
      new MessageEvent("message", {
        data: {
          source: "mos-imported-runtime",
          frameId: "imported-runtime-hero-section",
          type: "navigate",
          href: "#product-purchase-section",
        },
      }),
    );

    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
    target.remove();
  });

  it("routes missing imported section anchors back to the storefront home page", async () => {
    apiClientMocks.get.mockReset();
    commerceRuntimeMocks.value = null;
    const runtimeSource = `const ImportedSection = () => React.createElement("div", null, "Hero");`;
    const assign = vi.fn();
    const originalLocation = window.location;

    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        ...originalLocation,
        assign,
      },
    });

    render(
      <ImportedRuntimeSection
        id="hero-section"
        sectionLabel="Hero"
        runtimeSource={runtimeSource}
      />,
    );

    await screen.findByTitle("Hero");

    window.dispatchEvent(
      new MessageEvent("message", {
        data: {
          source: "mos-imported-runtime",
          frameId: "imported-runtime-hero-section",
          type: "navigate",
          href: "#product-purchase-section",
        },
      }),
    );

    expect(runtimeMocks.resolveRuntimeSitePath).toHaveBeenCalledWith(
      expect.objectContaining({
        productSlug: "honest-herbalist",
        funnelSlug: "preview",
      }),
      "",
    );
    expect(assign).toHaveBeenCalledWith("/preview/#product-purchase-section");

    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
  });

  it("hydrates imported purchase runtime data from the preview site's bound product", async () => {
    apiClientMocks.get.mockReset();
    commerceRuntimeMocks.value = {
      siteId: "site-1",
      siteClientId: "client-1",
    };
    apiClientMocks.get.mockImplementation(async (path: string) => {
      if (path === "/sites/site-1?clientId=client-1") {
        return { productId: "product-1" };
      }
      if (path === "/products/product-1") {
        return {
          id: "product-1",
          title: "The Honest Herbalist Handbook",
          client_id: "client-1",
          org_id: "org-1",
          tags: [],
          primary_benefits: [],
          feature_bullets: [],
          disclaimers: [],
          created_at: "2026-04-02T00:00:00Z",
          primary_asset_url: "https://cdn.example.com/book-cover.png",
          assets: [],
          creative_brief_assets: [],
          offers: [],
          variants: [
            {
              id: "variant-local-1",
              title: "Single Book",
              price: 4900,
              currency: "usd",
              external_price_id: "variant_01-single",
            },
            {
              id: "variant-local-2",
              title: "2-Book Bundle",
              price: 8800,
              compare_at_price: 9800,
              currency: "usd",
              external_price_id: "variant_01-bundle",
            },
          ],
        };
      }
      throw new Error(`Unexpected path ${path}`);
    });

    render(
      <ImportedRuntimeSection
        id="purchase-section"
        sectionLabel="Purchase"
        componentName="ProductPurchaseSection"
        runtimeSource={`const ImportedSection = () => React.createElement("div", null, "Purchase");`}
        buttonOverrides={[
          {
            originalText: "Get Your Handbook",
            text: "Get Your Handbook",
            href: "",
            action: "medusa_buy_now",
            selectionStrategy: "omni_selected_tier",
            replaceCart: true,
          },
        ]}
      />,
    );

    const frame = (await screen.findByTitle("Purchase")) as HTMLIFrameElement;
    await waitFor(() => {
      const srcdoc = frame.getAttribute("srcdoc") || frame.srcdoc;
      expect(srcdoc).toContain('"commerceVariantId":"variant_01-bundle"');
      expect(srcdoc).toContain('"priceLabel":"$88"');
      expect(srcdoc).toContain('"compareAtLabel":"$98"');
    });
  });

  it("merges live Medusa variants with the site-bound product assets when a site product has a handle", async () => {
    apiClientMocks.get.mockReset();
    commerceRuntimeMocks.value = {
      siteId: "site-1",
      siteClientId: "client-1",
      loadProductByHandle: vi.fn(async (handle: string) => {
        if (handle !== "ember-brain-clarity-protocol") {
          throw new Error(`Unexpected handle ${handle}`);
        }
        return {
          id: "medusa-product-1",
          handle,
          title: "Ember: Brain Clarity Protocol",
          images: [],
          thumbnail: null,
          variants: [
            {
              id: "variant_30-day",
              title: "30 Day Supply",
              calculated_price: {
                calculated_amount: 4200,
                original_amount: 6700,
                currency_code: "usd",
              },
              prices: [],
            },
            {
              id: "variant_60-day",
              title: "60 Day Supply",
              calculated_price: {
                calculated_amount: 6400,
                original_amount: 13400,
                currency_code: "usd",
              },
              prices: [],
            },
          ],
        };
      }),
    };
    apiClientMocks.get.mockImplementation(async (path: string) => {
      if (path === "/sites/site-1?clientId=client-1") {
        return { productId: "product-1" };
      }
      if (path === "/products/product-1") {
        return {
          id: "product-1",
          title: "Ember: Brain Clarity Protocol",
          client_id: "client-1",
          org_id: "org-1",
          handle: "ember-brain-clarity-protocol",
          tags: [],
          primary_benefits: [],
          feature_bullets: [],
          disclaimers: [],
          created_at: "2026-04-13T00:00:00Z",
          primary_asset_url: "https://cdn.example.com/ember-primary.png",
          assets: [],
          creative_brief_assets: [],
          offers: [],
          variants: [
            {
              id: "variant-local-3",
              title: "90 Day Supply",
              price: 8900,
              compare_at_price: 20100,
              currency: "usd",
              external_price_id: "variant_90-day",
            },
          ],
        };
      }
      throw new Error(`Unexpected path ${path}`);
    });

    render(
      <ImportedRuntimeSection
        id="purchase-section"
        sectionLabel="Purchase"
        componentName="ProductPurchaseSection"
        runtimeSource={`const ImportedSection = () => React.createElement("div", null, "Purchase");`}
        buttonOverrides={[
          {
            originalText: "Order Now",
            text: "Order Now",
            href: "",
            action: "medusa_buy_now",
            selectionStrategy: "omni_selected_tier",
            replaceCart: true,
          },
        ]}
      />,
    );

    const frame = (await screen.findByTitle("Purchase")) as HTMLIFrameElement;
    await waitFor(() => {
      const srcdoc = frame.getAttribute("srcdoc") || frame.srcdoc;
      expect(srcdoc).toContain('"commerceVariantId":"variant_30-day"');
      expect(srcdoc).toContain('"commerceVariantId":"variant_60-day"');
      expect(srcdoc).toContain('"commerceVariantId":"variant_90-day"');
      expect(srcdoc).toContain('"imageUrls":["https://cdn.example.com/ember-primary.png"]');
    });
  });

  it("routes imported buy-now actions through replaceCartWithVariant before checkout navigation", async () => {
    apiClientMocks.get.mockReset();
    const refreshCart = vi.fn(async () => {});
    const addToCart = vi.fn(async () => {});
    const replaceCartWithVariant = vi.fn(async () => ({ id: "cart_123" }));
    const navigateToCheckout = vi.fn();
    commerceRuntimeMocks.value = {
      siteId: "site-1",
      siteClientId: "client-1",
      refreshCart,
      addToCart,
      replaceCartWithVariant,
      navigateToCheckout,
    };
    apiClientMocks.get.mockImplementation(async (path: string) => {
      if (path === "/sites/site-1?clientId=client-1") {
        return { productId: "product-1" };
      }
      if (path === "/products/product-1") {
        return {
          id: "product-1",
          title: "The Honest Herbalist Handbook",
          client_id: "client-1",
          org_id: "org-1",
          tags: [],
          primary_benefits: [],
          feature_bullets: [],
          disclaimers: [],
          created_at: "2026-04-02T00:00:00Z",
          primary_asset_url: "https://cdn.example.com/book-cover.png",
          assets: [],
          creative_brief_assets: [],
          offers: [],
          variants: [
            {
              id: "variant-local-1",
              title: "Single Book",
              price: 4900,
              currency: "usd",
              external_price_id: "variant_01-single",
            },
            {
              id: "variant-local-2",
              title: "2-Book Bundle",
              price: 8800,
              compare_at_price: 9800,
              currency: "usd",
              external_price_id: "variant_01-bundle",
            },
          ],
        };
      }
      throw new Error(`Unexpected path ${path}`);
    });

    render(
      <ImportedRuntimeSection
        id="purchase-section"
        sectionLabel="Purchase"
        componentName="ProductPurchaseSection"
        runtimeSource={`const ImportedSection = () => React.createElement("div", null, "Purchase");`}
        buttonOverrides={[
          {
            originalText: "Get Your Handbook",
            text: "Get Your Handbook",
            href: "",
            action: "medusa_buy_now",
            selectionStrategy: "omni_selected_tier",
            replaceCart: true,
          },
        ]}
      />,
    );

    const frame = (await screen.findByTitle("Purchase")) as HTMLIFrameElement;
    await waitFor(() => {
      const srcdoc = frame.getAttribute("srcdoc") || frame.srcdoc;
      expect(srcdoc).toContain('"commerceVariantId":"variant_01-bundle"');
    });

    window.dispatchEvent(
      new MessageEvent("message", {
        data: {
          source: "mos-imported-runtime",
          frameId: "imported-runtime-purchase-section",
          type: "commerce-action",
          action: "medusa_buy_now",
          selectedOfferTitle: "2-Book Bundle",
          replaceCart: true,
        },
      }),
    );

    await waitFor(() => {
      expect(replaceCartWithVariant).toHaveBeenCalledWith("variant_01-bundle", 1);
      expect(refreshCart).toHaveBeenCalledTimes(1);
      expect(navigateToCheckout).toHaveBeenCalledTimes(1);
    });
    expect(addToCart).not.toHaveBeenCalled();
  });
});
