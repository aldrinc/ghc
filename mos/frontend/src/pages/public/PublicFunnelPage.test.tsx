import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PublicFunnelPage } from "@/pages/public/PublicFunnelPage";
import type { PublicFunnelPage as PublicFunnelPageType } from "@/types/funnels";
import { capturePostHogEvent } from "@/lib/posthog";

const importedHtmlRendererMock = vi.fn(() => <div data-testid="standalone-imported-html-page" />);

vi.mock("@/pages/public/PublicImportedHtmlRenderer", () => ({
  default: (props: unknown) => importedHtmlRendererMock(props),
}));

vi.mock("@/pages/public/PublicFunnelPuckRenderer", () => ({
  default: ({ children }: { children?: ReactNode }) => <div data-testid="puck-renderer">{children}</div>,
}));

vi.mock("@/funnels/runtimeRouting", () => ({
  buildPublicFunnelPath: ({
    productSlug,
    funnelSlug,
    slug,
  }: {
    productSlug: string;
    funnelSlug: string;
    slug: string;
  }) => `/${productSlug}/${funnelSlug}/${slug}`,
  getStandaloneDefaultFunnelSlug: () => "example-funnel",
  getStandalonePreloadedFunnelData: () => null,
  isStandaloneBundleMode: () => true,
  normalizeRouteToken: (value: string | null | undefined) => value?.trim().toLowerCase() || "",
  resolvePublicApiBaseUrl: () => "https://api.example.test",
}));

vi.mock("@/lib/metaPixel", () => ({
  ensureMetaPixel: vi.fn(),
  trackMetaPixelEvent: vi.fn(),
}));

vi.mock("@/lib/posthog", () => ({
  capturePostHogEvent: vi.fn(),
}));

function buildImportedHtmlPage(): PublicFunnelPageType {
  return {
    productSlug: "example-product",
    funnelId: "funnel-1",
    publicationId: "publication-1",
    pageId: "page-1",
    slug: "presales",
    stage: "pre_sales",
    puckData: {
      root: { props: {} },
      content: [
        {
          type: "ImportedHtmlDocument",
          props: {
            htmlDocument: "<html><body><main>Imported content</main></body></html>",
            instrumentationManifest: {
              schemaVersion: "imported-html-instrumentation-v1",
              pageStage: "pre_sales",
              bindings: [],
            },
          },
        },
      ],
      zones: {},
    },
    pageMap: {
      "page-1": "presales",
      "page-2": "sales-page",
    },
    pageStageMap: {
      "page-1": "pre_sales",
      "page-2": "sales",
    },
    designSystemTokens: null,
    metadata: {
      title: "Imported page",
      description: "Imported page description",
      lang: "en",
      brandName: "Ember",
    },
    tracking: {
      provider: "posthog",
      mode: "public_funnel_runtime",
      posthogProjectApiKey: "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
      posthogApiHost: "https://us.i.posthog.com",
      posthogDefaults: "2026-01-30",
      posthogPersonProfiles: "identified_only",
    },
    nextPageId: "page-2",
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/example-product/example-funnel/presales"]}>
      <Routes>
        <Route path="/:productSlug/:funnelSlug/:slug" element={<PublicFunnelPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderWildcardPage() {
  return render(
    <MemoryRouter initialEntries={["/f/example-product/example-funnel/presales"]}>
      <Routes>
        <Route path="/f/:productSlug/:funnelSlug/*" element={<PublicFunnelPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("PublicFunnelPage", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    const importedHtmlPage = buildImportedHtmlPage();
    global.fetch = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/meta")) {
        return Promise.resolve(
          new Response(JSON.stringify({ entrySlug: "presales" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.endsWith("/commerce")) {
        return new Promise<Response>(() => {
          // Keep commerce pending to verify imported HTML does not wait on it.
        });
      }
      if (url.endsWith("/pages/presales")) {
        return Promise.resolve(
          new Response(JSON.stringify(importedHtmlPage), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.endsWith("/public/events")) {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      throw new Error(`Unexpected fetch request in test: ${url}`);
    }) as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.clearAllMocks();
  });

  it("renders standalone imported HTML without waiting for commerce", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("standalone-imported-html-page")).toBeInTheDocument();
    });

    expect(screen.queryByText("Imported HTML page is unavailable.")).not.toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining("/pages/presales"));
    expect(global.fetch).not.toHaveBeenCalledWith(expect.stringContaining("/commerce"));
  });

  it("builds standalone imported HTML page paths with the funnel slug", async () => {
    renderPage();

    await waitFor(() => {
      expect(importedHtmlRendererMock).toHaveBeenCalled();
    });

    const props = importedHtmlRendererMock.mock.calls[0]?.[0] as {
      pagePathById?: Record<string, string>;
    };
    expect(props.pagePathById).toEqual({
      "page-1": "/example-product/example-funnel/presales",
      "page-2": "/example-product/example-funnel/sales-page",
    });
  });

  it("captures PostHog events for public funnel page views when tracking is configured", async () => {
    renderPage();

    await waitFor(() => {
      expect(capturePostHogEvent).toHaveBeenCalledWith(
        expect.objectContaining({
          eventType: "pre_sales_page_view",
          productSlug: "example-product",
          funnelSlug: "example-funnel",
          publicationId: "publication-1",
          pageId: "page-1",
          pageSlug: "presales",
          pageStage: "pre_sales",
          tracking: expect.objectContaining({
            posthogProjectApiKey: "gPFG-Lz2YfpQgyEjLvec7KsmvBEbyiQa8HkeY8lsmVk",
          }),
        }),
      );
    });
  });

  it("loads page content when mounted under a wildcard public route", async () => {
    renderWildcardPage();

    await waitFor(() => {
      expect(screen.getByTestId("standalone-imported-html-page")).toBeInTheDocument();
    });

    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining("/pages/presales"));
  });
});
