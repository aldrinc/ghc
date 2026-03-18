import { describe, it, expect } from "vitest";
import {
  parseStringMap,
  buildImageSlotPathOrder,
  orderStringMapByPreferredPaths,
  areStringMapsEqual,
  parseSlotPathList,
  humanizeSlotToken,
  buildImageSlotReadableLabelMap,
  buildTextSlotReadableLabelMap,
} from "../shopifyTemplateUtils";

describe("parseStringMap", () => {
  it("returns empty object for empty string", () => {
    expect(parseStringMap("", "Test")).toEqual({ value: {} });
    expect(parseStringMap("   ", "Test")).toEqual({ value: {} });
  });

  it("parses valid JSON object", () => {
    const result = parseStringMap('{"a": "1", "b": "2"}', "Test");
    expect(result).toEqual({ value: { a: "1", b: "2" } });
  });

  it("trims keys and values", () => {
    const result = parseStringMap('{"  a  ": "  1  "}', "Test");
    expect(result).toEqual({ value: { a: "1" } });
  });

  it("returns error for invalid JSON", () => {
    const result = parseStringMap("{bad json}", "Image map");
    expect(result.error).toBe("Image map must be valid JSON.");
    expect(result.value).toBeUndefined();
  });

  it("returns error for array JSON", () => {
    const result = parseStringMap("[1, 2]", "Test");
    expect(result.error).toBe("Test must be a JSON object.");
  });

  it("returns error for non-string values", () => {
    const result = parseStringMap('{"a": 123}', "Test");
    expect(result.error).toBe("Test values must be non-empty strings.");
  });

  it("returns error for empty string values", () => {
    const result = parseStringMap('{"a": "  "}', "Test");
    expect(result.error).toBe("Test values must be non-empty strings.");
  });
});

describe("buildImageSlotPathOrder", () => {
  it("returns ordered unique paths", () => {
    const slots = [
      { path: "hero.img", key: "", role: "", recommendedAspect: "" },
      { path: "gallery.img", key: "", role: "", recommendedAspect: "" },
      { path: "hero.img", key: "", role: "", recommendedAspect: "" },
    ];
    expect(buildImageSlotPathOrder(slots)).toEqual(["hero.img", "gallery.img"]);
  });

  it("skips empty paths", () => {
    const slots = [
      { path: "", key: "", role: "", recommendedAspect: "" },
      { path: "valid.img", key: "", role: "", recommendedAspect: "" },
      { path: "  ", key: "", role: "", recommendedAspect: "" },
    ];
    expect(buildImageSlotPathOrder(slots)).toEqual(["valid.img"]);
  });

  it("returns empty array for empty input", () => {
    expect(buildImageSlotPathOrder([])).toEqual([]);
  });
});

describe("orderStringMapByPreferredPaths", () => {
  it("orders preferred paths first", () => {
    const source = { c: "3", a: "1", b: "2" };
    const result = orderStringMapByPreferredPaths(source, ["b", "a"]);
    expect(Object.keys(result)).toEqual(["b", "a", "c"]);
  });

  it("skips preferred paths not in source", () => {
    const source = { a: "1" };
    const result = orderStringMapByPreferredPaths(source, ["missing", "a"]);
    expect(Object.keys(result)).toEqual(["a"]);
  });

  it("handles empty inputs", () => {
    expect(orderStringMapByPreferredPaths({}, [])).toEqual({});
    expect(orderStringMapByPreferredPaths({ a: "1" }, [])).toEqual({ a: "1" });
  });
});

describe("areStringMapsEqual", () => {
  it("returns true for identical maps", () => {
    expect(areStringMapsEqual({ a: "1" }, { a: "1" })).toBe(true);
  });

  it("returns true for empty maps", () => {
    expect(areStringMapsEqual({}, {})).toBe(true);
  });

  it("returns false for different values", () => {
    expect(areStringMapsEqual({ a: "1" }, { a: "2" })).toBe(false);
  });

  it("returns false for different keys", () => {
    expect(areStringMapsEqual({ a: "1" }, { b: "1" })).toBe(false);
  });

  it("returns false for different lengths", () => {
    expect(areStringMapsEqual({ a: "1" }, { a: "1", b: "2" })).toBe(false);
  });
});

describe("parseSlotPathList", () => {
  it("returns empty array for empty input", () => {
    expect(parseSlotPathList("")).toEqual({ value: [] });
    expect(parseSlotPathList("   ")).toEqual({ value: [] });
  });

  it("splits by comma", () => {
    expect(parseSlotPathList("a, b, c")).toEqual({ value: ["a", "b", "c"] });
  });

  it("splits by newline", () => {
    expect(parseSlotPathList("a\nb\nc")).toEqual({ value: ["a", "b", "c"] });
  });

  it("returns error for duplicate paths", () => {
    const result = parseSlotPathList("a, b, a");
    expect(result.error).toContain("Duplicate slot path(s)");
    expect(result.error).toContain("a");
  });
});

describe("humanizeSlotToken", () => {
  it("splits camelCase", () => {
    expect(humanizeSlotToken("heroImage")).toBe("Hero Image");
  });

  it("splits underscores and dashes", () => {
    expect(humanizeSlotToken("hero_image")).toBe("Hero Image");
    expect(humanizeSlotToken("hero-image")).toBe("Hero Image");
  });

  it("returns fallback for empty string", () => {
    expect(humanizeSlotToken("")).toBe("Image Slot");
  });

  it("capitalizes each word", () => {
    expect(humanizeSlotToken("gallery/main_image")).toBe("Gallery Main Image");
  });
});

describe("buildImageSlotReadableLabelMap", () => {
  const makeSlot = (path: string, role = "", key = "") => ({
    path,
    role,
    key,
    recommendedAspect: "",
  });

  it("returns unique labels without numbering", () => {
    const slots = [
      makeSlot("sections.hero.image", "hero", "heroImage"),
      makeSlot("sections.gallery.image", "gallery", "galleryImage"),
    ];
    const result = buildImageSlotReadableLabelMap(slots);
    expect(result.get("sections.hero.image")).toBe("Hero Image");
    expect(result.get("sections.gallery.image")).toBe("Gallery Image");
  });

  it("numbers duplicate base labels", () => {
    const slots = [
      makeSlot("sections.hero1.image", "hero", "hero1"),
      makeSlot("sections.hero2.image", "hero", "hero2"),
    ];
    const result = buildImageSlotReadableLabelMap(slots);
    expect(result.get("sections.hero1.image")).toBe("Hero Image 1");
    expect(result.get("sections.hero2.image")).toBe("Hero Image 2");
  });
});

describe("buildTextSlotReadableLabelMap", () => {
  const makeSlot = (path: string, key = "") => ({ path, key });

  it("derives label from key containing headline", () => {
    const slots = [makeSlot("sections.hero.headline", "heroHeadline")];
    const result = buildTextSlotReadableLabelMap(slots);
    expect(result.get("sections.hero.headline")).toBe("Headline");
  });

  it("numbers duplicates", () => {
    const slots = [
      makeSlot("sections.s1.headline", "headline1"),
      makeSlot("sections.s2.headline", "headline2"),
    ];
    const result = buildTextSlotReadableLabelMap(slots);
    expect(result.get("sections.s1.headline")).toBe("Headline 1");
    expect(result.get("sections.s2.headline")).toBe("Headline 2");
  });
});
