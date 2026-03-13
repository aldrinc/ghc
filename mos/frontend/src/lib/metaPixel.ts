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
) {
  const resolvedPixelId = ensureMetaPixel(pixelId);
  if (!resolvedPixelId || typeof window === "undefined" || !window.fbq) {
    return;
  }
  if (params && Object.keys(params).length > 0) {
    window.fbq("track", eventName, params);
    return;
  }
  window.fbq("track", eventName);
}
