import fs from "node:fs";
import path from "node:path";

const API_KEY = process.env.KLAVIYO_PRIVATE_KEY;
const REVISION = "2026-04-15";
const API_BASE = "https://a.klaviyo.com/api";
const TENOR_HOME_URL = "https://shoptenorco.com/";

const TEMPLATE_IDS = [
  "RhsKJf",
  "YtahLb",
  "SsRAC7",
  "W3HmD5",
  "RPQxZu",
  "SZfnTk",
  "RKdhE6",
];

if (!API_KEY) {
  console.error("KLAVIYO_PRIVATE_KEY is required in the environment.");
  process.exit(1);
}

function tenorWordmark() {
  return `<a href="${TENOR_HOME_URL}" aria-label="Tenor" style="display:inline-block;margin:0 0 20px;color:#000000;text-decoration:none;font-family:'Arial Black',Arial,Helvetica,sans-serif;font-size:28px;line-height:1;font-weight:900;letter-spacing:0;text-transform:uppercase;">TENOR</a>`;
}

function patchHtml(html) {
  const wordmark = tenorWordmark();
  const textHeader = /<p style="margin:0 0 6px;color:#6b7280;font-size:12px;text-transform:uppercase;letter-spacing:0\.08em;">Tenor<\/p>/;
  const existingWordmark = /<a href="https:\/\/shoptenorco\.com\/" aria-label="Tenor" style="display:inline-block;margin:0 0 20px;color:#000000;text-decoration:none;font-family:'Arial Black',Arial,Helvetica,sans-serif;font-size:28px;line-height:1;font-weight:900;letter-spacing:0;text-transform:uppercase;">TENOR<\/a>/;

  if (existingWordmark.test(html)) {
    return html;
  }
  if (textHeader.test(html)) {
    return html.replace(textHeader, wordmark);
  }
  throw new Error("Could not find the Tenor text header to replace.");
}

async function klaviyo(method, endpoint, body) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method,
    headers: {
      Authorization: `Klaviyo-API-Key ${API_KEY}`,
      accept: "application/vnd.api+json",
      "content-type": "application/vnd.api+json",
      revision: REVISION,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    json = { raw: text };
  }
  if (!res.ok) {
    throw new Error(`${method} ${endpoint} failed (${res.status}): ${JSON.stringify(json, null, 2)}`);
  }
  return json;
}

async function main() {
  const runId = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
  const results = [];

  for (const id of TEMPLATE_IDS) {
    const before = await klaviyo("GET", `/templates/${id}?fields[template]=name,editor_type,html,text`, null);
    const htmlBefore = before.data.attributes.html ?? "";
    const htmlAfter = patchHtml(htmlBefore);
    const changed = htmlAfter !== htmlBefore;

    if (changed) {
      await klaviyo("PATCH", `/templates/${id}`, {
        data: {
          type: "template",
          id,
          attributes: {
            html: htmlAfter,
          },
        },
      });
    }

    const after = await klaviyo("GET", `/templates/${id}?fields[template]=name,editor_type,html,text`, null);
    const htmlVerified = after.data.attributes.html ?? "";
    results.push({
      template_id: id,
      template_name: after.data.attributes.name,
      editor_type: after.data.attributes.editor_type,
      changed,
      has_wordmark: htmlVerified.includes('aria-label="Tenor"') && htmlVerified.includes(">TENOR</a>"),
      has_old_text_header: htmlVerified.includes(">Tenor</p>"),
      has_unsubscribe: htmlVerified.includes("unsubscribe"),
      html_bytes: Buffer.byteLength(htmlVerified),
    });
    console.log(`${changed ? "patched" : "already patched"} ${id}: ${after.data.attributes.name}`);
  }

  const manifestPath = path.resolve(`outputs/klaviyo-tenor-logo-patch-manifest-${runId}.json`);
  fs.writeFileSync(
    manifestPath,
    `${JSON.stringify(
      {
        created_at: new Date().toISOString(),
        tenor_home_url: TENOR_HOME_URL,
        template_ids: TEMPLATE_IDS,
        results,
      },
      null,
      2,
    )}\n`,
  );
  console.log(`manifest ${manifestPath}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
