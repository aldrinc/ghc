import { execFileSync } from "node:child_process";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const OUT_DIR = path.join(ROOT, "outputs/tenor-walk-away-trt-campaign-2026-05-02");
const SAMPLE_MANIFEST_PATH = path.join(OUT_DIR, "manifest.json");
const FULL_MANIFEST_PATH = path.join(OUT_DIR, "full-launch-manifest.json");
const GENERATED_DIR = path.join(OUT_DIR, "generated-full");
const REVIEW_DIR = "/Users/aldrinclement/Downloads/tenor-walk-away-trt-full-launch-review-2026-05-02";
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
const CAMPAIGN_NAME = "Tenor - Walk Away From TRT - 2026-05-02";
const ASSET_BRIEF_ID = "brief_editorial_wound_scene";
const BATCH_ID = "tenor-walk-away-trt-20260502";
const GENERATION_KEY = `batch:${BATCH_ID}`;
const PRESALES_URL = "https://shoptenorco.com/8b89a76d/daily-drive-essentials/walk-away-from-trt/";
const SALES_URL = "https://shoptenorco.com/8b89a76d/daily-drive-essentials/sales-page";

const DESTINATION_CONTEXT = {
  headline: '"I Watched My Patient Walk Away From TRT." 90 Days Later, His Labs Made My Hands Shake.',
  subheadline:
    "Board-certified MD reveals the four-factor cascade most doctors miss — and the daily protocol thousands of men 40+ are using to feel like themselves again, without the needles.",
  primaryProblem:
    "Men 40+ who feel like they are fading and feel stuck between underdosed natural products and the long-term cost, monitoring, injections, crashes, and dependency of TRT.",
  promise: "Understand the daily protocol men are trying before committing to TRT.",
  mechanismDisclosureLevel:
    "Partial mechanism; the destination article introduces the four-factor cascade behind low drive and why one-lever testosterone boosters are incomplete.",
  proofType:
    "Doctor-led advertorial using patient story, lab-result narrative, formula transparency, reported user experience, guarantee, and offer.",
  ctaUrgency:
    "Article-read CTA leading into claiming the protocol, with current offer framing around Save 30%, free welcome gifts, free shipping, and a 90-day guarantee.",
  compliancePosture: "Matches the downstream advertorial posture and funnel stage.",
  assetStage: "Ad to advertorial/listicle, before the sales page.",
  visualEmphasis: "Less text-heavy; let the visual carry more of the ad so the image can be evaluated clearly.",
};

const RUNS = [
  ["01-boss-babe", "d1de69e6-5795-5cba-9fb2-28ba5f99620f", "boss_babe.jpg", true],
  ["02-spanish-doctor-cta", "234f2a51-3140-5e86-b982-7a3c9d406a72", "spanish_doctor_cta.jpg", true],
  ["03-old-school", "a6422035-8a65-5074-ba35-69da84cb70d5", "old_school.jpg", true],
  ["04-static-3", "00e357f9-7953-5d6b-8b80-18a91e8a1510", "Static #3.png"],
  ["05-seven", "058b868e-4568-578e-99bc-21f0491ed671", "7.png"],
  ["06-derm-fag", "20c77ba2-f32c-5003-9c8f-539ba629c532", "derm_fag.jpg"],
  ["07-six", "32a41265-1b96-5096-b9f0-9a28b0ecef95", "6.png"],
  ["08-fatigue", "3a342736-0437-53dc-a84b-16a50b3c03e6", "fatigue.jpg"],
  ["09-static-4", "5e0bec7e-c4de-5135-a739-32de79c28f35", "Static #4.png"],
  ["10-care-bag", "5f0ac436-31e3-5f69-8756-41b3c433b731", "care_bag.jpg"],
  ["11-eight", "6111ae9b-95e0-5576-b2d7-3799f970a7e0", "8.png"],
  ["12-static-1", "74a2f8b1-2386-5213-ac31-16ee3860a08c", "Static #1.png"],
  ["13-static-2", "99f923f8-6725-58c0-ae66-3deb0b16248f", "Static #2.png"],
  ["14-eleven", "a23435d2-27a0-54ab-8e73-acf761834259", "11.png"],
  ["15-drawing", "a760221f-61bb-5f92-b4fc-d577eb9897ba", "drawing.jpg"],
  ["16-brush", "a9b9b792-bea4-579a-993f-95994908d8bb", "brush.jpg"],
  ["17-researchers", "adda0368-a6ef-5263-ae5c-1eef39732696", "researchers.jpg"],
  ["18-target-1", "b7787513-5b32-578e-85e3-b367207a4238", "target_1.jpg"],
  ["19-big-text", "b849e92a-1a3d-5a7f-bec9-0c4f028a2d25", "big_text.jpg"],
  ["20-nine", "b8d55c9d-f521-59b5-a1a0-a8aca5167cad", "9.png"],
  ["21-ten", "ca28769d-e1b3-5a34-9f55-f0bd70bb2c14", "10.png"],
  ["22-twelve", "cf80710e-7fc0-5323-9a3f-9c49fb8c3b80", "12.png"],
  ["23-raise-a-winner", "cfc68913-9b14-5b4a-a4ef-bb5ccbe602de", "raise_a_winner.jpg"],
  ["24-green", "e2ff843d-e853-55eb-b306-4398900615ef", "green.jpg"],
  ["25-grocery", "e358e68d-730a-5f8b-9bc9-fb7742985f43", "grocery.jpg"],
  ["26-women-health", "eab14ed3-2d63-528b-8611-f93c194d2a2d", "women_health.jpg"],
  ["27-health-cute-advertorial", "f1921084-1850-53af-8cc3-ae44c9691320", "health_cute_advertorial.jpg"],
  ["28-five", "f2d7c0da-d4ee-5636-80fc-5f80ac67ff8c", "5.png"],
  ["29-fb-message-ad", "f30c4cb6-de5d-5423-a6de-e36fa9fdb24e", "fb_message_ad.jpg"],
  ["30-researchers-alt", "adda0368-a6ef-5263-ae5c-1eef39732696", "researchers.jpg"],
].map(([key, companySwipeId, sourceSwipeTitle, approvedSample]) => ({
  key,
  awarenessLevel: "Solution-Aware",
  companySwipeId,
  sourceSwipeTitle,
  approvedSample: Boolean(approvedSample),
}));

const META_COPY = [
  ["Before You Start TRT", "Before making a long-term TRT decision, read the doctor-led article men are using to understand the daily protocol first."],
  ["Read This Before TRT", "The TRT decision can feel bigger than one lab result. Start with the article behind Tenor's daily protocol."],
  ["The TRT Decision", "Needles, monitoring, and long-term commitment are worth understanding before you decide. Read the presales article."],
  ["Walk Away From TRT?", "A doctor-led story about the daily protocol men are reading before committing to TRT."],
  ["Men 40+: Start Here", "If low drive has you weighing TRT, this article explains the protocol-first path."],
  ["Before The Needles", "Read the article about the step men are considering before a permanent TRT routine."],
  ["A Better First Read", "The destination article breaks down why some men try a daily protocol before TRT."],
  ["TRT Is A Big Call", "Before you choose injections, read the doctor-led Tenor article built for this exact decision."],
  ["Daily Protocol First", "Understand the daily protocol conversation before moving into a long-term TRT relationship."],
  ["The Article Men Read", "A direct read for men comparing natural support, low-drive frustration, and the TRT path."],
  ["Not Another Booster", "Read why the destination article frames the decision differently than a typical booster pitch."],
  ["Start With The Story", "A doctor-led patient story introduces the TRT decision and the daily protocol men are evaluating."],
  ["TRT Before And After", "Before choosing the needle path, read the article about what men are considering first."],
  ["The Protocol Question", "If the usual options feel incomplete, start with this Tenor article before making the call."],
  ["A 2-Minute TRT Read", "The presales article gives context before you commit to clinic visits and injections."],
  ["Think Before TRT", "Read the doctor-led article explaining the decision men are making before long-term TRT."],
  ["The First Step", "Before the sales page, start with the article that frames the problem, proof, and next step."],
  ["Needles For Life?", "The Tenor article is built around the decision men face before entering the TRT path."],
  ["Read The TRT Trap", "Understand the daily protocol story before you decide what comes next."],
  ["Start With Context", "The article connects the problem, promise, and proof before presenting the Tenor offer."],
  ["Before You Commit", "For men considering TRT, this article gives the decision context first."],
  ["The Daily Path", "Read about the daily protocol men are trying before making a TRT decision."],
  ["Doctor-Led Context", "A doctor-led advertorial frames the TRT decision and the Tenor protocol before the offer."],
  ["One Decision Read", "If TRT is on your mind, start with the article built to clarify the decision."],
  ["The Tenor Article", "Read the Walk Away From TRT presales article before moving to the sales page."],
  ["Know The Tradeoff", "The article walks through the tradeoff men consider before choosing TRT."],
  ["Before Clinic Mode", "Start with the Tenor article before committing to a long-term clinic routine."],
  ["Protocol Before TRT", "The presales page explains the protocol-first frame before the offer."],
  ["Read Before Needles", "A concise article for men comparing the TRT path with a daily protocol first."],
  ["Open The Article", "Start with the Walk Away From TRT article, then decide whether the Tenor protocol fits."],
];

let cachedToken = null;

function usage() {
  return [
    "Usage:",
    "  node run_full_launch.mjs generate",
    "  node run_full_launch.mjs stamp-batch",
    "  node run_full_launch.mjs create-specs",
    "  node run_full_launch.mjs validate-publish",
    "  node run_full_launch.mjs publish",
    "  node run_full_launch.mjs all",
  ].join("\n");
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

function readFullManifest() {
  if (!existsSync(FULL_MANIFEST_PATH)) {
    return {
      createdAt: new Date().toISOString(),
      campaignId: CAMPAIGN_ID,
      campaignName: CAMPAIGN_NAME,
      batchId: BATCH_ID,
      generationKey: GENERATION_KEY,
      outputDir: OUT_DIR,
      generatedDir: GENERATED_DIR,
      reviewDir: REVIEW_DIR,
      presalesUrl: PRESALES_URL,
      salesUrl: SALES_URL,
      destinationContext: DESTINATION_CONTEXT,
      outputs: [],
    };
  }
  return JSON.parse(readFileSync(FULL_MANIFEST_PATH, "utf8"));
}

function writeFullManifest(manifest) {
  mkdirSync(OUT_DIR, { recursive: true });
  writeFileSync(
    FULL_MANIFEST_PATH,
    JSON.stringify({ ...manifest, updatedAt: new Date().toISOString() }, null, 2) + "\n",
  );
}

function sampleByKey() {
  if (!existsSync(SAMPLE_MANIFEST_PATH)) return new Map();
  const sample = JSON.parse(readFileSync(SAMPLE_MANIFEST_PATH, "utf8"));
  return new Map((sample.outputs || []).map((output) => [output.key, output]));
}

function swipeAngle(awarenessLevel, runKey) {
  return [
    `Awareness level: ${awarenessLevel}`,
    "",
    "Downstream destination context:",
    `Headline: ${DESTINATION_CONTEXT.headline}`,
    `Subheadline: ${DESTINATION_CONTEXT.subheadline}`,
    `Primary problem: ${DESTINATION_CONTEXT.primaryProblem}`,
    `Promise: ${DESTINATION_CONTEXT.promise}`,
    `Mechanism disclosure level: ${DESTINATION_CONTEXT.mechanismDisclosureLevel}`,
    `Proof type: ${DESTINATION_CONTEXT.proofType}`,
    `CTA / urgency: ${DESTINATION_CONTEXT.ctaUrgency}`,
    `Compliance posture: ${DESTINATION_CONTEXT.compliancePosture}`,
    `Asset stage: ${DESTINATION_CONTEXT.assetStage}`,
    `Visual emphasis: ${DESTINATION_CONTEXT.visualEmphasis}`,
    "",
    `Run marker: tenor-walk-away-trt-congruence-${runKey}-${Date.now()}.`,
  ].join("\n");
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

async function getCampaignAssets() {
  return authed(
    `/assets?campaignId=${encodeURIComponent(CAMPAIGN_ID)}&productId=${encodeURIComponent(PRODUCT_ID)}&assetKind=image`,
  );
}

async function resolveAsset(assetId) {
  const rows = await getCampaignAssets();
  const row = rows.find((asset) => asset.id === assetId);
  if (!row?.public_id) throw new Error(`Could not resolve generated public_id for asset ${assetId}`);
  return row;
}

function downloadPublicAsset(publicId, outputPath) {
  execFileSync("curl", ["-sS", "-L", `${API_BASE}/public/assets/${publicId}`, "-o", outputPath], {
    stdio: "inherit",
  });
}

function ensureDirs() {
  mkdirSync(OUT_DIR, { recursive: true });
  mkdirSync(GENERATED_DIR, { recursive: true });
  mkdirSync(path.join(REVIEW_DIR, "generated"), { recursive: true });
}

async function assertCampaign() {
  await getBackendToken();
  const campaign = await authed(`/campaigns/${encodeURIComponent(CAMPAIGN_ID)}`);
  if (campaign.name !== CAMPAIGN_NAME) {
    throw new Error(`Unexpected campaign name for ${CAMPAIGN_ID}: ${campaign.name}`);
  }
}

function copyOrDownload({ publicId, sourcePath, localPath, reviewPath }) {
  if (sourcePath && existsSync(sourcePath)) {
    copyFileSync(sourcePath, localPath);
  } else {
    downloadPublicAsset(publicId, localPath);
  }
  copyFileSync(localPath, reviewPath);
}

async function cmdGenerate() {
  ensureDirs();
  await assertCampaign();
  const samples = sampleByKey();
  const manifest = readFullManifest();
  const outputs = Array.isArray(manifest.outputs) ? manifest.outputs : [];
  const completed = new Set(outputs.map((output) => output.key));

  for (const run of RUNS) {
    if (completed.has(run.key)) {
      console.log(`Skipping ${run.key}; already present in full manifest.`);
      continue;
    }

    const copy = META_COPY[outputs.length];
    if (!copy) throw new Error(`Missing Meta copy row for ${run.key}.`);
    const [headline, primaryText] = copy;

    if (run.approvedSample) {
      const sample = samples.get(run.key);
      if (!sample?.result?.assetId || !sample?.result?.publicId) {
        throw new Error(`Approved sample ${run.key} is missing from ${SAMPLE_MANIFEST_PATH}`);
      }
      const localPath = path.join(GENERATED_DIR, `${run.key}.jpg`);
      const reviewPath = path.join(REVIEW_DIR, "generated", `${run.key}.jpg`);
      copyOrDownload({
        publicId: sample.result.publicId,
        sourcePath: sample.result.localPath,
        localPath,
        reviewPath,
      });
      outputs.push({
        key: run.key,
        adId: `WA-${String(outputs.length + 1).padStart(2, "0")}`,
        awarenessLevel: run.awarenessLevel,
        source: {
          companySwipeId: run.companySwipeId,
          sourceSwipeTitle: run.sourceSwipeTitle,
          assetBriefId: ASSET_BRIEF_ID,
          requirementIndex: 1,
          approvedSample: true,
        },
        meta: {
          headline,
          primaryText,
          destinationUrl: PRESALES_URL,
          callToActionType: "LEARN_MORE",
        },
        payload: sample.payload,
        result: {
          assetId: sample.result.assetId,
          publicId: sample.result.publicId,
          publicUrl: `${API_BASE}/public/assets/${sample.result.publicId}`,
          localPath,
          reviewPath,
          workflowRunId: sample.workflow?.workflow_run_id || null,
          temporalWorkflowId: sample.workflow?.temporal_workflow_id || null,
          workflowPayloadOut: sample.result.workflowPayloadOut || null,
          reusedApprovedSample: true,
        },
      });
      writeFullManifest({ ...manifest, outputs });
      completed.add(run.key);
      console.log(`Reused approved sample ${run.key}`);
      continue;
    }

    const payload = {
      clientId: CLIENT_ID,
      productId: PRODUCT_ID,
      campaignId: CAMPAIGN_ID,
      assetBriefId: ASSET_BRIEF_ID,
      requirementIndex: 1,
      companySwipeId: run.companySwipeId,
      swipeRequiresProductImage: false,
      swipeContextMode: "minimal",
      swipeBrandName: "Tenor",
      swipeProductName: "Tenor",
      swipeHook: run.awarenessLevel,
      swipeAngle: swipeAngle(run.awarenessLevel, run.key),
      aspectRatio: "1:1",
      count: 1,
    };

    console.log(`Generating ${run.key} with source ${run.sourceSwipeTitle}`);
    const started = await authed("/swipes/generate-image-ad", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const detail = await waitForWorkflow(started.workflow_run_id);
    const workflowPath = path.join(OUT_DIR, `workflow-full-${run.key}.json`);
    writeFileSync(workflowPath, JSON.stringify(detail, null, 2) + "\n");
    const { assetId, payloadOut } = extractAssetId(detail);
    const asset = await resolveAsset(assetId);
    const localPath = path.join(GENERATED_DIR, `${run.key}.jpg`);
    const reviewPath = path.join(REVIEW_DIR, "generated", `${run.key}.jpg`);
    downloadPublicAsset(asset.public_id, localPath);
    copyFileSync(localPath, reviewPath);

    outputs.push({
      key: run.key,
      adId: `WA-${String(outputs.length + 1).padStart(2, "0")}`,
      awarenessLevel: run.awarenessLevel,
      source: {
        companySwipeId: run.companySwipeId,
        sourceSwipeTitle: run.sourceSwipeTitle,
        assetBriefId: ASSET_BRIEF_ID,
        requirementIndex: 1,
      },
      meta: {
        headline,
        primaryText,
        destinationUrl: PRESALES_URL,
        callToActionType: "LEARN_MORE",
      },
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
    });
    writeFullManifest({ ...manifest, outputs });
    completed.add(run.key);
  }

  if (outputs.length !== 30) {
    throw new Error(`Expected 30 outputs; found ${outputs.length}`);
  }
  writeFullManifest({ ...manifest, outputs });
  console.log(JSON.stringify({ campaignId: CAMPAIGN_ID, generatedCount: outputs.length, manifestPath: FULL_MANIFEST_PATH, reviewDir: REVIEW_DIR }, null, 2));
}

function requireFullOutputs() {
  const manifest = readFullManifest();
  const outputs = Array.isArray(manifest.outputs) ? manifest.outputs : [];
  if (outputs.length !== 30) {
    throw new Error(`Expected 30 outputs in ${FULL_MANIFEST_PATH}; found ${outputs.length}.`);
  }
  const assetIds = outputs.map((output) => output.result?.assetId).filter(Boolean);
  if (assetIds.length !== 30 || new Set(assetIds).size !== 30) {
    throw new Error(`Expected 30 unique asset ids; found ${assetIds.length} ids and ${new Set(assetIds).size} unique ids.`);
  }
  return { manifest, outputs, assetIds };
}

function stampBatchViaSsh(assetIds) {
  const payloadPath = path.join(OUT_DIR, "batch-stamp-input.json");
  writeFileSync(payloadPath, JSON.stringify({ campaignId: CAMPAIGN_ID, batchId: BATCH_ID, assetIds }, null, 2) + "\n");
  const remotePayloadPath = "/root/tmp/tenor-walk-away-trt-batch-stamp.json";
  execFileSync("scp", [
    "-i",
    path.join(os.homedir(), ".ssh/hetzner_prod"),
    "-o",
    "BatchMode=yes",
    payloadPath,
    `root@api.moshq.app:${remotePayloadPath}`,
  ], { stdio: "inherit" });

  const py = String.raw`
import json
from pathlib import Path
from sqlalchemy import select
from app.db.base import session_scope
from app.db.models import Asset

payload = json.loads(Path("${remotePayloadPath}").read_text())
campaign_id = payload["campaignId"]
batch_id = payload["batchId"]
asset_ids = payload["assetIds"]

with session_scope() as session:
    assets = session.scalars(
        select(Asset).where(Asset.campaign_id == campaign_id, Asset.id.in_(asset_ids))
    ).all()
    found = {str(asset.id) for asset in assets}
    missing = sorted(set(asset_ids).difference(found))
    if missing:
        raise RuntimeError(f"Missing campaign assets: {missing}")
    for asset in assets:
        metadata = dict(asset.ai_metadata or {})
        metadata["creativeGenerationBatchId"] = batch_id
        metadata["assetBriefId"] = metadata.get("assetBriefId") or "${ASSET_BRIEF_ID}"
        metadata["manualLaunchBatchStampedAt"] = "${new Date().toISOString()}"
        asset.ai_metadata = metadata
        session.add(asset)
    session.commit()
    print(json.dumps({"status": "ok", "batchId": batch_id, "assetCount": len(assets)}))
`;
  const result = execFileSync("ssh", [
    "-i",
    path.join(os.homedir(), ".ssh/hetzner_prod"),
    "-o",
    "BatchMode=yes",
    "root@api.moshq.app",
    "cd /opt/apps/mos-api/mos/backend && set -a && . /etc/cloudhand/env/mos-api.env && set +a && .venv/bin/python -",
  ], { input: py, encoding: "utf8" });
  return JSON.parse(result.trim().split(/\r?\n/).at(-1));
}

async function cmdStampBatch() {
  await assertCampaign();
  const { outputs, assetIds } = requireFullOutputs();
  const stamp = stampBatchViaSsh(assetIds);
  const assets = await getCampaignAssets();
  const byId = new Map(assets.map((asset) => [asset.id, asset]));
  const mismatched = outputs
    .map((output) => byId.get(output.result.assetId))
    .filter((asset) => asset?.ai_metadata?.creativeGenerationBatchId !== BATCH_ID)
    .map((asset) => asset.id);
  if (mismatched.length) {
    throw new Error(`Batch stamp verification failed for assets: ${mismatched.join(", ")}`);
  }
  const manifest = readFullManifest();
  writeFullManifest({ ...manifest, batchStamp: stamp });
  console.log(JSON.stringify({ campaignId: CAMPAIGN_ID, generationKey: GENERATION_KEY, stamp }, null, 2));
}

async function getCreativeSpecs() {
  return authed(`/meta/specs/creatives?campaignId=${encodeURIComponent(CAMPAIGN_ID)}`);
}

async function getAdSetSpecs() {
  return authed(`/meta/specs/adsets?campaignId=${encodeURIComponent(CAMPAIGN_ID)}`);
}

function specAssetId(spec) {
  return spec.asset_id || spec.assetId || null;
}

function specDestinationUrl(spec) {
  return spec.destination_url || spec.destinationUrl || null;
}

function specPrimaryText(spec) {
  return spec.primary_text || spec.primaryText || null;
}

function specHeadline(spec) {
  return spec.headline || null;
}

function specMetadata(spec) {
  if (spec.metadata_json && typeof spec.metadata_json === "object") return spec.metadata_json;
  if (spec.metadata && typeof spec.metadata === "object") return spec.metadata;
  return {};
}

function adsetId(spec) {
  return spec.id || spec.adsetSpecId || null;
}

function adsetPromotedObject(spec) {
  return spec.promoted_object || spec.promotedObject || null;
}

async function getActiveMetaConfig() {
  return authed(`/meta/clients/${encodeURIComponent(CLIENT_ID)}/active-config`);
}

async function upsertCreativeSpec(output, existingByAssetId) {
  const assetId = output.result.assetId;
  const primaryText = output.meta.primaryText;
  const headline = output.meta.headline;
  const body = {
    campaignId: CAMPAIGN_ID,
    name: `${output.adId} - ${headline}`,
    primaryText,
    headline,
    description: null,
    callToActionType: output.meta.callToActionType,
    destinationUrl: output.meta.destinationUrl,
    status: "draft",
    metadata: {
      externalRoutingAdId: output.adId,
      externalDestinationKey: "walk_away_trt_presales",
      externalFinalUrl: output.meta.destinationUrl,
      externalRoutingSource: FULL_MANIFEST_PATH,
      awarenessLevel: output.awarenessLevel,
      batchId: BATCH_ID,
      sourceSwipeTitle: output.source.sourceSwipeTitle,
      sourceCompanySwipeId: output.source.companySwipeId,
    },
  };
  const existing = existingByAssetId.get(assetId);
  if (!existing) {
    const created = await authed("/meta/specs/creatives", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assetId, ...body }),
    });
    return { action: "created", adId: output.adId, assetId, creativeSpecId: created.id || null };
  }
  const mismatched = [
    specDestinationUrl(existing) !== body.destinationUrl,
    specPrimaryText(existing) !== primaryText,
    specHeadline(existing) !== headline,
  ].some(Boolean);
  const metadata = specMetadata(existing);
  const needsMetadata = metadata.batchId !== BATCH_ID || metadata.externalRoutingAdId !== output.adId;
  if (!mismatched && !needsMetadata) {
    return { action: "verified", adId: output.adId, assetId, creativeSpecId: existing.id || null };
  }
  const updated = await authed(`/meta/specs/creatives/${encodeURIComponent(existing.id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return { action: "updated", adId: output.adId, assetId, creativeSpecId: updated.id || existing.id || null };
}

async function upsertAdSetSpecs(existingAdsets) {
  const activeConfig = await getActiveMetaConfig();
  const pixelId = activeConfig?.pixelId;
  if (!pixelId) {
    throw new Error(`Active Meta config ${activeConfig?.id || ""} is missing pixelId.`);
  }
  const promotedObject = {
    pixel_id: pixelId,
    custom_event_type: "PURCHASE",
  };
  const targeting = {
    age_min: 18,
    age_max: 65,
    age_range: [18, 65],
    geo_locations: {
      countries: ["US", "CA", "GB", "AU"],
      location_types: ["home", "recent"],
    },
    brand_safety_content_filter_levels: ["FACEBOOK_RELAXED"],
    targeting_automation: {
      advantage_audience: 1,
      individual_setting: {
        age: 1,
        gender: 1,
      },
    },
  };
  const attributionSpec = [
    { event_type: "CLICK_THROUGH", window_days: 7 },
    { event_type: "VIEW_THROUGH", window_days: 1 },
    { event_type: "ENGAGED_VIDEO_VIEW", window_days: 1 },
  ];

  const byBucket = new Map();
  for (const spec of existingAdsets || []) {
    const bucketIndex = Number(specMetadata(spec).bucketIndex);
    const bucketCount = Number(specMetadata(spec).bucketCount);
    if (specMetadata(spec).templateId !== "default-broad-int-cbo" || bucketCount !== 5 || bucketIndex < 1 || bucketIndex > 5) {
      continue;
    }
    if (byBucket.has(bucketIndex)) {
      throw new Error(`Duplicate default-broad-int-cbo ad set spec for bucket ${bucketIndex}`);
    }
    byBucket.set(bucketIndex, spec);
  }

  const results = [];
  for (let bucketIndex = 1; bucketIndex <= 5; bucketIndex += 1) {
    const body = {
      campaignId: CAMPAIGN_ID,
      name: `CBO Bucket ${bucketIndex}`,
      status: "draft",
      optimizationGoal: "OFFSITE_CONVERSIONS",
      billingEvent: "IMPRESSIONS",
      targeting,
      placements: null,
      dailyBudget: null,
      lifetimeBudget: null,
      promotedObject,
      conversionDomain: "shoptenorco.com",
      metadata: {
        templateId: "default-broad-int-cbo",
        campaignDailyBudget: 10000,
        bucketIndex,
        bucketCount: 5,
        bucketStrategy: "deterministic_round_robin",
        attributionSpec,
        source: "tenor_walk_away_trt_full_launch_20260502",
      },
    };
    const existing = byBucket.get(bucketIndex);
    if (!existing) {
      const created = await authed("/meta/specs/adsets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      results.push({ action: "created", bucketIndex, adsetSpecId: created.id || null });
      continue;
    }
    const metadata = specMetadata(existing);
    if (
      existing.name === body.name
      && existing.optimization_goal === body.optimizationGoal
      && existing.billing_event === body.billingEvent
      && JSON.stringify(adsetPromotedObject(existing)) === JSON.stringify(promotedObject)
      && metadata.source === body.metadata.source
    ) {
      results.push({ action: "verified", bucketIndex, adsetSpecId: adsetId(existing) });
      continue;
    }
    const updated = await authed(`/meta/specs/adsets/${encodeURIComponent(existing.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    results.push({ action: "updated", bucketIndex, adsetSpecId: updated.id || existing.id || null });
  }
  return results;
}

async function cmdCreateSpecs() {
  await assertCampaign();
  const { outputs } = requireFullOutputs();
  const assets = await getCampaignAssets();
  const byId = new Map(assets.map((asset) => [asset.id, asset]));
  const missingBatch = outputs
    .map((output) => byId.get(output.result.assetId))
    .filter((asset) => asset?.ai_metadata?.creativeGenerationBatchId !== BATCH_ID)
    .map((asset) => asset?.id || "missing");
  if (missingBatch.length) {
    throw new Error(`Run stamp-batch before create-specs. Missing batch on: ${missingBatch.join(", ")}`);
  }

  const creativeSpecs = await getCreativeSpecs();
  const creativeByAssetId = new Map();
  for (const spec of creativeSpecs || []) {
    const assetId = specAssetId(spec);
    if (assetId) creativeByAssetId.set(assetId, spec);
  }

  const creativeResults = [];
  for (const output of outputs) {
    creativeResults.push(await upsertCreativeSpec(output, creativeByAssetId));
  }
  const adsetResults = await upsertAdSetSpecs(await getAdSetSpecs());
  const specsPath = path.join(OUT_DIR, "full-launch-specs.json");
  writeFileSync(specsPath, JSON.stringify({
    campaignId: CAMPAIGN_ID,
    generationKey: GENERATION_KEY,
    createdAt: new Date().toISOString(),
    creativeSpecs: creativeResults,
    adsetSpecs: adsetResults,
  }, null, 2) + "\n");
  console.log(JSON.stringify({
    campaignId: CAMPAIGN_ID,
    generationKey: GENERATION_KEY,
    creativeSpecs: creativeResults.reduce((acc, row) => ({ ...acc, [row.action]: (acc[row.action] || 0) + 1 }), {}),
    adsetSpecs: adsetResults.reduce((acc, row) => ({ ...acc, [row.action]: (acc[row.action] || 0) + 1 }), {}),
    specsPath,
  }, null, 2));
}

function publishPayload() {
  return {
    generationKey: GENERATION_KEY,
    publishBaseUrl: "https://shop.shoptenorco.com",
    campaignName: "Tenor - Walk Away From TRT - Meta Launch - 2026-05-02",
    campaignObjective: "OUTCOME_SALES",
    buyingType: "AUCTION",
    specialAdCategories: [],
    campaignDailyBudget: 10000,
    bucketCount: 5,
    bucketDestinationUrls: [],
  };
}

async function cmdValidatePublish() {
  await assertCampaign();
  requireFullOutputs();
  const payload = publishPayload();
  const response = await authed(`/meta/campaigns/${encodeURIComponent(CAMPAIGN_ID)}/publish-plan/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const validationPath = path.join(OUT_DIR, "full-launch-publish-validation.json");
  writeFileSync(validationPath, JSON.stringify({ payload, response }, null, 2) + "\n");
  if (!response.ok) {
    throw new Error(`Publish validation blocked. See ${validationPath}: ${JSON.stringify(response.blockers || response.items || [])}`);
  }
  console.log(JSON.stringify({
    campaignId: CAMPAIGN_ID,
    ok: response.ok,
    includedCount: response.includedCount,
    adsetCount: response.adsetCount,
    publishDomain: response.publishDomain,
    validationPath,
  }, null, 2));
}

async function cmdPublish() {
  await assertCampaign();
  requireFullOutputs();
  const payload = publishPayload();
  const response = await authed(`/meta/campaigns/${encodeURIComponent(CAMPAIGN_ID)}/publish-runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const publishPath = path.join(OUT_DIR, "full-launch-publish-run-response.json");
  writeFileSync(publishPath, JSON.stringify({ payload, response }, null, 2) + "\n");
  console.log(JSON.stringify({
    campaignId: CAMPAIGN_ID,
    publishRunId: response.id || null,
    status: response.status,
    metaCampaignId: response.metaCampaignId || response.meta_campaign_id || null,
    itemCount: Array.isArray(response.items) ? response.items.length : null,
    failedItems: Array.isArray(response.items) ? response.items.filter((item) => item.status === "failed").length : null,
    publishPath,
  }, null, 2));
  if (response.status !== "published") {
    throw new Error(`Meta publish run did not finish as published. Status=${response.status}; see ${publishPath}`);
  }
}

async function main() {
  const command = process.argv[2];
  if (!command || command === "help" || command === "--help") {
    console.log(usage());
    return;
  }
  if (command === "generate") return cmdGenerate();
  if (command === "stamp-batch") return cmdStampBatch();
  if (command === "create-specs") return cmdCreateSpecs();
  if (command === "validate-publish") return cmdValidatePublish();
  if (command === "publish") return cmdPublish();
  if (command === "all") {
    await cmdGenerate();
    await cmdStampBatch();
    await cmdCreateSpecs();
    await cmdValidatePublish();
    await cmdPublish();
    return;
  }
  throw new Error(`Unknown command: ${command}\n${usage()}`);
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exitCode = 1;
});
