import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const OUT_DIR = path.join(ROOT, "outputs/tenor-advertorial-images-2026-04-29");
const SOURCE_DIR = path.join(OUT_DIR, "source");
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

const globalGuidance = [
  "Tenor advertorial visual system: premium editorial health and longevity imagery for men over 40.",
  "Use warm off-white, stone, black, graphite, and muted bronze accents.",
  "Natural window light, clean shadows, restrained contrast, article-native composition.",
  "No embedded claims text, no fake UI, no charts, no medical office, no needles, no shirtless gym trope, no before/after imagery.",
  "Do not invent logos, certifications, badges, people names, doctors, or testimonials.",
].join(" ");

const jobs = [
  {
    key: "01-hero-normal-labs",
    sourceFile: "01-hero-source.jpg",
    aspectRatio: "21:9",
    requiresProductImage: true,
    hook: "Normal labs, different person",
    angle:
      `${globalGuidance} Wide hero image for the top of an advertorial titled "Why So Many Men Past 40 Have Normal Testosterone And Still Feel Like a Different Person." Create a premium editorial scene: updated black Tenor Daily Drive Essentials bottle as the product anchor on a warm stone surface, with a soft out-of-focus lab report / driveway / morning-light mood cue in the background. The image should imply the gap between normal numbers and lived fatigue without readable lab data. No words except unavoidable tiny bottle label detail.`,
  },
  {
    key: "02-mechanism-actives",
    sourceFile: "02-mechanism-actives-source.jpg",
    aspectRatio: "4:3",
    requiresProductImage: true,
    hook: "The lock and key mechanism",
    angle:
      `${globalGuidance} Inline figure for the androgen receptor mechanism section. Create a sophisticated editorial scientific still life showing the Tenor bottle, two capsules, mineral stones, and botanical elements arranged around abstract lock-and-key receptor shapes made from light, shadow, and physical objects. It should feel evidence-based but not clinical. No readable labels, no molecular diagrams, no medical illustration labels, no claims text.`,
  },
  {
    key: "03-product-kit-label",
    sourceFile: "03-product-kit-source.jpg",
    aspectRatio: "4:3",
    requiresProductImage: true,
    hook: "Daily Drive Essentials kit and label",
    angle:
      `${globalGuidance} Product-kit figure for the restoration protocol section. Create a clean premium editorial product lockup with the updated black Tenor Daily Drive Essentials bottle, two capsules, a light stone background, and a supplement-facts label card or folded insert beside it. Keep the label card visually credible but do not require readable fine print. No extra product variants, no sachets, no powders, no shaker, no fake claim badges.`,
  },
  {
    key: "04-lifestyle-recovery",
    sourceFile: "04-lifestyle-source.jpg",
    aspectRatio: "4:3",
    requiresProductImage: false,
    hook: "Daily energy and recovery",
    angle:
      `${globalGuidance} Lifestyle editorial figure for the "What men report at 30, 60, and 90 days" section. Photorealistic scene of a realistic man in his early 50s on a quiet morning after an outdoor workout or weekend activity, composed and grounded, not posing like a fitness ad. Warm neutral environment, subtle bronze accent, no visible supplement bottle, no gym aggression, no medical claim, no text.`,
  },
  {
    key: "05-two-capsule-protocol",
    sourceFile: "05-daily-use-source.jpg",
    aspectRatio: "4:3",
    requiresProductImage: true,
    hook: "Two capsules every morning",
    angle:
      `${globalGuidance} Daily-use figure for the "How Men Get Started" section. Premium editorial morning routine still life: updated black Tenor Daily Drive Essentials bottle, exactly two capsules, water glass, simple breakfast or notebook, warm stone counter, clean masculine organization. No powder, no scoop, no shaker, no piles of pills, no embedded text beyond tiny bottle label detail.`,
  },
  {
    key: "06-bottle-supplement-facts",
    sourceFile: "06-bottle-facts-source.jpg",
    aspectRatio: "4:3",
    requiresProductImage: true,
    hook: "Bottle and supplement facts",
    angle:
      `${globalGuidance} Volume-signal / final product figure: updated black Tenor Daily Drive Essentials bottle beside a clean supplement-facts card on a warm off-white stone surface. The supplement-facts card should suggest disclosed active doses without needing all fine print to be readable. Use the source layout as structure. No fake certification marks, no awards, no invented badges, no extra product types.`,
  },
];

let cachedToken = null;

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
  cachedToken = token.jwt;
  return cachedToken;
}

async function authedRequest(apiPath, options = {}) {
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

async function apiGet(apiPath) {
  return authedRequest(apiPath);
}

async function apiPost(apiPath, payload) {
  return authedRequest(apiPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function uploadFiles(apiPath, files) {
  const token = cachedToken || (await getBackendToken());
  const form = new FormData();
  for (const filePath of files) {
    const bytes = readFileSync(filePath);
    form.append("files", new Blob([bytes], { type: "image/jpeg" }), path.basename(filePath));
  }
  try {
    return await requestJson(`${API_BASE}${apiPath}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
  } catch (error) {
    if (error.status !== 401) throw error;
    cachedToken = null;
    const refreshed = await getBackendToken();
    return requestJson(`${API_BASE}${apiPath}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${refreshed}` },
      body: form,
    });
  }
}

async function waitForWorkflow(workflowRunId, timeoutMs = 25 * 60 * 1000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const detail = await apiGet(`/workflows/${encodeURIComponent(workflowRunId)}`);
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

async function resolveAsset(assetId) {
  const rows = await apiGet(
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
  await getBackendToken();

  const sourcePaths = jobs.map((job) => path.join(SOURCE_DIR, job.sourceFile));
  const upload = await uploadFiles(
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
    const sourceUrl = `${API_BASE}${attachments[index].url}`;
    const payload = {
      clientId: CLIENT_ID,
      productId: PRODUCT_ID,
      campaignId: CAMPAIGN_ID,
      assetBriefId: "brief_editorial_mechanism_reveal",
      requirementIndex: 2,
      swipeImageUrl: sourceUrl,
      swipeRequiresProductImage: job.requiresProductImage,
      swipeContextMode: "minimal",
      swipeBrandName: "Tenor",
      swipeProductName: "Daily Drive Essentials",
      swipeHook: job.hook,
      swipeAngle: job.angle,
      aspectRatio: job.aspectRatio,
      count: 1,
    };
    const response = await apiPost("/swipes/generate-image-ad", payload);
    console.log(`Started ${job.key}: workflow ${response.workflow_run_id}`);
    started.push({ job, attachment: attachments[index], payload, workflow: response });
  }

  const completed = [];
  for (const item of started) {
    console.log(`Waiting for ${item.job.key} (${item.workflow.workflow_run_id})`);
    const detail = await waitForWorkflow(item.workflow.workflow_run_id);
    const extracted = extractAssetId(detail);
    const asset = await resolveAsset(extracted.assetId);
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

  const manifestPath = path.join(OUT_DIR, "mos-swipe-generation-manifest-advertorial-images.json");
  writeFileSync(
    manifestPath,
    JSON.stringify(
      {
        createdAt: new Date().toISOString(),
        campaignId: CAMPAIGN_ID,
        clientId: CLIENT_ID,
        productId: PRODUCT_ID,
        stagingFunnelId: STAGING_FUNNEL_ID,
        stagingPageId: STAGING_PAGE_ID,
        outputs: completed,
      },
      null,
      2,
    ) + "\n",
  );
  console.log(`Wrote manifest ${manifestPath}`);
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exit(1);
});
