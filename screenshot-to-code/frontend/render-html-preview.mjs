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
    // Use a fixed settle delay if the page never reaches a clean final state.
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

async function detectBlockingOverlay(page) {
  return await page.evaluate(() => {
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    const parseZIndex = (value) => {
      const parsed = Number.parseInt(value, 10);
      return Number.isFinite(parsed) ? parsed : 0;
    };

    const isVisible = (element) => {
      if (!(element instanceof HTMLElement)) {
        return false;
      }
      const style = window.getComputedStyle(element);
      if (
        style.display === "none" ||
        style.visibility === "hidden" ||
        Number(style.opacity) === 0
      ) {
        return false;
      }
      const rect = element.getBoundingClientRect();
      return rect.width >= 24 && rect.height >= 24;
    };

    const labelFor = (element) => {
      if (!(element instanceof HTMLElement)) {
        return "";
      }
      return [
        element.getAttribute("aria-label") || "",
        element.getAttribute("title") || "",
        element.getAttribute("data-testid") || "",
        element.id || "",
        element.className || "",
        (element.textContent || "").trim().slice(0, 120),
      ]
        .join(" ")
        .replace(/\s+/g, " ")
        .trim();
    };

    const candidates = Array.from(document.querySelectorAll("body *"))
      .filter((element) => element instanceof HTMLElement)
      .filter((element) => isVisible(element))
      .filter((element) => {
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        const zIndex = parseZIndex(style.zIndex);
        const isDialogLike =
          element.matches("dialog,[role='dialog'],[aria-modal='true']") ||
          element.hasAttribute("data-overlay") ||
          element.hasAttribute("data-modal");
        const isPositionedOverlay =
          style.position === "fixed" ||
          style.position === "sticky" ||
          style.position === "absolute";
        const coversWidth = rect.width >= viewportWidth * 0.7;
        const coversHeight = rect.height >= viewportHeight * 0.45;
        if (rect.height <= viewportHeight * 0.2 && rect.width >= viewportWidth * 0.9) {
          return false;
        }
        return (
          isDialogLike ||
          (isPositionedOverlay && coversWidth && coversHeight && zIndex >= 20)
        );
      })
      .map((element) => {
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return {
          label: labelFor(element),
          zIndex: parseZIndex(style.zIndex),
          area: rect.width * rect.height,
        };
      })
      .sort((left, right) => {
        if (right.zIndex !== left.zIndex) {
          return right.zIndex - left.zIndex;
        }
        return right.area - left.area;
      });

    return candidates[0] || null;
  });
}

async function tryClickCloseControl(page) {
  return await page.evaluate(() => {
    const closeHints = [
      "close",
      "dismiss",
      "skip",
      "not now",
      "no thanks",
      "maybe later",
      "continue to site",
      "enter site",
      "modal-close-btn",
      "close-modal",
      "close button",
    ];

    const parseZIndex = (value) => {
      const parsed = Number.parseInt(value, 10);
      return Number.isFinite(parsed) ? parsed : 0;
    };

    const isVisible = (element) => {
      if (!(element instanceof HTMLElement)) {
        return false;
      }
      const style = window.getComputedStyle(element);
      if (
        style.display === "none" ||
        style.visibility === "hidden" ||
        Number(style.opacity) === 0
      ) {
        return false;
      }
      const rect = element.getBoundingClientRect();
      return rect.width >= 12 && rect.height >= 12;
    };

    const labelFor = (element) => {
      if (!(element instanceof HTMLElement)) {
        return "";
      }
      return [
        element.getAttribute("aria-label") || "",
        element.getAttribute("title") || "",
        element.getAttribute("data-testid") || "",
        element.id || "",
        element.className || "",
        (element.textContent || "").trim().slice(0, 80),
      ]
        .join(" ")
        .replace(/\s+/g, " ")
        .trim()
        .toLowerCase();
    };

    const overlays = Array.from(document.querySelectorAll("body *"))
      .filter((element) => element instanceof HTMLElement)
      .filter((element) => {
        if (!isVisible(element)) {
          return false;
        }
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        const isDialogLike =
          element.matches("dialog,[role='dialog'],[aria-modal='true']") ||
          element.hasAttribute("data-overlay") ||
          element.hasAttribute("data-modal");
        const isPositionedOverlay =
          style.position === "fixed" ||
          style.position === "sticky" ||
          style.position === "absolute";
        const zIndex = parseZIndex(style.zIndex);
        return (
          isDialogLike ||
          (rect.width >= window.innerWidth * 0.7 &&
            rect.height >= window.innerHeight * 0.45 &&
            isPositionedOverlay &&
            zIndex >= 20)
        );
      })
      .sort((left, right) => {
        const leftStyle = window.getComputedStyle(left);
        const rightStyle = window.getComputedStyle(right);
        return parseZIndex(rightStyle.zIndex) - parseZIndex(leftStyle.zIndex);
      });

    const overlay = overlays[0];
    if (!overlay) {
      return { success: false, detail: "no blocking overlay detected" };
    }

    const overlayRect = overlay.getBoundingClientRect();
    const controls = Array.from(
      overlay.querySelectorAll(
        "button, [role='button'], a, [aria-label], [title], [data-testid], [id], [class]"
      )
    )
      .filter((element) => element instanceof HTMLElement)
      .filter((element) => isVisible(element))
      .map((element) => {
        const rect = element.getBoundingClientRect();
        const label = labelFor(element);
        const topRightDistance =
          Math.abs(rect.right - overlayRect.right) + Math.abs(rect.top - overlayRect.top);
        let score = 0;
        if (closeHints.some((hint) => label.includes(hint))) {
          score += 100;
        }
        const text = (element.textContent || "").trim().toLowerCase();
        if (text === "x" || text === "×") {
          score += 90;
        }
        score += Math.max(0, 40 - topRightDistance / 10);
        return { element, label, score };
      })
      .sort((left, right) => right.score - left.score);

    const best = controls[0];
    if (!best || best.score < 40) {
      return { success: false, detail: "no close-like control found" };
    }

    best.element.click();
    best.element.dispatchEvent(
      new MouseEvent("click", {
        bubbles: true,
        cancelable: true,
        view: window,
      })
    );
    return {
      success: true,
      detail: `clicked close-like control: ${best.label || "unlabeled control"}`,
    };
  });
}

async function tryClickOverlayRoot(page) {
  return await page.evaluate(() => {
    const parseZIndex = (value) => {
      const parsed = Number.parseInt(value, 10);
      return Number.isFinite(parsed) ? parsed : 0;
    };

    const isVisible = (element) => {
      if (!(element instanceof HTMLElement)) {
        return false;
      }
      const style = window.getComputedStyle(element);
      if (
        style.display === "none" ||
        style.visibility === "hidden" ||
        Number(style.opacity) === 0
      ) {
        return false;
      }
      const rect = element.getBoundingClientRect();
      return rect.width >= 24 && rect.height >= 24;
    };

    const overlays = Array.from(document.querySelectorAll("body *"))
      .filter((element) => element instanceof HTMLElement)
      .filter((element) => isVisible(element))
      .filter((element) => {
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return (
          (style.position === "fixed" ||
            style.position === "sticky" ||
            style.position === "absolute") &&
          rect.width >= window.innerWidth * 0.7 &&
          rect.height >= window.innerHeight * 0.45 &&
          parseZIndex(style.zIndex) >= 20
        );
      })
      .sort((left, right) => {
        const leftStyle = window.getComputedStyle(left);
        const rightStyle = window.getComputedStyle(right);
        return parseZIndex(rightStyle.zIndex) - parseZIndex(leftStyle.zIndex);
      });

    const overlay = overlays[0];
    if (!overlay) {
      return { success: false, detail: "no overlay root available" };
    }

    overlay.dispatchEvent(
      new MouseEvent("click", {
        bubbles: true,
        cancelable: true,
        view: window,
      })
    );
    return { success: true, detail: "dispatched click on overlay root" };
  });
}

async function dismissBlockingOverlays(page, automationEvents, contextLabel) {
  let overlaySeen = false;

  for (let pass = 1; pass <= 3; pass += 1) {
    const overlay = await detectBlockingOverlay(page);
    if (!overlay) {
      if (overlaySeen) {
        automationEvents.push(`[${contextLabel}] blocking overlay dismissed`);
      }
      return overlaySeen;
    }

    overlaySeen = true;
    automationEvents.push(
      `[${contextLabel}] blocking overlay detected (pass ${pass}): ${overlay.label || "unlabeled overlay"}`
    );

    const closeResult = await tryClickCloseControl(page);
    if (closeResult.success) {
      automationEvents.push(`[${contextLabel}] ${closeResult.detail}`);
      await waitForStableRender(page);
      await delay(180);
      continue;
    }

    await page.keyboard.press("Escape").catch(() => {});
    automationEvents.push(`[${contextLabel}] pressed Escape`);
    await waitForStableRender(page);
    await delay(120);

    const overlayAfterEscape = await detectBlockingOverlay(page);
    if (!overlayAfterEscape) {
      automationEvents.push(`[${contextLabel}] overlay dismissed via Escape`);
      return true;
    }

    const rootResult = await tryClickOverlayRoot(page);
    if (rootResult.success) {
      automationEvents.push(`[${contextLabel}] ${rootResult.detail}`);
      await waitForStableRender(page);
      await delay(180);
    }
  }

  const remainingOverlay = await detectBlockingOverlay(page);
  if (remainingOverlay) {
    automationEvents.push(
      `[${contextLabel}] blocking overlay remained: ${remainingOverlay.label || "unlabeled overlay"}`
    );
  }
  return overlaySeen;
}

function resolveActionType(frame) {
  const explicit = typeof frame.actionType === "string" ? frame.actionType : "";
  if (explicit === "dismiss_overlay" || explicit === "scroll" || explicit === "wait") {
    return explicit;
  }

  const combined = [
    frame.label || "",
    frame.trigger || "",
    frame.expectedResult || "",
    frame.targetDescription || "",
  ]
    .join(" ")
    .toLowerCase();

  if (combined.includes("scroll")) {
    return "scroll";
  }
  if (
    /(dismiss|close|overlay|modal|newsletter|cookie|scratch|welcome gift|promo)/.test(
      combined
    )
  ) {
    return "dismiss_overlay";
  }
  return "wait";
}

async function executeTimelineAction(page, frame, automationEvents, scrollState) {
  const actionType = resolveActionType(frame);
  const contextLabel = `timeline:${frame.label}`;

  if (actionType === "dismiss_overlay") {
    const dismissed = await dismissBlockingOverlays(page, automationEvents, contextLabel);
    if (!dismissed) {
      automationEvents.push(`[${contextLabel}] no blocking overlay found to dismiss`);
    }
    return;
  }

  if (actionType === "scroll") {
    scrollState.completed += 1;
    const ratio = Math.min(
      0.92,
      scrollState.completed / Math.max(scrollState.total + 1, 2)
    );
    await page.evaluate((targetRatio) => {
      const maxScroll = Math.max(
        0,
        document.documentElement.scrollHeight - window.innerHeight
      );
      window.scrollTo({
        top: Math.round(maxScroll * targetRatio),
        behavior: "auto",
      });
    }, ratio);
    automationEvents.push(
      `[${contextLabel}] scrolled to ${Math.round(ratio * 100)}% of page height`
    );
    await waitForStableRender(page);
    await delay(200);
    return;
  }

  automationEvents.push(`[${contextLabel}] no explicit interaction performed`);
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
        const trigger =
          typeof entry.trigger === "string" ? entry.trigger.trim() : "";
        const expectedResult =
          typeof entry.expectedResult === "string"
            ? entry.expectedResult.trim()
            : "";
        const actionType =
          typeof entry.actionType === "string" ? entry.actionType.trim() : "";
        const targetDescription =
          typeof entry.targetDescription === "string"
            ? entry.targetDescription.trim()
            : "";

        if (elapsedMs === null || elapsedMs < 0) {
          return null;
        }

        return {
          label,
          elapsedMs,
          trigger,
          expectedResult,
          actionType,
          targetDescription,
        };
      })
      .filter(Boolean);

    browser = await puppeteer.launch({
      headless: true,
      args: ["--no-sandbox", "--disable-dev-shm-usage"],
    });

    const page = await browser.newPage();
    const automationEvents = [];
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    await page.setContent(html, { waitUntil: "networkidle0" });
    await waitForStableRender(page);

    const viewportDataUrl = await captureViewportDataUrl(page);
    const fullPageDataUrl = await captureFullPageDataUrl(page);

    const hasDismissCheckpoint = timelinePlan.some(
      (frame) => resolveActionType(frame) === "dismiss_overlay"
    );
    if (!hasDismissCheckpoint) {
      await dismissBlockingOverlays(page, automationEvents, "pre-timeline");
    }

    const timelineFrames = [];
    let lastDelayMs = 0;
    const totalScrollActions = timelinePlan.filter(
      (frame) => resolveActionType(frame) === "scroll"
    ).length;
    const scrollState = { completed: 0, total: totalScrollActions };

    for (const frame of timelinePlan) {
      const waitMs = Math.max(0, frame.elapsedMs - lastDelayMs);
      if (waitMs > 0) {
        await delay(waitMs);
      }

      await waitForStableRender(page);
      await executeTimelineAction(page, frame, automationEvents, scrollState);
      await waitForStableRender(page);

      timelineFrames.push({
        label: frame.label,
        elapsedMs: frame.elapsedMs,
        viewportDataUrl: await captureViewportDataUrl(page),
      });
      lastDelayMs = frame.elapsedMs;
    }

    await dismissBlockingOverlays(page, automationEvents, "pre-settled");
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
        automationEvents,
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
