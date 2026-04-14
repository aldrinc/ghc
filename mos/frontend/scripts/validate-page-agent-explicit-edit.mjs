import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const scriptPath = fileURLToPath(import.meta.url);
const repoRoot = path.resolve(path.dirname(scriptPath), "..", "..", "..");
const authEnvPath = path.join(repoRoot, ".env.mos-test-auth");
const localPlaywrightHome = path.join(repoRoot, ".local", "playwright-home");
const authStatePath = path.join(localPlaywrightHome, "mos-auth-state.json");
const validationRoot = path.join(localPlaywrightHome, "page-agent-explicit-edit");

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
  await page.waitForSelector('textarea[placeholder="Tell Hermes what to change on this page."]', {
    timeout: 120000,
  });
  await page.waitForSelector('button:has-text("Send")', { timeout: 120000 });
  await page.waitForSelector('[data-page-agent-live-activity="true"]', { timeout: 120000 });
}

async function maybeResetSession(page) {
  const resetButton = page.getByRole("button", { name: /Start fresh Hermes session/i });
  if (!(await resetButton.isVisible().catch(() => false))) return false;
  await resetButton.click();
  await page.waitForSelector("text=Starting a fresh Hermes session for this page.", {
    timeout: 120000,
  });
  await page.waitForSelector("text=Starting a fresh Hermes session for this page.", {
    state: "hidden",
    timeout: 120000,
  });
  return true;
}

async function sendPrompt(page, prompt) {
  await page.getByPlaceholder("Tell Hermes what to change on this page.").fill(prompt);
  await page.getByRole("button", { name: /^Send$/ }).click();
}

async function assistantMessageCount(page) {
  return page.locator('[data-page-agent-message-role="assistant"]').count();
}

function normalizeTextForMatch(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function allFrames(page) {
  return [page.mainFrame(), ...page.frames().filter((frame) => frame !== page.mainFrame())];
}

async function pageTextMatches(page, needle) {
  const normalizedNeedle = normalizeTextForMatch(needle);
  if (!normalizedNeedle) return true;

  for (const frame of allFrames(page)) {
    const bodyText = normalizeTextForMatch(await frame.locator("body").innerText().catch(() => ""));
    if (bodyText.includes(normalizedNeedle)) {
      return true;
    }
  }
  return false;
}

async function assertPreviewContentState(page, { expectedText, forbiddenText }) {
  const previewContent = page.getByTestId("site-preview-content");
  await previewContent.waitFor({ timeout: 120000 });

  const deadline = Date.now() + 120000;
  while (Date.now() < deadline) {
    if (await pageTextMatches(page, expectedText)) {
      break;
    }
    await page.waitForTimeout(1000);
  }
  if (!(await pageTextMatches(page, expectedText))) {
    throw new Error(`Timed out waiting for preview text: ${expectedText}`);
  }

  if (!forbiddenText) {
    return;
  }

  while (Date.now() < deadline) {
    if (!(await pageTextMatches(page, forbiddenText))) {
      return;
    }
    await page.waitForTimeout(1000);
  }

  throw new Error(`Timed out waiting for preview text to disappear: ${forbiddenText}`);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const siteId = (args["site-id"] || "").trim();
  const pageId = (args["page-id"] || "").trim();
  const expectedText = (args["expected-text"] || "").trim();
  const forbiddenText = (args["forbidden-text"] || "").trim();
  const prompt = (args["prompt"] || "").trim();
  const baseUrl = (args["base-url"] || "http://127.0.0.1:5275").trim().replace(/\/+$/, "");
  if (!siteId || !pageId || !expectedText || !prompt) {
    throw new Error("Missing required --site-id, --page-id, --prompt, or --expected-text.");
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
    await maybeResetSession(page);
    const initialAssistantCount = await assistantMessageCount(page);
    await sendPrompt(page, prompt);
    await page.waitForFunction(
      (previousCount) => {
        const assistantMessages = document.querySelectorAll('[data-page-agent-message-role="assistant"]').length;
        return assistantMessages > previousCount;
      },
      initialAssistantCount,
      { timeout: 600000 },
    );
    await page.reload({ waitUntil: "networkidle", timeout: 120000 });
    await ensureAgentSidebar(page);
    await page.screenshot({ path: path.join(runDir, "editor-after-edit.png"), fullPage: true });

    await page.goto(previewUrl, { waitUntil: "networkidle", timeout: 120000 });
    await assertPreviewContentState(page, { expectedText, forbiddenText });
    await page.screenshot({ path: path.join(runDir, "preview-after-edit.png"), fullPage: true });

    const sessionFailureVisible = await page.getByText("Current session failed").isVisible().catch(() => false);
    const report = {
      siteId,
      pageId,
      editorUrl,
      previewUrl,
      signedIn,
      expectedText,
      forbiddenText,
      prompt,
      outputDir: runDir,
      sessionFailureVisible,
      apiErrors,
    };
    await fs.writeFile(path.join(runDir, "report.json"), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
    if (sessionFailureVisible || apiErrors.length) {
      throw new Error(`Explicit page-agent validation failed. See ${path.join(runDir, "report.json")}`);
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : error);
  process.exitCode = 1;
});
