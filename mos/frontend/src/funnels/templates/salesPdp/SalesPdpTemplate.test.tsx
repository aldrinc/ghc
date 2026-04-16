import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

import { SalesPdpFooter, salesPdpDefaults } from "@/funnels/templates/salesPdp/SalesPdpTemplate";

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
