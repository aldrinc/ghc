import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const SOURCE_MANIFEST_PATH = path.join(
  ROOT,
  "outputs/tenor-walk-away-trt-campaign-2026-05-02/full-launch-manifest.json",
);
const OUT_DIR = path.join(ROOT, "outputs/tenor-walk-away-trt-remove-product-only-2026-05-03");
const MANIFEST_PATH = path.join(OUT_DIR, "manifest.json");
const GENERATED_DIR = path.join(OUT_DIR, "generated");
const REVIEW_DIR = "/Users/aldrinclement/Downloads/tenor-walk-away-trt-remove-product-only-review-2026-05-03";
const REVIEW_GENERATED_DIR = path.join(REVIEW_DIR, "generated");
const AUTH_FILE = path.join(ROOT, ".env.mos-test-auth");

const API_BASE = "https://api.moshq.app";
const CLERK_BASE = "https://immune-turtle-79.clerk.accounts.dev/v1";
const CLERK_QUERY = "__clerk_api_version=2025-11-10&_clerk_js_version=5.125.10";
const ORIGIN_HEADERS = {
  Origin: "https://moshq.app",
  Referer: "https://moshq.app/",
};

const NO_PRODUCT_VISUAL_REQUIREMENT = [
  "Approved visual requirement for this campaign: remove the product and nothing else.",
  "Do not show any product, product packaging, packshot, supplement bottle, pouch, jar, tub, box, pack, product label, capsule, gummy, pill, or fake physical product anywhere in the image.",
  "Do not replace the removed product with a new object, prop, document, report, book, notebook, badge, icon, chart, lab result, illustration, or visual proxy.",
  "Preserve the original source swipe composition, text, people, background, colors, layout, and style; only remove the product object if one exists.",
].join(" ");

const PRODUCT_NAME_FOR_NO_PRODUCT_MODE = "Tenor";
const FORCE_KEYS = new Set(
  (process.env.FORCE_KEYS || "")
    .split(",")
    .map((key) => key.trim())
    .filter(Boolean),
);

const SOURCE_SPECIFIC_VISUAL_REQUIREMENTS = {};

let cachedToken = null;

function loadAuthEnv() {
  const env = {};
  for (const line of readFileSync(AUTH_FILE, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const idx = trimmed.indexOf("=");
    if (idx === -1) continue;
    env[trimmed.slice(0, idx)] = trimmed.slice(idx + 1);
  }
  if (!env.MOS_TEST_EMAIL || !env.MOS_TEST_PASSWORD) {
    throw new Error(`Missing MOS_TEST_EMAIL or MOS_TEST_PASSWORD in ${AUTH_FILE}`);
  }
  return env;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  if (!response.ok) {
    const error = new Error(`${options.method || "GET"} ${url} failed (${response.status}): ${text.slice(0, 4000)}`);
    error.status = response.status;
    error.body = text;
    throw error;
  }
  return text ? JSON.parse(text) : null;
}

async function getBackendToken() {
  const auth = loadAuthEnv();
  const dev = await requestJson(`${CLERK_BASE}/dev_browser?${CLERK_QUERY}`, {
    method: "POST",
    headers: ORIGIN_HEADERS,
  });
  const dbJwt = dev.id;
  const signIn = await requestJson(`${CLERK_BASE}/client/sign_ins?${CLERK_QUERY}&__clerk_db_jwt=${dbJwt}`, {
    method: "POST",
    headers: {
      ...ORIGIN_HEADERS,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({
      identifier: auth.MOS_TEST_EMAIL,
      password: auth.MOS_TEST_PASSWORD,
    }),
  });
  const sessionId = signIn?.response?.created_session_id;
  if (!sessionId) throw new Error("Clerk sign-in did not return created_session_id.");
  const token = await requestJson(
    `${CLERK_BASE}/client/sessions/${sessionId}/tokens/backend?${CLERK_QUERY}&__clerk_db_jwt=${dbJwt}`,
    { method: "POST", headers: ORIGIN_HEADERS },
  );
  if (!token?.jwt) throw new Error("Clerk backend token response did not include jwt.");
  cachedToken = token.jwt;
  return token.jwt;
}

async function authed(apiPath, options = {}) {
  const token = cachedToken || (await getBackendToken());
  try {
    return await requestJson(`${API_BASE}${apiPath}`, {
      ...options,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(options.headers || {}),
      },
    });
  } catch (error) {
    if (error.status !== 401) throw error;
    cachedToken = null;
    const refreshed = await getBackendToken();
    return requestJson(`${API_BASE}${apiPath}`, {
      ...options,
      headers: {
        Authorization: `Bearer ${refreshed}`,
        ...(options.headers || {}),
      },
    });
  }
}

function ensureDirs() {
  mkdirSync(OUT_DIR, { recursive: true });
  mkdirSync(GENERATED_DIR, { recursive: true });
  mkdirSync(REVIEW_GENERATED_DIR, { recursive: true });
}

function readSourceManifest() {
  const manifest = JSON.parse(readFileSync(SOURCE_MANIFEST_PATH, "utf8"));
  if (!Array.isArray(manifest.outputs) || manifest.outputs.length !== 30) {
    throw new Error(`Expected 30 outputs in ${SOURCE_MANIFEST_PATH}`);
  }
  return manifest;
}

function readManifest(sourceManifest) {
  if (existsSync(MANIFEST_PATH)) {
    return JSON.parse(readFileSync(MANIFEST_PATH, "utf8"));
  }
  return {
    createdAt: new Date().toISOString(),
    reason: "No-product visual regeneration for Tenor Walk Away From TRT review.",
    sourceManifestPath: SOURCE_MANIFEST_PATH,
    outputDir: OUT_DIR,
    generatedDir: GENERATED_DIR,
    reviewDir: REVIEW_DIR,
    campaignId: sourceManifest.campaignId,
    campaignName: sourceManifest.campaignName,
    clientId: sourceManifest.outputs[0]?.payload?.clientId,
    productId: sourceManifest.outputs[0]?.payload?.productId,
    assetBriefId: sourceManifest.outputs[0]?.payload?.assetBriefId,
    destinationContext: sourceManifest.destinationContext,
    noProductVisualRequirement: NO_PRODUCT_VISUAL_REQUIREMENT,
    outputs: [],
  };
}

function writeManifest(manifest) {
  writeFileSync(MANIFEST_PATH, JSON.stringify({ ...manifest, updatedAt: new Date().toISOString() }, null, 2) + "\n");
}

function runMarker(key) {
  return `tenor-walk-away-trt-no-product-${key}-${Date.now()}`;
}

function buildSwipeAngle({ awarenessLevel, destinationContext, key }) {
  const sourceSpecificRequirement = SOURCE_SPECIFIC_VISUAL_REQUIREMENTS[key];
  return [
    `Awareness level: ${awarenessLevel}`,
    "",
    "Downstream destination context:",
    `Headline: ${destinationContext.headline}`,
    `Subheadline: ${destinationContext.subheadline}`,
    `Primary problem: ${destinationContext.primaryProblem}`,
    `Promise: ${destinationContext.promise}`,
    `Mechanism disclosure level: ${destinationContext.mechanismDisclosureLevel}`,
    `Proof type: ${destinationContext.proofType}`,
    `CTA / urgency: ${destinationContext.ctaUrgency}`,
    `Compliance posture: ${destinationContext.compliancePosture}`,
    `Asset stage: ${destinationContext.assetStage}`,
    `Visual emphasis: ${destinationContext.visualEmphasis}`,
    "",
    "Approved visual requirement:",
    NO_PRODUCT_VISUAL_REQUIREMENT,
    sourceSpecificRequirement ? `Source-specific visual requirement: ${sourceSpecificRequirement}` : null,
    "",
    `Run marker: ${runMarker(key)}.`,
  ]
    .filter((part) => part !== null)
    .join("\n");
}

async function waitForWorkflow(workflowRunId, timeoutMs = 35 * 60 * 1000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const detail = await authed(`/workflows/${encodeURIComponent(workflowRunId)}`);
    const status = detail?.run?.status;
    if (status === "completed") return detail;
    if (status === "failed" || status === "cancelled") {
      const errors = (detail?.logs || []).map((log) => log.error).filter(Boolean).join("\n");
      throw new Error(`Workflow ${workflowRunId} ended with ${status}: ${errors || "no error detail"}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 10000));
  }
  throw new Error(`Timed out waiting for workflow ${workflowRunId}`);
}

function extractAssetId(workflowDetail) {
  for (const log of workflowDetail.logs || []) {
    if (log.step !== "swipe_image_ad" || log.status !== "succeeded") continue;
    const ids = log.payload_out?.asset_ids || [];
    if (ids.length !== 1) throw new Error(`Expected one asset id, got ${ids.length}`);
    return { assetId: ids[0], payloadOut: log.payload_out };
  }
  throw new Error("Completed workflow did not include a succeeded swipe_image_ad log.");
}

async function getCampaignAssets(campaignId, productId) {
  return authed(
    `/assets?campaignId=${encodeURIComponent(campaignId)}&productId=${encodeURIComponent(productId)}&assetKind=image`,
  );
}

async function resolveAsset({ campaignId, productId, assetId }) {
  const rows = await getCampaignAssets(campaignId, productId);
  const row = rows.find((asset) => asset.id === assetId);
  if (!row?.public_id) throw new Error(`Could not resolve generated public_id for asset ${assetId}`);
  return row;
}

function downloadPublicAsset(publicId, outputPath) {
  execFileSync("curl", ["-sS", "-L", `${API_BASE}/public/assets/${publicId}`, "-o", outputPath], {
    stdio: "inherit",
  });
}

function auditPromptText(text) {
  const terms = [
    "supplement",
    "pouch",
    "container",
    "packaging",
    "bottle",
    "jar",
    "tub",
    "box",
    "packshot",
    "product label",
    "capsule",
    "gummy",
    "pill",
    "physical packaged product",
  ];
  const lower = String(text || "").toLowerCase();
  return terms.filter((term) => lower.includes(term));
}

async function generate() {
  ensureDirs();
  const sourceManifest = readSourceManifest();
  const manifest = readManifest(sourceManifest);
  await getBackendToken();
  const campaign = await authed(`/campaigns/${encodeURIComponent(sourceManifest.campaignId)}`);
  if (sourceManifest.campaignName && campaign.name !== sourceManifest.campaignName) {
    throw new Error(`Unexpected campaign name for ${sourceManifest.campaignId}: ${campaign.name}`);
  }

  const completed = new Set((manifest.outputs || []).map((output) => output.key));
  if (FORCE_KEYS.size) {
    manifest.outputs = (manifest.outputs || []).filter((output) => !FORCE_KEYS.has(output.key));
    for (const key of FORCE_KEYS) {
      completed.delete(key);
    }
  }
  for (const sourceOutput of sourceManifest.outputs) {
    if (completed.has(sourceOutput.key)) {
      console.log(`Skipping ${sourceOutput.key}; already regenerated.`);
      continue;
    }

    const payload = {
      clientId: sourceOutput.payload.clientId,
      productId: sourceOutput.payload.productId,
      campaignId: sourceOutput.payload.campaignId,
      assetBriefId: sourceOutput.payload.assetBriefId,
      requirementIndex: sourceOutput.payload.requirementIndex,
      companySwipeId: sourceOutput.source.companySwipeId,
      swipeRequiresProductImage: false,
      swipeContextMode: "minimal",
      swipeBrandName: "Tenor",
      swipeProductName: PRODUCT_NAME_FOR_NO_PRODUCT_MODE,
      swipeHook: sourceOutput.awarenessLevel,
      swipeAngle: buildSwipeAngle({
        awarenessLevel: sourceOutput.awarenessLevel,
        destinationContext: sourceManifest.destinationContext,
        key: sourceOutput.key,
      }),
      aspectRatio: sourceOutput.payload.aspectRatio || "1:1",
      count: 1,
    };

    console.log(`Generating ${sourceOutput.key} from ${sourceOutput.source.sourceSwipeTitle}`);
    const started = await authed("/swipes/generate-image-ad", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const detail = await waitForWorkflow(started.workflow_run_id);
    const workflowPath = path.join(OUT_DIR, `workflow-${sourceOutput.key}.json`);
    writeFileSync(workflowPath, JSON.stringify(detail, null, 2) + "\n");

    const { assetId, payloadOut } = extractAssetId(detail);
    const asset = await resolveAsset({
      campaignId: sourceOutput.payload.campaignId,
      productId: sourceOutput.payload.productId,
      assetId,
    });
    const localPath = path.join(GENERATED_DIR, `${sourceOutput.key}.jpg`);
    const reviewPath = path.join(REVIEW_GENERATED_DIR, `${sourceOutput.key}.jpg`);
    downloadPublicAsset(asset.public_id, localPath);
    copyFileSync(localPath, reviewPath);

    const promptRaw = asset.ai_metadata?.swipePromptExtractedRaw || "";
    const promptProductTermHits = auditPromptText(promptRaw);
    const regenerated = {
      key: sourceOutput.key,
      awarenessLevel: sourceOutput.awarenessLevel,
      source: sourceOutput.source,
      payload,
      workflow: {
        workflow_run_id: started.workflow_run_id,
        temporal_workflow_id: started.temporal_workflow_id,
      },
      result: {
        assetId,
        publicId: asset.public_id,
        publicUrl: `${API_BASE}/public/assets/${asset.public_id}`,
        localPath,
        reviewPath,
        workflowPayloadOut: payloadOut,
        workflowDetailPath: workflowPath,
      },
      promptAudit: {
        productTermHits: promptProductTermHits,
        promptExcerpt: promptRaw.slice(0, 500),
      },
    };
    manifest.outputs.push(regenerated);
    writeManifest(manifest);
  }
  writeManifest(manifest);
  console.log(JSON.stringify({ manifestPath: MANIFEST_PATH, reviewDir: REVIEW_DIR, count: manifest.outputs.length }, null, 2));
}

async function main() {
  const command = process.argv[2] || "generate";
  if (command !== "generate") {
    throw new Error(`Unsupported command: ${command}`);
  }
  await generate();
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exitCode = 1;
});
