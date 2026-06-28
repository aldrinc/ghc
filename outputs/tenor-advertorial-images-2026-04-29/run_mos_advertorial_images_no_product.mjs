import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const OUT_DIR = path.join(ROOT, "outputs/tenor-advertorial-images-2026-04-29");
const SOURCE_DIR = path.join(OUT_DIR, "source-no-product");
const GENERATED_DIR = path.join(OUT_DIR, "generated-no-product");
const AUTH_FILE = path.join(ROOT, ".env.mos-test-auth");

const API_BASE = "https://api.moshq.app";
const CLERK_BASE = "https://immune-turtle-79.clerk.accounts.dev/v1";
const CLERK_QUERY = "__clerk_api_version=2025-11-10&_clerk_js_version=5.125.10";
const ORIGIN_HEADERS = { Origin: "https://moshq.app", Referer: "https://moshq.app/" };

const CAMPAIGN_ID = "a5af5e49-1eb8-4fb4-8029-d3d2006114e9";
const CLIENT_ID = "70124684-505f-48af-a25c-5f7a79601fa0";
const PRODUCT_ID = "8b89a76d-069c-41a6-be38-b7e4f4483460";
const STAGING_FUNNEL_ID = "be65d76e-ced9-4948-9465-18723c8446fd";
const STAGING_PAGE_ID = "ab3102f4-a179-410a-9eb0-66aa3020cafc";

const noProduct =
  "Hard compliance constraint: do not show the Tenor product or any supplement product. No bottle, jar, box, label, supplement facts panel, capsules, pills, powders, scoops, sachets, packaging, branded object, logo, or readable product text. This image must be editorial context only, not a product visual.";
const visualSystem =
  "Premium editorial health and longevity photography for men over 40. Warm off-white, stone, black, graphite, and muted bronze accents. Natural window light, clean shadows, restrained contrast, article-native composition. Photorealistic only. No fake UI, no charts, no doctors, no hospitals, no needles, no shirtless gym tropes, no before/after imagery.";

const jobs = [
  {
    key: "01-hero-normal-labs",
    sourceFile: "01-hero-normal-labs-source.jpg",
    aspectRatio: "21:9",
    hook: "Normal labs, different person",
    angle:
      `${noProduct} ${visualSystem} Wide advertorial hero image. Create a quiet, premium editorial scene: soft morning light on a warm stone surface, an out-of-focus lab report or paper cue with no readable numbers, and a subtle driveway / early morning atmosphere suggesting a 47-year-old man processing normal bloodwork but not feeling normal. No product objects of any kind.`,
  },
  {
    key: "02-mechanism-actives",
    sourceFile: "02-mechanism-actives-source.jpg",
    aspectRatio: "4:3",
    hook: "The lock and key mechanism",
    angle:
      `${noProduct} ${visualSystem} Inline figure for the androgen receptor mechanism section. Create a sophisticated scientific still life using abstract lock-and-key receptor shapes, mineral stones, botanical elements, and warm lab-style surfaces. It should feel evidence-based but not clinical. No molecular labels, no readable diagrams, no product objects.`,
  },
  {
    key: "03-formulation-context",
    sourceFile: "03-product-kit-label-source.jpg",
    aspectRatio: "4:3",
    hook: "The restoration protocol",
    angle:
      `${noProduct} ${visualSystem} Inline image for the restoration protocol section. Create a premium editorial formulation workspace: botanical roots, mineral stones, a clean notebook with unreadable marks, and warm natural light. It should suggest disclosed actives and scientific formulation without showing any supplement product, capsules, bottle, label, or packaging.`,
  },
  {
    key: "04-lifestyle-recovery",
    sourceFile: "04-lifestyle-recovery-source.jpg",
    aspectRatio: "4:3",
    hook: "Daily energy and recovery",
    angle:
      `${noProduct} ${visualSystem} Inline lifestyle figure. Photorealistic scene of a realistic man in his early 50s near a window after a calm morning workout or weekend activity, relaxed posture, grounded expression, premium neutral interior, subtle bronze accent object. No supplement product, no gym aggression, no medical claim, no text.`,
  },
  {
    key: "05-morning-routine",
    sourceFile: "05-two-capsule-protocol-source.jpg",
    aspectRatio: "4:3",
    hook: "Morning routine",
    angle:
      `${noProduct} ${visualSystem} Inline daily routine figure for the getting-started section. Photorealistic morning still life with a water glass, notebook, keys, and warm stone counter. It should imply a simple morning protocol without showing capsules, pills, bottle, label, packaging, powders, scoops, or any product.`,
  },
  {
    key: "06-volume-signal",
    sourceFile: "06-volume-signal-source.jpg",
    aspectRatio: "4:3",
    hook: "The volume signal",
    angle:
      `${noProduct} ${visualSystem} Inline proof/volume-signal figure. Create a premium editorial quality-control workspace: anonymous paperwork with no readable text, subtle checkmark-like process cue, mineral or stone objects, clean daylight. It should imply testing, scale, and rigor without any product, label, certification logo, badge, or packaging.`,
  },
];

let cachedToken = null;

function loadAuthEnv() {
  const env = {};
  for (const line of readFileSync(AUTH_FILE, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const idx = trimmed.indexOf("=");
    if (idx !== -1) env[trimmed.slice(0, idx)] = trimmed.slice(idx + 1);
  }
  if (!env.MOS_TEST_EMAIL || !env.MOS_TEST_PASSWORD) throw new Error("Missing MOS test auth credentials");
  return env;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, { ...options, headers: { Accept: "application/json", ...(options.headers || {}) } });
  const text = await response.text();
  if (!response.ok) {
    const error = new Error(`${options.method || "GET"} ${url} failed (${response.status}): ${text.slice(0, 1000)}`);
    error.status = response.status;
    throw error;
  }
  return text ? JSON.parse(text) : null;
}

async function getBackendToken() {
  const auth = loadAuthEnv();
  const dev = await requestJson(`${CLERK_BASE}/dev_browser?${CLERK_QUERY}`, { method: "POST", headers: ORIGIN_HEADERS });
  const dbJwt = dev.id;
  const signIn = await requestJson(`${CLERK_BASE}/client/sign_ins?${CLERK_QUERY}&__clerk_db_jwt=${dbJwt}`, {
    method: "POST",
    headers: { ...ORIGIN_HEADERS, "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ identifier: auth.MOS_TEST_EMAIL, password: auth.MOS_TEST_PASSWORD }),
  });
  const sessionId = signIn?.response?.created_session_id;
  if (!sessionId) throw new Error("Clerk sign-in did not return created_session_id");
  const token = await requestJson(
    `${CLERK_BASE}/client/sessions/${sessionId}/tokens/backend?${CLERK_QUERY}&__clerk_db_jwt=${dbJwt}`,
    { method: "POST", headers: ORIGIN_HEADERS },
  );
  if (!token?.jwt) throw new Error("No backend JWT");
  cachedToken = token.jwt;
  return cachedToken;
}

async function authed(apiPath, options = {}) {
  const token = cachedToken || (await getBackendToken());
  try {
    return await requestJson(`${API_BASE}${apiPath}`, {
      ...options,
      headers: { Authorization: `Bearer ${token}`, ...(options.headers || {}) },
    });
  } catch (error) {
    if (error.status !== 401) throw error;
    cachedToken = null;
    const refreshed = await getBackendToken();
    return requestJson(`${API_BASE}${apiPath}`, {
      ...options,
      headers: { Authorization: `Bearer ${refreshed}`, ...(options.headers || {}) },
    });
  }
}

async function uploadFiles(files) {
  const token = cachedToken || (await getBackendToken());
  const form = new FormData();
  for (const filePath of files) {
    const bytes = readFileSync(filePath);
    form.append("files", new Blob([bytes], { type: "image/jpeg" }), path.basename(filePath));
  }
  return requestJson(`${API_BASE}/funnels/${STAGING_FUNNEL_ID}/pages/${STAGING_PAGE_ID}/ai/attachments`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
}

async function waitForWorkflow(id) {
  const started = Date.now();
  while (Date.now() - started < 25 * 60 * 1000) {
    const detail = await authed(`/workflows/${encodeURIComponent(id)}`);
    const status = detail?.run?.status;
    if (status === "completed") return detail;
    if (status === "failed" || status === "cancelled") {
      const errors = (detail?.logs || []).map((log) => log.error).filter(Boolean).join("\n");
      throw new Error(`Workflow ${id} ended with ${status}: ${errors || "no error detail"}`);
    }
    console.log(`Workflow ${id} is ${status}; waiting...`);
    await new Promise((resolve) => setTimeout(resolve, 10000));
  }
  throw new Error(`Timed out waiting for workflow ${id}`);
}

function extractAssetId(detail) {
  for (const log of detail.logs || []) {
    if (log.step !== "swipe_image_ad" || log.status !== "succeeded") continue;
    const ids = log.payload_out?.asset_ids || [];
    if (ids.length !== 1) throw new Error(`Expected one asset id, got ${ids.length}`);
    return { assetId: ids[0], payloadOut: log.payload_out };
  }
  throw new Error("No succeeded swipe_image_ad log found");
}

async function resolveAsset(assetId) {
  const rows = await authed(
    `/assets?campaignId=${encodeURIComponent(CAMPAIGN_ID)}&productId=${encodeURIComponent(PRODUCT_ID)}&assetKind=image`,
  );
  const asset = rows.find((row) => row.id === assetId);
  if (!asset?.public_id) throw new Error(`Could not resolve asset ${assetId}`);
  return asset;
}

async function main() {
  mkdirSync(GENERATED_DIR, { recursive: true });
  await getBackendToken();
  const sourcePaths = jobs.map((job) => path.join(SOURCE_DIR, job.sourceFile));
  const upload = await uploadFiles(sourcePaths);
  const attachments = upload.attachments || [];
  if (attachments.length !== jobs.length) throw new Error(`Expected ${jobs.length} attachments, got ${attachments.length}`);
  console.log(`Staged ${attachments.length} no-product source images`);

  const started = [];
  for (let i = 0; i < jobs.length; i += 1) {
    const job = jobs[i];
    const payload = {
      clientId: CLIENT_ID,
      productId: PRODUCT_ID,
      campaignId: CAMPAIGN_ID,
      assetBriefId: "brief_editorial_mechanism_reveal",
      requirementIndex: 2,
      swipeImageUrl: `${API_BASE}${attachments[i].url}`,
      swipeRequiresProductImage: false,
      swipeContextMode: "minimal",
      swipeBrandName: "Tenor",
      swipeProductName: "Daily Drive Essentials",
      swipeHook: job.hook,
      swipeAngle: job.angle,
      aspectRatio: job.aspectRatio,
      count: 1,
    };
    const response = await authed("/swipes/generate-image-ad", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    console.log(`Started ${job.key}: workflow ${response.workflow_run_id}`);
    started.push({ job, attachment: attachments[i], payload, workflow: response });
  }

  const completed = [];
  for (const item of started) {
    console.log(`Waiting for ${item.job.key} (${item.workflow.workflow_run_id})`);
    const detail = await waitForWorkflow(item.workflow.workflow_run_id);
    const extracted = extractAssetId(detail);
    const asset = await resolveAsset(extracted.assetId);
    const ext = asset.content_type === "image/png" ? "png" : "jpg";
    const outputPath = path.join(GENERATED_DIR, `${item.job.key}.${ext}`);
    execFileSync("curl", ["-sS", "-L", `${API_BASE}/public/assets/${asset.public_id}`, "-o", outputPath], { stdio: "inherit" });
    console.log(`Downloaded ${item.job.key}: ${outputPath}`);
    completed.push({
      key: item.job.key,
      sourceFile: item.job.sourceFile,
      workflowRunId: item.workflow.workflow_run_id,
      assetId: asset.id,
      publicId: asset.public_id,
      publicUrl: `${API_BASE}/public/assets/${asset.public_id}`,
      localPath: outputPath,
      payload: item.payload,
      workflowPayloadOut: extracted.payloadOut,
    });
  }

  const manifestPath = path.join(OUT_DIR, "mos-swipe-generation-manifest-advertorial-images-no-product.json");
  writeFileSync(manifestPath, JSON.stringify({ createdAt: new Date().toISOString(), outputs: completed }, null, 2) + "\n");
  console.log(`Wrote manifest ${manifestPath}`);
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exit(1);
});
