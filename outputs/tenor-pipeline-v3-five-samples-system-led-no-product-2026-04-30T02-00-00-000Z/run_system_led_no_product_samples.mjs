import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const OUT_DIR =
  "/Users/aldrinclement/Documents/programming/marketi/outputs/tenor-pipeline-v3-five-samples-system-led-no-product-2026-04-30T02-00-00-000Z";
const GENERATED_DIR = path.join(OUT_DIR, "generated-full-meta");
const AUTH_FILE = path.join(ROOT, ".env.mos-test-auth");
const META_ADS_PATH = "/Users/aldrinclement/Downloads/pipeline-run-v3/phase-9-ads/meta-ads.md";

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
const resumeWorkflowRunIds = {};

const jobs = [
  {
    adId: "AV-A1",
    assetBriefId: "brief_editorial_wound_scene",
    requirementIndex: 1,
    companySwipeId: "a23435d2-27a0-54ab-8e73-acf761834259",
    sourceSwipeTitle: "11.png",
  },
  {
    adId: "AV-C1",
    assetBriefId: "brief_editorial_founder_authority",
    requirementIndex: 1,
    companySwipeId: "99f923f8-6725-58c0-ae66-3deb0b16248f",
    sourceSwipeTitle: "Static #2.png",
  },
  {
    adId: "L2",
    assetBriefId: "brief_editorial_wound_scene",
    requirementIndex: 1,
    companySwipeId: "b849e92a-1a3d-5a7f-bec9-0c4f028a2d25",
    sourceSwipeTitle: "big_text.jpg",
  },
  {
    adId: "L8",
    assetBriefId: "brief_editorial_wound_scene",
    requirementIndex: 1,
    companySwipeId: "3a342736-0437-53dc-a84b-16a50b3c03e6",
    sourceSwipeTitle: "fatigue.jpg",
  },
  {
    adId: "PDP2",
    assetBriefId: "brief_editorial_founder_authority",
    requirementIndex: 0,
    companySwipeId: "f30c4cb6-de5d-5423-a6de-e36fa9fdb24e",
    sourceSwipeTitle: "fb_message_ad.jpg",
  },
];

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

function extractAdBlock(metaAdsMarkdown, adId) {
  const escaped = adId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(`(?:^|\\n)(### AD ${escaped}[^\\n]*\\n[\\s\\S]*?)(?=\\n---\\n\\n(?:### AD |## |#)|\\s*$)`);
  const match = metaAdsMarkdown.match(re);
  if (!match) throw new Error(`Could not find ${adId} in ${META_ADS_PATH}`);
  return match[1].trim();
}

function fieldFromBlock(block, label) {
  const re = new RegExp(`^\\*\\*${label}:\\*\\*\\s*(.+)$`, "m");
  const match = block.match(re);
  return match ? match[1].trim() : null;
}

function buildSwipeAngle(adId, rawAdBlock) {
  return [
    `Meta ad copy/context from ${META_ADS_PATH}:`,
    "",
    rawAdBlock,
    "",
    "Compliance constraints:",
    "- Do not show the product image or any product object.",
    "- Do not show bottles, jars, boxes, pouches, labels, supplement facts panels, capsules, pills, powders, scoops, sachets, packaging, price, guarantee, ratings, or purchase/offer cues.",
    "- Do not reveal the product mechanism or solution mechanics: no ingredient list, dosage, protocol architecture, hormone pathway, biological system diagram, comparison grid, checklist, or explanation of how the solution works.",
    "- Do not invent clinical data, patient data, study citations, endorsements, testimonials, lab values, social metrics, names, ages, dates, or URLs beyond the provided Meta ad copy/context.",
    "- Final destination URL is pending.",
    "",
    `Run marker: pipeline-v3-system-led-full-meta-${adId}-no-product-${Date.now()}.`,
  ].join("\n");
}

function downloadPublicAsset(publicId, outputPath) {
  execFileSync("curl", ["-sS", "-L", `${API_BASE}/public/assets/${publicId}`, "-o", outputPath], {
    stdio: "inherit",
  });
}

function outputPathForAd(adId, ext = "jpg") {
  return path.join(GENERATED_DIR, `${adId.toLowerCase()}-system-led-full-meta-no-product.${ext}`);
}

async function main() {
  mkdirSync(GENERATED_DIR, { recursive: true });
  await getBackendToken();

  const metaAdsMarkdown = readFileSync(META_ADS_PATH, "utf8");
  const outputs = [];

  for (const job of jobs) {
    const rawAdBlock = extractAdBlock(metaAdsMarkdown, job.adId);
    const headline = fieldFromBlock(rawAdBlock, "Headline") || job.adId;
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
      swipeProductName: "Tenor Daily Drive Essentials",
      swipeHook: headline.replace(/\s*\([^)]*\)\s*$/, ""),
      swipeAngle: buildSwipeAngle(job.adId, rawAdBlock),
      aspectRatio: "1:1",
      count: 1,
    };

    let response = null;
    const existingWorkflowPath = path.join(OUT_DIR, `workflow-full-meta-${job.adId.toLowerCase()}.json`);
    const existingOutputPath = outputPathForAd(job.adId);
    if (readableFile(existingWorkflowPath) && readableFile(existingOutputPath)) {
      const existingDetail = JSON.parse(readFileSync(existingWorkflowPath, "utf8"));
      const extracted = extractAssetId(existingDetail);
      const asset = await resolveAsset(extracted.assetId);
      outputs.push(buildOutputRecord({ job, rawAdBlock, headline, payload, response: {
        workflow_run_id: existingDetail.run.id,
        temporal_workflow_id: existingDetail.run.temporal_workflow_id,
      }, asset, outputPath: existingOutputPath, extracted, workflowPath: existingWorkflowPath }));
      console.log(`Keeping existing ${job.adId}: ${existingOutputPath}`);
      continue;
    }

    const resumeWorkflowRunId = resumeWorkflowRunIds[job.adId];
    if (resumeWorkflowRunId) {
      response = {
        workflow_run_id: resumeWorkflowRunId,
        temporal_workflow_id: null,
      };
      console.log(`Resuming ${job.adId}: workflow ${resumeWorkflowRunId}`);
    } else {
      console.log(`Starting ${job.adId} with source ${job.sourceSwipeTitle}`);
      response = await authed("/swipes/generate-image-ad", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      console.log(`Started ${job.adId}: workflow ${response.workflow_run_id}`);
    }

    const detail = await waitForWorkflow(response.workflow_run_id);
    const extracted = extractAssetId(detail);
    const asset = await resolveAsset(extracted.assetId);
    const ext = asset.content_type === "image/png" ? "png" : "jpg";
    const outputPath = outputPathForAd(job.adId, ext);
    downloadPublicAsset(asset.public_id, outputPath);
    const workflowPath = existingWorkflowPath;
    writeFileSync(workflowPath, JSON.stringify(detail, null, 2) + "\n");

    outputs.push(buildOutputRecord({ job, rawAdBlock, headline, payload, response, asset, outputPath, extracted, workflowPath }));
    console.log(`Downloaded ${job.adId}: ${outputPath}`);
  }

  const manifest = {
    createdAt: new Date().toISOString(),
    outputDir: OUT_DIR,
    generatedDir: GENERATED_DIR,
    pipeline: {
      metaAdsPath: META_ADS_PATH,
      payloadMode: "system_led_full_meta_ad_context_plus_compliance_constraints",
    },
    workspace: {
      campaignId: CAMPAIGN_ID,
      clientId: CLIENT_ID,
      productId: PRODUCT_ID,
      workspaceName: "Tenor",
    },
    validationIntent: {
      sourceCollection: "Default",
      productImagesAllowed: false,
      mechanismRevealAllowed: false,
      creativeGuidanceAddedByOperator: false,
    },
    outputs,
  };
  const manifestPath = path.join(OUT_DIR, "manifest-full-meta.json");
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n");
  console.log(`Wrote manifest: ${manifestPath}`);
}

function readableFile(filePath) {
  try {
    readFileSync(filePath);
    return true;
  } catch {
    return false;
  }
}

function buildOutputRecord({ job, rawAdBlock, headline, payload, response, asset, outputPath, extracted, workflowPath }) {
  return {
    adId: job.adId,
    source: {
      collectionName: "Default",
      companySwipeId: job.companySwipeId,
      sourceSwipeTitle: job.sourceSwipeTitle,
    },
    selectedAd: {
      rawMarkdown: rawAdBlock,
      headline,
      primaryText: fieldFromBlock(rawAdBlock, "Primary Text"),
      destination: fieldFromBlock(rawAdBlock, "Destination"),
      hookType: fieldFromBlock(rawAdBlock, "Hook Type"),
      format: fieldFromBlock(rawAdBlock, "Format"),
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
  };
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exit(1);
});
