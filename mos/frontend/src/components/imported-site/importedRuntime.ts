type ImportedRuntimeHeadAssets = {
  scriptSrcs: string[];
  stylesheetHrefs: string[];
  inlineStyles: string[];
  inlineScripts: string[];
  bodyClassName: string;
};

type BuildImportedRuntimeSrcDocParams = {
  frameId: string;
  sectionLabel?: string;
  headAssets?: unknown;
  compiledSource: string;
  reactUmdSource: string;
  reactDomUmdSource: string;
  viewportHeightPx?: number | null;
  componentName?: string;
  sectionTargetId?: string;
  initialTextOverrides?: unknown;
  initialButtonOverrides?: unknown;
  initialImageOverrides?: unknown;
  purchaseRuntimeData?: unknown;
};

type ImportedTextOverride = {
  originalText: string;
  text: string;
};

type ImportedButtonOverride = {
  originalText: string;
  text: string;
  href: string;
  action?: string;
  selectionStrategy?: string;
  replaceCart?: boolean;
};

type ImportedImageOverride = {
  originalSrc: string;
  originalText?: string;
  src: string;
  alt: string;
};

type ImportedPurchaseRuntimeVariant = {
  title: string;
  priceLabel: string;
  compareAtLabel?: string;
};

type ImportedPurchaseRuntimeData = {
  ctaBaseLabel?: string;
  variants: ImportedPurchaseRuntimeVariant[];
  imageUrls?: string[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((entry): entry is string => typeof entry === "string")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function normalizeTextOverrides(value: unknown): ImportedTextOverride[] {
  if (!Array.isArray(value)) return [];
  const results: ImportedTextOverride[] = [];
  for (const entry of value) {
    if (!isRecord(entry)) continue;
    const originalText = typeof entry.originalText === "string" ? entry.originalText.trim() : "";
    if (!originalText) continue;
    const text = Object.prototype.hasOwnProperty.call(entry, "text") && typeof entry.text === "string"
      ? entry.text
      : originalText;
    results.push({ originalText, text });
  }
  return results;
}

function normalizeButtonOverrides(value: unknown): ImportedButtonOverride[] {
  if (!Array.isArray(value)) return [];
  const results: ImportedButtonOverride[] = [];
  for (const entry of value) {
    if (!isRecord(entry)) continue;
    const originalText = typeof entry.originalText === "string" ? entry.originalText.trim() : "";
    if (!originalText) continue;
    const text = Object.prototype.hasOwnProperty.call(entry, "text") && typeof entry.text === "string"
      ? entry.text
      : originalText;
    const href = Object.prototype.hasOwnProperty.call(entry, "href") && typeof entry.href === "string"
      ? entry.href
      : "";
    const action =
      Object.prototype.hasOwnProperty.call(entry, "action") && typeof entry.action === "string"
        ? entry.action.trim()
        : "";
    const selectionStrategy =
      Object.prototype.hasOwnProperty.call(entry, "selectionStrategy") && typeof entry.selectionStrategy === "string"
        ? entry.selectionStrategy.trim()
        : "";
    const replaceCart =
      Object.prototype.hasOwnProperty.call(entry, "replaceCart") && typeof entry.replaceCart === "boolean"
        ? entry.replaceCart
        : false;
    results.push({
      originalText,
      text,
      href,
      action: action || undefined,
      selectionStrategy: selectionStrategy || undefined,
      replaceCart,
    });
  }
  return results;
}

function normalizeImageOverrides(value: unknown): ImportedImageOverride[] {
  if (!Array.isArray(value)) return [];
  const results: ImportedImageOverride[] = [];
  for (const entry of value) {
    if (!isRecord(entry)) continue;
    const originalSrc = typeof entry.originalSrc === "string" ? entry.originalSrc.trim() : "";
    const originalText = typeof entry.originalText === "string" ? entry.originalText.trim() : "";
    if (!originalSrc && !originalText) continue;
    const src = Object.prototype.hasOwnProperty.call(entry, "src") && typeof entry.src === "string"
      ? entry.src
      : originalSrc;
    const alt = Object.prototype.hasOwnProperty.call(entry, "alt") && typeof entry.alt === "string"
      ? entry.alt
      : "";
    results.push({ originalSrc, originalText: originalText || undefined, src, alt });
  }
  return results;
}

function normalizePurchaseRuntimeData(value: unknown): ImportedPurchaseRuntimeData | null {
  if (!isRecord(value)) return null;
  const variantsInput = Array.isArray(value.variants) ? value.variants : [];
  const variants: ImportedPurchaseRuntimeVariant[] = [];
  for (const entry of variantsInput) {
    if (!isRecord(entry)) continue;
    const title = typeof entry.title === "string" ? entry.title.trim() : "";
    const priceLabel = typeof entry.priceLabel === "string" ? entry.priceLabel.trim() : "";
    if (!title || !priceLabel) continue;
    const compareAtLabel = typeof entry.compareAtLabel === "string" ? entry.compareAtLabel.trim() : "";
    variants.push({
      title,
      priceLabel,
      compareAtLabel: compareAtLabel || undefined,
    });
  }
  if (!variants.length) return null;
  const ctaBaseLabel = typeof value.ctaBaseLabel === "string" ? value.ctaBaseLabel.trim() : "";
  const imageUrls = Array.isArray(value.imageUrls)
    ? value.imageUrls.filter((entry): entry is string => typeof entry === "string" && entry.trim().length > 0)
    : [];
  return {
    ctaBaseLabel: ctaBaseLabel || undefined,
    variants,
    imageUrls,
  };
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeInlineTagContent(value: string): string {
  return value.replace(/<\/(script|style)/gi, "<\\/$1");
}

function normalizeViewportHeightPx(value: number | null | undefined): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const rounded = Math.round(value);
  return rounded >= 1 ? rounded : null;
}

function stabilizeViewportCss(value: string, viewportHeightPx: number | null): string {
  if (!viewportHeightPx) return value;
  return value
    .replaceAll("100dvh", "var(--mos-imported-vh)")
    .replaceAll("100svh", "var(--mos-imported-vh)")
    .replaceAll("100lvh", "var(--mos-imported-vh)")
    .replaceAll("100vh", "var(--mos-imported-vh)");
}

export function isImportedRuntimeSectionType(type: unknown): type is string {
  return typeof type === "string" && /^Imported[A-Za-z0-9]+Section$/.test(type) && type !== "ImportedRuntimeSection";
}

export function normalizeImportedHeadAssets(value: unknown): ImportedRuntimeHeadAssets {
  const record = isRecord(value) ? value : {};
  const bodyClassName = typeof record.bodyClassName === "string" ? record.bodyClassName.trim() : "";

  return {
    scriptSrcs: normalizeStringArray(record.scriptSrcs),
    stylesheetHrefs: normalizeStringArray(record.stylesheetHrefs),
    inlineStyles: normalizeStringArray(record.inlineStyles),
    inlineScripts: normalizeStringArray(record.inlineScripts),
    bodyClassName,
  };
}

export function normalizeImportedRuntimeSectionTypes(value: unknown): boolean {
  let changed = false;

  const walk = (node: unknown) => {
    if (Array.isArray(node)) {
      for (const entry of node) walk(entry);
      return;
    }

    if (!isRecord(node)) return;

    if (isImportedRuntimeSectionType(node.type) && isRecord(node.props) && typeof node.props.runtimeSource === "string") {
      node.props.originalType = node.type;
      node.type = "ImportedRuntimeSection";
      changed = true;
    }

    for (const key of Object.keys(node)) walk(node[key]);
  };

  walk(value);
  return changed;
}

export function buildImportedRuntimeSrcDoc({
  frameId,
  sectionLabel,
  headAssets,
  compiledSource,
  reactUmdSource,
  reactDomUmdSource,
  viewportHeightPx,
  componentName,
  sectionTargetId,
  initialTextOverrides,
  initialButtonOverrides,
  initialImageOverrides,
  purchaseRuntimeData,
}: BuildImportedRuntimeSrcDocParams): string {
  const normalizedHeadAssets = normalizeImportedHeadAssets(headAssets);
  const title = escapeHtml(sectionLabel?.trim() || "Imported section");
  const bodyClassName = escapeHtml(normalizedHeadAssets.bodyClassName);
  const compiledRuntime = escapeInlineTagContent(compiledSource);
  const resolvedViewportHeightPx = normalizeViewportHeightPx(viewportHeightPx);
  const resolvedComponentName = typeof componentName === "string" && componentName.trim() ? componentName.trim() : "App";
  const resolvedSectionTargetId = typeof sectionTargetId === "string" ? sectionTargetId.trim() : "";
  const initialTextOverridesJson = JSON.stringify(normalizeTextOverrides(initialTextOverrides));
  const initialButtonOverridesJson = JSON.stringify(normalizeButtonOverrides(initialButtonOverrides));
  const initialImageOverridesJson = JSON.stringify(normalizeImageOverrides(initialImageOverrides));
  const purchaseRuntimeDataJson = JSON.stringify(normalizePurchaseRuntimeData(purchaseRuntimeData));

  const bridgeScript = escapeInlineTagContent(`
(() => {
  const frameId = ${JSON.stringify(frameId)};
  const post = (type, payload = {}) => {
    parent.postMessage({ source: "mos-imported-runtime", frameId, type, ...payload }, "*");
  };
  window.__postImportedRuntimeEvent = post;

  const reportHeight = () => {
    const body = document.body;
    const root = document.documentElement;
    const height = Math.max(
      body ? body.scrollHeight : 0,
      body ? body.offsetHeight : 0,
      root ? root.scrollHeight : 0,
      root ? root.offsetHeight : 0,
      64,
    );
    post("height", { height });
  };

  const reportError = (error) => {
    const message =
      error && typeof error === "object" && "message" in error && typeof error.message === "string"
        ? error.message
        : String(error || "Failed to render imported section.");
    post("error", { message });
  };

  window.__notifyImportedRuntimeHeight = reportHeight;
  window.__reportImportedRuntimeError = reportError;

  window.addEventListener("error", (event) => {
    reportError(event.error || event.message || "Failed to render imported section.");
  });

  window.addEventListener("unhandledrejection", (event) => {
    reportError(event.reason || "Imported section runtime rejected.");
  });

  window.addEventListener("message", (event) => {
    const payload = event.data;
    if (!payload || typeof payload !== "object") return;
    if ((payload.source !== "mos-imported-runtime-host")) return;
    if (payload.frameId !== frameId) return;
    if (payload.type === "request-height") {
      reportHeight();
    }
  });

  window.addEventListener("load", () => {
    reportHeight();

    if (typeof ResizeObserver === "function") {
      const observer = new ResizeObserver(() => reportHeight());
      if (document.body) observer.observe(document.body);
      if (document.documentElement) observer.observe(document.documentElement);
    }

    if (typeof MutationObserver === "function" && document.body) {
      const observer = new MutationObserver(() => reportHeight());
      observer.observe(document.body, {
        attributes: true,
        childList: true,
        subtree: true,
        characterData: true,
      });
    }
  });
})();
  `);

  const stylesheetLinks = normalizedHeadAssets.stylesheetHrefs
    .map((href) => `<link rel="stylesheet" href="${escapeHtml(href)}" />`)
    .join("\n");
  const viewportStyle = resolvedViewportHeightPx
    ? `<style>:root{--mos-imported-vh:${resolvedViewportHeightPx}px;}</style>`
    : "";
  const inlineStyles = normalizedHeadAssets.inlineStyles
    .map((css) => `<style>${escapeInlineTagContent(stabilizeViewportCss(css, resolvedViewportHeightPx))}</style>`)
    .join("\n");
  const externalScripts = normalizedHeadAssets.scriptSrcs
    .map((src) => `<script src="${escapeHtml(src)}"></script>`)
    .join("\n");
  const inlineScripts = normalizedHeadAssets.inlineScripts
    .map((script) => `<script>${escapeInlineTagContent(script)}</script>`)
    .join("\n");

  const runtimeScript = escapeInlineTagContent(`
try {
${compiledRuntime}

  const runtimeFrameId = ${JSON.stringify(frameId)};
  const componentName = ${JSON.stringify(resolvedComponentName)};
  const sectionTargetId = ${JSON.stringify(resolvedSectionTargetId)};
  let textOverrides = ${initialTextOverridesJson};
  let buttonOverrides = ${initialButtonOverridesJson};
  let imageOverrides = ${initialImageOverridesJson};
  const purchaseRuntimeData = ${purchaseRuntimeDataJson};
  const NEWLINE = String.fromCharCode(10);
  const CARRIAGE_RETURN = String.fromCharCode(13);
  const normalizeText = (value) => {
    const input = String(value || "");
    let output = "";
    let lastWhitespace = false;
    for (const char of input) {
      const isWhitespace = char.trim().length === 0;
      if (isWhitespace) {
        if (!lastWhitespace) {
          output += " ";
        }
      } else {
        output += char;
      }
      lastWhitespace = isWhitespace;
    }
    return output.trim();
  };
  const splitOverrideSegments = (value) =>
    String(value ?? "")
      .replaceAll(CARRIAGE_RETURN, "")
      .split(NEWLINE)
      .map((entry) => entry.trim())
      .filter(Boolean);
  const readRawText = (node) => String(node && node.textContent ? node.textContent : "");
  const readNodeText = (node) => {
    if (node == null) return "";
    if (node.nodeType === Node.TEXT_NODE) {
      return String(node.textContent || "");
    }
    if (!(node instanceof Element)) {
      return String(node.textContent || "");
    }
    const tagName = node.tagName.toLowerCase();
    if (tagName === "script" || tagName === "style") return "";
    if (tagName === "br") return " ";
    const parts = [];
    node.childNodes.forEach((childNode) => {
      const text = readNodeText(childNode);
      if (text) parts.push(text);
    });
    return parts.join(" ");
  };
  const readNormalizedNodeText = (node) => normalizeText(readNodeText(node));
  const readRawButtonText = (element) => normalizeText(readRawText(element));
  const readButtonAriaLabel = (element) => {
    if (!(element instanceof Element)) return "";
    return normalizeText(element.getAttribute("aria-label") || element.getAttribute("title") || "");
  };
  const resolveOriginalTextForDisplay = (displayText) => {
    const normalizedDisplayText = normalizeText(displayText);
    if (!normalizedDisplayText || !Array.isArray(textOverrides)) {
      return normalizedDisplayText;
    }
    const matchingOverride = textOverrides.find((override) => {
      const overrideText = normalizeText(typeof override.text === "string" ? override.text : "");
      return overrideText === normalizedDisplayText && typeof override.originalText === "string";
    });
    if (
      matchingOverride &&
      typeof matchingOverride.originalText === "string" &&
      normalizeText(matchingOverride.originalText)
    ) {
      return normalizeText(matchingOverride.originalText);
    }
    return normalizedDisplayText;
  };
  const resolveButtonMatchKind = (element, override) => {
    const currentText = readRawButtonText(element);
    const ariaLabel = readButtonAriaLabel(element);
    const candidateTexts = [
      normalizeText(typeof override.originalText === "string" ? override.originalText : ""),
      normalizeText(typeof override.text === "string" ? override.text : ""),
    ].filter(Boolean);
    for (const candidateText of candidateTexts) {
      if (currentText === candidateText || currentText.startsWith(candidateText)) {
        return "text";
      }
      if (ariaLabel === candidateText || ariaLabel.startsWith(candidateText)) {
        return "accessibility";
      }
    }
    return null;
  };
  const buildOverrideButtonText = (element, override) => {
    const originalText = String(override.originalText || "");
    const nextText = typeof override.text === "string" ? override.text : originalText;
      const currentText = String(element.textContent || "");
    const trimmedCurrentText = currentText.trim();
    const trimmedOriginalText = originalText.trim();
    if (
      trimmedOriginalText &&
      trimmedCurrentText &&
      trimmedCurrentText !== trimmedOriginalText &&
      trimmedCurrentText.toUpperCase().startsWith(trimmedOriginalText.toUpperCase())
    ) {
      return nextText + trimmedCurrentText.slice(trimmedOriginalText.length);
    }
    return nextText;
  };
  const applyMatchedButtonText = (element, override, matchKind) => {
    const originalText = String(override.originalText || "");
    const nextText = typeof override.text === "string" ? override.text : originalText;
    if (matchKind === "text") {
      element.textContent = buildOverrideButtonText(element, override);
      return;
    }
    if (element.hasAttribute("aria-label")) {
      element.setAttribute("aria-label", nextText);
    }
    if (element.hasAttribute("title")) {
      element.setAttribute("title", nextText);
    }
  };
  const postCommerceAction = (payload) => {
    const postEvent =
      typeof window.__postImportedRuntimeEvent === "function"
        ? window.__postImportedRuntimeEvent
        : (type, detail) => parent.postMessage({ source: "mos-imported-runtime", frameId: runtimeFrameId, type, ...detail }, "*");
    postEvent("commerce-action", payload);
  };
  const postNavigationAction = (payload) => {
    const postEvent =
      typeof window.__postImportedRuntimeEvent === "function"
        ? window.__postImportedRuntimeEvent
        : (type, detail) => parent.postMessage({ source: "mos-imported-runtime", frameId: runtimeFrameId, type, ...detail }, "*");
    postEvent("navigate", payload);
  };
  const wireNavigationAction = (element, override) => {
    if (!(element instanceof HTMLElement)) return;
    const href = typeof override.href === "string" ? override.href.trim() : "";
    if (!href) return;
    if (element.dataset.mosImportedNavigationBound === "true") return;
    element.dataset.mosImportedNavigationBound = "true";
    element.dataset.mosImportedNavigationHref = href;
    element.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      postNavigationAction({
        href,
        buttonText: readRawButtonText(element),
      });
    });
  };
  const resolveButtonSelection = (scope, strategy) => {
    if (!(scope instanceof Element)) return null;
    if (strategy !== "omni_selected_tier") return null;

    const tierCard = Array.from(scope.querySelectorAll("*")).find((candidate) => {
      if (!(candidate instanceof HTMLElement)) return false;
      if (!candidate.classList.contains("border-primary") || !candidate.classList.contains("bg-bg-card")) {
        return false;
      }
      return candidate.querySelector("h3") instanceof HTMLElement;
    });

    if (!(tierCard instanceof HTMLElement)) return null;
    const titleElement = tierCard.querySelector("h3");
    const selectedOfferTitle = normalizeText(titleElement ? titleElement.textContent : "");
    if (!selectedOfferTitle) return null;
    return resolveOriginalTextForDisplay(selectedOfferTitle);
  };
  const wireCommerceAction = (scope, element, override) => {
    if (!(element instanceof HTMLElement)) return;
    const action = typeof override.action === "string" ? override.action.trim() : "";
    if (!action) return;
    if (element.dataset.mosImportedActionBound === "true") return;
    element.dataset.mosImportedActionBound = "true";
    element.dataset.mosImportedAction = action;
    if (typeof override.selectionStrategy === "string" && override.selectionStrategy.trim()) {
      element.dataset.mosImportedSelectionStrategy = override.selectionStrategy.trim();
    }
    element.dataset.mosImportedReplaceCart = override.replaceCart ? "true" : "false";
    element.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const selectionStrategy = typeof override.selectionStrategy === "string" ? override.selectionStrategy.trim() : "";
      const selectedOfferTitle = resolveButtonSelection(scope, selectionStrategy);
      postCommerceAction({
        action,
        selectionStrategy: selectionStrategy || null,
        replaceCart: Boolean(override.replaceCart),
        selectedOfferTitle,
        buttonText: readRawButtonText(element),
      });
    });
  };
  const appendFooterNavigationLinks = (scope, unmatchedOverrides) => {
    if (!(scope instanceof Element)) return;
    if (componentName !== "GlobalFooter" || !Array.isArray(unmatchedOverrides) || !unmatchedOverrides.length) {
      return;
    }

    const existingLinks = Array.from(scope.querySelectorAll("a[href]"));
    const navContainer =
      existingLinks.find((candidate) => candidate.getAttribute("href") === "policies/contact-support")?.parentElement ||
      existingLinks.find((candidate) => candidate.getAttribute("href") === "account")?.parentElement ||
      null;
    if (!(navContainer instanceof HTMLElement)) {
      return;
    }

    const templateLink = existingLinks.find((candidate) => candidate.parentElement === navContainer) || null;
    const insertionAnchor =
      Array.from(navContainer.querySelectorAll("a")).find((candidate) => {
        const href = candidate.getAttribute("href") || "";
        return href === "#product-purchase-section" || href === "account";
      }) || null;
    for (const override of unmatchedOverrides) {
      const href = typeof override.href === "string" ? override.href.trim() : "";
      const text = typeof override.text === "string" ? override.text.trim() : "";
      if (!href || !text || typeof override.action === "string" || !href.startsWith("policies/")) {
        continue;
      }
      const existing = Array.from(navContainer.querySelectorAll("a")).find(
        (candidate) => normalizeText(candidate.getAttribute("href") || "") === normalizeText(href),
      );
      if (existing) {
        continue;
      }
      const link = document.createElement("a");
      link.href = href;
      link.textContent = text;
      if (templateLink instanceof HTMLElement) {
        link.className = templateLink.className;
      }
      if (insertionAnchor instanceof HTMLElement) {
        navContainer.insertBefore(link, insertionAnchor);
      } else {
        navContainer.appendChild(link);
      }
      wireNavigationAction(link, override);
    }
  };
  const findSelectedPurchaseCard = (scope) => {
    if (!(scope instanceof Element)) return null;
    return (
      Array.from(scope.querySelectorAll("*")).find((candidate) => {
        if (!(candidate instanceof HTMLElement)) return false;
        if (!candidate.classList.contains("border-primary") || !candidate.classList.contains("bg-bg-card")) {
          return false;
        }
        return candidate.querySelector("h3") instanceof HTMLElement;
      }) || null
    );
  };
  const findPurchaseVariantByTitle = (displayTitle) => {
    if (!purchaseRuntimeData || !Array.isArray(purchaseRuntimeData.variants)) {
      return null;
    }
    const normalizedOriginalTitle = resolveOriginalTextForDisplay(displayTitle);
    return (
      purchaseRuntimeData.variants.find(
        (variant) => normalizeText(variant.title) === normalizedOriginalTitle,
      ) || null
    );
  };
  const renderPurchasePriceColumn = (container, variant) => {
    if (!(container instanceof HTMLElement) || !variant) return;
    container.replaceChildren();
    if (variant.compareAtLabel) {
      const compareAt = document.createElement("div");
      compareAt.className = "text-[14px] text-text-dark/40 line-through font-medium mb-1";
      compareAt.textContent = variant.compareAtLabel;
      container.appendChild(compareAt);
    }
    const price = document.createElement("div");
    price.className = "text-[20px] font-bold text-text-dark leading-none";
    price.textContent = variant.priceLabel;
    container.appendChild(price);
  };
  const syncPurchaseImages = (scope) => {
    if (
      !(scope instanceof Element) ||
      !purchaseRuntimeData ||
      !Array.isArray(purchaseRuntimeData.imageUrls) ||
      !purchaseRuntimeData.imageUrls.length
    ) {
      return;
    }
    const images = Array.from(scope.querySelectorAll("img"));
    if (!images.length) {
      return;
    }
    const fallbackImageUrl = purchaseRuntimeData.imageUrls[0];
    images.forEach((image, index) => {
      const nextImageUrl = purchaseRuntimeData.imageUrls[index] || fallbackImageUrl;
      if (!nextImageUrl) {
        return;
      }
      image.setAttribute("src", nextImageUrl);
    });
  };
  const syncPurchaseRuntime = (scope) => {
    if (!(scope instanceof Element) || componentName !== "ProductPurchaseSection" || !purchaseRuntimeData) {
      return;
    }

    const titleElements = Array.from(scope.querySelectorAll("h3"));
    for (const titleElement of titleElements) {
      const displayTitle = normalizeText(titleElement.textContent || "");
      const variant = findPurchaseVariantByTitle(displayTitle);
      if (!variant) {
        continue;
      }
      const card = titleElement.closest('[class*="cursor-pointer"]');
      if (!(card instanceof HTMLElement)) {
        continue;
      }
      const priceColumn = card.lastElementChild;
      if (priceColumn instanceof HTMLElement) {
        renderPurchasePriceColumn(priceColumn, variant);
      }
    }

    const selectedCard = findSelectedPurchaseCard(scope);
    const selectedTitle = normalizeText(selectedCard?.querySelector("h3")?.textContent || "");
    const selectedVariant = findPurchaseVariantByTitle(selectedTitle) || purchaseRuntimeData.variants[0] || null;
    const ctaButton = Array.from(scope.querySelectorAll("button, a")).find((candidate) => {
      if (!(candidate instanceof HTMLElement)) return false;
      return candidate.dataset.mosImportedAction === "medusa_buy_now";
    });
    if (ctaButton instanceof HTMLElement && selectedVariant) {
      const ctaBaseLabel = String(purchaseRuntimeData.ctaBaseLabel || "").trim();
      ctaButton.textContent = [ctaBaseLabel, selectedVariant.priceLabel].filter(Boolean).join(" ").trim();
    }
    syncPurchaseImages(scope);
  };
  const bindPurchaseRuntime = (scope) => {
    if (!(scope instanceof HTMLElement) || componentName !== "ProductPurchaseSection" || !purchaseRuntimeData) {
      return;
    }
    if (scope.dataset.mosImportedPurchaseRuntimeBound !== "true") {
      scope.dataset.mosImportedPurchaseRuntimeBound = "true";
      scope.addEventListener("click", () => {
        const run = () => syncPurchaseRuntime(scope);
        if (typeof queueMicrotask === "function") {
          queueMicrotask(run);
        } else {
          requestAnimationFrame(run);
        }
      });
    }
    syncPurchaseRuntime(scope);
  };
  const componentRegistry =
    globalThis.__mosImportedRuntimeComponents &&
    typeof globalThis.__mosImportedRuntimeComponents === "object"
      ? globalThis.__mosImportedRuntimeComponents
      : {};
  const rootComponent =
    typeof componentRegistry[componentName] === "function"
      ? componentRegistry[componentName]
      : typeof ImportedSection === "function"
        ? ImportedSection
        : null;

  if (typeof rootComponent !== "function") {
    throw new Error("Imported section runtime did not expose the requested component.");
  }

  const container = document.getElementById("root");
  if (!container) {
    throw new Error("Imported section root container is missing.");
  }

  let mountNode = null;
  let root = null;

  const createFreshRoot = () => {
    if (root && typeof root.unmount === "function") {
      try {
        root.unmount();
      } catch (_error) {
        // Ignore teardown failures and rebuild the runtime tree from scratch.
      }
    }
    container.replaceChildren();
    mountNode = document.createElement("div");
    mountNode.setAttribute("data-mos-imported-runtime-mount", "true");
    container.appendChild(mountNode);
    root = ReactDOM.createRoot(mountNode);
    return root;
  };

  const isolateSection = () => {
    if (!sectionTargetId) return container;
    const target = Array.from(container.querySelectorAll("[data-section-id]")).find(
      (candidate) => candidate.getAttribute("data-section-id") === sectionTargetId,
    );
    if (!(target instanceof HTMLElement)) {
      throw new Error('Imported section target "' + sectionTargetId + '" was not found in the rendered runtime.');
    }
    Array.from(container.querySelectorAll("[data-section-id]")).forEach((candidate) => {
      if (!(candidate instanceof HTMLElement) || candidate === target) {
        return;
      }
      candidate.hidden = true;
      candidate.style.setProperty("display", "none", "important");
    });
    target.hidden = false;
    target.style.removeProperty("display");
    return target;
  };

  const applyTextOverrides = (scope) => {
    if (!scope || !textOverrides.length || typeof document.createTreeWalker !== "function") return;
    const overrideModeByText = new Map();
    for (const override of textOverrides) {
      const originalText = normalizeText(override.originalText);
      if (!originalText) continue;
      const nextText = typeof override.text === "string" ? override.text : override.originalText;
      const current = overrideModeByText.get(originalText) || { count: 0, values: new Set() };
      current.count += 1;
      current.values.add(nextText);
      overrideModeByText.set(originalText, current);
    }
    const textNodes = [];
    const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (!(node instanceof Text)) return NodeFilter.FILTER_REJECT;
        const parent = node.parentElement;
        if (!parent) return NodeFilter.FILTER_REJECT;
        const tagName = parent.tagName.toLowerCase();
        if (tagName === "script" || tagName === "style") return NodeFilter.FILTER_REJECT;
        return normalizeText(node.textContent).length ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      },
    });
    let currentNode = walker.nextNode();
    while (currentNode) {
      textNodes.push(currentNode);
      currentNode = walker.nextNode();
    }
    const used = new Set();
    for (const override of textOverrides) {
      const originalText = normalizeText(override.originalText);
      if (!originalText) continue;
      const nextText = typeof override.text === "string" ? override.text : override.originalText;
      const overrideMode = overrideModeByText.get(originalText);
      const replaceAllMatches = Boolean(overrideMode) && overrideMode.values.size === 1;
      let matched = false;
      const matchedNodeIndexes = [];
      for (let index = 0; index < textNodes.length; index += 1) {
        if (used.has(index)) continue;
        const node = textNodes[index];
        if (normalizeText(node.textContent) !== originalText) continue;
        matchedNodeIndexes.push(index);
        if (!replaceAllMatches) break;
      }
      if (matchedNodeIndexes.length) {
        for (const index of matchedNodeIndexes) {
          const node = textNodes[index];
          node.textContent = nextText;
          used.add(index);
        }
        matched = true;
      }
      if (matched || !(scope instanceof Element)) continue;

      const elementDepth = (element) => {
        let depth = 0;
        let current = element.parentElement;
        while (current) {
          depth += 1;
          current = current.parentElement;
        }
        return depth;
      };

      const allElements = [scope, ...Array.from(scope.querySelectorAll("*"))];
      const matchingElements = allElements
        .filter((element) => readNormalizedNodeText(element) === originalText)
        .filter(
          (element) =>
            !Array.from(element.querySelectorAll("*")).some(
              (child) => readNormalizedNodeText(child) === originalText,
            ),
        )
        .sort((left, right) => {
          const leftDepth = elementDepth(left);
          const rightDepth = elementDepth(right);
          return rightDepth - leftDepth;
        });

      const targets = replaceAllMatches ? matchingElements : matchingElements.slice(0, 1);
      for (const target of targets) {
        if (!(target instanceof HTMLElement)) continue;

        const slots = [];
        target.childNodes.forEach((node) => {
          if (node.nodeType === Node.TEXT_NODE && normalizeText(node.textContent)) {
            slots.push(node);
            return;
          }
          if (node instanceof HTMLElement && node.tagName.toLowerCase() !== "br" && readNormalizedNodeText(node)) {
            slots.push(node);
          }
        });

        const segments = splitOverrideSegments(nextText);

        if (segments.length > 1 && slots.length === segments.length) {
          slots.forEach((slot, slotIndex) => {
            const segment = segments[slotIndex] || "";
            slot.textContent = segment;
          });
        } else {
          target.textContent = nextText;
        }
      }
    }
  };

  const applyButtonOverrides = (scope) => {
    if (!(scope instanceof Element) || !buttonOverrides.length) return;
    const actions = Array.from(scope.querySelectorAll("a, button"));
    const used = new Set();
    const unmatchedOverrides = [];
    for (const override of buttonOverrides) {
      const originalText = normalizeText(override.originalText);
      if (!originalText) continue;
      let matched = false;
      for (let index = 0; index < actions.length; index += 1) {
        if (used.has(index)) continue;
        const element = actions[index];
        const matchKind = resolveButtonMatchKind(element, override);
        if (!matchKind) continue;
        applyMatchedButtonText(element, override, matchKind);
        if (element instanceof HTMLAnchorElement && typeof override.href === "string") {
          if (override.href) {
            element.setAttribute("href", override.href);
          } else {
            element.removeAttribute("href");
          }
        }
        wireCommerceAction(scope, element, override);
        wireNavigationAction(element, override);
        used.add(index);
        matched = true;
        break;
      }
      if (!matched) {
        unmatchedOverrides.push(override);
      }
    }
    appendFooterNavigationLinks(scope, unmatchedOverrides);
  };

  const applyImageOverrides = (scope) => {
    if (!(scope instanceof Element) || !imageOverrides.length) return;
    const images = Array.from(scope.querySelectorAll("img"));
    const used = new Set();
    for (const override of imageOverrides) {
      const originalSrc = typeof override.originalSrc === "string" ? override.originalSrc.trim() : "";
      const originalText = typeof override.originalText === "string" ? normalizeText(override.originalText) : "";
      if (!originalSrc && !originalText) continue;
      if (!override.src) continue;
      for (let index = 0; index < images.length; index += 1) {
        if (used.has(index)) continue;
        const image = images[index];
        const currentSrc = image.getAttribute("src") || "";
        if (
          currentSrc !== originalSrc &&
          !currentSrc.endsWith(originalSrc) &&
          !currentSrc.includes(originalSrc)
        ) {
          continue;
        }
        const nextSrc = typeof override.src === "string" ? override.src : originalSrc;
        if (nextSrc) {
          image.setAttribute("src", nextSrc);
        } else {
          image.removeAttribute("src");
        }
        if (typeof override.alt === "string") {
          image.setAttribute("alt", override.alt);
        }
        used.add(index);
        break;
      }

      if (!originalText) continue;

      const elementDepth = (element) => {
        let depth = 0;
        let current = element.parentElement;
        while (current) {
          depth += 1;
          current = current.parentElement;
        }
        return depth;
      };

      const allElements = [scope, ...Array.from(scope.querySelectorAll("*"))];
      const matchingElements = allElements
        .filter((element) => readNormalizedNodeText(element) === originalText)
        .filter(
          (element) =>
            !Array.from(element.querySelectorAll("*")).some(
              (child) => readNormalizedNodeText(child) === originalText,
            ),
        )
        .sort((left, right) => {
          const leftDepth = elementDepth(left);
          const rightDepth = elementDepth(right);
          return rightDepth - leftDepth;
        });

      const target = matchingElements[0];
      if (!(target instanceof HTMLElement)) continue;

      const replacementImage = document.createElement("img");
      replacementImage.src = override.src;
      replacementImage.alt = typeof override.alt === "string" ? override.alt : "";
      replacementImage.style.display = "block";
      replacementImage.style.maxWidth = "100%";
      replacementImage.style.maxHeight = "48px";
      replacementImage.style.width = "auto";
      replacementImage.style.objectFit = "contain";
      replacementImage.setAttribute("data-mos-imported-replacement-image", "true");
      target.replaceChildren(replacementImage);
    }
  };

  const finalizeSection = () => {
    const sectionRoot = isolateSection();
    applyTextOverrides(sectionRoot);
    applyButtonOverrides(sectionRoot);
    applyImageOverrides(sectionRoot);
    bindPurchaseRuntime(sectionRoot);
  };

  const renderAndFinalizeSection = () => {
    const currentRoot = createFreshRoot();
    const renderRoot = () => currentRoot.render(React.createElement(rootComponent));
    if (typeof ReactDOM.flushSync === "function") {
      ReactDOM.flushSync(renderRoot);
    } else {
      renderRoot();
    }

    const finalize = () => {
      finalizeSection();
      if (typeof window.__notifyImportedRuntimeHeight === "function") {
        window.__notifyImportedRuntimeHeight();
      }
    };

    if (typeof queueMicrotask === "function") {
      queueMicrotask(finalize);
    } else {
      requestAnimationFrame(finalize);
    }
  };

  window.addEventListener("message", (event) => {
    const payload = event.data;
    if (!payload || typeof payload !== "object") return;
    if ((payload.source !== "mos-imported-runtime-host")) return;
    if (payload.frameId !== runtimeFrameId) return;
    if (payload.type !== "update-overrides") return;

    textOverrides = Array.isArray(payload.textOverrides) ? payload.textOverrides : textOverrides;
    buttonOverrides = Array.isArray(payload.buttonOverrides) ? payload.buttonOverrides : buttonOverrides;
    imageOverrides = Array.isArray(payload.imageOverrides) ? payload.imageOverrides : imageOverrides;
    renderAndFinalizeSection();
  });

  renderAndFinalizeSection();
} catch (error) {
  if (typeof window.__reportImportedRuntimeError === "function") {
    window.__reportImportedRuntimeError(error);
  } else {
    throw error;
  }
}
  `);

  return [
    "<!doctype html>",
    "<html>",
    "<head>",
    '<meta charset="utf-8" />',
    '<meta name="viewport" content="width=device-width, initial-scale=1" />',
    `<title>${title}</title>`,
    "<style>html,body{margin:0;padding:0;background:transparent;}body{min-height:1px;}#root{width:100%;}</style>",
    viewportStyle,
    stylesheetLinks,
    inlineStyles,
    `<script>${bridgeScript}</script>`,
    externalScripts,
    inlineScripts,
    "</head>",
    `<body${bodyClassName ? ` class="${bodyClassName}"` : ""}>`,
    '<div id="root"></div>',
    `<script>${escapeInlineTagContent(reactUmdSource)}</script>`,
    `<script>${escapeInlineTagContent(reactDomUmdSource)}</script>`,
    `<script>${runtimeScript}</script>`,
    "</body>",
    "</html>",
  ]
    .filter(Boolean)
    .join("\n");
}
