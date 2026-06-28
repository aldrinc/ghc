import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";

const repoRoot = "/Users/aldrinclement/Documents/programming/marketi";
const proofRoot = path.join(repoRoot, "proof_pack", "peptideprice-foundational-onboarding-2026-05-24");
const screenshotsDir = path.join(proofRoot, "screenshots");
const downloadsDir = path.join(proofRoot, "downloads");
const videosDir = path.join(proofRoot, "videos");
const authStatePath = path.join(repoRoot, ".local", "playwright-home", "mos-auth-state.json");
const frontendPackage = path.join(repoRoot, "mos", "frontend", "package.json");
const requireFromFrontend = createRequire(frontendPackage);
const { chromium } = requireFromFrontend("playwright");

const appBaseUrl = "http://localhost:5275";
const apiBaseUrl = "http://localhost:8008";
const summaryPath = path.join(proofRoot, "run-summary.json");
const logPath = path.join(proofRoot, "automation-events.jsonl");
const uiZipPath = path.join(downloadsDir, "peptideprice-foundational-docs.zip");
const videoPath = path.join(videosDir, "part-2-ui-download.webm");

async function log(message, details = {}) {
  const entry = { at: new Date().toISOString(), message, ...details };
  console.log(JSON.stringify(entry));
  await fs.appendFile(logPath, `${JSON.stringify(entry)}\n`);
}

function setupClientId(setupUrl) {
  const match = String(setupUrl || "").match(/\/clients\/([^/]+)\/marketing-agent\/setup/);
  return match?.[1] || null;
}

async function screenshot(page, name) {
  const filePath = path.join(screenshotsDir, `${name}.png`);
  await page.screenshot({ path: filePath, fullPage: true });
  await log("screenshot", { filePath });
  return filePath;
}

async function getBackendToken(page) {
  await page.waitForFunction(() => Boolean(window.Clerk?.session), { timeout: 120000 });
  const token = await page.evaluate(async () => window.Clerk.session.getToken({ template: "backend" }));
  if (!token) throw new Error("Unable to get backend auth token from Clerk session.");
  return token;
}

async function apiGet(page, urlPath) {
  const token = await getBackendToken(page);
  const response = await fetch(`${apiBaseUrl}${urlPath}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!response.ok) {
    throw new Error(`GET ${urlPath} failed: ${response.status} ${JSON.stringify(data).slice(0, 500)}`);
  }
  return data;
}

async function clickFirstEnabledButtonByText(page, text) {
  const locator = page.getByRole("button", { name: text });
  const count = await locator.count();
  for (let index = 0; index < count; index += 1) {
    const candidate = locator.nth(index);
    if (await candidate.isEnabled().catch(() => false)) {
      await candidate.click();
      return true;
    }
  }
  return false;
}

async function main() {
  await fs.mkdir(downloadsDir, { recursive: true });
  await fs.mkdir(videosDir, { recursive: true });
  const previous = JSON.parse(await fs.readFile(summaryPath, "utf8"));
  const setupRecord = previous.setup_responses?.at(-1);
  const setupPayload = setupRecord?.payload;
  const clientId = previous.setup?.client_id || setupClientId(setupRecord?.url);
  const productId = previous.setup?.product_id || setupPayload?.product_id;
  if (!clientId || !productId) throw new Error("Missing client/product context for docs download.");

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    acceptDownloads: true,
    viewport: { width: 1440, height: 1000 },
    storageState: authStatePath,
    recordVideo: {
      dir: videosDir,
      size: { width: 1440, height: 1000 },
    },
  });
  const page = await context.newPage();
  try {
    await page.goto(`${appBaseUrl}/strategy`, { waitUntil: "networkidle", timeout: 120000 });
    const readiness = await apiGet(page, `/clients/${clientId}/foundation-readiness?productId=${encodeURIComponent(productId)}`);
    if (readiness.status !== "foundation_ready") {
      throw new Error(`Foundation is not ready: ${JSON.stringify(readiness)}`);
    }
    const strategyWorkflowRunId = readiness.strategy_workflow_run_id;
    await page.goto(`${appBaseUrl}/strategy/${strategyWorkflowRunId}`, { waitUntil: "networkidle", timeout: 120000 });
    await page.getByText("Foundational docs", { exact: true }).waitFor({ state: "visible", timeout: 120000 });
    await screenshot(page, "08-foundational-docs-ready");
    const downloadPromise = page.waitForEvent("download", { timeout: 120000 });
    const clicked = await clickFirstEnabledButtonByText(page, "Download foundational ZIP");
    if (!clicked) throw new Error("No enabled Download foundational ZIP button was available.");
    const download = await downloadPromise;
    await download.saveAs(uiZipPath);
    await log("foundational_zip_downloaded", {
      suggestedFilename: download.suggestedFilename(),
      filePath: uiZipPath,
    });
    await screenshot(page, "09-foundational-download-complete");
    const workflowDetail = await apiGet(page, `/workflows/${strategyWorkflowRunId}`);
    const researchArtifacts = Array.isArray(workflowDetail.research_artifacts)
      ? workflowDetail.research_artifacts.map((artifact) => ({
          step_key: artifact.step_key,
          title: artifact.title,
          doc_url: artifact.doc_url,
          doc_id: artifact.doc_id,
          summary: artifact.summary,
        }))
      : [];
    const nextSummary = {
      status: "passed",
      provenance: previous.provenance,
      workspace_name: previous.workspace_name,
      source_url: previous.source_url,
      competitor_urls: [],
      setup: {
        client_id: clientId,
        product_id: productId,
        onboarding_workflow_run_id: setupPayload?.workflow_run_id,
        onboarding_temporal_workflow_id: setupPayload?.temporal_workflow_id,
      },
      readiness,
      strategy_workflow_run_id: strategyWorkflowRunId,
      research_artifacts: researchArtifacts,
      extraction_response_observed: previous.extract_responses?.at(-1)?.payload || previous.extraction_response_observed || null,
      download: {
        path: uiZipPath,
        suggestedFilename: download.suggestedFilename(),
      },
      screenshots_dir: screenshotsDir,
      video_paths: {
        onboarding_and_generation: path.join(videosDir, "peptideprice-foundational-onboarding.webm"),
        ui_download: videoPath,
      },
    };
    await fs.writeFile(summaryPath, `${JSON.stringify(nextSummary, null, 2)}\n`);
    await log("download_completed", { summaryPath });
  } finally {
    const video = page.video();
    await context.close();
    if (video) {
      await fs.copyFile(await video.path(), videoPath);
      await log("download_video_saved", { videoPath });
    }
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
});
