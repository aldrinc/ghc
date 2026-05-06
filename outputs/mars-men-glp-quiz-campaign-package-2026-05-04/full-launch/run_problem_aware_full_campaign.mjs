import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const PACKAGE_DIR = path.join(ROOT, "outputs/mars-men-glp-quiz-campaign-package-2026-05-04");
const FULL_LAUNCH_DIR = path.join(PACKAGE_DIR, "full-launch");
const OUT_DIR = path.join(FULL_LAUNCH_DIR, "problem-aware-full-campaign");
const GENERATED_DIR = path.join(OUT_DIR, "generated");
const REVIEW_DIR = path.join(OUT_DIR, "review");
const AUTH_FILE = path.join(ROOT, ".env.mos-test-auth");
const STATE_PATH = path.join(OUT_DIR, "campaign-state.json");
const REVIEW_PATH = path.join(FULL_LAUNCH_DIR, "destination-congruence-review-v2.json");
const MANIFEST_PATH = path.join(OUT_DIR, "problem-aware-full-manifest.json");

const API_BASE = process.env.MOS_API_BASE || "https://api.moshq.app";
const CLERK_BASE = "https://immune-turtle-79.clerk.accounts.dev/v1";
const CLERK_QUERY = "__clerk_api_version=2025-11-10&_clerk_js_version=5.125.10";
const ORIGIN_HEADERS = {
  Origin: "https://moshq.app",
  Referer: "https://moshq.app/",
};

const CLIENT_ID = "70124684-505f-48af-a25c-5f7a79601fa0";
const PRODUCT_ID = "8b89a76d-069c-41a6-be38-b7e4f4483460";
const MOS_GENERATION_CAMPAIGN_ID = "426afe15-ac66-436c-910d-2a1259597bf3";
const CAMPAIGN_NAME = "Tenor - GLP + Quiz - Problem-Aware Swipe Expansion - 2026-05-06";
const META_CAMPAIGN_NAME = "Tenor - GLP + Quiz - Problem-Aware Swipe Expansion - 2026-05-06";
const BATCH_ID = "tenor-glp-quiz-problem-aware-expansion-20260506";
const GENERATION_KEY = `batch:${BATCH_ID}`;
const EXPERIMENT_ID = "tenor-glp-quiz-problem-aware-expansion";
const GLP_BRIEF_ID = "brief_glp_listicle_swipe_image2";
const QUIZ_BRIEF_ID = "brief_quiz_funnel_swipe_image2";
const STAGING_FUNNEL_ID = "be65d76e-ced9-4948-9465-18723c8446fd";
const STAGING_PAGE_ID = "ab3102f4-a179-410a-9eb0-66aa3020cafc";
const STAGE_ONE_MODEL = "gemini-3.1-pro-preview";
const RENDER_MODEL_ID = "gpt-image-2";
const NANOBANANA_RENDER_MODEL_ID = "gemini-3.1-flash-image-preview";
const NANOBANANA_RENDER_MODEL_ID_USED = `models/${NANOBANANA_RENDER_MODEL_ID}`;
const CURATED_COLLECTION_ID = "b89e89f4-2565-4b5d-afd1-195532613bfb";
const CURATED_COLLECTION_NAME = "Tenor initial swipe collection";
const TENOR_PRIMARY_RED_HEX = "#ee1f2d";
const BRAND_COLOR_POLICY = [
  "Brand color policy:",
  `Use Tenor primary red ${TENOR_PRIMARY_RED_HEX} for brand accents and CTA accents in the generated ad image.`,
  "Do not reproduce the orange accent color from the source reference.",
].join("\n");
const CURATED_NO_PRODUCT_REVEAL_POLICY = [
  "Curated source product-reveal policy:",
  "Do not show the Tenor product, Daily Drive Essentials packaging, bottles, capsules, labels, Supplement Facts panels, checkout/product-page imagery, or any product reference image in the generated image.",
  "Keep the image problem-aware and non-product-facing while preserving the selected swipe composition.",
].join("\n");
const PUBLISH_BASE_URL = "https://shoptenorco.com";
const GLP_PRESALE_URL = "https://shoptenorco.com/8b89a76d/daily-drive-essentials/10-reasons-glp/";
const QUIZ_PRESALE_URL = "https://shoptenorco.com/8b89a76d/daily-drive-essentials/quiz/";
const SALES_URL =
  "https://shoptenorco.com/8b89a76d/daily-drive-essentials/sales-page/?selling_plan=2948432039";
const GENERATE_CONCURRENCY = Number(process.env.GENERATE_CONCURRENCY || "4");
const FORCE_NANOBANANA_FALLBACK_FOR_PENDING = process.env.FORCE_NANOBANANA_FALLBACK_FOR_PENDING === "1";
const CONTINUE_ON_FAILURE = process.env.CONTINUE_ON_FAILURE === "1";
const TENOR_PRODUCT_REFERENCE_CREATIVE_IDS = new Set([
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
const VERIFIED_OPENAI_MODERATION_FALLBACK_KEYS = new Set([
  "tenor-06-C008-glp",
]);
const ASPECT_RATIOS = ["1:1", "4:5", "9:16"];
const PRIMARY_ASPECT_RATIO = "1:1";
const CURRENT_OFFER = {
  salePrice: "$44",
  savingsPercent: "52%",
  compareAtPrice: "$92",
  supply: "30-day supply",
  guarantee: "90-day empty-bottle guarantee",
  welcomeKitValue: "$35",
  welcomeOffer: "52% off limited-time welcome offer",
};
const GROUP_ASPECT_RATIOS = Object.freeze(["1:1", "4:5", "9:16"]);
const GROUP_ASPECT_RATIO_ORDER = new Map(GROUP_ASPECT_RATIOS.map((aspectRatio, index) => [aspectRatio, index]));
const NORMALIZED_OFFER = Object.freeze({
  entryPrice: "$44",
  savings: "52% off",
  supply: "30-day supply",
  guarantee: "90-day guarantee",
  welcomeKitValue: "$35 Welcome Kit value",
});

let cachedToken = null;

function aspectRatioKey(aspectRatio) {
  return String(aspectRatio).replaceAll(":", "x");
}

function primaryAspectRatioFor(nativeAspectRatio, fallbackAspectRatio = "1:1") {
  if (GROUP_ASPECT_RATIO_ORDER.has(nativeAspectRatio)) return nativeAspectRatio;
  if (!GROUP_ASPECT_RATIO_ORDER.has(fallbackAspectRatio)) {
    throw new Error(`Unsupported grouped aspect ratio fallback: ${fallbackAspectRatio}`);
  }
  return fallbackAspectRatio;
}

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

function readRows() {
  const rows = parseCsv(readFileSync(path.join(PACKAGE_DIR, "glp-quiz-campaign-ready-expanded.csv"), "utf8"));
  if (rows.length !== 23) {
    throw new Error(`Expected 23 campaign rows, found ${rows.length}.`);
  }
  return rows.map((row, index) => ({
    ...row,
    rowIndex: index + 1,
    rowKey: `${String(index + 1).padStart(2, "0")}-${row.remix_copy_id}-${row.creative_id}`,
    sourcePath: path.join(PACKAGE_DIR, row.creative_file),
  }));
}

function destinationUrlForLaunchSlot(launchSlot) {
  if (launchSlot === "Quiz funnel") return QUIZ_PRESALE_URL;
  if (launchSlot === "GLP lander") return GLP_PRESALE_URL;
  throw new Error(`Unsupported launch slot: ${launchSlot}`);
}

function destinationKeyForLaunchSlot(launchSlot) {
  return launchSlot === "Quiz funnel" ? "quiz" : "glp";
}

function assetBriefIdForDestinationKey(destinationKey) {
  if (destinationKey === "quiz") return QUIZ_BRIEF_ID;
  if (destinationKey === "glp") return GLP_BRIEF_ID;
  throw new Error(`Unsupported destination key: ${destinationKey}`);
}

function copyUnitFromRow(row) {
  return normalizeCopyUnit({
    sourceCopyId: row.source_copy_id,
    remixCopyId: row.remix_copy_id,
    title: row.remix_title,
    body: row.remix_body,
    cta: row.remix_cta,
    linkDescription: row.remix_link_description || "-",
    destinationUrl: destinationUrlForLaunchSlot(row.launch_slot),
    salesUrl: SALES_URL,
    launchSlot: row.launch_slot,
  });
}

function normalizeCopyUnit(copy) {
  return {
    ...copy,
    title: normalizeHeadline(copy.title),
    body: normalizeBody(copy.body),
    linkDescription: normalizeLinkDescription(copy.linkDescription),
  };
}

function normalizeHeadline(text) {
  if (!text) return text;
  if (/Save 52%\s*\+\s*Free \$62 Welcome Kit 🚀/i.test(text)) return "52% Off Limited-Time Welcome Offer";
  if (/50% Off \+ Free Gifts 🚀/i.test(text)) return "52% Off Limited-Time Welcome Offer";
  if (/Save 52%\s*[—-]\s*90-Day Guarantee/i.test(text)) return "52% Off + 90-Day Guarantee";
  return normalizeOfferCopyText(text);
}

function normalizeBody(text) {
  return normalizeOfferCopyText(text);
}

function normalizeLinkDescription(text) {
  if (!text || text === "-") return text || "-";
  return normalizeOfferCopyText(text)
    .replace(/✅\s*90-day guarantee/gi, "✅ 90-Day Guarantee")
    .replace(/✅\s*90-Day Guarantee/gi, "✅ 90-Day Guarantee");
}

function normalizeOfferCopyText(text) {
  if (!text) return text;
  const replacements = [
    [
      /Save 52% on your first 90-day supply\. 90-day empty-bottle guarantee\./gi,
      `Get your ${NORMALIZED_OFFER.supply} for ${NORMALIZED_OFFER.entryPrice} at ${NORMALIZED_OFFER.savings}. ${NORMALIZED_OFFER.guarantee}.`,
    ],
    [
      /Save 52% on the 90-day supply\. 90-day empty-bottle guarantee\./gi,
      `Get your ${NORMALIZED_OFFER.supply} for ${NORMALIZED_OFFER.entryPrice} at ${NORMALIZED_OFFER.savings}. ${NORMALIZED_OFFER.guarantee}.`,
    ],
    [
      /Save 52% on your 90-day supply\. 90-day empty-bottle guarantee\./gi,
      `Get your ${NORMALIZED_OFFER.supply} for ${NORMALIZED_OFFER.entryPrice} at ${NORMALIZED_OFFER.savings}. ${NORMALIZED_OFFER.guarantee}.`,
    ],
    [
      /👉 Save 52% — 90-day empty-bottle guarantee\./gi,
      `👉 Get your ${NORMALIZED_OFFER.supply} for ${NORMALIZED_OFFER.entryPrice} at ${NORMALIZED_OFFER.savings}. ${NORMALIZED_OFFER.guarantee}.`,
    ],
    [
      /Save 52% on your 90-day supply — plus a \$62 Welcome Kit and free shipping\. Every bottle backed by a 90-day empty-bottle guarantee\./gi,
      `Get your ${NORMALIZED_OFFER.supply} for ${NORMALIZED_OFFER.entryPrice} at ${NORMALIZED_OFFER.savings} and receive a ${NORMALIZED_OFFER.welcomeKitValue}. Every order is backed by a ${NORMALIZED_OFFER.guarantee}.`,
    ],
    [
      /Save 52% on the 90-Day Supply — plus a \$62 Welcome Kit \(Pill Caddy, Shaker Bottle, Baseball Cap\) and free shipping\./g,
      `Get your ${NORMALIZED_OFFER.supply} for ${NORMALIZED_OFFER.entryPrice} at ${NORMALIZED_OFFER.savings} and receive a ${NORMALIZED_OFFER.welcomeKitValue}.`,
    ],
    [
      /Save 52% on the 90-Day Supply — plus a \$62 Welcome Kit and free shipping\./g,
      `Get your ${NORMALIZED_OFFER.supply} for ${NORMALIZED_OFFER.entryPrice} at ${NORMALIZED_OFFER.savings} and receive a ${NORMALIZED_OFFER.welcomeKitValue}.`,
    ],
    [
      /Save 52% on the 90-day supply\. Plus a 90-day empty-bottle guarantee\. No risk\. Just results or a full refund\./gi,
      `Get your ${NORMALIZED_OFFER.supply} for ${NORMALIZED_OFFER.entryPrice} at ${NORMALIZED_OFFER.savings}. Includes a ${NORMALIZED_OFFER.guarantee}. No risk. Just results or a full refund.`,
    ],
    [
      /SAVE 52% \+ FREE \$62 WELCOME KIT 🔥/g,
      "SAVE 52% + $35 WELCOME KIT VALUE",
    ],
    [
      /Get The Protocol — save 52% \+ free Welcome Kit \+ free shipping\./gi,
      `Get The Protocol — start your ${NORMALIZED_OFFER.supply} for ${NORMALIZED_OFFER.entryPrice} at ${NORMALIZED_OFFER.savings} and receive a ${NORMALIZED_OFFER.welcomeKitValue}.`,
    ],
  ];
  let normalized = text;
  for (const [pattern, replacement] of replacements) {
    normalized = normalized.replace(pattern, replacement);
  }
  return normalized
    .replace(/\$62 Welcome Kit/gi, "$35 Welcome Kit value")
    .replace(/free \$35 Welcome Kit value/gi, "$35 Welcome Kit value")
    .replace(/free Welcome Kit/gi, "$35 Welcome Kit value")
    .replace(/free gifts?/gi, "$35 Welcome Kit value")
    .replace(/\b50% off\b/gi, "52% off")
    .replace(/\b50% OFF\b/g, "52% OFF")
    .replace(/\b90-day empty-bottle guarantee\b/gi, "90-day guarantee")
    .replace(/\b90-Day Empty-Bottle Guarantee\b/g, "90-Day Guarantee")
    .replace(/\b90-day Higher-T Guarantee\b/gi, "90-day guarantee")
    .replace(/\b90-Day Higher-T Guarantee\b/g, "90-Day Guarantee")
    .replace(/\b90-Day Supply\b/g, "30-Day Supply")
    .replace(/\b90-day supply\b/gi, "30-day supply")
    .replace(/\b90-Day Launch Kit\b/g, "30-day supply")
    .replace(/\b90-Day Kit\b/g, "30-day supply")
    .replace(/\bfree shipping\b/gi, "")
    .replace(/[ \t]+\./g, ".")
    .replace(/,[ \t]+\./g, ".")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\n{3,}/g, "\n\n");
}

function uniqueCopyUnits(rows, launchSlot) {
  const seen = new Set();
  const units = [];
  for (const row of rows.filter((entry) => entry.launch_slot === launchSlot)) {
    if (seen.has(row.remix_copy_id)) continue;
    seen.add(row.remix_copy_id);
    units.push(copyUnitFromRow(row));
  }
  if (!units.length) throw new Error(`No copy units found for ${launchSlot}`);
  return units;
}

function congruenceBlockForUrl(destinationUrl) {
  const review = JSON.parse(readFileSync(REVIEW_PATH, "utf8"));
  const entry = review.destinationCongruenceMap.find((item) => item.destinationUrl === destinationUrl);
  if (!entry?.congruenceBlock) throw new Error(`Missing congruence block for ${destinationUrl} in ${REVIEW_PATH}`);
  if (!entry.congruenceBlock.startsWith("Awareness level: Problem-Aware")) {
    throw new Error(`Congruence block for ${destinationUrl} is not Problem-Aware.`);
  }
  return entry.congruenceBlock;
}

function validatePayload(payload) {
  if ("swipeHook" in payload) throw new Error("Generation payload must not include swipeHook.");
  if (!payload.swipeAngle.startsWith("Awareness level: Problem-Aware")) {
    throw new Error("Generation payload must be Problem-Aware.");
  }
  if (Boolean(payload.companySwipeId) === Boolean(payload.swipeImageUrl)) {
    throw new Error("Generation payload must provide exactly one of companySwipeId or swipeImageUrl.");
  }
  if (![RENDER_MODEL_ID, NANOBANANA_RENDER_MODEL_ID].includes(payload.renderModelId)) {
    throw new Error(`Unexpected render model: ${payload.renderModelId}`);
  }
}

function ctaEnumFor(copy) {
  if (copy.cta === "Get The Protocol") return "LEARN_MORE";
  if (copy.cta === "See Details") return "LEARN_MORE";
  throw new Error(`No approved Meta CTA mapping for ${copy.cta}`);
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
          angleName: "Tenor GLP + Quiz Problem-Aware Expansion",
          description:
            "Corrected problem-aware Meta campaign using grouped logical ads with Tenor package references plus the standard curated swipe collection.",
          evidence: [GLP_PRESALE_URL, QUIZ_PRESALE_URL, SALES_URL],
        },
      ],
    },
    offer: {
      ump: "Tenor GLP + Quiz external funnel campaign",
      ums: "Use destination-aligned copy, grouped aspect-ratio siblings, and problem-aware congruence for GLP and quiz presales.",
      corePromise: "Route GLP creatives to the GLP listicle and quiz creatives to the quiz funnel, with each logical ad shipping 1:1, 4:5, and 9:16 siblings before the supplied sales URL.",
      valueStackSummary:
        "Tenor package creatives keep their row copy. Curated swipes reuse only destination-matched copy from the non-curated Tenor package. Offer language is normalized to $44, 52% off, 30-day supply, 90-day guarantee, and a $35 Welcome Kit value.",
      guaranteeType: "90-day guarantee",
      pricingRationale: "Offer details are normalized in code to $44 entry pricing, 52% off, a 30-day supply, an allowed 90-day guarantee, and a $35 Welcome Kit value.",
      selectedVariantId: EXPERIMENT_ID,
      selectedVariantName: "Problem-Aware GLP + Quiz",
      offerDetailsMarkdown: [
        "# Supplied Destinations",
        "",
        `GLP listicle: ${GLP_PRESALE_URL}`,
        `Quiz: ${QUIZ_PRESALE_URL}`,
        `Sales: ${SALES_URL}`,
        "",
        "# Normalized Offer",
        "",
        `Entry price: ${NORMALIZED_OFFER.entryPrice}`,
        `Savings: ${NORMALIZED_OFFER.savings}`,
        `Supply: ${NORMALIZED_OFFER.supply}`,
        `Guarantee: ${NORMALIZED_OFFER.guarantee}`,
        `Welcome kit: ${NORMALIZED_OFFER.welcomeKitValue}`,
        "",
        "# Copy Routing",
        "",
        `GLP copy IDs: ${glpCopyIds.join(", ")}`,
        `Quiz copy IDs: ${quizCopyIds.join(", ")}`,
      ].join("\n"),
    },
    copyDocument: {
      headline: "Tenor Problem-Aware GLP + Quiz Campaign",
      promiseContract: {
        loopQuestion: "Can the corrected swipe inputs and curated set be launched as a MOS-managed Meta campaign?",
        specificPromise: "Each logical ad uses its destination congruence block, destination-matched copy assignment, and three sibling aspect-ratio variants.",
        deliveryTest: "MOS contains the campaign, creative context, asset briefs, grouped logical ads, generated sibling assets, Meta creative specs, CBO ad set specs, validation, and publish run.",
        minimumDelivery: "A paused Meta campaign with five U.S.-only CBO ad sets and all generated ads attached for review.",
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
        "Audience and product context are supplied by the Tenor campaign CSV rows and destination-level congruence blocks.",
      brandVoiceMarkdown:
        `Use Tenor naming and the supplied destination-matched copy. Generation payloads omit swipeHook. Offer language is normalized to the approved $44 / 52% off / 30-day supply framing. Use Tenor primary red ${TENOR_PRIMARY_RED_HEX} for brand accents and do not carry over orange accents from source references.`,
      complianceMarkdown:
        "Use the MOS validation flow and the destination-level Problem-Aware congruence blocks. Curated swipes do not receive Tenor product reference images.",
      mentalModelsMarkdown:
        "The campaign uses MOS external delivery with campaign-level sales URL and row-level creative destination URLs for GLP and quiz presales. Each logical ad group ships 1:1, 4:5, and 9:16 assets.",
      awarenessAngleMatrixMarkdown:
        "Both destinations are Problem-Aware. GLP creatives route to the GLP listicle and use GLP copy only. Quiz creatives route to the quiz funnel and use quiz copy only. Meta ad set targeting is U.S.-only.",
    },
    experimentSpecs: [
      {
        id: EXPERIMENT_ID,
        name: "Tenor GLP + Quiz Problem-Aware Expansion",
        hypothesis:
          "Problem-aware congruence, grouped aspect-ratio siblings, and destination-matched copy can support a combined Tenor package plus curated swipe campaign.",
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
        hook: "Destination congruence block",
        angle: "Use the supplied destination congruence block and selected swipe source.",
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
        creativeConcept: "Problem-aware swipe remixes routed to the GLP listicle presale.",
      },
      {
        ...common,
        id: QUIZ_BRIEF_ID,
        variantId: "quiz-funnel",
        variantName: "Quiz Funnel",
        destinationType: "pre-sales",
        destinationLabel: "Quiz presale",
        creativeConcept: "Problem-aware swipe remixes routed to the quiz presale.",
      },
    ],
    source: "tenor-glp-quiz-problem-aware-expansion",
    packageDir: PACKAGE_DIR,
  };
}

function seedAssetBriefViaSsh(campaignId) {
  const payloadPath = path.join(OUT_DIR, "asset-brief-payload.json");
  writeFileSync(payloadPath, JSON.stringify(assetBriefPayload(campaignId), null, 2) + "\n");
  const remotePayloadPath = `/root/tmp/tenor-problem-aware-asset-brief-${campaignId}.json`;
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
  const campaign = campaigns.find((item) => item.id === MOS_GENERATION_CAMPAIGN_ID);
  if (!campaign) {
    throw new Error(`Expected MOS generation campaign ${MOS_GENERATION_CAMPAIGN_ID} was not found for this client/product.`);
  }
  const campaignAction = "reused-valid-delivery-campaign";

  const campaignId = campaign.id;
  const creativeContext = await authed(`/campaigns/${encodeURIComponent(campaignId)}/creative-context/loaded`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(manualCreativeContextPayload(campaignId)),
  });
  const assetBriefSeed = seedAssetBriefViaSsh(campaignId);
  const delivery = await authed(`/campaigns/${encodeURIComponent(campaignId)}/delivery`);
  const deliveryValidation = {
    validationStatus: delivery.validationStatus,
    validationError: delivery.validationError,
    validatedAt: delivery.validatedAt,
    source: "existing-campaign-delivery-record",
  };
  if (deliveryValidation.validationStatus !== "valid") {
    throw new Error(`Existing MOS campaign delivery config is not valid: ${deliveryValidation.validationStatus} ${deliveryValidation.validationError || ""}`);
  }
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
    throw new Error(`Missing campaign state: ${STATE_PATH}. Run setup first.`);
  }
  return JSON.parse(readFileSync(STATE_PATH, "utf8"));
}

async function curatedSwipes() {
  const detail = await authed(`/swipes/collections/${CURATED_COLLECTION_ID}`);
  const swipes = detail.swipes || [];
  if (swipes.length !== 30) {
    throw new Error(`Expected 30 curated swipes in ${CURATED_COLLECTION_NAME}, found ${swipes.length}.`);
  }
  return swipes.map((swipe, index) => ({
    index: index + 1,
    companySwipeId: swipe.id,
    title: swipe.title || `curated-${index + 1}`,
    mediaUrl: (swipe.media || [])[0]?.download_url || (swipe.media || [])[0]?.url || null,
  }));
}

function sortedGroups(groups) {
  const sourceOrder = { tenor_package: 0, standard_curated: 1 };
  const destinationOrder = { glp: 0, quiz: 1 };
  return [...groups].sort((a, b) => {
    const sourceDiff = (sourceOrder[a.sourceType] ?? 9) - (sourceOrder[b.sourceType] ?? 9);
    if (sourceDiff) return sourceDiff;
    const destinationDiff = (destinationOrder[a.destinationKey] ?? 9) - (destinationOrder[b.destinationKey] ?? 9);
    if (destinationDiff) return destinationDiff;
    return a.sortIndex - b.sortIndex;
  });
}

function sortedEntries(entries) {
  const sourceOrder = { tenor_package: 0, standard_curated: 1 };
  const destinationOrder = { glp: 0, quiz: 1 };
  return [...entries].sort((a, b) => {
    const sourceDiff = (sourceOrder[a.sourceType] ?? 9) - (sourceOrder[b.sourceType] ?? 9);
    if (sourceDiff) return sourceDiff;
    const destinationDiff = (destinationOrder[a.destinationKey] ?? 9) - (destinationOrder[b.destinationKey] ?? 9);
    if (destinationDiff) return destinationDiff;
    const sortDiff = a.sortIndex - b.sortIndex;
    if (sortDiff) return sortDiff;
    const aspectDiff = (GROUP_ASPECT_RATIO_ORDER.get(a.aspectRatio) ?? 9) - (GROUP_ASPECT_RATIO_ORDER.get(b.aspectRatio) ?? 9);
    if (aspectDiff) return aspectDiff;
    return String(a.key).localeCompare(String(b.key));
  });
}

function groupEntriesByGroupKey(entries) {
  const map = new Map();
  for (const entry of entries || []) {
    const rows = map.get(entry.groupKey) || [];
    rows.push(entry);
    map.set(entry.groupKey, rows);
  }
  for (const rows of map.values()) {
    rows.sort(
      (a, b) => (GROUP_ASPECT_RATIO_ORDER.get(a.aspectRatio) ?? 9) - (GROUP_ASPECT_RATIO_ORDER.get(b.aspectRatio) ?? 9),
    );
  }
  return map;
}

function bundleForGroup(manifest, group, groupedEntries = null) {
  const grouped = groupedEntries || groupEntriesByGroupKey(manifest.entries);
  const variants = grouped.get(group.key) || [];
  if (variants.length !== GROUP_ASPECT_RATIOS.length) {
    throw new Error(`Expected ${GROUP_ASPECT_RATIOS.length} variants for ${group.key}, found ${variants.length}.`);
  }
  const primaryEntry = variants.find((entry) => entry.key === group.primaryEntryKey) || variants.find((entry) => entry.isPrimaryAsset);
  if (!primaryEntry) {
    throw new Error(`Group ${group.key} is missing a primary asset entry.`);
  }
  return {
    group,
    variants,
    primaryEntry,
    siblingEntries: variants.filter((entry) => entry.key !== primaryEntry.key),
  };
}

function buildBasePayload({ state, entry, congruenceBlock }) {
  const isCurated = entry.sourceType === "standard_curated";
  const swipeAngleParts = [congruenceBlock, BRAND_COLOR_POLICY];
  if (isCurated) swipeAngleParts.push(CURATED_NO_PRODUCT_REVEAL_POLICY);
  const payload = {
      clientId: CLIENT_ID,
      productId: PRODUCT_ID,
      campaignId: state.campaignId,
      assetBriefId: assetBriefIdForDestinationKey(entry.destinationKey),
      requirementIndex: 0,
      swipeRequiresProductImage: entry.productReferenceRequired,
      swipeContextMode: "minimal",
      swipeBrandName: "Tenor",
      swipeProductName: isCurated ? "Daily Drive Essentials (not pictured)" : "Daily Drive Essentials",
      swipeAngle: swipeAngleParts.join("\n\n"),
      model: STAGE_ONE_MODEL,
      renderModelId: RENDER_MODEL_ID,
      aspectRatio: entry.aspectRatio,
      count: 1,
    };
  if (entry.sourceType === "standard_curated") payload.companySwipeId = entry.companySwipeId;
  return payload;
}

async function buildManifest() {
  ensureDirs();
  const state = readState();
  const rows = readRows();
  const curated = await curatedSwipes();
  const glpCopyUnits = uniqueCopyUnits(rows, "GLP lander");
  const quizCopyUnits = uniqueCopyUnits(rows, "Quiz funnel");
  const congruenceBlocks = {
    glp: congruenceBlockForUrl(GLP_PRESALE_URL),
    quiz: congruenceBlockForUrl(QUIZ_PRESALE_URL),
  };
  const groups = [];
  const entries = [];

  for (const row of rows) {
    const destinationKey = destinationKeyForLaunchSlot(row.launch_slot);
    const sourcePath = row.sourcePath;
    const nativeAspectRatio = aspectRatioFor(sourcePath);
    const group = {
      key: `tenor-${String(row.rowIndex).padStart(2, "0")}-${row.creative_id}-${destinationKey}`,
      rowKey: row.rowKey,
      rowIndex: row.rowIndex,
      sortIndex: row.rowIndex,
      sourceType: "tenor_package",
      destinationKey,
      launchSlot: row.launch_slot,
      destinationUrl: destinationUrlForLaunchSlot(row.launch_slot),
      sourceCopyId: row.source_copy_id,
      remixCopyId: row.remix_copy_id,
      sourceCreativeId: row.creative_id,
      creativeFile: row.creative_file,
      creativeReferenceTitle: row.creative_reference_title,
      sourcePath,
      sourceTitle: row.creative_reference_title,
      productReferencePolicy: "dynamic_by_tenor_reference",
      productReferenceRequired: TENOR_PRODUCT_REFERENCE_CREATIVE_IDS.has(row.creative_id),
      nativeAspectRatio,
      primaryAspectRatio: primaryAspectRatioFor(nativeAspectRatio),
      variantAspectRatios: GROUP_ASPECT_RATIOS,
      adCopy: copyUnitFromRow(row),
    };
    const bytes = readFileSync(sourcePath);
    group.sourceCreativeSha256 = sha256(bytes);
    groups.push(group);
  }

  for (const [destinationKey, copyUnits, launchSlot, destinationUrl] of [
    ["glp", glpCopyUnits, "GLP lander", GLP_PRESALE_URL],
    ["quiz", quizCopyUnits, "Quiz funnel", QUIZ_PRESALE_URL],
  ]) {
    curated.forEach((swipe, index) => {
      const copy = copyUnits[index % copyUnits.length];
      groups.push({
        key: `curated-${String(index + 1).padStart(2, "0")}-${destinationKey}`,
        rowKey: `CURATED-${String(index + 1).padStart(2, "0")}-${destinationKey.toUpperCase()}`,
        rowIndex: rows.length + (destinationKey === "glp" ? index + 1 : curated.length + index + 1),
        sortIndex: index + 1,
        sourceType: "standard_curated",
        destinationKey,
        launchSlot,
        destinationUrl,
        companySwipeId: swipe.companySwipeId,
        sourceTitle: swipe.title,
        sourceMediaUrl: swipe.mediaUrl,
        productReferencePolicy: "never_for_curated",
        productReferenceRequired: false,
        nativeAspectRatio: "1:1",
        primaryAspectRatio: "1:1",
        variantAspectRatios: GROUP_ASPECT_RATIOS,
        adCopy: { ...copy, destinationUrl },
      });
    });
  }

  for (const group of groups) {
    let sourceAttachment = null;
    if (group.sourceType === "tenor_package") {
      sourceAttachment = await uploadSourceFile(group.sourcePath);
    }
    for (const aspectRatio of GROUP_ASPECT_RATIOS) {
      const entry = {
        ...group,
        key: `${group.key}-${aspectRatioKey(aspectRatio)}`,
        groupKey: group.key,
        aspectRatio,
        isPrimaryAsset: aspectRatio === group.primaryAspectRatio,
      };
      const payload = buildBasePayload({ state, entry, congruenceBlock: congruenceBlocks[entry.destinationKey] });
      if (entry.sourceType === "tenor_package") {
        entry.sourceAttachment = sourceAttachment;
        payload.swipeImageUrl = sourceAttachment.publicUrl;
      }
      validatePayload(payload);
      entry.payload = payload;
      entries.push(entry);
      if (entry.isPrimaryAsset) {
        group.primaryEntryKey = entry.key;
      }
    }
  }

  const orderedGroups = sortedGroups(groups);
  const orderedEntries = sortedEntries(entries);
  const manifest = {
    createdAt: new Date().toISOString(),
    note: `Full problem-aware generation. Logical ads are grouped by concept, each with 1:1, 4:5, and 9:16 siblings. Curated rows reuse destination-matched non-curated Tenor copy. Generation payloads omit swipeHook. All generated ads must use Tenor primary red ${TENOR_PRIMARY_RED_HEX} instead of inheriting orange source accents. Curated rows include the user-approved no-product-reveal policy.`,
    campaignId: state.campaignId,
    campaignName: CAMPAIGN_NAME,
    metaCampaignName: META_CAMPAIGN_NAME,
    batchId: BATCH_ID,
    generationKey: GENERATION_KEY,
    stageOneModel: STAGE_ONE_MODEL,
    renderModelId: RENDER_MODEL_ID,
    groupedCreativePlan: {
      logicalAds: "One Meta creative spec per logical ad group.",
      rawGeneratedAssets: "Each logical ad group generates three sibling assets at 1:1, 4:5, and 9:16.",
      aspectRatios: GROUP_ASPECT_RATIOS,
      primaryAssetSelection:
        "Tenor groups keep the current source aspect ratio as primary when it is one of the grouped ratios. Curated groups default to 1:1 as primary.",
    },
    targetPublishPlan: {
      geography: "US only",
      targeting: {
        geo_locations: {
          countries: ["US"],
          location_types: ["home", "recent"],
        },
      },
    },
    destinations: {
      glp: {
        label: "GLP listicle",
        presaleUrl: GLP_PRESALE_URL,
        salesUrl: SALES_URL,
        congruenceBlock: congruenceBlocks.glp,
      },
      quiz: {
        label: "Quiz funnel",
        presaleUrl: QUIZ_PRESALE_URL,
        salesUrl: SALES_URL,
        congruenceBlock: congruenceBlocks.quiz,
      },
    },
    sourceCollections: {
      standardCurated: {
        collectionId: CURATED_COLLECTION_ID,
        collectionName: CURATED_COLLECTION_NAME,
        productRevealPolicy: CURATED_NO_PRODUCT_REVEAL_POLICY,
      },
    },
    copyAssignmentPlan: {
      tenorPackage: "Each Tenor package row uses its own CSV copy and destination.",
      curatedGlp: "Round-robin across unique GLP copy units only.",
      curatedQuiz: "Round-robin across unique quiz copy units only.",
      glpCopyUnitOrder: glpCopyUnits.map((unit) => unit.remixCopyId),
      quizCopyUnitOrder: quizCopyUnits.map((unit) => unit.remixCopyId),
    },
    expectedCounts: {
      logicalAds: {
        total: 83,
        tenorPackage: 23,
        curatedGlp: 30,
        curatedQuiz: 30,
        glpTotal: 43,
        quizTotal: 40,
      },
      rawAssets: {
        total: 249,
        tenorPackage: 69,
        curatedGlp: 90,
        curatedQuiz: 90,
        glpTotal: 129,
        quizTotal: 120,
        byAspectRatio: Object.fromEntries(GROUP_ASPECT_RATIOS.map((aspectRatio) => [aspectRatio, 83])),
      },
    },
    groups: orderedGroups,
    entries: orderedEntries,
  };
  validateManifest(manifest, { requireResults: false });
  writeFileSync(MANIFEST_PATH, JSON.stringify(manifest, null, 2) + "\n");
  return manifest;
}

function validateManifest(manifest, { requireResults }) {
  if (!Array.isArray(manifest.groups) || !Array.isArray(manifest.entries)) {
    throw new Error(`Manifest must include grouped logical ads and raw entries. Rebuild ${MANIFEST_PATH} with the grouped manifest command.`);
  }
  if (manifest.groups.length !== 83) {
    throw new Error(`Expected 83 logical ad groups, found ${manifest.groups.length}.`);
  }
  if (manifest.entries.length !== 249) {
    throw new Error(`Expected 249 raw asset entries, found ${manifest.entries.length}.`);
  }
  const groupKeys = manifest.groups.map((group) => group.key);
  if (new Set(groupKeys).size !== groupKeys.length) {
    throw new Error("Manifest logical group keys must be unique.");
  }
  const entryKeys = manifest.entries.map((entry) => entry.key);
  if (new Set(entryKeys).size !== entryKeys.length) {
    throw new Error("Manifest raw asset entry keys must be unique.");
  }
  const groupCounts = {
    glp: manifest.groups.filter((group) => group.destinationKey === "glp").length,
    quiz: manifest.groups.filter((group) => group.destinationKey === "quiz").length,
    tenor: manifest.groups.filter((group) => group.sourceType === "tenor_package").length,
    curated: manifest.groups.filter((group) => group.sourceType === "standard_curated").length,
  };
  if (groupCounts.glp !== 43 || groupCounts.quiz !== 40 || groupCounts.tenor !== 23 || groupCounts.curated !== 60) {
    throw new Error(`Unexpected logical group counts: ${JSON.stringify(groupCounts)}`);
  }
  const entryCounts = {
    glp: manifest.entries.filter((entry) => entry.destinationKey === "glp").length,
    quiz: manifest.entries.filter((entry) => entry.destinationKey === "quiz").length,
    tenor: manifest.entries.filter((entry) => entry.sourceType === "tenor_package").length,
    curated: manifest.entries.filter((entry) => entry.sourceType === "standard_curated").length,
    byAspectRatio: Object.fromEntries(
      GROUP_ASPECT_RATIOS.map((aspectRatio) => [
        aspectRatio,
        manifest.entries.filter((entry) => entry.aspectRatio === aspectRatio).length,
      ]),
    ),
  };
  if (entryCounts.glp !== 129 || entryCounts.quiz !== 120 || entryCounts.tenor !== 69 || entryCounts.curated !== 180) {
    throw new Error(`Unexpected raw asset counts: ${JSON.stringify(entryCounts)}`);
  }
  for (const [aspectRatio, count] of Object.entries(entryCounts.byAspectRatio)) {
    if (count !== 83) throw new Error(`Expected 83 assets at ${aspectRatio}, found ${count}.`);
  }
  const groupedEntries = groupEntriesByGroupKey(manifest.entries);
  for (const group of manifest.groups) {
    const variants = groupedEntries.get(group.key) || [];
    if (variants.length !== GROUP_ASPECT_RATIOS.length) {
      throw new Error(`Group ${group.key} must contain ${GROUP_ASPECT_RATIOS.length} aspect-ratio variants.`);
    }
    const variantAspectRatios = variants.map((entry) => entry.aspectRatio);
    if (JSON.stringify(variantAspectRatios) !== JSON.stringify(GROUP_ASPECT_RATIOS)) {
      throw new Error(`Group ${group.key} has unexpected aspect ratios: ${variantAspectRatios.join(", ")}`);
    }
    const primaryEntries = variants.filter((entry) => entry.isPrimaryAsset);
    if (primaryEntries.length !== 1) {
      throw new Error(`Group ${group.key} must have exactly one primary asset.`);
    }
    if (primaryEntries[0].aspectRatio !== group.primaryAspectRatio) {
      throw new Error(`Group ${group.key} primary asset ratio mismatch: ${primaryEntries[0].aspectRatio} !== ${group.primaryAspectRatio}`);
    }
    if (primaryEntries[0].key !== group.primaryEntryKey) {
      throw new Error(`Group ${group.key} primary entry mismatch: ${primaryEntries[0].key} !== ${group.primaryEntryKey}`);
    }
  }
  for (const entry of manifest.entries) {
    validatePayload(entry.payload);
    if (entry.sourceType === "standard_curated" && entry.productReferenceRequired !== false) {
      throw new Error(`Curated entry ${entry.key} must not request a product reference.`);
    }
    if (!GROUP_ASPECT_RATIO_ORDER.has(entry.aspectRatio)) {
      throw new Error(`Entry ${entry.key} uses unsupported grouped aspect ratio ${entry.aspectRatio}.`);
    }
    if (!entry.groupKey) {
      throw new Error(`Entry ${entry.key} is missing its logical group key.`);
    }
    if (entry.destinationKey === "glp" && entry.adCopy.destinationUrl !== GLP_PRESALE_URL) {
      throw new Error(`GLP entry ${entry.key} has non-GLP copy destination: ${entry.adCopy.destinationUrl}`);
    }
    if (entry.destinationKey === "quiz" && entry.adCopy.destinationUrl !== QUIZ_PRESALE_URL) {
      throw new Error(`Quiz entry ${entry.key} has non-quiz copy destination: ${entry.adCopy.destinationUrl}`);
    }
    if (requireResults && !entry.result?.assetId) {
      throw new Error(`Entry ${entry.key} is missing generated result.`);
    }
  }
  if (JSON.stringify(manifest.targetPublishPlan?.targeting?.geo_locations?.countries || []) !== JSON.stringify(["US"])) {
    throw new Error("Manifest target publish plan is not U.S.-only.");
  }
  return {
    logicalGroups: groupCounts,
    rawAssets: entryCounts,
  };
}

async function generateOneEntry(manifest, entry, renderModelId = RENDER_MODEL_ID) {
  const payload = { ...entry.payload, renderModelId };
  validatePayload(payload);
  const started = await authed("/swipes/generate-image-ad", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const detail = await waitForWorkflow(started.workflow_run_id);
  const workflowPath = path.join(OUT_DIR, `workflow-${entry.key}.json`);
  writeFileSync(workflowPath, JSON.stringify(detail, null, 2) + "\n");
  const { assetId, payloadOut } = extractAssetId(detail);
  const asset = await resolveAsset(manifest.campaignId, assetId);
  const extension = (asset.content_type || "image/png").includes("jpeg") ? "jpg" : "png";
  const localPath = path.join(GENERATED_DIR, `${entry.key}.${extension}`);
  downloadPublicAsset(asset.public_id, localPath);
  return {
    payload,
    workflow: {
      workflowRunId: started.workflow_run_id,
      temporalWorkflowId: started.temporal_workflow_id,
      workflowUrl: `https://moshq.app/workflows/${started.workflow_run_id}`,
      workflowDetailPath: workflowPath,
      payloadOut,
    },
    result: {
      assetId,
      publicId: asset.public_id,
      publicUrl: `${API_BASE}/public/assets/${asset.public_id}`,
      contentType: asset.content_type,
      width: asset.width,
      height: asset.height,
      localPath,
      remoteJobId: payloadOut?.job_id || null,
      renderProvider: payloadOut?.swipe_render_provider || null,
      renderModelIdRequested: payload.renderModelId,
      renderModelIdUsed: payloadOut?.swipe_render_model_id || payload.renderModelId,
      usedAuthorizedFallback: renderModelId !== RENDER_MODEL_ID,
      expectedRenderer: expectedRendererFor(renderModelId),
      productReferenceRequired: Boolean(payload.swipeRequiresProductImage),
      productReferenceAttached: Boolean(payloadOut?.product_reference_attached),
      productReferenceRenderAssetIds: payloadOut?.product_reference_render_asset_ids || [],
      productReferenceImageUrlsSelected: payloadOut?.product_reference_image_urls_selected || [],
    },
  };
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

function persistManifest(manifest) {
  writeFileSync(MANIFEST_PATH, JSON.stringify({ ...manifest, updatedAt: new Date().toISOString() }, null, 2) + "\n");
}

function isModerationError(error) {
  const text = `${error?.message || ""}\n${error?.body || ""}`;
  return /moderation|safety|blocked|policy/i.test(text);
}

function canUseAuthorizedNanoFallback(entry, error) {
  if (isModerationError(error)) return true;
  if (
    VERIFIED_OPENAI_MODERATION_FALLBACK_KEYS.has(entry.groupKey || entry.key)
    && /ended with failed: no error detail/i.test(error?.message || "")
  ) {
    return true;
  }
  return false;
}

function manifestNeedsRebuild(manifest) {
  if (!manifest || manifest.generationKey !== GENERATION_KEY) return true;
  if (!Array.isArray(manifest.groups) || !Array.isArray(manifest.entries)) return true;
  return false;
}

async function generateAll() {
  let manifest;
  if (existsSync(MANIFEST_PATH)) {
    manifest = JSON.parse(readFileSync(MANIFEST_PATH, "utf8"));
  }
  if (!manifest || manifestNeedsRebuild(manifest)) {
    manifest = await buildManifest();
  }
  validateManifest(manifest, { requireResults: false });

  const pending = manifest.entries.filter((entry) => !entry.result?.assetId);
  let nextIndex = 0;
  const failures = [];
  let stopped = false;
  async function worker(workerIndex) {
    while (!stopped) {
      const entry = pending[nextIndex];
      nextIndex += 1;
      if (!entry) return;
      if (entry.result?.assetId) {
        console.log(`Skipping ${entry.key}; already generated ${entry.result.assetId}`);
        continue;
      }
      try {
        console.log(`Generating ${entry.key} on worker ${workerIndex} (${entry.payload.aspectRatio})`);
        if (FORCE_NANOBANANA_FALLBACK_FOR_PENDING) {
          entry.primaryOpenAiFailure = {
            message: "OpenAI renderer unavailable for remaining pending rows: billing_hard_limit_reached observed in MOS worker logs after GPT Image 2 generation started.",
            body: null,
          };
          const generated = await generateOneEntry(manifest, entry, NANOBANANA_RENDER_MODEL_ID);
          generated.workflow.primaryOpenAiFailure = entry.primaryOpenAiFailure;
          Object.assign(entry, generated);
        } else {
          try {
            const generated = await generateOneEntry(manifest, entry, RENDER_MODEL_ID);
            Object.assign(entry, generated);
          } catch (error) {
            if (!canUseAuthorizedNanoFallback(entry, error)) throw error;
            console.log(`OpenAI failure for ${entry.key}; retrying with authorized NanoBanana fallback.`);
            entry.primaryOpenAiFailure = { message: error?.message || String(error), body: error?.body || null };
            const generated = await generateOneEntry(manifest, entry, NANOBANANA_RENDER_MODEL_ID);
            generated.workflow.primaryOpenAiFailure = entry.primaryOpenAiFailure;
            Object.assign(entry, generated);
          }
        }
        persistManifest(manifest);
        console.log(`Completed ${entry.key} on worker ${workerIndex}.`);
      } catch (error) {
        failures.push({ key: entry.key, error });
        console.error(`Generation failed for ${entry.key}: ${error?.message || String(error)}`);
        if (!CONTINUE_ON_FAILURE) stopped = true;
      }
    }
  }
  await Promise.all(Array.from({ length: GENERATE_CONCURRENCY }, (_, index) => worker(index + 1)));
  if (failures.length) {
    const summary = failures
      .map((failure) => `${failure.key}: ${failure.error?.message || String(failure.error)}`)
      .join("; ");
    throw new Error(`Generation failed for ${failures.length} asset variant(s): ${summary}`);
  }
  validateManifest(manifest, { requireResults: true });
  persistManifest(manifest);
  console.log(JSON.stringify({
    manifestPath: MANIFEST_PATH,
    campaignId: manifest.campaignId,
    logicalGroupCount: manifest.groups.length,
    rawAssetCount: manifest.entries.length,
    concurrency: GENERATE_CONCURRENCY,
  }, null, 2));
}

function requireFullManifest() {
  if (!existsSync(MANIFEST_PATH)) throw new Error(`Missing manifest: ${MANIFEST_PATH}`);
  const manifest = JSON.parse(readFileSync(MANIFEST_PATH, "utf8"));
  if (manifestNeedsRebuild(manifest)) {
    throw new Error(`Manifest at ${MANIFEST_PATH} is stale for generationKey ${GENERATION_KEY}. Rebuild it with the manifest command first.`);
  }
  validateManifest(manifest, { requireResults: true });
  return manifest;
}

function stampBatchViaSsh(manifest) {
  const payloadPath = path.join(OUT_DIR, "batch-stamp-input.json");
  const groupsByKey = new Map(manifest.groups.map((group) => [group.key, group]));
  const assetRows = manifest.entries.map((entry) => ({
    groupKey: entry.groupKey,
    primaryEntryKey: groupsByKey.get(entry.groupKey)?.primaryEntryKey || null,
    primaryAspectRatio: groupsByKey.get(entry.groupKey)?.primaryAspectRatio || null,
    variantAspectRatio: entry.aspectRatio,
    isPrimaryAsset: Boolean(entry.isPrimaryAsset),
    assetId: entry.result.assetId,
    rowKey: entry.rowKey,
    rowIndex: entry.rowIndex,
    sourceType: entry.sourceType,
    launchSlot: entry.launchSlot,
    destinationKey: entry.destinationKey,
    destinationUrl: entry.destinationUrl,
    sourceCopyId: entry.adCopy.sourceCopyId,
    remixCopyId: entry.adCopy.remixCopyId,
    sourceCreativeId: entry.sourceCreativeId || null,
    companySwipeId: entry.companySwipeId || null,
    sourceTitle: entry.sourceTitle,
    headline: entry.adCopy.title,
  }));
  writeFileSync(payloadPath, JSON.stringify({ campaignId: manifest.campaignId, batchId: BATCH_ID, assetRows }, null, 2) + "\n");
  const remotePayloadPath = `/root/tmp/tenor-problem-aware-batch-stamp-${manifest.campaignId}.json`;
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
        metadata["creativeGroupKey"] = row["groupKey"]
        metadata["creativePrimaryEntryKey"] = row["primaryEntryKey"]
        metadata["creativePrimaryAspectRatio"] = row["primaryAspectRatio"]
        metadata["creativeVariantAspectRatio"] = row["variantAspectRatio"]
        metadata["creativeIsPrimaryAsset"] = row["isPrimaryAsset"]
        metadata["campaignPackageRowKey"] = row["rowKey"]
        metadata["campaignPackageRowIndex"] = row["rowIndex"]
        metadata["sourceType"] = row["sourceType"]
        metadata["launchSlot"] = row["launchSlot"]
        metadata["destinationKey"] = row["destinationKey"]
        metadata["sourceCopyId"] = row["sourceCopyId"]
        metadata["remixCopyId"] = row["remixCopyId"]
        metadata["creativeId"] = row["sourceCreativeId"]
        metadata["companySwipeId"] = row["companySwipeId"]
        metadata["sourceTitle"] = row["sourceTitle"]
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
  let assetIds = [];
  if (existsSync(MANIFEST_PATH)) {
    try {
      const manifest = JSON.parse(readFileSync(MANIFEST_PATH, "utf8"));
      assetIds = (manifest.entries || [])
        .map((entry) => entry?.result?.assetId)
        .filter((assetId) => typeof assetId === "string" && assetId.trim());
    } catch {
      assetIds = [];
    }
  }
  const py = String.raw`
import json
from sqlalchemy import select
from app.db.base import session_scope
from app.db.models import Asset

campaign_id = "${campaignId}"
product_id = "${PRODUCT_ID}"
asset_ids = ${JSON.stringify(assetIds)}

with session_scope() as session:
    stmt = (
        select(Asset)
        .where(
            Asset.campaign_id == campaign_id,
            Asset.product_id == product_id,
            Asset.asset_kind == "image",
        )
        .order_by(Asset.created_at.desc())
    )
    if asset_ids:
        stmt = stmt.where(Asset.id.in_(asset_ids))
    assets = session.scalars(stmt).all()
    print(json.dumps([
        {
            "id": str(asset.id),
            "public_id": str(asset.public_id),
            "content_type": asset.content_type,
            "width": asset.width,
            "height": asset.height,
            "ai_metadata": asset.ai_metadata or {},
        }
        for asset in assets
    ]))
`;
  const result = execFileSync("ssh", [
    "-i",
    path.join(os.homedir(), ".ssh/hetzner_prod"),
    "-o",
    "BatchMode=yes",
    "root@api.moshq.app",
    "cd /opt/apps/mos-api/mos/backend && set -a && . /etc/cloudhand/env/mos-api.env && set +a && .venv/bin/python -",
  ], { input: py, encoding: "utf8", maxBuffer: 20 * 1024 * 1024 });
  return JSON.parse(result.trim().split(/\r?\n/).at(-1));
}

async function stampBatch() {
  await getBackendToken();
  const manifest = requireFullManifest();
  const stamp = stampBatchViaSsh(manifest);
  const assets = await getCampaignAssets(manifest.campaignId);
  const byId = new Map(assets.map((asset) => [asset.id, asset]));
  const mismatched = manifest.entries
    .map((entry) => byId.get(entry.result.assetId))
    .filter((asset) => asset?.ai_metadata?.creativeGenerationBatchId !== BATCH_ID)
    .map((asset) => asset?.id || "missing");
  if (mismatched.length) {
    throw new Error(`Batch stamp verification failed for assets: ${mismatched.join(", ")}`);
  }
  manifest.batchStamp = stamp;
  persistManifest(manifest);
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

function creativeSpecGroupKey(spec) {
  const metadata = specMetadata(spec);
  return metadata.groupKey || metadata.multiAspectSpec?.groupKey || metadata.rowKey || null;
}

async function getCreativeSpecs(campaignId) {
  return authed(`/meta/specs/creatives?campaignId=${encodeURIComponent(campaignId)}`);
}

async function getAdSetSpecs(campaignId) {
  return authed(`/meta/specs/adsets?campaignId=${encodeURIComponent(campaignId)}`);
}

async function upsertCreativeSpec(campaignId, group, bundle, existingLookups) {
  const { primaryEntry, siblingEntries, variants } = bundle;
  const assetId = primaryEntry.result.assetId;
  const copy = group.adCopy;
  const groupedAdMetadata = {
    groupKey: group.key,
    primaryAsset: {
      assetId,
      entryKey: primaryEntry.key,
      aspectRatio: primaryEntry.aspectRatio,
      publicUrl: primaryEntry.result.publicUrl,
    },
    siblingVariantAssetIds: siblingEntries.map((entry) => entry.result.assetId),
    aspectRatios: variants.map((entry) => entry.aspectRatio),
    variantsByAspectRatio: Object.fromEntries(
      variants.map((entry) => [
        entry.aspectRatio,
        {
          assetId: entry.result.assetId,
          entryKey: entry.key,
          publicUrl: entry.result.publicUrl,
          isPrimaryAsset: Boolean(entry.isPrimaryAsset),
        },
      ]),
    ),
  };
  const body = {
    campaignId,
    name: `ProblemAware ${group.destinationKey.toUpperCase()} ${group.key} - ${copy.title}`.slice(0, 240),
    primaryText: copy.body,
    headline: copy.title,
    description: copy.linkDescription,
    callToActionType: ctaEnumFor(copy),
    destinationUrl: copy.destinationUrl,
    status: "draft",
    metadata: {
      source: "tenor_glp_quiz_problem_aware_expansion",
      packageDir: PACKAGE_DIR,
      sourceCsv: path.join(PACKAGE_DIR, "glp-quiz-campaign-ready-expanded.csv"),
      batchId: BATCH_ID,
      generationKey: GENERATION_KEY,
      rowKey: group.rowKey,
      rowIndex: group.rowIndex,
      groupKey: group.key,
      sourceType: group.sourceType,
      destinationKey: group.destinationKey,
      launchSlot: group.launchSlot,
      sourceCopyId: copy.sourceCopyId,
      remixCopyId: copy.remixCopyId,
      sourceCreativeId: group.sourceCreativeId || null,
      companySwipeId: group.companySwipeId || null,
      sourceTitle: group.sourceTitle,
      sourceMediaUrl: group.sourceMediaUrl || null,
      ctaMapping: { source: copy.cta, metaEnum: ctaEnumFor(copy) },
      presaleUrl: copy.destinationUrl,
      salesUrl: SALES_URL,
      generatedAssetPublicUrl: primaryEntry.result.publicUrl,
      workflowRunId: primaryEntry.workflow.workflowRunId,
      workflowUrl: primaryEntry.workflow.workflowUrl,
      remoteJobId: primaryEntry.result.remoteJobId,
      multiAspectSpec: {
        groupKey: group.key,
        primaryAssetId: assetId,
        variants: variants.map((entry) => ({
          assetId: entry.result.assetId,
          aspectRatio: entry.aspectRatio,
        })),
      },
      groupedAd: groupedAdMetadata,
      renderer: {
        stageOneModel: STAGE_ONE_MODEL,
        renderModelIdRequested: primaryEntry.result.renderModelIdRequested || primaryEntry.payload.renderModelId,
        renderModelIdUsed: primaryEntry.result.renderModelIdUsed || primaryEntry.payload.renderModelId,
        renderProvider: primaryEntry.result.renderProvider || null,
        usedAuthorizedFallback: Boolean(primaryEntry.result.usedAuthorizedFallback),
      },
      productReference: {
        required: Boolean(primaryEntry.result.productReferenceRequired || primaryEntry.payload.swipeRequiresProductImage),
        attached: Boolean(primaryEntry.result.productReferenceAttached),
        renderAssetIds: primaryEntry.result.productReferenceRenderAssetIds || [],
        imageUrlsSelected: primaryEntry.result.productReferenceImageUrlsSelected || [],
      },
      primaryOpenAiFailure: primaryEntry.workflow.primaryOpenAiFailure || null,
      variantRenders: variants.map((entry) => ({
        assetId: entry.result.assetId,
        entryKey: entry.key,
        aspectRatio: entry.aspectRatio,
        renderModelIdRequested: entry.result.renderModelIdRequested || entry.payload.renderModelId,
        renderModelIdUsed: entry.result.renderModelIdUsed || entry.payload.renderModelId,
        renderProvider: entry.result.renderProvider || null,
        usedAuthorizedFallback: Boolean(entry.result.usedAuthorizedFallback),
      })),
    },
  };
  const existing = existingLookups.byAssetId.get(assetId) || existingLookups.byGroupKey.get(group.key) || existingLookups.byGroupKey.get(group.rowKey);
  if (!existing) {
    const created = await authed("/meta/specs/creatives", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assetId, ...body }),
    });
    return {
      action: "created",
      groupKey: group.key,
      primaryAssetId: assetId,
      siblingVariantAssetIds: groupedAdMetadata.siblingVariantAssetIds,
      creativeSpecId: created.id,
    };
  }
  const updated = await authed(`/meta/specs/creatives/${encodeURIComponent(existing.id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ assetId, ...body }),
  });
  return {
    action: "updated",
    groupKey: group.key,
    primaryAssetId: assetId,
    siblingVariantAssetIds: groupedAdMetadata.siblingVariantAssetIds,
    creativeSpecId: updated.id || existing.id,
  };
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
      countries: ["US"],
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
    if (metadata.templateId !== "default-broad-us-cbo" || bucketCount !== 5 || bucketIndex < 1 || bucketIndex > 5) {
      continue;
    }
    if (byBucket.has(bucketIndex)) {
      throw new Error(`Duplicate default-broad-us-cbo ad set spec for bucket ${bucketIndex}`);
    }
    byBucket.set(bucketIndex, spec);
  }
  const results = [];
  for (let bucketIndex = 1; bucketIndex <= 5; bucketIndex += 1) {
    const body = {
      campaignId,
      name: `CBO US Bucket ${bucketIndex}`,
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
        source: "tenor_glp_quiz_problem_aware_expansion",
        templateId: "default-broad-us-cbo",
        campaignDailyBudget: 10000,
        countryScope: "US",
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
  const manifest = requireFullManifest();
  const assets = await getCampaignAssets(manifest.campaignId);
  const byId = new Map(assets.map((asset) => [asset.id, asset]));
  const missingBatch = manifest.entries
    .map((entry) => byId.get(entry.result.assetId))
    .filter((asset) => asset?.ai_metadata?.creativeGenerationBatchId !== BATCH_ID)
    .map((asset) => asset?.id || "missing");
  if (missingBatch.length) {
    throw new Error(`Run stamp-batch before create-specs. Missing batch on: ${missingBatch.join(", ")}`);
  }
  const creativeSpecs = await getCreativeSpecs(manifest.campaignId);
  const creativeByAssetId = new Map();
  const creativeByGroupKey = new Map();
  for (const spec of creativeSpecs || []) {
    const assetId = specAssetId(spec);
    if (assetId) creativeByAssetId.set(assetId, spec);
    const groupKey = creativeSpecGroupKey(spec);
    if (!groupKey) continue;
    if (creativeByGroupKey.has(groupKey)) {
      throw new Error(`Duplicate creative spec for logical group ${groupKey}`);
    }
    creativeByGroupKey.set(groupKey, spec);
  }
  const groupedEntries = groupEntriesByGroupKey(manifest.entries);
  const creativeResults = [];
  for (const group of manifest.groups) {
    creativeResults.push(await upsertCreativeSpec(
      manifest.campaignId,
      group,
      bundleForGroup(manifest, group, groupedEntries),
      { byAssetId: creativeByAssetId, byGroupKey: creativeByGroupKey },
    ));
  }
  const adsetResults = await upsertAdSetSpecs(manifest.campaignId, await getAdSetSpecs(manifest.campaignId));
  const specsPath = path.join(OUT_DIR, "problem-aware-full-specs.json");
  writeFileSync(specsPath, JSON.stringify({
    campaignId: manifest.campaignId,
    generationKey: GENERATION_KEY,
    createdAt: new Date().toISOString(),
    logicalGroupCount: manifest.groups.length,
    rawAssetCount: manifest.entries.length,
    creativeSpecs: creativeResults,
    adsetSpecs: adsetResults,
  }, null, 2) + "\n");
  console.log(JSON.stringify({
    campaignId: manifest.campaignId,
    generationKey: GENERATION_KEY,
    logicalGroupCount: manifest.groups.length,
    rawAssetCount: manifest.entries.length,
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
  const manifest = requireFullManifest();
  const payload = publishPayload();
  const response = await authed(`/meta/campaigns/${encodeURIComponent(manifest.campaignId)}/publish-plan/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const validationPath = path.join(OUT_DIR, "problem-aware-full-publish-validation.json");
  writeFileSync(validationPath, JSON.stringify({ payload, response }, null, 2) + "\n");
  if (!response.ok) {
    throw new Error(`Publish validation blocked. See ${validationPath}: ${JSON.stringify(response.blockers || response.items || [])}`);
  }
  if (Number.isFinite(response.includedCount) && response.includedCount !== manifest.groups.length) {
    throw new Error(`Publish validation included ${response.includedCount} ads; expected ${manifest.groups.length} logical groups.`);
  }
  if (Number.isFinite(response.adsetCount) && response.adsetCount !== 5) {
    throw new Error(`Publish validation returned adsetCount=${response.adsetCount}; expected 5.`);
  }
  if (Number.isFinite(response.bucketCount) && response.bucketCount !== 5) {
    throw new Error(`Publish validation returned bucketCount=${response.bucketCount}; expected 5.`);
  }
  console.log(JSON.stringify({
    campaignId: manifest.campaignId,
    ok: response.ok,
    includedCount: response.includedCount,
    adsetCount: response.adsetCount,
    bucketCount: response.bucketCount,
    logicalGroupCount: manifest.groups.length,
    rawAssetCount: manifest.entries.length,
    distribution: summarizeDistribution(response),
    publishDomain: response.publishDomain,
    validationPath,
  }, null, 2));
}

async function publish() {
  await getBackendToken();
  const manifest = requireFullManifest();
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
      logicalGroupCount: manifest.groups.length,
      rawAssetCount: manifest.entries.length,
    }, null, 2));
    return;
  }
  const payload = publishPayload();
  const response = await authed(`/meta/campaigns/${encodeURIComponent(manifest.campaignId)}/publish-runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const publishPath = path.join(OUT_DIR, "problem-aware-full-publish-run-response.json");
  writeFileSync(publishPath, JSON.stringify({ payload, response }, null, 2) + "\n");
  if (Array.isArray(response.items) && response.items.length !== manifest.groups.length) {
    throw new Error(`Publish run returned ${response.items.length} items; expected ${manifest.groups.length} logical groups. See ${publishPath}`);
  }
  console.log(JSON.stringify({
    campaignId: manifest.campaignId,
    publishRunId: response.id || null,
    status: response.status,
    metaCampaignId: response.metaCampaignId || response.meta_campaign_id || null,
    itemCount: Array.isArray(response.items) ? response.items.length : null,
    failedItems: Array.isArray(response.items) ? response.items.filter((item) => item.status === "failed").length : null,
    logicalGroupCount: manifest.groups.length,
    rawAssetCount: manifest.entries.length,
    publishPath,
  }, null, 2));
  if (response.status !== "published") {
    throw new Error(`Meta publish run did not finish as published. Status=${response.status}; see ${publishPath}`);
  }
}

async function publishStatus() {
  await getBackendToken();
  const manifest = requireFullManifest();
  const runs = await authed(`/meta/campaigns/${encodeURIComponent(manifest.campaignId)}/publish-runs`);
  const statusPath = path.join(OUT_DIR, "problem-aware-full-publish-runs.json");
  writeFileSync(statusPath, JSON.stringify({ checkedAt: new Date().toISOString(), runs }, null, 2) + "\n");
  const matching = (runs || []).filter((run) => run.generationKey === GENERATION_KEY);
  console.log(JSON.stringify({
    campaignId: manifest.campaignId,
    generationKey: GENERATION_KEY,
    logicalGroupCount: manifest.groups.length,
    rawAssetCount: manifest.entries.length,
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

function usage() {
  return [
    "Usage: node run_problem_aware_full_campaign.mjs <command>",
    "",
    "Commands:",
    "  setup",
    "  manifest",
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
  const command = process.argv[2] || "manifest";
  if (command === "help" || command === "--help") {
    console.log(usage());
    return;
  }
  if (command === "setup") return setupCampaign();
  if (command === "manifest") {
    const manifest = await buildManifest();
    console.log(JSON.stringify({
      manifestPath: MANIFEST_PATH,
      campaignId: manifest.campaignId,
      logicalGroups: manifest.groups.length,
      rawAssets: manifest.entries.length,
      counts: validateManifest(manifest, { requireResults: false }),
      copyAssignmentPlan: manifest.copyAssignmentPlan,
    }, null, 2));
    return;
  }
  if (command === "generate") return generateAll();
  if (command === "stamp-batch") return stampBatch();
  if (command === "create-specs") return createSpecs();
  if (command === "validate-publish") return validatePublish();
  if (command === "publish") return publish();
  if (command === "publish-status") return publishStatus();
  if (command === "all") {
    await setupCampaign();
    await buildManifest();
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
  process.exit(1);
});
