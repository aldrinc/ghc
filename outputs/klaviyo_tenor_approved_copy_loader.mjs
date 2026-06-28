import fs from "node:fs";
import path from "node:path";

const API_KEY = process.env.KLAVIYO_PRIVATE_KEY;
const REVISION = "2026-04-15";
const API_BASE = "https://a.klaviyo.com/api";
const ARTIFACT = path.resolve("outputs/tenor-welcome-lead-nurturer-compressed-review.md");
const TENOR_HOME_URL = "https://shoptenorco.com/";
const OFFER_URL = "https://shoptenorco.com/8b89a76d/daily-drive-essentials/sales-page/";
const FROM_EMAIL = "support@shoptenorco.com";
const DRY_RUN = process.env.DRY_RUN === "1";

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

if (!API_KEY && !DRY_RUN) {
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

function inlineFormat(value) {
  return escapeHtml(value).replace(/\*\*([^*]+)\*\*/g, '<strong style="font-weight:700;color:#111827;">$1</strong>');
}

function field(section, label) {
  const re = new RegExp(`\\*\\*${label}:\\*\\*\\s*([^\\n]+)`);
  return section.match(re)?.[1]?.trim() ?? "";
}

function cleanCta(cta) {
  const cleaned = String(cta ?? "")
    .replace(/\s*\([^)]*\)\s*$/g, "")
    .replace(/\s*\u2192\s*\[.*?\]\s*$/g, "")
    .trim();
  return /^none\b/i.test(cleaned) ? "" : cleaned;
}

function parseEmails(markdown) {
  const matches = [
    ...markdown.matchAll(
      /^## (Core Email \d+|Conditional Follow-Up \d+) [\s\S]*?(?=^## (?:Core Email \d+|Conditional Follow-Up \d+|RMBC Copy Audit|Key Quality Gates|Engagement Notes)|(?![\s\S]))/gm,
    ),
  ];

  return matches.map((match, index) => {
    const section = match[0].trim();
    const title = section.split("\n")[0].replace(/^##\s*/, "").trim();
    const sequence = String(index + 1).padStart(2, "0");
    const cta = cleanCta(field(section, "CTA"));
    const bodyStart = section.search(/\*\*From label:\*\*[^\n]*\n/);
    if (bodyStart < 0) {
      throw new Error(`Missing From label for ${title}`);
    }
    const bodyAfterFrom = section.slice(bodyStart).replace(/^[^\n]*\n+/, "");
    const body = bodyAfterFrom
      .replace(/\n\*\*CTA:\*\*[\s\S]*$/m, "")
      .replace(/\n\*\*Compliance notes:\*\*[\s\S]*$/m, "")
      .trim();
    return {
      sequence,
      title,
      kind: title.startsWith("Core") ? "core" : "conditional",
      subject: field(section, "Subject"),
      preview: field(section, "Preview text") || field(section, "Preview"),
      fromLabel: field(section, "From label") || "Dr. Adam Reese, Tenor",
      cta,
      trigger: field(section, "Trigger"),
      step: field(section, "Step"),
      body,
    };
  });
}

function renderList(lines) {
  const rows = lines
    .map((line) => {
      const bullet = line.match(/^\s*[-*]\s+(.+)$/);
      const numbered = line.match(/^\s*(\d+)\.\s+(.+)$/);
      if (bullet) {
        return { marker: "&bull;", text: bullet[1] };
      }
      if (numbered) {
        return { marker: `${numbered[1]}.`, text: numbered[2] };
      }
      return null;
    })
    .filter(Boolean);

  return `<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:2px 0 18px;">
    ${rows
      .map(
        (row) => `<tr>
          <td valign="top" style="width:24px;padding:0 8px 8px 0;color:#111827;font-size:15px;line-height:1.5;font-weight:700;">${escapeHtml(row.marker)}</td>
          <td valign="top" style="padding:0 0 8px;color:#202936;font-size:15px;line-height:1.5;">${inlineFormat(row.text)}</td>
        </tr>`,
      )
      .join("\n")}
  </table>`;
}

function renderCallout(rawLines) {
  const lines = rawLines.filter((line) => line.trim() && !/^```/.test(line.trim()));
  const html = [];
  let listBuffer = [];

  const flushList = () => {
    if (listBuffer.length) {
      html.push(renderList(listBuffer));
      listBuffer = [];
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (/^\d+\.\s+/.test(trimmed) || /^[-*]\s+/.test(trimmed)) {
      listBuffer.push(trimmed);
      continue;
    }
    flushList();

    if (/^System \d+\s+\u2014/.test(trimmed)) {
      html.push(`<p style="margin:14px 0 4px;color:#111827;font-size:15px;line-height:1.45;font-weight:700;">${inlineFormat(trimmed)}</p>`);
      continue;
    }

    if (/Guarantee|Triad|Supply|Protocol/i.test(trimmed) && trimmed.length < 80) {
      html.push(`<p style="margin:0 0 8px;color:#111827;font-size:16px;line-height:1.45;font-weight:700;">${inlineFormat(trimmed)}</p>`);
      continue;
    }

    html.push(`<p style="margin:0 0 10px;color:#202936;font-size:15px;line-height:1.5;">${inlineFormat(trimmed)}</p>`);
  }
  flushList();

  return `<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:26px 0 24px;border:1px solid #d8d1c4;background:#fbfaf6;">
    <tr>
      <td style="padding:18px 20px;">
        ${html.join("\n")}
      </td>
    </tr>
  </table>`;
}

function renderCta(email) {
  if (!email.cta) return "";
  return `<table role="presentation" cellspacing="0" cellpadding="0" style="margin:30px 0 10px;">
    <tr>
      <td bgcolor="#111827" style="border-radius:2px;">
        <a href="${OFFER_URL}" style="display:inline-block;color:#ffffff;text-decoration:none;padding:14px 22px;font-size:15px;line-height:1.2;font-weight:700;">${inlineFormat(email.cta)}</a>
      </td>
    </tr>
  </table>`;
}

function renderBody(email) {
  const lines = email.body.replace(/\r/g, "").split("\n");
  const html = [];
  let ctaInserted = false;
  let skipNextCtaLine = false;

  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (!trimmed || trimmed === "```") continue;

    if (trimmed === "[CALLOUT]") {
      const callout = [];
      i += 1;
      while (i < lines.length && lines[i].trim() !== "[/CALLOUT]") {
        callout.push(lines[i]);
        i += 1;
      }
      html.push(renderCallout(callout));
      continue;
    }

    if (trimmed === "[CTA Button]") {
      html.push(renderCta(email));
      ctaInserted = true;
      skipNextCtaLine = true;
      continue;
    }

    const unbolded = trimmed.replace(/\*\*/g, "");
    if (skipNextCtaLine && email.cta && unbolded === email.cta) {
      skipNextCtaLine = false;
      continue;
    }
    skipNextCtaLine = false;

    if (email.cta && unbolded === email.cta) {
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed) || /^[-*]\s+/.test(trimmed)) {
      const listLines = [trimmed];
      while (i + 1 < lines.length && (/^\s*\d+\.\s+/.test(lines[i + 1]) || /^\s*[-*]\s+/.test(lines[i + 1]))) {
        i += 1;
        listLines.push(lines[i].trim());
      }
      html.push(renderList(listLines));
      continue;
    }

    if (trimmed.startsWith("\u2014 ")) {
      html.push(`<p style="margin:28px 0 0;color:#2f3743;font-size:15px;line-height:1.55;">${inlineFormat(trimmed)}</p>`);
      continue;
    }

    if (/^\*\*[^*]+\*\*$/.test(trimmed) && trimmed.length <= 90) {
      html.push(`<p style="margin:0 0 18px;color:#111827;font-size:16px;line-height:1.5;font-weight:700;">${inlineFormat(trimmed)}</p>`);
      continue;
    }

    html.push(`<p style="margin:0 0 18px;color:#202936;font-size:16px;line-height:1.58;">${inlineFormat(trimmed)}</p>`);
  }

  if (email.cta && !ctaInserted) {
    html.push(renderCta(email));
  }

  return html.join("\n");
}

function htmlTemplate(email) {
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(email.subject)}</title>
</head>
<body style="margin:0;padding:0;background:#f6f1e8;font-family:Arial,Helvetica,sans-serif;">
  <div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;">${escapeHtml(email.preview)}</div>
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
              ${renderBody(email)}
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

function plainText(email) {
  const body = email.body
    .replace(/^```$/gm, "")
    .replace(/^\[CTA Button\]$/gm, "")
    .replace(/\*\*/g, "")
    .replace(/\[CALLOUT\]/g, "")
    .replace(/\[\/CALLOUT\]/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  const lines = [
    email.subject,
    "",
    email.preview,
    "",
    body,
    "",
    email.cta ? `CTA: ${email.cta} - ${OFFER_URL}` : "",
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

function verifyHtml(email, html) {
  const failures = [];
  if (!html.includes('aria-label="Tenor"')) failures.push("missing_header_wordmark");
  if (!html.includes("{% unsubscribe %}")) failures.push("missing_unsubscribe");
  if (html.includes("[CALLOUT]") || html.includes("[/CALLOUT]") || html.includes("[CTA Button]")) failures.push("raw_review_markers_visible");
  if (email.body.includes("**") && !html.includes("<strong")) failures.push("missing_bold_rendering");
  if (email.body.includes("[CALLOUT]") && !html.includes("border:1px solid #d8d1c4")) failures.push("missing_callout_rendering");
  if (email.cta && !html.includes(OFFER_URL)) failures.push("missing_cta_link");
  if (/Compliance notes:/i.test(html)) failures.push("internal_compliance_visible");
  return failures;
}

async function main() {
  const runId = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
  const markdown = fs.readFileSync(ARTIFACT, "utf8");
  const emails = parseEmails(markdown);
  if (emails.length !== 7) {
    throw new Error(`Expected 7 emails, found ${emails.length}`);
  }

  if (DRY_RUN) {
    const previews = emails.map((email) => {
      const html = htmlTemplate(email);
      const previewPath = path.resolve(`outputs/tenor-approved-copy-template-preview-${runId}-${email.sequence}.html`);
      fs.writeFileSync(previewPath, html);
      return {
        sequence: email.sequence,
        subject: email.subject,
        preview: email.preview,
        cta: email.cta,
        has_callout_source: email.body.includes("[CALLOUT]"),
        has_bold_source: email.body.includes("**"),
        html_bytes: Buffer.byteLength(html),
        preview_path: previewPath,
        failures: verifyHtml(email, html),
      };
    });
    const dryRunPath = path.resolve(`outputs/klaviyo-tenor-approved-copy-dry-run-${runId}.json`);
    fs.writeFileSync(dryRunPath, `${JSON.stringify({ created_at: new Date().toISOString(), previews }, null, 2)}\n`);
    console.log(`dry_run ${dryRunPath}`);
    console.log(`failures ${previews.flatMap((item) => item.failures).length}`);
    return;
  }

  const saved = [];
  for (const email of emails) {
    const templateId = SAVED_TEMPLATE_IDS.get(email.sequence);
    const prefix = email.kind === "core" ? "Core" : "Conditional";
    const name = `[Tenor] DDE Direct Approved ${runId} - ${prefix} ${email.sequence} - ${email.subject}`;
    const html = htmlTemplate(email);
    const text = plainText(email);
    await klaviyo("PATCH", `/templates/${templateId}`, {
      data: {
        type: "template",
        id: templateId,
        attributes: { name, html, text },
      },
    });
    const after = await klaviyo("GET", `/templates/${templateId}?fields[template]=name,editor_type,html,text`, null);
    const htmlAfter = after.data.attributes.html ?? "";
    const failures = verifyHtml(email, htmlAfter);
    saved.push({
      sequence: email.sequence,
      subject: email.subject,
      template_id: templateId,
      template_name: after.data.attributes.name,
      html_bytes: Buffer.byteLength(htmlAfter),
      failures,
    });
    console.log(`patched saved template ${templateId}: ${email.subject}`);
    await new Promise((resolve) => setTimeout(resolve, 300));
  }

  const emailBySequence = new Map(emails.map((email) => [email.sequence, email]));
  const flow = [];
  for (const item of FLOW_ACTION_TEMPLATE_MAP) {
    const email = emailBySequence.get(item.sequence);
    const beforeAction = await klaviyo("GET", `/flow-actions/${item.action_id}`, null);
    const definition = JSON.parse(JSON.stringify(beforeAction.data.attributes.definition));
    definition.data.status = "draft";
    definition.data.message.from_email = FROM_EMAIL;
    definition.data.message.from_label = email.fromLabel;
    definition.data.message.reply_to_email = FROM_EMAIL;
    definition.data.message.subject_line = email.subject;
    definition.data.message.preview_text = email.preview;
    definition.data.message.template_id = item.source_template_id;
    definition.data.message.name = `[TENOR] DDE Direct E${email.sequence} - ${email.subject}`;

    await klaviyo("PATCH", `/flow-actions/${item.action_id}`, {
      data: {
        type: "flow-action",
        id: item.action_id,
        attributes: { definition },
      },
    });
    await new Promise((resolve) => setTimeout(resolve, 500));

    const afterAction = await klaviyo("GET", `/flow-actions/${item.action_id}`, null);
    const afterDefinition = afterAction.data.attributes.definition;
    const clonedTemplateId = afterDefinition.data.message.template_id;
    const template = await klaviyo("GET", `/templates/${clonedTemplateId}?fields[template]=name,editor_type,html,text`, null);
    const htmlAfter = template.data.attributes.html ?? "";
    const failures = verifyHtml(email, htmlAfter);
    flow.push({
      action_id: item.action_id,
      sequence: email.sequence,
      subject: afterDefinition.data.message.subject_line,
      preview: afterDefinition.data.message.preview_text,
      source_template_id: item.source_template_id,
      cloned_template_id: clonedTemplateId,
      status: afterDefinition.data.status,
      html_bytes: Buffer.byteLength(htmlAfter),
      failures,
    });
    console.log(`updated flow action ${item.action_id}: ${email.subject} -> ${clonedTemplateId}`);
    await new Promise((resolve) => setTimeout(resolve, 300));
  }

  const previewPath = path.resolve(`outputs/tenor-approved-copy-template-preview-${runId}.html`);
  fs.writeFileSync(previewPath, htmlTemplate(emails[0]));

  const manifest = {
    created_at: new Date().toISOString(),
    artifact: ARTIFACT,
    flow_id: "Vy4zyb",
    saved,
    flow,
    preview_path: previewPath,
    failures: [...saved, ...flow].flatMap((item) => item.failures.map((failure) => ({ ...item, failure }))),
  };
  const manifestPath = path.resolve(`outputs/klaviyo-tenor-approved-copy-load-manifest-${runId}.json`);
  fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`manifest ${manifestPath}`);
  console.log(`preview ${previewPath}`);
  console.log(`failures ${manifest.failures.length}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
