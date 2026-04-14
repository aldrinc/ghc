import puppeteer from "puppeteer";

async function delay(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForStableRender(page) {
  await page.evaluate(async () => {
    if (document.fonts?.ready) {
      await document.fonts.ready;
    }
  });

  await page.evaluate(
    () =>
      new Promise((resolve) => {
        requestAnimationFrame(() => {
          requestAnimationFrame(resolve);
        });
      })
  );
}

async function captureScreenshotDataUrl(page, fullPage) {
  const base64 = await page.screenshot({
    type: "png",
    encoding: "base64",
    fullPage,
  });
  return `data:image/png;base64,${base64}`;
}

async function extractDesignSystem(page) {
  return page.evaluate(() => {
    const RULE_HINT_PROPERTIES = [
      "display",
      "flex-direction",
      "grid-template-columns",
      "align-items",
      "justify-content",
      "gap",
      "width",
      "height",
      "background",
      "background-image",
      "background-size",
      "object-fit",
    ];
    const matchedRuleHintCache = new WeakMap();

    const STRUCTURAL_KEYWORDS = [
      "announcement",
      "article",
      "banner",
      "dialog",
      "drawer",
      "dropdown",
      "footer",
      "header",
      "hero",
      "legal",
      "main",
      "marquee",
      "mega",
      "menu",
      "modal",
      "nav",
      "newsletter",
      "overlay",
      "popup",
      "promo",
      "related",
      "section",
      "sticky",
      "subscribe",
      "wrapper",
    ];

    function normalizeText(value) {
      return typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";
    }

    function formatStyleSignature(label, style, extras = []) {
      const parts = [
        `${label}: font ${style.fontFamily}`,
        `size ${style.fontSize}`,
        `line-height ${style.lineHeight}`,
        `weight ${style.fontWeight}`,
        `color ${style.color}`,
      ];
      if (style.letterSpacing && style.letterSpacing !== "normal") {
        parts.push(`letter-spacing ${style.letterSpacing}`);
      }
      if (style.textTransform && style.textTransform !== "none") {
        parts.push(`transform ${style.textTransform}`);
      }
      return [...parts, ...extras].join("; ");
    }

    function isVisible(element) {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return (
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        Number(style.opacity || "1") > 0 &&
        rect.width > 0 &&
        rect.height > 0
      );
    }

    function countValues(elements, getter, options = {}) {
      const maxItems = options.maxItems ?? 10;
      const map = new Map();
      for (const element of elements) {
        const value = normalizeText(getter(element));
        if (!value || value === "0px" || value === "rgba(0, 0, 0, 0)" || value === "none") {
          continue;
        }
        map.set(value, (map.get(value) ?? 0) + 1);
      }
      return Array.from(map.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, maxItems)
        .map(([value, count]) => ({ value, count }));
    }

    function uniqueStrings(values, maxItems = 10) {
      const seen = new Set();
      const result = [];
      for (const value of values) {
        const normalized = normalizeText(value);
        if (!normalized || seen.has(normalized)) {
          continue;
        }
        seen.add(normalized);
        result.push(normalized);
        if (result.length >= maxItems) {
          break;
        }
      }
      return result;
    }

    const allVisible = Array.from(document.querySelectorAll("body *"))
      .filter((element) => element instanceof HTMLElement)
      .filter((element) => isVisible(element));

    const body = document.body;
    const bodyStyle = window.getComputedStyle(body);

    function firstVisible(selector) {
      return Array.from(document.querySelectorAll(selector)).find(
        (element) => element instanceof HTMLElement && isVisible(element)
      );
    }

    function topOffset(element) {
      return element.getBoundingClientRect().top + window.scrollY;
    }

    function overlap(startA, endA, startB, endB) {
      return Math.max(0, Math.min(endA, endB) - Math.max(startA, startB));
    }

    function buildElementHandle(element) {
      const tag = element.tagName.toLowerCase();
      const parts = [`<${tag}>`];
      if (element.id) {
        parts.push(`#${element.id}`);
      }
      const classNames = Array.from(element.classList || []).slice(0, 3);
      if (classNames.length) {
        parts.push(classNames.map((className) => `.${className}`).join(""));
      }
      const role = normalizeText(element.getAttribute("role"));
      if (role) {
        parts.push(`role="${role}"`);
      }
      return parts.join("");
    }

    function cssEscapeIdentifier(value) {
      if (!value) {
        return "";
      }
      if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
        return CSS.escape(value);
      }
      return String(value).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
    }

    function slugify(value) {
      return normalizeText(value)
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
    }

    function buildElementSelector(element) {
      if (!(element instanceof Element)) {
        return "";
      }
      if (element.id) {
        return `#${cssEscapeIdentifier(element.id)}`;
      }

      const parts = [];
      let current = element;
      for (let depth = 0; depth < 5; depth += 1) {
        if (!(current instanceof Element) || current === document.documentElement) {
          break;
        }

        let part = current.tagName.toLowerCase();
        const dataSectionId = normalizeText(current.getAttribute("data-section-id"));
        if (dataSectionId) {
          part += `[data-section-id="${dataSectionId.replace(/"/g, '\\"')}"]`;
          parts.unshift(part);
          break;
        }

        const classNames = Array.from(current.classList || [])
          .filter(Boolean)
          .slice(0, 2)
          .map((className) => `.${cssEscapeIdentifier(className)}`);
        if (classNames.length) {
          part += classNames.join("");
        } else if (current.parentElement instanceof Element) {
          const siblings = Array.from(current.parentElement.children).filter(
            (child) => child.tagName === current.tagName
          );
          if (siblings.length > 1) {
            part += `:nth-of-type(${siblings.indexOf(current) + 1})`;
          }
        }

        parts.unshift(part);
        current = current.parentElement;
        if (current === document.body) {
          break;
        }
      }

      return parts.join(" > ");
    }

    function truncateHtmlExcerpt(html, maxChars = 900) {
      const normalized = normalizeText(html);
      if (!normalized) {
        return "";
      }
      return normalized.length > maxChars
        ? `${normalized.slice(0, maxChars)}… [truncated]`
        : normalized;
    }

    function findHeadingText(element) {
      if (!(element instanceof HTMLElement)) {
        return "";
      }
      const heading = Array.from(element.querySelectorAll("h1, h2, h3, h4, h5, h6")).find(
        (child) => child instanceof HTMLElement && isVisible(child) && normalizeText(child.textContent)
      );
      return heading instanceof HTMLElement
        ? normalizeText(heading.textContent).slice(0, 180)
        : "";
    }

    function nearestStructuralParent(element) {
      if (!(element instanceof HTMLElement)) {
        return null;
      }
      let current = element.parentElement;
      while (current instanceof HTMLElement) {
        if (
          current === document.body ||
          current === document.documentElement ||
          hasStructuralSignal(current) ||
          ["main", "section", "article", "header", "footer", "nav", "form", "dialog", "aside"].includes(
            current.tagName.toLowerCase()
          )
        ) {
          return current;
        }
        current = current.parentElement;
      }
      return null;
    }

    function collectElementAssetUrls(element, maxItems = 6) {
      if (!(element instanceof HTMLElement)) {
        return [];
      }
      const urls = [];
      const seen = new Set();

      function addUrl(value) {
        const resolved = safeResolveUrl(value);
        if (!resolved || seen.has(resolved) || isTrackingAssetUrl(resolved)) {
          return;
        }
        seen.add(resolved);
        urls.push(resolved);
      }

      for (const url of extractCssUrls(window.getComputedStyle(element).backgroundImage)) {
        addUrl(url);
      }

      const mediaNodes = [
        element,
        ...Array.from(element.querySelectorAll("img, video, source, svg, use, image")),
      ];
      for (const node of mediaNodes) {
        if (urls.length >= maxItems) {
          break;
        }
        if (node instanceof HTMLImageElement) {
          addUrl(node.currentSrc || node.src);
        } else if (node instanceof HTMLVideoElement) {
          addUrl(node.poster || node.currentSrc || node.src);
        } else if (node instanceof HTMLSourceElement) {
          addUrl(node.src);
        } else if (node instanceof Element) {
          addUrl(node.getAttribute("href") || node.getAttribute("xlink:href") || node.getAttribute("src"));
        }
      }

      const backgroundNodes = [element, ...Array.from(element.querySelectorAll("*")).slice(0, 80)];
      for (const node of backgroundNodes) {
        if (!(node instanceof HTMLElement) || urls.length >= maxItems) {
          continue;
        }
        for (const url of extractCssUrls(window.getComputedStyle(node).backgroundImage)) {
          addUrl(url);
          if (urls.length >= maxItems) {
            break;
          }
        }
      }

      return urls.slice(0, maxItems);
    }

    const evidenceIdCounts = new Map();

    function uniqueEvidenceId(seed) {
      const normalized = slugify(seed) || "dom-evidence";
      const nextCount = (evidenceIdCounts.get(normalized) ?? 0) + 1;
      evidenceIdCounts.set(normalized, nextCount);
      return nextCount === 1 ? normalized : `${normalized}-${nextCount}`;
    }

    function buildEvidenceNotes(element, extraNotes = []) {
      if (!(element instanceof HTMLElement)) {
        return uniqueStrings(extraNotes, 6);
      }
      const notes = [...extraNotes];
      const compositionRoot = resolveCompositionElement(element, 2) || element;
      const composition = describeCompositionPattern(compositionRoot);
      if (composition) {
        notes.push(composition);
      }
      const ruleHints = matchedDeclarationHints(element, 6);
      if (ruleHints.length) {
        notes.push(`css hints: ${ruleHints.join(", ")}`);
      }
      const contentLabel = primaryContentLabel(element);
      if (contentLabel) {
        notes.push(`content label "${contentLabel.slice(0, 120)}"`);
      }
      return uniqueStrings(notes, 6);
    }

    function buildEvidenceItem(element, options = {}) {
      if (!(element instanceof HTMLElement)) {
        return null;
      }
      const rect = element.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) {
        return null;
      }
      const style = window.getComputedStyle(element);
      const parent = options.parentElement instanceof HTMLElement
        ? options.parentElement
        : nearestStructuralParent(element);
      const label =
        normalizeText(options.label) ||
        findHeadingText(element) ||
        primaryContentLabel(element) ||
        buildElementHandle(element);
      const selector = buildElementSelector(element);
      const parentSelector = parent instanceof HTMLElement ? buildElementSelector(parent) : "";
      const headingText = findHeadingText(element);
      const background = backgroundDescriptor(style);
      const evidenceId = uniqueEvidenceId(
        `${options.kind || "section"}-${options.idSeed || label || selector || buildElementHandle(element)}`
      );
      return {
        evidence_id: evidenceId,
        kind: options.kind || "section",
        label,
        selector,
        parent_selector: parentSelector,
        tag: element.tagName.toLowerCase(),
        role: normalizeText(element.getAttribute("role")),
        heading_text: headingText,
        text_sample: normalizeText((element.innerText || element.textContent || "")).slice(0, 240),
        top_offset_px: Math.round(topOffset(element)),
        height_px: Math.round(rect.height),
        position: style.position,
        background,
        border_radius: style.borderRadius,
        max_width: style.maxWidth && style.maxWidth !== "none" ? style.maxWidth : "",
        asset_urls: collectElementAssetUrls(element),
        notes: buildEvidenceNotes(element, options.notes || []),
        html_excerpt: truncateHtmlExcerpt(element.outerHTML || ""),
      };
    }

    function dedupeEvidenceItems(items) {
      const result = [];
      const seen = new Set();
      for (const item of items) {
        if (!item) {
          continue;
        }
        const key = `${item.kind}|${item.selector || item.evidence_id}`;
        if (seen.has(key)) {
          continue;
        }
        seen.add(key);
        result.push(item);
      }
      return result;
    }

    function hasStructuralSignal(element) {
      const tag = element.tagName.toLowerCase();
      if (["header", "nav", "main", "section", "article", "footer", "aside", "dialog"].includes(tag)) {
        return true;
      }
      const haystack = normalizeText(
        [
          element.id,
          element.className,
          element.getAttribute("role"),
          element.getAttribute("aria-label"),
          element.getAttribute("data-section-id"),
        ]
          .filter(Boolean)
          .join(" ")
      ).toLowerCase();
      return STRUCTURAL_KEYWORDS.some((keyword) => haystack.includes(keyword));
    }

    function primaryContentLabel(element) {
      const ariaLabel = normalizeText(element.getAttribute("aria-label"));
      if (ariaLabel) {
        return ariaLabel;
      }
      const heading = Array.from(element.querySelectorAll("h1, h2, h3, h4")).find(
        (child) => child instanceof HTMLElement && isVisible(child) && normalizeText(child.textContent)
      );
      if (heading instanceof HTMLElement) {
        return normalizeText(heading.textContent).slice(0, 120);
      }
      const text = normalizeText(element.innerText || element.textContent || "");
      return text ? text.slice(0, 120) : "";
    }

    function isMeaningfulRegion(element) {
      const rect = element.getBoundingClientRect();
      if (!isVisible(element) || rect.width < 200 || rect.height < 32) {
        return false;
      }
      return rect.height >= 72 || hasStructuralSignal(element);
    }

    function backgroundDescriptor(style) {
      const backgroundImage = normalizeText(style.backgroundImage);
      if (backgroundImage && backgroundImage !== "none") {
        if (backgroundImage.includes("gradient")) {
          return `background-image ${backgroundImage.slice(0, 140)}`;
        }
        if (backgroundImage.includes("url(")) {
          const backgroundSize = normalizeText(style.backgroundSize);
          return backgroundSize && backgroundSize !== "auto"
            ? `background-image asset; background-size ${backgroundSize}`
            : "background-image asset";
        }
      }
      if (style.backgroundColor && style.backgroundColor !== "rgba(0, 0, 0, 0)") {
        return `background ${style.backgroundColor}`;
      }
      return "";
    }

    function safeResolveUrl(value) {
      const normalized = normalizeText(value);
      if (!normalized || normalized === "none") {
        return "";
      }
      if (normalized.startsWith("data:") || normalized.startsWith("blob:")) {
        return normalized;
      }
      try {
        return new URL(normalized, window.location.href).href;
      } catch (_error) {
        return normalized;
      }
    }

    function extractCssUrls(value) {
      const urls = [];
      const seen = new Set();
      const normalized = normalizeText(value);
      const pattern = /url\((['"]?)(.*?)\1\)/gi;
      let match;
      while ((match = pattern.exec(normalized))) {
        const resolved = safeResolveUrl(match[2]);
        if (!resolved || seen.has(resolved)) {
          continue;
        }
        seen.add(resolved);
        urls.push(resolved);
      }
      return urls;
    }

    function assetLabel(element) {
      if (!(element instanceof Element)) {
        return "";
      }
      const direct = normalizeText(
        [
          element.getAttribute("alt"),
          element.getAttribute("aria-label"),
          element.getAttribute("title"),
          element.getAttribute("data-alt"),
        ]
          .filter(Boolean)
          .join(" ")
      );
      if (direct) {
        return direct.slice(0, 120);
      }
      const parent = element.parentElement;
      if (parent instanceof HTMLElement) {
        const parentLabel = primaryContentLabel(parent);
        if (parentLabel) {
          return parentLabel.slice(0, 120);
        }
      }
      return "";
    }

    function assetContextElement(element) {
      if (!(element instanceof Element)) {
        return null;
      }
      const context = element.closest(
        "section, article, header, footer, nav, aside, dialog, figure, li, [role='banner'], [role='navigation'], [role='main'], [role='contentinfo'], [role='dialog'], [data-section-id], [class*='hero'], [class*='article'], [class*='header'], [class*='footer'], [class*='product'], [class*='bundle'], [class*='showcase'], [class*='related'], [class*='newsletter'], [class*='card']"
      );
      return context instanceof Element ? context : null;
    }

    function assetMeasurementElement(element) {
      if (!(element instanceof Element)) {
        return null;
      }
      let current = element;
      for (let depth = 0; depth < 8; depth += 1) {
        if (!(current instanceof HTMLElement)) {
          break;
        }
        const rect = current.getBoundingClientRect();
        if (rect.width >= 16 && rect.height >= 16) {
          return current;
        }
        if (!(current.parentElement instanceof HTMLElement)) {
          break;
        }
        current = current.parentElement;
      }
      return element instanceof HTMLElement ? element : null;
    }

    function assetKindFromUrl(url, fallbackKind) {
      const lowered = url.toLowerCase();
      if (lowered.includes(".svg") || lowered.includes("/svg")) {
        return "svg asset";
      }
      if (fallbackKind) {
        return fallbackKind;
      }
      return "image asset";
    }

    function isTrackingAssetUrl(url) {
      const lowered = normalizeText(url).toLowerCase();
      return (
        lowered.includes("analytics.twitter.com/1/i/adsct") ||
        lowered.includes("t.co/1/i/adsct") ||
        lowered.includes("/adsct?") ||
        lowered.includes("doubleclick.net/pagead") ||
        lowered.includes("googleads.g.doubleclick.net/pagead")
      );
    }

    function buildAssetEntry(element, url, options = {}) {
      if (!(element instanceof Element)) {
        return null;
      }
      const resolvedUrl = safeResolveUrl(url);
      if (!resolvedUrl || isTrackingAssetUrl(resolvedUrl)) {
        return null;
      }
      const measurementElement = assetMeasurementElement(element);
      if (!(measurementElement instanceof HTMLElement)) {
        return null;
      }
      const rect = measurementElement.getBoundingClientRect();
      if (rect.width < 16 || rect.height < 16) {
        return null;
      }
      const context = assetContextElement(element);
      const handle = buildElementHandle(element);
      const contextHandle =
        context instanceof Element && context !== element ? buildElementHandle(context) : "";
      const style = window.getComputedStyle(element);
      const label = assetLabel(element);
      const parts = [
        contextHandle ? `${handle} in ${contextHandle}` : handle,
        `${assetKindFromUrl(resolvedUrl, options.kind || "")} ${resolvedUrl}`,
        `size ${Math.round(rect.width)}x${Math.round(rect.height)}px`,
      ];
      if (label) {
        parts.push(`label "${label}"`);
      }
      if (style.objectFit && style.objectFit !== "fill") {
        parts.push(`object-fit ${style.objectFit}`);
      }
      if (options.extra) {
        parts.push(options.extra);
      }
      return {
        text: parts.join("; "),
        top: topOffset(measurementElement),
        area: rect.width * rect.height,
        dedupeKey: `${options.kind || ""}|${resolvedUrl}|${contextHandle || handle}`,
      };
    }

    function collectAssetInventory() {
      const assetRecords = [];
      const seenKeys = new Set();

      function addRecord(record) {
        if (!record || seenKeys.has(record.dedupeKey)) {
          return;
        }
        seenKeys.add(record.dedupeKey);
        assetRecords.push(record);
      }

      for (const element of allVisible) {
        const style = window.getComputedStyle(element);
        const backgroundImage = normalizeText(style.backgroundImage);
        for (const url of extractCssUrls(backgroundImage)) {
          addRecord(
            buildAssetEntry(element, url, {
              kind: "background asset",
              extra: style.backgroundSize && style.backgroundSize !== "auto"
                ? `background-size ${style.backgroundSize}`
                : "",
              })
          );
        }
      }

      const mediaElements = Array.from(document.querySelectorAll("img, video"));
      for (const element of mediaElements) {
        if (element instanceof HTMLImageElement) {
          addRecord(
            buildAssetEntry(element, element.currentSrc || element.src, {
              kind: "image asset",
            })
          );
          continue;
        }

        if (element instanceof HTMLVideoElement) {
          addRecord(
            buildAssetEntry(element, element.poster || element.currentSrc || element.src, {
              kind: "video asset",
            })
          );
          for (const source of Array.from(element.querySelectorAll("source"))) {
            const sourceSrc = source.getAttribute("src");
            if (!sourceSrc) {
              continue;
            }
            addRecord(
              buildAssetEntry(element, sourceSrc, {
                kind: "video asset",
                extra:
                  normalizeText(source.getAttribute("type")) || "video source",
              })
            );
          }
        }
      }

      const svgElements = Array.from(document.querySelectorAll("svg, use, image")).filter(
        (element) => element instanceof Element && isVisible(element)
      );
      for (const element of svgElements) {
        const href =
          element.getAttribute("href") ||
          element.getAttribute("xlink:href") ||
          element.getAttribute("src");
        if (!href || href.startsWith("#")) {
          continue;
        }
        addRecord(
          buildAssetEntry(element, href, {
            kind: "svg asset",
          })
        );
      }

      const sortedRecords = assetRecords.sort((first, second) => {
        if (first.top !== second.top) {
          return first.top - second.top;
        }
        return second.area - first.area;
      });

      return sortedRecords.map((record) => record.text);
    }

    function walkStyleRules(rules, visitor) {
      for (const rule of Array.from(rules || [])) {
        if (!rule) {
          continue;
        }
        if (rule.type === CSSRule.STYLE_RULE && rule.selectorText) {
          visitor(rule);
          continue;
        }
        if ("cssRules" in rule) {
          let nestedRules;
          try {
            nestedRules = rule.cssRules;
          } catch (_error) {
            nestedRules = null;
          }
          if (nestedRules) {
            walkStyleRules(Array.from(nestedRules), visitor);
          }
        }
      }
    }

    function meaningfulDirectChildren(root, options = {}) {
      if (!(root instanceof HTMLElement)) {
        return [];
      }
      const minWidth = options.minWidth ?? 80;
      const minHeight = options.minHeight ?? 48;
      const maxItems = options.maxItems ?? 8;
      return Array.from(root.children)
        .filter((child) => child instanceof HTMLElement && isVisible(child))
        .filter((child) => {
          const rect = child.getBoundingClientRect();
          return rect.width >= minWidth && rect.height >= minHeight;
        })
        .slice(0, maxItems);
    }

    function matchedDeclarationHints(element, maxItems = 6) {
      if (!(element instanceof HTMLElement)) {
        return [];
      }
      const cached = matchedRuleHintCache.get(element);
      if (cached) {
        return cached;
      }
      const propertyValues = new Map();
      for (const styleSheet of Array.from(document.styleSheets)) {
        let rules;
        try {
          rules = styleSheet.cssRules;
        } catch (_error) {
          continue;
        }
        walkStyleRules(Array.from(rules || []), (rule) => {
          let matches = false;
          try {
            matches = element.matches(rule.selectorText);
          } catch (_error) {
            matches = false;
          }
          if (!matches) {
            return;
          }
          for (const property of RULE_HINT_PROPERTIES) {
            const value = normalizeText(rule.style.getPropertyValue(property));
            if (!value) {
              continue;
            }
            propertyValues.set(property, value);
          }
        });
      }

      const result = RULE_HINT_PROPERTIES.filter((property) => propertyValues.has(property))
        .map((property) => `${property} ${propertyValues.get(property)}`)
        .slice(0, maxItems);
      matchedRuleHintCache.set(element, result);
      return result;
    }

    function extractPercentHint(value) {
      const normalized = normalizeText(value).toLowerCase();
      if (!normalized) {
        return null;
      }
      const directMatch = normalized.match(/(-?\d+(?:\.\d+)?)%/);
      if (!directMatch) {
        return null;
      }
      const numericValue = Number.parseFloat(directMatch[1]);
      if (!Number.isFinite(numericValue)) {
        return null;
      }
      if (normalized.startsWith("calc(100% -")) {
        return Math.max(0, 100 - numericValue);
      }
      return numericValue;
    }

    function inferAxisFromRuleHints(element, children) {
      if (!(element instanceof HTMLElement) || children.length < 2) {
        return "";
      }
      const ruleHints = matchedDeclarationHints(element, 8);
      const displayHint = ruleHints.find((hint) => hint.startsWith("display "));
      const flexDirectionHint = ruleHints.find((hint) =>
        hint.startsWith("flex-direction ")
      );
      const gridTemplateHint = ruleHints.find((hint) =>
        hint.startsWith("grid-template-columns ")
      );
      if (displayHint?.includes("grid") && gridTemplateHint) {
        return gridTemplateHint.split(" ").length >= 3 ? "row" : "";
      }
      if (displayHint?.includes("flex")) {
        return flexDirectionHint?.includes("column") ? "column" : "row";
      }

      const childWidthHints = children
        .map((child) => {
          const widthHint = matchedDeclarationHints(child, 6).find((hint) =>
            hint.startsWith("width ")
          );
          return widthHint ? extractPercentHint(widthHint.replace(/^width\s+/i, "")) : null;
        })
        .filter((value) => typeof value === "number");
      const childHeightHints = children
        .map((child) => {
          const heightHint = matchedDeclarationHints(child, 6).find((hint) =>
            hint.startsWith("height ")
          );
          return heightHint
            ? extractPercentHint(heightHint.replace(/^height\s+/i, ""))
            : null;
        })
        .filter((value) => typeof value === "number");
      const widthTotal = childWidthHints.reduce((sum, value) => sum + value, 0);
      const heightTotal = childHeightHints.reduce((sum, value) => sum + value, 0);
      if (childWidthHints.length >= 2 && widthTotal >= 70) {
        return "row";
      }
      if (childHeightHints.length >= 2 && heightTotal >= 70) {
        return "column";
      }
      return "";
    }

    function elementHasMedia(element) {
      if (!(element instanceof HTMLElement)) {
        return false;
      }
      const style = window.getComputedStyle(element);
      const backgroundImage = normalizeText(style.backgroundImage);
      if (
        backgroundImage &&
        backgroundImage !== "none" &&
        backgroundImage.includes("url(") &&
        !backgroundImage.includes("gradient")
      ) {
        return true;
      }
      return Boolean(
        element.querySelector("img, picture, video, canvas, svg, model-viewer")
      );
    }

    function elementHasTextContent(element) {
      if (!(element instanceof HTMLElement)) {
        return false;
      }
      if (primaryContentLabel(element)) {
        return true;
      }
      return Boolean(
        Array.from(element.querySelectorAll("h1, h2, h3, h4, h5, h6, p, li, span"))
          .map((node) => normalizeText(node.textContent))
          .find((text) => text.length >= 12)
      );
    }

    function detectChildAxis(elements) {
      if (elements.length < 2) {
        return "";
      }
      let horizontalScore = 0;
      let verticalScore = 0;
      const rects = elements.map((element) => element.getBoundingClientRect());
      for (let index = 0; index < rects.length; index += 1) {
        for (let innerIndex = index + 1; innerIndex < rects.length; innerIndex += 1) {
          const first = rects[index];
          const second = rects[innerIndex];
          const verticalOverlap =
            overlap(first.top, first.bottom, second.top, second.bottom) /
            Math.max(1, Math.min(first.height, second.height));
          const horizontalOverlap =
            overlap(first.left, first.right, second.left, second.right) /
            Math.max(1, Math.min(first.width, second.width));
          if (verticalOverlap > 0.42 && Math.abs(first.left - second.left) > 24) {
            horizontalScore += 1;
          }
          if (horizontalOverlap > 0.42 && Math.abs(first.top - second.top) > 24) {
            verticalScore += 1;
          }
        }
      }
      if (!horizontalScore && !verticalScore) {
        return "";
      }
      return horizontalScore >= verticalScore ? "row" : "column";
    }

    function childSimilarityKey(element) {
      if (!(element instanceof HTMLElement)) {
        return "";
      }
      const classNames = Array.from(element.classList || [])
        .filter((className) => className.length >= 6)
        .slice(0, 2);
      return `${element.tagName.toLowerCase()}:${classNames.join(".")}`;
    }

    function describeChildSlot(element, parentRect, axis) {
      if (!(element instanceof HTMLElement)) {
        return "";
      }
      const rect = element.getBoundingClientRect();
      const style = window.getComputedStyle(element);
      const ruleHints = matchedDeclarationHints(element, 4);
      const hintedWidthPct = extractPercentHint(
        (ruleHints.find((hint) => hint.startsWith("width ")) || "").replace(
          /^width\s+/i,
          ""
        )
      );
      const hintedHeightPct = extractPercentHint(
        (ruleHints.find((hint) => hint.startsWith("height ")) || "").replace(
          /^height\s+/i,
          ""
        )
      );
      const widthPct = Math.round(
        typeof hintedWidthPct === "number"
          ? hintedWidthPct
          : (rect.width / Math.max(1, parentRect.width)) * 100
      );
      const heightPct = Math.round(
        typeof hintedHeightPct === "number"
          ? hintedHeightPct
          : (rect.height / Math.max(1, parentRect.height)) * 100
      );
      const media = elementHasMedia(element);
      const text = elementHasTextContent(element);
      const background = backgroundDescriptor(style);
      let role = "panel";
      if (axis === "row") {
        role = rect.left - parentRect.left < parentRect.width / 2 ? "left panel" : "right panel";
      } else if (axis === "column") {
        role = rect.top - parentRect.top < parentRect.height / 2 ? "top panel" : "bottom panel";
      }
      if (media && axis === "row") {
        role = role.replace("panel", "media panel");
      } else if (text && axis === "row") {
        role = role.replace("panel", "text/detail column");
      } else if (media && axis === "column") {
        role = role.replace("panel", "media block");
      } else if (text && axis === "column") {
        role = role.replace("panel", "text block");
      }

      const parts = [
        `${role} ~${axis === "row" ? widthPct : heightPct}% ${
          axis === "row" ? "width" : "height"
        }`,
      ];
      if (media && heightPct >= 88) {
        parts.push(`~${heightPct}% height`);
      }
      if (background) {
        parts.push(background);
      }
      const widthHint = ruleHints.find((hint) => hint.startsWith("width "));
      if (widthHint) {
        parts.push(`css ${widthHint}`);
      }
      if (media) {
        const mediaNode = element.querySelector("img, video, canvas, picture");
        if (mediaNode instanceof HTMLElement) {
          const mediaStyle = window.getComputedStyle(mediaNode);
          if (mediaStyle.objectFit && mediaStyle.objectFit !== "fill") {
            parts.push(`object-fit ${mediaStyle.objectFit}`);
          }
        }
      }
      return parts.join("; ");
    }

    function describeCompositionPattern(element) {
      if (!(element instanceof HTMLElement)) {
        return "";
      }
      const style = window.getComputedStyle(element);
      const ruleHints = matchedDeclarationHints(element, 6);
      const rect = element.getBoundingClientRect();
      const children = meaningfulDirectChildren(element, {
        minWidth: 56,
        minHeight: 40,
        maxItems: 4,
      });
      if (children.length < 2) {
        return "";
      }
      const explicitAxis =
        style.display === "flex"
          ? style.flexDirection.includes("column")
            ? "column"
            : "row"
          : style.display === "grid" && style.gridTemplateColumns.split(" ").length >= 2
            ? "row"
            : "";
      const hintedAxis = inferAxisFromRuleHints(element, children);
      const axis = explicitAxis || hintedAxis || detectChildAxis(children);
      if (!axis) {
        return "";
      }

      const background = backgroundDescriptor(style);
      const slotDescriptions = children
        .map((child) => describeChildSlot(child, rect, axis))
        .filter(Boolean)
        .slice(0, 3);
      const parts = [
        axis === "row" ? "horizontal split layout" : "vertical stack layout",
        `display ${style.display}`,
      ];
      if (style.display === "flex" && style.gap && style.gap !== "normal") {
        parts.push(`gap ${style.gap}`);
      }
      if (style.display === "grid" && style.gridTemplateColumns && style.gridTemplateColumns !== "none") {
        parts.push(`columns ${style.gridTemplateColumns}`);
      }
      if (background) {
        parts.push(background);
      }
      if (style.borderRadius && style.borderRadius !== "0px") {
        parts.push(`radius ${style.borderRadius}`);
      }
      if (slotDescriptions.length) {
        parts.push(slotDescriptions.join(" | "));
      }
      const geometryHints = ruleHints.filter(
        (hint) =>
          hint.startsWith("display ") ||
          hint.startsWith("flex-direction ") ||
          hint.startsWith("grid-template-columns ") ||
          hint.startsWith("align-items ") ||
          hint.startsWith("gap ")
      );
      if (geometryHints.length) {
        parts.push(`css ${geometryHints.join(", ")}`);
      }
      return parts.join("; ");
    }

    function compositionSignalScore(element) {
      if (!(element instanceof HTMLElement)) {
        return 0;
      }
      const children = meaningfulDirectChildren(element, {
        minWidth: 56,
        minHeight: 40,
        maxItems: 4,
      });
      if (children.length < 2) {
        return 0;
      }
      const ruleHints = matchedDeclarationHints(element, 8);
      let score = children.length;
      if (inferAxisFromRuleHints(element, children)) {
        score += 3;
      }
      if (detectChildAxis(children)) {
        score += 2;
      }
      if (ruleHints.some((hint) => hint.startsWith("width "))) {
        score += 1;
      }
      if (ruleHints.some((hint) => hint.startsWith("background-image "))) {
        score += 1;
      }
      return score;
    }

    function resolveCompositionElement(element, depth = 2) {
      if (!(element instanceof HTMLElement)) {
        return null;
      }
      let bestElement = element;
      let bestScore = compositionSignalScore(element);

      function walk(node, remainingDepth) {
        if (!(node instanceof HTMLElement) || remainingDepth < 0) {
          return;
        }
        const score = compositionSignalScore(node);
        if (score > bestScore) {
          bestElement = node;
          bestScore = score;
        }
        if (remainingDepth === 0) {
          return;
        }
        const children = meaningfulDirectChildren(node, {
          minWidth: 56,
          minHeight: 40,
          maxItems: 4,
        });
        for (const child of children) {
          walk(child, remainingDepth - 1);
        }
      }

      walk(element, depth);
      return bestElement;
    }

    function describeElement(element, options = {}) {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      const parts = [];
      if (typeof options.scope === "string" && options.scope) {
        parts.push(`${options.scope} ${buildElementHandle(element)}`);
      } else {
        parts.push(buildElementHandle(element));
      }
      const contentLabel = primaryContentLabel(element);
      if (contentLabel) {
        parts.push(`content "${contentLabel}"`);
      }
      parts.push(`top ${Math.round(topOffset(element))}px`);
      parts.push(`height ${Math.round(rect.height)}px`);
      if (style.position && style.position !== "static") {
        parts.push(`position ${style.position}`);
      }
      if (style.maxWidth && style.maxWidth !== "none") {
        parts.push(`max-width ${style.maxWidth}`);
      }
      const background = backgroundDescriptor(style);
      if (background) {
        parts.push(background);
      }
      if (style.borderRadius && style.borderRadius !== "0px") {
        parts.push(`radius ${style.borderRadius}`);
      }
      return parts.join("; ");
    }

    const mainElement = firstVisible("main, [role='main']");

    function collectMeaningfulChildren(root, scope) {
      if (!(root instanceof HTMLElement)) {
        return [];
      }
      return Array.from(root.children)
        .filter((child) => child instanceof HTMLElement && isMeaningfulRegion(child))
        .map((child) => ({ element: child, scope }));
    }

    function collectNestedMeaningfulChildren(candidates) {
      const nested = [];
      for (const candidate of candidates) {
        const candidateStyle = window.getComputedStyle(candidate.element);
        const candidateRole = normalizeText(candidate.element.getAttribute("role"));
        if (
          candidate.scope === "overlay" ||
          candidateStyle.position === "fixed" ||
          candidateStyle.position === "sticky" ||
          candidate.element.tagName.toLowerCase() === "dialog" ||
          candidateRole === "dialog" ||
          candidate.element.getAttribute("aria-modal") === "true"
        ) {
          continue;
        }

        const rect = candidate.element.getBoundingClientRect();
        if (rect.height < 480) {
          continue;
        }

        const directChildren = collectMeaningfulChildren(
          candidate.element,
          `${candidate.scope} nested`
        ).filter(({ element }) => {
          const childRect = element.getBoundingClientRect();
          const hasContentLabel = Boolean(primaryContentLabel(element));
          const position = window.getComputedStyle(element).position;
          return (
            childRect.height >= 96 &&
            (hasStructuralSignal(element) || hasContentLabel) &&
            (position !== "absolute" || hasContentLabel)
          );
        });

        if (!directChildren.length) {
          continue;
        }

        nested.push(...directChildren.slice(0, 4));

        if (directChildren.length === 1) {
          nested.push(
            ...collectMeaningfulChildren(
              directChildren[0].element,
              `${candidate.scope} nested`
            )
              .filter(({ element }) => {
                const childRect = element.getBoundingClientRect();
                const hasContentLabel = Boolean(primaryContentLabel(element));
                const position = window.getComputedStyle(element).position;
                return (
                  childRect.height >= 96 &&
                  (hasStructuralSignal(element) || hasContentLabel) &&
                  (position !== "absolute" || hasContentLabel)
                );
              })
              .slice(0, 4)
          );
        }
      }
      return nested;
    }

    const bodyChildren = collectMeaningfulChildren(document.body, "body child");
    const mainChildren =
      mainElement instanceof HTMLElement ? collectMeaningfulChildren(mainElement, "main child") : [];

    const overlayCandidates = Array.from(
      document.querySelectorAll(
        "dialog, [role='dialog'], [aria-modal='true'], [class*='modal'], [class*='overlay'], [class*='popup']"
      )
    )
      .filter((element) => element instanceof HTMLElement && isMeaningfulRegion(element))
      .map((element) => ({ element, scope: "overlay" }));

    const sectionInventoryBaseCandidates = [
      ...bodyChildren.filter(({ element }) => element !== mainElement),
      ...(mainChildren.length >= 2
        ? mainChildren
        : mainElement instanceof HTMLElement && isMeaningfulRegion(mainElement)
          ? [{ element: mainElement, scope: "main shell" }]
          : []),
      ...overlayCandidates,
    ];

    const sectionInventoryCandidates = [
      ...sectionInventoryBaseCandidates,
      ...collectNestedMeaningfulChildren(sectionInventoryBaseCandidates),
    ]
      .sort((a, b) => topOffset(a.element) - topOffset(b.element))
      .filter(
        (candidate, index, candidates) =>
          candidates.findIndex((entry) => entry.element === candidate.element) === index
      );

    const sectionInventory = uniqueStrings(
      sectionInventoryCandidates.map(({ element, scope }) => describeElement(element, { scope })),
      14
    );

    function shouldSkipCompositionWalk(element) {
      if (!(element instanceof HTMLElement)) {
        return true;
      }
      const style = window.getComputedStyle(element);
      const role = normalizeText(element.getAttribute("role"));
      return (
        style.position === "fixed" ||
        style.position === "sticky" ||
        element.tagName.toLowerCase() === "dialog" ||
        role === "dialog" ||
        element.getAttribute("aria-modal") === "true"
      );
    }

    function collectCompositionRoots(candidates) {
      const roots = [];
      const seen = new Set();

      function addRoot(element) {
        if (!(element instanceof HTMLElement) || seen.has(element)) {
          return;
        }
        seen.add(element);
        roots.push(element);
      }

      function walk(element, depth) {
        if (!(element instanceof HTMLElement) || depth < 0 || shouldSkipCompositionWalk(element)) {
          return;
        }
        addRoot(element);
        const children = meaningfulDirectChildren(element, {
          minWidth: depth >= 2 ? 72 : 56,
          minHeight: depth >= 2 ? 48 : 36,
          maxItems: 8,
        });
        for (const child of children) {
          walk(child, depth - 1);
        }
      }

      for (const candidate of candidates) {
        walk(candidate.element, 3);
      }

      return roots;
    }

    const compositionRoots = collectCompositionRoots(sectionInventoryCandidates);

    const layoutCompositionPatterns = uniqueStrings(
      compositionRoots
        .map((element) => {
          const composition = describeCompositionPattern(element);
          if (!composition) {
            return "";
          }
          return `${buildElementHandle(element)}: ${composition}`;
        })
        .filter(Boolean),
      8
    );

    const repeatedComponentPatterns = uniqueStrings(
      allVisible
        .map((element) => {
          if (!(element instanceof HTMLElement) || shouldSkipCompositionWalk(element)) {
            return "";
          }
          const children = meaningfulDirectChildren(element, {
            minWidth: 72,
            minHeight: 56,
            maxItems: 8,
          });
          if (children.length < 2) {
            return "";
          }

          const counts = new Map();
          for (const child of children) {
            const key = childSimilarityKey(child);
            counts.set(key, (counts.get(key) ?? 0) + 1);
          }
          const repeatedKey = Array.from(counts.entries())
            .sort((first, second) => second[1] - first[1])[0];
          if (!repeatedKey || repeatedKey[1] < 2) {
            return "";
          }

          const repeatedChildren = children.filter(
            (child) => childSimilarityKey(child) === repeatedKey[0]
          );
          if (repeatedChildren.length < 2) {
            return "";
          }

          const groupAxis = detectChildAxis(repeatedChildren);
          const representative = repeatedChildren[0];
          const representativeElement =
            resolveCompositionElement(representative, 3) || representative;
          const representativeComposition = describeCompositionPattern(
            representativeElement
          );
          if (!representativeComposition) {
            return "";
          }

          const groupLabel =
            groupAxis === "row"
              ? "horizontal row"
              : groupAxis === "column"
                ? "vertical stack"
                : "repeated group";
          return `${buildElementHandle(element)} repeats ${repeatedChildren.length} similar items in a ${groupLabel}; representative ${buildElementHandle(representativeElement)} uses ${representativeComposition}`;
        })
        .filter(Boolean),
      8
    );

    const domLandmarks = uniqueStrings(
      Array.from(
        document.querySelectorAll(
          "header, nav, main, footer, section, article, aside, dialog, [role='banner'], [role='navigation'], [role='main'], [role='contentinfo'], [role='dialog'], [class*='announcement'], [class*='promo'], [class*='modal'], [class*='newsletter'], [class*='related'], [class*='legal']"
        )
      )
        .filter((element) => element instanceof HTMLElement && isMeaningfulRegion(element))
        .sort((a, b) => topOffset(a) - topOffset(b))
        .map((element) => describeElement(element)),
      16
    );

    const chromeLayers = uniqueStrings(
      Array.from(
        document.querySelectorAll(
          "dialog, header, nav, [role='banner'], [role='navigation'], [role='dialog'], [class*='announcement'], [class*='promo'], [class*='modal'], [class*='overlay'], [class*='sticky'], [class*='newsletter'], [class*='legal'], [class*='header'], [class*='footer']"
        )
      )
        .filter((element) => {
          if (!(element instanceof HTMLElement) || !isMeaningfulRegion(element)) {
            return false;
          }
          const style = window.getComputedStyle(element);
          return style.position === "sticky" || style.position === "fixed" || hasStructuralSignal(element);
        })
        .sort((a, b) => topOffset(a) - topOffset(b))
        .map((element) => describeElement(element)),
      12
    );

    const headingHierarchy = uniqueStrings(
      Array.from(document.querySelectorAll("h1, h2, h3, h4"))
        .filter((element) => element instanceof HTMLElement && isVisible(element))
        .sort((a, b) => topOffset(a) - topOffset(b))
        .map((element) => {
          const style = window.getComputedStyle(element);
          const container = element.closest(
            "section, article, header, footer, nav, dialog, [role='banner'], [role='contentinfo'], [class*='hero'], [class*='article'], [class*='footer'], [class*='related'], [class*='newsletter'], [class*='announcement'], [class*='promo']"
          );
          const containerLabel = container instanceof HTMLElement ? buildElementHandle(container) : "";
          const parts = [
            `${element.tagName.toLowerCase()} "${normalizeText(element.textContent).slice(0, 120)}"`,
            containerLabel ? `in ${containerLabel}` : "",
            `size ${style.fontSize}`,
            `line-height ${style.lineHeight}`,
            `weight ${style.fontWeight}`,
          ].filter(Boolean);
          if (style.letterSpacing && style.letterSpacing !== "normal") {
            parts.push(`letter-spacing ${style.letterSpacing}`);
          }
          return parts.join("; ");
        }),
      14
    );

    const shellRelationships = uniqueStrings(
      sectionInventoryCandidates
        .map(({ element, scope }) => {
          const parent = element.parentElement;
          if (!(parent instanceof HTMLElement)) {
            return "";
          }
          if (parent === document.body || parent === mainElement || hasStructuralSignal(parent)) {
            const parentStyle = window.getComputedStyle(parent);
            const childStyle = window.getComputedStyle(element);
            const details = [];
            if (scope) {
              details.push(`scope ${scope}`);
            }
            if (
              parentStyle.backgroundColor === childStyle.backgroundColor &&
              childStyle.backgroundColor !== "rgba(0, 0, 0, 0)"
            ) {
              details.push(`shared background ${childStyle.backgroundColor}`);
            }
            if (
              parentStyle.borderRadius === childStyle.borderRadius &&
              childStyle.borderRadius !== "0px"
            ) {
              details.push(`shared radius ${childStyle.borderRadius}`);
            }
            if (childStyle.maxWidth && childStyle.maxWidth !== "none") {
              details.push(`child max-width ${childStyle.maxWidth}`);
            }
            return `${buildElementHandle(element)} sits within ${buildElementHandle(parent)}${
              details.length ? `; ${details.join("; ")}` : ""
            }`;
          }
          return "";
        })
        .filter(Boolean),
      12
    );

    const sectionCandidates = dedupeEvidenceItems(
      sectionInventoryCandidates
        .map(({ element, scope }) =>
          buildEvidenceItem(element, {
            kind: "section",
            label: primaryContentLabel(element) || `${scope} ${buildElementHandle(element)}`,
            idSeed: `${scope}-${buildElementHandle(element)}`,
            notes: scope ? [`scope ${scope}`] : [],
          })
        )
        .filter(Boolean)
    );

    const chromeCandidateElements = Array.from(
      document.querySelectorAll(
        "dialog, header, nav, [role='banner'], [role='navigation'], [role='dialog'], [class*='announcement'], [class*='promo'], [class*='modal'], [class*='overlay'], [class*='sticky'], [class*='newsletter'], [class*='legal'], [class*='header'], [class*='footer']"
      )
    )
      .filter((element) => element instanceof HTMLElement && isMeaningfulRegion(element))
      .filter((element) => {
        const style = window.getComputedStyle(element);
        return style.position === "sticky" || style.position === "fixed" || hasStructuralSignal(element);
      })
      .sort((a, b) => topOffset(a) - topOffset(b));

    const chromeCandidates = dedupeEvidenceItems(
      chromeCandidateElements
        .map((element) =>
          buildEvidenceItem(element, {
            kind: "chrome",
            idSeed: buildElementHandle(element),
          })
        )
        .filter(Boolean)
    );

    const footerRoots = Array.from(
      document.querySelectorAll("footer, [role='contentinfo'], [class*='footer']")
    )
      .filter((element) => element instanceof HTMLElement && isMeaningfulRegion(element))
      .sort((a, b) => topOffset(a) - topOffset(b));
    const footerBandSourceElements = [];
    for (const footerRoot of footerRoots) {
      const directBands = collectMeaningfulChildren(footerRoot, "footer band");
      if (directBands.length) {
        footerBandSourceElements.push(...directBands.map(({ element }) => element));
      } else {
        footerBandSourceElements.push(footerRoot);
      }
    }
    const footerBands = dedupeEvidenceItems(
      footerBandSourceElements
        .map((element) =>
          buildEvidenceItem(element, {
            kind: "footer_band",
            idSeed: `footer-${buildElementHandle(element)}`,
            notes: ["footer region"],
          })
        )
        .filter(Boolean)
    );

    const formCandidates = dedupeEvidenceItems(
      Array.from(document.querySelectorAll("form, [role='form']"))
        .filter((element) => element instanceof HTMLElement && isMeaningfulRegion(element))
        .map((element) =>
          buildEvidenceItem(element, {
            kind: "form",
            idSeed: buildElementHandle(element),
          })
        )
        .filter(Boolean)
    );

    const repeatedGroupCandidates = dedupeEvidenceItems(
      allVisible
        .map((element) => {
          if (!(element instanceof HTMLElement) || shouldSkipCompositionWalk(element)) {
            return null;
          }
          const children = meaningfulDirectChildren(element, {
            minWidth: 72,
            minHeight: 56,
            maxItems: 8,
          });
          if (children.length < 2) {
            return null;
          }

          const counts = new Map();
          for (const child of children) {
            const key = childSimilarityKey(child);
            counts.set(key, (counts.get(key) ?? 0) + 1);
          }
          const repeatedKey = Array.from(counts.entries()).sort(
            (first, second) => second[1] - first[1]
          )[0];
          if (!repeatedKey || repeatedKey[1] < 2) {
            return null;
          }

          const repeatedChildren = children.filter(
            (child) => childSimilarityKey(child) === repeatedKey[0]
          );
          if (repeatedChildren.length < 2) {
            return null;
          }

          const representativeElement =
            resolveCompositionElement(repeatedChildren[0], 3) || repeatedChildren[0];
          const groupAxis = detectChildAxis(repeatedChildren);
          const groupLabel =
            groupAxis === "row"
              ? "horizontal row"
              : groupAxis === "column"
                ? "vertical stack"
                : "repeated group";

          return buildEvidenceItem(element, {
            kind: "repeated_group",
            idSeed: `${buildElementHandle(element)}-${groupLabel}`,
            notes: [
              `${repeatedChildren.length} repeated items in a ${groupLabel}`,
              `representative item ${buildElementHandle(representativeElement)}`,
            ],
          });
        })
        .filter(Boolean)
    );

    const stateVariants = dedupeEvidenceItems(
      chromeCandidateElements
        .filter((element) => {
          const haystack = normalizeText(
            [
              element.id,
              element.className,
              element.getAttribute("role"),
              element.getAttribute("aria-label"),
              primaryContentLabel(element),
            ]
              .filter(Boolean)
              .join(" ")
          ).toLowerCase();
          const style = window.getComputedStyle(element);
          return (
            style.position === "sticky" ||
            style.position === "fixed" ||
            haystack.includes("sticky") ||
            haystack.includes("modal") ||
            haystack.includes("overlay") ||
            haystack.includes("promo") ||
            haystack.includes("announcement")
          );
        })
        .map((element) =>
          buildEvidenceItem(element, {
            kind: "state_variant",
            idSeed: `state-${buildElementHandle(element)}`,
          })
        )
        .filter(Boolean)
    );

    const candidateBySelector = new Map();
    for (const candidate of [
      ...sectionCandidates,
      ...chromeCandidates,
      ...footerBands,
      ...formCandidates,
      ...repeatedGroupCandidates,
      ...stateVariants,
    ]) {
      if (candidate.selector && !candidateBySelector.has(candidate.selector)) {
        candidateBySelector.set(candidate.selector, candidate);
      }
    }

    const wrapperRelationships = uniqueStrings(
      shellRelationships,
      shellRelationships.length
    )
      .map((relationshipText) => {
        const matchingChild = [...candidateBySelector.values()].find((candidate) =>
          relationshipText.includes(candidate.selector || candidate.label)
        );
        if (!matchingChild) {
          return null;
        }
        const parentElement = nearestStructuralParent(
          document.querySelector(matchingChild.selector)
        );
        const parentSelector =
          parentElement instanceof HTMLElement ? buildElementSelector(parentElement) : "";
        const parentCandidate =
          parentSelector && candidateBySelector.has(parentSelector)
            ? candidateBySelector.get(parentSelector)
            : null;
        return {
          child_evidence_id: matchingChild.evidence_id,
          child_selector: matchingChild.selector,
          parent_evidence_id: parentCandidate?.evidence_id || "",
          parent_selector: parentSelector,
          relationship: relationshipText,
          notes: matchingChild.notes.slice(0, 3),
        };
      })
      .filter(Boolean);

    const typographySelectors = [
      ["body", body],
      ["h1", firstVisible("h1")],
      ["h2", firstVisible("h2")],
      ["h3", firstVisible("h3")],
      ["p", firstVisible("p")],
      ["a", firstVisible("a")],
      ["button", firstVisible("button, [role='button']")],
      ["input", firstVisible("input, textarea, select")],
    ];

    const typography = typographySelectors
      .filter(([, element]) => element instanceof HTMLElement)
      .map(([label, element]) => {
        const style = window.getComputedStyle(element);
        const extras = [];
        if (style.backgroundColor && style.backgroundColor !== "rgba(0, 0, 0, 0)") {
          extras.push(`background ${style.backgroundColor}`);
        }
        return formatStyleSignature(label, style, extras);
      });

    const textColors = countValues(allVisible, (element) => window.getComputedStyle(element).color, {
      maxItems: 12,
    }).map(({ value, count }) => `text ${value} used on ~${count} elements`);

    const backgroundColors = countValues(
      allVisible,
      (element) => window.getComputedStyle(element).backgroundColor,
      { maxItems: 12 }
    ).map(({ value, count }) => `background ${value} used on ~${count} elements`);

    const borderColors = countValues(
      allVisible,
      (element) => window.getComputedStyle(element).borderTopColor,
      { maxItems: 8 }
    ).map(({ value, count }) => `border ${value} used on ~${count} elements`);

    const spacing = [
      ...countValues(allVisible, (element) => window.getComputedStyle(element).gap, {
        maxItems: 8,
      }).map(({ value, count }) => `gap ${value} on ~${count} elements`),
      ...countValues(
        allVisible,
        (element) => `${window.getComputedStyle(element).paddingTop} ${window.getComputedStyle(element).paddingRight} ${window.getComputedStyle(element).paddingBottom} ${window.getComputedStyle(element).paddingLeft}`,
        { maxItems: 8 }
      ).map(({ value, count }) => `padding ${value} on ~${count} elements`),
      ...countValues(
        allVisible,
        (element) => `${window.getComputedStyle(element).marginTop} ${window.getComputedStyle(element).marginBottom}`,
        { maxItems: 8 }
      ).map(({ value, count }) => `vertical margin ${value} on ~${count} elements`),
    ].slice(0, 12);

    const radii = countValues(allVisible, (element) => window.getComputedStyle(element).borderRadius, {
      maxItems: 8,
    }).map(({ value, count }) => `radius ${value} on ~${count} elements`);

    const shadows = countValues(allVisible, (element) => window.getComputedStyle(element).boxShadow, {
      maxItems: 8,
    }).map(({ value, count }) => `shadow ${value} on ~${count} elements`);

    const layoutCandidates = Array.from(document.querySelectorAll("main, section, header, footer, nav, [class*='container'], [class*='wrapper']"))
      .filter((element) => element instanceof HTMLElement)
      .filter((element) => isVisible(element))
      .slice(0, 120);

    const layout = [
      `body background ${bodyStyle.backgroundColor}`,
      ...layoutCompositionPatterns,
      ...countValues(layoutCandidates, (element) => window.getComputedStyle(element).maxWidth, {
        maxItems: 6,
      }).map(({ value, count }) => `container max-width ${value} on ~${count} layout blocks`),
      ...countValues(layoutCandidates, (element) => window.getComputedStyle(element).paddingTop, {
        maxItems: 6,
      }).map(({ value, count }) => `section top padding ${value} on ~${count} layout blocks`),
      ...countValues(layoutCandidates, (element) => window.getComputedStyle(element).paddingBottom, {
        maxItems: 6,
      }).map(({ value, count }) => `section bottom padding ${value} on ~${count} layout blocks`),
    ].slice(0, 12);

    const primaryButton = firstVisible("button, [role='button'], a[class*='button'], a[class*='btn']");
    const buttonStyle = primaryButton instanceof HTMLElement ? window.getComputedStyle(primaryButton) : null;
    const cardCandidate = firstVisible("article, section, div[class*='card'], div[class*='panel']");
    const cardStyle = cardCandidate instanceof HTMLElement ? window.getComputedStyle(cardCandidate) : null;
    const inputCandidate = firstVisible("input, textarea, select");
    const inputStyle = inputCandidate instanceof HTMLElement ? window.getComputedStyle(inputCandidate) : null;

    const components = [...repeatedComponentPatterns];
    if (buttonStyle) {
      components.push(
        [
          `button: background ${buttonStyle.backgroundColor}`,
          `text ${buttonStyle.color}`,
          `radius ${buttonStyle.borderRadius}`,
          `padding ${buttonStyle.paddingTop} ${buttonStyle.paddingRight} ${buttonStyle.paddingBottom} ${buttonStyle.paddingLeft}`,
          `shadow ${buttonStyle.boxShadow}`,
          `border ${buttonStyle.borderTopWidth} ${buttonStyle.borderTopStyle} ${buttonStyle.borderTopColor}`,
        ].join("; ")
      );
    }
    if (cardStyle) {
      components.push(
        [
          `card/surface: background ${cardStyle.backgroundColor}`,
          `radius ${cardStyle.borderRadius}`,
          `shadow ${cardStyle.boxShadow}`,
          `border ${cardStyle.borderTopWidth} ${cardStyle.borderTopStyle} ${cardStyle.borderTopColor}`,
          `padding ${cardStyle.paddingTop} ${cardStyle.paddingRight} ${cardStyle.paddingBottom} ${cardStyle.paddingLeft}`,
        ].join("; ")
      );
    }
    if (inputStyle) {
      components.push(
        [
          `input: background ${inputStyle.backgroundColor}`,
          `text ${inputStyle.color}`,
          `radius ${inputStyle.borderRadius}`,
          `border ${inputStyle.borderTopWidth} ${inputStyle.borderTopStyle} ${inputStyle.borderTopColor}`,
          `padding ${inputStyle.paddingTop} ${inputStyle.paddingRight} ${inputStyle.paddingBottom} ${inputStyle.paddingLeft}`,
        ].join("; ")
      );
    }

    const assetInventory = collectAssetInventory();

    const rawObservations = [
      `document title: ${normalizeText(document.title) || "(none)"}`,
      `body font family: ${bodyStyle.fontFamily}`,
      `body font size: ${bodyStyle.fontSize}`,
      `body text color: ${bodyStyle.color}`,
      `body background color: ${bodyStyle.backgroundColor}`,
      `visible element sample size: ${allVisible.length}`,
      `detected section inventory entries: ${sectionInventory.length}`,
      `detected chrome layers: ${chromeLayers.length}`,
      `detected DOM landmarks: ${domLandmarks.length}`,
      `detected layout composition patterns: ${layoutCompositionPatterns.length}`,
      `detected repeated component patterns: ${repeatedComponentPatterns.length}`,
      `detected asset inventory entries: ${assetInventory.length}`,
    ];

    return {
      page_title: normalizeText(document.title),
      typography,
      colors: [...textColors, ...backgroundColors, ...borderColors].slice(0, 16),
      spacing,
      radii,
      shadows,
      layout,
      components,
      asset_inventory: assetInventory,
      dom_landmarks: domLandmarks,
      section_inventory: sectionInventory,
      chrome_layers: chromeLayers,
      heading_hierarchy: headingHierarchy,
      shell_relationships: shellRelationships,
      dom_evidence: {
        section_candidates: sectionCandidates,
        chrome_candidates: chromeCandidates,
        footer_bands: footerBands,
        form_candidates: formCandidates,
        repeated_groups: repeatedGroupCandidates,
        state_variants: stateVariants,
        wrapper_relationships: wrapperRelationships,
      },
      raw_observations: rawObservations,
    };
  });
}

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  input += chunk;
});

process.stdin.on("end", async () => {
  let browser;

  try {
    const payload = JSON.parse(input || "{}");
    const url = typeof payload.url === "string" ? payload.url.trim() : "";
    const width = Number.isFinite(payload.width) ? payload.width : 1440;
    const height = Number.isFinite(payload.height) ? payload.height : 1024;

    if (!url) {
      throw new Error("Missing required live reference URL.");
    }

    browser = await puppeteer.launch({
      headless: true,
      args: ["--no-sandbox", "--disable-dev-shm-usage"],
    });

    const page = await browser.newPage();
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    await page.goto(url, { waitUntil: "networkidle2", timeout: 45000 });
    await waitForStableRender(page);
    await delay(750);
    await waitForStableRender(page);

    const viewportRender = await captureScreenshotDataUrl(page, false);
    const fullPageRender = await captureScreenshotDataUrl(page, true);
    const fullDomHtml = await page.content();
    const designSystem = await extractDesignSystem(page);

    process.stdout.write(
      JSON.stringify({
        url,
        fullDomHtml,
        designSystem,
        renders: [
          { label: "live viewport render", dataUrl: viewportRender },
          { label: "live full-page render", dataUrl: fullPageRender },
        ],
      })
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(message);
    process.exitCode = 1;
  } finally {
    if (browser) {
      await browser.close();
    }
  }
});
