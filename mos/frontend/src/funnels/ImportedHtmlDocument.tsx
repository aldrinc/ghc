import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { buildPublicFunnelPath, resolvePublicApiBaseUrl } from "@/funnels/runtimeRouting";
import { checkoutClickEventForStage, navigationClickEventForStages } from "@/lib/funnelTracking";
import { pendingMetaPurchaseStorageKey, writePendingMetaPurchase } from "@/lib/metaCheckout";
import type { PublicFunnelCommerce } from "@/types/commerce";
import type { PublicFunnelStage } from "@/types/funnels";

const IMPORTED_HTML_HEIGHT_MESSAGE = "mos:imported-html-document:height";
const IMPORTED_HTML_ACTION_MESSAGE = "mos:imported-html-document:action";
const DEFAULT_INITIAL_HEIGHT = 900;
const MAX_FRAME_HEIGHT = 20000;
const apiBaseUrl = resolvePublicApiBaseUrl();

function getUtmParams(): Record<string, string> {
  const params = new URLSearchParams(window.location.search);
  const utm: Record<string, string> = {};
  for (const [key, value] of params.entries()) {
    if (key.startsWith("utm_")) {
      utm[key] = value;
    }
  }
  return utm;
}

type ImportedHtmlBinding =
  | {
      id?: string;
      type: "internal_navigation";
      event: "click";
      selector: string;
      targetPageId?: string;
      trackEventType?: string;
    }
  | {
      id?: string;
      type: "checkout";
      event: "click";
      selector: string;
      trackEventType?: string;
      checkout?: {
        mode?: "public_checkout" | string;
        variantResolver?: {
          type?: "fixed" | string;
          variantId?: string;
        } | null;
      } | null;
    };

export type ImportedHtmlInstrumentationManifest = {
  schemaVersion?: string;
  pageStage?: PublicFunnelStage;
  bindings?: ImportedHtmlBinding[];
};

type ImportedHtmlRuntime = {
  productSlug: string;
  funnelSlug: string;
  pageMap: Record<string, string>;
  pageStageMap: Record<string, PublicFunnelStage>;
  bundleMode?: boolean;
  pageStage?: PublicFunnelStage;
  trackEvent?: (event: { eventType: string; props?: Record<string, unknown> }) => void;
  commerce?: PublicFunnelCommerce | null;
  commerceError?: string | null;
  pageId?: string | null;
  visitorId?: string | null;
  sessionId?: string | null;
};

type ImportedHtmlActionPayload =
  | {
      bindingId?: string;
      type: "internal_navigation";
      targetPageId?: string;
      trackEventType?: string;
    }
  | {
      bindingId?: string;
      type: "checkout";
      trackEventType?: string;
      checkout?: {
        mode?: "public_checkout" | string;
        variantResolver?: {
          type?: "fixed" | string;
          variantId?: string;
        } | null;
      } | null;
    };

function injectRuntimeScripts(
  htmlDocument: string,
  {
    frameId,
    instrumentationManifest,
  }: {
    frameId: string;
    instrumentationManifest?: ImportedHtmlInstrumentationManifest;
  },
): string {
  const resizeScript = `
<script>
(function() {
  var FRAME_ID = ${JSON.stringify(frameId)};
  var TYPE = ${JSON.stringify(IMPORTED_HTML_HEIGHT_MESSAGE)};
  function measure() {
    var body = document.body;
    var doc = document.documentElement;
    var height = Math.max(
      body ? body.scrollHeight : 0,
      body ? body.offsetHeight : 0,
      doc ? doc.scrollHeight : 0,
      doc ? doc.offsetHeight : 0
    );
    parent.postMessage({ type: TYPE, frameId: FRAME_ID, height: height }, "*");
  }
  window.addEventListener("load", function() {
    measure();
    setTimeout(measure, 50);
    setTimeout(measure, 250);
    setTimeout(measure, 1000);
  });
  window.addEventListener("resize", measure);
  if (typeof ResizeObserver === "function") {
    var observer = new ResizeObserver(measure);
    if (document.documentElement) observer.observe(document.documentElement);
    if (document.body) observer.observe(document.body);
  }
})();
</script>`;

  const normalizedBindings = Array.isArray(instrumentationManifest?.bindings)
    ? instrumentationManifest.bindings.filter(
        (binding): binding is ImportedHtmlBinding =>
          Boolean(binding) &&
          binding.event === "click" &&
          typeof binding.selector === "string" &&
          binding.selector.trim().length > 0,
      )
    : [];
  const actionScript =
    normalizedBindings.length > 0
      ? `
<script>
(function() {
  var FRAME_ID = ${JSON.stringify(frameId)};
  var TYPE = ${JSON.stringify(IMPORTED_HTML_ACTION_MESSAGE)};
  var bindings = ${JSON.stringify(normalizedBindings)};

  function postAction(action) {
    parent.postMessage({ type: TYPE, frameId: FRAME_ID, action: action }, "*");
  }

  function isPrimaryClick(event) {
    return (
      !event.defaultPrevented &&
      event.button === 0 &&
      !event.metaKey &&
      !event.ctrlKey &&
      !event.shiftKey &&
      !event.altKey
    );
  }

  function bindClick(binding) {
    var elements = [];
    try {
      elements = Array.prototype.slice.call(document.querySelectorAll(binding.selector));
    } catch (_error) {
      return;
    }

    elements.forEach(function(element) {
      if (!element) return;
      var registry = element.__mosImportedHtmlBindings;
      if (!registry || typeof registry !== "object") {
        registry = {};
        element.__mosImportedHtmlBindings = registry;
      }
      var bindingKey = String(binding.id || binding.type + ":" + binding.selector);
      if (registry[bindingKey]) return;
      registry[bindingKey] = true;
      element.addEventListener("click", function(event) {
        if (!isPrimaryClick(event)) return;
        event.preventDefault();
        event.stopPropagation();
        postAction(binding);
      });
    });
  }

  function bindAll() {
    bindings.forEach(bindClick);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindAll, { once: true });
  } else {
    bindAll();
  }
  window.addEventListener("load", bindAll);
  setTimeout(bindAll, 50);
  setTimeout(bindAll, 250);
})();
</script>`
      : "";

  const runtimeScripts = `${resizeScript}${actionScript}`;
  if (/<\/body>/i.test(htmlDocument)) {
    return htmlDocument.replace(/<\/body>/i, `${runtimeScripts}</body>`);
  }
  if (/<\/html>/i.test(htmlDocument)) {
    return htmlDocument.replace(/<\/html>/i, `${runtimeScripts}</html>`);
  }
  return `${htmlDocument}${runtimeScripts}`;
}

export function ImportedHtmlDocument({
  id,
  title,
  htmlDocument,
  instrumentationManifest,
  runtime,
}: {
  id?: string;
  title?: string;
  htmlDocument?: string;
  instrumentationManifest?: ImportedHtmlInstrumentationManifest;
  runtime?: ImportedHtmlRuntime | null;
}) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [height, setHeight] = useState(DEFAULT_INITIAL_HEIGHT);
  const [actionError, setActionError] = useState<string | null>(null);
  const frameId = id || "imported-html-document";
  const navigate = useNavigate();

  const srcDoc = useMemo(() => {
    const normalizedHtml = typeof htmlDocument === "string" ? htmlDocument.trim() : "";
    if (!normalizedHtml) return "";
    return injectRuntimeScripts(normalizedHtml, { frameId, instrumentationManifest });
  }, [frameId, htmlDocument, instrumentationManifest]);

  useEffect(() => {
    setHeight(DEFAULT_INITIAL_HEIGHT);
    setActionError(null);
  }, [frameId, srcDoc]);

  useEffect(() => {
    async function handleAction(action: ImportedHtmlActionPayload) {
      if (!runtime) {
        throw new Error("Imported HTML actions require a funnel runtime.");
      }
      if (action.type === "internal_navigation") {
        const targetPageId = typeof action.targetPageId === "string" ? action.targetPageId.trim() : "";
        if (!targetPageId) {
          throw new Error("Imported HTML navigation is missing a target page.");
        }
        const targetSlug = runtime.pageMap[targetPageId];
        if (!targetSlug) {
          throw new Error("Imported HTML navigation target is not available in this funnel.");
        }
        const targetStage = runtime.pageStageMap[targetPageId] || "custom";
        runtime.trackEvent?.(
          navigationClickEventForStages({
            fromStage: runtime.pageStage || "custom",
            toStage: targetStage,
            props: {
              targetPageId,
              bindingId: action.bindingId || undefined,
            },
          }),
        );
        const targetPath = buildPublicFunnelPath({
          productSlug: runtime.productSlug,
          funnelSlug: runtime.funnelSlug,
          slug: targetSlug,
          bundleMode: Boolean(runtime.bundleMode),
        });
        navigate(`${targetPath}${window.location.search}${window.location.hash}`);
        return;
      }

      if (action.type !== "checkout") {
        throw new Error("Imported HTML action type is not supported.");
      }
      const checkoutMode = action.checkout?.mode || "";
      if (checkoutMode !== "public_checkout") {
        throw new Error("Imported HTML checkout only supports public checkout.");
      }
      if (runtime.commerceError) {
        throw new Error(runtime.commerceError);
      }
      if (!runtime.commerce) {
        throw new Error("Commerce data is not available.");
      }
      const variantResolver = action.checkout?.variantResolver;
      if (
        variantResolver?.type !== "fixed" ||
        typeof variantResolver.variantId !== "string" ||
        !variantResolver.variantId.trim()
      ) {
        throw new Error("Imported HTML checkout requires a fixed variant resolver.");
      }
      const variants = runtime.commerce.product?.variants || [];
      if (!variants.length) {
        throw new Error("Checkout is not configured for this funnel product. No product variants were found.");
      }
      const variant = variants.find((item) => item.id === variantResolver.variantId);
      if (!variant) {
        throw new Error("Configured checkout variant is not available for this funnel product.");
      }
      if (!variant.provider) {
        throw new Error("Checkout is not configured for this funnel product. Variant provider is missing.");
      }

      const checkoutReturnUrl = new URL(window.location.href);
      const checkoutCancelUrl = new URL(window.location.href);
      checkoutReturnUrl.searchParams.set("checkout", "success");
      checkoutCancelUrl.searchParams.set("checkout", "cancel");

      runtime.trackEvent?.(
        checkoutClickEventForStage({
          fromStage: runtime.pageStage || "custom",
          props: {
            variantId: variant.id,
            bindingId: action.bindingId || undefined,
          },
        }),
      );

      const response = await fetch(`${apiBaseUrl}/public/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          funnelSlug: runtime.funnelSlug,
          variantId: variant.id,
          selection: variant.option_values || undefined,
          quantity: 1,
          successUrl: checkoutReturnUrl.toString(),
          cancelUrl: checkoutCancelUrl.toString(),
          pageId: runtime.pageId || undefined,
          visitorId: runtime.visitorId || undefined,
          sessionId: runtime.sessionId || undefined,
          utm: getUtmParams(),
        }),
      });
      if (!response.ok) {
        const message = (await response.text()) || response.statusText;
        throw new Error(message || "Checkout failed.");
      }
      const data = await response.json();
      const checkoutUrl = typeof data?.checkoutUrl === "string" ? data.checkoutUrl.trim() : "";
      if (!checkoutUrl) {
        throw new Error("Checkout URL is missing.");
      }
      const normalizedProvider = typeof variant.provider === "string" ? variant.provider.trim().toLowerCase() : "";
      const pendingPurchaseKey = pendingMetaPurchaseStorageKey(runtime.sessionId || null, runtime.funnelSlug);
      if (normalizedProvider === "stripe" && pendingPurchaseKey) {
        writePendingMetaPurchase(sessionStorage, pendingPurchaseKey, {
          funnelSlug: runtime.funnelSlug,
          pageId: runtime.pageId || null,
          variantId: variant.id,
          value: variant.price,
          currency: variant.currency || null,
          quantity: 1,
          provider: normalizedProvider,
        });
      }
      window.location.assign(checkoutUrl);
    }

    function handleMessage(event: MessageEvent) {
      const data = event.data;
      if (!data || typeof data !== "object") return;
      if (data.frameId !== frameId) return;
      if (data.type === IMPORTED_HTML_HEIGHT_MESSAGE) {
        const nextHeight = Number(data.height);
        if (!Number.isFinite(nextHeight) || nextHeight <= 0) return;
        setHeight(Math.min(MAX_FRAME_HEIGHT, Math.ceil(nextHeight)));
        return;
      }
      if (data.type !== IMPORTED_HTML_ACTION_MESSAGE) return;
      setActionError(null);
      void handleAction(data.action as ImportedHtmlActionPayload).catch((error: unknown) => {
        setActionError(error instanceof Error ? error.message : "Imported HTML action failed.");
      });
    }

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [frameId, navigate, runtime]);

  if (!srcDoc) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-surface-2 p-6 text-sm text-content-muted">
        Imported HTML is empty.
      </div>
    );
  }

  return (
    <div className="w-full space-y-3">
      <div className="overflow-hidden rounded-2xl border border-border bg-surface shadow-sm">
        <iframe
          ref={iframeRef}
          title={title || "Imported HTML document"}
          srcDoc={srcDoc}
          sandbox="allow-scripts allow-forms allow-popups allow-modals allow-downloads"
          className="block w-full border-0 bg-surface"
          style={{ height }}
        />
      </div>
      {actionError ? (
        <div className="rounded-xl border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {actionError}
        </div>
      ) : null}
    </div>
  );
}
