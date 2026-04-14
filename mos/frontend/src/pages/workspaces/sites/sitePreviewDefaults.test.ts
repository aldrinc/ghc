import { describe, expect, it } from "vitest";
import { resolveSitePreviewDefaults } from "./sitePreviewDefaults";

describe("sitePreviewDefaults", () => {
  it("picks the first available collection handle", () => {
    expect(
      resolveSitePreviewDefaults(
        [{ handle: "" }, { handle: "featured" }, { handle: "summer" }],
        [],
      ).collectionHandle,
    ).toBe("featured");
  });

  it("prefers a root category handle when available", () => {
    expect(
      resolveSitePreviewDefaults(
        [],
        [
          { handle: "supplements/daily", parent_category_id: "pcat-parent" },
          { handle: "supplements", parent_category_id: null },
          { handle: "books", parent_category_id: null },
        ],
      ).categoryHandle,
    ).toBe("supplements");
  });

  it("falls back to the first category handle when no root category exists", () => {
    expect(
      resolveSitePreviewDefaults(
        [],
        [{ handle: "supplements/daily", parent_category_id: "pcat-parent" }],
      ).categoryHandle,
    ).toBe("supplements/daily");
  });
});
