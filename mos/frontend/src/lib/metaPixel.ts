declare global {
  interface Window {
    fbq?: ((...args: unknown[]) => void) & {
      callMethod?: (...args: unknown[]) => void;
      loaded?: boolean;
      push?: (...args: unknown[]) => number;
      queue?: unknown[];
      version?: string;
    };
    _fbq?: Window["fbq"];
    __mosMetaPixelIds?: string[];
  }
}

const META_PIXEL_SCRIPT_ID = "mos-meta-pixel-script";
const META_PIXEL_SCRIPT_SRC = "https://connect.facebook.net/en_US/fbevents.js";
const META_PIXEL_DEFER_TIMEOUT_MS = 1500;
type MetaPixelMethod = "track" | "trackCustom";

declare global {
  interface Window {
    __mosMetaPixelLoadScheduled?: boolean;
  }
}

function loadMetaPixelScript() {
  if (typeof document === "undefined" || document.getElementById(META_PIXEL_SCRIPT_ID)) {
    return;
  }

  const script = document.createElement("script");
  script.id = META_PIXEL_SCRIPT_ID;
  script.async = true;
  script.src = META_PIXEL_SCRIPT_SRC;
  document.head.appendChild(script);
}

function scheduleMetaPixelScriptLoad() {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return;
  }
  if (document.getElementById(META_PIXEL_SCRIPT_ID) || window.__mosMetaPixelLoadScheduled) {
    return;
  }

  window.__mosMetaPixelLoadScheduled = true;
  const flush = () => {
    window.__mosMetaPixelLoadScheduled = false;
    loadMetaPixelScript();
  };

  const listenerOptions = { capture: true, once: true } as const;
  window.addEventListener("pointerdown", flush, listenerOptions);
  window.addEventListener("keydown", flush, listenerOptions);
  window.addEventListener("touchstart", flush, listenerOptions);

  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(flush, { timeout: META_PIXEL_DEFER_TIMEOUT_MS });
    return;
  }

  window.setTimeout(flush, META_PIXEL_DEFER_TIMEOUT_MS);
}

function ensureMetaPixelBootstrap() {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return;
  }

  if (!window.fbq) {
    const fbq = function (...args: unknown[]) {
      if (typeof fbq.callMethod === "function") {
        fbq.callMethod(...args);
        return;
      }
      fbq.queue = fbq.queue || [];
      fbq.queue.push(args);
    } as NonNullable<Window["fbq"]>;
    fbq.queue = [];
    fbq.loaded = true;
    fbq.version = "2.0";
    window.fbq = fbq;
    window._fbq = fbq;
  }

  scheduleMetaPixelScriptLoad();

  if (!Array.isArray(window.__mosMetaPixelIds)) {
    window.__mosMetaPixelIds = [];
  }
}

export function ensureMetaPixel(pixelId?: string | null): string | null {
  const trimmedPixelId = typeof pixelId === "string" ? pixelId.trim() : "";
  if (!trimmedPixelId) {
    return null;
  }

  ensureMetaPixelBootstrap();
  if (typeof window === "undefined" || !window.fbq) {
    return null;
  }

  const pixelIds = window.__mosMetaPixelIds || [];
  if (!pixelIds.includes(trimmedPixelId)) {
    window.fbq("init", trimmedPixelId);
    pixelIds.push(trimmedPixelId);
    window.__mosMetaPixelIds = pixelIds;
  }
  return trimmedPixelId;
}

export function trackMetaPixelEvent(
  pixelId: string | null | undefined,
  eventName: string,
  params?: Record<string, unknown>,
  method: MetaPixelMethod = "track",
) {
  const resolvedPixelId = ensureMetaPixel(pixelId);
  if (!resolvedPixelId || typeof window === "undefined" || !window.fbq) {
    return;
  }
  if (params && Object.keys(params).length > 0) {
    window.fbq(method, eventName, params);
    return;
  }
  window.fbq(method, eventName);
}
