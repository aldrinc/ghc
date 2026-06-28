import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const OUT_DIR = path.join(
  ROOT,
  "outputs/tenor-mars-carousel-validation-swipe-flow-2026-04-28/generated-tenor-08-supplement-facts",
);
const SOURCE_FILE = path.join(OUT_DIR, "08-tenor-supplement-facts-exact.jpg");
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
  key: "08-tenor-supplement-facts-mos",
  assetBriefId: "brief_editorial_mechanism_reveal",
  requirementIndex: 2,
  hook: "Supplement Facts",
  angle:
    "Create a square Tenor PDP carousel supplement facts card using the attached corrected Tenor facts card as the source of truth. Preserve the supplement-facts panel structure, the light premium background, and the right-side trust badge rhythm. Required facts: Supplement Facts; Serving Size: 2 Vegan Capsules; Servings Per Container: 30; Zinc (as Zinc Oxide) 50 mg 333%; Tongkat Ali (powder) 400 mg; Maca (0.6 extract) 250 mg; L-Arginine 250 mg; Ginseng Eleuthero Blend 125 mg with Panax Ginseng (root) and Eleutherococcus (root); Supporting Botanical Matrix 745 mg with Sarsaparilla (root) Extract, Pumpkin (seed) Extract, Muira Puama (bark) Extract, Oat Straw (leaf and stalk), Nettle (leaf), Cayenne Pepper (fruit), Astragalus (root) Extract, Catuaba (bark), Licorice (root) Extract, Tribulus Terrestris, Orchic (substance), Oyster Extract, and Boron (amino acid chelate). Keep the text mobile-legible, do not invent additional ingredients or amounts, and use Supporting Botanical Matrix as the 745 mg line name.",
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
  const client = apiClient(token);

  const upload = await client.upload(`/funnels/${STAGING_FUNNEL_ID}/pages/${STAGING_PAGE_ID}/ai/attachments`, SOURCE_FILE);
  const attachment = upload.attachments?.[0];
  if (!attachment?.url) throw new Error("Attachment upload did not return a usable URL.");
  const sourceUrl = `${API_BASE}${attachment.url}`;
  console.log(`Staged corrected source image: ${sourceUrl}`);

  const payload = {
    clientId: CLIENT_ID,
    productId: PRODUCT_ID,
    campaignId: CAMPAIGN_ID,
    assetBriefId: job.assetBriefId,
    requirementIndex: job.requirementIndex,
    swipeImageUrl: sourceUrl,
    swipeRequiresProductImage: false,
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
  const detail = await waitForWorkflow(client, response.workflow_run_id);
  const extracted = extractAssetId(detail);
  const asset = await resolveAsset(client, extracted.assetId);
  const ext = asset.content_type === "image/png" ? "png" : "jpg";
  const outputPath = path.join(OUT_DIR, `${job.key}.${ext}`);
  downloadPublicAsset(asset.public_id, outputPath);

  const manifest = {
    createdAt: new Date().toISOString(),
    sourceFile: SOURCE_FILE,
    sourceAttachment: attachment,
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
  const manifestPath = path.join(OUT_DIR, "mos-swipe-generation-manifest-08-supplement-facts.json");
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n");
  console.log(`Downloaded generated image: ${outputPath}`);
  console.log(`Wrote manifest: ${manifestPath}`);
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exit(1);
});
