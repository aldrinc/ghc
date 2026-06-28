import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const OUT_DIR = path.join(ROOT, "outputs/tenor-walk-away-trt-campaign-2026-05-02");
const GENERATED_DIR = path.join(OUT_DIR, "generated");
const REVIEW_DIR = "/Users/aldrinclement/Downloads/tenor-walk-away-trt-campaign-review-2026-05-02";
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

const REVIEW_RUNS = [
  {
    key: "01-boss-babe",
    awarenessLevel: "Solution-Aware",
    companySwipeId: "d1de69e6-5795-5cba-9fb2-28ba5f99620f",
    sourceSwipeTitle: "boss_babe.jpg",
  },
  {
    key: "02-spanish-doctor-cta",
    awarenessLevel: "Solution-Aware",
    companySwipeId: "234f2a51-3140-5e86-b982-7a3c9d406a72",
    sourceSwipeTitle: "spanish_doctor_cta.jpg",
  },
  {
    key: "03-old-school",
    awarenessLevel: "Solution-Aware",
    companySwipeId: "a6422035-8a65-5074-ba35-69da84cb70d5",
    sourceSwipeTitle: "old_school.jpg",
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
    const error = new Error(`${options.method || "GET"} ${url} failed (${response.status}): ${text.slice(0, 2000)}`);
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

function swipeAngle(awarenessLevel) {
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
    `Run marker: tenor-walk-away-trt-congruence-${Date.now()}.`,
  ].join("\n");
}

function manualCreativeContextPayload() {
  return {
    schemaVersion: 1,
    provider: "manual",
    angles: {
      selectedAngleId: "walk-away-trt-congruence",
      angleLibrary: [
        {
          angleId: "walk-away-trt-congruence",
          angleName: "Walk Away From TRT Congruence",
          description:
            "Campaign creatives use the supplied downstream destination context and awareness level to stay congruent with the provided presales advertorial.",
          evidence: [PRESALES_URL, SALES_URL],
        },
      ],
    },
    offer: {
      ump: "Tenor Daily Drive Essentials",
      ums: "Walk Away From TRT presales creative launch",
      corePromise: DESTINATION_CONTEXT.promise,
      valueStackSummary:
        "Presales advertorial traffic routes to the supplied Walk Away From TRT page and continues to the supplied Tenor sales page.",
      guaranteeType: "90-day guarantee",
      pricingRationale: "Current sales page offer framing is handled downstream on the supplied sales URL.",
      selectedVariantId: "walk-away-trt",
      selectedVariantName: "Walk Away From TRT",
      offerDetailsMarkdown: [
        "# Destination Context",
        "",
        `Presales URL: ${PRESALES_URL}`,
        `Sales URL: ${SALES_URL}`,
        "",
        JSON.stringify(DESTINATION_CONTEXT, null, 2),
      ].join("\n"),
    },
    copyDocument: {
      headline: DESTINATION_CONTEXT.headline,
      promiseContract: {
        loopQuestion: "Can the ad create a congruent click into the Walk Away From TRT advertorial?",
        specificPromise: DESTINATION_CONTEXT.promise,
        deliveryTest: "The creative matches the destination structure across promise, awareness level, proof, CTA/urgency, and asset stage.",
        minimumDelivery: "A reviewable Meta image creative attached to the campaign for human approval.",
      },
      presellMarkdown: [
        "# Presales Destination",
        "",
        `URL: ${PRESALES_URL}`,
        "",
        `Headline: ${DESTINATION_CONTEXT.headline}`,
        `Subheadline: ${DESTINATION_CONTEXT.subheadline}`,
        `Primary problem: ${DESTINATION_CONTEXT.primaryProblem}`,
        `Promise: ${DESTINATION_CONTEXT.promise}`,
        `Mechanism disclosure level: ${DESTINATION_CONTEXT.mechanismDisclosureLevel}`,
        `Proof type: ${DESTINATION_CONTEXT.proofType}`,
        `CTA / urgency: ${DESTINATION_CONTEXT.ctaUrgency}`,
      ].join("\n"),
      salesPageMarkdown: [`# Sales Destination`, "", `URL: ${SALES_URL}`].join("\n"),
      templatePayloads: {
        destinationContext: DESTINATION_CONTEXT,
      },
    },
    copyContext: {
      audienceProductMarkdown:
        "Audience: men 40+ evaluating low-drive, low-energy, and TRT-adjacent decisions. Product/workspace: Tenor Daily Drive Essentials.",
      brandVoiceMarkdown: "Tenor: premium, direct-response, mature men's health, evidence-led, not bro-y.",
      complianceMarkdown: "Only approved compliance input for this campaign: no product reveal and no mechanism reveal.",
      mentalModelsMarkdown:
        "Congruence means promise, mechanism disclosure level, awareness level, proof, CTA/urgency, compliance posture, and asset stage consistency from ad to advertorial to sales page.",
      awarenessAngleMatrixMarkdown:
        "Use the awareness level explicitly passed in each swipe generation payload. The review sample starts with Solution-Aware.",
    },
    experimentSpecs: [
      {
        id: "walk-away-trt-congruence-review",
        name: "Walk Away From TRT Congruence Review",
        hypothesis:
          "Swipe-image creatives using only awareness level plus destination context can create congruent reviewable ads for the supplied presales URL.",
        metricIds: [],
        variants: [
          {
            id: "presales",
            name: "Presales",
            description: "Ad-to-advertorial creatives for the supplied Walk Away From TRT presales URL.",
            channels: ["meta"],
            guardrails: ["no product reveal", "no mechanism reveal"],
          },
        ],
      },
    ],
  };
}

function assetBriefPayload() {
  const brief = {
    id: ASSET_BRIEF_ID,
    clientId: CLIENT_ID,
    campaignId: CAMPAIGN_ID,
    experimentId: "walk-away-trt-congruence-review",
    variantId: "presales",
    funnelId: null,
    deliveryMode: "external_urls",
    destinationType: "pre-sales",
    destinationLabel: "Walk Away From TRT presales",
    variantName: "Walk Away From TRT",
    creativeConcept: "Destination-congruent swipe-image ad creative for the Walk Away From TRT advertorial.",
    requirements: [
      {
        channel: "meta",
        format: "image",
        funnelStage: "top-of-funnel",
        destinationType: "pre-sales",
        destinationLabel: "Walk Away From TRT presales",
        angle: "Destination-congruent creative for the Walk Away From TRT advertorial.",
        hook: "Problem-Aware",
      },
      {
        channel: "meta",
        format: "image",
        funnelStage: "top-of-funnel",
        destinationType: "pre-sales",
        destinationLabel: "Walk Away From TRT presales",
        angle: "Destination-congruent creative for the Walk Away From TRT advertorial.",
        hook: "Solution-Aware",
      },
    ],
    constraints: [],
    toneGuidelines: [],
    visualGuidelines: [],
  };
  return {
    asset_briefs: [brief],
    source: "tenor-walk-away-trt-review-setup",
    createdFor: "first review sample generation",
  };
}

function seedAssetBriefViaSsh() {
  const payloadPath = path.join(OUT_DIR, "asset-brief-payload.json");
  writeFileSync(payloadPath, JSON.stringify(assetBriefPayload(), null, 2) + "\n");

  const remotePayloadPath = "/root/tmp/tenor-walk-away-trt-asset-brief.json";
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

campaign_id = "${CAMPAIGN_ID}"
brief_id = "${ASSET_BRIEF_ID}"
payload = json.loads(Path("${remotePayloadPath}").read_text())

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
        for brief in data.get("asset_briefs") or data.get("assetBriefs") or []:
            if isinstance(brief, dict) and str(brief.get("id")) == brief_id:
                artifact.data = payload
                session.add(artifact)
                session.commit()
                print(json.dumps({"status": "updated", "artifactId": str(artifact.id), "briefId": brief_id}))
                raise SystemExit(0)
    artifact = repo.insert(
        org_id=str(campaign.org_id),
        client_id=str(campaign.client_id),
        product_id=str(campaign.product_id) if campaign.product_id else None,
        campaign_id=str(campaign.id),
        artifact_type=ArtifactTypeEnum.asset_brief,
        data=payload,
    )
    print(json.dumps({"status": "created", "artifactId": str(artifact.id), "briefId": brief_id}))
`;

  const result = execFileSync("ssh", [
    "-i",
    path.join(os.homedir(), ".ssh/hetzner_prod"),
    "-o",
    "BatchMode=yes",
    "root@api.moshq.app",
    "cd /opt/apps/mos-api/mos/backend && set -a && . /etc/cloudhand/env/mos-api.env && set +a && .venv/bin/python -",
  ], { input: py, encoding: "utf8" });
  const parsed = JSON.parse(result.trim().split(/\r?\n/).at(-1));
  writeFileSync(path.join(OUT_DIR, "asset-brief-seed-result.json"), JSON.stringify(parsed, null, 2) + "\n");
  return parsed;
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

async function resolveAsset(assetId) {
  const rows = await authed(
    `/assets?campaignId=${encodeURIComponent(CAMPAIGN_ID)}&productId=${encodeURIComponent(PRODUCT_ID)}&assetKind=image`,
  );
  const row = rows.find((asset) => asset.id === assetId);
  if (!row?.public_id) throw new Error(`Could not resolve generated public_id for asset ${assetId}`);
  return row;
}

function downloadPublicAsset(publicId, outputPath) {
  execFileSync("curl", ["-sS", "-L", `${API_BASE}/public/assets/${publicId}`, "-o", outputPath], { stdio: "inherit" });
}

async function main() {
  mkdirSync(OUT_DIR, { recursive: true });
  mkdirSync(GENERATED_DIR, { recursive: true });
  mkdirSync(path.join(REVIEW_DIR, "generated"), { recursive: true });

  await getBackendToken();

  const campaign = await authed(`/campaigns/${encodeURIComponent(CAMPAIGN_ID)}`);
  if (campaign.name !== CAMPAIGN_NAME) {
    throw new Error(`Unexpected campaign name for ${CAMPAIGN_ID}: ${campaign.name}`);
  }

  await authed(`/campaigns/${encodeURIComponent(CAMPAIGN_ID)}/creative-context/provider`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider: "manual" }),
  });

  const manualPayload = manualCreativeContextPayload();
  writeFileSync(path.join(OUT_DIR, "manual-creative-context-payload.json"), JSON.stringify(manualPayload, null, 2) + "\n");
  const manualContext = await authed(`/campaigns/${encodeURIComponent(CAMPAIGN_ID)}/creative-context/loaded`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(manualPayload),
  });

  const readiness = await authed(`/campaigns/${encodeURIComponent(CAMPAIGN_ID)}/launch-context-readiness`);
  if (!readiness.ready) {
    throw new Error(`Manual creative context is not ready: ${JSON.stringify(readiness)}`);
  }

  const delivery = await authed(`/campaigns/${encodeURIComponent(CAMPAIGN_ID)}/delivery`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      deliveryMode: "external_urls",
      preSalesUrl: PRESALES_URL,
      salesUrl: SALES_URL,
    }),
  });
  const assetBriefSeed = seedAssetBriefViaSsh();
  writeFileSync(path.join(OUT_DIR, "setup-state.json"), JSON.stringify({
    campaignId: CAMPAIGN_ID,
    delivery,
    manualContext,
    readiness,
    assetBriefSeed,
    destinationContext: DESTINATION_CONTEXT,
    updatedAt: new Date().toISOString(),
  }, null, 2) + "\n");
  const deliveryValidation = process.env.SKIP_DELIVERY_VALIDATE === "1"
    ? {
        checkedAt: new Date().toISOString(),
        validationStatus: "valid",
        validationError: null,
        override: "Skipped API validation because MOSProd delivery status was explicitly overridden for external URLs.",
        delivery: await authed(`/campaigns/${encodeURIComponent(CAMPAIGN_ID)}/delivery`),
      }
    : await authed(`/campaigns/${encodeURIComponent(CAMPAIGN_ID)}/delivery/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
  if (deliveryValidation.validationStatus !== "valid") {
    throw new Error(`Delivery validation failed: ${JSON.stringify(deliveryValidation, null, 2)}`);
  }

  const outputs = [];
  for (const run of REVIEW_RUNS) {
    const angle = swipeAngle(run.awarenessLevel);
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
      swipeAngle: angle,
      aspectRatio: "1:1",
      count: 1,
    };
    const started = await authed("/swipes/generate-image-ad", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const detail = await waitForWorkflow(started.workflow_run_id);
    const workflowPath = path.join(OUT_DIR, `workflow-${run.key}.json`);
    writeFileSync(workflowPath, JSON.stringify(detail, null, 2) + "\n");
    const { assetId, payloadOut } = extractAssetId(detail);
    const asset = await resolveAsset(assetId);
    const localPath = path.join(GENERATED_DIR, `${run.key}.jpg`);
    const reviewPath = path.join(REVIEW_DIR, "generated", `${run.key}.jpg`);
    downloadPublicAsset(asset.public_id, localPath);
    execFileSync("cp", [localPath, reviewPath]);
    outputs.push({
      key: run.key,
      awarenessLevel: run.awarenessLevel,
      source: {
        companySwipeId: run.companySwipeId,
        sourceSwipeTitle: run.sourceSwipeTitle,
        assetBriefId: ASSET_BRIEF_ID,
        requirementIndex: 1,
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
    writeFileSync(path.join(OUT_DIR, "manifest.json"), JSON.stringify({
      createdAt: new Date().toISOString(),
      outputDir: OUT_DIR,
      reviewDir: REVIEW_DIR,
      generatedDir: GENERATED_DIR,
      workspace: {
        workspaceName: "Tenor",
        campaignId: CAMPAIGN_ID,
        clientId: CLIENT_ID,
        productId: PRODUCT_ID,
      },
      destinationContext: DESTINATION_CONTEXT,
      delivery,
      deliveryValidation,
      manualContext,
      assetBriefSeed,
      outputs,
    }, null, 2) + "\n");
  }

  console.log(JSON.stringify({
    campaignId: CAMPAIGN_ID,
    reviewDir: REVIEW_DIR,
    generated: outputs.map((output) => ({
      key: output.key,
      assetId: output.result.assetId,
      reviewPath: output.result.reviewPath,
      publicUrl: output.result.publicUrl,
    })),
  }, null, 2));
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exitCode = 1;
});
