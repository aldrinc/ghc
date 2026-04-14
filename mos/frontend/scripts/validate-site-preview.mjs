import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const scriptPath = fileURLToPath(import.meta.url);
const scriptDir = path.dirname(scriptPath);
const frontendDir = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(frontendDir, "..", "..");
const authEnvPath = path.join(repoRoot, ".env.mos-test-auth");
const localPlaywrightHome = path.join(repoRoot, ".local", "playwright-home");
const authStatePath = path.join(localPlaywrightHome, "mos-auth-state.json");
const validationRoot = path.join(localPlaywrightHome, "preview-validation");

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

function timestampSlug() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function compactUrl(value) {
  try {
    const url = new URL(value);
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return value;
  }
}

async function saveScreenshot(page, filePath) {
  await page.screenshot({ path: filePath, fullPage: true });
}

async function openPreview(page, previewUrl) {
  await page.goto(previewUrl, { waitUntil: "networkidle", timeout: 120000 });
}

async function maybeSignIn(page, { email, password, baseUrl, previewUrl }) {
  await openPreview(page, previewUrl);
  const needsSignIn =
    page.url().includes("/sign-in") || (await page.locator("#identifier-field").count()) > 0;
  if (!needsSignIn) return false;

  await page.goto(new URL("/sign-in", baseUrl).toString(), {
    waitUntil: "networkidle",
    timeout: 120000,
  });
  await page.locator("#identifier-field").fill(email);
  await page.locator("#password-field").fill(password);
  await page.getByRole("button", { name: /^Continue$/ }).click();
  await page.waitForFunction(() => !window.location.pathname.includes("/sign-in"), {
    timeout: 120000,
  });
  await page.context().storageState({ path: authStatePath });
  await openPreview(page, previewUrl);
  if (page.url().includes("/sign-in")) {
    throw new Error("MOS sign-in did not complete successfully.");
  }
  return true;
}

function allFrames(page) {
  return [page.mainFrame(), ...page.frames().filter((frame) => frame !== page.mainFrame())];
}

async function findFrameByText(page, regex) {
  for (const frame of allFrames(page)) {
    try {
      const locator = frame.getByText(regex).first();
      if ((await locator.count()) > 0) {
        return frame;
      }
    } catch {
      // ignore detached/unsupported frames
    }
  }
  return null;
}

async function findAction(page, regex, { frameText } = {}) {
  const frameCandidates = frameText
    ? [await findFrameByText(page, frameText)].filter(Boolean)
    : allFrames(page);
  for (const frame of frameCandidates) {
    for (const role of ["button", "link"]) {
      try {
        const locator = frame.getByRole(role, { name: regex }).first();
        if ((await locator.count()) > 0) {
          return locator;
        }
      } catch {
        // continue
      }
    }
  }
  return null;
}

async function findActionInFrame(frame, regex) {
  if (!frame) return null;
  for (const role of ["button", "link"]) {
    try {
      const locator = frame.getByRole(role, { name: regex }).first();
      if ((await locator.count()) > 0) {
        return locator;
      }
    } catch {
      // continue
    }
  }
  return null;
}

async function findPurchaseSectionFrame(page, selector) {
  const section = page.locator(selector).first();
  if ((await section.count()) === 0) {
    return null;
  }
  const iframeHandle = await section.locator("iframe").first().elementHandle();
  if (!iframeHandle) {
    return null;
  }
  return iframeHandle.contentFrame();
}

async function waitForPath(page, expectedPathFragment, timeout = 20000) {
  await page.waitForFunction(
    (fragment) => window.location.pathname.includes(fragment),
    expectedPathFragment,
    { timeout },
  );
}

async function collectToastText(page) {
  const selectors = [
    "[role='alert']",
    "[role='status']",
    "[data-sonner-toast]",
    "[data-toast]",
  ];
  const messages = [];
  for (const selector of selectors) {
    const locator = page.locator(selector);
    const count = await locator.count();
    for (let index = 0; index < count; index += 1) {
      const text = (await locator.nth(index).innerText().catch(() => "")).trim();
      if (text) messages.push(text);
    }
  }
  return Array.from(new Set(messages));
}

async function collectRuntimeErrors(page) {
  const patterns = [
    /Medusa runtime is not configured/i,
    /No Medusa product could be loaded/i,
    /No Medusa variant title matches/i,
    /Imported section target .* was not found/i,
  ];
  const matches = [];
  for (const frame of allFrames(page)) {
    const text = (await frame.locator("body").innerText().catch(() => "")).trim();
    if (!text) continue;
    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (!match) continue;
      matches.push({
        frameUrl: compactUrl(frame.url()),
        message: match[0],
      });
    }
  }
  return matches;
}

async function assertNoRuntimeErrors(page) {
  const matches = await collectRuntimeErrors(page);
  if (matches.length === 0) return;
  const rendered = matches.map((entry) => `${entry.message} [${entry.frameUrl}]`).join("; ");
  throw new Error(`Preview runtime reported blocking errors: ${rendered}`);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const siteId = (args["site-id"] || "").trim();
  if (!siteId) {
    throw new Error("Missing required --site-id.");
  }

  const baseUrl = (args["base-url"] || "http://localhost:5275").trim().replace(/\/+$/, "");
  const countryCode = (args["country"] || "us").trim();
  const previewPath = `/workspaces/sites/${siteId}/preview/${countryCode}`;
  const previewUrl = `${baseUrl}${previewPath}`;

  const env = {
    ...(await readEnvFile(authEnvPath)),
    ...process.env,
  };
  const email = (env.MOS_TEST_EMAIL || "").trim();
  const password = (env.MOS_TEST_PASSWORD || "").trim();
  if (!email || !password) {
    throw new Error(`Missing MOS_TEST_EMAIL or MOS_TEST_PASSWORD in ${authEnvPath}.`);
  }

  await fs.mkdir(validationRoot, { recursive: true });
  const runDir = path.join(validationRoot, `${siteId}-${timestampSlug()}`);
  await fs.mkdir(runDir, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1600 },
    ignoreHTTPSErrors: true,
    storageState: (await pathExists(authStatePath)) ? authStatePath : undefined,
  });
  const page = await context.newPage();

  const report = {
    siteId,
    previewUrl,
    signedIn: false,
    screenshots: {},
    checks: [],
  };

  try {
    report.signedIn = await maybeSignIn(page, { email, password, baseUrl, previewUrl });

    await saveScreenshot(page, path.join(runDir, "01-preview-home.png"));
    report.screenshots.home = path.join(runDir, "01-preview-home.png");

    if (page.url().includes("/sign-in")) {
      throw new Error("Preview still redirects to sign-in after authentication.");
    }
    report.checks.push({
      name: "authenticated preview load",
      status: "passed",
      url: compactUrl(page.url()),
    });
    await assertNoRuntimeErrors(page);
    report.checks.push({
      name: "preview runtime health",
      status: "passed",
      url: compactUrl(page.url()),
    });

    const targetSelector = "#product-purchase-section, [data-imported-section-id='product-purchase-section']";
    const heroCta =
      (await findAction(page, /restore clarity/i)) ||
      (await findAction(page, /recover your clarity/i)) ||
      (await findAction(page, /start the protocol/i)) ||
      (await findAction(page, /start the brain clarity protocol/i)) ||
      (await findAction(page, /shop now/i));
    if (!heroCta) {
      throw new Error(
        'Could not find an Ember purchase CTA ("RESTORE CLARITY", "RECOVER YOUR CLARITY", "START THE PROTOCOL", "START THE BRAIN CLARITY PROTOCOL", or "SHOP NOW").',
      );
    }
    await heroCta.click();
    await page.waitForFunction(
      (selector) => {
        const target = document.querySelector(selector);
        if (!(target instanceof HTMLElement)) return false;
        return Math.abs(target.getBoundingClientRect().top) < 400;
      },
      targetSelector,
      { timeout: 20000 },
    );
    await saveScreenshot(page, path.join(runDir, "02-after-hero-cta.png"));
    report.screenshots.afterHeroCta = path.join(runDir, "02-after-hero-cta.png");
    report.checks.push({
      name: "hero CTA scrolls to purchase section",
      status: "passed",
      url: compactUrl(page.url()),
    });

    await openPreview(page, previewUrl);
    const contactLink = (await findAction(page, /contact us/i)) || (await findAction(page, /contact support/i));
    if (!contactLink) {
      throw new Error('Could not find the footer contact link ("CONTACT US" / "Contact Support").');
    }
    await contactLink.click();
    await waitForPath(page, `/workspaces/sites/${siteId}/preview/${countryCode}/policies/contact-support`);
    await saveScreenshot(page, path.join(runDir, "03-contact-support.png"));
    report.screenshots.contactSupport = path.join(runDir, "03-contact-support.png");
    report.checks.push({
      name: "footer contact support route",
      status: "passed",
      url: compactUrl(page.url()),
    });

    await openPreview(page, previewUrl);
    const loginLink =
      (await findAction(page, /^account$/i, { frameText: /contact support/i })) ||
      (await findAction(page, /account login/i, { frameText: /contact support/i })) ||
      (await findAction(page, /account login/i)) ||
      (await findAction(page, /^account$/i)) ||
      (await findAction(page, /^log in$/i));
    if (!loginLink) {
      throw new Error('Could not find the footer account link ("ACCOUNT LOGIN", "Account", or "Log In").');
    }
    await loginLink.click();
    await waitForPath(page, `/workspaces/sites/${siteId}/preview/${countryCode}/account`);
    await saveScreenshot(page, path.join(runDir, "04-account.png"));
    report.screenshots.account = path.join(runDir, "04-account.png");
    report.checks.push({
      name: "footer account route",
      status: "passed",
      url: compactUrl(page.url()),
    });

    await openPreview(page, previewUrl);
    await assertNoRuntimeErrors(page);
    const purchaseFrame = await findPurchaseSectionFrame(page, targetSelector);
    if (!purchaseFrame) {
      throw new Error("Could not locate the product-purchase section iframe.");
    }
    const purchaseButton =
      (await findActionInFrame(purchaseFrame, /add to cart/i)) ||
      (await findActionInFrame(purchaseFrame, /start clarity protocol/i)) ||
      (await findActionInFrame(purchaseFrame, /start the brain clarity protocol/i)) ||
      (await findActionInFrame(purchaseFrame, /restore clarity now/i));
    if (!purchaseButton) {
      throw new Error(
        'Could not find the purchase button in the product-purchase section ("ADD TO CART", "Start Clarity Protocol", "Start the Brain Clarity Protocol", or "Restore Clarity Now").',
      );
    }
    await purchaseButton.click();
    try {
      await waitForPath(page, `/workspaces/sites/${siteId}/preview/${countryCode}/checkout`, 30000);
      await saveScreenshot(page, path.join(runDir, "05-checkout.png"));
      report.screenshots.checkout = path.join(runDir, "05-checkout.png");
      report.checks.push({
        name: "purchase button reaches checkout",
        status: "passed",
        url: compactUrl(page.url()),
      });
    } catch (error) {
      const toasts = await collectToastText(page);
      const runtimeErrors = await collectRuntimeErrors(page);
      await saveScreenshot(page, path.join(runDir, "05-purchase-failure.png"));
      report.screenshots.purchaseFailure = path.join(runDir, "05-purchase-failure.png");
      report.checks.push({
        name: "purchase button reaches checkout",
        status: "failed",
        url: compactUrl(page.url()),
        toasts,
        runtimeErrors,
        error: error instanceof Error ? error.message : String(error),
      });
      report.failed = true;
    }
  } finally {
    const reportPath = path.join(runDir, "report.json");
    await fs.writeFile(reportPath, JSON.stringify(report, null, 2));
    console.log(JSON.stringify({ reportPath, ...report }, null, 2));
    await context.storageState({ path: authStatePath });
    await browser.close();
  }

  const failedChecks = report.checks.filter((check) => check.status === "failed");
  if (failedChecks.length > 0) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
});
