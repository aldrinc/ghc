const CLICK_ID_KEYS = ["fbclid", "gclid", "ttclid", "msclkid", "twclid", "li_fat_id"];
const CHECKOUT_TRACKING_PARAM_KEYS = new Set([
  ...CLICK_ID_KEYS,
  "experiment_id",
  "experiment",
  "exp",
  "src",
]);

function cleanText(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed || null;
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${name}=`;
  const match = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  return match ? cleanText(match.slice(prefix.length)) : null;
}

function randomIdSegment(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function currentUrl(): URL | null {
  if (typeof window === "undefined") return null;
  return new URL(window.location.href);
}

function isCheckoutTrackingParam(key: string): boolean {
  const normalized = key.trim();
  return normalized.startsWith("utm_") || CHECKOUT_TRACKING_PARAM_KEYS.has(normalized);
}

function resolveClickAttribution(url: URL | null): { clickId?: string; clickIdType?: string } {
  if (!url) return {};
  for (const key of CLICK_ID_KEYS) {
    const value = cleanText(url.searchParams.get(key));
    if (value) {
      return { clickId: value, clickIdType: key };
    }
  }
  return {};
}

function resolveExperimentId(url: URL | null): string | null {
  if (!url) return null;
  return (
    cleanText(url.searchParams.get("experiment_id")) ||
    cleanText(url.searchParams.get("experiment")) ||
    cleanText(url.searchParams.get("exp"))
  );
}

export function buildCheckoutTransitionId(): string {
  return `mos:checkout_transition:${randomIdSegment()}`;
}

export function buildCheckoutAttributionProps({
  pageVariant,
  ctaId,
  transitionId,
}: {
  pageVariant?: string | null;
  ctaId?: string | null;
  transitionId?: string | null;
}): Record<string, string> {
  const url = currentUrl();
  const click = resolveClickAttribution(url);
  const experimentId = resolveExperimentId(url);
  const props: Record<string, string> = {};

  if (click.clickId) {
    props.clickId = click.clickId;
  }
  if (click.clickIdType) {
    props.clickIdType = click.clickIdType;
  }
  const fbp = readCookie("_fbp");
  if (fbp) {
    props.fbp = fbp;
  }
  const fbc = readCookie("_fbc");
  if (fbc) {
    props.fbc = fbc;
  }
  if (url) {
    props.eventSourceUrl = url.href;
  }
  const cleanedPageVariant = cleanText(pageVariant);
  if (cleanedPageVariant) {
    props.pageVariant = cleanedPageVariant;
  }
  if (experimentId) {
    props.experimentId = experimentId;
  }
  const cleanedCtaId = cleanText(ctaId);
  if (cleanedCtaId) {
    props.ctaId = cleanedCtaId;
  }
  const cleanedTransitionId = cleanText(transitionId);
  if (cleanedTransitionId) {
    props.transitionId = cleanedTransitionId;
  }
  return props;
}

function serializeAttributeValue(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value === "string") return cleanText(value);
  return JSON.stringify(value);
}

export function appendCheckoutAttributesToCartUrl(
  checkoutUrl: string,
  attributes: Record<string, unknown>,
): string {
  const href = cleanText(checkoutUrl);
  if (!href) return checkoutUrl;
  if (typeof window === "undefined") return href;
  const url = new URL(href, window.location.href);
  if (!url.pathname.startsWith("/cart/")) return href;
  Object.entries(attributes).forEach(([key, value]) => {
    const serialized = serializeAttributeValue(value);
    if (serialized) {
      url.searchParams.set(`attributes[${key}]`, serialized);
    }
  });
  return url.toString();
}

export function appendCheckoutTrackingUrlParams(targetUrl: string): string {
  const href = cleanText(targetUrl);
  if (!href) return targetUrl;
  if (typeof window === "undefined") return href;
  const url = new URL(href, window.location.href);
  const params = currentUrl()?.searchParams;
  if (!params) return url.toString();
  for (const [key, value] of params.entries()) {
    if (isCheckoutTrackingParam(key)) {
      url.searchParams.set(key, value);
    }
  }
  return url.toString();
}

function resolveDeviceType(): "mobile" | "tablet" | "desktop" {
  if (typeof window === "undefined") return "desktop";
  const width = window.innerWidth || document.documentElement?.clientWidth || 0;
  if (width > 0 && width < 768) return "mobile";
  if (width >= 768 && width < 1024) return "tablet";
  return "desktop";
}

export function buildCheckoutTimingProps({
  transitionId,
  ctaId,
  checkoutUrl,
  selectedOffer,
  variantIds,
  sellingPlanId,
}: {
  transitionId?: string | null;
  ctaId?: string | null;
  checkoutUrl?: string | null;
  selectedOffer?: string | null;
  variantIds?: string[] | null;
  sellingPlanId?: string | null;
}): Record<string, unknown> {
  const props: Record<string, unknown> = {
    performance_now_ms:
      typeof performance !== "undefined" && typeof performance.now === "function"
        ? Math.round(performance.now())
        : null,
    client_timestamp_ms: Date.now(),
  };
  const cleanedTransitionId = cleanText(transitionId);
  if (cleanedTransitionId) props.transitionId = cleanedTransitionId;
  const cleanedCtaId = cleanText(ctaId);
  if (cleanedCtaId) props.ctaId = cleanedCtaId;
  const cleanedSelectedOffer = cleanText(selectedOffer);
  if (cleanedSelectedOffer) props.selected_offer = cleanedSelectedOffer;
  const cleanedSellingPlanId = cleanText(sellingPlanId);
  if (cleanedSellingPlanId) props.selling_plan_id = cleanedSellingPlanId;
  if (variantIds?.length) {
    props.variant_ids = variantIds.filter((item) => cleanText(item));
  }
  if (checkoutUrl && typeof window !== "undefined") {
    try {
      props.checkout_url_host = new URL(checkoutUrl, window.location.href).host;
    } catch {
      // Ignore malformed checkout URLs here; the navigation path still validates separately.
    }
  }
  if (typeof navigator !== "undefined") {
    props.user_agent = navigator.userAgent;
    props.device_type = resolveDeviceType();
    const connection = (navigator as Navigator & {
      connection?: {
        effectiveType?: string;
        rtt?: number;
        downlink?: number;
      };
      deviceMemory?: number;
    }).connection;
    if (connection?.effectiveType) props.connection_effective_type = connection.effectiveType;
    if (typeof connection?.rtt === "number") props.connection_rtt = connection.rtt;
    if (typeof connection?.downlink === "number") props.connection_downlink = connection.downlink;
    const deviceMemory = (navigator as Navigator & { deviceMemory?: number }).deviceMemory;
    if (typeof deviceMemory === "number") props.device_memory = deviceMemory;
  }
  return Object.fromEntries(Object.entries(props).filter(([, value]) => value !== null));
}
