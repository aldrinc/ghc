import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ImportedHtmlDocument } from "@/funnels/ImportedHtmlDocument";

const HEIGHT_MESSAGE_TYPE = "mos:imported-html-document:height";
const ACTION_MESSAGE_TYPE = "mos:imported-html-document:action";

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

describe("ImportedHtmlDocument", () => {
  it("shrinks to the reported iframe height instead of keeping the loading floor", () => {
    render(
      <MemoryRouter initialEntries={["/070d6cf7/e2bec743/presales"]}>
        <Routes>
          <Route
            path="*"
            element={<ImportedHtmlDocument title="Imported Ember Page" htmlDocument="<html><body><main>hello</main></body></html>" />}
          />
        </Routes>
      </MemoryRouter>,
    );

    const iframe = screen.getByTitle("Imported Ember Page");
    expect(iframe).toHaveStyle({ height: "900px" });

    act(() => {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: {
            type: HEIGHT_MESSAGE_TYPE,
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
      <MemoryRouter initialEntries={["/070d6cf7/e2bec743/presales"]}>
        <Routes>
          <Route
            path="*"
            element={<ImportedHtmlDocument title="Imported Ember Page" htmlDocument="<html><body><main>first</main></body></html>" />}
          />
        </Routes>
      </MemoryRouter>,
    );

    const iframe = screen.getByTitle("Imported Ember Page");

    act(() => {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: {
            type: HEIGHT_MESSAGE_TYPE,
            frameId: "imported-html-document",
            height: 640,
          },
        }),
      );
    });

    expect(iframe).toHaveStyle({ height: "640px" });

    rerender(
      <MemoryRouter initialEntries={["/070d6cf7/e2bec743/presales"]}>
        <Routes>
          <Route
            path="*"
            element={<ImportedHtmlDocument title="Imported Ember Page" htmlDocument="<html><body><main>second</main></body></html>" />}
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(iframe).toHaveStyle({ height: "900px" });
  });

  it("navigates imported HTML CTA clicks to the configured funnel page", async () => {
    render(
      <MemoryRouter initialEntries={["/070d6cf7/e2bec743/presales"]}>
        <Routes>
          <Route
            path="*"
            element={
              <>
                <ImportedHtmlDocument
                  title="Imported Ember Page"
                  htmlDocument="<html><body><a class='btn-primary' href='#'>See Why</a></body></html>"
                  runtime={{
                    productSlug: "070d6cf7",
                    funnelSlug: "e2bec743",
                    bundleMode: true,
                    pageMap: {
                      "page-presales": "presales",
                      "page-sales": "sales-page",
                    },
                    pageStageMap: {
                      "page-presales": "pre_sales",
                      "page-sales": "sales",
                    },
                    pageStage: "pre_sales",
                  }}
                />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    act(() => {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: {
            type: ACTION_MESSAGE_TYPE,
            frameId: "imported-html-document",
            action: {
              type: "internal_navigation",
              bindingId: "cta-1",
              targetPageId: "page-sales",
            },
          },
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent("/070d6cf7/e2bec743/sales-page");
    });
  });

  it("shows a clean error when an imported HTML CTA points to a missing funnel page", async () => {
    render(
      <MemoryRouter initialEntries={["/070d6cf7/e2bec743/presales"]}>
        <Routes>
          <Route
            path="*"
            element={
              <ImportedHtmlDocument
                title="Imported Ember Page"
                htmlDocument="<html><body><a class='btn-primary' href='#'>See Why</a></body></html>"
                runtime={{
                  productSlug: "070d6cf7",
                  funnelSlug: "e2bec743",
                  bundleMode: true,
                  pageMap: {},
                  pageStageMap: {},
                  pageStage: "pre_sales",
                }}
              />
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    act(() => {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: {
            type: ACTION_MESSAGE_TYPE,
            frameId: "imported-html-document",
            action: {
              type: "internal_navigation",
              bindingId: "cta-1",
              targetPageId: "missing-page",
            },
          },
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByText("Imported HTML navigation target is not available in this funnel.")).toBeInTheDocument();
    });
  });
});
