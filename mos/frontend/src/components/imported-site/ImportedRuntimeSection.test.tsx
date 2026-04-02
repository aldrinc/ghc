import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ImportedRuntimeSection } from "./ImportedRuntimeSection";

const { runtimeMocks } = vi.hoisted(() => ({
  runtimeMocks: {
    resolveRuntimeSitePath: vi.fn((_runtime: unknown, sitePath: string) => `/preview/${sitePath}`),
  },
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
});
