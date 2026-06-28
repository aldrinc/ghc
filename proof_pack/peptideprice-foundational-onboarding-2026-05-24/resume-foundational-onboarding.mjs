import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";

const repoRoot = "/Users/aldrinclement/Documents/programming/marketi";
const proofRoot = path.join(repoRoot, "proof_pack", "peptideprice-foundational-onboarding-2026-05-24");
const screenshotsDir = path.join(proofRoot, "screenshots");
const downloadsDir = path.join(proofRoot, "downloads");
const videosDir = path.join(proofRoot, "videos");
const authEnvPath = path.join(repoRoot, ".env.mos-test-auth");
const authStatePath = path.join(repoRoot, ".local", "playwright-home", "mos-auth-state.json");
const frontendPackage = path.join(repoRoot, "mos", "frontend", "package.json");
const requireFromFrontend = createRequire(frontendPackage);
const { chromium } = requireFromFrontend("playwright");

const appBaseUrl = "http://localhost:5275";
const apiBaseUrl = "http://localhost:8008";
const summaryPath = path.join(proofRoot, "run-summary.json");
const logPath = path.join(proofRoot, "automation-events.jsonl");
const uiZipPath = path.join(downloadsDir, "peptideprice-foundational-docs.zip");
const resumeVideoPath = path.join(videosDir, "part-2-foundation-download.webm");

function setupClientId(setupUrl) {
  const match = String(setupUrl || "").match(/\/clients\/([^/]+)\/marketing-agent\/setup/);
  return match?.[1] || null;
}

async function log(message, details = {}) {
  const entry = { at: new Date().toISOString(), message, ...details };
  console.log(JSON.stringify(entry));
  await fs.appendFile(logPath, `${JSON.stringify(entry)}\n`);
}

async function readEnvFile(filePath) {
  const raw = await fs.readFile(filePath, "utf8");
  const values = {};
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const equalsIndex = trimmed.indexOf("=");
    if (equalsIndex <= 0) continue;
    values[trimmed.slice(0, equalsIndex).trim()] = trimmed.slice(equalsIndex + 1).trim();
  }
  return values;
}

async function screenshot(page, name) {
  const filePath = path.join(screenshotsDir, `${name}.png`);
  await page.screenshot({ path: filePath, fullPage: true });
  await log("screenshot", { filePath });
  return filePath;
}

async function maybeSignIn(page, { email, password }) {
  await page.goto(`${appBaseUrl}/strategy`, { waitUntil: "networkidle", timeout: 120000 });
  const needsSignIn =
    page.url().includes("/sign-in") || (await page.locator("#identifier-field").count()) > 0;
  if (!needsSignIn) return;

  await page.goto(`${appBaseUrl}/sign-in`, { waitUntil: "networkidle", timeout: 120000 });
  await page.locator("#identifier-field").fill(email);
  await page.locator("#password-field").fill(password);
  await page.getByRole("button", { name: /^Continue$/ }).click();
  await page.waitForFunction(() => !window.location.pathname.includes("/sign-in"), { timeout: 120000 });
  await page.context().storageState({ path: authStatePath });
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

async function pollFoundationReady(page, clientId, productId) {
  const deadline = Date.now() + 90 * 60 * 1000;
  let attempt = 0;
  let last = null;
  while (Date.now() < deadline) {
    attempt += 1;
    last = await apiGet(page, `/clients/${clientId}/foundation-readiness?productId=${encodeURIComponent(productId)}`);
    await log("foundation_readiness_poll", {
      attempt,
      status: last.status,
      present_step_keys: last.present_step_keys,
      missing_step_keys: last.missing_step_keys,
      strategy_workflow_run_id: last.strategy_workflow_run_id,
    });
    if (last.status === "foundation_ready") return last;
    if (last.status === "foundation_failed") {
      throw new Error(`Foundation setup failed: ${last.reason || "unknown_error"}`);
    }
    if (attempt === 1 || attempt % 8 === 0) {
      await screenshot(page, `10-foundation-progress-${String(attempt).padStart(2, "0")}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 15000));
  }
  throw new Error(`Timed out waiting for foundation_ready. Last response: ${JSON.stringify(last)}`);
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

async function downloadFoundationalZip(page, workflowRunId) {
  await page.goto(`${appBaseUrl}/strategy/${workflowRunId}`, { waitUntil: "networkidle", timeout: 120000 });
  await screenshot(page, "11-strategy-run");
  await page.getByText("Workflow research artifacts").waitFor({ state: "visible", timeout: 120000 });
  await screenshot(page, "12-research-artifacts");

  const downloadPromise = page.waitForEvent("download", { timeout: 120000 });
  const clicked = await clickFirstEnabledButtonByText(page, "Download foundational ZIP");
  if (!clicked) throw new Error("No enabled Download foundational ZIP button was available.");
  const download = await downloadPromise;
  await download.saveAs(uiZipPath);
  await log("foundational_zip_downloaded", {
    suggestedFilename: download.suggestedFilename(),
    filePath: uiZipPath,
  });
  await screenshot(page, "13-download-complete");
  return { path: uiZipPath, suggestedFilename: download.suggestedFilename() };
}

async function main() {
  await fs.mkdir(screenshotsDir, { recursive: true });
  await fs.mkdir(downloadsDir, { recursive: true });
  await fs.mkdir(videosDir, { recursive: true });

  const previous = JSON.parse(await fs.readFile(summaryPath, "utf8"));
  const setupRecord = previous.setup_responses?.at(-1);
  const setupPayload = setupRecord?.payload;
  const clientId = setupClientId(setupRecord?.url);
  const productId = setupPayload?.product_id;
  const onboardingWorkflowRunId = setupPayload?.workflow_run_id;
  if (!clientId || !productId || !onboardingWorkflowRunId) {
    throw new Error("Cannot resume: setup response did not contain client/product/workflow context.");
  }

  const env = await readEnvFile(authEnvPath);
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
    await log("resume_started", { clientId, productId, onboardingWorkflowRunId });
    await maybeSignIn(page, { email: env.MOS_TEST_EMAIL, password: env.MOS_TEST_PASSWORD });
    await page.goto(`${appBaseUrl}/strategy/${onboardingWorkflowRunId}`, { waitUntil: "networkidle", timeout: 120000 });
    await screenshot(page, "10-onboarding-workflow-run");
    const readiness = await pollFoundationReady(page, clientId, productId);
    const strategyWorkflowRunId = readiness.strategy_workflow_run_id;
    if (!strategyWorkflowRunId) {
      throw new Error(`Readiness response missing strategy_workflow_run_id: ${JSON.stringify(readiness)}`);
    }
    await page.goto(`${appBaseUrl}/workspaces/foundation-ready`, { waitUntil: "networkidle", timeout: 120000 });
    await screenshot(page, "10-foundation-ready");
    const zip = await downloadFoundationalZip(page, strategyWorkflowRunId);
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
        onboarding_workflow_run_id: onboardingWorkflowRunId,
        onboarding_temporal_workflow_id: setupPayload.temporal_workflow_id,
      },
      readiness,
      strategy_workflow_run_id: strategyWorkflowRunId,
      research_artifacts: researchArtifacts,
      extraction_response_observed: previous.extract_responses?.at(-1)?.payload || null,
      download: zip,
      screenshots_dir: screenshotsDir,
      video_paths: {
        part_1: path.join(videosDir, "part-1-onboarding-submit.webm"),
        part_2: resumeVideoPath,
      },
    };
    await fs.writeFile(summaryPath, `${JSON.stringify(nextSummary, null, 2)}\n`);
    await log("resume_completed", { summaryPath });
  } catch (error) {
    await fs.writeFile(path.join(proofRoot, "resume-failure-page.txt"), await page.locator("body").innerText().catch(() => ""));
    await screenshot(page, "resume-failure").catch(() => {});
    throw error;
  } finally {
    const video = page.video();
    await context.close();
    if (video) {
      await fs.copyFile(await video.path(), resumeVideoPath);
      await log("resume_video_saved", { resumeVideoPath });
    }
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
});
