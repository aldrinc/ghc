import { execFileSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const OUT_DIR = path.join(
  ROOT,
  "outputs/tenor-pipeline-v3-meta-campaign-draft-2026-04-30",
);
const GENERATED_DIR = path.join(OUT_DIR, "generated");
const AUTH_FILE = path.join(ROOT, ".env.mos-test-auth");
const META_ADS_PATH = "/Users/aldrinclement/Downloads/pipeline-run-v3/phase-9-ads/meta-ads.md";
const PIPELINE_ROOT = "/Users/aldrinclement/Downloads/pipeline-run-v3";
const STATE_PATH = path.join(OUT_DIR, "state.json");

const API_BASE = "https://api.moshq.app";
const CLERK_BASE = "https://immune-turtle-79.clerk.accounts.dev/v1";
const CLERK_QUERY = "__clerk_api_version=2025-11-10&_clerk_js_version=5.125.10";
const ORIGIN_HEADERS = {
  Origin: "https://moshq.app",
  Referer: "https://moshq.app/",
};

const CLIENT_ID = "70124684-505f-48af-a25c-5f7a79601fa0";
const PRODUCT_ID = "8b89a76d-069c-41a6-be38-b7e4f4483460";
const EXISTING_TENOR_CAMPAIGN_ID = "a5af5e49-1eb8-4fb4-8029-d3d2006114e9";
const DEFAULT_COLLECTION_ID = "25b6115f-d5c5-4ddb-ada6-aba9ff704927";
const CAMPAIGN_NAME = "Tenor Pipeline V3 Meta Draft - No Product Reveal - 2026-04-30";
const CLONED_COLLECTION_NAME = "Tenor Pipeline V3 Meta Swipes - Default Clone - 2026-04-30";
const BRAND_NAME = "Tenor";
const PRODUCT_NAME = "Tenor Daily Drive Essentials";
const DESTINATION_URLS = {
  listicle_a: "https://shoptenorco.com/8b89a76d/daily-drive-essentials/3-reasons-your-t-booster-failed-and-none-of-them-are-your-fault/",
  listicle_b: "https://shoptenorco.com/8b89a76d/daily-drive-essentials/everything-youve-been-told-about-testosterone-support-is-based-on-half-the-science/",
  listicle_c: "https://shoptenorco.com/8b89a76d/daily-drive-essentials/94-more-morning-energy-92-more-like-yourself-the-21-ingredient-protocol-delivering-what-t-boosters-only-promised/",
  advertorial_a: "https://shoptenorco.com/8b89a76d/daily-drive-essentials/your-labs-are-normal-the-30-000-lie-doctors-tell-men-over-40-and-how-to-avoid-the-trap/",
  advertorial_b: "https://shoptenorco.com/8b89a76d/daily-drive-essentials/the-two-pathways-every-t-booster-ignores-and-why-thats-why-you-still-dont-feel-like-yourself/",
  advertorial_c: "https://shoptenorco.com/8b89a76d/daily-drive-essentials/needles-for-life-the-30-000-trt-trap-and-the-daily-protocol-you-try-first/",
  sales_pdp: "https://shoptenorco.com/8b89a76d/daily-drive-essentials/sales-page/",
};

let cachedToken = null;

function usage() {
  return [
    "Usage:",
    "  node tenor_campaign_runner.mjs inspect",
    "  node tenor_campaign_runner.mjs create-draft",
    "  node tenor_campaign_runner.mjs start-planning",
    "  node tenor_campaign_runner.mjs approve-planning-experiments",
    "  node tenor_campaign_runner.mjs load-context",
    "  node tenor_campaign_runner.mjs generate-funnels",
    "  node tenor_campaign_runner.mjs workflow-status --run=<workflowRunId>",
    "  node tenor_campaign_runner.mjs stop-workflow --run=<workflowRunId>",
    "  node tenor_campaign_runner.mjs list-funnels",
    "  node tenor_campaign_runner.mjs delete-campaign-funnels",
    "  node tenor_campaign_runner.mjs package-external",
    "  node tenor_campaign_runner.mjs generate --limit=5",
    "  node tenor_campaign_runner.mjs create-launch-specs",
    "  node tenor_campaign_runner.mjs validate-publish",
    "  node tenor_campaign_runner.mjs publish-now",
    "  node tenor_campaign_runner.mjs reconcile-creative-urls",
    "  node tenor_campaign_runner.mjs package",
  ].join("\n");
}

function readState() {
  if (!existsSync(STATE_PATH)) return {};
  return JSON.parse(readFileSync(STATE_PATH, "utf8"));
}

function writeState(next) {
  mkdirSync(OUT_DIR, { recursive: true });
  writeFileSync(STATE_PATH, JSON.stringify(next, null, 2) + "\n");
}

function mergeState(patch) {
  const state = readState();
  const next = { ...state, ...patch, updatedAt: new Date().toISOString() };
  writeState(next);
  return next;
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
    const error = new Error(
      `${options.method || "GET"} ${url} failed (${response.status}): ${text.slice(0, 2000)}`,
    );
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

function parseArgs(argv) {
  const args = {};
  for (const item of argv) {
    if (!item.startsWith("--")) continue;
    const [key, rawValue] = item.slice(2).split("=");
    args[key] = rawValue ?? "true";
  }
  return args;
}

function safeFile(pathname) {
  return existsSync(pathname) ? readFileSync(pathname, "utf8") : "";
}

function extractAdBlocks(markdown) {
  const re = /(?:^|\n)(### AD ([A-Z]+-[A-Z]\d+|[A-Z]+\d+)\b[\s\S]*?)(?=\n---\n\n(?:### AD |### VARIANT |## |#)|\s*$)/g;
  const ads = [];
  let match;
  while ((match = re.exec(markdown)) !== null) {
    const rawBlock = match[1].trim();
    const adId = match[2].trim();
    ads.push({
      adId,
      rawBlock,
      primaryText: fieldFromBlock(rawBlock, "Primary Text"),
      headline: fieldFromBlock(rawBlock, "Headline"),
      destination: fieldFromBlock(rawBlock, "Destination"),
      hookType: fieldFromBlock(rawBlock, "Hook Type"),
      format: fieldFromBlock(rawBlock, "Format"),
      stage: destinationStage(adId, fieldFromBlock(rawBlock, "Destination")),
    });
  }
  if (ads.length !== 30) {
    throw new Error(`Expected 30 ads in ${META_ADS_PATH}; found ${ads.length}.`);
  }
  return ads;
}

function fieldFromBlock(block, label) {
  const re = new RegExp(`^\\*\\*${label}:\\*\\*\\s*(.+)$`, "m");
  const match = block.match(re);
  return match ? match[1].trim() : null;
}

function destinationStage(adId, destination) {
  const value = `${adId} ${destination || ""}`.toLowerCase();
  if (value.includes("pdp") || value.includes("sales-page") || value.includes("sales page")) return "pdp";
  if (value.startsWith("l") || value.includes("listicle")) return "listicle";
  if (value.includes("advertorial") || value.startsWith("av-")) return "advertorial";
  return "unknown";
}

function destinationToken(ad) {
  if (ad.stage === "pdp") return "{{PDP_URL_PENDING}}";
  if (ad.stage === "listicle") {
    const listicleKey = listicleDestinationKey(ad);
    return `{{${listicleKey.toUpperCase()}_URL_PENDING}}`;
  }
  const dest = String(ad.destination || "");
  if (dest.includes("variant-b")) return "{{ADVERTORIAL_VARIANT_B_URL_PENDING}}";
  if (dest.includes("variant-c")) return "{{ADVERTORIAL_VARIANT_C_URL_PENDING}}";
  return "{{ADVERTORIAL_VARIANT_A_URL_PENDING}}";
}

function destinationKey(ad) {
  if (ad.stage === "pdp") return "sales_pdp";
  if (ad.stage === "listicle") return listicleDestinationKey(ad);
  const dest = String(ad.destination || "").toLowerCase();
  if (dest.includes("variant-b")) return "advertorial_b";
  if (dest.includes("variant-c")) return "advertorial_c";
  return "advertorial_a";
}

function destinationUrl(ad) {
  const key = destinationKey(ad);
  const url = DESTINATION_URLS[key];
  if (!url) throw new Error(`No destination URL configured for ${key}`);
  return url;
}

function listicleDestinationKey(ad) {
  const adId = String(ad.adId || "").toUpperCase();
  const headline = String(ad.headline || "").toLowerCase();
  const primary = String(ad.primaryText || "").toLowerCase();
  const hookType = String(ad.hookType || "").toLowerCase();

  const explicit = {
    L1: "listicle_b",
    L2: "listicle_a",
    L3: "listicle_c",
    L4: "listicle_c",
    L5: "listicle_c",
    L6: "listicle_b",
    L7: "listicle_c",
    L8: "listicle_c",
    L9: "listicle_c",
    L10: "listicle_a",
    L11: "listicle_c",
    L12: "listicle_b",
  };
  if (explicit[adId]) return explicit[adId];

  if (headline.includes("label") || primary.includes("proprietary blend")) return "listicle_a";
  if (hookType.includes("desire") || hookType.includes("social proof")) return "listicle_c";
  if (hookType.includes("contrarian")) return "listicle_b";
  if (hookType.includes("fear")) return "listicle_a";
  throw new Error(`No listicle destination rule for ${adId}`);
}

function destinationRationale(ad) {
  const key = destinationKey(ad);
  if (key === "advertorial_a") return "Meta ads file maps this ad to advertorial variant A.";
  if (key === "advertorial_b") return "Meta ads file maps this ad to advertorial variant B.";
  if (key === "advertorial_c") return "Meta ads file maps this ad to advertorial variant C.";
  if (key === "sales_pdp") return "Meta ads file maps this ad directly to the sales/PDP page.";
  if (key === "listicle_a") return "Listicle A is the past-failure/proprietary-blend variant; this ad emphasizes failed boosters or hidden-label risk.";
  if (key === "listicle_b") return "Listicle B is the mechanism/contrarian variant; this ad emphasizes incomplete science, pathways, or protocol architecture.";
  if (key === "listicle_c") return "Listicle C is the desire/stat-forward variant; this ad emphasizes desired outcome, survey result, guarantee, or testimonial proof.";
  return "Destination key resolved by campaign routing rules.";
}

function buildDestinationRegistry() {
  return {
    schemaVersion: 1,
    campaignId: readState().campaignId || null,
    urlState: "final_urls_supplied",
    salesDestinationKey: "sales_pdp",
    destinations: [
      {
        key: "advertorial_a",
        type: "pre_sales_advertorial",
        label: "Advertorial A - Your Labs Are Normal",
        sourcePath: "/Users/aldrinclement/Downloads/pipeline-run-v3/phase-5-advertorial/advertorial-variant-a.md",
        finalUrl: DESTINATION_URLS.advertorial_a,
        onwardDestinationKey: "sales_pdp",
      },
      {
        key: "advertorial_b",
        type: "pre_sales_advertorial",
        label: "Advertorial B - The Two Pathways Every T-Booster Ignores",
        sourcePath: "/Users/aldrinclement/Downloads/pipeline-run-v3/phase-5-advertorial/advertorial-variant-b.md",
        finalUrl: DESTINATION_URLS.advertorial_b,
        onwardDestinationKey: "sales_pdp",
      },
      {
        key: "advertorial_c",
        type: "pre_sales_advertorial",
        label: "Advertorial C - Needles for Life / TRT Trap",
        sourcePath: "/Users/aldrinclement/Downloads/pipeline-run-v3/phase-5-advertorial/advertorial-variant-c.md",
        finalUrl: DESTINATION_URLS.advertorial_c,
        onwardDestinationKey: "sales_pdp",
      },
      {
        key: "listicle_a",
        type: "pre_sales_listicle",
        label: "Listicle A - 3 Reasons Your T-Booster Failed",
        sourcePath: "/Users/aldrinclement/Downloads/pipeline-run-v3/phase-6-listicle/listicle-variant-a.md",
        finalUrl: DESTINATION_URLS.listicle_a,
        onwardDestinationKey: "sales_pdp",
      },
      {
        key: "listicle_b",
        type: "pre_sales_listicle",
        label: "Listicle B - Half the Science",
        sourcePath: "/Users/aldrinclement/Downloads/pipeline-run-v3/phase-6-listicle/listicle-variant-b.md",
        finalUrl: DESTINATION_URLS.listicle_b,
        onwardDestinationKey: "sales_pdp",
      },
      {
        key: "listicle_c",
        type: "pre_sales_listicle",
        label: "Listicle C - 94% Morning Energy / 92% Like Yourself",
        sourcePath: "/Users/aldrinclement/Downloads/pipeline-run-v3/phase-6-listicle/listicle-variant-c.md",
        finalUrl: DESTINATION_URLS.listicle_c,
        onwardDestinationKey: "sales_pdp",
      },
      {
        key: "sales_pdp",
        type: "sales_page",
        label: "Sales/PDP",
        sourcePath: "/Users/aldrinclement/Downloads/pipeline-run-v3/phase-7-sales-page/sales-page.md",
        finalUrl: DESTINATION_URLS.sales_pdp,
        onwardDestinationKey: null,
      },
    ],
  };
}

function adRoutingRows() {
  return adManifestBase().map((ad) => ({
    adId: ad.adId,
    stage: ad.stage,
    hookType: ad.hookType,
    headline: ad.headline,
    primaryText: ad.primaryText,
    format: ad.format,
    sourceDestination: ad.destination,
    destinationKey: destinationKey(ad),
    destinationToken: destinationToken(ad),
    finalUrl: destinationUrl(ad),
    rationale: destinationRationale(ad),
  }));
}

function writeCsv(rows, csvPath) {
  if (!rows.length) {
    writeFileSync(csvPath, "");
    return;
  }
  const header = Object.keys(rows[0]);
  const body = rows.map((row) =>
    header.map((key) => `"${String(row[key] ?? "").replaceAll('"', '""')}"`).join(","),
  );
  writeFileSync(csvPath, [header.join(","), ...body].join("\n") + "\n");
}

function buildComplianceMarkdown() {
  return [
    "# Tenor Meta Creative Compliance",
    "",
    "- Do not show the product image or any product object.",
    "- Do not show bottles, jars, boxes, pouches, labels, supplement facts panels, capsules, pills, powders, scoops, sachets, packaging, price, guarantee, ratings, or purchase/offer cues.",
    "- Do not reveal the product mechanism or solution mechanics.",
    "- Do not show an ingredient list, dosage, protocol architecture, hormone pathway, biological system diagram, comparison grid, checklist, or explanation of how the solution works.",
    "- Do not invent clinical data, patient data, study citations, endorsements, testimonials, lab values, social metrics, names, ages, dates, or URLs beyond the supplied pipeline copy.",
    "- Destination URLs are supplied for launch routing, but generated ad images must not display URLs.",
  ].join("\n");
}

function buildManualCreativeContextPayload() {
  const metaAds = safeFile(META_ADS_PATH);
  const creativeBrief = safeFile(path.join(PIPELINE_ROOT, "phase-4-brief/creative-brief.md"));
  const advertorialA = safeFile(path.join(PIPELINE_ROOT, "phase-5-advertorial/advertorial-variant-a.md"));
  const advertorialB = safeFile(path.join(PIPELINE_ROOT, "phase-5-advertorial/advertorial-variant-b.md"));
  const advertorialC = safeFile(path.join(PIPELINE_ROOT, "phase-5-advertorial/advertorial-variant-c.md"));
  const listicleA = safeFile(path.join(PIPELINE_ROOT, "phase-6-listicle/listicle-variant-a.md"));
  const listicleB = safeFile(path.join(PIPELINE_ROOT, "phase-6-listicle/listicle-variant-b.md"));
  const listicleC = safeFile(path.join(PIPELINE_ROOT, "phase-6-listicle/listicle-variant-c.md"));
  const salesPage = safeFile(path.join(PIPELINE_ROOT, "phase-7-sales-page/sales-page.md"));
  const audit = safeFile(path.join(PIPELINE_ROOT, "phase-10-ad-audit/ad-audit.md"));
  const finalReport = safeFile(path.join(PIPELINE_ROOT, "phase-11-final/final-report.md"));

  return {
    schemaVersion: 1,
    provider: "manual",
    angles: {
      selectedAngleId: "pipeline-v3-meta-ads",
      angleLibrary: [
        {
          angleId: "pipeline-v3-meta-ads",
          angleName: "Pipeline V3 Meta Ads",
          description: "Use the supplied Tenor pipeline v3 Meta ads, destination mapping, advertorial/listicle/PDP page context, and no-product/no-mechanism compliance constraints.",
          evidence: [
            META_ADS_PATH,
            "phase-5-advertorial",
            "phase-6-listicle",
            "phase-7-sales-page",
          ],
        },
      ],
    },
    offer: {
      ump: PRODUCT_NAME,
      ums: "Tenor pipeline v3 campaign creative generation",
      corePromise: "Create Meta creatives from the supplied campaign copy while withholding product reveal and mechanism details.",
      valueStackSummary: "Draft campaign setup and generated static Meta creatives for human review before Meta publishing.",
      guaranteeType: null,
      pricingRationale: "Destination URLs are supplied for routing; do not include price or offer cues in generated ads.",
      selectedVariantId: "pipeline-v3",
      selectedVariantName: "Pipeline V3 Meta Draft",
      offerDetailsMarkdown: [
        "# Offer Context",
        "",
        "Use the supplied destination URL registry for launch routing only. Do not display URLs in generated ad images.",
        "",
        "## Meta Ads",
        metaAds,
      ].join("\n"),
    },
    copyDocument: {
      headline: "Tenor Pipeline V3 Meta Ads",
      promiseContract: {
        loopQuestion: "Can the creative dramatize the ad hook without revealing the product or mechanism?",
        specificPromise: "Generate reviewable Meta ad creatives from the supplied copy and destination context.",
        deliveryTest: "No product object, packaging, ingredient/mechanism reveal, invented URLs, invented evidence, or purchase cues appear in the creative.",
        minimumDelivery: "Each creative should represent the corresponding ad copy and remain suitable for human review.",
      },
      presellMarkdown: [
        "# Advertorial Variants",
        advertorialA,
        "\n---\n",
        advertorialB,
        "\n---\n",
        advertorialC,
        "\n\n# Listicle Variants",
        listicleA,
        "\n---\n",
        listicleB,
        "\n---\n",
        listicleC,
      ].join("\n"),
      salesPageMarkdown: salesPage,
      templatePayloads: {
        metaAdsMarkdownPath: META_ADS_PATH,
        sourcePipelineRoot: PIPELINE_ROOT,
      },
    },
    copyContext: {
      audienceProductMarkdown: [
        "# Source Creative Brief",
        creativeBrief,
        "\n# Final Report",
        finalReport,
      ].join("\n"),
      brandVoiceMarkdown: "Confident, informed, warm, peer-to-peer. Never aggressive, bro-y, or clinical.",
      complianceMarkdown: buildComplianceMarkdown(),
      mentalModelsMarkdown: [
        "# Ad Audit",
        audit,
        "\n# Destination Mapping",
        `- AV-A1 through AV-A4: ${DESTINATION_URLS.advertorial_a}`,
        `- AV-B1 through AV-B4: ${DESTINATION_URLS.advertorial_b}`,
        `- AV-C1 through AV-C4: ${DESTINATION_URLS.advertorial_c}`,
        `- Listicle A: ${DESTINATION_URLS.listicle_a}`,
        `- Listicle B: ${DESTINATION_URLS.listicle_b}`,
        `- Listicle C: ${DESTINATION_URLS.listicle_c}`,
        `- PDP1 through PDP6: ${DESTINATION_URLS.sales_pdp}`,
      ].join("\n"),
      awarenessAngleMatrixMarkdown: metaAds,
    },
    experimentSpecs: [
      {
        id: "pipeline-v3-meta-creative-review",
        name: "Pipeline V3 Meta Creative Review",
        hypothesis: "The supplied Tenor Meta ads can be turned into reviewable creatives while teasing the problem without product reveal or mechanism reveal.",
        metricIds: [],
        variants: [
          {
            id: "advertorial",
            name: "Advertorial",
            description: "Cold traffic creatives mapped to advertorial variants A, B, and C.",
            channels: ["meta"],
            guardrails: ["no product reveal", "no mechanism reveal"],
          },
          {
            id: "listicle",
            name: "Listicle",
            description: "Warm traffic creatives mapped to listicle destination.",
            channels: ["meta"],
            guardrails: ["no product reveal", "no mechanism reveal"],
          },
          {
            id: "pdp",
            name: "PDP",
            description: "Hot traffic creatives mapped to PDP/sales page destination.",
            channels: ["meta"],
            guardrails: ["no product reveal", "no mechanism reveal"],
          },
        ],
      },
    ],
  };
}

function adManifestBase() {
  const metaAdsMarkdown = readFileSync(META_ADS_PATH, "utf8");
  return extractAdBlocks(metaAdsMarkdown).map((ad, index) => ({
    ...ad,
    destinationToken: destinationToken(ad),
    ordinal: index + 1,
  }));
}

function buildSwipeAngle(ad) {
  return [
    `Meta ad copy/context from ${META_ADS_PATH}:`,
    "",
    ad.rawBlock,
    "",
    "Compliance constraints:",
    "- Do not show the product image or any product object.",
    "- Do not show bottles, jars, boxes, pouches, labels, supplement facts panels, capsules, pills, powders, scoops, sachets, packaging, price, guarantee, ratings, or purchase/offer cues.",
    "- Do not reveal the product mechanism or solution mechanics: no ingredient list, dosage, protocol architecture, hormone pathway, biological system diagram, comparison grid, checklist, or explanation of how the solution works.",
    "- Do not invent clinical data, patient data, study citations, endorsements, testimonials, lab values, social metrics, names, ages, dates, or URLs beyond the provided Meta ad copy/context.",
    `- Final destination URL for launch routing is ${destinationUrl(ad)}; do not show this URL in the ad image.`,
  ].join("\n");
}

function chooseBriefForAd(ad, briefOptions) {
  const byDestination = briefOptions.filter((brief) => {
    const destination = String(brief.destinationPage || brief.destinationType || brief.destinationLabel || "").toLowerCase();
    if (ad.stage === "pdp") return !destination.includes("pre-sales") && (destination.includes("sales") || destination.includes("pdp"));
    return destination.includes("pre") || destination.includes("listicle") || destination.includes("advertorial");
  });
  const candidates = byDestination.length ? byDestination : briefOptions;
  const format = String(ad.format || "").toLowerCase();
  const wantsCarousel = format.includes("carousel");
  const matched = candidates.find((brief) => wantsCarousel ? brief.imageRequirementCount > 1 : brief.imageRequirementCount === 1)
    || candidates[ad.ordinal % candidates.length]
    || candidates[0];
  if (!matched) throw new Error(`No image asset brief available for ${ad.adId}.`);
  return matched;
}

function chooseSwipeForAd(ad, swipes) {
  const format = String(ad.format || "").toLowerCase();
  const titleNeedles = /needle|trt|medical|blood|injection/.test(format);
  const titleLab = /lab|report|doctor/.test(format);
  const titleFatigue = /fatigue|drained|energy|domestic|man/.test(format);
  const titleText = /typography|bold|text|list/.test(format);
  const searchable = swipes.map((swipe) => ({
    swipe,
    haystack: [
      swipe.title,
      swipe.body,
      swipe.visual_archetype,
      swipe.hook_type,
      swipe.destination_type,
      swipe.funnel_stage,
      swipe.product_presence,
      swipe.media?.[0]?.path,
      swipe.media?.[0]?.url,
      swipe.media?.[0]?.thumbnail_url,
    ].filter(Boolean).join(" ").toLowerCase(),
  }));
  const find = (patterns) => searchable.find(({ haystack }) => patterns.some((pattern) => haystack.includes(pattern)))?.swipe;
  if (titleNeedles) return find(["needle", "medical", "trt", "doctor", "blood"]) || swipes[ad.ordinal % swipes.length];
  if (titleLab) return find(["lab", "report", "doctor", "science"]) || swipes[ad.ordinal % swipes.length];
  if (titleFatigue) return find(["fatigue", "man", "energy", "drained"]) || swipes[ad.ordinal % swipes.length];
  if (titleText) return find(["text", "typography", "headline", "big_text"]) || swipes[ad.ordinal % swipes.length];
  return swipes[ad.ordinal % swipes.length];
}

function isStaticImageSwipe(swipe) {
  const format = String(swipe.ad_unit_format || "").toLowerCase();
  if (format === "image") return true;
  const media = Array.isArray(swipe.media) ? swipe.media : [];
  return media.some((item) => {
    const mime = String(item?.mime_type || item?.mimeType || "").toLowerCase();
    const url = String(item?.url || item?.download_url || item?.thumbnail_url || item?.path || "").toLowerCase();
    return mime.startsWith("image/") || /\.(png|jpe?g|webp)(?:$|\?)/.test(url);
  });
}

function summarizeBriefs(artifacts) {
  const rows = [];
  for (const artifact of artifacts) {
    const briefs = artifact?.data?.asset_briefs || artifact?.data?.assetBriefs || [];
    for (const brief of briefs) {
      const requirements = Array.isArray(brief.requirements) ? brief.requirements : [];
      const imageRequirements = requirements
        .map((req, index) => ({ req, index }))
        .filter(({ req }) => String(req?.format || "").toLowerCase().replace(/-/g, "_").includes("image"));
      if (!imageRequirements.length) continue;
      rows.push({
        artifactId: artifact.id,
        id: brief.id,
        name: brief.name || brief.title || brief.id,
        destinationPage: brief.destinationPage || brief.destination_type || brief.destinationType || brief.destinationLabel || null,
        funnelId: brief.funnelId || brief.funnel_id || null,
        imageRequirementCount: imageRequirements.length,
        imageRequirementIndexes: imageRequirements.map((item) => item.index),
        requirements,
      });
    }
  }
  return rows;
}

async function getArtifacts(campaignId, type) {
  return authed(
    `/artifacts?clientId=${encodeURIComponent(CLIENT_ID)}&campaignId=${encodeURIComponent(campaignId)}&type=${encodeURIComponent(type)}`,
  );
}

async function getGeneratedAssets(campaignId) {
  return authed(
    `/assets?campaignId=${encodeURIComponent(campaignId)}&productId=${encodeURIComponent(PRODUCT_ID)}&assetKind=image`,
  );
}

async function getCreativeSpecs(campaignId) {
  return authed(`/meta/specs/creatives?campaignId=${encodeURIComponent(campaignId)}`);
}

async function getAdSetSpecs(campaignId) {
  return authed(`/meta/specs/adsets?campaignId=${encodeURIComponent(campaignId)}`);
}

function launchGenerationKey() {
  const rawBatchId = process.env.TENOR_LAUNCH_BATCH_ID || "tenor-pipeline-v3-meta-20260430";
  return rawBatchId.startsWith("batch:") ? rawBatchId : `batch:${rawBatchId}`;
}

function launchPublishPayload() {
  return {
    generationKey: launchGenerationKey(),
    publishBaseUrl: "https://shop.shoptenorco.com",
    campaignName:
      process.env.TENOR_LAUNCH_CAMPAIGN_NAME ||
      "Tenor Pipeline V3 Meta Launch - 2026-04-30 - Compliance Clean 15",
    campaignObjective: "OUTCOME_SALES",
    buyingType: "AUCTION",
    specialAdCategories: [],
    campaignDailyBudget: 10000,
    bucketCount: 5,
    bucketDestinationUrls: [],
  };
}

function cleanMetaPrimaryText(value) {
  if (!value) return null;
  return String(value).replace(/\s*\[Link\]\s*$/i, "").trim() || null;
}

function cleanMetaHeadline(value) {
  if (!value) return null;
  return String(value).replace(/\s*\(\d+\s*chars?\)\s*$/i, "").trim() || null;
}

function requireGeneratedManifest() {
  const state = readState();
  if (!state.campaignId) throw new Error("Missing campaignId in state.");
  const manifestPath = state.generatedManifestPath || path.join(OUT_DIR, "generated-manifest.json");
  if (!existsSync(manifestPath)) {
    throw new Error(`Missing generated manifest at ${manifestPath}. Run generate first.`);
  }
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  const outputs = Array.isArray(manifest.outputs) ? manifest.outputs : [];
  if (outputs.length !== 30) {
    throw new Error(`Expected 30 generated outputs before launch setup; found ${outputs.length}.`);
  }
  const adIds = new Set();
  const assetIds = new Set();
  for (const output of outputs) {
    if (!output.adId || !output.assetId) {
      throw new Error(`Generated output is missing adId or assetId: ${JSON.stringify(output)}`);
    }
    if (adIds.has(output.adId)) throw new Error(`Duplicate generated ad id: ${output.adId}`);
    if (assetIds.has(output.assetId)) throw new Error(`Duplicate generated asset id: ${output.assetId}`);
    adIds.add(output.adId);
    assetIds.add(output.assetId);
  }
  return { state, manifestPath, manifest, outputs };
}

function requireRoutingRows() {
  const routingPath = path.join(OUT_DIR, "external-ad-routing.json");
  if (!existsSync(routingPath)) {
    throw new Error(`Missing external ad routing file at ${routingPath}. Run package-external first.`);
  }
  const payload = JSON.parse(readFileSync(routingPath, "utf8"));
  const routing = Array.isArray(payload.routing) ? payload.routing : [];
  if (routing.length !== 30) {
    throw new Error(`Expected 30 routing rows; found ${routing.length}.`);
  }
  return routing;
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

function adsetMetadata(spec) {
  return specMetadata(spec);
}

async function cmdCreateLaunchSpecs() {
  await getBackendToken();
  const { state, manifestPath, outputs } = requireGeneratedManifest();
  const routing = requireRoutingRows();
  const routeByAdId = new Map(routing.map((row) => [row.adId, row]));
  const existingCreativeSpecs = await getCreativeSpecs(state.campaignId);
  const creativeByAssetId = new Map();
  for (const spec of existingCreativeSpecs || []) {
    const assetId = specAssetId(spec);
    if (assetId) creativeByAssetId.set(assetId, spec);
  }

  const createdCreatives = [];
  const verifiedCreatives = [];
  for (const output of outputs) {
    const route = routeByAdId.get(output.adId);
    if (!route) throw new Error(`Missing routing row for generated ad ${output.adId}.`);
    const primaryText = cleanMetaPrimaryText(route.primaryText);
    const headline = cleanMetaHeadline(route.headline);
    const existing = creativeByAssetId.get(output.assetId);
    if (existing) {
      const mismatches = [];
      if (specDestinationUrl(existing) !== route.finalUrl) mismatches.push("destinationUrl");
      if (specPrimaryText(existing) !== primaryText) mismatches.push("primaryText");
      if (specHeadline(existing) !== headline) mismatches.push("headline");
      if (mismatches.length) {
        throw new Error(
          `Creative spec ${existing.id || ""} for asset ${output.assetId} does not match launch routing fields: ${mismatches.join(", ")}`,
        );
      }
      verifiedCreatives.push({ adId: output.adId, assetId: output.assetId, creativeSpecId: existing.id || null });
      continue;
    }
    const created = await authed("/meta/specs/creatives", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        assetId: output.assetId,
        campaignId: state.campaignId,
        name: `${output.adId} - ${headline || route.destinationKey}`,
        primaryText,
        headline,
        description: null,
        callToActionType: "LEARN_MORE",
        destinationUrl: route.finalUrl,
        status: "draft",
        metadata: {
          externalRoutingAdId: route.adId,
          externalDestinationKey: route.destinationKey,
          externalFinalUrl: route.finalUrl,
          externalRoutingSource: "tenor-pipeline-v3/external-ad-routing.json",
          sourceMetaAdsPath: META_ADS_PATH,
          sourcePrimaryText: route.primaryText,
          sourceHeadline: route.headline,
          productImageOrObjectAllowed: false,
          mechanismRevealAllowed: false,
        },
      }),
    });
    createdCreatives.push({ adId: output.adId, assetId: output.assetId, creativeSpecId: created.id || null });
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
  const attributionSpec = [
    { event_type: "CLICK_THROUGH", window_days: 7 },
    { event_type: "VIEW_THROUGH", window_days: 1 },
    { event_type: "ENGAGED_VIDEO_VIEW", window_days: 1 },
  ];
  const existingAdsets = await getAdSetSpecs(state.campaignId);
  const existingBuckets = new Map();
  for (const spec of existingAdsets || []) {
    const metadata = adsetMetadata(spec);
    if (
      metadata.templateId === "default-broad-int-cbo"
      && Number(metadata.bucketCount) === 5
      && Number(metadata.bucketIndex) >= 1
      && Number(metadata.bucketIndex) <= 5
    ) {
      const bucketIndex = Number(metadata.bucketIndex);
      if (existingBuckets.has(bucketIndex)) {
        throw new Error(`Duplicate default CBO bucket ad set spec for bucket ${bucketIndex}.`);
      }
      existingBuckets.set(bucketIndex, spec);
    }
  }

  const createdAdsets = [];
  const verifiedAdsets = [];
  for (let bucketIndex = 1; bucketIndex <= 5; bucketIndex += 1) {
    const existing = existingBuckets.get(bucketIndex);
    if (existing) {
      verifiedAdsets.push({ bucketIndex, adsetSpecId: adsetId(existing) });
      continue;
    }
    const created = await authed("/meta/specs/adsets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        campaignId: state.campaignId,
        name: `CBO Bucket ${bucketIndex}`,
        status: "draft",
        optimizationGoal: "OFFSITE_CONVERSIONS",
        billingEvent: "IMPRESSIONS",
        targeting,
        placements: null,
        dailyBudget: null,
        lifetimeBudget: null,
        promotedObject: null,
        conversionDomain: "shoptenorco.com",
        metadata: {
          templateId: "default-broad-int-cbo",
          campaignDailyBudget: 10000,
          bucketIndex,
          bucketCount: 5,
          bucketStrategy: "deterministic_round_robin",
          attributionSpec,
          source: "tenor_pipeline_v3_manual_launch_setup",
        },
      }),
    });
    createdAdsets.push({ bucketIndex, adsetSpecId: created.id || null });
  }

  const specsPath = path.join(OUT_DIR, "launch-specs-created.json");
  writeFileSync(
    specsPath,
    JSON.stringify(
      {
        campaignId: state.campaignId,
        generationKey: launchGenerationKey(),
        manifestPath,
        createdAt: new Date().toISOString(),
        creativeSpecs: { created: createdCreatives, verified: verifiedCreatives },
        adsetSpecs: { created: createdAdsets, verified: verifiedAdsets },
      },
      null,
      2,
    ) + "\n",
  );
  mergeState({ launchSpecsPath: specsPath, launchGenerationKey: launchGenerationKey() });
  console.log(JSON.stringify({
    campaignId: state.campaignId,
    generationKey: launchGenerationKey(),
    creativeSpecsCreated: createdCreatives.length,
    creativeSpecsVerified: verifiedCreatives.length,
    adsetSpecsCreated: createdAdsets.length,
    adsetSpecsVerified: verifiedAdsets.length,
    specsPath,
  }, null, 2));
}

async function cmdValidatePublish() {
  await getBackendToken();
  const { state } = requireGeneratedManifest();
  const payload = launchPublishPayload();
  const response = await authed(`/meta/campaigns/${encodeURIComponent(state.campaignId)}/publish-plan/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const validationPath = path.join(OUT_DIR, "publish-validation.json");
  writeFileSync(validationPath, JSON.stringify({ payload, response }, null, 2) + "\n");
  mergeState({ publishValidationPath: validationPath });
  if (!response.ok) {
    throw new Error(`Publish validation blocked. See ${validationPath}: ${JSON.stringify(response.blockers || [])}`);
  }
  console.log(JSON.stringify({
    campaignId: state.campaignId,
    ok: response.ok,
    includedCount: response.includedCount,
    adsetCount: response.adsetCount,
    publishDomain: response.publishDomain,
    validationPath,
  }, null, 2));
}

async function cmdPublishNow() {
  await getBackendToken();
  const { state } = requireGeneratedManifest();
  const payload = launchPublishPayload();
  const response = await authed(`/meta/campaigns/${encodeURIComponent(state.campaignId)}/publish-runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const publishPath = path.join(OUT_DIR, "publish-run-response.json");
  writeFileSync(publishPath, JSON.stringify({ payload, response }, null, 2) + "\n");
  mergeState({
    publishRunResponsePath: publishPath,
    publishRunId: response.id || null,
    metaCampaignId: response.metaCampaignId || response.meta_campaign_id || null,
  });
  console.log(JSON.stringify({
    campaignId: state.campaignId,
    publishRunId: response.id || null,
    status: response.status,
    metaCampaignId: response.metaCampaignId || response.meta_campaign_id || null,
    itemCount: Array.isArray(response.items) ? response.items.length : null,
    publishPath,
  }, null, 2));
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

async function waitForPlanningExperiments(workflowRunId, timeoutMs = 15 * 60 * 1000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const detail = await authed(`/workflows/${encodeURIComponent(workflowRunId)}`);
    const status = detail?.run?.status;
    const experimentArtifacts = detail?.experiment_specs || [];
    if (experimentArtifacts.length) return detail;
    if (status === "failed" || status === "cancelled") {
      throw new Error(`Campaign planning workflow ${workflowRunId} ended with ${status}.`);
    }
    console.log(`Planning workflow ${workflowRunId} status=${status}; waiting for experiment specs...`);
    await new Promise((resolve) => setTimeout(resolve, 10000));
  }
  throw new Error(`Timed out waiting for experiment specs from planning workflow ${workflowRunId}`);
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

function downloadPublicAsset(publicId, outputPath) {
  execFileSync("curl", ["-sS", "-L", `${API_BASE}/public/assets/${publicId}`, "-o", outputPath], {
    stdio: "inherit",
  });
}

async function cmdInspect() {
  await getBackendToken();
  const [campaigns, collections, defaultCollection, oldBriefArtifacts] = await Promise.all([
    authed(`/campaigns?client_id=${encodeURIComponent(CLIENT_ID)}&product_id=${encodeURIComponent(PRODUCT_ID)}`),
    authed("/swipes/collections"),
    authed(`/swipes/collections/${encodeURIComponent(DEFAULT_COLLECTION_ID)}?limit=500`),
    getArtifacts(EXISTING_TENOR_CAMPAIGN_ID, "asset_brief"),
  ]);
  const inspection = {
    checkedAt: new Date().toISOString(),
    campaigns: campaigns.map((campaign) => ({
      id: campaign.id,
      name: campaign.name,
      channels: campaign.channels,
      assetBriefTypes: campaign.asset_brief_types,
      defaultSwipeCollectionId: campaign.default_swipe_collection_id,
      createdAt: campaign.created_at,
    })),
    collections: collections.map((collection) => ({
      id: collection.id,
      name: collection.name,
      kind: collection.kind,
      itemCount: collection.item_count,
      writable: collection.writable,
    })),
    defaultCollection: {
      id: defaultCollection.id,
      name: defaultCollection.name,
      kind: defaultCollection.kind,
      itemCount: defaultCollection.item_count,
      swipes: (defaultCollection.swipes || []).map((swipe) => ({
        id: swipe.id,
        title: swipe.title,
        adUnitFormat: swipe.ad_unit_format,
        placementShape: swipe.placement_shape,
        productImagePolicy: swipe.product_image_policy,
        productPresence: swipe.product_presence,
        visualArchetype: swipe.visual_archetype,
        media: (swipe.media || []).map((media) => ({
          url: media.url,
          thumbnailUrl: media.thumbnail_url,
          mimeType: media.mime_type,
          path: media.path,
        })),
      })),
    },
    oldCampaignBriefs: summarizeBriefs(oldBriefArtifacts),
  };
  const outputPath = path.join(OUT_DIR, "inspection.json");
  writeFileSync(outputPath, JSON.stringify(inspection, null, 2) + "\n");
  console.log(JSON.stringify({
    outputPath,
    campaignCount: inspection.campaigns.length,
    defaultSwipeCount: inspection.defaultCollection.swipes.length,
    oldCampaignBriefCount: inspection.oldCampaignBriefs.length,
  }, null, 2));
}

async function findOrCreateCampaign() {
  const state = readState();
  if (state.campaignId) {
    return authed(`/campaigns/${encodeURIComponent(state.campaignId)}`);
  }
  const campaigns = await authed(
    `/campaigns?client_id=${encodeURIComponent(CLIENT_ID)}&product_id=${encodeURIComponent(PRODUCT_ID)}`,
  );
  const existing = campaigns.find((campaign) => campaign.name === CAMPAIGN_NAME);
  if (existing) {
    mergeState({ campaignId: existing.id, campaignName: existing.name });
    return existing;
  }
  const payload = {
    client_id: CLIENT_ID,
    product_id: PRODUCT_ID,
    name: CAMPAIGN_NAME,
    channels: ["meta"],
    asset_brief_types: ["image"],
    start_planning: false,
    goal_description: "Generate Tenor pipeline v3 Meta creatives for review using the supplied phase-9 meta ads, with no product image/object and no mechanism reveal. Destination URLs are pending.",
    objective_type: "draft_meta_creative_review",
  };
  const created = await authed("/campaigns", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  mergeState({ campaignId: created.id, campaignName: created.name });
  return created;
}

async function findOrCloneCollection() {
  const state = readState();
  if (state.swipeCollectionId) {
    return authed(`/swipes/collections/${encodeURIComponent(state.swipeCollectionId)}?limit=500`);
  }
  const collections = await authed("/swipes/collections");
  const existing = collections.find((collection) => collection.name === CLONED_COLLECTION_NAME);
  if (existing) {
    mergeState({ swipeCollectionId: existing.id, swipeCollectionName: existing.name });
    return authed(`/swipes/collections/${encodeURIComponent(existing.id)}?limit=500`);
  }
  const cloned = await authed(`/swipes/collections/${encodeURIComponent(DEFAULT_COLLECTION_ID)}/clone`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: CLONED_COLLECTION_NAME }),
  });
  mergeState({ swipeCollectionId: cloned.id, swipeCollectionName: cloned.name });
  return authed(`/swipes/collections/${encodeURIComponent(cloned.id)}?limit=500`);
}

async function cmdCreateDraft() {
  await getBackendToken();
  const campaign = await findOrCreateCampaign();
  const collection = await findOrCloneCollection();
  await authed(`/campaigns/${encodeURIComponent(campaign.id)}/swipe-default`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ swipeCollectionId: collection.id }),
  });
  const delivery = await authed(`/campaigns/${encodeURIComponent(campaign.id)}/delivery`);
  const state = mergeState({
    campaignId: campaign.id,
    campaignName: campaign.name,
    swipeCollectionId: collection.id,
    swipeCollectionName: collection.name,
    delivery,
  });
  console.log(JSON.stringify({
    campaignId: campaign.id,
    campaignName: campaign.name,
    swipeCollectionId: collection.id,
    swipeCollectionName: collection.name,
    deliveryMode: delivery.deliveryMode,
    statePath: STATE_PATH,
    updatedAt: state.updatedAt,
  }, null, 2));
}

async function cmdStartPlanning() {
  await getBackendToken();
  const campaign = await findOrCreateCampaign();
  const state = readState();
  if (state.planningWorkflowRunId) {
    console.log(JSON.stringify({ planningWorkflowRunId: state.planningWorkflowRunId, reused: true }, null, 2));
    return;
  }
  const started = await authed(`/campaigns/${encodeURIComponent(campaign.id)}/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ business_goal_id: null }),
  });
  mergeState({
    planningWorkflowRunId: started.workflow_run_id,
    planningTemporalWorkflowId: started.temporal_workflow_id,
  });
  const detail = await waitForPlanningExperiments(started.workflow_run_id);
  const experimentSpecs = (detail.experiment_specs || []).flatMap((artifact) => artifact?.data?.experimentSpecs || artifact?.data?.experiment_specs || []);
  const experimentIds = experimentSpecs.map((spec) => spec.id).filter(Boolean);
  mergeState({ planningExperimentIds: experimentIds });
  console.log(JSON.stringify({
    planningWorkflowRunId: started.workflow_run_id,
    experimentIds,
  }, null, 2));
}

async function cmdApprovePlanningExperiments() {
  await getBackendToken();
  const state = readState();
  if (!state.planningWorkflowRunId) {
    throw new Error("Missing planningWorkflowRunId in state. Run start-planning first.");
  }
  let experimentIds = state.planningExperimentIds || [];
  if (!experimentIds.length) {
    const detail = await waitForPlanningExperiments(state.planningWorkflowRunId);
    experimentIds = (detail.experiment_specs || []).flatMap((artifact) => artifact?.data?.experimentSpecs || artifact?.data?.experiment_specs || []).map((spec) => spec.id).filter(Boolean);
  }
  if (!experimentIds.length) throw new Error("No planning experiment IDs available to approve.");
  await authed(`/workflows/${encodeURIComponent(state.planningWorkflowRunId)}/signals/approve-experiments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved_ids: experimentIds, rejected_ids: [] }),
  });
  const detail = await waitForWorkflow(state.planningWorkflowRunId);
  const briefArtifacts = detail.asset_briefs || [];
  const briefOptions = summarizeBriefs(briefArtifacts);
  if (!briefOptions.length) throw new Error("Planning completed but produced no image asset briefs.");
  mergeState({ planningApprovedExperimentIds: experimentIds, briefOptions });
  console.log(JSON.stringify({
    planningWorkflowRunId: state.planningWorkflowRunId,
    approvedExperimentIds: experimentIds,
    briefCount: briefOptions.length,
    briefIds: briefOptions.map((brief) => brief.id),
  }, null, 2));
}

async function cmdLoadContext() {
  await getBackendToken();
  const campaign = await findOrCreateCampaign();
  const payload = buildManualCreativeContextPayload();
  const response = await authed(`/campaigns/${encodeURIComponent(campaign.id)}/creative-context/loaded`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const outputPath = path.join(OUT_DIR, "manual-creative-context-payload.json");
  writeFileSync(outputPath, JSON.stringify(payload, null, 2) + "\n");
  mergeState({
    creativeContextArtifactId: response.creativeContextArtifactId,
    experimentSpecArtifactId: response.experimentSpecArtifactId,
    uploadedDocKeys: response.uploadedDocKeys,
    manualCreativeContextPayloadPath: outputPath,
  });
  console.log(JSON.stringify({
    campaignId: campaign.id,
    creativeContextArtifactId: response.creativeContextArtifactId,
    experimentSpecArtifactId: response.experimentSpecArtifactId,
    uploadedDocKeys: response.uploadedDocKeys,
    payloadPath: outputPath,
  }, null, 2));
}

async function cmdGenerateFunnels() {
  await getBackendToken();
  const state = readState();
  if (!state.campaignId) throw new Error("Missing campaignId in state. Run create-draft first.");
  const experimentId = "pipeline-v3-meta-creative-review";
  if (state.funnelGenerationWorkflowRunId) {
    console.log(JSON.stringify({
      funnelGenerationWorkflowRunId: state.funnelGenerationWorkflowRunId,
      reused: true,
    }, null, 2));
    return;
  }
  const started = await authed(`/campaigns/${encodeURIComponent(state.campaignId)}/funnels/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      experimentIds: [experimentId],
      variantIdsByExperiment: {
        [experimentId]: ["advertorial", "listicle", "pdp"],
      },
      asyncMediaEnrichment: true,
      variantActivityConcurrency: 1,
      generateTestimonials: false,
    }),
  });
  mergeState({
    funnelGenerationWorkflowRunId: started.workflow_run_id,
    funnelGenerationTemporalWorkflowId: started.temporal_workflow_id,
  });
  const detail = await waitForWorkflow(started.workflow_run_id, 90 * 60 * 1000);
  const briefArtifacts = detail.asset_briefs || await getArtifacts(state.campaignId, "asset_brief");
  const briefOptions = summarizeBriefs(briefArtifacts);
  if (!briefOptions.length) {
    throw new Error("Funnel generation completed but produced no image asset briefs.");
  }
  mergeState({ briefOptions });
  const detailPath = path.join(OUT_DIR, "funnel-generation-workflow.json");
  writeFileSync(detailPath, JSON.stringify(detail, null, 2) + "\n");
  console.log(JSON.stringify({
    campaignId: state.campaignId,
    funnelGenerationWorkflowRunId: started.workflow_run_id,
    briefCount: briefOptions.length,
    briefIds: briefOptions.map((brief) => brief.id),
    detailPath,
  }, null, 2));
}

async function cmdWorkflowStatus(argv) {
  const args = parseArgs(argv);
  const state = readState();
  const runId = args.run || state.funnelGenerationWorkflowRunId || state.planningWorkflowRunId;
  if (!runId) throw new Error("Missing workflow run id. Pass --run=<workflowRunId>.");
  await getBackendToken();
  const detail = await authed(`/workflows/${encodeURIComponent(runId)}`);
  const outputPath = path.join(OUT_DIR, `workflow-status-${runId}.json`);
  writeFileSync(outputPath, JSON.stringify(detail, null, 2) + "\n");
  const logs = detail.logs || [];
  console.log(JSON.stringify({
    runId,
    status: detail.run?.status,
    kind: detail.run?.kind,
    logCount: logs.length,
    latestLogs: logs.slice(-8).map((log) => ({
      step: log.step,
      status: log.status,
      error: log.error || null,
      createdAt: log.created_at,
      payloadOutKeys: log.payload_out && typeof log.payload_out === "object" ? Object.keys(log.payload_out) : [],
    })),
    assetBriefArtifacts: (detail.asset_briefs || []).length,
    experimentSpecArtifacts: (detail.experiment_specs || []).length,
    outputPath,
  }, null, 2));
}

async function cmdStopWorkflow(argv) {
  const args = parseArgs(argv);
  const state = readState();
  const runId = args.run || state.funnelGenerationWorkflowRunId;
  if (!runId) throw new Error("Missing workflow run id. Pass --run=<workflowRunId>.");
  await getBackendToken();
  const response = await authed(`/workflows/${encodeURIComponent(runId)}/signals/stop`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  mergeState({
    stoppedWorkflowRunId: runId,
    stoppedWorkflowSignalSentAt: new Date().toISOString(),
    externalFunnelMode: true,
  });
  console.log(JSON.stringify({ runId, response }, null, 2));
}

async function listCampaignFunnels(campaignId) {
  return authed(`/funnels?campaignId=${encodeURIComponent(campaignId)}`);
}

async function cmdListFunnels() {
  const state = readState();
  if (!state.campaignId) throw new Error("Missing campaignId in state.");
  await getBackendToken();
  const funnels = await listCampaignFunnels(state.campaignId);
  const outputPath = path.join(OUT_DIR, "campaign-funnels.json");
  writeFileSync(outputPath, JSON.stringify(funnels, null, 2) + "\n");
  console.log(JSON.stringify({
    campaignId: state.campaignId,
    funnelCount: funnels.length,
    funnels: funnels.map((funnel) => ({
      id: funnel.id,
      name: funnel.name,
      status: funnel.status,
      experimentSpecId: funnel.experiment_spec_id,
      createdAt: funnel.created_at,
    })),
    outputPath,
  }, null, 2));
}

async function cmdDeleteCampaignFunnels() {
  const state = readState();
  if (!state.campaignId) throw new Error("Missing campaignId in state.");
  await getBackendToken();
  const funnels = await listCampaignFunnels(state.campaignId);
  const deleted = [];
  for (const funnel of funnels) {
    await authed(`/funnels/${encodeURIComponent(funnel.id)}`, { method: "DELETE" });
    deleted.push(funnel.id);
  }
  mergeState({
    externalFunnelMode: true,
    deletedInternalFunnelIds: deleted,
    deletedInternalFunnelsAt: new Date().toISOString(),
  });
  console.log(JSON.stringify({
    campaignId: state.campaignId,
    deletedCount: deleted.length,
    deleted,
  }, null, 2));
}

async function resolveAsset(campaignId, assetId) {
  const rows = await getGeneratedAssets(campaignId);
  const row = rows.find((asset) => asset.id === assetId);
  if (!row?.public_id) throw new Error(`Could not resolve generated public_id for asset ${assetId}`);
  return row;
}

async function cmdGenerate(argv) {
  const args = parseArgs(argv);
  const limit = args.limit ? Number.parseInt(args.limit, 10) : 30;
  if (!Number.isFinite(limit) || limit < 1 || limit > 30) {
    throw new Error("--limit must be between 1 and 30.");
  }
  await getBackendToken();
  mkdirSync(GENERATED_DIR, { recursive: true });
  const state = readState();
  if (!state.campaignId) throw new Error("Missing campaignId in state. Run create-draft first.");

  let briefOptions = state.briefOptions;
  if (!Array.isArray(briefOptions) || !briefOptions.length) {
    const artifacts = await getArtifacts(state.campaignId, "asset_brief");
    briefOptions = summarizeBriefs(artifacts);
    if (!briefOptions.length) {
      throw new Error("No image asset briefs are available for this campaign. Run start-planning and approve-planning-experiments first.");
    }
    mergeState({ briefOptions });
  }

  const collectionId = state.swipeCollectionId || DEFAULT_COLLECTION_ID;
  const collection = await authed(`/swipes/collections/${encodeURIComponent(collectionId)}?limit=500`);
  const swipes = (collection.swipes || []).filter(isStaticImageSwipe);
  if (!swipes.length) throw new Error(`Swipe collection ${collectionId} has no static image swipes.`);

  const ads = adManifestBase().slice(0, limit);
  const existingManifestPath = path.join(OUT_DIR, "generated-manifest.json");
  const existingManifest = existsSync(existingManifestPath)
    ? JSON.parse(readFileSync(existingManifestPath, "utf8"))
    : { campaignId: state.campaignId, outputs: [] };
  const outputs = Array.isArray(existingManifest.outputs) ? existingManifest.outputs : [];
  const completed = new Set(outputs.map((item) => item.adId));

  for (const ad of ads) {
    if (completed.has(ad.adId)) {
      console.log(`Skipping ${ad.adId}; already generated.`);
      continue;
    }
    const brief = chooseBriefForAd(ad, briefOptions);
    const requirementIndex = brief.imageRequirementIndexes[0] ?? 0;
    const swipe = chooseSwipeForAd(ad, swipes);
    const payload = {
      clientId: CLIENT_ID,
      productId: PRODUCT_ID,
      campaignId: state.campaignId,
      assetBriefId: brief.id,
      requirementIndex,
      companySwipeId: swipe.id,
      swipeRequiresProductImage: false,
      swipeContextMode: "minimal",
      swipeBrandName: BRAND_NAME,
      swipeProductName: PRODUCT_NAME,
      swipeHook: ad.headline || ad.adId,
      swipeAngle: buildSwipeAngle(ad),
      aspectRatio: "1:1",
      count: 1,
    };
    console.log(`Generating ${ad.adId} with brief=${brief.id} swipe=${swipe.id}`);
    const started = await authed("/swipes/generate-image-ad", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const detail = await waitForWorkflow(started.workflow_run_id);
    const { assetId, payloadOut } = extractAssetId(detail);
    const asset = await resolveAsset(state.campaignId, assetId);
    const imagePath = path.join(GENERATED_DIR, `${ad.adId.toLowerCase()}-${assetId}.jpg`);
    downloadPublicAsset(asset.public_id, imagePath);
    const record = {
      adId: ad.adId,
      stage: ad.stage,
      headline: ad.headline,
      primaryText: ad.primaryText,
      destination: ad.destination,
      destinationToken: ad.destinationToken,
      assetId,
      publicId: asset.public_id,
      localImagePath: imagePath,
      workflowRunId: started.workflow_run_id,
      temporalWorkflowId: started.temporal_workflow_id,
      assetBriefId: brief.id,
      assetBriefName: brief.name,
      requirementIndex,
      companySwipeId: swipe.id,
      sourceSwipeTitle: swipe.title,
      sourceSwipeMedia: swipe.media || [],
      payloadOut,
    };
    outputs.push(record);
    writeFileSync(existingManifestPath, JSON.stringify({
      campaignId: state.campaignId,
      campaignName: state.campaignName,
      swipeCollectionId: collection.id,
      generatedAt: new Date().toISOString(),
      compliance: {
        productShown: false,
        mechanismRevealAllowed: false,
        source: "manual creative context + swipe image request fields",
      },
      outputs,
    }, null, 2) + "\n");
  }
  mergeState({ generatedManifestPath: existingManifestPath, generatedCount: outputs.length });
  console.log(JSON.stringify({
    campaignId: state.campaignId,
    generatedCount: outputs.length,
    manifestPath: existingManifestPath,
    generatedDir: GENERATED_DIR,
  }, null, 2));
}

async function cmdPackage() {
  await getBackendToken();
  const state = readState();
  if (!state.campaignId) throw new Error("Missing campaignId in state.");
  const metaAds = adManifestBase();
  const generatedManifestPath = state.generatedManifestPath || path.join(OUT_DIR, "generated-manifest.json");
  const generatedManifest = existsSync(generatedManifestPath)
    ? JSON.parse(readFileSync(generatedManifestPath, "utf8"))
    : { outputs: [] };
  const byAdId = new Map((generatedManifest.outputs || []).map((item) => [item.adId, item]));
  const setup = {
    createdAt: new Date().toISOString(),
    campaignId: state.campaignId,
    campaignName: state.campaignName,
    clientId: CLIENT_ID,
    productId: PRODUCT_ID,
    status: "draft_not_published_to_meta",
    delivery: {
      urlsPending: false,
      destinationRegistry: buildDestinationRegistry(),
    },
    compliance: {
      noProductImageOrObject: true,
      noMechanismReveal: true,
      noInventedUrlsOrEvidence: true,
    },
    assets: metaAds.map((ad) => ({
      adId: ad.adId,
      stage: ad.stage,
      primaryText: ad.primaryText,
      headline: ad.headline,
      destinationSource: ad.destination,
      destinationKey: destinationKey(ad),
      destinationToken: destinationToken(ad),
      finalUrl: destinationUrl(ad),
      destinationRationale: destinationRationale(ad),
      generatedAsset: byAdId.get(ad.adId) || null,
    })),
  };
  const packagePath = path.join(OUT_DIR, "campaign-package.json");
  const csvPath = path.join(OUT_DIR, "campaign-package.csv");
  writeFileSync(packagePath, JSON.stringify(setup, null, 2) + "\n");
  const csvHeader = [
    "ad_id",
    "stage",
    "headline",
    "destination_token",
    "destination_key",
    "final_url",
    "asset_id",
    "public_id",
    "local_image_path",
  ];
  const csvRows = setup.assets.map((row) => [
    row.adId,
    row.stage,
    row.headline || "",
    row.destinationToken,
    row.destinationKey,
    row.finalUrl,
    row.generatedAsset?.assetId || "",
    row.generatedAsset?.publicId || "",
    row.generatedAsset?.localImagePath || "",
  ]);
  writeFileSync(
    csvPath,
    [csvHeader, ...csvRows]
      .map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(","))
      .join("\n") + "\n",
  );
  mergeState({ campaignPackagePath: packagePath, campaignPackageCsvPath: csvPath });
  console.log(JSON.stringify({
    campaignId: state.campaignId,
    packagePath,
    csvPath,
    generatedAssets: setup.assets.filter((asset) => asset.generatedAsset).length,
    totalAds: setup.assets.length,
  }, null, 2));
}

function creativeSpecAssetId(spec) {
  return spec.asset_id || spec.assetId || null;
}

function creativeSpecMetadata(spec) {
  if (spec.metadata_json && typeof spec.metadata_json === "object") return spec.metadata_json;
  if (spec.metadata && typeof spec.metadata === "object") return spec.metadata;
  return {};
}

async function cmdReconcileCreativeUrls() {
  await getBackendToken();
  const state = readState();
  if (!state.campaignId) throw new Error("Missing campaignId in state.");

  const generatedManifestPath = state.generatedManifestPath || path.join(OUT_DIR, "generated-manifest.json");
  if (!existsSync(generatedManifestPath)) {
    throw new Error(`Missing generated manifest at ${generatedManifestPath}. Run generate first.`);
  }
  const generatedManifest = JSON.parse(readFileSync(generatedManifestPath, "utf8"));
  const outputs = Array.isArray(generatedManifest.outputs) ? generatedManifest.outputs : [];
  if (!outputs.length) {
    throw new Error(`Generated manifest at ${generatedManifestPath} has no outputs. Run generate first.`);
  }

  const routeByAdId = new Map(adRoutingRows().map((row) => [row.adId, row]));
  const generatedByAssetId = new Map();
  for (const output of outputs) {
    if (!output.adId || !output.assetId) {
      throw new Error(`Generated manifest output is missing adId or assetId: ${JSON.stringify(output)}`);
    }
    const route = routeByAdId.get(output.adId);
    if (!route) throw new Error(`No external routing row found for generated ad ${output.adId}.`);
    generatedByAssetId.set(output.assetId, { output, route });
  }

  const specs = await getCreativeSpecs(state.campaignId);
  if (!Array.isArray(specs) || !specs.length) {
    throw new Error("No Meta creative specs found for this campaign. Run Prepare Meta review before reconciling URLs.");
  }
  const specsByAssetId = new Map();
  for (const spec of specs) {
    const assetId = creativeSpecAssetId(spec);
    if (assetId) specsByAssetId.set(assetId, spec);
  }

  const missingSpecs = outputs
    .filter((output) => !specsByAssetId.has(output.assetId))
    .map((output) => ({ adId: output.adId, assetId: output.assetId }));
  if (missingSpecs.length) {
    throw new Error(
      `Missing Meta creative specs for ${missingSpecs.length} generated assets. Run Prepare Meta review and retry. Missing: ${JSON.stringify(missingSpecs)}`,
    );
  }

  const updated = [];
  const unmatchedCampaignSpecs = [];
  for (const spec of specs) {
    const assetId = creativeSpecAssetId(spec);
    const match = assetId ? generatedByAssetId.get(assetId) : null;
    if (!match) {
      unmatchedCampaignSpecs.push({
        creativeSpecId: spec.id || null,
        assetId,
        currentDestinationUrl: spec.destination_url || spec.destinationUrl || null,
      });
      continue;
    }
    if (!spec.id) throw new Error(`Meta creative spec for asset ${assetId} is missing id.`);

    const { output, route } = match;
    const metadata = {
      ...creativeSpecMetadata(spec),
      externalRoutingAdId: route.adId,
      externalDestinationKey: route.destinationKey,
      externalFinalUrl: route.finalUrl,
      externalRoutingSource: "tenor-pipeline-v3/external-ad-routing.json",
    };
    const response = await authed(`/meta/specs/creatives/${encodeURIComponent(spec.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        destinationUrl: route.finalUrl,
        metadata,
      }),
    });
    updated.push({
      creativeSpecId: spec.id,
      assetId,
      adId: output.adId,
      destinationKey: route.destinationKey,
      finalUrl: route.finalUrl,
      previousDestinationUrl: spec.destination_url || spec.destinationUrl || null,
      updatedDestinationUrl: response.destination_url || response.destinationUrl || route.finalUrl,
    });
  }

  const reconciliationPath = path.join(OUT_DIR, "creative-url-reconciliation.json");
  writeFileSync(
    reconciliationPath,
    JSON.stringify({
      campaignId: state.campaignId,
      generatedManifestPath,
      reconciledAt: new Date().toISOString(),
      updated,
      unmatchedCampaignSpecs,
    }, null, 2) + "\n",
  );
  mergeState({
    creativeUrlReconciliationPath: reconciliationPath,
    creativeUrlReconciledAt: new Date().toISOString(),
    creativeUrlReconciledCount: updated.length,
  });
  console.log(JSON.stringify({
    campaignId: state.campaignId,
    updatedCreativeSpecs: updated.length,
    unmatchedCampaignSpecs: unmatchedCampaignSpecs.length,
    reconciliationPath,
  }, null, 2));
}

async function cmdPackageExternal() {
  const state = readState();
  if (!state.campaignId) throw new Error("Missing campaignId in state.");
  const registry = buildDestinationRegistry();
  const routing = adRoutingRows();
  const registryPath = path.join(OUT_DIR, "external-destination-registry.json");
  const routingPath = path.join(OUT_DIR, "external-ad-routing.json");
  const routingCsvPath = path.join(OUT_DIR, "external-ad-routing.csv");
  const reviewPath = path.join(OUT_DIR, "external-routing-review.md");
  writeFileSync(registryPath, JSON.stringify(registry, null, 2) + "\n");
  writeFileSync(routingPath, JSON.stringify({ schemaVersion: 1, campaignId: state.campaignId, routing }, null, 2) + "\n");
  writeCsv(routing, routingCsvPath);
  const counts = routing.reduce((acc, row) => {
    acc[row.destinationKey] = (acc[row.destinationKey] || 0) + 1;
    return acc;
  }, {});
  writeFileSync(
    reviewPath,
    [
      "# Tenor External Destination Routing Review",
      "",
      `Campaign: ${state.campaignName || state.campaignId}`,
      "",
      "## Destination Counts",
      "",
      ...Object.entries(counts).map(([key, count]) => `- ${key}: ${count}`),
      "",
      "## URL Status",
      "",
      "- Final URLs are supplied.",
      "- No fake URLs were inserted.",
      "- Advertorial and listicle destinations all point onward to `sales_pdp` in the registry.",
      "",
      "## Compliance Carryover",
      "",
      "- Product image/object remains disallowed for generated ad creatives.",
      "- Mechanism reveal remains disallowed for generated ad creatives.",
      "- Destination-specific product/mechanism details stay on the landing pages, not in the ad image.",
      "",
      "## Routing",
      "",
      "| Ad | Destination | Final URL | Headline | Rationale |",
      "| --- | --- | --- | --- | --- |",
      ...routing.map((row) => `| ${row.adId} | ${row.destinationKey} | ${row.finalUrl} | ${String(row.headline || "").replaceAll("|", "\\|")} | ${row.rationale.replaceAll("|", "\\|")} |`),
      "",
    ].join("\n"),
  );
  await cmdPackage();
  mergeState({
    externalFunnelMode: true,
    externalDestinationRegistryPath: registryPath,
    externalAdRoutingPath: routingPath,
    externalAdRoutingCsvPath: routingCsvPath,
    externalRoutingReviewPath: reviewPath,
  });
  console.log(JSON.stringify({
    campaignId: state.campaignId,
    registryPath,
    routingPath,
    routingCsvPath,
    reviewPath,
    destinationCounts: counts,
  }, null, 2));
}

async function main() {
  mkdirSync(OUT_DIR, { recursive: true });
  const [command, ...rest] = process.argv.slice(2);
  if (!command) {
    console.log(usage());
    process.exitCode = 1;
    return;
  }
  if (command === "inspect") return cmdInspect();
  if (command === "create-draft") return cmdCreateDraft();
  if (command === "start-planning") return cmdStartPlanning();
  if (command === "approve-planning-experiments") return cmdApprovePlanningExperiments();
  if (command === "load-context") return cmdLoadContext();
  if (command === "generate-funnels") return cmdGenerateFunnels();
  if (command === "workflow-status") return cmdWorkflowStatus(rest);
  if (command === "stop-workflow") return cmdStopWorkflow(rest);
  if (command === "list-funnels") return cmdListFunnels();
  if (command === "delete-campaign-funnels") return cmdDeleteCampaignFunnels();
  if (command === "package-external") return cmdPackageExternal();
  if (command === "generate") return cmdGenerate(rest);
  if (command === "create-launch-specs") return cmdCreateLaunchSpecs();
  if (command === "validate-publish") return cmdValidatePublish();
  if (command === "publish-now") return cmdPublishNow();
  if (command === "reconcile-creative-urls") return cmdReconcileCreativeUrls();
  if (command === "package") return cmdPackage();
  throw new Error(`Unknown command: ${command}\n${usage()}`);
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exitCode = 1;
});
