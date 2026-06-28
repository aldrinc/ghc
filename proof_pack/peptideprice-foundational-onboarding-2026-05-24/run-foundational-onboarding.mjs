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
const sourceUrl = "https://peptideprice.store/";
const workspaceName = `Peptide Price Store ${new Date().toISOString().slice(0, 16).replace("T", " ")}`;
const finalVideoPath = path.join(videosDir, "peptideprice-foundational-onboarding.webm");
const uiZipPath = path.join(downloadsDir, "peptideprice-foundational-docs.zip");
const summaryPath = path.join(proofRoot, "run-summary.json");
const logPath = path.join(proofRoot, "automation-events.jsonl");

function extractSetupClientId(setupUrl) {
  const match = String(setupUrl || "").match(/\/clients\/([^/]+)\/marketing-agent\/setup/);
  return match?.[1] || null;
}

function log(message, details = {}) {
  const entry = {
    at: new Date().toISOString(),
    message,
    ...details,
  };
  console.log(JSON.stringify(entry));
  return fs.appendFile(logPath, `${JSON.stringify(entry)}\n`);
}

async function readEnvFile(filePath) {
  const raw = await fs.readFile(filePath, "utf8");
  const values = {};
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const equalsIndex = trimmed.indexOf("=");
    if (equalsIndex <= 0) continue;
    const key = trimmed.slice(0, equalsIndex).trim();
    const value = trimmed.slice(equalsIndex + 1).trim();
    values[key] = value;
  }
  return values;
}

async function pathExists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function screenshot(page, name) {
  const filePath = path.join(screenshotsDir, `${name}.png`);
  await page.screenshot({ path: filePath, fullPage: true });
  await log("screenshot", { filePath });
  return filePath;
}

async function visibleText(page) {
  return (await page.locator("body").innerText({ timeout: 10000 }).catch(() => "")).trim();
}

async function clickSingle(locator, label) {
  const count = await locator.count();
  if (count !== 1) {
    throw new Error(`${label} expected 1 match, got ${count}`);
  }
  await locator.click();
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

async function maybeSignIn(page, { email, password }) {
  await page.goto(`${appBaseUrl}/workspaces/new`, { waitUntil: "networkidle", timeout: 120000 });
  const needsSignIn =
    page.url().includes("/sign-in") || (await page.locator("#identifier-field").count()) > 0;
  if (!needsSignIn) {
    await log("auth_state_reused");
    return;
  }

  await log("auth_state_refresh_started");
  await page.goto(`${appBaseUrl}/sign-in`, { waitUntil: "networkidle", timeout: 120000 });
  await page.locator("#identifier-field").fill(email);
  await page.locator("#password-field").fill(password);
  await page.getByRole("button", { name: /^Continue$/ }).click();
  await page.waitForFunction(() => !window.location.pathname.includes("/sign-in"), { timeout: 120000 });
  await page.context().storageState({ path: authStatePath });
  await page.goto(`${appBaseUrl}/workspaces/new`, { waitUntil: "networkidle", timeout: 120000 });
  if (page.url().includes("/sign-in")) {
    throw new Error("MOS sign-in did not complete successfully.");
  }
  await log("auth_state_refresh_completed");
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

async function downloadFoundationalZip(page, workflowRunId) {
  await page.goto(`${appBaseUrl}/strategy/${workflowRunId}`, { waitUntil: "networkidle", timeout: 120000 });
  await screenshot(page, "07-strategy-run");
  await page.getByText("Workflow research artifacts").waitFor({ state: "visible", timeout: 120000 });
  await screenshot(page, "08-research-artifacts");

  const downloadPromise = page.waitForEvent("download", { timeout: 120000 });
  const clicked = await clickFirstEnabledButtonByText(page, "Download foundational ZIP");
  if (!clicked) {
    throw new Error("No enabled Download foundational ZIP button was available.");
  }
  const download = await downloadPromise;
  await download.saveAs(uiZipPath);
  await log("foundational_zip_downloaded", {
    suggestedFilename: download.suggestedFilename(),
    filePath: uiZipPath,
  });
  await screenshot(page, "09-download-complete");
  return {
    path: uiZipPath,
    suggestedFilename: download.suggestedFilename(),
  };
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
      await screenshot(page, `06-foundation-progress-${String(attempt).padStart(2, "0")}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 15000));
  }
  throw new Error(`Timed out waiting for foundation_ready. Last response: ${JSON.stringify(last)}`);
}

async function main() {
  await fs.rm(screenshotsDir, { recursive: true, force: true });
  await fs.rm(downloadsDir, { recursive: true, force: true });
  await fs.rm(videosDir, { recursive: true, force: true });
  await fs.mkdir(screenshotsDir, { recursive: true });
  await fs.mkdir(downloadsDir, { recursive: true });
  await fs.mkdir(videosDir, { recursive: true });
  await fs.writeFile(logPath, "");

  const env = await readEnvFile(authEnvPath);
  const email = env.MOS_TEST_EMAIL;
  const password = env.MOS_TEST_PASSWORD;
  if (!email || !password) throw new Error("MOS test credentials are missing.");

  const browser = await chromium.launch({ headless: true });
  const contextOptions = {
    acceptDownloads: true,
    viewport: { width: 1440, height: 1000 },
    recordVideo: {
      dir: videosDir,
      size: { width: 1440, height: 1000 },
    },
  };
  if (await pathExists(authStatePath)) {
    contextOptions.storageState = authStatePath;
  }

  const context = await browser.newContext(contextOptions);
  const page = await context.newPage();
  const setupResponses = [];
  const extractResponses = [];
  page.on("response", async (response) => {
    const url = response.url();
    if (!url.includes("/marketing-agent/")) return;
    if (!url.includes("/extract") && !url.includes("/setup")) return;
    const payload = await response.json().catch(() => null);
    const record = {
      url,
      status: response.status(),
      payload,
    };
    if (url.includes("/extract")) extractResponses.push(record);
    if (url.includes("/setup")) setupResponses.push(record);
    await log("marketing_agent_response", {
      endpoint: url.includes("/extract") ? "extract" : "setup",
      status: response.status(),
    });
  });

  let summary = null;
  try {
    await log("automation_started", { workspaceName, sourceUrl });
    await maybeSignIn(page, { email, password });
    await screenshot(page, "01-onboarding-start");

    await page.getByLabel("Workspace name").fill(workspaceName);
    await screenshot(page, "02-workspace-name");
    await clickSingle(page.getByRole("button", { name: /^Continue$/ }), "Continue after workspace name");

    await clickSingle(page.getByText("Already live business", { exact: true }), "Already live business choice");
    await screenshot(page, "03-existing-business");

    await page.getByLabel("Business website URL").fill(sourceUrl);
    await screenshot(page, "04-business-url");
    await clickSingle(page.getByRole("button", { name: /^Continue$/ }), "Continue after business URL");

    await page.getByLabel("Competitor websites").waitFor({ state: "visible", timeout: 60000 });
    await screenshot(page, "05-competitors-omitted");
    await clickSingle(page.getByRole("button", { name: /^Continue$/ }), "Continue after competitors");

    await page.getByRole("button", { name: "Create workspace" }).waitFor({ state: "visible", timeout: 240000 });
    await screenshot(page, "06-review-before-create");
    const createButton = page.getByRole("button", { name: "Create workspace" });
    if (!(await createButton.isEnabled())) {
      const bodyText = await visibleText(page);
      await fs.writeFile(path.join(proofRoot, "blocked-review-text.txt"), bodyText);
      throw new Error("Create workspace button is disabled after source extraction.");
    }
    await createButton.click();
    await page.getByText("Setting up your workspace").waitFor({ state: "visible", timeout: 120000 });
    await screenshot(page, "06-setup-running");

    await page.waitForFunction(() => window.location.pathname.includes("/workspaces"), { timeout: 30000 }).catch(() => {});
    const setupPayload = setupResponses.at(-1)?.payload;
    const setupClientId = setupPayload?.client_id || extractSetupClientId(setupResponses.at(-1)?.url);
    if (!setupClientId || !setupPayload?.product_id) {
      throw new Error(`Setup response missing client_id/product_id: ${JSON.stringify(setupPayload)}`);
    }
    await log("setup_created", {
      client_id: setupClientId,
      product_id: setupPayload.product_id,
      onboarding_workflow_run_id: setupPayload.workflow_run_id,
      temporal_workflow_id: setupPayload.temporal_workflow_id,
    });

    const readiness = await pollFoundationReady(page, setupClientId, setupPayload.product_id);
    await page.goto(`${appBaseUrl}/workspaces/foundation-ready`, { waitUntil: "networkidle", timeout: 120000 });
    await screenshot(page, "07-foundation-ready");

    const strategyWorkflowRunId = readiness.strategy_workflow_run_id;
    if (!strategyWorkflowRunId) {
      throw new Error(`Readiness response missing strategy_workflow_run_id: ${JSON.stringify(readiness)}`);
    }
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

    summary = {
      status: "passed",
      provenance: {
        kind: "runtime_observed",
        source_manifest: path.join(proofRoot, "source", "source_manifest.json"),
        automation_events: logPath,
      },
      workspace_name: workspaceName,
      source_url: sourceUrl,
      competitor_urls: [],
      setup: {
        client_id: setupClientId,
        product_id: setupPayload.product_id,
        onboarding_workflow_run_id: setupPayload.workflow_run_id,
        onboarding_temporal_workflow_id: setupPayload.temporal_workflow_id,
      },
      readiness,
      strategy_workflow_run_id: strategyWorkflowRunId,
      research_artifacts: researchArtifacts,
      extraction_response_observed: extractResponses.at(-1)?.payload || null,
      download: zip,
      screenshots_dir: screenshotsDir,
      video_path: finalVideoPath,
    };
    await fs.writeFile(summaryPath, `${JSON.stringify(summary, null, 2)}\n`);
    await log("automation_completed", { summaryPath });
  } catch (error) {
    const bodyText = await visibleText(page).catch(() => "");
    await fs.writeFile(path.join(proofRoot, "automation-failure-page.txt"), bodyText);
    await screenshot(page, "failure").catch(() => {});
    summary = {
      status: "failed",
      error: error instanceof Error ? error.message : String(error),
      source_url: sourceUrl,
      workspace_name: workspaceName,
      setup_responses: setupResponses,
      extract_responses: extractResponses,
      screenshots_dir: screenshotsDir,
      video_path: finalVideoPath,
      provenance: {
        kind: "runtime_observed",
        source_manifest: path.join(proofRoot, "source", "source_manifest.json"),
        automation_events: logPath,
      },
    };
    await fs.writeFile(summaryPath, `${JSON.stringify(summary, null, 2)}\n`);
    throw error;
  } finally {
    const video = page.video();
    await context.close();
    if (video) {
      const rawVideoPath = await video.path();
      await fs.copyFile(rawVideoPath, finalVideoPath);
      await log("video_saved", { rawVideoPath, finalVideoPath });
    }
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
});
