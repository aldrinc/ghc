import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const OUT_DIR = path.join(ROOT, "outputs/tenor-awareness-level-only-ads-2026-05-01");
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

const jobs = [
  {
    key: "problem-aware-01",
    awarenessLevel: "Problem-Aware",
    companySwipeId: "a23435d2-27a0-54ab-8e73-acf761834259",
    sourceSwipeTitle: "11.png",
    assetBriefId: "brief_editorial_wound_scene",
    requirementIndex: 1,
  },
  {
    key: "problem-aware-02",
    awarenessLevel: "Problem-Aware",
    companySwipeId: "3a342736-0437-53dc-a84b-16a50b3c03e6",
    sourceSwipeTitle: "fatigue.jpg",
    assetBriefId: "brief_editorial_wound_scene",
    requirementIndex: 1,
  },
  {
    key: "solution-aware-01",
    awarenessLevel: "Solution-Aware",
    companySwipeId: "b849e92a-1a3d-5a7f-bec9-0c4f028a2d25",
    sourceSwipeTitle: "big_text.jpg",
    assetBriefId: "brief_editorial_wound_scene",
    requirementIndex: 1,
  },
  {
    key: "solution-aware-02",
    awarenessLevel: "Solution-Aware",
    companySwipeId: "99f923f8-6725-58c0-ae66-3deb0b16248f",
    sourceSwipeTitle: "Static #2.png",
    assetBriefId: "brief_editorial_founder_authority",
    requirementIndex: 1,
  },
  {
    key: "problem-aware-03",
    awarenessLevel: "Problem-Aware",
    companySwipeId: "a23435d2-27a0-54ab-8e73-acf761834259",
    sourceSwipeTitle: "11.png",
    assetBriefId: "brief_editorial_wound_scene",
    requirementIndex: 1,
  },
  {
    key: "problem-aware-04",
    awarenessLevel: "Problem-Aware",
    companySwipeId: "3a342736-0437-53dc-a84b-16a50b3c03e6",
    sourceSwipeTitle: "fatigue.jpg",
    assetBriefId: "brief_editorial_wound_scene",
    requirementIndex: 1,
  },
  {
    key: "problem-aware-05",
    awarenessLevel: "Problem-Aware",
    companySwipeId: "f30c4cb6-de5d-5423-a6de-e36fa9fdb24e",
    sourceSwipeTitle: "fb_message_ad.jpg",
    assetBriefId: "brief_editorial_founder_authority",
    requirementIndex: 0,
  },
  {
    key: "solution-aware-03",
    awarenessLevel: "Solution-Aware",
    companySwipeId: "b849e92a-1a3d-5a7f-bec9-0c4f028a2d25",
    sourceSwipeTitle: "big_text.jpg",
    assetBriefId: "brief_editorial_wound_scene",
    requirementIndex: 1,
  },
  {
    key: "solution-aware-04",
    awarenessLevel: "Solution-Aware",
    companySwipeId: "99f923f8-6725-58c0-ae66-3deb0b16248f",
    sourceSwipeTitle: "Static #2.png",
    assetBriefId: "brief_editorial_founder_authority",
    requirementIndex: 1,
  },
  {
    key: "solution-aware-05",
    awarenessLevel: "Solution-Aware",
    companySwipeId: "f30c4cb6-de5d-5423-a6de-e36fa9fdb24e",
    sourceSwipeTitle: "fb_message_ad.jpg",
    assetBriefId: "brief_editorial_founder_authority",
    requirementIndex: 0,
  },
];

const onlyKeys = (process.env.ONLY_KEYS || "")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);
const runSuffix = (process.env.RUN_SUFFIX || "").trim();

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

async function waitForWorkflow(workflowRunId, timeoutMs = 25 * 60 * 1000) {
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
    if (ids.length !== 1) throw new Error(`Expected one asset id, got ${ids.length}`);
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

function buildSwipeAngle(job) {
  const outputKey = `${job.key}${runSuffix}`;
  return [
    `Awareness level: ${job.awarenessLevel}`,
    "",
    "Compliance:",
    "- No product reveal.",
    "- No product object, packaging, supplement bottle, capsule, pill, powder, sachet, label, supplement facts panel, price, offer, guarantee, rating, or purchase cue.",
    "- No mechanism reveal.",
    "- Do not explain ingredients, dosage, protocol architecture, hormone pathways, biological mechanisms, root-cause diagrams, comparison grids, or how the solution works.",
    "",
    "Operator note: intentionally provide only the awareness level plus compliance so the system/workspace context drives the creative.",
    `Run marker: tenor-awareness-only-${outputKey}-${Date.now()}.`,
  ].join("\n");
}

async function startJob(job) {
  const outputKey = `${job.key}${runSuffix}`;
  const payload = {
    clientId: CLIENT_ID,
    productId: PRODUCT_ID,
    campaignId: CAMPAIGN_ID,
    assetBriefId: job.assetBriefId,
    requirementIndex: job.requirementIndex,
    companySwipeId: job.companySwipeId,
    swipeRequiresProductImage: false,
    swipeContextMode: "minimal",
    swipeBrandName: "Tenor",
    swipeProductName: "withheld visual product",
    swipeHook: job.awarenessLevel,
    swipeAngle: buildSwipeAngle(job),
    aspectRatio: "1:1",
    count: 1,
  };
  const response = await authed("/swipes/generate-image-ad", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return { payload, response };
}

async function main() {
  mkdirSync(GENERATED_DIR, { recursive: true });
  await getBackendToken();

  const outputs = [];
  const selectedJobs = onlyKeys.length ? jobs.filter((job) => onlyKeys.includes(job.key)) : jobs;
  if (onlyKeys.length && selectedJobs.length !== onlyKeys.length) {
    throw new Error(`ONLY_KEYS contained unknown keys. Requested=${onlyKeys.join(",")} matched=${selectedJobs.map((job) => job.key).join(",")}`);
  }
  for (const job of selectedJobs) {
    const outputKey = `${job.key}${runSuffix}`;
    console.log(`Starting ${outputKey} (${job.awarenessLevel}) from ${job.sourceSwipeTitle}`);
    const { payload, response } = await startJob(job);
    console.log(`Started ${outputKey}: workflow ${response.workflow_run_id}`);
    const detail = await waitForWorkflow(response.workflow_run_id);
    const workflowPath = path.join(OUT_DIR, `workflow-${outputKey}.json`);
    writeFileSync(workflowPath, JSON.stringify(detail, null, 2) + "\n");

    const extracted = extractAssetId(detail);
    const asset = await resolveAsset(extracted.assetId);
    const ext = asset.content_type === "image/png" ? "png" : "jpg";
    const outputPath = path.join(GENERATED_DIR, `${outputKey}.${ext}`);
    downloadPublicAsset(asset.public_id, outputPath);
    console.log(`Downloaded ${outputKey}: ${outputPath}`);

    outputs.push({
      key: outputKey,
      awarenessLevel: job.awarenessLevel,
      source: {
        collectionName: "Default",
        companySwipeId: job.companySwipeId,
        sourceSwipeTitle: job.sourceSwipeTitle,
      },
      payload,
      workflow: response,
      result: {
        workflowRunId: response.workflow_run_id,
        temporalWorkflowId: response.temporal_workflow_id,
        assetId: asset.id,
        publicId: asset.public_id,
        publicUrl: `${API_BASE}/public/assets/${asset.public_id}`,
        localPath: outputPath,
        workflowPayloadOut: extracted.payloadOut,
        workflowDetailPath: workflowPath,
      },
    });
  }

  const manifest = {
    createdAt: new Date().toISOString(),
    outputDir: OUT_DIR,
    generatedDir: GENERATED_DIR,
    workspace: {
      workspaceName: "Tenor",
      campaignId: CAMPAIGN_ID,
      clientId: CLIENT_ID,
      productId: PRODUCT_ID,
    },
    validationIntent: {
      inputMode: "awareness_level_only_plus_compliance",
      onlyKeys,
      runSuffix,
      awarenessLevels: ["Problem-Aware", "Solution-Aware"],
      productImagesAllowed: false,
      mechanismRevealAllowed: false,
      creativeGuidanceAddedByOperator: false,
    },
    outputs,
  };
  const manifestPath = path.join(OUT_DIR, "manifest.json");
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n");
  console.log(`Wrote manifest: ${manifestPath}`);
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exit(1);
});
