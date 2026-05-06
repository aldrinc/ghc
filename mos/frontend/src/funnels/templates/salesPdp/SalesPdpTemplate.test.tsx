import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { resolveRuntimePagePathMock, useFunnelRuntimeMock } = vi.hoisted(() => ({
  useFunnelRuntimeMock: vi.fn(),
  resolveRuntimePagePathMock: vi.fn(
    (runtime: { productSlug: string; funnelSlug: string }, slug: string) =>
      `/f/${runtime.productSlug}/${runtime.funnelSlug}/${slug}`,
  ),
}));

vi.mock("@/components/design-system/DesignSystemProvider", () => ({
  useDesignSystemTokens: () => null,
}));

vi.mock("@/funnels/puckConfig", () => ({
  useFunnelRuntime: () => useFunnelRuntimeMock(),
  resolveRuntimePagePath: resolveRuntimePagePathMock,
}));

vi.mock("@/funnels/runtimeRouting", () => ({
  resolvePublicApiBaseUrl: () => "https://api.example.test",
}));

import { SalesPdpFooter, SalesPdpHero, salesPdpDefaults } from "@/funnels/templates/salesPdp/SalesPdpTemplate";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SalesPdpFooter", () => {
  it("renders default funnel compliance links when no footer links are configured", () => {
    useFunnelRuntimeMock.mockReturnValue({
      productSlug: "example-product",
      funnelSlug: "example-funnel",
      pageMap: {
        "page-terms": "terms-of-service",
        "page-privacy": "privacy-policy",
        "page-refunds": "refund-policy",
      },
      pageTypeMap: {
        "page-terms": "terms_of_service",
        "page-privacy": "privacy_policy",
        "page-refunds": "returns_refunds_policy",
      },
    });

    render(<SalesPdpFooter config={{ ...salesPdpDefaults.config.footer, links: [] }} />);

    expect(screen.getByRole("link", { name: "Terms" })).toHaveAttribute(
      "href",
      "/f/example-product/example-funnel/terms-of-service",
    );
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute(
      "href",
      "/f/example-product/example-funnel/privacy-policy",
    );
    expect(screen.getByRole("link", { name: "Refunds" })).toHaveAttribute(
      "href",
      "/f/example-product/example-funnel/refund-policy",
    );
    expect(screen.getByRole("link", { name: "Terms" })).not.toHaveAttribute("target");
  });

  it("preserves configured external footer links", () => {
    useFunnelRuntimeMock.mockReturnValue({
      productSlug: "example-product",
      funnelSlug: "example-funnel",
      pageMap: {},
      pageTypeMap: {},
    });

    render(
      <SalesPdpFooter
        config={{
          ...salesPdpDefaults.config.footer,
          links: [{ label: "Support", href: "https://example.test/support" }],
        }}
      />,
    );

    expect(screen.getByRole("link", { name: "Support" })).toHaveAttribute("href", "https://example.test/support");
    expect(screen.getByRole("link", { name: "Support" })).toHaveAttribute("target", "_blank");
    expect(screen.queryByRole("link", { name: "Terms" })).not.toBeInTheDocument();
  });
});

describe("SalesPdpHero", () => {
  it("keeps the checkout button in loading state after click", async () => {
    const trackEvent = vi.fn();
    useFunnelRuntimeMock.mockReturnValue({
      productSlug: "example-product",
      funnelSlug: "example-funnel",
      pageMap: { "page-1": "sales-page" },
      pageStageMap: { "page-1": "sales" },
      pageStage: "sales",
      pageId: "page-1",
      visitorId: "visitor-1",
      sessionId: "session-1",
      trackEvent,
      commerce: {
        product: {
          variants: [
            {
              id: "variant-1",
              provider: "shopify",
              price: 5000,
              currency: "USD",
              option_values: { sizeId: "small", colorId: "gray", offerId: "1" },
            },
          ],
        },
      },
      commerceError: null,
    });
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));

    render(<SalesPdpHero config={salesPdpDefaults.config.hero} />);
    fireEvent.click(screen.getByRole("button", { name: /Add to Cart/i }));

    await waitFor(() => {
      const button = screen.getByRole("button", { name: /Opening secure checkout/i });
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute("aria-busy", "true");
    });
  });
});
