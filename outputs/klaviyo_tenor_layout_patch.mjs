import fs from "node:fs";
import path from "node:path";

const API_KEY = process.env.KLAVIYO_PRIVATE_KEY;
const REVISION = "2026-04-15";
const API_BASE = "https://a.klaviyo.com/api";
const ARTIFACT = path.resolve("outputs/tenor-welcome-lead-nurturer-compressed-review.md");
const TENOR_HOME_URL = "https://shoptenorco.com/";

const SAVED_TEMPLATE_IDS = new Map([
  ["01", "RhsKJf"],
  ["02", "YtahLb"],
  ["03", "SsRAC7"],
  ["04", "W3HmD5"],
  ["05", "RPQxZu"],
  ["06", "SZfnTk"],
  ["07", "RKdhE6"],
]);

const FLOW_ACTION_TEMPLATE_MAP = [
  { action_id: "105690567", sequence: "01", source_template_id: "RhsKJf" },
  { action_id: "105690569", sequence: "02", source_template_id: "YtahLb" },
  { action_id: "105690571", sequence: "03", source_template_id: "SsRAC7" },
  { action_id: "105690573", sequence: "04", source_template_id: "W3HmD5" },
  { action_id: "105690576", sequence: "05", source_template_id: "RPQxZu" },
];

if (!API_KEY) {
  console.error("KLAVIYO_PRIVATE_KEY is required in the environment.");
  process.exit(1);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function field(section, label) {
  const re = new RegExp(`\\*\\*${label}:\\*\\*\\s*([^\\n]+)`);
  return section.match(re)?.[1]?.trim() ?? "";
}

function bodyBetween(section) {
  const parts = section.split(/\n---\n/);
  if (parts.length < 3) return "";
  return parts[1]
    .replace(/\n— Dr\. Adam Reese[\s\S]*$/m, "\n— Dr. Adam Reese")
    .trim();
}

function parseEmails(markdown) {
  const matches = [
    ...markdown.matchAll(
      /^### (Email \d+|Conditional Follow-Up \d+) [\s\S]*?(?=^### (?:Email \d+|Conditional Follow-Up \d+)|^## RMBC Audit Summary)/gm,
    ),
  ];
  return matches.map((match, index) => {
    const section = match[0].trim();
    const heading = section.split("\n")[0].replace(/^###\s*/, "").trim();
    const sequence = String(index + 1).padStart(2, "0");
    return {
      heading,
      sequence,
      subject: field(section, "Subject"),
      preview: field(section, "Preview"),
      cta: field(section, "CTA"),
      trigger: field(section, "Trigger"),
      send: field(section, "Send"),
      body: bodyBetween(section),
    };
  });
}

function paragraphs(text) {
  return text
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => {
      if (p.startsWith("— ")) {
        return `<p style="margin:26px 0 0;color:#2f3743;font-size:15px;line-height:1.55;">${escapeHtml(p).replace(/\n/g, "<br>")}</p>`;
      }
      return `<p style="margin:0 0 18px;color:#202936;font-size:16px;line-height:1.58;">${escapeHtml(p).replace(/\n/g, "<br>")}</p>`;
    })
    .join("\n");
}

function cleanCtaText(cta) {
  return escapeHtml(cta.replace(/\s*→\s*\[.*?\]\s*$/g, ""));
}

function ctaBlock(email) {
  if (!email.cta) return "";

  const ctaText = cleanCtaText(email.cta);
  const actionHref = "https://shoptenorco.com/8b89a76d/daily-drive-essentials/sales-page/";

  if (/^reply\b/i.test(email.cta)) {
    return `<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:30px 0 8px;border:1px solid #d8d1c4;background:#fbfaf6;">
                <tr>
                  <td style="padding:18px 20px;">
                    <p style="margin:0 0 6px;color:#7a746b;font-size:12px;line-height:1.4;text-transform:uppercase;font-weight:700;">Hit reply</p>
                    <p style="margin:0;color:#202936;font-size:16px;line-height:1.5;font-weight:600;">${ctaText.replace(/^Reply and\s*/i, "")}</p>
                  </td>
                </tr>
              </table>`;
  }

  if (/^save\b/i.test(email.cta)) {
    return `<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:30px 0 8px;border-left:3px solid #111827;background:#fbfaf6;">
                <tr>
                  <td style="padding:16px 18px;">
                    <p style="margin:0;color:#202936;font-size:15px;line-height:1.5;font-weight:600;">${ctaText}</p>
                  </td>
                </tr>
              </table>`;
  }

  if (/^request\b/i.test(email.cta)) {
    const mailto = "mailto:support@shoptenorco.com?subject=Certificate%20of%20Analysis%20request";
    return `<p style="margin:30px 0 8px;"><a href="${mailto}" style="color:#111827;text-decoration:underline;font-size:16px;line-height:1.5;font-weight:700;">${ctaText}</a></p>`;
  }

  return `<table role="presentation" cellspacing="0" cellpadding="0" style="margin:30px 0 8px;">
            <tr>
              <td bgcolor="#111827" style="border-radius:2px;">
                <a href="${actionHref}" style="display:inline-block;color:#ffffff;text-decoration:none;padding:14px 22px;font-size:15px;line-height:1.2;font-weight:700;">${ctaText}</a>
              </td>
            </tr>
          </table>`;
}

function htmlTemplate(email) {
  const preview = escapeHtml(email.preview);
  const bodyHtml = paragraphs(email.body);
  const ctaHtml = ctaBlock(email);
  const metaRows = [
    email.trigger
      ? `<p style="margin:0 0 7px;color:#6b7280;font-size:13px;line-height:1.45;"><strong>Trigger:</strong> ${escapeHtml(email.trigger)}</p>`
      : "",
    email.send
      ? `<p style="margin:0 0 7px;color:#6b7280;font-size:13px;line-height:1.45;"><strong>Send:</strong> ${escapeHtml(email.send)}</p>`
      : "",
  ].join("");

  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(email.subject)}</title>
</head>
<body style="margin:0;padding:0;background:#f6f1e8;font-family:Arial,Helvetica,sans-serif;">
  <div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;">${preview}</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f6f1e8;margin:0;padding:24px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:#ffffff;border:1px solid #e6ded1;">
          <tr>
            <td align="center" style="padding:28px 32px 24px;border-bottom:1px solid #ece5d8;">
              <a href="${TENOR_HOME_URL}" aria-label="Tenor" style="display:inline-block;color:#000000;text-decoration:none;font-family:'Arial Black',Arial,Helvetica,sans-serif;font-size:30px;line-height:1;font-weight:900;letter-spacing:0;text-transform:uppercase;">TENOR</a>
            </td>
          </tr>
          <tr>
            <td style="padding:34px 40px 36px;">
              <h1 style="margin:0 0 24px;color:#111827;font-size:26px;line-height:1.25;font-weight:700;">${escapeHtml(email.subject)}</h1>
              ${metaRows}
              ${bodyHtml}
              ${ctaHtml}
            </td>
          </tr>
          <tr>
            <td style="padding:24px 40px 30px;background:#fbfaf6;border-top:1px solid #ece5d8;color:#6b7280;font-size:12px;line-height:1.55;">
              <p style="margin:0 0 8px;color:#111827;font-weight:700;">Tenor</p>
              <p style="margin:0 0 10px;">These statements have not been evaluated by the Food and Drug Administration. This product is not intended to diagnose, treat, cure, or prevent any disease. Results vary.</p>
              <p style="margin:0;">{% unsubscribe %}</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>`;
}

function textTemplate(email) {
  const lines = [
    email.subject,
    "",
    email.preview,
    "",
    email.trigger ? `Trigger: ${email.trigger}` : "",
    email.send ? `Send: ${email.send}` : "",
    "",
    email.body,
    "",
    email.cta ? `CTA: ${email.cta}` : "",
    "",
    "These statements have not been evaluated by the Food and Drug Administration. This product is not intended to diagnose, treat, cure, or prevent any disease. Results vary.",
    "Unsubscribe: {% unsubscribe_link %}",
  ];
  return lines.filter((line, i, arr) => line || arr[i - 1]).join("\n").trim();
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

function hasStandardHeader(html) {
  return html.includes("border-bottom:1px solid #ece5d8") && html.includes('aria-label="Tenor"');
}

function hasBrokenReplyButton(email, html) {
  return /^reply\b/i.test(email.cta) && (html.includes('bgcolor="#111827"') || html.includes("background:#111827"));
}

async function main() {
  const runId = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
  const emails = parseEmails(fs.readFileSync(ARTIFACT, "utf8"));
  if (emails.length !== 7) {
    throw new Error(`Expected 7 emails, found ${emails.length}`);
  }

  const emailBySequence = new Map(emails.map((email) => [email.sequence, email]));
  const saved = [];

  for (const email of emails) {
    const templateId = SAVED_TEMPLATE_IDS.get(email.sequence);
    if (!templateId) {
      throw new Error(`Missing saved template id for sequence ${email.sequence}`);
    }
    const html = htmlTemplate(email);
    const text = textTemplate(email);
    await klaviyo("PATCH", `/templates/${templateId}`, {
      data: {
        type: "template",
        id: templateId,
        attributes: { html, text },
      },
    });
    const after = await klaviyo("GET", `/templates/${templateId}?fields[template]=name,editor_type,html,text`, null);
    const htmlAfter = after.data.attributes.html ?? "";
    saved.push({
      sequence: email.sequence,
      template_id: templateId,
      template_name: after.data.attributes.name,
      has_standard_header: hasStandardHeader(htmlAfter),
      has_internal_compliance_note: htmlAfter.includes("Compliance note") || htmlAfter.includes("DSHEA-safe"),
      has_broken_reply_button: hasBrokenReplyButton(email, htmlAfter),
      has_unsubscribe: htmlAfter.includes("unsubscribe"),
      html_bytes: Buffer.byteLength(htmlAfter),
    });
    console.log(`patched saved template ${templateId}`);
    await new Promise((resolve) => setTimeout(resolve, 250));
  }

  const flow = [];
  for (const item of FLOW_ACTION_TEMPLATE_MAP) {
    const email = emailBySequence.get(item.sequence);
    const beforeAction = await klaviyo("GET", `/flow-actions/${item.action_id}`, null);
    const definition = JSON.parse(JSON.stringify(beforeAction.data.attributes.definition));
    definition.data.message.template_id = item.source_template_id;
    await klaviyo("PATCH", `/flow-actions/${item.action_id}`, {
      data: {
        type: "flow-action",
        id: item.action_id,
        attributes: { definition },
      },
    });
    await new Promise((resolve) => setTimeout(resolve, 450));
    const afterAction = await klaviyo("GET", `/flow-actions/${item.action_id}`, null);
    const afterDefinition = afterAction.data.attributes.definition;
    const clonedTemplateId = afterDefinition.data.message.template_id;
    const template = await klaviyo("GET", `/templates/${clonedTemplateId}?fields[template]=name,editor_type,html,text`, null);
    const htmlAfter = template.data.attributes.html ?? "";
    flow.push({
      action_id: item.action_id,
      sequence: item.sequence,
      source_template_id: item.source_template_id,
      cloned_template_id: clonedTemplateId,
      subject: afterDefinition.data.message.subject_line,
      status: afterDefinition.data.status,
      has_standard_header: hasStandardHeader(htmlAfter),
      has_internal_compliance_note: htmlAfter.includes("Compliance note") || htmlAfter.includes("DSHEA-safe"),
      has_broken_reply_button: hasBrokenReplyButton(email, htmlAfter),
      has_unsubscribe: htmlAfter.includes("unsubscribe"),
      html_bytes: Buffer.byteLength(htmlAfter),
    });
    console.log(`recloned flow action ${item.action_id}: ${clonedTemplateId}`);
    await new Promise((resolve) => setTimeout(resolve, 250));
  }

  const previewPath = path.resolve(`outputs/tenor-email-layout-preview-${runId}.html`);
  fs.writeFileSync(previewPath, htmlTemplate(emailBySequence.get("01")));

  const manifest = {
    created_at: new Date().toISOString(),
    flow_id: "Vy4zyb",
    saved,
    flow,
    preview_path: previewPath,
    failures: [...saved, ...flow].filter(
      (item) =>
        !item.has_standard_header ||
        item.has_internal_compliance_note ||
        item.has_broken_reply_button ||
        !item.has_unsubscribe,
    ),
  };
  const manifestPath = path.resolve(`outputs/klaviyo-tenor-layout-patch-manifest-${runId}.json`);
  fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`manifest ${manifestPath}`);
  console.log(`preview ${previewPath}`);
  console.log(`failures ${manifest.failures.length}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
