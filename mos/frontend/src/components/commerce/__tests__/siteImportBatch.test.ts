import { describe, expect, it } from "vitest";

import {
  buildSiteImportBatchItem,
  defaultPairedSalesPageName,
  defaultPairedSalesPageSlug,
  makeUniqueSiteImportSlug,
} from "../siteImportBatch";

describe("siteImportBatch helpers", () => {
  it("derives readable page names and unique slugs from uploaded filenames", () => {
    const usedSlugs = new Set<string>();
    const first = buildSiteImportBatchItem({
      id: "import-1",
      referenceHtml: "<html></html>",
      referenceLabel: "brain_fog-story-a.html",
      usedSlugs,
    });
    usedSlugs.add(first.slug);

    const second = buildSiteImportBatchItem({
      id: "import-2",
      referenceHtml: "<html></html>",
      referenceLabel: "brain fog story a.htm",
      usedSlugs,
    });

    expect(first.pageName).toBe("Brain Fog Story A");
    expect(first.slug).toBe("brain-fog-story-a");
    expect(second.pageName).toBe("Brain Fog Story A");
    expect(second.slug).toBe("brain-fog-story-a-2");
  });

  it("maps pasted html to a neutral imported page name", () => {
    const item = buildSiteImportBatchItem({
      id: "import-1",
      referenceHtml: "<html></html>",
      referenceLabel: "pasted-html",
    });

    expect(item.pageName).toBe("Imported Page");
    expect(item.slug).toBe("pasted-html");
  });

  it("builds paired sales-page defaults from the pre-sales draft", () => {
    expect(defaultPairedSalesPageName("Mid Sentence Freeze")).toBe("Mid Sentence Freeze Sales Page");
    expect(defaultPairedSalesPageSlug("mid-sentence-freeze")).toBe("mid-sentence-freeze-sales");
  });

  it("matches backend-style collision suffixes", () => {
    expect(makeUniqueSiteImportSlug("sales", ["sales", "sales-2"])).toBe("sales-3");
  });
});
