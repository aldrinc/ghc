import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import puppeteer from "puppeteer";

const APP_URL = process.env.APP_URL ?? "http://127.0.0.1:5173/";
const VIDEO_PATH =
  process.env.VIDEO_PATH ??
  path.join(os.homedir(), "Desktop", "easeHealthRecording.mov");
const OUTPUT_DIR =
  process.env.OUTPUT_DIR ??
  path.join(os.homedir(), "Desktop", "easeHealthRecording-output");
const MODEL =
  process.env.CODE_MODEL ?? "gemini-3.1-pro-preview (high thinking)";
const STACK = process.env.CODE_STACK ?? "html_tailwind";
const HEADLESS = process.env.HEADLESS === "true";
const KEEP_BROWSER_OPEN = process.env.KEEP_BROWSER_OPEN !== "false";
const RUN_TIMEOUT_MS = Number(process.env.RUN_TIMEOUT_MS ?? 25 * 60 * 1000);
const POLL_INTERVAL_MS = 5_000;

function nowIso() {
  return new Date().toISOString();
}

async function ensureFileExists(filePath) {
  await fs.access(filePath);
}

async function saveMetadata(metadataPath, metadata) {
  await fs.writeFile(metadataPath, JSON.stringify(metadata, null, 2), "utf8");
}

async function readUiState(page) {
  return await page.evaluate(() => {
    const iframe = document.querySelector("#preview-desktop");
    const updateInput = document.querySelector('[data-testid="update-input"]');
    const bodyText = document.body.innerText;
    const liveAlerts = Array.from(
      document.querySelectorAll('[role="alert"], [role="status"]')
    )
      .map((node) => node.textContent?.trim() ?? "")
      .filter(Boolean);

    return {
      hasUpdateInput: Boolean(updateInput),
      previewHtml:
        iframe instanceof HTMLIFrameElement ? iframe.srcdoc || "" : "",
      bodyText,
      liveAlerts,
    };
  });
}

async function waitForCompletedResult(page) {
  const startedAt = Date.now();
  let lastPreviewHtml = "";
  let stablePreviewCount = 0;

  while (Date.now() - startedAt < RUN_TIMEOUT_MS) {
    const state = await readUiState(page);

    if (
      state.liveAlerts.some((text) =>
        text.includes("The request payload is too large")
      )
    ) {
      throw new Error("UI reported a websocket payload-too-large error.");
    }

    if (
      state.liveAlerts.some((text) => text.includes("Generation failed")) ||
      state.bodyText.includes("Generation failed") ||
      state.bodyText.includes("Error generating code.")
    ) {
      throw new Error("UI reported a generation failure.");
    }

    const normalizedPreviewHtml = state.previewHtml.trim();
    if (normalizedPreviewHtml.length > 200) {
      if (normalizedPreviewHtml === lastPreviewHtml) {
        stablePreviewCount += 1;
      } else {
        stablePreviewCount = 0;
        lastPreviewHtml = normalizedPreviewHtml;
      }
    }

    if (
      normalizedPreviewHtml.length > 200 &&
      (state.hasUpdateInput || stablePreviewCount >= 3)
    ) {
      return state.previewHtml;
    }

    console.log(
      `[${nowIso()}] Waiting for result... hasUpdateInput=${state.hasUpdateInput} previewHtmlLength=${state.previewHtml.length} stablePreviewCount=${stablePreviewCount}`
    );
    await delay(POLL_INTERVAL_MS);
  }

  throw new Error(
    `Timed out after ${Math.round(RUN_TIMEOUT_MS / 1000)}s waiting for the generated result.`
  );
}

async function main() {
  await ensureFileExists(VIDEO_PATH);
  await fs.mkdir(OUTPUT_DIR, { recursive: true });

  const browser = await puppeteer.launch({
    headless: HEADLESS,
    defaultViewport: { width: 1440, height: 1024 },
    args: ["--window-size=1440,1024"],
  });
  const page = await browser.newPage();

  page.on("console", (msg) => {
    console.log(`[browser:${msg.type()}] ${msg.text()}`);
  });
  page.on("pageerror", (error) => {
    console.error("[pageerror]", error);
  });
  page.on("requestfailed", (request) => {
    console.error(
      `[requestfailed] ${request.method()} ${request.url()} ${request.failure()?.errorText ?? ""}`
    );
  });

  const setting = {
    openAiApiKey: null,
    openAiBaseURL: null,
    screenshotOneApiKey: null,
    isImageGenerationEnabled: true,
    editorTheme: "cobalt",
    generatedCodeConfig: STACK,
    codeGenerationModel: MODEL,
    isTermOfServiceAccepted: true,
    anthropicApiKey: null,
    geminiApiKey: null,
  };

  await page.goto(APP_URL, { waitUntil: "networkidle0" });
  await page.evaluate((nextSetting) => {
    localStorage.setItem("setting", JSON.stringify(nextSetting));
  }, setting);
  await page.reload({ waitUntil: "networkidle0" });

  await page.waitForSelector('[data-testid="tab-upload"]', { timeout: 30_000 });
  await page.click('[data-testid="tab-upload"]');

  const fileInput = await page.$('[data-testid="upload-input"]');
  if (!fileInput) {
    throw new Error("Upload input element not found.");
  }

  console.log(`[${nowIso()}] Uploading ${VIDEO_PATH}`);
  await fileInput.uploadFile(VIDEO_PATH);
  await page.waitForSelector('[data-testid="upload-generate"]', {
    timeout: 30_000,
  });

  const beforePath = path.join(OUTPUT_DIR, "easeHealthRecording_before.png");
  await page.screenshot({ path: beforePath, fullPage: true });

  console.log(`[${nowIso()}] Starting generation run`);
  await page.click('[data-testid="upload-generate"]');

  const generatedHtml = await waitForCompletedResult(page);

  const htmlPath = path.join(
    OUTPUT_DIR,
    "easeHealthRecording_generated.html"
  );
  const uiScreenshotPath = path.join(
    OUTPUT_DIR,
    "easeHealthRecording_ui_result.png"
  );
  const previewScreenshotPath = path.join(
    OUTPUT_DIR,
    "easeHealthRecording_preview_result.png"
  );
  const metadataPath = path.join(
    OUTPUT_DIR,
    "easeHealthRecording_run_metadata.json"
  );

  await fs.writeFile(htmlPath, generatedHtml, "utf8");
  await page.screenshot({ path: uiScreenshotPath, fullPage: true });

  const previewHandle = await page.$("#preview-desktop");
  if (previewHandle) {
    await previewHandle.screenshot({ path: previewScreenshotPath });
  }

  await saveMetadata(metadataPath, {
    appUrl: APP_URL,
    videoPath: VIDEO_PATH,
    outputDir: OUTPUT_DIR,
    outputHtmlPath: htmlPath,
    uiScreenshotPath,
    previewScreenshotPath,
    model: MODEL,
    stack: STACK,
    finishedAt: nowIso(),
  });

  console.log(`Saved HTML to ${htmlPath}`);
  console.log(`Saved UI screenshot to ${uiScreenshotPath}`);
  console.log(`Saved preview screenshot to ${previewScreenshotPath}`);
  console.log(`Saved metadata to ${metadataPath}`);

  if (KEEP_BROWSER_OPEN && !HEADLESS) {
    await browser.disconnect();
    console.log("Browser left open on the completed UI result.");
    return;
  }

  await browser.close();
}

main().catch(async (error) => {
  console.error("[run-desktop-video] Failed:", error);
  process.exitCode = 1;
});
