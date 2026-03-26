import { describe, expect, it } from "vitest";
import {
  buildImportedRuntimeSrcDoc,
  normalizeImportedHeadAssets,
  normalizeImportedRuntimeSectionTypes,
} from "./importedRuntime";

describe("normalizeImportedHeadAssets", () => {
  it("coerces missing values into a stable head asset shape", () => {
    expect(normalizeImportedHeadAssets(null)).toEqual({
      scriptSrcs: [],
      stylesheetHrefs: [],
      inlineStyles: [],
      inlineScripts: [],
      bodyClassName: "",
    });
  });
});

describe("normalizeImportedRuntimeSectionTypes", () => {
  it("maps imported runtime blocks to the generic frontend renderer", () => {
    const data = {
      content: [
        {
          type: "ImportedHeroSection",
          props: {
            id: "section-1",
            runtimeSource: "const ImportedSection = () => <div />;",
          },
        },
      ],
    };

    expect(normalizeImportedRuntimeSectionTypes(data)).toBe(true);
    expect(data).toEqual({
      content: [
        {
          type: "ImportedRuntimeSection",
          props: {
            id: "section-1",
            runtimeSource: "const ImportedSection = () => <div />;",
            originalType: "ImportedHeroSection",
          },
        },
      ],
    });
  });

  it("leaves non-imported blocks unchanged", () => {
    const data = {
      content: [
        {
          type: "Section",
          props: {
            id: "section-1",
          },
        },
      ],
    };

    expect(normalizeImportedRuntimeSectionTypes(data)).toBe(false);
    expect(data.content[0].type).toBe("Section");
  });
});

describe("buildImportedRuntimeSrcDoc", () => {
  it("embeds the runtime bridge, frame assets, and compiled source", () => {
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-123",
      sectionLabel: "Hero",
      compiledSource: "const ImportedSection = () => React.createElement('div', null, 'Hero');",
      reactUmdSource: "window.React = { createElement: () => null, Fragment: 'fragment' };",
      reactDomUmdSource: "window.ReactDOM = { createRoot: () => ({ render: () => null }) };",
      headAssets: {
        stylesheetHrefs: ["https://example.com/styles.css"],
        inlineStyles: ["body { color: red; }"],
      },
    });

    expect(srcDoc).toContain('source: "mos-imported-runtime"');
    expect(srcDoc).toContain("frame-123");
    expect(srcDoc).toContain("https://example.com/styles.css");
    expect(srcDoc).toContain("const ImportedSection = () => React.createElement('div', null, 'Hero');");
    expect(srcDoc).toContain("<title>Hero</title>");
  });
});
