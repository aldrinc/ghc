import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const PACKAGE_DIR = path.join(ROOT, "outputs/mars-men-glp-quiz-campaign-package-2026-05-04");
const OUT_DIR = path.join(PACKAGE_DIR, "pilot-output");
const AUTH_FILE = path.join(ROOT, ".env.mos-test-auth");
const PILOT_MANIFEST_PATH = path.join(OUT_DIR, "c001-gpt-image2-pilot-manifest.json");
const META_MANIFEST_PATH = path.join(OUT_DIR, "c001-gpt-image2-meta-spec-manifest.json");

const API_BASE = "https://api.moshq.app";
const CLERK_BASE = "https://immune-turtle-79.clerk.accounts.dev/v1";
const CLERK_QUERY = "__clerk_api_version=2025-11-10&_clerk_js_version=5.125.10";
const ORIGIN_HEADERS = {
  Origin: "https://moshq.app",
  Referer: "https://moshq.app/",
};

const GLP_PRESALE_URL = "https://shoptenorco.com/8b89a76d/daily-drive-essentials/10-reasons-glp/";
const SALES_URL =
  "https://shoptenorco.com/8b89a76d/daily-drive-essentials/sales-page/?selling_plan=2948432039";
const PUBLISH_BASE_URL = "https://shop.shoptenorco.com";

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
    if (char === '"') quoted = true;
    else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (char !== "\r") field += char;
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

async function main() {
  const pilot = JSON.parse(readFileSync(PILOT_MANIFEST_PATH, "utf8"));
  const rows = parseCsv(readFileSync(path.join(PACKAGE_DIR, "glp-quiz-campaign-ready-expanded.csv"), "utf8"));
  const row = rows.find((entry) => entry.creative_id === "C001" && entry.remix_copy_id === "TENOR-COPY001");
  if (!row) throw new Error("Could not find TENOR-COPY001 / C001 in expanded campaign CSV.");
  if (pilot.output.aiMetadata?.swipeRenderModelIdUsed !== "gpt-image-2") {
    throw new Error(
      `Pilot asset renderer mismatch: expected gpt-image-2, got ${pilot.output.aiMetadata?.swipeRenderModelIdUsed}`,
    );
  }
  if (pilot.output.aiMetadata?.swipePromptImageSha256 !== pilot.source.expectedSha256) {
    throw new Error("Pilot asset source hash metadata does not match package C001 hash.");
  }

  await getBackendToken();
  const existing = await authed(`/meta/specs/creatives?assetId=${encodeURIComponent(pilot.output.assetId)}`);
  let creativeSpec = existing[0] || null;
  const creativePayload = {
    assetId: pilot.output.assetId,
    campaignId: pilot.campaignId,
    name: "GLP Pilot GPT Image 2 - TENOR-COPY001 C001 - What GLP-1 Does to Your Drive",
    primaryText: row.remix_body,
    headline: row.remix_title,
    description: row.remix_link_description,
    callToActionType: "LEARN_MORE",
    destinationUrl: GLP_PRESALE_URL,
    status: "draft",
    metadata: {
      packageDir: PACKAGE_DIR,
      sourceCsv: path.join(PACKAGE_DIR, "glp-quiz-campaign-ready-expanded.csv"),
      launchSlot: row.launch_slot,
      sourceCopyId: row.source_copy_id,
      remixCopyId: row.remix_copy_id,
      creativeId: row.creative_id,
      creativeFile: row.creative_file,
      creativeReferenceTitle: row.creative_reference_title,
      sourceCreativeSha256: pilot.source.expectedSha256,
      stagedSourceSha256: pilot.source.stagedSha256,
      sourceCta: row.remix_cta,
      ctaMapping: { source: row.remix_cta, metaEnum: "LEARN_MORE" },
      presaleUrl: GLP_PRESALE_URL,
      salesUrl: SALES_URL,
      generation: {
        stageOneModel: pilot.generation.stageOneModel,
        renderModelId: pilot.generation.renderModelId,
        workflowRunId: pilot.generation.workflowRunId,
        workflowUrl: pilot.generation.workflowUrl,
        remoteJobId: pilot.output.aiMetadata.remoteJobId,
        generatedAssetPublicUrl: pilot.output.publicUrl,
      },
    },
  };

  let creativeAction = "reused";
  if (!creativeSpec) {
    creativeSpec = await authed("/meta/specs/creatives", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(creativePayload),
    });
    creativeAction = "created";
  } else {
    creativeSpec = await authed(`/meta/specs/creatives/${encodeURIComponent(creativeSpec.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(creativePayload),
    });
    creativeAction = "updated";
  }

  const generationKey = `remoteJob:${pilot.output.aiMetadata.remoteJobId}`;
  const validationPayload = {
    generationKey,
    publishBaseUrl: PUBLISH_BASE_URL,
    campaignName: "Tenor GLP Pilot GPT Image 2 - C001 - 2026-05-05",
    campaignObjective: "OUTCOME_SALES",
    buyingType: "AUCTION",
    specialAdCategories: [],
    campaignDailyBudget: 10000,
    bucketCount: 1,
    bucketDestinationUrls: [],
  };
  const validation = await authed(`/meta/campaigns/${encodeURIComponent(pilot.campaignId)}/publish-plan/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(validationPayload),
  });

  const manifest = {
    createdAt: new Date().toISOString(),
    creativeAction,
    creativeSpecId: creativeSpec.id,
    assetId: pilot.output.assetId,
    generationKey,
    validationPayload,
    validation,
  };
  writeFileSync(META_MANIFEST_PATH, JSON.stringify(manifest, null, 2) + "\n");
  console.log(JSON.stringify({ manifestPath: META_MANIFEST_PATH, ...manifest }, null, 2));
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exitCode = 1;
});
