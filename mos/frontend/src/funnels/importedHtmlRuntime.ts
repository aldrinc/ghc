import type {
  ImportedHtmlCheckoutConfig,
  ImportedHtmlInstrumentationManifest,
  ImportedHtmlTrackEventType,
} from "@/types/funnels";
import type { PublicCommerceVariant } from "@/types/commerce";

export const IMPORTED_HTML_RUNTIME_MESSAGE_SOURCE = "mos-imported-html-runtime";
export const IMPORTED_HTML_HEIGHT_MESSAGE = "height";

export type ImportedHtmlRuntimeHeightMessage = {
  source: typeof IMPORTED_HTML_RUNTIME_MESSAGE_SOURCE;
  type: typeof IMPORTED_HTML_HEIGHT_MESSAGE;
  frameId: string;
  height: number;
};

export type ImportedHtmlRuntimeErrorMessage = {
  source: typeof IMPORTED_HTML_RUNTIME_MESSAGE_SOURCE;
  type: "error";
  frameId: string;
  message: string;
};

export type ImportedHtmlRuntimeNavigateMessage = {
  source: typeof IMPORTED_HTML_RUNTIME_MESSAGE_SOURCE;
  type: "navigate";
  frameId: string;
  bindingId: string;
  targetPageId: string;
  trackEventType: ImportedHtmlTrackEventType;
  buttonText?: string | null;
};

export type ImportedHtmlRuntimeCheckoutMessage = {
  source: typeof IMPORTED_HTML_RUNTIME_MESSAGE_SOURCE;
  type: "checkout";
  frameId: string;
  bindingId: string;
  trackEventType: ImportedHtmlTrackEventType;
  checkoutMode: ImportedHtmlCheckoutConfig["mode"];
  buttonText?: string | null;
  variantId?: string | null;
  selection?: Record<string, string> | null;
  externalUrlsByVariant?: Array<{ variantId: string; url: string }> | null;
};

export type ImportedHtmlRuntimeTrackMessage = {
  source: typeof IMPORTED_HTML_RUNTIME_MESSAGE_SOURCE;
  type: "track";
  frameId: string;
  bindingId: string;
  trackEventType: ImportedHtmlTrackEventType;
  buttonText?: string | null;
};

export type ImportedHtmlRuntimeMessage =
  | ImportedHtmlRuntimeHeightMessage
  | ImportedHtmlRuntimeErrorMessage
  | ImportedHtmlRuntimeNavigateMessage
  | ImportedHtmlRuntimeCheckoutMessage
  | ImportedHtmlRuntimeTrackMessage;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function isImportedHtmlRuntimeMessage(value: unknown): value is ImportedHtmlRuntimeMessage {
  if (!isRecord(value)) return false;
  return value.source === IMPORTED_HTML_RUNTIME_MESSAGE_SOURCE && typeof value.type === "string";
}

export function normalizeImportedHtmlManifest(
  value: ImportedHtmlInstrumentationManifest | Record<string, unknown> | null | undefined,
): ImportedHtmlInstrumentationManifest | null {
  if (!isRecord(value)) return null;
  if (value.schemaVersion !== "imported-html-instrumentation-v1") return null;
  if (!Array.isArray(value.bindings)) return null;
  return value as ImportedHtmlInstrumentationManifest;
}

export function matchesVariantOptionValues(
  variant: PublicCommerceVariant,
  selection: Record<string, string> | null | undefined,
): boolean {
  if (!selection || !Object.keys(selection).length) {
    return false;
  }
  const optionValues = isRecord(variant.option_values) ? variant.option_values : null;
  if (!optionValues) return false;
  return Object.entries(selection).every(([key, value]) => {
    const candidate = optionValues[key];
    return typeof candidate === "string" && candidate === value;
  });
}

export function resolveExternalCheckoutUrlForVariant(
  externalUrlsByVariant: Array<{ variantId: string; url: string }> | null | undefined,
  variantId: string | null | undefined,
): string | null {
  if (!Array.isArray(externalUrlsByVariant) || !variantId) return null;
  const match = externalUrlsByVariant.find((item) => item.variantId === variantId && typeof item.url === "string");
  return match?.url || null;
}

const IMPORTED_HTML_EAGER_IMAGE_LIMIT = 1;

export function optimizeImportedHtmlDocument(htmlDocument: string | null | undefined): string {
  const normalizedHtml = typeof htmlDocument === "string" ? htmlDocument.trim() : "";
  if (!normalizedHtml) {
    return "";
  }
  if (typeof DOMParser !== "function") {
    return normalizedHtml;
  }

  try {
    const parsedDocument = new DOMParser().parseFromString(normalizedHtml, "text/html");
    const images = Array.from(parsedDocument.querySelectorAll("img"));
    let eagerImagesAssigned = 0;

    for (const image of images) {
      const existingLoading = (image.getAttribute("loading") || "").trim().toLowerCase();
      const existingFetchPriority = (image.getAttribute("fetchpriority") || "").trim().toLowerCase();
      const shouldRemainEager = existingLoading === "eager" || eagerImagesAssigned < IMPORTED_HTML_EAGER_IMAGE_LIMIT;

      if (!existingLoading) {
        image.setAttribute("loading", shouldRemainEager ? "eager" : "lazy");
      }
      if (!image.getAttribute("decoding")) {
        image.setAttribute("decoding", "async");
      }
      if (!existingFetchPriority) {
        image.setAttribute("fetchpriority", shouldRemainEager ? "high" : "low");
      }

      const resolvedLoading = (image.getAttribute("loading") || "").trim().toLowerCase();
      if (resolvedLoading === "eager") {
        eagerImagesAssigned += 1;
      }
    }

    const serializedDocument = parsedDocument.documentElement?.outerHTML?.trim();
    if (!serializedDocument) {
      return normalizedHtml;
    }
    if (/^\s*<!doctype/i.test(normalizedHtml)) {
      return `<!DOCTYPE html>\n${serializedDocument}`;
    }
    return serializedDocument;
  } catch {
    return normalizedHtml;
  }
}
