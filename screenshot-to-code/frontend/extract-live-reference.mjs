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

    const allVisible = Array.from(document.querySelectorAll("body *"))
      .filter((element) => element instanceof HTMLElement)
      .filter((element) => isVisible(element))
      .slice(0, 500);

    const body = document.body;
    const bodyStyle = window.getComputedStyle(body);

    function firstVisible(selector) {
      return Array.from(document.querySelectorAll(selector)).find(
        (element) => element instanceof HTMLElement && isVisible(element)
      );
    }

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

    const components = [];
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

    const rawObservations = [
      `document title: ${normalizeText(document.title) || "(none)"}`,
      `body font family: ${bodyStyle.fontFamily}`,
      `body font size: ${bodyStyle.fontSize}`,
      `body text color: ${bodyStyle.color}`,
      `body background color: ${bodyStyle.backgroundColor}`,
      `visible element sample size: ${allVisible.length}`,
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
    const designSystem = await extractDesignSystem(page);

    process.stdout.write(
      JSON.stringify({
        url,
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
