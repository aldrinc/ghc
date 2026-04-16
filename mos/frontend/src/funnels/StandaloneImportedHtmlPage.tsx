import { useEffect } from "react";
import { resolvePublicApiBaseUrl } from "@/funnels/runtimeRouting";
import type { PublicCommerceVariant } from "@/types/commerce";
import type {
  ImportedHtmlInstrumentationManifest,
  ImportedHtmlTrackEventType,
  PublicFunnelPage,
  PublicFunnelStage,
} from "@/types/funnels";

const apiBaseUrl = resolvePublicApiBaseUrl();

declare global {
  interface Window {
    __mosImportedHtmlStandalonePageId?: string;
  }
}

type StandaloneImportedHtmlPageProps = {
  page: PublicFunnelPage;
  productSlug: string;
  funnelSlug: string;
  visitorId: string;
  sessionId: string;
  htmlDocument: string;
  instrumentationManifest: ImportedHtmlInstrumentationManifest;
  variants: PublicCommerceVariant[];
  pagePathById: Record<string, string>;
  pageStageById: Record<string, PublicFunnelStage>;
};

type SerializedVariant = {
  id: string;
  provider: string | null;
  price: number | null;
  currency: string | null;
  optionValues: Record<string, string> | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeVariantOptionValues(
  optionValues: Record<string, unknown> | null | undefined,
): Record<string, string> | null {
  if (!isRecord(optionValues)) return null;
  const normalizedEntries = Object.entries(optionValues)
    .map(([key, value]) => {
      if (typeof key !== "string") return null;
      const normalizedKey = key.trim();
      if (!normalizedKey || typeof value !== "string") return null;
      const normalizedValue = value.trim();
      if (!normalizedValue) return null;
      return [normalizedKey, normalizedValue] as const;
    })
    .filter((entry): entry is readonly [string, string] => Boolean(entry));
  if (!normalizedEntries.length) return null;
  return Object.fromEntries(normalizedEntries);
}

function serializeVariants(variants: PublicCommerceVariant[]): SerializedVariant[] {
  return variants.map((variant) => ({
    id: variant.id,
    provider: typeof variant.provider === "string" ? variant.provider.trim().toLowerCase() || null : null,
    price: typeof variant.price === "number" ? variant.price : null,
    currency: typeof variant.currency === "string" ? variant.currency.trim() || null : null,
    optionValues: normalizeVariantOptionValues(variant.option_values ?? null),
  }));
}

function buildStandaloneImportedHtmlRuntimeScript({
  page,
  productSlug,
  funnelSlug,
  visitorId,
  sessionId,
  instrumentationManifest,
  variants,
  pagePathById,
  pageStageById,
}: Omit<StandaloneImportedHtmlPageProps, "htmlDocument">): string {
  const scriptConfig = {
    apiBaseUrl,
    pageId: page.pageId,
    pageSlug: page.slug,
    pageStage: page.stage,
    publicationId: page.publicationId,
    productSlug,
    funnelSlug,
    visitorId,
    sessionId,
    tracking: page.tracking ?? null,
    manifest: instrumentationManifest,
    variants: serializeVariants(variants),
    pagePathById,
    pageStageById,
  };

  return `
<script>
(() => {
  const config = ${JSON.stringify(scriptConfig)};

  const META_PIXEL_SCRIPT_ID = "mos-meta-pixel-script";
  const META_PIXEL_SCRIPT_SRC = "https://connect.facebook.net/en_US/fbevents.js";

  const cleanText = (value) => {
    if (typeof value !== "string") return null;
    const trimmed = value.trim();
    return trimmed || null;
  };

  const normalizeText = (value) =>
    String(value || "")
      .replace(/\\s+/g, " ")
      .trim();

  const isRecord = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);

  const getUtmParams = () => {
    const params = new URLSearchParams(window.location.search);
    const utm = {};
    for (const [key, value] of params.entries()) {
      if (key.startsWith("utm_")) {
        utm[key] = value;
      }
    }
    return utm;
  };

  const pendingMetaPurchaseStorageKey = (resolvedSessionId, resolvedFunnelSlug) => {
    const cleanSessionId = cleanText(resolvedSessionId);
    const cleanFunnelSlug = cleanText(resolvedFunnelSlug);
    if (!cleanSessionId || !cleanFunnelSlug) {
      return null;
    }
    return "mos-meta-purchase:" + cleanSessionId + ":" + cleanFunnelSlug;
  };

  const writePendingMetaPurchase = (key, purchase) => {
    if (!key) return;
    sessionStorage.setItem(
      key,
      JSON.stringify({
        ...purchase,
        createdAt: Date.now(),
      }),
    );
  };

  const ensureMetaPixelBootstrap = () => {
    if (!config.tracking || config.tracking.provider !== "meta" || !config.tracking.metaPixelId) {
      return null;
    }
    const pixelId = String(config.tracking.metaPixelId || "").trim();
    if (!pixelId) return null;

    if (!window.fbq) {
      const fbq = function (...args) {
        if (typeof fbq.callMethod === "function") {
          fbq.callMethod(...args);
          return;
        }
        fbq.queue = fbq.queue || [];
        fbq.queue.push(args);
      };
      fbq.queue = [];
      fbq.loaded = true;
      fbq.version = "2.0";
      window.fbq = fbq;
      window._fbq = fbq;
    }

    if (!document.getElementById(META_PIXEL_SCRIPT_ID)) {
      const script = document.createElement("script");
      script.id = META_PIXEL_SCRIPT_ID;
      script.async = true;
      script.src = META_PIXEL_SCRIPT_SRC;
      document.head.appendChild(script);
    }

    if (!Array.isArray(window.__mosMetaPixelIds)) {
      window.__mosMetaPixelIds = [];
    }
    if (!window.__mosMetaPixelIds.includes(pixelId)) {
      window.fbq("init", pixelId);
      window.__mosMetaPixelIds.push(pixelId);
    }
    return pixelId;
  };

  const trackMetaPixelForEvent = (eventType, props) => {
    const pixelId = ensureMetaPixelBootstrap();
    if (!pixelId || typeof window.fbq !== "function") {
      return;
    }
    if (eventType === "sales_to_checkout_click") {
      const variantId = cleanText(props && props.variantId);
      if (variantId) {
        window.fbq("track", "AddToCart", {
          content_ids: [variantId],
          content_type: "product",
          num_items: 1,
        });
      }
      return;
    }
    if (eventType === "pre_sales_to_sales_click") {
      window.fbq("trackCustom", "PreSalesToSalesClick", {
        from_stage: "pre_sales",
        to_stage: "sales",
      });
      return;
    }
    if (eventType === "custom_page_click") {
      window.fbq("trackCustom", "custom_page_click", props || {});
    }
  };

  const trackEvent = async (eventType, props) => {
    trackMetaPixelForEvent(eventType, props || {});
    try {
      await fetch(config.apiBaseUrl + "/public/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          events: [
            {
              eventType,
              publicationId: config.publicationId,
              pageId: config.pageId,
              visitorId: config.visitorId,
              sessionId: config.sessionId,
              path: window.location.pathname + window.location.search,
              referrer: document.referrer || undefined,
              utm: getUtmParams(),
              props: {
                fromPageId: config.pageId,
                slug: config.pageSlug,
                pageStage: config.pageStage,
                ...(props || {}),
              },
            },
          ],
        }),
        keepalive: true,
      });
    } catch (error) {
      console.error("[StandaloneImportedHtmlPage] Tracking failed.", error);
    }
  };

  const normalizeSelection = (selection) => {
    if (!isRecord(selection)) return null;
    const entries = Object.entries(selection)
      .map(([key, value]) => {
        const normalizedKey = cleanText(key);
        const normalizedValue = cleanText(typeof value === "string" ? value : null);
        if (!normalizedKey || !normalizedValue) return null;
        return [normalizedKey, normalizedValue];
      })
      .filter(Boolean);
    if (!entries.length) return null;
    return Object.fromEntries(entries);
  };

  const serializeVariant = (variant) => {
    if (!isRecord(variant)) return null;
    const id = cleanText(variant.id);
    if (!id) return null;
    const provider = cleanText(typeof variant.provider === "string" ? variant.provider.toLowerCase() : null);
    const currency = cleanText(variant.currency);
    const optionValues = normalizeSelection(variant.optionValues || variant.option_values || null);
    return {
      id,
      provider,
      price: typeof variant.price === "number" ? variant.price : null,
      currency,
      optionValues,
    };
  };

  let cachedVariants = Array.isArray(config.variants)
    ? config.variants.map(serializeVariant).filter(Boolean)
    : [];
  let cachedCommercePromise = null;
  const preparedCheckoutCache = {};
  const preparedCheckoutInFlight = {};
  const checkoutOriginPreconnects = {};
  const checkoutUrlPrefetches = {};
  const checkoutBindingElements = {};
  const checkoutBindingState = {};
  const PREPARED_CHECKOUT_TTL_MS = 10 * 60 * 1000;
  const PREPARED_CHECKOUT_RETRY_DELAYS_MS = [0, 250, 500];
  const CHECKOUT_LOADING_LABEL = "Preparing secure checkout...";
  const CHECKOUT_ERROR_LABEL = "Secure checkout is unavailable right now.";
  let warmCheckoutBindingsTimeout = null;
  let checkoutNavigationInProgress = false;

  const selectionsMatch = (left, right) => {
    const normalizedLeft = normalizeSelection(left);
    const normalizedRight = normalizeSelection(right);
    if (!normalizedLeft || !normalizedRight) return false;
    const leftEntries = Object.entries(normalizedLeft);
    const rightEntries = Object.entries(normalizedRight);
    if (leftEntries.length !== rightEntries.length) return false;
    return leftEntries.every(([key, value]) => normalizedRight[key] === value);
  };

  const buildPreparedCheckoutCacheKey = (variantId, selection) => {
    const normalizedSelection = normalizeSelection(selection) || {};
    const selectionEntries = Object.entries(normalizedSelection).sort(([left], [right]) =>
      left.localeCompare(right),
    );
    return JSON.stringify({
      variantId: cleanText(variantId) || "",
      selection: selectionEntries,
    });
  };

  const getPreparedCheckoutRecord = (cacheKey) => {
    const record = cacheKey ? preparedCheckoutCache[cacheKey] : null;
    if (!record) return null;
    if (Date.now() - record.createdAt > PREPARED_CHECKOUT_TTL_MS) {
      delete preparedCheckoutCache[cacheKey];
      return null;
    }
    return record;
  };

  const ensureCheckoutOriginPreconnect = (checkoutUrl) => {
    const href = cleanText(checkoutUrl);
    if (!href) return;
    let origin = "";
    try {
      origin = new URL(href, window.location.href).origin;
    } catch (_) {
      return;
    }
    if (!origin || checkoutOriginPreconnects[origin]) return;
    checkoutOriginPreconnects[origin] = true;
    const preconnect = document.createElement("link");
    preconnect.rel = "preconnect";
    preconnect.href = origin;
    preconnect.crossOrigin = "anonymous";
    document.head.appendChild(preconnect);
    const dnsPrefetch = document.createElement("link");
    dnsPrefetch.rel = "dns-prefetch";
    dnsPrefetch.href = origin;
    document.head.appendChild(dnsPrefetch);
  };

  const ensureCheckoutUrlPrefetch = (checkoutUrl) => {
    const href = cleanText(checkoutUrl);
    if (!href || checkoutUrlPrefetches[href]) return;
    checkoutUrlPrefetches[href] = true;
    const prefetch = document.createElement("link");
    prefetch.rel = "prefetch";
    prefetch.as = "document";
    prefetch.href = href;
    prefetch.crossOrigin = "anonymous";
    document.head.appendChild(prefetch);
  };

  const ensureCheckoutStatusNote = (bindingId, element) => {
    const existingId = cleanText(element.dataset.mosCheckoutStatusNoteId);
    if (existingId) {
      const existing = document.getElementById(existingId);
      if (existing) return existing;
    }
    const noteId =
      "mos-checkout-status-" +
      String(bindingId || "unknown") +
      "-" +
      String((checkoutBindingElements[bindingId] || []).length);
    const note = document.createElement("span");
    note.id = noteId;
    note.style.display = "none";
    note.style.width = "100%";
    note.style.marginTop = "0.5rem";
    note.style.fontSize = "0.75rem";
    note.style.lineHeight = "1.4";
    note.style.fontWeight = "600";
    note.style.letterSpacing = "normal";
    note.style.textTransform = "none";
    note.style.textAlign = "center";
    note.style.opacity = "0.82";
    note.style.color = "inherit";
    note.setAttribute("aria-live", "polite");
    element.insertAdjacentElement("afterend", note);
    element.dataset.mosCheckoutStatusNoteId = noteId;
    return note;
  };

  const setCheckoutElementWaiting = (bindingId, element, waiting, label) => {
    const note = ensureCheckoutStatusNote(bindingId, element);
    if (waiting) {
      if (!("mosCheckoutSavedPointerEvents" in element.dataset)) {
        element.dataset.mosCheckoutSavedPointerEvents = element.style.pointerEvents || "";
      }
      if (!("mosCheckoutSavedOpacity" in element.dataset)) {
        element.dataset.mosCheckoutSavedOpacity = element.style.opacity || "";
      }
      if (!("mosCheckoutSavedCursor" in element.dataset)) {
        element.dataset.mosCheckoutSavedCursor = element.style.cursor || "";
      }
      if (element instanceof HTMLButtonElement && !("mosCheckoutSavedDisabled" in element.dataset)) {
        element.dataset.mosCheckoutSavedDisabled = element.disabled ? "true" : "false";
      }
      element.dataset.mosCheckoutWaiting = "true";
      element.setAttribute("aria-busy", "true");
      element.setAttribute("aria-disabled", "true");
      element.style.pointerEvents = "none";
      element.style.opacity = "0.72";
      element.style.cursor = "progress";
      if (element instanceof HTMLButtonElement) {
        element.disabled = true;
      }
      note.textContent = cleanText(label) || CHECKOUT_LOADING_LABEL;
      note.style.display = "block";
      return;
    }

    delete element.dataset.mosCheckoutWaiting;
    element.removeAttribute("aria-busy");
    element.removeAttribute("aria-disabled");
    element.style.pointerEvents = element.dataset.mosCheckoutSavedPointerEvents || "";
    element.style.opacity = element.dataset.mosCheckoutSavedOpacity || "";
    element.style.cursor = element.dataset.mosCheckoutSavedCursor || "";
    delete element.dataset.mosCheckoutSavedPointerEvents;
    delete element.dataset.mosCheckoutSavedOpacity;
    delete element.dataset.mosCheckoutSavedCursor;
    if (element instanceof HTMLButtonElement) {
      const wasDisabled = element.dataset.mosCheckoutSavedDisabled === "true";
      element.disabled = wasDisabled;
      delete element.dataset.mosCheckoutSavedDisabled;
    }
    note.textContent = "";
    note.style.display = "none";
  };

  const renderCheckoutBindingState = (bindingId) => {
    const state = checkoutBindingState[bindingId] || { status: "idle", message: null };
    const waiting = state.status === "loading";
    const elements = checkoutBindingElements[bindingId] || [];
    for (const element of elements) {
      setCheckoutElementWaiting(bindingId, element, waiting, state.message || CHECKOUT_LOADING_LABEL);
    }
  };

  const setCheckoutBindingState = (bindingId, nextState) => {
    checkoutBindingState[bindingId] = {
      ...(checkoutBindingState[bindingId] || { status: "idle", cacheKey: null, message: null }),
      ...nextState,
    };
    renderCheckoutBindingState(bindingId);
  };

  const registerCheckoutElement = (bindingId, element) => {
    const list = checkoutBindingElements[bindingId] || [];
    if (!list.includes(element)) {
      list.push(element);
      checkoutBindingElements[bindingId] = list;
    }
    renderCheckoutBindingState(bindingId);
  };

  const resolveExternalCheckoutUrlForVariant = (items, variantId) => {
    if (!Array.isArray(items) || !variantId) return null;
    const match = items.find((item) => item && item.variantId === variantId && typeof item.url === "string");
    return match ? cleanText(match.url) : null;
  };

  const parseResponseError = async (response) => {
    try {
      const payload = await response.clone().json();
      const detail = cleanText(payload && payload.detail);
      if (detail) return detail;
      const message = cleanText(payload && payload.message);
      if (message) return message;
    } catch (_) {
      // ignore and fall back to plain text
    }
    try {
      const text = cleanText(await response.text());
      if (text) return text;
    } catch (_) {
      // ignore and fall back to status text
    }
    return cleanText(response.statusText) || "Request failed.";
  };

  const delay = (durationMs) =>
    new Promise((resolve) => {
      window.setTimeout(resolve, durationMs);
    });

  const loadCommerceVariants = async () => {
    if (cachedVariants.length) {
      return cachedVariants;
    }
    if (cachedCommercePromise) {
      return cachedCommercePromise;
    }
    cachedCommercePromise = fetch(
      config.apiBaseUrl +
        "/public/funnels/" +
        encodeURIComponent(config.productSlug) +
        "/" +
        encodeURIComponent(config.funnelSlug) +
        "/commerce",
    )
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(await parseResponseError(response));
        }
        const payload = await response.json();
        const product = payload && payload.product;
        const variants = Array.isArray(product && product.variants)
          ? product.variants.map(serializeVariant).filter(Boolean)
          : [];
        cachedVariants = variants;
        return cachedVariants;
      })
      .finally(() => {
        cachedCommercePromise = null;
      });
    return cachedCommercePromise;
  };

  const resolveCheckoutUrls = () => {
    const checkoutReturnUrl = new URL(window.location.href);
    const checkoutCancelUrl = new URL(window.location.href);
    checkoutReturnUrl.searchParams.set("checkout", "success");
    checkoutCancelUrl.searchParams.set("checkout", "cancel");
    return {
      successUrl: checkoutReturnUrl.toString(),
      cancelUrl: checkoutCancelUrl.toString(),
    };
  };

  const createCheckoutPayload = ({ resolvedVariantId, resolvedSelection }) => {
    const checkoutUrls = resolveCheckoutUrls();
    return {
      funnelSlug: config.funnelSlug,
      variantId: resolvedVariantId || undefined,
      selection: resolvedSelection,
      quantity: 1,
      successUrl: checkoutUrls.successUrl,
      cancelUrl: checkoutUrls.cancelUrl,
      pageId: config.pageId,
      visitorId: config.visitorId,
      sessionId: config.sessionId,
      utm: getUtmParams(),
    };
  };

  const requestCheckout = async ({ resolvedVariantId, resolvedSelection }) => {
    const response = await fetch(config.apiBaseUrl + "/public/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(createCheckoutPayload({ resolvedVariantId, resolvedSelection })),
    });

    if (!response.ok) {
      throw new Error((await response.text()) || response.statusText || "Checkout failed.");
    }

    const data = await response.json();
    const checkoutUrl = cleanText(data && data.checkoutUrl);
    if (!checkoutUrl) {
      throw new Error("Checkout URL is missing.");
    }
    ensureCheckoutOriginPreconnect(checkoutUrl);
    ensureCheckoutUrlPrefetch(checkoutUrl);
    return {
      checkoutUrl,
      sessionId: cleanText(data && data.sessionId) || null,
    };
  };

  const resolveVariantForCheckout = (checkout, selectionFromDom, variants) => {
    const resolver = checkout && checkout.variantResolver;
    if (!resolver || typeof resolver.type !== "string") {
      throw new Error("Checkout binding is missing a variantResolver.");
    }
    if (resolver.type === "fixed") {
      const variantId = cleanText(resolver.variantId);
      const variant = variants.find((candidate) => candidate.id === variantId) || null;
      return {
        variantId,
        variant,
        selection: selectionFromDom || (variant && variant.optionValues ? variant.optionValues : null),
      };
    }
    if (resolver.type === "option_values") {
      return {
        variantId: null,
        variant: variants.find((candidate) => selectionsMatch(candidate.optionValues, selectionFromDom)) || null,
        selection: selectionFromDom,
      };
    }
    throw new Error("Unsupported checkout resolver type.");
  };

  const resolveCheckoutBindingState = async (binding) => {
    const selectionFromDom = readSelectionFromResolver(binding.checkout.variantResolver, binding.id || "unknown");
    const checkoutVariants =
      selectionFromDom && !cachedVariants.length ? await loadCommerceVariants() : cachedVariants;
    const { variantId, variant, selection } = resolveVariantForCheckout(
      binding.checkout,
      selectionFromDom,
      checkoutVariants,
    );
    const resolvedVariantId = cleanText(variant && variant.id ? variant.id : variantId);
    const resolvedSelection = normalizeSelection(selection) || {};
    return {
      variant,
      resolvedVariantId,
      resolvedSelection,
      cacheKey: buildPreparedCheckoutCacheKey(resolvedVariantId, resolvedSelection),
    };
  };

  const prepareCheckoutInBackground = async ({ variant, resolvedVariantId, resolvedSelection, cacheKey }) => {
    if (!cacheKey || !variant || variant.provider !== "shopify") {
      return null;
    }
    const cachedRecord = getPreparedCheckoutRecord(cacheKey);
    if (cachedRecord) {
      return cachedRecord;
    }
    if (preparedCheckoutInFlight[cacheKey]) {
      return preparedCheckoutInFlight[cacheKey];
    }
    const promise = (async () => {
      let lastError = null;
      for (const retryDelayMs of PREPARED_CHECKOUT_RETRY_DELAYS_MS) {
        if (retryDelayMs > 0) {
          await delay(retryDelayMs);
        }
        try {
          const preparedCheckout = await requestCheckout({ resolvedVariantId, resolvedSelection });
          const record = {
            ...preparedCheckout,
            variantId: resolvedVariantId || "",
            selection: resolvedSelection,
            createdAt: Date.now(),
          };
          preparedCheckoutCache[cacheKey] = record;
          return record;
        } catch (error) {
          lastError = error;
        }
      }
      console.error("[StandaloneImportedHtmlPage] Failed to prepare checkout in background.", lastError);
      return null;
    })()
      .finally(() => {
        delete preparedCheckoutInFlight[cacheKey];
      });
    preparedCheckoutInFlight[cacheKey] = promise;
    return promise;
  };

  const waitForPreparedCheckout = async (cacheKey) => {
    if (!cacheKey || !preparedCheckoutInFlight[cacheKey]) {
      return null;
    }
    return preparedCheckoutInFlight[cacheKey];
  };

  const syncCheckoutBindingWarmState = async (binding) => {
    const bindingId = String(binding && binding.id ? binding.id : "unknown");
    const checkoutState = await resolveCheckoutBindingState(binding);
    const isWarmable =
      Boolean(checkoutState.cacheKey) &&
      Boolean(checkoutState.variant) &&
      checkoutState.variant.provider === "shopify";

    if (!isWarmable) {
      setCheckoutBindingState(bindingId, {
        status: "idle",
        cacheKey: checkoutState.cacheKey || null,
        message: null,
      });
      return checkoutState;
    }

    const preparedCheckout = getPreparedCheckoutRecord(checkoutState.cacheKey);
    if (preparedCheckout) {
      setCheckoutBindingState(bindingId, {
        status: "ready",
        cacheKey: checkoutState.cacheKey,
        message: null,
      });
      return checkoutState;
    }

    setCheckoutBindingState(bindingId, {
      status: "loading",
      cacheKey: checkoutState.cacheKey,
      message: CHECKOUT_LOADING_LABEL,
    });

    void prepareCheckoutInBackground(checkoutState).then(() => {
      const currentState = checkoutBindingState[bindingId];
      if (!currentState || currentState.cacheKey !== checkoutState.cacheKey) {
        return;
      }
      if (getPreparedCheckoutRecord(checkoutState.cacheKey)) {
        setCheckoutBindingState(bindingId, {
          status: "ready",
          cacheKey: checkoutState.cacheKey,
          message: null,
        });
        return;
      }
      setCheckoutBindingState(bindingId, {
        status: "error",
        cacheKey: checkoutState.cacheKey,
        message: CHECKOUT_ERROR_LABEL,
      });
    });

    return checkoutState;
  };

  const ensurePreparedCheckoutForClick = async ({
    bindingId,
    cacheKey,
    variant,
    resolvedVariantId,
    resolvedSelection,
  }) => {
    const isWarmableShopifyCheckout = Boolean(cacheKey) && Boolean(variant) && variant.provider === "shopify";
    if (!isWarmableShopifyCheckout) {
      return requestCheckout({ resolvedVariantId, resolvedSelection });
    }
    let preparedCheckout = getPreparedCheckoutRecord(cacheKey);
    if (preparedCheckout) {
      return preparedCheckout;
    }
    setCheckoutBindingState(bindingId, {
      status: "loading",
      cacheKey,
      message: CHECKOUT_LOADING_LABEL,
    });
    preparedCheckout =
      (await waitForPreparedCheckout(cacheKey)) ||
      (await prepareCheckoutInBackground({ variant, resolvedVariantId, resolvedSelection, cacheKey }));
    if (!preparedCheckout) {
      setCheckoutBindingState(bindingId, {
        status: "error",
        cacheKey,
        message: CHECKOUT_ERROR_LABEL,
      });
      throw new Error("Prepared checkout is unavailable.");
    }
    setCheckoutBindingState(bindingId, {
      status: "ready",
      cacheKey,
      message: null,
    });
    return preparedCheckout;
  };

  const isCheckoutBindingTarget = (target) => {
    if (!(target instanceof Node)) {
      return false;
    }
    return Object.values(checkoutBindingElements).some((elements) =>
      Array.isArray(elements) && elements.some((element) => element instanceof HTMLElement && element.contains(target)),
    );
  };

  const readNodeValue = (node, source) => {
    if (!node) return "";
    if (source === "text") {
      return normalizeText(node.textContent || "");
    }
    if (node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement || node instanceof HTMLSelectElement) {
      return normalizeText(node.value || "");
    }
    return normalizeText(node.textContent || "");
  };

  const readSelectionFromResolver = (resolver, bindingId) => {
    if (!resolver || resolver.type !== "option_values") return null;
    const selection = {};
    const optionSelectors = Array.isArray(resolver.optionSelectors) ? resolver.optionSelectors : [];
    for (const option of optionSelectors) {
      const selector = cleanText(option && option.selector);
      const optionName = cleanText(option && option.name);
      const source = option && option.source === "text" ? "text" : "value";
      if (!selector || !optionName) {
        throw new Error("Checkout binding '" + bindingId + "' has an invalid option selector.");
      }
      const matches = Array.from(document.querySelectorAll(selector));
      if (matches.length !== 1) {
        throw new Error(
          "Checkout binding '" +
            bindingId +
            "' option selector '" +
            selector +
            "' matched " +
            String(matches.length) +
            " elements.",
        );
      }
      const value = readNodeValue(matches[0], source);
      if (!value) {
        throw new Error(
          "Checkout binding '" + bindingId + "' could not resolve a non-empty option value for '" + optionName + "'.",
        );
      }
      selection[optionName] = value;
    }
    return selection;
  };

  const findSmallestElementContainingText = (text) => {
    const target = cleanText(text);
    if (!target || !document.body) return null;

    let match = null;
    let matchLength = Number.POSITIVE_INFINITY;
    const elements = Array.from(document.body.querySelectorAll("*"));
    for (const element of elements) {
      const content = normalizeText(element.textContent || "");
      if (!content || !content.includes(target)) continue;
      if (content.length < matchLength) {
        match = element;
        matchLength = content.length;
      }
    }
    return match;
  };

  const applyMobileSpacingFixes = () => {
    if (window.innerWidth >= 768 || !document.body) return;

    const loadMoreComments = findSmallestElementContainingText("Load more comments...");
    const healthDisclaimer = findSmallestElementContainingText("HEALTH DISCLAIMER:");
    if (loadMoreComments && healthDisclaimer) {
      healthDisclaimer.style.marginTop = "1rem";
      healthDisclaimer.style.paddingBottom = "1rem";
      healthDisclaimer.style.color = "rgba(45, 41, 38, 0.4)";
      healthDisclaimer.style.opacity = "1";

      const copyright = findSmallestElementContainingText("All Rights Reserved.");
      if (copyright) {
        copyright.style.marginBottom = "1.25rem";
        copyright.style.color = "rgba(45, 41, 38, 0.35)";
        copyright.style.opacity = "1";
      }
    }

    const footer = document.querySelector("footer");
    const newsletterHeading = findSmallestElementContainingText("Join 14,000+ Women");
    const footerFinePrint = findSmallestElementContainingText("These statements have not been evaluated");
    if (footer && newsletterHeading && footerFinePrint) {
      footer.style.paddingTop = "2.5rem";
      footer.style.paddingBottom = "2rem";

      const newsletterBlock = newsletterHeading.parentElement;
      if (newsletterBlock) {
        newsletterBlock.style.marginBottom = "2.5rem";
      }

      footerFinePrint.style.marginTop = "1.5rem";
      footerFinePrint.style.color = "#6b7280";
      footerFinePrint.style.opacity = "1";
    }
  };

  const bindManifest = () => {
    if (!config.manifest || !Array.isArray(config.manifest.bindings)) return;

    for (const binding of config.manifest.bindings) {
      if (!binding || typeof binding !== "object") continue;
      const selector = cleanText(binding.selector);
      if (!selector) continue;

      const matches = Array.from(document.querySelectorAll(selector));
      if (matches.length < 1) {
        console.error(
          "[StandaloneImportedHtmlPage] Binding '" +
            String(binding.id || "unknown") +
            "' selector '" +
            selector +
            "' matched no elements.",
        );
        continue;
      }

      for (const element of matches) {
        if (!(element instanceof HTMLElement)) {
          continue;
        }
        if (element.dataset.mosStandaloneImportedHtmlBound === "true") {
          continue;
        }
        if (binding.type === "checkout" && binding.checkout) {
          registerCheckoutElement(String(binding.id || "unknown"), element);
        }
        element.dataset.mosStandaloneImportedHtmlBound = "true";
        element.addEventListener("click", async (event) => {
          event.preventDefault();
          event.stopPropagation();

          const buttonText = normalizeText(element.textContent || "");
          try {
            if (binding.type === "internal_navigation") {
              const targetPath = config.pagePathById[String(binding.targetPageId || "")];
              const targetStage = cleanText(config.pageStageById && config.pageStageById[String(binding.targetPageId || "")]);
              if (!targetPath) {
                throw new Error("Target page path is missing for binding '" + String(binding.id || "unknown") + "'.");
              }
              await trackEvent(binding.trackEventType || "custom_page_click", {
                fromStage: config.pageStage,
                toStage: targetStage || "custom",
                targetPageId: binding.targetPageId,
                buttonText: buttonText || undefined,
              });
              window.location.href = targetPath;
              return;
            }

            if (binding.type === "track_only") {
              await trackEvent(binding.trackEventType || "custom_page_click", {
                fromStage: config.pageStage,
                pageId: config.pageId,
                buttonText: buttonText || undefined,
                bindingId: binding.id,
              });
              return;
            }

            if (binding.type !== "checkout" || !binding.checkout) {
              throw new Error("Unsupported binding type.");
            }

            const bindingId = String(binding.id || "unknown");
            const { variant, resolvedVariantId, resolvedSelection, cacheKey } = await syncCheckoutBindingWarmState(
              binding,
            );

            void trackEvent(
              binding.trackEventType || "sales_to_checkout_click",
              {
                fromStage: config.pageStage,
                toStage: "checkout",
                bindingId,
                buttonText: buttonText || undefined,
                ...(resolvedVariantId ? { variantId: resolvedVariantId } : {}),
              },
            );

            if (binding.checkout.mode === "external_checkout_url") {
              const checkoutUrl = resolveExternalCheckoutUrlForVariant(
                binding.checkout.externalUrlsByVariant || [],
                resolvedVariantId,
              );
              if (!checkoutUrl) {
                throw new Error("Missing external checkout URL for binding '" + String(binding.id || "unknown") + "'.");
              }
              window.location.href = checkoutUrl;
              return;
            }

            const checkout = await ensurePreparedCheckoutForClick({
              bindingId,
              cacheKey,
              variant,
              resolvedVariantId,
              resolvedSelection,
            });

            if (variant && variant.provider === "stripe") {
              const pendingKey = pendingMetaPurchaseStorageKey(config.sessionId, config.funnelSlug);
              if (pendingKey) {
                writePendingMetaPurchase(pendingKey, {
                  funnelSlug: config.funnelSlug,
                  pageId: config.pageId,
                  variantId: variant.id,
                  value: typeof variant.price === "number" ? variant.price : null,
                  currency: variant.currency || null,
                  quantity: 1,
                  provider: variant.provider,
                });
              }
            }

            checkoutNavigationInProgress = true;
            window.location.href = checkout.checkoutUrl;
          } catch (error) {
            console.error(
              "[StandaloneImportedHtmlPage] Binding '" + String(binding.id || "unknown") + "' failed.",
              error,
            );
            setCheckoutBindingState(String(binding.id || "unknown"), {
              status: "error",
              cacheKey: null,
              message: CHECKOUT_ERROR_LABEL,
            });
          }
        });
      }
    }
  };

  const bindManifestSafely = () => {
    try {
      bindManifest();
    } catch (error) {
      console.error("[StandaloneImportedHtmlPage] Failed to bind manifest.", error);
    }
  };

  const applyMobileSpacingFixesSafely = () => {
    try {
      applyMobileSpacingFixes();
    } catch (error) {
      console.error("[StandaloneImportedHtmlPage] Failed to apply mobile spacing fixes.", error);
    }
  };

  const warmCheckoutBindings = async () => {
    if (!config.manifest || !Array.isArray(config.manifest.bindings)) return;
    await Promise.all(
      config.manifest.bindings.map(async (binding) => {
        if (!binding || typeof binding !== "object") return;
        if (binding.type !== "checkout" || !binding.checkout) return;
        if (binding.checkout.mode === "external_checkout_url") return;
        try {
          await syncCheckoutBindingWarmState(binding);
        } catch (_) {
          setCheckoutBindingState(String(binding.id || "unknown"), {
            status: "error",
            cacheKey: null,
            message: CHECKOUT_ERROR_LABEL,
          });
        }
      }),
    );
  };

  const warmCheckoutBindingsSafely = () => {
    try {
      void warmCheckoutBindings();
    } catch (error) {
      console.error("[StandaloneImportedHtmlPage] Failed to warm checkout bindings.", error);
    }
  };

  const scheduleWarmCheckoutBindings = (delayMs = 75) => {
    if (warmCheckoutBindingsTimeout !== null) {
      window.clearTimeout(warmCheckoutBindingsTimeout);
    }
    warmCheckoutBindingsTimeout = window.setTimeout(() => {
      warmCheckoutBindingsTimeout = null;
      warmCheckoutBindingsSafely();
    }, delayMs);
  };

  bindManifestSafely();
  warmCheckoutBindingsSafely();
  applyMobileSpacingFixesSafely();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindManifestSafely, { once: true });
    document.addEventListener("DOMContentLoaded", warmCheckoutBindingsSafely, { once: true });
    document.addEventListener("DOMContentLoaded", applyMobileSpacingFixesSafely, { once: true });
  }
  window.addEventListener("load", bindManifestSafely, { once: true });
  window.addEventListener("load", warmCheckoutBindingsSafely, { once: true });
  window.addEventListener("load", applyMobileSpacingFixesSafely, { once: true });
  window.setTimeout(bindManifestSafely, 0);
  window.setTimeout(bindManifestSafely, 250);
  window.setTimeout(bindManifestSafely, 1000);
  window.setTimeout(warmCheckoutBindingsSafely, 0);
  window.setTimeout(warmCheckoutBindingsSafely, 250);
  window.setTimeout(warmCheckoutBindingsSafely, 1000);
  window.setTimeout(applyMobileSpacingFixesSafely, 0);
  window.setTimeout(applyMobileSpacingFixesSafely, 250);
  window.setTimeout(applyMobileSpacingFixesSafely, 1000);
  window.addEventListener("resize", applyMobileSpacingFixesSafely);
  document.addEventListener("click", (event) => {
    if (checkoutNavigationInProgress || isCheckoutBindingTarget(event.target)) {
      return;
    }
    scheduleWarmCheckoutBindings();
  }, true);
  document.addEventListener("input", () => scheduleWarmCheckoutBindings(), true);
  document.addEventListener("change", () => scheduleWarmCheckoutBindings(), true);
  window.addEventListener("pageshow", () => scheduleWarmCheckoutBindings(0));
})();
</script>`;
}

function injectStandaloneRuntimeScript(
  htmlDocument: string,
  runtimeScript: string,
): string {
  if (/<\/body>/i.test(htmlDocument)) {
    return htmlDocument.replace(/<\/body>/i, `${runtimeScript}</body>`);
  }
  if (/<\/html>/i.test(htmlDocument)) {
    return htmlDocument.replace(/<\/html>/i, `${runtimeScript}</html>`);
  }
  return `${htmlDocument}${runtimeScript}`;
}

export function StandaloneImportedHtmlPage(props: StandaloneImportedHtmlPageProps) {
  useEffect(() => {
    const normalizedHtml = props.htmlDocument.trim();
    if (!normalizedHtml) {
      throw new Error("Standalone imported HTML page is empty.");
    }
    if (window.__mosImportedHtmlStandalonePageId === props.page.pageId) {
      return;
    }
    window.__mosImportedHtmlStandalonePageId = props.page.pageId;
    const runtimeScript = buildStandaloneImportedHtmlRuntimeScript(props);
    const nextDocument = injectStandaloneRuntimeScript(normalizedHtml, runtimeScript);
    document.open();
    document.write(nextDocument);
    document.close();
  }, [props]);

  return null;
}
