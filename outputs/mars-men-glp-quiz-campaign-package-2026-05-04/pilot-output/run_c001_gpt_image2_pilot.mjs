import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const PACKAGE_DIR = path.join(ROOT, "outputs/mars-men-glp-quiz-campaign-package-2026-05-04");
const OUT_DIR = path.join(PACKAGE_DIR, "pilot-output");
const GENERATED_DIR = path.join(OUT_DIR, "generated");
const AUTH_FILE = path.join(ROOT, ".env.mos-test-auth");

const API_BASE = "https://api.moshq.app";
const CLERK_BASE = "https://immune-turtle-79.clerk.accounts.dev/v1";
const CLERK_QUERY = "__clerk_api_version=2025-11-10&_clerk_js_version=5.125.10";
const ORIGIN_HEADERS = {
  Origin: "https://moshq.app",
  Referer: "https://moshq.app/",
};

const CLIENT_ID = "70124684-505f-48af-a25c-5f7a79601fa0";
const PRODUCT_ID = "8b89a76d-069c-41a6-be38-b7e4f4483460";
const CAMPAIGN_ID = "3ff5811c-741b-4dc2-8050-46506dea14bc";
const ASSET_BRIEF_ID = "brief_editorial_wound_scene";
const REQUIREMENT_INDEX = 0;
const STAGING_FUNNEL_ID = "be65d76e-ced9-4948-9465-18723c8446fd";
const STAGING_PAGE_ID = "ab3102f4-a179-410a-9eb0-66aa3020cafc";
const RENDER_MODEL_ID = "gpt-image-2";
const STAGE_ONE_MODEL = "gemini-3.1-pro-preview";

const SOURCE_FILE = path.join(
  PACKAGE_DIR,
  "creatives/C001_9e8258a1f182_what-glp-1-does-to-your-t-levels.jpg",
);
const EXPECTED_SOURCE_SHA256 = "9e8258a1f18266606a0ae97cd85c2ada8200275f03b6f658984e9ca8d09f762b";
const MANIFEST_PATH = path.join(OUT_DIR, "c001-gpt-image2-pilot-manifest.json");
const WORKFLOW_DETAIL_PATH = path.join(OUT_DIR, "c001-gpt-image2-workflow-detail.json");

let cachedToken = null;

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

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
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

async function resolveAsset(assetId) {
  const rows = await authed(
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
  const sourceBytes = readFileSync(SOURCE_FILE);
  const sourceSha256 = sha256(sourceBytes);
  if (sourceSha256 !== EXPECTED_SOURCE_SHA256) {
    throw new Error(`C001 source hash mismatch: expected ${EXPECTED_SOURCE_SHA256}, got ${sourceSha256}`);
  }

  const csvRows = parseCsv(readFileSync(path.join(PACKAGE_DIR, "glp-quiz-campaign-ready-expanded.csv"), "utf8"));
  const row = csvRows.find((entry) => entry.creative_id === "C001" && entry.remix_copy_id === "TENOR-COPY001");
  if (!row) throw new Error("Could not find TENOR-COPY001 / C001 in expanded campaign CSV.");

  await getBackendToken();
  const sourceAttachment = await uploadSourceFile(SOURCE_FILE);

  const sourceResponse = await fetch(sourceAttachment.publicUrl);
  if (!sourceResponse.ok) {
    throw new Error(`Failed to re-download staged source (${sourceResponse.status}) from ${sourceAttachment.publicUrl}`);
  }
  const stagedSourceBytes = Buffer.from(await sourceResponse.arrayBuffer());
  const stagedSourceSha256 = sha256(stagedSourceBytes);
  if (stagedSourceSha256 !== EXPECTED_SOURCE_SHA256) {
    throw new Error(`Staged source hash mismatch: expected ${EXPECTED_SOURCE_SHA256}, got ${stagedSourceSha256}`);
  }

  const payload = {
    clientId: CLIENT_ID,
    productId: PRODUCT_ID,
    campaignId: CAMPAIGN_ID,
    assetBriefId: ASSET_BRIEF_ID,
    requirementIndex: REQUIREMENT_INDEX,
    swipeImageUrl: sourceAttachment.publicUrl,
    swipeRequiresProductImage: false,
    swipeContextMode: "minimal",
    swipeBrandName: "Tenor",
    swipeProductName: "Daily Drive Essentials",
    swipeHook: row.remix_title,
    swipeAngle: [
      `Launch slot: ${row.launch_slot}`,
      `Source creative: ${row.creative_id} / ${row.creative_reference_title}`,
      `Remix copy: ${row.remix_copy_id} / ${row.remix_title}`,
      `Destination: ${row.exact_landers}`,
    ].join("\n"),
    model: STAGE_ONE_MODEL,
    renderModelId: RENDER_MODEL_ID,
    aspectRatio: "9:16",
    count: 1,
  };

  const started = await authed("/swipes/generate-image-ad", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  console.log(`Started GPT Image 2 C001 workflow ${started.workflow_run_id}`);

  const detail = await waitForWorkflow(started.workflow_run_id);
  writeFileSync(WORKFLOW_DETAIL_PATH, JSON.stringify(detail, null, 2) + "\n");
  const { assetId, payloadOut } = extractAssetId(detail);
  const asset = await resolveAsset(assetId);
  const ext = asset.content_type === "image/png" ? "png" : "jpg";
  const localPath = path.join(GENERATED_DIR, `C001-gpt-image2.${ext}`);
  downloadPublicAsset(asset.public_id, localPath);
  const generatedBytes = readFileSync(localPath);

  const manifest = {
    createdAt: new Date().toISOString(),
    packageDir: PACKAGE_DIR,
    sourceCsv: path.join(PACKAGE_DIR, "glp-quiz-campaign-ready-expanded.csv"),
    campaignId: CAMPAIGN_ID,
    clientId: CLIENT_ID,
    productId: PRODUCT_ID,
    source: {
      creativeId: row.creative_id,
      copyId: row.remix_copy_id,
      creativeFile: SOURCE_FILE,
      expectedSha256: EXPECTED_SOURCE_SHA256,
      stagedSha256: stagedSourceSha256,
      stagedAttachment: sourceAttachment,
    },
    generation: {
      stageOneModel: STAGE_ONE_MODEL,
      renderModelId: RENDER_MODEL_ID,
      workflowRunId: started.workflow_run_id,
      temporalWorkflowId: started.temporal_workflow_id,
      workflowUrl: `https://moshq.app/workflows/${started.workflow_run_id}`,
      workflowDetailPath: WORKFLOW_DETAIL_PATH,
      workflowPayloadOut: payloadOut,
    },
    output: {
      assetId: asset.id,
      publicId: asset.public_id,
      publicUrl: `${API_BASE}/public/assets/${asset.public_id}`,
      contentType: asset.content_type,
      width: asset.width,
      height: asset.height,
      localPath,
      bytes: generatedBytes.length,
      sha256: sha256(generatedBytes),
      aiMetadata: {
        swipePromptModel: asset.ai_metadata?.swipePromptModel,
        swipeRenderModelIdRequested: asset.ai_metadata?.swipeRenderModelIdRequested,
        swipeRenderModelIdUsed: asset.ai_metadata?.swipeRenderModelIdUsed,
        swipeRenderProvider: asset.ai_metadata?.swipeRenderProvider,
        swipePromptImageSha256: asset.ai_metadata?.swipePromptImageSha256,
        swipePromptImageSourceUrl: asset.ai_metadata?.swipePromptImageSourceUrl,
        remoteJobId: asset.ai_metadata?.remoteJobId,
      },
    },
    payload,
  };
  writeFileSync(MANIFEST_PATH, JSON.stringify(manifest, null, 2) + "\n");
  console.log(JSON.stringify({ manifestPath: MANIFEST_PATH, localPath, assetId: asset.id, publicUrl: manifest.output.publicUrl }, null, 2));
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exitCode = 1;
});
