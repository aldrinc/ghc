export type PendingMetaPurchase = {
  funnelSlug: string;
  pageId: string | null;
  variantId: string | null;
  value: number | null;
  currency: string | null;
  quantity: number;
  provider: string | null;
  createdAt: number;
};

const PENDING_META_PURCHASE_PREFIX = "mos-meta-purchase";

function cleanText(value: string | null | undefined): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed || null;
}

export function pendingMetaPurchaseStorageKey(sessionId: string | null | undefined, funnelSlug: string | null | undefined) {
  const resolvedSessionId = cleanText(sessionId);
  const resolvedFunnelSlug = cleanText(funnelSlug);
  if (!resolvedSessionId || !resolvedFunnelSlug) {
    return null;
  }
  return `${PENDING_META_PURCHASE_PREFIX}:${resolvedSessionId}:${resolvedFunnelSlug}`;
}

export function writePendingMetaPurchase(
  storage: Storage,
  key: string,
  purchase: Omit<PendingMetaPurchase, "createdAt"> & { createdAt?: number },
) {
  storage.setItem(
    key,
    JSON.stringify({
      ...purchase,
      createdAt: purchase.createdAt ?? Date.now(),
    } satisfies PendingMetaPurchase),
  );
}

export function readPendingMetaPurchase(storage: Storage, key: string): PendingMetaPurchase | null {
  const raw = storage.getItem(key);
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as Partial<PendingMetaPurchase>;
    const funnelSlug = cleanText(parsed.funnelSlug);
    if (!funnelSlug) {
      return null;
    }
    const quantity = typeof parsed.quantity === "number" && Number.isFinite(parsed.quantity) ? parsed.quantity : 1;
    const createdAt =
      typeof parsed.createdAt === "number" && Number.isFinite(parsed.createdAt) ? parsed.createdAt : Date.now();

    return {
      funnelSlug,
      pageId: cleanText(parsed.pageId),
      variantId: cleanText(parsed.variantId),
      value: typeof parsed.value === "number" && Number.isFinite(parsed.value) ? parsed.value : null,
      currency: cleanText(parsed.currency),
      quantity,
      provider: cleanText(parsed.provider),
      createdAt,
    };
  } catch {
    return null;
  }
}

export function clearPendingMetaPurchase(storage: Storage, key: string) {
  storage.removeItem(key);
}

export function buildPurchaseEventParams(purchase: PendingMetaPurchase): Record<string, unknown> {
  const params: Record<string, unknown> = {
    content_type: "product",
    num_items: purchase.quantity > 0 ? purchase.quantity : 1,
  };

  if (purchase.variantId) {
    params.content_ids = [purchase.variantId];
  }
  if (typeof purchase.value === "number" && Number.isFinite(purchase.value)) {
    params.value = purchase.value;
  }
  if (purchase.currency) {
    params.currency = purchase.currency.toUpperCase();
  }

  return params;
}

export function clearCheckoutQueryParam(href: string): string {
  const url = new URL(href);
  url.searchParams.delete("checkout");
  return `${url.pathname}${url.search}${url.hash}`;
}
