import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ImportedRuntimeSection } from "./ImportedRuntimeSection";

vi.mock("./importedRuntimeFrameAssets", () => ({
  importedRuntimeFrameAssets: {
    reactUmdSource: "window.React = { createElement: () => null, Fragment: 'fragment' };",
    reactDomUmdSource: "window.ReactDOM = { createRoot: () => ({ render: () => null }) };",
  },
}));

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
});
