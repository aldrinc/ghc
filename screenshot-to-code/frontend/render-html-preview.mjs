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

async function waitForSettledAnimations(page) {
  const hasAnimatedElements = await page.evaluate(
    () => document.querySelectorAll("[data-animate]").length > 0
  );

  if (!hasAnimatedElements) {
    await delay(300);
    return;
  }

  try {
    await page.waitForFunction(
      () => {
        const animated = Array.from(document.querySelectorAll("[data-animate]"));
        return (
          animated.length === 0 ||
          animated.every((element) =>
            element.classList.contains("animate-active")
          )
        );
      },
      { timeout: 2500 }
    );
  } catch {
    // Fall back to a fixed settle delay when the page never reaches a clean
    // "all active" state within the timeout.
  }

  await delay(1200);
}

async function captureViewportDataUrl(page) {
  const base64 = await page.screenshot({
    type: "png",
    encoding: "base64",
    fullPage: false,
  });
  return `data:image/png;base64,${base64}`;
}

async function captureFullPageDataUrl(page) {
  const base64 = await page.screenshot({
    type: "png",
    encoding: "base64",
    fullPage: true,
  });
  return `data:image/png;base64,${base64}`;
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
    const html = typeof payload.html === "string" ? payload.html : "";
    const width = Number.isFinite(payload.width) ? payload.width : 1440;
    const height = Number.isFinite(payload.height) ? payload.height : 1024;
    const rawTimelinePlan = Array.isArray(payload.timelinePlan)
      ? payload.timelinePlan
      : [];
    const timelinePlan = rawTimelinePlan
      .map((entry, index) => {
        if (!entry || typeof entry !== "object") {
          return null;
        }

        const elapsedMs = Number.isFinite(entry.elapsedMs) ? entry.elapsedMs : null;
        const label =
          typeof entry.label === "string" && entry.label.trim()
            ? entry.label.trim()
            : `checkpoint-${index + 1}`;

        if (elapsedMs === null || elapsedMs < 0) {
          return null;
        }

        return { label, elapsedMs };
      })
      .filter(Boolean);

    browser = await puppeteer.launch({
      headless: true,
      args: ["--no-sandbox", "--disable-dev-shm-usage"],
    });

    const page = await browser.newPage();
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    await page.setContent(html, { waitUntil: "networkidle0" });
    await waitForStableRender(page);

    const viewportDataUrl = await captureViewportDataUrl(page);
    const fullPageDataUrl = await captureFullPageDataUrl(page);

    const timelineFrames = [];
    let lastDelayMs = 0;
    for (const frame of timelinePlan) {
      const waitMs = Math.max(0, frame.elapsedMs - lastDelayMs);
      if (waitMs > 0) {
        await delay(waitMs);
      }
      await waitForStableRender(page);
      timelineFrames.push({
        label: frame.label,
        elapsedMs: frame.elapsedMs,
        viewportDataUrl: await captureViewportDataUrl(page),
      });
      lastDelayMs = frame.elapsedMs;
    }

    await waitForSettledAnimations(page);
    await waitForStableRender(page);

    const settledViewportDataUrl = await captureViewportDataUrl(page);
    const settledFullPageDataUrl = await captureFullPageDataUrl(page);

    process.stdout.write(
      JSON.stringify({
        viewportDataUrl,
        fullPageDataUrl,
        settledViewportDataUrl,
        settledFullPageDataUrl,
        timelineFrames,
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
