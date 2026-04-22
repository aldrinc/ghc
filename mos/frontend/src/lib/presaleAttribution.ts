import type { PublicFunnelStage } from "@/types/funnels";

export const PRESALE_SOURCE_PARAM = "src";
export const PRESALE_SOURCE_VALUE = "presale";

function clean(value: string | null | undefined): string {
  return typeof value === "string" ? value.trim() : "";
}

export function isPresaleToSalesNavigation(
  fromStage: PublicFunnelStage | null | undefined,
  toStage: PublicFunnelStage | null | undefined,
): boolean {
  return fromStage === "pre_sales" && toStage === "sales";
}

export function presaleAttributionStorageKey(
  productSlug: string | null | undefined,
  funnelSlug: string | null | undefined,
): string | null {
  const cleanedProductSlug = clean(productSlug);
  const cleanedFunnelSlug = clean(funnelSlug);
  if (!cleanedProductSlug || !cleanedFunnelSlug) {
    return null;
  }
  return `from_presale:${cleanedProductSlug}:${cleanedFunnelSlug}`;
}

export function markPresaleAttribution(
  storage: Storage | null | undefined,
  {
    productSlug,
    funnelSlug,
  }: {
    productSlug: string | null | undefined;
    funnelSlug: string | null | undefined;
  },
): void {
  if (!storage) return;
  const key = presaleAttributionStorageKey(productSlug, funnelSlug);
  if (!key) return;
  try {
    storage.setItem(key, "1");
  } catch {
    // ignore storage write failures
  }
}

export function hasStoredPresaleAttribution(
  storage: Storage | null | undefined,
  {
    productSlug,
    funnelSlug,
  }: {
    productSlug: string | null | undefined;
    funnelSlug: string | null | undefined;
  },
): boolean {
  if (!storage) return false;
  const key = presaleAttributionStorageKey(productSlug, funnelSlug);
  if (!key) return false;
  try {
    return storage.getItem(key) === "1";
  } catch {
    return false;
  }
}

export function hasPresaleSourceParam(search: string | null | undefined): boolean {
  const params = new URLSearchParams(clean(search));
  return params.get(PRESALE_SOURCE_PARAM) === PRESALE_SOURCE_VALUE;
}

export function buildPresaleAttributedInternalPath(
  targetPath: string,
  currentSearch: string,
): string {
  const normalizedTargetPath = clean(targetPath);
  if (!normalizedTargetPath) {
    return "#";
  }
  const baseOrigin =
    typeof window !== "undefined" && window.location.origin
      ? window.location.origin
      : "https://example.test";
  const nextUrl = new URL(normalizedTargetPath, baseOrigin);
  const params = new URLSearchParams(clean(currentSearch));
  params.delete("checkout");
  params.set(PRESALE_SOURCE_PARAM, PRESALE_SOURCE_VALUE);
  const search = params.toString();
  return `${nextUrl.pathname}${search ? `?${search}` : ""}${nextUrl.hash}`;
}

export function hasPresaleReferrerAttribution(
  referrer: string | null | undefined,
  preSalesPaths: string[],
  origin: string,
): boolean {
  const cleanedReferrer = clean(referrer);
  if (!cleanedReferrer || !origin || !preSalesPaths.length) {
    return false;
  }
  try {
    const referrerUrl = new URL(cleanedReferrer, origin);
    if (referrerUrl.origin !== origin) {
      return false;
    }
    return preSalesPaths.some((path) => {
      const cleanedPath = clean(path);
      if (!cleanedPath) return false;
      return new URL(cleanedPath, origin).pathname === referrerUrl.pathname;
    });
  } catch {
    return false;
  }
}

export function resolvePresaleAttributionSource({
  search,
  storage,
  productSlug,
  funnelSlug,
  referrer,
  preSalesPaths,
  origin,
}: {
  search: string | null | undefined;
  storage: Storage | null | undefined;
  productSlug: string | null | undefined;
  funnelSlug: string | null | undefined;
  referrer?: string | null | undefined;
  preSalesPaths?: string[] | null | undefined;
  origin?: string | null | undefined;
}): "url" | "session" | "referrer" | null {
  if (hasPresaleSourceParam(search)) {
    return "url";
  }
  if (hasStoredPresaleAttribution(storage, { productSlug, funnelSlug })) {
    return "session";
  }
  if (hasPresaleReferrerAttribution(referrer, preSalesPaths ?? [], clean(origin))) {
    return "referrer";
  }
  return null;
}
