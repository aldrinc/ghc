import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const OLD_OUT_DIR = path.join(ROOT, "outputs/tenor-walk-away-trt-campaign-2026-05-02");
const OUT_DIR = path.join(ROOT, "outputs/tenor-walk-away-trt-no-product-regeneration-2026-05-03");
const MANIFEST_PATH = path.join(OUT_DIR, "manifest.json");
const SOURCE_MANIFEST_PATH = path.join(OLD_OUT_DIR, "full-launch-manifest.json");
const COPY_SPECS_PATH = path.join(OLD_OUT_DIR, "meta-review-copy-specs.json");
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
const BATCH_ID = "tenor-walk-away-trt-no-product-20260503";
const GENERATION_KEY = `batch:${BATCH_ID}`;
const PRESALES_URL = "https://shoptenorco.com/8b89a76d/daily-drive-essentials/walk-away-from-trt/";

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

function readJson(filePath) {
  return JSON.parse(readFileSync(filePath, "utf8"));
}

function sortByRunKey(outputs) {
  return [...outputs].sort((a, b) => Number(a.key.split("-", 1)[0]) - Number(b.key.split("-", 1)[0]));
}

function assertManifests() {
  const regeneratedManifest = readJson(MANIFEST_PATH);
  const sourceManifest = readJson(SOURCE_MANIFEST_PATH);
  const copySpecs = readJson(COPY_SPECS_PATH);
  if (!Array.isArray(regeneratedManifest.outputs) || regeneratedManifest.outputs.length !== 30) {
    throw new Error(`Expected 30 regenerated outputs in ${MANIFEST_PATH}`);
  }
  if (!Array.isArray(sourceManifest.outputs) || sourceManifest.outputs.length !== 30) {
    throw new Error(`Expected 30 source outputs in ${SOURCE_MANIFEST_PATH}`);
  }
  if (!Array.isArray(copySpecs.rows) || copySpecs.rows.length !== 30) {
    throw new Error(`Expected 30 copy spec rows in ${COPY_SPECS_PATH}`);
  }
  return { regeneratedManifest, sourceManifest, copySpecs };
}

function ctaToType(cta) {
  const normalized = String(cta || "").trim().toLowerCase();
  if (normalized === "learn more") return "LEARN_MORE";
  if (normalized === "shop now") return "SHOP_NOW";
  throw new Error(`Unsupported CTA from copy specs: ${cta}`);
}

function buildOutputRows() {
  const { regeneratedManifest, sourceManifest, copySpecs } = assertManifests();
  const oldByKey = new Map(sourceManifest.outputs.map((output) => [output.key, output]));
  const copyByOldAssetId = new Map(copySpecs.rows.map((row) => [row.assetId, row]));
  return sortByRunKey(regeneratedManifest.outputs).map((output, index) => {
    const oldOutput = oldByKey.get(output.key);
    if (!oldOutput?.result?.assetId) {
      throw new Error(`Could not map regenerated output ${output.key} to old source output.`);
    }
    const copy = copyByOldAssetId.get(oldOutput.result.assetId);
    if (!copy) {
      throw new Error(`No MOS-generated copy spec row found for old asset ${oldOutput.result.assetId} (${output.key}).`);
    }
    return {
      ...output,
      adId: `WA-NP-${String(index + 1).padStart(2, "0")}`,
      oldAssetId: oldOutput.result.assetId,
      copy,
    };
  });
}

async function assertCampaign() {
  await getBackendToken();
  const campaign = await authed(`/campaigns/${encodeURIComponent(CAMPAIGN_ID)}`);
  if (!campaign?.id) throw new Error(`Campaign not found: ${CAMPAIGN_ID}`);
  return campaign;
}

async function getCampaignAssets() {
  return authed(
    `/assets?campaignId=${encodeURIComponent(CAMPAIGN_ID)}&productId=${encodeURIComponent(PRODUCT_ID)}&assetKind=image`,
  );
}

function stampBatchViaSsh(assetIds) {
  const payloadPath = path.join(OUT_DIR, "batch-stamp-input.json");
  writeFileSync(payloadPath, JSON.stringify({ campaignId: CAMPAIGN_ID, batchId: BATCH_ID, assetIds }, null, 2) + "\n");
  const remotePayloadPath = "/root/tmp/tenor-walk-away-trt-no-product-batch-stamp.json";
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
        metadata["noProductVisualRequirement"] = True
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
  const rows = buildOutputRows();
  const assetIds = rows.map((row) => row.result.assetId);
  if (new Set(assetIds).size !== 30) {
    throw new Error(`Expected 30 unique regenerated asset IDs; got ${new Set(assetIds).size}`);
  }
  const stamp = stampBatchViaSsh(assetIds);
  const assets = await getCampaignAssets();
  const byId = new Map(assets.map((asset) => [asset.id, asset]));
  const mismatched = assetIds.filter((assetId) => byId.get(assetId)?.ai_metadata?.creativeGenerationBatchId !== BATCH_ID);
  if (mismatched.length) {
    throw new Error(`Batch stamp verification failed for assets: ${mismatched.join(", ")}`);
  }
  const manifest = readJson(MANIFEST_PATH);
  writeFileSync(MANIFEST_PATH, JSON.stringify({ ...manifest, batchId: BATCH_ID, generationKey: GENERATION_KEY, batchStamp: stamp, updatedAt: new Date().toISOString() }, null, 2) + "\n");
  console.log(JSON.stringify({ campaignId: CAMPAIGN_ID, generationKey: GENERATION_KEY, stamp }, null, 2));
}

async function getCreativeSpecs() {
  return authed(`/meta/specs/creatives?campaignId=${encodeURIComponent(CAMPAIGN_ID)}`);
}

async function getAdSetSpecs() {
  return authed(`/meta/specs/adsets?campaignId=${encodeURIComponent(CAMPAIGN_ID)}`);
}

async function getActiveMetaConfig() {
  return authed(`/meta/clients/${encodeURIComponent(CLIENT_ID)}/active-config`);
}

function specMetadata(spec) {
  if (spec.metadata_json && typeof spec.metadata_json === "object") return spec.metadata_json;
  if (spec.metadata && typeof spec.metadata === "object") return spec.metadata;
  return {};
}

function specAssetId(spec) {
  return spec.asset_id || spec.assetId || null;
}

function specPrimaryText(spec) {
  return spec.primary_text || spec.primaryText || null;
}

function specDestinationUrl(spec) {
  return spec.destination_url || spec.destinationUrl || null;
}

function adsetId(spec) {
  return spec.id || spec.adsetSpecId || null;
}

function adsetPromotedObject(spec) {
  return spec.promoted_object || spec.promotedObject || null;
}

async function upsertCreativeSpec(row, existingByAssetId) {
  const assetId = row.result.assetId;
  const body = {
    campaignId: CAMPAIGN_ID,
    name: `${row.adId} - ${row.copy.headline}`,
    primaryText: row.copy.primaryText,
    headline: row.copy.headline,
    description: row.copy.description || null,
    callToActionType: ctaToType(row.copy.cta),
    destinationUrl: row.copy.destinationUrl || PRESALES_URL,
    status: "draft",
    metadata: {
      externalRoutingAdId: row.adId,
      externalDestinationKey: "walk_away_trt_presales",
      externalFinalUrl: row.copy.destinationUrl || PRESALES_URL,
      externalRoutingSource: MANIFEST_PATH,
      awarenessLevel: row.awarenessLevel,
      batchId: BATCH_ID,
      noProductVisualRequirement: true,
      sourceSwipeTitle: row.source.sourceSwipeTitle,
      sourceCompanySwipeId: row.source.companySwipeId,
      previousProductBatchAssetId: row.oldAssetId,
      sourceCopySpecId: row.copy.creativeSpecId,
      sourceCopySelectedVariation: row.copy.selectedVariation,
    },
  };
  const existing = existingByAssetId.get(assetId);
  if (!existing) {
    const created = await authed("/meta/specs/creatives", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assetId, ...body }),
    });
    return { action: "created", adId: row.adId, assetId, creativeSpecId: created.id || null };
  }
  const needsUpdate =
    specPrimaryText(existing) !== body.primaryText ||
    existing.headline !== body.headline ||
    specDestinationUrl(existing) !== body.destinationUrl ||
    specMetadata(existing).batchId !== BATCH_ID;
  if (!needsUpdate) {
    return { action: "verified", adId: row.adId, assetId, creativeSpecId: existing.id || null };
  }
  const updated = await authed(`/meta/specs/creatives/${encodeURIComponent(existing.id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return { action: "updated", adId: row.adId, assetId, creativeSpecId: updated.id || existing.id || null };
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
        source: "tenor_walk_away_trt_no_product_launch_20260503",
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
      existing.name === body.name &&
      existing.optimization_goal === body.optimizationGoal &&
      existing.billing_event === body.billingEvent &&
      JSON.stringify(adsetPromotedObject(existing)) === JSON.stringify(promotedObject) &&
      metadata.source === body.metadata.source
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
  const rows = buildOutputRows();
  const assets = await getCampaignAssets();
  const byId = new Map(assets.map((asset) => [asset.id, asset]));
  const missingBatch = rows
    .map((row) => byId.get(row.result.assetId))
    .filter((asset) => asset?.ai_metadata?.creativeGenerationBatchId !== BATCH_ID)
    .map((asset) => asset?.id || "missing");
  if (missingBatch.length) {
    throw new Error(`Run stamp-batch before create-specs. Missing batch on: ${missingBatch.join(", ")}`);
  }

  const existingSpecs = await getCreativeSpecs();
  const byAssetId = new Map();
  for (const spec of existingSpecs || []) {
    const assetId = specAssetId(spec);
    if (assetId) byAssetId.set(assetId, spec);
  }
  const creativeSpecs = [];
  for (const row of rows) {
    creativeSpecs.push(await upsertCreativeSpec(row, byAssetId));
  }
  const adsetSpecs = await upsertAdSetSpecs(await getAdSetSpecs());
  const specsPath = path.join(OUT_DIR, "no-product-launch-specs.json");
  writeFileSync(specsPath, JSON.stringify({
    campaignId: CAMPAIGN_ID,
    generationKey: GENERATION_KEY,
    createdAt: new Date().toISOString(),
    creativeSpecs,
    adsetSpecs,
  }, null, 2) + "\n");
  console.log(JSON.stringify({
    campaignId: CAMPAIGN_ID,
    generationKey: GENERATION_KEY,
    creativeSpecs: creativeSpecs.reduce((acc, row) => ({ ...acc, [row.action]: (acc[row.action] || 0) + 1 }), {}),
    adsetSpecs: adsetSpecs.reduce((acc, row) => ({ ...acc, [row.action]: (acc[row.action] || 0) + 1 }), {}),
    specsPath,
  }, null, 2));
}

function publishPayload() {
  return {
    generationKey: GENERATION_KEY,
    publishBaseUrl: "https://shop.shoptenorco.com",
    campaignName: "Tenor - Walk Away From TRT - No Product - 2026-05-03",
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
  const payload = publishPayload();
  const response = await authed(`/meta/campaigns/${encodeURIComponent(CAMPAIGN_ID)}/publish-plan/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const validationPath = path.join(OUT_DIR, "no-product-publish-validation.json");
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
  const payload = publishPayload();
  const response = await authed(`/meta/campaigns/${encodeURIComponent(CAMPAIGN_ID)}/publish-runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const publishPath = path.join(OUT_DIR, "no-product-publish-run-response.json");
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
  if (command === "stamp-batch") return cmdStampBatch();
  if (command === "create-specs") return cmdCreateSpecs();
  if (command === "validate-publish") return cmdValidatePublish();
  if (command === "publish") return cmdPublish();
  if (command === "all") {
    await cmdStampBatch();
    await cmdCreateSpecs();
    await cmdValidatePublish();
    await cmdPublish();
    return;
  }
  throw new Error("Usage: node publish_no_product_campaign.mjs stamp-batch|create-specs|validate-publish|publish|all");
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exitCode = 1;
});
