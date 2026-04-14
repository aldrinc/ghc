import { describe, expect, it } from "vitest";

import { SITE_PAGE_EDITOR_THEME_INHERITANCE_COPY } from "./sitePageEditorCopy";

describe("SitePageEditorPage copy", () => {
  it("describes page overrides in terms of site theme inheritance", () => {
    expect(SITE_PAGE_EDITOR_THEME_INHERITANCE_COPY).toContain("Inherit from site theme");
    expect(SITE_PAGE_EDITOR_THEME_INHERITANCE_COPY).toContain("site's theme settings");
    expect(SITE_PAGE_EDITOR_THEME_INHERITANCE_COPY).not.toContain("workspace");
  });
});
