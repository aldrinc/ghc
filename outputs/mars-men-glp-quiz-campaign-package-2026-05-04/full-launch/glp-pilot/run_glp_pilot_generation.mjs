import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const PACKAGE_DIR = path.join(ROOT, "outputs/mars-men-glp-quiz-campaign-package-2026-05-04");
const FULL_LAUNCH_DIR = path.join(PACKAGE_DIR, "full-launch");
const OUT_DIR = path.join(FULL_LAUNCH_DIR, "glp-pilot");
const GENERATED_DIR = path.join(OUT_DIR, "generated");
const AUTH_FILE = path.join(ROOT, ".env.mos-test-auth");
const STATE_PATH = path.join(FULL_LAUNCH_DIR, "campaign-state.json");
const REVIEW_PATH = path.join(FULL_LAUNCH_DIR, "destination-congruence-review-v2.json");
const MANIFEST_PATH = path.join(OUT_DIR, "glp-pilot-manifest.json");

const API_BASE = "https://api.moshq.app";
const CLERK_BASE = "https://immune-turtle-79.clerk.accounts.dev/v1";
const CLERK_QUERY = "__clerk_api_version=2025-11-10&_clerk_js_version=5.125.10";
const ORIGIN_HEADERS = {
  Origin: "https://moshq.app",
  Referer: "https://moshq.app/",
};

const CLIENT_ID = "70124684-505f-48af-a25c-5f7a79601fa0";
const PRODUCT_ID = "8b89a76d-069c-41a6-be38-b7e4f4483460";
const GLP_BRIEF_ID = "brief_glp_listicle_swipe_image2";
const STAGING_FUNNEL_ID = "be65d76e-ced9-4948-9465-18723c8446fd";
const STAGING_PAGE_ID = "ab3102f4-a179-410a-9eb0-66aa3020cafc";
const STAGE_ONE_MODEL = "gemini-3.1-pro-preview";
const RENDER_MODEL_ID = "gpt-image-2";
const GLP_PRESALE_URL = "https://shoptenorco.com/8b89a76d/daily-drive-essentials/10-reasons-glp/";
const SALES_URL =
  "https://shoptenorco.com/8b89a76d/daily-drive-essentials/sales-page/?selling_plan=2948432039";

let cachedToken = null;

function ensureDirs() {
  mkdirSync(OUT_DIR, { recursive: true });
  mkdirSync(GENERATED_DIR, { recursive: true });
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];
    if (quoted) {
      if (char === '"' && next === '"') {
        field += '"';
        i += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
      continue;
    }
    if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (char !== "\r") {
      field += char;
    }
  }
  if (field || row.length) {
    row.push(field);
    rows.push(row);
  }
  const [headers, ...body] = rows;
  return body
    .filter((entry) => entry.length > 1)
    .map((entry) => Object.fromEntries(headers.map((header, index) => [header, entry[index] ?? ""])));
}

function imageSize(filePath) {
  const output = execFileSync(
    "python3",
    [
      "-c",
      "from PIL import Image; import sys; im=Image.open(sys.argv[1]); print(f'{im.size[0]}x{im.size[1]}')",
      filePath,
    ],
    { encoding: "utf8" },
  ).trim();
  const [width, height] = output.split("x").map((value) => Number(value));
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    throw new Error(`Could not read image dimensions for ${filePath}: ${output}`);
  }
  return { width, height };
}

function aspectRatioFor(filePath) {
  const { width, height } = imageSize(filePath);
  if (width === height) return "1:1";
  if (width * 5 === height * 4) return "4:5";
  if (width * 16 === height * 9) return "9:16";
  const gcd = (a, b) => (b === 0 ? a : gcd(b, a % b));
  const divisor = gcd(width, height);
  return `${width / divisor}:${height / divisor}`;
}

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

async function uploadSourceFile(filePath) {
  const token = cachedToken || (await getBackendToken());
  const form = new FormData();
  const bytes = readFileSync(filePath);
  form.append("files", new Blob([bytes], { type: "image/jpeg" }), path.basename(filePath));
  const upload = await requestJson(
    `${API_BASE}/funnels/${STAGING_FUNNEL_ID}/pages/${STAGING_PAGE_ID}/ai/attachments`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    },
  );
  const [attachment] = upload?.attachments || [];
  if (!attachment?.url || !attachment?.assetId || !attachment?.publicId) {
    throw new Error(`Unexpected source upload response: ${JSON.stringify(upload)}`);
  }
  return {
    assetId: attachment.assetId,
    publicId: attachment.publicId,
    publicUrl: `${API_BASE}${attachment.url}`,
    width: attachment.width,
    height: attachment.height,
    contentType: attachment.contentType,
  };
}

async function waitForWorkflow(workflowRunId, timeoutMs = 40 * 60 * 1000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const detail = await authed(`/workflows/${encodeURIComponent(workflowRunId)}`);
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
    if (ids.length !== 1) throw new Error(`Expected one generated asset id, got ${ids.length}`);
    return { assetId: ids[0], payloadOut: log.payload_out };
  }
  throw new Error("Completed workflow did not include a succeeded swipe_image_ad log.");
}

async function resolveAsset(campaignId, assetId) {
  const rows = await authed(
    `/assets?campaignId=${encodeURIComponent(campaignId)}&productId=${encodeURIComponent(PRODUCT_ID)}&assetKind=image`,
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

function rowByCreativeId(rows, creativeId) {
  const row = rows.find((entry) => entry.creative_id === creativeId && entry.launch_slot === "GLP lander");
  if (!row) throw new Error(`Could not find GLP row for creative ${creativeId}`);
  return row;
}

function copyUnitFor(rows, remixCopyId) {
  const row = rows.find((entry) => entry.remix_copy_id === remixCopyId && entry.launch_slot === "GLP lander");
  if (!row) throw new Error(`Could not find GLP copy unit ${remixCopyId}`);
  return {
    sourceCopyId: row.source_copy_id,
    remixCopyId: row.remix_copy_id,
    title: row.remix_title,
    body: row.remix_body,
    cta: row.remix_cta,
    linkDescription: row.remix_link_description,
    destinationUrl: GLP_PRESALE_URL,
    salesUrl: SALES_URL,
  };
}

function glpCongruenceBlock() {
  const review = JSON.parse(readFileSync(REVIEW_PATH, "utf8"));
  const entry = review.destinationCongruenceMap.find((item) => item.destinationUrl === GLP_PRESALE_URL);
  if (!entry?.congruenceBlock) throw new Error(`Missing GLP congruence block in ${REVIEW_PATH}`);
  if (!entry.congruenceBlock.startsWith("Awareness level: Problem-Aware")) {
    throw new Error("GLP congruence block is not Problem-Aware.");
  }
  return entry.congruenceBlock;
}

function validatePayload(payload) {
  if ("swipeHook" in payload) throw new Error("Pilot payload must not include swipeHook.");
  if (!payload.swipeAngle.startsWith("Awareness level: Problem-Aware")) {
    throw new Error("Pilot payload must be Problem-Aware.");
  }
  if (Boolean(payload.companySwipeId) === Boolean(payload.swipeImageUrl)) {
    throw new Error("Pilot payload must provide exactly one of companySwipeId or swipeImageUrl.");
  }
  if (payload.renderModelId !== RENDER_MODEL_ID) {
    throw new Error(`Unexpected render model: ${payload.renderModelId}`);
  }
}

async function buildManifest() {
  ensureDirs();
  const state = JSON.parse(readFileSync(STATE_PATH, "utf8"));
  const rows = parseCsv(readFileSync(path.join(PACKAGE_DIR, "glp-quiz-campaign-ready-expanded.csv"), "utf8"));
  const congruenceBlock = glpCongruenceBlock();
  const c001 = rowByCreativeId(rows, "C001");
  const c006 = rowByCreativeId(rows, "C006");
  const curatedCopy = copyUnitFor(rows, "TENOR-COPY002");
  const c001Copy = copyUnitFor(rows, c001.remix_copy_id);
  const c006Copy = copyUnitFor(rows, c006.remix_copy_id);

  const entries = [
    {
      key: "curated-green-glp",
      sourceType: "standard_curated",
      companySwipeId: "e2ff843d-e853-55eb-b306-4398900615ef",
      sourceTitle: "green.jpg",
      productReferencePolicy: "never_for_curated",
      productReferenceRequired: false,
      aspectRatio: "1:1",
      adCopy: curatedCopy,
    },
    {
      key: "tenor-c001-non-product-glp",
      sourceType: "tenor_package",
      sourceCreativeId: "C001",
      sourceTitle: c001.creative_reference_title,
      sourcePath: path.join(PACKAGE_DIR, c001.creative_file),
      productReferencePolicy: "dynamic_by_tenor_reference",
      productReferenceRequired: false,
      aspectRatio: aspectRatioFor(path.join(PACKAGE_DIR, c001.creative_file)),
      adCopy: c001Copy,
    },
    {
      key: "tenor-c006-product-bearing-glp",
      sourceType: "tenor_package",
      sourceCreativeId: "C006",
      sourceTitle: c006.creative_reference_title,
      sourcePath: path.join(PACKAGE_DIR, c006.creative_file),
      productReferencePolicy: "dynamic_by_tenor_reference",
      productReferenceRequired: true,
      aspectRatio: aspectRatioFor(path.join(PACKAGE_DIR, c006.creative_file)),
      adCopy: c006Copy,
    },
  ];

  for (const entry of entries) {
    const payload = {
      clientId: CLIENT_ID,
      productId: PRODUCT_ID,
      campaignId: state.campaignId,
      assetBriefId: GLP_BRIEF_ID,
      requirementIndex: 0,
      swipeRequiresProductImage: entry.productReferenceRequired,
      swipeContextMode: "minimal",
      swipeBrandName: "Tenor",
      swipeProductName: "Daily Drive Essentials",
      swipeAngle: congruenceBlock,
      model: STAGE_ONE_MODEL,
      renderModelId: RENDER_MODEL_ID,
      aspectRatio: entry.aspectRatio,
      count: 1,
    };
    if (entry.sourceType === "standard_curated") {
      payload.companySwipeId = entry.companySwipeId;
    } else {
      const bytes = readFileSync(entry.sourcePath);
      entry.sourceCreativeSha256 = sha256(bytes);
      const sourceAttachment = await uploadSourceFile(entry.sourcePath);
      entry.sourceAttachment = sourceAttachment;
      payload.swipeImageUrl = sourceAttachment.publicUrl;
    }
    validatePayload(payload);
    entry.payload = payload;
  }

  const manifest = {
    createdAt: new Date().toISOString(),
    note: "GLP-only pilot. No publishing. Curated row reuses GLP copy only; generation payload omits swipeHook and uses only the GLP congruence block as swipeAngle.",
    campaignId: state.campaignId,
    targetPublishPlan: {
      geography: "US only",
      targeting: {
        geo_locations: {
          countries: ["US"],
          location_types: ["home", "recent"],
        },
      },
    },
    destination: {
      label: "GLP listicle",
      presaleUrl: GLP_PRESALE_URL,
      salesUrl: SALES_URL,
      congruenceBlock,
    },
    sourceCollections: {
      standardCurated: {
        collectionId: "b89e89f4-2565-4b5d-afd1-195532613bfb",
        collectionName: "Tenor initial swipe collection",
      },
    },
    entries,
  };
  writeFileSync(MANIFEST_PATH, JSON.stringify(manifest, null, 2) + "\n");
  return manifest;
}

async function generatePilot() {
  let manifest;
  if (existsSync(MANIFEST_PATH)) {
    manifest = JSON.parse(readFileSync(MANIFEST_PATH, "utf8"));
  } else {
    manifest = await buildManifest();
  }

  for (const entry of manifest.entries) {
    if (entry.result?.assetId) {
      console.log(`Skipping ${entry.key}; already generated ${entry.result.assetId}`);
      continue;
    }
    validatePayload(entry.payload);
    console.log(`Generating ${entry.key} (${entry.payload.aspectRatio})`);
    const started = await authed("/swipes/generate-image-ad", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(entry.payload),
    });
    const detail = await waitForWorkflow(started.workflow_run_id);
    const workflowPath = path.join(OUT_DIR, `workflow-${entry.key}.json`);
    writeFileSync(workflowPath, JSON.stringify(detail, null, 2) + "\n");
    const { assetId, payloadOut } = extractAssetId(detail);
    const asset = await resolveAsset(manifest.campaignId, assetId);
    const extension = (asset.content_type || "image/png").includes("jpeg") ? "jpg" : "png";
    const localPath = path.join(GENERATED_DIR, `${entry.key}.${extension}`);
    downloadPublicAsset(asset.public_id, localPath);
    entry.workflow = {
      workflowRunId: started.workflow_run_id,
      temporalWorkflowId: started.temporal_workflow_id,
      workflowUrl: `https://moshq.app/workflows/${started.workflow_run_id}`,
      workflowDetailPath: workflowPath,
      payloadOut,
    };
    entry.result = {
      assetId,
      publicId: asset.public_id,
      publicUrl: `${API_BASE}/public/assets/${asset.public_id}`,
      contentType: asset.content_type,
      width: asset.width,
      height: asset.height,
      localPath,
      remoteJobId: payloadOut?.job_id || null,
      renderProvider: payloadOut?.swipe_render_provider || null,
      renderModelIdUsed: payloadOut?.swipe_render_model_id || entry.payload.renderModelId,
    };
    writeFileSync(MANIFEST_PATH, JSON.stringify({ ...manifest, updatedAt: new Date().toISOString() }, null, 2) + "\n");
  }
  return manifest;
}

async function main() {
  const command = process.argv[2] || "manifest";
  if (command === "manifest") {
    const manifest = await buildManifest();
    console.log(JSON.stringify({ manifestPath: MANIFEST_PATH, entries: manifest.entries.map((entry) => entry.key) }, null, 2));
  } else if (command === "generate") {
    const manifest = await generatePilot();
    console.log(JSON.stringify({ manifestPath: MANIFEST_PATH, generated: manifest.entries.map((entry) => ({ key: entry.key, result: entry.result || null })) }, null, 2));
  } else {
    throw new Error(`Unknown command: ${command}`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
