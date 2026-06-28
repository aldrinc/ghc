import fs from "node:fs";
import path from "node:path";

const API_KEY = process.env.KLAVIYO_PRIVATE_KEY;
const REVISION = "2026-04-15";
const API_BASE = "https://a.klaviyo.com/api";
const ARTIFACT = path.resolve("outputs/tenor-welcome-lead-nurturer-compressed-review.md");
const SOURCE_FLOW_INSPECT = path.resolve("outputs/klaviyo-ember-welcome-flow-inspect.json");
const TENOR_LIST_ID = "T75wvB";
const FROM_EMAIL = "support@shoptenorco.com";
const FROM_LABEL = "Dr. Adam Reese, Tenor";

if (!API_KEY) {
  console.error("KLAVIYO_PRIVATE_KEY is required in the environment.");
  process.exit(1);
}

function latestManifest() {
  const files = fs
    .readdirSync(path.resolve("outputs"))
    .filter((name) => /^klaviyo-tenor-template-manifest-\d+\.json$/.test(name))
    .sort();
  if (!files.length) {
    throw new Error("No Klaviyo Tenor template manifest found.");
  }
  return path.resolve("outputs", files.at(-1));
}

function field(section, label) {
  const re = new RegExp(`\\*\\*${label}:\\*\\*\\s*([^\\n]+)`);
  return section.match(re)?.[1]?.trim() ?? "";
}

function parseCoreEmails(markdown) {
  const matches = [
    ...markdown.matchAll(/^### Email \d+ [\s\S]*?(?=^### (?:Email \d+|Conditional Follow-Up \d+)|^## RMBC Audit Summary)/gm),
  ];
  return matches.slice(0, 5).map((match, index) => {
    const section = match[0].trim();
    const heading = section.split("\n")[0].replace(/^###\s*/, "").trim();
    return {
      sequence: String(index + 1).padStart(2, "0"),
      heading,
      subject: field(section, "Subject"),
      preview: field(section, "Preview"),
    };
  });
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

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function buildDraftWelcomeFlow(sourceDefinition, emails, templateManifest) {
  const templateBySequence = new Map(templateManifest.templates.map((item) => [item.sequence, item]));
  const actions = clone(sourceDefinition.actions.slice(0, 9));
  const delayValues = [1, 2, 2, 2];
  let emailIndex = 0;
  let delayIndex = 0;

  for (const action of actions) {
    const originalId = action.id;
    action.temporary_id = originalId;
    delete action.id;

    if (action.type === "time-delay") {
      action.data.value = delayValues[delayIndex++];
      action.data.secondary_value = null;
      action.data.timezone = "profile";
      action.data.delay_until_weekdays = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
      ];
      continue;
    }

    if (action.type !== "send-email") {
      continue;
    }

    const email = emails[emailIndex++];
    const template = templateBySequence.get(email.sequence);
    if (!template) {
      throw new Error(`Missing template for sequence ${email.sequence}`);
    }

    action.data.status = "draft";
    action.data.message.from_email = FROM_EMAIL;
    action.data.message.from_label = FROM_LABEL;
    action.data.message.reply_to_email = FROM_EMAIL;
    action.data.message.subject_line = email.subject;
    action.data.message.preview_text = email.preview;
    action.data.message.template_id = template.template_id;
    delete action.data.message.id;
    action.data.message.smart_sending_enabled = true;
    action.data.message.transactional = false;
    action.data.message.add_tracking_params = false;
    action.data.message.custom_tracking_params = null;
    action.data.message.additional_filters = null;
    action.data.message.name = `[TENOR] DDE Welcome E${email.sequence} - ${email.heading.replace(
      /^Email \d+\s+(?:-|\u2014)\s+/,
      "",
    )}`;
  }

  actions.at(-1).links.next = null;

  return {
    triggers: [{ type: "list", id: TENOR_LIST_ID }],
    profile_filter: sourceDefinition.profile_filter ?? null,
    actions,
    entry_action_id: sourceDefinition.entry_action_id,
  };
}

async function main() {
  const runId = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
  const manifestPath = latestManifest();
  const templateManifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const sourceInspect = JSON.parse(fs.readFileSync(SOURCE_FLOW_INSPECT, "utf8"));
  const emails = parseCoreEmails(fs.readFileSync(ARTIFACT, "utf8"));

  if (emails.length !== 5) {
    throw new Error(`Expected 5 core emails, found ${emails.length}`);
  }

  const definition = buildDraftWelcomeFlow(sourceInspect.flow.attributes.definition, emails, templateManifest);
  const payload = {
    data: {
      type: "flow",
      attributes: {
        name: `Tenor - Daily Drive Essentials Welcome Lead Nurturer - Draft ${runId}`,
        definition,
      },
    },
  };

  const requestPath = path.resolve(`outputs/klaviyo-tenor-welcome-flow-create-request-${runId}.json`);
  fs.writeFileSync(requestPath, `${JSON.stringify(payload, null, 2)}\n`);

  const created = await klaviyo("POST", "/flows?additional-fields[flow]=definition", payload);
  const responsePath = path.resolve(`outputs/klaviyo-tenor-welcome-flow-create-response-${runId}.json`);
  fs.writeFileSync(responsePath, `${JSON.stringify(created, null, 2)}\n`);

  const actions = await klaviyo("GET", `/flows/${created.data.id}/flow-actions?page[size]=50`, null);
  const verificationPath = path.resolve(`outputs/klaviyo-tenor-welcome-flow-actions-${runId}.json`);
  fs.writeFileSync(verificationPath, `${JSON.stringify(actions, null, 2)}\n`);

  const configManifest = {
    created_at: new Date().toISOString(),
    template_manifest: manifestPath,
    source_flow_inspect: SOURCE_FLOW_INSPECT,
    tenor_list_id: TENOR_LIST_ID,
    draft_flow_id: created.data.id,
    draft_flow_name: created.data.attributes.name,
    draft_flow_status: created.data.attributes.status,
    draft_flow_trigger_type: created.data.attributes.trigger_type,
    request_path: requestPath,
    response_path: responsePath,
    verification_path: verificationPath,
    core_templates_used: templateManifest.templates.slice(0, 5),
    conditional_templates_created_not_attached: templateManifest.templates.slice(5),
  };
  const configManifestPath = path.resolve(`outputs/klaviyo-tenor-config-manifest-${runId}.json`);
  fs.writeFileSync(configManifestPath, `${JSON.stringify(configManifest, null, 2)}\n`);

  console.log(`created draft flow ${created.data.id}: ${created.data.attributes.name}`);
  console.log(`status ${created.data.attributes.status}; trigger ${created.data.attributes.trigger_type}`);
  console.log(`actions ${actions.data?.length ?? 0}`);
  console.log(`manifest ${configManifestPath}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
