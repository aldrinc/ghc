import fs from "node:fs";
import path from "node:path";

const API_KEY = process.env.KLAVIYO_PRIVATE_KEY;
const REVISION = "2026-04-15";
const API_BASE = "https://a.klaviyo.com/api";
const ARTIFACT = path.resolve("outputs/tenor-welcome-lead-nurturer-compressed-review.md");
const TENOR_HOME_URL = "https://shoptenorco.com/";

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

function slug(value) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 60);
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
  const matches = [...markdown.matchAll(/^### (Email \d+|Conditional Follow-Up \d+) [\s\S]*?(?=^### (?:Email \d+|Conditional Follow-Up \d+)|^## RMBC Audit Summary)/gm)];
  return matches.map((match, index) => {
    const section = match[0].trim();
    const heading = section.split("\n")[0].replace(/^###\s*/, "").trim();
    const subject = field(section, "Subject");
    const preview = field(section, "Preview");
    const from = field(section, "From");
    const cta = field(section, "CTA");
    const compliance = field(section, "Compliance note");
    const trigger = field(section, "Trigger");
    const send = field(section, "Send");
    const strategicJob = field(section, "Strategic job");
    const body = bodyBetween(section);
    const kind = heading.startsWith("Conditional") ? "conditional" : "core";
    const sequence = String(index + 1).padStart(2, "0");
    return { heading, subject, preview, from, cta, compliance, trigger, send, strategicJob, body, kind, sequence };
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
    email.trigger ? `<p style="margin:0 0 7px;color:#6b7280;font-size:13px;line-height:1.45;"><strong>Trigger:</strong> ${escapeHtml(email.trigger)}</p>` : "",
    email.send ? `<p style="margin:0 0 7px;color:#6b7280;font-size:13px;line-height:1.45;"><strong>Send:</strong> ${escapeHtml(email.send)}</p>` : "",
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
    const message = JSON.stringify(json, null, 2);
    throw new Error(`${method} ${endpoint} failed (${res.status}): ${message}`);
  }
  return json;
}

async function main() {
  const markdown = fs.readFileSync(ARTIFACT, "utf8");
  const emails = parseEmails(markdown);
  if (emails.length !== 7) {
    throw new Error(`Expected 7 emails, found ${emails.length}`);
  }

  const runId = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
  const results = [];

  for (const email of emails) {
    const prefix = email.kind === "core" ? "Core" : "Conditional";
    const name = `[Tenor] DDE Welcome 5+2 ${runId} - ${prefix} ${email.sequence} - ${email.subject}`;
    const payload = {
      data: {
        type: "template",
        attributes: {
          name,
          editor_type: "CODE",
          html: htmlTemplate(email),
          text: textTemplate(email),
        },
      },
    };
    const created = await klaviyo("POST", "/templates", payload);
    results.push({
      sequence: email.sequence,
      heading: email.heading,
      subject: email.subject,
      template_id: created.data.id,
      template_name: created.data.attributes.name,
    });
    console.log(`created template ${created.data.id}: ${name}`);
  }

  let flows = null;
  try {
    flows = await klaviyo("GET", "/flows?page[size]=50&fields[flow]=name,status,trigger_type,archived,created,updated", null);
  } catch (error) {
    flows = { error: error.message };
  }

  const manifest = {
    created_at: new Date().toISOString(),
    artifact: ARTIFACT,
    revision: REVISION,
    templates: results,
    existing_flows_snapshot: Array.isArray(flows?.data)
      ? flows.data.map((flow) => ({
          id: flow.id,
          name: flow.attributes?.name,
          status: flow.attributes?.status,
          trigger_type: flow.attributes?.trigger_type,
          archived: flow.attributes?.archived,
        }))
      : flows,
  };

  const manifestPath = path.resolve(`outputs/klaviyo-tenor-template-manifest-${runId}.json`);
  fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`manifest ${manifestPath}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
