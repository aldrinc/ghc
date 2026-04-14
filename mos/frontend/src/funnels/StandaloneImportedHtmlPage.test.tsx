import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StandaloneImportedHtmlPage } from "@/funnels/StandaloneImportedHtmlPage";
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

describe("StandaloneImportedHtmlPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    delete window.__mosImportedHtmlStandalonePageId;
  });

  it("injects a lazy commerce loader into the standalone runtime script", async () => {
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
        htmlDocument="<html><body><button>Buy now</button></body></html>"
        instrumentationManifest={{
          schemaVersion: "imported-html-instrumentation-v1",
          pageStage: "sales",
          bindings: [],
        }}
        variants={[]}
        pagePathById={{ "page-1": "/example-product/example-funnel/sales-page" }}
        pageStageById={{ "page-1": "sales" }}
      />,
    );

    await waitFor(() => {
      expect(documentOpenSpy).toHaveBeenCalled();
      expect(documentWriteSpy).toHaveBeenCalled();
      expect(documentCloseSpy).toHaveBeenCalled();
    });

    const injectedDocument = documentWriteSpy.mock.calls[0]?.[0] || "";
    expect(injectedDocument).toContain("loadCommerceVariants");
    expect(injectedDocument).toContain("/public/funnels/");
    expect(injectedDocument).toContain("/commerce");
  });
});
