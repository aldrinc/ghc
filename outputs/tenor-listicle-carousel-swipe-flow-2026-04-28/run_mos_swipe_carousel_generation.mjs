import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const OUT_DIR = path.join(ROOT, "outputs/tenor-listicle-carousel-swipe-flow-2026-04-28");
const SOURCE_DIR = path.join(OUT_DIR, "source-swipes");
const GENERATED_DIR = path.join(OUT_DIR, "generated");
const AUTH_FILE = path.join(ROOT, ".env.mos-test-auth");
const API_BASE = "https://api.moshq.app";
const CLERK_BASE = "https://immune-turtle-79.clerk.accounts.dev/v1";
const CLERK_QUERY = "__clerk_api_version=2025-11-10&_clerk_js_version=5.125.10";
const ORIGIN_HEADERS = {
  Origin: "https://moshq.app",
  Referer: "https://moshq.app/",
};

const CAMPAIGN_ID = "a5af5e49-1eb8-4fb4-8029-d3d2006114e9";
const CLIENT_ID = "70124684-505f-48af-a25c-5f7a79601fa0";
const PRODUCT_ID = "8b89a76d-069c-41a6-be38-b7e4f4483460";
const STAGING_FUNNEL_ID = "be65d76e-ced9-4948-9465-18723c8446fd";
const STAGING_PAGE_ID = "ab3102f4-a179-410a-9eb0-66aa3020cafc";

const jobs = [
  {
    key: "01-product-hero",
    sourceFile: "01-tenor-product-hero-source.jpg",
    assetBriefId: "brief_editorial_mechanism_reveal",
    requirementIndex: 2,
    hook: "Daily Drive Essentials",
    angle:
      "Create a square Tenor listicle carousel product hero card. Use the attached source swipe as the exact copy and layout target. Keep the updated black Daily Drive Essentials bottle recognizable from the product reference. Required text: Daily Drive Essentials; Physician-formulated vitality support; 2 capsules every morning; Every active dose disclosed on the label; Clean & consistent energy; Natural drive & libido; Peak vitality & performance; Non-GMO | Third-Party Tested | cGMP Manufactured. Use a neutral bone background, graphite/black typography, and one ember red accent. Do not use sachets, powder, scoop, IM8 branding, celebrity language, or 92-ingredient claims.",
  },
  {
    key: "02-survey-proof",
    sourceFile: "02-tenor-survey-proof-source.jpg",
    assetBriefId: "brief_editorial_mechanism_reveal",
    requirementIndex: 1,
    hook: "Men reported feeling more like themselves.",
    angle:
      "Create a square Tenor listicle carousel proof card based on the attached source swipe. Use survey proof only, not clinical trial language. Required text: Reported outcomes; Men reported feeling more like themselves; Survey data from 1,203 men; 94% Morning energy; 81% Physical stamina; 87% Mental sharpness; 92% Overall vitality; For creative review. Not a clinical trial claim. Keep the design editorial, neutral, masculine, and mobile-legible. Do not mention digestion, sleep, randomized trial, IM8, or Essentials Pro.",
  },
  {
    key: "03-formula",
    sourceFile: "03-tenor-formula-source.jpg",
    assetBriefId: "brief_editorial_mechanism_reveal",
    requirementIndex: 2,
    hook: "Five core levers. No proprietary blend.",
    angle:
      "Create a square Tenor listicle carousel formula card from the attached source swipe. Required text: Five core levers; No proprietary blend; Exact active doses disclosed on the label; Tongkat Ali 400 mg; Zinc 50 mg; Maca 250 mg; L-Arginine 250 mg; Ginseng + Eleuthero 125 mg; Built for men who want a daily protocol before clinics, prescriptions, or needles. Include the updated Daily Drive Essentials bottle. Do not say one scoop replaces anything, do not show sachets or powder, and do not invent additional doses.",
  },
  {
    key: "04-scientific-foundation",
    sourceFile: "04-tenor-scientific-foundation-source.jpg",
    assetBriefId: "brief_editorial_founder_authority",
    requirementIndex: 0,
    hook: "Ingredient science, not borrowed celebrity.",
    angle:
      "Create a square Tenor listicle carousel scientific foundation card from the attached source swipe. Required text: Scientific foundation; Ingredient science, not borrowed celebrity; Research territories represented across nitric oxide, men's health, zinc biology, maca endocrinology, and vascular medicine. Include these names and territories: Dr. R. William Caldwell - nitric oxide / vascular tone; Dr. Wolfgang Maret - zinc biology; Dr. Gustavo F. Gonzales - maca endocrine research; Dr. Mohammed Rais - vascular medicine; Also reviewed: Dr. Faysal A. Yafi, MD, FRCSC - men's health and urology. Do not use the old IM8 advisory board, NASA, Mayo, Beckham, or celebrity claims. Do not imply these experts personally endorse the product beyond the stated scientific foundation/review framing.",
  },
];

function loadAuthEnv() {
  const raw = readFileSync(AUTH_FILE, "utf8");
  const env = {};
  for (const line of raw.split(/\r?\n/)) {
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
    throw new Error(`${options.method || "GET"} ${url} failed (${response.status}): ${text.slice(0, 1000)}`);
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
  const token = await requestJson(`${CLERK_BASE}/client/sessions/${sessionId}/tokens/backend?${CLERK_QUERY}&__clerk_db_jwt=${dbJwt}`, {
    method: "POST",
    headers: ORIGIN_HEADERS,
  });
  if (!token?.jwt) throw new Error("Clerk backend token response did not include jwt.");
  return token.jwt;
}

function apiClient(token) {
  return {
    get: (apiPath) =>
      requestJson(`${API_BASE}${apiPath}`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
    post: (apiPath, payload) =>
      requestJson(`${API_BASE}${apiPath}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      }),
    upload: async (apiPath, files) => {
      const form = new FormData();
      for (const filePath of files) {
        const bytes = readFileSync(filePath);
        form.append("files", new Blob([bytes], { type: "image/jpeg" }), path.basename(filePath));
      }
      return requestJson(`${API_BASE}${apiPath}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
    },
  };
}

async function waitForWorkflow(client, workflowRunId, timeoutMs = 25 * 60 * 1000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const detail = await client.get(`/workflows/${encodeURIComponent(workflowRunId)}`);
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
    return { assetId: ids[0], jobId: log.payload_out?.job_id || null, payloadOut: log.payload_out };
  }
  throw new Error("Completed workflow did not include a succeeded swipe_image_ad log.");
}

async function resolveAsset(client, assetId) {
  const rows = await client.get(
    `/assets?campaignId=${encodeURIComponent(CAMPAIGN_ID)}&productId=${encodeURIComponent(PRODUCT_ID)}&assetKind=image`,
  );
  const row = rows.find((asset) => asset.id === assetId);
  if (!row?.public_id) throw new Error(`Could not resolve generated public_id for asset ${assetId}`);
  return row;
}

function downloadPublicAsset(publicId, outputPath) {
  execFileSync("curl", ["-sS", "-L", `${API_BASE}/public/assets/${publicId}`, "-o", outputPath], {
    stdio: "inherit",
  });
}

async function main() {
  mkdirSync(GENERATED_DIR, { recursive: true });
  const token = await getBackendToken();
  const client = apiClient(token);

  const sourcePaths = jobs.map((job) => path.join(SOURCE_DIR, job.sourceFile));
  const upload = await client.upload(
    `/funnels/${STAGING_FUNNEL_ID}/pages/${STAGING_PAGE_ID}/ai/attachments`,
    sourcePaths,
  );
  const attachments = upload.attachments || [];
  if (attachments.length !== jobs.length) {
    throw new Error(`Expected ${jobs.length} staged attachments, got ${attachments.length}`);
  }
  console.log(`Staged ${attachments.length} source images as funnel AI attachments`);

  const started = [];
  for (let index = 0; index < jobs.length; index += 1) {
    const job = jobs[index];
    const attachment = attachments[index];
    const sourceUrl = `${API_BASE}${attachment.url}`;
    const payload = {
      clientId: CLIENT_ID,
      productId: PRODUCT_ID,
      campaignId: CAMPAIGN_ID,
      assetBriefId: job.assetBriefId,
      requirementIndex: job.requirementIndex,
      swipeImageUrl: sourceUrl,
      swipeRequiresProductImage: true,
      swipeContextMode: "minimal",
      swipeBrandName: "Tenor",
      swipeProductName: "Daily Drive Essentials",
      swipeHook: job.hook,
      swipeAngle: job.angle,
      aspectRatio: "1:1",
      count: 1,
    };
    const response = await client.post("/swipes/generate-image-ad", payload);
    console.log(`Started ${job.key}: workflow ${response.workflow_run_id}`);
    started.push({ job, attachment, payload, workflow: response });
  }

  const completed = [];
  for (const item of started) {
    console.log(`Waiting for ${item.job.key} (${item.workflow.workflow_run_id})`);
    const detail = await waitForWorkflow(client, item.workflow.workflow_run_id);
    const extracted = extractAssetId(detail);
    const asset = await resolveAsset(client, extracted.assetId);
    const ext = asset.content_type === "image/png" ? "png" : "jpg";
    const outputPath = path.join(GENERATED_DIR, `${item.job.key}.${ext}`);
    downloadPublicAsset(asset.public_id, outputPath);
    console.log(`Downloaded ${item.job.key}: ${outputPath}`);
    completed.push({
      key: item.job.key,
      sourceFile: item.job.sourceFile,
      sourceAttachment: item.attachment,
      workflowRunId: item.workflow.workflow_run_id,
      temporalWorkflowId: item.workflow.temporal_workflow_id,
      assetId: asset.id,
      publicId: asset.public_id,
      publicUrl: `${API_BASE}/public/assets/${asset.public_id}`,
      localPath: outputPath,
      payload: item.payload,
      workflowPayloadOut: extracted.payloadOut,
    });
  }

  const manifest = {
    createdAt: new Date().toISOString(),
    stagingFunnelId: STAGING_FUNNEL_ID,
    stagingPageId: STAGING_PAGE_ID,
    campaignId: CAMPAIGN_ID,
    clientId: CLIENT_ID,
    productId: PRODUCT_ID,
    outputs: completed,
  };
  writeFileSync(path.join(OUT_DIR, "mos-swipe-generation-manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
  console.log(`Wrote manifest ${path.join(OUT_DIR, "mos-swipe-generation-manifest.json")}`);
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exit(1);
});
