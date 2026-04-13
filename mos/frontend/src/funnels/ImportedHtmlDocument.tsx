import { useEffect, useMemo, useState } from "react";
import type { ImportedHtmlInstrumentationManifest } from "@/types/funnels";
import {
  IMPORTED_HTML_HEIGHT_MESSAGE,
  IMPORTED_HTML_RUNTIME_MESSAGE_SOURCE,
  isImportedHtmlRuntimeMessage,
  normalizeImportedHtmlManifest,
  type ImportedHtmlRuntimeCheckoutMessage,
  type ImportedHtmlRuntimeErrorMessage,
  type ImportedHtmlRuntimeNavigateMessage,
  type ImportedHtmlRuntimeTrackMessage,
} from "@/funnels/importedHtmlRuntime";

const DEFAULT_INITIAL_HEIGHT = 900;
const MAX_FRAME_HEIGHT = 20000;

type ImportedHtmlRuntimeActions = {
  manifest: ImportedHtmlInstrumentationManifest;
  onNavigate: (message: ImportedHtmlRuntimeNavigateMessage) => void;
  onCheckout: (message: ImportedHtmlRuntimeCheckoutMessage) => void;
  onTrack: (message: ImportedHtmlRuntimeTrackMessage) => void;
  onError?: (message: ImportedHtmlRuntimeErrorMessage) => void;
};

function escapeInlineTagContent(value: string): string {
  return value.replace(/<\/(script|style)/gi, "<\\/$1");
}

function injectImportedHtmlRuntimeScript(
  htmlDocument: string,
  frameId: string,
  manifest: ImportedHtmlInstrumentationManifest | null,
): string {
  const runtimeScript = `
<script>
(() => {
  const SOURCE = ${JSON.stringify(IMPORTED_HTML_RUNTIME_MESSAGE_SOURCE)};
  const FRAME_ID = ${JSON.stringify(frameId)};
  const HEIGHT_TYPE = ${JSON.stringify(IMPORTED_HTML_HEIGHT_MESSAGE)};
  const manifest = ${JSON.stringify(manifest)};

  const post = (type, payload = {}) => {
    parent.postMessage({ source: SOURCE, type, frameId: FRAME_ID, ...payload }, "*");
  };

  const normalizedText = (value) =>
    String(value || "")
      .replace(/\\s+/g, " ")
      .trim();

  const measure = () => {
    const body = document.body;
    const doc = document.documentElement;
    const height = Math.max(
      body ? body.scrollHeight : 0,
      body ? body.offsetHeight : 0,
      doc ? doc.scrollHeight : 0,
      doc ? doc.offsetHeight : 0,
      0,
    );
    post(HEIGHT_TYPE, { height });
  };

  const reportError = (message) => {
    post("error", { message: normalizedText(message) || "Imported HTML runtime failed." });
  };

  const readNodeValue = (node, source) => {
    if (!node) return "";
    if (source === "text") {
      return normalizedText(node.textContent || "");
    }
    if (node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement || node instanceof HTMLSelectElement) {
      return normalizedText(node.value || "");
    }
    return normalizedText(node.textContent || "");
  };

  const bindManifest = () => {
    if (!manifest || !Array.isArray(manifest.bindings)) {
      return;
    }
    for (const binding of manifest.bindings) {
      if (!binding || typeof binding !== "object") continue;
      const selector = typeof binding.selector === "string" ? binding.selector : "";
      if (!selector) continue;
      const matches = Array.from(document.querySelectorAll(selector));
      if (matches.length < 1) {
        reportError(
          "Binding '" +
            String(binding.id || "unknown") +
            "' selector '" +
            selector +
            "' matched no elements at runtime.",
        );
        continue;
      }
      for (const element of matches) {
        if (!(element instanceof HTMLElement)) {
          reportError("Binding '" + String(binding.id || "unknown") + "' did not resolve to an HTMLElement.");
          continue;
        }
        if (element.dataset.mosImportedHtmlBound === "true") {
          continue;
        }
        element.dataset.mosImportedHtmlBound = "true";
        element.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          const buttonText = normalizedText(element.textContent || "");
          if (binding.type === "internal_navigation") {
            post("navigate", {
              bindingId: binding.id,
              targetPageId: binding.targetPageId,
              trackEventType: binding.trackEventType,
              buttonText,
            });
            return;
          }
          if (binding.type === "track_only") {
            post("track", {
              bindingId: binding.id,
              trackEventType: binding.trackEventType,
              buttonText,
            });
            return;
          }
          if (binding.type !== "checkout" || !binding.checkout || typeof binding.checkout !== "object") {
            reportError("Binding '" + String(binding.id || "unknown") + "' has unsupported type.");
            return;
          }
          const checkout = binding.checkout;
          let variantId = null;
          let selection = null;
          const resolver = checkout.variantResolver;
          if (!resolver || typeof resolver !== "object" || typeof resolver.type !== "string") {
            reportError("Checkout binding '" + String(binding.id || "unknown") + "' is missing variantResolver.");
            return;
          }
          if (resolver.type === "fixed") {
            variantId = typeof resolver.variantId === "string" ? resolver.variantId : null;
          } else if (resolver.type === "option_values") {
            selection = {};
            const optionSelectors = Array.isArray(resolver.optionSelectors) ? resolver.optionSelectors : [];
            for (const option of optionSelectors) {
              const optionMatches = Array.from(document.querySelectorAll(option.selector || ""));
              if (optionMatches.length !== 1) {
                reportError(
                  "Checkout binding '" +
                    String(binding.id || "unknown") +
                    "' option selector '" +
                    String(option.selector || "") +
                    "' matched " +
                    String(optionMatches.length) +
                    " elements.",
                );
                return;
              }
              const optionNode = optionMatches[0];
              const optionName = normalizedText(option.name || "");
              const optionValue = readNodeValue(optionNode, option.source === "text" ? "text" : "value");
              if (!optionName || !optionValue) {
                reportError(
                  "Checkout binding '" +
                    String(binding.id || "unknown") +
                    "' could not resolve a non-empty option value for '" +
                    String(option.name || "") +
                    "'.",
                );
                return;
              }
              selection[optionName] = optionValue;
            }
          } else {
            reportError("Checkout binding '" + String(binding.id || "unknown") + "' uses an unsupported resolver.");
            return;
          }
          post("checkout", {
            bindingId: binding.id,
            trackEventType: binding.trackEventType,
            checkoutMode: checkout.mode,
            buttonText,
            variantId,
            selection,
            externalUrlsByVariant: Array.isArray(checkout.externalUrlsByVariant) ? checkout.externalUrlsByVariant : null,
          });
        });
      }
    }
  };

  window.addEventListener("load", () => {
    bindManifest();
    measure();
    setTimeout(measure, 50);
    setTimeout(measure, 250);
    setTimeout(measure, 1000);
    if (typeof ResizeObserver === "function") {
      const observer = new ResizeObserver(measure);
      if (document.documentElement) observer.observe(document.documentElement);
      if (document.body) observer.observe(document.body);
    }
    if (typeof MutationObserver === "function" && document.body) {
      const observer = new MutationObserver(measure);
      observer.observe(document.body, {
        attributes: true,
        childList: true,
        subtree: true,
        characterData: true,
      });
    }
  });

  window.addEventListener("resize", measure);
  window.addEventListener("error", (event) => {
    reportError(event.error && event.error.message ? event.error.message : event.message || "Imported HTML runtime error.");
  });
  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason && event.reason.message ? event.reason.message : String(event.reason || "");
    reportError(reason || "Imported HTML runtime rejected.");
  });
})();
</script>`;

  if (/<\/body>/i.test(htmlDocument)) {
    return htmlDocument.replace(/<\/body>/i, `${escapeInlineTagContent(runtimeScript)}</body>`);
  }
  if (/<\/html>/i.test(htmlDocument)) {
    return htmlDocument.replace(/<\/html>/i, `${escapeInlineTagContent(runtimeScript)}</html>`);
  }
  return `${htmlDocument}${escapeInlineTagContent(runtimeScript)}`;
}

export function ImportedHtmlDocument({
  id,
  title,
  htmlDocument,
  instrumentationManifest,
  runtimeActions,
}: {
  id?: string;
  title?: string;
  htmlDocument?: string;
  instrumentationManifest?: ImportedHtmlInstrumentationManifest | Record<string, unknown> | null;
  runtimeActions?: ImportedHtmlRuntimeActions | null;
}) {
  const [height, setHeight] = useState(DEFAULT_INITIAL_HEIGHT);
  const frameId = id || "imported-html-document";
  const manifest = useMemo(
    () => normalizeImportedHtmlManifest(instrumentationManifest ?? null),
    [instrumentationManifest],
  );

  const srcDoc = useMemo(() => {
    const normalizedHtml = typeof htmlDocument === "string" ? htmlDocument.trim() : "";
    if (!normalizedHtml) return "";
    return injectImportedHtmlRuntimeScript(
      normalizedHtml,
      frameId,
      runtimeActions ? runtimeActions.manifest || manifest : null,
    );
  }, [frameId, htmlDocument, manifest, runtimeActions?.manifest]);

  useEffect(() => {
    setHeight(DEFAULT_INITIAL_HEIGHT);
  }, [frameId, srcDoc]);

  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      const payload = event.data;
      if (!isImportedHtmlRuntimeMessage(payload)) return;
      if (payload.frameId !== frameId) return;
      if (payload.type === IMPORTED_HTML_HEIGHT_MESSAGE) {
        const nextHeight = Number(payload.height);
        if (!Number.isFinite(nextHeight) || nextHeight <= 0) return;
        setHeight(Math.min(MAX_FRAME_HEIGHT, Math.ceil(nextHeight)));
        return;
      }
      if (payload.type === "navigate" && runtimeActions) {
        runtimeActions.onNavigate(payload);
        return;
      }
      if (payload.type === "checkout" && runtimeActions) {
        runtimeActions.onCheckout(payload);
        return;
      }
      if (payload.type === "track" && runtimeActions) {
        runtimeActions.onTrack(payload);
        return;
      }
      if (payload.type === "error" && runtimeActions?.onError) {
        runtimeActions.onError(payload);
      }
    }

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [frameId, runtimeActions]);

  if (!srcDoc) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-surface-2 p-6 text-sm text-content-muted">
        Imported HTML is empty.
      </div>
    );
  }

  return (
    <div className="w-full overflow-hidden">
      <iframe
        title={title || "Imported HTML document"}
        srcDoc={srcDoc}
        sandbox="allow-scripts allow-forms allow-popups allow-modals allow-downloads"
        className="block w-full border-0 bg-transparent"
        style={{ height }}
      />
    </div>
  );
}
