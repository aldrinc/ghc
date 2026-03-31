import React from "react";
import ReactDOM from "react-dom/client";

import { DesignSystemProvider } from "@/components/design-system/DesignSystemProvider";
import {
  B2CRuntimeContext,
  type B2CRuntimeContextValue,
} from "@/components/commerce/b2c/B2CRuntimeProvider";
import { MedusaB2CHomePage } from "@/components/commerce/b2c/pages/MedusaB2CHomePage";

const importedCandidate = {
  dataTheme: "light",
  fontUrls: [],
  cssVars: {
    "--font-sans": "Satoshi, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Inter, Arial, Apple Color Emoji, Segoe UI Emoji",
    "--font-heading": "Satoshi, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Inter, Arial, Apple Color Emoji, Segoe UI Emoji",
    "--font-cta": "Satoshi, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Inter, Arial, Apple Color Emoji, Segoe UI Emoji",
    "--color-brand": "rgb(0, 34, 102)",
    "--color-text": "rgb(26, 26, 26)",
    "--color-muted": "rgba(26, 26, 26, 0.76)",
    "--color-border": "rgba(0, 34, 102, 0.18)",
    "--color-bg": "rgb(245, 248, 255)",
    "--color-page-bg": "rgb(245, 248, 255)",
    "--color-page-bg-secondary": "rgb(235, 242, 255)",
    "--hero-bg": "rgb(235, 242, 255)",
    "--pitch-bg": "rgb(235, 242, 255)",
    "--color-soft": "rgb(235, 242, 255)",
    "--color-cta": "rgb(38, 83, 146)",
    "--color-cta-text": "#ffffff",
    "--color-cta-icon": "rgb(0, 34, 102)",
    "--radius-md": "14px",
    "--radius-lg": "18px",
    "--radius-full": "999px",
    "--pdp-radius-pill": "999px",
  },
  brand: { name: "validated-loop-react-export" },
  palette: {
    primary: "rgb(38, 83, 146)",
    secondary: "rgb(0, 34, 102)",
    surface: "rgb(235, 242, 255)",
    accent: "rgb(220, 38, 38)",
    text: "rgb(26, 26, 26)",
    background: "rgb(245, 248, 255)",
  },
  fonts: {
    primary: "Satoshi",
    heading: "Satoshi",
    body: "Satoshi",
    cta: "Satoshi",
  },
  cta: { style: "solid", borderRadius: "999px" },
  diagnostics: {
    sourceInputs: { designSystemHtmlPath: "design-system/design-system.html" },
    fidelity: {
      fontDelivery: "family_name_only",
      backgroundStrategy:
        "page and section surfaces derive from background and surface roles; accent is excluded from hero and pitch backgrounds",
    },
    promotionReadiness: {
      ready: false,
      missingFields: ["brand.logoAssetPublicId"],
    },
  },
};

const baselinePreset = {
  dataTheme: "light",
  fontUrls: [],
  cssVars: {
    "--font-sans": "Poppins, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Inter, Arial, Apple Color Emoji, Segoe UI Emoji",
    "--font-heading": "Merriweather, ui-serif, Georgia, Times New Roman, Times, serif",
    "--font-cta": "Poppins, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Inter, Arial, Apple Color Emoji, Segoe UI Emoji",
    "--color-brand": "#061a70",
    "--color-text": "#061a70",
    "--color-muted": "rgba(6, 26, 112, 0.76)",
    "--color-border": "rgba(6, 26, 112, 0.18)",
    "--color-bg": "#ffffff",
    "--color-page-bg": "rgb(255, 249, 244)",
    "--color-page-bg-secondary": "#e9fbff",
    "--hero-bg": "#e9fbff",
    "--pitch-bg": "#e9fbff",
    "--color-soft": "rgba(6, 26, 112, 0.06)",
    "--color-cta": "#3b8c33",
    "--color-cta-text": "#ffffff",
    "--color-cta-icon": "#2f6f29",
    "--radius-md": "14px",
    "--radius-lg": "18px",
  },
  brand: { name: "Base Tokens Template" },
  fonts: { heading: "Merriweather", body: "Poppins", cta: "Poppins" },
  diagnostics: {
    sourceInputs: { designSystemHtmlPath: null },
    fidelity: { fontDelivery: "template_default" },
    promotionReadiness: { ready: true, missingFields: [] },
  },
};

function noopAsync<T>(value: T): Promise<T> {
  return Promise.resolve(value);
}

function buildRuntime(siteName: string): B2CRuntimeContextValue {
  return {
    isConfigured: true,
    configError: null,
    siteFamily: "medusa-b2c-starter",
    siteName,
    countryCode: "us",
    locale: "en-US",
    regions: [],
    products: [],
    collections: [],
    categories: [],
    productsLoading: false,
    productsError: null,
    productsCount: 0,
    currentProduct: null,
    currentCategory: null,
    currentCollection: null,
    cart: null,
    cartLoading: false,
    cartError: null,
    customer: null,
    customerLoading: false,
    customerError: null,
    isAuthenticated: false,
    setCountry: () => undefined,
    setLocalePreference: () => undefined,
    refreshProducts: () => noopAsync(null),
    refreshCollections: () => noopAsync(undefined),
    refreshCategories: () => noopAsync(undefined),
    loadProductByHandle: () => noopAsync(null),
    loadCollectionByHandle: () => noopAsync(null),
    loadCategoryByHandle: () => noopAsync(null),
    createCart: () => Promise.reject(new Error("Validation page does not create carts")),
    refreshCart: () => noopAsync(undefined),
    addToCart: () => noopAsync(undefined),
    updateCartItem: () => noopAsync(undefined),
    removeCartItem: () => noopAsync(undefined),
    applyPromotionCode: () => noopAsync(undefined),
    removePromotionCode: () => noopAsync(undefined),
    updateCartEmail: () => noopAsync(undefined),
    updateCartShippingAddress: () => noopAsync(undefined),
    updateCartBillingAddress: () => noopAsync(undefined),
    performCheckoutAction: () => Promise.reject(new Error("Validation page does not support checkout actions")),
    getShippingOptions: () => noopAsync([]),
    selectShippingMethod: () => noopAsync(undefined),
    getPaymentProviders: () => noopAsync([]),
    initPaymentSession: () => Promise.reject(new Error("Validation page does not support payment sessions")),
    completeCheckout: () => Promise.reject(new Error("Validation page does not complete checkout")),
    login: () => noopAsync(undefined),
    register: () => noopAsync(undefined),
    logout: () => noopAsync(undefined),
    refreshCustomer: () => noopAsync(undefined),
    updateCustomer: () => noopAsync(undefined),
    requestPasswordReset: () => noopAsync(undefined),
    addCustomerAddress: () => Promise.reject(new Error("Validation page does not create addresses")),
    updateCustomerAddress: () => Promise.reject(new Error("Validation page does not update addresses")),
    deleteCustomerAddress: () => noopAsync(undefined),
    listOrders: () => noopAsync({ orders: [], count: 0 }),
    getOrder: () => noopAsync(null),
    requestOrderTransfer: () => Promise.reject(new Error("Validation page does not request order transfers")),
    acceptOrderTransfer: () => Promise.reject(new Error("Validation page does not accept order transfers")),
    declineOrderTransfer: () => Promise.reject(new Error("Validation page does not decline order transfers")),
    navigateToHome: () => undefined,
    navigateToStore: () => undefined,
    navigateToCollection: () => undefined,
    navigateToCategory: () => undefined,
    navigateToProduct: () => undefined,
    navigateToCart: () => undefined,
    navigateToCheckout: () => undefined,
    navigateToAccount: () => undefined,
    navigateToAccountProfile: () => undefined,
    navigateToAccountAddresses: () => undefined,
    navigateToAccountOrders: () => undefined,
    navigateToOrder: () => undefined,
    navigateToOrderConfirmed: () => undefined,
    resolvePageSlug: () => null,
  } as B2CRuntimeContextValue;
}

function readPreset() {
  const params = new URLSearchParams(window.location.search);
  return params.get("preset") === "baseline" ? "baseline" : "imported";
}

function App() {
  const preset = readPreset();
  const tokens = preset === "baseline" ? baselinePreset : importedCandidate;
  const title = preset === "baseline" ? "Baseline preset" : "Imported design-system.html candidate";
  const runtime = buildRuntime(tokens.brand.name);
  const summary = {
    preset,
    designSystemHtmlPath: tokens.diagnostics.sourceInputs.designSystemHtmlPath,
    brand: tokens.brand.name,
    fontHeading: tokens.fonts.heading,
    fontBody: tokens.fonts.body,
    ctaColor: tokens.cssVars["--color-cta"],
    heroBackground: tokens.cssVars["--hero-bg"],
    pageBackground: tokens.cssVars["--color-bg"],
    radiusFull: tokens.cssVars["--radius-full"] ?? null,
    missingPromotionFields: tokens.diagnostics.promotionReadiness.missingFields,
  };

  return (
    <React.StrictMode>
      <div style={{ background: "#eef2f7", minHeight: "100vh", padding: "24px" }}>
        <div style={{ maxWidth: 1440, margin: "0 auto", display: "grid", gap: 24 }}>
          <section
            data-testid="candidate-card"
            style={{
              background: "#ffffff",
              border: "1px solid rgba(15, 23, 42, 0.12)",
              borderRadius: 16,
              padding: 20,
              boxShadow: "0 12px 30px rgba(15, 23, 42, 0.08)",
            }}
          >
            <div style={{ fontSize: 12, letterSpacing: "0.08em", textTransform: "uppercase", color: "#64748b" }}>
              Design Candidate Summary
            </div>
            <h1 style={{ margin: "8px 0 12px", fontSize: 28, lineHeight: 1.2 }}>{title}</h1>
            <pre
              style={{
                margin: 0,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                fontSize: 14,
                lineHeight: 1.5,
                color: "#0f172a",
              }}
            >
              {JSON.stringify(summary, null, 2)}
            </pre>
          </section>

          <section
            data-testid="medusa-home-preview"
            style={{
              background: "#ffffff",
              border: "1px solid rgba(15, 23, 42, 0.12)",
              borderRadius: 20,
              overflow: "hidden",
              boxShadow: "0 18px 36px rgba(15, 23, 42, 0.08)",
            }}
          >
            <DesignSystemProvider tokens={tokens}>
              <B2CRuntimeContext.Provider value={runtime}>
                <MedusaB2CHomePage />
              </B2CRuntimeContext.Provider>
            </DesignSystemProvider>
          </section>
        </div>
      </div>
    </React.StrictMode>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(<App />);
