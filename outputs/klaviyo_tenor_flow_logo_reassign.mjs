import fs from "node:fs";
import path from "node:path";

const API_KEY = process.env.KLAVIYO_PRIVATE_KEY;
const REVISION = "2026-04-15";
const API_BASE = "https://a.klaviyo.com/api";

const FLOW_ACTION_TEMPLATE_MAP = [
  { action_id: "105690567", source_template_id: "RhsKJf" },
  { action_id: "105690569", source_template_id: "YtahLb" },
  { action_id: "105690571", source_template_id: "SsRAC7" },
  { action_id: "105690573", source_template_id: "W3HmD5" },
  { action_id: "105690576", source_template_id: "RPQxZu" },
];

if (!API_KEY) {
  console.error("KLAVIYO_PRIVATE_KEY is required in the environment.");
  process.exit(1);
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

function hasWordmark(html) {
  return html.includes('aria-label="Tenor"') && html.includes(">TENOR</a>");
}

async function main() {
  const runId = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
  const results = [];

  for (const item of FLOW_ACTION_TEMPLATE_MAP) {
    const beforeAction = await klaviyo("GET", `/flow-actions/${item.action_id}`, null);
    const beforeDefinition = beforeAction.data.attributes.definition;
    const beforeTemplateId = beforeDefinition.data.message.template_id;
    let beforeTemplateHasWordmark = false;

    try {
      const beforeTemplate = await klaviyo("GET", `/templates/${beforeTemplateId}?fields[template]=html`, null);
      beforeTemplateHasWordmark = hasWordmark(beforeTemplate.data.attributes.html ?? "");
    } catch {
      beforeTemplateHasWordmark = false;
    }

    let reassigned = false;
    if (!beforeTemplateHasWordmark) {
      const nextDefinition = JSON.parse(JSON.stringify(beforeDefinition));
      nextDefinition.data.message.template_id = item.source_template_id;
      await klaviyo("PATCH", `/flow-actions/${item.action_id}`, {
        data: {
          type: "flow-action",
          id: item.action_id,
          attributes: {
            definition: nextDefinition,
          },
        },
      });
      reassigned = true;
      await new Promise((resolve) => setTimeout(resolve, 400));
    }

    const afterAction = await klaviyo("GET", `/flow-actions/${item.action_id}`, null);
    const afterDefinition = afterAction.data.attributes.definition;
    const afterTemplateId = afterDefinition.data.message.template_id;
    const afterTemplate = await klaviyo("GET", `/templates/${afterTemplateId}?fields[template]=name,editor_type,html`, null);
    const afterHtml = afterTemplate.data.attributes.html ?? "";

    results.push({
      action_id: item.action_id,
      source_template_id: item.source_template_id,
      before_template_id: beforeTemplateId,
      after_template_id: afterTemplateId,
      reassigned,
      subject: afterDefinition.data.message.subject_line,
      status: afterDefinition.data.status,
      template_name: afterTemplate.data.attributes.name,
      editor_type: afterTemplate.data.attributes.editor_type,
      has_wordmark: hasWordmark(afterHtml),
      has_old_text_header: afterHtml.includes(">Tenor</p>"),
      has_unsubscribe: afterHtml.includes("unsubscribe"),
      html_bytes: Buffer.byteLength(afterHtml),
    });
    console.log(`${reassigned ? "reassigned" : "already current"} ${item.action_id}: ${beforeTemplateId} -> ${afterTemplateId}`);
    await new Promise((resolve) => setTimeout(resolve, 400));
  }

  const manifestPath = path.resolve(`outputs/klaviyo-tenor-flow-logo-reassign-manifest-${runId}.json`);
  fs.writeFileSync(
    manifestPath,
    `${JSON.stringify(
      {
        created_at: new Date().toISOString(),
        flow_id: "Vy4zyb",
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
