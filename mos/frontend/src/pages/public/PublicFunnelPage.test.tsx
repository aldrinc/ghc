import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PublicFunnelPage } from "@/pages/public/PublicFunnelPage";
import type { PublicFunnelPage as PublicFunnelPageType } from "@/types/funnels";

vi.mock("@measured/puck", () => ({
  Render: () => <div data-testid="puck-renderer" />,
}));

vi.mock("@/funnels/puckConfig", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/funnels/puckConfig")>();
  return {
    ...actual,
    createFunnelPuckConfig: () => ({}),
    FunnelRuntimeProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
  };
});

vi.mock("@/components/design-system/DesignSystemProvider", () => ({
  DesignSystemProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("@/funnels/StandaloneImportedHtmlPage", () => ({
  StandaloneImportedHtmlPage: () => <div data-testid="standalone-imported-html-page" />,
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
    tracking: null,
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
  });
});
