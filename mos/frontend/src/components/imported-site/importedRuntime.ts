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
  src: string;
  alt: string;
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
    if (!originalSrc) continue;
    const src = Object.prototype.hasOwnProperty.call(entry, "src") && typeof entry.src === "string"
      ? entry.src
      : originalSrc;
    const alt = Object.prototype.hasOwnProperty.call(entry, "alt") && typeof entry.alt === "string"
      ? entry.alt
      : "";
    results.push({ originalSrc, src, alt });
  }
  return results;
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
  const matchesButtonText = (element, originalText) => {
    const currentText = readRawButtonText(element);
    const targetText = normalizeText(originalText);
    if (!targetText) return false;
    return currentText === targetText || currentText.startsWith(targetText);
  };
  const buildOverrideButtonText = (element, override) => {
    const originalText = String(override.originalText || "");
    const nextText = typeof override.text === "string" ? override.text : originalText;
    if (typeof override.action === "string" && override.action.trim() === "medusa_buy_now") {
      return nextText.replace(/\s*-\s*$/, "").trim();
    }
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
  const postCommerceAction = (payload) => {
    const postEvent =
      typeof window.__postImportedRuntimeEvent === "function"
        ? window.__postImportedRuntimeEvent
        : (type, detail) => parent.postMessage({ source: "mos-imported-runtime", frameId: runtimeFrameId, type, ...detail }, "*");
    postEvent("commerce-action", payload);
  };
  const postHashNavigation = (hash) => {
    const normalizedHash = String(hash || "").trim();
    if (!normalizedHash) return;
    const postEvent =
      typeof window.__postImportedRuntimeEvent === "function"
        ? window.__postImportedRuntimeEvent
        : (type, detail) => parent.postMessage({ source: "mos-imported-runtime", frameId: runtimeFrameId, type, ...detail }, "*");
    postEvent("navigate-hash", { hash: normalizedHash });
  };
  const readMoneyTokens = (value) => {
    const matches = String(value || "").match(/[$€£]\s?\d+(?:[.,]\d+)?/g);
    return Array.isArray(matches) ? matches.map((entry) => entry.trim()) : [];
  };
  const readTierCards = (scope) => {
    if (!(scope instanceof Element)) return [];
    return Array.from(scope.querySelectorAll("*")).filter((candidate) => {
      if (!(candidate instanceof HTMLElement)) return false;
      if (!candidate.classList.contains("cursor-pointer")) return false;
      const titleElement = candidate.querySelector("h3");
      if (!(titleElement instanceof HTMLElement)) return false;
      return /pouch/i.test(normalizeText(titleElement.textContent));
    });
  };
  const readSelectedTierCard = (scope) => {
    if (!(scope instanceof Element)) return null;
    const tierCards = readTierCards(scope);
    if (!tierCards.length) {
      const fallbackCard = Array.from(scope.querySelectorAll("*")).find((candidate) => {
        if (!(candidate instanceof HTMLElement)) return false;
        if (!candidate.classList.contains("border-primary") || !candidate.classList.contains("bg-bg-card")) {
          return false;
        }
        return candidate.querySelector("h3") instanceof HTMLElement;
      });
      return fallbackCard instanceof HTMLElement ? fallbackCard : null;
    }
    const explicitSelected = tierCards.find((candidate) => candidate.dataset.mosImportedSelectedTier === "true");
    if (explicitSelected) return explicitSelected;
    const classSelected = tierCards.find(
      (candidate) => candidate.classList.contains("border-primary") && candidate.classList.contains("bg-bg-card"),
    );
    return classSelected || tierCards[0] || null;
  };
  const readTierCardPrice = (tierCard) => {
    if (!(tierCard instanceof HTMLElement)) return null;
    const moneyTokens = readMoneyTokens(tierCard.textContent || "");
    if (!moneyTokens.length) return null;
    return moneyTokens.length >= 2 ? moneyTokens[moneyTokens.length - 2] : moneyTokens[moneyTokens.length - 1];
  };
  const readSelectedTierPrice = (scope) => {
    const selectedTierCard = readSelectedTierCard(scope);
    return readTierCardPrice(selectedTierCard);
  };
  const setTierCardSelected = (card, selected) => {
    if (!(card instanceof HTMLElement)) return;
    card.dataset.mosImportedSelectedTier = selected ? "true" : "false";
    card.classList.toggle("border-primary", selected);
    card.classList.toggle("bg-bg-card", selected);
    card.classList.toggle("border-black/10", !selected);
    card.classList.toggle("bg-white", !selected);

    const indicator = Array.from(card.querySelectorAll("div")).find((candidate) => {
      return candidate instanceof HTMLElement && candidate.classList.contains("rounded-circle") && candidate.classList.contains("border-2");
    });
    if (indicator instanceof HTMLElement) {
      indicator.classList.toggle("border-primary", selected);
      indicator.classList.toggle("border-black/20", !selected);
      let dot = Array.from(indicator.children).find((child) => child instanceof HTMLElement && child.classList.contains("rounded-circle"));
      if (selected) {
        if (!(dot instanceof HTMLElement)) {
          dot = document.createElement("div");
          dot.className = "w-3 h-3 rounded-circle bg-primary";
          indicator.appendChild(dot);
        }
      } else if (dot instanceof HTMLElement) {
        dot.remove();
      }
    }
  };
  const syncBuyNowButtonText = (scope) => {
    if (!(scope instanceof Element)) return;
    const buyButton = scope.querySelector('[data-mos-imported-action="medusa_buy_now"]');
    if (!(buyButton instanceof HTMLElement)) return;
    const prefix = String(buyButton.dataset.mosImportedLabelPrefix || readRawButtonText(buyButton) || "BUY NOW").replace(/\s*-\s*$/, "").trim();
    const price = readSelectedTierPrice(scope);
    if (price) {
      buyButton.dataset.mosImportedSelectedPrice = price;
    }
    buyButton.textContent = prefix;
  };
  const readFlavorButtons = (scope) => {
    if (!(scope instanceof Element)) return [];
    const flavorLabel = Array.from(scope.querySelectorAll("*")).find((candidate) => {
      return candidate instanceof HTMLElement && normalizeText(candidate.textContent) === "Choose Flavor:";
    });
    if (!(flavorLabel instanceof HTMLElement) || !(flavorLabel.nextElementSibling instanceof HTMLElement)) return [];
    return Array.from(flavorLabel.nextElementSibling.querySelectorAll("button")).filter((candidate) => {
      return normalizeText(candidate.textContent).length > 0;
    });
  };
  const setFlavorButtonSelected = (button, selected) => {
    if (!(button instanceof HTMLElement)) return;
    button.dataset.mosImportedSelectedFlavor = selected ? "true" : "false";
    button.classList.toggle("border-primary", selected);
    button.classList.toggle("bg-bg-card", selected);
    button.classList.toggle("text-primary", selected);
    button.classList.toggle("shadow-sm", selected);
    button.classList.toggle("border-black/10", !selected);
    button.classList.toggle("bg-white", !selected);
    button.classList.toggle("text-text-dark/70", !selected);
    button.classList.toggle("hover:border-black/20", !selected);
  };
  const enhanceOmniPurchaseSelection = (scope) => {
    if (!(scope instanceof Element)) return;
    const buyButton = scope.querySelector('[data-mos-imported-action="medusa_buy_now"]');
    if (!(buyButton instanceof HTMLElement)) return;

    const tierCards = readTierCards(scope);
    if (tierCards.length) {
      const applySelectedTierPrice = () => {
        const selectedPrice = readSelectedTierPrice(scope);
        const prefix = String(buyButton.dataset.mosImportedLabelPrefix || readRawButtonText(buyButton) || "BUY NOW").replace(/\s*-\s*$/, "").trim();
        if (selectedPrice) {
          buyButton.dataset.mosImportedSelectedPrice = selectedPrice;
        }
        buyButton.textContent = prefix;
      };
      const selectedCard = readSelectedTierCard(scope);
      tierCards.forEach((candidate) => setTierCardSelected(candidate, candidate === selectedCard));
      tierCards.forEach((candidate) => {
        if (candidate.dataset.mosImportedTierBound === "true") return;
        candidate.dataset.mosImportedTierBound = "true";
        candidate.tabIndex = 0;
        candidate.setAttribute("role", "button");
        candidate.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          if (typeof event.stopImmediatePropagation === "function") {
            event.stopImmediatePropagation();
          }
          tierCards.forEach((entry) => setTierCardSelected(entry, entry === candidate));
          applySelectedTierPrice();
          if (typeof queueMicrotask === "function") {
            queueMicrotask(applySelectedTierPrice);
          } else {
            setTimeout(applySelectedTierPrice, 0);
          }
          setTimeout(applySelectedTierPrice, 32);
          if (typeof window.__notifyImportedRuntimeHeight === "function") {
            window.__notifyImportedRuntimeHeight();
          }
        }, true);
        candidate.addEventListener("keydown", (event) => {
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault();
          candidate.click();
        });
      });
      if (typeof MutationObserver === "function" && scope instanceof HTMLElement && scope.dataset.mosImportedTierObserverBound !== "true") {
        scope.dataset.mosImportedTierObserverBound = "true";
        const observer = new MutationObserver(() => applySelectedTierPrice());
        tierCards.forEach((candidate) => {
          observer.observe(candidate, {
            attributes: true,
            attributeFilter: ["data-mos-imported-selected-tier"],
          });
        });
      }
      applySelectedTierPrice();
    }

    const flavorButtons = readFlavorButtons(scope);
    if (flavorButtons.length) {
      const selectedFlavor = flavorButtons.find((candidate) => candidate.classList.contains("border-primary")) || flavorButtons[0];
      flavorButtons.forEach((candidate) => setFlavorButtonSelected(candidate, candidate === selectedFlavor));
      flavorButtons.forEach((candidate) => {
        if (candidate.dataset.mosImportedFlavorBound === "true") return;
        candidate.dataset.mosImportedFlavorBound = "true";
        candidate.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          if (typeof event.stopImmediatePropagation === "function") {
            event.stopImmediatePropagation();
          }
          flavorButtons.forEach((entry) => setFlavorButtonSelected(entry, entry === candidate));
          if (typeof window.__notifyImportedRuntimeHeight === "function") {
            window.__notifyImportedRuntimeHeight();
          }
        }, true);
      });
    }

    syncBuyNowButtonText(scope);
  };
  const resolveImplicitTargetHash = (override) => {
    const href = typeof override.href === "string" ? override.href.trim() : "";
    if (href.startsWith("#")) return href;
    const label = normalizeText(typeof override.text === "string" ? override.text : override.originalText).toUpperCase();
    if (!label) return "";
    if (
      label.includes("TRY OMNI") ||
      label.includes("SHOP OMNI") ||
      label === "SHOP NOW" ||
      label === "GET STARTED"
    ) {
      return "#shop";
    }
    return "";
  };
  const wireHashNavigation = (element, targetHash) => {
    if (!(element instanceof HTMLElement)) return;
    const normalizedHash = String(targetHash || "").trim();
    if (!normalizedHash || !normalizedHash.startsWith("#")) return;
    if (element.dataset.mosImportedHashBound === "true") return;
    element.dataset.mosImportedHashBound = "true";
    element.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (typeof event.stopImmediatePropagation === "function") {
        event.stopImmediatePropagation();
      }
      postHashNavigation(normalizedHash);
    }, true);
  };
  const resolveButtonSelection = (scope, strategy) => {
    if (!(scope instanceof Element)) return null;
    if (strategy !== "omni_selected_tier") return null;

    const tierCard = readSelectedTierCard(scope);

    if (!(tierCard instanceof HTMLElement)) return null;
    const titleElement = tierCard.querySelector("h3");
    const selectedOfferTitle = normalizeText(titleElement ? titleElement.textContent : "");
    return selectedOfferTitle || null;
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
      if (typeof event.stopImmediatePropagation === "function") {
        event.stopImmediatePropagation();
      }
      const selectionStrategy = typeof override.selectionStrategy === "string" ? override.selectionStrategy.trim() : "";
      const selectedOfferTitle = resolveButtonSelection(scope, selectionStrategy);
      postCommerceAction({
        action,
        selectionStrategy: selectionStrategy || null,
        replaceCart: Boolean(override.replaceCart),
        selectedOfferTitle,
        buttonText: readRawButtonText(element),
      });
    }, true);
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
    const isolatedTarget = target.cloneNode(true);
    if (!(isolatedTarget instanceof HTMLElement)) {
      throw new Error('Imported section target "' + sectionTargetId + '" could not be isolated.');
    }
    container.replaceChildren(isolatedTarget);
    return isolatedTarget;
  };

  const applyTextOverrides = (scope) => {
    if (!scope || !textOverrides.length || typeof document.createTreeWalker !== "function") return;
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
      let matched = false;
      for (let index = 0; index < textNodes.length; index += 1) {
        if (used.has(index)) continue;
        const node = textNodes[index];
        if (normalizeText(node.textContent) !== originalText) continue;
        node.textContent = nextText;
        used.add(index);
        matched = true;
        break;
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

      const target = matchingElements[0];
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
  };

  const applyButtonOverrides = (scope) => {
    if (!(scope instanceof Element) || !buttonOverrides.length) return;
    const actions = Array.from(scope.querySelectorAll("a, button"));
    const used = new Set();
    for (const override of buttonOverrides) {
      const originalText = normalizeText(override.originalText);
      if (!originalText) continue;
      for (let index = 0; index < actions.length; index += 1) {
        if (used.has(index)) continue;
        const element = actions[index];
        if (!matchesButtonText(element, originalText)) continue;
        const nextText = buildOverrideButtonText(element, override);
        element.dataset.mosImportedLabelPrefix = typeof override.text === "string" ? override.text : override.originalText;
        element.textContent = nextText;
        if (element instanceof HTMLAnchorElement && typeof override.href === "string") {
          if (override.href) {
            element.setAttribute("href", override.href);
          } else {
            element.removeAttribute("href");
          }
        }
        wireCommerceAction(scope, element, override);
        wireHashNavigation(element, resolveImplicitTargetHash(override));
        used.add(index);
        break;
      }
    }
  };

  const applyImageOverrides = (scope) => {
    if (!(scope instanceof Element) || !imageOverrides.length) return;
    const images = Array.from(scope.querySelectorAll("img"));
    const used = new Set();
    for (const override of imageOverrides) {
      const originalSrc = typeof override.originalSrc === "string" ? override.originalSrc.trim() : "";
      if (!originalSrc) continue;
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
    }
  };

  const finalizeSection = () => {
    const sectionRoot = isolateSection();
    applyTextOverrides(sectionRoot);
    applyButtonOverrides(sectionRoot);
    applyImageOverrides(sectionRoot);
    enhanceOmniPurchaseSelection(sectionRoot);
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
