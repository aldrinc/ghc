import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const OUT_DIR = path.join(
  ROOT,
  "outputs/tenor-mars-carousel-validation-swipe-flow-2026-04-28/generated-tenor-06-free-gifts",
);
const SOURCE_FILE = path.join(
  ROOT,
  "outputs/tenor-mars-carousel-validation-swipe-flow-2026-04-28/generated-tenor-06-free-gifts/06-tenor-free-gifts-reference-board-v3-pill-caddy-zoom.jpg",
);
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

const job = {
  key: "06-tenor-free-gifts-main-product-first-4-v3",
  assetBriefId: "brief_editorial_wound_scene",
  requirementIndex: 0,
  hook: "What's Included: Your Free Gifts",
  angle:
    "Use the attached V3 reference board as the complete visual input. The Mars Men source 06 panel controls the final layout/composition. The V2 output panel controls the approved Tenor styling and the already-approved hat, shaker bottle, and gym towel direction. The enlarged pill caddy photo in the bottom half controls the pill caddy object and must be followed closely. Do not reproduce the reference-board layout in the final output; create one finished 1:1 PDP carousel slide.\n\n" +
    "Preserve the Mars source composition: bold WHAT'S INCLUDED headline at the top, YOUR FREE GIFTS subheadline, large main product block on the left, plus sign in the center, and four gift cards on the right with FREE ribbons.\n\n" +
    "Adapt the content for Tenor. Brand: Tenor. Product: Daily Drive Essentials, premium black men's vitality supplement bottle, 60 capsules, testosterone and vitality support. Keep the product as the main left-side object. Use Tenor's premium light carousel direction: warm off-white / stone background, black or near-black Aeonik-style typography, filled/blocky UI elements, restrained warm neutral accent, polished PDP carousel quality. Do not make the design red-heavy.\n\n" +
    "Gift content: include exactly these four Tenor gifts: Pill Caddy ($19 value), Shaker Bottle ($18 value), Baseball Cap ($25 value), and Gym Towel ($18 value). Show these as four gift cards on the right. Keep FREE ribbons. Do not include Duffle Bag, Stainless Steel Bottle, apps, watches, ebooks, travel tins, or any Mars Men items.\n\n" +
    "Critical V3 correction: replace only the pill caddy with the enlarged bottom reference. It must be the actual long black weekly organizer with rounded half-cylinder end caps, seven curved day lids across the top, a slightly wavy lower front edge, and a white TENOR wordmark on the lower front. Do not render it as a rounded oval/capsule case, a hard rectangular block, a small generic case, or a box. Keep the baseball cap as a black cap with clear white Tenor text. Keep the shaker bottle and gym towel direction from V2.\n\n" +
    "Offer context: Save 30% + Free Welcome Gifts. Bonus gifts are for new subscribers and ship with scheduled subscription orders. Make the slide feel like a clean Tenor product carousel image, not a copied Mars Men design.",
};

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
    const error = new Error(`${options.method || "GET"} ${url} failed (${response.status}): ${text.slice(0, 1000)}`);
    error.status = response.status;
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
    {
      method: "POST",
      headers: ORIGIN_HEADERS,
    },
  );
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
    upload: async (apiPath, filePath) => {
      const bytes = readFileSync(filePath);
      const form = new FormData();
      form.append("files", new Blob([bytes], { type: "image/jpeg" }), path.basename(filePath));
      return requestJson(`${API_BASE}${apiPath}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
    },
  };
}

async function waitForWorkflow(clientRef, workflowRunId, timeoutMs = 25 * 60 * 1000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    let detail;
    try {
      detail = await clientRef.current.get(`/workflows/${encodeURIComponent(workflowRunId)}`);
    } catch (error) {
      if (error?.status !== 401) throw error;
      console.log("Workflow polling token expired; refreshing auth token...");
      clientRef.current = apiClient(await getBackendToken());
      detail = await clientRef.current.get(`/workflows/${encodeURIComponent(workflowRunId)}`);
    }
    const status = detail?.run?.status;
    if (status === "completed") return detail;
    if (status === "failed" || status === "cancelled") {
      const errors = (detail?.logs || []).map((log) => log.error).filter(Boolean).join("\n");
      throw new Error(`Workflow ${workflowRunId} ended with ${status}: ${errors || "no error detail"}`);
    }
    console.log(`Workflow ${workflowRunId} is ${status}; waiting...`);
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
  mkdirSync(OUT_DIR, { recursive: true });
  const token = await getBackendToken();
  const clientRef = { current: apiClient(token) };
  const resumeWorkflowRunId = (process.env.RESUME_WORKFLOW_RUN_ID || "").trim();

  let attachment = null;
  let response = null;
  let payload = null;
  if (resumeWorkflowRunId) {
    console.log(`Resuming existing workflow ${resumeWorkflowRunId}`);
    response = { workflow_run_id: resumeWorkflowRunId, temporal_workflow_id: null };
  } else {
    const upload = await clientRef.current.upload(
      `/funnels/${STAGING_FUNNEL_ID}/pages/${STAGING_PAGE_ID}/ai/attachments`,
      SOURCE_FILE,
    );
    attachment = upload.attachments?.[0];
    if (!attachment?.url) throw new Error("Attachment upload did not return a usable URL.");
    const sourceUrl = `${API_BASE}${attachment.url}`;
    console.log(`Staged Mars source 06 + Tenor gift reference board: ${sourceUrl}`);

    payload = {
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

    response = await clientRef.current.post("/swipes/generate-image-ad", payload);
    console.log(`Started ${job.key}: workflow ${response.workflow_run_id}`);
  }
  const detail = await waitForWorkflow(clientRef, response.workflow_run_id);
  const extracted = extractAssetId(detail);
  const asset = await resolveAsset(clientRef.current, extracted.assetId);
  const ext = asset.content_type === "image/png" ? "png" : "jpg";
  const outputPath = path.join(OUT_DIR, `${job.key}.${ext}`);
  downloadPublicAsset(asset.public_id, outputPath);

  const manifest = {
    createdAt: new Date().toISOString(),
    sourceFile: SOURCE_FILE,
    sourceAttachment: attachment,
    note: "Uploaded one composite reference board: Mars Men source 06 for composition plus actual Tenor product/gift images for object accuracy.",
    stagingFunnelId: STAGING_FUNNEL_ID,
    stagingPageId: STAGING_PAGE_ID,
    campaignId: CAMPAIGN_ID,
    clientId: CLIENT_ID,
    productId: PRODUCT_ID,
    output: {
      key: job.key,
      workflowRunId: response.workflow_run_id,
      temporalWorkflowId: response.temporal_workflow_id,
      assetId: asset.id,
      publicId: asset.public_id,
      publicUrl: `${API_BASE}/public/assets/${asset.public_id}`,
      localPath: outputPath,
      payload,
      workflowPayloadOut: extracted.payloadOut,
    },
  };
  const manifestPath = path.join(OUT_DIR, "mos-swipe-generation-manifest-06-free-gifts.json");
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n");
  console.log(`Downloaded generated image: ${outputPath}`);
  console.log(`Wrote manifest: ${manifestPath}`);
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exit(1);
});
