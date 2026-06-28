import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const PACKAGE_DIR = path.join(ROOT, "outputs/mars-men-glp-quiz-campaign-package-2026-05-04");
const OUT_DIR = path.join(PACKAGE_DIR, "pilot-output");
const AUTH_FILE = path.join(ROOT, ".env.mos-test-auth");
const META_SPEC_MANIFEST_PATH = path.join(OUT_DIR, "c001-gpt-image2-meta-spec-manifest.json");
const PUBLISH_MANIFEST_PATH = path.join(OUT_DIR, "c001-gpt-image2-meta-publish-run.json");

const API_BASE = "https://api.moshq.app";
const CLERK_BASE = "https://immune-turtle-79.clerk.accounts.dev/v1";
const CLERK_QUERY = "__clerk_api_version=2025-11-10&_clerk_js_version=5.125.10";
const ORIGIN_HEADERS = {
  Origin: "https://moshq.app",
  Referer: "https://moshq.app/",
};

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

async function main() {
  const metaSpecManifest = JSON.parse(readFileSync(META_SPEC_MANIFEST_PATH, "utf8"));
  if (metaSpecManifest.validation?.ok !== true) {
    throw new Error("Refusing to publish because the stored publish-plan validation is not ok.");
  }
  const campaignId = metaSpecManifest.validation.campaignId;
  const publishRun = await authed(`/meta/campaigns/${encodeURIComponent(campaignId)}/publish-runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(metaSpecManifest.validationPayload),
  });
  writeFileSync(PUBLISH_MANIFEST_PATH, JSON.stringify(publishRun, null, 2) + "\n");
  console.log(
    JSON.stringify(
      {
        manifestPath: PUBLISH_MANIFEST_PATH,
        publishRunId: publishRun.id,
        status: publishRun.status,
        metaCampaignId: publishRun.metaCampaignId,
        items: (publishRun.items || []).map((item) => ({
          assetId: item.assetId,
          status: item.status,
          metaAssetUploadId: item.metaAssetUploadId,
          metaCreativeId: item.metaCreativeId,
          metaAdSetId: item.metaAdSetId,
          metaAdId: item.metaAdId,
          errorMessage: item.errorMessage,
        })),
      },
      null,
      2,
    ),
  );
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exitCode = 1;
});
