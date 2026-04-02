import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const scriptPath = fileURLToPath(import.meta.url);
const repoRoot = path.resolve(path.dirname(scriptPath), "..", "..", "..");
const authEnvPath = path.join(repoRoot, ".env.mos-test-auth");
const localPlaywrightHome = path.join(repoRoot, ".local", "playwright-home");
const authStatePath = path.join(localPlaywrightHome, "mos-auth-state.json");
const validationRoot = path.join(localPlaywrightHome, "page-agent-validation");
const PROMPT = "Audit this page for broken UX, copy gaps, and missing sections.";

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) {
      args[token.slice(2)] = "true";
      continue;
    }
    args[token.slice(2)] = next;
    index += 1;
  }
  return args;
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

async function pathExists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

function timestampSlug() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

async function maybeSignIn(page, context, { email, password, baseUrl, targetUrl }) {
  await page.goto(targetUrl, { waitUntil: "networkidle", timeout: 120000 });
  const needsSignIn =
    page.url().includes("/sign-in") || (await page.locator("#identifier-field").count()) > 0;
  if (!needsSignIn) return false;

  await page.goto(`${baseUrl}/sign-in`, { waitUntil: "networkidle", timeout: 120000 });
  await page.locator("#identifier-field").fill(email);
  await page.locator("#password-field").fill(password);
  await page.getByRole("button", { name: /^Continue$/ }).click();
  await page.waitForFunction(() => !window.location.pathname.includes("/sign-in"), {
    timeout: 120000,
  });
  await context.storageState({ path: authStatePath });
  await page.goto(targetUrl, { waitUntil: "networkidle", timeout: 120000 });
  if (page.url().includes("/sign-in")) {
    throw new Error("MOS sign-in did not complete successfully.");
  }
  return true;
}

async function ensureAgentSidebar(page) {
  await page.waitForSelector("text=Hermes Page Agent", { timeout: 120000 });
  await page.waitForSelector(
    "text=Cmd/Ctrl+Enter sends directly to the live Hermes-backed page thread.",
    { timeout: 120000 },
  );
  await page.waitForSelector('[data-page-agent-live-activity="true"]', { timeout: 120000 });
}

async function sendPrompt(page) {
  await page.getByPlaceholder("Tell Hermes what to change on this page.").fill(PROMPT);
  await page.getByRole("button", { name: /^Send$/ }).click();
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const siteId = (args["site-id"] || "").trim();
  const pageId = (args["page-id"] || "").trim();
  const baseUrl = (args["base-url"] || "http://127.0.0.1:5275").trim().replace(/\/+$/, "");
  if (!siteId || !pageId) {
    throw new Error("Missing required --site-id or --page-id.");
  }

  const env = { ...(await readEnvFile(authEnvPath)), ...process.env };
  const email = (env.MOS_TEST_EMAIL || "").trim();
  const password = (env.MOS_TEST_PASSWORD || "").trim();
  if (!email || !password) {
    throw new Error(`Missing MOS_TEST_EMAIL or MOS_TEST_PASSWORD in ${authEnvPath}.`);
  }

  await fs.mkdir(validationRoot, { recursive: true });
  const runDir = path.join(validationRoot, `${siteId}-${pageId}-${timestampSlug()}`);
  await fs.mkdir(runDir, { recursive: true });

  const editorUrl = `${baseUrl}/workspaces/sites/${siteId}/pages/${pageId}`;
  const previewUrl = `${baseUrl}/workspaces/sites/${siteId}/preview/us`;

  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({
      viewport: { width: 1680, height: 1200 },
      storageState: (await pathExists(authStatePath)) ? authStatePath : undefined,
      ignoreHTTPSErrors: true,
    });
    const page = await context.newPage();
    const apiErrors = [];
    page.on("response", async (response) => {
      const url = response.url();
      if (!url.includes("/agent-threads/")) return;
      if (response.status() < 400) return;
      let body = "";
      try {
        body = await response.text();
      } catch {
        body = "<unreadable>";
      }
      apiErrors.push({ url, status: response.status(), body });
    });

    const signedIn = await maybeSignIn(page, context, { email, password, baseUrl, targetUrl: editorUrl });
    await ensureAgentSidebar(page);
    const oldAiTabCount = await page.getByText("AI assistant", { exact: true }).count();
    await page.screenshot({ path: path.join(runDir, "editor.png"), fullPage: true });

    await page.goto(previewUrl, { waitUntil: "networkidle", timeout: 120000 });
    await ensureAgentSidebar(page);
    await page.screenshot({ path: path.join(runDir, "preview.png"), fullPage: true });

    await page.goto(editorUrl, { waitUntil: "networkidle", timeout: 120000 });
    await ensureAgentSidebar(page);
    await sendPrompt(page);
    await page.waitForSelector("text=Hermes is working on the page.", { timeout: 30000 });
    await page.waitForSelector('[data-page-agent-activity-item="true"]', { timeout: 120000 });
    await page.screenshot({ path: path.join(runDir, "editor-during-stream.png"), fullPage: true });
    await page.waitForSelector("text=Hermes is working on the page.", {
      state: "hidden",
      timeout: 600000,
    });
    const resetButton = page.getByRole("button", { name: /Start fresh Hermes session/i });
    if (await resetButton.isVisible().catch(() => false)) {
      await resetButton.click();
      await page.waitForSelector("text=Starting a fresh Hermes session for this page.", {
        timeout: 120000,
      });
      await page.waitForSelector("text=Starting a fresh Hermes session for this page.", {
        state: "hidden",
        timeout: 120000,
      });
      await sendPrompt(page);
      await page.waitForSelector("text=Hermes is working on the page.", { timeout: 30000 });
      await page.waitForSelector("text=Hermes is working on the page.", {
        state: "hidden",
        timeout: 600000,
      });
    }
    const sessionFailureVisible = await page.getByText("Current session failed").isVisible().catch(() => false);
    await page.waitForSelector(`text=${PROMPT}`, { timeout: 60000 });
    await page.screenshot({ path: path.join(runDir, "editor-after-send.png"), fullPage: true });

    const report = {
      siteId,
      pageId,
      editorUrl,
      previewUrl,
      signedIn,
      oldAiTabCount,
      outputDir: runDir,
      sessionFailureVisible,
      apiErrors,
    };
    await fs.writeFile(path.join(runDir, "report.json"), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
    if (sessionFailureVisible || apiErrors.length) {
      throw new Error(`Page-agent sidebar validation failed. See ${path.join(runDir, "report.json")}`);
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : error);
  process.exitCode = 1;
});
