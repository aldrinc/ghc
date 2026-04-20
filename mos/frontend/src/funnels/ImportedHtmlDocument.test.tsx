import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ImportedHtmlDocument } from "@/funnels/ImportedHtmlDocument";
import {
  IMPORTED_HTML_HEIGHT_MESSAGE,
  IMPORTED_HTML_RUNTIME_MESSAGE_SOURCE,
} from "@/funnels/importedHtmlRuntime";

describe("ImportedHtmlDocument", () => {
  it("shrinks to the reported iframe height instead of keeping the loading floor", () => {
    render(
      <ImportedHtmlDocument
        title="Imported Ember Page"
        htmlDocument="<html><body><main>hello</main></body></html>"
      />,
    );

    const iframe = screen.getByTitle("Imported Ember Page");
    expect(iframe).toHaveStyle({ height: "900px" });

    act(() => {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: {
            source: IMPORTED_HTML_RUNTIME_MESSAGE_SOURCE,
            type: IMPORTED_HTML_HEIGHT_MESSAGE,
            frameId: "imported-html-document",
            height: 612.2,
          },
        }),
      );
    });

    expect(iframe).toHaveStyle({ height: "613px" });
  });

  it("resets to the loading height when a different imported document is rendered", () => {
    const { rerender } = render(
      <ImportedHtmlDocument
        title="Imported Ember Page"
        htmlDocument="<html><body><main>first</main></body></html>"
      />,
    );

    const iframe = screen.getByTitle("Imported Ember Page");

    act(() => {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: {
            source: IMPORTED_HTML_RUNTIME_MESSAGE_SOURCE,
            type: IMPORTED_HTML_HEIGHT_MESSAGE,
            frameId: "imported-html-document",
            height: 640,
          },
        }),
      );
    });

    expect(iframe).toHaveStyle({ height: "640px" });

    rerender(
      <ImportedHtmlDocument
        title="Imported Ember Page"
        htmlDocument="<html><body><main>second</main></body></html>"
      />,
    );

    expect(iframe).toHaveStyle({ height: "900px" });
  });

  it("injects the mobile trailing-space compaction runtime", () => {
    render(
      <ImportedHtmlDocument
        title="Imported Ember Page"
        htmlDocument="<html><body><main>hello</main></body></html>"
      />,
    );

    const iframe = screen.getByTitle("Imported Ember Page");
    const srcDoc = iframe.getAttribute("srcdoc") || "";

    expect(srcDoc).toContain("compactMobileTrailingSpacing");
    expect(srcDoc).toContain("restoreCompactedSpacing");
    expect(srcDoc).toContain("window.innerWidth > MOBILE_MAX_WIDTH");
  });

  it("optimizes imported HTML image loading inside the iframe document", () => {
    render(
      <ImportedHtmlDocument
        title="Imported Ember Page"
        htmlDocument={`
          <html>
            <body>
              <img src="/hero.jpg" alt="Hero" />
              <img src="/gallery.jpg" alt="Gallery" />
            </body>
          </html>
        `}
      />,
    );

    const iframe = screen.getByTitle("Imported Ember Page");
    const srcDoc = iframe.getAttribute("srcdoc") || "";

    expect(srcDoc).toContain('src="/hero.jpg" alt="Hero" loading="eager" decoding="async" fetchpriority="high"');
    expect(srcDoc).toContain('src="/gallery.jpg" alt="Gallery" loading="lazy" decoding="async" fetchpriority="low"');
  });
});
