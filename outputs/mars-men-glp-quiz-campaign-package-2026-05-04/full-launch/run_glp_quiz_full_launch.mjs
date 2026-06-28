import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  linkSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const PACKAGE_DIR = path.join(ROOT, "outputs/mars-men-glp-quiz-campaign-package-2026-05-04");
const OUT_DIR = path.join(PACKAGE_DIR, "full-launch");
const GENERATED_DIR = path.join(OUT_DIR, "generated");
const REVIEW_DIR = path.join(OUT_DIR, "review");
const AUTH_FILE = path.join(ROOT, ".env.mos-test-auth");
const STATE_PATH = path.join(OUT_DIR, "campaign-state.json");
const MANIFEST_PATH = path.join(OUT_DIR, "full-launch-manifest.json");

const API_BASE = "https://api.moshq.app";
const CLERK_BASE = "https://immune-turtle-79.clerk.accounts.dev/v1";
const CLERK_QUERY = "__clerk_api_version=2025-11-10&_clerk_js_version=5.125.10";
const ORIGIN_HEADERS = {
  Origin: "https://moshq.app",
  Referer: "https://moshq.app/",
};

const CLIENT_ID = "70124684-505f-48af-a25c-5f7a79601fa0";
const PRODUCT_ID = "8b89a76d-069c-41a6-be38-b7e4f4483460";
const CAMPAIGN_NAME = "Tenor - GLP + Quiz - GPT Image 2 - 2026-05-05";
const META_CAMPAIGN_NAME = "Tenor - GLP + Quiz - GPT Image 2 - 2026-05-05";
const BATCH_ID = "tenor-glp-quiz-gpt-image2-20260505";
const GENERATION_KEY = `batch:${BATCH_ID}`;
const EXPERIMENT_ID = "tenor-glp-quiz-gpt-image2";
const GLP_BRIEF_ID = "brief_glp_listicle_swipe_image2";
const QUIZ_BRIEF_ID = "brief_quiz_funnel_swipe_image2";
const STAGING_FUNNEL_ID = "be65d76e-ced9-4948-9465-18723c8446fd";
const STAGING_PAGE_ID = "ab3102f4-a179-410a-9eb0-66aa3020cafc";
const STAGE_ONE_MODEL = "gemini-3.1-pro-preview";
const RENDER_MODEL_ID = "gpt-image-2";
const NANOBANANA_RENDER_MODEL_ID = "gemini-3.1-flash-image-preview";
const NANOBANANA_RENDER_MODEL_ID_USED = `models/${NANOBANANA_RENDER_MODEL_ID}`;
const AUTHORIZED_NANOBANANA_FALLBACK_ROW_KEYS = new Set(["03-TENOR-COPY001-C004"]);
const CREATIVE_IDS_REQUIRING_PRODUCT_REFERENCE = new Set([
  "C005",
  "C006",
  "C009",
  "C012",
  "C013",
  "C017",
  "C018",
  "C019",
  "C020",
  "C021",
  "C022",
  "C023",
  "C024",
  "C025",
]);
const PUBLISH_BASE_URL = "https://shop.shoptenorco.com";
const GLP_PRESALE_URL = "https://shoptenorco.com/8b89a76d/daily-drive-essentials/10-reasons-glp/";
const QUIZ_PRESALE_URL = "https://shoptenorco.com/8b89a76d/daily-drive-essentials/quiz/";
const SALES_URL =
  "https://shoptenorco.com/8b89a76d/daily-drive-essentials/sales-page/?selling_plan=2948432039";

let cachedToken = null;

function ensureDirs() {
  mkdirSync(OUT_DIR, { recursive: true });
  mkdirSync(GENERATED_DIR, { recursive: true });
  mkdirSync(REVIEW_DIR, { recursive: true });
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

function readRows() {
  const rows = parseCsv(readFileSync(path.join(PACKAGE_DIR, "glp-quiz-campaign-ready-expanded.csv"), "utf8"));
  if (rows.length !== 23) {
    throw new Error(`Expected 23 campaign rows, found ${rows.length}.`);
  }
  for (const row of rows) {
    const sourcePath = path.join(PACKAGE_DIR, row.creative_file);
    const bytes = readFileSync(sourcePath);
    if (!bytes.length) {
      throw new Error(`Creative file is empty: ${sourcePath}`);
    }
  }
  return rows.map((row, index) => ({
    ...row,
    rowIndex: index + 1,
    rowKey: `${String(index + 1).padStart(2, "0")}-${row.remix_copy_id}-${row.creative_id}`,
    sourcePath: path.join(PACKAGE_DIR, row.creative_file),
  }));
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

function destinationUrlFor(row) {
  return row.launch_slot === "Quiz funnel" ? QUIZ_PRESALE_URL : GLP_PRESALE_URL;
}

function assetBriefIdFor(row) {
  return row.launch_slot === "Quiz funnel" ? QUIZ_BRIEF_ID : GLP_BRIEF_ID;
}

function requiresProductReference(row) {
  return CREATIVE_IDS_REQUIRING_PRODUCT_REFERENCE.has(row.creative_id);
}

function ctaEnumFor(row) {
  if (row.remix_cta === "Get The Protocol") return "LEARN_MORE";
  if (row.remix_cta === "See Details") return "LEARN_MORE";
  throw new Error(`No approved Meta CTA mapping for ${row.remix_cta}`);
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

function manualCreativeContextPayload(campaignId) {
  const rows = readRows();
  const glpCopyIds = [...new Set(rows.filter((row) => row.launch_slot === "GLP lander").map((row) => row.remix_copy_id))];
  const quizCopyIds = [...new Set(rows.filter((row) => row.launch_slot === "Quiz funnel").map((row) => row.remix_copy_id))];
  return {
    schemaVersion: 1,
    provider: "manual",
    angles: {
      selectedAngleId: EXPERIMENT_ID,
      angleLibrary: [
        {
          angleId: EXPERIMENT_ID,
          angleName: "Tenor GLP + Quiz",
          description:
            "Package-driven Meta launch using the supplied GLP listicle and quiz destinations with source creative remixes.",
          evidence: [GLP_PRESALE_URL, QUIZ_PRESALE_URL, SALES_URL],
        },
      ],
    },
    offer: {
      ump: "Tenor GLP + Quiz external funnel campaign",
      ums: "Use the supplied package rows to route GLP rows to the listicle and quiz rows to the quiz.",
      corePromise: "Use Tenor Daily Drive Essentials as the protocol positioned in the supplied copy package.",
      valueStackSummary:
        "Campaign rows come from the approved CSV package and route to the supplied presale URLs before the supplied sales URL.",
      guaranteeType: "90-day guarantee",
      pricingRationale: "Offer details and savings language come from the supplied campaign CSV copy.",
      selectedVariantId: EXPERIMENT_ID,
      selectedVariantName: "GLP + Quiz",
      offerDetailsMarkdown: [
        "# Supplied Destinations",
        "",
        `GLP listicle: ${GLP_PRESALE_URL}`,
        `Quiz: ${QUIZ_PRESALE_URL}`,
        `Sales: ${SALES_URL}`,
        "",
        "# Package Summary",
        "",
        `Rows: ${rows.length}`,
        `GLP copy IDs: ${glpCopyIds.join(", ")}`,
        `Quiz copy IDs: ${quizCopyIds.join(", ")}`,
      ].join("\n"),
    },
    copyDocument: {
      headline: "Tenor GLP + Quiz Campaign",
      promiseContract: {
        loopQuestion: "Can the supplied creative/copy package be launched as a MOS-managed Meta campaign?",
        specificPromise: "Each generated ad uses its assigned source creative, CSV copy, and row-level destination URL.",
        deliveryTest: "MOS contains the campaign, manual creative context, asset briefs, generated assets, Meta creative specs, CBO ad set specs, validation, and publish run.",
        minimumDelivery: "A paused Meta campaign with five CBO ad sets and all generated ads attached for review.",
      },
      presellMarkdown: [
        "# Presell Destinations",
        "",
        `GLP listicle: ${GLP_PRESALE_URL}`,
        `Quiz: ${QUIZ_PRESALE_URL}`,
      ].join("\n"),
      salesPageMarkdown: [`# Sales Destination`, "", SALES_URL].join("\n"),
      templatePayloads: {
        glpPresaleUrl: GLP_PRESALE_URL,
        quizPresaleUrl: QUIZ_PRESALE_URL,
        salesUrl: SALES_URL,
        packageDir: PACKAGE_DIR,
      },
    },
    copyContext: {
      audienceProductMarkdown:
        "Audience and product context are supplied by the campaign CSV rows for Tenor Daily Drive Essentials.",
      brandVoiceMarkdown:
        "Use Tenor naming and the supplied row copy. Do not add creative interpretation outside the provided package.",
      complianceMarkdown:
        "No additional content constraints are introduced here; use the supplied copy package and MOS validation flow.",
      mentalModelsMarkdown:
        "The campaign uses MOS external delivery with campaign-level sales URL and row-level creative destination URLs for the two presales.",
      awarenessAngleMatrixMarkdown:
        "GLP lander rows route to the GLP listicle; quiz funnel rows route to the quiz destination.",
    },
    experimentSpecs: [
      {
        id: EXPERIMENT_ID,
        name: "Tenor GLP + Quiz",
        hypothesis:
          "The supplied GLP and quiz creative/copy rows can be launched through one MOS-managed CBO Meta campaign.",
        metricIds: ["ctr", "cvr"],
        variants: [
          {
            id: "glp-listicle",
            name: "GLP Listicle",
            description: "Rows routed to the GLP listicle presale.",
            channels: ["meta"],
            guardrails: [],
          },
          {
            id: "quiz-funnel",
            name: "Quiz Funnel",
            description: "Rows routed to the quiz presale.",
            channels: ["meta"],
            guardrails: [],
          },
        ],
      },
    ],
  };
}

function assetBriefPayload(campaignId) {
  const common = {
    clientId: CLIENT_ID,
    campaignId,
    experimentId: EXPERIMENT_ID,
    funnelId: null,
    deliveryMode: "external_urls",
    requirements: [
      {
        channel: "meta",
        format: "image",
        funnelStage: "pre-sales",
        destinationType: "pre-sales",
        hook: "Package supplied row",
        angle: "Use the supplied row-level swipe image, copy, and destination.",
      },
    ],
    constraints: [],
    toneGuidelines: [],
    visualGuidelines: [],
  };
  return {
    asset_briefs: [
      {
        ...common,
        id: GLP_BRIEF_ID,
        variantId: "glp-listicle",
        variantName: "GLP Listicle",
        destinationType: "pre-sales",
        destinationLabel: "GLP listicle presale",
        creativeConcept: "Source creative remixes routed to the GLP listicle presale.",
      },
      {
        ...common,
        id: QUIZ_BRIEF_ID,
        variantId: "quiz-funnel",
        variantName: "Quiz Funnel",
        destinationType: "pre-sales",
        destinationLabel: "Quiz presale",
        creativeConcept: "Source creative remixes routed to the quiz presale.",
      },
    ],
    source: "tenor-glp-quiz-gpt-image2-full-launch",
    packageDir: PACKAGE_DIR,
  };
}

function seedAssetBriefViaSsh(campaignId) {
  const payloadPath = path.join(OUT_DIR, "asset-brief-payload.json");
  writeFileSync(payloadPath, JSON.stringify(assetBriefPayload(campaignId), null, 2) + "\n");
  const remotePayloadPath = `/root/tmp/tenor-glp-quiz-asset-brief-${campaignId}.json`;
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
from app.db.enums import ArtifactTypeEnum
from app.db.models import Campaign
from app.db.repositories.artifacts import ArtifactsRepository

campaign_id = "${campaignId}"
payload = json.loads(Path("${remotePayloadPath}").read_text())
brief_ids = {str(brief["id"]) for brief in payload["asset_briefs"]}

with session_scope() as session:
    campaign = session.scalars(select(Campaign).where(Campaign.id == campaign_id)).first()
    if campaign is None:
        raise RuntimeError(f"Campaign not found: {campaign_id}")
    repo = ArtifactsRepository(session)
    existing = repo.list(
        org_id=str(campaign.org_id),
        client_id=str(campaign.client_id),
        product_id=str(campaign.product_id) if campaign.product_id else None,
        campaign_id=str(campaign.id),
        artifact_type=ArtifactTypeEnum.asset_brief,
        limit=200,
    )
    for artifact in existing:
        data = artifact.data if isinstance(artifact.data, dict) else {}
        found = {
            str(brief.get("id"))
            for brief in (data.get("asset_briefs") or data.get("assetBriefs") or [])
            if isinstance(brief, dict)
        }
        if brief_ids.intersection(found):
            artifact.data = payload
            session.add(artifact)
            session.commit()
            print(json.dumps({"status": "updated", "artifactId": str(artifact.id), "briefIds": sorted(brief_ids)}))
            raise SystemExit(0)
    artifact = repo.insert(
        org_id=str(campaign.org_id),
        client_id=str(campaign.client_id),
        product_id=str(campaign.product_id) if campaign.product_id else None,
        campaign_id=str(campaign.id),
        artifact_type=ArtifactTypeEnum.asset_brief,
        data=payload,
    )
    print(json.dumps({"status": "created", "artifactId": str(artifact.id), "briefIds": sorted(brief_ids)}))
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

async function setupCampaign() {
  ensureDirs();
  await getBackendToken();
  const campaigns = await authed(`/campaigns?client_id=${encodeURIComponent(CLIENT_ID)}&product_id=${encodeURIComponent(PRODUCT_ID)}`);
  let campaign = campaigns.find((item) => item.name === CAMPAIGN_NAME);
  let campaignAction = "reused";
  if (!campaign) {
    campaign = await authed("/campaigns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_id: CLIENT_ID,
        product_id: PRODUCT_ID,
        name: CAMPAIGN_NAME,
        channels: ["facebook"],
        asset_brief_types: ["image"],
        start_planning: false,
        goal_description: "Launch the supplied Tenor GLP + quiz Meta campaign package.",
        objective_type: "sales",
        budget_min: 100,
        budget_max: 100,
      }),
    });
    campaignAction = "created";
  }

  const campaignId = campaign.id;
  const creativeContext = await authed(`/campaigns/${encodeURIComponent(campaignId)}/creative-context/loaded`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(manualCreativeContextPayload(campaignId)),
  });
  const assetBriefSeed = seedAssetBriefViaSsh(campaignId);
  const delivery = await authed(`/campaigns/${encodeURIComponent(campaignId)}/delivery`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      deliveryMode: "external_urls",
      preSalesUrl: GLP_PRESALE_URL,
      salesUrl: SALES_URL,
    }),
  });
  const deliveryValidation = await authed(`/campaigns/${encodeURIComponent(campaignId)}/delivery/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  const state = {
    createdAt: new Date().toISOString(),
    campaignAction,
    campaignId,
    campaign,
    creativeContext,
    assetBriefSeed,
    delivery,
    deliveryValidation,
    generationKey: GENERATION_KEY,
    batchId: BATCH_ID,
  };
  writeFileSync(STATE_PATH, JSON.stringify(state, null, 2) + "\n");
  console.log(JSON.stringify({ campaignAction, campaignId, statePath: STATE_PATH, deliveryStatus: deliveryValidation.validationStatus }, null, 2));
  return state;
}

function readState() {
  if (!existsSync(STATE_PATH)) {
    throw new Error(`Campaign state does not exist yet: ${STATE_PATH}. Run setup first.`);
  }
  return JSON.parse(readFileSync(STATE_PATH, "utf8"));
}

function readManifest(state) {
  if (existsSync(MANIFEST_PATH)) {
    return JSON.parse(readFileSync(MANIFEST_PATH, "utf8"));
  }
  return {
    createdAt: new Date().toISOString(),
    packageDir: PACKAGE_DIR,
    sourceCsv: path.join(PACKAGE_DIR, "glp-quiz-campaign-ready-expanded.csv"),
    campaignId: state.campaignId,
    campaignName: CAMPAIGN_NAME,
    generationKey: GENERATION_KEY,
    batchId: BATCH_ID,
    stageOneModel: STAGE_ONE_MODEL,
    renderModelId: RENDER_MODEL_ID,
    destinations: {
      glpPresaleUrl: GLP_PRESALE_URL,
      quizPresaleUrl: QUIZ_PRESALE_URL,
      salesUrl: SALES_URL,
    },
    outputs: [],
  };
}

function writeManifest(manifest) {
  writeFileSync(MANIFEST_PATH, JSON.stringify({ ...manifest, updatedAt: new Date().toISOString() }, null, 2) + "\n");
}

function normalizeManifestOutputs(manifest) {
  manifest.outputs = (manifest.outputs || []).map((output) => {
    const payloadOut = output.workflow?.payloadOut || {};
    return {
      ...output,
      result: {
        ...output.result,
        renderProvider: output.result?.renderProvider || payloadOut.swipe_render_provider || null,
        renderModelIdRequested: output.result?.renderModelIdRequested || output.payload?.renderModelId || null,
        renderModelIdUsed: output.result?.renderModelIdUsed || payloadOut.swipe_render_model_id || output.payload?.renderModelId || null,
        usedAuthorizedFallback: Boolean(output.result?.usedAuthorizedFallback || output.workflow?.primaryOpenAiFailure),
      },
    };
  });
  manifest.outputs.sort((a, b) => Number(a.rowIndex) - Number(b.rowIndex));
  return manifest;
}

function expectedRendererFor(renderModelId) {
  if (renderModelId === RENDER_MODEL_ID) {
    return { provider: "openai", modelIdUsed: RENDER_MODEL_ID };
  }
  if (renderModelId === NANOBANANA_RENDER_MODEL_ID) {
    return { provider: "creative_service", modelIdUsed: NANOBANANA_RENDER_MODEL_ID_USED };
  }
  throw new Error(`No approved renderer expectation for ${renderModelId}`);
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

async function verifyStagedSource(attachment, expectedSha256) {
  const response = await fetch(attachment.publicUrl);
  if (!response.ok) {
    throw new Error(`Failed to re-download staged source (${response.status}) from ${attachment.publicUrl}`);
  }
  const bytes = Buffer.from(await response.arrayBuffer());
  const actualSha256 = sha256(bytes);
  if (actualSha256 !== expectedSha256) {
    throw new Error(`Staged source hash mismatch: expected ${expectedSha256}, got ${actualSha256}`);
  }
  return actualSha256;
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

function linkReviewAsset(localPath, reviewPath) {
  rmSync(reviewPath, { force: true });
  linkSync(localPath, reviewPath);
}

function buildSwipeAngle(row, sourceSha256) {
  return [
    `Launch slot: ${row.launch_slot}`,
    `Source creative: ${row.creative_id} / ${row.creative_reference_title}`,
    `Source creative SHA-256: ${sourceSha256}`,
    `Remix copy: ${row.remix_copy_id} / ${row.remix_title}`,
    `Destination URL for this row: ${destinationUrlFor(row)}`,
    `Sales URL: ${SALES_URL}`,
    `CSV CTA: ${row.remix_cta}`,
    "Use the attached source creative as the composition and design reference.",
    "Replace source brand identity with Tenor using the supplied row context.",
  ].join("\n");
}

async function generateRow(state, row) {
    const sourceBytes = readFileSync(row.sourcePath);
    const sourceSha256 = sha256(sourceBytes);
    const aspectRatio = aspectRatioFor(row.sourcePath);
    const sourceAttachment = await uploadSourceFile(row.sourcePath);
    const stagedSourceSha256 = await verifyStagedSource(sourceAttachment, sourceSha256);
    const buildPayload = (renderModelId) => ({
      clientId: CLIENT_ID,
      productId: PRODUCT_ID,
      campaignId: state.campaignId,
      assetBriefId: assetBriefIdFor(row),
      requirementIndex: 0,
      swipeImageUrl: sourceAttachment.publicUrl,
      swipeRequiresProductImage: requiresProductReference(row),
      swipeContextMode: "minimal",
      swipeBrandName: "Tenor",
      swipeProductName: "Daily Drive Essentials",
      swipeHook: row.remix_title,
      swipeAngle: buildSwipeAngle(row, sourceSha256),
      model: STAGE_ONE_MODEL,
      renderModelId,
      aspectRatio,
      count: 1,
    });
    let payload = buildPayload(RENDER_MODEL_ID);
    let primaryOpenAiFailure = null;
    console.log(`Generating ${row.rowKey} with ${RENDER_MODEL_ID} (${aspectRatio})`);
    let started = await authed("/swipes/generate-image-ad", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    let detail;
    try {
      detail = await waitForWorkflow(started.workflow_run_id);
    } catch (error) {
      const failedWorkflowPath = path.join(OUT_DIR, `workflow-failed-openai-${row.rowKey}.json`);
      let failedDetail = null;
      try {
        failedDetail = await authed(`/workflows/${encodeURIComponent(started.workflow_run_id)}`);
        writeFileSync(failedWorkflowPath, JSON.stringify(failedDetail, null, 2) + "\n");
      } catch (detailError) {
        writeFileSync(
          failedWorkflowPath,
          JSON.stringify({
            workflowRunId: started.workflow_run_id,
            error: error?.stack || error?.message || String(error),
            detailFetchError: detailError?.stack || detailError?.message || String(detailError),
          }, null, 2) + "\n",
        );
      }
      primaryOpenAiFailure = {
        workflowRunId: started.workflow_run_id,
        temporalWorkflowId: started.temporal_workflow_id,
        workflowUrl: `https://moshq.app/workflows/${started.workflow_run_id}`,
        workflowDetailPath: failedWorkflowPath,
        error: error?.message || String(error),
      };
      if (!AUTHORIZED_NANOBANANA_FALLBACK_ROW_KEYS.has(row.rowKey)) {
        throw error;
      }
      payload = buildPayload(NANOBANANA_RENDER_MODEL_ID);
      console.log(`OpenAI failed for ${row.rowKey}; using authorized NanoBanana fallback (${NANOBANANA_RENDER_MODEL_ID}).`);
      started = await authed("/swipes/generate-image-ad", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      detail = await waitForWorkflow(started.workflow_run_id);
    }
    const workflowPath = path.join(OUT_DIR, `workflow-${row.rowKey}.json`);
    writeFileSync(workflowPath, JSON.stringify(detail, null, 2) + "\n");
    const { assetId, payloadOut } = extractAssetId(detail);
    const asset = await resolveAsset(state.campaignId, assetId);
    const metadata = asset.ai_metadata || {};
    const expectedRenderer = expectedRendererFor(payload.renderModelId);
    if (metadata.swipeRenderProvider !== expectedRenderer.provider || metadata.swipeRenderModelIdUsed !== expectedRenderer.modelIdUsed) {
      throw new Error(
        `Generated asset ${assetId} used wrong renderer: ${metadata.swipeRenderProvider} / ${metadata.swipeRenderModelIdUsed}; expected ${expectedRenderer.provider} / ${expectedRenderer.modelIdUsed}`,
      );
    }
    if (metadata.swipePromptImageSha256 !== sourceSha256) {
      throw new Error(`Generated asset ${assetId} source hash mismatch: expected ${sourceSha256}, got ${metadata.swipePromptImageSha256}`);
    }
    const ext = asset.content_type === "image/png" ? "png" : "jpg";
    const localPath = path.join(GENERATED_DIR, `${row.rowKey}.${ext}`);
    const reviewPath = path.join(REVIEW_DIR, `${row.rowKey}.${ext}`);
    downloadPublicAsset(asset.public_id, localPath);
    linkReviewAsset(localPath, reviewPath);
    const generatedBytes = readFileSync(localPath);
    const output = {
      rowKey: row.rowKey,
      rowIndex: row.rowIndex,
      launchSlot: row.launch_slot,
      sourceCopyId: row.source_copy_id,
      remixCopyId: row.remix_copy_id,
      creativeId: row.creative_id,
      creativeReferenceTitle: row.creative_reference_title,
      creativeFile: row.creative_file,
      sourceCreativeSha256: sourceSha256,
      stagedSourceSha256,
      aspectRatio,
      sourceAttachment,
      meta: {
        headline: row.remix_title,
        primaryText: row.remix_body,
        description: row.remix_link_description,
        sourceCta: row.remix_cta,
        callToActionType: ctaEnumFor(row),
        destinationUrl: destinationUrlFor(row),
      },
      payload,
      workflow: {
        workflowRunId: started.workflow_run_id,
        temporalWorkflowId: started.temporal_workflow_id,
        workflowUrl: `https://moshq.app/workflows/${started.workflow_run_id}`,
        workflowDetailPath: workflowPath,
        payloadOut,
        primaryOpenAiFailure,
      },
      result: {
        assetId: asset.id,
        publicId: asset.public_id,
        publicUrl: `${API_BASE}/public/assets/${asset.public_id}`,
        contentType: asset.content_type,
        width: asset.width,
        height: asset.height,
        localPath,
        reviewPath,
        bytes: generatedBytes.length,
        sha256: sha256(generatedBytes),
        remoteJobId: metadata.remoteJobId,
        renderProvider: metadata.swipeRenderProvider,
        renderModelIdRequested: metadata.swipeRenderModelIdRequested,
        renderModelIdUsed: metadata.swipeRenderModelIdUsed,
        usedAuthorizedFallback: Boolean(primaryOpenAiFailure),
        productReferenceRequired: payload.swipeRequiresProductImage,
        productReferenceAttached: Boolean(metadata.swipePromptProductImageAttached),
        productReferenceRenderAssetIds: metadata.swipeProductReferenceRenderAssetIds || [],
        productReferenceImageUrlsSelected: metadata.swipeProductReferenceImageUrlsSelected || [],
      },
    };
    return output;
}

function parsePositiveIntegerEnv(name, fallback) {
  const raw = process.env[name];
  if (raw === undefined || !String(raw).trim()) return fallback;
  const parsed = Number.parseInt(String(raw), 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error(`${name} must be a positive integer; got ${raw}`);
  }
  return parsed;
}

async function generateAll() {
  ensureDirs();
  const state = existsSync(STATE_PATH) ? readState() : await setupCampaign();
  await getBackendToken();
  const rows = readRows();
  const manifest = normalizeManifestOutputs(readManifest(state));
  const completed = new Set((manifest.outputs || []).map((output) => output.rowKey));
  for (const row of rows) {
    if (completed.has(row.rowKey)) {
      console.log(`Skipping ${row.rowKey}; already generated.`);
    }
  }
  const pendingRows = rows.filter((row) => !completed.has(row.rowKey));
  const concurrency = Math.min(parsePositiveIntegerEnv("GENERATE_CONCURRENCY", 4), Math.max(1, pendingRows.length));
  let nextIndex = 0;
  let stopped = false;
  const failures = [];
  async function worker(workerIndex) {
    while (!stopped) {
      const row = pendingRows[nextIndex];
      nextIndex += 1;
      if (!row) return;
      try {
        const output = await generateRow(state, row);
        manifest.outputs.push(output);
        normalizeManifestOutputs(manifest);
        writeReviewHtml(manifest);
        writeManifest(manifest);
        completed.add(row.rowKey);
        console.log(`Completed ${row.rowKey} on worker ${workerIndex}.`);
      } catch (error) {
        stopped = true;
        failures.push({ rowKey: row.rowKey, error });
      }
    }
  }
  await Promise.all(Array.from({ length: concurrency }, (_, index) => worker(index + 1)));
  if (failures.length) {
    const failure = failures[0];
    throw new Error(`Generation failed for ${failure.rowKey}: ${failure.error?.message || String(failure.error)}`);
  }
  writeReviewHtml(manifest);
  writeManifest(manifest);
  console.log(JSON.stringify({ manifestPath: MANIFEST_PATH, campaignId: state.campaignId, count: manifest.outputs.length, concurrency, reviewDir: REVIEW_DIR }, null, 2));
}

function requireFullOutputs() {
  if (!existsSync(MANIFEST_PATH)) {
    throw new Error(`Missing generation manifest: ${MANIFEST_PATH}`);
  }
  const manifest = JSON.parse(readFileSync(MANIFEST_PATH, "utf8"));
  if (!Array.isArray(manifest.outputs) || manifest.outputs.length !== 23) {
    throw new Error(`Expected 23 generated outputs in ${MANIFEST_PATH}`);
  }
  return manifest;
}

function stampBatchViaSsh(manifest) {
  const payloadPath = path.join(OUT_DIR, "batch-stamp-input.json");
  const assetRows = manifest.outputs.map((output) => ({
    assetId: output.result.assetId,
    rowKey: output.rowKey,
    rowIndex: output.rowIndex,
    launchSlot: output.launchSlot,
    sourceCopyId: output.sourceCopyId,
    remixCopyId: output.remixCopyId,
    creativeId: output.creativeId,
    creativeFile: output.creativeFile,
    creativeReferenceTitle: output.creativeReferenceTitle,
    destinationUrl: output.meta.destinationUrl,
    headline: output.meta.headline,
  }));
  writeFileSync(payloadPath, JSON.stringify({ campaignId: manifest.campaignId, batchId: BATCH_ID, assetRows }, null, 2) + "\n");
  const remotePayloadPath = `/root/tmp/tenor-glp-quiz-batch-stamp-${manifest.campaignId}.json`;
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
asset_rows = payload["assetRows"]
asset_ids = [row["assetId"] for row in asset_rows]
row_by_asset_id = {row["assetId"]: row for row in asset_rows}

with session_scope() as session:
    assets = session.scalars(
        select(Asset).where(Asset.campaign_id == campaign_id, Asset.id.in_(asset_ids))
    ).all()
    found = {str(asset.id) for asset in assets}
    missing = sorted(set(asset_ids).difference(found))
    if missing:
        raise RuntimeError(f"Missing campaign assets: {missing}")
    for asset in assets:
        row = row_by_asset_id[str(asset.id)]
        metadata = dict(asset.ai_metadata or {})
        metadata["creativeGenerationBatchId"] = batch_id
        metadata["packageDir"] = "${PACKAGE_DIR}"
        metadata["campaignPackageRowKey"] = row["rowKey"]
        metadata["campaignPackageRowIndex"] = row["rowIndex"]
        metadata["launchSlot"] = row["launchSlot"]
        metadata["sourceCopyId"] = row["sourceCopyId"]
        metadata["remixCopyId"] = row["remixCopyId"]
        metadata["creativeId"] = row["creativeId"]
        metadata["creativeFile"] = row["creativeFile"]
        metadata["creativeReferenceTitle"] = row["creativeReferenceTitle"]
        metadata["rowDestinationUrl"] = row["destinationUrl"]
        metadata["rowHeadline"] = row["headline"]
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

async function getCampaignAssets(campaignId) {
  return authed(`/assets?campaignId=${encodeURIComponent(campaignId)}&productId=${encodeURIComponent(PRODUCT_ID)}&assetKind=image`);
}

async function stampBatch() {
  await getBackendToken();
  const manifest = requireFullOutputs();
  const stamp = stampBatchViaSsh(manifest);
  const assets = await getCampaignAssets(manifest.campaignId);
  const byId = new Map(assets.map((asset) => [asset.id, asset]));
  const mismatched = manifest.outputs
    .map((output) => byId.get(output.result.assetId))
    .filter((asset) => asset?.ai_metadata?.creativeGenerationBatchId !== BATCH_ID)
    .map((asset) => asset?.id || "missing");
  if (mismatched.length) {
    throw new Error(`Batch stamp verification failed for assets: ${mismatched.join(", ")}`);
  }
  writeManifest({ ...manifest, batchStamp: stamp });
  console.log(JSON.stringify({ campaignId: manifest.campaignId, generationKey: GENERATION_KEY, stamp }, null, 2));
}

function specAssetId(spec) {
  return spec.asset_id || spec.assetId || null;
}

function specMetadata(spec) {
  if (spec.metadata_json && typeof spec.metadata_json === "object") return spec.metadata_json;
  if (spec.metadata && typeof spec.metadata === "object") return spec.metadata;
  return {};
}

async function getCreativeSpecs(campaignId) {
  return authed(`/meta/specs/creatives?campaignId=${encodeURIComponent(campaignId)}`);
}

async function getAdSetSpecs(campaignId) {
  return authed(`/meta/specs/adsets?campaignId=${encodeURIComponent(campaignId)}`);
}

async function upsertCreativeSpec(campaignId, output, existingByAssetId) {
  const assetId = output.result.assetId;
  const body = {
    campaignId,
    name: `GLPQuiz ${String(output.rowIndex).padStart(2, "0")} ${output.remixCopyId} ${output.creativeId} - ${output.meta.headline}`.slice(0, 240),
    primaryText: output.meta.primaryText,
    headline: output.meta.headline,
    description: output.meta.description,
    callToActionType: output.meta.callToActionType,
    destinationUrl: output.meta.destinationUrl,
    status: "draft",
    metadata: {
      source: "tenor_glp_quiz_gpt_image2_package",
      packageDir: PACKAGE_DIR,
      sourceCsv: path.join(PACKAGE_DIR, "glp-quiz-campaign-ready-expanded.csv"),
      batchId: BATCH_ID,
      generationKey: GENERATION_KEY,
      rowKey: output.rowKey,
      rowIndex: output.rowIndex,
      launchSlot: output.launchSlot,
      sourceCopyId: output.sourceCopyId,
      remixCopyId: output.remixCopyId,
      creativeId: output.creativeId,
      creativeFile: output.creativeFile,
      creativeReferenceTitle: output.creativeReferenceTitle,
      sourceCreativeSha256: output.sourceCreativeSha256,
      stagedSourceSha256: output.stagedSourceSha256,
      sourceCta: output.meta.sourceCta,
      ctaMapping: { source: output.meta.sourceCta, metaEnum: output.meta.callToActionType },
      presaleUrl: output.meta.destinationUrl,
      salesUrl: SALES_URL,
      generatedAssetPublicUrl: output.result.publicUrl,
      workflowRunId: output.workflow.workflowRunId,
      workflowUrl: output.workflow.workflowUrl,
      remoteJobId: output.result.remoteJobId,
      renderer: {
        stageOneModel: STAGE_ONE_MODEL,
        renderModelIdRequested: output.result.renderModelIdRequested || output.payload.renderModelId,
        renderModelIdUsed: output.result.renderModelIdUsed || output.payload.renderModelId,
        renderProvider: output.result.renderProvider || null,
        usedAuthorizedFallback: Boolean(output.result.usedAuthorizedFallback),
      },
      productReference: {
        required: Boolean(output.result.productReferenceRequired || output.payload.swipeRequiresProductImage),
        attached: Boolean(output.result.productReferenceAttached),
        renderAssetIds: output.result.productReferenceRenderAssetIds || [],
        imageUrlsSelected: output.result.productReferenceImageUrlsSelected || [],
      },
      primaryOpenAiFailure: output.workflow.primaryOpenAiFailure || null,
    },
  };
  const existing = existingByAssetId.get(assetId);
  if (!existing) {
    const created = await authed("/meta/specs/creatives", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assetId, ...body }),
    });
    return { action: "created", rowKey: output.rowKey, assetId, creativeSpecId: created.id };
  }
  const updated = await authed(`/meta/specs/creatives/${encodeURIComponent(existing.id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return { action: "updated", rowKey: output.rowKey, assetId, creativeSpecId: updated.id || existing.id };
}

async function activeMetaConfig() {
  return authed(`/meta/clients/${encodeURIComponent(CLIENT_ID)}/active-config`);
}

async function upsertAdSetSpecs(campaignId, existingAdsets) {
  const config = await activeMetaConfig();
  if (!config?.pixelId) {
    throw new Error(`Active Meta config ${config?.id || ""} is missing pixelId.`);
  }
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
  const promotedObject = {
    pixel_id: config.pixelId,
    custom_event_type: "PURCHASE",
  };
  const attributionSpec = [
    { event_type: "CLICK_THROUGH", window_days: 7 },
    { event_type: "VIEW_THROUGH", window_days: 1 },
    { event_type: "ENGAGED_VIDEO_VIEW", window_days: 1 },
  ];
  const byBucket = new Map();
  for (const spec of existingAdsets || []) {
    const metadata = specMetadata(spec);
    const bucketIndex = Number(metadata.bucketIndex);
    const bucketCount = Number(metadata.bucketCount);
    if (metadata.templateId !== "default-broad-int-cbo" || bucketCount !== 5 || bucketIndex < 1 || bucketIndex > 5) {
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
      campaignId,
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
        source: "tenor_glp_quiz_gpt_image2_full_launch",
        templateId: "default-broad-int-cbo",
        campaignDailyBudget: 10000,
        bucketIndex,
        bucketCount: 5,
        bucketStrategy: "deterministic_round_robin",
        attributionSpec,
      },
    };
    const existing = byBucket.get(bucketIndex);
    if (!existing) {
      const created = await authed("/meta/specs/adsets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      results.push({ action: "created", bucketIndex, adsetSpecId: created.id });
    } else {
      const updated = await authed(`/meta/specs/adsets/${encodeURIComponent(existing.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      results.push({ action: "updated", bucketIndex, adsetSpecId: updated.id || existing.id });
    }
  }
  return results;
}

async function createSpecs() {
  await getBackendToken();
  const manifest = requireFullOutputs();
  const assets = await getCampaignAssets(manifest.campaignId);
  const byId = new Map(assets.map((asset) => [asset.id, asset]));
  const missingBatch = manifest.outputs
    .map((output) => byId.get(output.result.assetId))
    .filter((asset) => asset?.ai_metadata?.creativeGenerationBatchId !== BATCH_ID)
    .map((asset) => asset?.id || "missing");
  if (missingBatch.length) {
    throw new Error(`Run stamp-batch before create-specs. Missing batch on: ${missingBatch.join(", ")}`);
  }
  const creativeSpecs = await getCreativeSpecs(manifest.campaignId);
  const creativeByAssetId = new Map();
  for (const spec of creativeSpecs || []) {
    const assetId = specAssetId(spec);
    if (assetId) creativeByAssetId.set(assetId, spec);
  }
  const creativeResults = [];
  for (const output of manifest.outputs) {
    creativeResults.push(await upsertCreativeSpec(manifest.campaignId, output, creativeByAssetId));
  }
  const adsetResults = await upsertAdSetSpecs(manifest.campaignId, await getAdSetSpecs(manifest.campaignId));
  const specsPath = path.join(OUT_DIR, "full-launch-specs.json");
  writeFileSync(specsPath, JSON.stringify({
    campaignId: manifest.campaignId,
    generationKey: GENERATION_KEY,
    createdAt: new Date().toISOString(),
    creativeSpecs: creativeResults,
    adsetSpecs: adsetResults,
  }, null, 2) + "\n");
  console.log(JSON.stringify({
    campaignId: manifest.campaignId,
    generationKey: GENERATION_KEY,
    creativeSpecs: creativeResults.reduce((acc, row) => ({ ...acc, [row.action]: (acc[row.action] || 0) + 1 }), {}),
    adsetSpecs: adsetResults.reduce((acc, row) => ({ ...acc, [row.action]: (acc[row.action] || 0) + 1 }), {}),
    specsPath,
  }, null, 2));
}

function publishPayload() {
  return {
    generationKey: GENERATION_KEY,
    publishBaseUrl: PUBLISH_BASE_URL,
    campaignName: META_CAMPAIGN_NAME,
    campaignObjective: "OUTCOME_SALES",
    buyingType: "AUCTION",
    specialAdCategories: [],
    campaignDailyBudget: 10000,
    bucketCount: 5,
    bucketDestinationUrls: [],
  };
}

function summarizeDistribution(validation) {
  const counts = {};
  for (const item of validation.items || []) {
    const key = String(item.bucketIndex || "none");
    counts[key] = (counts[key] || 0) + 1;
  }
  return counts;
}

async function validatePublish() {
  await getBackendToken();
  const manifest = requireFullOutputs();
  const payload = publishPayload();
  const response = await authed(`/meta/campaigns/${encodeURIComponent(manifest.campaignId)}/publish-plan/validate`, {
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
    campaignId: manifest.campaignId,
    ok: response.ok,
    includedCount: response.includedCount,
    adsetCount: response.adsetCount,
    bucketCount: response.bucketCount,
    distribution: summarizeDistribution(response),
    publishDomain: response.publishDomain,
    validationPath,
  }, null, 2));
}

async function publish() {
  await getBackendToken();
  const manifest = requireFullOutputs();
  const existingRuns = await authed(`/meta/campaigns/${encodeURIComponent(manifest.campaignId)}/publish-runs`);
  const existingPublished = (existingRuns || []).find(
    (run) => run.generationKey === GENERATION_KEY && run.status === "published",
  );
  if (existingPublished) {
    console.log(JSON.stringify({
      campaignId: manifest.campaignId,
      publishRunId: existingPublished.id,
      status: existingPublished.status,
      metaCampaignId: existingPublished.metaCampaignId,
      reusedExistingPublishRun: true,
    }, null, 2));
    return;
  }
  const payload = publishPayload();
  const response = await authed(`/meta/campaigns/${encodeURIComponent(manifest.campaignId)}/publish-runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const publishPath = path.join(OUT_DIR, "full-launch-publish-run-response.json");
  writeFileSync(publishPath, JSON.stringify({ payload, response }, null, 2) + "\n");
  console.log(JSON.stringify({
    campaignId: manifest.campaignId,
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

async function publishStatus() {
  await getBackendToken();
  const manifest = requireFullOutputs();
  const runs = await authed(`/meta/campaigns/${encodeURIComponent(manifest.campaignId)}/publish-runs`);
  const statusPath = path.join(OUT_DIR, "full-launch-publish-runs.json");
  writeFileSync(statusPath, JSON.stringify({ checkedAt: new Date().toISOString(), runs }, null, 2) + "\n");
  const matching = (runs || []).filter((run) => run.generationKey === GENERATION_KEY);
  console.log(JSON.stringify({
    campaignId: manifest.campaignId,
    generationKey: GENERATION_KEY,
    matchingRuns: matching.map((run) => ({
      id: run.id,
      status: run.status,
      metaCampaignId: run.metaCampaignId || run.meta_campaign_id || null,
      itemCount: Array.isArray(run.items) && run.items.length
        ? run.items.length
        : run.metadata?.resultSummary?.totalCount ?? null,
      failedItems: Array.isArray(run.items) && run.items.length
        ? run.items.filter((item) => item.status === "failed").length
        : run.metadata?.resultSummary?.failedCount ?? null,
      createdAt: run.createdAt || run.created_at || null,
      updatedAt: run.updatedAt || run.updated_at || null,
    })),
    statusPath,
  }, null, 2));
}

function writeReviewHtml(manifest) {
  const cards = manifest.outputs
    .map((output) => {
      const rel = path.relative(REVIEW_DIR, output.result.reviewPath);
      return [
        "<article>",
        `<img src="${rel}" alt="${output.rowKey}">`,
        `<h2>${output.rowKey}</h2>`,
        `<p>${output.launchSlot} / ${output.meta.destinationUrl}</p>`,
        `<p>${output.meta.headline}</p>`,
        "</article>",
      ].join("\n");
    })
    .join("\n");
  const html = [
    "<!doctype html>",
    "<html>",
    "<head>",
    '<meta charset="utf-8">',
    "<title>Tenor GLP + Quiz GPT Image 2 Review</title>",
    "<style>",
    "body{font-family:Arial,sans-serif;margin:24px;background:#f4f4f0;color:#171717}",
    "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:18px}",
    "article{background:white;border:1px solid #d8d8d2;padding:10px}",
    "img{width:100%;height:auto;display:block;background:#ddd}",
    "h2{font-size:14px;margin:10px 0 6px}",
    "p{font-size:12px;line-height:1.35;margin:4px 0;color:#444;word-break:break-word}",
    "</style>",
    "</head>",
    "<body>",
    "<h1>Tenor GLP + Quiz GPT Image 2 Review</h1>",
    `<p>Campaign: ${manifest.campaignName} / ${manifest.outputs.length} creatives</p>`,
    "<main>",
    cards,
    "</main>",
    "</body>",
    "</html>",
  ].join("\n");
  writeFileSync(path.join(REVIEW_DIR, "index.html"), html + "\n");
}

function usage() {
  return [
    "Usage: node run_glp_quiz_full_launch.mjs <command>",
    "",
    "Commands:",
    "  setup",
    "  generate",
    "  stamp-batch",
    "  create-specs",
    "  validate-publish",
    "  publish",
    "  publish-status",
    "  all",
  ].join("\n");
}

async function main() {
  const command = process.argv[2];
  if (!command || command === "help" || command === "--help") {
    console.log(usage());
    return;
  }
  if (command === "setup") return setupCampaign();
  if (command === "generate") return generateAll();
  if (command === "stamp-batch") return stampBatch();
  if (command === "create-specs") return createSpecs();
  if (command === "validate-publish") return validatePublish();
  if (command === "publish") return publish();
  if (command === "publish-status") return publishStatus();
  if (command === "all") {
    await setupCampaign();
    await generateAll();
    await stampBatch();
    await createSpecs();
    await validatePublish();
    await publish();
    return;
  }
  throw new Error(`Unknown command: ${command}\n${usage()}`);
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exitCode = 1;
});
