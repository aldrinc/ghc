import { describe, expect, it } from "vitest";

import {
  buildPurchaseEventParams,
  clearCheckoutQueryParam,
  clearPendingMetaPurchase,
  pendingMetaPurchaseStorageKey,
  readPendingMetaPurchase,
  writePendingMetaPurchase,
} from "@/lib/metaCheckout";

class MemoryStorage implements Storage {
  private data = new Map<string, string>();

  get length() {
    return this.data.size;
  }

  clear() {
    this.data.clear();
  }

  getItem(key: string) {
    return this.data.get(key) ?? null;
  }

  key(index: number) {
    return Array.from(this.data.keys())[index] ?? null;
  }

  removeItem(key: string) {
    this.data.delete(key);
  }

  setItem(key: string, value: string) {
    this.data.set(key, value);
  }
}

describe("pendingMetaPurchaseStorageKey", () => {
  it("builds a stable session and funnel scoped key", () => {
    expect(pendingMetaPurchaseStorageKey("session-1", "summer-funnel")).toBe(
      "mos-meta-purchase:session-1:summer-funnel",
    );
  });

  it("returns null when required values are missing", () => {
    expect(pendingMetaPurchaseStorageKey("", "summer-funnel")).toBeNull();
    expect(pendingMetaPurchaseStorageKey("session-1", "")).toBeNull();
  });
});

describe("pending Meta purchase storage", () => {
  it("round-trips purchase metadata for the return page", () => {
    const storage = new MemoryStorage();
    const key = "mos-meta-purchase:session-1:summer-funnel";

    writePendingMetaPurchase(storage, key, {
      funnelSlug: "summer-funnel",
      pageId: "page-1",
      variantId: "variant-1",
      value: 49,
      currency: "usd",
      quantity: 2,
      provider: "stripe",
      createdAt: 1234,
    });

    expect(readPendingMetaPurchase(storage, key)).toEqual({
      funnelSlug: "summer-funnel",
      pageId: "page-1",
      variantId: "variant-1",
      value: 49,
      currency: "usd",
      quantity: 2,
      provider: "stripe",
      createdAt: 1234,
    });

    clearPendingMetaPurchase(storage, key);
    expect(readPendingMetaPurchase(storage, key)).toBeNull();
  });
});

describe("buildPurchaseEventParams", () => {
  it("maps pending checkout data to a Meta Purchase payload", () => {
    expect(
      buildPurchaseEventParams({
        funnelSlug: "summer-funnel",
        pageId: "page-1",
        variantId: "variant-1",
        value: 49,
        currency: "usd",
        quantity: 2,
        provider: "stripe",
        createdAt: 1234,
      }),
    ).toEqual({
      content_type: "product",
      content_ids: ["variant-1"],
      value: 49,
      currency: "USD",
      num_items: 2,
    });
  });
});

describe("clearCheckoutQueryParam", () => {
  it("removes only the checkout status flag from the URL", () => {
    expect(clearCheckoutQueryParam("https://example.com/f/product/funnel?page=1&checkout=success&utm_source=meta#top"))
      .toBe("/f/product/funnel?page=1&utm_source=meta#top");
  });
});
